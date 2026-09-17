"""Phase 2C engineering adapter. ENGINEERING VALIDATION — NOT PAPER DATA.

No experiment execution or retry policy. An injected transport is trusted test
code: only the default transport's HTTP dispatch behavior is established here.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum
import http.client
import json
import math
import re
from urllib.parse import parse_qsl, quote, urlsplit

from retry_semantics.study2.github_semantics import GITHUB_OBSERVATION_REQUIREMENTS as READ


@dataclass(frozen=True, slots=True)
class GitHubConfig:
    api_base_url: str
    owner: str
    repository: str
    token: str = field(repr=False, compare=False)
    api_version: str
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        # Messages deliberately contain no supplied values.
        valid = all(type(v) is str and v for v in (
            self.api_base_url, self.owner, self.repository, self.token, self.api_version,
        ))
        if not valid:
            raise ValueError("nonempty runtime GitHub configuration required")
        if not re.fullmatch(r"[!-~]+", self.token):
            raise ValueError("invalid authentication configuration")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.api_version):
            raise ValueError("explicit date-form API version required")
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", v) or v in (".", "..")
               for v in (self.owner, self.repository)):
            raise ValueError("invalid repository scope")
        parts = None
        try:
            parts = urlsplit(self.api_base_url)
            port = parts.port
        except ValueError:
            port = -1
        if (parts is None or parts.scheme != "https" or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment or port == -1
                or not re.fullmatch(r"https://[A-Za-z0-9.\-\[\]:]+(?:/[A-Za-z0-9_-]+)*",
                                    self.api_base_url)):
            raise ValueError("HTTPS API base without credentials/query/fragment required")
        if (type(self.timeout_seconds) not in (int, float)
                or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0):
            raise ValueError("finite positive socket timeout required")
        if any(self.token in v for v in (
            self.api_base_url, self.owner, self.repository, self.api_version,
        )):
            raise ValueError("authentication must not occur in nonsecret configuration")

    @property
    def issue_url(self) -> str:
        return (f"{self.api_base_url}/repos/{quote(self.owner, safe='')}/"
                f"{quote(self.repository, safe='')}/issues")


@dataclass(frozen=True, slots=True)
class EngineeringRequest:
    """Nonsecret identity at the HTTP boundary; body is the actual UTF-8 bytes."""
    method: str
    url: str
    target_path: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    read_error: str | None = None


class LifecycleStage(str, Enum):
    REQUEST_PREPARED = "REQUEST_PREPARED"
    CONNECT_STARTED = "CONNECT_STARTED"
    CONNECT_COMPLETED = "CONNECT_COMPLETED"
    REQUEST_SEND_STARTED = "REQUEST_SEND_STARTED"
    LOCAL_REQUEST_SEND_COMPLETED = "LOCAL_REQUEST_SEND_COMPLETED"
    RESPONSE_WAIT_STARTED = "RESPONSE_WAIT_STARTED"
    RESPONSE_HEADERS_RECEIVED = "RESPONSE_HEADERS_RECEIVED"
    RESPONSE_BODY_COMPLETED = "RESPONSE_BODY_COMPLETED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    INJECTED_FAULT = "INJECTED_FAULT"


class EngineeringFaultPoint(str, Enum):
    BEFORE_REQUEST_SEND = "BEFORE_REQUEST_SEND"
    AFTER_LOCAL_REQUEST_SEND_BEFORE_RESPONSE = "AFTER_LOCAL_REQUEST_SEND_BEFORE_RESPONSE"


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    sequence: int
    stage: LifecycleStage
    # Only typed, fixed metadata; no buffers, exception text or credentials.
    fault_point: EngineeringFaultPoint | None = None

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 1 or not isinstance(self.stage, LifecycleStage):
            raise ValueError("invalid lifecycle event")
        if self.stage is LifecycleStage.INJECTED_FAULT:
            if not isinstance(self.fault_point, EngineeringFaultPoint):
                raise ValueError("typed engineering fault point required")
        elif self.fault_point is not None:
            raise ValueError("fault metadata only allowed on injected fault")


_NORMAL_STAGES = tuple(LifecycleStage)[:8]
_TRANSPORT_ERRORS = frozenset({"transport_timeout", "transport_connection_error", "transport_error"})


@dataclass(frozen=True, slots=True)
class HTTPAttempt:
    index: int
    request: EngineeringRequest
    dispatch_started: bool
    dispatch_ended: bool
    outcome: str
    status: int | None = None
    response_metadata: tuple[tuple[str, str], ...] = ()
    # Empty means historical/opaque transport: no granular evidence available.
    lifecycle: tuple[LifecycleEvent, ...] = ()

    def __post_init__(self) -> None:
        if type(self.lifecycle) is not tuple:
            raise ValueError("immutable lifecycle required")
        if not self.lifecycle:
            return
        # Legacy flags describe a finalized adapter transport-boundary invocation,
        # not request transmission or provider receipt/execution.
        if self.dispatch_started is not True or self.dispatch_ended is not True:
            raise ValueError("instrumented attempt requires finalized transport boundary")
        stages = []
        for index, event in enumerate(self.lifecycle, 1):
            if not isinstance(event, LifecycleEvent) or event.sequence != index:
                raise ValueError("invalid lifecycle ordering")
            stages.append(event.stage)
        terminal = stages[-1] in (LifecycleStage.TRANSPORT_ERROR, LifecycleStage.INJECTED_FAULT)
        prefix = stages[:-1] if terminal else stages
        if not prefix or tuple(prefix) != _NORMAL_STAGES[:len(prefix)]:
            raise ValueError("invalid lifecycle prefix")
        if terminal:
            if stages[-1] is LifecycleStage.INJECTED_FAULT:
                point = self.lifecycle[-1].fault_point
                expected = (LifecycleStage.CONNECT_COMPLETED if point is EngineeringFaultPoint.BEFORE_REQUEST_SEND
                            else LifecycleStage.LOCAL_REQUEST_SEND_COMPLETED)
                if prefix[-1] is not expected or self.outcome != "injected_fault":
                    raise ValueError("invalid injected fault boundary/outcome")
            elif self.outcome not in _TRANSPORT_ERRORS:
                raise ValueError("transport error requires failure outcome")
        elif tuple(stages) != _NORMAL_STAGES or self.outcome != "http_response":
            raise ValueError("HTTP response requires complete lifecycle")
        if (self.status is not None) != (LifecycleStage.RESPONSE_HEADERS_RECEIVED in prefix):
            raise ValueError("response status and header evidence disagree")
        if self.response_metadata and LifecycleStage.RESPONSE_HEADERS_RECEIVED not in prefix:
            raise ValueError("response metadata requires response headers")


@dataclass(frozen=True, slots=True)
class EngineeringTrace:
    operation: str
    attempts: tuple[HTTPAttempt, ...] = ()
    outcome: str = "not_started"
    pages_fetched: int = 0
    raw_entries: int = 0
    excluded_prs: int = 0
    repeated_identities: int = 0
    distinct_issues: int = 0
    complete: bool = False

    def __post_init__(self) -> None:
        if (self.outcome == "success") != self.complete:
            raise ValueError("trace success and completeness disagree")
        if self.complete or self.outcome == "success":
            if not self.attempts:
                raise ValueError("successful trace requires HTTP attempt evidence")
            if any(a.outcome != "http_response" for a in self.attempts):
                raise ValueError("successful trace cannot contain terminal attempt failure")

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)


@dataclass(frozen=True, slots=True)
class ObservedIssue:
    identity: tuple[tuple[str, str], int]
    title: str
    body: str | None
    state: str


@dataclass(frozen=True, slots=True)
class CreationResult:
    issue: ObservedIssue
    trace: EngineeringTrace


@dataclass(frozen=True, slots=True)
class ObservationResult:
    issues: tuple[ObservedIssue, ...]
    trace: EngineeringTrace

    def matching(self, predicate: Callable[[ObservedIssue], bool]) -> tuple[ObservedIssue, ...]:
        """Caller matching occurs only after exhaustive traversal."""
        return tuple(issue for issue in self.issues if predicate(issue))


class GitHubEngineeringError(Exception):
    """A safe fixed category and nonsecret trace; never provider/transport text."""
    def __init__(self, category: str, trace: EngineeringTrace):
        super().__init__(category)
        self.category = category
        self.trace = replace(trace, outcome=category, complete=False)


# Transport receives credentials only at dispatch, never inside request evidence.
Transport = Callable[[EngineeringRequest, str, float], HTTPResponse]


class _InjectedEngineeringFault(Exception):
    def __init__(self) -> None:
        super().__init__("injected_fault")


def _event(events: list[LifecycleEvent], stage: LifecycleStage,
           point: EngineeringFaultPoint | None = None) -> None:
    events.append(LifecycleEvent(len(events) + 1, stage, point))


@dataclass(frozen=True, slots=True)
class OfflineFaultTransport:
    """Trusted OFFLINE fake connection factory only; never use against GitHub.

    No default factory: fault injection cannot be enabled on the live default
    transport or smoke. The caller is responsible for supplying offline machinery.
    """
    connection_factory: Callable
    fault_point: EngineeringFaultPoint

    def __post_init__(self) -> None:
        if not callable(self.connection_factory) or not isinstance(self.fault_point, EngineeringFaultPoint):
            raise ValueError("offline factory and typed engineering fault point required")

    def __call__(self, request: EngineeringRequest, token: str, timeout: float,
                 *, lifecycle: list[LifecycleEvent] | None = None) -> HTTPResponse:
        return _https_attempt(request, token, timeout, self.connection_factory,
                              lifecycle if lifecycle is not None else [], self.fault_point)


def https_single_attempt(request: EngineeringRequest, token: str, timeout: float,
                         *, lifecycle: list[LifecycleEvent] | None = None) -> HTTPResponse:
    """Fresh verified TLS/HTTP1 connection; no pool, proxy, redirect or retry.

    connect() is explicit and auto_open is disabled: even a missing/closed socket
    cannot trigger implicit reconnection between headers and body. Debug is off.
    http.client removes HTTP transfer framing, but does not decompress content.
    """
    return _https_attempt(request, token, timeout, http.client.HTTPSConnection,
                          lifecycle if lifecycle is not None else [])


def _https_attempt(request: EngineeringRequest, token: str, timeout: float,
                   connection_factory: Callable, events: list[LifecycleEvent],
                   fault_point: EngineeringFaultPoint | None = None) -> HTTPResponse:
    parts = urlsplit(request.url)
    connection = connection_factory(parts.hostname, parts.port, timeout=timeout)
    try:
        connection.set_debuglevel(0)
        connection.auto_open = 0
        _event(events, LifecycleStage.CONNECT_STARTED)
        connection.connect()
        _event(events, LifecycleStage.CONNECT_COMPLETED)
        # putrequest/putheader buffer locally; endheaders sends headers AND body.
        connection.putrequest(request.method, request.target_path,
                              skip_host=True, skip_accept_encoding=True)
        for name, value in request.headers:
            connection.putheader(name, value)
        connection.putheader("Authorization", f"Bearer {token}")
        if fault_point is EngineeringFaultPoint.BEFORE_REQUEST_SEND:
            _event(events, LifecycleStage.INJECTED_FAULT, fault_point)
            raise _InjectedEngineeringFault()
        _event(events, LifecycleStage.REQUEST_SEND_STARTED)
        connection.endheaders(request.body or None, encode_chunked=False)
        _event(events, LifecycleStage.LOCAL_REQUEST_SEND_COMPLETED)
        if fault_point is EngineeringFaultPoint.AFTER_LOCAL_REQUEST_SEND_BEFORE_RESPONSE:
            _event(events, LifecycleStage.INJECTED_FAULT, fault_point)
            raise _InjectedEngineeringFault()
        _event(events, LifecycleStage.RESPONSE_WAIT_STARTED)
        response = connection.getresponse()
        _event(events, LifecycleStage.RESPONSE_HEADERS_RECEIVED)
        # Keep status/headers even if receiving the body fails.
        headers = ()
        try:
            headers = tuple(response.getheaders())
            body = response.read()
        except TimeoutError:
            return HTTPResponse(response.status, headers, b"", "transport_timeout")
        except ConnectionError:
            return HTTPResponse(response.status, headers, b"", "transport_connection_error")
        except Exception:
            return HTTPResponse(response.status, headers, b"", "transport_error")
        _event(events, LifecycleStage.RESPONSE_BODY_COMPLETED)
        return HTTPResponse(response.status, headers, body)
    finally:
        # Cleanup must not mask a terminal fault/failure or invent provider facts.
        try:
            connection.close()
        except Exception:
            pass


_METADATA = frozenset({
    "x-github-request-id", "x-ratelimit-limit", "x-ratelimit-remaining",
    "x-ratelimit-reset", "x-ratelimit-resource", "retry-after",
    "x-github-api-version-selected", "content-type", "content-encoding",
    "warning", "deprecation", "sunset",
})


def _header(response: HTTPResponse, name: str) -> str | None:
    values = [v for k, v in response.headers if k.lower() == name]
    if len(values) > 1:
        raise ValueError("duplicate relevant response header")
    return values[0] if values else None


def _json(response: HTTPResponse) -> object:
    if (_header(response, "content-encoding") or "identity").lower() != "identity":
        raise ValueError("encoded response unsupported")
    media = (_header(response, "content-type") or "").split(";", 1)[0].strip().lower()
    if media != "application/json" and not (media.startswith("application/") and media.endswith("+json")):
        raise ValueError("JSON representation required")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("non-JSON constant")

    return json.loads(response.body.decode("utf-8"), object_pairs_hook=unique_pairs,
                      parse_constant=invalid_constant)


def _next_link(value: str | None) -> str | None:
    """Conservative Link grammar: fail closed on malformed/ambiguous headers.

    Supports quoted parameters (including commas), multiple relation tokens,
    and extension parameters. No anchor context override is permitted.
    """
    if value is None:
        return None
    remaining = value.strip()
    next_url = None
    while remaining:
        link = re.match(r"<([^<>\s]+)>", remaining)
        if not link:
            raise ValueError("malformed Link")
        url = link[1]
        remaining = remaining[link.end():]
        params = {}
        while remaining.lstrip().startswith(";"):
            remaining = remaining.lstrip()[1:].lstrip()
            param = re.match(r'([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(?:"([^"\\]*)"|([A-Za-z0-9_.:-]+))', remaining)
            if not param or param[1].lower() in params:
                raise ValueError("malformed Link parameter")
            params[param[1].lower()] = param[2] if param[2] is not None else param[3]
            remaining = remaining[param.end():]
        if "anchor" in params or "rel" not in params:
            raise ValueError("unsupported Link context/relation")
        relations = params["rel"].lower().split()
        if not relations or any(not re.fullmatch(r"[a-z][a-z0-9.-]*", rel) for rel in relations):
            raise ValueError("malformed or unsupported Link relation")
        if "next" in relations:
            if next_url is not None:
                raise ValueError("multiple next links")
            next_url = url
        remaining = remaining.strip()
        if remaining:
            if not remaining.startswith(",") or not remaining[1:].strip():
                raise ValueError("malformed Link separator")
            remaining = remaining[1:].strip()
    if not value.strip():
        raise ValueError("empty Link")
    return next_url


class GitHubEngineeringAdapter:
    def __init__(self, config: GitHubConfig, *, transport: Transport = https_single_attempt):
        self.config = config
        self._transport = transport

    def _request(self, method: str, url: str, body: bytes = b"") -> EngineeringRequest:
        parts = urlsplit(url)
        headers = (
            ("Host", parts.netloc), ("Accept", "application/vnd.github.raw+json"),
            ("X-GitHub-Api-Version", self.config.api_version),
            ("User-Agent", "retry-semantics-engineering"),
            ("Accept-Encoding", "identity"), ("Connection", "close"),
        )
        if method == "POST":
            headers += (("Content-Type", "application/json; charset=utf-8"),
                        ("Content-Length", str(len(body))))
        if self.config.token in url or any(self.config.token in v for _, v in headers) or self.config.token.encode() in body:
            raise ValueError("authentication must not occur in request evidence")
        path = parts.path + ("?" + parts.query if parts.query else "")
        return EngineeringRequest(method, url, path, headers, body)

    def prepare_create_issue(self, *, title: str, body: str) -> EngineeringRequest:
        """Inspectable intended request before dispatch, with no authentication."""
        if type(title) is not str or not title or type(body) is not str:
            raise ValueError("nonempty title and string body required")
        if self.config.token in title or self.config.token in body:
            raise ValueError("authentication must not occur in controlled content")
        payload = json.dumps({"title": title, "body": body}, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        return self._request("POST", self.config.issue_url, payload)

    def _dispatch(self, request: EngineeringRequest, trace: EngineeringTrace) -> tuple[HTTPResponse, EngineeringTrace]:
        response = None
        failure = None
        events = []
        instrumented = self._transport is https_single_attempt or isinstance(self._transport, OfflineFaultTransport)
        if instrumented:
            _event(events, LifecycleStage.REQUEST_PREPARED)
        try:
            if instrumented:
                response = self._transport(request, self.config.token, self.config.timeout_seconds,
                                           lifecycle=events)
            else:
                response = self._transport(request, self.config.token, self.config.timeout_seconds)
        except _InjectedEngineeringFault:
            failure = "injected_fault"
        except TimeoutError:
            failure = "transport_timeout"
        except ConnectionError:
            failure = "transport_connection_error"
        except Exception:
            failure = "transport_error"
        metadata = ()
        status = None
        if response is not None:
            status = response.status
            failure = (response.read_error if response.read_error in _TRANSPORT_ERRORS else
                       "transport_error" if response.read_error is not None else None)
            metadata = tuple((k.lower(), v.replace(self.config.token, "[REDACTED]"))
                             for k, v in response.headers if k.lower() in _METADATA)
        if instrumented and failure and failure != "injected_fault":
            _event(events, LifecycleStage.TRANSPORT_ERROR)
        attempt = HTTPAttempt(trace.attempt_count + 1, request, True, True,
                              failure or "http_response", status, metadata, tuple(events))
        trace = replace(trace, attempts=trace.attempts + (attempt,))
        if failure:
            # Raise outside except: no credential-bearing exception context.
            raise GitHubEngineeringError(failure, trace)
        return response, trace

    def _issue(self, entry: object) -> ObservedIssue:
        if not isinstance(entry, dict):
            raise ValueError("list entry must be object")
        number = entry.get("number")
        if type(number) is not int or number <= 0:
            raise ValueError("positive issue number required")
        if (type(entry.get("title")) is not str or "body" not in entry
                or (entry["body"] is not None and type(entry["body"]) is not str)
                or entry.get("state") not in ("open", "closed")):
            raise ValueError("issue content/state unavailable")
        if any(self.config.token in value for value in (entry["title"], entry["body"] or "")):
            raise ValueError("secret in provider content")
        return ObservedIssue(READ.issue_resource_identity(
            (self.config.owner, self.config.repository), entry),
            entry["title"], entry["body"], entry["state"])

    def _decode(self, response: HTTPResponse) -> object:
        version = _header(response, "x-github-api-version-selected")
        if version is not None and version != self.config.api_version:
            raise ValueError("response API version differs from request")
        return _json(response)

    def create_issue(self, *, title: str, body: str) -> CreationResult:
        request = self.prepare_create_issue(title=title, body=body)
        response, trace = self._dispatch(request, EngineeringTrace("create_issue"))
        if response.status != 201:
            raise GitHubEngineeringError("http_error", trace)
        issue = None
        try:
            entry = self._decode(response)
            issue = self._issue(entry)
            if not READ.is_issue_entry(entry):
                issue = None
        except (ValueError, TypeError, UnicodeError, RecursionError):
            pass
        if issue is None:
            raise GitHubEngineeringError("malformed_success", trace)
        return CreationResult(issue, replace(trace, outcome="success", complete=True))

    def _validate_next(
        self, url: str, canonical_path: str | None,
    ) -> tuple[str, int, str | None]:
        parts, expected = urlsplit(url), urlsplit(self.config.issue_url)
        if (parts.scheme != expected.scheme or parts.hostname != expected.hostname
                or parts.port != expected.port or parts.username or parts.password
                or parts.fragment
                or any(c.isspace() or ord(c) < 32 for c in url)
                or self.config.token in url):
            raise ValueError("unsafe pagination URL")
        if canonical_path is not None:
            if parts.path != canonical_path:
                raise ValueError("bound pagination path changed")
        elif parts.path != expected.path:
            prefix = urlsplit(self.config.api_base_url).path
            if not re.fullmatch(re.escape(prefix) + r"/repositories/[1-9][0-9]*/issues", parts.path):
                raise ValueError("unsupported pagination path")
            # Trust the first constrained provider-issued canonical target, not
            # an ID derived from config. Bind it only within this traversal.
            canonical_path = parts.path
        pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
        query = dict(pairs)
        if (len(query) != len(pairs) or set(query) != {"state", "per_page", "page"}
                or query["state"] != "all" or query["per_page"] != "100"
                or not re.fullmatch(r"[1-9][0-9]*", query["page"])):
            raise ValueError("pagination scope/filter mismatch")
        # Canonical page identity prevents loops disguised by query ordering.
        return url, int(query["page"]), canonical_path

    def observe_issues(self) -> ObservationResult:
        url = self.config.issue_url + "?state=all&per_page=100&page=1"
        visited = {1}
        canonical_path = None
        issues = {}
        trace = EngineeringTrace("observe_issues")
        while True:
            response, trace = self._dispatch(self._request("GET", url), trace)
            if response.status != 200:
                raise GitHubEngineeringError("http_error", trace)
            trace = replace(trace, pages_fetched=trace.pages_fetched + 1)
            entries = None
            try:
                decoded = self._decode(response)
                if isinstance(decoded, list):
                    entries = decoded
            except (ValueError, TypeError, UnicodeError, RecursionError):
                pass
            if entries is None:
                raise GitHubEngineeringError("malformed_success", trace)
            for entry in entries:
                trace = replace(trace, raw_entries=trace.raw_entries + 1)
                issue = None
                try:
                    # Validate mapping and content/identity before key-based exclusion.
                    issue = self._issue(entry)
                except (ValueError, TypeError):
                    pass
                if issue is None:
                    raise GitHubEngineeringError("malformed_success", trace)
                if not READ.is_issue_entry(entry):
                    trace = replace(trace, excluded_prs=trace.excluded_prs + 1)
                elif issue.identity in issues:
                    trace = replace(trace, repeated_identities=trace.repeated_identities + 1)
                else:
                    # First appearance retained, including on content/state drift.
                    issues[issue.identity] = issue
                    trace = replace(trace, distinct_issues=len(issues))
            failure = None
            next_url = None
            try:
                next_url = _next_link(_header(response, "link"))
                if next_url is not None:
                    next_url, page, canonical_path = self._validate_next(next_url, canonical_path)
                    if page in visited:
                        failure = "pagination_loop"
                    else:
                        visited.add(page)
            except (ValueError, TypeError):
                failure = "unsafe_or_malformed_pagination"
            if failure:
                raise GitHubEngineeringError(failure, trace)
            if next_url is None:
                return ObservationResult(tuple(issues.values()),
                                         replace(trace, outcome="success", complete=True))
            url = next_url
