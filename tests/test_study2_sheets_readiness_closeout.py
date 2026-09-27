"""Offline hostile tests for the prospective Sheets acknowledgement closeout."""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_adapter import DispatchFacts, prepare_paper_append
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
from retry_semantics.study2 import sheets_paper_materialize as mat
from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest
from retry_semantics.study2.sheets_paper_readiness import (
    CONTROL_FACTS, PaperReadinessError, check_readiness_structure,
    qualify_readiness, readiness_requirements,
)
from retry_semantics.study2.sheets_paper_runner import PaperRunnerError, validate_append_acknowledgement
import materialize_sheets_paper_readiness_controls as controls
import prepare_sheets_paper_readiness_lock as lock_prep

REAL_ACK = (
    b'{\n  "spreadsheetId": "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w",'
    b'\n  "replies": [\n    {}\n  ],\n'
    b'  "commentUpdateState": "NO_UPDATES_REQUESTED"\n}\n'
)


def _current_controls():
    return {name: json.loads((controls.OUTPUT_DIR / f"{name}.json").read_bytes())
            for name in readiness_requirements()}


def _fixture_request():
    arm = {"spreadsheet_id": "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w",
           "sheet_id": 1, "arm_marker": "RS2-SHEETS-V1-b6328ec985a06929becd9a7d91bd35fa"}
    return prepare_paper_append(arm, "engineering-qualification-item-v1",
                                "engineering-qualification-detail-v1"), arm


def _ack(body, status=200, error=None):
    raw = body if type(body) is bytes else canonical_json_bytes(body)
    return PaperHTTPResult(DispatchFacts(True, True, status), raw, error)


def test_exact_real_google_ack_and_absent_optional_field_accepted():
    request, arm = _fixture_request()
    assert sha256_hex(REAL_ACK) == "41d54d9b1c6cce13b965a3d440b9e2153993b4f951d62e88dd15c65545891e3d"
    assert validate_append_acknowledgement(request, arm, _ack(REAL_ACK)).acknowledgement_validated
    assert validate_append_acknowledgement(request, arm, _ack({
        "spreadsheetId": arm["spreadsheet_id"], "replies": [{}]})).acknowledgement_validated


@pytest.mark.parametrize("body", [
    {"spreadsheetId": "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w",
     "replies": [{}], "commentUpdateState": "MODIFIED"},
    {"spreadsheetId": "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w",
     "replies": [{}], "commentUpdateState": None},
    {"spreadsheetId": "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w",
     "replies": [{}], "updatedSpreadsheet": {}},
    {"spreadsheetId": "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w",
     "replies": [{}], "unknown": 1},
    {"spreadsheetId": "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w", "replies": []},
    {"spreadsheetId": "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w", "replies": [{}, {}]},
    {"spreadsheetId": "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w"},
    {"spreadsheetId": "wrong", "replies": [{}]},
    b"{malformed",
])
def test_ack_rejects_every_other_shape(body):
    request, arm = _fixture_request()
    with pytest.raises(PaperRunnerError):
        validate_append_acknowledgement(request, arm, _ack(body))


@pytest.mark.parametrize("status,error", [(503, None), (None, "TimeoutError")])
def test_ack_rejects_non_200_and_ambiguity(status, error):
    request, arm = _fixture_request()
    with pytest.raises(PaperRunnerError):
        validate_append_acknowledgement(request, arm, _ack(REAL_ACK, status, error))


def test_historical_frozen_manifest_remains_reproducible():
    raw = (mat.REPOSITORY_ROOT / mat.MANIFEST_PATH).read_bytes()
    manifest = load_paper_manifest()
    assert sha256_hex(raw) == "7c9bddb797938e026344afe49650922219ca35febf9322bdfb62f402caa87991"
    assert raw == mat.build_paper_manifest()
    assert manifest["status"] == "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"
    assert len(manifest["families"]) == 64
    assert manifest["study2_paper_observations"] == 0  # Historical pre-data snapshot.


def test_stale_runner_implementation_sha_is_refused(tmp_path, monkeypatch):
    current = load_paper_manifest()
    stale = copy.deepcopy(current)
    stale["implementation_sha256"]["src/retry_semantics/study2/sheets_paper_runner.py"] = (
        "0" * 64)
    target = tmp_path / mat.MANIFEST_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(canonical_json_bytes(stale))
    monkeypatch.setattr(mat, "build_paper_manifest", lambda **kwargs: canonical_json_bytes(current))
    with pytest.raises(mat.SheetsPaperMaterializationError, match="differs"):
        mat.load_paper_manifest(root=tmp_path)


def test_old_257_get_capture_cannot_transfer_to_current_manifest():
    with pytest.raises(controls.ControlEvidenceError, match="capture plan or state differs"):
        controls._capture(load_paper_manifest(), controls.CAPTURE_DIR)


def test_all_ten_canonical_controls_and_exact_fact_fields():
    manifest = load_paper_manifest()
    expected = _current_controls()
    assert set(expected) == set(readiness_requirements()) == set(CONTROL_FACTS)
    for name, record in expected.items():
        path = controls.OUTPUT_DIR / f"{name}.json"
        raw = path.read_bytes()
        assert raw == canonical_json_bytes(record)
        assert set(record["facts"]) == CONTROL_FACTS[name]
        assert record["subject"] == {"spreadsheet_id": manifest["spreadsheet_id"],
                                     "manifest_sha256": sha256_hex(canonical_json_bytes(manifest))}
    controls.validate_control_provenance(expected, allow_late_evidence=True)
    assert all(record["qualified"] for record in expected.values())


def test_unqualified_control_cannot_pass_frozen_final_structure_gate(tmp_path):
    manifest = load_paper_manifest()
    arms = [arm for family in manifest["families"] for arm in family["arms"]]
    topology = (200, (controls.CAPTURE_DIR / "topology.response.json").read_bytes())
    baselines = {arm["arm_id"]: ("GET", arm["read_target"], 200,
                 (controls.CAPTURE_DIR / f"baseline-{index:03d}.response.json").read_bytes())
                 for index, arm in enumerate(arms)}
    index = {}
    for name, record in _current_controls().items():
        if name == "token_lifetime":
            record["qualified"] = False
        raw = canonical_json_bytes(record)
        (tmp_path / f"{name}.json").write_bytes(raw)
        index[name] = {"file": f"{name}.json", "sha256": sha256_hex(raw)}
    with pytest.raises(PaperReadinessError, match="unqualified control"):
        check_readiness_structure(manifest, topology_response=topology,
                                  baseline_responses=baselines, control_evidence=index,
                                  evidence_root=tmp_path)


def test_control_provenance_refuses_attestation_laundering_and_paper_write_claim():
    records = _current_controls()
    changed = copy.deepcopy(records)
    changed["no_scripts_or_external_writers"]["facts"]["script_inventory"]["authority"] = "provider_proven"
    with pytest.raises(controls.ControlEvidenceError, match="attestation"):
        controls.validate_control_provenance(changed)
    changed = copy.deepcopy(records)
    changed["append_placement_and_duplicate_preservation"]["facts"]["qualification_scope"]["spreadsheet_id"] = (
        load_paper_manifest()["spreadsheet_id"])
    with pytest.raises(controls.ControlEvidenceError, match="paper mutation"):
        controls.validate_control_provenance(changed)
    changed = copy.deepcopy(records)
    changed["post_write_visibility"]["facts"]["visibility_timing"]["first_append_within_40_seconds_proven"] = True
    with pytest.raises(controls.ControlEvidenceError, match="first visibility"):
        controls.validate_control_provenance(changed)
    assert records["post_write_visibility"]["facts"]["visibility_timing"][
        "second_append_ack_to_complete_grid_seconds"] == 0.6371620419959072


def test_missing_source_or_wrong_subject_fails_closed(tmp_path):
    manifest = load_paper_manifest()
    records = _current_controls()
    index = {}
    for name, record in records.items():
        value = copy.deepcopy(record)
        value["qualified"] = True  # Isolate the frozen subject gate in this test.
        if name == "writer_exclusion":
            value["subject"]["manifest_sha256"] = "0" * 64
        raw = canonical_json_bytes(value)
        (tmp_path / f"{name}.json").write_bytes(raw)
        index[name] = {"file": f"{name}.json", "sha256": sha256_hex(raw)}
    arms = [a for family in manifest["families"] for a in family["arms"]]
    topology = (200, (controls.CAPTURE_DIR / "topology.response.json").read_bytes())
    baselines = {arm["arm_id"]: ("GET", arm["read_target"], 200,
                 (controls.CAPTURE_DIR / f"baseline-{i:03d}.response.json").read_bytes())
                 for i, arm in enumerate(arms)}
    args = dict(topology_response=topology, baseline_responses=baselines,
                control_evidence=index, evidence_root=tmp_path)
    with pytest.raises(PaperReadinessError, match="unqualified control"):
        check_readiness_structure(manifest, **args)
    (tmp_path / "writer_exclusion.json").unlink()
    with pytest.raises(PaperReadinessError, match="missing"):
        check_readiness_structure(manifest, **args)


def test_no_lock_before_receipt_report_and_clean_committed_inputs(tmp_path):
    manifest = load_paper_manifest()
    subject = {"spreadsheet_id": manifest["spreadsheet_id"],
               "manifest_sha256": sha256_hex(canonical_json_bytes(manifest))}
    with pytest.raises(lock_prep.LockPreparationRefused, match="receipt"):
        lock_prep.require_independent_audit(tmp_path / "absent.json", subject=subject,
                                            control_sha256={}, topology_sha256="0" * 64,
                                            baseline_sha256={})
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(canonical_json_bytes({
        "schema": "sheets-paper-readiness-audit-receipt-v1", "subject": subject,
        "control_sha256": {}, "topology_sha256": "0" * 64,
        "baseline_sha256": {}, "independent_audit": {
            "auditor_id": "future-independent-auditor", "audited_at_utc": "future",
            "audit_report_file": "missing-report.txt", "audit_report_sha256": "0" * 64}}))
    with pytest.raises(lock_prep.LockPreparationRefused, match="report"):
        lock_prep.require_independent_audit(receipt, subject=subject,
                                            control_sha256={}, topology_sha256="0" * 64,
                                            baseline_sha256={})
    with pytest.raises((controls.ControlEvidenceError, PaperReadinessError,
                        lock_prep.LockPreparationRefused)):
        lock_prep.prepare_lock(audit_receipt=receipt)
    assert not (tmp_path / "GOOGLE_SHEETS_PAPER_READINESS_LOCK_V1.json").exists()
    assert manifest["collection_status"] == "BLOCKED"


def test_offline_materializers_have_no_provider_action_path():
    source = inspect.getsource(controls) + inspect.getsource(lock_prep)
    for forbidden in ("one_shot_request", "acquire_resident_token", "spreadsheets.create",
                      "model_continue", "allow_mutation=True"):
        assert forbidden not in source
