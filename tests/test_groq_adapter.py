from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import groq
import httpx
import pytest

import retry_semantics.models.groq as groq_module
from retry_semantics.environments.ticket import SourceStage, TicketEnvironment
from retry_semantics.models import (
    GroqModelClient,
    ModelAuthenticationError,
    ModelBehaviorError,
    ModelCallConfig,
    ModelProviderError,
    ModelProviderStatusError,
    ModelRateLimitError,
    ModelRejectedGenerationError,
    ModelRequest,
    ModelRequestError,
    ModelResponseError,
    ModelTimeoutError,
    ToolChoice,
    build_groq_chat_completion_kwargs,
    capture_groq_chat_completion,
    model_request_from_regeneration_context,
)
from retry_semantics.runtime.hidden_worlds import construct_trial_family_states
from retry_semantics.runtime.regeneration_context import (
    CANONICAL_AMBIGUITY_TEXT,
    CanonicalContextMessage,
    CanonicalToolCall,
    CreateTicketArguments,
    build_canonical_regeneration_context,
)

USER_TASK = (
    'Create exactly one support ticket for customer "C" with title "X" '
    'and description "Y".'
)
RAW_HISTORICAL_ARGUMENTS = (
    '{ "title": "X", "customer_id": "C", "description": "Y" }'
)


def _context(request):
    value = json.loads(request.serialized_request)
    assistant = CanonicalContextMessage(
        role="assistant",
        content="",
        tool_calls=(
            CanonicalToolCall(
                tool_call_id=value["tool_call_id"],
                tool=value["tool"],
                arguments_json=RAW_HISTORICAL_ARGUMENTS,
                arguments=CreateTicketArguments(**value["arguments"]),
            ),
        ),
        tool_call_id=None,
    )
    return build_canonical_regeneration_context(
        user_task=USER_TASK,
        frozen_original_request=request,
        original_assistant_message=assistant,
    )


def _request(
    make_request,
    *,
    tool_choice=None,
    seed=23,
    top_p=None,
    parallel_tool_calls=None,
    provider_parameters=None,
):
    context = _context(
        make_request(customer_id="C", title="X", description="Y")
    )
    return model_request_from_regeneration_context(
        context,
        ModelCallConfig(
            model="requested-model",
            temperature=0.25,
            seed=seed,
            max_completion_tokens=321,
            tool_choice=tool_choice or ToolChoice.auto(),
            top_p=top_p,
            parallel_tool_calls=parallel_tool_calls,
            provider_parameters=(
                {} if provider_parameters is None else provider_parameters
            ),
        ),
    )


def _tool_call(
    call_id: str,
    name: str,
    arguments: str,
    *,
    tool_type: str = "function",
):
    return SimpleNamespace(
        id=call_id,
        type=tool_type,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _completion(
    *,
    content=None,
    tool_calls=None,
    finish_reason="stop",
    role="assistant",
    model="returned-model",
    completion_id="completion-123",
    fingerprint="fp-abc",
    usage=True,
):
    usage_value = (
        SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
        )
        if usage
        else None
    )
    return SimpleNamespace(
        id=completion_id,
        model=model,
        system_fingerprint=fingerprint,
        usage=usage_value,
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(
                    role=role,
                    content=content,
                    tool_calls=tool_calls,
                ),
            )
        ],
    )


def _bad_request(body, *, request_id: str | None = None):
    headers = {"x-request-id": request_id} if request_id is not None else {}
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.groq.com/test"),
        headers=headers,
    )
    return groq.BadRequestError("bad request", response=response, body=body)


def test_exact_historical_raw_arguments_and_ambiguity_mapping(make_request) -> None:
    payload = build_groq_chat_completion_kwargs(_request(make_request))

    assert payload["messages"][2] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-001",
                "type": "function",
                "function": {
                    "name": "create_ticket",
                    "arguments": RAW_HISTORICAL_ARGUMENTS,
                },
            }
        ],
    }
    assert payload["messages"][2]["tool_calls"][0]["function"][
        "arguments"
    ] == RAW_HISTORICAL_ARGUMENTS
    assert payload["messages"][3] == {
        "role": "tool",
        "tool_call_id": "call-001",
        "content": CANONICAL_AMBIGUITY_TEXT,
    }


def test_frozen_tool_catalog_maps_directly_without_schema_changes(make_request) -> None:
    request = _request(make_request)
    payload = build_groq_chat_completion_kwargs(request)

    assert payload["tools"] == [
        {"type": "function", "function": tool.as_dict()}
        for tool in request.tools
    ]


def test_request_mapping_contains_no_hidden_state_or_evaluator_leakage(
    make_request,
) -> None:
    request = _request(make_request)
    frozen = make_request(customer_id="C", title="X", description="Y")
    family = construct_trial_family_states(
        initial_state=TicketEnvironment.empty(),
        frozen_original_request=frozen,
        serialized_original_request=frozen.serialized_request,
        original_request_hash=frozen.request_hash,
        original_source_stage=SourceStage.ORIGINAL,
        original_arm_id=None,
    )
    serialized = json.dumps(
        build_groq_chat_completion_kwargs(request),
        ensure_ascii=False,
        sort_keys=True,
    )

    for forbidden in (
        "NOT_EXECUTED",
        "EXECUTED_ACK_LOST",
        "ticket_id",
        "mutation_events",
        "dispatch_count",
        "state_schema_version",
        "CORRECT",
        "DUPLICATE_EFFECT",
        family.initial_state_hash,
        family.not_executed.post_ambiguity_state_hash,
        family.executed_ack_lost.post_ambiguity_state_hash,
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        (ToolChoice.auto(), "auto"),
        (ToolChoice.required(), "required"),
        (ToolChoice.none(), "none"),
        (
            ToolChoice.forced_function("create_ticket"),
            {"type": "function", "function": {"name": "create_ticket"}},
        ),
    ],
)
def test_all_tool_choice_modes_map_explicitly(make_request, choice, expected) -> None:
    payload = build_groq_chat_completion_kwargs(
        _request(make_request, tool_choice=choice)
    )

    assert payload["tool_choice"] == expected


def test_configuration_fields_map_exactly(make_request) -> None:
    payload = build_groq_chat_completion_kwargs(
        _request(
            make_request,
            seed=99,
            top_p=0.75,
            parallel_tool_calls=False,
            provider_parameters={},
        )
    )

    assert payload["model"] == "requested-model"
    assert payload["temperature"] == 0.25
    assert payload["top_p"] == 0.75
    assert payload["seed"] == 99
    assert payload["max_completion_tokens"] == 321
    assert payload["tool_choice"] == "auto"
    assert payload["parallel_tool_calls"] is False


def test_unspecified_optional_sampling_fields_are_omitted(make_request) -> None:
    context = _context(make_request(customer_id="C", title="X", description="Y"))
    request = model_request_from_regeneration_context(
        context,
        ModelCallConfig(
            model="requested-model",
            temperature=None,
            seed=None,
            max_completion_tokens=None,
            tool_choice=ToolChoice.none(),
        ),
    )
    payload = build_groq_chat_completion_kwargs(request)

    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "seed" not in payload
    assert "max_completion_tokens" not in payload
    assert "parallel_tool_calls" not in payload


def test_nonempty_provider_parameters_are_rejected_instead_of_dropped(
    make_request,
) -> None:
    request = _request(
        make_request,
        provider_parameters={"unsupported_option": "value"},
    )

    with pytest.raises(ModelRequestError, match="unsupported_option"):
        build_groq_chat_completion_kwargs(request)


def test_supported_provider_parameter_maps_exactly(make_request) -> None:
    request = _request(
        make_request,
        provider_parameters={"reasoning_effort": "medium"},
    )

    payload = build_groq_chat_completion_kwargs(request)

    assert payload["reasoning_effort"] == "medium"


def test_empty_provider_parameters_do_not_change_groq_request(make_request) -> None:
    implicit_empty = build_groq_chat_completion_kwargs(_request(make_request))
    explicit_empty = build_groq_chat_completion_kwargs(
        _request(make_request, provider_parameters={})
    )

    assert explicit_empty == implicit_empty


def test_invalid_supported_provider_parameter_value_is_rejected(make_request) -> None:
    request = _request(
        make_request,
        provider_parameters={"reasoning_effort": "unsupported"},
    )

    with pytest.raises(ModelRequestError, match="reasoning_effort"):
        build_groq_chat_completion_kwargs(request)


def test_h0_h1_groq_payloads_are_identical(make_request) -> None:
    frozen = make_request(customer_id="C", title="X", description="Y")
    family = construct_trial_family_states(
        initial_state=TicketEnvironment.empty(),
        frozen_original_request=frozen,
        serialized_original_request=frozen.serialized_request,
        original_request_hash=frozen.request_hash,
        original_source_stage=SourceStage.ORIGINAL,
        original_arm_id=None,
    )
    h0 = _context(
        family.not_executed.arm_states.llm_regeneration_state
        .frozen_original_request
    )
    h1 = _context(
        family.executed_ack_lost.arm_states.llm_regeneration_state
        .frozen_original_request
    )
    config = ModelCallConfig(
        model="requested-model",
        temperature=0.0,
        seed=31,
        max_completion_tokens=256,
        tool_choice=ToolChoice.auto(),
    )

    assert build_groq_chat_completion_kwargs(
        model_request_from_regeneration_context(h0, config)
    ) == build_groq_chat_completion_kwargs(
        model_request_from_regeneration_context(h1, config)
    )


def test_normal_text_response_is_captured_faithfully() -> None:
    response = capture_groq_chat_completion(
        _completion(content="Done.", tool_calls=None),
        requested_model="requested-model",
    )

    assert response.assistant_message.content == "Done."
    assert response.assistant_message.tool_calls == ()
    assert response.finish_reason == "stop"
    assert response.provider == "groq"
    assert response.requested_model == "requested-model"
    assert response.returned_model == "returned-model"
    assert response.system_fingerprint == "fp-abc"
    assert response.provider_request_id == "completion-123"
    assert response.usage is not None
    assert response.usage.prompt_tokens == 11
    assert response.usage.completion_tokens == 7
    assert response.usage.total_tokens == 18


def test_one_tool_call_preserves_raw_and_parsed_arguments() -> None:
    raw = '{ "title": "X", "count": 2 }'
    response = capture_groq_chat_completion(
        _completion(
            tool_calls=[_tool_call("call-1", "create_ticket", raw)],
            finish_reason="tool_calls",
        ),
        requested_model="requested-model",
    )
    call = response.assistant_message.tool_calls[0]

    assert call.tool_call_id == "call-1"
    assert call.tool_name == "create_ticket"
    assert call.arguments_json == raw
    assert call.parse_success is True
    assert call.parsed_arguments == {"title": "X", "count": 2}
    assert call.parse_error is None


def test_multiple_tool_calls_are_all_preserved_in_provider_order() -> None:
    response = capture_groq_chat_completion(
        _completion(
            tool_calls=[
                _tool_call("call-1", "list_tickets", "{}"),
                _tool_call("call-2", "create_ticket", '{"title":"X"}'),
            ],
            finish_reason="tool_calls",
        ),
        requested_model="requested-model",
    )

    assert [call.tool_call_id for call in response.assistant_message.tool_calls] == [
        "call-1",
        "call-2",
    ]
    assert [call.tool_name for call in response.assistant_message.tool_calls] == [
        "list_tickets",
        "create_ticket",
    ]


def test_missing_tool_call_id_is_preserved_as_readable_model_behavior() -> None:
    raw_call = SimpleNamespace(
        type="function",
        function=SimpleNamespace(name="create_ticket", arguments="{}"),
    )

    response = capture_groq_chat_completion(
        _completion(tool_calls=[raw_call]),
        requested_model="requested-model",
    )

    assert response.assistant_message.tool_calls[0].tool_call_id is None


def test_non_string_json_tool_call_id_is_preserved_as_readable_behavior() -> None:
    response = capture_groq_chat_completion(
        _completion(tool_calls=[_tool_call(7, "create_ticket", "{}")]),
        requested_model="requested-model",
    )

    assert response.assistant_message.tool_calls[0].tool_call_id == 7


@pytest.mark.parametrize(
    "raw",
    [
        '{"customer_id":"C",',
        '{"x":1,"x":2}',
        '{"x":NaN}',
        '{"x":1e999}',
    ],
)
def test_invalid_or_non_strict_argument_json_is_retained_as_behavior(raw) -> None:
    response = capture_groq_chat_completion(
        _completion(tool_calls=[_tool_call("call-bad", "create_ticket", raw)]),
        requested_model="requested-model",
    )
    call = response.assistant_message.tool_calls[0]

    assert call.arguments_json == raw
    assert call.parse_success is False
    assert call.parsed_arguments is None
    assert call.parse_error


def test_wrong_tool_name_is_retained_without_repair() -> None:
    response = capture_groq_chat_completion(
        _completion(tool_calls=[_tool_call("call-1", "delete_everything", "{}")]),
        requested_model="requested-model",
    )

    assert response.assistant_message.tool_calls[0].tool_name == "delete_everything"


def test_assistant_content_and_tool_call_are_both_preserved() -> None:
    response = capture_groq_chat_completion(
        _completion(
            content="I will try this.",
            tool_calls=[_tool_call("call-1", "create_ticket", "{}")],
            finish_reason="tool_calls",
        ),
        requested_model="requested-model",
    )

    assert response.assistant_message.content == "I will try this."
    assert len(response.assistant_message.tool_calls) == 1


@pytest.mark.parametrize("content", ["", None])
def test_empty_and_null_content_remain_distinct(content) -> None:
    response = capture_groq_chat_completion(
        _completion(content=content, tool_calls=None),
        requested_model="requested-model",
    )

    assert response.assistant_message.content is content


def test_parsed_arguments_and_response_are_immutable() -> None:
    response = capture_groq_chat_completion(
        _completion(tool_calls=[_tool_call("call-1", "create_ticket", '{"x":1}')]),
        requested_model="requested-model",
    )
    parsed = response.assistant_message.tool_calls[0].parsed_arguments
    assert parsed is not None

    with pytest.raises(TypeError):
        parsed["x"] = 2  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        response.returned_model = "changed"  # type: ignore[misc]


def test_structurally_malformed_provider_response_is_an_infrastructure_error() -> None:
    with pytest.raises(ModelResponseError):
        capture_groq_chat_completion(
            SimpleNamespace(choices=[]), requested_model="requested-model"
        )


def test_non_assistant_response_role_is_rejected_without_normalization() -> None:
    with pytest.raises(ModelResponseError, match="exactly 'assistant'"):
        capture_groq_chat_completion(
            _completion(role="user"), requested_model="requested-model"
        )


class _FakeCompletions:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class _FakeSdkClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


def test_unsupported_provider_parameter_fails_before_sdk_invocation(
    make_request,
) -> None:
    completions = _FakeCompletions(result=_completion(content="unused"))
    client = GroqModelClient(sdk_client=_FakeSdkClient(completions))

    with pytest.raises(ModelRequestError, match="unsupported_option"):
        client.complete(
            _request(
                make_request,
                provider_parameters={"unsupported_option": "value"},
            )
        )

    assert completions.calls == []


def test_client_makes_exactly_one_call_and_executes_no_tool(make_request) -> None:
    completion = _completion(
        tool_calls=[_tool_call("call-1", "create_ticket", '{"title":"X"}')],
        finish_reason="tool_calls",
    )
    completions = _FakeCompletions(completion)
    client = GroqModelClient(sdk_client=_FakeSdkClient(completions))
    request = _request(make_request)

    response = client.complete(request)

    assert len(completions.calls) == 1
    assert completions.calls[0] == build_groq_chat_completion_kwargs(request)
    assert response.assistant_message.tool_calls[0].tool_name == "create_ticket"
    assert not hasattr(client, "execute_tool")


def test_client_constructs_official_sdk_with_zero_retries_and_timeout(
    monkeypatch,
) -> None:
    captured = {}
    fake = _FakeSdkClient(_FakeCompletions())

    def construct(**kwargs):
        captured.update(kwargs)
        return fake

    monkeypatch.setattr(groq_module.groq_sdk, "Groq", construct)
    GroqModelClient(api_key="test-placeholder", timeout_seconds=12.5)

    assert captured == {
        "api_key": "test-placeholder",
        "timeout": 12.5,
        "max_retries": 0,
    }


def test_timeout_is_infrastructure_failure_and_is_not_retried(make_request) -> None:
    error = groq.APITimeoutError(
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    )
    completions = _FakeCompletions(error=error)
    client = GroqModelClient(sdk_client=_FakeSdkClient(completions))

    with pytest.raises(ModelTimeoutError):
        client.complete(_request(make_request))

    assert len(completions.calls) == 1


@pytest.mark.parametrize(
    ("sdk_error", "boundary_error"),
    [
        (
            groq.AuthenticationError(
                "unauthorized",
                response=httpx.Response(
                    401,
                    request=httpx.Request("POST", "https://api.groq.com/test"),
                ),
                body=None,
            ),
            ModelAuthenticationError,
        ),
        (
            groq.RateLimitError(
                "rate limited",
                response=httpx.Response(
                    429,
                    request=httpx.Request("POST", "https://api.groq.com/test"),
                ),
                body=None,
            ),
            ModelRateLimitError,
        ),
        (
            groq.InternalServerError(
                "provider failed",
                response=httpx.Response(
                    500,
                    request=httpx.Request("POST", "https://api.groq.com/test"),
                ),
                body=None,
            ),
            ModelProviderStatusError,
        ),
    ],
)
def test_provider_failures_are_distinct_from_model_behavior_and_not_retried(
    make_request,
    sdk_error,
    boundary_error,
) -> None:
    completions = _FakeCompletions(error=sdk_error)
    client = GroqModelClient(sdk_client=_FakeSdkClient(completions))

    with pytest.raises(boundary_error):
        client.complete(_request(make_request))

    assert len(completions.calls) == 1


def test_tool_use_failed_string_is_behavioral_and_preserved_exactly(
    make_request,
) -> None:
    sdk_error = _bad_request(
        {
            "error": {
                "message": "Invalid tool call generated",
                "type": "invalid_request_error",
                "code": "tool_use_failed",
                "failed_generation": "maybe",
            }
        },
        request_id="req-behavior-1",
    )
    completions = _FakeCompletions(error=sdk_error)
    client = GroqModelClient(sdk_client=_FakeSdkClient(completions))

    with pytest.raises(ModelRejectedGenerationError) as caught:
        client.complete(_request(make_request))

    failure = caught.value
    assert isinstance(failure, ModelBehaviorError)
    assert not isinstance(failure, ModelProviderError)
    assert failure.provider == "groq"
    assert failure.provider_error_code == "tool_use_failed"
    assert failure.failed_generation == "maybe"
    assert failure.provider_request_id == "req-behavior-1"
    assert failure.__cause__ is None
    assert failure.__context__ is None
    with pytest.raises(FrozenInstanceError):
        failure.provider = "changed"  # type: ignore[misc]
    assert len(completions.calls) == 1


def test_tool_use_failed_object_is_faithfully_frozen(make_request) -> None:
    attempted_arguments = "{'location': 'New York'}"
    sdk_error = _bad_request(
        {
            "error": {
                "code": "tool_use_failed",
                "failed_generation": {
                    "reason": "Tool call arguments are not valid JSON",
                    "tool_call_id": "call_abc123",
                    "attempted_arguments": attempted_arguments,
                    "diagnostics": ["first", {"position": 7}],
                },
            }
        }
    )
    completions = _FakeCompletions(error=sdk_error)
    client = GroqModelClient(sdk_client=_FakeSdkClient(completions))

    with pytest.raises(ModelRejectedGenerationError) as caught:
        client.complete(_request(make_request))

    evidence = caught.value.failed_generation
    assert evidence == {
        "reason": "Tool call arguments are not valid JSON",
        "tool_call_id": "call_abc123",
        "attempted_arguments": attempted_arguments,
        "diagnostics": ("first", {"position": 7}),
    }
    assert evidence["attempted_arguments"] == attempted_arguments
    assert evidence["diagnostics"][1] == {"position": 7}
    with pytest.raises(TypeError):
        evidence["reason"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        evidence["diagnostics"][1]["position"] = 8  # type: ignore[index]
    assert len(completions.calls) == 1


def test_documented_code_absent_rejected_generation_is_behavioral(
    make_request,
) -> None:
    failed_generation = {
        "reason": "Tool call arguments are not valid JSON"
    }
    completions = _FakeCompletions(
        error=_bad_request(
            {
                "error": {
                    "message": "Invalid tool call generated",
                    "type": "invalid_request_error",
                    "failed_generation": failed_generation,
                }
            }
        )
    )
    client = GroqModelClient(sdk_client=_FakeSdkClient(completions))

    with pytest.raises(ModelRejectedGenerationError) as caught:
        client.complete(_request(make_request))

    assert caught.value.provider_error_code is None
    assert caught.value.failed_generation == failed_generation
    assert isinstance(caught.value, ModelBehaviorError)
    assert not isinstance(caught.value, ModelProviderError)
    assert len(completions.calls) == 1


def test_code_absent_string_generation_is_behavioral_and_exact(
    make_request,
) -> None:
    completions = _FakeCompletions(
        error=_bad_request(
            {
                "error": {
                    "type": "invalid_request_error",
                    "failed_generation": "maybe",
                }
            }
        )
    )
    client = GroqModelClient(sdk_client=_FakeSdkClient(completions))

    with pytest.raises(ModelRejectedGenerationError) as caught:
        client.complete(_request(make_request))

    assert caught.value.provider_error_code is None
    assert caught.value.failed_generation == "maybe"
    assert len(completions.calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"code": "invalid_request_error", "detail": "bad input"}},
        {
            "error": {
                "type": "invalid_request_error",
                "code": "some_other_error",
                "failed_generation": "...",
            }
        },
        {
            "error": {
                "type": "authentication_error",
                "failed_generation": "...",
            }
        },
        {"error": {"code": "tool_use_failed"}},
    ],
)
def test_unrelated_or_evidence_free_bad_request_remains_provider_failure(
    make_request,
    body,
) -> None:
    completions = _FakeCompletions(error=_bad_request(body))
    client = GroqModelClient(sdk_client=_FakeSdkClient(completions))

    with pytest.raises(ModelProviderStatusError) as caught:
        client.complete(_request(make_request))

    assert caught.value.status_code == 400
    assert len(completions.calls) == 1


def test_unexpected_but_json_compatible_failed_generation_is_preserved(
    make_request,
) -> None:
    completions = _FakeCompletions(
        error=_bad_request(
            {
                "error": {
                    "code": "tool_use_failed",
                    "failed_generation": ["unexpected", 3, None],
                }
            }
        )
    )
    client = GroqModelClient(sdk_client=_FakeSdkClient(completions))

    with pytest.raises(ModelRejectedGenerationError) as caught:
        client.complete(_request(make_request))

    assert caught.value.failed_generation == ("unexpected", 3, None)
    assert len(completions.calls) == 1


def test_unreadable_failed_generation_fails_explicitly_without_retry(
    make_request,
) -> None:
    completions = _FakeCompletions(
        error=_bad_request(
            {
                "error": {
                    "code": "tool_use_failed",
                    "failed_generation": object(),
                }
            }
        )
    )
    client = GroqModelClient(sdk_client=_FakeSdkClient(completions))

    with pytest.raises(ModelResponseError, match="unreadable failed_generation"):
        client.complete(_request(make_request))

    assert len(completions.calls) == 1
