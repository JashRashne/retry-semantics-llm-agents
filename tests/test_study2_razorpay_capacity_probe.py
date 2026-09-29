import json
import socket

import pytest

from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2 import razorpay_capacity_probe as capacity
from retry_semantics.study2.provider_paper_io import PaperTransportResult


@pytest.fixture
def stopped(tmp_path, monkeypatch):
    def deny(*a, **kw):
        raise AssertionError("unexpected network")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    source = tmp_path / "stopped"
    source.mkdir()
    capacity.base.write_once(source / "summary.json", {"state": "STOPPED"})
    capacity.base.write_once(source / "00005.result.json", {
        "provider": "razorpay", "method": "GET", "http_status": 429,
        "operation_type": "fetch_all", "manifest_sha256": "a" * 64, "runtime_sha256": {},
        "target": "https://api.razorpay.com/v1/orders?count=100&skip=0&from=1&to=2"})
    capacity.base.write_once(source / "inventory.json", capacity.base.inventory(source))
    return source


@pytest.mark.parametrize("status", [200, 401, 403, 429, 500])
def test_bounded_read_only_probe_and_actual_stop_report(tmp_path, stopped, status):
    before = capacity.base.inventory(stopped)
    now, calls = [0.0], []
    output = tmp_path / "diagnostic"
    def send(request, **kwargs):
        assert request.method == "GET" and request.body == b""
        assert request.url.endswith("count=100&skip=0&from=1&to=2")
        assert list(output.glob("*.intent.json")), "HTTP before durable intent"
        calls.append(now[0])
        response_status = 200 if len(calls) < 3 else status
        body = {"entity": "collection", "items": []} if response_status == 200 else {"error": "limited"}
        return PaperTransportResult(response_status, (("Retry-After", "3"),),
            canonical_json_bytes(body), None, True, True, True, now[0], now[0])
    summary = capacity.probe(stopped, output, credential="secret", send=send,
        clock=lambda: now[0], sleep=lambda delay: now.__setitem__(0, now[0]+delay),
        progress=lambda *a, **kw: None)
    assert capacity.base.inventory(stopped) == before
    assert summary["passed"] == (status == 200)
    assert len(calls) == (30 if status == 200 else 3)
    assert calls == [10.0 * (i+1) for i in range(len(calls))]
    assert summary["experiment_launch_authorized"] is False
    assert not list(tmp_path.rglob("*.started.json"))
    assert "secret" not in json.dumps(summary)
    if status in (401, 403, 429):
        assert summary["provider_stop_responses"][0]["http_status"] == status
        assert summary["provider_stop_responses"][0]["retry_after"] == "3"
    assert json.loads((output / "inventory.json").read_bytes()) == capacity.base.inventory(output)


def test_refuses_modified_stopped_evidence_before_network(tmp_path, stopped):
    (stopped / "summary.json").write_text("{}")
    with pytest.raises(capacity.base.PaperCollectionError, match="inventory"):
        capacity.probe(stopped, tmp_path / "output", credential="secret",
                       send=lambda *a, **kw: pytest.fail("network before evidence validation"))


def test_transport_exception_is_not_retried_or_leaked(tmp_path, stopped):
    now, calls = [0], []
    def fail(*a, **kw):
        calls.append(1)
        raise RuntimeError("secret credential")
    summary = capacity.probe(stopped, tmp_path / "output", credential="secret", send=fail,
        clock=lambda: now[0], sleep=lambda delay: now.__setitem__(0, now[0]+delay))
    assert calls == [1] and summary["failure_type"] == "RuntimeError"
    assert not summary["passed"] and "secret" not in json.dumps(summary)
