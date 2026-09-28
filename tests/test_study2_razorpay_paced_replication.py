"""Offline portability, evidence preservation and complete paced collection tests."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import socket

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import razorpay_paced_replication as replication
from retry_semantics.study2 import provider_operator_launch as base
from retry_semantics.study2 import provider_paper_collection as collection
from retry_semantics.study2.provider_paper_io import PaperRequest, PaperTransportResult
from retry_semantics.study2.provider_paper_readiness_controls import HISTORICAL_TEST_MARKER, HISTORICAL_TEST_ORDER_ID
from test_study2_provider_operator_launch import API


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a, **kw):
        raise AssertionError("unexpected network")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


@pytest.fixture
def stopped(tmp_path):
    directory = tmp_path / "original"
    directory.mkdir()
    base.write_once(directory / "manifest.json", base.manifest_for("razorpay"))
    base.write_once(directory / "summary.json", {
        "provider": "razorpay", "state": "STOPPED", "dataset_role": base.ROLE,
        "scheduled_arms": 256, "evaluated_arms": 2})
    base.write_once(directory / "00001.result.json", {"http_status": 429})
    base.write_once(directory / "inventory.json", base.inventory(directory))
    return directory


def test_replication_changes_only_declared_manifest_fields():
    original = base.manifest_for("razorpay")
    manifest, registry = replication.inputs("a" * 32)
    allowed = {"status", "audit_provenance", "run_namespace", "collection_status", "dataset_role",
               "independent_audit_claimed", "families", "manifest_id", "registry_semantic_sha256",
               "provider_request_gap_seconds", "source_manifest_sha256"}
    assert {k: v for k, v in manifest.items() if k not in allowed} == {
        k: v for k, v in original.items() if k not in allowed}
    for before, after in zip(original["families"], manifest["families"], strict=True):
        after = copy.deepcopy(after)
        for arm, old in zip(after["arms"], before["arms"], strict=True):
            assert arm["marker"] != old["marker"]
            body = bytes.fromhex(arm["provider_request_body_hex"])
            assert sha256_hex(body) == arm["provider_request_body_sha256"]
            assert json.loads(body) == {"amount": 200, "currency": "INR",
                                       "notes": {"retry_semantics_marker": arm["marker"]}}
            for key in ("marker", "provider_request_body_hex", "provider_request_body_sha256"):
                arm[key] = old[key]
        assert after == before
    assert len({r["arm_marker"] for r in registry["reservations"]}) == 256
    assert "audit_provenance" not in manifest and "audit_provenance" not in registry
    with pytest.raises(base.PaperCollectionError, match="fresh"):
        replication.inputs(original["run_namespace"])


def test_plan_binds_host_and_stopped_evidence(tmp_path, monkeypatch, stopped):
    monkeypatch.setattr(base, "git_head", lambda: "a" * 40)
    path = tmp_path / "plan.json"
    base.write_once(path, replication.build_plan("a" * 32, "operator", stopped))
    assert replication.check_plan(path)["provider_request_gap_seconds"] == 3
    original_host = base.host_identity
    monkeypatch.setattr(base, "host_identity", lambda: "wrong")
    with pytest.raises(base.PaperCollectionError, match="differs"):
        replication.check_plan(path)
    monkeypatch.setattr(base, "host_identity", original_host)
    (stopped / "00001.result.json").write_text("{}")
    with pytest.raises(base.PaperCollectionError, match="changed"):
        replication.check_plan(path)


def test_transport_spaces_reads_and_writes_and_never_retries():
    now, calls, sleeps = [0.0], [], []
    def send(req, **kw):
        calls.append(now[0])
        now[0] += 1  # Gap must be after completion, not just dispatch.
        return PaperTransportResult(429, (), b"{}", None, True, True, True, now[0]-1, now[0])
    def sleep(delay):
        sleeps.append(delay)
        now[0] += min(delay, 1.0)  # Early wake must not shorten the gap.
    transport = replication.PacedTransport("fake", send=send, clock=lambda: now[0], sleep=sleep)
    for method in ("GET", "POST", "GET"):
        assert transport(PaperRequest(method, "https://api.razorpay.com/v1/orders", (), b"")).status == 429
    assert calls == [0.0, 4.0, 8.0]
    assert len(sleeps) == 6


@pytest.mark.parametrize("stop", [False, True])
def test_full_paced_readiness_and_schedule(tmp_path, monkeypatch, stopped, stop):
    manifest, _ = replication.inputs("a" * 32)
    api = API("razorpay", manifest)
    monkeypatch.setattr(base, "git_head", lambda: "a" * 40)
    monkeypatch.setattr(base, "claim_path", lambda p: tmp_path / "claims" / f"{p}.json")
    monkeypatch.setattr(base, "credentials", lambda p: ("fake", "fake"))
    monkeypatch.setattr(collection.time, "monotonic", lambda: api.now)
    monkeypatch.setattr(collection.time, "time", lambda: api.now)
    monkeypatch.setattr(collection.time, "sleep", lambda delay: setattr(api, "now", api.now+delay))
    monkeypatch.setattr(collection, "live_fireworks_completion", lambda key: api.complete)
    monkeypatch.setattr(base, "live_fireworks_completion", lambda key: api.complete)
    calls, stopped_at = [], []
    def send(req, **kw):
        assert not stopped_at, "sent another provider request after 429"
        if calls:
            assert api.now - calls[-1] >= 3
        calls.append(api.now)
        if stop and len(api.posts) >= 2:  # Qualification plus H1 original, then stop.
            stopped_at.append(api.now)
            return PaperTransportResult(429, (("Retry-After", "2"),), b"{}", None,
                                        True, True, True, api.now, api.now)
        if req.url.endswith("/" + HISTORICAL_TEST_ORDER_ID):
            return PaperTransportResult(200, (), canonical_json_bytes({
                "id": HISTORICAL_TEST_ORDER_ID, "entity": "order",
                "notes": {"retry_semantics_marker": HISTORICAL_TEST_MARKER}}),
                None, True, True, True, api.now, api.now)
        return api.send(req)
    monkeypatch.setattr(base, "one_shot_http", send)
    real_capture = base.capture_razorpay_readiness
    monkeypatch.setattr(base, "capture_razorpay_readiness", lambda **kw: real_capture(
        **kw, monotonic_fn=lambda: api.now,
        now_fn=lambda: datetime.fromtimestamp(api.now, timezone.utc)))
    base.claim_path("razorpay").parent.mkdir()
    base.write_once(base.claim_path("razorpay"), {"state": "ORIGINAL_REMAINS_CONSUMED"})
    original_claim = base.claim_path("razorpay").read_bytes()
    original_inventory = base.inventory(stopped)
    plan = tmp_path / "plan.json"
    base.write_once(plan, replication.build_plan("a" * 32, "offline-operator", stopped))
    summary = replication.run(plan, confirm_no_external_writers=True,
                              confirm_separate_replication=True, progress=lambda *a, **kw: None)
    assert base.inventory(stopped) == original_inventory
    assert base.claim_path("razorpay").read_bytes() == original_claim
    if stop:
        assert summary["state"] == "STOPPED" and summary["evaluated_arms"] < 256, summary
        assert "provider_run_stop" in summary["failure_reason"]
        assert stopped_at
        with pytest.raises(base.PaperCollectionError, match="stopped"):
            replication.verify(tmp_path / "razorpay-run")
    else:
        assert summary["state"] == "COMPLETED", summary
        assert summary["verdicts"] == {"SUCCESS": 192, "FAILURE": 64}
        assert len(api.posts) == 321 and api.model_originals == 64
        assert replication.verify(tmp_path / "razorpay-run") == summary
        assert api.now - 1_800_000_000 > 128*370 + 64*200
    with pytest.raises(base.PaperCollectionError, match="consumed"):
        replication.run(plan, confirm_no_external_writers=True, confirm_separate_replication=True)
    with pytest.raises(base.PaperCollectionError, match="consumed"):
        base.require_unconsumed(tmp_path / "different-plan.json", replication.CLAIM)
