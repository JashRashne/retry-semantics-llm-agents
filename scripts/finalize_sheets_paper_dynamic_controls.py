"""Offline finalization of two Sheets controls from one retained OAuth session.

The operator supplies a prospective absolute run end. No bearer or audit PASS
is created here. An independent auditor must still review the candidate bytes.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_materialize import _parse, load_paper_manifest
from retry_semantics.study2.sheets_paper_readiness import readiness_requirements

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import materialize_sheets_paper_readiness_controls as controls


def _read(path: Path) -> dict:
    raw = controls._raw(path)
    value = _parse(raw)
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise controls.ControlEvidenceError(f"noncanonical evidence: {path.name}")
    return value


def _drive_response(directory: Path, name: str, target: str) -> dict:
    body_path = directory / f"{name}.response.json"
    receipt = _read(directory / f"{name}.receipt.json")
    raw = controls._raw(body_path)
    if (receipt.get("method") != "GET" or receipt.get("target") != target
            or receipt.get("status") != 200 or receipt.get("transport_error") is not None
            or receipt.get("dispatch_initiated") is not True
            or receipt.get("local_send_completed") is not True
            or receipt.get("body_sha256") != sha256_hex(raw)):
        raise controls.ControlEvidenceError("Drive principal capture differs")
    value = _parse(raw)
    if type(value) is not dict:
        raise controls.ControlEvidenceError("Drive response malformed")
    return value


def finalize(*, capture_dir: Path, output_dir: Path = controls.OUTPUT_DIR,
             planned_run_end_epoch: float, now: float | None = None) -> dict[str, str]:
    if capture_dir.is_symlink():
        raise controls.ControlEvidenceError("capture directory symlinked")
    capture_dir = capture_dir.resolve(strict=True)
    if not capture_dir.is_dir():
        raise controls.ControlEvidenceError("capture directory invalid")
    instant = time.time() if now is None else now
    if (type(planned_run_end_epoch) not in (int, float)
            or not math.isfinite(planned_run_end_epoch)
            or planned_run_end_epoch <= instant + 40):
        raise controls.ControlEvidenceError("prospective run end must cover one OBS-1 arm")
    manifest = load_paper_manifest()
    controls._capture(manifest, capture_dir)
    session = _read(capture_dir / "dynamic-session.json")
    acquisition = session.get("acquisition")
    token = session.get("token_metadata")
    # Phase-4 review is canonical JSON with its historical trailing newline.
    review = controls._json(controls.CLIENT_REVIEW)
    plan = _read(capture_dir / "capture-plan.json")
    state = _read(capture_dir / "capture-state.json")
    if (set(session) != {"schema", "client_id", "public_config_sha256", "acquisition",
                         "token_metadata", "principal", "permission_inventory_sha256",
                         "capture_plan_sha256", "capture_state_sha256"}
            or session["schema"] != "sheets-paper-dynamic-session-v1"
            or type(acquisition) is not dict or type(token) is not dict
            or type(review.get("public")) is not dict
            or review.get("public_sha256") != sha256_hex(canonical_json_bytes(review.get("public")))
            or review["public"].get("scope") != "https://www.googleapis.com/auth/drive.file"
            or session["client_id"] != review["public"]["client_id"]
            or session["public_config_sha256"] != review["public_sha256"]
            or acquisition.get("schema") != "sheets-phase3-acquisition-metadata-v1"
            or acquisition.get("implementation") != "stdlib-desktop-pkce-one-shot-v1"
            or acquisition.get("expiry_basis") != "exchange-start-plus-expires-in"
            or acquisition.get("exchange_started_at", float("inf")) >
               acquisition.get("prepared_at", -1)
            or acquisition.get("prepared_at", float("inf")) >= acquisition.get("expires_at", -1)
            or acquisition.get("public_config_sha256") != review["public_sha256"]
            or acquisition.get("requested_scopes") != ["https://www.googleapis.com/auth/drive.file"]
            or acquisition.get("granted_scopes") != ["https://www.googleapis.com/auth/drive.file"]
            or acquisition.get("token_type") != "Bearer"
            or acquisition.get("refresh_persistence") != "none"
            or acquisition.get("expires_at") != token.get("expires_at")
            or acquisition.get("clock_uncertainty_seconds") != token.get("clock_uncertainty_seconds")
            or token.get("schema") != "sheets-paper-prepared-token-v1"
            or set(token) != {"schema", "bearer_sha256", "expires_at",
                              "clock_uncertainty_seconds"}
            or type(token.get("bearer_sha256")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", token["bearer_sha256"]) is None
            or plan.get("token_expiry") != token["expires_at"]
            or plan.get("clock_uncertainty_seconds") != token["clock_uncertainty_seconds"]
            or session["capture_plan_sha256"] != sha256_hex(controls._raw(capture_dir / "capture-plan.json"))
            or session["capture_state_sha256"] != sha256_hex(controls._raw(capture_dir / "capture-state.json"))
            or state.get("state") != "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"):
        raise controls.ControlEvidenceError("session OAuth or capture binding differs")
    expiry = token["expires_at"]
    uncertainty = token["clock_uncertainty_seconds"]
    if (type(expiry) not in (int, float) or not math.isfinite(expiry)
            or type(uncertainty) not in (int, float) or not math.isfinite(uncertainty)
            or uncertainty < 0 or expiry <= planned_run_end_epoch + uncertainty):
        raise controls.ControlEvidenceError("real token cannot cover prospective run plan")
    about = _drive_response(capture_dir, "paper-principal",
                            "/drive/v3/about?fields=user(permissionId,emailAddress,displayName)")
    principal = about.get("user")
    if (set(about) != {"user"} or type(principal) is not dict
            or any(type(principal.get(key)) is not str or not principal[key]
                   for key in ("permissionId", "emailAddress", "displayName"))
            or session["principal"] != {"permission_id": principal["permissionId"],
                                         "email_address": principal["emailAddress"],
                                         "display_name": principal["displayName"]}):
        raise controls.ControlEvidenceError("fresh Drive principal differs")
    base = (f"/drive/v3/files/{quote(manifest['spreadsheet_id'], safe='')}/permissions?"
            "fields=nextPageToken,permissions(id,type,role,emailAddress,displayName,allowFileDiscovery)"
            "&pageSize=100")
    hashes, owners, seen, page_refs = [], [], set(), []
    page_token = None
    for page in range(1, 101):
        name = "paper-permissions" if page == 1 else f"paper-permissions-page-{page}"
        target = base + ("&pageToken=" + quote(page_token, safe="") if page_token else "")
        data = _drive_response(capture_dir, name, target)
        hashes.append(sha256_hex(controls._raw(capture_dir / f"{name}.response.json")))
        page_refs.extend((controls._ref(capture_dir / f"{name}.response.json"),
                          controls._ref(capture_dir / f"{name}.receipt.json")))
        if (not set(data) <= {"permissions", "nextPageToken"}
                or type(data.get("permissions")) is not list):
            raise controls.ControlEvidenceError("permission page malformed")
        for permission in data["permissions"]:
            if (type(permission) is not dict or type(permission.get("id")) is not str
                    or not permission["id"] or permission["id"] in seen
                    or permission.get("type") not in ("user", "group", "domain", "anyone")
                    or permission.get("role") not in ("owner", "writer", "fileOrganizer",
                                                      "organizer", "reader", "commenter")):
                raise controls.ControlEvidenceError("permission inventory malformed")
            seen.add(permission["id"])
            if permission["role"] in ("owner", "writer", "fileOrganizer", "organizer"):
                owners.append(permission)
        page_token = data.get("nextPageToken")
        if page_token is None:
            break
        if type(page_token) is not str or not page_token or page == 100:
            raise controls.ControlEvidenceError("permission pagination incomplete")
    if (len(owners) != 1 or owners[0].get("id") != principal["permissionId"]
            or owners[0].get("emailAddress") != principal["emailAddress"]
            or owners[0].get("role") != "owner" or owners[0].get("type") != "user"
            or session["permission_inventory_sha256"] != sha256_hex(canonical_json_bytes(hashes))):
        raise controls.ControlEvidenceError("fresh principal is not sole owner")
    records = {_name: _read(output_dir / f"{_name}.json")
               for _name in readiness_requirements()}
    controls.validate_control_provenance(records)
    subject = {"spreadsheet_id": manifest["spreadsheet_id"],
               "manifest_sha256": sha256_hex(canonical_json_bytes(manifest))}
    if any(record["subject"] != subject for record in records.values()):
        raise controls.ControlEvidenceError("control subjects differ from capture")
    if (records["same_app_and_principal_access"]["facts"]["principal_id"]["permission_id"]
            != principal["permissionId"]):
        raise controls.ControlEvidenceError("fresh principal differs from audited app")
    if (records["same_app_and_principal_access"]["facts"]["app_id"]["candidate_public_client_id"]
            != session["client_id"]):
        raise controls.ControlEvidenceError("fresh Desktop client differs")
    session_ref = controls._ref(capture_dir / "dynamic-session.json")
    principal_ref = controls._ref(capture_dir / "paper-principal.response.json")
    permission_ref = controls._ref(capture_dir / "paper-permissions.response.json")
    app = records["same_app_and_principal_access"]
    app["facts"]["app_id"]["live_qualification_session_binding"] = {
        "verified": True, "session": session_ref,
        "capture_plan": controls._ref(capture_dir / "capture-plan.json"),
        "capture_state": controls._ref(capture_dir / "capture-state.json")}
    app["facts"]["principal_id"] = {"permission_id": principal["permissionId"],
                                      "source": principal_ref}
    app["facts"]["drive_file_grant"] = {
        "scope": "https://www.googleapis.com/auth/drive.file",
        "session_client_id_proven": True, "source": session_ref,
        "live_access": permission_ref,
        "permission_pages": page_refs,
        "permission_inventory_sha256": session["permission_inventory_sha256"]}
    app["qualified"] = True
    plan_record = {"schema": "sheets-paper-prospective-run-plan-v1",
                   "dynamic_session_sha256": session_ref["sha256"],
                   "bearer_sha256": token["bearer_sha256"],
                   "planned_run_end_epoch": planned_run_end_epoch,
                   "recorded_at_epoch": instant}
    plan_raw = canonical_json_bytes(plan_record)
    plan_path = capture_dir / "prospective-run-plan.json"
    if plan_path.exists() or plan_path.is_symlink():
        raise controls.ControlEvidenceError("run plan already exists")
    token_record = records["token_lifetime"]
    token_record["facts"] = {
        "token_expiry": {"expires_at": expiry, "clock_uncertainty_seconds": uncertainty,
                         "bearer_sha256": token["bearer_sha256"], "source": session_ref},
        "planned_run_end": {"epoch_seconds": planned_run_end_epoch,
                            "source": {"path": str(plan_path), "sha256": sha256_hex(plan_raw)}}}
    token_record["qualified"] = True
    controls.validate_control_provenance(records, allow_late_evidence=True)
    with plan_path.open("xb") as output:
        output.write(plan_raw)
    hashes_out = {}
    for name in ("same_app_and_principal_access", "token_lifetime"):
        path = output_dir / f"{name}.json"
        raw = canonical_json_bytes(records[name])
        path.write_bytes(raw)
        hashes_out[name] = sha256_hex(raw)
    return hashes_out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize-offline", action="store_true", required=True)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--planned-run-end-epoch", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        for name, digest in finalize(capture_dir=args.capture_dir,
                                     planned_run_end_epoch=args.planned_run_end_epoch).items():
            print(f"{name} {digest}")
        return 0
    except Exception as exc:
        print(f"Dynamic controls refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
