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
import ssl
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_live_go_phase1 as p1
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2.sheets_phase2_control import require, strict_json, label, digest

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
ACQUISITION_CONFIRMATION = "EXPLICIT_OPERATOR_OAUTH_ACQUISITION"


class CredentialRefused(ValueError):
    def __init__(self):
        super().__init__()


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
    require(type(config) is ClientConfig and type(body) is bytes and len(body) <= 65536)
    value = strict_json(body)
    require(type(value) is dict and {"access_token", "expires_in", "scope", "token_type"} <= set(value)
            and set(value) <= {"access_token", "expires_in", "scope", "token_type", "refresh_token"})
    require(type(value["scope"]) is str and value["scope"].split() == [p1.SCOPE]
            and value["token_type"] == "Bearer")
    require(type(value["access_token"]) is str and 0 < len(value["access_token"]) <= 8192)
    frozen._number(value["expires_in"], positive=True)
    metadata = AcquisitionMetadata(config.public_hash, account_alias, exchange_started_at,
        prepared_at, exchange_started_at + value["expires_in"], clock_uncertainty_seconds)
    token = frozen.prepare_token(value["access_token"], expires_at=metadata.expires_at,
        clock_uncertainty_seconds=clock_uncertainty_seconds)
    # Refresh material is discarded with the local response; no refresh object
    # exists, and no OAuth body/value/hash crosses the export boundary.
    return token, metadata


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
                  clock_uncertainty_seconds: float, timeout_seconds: float):
        try:
            return self._exchange_once(callback_url, redirect_uri, account_alias=account_alias,
                clock_uncertainty_seconds=clock_uncertainty_seconds, timeout_seconds=timeout_seconds)
        finally:
            if self._used:
                self._verifier = self._state = ""

    def _exchange_once(self, callback_url, redirect_uri, *, account_alias,
                       clock_uncertainty_seconds, timeout_seconds):
        require(not self._used)
        self._used = True  # Every callback/exchange failure terminates this session.
        self._check_redirect(redirect_uri)
        require(type(callback_url) is str and len(callback_url) <= 8192)
        parts = urlsplit(callback_url)
        require(not parts.fragment and parts.scheme + "://" + parts.netloc + parts.path == redirect_uri)
        args = parse_qs(parts.query, strict_parsing=True, keep_blank_values=True)
        require(set(args) == {"code", "state"} and all(len(v) == 1 for v in args.values()))
        require(hmac.compare_digest(args["state"][0], self._state)
                and 0 < len(args["code"][0]) <= 4096)
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
        connection = http.client.HTTPSConnection("oauth2.googleapis.com", 443,
            timeout=timeout_seconds, context=context)
        connection.auto_open = connection.debuglevel = 0
        started = time.time()
        try:
            connection.connect()
            connection.request("POST", "/token", payload, {"Content-Type":
                "application/x-www-form-urlencoded", "Accept": "application/json",
                "Accept-Encoding": "identity", "Connection": "close"})
            response = connection.getresponse()
            require(response.status == 200 and not response.chunked)
            headers = response.getheaders()
            lengths = [v for k, v in headers if k.lower() == "content-length"]
            types = [v for k, v in headers if k.lower() == "content-type"]
            require(len(lengths) == 1 and re.fullmatch(r"[1-9][0-9]{0,4}", lengths[0])
                    and int(lengths[0]) <= 65536 and len(types) == 1
                    and types[0].lower() in ("application/json", "application/json; charset=utf-8")
                    and not any(k.lower() in ("transfer-encoding", "content-encoding") for k, _ in headers))
            body = response.read(int(lengths[0]) + 1)
            require(len(body) == int(lengths[0]) and response.isclosed())
            return validate_token_response(body, self._config, account_alias=account_alias,
                exchange_started_at=started, prepared_at=time.time(),
                clock_uncertainty_seconds=clock_uncertainty_seconds)
        finally:
            connection.close()
            self._verifier = self._state = ""

    @secret_safe
    def acquire(self, *, operator_confirmation: str, present_url, account_alias: str,
                clock_uncertainty_seconds: float, consent_seconds: float,
                exchange_timeout_seconds: float):
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
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                if len(self.path) <= 8192:
                    received.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
        class LoopbackServer(http.server.HTTPServer):
            def get_request(self):
                sock, address = super().get_request()
                sock.settimeout(consent_seconds)
                return sock, address
            def handle_error(self, request, client_address):
                pass  # Stdlib's default prints a secret-bearing traceback.
        server = LoopbackServer(("127.0.0.1", 0), Handler)
        server.timeout = consent_seconds
        try:
            redirect = f"http://127.0.0.1:{server.server_port}/"
            present_url(self.authorization_url(redirect))
            server.handle_request()
            require(len(received) == 1)
            return self._exchange(redirect[:-1] + received[0], redirect,
                account_alias=account_alias, clock_uncertainty_seconds=clock_uncertainty_seconds,
                timeout_seconds=exchange_timeout_seconds)
        finally:
            self._used = True
            self._verifier = self._state = ""
            server.server_close()
