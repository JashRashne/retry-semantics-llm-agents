from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

import retry_semantics.runtime.scheduled_trial as scheduled_trial_module
from retry_semantics.environments.ticket import (
    PrimaryClassification,
    SourceStage,
    TicketEnvironment,
)
from retry_semantics.models import (
    ModelAssistantMessage,
    ModelCallConfig,
    ModelRejectedGenerationError,
    ModelRequest,
    ModelResponse,
    ModelTimeoutError,
    ModelToolCall,
    ModelUsage,
    ToolChoice,
    freeze_json_value,
    parse_tool_arguments_json,
)
from retry_semantics.runtime.exact_replay import EXACT_REPLAY
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.runtime.original_generation import (
    OriginalGenerationFailureReason,
    V1CreateTicketTaskSpec,
)
from retry_semantics.runtime.regeneration import LLM_REGENERATION
from retry_semantics.runtime.regeneration_context import CANONICAL_AMBIGUITY_TEXT
from retry_semantics.runtime.scheduled_trial import (
    EligibleMatchedTrialResult,
    PreTreatmentFailureTrialResult,
    ScheduledTrialPlan,
    ScheduledTrialProtocolError,
    run_scheduled_trial,
)

EXPECTED = {
    "customer_id": "CUST-001",
    "title": "Login page timeout",
    "description": "The login page times out after 30 seconds.",
}
USER_TASK = (
    'Create exactly one support ticket for customer "CUST-001" with title '
    '"Login page timeout" and description '
    '"The login page times out after 30 seconds.".'
)
RAW_ORIGINAL_ARGUMENTS = (
    '{ "title": "Login page timeout", '
    '"description": "The login page times out after 30 seconds.", '
    '"customer_id": "CUST-001" }'
)


def _task() -> V1CreateTicketTaskSpec:
    return V1CreateTicketTaskSpec(
        customer_id=EXPECTED["customer_id"],
        expected_title=EXPECTED["title"],
        expected_description=EXPECTED["description"],
        user_task=USER_TASK,
    )


def _plan(
    *,
    hidden_world_order=(
        HiddenWorld.NOT_EXECUTED,
        HiddenWorld.EXECUTED_ACK_LOST,
    ),
    h0_arm_order=(EXACT_REPLAY, LLM_REGENERATION),
    h1_arm_order=(LLM_REGENERATION, EXACT_REPLAY),
) -> ScheduledTrialPlan:
    return ScheduledTrialPlan(
        manifest_id="engineering-validation",
        scheduled_attempt_ordinal=7,
        scenario_id="CREATE-001",
        task_spec=_task(),
        hidden_world_order=hidden_world_order,
        h0_arm_order=h0_arm_order,
        h1_arm_order=h1_arm_order,
    )


def _config(seed: int | None) -> ModelCallConfig:
    return ModelCallConfig(
        model="test-model",
        temperature=0.25,
        seed=seed,
        max_completion_tokens=128,
        tool_choice=ToolChoice.auto(),
    )


def _call(
    raw: str,
    *,
    call_id: object,
    tool_name: str = "create_ticket",
) -> ModelToolCall:
    parsed, arguments, error = parse_tool_arguments_json(raw)
    return ModelToolCall(
        tool_call_id=call_id,
        tool_name=tool_name,
        arguments_json=raw,
        parse_success=parsed,
        parsed_arguments=arguments,
        parse_error=error,
        tool_type="function",
    )


def _create_call(*, call_id: str) -> ModelToolCall:
    return _call(
        json.dumps(EXPECTED, separators=(",", ":")),
        call_id=call_id,
    )


def _list_call(*, call_id: str) -> ModelToolCall:
    return _call("{}", call_id=call_id, tool_name="list_tickets")


def _response(
    *calls: ModelToolCall,
    content: str | None = None,
    request_id: str = "fake-request",
) -> ModelResponse:
    return ModelResponse(
        assistant_message=ModelAssistantMessage(
            role="assistant",
            content=content,
            tool_calls=tuple(calls),
        ),
        finish_reason="tool_calls" if calls else "stop",
        provider="fake-provider",
        requested_model="test-model",
        returned_model="fake-model-v1",
        usage=ModelUsage(10, 4, 14),
        system_fingerprint="fake-fingerprint",
        provider_request_id=request_id,
    )


def _eligible_original() -> ModelResponse:
    return _response(
        _call(
            RAW_ORIGINAL_ARGUMENTS,
            call_id="provider-original-call",
        ),
        content="I will create the ticket.",
        request_id="original-request",
    )


class RecordingClient:
    def __init__(self, outcomes: list[ModelResponse | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self.outcomes:
            raise AssertionError("unexpected model invocation or hidden retry")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _run(client: RecordingClient, *, plan: ScheduledTrialPlan | None = None):
    return run_scheduled_trial(
        client,
        plan=plan or _plan(),
        initial_state=TicketEnvironment.empty(),
        original_generation_config=_config(11),
        regeneration_config=_config(200),
    )


def _forbid_recovery_boundaries(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("ineligible original generation reached recovery")

    monkeypatch.setattr(
        scheduled_trial_module, "construct_trial_family_states", forbidden
    )
    monkeypatch.setattr(scheduled_trial_module, "execute_exact_replay", forbidden)
    monkeypatch.setattr(
        scheduled_trial_module, "execute_llm_regeneration", forbidden
    )


def _contains_ticket_environment(value: object, seen: set[int] | None = None) -> bool:
    if isinstance(value, TicketEnvironment):
        return True
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        return False
    seen.add(identity)
    if is_dataclass(value) and not isinstance(value, type):
        return any(
            _contains_ticket_environment(getattr(value, item.name), seen)
            for item in fields(value)
        )
    if isinstance(value, Mapping):
        return any(
            _contains_ticket_environment(key, seen)
            or _contains_ticket_environment(item, seen)
            for key, item in value.items()
        )
    if isinstance(value, (tuple, list, set, frozenset)):
        return any(_contains_ticket_environment(item, seen) for item in value)
    return False


def test_ineligible_original_stops_before_all_recovery_without_resampling(
    monkeypatch,
) -> None:
    _forbid_recovery_boundaries(monkeypatch)
    response = _response(content="No tool call.")
    client = RecordingClient([response])

    result = _run(client)

    assert type(result) is PreTreatmentFailureTrialResult
    assert len(client.requests) == 1
    assert result.original_generation.reason is (
        OriginalGenerationFailureReason.NO_TOOL_CALL
    )
    assert result.original_generation.model_response is response
    assert result.original_generation.rejected_generation is None


def test_original_rejected_generation_stops_before_all_recovery(monkeypatch) -> None:
    _forbid_recovery_boundaries(monkeypatch)
    rejected = ModelRejectedGenerationError(
        provider="fake-provider",
        provider_error_code="tool_use_failed",
        failed_generation=freeze_json_value({"raw": "malformed tool syntax"}),
        provider_request_id="rejected-original",
    )
    client = RecordingClient([rejected])

    result = _run(client)

    assert type(result) is PreTreatmentFailureTrialResult
    assert len(client.requests) == 1
    assert result.original_generation.reason is (
        OriginalGenerationFailureReason.REJECTED_GENERATION
    )
    assert result.original_generation.rejected_generation is rejected
    assert result.original_generation.model_response is None


def test_original_provider_failure_propagates_once_without_recovery(
    monkeypatch,
) -> None:
    _forbid_recovery_boundaries(monkeypatch)
    client = RecordingClient([ModelTimeoutError("provider timeout")])

    with pytest.raises(ModelTimeoutError, match="provider timeout"):
        _run(client)

    assert len(client.requests) == 1


def test_eligible_trial_constructs_one_family_and_preserves_all_four_starts(
    monkeypatch,
) -> None:
    calls = 0
    context_calls = 0
    captured_families = []
    real_construct = scheduled_trial_module.construct_trial_family_states
    real_build_context = scheduled_trial_module.build_canonical_regeneration_context

    def counted_construct(**kwargs):
        nonlocal calls
        calls += 1
        family = real_construct(**kwargs)
        captured_families.append(family)
        return family

    def counted_build_context(**kwargs):
        nonlocal context_calls
        context_calls += 1
        return real_build_context(**kwargs)

    monkeypatch.setattr(
        scheduled_trial_module, "construct_trial_family_states", counted_construct
    )
    monkeypatch.setattr(
        scheduled_trial_module,
        "build_canonical_regeneration_context",
        counted_build_context,
    )
    initial = TicketEnvironment.empty()
    initial_snapshot = initial.snapshot_bytes()
    client = RecordingClient(
        [
            _eligible_original(),
            _response(content="H0 stop"),
            _response(content="H1 stop"),
        ]
    )

    result = run_scheduled_trial(
        client,
        plan=_plan(),
        initial_state=initial,
        original_generation_config=_config(11),
        regeneration_config=_config(200),
    )

    assert type(result) is EligibleMatchedTrialResult
    assert calls == 1
    assert context_calls == 1
    assert len(captured_families) == 1
    assert initial.snapshot_bytes() == initial_snapshot
    assert initial.dispatch_count == 0
    evidence = result.family_construction
    assert evidence.initial_state_snapshot == initial_snapshot
    assert evidence.not_executed.original_request_dispatch_count == 0
    assert evidence.executed_ack_lost.original_request_dispatch_count == 1
    assert len(
        json.loads(evidence.not_executed.post_ambiguity_snapshot)["mutation_events"]
    ) == 0
    h1_state = json.loads(evidence.executed_ack_lost.post_ambiguity_snapshot)
    assert len(h1_state["tickets"]) == len(h1_state["mutation_events"]) == 1
    assert h1_state["mutation_events"][0]["source_stage"] == "ORIGINAL"
    assert h1_state["mutation_events"][0]["arm_id"] is None
    for world in (evidence.not_executed, evidence.executed_ack_lost):
        assert world.exact_replay_starting_state_snapshot == (
            world.llm_regeneration_starting_state_snapshot
        ) == world.post_ambiguity_snapshot
        assert world.exact_replay_starting_state_hash == (
            world.llm_regeneration_starting_state_hash
        ) == world.post_ambiguity_state_hash
    execution_family = captured_families[0]
    for world in (
        execution_family.not_executed,
        execution_family.executed_ack_lost,
    ):
        assert world.arm_states.exact_replay_state.environment is not (
            world.arm_states.llm_regeneration_state.environment
        )


def test_returned_result_hierarchy_contains_no_ticket_environment() -> None:
    client = RecordingClient(
        [
            _eligible_original(),
            _response(content="H0 stop"),
            _response(content="H1 stop"),
        ]
    )

    result = _run(client)

    assert type(result) is EligibleMatchedTrialResult
    assert not hasattr(result, "trial_family_states")
    assert not _contains_ticket_environment(result)
    assert not _contains_ticket_environment(result.family_construction)


def test_replay_oracle_arm_ids_and_no_replay_model_calls() -> None:
    client = RecordingClient(
        [
            _eligible_original(),
            _response(content="H0 stop"),
            _response(content="H1 stop"),
        ]
    )

    result = _run(client)

    assert type(result) is EligibleMatchedTrialResult
    assert result.h0_replay.evaluation.primary_classification is (
        PrimaryClassification.CORRECT
    )
    assert result.h1_replay.evaluation.primary_classification is (
        PrimaryClassification.DUPLICATE_EFFECT
    )
    assert result.h0_replay.additional_llm_calls == 0
    assert result.h1_replay.additional_llm_calls == 0
    assert len(client.requests) == 3
    assert result.plan.arm_id(HiddenWorld.NOT_EXECUTED, EXACT_REPLAY).endswith(
        "-H0:P1"
    )
    assert result.plan.arm_id(HiddenWorld.EXECUTED_ACK_LOST, EXACT_REPLAY).endswith(
        "-H1:P1"
    )


def test_first_regeneration_requests_are_fully_matched_and_world_blind() -> None:
    client = RecordingClient(
        [
            _eligible_original(),
            _response(content="H0 stop"),
            _response(content="H1 stop"),
        ]
    )

    result = _run(client)

    assert type(result) is EligibleMatchedTrialResult
    h0 = result.h0_regeneration.model_invocations[0]
    h1 = result.h1_regeneration.model_invocations[0]
    assert h0.model_request == h1.model_request
    assert h0.model_request.messages == result.regeneration_context.messages
    assert h0.model_request.tools == result.regeneration_context.tools
    assert h0.model_request.model_config == h1.model_request.model_config
    assert h0.derived_seed == h1.derived_seed == 200
    original_call = h0.model_request.messages[2].tool_calls[0]
    assert original_call.arguments_json == RAW_ORIGINAL_ARGUMENTS
    assert h0.model_request.messages[3].content == CANONICAL_AMBIGUITY_TEXT
    encoded = json.dumps(
        {
            "messages": [message.as_dict() for message in h0.model_request.messages],
            "tools": [tool.as_dict() for tool in h0.model_request.tools],
        }
    )
    for hidden_value in (
        "NOT_EXECUTED",
        "EXECUTED_ACK_LOST",
        result.plan.arm_id(HiddenWorld.NOT_EXECUTED, LLM_REGENERATION),
        result.plan.arm_id(HiddenWorld.EXECUTED_ACK_LOST, LLM_REGENERATION),
        result.family_construction.not_executed.post_ambiguity_state_hash,
        result.family_construction.executed_ack_lost.post_ambiguity_state_hash,
    ):
        assert hidden_value not in encoded


def test_matched_seed_trajectories_ignore_world_and_arm_identity() -> None:
    trajectory = [
        _response(_list_call(call_id="read-0")),
        _response(_list_call(call_id="read-1")),
        _response(content="done"),
    ]
    client = RecordingClient([_eligible_original(), *trajectory, *trajectory])

    result = _run(client)

    assert type(result) is EligibleMatchedTrialResult
    assert [
        invocation.model_call_index
        for invocation in result.h0_regeneration.model_invocations
    ] == [0, 1, 2]
    assert [
        invocation.model_call_index
        for invocation in result.h1_regeneration.model_invocations
    ] == [0, 1, 2]
    assert [
        invocation.derived_seed
        for invocation in result.h0_regeneration.model_invocations
    ] == [200, 201, 202]
    assert [
        invocation.derived_seed
        for invocation in result.h1_regeneration.model_invocations
    ] == [200, 201, 202]
    for h0, h1 in zip(
        result.h0_regeneration.model_invocations,
        result.h1_regeneration.model_invocations,
        strict=True,
    ):
        assert h0.model_request.model_config == h1.model_request.model_config


def test_state_revealing_divergence_begins_only_after_model_selected_read() -> None:
    trajectory = [
        _response(_list_call(call_id="inspect")),
        _response(content="done"),
    ]
    client = RecordingClient([_eligible_original(), *trajectory, *trajectory])

    result = _run(client)

    assert type(result) is EligibleMatchedTrialResult
    h0_calls = result.h0_regeneration.model_invocations
    h1_calls = result.h1_regeneration.model_invocations
    assert h0_calls[0].model_request == h1_calls[0].model_request
    assert h0_calls[1].model_request.messages[:-1] == (
        h1_calls[1].model_request.messages[:-1]
    )
    assert h0_calls[1].model_request.messages[-1].content == '{"tickets":[]}'
    assert json.loads(h1_calls[1].model_request.messages[-1].content or "") == {
        "tickets": [EXPECTED]
    }
    assert h0_calls[1].derived_seed == h1_calls[1].derived_seed == 201


def test_policy_mutations_preserve_start_evidence_and_arm_isolation(
    monkeypatch,
) -> None:
    captured_families = []
    real_construct = scheduled_trial_module.construct_trial_family_states

    def capture_constructed_family(**kwargs):
        family = real_construct(**kwargs)
        captured_families.append(family)
        return family

    monkeypatch.setattr(
        scheduled_trial_module,
        "construct_trial_family_states",
        capture_constructed_family,
    )
    client = RecordingClient(
        [
            _eligible_original(),
            _response(_create_call(call_id="h0-regeneration-create")),
            _response(content="H0 done"),
            _response(_list_call(call_id="h1-read")),
            _response(content="H1 done"),
        ]
    )

    result = _run(client)

    assert type(result) is EligibleMatchedTrialResult
    assert len(captured_families) == 1
    family = captured_families[0]
    evidence = result.family_construction
    h0_replay = family.not_executed.arm_states.exact_replay_state.environment
    h0_regeneration = (
        family.not_executed.arm_states.llm_regeneration_state.environment
    )
    h1_replay = family.executed_ack_lost.arm_states.exact_replay_state.environment
    h1_regeneration = (
        family.executed_ack_lost.arm_states.llm_regeneration_state.environment
    )
    assert len(h0_replay.state.tickets) == len(h0_regeneration.state.tickets) == 1
    assert len(h1_replay.state.tickets) == 2
    assert len(h1_regeneration.state.tickets) == 1
    assert json.loads(evidence.not_executed.post_ambiguity_snapshot)["tickets"] == []
    assert len(
        json.loads(evidence.executed_ack_lost.post_ambiguity_snapshot)["tickets"]
    ) == 1
    for world in (evidence.not_executed, evidence.executed_ack_lost):
        assert world.exact_replay_starting_state_snapshot == (
            world.llm_regeneration_starting_state_snapshot
        ) == world.post_ambiguity_snapshot
        assert world.exact_replay_starting_state_hash == (
            world.llm_regeneration_starting_state_hash
        ) == world.post_ambiguity_state_hash
    assert result.h0_replay.final_state_snapshot != (
        evidence.not_executed.exact_replay_starting_state_snapshot
    )
    assert result.h0_regeneration.final_state_snapshot != (
        evidence.not_executed.llm_regeneration_starting_state_snapshot
    )
    assert result.h1_replay.final_state_snapshot != (
        evidence.executed_ack_lost.exact_replay_starting_state_snapshot
    )
    assert result.h1_regeneration.final_state_snapshot == (
        evidence.executed_ack_lost.llm_regeneration_starting_state_snapshot
    )
    assert result.h0_replay.final_state_snapshot == h0_replay.snapshot_bytes()
    assert result.h0_regeneration.final_state_snapshot == (
        h0_regeneration.snapshot_bytes()
    )
    assert result.h1_replay.final_state_snapshot == h1_replay.snapshot_bytes()
    assert result.h1_regeneration.final_state_snapshot == (
        h1_regeneration.snapshot_bytes()
    )
    assert h0_replay.state.mutation_events[-1].arm_id == result.plan.arm_id(
        HiddenWorld.NOT_EXECUTED, EXACT_REPLAY
    )
    assert h0_regeneration.state.mutation_events[-1].arm_id == result.plan.arm_id(
        HiddenWorld.NOT_EXECUTED, LLM_REGENERATION
    )
    assert h1_replay.state.mutation_events[-1].arm_id == result.plan.arm_id(
        HiddenWorld.EXECUTED_ACK_LOST, EXACT_REPLAY
    )
    assert all(
        event.arm_id is None for event in h1_regeneration.state.mutation_events
    )
    assert not _contains_ticket_environment(evidence)


def test_one_frozen_m_and_historical_call_evidence_feed_every_arm() -> None:
    client = RecordingClient(
        [
            _eligible_original(),
            _response(content="H0 stop"),
            _response(content="H1 stop"),
        ]
    )

    result = _run(client)

    assert type(result) is EligibleMatchedTrialResult
    original = result.original_generation
    evidence = result.family_construction
    assert evidence.frozen_original_request == original.frozen_executable_request
    assert evidence.serialized_original_request == original.serialized_original_request
    assert evidence.original_request_hash == original.original_request_hash
    assert result.regeneration_context.original_assistant_message == (
        original.original_assistant_message
    )
    h1_original = evidence.executed_ack_lost.post_ambiguity_snapshot
    h1_original_event = json.loads(h1_original)["mutation_events"][0]
    assert h1_original_event["serialized_request"] == (
        original.serialized_original_request.decode("utf-8")
    )
    assert h1_original_event["request_hash"] == original.original_request_hash
    for replay_result in (
        result.h0_replay,
        result.h1_replay,
    ):
        replay_event = json.loads(replay_result.final_state_snapshot)[
            "mutation_events"
        ][-1]
        assert replay_event["serialized_request"] == (
            original.serialized_original_request.decode("utf-8")
        )
        assert replay_event["request_hash"] == original.original_request_hash
    for regeneration in (result.h0_regeneration, result.h1_regeneration):
        historical = regeneration.model_invocations[0].model_request.messages[2]
        assert historical is original.original_assistant_message
        assert historical.tool_calls[0].arguments_json == RAW_ORIGINAL_ARGUMENTS


def test_actual_serial_execution_follows_all_materialized_order_values(
    monkeypatch,
) -> None:
    order: list[str] = []
    real_replay = scheduled_trial_module.execute_exact_replay
    real_regeneration = scheduled_trial_module.execute_llm_regeneration

    def recorded_replay(*args, **kwargs):
        order.append(kwargs["arm_id"])
        return real_replay(*args, **kwargs)

    def recorded_regeneration(*args, **kwargs):
        order.append(kwargs["arm_id"])
        return real_regeneration(*args, **kwargs)

    monkeypatch.setattr(scheduled_trial_module, "execute_exact_replay", recorded_replay)
    monkeypatch.setattr(
        scheduled_trial_module, "execute_llm_regeneration", recorded_regeneration
    )
    plan = _plan(
        hidden_world_order=(
            HiddenWorld.EXECUTED_ACK_LOST,
            HiddenWorld.NOT_EXECUTED,
        ),
        h0_arm_order=(LLM_REGENERATION, EXACT_REPLAY),
        h1_arm_order=(EXACT_REPLAY, LLM_REGENERATION),
    )
    client = RecordingClient(
        [
            _eligible_original(),
            _response(content="H1 stop"),
            _response(content="H0 stop"),
        ]
    )

    result = _run(client, plan=plan)

    assert type(result) is EligibleMatchedTrialResult
    assert order == [
        plan.arm_id(HiddenWorld.EXECUTED_ACK_LOST, EXACT_REPLAY),
        plan.arm_id(HiddenWorld.EXECUTED_ACK_LOST, LLM_REGENERATION),
        plan.arm_id(HiddenWorld.NOT_EXECUTED, LLM_REGENERATION),
        plan.arm_id(HiddenWorld.NOT_EXECUTED, EXACT_REPLAY),
    ]


def test_deterministic_fake_trials_have_equivalent_logical_results_and_hashes() -> None:
    outcomes = [
        _eligible_original(),
        _response(content="H0 stop"),
        _response(content="H1 stop"),
    ]

    first = _run(RecordingClient(outcomes))
    second = _run(RecordingClient(outcomes))

    assert type(first) is type(second) is EligibleMatchedTrialResult
    assert first.plan == second.plan
    assert first.original_generation == second.original_generation
    assert first.family_construction == second.family_construction
    assert first.regeneration_context == second.regeneration_context
    assert first.original_request_hash == second.original_request_hash
    assert first.initial_state_hash == second.initial_state_hash
    assert first.h0_replay == second.h0_replay
    assert first.h0_regeneration == second.h0_regeneration
    assert first.h1_replay == second.h1_replay
    assert first.h1_regeneration == second.h1_regeneration


@pytest.mark.parametrize(
    "replacement",
    [
        {"hidden_world_order": (HiddenWorld.NOT_EXECUTED,) * 2},
        {"h0_arm_order": (EXACT_REPLAY, EXACT_REPLAY)},
        {"h1_arm_order": (LLM_REGENERATION, LLM_REGENERATION)},
    ],
)
def test_schedule_rejects_non_factorial_or_duplicate_orders(replacement) -> None:
    values = {
        "hidden_world_order": (
            HiddenWorld.NOT_EXECUTED,
            HiddenWorld.EXECUTED_ACK_LOST,
        ),
        "h0_arm_order": (EXACT_REPLAY, LLM_REGENERATION),
        "h1_arm_order": (LLM_REGENERATION, EXACT_REPLAY),
    }
    values.update(replacement)

    with pytest.raises(ScheduledTrialProtocolError):
        _plan(**values)


def test_protocol_identifiers_and_results_are_immutable() -> None:
    plan = _plan()
    client = RecordingClient(
        [
            _eligible_original(),
            _response(content="H0 stop"),
            _response(content="H1 stop"),
        ]
    )
    result = _run(client, plan=plan)

    assert plan.base_trial_id == "bt-engineering-validation-000007"
    assert plan.trial_family_id == "family-bt-engineering-validation-000007"
    assert plan.pair_id(HiddenWorld.NOT_EXECUTED) == (
        "pair-family-bt-engineering-validation-000007-H0"
    )
    assert plan.arm_id(HiddenWorld.EXECUTED_ACK_LOST, LLM_REGENERATION) == (
        "pair-family-bt-engineering-validation-000007-H1:P2"
    )
    assert plan.run_id(HiddenWorld.EXECUTED_ACK_LOST, LLM_REGENERATION) == (
        "run-pair-family-bt-engineering-validation-000007-H1:P2"
    )
    with pytest.raises(FrozenInstanceError):
        plan.manifest_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.h0_replay = result.h1_replay  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.family_construction.initial_state_hash = "0" * 64  # type: ignore[misc]
