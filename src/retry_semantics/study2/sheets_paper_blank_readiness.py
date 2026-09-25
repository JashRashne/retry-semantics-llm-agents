"""Prospective PRE-COLLECTION blank-baseline rule only.

The experimental OBS-1 evaluator retains its frozen requirement for one
explicit GridData block. This module never calls or normalizes check_grid.
"""

from __future__ import annotations

from typing import Any

from retry_semantics.study2.sheets_paper_materialize import (
    MAX_READ_BYTES, SheetsPaperMaterializationError, _parse, read_target,
)


class BlankReadinessError(ValueError):
    """A pre-collection baseline cannot be certified blank."""


def check_precollection_blank(manifest: dict[str, Any], arm: dict[str, Any],
                              *, method: str, target: str, status: int,
                              raw: bytes) -> None:
    """Accept only exact, visibly successful, structurally blank baseline GET.

    This does not produce an experimental observation or effect classification.
    """
    if (method != "GET" or target != arm.get("read_target")
            or target != read_target(arm["spreadsheet_id"], arm["tab_title"])
            or arm["spreadsheet_id"] != manifest["spreadsheet_id"]
            or arm["range"] != "A1:C100" or type(status) is not int
            or status != 200 or type(raw) is not bytes or len(raw) > MAX_READ_BYTES):
        raise BlankReadinessError("request or visible response is not exact")
    try:
        body = _parse(raw)
    except SheetsPaperMaterializationError as exc:
        raise BlankReadinessError("malformed provider JSON") from exc
    if (type(body) is not dict or set(body) != {"spreadsheetId", "sheets"}
            or body["spreadsheetId"] != arm["spreadsheet_id"]
            or type(body["sheets"]) is not list or len(body["sheets"]) != 1):
        raise BlankReadinessError("wrong spreadsheet or sheet selection")
    sheet = body["sheets"][0]
    if (type(sheet) is not dict or "properties" not in sheet
            or not set(sheet) <= {"properties", "data", "merges", "tables"}
            or ("merges" in sheet and sheet["merges"] != [])
            or ("tables" in sheet and sheet["tables"] != [])):
        raise BlankReadinessError("unexpected sheet structure")
    props = sheet["properties"]
    if (type(props) is not dict
            or set(props) != {"sheetId", "title", "sheetType", "gridProperties"}
            or type(props["sheetId"]) is not int or props["sheetId"] != arm["sheet_id"]
            or props["title"] != arm["tab_title"] or props["sheetType"] != "GRID"):
        raise BlankReadinessError("wrong sheet identity")
    extent = props["gridProperties"]
    if (type(extent) is not dict or set(extent) != {"rowCount", "columnCount"}
            or type(extent["rowCount"]) is not int or extent["rowCount"] != 100
            or type(extent["columnCount"]) is not int or extent["columnCount"] != 3):
        raise BlankReadinessError("wrong grid extent")
    # Empty fields can be omitted by the provider for this exact GET. The
    # omitted/default representation is accepted only in this readiness path.
    grids = sheet.get("data", [])
    if type(grids) is not list or len(grids) > 1:
        raise BlankReadinessError("conflicting GridData")
    grid = grids[0] if grids else {}
    if (type(grid) is not dict or not set(grid) <= {"startRow", "startColumn", "rowData"}
            or type(grid.get("startRow", 0)) is not int or grid.get("startRow", 0) != 0
            or type(grid.get("startColumn", 0)) is not int or grid.get("startColumn", 0) != 0):
        raise BlankReadinessError("offset or malformed GridData")
    rows = grid.get("rowData", [])
    if type(rows) is not list or len(rows) > 100:
        raise BlankReadinessError("malformed row count")
    for row in rows:
        if type(row) is not dict or not set(row) <= {"values"}:
            raise BlankReadinessError("malformed row")
        cells = row.get("values", [])
        if type(cells) is not list or len(cells) > 3:
            raise BlankReadinessError("malformed column count")
        for cell in cells:
            if type(cell) is not dict or not set(cell) <= {"userEnteredValue"}:
                raise BlankReadinessError("malformed cell")
            entered = cell.get("userEnteredValue", {})
            if type(entered) is not dict or entered:
                raise BlankReadinessError("entered value or malformed value")


def check_all_precollection_blanks(manifest: dict[str, Any],
                                   responses: dict[str, tuple[str, str, int, bytes]]) -> None:
    arms = [arm for family in manifest["families"] for arm in family["arms"]]
    if type(responses) is not dict or set(responses) != {arm["arm_id"] for arm in arms}:
        raise BlankReadinessError("incomplete baseline set")
    for arm in arms:
        captured = responses[arm["arm_id"]]
        if type(captured) is not tuple or len(captured) != 4:
            raise BlankReadinessError("malformed baseline capture")
        method, target, status, raw = captured
        check_precollection_blank(manifest, arm, method=method, target=target,
                                  status=status, raw=raw)
