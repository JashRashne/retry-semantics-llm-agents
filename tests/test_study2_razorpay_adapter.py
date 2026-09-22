"""Hostile offline tests for the Razorpay Order candidate adapter.

Every transport is injected.  The autouse socket guard makes an accidental
external connection a test failure.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
from threading import Barrier, Lock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2 import razorpay_adapter as razorpay_module
from retry_semantics.study2.razorpay_adapter import (
    CONTENT_TYPE,
    DEFAULT_TRANSPORT_PROFILE,
    EXPECTED_HTTP_SUCCESS,
    MARKER_KEY,
    ORDER_AMOUNT,
    ORDER_CURRENCY,
    ORDERS_PATH,
    ORDERS_URL,
    DispatchPermit,
    MutationClassification,
    ObservationConclusion,
    ObservationStatus,
    RazorpayAdapterValidationError,
    RazorpayCredentials,
    RazorpayOrderAdapter,
)


KEY_ID = "synthetic_key_id_offline_only"
SECRET = "synthetic_secret_offline_only_DO_NOT_USE"
MARKER = "study2_synthetic_0001"
SYNTHETIC_TRANSPORT_PROFILE = "synthetic_httpx_mocktransport_no_retry_v1"


@pytest.fixture(autouse=True)
def prohibit_external_sockets(monkeypatch):
    def blocked(*_args, **_kwargs):
        pytest.fail("external socket use is prohibited in Razorpay offline tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def adapter_factory():
    adapters: list[RazorpayOrderAdapter] = []

    def factory(handler, *, credentials=None, timeout_seconds=7.5):
        adapter = RazorpayOrderAdapter(
            credentials or RazorpayCredentials(KEY_ID, SECRET),
            timeout_seconds=timeout_seconds,
            transport=httpx.MockTransport(handler),
            transport_profile=SYNTHETIC_TRANSPORT_PROFILE,
        )
        adapters.append(adapter)
        return adapter

    yield factory
    for adapter in adapters:
        adapter.close()


def json_response(request, value, *, status=EXPECTED_HTTP_SUCCESS):
    return httpx.Response(
        status,
        headers={"Content-Type": "application/json"},
        content=canonical_json_bytes(value),
        request=request,
    )


def acknowledgement(marker=MARKER, **changes):
    value = {
        "id": "order_synthetic_0001",
        "entity": "order",
        "amount": ORDER_AMOUNT,
        "currency": ORDER_CURRENCY,
        "status": "created",
        "attempts": 0,
        "amount_paid": 0,
        "notes": {MARKER_KEY: marker},
        "receipt": None,
    }
    value.update(changes)
    return value


def order(index, *, marker=MARKER, notes_marker=True, notes_value=None):
    item = {"id": f"order_synthetic_{index:04d}", "entity": "order"}
    if notes_value is not None:
        item["notes"] = notes_value
    elif notes_marker:
        item["notes"] = {MARKER_KEY: marker}
    else:
        item["notes"] = {}
    return item


def collection(items):
    return {"entity": "collection", "count": len(items), "items": items}


def test_mutation_request_has_exact_deterministic_bytes_and_endpoint(adapter_factory):
    adapter = adapter_factory(lambda request: json_response(request, acknowledgement()))
    first = adapter.prepare_create_order(MARKER)
    second = adapter.prepare_create_order(MARKER)

    expected = (
        b'{"amount":200,"currency":"INR","notes":'
        b'{"retry_semantics_marker":"study2_synthetic_0001"}}'
    )
    assert first == second
    assert first.body == expected
    assert first.identity_bytes() == second.identity_bytes()
    assert first.identity_sha256 == second.identity_sha256
    assert first.method == "POST"
    assert first.origin == "https://api.razorpay.com"
    assert first.path == ORDERS_PATH
    assert first.url == ORDERS_URL
    assert first.content_type == CONTENT_TYPE
    assert first.amount == 200 and first.currency == "INR"
    assert first.marker == MARKER

    payload = json.loads(first.body)
    assert payload == {
        "amount": 200,
        "currency": "INR",
        "notes": {MARKER_KEY: MARKER},
    }
    for forbidden in (
        "receipt",
        "partial_payment",
        "first_payment_min_amount",
        "customer",
        "transfer",
        "offer",
        "checkout",
    ):
        assert forbidden not in payload
    assert len(payload["notes"]) == 1


@pytest.mark.parametrize(
    "marker",
    [
        "",
        "   ",
        "synthetic_without_prefix",
        "study2_é",
        "study2_line\nbreak",
        "study2_path/to/value",
        r"study2_path\to\value",
        "study2_https://example.test",
        "study2_user@example.test",
        "study2_" + "x" * 57,
        None,
    ],
)
def test_unsafe_or_non_ascii_marker_rejected_before_dispatch(adapter_factory, marker):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return json_response(request, acknowledgement())

    adapter = adapter_factory(handler)
    permit = DispatchPermit()
    result = adapter.create_order(marker, permit)
    assert result.classification is MutationClassification.PRE_DISPATCH_REJECTED
    assert not result.dispatch_started
    assert not permit.consumed
    assert calls == 0


def test_request_identity_changes_with_marker_scope_and_exact_body(adapter_factory):
    first = adapter_factory(
        lambda request: json_response(request, acknowledgement()),
        credentials=RazorpayCredentials("synthetic_scope_a", "synthetic_secret_a"),
    )
    second = adapter_factory(
        lambda request: json_response(request, acknowledgement()),
        credentials=RazorpayCredentials("synthetic_scope_b", "synthetic_secret_b"),
    )
    request_a = first.prepare_create_order("study2_marker_a")
    request_a_again = first.prepare_create_order("study2_marker_a")
    request_marker_b = first.prepare_create_order("study2_marker_b")
    request_scope_b = second.prepare_create_order("study2_marker_a")

    assert request_a.identity_sha256 == request_a_again.identity_sha256
    assert request_a.body == request_a_again.body
    assert request_a.identity_sha256 != request_marker_b.identity_sha256
    assert request_a.body != request_marker_b.body
    assert request_a.identity_sha256 != request_scope_b.identity_sha256
    assert request_a.body == request_scope_b.body
    encoded_body = base64.b64encode(request_a.body).decode("ascii")
    assert encoded_body in request_a.identity_bytes().decode("ascii")


def test_changing_only_transport_profile_changes_request_identity():
    credentials = RazorpayCredentials(KEY_ID, SECRET)
    handler = lambda request: json_response(request, acknowledgement())
    first = RazorpayOrderAdapter(
        credentials,
        transport=httpx.MockTransport(handler),
        transport_profile="synthetic_transport_profile_a_v1",
    )
    second = RazorpayOrderAdapter(
        credentials,
        transport=httpx.MockTransport(handler),
        transport_profile="synthetic_transport_profile_b_v1",
    )
    try:
        request_a = first.prepare_create_order(MARKER)
        request_b = second.prepare_create_order(MARKER)
        assert request_a.body == request_b.body
        assert request_a.transport_profile != request_b.transport_profile
        assert request_a.identity_sha256 != request_b.identity_sha256
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize(
    "key_id,key_secret",
    [("", "secret"), ("key", ""), (None, "secret"), ("key", None)],
)
def test_empty_credentials_rejected(key_id, key_secret):
    with pytest.raises(RazorpayAdapterValidationError, match="nonempty"):
        RazorpayCredentials(key_id, key_secret)


def test_credential_repr_authorization_boundary_and_evidence_are_secret_safe(adapter_factory):
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(
            request,
            acknowledgement(),
        )

    credentials = RazorpayCredentials(KEY_ID, SECRET)
    adapter = adapter_factory(handler, credentials=credentials)
    result = adapter.create_order(MARKER, DispatchPermit())
    expected_basic = "Basic " + base64.b64encode(
        f"{KEY_ID}:{SECRET}".encode("utf-8")
    ).decode("ascii")

    assert seen[0].headers["Authorization"] == expected_basic
    assert seen[0].headers["Content-Type"] == CONTENT_TYPE
    evidence = canonical_json_bytes(result.sanitized_evidence())
    safe_text = repr(credentials) + str(credentials) + repr(adapter) + repr(result)
    assert SECRET not in safe_text
    assert KEY_ID not in safe_text
    assert SECRET.encode() not in evidence
    assert KEY_ID.encode() not in evidence
    assert expected_basic.encode() not in evidence
    assert b"Authorization" not in evidence
    assert result.classification is MutationClassification.ACKNOWLEDGED_CREATE


def test_one_shot_permit_consumed_before_transport_exception_and_never_refunded(adapter_factory):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("synthetic timeout carrying no credentials", request=request)

    adapter = adapter_factory(handler)
    frozen = adapter.prepare_create_order(MARKER)
    permit = DispatchPermit()
    first = adapter.dispatch_create_order(frozen, permit)
    second = adapter.dispatch_create_order(frozen, permit)

    assert permit.consumed
    assert calls == 1
    assert first.classification is MutationClassification.UNKNOWN_AFTER_DISPATCH
    assert first.dispatch_started and not first.local_transport_completed
    assert second.classification is MutationClassification.PRE_DISPATCH_REJECTED
    assert not second.dispatch_started


def test_local_outbound_construction_failure_does_not_consume_or_send(
    adapter_factory, monkeypatch
):
    sends = 0

    def handler(request):
        nonlocal sends
        sends += 1
        return json_response(request, acknowledgement())

    adapter = adapter_factory(handler)
    frozen = adapter.prepare_create_order(MARKER)
    permit = DispatchPermit()

    def fail_build(*_args, **_kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(adapter._client, "build_request", fail_build)
    result = adapter.dispatch_create_order(frozen, permit)

    assert not permit.consumed
    assert sends == 0
    assert result.classification is MutationClassification.PRE_DISPATCH_REJECTED
    assert result.failure_reason == "outbound_request_construction_failed"
    assert SECRET not in repr(result) + repr(result.sanitized_evidence())


def test_consumed_permit_sends_zero_times(adapter_factory):
    sends = 0

    def handler(request):
        nonlocal sends
        sends += 1
        return json_response(request, acknowledgement())

    adapter = adapter_factory(handler)
    frozen = adapter.prepare_create_order(MARKER)
    permit = DispatchPermit()
    assert permit.consume()

    result = adapter.dispatch_create_order(frozen, permit)
    assert sends == 0
    assert result.classification is MutationClassification.PRE_DISPATCH_REJECTED
    assert result.failure_reason == "dispatch_permit_unavailable"


def test_two_threads_racing_same_permit_dispatch_exactly_once(
    adapter_factory, monkeypatch
):
    sends = 0
    sends_lock = Lock()

    def handler(request):
        nonlocal sends
        with sends_lock:
            sends += 1
        return json_response(request, acknowledgement())

    adapter = adapter_factory(handler)
    frozen = adapter.prepare_create_order(MARKER)
    permit = DispatchPermit()
    original_build = adapter._client.build_request
    both_requests_built = Barrier(2)

    def synchronized_build(*args, **kwargs):
        outbound = original_build(*args, **kwargs)
        both_requests_built.wait(timeout=2)
        return outbound

    monkeypatch.setattr(adapter._client, "build_request", synchronized_build)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _index: adapter.dispatch_create_order(frozen, permit),
                range(2),
            )
        )

    assert sends == 1
    assert permit.consumed
    assert sorted(result.classification.value for result in results) == [
        MutationClassification.ACKNOWLEDGED_CREATE.value,
        MutationClassification.PRE_DISPATCH_REJECTED.value,
    ]


def test_invalid_acknowledgement_does_not_refund_permit(adapter_factory):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return json_response(request, {"entity": "order"})

    adapter = adapter_factory(handler)
    frozen = adapter.prepare_create_order(MARKER)
    permit = DispatchPermit()
    first = adapter.dispatch_create_order(frozen, permit)
    second = adapter.dispatch_create_order(frozen, permit)

    assert calls == 1 and permit.consumed
    assert first.classification is MutationClassification.UNKNOWN_AFTER_DISPATCH
    assert first.local_transport_completed and not first.acknowledgement_valid
    assert second.classification is MutationClassification.PRE_DISPATCH_REJECTED


def test_new_permit_can_dispatch_same_frozen_request_again_without_replay_policy(adapter_factory):
    calls = []

    def handler(request):
        calls.append(request.content)
        return json_response(request, acknowledgement())

    adapter = adapter_factory(handler)
    frozen = adapter.prepare_create_order(MARKER)
    first = adapter.dispatch_create_order(frozen, DispatchPermit())
    second = adapter.dispatch_create_order(frozen, DispatchPermit())

    assert len(calls) == 2
    assert calls[0] == calls[1] == frozen.body
    assert first.classification is second.classification is MutationClassification.ACKNOWLEDGED_CREATE
    assert first.request_identity_sha256 == second.request_identity_sha256


def test_valid_create_acknowledgement_is_conservatively_accepted(adapter_factory):
    adapter = adapter_factory(lambda request: json_response(request, acknowledgement()))
    result = adapter.create_order(MARKER, DispatchPermit())
    assert result.classification is MutationClassification.ACKNOWLEDGED_CREATE
    assert result.dispatch_started
    assert result.local_transport_completed
    assert result.acknowledgement_valid
    assert result.http_status == 200
    assert result.provider_order_id == "order_synthetic_0001"
    assert result.failure_reason is None


@pytest.mark.parametrize(
    "status",
    [400, 401, 403, 404, 409, 422, 429, 500, 502, 503, 504],
)
def test_every_4xx_and_5xx_is_unknown_after_one_attempt(adapter_factory, status):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return json_response(request, {"error": {"description": SECRET}}, status=status)

    adapter = adapter_factory(handler)
    result = adapter.create_order(MARKER, DispatchPermit())
    assert calls == 1
    assert result.classification is MutationClassification.UNKNOWN_AFTER_DISPATCH
    assert result.dispatch_started and result.local_transport_completed
    assert not result.acknowledgement_valid and result.provider_order_id is None
    assert result.http_status == status
    assert SECRET not in repr(result) + repr(result.sanitized_evidence())


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_timeout_and_disconnect_are_unknown_and_not_retried(adapter_factory, error_type):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise error_type(SECRET, request=request)

    adapter = adapter_factory(handler)
    result = adapter.create_order(MARKER, DispatchPermit())
    assert calls == 1
    assert result.classification is MutationClassification.UNKNOWN_AFTER_DISPATCH
    assert not result.local_transport_completed
    assert SECRET not in repr(result) + repr(result.sanitized_evidence())


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        acknowledgement(entity="payment"),
        acknowledgement(id=""),
        acknowledgement(amount=201),
        acknowledgement(amount=True),
        acknowledgement(currency="USD"),
        acknowledgement(status="attempted"),
        acknowledgement(attempts=1),
        acknowledgement(amount_paid=1),
        acknowledgement(notes={MARKER_KEY: "study2_wrong"}),
        acknowledgement(notes=[]),
        acknowledgement(receipt="synthetic_receipt"),
    ],
)
def test_malformed_or_contradictory_success_ack_is_unknown(adapter_factory, payload):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return json_response(request, payload)

    adapter = adapter_factory(handler)
    result = adapter.create_order(MARKER, DispatchPermit())
    assert calls == 1
    assert result.classification is MutationClassification.UNKNOWN_AFTER_DISPATCH
    assert result.dispatch_started and result.local_transport_completed
    assert not result.acknowledgement_valid
    assert result.provider_order_id is None


def test_non_json_success_is_unknown_and_not_retried(adapter_factory):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"not-json", request=request)

    adapter = adapter_factory(handler)
    result = adapter.create_order(MARKER, DispatchPermit())
    assert calls == 1
    assert result.classification is MutationClassification.UNKNOWN_AFTER_DISPATCH
    assert result.failure_reason == "malformed_json_acknowledgement"


def test_default_http_client_disables_retries_redirects_and_environment(monkeypatch):
    transport_kwargs = {}
    client_kwargs = {}
    sentinel = object()

    class FakeClient:
        def __init__(self, **kwargs):
            client_kwargs.update(kwargs)

        def close(self):
            pass

    def fake_transport(**kwargs):
        transport_kwargs.update(kwargs)
        return sentinel

    monkeypatch.setattr(razorpay_module.httpx, "HTTPTransport", fake_transport)
    monkeypatch.setattr(razorpay_module.httpx, "Client", FakeClient)
    adapter = RazorpayOrderAdapter(
        RazorpayCredentials(KEY_ID, SECRET), timeout_seconds=12.5
    )
    frozen = adapter.prepare_create_order(MARKER)
    adapter.close()

    assert transport_kwargs == {"retries": 0}
    assert client_kwargs["transport"] is sentinel
    assert client_kwargs["follow_redirects"] is False
    assert client_kwargs["trust_env"] is False
    assert client_kwargs["timeout"] == httpx.Timeout(12.5)
    assert frozen.transport_profile == DEFAULT_TRANSPORT_PROFILE


def test_injected_transport_requires_and_records_explicit_profile():
    transport = httpx.MockTransport(
        lambda request: json_response(request, acknowledgement())
    )
    with pytest.raises(RazorpayAdapterValidationError, match="explicit profile"):
        RazorpayOrderAdapter(RazorpayCredentials(KEY_ID, SECRET), transport=transport)
    with pytest.raises(RazorpayAdapterValidationError, match="reserved"):
        RazorpayOrderAdapter(
            RazorpayCredentials(KEY_ID, SECRET),
            transport=transport,
            transport_profile=DEFAULT_TRANSPORT_PROFILE,
        )

    adapter = RazorpayOrderAdapter(
        RazorpayCredentials(KEY_ID, SECRET),
        transport=transport,
        transport_profile=SYNTHETIC_TRANSPORT_PROFILE,
    )
    try:
        assert (
            adapter.prepare_create_order(MARKER).transport_profile
            == SYNTHETIC_TRANSPORT_PROFILE
        )
    finally:
        adapter.close()


def test_observation_uses_exact_get_endpoint_stable_query_and_local_marker(adapter_factory):
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(
            request,
            collection(
                [
                    order(1),
                    order(2, marker="study2_case_different"),
                    order(3, notes_marker=False),
                ]
            ),
        )

    adapter = adapter_factory(handler)
    result = adapter.observe_orders(
        marker=MARKER,
        from_timestamp=1_700_000_000,
        to_timestamp=1_700_000_100,
        page_cap=4,
    )
    request = seen[0]
    assert request.method == "GET"
    assert request.url.path == ORDERS_PATH
    assert request.url.query.decode() == (
        "count=100&skip=0&from=1700000000&to=1700000100"
    )
    assert parse_qs(urlsplit(str(request.url)).query) == {
        "count": ["100"],
        "skip": ["0"],
        "from": ["1700000000"],
        "to": ["1700000100"],
    }
    assert "receipt" not in str(request.url)
    assert "notes" not in str(request.url)
    assert result.matching_order_ids == ("order_synthetic_0001",)
    assert result.matching_resource_count == 1


@pytest.mark.parametrize(
    "matching,expected_additional",
    [(0, 0), (1, 0), (2, 1), (3, 2)],
)
def test_distinct_resource_multiplicity_arithmetic(
    adapter_factory, matching, expected_additional
):
    items = [order(index + 1) for index in range(matching)]
    adapter = adapter_factory(lambda request: json_response(request, collection(items)))
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=10, to_timestamp=20, page_cap=2
    )
    assert result.status is ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED
    assert result.authoritative_completeness_qualified is False
    assert result.matching_resource_count == matching
    assert result.additional_matching_resource_count == expected_additional


@pytest.mark.parametrize(
    "item_count,expected_requests",
    [(0, 1), (1, 1), (99, 1), (100, 2), (101, 2), (199, 2), (200, 3)],
)
def test_offset_boundary_traversal_is_structural_and_unqualified(
    adapter_factory, item_count, expected_requests
):
    all_items = [order(index + 1, notes_marker=False) for index in range(item_count)]
    calls = []

    def handler(request):
        query = parse_qs(request.url.query.decode())
        skip = int(query["skip"][0])
        calls.append(skip)
        return json_response(request, collection(all_items[skip : skip + 100]))

    adapter = adapter_factory(handler)
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=100, to_timestamp=200, page_cap=10
    )
    assert len(calls) == expected_requests
    assert calls == [index * 100 for index in range(expected_requests)]
    assert result.status is ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED
    assert result.structurally_completed
    assert result.authoritative_completeness_qualified is False
    assert result.pages_requested == result.pages_completed == expected_requests
    assert result.matching_resource_count == 0
    assert result.conclusion is ObservationConclusion.ZERO_MATCHES_READ_NOT_H0_PROOF


def test_repeated_order_id_across_pages_is_instability_not_resource(adapter_factory):
    first = [order(index + 1) for index in range(100)]
    second = [order(1)]
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return json_response(request, collection(first if calls == 1 else second))

    adapter = adapter_factory(handler)
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=3
    )
    assert calls == 2
    assert result.status is ObservationStatus.INCOMPLETE
    assert result.pagination_instability
    assert result.incomplete_reason == "repeated_order_id"
    assert result.matching_resource_count is None
    assert result.additional_matching_resource_count is None
    assert result.conclusion is ObservationConclusion.OBSERVATION_INCOMPLETE


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"entity": "other", "items": []},
        {"entity": "collection", "items": {}},
        collection([None]),
        collection([{"id": "order_1", "entity": "other", "notes": {}}]),
        collection([{"id": "", "entity": "order", "notes": {}}]),
        collection([order(index + 1) for index in range(101)]),
    ],
)
def test_malformed_collection_never_becomes_empty_complete(adapter_factory, payload):
    adapter = adapter_factory(lambda request: json_response(request, payload))
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=2
    )
    assert result.status is ObservationStatus.MALFORMED
    assert not result.structurally_completed
    assert result.matching_resource_count is None
    assert result.conclusion is ObservationConclusion.OBSERVATION_INCOMPLETE


@pytest.mark.parametrize(
    "notes",
    [None, [], ["possibly", "marker"], "unsafe", {MARKER_KEY: None}, {MARKER_KEY: 1}],
)
def test_malformed_notes_fail_closed_instead_of_nonmatching(adapter_factory, notes):
    item = {"id": "order_synthetic_0001", "entity": "order", "notes": notes}
    adapter = adapter_factory(
        lambda request: json_response(request, collection([item]))
    )
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=2
    )
    assert result.status is ObservationStatus.MALFORMED
    assert result.matching_resource_count is None
    assert result.incomplete_reason in {"malformed_notes", "malformed_marker_value"}


def test_missing_notes_field_fails_closed(adapter_factory):
    item = {"id": "order_missing_notes", "entity": "order"}
    adapter = adapter_factory(
        lambda request: json_response(request, collection([item]))
    )
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=2
    )
    assert result.status is ObservationStatus.MALFORMED
    assert result.matching_resource_count is None
    assert result.incomplete_reason == "missing_notes_field"


@pytest.mark.parametrize("notes", [{}, {"other_key": "synthetic_value"}])
def test_notes_object_without_marker_is_safe_nonmatch(adapter_factory, notes):
    item = {"id": "order_notes_without_marker", "entity": "order", "notes": notes}
    adapter = adapter_factory(
        lambda request: json_response(request, collection([item]))
    )
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=2
    )
    assert result.status is ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED
    assert result.matching_resource_count == 0
    assert result.conclusion is ObservationConclusion.ZERO_MATCHES_READ_NOT_H0_PROOF


def test_marker_matching_is_case_sensitive_without_normalization(adapter_factory):
    items = [order(1), order(2, marker=MARKER.upper())]
    adapter = adapter_factory(lambda request: json_response(request, collection(items)))
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=2
    )
    assert result.matching_order_ids == ("order_synthetic_0001",)


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_read_transport_failure_is_incomplete_not_zero_and_not_retried(
    adapter_factory, error_type
):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise error_type(SECRET, request=request)

    adapter = adapter_factory(handler)
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=2
    )
    assert calls == 1
    assert result.status is ObservationStatus.TRANSPORT_FAILED
    assert result.matching_resource_count is None
    assert result.additional_matching_resource_count is None
    assert result.conclusion is ObservationConclusion.OBSERVATION_INCOMPLETE
    assert SECRET not in repr(result) + repr(result.sanitized_evidence())


@pytest.mark.parametrize("status", [400, 500])
def test_read_http_failure_is_incomplete_and_not_retried(adapter_factory, status):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return json_response(request, {"error": SECRET}, status=status)

    adapter = adapter_factory(handler)
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=2
    )
    assert calls == 1
    assert result.status is ObservationStatus.INCOMPLETE
    assert result.matching_resource_count is None
    assert result.incomplete_reason == "unexpected_http_status"
    assert result.http_statuses == (status,)
    assert result.sanitized_evidence()["http_statuses"] == [status]
    assert SECRET not in repr(result.sanitized_evidence())


def test_read_malformed_json_is_incomplete_and_not_retried(adapter_factory):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"not-json", request=request)

    adapter = adapter_factory(handler)
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=2
    )
    assert calls == 1
    assert result.status is ObservationStatus.MALFORMED
    assert result.matching_resource_count is None


def test_page_cap_returns_incomplete_without_infinite_scan(adapter_factory):
    calls = 0
    full_page = [order(index + 1, notes_marker=False) for index in range(100)]

    def handler(request):
        nonlocal calls
        calls += 1
        return json_response(request, collection(full_page))

    adapter = adapter_factory(handler)
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=1
    )
    assert calls == 1
    assert result.status is ObservationStatus.INCOMPLETE
    assert result.incomplete_reason == "page_cap_exceeded"
    assert result.matching_resource_count is None


@pytest.mark.parametrize(
    "from_timestamp,to_timestamp,page_cap",
    [
        (-1, 2, 1),
        (1, -2, 1),
        (3, 2, 1),
        (1.0, 2, 1),
        (1, 2.0, 1),
        (True, 2, 1),
        (1, 2, 0),
        (1, 2, -1),
        (1, 2, True),
    ],
)
def test_observation_window_and_page_cap_validation(
    adapter_factory, from_timestamp, to_timestamp, page_cap
):
    adapter = adapter_factory(lambda request: json_response(request, collection([])))
    with pytest.raises(RazorpayAdapterValidationError):
        adapter.prepare_observation(
            marker=MARKER,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            page_cap=page_cap,
        )


def test_structural_zero_is_explicitly_not_h0_or_not_executed(adapter_factory):
    adapter = adapter_factory(
        lambda request: json_response(request, collection([]))
    )
    result = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=1
    )
    evidence = canonical_json_bytes(result.sanitized_evidence())
    assert result.matching_resource_count == 0
    assert result.conclusion is ObservationConclusion.ZERO_MATCHES_READ_NOT_H0_PROOF
    assert b"ZERO_MATCHES_READ_NOT_H0_PROOF" in evidence
    assert b"NOT_EXECUTED" not in evidence
    assert b'"H0"' not in evidence
    assert result.authoritative_completeness_qualified is False


def test_secret_absent_from_repr_evidence_exception_messages_and_document(adapter_factory):
    def handler(request):
        raise RuntimeError(SECRET)

    credentials = RazorpayCredentials(KEY_ID, SECRET)
    adapter = adapter_factory(handler, credentials=credentials)
    mutation = adapter.create_order(MARKER, DispatchPermit())
    observation = adapter.observe_orders(
        marker=MARKER, from_timestamp=1, to_timestamp=2, page_cap=1
    )
    evidence = canonical_json_bytes(
        {
            "mutation": mutation.sanitized_evidence(),
            "observation": observation.sanitized_evidence(),
        }
    )
    documentation = (
        Path(__file__).parents[1]
        / "research/study2/razorpay/RAZORPAY_ADAPTER_ENGINEERING_DRAFT.md"
    ).read_text()

    assert SECRET not in repr(credentials) + repr(adapter) + repr(mutation) + repr(observation)
    assert SECRET.encode() not in evidence
    assert SECRET not in documentation
    assert mutation.failure_reason == "transport_exception"
    assert observation.incomplete_reason == "transport_exception"
