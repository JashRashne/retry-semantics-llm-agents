from __future__ import annotations

import json

import pytest

import retry_semantics.environments.ticket as ticket_module
from retry_semantics.environments.ticket import (
    CREATE_TICKET_COMMITTED,
    FrozenExecutableRequest,
    RequestValidationError,
    SourceStage,
    TicketEnvironment,
)
from retry_semantics.serialization import canonical_json_bytes, sha256_hex


def _execute_create(
    environment: TicketEnvironment,
    request: FrozenExecutableRequest,
    *,
    arm_id: str = "pair-family-bt-test-000001-H0:P2",
) -> bytes:
    return environment.execute_request(
        request.serialized_request,
        source_stage=SourceStage.RECOVERY,
        arm_id=arm_id,
    )


def test_empty_environment_has_frozen_authoritative_state() -> None:
    environment = TicketEnvironment.empty()

    assert environment.snapshot_bytes() == (
        b'{"mutation_events":[],"next_ticket_id":1,'
        b'"state_schema_version":"ticket-state-v1","tickets":[]}'
    )
    assert environment.state.next_ticket_id == 1
    assert environment.dispatch_count == 0


def test_create_is_append_only_and_duplicate_sensitive(make_request) -> None:
    environment = TicketEnvironment.empty()
    request = make_request()

    assert _execute_create(environment, request) == b'{"status":"created"}'
    assert _execute_create(environment, request) == b'{"status":"created"}'

    assert [ticket.ticket_id for ticket in environment.state.tickets] == [1, 2]
    assert environment.state.next_ticket_id == 3
    assert len(environment.state.tickets) == 2
    assert environment.state.tickets[0].model_visible_dict() == (
        environment.state.tickets[1].model_visible_dict()
    )
    assert len(environment.state.mutation_events) == 2
    assert environment.dispatch_count == 2

    list_request = make_request(tool="list_tickets", tool_call_id="read-duplicates")
    visible = json.loads(
        environment.execute_request(
            list_request.serialized_request,
            source_stage=SourceStage.RECOVERY,
            arm_id="arm-read",
        )
    )
    assert len(visible["tickets"]) == 2
    assert visible["tickets"][0] == visible["tickets"][1]


def test_each_create_records_one_deterministic_immutable_event(make_request) -> None:
    environment = TicketEnvironment.empty()
    request = make_request(tool_call_id="provider-call-7")

    _execute_create(environment, request)
    event = environment.state.mutation_events[0]

    assert event.event_id == "evt-000001"
    assert event.event_sequence == 1
    assert event.event_type == CREATE_TICKET_COMMITTED
    assert event.source_stage is SourceStage.RECOVERY
    assert event.arm_id == "pair-family-bt-test-000001-H0:P2"
    assert event.tool_call_id == "provider-call-7"
    assert event.serialized_request is request.serialized_request
    assert event.request_hash == request.request_hash
    assert event.ticket == environment.state.tickets[0]
    assert event.ticket is not environment.state.tickets[0]


def test_original_commit_accepts_null_arm_id(make_request) -> None:
    environment = TicketEnvironment.empty()
    request = make_request()

    environment.execute_request(
        request.serialized_request,
        source_stage=SourceStage.ORIGINAL,
        arm_id=None,
    )

    assert environment.state.mutation_events[0].source_stage is SourceStage.ORIGINAL
    assert environment.state.mutation_events[0].arm_id is None


def test_list_tickets_is_ordered_duplicate_preserving_and_read_only(make_request) -> None:
    environment = TicketEnvironment.empty()
    first = make_request(tool_call_id="call-1", title="First")
    second = make_request(tool_call_id="call-2", title="Second")
    _execute_create(environment, first)
    _execute_create(environment, second)
    before = environment.snapshot_bytes()
    list_request = make_request(tool="list_tickets", tool_call_id="read-1")

    first_result = environment.execute_request(
        list_request.serialized_request,
        source_stage=SourceStage.RECOVERY,
        arm_id="arm-read",
    )
    second_result = environment.execute_request(
        list_request.serialized_request,
        source_stage=SourceStage.RECOVERY,
        arm_id="arm-read",
    )

    assert first_result == second_result
    assert environment.snapshot_bytes() == before
    assert len(environment.state.mutation_events) == 2
    assert json.loads(first_result) == {
        "tickets": [
            {
                "customer_id": "CUST-001",
                "title": "First",
                "description": "The login page times out after 30 seconds.",
            },
            {
                "customer_id": "CUST-001",
                "title": "Second",
                "description": "The login page times out after 30 seconds.",
            },
        ]
    }


@pytest.mark.parametrize(
    "value",
    [
        {"tool": "create_ticket", "tool_call_id": "call", "arguments": {}},
        {
            "tool": "create_ticket",
            "tool_call_id": "call",
            "arguments": {
                "customer_id": "CUST-001",
                "title": "Title",
                "description": "Description",
                "extra": "forbidden",
            },
        },
        {
            "tool": "create_ticket",
            "tool_call_id": "call",
            "arguments": {
                "customer_id": "",
                "title": "Title",
                "description": "Description",
            },
        },
        {
            "tool": "create_ticket",
            "tool_call_id": "call",
            "arguments": {
                "customer_id": 123,
                "title": "Title",
                "description": "Description",
            },
        },
        {"tool": "delete_ticket", "tool_call_id": "call", "arguments": {}},
        {
            "tool": "create_ticket",
            "tool_call_id": "",
            "arguments": {
                "customer_id": "CUST-001",
                "title": "Title",
                "description": "Description",
            },
        },
    ],
)
def test_invalid_canonical_requests_make_zero_state_changes(value: dict) -> None:
    environment = TicketEnvironment.empty()
    before = environment.snapshot_bytes()

    with pytest.raises(RequestValidationError):
        environment.execute_request(
            canonical_json_bytes(value),
            source_stage=SourceStage.RECOVERY,
            arm_id="arm-invalid",
        )

    assert environment.snapshot_bytes() == before
    assert environment.dispatch_count == 1


@pytest.mark.parametrize(
    "bad_bytes",
    [
        b"not-json",
        b'{"arguments":{},"tool":"list_tickets","tool_call_id":"read"}\n',
        b' {"arguments":{},"tool":"list_tickets","tool_call_id":"read"}',
        b'\xef\xbb\xbf{"arguments":{},"tool":"list_tickets","tool_call_id":"read"}',
        b'{"arguments":{},"tool":"list_tickets","tool_call_id":"read",}',
        b"\xff",
    ],
)
def test_invalid_or_noncanonical_bytes_make_zero_state_changes(bad_bytes: bytes) -> None:
    environment = TicketEnvironment.empty()
    before = environment.snapshot_bytes()

    with pytest.raises(RequestValidationError):
        environment.execute_request(
            bad_bytes,
            source_stage=SourceStage.RECOVERY,
            arm_id="arm-invalid",
        )

    assert environment.snapshot_bytes() == before
    assert environment.dispatch_count == 1


@pytest.mark.parametrize(
    "arguments",
    [{"unexpected": True}, {"customer_id": "not empty"}],
)
def test_list_tickets_requires_exactly_empty_arguments(arguments: dict) -> None:
    environment = TicketEnvironment.empty()
    bad_request = canonical_json_bytes(
        {"arguments": arguments, "tool": "list_tickets", "tool_call_id": "read"}
    )

    with pytest.raises(RequestValidationError):
        environment.execute_request(
            bad_request,
            source_stage=SourceStage.RECOVERY,
            arm_id="arm-read",
        )

    assert environment.state == environment.state.empty()


def test_invalid_stage_metadata_cannot_partially_commit(make_request) -> None:
    environment = TicketEnvironment.empty()
    request = make_request()
    before = environment.snapshot_bytes()

    with pytest.raises(RequestValidationError):
        environment.execute_request(
            request.serialized_request,
            source_stage=SourceStage.RECOVERY,
            arm_id=None,
        )

    assert environment.snapshot_bytes() == before


def test_internal_failure_before_transition_publication_is_atomic(
    make_request, monkeypatch
) -> None:
    environment = TicketEnvironment.empty()
    request = make_request()
    before = environment.snapshot_bytes()

    def fail_hash(_: bytes) -> str:
        raise RuntimeError("simulated evaluator-side event failure")

    monkeypatch.setattr(ticket_module, "sha256_hex", fail_hash)
    with pytest.raises(RuntimeError, match="simulated"):
        _execute_create(environment, request)

    assert environment.snapshot_bytes() == before
    assert environment.state.next_ticket_id == 1
    assert environment.state.tickets == ()
    assert environment.state.mutation_events == ()


def test_frozen_byte_boundary_preserves_exact_buffer_and_checks_hash(make_request) -> None:
    environment = TicketEnvironment.empty()
    request = make_request()

    environment.execute_request(
        request.serialized_request,
        source_stage=SourceStage.ORIGINAL,
        arm_id=None,
        expected_request_hash=request.request_hash,
    )

    assert environment.state.mutation_events[0].serialized_request is request.serialized_request
    assert environment.state.mutation_events[0].request_hash == sha256_hex(
        request.serialized_request
    )


def test_frozen_request_envelope_has_exact_canonical_representation(make_request) -> None:
    request = make_request(
        tool_call_id="provider-call",
        customer_id="CUST-001",
        title="Exact title",
        description="Exact description",
    )

    assert request.serialized_request == (
        b'{"arguments":{"customer_id":"CUST-001",'
        b'"description":"Exact description","title":"Exact title"},'
        b'"tool":"create_ticket","tool_call_id":"provider-call"}'
    )


def test_frozen_request_representation_rejects_incoherent_bytes_and_hash(
    make_request,
) -> None:
    request = make_request()

    with pytest.raises(RequestValidationError, match="hash"):
        FrozenExecutableRequest(request.serialized_request, "0" * 64)
    with pytest.raises(RequestValidationError, match="not canonical"):
        FrozenExecutableRequest(b" " + request.serialized_request, request.request_hash)


def test_semantically_equal_but_byte_different_request_is_rejected(make_request) -> None:
    environment = TicketEnvironment.empty()
    frozen = make_request()
    decoded = json.loads(frozen.serialized_request)
    changed_bytes = json.dumps(decoded, sort_keys=False, indent=2).encode("utf-8")

    assert json.loads(changed_bytes) == json.loads(frozen.serialized_request)
    with pytest.raises(RequestValidationError, match="hash"):
        environment.execute_request(
            changed_bytes,
            source_stage=SourceStage.ORIGINAL,
            arm_id=None,
            expected_request_hash=frozen.request_hash,
        )
    assert environment.state == environment.state.empty()


def test_hash_mismatch_is_rejected_before_commit(make_request) -> None:
    environment = TicketEnvironment.empty()
    request = make_request()

    with pytest.raises(RequestValidationError, match="hash"):
        environment.execute_request(
            request.serialized_request,
            source_stage=SourceStage.ORIGINAL,
            arm_id=None,
            expected_request_hash="0" * 64,
        )

    assert environment.state == environment.state.empty()


def test_one_explicit_dispatch_causes_at_most_one_execution(make_request) -> None:
    environment = TicketEnvironment.empty()
    request = make_request()

    _execute_create(environment, request)

    assert environment.dispatch_count == 1
    assert len(environment.state.tickets) == 1
    assert len(environment.state.mutation_events) == 1


def test_retry_like_error_text_is_not_implicitly_retried() -> None:
    environment = TicketEnvironment.empty()

    with pytest.raises(RequestValidationError):
        environment.execute_request(
            b'"ToolError: timeout; please retry"',
            source_stage=SourceStage.RECOVERY,
            arm_id="arm-error",
        )

    assert environment.dispatch_count == 1
    assert environment.state == environment.state.empty()


def test_model_visible_results_never_expose_evaluator_metadata(make_request) -> None:
    environment = TicketEnvironment.empty()
    create = make_request(
        tool_call_id="secret-provider-call",
        customer_id="CUSTOMER-VISIBLE",
        title="Visible title",
        description="Visible description",
    )
    create_result = _execute_create(
        environment, create, arm_id="secret-arm-identifier"
    )
    list_request = make_request(tool="list_tickets", tool_call_id="secret-read-id")
    list_result = environment.execute_request(
        list_request.serialized_request,
        source_stage=SourceStage.RECOVERY,
        arm_id="secret-arm-identifier",
    )

    assert create_result == b'{"status":"created"}'
    assert set(json.loads(create_result)) == {"status"}
    assert set(json.loads(list_result)) == {"tickets"}
    assert set(json.loads(list_result)["tickets"][0]) == {
        "customer_id",
        "title",
        "description",
    }
    combined = create_result + list_result
    for forbidden in (
        b"ticket_id",
        b"event_id",
        b"event_sequence",
        b"state_schema_version",
        b"next_ticket_id",
        b"request_hash",
        b"source_stage",
        b"arm_id",
        b"secret-arm-identifier",
        b"secret-provider-call",
    ):
        assert forbidden not in combined
