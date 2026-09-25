"""Hostile offline checks for post-audit implementation repairs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import runpy

import pytest

_CAPTURE = runpy.run_path(str(Path(__file__).resolve().parents[1]
                            / "scripts/check_sheets_paper_live_readiness.py"))
preflight_capture = _CAPTURE["preflight_capture"]
run_capture = _CAPTURE["run_capture"]
READ_INTERVAL_SECONDS = _CAPTURE["READ_INTERVAL_SECONDS"]
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_paper_http as paper_http
from retry_semantics.study2.sheets_paper_adapter import DispatchFacts, prepare_paper_append
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest
from retry_semantics.study2.sheets_paper_readiness import PaperReadinessError
from retry_semantics.study2.sheets_paper_runner import (
    ModelDecision, PaperRunnerError, certify_h1_constructor, dispatch_stage, run_recovery,
    store_original, validate_append_acknowledgement,
)


@pytest.fixture(scope="module")
def manifest():
    return load_paper_manifest()


def _arm(manifest, *, world="H1", policy="LLM_REGENERATION"):
    family = manifest["families"][0]
    return family, next(a for a in family["arms"]
                        if a["hidden_world"] == world and a["policy"] == policy)


@pytest.mark.parametrize("failure,expected", [
    ("putrequest", "DISPATCH_NOT_INITIATED"),
    ("putheader", "DISPATCH_NOT_INITIATED"),
    ("endheaders", "DISPATCH_INITIATED_LOCAL_SEND_INCOMPLETE"),
    ("getresponse", "LOCAL_SEND_COMPLETE_ACK_AMBIGUOUS"),
])
def test_dispatch_boundary_after_connect(monkeypatch, manifest, failure, expected):
    _, arm = _arm(manifest)
    stages = []

    class FakeConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def connect(self):
            stages.append("connected")

        def putrequest(self, *_args, **_kwargs):
            if failure == "putrequest":
                raise OSError("synthetic")

        def putheader(self, *_args):
            if failure == "putheader":
                raise OSError("synthetic")

        def endheaders(self, *_args, **_kwargs):
            if failure == "endheaders":
                raise OSError("synthetic")

        def getresponse(self):
            raise OSError("synthetic")

        def close(self):
            pass

    monkeypatch.setattr(paper_http.http.client, "HTTPSConnection", FakeConnection)
    result = paper_http.one_shot_request(
        method="GET", target=arm["read_target"], body=b"", bearer="synthetic",
        spreadsheet_id=arm["spreadsheet_id"], max_response_bytes=1024)
    assert stages == ["connected"]
    assert dispatch_stage(result.facts) == expected
    assert result.transport_error == "OSError"


def _metadata(manifest):
    arms = [a for f in manifest["families"] for a in f["arms"]]
    props = lambda a: {"sheetId": a["sheet_id"], "title": a["tab_title"],
                       "sheetType": "GRID", "gridProperties": {"rowCount": 100,
                                                               "columnCount": 3}}
    topology = {"spreadsheetId": manifest["spreadsheet_id"],
                "properties": {"title": manifest["spreadsheet_title"]},
                "sheets": [{"properties": props(a)} for a in arms]}
    return canonical_json_bytes(topology), {
        a["read_target"]: canonical_json_bytes({
            "spreadsheetId": manifest["spreadsheet_id"],
            "sheets": [{"properties": props(a)}]}) for a in arms}


def _token(*, expiry=10000):
    return {"schema": "sheets-paper-prepared-token-v1",
            "bearer_sha256": sha256_hex(b"synthetic"), "expires_at": expiry,
            "clock_uncertainty_seconds": 1.0}


class Clock:
    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

    def sleep(self, duration):
        assert duration >= 0
        self.value += duration


def test_readiness_preflight_refuses_before_dispatch(tmp_path, manifest):
    calls = []
    with pytest.raises(PaperReadinessError, match="cannot cover"):
        run_capture(manifest=manifest, bearer="synthetic", evidence_dir=tmp_path / "short",
                    token_metadata=_token(expiry=100), wall_clock=lambda: 0,
                    transport=lambda **kwargs: calls.append(kwargs))
    assert not calls and not (tmp_path / "short").exists()
    assert preflight_capture(manifest=manifest, token_metadata=_token(),
                             bearer="synthetic", now=0) > 600


def test_readiness_fixed_pacing_and_no_retry(tmp_path, manifest):
    topology, grids = _metadata(manifest)
    clock = Clock()
    starts = []

    def transport(**kwargs):
        starts.append(clock.now())
        target = kwargs["target"]
        body = grids.get(target, topology)
        return PaperHTTPResult(DispatchFacts(True, True, 200), body, None)

    state = run_capture(manifest=manifest, bearer="synthetic",
                        evidence_dir=tmp_path / "good", token_metadata=_token(),
                        wall_clock=clock.now, monotonic=clock.now, sleep=clock.sleep,
                        transport=transport)
    assert state == "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"
    assert len(starts) == 257
    assert all(abs(start - index * READ_INTERVAL_SECONDS) < 1e-8
               for index, start in enumerate(starts))
    assert (tmp_path / "good" / "capture-state.json").is_file()

    clock = Clock()
    starts = []

    def rejected(**kwargs):
        starts.append(clock.now())
        return PaperHTTPResult(DispatchFacts(True, True, 429), b"quota", None)

    with pytest.raises(PaperReadinessError, match="failed read"):
        run_capture(manifest=manifest, bearer="synthetic",
                    evidence_dir=tmp_path / "rejected", token_metadata=_token(),
                    wall_clock=clock.now, monotonic=clock.now, sleep=clock.sleep,
                    transport=rejected)
    assert starts == [0.0]
    assert (tmp_path / "rejected" / "topology.receipt.json").is_file()
    assert not (tmp_path / "rejected" / "capture-state.json").exists()

    clock = Clock()
    starts = []

    def slow(**kwargs):
        starts.append(clock.now())
        clock.value += READ_INTERVAL_SECONDS + 1
        return PaperHTTPResult(DispatchFacts(True, True, 200), topology, None)

    with pytest.raises(PaperReadinessError, match="slot missed"):
        run_capture(manifest=manifest, bearer="synthetic",
                    evidence_dir=tmp_path / "slow", token_metadata=_token(),
                    wall_clock=clock.now, monotonic=clock.now, sleep=clock.sleep,
                    transport=slow)
    assert starts == [0.0]


def test_strict_append_ack_and_h1_certificate_revalidation(tmp_path, manifest):
    family, arm = _arm(manifest)
    semantic = family["target_semantic_m"]
    request = prepare_paper_append(arm, semantic["item"], semantic["detail"])
    good = PaperHTTPResult(DispatchFacts(True, True, 200), canonical_json_bytes({
        "spreadsheetId": arm["spreadsheet_id"], "replies": [{}]}), None)
    assert validate_append_acknowledgement(request, arm, good).acknowledgement_validated
    for body in ({"replies": [{}]},
                 {"spreadsheetId": "wrong", "replies": [{}]},
                 {"spreadsheetId": arm["spreadsheet_id"], "replies": []},
                 {"spreadsheetId": arm["spreadsheet_id"], "replies": [{"x": 1}]},
                 {"spreadsheetId": arm["spreadsheet_id"], "replies": [{}],
                  "updatedSpreadsheet": {}},
                 {"spreadsheetId": arm["spreadsheet_id"], "replies": [{}],
                  "error": {}}):
        with pytest.raises(PaperRunnerError):
            validate_append_acknowledgement(request, arm,
                replace(good, body=canonical_json_bytes(body)))
    with pytest.raises(PaperRunnerError):
        validate_append_acknowledgement(request, arm,
            replace(good, facts=DispatchFacts(True, True, 200, True, True)))
    observed = {"spreadsheetId": arm["spreadsheet_id"], "sheets": [{
        "properties": {"sheetId": arm["sheet_id"], "title": arm["tab_title"],
                       "sheetType": "GRID", "gridProperties": {"rowCount": 100,
                                                               "columnCount": 3}},
        "data": [{"rowData": [{"values": [
            {"userEnteredValue": {"stringValue": x}}
            for x in (arm["arm_marker"], semantic["item"], semantic["detail"])]}]}]}]}
    read = canonical_json_bytes(observed)
    cert = certify_h1_constructor(manifest, family, arm, request, good,
                                  ("GET", arm["read_target"], 200, read))
    with pytest.raises(PaperRunnerError):
        certify_h1_constructor(manifest, family, arm, request, good,
                               ("GET", "/wrong", 200, read))
    path = tmp_path / "original.json"
    store_original(path, request)
    kwargs = dict(manifest=manifest, family=family, arm=arm, original_path=path,
                  original_model_message=b"original", model_visible_common=manifest["model_visible_common"],
                  dispatch=lambda _: pytest.fail("should not dispatch"),
                  model_continue=lambda _: pytest.fail("should not call model"))
    for forged in (DispatchFacts(True, True, 200, True, True),
                   replace(cert, acknowledgement=replace(good, body=b'{}')),
                   replace(cert, read_capture=("GET", arm["read_target"], 200, b'{}')),
                   replace(cert, original_identity_sha256="0" * 64),
                   replace(cert, manifest_sha256="0" * 64)):
        with pytest.raises(PaperRunnerError):
            run_recovery(initial_world_facts=forged, **kwargs)


def test_regeneration_success_projection_requires_strict_ack(tmp_path, manifest):
    family, arm = _arm(manifest, world="H0")
    semantic = family["target_semantic_m"]
    path = tmp_path / "original.json"
    store_original(path, prepare_paper_append(arm, semantic["item"], semantic["detail"]))
    seen = []

    def model(context):
        seen.append(context)
        return (ModelDecision("append_row", semantic["item"], semantic["detail"])
                if len(seen) == 1 else ModelDecision("finish"))

    ack = PaperHTTPResult(DispatchFacts(True, True, 200), canonical_json_bytes({
        "spreadsheetId": arm["spreadsheet_id"], "replies": [{}]}), None)
    kwargs = dict(manifest=manifest, family=family, arm=arm,
                  original_path=path, initial_world_facts=DispatchFacts(),
                  original_model_message=b"original",
                  model_visible_common=manifest["model_visible_common"],
                  model_continue=model)
    result = run_recovery(dispatch=lambda _: ack, **kwargs)
    assert result.model_calls == 2
    assert result.actions[0].facts.acknowledgement_validated is True
    assert seen[1].previous_tool_result == {"status": "appended"}

    # Malformed acknowledgement -> never success projection
    seen.clear()
    bad = replace(ack, body=b'{"replies":[{}]}')
    result = run_recovery(dispatch=lambda _: bad, **kwargs)
    assert result.terminal_reason == "UNRESOLVED_MUTATION_OUTCOME"
    assert len(seen) == 1
    assert all(c.previous_tool_result != {"status": "appended"} for c in seen)

    # Uncertain / timeout acknowledgement -> never success projection
    seen.clear()
    uncertain = PaperHTTPResult(DispatchFacts(True, True), b"", "synthetic")
    result = run_recovery(dispatch=lambda _: uncertain, **kwargs)
    assert result.terminal_reason == "UNRESOLVED_MUTATION_OUTCOME"
    assert len(seen) == 1
    assert all(c.previous_tool_result != {"status": "appended"} for c in seen)

    # Visible non-200 failure -> never success projection
    seen.clear()
    non_200 = PaperHTTPResult(DispatchFacts(True, True, 500), b"error", None)
    result = run_recovery(dispatch=lambda _: non_200, **kwargs)
    assert result.terminal_reason == "VISIBLE_PROVIDER_FAILURE"
    assert len(seen) == 1
    assert all(c.previous_tool_result != {"status": "appended"} for c in seen)

    # Unauthorized success projection in runner -> refused
    for unauthorized in ({"status": "other"}, {}, None):
        seen.clear()
        tampered_common = {**manifest["model_visible_common"],
                           "append_row_success_projection": unauthorized}
        with pytest.raises(PaperRunnerError, match="unauthorized append success projection"):
            run_recovery(dispatch=lambda _: ack,
                         **{**kwargs, "model_visible_common": tampered_common})

