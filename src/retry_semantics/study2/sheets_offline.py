"""Frozen Sheets offline qualification primitives. Fake sockets ONLY; no live adapter.

Uses real stdlib HTTP serialization/parsing, but never constructs a network
connection. No Google auth, policy executor, provider state model or paper data.
"""

from dataclasses import dataclass
from enum import Enum
import http.client
import io
import re
import time

from retry_semantics.serialization import canonical_json_bytes, sha256_hex


class Traffic(str, Enum):
    AUTH = "authentication"
    DISCOVERY = "discovery_metadata"
    READ = "sheets_read"
    MUTATION = "sheets_mutation"


@dataclass(frozen=True, slots=True)
class FrozenMutation:
    """Exact application identity, excluding runtime bearer and HTTP framing."""
    method: str
    uri: str
    headers: tuple[tuple[str, str], ...]
    body: bytes

    @property
    def body_hash(self) -> str:
        return sha256_hex(self.body)

    @property
    def identity_hash(self) -> str:
        return sha256_hex(canonical_json_bytes({
            "origin": "https://sheets.googleapis.com",
            "method": self.method, "uri": self.uri,
            "headers": [list(pair) for pair in self.headers],
            "body_hex": self.body.hex(),
        }))


def prepare_append_cells(*, spreadsheet_id: str, sheet_id: int,
                         marker: str) -> FrozenMutation:
    """Caller-supplied fixture identity; literals only. No target discovery."""
    if (type(spreadsheet_id) is not str
            or not re.fullmatch(r"[A-Za-z0-9_-]+", spreadsheet_id)
            or type(sheet_id) is not int or sheet_id < 0
            or type(marker) is not str
            or not re.fullmatch(r"ENGINEERING-ONLY-[A-Za-z0-9_-]+", marker)):
        raise ValueError("invalid nonsecret fixture identity")
    row = (marker, "engineering-v1", "literal-payload")
    body = canonical_json_bytes({
        "includeSpreadsheetInResponse": False,
        "requests": [{"appendCells": {
            "sheetId": sheet_id,
            "fields": "userEnteredValue",
            "rows": [{"values": [
                {"userEnteredValue": {"stringValue": value}} for value in row
            ]}],
        }}],
    })
    return FrozenMutation(
        "POST", f"/v4/spreadsheets/{spreadsheet_id}:batchUpdate",
        (("content-type", "application/json; charset=utf-8"),
         ("accept", "application/json")), body,
    )


@dataclass(frozen=True, slots=True)
class DispatchRecord:
    sequence: int
    monotonic_ns: int
    method: str
    uri: str
    body_hash: str
    traffic: Traffic
    after_policy_entry: bool
    request_identity_hash: str | None


@dataclass(frozen=True, slots=True)
class LocalResult:
    classification: str
    status: int | None
    send_completed: bool


class LifecycleStage(str, Enum):
    DISPATCH_INITIATED = "dispatch_initiated"
    LOCAL_SEND_COMPLETED = "local_send_completed"
    STATUS_OBSERVED = "status_observed"
    POLICY_ENTRY = "policy_entry"


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    """Local facts only; no assertion of remote receipt or commit."""
    sequence: int
    monotonic_ns: int
    dispatch_sequence: int
    stage: LifecycleStage
    status: int | None = None


class DispatchLedger:
    """One isolated qualification trial. Entry validates evidence, runs no policy."""
    def __init__(self):
        self._records = []
        self._lifecycle = []
        self.policy_entry_ns = None

    @property
    def records(self) -> tuple[DispatchRecord, ...]:
        return tuple(self._records)

    @property
    def lifecycle(self) -> tuple[LifecycleEvent, ...]:
        return tuple(self._lifecycle)

    def _event(self, stage: LifecycleStage, dispatch_sequence: int,
               status: int | None = None) -> LifecycleEvent:
        event = LifecycleEvent(len(self._lifecycle) + 1, time.monotonic_ns(),
                               dispatch_sequence, stage, status)
        self._lifecycle.append(event)
        return event

    def record(self, method: str, uri: str, body: bytes, traffic: Traffic,
               identity_hash: str | None = None) -> DispatchRecord:
        record = DispatchRecord(
            len(self._records) + 1, time.monotonic_ns(), method, uri,
            sha256_hex(body), traffic, self.policy_entry_ns is not None, identity_hash,
        )
        self._records.append(record)
        if traffic is Traffic.MUTATION:
            self._event(LifecycleStage.DISPATCH_INITIATED, record.sequence)
        return record

    def observe_send_completion(self, dispatch_sequence: int) -> None:
        self._event(LifecycleStage.LOCAL_SEND_COMPLETED, dispatch_sequence)

    def observe_status(self, dispatch_sequence: int, status: int) -> None:
        self._event(LifecycleStage.STATUS_OBSERVED, dispatch_sequence, status)

    def qualify_retry_entry(self, result: LocalResult,
                            frozen: FrozenMutation) -> None:
        mutations = [r for r in self.records if r.traffic is Traffic.MUTATION]
        expected_stages = (LifecycleStage.DISPATCH_INITIATED,
                           LifecycleStage.LOCAL_SEND_COMPLETED)
        if (self.policy_entry_ns is not None or len(mutations) != 1
                or mutations[0].after_policy_entry
                or mutations[0].request_identity_hash != frozen.identity_hash
                or (mutations[0].method, mutations[0].uri, mutations[0].body_hash)
                != (frozen.method, frozen.uri, frozen.body_hash)
                or result.classification != "ambiguous"
                or result.status is not None or not result.send_completed
                or tuple(event.stage for event in self.lifecycle) != expected_stages
                or any(event.dispatch_sequence != mutations[0].sequence
                       or event.status is not None for event in self.lifecycle)):
            raise ValueError("invalid target ambiguity qualification")
        self.policy_entry_ns = self._event(
            LifecycleStage.POLICY_ENTRY, mutations[0].sequence).monotonic_ns


class Fault(str, Enum):
    NONE = "none"
    BEFORE_SEND = "before_send"
    AFTER_SEND = "after_send_before_status"
    WAIT_LOSS = "response_wait_loss"
    BODY_LOSS = "visible_status_body_loss"
    PARTIAL_SEND = "synthetic_incomplete_body_send"
    CONNECT = "connect_failure"
    SOCKET_GONE = "socket_gone_before_send"


class _UnreadStatusStream(io.BytesIO):
    """Initialize HTTPResponse safely, then lose its first status-line read."""
    def __init__(self):
        super().__init__()
        self.readline_calls = 0

    def readline(self, size=-1):
        self.readline_calls += 1
        raise TimeoutError("synthetic status-stream loss")


def _validate_header_envelope(data: bytes, request: FrozenMutation) -> None:
    """Strict controlled shape, not an RFC parser or independent attestation.

    Auth is checked structurally and never copied into the comparison map/hash.
    Errors contain fixed reasons only, never serialized fields or header values.
    """
    fixed = {
        b"host": b"sheets.googleapis.com",
        b"content-length": str(len(request.body)).encode("ascii"),
        b"accept-encoding": b"identity",
        b"connection": b"close",
    }
    application_names = {b"content-type", b"accept"}
    allowed = set(fixed) | application_names | {b"authorization"}
    if not data.endswith(b"\r\n\r\n"):
        raise ValueError("serialized controlled header envelope differs: invalid termination")
    observed = {}
    application = []
    for line in data[:-4].split(b"\r\n")[1:]:
        name, separator, value = line.partition(b": ")
        if not separator or not re.fullmatch(rb"[A-Za-z][A-Za-z0-9-]*", name):
            raise ValueError("serialized controlled header envelope differs: invalid header syntax")
        name = name.lower()
        if name not in allowed:
            raise ValueError("serialized controlled header envelope differs: unexpected header")
        if name in observed:
            raise ValueError("serialized controlled header envelope differs: duplicate header")
        if name == b"authorization":
            if not re.fullmatch(rb"Bearer [A-Za-z0-9._~+/-]+=*", value):
                raise ValueError("serialized controlled header envelope differs: authorization form")
            observed[name] = None  # Presence only; no bearer value in stored evidence.
        else:
            observed[name] = value
            if name in application_names:
                application.append((name, value))
    if set(observed) != allowed:
        raise ValueError("serialized controlled header envelope differs: missing required header")
    # Canonical decimal equality also rejects noninteger/negative/ambiguous lengths.
    if any(observed[name] != value for name, value in fixed.items()):
        raise ValueError("serialized controlled header envelope differs: routing/framing mismatch")
    expected_application = tuple((name.encode("ascii"), value.encode("ascii"))
                                 for name, value in request.headers)
    if tuple(application) != expected_application:
        raise ValueError("serialized application headers differ")


class OfflineWire:
    """Fake socket boundary recording actual serialized request-line handoffs.

    Body hash comes from the stdlib _send_output argument, and each emitted body
    is checked against it. Header and body sendall calls are ONE HTTP dispatch.
    Private synthetic buffers may contain placeholder auth; none enter records.
    """
    def __init__(self, ledger: DispatchLedger, *, status: int = 200,
                 fault: Fault = Fault.NONE):
        if type(fault) is not Fault:
            raise ValueError("typed offline fault required")
        self.ledger, self.status, self.fault = ledger, status, fault
        self.connections = []
        self.response_calls = 0
        self.response_streams = []
        self.completed_bodies = []

    def connection(self, request: FrozenMutation):
        wire = self

        class FakeSocket:
            def __init__(self):
                self.header_pending = True
                self.expected_body = request.body
                self.dispatch_sequence = None

            def sendall(self, data):
                if self.header_pending:
                    line = data.split(b"\r\n", 1)[0]
                    expected_line = (f"{request.method} {request.uri} HTTP/1.1").encode("ascii")
                    if line != expected_line:
                        raise ValueError("serialized target differs from frozen target")
                    _validate_header_envelope(data, request)
                    method, uri, _ = line.decode("ascii").split(" ")
                    # This is the first actual socket handoff, not endheaders count.
                    record = wire.ledger.record(method, uri, self.expected_body, Traffic.MUTATION,
                                                request.identity_hash)
                    self.dispatch_sequence = record.sequence
                    self.header_pending = False
                else:
                    if data != self.expected_body:
                        raise ValueError("serialized body differs from frozen body")
                    if wire.fault is Fault.PARTIAL_SEND:
                        # Synthetic local failure; no remote byte-delivery estimate.
                        raise ConnectionError("synthetic incomplete body send")
                    wire.completed_bodies.append(data)

            def makefile(self, mode):
                wire.response_calls += 1
                if wire.fault is Fault.WAIT_LOSS:
                    stream = _UnreadStatusStream()
                    wire.response_streams.append(stream)
                    return stream
                body = b"{}"
                available = b"" if wire.fault is Fault.BODY_LOSS else body
                headers = (f"HTTP/1.1 {wire.status} Synthetic\r\n"
                           "Content-Type: application/json\r\n"
                           "Content-Length: 2\r\nConnection: close\r\n"
                           "Location: https://redirect.invalid/\r\n"
                           "Retry-After: 0\r\n\r\n").encode("ascii")
                stream = io.BytesIO(headers + available)
                wire.response_streams.append(stream)
                return stream

            def close(self):
                pass

        class FakeConnection(http.client.HTTPConnection):
            def __init__(self):
                super().__init__("offline.invalid", timeout=1)
                self.connect_count = 0
                self.closed = False
                self.fake_socket = FakeSocket()

            def connect(self):
                self.connect_count += 1
                if wire.fault is Fault.CONNECT:
                    raise ConnectionError("synthetic connect failure")
                self.sock = self.fake_socket

            def _send_output(self, message_body=None, encode_chunked=False):
                if message_body != request.body or encode_chunked:
                    raise ValueError("frozen unchunked body required")
                self.fake_socket.header_pending = True
                self.fake_socket.expected_body = message_body
                super()._send_output(message_body, encode_chunked=encode_chunked)

            def close(self):
                self.closed = True
                super().close()

        connection = FakeConnection()
        self.connections.append(connection)
        return connection


def qualify_single_attempt(request: FrozenMutation, wire: OfflineWire) -> LocalResult:
    """Offline proposed transport flow; fixed synthetic bearer, no refresh layer.

    Factory is deliberately unavailable as an injection point for live HTTPS.
    Does not retry, follow redirects, parse mutation success payload or run arms.
    """
    if type(wire) is not OfflineWire:
        raise ValueError("offline wire required")
    connection = wire.connection(request)
    initiated_before = len(wire.ledger.records)
    status = None
    completed = False
    classification = None
    try:
        connection.auto_open = 0
        connection.set_debuglevel(0)
        connection.connect()
        connection.putrequest(request.method, request.uri,
                              skip_host=True, skip_accept_encoding=True)
        for name, value in request.headers:
            connection.putheader(name, value)
        connection.putheader("Host", "sheets.googleapis.com")
        connection.putheader("Authorization", "Bearer offline-placeholder")
        connection.putheader("Content-Length", str(len(request.body)))
        connection.putheader("Accept-Encoding", "identity")
        connection.putheader("Connection", "close")
        if wire.fault is Fault.BEFORE_SEND:
            return LocalResult("known_non_dispatch", None, False)
        if wire.fault is Fault.SOCKET_GONE:
            connection.sock = None
        connection.endheaders(request.body, encode_chunked=False)
        completed = True
        wire.ledger.observe_send_completion(connection.fake_socket.dispatch_sequence)
        if wire.fault is Fault.AFTER_SEND:
            return LocalResult("ambiguous", None, True)
        response = connection.getresponse()
        status = response.status
        wire.ledger.observe_status(connection.fake_socket.dispatch_sequence, status)
        classification = ("known_success" if 200 <= status < 300 else
                          "auth_issue" if status == 401 else
                          "redirect_refused" if 300 <= status < 400 else "known_http_error")
        response.read()
    except (OSError, http.client.HTTPException):
        if status is not None:
            if 200 <= status < 300:
                classification = "known_success_incomplete_response"
        else:
            classification = ("known_non_dispatch" if len(wire.ledger.records) == initiated_before
                              else "ambiguous" if completed else "incomplete_send_unknown")
    finally:
        connection.close()
    return LocalResult(classification, status, completed)
