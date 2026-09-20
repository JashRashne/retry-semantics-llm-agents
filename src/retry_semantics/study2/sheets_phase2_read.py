"""DRAFT connected GET-only boundary; import/construction never opens a socket.

No public generic request, connection, connector injection, OAuth or CLI. The only
production entry is inspect with an explicit, bound, unspent LIVE_READ_GO. Blocking
stdlib DNS/TLS/status/body parsing is confined to a spawned child; the parent owns
one monotonic deadline and kills the child on exhaustion. Trusted Python is not a
security sandbox. Private fake seams are used only by offline qualification tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import http.client
import importlib
import ipaddress
import multiprocessing
import os
from pathlib import Path
import re
import ssl
import threading
import time
from urllib.parse import urlencode

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_live_go_phase1 as phase1
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2.sheets_http_framing import ResponseFramingError, read_json_body
from retry_semantics.study2.sheets_phase2_control import (
    LocalRegistry, QualificationFixture, Refused, _private_fd, authorization_hash, digest, label,
    require, strict_json, validate_fixture, validate_read_authorization,
)

FIELDS = ("spreadsheetId,sheets(properties(sheetId,title,sheetType,"
          "gridProperties(rowCount,columnCount)),merges,tables,"
          "data(startRow,startColumn,rowData(values(userEnteredValue))))")

# Explicit implementation inventory for the pinned CPython/macOS POSIX spawn
# path, its anonymous pipes, resource tracker, pickle and wait/kill/reap helpers.
# This is not generic package enumeration or a claim to cover every stdlib file.
SPAWN_PYTHON_MODULES = (
    "multiprocessing", "multiprocessing.context", "multiprocessing.process",
    "multiprocessing.connection", "multiprocessing.spawn",
    "multiprocessing.popen_spawn_posix", "multiprocessing.popen_fork",
    "multiprocessing.resource_tracker", "multiprocessing.reduction",
    "multiprocessing.resource_sharer", "multiprocessing.util", "selectors", "pickle",
    "subprocess", "threading",
)
SPAWN_NATIVE_MODULES = ("_multiprocessing", "_posixsubprocess", "select", "_pickle")


@dataclass(frozen=True, slots=True)
class ReadConfiguration:
    total_seconds: float
    max_response_bytes: int
    max_cell_characters: int
    registry_root: str
    schema: str = "sheets-phase2-read-configuration-v1"

    def __post_init__(self) -> None:
        frozen._number(self.total_seconds, positive=True)
        require(type(self.max_response_bytes) is int and 0 < self.max_response_bytes <= 2147483647
                and type(self.max_cell_characters) is int
                and 0 < self.max_cell_characters <= self.max_response_bytes
                and type(self.schema) is str and self.schema == "sheets-phase2-read-configuration-v1")
        require(type(self.registry_root) is str and not re.search(r"[\x00\r\n]", self.registry_root)
                and Path(self.registry_root).is_absolute()
                and ".." not in Path(self.registry_root).parts
                and str(Path(self.registry_root)) == self.registry_root)

    def projection(self) -> dict:
        return {"schema": self.schema, "total_seconds": self.total_seconds,
                "max_response_bytes": self.max_response_bytes,
                "max_cell_characters": self.max_cell_characters,
                "registry_root": self.registry_root,
                "deadline_engine": "spawned-process-monotonic-watchdog-v1",
                "response_framing": "bounded-content-length-or-chunked-utf8-json-v1"}


class DeadlineExpired(Refused):
    pass


class EvidenceFailure(Refused):
    pass


class AuthorizationAtSendRefused(Refused):
    pass


class ReadinessAtSendRefused(Refused):
    pass


class TLSObservationRefused(Refused):
    pass


class Deadline:
    def __init__(self, total_seconds: float, *, clock=time.monotonic,
                 absolute_end: float | None = None) -> None:
        frozen._number(total_seconds, positive=True)
        self._clock = clock
        start = clock()
        frozen._number(start)
        self.end = start + total_seconds if absolute_end is None else absolute_end
        frozen._number(self.end, positive=True)

    def remaining(self) -> float:
        now = self._clock()
        frozen._number(now)
        value = self.end - now
        if value <= 0:
            raise DeadlineExpired()
        return value


def source_hash() -> str:
    directory = Path(__file__).parent
    projection = {name: sha256_hex((directory / name).read_bytes())
        for name in ("sheets_phase2_control.py", "sheets_phase2_read.py",
                     "sheets_live_go_phase1.py", "sheets_http_framing.py")}
    projection["phase2_fixture_specification"] = sha256_hex((frozen.SHEETS_DOCS /
        "fixtures/qualification_fixture_phase2_template.json").read_bytes())
    return sha256_hex(canonical_json_bytes(projection))


def multiprocessing_projection() -> dict:
    def hashes(names):
        return {name: sha256_hex(Path(importlib.import_module(name).__file__).read_bytes())
                for name in names}
    return {"schema": "sheets-phase2-posix-spawn-implementation-v1",
            "path": "pinned-cpython-macos-posix-spawn",
            "python_sources": hashes(SPAWN_PYTHON_MODULES),
            "native_implementations": hashes(SPAWN_NATIVE_MODULES)}


def runtime_hash(configuration: ReadConfiguration) -> str:
    require(type(configuration) is ReadConfiguration)
    configuration.__post_init__()
    return sha256_hex(canonical_json_bytes({"schema": "sheets-phase2-runtime-v1",
        "frozen_runtime": frozen.check_runtime(), "frozen_pin_hash": phase1.pin_hash(),
        "phase2_source_hash": source_hash(), "configuration": configuration.projection(),
        "multiprocessing_implementation": multiprocessing_projection()}))


def read_path(fixture: QualificationFixture) -> str:
    validate_fixture(fixture)
    # Preserve the frozen verifier's exact order/encoding and field mask.
    return f"/v4/spreadsheets/{fixture.spreadsheet_id}?" + urlencode((
        ("ranges", fixture.verifier_range), ("includeGridData", "true"), ("fields", FIELDS)))


class Stage(Enum):
    CONSUMED = "authorization_consumed"
    CONSTRUCT_STARTED = "connector_construction_started"
    CONSTRUCTED = "connector_constructed"
    CONNECT_STARTED = "connect_started"
    CONNECTED = "connect_completed"
    TLS_OBSERVED = "tls_observation_persisted"
    REQUEST_STARTED = "request_started"
    SENT = "local_send_completed"
    STATUS = "status_observed"
    BODY = "body_read_completed"
    PARSED = "parse_completed"
    TERMINAL = "terminal"


class Outcome(Enum):
    ZERO = "zero_matches_currently_not_observed"
    ONE = "one_match"
    MULTIPLE = "multiple_matches"
    MALFORMED = "malformed_or_incomplete"
    UNCERTAIN = "verifier_uncertainty"
    HTTP_ERROR = "terminal_http_status"
    DEADLINE = "total_deadline_exhausted"
    CONSTRUCTION = "connector_construction_error"
    TRANSPORT = "transport_error"
    STORAGE = "evidence_storage_error"
    WORKER = "worker_incomplete"
    AUTHORIZATION = "authorization_refused_at_raw_send"
    SEND_READINESS = "token_readiness_refused_at_raw_send"
    TLS = "tls_observation_refused"


@dataclass(frozen=True, slots=True)
class TLSObservation:
    """Positive nonsecret projection, never a socket/certificate-object dump."""
    server_hostname: str
    protocol: str
    cipher_name: str
    cipher_protocol: str
    cipher_bits: int
    leaf_certificate_sha256: str
    alpn: str | None
    peer_address: str
    peer_port: int
    schema: str = "sheets-phase2-tls-observation-v1"

    def __post_init__(self) -> None:
        require(type(self.schema) is str and self.schema == "sheets-phase2-tls-observation-v1"
                and type(self.server_hostname) is str and self.server_hostname == frozen.HOST
                and type(self.protocol) is str and self.protocol in ("TLSv1.2", "TLSv1.3")
                and type(self.cipher_name) is str
                and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.cipher_name)
                and type(self.cipher_protocol) is str
                and re.fullmatch(r"[A-Za-z0-9./_-]{1,32}", self.cipher_protocol)
                and type(self.cipher_bits) is int and 0 < self.cipher_bits <= 512
                and (self.alpn is None or type(self.alpn) is str and self.alpn == "http/1.1")
                and type(self.peer_address) is str and len(self.peer_address) <= 45
                and re.fullmatch(r"[0-9A-Fa-f:.]+", self.peer_address)
                and type(self.peer_port) is int and self.peer_port == 443)
        digest(self.leaf_certificate_sha256)
        address = ipaddress.ip_address(self.peer_address)
        require(str(address) == self.peer_address)

    def projection(self) -> dict:
        self.__post_init__()
        return {"schema": self.schema, "server_hostname": self.server_hostname,
                "expected_server_hostname": frozen.HOST, "socket_type": "stdlib.ssl.SSLSocket",
                "hostname_check": True, "certificate_verification": "CERT_REQUIRED",
                "minimum_tls_policy": "TLSv1.2", "keylog": "disabled",
                "protocol": self.protocol, "cipher_name": self.cipher_name,
                "cipher_protocol": self.cipher_protocol, "cipher_bits": self.cipher_bits,
                "leaf_certificate_sha256": self.leaf_certificate_sha256,
                "alpn": self.alpn, "peer_address": self.peer_address, "peer_port": self.peer_port}

    @classmethod
    def from_projection(cls, value: dict) -> TLSObservation:
        require(type(value) is dict and set(value) == {"schema", "server_hostname",
            "expected_server_hostname", "socket_type", "hostname_check", "certificate_verification",
            "minimum_tls_policy", "keylog", "protocol", "cipher_name", "cipher_protocol",
            "cipher_bits", "leaf_certificate_sha256", "alpn", "peer_address", "peer_port"})
        require(value["hostname_check"] is True)
        observation = cls(value["server_hostname"], value["protocol"], value["cipher_name"],
            value["cipher_protocol"], value["cipher_bits"], value["leaf_certificate_sha256"],
            value["alpn"], value["peer_address"], value["peer_port"], value["schema"])
        require(value == observation.projection())
        return observation


def observe_tls(raw, context: ssl.SSLContext) -> TLSObservation:
    """Read only reviewed methods from the SAME successfully connected TLS socket.

    No credential input, second connection, trust probe or arbitrary repr. Exact
    SSLSocket type and context identity tie observation to the qualified connector.
    Test helpers replace that type with an explicitly fake verified TLS socket.
    """
    try:
        require(type(raw) is ssl.SSLSocket and raw.context is context
                and raw.server_side is False and type(raw.server_hostname) is str
                and raw.server_hostname == frozen.HOST)
        phase1.validate_context(context)
        version, cipher, alpn = raw.version(), raw.cipher(), raw.selected_alpn_protocol()
        require(type(cipher) is tuple and len(cipher) == 3)
        certificate = raw.getpeercert(binary_form=True)
        require(type(certificate) is bytes and 0 < len(certificate) <= 65536)
        peer = raw.getpeername()
        require(type(peer) is tuple and len(peer) in (2, 4)
                and type(peer[0]) is str and type(peer[1]) is int)
        if len(peer) == 4:
            require(all(type(value) is int and 0 <= value <= 4294967295 for value in peer[2:]))
        require(type(peer[0]) is str and len(peer[0]) <= 45
                and re.fullmatch(r"[0-9A-Fa-f:.]+", peer[0]))
        address = ipaddress.ip_address(peer[0])
        require(len(peer) == (4 if address.version == 6 else 2))
        observation = TLSObservation(raw.server_hostname, version, cipher[0], cipher[1], cipher[2],
                                     sha256_hex(certificate), alpn, str(address), peer[1])
        # Cipher protocol describes the suite, not necessarily the session's TLS
        # version. Require the exact suite metadata to exist in this SSL context.
        require(any(type(item) is dict and (item.get("name"), item.get("protocol"),
                    item.get("strength_bits")) == cipher for item in context.get_ciphers()))
        return observation
    except (OSError, ValueError, TypeError, AttributeError):
        raise TLSObservationRefused() from None


@dataclass(frozen=True, slots=True)
class ReadSummary:
    outcome: Outcome
    status: int | None = None
    byte_count: int = 0
    matching_rows: tuple[int, ...] = ()
    nonempty_rows: int = 0

    def __post_init__(self) -> None:
        require(type(self.outcome) is Outcome and
                (self.status is None or type(self.status) is int and 100 <= self.status <= 599)
                and type(self.byte_count) is int and self.byte_count >= 0
                and type(self.matching_rows) is tuple
                and all(type(row) is int and 0 <= row < 1000 for row in self.matching_rows)
                and tuple(sorted(set(self.matching_rows))) == self.matching_rows
                and type(self.nonempty_rows) is int and 0 <= self.nonempty_rows <= 1000)
        count = len(self.matching_rows)
        require(self.nonempty_rows >= count)
        if self.outcome in (Outcome.ZERO, Outcome.ONE, Outcome.MULTIPLE):
            require(self.status == 200 and (count == 0 if self.outcome is Outcome.ZERO
                    else count == 1 if self.outcome is Outcome.ONE else count > 1))
        else:
            require(count == self.nonempty_rows == 0)

    def projection(self) -> dict:
        return {"outcome": self.outcome.value, "status": self.status,
                "byte_count": self.byte_count, "matching_rows": list(self.matching_rows),
                "nonempty_rows": self.nonempty_rows}


class AttemptEvidence:
    """Typed positive allowlist, exclusive 0600 reservation, fsync every event.

    No token, response, headers, exceptions or credential object is an input.
    Interrupted append is incomplete evidence; it cannot renew a claim.
    """
    def __init__(self, registry: LocalRegistry, fixture: QualificationFixture,
                 authorization_id: str, runtime: str, source: str, *, reserve: bool) -> None:
        validate_fixture(fixture)
        label(authorization_id)
        digest(runtime)
        digest(source)
        self._registry = registry
        self._name = f"attempt-{authorization_id}.jsonl"
        self._fixture = fixture
        self._header = {"schema": "sheets-live-read-attempt-v1-draft", "engineering_only": True,
            "attempt_id": authorization_id, "authorization_id": authorization_id,
            "fixture_hash": fixture.manifest_hash, "runtime_hash": runtime,
            "source_hash": source, "capability": "LIVE_READ_GO"}
        if reserve:
            registry.create(self._name, self._header)
        records = self.records()
        require(records[0] == self._header)
        self._sequence = len(records) - 1
        self._stage = Stage(records[-1]["stage"]) if self._sequence else None

    def records(self) -> list[dict]:
        data = self._registry.read(self._name)
        require(data.endswith(b"\n"))
        records = [strict_json(line) for line in data.splitlines()]
        require(records and type(records[0]) is dict and records[0].get("engineering_only") is True
                and records[0] == self._header)
        previous = None
        for sequence, record in enumerate(records[1:], 1):
            require(type(record) is dict and set(record) in (
                    {"sequence", "stage", "summary"}, {"sequence", "stage", "summary", "tls"})
                    and type(record["sequence"]) is int and record["sequence"] == sequence)
            try:
                stage = Stage(record["stage"])
            except (ValueError, TypeError):
                raise Refused() from None
            require(self._allowed(previous, stage))
            summary = self._decode_summary(record["summary"])
            require(("tls" in record) is (stage is Stage.TLS_OBSERVED))
            if stage is Stage.TLS_OBSERVED:
                try:
                    TLSObservation.from_projection(record["tls"])
                except (ValueError, TypeError):
                    raise Refused() from None
            if stage not in (Stage.STATUS, Stage.BODY, Stage.PARSED, Stage.TERMINAL):
                require(summary == ReadSummary(Outcome.UNCERTAIN))
            previous = stage
        require(data == b"".join(canonical_json_bytes(record) + b"\n" for record in records))
        return records

    @staticmethod
    def _decode_summary(value: dict) -> ReadSummary:
        require(type(value) is dict and set(value) == {
            "outcome", "status", "byte_count", "matching_rows", "nonempty_rows"}
            and type(value["matching_rows"]) is list)
        try:
            return ReadSummary(Outcome(value["outcome"]), value["status"], value["byte_count"],
                               tuple(value["matching_rows"]), value["nonempty_rows"])
        except (ValueError, TypeError):
            raise Refused() from None

    @staticmethod
    def _allowed(previous: Stage | None, stage: Stage) -> bool:
        order = list(Stage)
        if stage is Stage.TERMINAL:
            return previous is not Stage.TERMINAL
        return stage is order[0] if previous is None else order.index(stage) == order.index(previous) + 1

    def event(self, stage: Stage, summary: ReadSummary | None = None, *,
              tls: TLSObservation | None = None) -> None:
        require(type(stage) is Stage and self._allowed(self._stage, stage))
        require((tls is not None) is (stage is Stage.TLS_OBSERVED))
        if tls is not None:
            require(type(tls) is TLSObservation)
            tls.__post_init__()
        summary = ReadSummary(Outcome.UNCERTAIN) if summary is None else summary
        require(type(summary) is ReadSummary)
        summary.__post_init__()
        require(all(row < self._fixture.rows for row in summary.matching_rows)
                and summary.nonempty_rows <= self._fixture.rows)
        if stage not in (Stage.STATUS, Stage.BODY, Stage.PARSED, Stage.TERMINAL):
            require(summary == ReadSummary(Outcome.UNCERTAIN))
        record = {"sequence": self._sequence + 1, "stage": stage.value,
                  "summary": summary.projection()}
        if tls is not None:
            record["tls"] = tls.projection()
        data = canonical_json_bytes(record) + b"\n"
        self._append(data)
        self._sequence += 1
        self._stage = stage

    def _append(self, data: bytes) -> None:
        try:
            fd = os.open(self._name, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW,
                         dir_fd=self._registry._dir)
            try:
                _private_fd(fd)
                # A short write poisons the artifact. No repair/truncate/retry.
                if os.write(fd, data) != len(data):
                    raise EvidenceFailure()
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            raise EvidenceFailure() from None


def parse_body(body: bytes, fixture: QualificationFixture,
               configuration: ReadConfiguration) -> ReadSummary:
    """Stricter shape fence before reuse of the frozen literal-grid verifier."""
    count = len(body)
    try:
        require(count <= configuration.max_response_bytes)
        payload = strict_json(body)
        require(type(payload) is dict and set(payload) == {"spreadsheetId", "sheets"})
        sheets = payload["sheets"]
        require(type(sheets) is list and len(sheets) == 1 and type(sheets[0]) is dict)
        sheet = sheets[0]
        require({"properties", "data"} <= set(sheet) <= {"properties", "data", "merges", "tables"})
        for key in ("merges", "tables"):
            require(key not in sheet or type(sheet[key]) is list and not sheet[key])
        props = sheet["properties"]
        require(type(props) is dict and set(props) == {"sheetId", "title", "sheetType", "gridProperties"})
        extent = props["gridProperties"]
        require(type(extent) is dict and set(extent) == {"rowCount", "columnCount"}
                and type(extent["rowCount"]) is int and type(extent["columnCount"]) is int)
        grid = sheet["data"]
        require(type(grid) is list and len(grid) == 1 and type(grid[0]) is dict
                and set(grid[0]) <= {"startRow", "startColumn", "rowData"})
        rows = grid[0].get("rowData", [])
        require(type(rows) is list and len(rows) <= fixture.rows)
        for row in rows:
            require(type(row) is dict and set(row) <= {"values"})
            cells = row.get("values", [])
            require(type(cells) is list and len(cells) <= 3)
            for cell in cells:
                require(type(cell) is dict and set(cell) <= {"userEnteredValue"})
                entered = cell.get("userEnteredValue", {})
                require(type(entered) is dict and (not entered or set(entered) == {"stringValue"}))
                if entered:
                    text = entered["stringValue"]
                    require(type(text) is str and len(text) <= configuration.max_cell_characters
                            and not re.search(r"[\ud800-\udfff]", text))
        result = frozen.parse_grid(payload, fixture, fixture.marker("qualification_read"))
        outcomes = {"zero_matches": Outcome.ZERO, "one_match": Outcome.ONE,
                    "multiple_matches": Outcome.MULTIPLE, "malformed_or_incomplete": Outcome.MALFORMED}
        return ReadSummary(outcomes[result.classification], 200, count, result.rows, result.nonempty_rows)
    except (frozen.QualificationError, KeyError, TypeError, ValueError, IndexError):
        return ReadSummary(Outcome.MALFORMED, 200, count)


class _ReadSocket:
    """Only one exact GET header block can cross sendall; no body or second send."""
    def __init__(self, raw, fixture, token, deadline, evidence, authorization, runtime, source):
        self._raw, self._path, self._deadline, self._evidence = raw, read_path(fixture), deadline, evidence
        self._auth = ("Bearer " + token.value).encode("ascii")
        self._fixture, self._token = fixture, token
        self._authorization, self._runtime, self._source = authorization, runtime, source
        self._assertion_hash = authorization_hash(authorization)
        # Only a durably recorded observation of this exact socket permits HTTP.
        require(evidence._stage is Stage.TLS_OBSERVED)
        self._spent = False

    def sendall(self, data: bytes) -> None:
        require(not self._spent and type(data) is bytes and data.endswith(b"\r\n\r\n"))
        lines = data[:-4].split(b"\r\n")
        require(lines[0] == f"GET {self._path} HTTP/1.1".encode("ascii"))
        observed = {}
        for line in lines[1:]:
            name, separator, value = line.partition(b": ")
            require(separator and re.fullmatch(rb"[A-Za-z][A-Za-z0-9-]*", name)
                    and not re.search(rb"[\r\n]", value))
            name = name.lower()
            require(name not in observed)
            observed[name] = value
        require(observed == {b"host": frozen.HOST.encode("ascii"), b"authorization": self._auth,
            b"accept": b"application/json", b"accept-encoding": b"identity", b"connection": b"close"})
        self._raw.settimeout(self._deadline.remaining())
        self._spent = True
        self._evidence.event(Stage.REQUEST_STARTED)
        self._raw.settimeout(self._deadline.remaining())  # Include evidence storage time.
        try:
            self._token.check_ready(now=time.time(), dispatch_budget_seconds=self._deadline.remaining())
        except DeadlineExpired:
            raise
        except frozen.QualificationError:
            raise ReadinessAtSendRefused() from None
        try:
            require(authorization_hash(self._authorization) == self._assertion_hash)
            validate_read_authorization(self._authorization, self._fixture, self._runtime,
                                        self._source, now=time.time())
            # Full binding validation has CPU cost. Refresh the temporal check
            # afterward as well; there is no intervening serialization/fsync/I/O.
            require(self._authorization.authorized_at <= time.time() < self._authorization.expires_at)
        except frozen.QualificationError:
            raise AuthorizationAtSendRefused() from None
        # No evidence write, serialization or other I/O remains between this
        # authorization check and the single raw handoff. OS scheduling can still
        # intervene; this is not an atomic wall-clock/send or realtime guarantee.
        self._raw.sendall(data)

    def makefile(self, *args, **kwargs):
        self._raw.settimeout(self._deadline.remaining())
        return self._raw.makefile(*args, **kwargs)

    def close(self):
        self._raw.close()

    def settimeout(self, value):
        self._raw.settimeout(min(value, self._deadline.remaining()))


def _construct(timeout: float):
    # Reuse the frozen Phase 1 stack/policy, without its legacy fixture/hash gate.
    # The new gate + durable claim are checked by _read_once BEFORE this call.
    phase1.environment_gate(os.environ)
    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    phase1.validate_context(context)
    connection = http.client.HTTPSConnection(frozen.HOST, 443, timeout=timeout, context=context)
    connection.auto_open = 0
    connection.debuglevel = 0
    require(connection.sock is None and connection._tunnel_host is None
            and connection.host == frozen.HOST and connection.port == 443)
    return connection


def _precheck(fixture, configuration, token, provenance, authorization, *, now, offline=False):
    validate_fixture(fixture)
    require(offline or fixture.identity_kind == "PROVISIONED")
    require(type(configuration) is ReadConfiguration and type(token) is frozen.PreparedToken
            and type(provenance) is phase1.CredentialProvenance)
    configuration.__post_init__()
    token.__post_init__()
    require(type(provenance.mechanism) is str
            and type(provenance.requested_scopes) is tuple
            and type(provenance.granted_scopes) is tuple
            and all(type(scope) is str for scope in provenance.requested_scopes + provenance.granted_scopes))
    provenance.__post_init__()
    require(provenance.public_config_sha256 == fixture.provenance.public_app_config_sha256
            and provenance.account_alias == fixture.provenance.account_alias
            and token.expires_at == provenance.expires_at
            and token.clock_uncertainty_seconds == provenance.clock_uncertainty_seconds
            and provenance.prepared_at <= now)
    token.check_ready(now=now, dispatch_budget_seconds=configuration.total_seconds)
    phase1.environment_gate(os.environ)
    runtime, source = runtime_hash(configuration), source_hash()
    validate_read_authorization(authorization, fixture, runtime, source, now=now)
    return runtime, source


def _response_body(response, socket, deadline, configuration):
    try:
        return read_json_body(response, configuration.max_response_bytes, min_body_bytes=1,
            before_read=lambda: socket.settimeout(deadline.remaining()),
            after_read=deadline.remaining, catch_transport_errors=False)
    except ResponseFramingError:
        raise Refused() from None


def _read_once(registry, fixture, configuration, token, provenance, authorization,
               deadline, *, offline=False) -> ReadSummary:
    """Private offline seam uses the SAME claim, envelope and parser as production."""
    runtime, source = _precheck(fixture, configuration, token, provenance, authorization,
                               now=time.time(), offline=offline)
    require(registry.path == Path(configuration.registry_root))
    registry.check_reserved(fixture)
    registry.check_claim(authorization, fixture, runtime, source)
    evidence = AttemptEvidence(registry, fixture, authorization.authorization_id, runtime, source,
                               reserve=False)
    require(evidence._stage is Stage.CONSUMED)
    connection = response = None
    summary = ReadSummary(Outcome.UNCERTAIN)
    try:
        deadline.remaining()
        evidence.event(Stage.CONSTRUCT_STARTED)
        connection = _construct(deadline.remaining())
        evidence.event(Stage.CONSTRUCTED)
        connection.timeout = deadline.remaining()
        validate_read_authorization(authorization, fixture, runtime, source, now=time.time())
        evidence.event(Stage.CONNECT_STARTED)
        deadline.remaining()
        connection.connect()  # DNS/TCP/TLS: parent watchdog bounds this whole call.
        evidence.event(Stage.CONNECTED)
        raw = connection.sock
        tls = observe_tls(raw, connection._context)
        deadline.remaining()
        evidence.event(Stage.TLS_OBSERVED, tls=tls)
        deadline.remaining()
        validate_read_authorization(authorization, fixture, runtime, source, now=time.time())
        token.check_ready(now=time.time(), dispatch_budget_seconds=deadline.remaining())
        require(connection.sock is raw)
        connection.sock = _ReadSocket(raw, fixture, token, deadline, evidence, authorization, runtime, source)
        connection.putrequest("GET", read_path(fixture), skip_host=True, skip_accept_encoding=True)
        for name, value in (("Host", frozen.HOST), ("Authorization", "Bearer " + token.value),
                            ("Accept", "application/json"), ("Accept-Encoding", "identity"),
                            ("Connection", "close")):
            connection.putheader(name, value)
        connection.endheaders()  # No body argument, no Content-Length, no chunking.
        evidence.event(Stage.SENT)
        connection.sock.settimeout(deadline.remaining())
        socket = connection.sock  # HTTPConnection may detach it on Connection: close.
        response = connection.getresponse()
        require(type(response.status) is int and 100 <= response.status <= 599)
        summary = ReadSummary(Outcome.UNCERTAIN, response.status)
        evidence.event(Stage.STATUS, summary)
        if response.status != 200:
            return ReadSummary(Outcome.HTTP_ERROR, response.status)
        deadline.remaining()
        try:
            body = _response_body(response, socket, deadline, configuration)
        except DeadlineExpired:
            raise
        except (Refused, http.client.IncompleteRead):
            return ReadSummary(Outcome.MALFORMED, response.status)
        summary = ReadSummary(Outcome.UNCERTAIN, 200, len(body))
        evidence.event(Stage.BODY, summary)
        deadline.remaining()
        summary = parse_body(body, fixture, configuration)
        deadline.remaining()
        evidence.event(Stage.PARSED, summary)
        return summary
    except DeadlineExpired:
        return ReadSummary(Outcome.DEADLINE, summary.status, summary.byte_count)
    except EvidenceFailure:
        return ReadSummary(Outcome.STORAGE, summary.status, summary.byte_count)
    except AuthorizationAtSendRefused:
        return ReadSummary(Outcome.AUTHORIZATION, summary.status, summary.byte_count)
    except ReadinessAtSendRefused:
        return ReadSummary(Outcome.SEND_READINESS, summary.status, summary.byte_count)
    except TLSObservationRefused:
        return ReadSummary(Outcome.TLS, summary.status, summary.byte_count)
    except (OSError, http.client.HTTPException, frozen.QualificationError):
        outcome = Outcome.CONSTRUCTION if connection is None else Outcome.TRANSPORT
        return ReadSummary(outcome, summary.status, summary.byte_count)
    finally:
        if response is not None:
            response.close()
        if connection is not None:
            connection.close()


def _lifeline(activation, end, stopped, *, clock=time.monotonic, abort=os._exit):
    """Independent worker thread: parent death/EOF or budget exhaustion is fatal.

    Blocking stdlib resolver/socket operations release the GIL. The parent process
    additionally preempts parsing/other child work while alive. This is an OS
    watchdog, not a hard realtime scheduling or storage-latency guarantee.
    """
    remaining = end - clock()
    if remaining > 0:
        try:
            activation.poll(remaining)
        except (OSError, EOFError):
            pass  # Closed lifeline is cancellation, never renewed permission.
    if not stopped.is_set():
        abort(24)  # No exception rendering, cleanup callback or later network I/O.


def _worker(send, activation, registry_path, fixture, configuration, token, provenance, authorization, end):
    # Only allowlisted primitive summaries leave this process. No exception text.
    stopped = threading.Event()
    try:
        require(activation.recv_bytes(4) == b"READ")
        Deadline(configuration.total_seconds, absolute_end=end).remaining()
        # Parent keeps the writer open through child exit. EOF therefore also
        # cancels an orphan after abrupt parent death, with no authorization reuse.
        threading.Thread(target=_lifeline, args=(activation, end, stopped), daemon=True).start()
        with LocalRegistry(registry_path) as registry:
            result = _read_once(registry, fixture, configuration, token, provenance, authorization,
                Deadline(configuration.total_seconds, absolute_end=end))
        send.send_bytes(canonical_json_bytes(result.projection()))
    except (OSError, EOFError, ValueError, TypeError, http.client.HTTPException):
        send.send_bytes(canonical_json_bytes(ReadSummary(Outcome.WORKER).projection()))
    finally:
        stopped.set()
        activation.close()
        send.close()


def _supervise(fixture, configuration, token, provenance, authorization, registry_path,
               deadline) -> ReadSummary:
    require(Path(registry_path).absolute() == Path(configuration.registry_root))
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    activation, activate = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(send, activation, registry_path, fixture, configuration,
        token, provenance, authorization, deadline.end), daemon=True)
    started = False
    try:
        deadline.remaining()
        process.start()
        started = True
        send.close()
        activation.close()
        deadline.remaining()
        activate.send_bytes(b"READ")
        if not receive.poll(deadline.remaining()):
            raise DeadlineExpired()
        result = AttemptEvidence._decode_summary(strict_json(receive.recv_bytes(65536)))
        process.join(deadline.remaining())
        deadline.remaining()
        require(not process.is_alive() and process.exitcode == 0)
        return result
    except DeadlineExpired:
        return ReadSummary(Outcome.DEADLINE)
    except (OSError, EOFError, ValueError, TypeError):
        try:
            deadline.remaining()
        except DeadlineExpired:
            return ReadSummary(Outcome.DEADLINE)
        return ReadSummary(Outcome.WORKER)
    finally:
        # A blocked resolver or dribbling HTTPResponse cannot outlive the attempt.
        # kill, not a cooperative cancellation callback; never start another child.
        if started:
            if process.is_alive():
                process.kill()
            process.join()
            process.close()
        receive.close()
        send.close()
        activation.close()
        activate.close()


class ReadAdapter:
    """GET-only future entry. Missing auth and TEST_ONLY identities fail closed.

    No real usable authorization is created by this module. The registry path is
    an operator-selected durable control-plane root, not a temporary per-attempt
    directory. One spawned process/fresh HTTPSConnection per consumed assertion.
    """
    __slots__ = ("_fixture", "_configuration", "_registry_path")

    def __init__(self, fixture: QualificationFixture, configuration: ReadConfiguration,
                 registry_path: Path) -> None:
        validate_fixture(fixture)
        require(type(configuration) is ReadConfiguration)
        configuration.__post_init__()
        self._fixture, self._configuration = fixture, configuration
        self._registry_path = Path(registry_path)
        require(self._registry_path.absolute() == Path(configuration.registry_root))

    def inspect(self, token: frozen.PreparedToken, provenance: phase1.CredentialProvenance,
                *, authorization: phase1.LiveAuthorization | None = None) -> ReadSummary:
        try:
            return self._inspect(token, provenance, authorization)
        except (OSError, EOFError, http.client.HTTPException):
            raise Refused() from None

    def _inspect(self, token, provenance, authorization):
        deadline = Deadline(self._configuration.total_seconds)
        runtime, source = _precheck(self._fixture, self._configuration, token, provenance,
                                   authorization, now=time.time())
        deadline.remaining()
        with LocalRegistry(self._registry_path) as registry:
            registry.check_reserved(self._fixture)
            evidence = AttemptEvidence(registry, self._fixture, authorization.authorization_id,
                                       runtime, source, reserve=True)
            deadline.remaining()
            registry.consume(authorization, self._fixture, runtime, source, now=time.time())
            evidence.event(Stage.CONSUMED)
            # Only after file fsync AND directory fsync succeeded can any worker
            # or connector be constructed. Failures never remove the claim.
            result = _supervise(self._fixture, self._configuration, token, provenance,
                                authorization, self._registry_path, deadline)
            # Worker has exited/been killed before parent reopens its journal.
            evidence = AttemptEvidence(registry, self._fixture, authorization.authorization_id,
                                       runtime, source, reserve=False)
            records = evidence.records()
            status = next((record["summary"]["status"] for record in reversed(records[1:])
                           if record["summary"]["status"] is not None), None)
            if result.status is None and status is not None:
                result = ReadSummary(result.outcome, status, result.byte_count,
                                     result.matching_rows, result.nonempty_rows)
            evidence.event(Stage.TERMINAL, result)
            return result
