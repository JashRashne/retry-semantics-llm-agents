"""Non-network engineering qualification, never Sheets/paper observations."""

from dataclasses import FrozenInstanceError, asdict, replace
import gc
import http.client
import json
import socket

import pytest

from retry_semantics.study2.sheets_offline import (
    DispatchLedger, Fault, LifecycleStage as Stage, LocalResult, OfflineWire, Traffic,
    prepare_append_cells, qualify_single_attempt,
)


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("offline tests must not create network sockets")
    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    yield
    # Collect cleanup failures inside pytest's warning/unraisable handling, rather
    # than letting delayed object finalizers run after the focused suite exits.
    gc.collect()


@pytest.fixture
def frozen():
    # Synthetic fixture labels, not final spreadsheet identifiers.
    return prepare_append_cells(spreadsheet_id="offline_fixture", sheet_id=7,
                                marker="ENGINEERING-ONLY-offline-0001")


def test_frozen_candidate_is_one_literal_sheet_append(frozen):
    value = json.loads(frozen.body)
    assert value["includeSpreadsheetInResponse"] is False
    assert len(value["requests"]) == 1
    append = value["requests"][0]["appendCells"]
    assert set(append) == {"sheetId", "fields", "rows"}
    assert append["sheetId"] == 7 and append["fields"] == "userEnteredValue"
    assert append["rows"] == [{"values": [
        {"userEnteredValue": {"stringValue": s}} for s in
        ("ENGINEERING-ONLY-offline-0001", "engineering-v1", "literal-payload")
    ]}]
    with pytest.raises(FrozenInstanceError):
        frozen.body = b"changed"


@pytest.mark.parametrize("change", [
    {"method": "PUT"}, {"uri": "/v4/spreadsheets/other:batchUpdate"},
    {"uri": "/v4/spreadsheets/offline_fixture:batchUpdate?alt=json"},
    {"body": b"{ }"}, {"headers": (("content-type", "text/plain"),)},
])
def test_identity_surface_detects_changes(frozen, change):
    assert replace(frozen, **change).identity_hash != frozen.identity_hash


@pytest.mark.parametrize("material", [
    "accept", "content-type", "body", "host",
    "cl-large", "cl-small", "cl-malformed", "cl-negative",
    "user-project", "unknown", "transfer-encoding", "accept-encoding", "connection",
    "duplicate-host", "duplicate-cl", "conflicting-cl", "duplicate-auth",
    "duplicate-accept", "duplicate-content-type", "duplicate-accept-encoding",
    "duplicate-connection", "missing-host", "missing-cl", "missing-auth",
    "missing-accept", "missing-content-type", "missing-accept-encoding", "missing-connection",
    "malformed-header", "folded-header", "auth-form",
])
def test_hostile_emitted_serializer_mismatch_fails_closed(frozen, monkeypatch, material):
    original_identity = frozen.identity_hash
    original_body = frozen.body
    original_send = http.client.HTTPConnection.send
    altered = []

    def tampered_send(connection, data):
        emitted = data
        if material == "body" and data == original_body:
            emitted = data + b" "
        elif data.startswith(b"POST "):
            headers = {
                "host": b"Host: sheets.googleapis.com\r\n",
                "cl": f"Content-Length: {len(original_body)}\r\n".encode(),
                "auth": b"Authorization: Bearer offline-placeholder\r\n",
                "accept": b"accept: application/json\r\n",
                "content-type": b"content-type: application/json; charset=utf-8\r\n",
                "accept-encoding": b"Accept-Encoding: identity\r\n",
                "connection": b"Connection: close\r\n",
            }
            replacements = {
                "accept": (headers["accept"], b"accept: text/plain\r\n"),
                "content-type": (headers["content-type"], b"content-type: text/plain\r\n"),
                "host": (headers["host"], b"Host: evil.invalid\r\n"),
                "cl-large": (headers["cl"], b"Content-Length: 999\r\n"),
                "cl-small": (headers["cl"], f"Content-Length: {len(original_body)-1}\r\n".encode()),
                "cl-malformed": (headers["cl"], b"Content-Length: not-an-integer\r\n"),
                "cl-negative": (headers["cl"], b"Content-Length: -1\r\n"),
                "conflicting-cl": (headers["cl"], headers["cl"] + b"content-length: 999\r\n"),
                "auth-form": (headers["auth"], b"Authorization: Basic offline-placeholder\r\n"),
                "accept-encoding": (headers["accept-encoding"], b"Accept-Encoding: gzip\r\n"),
                "connection": (headers["connection"], b"Connection: keep-alive\r\n"),
            }
            additions = {
                "user-project": b"X-Goog-User-Project: hostile-project\r\n",
                "unknown": b"X-Harmless-Looking: extra\r\n",
                "transfer-encoding": b"Transfer-Encoding: chunked\r\n",
                "malformed-header": b"MalformedHeaderWithoutColon\r\n",
                "folded-header": b" folded: invalid\r\n",
            }
            if material in replacements:
                before, after = replacements[material]
                emitted = data.replace(before, after)
            elif material in additions:
                emitted = data[:-2] + additions[material] + b"\r\n"
            elif material.startswith("duplicate-"):
                header = headers[material.removeprefix("duplicate-")]
                # Include casing-conflicting duplicates (Host/host, etc.).
                emitted = data.replace(header, header + header.lower())
            elif material.startswith("missing-"):
                emitted = data.replace(headers[material.removeprefix("missing-")], b"")
        if emitted != data:
            altered.append(emitted)
        return original_send(connection, emitted)

    monkeypatch.setattr(http.client.HTTPConnection, "send", tampered_send)
    ledger = DispatchLedger()
    wire = OfflineWire(ledger, fault=Fault.AFTER_SEND)
    with pytest.raises(ValueError, match="serialized .* differ"):
        qualify_single_attempt(frozen, wire)
    assert len(altered) == 1
    assert frozen.identity_hash == original_identity and frozen.body is original_body
    assert wire.completed_bodies == [] and wire.response_calls == 0
    assert wire.connections[0].closed
    assert not any(e.stage is Stage.LOCAL_SEND_COMPLETED for e in ledger.lifecycle)
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(LocalResult("ambiguous", None, True), frozen)
    assert ledger.policy_entry_ns is None


@pytest.mark.parametrize("mode", ["header-casing", "different-bearer"])
def test_case_insensitive_names_and_ephemeral_bearer_preserve_identity(frozen, monkeypatch, mode):
    original_send = http.client.HTTPConnection.send
    identity = frozen.identity_hash
    secret = "ya29.hostile.test.secret"

    def allowed_change(connection, data):
        if data.startswith(b"POST "):
            if mode == "different-bearer":
                data = data.replace(b"offline-placeholder", secret.encode())
            else:
                lines = data[:-4].split(b"\r\n")
                data = b"\r\n".join([lines[0], *[
                    name.swapcase() + b":" + value
                    for name, value in (line.split(b":", 1) for line in lines[1:])
                ]]) + b"\r\n\r\n"
        return original_send(connection, data)

    monkeypatch.setattr(http.client.HTTPConnection, "send", allowed_change)
    ledger = DispatchLedger()
    result = qualify_single_attempt(frozen, OfflineWire(ledger, fault=Fault.AFTER_SEND))
    assert result == LocalResult("ambiguous", None, True)
    ledger.qualify_retry_entry(result, frozen)
    assert frozen.identity_hash == identity == ledger.records[0].request_identity_hash
    evidence = json.dumps({"dispatches": [asdict(r) for r in ledger.records],
                           "lifecycle": [asdict(e) for e in ledger.lifecycle]})
    assert secret not in evidence and "ya29.hostile" not in evidence
    assert "Bearer" not in evidence and "Authorization" not in evidence


@pytest.mark.parametrize("attack", ["wrong-host", "unexpected-header", "duplicate-auth", "malformed-auth", "body"])
def test_failed_envelope_validation_never_echoes_authorization(frozen, monkeypatch, attack):
    original_send = http.client.HTTPConnection.send
    secret = "ya29.hostile.test.secret"
    raw_value = f"Bearer {secret}"

    def hostile_send(connection, data):
        if data.startswith(b"POST "):
            data = data.replace(b"Bearer offline-placeholder", raw_value.encode())
            if attack == "wrong-host":
                data = data.replace(b"Host: sheets.googleapis.com", b"Host: evil.invalid")
            elif attack == "unexpected-header":
                data = data[:-2] + b"X-Goog-User-Project: hostile-project\r\n\r\n"
            elif attack == "duplicate-auth":
                data = data[:-2] + b"authorization: " + raw_value.encode() + b"\r\n\r\n"
            elif attack == "malformed-auth":
                data = data.replace(raw_value.encode(), f"Basic {secret}".encode())
        elif attack == "body" and data == frozen.body:
            data += b" "
        return original_send(connection, data)

    monkeypatch.setattr(http.client.HTTPConnection, "send", hostile_send)
    ledger = DispatchLedger()
    wire = OfflineWire(ledger, fault=Fault.AFTER_SEND)
    with pytest.raises(ValueError) as error:
        qualify_single_attempt(frozen, wire)
    # Only fixed safe error text and explicitly permitted evidence are exported.
    evidence = json.dumps({
        "dispatches": [asdict(r) for r in ledger.records],
        "lifecycle": [asdict(e) for e in ledger.lifecycle],
        "error_type": type(error.value).__name__, "error_message": str(error.value),
        "error_repr": repr(error.value), "error_args": error.value.args,
    })
    assert secret not in evidence and "ya29.hostile" not in evidence
    assert raw_value not in evidence and "Bearer" not in evidence
    assert error.value.__context__ is None and error.value.__cause__ is None
    assert wire.completed_bodies == [] and wire.response_calls == 0
    assert len(ledger.records) == (1 if attack == "body" else 0)
    assert not any(e.stage is Stage.LOCAL_SEND_COMPLETED for e in ledger.lifecycle)
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(LocalResult("ambiguous", None, True), frozen)
    assert ledger.policy_entry_ns is None


@pytest.mark.parametrize("status,classification", [
    (200, "known_success"), (201, "known_success"), (204, "known_success"),
    (400, "known_http_error"), (401, "auth_issue"), (403, "known_http_error"),
    (429, "known_http_error"), (500, "known_http_error"), (503, "known_http_error"),
    (301, "redirect_refused"), (302, "redirect_refused"),
    (303, "redirect_refused"), (307, "redirect_refused"), (308, "redirect_refused"),
])
def test_status_never_resends_or_enters_retry(frozen, status, classification):
    ledger = DispatchLedger()
    wire = OfflineWire(ledger, status=status)
    result = qualify_single_attempt(frozen, wire)
    assert result.classification == classification and result.status == status
    assert [event.stage for event in ledger.lifecycle] == [
        Stage.DISPATCH_INITIATED, Stage.LOCAL_SEND_COMPLETED, Stage.STATUS_OBSERVED,
    ]
    assert ledger.lifecycle[-1].status == status
    assert len(ledger.records) == len(wire.connections) == 1
    assert wire.connections[0].connect_count == 1
    assert wire.connections[0].auto_open == 0
    assert wire.connections[0].debuglevel == 0
    assert wire.connections[0].closed
    assert wire.completed_bodies == [frozen.body]
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(result, frozen)
    assert ledger.policy_entry_ns is None


@pytest.mark.parametrize("fault", [Fault.BEFORE_SEND, Fault.CONNECT, Fault.SOCKET_GONE])
def test_non_dispatch_and_no_implicit_reconnect(frozen, fault):
    ledger = DispatchLedger()
    wire = OfflineWire(ledger, fault=fault)
    result = qualify_single_attempt(frozen, wire)
    assert result == LocalResult("known_non_dispatch", None, False)
    assert ledger.records == () and wire.response_calls == 0
    assert ledger.lifecycle == ()
    assert wire.connections[0].connect_count == 1
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(result, frozen)


@pytest.mark.parametrize("fault", [Fault.AFTER_SEND, Fault.WAIT_LOSS])
def test_one_send_ambiguity_and_explicit_replay_bytes(frozen, fault):
    ledger = DispatchLedger()
    wire = OfflineWire(ledger, fault=fault)
    result = qualify_single_attempt(frozen, wire)
    assert result == LocalResult("ambiguous", None, True)
    assert wire.response_calls == (0 if fault is Fault.AFTER_SEND else 1)
    assert len(ledger.records) == 1
    record = ledger.records[0]
    assert record.body_hash == frozen.body_hash
    assert record.traffic is Traffic.MUTATION and not record.after_policy_entry
    assert (record.method, record.uri) == (frozen.method, frozen.uri)
    assert [event.stage for event in ledger.lifecycle] == [
        Stage.DISPATCH_INITIATED, Stage.LOCAL_SEND_COMPLETED,
    ]
    ledger.qualify_retry_entry(result, frozen)
    assert ledger.lifecycle[-1].stage is Stage.POLICY_ENTRY
    assert ledger.lifecycle[-1].monotonic_ns == ledger.policy_entry_ns
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(result, frozen)
    assert ledger.policy_entry_ns >= record.monotonic_ns
    # Qualification handoff only: no policy/LLM executor. Manually exercise a
    # second controlled dispatch AFTER the explicit qualification entry event.
    replay_wire = OfflineWire(ledger)
    assert qualify_single_attempt(frozen, replay_wire).classification == "known_success"
    assert replay_wire.completed_bodies[0] is frozen.body
    assert wire.completed_bodies[0] is frozen.body
    assert ledger.records[1].after_policy_entry
    assert [r.sequence for r in ledger.records] == [1, 2]
    assert ledger.records[1].monotonic_ns >= ledger.policy_entry_ns
    assert [(r.method, r.uri, r.body_hash) for r in ledger.records] == [
        (frozen.method, frozen.uri, frozen.body_hash)
    ] * 2
    assert [event.stage for event in ledger.lifecycle] == [
        Stage.DISPATCH_INITIATED, Stage.LOCAL_SEND_COMPLETED, Stage.POLICY_ENTRY,
        Stage.DISPATCH_INITIATED, Stage.LOCAL_SEND_COMPLETED, Stage.STATUS_OBSERVED,
    ]
    assert [e.dispatch_sequence for e in ledger.lifecycle] == [1, 1, 1, 2, 2, 2]
    assert [e.sequence for e in ledger.lifecycle] == list(range(1, 7))
    assert [e.monotonic_ns for e in ledger.lifecycle] == sorted(
        e.monotonic_ns for e in ledger.lifecycle)
    with pytest.raises(FrozenInstanceError):
        ledger.lifecycle[0].stage = Stage.STATUS_OBSERVED


def test_wait_loss_initializes_response_before_status_read_and_closes_cleanly(frozen, monkeypatch):
    initialized = []
    original_init = http.client.HTTPResponse.__init__

    def checked_init(response, *args, **kwargs):
        original_init(response, *args, **kwargs)
        initialized.append(response.fp is not None and not response.fp.closed)

    monkeypatch.setattr(http.client.HTTPResponse, "__init__", checked_init)
    ledger = DispatchLedger()
    wire = OfflineWire(ledger, fault=Fault.WAIT_LOSS)
    result = qualify_single_attempt(frozen, wire)
    assert initialized == [True]
    assert len(wire.response_streams) == wire.response_calls == 1
    assert wire.response_streams[0].readline_calls == 1
    assert wire.response_streams[0].closed and wire.connections[0].closed
    assert result == LocalResult("ambiguous", None, True)
    assert len(ledger.records) == 1
    assert [e.stage for e in ledger.lifecycle] == [
        Stage.DISPATCH_INITIATED, Stage.LOCAL_SEND_COMPLETED,
    ]
    ledger.qualify_retry_entry(result, frozen)
    assert ledger.lifecycle[-1].stage is Stage.POLICY_ENTRY


@pytest.mark.parametrize("fault", list(Fault))
def test_complete_fault_matrix_closes_connections_and_response_streams(frozen, fault):
    ledger = DispatchLedger()
    wire = OfflineWire(ledger, fault=fault)
    qualify_single_attempt(frozen, wire)
    assert all(connection.closed for connection in wire.connections)
    assert all(stream.closed for stream in wire.response_streams)


@pytest.mark.parametrize("status", [200, 201, 202])
def test_visible_2xx_missing_body_is_not_target_ambiguity(frozen, status):
    ledger = DispatchLedger()
    result = qualify_single_attempt(frozen, OfflineWire(ledger, status=status, fault=Fault.BODY_LOSS))
    assert result == LocalResult("known_success_incomplete_response", status, True)
    assert len(ledger.records) == 1
    assert ledger.lifecycle[-1].stage is Stage.STATUS_OBSERVED
    assert ledger.lifecycle[-1].status == status
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(result, frozen)
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(LocalResult("ambiguous", None, True), frozen)


def test_incomplete_send_has_one_initiation_without_completion_and_cannot_qualify(frozen):
    ledger = DispatchLedger()
    wire = OfflineWire(ledger, fault=Fault.PARTIAL_SEND)
    result = qualify_single_attempt(frozen, wire)
    assert result == LocalResult("incomplete_send_unknown", None, False)
    assert len(ledger.records) == 1
    assert [event.stage for event in ledger.lifecycle] == [Stage.DISPATCH_INITIATED]
    assert wire.completed_bodies == [] and wire.response_calls == 0
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(result, frozen)
    # A falsely upgraded result cannot replace missing lifecycle evidence.
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(LocalResult("ambiguous", None, True), frozen)
    assert ledger.policy_entry_ns is None


def test_deliberately_hidden_second_mutation_fails_closed(frozen):
    ledger = DispatchLedger()
    wire = OfflineWire(ledger, fault=Fault.AFTER_SEND)
    result = qualify_single_attempt(frozen, wire)
    # Deliberate hostile wrapper simulates a resend below policy.
    qualify_single_attempt(frozen, wire)
    assert len(ledger.records) == 2
    assert sum(e.stage is Stage.DISPATCH_INITIATED for e in ledger.lifecycle) == 2
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(result, frozen)
    assert ledger.policy_entry_ns is None


@pytest.mark.parametrize("status,classification", [
    (401, "auth_issue"), (429, "known_http_error"),
    (500, "known_http_error"), (503, "known_http_error"),
])
def test_visible_error_status_survives_body_loss_without_reissue(frozen, status, classification):
    ledger = DispatchLedger()
    wire = OfflineWire(ledger, status=status, fault=Fault.BODY_LOSS)
    result = qualify_single_attempt(frozen, wire)
    assert result == LocalResult(classification, status, True)
    assert len(ledger.records) == len(wire.connections) == 1
    assert ledger.lifecycle[-1].status == status
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(result, frozen)
    # Policy-facing status cannot be erased to bypass the recorded status.
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(LocalResult("ambiguous", None, True), frozen)


@pytest.mark.parametrize("mode", ["missing_completion", "wrong_dispatch", "duplicate_completion"])
def test_gate_requires_matching_completion_lifecycle(frozen, mode):
    ledger = DispatchLedger()
    record = ledger.record(frozen.method, frozen.uri, frozen.body, Traffic.MUTATION,
                           frozen.identity_hash)
    if mode == "wrong_dispatch":
        ledger.observe_send_completion(record.sequence + 1)
    elif mode == "duplicate_completion":
        ledger.observe_send_completion(record.sequence)
        ledger.observe_send_completion(record.sequence)
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(LocalResult("ambiguous", None, True), frozen)
    assert ledger.policy_entry_ns is None


def test_status_observed_before_send_completion_cannot_qualify(frozen):
    ledger = DispatchLedger()
    record = ledger.record(frozen.method, frozen.uri, frozen.body, Traffic.MUTATION,
                           frozen.identity_hash)
    ledger.observe_status(record.sequence, 200)
    ledger.observe_send_completion(record.sequence)
    assert [e.stage for e in ledger.lifecycle] == [
        Stage.DISPATCH_INITIATED, Stage.STATUS_OBSERVED, Stage.LOCAL_SEND_COMPLETED,
    ]
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(LocalResult("ambiguous", None, True), frozen)
    assert ledger.policy_entry_ns is None


def test_completion_for_wrong_one_of_two_dispatches_cannot_qualify(frozen):
    ledger = DispatchLedger()
    records = [ledger.record(frozen.method, frozen.uri, frozen.body, Traffic.MUTATION,
                             frozen.identity_hash) for _ in range(2)]
    ledger.observe_send_completion(records[1].sequence)
    assert [e.dispatch_sequence for e in ledger.lifecycle] == [1, 2, 2]
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(LocalResult("ambiguous", None, True), frozen)
    assert ledger.policy_entry_ns is None


def test_zero_count_fake_ambiguity_and_wrong_identity_rejected(frozen):
    result = LocalResult("ambiguous", None, True)
    with pytest.raises(ValueError):
        DispatchLedger().qualify_retry_entry(result, frozen)
    ledger = DispatchLedger()
    qualify_single_attempt(frozen, OfflineWire(ledger, fault=Fault.AFTER_SEND))
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(result, replace(frozen, body=b"{}"))
    with pytest.raises(ValueError):
        ledger.qualify_retry_entry(result, replace(frozen, headers=()))


def test_count_distinguishes_categories_and_trace_contains_no_auth(frozen):
    ledger = DispatchLedger()
    # Declarative category inventory; these are not certified auth/read paths.
    ledger.record("POST", "/synthetic-token", b"", Traffic.AUTH)
    ledger.record("GET", "/synthetic-discovery", b"", Traffic.DISCOVERY)
    ledger.record("GET", "/synthetic-values", b"", Traffic.READ)
    result = qualify_single_attempt(frozen, OfflineWire(ledger, fault=Fault.AFTER_SEND))
    assert len(ledger.records) == 4
    assert sum(r.traffic is Traffic.MUTATION for r in ledger.records) == 1
    ledger.qualify_retry_entry(result, frozen)
    evidence = json.dumps({"dispatches": [asdict(r) for r in ledger.records],
                           "lifecycle": [asdict(e) for e in ledger.lifecycle]})
    assert "offline-placeholder" not in evidence and "Authorization" not in evidence
    assert "Bearer" not in evidence and "Location" not in evidence
    assert "remote_received" not in evidence and "remote_committed" not in evidence
    assert all(set(asdict(event)) == {
        "sequence", "monotonic_ns", "dispatch_sequence", "stage", "status",
    } for event in ledger.lifecycle)


@pytest.mark.parametrize("change", [
    {"spreadsheet_id": "bad/id"}, {"sheet_id": True}, {"sheet_id": -1},
    {"marker": "=FORMULA()"}, {"marker": ""},
])
def test_invalid_candidate_inputs_rejected_before_wire(change):
    kwargs = dict(spreadsheet_id="offline_fixture", sheet_id=7,
                  marker="ENGINEERING-ONLY-offline-0001")
    kwargs.update(change)
    with pytest.raises(ValueError):
        prepare_append_cells(**kwargs)
