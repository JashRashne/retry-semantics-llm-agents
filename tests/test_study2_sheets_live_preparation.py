"""Frozen offline Sheets preparation qualification; no real credentials/observations."""
from dataclasses import replace
import gc
import http.client
import io
import json
import socket
import ssl
import time

import pytest

import retry_semantics.study2.sheets_live_preparation as live
from retry_semantics.study2.sheets_offline import prepare_append_cells

SECRET = "ya29.hostile.synthetic-secret"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    yield
    gc.collect()


@pytest.fixture
def fixture():
    return live.Fixture("offline_fixture", 7, "RetrySemanticsEngineering", 100, 3, "offline")


@pytest.fixture
def token():
    return live.prepare_token(SECRET, expires_at=time.time() + 3600,
                              clock_uncertainty_seconds=2)


@pytest.fixture
def frozen(fixture):
    return prepare_append_cells(spreadsheet_id=fixture.spreadsheet_id,
                                sheet_id=fixture.sheet_id, marker=fixture.marker("0001"))


@pytest.fixture
def journal(tmp_path, fixture, frozen, token):
    j = live.EvidenceJournal(tmp_path / "evidence.jsonl", trial_id="trial_0001",
        fixture=fixture, case_id="0001", request=frozen, token=token)
    yield j
    j.close()


class ErrorStream(io.BytesIO):
    def __init__(self, fault):
        super().__init__()
        self.fault = fault

    def readline(self, *args):
        if self.fault == "reset":
            error = ConnectionResetError(SECRET)
            error.authorization = SECRET
            raise error
        raise TimeoutError(SECRET)


class Wire:
    """Real HTTPSConnection class and HTTPResponse parser, fake connected socket."""
    def __init__(self, *, status=200, fault=None, body=b"{}"):
        self.status, self.fault, self.body = status, fault, body
        self.sockets, self.streams, self.calls = [], [], 0

    def connector(self, host, port, timeout, context):
        self.calls += 1
        assert (host, port) == (live.HOST, 443)
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        if self.fault in ("connect", "tls"):
            raise (ssl.SSLError(SECRET) if self.fault == "tls" else ConnectionError(SECRET))
        wire = self

        class FakeSocket:
            def __init__(self):
                self.chunks = []
                self.closed = False

            def sendall(self, data):
                self.chunks.append(data)
                if wire.fault == "header" or wire.fault == "partial" and len(self.chunks) == 2:
                    raise ConnectionError(SECRET)

            def makefile(self, *args, **kwargs):
                if wire.fault in ("wait", "reset"):
                    stream = ErrorStream(wire.fault)
                elif wire.fault == "malformed":
                    stream = io.BytesIO(b"this is not HTTP\r\n")
                else:
                    body = wire.body
                    declared = len(body) + (20 if wire.fault == "body_loss" else 0)
                    stream = io.BytesIO(f"HTTP/1.1 {wire.status} synthetic\r\nContent-Length: {declared}\r\nLocation: https://evil.invalid/?access_token={SECRET}\r\nRetry-After: 1\r\nAuthorization: {SECRET}\r\nSet-Cookie: {SECRET}\r\nConnection: close\r\n\r\n".encode() + body)
                wire.streams.append(stream)
                return stream

            def close(self):
                self.closed = True

        sock = FakeSocket()
        self.sockets.append(sock)
        return sock

    @property
    def mutation_count(self):
        return sum(chunk.startswith(b"POST ") for s in self.sockets for chunk in s.chunks)


def attempt(frozen, token, journal, wire):
    return live.mutation_attempt(frozen, token, journal, timeout=5,
        dispatch_budget_seconds=12, socket_connector=wire.connector)


def response(fixture, rows=()):
    return {"spreadsheetId": fixture.spreadsheet_id, "sheets": [{"properties": {
        "sheetId": fixture.sheet_id, "title": fixture.title, "sheetType": "GRID",
        "gridProperties": {"rowCount": fixture.rows, "columnCount": fixture.columns}},
        "data": [{"rowData": [{"values": [
            {"userEnteredValue": {"stringValue": s}} if s is not None else {}
            for s in row]} for row in rows]}]}]}


@pytest.mark.parametrize("status,expected", [(200, "known_success"), (201, "known_success"),
    (204, "known_success"), (301, "redirect_refused"), (302, "redirect_refused"),
    (303, "redirect_refused"), (307, "redirect_refused"), (308, "redirect_refused"),
    (401, "auth_issue"), (403, "known_http_error"), (404, "known_http_error"),
    (429, "known_http_error"), (500, "known_http_error"), (503, "known_http_error")])
def test_status_is_terminal_never_resends(frozen, token, journal, status, expected):
    wire = Wire(status=status, body=SECRET.encode())
    result = attempt(frozen, token, journal, wire)
    assert result == live.AttemptResult(expected, status, True)
    assert wire.calls == wire.mutation_count == 1
    assert wire.sockets[0].chunks[1] is frozen.body
    assert [e["stage"] for e in journal.events] == ["connect_started", "connect_completed",
        "dispatch_initiated", "local_send_completed", "status_observed", "closed", "attempt_result"]
    assert all(s.closed for s in wire.sockets) and all(s.closed for s in wire.streams)
    with pytest.raises(live.QualificationError):
        journal.enter_replay_policy()
    with pytest.raises(live.QualificationError):
        attempt(frozen, token, journal, wire)
    assert wire.mutation_count == 1


@pytest.mark.parametrize("fault,count,classification,completed", [
    ("connect", 0, "known_non_dispatch", False), ("tls", 0, "known_non_dispatch", False),
    ("header", 1, "incomplete_send_unknown", False),
    ("partial", 1, "incomplete_send_unknown", False),
    ("wait", 1, "ambiguous", True), ("reset", 1, "ambiguous", True),
    ("malformed", 1, "ambiguous", True)])
def test_fault_matrix_no_hidden_send(frozen, token, journal, fault, count, classification, completed):
    wire = Wire(fault=fault)
    result = attempt(frozen, token, journal, wire)
    assert result == live.AttemptResult(classification, None, completed)
    assert wire.calls == 1 and wire.mutation_count == count
    assert sum(e["stage"] == "dispatch_initiated" for e in journal.events) == count
    assert sum(e["stage"] == "local_send_completed" for e in journal.events) == int(completed)
    assert all(s.closed for s in wire.sockets) and all(s.closed for s in wire.streams)
    if completed:
        journal.enter_replay_policy()
    else:
        with pytest.raises(live.QualificationError):
            journal.enter_replay_policy()


@pytest.mark.parametrize("status,expected", [(200, "known_success_incomplete_response"),
    (401, "auth_issue"), (429, "known_http_error"), (500, "known_http_error"), (503, "known_http_error")])
def test_status_survives_body_loss(frozen, token, journal, status, expected):
    wire = Wire(status=status, fault="body_loss")
    assert attempt(frozen, token, journal, wire) == live.AttemptResult(expected, status, True)
    with pytest.raises(live.QualificationError):
        journal.enter_replay_policy()
    assert wire.mutation_count == 1


def test_explicit_replay_is_same_body_after_policy(frozen, token, journal):
    initial = Wire(fault="wait")
    attempt(frozen, token, journal, initial)
    hidden = Wire()
    with pytest.raises(live.QualificationError):
        attempt(frozen, token, journal, hidden)
    assert hidden.calls == 0
    journal.enter_replay_policy()
    replay = Wire()
    assert attempt(frozen, token, journal, replay).classification == "known_success"
    assert initial.sockets[0].chunks[1] is replay.sockets[0].chunks[1] is frozen.body
    facts = [e for e in journal.events if e["stage"] == "dispatch_initiated"]
    assert [e["dispatch_id"] for e in facts] == [1, 2]
    assert [e["after_policy_entry"] for e in facts] == [False, True]
    with pytest.raises(live.QualificationError):
        attempt(frozen, token, journal, replay)


@pytest.mark.parametrize("change", [{"method": "PUT"}, {"uri": "/v4/spreadsheets/other:batchUpdate"},
    {"uri": "/v4/spreadsheets/offline_fixture:batchUpdate?access_token=" + SECRET},
    {"body": b"{}"}, {"headers": (("Authorization", SECRET),)}])
def test_frozen_mismatch_refused_before_connector(frozen, token, journal, change):
    wire = Wire()
    with pytest.raises(live.QualificationError):
        attempt(replace(frozen, **change), token, journal, wire)
    assert wire.calls == 0


@pytest.mark.parametrize("attack", ["host", "length", "auth", "extra", "duplicate", "method", "body", "resend"])
def test_wire_tampering_fails_closed(monkeypatch, frozen, token, journal, attack):
    original = http.client.HTTPConnection.send
    def send(conn, data):
        if data.startswith(b"POST "):
            if attack == "host":
                data = data.replace(live.HOST.encode(), b"evil.invalid")
            elif attack == "length":
                data = data.replace(f"Content-Length: {len(frozen.body)}".encode(), b"Content-Length: 999")
            elif attack == "auth":
                data = data.replace(SECRET.encode(), b"other-token")
            elif attack in ("extra", "duplicate"):
                data = data[:-2] + (b"X-Secret: " if attack == "extra" else b"authorization: Bearer ") + SECRET.encode() + b"\r\n\r\n"
            elif attack == "method":
                data = data.replace(b"POST ", b"GET ", 1)
            elif attack == "resend":
                original(conn, data)
                original(conn, frozen.body)
        elif attack == "body":
            data = data + b" "
        return original(conn, data)
    monkeypatch.setattr(http.client.HTTPConnection, "send", send)
    wire = Wire()
    with pytest.raises(live.QualificationError):
        attempt(frozen, token, journal, wire)
    assert wire.mutation_count <= 1
    with pytest.raises(live.QualificationError):
        journal.enter_replay_policy()


@pytest.mark.parametrize("now,expiry,budget,uncertainty,ready", [(100, 120, 10, 2, True),
    (100, 112, 10, 2, False), (100, 111, 10, 2, False), (100, 90, 10, 2, False)])
def test_token_readiness_no_magic_margin(now, expiry, budget, uncertainty, ready):
    token = live.prepare_token(SECRET, expires_at=expiry, clock_uncertainty_seconds=uncertainty)
    if ready:
        token.check_ready(now=now, dispatch_budget_seconds=budget)
    else:
        with pytest.raises(live.QualificationError):
            token.check_ready(now=now, dispatch_budget_seconds=budget)
    assert SECRET not in repr(token) and "ya29" not in repr(token)
    assert not hasattr(token, "refresh") and not hasattr(token, "before_request")


@pytest.mark.parametrize("value", ["Bearer " + SECRET, SECRET + "\r\nInjected: x", "", object()])
def test_bad_auth_material_refused(value):
    with pytest.raises(live.QualificationError):
        live.prepare_token(value, expires_at=1000, clock_uncertainty_seconds=1)


def test_expired_token_and_unselected_real_network_refused(frozen, token, journal):
    wire = Wire()
    with pytest.raises(live.QualificationError):
        attempt(frozen, replace(token, expires_at=1), journal, wire)
    assert wire.calls == 0
    with pytest.raises(live.QualificationError):
        live.mutation_attempt(frozen, token, journal, timeout=5, dispatch_budget_seconds=12)


@pytest.mark.parametrize("kind,expected,coords", [("empty", "zero_matches", ()),
    ("one", "one_match", (1,)), ("duplicates", "multiple_matches", (0, 2)),
    ("unrelated", "zero_matches", ()), ("trailing", "one_match", (0,))])
def test_grid_literal_and_sparse_shapes(fixture, kind, expected, coords):
    marker = fixture.marker("0001")
    row = (marker, "engineering-v1", "literal-payload")
    rows = {"empty": [], "one": [(), row], "duplicates": [row, (), row],
            "unrelated": [("other", "values")], "trailing": [row, (), (None,)]}[kind]
    payload = response(fixture, rows)
    result = live.parse_grid(payload, fixture, marker)
    assert (result.classification, result.rows) == (expected, coords)


@pytest.mark.parametrize("attack", ["missing_sheet", "missing_data", "missing_id", "wrong_sheet",
    "wrong_title", "changed_extent", "too_many_columns", "too_many_rows", "start_row",
    "start_column", "multiple_grids", "formula", "number", "mismatch", "merges", "tables",
    "malformed_row", "malformed_cell", "bad_offset_type", "data_none"])
def test_grid_bad_or_incomplete_is_unknown(fixture, attack):
    marker = fixture.marker("0001")
    payload = response(fixture, [(marker, "engineering-v1", "literal-payload")])
    sheet = payload["sheets"][0]
    grid = sheet["data"][0]
    if attack == "missing_sheet": payload["sheets"] = []
    elif attack == "missing_data": del sheet["data"]
    elif attack == "missing_id": del payload["spreadsheetId"]
    elif attack == "wrong_sheet": sheet["properties"]["sheetId"] = 8
    elif attack == "wrong_title": sheet["properties"]["title"] = "other"
    elif attack == "changed_extent": sheet["properties"]["gridProperties"]["rowCount"] += 1
    elif attack == "too_many_columns": grid["rowData"][0]["values"].append({})
    elif attack == "too_many_rows": grid["rowData"] = [{}] * 101
    elif attack == "start_row": grid["startRow"] = 1
    elif attack == "start_column": grid["startColumn"] = 1
    elif attack == "multiple_grids": sheet["data"].append({})
    elif attack in ("formula", "number"):
        grid["rowData"][0]["values"][0]["userEnteredValue"] = {
            "formulaValue" if attack == "formula" else "numberValue": "=" + marker}
    elif attack == "mismatch": grid["rowData"][0]["values"][1] = {}
    elif attack in ("merges", "tables"): sheet[attack] = [{}]
    elif attack == "malformed_row": grid["rowData"][0] = None
    elif attack == "malformed_cell": grid["rowData"][0]["values"][0] = None
    elif attack == "bad_offset_type": grid["startRow"] = False
    elif attack == "data_none": sheet["data"] = None
    assert live.parse_grid(payload, fixture, marker).classification == "malformed_or_incomplete"


def test_display_and_effective_values_do_not_match_marker(fixture):
    marker = fixture.marker("0001")
    payload = response(fixture, [()])
    payload["sheets"][0]["data"][0]["rowData"][0]["values"] = [
        {"formattedValue": marker, "effectiveValue": {"stringValue": marker}}]
    assert live.parse_grid(payload, fixture, marker) == live.Verification("zero_matches")


@pytest.mark.parametrize("status,fault,expected", [(200, None, "one_match"),
    (401, None, "verifier_uncertainty"), (403, None, "verifier_uncertainty"),
    (429, None, "verifier_uncertainty"), (302, None, "verifier_uncertainty"),
    (200, "wait", "verifier_uncertainty"), (200, "body_loss", "verifier_uncertainty"),
    (200, "malformed", "verifier_uncertainty")])
def test_verifier_is_one_get_and_never_mutates(fixture, token, journal, status, fault, expected):
    marker = fixture.marker("0001")
    wire = Wire(status=status, fault=fault, body=json.dumps(response(fixture,
        [(marker, "engineering-v1", "literal-payload")])).encode())
    verifier = live.ReadOnlyVerifier(fixture, socket_connector=wire.connector)
    assert verifier.inspect(token, marker, journal).classification == expected
    assert wire.calls == 1 and wire.mutation_count == 0
    assert wire.sockets[0].chunks[0].startswith(b"GET ")
    assert len(wire.sockets[0].chunks) == 1
    assert all(s.closed for s in wire.sockets) and all(s.closed for s in wire.streams)
    assert not hasattr(verifier, "batchUpdate") and not hasattr(verifier, "mutation_attempt")


@pytest.mark.parametrize("bad_body", [b"{}", b"not json", b'{"spreadsheetId":"x","spreadsheetId":"y"}', b'{"sheets":NaN}'])
def test_verifier_malformed_json(fixture, token, journal, bad_body):
    wire = Wire(body=bad_body)
    result = live.ReadOnlyVerifier(fixture, socket_connector=wire.connector).inspect(token, fixture.marker("0001"), journal)
    assert result.classification in ("verifier_uncertainty", "malformed_or_incomplete")
    assert wire.mutation_count == 0


def test_verifier_response_cap(fixture, token, journal):
    wire = Wire(body=b" " * 100)
    assert live.ReadOnlyVerifier(fixture, socket_connector=wire.connector,
        max_response_bytes=10).inspect(token, fixture.marker("0001"), journal).classification == "verifier_uncertainty"


@pytest.mark.parametrize("attack", ["Authorization", "exception_args", "exception_attrs", "response_headers",
    "response_body", "query", "environment", "credential_object"])
def test_secret_exclusion_construction_allowlist(monkeypatch, frozen, token, journal, tmp_path, attack):
    wire = Wire(body=SECRET.encode(), fault="reset" if attack in ("exception_args", "exception_attrs") else None)
    if attack == "query":
        with pytest.raises(live.QualificationError):
            attempt(replace(frozen, uri=frozen.uri + "?access_token=" + SECRET), token, journal, wire)
    elif attack == "environment":
        monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", SECRET)
        attempt(frozen, token, journal, wire)
    elif attack == "credential_object":
        class Credential:
            authorization = refresh_token = SECRET
            def __str__(self):
                pytest.fail("credential serialization forbidden")
        with pytest.raises(TypeError):
            journal.event("failure", 0, credentials=Credential())
    else:
        attempt(frozen, token, journal, wire)
    persisted = (tmp_path / "evidence.jsonl").read_text()
    assert SECRET not in persisted and "ya29" not in persisted
    assert "Authorization" not in persisted and "Bearer" not in persisted
    assert "refresh_token" not in persisted and "GOOGLE_ACCESS_TOKEN" not in persisted
    assert "remote_received" not in persisted and "remote_committed" not in persisted


@pytest.mark.parametrize("field", ["trial_id", "case_id", "spreadsheet_id", "namespace"])
def test_secret_input_cannot_enter_header(tmp_path, fixture, frozen, token, field):
    kwargs = dict(trial_id="trial_0001", case_id="0001", fixture=fixture, request=frozen, token=token)
    with pytest.raises(live.QualificationError):
        if field in ("spreadsheet_id", "namespace"):
            kwargs["fixture"] = replace(fixture, **{field: "ya29_hostile_secret"})
        else:
            kwargs[field] = "ya29_hostile_secret"
        live.EvidenceJournal(tmp_path / "bad.jsonl", **kwargs)
    assert not (tmp_path / "bad.jsonl").exists()


def test_allowlist_rejects_arbitrary_event_fields(journal):
    with pytest.raises(TypeError): journal.event("failure", 0, exception=Exception(SECRET))
    with pytest.raises(live.QualificationError): journal.event(SECRET, 0)
    with pytest.raises(live.QualificationError): journal.event("failure", 0, classification=SECRET)
    with pytest.raises(live.QualificationError): journal.event("verifier_summary", 0, verifier=SECRET)


@pytest.mark.parametrize("boundary", ["before_header", "after_send", "close"])
def test_storage_failure_blocks_and_never_resends(monkeypatch, frozen, token, journal, boundary):
    original = journal._write
    def fail(safe):
        if safe.get("stage") == {"before_header": "dispatch_initiated", "after_send": "local_send_completed", "close": "closed"}[boundary]:
            raise OSError(SECRET)
        return original(safe)
    monkeypatch.setattr(journal, "_write", fail)
    wire = Wire()
    with pytest.raises(live.QualificationError): attempt(frozen, token, journal, wire)
    assert wire.mutation_count == (0 if boundary == "before_header" else 1)
    with pytest.raises(live.QualificationError): attempt(frozen, token, journal, wire)
    with pytest.raises(live.QualificationError): journal.enter_replay_policy()
    assert wire.calls == 1 and all(s.closed for s in wire.sockets)


def test_fixture_template_has_no_live_ids_and_hash_is_stable(fixture):
    template = json.loads((live.SHEETS_DOCS / "fixtures/qualification_fixture_draft.json").read_text())
    assert template["spreadsheet_id"] is template["sheet_id"] is None
    assert fixture.manifest_hash == replace(fixture).manifest_hash
    assert fixture.manifest_hash != replace(fixture, sheet_id=8).manifest_hash
    assert fixture.read_path.startswith("/v4/spreadsheets/offline_fixture?")
    assert "batchUpdate" not in fixture.read_path


def test_runtime_exact_pin_and_drift_refusal(monkeypatch):
    actual = live.check_runtime()
    assert actual["python_version"] == "3.11.14" and actual["implementation"] == "CPython"
    monkeypatch.setattr(live, "runtime_fingerprint", lambda: dict(actual, openssl="changed"))
    with pytest.raises(live.QualificationError): live.check_runtime()


def test_reserved_evidence_no_overwrite(tmp_path, fixture, frozen, token):
    path = tmp_path / "exists.jsonl"
    path.write_text("prior evidence\n")
    with pytest.raises(FileExistsError):
        live.EvidenceJournal(path, trial_id="trial_0001", fixture=fixture, case_id="0001", request=frozen, token=token)
    assert path.read_text() == "prior evidence\n"


def test_after_send_fault_and_persisted_result(fixture, frozen, token, tmp_path):
    journal = live.EvidenceJournal(tmp_path / "evidence.jsonl", trial_id="trial_0001",
        fixture=fixture, case_id="0001", request=frozen, token=token, fault="after_send_before_status")
    wire = Wire()
    assert attempt(frozen, token, journal, wire) == live.AttemptResult("ambiguous", None, True)
    assert wire.streams == [] and wire.mutation_count == 1
    assert [e["stage"] for e in journal.events][-3:] == ["fault_injected", "closed", "attempt_result"]
    journal.enter_replay_policy()
    lines = [json.loads(line) for line in (tmp_path / "evidence.jsonl").read_text().splitlines()]
    assert lines[-2]["classification"] == "ambiguous"
    assert lines[-2]["send_completed"] is True
    assert lines[0]["body_hex"] == frozen.body.hex()
    assert [e["sequence"] for e in lines[1:]] == list(range(1, len(lines)))
    assert [e["monotonic_ns"] for e in lines[1:]] == sorted(e["monotonic_ns"] for e in lines[1:])
    journal.close()


@pytest.mark.parametrize("stage", ["dispatch_initiated", "local_send_completed", "status_observed", "policy_entry"])
def test_lifecycle_cannot_be_entered_without_attempt(journal, stage):
    with pytest.raises(live.QualificationError):
        journal.event(stage, 1)


def test_duplicate_wrong_completion_fail_closed(frozen, token, journal):
    journal.begin_attempt(frozen)
    journal.event("connect_started", 1)
    journal.event("connect_completed", 1)
    journal.event("dispatch_initiated", 1)
    with pytest.raises(live.QualificationError): journal.event("local_send_completed", 2)
    journal.event("local_send_completed", 1)
    with pytest.raises(live.QualificationError): journal.event("local_send_completed", 1)
    with pytest.raises(live.QualificationError): journal.enter_replay_policy()


@pytest.mark.parametrize("method", [b"POST", b"PUT", b"DELETE", b"PATCH"])
def test_verifier_actual_wire_method_override_refused(monkeypatch, fixture, token, journal, method):
    original = http.client.HTTPConnection.send
    def hostile(conn, data):
        return original(conn, data.replace(b"GET ", method + b" ", 1))
    monkeypatch.setattr(http.client.HTTPConnection, "send", hostile)
    wire = Wire()
    result = live.ReadOnlyVerifier(fixture, socket_connector=wire.connector).inspect(token, fixture.marker("0001"), journal)
    assert result.classification == "verifier_uncertainty"
    assert wire.mutation_count == 0 and wire.sockets[0].chunks == []


@pytest.mark.parametrize("attack", ["batchUpdate", "method_header", "extra_query", "read_resend"])
def test_verifier_path_headers_and_resend_refused(monkeypatch, fixture, token, journal, attack):
    original = http.client.HTTPConnection.send
    def hostile(conn, data):
        if attack == "batchUpdate":
            data = data.replace(fixture.read_path.encode(), b"/v4/spreadsheets/offline_fixture:batchUpdate")
        elif attack == "extra_query":
            data = data.replace(b" HTTP/1.1", b"&access_token=" + SECRET.encode() + b" HTTP/1.1")
        elif attack == "method_header":
            data = data[:-2] + b"X-HTTP-Method-Override: POST\r\n\r\n"
        else:
            original(conn, data)
        return original(conn, data)
    monkeypatch.setattr(http.client.HTTPConnection, "send", hostile)
    wire = Wire()
    result = live.ReadOnlyVerifier(fixture, socket_connector=wire.connector).inspect(token, fixture.marker("0001"), journal)
    assert result.classification == "verifier_uncertainty"
    assert wire.mutation_count == 0
    assert len(wire.sockets[0].chunks) == (1 if attack == "read_resend" else 0)


def test_verifier_summaries_persist_no_provider_values(fixture, token, journal, tmp_path):
    marker = fixture.marker("0001")
    payload = response(fixture, [(SECRET,), (marker, "engineering-v1", "literal-payload")])
    wire = Wire(body=json.dumps(payload).encode())
    verifier = live.ReadOnlyVerifier(fixture, socket_connector=wire.connector)
    for _ in range(2):
        assert verifier.inspect(token, marker, journal) == live.Verification("one_match", (1,), 2)
    summaries = [e for e in journal.events if e["stage"] == "verifier_summary"]
    assert [e["dispatch_id"] for e in summaries] == [1, 2]
    assert wire.calls == 2 and wire.mutation_count == 0
    persisted = (tmp_path / "evidence.jsonl").read_text()
    assert SECRET not in persisted and "ya29" not in persisted
    assert summaries[0]["matching_rows"] == [1]


def test_fsync_failure_is_terminal(monkeypatch, frozen, token, journal):
    def fail(*args): raise OSError(SECRET)
    monkeypatch.setattr(live.os, "fsync", fail)
    wire = Wire()
    with pytest.raises(live.QualificationError): attempt(frozen, token, journal, wire)
    assert wire.calls == 0
    with pytest.raises(live.QualificationError): journal.enter_replay_policy()


def test_read_storage_failure_prevents_wire_send(monkeypatch, fixture, token, journal):
    original = journal._write
    def fail(safe):
        if safe.get("stage") == "verifier_initiated": raise OSError(SECRET)
        return original(safe)
    monkeypatch.setattr(journal, "_write", fail)
    wire = Wire()
    with pytest.raises(live.QualificationError):
        live.ReadOnlyVerifier(fixture, socket_connector=wire.connector).inspect(token, fixture.marker("0001"), journal)
    assert wire.mutation_count == 0 and wire.sockets[0].chunks == []


def test_mutation_has_no_credential_callback_path(frozen, token, journal):
    class Credentials:
        token = SECRET
        def refresh(self, *args): pytest.fail("refresh forbidden")
        def before_request(self, *args): pytest.fail("auth wrapper forbidden")
    wire = Wire(status=401)
    with pytest.raises(live.QualificationError): attempt(frozen, Credentials(), journal, wire)
    assert wire.calls == 0
    assert attempt(frozen, token, journal, wire).classification == "auth_issue"
    assert wire.calls == wire.mutation_count == 1


def test_known_token_echo_rejected_before_any_artifact(tmp_path, fixture, frozen):
    token = live.prepare_token("offline", expires_at=time.time() + 3600, clock_uncertainty_seconds=2)
    with pytest.raises(live.QualificationError):
        live.EvidenceJournal(tmp_path / "echo.jsonl", trial_id="trial_0001", fixture=fixture,
                             case_id="0001", request=frozen, token=token)
    assert not (tmp_path / "echo.jsonl").exists()


def test_hex_token_echo_refused_before_artifact(tmp_path, fixture, token):
    hostile = replace(fixture, namespace=SECRET.encode().hex())
    frozen = prepare_append_cells(spreadsheet_id=hostile.spreadsheet_id,
        sheet_id=hostile.sheet_id, marker=hostile.marker("0001"))
    with pytest.raises(live.QualificationError):
        live.EvidenceJournal(tmp_path / "hex.jsonl", trial_id="trial_0001", fixture=hostile,
                             case_id="0001", request=frozen, token=token)
    assert not (tmp_path / "hex.jsonl").exists()


def test_export_is_immutable_and_no_callback_slot(token):
    from dataclasses import FrozenInstanceError
    with pytest.raises((FrozenInstanceError, TypeError)):
        token.refresh = lambda: SECRET
    with pytest.raises(FrozenInstanceError): token.value = "changed"


def test_replay_does_not_call_model_or_regenerate_body(monkeypatch, frozen, token, journal):
    first = Wire(fault="wait")
    attempt(frozen, token, journal, first)
    journal.enter_replay_policy()
    import retry_semantics.study2.sheets_offline as offline
    monkeypatch.setattr(offline, "prepare_append_cells", lambda **kwargs: pytest.fail("body regeneration forbidden"))
    second = Wire()
    attempt(frozen, token, journal, second)
    assert second.sockets[0].chunks[1] is frozen.body


def test_noncanonical_replay_bytes_fail_exact_snapshot(frozen, token, journal):
    attempt(frozen, token, journal, Wire(fault="wait"))
    journal.enter_replay_policy()
    wire = Wire()
    changed = replace(frozen, body=json.dumps(json.loads(frozen.body), indent=2).encode())
    with pytest.raises(live.QualificationError): attempt(changed, token, journal, wire)
    assert wire.calls == 0


def test_every_verifier_without_connector_remains_disabled(fixture, token, journal):
    verifier = live.ReadOnlyVerifier(fixture)
    assert verifier.inspect(token, fixture.marker("0001"), journal).classification == "verifier_uncertainty"


def test_socket_loss_never_auto_reopens(monkeypatch, frozen, token, journal):
    original = live._Connection.connect
    def lose(conn):
        original(conn)
        conn.sock.close()
        conn.sock = None
    monkeypatch.setattr(live._Connection, "connect", lose)
    wire = Wire()
    with pytest.raises(live.QualificationError): attempt(frozen, token, journal, wire)
    assert wire.calls == 1 and wire.mutation_count == 0
    assert not any(e["stage"] == "dispatch_initiated" for e in journal.events)


def test_fixed_connection_configuration_and_no_tunnel(token):
    wire = Wire()
    conn = live._Connection(5, wire.connector)
    assert conn.auto_open == conn.debuglevel == 0
    conn.set_tunnel("evil.invalid")
    with pytest.raises(live.QualificationError): conn.connect()
    assert wire.calls == 0
    conn.close()


def test_secret_unknown_exception_is_not_serialized(fixture, token, journal, tmp_path):
    def hostile(*args):
        error = RuntimeError(SECRET)
        error.refresh_token = SECRET
        raise error
    verifier = live.ReadOnlyVerifier(fixture, socket_connector=hostile)
    assert verifier.inspect(token, fixture.marker("0001"), journal).classification == "verifier_uncertainty"
    assert SECRET not in (tmp_path / "evidence.jsonl").read_text()


def test_checklist_only_marks_offline_conditions_offline_pass():
    data = json.loads((live.SHEETS_DOCS / "SHEETS_LIVE_GO_CHECKLIST_DRAFT.json").read_text())
    assert data["live_go"] == "CLOSED" and data["paper_observations"] == 0
    assert len({i["id"] for i in data["items"]}) == len(data["items"])
    assert {i["status"] for i in data["items"]} == {"PASS OFFLINE", "BLOCKED", "REQUIRES LIVE VALIDATION"}
    for item in data["items"]:
        assert item["evidence"]
        if item["id"] in ("actual_grid_response_shapes", "baseline_isolation", "clean_success_placement", "live_ambiguity_boundary"):
            assert item["status"] == "REQUIRES LIVE VALIDATION"


def test_equal_copy_replay_still_sends_original_stored_body(frozen, token, journal):
    attempt(frozen, token, journal, Wire(fault="wait"))
    journal.enter_replay_policy()
    equal_copy = replace(frozen, body=bytes(bytearray(frozen.body)))
    assert equal_copy.body == frozen.body and equal_copy.body is not frozen.body
    wire = Wire()
    attempt(equal_copy, token, journal, wire)
    assert wire.sockets[0].chunks[1] is frozen.body


def exported(value):
    return live.prepare_token(value, expires_at=time.time() + 3600,
                              clock_uncertainty_seconds=2)


@pytest.mark.parametrize("action", ["baseline_read", "mutation", "later_read", "replay"])
@pytest.mark.parametrize("collision", ["spreadsheet", "trial", "namespace", "marker", "runtime", "future_field"])
def test_distinct_later_tokens_colliding_with_evidence_refused(
        fixture, frozen, token, journal, tmp_path, action, collision):
    values = {"spreadsheet": fixture.spreadsheet_id, "trial": "trial_0001",
              "namespace": fixture.namespace, "marker": fixture.marker("0001"),
              "runtime": "stdlib-http.client", "future_field": "verifier_classification"}
    later = exported(values[collision])
    assert later.value != token.value and "ya29" not in later.value
    prior = Wire(fault="wait" if action == "replay" else None)
    if action == "mutation":
        baseline = Wire(body=json.dumps(response(fixture)).encode())
        assert live.ReadOnlyVerifier(fixture, socket_connector=baseline.connector).inspect(
            token, fixture.marker("0001"), journal).classification == "zero_matches"
    elif action == "later_read":
        assert live.ReadOnlyVerifier(fixture, socket_connector=prior.connector).inspect(
            token, fixture.marker("0001"), journal).classification == "malformed_or_incomplete"
    elif action == "replay":
        assert attempt(frozen, token, journal, prior).classification == "ambiguous"
        journal.enter_replay_policy()
    before = (tmp_path / "evidence.jsonl").read_bytes()
    events, attempts, reads = journal.events, journal._attempts, journal._reads
    next_wire = Wire()
    with pytest.raises(live.TokenSafetyError) as error:
        if action in ("mutation", "replay"):
            attempt(frozen, later, journal, next_wire)
        else:
            live.ReadOnlyVerifier(fixture, socket_connector=next_wire.connector).inspect(
                later, fixture.marker("0001"), journal)
    assert next_wire.calls == next_wire.mutation_count == 0 and next_wire.sockets == []
    assert (tmp_path / "evidence.jsonl").read_bytes() == before
    assert journal.events == events and journal._attempts == attempts and journal._reads == reads
    assert str(error.value) == "" and error.value.args == ()
    assert later.value not in repr(error.value)
    assert journal._broken  # Existing evidence collision invalidates, never repairs/reissues.


@pytest.mark.parametrize("action", ["mutation", "later_read", "replay"])
@pytest.mark.parametrize("case", ["lower", "upper"])
def test_distinct_later_hex_echo_in_evidence_refused(
        fixture, token, tmp_path, action, case):
    later = exported("synthetic-next-material-9482")
    encoded = later.value.encode().hex()
    if case == "upper": encoded = encoded.upper()
    hostile_fixture = replace(fixture, namespace=encoded)
    frozen = prepare_append_cells(spreadsheet_id=fixture.spreadsheet_id,
        sheet_id=fixture.sheet_id, marker=hostile_fixture.marker("0001"))
    path = tmp_path / "hex_later.jsonl"
    with live.EvidenceJournal(path, trial_id="trial_0001", fixture=hostile_fixture,
            case_id="0001", request=frozen, token=token) as journal:
        if action == "replay":
            attempt(frozen, token, journal, Wire(fault="wait"))
            journal.enter_replay_policy()
        before = path.read_bytes()
        wire = Wire()
        with pytest.raises(live.TokenSafetyError) as error:
            if action == "later_read":
                live.ReadOnlyVerifier(hostile_fixture, socket_connector=wire.connector).inspect(
                    later, hostile_fixture.marker("0001"), journal)
            else:
                attempt(frozen, later, journal, wire)
        assert wire.calls == 0 and wire.sockets == []
        assert path.read_bytes() == before and error.value.args == ()
        assert later.value not in repr(error.value)


def test_genuinely_distinct_safe_read_mutation_and_later_read_tokens(
        fixture, frozen, token, journal, tmp_path):
    baseline_token = exported("synthetic-baseline-material-1829")
    mutation_token = exported("synthetic-mutation-material-3741")
    later_read_token = exported("synthetic-readback-material-5927")
    baseline = Wire(body=json.dumps(response(fixture)).encode())
    assert live.ReadOnlyVerifier(fixture, socket_connector=baseline.connector).inspect(
        baseline_token, fixture.marker("0001"), journal) == live.Verification("zero_matches")
    mutation = Wire()
    assert attempt(frozen, mutation_token, journal, mutation).classification == "known_success"
    readback = Wire(body=json.dumps(response(fixture,
        [(fixture.marker("0001"), "engineering-v1", "literal-payload")])).encode())
    assert live.ReadOnlyVerifier(fixture, socket_connector=readback.connector).inspect(
        later_read_token, fixture.marker("0001"), journal) == live.Verification("one_match", (0,), 1)
    assert baseline.calls == mutation.calls == readback.calls == 1
    assert baseline.mutation_count == readback.mutation_count == 0 and mutation.mutation_count == 1
    evidence = (tmp_path / "evidence.jsonl").read_text()
    for active in (token, baseline_token, mutation_token, later_read_token):
        assert active.value not in evidence and active.value.encode().hex() not in evidence
    assert not any(type(v) is live.PreparedToken for v in vars(journal).values())


def test_distinct_safe_replay_token_sends_original_frozen_bytes(frozen, token, journal, tmp_path):
    attempt(frozen, token, journal, Wire(fault="wait"))
    journal.enter_replay_policy()
    later = exported("synthetic-replay-material-7183")
    wire = Wire()
    assert attempt(frozen, later, journal, wire).classification == "known_success"
    assert wire.mutation_count == 1 and wire.sockets[0].chunks[1] is frozen.body
    evidence = (tmp_path / "evidence.jsonl").read_text()
    assert later.value not in evidence and later.value.encode().hex() not in evidence


def test_serialization_source_drift_refuses_runtime(monkeypatch):
    source = live.ROOT / "src/retry_semantics/serialization.py"
    original = live.Path.read_bytes
    before = live.check_runtime()
    assert before["serialization_source_sha256"] == live.sha256_hex(original(source))
    def drift(path):
        data = original(path)
        return data + b"\n# synthetic source drift\n" if path == source else data
    monkeypatch.setattr(live.Path, "read_bytes", drift)
    assert live.runtime_fingerprint()["serialization_source_sha256"] != before["serialization_source_sha256"]
    with pytest.raises(live.QualificationError): live.check_runtime()


def test_exact_platform_release_pin_and_drift_refusal(monkeypatch):
    before = live.check_runtime()
    assert before["platform_release"] == live.platform.release()
    assert before["platform_release"]
    monkeypatch.setattr(live.platform, "release", lambda: "synthetic-release-drift")
    with pytest.raises(live.QualificationError): live.check_runtime()


def test_later_token_colliding_with_recorded_dynamic_value_is_refused(
        fixture, token, journal, tmp_path):
    wire = Wire(body=json.dumps(response(fixture)).encode())
    verifier = live.ReadOnlyVerifier(fixture, socket_connector=wire.connector)
    verifier.inspect(token, fixture.marker("0001"), journal)
    later = exported(str(journal.events[0]["monotonic_ns"]))
    before = (tmp_path / "evidence.jsonl").read_bytes()
    with pytest.raises(live.TokenSafetyError) as error:
        verifier.inspect(later, fixture.marker("0001"), journal)
    assert wire.calls == 1 and wire.mutation_count == 0
    assert (tmp_path / "evidence.jsonl").read_bytes() == before
    assert str(error.value) == "" and error.value.args == ()


def test_central_check_walks_only_known_evidence_without_serializing_token(
        monkeypatch, token, journal, tmp_path):
    before = (tmp_path / "evidence.jsonl").read_bytes()
    def forbidden(*args, **kwargs): pytest.fail("token safety must not serialize anything")
    monkeypatch.setattr(live, "canonical_json_bytes", forbidden)
    monkeypatch.setattr(live.json, "dumps", forbidden)
    journal.assert_token_safe(exported("synthetic-isolated-material-3629"))
    assert (tmp_path / "evidence.jsonl").read_bytes() == before


def test_future_independent_404_status_equality_is_not_credential_dataflow(
        monkeypatch, fixture, frozen, tmp_path):
    from datetime import datetime as RealDatetime, timezone
    # Freeze only the wall clock so accidental digits in preparation time cannot
    # violate the known-domain precondition on this exact pinned environment.
    class FixedDatetime:
        @classmethod
        def now(cls, zone):
            return RealDatetime(2001, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(live, "datetime", FixedDatetime)
    synthetic = exported("404")
    path = tmp_path / "status_coincidence.jsonl"
    with live.EvidenceJournal(path, trial_id="trial_0001", fixture=fixture,
            case_id="0001", request=frozen, token=synthetic) as journal:
        assert "404" not in path.read_text()
        journal.assert_token_safe(synthetic)
        wire = Wire(status=404)
        result = live.ReadOnlyVerifier(fixture, socket_connector=wire.connector).inspect(
            synthetic, fixture.marker("0001"), journal)
        assert result == live.Verification("verifier_uncertainty")
        assert wire.calls == 1 and wire.mutation_count == 0
        records = [json.loads(line) for line in path.read_text().splitlines()]
        status = next(r for r in records[1:] if r["stage"] == "verifier_status")
        assert type(status["status"]) is int and status["status"] == wire.status == 404
        assert set(status) == {"sequence", "monotonic_ns", "utc", "stage", "dispatch_id",
                              "after_policy_entry", "method", "path", "traffic", "status"}
        def json_only(value):
            if type(value) is dict:
                assert not set(value) & {"token", "token_hash", "Authorization", "authorization",
                                         "credentials", "refresh_token", "access_token"}
                for item in value.values(): json_only(item)
            elif type(value) is list:
                for item in value: json_only(item)
            else:
                assert type(value) in (str, int, bool, float, type(None))
        json_only(records)
        assert all(name != "authorization" for name, _ in records[0]["application_headers"])
        assert "Bearer 404" not in path.read_text()
        # The independently generated status is kept. This is not a future-string
        # absence assertion, and no token hash is used as a leak-detection sentinel.
        assert not journal._broken


def test_evidence_writer_receives_only_constructed_safe_values(
        monkeypatch, fixture, frozen, token, tmp_path):
    received = []
    original = live.EvidenceJournal._write
    def typed_json(value):
        if type(value) is dict:
            assert all(type(key) is str for key in value)
            for item in value.values(): typed_json(item)
        elif type(value) is list:
            for item in value: typed_json(item)
        else:
            assert type(value) in (str, int, bool, float, type(None))
            if type(value) is str:
                assert SECRET not in value and "Bearer " not in value
    def observe(journal, safe):
        typed_json(safe)  # Before serialization: no token/credential/header/exception object.
        received.append(safe)
        return original(journal, safe)
    monkeypatch.setattr(live.EvidenceJournal, "_write", observe)
    class Credential:
        authorization = SECRET
        def __str__(self): pytest.fail("credential stringification forbidden")
        def __repr__(self): pytest.fail("credential repr forbidden")
    path = tmp_path / "dataflow.jsonl"
    with live.EvidenceJournal(path, trial_id="trial_0001", fixture=fixture,
            case_id="0001", request=frozen, token=token) as journal:
        # Fake replies have arbitrary Authorization/cookie/Location headers and
        # secret-bearing bodies. They never enter the evidence constructor.
        wire = Wire(body=SECRET.encode())
        assert live.ReadOnlyVerifier(fixture, socket_connector=wire.connector).inspect(
            token, fixture.marker("0001"), journal).classification == "verifier_uncertainty"
        # Status-stream reset carries arbitrary exception args and attributes.
        assert attempt(frozen, token, journal, Wire(fault="reset")).classification == "ambiguous"
        journal.enter_replay_policy()
        assert attempt(frozen, token, journal, Wire(body=SECRET.encode())).classification == "known_success"
        before = len(received)
        for forbidden in ({"token": token}, {"Authorization": "Bearer " + SECRET},
                          {"credentials": Credential()}, {"response_headers": [("Authorization", SECRET)]},
                          {"response_body": SECRET.encode()}, {"exception": RuntimeError(SECRET)}):
            with pytest.raises(TypeError): journal.event("failure", 0, **forbidden)
        with pytest.raises(live.QualificationError):
            journal.event("verifier_summary", 0, verifier=token)
        assert len(received) == before
    assert received[0]["engineering_only"] is True
    assert any(r.get("stage") == "verifier_summary" for r in received)
    assert any(r.get("stage") == "attempt_result" and r["classification"] == "ambiguous"
               for r in received)
