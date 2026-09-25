"""Prospective one-shot paper HTTPS transport; import has no network effect.

No OAuth, redirects, retries, token refresh, or implicit mutation. The
readiness command invokes GET only; POST requires a future collection caller's
explicit `allow_mutation=True`. Status visibility survives later body failure.
"""

from __future__ import annotations

import http.client
import signal
import ssl
import threading
from dataclasses import dataclass

from retry_semantics.study2.sheets_offline import FrozenMutation
from retry_semantics.study2.sheets_paper_adapter import DispatchFacts

HOST = "sheets.googleapis.com"


class PaperTransportDeadline(TimeoutError):
    """Whole-request deadline, including DNS, connect, TLS, send, and body."""


def _deadline(_signum, _frame):
    raise PaperTransportDeadline()


@dataclass(frozen=True, slots=True)
class PaperHTTPResult:
    facts: DispatchFacts
    body: bytes
    transport_error: str | None


def one_shot_request(*, method: str, target: str, body: bytes,
                     bearer: str, spreadsheet_id: str, max_response_bytes: int,
                     application_headers: tuple[tuple[str, str], ...] = (),
                     timeout_seconds: int = 30,
                     allow_mutation: bool = False) -> PaperHTTPResult:
    if (method not in ("GET", "POST") or (method == "POST" and not allow_mutation)
            or type(target) is not str
            or not target.startswith(f"/v4/spreadsheets/{spreadsheet_id}")
            or type(body) is not bytes or (method == "GET" and body)
            or type(bearer) is not str or not bearer
            or type(max_response_bytes) is not int or max_response_bytes < 1
            or type(timeout_seconds) is not int or not 0 < timeout_seconds <= 60):
        raise ValueError("invalid or unauthorized paper transport request")
    if method == "POST" and application_headers != (
        ("content-type", "application/json; charset=utf-8"),
        ("accept", "application/json")):
        raise ValueError("mutation application headers changed")
    if method == "GET" and application_headers:
        raise ValueError("unexpected GET application headers")
    if threading.current_thread() is not threading.main_thread():
        raise ValueError("whole-request deadline requires main thread")
    old_handler = signal.getsignal(signal.SIGALRM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    if old_timer != (0.0, 0.0):
        raise ValueError("existing process deadline cannot be replaced")
    signal.signal(signal.SIGALRM, _deadline)
    connection = None
    initiated = False
    sent = False
    status = None
    response_body = b""
    try:
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        connection = http.client.HTTPSConnection(
            HOST, 443, timeout=timeout_seconds,
            context=ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH))
        connection.connect()
        connection.putrequest(method, target, skip_host=True, skip_accept_encoding=True)
        for name, value in (("Host", HOST), ("Authorization", "Bearer " + bearer),
                            ("Accept-Encoding", "identity"), ("Connection", "close")):
            connection.putheader(name, value)
        if method == "GET":
            connection.putheader("Accept", "application/json")
        else:
            for name, value in application_headers:
                connection.putheader(name, value)
            connection.putheader("Content-Length", str(len(body)))
        # http.client buffers the request line and headers until endheaders.
        # Only this boundary can begin transmission of request bytes.
        initiated = True
        connection.endheaders(body if method == "POST" else None,
                              encode_chunked=False)
        sent = True
        response = connection.getresponse()
        status = response.status
        if type(status) is not int or not 100 <= status <= 599:
            raise ValueError("invalid HTTP status")
        response_body = response.read(max_response_bytes + 1)
        if len(response_body) > max_response_bytes:
            return PaperHTTPResult(DispatchFacts(True, True, status), b"", "response_cap_exceeded")
        return PaperHTTPResult(DispatchFacts(True, True, status), response_body, None)
    except Exception as exc:
        # Local send completion is never a remote-receipt or commit claim.
        return PaperHTTPResult(DispatchFacts(initiated, sent, status),
                               response_body, type(exc).__name__)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def send_frozen_mutation(request: FrozenMutation, *, bearer: str,
                         spreadsheet_id: str, allow_live_collection: bool) -> PaperHTTPResult:
    if (type(request) is not FrozenMutation or request.method != "POST"
            or request.uri != f"/v4/spreadsheets/{spreadsheet_id}:batchUpdate"
            or allow_live_collection is not True):
        raise ValueError("mutation is not explicitly authorized")
    return one_shot_request(
        method=request.method, target=request.uri, body=request.body,
        bearer=bearer, spreadsheet_id=spreadsheet_id,
        application_headers=request.headers, max_response_bytes=131072,
        timeout_seconds=30, allow_mutation=True)
