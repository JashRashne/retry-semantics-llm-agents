"""Synthetic OAuth qualification: actual loopback sockets and stdlib HTTP parsing."""
import http.client
import http.server
import io
import json
import os
import socket
import ssl
import stat
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from retry_semantics.study2 import sheets_live_go_phase1 as p1
from retry_semantics.study2 import sheets_phase3_credentials as oauth
from retry_semantics.study2 import sheets_phase3_control as p3
from retry_semantics.study2 import sheets_phase4_control as p4

TOKEN = "A" * 2048 + ".synthetic"
CLIENT = oauth.ClientConfig("123-abc.apps.googleusercontent.com", "synthetic-client-secret", "synthetic_project")


def received_diagnostic():
    diagnostic = oauth.AcquisitionDiagnostic()
    diagnostic.callback_count = "one"
    diagnostic.advance("callback_received")
    return diagnostic


def assert_valid_failure(diagnostic):
    value = diagnostic.projection()
    assert p4.validate_acquisition_failure(value) == value
    assert TOKEN not in json.dumps(value)


def token_body(**changes):
    return json.dumps({"access_token": TOKEN, "expires_in": 3600, "scope": p1.SCOPE,
                       "token_type": "Bearer", **changes}).encode()


def token_body_without_scope():
    value = json.loads(token_body())
    del value["scope"]
    return json.dumps(value).encode()


class ByteSocket:
    def __init__(self, raw):
        self.raw = raw

    def makefile(self, mode):
        return io.BytesIO(self.raw)


def wire(body=None, *, headers=None, status=200):
    if body is None:
        body = token_body()
    if headers is None:
        headers = [("Content-Length", str(len(body))), ("Content-Type", "application/json")]
    return (f"HTTP/1.1 {status} synthetic\r\n".encode() +
            b"".join(f"{k}: {v}\r\n".encode() for k, v in headers) + b"\r\n" + body)


def parsed(raw):
    response = http.client.HTTPResponse(ByteSocket(raw))
    response.begin()
    return response


def chunked(body):
    return f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n"


@pytest.mark.parametrize("raw,accepted,reason", [
    (wire(), True, None),
    (wire(headers=[("Transfer-Encoding", "chunked"), ("Content-Type", "application/json")],
          body=chunked(token_body())), True, None),
    (wire(headers=[("Transfer-Encoding", "chunked"), ("Content-Length", "12"),
                   ("Content-Type", "application/json")], body=chunked(token_body())), False, "framing_invalid"),
    (wire(headers=[("Content-Length", "20"), ("Content-Length", "20"),
                   ("Content-Type", "application/json")]), False, "framing_invalid"),
    (wire(headers=[("Content-Type", "application/json")]), False, "framing_invalid"),
    (wire(headers=[("Transfer-Encoding", "gzip"), ("Content-Type", "application/json")]), False, "framing_invalid"),
    (wire(headers=[("Transfer-Encoding", "chunked"), ("Content-Type", "application/json")],
          body=b"f\r\nshort\r\n"), False, "body_incomplete"),
    (wire(headers=[("Transfer-Encoding", "chunked"), ("Content-Type", "application/json")],
          body=chunked(b"x" * 65537)), False, "body_size_invalid"),
    (wire(headers=[("Content-Length", "9999"), ("Content-Type", "application/json")],
          body=b"{}"), False, "body_incomplete"),
    (wire(headers=[("Content-Length", str(len(token_body()))), ("Content-Type", "application/json"),
                   ("Content-Encoding", "gzip")]), False, "content_encoding_invalid"),
    (wire(headers=[("Content-Length", str(len(token_body()))), ("Content-Type", "text/html")]),
     False, "content_type_invalid"),
    (wire(status=400), False, "non_success_status"),
])
def test_raw_http_token_framing(raw, accepted, reason):
    response = parsed(raw)
    diagnostic = oauth.AcquisitionDiagnostic()
    diagnostic.advance("token_response_started")
    if response.status != 200:
        with pytest.raises(oauth.AcquisitionFailure):
            diagnostic.fail("non_success_status")
    elif accepted:
        assert oauth._response_body(response, diagnostic) == token_body()
        assert response.isclosed()
    else:
        with pytest.raises(oauth.AcquisitionFailure) as failure:
            oauth._response_body(response, diagnostic)
        assert failure.value.reason == reason


@pytest.mark.parametrize("headers,body,framing_class,accepted", [
    ([("Content-Length", str(len(token_body()))), ("Content-Type", "application/json")],
     token_body(), "content_length", True),
    ([("Transfer-Encoding", "chunked"), ("Content-Type", "application/json")],
     chunked(token_body()), "chunked", True),
    ([("Transfer-Encoding", "gzip"), ("Content-Type", "application/json")],
     token_body(), "unsupported_transfer", False),
    ([("Transfer-Encoding", "gzip, chunked"), ("Content-Type", "application/json")],
     chunked(token_body()), "unsupported_transfer", False),
    ([("Content-Length", "5"), ("Transfer-Encoding", "chunked"),
      ("Content-Type", "application/json")], b"0\r\n\r\n", "conflicting", False),
    ([("Content-Type", "application/json")], token_body(), "neither", False),
], ids=["content_length", "chunked", "gzip", "gzip_then_chunked", "conflicting", "neither"])
def test_framing_diagnostic_classes(headers, body, framing_class, accepted):
    diagnostic = received_diagnostic()
    diagnostic.advance("token_response_started")
    diagnostic.status_class = "200"
    response = parsed(wire(body, headers=headers))
    if accepted:
        assert oauth._response_body(response, diagnostic) == token_body()
        assert diagnostic.stage == "token_body_complete"
    else:
        with pytest.raises(oauth.AcquisitionFailure) as failure:
            oauth._response_body(response, diagnostic)
        assert failure.value.reason == "framing_invalid"
        diagnostic.reason = failure.value.reason
        assert_valid_failure(diagnostic)
    assert diagnostic.framing_class == framing_class


def test_duplicate_framing_header_has_no_invented_class():
    diagnostic = received_diagnostic()
    diagnostic.advance("token_response_started")
    diagnostic.status_class = "200"
    response = parsed(wire(headers=[("Content-Length", "5"), ("Content-Length", "5"),
                                    ("Content-Type", "application/json")]))
    with pytest.raises(oauth.AcquisitionFailure) as failure:
        oauth._response_body(response, diagnostic)
    assert failure.value.reason == "framing_invalid"
    assert diagnostic.framing_class is None
    diagnostic.reason = failure.value.reason
    assert_valid_failure(diagnostic)


@pytest.mark.parametrize("kind", ["application/json", "APPLICATION/JSON ; CHARSET = UTF-8",
                                   'application/json; charset="utf-8"'])
def test_json_media_type_variants(kind):
    body = token_body()
    response = parsed(wire(body, headers=[("Content-Length", str(len(body))),
                                               ("Content-Type", kind), ("Content-Encoding", "identity")]))
    assert oauth._response_body(response) == body


@pytest.mark.parametrize("changes,accepted", [
    ({}, True), ({"refresh_token": "secret-refresh"}, True),
    ({"refresh_token_expires_in": 1000}, True), ({"id_token": "secret-id"}, True),
    ({"new_provider_member": "secret-unknown"}, True),
    ({"expires_in": 3600}, True), ({"expires_in": "3600"}, False),
    ({"expires_in": 3600.5}, True), ({"token_type": "bEaReR"}, True),
    ({"scope": ""}, False), ({"scope": "changed"}, False),
])
def test_golden_token_semantics(changes, accepted):
    body = token_body(**changes)
    if accepted:
        token, metadata = oauth.validate_token_response(body, CLIENT, account_alias="synthetic_account",
            exchange_started_at=1000, prepared_at=1001, clock_uncertainty_seconds=1)
        assert token.value == TOKEN and metadata.projection()["granted_scopes"] == [p1.SCOPE]
        assert "secret" not in json.dumps(metadata.projection())
    else:
        with pytest.raises(oauth.CredentialRefused):
            oauth.validate_token_response(body, CLIENT, account_alias="synthetic_account",
                exchange_started_at=1000, prepared_at=1001, clock_uncertainty_seconds=1)


def test_pretty_json_and_missing_scope():
    value = json.loads(token_body())
    pretty = json.dumps(value, indent=2).encode()
    token, _ = oauth.validate_token_response(pretty, CLIENT, account_alias="synthetic_account",
        exchange_started_at=1000, prepared_at=1001, clock_uncertainty_seconds=1)
    assert token.value == TOKEN
    del value["scope"]
    with pytest.raises(oauth.CredentialRefused):
        oauth.validate_token_response(json.dumps(value).encode(), CLIENT,
            account_alias="synthetic_account", exchange_started_at=1000, prepared_at=1001,
            clock_uncertainty_seconds=1)


@pytest.mark.parametrize("body", [b"{", b"{}", b"x" * 65537])
def test_malformed_missing_oversize_token(body):
    with pytest.raises(oauth.CredentialRefused):
        oauth.validate_token_response(body, CLIENT, account_alias="synthetic_account",
            exchange_started_at=1000, prepared_at=1001, clock_uncertainty_seconds=1)


def test_unknown_callback_and_token_members_are_not_projected(monkeypatch):
    calls = fake_token_connection(monkeypatch, wire(token_body(
        refresh_token="secret-refresh", id_token="secret-id", new_member="secret-unknown")))
    session = oauth.DesktopPreparer(CLIENT)
    uri = "http://127.0.0.1:12345/"
    diagnostic = received_diagnostic()
    callback = uri[:-1] + callback_path(oauth.AUTH_URI + "?state=" + session._state,
                                   extra="&future_field=secret-callback")
    token, metadata = session._exchange(callback, uri, account_alias="synthetic_account",
        clock_uncertainty_seconds=1, timeout_seconds=2, diagnostic=diagnostic)
    assert token.value == TOKEN and calls.count("request") == 1
    assert diagnostic.status_class == "200"
    evidence = json.dumps(metadata.projection()) + json.dumps(diagnostic.projection())
    assert all(secret not in evidence for secret in (
        "secret-refresh", "secret-id", "secret-unknown", "secret-callback", TOKEN))


@pytest.mark.parametrize("extra,reason", [
    ("&state=duplicate", "duplicate_security_field"),
    ("&iss=duplicate", "duplicate_security_field"),
    ("&scope=duplicate", "duplicate_security_field"),
    ("&code=duplicate", "duplicate_security_field"),
])
def test_security_callback_duplicates_still_refused(monkeypatch, extra, reason):
    calls = fake_token_connection(monkeypatch)
    session = oauth.DesktopPreparer(CLIENT)
    uri = "http://127.0.0.1:12345/"
    diagnostic = received_diagnostic()
    callback = uri[:-1] + callback_path(oauth.AUTH_URI + "?state=" + session._state, extra=extra)
    with pytest.raises(oauth.CredentialRefused):
        session._exchange(callback, uri, account_alias="synthetic_account",
            clock_uncertainty_seconds=1, timeout_seconds=2, diagnostic=diagnostic)
    assert diagnostic.reason == reason and calls == []
    assert_valid_failure(diagnostic)


@pytest.mark.parametrize("kind,stage,reason", [
    ("malformed", "callback_received", "malformed_query"),
    ("state", "callback_parsed", "state_mismatch"),
    ("issuer", "callback_parsed", "issuer_mismatch"),
    ("scope", "callback_parsed", "scope_mismatch"),
    ("missing", "callback_parsed", "missing_required_field"),
    ("provider_error", "callback_parsed", "provider_refusal"),
])
def test_actual_callback_failure_shapes(monkeypatch, kind, stage, reason):
    calls = fake_token_connection(monkeypatch)
    session = oauth.DesktopPreparer(CLIENT)
    diagnostic = received_diagnostic()
    uri = "http://127.0.0.1:12345/"
    query = {"code": "synthetic-code", "state": session._state,
             "iss": oauth.CALLBACK_ISSUER, "scope": p1.SCOPE}
    if kind == "state":
        query["state"] = "wrong"
    elif kind == "issuer":
        query["iss"] = "wrong"
    elif kind == "scope":
        query["scope"] = "wrong"
    elif kind == "missing":
        del query["scope"]
    elif kind == "provider_error":
        del query["code"]
        del query["scope"]
        query["error"] = "synthetic-refusal"
        query["unknown_future_member"] = "secret-provider-value"
    callback = uri + "?" + urlencode(query) + ("&broken" if kind == "malformed" else "")
    with pytest.raises(oauth.CredentialRefused):
        session._exchange(callback, uri, account_alias="synthetic_account",
            clock_uncertainty_seconds=1, timeout_seconds=2, diagnostic=diagnostic)
    assert diagnostic.stage == stage and diagnostic.reason == reason and calls == []
    assert_valid_failure(diagnostic)
    assert "secret-provider-value" not in json.dumps(diagnostic.projection())


@pytest.mark.parametrize("raw,stage,reason,status_class", [
    (wire(status=400), "token_response_started", "non_success_status", "4xx"),
    (wire(status=503), "token_response_started", "non_success_status", "5xx"),
    (wire(status=201), "token_response_started", "non_success_status", "other_2xx"),
    (wire(status=204), "token_response_started", "non_success_status", "other_2xx"),
    (wire(status=302), "token_response_started", "non_success_status", "other"),
    (wire(headers=[("Transfer-Encoding", "chunked"), ("Content-Length", "5"),
                   ("Content-Type", "application/json")], body=b"0\r\n\r\n"),
     "token_response_started", "framing_invalid", "200"),
    (wire(headers=[("Content-Length", "1"), ("Content-Length", "1"),
                   ("Content-Type", "application/json")], body=b"{"),
     "token_response_started", "framing_invalid", "200"),
    (wire(headers=[("Transfer-Encoding", "gzip"), ("Content-Type", "application/json")]),
     "token_response_started", "framing_invalid", "200"),
    (wire(headers=[("Content-Length", "99999"), ("Content-Type", "application/json")]),
     "token_response_started", "body_size_invalid", "200"),
    (wire(headers=[("Content-Length", str(len(token_body()))), ("Content-Type", "application/json"),
                   ("Content-Encoding", "gzip")]),
     "token_response_started", "content_encoding_invalid", "200"),
    (wire(headers=[("Content-Length", str(len(token_body()))), ("Content-Type", "text/plain")]),
     "token_response_started", "content_type_invalid", "200"),
    (wire(headers=[("Content-Length", "9999"), ("Content-Type", "application/json")], body=b"{}"),
     "token_http_validated", "body_incomplete", "200"),
    (wire(headers=[("Transfer-Encoding", "chunked"), ("Content-Type", "application/json")],
          body=chunked(b"x" * 65537)), "token_http_validated", "body_size_invalid", "200"),
    (wire(body=b"{", headers=[("Content-Length", "1"), ("Content-Type", "application/json")]),
     "token_body_complete", "malformed_json", "200"),
    (wire(body=token_body_without_scope()), "token_json_parsed", "required_field_missing", "200"),
    (wire(body=token_body(scope="wrong")), "token_json_parsed", "semantic_scope_mismatch", "200"),
    (wire(body=token_body(token_type="DPoP")), "token_json_parsed", "token_type_invalid", "200"),
    (wire(body=token_body(expires_in="3600")), "token_json_parsed", "expires_in_invalid", "200"),
    (wire(body=token_body(access_token="bad token")),
     "token_json_parsed", "token_validation_failed", "200"),
])
def test_exchange_failure_stage_is_safe(monkeypatch, raw, stage, reason, status_class):
    fake_token_connection(monkeypatch, raw)
    session = oauth.DesktopPreparer(CLIENT)
    uri = "http://127.0.0.1:12345/"
    diagnostic = received_diagnostic()
    callback = uri[:-1] + callback_path(oauth.AUTH_URI + "?state=" + session._state)
    with pytest.raises(oauth.CredentialRefused):
        session._exchange(callback, uri, account_alias="synthetic_account",
            clock_uncertainty_seconds=1, timeout_seconds=2, diagnostic=diagnostic)
    assert diagnostic.stage == stage and diagnostic.reason == reason
    assert diagnostic.status_class == status_class
    assert_valid_failure(diagnostic)


@pytest.mark.parametrize("failure,reason", [
    (socket.gaierror("synthetic"), "dns_failure"),
    (ConnectionRefusedError("synthetic"), "tcp_failure"),
    (ssl.SSLError("synthetic"), "tls_failure"),
    (OSError("synthetic"), "connection_other"),
])
def test_actual_token_connection_failure_shapes(monkeypatch, failure, reason):
    class Connection:
        def __init__(self, *args, **kwargs):
            pass
        def connect(self):
            raise failure
        def close(self):
            pass
    monkeypatch.setattr(oauth.http.client, "HTTPSConnection", Connection)
    monkeypatch.setattr(p3, "environment_gate", lambda: None)
    session = oauth.DesktopPreparer(CLIENT)
    diagnostic = received_diagnostic()
    uri = "http://127.0.0.1:12345/"
    callback = uri[:-1] + callback_path(oauth.AUTH_URI + "?state=" + session._state)
    with pytest.raises(oauth.CredentialRefused):
        session._exchange(callback, uri, account_alias="synthetic_account",
            clock_uncertainty_seconds=1, timeout_seconds=2, diagnostic=diagnostic)
    assert diagnostic.stage == "token_connection_started" and diagnostic.reason == reason
    assert_valid_failure(diagnostic)


def fake_token_connection(monkeypatch, raw=None, calls=None):
    if raw is None:
        raw = wire()
    if calls is None:
        calls = []
    class Connection:
        def __init__(self, *args, **kwargs):
            assert args[:2] == ("oauth2.googleapis.com", 443)
        def connect(self):
            calls.append("connect")
        def request(self, *args, **kwargs):
            calls.append("request")
        def getresponse(self):
            calls.append("response")
            return parsed(raw)
        def close(self):
            calls.append("close")
    monkeypatch.setattr(oauth.http.client, "HTTPSConnection", Connection)
    monkeypatch.setattr(p3, "environment_gate", lambda: None)
    return calls


def callback_path(url, *, extra="", state=None):
    parts = urlsplit(url)
    original = parse_qs(parts.query)["state"][0]
    return "/?" + urlencode({"code": "synthetic code+value", "state": original if state is None else state,
                              "iss": oauth.CALLBACK_ISSUER, "scope": p1.SCOPE}) + extra


def loopback_port(url):
    redirect = parse_qs(urlsplit(url).query)["redirect_uri"][0]
    parts = urlsplit(redirect)
    assert parts.scheme == "http" and parts.hostname == "127.0.0.1" and parts.path == "/"
    return parts.port


def send(port, payload):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
            sock.sendall(payload)
            try:
                return sock.recv(4096)
            except ConnectionResetError:
                return b""
    except OSError:
        return b""


def request(path):
    return f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n".encode()


def test_real_loopback_valid_percent_encoded_exactly_once_and_closes(monkeypatch):
    calls = fake_token_connection(monkeypatch)
    session = oauth.DesktopPreparer(CLIENT)
    diagnostic = oauth.AcquisitionDiagnostic()
    responses = []
    port_holder = []
    def present(url):
        port = loopback_port(url)
        port_holder.append(port)
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.2", port), timeout=0.1)
        worker = threading.Thread(target=lambda: responses.append(send(port,
            request(callback_path(url)) + request("/favicon.ico"))))
        worker.start()
        threads.append(worker)
    threads = []
    token, _ = session.acquire(operator_confirmation=oauth.ACQUISITION_CONFIRMATION,
        present_url=present, account_alias="synthetic_account", clock_uncertainty_seconds=1,
        consent_seconds=2, exchange_timeout_seconds=2, diagnostic=diagnostic)
    for thread in threads:
        thread.join(2)
    assert token.value == TOKEN and len(responses) == 1 and b"200" in responses[0]
    assert calls == ["connect", "request", "response", "close"]
    assert diagnostic.stage == "token_semantics_validated" and diagnostic.callback_count == "one"
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port_holder[0]), timeout=0.1)


def test_idle_connection_does_not_consume_callback(monkeypatch):
    fake_token_connection(monkeypatch)
    session = oauth.DesktopPreparer(CLIENT)
    idle = []
    threads = []
    def present(url):
        port = loopback_port(url)
        idle.append(socket.create_connection(("127.0.0.1", port), timeout=1))
        thread = threading.Thread(target=lambda: (time.sleep(0.05), send(port, request(callback_path(url)))))
        thread.start()
        threads.append(thread)
    try:
        token, _ = session.acquire(operator_confirmation=oauth.ACQUISITION_CONFIRMATION,
            present_url=present, account_alias="synthetic_account", clock_uncertainty_seconds=1,
            consent_seconds=2, exchange_timeout_seconds=2)
        assert token.value == TOKEN
    finally:
        for sock in idle:
            sock.close()
        for thread in threads:
            thread.join(2)


@pytest.mark.parametrize("payload,reason,count", [
    (b"GARBAGE\r\n\r\n", "callback_count_invalid", "invalid"),
    (None, "callback_timeout", "zero"),
])
def test_real_loopback_diagnostic_invalid_vs_missing(monkeypatch, payload, reason, count):
    fake_token_connection(monkeypatch)
    session = oauth.DesktopPreparer(CLIENT)
    diagnostic = oauth.AcquisitionDiagnostic()
    threads = []
    def present(url):
        if payload is not None:
            thread = threading.Thread(target=lambda: send(loopback_port(url), payload))
            thread.start()
            threads.append(thread)
    with pytest.raises(oauth.CredentialRefused):
        session.acquire(operator_confirmation=oauth.ACQUISITION_CONFIRMATION,
            present_url=present, account_alias="synthetic_account", clock_uncertainty_seconds=1,
            consent_seconds=0.5, exchange_timeout_seconds=2, diagnostic=diagnostic)
    for thread in threads:
        thread.join(2)
    assert diagnostic.reason == reason and diagnostic.callback_count == count
    assert_valid_failure(diagnostic)


def test_real_loopback_handler_transport_failure_is_localized(monkeypatch):
    fake_token_connection(monkeypatch)
    def fail_response(self, *args, **kwargs):
        raise OSError("synthetic-handler-failure")
    monkeypatch.setattr(http.server.BaseHTTPRequestHandler, "send_response", fail_response)
    diagnostic = oauth.AcquisitionDiagnostic()
    threads = []
    def present(url):
        thread = threading.Thread(target=lambda: send(loopback_port(url), request(callback_path(url))))
        thread.start()
        threads.append(thread)
    with pytest.raises(oauth.CredentialRefused):
        oauth.DesktopPreparer(CLIENT).acquire(operator_confirmation=oauth.ACQUISITION_CONFIRMATION,
            present_url=present, account_alias="synthetic_account", clock_uncertainty_seconds=1,
            consent_seconds=1, exchange_timeout_seconds=2, diagnostic=diagnostic)
    for thread in threads:
        thread.join(2)
    assert diagnostic.stage == "authorization_url_presented"
    assert diagnostic.reason == "callback_transport_failure" and diagnostic.callback_count == "invalid"
    assert_valid_failure(diagnostic)


def test_received_callback_with_wrong_state_is_localized(monkeypatch):
    calls = fake_token_connection(monkeypatch)
    diagnostic = oauth.AcquisitionDiagnostic()
    threads = []
    def present(url):
        thread = threading.Thread(target=lambda: send(loopback_port(url),
            request(callback_path(url, state="wrong-state"))))
        thread.start()
        threads.append(thread)
    with pytest.raises(oauth.CredentialRefused):
        oauth.DesktopPreparer(CLIENT).acquire(operator_confirmation=oauth.ACQUISITION_CONFIRMATION,
            present_url=present, account_alias="synthetic_account", clock_uncertainty_seconds=1,
            consent_seconds=1, exchange_timeout_seconds=2, diagnostic=diagnostic)
    for thread in threads:
        thread.join(2)
    assert diagnostic.stage == "callback_parsed" and diagnostic.reason == "state_mismatch"
    assert diagnostic.callback_count == "one" and calls == []
    assert_valid_failure(diagnostic)


def test_second_favicon_socket_is_not_a_second_callback(monkeypatch):
    calls = fake_token_connection(monkeypatch)
    replies = []
    threads = []
    def present(url):
        port = loopback_port(url)
        def visit():
            replies.append(send(port, request(callback_path(url))))
            replies.append(send(port, request("/favicon.ico")))
        thread = threading.Thread(target=visit)
        thread.start()
        threads.append(thread)
    token, _ = oauth.DesktopPreparer(CLIENT).acquire(
        operator_confirmation=oauth.ACQUISITION_CONFIRMATION, present_url=present,
        account_alias="synthetic_account", clock_uncertainty_seconds=1,
        consent_seconds=1, exchange_timeout_seconds=2)
    for thread in threads:
        thread.join(2)
    assert token.value == TOKEN and b"200" in replies[0]
    assert len(replies) == 2 and b"200" not in replies[1]
    assert calls.count("request") == 1


def test_delayed_callback_within_deadline_and_after_deadline(monkeypatch):
    fake_token_connection(monkeypatch)
    threads = []
    def run(delay, consent):
        session = oauth.DesktopPreparer(CLIENT)
        diagnostic = oauth.AcquisitionDiagnostic()
        def present(url):
            thread = threading.Thread(target=lambda: (time.sleep(delay),
                send(loopback_port(url), request(callback_path(url)))))
            thread.start()
            threads.append(thread)
        try:
            return session.acquire(operator_confirmation=oauth.ACQUISITION_CONFIRMATION,
                present_url=present, account_alias="synthetic_account", clock_uncertainty_seconds=1,
                consent_seconds=consent, exchange_timeout_seconds=2, diagnostic=diagnostic), diagnostic
        except oauth.CredentialRefused:
            return None, diagnostic
    result, good = run(0.1, 1)
    failed, late = run(0.3, 0.1)
    for thread in threads:
        thread.join(2)
    assert result[0].value == TOKEN and good.stage == "token_semantics_validated"
    assert failed is None and late.reason == "callback_timeout"
    assert_valid_failure(late)


@pytest.mark.parametrize("fault", [None, "exclusive", "file_fsync", "directory_fsync"])
def test_acquisition_metadata_durable_write_primitives(tmp_path, monkeypatch, fault):
    path = tmp_path / "acquisition.json"
    metadata = oauth.AcquisitionMetadata(CLIENT.public_hash, "synthetic_account", 1000, 1001, 4600, 1)
    value = metadata.projection()
    if fault == "exclusive":
        p3.write_json(path, {"schema": "occupied"})
    original = os.fsync
    observed = []
    def fsync(fd):
        kind = "directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"
        observed.append(kind)
        if fault == kind + "_fsync":
            raise OSError("synthetic-fsync-failure")
        return original(fd)
    monkeypatch.setattr(p3.os, "fsync", fsync)
    if fault is None:
        p3.write_json(path, value)
        assert p3.load_json(path) == value and observed == ["file", "directory"]
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    else:
        with pytest.raises((OSError, FileExistsError)):
            p3.write_json(path, value)
        assert p3.load_json(path) != value if fault == "exclusive" else path.exists()
