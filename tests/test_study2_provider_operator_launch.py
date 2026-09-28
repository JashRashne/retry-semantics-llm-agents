"""Offline host/consumption checks and real 256-arm schedules against stateful APIs."""
import json
import socket
from datetime import datetime, timezone
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import provider_operator_launch as launch
from retry_semantics.study2 import provider_paper_collection as collection
from retry_semantics.study2 import github_live_readiness as gh_ready
from retry_semantics.study2 import razorpay_live_readiness as rz_ready
from retry_semantics.study2.provider_paper_io import PaperRequest, PaperTransportResult
from retry_semantics.study2.provider_paper_readiness_controls import HISTORICAL_TEST_MARKER, HISTORICAL_TEST_ORDER_ID


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a, **kw):
        raise AssertionError("unexpected network")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


@pytest.mark.parametrize("error,status,received", [(None, 200, True), ("ReadError", 200, True),
                                                  ("TimeoutError", None, False)])
def test_readiness_preserves_transport_truth(error, status, received):
    req = PaperRequest("GET", "https://api.github.com/user", (), b"")
    resp = PaperTransportResult(status, (), b"{}", error, True, True, received, 1, 2)
    gh = gh_ready._pair_dict(req, resp, started_mono=1, ended_mono=2, api_version="2022-11-28")
    rz = rz_ready._pair_dict(req, resp, scope="s", started_mono=1, ended_mono=2)
    assert gh["request"]["headers"] == {}
    assert gh["response"]["headers"] == {}  # Never synthesize a provider header.
    for pair in (gh, rz):
        assert pair["response"]["transport_complete"] == (error is None and received)


def completion(action, args=None):
    message = {"role": "assistant", "content": "Done" if action == "finish" else None}
    if action != "finish":
        message["tool_calls"] = [{"id": "call-1", "type": "function",
            "function": {"name": action, "arguments": json.dumps(args or {})}}]
    return {"choices": [{"message": message, "finish_reason": "stop" if action == "finish" else "tool_calls"}]}


class API:
    def __init__(self, provider, manifest):
        self.provider, self.manifest = provider, manifest
        self.now = 1_800_000_000.0
        self.entries = []
        self.posts = []
        self.model_originals = 0

    def complete(self, payload):
        messages = payload["messages"]
        create, read = [t["name"] for t in self.manifest["model_visible_common"]["tools"]]
        if len(messages) == 1:  # Engineering-only model capability probe.
            return completion(create, self.manifest["families"][0]["target_semantic_m"])
        if len(messages) == 2:
            self.model_originals += 1
            family = next(f for f in self.manifest["families"] if f["user_task"] == messages[1]["content"])
            return completion(create, family["target_semantic_m"])
        if len(messages) == 4:
            return completion(read)
        if len(messages) == 6:
            observed = json.loads(messages[-1]["content"])
            if not observed["issues" if self.provider == "github" else "orders"]:
                return completion(create, json.loads(messages[2]["tool_calls"][0]["function"]["arguments"]))
        return completion("finish")

    def send(self, req, **kw):
        url, headers = urlsplit(req.url), []
        query = parse_qs(url.query)
        status = 200
        if req.method == "POST":
            self.posts.append(req)
            body = json.loads(req.body)
            if self.provider == "github":
                status = 201
                body.update(number=len(self.entries)+1, state="open")
            else:
                body.update(id=f"order_{len(self.entries)+1}", entity="order", status="created",
                            created_at=int(self.now), amount_paid=0, attempts=0, receipt=None)
            self.entries.append(body)
        elif self.provider == "github":
            page = int(query.get("page", [1])[0])
            body = self.entries[(page-1)*100:page*100]
            if page*100 < len(self.entries):
                target = f"https://api.github.com{url.path}?state=all&per_page=100&page={page+1}"
                headers.append(("Link", f'<{target}>; rel="next"'))
        elif url.path.endswith("/orders"):
            start, end = int(query["from"][0]), int(query["to"][0])
            items = [e for e in self.entries if start <= e["created_at"] <= end]
            skip = int(query["skip"][0])
            body = {"entity": "collection", "items": items[skip:skip+100]}
        else:
            body = next(e for e in self.entries if e["id"] == url.path.split("/")[-1])
        return PaperTransportResult(status, tuple(headers), canonical_json_bytes(body), None,
                                    True, True, True, self.now, self.now)


@pytest.mark.parametrize("provider,waiting", [("github", 192*600), ("razorpay", 128*370+64*200)])
def test_complete_real_serial_schedule_and_frozen_waits(tmp_path, monkeypatch, provider, waiting):
    manifest = launch.manifest_for(provider)
    api = API(provider, manifest)
    # A valid pre-data GitHub scope can grow above 860 during collection.
    if provider == "github":
        api.entries = [{"number": i+1, "title": "old", "body": "old", "state": "open"} for i in range(850)]
    monkeypatch.setattr(collection.time, "monotonic", lambda: api.now)
    monkeypatch.setattr(collection.time, "time", lambda: api.now)
    monkeypatch.setattr(collection.time, "sleep", lambda s: setattr(api, "now", api.now+s))
    monkeypatch.setattr(collection, "one_shot_http", api.send)
    monkeypatch.setattr(collection, "live_fireworks_completion", lambda key: api.complete)
    lock = tmp_path / "lock.json"
    lock.write_text("{}")
    (tmp_path / "writer_exclusion.json").write_text("{}")
    manifest_sha = sha256_hex(canonical_json_bytes(manifest))
    results = collection._execute_provider_schedule(
        provider=provider, run_dir=tmp_path / "collection", manifest=manifest,
        identity={"manifest_sha256": manifest_sha, "runtime_sha256": {}}, lock_path=lock,
        evidence_dir=tmp_path, credential="fake", model_api_key="fake", api_version="2022-11-28",
        authorization_sha256="a"*64, authorization_basis="offline-test")
    assert len(results) == 256
    assert {r.status for r in results} == {"SUCCESS", "FAILURE"}
    assert sum(r.status == "SUCCESS" for r in results) == 192
    assert api.model_originals == 64
    assert len(api.posts) == 320
    assert api.now - 1_800_000_000 == waiting
    assert len(launch.load_run_projections(tmp_path / "collection", manifest, provider, expected_families=64)) == 256


def test_plan_host_code_and_consumption(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, "git_head", lambda: "a"*40)
    path = tmp_path / "github.plan.json"
    launch.write_once(path, launch.build_plan("github", "operator"))
    assert launch.check_plan(path)["independent_audit_claimed"] is False
    monkeypatch.setattr(launch, "host_identity", lambda: "different-host")
    with pytest.raises(collection.PaperCollectionError, match="differs"):
        launch.check_plan(path)
    monkeypatch.setattr(launch, "claim_path", lambda p: tmp_path / "global" / f"{p}.json")
    launch.require_unconsumed(path, "github")
    path.with_suffix(".started.json").write_text("{}")
    with pytest.raises(collection.PaperCollectionError, match="consumed"):
        launch.require_unconsumed(path, "github")
    other = tmp_path / "other" / "github.plan.json"
    global_claim = launch.claim_path("github")
    global_claim.parent.mkdir()
    global_claim.write_text("{}")
    with pytest.raises(collection.PaperCollectionError, match="consumed"):
        launch.require_unconsumed(other, "github")


def test_readiness_failure_consumes_launch_and_retains_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, "git_head", lambda: "a"*40)
    path = tmp_path / "github.plan.json"
    launch.write_once(path, launch.build_plan("github", "operator"))
    monkeypatch.setattr(launch, "claim_path", lambda p: tmp_path / "global" / f"{p}.json")
    monkeypatch.setattr(launch, "credentials", lambda p: ("fake", "fake"))
    def fail(**kwargs):
        raise RuntimeError("secret-must-not-be-logged")
    monkeypatch.setattr(launch, "capture_github_readiness", fail)
    summary = launch.run(path, confirm_no_external_writers=True,
                         confirm_provider_never_started=True, progress=lambda *a, **kw: None)
    assert summary["state"] == "STOPPED" and summary["evaluated_arms"] == 0
    assert "secret" not in json.dumps(summary)
    assert (tmp_path / "github-run/inventory.json").exists()
    with pytest.raises(collection.PaperCollectionError, match="consumed"):
        launch.run(path, confirm_no_external_writers=True, confirm_provider_never_started=True)
    with pytest.raises(collection.PaperCollectionError, match="stopped"):
        launch.verify(tmp_path / "github-run")


@pytest.mark.parametrize("provider", ["github", "razorpay"])
def test_seven_live_readiness_controls_with_durable_intents(tmp_path, provider):
    manifest = launch.manifest_for(provider)
    api = API(provider, manifest)
    path = tmp_path / "readiness"
    def send(req):
        # Verify the exact request intent was persisted before touching the API.
        intents = sorted((path / "operations").glob("*.intent.json"))
        assert intents
        assert json.loads(intents[-1].read_bytes())["body_hex"] == req.body.hex()
        url = urlsplit(req.url)
        body = None
        if url.path == "/user":
            body = {"id": 42, "login": "operator"}
        elif url.path == "/rate_limit":
            body = {"resources": {"core": {"limit": 5000, "remaining": 4900}}}
        elif provider == "github" and url.path == "/repos/" + manifest["selected_repository"]:
            body = {"id": 123, "full_name": manifest["selected_repository"]}
        elif url.path.endswith("/" + HISTORICAL_TEST_ORDER_ID):
            body = {"id": HISTORICAL_TEST_ORDER_ID, "entity": "order",
                    "notes": {"retry_semantics_marker": HISTORICAL_TEST_MARKER}}
        response = (PaperTransportResult(200, (), canonical_json_bytes(body), None,
                    True, True, True, api.now, api.now) if body is not None else api.send(req))
        if provider == "github":
            response = replace(response, headers=response.headers + (("x-github-api-version-selected", "2022-11-28"),))
        return response
    capture = gh_ready.capture_github_readiness if provider == "github" else rz_ready.capture_razorpay_readiness
    registry = launch.github_registry().as_json() if provider == "github" else launch.razorpay_registry()
    hashes = capture(manifest=manifest, registry=registry, evidence_dir=path,
        identity=launch.current_static_identity(provider), operator_id="offline-operator",
        http_send=send, monotonic_fn=lambda: api.now,
        now_fn=lambda: datetime.fromtimestamp(api.now, timezone.utc),
        model_complete=lambda model, tools, sampling: completion(tools[0]["name"], manifest["families"][0]["target_semantic_m"]))
    assert len(hashes) == 7
    assert len(api.posts) == (2 if provider == "github" else 1)
    assert len(list((path / "operations").glob("*.intent.json"))) == len(list((path / "operations").glob("*.result.json")))


def test_transport_gap_does_not_retry():
    now, calls = [100.0], []
    def send(req, **kw):
        calls.append(now[0])
        return PaperTransportResult(429, (), b"{}", None, True, True, True, now[0], now[0])
    transport = launch.ProviderTransport("github", "fake", send=send,
        clock=lambda: now[0], sleep=lambda delay: now.__setitem__(0, now[0]+delay))
    request = PaperRequest("POST", "https://api.github.com/repos/test/test/issues", (), b"{}")
    assert transport(request).status == 429
    assert len(calls) == 1
    transport(request)
    assert calls == [100.0, 101.1]


def test_full_operator_launch_and_verify(tmp_path, monkeypatch):
    manifest = launch.manifest_for("razorpay")
    api = API("razorpay", manifest)
    monkeypatch.setattr(launch, "git_head", lambda: "a"*40)
    monkeypatch.setattr(launch, "claim_path", lambda p: tmp_path / "global" / f"{p}.json")
    monkeypatch.setattr(launch, "credentials", lambda p: ("fake", "fake"))
    monkeypatch.setattr(collection.time, "monotonic", lambda: api.now)
    monkeypatch.setattr(collection.time, "time", lambda: api.now)
    monkeypatch.setattr(collection.time, "sleep", lambda s: setattr(api, "now", api.now+s))
    monkeypatch.setattr(collection, "live_fireworks_completion", lambda key: api.complete)
    monkeypatch.setattr(launch, "live_fireworks_completion", lambda key: api.complete)
    def send(req):
        if req.url.endswith("/" + HISTORICAL_TEST_ORDER_ID):
            return PaperTransportResult(200, (), canonical_json_bytes({
                "id": HISTORICAL_TEST_ORDER_ID, "entity": "order",
                "notes": {"retry_semantics_marker": HISTORICAL_TEST_MARKER}}),
                None, True, True, True, api.now, api.now)
        return api.send(req)
    monkeypatch.setattr(launch, "ProviderTransport", lambda *a, **kw: send)
    real_capture = launch.capture_razorpay_readiness
    monkeypatch.setattr(launch, "capture_razorpay_readiness", lambda **kw: real_capture(
        **kw, monotonic_fn=lambda: api.now,
        now_fn=lambda: datetime.fromtimestamp(api.now, timezone.utc)))
    plan_path = tmp_path / "razorpay.plan.json"
    launch.write_once(plan_path, launch.build_plan("razorpay", "offline-operator"))
    summary = launch.run(plan_path, confirm_no_external_writers=True,
                         confirm_provider_never_started=True, progress=lambda *a, **kw: None)
    assert summary["state"] == "COMPLETED", summary
    assert summary["verdicts"] == {"SUCCESS": 192, "FAILURE": 64}
    assert launch.verify(tmp_path / "razorpay-run") == summary
    assert len(api.posts) == 321  # One readiness order plus 320 experimental creates.
    (tmp_path / "razorpay-run/manifest.json").write_text("{}")
    with pytest.raises(collection.PaperCollectionError, match="inventory"):
        launch.verify(tmp_path / "razorpay-run")
