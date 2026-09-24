"""Prospective, single-use paper CREATE HTTPS adapter. No import-time action."""
from __future__ import annotations

import http.client
import signal
import ssl
import threading

from retry_semantics.study2 import sheets_live_go_phase1 as phase1
from retry_semantics.study2 import sheets_paper_scope_provisioning as paper
from retry_semantics.study2.sheets_http_framing import read_json_body


class PaperTransportRefused(Exception):
    def __init__(self):
        super().__init__("paper HTTPS transport refused")


TIMEOUT_SECONDS = 60
MAX_RESPONSE_BYTES = 131072


def _deadline(_signum, _frame):
    raise PaperTransportRefused()


def transport(host, port, method, target, body, prepared_bearer):
    """One explicit verified TLS connection and one exact-body send.

    A status already observed survives any subsequent framing/body/close failure.
    An empty body with status 200 is intentionally rejected by the frozen gate.
    This path is main-thread only so SIGALRM bounds DNS as well as socket stages.
    """
    if (host != paper.HOST or port != paper.PORT or method != paper.METHOD
            or target != paper.TARGET or type(body) is not bytes
            or type(prepared_bearer) is not str or not prepared_bearer
            or threading.current_thread() is not threading.main_thread()):
        raise PaperTransportRefused()
    connection = None
    status = None
    old_handler = signal.getsignal(signal.SIGALRM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    if old_timer != (0.0, 0.0):
        raise PaperTransportRefused()
    try:
        signal.signal(signal.SIGALRM, _deadline)
        signal.setitimer(signal.ITIMER_REAL, TIMEOUT_SECONDS)
        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        phase1.validate_context(context)
        connection = http.client.HTTPSConnection(host, port, timeout=TIMEOUT_SECONDS,
                                                 context=context)
        connection.auto_open = 0
        connection.debuglevel = 0
        connection.connect()
        connection.putrequest(method, target, skip_host=True, skip_accept_encoding=True)
        for name, value in (
            ("Host", host), ("Authorization", "Bearer " + prepared_bearer),
            ("Content-Type", "application/json; charset=utf-8"),
            ("Accept", "application/json"), ("Accept-Encoding", "identity"),
            ("Content-Length", str(len(body))), ("Connection", "close"),
        ):
            connection.putheader(name, value)
        connection.endheaders(body, encode_chunked=False)
        response = connection.getresponse()
        if type(response.status) is not int or not 100 <= response.status <= 599:
            raise PaperTransportRefused()
        status = response.status
        raw = read_json_body(response, MAX_RESPONSE_BYTES, min_body_bytes=1)
        return status, raw
    except Exception:
        if status is not None:
            return status, b""
        raise PaperTransportRefused() from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
