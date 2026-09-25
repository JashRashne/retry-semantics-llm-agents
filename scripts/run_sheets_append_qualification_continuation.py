"""Continue one spent engineering AppendCells qualification incident.

The original incident directory is fixed and read only. Importing this module
performs no OAuth, network request, or mutation.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_live_preparation import PreparedToken
from retry_semantics.study2.sheets_offline import FrozenMutation
from retry_semantics.study2.sheets_paper_adapter import (
    DispatchFacts, evaluate_observation, replay_request,
)
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult, one_shot_request
from retry_semantics.study2.sheets_paper_materialize import (
    MANIFEST_PATH, MAX_READ_BYTES, _parse, read_target,
)
from retry_semantics.study2.sheets_paper_readiness import check_grid
from retry_semantics.study2.sheets_paper_registry import REPOSITORY_ROOT
from retry_semantics.study2.sheets_paper_runner import load_original

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from run_sheets_paper_live_readiness_session import acquire_resident_token

ORIGINAL_EVIDENCE_DIR = (Path.home() / "Library/Application Support/RetrySemantics/"
                         "sheets-paper-append-qualification-"
                         "c5f5872b50ffa1a6031483679fff6d6646e1ec4a-drive-enabled")
PAPER_MANIFEST_SHA256 = "c9184255d5788fc00da3e7dd43afbe332a4dadcbc3f1534e95db320aeed8de4c"
PAPER_SPREADSHEET_ID = "15Sf9PrQqVRWj2Fe4pR_ZKslGWwbBi3OfgH_eElpoJ_Q"
FIXTURE_SPREADSHEET_ID = "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w"
FIXTURE_SHEET_ID = 1
FIXTURE_TITLE = "RetrySemanticsEngineering"
FIXTURE_RANGE = "A1:C100"
MARKER = "RS2-SHEETS-V1-b6328ec985a06929becd9a7d91bd35fa"
ITEM = "engineering-qualification-item-v1"
DETAIL = "engineering-qualification-detail-v1"
FIRST_REQUEST_SHA256 = "5ea069da3a2e02b2674ba4ef85db2f810b8834800c9096dcbe3ffe1fb66ec543"
FIRST_RESPONSE_SHA256 = "41d54d9b1c6cce13b965a3d440b9e2153993b4f951d62e88dd15c65545891e3d"
CONTINUATION_CONFIRMATION = "EXPLICIT_CONTINUE_SPENT_APPEND_QUALIFICATION_ONCE"
SUCCESS = "ENGINEERING_APPEND_QUALIFICATION_CONTINUATION_PASSED"
MUTATION_URI = f"/v4/spreadsheets/{FIXTURE_SPREADSHEET_ID}:batchUpdate"
APPLICATION_HEADERS = (("content-type", "application/json; charset=utf-8"),
                       ("accept", "application/json"))
ROW = (MARKER, ITEM, DETAIL)


class ContinuationRefused(ValueError):
    """An incident gate failed; the retired fixture must be left untouched."""


def _git(*args: str, root: Path = REPOSITORY_ROOT) -> bytes:
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", *args],
        cwd=root, capture_output=True, check=True,
    ).stdout


def verify_repository_state(*, expected_head: str, root: Path = REPOSITORY_ROOT) -> None:
    """All repository checks precede OAuth and any evidence directory creation."""
    if type(expected_head) is not str or len(expected_head) != 40:
        raise ContinuationRefused("full --expected-head required")
    try:
        head = _git("rev-parse", "HEAD", root=root).decode().strip()
        if head != expected_head:
            raise ContinuationRefused("HEAD differs from --expected-head")
        if Path(_git("rev-parse", "--show-toplevel", root=root).decode().strip()).resolve() != root.resolve():
            raise ContinuationRefused("repository root differs")
        if _git("status", "--porcelain", "--ignore-submodules=all", root=root).strip():
            raise ContinuationRefused("working tree is dirty")
        if _git("rev-parse", "origin/main", root=root).decode().strip() != head:
            raise ContinuationRefused("HEAD differs from origin/main")
    except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
        raise ContinuationRefused("repository check failed") from exc
    if sha256_hex((root / MANIFEST_PATH).read_bytes()) != PAPER_MANIFEST_SHA256:
        raise ContinuationRefused("frozen paper manifest SHA differs")


def _read_file(path: Path, *, canonical: bool = False) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ContinuationRefused("original incident evidence missing or symlinked")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_READ_BYTES:
        raise ContinuationRefused("original incident evidence empty or oversized")
    value = _parse(raw)
    if type(value) is not dict or (canonical and canonical_json_bytes(value) != raw):
        raise ContinuationRefused("original incident evidence malformed")
    return value, raw


def validate_documented_acknowledgement(request: FrozenMutation,
                                         result: PaperHTTPResult) -> None:
    """Validate the documented response without changing the frozen paper runner."""
    if (type(request) is not FrozenMutation or request.method != "POST"
            or request.uri != MUTATION_URI or request.headers != APPLICATION_HEADERS
            or request.identity_hash != FIRST_REQUEST_SHA256
            or type(result) is not PaperHTTPResult
            or result.transport_error is not None
            or result.facts != DispatchFacts(True, True, 200)
            or type(result.body) is not bytes or len(result.body) > 131072):
        raise ContinuationRefused("append acknowledgement transport or request invalid")
    body = _parse(result.body)
    if (type(body) is not dict
            or not {"spreadsheetId", "replies"} <= set(body)
            or not set(body) <= {"spreadsheetId", "replies", "commentUpdateState"}
            or body["spreadsheetId"] != FIXTURE_SPREADSHEET_ID
            or type(body["replies"]) is not list or body["replies"] != [{}]
            or ("commentUpdateState" in body
                and body["commentUpdateState"] != "NO_UPDATES_REQUESTED")):
        raise ContinuationRefused("append acknowledgement shape invalid")


def _inventory(original_dir: Path) -> dict[str, str]:
    if original_dir.is_symlink() or not original_dir.is_dir():
        raise ContinuationRefused("original incident directory missing or symlinked")
    hashes: dict[str, str] = {}
    for path in sorted(original_dir.iterdir()):
        if path.is_symlink() or not path.is_file():
            raise ContinuationRefused("original incident directory has non-file entry")
        hashes[path.name] = sha256_hex(path.read_bytes())
    return hashes


def verify_original_incident(original_dir: Path | None = None) -> tuple[FrozenMutation, dict[str, str]]:
    """Bind the exact observed first POST and prove no original continuation exists."""
    if original_dir is None:
        original_dir = ORIGINAL_EVIDENCE_DIR
    inventory = _inventory(original_dir)
    required = {"qualification-state.json", "fixture-retired.json",
                "append-1.receipt.json", "append-1.response.json", "frozen-request.json"}
    if not required <= set(inventory):
        raise ContinuationRefused("original incident evidence incomplete")
    if any(name.startswith(("post-1.", "append-2.", "post-2.")) for name in inventory):
        raise ContinuationRefused("original incident has later action evidence")
    state, _ = _read_file(original_dir / "qualification-state.json", canonical=True)
    fixture = {"spreadsheet_id": FIXTURE_SPREADSHEET_ID, "sheet_id": FIXTURE_SHEET_ID,
               "title": FIXTURE_TITLE, "range": FIXTURE_RANGE}
    if (state.get("state") != "ENGINEERING_APPEND_QUALIFICATION_FAILED"
            or state.get("failure_type") != "PaperRunnerError"
            or state.get("fixture_retired") is not True
            or type(state.get("post_dispatch_count")) is not int
            or state["post_dispatch_count"] != 1
            or type(state.get("paper_spreadsheet_mutation_count")) is not int
            or state["paper_spreadsheet_mutation_count"] != 0
            or type(state.get("study2_paper_observations")) is not int
            or state["study2_paper_observations"] != 0
            or state.get("fixture") != fixture or state.get("marker") != MARKER
            or state.get("frozen_request_identity_sha256") != FIRST_REQUEST_SHA256
            or state.get("manifest_sha256") != PAPER_MANIFEST_SHA256):
        raise ContinuationRefused("original qualification state differs")
    retired, _ = _read_file(original_dir / "fixture-retired.json", canonical=True)
    if retired.get("retired") is not True or retired.get("fixture") != fixture:
        raise ContinuationRefused("original fixture retirement evidence differs")
    receipt, _ = _read_file(original_dir / "append-1.receipt.json", canonical=True)
    response, raw = _read_file(original_dir / "append-1.response.json")
    expected_receipt = {
        "schema": "sheets-append-qualification-http-receipt-v1", "method": "POST",
        "target": MUTATION_URI, "status": 200, "transport_error": None,
        "dispatch_initiated": True, "local_send_completed": True,
        "body_sha256": FIRST_RESPONSE_SHA256,
        "request_identity_sha256": FIRST_REQUEST_SHA256,
    }
    if receipt != expected_receipt or sha256_hex(raw) != FIRST_RESPONSE_SHA256:
        raise ContinuationRefused("first append receipt or response hash differs")
    if response.get("commentUpdateState") != "NO_UPDATES_REQUESTED":
        raise ContinuationRefused("first append documented state differs")
    request = load_original(original_dir / "frozen-request.json")
    if (request.identity_hash != FIRST_REQUEST_SHA256 or request.method != "POST"
            or request.uri != MUTATION_URI or request.headers != APPLICATION_HEADERS
            or canonical_json_bytes(_parse(request.body)) != request.body):
        raise ContinuationRefused("stored frozen mutation differs")
    validate_documented_acknowledgement(request,
        PaperHTTPResult(DispatchFacts(True, True, 200), raw, None))
    return request, inventory


def _write(path: Path, value: Any) -> str:
    raw = value if type(value) is bytes else canonical_json_bytes(value)
    with path.open("xb") as file:
        file.write(raw)
        file.flush()
        os.fsync(file.fileno())
    return sha256_hex(raw)


def _capture(evidence_dir: Path, name: str, result: PaperHTTPResult, *,
             method: str, target: str, bearer: str,
             request_sha: str | None = None) -> None:
    if type(result) is not PaperHTTPResult or type(result.body) is not bytes:
        raise ContinuationRefused("transport result malformed")
    if bearer.encode("utf-8") in result.body:
        raise ContinuationRefused("provider response contains resident bearer")
    body_sha = _write(evidence_dir / f"{name}.response.json", result.body)
    receipt = {"schema": "sheets-append-continuation-http-receipt-v1",
               "method": method, "target": target, "status": result.facts.http_status,
               "transport_error": result.transport_error,
               "dispatch_initiated": result.facts.initiated,
               "local_send_completed": result.facts.local_send_completed,
               "body_sha256": body_sha}
    if request_sha is not None:
        receipt["request_identity_sha256"] = request_sha
    _write(evidence_dir / f"{name}.receipt.json", receipt)


def _fixture_arm() -> dict[str, Any]:
    return {"spreadsheet_id": FIXTURE_SPREADSHEET_ID, "sheet_id": FIXTURE_SHEET_ID,
            "tab_title": FIXTURE_TITLE, "range": FIXTURE_RANGE,
            "read_target": read_target(FIXTURE_SPREADSHEET_ID, FIXTURE_TITLE),
            "arm_marker": MARKER}


def _require_grid(result: PaperHTTPResult, arm: dict[str, Any],
                  expected: tuple[int, ...]) -> str:
    if (type(result) is not PaperHTTPResult or result.transport_error is not None
            or result.facts != DispatchFacts(True, True, 200)):
        raise ContinuationRefused("full-grid GET failed")
    observation = check_grid({"spreadsheet_id": FIXTURE_SPREADSHEET_ID}, arm,
                             200, result.body, intended=(ITEM, DETAIL))
    if (observation.entered_rows != expected
            or observation.marker_rows != expected
            or observation.matching_intended_rows != expected
            or observation.unexpected_rows or observation.attributable_unintended_rows
            or any(observation.rows[i] != ROW for i in expected)):
        raise ContinuationRefused("retired fixture row placement or contents differ")
    classification = evaluate_observation(observation, authority_qualified=True)
    if classification != ("EXACTLY_ONE" if expected == (0,) else "DUPLICATE"):
        raise ContinuationRefused("retired fixture classification differs")
    return classification


def run_continuation(*, client_path: Path, evidence_dir: Path, expected_head: str,
                     execute: bool, confirmation: str,
                     acquire_token: Callable[..., PreparedToken] = acquire_resident_token,
                     sheets_transport: Callable[..., PaperHTTPResult] = one_shot_request,
                     wall_clock: Callable[[], float] = time.time,
                     monotonic: Callable[[], float] = time.monotonic) -> str:
    if execute is not True or confirmation != CONTINUATION_CONFIRMATION:
        raise ContinuationRefused("explicit one-time continuation confirmation required")
    required_evidence_dir = ORIGINAL_EVIDENCE_DIR.parent / (ORIGINAL_EVIDENCE_DIR.name + "-continuation")
    if evidence_dir.resolve() != required_evidence_dir.resolve():
        raise ContinuationRefused("continuation evidence path must be the fixed one-time sibling")
    if evidence_dir.exists() or evidence_dir.is_symlink():
        raise ContinuationRefused("continuation evidence directory must be fresh")
    if evidence_dir.resolve().is_relative_to(ORIGINAL_EVIDENCE_DIR.resolve()):
        raise ContinuationRefused("continuation evidence cannot be inside original incident")
    verify_repository_state(expected_head=expected_head)
    original, original_inventory = verify_original_incident()
    token = acquire_token(client_path)
    if (type(token) is not PreparedToken
            or token.expires_at - wall_clock() <= 150 + token.clock_uncertainty_seconds):
        raise ContinuationRefused("resident drive.file token insufficient")
    evidence_dir.mkdir(mode=0o700, parents=True)
    state: dict[str, Any] = {
        "schema": "sheets-append-qualification-continuation-state-v1",
        "state": "IN_PROGRESS", "original_evidence_directory": str(ORIGINAL_EVIDENCE_DIR),
        "original_evidence_inventory": original_inventory,
        "original_evidence_inventory_sha256": sha256_hex(canonical_json_bytes(original_inventory)),
        "first_post_request_identity_sha256": FIRST_REQUEST_SHA256,
        "first_post_http_status": 200, "continuation_post_dispatch_count": 0,
        "fixture_retired": True, "cleanup_performed": False,
        "paper_spreadsheet_mutation_count": 0, "study2_paper_observations": 0,
    }
    _write(evidence_dir / "continuation-intent.json", {
        "schema": "sheets-append-qualification-continuation-intent-v1",
        "expected_head": expected_head, "original_evidence_directory": str(ORIGINAL_EVIDENCE_DIR),
        "original_evidence_inventory_sha256": state["original_evidence_inventory_sha256"],
        "fixture_spreadsheet_id": FIXTURE_SPREADSHEET_ID,
        "frozen_request_identity_sha256": FIRST_REQUEST_SHA256,
        "confirmation": CONTINUATION_CONFIRMATION,
        "planned_additional_post_count": 1,
    })
    arm = _fixture_arm()
    target = arm["read_target"]
    try:
        pre = sheets_transport(method="GET", target=target, body=b"", bearer=token.value,
                               spreadsheet_id=FIXTURE_SPREADSHEET_ID,
                               max_response_bytes=MAX_READ_BYTES)
        _capture(evidence_dir, "pre-replay", pre, method="GET", target=target,
                 bearer=token.value)
        _require_grid(pre, arm, (0,))
        state["first_post_current_state_row"] = 1
        state["first_post_visibility_within_40_seconds_proven"] = False
        # Re-read the original bytes, then check the entire original inventory
        # before any continuation POST. Nothing writes to the original directory.
        loaded = load_original(ORIGINAL_EVIDENCE_DIR / "frozen-request.json")
        if (loaded != original or loaded.identity_hash != FIRST_REQUEST_SHA256
                or _inventory(ORIGINAL_EVIDENCE_DIR) != original_inventory):
            raise ContinuationRefused("original incident evidence changed")
        replayed = replay_request(loaded)
        if (replayed is not loaded or replayed.method != original.method
                or replayed.uri != original.uri or replayed.headers != original.headers
                or replayed.body != original.body
                or replayed.identity_hash != FIRST_REQUEST_SHA256
                or replayed.uri != MUTATION_URI or PAPER_SPREADSHEET_ID in replayed.uri):
            raise ContinuationRefused("stored replay is not byte-identical")
        _write(evidence_dir / "loaded-frozen-request.json", {
            "schema": "sheets-append-continuation-loaded-frozen-request-v1",
            "method": replayed.method, "uri": replayed.uri,
            "headers": [list(pair) for pair in replayed.headers],
            "body_hex": replayed.body.hex(), "identity_sha256": replayed.identity_hash,
            "source_original_frozen_request_sha256": original_inventory["frozen-request.json"],
        })
        state["continuation_post_dispatch_count"] = 1
        second = sheets_transport(method=replayed.method, target=replayed.uri,
                                  body=replayed.body, bearer=token.value,
                                  spreadsheet_id=FIXTURE_SPREADSHEET_ID,
                                  max_response_bytes=131072,
                                  application_headers=replayed.headers,
                                  timeout_seconds=30, allow_mutation=True)
        _capture(evidence_dir, "append-2", second, method="POST", target=replayed.uri,
                 request_sha=replayed.identity_hash, bearer=token.value)
        validate_documented_acknowledgement(replayed, second)
        acknowledged_at = monotonic()
        post = sheets_transport(method="GET", target=target, body=b"", bearer=token.value,
                                spreadsheet_id=FIXTURE_SPREADSHEET_ID,
                                max_response_bytes=MAX_READ_BYTES)
        _capture(evidence_dir, "post-2", post, method="GET", target=target,
                 bearer=token.value)
        _require_grid(post, arm, (0, 1))
        elapsed = monotonic() - acknowledged_at
        state["second_append_visibility_seconds"] = elapsed
        if elapsed < 0 or elapsed > 40:
            raise ContinuationRefused("second append visibility exceeded 40 seconds")
        state.update(state=SUCCESS,
                     second_post_request_identity_sha256=replayed.identity_hash,
                     first_second_request_identity_equal=True,
                     final_duplicate_rows=[1, 2])
        if _inventory(ORIGINAL_EVIDENCE_DIR) != original_inventory:
            raise ContinuationRefused("original incident evidence changed after replay")
        _write(evidence_dir / "continuation-state.json", state)
        return SUCCESS
    except Exception as exc:
        state["state"] = "ENGINEERING_APPEND_QUALIFICATION_CONTINUATION_FAILED"
        state["failure_type"] = type(exc).__name__
        if not (evidence_dir / "continuation-state.json").exists():
            _write(evidence_dir / "continuation-state.json", state)
        raise
    finally:
        token = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args(argv)
    try:
        state = run_continuation(client_path=args.client, evidence_dir=args.evidence_dir,
                                 expected_head=args.expected_head, execute=args.execute,
                                 confirmation=args.confirmation)
        print(state)
        return 0
    except Exception as exc:
        print(f"Append continuation refused: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
