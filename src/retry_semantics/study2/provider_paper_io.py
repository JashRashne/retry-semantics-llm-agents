"""One-shot paper HTTP and durable, credential-free operation evidence.

Nothing here performs I/O until explicitly called by an authorized collector.
The POSIX alarm enforces the full request deadline, including DNS and body read.
"""

from __future__ import annotations

import base64
import os
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import httpx

from retry_semantics.serialization import canonical_json_bytes, sha256_hex


class PaperIOError(ValueError):
    """Unsafe request, deadline, or evidence failure."""


@dataclass(frozen=True, slots=True)
class PaperRequest:
    method: str
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def __post_init__(self) -> None:
        parsed = urlsplit(self.url)
        allowed = ({"accept", "x-github-api-version", "content-type", "user-agent"}
                   if parsed.hostname == "api.github.com"
                   else {"content-type", "accept"} if parsed.hostname == "sheets.googleapis.com"
                   else {"content-type"})
        if (self.method not in ("GET", "POST") or parsed.scheme != "https"
                or parsed.hostname not in ("api.github.com", "api.razorpay.com", "sheets.googleapis.com")
                or parsed.port is not None or parsed.username or parsed.password
                or parsed.fragment or type(self.body) is not bytes
                or len(self.url) > 2048 or len(self.body) > 1_000_000
                or (self.method == "GET" and self.body)
                or any(type(k) is not str or k.lower() not in allowed
                       or type(v) is not str or any(ord(c) < 32 for c in v)
                       or len(k) + len(v) > 8192
                       for k, v in self.headers)):
            raise PaperIOError("unsafe paper request")

    @property
    def identity_sha256(self) -> str:
        return sha256_hex(canonical_json_bytes({
            "method": self.method, "url": self.url,
            "headers": [list(item) for item in self.headers],
            "body_hex": self.body.hex(),
        }))


@dataclass(frozen=True, slots=True)
class PaperTransportResult:
    status: int | None
    headers: tuple[tuple[str, str], ...]
    body: bytes
    error: str | None
    dispatch_initiated: bool
    local_send_completed: bool | None
    response_received: bool
    started_monotonic: float
    ended_monotonic: float


def _public_headers(headers: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    allowed = {"content-type", "link", "x-github-api-version-selected",
               "retry-after", "date", "content-length", "x-request-id",
               "x-razorpay-request-id"}
    return tuple((k, v) for k, v in headers
                 if k.lower() in allowed or k.lower().startswith("x-ratelimit-"))


def _deadline_handler(_signum: int, _frame: object) -> None:
    raise TimeoutError("absolute paper request deadline")


def one_shot_http(request: PaperRequest, *, credential: str,
                  deadline_seconds: float = 30.0,
                  max_body_bytes: int = 4_000_000,
                  transport: httpx.BaseTransport | None = None) -> PaperTransportResult:
    """Exactly one HTTP send; never follow redirects or retry any status/error."""
    if (type(request) is not PaperRequest or type(credential) is not str
            or not credential or type(deadline_seconds) not in (int, float)
            or not 0 < deadline_seconds <= 30 or max_body_bytes < 1
            or threading.current_thread() is not threading.main_thread()):
        raise PaperIOError("invalid one-shot transport configuration")
    host = urlsplit(request.url).hostname
    auth = ("Bearer " + credential if host in ("api.github.com", "sheets.googleapis.com") else
            "Basic " + base64.b64encode(credential.encode("utf-8")).decode("ascii"))
    headers = dict(request.headers)
    headers["Authorization"] = auth
    started = time.monotonic()
    old_handler = signal.getsignal(signal.SIGALRM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    if old_timer[0] or old_timer[1]:
        raise PaperIOError("another absolute deadline is active")
    signal.signal(signal.SIGALRM, _deadline_handler)
    signal.setitimer(signal.ITIMER_REAL, deadline_seconds)
    dispatched = False
    seen_status: int | None = None
    seen_headers: tuple[tuple[str, str], ...] = ()
    partial_body = bytearray()
    try:
        with httpx.Client(timeout=httpx.Timeout(deadline_seconds),
                          follow_redirects=False, trust_env=False,
                          transport=(httpx.HTTPTransport(retries=0)
                                     if transport is None else transport)) as client:
            outbound = client.build_request(request.method, request.url,
                                            headers=headers, content=request.body)
            dispatched = True
            response = client.send(outbound, stream=True)
            try:
                seen_status = response.status_code
                seen_headers = _public_headers(tuple(response.headers.items()))
                if sum(len(k) + len(v) for k, v in response.headers.items()) > 65_536:
                    raise PaperIOError("response headers cap exceeded")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_body_bytes:
                        raise PaperIOError("response body cap exceeded")
                    chunks.append(chunk)
                    partial_body.extend(chunk)
                if time.monotonic() - started > deadline_seconds:
                    raise TimeoutError("absolute paper request deadline")
                return PaperTransportResult(
                    seen_status, seen_headers,
                    b"".join(chunks), None, True, True, True,
                    started, time.monotonic())
            finally:
                response.close()
    except (httpx.HTTPError, TimeoutError, PaperIOError) as exc:
        return PaperTransportResult(seen_status, seen_headers,
                                    bytes(partial_body), type(exc).__name__,
                                    dispatched, True if seen_status is not None else None,
                                    seen_status is not None,
                                    started, time.monotonic())
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


class DurablePaperEvidence:
    """Exclusive intent then result files; failed result write never resends."""

    def __init__(self, directory: Path, *, provider: str, family_id: str,
                 arm_id: str, manifest_sha256: str,
                 runtime_sha256: dict[str, str]):
        if provider not in ("github", "razorpay", "sheets"):
            raise PaperIOError("unknown provider")
        self.directory = directory
        self.provider = provider
        self.family_id = family_id
        self.arm_id = arm_id
        self.manifest_sha256 = manifest_sha256
        self.runtime_sha256 = runtime_sha256
        self.index = 0
        directory.mkdir(parents=True, exist_ok=True)

    def _write(self, name: str, value: dict) -> None:
        raw = canonical_json_bytes(value)
        path = self.directory / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            dirfd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        except Exception:
            raise

    def record(self, operation: str, request: PaperRequest,
               send: Callable[[PaperRequest], PaperTransportResult]) -> PaperTransportResult:
        if type(request) is not PaperRequest:
            raise PaperIOError("invalid paper request")
        index = self.index
        self.index += 1
        prefix = f"{index:05d}"
        common = {
            "schema": "provider-paper-operation-v1", "provider": self.provider,
            "family_id": self.family_id, "arm_id": self.arm_id,
            "operation_number": index, "operation_type": operation,
            "method": request.method, "target": request.url,
            "application_headers": [list(x) for x in request.headers],
            "body_hex": request.body.hex(),
            "body_sha256": sha256_hex(request.body),
            "request_identity_sha256": request.identity_sha256,
            "manifest_sha256": self.manifest_sha256,
            "runtime_sha256": self.runtime_sha256,
        }
        self._write(prefix + ".intent.json", common)
        result = send(request)
        if type(result) is not PaperTransportResult:
            raise PaperIOError("transport did not provide dispatch evidence")
        safe_headers = _public_headers(result.headers)
        self._write(prefix + ".result.json", {
            **common, "dispatch_initiated": result.dispatch_initiated,
            "local_send_completed": result.local_send_completed,
            "response_received": result.response_received,
            "http_status": result.status,
            "response_headers": [list(x) for x in safe_headers],
            "response_body_hex": result.body.hex(),
            "response_body_sha256": sha256_hex(result.body),
            "transport_error": result.error,
            "started_monotonic": result.started_monotonic,
            "ended_monotonic": result.ended_monotonic,
        })
        return result

    def event(self, name: str, value: dict) -> None:
        if (type(name) is not str or not name or
                any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
                    for c in name)):
            raise PaperIOError("unsafe evidence event name")
        self._write(name + ".json", value)
