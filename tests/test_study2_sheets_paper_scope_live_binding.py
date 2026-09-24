"""Offline hostile tests for the prospective paper live binding."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import socket
import time
from types import SimpleNamespace
import webbrowser

import pytest

from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2 import sheets_live_preparation as prepared
from retry_semantics.study2 import sheets_paper_scope_provisioning as paper
from retry_semantics.study2 import sheets_paper_live_transport as live
from retry_semantics.study2 import sheets_paper_scope_operator as operator

SENTINEL = "ya29.paper-secret-sentinel-do-not-persist"


@pytest.fixture(autouse=True)
def no_external_action(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("external action attempted")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(webbrowser, "open", blocked)


class Response:
    status = 200
    chunked = False
    version = 11
    length = 2

    def __init__(self, status=200, body=b"{}", headers=None, failure=None):
        self.status, self.body, self.failure = status, body, failure
        self.headers = headers if headers is not None else [
            ("Content-Length", str(len(body))), ("Content-Type", "application/json")]
        self.length = len(body)
        self.closed = False

    def getheaders(self):
        return self.headers

    def read(self, _size):
        if self.failure:
            raise self.failure
        self.length = 0
        self.closed = True
        return self.body

    def isclosed(self):
        return self.closed


class Connection:
    instances = []
    response = Response()
    failure_stage = None

    def __init__(self, host, port, *, timeout, context):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls = []
        self.auto_open = 1
        self.debuglevel = 1
        self.instances.append(self)

    def connect(self):
        self.calls.append(("connect",))
        if self.failure_stage == "connect":
            raise TimeoutError(SENTINEL)

    def putrequest(self, *args, **kwargs):
        self.calls.append(("request", args, kwargs))

    def putheader(self, *args):
        self.calls.append(("header", args))

    def endheaders(self, body, *, encode_chunked):
        self.calls.append(("send", body, encode_chunked))
        if self.failure_stage == "send":
            raise ConnectionResetError(SENTINEL)

    def getresponse(self):
        self.calls.append(("response",))
        if self.failure_stage == "status":
            raise TimeoutError(SENTINEL)
        return self.response

    def close(self):
        self.calls.append(("close",))


@pytest.fixture
def fake_https(monkeypatch):
    Connection.instances = []
    Connection.response = Response()
    Connection.failure_stage = None
    monkeypatch.setattr(live.ssl, "create_default_context", lambda **_kw: object())
    monkeypatch.setattr(live.phase1, "validate_context", lambda _ctx: None)
    monkeypatch.setattr(live.http.client, "HTTPSConnection", Connection)
    return Connection


def invoke(body=b'{"x":  1}'):
    return live.transport(paper.HOST, paper.PORT, paper.METHOD, paper.TARGET, body, SENTINEL)


def test_frozen_and_engineering_hashes_independently_match_disk():
    for path, digest in operator.PINNED.items():
        assert hashlib.sha256((operator.ROOT / path).read_bytes()).hexdigest() == digest
    assert paper.EVIDENCE_ROOT.name == "sheets-paper-scope-v1-76b0af67d7eece50cb12167e7ec374b9"
    assert not paper.EVIDENCE_ROOT.exists()


@pytest.mark.parametrize("change", ["host", "port", "method", "target"])
def test_exact_envelope_rejected_before_tls(fake_https, change):
    values = [paper.HOST, paper.PORT, paper.METHOD, paper.TARGET, b"{}", SENTINEL]
    values[["host", "port", "method", "target"].index(change)] = "wrong"
    with pytest.raises(live.PaperTransportRefused):
        live.transport(*values)
    assert not fake_https.instances


def test_exact_body_and_one_connection_no_redirect(fake_https):
    body = b'{ "a" : 1, "a": 2 }'
    assert invoke(body) == (200, b"{}")
    assert len(fake_https.instances) == 1
    connection = fake_https.instances[0]
    assert connection.auto_open == 0
    assert connection.calls.count(("connect",)) == 1
    assert [c for c in connection.calls if c[0] == "send"] == [("send", body, False)]
    assert [c for c in connection.calls if c[0] == "request"][0][1] == ("POST", paper.TARGET)
    assert connection.host == paper.HOST and connection.port == 443
    assert not hasattr(live, "refresh")


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_visible_status_one_shot(fake_https, status):
    fake_https.response = Response(status)
    assert invoke()[0] == status
    assert len(fake_https.instances) == 1
    assert fake_https.instances[0].calls.count(("connect",)) == 1
    assert len([c for c in fake_https.instances[0].calls if c[0] == "send"]) == 1


@pytest.mark.parametrize("stage", ["connect", "send", "status"])
def test_timeout_reset_and_send_uncertainty_one_shot(fake_https, stage):
    fake_https.failure_stage = stage
    with pytest.raises(live.PaperTransportRefused) as caught:
        invoke()
    assert SENTINEL not in str(caught.value)
    assert len(fake_https.instances) == 1
    assert fake_https.instances[0].calls.count(("connect",)) == 1


@pytest.mark.parametrize("headers,body,failure", [
    ([("Content-Type", "application/json")], b"{}", None),
    ([("Content-Length", "999999999"), ("Content-Type", "application/json")], b"{}", None),
    ([("Transfer-Encoding", "gzip"), ("Content-Type", "application/json")], b"{}", None),
    ([("Content-Length", "2"), ("Content-Type", "application/json")], b"{}", TimeoutError(SENTINEL)),
])
def test_visible_status_survives_framing_or_body_failure(fake_https, headers, body, failure):
    fake_https.response = Response(200, body, headers, failure)
    assert invoke() == (200, b"")
    assert len(fake_https.instances) == 1


def test_response_body_bound(fake_https):
    fake_https.response = Response(200, b"{}", [
        ("Content-Length", str(live.MAX_RESPONSE_BYTES + 1)),
        ("Content-Type", "application/json")])
    assert invoke() == (200, b"")


@pytest.mark.parametrize("oauth,provision,oauth_text,paper_text", [
    (False, True, "EXPLICIT_OPERATOR_OAUTH_ACQUISITION", paper.OPERATOR_CONFIRMATION),
    (True, False, "EXPLICIT_OPERATOR_OAUTH_ACQUISITION", paper.OPERATOR_CONFIRMATION),
    (True, True, "wrong", paper.OPERATOR_CONFIRMATION),
    (True, True, "EXPLICIT_OPERATOR_OAUTH_ACQUISITION", "wrong"),
])
def test_both_flags_and_both_confirmations_precede_source_or_network(
    monkeypatch, oauth, provision, oauth_text, paper_text,
):
    monkeypatch.setattr(operator, "source_projection", lambda *_: pytest.fail("source reached"))
    with pytest.raises(operator.PaperOperatorRefused):
        operator.provision_session(configuration=Path("/abs/operator.json"), client=Path("/abs/client.json"),
            expected_head="a" * 40, execute_oauth=oauth, oauth_confirmation=oauth_text,
            execute_provisioning=provision, paper_confirmation=paper_text)


def test_inspect_and_client_review_have_no_provider_or_oauth(monkeypatch, capsys):
    monkeypatch.setattr(operator, "source_projection", lambda _head: {})
    monkeypatch.setattr(operator.setup, "review_client", lambda _path: {"public_sha256": "a" * 64})
    assert operator.main(["inspect", "--expected-head", "a" * 40]) == 0
    assert operator.main(["client-review", "--client", "/abs/client.json"]) == 0
    output = capsys.readouterr()
    assert SENTINEL not in output.out + output.err


@pytest.mark.parametrize("state,expected_exit", [
    ("CREATE_RESPONSE_VALIDATED_PENDING_AUDIT", 0),
    ("VISIBLE_HTTP_FAILURE_TERMINAL", 2),
    ("PROVISIONING_OUTCOME_UNCERTAIN", 2),
    ("REFUSED", 2),
])
def test_cli_exit_state_is_only_process_signal(monkeypatch, capsys, state, expected_exit):
    calls = []
    def session(**kwargs):
        calls.append(kwargs)
        return {"state": state, "http_status": 403 if state == "VISIBLE_HTTP_FAILURE_TERMINAL" else None}
    monkeypatch.setattr(operator, "provision_session", session)
    assert operator.main(["provision-session", "--configuration", "/abs/operator.json",
        "--client", "/abs/client.json", "--expected-head", "a" * 40,
        "--execute-oauth", "--oauth-confirmation", "EXPLICIT_OPERATOR_OAUTH_ACQUISITION",
        "--execute-provisioning", "--paper-confirmation", paper.OPERATOR_CONFIRMATION]) == expected_exit
    assert len(calls) == 1
    output = capsys.readouterr()
    assert state in output.out and SENTINEL not in output.out + output.err


def test_cli_refusal_is_nonzero_without_retry(monkeypatch, capsys):
    calls = []
    def refused(**kwargs):
        calls.append(kwargs)
        raise operator.PaperOperatorRefused()
    monkeypatch.setattr(operator, "provision_session", refused)
    assert operator.main(["provision-session", "--configuration", "/abs/operator.json",
        "--client", "/abs/client.json", "--expected-head", "a" * 40,
        "--execute-oauth", "--oauth-confirmation", "EXPLICIT_OPERATOR_OAUTH_ACQUISITION",
        "--execute-provisioning", "--paper-confirmation", paper.OPERATOR_CONFIRMATION]) == 2
    assert len(calls) == 1
    assert SENTINEL not in repr(capsys.readouterr())


@pytest.mark.parametrize("stdin_tty,stdout_tty", [(False, True), (True, False)])
def test_noninteractive_refuses_before_oauth_or_provider(monkeypatch, stdin_tty, stdout_tty):
    monkeypatch.setattr(operator.sys, "stdin", SimpleNamespace(isatty=lambda: stdin_tty))
    monkeypatch.setattr(operator.sys, "stdout", SimpleNamespace(isatty=lambda: stdout_tty))
    monkeypatch.setattr(operator, "source_projection", lambda *_: pytest.fail("source reached"))
    actions = []
    monkeypatch.setattr(operator.resource, "setrlimit", lambda *_: actions.append("core"))
    monkeypatch.setattr(operator.setup, "acquire", lambda *_a, **_kw: actions.append("oauth"))
    monkeypatch.setattr(paper, "execute_create_once", lambda *_a, **_kw: actions.append("paper"))
    monkeypatch.setattr(live, "transport", lambda *_a: actions.append("provider"))
    with pytest.raises(operator.PaperOperatorRefused):
        operator.provision_session(configuration=Path("/abs/operator.json"),
            client=Path("/abs/client.json"), expected_head="a" * 40,
            execute_oauth=True, oauth_confirmation="EXPLICIT_OPERATOR_OAUTH_ACQUISITION",
            execute_provisioning=True, paper_confirmation=paper.OPERATOR_CONFIRMATION)
    assert actions == []


def test_core_limit_failure_refuses_before_oauth_or_provider(monkeypatch):
    monkeypatch.setattr(operator.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(operator.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(operator, "source_projection", lambda *_: pytest.fail("source reached"))
    actions = []
    def fail_limit(which, limits):
        actions.append((which, limits))
        raise OSError(SENTINEL)
    monkeypatch.setattr(operator.resource, "setrlimit", fail_limit)
    monkeypatch.setattr(operator.setup, "acquire", lambda *_a, **_kw: actions.append("oauth"))
    monkeypatch.setattr(paper, "execute_create_once", lambda *_a, **_kw: actions.append("paper"))
    monkeypatch.setattr(live, "transport", lambda *_a: actions.append("provider"))
    with pytest.raises(operator.PaperOperatorRefused) as caught:
        operator.provision_session(configuration=Path("/abs/operator.json"),
            client=Path("/abs/client.json"), expected_head="a" * 40,
            execute_oauth=True, oauth_confirmation="EXPLICIT_OPERATOR_OAUTH_ACQUISITION",
            execute_provisioning=True, paper_confirmation=paper.OPERATOR_CONFIRMATION)
    assert actions == [(operator.resource.RLIMIT_CORE, (0, 0))]
    assert SENTINEL not in str(caught.value)


def test_source_pin_rejects_dirty_or_uncommitted_before_acquisition(monkeypatch):
    with pytest.raises(operator.PaperOperatorRefused):
        operator.source_projection("a" * 40)
    assert "setup.acquire" in inspect.getsource(operator.provision_session)
    assert "paper.execute_create_once" in inspect.getsource(operator.provision_session)
    assert "spreadsheets.create" not in inspect.getsource(operator)
    assert "EVIDENCE_ROOT" not in inspect.signature(operator.provision_session).parameters


def test_altered_dependency_and_request_pin_fail(monkeypatch):
    def committed(*args):
        if args == ("rev-parse", "HEAD"):
            return ("a" * 40 + "\n").encode()
        if args == ("rev-parse", "--show-toplevel"):
            return (str(operator.ROOT) + "\n").encode()
        if args == ("status", "--porcelain", "--ignore-submodules=all"):
            return b""
        if args[:1] == ("show",):
            return (operator.ROOT / args[1].removeprefix("HEAD:")).read_bytes()
        pytest.fail("unexpected git call")
    monkeypatch.setattr(operator, "_git", committed)
    assert operator.source_projection("a" * 40)["clean_committed_tree"] is True
    original = operator.PINNED["src/retry_semantics/study2/sheets_phase3_credentials.py"]
    monkeypatch.setitem(operator.PINNED, "src/retry_semantics/study2/sheets_phase3_credentials.py", "0" * 64)
    with pytest.raises(operator.PaperOperatorRefused):
        operator.source_projection("a" * 40)
    monkeypatch.setitem(operator.PINNED, "src/retry_semantics/study2/sheets_phase3_credentials.py", original)
    monkeypatch.setitem(operator.PINNED, str(paper.REQUEST_PATH), "0" * 64)
    with pytest.raises(operator.PaperOperatorRefused):
        operator.source_projection("a" * 40)


def test_dirty_and_substituted_committed_sources_refused(monkeypatch):
    def git(*args):
        if args == ("rev-parse", "HEAD"):
            return ("a" * 40 + "\n").encode()
        if args == ("rev-parse", "--show-toplevel"):
            return (str(operator.ROOT) + "\n").encode()
        if args == ("status", "--porcelain", "--ignore-submodules=all"):
            return b" M source.py\n"
        pytest.fail("dirty source reached show")
    monkeypatch.setattr(operator, "_git", git)
    with pytest.raises(operator.PaperOperatorRefused):
        operator.source_projection("a" * 40)
    def substituted(*args):
        if args == ("status", "--porcelain", "--ignore-submodules=all"):
            return b""
        if args == ("show", "HEAD:" + next(iter(operator.PINNED))):
            return b"substituted"
        if args[:1] == ("show",):
            return (operator.ROOT / args[1].removeprefix("HEAD:")).read_bytes()
        return git(*args)
    monkeypatch.setattr(operator, "_git", substituted)
    with pytest.raises(operator.PaperOperatorRefused):
        operator.source_projection("a" * 40)


@pytest.mark.parametrize("fail_gate", [False, True])
def test_resident_fake_session_one_acquisition_one_gate(monkeypatch, tmp_path, capsys, fail_gate):
    monkeypatch.setattr(operator.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(operator.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    order = []
    monkeypatch.setattr(operator.resource, "setrlimit", lambda which, limits: order.append((which, limits)))
    monkeypatch.setattr(operator, "source_projection", lambda _head: {})
    monkeypatch.setattr(paper, "EVIDENCE_ROOT", tmp_path)
    class Config:
        expected_head = "a" * 40
        def path(self, name):
            return Path("/abs") / name
    monkeypatch.setattr(operator.phase3_operator, "_typed", lambda *_: Config())
    monkeypatch.setattr(operator.phase3, "load_json", lambda *_: {})
    acquisitions, gates = [], []
    sends = []
    token = prepared.PreparedToken(SENTINEL, time.time() + 3600, 0)
    def acquire(*_args, **_kwargs):
        order.append("oauth")
        acquisitions.append(1)
        return token, object()
    def gate(transport, bearer, **kwargs):
        gates.append((transport, bearer, kwargs))
        assert transport(paper.HOST, paper.PORT, paper.METHOD, paper.TARGET, b"{}", bearer) == (403, b"{}")
        if fail_gate:
            raise RuntimeError(SENTINEL)
        return {"state": "PROVISIONING_OUTCOME_UNCERTAIN", "http_status": None}
    monkeypatch.setattr(operator.setup, "acquire", acquire)
    monkeypatch.setattr(paper, "execute_create_once", gate)
    monkeypatch.setattr(live, "transport", lambda *args: (sends.append(args), (403, b"{}"))[1])
    def run():
        return operator.provision_session(configuration=Path("/abs/operator.json"),
            client=Path("/abs/client.json"), expected_head="a" * 40,
            execute_oauth=True, oauth_confirmation="EXPLICIT_OPERATOR_OAUTH_ACQUISITION",
            execute_provisioning=True, paper_confirmation=paper.OPERATOR_CONFIRMATION)
    if fail_gate:
        with pytest.raises(operator.PaperOperatorRefused) as caught:
            run()
        assert SENTINEL not in str(caught.value)
    else:
        result = run()
        assert result["state"] == "PROVISIONING_OUTCOME_UNCERTAIN"
        assert SENTINEL not in repr(result)
    assert len(acquisitions) == len(gates) == 1
    assert order == [(operator.resource.RLIMIT_CORE, (0, 0)), "oauth"]
    assert len(sends) == 1
    assert sends[0][:4] == (paper.HOST, paper.PORT, paper.METHOD, paper.TARGET)
    assert gates[0][1] == SENTINEL
    assert not list(tmp_path.iterdir())
    output = capsys.readouterr()
    assert SENTINEL not in output.out + output.err


def test_frozen_gate_sentinel_evidence_and_no_second_create(monkeypatch, tmp_path):
    monkeypatch.setattr(paper, "EVIDENCE_ROOT", tmp_path)
    calls = []
    def once(*_args):
        calls.append(1)
        return 403, b"{}"
    first = paper.execute_create_once(once, SENTINEL, execute_provisioning=True,
                                       operator_confirmation=paper.OPERATOR_CONFIRMATION)
    assert first["state"] == "VISIBLE_HTTP_FAILURE_TERMINAL"
    with pytest.raises(Exception):
        paper.execute_create_once(once, SENTINEL, execute_provisioning=True,
                                   operator_confirmation=paper.OPERATOR_CONFIRMATION)
    assert calls == [1]
    evidence = b"".join(path.read_bytes() for path in tmp_path.iterdir() if path.is_file())
    assert SENTINEL.encode() not in evidence
    assert hashlib.sha256(SENTINEL.encode()).hexdigest().encode() not in evidence
    assert SENTINEL not in repr(first)
    assert not (operator.ROOT / "research/study2/sheets/GOOGLE_SHEETS_PAPER_SCOPE_BINDING_V1.json").exists()
