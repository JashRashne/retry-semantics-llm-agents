"""Hostile OFFLINE Phase 2 qualification; TEST_ONLY fixtures, fake assertions."""
from dataclasses import replace
import http.client
import io
import multiprocessing
import os
from pathlib import Path
import socket
import ssl
import time
import warnings

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_live_go_phase1 as phase1
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2 import sheets_phase2_control as control
from retry_semantics.study2 import sheets_phase2_read as read
from test_study2_sheets_http_framing import chunked

FAKE_TOKEN = "obviously-nonsecret-phase2-bearer"
FAKE_DER = b"TEST_ONLY_nonsecret_peer_certificate_DER"


def trap_network():
    warnings.simplefilter("error")
    read.ssl.SSLSocket = FakeTLS
    def denied(*a, **kw):
        raise AssertionError("Phase 2 socket/DNS forbidden")
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname",
                 "gethostbyname_ex", "getnameinfo"):
        setattr(socket, name, denied)
    http.client.HTTPSConnection.connect = denied


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(read.ssl, "SSLSocket", FakeTLS)
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname",
                 "gethostbyname_ex", "getnameinfo"):
        monkeypatch.setattr(socket, name, lambda *a, **kw: pytest.fail("network forbidden"))
    monkeypatch.setattr(http.client.HTTPSConnection, "connect",
                        lambda *a, **kw: pytest.fail("real connect forbidden"))
    monkeypatch.setattr(phase1.os, "environ", {"PYTHONWARNINGS": "error"})


@pytest.fixture
def fixture():
    return control.QualificationFixture("TEST_ONLY_phase2", 7, 100, "qualification_run",
        control.SameAppProvenance("created_by_same_app", "a" * 64, "engineering_account", "b" * 64))


@pytest.fixture
def configuration(tmp_path):
    # Illustrative fake numbers, never production-selected constants.
    return read.ReadConfiguration(10, 100000, 512, str(tmp_path / "registry"))


@pytest.fixture
def provenance():
    now = time.time()
    return phase1.CredentialProvenance("engineering_account", "a" * 64, "1.2.3",
                                     now - 2, now - 1, now + 3600, 2)


@pytest.fixture
def token(provenance):
    return phase1.export_prepared_token(FAKE_TOKEN, provenance)


@pytest.fixture
def authorization(fixture, configuration):
    now = time.time()
    return phase1.LiveAuthorization(phase1.Capability.LIVE_READ_GO, fixture.manifest_hash,
        read.runtime_hash(configuration), read.source_hash(), "test_assertion", "test_operator",
        now - 10, now + 1000, phase1.CONFIRMATION)


@pytest.fixture
def registry(tmp_path, fixture):
    with control.LocalRegistry(tmp_path / "registry") as registry:
        registry.reserve(fixture)
        yield registry


def payload(fixture, rows=()):
    return {"spreadsheetId": fixture.spreadsheet_id, "sheets": [{"properties": {
        "sheetId": fixture.sheet_id, "title": fixture.title, "sheetType": "GRID",
        "gridProperties": {"rowCount": fixture.rows, "columnCount": 3}},
        "data": [{"rowData": [{"values": [{"userEnteredValue": {"stringValue": v}}
                    if v is not None else {} for v in row]} for row in rows]}]}]}


def marker_row(fixture):
    return (fixture.marker("qualification_read"), "engineering-v1", "literal-payload")


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class FakeTLS:
    """Fake verified socket only; creating it cannot allocate/connect a socket."""
    def __init__(self, wire, context):
        self.wire = wire
        self.context = wire.tls_values.get("context", context)
        self.server_side = wire.tls_values.get("server_side", False)
        self.server_hostname = wire.tls_values.get("server_hostname", frozen.HOST)
    def version(self):
        self.wire.tls_checks.append("version")
        return self.wire.tls_values.get("version", "TLSv1.3")
    def cipher(self):
        self.wire.tls_checks.append("cipher")
        return self.wire.tls_values.get("cipher", ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256))
    def selected_alpn_protocol(self):
        self.wire.tls_checks.append("alpn")
        return self.wire.tls_values.get("alpn", None)
    def getpeercert(self, *, binary_form):
        assert binary_form is True
        self.wire.tls_checks.append("certificate")
        if self.wire.tls_values.get("certificate_error"):
            raise OSError(FAKE_TOKEN)
        return self.wire.tls_values.get("certificate", FAKE_DER)
    def getpeername(self):
        self.wire.tls_checks.append("peer")
        return self.wire.tls_values.get("peer", ("203.0.113.7", 443))
    def settimeout(self, value): self.wire.timeouts.append(value)
    def sendall(self, data):
        self.wire.chunks.append(data)
        self.wire.tick("send")
        if self.wire.fault == "send": raise ConnectionError(FAKE_TOKEN)
    def makefile(self, *a, **kw):
        wire = self.wire
        self.wire.responses += 1
        self.wire.tick("status")
        if self.wire.fault == "status": raise TimeoutError(FAKE_TOKEN)
        declared = len(self.wire.body) + (20 if self.wire.fault == "truncated" else 0)
        headers = self.wire.headers if self.wire.headers is not None else (
            f"Content-Length: {declared}\r\nContent-Type: application/json; charset=utf-8\r\n")
        header = (f"HTTP/1.1 {self.wire.status} fake\r\n" + headers +
            f"Location: https://evil.invalid/?echo={FAKE_TOKEN}\r\nRetry-After: 0\r\n"
            f"Set-Cookie: {FAKE_TOKEN}\r\nConnection: close\r\n\r\n").encode()
        class Stream(io.BytesIO):
            def read(self, *a, **kw):
                wire.tick("body")
                if wire.fault == "body": raise ConnectionResetError(FAKE_TOKEN)
                return super().read(*a, **kw)
        return Stream(header + self.wire.body)
    def close(self): self.wire.closed = True


class Wire:
    """Real HTTP serializer/parser over fake connected socket, no network seam."""
    def __init__(self, body, *, status=200, fault=None, headers=None, clock=None, delay=None):
        self.body, self.status, self.fault = body, status, fault
        self.headers, self.clock, self.delay = headers, clock, delay or {}
        self.chunks, self.timeouts = [], []
        self.constructs = self.connects = self.responses = 0
        self.tls_values, self.tls_checks, self.connected_sockets = {}, [], []
        self.closed = False

    def tick(self, stage):
        if self.clock: self.clock.advance(self.delay.get(stage, 0))

    def construct(self, timeout):
        self.constructs += 1
        self.tick("construct")
        if self.fault == "construct": raise OSError(FAKE_TOKEN)
        wire = self
        class FakeConnection(http.client.HTTPConnection):
            def __init__(self):
                super().__init__(frozen.HOST, 443, timeout=timeout)
                self.auto_open = self.debuglevel = 0
                self._context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
            def connect(self):
                wire.connects += 1
                wire.tick("connect")
                if wire.fault == "connect": raise OSError(FAKE_TOKEN)
                self.sock = FakeTLS(wire, self._context)
                wire.connected_sockets.append(self.sock)
        return FakeConnection()


def prepare(registry, fixture, configuration, authorization):
    runtime, source = read.runtime_hash(configuration), read.source_hash()
    evidence = read.AttemptEvidence(registry, fixture, authorization.authorization_id,
                                    runtime, source, reserve=True)
    registry.consume(authorization, fixture, runtime, source, now=time.time())
    evidence.event(read.Stage.CONSUMED)
    return evidence


def run(monkeypatch, registry, fixture, configuration, token, provenance, authorization,
        wire, *, deadline=None):
    read._precheck(fixture, configuration, token, provenance, authorization,
                   now=time.time(), offline=True)
    prepare(registry, fixture, configuration, authorization)
    monkeypatch.setattr(read, "_construct", wire.construct)
    result = read._read_once(registry, fixture, configuration, token, provenance, authorization,
        deadline or read.Deadline(configuration.total_seconds), offline=True)
    evidence = read.AttemptEvidence(registry, fixture, authorization.authorization_id,
        read.runtime_hash(configuration), read.source_hash(), reserve=False)
    evidence.event(read.Stage.TERMINAL, result)
    return result


def test_canonical_hash_and_frozen_envelope(fixture):
    assert replace(fixture).manifest_hash == fixture.manifest_hash
    assert fixture.manifest_hash == sha256_hex(canonical_json_bytes(fixture.manifest))
    legacy = frozen.Fixture(fixture.spreadsheet_id, 7, fixture.title, 100, 3, fixture.marker_namespace)
    assert read.read_path(fixture) == legacy.read_path
    assert fixture.verifier_range == "'RetrySemanticsEngineering'!A1:C100"
    assert fixture.manifest["verifier_case_id"] == "qualification_read"


@pytest.mark.parametrize("change", [{"spreadsheet_id": "TEST_ONLY_other"}, {"sheet_id": 8},
    {"rows": 101}, {"reservation_id": "other"}])
def test_material_hash_changes(fixture, change):
    other = replace(fixture, **change)
    assert other.manifest_hash != fixture.manifest_hash
    if "rows" not in change: assert other.marker_namespace != fixture.marker_namespace


@pytest.mark.parametrize("change", [{"spreadsheet_id": ""}, {"spreadsheet_id": "../escape"},
    {"spreadsheet_id": "x?key=oops"}, {"spreadsheet_id": "x:batchUpdate"},
    {"spreadsheet_id": "x%2Fescape"}, {"spreadsheet_id": "x\r\nHost: evil"},
    {"spreadsheet_id": "arbitrary_id"}, {"sheet_id": True}, {"sheet_id": -1},
    {"sheet_id": 2147483648}, {"rows": True}, {"rows": 2}, {"rows": 1001},
    {"provenance": None}, {"reservation_id": "../escape"}, {"engineering_only": False},
    {"schema": "draft"}, {"purpose": "paper"}, {"identity_kind": "PROVISIONED"}])
def test_malformed_fixture(fixture, change):
    with pytest.raises(frozen.QualificationError): replace(fixture, **change)


@pytest.mark.parametrize("change", [{"mode": "arbitrary_id"}, {"mode": "get_succeeded"},
    {"public_app_config_sha256": "bad"}, {"provisioning_evidence_sha256": ""},
    {"account_alias": "Bearer-sensitive"}])
def test_same_app_required(fixture, change):
    with pytest.raises(frozen.QualificationError): replace(fixture.provenance, **change)


def test_provenance_is_bound(fixture):
    other = replace(fixture, provenance=replace(fixture.provenance, mode="selected_through_same_app"))
    assert other.manifest_hash != fixture.manifest_hash


@pytest.mark.parametrize("change", [{}, {"reservation_id": "another"},
    {"spreadsheet_id": "TEST_ONLY_other"}, {"rows": 101}])
def test_reservation_collision(registry, fixture, change):
    with pytest.raises(frozen.QualificationError): registry.reserve(replace(fixture, **change))


def test_disjoint_reservation_and_mismatch(registry, fixture):
    other = replace(fixture, spreadsheet_id="TEST_ONLY_other", reservation_id="other")
    with pytest.raises(frozen.QualificationError): registry.check_reserved(other)
    registry.reserve(other)
    registry.check_reserved(other)


@pytest.mark.parametrize("corruption", [b"", b"{", b"{}", b'{}\n{}\n'])
def test_corrupt_reservation_closed(registry, fixture, corruption):
    (registry.path / "reservation-qualification_run.json").write_bytes(corruption)
    with pytest.raises(frozen.QualificationError): registry.check_reserved(fixture)


@pytest.mark.parametrize("change", [
    {"capability": phase1.Capability.CLEAN_MUTATION_GO},
    {"capability": phase1.Capability.AMBIGUITY_ENGINEERING_GO},
    {"fixture_manifest_sha256": "c" * 64}, {"runtime_pin_sha256": "c" * 64},
    {"connector_source_sha256": "c" * 64}, {"expires_at": time.time() - 1},
    {"authorized_at": time.time() + 100}])
def test_auth_prechecks_no_handoff(registry, fixture, configuration, token, provenance,
                                  authorization, change, monkeypatch):
    monkeypatch.setattr(read, "_construct", lambda *a: pytest.fail("no handoff"))
    with pytest.raises(frozen.QualificationError):
        read._precheck(fixture, configuration, token, provenance, replace(authorization, **change),
                       now=time.time(), offline=True)
    assert not list(registry.path.glob("claim-*"))


@pytest.mark.parametrize("change", [{"operator_confirmation": "yes"}, {"engineering_only": False},
    {"gate_version": "v2"}, {"purpose": "paper"}, {"authorized_at": float("nan")},
    {"capability": "LIVE_READ_GO"}, {"authorization_id": "../escape"}])
def test_malformed_auth(authorization, change):
    with pytest.raises(frozen.QualificationError): replace(authorization, **change)


def test_auth_expiry_equality(fixture, configuration, authorization):
    for now in (authorization.expires_at, authorization.authorized_at - 1):
        with pytest.raises(frozen.QualificationError):
            control.validate_read_authorization(authorization, fixture,
                read.runtime_hash(configuration), read.source_hash(), now=now)


def test_default_closed_no_constructor_io(tmp_path, fixture, configuration, token, provenance, authorization):
    adapter = read.ReadAdapter(fixture, configuration, Path(configuration.registry_root))
    for auth in (None, authorization):
        with pytest.raises(frozen.QualificationError): adapter.inspect(token, provenance, authorization=auth)
    assert not (Path(configuration.registry_root)).exists()
    assert [name for name in dir(adapter) if not name.startswith("_")] == ["inspect"]


@pytest.mark.parametrize("change", [{"account_alias": "another"}, {"public_config_sha256": "c" * 64},
                                  {"prepared_at": time.time() + 10}])
def test_credential_provenance_mismatch(fixture, configuration, token, provenance, authorization, change):
    with pytest.raises(frozen.QualificationError):
        read._precheck(fixture, configuration, token, replace(provenance, **change), authorization,
                       now=time.time(), offline=True)


def test_hostile_credential_never_inspected(fixture, configuration, provenance, authorization):
    class Hostile:
        def __repr__(self): pytest.fail("repr forbidden")
        def __str__(self): pytest.fail("str forbidden")
        def refresh(self): pytest.fail("refresh forbidden")
    with pytest.raises(frozen.QualificationError):
        read._precheck(fixture, configuration, Hostile(), provenance, authorization,
                       now=time.time(), offline=True)


@pytest.mark.parametrize("matches,expected", [(0, read.Outcome.ZERO), (1, read.Outcome.ONE),
                                           (2, read.Outcome.MULTIPLE)])
def test_stdlib_get_parser_and_secret_safety(monkeypatch, registry, fixture, configuration,
                                            token, provenance, authorization, matches, expected):
    wire = Wire(canonical_json_bytes(payload(fixture, [marker_row(fixture)] * matches)))
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome is expected and result.matching_rows == tuple(range(matches))
    assert wire.constructs == wire.connects == wire.responses == len(wire.chunks) == 1 and wire.closed
    data = wire.chunks[0]
    assert data.split(b"\r\n")[0] == f"GET {read.read_path(fixture)} HTTP/1.1".encode()
    assert data.endswith(b"\r\n\r\n") and b"Content-Length" not in data and b":batchUpdate" not in data
    assert b"Host: sheets.googleapis.com\r\n" in data and b"Content-Type:" not in data
    evidence = (registry.path / "attempt-test_assertion.jsonl").read_bytes()
    assert FAKE_TOKEN.encode() not in evidence and b"Authorization" not in evidence
    assert sha256_hex(FAKE_TOKEN.encode()).encode() not in evidence
    assert b"spreadsheetId" not in evidence and b"rowData" not in evidence


@pytest.mark.parametrize("status", [201, 204, 301, 302, 303, 307, 308, 401, 403, 404, 429, 500, 503])
def test_status_terminal_no_second_request(monkeypatch, registry, fixture, configuration,
                                         token, provenance, authorization, status):
    wire = Wire(FAKE_TOKEN.encode(), status=status)
    assert run(monkeypatch, registry, fixture, configuration, token, provenance,
               authorization, wire) == read.ReadSummary(read.Outcome.HTTP_ERROR, status)
    assert wire.constructs == wire.connects == wire.responses == len(wire.chunks) == 1
    assert FAKE_TOKEN.encode() not in (registry.path / "attempt-test_assertion.jsonl").read_bytes()


@pytest.mark.parametrize("fault", ["construct", "connect", "send", "status", "body", "truncated"])
def test_failure_spent_restart_sanitized(monkeypatch, registry, fixture, configuration,
                                       token, provenance, authorization, fault):
    wire = Wire(canonical_json_bytes(payload(fixture)), fault=fault)
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome in (read.Outcome.CONSTRUCTION, read.Outcome.TRANSPORT, read.Outcome.MALFORMED)
    if fault in ("body", "truncated"): assert result.status == 200
    with control.LocalRegistry(registry.path) as reopened:
        with pytest.raises(control.Spent):
            reopened.consume(authorization, fixture, read.runtime_hash(configuration),
                             read.source_hash(), now=time.time())
    assert FAKE_TOKEN.encode() not in b"".join(p.read_bytes() for p in registry.path.iterdir())


@pytest.mark.parametrize("attack", ["POST", "PUT", "PATCH", "DELETE", "endpoint", "host",
    "query", "duplicate_query", "duplicate_header", "body", "crlf", "override", "auth", "header_case"])
def test_hostile_serializer_guard(monkeypatch, registry, fixture, configuration,
                                  token, provenance, authorization, attack):
    original = read._ReadSocket.sendall
    def tampered(self, data):
        if attack in ("POST", "PUT", "PATCH", "DELETE"): data = data.replace(b"GET ", attack.encode() + b" ", 1)
        elif attack == "endpoint": data = data.replace(b"?ranges=", b":batchUpdate?ranges=", 1)
        elif attack == "host": data = data.replace(b"Host: sheets.googleapis.com", b"Host: evil.invalid")
        elif attack in ("query", "duplicate_query"):
            data = data.replace(b" HTTP/1.1", b"&ranges=other&unexpected=true HTTP/1.1", 1)
        elif attack == "body": data += b"{}"
        elif attack == "auth": data = data.replace(FAKE_TOKEN.encode(), b"another-bearer")
        elif attack == "header_case": data = data.replace(b"Host:", b"hOsT:")
        else:
            extra = {"duplicate_header": b"host: sheets.googleapis.com\r\n",
                     "crlf": b"X-Injected: bad\nother\r\n",
                     "override": b"X-HTTP-Method-Override: POST\r\n"}[attack]
            data = data[:-2] + extra + b"\r\n"
        return original(self, data)
    monkeypatch.setattr(read._ReadSocket, "sendall", tampered)
    wire = Wire(canonical_json_bytes(payload(fixture)))
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert len(wire.chunks) == (1 if attack == "header_case" else 0)
    assert result.outcome is (read.Outcome.ZERO if attack == "header_case" else read.Outcome.TRANSPORT)


def test_second_send_blocked(monkeypatch, registry, fixture, configuration, token, provenance, authorization):
    original = read._ReadSocket.sendall
    def twice(self, data):
        original(self, data)
        original(self, data)
    monkeypatch.setattr(read._ReadSocket, "sendall", twice)
    wire = Wire(canonical_json_bytes(payload(fixture)))
    assert run(monkeypatch, registry, fixture, configuration, token, provenance,
               authorization, wire).outcome is read.Outcome.TRANSPORT
    assert len(wire.chunks) == 1 and wire.responses == 0


@pytest.mark.parametrize("body", [b"", b"{", b"[]", b"null", b"true", b"{}", b'{}{}',
    b'{"spreadsheetId":"x","spreadsheetId":"x"}', b'{"x":NaN}', b'\xef\xbb\xbf{}',
    '{}'.encode("utf-16"), b'\xff'])
def test_strict_json_uncertain(fixture, configuration, body):
    assert read.parse_body(body, fixture, configuration).outcome is read.Outcome.MALFORMED


@pytest.mark.parametrize("attack", ["missing_data", "missing_properties", "sheets_type", "extra_sheet",
    "sheet_id_bool", "row_count_bool", "column_count_bool", "merges_null", "merges_object",
    "tables_false", "extra_grid", "offset_bool", "offset_nonzero", "rows_type", "too_many_rows",
    "too_many_cells", "formula", "number", "wrong_identity", "wrong_title", "wrong_extent",
    "extra_root_field", "extra_cell_field", "marker_partial", "long_cell"])
def test_hostile_grid_not_zero(fixture, configuration, attack):
    value = payload(fixture)
    sheet = value["sheets"][0]
    props, grid = sheet["properties"], sheet["data"][0]
    if attack == "missing_data": del sheet["data"]
    elif attack == "missing_properties": del sheet["properties"]
    elif attack == "sheets_type": value["sheets"] = {}
    elif attack == "extra_sheet": value["sheets"].append(sheet.copy())
    elif attack == "sheet_id_bool": props["sheetId"] = True
    elif attack == "row_count_bool": props["gridProperties"]["rowCount"] = True
    elif attack == "column_count_bool": props["gridProperties"]["columnCount"] = True
    elif attack.startswith("merges_"): sheet["merges"] = None if attack == "merges_null" else {}
    elif attack == "tables_false": sheet["tables"] = False
    elif attack == "extra_grid": sheet["data"].append({})
    elif attack == "offset_bool": grid["startRow"] = False
    elif attack == "offset_nonzero": grid["startColumn"] = 1
    elif attack == "rows_type": grid["rowData"] = {}
    elif attack == "too_many_rows": grid["rowData"] = [{}] * 101
    elif attack == "too_many_cells": grid["rowData"] = [{"values": [{}] * 4}]
    elif attack in ("formula", "number"):
        grid["rowData"] = [{"values": [{"userEnteredValue": {
            "formulaValue" if attack == "formula" else "numberValue": "=1" if attack == "formula" else 1}}]}]
    elif attack == "wrong_identity": value["spreadsheetId"] = "TEST_ONLY_other"
    elif attack == "wrong_title": props["title"] = "other"
    elif attack == "wrong_extent": props["gridProperties"]["rowCount"] = 101
    elif attack == "extra_root_field": value["arbitrary"] = FAKE_TOKEN
    elif attack == "extra_cell_field": grid["rowData"] = [{"values": [{"effectiveValue": {}}]}]
    elif attack == "marker_partial": value = payload(fixture, [(fixture.marker("qualification_read"),)])
    elif attack == "long_cell": value = payload(fixture, [("x" * 513,)])
    assert read.parse_body(canonical_json_bytes(value), fixture, configuration).outcome is read.Outcome.MALFORMED


def test_sparse_rows_and_current_observation(fixture, configuration):
    result = read.parse_body(canonical_json_bytes(payload(fixture,
        [("unrelated",), marker_row(fixture), ()])), fixture, configuration)
    assert result.outcome is read.Outcome.ONE and result.matching_rows == (1,) and result.nonempty_rows == 2
    assert read.parse_body(canonical_json_bytes(payload(fixture)), fixture, configuration).outcome is read.Outcome.ZERO


@pytest.mark.parametrize("headers", ["", "Content-Length: 01\r\n", "Content-Length: -1\r\n",
    "Content-Length: 2\r\nContent-Length: 2\r\nContent-Type: application/json\r\n",
    "Transfer-Encoding: chunked\r\nContent-Type: application/json\r\n",
    "Content-Length: 2\r\nContent-Type: text/plain\r\n",
    "Content-Length: 2\r\nContent-Type: application/json\r\nContent-Encoding: gzip\r\n",
    "Content-Length: 100001\r\nContent-Type: application/json\r\n"])
def test_response_framing_fail_closed(monkeypatch, registry, fixture, configuration,
                                     token, provenance, authorization, headers):
    wire = Wire(b"{}", headers=headers)
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome is read.Outcome.MALFORMED and result.status == 200 and len(wire.chunks) == 1


@pytest.mark.parametrize('fault,expected', [
    ('length', read.Outcome.ZERO), ('chunked', read.Outcome.ZERO),
    ('conflict', read.Outcome.MALFORMED), ('unsupported-transfer', read.Outcome.MALFORMED),
    ('bad-chunk', read.Outcome.MALFORMED), ('incomplete', read.Outcome.MALFORMED),
    ('oversize', read.Outcome.MALFORMED), ('wrong-type', read.Outcome.MALFORMED),
    ('bad-json', read.Outcome.MALFORMED), ('wrong-status', read.Outcome.HTTP_ERROR),
    ('gzip', read.Outcome.MALFORMED), ('neither', read.Outcome.MALFORMED),
])
def test_read_raw_http_framing_evidence(monkeypatch, registry, fixture, configuration,
                                       token, provenance, authorization, fault, expected):
    body = canonical_json_bytes(payload(fixture))
    if fault == 'bad-json': body = b'x' * len(body)
    headers = f'Content-Length: {len(body)}\r\nContent-Type: application/json; charset=utf-8\r\n'
    raw_body = body
    if fault in ('chunked', 'conflict', 'bad-chunk'):
        headers = 'Transfer-Encoding: chunked\r\nContent-Type: Application/JSON ; CHARSET="UTF-8"\r\n'
        raw_body = chunked(body) if fault != 'bad-chunk' else b'z\r\ninvalid\r\n'
    if fault == 'conflict': headers += f'Content-Length: {len(body)}\r\n'
    if fault == 'unsupported-transfer': headers = 'Transfer-Encoding: gzip, chunked\r\nContent-Type: application/json\r\n'
    if fault == 'incomplete': headers = headers.replace(str(len(body)), str(len(body) + 1))
    if fault == 'oversize': headers = headers.replace(str(len(body)), '100001')
    if fault == 'wrong-type': headers = headers.replace('application/json', 'text/plain')
    if fault == 'gzip': headers += 'Content-Encoding: gzip\r\n'
    if fault == 'neither': headers = 'Content-Type: application/json\r\n'
    wire = Wire(raw_body, headers=headers, status=404 if fault == 'wrong-status' else 200)
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome is expected
    assert result.status == (404 if fault == 'wrong-status' else 200)
    records = read.AttemptEvidence(registry, fixture, authorization.authorization_id,
        read.runtime_hash(configuration), read.source_hash(), reserve=False).records()
    stages = [record['stage'] for record in records[1:]]
    assert read.Stage.STATUS.value in stages
    assert (read.Stage.PARSED.value in stages) == (fault in ('length', 'chunked', 'bad-json'))
    if expected is not read.Outcome.ZERO:
        assert all(record['summary']['outcome'] != read.Outcome.ZERO.value for record in records[1:])
    assert len(wire.chunks) == 1


def test_oversize_not_zero(fixture, configuration):
    assert read.parse_body(b" " * 100001, fixture, configuration).outcome is read.Outcome.MALFORMED


@pytest.mark.parametrize("change", [{"total_seconds": 0}, {"total_seconds": -1},
    {"total_seconds": float("inf")}, {"total_seconds": True}, {"max_response_bytes": 0},
    {"max_response_bytes": True}, {"max_cell_characters": 100001}, {"schema": "other"}])
def test_configuration_strict(configuration, change):
    with pytest.raises(frozen.QualificationError): replace(configuration, **change)


def test_config_in_runtime_hash(configuration):
    for change in ({"total_seconds": 11}, {"max_response_bytes": 100001}, {"max_cell_characters": 513}):
        assert read.runtime_hash(replace(configuration, **change)) != read.runtime_hash(configuration)


@pytest.mark.parametrize("stage", ["construct", "connect", "send", "status", "body"])
def test_total_deadline_slow_stages(monkeypatch, registry, fixture, configuration,
                                   token, provenance, authorization, stage):
    clock = Clock()
    wire = Wire(canonical_json_bytes(payload(fixture)), clock=clock, delay={stage: 10})
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization,
                 wire, deadline=read.Deadline(10, clock=clock))
    assert result.outcome is read.Outcome.DEADLINE
    assert wire.connects == (0 if stage == "construct" else 1)
    assert len(wire.chunks) == (0 if stage in ("construct", "connect") else 1)


def test_stage_budget_does_not_reset(monkeypatch, registry, fixture, configuration, token, provenance, authorization):
    clock = Clock()
    wire = Wire(canonical_json_bytes(payload(fixture)), clock=clock,
                delay={"construct": 2, "connect": 2, "send": 2, "status": 2, "body": 2})
    deadline = read.Deadline(10, clock=clock)
    assert run(monkeypatch, registry, fixture, configuration, token, provenance,
               authorization, wire, deadline=deadline).outcome is read.Outcome.DEADLINE
    assert deadline.end == 110 and min(wire.timeouts) < max(wire.timeouts)


@pytest.mark.parametrize("elapsed", [10, 11])
def test_exhausted_no_construct(monkeypatch, registry, fixture, configuration, token, provenance, authorization, elapsed):
    clock = Clock()
    deadline = read.Deadline(10, clock=clock)
    clock.advance(elapsed)
    wire = Wire(canonical_json_bytes(payload(fixture)))
    assert run(monkeypatch, registry, fixture, configuration, token, provenance,
               authorization, wire, deadline=deadline).outcome is read.Outcome.DEADLINE
    assert wire.constructs == 0


@pytest.mark.parametrize("corruption", [b"", b"{", b"{}", b"null", b'{"consumed_at":NaN}'])
def test_corrupt_claim_spent(registry, fixture, configuration, authorization, corruption):
    claim = registry.path / "claim-test_assertion.json"
    claim.write_bytes(corruption)
    claim.chmod(0o600)
    with pytest.raises(control.Spent):
        registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())
    with pytest.raises(frozen.QualificationError):
        registry.check_claim(authorization, fixture, read.runtime_hash(configuration), read.source_hash())
    assert claim.read_bytes() == corruption


@pytest.mark.parametrize("point", ["file_write", "file_fsync", "directory_fsync"])
def test_claim_crash_points_no_unconsume(monkeypatch, registry, fixture, configuration, authorization, point):
    original_write, original_fsync = os.write, os.fsync
    if point == "file_write":
        monkeypatch.setattr(control.os, "write", lambda *a: (_ for _ in ()).throw(OSError(FAKE_TOKEN)))
    else:
        calls = []
        def failed(fd):
            calls.append(fd)
            if len(calls) == (1 if point == "file_fsync" else 2): raise OSError(FAKE_TOKEN)
            original_fsync(fd)
        monkeypatch.setattr(control.os, "fsync", failed)
    with pytest.raises(OSError):
        registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())
    monkeypatch.setattr(control.os, "write", original_write)
    monkeypatch.setattr(control.os, "fsync", original_fsync)
    assert (registry.path / "claim-test_assertion.json").exists()
    with pytest.raises(control.Spent):
        registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())


def test_claim_before_constructor(monkeypatch, registry, fixture, configuration, token, provenance, authorization):
    wire = Wire(canonical_json_bytes(payload(fixture)))
    original = wire.construct
    def observed(timeout):
        registry.check_claim(authorization, fixture, read.runtime_hash(configuration), read.source_hash())
        assert b"authorization_consumed" in (registry.path / "attempt-test_assertion.jsonl").read_bytes()
        return original(timeout)
    wire.construct = observed
    assert run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire).outcome is read.Outcome.ZERO


def test_missing_claim_no_handoff(monkeypatch, registry, fixture, configuration, token, provenance, authorization):
    monkeypatch.setattr(read, "_construct", lambda *a: pytest.fail("no handoff"))
    with pytest.raises(FileNotFoundError):
        read._read_once(registry, fixture, configuration, token, provenance, authorization,
                        read.Deadline(10), offline=True)
    with pytest.raises(frozen.QualificationError):
        registry.consume(authorization, replace(fixture, rows=101), read.runtime_hash(configuration),
                         read.source_hash(), now=time.time())


def consumer(path, fixture, authorization, runtime, source, send):
    trap_network()
    try:
        with control.LocalRegistry(Path(path)) as registry:
            try:
                registry.consume(authorization, fixture, runtime, source, now=time.time())
                send.send_bytes(b"won")
            except control.Spent: send.send_bytes(b"spent")
    finally: send.close()


def test_two_process_consumers_restart(registry, fixture, configuration, authorization):
    context = multiprocessing.get_context("spawn")
    targets = []
    for _ in range(2):
        receive, send = context.Pipe(duplex=False)
        process = context.Process(target=consumer, args=(registry.path, fixture, authorization,
            read.runtime_hash(configuration), read.source_hash(), send))
        process.start()
        send.close()
        targets.append((process, receive))
    results = []
    try:
        for process, receive in targets:
            assert receive.poll(10)
            results.append(receive.recv_bytes())
            process.join(10)
            assert process.exitcode == 0
        assert sorted(results) == [b"spent", b"won"]
    finally:
        for process, receive in targets:
            if process.is_alive(): process.kill()
            process.join()
            process.close()
            receive.close()
    with control.LocalRegistry(registry.path) as reopened:
        with pytest.raises(control.Spent):
            reopened.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())
    assert not hasattr(registry, "unconsume")


def crash_after_consumption(path, fixture, authorization, runtime, source):
    trap_network()
    with control.LocalRegistry(Path(path)) as registry:
        registry.consume(authorization, fixture, runtime, source, now=time.time())
        os._exit(23)


def test_process_death_claim_survives(registry, fixture, configuration, authorization):
    process = multiprocessing.get_context("spawn").Process(target=crash_after_consumption,
        args=(registry.path, fixture, authorization, read.runtime_hash(configuration), read.source_hash()))
    process.start()
    process.join(10)
    try:
        assert process.exitcode == 23
    finally:
        if process.is_alive(): process.kill()
        process.join()
        process.close()
    with pytest.raises(control.Spent):
        registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())
    assert not list(registry.path.glob("attempt-*"))


def test_evidence_permissions_exclusive_allowlist(registry, fixture, configuration, authorization):
    evidence = prepare(registry, fixture, configuration, authorization)
    assert registry.path.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in registry.path.iterdir())
    with pytest.raises(FileExistsError):
        read.AttemptEvidence(registry, fixture, authorization.authorization_id,
            read.runtime_hash(configuration), read.source_hash(), reserve=True)
    with pytest.raises(frozen.QualificationError): evidence.event("untrusted", {})
    with pytest.raises(frozen.QualificationError): evidence.event(read.Stage.STATUS)
    with pytest.raises(TypeError): evidence.event(read.Stage.TERMINAL, token=FAKE_TOKEN)
    with pytest.raises(frozen.QualificationError): read.AttemptEvidence._decode_summary({"outcome": FAKE_TOKEN})


@pytest.mark.parametrize("mode", [0o644, 0o666, 0o777])
def test_unsafe_registry_mode(tmp_path, mode):
    path = tmp_path / "unsafe"
    path.mkdir()
    path.chmod(mode)
    with pytest.raises(frozen.QualificationError): control.LocalRegistry(path)


def test_symlink_hardlink_closed(registry, fixture, tmp_path):
    link = tmp_path / "link"
    link.symlink_to(registry.path, target_is_directory=True)
    with pytest.raises(frozen.QualificationError): control.LocalRegistry(link)
    os.link(registry.path / "reservation-qualification_run.json", tmp_path / "hard")
    with pytest.raises(frozen.QualificationError): registry.check_reserved(fixture)


def test_partial_evidence_no_renewal(monkeypatch, registry, fixture, configuration, authorization):
    evidence = prepare(registry, fixture, configuration, authorization)
    original = os.write
    monkeypatch.setattr(read.os, "write", lambda fd, data: original(fd, data[:4]))
    with pytest.raises(frozen.QualificationError): evidence.event(read.Stage.CONSTRUCT_STARTED)
    monkeypatch.setattr(read.os, "write", original)
    with pytest.raises(frozen.QualificationError):
        read.AttemptEvidence(registry, fixture, authorization.authorization_id,
            read.runtime_hash(configuration), read.source_hash(), reserve=False)
    with pytest.raises(control.Spent):
        registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())


def test_real_constructor_no_network():
    connection = read._construct(3)
    try:
        assert connection.host == frozen.HOST and connection.port == 443 and connection.sock is None
        assert connection.auto_open == connection.debuglevel == 0
        assert connection._context.check_hostname and connection._context.verify_mode == ssl.CERT_REQUIRED
    finally: connection.close()


@pytest.mark.parametrize("name", ["HTTPS_PROXY", "SSLKEYLOGFILE", "SSL_CERT_FILE", "PYTHONPATH"])
def test_environment_gate(name, monkeypatch, fixture, configuration, token, provenance, authorization):
    monkeypatch.setattr(read.os, "environ", {name: FAKE_TOKEN})
    with pytest.raises(frozen.QualificationError):
        read._precheck(fixture, configuration, token, provenance, authorization, now=time.time(), offline=True)


def test_public_pipeline_before_supervisor(monkeypatch, registry, fixture, configuration, token, provenance, authorization):
    precheck = read._precheck
    # Private test-only identity bypass. No such switch on the public adapter.
    monkeypatch.setattr(read, "_precheck", lambda *a, **kw: precheck(*a, **kw, offline=True))
    def supervisor(*a):
        registry.check_claim(authorization, fixture, read.runtime_hash(configuration), read.source_hash())
        return read.ReadSummary(read.Outcome.WORKER)
    monkeypatch.setattr(read, "_supervise", supervisor)
    adapter = read.ReadAdapter(fixture, configuration, registry.path)
    assert adapter.inspect(token, provenance, authorization=authorization).outcome is read.Outcome.WORKER
    with pytest.raises(control.Refused):
        adapter.inspect(token, provenance, authorization=authorization)


@pytest.mark.parametrize("expired_at", ["before_start", "after_start", "poll"])
def test_watchdog_kills_child_without_reset(monkeypatch, fixture, configuration, token,
                                           provenance, authorization, tmp_path, expired_at):
    clock = Clock()
    deadline = read.Deadline(10, clock=clock)
    actions = []
    class Endpoint:
        def close(self): actions.append("endpoint_close")
        def send_bytes(self, data): actions.append(data)
        def poll(self, timeout):
            actions.append(("poll", timeout))
            clock.advance(10)
            return False
    class FakeProcess:
        exitcode = None
        def __init__(self, **kw):
            assert kw["target"] is read._worker and kw["args"][-1] == 110
        def start(self):
            actions.append("start")
            if expired_at == "after_start": clock.advance(10)
        def is_alive(self): return "killed" not in actions
        def kill(self): actions.append("killed")
        def join(self, *a): actions.append("joined")
        def close(self): actions.append("process_close")
    class Context:
        Process = FakeProcess
        def Pipe(self, **kw): return Endpoint(), Endpoint()
    monkeypatch.setattr(read.multiprocessing, "get_context", lambda method: Context())
    if expired_at == "before_start": clock.advance(10)
    result = read._supervise(fixture, configuration, token, provenance, authorization, Path(configuration.registry_root), deadline)
    assert result.outcome is read.Outcome.DEADLINE
    assert ("start" in actions) == (expired_at != "before_start")
    assert ("killed" in actions) == (expired_at != "before_start")
    assert (b"READ" in actions) == (expired_at == "poll")


def offline_worker(*args):
    """Spawned test wrapper; no fixture or authorization can escape TEST_ONLY."""
    trap_network()
    fixture = args[3]
    wire = Wire(canonical_json_bytes(payload(fixture)))
    read._construct = wire.construct
    precheck = read._precheck
    def offline_precheck(*a, **kw):
        kw["offline"] = True
        return precheck(*a, **kw)
    read._precheck = offline_precheck
    read._worker(*args)


def test_actual_spawn_supervisor_worker_and_evidence(monkeypatch, registry, fixture, configuration,
                                                    token, provenance, authorization):
    prepare(registry, fixture, configuration, authorization)
    real = multiprocessing.get_context("spawn")
    class Context:
        def Pipe(self, **kw): return real.Pipe(**kw)
        def Process(self, **kw):
            assert kw["target"] is read._worker
            kw["target"] = offline_worker
            return real.Process(**kw)
    monkeypatch.setattr(read.multiprocessing, "get_context", lambda method: Context())
    result = read._supervise(fixture, configuration, token, provenance, authorization,
                             registry.path, read.Deadline(10))
    assert result.outcome is read.Outcome.ZERO
    evidence = read.AttemptEvidence(registry, fixture, authorization.authorization_id,
        read.runtime_hash(configuration), read.source_hash(), reserve=False)
    records = evidence.records()
    assert records[-1]["stage"] == read.Stage.PARSED.value
    evidence.event(read.Stage.TERMINAL, result)
    assert FAKE_TOKEN.encode() not in registry.read("attempt-test_assertion.jsonl")


@pytest.mark.parametrize("case", ["deadline", "parent_death", "already_stopped"])
def test_worker_lifeline_cancels_without_real_wait(case):
    actions = []
    clock = Clock()
    class Stopped:
        def is_set(self): return case == "already_stopped"
    class Activation:
        def poll(self, remaining):
            assert remaining == 10
            actions.append("polled")
            if case == "deadline": clock.advance(10)
            return case == "parent_death"
    read._lifeline(Activation(), 110, Stopped(), clock=clock, abort=lambda code: actions.append(code))
    assert (24 in actions) == (case != "already_stopped")


@pytest.mark.parametrize("crash_stage", list(read.Stage)[:-1])
def test_every_incomplete_attempt_prefix_stays_spent(registry, fixture, configuration, authorization, crash_stage):
    evidence = prepare(registry, fixture, configuration, authorization)
    for stage in list(read.Stage)[1:]:
        if stage is read.Stage.TERMINAL or evidence._stage is crash_stage:
            break
        summary = read.ReadSummary(read.Outcome.UNCERTAIN, 200) if stage in (
            read.Stage.STATUS, read.Stage.BODY, read.Stage.PARSED) else None
        evidence.event(stage, summary, tls=fake_observation() if stage is read.Stage.TLS_OBSERVED else None)
    # Recovery opens only for inspection; no automatic execution or unconsume.
    with control.LocalRegistry(registry.path) as reopened:
        with pytest.raises(control.Spent):
            reopened.consume(authorization, fixture, read.runtime_hash(configuration),
                             read.source_hash(), now=time.time())
        assert read.AttemptEvidence(reopened, fixture, authorization.authorization_id,
            read.runtime_hash(configuration), read.source_hash(), reserve=False).records()


def test_before_validation_and_before_consumption_no_network(registry, fixture, configuration, authorization):
    with pytest.raises(frozen.QualificationError):
        registry.consume(None, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())
    control.validate_read_authorization(authorization, fixture, read.runtime_hash(configuration),
                                        read.source_hash(), now=time.time())
    assert not list(registry.path.glob("claim-*"))
    registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())
    assert list(registry.path.glob("claim-*"))


def test_durable_claim_completion_before_public_network_handoff(monkeypatch, registry, fixture,
                                                               configuration, token, provenance, authorization):
    precheck = read._precheck
    monkeypatch.setattr(read, "_precheck", lambda *a, **kw: precheck(*a, **kw, offline=True))
    monkeypatch.setattr(read, "_supervise", lambda *a: pytest.fail("handoff forbidden after fsync failure"))
    # Use class seam since the public adapter reopens the registry.
    real_create = control.LocalRegistry.create
    def failed(self, name, value):
        if name.startswith("claim-"):
            real_create(self, name, value)
            raise OSError(FAKE_TOKEN)
        return real_create(self, name, value)
    monkeypatch.setattr(control.LocalRegistry, "create", failed)
    with pytest.raises(control.Refused) as caught:
        read.ReadAdapter(fixture, configuration, registry.path).inspect(token, provenance, authorization=authorization)
    assert FAKE_TOKEN not in str(caught.value)
    assert (registry.path / "claim-test_assertion.json").exists()


def test_registry_root_bound_before_reuse(tmp_path, registry, fixture, configuration, authorization):
    other_root = tmp_path / "second_registry"
    with pytest.raises(control.Refused):
        read.ReadAdapter(fixture, configuration, other_root)
    other_configuration = replace(configuration, registry_root=str(other_root))
    assert read.runtime_hash(other_configuration) != read.runtime_hash(configuration)
    with pytest.raises(control.Refused):
        control.validate_read_authorization(authorization, fixture,
            read.runtime_hash(other_configuration), read.source_hash(), now=time.time())


@pytest.mark.parametrize("root", ["relative", "/tmp/../escape", "/tmp/evil\r\n", "/tmp//double"])
def test_noncanonical_registry_root_refused(configuration, root):
    with pytest.raises(frozen.QualificationError): replace(configuration, registry_root=root)


def test_token_noninterference_in_evidence(registry, fixture, configuration, provenance, authorization):
    # No evidence constructor accepts token material. Prepared values vary but
    # independent nonsecret evidence stays byte-identical.
    first = read.AttemptEvidence(registry, fixture, authorization.authorization_id,
        read.runtime_hash(configuration), read.source_hash(), reserve=True)
    before = registry.read("attempt-test_assertion.jsonl")
    for value in (FAKE_TOKEN, "another-obviously-nonsecret-bearer"):
        material = phase1.export_prepared_token(value, provenance)
        assert value not in repr(material)
        assert first.records()[0]["fixture_hash"] == fixture.manifest_hash
        assert registry.read("attempt-test_assertion.jsonl") == before


def test_authorization_and_fixture_tampering_revalidated(fixture, configuration, authorization):
    other = replace(fixture)
    object.__setattr__(other, "spreadsheet_id", "../../escape")
    with pytest.raises(frozen.QualificationError): read.read_path(other)
    auth = replace(authorization)
    object.__setattr__(auth, "engineering_only", 1)
    with pytest.raises(frozen.QualificationError):
        control.validate_read_authorization(auth, fixture, read.runtime_hash(configuration),
                                            read.source_hash(), now=time.time())


def test_claim_binds_exact_nonsecret_authorization_assertion(registry, fixture, configuration, authorization):
    registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())
    registry.check_claim(authorization, fixture, read.runtime_hash(configuration), read.source_hash())
    for change in ({"operator_alias": "another_operator"}, {"expires_at": authorization.expires_at + 1}):
        with pytest.raises(control.Refused):
            registry.check_claim(replace(authorization, **change), fixture,
                                 read.runtime_hash(configuration), read.source_hash())


def test_corrupt_evidence_stage_has_fixed_refusal(registry, fixture, configuration, authorization):
    evidence = read.AttemptEvidence(registry, fixture, authorization.authorization_id,
        read.runtime_hash(configuration), read.source_hash(), reserve=True)
    path = registry.path / "attempt-test_assertion.jsonl"
    with path.open("ab") as stream:
        stream.write(canonical_json_bytes({"sequence": 1, "stage": FAKE_TOKEN,
                     "summary": read.ReadSummary(read.Outcome.UNCERTAIN).projection()}) + b"\n")
    with pytest.raises(control.Refused) as caught:
        evidence.records()
    assert FAKE_TOKEN not in str(caught.value)


@pytest.mark.parametrize("body", [b'1e400', b'-1e400', b'{"number":1e400}'])
def test_json_overflow_not_finite(body):
    with pytest.raises(control.Refused): control.strict_json(body)


def test_lone_unicode_surrogate_uncertain(fixture, configuration):
    body = canonical_json_bytes(payload(fixture, [("sentinel",)])).replace(b'sentinel', b'\\ud800')
    assert read.parse_body(body, fixture, configuration).outcome is read.Outcome.MALFORMED


@pytest.mark.parametrize("field", ["purpose", "gate_version", "operator_confirmation"])
def test_hostile_assertion_objects_not_serialized(fixture, configuration, authorization, field):
    class Hostile:
        def __eq__(self, other): return True
        def __str__(self): pytest.fail("no stringify")
        def __repr__(self): pytest.fail("no repr")
    # Existing frozen schema is not changed; Phase 2 adds strict type fences.
    auth = replace(authorization, **{field: Hostile()})
    with pytest.raises(control.Refused): control.authorization_hash(auth)
    with pytest.raises(control.Refused):
        control.validate_read_authorization(auth, fixture, read.runtime_hash(configuration),
                                            read.source_hash(), now=time.time())


def test_parent_terminal_preserves_durable_status(monkeypatch, registry, fixture, configuration,
                                                 token, provenance, authorization):
    precheck = read._precheck
    monkeypatch.setattr(read, "_precheck", lambda *a, **kw: precheck(*a, **kw, offline=True))
    def supervisor(*a):
        evidence = read.AttemptEvidence(registry, fixture, authorization.authorization_id,
            read.runtime_hash(configuration), read.source_hash(), reserve=False)
        for stage in list(read.Stage)[1:]:
            evidence.event(stage, read.ReadSummary(read.Outcome.UNCERTAIN, 200)
                           if stage is read.Stage.STATUS else None,
                           tls=fake_observation() if stage is read.Stage.TLS_OBSERVED else None)
            if stage is read.Stage.STATUS: break
        return read.ReadSummary(read.Outcome.DEADLINE)
    monkeypatch.setattr(read, "_supervise", supervisor)
    result = read.ReadAdapter(fixture, configuration, registry.path).inspect(token, provenance,
                                                                          authorization=authorization)
    assert result == read.ReadSummary(read.Outcome.DEADLINE, 200)


def test_evidence_failure_classified_before_send(monkeypatch, registry, fixture, configuration,
                                               token, provenance, authorization):
    prepare(registry, fixture, configuration, authorization)
    wire = Wire(canonical_json_bytes(payload(fixture)))
    monkeypatch.setattr(read, "_construct", wire.construct)
    append = read.AttemptEvidence._append
    def failed(self, data):
        if b'request_started' in data:
            raise read.EvidenceFailure()
        append(self, data)
    monkeypatch.setattr(read.AttemptEvidence, "_append", failed)
    result = read._read_once(registry, fixture, configuration, token, provenance, authorization,
                             read.Deadline(10), offline=True)
    assert result.outcome is read.Outcome.STORAGE and not wire.chunks
    with pytest.raises(control.Spent):
        registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())


@pytest.mark.parametrize("corruption", ["boolean_alias", "noncanonical"])
def test_evidence_header_and_serialization_strict(registry, fixture, configuration, authorization, corruption):
    evidence = read.AttemptEvidence(registry, fixture, authorization.authorization_id,
        read.runtime_hash(configuration), read.source_hash(), reserve=True)
    path = registry.path / "attempt-test_assertion.jsonl"
    if corruption == "boolean_alias":
        path.write_bytes(path.read_bytes().replace(b'"engineering_only":true', b'"engineering_only":1'))
    else:
        path.write_bytes(b' ' + path.read_bytes())
    with pytest.raises(control.Refused): evidence.records()


def fake_observation():
    return read.TLSObservation(frozen.HOST, "TLSv1.3", "TLS_AES_256_GCM_SHA384", "TLSv1.3", 256,
                               sha256_hex(FAKE_DER), None, "203.0.113.7", 443)


def test_authorization_expires_during_presend_fsync_no_http(monkeypatch, registry, fixture,
                                                         configuration, token, provenance, authorization):
    wall = Clock()
    wall.now = provenance.prepared_at + 2
    first_now = wall.now
    assert authorization.authorized_at <= first_now < authorization.expires_at
    monkeypatch.setattr(read.time, "time", wall)
    append = read.AttemptEvidence._append
    def slow_evidence(self, data):
        append(self, data)  # Actual exclusive journal append and file fsync finish.
        if b'request_started' in data:
            wall.now = authorization.expires_at
    monkeypatch.setattr(read.AttemptEvidence, "_append", slow_evidence)
    wire = Wire(canonical_json_bytes(payload(fixture)))
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result == read.ReadSummary(read.Outcome.AUTHORIZATION)
    assert wire.constructs == wire.connects == 1 and not wire.chunks and wire.responses == 0
    with control.LocalRegistry(registry.path) as reopened:
        reopened.check_claim(authorization, fixture, read.runtime_hash(configuration), read.source_hash())
        with pytest.raises(control.Spent):
            reopened.consume(authorization, fixture, read.runtime_hash(configuration),
                             read.source_hash(), now=first_now)
    records = read.AttemptEvidence(registry, fixture, authorization.authorization_id,
        read.runtime_hash(configuration), read.source_hash(), reserve=False).records()
    assert records[-2]["stage"] == read.Stage.REQUEST_STARTED.value
    assert records[-1]["summary"]["outcome"] == read.Outcome.AUTHORIZATION.value
    assert FAKE_TOKEN.encode() not in registry.read("attempt-test_assertion.jsonl")


def test_token_readiness_repeated_after_presend_evidence(monkeypatch, registry, fixture,
                                                       configuration, token, provenance, authorization):
    wall = Clock()
    wall.now = provenance.prepared_at + 2
    first_now = wall.now
    # Keep auth valid through token-budget exhaustion; this is a fake assertion.
    auth = replace(authorization, expires_at=provenance.expires_at + 100)
    monkeypatch.setattr(read.time, "time", wall)
    append = read.AttemptEvidence._append
    def slow_evidence(self, data):
        append(self, data)
        if b'request_started' in data:
            wall.now = provenance.expires_at - token.clock_uncertainty_seconds
    monkeypatch.setattr(read.AttemptEvidence, "_append", slow_evidence)
    wire = Wire(canonical_json_bytes(payload(fixture)))
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, auth, wire)
    assert result.outcome is read.Outcome.SEND_READINESS
    assert not wire.chunks and wire.constructs == wire.connects == 1 and wire.responses == 0
    with pytest.raises(control.Spent):
        registry.consume(auth, fixture, read.runtime_hash(configuration), read.source_hash(), now=first_now)


@pytest.mark.parametrize("binding", ["fixture", "runtime", "source", "capability", "assertion"])
def test_final_raw_send_revalidates_exact_authorization_binding(monkeypatch, registry, fixture,
                configuration, token, provenance, authorization, binding):
    sendall = read._ReadSocket.sendall
    def altered(self, data):
        if binding == "fixture":
            self._fixture = replace(fixture, spreadsheet_id="TEST_ONLY_other")
        elif binding == "runtime": self._runtime = "c" * 64
        elif binding == "source": self._source = "c" * 64
        elif binding == "capability":
            self._authorization = replace(authorization, capability=phase1.Capability.CLEAN_MUTATION_GO)
        else:
            self._authorization = replace(authorization, operator_alias="another_operator")
        return sendall(self, data)
    monkeypatch.setattr(read._ReadSocket, "sendall", altered)
    wire = Wire(canonical_json_bytes(payload(fixture)))
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome is read.Outcome.AUTHORIZATION and not wire.chunks
    assert wire.constructs == wire.connects == 1 and wire.responses == 0
    with pytest.raises(control.Spent):
        registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())


def test_raw_send_guard_spent_on_refusal_and_secret_exception_sanitized(monkeypatch, registry,
                     fixture, configuration, token, provenance, authorization):
    validator = read.validate_read_authorization
    guard = []
    sendall = read._ReadSocket.sendall
    def observed(self, data):
        guard.append((self, data))
        return sendall(self, data)
    def failed(*a, **kw):
        # All earlier checks pass; only the post-fsync check receives this error.
        evidence = registry.read("attempt-test_assertion.jsonl") if (registry.path / "attempt-test_assertion.jsonl").exists() else b""
        if b'request_started' in evidence:
            raise frozen.QualificationError() from OSError(FAKE_TOKEN)
        return validator(*a, **kw)
    monkeypatch.setattr(read, "validate_read_authorization", failed)
    monkeypatch.setattr(read._ReadSocket, "sendall", observed)
    wire = Wire(canonical_json_bytes(payload(fixture)))
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome is read.Outcome.AUTHORIZATION and not wire.chunks
    assert len(guard) == 1 and guard[0][0]._spent is True
    with pytest.raises(control.Refused): sendall(*guard[0])
    assert FAKE_TOKEN.encode() not in registry.read("attempt-test_assertion.jsonl")
    assert sha256_hex(FAKE_TOKEN.encode()).encode() not in registry.read("attempt-test_assertion.jsonl")


def test_safe_tls_observation_and_order_same_socket(monkeypatch, registry, fixture, configuration,
                                                  token, provenance, authorization):
    collected, wrapped = [], []
    observe = read.observe_tls
    init = read._ReadSocket.__init__
    def observed(raw, context):
        collected.append(raw)
        return observe(raw, context)
    def captured(self, raw, *a, **kw):
        records = registry.read("attempt-test_assertion.jsonl")
        assert b'tls_observation_persisted' in records
        wrapped.append(raw)
        init(self, raw, *a, **kw)
    monkeypatch.setattr(read, "observe_tls", observed)
    monkeypatch.setattr(read._ReadSocket, "__init__", captured)
    wire = Wire(canonical_json_bytes(payload(fixture)))
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome is read.Outcome.ZERO
    assert collected == wrapped == wire.connected_sockets and len(collected) == 1
    assert wire.tls_checks == ["version", "cipher", "alpn", "certificate", "peer"]
    assert wire.constructs == wire.connects == wire.responses == len(wire.chunks) == 1
    records = read.AttemptEvidence(registry, fixture, authorization.authorization_id,
        read.runtime_hash(configuration), read.source_hash(), reserve=False).records()
    tls_record = next(record for record in records[1:] if record["stage"] == read.Stage.TLS_OBSERVED.value)
    assert tls_record["tls"] == fake_observation().projection()
    assert tls_record["sequence"] < next(record["sequence"] for record in records[1:]
                                       if record["stage"] == read.Stage.REQUEST_STARTED.value)
    assert FAKE_DER not in registry.read("attempt-test_assertion.jsonl")
    assert FAKE_TOKEN.encode() not in registry.read("attempt-test_assertion.jsonl")
    assert read.TLSObservation.from_projection(tls_record["tls"]) == fake_observation()


@pytest.mark.parametrize("values", [
    {"version": None}, {"version": "SSLv3"}, {"version": "TLSv1.4"},
    {"cipher": None}, {"cipher": ()}, {"cipher": ["TLS_AES_256_GCM_SHA384", "TLSv1.3", 256]},
    {"cipher": ("TLS_AES_256_GCM_SHA384", "TLSv1.3", True)},
    {"cipher": ("TLS_AES_256_GCM_SHA384", "TLSv1.3", -1)},
    {"cipher": (FAKE_TOKEN, "TLSv1.3", 256)},
    {"cipher": ("TLS_AES_256_GCM_SHA384", "TLSv1.3\r\n", 256)},
    {"server_hostname": "evil.invalid"}, {"server_hostname": None}, {"server_side": True},
    {"context": None}, {"alpn": "h2"}, {"alpn": 42}, {"alpn": b"http/1.1"},
    {"alpn": "http/1.1\r\n"}, {"certificate": None}, {"certificate": b""},
    {"certificate": "not DER bytes"}, {"certificate": bytearray(FAKE_DER)},
    {"certificate": b"x" * 65537}, {"certificate_error": True},
    {"peer": None}, {"peer": ("dnsname.invalid", 443)}, {"peer": ("203.0.113.7", True)},
    {"peer": ("203.0.113.7", 80)}, {"peer": ("2001:db8::1", 443)},
    {"peer": ("fe80::1%unsafe", 443, 0, 0)}, {"peer": ("2001:db8::1", 443, False, 0)},
])
def test_failed_tls_observation_no_serialization_or_http(monkeypatch, registry, fixture,
                                configuration, token, provenance, authorization, values):
    wire = Wire(canonical_json_bytes(payload(fixture)))
    wire.tls_values.update(values)
    monkeypatch.setattr(http.client.HTTPConnection, "putrequest", lambda *a, **kw: pytest.fail("HTTP before TLS evidence"))
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome is read.Outcome.TLS
    assert not wire.chunks and wire.responses == 0 and wire.constructs == wire.connects == 1
    assert FAKE_TOKEN.encode() not in registry.read("attempt-test_assertion.jsonl")
    with pytest.raises(control.Spent):
        registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())


@pytest.mark.parametrize("field", ["version", "cipher", "server_hostname", "alpn", "certificate", "peer"])
def test_arbitrary_tls_objects_never_stringified(monkeypatch, registry, fixture, configuration,
                                                 token, provenance, authorization, field):
    class Hostile:
        def __str__(self): pytest.fail("TLS object str forbidden")
        def __repr__(self): pytest.fail("TLS object repr forbidden")
        def __eq__(self, other): pytest.fail("TLS object equality forbidden")
    wire = Wire(canonical_json_bytes(payload(fixture)))
    wire.tls_values[field] = Hostile()
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome is read.Outcome.TLS and not wire.chunks
    assert wire.constructs == wire.connects == 1


def test_wrong_socket_type_refused():
    with pytest.raises(read.TLSObservationRefused): read.observe_tls(object(), None)


def test_tls_evidence_failure_no_http(monkeypatch, registry, fixture, configuration,
                                     token, provenance, authorization):
    append = read.AttemptEvidence._append
    def failed(self, data):
        if b'tls_observation_persisted' in data:
            raise read.EvidenceFailure() from OSError(FAKE_TOKEN)
        append(self, data)
    monkeypatch.setattr(read.AttemptEvidence, "_append", failed)
    monkeypatch.setattr(http.client.HTTPConnection, "putrequest", lambda *a, **kw: pytest.fail("no serialization"))
    wire = Wire(canonical_json_bytes(payload(fixture)))
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome is read.Outcome.STORAGE and not wire.chunks
    assert wire.constructs == wire.connects == 1 and wire.responses == 0
    assert b'tls_observation_persisted' not in registry.read("attempt-test_assertion.jsonl")
    assert FAKE_TOKEN.encode() not in registry.read("attempt-test_assertion.jsonl")


def test_tls_observation_actual_fsync_failure_blocks_http(monkeypatch, registry, fixture,
                                    configuration, token, provenance, authorization):
    append, fsync = read.AttemptEvidence._append, os.fsync
    in_tls_append, failures = [], []
    def observed_append(self, data):
        in_tls_append.append(b'tls_observation_persisted' in data)
        try:
            append(self, data)
        finally:
            in_tls_append.pop()
    def failed_fsync(fd):
        if in_tls_append and in_tls_append[-1]:
            failures.append(fd)
            raise OSError(FAKE_TOKEN)
        fsync(fd)
    monkeypatch.setattr(read.AttemptEvidence, "_append", observed_append)
    monkeypatch.setattr(read.os, "fsync", failed_fsync)
    monkeypatch.setattr(http.client.HTTPConnection, "putrequest",
                        lambda *a, **kw: pytest.fail("no HTTP before successful TLS fsync"))
    wire = Wire(canonical_json_bytes(payload(fixture)))
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome is read.Outcome.STORAGE and len(failures) == 1
    assert not wire.chunks and wire.constructs == wire.connects == 1 and wire.responses == 0
    records = registry.read("attempt-test_assertion.jsonl")
    assert b'request_started' not in records and FAKE_TOKEN.encode() not in records
    with pytest.raises(control.Spent):
        registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=time.time())


def test_tls_noninterference_no_token_or_raw_cert_input():
    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    values = []
    for material in (FAKE_TOKEN, "another-obviously-nonsecret-bearer"):
        token = frozen.prepare_token(material, expires_at=time.time() + 1000, clock_uncertainty_seconds=1)
        wire = Wire(b"{}")
        raw = FakeTLS(wire, context)
        observation = read.observe_tls(raw, context)
        values.append(canonical_json_bytes(observation.projection()))
        assert material.encode() not in values[-1]
        assert sha256_hex(material.encode()).encode() not in values[-1]
        assert FAKE_DER not in values[-1]
        assert material not in repr(token)
    assert values[0] == values[1]


@pytest.mark.parametrize("peer,alpn", [(("203.0.113.7", 443), "http/1.1"),
                                       (("2001:db8::1", 443, 0, 0), None)])
def test_qualified_tls_endpoint_and_alpn(peer, alpn):
    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    wire = Wire(b"{}")
    wire.tls_values.update(peer=peer, alpn=alpn)
    observation = read.observe_tls(FakeTLS(wire, context), context)
    assert observation.peer_address == peer[0] and observation.alpn == alpn


def test_multiprocessing_projection_explicit_modules_and_authorization_hash(configuration, fixture, authorization, monkeypatch):
    projection = read.multiprocessing_projection()
    assert set(projection) == {"schema", "path", "python_sources", "native_implementations"}
    assert set(projection["python_sources"]) == {
        "multiprocessing", "multiprocessing.context", "multiprocessing.process", "multiprocessing.connection",
        "multiprocessing.spawn", "multiprocessing.popen_spawn_posix", "multiprocessing.popen_fork",
        "multiprocessing.resource_tracker", "multiprocessing.reduction", "multiprocessing.resource_sharer",
        "multiprocessing.util", "selectors", "pickle", "subprocess", "threading"}
    assert set(projection["native_implementations"]) == {"_multiprocessing", "_posixsubprocess", "select", "_pickle"}
    for group in ("python_sources", "native_implementations"):
        for name, digest in projection[group].items():
            module = read.importlib.import_module(name)
            assert digest == sha256_hex(Path(module.__file__).read_bytes())
    baseline = read.runtime_hash(configuration)
    for group in ("python_sources", "native_implementations"):
        for name in projection[group]:
            changed = {**projection, group: {**projection[group], name: "c" * 64}}
            monkeypatch.setattr(read, "multiprocessing_projection", lambda: changed)
            runtime = read.runtime_hash(configuration)
            assert runtime != baseline
            with pytest.raises(control.Refused):
                control.validate_read_authorization(authorization, fixture, runtime, read.source_hash(), now=time.time())


def test_public_inspect_full_spawn_fake_tls_get_and_parent_terminal(monkeypatch, registry, fixture,
                                                                  configuration, token, provenance, authorization):
    precheck = read._precheck
    # TEST_ONLY stays TEST_ONLY; no production ID or authorization is invented.
    def offline_precheck(*a, **kw):
        kw["offline"] = True
        return precheck(*a, **kw)
    monkeypatch.setattr(read, "_precheck", offline_precheck)
    real = multiprocessing.get_context("spawn")
    class Context:
        def Pipe(self, **kw): return real.Pipe(**kw)
        def Process(self, **kw):
            assert kw["target"] is read._worker
            kw["target"] = offline_worker
            return real.Process(**kw)
    monkeypatch.setattr(read.multiprocessing, "get_context", lambda method: Context())
    result = read.ReadAdapter(fixture, configuration, registry.path).inspect(token, provenance,
                                                                          authorization=authorization)
    assert result.outcome is read.Outcome.ZERO
    records = read.AttemptEvidence(registry, fixture, authorization.authorization_id,
        read.runtime_hash(configuration), read.source_hash(), reserve=False).records()
    assert [record["stage"] for record in records[1:]] == [stage.value for stage in read.Stage]
    tls_record = next(record for record in records[1:] if record["stage"] == read.Stage.TLS_OBSERVED.value)
    assert tls_record["tls"]["leaf_certificate_sha256"] == sha256_hex(FAKE_DER)
    assert records[-1]["summary"] == result.projection()
    registry.check_claim(authorization, fixture, read.runtime_hash(configuration), read.source_hash())
    with pytest.raises(control.Refused):
        read.ReadAdapter(fixture, configuration, registry.path).inspect(token, provenance, authorization=authorization)
    assert FAKE_TOKEN.encode() not in registry.read("attempt-test_assertion.jsonl")
    assert FAKE_DER not in registry.read("attempt-test_assertion.jsonl")


def test_expiry_during_final_binding_validation_still_no_http(monkeypatch, registry, fixture,
                   configuration, token, provenance, authorization):
    wall = Clock()
    wall.now = provenance.prepared_at + 2
    first_now = wall.now
    monkeypatch.setattr(read.time, "time", wall)
    validator = read.validate_read_authorization
    def slow_validator(*a, **kw):
        result = validator(*a, **kw)
        if (registry.path / "attempt-test_assertion.jsonl").exists() and b'request_started' in registry.read("attempt-test_assertion.jsonl"):
            wall.now = authorization.expires_at
        return result
    monkeypatch.setattr(read, "validate_read_authorization", slow_validator)
    wire = Wire(canonical_json_bytes(payload(fixture)))
    result = run(monkeypatch, registry, fixture, configuration, token, provenance, authorization, wire)
    assert result.outcome is read.Outcome.AUTHORIZATION and not wire.chunks
    assert wire.constructs == wire.connects == 1 and wire.responses == 0
    with pytest.raises(control.Spent):
        registry.consume(authorization, fixture, read.runtime_hash(configuration), read.source_hash(), now=first_now)
