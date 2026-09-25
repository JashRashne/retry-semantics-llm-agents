"""Offline, evidence-bound pre-data Sheets readiness control materialization.

This reads retained provider responses only. It never acquires credentials or
contacts a provider. Unproved same-app and future-token facts remain false.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_adapter import evaluate_observation
from retry_semantics.study2.sheets_paper_blank_readiness import check_precollection_blank
from retry_semantics.study2.sheets_paper_materialize import _parse, load_paper_manifest
from retry_semantics.study2.sheets_paper_readiness import (
    CONTROL_FACTS, check_blank_baselines, check_grid, check_topology,
    metadata_target, readiness_requirements,
)

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import run_sheets_append_qualification_continuation as incident

BASE = Path.home() / "Library/Application Support/RetrySemantics"
CAPTURE_DIR = BASE / "sheets-paper-live-readiness-5d0465d760c88654425af577403419fdda737332"
ORIGINAL_DIR = incident.ORIGINAL_EVIDENCE_DIR
CONTINUATION_DIR = BASE / (ORIGINAL_DIR.name + "-continuation")
CLIENT_REVIEW = BASE / "sheets-phase4-first-read/client-review.json"
OUTPUT_DIR = Path("research/study2/sheets/readiness_control_evidence")
OLD_MANIFEST_SHA256 = "c9184255d5788fc00da3e7dd43afbe332a4dadcbc3f1534e95db320aeed8de4c"
SECOND_VISIBILITY_SECONDS = 0.6371620419959072


class ControlEvidenceError(ValueError):
    """Retained bytes do not support a claimed readiness fact."""


def _raw(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ControlEvidenceError(f"missing or symlinked source: {path.name}")
    return path.read_bytes()


def _json(path: Path) -> dict[str, Any]:
    value = _parse(_raw(path))
    if type(value) is not dict:
        raise ControlEvidenceError(f"malformed source: {path.name}")
    return value


def _ref(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_hex(_raw(path))}


def _capture(manifest: dict[str, Any], directory: Path) -> dict[str, Any]:
    plan = _json(directory / "capture-plan.json")
    state = _json(directory / "capture-state.json")
    if (plan.get("manifest_sha256") != OLD_MANIFEST_SHA256
            or state.get("manifest_sha256") != OLD_MANIFEST_SHA256
            or state.get("state") != "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"
            or plan.get("read_count") != 257
            or plan.get("interval_seconds") != 2.0
            or plan.get("spreadsheet_id") != manifest["spreadsheet_id"]
            or state.get("spreadsheet_id") != manifest["spreadsheet_id"]):
        raise ControlEvidenceError("read-only capture plan or state differs")
    arms = [arm for family in manifest["families"] for arm in family["arms"]]
    if len(arms) != 256:
        raise ControlEvidenceError("paper arm count differs")
    inventory: dict[str, str] = {}
    responses: dict[str, tuple[str, str, int, bytes]] = {}
    for index in range(257):
        name = "topology" if index == 0 else f"baseline-{index - 1:03d}"
        target = (metadata_target(manifest["spreadsheet_id"]) if index == 0
                  else arms[index - 1]["read_target"])
        response_path = directory / f"{name}.response.json"
        receipt_path = directory / f"{name}.receipt.json"
        raw = _raw(response_path)
        receipt = _json(receipt_path)
        inventory[response_path.name] = sha256_hex(raw)
        inventory[receipt_path.name] = sha256_hex(_raw(receipt_path))
        if (receipt.get("method") != "GET" or receipt.get("target") != target
                or receipt.get("status") != 200 or receipt.get("transport_error") is not None
                or receipt.get("dispatch_initiated") is not True
                or receipt.get("local_send_completed") is not True
                or receipt.get("spreadsheet_id") != manifest["spreadsheet_id"]
                or receipt.get("body_sha256") != sha256_hex(raw)):
            raise ControlEvidenceError(f"read-only capture receipt differs: {name}")
        if index == 0:
            check_topology(manifest, 200, raw)
            topology_raw = raw
        else:
            arm = arms[index - 1]
            responses[arm["arm_id"]] = ("GET", target, 200, raw)
            # All retained paper GETs also contain explicit GridData, so they
            # satisfy the frozen strict parser without using its blank shortcut.
            observed = check_grid(manifest, arm, 200, raw)
            if observed.entered_rows or observed.marker_rows or observed.unexpected_rows:
                raise ControlEvidenceError("paper baseline is not strictly blank")
    check_blank_baselines(manifest, responses)
    return {"plan": plan, "state": state, "inventory_sha256": sha256_hex(canonical_json_bytes(inventory)),
            "topology_sha256": sha256_hex(topology_raw),
            "baseline_sha256": {arm_id: sha256_hex(captured[3]) for arm_id, captured in responses.items()},
            "plan_ref": _ref(directory / "capture-plan.json"),
            "state_ref": _ref(directory / "capture-state.json"),
            "topology_ref": _ref(directory / "topology.response.json")}


def _engineering(original_dir: Path, continuation_dir: Path) -> dict[str, Any]:
    original, original_inventory = incident.verify_original_incident(original_dir)
    intent = _json(original_dir / "qualification-intent.json")
    principal = _json(original_dir / "paper-principal.response.json").get("user")
    permissions = _json(original_dir / "paper-permissions.response.json").get("permissions")
    original_state = _json(original_dir / "qualification-state.json")
    state = _json(continuation_dir / "continuation-state.json")
    if (type(principal) is not dict or type(permissions) is not list
            or len(permissions) != 1 or permissions[0].get("role") != "owner"
            or permissions[0].get("id") != principal.get("permissionId")
            or permissions[0].get("emailAddress") != principal.get("emailAddress")
            or original_state.get("paper_principal_identity", {}).get("permission_id")
            != principal.get("permissionId")
            or intent.get("operator_controls_provider_proven") is not False
            or set(intent.get("operator_attested_controls", [])) != {
                "EXPLICIT_NO_BOUND_SCRIPTS_OR_EXTERNAL_AUTOMATION",
                "EXPLICIT_DEDICATED_PAPER_SPREADSHEET_NO_MANUAL_WRITERS"}
            or state.get("state") != incident.SUCCESS
            or state.get("original_evidence_inventory") != original_inventory
            or state.get("first_post_http_status") != 200
            or state.get("first_post_current_state_row") != 1
            or state.get("first_post_visibility_within_40_seconds_proven") is not False
            or state.get("continuation_post_dispatch_count") != 1
            or state.get("first_second_request_identity_equal") is not True
            or state.get("final_duplicate_rows") != [1, 2]
            or state.get("second_append_visibility_seconds") != SECOND_VISIBILITY_SECONDS
            or state.get("cleanup_performed") is not False
            or state.get("fixture_retired") is not True
            or state.get("paper_spreadsheet_mutation_count") != 0
            or state.get("study2_paper_observations") != 0):
        raise ControlEvidenceError("engineering incident evidence differs")
    arm = incident._fixture_arm()
    for name, target in (("paper-principal", "/drive/v3/about?fields=user(permissionId,emailAddress,displayName)"),
                         ("paper-permissions", f"/drive/v3/files/{incident.PAPER_SPREADSHEET_ID}/permissions?"
                          "fields=nextPageToken,permissions(id,type,role,emailAddress,displayName,allowFileDiscovery)"
                          "&pageSize=100")):
        raw = _raw(original_dir / f"{name}.response.json")
        receipt = _json(original_dir / f"{name}.receipt.json")
        if (receipt.get("method") != "GET" or receipt.get("target") != target
                or receipt.get("status") != 200 or receipt.get("transport_error") is not None
                or receipt.get("body_sha256") != sha256_hex(raw)):
            raise ControlEvidenceError("paper Drive identity receipt differs")
    preblank = _raw(original_dir / "preblank.response.json")
    preblank_receipt = _json(original_dir / "preblank.receipt.json")
    if (preblank_receipt.get("method") != "GET"
            or preblank_receipt.get("target") != arm["read_target"]
            or preblank_receipt.get("status") != 200
            or preblank_receipt.get("transport_error") is not None
            or preblank_receipt.get("body_sha256") != sha256_hex(preblank)):
        raise ControlEvidenceError("engineering preblank receipt differs")
    check_precollection_blank({"spreadsheet_id": incident.FIXTURE_SPREADSHEET_ID}, arm,
                              method="GET", target=arm["read_target"], status=200, raw=preblank)
    for name, expected in (("pre-replay", (0,)), ("post-2", (0, 1))):
        raw = _raw(continuation_dir / f"{name}.response.json")
        receipt = _json(continuation_dir / f"{name}.receipt.json")
        if (receipt.get("method") != "GET" or receipt.get("target") != arm["read_target"]
                or receipt.get("status") != 200 or receipt.get("transport_error") is not None
                or receipt.get("body_sha256") != sha256_hex(raw)):
            raise ControlEvidenceError("engineering full-grid read receipt differs")
        observed = check_grid({"spreadsheet_id": incident.FIXTURE_SPREADSHEET_ID},
                              arm, 200, raw, intended=(incident.ITEM, incident.DETAIL))
        if (observed.entered_rows != expected or observed.matching_intended_rows != expected
                or observed.unexpected_rows or observed.attributable_unintended_rows
                or evaluate_observation(observed, authority_qualified=True)
                != ("EXACTLY_ONE" if expected == (0,) else "DUPLICATE")):
            raise ControlEvidenceError("engineering full-grid row evidence differs")
    second = _raw(continuation_dir / "append-2.response.json")
    second_receipt = _json(continuation_dir / "append-2.receipt.json")
    if (second_receipt.get("method") != "POST"
            or second_receipt.get("target") != incident.MUTATION_URI
            or second_receipt.get("status") != 200
            or second_receipt.get("transport_error") is not None
            or second_receipt.get("request_identity_sha256") != original.identity_hash
            or second_receipt.get("body_sha256") != sha256_hex(second)):
        raise ControlEvidenceError("second append receipt differs")
    from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
    from retry_semantics.study2.sheets_paper_adapter import DispatchFacts
    incident.validate_documented_acknowledgement(
        original, PaperHTTPResult(DispatchFacts(True, True, 200), second, None))
    return {"intent_ref": _ref(original_dir / "qualification-intent.json"),
            "principal_ref": _ref(original_dir / "paper-principal.response.json"),
            "permissions_ref": _ref(original_dir / "paper-permissions.response.json"),
            "original_request_ref": _ref(original_dir / "frozen-request.json"),
            "preblank_ref": _ref(original_dir / "preblank.response.json"),
            "pre_ref": _ref(continuation_dir / "pre-replay.response.json"),
            "post_ref": _ref(continuation_dir / "post-2.response.json"),
            "append_ref": _ref(continuation_dir / "append-2.response.json"),
            "state_ref": _ref(continuation_dir / "continuation-state.json"),
            "principal_id": principal["permissionId"],
            "request_sha256": original.identity_hash}


def build_records(*, manifest: dict[str, Any], capture_dir: Path = CAPTURE_DIR,
                  original_dir: Path = ORIGINAL_DIR,
                  continuation_dir: Path = CONTINUATION_DIR,
                  client_review: Path = CLIENT_REVIEW) -> dict[str, dict[str, Any]]:
    if (manifest.get("collection_status") != "BLOCKED"
            or manifest.get("readiness_status") != "NOT_QUALIFIED"
            or manifest.get("study2_paper_observations") != 0
            or manifest.get("spreadsheet_id") != incident.PAPER_SPREADSHEET_ID):
        raise ControlEvidenceError("paper manifest is not prospective and blocked")
    capture = _capture(manifest, capture_dir)
    paper_markers = [arm["arm_marker"] for family in manifest["families"] for arm in family["arms"]]
    if len(set(paper_markers)) != 256 or incident.MARKER in paper_markers:
        raise ControlEvidenceError("engineering marker collides with paper allocation")
    eng = _engineering(original_dir, continuation_dir)
    review = _json(client_review)
    public = review.get("public")
    if (type(public) is not dict or public.get("scope") != "https://www.googleapis.com/auth/drive.file"
            or type(public.get("client_id")) is not str
            or review.get("public_sha256") != sha256_hex(canonical_json_bytes(public))):
        raise ControlEvidenceError("public OAuth client review differs")
    source = {"capture_directory": str(capture_dir),
              "capture_inventory_sha256": capture["inventory_sha256"],
              "capture_state": capture["state_ref"]}
    engineering_scope = {"kind": "engineering_fixture_only",
                         "spreadsheet_id": incident.FIXTURE_SPREADSHEET_ID,
                         "paper_spreadsheet_mutation_count": 0,
                         "source": eng["state_ref"]}
    facts = {
        "same_app_and_principal_access": {
            "app_id": {"candidate_public_client_id": public["client_id"],
                       "source": _ref(client_review),
                       "live_qualification_session_binding": "NOT_PERSISTED"},
            "principal_id": {"permission_id": eng["principal_id"], "source": eng["principal_ref"]},
            "drive_file_grant": {"scope": public["scope"], "source": _ref(client_review),
                                 "live_access": eng["principal_ref"],
                                 "session_client_id_proven": False}},
        "writer_exclusion": {
            "writer_inventory": {"sole_owner_permission_id": eng["principal_id"],
                                 "other_writer_roles": [], "source": eng["permissions_ref"]},
            "exclusive_writer_control": {"at_capture": True,
                                         "provider_acl": eng["permissions_ref"],
                                         "manual_writer_exclusion": "operator_attested",
                                         "attestation_source": eng["intent_ref"]}},
        "no_scripts_or_external_writers": {
            "script_inventory": {"authority": "operator_attested_not_provider_proven",
                                 "confirmation": "EXPLICIT_NO_BOUND_SCRIPTS_OR_EXTERNAL_AUTOMATION",
                                 "source": eng["intent_ref"]},
            "external_writer_inventory": {"authority": "operator_attested_not_provider_proven",
                                          "confirmation": "EXPLICIT_DEDICATED_PAPER_SPREADSHEET_NO_MANUAL_WRITERS",
                                          "source": eng["intent_ref"]}},
        "no_formula_protection_or_structural_edit": {
            "formula_scan": {"finding": "zero_entered_cells_in_all_256_100x3_grids_at_capture",
                             "source": source},
            "protection_scan": {"finding": "no_protected_ranges_or_filters_in_topology_at_capture",
                                "source": capture["topology_ref"]},
            "structure_lock": {"finding": "expected_256_GRID_tabs_100x3_at_capture",
                               "source": capture["topology_ref"],
                               "future_edit_exclusion": "operator_attested",
                               "attestation_source": eng["intent_ref"]}},
        "marker_round_trip_and_collision_refusal": {
            "qualification_scope": engineering_scope,
            "marker_readback": {"marker": incident.MARKER, "source": eng["post_ref"]},
            "collision_check": {"paper_marker_count": 256,
                                "paper_baseline_entered_row_count": 0,
                                "source": source}},
        "append_placement_and_duplicate_preservation": {
            "qualification_scope": engineering_scope,
            "placement": {"first_row_one_based": 1,
                          "previously_blank_source": eng["preblank_ref"],
                          "current_one_row_source": eng["pre_ref"]},
            "duplicate_readback": {"rows_one_based": [1, 2],
                                   "frozen_request_identity_sha256": eng["request_sha256"],
                                   "first_request": eng["original_request_ref"],
                                   "second_ack": eng["append_ref"],
                                   "final_read": eng["post_ref"]}},
        "post_write_visibility": {
            "qualification_scope": engineering_scope,
            "visibility_timing": {"second_append_ack_to_complete_grid_seconds": SECOND_VISIBILITY_SECONDS,
                                  "within_40_seconds": True,
                                  "first_append_within_40_seconds_proven": False,
                                  "source": eng["state_ref"]}},
        "observer_authority": {
            "complete_grid_read": {"strict_explicit_grid_data_accepted_count": 256,
                                   "paper_source": source,
                                   "engineering_post_write_source": eng["post_ref"]},
            "read_identity": {"paper_spreadsheet_id": manifest["spreadsheet_id"],
                              "a1_range": "A1:C100", "source": capture["topology_ref"]}},
        "token_lifetime": {
            "token_expiry": {"prior_readiness_token_expiry": capture["plan"]["token_expiry"],
                             "source": capture["plan_ref"],
                             "future_run_authority": False},
            "planned_run_end": {"state": "UNBOUND_FOR_FUTURE_PAPER_COLLECTION",
                                "required_action": "fresh resident drive.file token and pre-dispatch bounded paper-run end certificate"}},
        "quota_and_timing_feasibility": {
            "quota_snapshot": {"successful_read_only_get_count": 257,
                               "read_interval_seconds": 2.0, "source": capture["plan_ref"]},
            "request_budget": {"max_get_response_bytes": 1048576,
                               "request_cap_seconds": 30,
                               "source": capture["plan_ref"]},
            "timing_budget": {"capture_planned_seconds": capture["plan"]["planned_seconds"],
                              "capture_state": capture["state_ref"],
                              "paper_run_token_lifetime_still_unqualified": True}},
    }
    qualified = {name: name not in {"same_app_and_principal_access", "token_lifetime"}
                 for name in readiness_requirements()}
    subject = {"spreadsheet_id": manifest["spreadsheet_id"],
               "manifest_sha256": sha256_hex(canonical_json_bytes(manifest))}
    if set(facts) != set(CONTROL_FACTS):
        raise ControlEvidenceError("control set differs from frozen requirements")
    return {name: {"schema": "sheets-paper-readiness-control-evidence-v1",
                   "control": name, "subject": subject, "qualified": qualified[name],
                   "facts": facts[name]}
            for name in readiness_requirements()}


def validate_control_provenance(records: dict[str, dict[str, Any]], *,
                                allow_late_evidence: bool = False) -> None:
    """Reject source-authority laundering before any future lock candidate."""
    if set(records) != set(CONTROL_FACTS):
        raise ControlEvidenceError("missing readiness control")
    for name, record in records.items():
        if (set(record) != {"schema", "control", "subject", "qualified", "facts"}
                or record["schema"] != "sheets-paper-readiness-control-evidence-v1"
                or record["control"] != name or type(record["qualified"]) is not bool
                or set(record["facts"]) != CONTROL_FACTS[name]):
            raise ControlEvidenceError("control shape differs")
    script = records["no_scripts_or_external_writers"]
    for field in CONTROL_FACTS["no_scripts_or_external_writers"]:
        if script["facts"][field].get("authority") != "operator_attested_not_provider_proven":
            raise ControlEvidenceError("operator attestation misrepresented as provider proof")
    for name in ("marker_round_trip_and_collision_refusal",
                 "append_placement_and_duplicate_preservation", "post_write_visibility"):
        scope = records[name]["facts"]["qualification_scope"]
        if (scope.get("kind") != "engineering_fixture_only"
                or scope.get("spreadsheet_id") != incident.FIXTURE_SPREADSHEET_ID
                or scope.get("paper_spreadsheet_mutation_count") != 0):
            raise ControlEvidenceError("engineering qualification misrepresented as paper mutation")
    visibility = records["post_write_visibility"]["facts"]["visibility_timing"]
    if (visibility.get("first_append_within_40_seconds_proven") is not False
            or visibility.get("second_append_ack_to_complete_grid_seconds") != SECOND_VISIBILITY_SECONDS):
        raise ControlEvidenceError("unsupported first visibility or altered second timing")
    app = records["same_app_and_principal_access"]
    token = records["token_lifetime"]
    if allow_late_evidence:
        binding = app["facts"]["app_id"].get("live_qualification_session_binding")
        expiry = token["facts"]["token_expiry"].get("expires_at")
        run_end = token["facts"]["planned_run_end"].get("epoch_seconds")
        if (app["qualified"] is not True or type(binding) is not dict
                or binding.get("verified") is not True
                or app["facts"]["drive_file_grant"].get("session_client_id_proven") is not True
                or token["qualified"] is not True or type(expiry) not in (int, float)
                or type(run_end) not in (int, float) or expiry <= run_end):
            raise ControlEvidenceError("future app or token lifetime proof incomplete")
    elif app["qualified"] or token["qualified"]:
        raise ControlEvidenceError("future app or token lifetime proof absent")


def materialize(*, output_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    manifest = load_paper_manifest()
    records = build_records(manifest=manifest)
    validate_control_provenance(records)
    output_dir.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, record in records.items():
        path = output_dir / f"{name}.json"
        raw = canonical_json_bytes(record)
        if path.exists():
            if path.is_symlink() or path.read_bytes() != raw:
                raise ControlEvidenceError(f"existing control differs: {name}")
        else:
            with path.open("xb") as file:
                file.write(raw)
        hashes[name] = sha256_hex(raw)
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materialize-offline", action="store_true", required=True)
    args = parser.parse_args()
    if args.materialize_offline:
        hashes = materialize()
        print(f"{len(hashes)} canonical controls; {sum(_json(OUTPUT_DIR / (n + '.json'))['qualified'] for n in hashes)} qualified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
