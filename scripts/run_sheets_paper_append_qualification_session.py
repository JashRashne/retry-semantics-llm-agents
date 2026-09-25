"""One terminal, engineering-only qualification of the frozen paper AppendCells request.

Importing this module has no network or mutation effect. The paper spreadsheet
is read only for principal and ACL evidence; all Sheets requests use the fixed
retained engineering fixture.
"""

from __future__ import annotations

import argparse
import http.client
import os
from pathlib import Path
import signal
import ssl
import subprocess
import sys
import threading
import time
from typing import Any, Callable
from urllib.parse import quote

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_live_preparation import PreparedToken
from retry_semantics.study2.sheets_offline import FrozenMutation
from retry_semantics.study2.sheets_paper_adapter import (
    DispatchFacts, evaluate_observation, prepare_paper_append, replay_request,
)
from retry_semantics.study2.sheets_paper_blank_readiness import check_precollection_blank
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult, one_shot_request
from retry_semantics.study2.sheets_paper_materialize import (
    IMPLEMENTATION_PATHS, MANIFEST_PATH, MAX_READ_BYTES, _parse,
    load_paper_manifest, read_target,
)
from retry_semantics.study2.sheets_paper_readiness import check_grid
from retry_semantics.study2.sheets_paper_registry import REPOSITORY_ROOT
from retry_semantics.study2.sheets_paper_runner import store_original, validate_append_acknowledgement

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from run_sheets_paper_live_readiness_session import acquire_resident_token

FROZEN_PAPER_RUNTIME_HEAD = "5d0465d760c88654425af577403419fdda737332"
FROZEN_MANIFEST_SHA256 = "c9184255d5788fc00da3e7dd43afbe332a4dadcbc3f1534e95db320aeed8de4c"
FIXTURE_SPREADSHEET_ID = "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w"
FIXTURE_SHEET_ID = 1
FIXTURE_TITLE = "RetrySemanticsEngineering"
FIXTURE_RANGE = "A1:C100"
ITEM = "engineering-qualification-item-v1"
DETAIL = "engineering-qualification-detail-v1"
MARKER = "RS2-SHEETS-V1-" + sha256_hex(b"sheets-paper-append-qualification-v1")[:32]
APPEND_CONFIRMATION = "EXPLICIT_ENGINEERING_APPEND_DUPLICATE_QUALIFICATION"
AUTOMATION_CONFIRMATION = "EXPLICIT_NO_BOUND_SCRIPTS_OR_EXTERNAL_AUTOMATION"
WRITERS_CONFIRMATION = "EXPLICIT_DEDICATED_PAPER_SPREADSHEET_NO_MANUAL_WRITERS"
SUCCESS = "ENGINEERING_APPEND_QUALIFICATION_PASSED"


class QualificationRefused(ValueError):
    """A qualification gate failed; no recovery or cleanup is authorized."""


def _git(*args: str, root: Path = REPOSITORY_ROOT) -> bytes:
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", *args],
        cwd=root, capture_output=True, check=True,
    ).stdout


def verify_repository_state(*, expected_head: str, root: Path = REPOSITORY_ROOT) -> None:
    if type(expected_head) is not str or not expected_head:
        raise QualificationRefused("--expected-head is required")
    try:
        head = _git("rev-parse", "HEAD", root=root).decode().strip()
        if head != expected_head:
            raise QualificationRefused("repository HEAD differs from --expected-head")
        if Path(_git("rev-parse", "--show-toplevel", root=root).decode().strip()).resolve() != root.resolve():
            raise QualificationRefused("repository root differs")
        if _git("status", "--porcelain", "--ignore-submodules=all", root=root).strip():
            raise QualificationRefused("repository working tree is dirty")
        _git("merge-base", "--is-ancestor", FROZEN_PAPER_RUNTIME_HEAD, head, root=root)
    except subprocess.CalledProcessError as exc:
        raise QualificationRefused("repository git gate failed") from exc
    if sha256_hex((root / MANIFEST_PATH).read_bytes()) != FROZEN_MANIFEST_SHA256:
        raise QualificationRefused("frozen manifest SHA mismatch")
    if "scripts/run_sheets_paper_append_qualification_session.py" in IMPLEMENTATION_PATHS:
        raise QualificationRefused("operator entered frozen implementation paths")


def _read_json_file(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise QualificationRefused("missing or symlinked readiness evidence")
    raw = path.read_bytes()
    if len(raw) > MAX_READ_BYTES:
        raise QualificationRefused("oversized readiness evidence")
    value = _parse(raw)
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise QualificationRefused("malformed or noncanonical readiness evidence")
    return value, raw


def verify_prior_readiness(evidence_dir: Path, manifest: dict[str, Any]) -> str:
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise QualificationRefused("prior paper-readiness directory missing")
    state, state_raw = _read_json_file(evidence_dir / "capture-state.json")
    if (state.get("state") != "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"
            or state.get("spreadsheet_id") != manifest["spreadsheet_id"]
            or state.get("manifest_sha256") != FROZEN_MANIFEST_SHA256):
        raise QualificationRefused("prior paper-readiness capture-state invalid")
    names = ["topology"] + [f"baseline-{i:03d}" for i in range(256)]
    arms = [arm for family in manifest["families"] for arm in family["arms"]]
    if len(arms) != 256:
        raise QualificationRefused("paper arm count invalid")
    for index, name in enumerate(names):
        receipt, _ = _read_json_file(evidence_dir / f"{name}.receipt.json")
        response_path = evidence_dir / f"{name}.response.json"
        if response_path.is_symlink() or not response_path.is_file():
            raise QualificationRefused("missing or symlinked readiness response")
        response_raw = response_path.read_bytes()
        if len(response_raw) > MAX_READ_BYTES or type(_parse(response_raw)) is not dict:
            raise QualificationRefused("malformed readiness response")
        expected_target = (None if index == 0 else arms[index - 1]["read_target"])
        if (receipt.get("method") != "GET" or receipt.get("status") != 200
                or receipt.get("transport_error") is not None
                or receipt.get("dispatch_initiated") is not True
                or receipt.get("local_send_completed") is not True
                or receipt.get("spreadsheet_id") != manifest["spreadsheet_id"]
                or receipt.get("body_sha256") != sha256_hex(response_raw)
                or (expected_target is not None and receipt.get("target") != expected_target)):
            raise QualificationRefused(f"prior paper-readiness evidence invalid: {name}")
    return sha256_hex(state_raw)


def _write(path: Path, value: Any) -> str:
    raw = value if type(value) is bytes else canonical_json_bytes(value)
    with path.open("xb") as file:
        file.write(raw)
        file.flush()
        os.fsync(file.fileno())
    return sha256_hex(raw)


def _deadline(_signum: int, _frame: Any) -> None:
    raise TimeoutError()


def drive_get_once(*, target: str, bearer: str) -> PaperHTTPResult:
    """One bounded Drive GET with no redirect, retry, refresh, or bearer logging."""
    if (type(target) is not str or not target.startswith(("/drive/v3/about?", "/drive/v3/files/"))
            or type(bearer) is not str or not bearer
            or threading.current_thread() is not threading.main_thread()):
        raise QualificationRefused("invalid Drive GET")
    old_handler = signal.getsignal(signal.SIGALRM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    if old_timer != (0.0, 0.0):
        raise QualificationRefused("existing request deadline")
    connection = None
    initiated = False
    sent = False
    status = None
    body = b""
    try:
        signal.signal(signal.SIGALRM, _deadline)
        signal.setitimer(signal.ITIMER_REAL, 30)
        connection = http.client.HTTPSConnection(
            "www.googleapis.com", 443, timeout=30,
            context=ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH))
        connection.connect()
        connection.putrequest("GET", target, skip_host=True, skip_accept_encoding=True)
        for key, value in (("Host", "www.googleapis.com"), ("Authorization", "Bearer " + bearer),
                           ("Accept", "application/json"), ("Accept-Encoding", "identity"),
                           ("Connection", "close")):
            connection.putheader(key, value)
        initiated = True
        connection.endheaders()
        sent = True
        response = connection.getresponse()
        status = response.status
        body = response.read(MAX_READ_BYTES + 1)
        if len(body) > MAX_READ_BYTES:
            return PaperHTTPResult(DispatchFacts(True, True, status), b"", "response_cap_exceeded")
        return PaperHTTPResult(DispatchFacts(True, True, status), body, None)
    except Exception as exc:
        return PaperHTTPResult(DispatchFacts(initiated, sent, status), body, type(exc).__name__)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _receipt(result: PaperHTTPResult, target: str, body_hash: str) -> dict[str, Any]:
    return {"schema": "sheets-append-qualification-http-receipt-v1", "method": "GET",
            "target": target, "status": result.facts.http_status,
            "transport_error": result.transport_error,
            "dispatch_initiated": result.facts.initiated,
            "local_send_completed": result.facts.local_send_completed,
            "body_sha256": body_hash}


def _capture(evidence_dir: Path, name: str, result: PaperHTTPResult,
             target: str, *, method: str = "GET", request_sha: str | None = None,
             bearer: str) -> None:
    if bearer.encode("utf-8") in result.body:
        raise QualificationRefused("provider response contains resident bearer")
    body_hash = _write(evidence_dir / f"{name}.response.json", result.body)
    receipt = _receipt(result, target, body_hash)
    receipt["method"] = method
    if request_sha is not None:
        receipt["request_identity_sha256"] = request_sha
    _write(evidence_dir / f"{name}.receipt.json", receipt)


def _require_get(result: PaperHTTPResult) -> dict[str, Any]:
    if (type(result) is not PaperHTTPResult or result.facts.http_status != 200
            or result.transport_error is not None or not result.facts.local_send_completed):
        raise QualificationRefused("read-only provider GET failed")
    value = _parse(result.body)
    if type(value) is not dict:
        raise QualificationRefused("read-only provider response malformed")
    return value


def _drive_evidence(*, evidence_dir: Path, paper_id: str, bearer: str,
                    drive_get: Callable[..., PaperHTTPResult]) -> tuple[dict[str, str], str, int]:
    about_target = "/drive/v3/about?fields=user(permissionId,emailAddress,displayName)"
    about_result = drive_get(target=about_target, bearer=bearer)
    _capture(evidence_dir, "paper-principal", about_result, about_target, bearer=bearer)
    about = _require_get(about_result)
    principal = about.get("user")
    if (set(about) != {"user"} or type(principal) is not dict
            or type(principal.get("permissionId")) is not str or not principal["permissionId"]
            or type(principal.get("emailAddress")) is not str or not principal["emailAddress"]
            or type(principal.get("displayName")) is not str or not principal["displayName"]):
        raise QualificationRefused("paper principal not identifiable")
    base = (f"/drive/v3/files/{quote(paper_id, safe='')}/permissions?"
            "fields=nextPageToken,permissions(id,type,role,emailAddress,displayName,allowFileDiscovery)"
            "&pageSize=100")
    permissions: list[dict[str, Any]] = []
    page_token: str | None = None
    page = 1
    hashes: list[str] = []
    while True:
        target = base + ("&pageToken=" + quote(page_token, safe="") if page_token else "")
        result = drive_get(target=target, bearer=bearer)
        name = "paper-permissions" if page == 1 else f"paper-permissions-page-{page}"
        _capture(evidence_dir, name, result, target, bearer=bearer)
        hashes.append(sha256_hex(result.body))
        data = _require_get(result)
        if (not set(data) <= {"permissions", "nextPageToken"}
                or type(data.get("permissions")) is not list):
            raise QualificationRefused("paper permission response incomplete")
        permissions.extend(data["permissions"])
        next_token = data.get("nextPageToken")
        if next_token is None:
            break
        if type(next_token) is not str or not next_token or next_token == page_token or page >= 100:
            raise QualificationRefused("paper permission pagination malformed")
        page_token = next_token
        page += 1
    ids: set[str] = set()
    owners = []
    for permission in permissions:
        if (type(permission) is not dict
                or not {"id", "type", "role"} <= set(permission)
                or not set(permission) <= {"id", "type", "role", "emailAddress", "displayName", "allowFileDiscovery"}
                or type(permission["id"]) is not str or not permission["id"]
                or permission["id"] in ids or permission["type"] not in {"user", "group", "domain", "anyone"}
                or permission["role"] not in {"owner", "writer", "fileOrganizer",
                                               "organizer", "reader", "commenter"}
                or ("emailAddress" in permission and type(permission["emailAddress"]) is not str)
                or ("displayName" in permission and type(permission["displayName"]) is not str)
                or ("allowFileDiscovery" in permission and type(permission["allowFileDiscovery"]) is not bool)):
            raise QualificationRefused("paper permission response malformed")
        ids.add(permission["id"])
        if permission["role"] in {"owner", "writer", "fileOrganizer", "organizer"}:
            if (permission["role"] != "owner" or permission["type"] != "user"
                    or permission["id"] != principal["permissionId"]
                    or permission.get("emailAddress") != principal["emailAddress"]):
                raise QualificationRefused("paper ACL has another writer or owner")
            owners.append(permission)
    if len(owners) != 1:
        raise QualificationRefused("paper principal does not match sole owner")
    return ({"permission_id": principal["permissionId"],
             "email_address": principal["emailAddress"],
             "display_name": principal["displayName"]},
            sha256_hex(canonical_json_bytes(hashes)), page + 1)


def _fixture_arm() -> dict[str, Any]:
    return {"spreadsheet_id": FIXTURE_SPREADSHEET_ID, "sheet_id": FIXTURE_SHEET_ID,
            "tab_title": FIXTURE_TITLE, "range": FIXTURE_RANGE,
            "read_target": read_target(FIXTURE_SPREADSHEET_ID, FIXTURE_TITLE),
            "arm_marker": MARKER}


def _check_post(manifest: dict[str, Any], arm: dict[str, Any],
                result: PaperHTTPResult, expected_rows: tuple[int, ...]) -> str:
    if result.transport_error is not None or result.facts.http_status != 200:
        raise QualificationRefused("post-write grid GET failed")
    observation = check_grid(manifest, arm, 200, result.body, intended=(ITEM, DETAIL))
    if (observation.entered_rows != expected_rows
            or observation.marker_rows != expected_rows
            or observation.matching_intended_rows != expected_rows
            or observation.unexpected_rows or observation.attributable_unintended_rows
            or any(observation.rows[i] != (MARKER, ITEM, DETAIL) for i in expected_rows)):
        raise QualificationRefused("post-write row placement or contents mismatch")
    classification = evaluate_observation(observation, authority_qualified=True)
    expected_classification = "EXACTLY_ONE" if len(expected_rows) == 1 else "DUPLICATE"
    if classification != expected_classification:
        raise QualificationRefused("post-write classification mismatch")
    return classification


def run_qualification(*, client_path: Path, prior_readiness_dir: Path,
                      evidence_dir: Path, expected_head: str,
                      execute: bool, confirmation: str,
                      automation_confirmation: str, writers_confirmation: str,
                      root: Path = REPOSITORY_ROOT,
                      acquire_token: Callable[..., PreparedToken] = acquire_resident_token,
                      drive_get: Callable[..., PaperHTTPResult] = drive_get_once,
                      sheets_transport: Callable[..., PaperHTTPResult] = one_shot_request,
                      wall_clock: Callable[[], float] = time.time,
                      monotonic: Callable[[], float] = time.monotonic) -> str:
    if (execute is not True or confirmation != APPEND_CONFIRMATION
            or automation_confirmation != AUTOMATION_CONFIRMATION
            or writers_confirmation != WRITERS_CONFIRMATION):
        raise QualificationRefused("explicit execution and operator confirmations required")
    if evidence_dir.exists() or evidence_dir.is_symlink():
        raise QualificationRefused("evidence directory must be new")
    verify_repository_state(expected_head=expected_head, root=root)
    manifest = load_paper_manifest(root=root)
    readiness_state_sha = verify_prior_readiness(prior_readiness_dir, manifest)
    markers = [arm["arm_marker"] for family in manifest["families"] for arm in family["arms"]]
    if len(markers) != 256 or MARKER in markers:
        raise QualificationRefused("qualification marker collides with paper arm")
    if FIXTURE_SPREADSHEET_ID == manifest["spreadsheet_id"]:
        raise QualificationRefused("engineering fixture aliases paper spreadsheet")
    token = acquire_token(client_path)
    if type(token) is not PreparedToken or token.expires_at - wall_clock() <= 180 + token.clock_uncertainty_seconds:
        raise QualificationRefused("resident token insufficient for qualification")
    evidence_dir.mkdir(mode=0o700, parents=True)
    arm = _fixture_arm()
    fixture_manifest = {"spreadsheet_id": FIXTURE_SPREADSHEET_ID}
    state: dict[str, Any] = {
        "schema": "sheets-append-qualification-state-v1", "state": "IN_PROGRESS",
        "manifest_sha256": FROZEN_MANIFEST_SHA256,
        "fixture": {"spreadsheet_id": FIXTURE_SPREADSHEET_ID, "sheet_id": FIXTURE_SHEET_ID,
                    "title": FIXTURE_TITLE, "range": FIXTURE_RANGE},
        "marker": MARKER, "post_dispatch_count": 0, "get_count": 0,
        "fixture_retired": False, "paper_spreadsheet_mutation_count": 0,
        "study2_paper_observations": 0,
        "operator_attested_controls": [AUTOMATION_CONFIRMATION, WRITERS_CONFIRMATION],
    }
    _write(evidence_dir / "qualification-intent.json", {
        "schema": "sheets-append-qualification-intent-v1",
        "expected_head": expected_head, "manifest_sha256": FROZEN_MANIFEST_SHA256,
        "prior_readiness_capture_state_sha256": readiness_state_sha,
        "fixture": state["fixture"], "marker": MARKER,
        "item": ITEM, "detail": DETAIL, "confirmation": APPEND_CONFIRMATION,
        "operator_attested_controls": state["operator_attested_controls"],
        "operator_controls_provider_proven": False,
    })
    try:
        principal, inventory_hash, drive_get_count = _drive_evidence(
            evidence_dir=evidence_dir, paper_id=manifest["spreadsheet_id"],
            bearer=token.value, drive_get=drive_get)
        state["paper_principal_identity"] = principal
        state["paper_permission_inventory_sha256"] = inventory_hash
        state["drive_get_count"] = drive_get_count
        state["get_count"] += drive_get_count
        target = arm["read_target"]
        pre = sheets_transport(method="GET", target=target, body=b"", bearer=token.value,
                               spreadsheet_id=FIXTURE_SPREADSHEET_ID,
                               max_response_bytes=MAX_READ_BYTES)
        state["get_count"] += 1
        _capture(evidence_dir, "preblank", pre, target, bearer=token.value)
        if pre.transport_error is not None:
            raise QualificationRefused("engineering preflight GET failed")
        check_precollection_blank(fixture_manifest, arm, method="GET", target=target,
                                  status=pre.facts.http_status, raw=pre.body)
        original = prepare_paper_append(arm, ITEM, DETAIL)
        if original.uri != f"/v4/spreadsheets/{FIXTURE_SPREADSHEET_ID}:batchUpdate":
            raise QualificationRefused("frozen mutation target mismatch")
        store_original(evidence_dir / "frozen-request.json", original)
        state["frozen_request_identity_sha256"] = original.identity_hash
        for number, expected_rows in ((1, (0,)), (2, (0, 1))):
            request = original if number == 1 else replay_request(original)
            if (request is not original or request.method != original.method
                    or request.uri != original.uri or request.headers != original.headers
                    or request.body != original.body or request.identity_hash != original.identity_hash):
                raise QualificationRefused("exact replay identity changed")
            # Durable retirement precedes any possible transport dispatch.
            if number == 1:
                _write(evidence_dir / "fixture-retired.json", {
                    "schema": "sheets-append-fixture-retired-v1", "fixture": state["fixture"],
                    "retired": True, "reason": "first mutation dispatch planned; no cleanup permitted"})
                state["fixture_retired"] = True
            state["post_dispatch_count"] += 1
            result = sheets_transport(method=request.method, target=request.uri,
                                      body=request.body, bearer=token.value,
                                      spreadsheet_id=FIXTURE_SPREADSHEET_ID,
                                      max_response_bytes=131072,
                                      application_headers=request.headers,
                                      timeout_seconds=30, allow_mutation=True)
            _capture(evidence_dir, f"append-{number}", result, request.uri,
                     method="POST", request_sha=request.identity_hash, bearer=token.value)
            validate_append_acknowledgement(request, arm, result)
            acknowledged_at = monotonic()
            read = sheets_transport(method="GET", target=target, body=b"", bearer=token.value,
                                    spreadsheet_id=FIXTURE_SPREADSHEET_ID,
                                    max_response_bytes=MAX_READ_BYTES)
            state["get_count"] += 1
            _capture(evidence_dir, f"post-{number}", read, target, bearer=token.value)
            classification = _check_post(fixture_manifest, arm, read, expected_rows)
            read_complete_at = monotonic()
            elapsed = read_complete_at - acknowledged_at
            state[f"visibility_{number}_seconds"] = elapsed
            state[f"classification_{number}"] = classification
            if elapsed < 0 or elapsed > 40:
                raise QualificationRefused("post-write visibility exceeded 40 seconds")
        state.update(state=SUCCESS, first_placement_row=1,
                     duplicate_row_indices=[1, 2])
        _write(evidence_dir / "qualification-state.json", state)
        return SUCCESS
    except Exception as exc:
        state["state"] = "ENGINEERING_APPEND_QUALIFICATION_FAILED"
        state["failure_type"] = type(exc).__name__
        if not (evidence_dir / "qualification-state.json").exists():
            _write(evidence_dir / "qualification-state.json", state)
        raise
    finally:
        token = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--prior-readiness-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--automation-confirmation", required=True)
    parser.add_argument("--writers-confirmation", required=True)
    args = parser.parse_args(argv)
    try:
        print(run_qualification(client_path=args.client, prior_readiness_dir=args.prior_readiness_dir,
                                evidence_dir=args.evidence_dir, expected_head=args.expected_head,
                                execute=args.execute, confirmation=args.confirmation,
                                automation_confirmation=args.automation_confirmation,
                                writers_confirmation=args.writers_confirmation))
        return 0
    except Exception as exc:
        print(f"Append qualification refused: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
