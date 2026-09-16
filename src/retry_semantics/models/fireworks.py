"""Fireworks Chat Completions adapter for the frozen non-reasoning protocol."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from typing import Any

import httpx

from retry_semantics.models.base import (
    ModelAssistantMessage,
    ModelAuthenticationError,
    ModelProviderStatusError,
    ModelRateLimitError,
    ModelRequest,
    ModelRequestError,
    ModelResponse,
    ModelResponseError,
    ModelTimeoutError,
    ModelToolCall,
    ModelTransportError,
    ModelUsage,
    ToolChoice,
    ToolChoiceMode,
    freeze_json_value,
    parse_tool_arguments_json,
)

FIREWORKS_PROVIDER = "fireworks"
FIREWORKS_CHAT_COMPLETIONS_URL = (
    "https://api.fireworks.ai/inference/v1/chat/completions"
)
DEEPSEEK_V4_FLASH_0731_MODEL = (
    "accounts/fireworks/models/deepseek-v4-flash-0731"
)


def _map_tool_choice(tool_choice: ToolChoice) -> str | dict[str, Any]:
    if type(tool_choice) is not ToolChoice:
        raise ModelRequestError("tool_choice must be a ToolChoice")
    if tool_choice.mode is ToolChoiceMode.AUTO:
        return "auto"
    if tool_choice.mode is ToolChoiceMode.REQUIRED:
        return "required"
    if tool_choice.mode is ToolChoiceMode.NONE:
        return "none"
    return {
        "type": "function",
        "function": {"name": tool_choice.function_name},
    }


def _map_message(message: Any) -> dict[str, Any]:
    if message.role in ("system", "user"):
        if message.tool_calls or message.tool_call_id is not None:
            raise ModelRequestError(f"{message.role} message has invalid tool fields")
        return {"role": message.role, "content": message.content}
    if message.role == "assistant":
        if message.tool_call_id is not None:
            raise ModelRequestError(
                "assistant message cannot have a message-level tool_call_id"
            )
        mapped: dict[str, Any] = {
            "role": "assistant",
            "content": message.content,
        }
        if message.tool_calls:
            mapped["tool_calls"] = [
                {
                    "id": call.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": call.tool,
                        # Preserve the historical provider string byte-for-character.
                        "arguments": call.arguments_json,
                    },
                }
                for call in message.tool_calls
            ]
        return mapped
    if message.role == "tool":
        if message.tool_calls:
            raise ModelRequestError("tool message cannot contain tool_calls")
        if type(message.tool_call_id) is not str or message.tool_call_id == "":
            raise ModelRequestError("tool message requires a non-empty tool_call_id")
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    raise ModelRequestError(f"unsupported message role: {message.role!r}")


def _map_provider_parameters(
    model: str, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for key in sorted(parameters):
        if key != "reasoning_effort":
            raise ModelRequestError(
                "Fireworks adapter does not support provider parameter " f"{key!r}"
            )
        value = parameters[key]
        if value != "none" or type(value) is not str:
            raise ModelRequestError(
                "Fireworks reasoning_effort must be exactly 'none'"
            )
        mapped["reasoning_effort"] = "none"

    if model == DEEPSEEK_V4_FLASH_0731_MODEL and mapped.get(
        "reasoning_effort"
    ) != "none":
        raise ModelRequestError(
            "DeepSeek V4 Flash 0731 requires explicit reasoning_effort='none'"
        )
    return mapped


def build_fireworks_chat_completion_payload(
    request: ModelRequest,
) -> dict[str, Any]:
    """Purely map one provider-neutral request to one Fireworks JSON body."""

    if type(request) is not ModelRequest:
        raise ModelRequestError("request must be a ModelRequest")
    config = request.model_config
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [_map_message(message) for message in request.messages],
        "tools": [
            {"type": "function", "function": tool.as_dict()}
            for tool in request.tools
        ],
        "tool_choice": _map_tool_choice(config.tool_choice),
    }
    payload.update(
        _map_provider_parameters(config.model, config.provider_parameters)
    )
    if config.temperature is not None:
        payload["temperature"] = config.temperature
    if config.top_p is not None:
        payload["top_p"] = config.top_p
    if config.seed is not None:
        payload["seed"] = config.seed
    if config.max_completion_tokens is not None:
        payload["max_completion_tokens"] = config.max_completion_tokens
    if config.parallel_tool_calls is not None:
        payload["parallel_tool_calls"] = config.parallel_tool_calls
    return payload


_MISSING = object()


def _field(value: Any, name: str, default: Any = _MISSING) -> Any:
    if isinstance(value, Mapping) and name in value:
        return value[name]
    if default is not _MISSING:
        return default
    raise ModelResponseError(f"Fireworks response is missing {name!r}")


def _optional_string(value: Any, label: str) -> str | None:
    if value is None or type(value) is str:
        return value
    raise ModelResponseError(f"Fireworks {label} must be a string or null")


def _capture_tool_call(raw_call: Any) -> ModelToolCall:
    function = _field(raw_call, "function")
    tool_call_id = freeze_json_value(_field(raw_call, "id", None))
    name = _field(function, "name")
    arguments_json = _field(function, "arguments")
    if type(name) is not str:
        raise ModelResponseError("Fireworks tool-call name must be a string")
    if type(arguments_json) is not str:
        raise ModelResponseError(
            "Fireworks tool-call arguments must be a raw string"
        )
    parse_success, parsed_arguments, parse_error = parse_tool_arguments_json(
        arguments_json
    )
    return ModelToolCall(
        tool_call_id=tool_call_id,
        tool_name=name,
        arguments_json=arguments_json,
        parse_success=parse_success,
        parsed_arguments=parsed_arguments,
        parse_error=parse_error,
        tool_type=_optional_string(
            _field(raw_call, "type", None), "tool-call type"
        ),
    )


def _capture_usage(raw_usage: Any) -> ModelUsage | None:
    if raw_usage is None:
        return None
    if not isinstance(raw_usage, Mapping):
        raise ModelResponseError("Fireworks usage must be an object or null")
    return ModelUsage(
        prompt_tokens=_field(raw_usage, "prompt_tokens", None),
        completion_tokens=_field(raw_usage, "completion_tokens", None),
        total_tokens=_field(raw_usage, "total_tokens", None),
    )


def capture_fireworks_chat_completion(
    completion: Any,
    *,
    requested_model: str,
) -> ModelResponse:
    """Capture one readable Fireworks completion without repair or normalization."""

    if type(requested_model) is not str or requested_model == "":
        raise ModelResponseError("requested_model must be a non-empty string")
    if not isinstance(completion, Mapping):
        raise ModelResponseError("Fireworks completion must be a JSON object")
    raw_choices = _field(completion, "choices")
    if not isinstance(raw_choices, list):
        raise ModelResponseError("Fireworks choices must be a JSON array")
    if len(raw_choices) != 1:
        raise ModelResponseError(
            "Fireworks completion must contain exactly one choice"
        )

    choice = raw_choices[0]
    raw_message = _field(choice, "message")
    if not isinstance(raw_message, Mapping):
        raise ModelResponseError("Fireworks assistant message must be an object")
    if (
        requested_model == DEEPSEEK_V4_FLASH_0731_MODEL
        and _field(raw_message, "reasoning_content", None) is not None
    ):
        raise ModelResponseError(
            "Fireworks unexpectedly returned reasoning content while "
            "non-reasoning operation was required"
        )
    raw_tool_calls = _field(raw_message, "tool_calls", None)
    if raw_tool_calls is None:
        tool_calls: tuple[ModelToolCall, ...] = ()
    elif isinstance(raw_tool_calls, list):
        tool_calls = tuple(_capture_tool_call(call) for call in raw_tool_calls)
    else:
        raise ModelResponseError(
            "Fireworks tool_calls must be a JSON array or null"
        )

    return ModelResponse(
        assistant_message=ModelAssistantMessage(
            role=_field(raw_message, "role"),
            content=_optional_string(
                _field(raw_message, "content", None), "assistant content"
            ),
            tool_calls=tool_calls,
        ),
        finish_reason=_optional_string(
            _field(choice, "finish_reason", None), "finish reason"
        ),
        provider=FIREWORKS_PROVIDER,
        requested_model=requested_model,
        returned_model=_optional_string(
            _field(completion, "model", None), "returned model"
        ),
        usage=_capture_usage(_field(completion, "usage", None)),
        system_fingerprint=_optional_string(
            _field(completion, "system_fingerprint", None),
            "system fingerprint",
        ),
        provider_request_id=_optional_string(
            _field(completion, "id", None), "completion ID"
        ),
    )


class FireworksModelClient:
    """One-request Fireworks client with transport retries disabled."""

    @property
    def provider(self) -> str:
        return FIREWORKS_PROVIDER

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if type(timeout_seconds) not in (int, float) or not math.isfinite(
            timeout_seconds
        ) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive finite number")
        resolved_api_key = (
            os.environ.get("FIREWORKS_API_KEY") if api_key is None else api_key
        )
        if type(resolved_api_key) is not str or resolved_api_key == "":
            raise ValueError("FIREWORKS_API_KEY must be a non-empty string")
        resolved_transport = (
            httpx.HTTPTransport(retries=0)
            if transport is None
            else transport
        )
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {resolved_api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(float(timeout_seconds)),
            follow_redirects=False,
            transport=resolved_transport,
            trust_env=False,
        )

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Validate locally, then issue at most one inference HTTP request."""

        payload = build_fireworks_chat_completion_payload(request)
        transport_failure: ModelTimeoutError | ModelTransportError | None = None
        try:
            response = self._client.post(
                FIREWORKS_CHAT_COMPLETIONS_URL,
                json=payload,
            )
        except httpx.TimeoutException:
            transport_failure = ModelTimeoutError(
                "Fireworks model invocation timed out"
            )
        except httpx.RequestError:
            transport_failure = ModelTransportError(
                "Fireworks model invocation could not connect"
            )
        if transport_failure is not None:
            # Raise outside the httpx handler so the sanitized boundary error
            # cannot retain a request object containing Authorization headers.
            raise transport_failure

        status_code = response.status_code
        if status_code in (401, 403):
            raise ModelAuthenticationError(
                "Fireworks rejected the configured credentials"
            )
        if status_code == 429:
            raise ModelRateLimitError(
                "Fireworks rate limit rejected the invocation"
            )
        if not 200 <= status_code < 300:
            raise ModelProviderStatusError(
                "Fireworks returned a non-success status",
                status_code=status_code,
            )

        try:
            completion = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ModelResponseError(
                "Fireworks returned a non-JSON success response"
            ) from exc
        return capture_fireworks_chat_completion(
            completion,
            requested_model=request.model_config.model,
        )

    def close(self) -> None:
        self._client.close()


__all__ = [
    "DEEPSEEK_V4_FLASH_0731_MODEL",
    "FIREWORKS_CHAT_COMPLETIONS_URL",
    "FIREWORKS_PROVIDER",
    "FireworksModelClient",
    "build_fireworks_chat_completion_payload",
    "capture_fireworks_chat_completion",
]
