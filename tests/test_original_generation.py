from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from retry_semantics.environments.ticket import SourceStage, TicketEnvironment
from retry_semantics.models import (
    ModelAssistantMessage,
    ModelCallConfig,
    ModelRejectedGenerationError,
    ModelRequest,
    ModelRequestError,
    ModelResponse,
    ModelTimeoutError,
    ModelToolCall,
    ModelUsage,
    ToolChoice,
    build_groq_chat_completion_kwargs,
    freeze_json_value,
    parse_tool_arguments_json,
)
from retry_semantics.runtime.hidden_worlds import construct_trial_family_states
from retry_semantics.runtime.original_generation import (
    EligibleOriginalGeneration,
    OriginalGenerationBehavioralFailure,
    OriginalGenerationFailureReason,
    V1CreateTicketTaskSpec,
    build_v1_original_generation_request,
    render_v1_create_ticket_task,
    run_v1_original_generation_attempt,
)
from retry_semantics.runtime.regeneration_context import (
    FROZEN_SYSTEM_MESSAGE,
    FROZEN_TOOL_CATALOG,
    build_canonical_regeneration_context,
)
from retry_semantics.serialization import sha256_hex

CUSTOMER = "C"
TITLE = "T"
DESCRIPTION = "D"
USER_TASK = (
    'Create exactly one support ticket for customer "C" with title "T" '
    'and description "D".'
)
COMPACT_ARGUMENTS = '{"customer_id":"C","title":"T","description":"D"}'
REFORMATTED_ARGUMENTS = (
    '{ "title": "T", "description": "D", "customer_id": "C" }'
)


def _task(*, user_task: str = USER_TASK) -> V1CreateTicketTaskSpec:
    return V1CreateTicketTaskSpec(
        customer_id=CUSTOMER,
        expected_title=TITLE,
        expected_description=DESCRIPTION,
        user_task=user_task,
    )


def _config(*, tool_choice: ToolChoice | None = None, seed: int | None = 7):
    return ModelCallConfig(
        model="test-model",
        temperature=0.25,
        seed=seed,
        max_completion_tokens=123,
        tool_choice=tool_choice or ToolChoice.auto(),
        top_p=0.85,
        parallel_tool_calls=False,
        provider_parameters={"reasoning_effort": "low"},
    )


def _tool_call(
    raw: str = COMPACT_ARGUMENTS,
    *,
    call_id: object = "call-original",
    tool_name: str = "create_ticket",
    tool_type: str | None = "function",
) -> ModelToolCall:
    parse_success, parsed_arguments, parse_error = parse_tool_arguments_json(raw)
    return ModelToolCall(
        tool_call_id=call_id,
        tool_name=tool_name,
        arguments_json=raw,
        parse_success=parse_success,
        parsed_arguments=parsed_arguments,
        parse_error=parse_error,
        tool_type=tool_type,
    )


def _response(
    *calls: ModelToolCall,
    content: str | None = None,
    finish_reason: str | None = "tool_calls",
) -> ModelResponse:
    return ModelResponse(
        assistant_message=ModelAssistantMessage(
            role="assistant",
            content=content,
            tool_calls=tuple(calls),
        ),
        finish_reason=finish_reason,
        provider="fake-provider",
        requested_model="test-model",
        returned_model="returned-test-model",
        usage=ModelUsage(11, 5, 16),
        system_fingerprint="fingerprint-1",
        provider_request_id="provider-request-1",
    )


class FakeClient:
    def __init__(self, outcome: ModelResponse | Exception) -> None:
        self.outcome = outcome
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _attempt(
    response: ModelResponse,
    *,
    task: V1CreateTicketTaskSpec | None = None,
    config: ModelCallConfig | None = None,
):
    client = FakeClient(response)
    result = run_v1_original_generation_attempt(
        client,
        task_spec=task or _task(),
        model_config=config or _config(),
    )
    assert len(client.requests) == 1
    return result


def test_v1_task_renderer_reproduces_the_exact_frozen_template() -> None:
    assert render_v1_create_ticket_task(
        customer_id=CUSTOMER,
        expected_title=TITLE,
        expected_description=DESCRIPTION,
    ) == USER_TASK


def test_valid_materialized_task_is_accepted_and_transmitted_unchanged() -> None:
    task = _task()
    config = _config()
    request = build_v1_original_generation_request(
        task_spec=task,
        model_config=config,
    )

    assert [message.role for message in request.messages] == ["system", "user"]
    assert request.messages[0].content == FROZEN_SYSTEM_MESSAGE
    assert request.messages[1].content is task.user_task
    assert request.messages[1].content == USER_TASK
    assert request.messages[1].content.encode("ascii") == USER_TASK.encode("ascii")
    assert all(message.tool_calls == () for message in request.messages)
    assert all(message.tool_call_id is None for message in request.messages)
    assert request.tools is FROZEN_TOOL_CATALOG
    assert request.model_config is config
    assert request.model_config.top_p == 0.85
    assert request.model_config.parallel_tool_calls is False
    assert request.model_config.provider_parameters == {
        "reasoning_effort": "low"
    }
    assert [tool.name for tool in request.tools] == [
        "create_ticket",
        "list_tickets",
    ]


@pytest.mark.parametrize(
    "user_task",
    [
        (
            'Create exactly one support ticket for customer "CUST-999" with '
            'title "T" and description "D".'
        ),
        "Write a poem about retry semantics.",
    ],
)
def test_incoherent_materialized_task_fails_before_provider_call(user_task) -> None:
    client = FakeClient(_response(_tool_call()))

    with pytest.raises(ModelRequestError, match="exactly match"):
        task = _task(user_task=user_task)
        run_v1_original_generation_attempt(
            client,
            task_spec=task,
            model_config=_config(),
        )

    assert client.requests == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_title", "café"),
        ("expected_description", "line one\nline two"),
        ("expected_description", "column one\tcolumn two"),
        ("expected_title", 'Login "broken"'),
        ("customer_id", ""),
    ],
)
def test_task_spec_rejects_non_v1_scenario_values(field, value) -> None:
    values = {
        "customer_id": CUSTOMER,
        "expected_title": TITLE,
        "expected_description": DESCRIPTION,
    }
    values[field] = value

    with pytest.raises(ModelRequestError):
        V1CreateTicketTaskSpec(
            **values,
            user_task=USER_TASK,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_title", "café"),
        ("expected_description", "line one\nline two"),
        ("expected_description", "column one\tcolumn two"),
        ("expected_title", 'Login "broken"'),
        ("customer_id", ""),
    ],
)
def test_task_renderer_rejects_non_v1_scenario_values(field, value) -> None:
    values = {
        "customer_id": CUSTOMER,
        "expected_title": TITLE,
        "expected_description": DESCRIPTION,
    }
    values[field] = value

    with pytest.raises(ModelRequestError):
        render_v1_create_ticket_task(**values)


def test_printable_ascii_punctuation_remains_valid() -> None:
    customer_id = "CUST-001/A+B"
    title = "Login?! #1: [broken] @ home"
    description = "Can't save: 50% complete; retry/update = false."
    rendered = render_v1_create_ticket_task(
        customer_id=customer_id,
        expected_title=title,
        expected_description=description,
    )

    task = V1CreateTicketTaskSpec(
        customer_id=customer_id,
        expected_title=title,
        expected_description=description,
        user_task=rendered,
    )

    assert task.user_task is rendered


def test_groq_original_generation_payload_has_no_prior_or_ambiguity_message() -> None:
    request = build_v1_original_generation_request(
        task_spec=_task(),
        model_config=_config(),
    )
    payload = build_groq_chat_completion_kwargs(request)

    assert payload["messages"] == [
        {"role": "system", "content": FROZEN_SYSTEM_MESSAGE},
        {"role": "user", "content": USER_TASK},
    ]
    assert payload["tools"] == [
        {"type": "function", "function": tool.as_dict()}
        for tool in FROZEN_TOOL_CATALOG
    ]
    assert payload["tool_choice"] == "auto"
    assert "ToolError" not in json.dumps(payload)


def test_request_construction_is_pure_and_config_changes_only_config() -> None:
    task = _task()
    first = build_v1_original_generation_request(
        task_spec=task,
        model_config=_config(seed=1),
    )
    same = build_v1_original_generation_request(
        task_spec=task,
        model_config=_config(seed=1),
    )
    changed = build_v1_original_generation_request(
        task_spec=task,
        model_config=ModelCallConfig(
            model="different-model",
            temperature=None,
            seed=2,
            max_completion_tokens=None,
            tool_choice=ToolChoice.auto(),
        ),
    )

    assert first == same
    assert first.messages == changed.messages
    assert first.tools == changed.tools == FROZEN_TOOL_CATALOG
    assert first.model_config != changed.model_config


@pytest.mark.parametrize(
    "tool_choice",
    [
        ToolChoice.required(),
        ToolChoice.none(),
        ToolChoice.forced_function("create_ticket"),
    ],
)
def test_non_auto_config_fails_before_provider_call(tool_choice) -> None:
    client = FakeClient(_response(_tool_call()))

    with pytest.raises(ModelRequestError, match="requires tool_choice mode AUTO"):
        run_v1_original_generation_attempt(
            client,
            task_spec=_task(),
            model_config=_config(tool_choice=tool_choice),
        )

    assert client.requests == []


@pytest.mark.parametrize(
    "content",
    [None, "", "  ordinary text — café ☃\n  "],
)
def test_eligible_generation_preserves_all_assistant_content(content) -> None:
    raw_response = _response(_tool_call(), content=content)
    result = _attempt(raw_response)

    assert isinstance(result, EligibleOriginalGeneration)
    assert result.model_response is raw_response
    assert result.original_assistant_message.content == content
    assert result.model_response.finish_reason == "tool_calls"
    assert result.model_response.usage == ModelUsage(11, 5, 16)


def test_eligible_generation_freezes_raw_history_and_canonical_executable_m() -> None:
    raw = '{  "title" : "T", "description" : "D", "customer_id" : "C"  }'
    result = _attempt(_response(_tool_call(raw, call_id="provider-call-9")))

    assert isinstance(result, EligibleOriginalGeneration)
    historical_call = result.original_assistant_message.tool_calls[0]
    assert historical_call.arguments_json == raw
    assert historical_call.tool_call_id == "provider-call-9"
    assert historical_call.tool == "create_ticket"
    assert historical_call.arguments.as_dict() == {
        "customer_id": "C",
        "title": "T",
        "description": "D",
    }
    assert result.serialized_original_request == (
        b'{"arguments":{"customer_id":"C","description":"D","title":"T"},'
        b'"tool":"create_ticket","tool_call_id":"provider-call-9"}'
    )
    assert result.original_request_hash == sha256_hex(
        result.serialized_original_request
    )
    assert json.loads(result.serialized_original_request) == {
        "arguments": {
            "customer_id": "C",
            "description": "D",
            "title": "T",
        },
        "tool": "create_ticket",
        "tool_call_id": "provider-call-9",
    }
    with pytest.raises(FrozenInstanceError):
        result.task_spec = _task()  # type: ignore[misc]


def test_raw_unicode_escape_spelling_is_preserved_but_m_uses_decoded_value() -> None:
    raw = '{"customer_id":"C","title":"T","description":"\\u0044"}'
    result = _attempt(_response(_tool_call(raw)))

    assert isinstance(result, EligibleOriginalGeneration)
    assert result.original_assistant_message.tool_calls[0].arguments_json == raw
    assert b'"description":"D"' in result.serialized_original_request
    assert b"\\u0044" not in result.serialized_original_request


@pytest.mark.parametrize("finish_reason", [None, "stop", "unexpected-provider-value"])
def test_finish_reason_is_provenance_not_an_eligibility_rule(finish_reason) -> None:
    result = _attempt(_response(_tool_call(), finish_reason=finish_reason))

    assert isinstance(result, EligibleOriginalGeneration)
    assert result.model_response.finish_reason == finish_reason


def test_no_tool_call_is_behavioral_failure_with_response_evidence() -> None:
    response = _response(content="I cannot do that.", finish_reason="stop")
    result = _attempt(response)

    assert isinstance(result, OriginalGenerationBehavioralFailure)
    assert result.reason is OriginalGenerationFailureReason.NO_TOOL_CALL
    assert result.model_response is response
    assert result.model_response.assistant_message.content == "I cannot do that."


@pytest.mark.parametrize(
    "calls",
    [
        (_tool_call(call_id="one"), _tool_call(call_id="two")),
        (
            _tool_call(call_id="correct"),
            _tool_call("{}", call_id="extra", tool_name="list_tickets"),
        ),
    ],
)
def test_multiple_calls_are_behavioral_failure_and_all_are_retained(calls) -> None:
    response = _response(*calls)
    result = _attempt(response)

    assert isinstance(result, OriginalGenerationBehavioralFailure)
    assert result.reason is OriginalGenerationFailureReason.MULTIPLE_TOOL_CALLS
    assert result.model_response is response
    assert result.model_response.assistant_message.tool_calls == calls


@pytest.mark.parametrize("tool_name", ["list_tickets", "delete_ticket"])
def test_one_wrong_tool_is_behavioral_failure(tool_name) -> None:
    result = _attempt(
        _response(_tool_call("{}", tool_name=tool_name, call_id="wrong-tool"))
    )

    assert isinstance(result, OriginalGenerationBehavioralFailure)
    assert result.reason is OriginalGenerationFailureReason.WRONG_TOOL


@pytest.mark.parametrize("tool_type", [None, "computer", "FUNCTION"])
def test_invalid_tool_call_type_is_behavioral_failure(tool_type) -> None:
    result = _attempt(_response(_tool_call(tool_type=tool_type)))

    assert isinstance(result, OriginalGenerationBehavioralFailure)
    assert result.reason is OriginalGenerationFailureReason.INVALID_TOOL_CALL_TYPE


@pytest.mark.parametrize("call_id", [None, "", 17])
def test_missing_or_empty_tool_call_id_is_behavioral_failure(call_id) -> None:
    result = _attempt(_response(_tool_call(call_id=call_id)))

    assert isinstance(result, OriginalGenerationBehavioralFailure)
    assert result.reason is (
        OriginalGenerationFailureReason.MISSING_OR_INVALID_TOOL_CALL_ID
    )


@pytest.mark.parametrize(
    "raw",
    [
        '{"customer_id":"C",',
        '{"customer_id":"C","customer_id":"C","title":"T","description":"D"}',
    ],
)
def test_malformed_and_duplicate_key_json_are_behavioral_failures(raw) -> None:
    call = _tool_call(raw)
    assert call.parse_success is False
    result = _attempt(_response(call))

    assert isinstance(result, OriginalGenerationBehavioralFailure)
    assert result.reason is OriginalGenerationFailureReason.MALFORMED_ARGUMENT_JSON
    assert result.model_response is not None
    assert result.model_response.assistant_message.tool_calls[0].arguments_json == raw


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        '{"customer_id":"C","title":"T","description":"D","extra":"x"}',
        '{"customer_id":"C","title":"T"}',
        '{"customer_id":7,"title":"T","description":"D"}',
        '{"customer_id":"C","title":"","description":"D"}',
    ],
)
def test_invalid_argument_shapes_are_behavioral_failures(raw) -> None:
    result = _attempt(_response(_tool_call(raw)))

    assert isinstance(result, OriginalGenerationBehavioralFailure)
    assert result.reason is OriginalGenerationFailureReason.INVALID_ARGUMENT_SHAPE


@pytest.mark.parametrize(
    "raw",
    [
        '{"customer_id":"WRONG","title":"T","description":"D"}',
        '{"customer_id":"C","title":"WRONG","description":"D"}',
        '{"customer_id":"C","title":"T","description":"WRONG"}',
    ],
)
def test_task_incorrect_arguments_are_behavioral_failures(raw) -> None:
    result = _attempt(_response(_tool_call(raw)))

    assert isinstance(result, OriginalGenerationBehavioralFailure)
    assert result.reason is (
        OriginalGenerationFailureReason.TASK_INCORRECT_ARGUMENTS
    )


def test_rejected_generation_becomes_behavioral_failure_with_all_diagnostics() -> None:
    rejected = ModelRejectedGenerationError(
        provider="groq",
        provider_error_code="tool_use_failed",
        failed_generation=freeze_json_value(
            {"attempted": "{'customer_id': 'C'}", "position": 4}
        ),
        provider_request_id="groq-request-9",
    )
    client = FakeClient(rejected)

    result = run_v1_original_generation_attempt(
        client,
        task_spec=_task(),
        model_config=_config(),
    )

    assert len(client.requests) == 1
    assert isinstance(result, OriginalGenerationBehavioralFailure)
    assert result.reason is OriginalGenerationFailureReason.REJECTED_GENERATION
    assert result.model_response is None
    assert result.rejected_generation is rejected
    assert result.rejected_generation.failed_generation == {
        "attempted": "{'customer_id': 'C'}",
        "position": 4,
    }
    assert result.rejected_generation.provider_error_code == "tool_use_failed"
    assert result.rejected_generation.provider_request_id == "groq-request-9"


def test_provider_failure_propagates_and_is_not_retried() -> None:
    client = FakeClient(ModelTimeoutError("network timeout"))

    with pytest.raises(ModelTimeoutError, match="network timeout"):
        run_v1_original_generation_attempt(
            client,
            task_spec=_task(),
            model_config=_config(),
        )

    assert len(client.requests) == 1


def test_each_attempt_calls_model_once_and_never_resamples_ineligible_behavior(
) -> None:
    client = FakeClient(_response(content="no tool", finish_reason="stop"))

    result = run_v1_original_generation_attempt(
        client,
        task_spec=_task(),
        model_config=_config(),
    )

    assert isinstance(result, OriginalGenerationBehavioralFailure)
    assert len(client.requests) == 1


def test_generation_performs_zero_environment_dispatches_or_mutations(
    monkeypatch,
) -> None:
    environment = TicketEnvironment.empty()
    before = environment.snapshot_bytes()

    def forbidden_dispatch(*args, **kwargs):
        raise AssertionError("original generation must not dispatch a tool")

    monkeypatch.setattr(TicketEnvironment, "execute_request", forbidden_dispatch)
    result = _attempt(_response(_tool_call()))

    assert isinstance(result, EligibleOriginalGeneration)
    assert environment.dispatch_count == 0
    assert environment.snapshot_bytes() == before
    assert environment.state.tickets == ()
    assert environment.state.mutation_events == ()


def test_generation_boundary_has_no_environment_hidden_world_or_retry_input() -> None:
    signature = inspect.signature(run_v1_original_generation_attempt)
    assert set(signature.parameters) == {"client", "task_spec", "model_config"}
    module_path = inspect.getsourcefile(run_v1_original_generation_attempt)
    assert module_path is not None
    source = Path(module_path).read_text(encoding="utf-8")
    assert "TicketEnvironment" not in source
    assert "construct_trial_family_states" not in source
    assert "execute_request" not in source
    assert "for " not in inspect.getsource(run_v1_original_generation_attempt)


def test_same_input_and_fake_response_produce_same_m_bytes_and_hash() -> None:
    response = _response(_tool_call(REFORMATTED_ARGUMENTS))
    first = _attempt(response)
    second = _attempt(response)

    assert isinstance(first, EligibleOriginalGeneration)
    assert isinstance(second, EligibleOriginalGeneration)
    assert first.serialized_original_request == second.serialized_original_request
    assert first.original_request_hash == second.original_request_hash


def test_raw_formatting_changes_history_and_context_but_not_executable_m() -> None:
    compact = _attempt(_response(_tool_call(COMPACT_ARGUMENTS)))
    reformatted = _attempt(_response(_tool_call(REFORMATTED_ARGUMENTS)))

    assert isinstance(compact, EligibleOriginalGeneration)
    assert isinstance(reformatted, EligibleOriginalGeneration)
    assert compact.original_assistant_message != reformatted.original_assistant_message
    assert (
        compact.serialized_original_request
        == reformatted.serialized_original_request
    )
    assert compact.original_request_hash == reformatted.original_request_hash

    compact_context = build_canonical_regeneration_context(
        user_task=compact.task_spec.user_task,
        frozen_original_request=compact.frozen_executable_request,
        original_assistant_message=compact.original_assistant_message,
    )
    reformatted_context = build_canonical_regeneration_context(
        user_task=reformatted.task_spec.user_task,
        frozen_original_request=reformatted.frozen_executable_request,
        original_assistant_message=reformatted.original_assistant_message,
    )
    assert compact_context.original_assistant_message is (
        compact.original_assistant_message
    )
    assert reformatted_context.original_assistant_message is (
        reformatted.original_assistant_message
    )
    assert compact_context.canonical_context_bytes != (
        reformatted_context.canonical_context_bytes
    )
    assert compact_context.canonical_context_sha256 != (
        reformatted_context.canonical_context_sha256
    )


def test_tool_call_id_is_shared_across_history_and_m_and_changes_m_identity() -> None:
    first = _attempt(_response(_tool_call(call_id="call-a")))
    second = _attempt(_response(_tool_call(call_id="call-b")))

    assert isinstance(first, EligibleOriginalGeneration)
    assert isinstance(second, EligibleOriginalGeneration)
    assert first.original_assistant_message.tool_calls[0].tool_call_id == "call-a"
    assert json.loads(first.serialized_original_request)["tool_call_id"] == "call-a"
    assert first.serialized_original_request != second.serialized_original_request
    assert first.original_request_hash != second.original_request_hash


def test_eligible_output_flows_directly_into_hidden_world_construction() -> None:
    result = _attempt(_response(_tool_call(REFORMATTED_ARGUMENTS)))
    assert isinstance(result, EligibleOriginalGeneration)

    family = construct_trial_family_states(
        initial_state=TicketEnvironment.empty(),
        frozen_original_request=result.frozen_executable_request,
        serialized_original_request=result.serialized_original_request,
        original_request_hash=result.original_request_hash,
        original_source_stage=SourceStage.ORIGINAL,
        original_arm_id=None,
    )

    assert family.frozen_original_request is result.frozen_executable_request
    assert family.not_executed.original_request_dispatch_count == 0
    assert family.executed_ack_lost.original_request_dispatch_count == 1
    h1_replay_state = (
        family.executed_ack_lost.arm_states.exact_replay_state.environment.state
    )
    assert len(h1_replay_state.tickets) == 1


def test_eligible_assistant_message_flows_directly_into_regeneration_context() -> None:
    result = _attempt(
        _response(
            _tool_call(REFORMATTED_ARGUMENTS),
            content="  Stored Unicode: café ☃  ",
        )
    )
    assert isinstance(result, EligibleOriginalGeneration)

    context = build_canonical_regeneration_context(
        user_task=result.task_spec.user_task,
        frozen_original_request=result.frozen_executable_request,
        original_assistant_message=result.original_assistant_message,
    )

    assert context.original_assistant_message is result.original_assistant_message
    assert context.original_tool_call.arguments_json == REFORMATTED_ARGUMENTS
    assert context.original_assistant_message.content == "  Stored Unicode: café ☃  "


def test_attempts_are_stateless_and_never_include_prior_assistant_history() -> None:
    client = FakeClient(_response(_tool_call()))
    for _ in range(2):
        result = run_v1_original_generation_attempt(
            client,
            task_spec=_task(),
            model_config=_config(),
        )
        assert isinstance(result, EligibleOriginalGeneration)

    assert len(client.requests) == 2
    assert all(
        [message.role for message in request.messages] == ["system", "user"]
        for request in client.requests
    )
    assert client.requests[0] == client.requests[1]
