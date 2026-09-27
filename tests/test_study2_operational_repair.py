"""Hostile offline checks for the repaired Study-2 operational boundaries."""

from __future__ import annotations

import copy
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import provider_paper_collection as collection
from retry_semantics.study2 import provider_paper_readiness as readiness
from retry_semantics.study2.provider_paper_io import PaperRequest, PaperTransportResult
from retry_semantics.study2.provider_paper_collection import (
    PaperCollectionError, collect_provider_run, validate_run_directory,
)
from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest
from retry_semantics.study2.razorpay_live_readiness import capture_razorpay_readiness
from retry_semantics.study2.razorpay_paper_manifest import (
    load_razorpay_paper_manifest, load_namespace_registry as load_razorpay_registry,
)
from scripts import prepare_study2_final_collection_authorization as authorization


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("offline repair test attempted network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def test_run_directory_containment_and_resume(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "research").mkdir()
    for target in (repository / "foo", repository / "research" / "foo"):
        with pytest.raises(PaperCollectionError, match="outside repository"):
            validate_run_directory(target, root=repository)
    external = tmp_path / "new-run"
    assert validate_run_directory(external, root=repository) == external
    external.mkdir()
    with pytest.raises(PaperCollectionError, match="cannot resume"):
        validate_run_directory(external, root=repository)
    alias = tmp_path / "alias"
    alias.symlink_to(repository, target_is_directory=True)
    with pytest.raises(PaperCollectionError, match="outside repository"):
        validate_run_directory(alias / "escaped", root=repository)


def test_sheets_static_identity_is_lock_independent_and_fails_closed(tmp_path, monkeypatch):
    manifest = {"status": "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED",
                "study2_paper_observations": 0}
    path = tmp_path / readiness.SHEETS_MANIFEST_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(canonical_json_bytes(manifest))
    runtime = "src/runtime.py"
    (tmp_path / "src").mkdir()
    (tmp_path / runtime).write_bytes(b"runtime")
    monkeypatch.setitem(readiness.RUNTIME_FILES, "sheets", (runtime,))
    monkeypatch.setattr(readiness, "load_sheets_paper_manifest", lambda *, root: manifest)
    first = readiness.current_static_identity("sheets", root=tmp_path)
    assert first["runtime_sha256"] == {runtime: sha256_hex(b"runtime")}
    (path.parent / "GOOGLE_SHEETS_PAPER_READINESS_LOCK_V1.json").write_bytes(b"not-json")
    assert readiness.current_static_identity("sheets", root=tmp_path) == first
    monkeypatch.setattr(readiness, "load_sheets_paper_manifest",
                        lambda *, root: (_ for _ in ()).throw(ValueError("stale")))
    with pytest.raises(readiness.ProviderReadinessError, match="cannot be regenerated"):
        readiness.current_static_identity("sheets", root=tmp_path)


def test_razorpay_readiness_inspects_page_two(tmp_path):
    manifest = load_razorpay_paper_manifest()
    registry = load_razorpay_registry()
    identity = {"provider": "razorpay", "manifest_sha256": "a" * 64,
                "runtime_sha256": {}}
    fetched: list[str] = []

    def order(index: int) -> dict:
        return {"id": f"order_qual{index}", "entity": "order", "amount": 200,
                "currency": "INR", "notes": {}}

    def send(request: PaperRequest) -> PaperTransportResult:
        if "order_TfBuv3iQHQrz9p" in request.url:
            body = {"id": "order_TfBuv3iQHQrz9p", "entity": "order",
                    "amount": 200, "currency": "INR",
                    "notes": {"retry_semantics_marker":
                              "study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215"}}
        elif request.method == "POST":
            sent = json.loads(request.body)
            body = {"id": "order_qualcreate", "entity": "order",
                    "amount": sent["amount"], "currency": sent["currency"],
                    "notes": sent["notes"]}
        else:
            fetched.append(request.url)
            items = [order(i) for i in range(100)] if "skip=0" in request.url else [order(100)]
            body = {"entity": "collection", "items": items}
        return _response(200, canonical_json_bytes(body))

    def model(_name, tools, _sampling):
        return {"choices": [{"message": {"role": "assistant", "content": None,
                "tool_calls": [{"id": "call-1", "type": "function",
                                "function": {"name": tools[0]["name"],
                                             "arguments": "{}"}}]},
                "finish_reason": "tool_calls"}]}

    capture_razorpay_readiness(
        manifest=manifest, registry=registry, evidence_dir=tmp_path / "evidence",
        identity=identity, operator_id="offline-operator", http_send=send,
        model_complete=model)
    assert len(fetched) == 2
    assert "skip=0" in fetched[0] and "skip=100" in fetched[1]
    facts = json.loads((tmp_path / "evidence" /
                        "bounded_fetch_all_capture.json").read_bytes())["facts"]
    assert len(facts["pages"]) == 2
    assert facts["authoritative_completeness_qualified"] is False


def _response(status: int, body: bytes) -> PaperTransportResult:
    instant = time.monotonic()
    return PaperTransportResult(status, (), body, None, True, True, True,
                                instant, instant + 0.001)


def _grid(manifest: dict, arm: dict, *, entered: bool) -> bytes:
    rows = []
    if entered:
        semantic = manifest["families"][0]["target_semantic_m"]
        rows = [{"values": [{"userEnteredValue": {"stringValue": value}}
                           for value in (arm["arm_marker"], semantic["item"],
                                         semantic["detail"])]}]
    return canonical_json_bytes({
        "spreadsheetId": manifest["spreadsheet_id"],
        "sheets": [{"properties": {
            "sheetId": arm["sheet_id"], "title": arm["tab_title"],
            "sheetType": "GRID", "gridProperties": {"rowCount": 100, "columnCount": 3}},
            "data": [{"rowData": rows}]}],
    })


def _mock_sheets_run(monkeypatch, *, arm_count: int):
    manifest = copy.deepcopy(load_paper_manifest())
    family = manifest["families"][0]
    replay = next(arm for arm in family["arms"]
                  if arm["hidden_world"] == "H0" and arm["policy"] == "EXACT_REPLAY")
    other = next(arm for arm in family["arms"] if arm is not replay)
    family["arms"] = [replay] + ([other] if arm_count == 2 else [])
    manifest["families"] = [family]
    identity = {"provider": "sheets", "manifest_sha256": "a" * 64,
                "runtime_sha256": {"runner.py": "b" * 64}}
    monkeypatch.setattr(collection, "load_sheets_paper_manifest", lambda: manifest)
    monkeypatch.setattr(collection, "check_readiness_lock", lambda *a, **kw: identity)
    monkeypatch.setattr(collection, "check_final_collection_authorization",
                        lambda **kw: "c" * 64)
    monkeypatch.setattr(collection, "_check_sheets_token_lifetime",
                        lambda *a, **kw: time.time() + 3600)

    def completion(_key):
        def call(_payload):
            return {"choices": [{"message": {"role": "assistant", "content": None,
                     "tool_calls": [{"id": "call-1", "type": "function",
                       "function": {"name": "append_row",
                                    "arguments": json.dumps(family["target_semantic_m"])}}]},
                     "finish_reason": "tool_calls"}]}
        return call
    monkeypatch.setattr(collection, "live_fireworks_completion", completion)
    return manifest, replay


@pytest.mark.parametrize("post_status", [200, 401, 403, 429])
def test_sheets_real_run_path_offline_and_run_stop(tmp_path, monkeypatch, post_status):
    manifest, arm = _mock_sheets_run(monkeypatch, arm_count=2)
    calls: list[PaperRequest] = []
    posted = False

    def send(request: PaperRequest, *, credential: str):
        nonlocal posted
        calls.append(request)
        assert credential == "fake-bearer"
        if request.method == "POST":
            posted = True
            return _response(post_status, canonical_json_bytes({
                "spreadsheetId": manifest["spreadsheet_id"], "replies": [{}]}))
        return _response(200, _grid(manifest, arm, entered=posted and post_status == 200))

    monkeypatch.setattr(collection, "one_shot_http", send)
    lock = tmp_path / "lock.json"
    lock.write_bytes(b"{}")
    run_dir = tmp_path / "run"
    kwargs = dict(
        provider="sheets", run_dir=run_dir, lock_path=lock,
        evidence_dir=tmp_path, audit_receipt_path=lock, audit_report_path=lock,
        credential="fake-bearer", model_api_key="fake-model",
        all_provider_readiness_lock_paths={"sheets": lock},
        collection_authorization_path=lock,
        collection_audit_receipt_path=lock,
        collection_audit_report_path=lock,
    )
    results = collect_provider_run(**kwargs)
    assert (run_dir / "run-authorization.json").is_file()
    assert len(results) >= 1
    assert calls[0].method == "GET"
    assert calls[1].method == "POST"
    first_arm = next(path for path in run_dir.iterdir()
                     if path.is_dir() and path.name.startswith("000-"))
    assert (first_arm / "stored-original.json").is_file()
    assert (first_arm / "sheets-observation-anchor.json").is_file() == (post_status == 200)
    if post_status == 200:
        assert results[0].status == "SUCCESS"
        assert len(calls) > 2
    else:
        assert len(results) == 1
        assert results[0].status == "INCONCLUSIVE"
        assert len(calls) == 2
        assert len(list(run_dir.glob("run-stopped-*.json"))) == 1
    with pytest.raises(PaperCollectionError, match="cannot resume"):
        collect_provider_run(**kwargs)


@pytest.mark.parametrize("stop_at", ["baseline", "observation"])
def test_sheets_401_stops_before_next_arm(tmp_path, monkeypatch, stop_at):
    manifest, arm = _mock_sheets_run(monkeypatch, arm_count=2)
    calls: list[PaperRequest] = []

    def send(request: PaperRequest, *, credential: str):
        calls.append(request)
        if stop_at == "baseline" or (stop_at == "observation" and len(calls) == 3):
            return _response(401, b"unauthorized")
        if request.method == "POST":
            return _response(200, canonical_json_bytes({
                "spreadsheetId": manifest["spreadsheet_id"], "replies": [{}]}))
        return _response(200, _grid(manifest, arm, entered=len(calls) > 2))

    monkeypatch.setattr(collection, "one_shot_http", send)
    lock = tmp_path / "lock.json"
    lock.write_bytes(b"{}")
    run_dir = tmp_path / "run"
    results = collect_provider_run(
        provider="sheets", run_dir=run_dir, lock_path=lock,
        evidence_dir=tmp_path, audit_receipt_path=lock, audit_report_path=lock,
        credential="fake-bearer", model_api_key="fake-model",
        all_provider_readiness_lock_paths={"sheets": lock},
        collection_authorization_path=lock,
        collection_audit_receipt_path=lock,
        collection_audit_report_path=lock)
    assert len(results) == 1 and results[0].status == "INCONCLUSIVE"
    assert len(calls) == (1 if stop_at == "baseline" else 3)
    assert len(list(run_dir.glob("run-stopped-*.json"))) == 1


def test_sheets_token_preflight_binds_bearer_and_prospective_plan(tmp_path):
    now = 1_000_000.0
    record = {"qualified": True, "facts": {
        "token_expiry": {"expires_at": now + 3600,
                         "clock_uncertainty_seconds": 1,
                         "bearer_sha256": sha256_hex(b"bound-bearer")},
        "planned_run_end": {"epoch_seconds": now + 1800}}}
    path = tmp_path / "token_lifetime.json"
    path.write_bytes(canonical_json_bytes(record))
    collection._check_sheets_token_lifetime(tmp_path, credential="bound-bearer",
                                             now=now, arm_count=256)
    with pytest.raises(PaperCollectionError, match="token lifetime"):
        collection._check_sheets_token_lifetime(tmp_path, credential="other-bearer",
                                                 now=now, arm_count=256)
    record["facts"]["planned_run_end"]["epoch_seconds"] = now + 3600
    path.write_bytes(canonical_json_bytes(record))
    with pytest.raises(PaperCollectionError, match="token lifetime"):
        collection._check_sheets_token_lifetime(tmp_path, credential="bound-bearer",
                                                 now=now, arm_count=256)


def test_sheets_run_stops_before_dispatch_when_plan_is_exhausted(tmp_path, monkeypatch):
    _mock_sheets_run(monkeypatch, arm_count=2)
    monkeypatch.setattr(collection, "_check_sheets_token_lifetime",
                        lambda *a, **kw: time.time() + 39)
    monkeypatch.setattr(collection, "one_shot_http",
                        lambda *_a, **_kw: pytest.fail("provider dispatch after plan"))
    lock = tmp_path / "lock.json"
    lock.write_bytes(b"{}")
    with pytest.raises(PaperCollectionError, match="plan exhausted"):
        collect_provider_run(
            provider="sheets", run_dir=tmp_path / "run", lock_path=lock,
            evidence_dir=tmp_path, audit_receipt_path=lock, audit_report_path=lock,
            credential="fake-bearer", model_api_key="fake-model",
            all_provider_readiness_lock_paths={"sheets": lock},
            collection_authorization_path=lock,
            collection_audit_receipt_path=lock,
            collection_audit_report_path=lock)


def test_final_intent_requires_exact_independent_audit(tmp_path, monkeypatch):
    identities = {name: {"provider": name, "manifest_sha256": "a" * 64,
                         "runtime_sha256": {}}
                  for name in ("github", "razorpay", "sheets")}
    locks = {}
    for name in identities:
        stem = "GOOGLE_SHEETS" if name == "sheets" else name.upper()
        path = tmp_path / "research" / "study2" / name / f"{stem}_PAPER_READINESS_LOCK_V1.json"
        path.parent.mkdir(parents=True)
        path.write_bytes(canonical_json_bytes({"name": name}))
        locks[name] = path
    monkeypatch.setattr(authorization, "check_readiness_lock",
                        lambda name, *args, **kwargs: identities[name])
    authorized_at = "2026-09-28T00:00:00Z"
    candidate = {
        "schema": "study2-final-collection-authorization-v1",
        "status": "PENDING_INDEPENDENT_AUDIT", "collection_authorized": False,
        "provider_readiness_lock_sha256": {name: sha256_hex(path.read_bytes())
                                           for name, path in locks.items()},
        "provider_static_identities": identities,
        "authorized_at_utc": authorized_at,
        "study2_paper_observations_at_authorization": 0,
    }
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_bytes(canonical_json_bytes(candidate))
    final_sha = sha256_hex(authorization.final_intent_bytes(candidate))
    report = {"schema": "study2-final-authorization-audit-report-v1",
              "authorization_sha256": final_sha, "independent_auditor": "auditor",
              "result": "PASS", "findings": []}
    report_path = tmp_path / "report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    receipt = {"schema": "study2-final-authorization-audit-receipt-v1",
               "authorization_sha256": final_sha,
               "audit_report_sha256": sha256_hex(report_path.read_bytes()),
               "auditor_id": "auditor", "audited_at_utc": "2026-09-27T00:00:00Z"}
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    output_path = tmp_path / "final.json"
    assert authorization.finalize_final_authorization(
        candidate_path=candidate_path, audit_receipt_path=receipt_path,
        audit_report_path=report_path, output_path=output_path, root=tmp_path,
        now=datetime(2026, 9, 28, 1, tzinfo=timezone.utc)) == final_sha
    assert sha256_hex(output_path.read_bytes()) == final_sha
    output_path.unlink()
    report["result"] = "FAIL"
    report_path.write_bytes(canonical_json_bytes(report))
    with pytest.raises(readiness.ProviderReadinessError):
        authorization.finalize_final_authorization(
            candidate_path=candidate_path, audit_receipt_path=receipt_path,
            audit_report_path=report_path, output_path=output_path, root=tmp_path,
            now=datetime(2026, 9, 28, 1, tzinfo=timezone.utc))
    assert not output_path.exists()
