"""Offline hostile checks for the one-shot Phase-3 gate."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import socket
from threading import Barrier, Lock

import httpx
import pytest

from scripts import qualify_study2_razorpay_phase3 as cli
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import razorpay_phase3_replay_visibility as p3
from retry_semantics.study2.razorpay_adapter import MARKER_KEY, RazorpayCredentials


ROOT = Path(__file__).resolve().parents[1]
KEY_ID = "rzp_test_phase3_synthetic_only"
SECRET = "phase3_synthetic_secret_NEVER_SEND"
SCOPE = RazorpayCredentials(KEY_ID, SECRET).scope_fingerprint
HEAD = "a" * 40
SECOND = "order_SyntheticSecond123"


@pytest.fixture(autouse=True)
def prohibit_external_sockets(monkeypatch):
    def blocked(*_args, **_kwargs):
        pytest.fail("external socket/network use prohibited")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert seconds > 0
        self.sleeps.append(seconds)
        self.now += seconds


def _collection(ids=(), marker=p3.MARKER):
    return {"entity": "collection", "items": [
        {"id": item, "entity": "order", "notes": {MARKER_KEY: marker}}
        for item in ids
    ]}


def _ack(order_id=SECOND, **overrides):
    value = {"id": order_id, "entity": "order", "amount": 200, "currency": "INR",
             "receipt": None, "notes": {MARKER_KEY: p3.MARKER}, "status": "created",
             "attempts": 0, "amount_paid": 0}
    value.update(overrides)
    return value


def _direct(order_id=SECOND, **overrides):
    value = {"id": order_id, "entity": "order", "amount": 200, "currency": "INR",
             "receipt": None, "notes": {MARKER_KEY: p3.MARKER}, "created_at": 1790200001}
    value.update(overrides)
    return value


def _direct_without_notes(order_id=SECOND, **overrides):
    value = _direct(order_id=order_id, **overrides)
    value.pop("notes", None)
    return value


def _load(package, name):
    return json.loads((package / name).read_bytes())


def _assert_no_secrets(package):
    content = "\n".join(path.read_text() for path in package.iterdir())
    for forbidden in (KEY_ID, SECRET, "Authorization", "Basic "):
        assert forbidden not in content


@pytest.fixture
def gate(tmp_path, monkeypatch):
    real = p3.read_frozen_facts(ROOT)
    facts = {**real, "credential_scope_fingerprint": SCOPE}
    request = p3._frozen_request(real)
    monkeypatch.setattr(p3, "SCOPE_SHA256", SCOPE)
    synthetic_identity = p3._frozen_request.__globals__["FrozenOrderCreateRequest"](
        provider_candidate=request.provider_candidate, operation=request.operation,
        method=request.method, origin=request.origin, path=request.path,
        content_type=request.content_type, body=request.body, marker=request.marker,
        amount=request.amount, currency=request.currency,
        credential_scope_fingerprint=SCOPE, timeout_seconds=request.timeout_seconds,
        transport_profile=request.transport_profile,
    ).identity_sha256
    monkeypatch.setattr(p3, "IDENTITY_SHA256", synthetic_identity)
    monkeypatch.setattr(p3, "read_frozen_facts", lambda _: facts)
    package = tmp_path / "synthetic-package"
    provenance = {"clean": True, "git_head": HEAD, "origin_main": HEAD}
    hashes = p3.read_source_hashes(ROOT)
    runtime = {"httpx": "0.28.1"}
    clock = Clock()

    def prepare(**override):
        return p3.prepare_package(
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
            with lock:
                record.append(request)
                if not queue:
                    pytest.fail("unexpected additional provider request")
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

        return p3.execute_package(
            ROOT, package,
            execute_live_replay_visibility_qualification=override.get("flag", True),
            confirmation=override.get("confirmation", p3.CONFIRMATION),
            test_mode_operator_confirmation=override.get("test_mode", p3.TEST_MODE_CONFIRMATION),
            plan_file_sha256=override.get("plan_hash", p3.plan_file_sha256(package)),
            key_id=key_id, key_secret=key_secret,
            _provenance_reader=lambda _: override.get("provenance", provenance),
            _source_hash_reader=lambda _: override.get("hashes", hashes),
            _runtime_reader=lambda: override.get("runtime", runtime),
            _synthetic_transport=httpx.MockTransport(handler),
            _wall_clock=lambda: 1790200000,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
            _synthetic_test_execution=True,
        )

    return {"package": package, "facts": facts, "prepare": prepare,
            "execute": execute, "clock": clock, "provenance": provenance,
            "hashes": hashes, "runtime": runtime, "identity": synthetic_identity}


def test_frozen_hashes_and_exact_phase1_derivation():
    facts = p3.read_frozen_facts(ROOT)
    request = p3._frozen_request(facts)
    assert request.body_sha256 == p3.BODY_SHA256
    assert request.identity_sha256 == p3.IDENTITY_SHA256
    assert request.credential_scope_fingerprint == p3.SCOPE_SHA256
    assert json.loads(request.body) == {"amount": 200, "currency": "INR",
                                         "notes": {MARKER_KEY: p3.MARKER}}
    assert request.transport_profile == p3.DEFAULT_TRANSPORT_PROFILE
    for relative, digest in {**p3.p2.PHASE1_HASHES, **p3.PHASE2_HASHES}.items():
        assert sha256_hex((ROOT / relative).read_bytes()) == digest


def test_socket_guard_active():
    sock = socket.socket()
    try:
        with pytest.raises(BaseException, match="external socket/network use prohibited"):
            sock.connect(("203.0.113.1", 443))
    finally:
        sock.close()


def test_prepare_plan_and_provenance(gate):
    plan = gate["prepare"]()
    package = gate["package"]
    assert {p.name for p in package.iterdir()} == {p3.PLAN_FILENAME}
    assert plan["phase"] == 3 and plan["paper_observations"] == 0
    assert plan["maximum_mutation_dispatches"] == plan["maximum_post_dispatches"] == 1
    assert plan["maximum_get_dispatches"] == 13
    assert plan["visibility_offsets_seconds"] == [0, 5, 30, 120, 600]
    assert plan["phase1_evidence_hashes"] == p3.p2.PHASE1_HASHES
    assert plan["phase2_evidence_hashes"] == p3.PHASE2_HASHES
    assert plan["request_body_sha256"] == p3.BODY_SHA256
    assert plan["request_identity_sha256"] == gate["identity"]
    assert plan["source_hashes"] == gate["hashes"]
    assert plan["git_head"] == plan["origin_main"] == HEAD
    assert plan["runtime_versions"] == gate["runtime"]
    raw = (package / p3.PLAN_FILENAME).read_bytes()
    assert p3.plan_file_sha256(package) == sha256_hex(raw)
    without_hash = dict(plan)
    without_hash.pop("plan_sha256")
    assert plan["plan_sha256"] == sha256_hex(canonical_json_bytes(without_hash))
    assert plan["package_location_sha256"] == p3.p2._location_hash(plan["qualification_id"], package)
    _assert_no_secrets(package)
    with pytest.raises(p3.QualificationError, match="package_already_exists"):
        gate["prepare"]()


def test_prepare_rejects_dirty_changed_head_runtime_and_inside_repo(gate):
    with pytest.raises(p3.QualificationError, match="working_tree_not_clean"):
        gate["prepare"](provenance={**gate["provenance"], "clean": False})
    with pytest.raises(p3.QualificationError, match="head_origin_main_mismatch"):
        gate["prepare"](provenance={**gate["provenance"], "origin_main": "b" * 40})
    with pytest.raises(p3.QualificationError, match="runtime_dependency_mismatch"):
        gate["prepare"](runtime={"httpx": "0.0"})
    with pytest.raises(p3.QualificationError, match="outside_repository"):
        p3.prepare_package(ROOT, ROOT / "forbidden-phase3-package")


def test_tamper_copy_and_changed_source_fail_before_traffic(gate, tmp_path):
    plan = gate["prepare"]()
    package = gate["package"]
    path = package / p3.PLAN_FILENAME
    original = p3.plan_file_sha256(package)
    changed = dict(plan)
    changed["maximum_get_dispatches"] = 14
    changed.pop("plan_sha256")
    changed["plan_sha256"] = sha256_hex(canonical_json_bytes(changed))
    path.write_bytes(canonical_json_bytes(changed) + b"\n")
    with pytest.raises(p3.QualificationError, match="plan_file_sha256_mismatch"):
        gate["execute"]([], plan_hash=original)
    with pytest.raises(p3.QualificationError, match="plan_invariant_mismatch"):
        gate["execute"]([], plan_hash=p3.plan_file_sha256(package))
    path.write_bytes(canonical_json_bytes(plan) + b"\n")
    copy = tmp_path / "copied"
    shutil.copytree(package, copy)
    with pytest.raises(p3.QualificationError, match="package_location_mismatch"):
        p3._load_plan(copy, p3.plan_file_sha256(copy), gate["facts"])
    with pytest.raises(p3.QualificationError, match="plan_source_hash_mismatch"):
        gate["execute"]([], hashes={**gate["hashes"], "src/retry_semantics/serialization.py": "0" * 64})
    with pytest.raises(p3.QualificationError, match="runtime_dependency_mismatch"):
        gate["execute"]([], runtime={"httpx": "0.0"})
    with pytest.raises(p3.QualificationError, match="plan_git_provenance_mismatch"):
        gate["execute"]([], provenance={"clean": True, "git_head": "b" * 40, "origin_main": "b" * 40})
    assert not (package / p3.INTENT_FILENAME).exists()


def test_frozen_evidence_tamper_fails(monkeypatch, tmp_path):
    root = tmp_path / "copy"
    for relative in {**p3.p2.PHASE1_HASHES, **p3.PHASE2_HASHES}:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    (root / "research/study2/razorpay/evidence/phase1/mutation_1.json").write_bytes(b"{}")
    with pytest.raises(p3.QualificationError, match="phase1_evidence_hash_mismatch"):
        p3.read_frozen_facts(root)
    (root / "research/study2/razorpay/evidence/phase1/mutation_1.json").write_bytes(
        (ROOT / "research/study2/razorpay/evidence/phase1/mutation_1.json").read_bytes())
    (root / "research/study2/razorpay/evidence/phase2/direct_fetch.json").write_bytes(b"{}")
    with pytest.raises(p3.QualificationError, match="phase2_evidence_hash_mismatch"):
        p3.read_frozen_facts(root)


def test_scope_mismatch_consumes_with_zero_calls(gate):
    gate["prepare"]()
    requests = []
    result = gate["execute"]([], key_secret="different_secret", record=requests)
    assert result.status is p3.TerminalStatus.LOCAL_PREFLIGHT_FAILED
    assert requests == [] and result.counts["total_get_dispatches"] == 0
    intent = _load(gate["package"], p3.INTENT_FILENAME)
    assert intent["observation_from"] == p3.ORIGINAL_FROM
    assert intent["observation_to"] == 1790200300
    _assert_no_secrets(gate["package"])
    with pytest.raises(p3.QualificationError, match="package_already_consumed"):
        gate["execute"]([])


@pytest.mark.parametrize("baseline,reason", [
    (_collection(()), "baseline_exact_set_not_observed"),
    (_collection((p3.ORIGINAL_ID, SECOND)), "baseline_unexpected_additional_match"),
    (b"not json", "baseline_observation_incomplete"),
    ({"entity": "collection", "items": [{"id": p3.ORIGINAL_ID, "entity": "order"}]},
     "baseline_observation_incomplete"),
])
def test_baseline_stops_before_post(gate, baseline, reason):
    gate["prepare"]()
    requests = []
    result = gate["execute"]([baseline], record=requests)
    assert result.status is p3.TerminalStatus.INCONCLUSIVE and result.reason == reason
    assert [r.method for r in requests] == ["GET"]
    assert not (gate["package"] / "replay_mutation.json").exists()


def test_exact_replay_distinct_and_immediate_visibility(gate):
    gate["prepare"]()
    requests = []
    result = gate["execute"]([
        _collection((p3.ORIGINAL_ID,)), _ack(), _direct(),
        _collection((p3.ORIGINAL_ID, SECOND)),
    ], record=requests)
    assert result.status is p3.TerminalStatus.RESOLVED
    assert result.multiplicity_result == "DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED"
    assert result.visibility_result == "EXACT_TWO_RESOURCE_SET_OBSERVED"
    assert [r.method for r in requests] == ["GET", "POST", "GET", "GET"]
    post = requests[1]
    assert sha256_hex(post.content) == p3.BODY_SHA256
    assert json.loads(post.content) == {"amount": 200, "currency": "INR",
                                        "notes": {MARKER_KEY: p3.MARKER}}
    replay = _load(gate["package"], "replay_mutation.json")
    assert replay["adapter_evidence"]["request_identity_sha256"] == gate["identity"]
    assert replay["adapter_evidence"]["classification"] == "ACKNOWLEDGED_CREATE"
    assert _load(gate["package"], p3.RESULT_FILENAME)["first_successful_scheduled_offset_seconds"] == 0
    assert not (gate["package"] / "visibility_round_5.json").exists()
    for request in (requests[0], requests[3]):
        assert request.url.params["from"] == str(p3.ORIGINAL_FROM)
        assert request.url.params["to"] == "1790200300"
        assert request.url.params["count"] == "100"
        assert request.url.params["skip"] == "0"
    _assert_no_secrets(gate["package"])


def test_intent_is_persisted_before_first_get(gate):
    gate["prepare"]()

    def baseline(_request):
        intent = _load(gate["package"], p3.INTENT_FILENAME)
        assert intent["session_consumed"] is True
        assert intent["observation_to"] == 1790200300
        return _collection(())

    result = gate["execute"]([baseline])
    assert result.reason == "baseline_exact_set_not_observed"


@pytest.mark.parametrize("mutation", [httpx.ReadTimeout("synthetic"), 400, 500,
                                    _ack(amount=201), b"not-json"])
def test_replay_unknown_never_retries_or_fetches(gate, mutation):
    gate["prepare"]()
    requests = []
    result = gate["execute"]([_collection((p3.ORIGINAL_ID,)), mutation], record=requests)
    assert result.status is p3.TerminalStatus.INCONCLUSIVE
    assert result.multiplicity_result == "UNRESOLVED"
    assert [r.method for r in requests] == ["GET", "POST"]
    assert result.counts["mutation_dispatches"] == result.counts["post_dispatches"] == 1
    assert not (gate["package"] / "direct_fetch_replay.json").exists()


@pytest.mark.parametrize("bad", [
    _direct(id="order_Wrong"), _direct(entity="payment"), _direct(amount=201),
    _direct(currency="USD"), _direct(receipt="abc"), _direct(notes=None),
    _direct(notes={}), _direct_without_notes(),
    _direct(notes={MARKER_KEY: "wrong"}), _direct(created_at="bad"),
    _direct(created_at=-1), 500, httpx.ReadTimeout("synthetic"), b"not-json",
])
def test_direct_fetch_validation_stops_rounds(gate, bad):
    gate["prepare"]()
    requests = []
    result = gate["execute"]([_collection((p3.ORIGINAL_ID,)), _ack(), bad], record=requests)
    assert result.status is p3.TerminalStatus.INCONCLUSIVE
    assert result.reason == "direct_fetch_not_validated"
    assert result.multiplicity_result == "DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED"
    assert [r.method for r in requests] == ["GET", "POST", "GET"]
    assert not list(gate["package"].glob("visibility_round_*.json"))


def test_direct_fetch_wrong_entity_stops_rounds(gate):
    gate["prepare"]()
    requests = []
    bad = _direct(entity="payment")
    result = gate["execute"]([_collection((p3.ORIGINAL_ID,)), _ack(), bad], record=requests)
    assert result.status is p3.TerminalStatus.INCONCLUSIVE
    assert result.reason == "direct_fetch_not_validated"
    assert result.multiplicity_result == "DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED"
    assert [r.method for r in requests] == ["GET", "POST", "GET"]
    assert not list(gate["package"].glob("visibility_round_*.json"))
    evidence = _load(gate["package"], "direct_fetch_replay.json")
    assert evidence["entity"] == "unexpected"
    assert evidence["validation_reason"] == "direct_fetch_not_validated"


def test_direct_fetch_notes_field_absent_stops_rounds(gate):
    gate["prepare"]()
    requests = []
    bad = _direct()
    bad.pop("notes")
    assert "notes" not in bad
    result = gate["execute"]([_collection((p3.ORIGINAL_ID,)), _ack(), bad], record=requests)
    assert result.status is p3.TerminalStatus.INCONCLUSIVE
    assert result.reason == "direct_fetch_not_validated"
    assert result.multiplicity_result == "DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED"
    assert [r.method for r in requests] == ["GET", "POST", "GET"]
    assert not list(gate["package"].glob("visibility_round_*.json"))
    evidence = _load(gate["package"], "direct_fetch_replay.json")
    assert evidence["exact_marker_match"] is False
    assert evidence["validation_reason"] == "direct_fetch_not_validated"


def test_unsafe_acknowledged_id_never_enters_get_path(gate):
    gate["prepare"]()
    requests = []
    result = gate["execute"]([_collection((p3.ORIGINAL_ID,)), _ack("order_bad/slash")],
                             record=requests)
    assert result.reason == "direct_fetch_not_validated"
    assert [r.method for r in requests] == ["GET", "POST"]
    assert _load(gate["package"], "direct_fetch_replay.json")["validation_reason"] == "unsafe_order_id"


def test_direct_fetch_created_at_above_upper_bound_stops_before_visibility(gate):
    gate["prepare"]()
    requests = []
    observation_to = 1790200000 + 300
    bad = _direct(created_at=observation_to + 1)
    result = gate["execute"]([_collection((p3.ORIGINAL_ID,)), _ack(), bad], record=requests)
    assert result.status is p3.TerminalStatus.INCONCLUSIVE
    assert result.reason == "replay_created_at_outside_fixed_window"
    assert result.multiplicity_result == "DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED"
    assert result.visibility_result == "NOT_REACHED"
    assert [r.method for r in requests] == ["GET", "POST", "GET"]
    assert not list(gate["package"].glob("visibility_round_*.json"))
    assert (gate["package"] / "direct_fetch_replay.json").exists()
    assert (gate["package"] / "replay_mutation.json").exists()
    fetch_evidence = _load(gate["package"], "direct_fetch_replay.json")
    assert fetch_evidence["validation_reason"] == "validated"
    assert fetch_evidence["provider_created_at"] == observation_to + 1


def test_direct_fetch_created_at_below_lower_bound_stops_before_visibility(gate):
    gate["prepare"]()
    requests = []
    bad = _direct(created_at=p3.ORIGINAL_FROM - 1)
    result = gate["execute"]([_collection((p3.ORIGINAL_ID,)), _ack(), bad], record=requests)
    assert result.status is p3.TerminalStatus.INCONCLUSIVE
    assert result.reason == "replay_created_at_outside_fixed_window"
    assert result.multiplicity_result == "DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED"
    assert result.visibility_result == "NOT_REACHED"
    assert [r.method for r in requests] == ["GET", "POST", "GET"]
    assert not list(gate["package"].glob("visibility_round_*.json"))
    assert (gate["package"] / "direct_fetch_replay.json").exists()
    assert (gate["package"] / "replay_mutation.json").exists()
    fetch_evidence = _load(gate["package"], "direct_fetch_replay.json")
    assert fetch_evidence["validation_reason"] == "validated"
    assert fetch_evidence["provider_created_at"] == p3.ORIGINAL_FROM - 1


def test_absolute_schedule_and_first_success_at_five(gate):
    gate["prepare"]()
    requests = []
    result = gate["execute"]([
        _collection((p3.ORIGINAL_ID,)), _ack(), _direct(),
        _collection((p3.ORIGINAL_ID,)), _collection((p3.ORIGINAL_ID, SECOND)),
    ], record=requests)
    assert result.status is p3.TerminalStatus.RESOLVED
    assert gate["clock"].sleeps == [5]
    assert _load(gate["package"], p3.RESULT_FILENAME)["first_successful_scheduled_offset_seconds"] == 5
    assert not (gate["package"] / "visibility_round_30.json").exists()
    assert result.counts["visibility_rounds_attempted"] == 2


def test_processing_time_uses_absolute_targets_without_unneeded_sleep(gate):
    gate["prepare"]()
    clock = gate["clock"]

    def acknowledge(_request):
        clock.now = 2
        return _ack()

    def direct(_request):
        clock.now += 4
        return _direct()

    def round_zero(_request):
        clock.now += 3
        return _collection((p3.ORIGINAL_ID,))

    def round_five(_request):
        clock.now += 1
        return _collection((p3.ORIGINAL_ID,))

    result = gate["execute"]([
        _collection((p3.ORIGINAL_ID,)), acknowledge, direct,
        round_zero, round_five, _collection((p3.ORIGINAL_ID, SECOND)),
    ])
    assert result.status is p3.TerminalStatus.RESOLVED
    assert clock.sleeps == [22]
    assert _load(gate["package"], p3.RESULT_FILENAME)["first_successful_scheduled_offset_seconds"] == 30


def test_bounded_miss_and_worst_case_counters(gate):
    gate["prepare"]()
    full = {"entity": "collection", "items": [
        {"id": p3.ORIGINAL_ID, "entity": "order", "notes": {MARKER_KEY: p3.MARKER}}
    ] + [{"id": f"order_Filler{i}", "entity": "order", "notes": {}}
         for i in range(99)]}
    stages = [full, _collection(), _ack(), _direct()]
    for _ in p3.OFFSETS:
        stages.extend((full, _collection()))
    requests = []
    result = gate["execute"](stages, record=requests)
    assert result.status is p3.TerminalStatus.INCONCLUSIVE
    assert result.visibility_result == "SECOND_RESOURCE_NOT_LIST_OBSERVED_WITHIN_BOUND"
    assert gate["clock"].sleeps == [5, 25, 90, 480]
    assert result.counts["baseline_get_dispatches"] == 2
    assert result.counts["direct_fetch_get_dispatches"] == 1
    assert result.counts["visibility_get_dispatches"] == 10
    assert result.counts["total_get_dispatches"] == 13
    assert result.counts["post_dispatches"] == 1
    assert len(requests) == 14
    for request in requests:
        if request.method == "GET" and request.url.path == "/v1/orders":
            assert request.url.params["from"] == str(p3.ORIGINAL_FROM)
            assert request.url.params["to"] == "1790200300"
            assert request.url.params["count"] == "100"
            assert request.url.params["skip"] in ("0", "100")
    assert not (gate["package"] / "visibility_round_601.json").exists()


@pytest.mark.parametrize("bad", [
    _collection(()), _collection((SECOND,)),
    _collection((p3.ORIGINAL_ID, SECOND, "order_Third")),
    b"bad-json",
])
def test_unexpected_or_incomplete_visibility_stops(gate, bad):
    gate["prepare"]()
    result = gate["execute"]([_collection((p3.ORIGINAL_ID,)), _ack(), _direct(), bad])
    assert result.status is p3.TerminalStatus.INCONCLUSIVE
    assert result.visibility_result in ("UNEXPECTED_OR_NONMONOTONIC_LIST_SET", "OBSERVATION_INCOMPLETE")
    assert result.counts["visibility_rounds_attempted"] == 1
    assert not (gate["package"] / "visibility_round_5.json").exists()


def test_same_id_remains_conservative(gate):
    gate["prepare"]()
    stages = [_collection((p3.ORIGINAL_ID,)), _ack(p3.ORIGINAL_ID),
              _direct(p3.ORIGINAL_ID)] + [_collection((p3.ORIGINAL_ID,)) for _ in p3.OFFSETS]
    result = gate["execute"](stages)
    assert result.status is p3.TerminalStatus.INCONCLUSIVE
    assert result.multiplicity_result == "SAME_RESOURCE_ID_ACKNOWLEDGED"
    assert result.visibility_result == "NO_DISTINCT_SECOND_RESOURCE_OBSERVED_UNDER_UNQUALIFIED_LIST"
    assert result.counts["visibility_rounds_completed"] == 5
    assert _load(gate["package"], p3.RESULT_FILENAME)["authoritative_completeness_qualified"] is False


def test_intent_exclusive_race_and_crash_no_refund(gate, monkeypatch):
    gate["prepare"]()
    original_write = p3.p2._write_exclusive_json
    barrier = Barrier(2)
    outcomes = []

    def race_write(path, value):
        if path.name == p3.INTENT_FILENAME:
            barrier.wait(timeout=5)
        return original_write(path, value)

    monkeypatch.setattr(p3.p2, "_write_exclusive_json", race_write)
    def run():
        try:
            return gate["execute"]([_collection(())])
        except p3.QualificationError as error:
            return error.reason
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: run(), range(2)))
    assert sum(x == "artifact_already_exists" for x in outcomes) == 1
    assert sum(isinstance(x, p3.ExecutionOutcome) for x in outcomes) == 1
    assert (gate["package"] / p3.INTENT_FILENAME).exists()
    with pytest.raises(p3.QualificationError, match="package_already_consumed"):
        gate["execute"]([])


def test_crash_after_intent_never_refunds_package(gate, monkeypatch):
    gate["prepare"]()
    original_write = p3.p2._write_exclusive_json

    def crash_on_baseline(path, value):
        if path.name == "baseline_observation.json":
            raise KeyboardInterrupt
        return original_write(path, value)

    monkeypatch.setattr(p3.p2, "_write_exclusive_json", crash_on_baseline)
    with pytest.raises(KeyboardInterrupt):
        gate["execute"]([_collection((p3.ORIGINAL_ID,))])
    monkeypatch.setattr(p3.p2, "_write_exclusive_json", original_write)
    assert (gate["package"] / p3.INTENT_FILENAME).exists()
    assert not (gate["package"] / p3.RESULT_FILENAME).exists()
    with pytest.raises(p3.QualificationError, match="package_already_consumed"):
        gate["execute"]([])


def test_cli_has_no_synthetic_or_credential_flags():
    parser = cli._parser()
    help_text = parser.format_help()
    assert "synthetic" not in help_text
    with pytest.raises(SystemExit):
        parser.parse_args(["execute", "--key-id", KEY_ID])


def test_cli_preflight_precedes_hidden_credential_prompt(monkeypatch, tmp_path):
    def refuse(*_args):
        raise p3.QualificationError("synthetic_preflight_refusal")

    def prompt(_message):
        pytest.fail("credential prompt happened before preflight")

    monkeypatch.setattr(cli, "preflight_package", refuse)
    monkeypatch.setattr(cli.getpass, "getpass", prompt)
    code = cli.main([
        "execute", "--repository-root", str(ROOT),
        "--package-dir", str(tmp_path / "absent"),
        "--execute-live-replay-visibility-qualification",
        "--confirmation", p3.CONFIRMATION,
        "--plan-file-sha256", "a" * 64,
        "--confirm-test-mode-credentials",
    ])
    assert code == 3


def test_production_rejects_synthetic_seam(gate):
    gate["prepare"]()
    with pytest.raises(p3.QualificationError, match="production_seam_injection_rejected"):
        p3.execute_package(
            ROOT, gate["package"],
            execute_live_replay_visibility_qualification=True,
            confirmation=p3.CONFIRMATION,
            test_mode_operator_confirmation=p3.TEST_MODE_CONFIRMATION,
            plan_file_sha256=p3.plan_file_sha256(gate["package"]),
            key_id=KEY_ID, key_secret=SECRET,
            _synthetic_transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        )
