"""Hostile offline-only tests: every synthetic outbound request must be GET."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import socket
from threading import Barrier, Lock

import httpx
import pytest

from scripts import qualify_study2_razorpay_phase2 as cli
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import razorpay_phase2_readonly as p2
from retry_semantics.study2.razorpay_adapter import MARKER_KEY, RazorpayCredentials


ROOT = Path(__file__).resolve().parents[1]
KEY_ID = "rzp_test_phase2_synthetic_only"
SECRET = "phase2_synthetic_secret_NEVER_SEND"
SCOPE = RazorpayCredentials(KEY_ID, SECRET).scope_fingerprint
HEAD = "a" * 40


@pytest.fixture(autouse=True)
def prohibit_external_sockets(monkeypatch):
    def blocked(*_args, **_kwargs):
        pytest.fail("external socket/network use prohibited")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def gate(tmp_path, monkeypatch):
    frozen = p2.read_phase1_facts(ROOT)
    synthetic_facts = {**frozen, "credential_scope_fingerprint": SCOPE}
    monkeypatch.setattr(p2, "read_phase1_facts", lambda root: synthetic_facts)
    package = tmp_path / "synthetic-package"
    provenance = {"clean": True, "git_head": HEAD, "origin_main": HEAD}
    hashes = p2.read_source_hashes(ROOT)
    runtime = {"httpx": "0.28.1"}

    def prepare(**override):
        return p2.prepare_package(
            ROOT, package,
            _provenance_reader=lambda _: override.get("provenance", provenance),
            _source_hash_reader=lambda _: override.get("hashes", hashes),
            _runtime_reader=lambda: override.get("runtime", runtime),
        )

    def execute(stages, *, key_id=KEY_ID, key_secret=SECRET, record=None, **override):
        queue = list(stages)
        lock = Lock()
        if record is None:
            record = []

        def handler(request):
            if request.method != "GET":
                pytest.fail("read-only invariant violated")
            with lock:
                record.append(request)
                if not queue:
                    pytest.fail("unexpected additional GET")
                item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            if callable(item):
                item = item(request)
            if isinstance(item, httpx.Response):
                return item
            if type(item) is int:
                return httpx.Response(item, json={"synthetic_error": True})
            if type(item) is bytes:
                return httpx.Response(200, content=item)
            return httpx.Response(200, json=item)

        return p2.execute_package(
            ROOT, package,
            execute_live_readonly_diagnostic=override.get("flag", True),
            confirmation=override.get("confirmation", p2.CONFIRMATION),
            test_mode_operator_confirmation=override.get("test_mode", p2.TEST_MODE_CONFIRMATION),
            plan_file_sha256=override.get("plan_hash", p2.plan_file_sha256(package)),
            key_id=key_id, key_secret=key_secret,
            _provenance_reader=lambda _: override.get("provenance", provenance),
            _source_hash_reader=lambda _: override.get("hashes", hashes),
            _runtime_reader=lambda: override.get("runtime", runtime),
            _synthetic_transport=httpx.MockTransport(handler),
            _synthetic_test_execution=True,
        )

    return {"package": package, "prepare": prepare, "execute": execute,
            "facts": synthetic_facts, "provenance": provenance, "hashes": hashes}


def _order(facts, created_at=1790103800, **overrides):
    value = {
        "id": facts["provider_order_id"], "entity": "order", "amount": 200,
        "currency": "INR", "receipt": None, "notes": {MARKER_KEY: facts["marker"]},
        "created_at": created_at, "status": "created", "attempts": 0,
    }
    value.update(overrides)
    return value


def _collection(facts, ids=()):
    return {"entity": "collection", "items": [
        {"id": item, "entity": "order", "notes": {MARKER_KEY: facts["marker"]}}
        for item in ids
    ]}


def _load(package, name):
    return json.loads((package / name).read_bytes())


def _assert_sanitized(package):
    content = "\n".join(path.read_text() for path in package.iterdir())
    assert KEY_ID not in content
    assert SECRET not in content
    assert "Authorization" not in content
    assert "Basic " not in content


def test_frozen_phase1_evidence_and_derived_facts():
    facts = p2.read_phase1_facts(ROOT)
    assert facts["provider_order_id"] == "order_TfBuv3iQHQrz9p"
    assert facts["marker"] == "study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215"
    assert (facts["original_from_timestamp"], facts["original_to_timestamp"]) == (1790103525, 1790104125)
    assert len(facts["credential_scope_fingerprint"]) == 64
    for relative, digest in p2.PHASE1_HASHES.items():
        assert sha256_hex((ROOT / relative).read_bytes()) == digest


def test_external_socket_guard_is_active():
    sock = socket.socket()
    try:
        with pytest.raises(BaseException, match="external socket/network use prohibited"):
            sock.connect(("203.0.113.1", 443))
    finally:
        sock.close()


def test_prepare_plan_only_hashes_location_and_no_network(gate):
    plan = gate["prepare"]()
    package = gate["package"]
    assert {x.name for x in package.iterdir()} == {p2.PLAN_FILENAME}
    assert plan["phase"] == 2 and plan["read_only"] is True
    assert plan["mutation_dispatch_maximum"] == plan["post_dispatch_maximum"] == 0
    assert plan["get_dispatch_maximum"] == 5
    assert plan["phase1_evidence_hashes"] == p2.PHASE1_HASHES
    assert plan["provider_order_id"] == gate["facts"]["provider_order_id"]
    assert plan["credential_scope_fingerprint"] == SCOPE
    assert plan["source_hashes"] == gate["hashes"]
    assert plan["git_head"] == plan["origin_main"] == HEAD
    assert plan["runtime_versions"] == {"httpx": "0.28.1"}
    raw = (package / p2.PLAN_FILENAME).read_bytes()
    assert p2.plan_file_sha256(package) == sha256_hex(raw)
    without_hash = dict(plan)
    without_hash.pop("plan_sha256")
    assert plan["plan_sha256"] == sha256_hex(canonical_json_bytes(without_hash))
    assert plan["package_location_sha256"] == p2._location_hash(plan["qualification_id"], package)
    assert str(package) not in raw.decode()
    _assert_sanitized(package)
    with pytest.raises(p2.QualificationError, match="package_already_exists"):
        gate["prepare"]()


def test_prepare_rejects_dirty_head_runtime_and_inside_repo(gate):
    with pytest.raises(p2.QualificationError, match="working_tree_not_clean"):
        gate["prepare"](provenance={**gate["provenance"], "clean": False})
    with pytest.raises(p2.QualificationError, match="head_origin_main_mismatch"):
        gate["prepare"](provenance={**gate["provenance"], "origin_main": "b" * 40})
    with pytest.raises(p2.QualificationError, match="invalid_git_head"):
        gate["prepare"](provenance={"clean": True, "git_head": "bad", "origin_main": "bad"})
    with pytest.raises(p2.QualificationError, match="runtime_dependency_mismatch"):
        gate["prepare"](runtime={"httpx": "0.0.0"})
    with pytest.raises(p2.QualificationError, match="outside_repository"):
        p2.prepare_package(ROOT, ROOT / "forbidden-phase2-package")


def test_exact_hash_internal_tamper_and_copied_package_fail(gate, tmp_path):
    plan = gate["prepare"]()
    package = gate["package"]
    original_hash = p2.plan_file_sha256(package)
    path = package / p2.PLAN_FILENAME
    changed = dict(plan)
    changed["get_dispatch_maximum"] = 6
    changed.pop("plan_sha256")
    changed["plan_sha256"] = sha256_hex(canonical_json_bytes(changed))
    path.write_bytes(canonical_json_bytes(changed) + b"\n")
    with pytest.raises(p2.QualificationError, match="plan_file_sha256_mismatch"):
        gate["execute"]([], plan_hash=original_hash)
    with pytest.raises(p2.QualificationError, match="plan_invariant_mismatch"):
        gate["execute"]([], plan_hash=p2.plan_file_sha256(package))
    path.write_bytes(canonical_json_bytes(plan) + b"\n")
    copy = tmp_path / "copied"
    shutil.copytree(package, copy)
    with pytest.raises(p2.QualificationError, match="package_location_mismatch"):
        p2._load_plan(copy, p2.plan_file_sha256(copy), gate["facts"])


def test_scope_mismatch_consumes_without_provider_get(gate):
    gate["prepare"]()
    requests = []
    result = gate["execute"]([], key_secret="different_synthetic_secret", record=requests)
    assert result.status is p2.TerminalStatus.LOCAL_PREFLIGHT_FAILED
    assert result.reason == "credential_scope_mismatch"
    assert requests == [] and result.counts["total_get_dispatches"] == 0
    assert (gate["package"] / p2.INTENT_FILENAME).exists()
    _assert_sanitized(gate["package"])
    with pytest.raises(p2.QualificationError, match="package_already_consumed"):
        gate["execute"]([])


@pytest.mark.parametrize("invalid", [
    {"id": "order_other"}, {"entity": "payment"}, {"amount": 201},
    {"currency": "USD"}, {"receipt": "not-null"}, {"notes": None},
    {"notes": {}}, {"notes": {MARKER_KEY: "wrong"}},
    {"notes": {MARKER_KEY: 1}}, {"created_at": None},
    {"created_at": "1790103800"}, {"created_at": -1},
])
def test_invalid_direct_fetch_stops_before_lists(gate, invalid):
    gate["prepare"]()
    value = _order(gate["facts"], **invalid)
    requests = []
    result = gate["execute"]([value], record=requests)
    assert result.status is p2.TerminalStatus.INCONCLUSIVE
    assert result.reason == "direct_fetch_not_validated"
    assert len(requests) == result.counts["total_get_dispatches"] == 1
    assert requests[0].url.path == "/v1/orders/order_TfBuv3iQHQrz9p"
    assert not (gate["package"] / "original_window_observation.json").exists()
    direct = _load(gate["package"], "direct_fetch.json")
    assert direct["engineering_only"] is True and direct["paper_observations"] == 0
    if invalid.get("id") == "order_other":
        assert direct["provider_order_id"] is None
        assert direct["requested_provider_order_id"] == gate["facts"]["provider_order_id"]
    if "notes" in invalid and invalid["notes"] != {MARKER_KEY: gate["facts"]["marker"]}:
        assert direct["exact_marker_match"] is False
    _assert_sanitized(gate["package"])


def test_missing_notes_and_hostile_response_strings_are_not_persisted(gate):
    gate["prepare"]()
    value = _order(gate["facts"])
    value.pop("notes")
    value["entity"] = KEY_ID
    value["currency"] = SECRET
    value["status"] = SECRET
    result = gate["execute"]([value])
    assert result.reason == "direct_fetch_not_validated"
    assert _load(gate["package"], "direct_fetch.json")["exact_marker_match"] is False
    _assert_sanitized(gate["package"])


@pytest.mark.parametrize("response", [500, httpx.TimeoutException("secret-looking timeout"), b"not-json", [1, 2]])
def test_direct_http_timeout_or_json_failure(gate, response):
    gate["prepare"]()
    requests = []
    result = gate["execute"]([response], record=requests)
    assert result.reason == "direct_fetch_not_validated"
    assert len(requests) == 1
    assert not (gate["package"] / "original_window_observation.json").exists()
    _assert_sanitized(gate["package"])


def test_exact_original_window_resolves_without_provider_window(gate):
    gate["prepare"]()
    facts = gate["facts"]
    requests = []
    result = gate["execute"]([_order(facts), _collection(facts, [facts["provider_order_id"]])], record=requests)
    assert result.status is p2.TerminalStatus.RESOLVED
    assert result.reason == "later_list_visibility_established_under_original_window"
    assert len(requests) == result.counts["total_get_dispatches"] == 2
    assert result.counts["post_dispatches"] == result.counts["mutation_dispatches"] == 0
    assert not (gate["package"] / "provider_window_observation.json").exists()
    assert dict(requests[1].url.params) == {"count": "100", "skip": "0", "from": "1790103525", "to": "1790104125"}
    assert _load(gate["package"], "original_window_observation.json")["adapter_evidence"]["matching_order_ids"] == [facts["provider_order_id"]]
    assert _load(gate["package"], "direct_fetch.json")["status"] == "created"
    assert _load(gate["package"], "direct_fetch.json")["attempts"] == 0
    assert _load(gate["package"], "direct_fetch.json")["provider_order_id"] == facts["provider_order_id"]
    _assert_sanitized(gate["package"])


@pytest.mark.parametrize("created_at,expected_reason,expected_status", [
    (1790104500, "provider_timestamp_window_explains_phase1_miss", p2.TerminalStatus.RESOLVED),
    (1790103800, "window_behavior_requires_further_review", p2.TerminalStatus.INCONCLUSIVE),
])
def test_conditional_provider_window_interpretation(gate, created_at, expected_reason, expected_status):
    gate["prepare"]()
    facts = gate["facts"]
    requests = []
    result = gate["execute"]([
        _order(facts, created_at=created_at), _collection(facts),
        _collection(facts, [facts["provider_order_id"]]),
    ], record=requests)
    assert result.status is expected_status and result.reason == expected_reason
    assert len(requests) == result.counts["total_get_dispatches"] == 3
    assert dict(requests[2].url.params) == {
        "count": "100", "skip": "0", "from": str(created_at - 300), "to": str(created_at + 300),
    }
    assert _load(gate["package"], "provider_window_observation.json")["from_timestamp"] == created_at - 300
    _assert_sanitized(gate["package"])


def test_both_list_windows_miss(gate):
    gate["prepare"]()
    facts = gate["facts"]
    result = gate["execute"]([_order(facts), _collection(facts), _collection(facts)])
    assert result.status is p2.TerminalStatus.INCONCLUSIVE
    assert result.reason == "direct_fetch_visible_list_visibility_not_established"
    assert result.counts["total_get_dispatches"] == 3


@pytest.mark.parametrize("original", [
    503, b"broken", {"entity": "collection", "items": [{"id": "x", "entity": "order"}]},
    {"entity": "collection", "items": [{"id": "order_other", "entity": "order", "notes": {MARKER_KEY: "study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215"}}]},
])
def test_original_window_incomplete_or_extra_stops(gate, original):
    gate["prepare"]()
    facts = gate["facts"]
    requests = []
    result = gate["execute"]([_order(facts), original], record=requests)
    assert result.status is p2.TerminalStatus.INCONCLUSIVE
    assert result.reason in {"original_window_observation_incomplete", "original_window_unexpected_matching_resource"}
    assert len(requests) == 2
    assert not (gate["package"] / "provider_window_observation.json").exists()


def test_original_window_expected_plus_extra_stops(gate):
    gate["prepare"]()
    facts = gate["facts"]
    result = gate["execute"]([
        _order(facts), _collection(facts, [facts["provider_order_id"], "order_other"]),
    ])
    assert result.reason == "original_window_unexpected_matching_resource"
    assert not (gate["package"] / "provider_window_observation.json").exists()


def test_provider_window_negative_bound_stops_without_third_get(gate):
    gate["prepare"]()
    facts = gate["facts"]
    requests = []
    result = gate["execute"]([_order(facts, created_at=100), _collection(facts)], record=requests)
    assert result.reason == "provider_window_bounds_invalid"
    assert len(requests) == 2


@pytest.mark.parametrize("provider", [503, b"broken", _collection({"marker": "study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215"}, ["order_other"])])
def test_provider_window_incomplete_or_extra(gate, provider):
    gate["prepare"]()
    facts = gate["facts"]
    result = gate["execute"]([_order(facts), _collection(facts), provider])
    assert result.status is p2.TerminalStatus.INCONCLUSIVE
    assert result.reason in {"provider_window_observation_incomplete", "provider_window_unexpected_matching_resource"}
    assert result.counts["total_get_dispatches"] == 3


def test_two_page_cap_and_no_polling(gate):
    gate["prepare"]()
    facts = gate["facts"]
    full_page = {"entity": "collection", "items": [
        {"id": f"order_synthetic_{i}", "entity": "order", "notes": {}}
        for i in range(100)
    ]}
    requests = []
    result = gate["execute"]([
        _order(facts), full_page, _collection(facts), full_page,
        _collection(facts, [facts["provider_order_id"]]),
    ], record=requests)
    assert result.counts["total_get_dispatches"] == len(requests) == 5
    assert result.counts["original_window_get_dispatches"] == 2
    assert result.counts["provider_window_get_dispatches"] == 2
    assert [request.url.params.get("skip") for request in requests[1:]] == ["0", "100", "0", "100"]
    assert all(request.method == "GET" for request in requests)


def test_intent_race_one_owner_loser_zero_gets(gate):
    gate["prepare"]()
    facts = gate["facts"]
    barrier = Barrier(2)
    calls = []

    def run():
        barrier.wait()
        try:
            result = gate["execute"]([_order(facts), _collection(facts, [facts["provider_order_id"]])], record=calls)
            return result.reason
        except p2.QualificationError as error:
            return error.reason

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert results.count("later_list_visibility_established_under_original_window") == 1
    assert len(set(results) & {"artifact_already_exists", "package_already_consumed", "package_not_pristine"}) == 1
    assert len(calls) == 2
    assert _load(gate["package"], p2.INTENT_FILENAME)["session_consumed"] is True
    assert _load(gate["package"], p2.RESULT_FILENAME)["reason"] == "later_list_visibility_established_under_original_window"


def test_crash_intent_never_refunds(gate):
    plan = gate["prepare"]()
    path = gate["package"] / p2.INTENT_FILENAME
    p2._write_exclusive_json(path, {"qualification_id": plan["qualification_id"], "session_consumed": True})
    with pytest.raises(p2.QualificationError, match="package_already_consumed"):
        gate["execute"]([])
    assert not (gate["package"] / p2.RESULT_FILENAME).exists()


def test_cli_requires_explicit_flags_and_has_no_synthetic_switch():
    parser = cli._parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["execute", "--synthetic-test-execution"])
    with pytest.raises(SystemExit):
        parser.parse_args(["execute", "--repository-root", str(ROOT), "--package-dir", "/tmp/x"])
