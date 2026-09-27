"""Hostile offline checks for the post-observation continuation boundary."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import socket
import sys

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import post_sheets_continuation as continuation
from retry_semantics.study2 import provider_paper_readiness as readiness
from retry_semantics.study2.provider_paper_collection import (
    PaperCollectionError, collect_provider_run,
)
from scripts import run_study2_sheets_primary
from scripts import prepare_study2_post_sheets_continuation as preparation

NOW = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
STAMP = "2026-09-28T11:00:00Z"


def _write(path: Path, doc: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_json_bytes(doc)
    path.write_bytes(raw)
    return sha256_hex(raw)


def _gate(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: pytest.fail("network call"))
    monkeypatch.setattr(continuation, "_require_committed", lambda *_a, **_k: None)
    monkeypatch.setattr(continuation, "_fix_commit_collector_sha",
                        lambda *_a, **_k: continuation.COLLECTOR_SHA256)
    monkeypatch.setattr(readiness, "_require_committed", lambda *_a, **_k: None)
    repository = readiness.ROOT
    amendment, _ = readiness._read_canonical(repository / continuation.AMENDMENT)
    _write(tmp_path / continuation.AMENDMENT, amendment)
    (tmp_path / continuation.BASE_AUTHORIZATION).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / continuation.BASE_AUTHORIZATION).write_bytes(
        (repository / continuation.BASE_AUTHORIZATION).read_bytes())
    amendment_sha = sha256_hex((tmp_path / continuation.AMENDMENT).read_bytes())
    report = {"schema": "study2-post-sheets-incident-audit-report-v1",
              "amendment_sha256": amendment_sha, "independent_auditor": "offline-fixture",
              "result": "PASS", "findings": []}
    report_sha = _write(tmp_path / continuation.AMENDMENT_REPORT, report)
    _write(tmp_path / continuation.AMENDMENT_RECEIPT, {
        "schema": "study2-post-sheets-incident-audit-receipt-v1",
        "amendment_sha256": amendment_sha, "audit_report_sha256": report_sha,
        "auditor_id": "offline-fixture", "audited_at_utc": STAMP})
    identities = {name: {"provider": name, "manifest_sha256": "a" * 64,
                         "runtime_sha256": {continuation.COLLECTOR:
                                            sha256_hex((repository / continuation.COLLECTOR).read_bytes())}}
                  for name in continuation.PROVIDERS}
    locks = {}
    for name in continuation.PROVIDERS:
        path = tmp_path / f"{name}-lock.json"
        _write(path, {"schema": f"{name}-paper-readiness-lock-v1",
                      "static_identity": identities[name],
                      "study2_paper_observations": 0,
                      "collection_authorized": False})
        locks[name] = path
    monkeypatch.setattr(continuation, "current_static_identity",
                        lambda name, root=None: identities[name])
    monkeypatch.setattr(continuation, "check_readiness_lock",
                        lambda name, *_a, **_k: identities[name])
    candidate = {
        "schema": "study2-post-sheets-continuation-authorization-v1",
        "status": "PENDING_INDEPENDENT_AUDIT", "collection_authorized": False,
        "authorized_providers": ["github", "razorpay"],
        "sheets_primary_status": "CLOSED_IMPLEMENTATION_INVALIDATED",
        "incident_amendment_sha256": amendment_sha,
        "base_preincident_authorization_sha256": continuation.BASE_SHA256,
        "defect_fix_collector_sha256": continuation.COLLECTOR_SHA256,
        "provider_readiness_lock_sha256": {
            name: sha256_hex(path.read_bytes()) for name, path in locks.items()},
        "provider_static_identities": identities,
        "authorized_at_utc": STAMP,
    }
    final = dict(candidate, status="FROZEN_INDEPENDENT_AUDIT_PASSED",
                 collection_authorized=True)
    auth_path = tmp_path / continuation.AUTHORIZATION
    auth_sha = _write(auth_path, final)
    report_path = tmp_path / "authorization-report.json"
    report_sha = _write(report_path, {
        "schema": "study2-post-sheets-continuation-audit-report-v1",
        "authorization_sha256": auth_sha, "independent_auditor": "offline-fixture",
        "result": "PASS", "findings": []})
    receipt_path = tmp_path / "authorization-receipt.json"
    _write(receipt_path, {
        "schema": "study2-post-sheets-continuation-audit-receipt-v1",
        "authorization_sha256": auth_sha, "audit_report_sha256": report_sha,
        "auditor_id": "offline-fixture", "audited_at_utc": STAMP})
    return {"root": tmp_path, "identities": identities, "locks": locks,
            "auth": auth_path, "receipt": receipt_path, "report": report_path,
            "auth_sha": auth_sha}


def _check(gate, provider, *, now=NOW):
    return continuation.check_continuation_authorization(
        provider=provider, provider_identity=gate["identities"].get(provider, {}),
        readiness_lock_paths=gate["locks"], authorization_path=gate["auth"],
        audit_receipt_path=gate["receipt"], audit_report_path=gate["report"],
        root=gate["root"], now=now)


def _rebind_auth_audit(gate, auth):
    auth_sha = _write(gate["auth"], auth)
    report, _ = readiness._read_canonical(gate["report"])
    report["authorization_sha256"] = auth_sha
    report_sha = _write(gate["report"], report)
    receipt, _ = readiness._read_canonical(gate["receipt"])
    receipt["authorization_sha256"] = auth_sha
    receipt["audit_report_sha256"] = report_sha
    _write(gate["receipt"], receipt)


@pytest.mark.parametrize("provider", ["github", "razorpay"])
def test_only_exact_audited_provider_binding_passes(tmp_path, monkeypatch, provider):
    gate = _gate(tmp_path, monkeypatch)
    assert _check(gate, provider) == gate["auth_sha"]
    altered = deepcopy(gate["identities"][provider])
    altered["manifest_sha256"] = "0" * 64
    gate["identities"][provider] = altered
    with pytest.raises(readiness.ProviderReadinessError):
        _check(gate, provider)


def test_sheets_rejected_before_evidence_or_network(tmp_path, monkeypatch):
    gate = _gate(tmp_path, monkeypatch)
    with pytest.raises(readiness.ProviderReadinessError, match="permanently closed"):
        _check(gate, "sheets")
    def forbidden(*_args, **_kwargs):
        pytest.fail("Sheets primary reached readiness, model, provider, or run directory")
    monkeypatch.setattr("retry_semantics.study2.provider_paper_collection.check_readiness_lock", forbidden)
    monkeypatch.setattr("retry_semantics.study2.provider_paper_collection.validate_run_directory", forbidden)
    monkeypatch.setattr("retry_semantics.study2.provider_paper_collection.one_shot_http", forbidden)
    monkeypatch.setattr("retry_semantics.study2.provider_paper_collection.live_fireworks_completion", forbidden)
    for authorization in (gate["auth"],
                          readiness.ROOT / continuation.BASE_AUTHORIZATION,
                          tmp_path / "arbitrary-name.json"):
        with pytest.raises(PaperCollectionError, match="permanently closed"):
            collect_provider_run(
                provider="sheets", run_dir=tmp_path / "unused-run",
                lock_path=tmp_path / "unused-lock", evidence_dir=tmp_path,
                audit_receipt_path=tmp_path / "unused-receipt",
                audit_report_path=tmp_path / "unused-report", credential="offline",
                model_api_key="offline", all_provider_readiness_lock_paths=gate["locks"],
                collection_authorization_path=authorization,
                collection_audit_receipt_path=gate["receipt"],
                collection_audit_report_path=gate["report"])
    assert not (tmp_path / "unused-run").exists()
    with pytest.raises(SystemExit, match="permanently closed"):
        run_study2_sheets_primary.main()


@pytest.mark.parametrize("field", ["failed_run_file_inventory_sha256",
                                   "failed_run_summary_sha256",
                                   "ack_fix_hostile_audit_zip_sha256"])
def test_amendment_requires_forensic_hashes(tmp_path, monkeypatch, field):
    gate = _gate(tmp_path, monkeypatch)
    amendment, _ = readiness._read_canonical(tmp_path / continuation.AMENDMENT)
    assert len(amendment[field]) == 64
    amendment[field] = "0" * 64
    _write(tmp_path / continuation.AMENDMENT, amendment)
    with pytest.raises(readiness.ProviderReadinessError, match="incident amendment"):
        _check(gate, "github")


def _future_candidate(gate, monkeypatch):
    monkeypatch.setattr(preparation, "LOCKS", gate["locks"])
    final, _ = readiness._read_canonical(gate["auth"])
    final["authorized_at_utc"] = "2026-09-28T13:00:00Z"
    candidate = dict(final, status="PENDING_INDEPENDENT_AUDIT",
                     collection_authorized=False)
    candidate_path = gate["root"] / "external-candidate.json"
    _write(candidate_path, candidate)
    _rebind_auth_audit(gate, final)
    gate["auth"].unlink()
    return candidate_path


def test_finalizer_rejects_future_dated_audit_and_accepts_past_audit(tmp_path, monkeypatch):
    gate = _gate(tmp_path, monkeypatch)
    candidate_path = _future_candidate(gate, monkeypatch)
    receipt, _ = readiness._read_canonical(gate["receipt"])
    receipt["audited_at_utc"] = "2026-09-28T12:30:00Z"
    _write(gate["receipt"], receipt)
    with pytest.raises(readiness.ProviderReadinessError, match="independent audit missing"):
        preparation.finalize_continuation(
            candidate_path=candidate_path, receipt_path=gate["receipt"],
            report_path=gate["report"], output_path=gate["auth"],
            root=tmp_path, now=NOW)
    assert not gate["auth"].exists()
    receipt["audited_at_utc"] = "2026-09-28T12:00:00Z"
    _write(gate["receipt"], receipt)
    digest = preparation.finalize_continuation(
        candidate_path=candidate_path, receipt_path=gate["receipt"],
        report_path=gate["report"], output_path=gate["auth"],
        root=tmp_path, now=NOW)
    assert digest == sha256_hex(gate["auth"].read_bytes())


def test_launch_requires_activation_time(tmp_path, monkeypatch):
    gate = _gate(tmp_path, monkeypatch)
    final, _ = readiness._read_canonical(gate["auth"])
    final["authorized_at_utc"] = "2026-09-28T13:00:00Z"
    _rebind_auth_audit(gate, final)
    with pytest.raises(readiness.ProviderReadinessError, match="missing or stale"):
        _check(gate, "github", now=NOW)
    assert _check(gate, "github", now=datetime(2026, 9, 28, 13, tzinfo=timezone.utc)) == (
        sha256_hex(gate["auth"].read_bytes()))


def test_candidate_cli_external_write_once(tmp_path, monkeypatch):
    gate = _gate(tmp_path, monkeypatch)
    candidate, _ = readiness._read_canonical(gate["auth"])
    candidate["status"] = "PENDING_INDEPENDENT_AUDIT"
    candidate["collection_authorized"] = False
    candidate["authorized_at_utc"] = "2026-09-28T13:00:00Z"
    calls = []
    monkeypatch.setattr(preparation, "prepare_continuation",
                        lambda **kwargs: (calls.append(kwargs) or candidate, "a" * 64))
    output = tmp_path / "candidate-output.json"
    argv = ["prepare", "--authorization-at-utc", "2026-09-28T13:00:00Z",
            "--output", str(output)]
    monkeypatch.setattr(sys, "argv", argv)
    assert preparation.main() == 0
    assert output.read_bytes() == canonical_json_bytes(candidate)
    assert calls and calls[0]["readiness_lock_paths"] == preparation.LOCKS
    with pytest.raises(FileExistsError):
        preparation.main()


def test_stale_collector_and_old_authorization_refused(tmp_path, monkeypatch):
    gate = _gate(tmp_path, monkeypatch)
    auth, _ = readiness._read_canonical(gate["auth"])
    auth["provider_static_identities"]["github"]["runtime_sha256"][continuation.COLLECTOR] = (
        "d8d3692e9313bee8a81ac95250c6376ccf9556599ba2e27d21ed37b3f0ae0905")
    _rebind_auth_audit(gate, auth)
    with pytest.raises(readiness.ProviderReadinessError):
        _check(gate, "github")
    historical, _ = readiness._read_canonical(readiness.ROOT / continuation.BASE_AUTHORIZATION)
    assert historical["provider_static_identities"]["github"]["runtime_sha256"][continuation.COLLECTOR] != (
        readiness.current_static_identity("github")["runtime_sha256"][continuation.COLLECTOR])
    old_locks = {
        name: readiness.ROOT / f"research/study2/{name}/{name.upper()}_PAPER_READINESS_LOCK_V1.json"
        for name in ("github", "razorpay")}
    old_locks["sheets"] = (readiness.ROOT /
                           "research/study2/sheets/GOOGLE_SHEETS_PAPER_READINESS_LOCK_V1.json")
    with pytest.raises(readiness.ProviderReadinessError, match="current static identity"):
        readiness.check_final_collection_authorization(
            provider="github", provider_identity=historical["provider_static_identities"]["github"],
            readiness_lock_paths=old_locks,
            authorization_path=readiness.ROOT / continuation.BASE_AUTHORIZATION,
            audit_receipt_path=readiness.ROOT /
                "research/study2/STUDY2_FINAL_AUTHORIZATION_AUDIT_RECEIPT_V1.json",
            audit_report_path=readiness.ROOT /
                "research/study2/STUDY2_FINAL_AUTHORIZATION_AUDIT_REPORT_V1.json",
            root=readiness.ROOT, now=NOW)


def test_missing_continuation_audit_and_stale_lock_refused(tmp_path, monkeypatch):
    gate = _gate(tmp_path, monkeypatch)
    gate["receipt"].unlink()
    with pytest.raises(readiness.ProviderReadinessError):
        _check(gate, "github")
    gate = _gate(tmp_path, monkeypatch)
    _write(gate["locks"]["razorpay"], {"stale": True})
    with pytest.raises(readiness.ProviderReadinessError, match="missing or stale"):
        _check(gate, "razorpay")


def test_missing_or_unaudited_amendment_refused(tmp_path, monkeypatch):
    gate = _gate(tmp_path, monkeypatch)
    (tmp_path / continuation.AMENDMENT_RECEIPT).unlink()
    with pytest.raises(readiness.ProviderReadinessError):
        _check(gate, "github")
    gate = _gate(tmp_path, monkeypatch)
    report, _ = readiness._read_canonical(tmp_path / continuation.AMENDMENT_REPORT)
    report["result"] = "PENDING"
    _write(tmp_path / continuation.AMENDMENT_REPORT, report)
    with pytest.raises(readiness.ProviderReadinessError, match="lacks independent audit"):
        _check(gate, "razorpay")
    (tmp_path / continuation.AMENDMENT).unlink()
    with pytest.raises(readiness.ProviderReadinessError):
        _check(gate, "github")


def test_no_zero_global_observations_or_refill_semantics(tmp_path, monkeypatch):
    gate = _gate(tmp_path, monkeypatch)
    auth, _ = readiness._read_canonical(gate["auth"])
    assert "study2_paper_observations_at_authorization" not in auth
    assert auth["sheets_primary_status"] == "CLOSED_IMPLEMENTATION_INVALIDATED"
    auth["study2_paper_observations_at_authorization"] = 0
    _rebind_auth_audit(gate, auth)
    with pytest.raises(readiness.ProviderReadinessError):
        _check(gate, "github")
    amendment, _ = readiness._read_canonical(tmp_path / continuation.AMENDMENT)
    assert amendment["sheets_primary_rerun_resume_refill_replacement"] is False
    amendment["sheets_primary_rerun_resume_refill_replacement"] = True
    _write(tmp_path / continuation.AMENDMENT, amendment)
    with pytest.raises(readiness.ProviderReadinessError):
        _check(gate, "razorpay")
