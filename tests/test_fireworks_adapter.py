from __future__ import annotations

import json
from collections.abc import Callable
from types import MappingProxyType

import httpx
import pytest

import retry_semantics.models.fireworks as fireworks_module
from retry_semantics.environments.ticket import TicketEnvironment
from retry_semantics.models import (
    DEEPSEEK_V4_FLASH_0731_MODEL,
    FIREWORKS_CHAT_COMPLETIONS_URL,
    FIREWORKS_PROVIDER,
    FireworksModelClient,
    ModelAuthenticationError,
    ModelCallConfig,
    ModelProviderStatusError,
    ModelRateLimitError,
    ModelRequestError,
    ModelResponseError,
    ModelTimeoutError,
    ModelTransportError,
    ToolChoice,
    build_fireworks_chat_completion_payload,
    capture_fireworks_chat_completion,
    model_request_from_regeneration_context,
)
from retry_semantics.runtime.original_generation import (
    V1CreateTicketTaskSpec,
    build_v1_original_generation_request,
)
from retry_semantics.runtime.regeneration import execute_llm_regeneration
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
FAKE_API_KEY = "offline-test-credential"
_ABSENT = object()


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
    model: str = DEEPSEEK_V4_FLASH_0731_MODEL,
    tool_choice: ToolChoice | None = None,
    provider_parameters: object = MappingProxyType(
        {"reasoning_effort": "none"}
    ),
):
    return model_request_from_regeneration_context(
        _context(make_request(customer_id="C", title="X", description="Y")),
        ModelCallConfig(
            model=model,
            temperature=0.0,
            top_p=1.0,
            seed=99,
            max_completion_tokens=321,
            parallel_tool_calls=False,
            tool_choice=tool_choice or ToolChoice.auto(),
            provider_parameters=provider_parameters,
        ),
    )


def _completion(
    *,
    content=None,
    tool_calls=None,
    finish_reason="stop",
    model="accounts/fireworks/models/returned-model",
    completion_id="fw-completion-123",
    reasoning_content=_ABSENT,
):
    message = {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
    }
    if reasoning_content is not _ABSENT:
        message["reasoning_content"] = reasoning_content
    return {
        "id": completion_id,
        "model": model,
        "system_fingerprint": "fp-fireworks",
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
            "prompt_tokens_details": {"cached_tokens": 3},
        },
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": message,
            }
        ],
    }


def _tool_call(call_id, name: str, arguments: str):
    value = {
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }
    if call_id is not ...:
        value["id"] = call_id
    return value


def _mock_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> FireworksModelClient:
    return FireworksModelClient(
        api_key=FAKE_API_KEY,
        transport=httpx.MockTransport(handler),
    )


def _json_response(
    request: httpx.Request,
    value: object,
    *,
    status_code: int = 200,
) -> httpx.Response:
    return httpx.Response(status_code, json=value, request=request)


def test_request_mapping_is_exact_and_reasoning_is_explicit(make_request) -> None:
    request = _request(make_request)
    payload = build_fireworks_chat_completion_payload(request)

    assert payload["model"] == DEEPSEEK_V4_FLASH_0731_MODEL
    assert payload["temperature"] == 0.0
    assert payload["top_p"] == 1.0
    assert payload["seed"] == 99
    assert payload["max_completion_tokens"] == 321
    assert payload["parallel_tool_calls"] is False
    assert payload["tool_choice"] == "auto"
    assert payload["reasoning_effort"] == "none"
    assert payload["tools"] == [
        {"type": "function", "function": tool.as_dict()}
        for tool in request.tools
    ]
    assert "max_tokens" not in payload
    assert "reasoning_history" not in payload
    assert "thinking" not in payload


def test_original_generation_request_maps_without_provider_state() -> None:
    task = V1CreateTicketTaskSpec(
        customer_id="C",
        expected_title="X",
        expected_description="Y",
        user_task=USER_TASK,
    )
    config = ModelCallConfig(
        model=DEEPSEEK_V4_FLASH_0731_MODEL,
        temperature=0.0,
        top_p=1.0,
        seed=99,
        max_completion_tokens=321,
        parallel_tool_calls=False,
        tool_choice=ToolChoice.auto(),
        provider_parameters={"reasoning_effort": "none"},
    )

    payload = build_fireworks_chat_completion_payload(
        build_v1_original_generation_request(
            task_spec=task,
            model_config=config,
        )
    )

    assert [message["role"] for message in payload["messages"]] == [
        "system",
        "user",
    ]
    assert payload["reasoning_effort"] == "none"
    assert "reasoning_content" not in json.dumps(payload["messages"])


def test_frozen_assistant_and_tool_messages_map_without_hidden_state(
    make_request,
) -> None:
    payload = build_fireworks_chat_completion_payload(_request(make_request))

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
    assert payload["messages"][3] == {
        "role": "tool",
        "tool_call_id": "call-001",
        "content": CANONICAL_AMBIGUITY_TEXT,
    }
    serialized = json.dumps(payload["messages"])
    assert "reasoning_content" not in serialized
    assert "reasoning_history" not in serialized
    assert "thinking" not in serialized


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
def test_all_tool_choice_modes_map(make_request, choice, expected) -> None:
    payload = build_fireworks_chat_completion_payload(
        _request(make_request, tool_choice=choice)
    )

    assert payload["tool_choice"] == expected


@pytest.mark.parametrize(
    "provider_parameters",
    [
        {},
        {"reasoning_effort": None},
        {"reasoning_effort": "medium"},
        {"reasoning_effort": "high"},
        {"unsupported_option": "value", "reasoning_effort": "none"},
    ],
)
def test_unsafe_provider_parameters_fail_before_http(
    make_request,
    provider_parameters,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _json_response(request, _completion(content="unused"))

    client = _mock_client(handler)
    with pytest.raises(ModelRequestError):
        client.complete(
            _request(
                make_request,
                provider_parameters=provider_parameters,
            )
        )

    assert attempts == 0


def test_provider_identity_and_exact_endpoint(make_request) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _json_response(request, _completion(content="Done."))

    client = _mock_client(handler)
    response = client.complete(_request(make_request))

    assert client.provider == FIREWORKS_PROVIDER
    assert response.provider == FIREWORKS_PROVIDER
    assert len(seen) == 1
    assert str(seen[0].url) == FIREWORKS_CHAT_COMPLETIONS_URL
    assert seen[0].method == "POST"


def test_normal_text_response_and_metadata_are_captured() -> None:
    response = capture_fireworks_chat_completion(
        _completion(content="Done."),
        requested_model=DEEPSEEK_V4_FLASH_0731_MODEL,
    )

    assert response.assistant_message.content == "Done."
    assert response.assistant_message.tool_calls == ()
    assert response.finish_reason == "stop"
    assert response.provider == "fireworks"
    assert response.requested_model == DEEPSEEK_V4_FLASH_0731_MODEL
    assert response.returned_model == "accounts/fireworks/models/returned-model"
    assert response.provider_request_id == "fw-completion-123"
    assert response.system_fingerprint == "fp-fireworks"
    assert response.usage is not None
    assert response.usage.prompt_tokens == 11
    assert response.usage.completion_tokens == 7
    assert response.usage.total_tokens == 18


@pytest.mark.parametrize(
    ("tool_name", "raw"),
    [
        (
            "create_ticket",
            '{ "description": "Y", "customer_id": "C", "title": "X" }',
        ),
        ("list_tickets", "{ }"),
    ],
)
def test_single_tool_call_preserves_id_name_and_exact_arguments(
    tool_name,
    raw,
) -> None:
    response = capture_fireworks_chat_completion(
        _completion(
            tool_calls=[_tool_call("fw-call-1", tool_name, raw)],
            finish_reason="tool_calls",
        ),
        requested_model=DEEPSEEK_V4_FLASH_0731_MODEL,
    )
    call = response.assistant_message.tool_calls[0]

    assert call.tool_call_id == "fw-call-1"
    assert call.tool_name == tool_name
    assert call.arguments_json == raw
    assert call.parse_success is True
    assert response.finish_reason == "tool_calls"


def test_multiple_tool_calls_are_preserved_in_provider_order() -> None:
    response = capture_fireworks_chat_completion(
        _completion(
            tool_calls=[
                _tool_call("call-1", "list_tickets", "{}"),
                _tool_call("call-2", "create_ticket", '{"title":"X"}'),
            ],
            finish_reason="tool_calls",
        ),
        requested_model=DEEPSEEK_V4_FLASH_0731_MODEL,
    )

    assert [call.tool_call_id for call in response.assistant_message.tool_calls] == [
        "call-1",
        "call-2",
    ]
    assert [call.tool_name for call in response.assistant_message.tool_calls] == [
        "list_tickets",
        "create_ticket",
    ]


@pytest.mark.parametrize("call_id", [..., 7, None])
def test_missing_or_invalid_tool_call_id_is_retained(call_id) -> None:
    response = capture_fireworks_chat_completion(
        _completion(
            tool_calls=[_tool_call(call_id, "create_ticket", "{}")],
            finish_reason="tool_calls",
        ),
        requested_model=DEEPSEEK_V4_FLASH_0731_MODEL,
    )

    expected = None if call_id is ... else call_id
    assert response.assistant_message.tool_calls[0].tool_call_id == expected


@pytest.mark.parametrize(
    "raw",
    [
        '{"customer_id":"C",',
        "not-json-at-all",
        '{"x":1,"x":2}',
        '{"x":NaN}',
    ],
)
def test_malformed_arguments_are_preserved_without_repair(raw) -> None:
    response = capture_fireworks_chat_completion(
        _completion(
            tool_calls=[_tool_call("call-bad", "create_ticket", raw)],
            finish_reason="tool_calls",
        ),
        requested_model=DEEPSEEK_V4_FLASH_0731_MODEL,
    )
    call = response.assistant_message.tool_calls[0]

    assert call.arguments_json == raw
    assert call.parse_success is False
    assert call.parsed_arguments is None
    assert call.parse_error


def test_unknown_tool_name_remains_model_evidence() -> None:
    response = capture_fireworks_chat_completion(
        _completion(
            tool_calls=[_tool_call("call-1", "unknown_tool", "{}")],
            finish_reason="tool_calls",
        ),
        requested_model=DEEPSEEK_V4_FLASH_0731_MODEL,
    )

    assert response.assistant_message.tool_calls[0].tool_name == "unknown_tool"


@pytest.mark.parametrize("reasoning_content", [_ABSENT, None])
def test_absent_or_null_reasoning_content_succeeds(reasoning_content) -> None:
    response = capture_fireworks_chat_completion(
        _completion(
            content="visible",
            reasoning_content=reasoning_content,
        ),
        requested_model=DEEPSEEK_V4_FLASH_0731_MODEL,
    )

    assert response.assistant_message.content == "visible"
    assert not hasattr(response.assistant_message, "reasoning_content")


def test_non_null_reasoning_content_fails_closed_without_retaining_text() -> None:
    private_text = "sensitive unexpected reasoning text"

    with pytest.raises(ModelResponseError) as caught:
        capture_fireworks_chat_completion(
            _completion(
                content="visible",
                reasoning_content=private_text,
            ),
            requested_model=DEEPSEEK_V4_FLASH_0731_MODEL,
        )

    assert str(caught.value) == (
        "Fireworks unexpectedly returned reasoning content while "
        "non-reasoning operation was required"
    )
    assert private_text not in str(caught.value)


def test_multiturn_tool_result_request_uses_only_frozen_visible_state(
    make_request,
) -> None:
    bodies: list[dict] = []
    responses = [
        _completion(
            tool_calls=[_tool_call("recovery-list-1", "list_tickets", "{}")],
            finish_reason="tool_calls",
            reasoning_content=None,
        ),
        _completion(content="Done.", tool_calls=None, finish_reason="stop"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _json_response(request, responses[len(bodies) - 1])

    client = _mock_client(handler)
    request = _request(make_request)
    result = execute_llm_regeneration(
        TicketEnvironment.empty(),
        context=_context(make_request(customer_id="C", title="X", description="Y")),
        client=client,
        model_config=request.model_config,
        arm_id="arm-fireworks-offline",
    )

    assert len(result.model_invocations) == 2
    assert len(bodies) == 2
    second_messages = bodies[1]["messages"]
    assert second_messages[-2] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "recovery-list-1",
                "type": "function",
                "function": {"name": "list_tickets", "arguments": "{}"},
            }
        ],
    }
    assert second_messages[-1]["role"] == "tool"
    assert second_messages[-1]["tool_call_id"] == "recovery-list-1"
    assert "reasoning_content" not in json.dumps(second_messages)
    assert bodies[0]["reasoning_effort"] == "none"
    assert bodies[1]["reasoning_effort"] == "none"


def test_unexpected_reasoning_stops_all_model_and_tool_continuation(
    make_request,
) -> None:
    bodies: list[dict] = []
    private_text = "sensitive unexpected reasoning text"

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _json_response(
            request,
            _completion(
                tool_calls=[
                    _tool_call(
                        "must-not-execute",
                        "create_ticket",
                        '{"customer_id":"C","title":"X","description":"Y"}',
                    )
                ],
                finish_reason="tool_calls",
                reasoning_content=private_text,
            ),
        )

    environment = TicketEnvironment.empty()
    client = _mock_client(handler)
    request = _request(make_request)
    result = execute_llm_regeneration(
        environment,
        context=_context(make_request(customer_id="C", title="X", description="Y")),
        client=client,
        model_config=request.model_config,
        arm_id="arm-fireworks-reasoning-failure",
    )

    assert len(bodies) == 1
    assert bodies[0]["reasoning_effort"] == "none"
    assert len(result.model_invocations) == 1
    assert result.recovery_actions == ()
    assert result.recovery_tool_calls_attempted == 0
    assert result.recovery_tool_calls_executed == 0
    assert environment.state.tickets == ()
    infrastructure_error = result.model_invocations[0].infrastructure_error
    assert isinstance(infrastructure_error, ModelResponseError)
    assert private_text not in str(infrastructure_error)


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (400, ModelProviderStatusError),
        (401, ModelAuthenticationError),
        (403, ModelAuthenticationError),
        (408, ModelProviderStatusError),
        (422, ModelProviderStatusError),
        (429, ModelRateLimitError),
        (500, ModelProviderStatusError),
        (503, ModelProviderStatusError),
    ],
)
def test_http_failures_are_infrastructure_and_never_retried(
    make_request,
    status_code,
    expected_error,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _json_response(
            request,
            {"error": {"message": "offline provider failure"}},
            status_code=status_code,
        )

    client = _mock_client(handler)
    with pytest.raises(expected_error) as caught:
        client.complete(_request(make_request))

    assert attempts == 1
    if isinstance(caught.value, ModelProviderStatusError):
        assert caught.value.status_code == status_code


@pytest.mark.parametrize(
    ("exception_factory", "expected_error"),
    [
        (
            lambda request: httpx.ReadTimeout("offline timeout", request=request),
            ModelTimeoutError,
        ),
        (
            lambda request: httpx.ConnectError(
                "offline connection failure", request=request
            ),
            ModelTransportError,
        ),
    ],
)
def test_transport_failures_are_never_retried(
    make_request,
    exception_factory,
    expected_error,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise exception_factory(request)

    client = _mock_client(handler)
    with pytest.raises(expected_error) as caught:
        client.complete(_request(make_request))

    assert attempts == 1
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_successful_but_structurally_unreadable_response_is_not_retried(
    make_request,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _json_response(request, {"choices": []})

    client = _mock_client(handler)
    with pytest.raises(ModelResponseError):
        client.complete(_request(make_request))

    assert attempts == 1


def test_default_transport_has_zero_retries_finite_timeout_and_no_redirects(
    monkeypatch,
) -> None:
    transport_kwargs = {}
    client_kwargs = {}
    sentinel_transport = object()

    class FakeClient:
        def __init__(self, **kwargs):
            client_kwargs.update(kwargs)

        def close(self):
            pass

    def fake_transport(**kwargs):
        transport_kwargs.update(kwargs)
        return sentinel_transport

    monkeypatch.setattr(fireworks_module.httpx, "HTTPTransport", fake_transport)
    monkeypatch.setattr(fireworks_module.httpx, "Client", FakeClient)

    client = FireworksModelClient(
        api_key=FAKE_API_KEY,
        timeout_seconds=12.5,
    )
    client.close()

    assert transport_kwargs == {"retries": 0}
    assert client_kwargs["transport"].transport is sentinel_transport
    assert client_kwargs["follow_redirects"] is False
    assert client_kwargs["trust_env"] is False
    assert client_kwargs["timeout"] == httpx.Timeout(12.5)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True])
def test_invalid_timeout_is_rejected_without_client_construction(timeout) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        FireworksModelClient(api_key=FAKE_API_KEY, timeout_seconds=timeout)


def test_missing_api_key_is_rejected_without_loading_dotenv(monkeypatch) -> None:
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)

    with pytest.raises(ValueError, match="FIREWORKS_API_KEY"):
        FireworksModelClient()
