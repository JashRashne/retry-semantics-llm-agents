"""DRAFT one-shot desktop OAuth preparer. Never imported by the read transport.

No ADC, caches, refresh method, browser launch, persistence or configurable scope.
Only acquire() can open sockets, and it requires separate acquisition permission.
Manual browser interaction uses a loopback listener, never the deprecated OOB flow.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import functools
import hashlib
import hmac
import http.client
import http.server
import os
from pathlib import Path
import platform
import re
import secrets
import socket
import ssl
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_live_go_phase1 as p1
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2.sheets_phase2_control import require, strict_json, label, digest

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
CALLBACK_ISSUER = "https://accounts.google.com"
ACQUISITION_CONFIRMATION = "EXPLICIT_OPERATOR_OAUTH_ACQUISITION"


class CredentialRefused(ValueError):
    def __init__(self):
        super().__init__()


class AcquisitionFailure(Exception):
    """Internal fixed reason only; never carry provider text or an exception."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__()


STAGES = ("oauth_intent_persisted", "listener_ready", "authorization_url_presented",
          "callback_received", "callback_parsed", "callback_validated",
          "token_request_constructed", "token_connection_started", "token_response_started",
          "token_http_validated", "token_body_complete", "token_json_parsed",
          "token_semantics_validated", "acquisition_persistence_started", "acquisition_persisted")
REASONS = frozenset(("callback_timeout", "callback_count_invalid", "callback_transport_failure",
    "malformed_query", "state_mismatch", "issuer_mismatch", "scope_mismatch",
    "missing_required_field", "duplicate_security_field", "provider_refusal",
    "dns_failure", "tcp_failure", "tls_failure", "connection_other",
    "non_success_status", "framing_invalid", "content_encoding_invalid",
    "content_type_invalid", "body_size_invalid", "body_incomplete",
    "malformed_json", "required_field_missing", "semantic_scope_mismatch",
    "token_type_invalid", "expires_in_invalid", "token_validation_failed",
    "persistence_failure", "handoff_lifetime_invalid", "local_failure"))


def acquisition_failure_consistent(value):
    """Validate only the closed, mutually consistent failure projection."""
    if (type(value) is not dict or set(value) != {"schema", "status", "recovery",
            "last_stage", "reason", "http_status_class", "framing_class",
            "content_encoding_class", "content_type_class", "callback_count"}
        or value["schema"] != "sheets-phase4-acquisition-failure-v1"
        or value["status"] != "BLOCKED" or value["recovery"] != "stop-review-no-retry"
        or type(value["last_stage"]) is not str or value["last_stage"] not in STAGES
        or type(value["reason"]) is not str or value["reason"] not in REASONS
        or value["http_status_class"] not in (None, "200", "other_2xx", "4xx", "5xx", "other")
        or value["framing_class"] not in (None, "content_length", "chunked", "unsupported_transfer",
                                               "neither", "conflicting")
        or value["content_encoding_class"] not in (None, "absent", "identity", "other")
        or value["content_type_class"] not in (None, "json", "json_utf8", "other")
        or value["callback_count"] not in ("zero", "one", "invalid")):
        return False

    stage = value["last_stage"]
    reason = value["reason"]
    status = value["http_status_class"]
    framing = value["framing_class"]
    encoding = value["content_encoding_class"]
    content_type = value["content_type_class"]
    count = value["callback_count"]
    at = STAGES.index(stage)
    callback_at = STAGES.index("callback_received")
    response_at = STAGES.index("token_response_started")
    http_at = STAGES.index("token_http_validated")
    no_http = all(field is None for field in (status, framing, encoding, content_type))
    valid_http = (status == "200" and framing in ("content_length", "chunked")
                  and encoding in ("absent", "identity")
                  and content_type in ("json", "json_utf8"))

    if stage == "acquisition_persisted":
        return False  # This schema is only for an unaccepted acquisition.
    if (at < callback_at and count == "one") or (at >= callback_at and count != "one"):
        return False
    if count == "invalid" and stage != "authorization_url_presented":
        return False
    if at < response_at and not no_http:
        return False
    if at >= http_at and not valid_http:
        return False
    if at == response_at:
        # Classifications are assigned together after header enumeration.
        if (framing is None) != (encoding is None) or (framing is None) != (content_type is None):
            return False
        if status != "200" and not all(field is None for field in (framing, encoding, content_type)):
            return False

    if reason == "local_failure":
        return True  # Coarse, but still subject to stage-derived impossibilities.
    if reason == "callback_timeout":
        return stage == "authorization_url_presented" and count == "zero" and no_http
    if reason in ("callback_count_invalid", "callback_transport_failure"):
        return stage == "authorization_url_presented" and count == "invalid" and no_http
    if reason in ("malformed_query", "state_mismatch", "issuer_mismatch", "scope_mismatch",
                  "missing_required_field", "duplicate_security_field", "provider_refusal"):
        allowed = ("callback_received", "callback_parsed") if reason == "malformed_query" else ("callback_parsed",)
        return stage in allowed and count == "one" and no_http
    if reason in ("dns_failure", "tcp_failure", "tls_failure", "connection_other"):
        return stage == "token_connection_started" and count == "one" and no_http
    if reason == "non_success_status":
        return (stage == "token_response_started" and count == "one"
                and status in ("other_2xx", "4xx", "5xx", "other")
                and framing is encoding is content_type is None)
    if reason == "framing_invalid":
        return stage == "token_response_started" and count == "one" and status == "200"
    if reason == "content_encoding_invalid":
        return (stage == "token_response_started" and count == "one" and status == "200"
                and framing in ("content_length", "chunked") and encoding == "other")
    if reason == "content_type_invalid":
        return (stage == "token_response_started" and count == "one" and status == "200"
                and framing in ("content_length", "chunked")
                and encoding in ("absent", "identity") and content_type == "other")
    if reason == "body_size_invalid":
        return (count == "one" and status == "200"
                and ((stage == "token_response_started" and framing == "content_length")
                     or (stage == "token_http_validated" and valid_http)))
    if reason == "body_incomplete":
        return stage == "token_http_validated" and count == "one" and valid_http
    if reason == "malformed_json":
        return stage == "token_body_complete" and count == "one" and valid_http
    if reason in ("required_field_missing", "semantic_scope_mismatch", "token_type_invalid",
                  "expires_in_invalid", "token_validation_failed"):
        return stage == "token_json_parsed" and count == "one" and valid_http
    if reason == "handoff_lifetime_invalid":
        return stage == "token_semantics_validated" and count == "one" and valid_http
    if reason == "persistence_failure":
        return stage == "acquisition_persistence_started" and count == "one" and valid_http
    return False


class AcquisitionDiagnostic:
    """Positive, closed-enum audit projection. Contains no request/provider values."""
    def __init__(self):
        self.stage = "oauth_intent_persisted"
        self.reason = "local_failure"
        self.status_class = None
        self.framing_class = None
        self.encoding_class = None
        self.content_type_class = None
        self.callback_count = "zero"

    def advance(self, stage):
        if stage not in STAGES or STAGES.index(stage) < STAGES.index(self.stage):
            raise AcquisitionFailure("local_failure")
        self.stage = stage

    def fail(self, reason):
        if reason not in REASONS:
            raise AcquisitionFailure("local_failure")
        self.reason = reason
        raise AcquisitionFailure(reason)

    def projection(self):
        value = {"schema": "sheets-phase4-acquisition-failure-v1", "status": "BLOCKED",
            "recovery": "stop-review-no-retry", "last_stage": self.stage,
            "reason": self.reason, "http_status_class": self.status_class,
            "framing_class": self.framing_class, "content_encoding_class": self.encoding_class,
            "content_type_class": self.content_type_class,
            "callback_count": self.callback_count}
        if not acquisition_failure_consistent(value):
            raise CredentialRefused()
        return value


def secret_safe(function):
    @functools.wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            pass
        # Outside the handler: no secret-bearing chained exception object.
        raise CredentialRefused()
    return call


@dataclass(frozen=True, slots=True, repr=False)
class ClientConfig:
    client_id: str
    client_secret: str
    project_id: str

    def __repr__(self):
        return "ClientConfig(<excluded>)"

    def public_projection(self):
        # Explicit reviewed public identity only; NEVER hash the source JSON.
        require(type(self.client_id) is str and re.fullmatch(
            r"[A-Za-z0-9_-]{1,256}\.apps\.googleusercontent\.com", self.client_id))
        label(self.project_id)
        require(type(self.client_secret) is str and 0 < len(self.client_secret) <= 4096
                and all(32 <= ord(c) < 127 for c in self.client_secret))
        return {"schema": "sheets-phase3-public-oauth-client-v1", "client_id": self.client_id,
                "project_id": self.project_id, "client_type": "installed",
                "auth_uri": AUTH_URI, "token_uri": TOKEN_URI, "scope": p1.SCOPE,
                "pkce": "S256", "redirect": "ipv4-loopback-random-port"}

    @property
    def public_hash(self):
        return sha256_hex(canonical_json_bytes(self.public_projection()))


@secret_safe
def load_client_config(path: Path, *, reviewed_public_hash: str) -> ClientConfig:
    """Explicit private file only. No environment/home/cloud SDK discovery."""
    from retry_semantics.study2.sheets_phase2_control import _private_fd
    digest(reviewed_public_hash)
    require(type(path) is Path or isinstance(path, Path))
    require(path.is_absolute() and ".." not in path.parts)
    require(not any(p.is_symlink() for p in (path, *path.parents)))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        _private_fd(fd)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            body = stream.read(16385)
        require(len(body) <= 16384)
    finally:
        os.close(fd)
    obj = strict_json(body)
    require(type(obj) is dict and set(obj) == {"installed"})
    value = obj["installed"]
    require(type(value) is dict and set(value) == {"client_id", "project_id", "auth_uri",
        "token_uri", "auth_provider_x509_cert_url", "client_secret", "redirect_uris"})
    require(value["auth_uri"] == AUTH_URI and value["token_uri"] == TOKEN_URI
            and value["auth_provider_x509_cert_url"] == "https://www.googleapis.com/oauth2/v1/certs"
            and value["redirect_uris"] == ["http://localhost"])
    config = ClientConfig(value["client_id"], value["client_secret"], value["project_id"])
    require(config.public_hash == reviewed_public_hash)
    return config


@dataclass(frozen=True, slots=True)
class AcquisitionMetadata:
    public_config_sha256: str
    account_alias: str
    exchange_started_at: float
    prepared_at: float
    expires_at: float
    clock_uncertainty_seconds: float

    def __post_init__(self):
        digest(self.public_config_sha256)
        label(self.account_alias)
        for v in (self.exchange_started_at, self.prepared_at, self.expires_at):
            frozen._number(v, positive=True)
        frozen._number(self.clock_uncertainty_seconds)
        require(self.exchange_started_at <= self.prepared_at < self.expires_at)

    def projection(self):
        self.__post_init__()
        return {"schema": "sheets-phase3-acquisition-metadata-v1", "engineering_only": True,
                "implementation": "stdlib-desktop-pkce-one-shot-v1",
                "python_version": platform.python_version(), "requested_scopes": [p1.SCOPE],
                "granted_scopes": [p1.SCOPE], "token_type": "Bearer",
                "public_config_sha256": self.public_config_sha256,
                "account_alias": self.account_alias, "exchange_started_at": self.exchange_started_at,
                "prepared_at": self.prepared_at, "expires_at": self.expires_at,
                "expiry_basis": "exchange-start-plus-expires-in",
                "clock_uncertainty_seconds": self.clock_uncertainty_seconds,
                "refresh_persistence": "none"}

    def transport_provenance(self):
        # Compatibility record only. Phase 1's evidence() hardcodes an absent
        # library; NEVER use it as acquisition evidence. projection() is truthful.
        return p1.CredentialProvenance(self.account_alias, self.public_config_sha256,
            platform.python_version(), self.exchange_started_at, self.prepared_at,
            self.expires_at, self.clock_uncertainty_seconds)


@secret_safe
def validate_token_response(body: bytes, config: ClientConfig, *, account_alias: str,
                            exchange_started_at: float, prepared_at: float,
                            clock_uncertainty_seconds: float):
    return _validate_token_response(body, config, account_alias=account_alias,
        exchange_started_at=exchange_started_at, prepared_at=prepared_at,
        clock_uncertainty_seconds=clock_uncertainty_seconds)


def _validate_token_response(body, config, *, account_alias, exchange_started_at,
                             prepared_at, clock_uncertainty_seconds, diagnostic=None):
    require(type(config) is ClientConfig and type(body) is bytes and len(body) <= 65536)
    try:
        value = strict_json(body)
    except Exception:
        raise AcquisitionFailure("malformed_json") from None
    if type(value) is not dict:
        raise AcquisitionFailure("malformed_json")
    if diagnostic is not None:
        diagnostic.advance("token_json_parsed")
    if not {"access_token", "expires_in", "scope", "token_type"} <= set(value):
        raise AcquisitionFailure("required_field_missing")
    if type(value["scope"]) is not str or value["scope"].split() != [p1.SCOPE]:
        raise AcquisitionFailure("semantic_scope_mismatch")
    if type(value["token_type"]) is not str or value["token_type"].lower() != "bearer":
        raise AcquisitionFailure("token_type_invalid")
    if type(value["access_token"]) is not str or not 0 < len(value["access_token"]) <= 8192:
        raise AcquisitionFailure("token_validation_failed")
    try:
        frozen._number(value["expires_in"], positive=True)
    except Exception:
        raise AcquisitionFailure("expires_in_invalid") from None
    metadata = AcquisitionMetadata(config.public_hash, account_alias, exchange_started_at,
        prepared_at, exchange_started_at + value["expires_in"], clock_uncertainty_seconds)
    try:
        token = frozen.prepare_token(value["access_token"], expires_at=metadata.expires_at,
            clock_uncertainty_seconds=clock_uncertainty_seconds)
    except Exception:
        raise AcquisitionFailure("token_validation_failed") from None
    if diagnostic is not None:
        diagnostic.advance("token_semantics_validated")
    # Refresh material is discarded with the local response; no refresh object
    # exists, and no OAuth body/value/hash crosses the export boundary.
    return token, metadata


def _response_body(response, diagnostic=None):
    """Preserve the frozen OAuth diagnostic stages around shared framing."""
    from retry_semantics.study2.sheets_http_framing import ResponseFramingError, read_json_body

    def classify(selected):
        if diagnostic is None:
            return
        length, transfer = selected.get("content-length"), selected.get("transfer-encoding")
        diagnostic.framing_class = ("conflicting" if length is not None and transfer is not None
            else "chunked" if transfer is not None and transfer.strip().lower() == "chunked"
            else "unsupported_transfer" if transfer is not None
            else "content_length" if length is not None else "neither")
        encoding = selected.get("content-encoding")
        diagnostic.encoding_class = ("absent" if encoding is None else "identity"
            if encoding.strip().lower() == "identity" else "other")
        kind = selected.get("content-type", "")
        diagnostic.content_type_class = ("json" if re.fullmatch(r"[ \t]*application/json[ \t]*", kind, re.I)
            else "json_utf8" if re.fullmatch(
                r'[ \t]*application/json[ \t]*;[ \t]*charset[ \t]*=[ \t]*(?:utf-8|"utf-8")[ \t]*', kind, re.I)
            else "other")
    try:
        body = read_json_body(response, 65536, min_body_bytes=1, on_headers=classify,
            before_read=(lambda: diagnostic.advance("token_http_validated")) if diagnostic else None)
    except ResponseFramingError as error:
        raise AcquisitionFailure(error.reason) from None
    if diagnostic is not None:
        diagnostic.advance("token_body_complete")
    return body


class DesktopPreparer:
    __slots__ = ("_config", "_verifier", "_state", "_used")

    @secret_safe
    def __init__(self, config: ClientConfig):
        require(type(config) is ClientConfig)
        config.public_projection()
        self._config = config
        self._verifier = secrets.token_urlsafe(64)
        self._state = secrets.token_urlsafe(32)
        self._used = False

    def __repr__(self):
        return "DesktopPreparer(<excluded>)"

    @secret_safe
    def authorization_url(self, redirect_uri: str):
        self._check_redirect(redirect_uri)
        require(not self._used)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(
            self._verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        return AUTH_URI + "?" + urlencode({"client_id": self._config.client_id,
            "redirect_uri": redirect_uri, "response_type": "code", "scope": p1.SCOPE,
            "code_challenge": challenge, "code_challenge_method": "S256", "state": self._state,
            "access_type": "online", "include_granted_scopes": "false", "prompt": "consent"})

    @staticmethod
    def _check_redirect(uri):
        require(type(uri) is str and re.fullmatch(r"http://127\.0\.0\.1:[1-9][0-9]{0,4}/", uri))
        require(0 < urlsplit(uri).port <= 65535)

    @secret_safe
    def _exchange(self, callback_url: str, redirect_uri: str, *, account_alias: str,
                  clock_uncertainty_seconds: float, timeout_seconds: float, diagnostic=None):
        try:
            return self._exchange_once(callback_url, redirect_uri, account_alias=account_alias,
                clock_uncertainty_seconds=clock_uncertainty_seconds, timeout_seconds=timeout_seconds,
                diagnostic=diagnostic)
        except AcquisitionFailure as failure:
            if diagnostic is not None:
                diagnostic.reason = failure.reason
            raise
        finally:
            if self._used:
                self._verifier = self._state = ""

    def _exchange_once(self, callback_url, redirect_uri, *, account_alias,
                       clock_uncertainty_seconds, timeout_seconds, diagnostic=None):
        require(not self._used)
        self._used = True  # Every callback/exchange failure terminates this session.
        self._check_redirect(redirect_uri)
        require(type(callback_url) is str and len(callback_url) <= 8192)
        parts = urlsplit(callback_url)
        require(not parts.fragment and parts.scheme + "://" + parts.netloc + parts.path == redirect_uri)
        if re.search(r"%(?![0-9A-Fa-f]{2})", parts.query):
            raise AcquisitionFailure("malformed_query")
        try:
            args = parse_qs(parts.query, strict_parsing=True, keep_blank_values=True)
        except ValueError:
            raise AcquisitionFailure("malformed_query") from None
        if diagnostic is not None:
            diagnostic.advance("callback_parsed")
        required = {"state", "iss"}
        if not required <= set(args) or ("code" not in args and "error" not in args):
            raise AcquisitionFailure("missing_required_field")
        if any(len(args[key]) != 1 for key in ("state", "iss", "code", "scope", "error") if key in args):
            raise AcquisitionFailure("duplicate_security_field")
        if "code" in args and "error" in args:
            raise AcquisitionFailure("malformed_query")
        if args["iss"][0] != CALLBACK_ISSUER:
            raise AcquisitionFailure("issuer_mismatch")
        if not hmac.compare_digest(args["state"][0], self._state):
            raise AcquisitionFailure("state_mismatch")
        if "error" in args:
            require(0 < len(args["error"][0]) <= 4096)
            raise AcquisitionFailure("provider_refusal")
        if "scope" not in args:
            raise AcquisitionFailure("missing_required_field")
        if args["scope"][0] != p1.SCOPE:
            raise AcquisitionFailure("scope_mismatch")
        require(0 < len(args["code"][0]) <= 4096)
        if diagnostic is not None:
            diagnostic.advance("callback_validated")
        from retry_semantics.study2.sheets_phase3_control import environment_gate
        environment_gate()
        frozen._number(timeout_seconds, positive=True)
        frozen._number(clock_uncertainty_seconds)
        label(account_alias)
        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        p1.validate_context(context)
        payload = urlencode({"client_id": self._config.client_id,
            "client_secret": self._config.client_secret, "code": args["code"][0],
            "code_verifier": self._verifier, "grant_type": "authorization_code",
            "redirect_uri": redirect_uri}).encode("ascii")
        if diagnostic is not None:
            diagnostic.advance("token_request_constructed")
        connection = http.client.HTTPSConnection("oauth2.googleapis.com", 443,
            timeout=timeout_seconds, context=context)
        connection.auto_open = connection.debuglevel = 0
        started = time.time()
        try:
            if diagnostic is not None:
                diagnostic.advance("token_connection_started")
            try:
                connection.connect()
            except socket.gaierror:
                raise AcquisitionFailure("dns_failure") from None
            except (ssl.SSLError, ssl.CertificateError):
                raise AcquisitionFailure("tls_failure") from None
            except (ConnectionRefusedError, TimeoutError):
                raise AcquisitionFailure("tcp_failure") from None
            except OSError:
                raise AcquisitionFailure("connection_other") from None
            try:
                connection.request("POST", "/token", payload, {"Content-Type":
                    "application/x-www-form-urlencoded", "Accept": "application/json",
                    "Accept-Encoding": "identity", "Connection": "close"})
                response = connection.getresponse()
            except (OSError, http.client.HTTPException):
                raise AcquisitionFailure("connection_other") from None
            if diagnostic is not None:
                diagnostic.advance("token_response_started")
                diagnostic.status_class = ("200" if response.status == 200 else
                    "other_2xx" if 200 <= response.status < 300 else
                    "4xx" if 400 <= response.status < 500 else "5xx" if 500 <= response.status < 600 else "other")
            if response.status != 200:
                raise AcquisitionFailure("non_success_status")
            body = _response_body(response, diagnostic)
            return _validate_token_response(body, self._config, account_alias=account_alias,
                exchange_started_at=started, prepared_at=time.time(),
                clock_uncertainty_seconds=clock_uncertainty_seconds, diagnostic=diagnostic)
        finally:
            connection.close()
            self._verifier = self._state = ""

    @secret_safe
    def acquire(self, *, operator_confirmation: str, present_url, account_alias: str,
                clock_uncertainty_seconds: float, consent_seconds: float,
                exchange_timeout_seconds: float, diagnostic=None):
        """Separately authorized later action; present_url is a manual UI callback.

        Caller must never log/store URLs or callback content. No automatic browser.
        One loopback callback and one token exchange, no refresh/retry. Acquisition
        has per-operation timeouts, not Phase 2's hard total read watchdog.
        """
        require(operator_confirmation == ACQUISITION_CONFIRMATION and not self._used)
        from retry_semantics.study2.sheets_phase3_control import environment_gate
        environment_gate()
        frozen._number(consent_seconds, positive=True)
        frozen._number(exchange_timeout_seconds, positive=True)
        frozen._number(clock_uncertainty_seconds)
        label(account_alias)
        received = []
        invalid = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def send_error(self, *args, **kwargs):
                invalid.append(True)
                # A fixed empty response; never interpolate a request line.
                self.send_response(400)
                self.send_header("Content-Length", "0")
                self.end_headers()
            def do_GET(self):
                if len(self.path) <= 8192 and self.path.startswith("/?"):
                    received.append(self.path)
                else:
                    invalid.append(True)
                self.send_response(200 if not invalid else 400)
                self.send_header("Content-Length", "0")
                self.end_headers()
        class LoopbackServer(http.server.HTTPServer):
            address_family = socket.AF_INET
            def get_request(self):
                sock, address = super().get_request()
                sock.settimeout(min(0.25, max(0.001, deadline - time.monotonic())))
                return sock, address
            def handle_error(self, request, client_address):
                invalid.append("transport")  # Never print a secret-bearing traceback.
        server = LoopbackServer(("127.0.0.1", 0), Handler)
        deadline = time.monotonic() + consent_seconds
        try:
            if diagnostic is not None:
                diagnostic.advance("listener_ready")
            redirect = f"http://127.0.0.1:{server.server_port}/"
            present_url(self.authorization_url(redirect))
            if diagnostic is not None:
                diagnostic.advance("authorization_url_presented")
            while not received and not invalid:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if diagnostic is not None:
                        diagnostic.fail("callback_timeout")
                    raise AcquisitionFailure("callback_timeout")
                server.timeout = min(0.25, remaining)
                server.handle_request()
            late = time.monotonic() > deadline
            if diagnostic is not None:
                diagnostic.callback_count = "invalid" if invalid or late else "one" if received else "zero"
            if invalid or len(received) != 1 or late:
                if diagnostic is not None:
                    diagnostic.fail("callback_transport_failure" if "transport" in invalid
                                    else "callback_count_invalid")
                raise AcquisitionFailure("callback_count_invalid")
            if diagnostic is not None:
                diagnostic.advance("callback_received")
            return self._exchange(redirect[:-1] + received[0], redirect,
                account_alias=account_alias, clock_uncertainty_seconds=clock_uncertainty_seconds,
                timeout_seconds=exchange_timeout_seconds, diagnostic=diagnostic)
        finally:
            self._used = True
            self._verifier = self._state = ""
            server.server_close()
