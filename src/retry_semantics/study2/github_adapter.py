"""Phase 2B engineering adapter. ENGINEERING VALIDATION — NOT PAPER DATA.

No experiment execution or retry policy. An injected transport is trusted test
code: only the default transport's HTTP dispatch behavior is established here.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
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


@dataclass(frozen=True, slots=True)
class HTTPAttempt:
    index: int
    request: EngineeringRequest
    dispatch_started: bool
    dispatch_ended: bool
    outcome: str
    status: int | None = None
    response_metadata: tuple[tuple[str, str], ...] = ()


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


def https_single_attempt(request: EngineeringRequest, token: str, timeout: float) -> HTTPResponse:
    """Fresh verified TLS/HTTP1 connection; no pool, proxy, redirect or retry.

    connect() is explicit and auto_open is disabled: even a missing/closed socket
    cannot trigger implicit reconnection between headers and body. Debug is off.
    http.client removes HTTP transfer framing, but does not decompress content.
    """
    parts = urlsplit(request.url)
    connection = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=timeout)
    connection.set_debuglevel(0)
    connection.auto_open = 0
    try:
        connection.connect()
        connection.putrequest(request.method, request.target_path,
                              skip_host=True, skip_accept_encoding=True)
        for name, value in request.headers:
            connection.putheader(name, value)
        connection.putheader("Authorization", f"Bearer {token}")
        connection.endheaders(request.body or None, encode_chunked=False)
        response = connection.getresponse()
        # Keep status/headers even if receiving the body fails.
        headers = tuple(response.getheaders())
        try:
            body = response.read()
        except TimeoutError:
            return HTTPResponse(response.status, headers, b"", "transport_timeout")
        except ConnectionError:
            return HTTPResponse(response.status, headers, b"", "transport_connection_error")
        except Exception:
            return HTTPResponse(response.status, headers, b"", "transport_error")
        return HTTPResponse(response.status, headers, body)
    finally:
        connection.close()


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
        try:
            response = self._transport(request, self.config.token, self.config.timeout_seconds)
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
            failure = response.read_error
            metadata = tuple((k.lower(), v.replace(self.config.token, "[REDACTED]"))
                             for k, v in response.headers if k.lower() in _METADATA)
        attempt = HTTPAttempt(trace.attempt_count + 1, request, True, True,
                              failure or "http_response", status, metadata)
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
