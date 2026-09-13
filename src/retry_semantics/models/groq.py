"""Groq Chat Completions adapter for local (caller-executed) tool calling."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import groq as groq_sdk

from retry_semantics.models.base import (
    ModelAssistantMessage,
    ModelAuthenticationError,
    ModelProviderError,
    ModelProviderStatusError,
    ModelRateLimitError,
    ModelRejectedGenerationError,
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

GROQ_PROVIDER = "groq"
_TOOL_USE_FAILED = "tool_use_failed"
_INVALID_REQUEST_ERROR = "invalid_request_error"


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
                        # This exact stored string is the historical request.
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


def build_groq_chat_completion_kwargs(request: ModelRequest) -> dict[str, Any]:
    """Purely map one provider-neutral request to Groq SDK keyword arguments."""

    if type(request) is not ModelRequest:
        raise ModelRequestError("request must be a ModelRequest")
    config = request.model_config
    kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": [_map_message(message) for message in request.messages],
        "tools": [
            {"type": "function", "function": tool.as_dict()}
            for tool in request.tools
        ],
        "tool_choice": _map_tool_choice(config.tool_choice),
    }
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature
    if config.seed is not None:
        kwargs["seed"] = config.seed
    if config.max_completion_tokens is not None:
        kwargs["max_completion_tokens"] = config.max_completion_tokens
    return kwargs


_MISSING = object()


def _field(value: Any, name: str, default: Any = _MISSING) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
    elif hasattr(value, name):
        return getattr(value, name)
    if default is not _MISSING:
        return default
    raise ModelResponseError(f"Groq response is missing {name!r}")


def _optional_string(value: Any, label: str) -> str | None:
    if value is None or type(value) is str:
        return value
    raise ModelResponseError(f"Groq {label} must be a string or null")


def _capture_tool_call(raw_call: Any) -> ModelToolCall:
    function = _field(raw_call, "function")
    tool_call_id = _field(raw_call, "id")
    name = _field(function, "name")
    arguments_json = _field(function, "arguments")
    if type(tool_call_id) is not str:
        raise ModelResponseError("Groq tool-call ID must be a string")
    if type(name) is not str:
        raise ModelResponseError("Groq tool-call name must be a string")
    if type(arguments_json) is not str:
        raise ModelResponseError("Groq tool-call arguments must be a raw string")
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
    return ModelUsage(
        prompt_tokens=_field(raw_usage, "prompt_tokens", None),
        completion_tokens=_field(raw_usage, "completion_tokens", None),
        total_tokens=_field(raw_usage, "total_tokens", None),
    )


def _provider_request_id(error: groq_sdk.BadRequestError) -> str | None:
    """Read only the documented-style request ID header, never arbitrary headers."""

    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    request_id = headers.get("x-request-id")
    return request_id if type(request_id) is str else None


def _rejected_generation_behavior(
    error: groq_sdk.BadRequestError,
) -> ModelRejectedGenerationError | None:
    """Recognize Groq's two structured rejected-generation response forms."""

    body = getattr(error, "body", None)
    if not isinstance(body, Mapping):
        return None
    error_value = body.get("error")
    if not isinstance(error_value, Mapping):
        return None
    if "failed_generation" not in error_value:
        return None
    provider_error_code = error_value.get("code")
    has_explicit_tool_use_code = provider_error_code == _TOOL_USE_FAILED
    has_documented_code_absent_shape = (
        provider_error_code is None
        and error_value.get("type") == _INVALID_REQUEST_ERROR
    )
    if not (has_explicit_tool_use_code or has_documented_code_absent_shape):
        return None
    failed_generation = freeze_json_value(error_value["failed_generation"])
    return ModelRejectedGenerationError(
        provider=GROQ_PROVIDER,
        provider_error_code=provider_error_code,
        failed_generation=failed_generation,
        provider_request_id=_provider_request_id(error),
    )


def capture_groq_chat_completion(
    completion: Any,
    *,
    requested_model: str,
) -> ModelResponse:
    """Purely capture one structurally readable Groq completion without repair."""

    if type(requested_model) is not str or requested_model == "":
        raise ModelResponseError("requested_model must be a non-empty string")
    raw_choices = _field(completion, "choices")
    if isinstance(raw_choices, (str, bytes)):
        raise ModelResponseError("Groq choices must be a sequence")
    try:
        choices = tuple(raw_choices)
    except TypeError as exc:
        raise ModelResponseError("Groq choices must be a sequence") from exc
    if len(choices) != 1:
        raise ModelResponseError("Groq completion must contain exactly one choice")

    choice = choices[0]
    raw_message = _field(choice, "message")
    raw_tool_calls = _field(raw_message, "tool_calls", None)
    if raw_tool_calls is None:
        tool_calls: tuple[ModelToolCall, ...] = ()
    else:
        if isinstance(raw_tool_calls, (str, bytes)):
            raise ModelResponseError("Groq tool_calls must be a sequence or null")
        try:
            tool_calls = tuple(_capture_tool_call(call) for call in raw_tool_calls)
        except TypeError as exc:
            raise ModelResponseError(
                "Groq tool_calls must be a sequence or null"
            ) from exc

    assistant_message = ModelAssistantMessage(
        role=_field(raw_message, "role"),
        content=_optional_string(
            _field(raw_message, "content", None), "assistant content"
        ),
        tool_calls=tool_calls,
    )
    return ModelResponse(
        assistant_message=assistant_message,
        finish_reason=_optional_string(
            _field(choice, "finish_reason", None), "finish reason"
        ),
        provider=GROQ_PROVIDER,
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


class GroqModelClient:
    """Stateless-message Groq client that performs one call per ``complete``."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        sdk_client: Any | None = None,
    ) -> None:
        if type(timeout_seconds) not in (int, float) or not math.isfinite(
            timeout_seconds
        ) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive finite number")
        if sdk_client is None:
            # Provider transport retries are disabled so a logical model
            # invocation corresponds to one explicit experiment-level invocation.
            self._client = groq_sdk.Groq(
                api_key=api_key,
                timeout=float(timeout_seconds),
                max_retries=0,
            )
        else:
            self._client = sdk_client

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Submit the complete explicit history in one Groq invocation."""

        kwargs = build_groq_chat_completion_kwargs(request)
        rejected_failure: ModelRejectedGenerationError | ModelResponseError | None = (
            None
        )
        try:
            completion = self._client.chat.completions.create(**kwargs)
        except groq_sdk.APITimeoutError as exc:
            raise ModelTimeoutError("Groq model invocation timed out") from exc
        except groq_sdk.BadRequestError as exc:
            try:
                behavior = _rejected_generation_behavior(exc)
            except ModelResponseError:
                # Do not retain the SDK exception: its request may contain
                # authorization headers. The sanitized error is raised after
                # leaving this exception context.
                rejected_failure = ModelResponseError(
                    "Groq rejected generation contained unreadable failed_generation"
                )
            else:
                if behavior is None:
                    raise ModelProviderStatusError(
                        "Groq returned a non-success status",
                        status_code=exc.status_code,
                    ) from exc
                rejected_failure = behavior
        except groq_sdk.AuthenticationError as exc:
            raise ModelAuthenticationError(
                "Groq rejected the configured credentials"
            ) from exc
        except groq_sdk.RateLimitError as exc:
            raise ModelRateLimitError(
                "Groq rate limit rejected the invocation"
            ) from exc
        except groq_sdk.APIConnectionError as exc:
            raise ModelTransportError(
                "Groq model invocation could not connect"
            ) from exc
        except groq_sdk.APIResponseValidationError as exc:
            raise ModelResponseError(
                "Groq returned a response the official SDK could not validate"
            ) from exc
        except groq_sdk.APIStatusError as exc:
            raise ModelProviderStatusError(
                "Groq returned a non-success status",
                status_code=exc.status_code,
            ) from exc
        except groq_sdk.APIError as exc:
            raise ModelProviderError("Groq model invocation failed") from exc
        if rejected_failure is not None:
            # Raise outside the SDK exception handler so behavioral evidence
            # cannot retain the provider request or its authorization headers.
            raise rejected_failure
        return capture_groq_chat_completion(
            completion,
            requested_model=request.model_config.model,
        )


__all__ = [
    "GROQ_PROVIDER",
    "GroqModelClient",
    "build_groq_chat_completion_kwargs",
    "capture_groq_chat_completion",
]
