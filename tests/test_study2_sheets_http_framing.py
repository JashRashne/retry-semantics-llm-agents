"""Offline raw HTTP/1.1 qualification of the shared JSON framing primitive."""
import http.client
import io

import pytest

from retry_semantics.study2.sheets_http_framing import ResponseFramingError, read_json_body


class ByteSocket:
    def __init__(self, data):
        self.data = data

    def makefile(self, mode):
        return io.BytesIO(self.data)


def parsed(body, headers, *, status=200, version="1.1"):
    raw = (f"HTTP/{version} {status} synthetic\r\n".encode() +
           b"".join(f"{name}: {value}\r\n".encode() for name, value in headers) +
           b"\r\n" + body)
    response = http.client.HTTPResponse(ByteSocket(raw))
    response.begin()
    return response


def chunked(body):
    return f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n"


@pytest.mark.parametrize("body,headers,expected", [
    (b"{}", [("Content-Length", "2"), ("Content-Type", "application/json")], None),
    (b"{}", [("Content-Length", "2"), ("Content-Type", "application/json"),
              ("Content-Encoding", " Identity ")], None),
    (chunked(b"{}"), [("Transfer-Encoding", "chunked"),
                       ("Content-Type", ' Application/JSON ; CHARSET = "UTF-8" ')], None),
    (chunked(b"{}"), [("Transfer-Encoding", "gzip, chunked"),
                       ("Content-Type", "application/json")], "framing_invalid"),
    (chunked(b"{}"), [("Transfer-Encoding", "chunked"), ("Transfer-Encoding", "chunked"),
                       ("Content-Type", "application/json")], "framing_invalid"),
    (chunked(b"{}"), [("Transfer-Encoding", "chunked"), ("Content-Length", "2"),
                       ("Content-Type", "application/json")], "framing_invalid"),
    (b"{}", [("Content-Length", "2"), ("Content-Length", "2"),
              ("Content-Type", "application/json")], "framing_invalid"),
    (b"{}", [("Content-Type", "application/json")], "framing_invalid"),
    (b"{}", [("Content-Length", "02"), ("Content-Type", "application/json")], "framing_invalid"),
    (b"", [("Content-Length", "0"), ("Content-Type", "application/json")], None),
    (b"{}", [("Content-Length", "3"), ("Content-Type", "application/json")], "body_incomplete"),
    (b"1\r\nx\r\n", [("Transfer-Encoding", "chunked"),
                            ("Content-Type", "application/json")], "body_incomplete"),
    (b"z\r\n", [("Transfer-Encoding", "chunked"),
                  ("Content-Type", "application/json")], "body_incomplete"),
    (chunked(b"abc"), [("Transfer-Encoding", "chunked"),
                         ("Content-Type", "application/json")], "body_size_invalid"),
    (b"abc", [("Content-Length", "3"), ("Content-Type", "application/json")], "body_size_invalid"),
    (b"{}", [("Content-Length", "2"), ("Content-Type", "text/html")], "content_type_invalid"),
    (b"{}", [("Content-Length", "2"), ("Content-Type", "application/problem+json")],
     "content_type_invalid"),
    (b"{}", [("Content-Length", "2"), ("Content-Type", "application/json"),
              ("Content-Encoding", "gzip")], "content_encoding_invalid"),
])
def test_raw_framing(body, headers, expected):
    response = parsed(body, headers)
    limit = 3 if expected == "body_incomplete" else 2
    if expected is None:
        assert read_json_body(response, limit) == (b"" if body == b"" else b"{}")
        assert response.isclosed()
    else:
        with pytest.raises(ResponseFramingError) as failure:
            read_json_body(response, limit)
        assert failure.value.reason == expected


def test_chunked_requires_http_11():
    response = parsed(chunked(b"{}"), [('Transfer-Encoding', 'chunked'),
        ('Content-Type', 'application/json')], version='1.0')
    with pytest.raises(ResponseFramingError) as failure:
        read_json_body(response, 2)
    assert failure.value.reason == 'framing_invalid'


@pytest.mark.parametrize('headers,wire_body,accepted', [
    ([('Content-Length', '0'), ('Content-Type', 'application/json')], b'', False),
    ([('Content-Length', '1'), ('Content-Type', 'application/json')], b'x', True),
    ([('Transfer-Encoding', 'chunked'), ('Content-Type', 'application/json')], chunked(b''), False),
    ([('Transfer-Encoding', 'chunked'), ('Content-Type', 'application/json')], chunked(b'x'), True),
])
def test_minimum_decoded_body_for_both_framings(headers, wire_body, accepted):
    response = parsed(wire_body, headers)
    if accepted:
        assert read_json_body(response, 1, min_body_bytes=1) == b'x'
    else:
        with pytest.raises(ResponseFramingError) as failure:
            read_json_body(response, 1, min_body_bytes=1)
        assert failure.value.reason == 'framing_invalid'


@pytest.mark.parametrize('minimum', [-1, True, 1.0, 2])
def test_invalid_minimum_rejected_before_response_read(minimum):
    response = parsed(b'x', [('Content-Length', '1'), ('Content-Type', 'application/json')])
    with pytest.raises(ValueError, match='invalid response bounds'):
        read_json_body(response, 1, min_body_bytes=minimum)
