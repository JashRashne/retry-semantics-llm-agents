"""Hostile offline checks for the Stripe Customer adapter; no provider calls."""

from dataclasses import FrozenInstanceError, asdict, replace
import json
from pathlib import Path
import socket
from urllib.parse import parse_qs

import httpx
import pytest

import retry_semantics.study2.stripe_adapter as adapter_module
from retry_semantics.study2.stripe_adapter import (
    CUSTOMER_LIST_LIMIT,
    CUSTOMERS_PATH,
    REVIEWED_STRIPE_API_VERSION,
    DispatchLifecycle,
    FrozenCustomerCreateRequest,
    MutationDisposition,
    ObservationConclusion,
    RemoteMutationOutcome,
    StripeAdapterError,
    StripeCustomerAdapter,
    StripeTestCredential,
)
from retry_semantics.study2.stripe_semantics import STRIPE_ENGINEERING_SCOPE


RAW_CREDENTIAL = "sk_test_OFFLINE_ONLY_SECRET_123"
EMAIL = "Study.Marker+Case@retry-semantics.invalid"


@pytest.fixture(autouse=True)
def forbid_external_sockets(monkeypatch):
    def prohibited(*_args, **_kwargs):
        raise AssertionError("Stripe adapter tests must not open sockets")

    monkeypatch.setattr(socket, "create_connection", prohibited)
    monkeypatch.setattr(socket.socket, "connect", prohibited)


class RecordedTransport:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        status, payload, headers = outcome
        if isinstance(payload, bytes):
            return httpx.Response(status, content=payload, headers=headers)
        return httpx.Response(status, json=payload, headers=headers)


@pytest.fixture
def adapter_factory(request):
    clients = []

    def make(*outcomes, **options):
        recorded = RecordedTransport(*outcomes)
        client = StripeCustomerAdapter(
            StripeTestCredential(RAW_CREDENTIAL),
            transport=recorded.transport,
            **options,
        )
        clients.append(client)
        return client, recorded

    def close_all():
        for client in clients:
            client.close()

    request.addfinalizer(close_all)
    return make


def response(status, payload, headers=()):
    return status, payload, headers


def customer(customer_id="cus_A1", *, email=EMAIL, livemode=False, **changes):
    return {
        "id": customer_id,
        "object": "customer",
        "email": email,
        "livemode": livemode,
        **changes,
    }


def page(data=(), *, has_more=False, **changes):
    return {"object": "list", "data": list(data), "has_more": has_more, **changes}


def test_deterministic_create_request_preserves_exact_form_bytes_and_identity(adapter_factory):
    client, recorded = adapter_factory(response(200, customer()))
    first = client.prepare_customer_create(email=EMAIL)
    second = client.prepare_customer_create(email=EMAIL)

    assert first.request.body == second.request.body == (
        b"email=Study.Marker%2BCase%40retry-semantics.invalid"
    )
    assert first.request.identity_sha256 == second.request.identity_sha256
    assert first.request.body_sha256 == second.request.body_sha256
    frozen_bytes = first.request.body
    result = first.dispatch()

    assert len(recorded.requests) == 1
    assert recorded.requests[0].content is frozen_bytes
    assert bytes(recorded.requests[0].content) == frozen_bytes
    assert result.request.body_sha256 == first.request.body_sha256
    assert result.request.body_byte_count == len(frozen_bytes)
    assert result.request.identity_sha256 == first.request.identity_sha256
    with pytest.raises(FrozenInstanceError):
        first.request.body = b"changed"


def test_idempotency_key_is_absent_unless_explicitly_enabled(adapter_factory):
    client, recorded = adapter_factory(response(200, customer()))
    session = client.prepare_customer_create(email=EMAIL)
    prepared = session.prepared_evidence
    result = session.dispatch()

    assert "Idempotency-Key" not in recorded.requests[0].headers
    assert prepared.idempotency_key_present is False
    assert prepared.idempotency_key_identity_sha256 is None
    assert result.request.identity_sha256 == prepared.identity_sha256


def test_exact_runtime_owned_idempotency_key_is_sent_and_changes_identity(adapter_factory):
    key = "arm-local-runtime-key-001"
    client, recorded = adapter_factory(response(200, customer()))
    enabled = client.prepare_customer_create(email=EMAIL, idempotency_key=key)
    same = client.prepare_customer_create(email=EMAIL, idempotency_key=key)
    changed = client.prepare_customer_create(email=EMAIL, idempotency_key=key + "-changed")

    assert enabled.request.identity_sha256 == same.request.identity_sha256
    assert enabled.request.identity_sha256 != changed.request.identity_sha256
    evidence = enabled.dispatch()
    assert recorded.requests[0].headers["Idempotency-Key"] == key
    assert evidence.request.idempotency_key_present
    assert evidence.request.idempotency_key_identity_sha256 is not None
    assert key not in repr(enabled.request) + repr(evidence)


def test_credentials_cannot_be_reused_as_idempotency_identity_material(adapter_factory):
    client, recorded = adapter_factory()
    for unsafe_key in (RAW_CREDENTIAL, "prefix-" + RAW_CREDENTIAL):
        with pytest.raises(StripeAdapterError) as captured:
            client.prepare_customer_create(email=EMAIL, idempotency_key=unsafe_key)
        assert RAW_CREDENTIAL not in str(captured.value) + repr(captured.value)
    assert recorded.requests == []


@pytest.mark.parametrize(
    "value",
    ["sk_live_forbidden", "rk_live_forbidden", "sk_test_", "sandbox", "", None],
)
def test_credential_gate_rejects_live_or_unclear_scope_without_echo(value):
    with pytest.raises(StripeAdapterError) as captured:
        StripeTestCredential(value)
    assert not value or value not in str(captured.value) + repr(captured.value)


def test_raw_credential_absent_from_repr_errors_and_all_returned_evidence(adapter_factory):
    client, recorded = adapter_factory(
        response(
            200,
            customer(),
            (("Request-Id", RAW_CREDENTIAL), ("Idempotent-Replayed", RAW_CREDENTIAL)),
        )
    )
    session = client.prepare_customer_create(email=EMAIL)
    result = session.dispatch()

    rendered = repr(client) + repr(session) + repr(session.request) + repr(result)
    rendered += repr(asdict(result))
    assert RAW_CREDENTIAL not in rendered
    assert result.acknowledgement.request_id is None
    assert result.acknowledgement.idempotent_replayed is None
    assert recorded.requests[0].headers["Authorization"] == f"Bearer {RAW_CREDENTIAL}"


def test_explicit_stripe_version_and_fixed_create_endpoint(adapter_factory):
    client, recorded = adapter_factory(response(200, customer()))
    client.prepare_customer_create(email=EMAIL).dispatch()
    sent = recorded.requests[0]

    assert sent.method == "POST"
    assert sent.url.path == CUSTOMERS_PATH
    assert sent.headers["Stripe-Version"] == REVIEWED_STRIPE_API_VERSION
    assert sent.headers["Content-Type"] == "application/x-www-form-urlencoded"


def test_default_httpx_transport_is_explicitly_zero_retry(monkeypatch):
    captured = {}
    mock = httpx.MockTransport(lambda _request: httpx.Response(500))

    def transport_factory(*, retries):
        captured["retries"] = retries
        return mock

    monkeypatch.setattr(adapter_module.httpx, "HTTPTransport", transport_factory)
    client = StripeCustomerAdapter(StripeTestCredential(RAW_CREDENTIAL))
    try:
        assert captured == {"retries": 0}
        assert client._client.follow_redirects is False
    finally:
        client.close()


def test_redirect_is_acknowledged_not_followed_or_retried(adapter_factory):
    client, recorded = adapter_factory(
        response(302, b"redirect", (("Location", "https://example.invalid/elsewhere"),)),
        response(200, customer()),
    )
    result = client.prepare_customer_create(email=EMAIL).dispatch()

    assert len(recorded.requests) == 1
    assert result.disposition is MutationDisposition.UNEXPECTED_REDIRECT
    assert result.acknowledgement.response_received
    assert result.acknowledgement.status_code == 302
    assert result.remote_outcome is RemoteMutationOutcome.UNKNOWN_AFTER_HTTP_ACKNOWLEDGEMENT


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("synthetic timeout"),
        httpx.ConnectError("synthetic connection error"),
    ],
)
def test_transport_exception_is_one_ambiguous_attempt_and_consumes_one_shot(
    adapter_factory, error
):
    client, recorded = adapter_factory(error, response(200, customer()))
    session = client.prepare_customer_create(email=EMAIL)
    result = session.dispatch()

    assert len(recorded.requests) == 1
    assert len(recorded.outcomes) == 1
    assert session.consumed
    assert result.disposition is MutationDisposition.AMBIGUOUS_TRANSPORT_FAILURE
    assert result.remote_outcome is RemoteMutationOutcome.UNKNOWN_AMBIGUOUS
    assert result.request.dispatch_lifecycle is DispatchLifecycle.DISPATCH_INITIATED
    assert result.acknowledgement.response_received is False
    assert result.acknowledgement.status_code is None
    assert "not_executed" not in repr(result).lower()
    with pytest.raises(StripeAdapterError, match="already consumed"):
        session.dispatch()
    assert len(recorded.requests) == 1


def test_transport_exception_text_cannot_escape_into_evidence(adapter_factory):
    client, _ = adapter_factory(TimeoutError(RAW_CREDENTIAL))
    result = client.prepare_customer_create(email=EMAIL).dispatch()
    assert RAW_CREDENTIAL not in repr(result) + repr(asdict(result))
    assert result.failure_reason == "transport_exception_after_dispatch_initiated"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_http_failures_are_acknowledged_once_without_remote_execution_claim(
    adapter_factory, status
):
    client, recorded = adapter_factory(
        response(status, {"error": {"message": RAW_CREDENTIAL}}),
        response(200, customer()),
    )
    result = client.prepare_customer_create(email=EMAIL).dispatch()

    assert len(recorded.requests) == 1
    assert result.disposition is MutationDisposition.HTTP_ACKNOWLEDGED_FAILURE
    assert result.acknowledgement.response_received
    assert result.acknowledgement.status_code == status
    assert result.remote_outcome is RemoteMutationOutcome.UNKNOWN_AFTER_HTTP_ACKNOWLEDGEMENT
    assert RAW_CREDENTIAL not in repr(result)


def test_successful_customer_acknowledgement_and_optional_headers(adapter_factory):
    client, _ = adapter_factory(
        response(
            200,
            customer("cus_Valid123"),
            (("Request-Id", "req_123"), ("Idempotent-Replayed", "true")),
        )
    )
    result = client.prepare_customer_create(email=EMAIL).dispatch()

    assert result.disposition is MutationDisposition.VALID_CUSTOMER_ACKNOWLEDGEMENT
    assert result.remote_outcome is RemoteMutationOutcome.ACKNOWLEDGED_CUSTOMER
    assert result.request.dispatch_lifecycle is DispatchLifecycle.ACKNOWLEDGEMENT_VALIDATED
    assert result.acknowledgement.customer_id == "cus_Valid123"
    assert result.acknowledgement.request_id == "req_123"
    assert result.acknowledgement.idempotent_replayed is True
    assert result.failure_reason is None


def test_request_id_and_replayed_headers_are_optional(adapter_factory):
    client, _ = adapter_factory(response(200, customer()))
    acknowledgement = client.prepare_customer_create(email=EMAIL).dispatch().acknowledgement
    assert acknowledgement.request_id is None
    assert acknowledgement.idempotent_replayed is None


@pytest.mark.parametrize(
    "payload",
    [
        customer(email="Other@retry-semantics.invalid"),
        customer(livemode=True),
        {"id": "cus_A1", "object": "not_customer", "email": EMAIL, "livemode": False},
        {"id": "bad", "object": "customer", "email": EMAIL, "livemode": False},
        b"not-json",
    ],
)
def test_malformed_or_mismatched_success_never_becomes_execution_proof_or_retry(
    adapter_factory, payload
):
    client, recorded = adapter_factory(
        response(200, payload), response(200, customer())
    )
    result = client.prepare_customer_create(email=EMAIL).dispatch()

    assert len(recorded.requests) == 1
    assert result.disposition is MutationDisposition.MALFORMED_ACKNOWLEDGEMENT
    assert result.acknowledgement.response_received
    assert result.acknowledgement.customer_id is None
    assert result.remote_outcome is RemoteMutationOutcome.UNKNOWN_AFTER_MALFORMED_ACKNOWLEDGEMENT


def test_observer_uses_exact_email_limit_and_only_customer_list(adapter_factory):
    client, recorded = adapter_factory(response(200, page([customer()])))
    result = client.observe_customers(email=EMAIL)
    sent = recorded.requests[0]

    assert result.complete
    assert result.matching_customer_ids == ("cus_A1",)
    assert sent.method == "GET" and sent.url.path == CUSTOMERS_PATH
    assert parse_qs(sent.url.query.decode(), keep_blank_values=True) == {
        "email": [EMAIL],
        "limit": [str(CUSTOMER_LIST_LIMIT)],
    }
    assert "/search" not in str(sent.url)
    assert "test_clock" not in str(sent.url)
    assert sent.headers["Stripe-Version"] == REVIEWED_STRIPE_API_VERSION


@pytest.mark.parametrize(
    "returned_email",
    ["Other@retry-semantics.invalid", EMAIL.swapcase()],
)
def test_nonmatching_or_case_different_email_violates_exact_filter_contract(
    adapter_factory, returned_email
):
    client, recorded = adapter_factory(
        response(200, page([customer(email=returned_email)]))
    )
    result = client.observe_customers(email=EMAIL)

    assert len(recorded.requests) == 1
    assert not result.complete
    assert result.conclusion is ObservationConclusion.UNKNOWN_INCOMPLETE
    assert result.failure_reason == "exact_email_filter_contract_violation"
    assert result.matching_customer_ids == ()
    assert result.matching_resource_count == 0
    assert result.additional_matching_resource_count == 0


def test_multi_page_observation_processes_every_page_and_does_not_stop_at_first_match(
    adapter_factory,
):
    client, recorded = adapter_factory(
        response(200, page([customer("cus_A"), customer("cus_B")], has_more=True)),
        response(200, page([customer("cus_C"), customer("cus_D")], has_more=True)),
        response(200, page([customer("cus_E")], has_more=False)),
    )
    result = client.observe_customers(email=EMAIL)

    assert result.complete and result.page_count == result.request_count == 3
    assert result.matching_customer_ids == (
        "cus_A", "cus_B", "cus_C", "cus_D", "cus_E"
    )
    assert result.matching_resource_count == result.marker_multiplicity == 5
    assert result.additional_matching_resource_count == 4
    assert parse_qs(recorded.requests[1].url.query.decode())["starting_after"] == ["cus_B"]
    assert parse_qs(recorded.requests[2].url.query.decode())["starting_after"] == ["cus_D"]
    assert all(item.url.path == CUSTOMERS_PATH for item in recorded.requests)


@pytest.mark.parametrize(
    "customer_ids,additional",
    [
        (("cus_A",), 0),
        (("cus_A", "cus_B"), 1),
        (("cus_A", "cus_B", "cus_C"), 2),
    ],
)
def test_distinct_customers_define_experimental_resource_multiplicity(
    adapter_factory, customer_ids, additional
):
    client, _ = adapter_factory(
        response(200, page([customer(customer_id) for customer_id in customer_ids]))
    )
    result = client.observe_customers(email=EMAIL)

    assert result.complete
    assert result.matching_customer_ids == customer_ids
    assert result.matching_resource_count == len(customer_ids)
    assert result.marker_multiplicity == len(customer_ids)
    assert result.additional_matching_resource_count == additional
    assert "duplicate_count" not in result.__dataclass_fields__


def test_has_more_without_usable_final_cursor_fails_closed(adapter_factory):
    client, recorded = adapter_factory(response(200, page([], has_more=True)))
    result = client.observe_customers(email=EMAIL)

    assert len(recorded.requests) == 1
    assert not result.complete
    assert result.failure_reason == "malformed_or_nonadvancing_pagination"
    assert result.conclusion is ObservationConclusion.UNKNOWN_INCOMPLETE


def test_repeated_nonadvancing_cursor_fails_closed(adapter_factory):
    client, recorded = adapter_factory(
        response(200, page([customer("cus_A")], has_more=True)),
        response(200, page([customer("cus_A")], has_more=True)),
        response(200, page([])),
    )
    result = client.observe_customers(email=EMAIL)

    assert len(recorded.requests) == 2
    assert not result.complete
    assert result.conclusion is ObservationConclusion.UNKNOWN_INCOMPLETE
    assert result.failure_reason == "repeated_customer_id_across_pages"
    assert result.matching_customer_ids == ("cus_A",)
    assert result.matching_resource_count == 1
    assert result.additional_matching_resource_count == 0


def test_page_bound_exhaustion_is_unknown_incomplete_not_zero(adapter_factory):
    client, recorded = adapter_factory(
        response(200, page([customer("cus_A")], has_more=True)),
        response(200, page([customer("cus_B")], has_more=True)),
        response(200, page([])),
        max_observation_pages=2,
    )
    result = client.observe_customers(email=EMAIL)

    assert len(recorded.requests) == 2
    assert result.page_count == result.request_count == 2
    assert not result.complete
    assert result.failure_reason == "page_bound_exhausted"
    assert result.conclusion is ObservationConclusion.UNKNOWN_INCOMPLETE


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"object": "list", "data": [], "has_more": 0},
        {"object": "list", "data": {}, "has_more": False},
        {"object": "customer", "data": [], "has_more": False},
        b"not-json",
    ],
)
def test_malformed_list_payload_fails_closed(adapter_factory, payload):
    client, _ = adapter_factory(response(200, payload))
    result = client.observe_customers(email=EMAIL)
    assert not result.complete
    assert result.failure_reason == "malformed_or_nonadvancing_pagination"
    assert result.conclusion is ObservationConclusion.UNKNOWN_INCOMPLETE


@pytest.mark.parametrize(
    "entry",
    [
        None,
        {},
        customer(customer_id="invalid"),
        customer(email=None),
        customer(livemode=True),
        {"id": "cus_A", "object": "customer", "email": EMAIL},
    ],
)
def test_malformed_matching_customer_fails_closed(adapter_factory, entry):
    client, _ = adapter_factory(response(200, page([entry])))
    result = client.observe_customers(email=EMAIL)
    assert not result.complete
    assert result.failure_reason == "malformed_or_nonadvancing_pagination"


def test_observation_never_retries_transport_http_or_redirect_failures(adapter_factory):
    for first in (
        httpx.ReadTimeout("offline"),
        response(429, {}),
        response(503, {}),
        response(307, b"redirect", (("Location", "https://example.invalid"),)),
    ):
        client, recorded = adapter_factory(first, response(200, page()))
        result = client.observe_customers(email=EMAIL)
        assert not result.complete
        assert len(recorded.requests) == 1


def test_complete_zero_match_read_explicitly_is_not_h0_or_not_executed(adapter_factory):
    client, _ = adapter_factory(response(200, page([])))
    result = client.observe_customers(email=EMAIL)

    assert result.complete
    assert result.matching_customer_ids == ()
    assert result.matching_resource_count == 0
    assert result.additional_matching_resource_count == 0
    assert result.marker_multiplicity == 0
    assert result.conclusion is ObservationConclusion.COMPLETED_READ_NOT_H0_PROOF
    assert "not_executed" not in repr(result).lower()


def test_test_clock_and_arbitrary_mutation_fields_are_not_supported(adapter_factory):
    client, recorded = adapter_factory()
    with pytest.raises(TypeError):
        client.prepare_customer_create(email=EMAIL, test_clock="clock_123")
    assert recorded.requests == []

    valid = client.prepare_customer_create(email=EMAIL).request
    with pytest.raises(StripeAdapterError):
        replace(valid, body=valid.body + b"&test_clock=clock_123")


def test_request_evidence_is_immutable_safe_and_has_no_authorization(adapter_factory):
    client, _ = adapter_factory(response(200, customer()))
    evidence = client.prepare_customer_create(email=EMAIL).dispatch().request
    serialized = json.dumps(asdict(evidence), default=str, sort_keys=True)

    assert RAW_CREDENTIAL not in serialized
    assert "Authorization" not in serialized
    assert evidence.credential_fingerprint
    assert evidence.target_scope.endswith(evidence.credential_fingerprint)
    with pytest.raises(FrozenInstanceError):
        evidence.path = "/v1/customers/search"


def test_slice_creates_no_paper_observation_object_or_file():
    root = Path(__file__).resolve().parents[1]
    stripe_files = {path.name.lower() for path in (root / "research/study2/stripe").iterdir()}

    assert STRIPE_ENGINEERING_SCOPE.paper_observations == 0
    assert not any("observation" in name or "result" in name for name in stripe_files)
    assert not any(name.startswith("paper") for name in vars(adapter_module))


def test_frozen_request_rejects_credential_scope_substitution(adapter_factory):
    first, _ = adapter_factory()
    second_credential = StripeTestCredential("sk_test_DIFFERENT_SCOPE_456")
    recorded = RecordedTransport(response(200, customer()))
    second = StripeCustomerAdapter(second_credential, transport=recorded.transport)
    try:
        frozen = first.prepare_customer_create(email=EMAIL).request
        substituted = adapter_module.OneShotCustomerMutation(second, frozen)
        with pytest.raises(StripeAdapterError, match="credential scope mismatch"):
            substituted.dispatch()
        assert substituted.consumed
        assert not recorded.requests
    finally:
        second.close()


def test_frozen_request_constructor_does_not_accept_arbitrary_http_components():
    fields = FrozenCustomerCreateRequest.__dataclass_fields__
    assert fields["method"].init is False
    assert fields["path"].init is False
    assert fields["api_version"].init is False
    assert set(fields) >= {"body", "correlation_email", "credential_fingerprint"}
