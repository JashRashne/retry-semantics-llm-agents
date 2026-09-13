"""One-shot original-generation and eligibility boundary for V1 CREATE."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import TypeAlias

from retry_semantics.environments.ticket import FrozenExecutableRequest
from retry_semantics.models.base import (
    ModelCallConfig,
    ModelClient,
    ModelRejectedGenerationError,
    ModelRequest,
    ModelRequestError,
    ModelResponse,
    ModelResponseError,
    ToolChoiceMode,
    parse_tool_arguments_json,
)
from retry_semantics.runtime.regeneration_context import (
    FROZEN_SYSTEM_MESSAGE,
    FROZEN_TOOL_CATALOG,
    CanonicalContextMessage,
    CanonicalToolCall,
    CreateTicketArguments,
)

_CREATE_TICKET = "create_ticket"
_CREATE_ARGUMENT_FIELDS = frozenset({"customer_id", "title", "description"})


def _validate_v1_scenario_value(name: str, value: object) -> str:
    if type(value) is not str or value == "":
        raise ModelRequestError(f"{name} must be a non-empty string")
    if '"' in value:
        raise ModelRequestError(f'{name} must not contain a double quote (\")')
    if any(ord(character) < 0x20 or ord(character) > 0x7E for character in value):
        raise ModelRequestError(
            f"{name} must contain only printable ASCII characters from 0x20 to 0x7E"
        )
    return value


def _render_validated_v1_create_ticket_task(
    *, customer_id: str, expected_title: str, expected_description: str
) -> str:
    return (
        f'Create exactly one support ticket for customer "{customer_id}" with title '
        f'"{expected_title}" and description "{expected_description}".'
    )


class OriginalGenerationFailureReason(str, Enum):
    """Closed V1 taxonomy for readable pre-treatment model failures."""

    NO_TOOL_CALL = "NO_TOOL_CALL"
    MULTIPLE_TOOL_CALLS = "MULTIPLE_TOOL_CALLS"
    WRONG_TOOL = "WRONG_TOOL"
    INVALID_TOOL_CALL_TYPE = "INVALID_TOOL_CALL_TYPE"
    MISSING_OR_INVALID_TOOL_CALL_ID = "MISSING_OR_INVALID_TOOL_CALL_ID"
    MALFORMED_ARGUMENT_JSON = "MALFORMED_ARGUMENT_JSON"
    INVALID_ARGUMENT_SHAPE = "INVALID_ARGUMENT_SHAPE"
    TASK_INCORRECT_ARGUMENTS = "TASK_INCORRECT_ARGUMENTS"
    REJECTED_GENERATION = "REJECTED_GENERATION"


@dataclass(frozen=True, slots=True)
class V1CreateTicketTaskSpec:
    """Frozen task text plus the exact CREATE effect required for eligibility."""

    customer_id: str
    expected_title: str
    expected_description: str
    user_task: str

    def __post_init__(self) -> None:
        for name, value in (
            ("customer_id", self.customer_id),
            ("expected_title", self.expected_title),
            ("expected_description", self.expected_description),
        ):
            _validate_v1_scenario_value(name, value)
        if type(self.user_task) is not str:
            raise ModelRequestError("user_task must be a string")
        expected_user_task = _render_validated_v1_create_ticket_task(
            customer_id=self.customer_id,
            expected_title=self.expected_title,
            expected_description=self.expected_description,
        )
        if self.user_task != expected_user_task:
            raise ModelRequestError(
                "user_task must exactly match the frozen V1 task template and "
                "scenario values"
            )

    @property
    def expected_arguments(self) -> CreateTicketArguments:
        return CreateTicketArguments(
            customer_id=self.customer_id,
            title=self.expected_title,
            description=self.expected_description,
        )


def render_v1_create_ticket_task(
    *, customer_id: str, expected_title: str, expected_description: str
) -> str:
    """Render the exact frozen V1 task template without normalizing values."""

    validated_customer_id = _validate_v1_scenario_value(
        "customer_id", customer_id
    )
    validated_title = _validate_v1_scenario_value(
        "expected_title", expected_title
    )
    validated_description = _validate_v1_scenario_value(
        "expected_description", expected_description
    )
    return _render_validated_v1_create_ticket_task(
        customer_id=validated_customer_id,
        expected_title=validated_title,
        expected_description=validated_description,
    )


@dataclass(frozen=True, slots=True)
class EligibleOriginalGeneration:
    """An eligible response frozen at both history and executable boundaries."""

    task_spec: V1CreateTicketTaskSpec
    model_request: ModelRequest
    model_response: ModelResponse
    original_assistant_message: CanonicalContextMessage
    frozen_executable_request: FrozenExecutableRequest

    def __post_init__(self) -> None:
        if type(self.task_spec) is not V1CreateTicketTaskSpec:
            raise ModelResponseError("task_spec has the wrong type")
        if type(self.model_request) is not ModelRequest:
            raise ModelResponseError("model_request has the wrong type")
        if type(self.model_response) is not ModelResponse:
            raise ModelResponseError("model_response has the wrong type")
        if type(self.original_assistant_message) is not CanonicalContextMessage:
            raise ModelResponseError("original_assistant_message has the wrong type")
        if type(self.frozen_executable_request) is not FrozenExecutableRequest:
            raise ModelResponseError("frozen_executable_request has the wrong type")
        if self.model_request.model_config.tool_choice.mode is not ToolChoiceMode.AUTO:
            raise ModelResponseError("eligible V1 request did not use AUTO tool choice")
        if self.model_request.tools is not FROZEN_TOOL_CATALOG:
            raise ModelResponseError(
                "eligible V1 request used a different tool catalog"
            )
        expected_messages = (
            CanonicalContextMessage(
                role="system",
                content=FROZEN_SYSTEM_MESSAGE,
                tool_calls=(),
                tool_call_id=None,
            ),
            CanonicalContextMessage(
                role="user",
                content=self.task_spec.user_task,
                tool_calls=(),
                tool_call_id=None,
            ),
        )
        if self.model_request.messages != expected_messages:
            raise ModelResponseError("eligible V1 request messages are incoherent")
        if self.model_response.requested_model != self.model_request.model_config.model:
            raise ModelResponseError("request and response model provenance disagree")

        response_message = self.model_response.assistant_message
        if len(response_message.tool_calls) != 1:
            raise ModelResponseError(
                "eligible response must contain exactly one tool call"
            )
        response_call = response_message.tool_calls[0]
        parsed_success, parsed_arguments, _ = parse_tool_arguments_json(
            response_call.arguments_json
        )
        if (
            response_call.tool_type != "function"
            or response_call.tool_name != _CREATE_TICKET
            or type(response_call.tool_call_id) is not str
            or response_call.tool_call_id == ""
            or not parsed_success
            or not response_call.parse_success
            or parsed_arguments != response_call.parsed_arguments
            or type(parsed_arguments) is not MappingProxyType
            or set(parsed_arguments) != _CREATE_ARGUMENT_FIELDS
            or any(
                type(parsed_arguments[field]) is not str
                or parsed_arguments[field] == ""
                for field in _CREATE_ARGUMENT_FIELDS
            )
            or CreateTicketArguments(
                customer_id=parsed_arguments["customer_id"],
                title=parsed_arguments["title"],
                description=parsed_arguments["description"],
            )
            != self.task_spec.expected_arguments
        ):
            raise ModelResponseError(
                "eligible response does not satisfy V1 eligibility"
            )
        if len(self.original_assistant_message.tool_calls) != 1:
            raise ModelResponseError(
                "eligible historical assistant message must contain exactly one "
                "tool call"
            )
        historical_call = self.original_assistant_message.tool_calls[0]
        if (
            self.original_assistant_message.role != "assistant"
            or self.original_assistant_message.content != response_message.content
            or self.original_assistant_message.tool_call_id is not None
            or historical_call.tool_call_id != response_call.tool_call_id
            or historical_call.tool != response_call.tool_name
            or historical_call.arguments_json != response_call.arguments_json
            or historical_call.arguments != self.task_spec.expected_arguments
        ):
            raise ModelResponseError(
                "eligible response and historical assistant message are incoherent"
            )
        executable = json.loads(self.frozen_executable_request.serialized_request)
        if executable != {
            "arguments": self.task_spec.expected_arguments.as_dict(),
            "tool": historical_call.tool,
            "tool_call_id": historical_call.tool_call_id,
        }:
            raise ModelResponseError(
                "historical assistant message and executable M are incoherent"
            )

    @property
    def serialized_original_request(self) -> bytes:
        return self.frozen_executable_request.serialized_request

    @property
    def original_request_hash(self) -> str:
        return self.frozen_executable_request.request_hash


@dataclass(frozen=True, slots=True)
class OriginalGenerationBehavioralFailure:
    """Readable model behavior that cannot activate a V1 trial family."""

    task_spec: V1CreateTicketTaskSpec
    model_request: ModelRequest
    reason: OriginalGenerationFailureReason
    model_response: ModelResponse | None
    rejected_generation: ModelRejectedGenerationError | None
    detail: str | None = None

    def __post_init__(self) -> None:
        if type(self.task_spec) is not V1CreateTicketTaskSpec:
            raise ModelResponseError("task_spec has the wrong type")
        if type(self.model_request) is not ModelRequest:
            raise ModelResponseError("model_request has the wrong type")
        if type(self.reason) is not OriginalGenerationFailureReason:
            raise ModelResponseError("behavioral failure reason has the wrong type")
        if self.detail is not None and type(self.detail) is not str:
            raise ModelResponseError(
                "behavioral failure detail must be a string or null"
            )
        if self.reason is OriginalGenerationFailureReason.REJECTED_GENERATION:
            if (
                self.model_response is not None
                or type(self.rejected_generation) is not ModelRejectedGenerationError
            ):
                raise ModelResponseError(
                    "rejected generation must retain only rejected-generation evidence"
                )
        elif (
            type(self.model_response) is not ModelResponse
            or self.rejected_generation is not None
        ):
            raise ModelResponseError(
                "ordinary behavioral failure must retain exactly one model response"
            )


OriginalGenerationAttemptResult: TypeAlias = (
    EligibleOriginalGeneration | OriginalGenerationBehavioralFailure
)


def build_v1_original_generation_request(
    *, task_spec: V1CreateTicketTaskSpec, model_config: ModelCallConfig
) -> ModelRequest:
    """Purely construct the exact stateless V1 original-generation request."""

    if type(task_spec) is not V1CreateTicketTaskSpec:
        raise ModelRequestError("task_spec must be a V1CreateTicketTaskSpec")
    if type(model_config) is not ModelCallConfig:
        raise ModelRequestError("model_config must be a ModelCallConfig")
    if model_config.tool_choice.mode is not ToolChoiceMode.AUTO:
        raise ModelRequestError(
            "V1 original generation requires tool_choice mode AUTO"
        )
    messages = (
        CanonicalContextMessage(
            role="system",
            content=FROZEN_SYSTEM_MESSAGE,
            tool_calls=(),
            tool_call_id=None,
        ),
        CanonicalContextMessage(
            role="user",
            content=task_spec.user_task,
            tool_calls=(),
            tool_call_id=None,
        ),
    )
    return ModelRequest(
        messages=messages,
        tools=FROZEN_TOOL_CATALOG,
        model_config=model_config,
    )


def _failure(
    *,
    task_spec: V1CreateTicketTaskSpec,
    model_request: ModelRequest,
    reason: OriginalGenerationFailureReason,
    model_response: ModelResponse,
    detail: str | None = None,
) -> OriginalGenerationBehavioralFailure:
    return OriginalGenerationBehavioralFailure(
        task_spec=task_spec,
        model_request=model_request,
        reason=reason,
        model_response=model_response,
        rejected_generation=None,
        detail=detail,
    )


def _evaluate_response(
    *,
    task_spec: V1CreateTicketTaskSpec,
    model_request: ModelRequest,
    model_response: ModelResponse,
) -> OriginalGenerationAttemptResult:
    calls = model_response.assistant_message.tool_calls
    if len(calls) == 0:
        return _failure(
            task_spec=task_spec,
            model_request=model_request,
            reason=OriginalGenerationFailureReason.NO_TOOL_CALL,
            model_response=model_response,
        )
    if len(calls) != 1:
        return _failure(
            task_spec=task_spec,
            model_request=model_request,
            reason=OriginalGenerationFailureReason.MULTIPLE_TOOL_CALLS,
            model_response=model_response,
            detail=f"model returned {len(calls)} tool calls",
        )

    call = calls[0]
    if call.tool_type != "function":
        return _failure(
            task_spec=task_spec,
            model_request=model_request,
            reason=OriginalGenerationFailureReason.INVALID_TOOL_CALL_TYPE,
            model_response=model_response,
            detail=f"tool-call type was {call.tool_type!r}",
        )
    if call.tool_name != _CREATE_TICKET:
        return _failure(
            task_spec=task_spec,
            model_request=model_request,
            reason=OriginalGenerationFailureReason.WRONG_TOOL,
            model_response=model_response,
            detail=f"tool name was {call.tool_name!r}",
        )
    if type(call.tool_call_id) is not str or call.tool_call_id == "":
        return _failure(
            task_spec=task_spec,
            model_request=model_request,
            reason=OriginalGenerationFailureReason.MISSING_OR_INVALID_TOOL_CALL_ID,
            model_response=model_response,
        )

    parse_success, parsed_arguments, parse_error = parse_tool_arguments_json(
        call.arguments_json
    )
    if parse_success != call.parse_success or (
        parse_success and parsed_arguments != call.parsed_arguments
    ):
        raise ModelResponseError(
            "captured tool-call parse metadata is incoherent with raw arguments_json"
        )
    if not parse_success:
        return _failure(
            task_spec=task_spec,
            model_request=model_request,
            reason=OriginalGenerationFailureReason.MALFORMED_ARGUMENT_JSON,
            model_response=model_response,
            detail=parse_error,
        )
    if type(parsed_arguments) is not MappingProxyType:
        return _failure(
            task_spec=task_spec,
            model_request=model_request,
            reason=OriginalGenerationFailureReason.INVALID_ARGUMENT_SHAPE,
            model_response=model_response,
            detail="arguments_json must decode to an object",
        )
    if set(parsed_arguments) != _CREATE_ARGUMENT_FIELDS:
        return _failure(
            task_spec=task_spec,
            model_request=model_request,
            reason=OriginalGenerationFailureReason.INVALID_ARGUMENT_SHAPE,
            model_response=model_response,
            detail=(
                "create_ticket fields must be exactly "
                f"{sorted(_CREATE_ARGUMENT_FIELDS)!r}"
            ),
        )
    if any(
        type(parsed_arguments[field]) is not str or parsed_arguments[field] == ""
        for field in _CREATE_ARGUMENT_FIELDS
    ):
        return _failure(
            task_spec=task_spec,
            model_request=model_request,
            reason=OriginalGenerationFailureReason.INVALID_ARGUMENT_SHAPE,
            model_response=model_response,
            detail="create_ticket fields must be non-empty strings",
        )

    arguments = CreateTicketArguments(
        customer_id=parsed_arguments["customer_id"],
        title=parsed_arguments["title"],
        description=parsed_arguments["description"],
    )
    if arguments != task_spec.expected_arguments:
        return _failure(
            task_spec=task_spec,
            model_request=model_request,
            reason=OriginalGenerationFailureReason.TASK_INCORRECT_ARGUMENTS,
            model_response=model_response,
            detail="create_ticket arguments do not exactly match the requested effect",
        )

    original_assistant_message = CanonicalContextMessage(
        role="assistant",
        content=model_response.assistant_message.content,
        tool_calls=(
            CanonicalToolCall(
                tool_call_id=call.tool_call_id,
                tool=call.tool_name,
                arguments_json=call.arguments_json,
                arguments=arguments,
            ),
        ),
        tool_call_id=None,
    )
    frozen_request = FrozenExecutableRequest.from_value(
        {
            "arguments": arguments.as_dict(),
            "tool": call.tool_name,
            "tool_call_id": call.tool_call_id,
        }
    )
    return EligibleOriginalGeneration(
        task_spec=task_spec,
        model_request=model_request,
        model_response=model_response,
        original_assistant_message=original_assistant_message,
        frozen_executable_request=frozen_request,
    )


def run_v1_original_generation_attempt(
    client: ModelClient,
    *,
    task_spec: V1CreateTicketTaskSpec,
    model_config: ModelCallConfig,
) -> OriginalGenerationAttemptResult:
    """Invoke the model once, classify eligibility, freeze M, and stop."""

    model_request = build_v1_original_generation_request(
        task_spec=task_spec,
        model_config=model_config,
    )
    try:
        model_response = client.complete(model_request)
    except ModelRejectedGenerationError as exc:
        return OriginalGenerationBehavioralFailure(
            task_spec=task_spec,
            model_request=model_request,
            reason=OriginalGenerationFailureReason.REJECTED_GENERATION,
            model_response=None,
            rejected_generation=exc,
            detail=str(exc),
        )
    if type(model_response) is not ModelResponse:
        raise ModelResponseError("ModelClient.complete() must return ModelResponse")
    return _evaluate_response(
        task_spec=task_spec,
        model_request=model_request,
        model_response=model_response,
    )


__all__ = [
    "EligibleOriginalGeneration",
    "OriginalGenerationAttemptResult",
    "OriginalGenerationBehavioralFailure",
    "OriginalGenerationFailureReason",
    "V1CreateTicketTaskSpec",
    "build_v1_original_generation_request",
    "render_v1_create_ticket_task",
    "run_v1_original_generation_attempt",
]
