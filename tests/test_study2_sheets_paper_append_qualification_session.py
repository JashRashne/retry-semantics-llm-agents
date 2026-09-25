"""Offline, fake-transport gates for the terminal engineering qualification."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_live_preparation import PreparedToken
from retry_semantics.study2.sheets_paper_adapter import DispatchFacts
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
from retry_semantics.study2.sheets_paper_materialize import (
    IMPLEMENTATION_PATHS, MANIFEST_PATH, REPOSITORY_ROOT, load_paper_manifest,
)
import run_sheets_paper_append_qualification_session as q

HEAD = "1" * 40
BEARER = "resident-secret-bearer-never-persist"


def result(status=200, body=None, error=None, initiated=True):
    raw = canonical_json_bytes(body) if type(body) is dict else (body if body is not None else b"")
    return PaperHTTPResult(DispatchFacts(initiated, initiated, status if initiated else None), raw, error)


def grid(rows=(), *, blank_data=False):
    sheet = {"properties": {"sheetId": q.FIXTURE_SHEET_ID, "title": q.FIXTURE_TITLE,
                            "sheetType": "GRID", "gridProperties": {"rowCount": 100,
                                                                    "columnCount": 3}}}
    if not blank_data:
        sheet["data"] = [{"startRow": 0, "startColumn": 0,
                          "rowData": [{"values": [{"userEnteredValue": {"stringValue": v}}
                                                  for v in row]} for row in rows]}]
    return {"spreadsheetId": q.FIXTURE_SPREADSHEET_ID, "sheets": [sheet]}


def prior_evidence(path, manifest, *, missing=None):
    path.mkdir()
    state = {"state": "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT",
             "spreadsheet_id": manifest["spreadsheet_id"],
             "manifest_sha256": q.FROZEN_MANIFEST_SHA256}
    (path / "capture-state.json").write_bytes(canonical_json_bytes(state))
    arms = [arm for family in manifest["families"] for arm in family["arms"]]
    for i in range(257):
        name = "topology" if i == 0 else f"baseline-{i - 1:03d}"
        raw = b"{}"
        receipt = {"method": "GET", "status": 200, "transport_error": None,
                   "dispatch_initiated": True, "local_send_completed": True,
                   "spreadsheet_id": manifest["spreadsheet_id"],
                   "body_sha256": sha256_hex(raw),
                   "target": "/topology" if i == 0 else arms[i - 1]["read_target"]}
        (path / f"{name}.response.json").write_bytes(raw)
        if name != missing:
            (path / f"{name}.receipt.json").write_bytes(canonical_json_bytes(receipt))


class Harness:
    def __init__(self, *, sheets=None, drive=None, times=None):
        self.sheets = list(sheets or [])
        self.drive = list(drive or [])
        self.sheets_calls = []
        self.drive_calls = []
        self.oauth = Mock(return_value=PreparedToken(BEARER, time.time() + 10_000, 1.0))
        self.times = iter(times or [0, 1, 2, 3])

    def sheets_transport(self, **kwargs):
        self.sheets_calls.append(kwargs)
        assert kwargs["bearer"] == BEARER
        assert kwargs["spreadsheet_id"] == q.FIXTURE_SPREADSHEET_ID
        assert self.sheets
        return self.sheets.pop(0)

    def drive_get(self, **kwargs):
        self.drive_calls.append(kwargs)
        assert kwargs["bearer"] == BEARER
        assert self.drive
        return self.drive.pop(0)

    def monotonic(self):
        return next(self.times)

    @property
    def posts(self):
        return [x for x in self.sheets_calls if x["method"] == "POST"]


def drive_results(*, extra_writer=False, next_page=False):
    principal = {"permissionId": "owner-id", "emailAddress": "owner@example.test",
                 "displayName": "Owner"}
    permissions = [{"id": "owner-id", "type": "user", "role": "owner",
                    "emailAddress": "owner@example.test", "displayName": "Owner"}]
    if extra_writer:
        permissions.append({"id": "writer-id", "type": "user", "role": "writer",
                            "emailAddress": "writer@example.test"})
    first = {"permissions": permissions}
    if next_page:
        first["nextPageToken"] = "page-2"
        return [result(body={"user": principal}), result(body=first),
                result(body={"permissions": []})]
    return [result(body={"user": principal}), result(body=first)]


def append_result(status=200, error=None, body=None):
    if body is None:
        body = {"spreadsheetId": q.FIXTURE_SPREADSHEET_ID, "replies": [{}]}
    return result(status=status, body=body, error=error)


def standard_sheets(*, pre=None, first=None, read1=None, second=None, read2=None):
    row = (q.MARKER, q.ITEM, q.DETAIL)
    return [pre or result(body=grid(blank_data=True)),
            first or append_result(),
            read1 or result(body=grid((row,))),
            second or append_result(),
            read2 or result(body=grid((row, row)))]


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    manifest = load_paper_manifest()
    prior = tmp_path / "prior"
    prior_evidence(prior, manifest)
    monkeypatch.setattr(q, "verify_repository_state", lambda **kwargs: None)

    def run(harness=None, **kwargs):
        h = harness or Harness(sheets=standard_sheets(), drive=drive_results())
        params = dict(client_path=tmp_path / "client.json", prior_readiness_dir=prior,
                      evidence_dir=tmp_path / f"evidence-{len(list(tmp_path.glob('evidence-*')))}",
                      expected_head=HEAD, execute=True, confirmation=q.APPEND_CONFIRMATION,
                      automation_confirmation=q.AUTOMATION_CONFIRMATION,
                      writers_confirmation=q.WRITERS_CONFIRMATION,
                      acquire_token=h.oauth, drive_get=h.drive_get,
                      sheets_transport=h.sheets_transport, monotonic=h.monotonic)
        params.update(kwargs)
        return h, lambda: q.run_qualification(**params), params["evidence_dir"]

    return run, prior, manifest


def test_happy_path_exact_replay_evidence_and_no_bearer(prepared, capsys):
    run, _, manifest = prepared
    h = Harness(sheets=standard_sheets(), drive=drive_results(next_page=True))
    h, invoke, evidence = run(h)
    assert invoke() == q.SUCCESS
    assert len(h.posts) == 2
    assert h.posts[0]["target"] == h.posts[1]["target"]
    for key in ("method", "body", "application_headers"):
        assert h.posts[0][key] == h.posts[1][key]
    assert manifest["spreadsheet_id"] not in h.posts[0]["target"]
    state = json.loads((evidence / "qualification-state.json").read_bytes())
    assert state["post_dispatch_count"] == 2 and state["get_count"] == 6
    assert state["drive_get_count"] == 3
    assert state["first_placement_row"] == 1 and state["duplicate_row_indices"] == [1, 2]
    assert state["classification_1"] == "EXACTLY_ONE"
    assert state["classification_2"] == "DUPLICATE"
    assert state["fixture_retired"] is True
    assert state["paper_spreadsheet_mutation_count"] == 0
    assert state["study2_paper_observations"] == 0
    assert state["visibility_1_seconds"] == 1 and state["visibility_2_seconds"] == 1
    assert (evidence / "paper-permissions-page-2.response.json").exists()
    assert BEARER not in "".join(p.read_text() for p in evidence.iterdir())
    assert BEARER not in capsys.readouterr().out
    assert h.oauth.call_count == 1


@pytest.mark.parametrize("git_mode,pattern", [
    ("wrong_head", "HEAD"), ("dirty", "dirty"), ("non_ancestor", "git gate")])
def test_repository_gate_before_oauth(tmp_path, monkeypatch, git_mode, pattern):
    def fake_git(*args, root=REPOSITORY_ROOT):
        if args == ("rev-parse", "HEAD"):
            return ("2" * 40 if git_mode == "wrong_head" else HEAD).encode()
        if args == ("rev-parse", "--show-toplevel"):
            return str(root).encode()
        if args == ("status", "--porcelain", "--ignore-submodules=all"):
            return b" M dirty" if git_mode == "dirty" else b""
        if args[:3] == ("merge-base", "--is-ancestor", q.FROZEN_PAPER_RUNTIME_HEAD):
            if git_mode == "non_ancestor":
                raise subprocess.CalledProcessError(1, "git")
            return b""
        raise AssertionError(args)
    monkeypatch.setattr(q, "_git", fake_git)
    oauth = Mock()
    with pytest.raises(q.QualificationRefused, match=pattern):
        q.run_qualification(client_path=tmp_path / "client", prior_readiness_dir=tmp_path,
                            evidence_dir=tmp_path / "ev", expected_head=HEAD,
                            execute=True, confirmation=q.APPEND_CONFIRMATION,
                            automation_confirmation=q.AUTOMATION_CONFIRMATION,
                            writers_confirmation=q.WRITERS_CONFIRMATION, acquire_token=oauth)
    oauth.assert_not_called()


def test_manifest_sha_gate_before_oauth(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "_git", lambda *args, root=REPOSITORY_ROOT:
                        HEAD.encode() if args == ("rev-parse", "HEAD") else
                        str(root).encode() if args == ("rev-parse", "--show-toplevel") else b"")
    monkeypatch.setattr(q, "FROZEN_MANIFEST_SHA256", "0" * 64)
    oauth = Mock()
    with pytest.raises(q.QualificationRefused, match="manifest SHA"):
        q.run_qualification(client_path=tmp_path / "client", prior_readiness_dir=tmp_path,
                            evidence_dir=tmp_path / "ev", expected_head=HEAD,
                            execute=True, confirmation=q.APPEND_CONFIRMATION,
                            automation_confirmation=q.AUTOMATION_CONFIRMATION,
                            writers_confirmation=q.WRITERS_CONFIRMATION, acquire_token=oauth)
    oauth.assert_not_called()


def test_missing_readiness_receipt_before_oauth(prepared):
    run, prior, _ = prepared
    (prior / "baseline-255.receipt.json").unlink()
    h, invoke, _ = run()
    with pytest.raises(q.QualificationRefused, match="missing"):
        invoke()
    h.oauth.assert_not_called()


@pytest.mark.parametrize("change,pattern", [
    ("acl", "another writer"), ("nonblank", "entered value"),
    ("malformed_blank", "wrong grid extent")])
def test_pre_mutation_refusals(prepared, change, pattern):
    run, _, _ = prepared
    drive = drive_results(extra_writer=change == "acl")
    pre = (result(body=grid((("other", "x", "y"),))) if change == "nonblank" else
           result(body={"spreadsheetId": q.FIXTURE_SPREADSHEET_ID, "sheets": [
               {"properties": {"sheetId": 1, "title": q.FIXTURE_TITLE,
                                "sheetType": "GRID", "gridProperties": {"rowCount": 99,
                                                                          "columnCount": 3}}}]})
           if change == "malformed_blank" else None)
    h = Harness(sheets=standard_sheets(pre=pre), drive=drive)
    h, invoke, evidence = run(h)
    with pytest.raises(Exception, match=pattern):
        invoke()
    assert not h.posts
    assert not (evidence / "fixture-retired.json").exists()


def test_missing_automation_attestation_before_oauth(prepared):
    run, _, _ = prepared
    h, invoke, _ = run(automation_confirmation="")
    with pytest.raises(q.QualificationRefused, match="confirmations"):
        invoke()
    h.oauth.assert_not_called()


def test_marker_collision_before_oauth(prepared, monkeypatch):
    run, _, _ = prepared
    monkeypatch.setattr(q, "MARKER", load_paper_manifest()["families"][0]["arms"][0]["arm_marker"])
    h, invoke, _ = run()
    with pytest.raises(q.QualificationRefused, match="collides"):
        invoke()
    h.oauth.assert_not_called()


@pytest.mark.parametrize("first", [
    append_result(status=None, error="TimeoutError"),
    append_result(status=503),
    append_result(body={"spreadsheetId": q.FIXTURE_SPREADSHEET_ID, "replies": []}),
])
def test_first_append_failure_never_replays(prepared, first):
    run, _, _ = prepared
    h = Harness(sheets=standard_sheets(first=first), drive=drive_results())
    h, invoke, evidence = run(h)
    with pytest.raises(Exception):
        invoke()
    assert len(h.posts) == 1
    assert (evidence / "fixture-retired.json").exists()
    assert json.loads((evidence / "qualification-state.json").read_bytes())["fixture_retired"] is True


@pytest.mark.parametrize("read1", [
    result(body=grid(())),
    result(body=grid(((q.MARKER, q.ITEM, "wrong"),))),
    result(body=grid((("other", q.ITEM, q.DETAIL),))),
])
def test_first_post_read_requires_exactly_one(prepared, read1):
    run, _, _ = prepared
    h = Harness(sheets=standard_sheets(read1=read1), drive=drive_results())
    h, invoke, _ = run(h)
    with pytest.raises(q.QualificationRefused):
        invoke()
    assert len(h.posts) == 1


@pytest.mark.parametrize("second", [
    append_result(status=None, error="TimeoutError"), append_result(status=503),
])
def test_second_append_failure_not_retried(prepared, second):
    run, _, _ = prepared
    h = Harness(sheets=standard_sheets(second=second), drive=drive_results())
    h, invoke, _ = run(h)
    with pytest.raises(Exception):
        invoke()
    assert len(h.posts) == 2


@pytest.mark.parametrize("read2", [
    result(body=grid(((q.MARKER, q.ITEM, q.DETAIL),))),
    result(body=grid(((q.MARKER, q.ITEM, q.DETAIL), ("other", q.ITEM, q.DETAIL)))),
    result(body=grid((("other", q.ITEM, q.DETAIL), (q.MARKER, q.ITEM, q.DETAIL)))),
])
def test_final_read_requires_two_matching_rows_without_overwrite(prepared, read2):
    run, _, _ = prepared
    h = Harness(sheets=standard_sheets(read2=read2), drive=drive_results())
    h, invoke, _ = run(h)
    with pytest.raises(q.QualificationRefused):
        invoke()
    assert len(h.posts) == 2


@pytest.mark.parametrize("times,post_count", [
    ([0, 41], 1), ([0, 1, 2, 43], 2),
])
def test_visibility_over_40_seconds_fails(prepared, times, post_count):
    run, _, _ = prepared
    h = Harness(sheets=standard_sheets(), drive=drive_results(), times=times)
    h, invoke, _ = run(h)
    with pytest.raises(q.QualificationRefused, match="40 seconds"):
        invoke()
    assert len(h.posts) == post_count


def test_no_model_create_cleanup_paper_post_or_frozen_changes():
    source = inspect.getsource(q)
    for forbidden in ("spreadsheets.create", "clear", "delete", "refresh_token", "model_continue"):
        assert forbidden not in source
    assert "scripts/run_sheets_paper_append_qualification_session.py" not in IMPLEMENTATION_PATHS
    assert q.FROZEN_MANIFEST_SHA256 == (
        "c9184255d5788fc00da3e7dd43afbe332a4dadcbc3f1534e95db320aeed8de4c"
    )  # Historical one-shot fixture operator remains pinned to its original manifest.
    assert q.FIXTURE_SPREADSHEET_ID != load_paper_manifest()["spreadsheet_id"]
