from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, fields

import pytest

from retry_semantics.environments.ticket import (
    PrimaryClassification,
    SourceStage,
    TicketEnvironment,
)
from retry_semantics.runtime.exact_replay import (
    EXACT_REPLAY,
    REPLAY_EXECUTED,
    ReplayProtocolError,
    execute_exact_replay,
)
from retry_semantics.runtime.hidden_worlds import construct_trial_family_states


def _construct(request):
    return construct_trial_family_states(
        initial_state=TicketEnvironment.empty(),
        frozen_original_request=request,
        serialized_original_request=request.serialized_request,
        original_request_hash=request.request_hash,
        original_source_stage=SourceStage.ORIGINAL,
        original_arm_id=None,
    )


def _replay(environment, request, arm_id: str):
    return execute_exact_replay(
        environment,
        frozen_request=request,
        serialized_original_request=request.serialized_request,
        original_request_hash=request.request_hash,
        arm_id=arm_id,
    )


def test_h0_replay_creates_exactly_one_intended_ticket(make_request) -> None:
    request = make_request()
    family = _construct(request)
    environment = family.not_executed.arm_states.exact_replay_state.environment

    result = _replay(environment, request, "test-H0-P1")

    assert result.policy == EXACT_REPLAY
    assert result.request_hash == request.request_hash
    assert result.recovery_tool_calls_attempted == 1
    assert result.recovery_tool_calls_executed == 1
    assert result.additional_llm_calls == 0
    assert result.model_visible_observation == '{"status":"created"}'
    assert result.committed_effect_event_ids == ("evt-000001",)
    assert result.final_state_snapshot == environment.snapshot_bytes()
    assert result.final_state_hash == environment.snapshot_hash()
    assert result.termination_reason == REPLAY_EXECUTED
    assert result.evaluation.primary_classification is PrimaryClassification.CORRECT
    assert result.evaluation.correct is True
    assert result.evaluation.effect_multiplicity == 1
    assert result.evaluation.unintended_ticket_count == 0

    event = environment.state.mutation_events[0]
    assert event.source_stage is SourceStage.RECOVERY
    assert event.arm_id == "test-H0-P1"


def test_h1_replay_deterministically_duplicates_the_intended_effect(
    make_request,
) -> None:
    request = make_request(tool_call_id="same-provider-call")
    family = _construct(request)
    environment = family.executed_ack_lost.arm_states.exact_replay_state.environment

    result = _replay(environment, request, "test-H1-P1")

    assert result.evaluation.primary_classification is (
        PrimaryClassification.DUPLICATE_EFFECT
    )
    assert result.evaluation.correct is False
    assert result.evaluation.duplicate_effect is True
    assert result.evaluation.effect_multiplicity == 2
    assert result.evaluation.unintended_ticket_count == 0
    assert result.committed_effect_event_ids == ("evt-000002",)

    original, recovery = environment.state.mutation_events
    assert original.source_stage is SourceStage.ORIGINAL
    assert original.arm_id is None
    assert recovery.source_stage is SourceStage.RECOVERY
    assert recovery.arm_id == "test-H1-P1"
    assert original.serialized_request == recovery.serialized_request
    assert original.request_hash == recovery.request_hash == request.request_hash

    first, second = environment.state.tickets
    assert first.model_visible_dict() == second.model_visible_dict()
    assert first.ticket_id != second.ticket_id


def test_replay_dispatches_the_same_frozen_bytes_object_exactly_once(
    make_request, monkeypatch
) -> None:
    request = make_request()
    environment = _construct(request).not_executed.arm_states.exact_replay_state.environment
    dispatched: list[bytes] = []
    original_execute = environment.execute_request

    def record_dispatch(serialized_request: bytes, **kwargs) -> bytes:
        dispatched.append(serialized_request)
        return original_execute(serialized_request, **kwargs)

    monkeypatch.setattr(environment, "execute_request", record_dispatch)
    dispatch_count_before = environment.dispatch_count

    _replay(environment, request, "test-H0-P1")

    assert dispatched == [request.serialized_request]
    assert dispatched[0] is request.serialized_request
    assert environment.dispatch_count - dispatch_count_before == 1


def test_replay_has_no_model_or_hidden_world_dependency_and_reads_no_tickets(
    make_request, monkeypatch
) -> None:
    request = make_request()
    family = _construct(request)
    signature = inspect.signature(execute_exact_replay)
    result_fields = {item.name for item in fields(type(_replay(
        family.not_executed.arm_states.exact_replay_state.environment,
        request,
        "test-H0-P1",
    )))}

    assert "model" not in signature.parameters
    assert "hidden_world" not in signature.parameters
    assert "additional_llm_calls" in result_fields

    h1_environment = family.executed_ack_lost.arm_states.exact_replay_state.environment

    def fail_if_read() -> bytes:
        raise AssertionError("Exact Replay must not call list_tickets")

    monkeypatch.setattr(h1_environment, "_list_tickets_result", fail_if_read)
    result = _replay(h1_environment, request, "test-H1-P1")

    assert result.additional_llm_calls == 0
    assert result.recovery_tool_calls_executed == 1


def test_hash_mismatch_fails_before_dispatch_and_preserves_state(make_request) -> None:
    request = make_request()
    environment = _construct(request).not_executed.arm_states.exact_replay_state.environment
    before = environment.snapshot_bytes()
    dispatch_count_before = environment.dispatch_count

    with pytest.raises(ReplayProtocolError, match="hash"):
        execute_exact_replay(
            environment,
            frozen_request=request,
            serialized_original_request=request.serialized_request,
            original_request_hash="0" * 64,
            arm_id="test-H0-P1",
        )

    assert environment.dispatch_count == dispatch_count_before
    assert environment.snapshot_bytes() == before
    assert environment.state.mutation_events == ()


def test_incoherent_frozen_request_representations_fail_before_dispatch(
    make_request,
) -> None:
    frozen_request = make_request(tool_call_id="frozen-a", title="A")
    other_request = make_request(tool_call_id="frozen-b", title="B")
    environment = _construct(frozen_request).not_executed.arm_states.exact_replay_state.environment
    before = environment.snapshot_bytes()

    with pytest.raises(ReplayProtocolError, match="serialized_original_request"):
        execute_exact_replay(
            environment,
            frozen_request=frozen_request,
            serialized_original_request=other_request.serialized_request,
            original_request_hash=other_request.request_hash,
            arm_id="test-H0-P1",
        )

    assert environment.dispatch_count == 0
    assert environment.snapshot_bytes() == before
    assert environment.state.mutation_events == ()


def test_replay_mutates_only_its_two_selected_arm_clones(make_request) -> None:
    request = make_request()
    family = _construct(request)
    h0_replay = family.not_executed.arm_states.exact_replay_state.environment
    h0_regeneration = family.not_executed.arm_states.llm_regeneration_state.environment
    h1_replay = family.executed_ack_lost.arm_states.exact_replay_state.environment
    h1_regeneration = family.executed_ack_lost.arm_states.llm_regeneration_state.environment
    initial_snapshot = family.initial_state_snapshot
    h0_snapshot = family.not_executed.post_ambiguity_snapshot
    h1_snapshot = family.executed_ack_lost.post_ambiguity_snapshot

    _replay(h0_replay, request, "test-H0-P1")
    assert h0_regeneration.snapshot_bytes() == h0_snapshot
    assert h1_replay.snapshot_bytes() == h1_snapshot
    assert h1_regeneration.snapshot_bytes() == h1_snapshot

    _replay(h1_replay, request, "test-H1-P1")

    assert h0_regeneration.snapshot_bytes() == h0_snapshot
    assert h1_regeneration.snapshot_bytes() == h1_snapshot
    assert family.not_executed.post_ambiguity_snapshot == h0_snapshot
    assert family.executed_ack_lost.post_ambiguity_snapshot == h1_snapshot
    assert family.initial_state_snapshot == initial_snapshot


@pytest.mark.parametrize(
    ("world_name", "arm_id", "expected_multiplicity"),
    [
        ("not_executed", "test-H0-P1", 1),
        ("executed_ack_lost", "test-H1-P1", 2),
    ],
)
def test_same_policy_function_is_hidden_world_ignorant(
    make_request, world_name, arm_id, expected_multiplicity
) -> None:
    request = make_request()
    family = _construct(request)
    world = getattr(family, world_name)

    result = _replay(world.arm_states.exact_replay_state.environment, request, arm_id)

    assert result.evaluation.effect_multiplicity == expected_multiplicity


@pytest.mark.parametrize("world_name", ["not_executed", "executed_ack_lost"])
def test_replay_is_deterministic_from_the_same_snapshot_and_m(
    make_request, world_name
) -> None:
    request = make_request()
    family = _construct(request)
    starting_snapshot = getattr(family, world_name).post_ambiguity_snapshot
    first = TicketEnvironment.clone_from_snapshot(starting_snapshot)
    second = TicketEnvironment.clone_from_snapshot(starting_snapshot)

    first_result = _replay(first, request, "same-arm-P1")
    second_result = _replay(second, request, "same-arm-P1")

    assert first_result == second_result
    assert first_result.final_state_snapshot == second_result.final_state_snapshot
    assert first_result.final_state_hash == second_result.final_state_hash


def test_replay_result_is_immutable(make_request) -> None:
    request = make_request()
    environment = _construct(request).not_executed.arm_states.exact_replay_state.environment
    result = _replay(environment, request, "test-H0-P1")

    with pytest.raises(FrozenInstanceError):
        result.request_hash = "0" * 64  # type: ignore[misc]


def test_executor_error_gets_no_fallback_or_second_attempt(
    make_request, monkeypatch
) -> None:
    request = make_request()
    environment = _construct(request).not_executed.arm_states.exact_replay_state.environment
    before = environment.snapshot_bytes()
    attempts: list[bytes] = []

    def fail_dispatch(serialized_request: bytes, **kwargs) -> bytes:
        attempts.append(serialized_request)
        raise RuntimeError("deterministic executor failure")

    monkeypatch.setattr(environment, "execute_request", fail_dispatch)

    with pytest.raises(RuntimeError, match="executor failure"):
        _replay(environment, request, "test-H0-P1")

    assert attempts == [request.serialized_request]
    assert environment.snapshot_bytes() == before
