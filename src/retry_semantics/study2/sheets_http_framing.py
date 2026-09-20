"""Bounded HTTP/1.1 JSON response framing shared by OAuth and Sheets paths.

The standard library owns chunk decoding. This module never records response
headers or bodies and never decides whether a Sheets mutation was committed.
"""
from __future__ import annotations

import http.client
import re


class ResponseFramingError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def read_json_body(response, max_bytes: int, *, min_body_bytes: int = 0,
                   before_read=None, after_read=None, on_headers=None,
                   catch_transport_errors: bool = True) -> bytes:
    """Accept one canonical Content-Length or sole HTTP/1.1 chunked coding.

    Hooks permit caller-owned diagnostics and deadlines without moving their
    authorization, evidence, or mutation-uncertainty decisions into transport.
    """
    if (type(max_bytes) is not int or max_bytes < 0 or type(min_body_bytes) is not int
            or not 0 <= min_body_bytes <= max_bytes):
        raise ValueError("invalid response bounds")
    selected = {}
    for name, value in response.getheaders():
        key = name.lower()
        if key in ("content-length", "transfer-encoding", "content-type", "content-encoding"):
            if key in selected:
                raise ResponseFramingError("framing_invalid")
            selected[key] = value
    if on_headers is not None:
        on_headers(selected)

    length, transfer = selected.get("content-length"), selected.get("transfer-encoding")
    if length is not None and transfer is not None:
        raise ResponseFramingError("framing_invalid")
    if transfer is not None:
        if (not re.fullmatch(r"[ \t]*chunked[ \t]*", transfer, re.I)
                or response.chunked is not True
                or (hasattr(response, "version") and response.version != 11)):
            raise ResponseFramingError("framing_invalid")
        expected = None
    elif length is not None:
        if (not re.fullmatch(r"0|[1-9][0-9]*", length)
                or response.chunked is not False):
            raise ResponseFramingError("framing_invalid")
        # Avoid converting an arbitrarily long decimal before bounding it.
        if len(length) > len(str(max_bytes)) or int(length) > max_bytes:
            raise ResponseFramingError("body_size_invalid")
        expected = int(length)
        if expected < min_body_bytes or (hasattr(response, "length") and response.length != expected):
            raise ResponseFramingError("framing_invalid")
    else:
        raise ResponseFramingError("framing_invalid")

    if not re.fullmatch(r"[ \t]*identity[ \t]*",
                        selected.get("content-encoding", "identity"), re.I):
        raise ResponseFramingError("content_encoding_invalid")
    kind = selected.get("content-type", "")
    if not (re.fullmatch(r"[ \t]*application/json[ \t]*", kind, re.I)
            or re.fullmatch(
                r'[ \t]*application/json[ \t]*;[ \t]*charset[ \t]*=[ \t]*(?:utf-8|"utf-8")[ \t]*',
                kind, re.I)):
        raise ResponseFramingError("content_type_invalid")

    if before_read is not None:
        before_read()
    try:
        body = response.read((expected if expected is not None else max_bytes) + 1)
    except (http.client.IncompleteRead, ValueError):
        raise ResponseFramingError("body_incomplete") from None
    except (http.client.HTTPException, OSError):
        if not catch_transport_errors:
            raise
        raise ResponseFramingError("body_incomplete") from None
    if after_read is not None:
        after_read()
    if len(body) > max_bytes:
        raise ResponseFramingError("body_size_invalid")
    if ((expected is not None and len(body) != expected) or not response.isclosed()
            or (expected is not None and hasattr(response, "length") and response.length != 0)):
        raise ResponseFramingError("body_incomplete")
    if len(body) < min_body_bytes:
        raise ResponseFramingError("framing_invalid")
    return body
