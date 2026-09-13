"""Provider-neutral boundary for one stateless model invocation."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, TypeAlias, runtime_checkable

from retry_semantics.runtime.regeneration_context import (
    CanonicalContextMessage,
    CanonicalRegenerationContext,
    FrozenToolDefinition,
)
from retry_semantics.serialization import canonical_json_bytes, sha256_hex


class ModelBoundaryError(Exception):
    """Base exception for failures at the model-call boundary."""


class ModelRequestError(ModelBoundaryError, ValueError):
    """A provider-neutral request or configuration is invalid."""


class ModelBehaviorError(ModelBoundaryError):
    """Readable evidence that the model produced a behavioral failure."""


class ModelProviderError(ModelBoundaryError):
    """The provider invocation failed before a readable model response existed."""


class ModelTransportError(ModelProviderError):
    """The provider could not be reached."""


class ModelTimeoutError(ModelTransportError):
    """The single provider invocation exceeded its transport timeout."""


class ModelAuthenticationError(ModelProviderError):
    """The provider rejected the configured credentials."""


class ModelRateLimitError(ModelProviderError):
    """The provider rejected the invocation because of a rate limit."""


class ModelProviderStatusError(ModelProviderError):
    """The provider returned another non-success HTTP status."""

    def __init__(self, message: str, *, status_code: int | None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ModelResponseError(ModelProviderError):
    """The provider response was not structurally readable by the adapter."""


class ToolChoiceMode(str, Enum):
    AUTO = "AUTO"
    REQUIRED = "REQUIRED"
    NONE = "NONE"
    FORCED_FUNCTION = "FORCED_FUNCTION"


@dataclass(frozen=True, slots=True)
class ToolChoice:
    """Provider-neutral tool-selection mode for one invocation."""

    mode: ToolChoiceMode
    function_name: str | None = None

    def __post_init__(self) -> None:
        if type(self.mode) is not ToolChoiceMode:
            raise ModelRequestError("tool-choice mode must be a ToolChoiceMode")
        if self.mode is ToolChoiceMode.FORCED_FUNCTION:
            if type(self.function_name) is not str or self.function_name == "":
                raise ModelRequestError(
                    "FORCED_FUNCTION requires a non-empty function name"
                )
        elif self.function_name is not None:
            raise ModelRequestError(
                "a function name is only valid with FORCED_FUNCTION"
            )

    @classmethod
    def auto(cls) -> ToolChoice:
        return cls(ToolChoiceMode.AUTO)

    @classmethod
    def required(cls) -> ToolChoice:
        return cls(ToolChoiceMode.REQUIRED)

    @classmethod
    def none(cls) -> ToolChoice:
        return cls(ToolChoiceMode.NONE)

    @classmethod
    def forced_function(cls, name: str) -> ToolChoice:
        return cls(ToolChoiceMode.FORCED_FUNCTION, name)


@dataclass(frozen=True, slots=True)
class ModelCallConfig:
    """Model and sampling settings kept outside canonical visible context."""

    model: str
    temperature: float | None
    seed: int | None
    max_completion_tokens: int | None
    tool_choice: ToolChoice

    def __post_init__(self) -> None:
        if type(self.model) is not str or self.model == "":
            raise ModelRequestError("model must be a non-empty string")
        if self.temperature is not None:
            if type(self.temperature) not in (int, float) or not math.isfinite(
                self.temperature
            ):
                raise ModelRequestError("temperature must be a finite number or null")
        if self.seed is not None and type(self.seed) is not int:
            raise ModelRequestError("seed must be an integer or null")
        if self.max_completion_tokens is not None and (
            type(self.max_completion_tokens) is not int
            or self.max_completion_tokens < 1
        ):
            raise ModelRequestError(
                "max_completion_tokens must be a positive integer or null"
            )
        if type(self.tool_choice) is not ToolChoice:
            raise ModelRequestError("tool_choice must be a ToolChoice")


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Everything needed for exactly one stateless model invocation."""

    messages: tuple[CanonicalContextMessage, ...]
    tools: tuple[FrozenToolDefinition, ...]
    model_config: ModelCallConfig

    def __post_init__(self) -> None:
        if type(self.messages) is not tuple or any(
            type(message) is not CanonicalContextMessage
            for message in self.messages
        ):
            raise ModelRequestError(
                "messages must be an immutable tuple of canonical messages"
            )
        if type(self.tools) is not tuple or any(
            type(tool) is not FrozenToolDefinition for tool in self.tools
        ):
            raise ModelRequestError(
                "tools must be an immutable tuple of frozen tool definitions"
            )
        if type(self.model_config) is not ModelCallConfig:
            raise ModelRequestError("model_config must be a ModelCallConfig")


JsonScalar: TypeAlias = str | int | float | bool | None
ImmutableJson: TypeAlias = JsonScalar | tuple["ImmutableJson", ...] | Mapping[
    str, "ImmutableJson"
]


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r}")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _freeze_json(value: Any) -> ImmutableJson:
    if value is None or isinstance(value, (str, bool)) or type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return value
    if type(value) is list:
        return tuple(_freeze_json(item) for item in value)
    if type(value) is dict:
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    raise TypeError(f"unsupported parsed JSON type: {type(value).__name__}")


def _is_immutable_json(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool)) or type(value) in (int, float):
        return type(value) is not float or math.isfinite(value)
    if type(value) is tuple:
        return all(_is_immutable_json(item) for item in value)
    if type(value) is MappingProxyType:
        return all(
            type(key) is str and _is_immutable_json(item)
            for key, item in value.items()
        )
    return False


def freeze_json_value(value: Any) -> ImmutableJson:
    """Copy JSON-compatible provider data into recursively immutable values."""

    try:
        return _freeze_json(value)
    except (TypeError, ValueError) as exc:
        raise ModelResponseError(
            "provider data is not a readable JSON-compatible value"
        ) from exc


def parse_tool_arguments_json(
    arguments_json: str,
) -> tuple[bool, ImmutableJson | None, str | None]:
    """Parse strict JSON without changing the caller's raw argument string."""

    if type(arguments_json) is not str:
        raise TypeError("arguments_json must be a string")
    try:
        decoded = json.loads(
            arguments_json,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
        frozen = _freeze_json(decoded)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return False, None, f"{type(exc).__name__}: {exc}"
    return True, frozen, None


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    """One exactly captured model-returned tool request."""

    tool_call_id: ImmutableJson
    tool_name: str
    arguments_json: str
    parse_success: bool
    parsed_arguments: ImmutableJson | None
    parse_error: str | None
    tool_type: str | None

    def __post_init__(self) -> None:
        if not _is_immutable_json(self.tool_call_id):
            raise ModelResponseError(
                "tool-call ID must be an immutable JSON-compatible value"
            )
        if type(self.tool_name) is not str:
            raise ModelResponseError("tool-call name must be a string")
        if type(self.arguments_json) is not str:
            raise ModelResponseError("tool-call arguments must be a raw string")
        if type(self.parse_success) is not bool:
            raise ModelResponseError("parse_success must be a bool")
        if self.parse_success and self.parse_error is not None:
            raise ModelResponseError("a parsed tool call cannot have a parse error")
        if self.parse_success and not _is_immutable_json(self.parsed_arguments):
            raise ModelResponseError(
                "parsed tool-call arguments must be an immutable JSON value"
            )
        if not self.parse_success and (
            self.parsed_arguments is not None
            or type(self.parse_error) is not str
            or self.parse_error == ""
        ):
            raise ModelResponseError(
                "an unparsed tool call must retain one parse error"
            )
        if self.tool_type is not None and type(self.tool_type) is not str:
            raise ModelResponseError("tool-call type must be a string or null")


@dataclass(frozen=True, slots=True)
class ModelRejectedGenerationError(ModelBehaviorError):
    """Provider evidence that a model generation was rejected before completion."""

    provider: str
    provider_error_code: str | None
    failed_generation: ImmutableJson
    provider_request_id: str | None

    def __post_init__(self) -> None:
        if type(self.provider) is not str or self.provider == "":
            raise ModelResponseError("rejected-generation provider must be non-empty")
        if self.provider_error_code is not None and (
            type(self.provider_error_code) is not str
            or self.provider_error_code == ""
        ):
            raise ModelResponseError(
                "rejected-generation provider error code must be non-empty or null"
            )
        if not _is_immutable_json(self.failed_generation):
            raise ModelResponseError(
                "failed_generation must be an immutable JSON-compatible value"
            )
        if self.provider_request_id is not None and type(
            self.provider_request_id
        ) is not str:
            raise ModelResponseError(
                "rejected-generation provider request ID must be a string or null"
            )
        detail = (
            f"with code {self.provider_error_code}"
            if self.provider_error_code is not None
            else "without a provider error code"
        )
        ModelBehaviorError.__init__(
            self, f"{self.provider} rejected model generation {detail}"
        )


@dataclass(frozen=True, slots=True)
class ModelAssistantMessage:
    """Assistant message returned by a provider, with all tool calls in order."""

    role: str
    content: str | None
    tool_calls: tuple[ModelToolCall, ...]

    def __post_init__(self) -> None:
        if self.role != "assistant":
            raise ModelResponseError(
                "assistant-message role must be exactly 'assistant'"
            )
        if self.content is not None and type(self.content) is not str:
            raise ModelResponseError(
                "assistant-message content must be a string or null"
            )
        if type(self.tool_calls) is not tuple or any(
            type(call) is not ModelToolCall for call in self.tool_calls
        ):
            raise ModelResponseError("assistant tool_calls must be an immutable tuple")


@dataclass(frozen=True, slots=True)
class ModelUsage:
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None

    def __post_init__(self) -> None:
        for name, value in (
            ("prompt_tokens", self.prompt_tokens),
            ("completion_tokens", self.completion_tokens),
            ("total_tokens", self.total_tokens),
        ):
            if value is not None and (type(value) is not int or value < 0):
                raise ModelResponseError(
                    f"{name} must be a non-negative integer or null"
                )


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Immutable provider-neutral capture of one model completion."""

    assistant_message: ModelAssistantMessage
    finish_reason: str | None
    provider: str
    requested_model: str
    returned_model: str | None
    usage: ModelUsage | None
    system_fingerprint: str | None
    provider_request_id: str | None

    def __post_init__(self) -> None:
        if type(self.assistant_message) is not ModelAssistantMessage:
            raise ModelResponseError("assistant_message has the wrong type")
        for name, value, required in (
            ("finish_reason", self.finish_reason, False),
            ("provider", self.provider, True),
            ("requested_model", self.requested_model, True),
            ("returned_model", self.returned_model, False),
            ("system_fingerprint", self.system_fingerprint, False),
            ("provider_request_id", self.provider_request_id, False),
        ):
            if (required and (type(value) is not str or value == "")) or (
                not required and value is not None and type(value) is not str
            ):
                raise ModelResponseError(f"{name} has the wrong type or value")
        if self.usage is not None and type(self.usage) is not ModelUsage:
            raise ModelResponseError("usage must be ModelUsage or null")


@runtime_checkable
class ModelClient(Protocol):
    """The complete provider-neutral model-client interface."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Perform exactly one model invocation."""


def model_request_from_regeneration_context(
    context: CanonicalRegenerationContext,
    model_config: ModelCallConfig,
) -> ModelRequest:
    """Combine frozen visible context with separately supplied call settings."""

    if type(context) is not CanonicalRegenerationContext:
        raise ModelRequestError("context must be a CanonicalRegenerationContext")
    if type(model_config) is not ModelCallConfig:
        raise ModelRequestError("model_config must be a ModelCallConfig")
    expected_bytes = canonical_json_bytes(context.as_dict())
    if context.canonical_context_bytes != expected_bytes:
        raise ModelRequestError("canonical context bytes are incoherent")
    if context.canonical_context_sha256 != sha256_hex(expected_bytes):
        raise ModelRequestError("canonical context hash is incoherent")
    return ModelRequest(
        messages=context.messages,
        tools=context.tools,
        model_config=model_config,
    )


__all__ = [
    "ImmutableJson",
    "ModelAssistantMessage",
    "ModelAuthenticationError",
    "ModelBehaviorError",
    "ModelBoundaryError",
    "ModelCallConfig",
    "ModelClient",
    "ModelProviderError",
    "ModelProviderStatusError",
    "ModelRateLimitError",
    "ModelRejectedGenerationError",
    "ModelRequest",
    "ModelRequestError",
    "ModelResponse",
    "ModelResponseError",
    "ModelTimeoutError",
    "ModelToolCall",
    "ModelTransportError",
    "ModelUsage",
    "ToolChoice",
    "ToolChoiceMode",
    "freeze_json_value",
    "model_request_from_regeneration_context",
    "parse_tool_arguments_json",
]
