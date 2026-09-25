"""Pure, read-only validation of later Sheets paper readiness observations.

Callers must supply captured provider GET responses. This module has no
credential, network, mutation, or OAuth path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import quote

from retry_semantics.study2.sheets_paper_materialize import (
    IMPLEMENTATION_PATHS, MANIFEST_PATH, MAX_READ_BYTES, REPOSITORY_ROOT,
    SheetsPaperMaterializationError, _parse, read_target,
)
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_blank_readiness import (
    BlankReadinessError, check_all_precollection_blanks,
)

METADATA_FIELDS = ("spreadsheetId,properties(title),sheets(properties(sheetId,"
                   "title,sheetType,gridProperties(rowCount,columnCount)),"
                   "merges,tables,basicFilter,protectedRanges)")


class PaperReadinessError(ValueError):
    """A provider observation is incomplete or contradicts frozen scope."""


@dataclass(frozen=True, slots=True)
class GridObservation:
    rows: tuple[tuple[str | None, str | None, str | None], ...]
    entered_rows: tuple[int, ...]
    marker_rows: tuple[int, ...]
    matching_intended_rows: tuple[int, ...]
    attributable_unintended_rows: tuple[int, ...]
    unexpected_rows: tuple[int, ...]


def metadata_target(spreadsheet_id: str) -> str:
    """One spreadsheet metadata GET, with no includeGridData or write method."""
    return (f"/v4/spreadsheets/{quote(spreadsheet_id, safe='')}?"
            f"fields={quote(METADATA_FIELDS, safe='')}")


def _body(status: int, raw: bytes, cap: int) -> dict[str, Any]:
    if type(status) is not int or status != 200 or type(raw) is not bytes or len(raw) > cap:
        raise PaperReadinessError("non-200 or oversized provider response")
    try:
        value = _parse(raw)
    except SheetsPaperMaterializationError as exc:
        raise PaperReadinessError("invalid provider JSON") from exc
    if type(value) is not dict:
        raise PaperReadinessError("provider response is not an object")
    return value


def check_topology(manifest: dict[str, Any], status: int, raw: bytes) -> None:
    """Require the observed entire spreadsheet to match all 256 bound GRID tabs."""
    body = _body(status, raw, MAX_READ_BYTES)
    if set(body) != {"spreadsheetId", "properties", "sheets"}:
        raise PaperReadinessError("unexpected topology response fields")
    arms = [arm for family in manifest["families"] for arm in family["arms"]]
    expected = {arm["tab_title"]: arm["sheet_id"] for arm in arms}
    if (len(arms) != 256 or len(expected) != 256 or body.get("spreadsheetId") != manifest["spreadsheet_id"]
            or type(body.get("properties")) is not dict
            or body["properties"].get("title") != manifest["spreadsheet_title"]
            or type(body.get("sheets")) is not list or len(body["sheets"]) != 256):
        raise PaperReadinessError("spreadsheet identity or sheet count mismatch")
    found: dict[str, int] = {}
    ids: set[int] = set()
    for sheet in body["sheets"]:
        if type(sheet) is not dict or type(sheet.get("properties")) is not dict:
            raise PaperReadinessError("malformed sheet metadata")
        props = sheet["properties"]
        title, sheet_id = props.get("title"), props.get("sheetId")
        if (type(title) is not str or title not in expected or title in found
                or type(sheet_id) is not int or sheet_id < 0 or sheet_id in ids
                or expected[title] != sheet_id or props.get("sheetType") != "GRID"
                or type(props.get("gridProperties")) is not dict
                or props["gridProperties"].get("rowCount") != 100
                or type(props["gridProperties"].get("rowCount")) is not int
                or props["gridProperties"].get("columnCount") != 3
                or type(props["gridProperties"].get("columnCount")) is not int
                or sheet.get("merges") or sheet.get("tables")
                or sheet.get("basicFilter") or sheet.get("protectedRanges")):
            raise PaperReadinessError("sheet identity, extent, or structure mismatch")
        found[title] = sheet_id
        ids.add(sheet_id)
    if found != expected or len(ids) != 256:
        raise PaperReadinessError("missing, extra, or duplicate scope sheet")


def check_grid(manifest: dict[str, Any], arm: dict[str, Any], status: int,
               raw: bytes, *, intended: tuple[str, str] | None = None) -> GridObservation:
    """Scan one complete bounded GET; absent data never counts as blank."""
    if (arm["spreadsheet_id"] != manifest["spreadsheet_id"]
            or arm["read_target"] != read_target(arm["spreadsheet_id"], arm["tab_title"])
            or arm["range"] != "A1:C100"):
        raise PaperReadinessError("arm read identity changed")
    body = _body(status, raw, MAX_READ_BYTES)
    if set(body) != {"spreadsheetId", "sheets"}:
        raise PaperReadinessError("unexpected selected-grid response fields")
    if body.get("spreadsheetId") != arm["spreadsheet_id"] or type(body.get("sheets")) is not list or len(body["sheets"]) != 1:
        raise PaperReadinessError("selected-grid identity mismatch")
    sheet = body["sheets"][0]
    if (type(sheet) is not dict or not {"properties", "data"} <= set(sheet)
            or not set(sheet) <= {"properties", "data", "merges", "tables"}
            or type(sheet.get("properties")) is not dict):
        raise PaperReadinessError("malformed selected sheet")
    props = sheet["properties"]
    if (set(props) != {"sheetId", "title", "sheetType", "gridProperties"}
            or type(props.get("sheetId")) is not int or props["sheetId"] != arm["sheet_id"]
            or props.get("title") != arm["tab_title"] or props.get("sheetType") != "GRID"
            or type(props.get("gridProperties")) is not dict
            or type(props["gridProperties"].get("rowCount")) is not int
            or props["gridProperties"].get("rowCount") != 100
            or type(props["gridProperties"].get("columnCount")) is not int
            or props["gridProperties"].get("columnCount") != 3
            or set(props["gridProperties"]) != {"rowCount", "columnCount"}
            or sheet.get("merges") or sheet.get("tables")):
        raise PaperReadinessError("selected-grid shape changed")
    data = sheet.get("data")
    if type(data) is not list or len(data) != 1 or type(data[0]) is not dict:
        raise PaperReadinessError("absent or multiple grid data blocks")
    grid = data[0]
    if (not set(grid) <= {"startRow", "startColumn", "rowData"}
            or type(grid.get("startRow", 0)) is not int or grid.get("startRow", 0) != 0
            or type(grid.get("startColumn", 0)) is not int or grid.get("startColumn", 0) != 0
            or type(grid.get("rowData", [])) is not list or len(grid.get("rowData", [])) > 100):
        raise PaperReadinessError("incomplete or out-of-range grid data")
    rows: list[tuple[str | None, str | None, str | None]] = []
    entered, marked, matching, unintended, unexpected = [], [], [], [], []
    for index, row in enumerate(grid.get("rowData", [])):
        if (type(row) is not dict or not set(row) <= {"values"}
                or type(row.get("values", [])) is not list or len(row.get("values", [])) > 3):
            raise PaperReadinessError("malformed row")
        values: list[str | None] = []
        for cell in row.get("values", []):
            if (type(cell) is not dict or not set(cell) <= {"userEnteredValue"}
                    or type(cell.get("userEnteredValue", {})) is not dict):
                raise PaperReadinessError("malformed cell")
            entry = cell.get("userEnteredValue", {})
            if entry and (set(entry) != {"stringValue"} or type(entry.get("stringValue")) is not str
                          or len(entry["stringValue"]) > 160
                          or any(0xD800 <= ord(c) <= 0xDFFF for c in entry["stringValue"])):
                raise PaperReadinessError("nonliteral or oversized entered value")
            values.append(entry.get("stringValue"))
        values.extend([None] * (3 - len(values)))
        triple = (values[0], values[1], values[2])
        rows.append(triple)
        if any(x is not None for x in triple):
            entered.append(index)
        if triple[0] == arm["arm_marker"]:
            marked.append(index)
            if (type(triple[1]) is not str or not triple[1]
                    or type(triple[2]) is not str or not triple[2]):
                raise PaperReadinessError("marked row lacks literal semantic pair")
            if intended is not None:
                (matching if triple[1:] == intended else unintended).append(index)
        elif any(x is not None for x in triple):
            unexpected.append(index)
    return GridObservation(tuple(rows), tuple(entered), tuple(marked),
                           tuple(matching), tuple(unintended), tuple(unexpected))


def check_blank_baselines(manifest: dict[str, Any],
                          responses: dict[str, tuple[str, str, int, bytes]]) -> None:
    """Apply prospective readiness-only blank rule, never the OBS-1 evaluator."""
    try:
        check_all_precollection_blanks(manifest, responses)
    except BlankReadinessError as exc:
        raise PaperReadinessError("pre-collection blank baseline failed") from exc


def readiness_requirements() -> tuple[str, ...]:
    """Non-GET controls require independent evidence; never infer them from blank GETs."""
    return ("same_app_and_principal_access", "writer_exclusion", "no_scripts_or_external_writers",
            "no_formula_protection_or_structural_edit", "marker_round_trip_and_collision_refusal",
            "append_placement_and_duplicate_preservation", "post_write_visibility",
            "observer_authority", "token_lifetime", "quota_and_timing_feasibility")


CONTROL_FACTS = {
    "same_app_and_principal_access": {"app_id", "principal_id", "drive_file_grant"},
    "writer_exclusion": {"writer_inventory", "exclusive_writer_control"},
    "no_scripts_or_external_writers": {"script_inventory", "external_writer_inventory"},
    "no_formula_protection_or_structural_edit": {"formula_scan", "protection_scan", "structure_lock"},
    "marker_round_trip_and_collision_refusal": {"qualification_scope", "marker_readback", "collision_check"},
    "append_placement_and_duplicate_preservation": {"qualification_scope", "placement", "duplicate_readback"},
    "post_write_visibility": {"qualification_scope", "visibility_timing"},
    "observer_authority": {"complete_grid_read", "read_identity"},
    "token_lifetime": {"token_expiry", "planned_run_end"},
    "quota_and_timing_feasibility": {"quota_snapshot", "request_budget", "timing_budget"},
}

READINESS_LOCK_PATH = Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_READINESS_LOCK_V1.json")


def _durable_json(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise PaperReadinessError("missing or symlinked durable evidence")
    raw = path.read_bytes()
    if len(raw) > MAX_READ_BYTES:
        raise PaperReadinessError("oversized evidence")
    try:
        value = _parse(raw)
    except SheetsPaperMaterializationError as exc:
        raise PaperReadinessError("malformed evidence") from exc
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise PaperReadinessError("noncanonical evidence")
    return value, sha256_hex(raw)


def check_readiness_structure(manifest: dict[str, Any], *,
                              topology_response: tuple[int, bytes],
                              baseline_responses: dict[str, tuple[str, str, int, bytes]],
                              control_evidence: dict[str, dict[str, Any]],
                              evidence_root: Path = Path(".")) -> dict[str, str]:
    """Validate provider GETs and hash-bound control evidence bytes.

    Structural validation does not establish independent control authority.
    """
    check_topology(manifest, *topology_response)
    check_blank_baselines(manifest, baseline_responses)
    if type(control_evidence) is not dict or set(control_evidence) != set(readiness_requirements()):
        raise PaperReadinessError("non-GET control evidence incomplete")
    if len({entry.get("file") for entry in control_evidence.values()
            if type(entry) is dict}) != len(control_evidence):
        raise PaperReadinessError("duplicated control evidence file")
    subject = {"spreadsheet_id": manifest["spreadsheet_id"],
               "manifest_sha256": sha256_hex(canonical_json_bytes(manifest))}
    actual = {}
    for name in readiness_requirements():
        entry = control_evidence[name]
        if (type(entry) is not dict or set(entry) != {"file", "sha256"}
                or type(entry["file"]) is not str or not entry["file"].endswith(".json")
                or "/" in entry["file"] or "\\" in entry["file"]
                or entry["file"] in (".", "..") or type(entry["sha256"]) is not str):
            raise PaperReadinessError(f"unqualified control: {name}")
        value, digest = _durable_json(evidence_root / entry["file"])
        if (digest != entry["sha256"]
                or set(value) != {"schema", "control", "subject", "qualified", "facts"}
                or value["schema"] != "sheets-paper-readiness-control-evidence-v1"
                or value["control"] != name or value["subject"] != subject
                or value["qualified"] is not True or type(value["facts"]) is not dict
                or set(value["facts"]) != CONTROL_FACTS[name]
                or any(v is None or v is False or v == "" for v in value["facts"].values())):
            raise PaperReadinessError(f"unqualified control: {name}")
        actual[name] = digest
    return actual


def _require_clean_committed_lock(root: Path, manifest: dict[str, Any]) -> None:
    """The later lock is trusted through a reviewed, clean repository commit."""
    try:
        def git(*args: str) -> bytes:
            return subprocess.run(["/usr/bin/git", "-c", "core.fsmonitor=false",
                                   "-c", "core.untrackedCache=false", *args],
                                  cwd=root, capture_output=True, check=True).stdout
        if (git("rev-parse", "--show-toplevel").decode().strip() != str(root)
                or git("status", "--porcelain", "--ignore-submodules=all")):
            raise PaperReadinessError("collection repository is not clean and committed")
        for relative in (READINESS_LOCK_PATH, MANIFEST_PATH, *IMPLEMENTATION_PATHS):
            path = root / relative
            if path.is_symlink() or path.read_bytes() != git("show", "HEAD:" + str(relative)):
                raise PaperReadinessError("collection source differs from committed review")
        if (canonical_json_bytes(manifest) != (root / MANIFEST_PATH).read_bytes()
                or type(manifest.get("implementation_sha256")) is not dict
                or set(manifest["implementation_sha256"]) != set(IMPLEMENTATION_PATHS)
                or any(sha256_hex((root / path).read_bytes()) != manifest["implementation_sha256"][path]
                       for path in IMPLEMENTATION_PATHS)):
            raise PaperReadinessError("manifest or implementation identity changed")
    except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
        raise PaperReadinessError("collection source is not committed") from exc


def qualify_readiness(manifest: dict[str, Any], *,
                      topology_response: tuple[int, bytes],
                      baseline_responses: dict[str, tuple[str, str, int, bytes]],
                      control_evidence: dict[str, dict[str, Any]],
                      evidence_root: Path, audit_receipt: Path,
                      root: Path = REPOSITORY_ROOT) -> None:
    """Final gate: actual evidence and a later, independently reviewed lock."""
    actual = check_readiness_structure(
        manifest, topology_response=topology_response,
        baseline_responses=baseline_responses,
        control_evidence=control_evidence, evidence_root=evidence_root)
    lock, _ = _durable_json(root / READINESS_LOCK_PATH)
    _require_clean_committed_lock(root, manifest)
    receipt, digest = _durable_json(audit_receipt)
    baseline_hashes = {arm_id: sha256_hex(response[3])
                       for arm_id, response in baseline_responses.items()}
    manifest_hash = sha256_hex(canonical_json_bytes(manifest))
    expected = {"manifest_sha256": manifest_hash,
                "spreadsheet_id": manifest["spreadsheet_id"],
                "topology_sha256": sha256_hex(topology_response[1]),
                "baseline_sha256": baseline_hashes,
                "control_sha256": actual}
    audit = receipt.get("independent_audit")
    if (set(receipt) != {"schema", "subject", "independent_audit",
                        "control_sha256", "topology_sha256", "baseline_sha256"}
            or receipt["schema"] != "sheets-paper-readiness-audit-receipt-v1"
            or receipt["subject"] != {"manifest_sha256": manifest_hash,
                                      "spreadsheet_id": manifest["spreadsheet_id"]}
            or type(audit) is not dict
            or set(audit) != {"auditor_id", "audit_report_sha256", "audit_report_file",
                              "audited_at_utc"}
            or type(audit["auditor_id"]) is not str or not audit["auditor_id"]
            or type(audit["audit_report_file"]) is not str
            or re.fullmatch(r"[A-Za-z0-9_.-]+", audit["audit_report_file"]) is None
            or audit["audit_report_file"] in (".", "..")
            or type(audit["audit_report_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", audit["audit_report_sha256"]) is None
            or type(audit["audited_at_utc"]) is not str or not audit["audited_at_utc"]
            or receipt["control_sha256"] != actual
            or receipt["topology_sha256"] != expected["topology_sha256"]
            or receipt["baseline_sha256"] != baseline_hashes):
        raise PaperReadinessError("invalid or unaudited readiness receipt")
    report_path = audit_receipt.parent / audit["audit_report_file"]
    if (report_path.is_symlink() or not report_path.is_file()
            or report_path.stat().st_size > MAX_READ_BYTES
            or sha256_hex(report_path.read_bytes()) != audit["audit_report_sha256"]):
        raise PaperReadinessError("independent audit report bytes differ")
    if (set(lock) != {"schema", "receipt_sha256", "independent_audit", *expected}
            or lock["schema"] != "sheets-paper-readiness-lock-v1"
            or lock["receipt_sha256"] != digest
            or lock["independent_audit"] != audit
            or any(lock[key] != value for key, value in expected.items())):
        raise PaperReadinessError("readiness lock does not match audited evidence")


# Legacy name is a structural parser only. It cannot authorize collection.
check_readiness = check_readiness_structure
