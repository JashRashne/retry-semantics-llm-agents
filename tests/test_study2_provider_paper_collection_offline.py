"""No live dispatch: hostile one-shot, persistence, and collector checks."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex

from retry_semantics.study2.provider_paper_io import (
    DurablePaperEvidence, PaperIOError, PaperRequest,
    PaperTransportResult, one_shot_http,
)
from retry_semantics.study2.provider_paper_model import PaperModelSession
from retry_semantics.study2.provider_paper_collection import (
    PaperCollectionError, collect_github_arm, collect_razorpay_arm,
    collect_provider_run,
)
from retry_semantics.study2.github_paper_manifest import load_github_paper_manifest
from retry_semantics.study2.razorpay_paper_manifest import load_razorpay_paper_manifest
from retry_semantics.study2 import provider_paper_collection as collection
from retry_semantics.study2 import provider_paper_readiness as readiness
from retry_semantics.study2.provider_paper_readiness import ProviderReadinessError
from retry_semantics.study2.github_paper_runtime import expected_original


def request():
    return PaperRequest("POST", "https://api.razorpay.com/v1/orders",
                        (("Content-Type", "application/json"),), b"{}")


def result(status=200, body=b"{}"):
    return PaperTransportResult(status, (), body, None, True, True, True, 1.0, 1.1)


def evidence(tmp_path, provider="razorpay"):
    return DurablePaperEvidence(tmp_path, provider=provider, family_id="f001",
                                arm_id="a001", manifest_sha256="a" * 64,
                                runtime_sha256={"runtime.py": "b" * 64})


@pytest.mark.parametrize("status", [302, 403, 429, 500])
def test_http_visible_failure_is_one_send_no_redirect(status):
    calls = []

    def handle(outbound):
        calls.append(outbound)
        return httpx.Response(status, headers={"Location": "https://api.razorpay.com/v1/orders"},
                              content=b"failure")

    recorded = one_shot_http(request(), credential="key:SECRET", transport=httpx.MockTransport(handle))
    assert recorded.status == status
    assert len(calls) == 1
    assert calls[0].headers["Authorization"].startswith("Basic ")


def test_http_timeout_is_one_send_and_absolute_deadline():
    calls = []

    def timeout(outbound):
        calls.append(outbound)
        raise httpx.ReadTimeout("offline timeout")

    recorded = one_shot_http(request(), credential="key:SECRET", transport=httpx.MockTransport(timeout))
    assert recorded.error == "ReadTimeout"
    assert len(calls) == 1

    def slow(outbound):
        calls.append(outbound)
        time.sleep(0.1)
        return httpx.Response(200, content=b"{}")

    recorded = one_shot_http(request(), credential="key:SECRET",
                             deadline_seconds=0.01, transport=httpx.MockTransport(slow))
    assert recorded.error == "TimeoutError"
    assert len(calls) == 2


def test_credentials_never_enter_durable_evidence(tmp_path):
    store = evidence(tmp_path)
    store.record("create_order", request(), lambda _: result())
    all_bytes = b"".join(path.read_bytes() for path in tmp_path.iterdir())
    assert b"SECRET" not in all_bytes
    assert b"Authorization" not in all_bytes
    assert b"body_sha256" in all_bytes
    assert b"dispatch_initiated" in all_bytes


def test_failed_intent_prevents_mutation(tmp_path, monkeypatch):
    store = evidence(tmp_path)
    calls = []

    def fail(_name, _value):
        raise OSError("disk full")

    monkeypatch.setattr(store, "_write", fail)
    with pytest.raises(OSError):
        store.record("create_order", request(), lambda _: calls.append(1))
    assert calls == []


def test_failed_result_never_resends(tmp_path, monkeypatch):
    store = evidence(tmp_path)
    original = store._write
    calls = []

    def fail_result(name, value):
        if name.endswith(".result.json"):
            raise OSError("disk full after dispatch")
        original(name, value)

    monkeypatch.setattr(store, "_write", fail_result)
    with pytest.raises(OSError):
        store.record("create_order", request(),
                     lambda _: (calls.append(1), result())[1])
    assert calls == [1]
    assert (tmp_path / "00000.intent.json").exists()


def _completion(action, args):
    calls = [] if action == "finish" else [{
        "id": "call-1", "type": "function",
        "function": {"name": action, "arguments": json.dumps(args)},
    }]
    return {"choices": [{"message": {"role": "assistant", "content": None,
                                     "tool_calls": calls},
                         "finish_reason": "stop" if not calls else "tool_calls"}]}


def test_original_generation_bound_to_frozen_family(tmp_path):
    manifest = load_razorpay_paper_manifest()
    family = manifest["families"][0]
    store = evidence(tmp_path)
    payloads = []

    def complete(payload):
        payloads.append(payload)
        return _completion("create_order", family["target_semantic_m"])

    model = PaperModelSession(provider="razorpay", family=family,
                              common=manifest["model_visible_common"],
                              complete=complete, evidence=store)
    original = model.generate_original()
    assert original["tool_calls"][0]["function"]["name"] == "create_order"
    assert payloads[0]["model"] == "accounts/fireworks/models/deepseek-v4p1-flash"
    assert (tmp_path / "model-original-0.json").exists()
    with pytest.raises(Exception):
        model.generate_original()


def test_github_h0_replay_no_model_and_exact_body(tmp_path):
    manifest = load_github_paper_manifest().as_json()
    family = manifest["families"][0]
    arm = next(x for x in family["arms"] if x["hidden_world"] == "H0"
               and x["policy"] == "EXACT_REPLAY")
    now = [100.0]
    sent = []

    def sender(req):
        sent.append(req)
        if req.method == "GET":
            return result(200, b"[]")
        body = json.loads(req.body)
        return result(201, json.dumps({"number": 91, "title": body["title"],
                                       "body": body["body"], "state": "open"}).encode())

    projection, stopped = collect_github_arm(
        manifest=manifest, family=family, arm=arm,
        evidence=evidence(tmp_path, "github"), send=sender, model=None,
        api_version="2022-11-28", clock=lambda: now[0],
        wait_until=lambda target: now.__setitem__(0, target))
    posts = [x for x in sent if x.method == "POST"]
    assert len(posts) == 1
    frozen = expected_original(manifest, family, arm,
                               api_base="https://api.github.com",
                               api_version="2022-11-28")
    assert posts[0].body == frozen.body
    assert projection.status == "INCONCLUSIVE"  # fixture never returned the created issue
    assert stopped is False
    assert len([x for x in sent if x.method == "GET"]) == 3


def test_github_h0_replay_success_matching_issue_observed(tmp_path):
    manifest = load_github_paper_manifest().as_json()
    family = manifest["families"][0]
    target = family["target_semantic_m"]
    arm = next(x for x in family["arms"] if x["hidden_world"] == "H0"
               and x["policy"] == "EXACT_REPLAY")
    now = [100.0]
    sent = []

    def sender(req):
        sent.append(req)
        if req.method == "GET":
            posts = [x for x in sent if x.method == "POST"]
            if not posts:
                return result(200, b"[]")
            matching_issue = [{
                "number": 91,
                "title": target["title"],
                "body": target["body"] + arm["suffix"],
                "state": "open",
            }]
            return result(200, json.dumps(matching_issue).encode())
        body = json.loads(req.body)
        return result(201, json.dumps({"number": 91, "title": body["title"],
                                       "body": body["body"], "state": "open"}).encode())

    projection, stopped = collect_github_arm(
        manifest=manifest, family=family, arm=arm,
        evidence=evidence(tmp_path, "github"), send=sender, model=None,
        api_version="2022-11-28", clock=lambda: now[0],
        wait_until=lambda target_t: now.__setitem__(0, target_t))
    assert stopped is False
    assert projection.status == "SUCCESS"
    assert projection.state_correct == 1
    assert projection.reason == "CORRECT"
    assert projection.arm_id == arm["arm_id"]


def test_razorpay_h0_replay_no_original_dispatch(tmp_path):
    manifest = load_razorpay_paper_manifest()
    family = manifest["families"][0]
    arm = next(x for x in family["arms"] if x["hidden_world"] == "H0"
               and x["policy"] == "EXACT_REPLAY")
    now = [100.0]
    sent = []

    def sender(req):
        sent.append(req)
        if req.method == "GET":
            if req.url.endswith("/order_123"):
                return result(200, json.dumps({
                    "id": "order_123", "entity": "order", "amount": 200,
                    "currency": "INR", "receipt": None,
                    "notes": {"retry_semantics_marker": arm["marker"]},
                }).encode())
            return result(200, b'{"entity":"collection","items":[]}')
        body = json.loads(req.body)
        return result(200, json.dumps({
            "id": "order_123", "entity": "order", "amount": body["amount"],
            "currency": body["currency"], "notes": body["notes"],
            "receipt": None,
        }).encode())

    projection, stopped = collect_razorpay_arm(
        manifest=manifest, family=family, arm=arm,
        evidence=evidence(tmp_path), send=sender, model=None,
        readiness_lock_sha256="c" * 64,
        writer_exclusion_audit_sha256="d" * 64,
        clock=lambda: now[0],
        wait_until=lambda target: now.__setitem__(0, target),
        wall_time=lambda: 1_800_000_000)
    assert len([x for x in sent if x.method == "POST"]) == 1
    assert projection.state_correct == 1
    assert stopped is False
    assert len([x for x in sent if x.method == "GET"]) == 4

    def contradicted(req):
        if req.url.endswith("/order_123"):
            return result(200, json.dumps({
                "id": "order_123", "entity": "order", "amount": 200,
                "currency": "INR", "receipt": None,
                "notes": {"retry_semantics_marker": "other-marker"},
            }).encode())
        return sender(req)

    now[0] = 100.0
    bad, _ = collect_razorpay_arm(
        manifest=manifest, family=family, arm=arm,
        evidence=evidence(tmp_path / "wrong"), send=contradicted, model=None,
        readiness_lock_sha256="c" * 64,
        writer_exclusion_audit_sha256="d" * 64,
        clock=lambda: now[0],
        wait_until=lambda target: now.__setitem__(0, target),
        wall_time=lambda: 1_800_000_000)
    assert bad.status == "INFRASTRUCTURE_FAILURE"
    assert bad.state_correct is None


def test_regeneration_model_uses_frozen_ambiguity_and_model_action(tmp_path):
    manifest = load_razorpay_paper_manifest()
    family = manifest["families"][0]
    calls = []

    def complete(payload):
        calls.append(payload)
        return (_completion("create_order", family["target_semantic_m"])
                if len(calls) == 1 else _completion("list_orders", {}))

    model = PaperModelSession(provider="razorpay", family=family,
                              common=manifest["model_visible_common"],
                              complete=complete, evidence=evidence(tmp_path))
    model.generate_original()
    model.begin_regeneration()
    action, args = model.next_action({
        "model_call_index": 0, "previous_tool_result": None,
        "seed": family["model_config"]["regeneration"]["seed"],
    })
    assert (action, args) == ("list_orders", {})
    assert calls[1]["messages"][-1]["content"] == manifest["model_visible_common"]["ambiguity_text"]
    assert calls[1]["seed"] == family["model_config"]["regeneration"]["seed"]
    saved = json.loads((tmp_path / "model-regeneration-0.json").read_bytes())
    assert saved["raw_response_hex"]


def test_model_history_preserves_multiple_tool_results_in_provider_order(tmp_path):
    manifest = load_razorpay_paper_manifest()
    family = manifest["families"][0]
    calls = []

    def complete(payload):
        calls.append(payload)
        if len(calls) == 1:
            return _completion("create_order", family["target_semantic_m"])
        if len(calls) == 2:
            return {"choices": [{"message": {"role": "assistant", "content": None,
                        "tool_calls": [
                            {"id": "read-id", "type": "function",
                             "function": {"name": "list_orders", "arguments": "{}"}},
                            {"id": "create-id", "type": "function",
                             "function": {"name": "create_order",
                                          "arguments": '{"amount":200,"currency":"INR"}'}},
                        ]}, "finish_reason": "tool_calls"}]}
        return _completion("finish", {})

    model = PaperModelSession(provider="razorpay", family=family,
                              common=manifest["model_visible_common"],
                              complete=complete, evidence=evidence(tmp_path))
    model.generate_original()
    model.begin_regeneration()
    first = model.next_actions({
        "model_call_index": 0, "previous_tool_result": None,
        "seed": family["model_config"]["regeneration"]["seed"],
    })
    assert first == (("list_orders", {}),
                     ("create_order", {"amount": 200, "currency": "INR"}))
    assert model.next_actions({
        "model_call_index": 1,
        "previous_tool_result": [{"orders": [], "list_traversal_complete": True},
                                 {"status": "created"}],
        "seed": family["model_config"]["regeneration"]["seed"] + 1,
    }) == ()
    assert [message["tool_call_id"] for message in calls[2]["messages"][-2:]] == [
        "read-id", "create-id"]


def test_github_run_stop_persists_every_unstarted_opportunity(tmp_path, monkeypatch):
    manifest = load_github_paper_manifest().as_json()
    identity = {"provider": "github", "manifest_sha256": "a" * 64,
                "runtime_sha256": {"runner.py": "b" * 64}}
    monkeypatch.setattr(collection, "check_readiness_lock", lambda *a, **k: identity)
    evidence_dir = tmp_path / "readiness"
    evidence_dir.mkdir()
    (tmp_path / "lock.json").write_bytes(b"{}")
    (evidence_dir / "repository_identity_and_full_baseline.json").write_text(
        json.dumps({"facts": {"api_version": "2022-11-28"}}))
    sends = []

    def sender(req):
        sends.append(req)
        return result(403, b"access blocked")

    monkeypatch.setattr(collection, "one_shot_http",
                        lambda req, credential: sender(req))
    monkeypatch.setattr(collection, "live_fireworks_completion",
                        lambda key: (lambda payload: _completion(
                            "create_issue", manifest["families"][0]["target_semantic_m"])))

    run_dir = tmp_path / "run"
    authorization = {
        "all_provider_readiness_lock_paths": {
            "github": tmp_path / "lock.json",
            "razorpay": tmp_path / "razorpay-lock.json",
            "sheets": tmp_path / "sheets-lock.json",
        },
        "collection_authorization_path": tmp_path / "authorization.json",
        "collection_audit_receipt_path": tmp_path / "authorization-receipt.json",
        "collection_audit_report_path": tmp_path / "authorization-report.json",
    }
    with pytest.raises(ProviderReadinessError):
        collect_provider_run(
            provider="github", run_dir=run_dir,
            lock_path=tmp_path / "lock.json", evidence_dir=evidence_dir,
            audit_receipt_path=tmp_path / "receipt.json",
            audit_report_path=tmp_path / "report.json",
            credential="offline-secret", model_api_key="offline-model",
            **authorization,
            api_version="2022-11-28")
    assert not run_dir.exists() and not sends
    monkeypatch.setattr(collection, "check_final_collection_authorization",
                        lambda **kwargs: "a" * 64)
    results = collect_provider_run(
        provider="github", run_dir=run_dir,
        lock_path=tmp_path / "lock.json", evidence_dir=evidence_dir,
        audit_receipt_path=tmp_path / "receipt.json",
        audit_report_path=tmp_path / "report.json",
        credential="offline-secret", model_api_key="offline-model",
        **authorization,
        api_version="2022-11-28")
    assert len(results) == 1
    assert results[0].status == "INCONCLUSIVE"
    assert len(sends) == 1
    assert sends[0].method == "GET"
    assert len(list(run_dir.glob("run-stopped-*.json"))) == 255
    with pytest.raises(PaperCollectionError, match="cannot resume"):
        collect_provider_run(
            provider="github", run_dir=run_dir,
            lock_path=tmp_path / "lock.json", evidence_dir=evidence_dir,
            audit_receipt_path=tmp_path / "receipt.json",
            audit_report_path=tmp_path / "report.json",
            credential="offline-secret", model_api_key="offline-model",
            **authorization,
            api_version="2022-11-28")


def test_static_identity_includes_collector_transport_model_and_readiness(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "load_github_paper_manifest",
                        lambda root: SimpleNamespace(
                            manifest_hash="a" * 64,
                            as_json=lambda: {"status": "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"},
                        ))
    for relative in readiness.RUNTIME_FILES["github"]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"frozen implementation")
    first = readiness.current_static_identity("github", root=tmp_path)
    for key in ("provider_paper_collection.py", "provider_paper_io.py",
                "provider_paper_model.py", "provider_paper_readiness.py"):
        assert any(path.endswith(key) for path in first["runtime_sha256"])
    changed = tmp_path / "src/retry_semantics/study2/provider_paper_collection.py"
    changed.write_bytes(b"changed collector")
    second = readiness.current_static_identity("github", root=tmp_path)
    assert second["runtime_sha256"] != first["runtime_sha256"]


def _valid_authorization_gate(tmp_path, now=None):
    if now is None:
        now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    instant_str = now.isoformat().replace("+00:00", "Z")

    gh_identity = {
        "provider": "github",
        "manifest_sha256": "1" * 64,
        "runtime_sha256": {"file.py": "2" * 64},
    }
    gh_lock = {
        "schema": "github-paper-readiness-lock-v1",
        "static_identity": gh_identity,
        "live_evidence_sha256": {c: "3" * 64 for c in readiness.PROVIDER_CONTROLS["github"]},
        "independent_audit_receipt_sha256": "4" * 64,
        "study2_paper_observations": 0,
        "collection_authorized": False,
    }
    gh_lock_path = tmp_path / "github-lock.json"
    gh_lock_path.write_bytes(canonical_json_bytes(gh_lock))

    rz_identity = {
        "provider": "razorpay",
        "manifest_sha256": "5" * 64,
        "runtime_sha256": {"file.py": "6" * 64},
    }
    rz_lock = {
        "schema": "razorpay-paper-readiness-lock-v1",
        "static_identity": rz_identity,
        "live_evidence_sha256": {c: "7" * 64 for c in readiness.PROVIDER_CONTROLS["razorpay"]},
        "independent_audit_receipt_sha256": "8" * 64,
        "study2_paper_observations": 0,
        "collection_authorized": False,
    }
    rz_lock_path = tmp_path / "razorpay-lock.json"
    rz_lock_path.write_bytes(canonical_json_bytes(rz_lock))

    _, sheets_manifest_hash = readiness._read_canonical(readiness.ROOT / readiness.SHEETS_MANIFEST_PATH)
    sheets_control_hashes = {"same_app_and_principal_access": "a" * 64, "writer_exclusion": "b" * 64}
    sheets_identity = {
        "manifest_sha256": sheets_manifest_hash,
        "control_sha256": sheets_control_hashes,
    }
    sheets_lock = {
        "schema": "sheets-paper-readiness-lock-v1",
        "receipt_sha256": "c" * 64,
        "independent_audit": {"auditor_id": "auditor-1", "audit_report_sha256": "d" * 64},
        "spreadsheet_id": "sheet_123",
        "manifest_sha256": sheets_manifest_hash,
        "topology_sha256": "e" * 64,
        "baseline_sha256": {"arm1": "f" * 64},
        "control_sha256": sheets_control_hashes,
    }
    sheets_lock_path = tmp_path / "sheets-lock.json"
    sheets_lock_path.write_bytes(canonical_json_bytes(sheets_lock))

    readiness_locks = {
        "github": gh_lock_path,
        "razorpay": rz_lock_path,
        "sheets": sheets_lock_path,
    }
    lock_hashes = {name: sha256_hex(p.read_bytes()) for name, p in readiness_locks.items()}

    authorization = {
        "schema": "study2-final-collection-authorization-v1",
        "status": "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED",
        "collection_authorized": True,
        "provider_readiness_lock_sha256": lock_hashes,
        "provider_static_identities": {
            "github": gh_identity,
            "razorpay": rz_identity,
            "sheets": sheets_identity,
        },
        "authorized_at_utc": instant_str,
        "study2_paper_observations_at_authorization": 0,
    }
    auth_bytes = canonical_json_bytes(authorization)
    auth_hash = sha256_hex(auth_bytes)
    auth_path = tmp_path / "final-authorization.json"
    auth_path.write_bytes(auth_bytes)

    report = {
        "schema": "study2-final-authorization-audit-report-v1",
        "authorization_sha256": auth_hash,
        "independent_auditor": "external-auditor-1",
        "result": "PASS",
        "findings": [],
    }
    report_bytes = canonical_json_bytes(report)
    report_hash = sha256_hex(report_bytes)
    report_path = tmp_path / "authorization-report.json"
    report_path.write_bytes(report_bytes)

    receipt = {
        "schema": "study2-final-authorization-audit-receipt-v1",
        "authorization_sha256": auth_hash,
        "audit_report_sha256": report_hash,
        "auditor_id": "external-auditor-1",
        "audited_at_utc": instant_str,
    }
    receipt_bytes = canonical_json_bytes(receipt)
    receipt_path = tmp_path / "authorization-receipt.json"
    receipt_path.write_bytes(receipt_bytes)

    return {
        "gh_identity": gh_identity,
        "rz_identity": rz_identity,
        "sheets_manifest_hash": sheets_manifest_hash,
        "readiness_locks": readiness_locks,
        "lock_hashes": lock_hashes,
        "authorization": authorization,
        "auth_path": auth_path,
        "receipt": receipt,
        "receipt_path": receipt_path,
        "report": report,
        "report_path": report_path,
        "now": now,
        "auth_hash": auth_hash,
    }


def test_final_collection_authorization_binds_all_providers_and_audits(tmp_path, monkeypatch):
    gate = _valid_authorization_gate(tmp_path)
    monkeypatch.setattr(readiness, "_require_committed", lambda root, paths: None)
    monkeypatch.setattr(readiness, "current_static_identity",
                        lambda p, root=None: gate["gh_identity"] if p == "github" else gate["rz_identity"])

    for prov, ident in (("github", gate["gh_identity"]), ("razorpay", gate["rz_identity"])):
        auth_hash = readiness.check_final_collection_authorization(
            provider=prov,
            provider_identity=ident,
            readiness_lock_paths=gate["readiness_locks"],
            authorization_path=gate["auth_path"],
            audit_receipt_path=gate["receipt_path"],
            audit_report_path=gate["report_path"],
            root=readiness.ROOT,
            now=gate["now"],
        )
        assert auth_hash == gate["auth_hash"]


def test_final_collection_authorization_rejects_missing_or_incomplete_provider_gates(tmp_path, monkeypatch):
    gate = _valid_authorization_gate(tmp_path)
    monkeypatch.setattr(readiness, "_require_committed", lambda root, paths: None)
    monkeypatch.setattr(readiness, "current_static_identity",
                        lambda p, root=None: gate["gh_identity"] if p == "github" else gate["rz_identity"])

    # Missing provider lock in mapping
    for missing_name in ("sheets", "github", "razorpay"):
        incomplete_locks = {k: v for k, v in gate["readiness_locks"].items() if k != missing_name}
        with pytest.raises(ProviderReadinessError, match="all provider readiness locks are required"):
            readiness.check_final_collection_authorization(
                provider="github",
                provider_identity=gate["gh_identity"],
                readiness_lock_paths=incomplete_locks,
                authorization_path=gate["auth_path"],
                audit_receipt_path=gate["receipt_path"],
                audit_report_path=gate["report_path"],
                root=readiness.ROOT,
                now=gate["now"],
            )

    # Unknown provider
    with pytest.raises(ProviderReadinessError, match="all provider readiness locks are required"):
        readiness.check_final_collection_authorization(
            provider="unknown_provider",
            provider_identity=gate["gh_identity"],
            readiness_lock_paths=gate["readiness_locks"],
            authorization_path=gate["auth_path"],
            audit_receipt_path=gate["receipt_path"],
            audit_report_path=gate["report_path"],
            root=readiness.ROOT,
            now=gate["now"],
        )

    # Lock tampered (hash in authorization differs from lock on disk)
    gate["readiness_locks"]["github"].write_bytes(b'{"tampered":true}')
    with pytest.raises(ProviderReadinessError):
        readiness.check_final_collection_authorization(
            provider="github",
            provider_identity=gate["gh_identity"],
            readiness_lock_paths=gate["readiness_locks"],
            authorization_path=gate["auth_path"],
            audit_receipt_path=gate["receipt_path"],
            audit_report_path=gate["report_path"],
            root=readiness.ROOT,
            now=gate["now"],
        )


def test_final_collection_authorization_rejects_identity_and_lock_state_mismatches(tmp_path, monkeypatch):
    gate = _valid_authorization_gate(tmp_path)
    monkeypatch.setattr(readiness, "_require_committed", lambda root, paths: None)
    monkeypatch.setattr(readiness, "current_static_identity",
                        lambda p, root=None: gate["gh_identity"] if p == "github" else gate["rz_identity"])

    # Caller identity differs from authorization
    wrong_caller_identity = dict(gate["gh_identity"], manifest_sha256="0" * 64)
    with pytest.raises(ProviderReadinessError, match="final collection authorization missing or stale"):
        readiness.check_final_collection_authorization(
            provider="github",
            provider_identity=wrong_caller_identity,
            readiness_lock_paths=gate["readiness_locks"],
            authorization_path=gate["auth_path"],
            audit_receipt_path=gate["receipt_path"],
            audit_report_path=gate["report_path"],
            root=readiness.ROOT,
            now=gate["now"],
        )

    # Provider lock has collection_authorized=True (must be False before collection)
    tampered_gh_lock = json.loads(gate["readiness_locks"]["github"].read_bytes())
    tampered_gh_lock["collection_authorized"] = True
    gate["readiness_locks"]["github"].write_bytes(canonical_json_bytes(tampered_gh_lock))
    auth = dict(gate["authorization"])
    auth["provider_readiness_lock_sha256"] = {
        name: sha256_hex(p.read_bytes()) for name, p in gate["readiness_locks"].items()
    }
    gate["auth_path"].write_bytes(canonical_json_bytes(auth))
    with pytest.raises(ProviderReadinessError, match="provider readiness lock identity differs"):
        readiness.check_final_collection_authorization(
            provider="github",
            provider_identity=gate["gh_identity"],
            readiness_lock_paths=gate["readiness_locks"],
            authorization_path=gate["auth_path"],
            audit_receipt_path=gate["receipt_path"],
            audit_report_path=gate["report_path"],
            root=readiness.ROOT,
            now=gate["now"],
        )


def test_final_collection_authorization_rejects_sheets_lock_tampering(tmp_path, monkeypatch):
    gate = _valid_authorization_gate(tmp_path)
    monkeypatch.setattr(readiness, "_require_committed", lambda root, paths: None)
    monkeypatch.setattr(readiness, "current_static_identity",
                        lambda p, root=None: gate["gh_identity"] if p == "github" else gate["rz_identity"])

    original_sheets = json.loads(gate["readiness_locks"]["sheets"].read_bytes())

    for hostile_patch in (
        {"schema": "wrong-sheets-schema"},
        {"manifest_sha256": "0" * 64},
        {"control_sha256": "not-a-dict"},
        {"control_sha256": {}},
        {"control_sha256": {"c1": "not-a-valid-hash"}},
        {"receipt_sha256": "not-a-valid-hash"},
    ):
        sheets_tampered = {**original_sheets, **hostile_patch}
        gate["readiness_locks"]["sheets"].write_bytes(canonical_json_bytes(sheets_tampered))
        auth = dict(gate["authorization"])
        auth["provider_readiness_lock_sha256"] = {
            name: sha256_hex(p.read_bytes()) for name, p in gate["readiness_locks"].items()
        }
        gate["auth_path"].write_bytes(canonical_json_bytes(auth))
        with pytest.raises(ProviderReadinessError, match="Sheets readiness lock identity differs"):
            readiness.check_final_collection_authorization(
                provider="github",
                provider_identity=gate["gh_identity"],
                readiness_lock_paths=gate["readiness_locks"],
                authorization_path=gate["auth_path"],
                audit_receipt_path=gate["receipt_path"],
                audit_report_path=gate["report_path"],
                root=readiness.ROOT,
                now=gate["now"],
            )


def test_final_collection_authorization_rejects_stale_or_unauthorized_state(tmp_path, monkeypatch):
    gate = _valid_authorization_gate(tmp_path)
    monkeypatch.setattr(readiness, "_require_committed", lambda root, paths: None)
    monkeypatch.setattr(readiness, "current_static_identity",
                        lambda p, root=None: gate["gh_identity"] if p == "github" else gate["rz_identity"])

    for field, bad_val in (
        ("collection_authorized", False),
        ("status", "NOT_FROZEN"),
        ("study2_paper_observations_at_authorization", 1),
        ("authorized_at_utc", "2026-09-27T00:00:00Z"),
    ):
        auth = {**gate["authorization"], field: bad_val}
        gate["auth_path"].write_bytes(canonical_json_bytes(auth))
        with pytest.raises(ProviderReadinessError, match="final collection authorization missing or stale"):
            readiness.check_final_collection_authorization(
                provider="github",
                provider_identity=gate["gh_identity"],
                readiness_lock_paths=gate["readiness_locks"],
                authorization_path=gate["auth_path"],
                audit_receipt_path=gate["receipt_path"],
                audit_report_path=gate["report_path"],
                root=readiness.ROOT,
                now=gate["now"],
            )


def test_final_collection_authorization_rejects_independent_audit_failures(tmp_path, monkeypatch):
    gate = _valid_authorization_gate(tmp_path)
    monkeypatch.setattr(readiness, "_require_committed", lambda root, paths: None)
    monkeypatch.setattr(readiness, "current_static_identity",
                        lambda p, root=None: gate["gh_identity"] if p == "github" else gate["rz_identity"])

    # 1. Receipt schema mismatch
    bad_receipt = {**gate["receipt"], "schema": "wrong-receipt-schema"}
    gate["receipt_path"].write_bytes(canonical_json_bytes(bad_receipt))
    with pytest.raises(ProviderReadinessError, match="independent final authorization receipt missing"):
        readiness.check_final_collection_authorization(
            provider="github",
            provider_identity=gate["gh_identity"],
            readiness_lock_paths=gate["readiness_locks"],
            authorization_path=gate["auth_path"],
            audit_receipt_path=gate["receipt_path"],
            audit_report_path=gate["report_path"],
            root=readiness.ROOT,
            now=gate["now"],
        )
    gate["receipt_path"].write_bytes(canonical_json_bytes(gate["receipt"]))

    # 2. Auditor mismatch between receipt and report
    bad_report = {**gate["report"], "independent_auditor": "other-auditor"}
    gate["report_path"].write_bytes(canonical_json_bytes(bad_report))
    receipt_sync = {**gate["receipt"], "audit_report_sha256": sha256_hex(gate["report_path"].read_bytes())}
    gate["receipt_path"].write_bytes(canonical_json_bytes(receipt_sync))
    with pytest.raises(ProviderReadinessError, match="independent final authorization audit not passing"):
        readiness.check_final_collection_authorization(
            provider="github",
            provider_identity=gate["gh_identity"],
            readiness_lock_paths=gate["readiness_locks"],
            authorization_path=gate["auth_path"],
            audit_receipt_path=gate["receipt_path"],
            audit_report_path=gate["report_path"],
            root=readiness.ROOT,
            now=gate["now"],
        )

    # 3. Report not passing (result != PASS or findings non-empty)
    for bad_report_field in ({"result": "FAIL"}, {"findings": ["breach"]}):
        bad_rep = {**gate["report"], **bad_report_field}
        gate["report_path"].write_bytes(canonical_json_bytes(bad_rep))
        receipt_sync = {**gate["receipt"], "audit_report_sha256": sha256_hex(gate["report_path"].read_bytes())}
        gate["receipt_path"].write_bytes(canonical_json_bytes(receipt_sync))
        with pytest.raises(ProviderReadinessError, match="independent final authorization audit not passing"):
            readiness.check_final_collection_authorization(
                provider="github",
                provider_identity=gate["gh_identity"],
                readiness_lock_paths=gate["readiness_locks"],
                authorization_path=gate["auth_path"],
                audit_receipt_path=gate["receipt_path"],
                audit_report_path=gate["report_path"],
                root=readiness.ROOT,
                now=gate["now"],
            )

    # 4. Receipt audited_at_utc after authorization authorized_at_utc
    future_audit_receipt = {**gate["receipt"], "audited_at_utc": "2026-09-26T13:00:00Z"}
    gate["receipt_path"].write_bytes(canonical_json_bytes(future_audit_receipt))
    gate["report_path"].write_bytes(canonical_json_bytes(gate["report"]))
    with pytest.raises(ProviderReadinessError, match="independent final authorization receipt missing"):
        readiness.check_final_collection_authorization(
            provider="github",
            provider_identity=gate["gh_identity"],
            readiness_lock_paths=gate["readiness_locks"],
            authorization_path=gate["auth_path"],
            audit_receipt_path=gate["receipt_path"],
            audit_report_path=gate["report_path"],
            root=readiness.ROOT,
            now=gate["now"],
        )


def test_final_collection_authorization_rejects_when_other_provider_runtime_identity_changes(tmp_path, monkeypatch):
    gate = _valid_authorization_gate(tmp_path)
    monkeypatch.setattr(readiness, "_require_committed", lambda root, paths: None)

    # State A: authorization has gate["gh_identity"] and gate["rz_identity"]
    # 1. When launching "github", Razorpay's current runtime identity becomes State B
    state_b_rz = dict(gate["rz_identity"], manifest_sha256="b" * 64)
    monkeypatch.setattr(readiness, "current_static_identity",
                        lambda p, root=None: gate["gh_identity"] if p == "github" else state_b_rz)

    with pytest.raises(ProviderReadinessError, match="current static identity of razorpay differs from authorization"):
        readiness.check_final_collection_authorization(
            provider="github",
            provider_identity=gate["gh_identity"],
            readiness_lock_paths=gate["readiness_locks"],
            authorization_path=gate["auth_path"],
            audit_receipt_path=gate["receipt_path"],
            audit_report_path=gate["report_path"],
            root=readiness.ROOT,
            now=gate["now"],
        )

    # 2. When launching "razorpay", GitHub's current runtime identity becomes State B
    state_b_gh = dict(gate["gh_identity"], manifest_sha256="b" * 64)
    monkeypatch.setattr(readiness, "current_static_identity",
                        lambda p, root=None: state_b_gh if p == "github" else gate["rz_identity"])

    with pytest.raises(ProviderReadinessError, match="current static identity of github differs from authorization"):
        readiness.check_final_collection_authorization(
            provider="razorpay",
            provider_identity=gate["rz_identity"],
            readiness_lock_paths=gate["readiness_locks"],
            authorization_path=gate["auth_path"],
            audit_receipt_path=gate["receipt_path"],
            audit_report_path=gate["report_path"],
            root=readiness.ROOT,
            now=gate["now"],
        )


def test_final_collection_authorization_requires_committed_checkout(tmp_path):
    gate = _valid_authorization_gate(tmp_path)
    with pytest.raises(ProviderReadinessError, match="readiness bytes are not committed"):
        readiness.check_final_collection_authorization(
            provider="github",
            provider_identity=gate["gh_identity"],
            readiness_lock_paths=gate["readiness_locks"],
            authorization_path=gate["auth_path"],
            audit_receipt_path=gate["receipt_path"],
            audit_report_path=gate["report_path"],
            root=tmp_path,
            now=gate["now"],
        )
