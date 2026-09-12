from __future__ import annotations

from dataclasses import fields

import pytest

from retry_semantics.environments.ticket import SourceStage, TicketEnvironment
from retry_semantics.runtime.hidden_worlds import (
    ConstructedHiddenWorld,
    HiddenWorld,
    TrialFamilyConstructionError,
    construct_trial_family_states,
)


def _construct(initial_state, request):
    return construct_trial_family_states(
        initial_state=initial_state,
        frozen_original_request=request,
        serialized_original_request=request.serialized_request,
        original_request_hash=request.request_hash,
        original_source_stage=SourceStage.ORIGINAL,
        original_arm_id=None,
    )


def test_h0_is_untouched_and_dispatches_zero_times(make_request) -> None:
    family = _construct(TicketEnvironment.empty(), make_request())
    h0 = family.not_executed
    state = h0.arm_states.exact_replay_state.environment.state

    assert h0.hidden_world is HiddenWorld.NOT_EXECUTED
    assert h0.original_request_executed is False
    assert h0.original_request_dispatch_count == 0
    assert h0.original_commit_event_ids == ()
    assert h0.post_ambiguity_snapshot == family.initial_state_snapshot
    assert h0.post_ambiguity_state_hash == family.initial_state_hash
    assert state.tickets == ()
    assert state.mutation_events == ()
    assert state.next_ticket_id == 1


def test_h1_dispatches_once_and_commits_one_intended_ticket(make_request) -> None:
    request = make_request()
    family = _construct(TicketEnvironment.empty(), request)
    h1 = family.executed_ack_lost
    state = h1.arm_states.exact_replay_state.environment.state

    assert h1.hidden_world is HiddenWorld.EXECUTED_ACK_LOST
    assert h1.original_request_executed is True
    assert h1.original_request_dispatch_count == 1
    assert h1.original_commit_event_ids == ("evt-000001",)
    assert len(state.tickets) == 1
    assert state.tickets[0].model_visible_dict() == {
        "customer_id": "CUST-001",
        "title": "Login page timeout",
        "description": "The login page times out after 30 seconds.",
    }
    assert len(state.mutation_events) == 1
    assert state.next_ticket_id == 2


def test_h1_original_event_is_pre_policy_and_uses_exact_m(make_request) -> None:
    request = make_request(tool_call_id="original-provider-call")
    family = _construct(TicketEnvironment.empty(), request)
    event = (
        family.executed_ack_lost.arm_states.exact_replay_state.environment.state
        .mutation_events[0]
    )

    assert event.source_stage is SourceStage.ORIGINAL
    assert event.arm_id is None
    assert event.tool_call_id == "original-provider-call"
    assert event.serialized_request == request.serialized_request
    assert event.request_hash == request.request_hash


def test_preparing_two_h1_arm_states_does_not_dispatch_m_twice(make_request) -> None:
    family = _construct(TicketEnvironment.empty(), make_request())
    h1 = family.executed_ack_lost

    assert h1.original_request_dispatch_count == 1
    assert h1.arm_states.exact_replay_state.environment.dispatch_count == 0
    assert h1.arm_states.llm_regeneration_state.environment.dispatch_count == 0
    assert len(h1.arm_states.exact_replay_state.environment.state.tickets) == 1
    assert len(h1.arm_states.llm_regeneration_state.environment.state.tickets) == 1


def test_wrong_m_hash_fails_before_dispatch_or_state_change(make_request) -> None:
    initial = TicketEnvironment.empty()
    request = make_request()
    before = initial.snapshot_bytes()

    with pytest.raises(TrialFamilyConstructionError, match="request hash"):
        construct_trial_family_states(
            initial_state=initial,
            frozen_original_request=request,
            serialized_original_request=request.serialized_request,
            original_request_hash="0" * 64,
            original_source_stage=SourceStage.ORIGINAL,
            original_arm_id=None,
        )

    assert initial.dispatch_count == 0
    assert initial.snapshot_bytes() == before


def test_non_create_original_request_fails_without_partial_commit(make_request) -> None:
    initial = TicketEnvironment.empty()
    request = make_request(tool="list_tickets")
    before = initial.snapshot_bytes()

    with pytest.raises(TrialFamilyConstructionError, match="create_ticket"):
        _construct(initial, request)

    assert initial.dispatch_count == 0
    assert initial.snapshot_bytes() == before


@pytest.mark.parametrize(
    ("source_stage", "arm_id"),
    [
        (SourceStage.RECOVERY, "future-arm"),
        (SourceStage.ORIGINAL, "premature-arm"),
    ],
)
def test_invalid_original_source_metadata_fails_before_dispatch(
    make_request, source_stage, arm_id
) -> None:
    initial = TicketEnvironment.empty()
    request = make_request()

    with pytest.raises(TrialFamilyConstructionError):
        construct_trial_family_states(
            initial_state=initial,
            frozen_original_request=request,
            serialized_original_request=request.serialized_request,
            original_request_hash=request.request_hash,
            original_source_stage=source_stage,
            original_arm_id=arm_id,
        )

    assert initial.dispatch_count == 0
    assert initial.state == initial.state.empty()


def test_success_acknowledgement_is_not_retained(make_request) -> None:
    family = _construct(TicketEnvironment.empty(), make_request())

    stored_fields = {field.name for field in fields(ConstructedHiddenWorld)}
    assert "response" not in stored_fields
    assert "acknowledgement" not in stored_fields
    assert (
        b'{"status":"created"}'
        not in family.executed_ack_lost.post_ambiguity_snapshot
    )
