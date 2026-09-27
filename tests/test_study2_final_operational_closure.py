"""Offline failure cases for the final Study-2 readiness materializers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import socket
import time

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import provider_paper_readiness as readiness
from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest
from retry_semantics.study2.sheets_paper_readiness import readiness_requirements
from scripts import finalize_sheets_paper_dynamic_controls as dynamic
from scripts import materialize_sheets_paper_readiness_controls as controls
from scripts import prepare_study2_provider_readiness_lock as locks
from scripts import run_sheets_paper_live_readiness_session as session
from retry_semantics.study2.sheets_live_preparation import PreparedToken
from retry_semantics.study2.sheets_phase3_credentials import AcquisitionMetadata
from retry_semantics.study2.sheets_paper_adapter import DispatchFacts
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("offline test attempted network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def _write(path: Path, value: dict) -> None:
    path.write_bytes(canonical_json_bytes(value))


def _dynamic_fixture(tmp_path, monkeypatch):
    now = time.time()
    capture = tmp_path / "capture"
    output = tmp_path / "controls"
    capture.mkdir()
    output.mkdir()
    for name in readiness_requirements():
        record = controls._json(readiness.ROOT / controls.OUTPUT_DIR / f"{name}.json")
        record["subject"] = {
            "spreadsheet_id": load_paper_manifest()["spreadsheet_id"],
            "manifest_sha256": sha256_hex(canonical_json_bytes(load_paper_manifest()))}
        _write(output / f"{name}.json", record)
    monkeypatch.setattr(dynamic.controls, "_capture", lambda *_args, **_kw: {})
    original = controls._json(output / "same_app_and_principal_access.json")
    public = {"client_id": original["facts"]["app_id"]["candidate_public_client_id"],
              "scope": "https://www.googleapis.com/auth/drive.file"}
    review = {"public": public,
              "public_sha256": sha256_hex(canonical_json_bytes(public))}
    review_path = tmp_path / "client-review.json"
    _write(review_path, review)
    monkeypatch.setattr(dynamic.controls, "CLIENT_REVIEW", review_path)
    plan = {"token_expiry": now + 3600, "clock_uncertainty_seconds": 1}
    state = {"state": "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"}
    _write(capture / "capture-plan.json", plan)
    _write(capture / "capture-state.json", state)
    principal_id = original["facts"]["principal_id"]["permission_id"]
    principal = {"permissionId": principal_id, "emailAddress": "owner@example.test",
                 "displayName": "Owner"}
    about_target = "/drive/v3/about?fields=user(permissionId,emailAddress,displayName)"
    permission_target = (
        f"/drive/v3/files/{load_paper_manifest()['spreadsheet_id']}/permissions?"
        "fields=nextPageToken,permissions(id,type,role,emailAddress,displayName,allowFileDiscovery)"
        "&pageSize=100")
    for name, target, body in (
        ("paper-principal", about_target, {"user": principal}),
        ("paper-permissions", permission_target,
         {"permissions": [{"id": principal_id, "type": "user", "role": "owner",
                            "emailAddress": principal["emailAddress"]}]}),
    ):
        raw = canonical_json_bytes(body)
        (capture / f"{name}.response.json").write_bytes(raw)
        _write(capture / f"{name}.receipt.json", {
            "method": "GET", "target": target, "status": 200,
            "transport_error": None, "dispatch_initiated": True,
            "local_send_completed": True, "body_sha256": sha256_hex(raw)})
    permission_hash = sha256_hex((capture / "paper-permissions.response.json").read_bytes())
    session = {
        "schema": "sheets-paper-dynamic-session-v1",
        "client_id": review["public"]["client_id"],
        "public_config_sha256": review["public_sha256"],
        "acquisition": {"schema": "sheets-phase3-acquisition-metadata-v1",
                        "implementation": "stdlib-desktop-pkce-one-shot-v1",
                        "expiry_basis": "exchange-start-plus-expires-in",
                        "exchange_started_at": now - 2, "prepared_at": now - 1,
                        "public_config_sha256": review["public_sha256"],
                        "requested_scopes": ["https://www.googleapis.com/auth/drive.file"],
                        "granted_scopes": ["https://www.googleapis.com/auth/drive.file"],
                        "token_type": "Bearer", "refresh_persistence": "none",
                        "expires_at": plan["token_expiry"], "clock_uncertainty_seconds": 1},
        "token_metadata": {"schema": "sheets-paper-prepared-token-v1",
                           "bearer_sha256": sha256_hex(b"resident-test-token"),
                           "expires_at": plan["token_expiry"],
                           "clock_uncertainty_seconds": 1},
        "principal": {"permission_id": principal_id,
                      "email_address": principal["emailAddress"],
                      "display_name": principal["displayName"]},
        "permission_inventory_sha256": sha256_hex(canonical_json_bytes([permission_hash])),
        "capture_plan_sha256": sha256_hex((capture / "capture-plan.json").read_bytes()),
        "capture_state_sha256": sha256_hex((capture / "capture-state.json").read_bytes()),
    }
    _write(capture / "dynamic-session.json", session)
    return capture, output, now


def test_sheets_dynamic_finalizer_binds_realistic_plan_and_source_bytes(tmp_path, monkeypatch):
    capture, output, now = _dynamic_fixture(tmp_path, monkeypatch)
    hashes = dynamic.finalize(capture_dir=capture, output_dir=output,
                              planned_run_end_epoch=now + 1800, now=now)
    assert set(hashes) == {"same_app_and_principal_access", "token_lifetime"}
    token = controls._json(output / "token_lifetime.json")
    assert token["qualified"] is True
    assert token["facts"]["planned_run_end"]["epoch_seconds"] == now + 1800
    assert token["facts"]["token_expiry"]["expires_at"] == now + 3600
    assert b"resident-test-token" not in token["facts"]["token_expiry"]["source"]["path"].encode()
    controls.validate_control_provenance(
        {name: controls._json(output / f"{name}.json") for name in readiness_requirements()},
        allow_late_evidence=True)


def test_live_session_hands_same_bearer_to_external_owner_only_file(tmp_path, monkeypatch):
    now = time.time()
    token = PreparedToken("resident-test-token", now + 3600, 1)
    metadata = AcquisitionMetadata("a" * 64, "operator", now, now + 1,
                                   token.expires_at, 1)
    monkeypatch.setattr(session, "verify_repository_state", lambda **_kw: None)
    monkeypatch.setattr(session, "load_paper_manifest", lambda **_kw: {
        **load_paper_manifest(), "status": "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"})
    monkeypatch.setattr(session.setup, "review_client", lambda _path: {
        "public": {"client_id": "test.apps.googleusercontent.com"},
        "public_sha256": "a" * 64})
    def capture(*, evidence_dir, **_kw):
        evidence_dir.mkdir()
        _write(evidence_dir / "capture-plan.json", {"token_expiry": token.expires_at})
        _write(evidence_dir / "capture-state.json", {"state":
            "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"})
        return "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"
    def drive_get(*, target, bearer):
        assert bearer == token.value
        if target.startswith("/drive/v3/about?"):
            body = {"user": {"permissionId": "owner", "emailAddress": "owner@example.test",
                             "displayName": "Owner"}}
        else:
            body = {"permissions": [{"id": "owner", "type": "user", "role": "owner",
                                     "emailAddress": "owner@example.test"}]}
        return PaperHTTPResult(DispatchFacts(True, True, 200), canonical_json_bytes(body), None)
    capture_dir = tmp_path / "capture"
    bearer_file = tmp_path / "private-token"
    state = session.run_readiness_session(
        client_path=tmp_path / "client.json", evidence_dir=capture_dir,
        execute_live_readiness=True,
        readiness_confirmation=session.LIVE_READINESS_CONFIRMATION,
        expected_head="a" * 40, capture_dynamic_authority=True,
        acquire_authority_fn=lambda *_args, **_kw: (token, metadata),
        run_capture_fn=capture, drive_get_fn=drive_get,
        bearer_file=bearer_file)
    assert state == "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"
    assert bearer_file.read_bytes() == token.value.encode()
    assert bearer_file.stat().st_mode & 0o777 == 0o600
    assert token.value.encode() not in (capture_dir / "dynamic-session.json").read_bytes()
    assert session.make_token_metadata(token)["bearer_sha256"] == sha256_hex(bearer_file.read_bytes())


@pytest.mark.parametrize("attack", ["wrong_client", "wrong_principal", "changed_response",
                                    "short_plan", "missing_permission"])
def test_sheets_dynamic_finalizer_refuses_unproved_authority(tmp_path, monkeypatch, attack):
    capture, output, now = _dynamic_fixture(tmp_path, monkeypatch)
    if attack in ("wrong_client", "wrong_principal"):
        session = controls._json(capture / "dynamic-session.json")
        if attack == "wrong_client":
            session["client_id"] = "other.apps.googleusercontent.com"
        else:
            session["principal"]["permission_id"] = "different"
        _write(capture / "dynamic-session.json", session)
    elif attack == "changed_response":
        (capture / "paper-principal.response.json").write_bytes(b"{}\n")
    elif attack == "missing_permission":
        (capture / "paper-permissions.response.json").unlink()
    with pytest.raises((dynamic.controls.ControlEvidenceError, FileNotFoundError)):
        dynamic.finalize(capture_dir=capture, output_dir=output,
                         planned_run_end_epoch=now + (10 if attack == "short_plan" else 1800),
                         now=now)
    assert not (capture / "prospective-run-plan.json").exists()


def _lock_fixture(tmp_path, monkeypatch, provider="github"):
    identity = {"provider": provider, "manifest_sha256": "a" * 64,
                "runtime_sha256": {}}
    monkeypatch.setattr(locks, "current_static_identity", lambda *_args, **_kw: identity)
    monkeypatch.setattr(locks, "load_github_paper_manifest",
                        lambda _root: type("Manifest", (), {"as_json": lambda self: {
                            "study2_paper_observations": 0, "collection_status": "BLOCKED"}})())
    monkeypatch.setattr(locks, "load_razorpay_paper_manifest", lambda _root: {
        "study2_paper_observations": 0, "collection_status": "BLOCKED"})
    root = tmp_path
    directory = root / "research" / "study2" / provider
    evidence = directory / "readiness_control_evidence"
    evidence.mkdir(parents=True)
    hashes = {}
    for control in readiness.PROVIDER_CONTROLS[provider]:
        raw = canonical_json_bytes({"control": control})
        (evidence / f"{control}.json").write_bytes(raw)
        hashes[control] = sha256_hex(raw)
    report = {"schema": f"{provider}-paper-readiness-audit-report-v1",
              "static_identity": identity, "live_evidence_sha256": hashes,
              "independent_auditor": "separate-reviewer", "result": "PASS", "findings": []}
    report_path = directory / f"{provider.upper()}_PAPER_READINESS_AUDIT_REPORT_V1.json"
    _write(report_path, report)
    receipt = {"schema": f"{provider}-paper-readiness-audit-receipt-v1",
               "static_identity": identity, "live_evidence_sha256": hashes,
               "audit_report_sha256": sha256_hex(report_path.read_bytes()),
               "auditor_id": "separate-reviewer",
               "audited_at_utc": datetime.now(timezone.utc).isoformat()}
    receipt_path = directory / f"{provider.upper()}_PAPER_READINESS_AUDIT_RECEIPT_V1.json"
    _write(receipt_path, receipt)
    return root, evidence, receipt_path, report_path


@pytest.mark.parametrize("provider", ["github", "razorpay"])
def test_lock_preparer_submits_exact_candidate_to_existing_verifier(tmp_path, monkeypatch, provider):
    root, _, _, _ = _lock_fixture(tmp_path, monkeypatch, provider)
    def verifier(provider, candidate, **kwargs):
        lock = readiness._read_canonical(candidate)[0]
        assert kwargs["_candidate_uncommitted"] is True
        assert lock["static_identity"]["provider"] == provider
        assert lock["collection_authorized"] is False
        return lock["static_identity"]
    monkeypatch.setattr(locks, "check_readiness_lock", verifier)
    raw = locks.prepare_lock(provider, root=root)
    assert canonical_json_bytes(json.loads(raw)) == raw
    assert json.loads(raw)["collection_authorized"] is False


@pytest.mark.parametrize("attack", ["fake_audit", "fake_pass", "altered_control",
                                    "wrong_identity", "missing_control"])
def test_lock_preparer_refuses_bad_audit_or_control(tmp_path, monkeypatch, attack):
    root, evidence, receipt_path, report_path = _lock_fixture(tmp_path, monkeypatch)
    if attack in ("fake_audit", "fake_pass"):
        report = readiness._read_canonical(report_path)[0]
        if attack == "fake_audit":
            report["result"] = "FAIL"
        _write(report_path, report)
        receipt = readiness._read_canonical(receipt_path)[0]
        receipt["audit_report_sha256"] = sha256_hex(report_path.read_bytes())
        _write(receipt_path, receipt)
        monkeypatch.setattr(readiness, "current_static_identity",
                            lambda *_args, **_kw: locks.current_static_identity("github"))
        if attack == "fake_pass":
            monkeypatch.setattr(readiness, "load_github_paper_manifest",
                                locks.load_github_paper_manifest)
            monkeypatch.setattr(readiness, "load_github_namespace_registry",
                                lambda _root: type("Registry", (), {"as_json":
                                    lambda self: {}})())
    elif attack == "altered_control":
        (evidence / "writer_exclusion.json").write_bytes(b"{\"control\":\"changed\"}\n")
    elif attack == "wrong_identity":
        receipt = readiness._read_canonical(receipt_path)[0]
        receipt["static_identity"]["manifest_sha256"] = "b" * 64
        _write(receipt_path, receipt)
    else:
        (evidence / "writer_exclusion.json").unlink()
    with pytest.raises((readiness.ProviderReadinessError, FileNotFoundError)):
        locks.prepare_lock("github", root=root)
    assert not (root / "research/study2/github/GITHUB_PAPER_READINESS_LOCK_V1.json").exists()
