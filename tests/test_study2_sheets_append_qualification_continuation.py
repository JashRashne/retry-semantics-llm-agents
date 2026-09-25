"""Offline incident-continuation tests: every provider action uses fakes."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
import time
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_live_preparation import PreparedToken
from retry_semantics.study2.sheets_paper_adapter import DispatchFacts, prepare_paper_append
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
from retry_semantics.study2.sheets_paper_runner import store_original
import run_sheets_append_qualification_continuation as c

REAL_VERIFY_REPOSITORY_STATE = c.verify_repository_state

HEAD = "c5f5872b50ffa1a6031483679fff6d6646e1ec4a"
BEARER = "resident-secret-continuation-test"
REAL_RESPONSE = (
    b'{\n  "spreadsheetId": "1KZybNOl5S4Ul52yqyVmktX8JE-7zV4YqNqkuJES8_7w",'
    b'\n  "replies": [\n    {}\n  ],\n'
    b'  "commentUpdateState": "NO_UPDATES_REQUESTED"\n}\n'
)


def reply(status=200, body=None, error=None):
    raw = canonical_json_bytes(body) if type(body) is dict else (
        REAL_RESPONSE if body is None else body)
    return PaperHTTPResult(DispatchFacts(True, True, status), raw, error)


def grid(rows):
    return {"spreadsheetId": c.FIXTURE_SPREADSHEET_ID, "sheets": [{
        "properties": {"sheetId": c.FIXTURE_SHEET_ID, "title": c.FIXTURE_TITLE,
                       "sheetType": "GRID", "gridProperties": {"rowCount": 100,
                                                               "columnCount": 3}},
        "data": [{"startRow": 0, "startColumn": 0, "rowData": [
            {"values": [{"userEnteredValue": {"stringValue": value}} for value in row]}
            for row in rows]}],
    }]}


def request():
    arm = {"spreadsheet_id": c.FIXTURE_SPREADSHEET_ID,
           "sheet_id": c.FIXTURE_SHEET_ID, "arm_marker": c.MARKER}
    prepared = prepare_paper_append(arm, c.ITEM, c.DETAIL)
    assert prepared.identity_hash == c.FIRST_REQUEST_SHA256
    return prepared


def original_fixture(path):
    path.mkdir()
    fixture = {"spreadsheet_id": c.FIXTURE_SPREADSHEET_ID,
               "sheet_id": c.FIXTURE_SHEET_ID,
               "title": c.FIXTURE_TITLE, "range": c.FIXTURE_RANGE}
    state = {"state": "ENGINEERING_APPEND_QUALIFICATION_FAILED",
             "failure_type": "PaperRunnerError", "fixture_retired": True,
             "post_dispatch_count": 1, "paper_spreadsheet_mutation_count": 0,
             "study2_paper_observations": 0, "fixture": fixture,
             "marker": c.MARKER, "frozen_request_identity_sha256": c.FIRST_REQUEST_SHA256,
             "manifest_sha256": c.PAPER_MANIFEST_SHA256}
    (path / "qualification-state.json").write_bytes(canonical_json_bytes(state))
    (path / "fixture-retired.json").write_bytes(canonical_json_bytes(
        {"retired": True, "fixture": fixture}))
    assert sha256_hex(REAL_RESPONSE) == c.FIRST_RESPONSE_SHA256
    (path / "append-1.response.json").write_bytes(REAL_RESPONSE)
    receipt = {"schema": "sheets-append-qualification-http-receipt-v1",
               "method": "POST", "target": c.MUTATION_URI, "status": 200,
               "transport_error": None, "dispatch_initiated": True,
               "local_send_completed": True, "body_sha256": c.FIRST_RESPONSE_SHA256,
               "request_identity_sha256": c.FIRST_REQUEST_SHA256}
    (path / "append-1.receipt.json").write_bytes(canonical_json_bytes(receipt))
    store_original(path / "frozen-request.json", request())


class FakeTransport:
    def __init__(self, responses=None):
        self.responses = list(responses or [reply(body=grid((c.ROW,))),
                                           reply(), reply(body=grid((c.ROW, c.ROW)))])
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["bearer"] == BEARER
        assert kwargs["spreadsheet_id"] == c.FIXTURE_SPREADSHEET_ID
        assert self.responses
        return self.responses.pop(0)

    @property
    def posts(self):
        return [call for call in self.calls if call["method"] == "POST"]


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    original = tmp_path / "original"
    original_fixture(original)
    monkeypatch.setattr(c, "ORIGINAL_EVIDENCE_DIR", original)
    monkeypatch.setattr(c, "verify_repository_state", lambda **kwargs: None)

    def run(transport=None, *, times=None, **changes):
        transport = transport or FakeTransport()
        oauth = Mock(return_value=PreparedToken(BEARER, time.time() + 10_000, 1.0))
        clock = iter(times or [0.0, 1.0])
        evidence = original.parent / (original.name + "-continuation")
        params = dict(client_path=tmp_path / "client.json", evidence_dir=evidence,
                      expected_head=HEAD, execute=True,
                      confirmation=c.CONTINUATION_CONFIRMATION,
                      acquire_token=oauth, sheets_transport=transport,
                      monotonic=lambda: next(clock))
        params.update(changes)
        return transport, oauth, evidence, lambda: c.run_continuation(**params)

    return run, original


def test_exact_real_response_regression_and_absent_field_accepted():
    c.validate_documented_acknowledgement(request(), reply())
    c.validate_documented_acknowledgement(request(), reply(body={
        "spreadsheetId": c.FIXTURE_SPREADSHEET_ID, "replies": [{}]}))


@pytest.mark.parametrize("body", [
    {"spreadsheetId": c.FIXTURE_SPREADSHEET_ID, "replies": [{}],
     "commentUpdateState": "MODIFIED"},
    {"spreadsheetId": c.FIXTURE_SPREADSHEET_ID, "replies": [{}],
     "updatedSpreadsheet": {}},
    {"spreadsheetId": c.FIXTURE_SPREADSHEET_ID, "replies": []},
    {"spreadsheetId": c.FIXTURE_SPREADSHEET_ID, "replies": [{}, {}]},
    {"spreadsheetId": c.FIXTURE_SPREADSHEET_ID, "replies": [{}], "extra": True},
])
def test_documented_ack_rejects_other_shapes(body):
    with pytest.raises(c.ContinuationRefused):
        c.validate_documented_acknowledgement(request(), reply(body=body))


def test_happy_path_one_exact_stored_post_and_original_unchanged(prepared, capsys):
    run, original = prepared
    before = c._inventory(original)
    transport, oauth, evidence, invoke = run()
    assert invoke() == c.SUCCESS
    assert len(transport.posts) == 1
    post = transport.posts[0]
    frozen = request()
    assert (post["method"], post["target"], post["application_headers"], post["body"]) == (
        frozen.method, frozen.uri, frozen.headers, frozen.body)
    assert c.PAPER_SPREADSHEET_ID not in post["target"]
    assert c._inventory(original) == before
    state = json.loads((evidence / "continuation-state.json").read_bytes())
    assert state["state"] == c.SUCCESS
    assert state["first_post_http_status"] == 200
    assert state["first_post_current_state_row"] == 1
    assert state["first_post_visibility_within_40_seconds_proven"] is False
    assert state["first_second_request_identity_equal"] is True
    assert state["continuation_post_dispatch_count"] == 1
    assert state["final_duplicate_rows"] == [1, 2]
    assert state["second_append_visibility_seconds"] == 1.0
    assert state["fixture_retired"] is True and state["cleanup_performed"] is False
    assert state["paper_spreadsheet_mutation_count"] == 0
    assert state["study2_paper_observations"] == 0
    for name in ("continuation-intent", "pre-replay.response", "pre-replay.receipt",
                 "loaded-frozen-request", "append-2.response", "append-2.receipt",
                 "post-2.response", "post-2.receipt", "continuation-state"):
        assert (evidence / f"{name}.json").exists()
    assert BEARER not in "".join(path.read_text() for path in evidence.iterdir())
    assert BEARER not in capsys.readouterr().out
    oauth.assert_called_once()


def test_fixed_continuation_evidence_path_prevents_second_run(prepared):
    run, original = prepared
    first, _, evidence, invoke = run()
    assert invoke() == c.SUCCESS
    assert len(first.posts) == 1
    second, oauth, _, invoke_again = run()
    with pytest.raises(c.ContinuationRefused, match="fresh"):
        invoke_again()
    assert not second.posts
    oauth.assert_not_called()
    assert evidence == original.parent / (original.name + "-continuation")


@pytest.mark.parametrize("change", ["state", "receipt_status", "body", "later_file", "missing_frozen"])
def test_original_evidence_mismatch_refuses_before_oauth(prepared, change):
    run, original = prepared
    if change == "state":
        path = original / "qualification-state.json"
        value = json.loads(path.read_bytes())
        value["fixture_retired"] = False
        path.write_bytes(canonical_json_bytes(value))
    elif change == "receipt_status":
        path = original / "append-1.receipt.json"
        value = json.loads(path.read_bytes())
        value["status"] = 503
        path.write_bytes(canonical_json_bytes(value))
    elif change == "body":
        (original / "append-1.response.json").write_bytes(b"{}")
    elif change == "later_file":
        (original / "post-1.response.json").write_bytes(b"{}")
    else:
        (original / "frozen-request.json").unlink()
    transport, oauth, _, invoke = run()
    with pytest.raises(c.ContinuationRefused):
        invoke()
    oauth.assert_not_called()
    assert not transport.posts


@pytest.mark.parametrize("mode", ["wrong_head", "dirty", "behind_origin"])
def test_repository_gate_before_oauth(prepared, monkeypatch, mode):
    run, _ = prepared
    monkeypatch.setattr(c, "verify_repository_state", REAL_VERIFY_REPOSITORY_STATE)
    def fake_git(*args, root=c.REPOSITORY_ROOT):
        if args == ("rev-parse", "HEAD"):
            return ("0" * 40 if mode == "wrong_head" else HEAD).encode()
        if args == ("rev-parse", "--show-toplevel"):
            return str(root).encode()
        if args == ("status", "--porcelain", "--ignore-submodules=all"):
            return b" M dirty" if mode == "dirty" else b""
        if args == ("rev-parse", "origin/main"):
            return ("0" * 40 if mode == "behind_origin" else HEAD).encode()
        raise AssertionError(args)
    monkeypatch.setattr(c, "_git", fake_git)
    transport, oauth, _, invoke = run()
    with pytest.raises(c.ContinuationRefused):
        invoke()
    oauth.assert_not_called()
    assert not transport.posts


@pytest.mark.parametrize("rows", [
    (),
    (("wrong", c.ITEM, c.DETAIL),),
    ((c.MARKER, "wrong", c.DETAIL),),
    ((c.MARKER, c.ITEM, "wrong"),),
    (c.ROW, c.ROW),
])
def test_pre_replay_grid_must_be_exactly_one(prepared, rows):
    run, _ = prepared
    transport = FakeTransport([reply(body=grid(rows))])
    transport, _, evidence, invoke = run(transport)
    with pytest.raises(c.ContinuationRefused):
        invoke()
    assert not transport.posts
    assert not (evidence / "append-2.receipt.json").exists()


def test_frozen_request_identity_mismatch_zero_post(prepared):
    run, original = prepared
    path = original / "frozen-request.json"
    value = json.loads(path.read_bytes())
    value["identity_sha256"] = "0" * 64
    path.write_bytes(canonical_json_bytes(value))
    transport, _, _, invoke = run()
    with pytest.raises(Exception):
        invoke()
    assert not transport.posts


@pytest.mark.parametrize("second", [
    reply(status=None, error="TimeoutError", body=b""),
    reply(status=503, body=b"{}"),
])
def test_second_post_failure_never_retried(prepared, second):
    run, _ = prepared
    transport = FakeTransport([reply(body=grid((c.ROW,))), second])
    transport, _, evidence, invoke = run(transport)
    with pytest.raises(c.ContinuationRefused):
        invoke()
    assert len(transport.posts) == 1
    assert (evidence / "append-2.receipt.json").exists()


@pytest.mark.parametrize("rows", [
    (c.ROW,),
    (("wrong", c.ITEM, c.DETAIL), c.ROW),
    (c.ROW, (c.MARKER, c.ITEM, "wrong")),
    (c.ROW, c.ROW, c.ROW),
])
def test_final_grid_requires_two_matching_rows_no_overwrite_or_third(prepared, rows):
    run, _ = prepared
    transport = FakeTransport([reply(body=grid((c.ROW,))), reply(), reply(body=grid(rows))])
    transport, _, _, invoke = run(transport)
    with pytest.raises(c.ContinuationRefused):
        invoke()
    assert len(transport.posts) == 1


def test_visibility_over_40_seconds_fails(prepared):
    run, _ = prepared
    transport, _, evidence, invoke = run(times=[0.0, 40.001])
    with pytest.raises(c.ContinuationRefused, match="40 seconds"):
        invoke()
    assert len(transport.posts) == 1
    state = json.loads((evidence / "continuation-state.json").read_bytes())
    assert state["study2_paper_observations"] == 0


def test_no_model_cleanup_create_or_paper_mutation_path():
    source = inspect.getsource(c)
    for forbidden in ("spreadsheets.create", "deleteSheet", "batchClear",
                      "values.clear", "model_continue", "prepare_paper_append"):
        assert forbidden not in source
    assert c.MUTATION_URI.startswith(f"/v4/spreadsheets/{c.FIXTURE_SPREADSHEET_ID}")
    assert c.PAPER_SPREADSHEET_ID != c.FIXTURE_SPREADSHEET_ID
