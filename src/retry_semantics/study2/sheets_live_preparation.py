"""Frozen offline Sheets live-preparation boundaries. No real socket connector or
live runner supplied.

Trusted Python code is not a security sandbox. Injected socket connectors are a
qualification seam, not an authorization mechanism. Mutation/read traffic uses
stdlib serialization and a guarded sendall boundary, never an authenticated SDK.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import http.client
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import ssl
import sys
import threading
import time

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_offline import FrozenMutation

HOST = "sheets.googleapis.com"
ROOT = Path(__file__).resolve().parents[3]
SHEETS_DOCS = ROOT / "research/study2/sheets"


class QualificationError(ValueError):
    """Fixed, nonsecret error text only. Never wrap arbitrary exception content."""
    def __init__(self):
        super().__init__("Sheets engineering qualification refused")


class TokenSafetyError(QualificationError):
    """No message/args that could echo a token colliding with a fixed label."""
    def __init__(self):
        ValueError.__init__(self)


def _require(condition):
    if not condition:
        raise QualificationError()


def _number(value, *, positive=False):
    _require(type(value) in (int, float) and math.isfinite(value)
             and (value > 0 if positive else value >= 0))


def _safe_label(value):
    _require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)
             and not re.search(r"ya29|1//|Bearer|token|secret|credential", value, re.I))
    return value


@dataclass(frozen=True, slots=True, repr=False)
class PreparedToken:
    """Immutable exported token only; no credential object/refresh/request callback."""
    value: str = field(repr=False)
    expires_at: float
    clock_uncertainty_seconds: float

    def __post_init__(self):
        _require(type(self.value) is str
                 and re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", self.value))
        _number(self.expires_at, positive=True)
        _number(self.clock_uncertainty_seconds)

    def __repr__(self):
        return "PreparedToken(<excluded>)"

    def check_ready(self, *, now: float, dispatch_budget_seconds: float):
        _number(now)
        _number(dispatch_budget_seconds, positive=True)
        # Budget and clock uncertainty must later be justified/frozen, not a
        # magic TTL. Readiness is a local expiry check, not server acceptance.
        _require(self.expires_at - now > dispatch_budget_seconds
                 + self.clock_uncertainty_seconds)


def prepare_token(value, *, expires_at, clock_uncertainty_seconds):
    """Minimal manual export approach v1. Does not acquire/refresh/validate remotely."""
    return PreparedToken(value, expires_at, clock_uncertainty_seconds)


def runtime_fingerprint():
    """No environment dump, executable/credential paths or arbitrary packages."""
    import socket
    import _ssl
    return {
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_build": list(platform.python_build()),
        "python_compiler": platform.python_compiler(),
        "interpreter_sha256": sha256_hex(Path(sys.executable).read_bytes()),
        "system": platform.system(), "machine": platform.machine(),
        "platform_release": platform.release(),
        "openssl": ssl.OPENSSL_VERSION,
        "http_client_sha256": sha256_hex(Path(http.client.__file__).read_bytes()),
        "ssl_sha256": sha256_hex(Path(ssl.__file__).read_bytes()),
        "socket_sha256": sha256_hex(Path(socket.__file__).read_bytes()),
        "ssl_extension_sha256": sha256_hex(Path(_ssl.__file__).read_bytes()),
        "lock_sha256": sha256_hex((ROOT / "uv.lock").read_bytes()),
        "transport_source_sha256": sha256_hex(Path(__file__).read_bytes()),
        "serialization_source_sha256": sha256_hex((ROOT / "src/retry_semantics/serialization.py").read_bytes()),
        "offline_source_sha256": sha256_hex((Path(__file__).parent / "sheets_offline.py").read_bytes()),
        "fixture_template_sha256": sha256_hex((SHEETS_DOCS / "fixtures/qualification_fixture_draft.json").read_bytes()),
        "dependencies": {name: importlib.metadata.version(name) for name in
                         ("groq", "httpx", "jsonschema", "pytest")},
        "mutation_http_layer": "stdlib-http.client",
        "auth_preparation": "manual-prepared-token-v1",
        "tls_policy": "default-context-hostname-and-certificate-verification",
    }


def check_runtime():
    actual = runtime_fingerprint()
    expected = json.loads((SHEETS_DOCS / "SHEETS_RUNTIME_PIN_DRAFT.json").read_text())
    _require(actual == expected)
    return actual


@dataclass(frozen=True, slots=True)
class Fixture:
    spreadsheet_id: str
    sheet_id: int
    title: str
    rows: int
    columns: int
    namespace: str

    def __post_init__(self):
        _safe_label(self.spreadsheet_id)
        _safe_label(self.namespace)
        _require(type(self.sheet_id) is int and self.sheet_id >= 0
                 and self.title == "RetrySemanticsEngineering"
                 and type(self.rows) is int and 3 <= self.rows <= 1000
                 and type(self.columns) is int and self.columns == 3)

    @property
    def manifest(self):
        template = json.loads((SHEETS_DOCS / "fixtures/qualification_fixture_draft.json").read_text())
        _require(set(template) == {"schema", "engineering_only", "live_go", "spreadsheet_id",
            "sheet_id", "expected_title", "sheet_type", "candidate", "row_count", "column_count",
            "expected_baseline", "baseline_region", "formulas", "tables", "merged_cells",
            "automation", "concurrent_writers", "structural_edits_sorts", "unrelated_data",
            "marker_namespace", "marker_template", "namespace_reservation", "capacity",
            "expected_clean_placement", "verification_scope", "cleanup_policy"})
        template.update(spreadsheet_id=self.spreadsheet_id, sheet_id=self.sheet_id,
                        row_count=self.rows, column_count=self.columns,
                        marker_namespace=self.namespace)
        template["baseline_region"] = f"A1:C{self.rows} (whole manifest grid)"
        return template

    @property
    def manifest_hash(self):
        return sha256_hex(canonical_json_bytes(self.manifest))

    def marker(self, case_id):
        return f"ENGINEERING-ONLY-{self.namespace}-{_safe_label(case_id)}"

    @property
    def read_path(self):
        from urllib.parse import urlencode
        fields = ("spreadsheetId,sheets(properties(sheetId,title,sheetType,"
                  "gridProperties(rowCount,columnCount)),merges,tables,"
                  "data(startRow,startColumn,rowData(values(userEnteredValue))))")
        return f"/v4/spreadsheets/{self.spreadsheet_id}?" + urlencode({
            "ranges": f"'{self.title}'!A1:C{self.rows}",
            "includeGridData": "true", "fields": fields})


def validate_frozen(request, fixture, case_id):
    """Parse candidate structure without regenerating/transmitting JSON.

    Replay also compares against the journal's original stored bytes/identity.
    """
    _require(type(request) is FrozenMutation and type(request.body) is bytes)
    _require(request.method == "POST" and request.uri ==
             f"/v4/spreadsheets/{fixture.spreadsheet_id}:batchUpdate"
             and request.headers == (("content-type", "application/json; charset=utf-8"),
                                     ("accept", "application/json")))
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                _require(key not in result)
                result[key] = value
            return result
        decoded = json.loads(request.body, object_pairs_hook=unique)
        _require(decoded == {"includeSpreadsheetInResponse": False,
            "requests": [{"appendCells": {"sheetId": fixture.sheet_id,
                "fields": "userEnteredValue", "rows": [{"values": [
                    {"userEnteredValue": {"stringValue": s}} for s in
                    (fixture.marker(case_id), "engineering-v1", "literal-payload")]}]}}]})
        _require(type(decoded["includeSpreadsheetInResponse"]) is bool
                 and type(decoded["requests"][0]["appendCells"]["sheetId"]) is int)
    except Exception:
        raise QualificationError() from None


STAGES = frozenset({"connect_started", "connect_completed", "dispatch_initiated",
                    "local_send_completed", "status_observed", "failure",
                    "closed", "policy_entry", "verifier_summary",
                    "verifier_initiated", "verifier_status", "attempt_result",
                    "fault_injected"})
CLASSIFICATIONS = frozenset({"known_non_dispatch", "incomplete_send_unknown",
    "ambiguous", "known_success", "known_success_incomplete_response", "auth_issue",
    "redirect_refused", "known_http_error", "invalid_evidence"})
FAULTS = frozenset({"none", "after_send_before_status"})
VERIFY_CLASSES = frozenset({"zero_matches", "one_match", "multiple_matches",
                            "malformed_or_incomplete", "verifier_uncertainty"})


class EvidenceJournal:
    """Exclusive reserved append-only JSONL, fsync each typed event before handoff.

    Single owner, no arbitrary serialization fallback. Failure poisons the journal.
    Process/power-loss durability and a lost event after a send remain unqualified.
    """
    def __init__(self, path, *, trial_id, fixture, case_id, request, token, fault="none"):
        self._lock = threading.RLock()
        self._broken = False
        self._events = []
        self._attempts = 0
        self._active = False
        self._reading = False
        self._reads = 0
        self._entering_policy = False
        self._policy = False
        self._result = None
        _require(type(fixture) is Fixture and type(token) is PreparedToken)
        self.fixture, self.case_id, self.request = fixture, _safe_label(case_id), request
        validate_frozen(request, fixture, case_id)
        _require(fault in FAULTS)
        self._fault = fault
        # Canonical path/query/body derive only from the validated fixture/candidate.
        header = {
            "schema": "sheets-engineering-v1-draft", "engineering_only": True,
            "trial_id": _safe_label(trial_id), "runtime": check_runtime(),
            "fixture_manifest": fixture.manifest,
            "fixture_manifest_sha256": fixture.manifest_hash,
            "fault": fault, "origin": "https://" + HOST,
            "method": request.method, "path": request.uri,
            "application_headers": [list(p) for p in request.headers],
            "body_hex": request.body.hex(), "body_sha256": request.body_hash,
            "frozen_identity_sha256": request.identity_hash,
            "marker": fixture.marker(case_id),
            "prepared_utc": datetime.now(timezone.utc).isoformat(),
        }
        self._header = header
        # Supplemental collision defense runs before reservation/every action.
        # No credential-derived object, value or hash is retained on the journal.
        self.assert_token_safe(token)
        self._file = open(path, "xb", buffering=0)
        try:
            os.chmod(path, 0o600)
            self._write(header)
        except BaseException:
            self._file.close()
            raise QualificationError() from None

    def _write(self, safe):
        _require(not self._broken)
        try:
            data = canonical_json_bytes(safe) + b"\n"
            _require(self._file.write(data) == len(data))
            os.fsync(self._file.fileno())
        except BaseException:
            self._broken = True
            raise QualificationError() from None

    @property
    def events(self):
        return tuple(dict(e) for e in self._events)

    @property
    def fault(self):
        return self._fault

    def assert_token_safe(self, token):
        """Supplemental pre-action collision defense for the known evidence domain.

        Walk only internally constructed JSON primitives, not credentials/config.
        Include prior evidence and all prospective fixed event labels/read target.
        No token serialization, token hash, credential inspection or new evidence.
        A collision invalidates the journal without writing a refusal artifact.
        Primary safety is construction-time exclusion of credential dataflow.
        Later independent status/counter/timestamp values may coincidentally equal
        arbitrary token strings; this check does not predict those future values.
        """
        _require(type(token) is PreparedToken)
        with self._lock:
            _require(not self._broken)
            raw = token.value
            lower_hex = raw.encode("ascii").hex()
            echoes = (raw, lower_hex, lower_hex.upper())
            def safe(value):
                if type(value) is dict:
                    return all(safe(key) and safe(item) for key, item in value.items())
                if type(value) in (list, tuple):
                    return all(safe(item) for item in value)
                if type(value) is str:
                    text = value
                elif value is None:
                    text = "null"
                elif type(value) is bool:
                    text = "true" if value else "false"
                elif type(value) in (int, float):
                    text = str(value)
                else:
                    return False  # No str/repr/serialization of arbitrary objects.
                return not any(echo in text for echo in echoes)

            domain = (self._header, self._events, self.fixture.read_path,
                sorted(STAGES | CLASSIFICATIONS | FAULTS | VERIFY_CLASSES),
                ("sequence", "monotonic_ns", "utc", "stage", "dispatch_id",
                 "after_policy_entry", "method", "path", "traffic", "body_sha256",
                 "frozen_identity_sha256", "status", "classification", "send_completed",
                 "fault_boundary", "verifier_classification", "matching_rows", "nonempty_rows",
                 "GET", "sheets_read", "sheets_mutation"))
            if not safe(domain) or any(echo.encode("ascii") in self.request.body for echo in echoes):
                self._broken = True
                raise TokenSafetyError()

    def event(self, stage, dispatch_id, *, status=None, classification=None,
              verifier=None, send_completed=None):
        with self._lock:
            _require(stage in STAGES and type(dispatch_id) is int and dispatch_id >= 0)
            _require(status is None or type(status) is int and 200 <= status <= 599)
            _require(classification is None or classification in CLASSIFICATIONS)
            _require(send_completed is None or type(send_completed) is bool)
            mutation_events = [e for e in self._events if e["dispatch_id"] == dispatch_id
                               and not e["stage"].startswith("verifier_")]
            stages = [e["stage"] for e in mutation_events]
            if stage in {"connect_started", "connect_completed", "dispatch_initiated",
                         "local_send_completed", "status_observed", "failure", "closed"}:
                _require(self._active and dispatch_id == self._attempts)
                previous = {"connect_started": [], "connect_completed": ["connect_started"],
                    "dispatch_initiated": ["connect_started", "connect_completed"],
                    "local_send_completed": ["connect_started", "connect_completed", "dispatch_initiated"],
                    "status_observed": ["connect_started", "connect_completed", "dispatch_initiated", "local_send_completed"]}
                if stage in previous:
                    _require(stages == previous[stage])
                else:
                    _require("closed" not in stages and "failure" not in stages
                             or stage == "closed" and stages[-1:] == ["failure"])
            if stage == "policy_entry":
                _require(self._entering_policy)
            if stage == "fault_injected":
                _require(self._active and stages[-1:] == ["local_send_completed"]
                         and self.fault == "after_send_before_status")
                # Fixed intended/actual boundary; never a remote-state claim.
            if stage == "attempt_result":
                _require(self._active and stages[-1:] == ["closed"])
            safe = {"sequence": len(self._events) + 1, "monotonic_ns": time.monotonic_ns(),
                    "utc": datetime.now(timezone.utc).isoformat(), "stage": stage,
                    "dispatch_id": dispatch_id, "after_policy_entry": self._policy}
            if stage == "dispatch_initiated":
                safe.update(method=self.request.method, path=self.request.uri,
                            traffic="sheets_mutation", body_sha256=self.request.body_hash,
                            frozen_identity_sha256=self.request.identity_hash)
            if stage.startswith("verifier_"):
                safe.update(method="GET", path=self.fixture.read_path, traffic="sheets_read")
            if status is not None:
                safe["status"] = status
            if classification is not None:
                safe["classification"] = classification
            if send_completed is not None:
                safe["send_completed"] = send_completed
            if stage == "fault_injected":
                safe["fault_boundary"] = "after_send_before_status"
            if verifier is not None:
                _require(type(verifier) is Verification and verifier.classification in VERIFY_CLASSES
                         and all(type(r) is int and 0 <= r < self.fixture.rows for r in verifier.rows)
                         and type(verifier.nonempty_rows) is int
                         and 0 <= verifier.nonempty_rows <= self.fixture.rows)
                safe.update(traffic="sheets_read", method="GET", path=self.fixture.read_path,
                            verifier_classification=verifier.classification,
                            matching_rows=list(verifier.rows),
                            nonempty_rows=verifier.nonempty_rows)
            try:
                self._write(safe)
            except BaseException:
                self._broken = True
                raise QualificationError() from None
            self._events.append(safe)

    def begin_attempt(self, request):
        with self._lock:
            _require(not self._active and not self._reading and not self._broken)
            validate_frozen(request, self.fixture, self.case_id)
            _require(request == self.request and request.identity_hash == self.request.identity_hash
                     and self._attempts == (1 if self._policy else 0))
            self._attempts += 1
            self._active = True
            return self._attempts

    def finish(self, result):
        with self._lock:
            if not self._broken:
                self.event("attempt_result", self._attempts, status=result.status,
                           classification=result.classification, send_completed=result.send_completed)
            self._result = result
            self._active = False

    def enter_replay_policy(self):
        """Qualification handoff only: does not execute a policy or dispatch."""
        with self._lock:
            _require(not self._active and not self._broken and not self._policy
                     and self._attempts == 1 and self._result == AttemptResult("ambiguous", None, True))
            facts = [e["stage"] for e in self._events if e["stage"] in
                     {"dispatch_initiated", "local_send_completed", "status_observed"}]
            _require(facts == ["dispatch_initiated", "local_send_completed"]
                     and all(e["dispatch_id"] == 1 for e in self._events
                             if e["stage"] in {"dispatch_initiated", "local_send_completed"})
                     and self._events[-1]["stage"] == "attempt_result")
            self._entering_policy = True
            try:
                self.event("policy_entry", 1)
            finally:
                self._entering_policy = False
            self._policy = True

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@dataclass(frozen=True, slots=True)
class AttemptResult:
    classification: str
    status: int | None
    send_completed: bool


class _GuardedSocket:
    """Exactly one header block then the stored body; no other socket writes."""
    def __init__(self, raw, request, journal, dispatch_id, auth_header):
        _require(raw is not None and callable(getattr(raw, "sendall", None)))
        self._raw, self._request, self._journal = raw, request, journal
        self._id, self._auth = dispatch_id, auth_header
        self.phase = 0
        self.initiated = False

    def sendall(self, data):
        _require(type(data) is bytes and self.phase < 2)
        if self.phase == 0:
            from retry_semantics.study2.sheets_offline import _validate_header_envelope
            # Frozen envelope validation is read-only; fixed errors never echo auth.
            _require(data.split(b"\r\n", 1)[0] ==
                     f"POST {self._request.uri} HTTP/1.1".encode("ascii"))
            _validate_header_envelope(data, self._request)
            auth = [line.split(b": ", 1)[1] for line in data[:-4].split(b"\r\n")[1:]
                    if line.lower().startswith(b"authorization: ")]
            _require(auth == [self._auth])
            self._journal.event("dispatch_initiated", self._id)
            self.initiated = True
        else:
            _require(data is self._request.body)
        # Advance before raw send: a failure cannot reopen the handoff.
        self.phase += 1
        self._raw.sendall(data)

    def makefile(self, *args, **kwargs):
        return self._raw.makefile(*args, **kwargs)

    def close(self):
        self._raw.close()


class _Connection(http.client.HTTPSConnection):
    """Production-shaped connection; injected already-connected socket ONLY.

    No default real network construction. A later TLS connector must be separately
    implemented, source-audited, gated and qualified. No tunnels/proxies/SDKs.
    """
    def __init__(self, timeout, connector):
        context = ssl.create_default_context()
        super().__init__(HOST, 443, timeout=timeout, context=context)
        self.auto_open = 0
        self.debuglevel = 0
        self._connector = connector
        self._connected_once = False

    def connect(self):
        _require(not self._connected_once and self._tunnel_host is None)
        self._connected_once = True
        _require(self._connector is not None)
        self.sock = self._connector(HOST, 443, self.timeout, self._context)
        _require(self.sock is not None)


def mutation_attempt(request, token, journal, *, timeout, dispatch_budget_seconds,
                     socket_connector=None):
    """One initial send or one explicit replay. No live connector exists here."""
    _require(type(token) is PreparedToken and type(journal) is EvidenceJournal)
    check_runtime()
    _number(timeout, positive=True)
    _number(dispatch_budget_seconds, positive=True)
    _require(dispatch_budget_seconds >= timeout)
    token.check_ready(now=time.time(), dispatch_budget_seconds=dispatch_budget_seconds)
    with journal._lock:
        journal.assert_token_safe(token)
        dispatch_id = journal.begin_attempt(request)
    # Equality authorizes this representation, but transmission always selects
    # the journal's original snapshot, even if the caller supplied an equal copy.
    request = journal.request
    connection = None
    guard = None
    status = None
    completed = False
    result = AttemptResult("invalid_evidence", None, False)
    try:
        connection = _Connection(timeout, socket_connector)
        journal.event("connect_started", dispatch_id)
        connection.connect()
        journal.event("connect_completed", dispatch_id)
        token.check_ready(now=time.time(), dispatch_budget_seconds=dispatch_budget_seconds)
        guard = _GuardedSocket(connection.sock, request, journal, dispatch_id,
                               ("Bearer " + token.value).encode("ascii"))
        connection.sock = guard
        connection.putrequest("POST", request.uri, skip_host=True, skip_accept_encoding=True)
        for name, value in request.headers:
            connection.putheader(name, value)
        for name, value in (("Host", HOST), ("Authorization", "Bearer " + token.value),
                            ("Content-Length", str(len(request.body))),
                            ("Accept-Encoding", "identity"), ("Connection", "close")):
            connection.putheader(name, value)
        connection.endheaders(request.body, encode_chunked=False)
        _require(guard.phase == 2 and guard.initiated)
        completed = True
        journal.event("local_send_completed", dispatch_id)
        if journal.fault == "after_send_before_status" and dispatch_id == 1:
            journal.event("fault_injected", dispatch_id)
            result = AttemptResult("ambiguous", None, True)
        else:
            response = connection.getresponse()
            status = response.status
            _require(type(status) is int and 200 <= status <= 599)
            journal.event("status_observed", dispatch_id, status=status)
            classification = ("known_success" if status < 300 else
                              "redirect_refused" if status < 400 else
                              "auth_issue" if status == 401 else "known_http_error")
            # Mutation response content/headers are unnecessary and never retained.
            try:
                response.read()
            except (OSError, http.client.HTTPException):
                if status < 300:
                    classification = "known_success_incomplete_response"
            finally:
                response.close()
            result = AttemptResult(classification, status, completed)
    except (OSError, http.client.HTTPException):
        classification = ("known_non_dispatch" if guard is None or not guard.initiated else
                          "ambiguous" if completed else "incomplete_send_unknown")
        result = AttemptResult(classification, status, completed)
        journal.event("failure", dispatch_id, classification=classification)
    except Exception:
        # Evidence/envelope/programming failure invalidates; never serialize input.
        journal._broken = True
        raise QualificationError() from None
    finally:
        try:
            if connection is not None:
                connection.close()
            journal.event("closed", dispatch_id)
        except Exception:
            journal._broken = True
            journal.finish(AttemptResult("invalid_evidence", status, completed))
            raise QualificationError() from None
        journal.finish(result)
    return result


@dataclass(frozen=True, slots=True)
class Verification:
    classification: str
    rows: tuple[int, ...] = ()
    nonempty_rows: int = 0


def parse_grid(payload, fixture, marker):
    """Strict one-range whole-fixture read. Trailing omitted rows/cells are blank.

    Zero is a current complete-read result, never a historical noncommit label.
    Raw/provider-controlled strings are never included in the returned summary.
    """
    try:
        _require(type(payload) is dict and payload["spreadsheetId"] == fixture.spreadsheet_id)
        sheets = payload["sheets"]
        _require(type(sheets) is list and len(sheets) == 1)
        sheet = sheets[0]
        props = sheet["properties"]
        _require(props["sheetId"] == fixture.sheet_id and type(props["sheetId"]) is int
                 and props["title"] == fixture.title and props["sheetType"] == "GRID"
                 and props["gridProperties"] == {"rowCount": fixture.rows, "columnCount": fixture.columns}
                 and not sheet.get("merges") and not sheet.get("tables"))
        data = sheet["data"]
        _require(type(data) is list and len(data) == 1)
        grid = data[0]
        _require(type(grid) is dict and type(grid.get("startRow", 0)) is int
                 and type(grid.get("startColumn", 0)) is int
                 and grid.get("startRow", 0) == grid.get("startColumn", 0) == 0)
        rows = grid.get("rowData", [])
        _require(type(rows) is list and len(rows) <= fixture.rows)
        matches, nonempty = [], 0
        for index, row in enumerate(rows):
            _require(type(row) is dict)
            values = row.get("values", [])
            _require(type(values) is list and len(values) <= fixture.columns)
            entered = []
            for cell in values:
                _require(type(cell) is dict)
                val = cell.get("userEnteredValue", {})
                _require(type(val) is dict and (not val or set(val) == {"stringValue"}))
                _require(not val or type(val["stringValue"]) is str)
                entered.append(val.get("stringValue"))
            entered += [None] * (fixture.columns - len(entered))
            if any(v is not None for v in entered):
                nonempty += 1
            if entered[0] == marker:
                _require(entered == [marker, "engineering-v1", "literal-payload"])
                matches.append(index)
        return Verification("zero_matches" if not matches else
                            "one_match" if len(matches) == 1 else "multiple_matches",
                            tuple(matches), nonempty)
    except (KeyError, TypeError, ValueError, IndexError):
        return Verification("malformed_or_incomplete")


class ReadOnlyVerifier:
    """Separate GET-only capability; no generic method/body/URL or mutation client."""
    def __init__(self, fixture, *, socket_connector=None, timeout=10, max_response_bytes=1000000):
        _require(type(fixture) is Fixture and type(max_response_bytes) is int
                 and max_response_bytes > 0)
        _number(timeout, positive=True)
        self.fixture, self._connector = fixture, socket_connector
        self.timeout, self.max_response_bytes = timeout, max_response_bytes

    def inspect(self, token, marker, journal):
        _require(type(token) is PreparedToken and type(marker) is str
                 and type(journal) is EvidenceJournal and journal.fixture == self.fixture
                 and marker == self.fixture.marker(journal.case_id) and not journal._broken)
        token.check_ready(now=time.time(), dispatch_budget_seconds=self.timeout)
        with journal._lock:
            _require(not journal._active and not journal._reading)
            journal.assert_token_safe(token)
            journal._reading = True
            journal._reads += 1
            read_id = journal._reads
        connection = None
        result = Verification("verifier_uncertainty")
        try:
            connection = _Connection(self.timeout, self._connector)
            connection.connect()
            # Guard actual serializer output, not a caller's 'read' label.
            raw = connection.sock
            expected_path = self.fixture.read_path
            auth = ("Bearer " + token.value).encode()

            class ReadSocket:
                sent = False

                def sendall(self, data):
                    _require(not self.sent and type(data) is bytes)
                    lines = data[:-4].split(b"\r\n")
                    _require(data.endswith(b"\r\n\r\n") and lines[0] ==
                             f"GET {expected_path} HTTP/1.1".encode())
                    observed = {}
                    for line in lines[1:]:
                        name, sep, value = line.partition(b": ")
                        name = name.lower()
                        _require(sep and name not in observed)
                        observed[name] = value
                    _require(observed == {b"host": HOST.encode(), b"authorization": auth,
                        b"accept": b"application/json", b"accept-encoding": b"identity",
                        b"connection": b"close"})
                    self.sent = True
                    journal.event("verifier_initiated", read_id)
                    raw.sendall(data)

                def makefile(self, *args, **kwargs):
                    return raw.makefile(*args, **kwargs)

                def close(self):
                    raw.close()

            connection.sock = ReadSocket()
            connection.putrequest("GET", expected_path, skip_host=True, skip_accept_encoding=True)
            for name, value in (("Host", HOST), ("Authorization", "Bearer " + token.value),
                                ("Accept", "application/json"), ("Accept-Encoding", "identity"),
                                ("Connection", "close")):
                connection.putheader(name, value)
            connection.endheaders()
            response = connection.getresponse()
            try:
                journal.event("verifier_status", read_id, status=response.status)
                if response.status != 200:
                    return result
                body = response.read(self.max_response_bytes + 1)
                _require(len(body) <= self.max_response_bytes
                         and response.length in (None, 0)
                         and response.read(1) == b"" and response.isclosed())
                def unique(pairs):
                    result = {}
                    for key, value in pairs:
                        _require(key not in result)
                        result[key] = value
                    return result
                payload = json.loads(body, object_pairs_hook=unique,
                                     parse_constant=lambda _: (_require(False)))
                result = parse_grid(payload, self.fixture, marker)
                return result
            finally:
                response.close()
        except Exception:
            return Verification("verifier_uncertainty")
        finally:
            try:
                if connection is not None:
                    connection.close()
                journal.event("verifier_summary", read_id, verifier=result)
            except Exception:
                journal._broken = True
                raise QualificationError() from None
            finally:
                journal._reading = False
