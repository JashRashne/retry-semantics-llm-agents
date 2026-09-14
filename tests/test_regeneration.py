from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace

import pytest

from retry_semantics.environments.ticket import (
    PrimaryClassification,
    RequestValidationError,
    SourceStage,
    TicketEnvironment,
)
from retry_semantics.models import (
    ModelAssistantMessage,
    ModelCallConfig,
    ModelRejectedGenerationError,
    ModelRequest,
    ModelResponse,
    ModelResponseError,
    ModelTimeoutError,
    ModelToolCall,
    ModelUsage,
    ToolChoice,
    build_groq_chat_completion_kwargs,
    freeze_json_value,
    parse_tool_arguments_json,
)
from retry_semantics.runtime.hidden_worlds import construct_trial_family_states
from retry_semantics.runtime.regeneration import (
    ACTION_BUDGET_EXCEEDED,
    BUDGET_REJECTED_TOOL_CALL,
    INFRASTRUCTURE_FAILURE,
    INVALID,
    INVALID_MODEL_TOOL_CALL,
    INVALID_TOOL_CALL,
    MODEL_REJECTED_GENERATION,
    MODEL_STOP,
    MODEL_STOPPED,
    NOT_APPLICABLE,
    TOOL_CALL,
    VALID,
    execute_llm_regeneration,
)
from retry_semantics.runtime.regeneration_context import (
    FROZEN_TOOL_CATALOG,
    CanonicalContextMessage,
    CanonicalToolCall,
    CreateTicketArguments,
    ModelVisibleToolCall,
    build_canonical_regeneration_context,
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


def _family(request):
    return construct_trial_family_states(
        initial_state=TicketEnvironment.empty(),
        frozen_original_request=request,
        serialized_original_request=request.serialized_request,
        original_request_hash=request.request_hash,
        original_source_stage=SourceStage.ORIGINAL,
        original_arm_id=None,
    )


def _context(request):
    value = json.loads(request.serialized_request)
    raw = (
        '{ "title": "Login page timeout", '
        '"description": "The login page times out after 30 seconds.", '
        '"customer_id": "CUST-001" }'
    )
    assistant = CanonicalContextMessage(
        role="assistant",
        content="I will create the ticket.",
        tool_calls=(
            CanonicalToolCall(
                tool_call_id=value["tool_call_id"],
                tool=value["tool"],
                arguments_json=raw,
                arguments=CreateTicketArguments(**EXPECTED),
            ),
        ),
        tool_call_id=None,
    )
    return build_canonical_regeneration_context(
        user_task=USER_TASK,
        frozen_original_request=request,
        original_assistant_message=assistant,
    )


def _config(seed: int | None = 100) -> ModelCallConfig:
    return ModelCallConfig(
        model="test-model",
        temperature=0.25,
        seed=seed,
        max_completion_tokens=128,
        tool_choice=ToolChoice.auto(),
        top_p=0.7,
        parallel_tool_calls=False,
        provider_parameters={"reasoning_effort": "medium"},
    )


def _call(
    raw: str,
    *,
    call_id: object = "call-1",
    tool_name: str = "create_ticket",
    tool_type: str | None = "function",
) -> ModelToolCall:
    parsed, arguments, error = parse_tool_arguments_json(raw)
    return ModelToolCall(
        tool_call_id=call_id,
        tool_name=tool_name,
        arguments_json=raw,
        parse_success=parsed,
        parsed_arguments=arguments,
        parse_error=error,
        tool_type=tool_type,
    )


def _create_call(
    *, call_id: object = "create-1", arguments: dict[str, object] | None = None
) -> ModelToolCall:
    return _call(
        json.dumps(arguments or EXPECTED, separators=(",", ":")),
        call_id=call_id,
    )


def _list_call(*, call_id: object = "list-1", raw: str = "{}") -> ModelToolCall:
    return _call(raw, call_id=call_id, tool_name="list_tickets")


def _response(
    *calls: ModelToolCall,
    content: str | None = None,
    request_id: str = "provider-response",
) -> ModelResponse:
    return ModelResponse(
        assistant_message=ModelAssistantMessage(
            role="assistant", content=content, tool_calls=tuple(calls)
        ),
        finish_reason="tool_calls" if calls else "stop",
        provider="fake-provider",
        requested_model="test-model",
        returned_model="fake-model-v1",
        usage=ModelUsage(10, 4, 14),
        system_fingerprint="fake-fingerprint",
        provider_request_id=request_id,
    )


class ScriptedClient:
    def __init__(self, outcomes: list[ModelResponse | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self.outcomes:
            raise AssertionError("unexpected hidden model retry")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _execute(environment, request, outcomes, *, seed=100, arm_id="arm-P2"):
    client = ScriptedClient(outcomes)
    config = _config(seed)
    result = execute_llm_regeneration(
        environment,
        context=_context(request),
        client=client,
        model_config=config,
        arm_id=arm_id,
    )
    return result, client, config


def _rejected() -> ModelRejectedGenerationError:
    return ModelRejectedGenerationError(
        provider="fake-provider",
        provider_error_code="tool_use_failed",
        failed_generation=freeze_json_value(
            {"attempted": "{'customer_id': 'CUST-001'}", "offset": 9}
        ),
        provider_request_id="rejected-request-9",
    )


def test_initial_h0_h1_requests_are_matched_and_hide_authoritative_state(
    make_request,
) -> None:
    original = make_request(tool_call_id="original-provider-call")
    family = _family(original)
    h0 = family.not_executed.arm_states.llm_regeneration_state.environment
    h1 = family.executed_ack_lost.arm_states.llm_regeneration_state.environment
    h0_result, h0_client, _ = _execute(h0, original, [_response(content="stop")])
    h1_result, h1_client, _ = _execute(h1, original, [_response(content="stop")])

    assert h0_client.requests[0] == h1_client.requests[0]
    assert h0_client.requests[0].messages == _context(original).messages
    assert h0_client.requests[0].tools is FROZEN_TOOL_CATALOG
    assert h0_client.requests[0].model_config == h1_client.requests[0].model_config
    assert h0_result.model_invocations[0].derived_seed == 100
    assert h1_result.model_invocations[0].derived_seed == 100
    encoded = json.dumps(
        [message.as_dict() for message in h0_client.requests[0].messages]
    )
    for hidden in (
        "NOT_EXECUTED",
        "EXECUTED_ACK_LOST",
        "ticket_id",
        "mutation_events",
        family.not_executed.post_ambiguity_state_hash,
        family.executed_ack_lost.post_ambiguity_state_hash,
    ):
        assert hidden not in encoded


@pytest.mark.parametrize(
    ("base_seed", "expected"),
    [(100, [100, 101, 102, 103]), (None, [None, None, None, None])],
)
def test_seed_derivation_tracks_only_model_invocation_ordinal(
    make_request, base_seed, expected
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    outcomes = [
        _response(_list_call(call_id="read-1")),
        _response(_list_call(call_id="read-2")),
        _response(_list_call(call_id="read-3")),
        _response(content="finished"),
    ]

    result, client, config = _execute(
        environment, original, outcomes, seed=base_seed
    )

    assert [request.model_config.seed for request in client.requests] == expected
    assert [item.model_call_index for item in result.model_invocations] == [0, 1, 2, 3]
    assert [item.derived_seed for item in result.model_invocations] == expected
    assert config.seed == base_seed


def test_seed_is_independent_of_tool_action_count_arm_and_world(make_request) -> None:
    original = make_request()
    family = _family(original)
    first_response = _response(
        _list_call(call_id="read-1"), _list_call(call_id="read-2")
    )
    scripts = [first_response, _response(_list_call(call_id="read-3")), _response(content="done")]
    h0_result, h0_client, _ = _execute(
        family.not_executed.arm_states.llm_regeneration_state.environment,
        original,
        scripts,
        arm_id="different-H0-arm",
    )
    h1_result, h1_client, _ = _execute(
        family.executed_ack_lost.arm_states.llm_regeneration_state.environment,
        original,
        scripts,
        arm_id="different-H1-arm",
    )

    assert [request.model_config.seed for request in h0_client.requests] == [100, 101, 102]
    assert [request.model_config.seed for request in h1_client.requests] == [100, 101, 102]
    assert h0_result.tool_action_attempt_count == h1_result.tool_action_attempt_count == 3


def test_immediate_text_stop_uses_no_tool_slot_read_or_mutation(make_request) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    before = environment.snapshot_bytes()

    result, client, _ = _execute(
        environment, original, [_response(content="I cannot determine the outcome.")]
    )

    assert len(client.requests) == result.additional_llm_calls == 1
    assert result.termination_reason == MODEL_STOPPED
    assert result.tool_action_attempt_count == 0
    assert result.recovery_tool_calls_attempted == 0
    assert result.recovery_tool_calls_executed == 0
    assert result.recovery_actions[0].action_type == MODEL_STOP
    assert environment.dispatch_count == 0
    assert environment.snapshot_bytes() == before
    assert result.evaluation.primary_classification is PrimaryClassification.MISSING_EFFECT


@pytest.mark.parametrize(
    ("world_name", "classification", "event_id"),
    [
        ("not_executed", PrimaryClassification.CORRECT, "evt-000001"),
        ("executed_ack_lost", PrimaryClassification.DUPLICATE_EFFECT, "evt-000002"),
    ],
)
def test_valid_create_mutates_once_with_recovery_provenance(
    make_request, world_name, classification, event_id
) -> None:
    original = make_request()
    family = _family(original)
    environment = getattr(family, world_name).arm_states.llm_regeneration_state.environment

    result, client, _ = _execute(
        environment,
        original,
        [_response(_create_call(call_id="recovery-create")), _response(content="done")],
        arm_id="supplied-regeneration-arm",
    )

    action = result.recovery_actions[0]
    assert result.arm_id == "supplied-regeneration-arm"
    assert len(client.requests) == 2
    assert result.tool_action_attempt_count == 1
    assert result.recovery_tool_calls_executed == 1
    assert action.action_type == TOOL_CALL
    assert action.validation_status == VALID
    assert action.executed is True
    assert action.mutating is True
    assert action.model_visible_observation == '{"status":"created"}'
    assert action.committed_effect_event_ids == (event_id,)
    assert result.evaluation.primary_classification is classification
    event = environment.state.mutation_events[-1]
    assert event.source_stage is SourceStage.RECOVERY
    assert event.arm_id == "supplied-regeneration-arm"


def test_list_tickets_consumes_slot_is_read_only_and_is_never_inserted(
    make_request,
) -> None:
    original = make_request()
    environment = _family(original).executed_ack_lost.arm_states.llm_regeneration_state.environment
    before = environment.snapshot_bytes()
    result, client, _ = _execute(
        environment,
        original,
        [_response(_list_call()), _response(content="done")],
    )

    action = result.recovery_actions[0]
    visible = json.loads(action.model_visible_observation or "")
    assert action.mutating is False
    assert action.executed is True
    assert result.tool_action_attempt_count == 1
    assert result.recovery_tool_calls_executed == 1
    assert environment.snapshot_bytes() == before
    assert environment.state.mutation_events[-1].source_stage is SourceStage.ORIGINAL
    assert visible == {"tickets": [EXPECTED]}
    assert "ticket_id" not in action.model_visible_observation
    assert [message.role for message in client.requests[0].messages] == [
        "system", "user", "assistant", "tool"
    ]


def test_histories_can_diverge_only_after_model_selected_state_read(make_request) -> None:
    original = make_request()
    family = _family(original)
    scripts = [_response(_list_call()), _response(content="done")]
    _, h0_client, _ = _execute(
        family.not_executed.arm_states.llm_regeneration_state.environment,
        original,
        scripts,
    )
    _, h1_client, _ = _execute(
        family.executed_ack_lost.arm_states.llm_regeneration_state.environment,
        original,
        scripts,
    )

    assert h0_client.requests[0] == h1_client.requests[0]
    assert h0_client.requests[1].messages[:-1] == h1_client.requests[1].messages[:-1]
    assert h0_client.requests[1].messages[-1].content == '{"tickets":[]}'
    assert json.loads(h1_client.requests[1].messages[-1].content or "") == {
        "tickets": [EXPECTED]
    }


def test_multiple_calls_are_all_processed_before_next_model_invocation(
    make_request,
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    result, client, _ = _execute(
        environment,
        original,
        [
            _response(
                _list_call(call_id="read-first"),
                _create_call(call_id="create-second"),
                request_id="provider-call-0",
            ),
            _response(content="done", request_id="provider-call-1"),
        ],
    )

    assert [action.tool_call.tool_call_id for action in result.recovery_actions[:2]] == [
        "read-first", "create-second"
    ]
    assert result.tool_action_attempt_count == 2
    assert len(result.model_invocations) == 2
    assert [request.model_config.seed for request in client.requests] == [100, 101]
    second_roles = [message.role for message in client.requests[1].messages]
    assert second_roles == ["system", "user", "assistant", "tool", "assistant", "tool", "tool"]
    assert client.requests[1].messages[-2].tool_call_id == "read-first"
    assert client.requests[1].messages[-1].tool_call_id == "create-second"


def test_three_requests_in_one_response_allow_one_final_call_at_index_one(
    make_request,
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    first = _response(
        _list_call(call_id="one"),
        _list_call(call_id="two"),
        _list_call(call_id="three"),
    )
    result, client, _ = _execute(environment, original, [first, _response(content="done")])

    assert result.tool_action_attempt_count == 3
    assert result.recovery_tool_calls_attempted == 3
    assert result.recovery_tool_calls_executed == 3
    assert [item.model_call_index for item in result.model_invocations] == [0, 1]
    assert [request.model_config.seed for request in client.requests] == [100, 101]
    assert result.termination_reason == MODEL_STOPPED


def test_fourth_request_in_one_response_is_the_only_budget_rejection(
    make_request,
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    calls = tuple(_list_call(call_id=f"read-{index}") for index in range(1, 5))
    result, client, _ = _execute(environment, original, [_response(*calls)])

    assert len(client.requests) == 1
    assert result.tool_action_attempt_count == 3
    assert result.recovery_tool_calls_attempted == 4
    assert result.recovery_tool_calls_executed == 3
    assert [action.action_type for action in result.recovery_actions] == [
        TOOL_CALL, TOOL_CALL, TOOL_CALL, BUDGET_REJECTED_TOOL_CALL
    ]
    rejected = result.recovery_actions[-1]
    assert rejected.validation_status == NOT_APPLICABLE
    assert rejected.executed is False
    assert rejected.model_visible_observation is None
    assert environment.dispatch_count == 3
    assert result.termination_reason == ACTION_BUDGET_EXCEEDED


def test_later_requests_after_first_budget_rejection_remain_only_raw_evidence(
    make_request,
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    calls = tuple(_list_call(call_id=f"read-{index}") for index in range(1, 7))
    response = _response(*calls)
    result, client, _ = _execute(environment, original, [response])

    assert len(result.recovery_actions) == 4
    assert result.recovery_tool_calls_attempted == 4
    assert [action.tool_call.tool_call_id for action in result.recovery_actions] == [
        "read-1", "read-2", "read-3", "read-4"
    ]
    assert result.model_invocations[0].model_response is response
    assert [call.tool_call_id for call in response.assistant_message.tool_calls] == [
        "read-1", "read-2", "read-3", "read-4", "read-5", "read-6"
    ]
    assert len(client.requests) == 1


def test_one_action_per_call_rejects_call_three_tool_without_fourth_slot(
    make_request,
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    outcomes = [
        _response(_list_call(call_id="one")),
        _response(_list_call(call_id="two")),
        _response(_list_call(call_id="three")),
        _response(_create_call(call_id="four")),
    ]
    result, client, _ = _execute(environment, original, outcomes)

    assert [request.model_config.seed for request in client.requests] == [100, 101, 102, 103]
    assert result.tool_action_attempt_count == 3
    assert result.recovery_tool_calls_attempted == 4
    assert result.recovery_actions[-1].action_type == BUDGET_REJECTED_TOOL_CALL
    assert len(environment.state.tickets) == 0
    assert result.termination_reason == ACTION_BUDGET_EXCEEDED


def test_final_text_after_third_action_is_accepted_and_state_evaluated(
    make_request,
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    outcomes = [
        _response(_list_call(call_id="one")),
        _response(_list_call(call_id="two")),
        _response(_create_call(call_id="three")),
        _response(content="Ticket handled."),
    ]
    result, client, _ = _execute(environment, original, outcomes)

    assert len(client.requests) == 4
    assert result.termination_reason == MODEL_STOPPED
    assert result.recovery_actions[-1].action_type == MODEL_STOP
    assert result.recovery_tool_calls_executed == 3
    assert result.evaluation.primary_classification is PrimaryClassification.CORRECT


@pytest.mark.parametrize(
    "invalid_call",
    [
        _call("{}", tool_name="delete_ticket"),
        _call('{"customer_id":"CUST-001",'),
        _call(
            '{"customer_id":"CUST-001","customer_id":"CUST-001",'
            '"title":"T","description":"D"}'
        ),
        _call("[]"),
        _call('{"customer_id":"CUST-001","title":"T"}'),
        _call(
            '{"customer_id":"CUST-001","title":"T",'
            '"description":"D","extra":"forbidden"}'
        ),
        _call('{"customer_id":7,"title":"T","description":"D"}'),
        _list_call(raw='{ "unexpected": true }'),
        _call("{}", tool_type="computer"),
        _call("{}", call_id=None, tool_name="list_tickets"),
        _call("{}", call_id="", tool_name="list_tickets"),
        _call("{}", call_id=17, tool_name="list_tickets"),
    ],
    ids=[
        "unknown-tool",
        "malformed-json",
        "duplicate-json-key",
        "non-object-shape",
        "missing-create-field",
        "extra-create-field",
        "wrong-create-type",
        "wrong-list-arguments",
        "invalid-call-type",
        "missing-call-id",
        "empty-call-id",
        "non-string-call-id",
    ],
)
def test_invalid_tool_categories_consume_one_slot_without_repair_or_observation(
    make_request, invalid_call
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    before = environment.snapshot_bytes()
    result, client, _ = _execute(environment, original, [_response(invalid_call)])

    assert len(client.requests) == 1
    assert result.termination_reason == INVALID_MODEL_TOOL_CALL
    assert result.tool_action_attempt_count == 1
    assert result.recovery_tool_calls_attempted == 1
    assert result.recovery_tool_calls_executed == 0
    assert len(result.recovery_actions) == 1
    action = result.recovery_actions[0]
    assert action.action_type == INVALID_TOOL_CALL
    assert action.validation_status == INVALID
    assert action.executed is False
    assert action.serialized_request is None
    assert action.model_visible_observation is None
    assert action.tool_call is invalid_call
    assert environment.dispatch_count == 0
    assert environment.snapshot_bytes() == before


def test_schema_valid_changed_task_arguments_execute_without_repair(make_request) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    changed = {**EXPECTED, "customer_id": "CUST-DIFFERENT"}
    result, _, _ = _execute(
        environment,
        original,
        [_response(_create_call(arguments=changed)), _response(content="done")],
    )

    assert result.recovery_actions[0].validation_status == VALID
    assert result.recovery_actions[0].executed is True
    assert environment.state.tickets[0].customer_id == "CUST-DIFFERENT"
    assert result.evaluation.primary_classification is PrimaryClassification.WRONG_MUTATION


@pytest.mark.parametrize(
    ("world_name", "classification"),
    [
        ("not_executed", PrimaryClassification.MISSING_EFFECT),
        ("executed_ack_lost", PrimaryClassification.CORRECT),
    ],
)
def test_first_call_rejected_generation_is_behavioral_and_evaluates_state(
    make_request, world_name, classification
) -> None:
    original = make_request()
    family = _family(original)
    environment = getattr(family, world_name).arm_states.llm_regeneration_state.environment
    rejected = _rejected()
    result, client, _ = _execute(environment, original, [rejected])

    assert len(client.requests) == result.additional_llm_calls == 1
    assert result.termination_reason == MODEL_REJECTED_GENERATION
    assert result.tool_action_attempt_count == 0
    assert result.recovery_tool_calls_attempted == 0
    assert result.recovery_tool_calls_executed == 0
    assert result.recovery_actions == ()
    assert result.model_invocations[0].rejected_generation is rejected
    assert result.model_invocations[0].derived_seed == 100
    assert result.evaluation.primary_classification is classification
    assert result.evaluation.infrastructure_failure is False


def test_rejection_after_actions_preserves_effects_and_does_not_retry(make_request) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    rejected = _rejected()
    result, client, _ = _execute(
        environment, original, [_response(_create_call()), rejected]
    )

    assert len(client.requests) == 2
    assert result.termination_reason == MODEL_REJECTED_GENERATION
    assert result.tool_action_attempt_count == 1
    assert result.recovery_tool_calls_executed == 1
    assert len(result.recovery_actions) == 1
    assert len(environment.state.tickets) == 1
    assert result.evaluation.primary_classification is PrimaryClassification.CORRECT
    assert result.model_invocations[-1].derived_seed == 101


def test_rejection_at_index_two_counts_three_invocations_and_two_actions(
    make_request,
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    result, client, _ = _execute(
        environment,
        original,
        [
            _response(_list_call(call_id="first")),
            _response(_list_call(call_id="second")),
            _rejected(),
        ],
        seed=50,
    )

    assert len(client.requests) == result.additional_llm_calls == 3
    assert result.model_invocations[-1].model_call_index == 2
    assert result.model_invocations[-1].derived_seed == 52
    assert result.tool_action_attempt_count == 2
    assert result.recovery_tool_calls_attempted == 2
    assert result.recovery_tool_calls_executed == 2
    assert len(result.recovery_actions) == 2
    assert result.termination_reason == MODEL_REJECTED_GENERATION


def test_rejection_on_final_permitted_call_is_not_budget_exceeded(make_request) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    outcomes = [
        _response(_list_call(call_id="one")),
        _response(_list_call(call_id="two")),
        _response(_list_call(call_id="three")),
        _rejected(),
    ]
    result, client, _ = _execute(environment, original, outcomes)

    assert len(client.requests) == 4
    assert result.model_invocations[-1].model_call_index == 3
    assert result.model_invocations[-1].derived_seed == 103
    assert result.termination_reason == MODEL_REJECTED_GENERATION
    assert result.tool_action_attempt_count == 3
    assert result.recovery_tool_calls_attempted == 3


def test_provider_failure_is_distinct_infrastructure_and_not_retried(make_request) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    failure = ModelTimeoutError("provider timed out")
    result, client, _ = _execute(environment, original, [failure])

    assert len(client.requests) == 1
    assert result.termination_reason == INFRASTRUCTURE_FAILURE
    assert result.tool_action_attempt_count == 0
    assert result.recovery_actions == ()
    assert result.model_invocations[0].infrastructure_error is failure
    assert result.evaluation.primary_classification is PrimaryClassification.INFRASTRUCTURE_FAILURE
    assert result.evaluation.valid_for_behavioral_analysis is False
    assert result.evaluation.exclusion_reasons == ("PROVIDER_UNAVAILABLE",)


def test_non_model_response_is_implementation_bug_and_is_not_retried(
    make_request,
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    client = ScriptedClient([{"not": "a ModelResponse"}])

    result = execute_llm_regeneration(
        environment,
        context=_context(original),
        client=client,
        model_config=_config(),
        arm_id="arm-P2",
    )

    assert len(client.requests) == 1
    assert result.termination_reason == INFRASTRUCTURE_FAILURE
    assert result.evaluation.primary_classification is PrimaryClassification.INFRASTRUCTURE_FAILURE
    assert result.evaluation.valid_for_behavioral_analysis is False
    assert result.evaluation.exclusion_reasons == ("IMPLEMENTATION_BUG",)
    assert isinstance(
        result.model_invocations[0].infrastructure_error, ModelResponseError
    )


def test_incoherent_parse_metadata_is_implementation_bug_without_retry(
    make_request,
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    incoherent = ModelToolCall(
        tool_call_id="read-with-bad-metadata",
        tool_name="list_tickets",
        arguments_json="{}",
        parse_success=False,
        parsed_arguments=None,
        parse_error="fabricated parse failure",
        tool_type="function",
    )
    result, client, _ = _execute(environment, original, [_response(incoherent)])

    assert len(client.requests) == 1
    assert result.termination_reason == INFRASTRUCTURE_FAILURE
    assert result.evaluation.exclusion_reasons == ("IMPLEMENTATION_BUG",)
    error = result.model_invocations[0].infrastructure_error
    assert isinstance(error, ModelResponseError)
    assert "parse metadata is incoherent" in str(error)
    assert environment.dispatch_count == 0


def test_validated_request_environment_rejection_preserves_implementation_error(
    make_request, monkeypatch
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    failure = RequestValidationError("unexpected deterministic rejection")

    def reject_validated_request(*args, **kwargs):
        raise failure

    monkeypatch.setattr(environment, "execute_request", reject_validated_request)
    result, client, _ = _execute(
        environment, original, [_response(_list_call())]
    )

    assert len(client.requests) == 1
    assert result.termination_reason == INFRASTRUCTURE_FAILURE
    assert result.evaluation.exclusion_reasons == ("IMPLEMENTATION_BUG",)
    assert result.model_invocations[0].infrastructure_error is failure
    assert result.recovery_tool_calls_executed == 0


def test_continuation_history_maps_through_groq_with_exact_raw_calls_and_ids(
    make_request,
) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    list_raw = "{  }"
    create_raw = (
        '{ "title": "Login page timeout", '
        '"customer_id": "CUST-001", '
        '"description": "The login page times out after 30 seconds." }'
    )
    result, client, _ = _execute(
        environment,
        original,
        [
            _response(
                _list_call(call_id="recovery-read", raw=list_raw),
                _call(
                    create_raw,
                    call_id="recovery-create",
                    tool_name="create_ticket",
                ),
                content="I will inspect and then create.",
            ),
            _response(content="done"),
        ],
    )

    assert result.tool_action_attempt_count == 2
    continuation = client.requests[1]
    recovery_assistant = continuation.messages[-3]
    assert all(
        type(call) is ModelVisibleToolCall
        for call in recovery_assistant.tool_calls
    )
    assert [call.arguments_json for call in recovery_assistant.tool_calls] == [
        list_raw,
        create_raw,
    ]

    payload = build_groq_chat_completion_kwargs(continuation)
    assistant_payload, read_result, create_result = payload["messages"][-3:]
    assert assistant_payload == {
        "role": "assistant",
        "content": "I will inspect and then create.",
        "tool_calls": [
            {
                "id": "recovery-read",
                "type": "function",
                "function": {
                    "name": "list_tickets",
                    "arguments": list_raw,
                },
            },
            {
                "id": "recovery-create",
                "type": "function",
                "function": {
                    "name": "create_ticket",
                    "arguments": create_raw,
                },
            },
        ],
    }
    assert read_result == {
        "role": "tool",
        "tool_call_id": "recovery-read",
        "content": '{"tickets":[]}',
    }
    assert create_result == {
        "role": "tool",
        "tool_call_id": "recovery-create",
        "content": '{"status":"created"}',
    }


def test_executor_mutates_only_supplied_environment(make_request) -> None:
    original = make_request()
    family = _family(original)
    selected = family.not_executed.arm_states.llm_regeneration_state.environment
    siblings = (
        family.not_executed.arm_states.exact_replay_state.environment,
        family.executed_ack_lost.arm_states.exact_replay_state.environment,
        family.executed_ack_lost.arm_states.llm_regeneration_state.environment,
    )
    before = tuple(environment.snapshot_bytes() for environment in siblings)

    _execute(selected, original, [_response(_create_call()), _response(content="done")])

    assert len(selected.state.tickets) == 1
    assert tuple(environment.snapshot_bytes() for environment in siblings) == before


def test_caller_config_is_immutable_and_only_derived_seed_changes(make_request) -> None:
    original = make_request()
    environment = _family(original).not_executed.arm_states.llm_regeneration_state.environment
    result, client, config = _execute(
        environment,
        original,
        [_response(_list_call()), _response(content="done")],
        seed=44,
    )

    assert config.seed == 44
    assert [request.model_config.seed for request in client.requests] == [44, 45]
    for model_call_index, request in enumerate(client.requests):
        assert request.model_config == replace(
            config, seed=config.seed + model_call_index
        )
        assert request.model_config.model == config.model
        assert request.model_config.temperature == config.temperature
        assert request.model_config.top_p == config.top_p
        assert (
            request.model_config.max_completion_tokens
            == config.max_completion_tokens
        )
        assert request.model_config.tool_choice == config.tool_choice
        assert (
            request.model_config.parallel_tool_calls
            == config.parallel_tool_calls
        )
        assert request.model_config.provider_parameters == config.provider_parameters
        assert request.model_config is not config
    assert [item.derived_seed for item in result.model_invocations] == [44, 45]
    with pytest.raises(FrozenInstanceError):
        config.seed = 99  # type: ignore[misc]
