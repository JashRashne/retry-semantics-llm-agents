"""Adversarial offline checks for actual scope materialization and read parsing."""

from __future__ import annotations

import json
import shutil

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_adapter import (
    DispatchFacts, PaperAdapterError, evaluate_observation, prepare_paper_append,
    project_list_rows, replay_request,
)
from retry_semantics.study2.sheets_paper_materialize import (
    BINDING_PATH, EVIDENCE_ROOT, MANIFEST_PATH, REPOSITORY_ROOT,
    SheetsPaperMaterializationError, build_paper_manifest, build_scope_binding,
    load_paper_manifest, load_scope_binding,
)
from retry_semantics.study2.sheets_paper_readiness import (
    PaperReadinessError, check_blank_baselines, check_grid, check_readiness,
    check_topology,
)


@pytest.fixture(scope="module")
def manifest():
    return load_paper_manifest()


def _arm(manifest):
    return manifest["families"][0]["arms"][0]


def _grid(arm, *, rows=None, data=True):
    sheet = {"properties": {"sheetId": arm["sheet_id"], "title": arm["tab_title"],
                            "sheetType": "GRID", "gridProperties": {"rowCount": 100,
                                                                       "columnCount": 3}}}
    if data:
        sheet["data"] = [{"startRow": 0, "startColumn": 0, "rowData": rows or []}]
    return canonical_json_bytes({"spreadsheetId": arm["spreadsheet_id"], "sheets": [sheet]})


def _row(*values):
    return {"values": [{"userEnteredValue": {"stringValue": value}} for value in values]}


def test_actual_binding_and_manifest_are_reproducible(manifest):
    assert (REPOSITORY_ROOT / BINDING_PATH).read_bytes() == build_scope_binding()
    assert (REPOSITORY_ROOT / MANIFEST_PATH).read_bytes() == build_paper_manifest()
    binding = load_scope_binding()
    assert len(binding["arms"]) == 256
    assert len({row["sheet_id"] for row in binding["arms"]}) == 256
    assert len(manifest["families"]) == 64
    assert {arm["range"] for family in manifest["families"] for arm in family["arms"]} == {"A1:C100"}
    assert [family["family_id"] for family in manifest["families"]] == [
        f"sheets-f{i:03d}" for i in range(1, 65)]
    assert [arm["policy"] for arm in manifest["families"][0]["arms"]] == [
        "EXACT_REPLAY", "LLM_REGENERATION", "LLM_REGENERATION", "EXACT_REPLAY"]


@pytest.mark.parametrize("file,change", [
    ("create-intent.json", lambda x: x.update(expected_tab_count=255)),
    ("create-dispatch.json", lambda x: x.update(intent_sha256="0" * 64)),
    ("create-result.json", lambda x: x.update(http_status=201)),
    ("create-result.json", lambda x: x["sheet_ids_by_title"].update(
        {next(iter(x["sheet_ids_by_title"])): True})),
])
def test_changed_durable_evidence_refused(tmp_path, file, change):
    for name in ("create-intent.json", "create-dispatch.json", "create-result.json"):
        shutil.copyfile(EVIDENCE_ROOT / name, tmp_path / name)
    path = tmp_path / file
    value = json.loads(path.read_bytes())
    change(value)
    path.write_bytes(canonical_json_bytes(value))
    with pytest.raises(SheetsPaperMaterializationError):
        build_scope_binding(evidence_root=tmp_path)


def test_topology_rejects_missing_extra_wrong_id_and_extent(manifest):
    arms = [arm for family in manifest["families"] for arm in family["arms"]]
    sheets = [{"properties": {"sheetId": arm["sheet_id"], "title": arm["tab_title"],
                              "sheetType": "GRID", "gridProperties": {"rowCount": 100,
                                                                         "columnCount": 3}}} for arm in arms]
    body = {"spreadsheetId": manifest["spreadsheet_id"],
            "properties": {"title": manifest["spreadsheet_title"]}, "sheets": sheets}
    check_topology(manifest, 200, canonical_json_bytes(body))
    for mutation in (lambda s: s.pop(),
                     lambda s: s[0]["properties"].update(sheetId=123456789),
                     lambda s: s[0]["properties"]["gridProperties"].update(rowCount=99),
                     lambda s: s[0].update(tables=[{"tableId": "x"}])):
        altered = json.loads(json.dumps(body))
        mutation(altered["sheets"])
        with pytest.raises(PaperReadinessError):
            check_topology(manifest, 200, canonical_json_bytes(altered))


def test_grid_blank_marker_wrong_row_and_incomplete(manifest):
    arm = _arm(manifest)
    blank = check_grid(manifest, arm, 200, _grid(arm))
    assert not blank.entered_rows
    rows = [_row(arm["arm_marker"], "Blue notebook", "wrong detail"),
            _row(arm["arm_marker"], "Blue notebook", "correct detail")]
    observation = check_grid(manifest, arm, 200, _grid(arm, rows=rows),
                             intended=("Blue notebook", "correct detail"))
    assert observation.matching_intended_rows == (1,)
    assert observation.attributable_unintended_rows == (0,)
    assert evaluate_observation(observation, authority_qualified=True) == "EXTRA_UNINTENDED_MUTATION"
    assert project_list_rows(observation, authority_qualified=True) == {
        "rows": [{"item": "Blue notebook", "detail": "wrong detail"},
                 {"item": "Blue notebook", "detail": "correct detail"}],
        "read_complete": True}
    for raw in (_grid(arm, data=False), _grid(arm, rows=[_row("")]),
                _grid(arm, rows=[{"values": [{"userEnteredValue": {"formulaValue": "=1"}}]}])):
        if raw == _grid(arm, rows=[_row("")]):
            assert check_grid(manifest, arm, 200, raw).entered_rows == (0,)
        else:
            with pytest.raises(PaperReadinessError):
                check_grid(manifest, arm, 200, raw)


def test_baselines_require_every_arm(manifest):
    with pytest.raises(PaperReadinessError):
        check_blank_baselines(manifest, {})
    with pytest.raises(PaperReadinessError):
        check_readiness(manifest, topology_response=(200, b"{}"),
                        baseline_responses={}, control_evidence={})


def test_exact_replay_and_dispatch_boundaries(manifest):
    arm = _arm(manifest)
    original = prepare_paper_append(arm, "Blue notebook", "A compact notebook")
    assert replay_request(original) is original
    assert original.body_hash == sha256_hex(original.body)
    assert b'"sheetId":' in original.body
    assert DispatchFacts(initiated=True, local_send_completed=True).target_ambiguity_open
    assert not DispatchFacts(initiated=True, http_status=500).target_ambiguity_open
    with pytest.raises(PaperAdapterError):
        DispatchFacts(local_send_completed=True)
    with pytest.raises(PaperAdapterError):
        prepare_paper_append(arm, "", "detail")


def test_duplicate_rows_count_by_coordinate_and_unmarked_row_contaminates(manifest):
    arm = _arm(manifest)
    intended = ("Blue notebook", "A compact notebook")
    matching = _row(arm["arm_marker"], *intended)
    duplicate = check_grid(manifest, arm, 200, _grid(arm, rows=[matching, matching]),
                           intended=intended)
    assert evaluate_observation(duplicate, authority_qualified=True) == "DUPLICATE"
    assert evaluate_observation(duplicate, authority_qualified=False) == "INCONCLUSIVE"
    contaminated = check_grid(manifest, arm, 200,
                              _grid(arm, rows=[matching, _row("other marker", *intended)]),
                              intended=intended)
    assert evaluate_observation(contaminated, authority_qualified=True) == "INCONCLUSIVE"
    assert project_list_rows(contaminated, authority_qualified=True) == (
        "ToolError: Row observation incomplete.")
