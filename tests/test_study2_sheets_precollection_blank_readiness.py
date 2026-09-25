"""Readiness-only omitted-empty acceptance; frozen OBS-1 remains strict."""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_adapter import classify_experimental_get
from retry_semantics.study2.sheets_paper_blank_readiness import (
    BlankReadinessError, check_precollection_blank,
)
from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest
from retry_semantics.study2.sheets_paper_readiness import PaperReadinessError, check_grid


@pytest.fixture(scope="module")
def scope():
    manifest = load_paper_manifest()
    return manifest, manifest["families"][0]["arms"][0]


def _body(arm, data="missing"):
    sheet = {"properties": {"sheetId": arm["sheet_id"], "title": arm["tab_title"],
                            "sheetType": "GRID", "gridProperties": {"rowCount": 100,
                                                                       "columnCount": 3}}}
    if data != "missing":
        sheet["data"] = data
    return {"spreadsheetId": arm["spreadsheet_id"], "sheets": [sheet]}


def _check(scope, body):
    manifest, arm = scope
    check_precollection_blank(manifest, arm, method="GET", target=arm["read_target"],
                              status=200, raw=canonical_json_bytes(body))


@pytest.mark.parametrize("data", [[], [{}], [{"rowData": []}],
                                  [{"startRow": 0, "startColumn": 0, "rowData": [{}]}]])
def test_readiness_explicit_empty_passes(scope, data):
    _check(scope, _body(scope[1], data))


def test_readiness_omitted_empty_passes(scope):
    _check(scope, _body(scope[1]))


@pytest.mark.parametrize("entered", [{"stringValue": ""}, {"stringValue": "x"},
                                            {"formulaValue": "=1"}, {"numberValue": 1},
                                            {"boolValue": True}, "bad"])
def test_readiness_any_entered_or_malformed_value_fails(scope, entered):
    with pytest.raises(BlankReadinessError):
        _check(scope, _body(scope[1], [{"rowData": [{"values": [
            {"userEnteredValue": entered}]}]}]))


@pytest.mark.parametrize("bad", [
    [{}, {}], [{"startRow": 1}], [{"startColumn": 1}],
    [{"rowData": [{}] * 101}], [{"rowData": [{"values": [{}] * 4}]}],
    [{"unexpected": 1}], ["bad"],
])
def test_readiness_ambiguous_grid_fails(scope, bad):
    with pytest.raises(BlankReadinessError):
        _check(scope, _body(scope[1], bad))


def test_readiness_wrong_request_identity_and_extent_fail(scope):
    manifest, arm = scope
    body = _body(arm)
    for mutation in (
        lambda x: x.update(spreadsheetId="wrong"),
        lambda x: x["sheets"][0]["properties"].update(sheetId=999999),
        lambda x: x["sheets"][0]["properties"].update(sheetType="OBJECT"),
        lambda x: x["sheets"][0]["properties"]["gridProperties"].update(rowCount=99),
    ):
        altered = copy.deepcopy(body)
        mutation(altered)
        with pytest.raises(BlankReadinessError):
            _check(scope, altered)
    for method, target, status in (("POST", arm["read_target"], 200),
                                   ("GET", "/wrong", 200),
                                   ("GET", arm["read_target"], 503)):
        with pytest.raises(BlankReadinessError):
            check_precollection_blank(manifest, arm, method=method, target=target,
                                      status=status, raw=canonical_json_bytes(body))


def test_experimental_evaluator_still_requires_data_block(scope):
    manifest, arm = scope
    omitted = canonical_json_bytes(_body(arm))
    with pytest.raises(PaperReadinessError, match="malformed selected sheet"):
        check_grid(manifest, arm, 200, omitted)
    assert classify_experimental_get(manifest, arm, 200, omitted,
                                     intended=("Blue notebook", "A compact notebook"),
                                     authority_qualified=True) == "INCOMPLETE"
    # Explicit-empty OBS-1 behavior remains exactly as frozen.
    assert check_grid(manifest, arm, 200, canonical_json_bytes(_body(arm, [{}]))).entered_rows == ()


def test_frozen_experimental_grid_parser_bytes_unchanged():
    from retry_semantics.study2 import sheets_paper_readiness as readiness
    raw = Path(readiness.__file__).read_bytes()
    node = next(n for n in ast.parse(raw).body
                if isinstance(n, ast.FunctionDef) and n.name == "check_grid")
    block = b"".join(raw.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    assert sha256_hex(block) == "c6f2c35fe0f43038f0af7e22d33bf8a506b715ec5ef0c0987504d1b5de85ed7f"
