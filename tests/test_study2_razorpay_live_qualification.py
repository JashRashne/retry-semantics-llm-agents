"""Hostile offline tests for the Razorpay live-qualification gate.

All provider behavior is supplied by httpx.MockTransport and the socket guard
makes any accidental external networking a hard failure.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import socket
import subprocess
from threading import Barrier, Lock
from types import SimpleNamespace

import httpx
import pytest

from scripts import qualify_study2_razorpay_live as qualification_cli
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.razorpay_adapter import (
    MARKER_KEY,
    RazorpayOrderAdapter,
)
from retry_semantics.study2 import razorpay_live_qualification as qualification_module
from retry_semantics.study2.razorpay_live_qualification import (
    CONFIRMATION,
    FROZEN_HASHES,
    INTENT_FILENAME,
    PLAN_FILENAME,
    RESULT_FILENAME,
    TEST_MODE_CONFIRMATION,
    QualificationError,
    TerminalStatus,
    execute_package,
    plan_file_sha256,
    prepare_package,
)


SYNTHETIC_KEY_ID = "rzp_test_synthetic_offline_only"
SYNTHETIC_SECRET = "synthetic_secret_NEVER_SEND"
SYNTHETIC_PROFILE = "synthetic_mocktransport_offline_v1"
HEAD = "a" * 40


@pytest.fixture(autouse=True)
def prohibit_external_sockets(monkeypatch):
    def blocked(*_args, **_kwargs):
        pytest.fail("external socket/network use prohibited")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def gate(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    package = tmp_path / "qualification-package"
    provenance = {"clean": True, "git_head": HEAD, "origin_main": HEAD}
    hashes = dict(FROZEN_HASHES)
    hashes.update(
        {
            "scripts/qualify_study2_razorpay_live.py": "1" * 64,
            "src/retry_semantics/serialization.py": "2" * 64,
            "src/retry_semantics/study2/razorpay_live_qualification.py": "3" * 64,
        }
    )
    runtime = {"httpx": "0.28.1"}

    def prepare(**overrides):
        return prepare_package(
            root,
            package,
            _provenance_reader=lambda _root: overrides.get("provenance", provenance),
            _source_hash_reader=lambda _root: overrides.get("hashes", hashes),
            _runtime_reader=lambda: overrides.get("runtime", runtime),
        )

    def execute(factory, **overrides):
        return execute_package(
            root,
            package,
            execute_live_qualification=overrides.get("live", True),
            confirmation=overrides.get("confirmation", CONFIRMATION),
            test_mode_operator_confirmation=overrides.get(
                "test_mode_confirmation", TEST_MODE_CONFIRMATION
            ),
            plan_file_sha256=overrides.get(
                "plan_hash",
                plan_file_sha256(package) if package.is_dir() else "0" * 64,
            ),
            key_id=overrides.get("key_id", SYNTHETIC_KEY_ID),
            key_secret=overrides.get("key_secret", SYNTHETIC_SECRET),
            _provenance_reader=lambda _root: overrides.get("provenance", provenance),
            _source_hash_reader=lambda _root: overrides.get("hashes", hashes),
            _runtime_reader=lambda: overrides.get("runtime", runtime),
            _test_adapter_factory=factory,
            _clock=lambda: 1_800_000_000.0,
            _synthetic_test_execution=True,
        )

    return {
        "root": root,
        "package": package,
        "provenance": provenance,
        "hashes": hashes,
        "runtime": runtime,
        "prepare": prepare,
        "execute": execute,
    }


def _order(order_id, marker):
    return {"entity": "order", "id": order_id, "notes": {MARKER_KEY: marker}}


def _ack(order_id, marker):
    return {
        "id": order_id,
        "entity": "order",
        "amount": 200,
        "currency": "INR",
        "status": "created",
        "attempts": 0,
        "amount_paid": 0,
        "notes": {MARKER_KEY: marker},
    }


def _response(request, value, status=200):
    return httpx.Response(status, json=value, request=request)


def _factory_for(plan, stages, record=None):
    lock = Lock()

    def factory(credentials):
        queue = list(stages)

        def handler(request):
            with lock:
                if record is not None:
                    record.setdefault("http_methods", []).append(request.method)
                item = queue.pop(0)
            if isinstance(item, BaseException):
                raise item
            kind, payload = item
            assert request.method == kind
            if callable(payload):
                payload = payload(request)
            if isinstance(payload, BaseException):
                raise payload
            if type(payload) is int:
                return _response(request, {"error": "synthetic"}, payload)
            return _response(request, payload)

        adapter = RazorpayOrderAdapter(
            credentials,
            timeout_seconds=30.0,
            transport=httpx.MockTransport(handler),
            transport_profile=SYNTHETIC_PROFILE,
        )
        if record is not None:
            original = adapter.dispatch_create_order

            def dispatch(request, permit):
                record.setdefault("request_object_ids", []).append(id(request))
                record.setdefault("body_objects", []).append(request.body)
                record.setdefault("permits", []).append(permit)
                return original(request, permit)

            adapter.dispatch_create_order = dispatch
        return adapter

    return factory


def _second_result_proxy_factory(plan, *, identity_mismatch=False, hide_dispatch=False):
    base_factory = _factory_for(plan, _pass_stages(plan["marker"]))

    def factory(credentials):
        adapter = base_factory(credentials)
        original = adapter.dispatch_create_order
        call_count = 0

        def dispatch(request, permit):
            nonlocal call_count
            call_count += 1
            result = original(request, permit)
            if call_count != 2:
                return result
            return SimpleNamespace(
                dispatch_started=(False if hide_dispatch else result.dispatch_started),
                classification=result.classification,
                provider_order_id=result.provider_order_id,
                request_identity_sha256=(
                    "f" * 64 if identity_mismatch else result.request_identity_sha256
                ),
                request_body_sha256=result.request_body_sha256,
                sanitized_evidence=result.sanitized_evidence,
            )

        adapter.dispatch_create_order = dispatch
        return adapter

    return factory


def _pass_stages(marker):
    return [
        ("GET", {"entity": "collection", "items": []}),
        ("POST", _ack("order_1", marker)),
        ("GET", {"entity": "collection", "items": [_order("order_1", marker)]}),
        ("POST", _ack("order_2", marker)),
        (
            "GET",
            {
                "entity": "collection",
                "items": [_order("order_1", marker), _order("order_2", marker)],
            },
        ),
    ]


def _read_json(path):
    return json.loads(path.read_text())


def test_direct_socket_attempt_is_blocked_by_module_guard():
    sock = socket.socket()
    try:
        with pytest.raises(BaseException, match="external socket/network use prohibited"):
            sock.connect(("203.0.113.1", 443))
    finally:
        sock.close()


def test_prepare_is_plan_only_exclusive_and_contains_frozen_invariants(gate):
    plan = gate["prepare"]()
    assert list(gate["package"].iterdir()) == [gate["package"] / PLAN_FILENAME]
    assert plan["engineering_only"] is True
    assert plan["paper_observations"] == 0
    assert plan["maximum_mutation_dispatches"] == 2
    assert plan["maximum_post_dispatches"] == 2
    assert plan["maximum_get_dispatches"] == 6
    assert plan["frozen_hashes"] == FROZEN_HASHES
    assert len(plan["plan_sha256"]) == 64
    assert len(plan["package_location_sha256"]) == 64
    text = (gate["package"] / PLAN_FILENAME).read_text()
    assert str(gate["package"]) not in text
    assert SYNTHETIC_SECRET not in text
    assert SYNTHETIC_KEY_ID not in text
    with pytest.raises(QualificationError, match="package_already_exists"):
        gate["prepare"]()


def test_prepare_rejects_package_inside_repository(gate):
    with pytest.raises(QualificationError, match="outside_repository"):
        prepare_package(
            gate["root"],
            gate["root"] / "package",
            _provenance_reader=lambda _: gate["provenance"],
            _source_hash_reader=lambda _: gate["hashes"],
            _runtime_reader=lambda: gate["runtime"],
        )


@pytest.mark.parametrize(
    "provenance,reason",
    [
        ({"clean": False, "git_head": HEAD, "origin_main": HEAD}, "working_tree_not_clean"),
        ({"clean": True, "git_head": "b" * 40, "origin_main": HEAD}, "head_origin_main_mismatch"),
    ],
)
def test_prepare_rejects_dirty_or_head_origin_mismatch(gate, provenance, reason):
    with pytest.raises(QualificationError, match=reason):
        gate["prepare"](provenance=provenance)


def test_prepare_rejects_frozen_hash_or_runtime_drift(gate):
    hashes = dict(gate["hashes"])
    hashes[next(iter(FROZEN_HASHES))] = "0" * 64
    with pytest.raises(QualificationError, match="frozen_source_hash_mismatch"):
        gate["prepare"](hashes=hashes)
    with pytest.raises(QualificationError, match="runtime_dependency_mismatch"):
        gate["prepare"](runtime={"httpx": "0.0.0"})


def test_prepare_cli_prints_canonical_path_and_both_plan_hashes(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "repo"
    root.mkdir()
    package = tmp_path / "package"
    plan = {"plan_sha256": "c" * 64, "qualification_id": "synthetic-id"}
    exact_bytes = b'{"synthetic":"plan"}\n'

    def fake_prepare(_root, destination):
        destination.mkdir()
        (destination / PLAN_FILENAME).write_bytes(exact_bytes)
        return plan

    monkeypatch.setattr(qualification_cli, "prepare_package", fake_prepare)
    assert qualification_cli.main(
        [
            "prepare",
            "--repository-root",
            str(root),
            "--package-dir",
            str(package),
        ]
    ) == 0
    output = capsys.readouterr().out
    assert f"PLAN_PATH={(package / PLAN_FILENAME).resolve()}" in output
    assert f"PLAN_FILE_SHA256={sha256_hex(exact_bytes)}" in output
    assert f"PLAN_CANONICAL_SHA256={'c' * 64}" in output
    assert "QUALIFICATION_ID=synthetic-id" in output
    assert SYNTHETIC_KEY_ID not in output and SYNTHETIC_SECRET not in output


def test_cli_has_no_synthetic_execution_mode(capsys):
    with pytest.raises(SystemExit):
        qualification_cli._parser().parse_args(
            [
                "execute",
                "--repository-root", "/tmp/repo",
                "--package-dir", "/tmp/package",
                "--execute-live-qualification",
                "--confirmation", CONFIRMATION,
                "--plan-file-sha256", "0" * 64,
                "--confirm-test-mode-credentials",
                "--synthetic-test-execution",
            ]
        )
    assert "unrecognized arguments: --synthetic-test-execution" in capsys.readouterr().err


def test_cli_requires_explicit_plan_file_hash(capsys):
    with pytest.raises(SystemExit):
        qualification_cli._parser().parse_args(
            [
                "execute",
                "--repository-root", "/tmp/repo",
                "--package-dir", "/tmp/package",
                "--execute-live-qualification",
                "--confirmation", CONFIRMATION,
                "--confirm-test-mode-credentials",
            ]
        )
    assert "--plan-file-sha256" in capsys.readouterr().err


def test_execute_rejects_plan_tampering_before_adapter_creation(gate):
    gate["prepare"]()
    path = gate["package"] / PLAN_FILENAME
    value = _read_json(path)
    value["amount"] = 201
    path.write_text(json.dumps(value))
    created = []
    with pytest.raises(QualificationError, match="plan_hash_mismatch"):
        gate["execute"](lambda credentials: created.append(credentials))
    assert created == []
    assert not (gate["package"] / INTENT_FILENAME).exists()


def test_rehashed_plan_invariant_tampering_is_still_rejected(gate):
    gate["prepare"]()
    path = gate["package"] / PLAN_FILENAME
    value = _read_json(path)
    value["maximum_get_dispatches"] = 600
    unhashed = dict(value)
    unhashed.pop("plan_sha256")
    value["plan_sha256"] = sha256_hex(canonical_json_bytes(unhashed))
    path.write_bytes(canonical_json_bytes(value) + b"\n")
    with pytest.raises(QualificationError, match="plan_invariant_mismatch"):
        gate["execute"](lambda credentials: None)


@pytest.mark.parametrize("field", ["marker", "qualification_id"])
def test_rehashed_valid_plan_field_still_fails_external_file_anchor(gate, field):
    gate["prepare"]()
    original_file_hash = plan_file_sha256(gate["package"])
    path = gate["package"] / PLAN_FILENAME
    value = _read_json(path)
    value[field] = (
        "study2_rehashed_marker" if field == "marker"
        else "11111111-1111-4111-8111-111111111111"
    )
    unhashed = dict(value)
    unhashed.pop("plan_sha256")
    value["plan_sha256"] = sha256_hex(canonical_json_bytes(unhashed))
    path.write_bytes(canonical_json_bytes(value) + b"\n")
    created = []
    with pytest.raises(QualificationError, match="plan_file_sha256_mismatch"):
        gate["execute"](
            lambda credentials: created.append(credentials),
            plan_hash=original_file_hash,
        )
    assert created == []
    assert not (gate["package"] / INTENT_FILENAME).exists()


def test_one_byte_plan_change_fails_external_file_anchor(gate):
    gate["prepare"]()
    expected = plan_file_sha256(gate["package"])
    path = gate["package"] / PLAN_FILENAME
    raw = path.read_bytes()
    path.write_bytes(raw[:-2] + b" " + raw[-1:])
    with pytest.raises(QualificationError, match="plan_file_sha256_mismatch"):
        gate["execute"](lambda credentials: None, plan_hash=expected)
    assert not (gate["package"] / INTENT_FILENAME).exists()


def test_wrong_or_malformed_expected_plan_hash_fails_before_intent_and_adapter(gate):
    gate["prepare"]()
    created = []
    with pytest.raises(QualificationError, match="plan_file_sha256_mismatch"):
        gate["execute"](
            lambda credentials: created.append(credentials), plan_hash="0" * 64
        )
    with pytest.raises(QualificationError, match="expected_plan_file_sha256_invalid"):
        gate["execute"](
            lambda credentials: created.append(credentials), plan_hash="NOT-A-HASH"
        )
    assert created == []
    assert not (gate["package"] / INTENT_FILENAME).exists()


def test_unexplained_preexecution_artifact_is_rejected(gate):
    gate["prepare"]()
    (gate["package"] / "unexpected.json").write_text("{}")
    with pytest.raises(QualificationError, match="package_not_pristine"):
        gate["execute"](lambda credentials: None)


def test_exact_plan_copied_to_second_outside_directory_is_rejected(gate, tmp_path):
    gate["prepare"]()
    copied = tmp_path / "copied-package"
    copied.mkdir()
    shutil.copy2(gate["package"] / PLAN_FILENAME, copied / PLAN_FILENAME)
    expected = plan_file_sha256(copied)
    created = []
    with pytest.raises(QualificationError, match="package_location_mismatch"):
        execute_package(
            gate["root"],
            copied,
            execute_live_qualification=True,
            confirmation=CONFIRMATION,
            test_mode_operator_confirmation=TEST_MODE_CONFIRMATION,
            plan_file_sha256=expected,
            key_id=SYNTHETIC_KEY_ID,
            key_secret=SYNTHETIC_SECRET,
            _provenance_reader=lambda _: gate["provenance"],
            _source_hash_reader=lambda _: gate["hashes"],
            _runtime_reader=lambda: gate["runtime"],
            _test_adapter_factory=lambda credentials: created.append(credentials),
            _clock=lambda: 1_800_000_000.0,
            _synthetic_test_execution=True,
        )
    assert created == []
    assert not (copied / INTENT_FILENAME).exists()


@pytest.mark.parametrize("directory_name", ["package", ".ignored/package"])
def test_execute_rejects_package_inside_repository_even_if_ignored(
    gate, directory_name
):
    gate["prepare"]()
    inside = gate["root"] / directory_name
    inside.mkdir(parents=True)
    shutil.copy2(gate["package"] / PLAN_FILENAME, inside / PLAN_FILENAME)
    with pytest.raises(QualificationError, match="outside_repository"):
        execute_package(
            gate["root"],
            inside,
            execute_live_qualification=True,
            confirmation=CONFIRMATION,
            test_mode_operator_confirmation=TEST_MODE_CONFIRMATION,
            plan_file_sha256=plan_file_sha256(inside),
            key_id=SYNTHETIC_KEY_ID,
            key_secret=SYNTHETIC_SECRET,
            _provenance_reader=lambda _: gate["provenance"],
            _source_hash_reader=lambda _: gate["hashes"],
            _runtime_reader=lambda: gate["runtime"],
            _test_adapter_factory=lambda credentials: None,
            _clock=lambda: 1_800_000_000.0,
            _synthetic_test_execution=True,
        )
    assert not (inside / INTENT_FILENAME).exists()


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"live": False}, "live_execution_flag_required"),
        ({"confirmation": "wrong"}, "confirmation_mismatch"),
        ({"test_mode_confirmation": "wrong"}, "test_mode_operator_confirmation_required"),
        ({"key_id": "rzp_live_synthetic"}, "live_looking_key_id_rejected"),
    ],
)
def test_authorization_and_test_mode_guards_precede_consumption(gate, overrides, reason):
    gate["prepare"]()
    with pytest.raises(QualificationError, match=reason):
        gate["execute"](lambda credentials: None, **overrides)
    assert not (gate["package"] / INTENT_FILENAME).exists()


def test_injected_adapter_without_synthetic_mode_is_rejected(gate):
    gate["prepare"]()
    created = []
    with pytest.raises(QualificationError, match="production_seam_injection_rejected"):
        execute_package(
            gate["root"], gate["package"],
            execute_live_qualification=True,
            confirmation=CONFIRMATION,
            test_mode_operator_confirmation=TEST_MODE_CONFIRMATION,
            plan_file_sha256=plan_file_sha256(gate["package"]),
            key_id=SYNTHETIC_KEY_ID,
            key_secret=SYNTHETIC_SECRET,
            _test_adapter_factory=lambda credentials: created.append(credentials),
        )
    assert created == []
    assert not (gate["package"] / INTENT_FILENAME).exists()


@pytest.mark.parametrize("seam", ["provenance", "source", "runtime", "clock"])
def test_injected_reader_or_clock_without_synthetic_mode_is_rejected(gate, seam):
    gate["prepare"]()
    kwargs = {}
    if seam == "provenance":
        kwargs["_provenance_reader"] = lambda _: gate["provenance"]
    elif seam == "source":
        kwargs["_source_hash_reader"] = lambda _: gate["hashes"]
    elif seam == "runtime":
        kwargs["_runtime_reader"] = lambda: gate["runtime"]
    else:
        kwargs["_clock"] = lambda: 1_800_000_000.0
    with pytest.raises(QualificationError, match="production_seam_injection_rejected"):
        execute_package(
            gate["root"], gate["package"],
            execute_live_qualification=True,
            confirmation=CONFIRMATION,
            test_mode_operator_confirmation=TEST_MODE_CONFIRMATION,
            plan_file_sha256=plan_file_sha256(gate["package"]),
            key_id=SYNTHETIC_KEY_ID,
            key_secret=SYNTHETIC_SECRET,
            **kwargs,
        )
    assert not (gate["package"] / INTENT_FILENAME).exists()


def test_true_preprovider_profile_failure_is_local_and_production_labeled(
    tmp_path, monkeypatch
):
    source_root = Path(__file__).resolve().parents[1]
    root = tmp_path / "production-repository"
    root.mkdir()
    paths = set(qualification_module.RELEVANT_SOURCE_PATHS) | set(FROZEN_HASHES)
    for relative in paths:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, destination)
    subprocess.run(("git", "init", "-q", str(root)), check=True)
    subprocess.run(
        ("git", "-C", str(root), "config", "user.email", "offline@example.test"),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(root), "config", "user.name", "Offline Test"),
        check=True,
    )
    subprocess.run(("git", "-C", str(root), "add", "."), check=True)
    subprocess.run(
        ("git", "-C", str(root), "commit", "-qm", "qualification source"),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(root), "branch", "origin/main"), check=True
    )
    package = tmp_path / "production-package"
    prepare_package(root, package)
    provider_calls = []

    class MismatchedProfileAdapter:
        def __init__(self, credentials, *, timeout_seconds):
            self._inner = RazorpayOrderAdapter(
                credentials,
                timeout_seconds=timeout_seconds,
                transport=httpx.MockTransport(
                    lambda request: provider_calls.append(request)
                ),
                transport_profile=SYNTHETIC_PROFILE,
            )

        def prepare_create_order(self, marker):
            return self._inner.prepare_create_order(marker)

        def close(self):
            self._inner.close()

    monkeypatch.setattr(
        qualification_module, "RazorpayOrderAdapter", MismatchedProfileAdapter
    )
    outcome = execute_package(
        root,
        package,
        execute_live_qualification=True,
        confirmation=CONFIRMATION,
        test_mode_operator_confirmation=TEST_MODE_CONFIRMATION,
        plan_file_sha256=plan_file_sha256(package),
        key_id=SYNTHETIC_KEY_ID,
        key_secret=SYNTHETIC_SECRET,
    )
    assert outcome.status is TerminalStatus.LOCAL_PREFLIGHT_FAILED
    assert outcome.reason == "audited_transport_profile_not_pinned"
    assert provider_calls == []
    intent = _read_json(package / INTENT_FILENAME)
    result = _read_json(package / RESULT_FILENAME)
    for evidence in (intent, result):
        assert evidence["synthetic_test_execution"] is False
        assert evidence["live_qualification_evidence"] is True
    assert result["counts"]["get_dispatches"] == 0
    assert result["counts"]["mutation_dispatches"] == 0


def test_missing_package_rejected(gate):
    with pytest.raises(QualificationError, match="package_missing"):
        gate["execute"](lambda credentials: None)


@pytest.mark.parametrize(
    "drift,reason",
    [
        ("dirty", "working_tree_not_clean"),
        ("head", "plan_git_head_mismatch"),
        ("origin", "head_origin_main_mismatch"),
        ("source", "plan_source_hash_mismatch"),
        ("runtime", "runtime_dependency_mismatch"),
    ],
)
def test_execute_rejects_all_provenance_drift_before_consumption(gate, drift, reason):
    gate["prepare"]()
    kwargs = {}
    if drift == "dirty":
        kwargs["provenance"] = {"clean": False, "git_head": HEAD, "origin_main": HEAD}
    elif drift == "head":
        kwargs["provenance"] = {"clean": True, "git_head": "b" * 40, "origin_main": "b" * 40}
    elif drift == "origin":
        kwargs["provenance"] = {"clean": True, "git_head": HEAD, "origin_main": "b" * 40}
    elif drift == "source":
        hashes = dict(gate["hashes"])
        hashes["src/retry_semantics/serialization.py"] = "f" * 64
        kwargs["hashes"] = hashes
    else:
        kwargs["runtime"] = {"httpx": "0.28.0"}
    with pytest.raises(QualificationError, match=reason):
        gate["execute"](lambda credentials: None, **kwargs)
    assert not (gate["package"] / INTENT_FILENAME).exists()


def test_pass_sequence_reuses_same_frozen_object_and_new_permits(gate):
    plan = gate["prepare"]()
    record = {}
    outcome = gate["execute"](_factory_for(plan, _pass_stages(plan["marker"]), record))
    assert outcome.status is TerminalStatus.PASS
    assert record["http_methods"] == ["GET", "POST", "GET", "POST", "GET"]
    assert record["request_object_ids"][0] == record["request_object_ids"][1]
    assert record["body_objects"][0] is record["body_objects"][1]
    assert record["permits"][0] is not record["permits"][1]
    assert all(permit.consumed for permit in record["permits"])
    assert outcome.mutation_dispatches == 2
    assert outcome.baseline_observation_sequences == 1
    assert outcome.post_create_observation_sequences == 2
    result = _read_json(gate["package"] / RESULT_FILENAME)
    assert result["synthetic_test_execution"] is True
    assert result["live_qualification_evidence"] is False
    assert result["counts"]["get_dispatches"] == 3
    assert result["plan_file_sha256"] == plan_file_sha256(gate["package"])
    assert result["package_location_sha256"] == plan["package_location_sha256"]
    assert sorted(path.name for path in gate["package"].iterdir()) == [
        "baseline_observation.json",
        "intent.json",
        "mutation_1.json",
        "mutation_2.json",
        "observation_1.json",
        "observation_2.json",
        "qualification_plan.json",
        "qualification_result.json",
    ]
    for path in gate["package"].glob("*.json"):
        if path.name == PLAN_FILENAME:
            continue
        evidence = _read_json(path)
        assert evidence["synthetic_test_execution"] is True
        assert evidence["live_qualification_evidence"] is False


def test_synthetic_mode_rejects_default_provider_transport_before_any_request(gate):
    gate["prepare"]()
    outcome = gate["execute"](
        lambda credentials: RazorpayOrderAdapter(credentials, timeout_seconds=30.0)
    )
    assert outcome.status is TerminalStatus.LOCAL_PREFLIGHT_FAILED
    assert outcome.reason == "synthetic_default_transport_rejected"
    result = _read_json(gate["package"] / RESULT_FILENAME)
    assert result["counts"]["get_dispatches"] == 0
    assert result["counts"]["mutation_dispatches"] == 0
    assert not (gate["package"] / "baseline_observation.json").exists()


def test_intent_exists_and_was_fsynced_before_first_provider_invocation(gate, monkeypatch):
    plan = gate["prepare"]()
    fsync_calls = []
    original_fsync = __import__("os").fsync

    def fsync(descriptor):
        fsync_calls.append(descriptor)
        return original_fsync(descriptor)

    monkeypatch.setattr("os.fsync", fsync)
    observed = {}

    def factory(credentials):
        observed["intent_at_factory"] = (gate["package"] / INTENT_FILENAME).exists()
        return _factory_for(plan, _pass_stages(plan["marker"]))(credentials)

    outcome = gate["execute"](factory)
    assert outcome.status is TerminalStatus.PASS
    assert observed["intent_at_factory"] is True
    assert fsync_calls


def test_consumed_package_cannot_execute_twice(gate):
    plan = gate["prepare"]()
    gate["execute"](_factory_for(plan, _pass_stages(plan["marker"])))
    second_factory_calls = []
    with pytest.raises(QualificationError, match="already_consumed"):
        gate["execute"](lambda credentials: second_factory_calls.append(credentials))
    assert second_factory_calls == []


def test_crash_after_intent_does_not_refund_session(gate):
    gate["prepare"]()

    def crashing_factory(_credentials):
        raise RuntimeError(SYNTHETIC_SECRET)

    outcome = gate["execute"](crashing_factory)
    assert outcome.status is TerminalStatus.INCONCLUSIVE
    assert outcome.reason == "unexpected_local_exception"
    with pytest.raises(QualificationError, match="already_consumed"):
        gate["execute"](crashing_factory)


def test_two_executors_race_and_only_one_can_reach_transport(gate):
    plan = gate["prepare"]()
    barrier = Barrier(2)
    calls = []
    calls_lock = Lock()

    def provenance(_root):
        barrier.wait()
        return gate["provenance"]

    def factory(credentials):
        base = _factory_for(plan, _pass_stages(plan["marker"]))(credentials)
        original = base._client._transport.handle_request

        def handler(request):
            with calls_lock:
                calls.append(request.method)
            return original(request)

        base._client._transport.handle_request = handler
        return base

    def run():
        try:
            return execute_package(
                gate["root"], gate["package"],
                execute_live_qualification=True,
                confirmation=CONFIRMATION,
                test_mode_operator_confirmation=TEST_MODE_CONFIRMATION,
                plan_file_sha256=plan_file_sha256(gate["package"]),
                key_id=SYNTHETIC_KEY_ID,
                key_secret=SYNTHETIC_SECRET,
                _provenance_reader=provenance,
                _source_hash_reader=lambda _: gate["hashes"],
                _runtime_reader=lambda: gate["runtime"],
                _test_adapter_factory=factory,
                _clock=lambda: 1_800_000_000.0,
                _synthetic_test_execution=True,
            )
        except QualificationError as error:
            return error.reason

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in (pool.submit(run), pool.submit(run))]
    assert sum(hasattr(result, "status") for result in results) == 1
    assert len([result for result in results if isinstance(result, str)]) == 1
    assert calls == ["GET", "POST", "GET", "POST", "GET"]


@pytest.mark.parametrize(
    "baseline,status,reason",
    [
        ({"entity": "collection", "items": [_order("old", "MARKER")]}, TerminalStatus.NON_PASS, "baseline_marker_collision"),
        ({"bad": "shape"}, TerminalStatus.INCONCLUSIVE, "baseline_observation_incomplete"),
    ],
)
def test_baseline_failures_dispatch_no_mutation(gate, baseline, status, reason):
    plan = gate["prepare"]()
    if baseline.get("items"):
        baseline["items"][0]["notes"][MARKER_KEY] = plan["marker"]
    record = {}
    outcome = gate["execute"](_factory_for(plan, [("GET", baseline)], record))
    assert outcome.status is status and outcome.reason == reason
    assert record["http_methods"] == ["GET"]
    assert outcome.mutation_dispatches == 0


@pytest.mark.parametrize(
    "mutation",
    [
        400,
        httpx.ReadTimeout("synthetic"),
        {"entity": "order", "id": "invalid_ack"},
    ],
)
def test_create_1_failure_stops_after_one_mutation(gate, mutation):
    plan = gate["prepare"]()
    record = {}
    stages = [("GET", {"entity": "collection", "items": []}), ("POST", mutation)]
    outcome = gate["execute"](_factory_for(plan, stages, record))
    assert outcome.status is TerminalStatus.INCONCLUSIVE
    assert outcome.reason == "mutation_1_not_acknowledged"
    assert record["http_methods"] == ["GET", "POST"]
    assert outcome.mutation_dispatches == 1


@pytest.mark.parametrize(
    "items",
    [
        [],
        [_order("wrong", "MARKER")],
        [_order("order_1", "MARKER"), _order("extra", "MARKER")],
    ],
)
def test_observe_1_non_exact_set_prevents_second_mutation(gate, items):
    plan = gate["prepare"]()
    for item in items:
        item["notes"][MARKER_KEY] = plan["marker"]
    record = {}
    stages = [
        ("GET", {"entity": "collection", "items": []}),
        ("POST", _ack("order_1", plan["marker"])),
        ("GET", {"entity": "collection", "items": items}),
    ]
    outcome = gate["execute"](_factory_for(plan, stages, record))
    assert outcome.status is TerminalStatus.INCONCLUSIVE
    assert record["http_methods"] == ["GET", "POST", "GET"]
    assert outcome.mutation_dispatches == 1


@pytest.mark.parametrize(
    "second,status,reason",
    [
        (lambda marker: _ack("order_1", marker), TerminalStatus.NON_PASS, "mutation_2_reused_provider_id"),
        (lambda marker: 400, TerminalStatus.INCONCLUSIVE, "mutation_2_not_acknowledged"),
        (lambda marker: httpx.ReadTimeout("synthetic"), TerminalStatus.INCONCLUSIVE, "mutation_2_not_acknowledged"),
    ],
)
def test_create_2_failures_never_dispatch_third_mutation(gate, second, status, reason):
    plan = gate["prepare"]()
    record = {}
    stages = [
        ("GET", {"entity": "collection", "items": []}),
        ("POST", _ack("order_1", plan["marker"])),
        ("GET", {"entity": "collection", "items": [_order("order_1", plan["marker"])]}),
        ("POST", second(plan["marker"])),
    ]
    outcome = gate["execute"](_factory_for(plan, stages, record))
    assert outcome.status is status and outcome.reason == reason
    assert record["http_methods"].count("POST") == 2
    assert outcome.mutation_dispatches == 2
    assert not (gate["package"] / "observation_2.json").exists()


def test_post_dispatch_request_identity_failure_is_inconclusive(gate):
    plan = gate["prepare"]()
    outcome = gate["execute"](
        _second_result_proxy_factory(plan, identity_mismatch=True)
    )
    result = _read_json(gate["package"] / RESULT_FILENAME)
    assert outcome.status is TerminalStatus.INCONCLUSIVE
    assert outcome.reason == "post_dispatch_request_identity_invariant_failed"
    assert outcome.mutation_dispatches == 2
    assert result["status"] == "INCONCLUSIVE"
    assert result["counts"]["mutation_dispatches"] == 2
    assert (gate["package"] / "mutation_2.json").exists()
    assert not (gate["package"] / "observation_2.json").exists()


def test_post_dispatch_counter_failure_is_inconclusive(gate):
    plan = gate["prepare"]()
    outcome = gate["execute"](
        _second_result_proxy_factory(plan, hide_dispatch=True)
    )
    result = _read_json(gate["package"] / RESULT_FILENAME)
    mutation_2 = _read_json(gate["package"] / "mutation_2.json")
    assert outcome.status is TerminalStatus.INCONCLUSIVE
    assert outcome.reason == "post_dispatch_counter_invariant_failed"
    assert result["status"] == "INCONCLUSIVE"
    assert result["counts"]["post_create_observation_sequences"] == 2
    assert result["counts"]["get_dispatches"] == 3
    assert mutation_2["adapter_evidence"]["dispatch_started"] is True
    assert (gate["package"] / "observation_2.json").exists()


@pytest.mark.parametrize(
    "ids,status",
    [
        ([], TerminalStatus.INCONCLUSIVE),
        (["order_1"], TerminalStatus.INCONCLUSIVE),
        (["order_2"], TerminalStatus.INCONCLUSIVE),
        (["order_1", "order_2", "order_3"], TerminalStatus.NON_PASS),
        (["order_1", "unexpected"], TerminalStatus.NON_PASS),
    ],
)
def test_observe_2_requires_exact_two_expected_ids(gate, ids, status):
    plan = gate["prepare"]()
    stages = _pass_stages(plan["marker"])
    stages[-1] = (
        "GET",
        {"entity": "collection", "items": [_order(item, plan["marker"]) for item in ids]},
    )
    outcome = gate["execute"](_factory_for(plan, stages))
    assert outcome.status is status
    assert outcome.reason == "observation_2_exact_set_not_observed"
    assert outcome.mutation_dispatches == 2


def test_malformed_observation_2_is_inconclusive(gate):
    plan = gate["prepare"]()
    stages = _pass_stages(plan["marker"])
    stages[-1] = ("GET", {"bad": "shape"})
    outcome = gate["execute"](_factory_for(plan, stages))
    assert outcome.status is TerminalStatus.INCONCLUSIVE
    assert outcome.reason == "observation_2_incomplete"


def test_persisted_artifacts_exclude_credentials_authorization_and_exception_text(gate):
    plan = gate["prepare"]()
    stages = [
        ("GET", {"entity": "collection", "items": []}),
        ("POST", httpx.ReadTimeout(SYNTHETIC_SECRET)),
    ]
    gate["execute"](_factory_for(plan, stages))
    persisted = b"".join(path.read_bytes() for path in gate["package"].iterdir())
    assert SYNTHETIC_SECRET.encode() not in persisted
    assert SYNTHETIC_KEY_ID.encode() not in persisted
    assert b"Authorization" not in persisted
    assert b"Basic " not in persisted
    intent = _read_json(gate["package"] / INTENT_FILENAME)
    assert intent["session_consumed"] is True
    assert intent["maximum_mutation_dispatches"] == 2


def test_evidence_records_windows_pages_skips_statuses_and_unqualified_completeness(gate):
    plan = gate["prepare"]()
    gate["execute"](_factory_for(plan, _pass_stages(plan["marker"])))
    evidence = _read_json(gate["package"] / "observation_2.json")
    assert evidence["from_timestamp"] == 1_799_999_700
    assert evidence["to_timestamp"] == 1_800_000_300
    assert evidence["boundary_semantics_qualified"] is False
    assert evidence["adapter_evidence"]["page_skips"] == [0]
    assert evidence["adapter_evidence"]["http_statuses"] == [200]
    assert evidence["adapter_evidence"]["pages_requested"] == 1
    assert evidence["adapter_evidence"]["authoritative_completeness_qualified"] is False
    assert evidence["total_returned_order_items_encountered"] is None


def test_untracked_file_is_dirty_under_real_git_porcelain(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(("git", "init", "-q", str(root)), check=True)
    subprocess.run(("git", "-C", str(root), "config", "user.email", "offline@example.test"), check=True)
    subprocess.run(("git", "-C", str(root), "config", "user.name", "Offline Test"), check=True)
    (root / "tracked").write_text("x")
    subprocess.run(("git", "-C", str(root), "add", "tracked"), check=True)
    subprocess.run(("git", "-C", str(root), "commit", "-qm", "initial"), check=True)
    subprocess.run(("git", "-C", str(root), "branch", "origin/main"), check=True)
    (root / "untracked").write_text("x")
    from retry_semantics.study2.razorpay_live_qualification import read_git_provenance

    assert read_git_provenance(root)["clean"] is False


def test_result_artifact_is_terminal_and_study_state_remains_engineering_only(gate):
    plan = gate["prepare"]()
    outcome = gate["execute"](_factory_for(plan, _pass_stages(plan["marker"])))
    result = _read_json(gate["package"] / RESULT_FILENAME)
    assert outcome.status is TerminalStatus.PASS
    assert result["engineering_only"] is True
    assert result["paper_observations"] == 0
    assert result["provider_c_selection"] == "not_performed"
    assert result["authoritative_completeness_qualified"] is False
