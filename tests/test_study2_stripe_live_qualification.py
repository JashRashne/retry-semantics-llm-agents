"""Hostile offline tests for the Stripe live qualification gate."""

import json
from pathlib import Path
import socket
import threading

import httpx
import pytest

import retry_semantics.study2.stripe_live_qualification as gate
from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2.stripe_adapter import StripeCustomerAdapter


HEAD = "1" * 40
ORIGIN = HEAD
RAW_CREDENTIAL = "rk_test_OFFLINE_ONLY_qualification_secret"
QID = "stripe-eng-0123456789abcdef0123456789abcdef"
CREATED = "2026-09-22T10:00:00Z"
SOURCE_HASHES = {name: "3" * 64 for name in gate.RELEVANT_SOURCE_PATHS}


@pytest.fixture(autouse=True)
def forbid_external_sockets(monkeypatch):
    def prohibited(*_args, **_kwargs):
        raise AssertionError("qualification tests must not open sockets")

    monkeypatch.setattr(socket, "create_connection", prohibited)
    monkeypatch.setattr(socket.socket, "connect", prohibited)


def customer(customer_id="cus_One", *, email=f"{QID}@retry-semantics.invalid", livemode=False):
    return {"id": customer_id, "object": "customer", "email": email, "livemode": livemode}


def page(customers=(), *, has_more=False):
    return {"object": "list", "data": list(customers), "has_more": has_more}


class RecordingTransport:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        status, payload, headers = outcome
        if isinstance(payload, bytes):
            return httpx.Response(status, content=payload, headers=headers)
        return httpx.Response(status, json=payload, headers=headers)


def response(status, payload, headers=()):
    return status, payload, headers


@pytest.fixture
def frozen_plan():
    return gate.build_plan(
        qualification_id=QID,
        git_head=HEAD,
        origin_main=ORIGIN,
        source_sha256=SOURCE_HASHES,
        created_at=CREATED,
    )


@pytest.fixture
def package(tmp_path, frozen_plan, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    package_dir = tmp_path / "qualification"
    package_dir.mkdir(mode=0o700)
    gate._write_exclusive_json(package_dir / gate.PLAN_FILENAME, frozen_plan)
    monkeypatch.setattr(gate, "_repository_state", lambda _root: (HEAD, ORIGIN, ""))
    monkeypatch.setattr(gate, "_source_hashes", lambda _root: dict(SOURCE_HASHES))
    monkeypatch.setattr(gate, "_httpx_runtime_version", lambda: gate.REVIEWED_HTTPX_VERSION)
    return root, package_dir, frozen_plan


def execute(package, transport, **changes):
    root, package_dir, plan = package
    values = {
        "expected_plan_sha256": plan["plan_sha256"],
        "execute_live_qualification": True,
        "operator_confirmation": gate.EXECUTE_CONFIRMATION,
        "repository_root": root,
        "credential_reader": lambda: RAW_CREDENTIAL,
        "adapter_factory": lambda credential: StripeCustomerAdapter(
            credential, transport=transport.transport
        ),
    }
    values.update(changes)
    return gate.execute_qualification(package_dir / gate.PLAN_FILENAME, **values)


def persisted(package_dir, name):
    return json.loads((package_dir / name).read_text(encoding="utf-8"))


def test_plan_is_deterministic_for_frozen_material_and_has_required_scope(frozen_plan):
    second = gate.build_plan(
        qualification_id=QID,
        git_head=HEAD,
        origin_main=ORIGIN,
        source_sha256=SOURCE_HASHES,
        created_at=CREATED,
    )
    assert frozen_plan == second
    assert canonical_json_bytes(frozen_plan) == canonical_json_bytes(second)
    assert frozen_plan["engineering_only"] is True
    assert frozen_plan["paper_observations"] == 0
    assert frozen_plan["git_head"] == HEAD
    assert frozen_plan["origin_main"] == ORIGIN
    assert frozen_plan["source_sha256"] == SOURCE_HASHES
    assert frozen_plan["reviewed_httpx_version"] == "0.28.1"
    assert frozen_plan["runtime_httpx_version"] == "0.28.1"
    assert frozen_plan["expected_maximum_post_dispatches"] == 1
    assert frozen_plan["cleanup"] == frozen_plan["mutation_retry"] == "prohibited"


def test_prepare_is_offline_exclusive_and_stores_no_credential(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    destination = tmp_path / "new-package"
    monkeypatch.setattr(gate, "_repository_state", lambda _root: (HEAD, ORIGIN, ""))
    monkeypatch.setattr(gate, "_source_hashes", lambda _root: dict(SOURCE_HASHES))
    monkeypatch.setattr(gate, "_httpx_runtime_version", lambda: gate.REVIEWED_HTTPX_VERSION)
    prepared = gate.prepare_qualification(
        destination,
        repository_root=root,
        qualification_id=QID,
        created_at=CREATED,
    )
    assert prepared.plan_path == destination / gate.PLAN_FILENAME
    assert set(destination.iterdir()) == {prepared.plan_path}
    assert RAW_CREDENTIAL.encode() not in prepared.plan_path.read_bytes()
    with pytest.raises(gate.StripeLiveQualificationError, match="already exists"):
        gate.prepare_qualification(destination, repository_root=root)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"expected_plan_sha256": "9" * 64}, "plan hash"),
        ({"execute_live_qualification": False}, "live qualification flag"),
        ({"operator_confirmation": "wrong"}, "operator confirmation"),
    ],
)
def test_authorization_failures_precede_credential_and_provider(package, change, message):
    called = []
    with pytest.raises(gate.StripeLiveQualificationError, match=message):
        execute(
            package,
            RecordingTransport(),
            credential_reader=lambda: called.append("credential") or RAW_CREDENTIAL,
            adapter_factory=lambda _credential: called.append("adapter"),
            **change,
        )
    assert called == []


def test_execute_refuses_source_head_origin_and_dirty_drift(package, monkeypatch):
    root, package_dir, plan = package
    cases = [
        (("4" * 40, "4" * 40, ""), SOURCE_HASHES, "HEAD differs"),
        ((HEAD, "5" * 40, ""), SOURCE_HASHES, "pushed origin/main"),
        ((HEAD, ORIGIN, " M tracked.py"), SOURCE_HASHES, "fully clean"),
        ((HEAD, ORIGIN, "?? untracked.py"), SOURCE_HASHES, "fully clean"),
        ((HEAD, ORIGIN, ""), {**SOURCE_HASHES, gate.RELEVANT_SOURCE_PATHS[0]: "6" * 64}, "source"),
    ]
    for state, hashes, message in cases:
        monkeypatch.setattr(gate, "_repository_state", lambda _root, value=state: value)
        monkeypatch.setattr(gate, "_source_hashes", lambda _root, value=hashes: value)
        called = []
        with pytest.raises(gate.StripeLiveQualificationError, match=message):
            gate.execute_qualification(
                package_dir / gate.PLAN_FILENAME,
                expected_plan_sha256=plan["plan_sha256"],
                execute_live_qualification=True,
                operator_confirmation=gate.EXECUTE_CONFIRMATION,
                repository_root=root,
                credential_reader=lambda: called.append("credential") or RAW_CREDENTIAL,
                adapter_factory=lambda _credential: called.append("adapter"),
            )
        assert called == []


def test_previously_consumed_or_unknown_package_state_refuses_before_provider(package):
    root, package_dir, plan = package
    gate._write_exclusive_json(package_dir / gate.INTENT_FILENAME, {"spent": True})
    called = []
    with pytest.raises(gate.StripeLiveQualificationError, match="consumed"):
        gate.execute_qualification(
            package_dir / gate.PLAN_FILENAME,
            expected_plan_sha256=plan["plan_sha256"],
            execute_live_qualification=True,
            operator_confirmation=gate.EXECUTE_CONFIRMATION,
            repository_root=root,
            credential_reader=lambda: called.append("credential") or RAW_CREDENTIAL,
            adapter_factory=lambda _credential: called.append("adapter"),
        )
    assert called == []


@pytest.mark.parametrize(
    "credential",
    ["rk_live_forbidden", "sk_live_forbidden", "pk_test_public", "pk_live_public", "unknown"],
)
def test_credential_prefixes_fail_closed_without_echo(package, credential):
    with pytest.raises(Exception) as captured:
        execute(package, RecordingTransport(), credential_reader=lambda: credential)
    assert credential not in str(captured.value) + repr(captured.value)
    assert not (package[1] / gate.INTENT_FILENAME).exists()


def test_cli_has_no_credential_argument_and_environment_is_not_read(monkeypatch):
    parser = gate._parser()
    help_text = parser.format_help()
    execute_help = parser._subparsers._group_actions[0].choices["execute"].format_help()
    assert "credential" not in (help_text + execute_help).lower()
    assert "stripe_api_key" not in (help_text + execute_help).lower()


def test_intent_is_durable_before_provider_boundary(package):
    observed = []

    class BoundaryTransport(RecordingTransport):
        def handle(self, request):
            intent = package[1] / gate.INTENT_FILENAME
            observed.append(persisted(package[1], gate.INTENT_FILENAME))
            assert intent.exists()
            return super().handle(request)

    transport = BoundaryTransport(response(200, customer()), response(200, page([customer()])))
    result = execute(package, transport)
    assert result["result"] == "PASS"
    assert observed[0]["dispatch_consumed"] is True
    assert observed[0]["intended_post_dispatch_budget"] == 1


def test_failed_intent_persistence_means_zero_provider_calls(package, monkeypatch):
    transport = RecordingTransport(response(200, customer()))
    original = gate._write_exclusive_json

    def fail_intent(path, value):
        if path.name == gate.INTENT_FILENAME:
            raise OSError("synthetic persistence failure")
        return original(path, value)

    monkeypatch.setattr(gate, "_write_exclusive_json", fail_intent)
    with pytest.raises(gate.StripeLiveQualificationError, match="failed closed"):
        execute(package, transport)
    assert transport.requests == []
    assert not (package[1] / gate.INTENT_FILENAME).exists()
    assert not (package[1] / gate.QUALIFICATION_RESULT_FILENAME).exists()


@pytest.mark.parametrize(
    "outcome",
    [httpx.ReadTimeout("synthetic"), httpx.ConnectError("synthetic")],
)
def test_transport_uncertainty_consumes_once_and_never_observes(package, outcome):
    transport = RecordingTransport(outcome, response(200, customer()))
    result = execute(package, transport)
    assert result["result"] == "NOT_PASS"
    assert result["real_stripe_create_dispatches"] == 1
    assert result["real_stripe_get_dispatches"] == 0
    assert len(transport.requests) == 1
    assert (package[1] / gate.INTENT_FILENAME).exists()
    with pytest.raises(gate.StripeLiveQualificationError, match="consumed"):
        execute(package, transport)
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "first",
    [
        response(200, b"not-json"),
        response(429, {"error": {}}),
        response(500, {"error": {}}),
        response(302, b"redirect", (("Location", "https://example.invalid"),)),
    ],
)
def test_malformed_429_5xx_and_redirect_never_retry_or_observe(package, first):
    transport = RecordingTransport(first, response(200, customer()))
    result = execute(package, transport)
    assert result["result"] == "NOT_PASS"
    assert result["validated_successful_creates"] == 0
    assert result["real_stripe_get_dispatches"] == 0
    assert len(transport.requests) == 1


def test_success_runs_one_exhaustive_multi_page_observation(package):
    transport = RecordingTransport(
        response(200, customer("cus_A"), (("Request-Id", "req_1"),)),
        response(200, page([customer("cus_A")], has_more=True)),
        response(200, page([], has_more=False)),
    )
    result = execute(package, transport)
    assert [request.method for request in transport.requests] == ["POST", "GET", "GET"]
    assert result["result"] == "PASS"
    assert result["real_stripe_create_dispatches"] == 1
    assert result["acknowledged_create_responses"] == 1
    assert result["validated_successful_creates"] == 1
    assert result["real_stripe_get_dispatches"] == 2
    assert result["complete_observations"] == 1
    assert result["matching_resource_count"] == 1
    assert result["additional_matching_resource_count"] == 0
    assert result["provider_request_id"] == "req_1"


@pytest.mark.parametrize(
    ("observation", "failure"),
    [
        (response(200, page([])), "matching_resource_count_not_one"),
        (response(200, page([customer("cus_One"), customer("cus_Two")])), "matching_resource_count_not_one"),
        (response(500, {"error": {}}), "unexpected_http_status"),
        (response(200, page([customer("cus_Different")])), "observed_customer_id_mismatch"),
    ],
)
def test_zero_multiple_incomplete_and_id_mismatch_fail(package, observation, failure):
    transport = RecordingTransport(response(200, customer("cus_One")), observation)
    result = execute(package, transport)
    assert result["result"] == "NOT_PASS"
    assert result["failure_reason"] == failure
    assert len([request for request in transport.requests if request.method == "POST"]) == 1


def test_all_evidence_is_sanitized_zero_paper_and_no_cleanup(package):
    transport = RecordingTransport(
        response(200, customer(), (("Request-Id", RAW_CREDENTIAL),)),
        response(200, page([customer()])),
    )
    result = execute(package, transport)
    package_bytes = b"".join(path.read_bytes() for path in package[1].iterdir())
    assert RAW_CREDENTIAL.encode() not in package_bytes
    assert b"Authorization" not in package_bytes
    assert all(json.loads(path.read_text())["paper_observations"] == 0 for path in package[1].iterdir())
    assert all(request.method != "DELETE" for request in transport.requests)
    assert result["paper_observations"] == 0
    assert result["engineering_only"] is True


def test_no_raw_credential_argument_or_environment_lookup_in_source():
    source = Path(gate.__file__).read_text(encoding="utf-8")
    assert "os.getenv" not in source
    assert "os.environ[\"STRIPE" not in source
    assert "add_argument(\"--credential" not in source
    assert "DELETE" not in source


def test_result_artifact_is_terminal_and_prevents_automatic_rerun(package):
    transport = RecordingTransport(response(200, customer()), response(200, page([customer()])))
    first = execute(package, transport)
    assert first["result"] == "PASS"
    with pytest.raises(gate.StripeLiveQualificationError, match="consumed"):
        execute(package, transport)
    assert len([request for request in transport.requests if request.method == "POST"]) == 1


def test_plan_tampering_is_rejected_before_provider(package):
    root, package_dir, plan = package
    tampered = {**plan, "paper_observations": 1}
    (package_dir / gate.PLAN_FILENAME).write_bytes(canonical_json_bytes(tampered) + b"\n")
    called = []
    with pytest.raises(gate.StripeLiveQualificationError):
        gate.execute_qualification(
            package_dir / gate.PLAN_FILENAME,
            expected_plan_sha256=plan["plan_sha256"],
            execute_live_qualification=True,
            operator_confirmation=gate.EXECUTE_CONFIRMATION,
            repository_root=root,
            credential_reader=lambda: called.append("credential") or RAW_CREDENTIAL,
            adapter_factory=lambda _credential: called.append("adapter"),
        )
    assert called == []


def test_engineering_idempotency_identity_is_unique_per_qualification():
    other_id = "stripe-eng-fedcba9876543210fedcba9876543210"
    first = gate.build_plan(
        qualification_id=QID,
        git_head=HEAD,
        origin_main=ORIGIN,
        source_sha256=SOURCE_HASHES,
        created_at=CREATED,
    )
    second = gate.build_plan(
        qualification_id=other_id,
        git_head=HEAD,
        origin_main=ORIGIN,
        source_sha256=SOURCE_HASHES,
        created_at=CREATED,
    )
    assert first["idempotency"]["key_identity_sha256"] != second["idempotency"]["key_identity_sha256"]
    assert first["correlation_email"] != second["correlation_email"]


@pytest.mark.parametrize("prefix", ["rk_test_", "sk_test_"])
def test_both_frozen_test_secret_prefixes_are_accepted(package, prefix):
    transport = RecordingTransport(response(200, customer()), response(200, page([customer()])))
    result = execute(package, transport, credential_reader=lambda: prefix + "SYNTHETIC_ACCEPTED")
    assert result["result"] == "PASS"


def test_process_interruption_after_boundary_persists_ambiguous_evidence(package):
    transport = RecordingTransport(KeyboardInterrupt())
    result = execute(package, transport)
    mutation = persisted(package[1], gate.MUTATION_RESULT_FILENAME)
    assert result["result"] == "NOT_PASS"
    assert result["failure_reason"] == "exception_after_create_dispatch_boundary_entered"
    assert mutation["remote_outcome"] == "unknown_ambiguous"
    assert mutation["dispatch_lifecycle"] == "dispatch_initiated"
    assert len(transport.requests) == 1


def test_observation_evidence_failure_records_actual_get_counters(package, monkeypatch):
    transport = RecordingTransport(response(200, customer()), response(200, page([customer()])))
    original = gate._write_exclusive_json

    def fail_observation(path, value):
        if path.name == gate.OBSERVATION_RESULT_FILENAME:
            raise OSError("synthetic observation persistence failure")
        return original(path, value)

    monkeypatch.setattr(gate, "_write_exclusive_json", fail_observation)
    result = execute(package, transport)
    stored = persisted(package[1], gate.QUALIFICATION_RESULT_FILENAME)
    assert result["result"] == "NOT_PASS"
    assert stored["real_stripe_get_dispatches"] == 1
    assert stored["complete_observations"] == 1


def test_credential_reader_exception_cannot_escape_secret_text(package):
    leaked = "sk_test_MUST_NOT_ESCAPE_FROM_EXCEPTION"

    def fail_reader():
        raise RuntimeError(leaked)

    with pytest.raises(gate.StripeLiveQualificationError) as captured:
        execute(package, RecordingTransport(), credential_reader=fail_reader)
    assert leaked not in str(captured.value) + repr(captured.value)
    assert captured.value.__context__ is None


def test_execute_requires_private_package_permissions(package):
    package[1].chmod(0o755)
    with pytest.raises(gate.StripeLiveQualificationError, match="private"):
        execute(package, RecordingTransport())


def test_noncanonical_plan_is_rejected(package):
    plan_path = package[1] / gate.PLAN_FILENAME
    plan_path.write_text(json.dumps(package[2], indent=2) + "\n", encoding="utf-8")
    with pytest.raises(gate.StripeLiveQualificationError, match="noncanonical"):
        execute(package, RecordingTransport())


def test_single_post_contains_engineering_key_and_email_only(package):
    transport = RecordingTransport(response(200, customer()), response(200, page([customer()])))
    execute(package, transport)
    post = transport.requests[0]
    assert post.method == "POST"
    assert post.headers["Idempotency-Key"].startswith("retry-semantics-stripe-engineering-v1-")
    assert post.content == f"email={QID}%40retry-semantics.invalid".encode("ascii")
    assert b"test_clock" not in post.content


def test_runtime_introduces_no_experimental_policy_execution():
    source = Path(gate.__file__).read_text(encoding="utf-8")
    for prohibited in ("Replay", "Regeneration", "H0", "H1", "trial_family", "paper_manifest"):
        assert prohibited not in source


def test_partial_intent_residue_never_grants_evidence_ownership(package, monkeypatch):
    transport = RecordingTransport(response(200, customer()))
    original = gate._write_exclusive_json

    def fail_after_intent_fsync(path, value):
        original(path, value)
        if path.name == gate.INTENT_FILENAME:
            raise OSError("synthetic post-fsync failure")

    monkeypatch.setattr(gate, "_write_exclusive_json", fail_after_intent_fsync)
    with pytest.raises(gate.StripeLiveQualificationError, match="failed closed"):
        execute(package, transport)
    assert transport.requests == []
    assert (package[1] / gate.INTENT_FILENAME).exists()
    assert not (package[1] / gate.QUALIFICATION_RESULT_FILENAME).exists()


def test_two_executors_have_one_intent_owner_and_one_post(package):
    root, package_dir, plan = package
    start_claim = threading.Barrier(2)
    loser_finished = threading.Event()
    requests = []
    request_lock = threading.Lock()
    results = []
    errors = []
    credentials = ["rk_test_RACE_OWNER_A", "rk_test_RACE_OWNER_B"]

    def handler(request):
        with request_lock:
            requests.append(request)
        if request.method == "POST":
            assert loser_finished.wait(5)
            assert {path.name for path in package_dir.iterdir()} == {
                gate.PLAN_FILENAME,
                gate.INTENT_FILENAME,
            }
            return httpx.Response(200, json=customer())
        return httpx.Response(200, json=page([customer()]))

    def adapter_factory(credential):
        adapter = StripeCustomerAdapter(
            credential, transport=httpx.MockTransport(handler)
        )
        start_claim.wait(timeout=5)
        return adapter

    def worker(index):
        try:
            value = gate.execute_qualification(
                package_dir / gate.PLAN_FILENAME,
                expected_plan_sha256=plan["plan_sha256"],
                execute_live_qualification=True,
                operator_confirmation=gate.EXECUTE_CONFIRMATION,
                repository_root=root,
                credential_reader=lambda: credentials[index],
                adapter_factory=adapter_factory,
            )
            results.append((index, value))
        except gate.StripeLiveQualificationError as exc:
            errors.append((index, str(exc)))
            loser_finished.set()

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == len(errors) == 1
    assert "already consumed" in errors[0][1]
    assert [request.method for request in requests] == ["POST", "GET"]
    winner, result = results[0]
    assert result["result"] == "PASS"
    intent = persisted(package_dir, gate.INTENT_FILENAME)
    mutation = persisted(package_dir, gate.MUTATION_RESULT_FILENAME)
    terminal = persisted(package_dir, gate.QUALIFICATION_RESULT_FILENAME)
    winner_fingerprint = gate.StripeTestCredential(credentials[winner]).fingerprint
    assert intent["credential_fingerprint"] == winner_fingerprint
    assert mutation["credential_fingerprint"] == winner_fingerprint
    assert terminal["credential_fingerprint"] == winner_fingerprint
    assert terminal["real_stripe_create_dispatches"] == 1
    before = len(requests)
    with pytest.raises(gate.StripeLiveQualificationError, match="consumed"):
        execute(package, RecordingTransport())
    assert len(requests) == before


def test_provider_reported_idempotent_replay_is_terminal_nonpass(package):
    transport = RecordingTransport(
        response(200, customer(), (("Idempotent-Replayed", "true"),)),
        response(200, page([customer()])),
    )
    result = execute(package, transport)
    assert result["result"] == "NOT_PASS"
    assert result["failure_reason"] == "provider_reported_idempotent_replay"
    assert result["idempotent_replayed"] is True
    assert [request.method for request in transport.requests] == ["POST"]
    assert (package[1] / gate.MUTATION_RESULT_FILENAME).exists()
    assert not (package[1] / gate.OBSERVATION_RESULT_FILENAME).exists()


@pytest.mark.parametrize("header", [None, "false"])
def test_absent_or_false_idempotent_replay_allows_normal_path(package, header):
    headers = () if header is None else (("Idempotent-Replayed", header),)
    transport = RecordingTransport(
        response(200, customer(), headers), response(200, page([customer()]))
    )
    result = execute(package, transport)
    assert result["result"] == "PASS"
    assert result["idempotent_replayed"] is (False if header == "false" else None)
    assert [request.method for request in transport.requests] == ["POST", "GET"]


def test_repository_state_uses_full_porcelain_status(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    calls = []

    def run_git(_root, *args):
        calls.append(args)
        if args == ("rev-parse", "--show-toplevel"):
            return str(root)
        if args == ("rev-parse", "HEAD"):
            return HEAD
        if args == ("rev-parse", "origin/main"):
            return ORIGIN
        if args == ("status", "--porcelain"):
            return "?? untracked.py"
        raise AssertionError(args)

    monkeypatch.setattr(gate, "_run_git", run_git)
    assert gate._repository_state(root) == (HEAD, ORIGIN, "?? untracked.py")
    assert ("status", "--porcelain", "--untracked-files=no") not in calls


def test_prepare_rejects_unpushed_head_and_unreviewed_httpx(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    destination = tmp_path / "qualification"
    monkeypatch.setattr(gate, "_source_hashes", lambda _root: dict(SOURCE_HASHES))
    monkeypatch.setattr(gate, "_repository_state", lambda _root: (HEAD, "5" * 40, ""))
    with pytest.raises(gate.StripeLiveQualificationError, match="pushed origin/main"):
        gate.prepare_qualification(destination, repository_root=root)
    assert not destination.exists()

    monkeypatch.setattr(gate, "_repository_state", lambda _root: (HEAD, HEAD, ""))
    monkeypatch.setattr(gate, "_httpx_runtime_version", lambda: "0.29.0")
    with pytest.raises(gate.StripeLiveQualificationError, match="reviewed httpx"):
        gate.prepare_qualification(destination, repository_root=root)
    assert not destination.exists()


def test_execute_rejects_httpx_runtime_drift_before_credential_or_provider(
    package, monkeypatch
):
    monkeypatch.setattr(gate, "_httpx_runtime_version", lambda: "0.29.0")
    called = []
    with pytest.raises(gate.StripeLiveQualificationError, match="reviewed httpx"):
        execute(
            package,
            RecordingTransport(),
            credential_reader=lambda: called.append("credential") or RAW_CREDENTIAL,
            adapter_factory=lambda _credential: called.append("adapter"),
        )
    assert called == []


def test_final_result_preserves_httpx_runtime_provenance(package):
    transport = RecordingTransport(response(200, customer()), response(200, page([customer()])))
    result = execute(package, transport)
    assert result["reviewed_httpx_version"] == "0.28.1"
    assert result["runtime_httpx_version"] == "0.28.1"
