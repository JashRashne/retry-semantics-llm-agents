"""Frozen provider-neutral Regeneration context for ``primary-create-v1``.

The canonical bytes in this module represent the experiment's logical
model-visible context.  They are not a provider HTTP request body: model name,
sampling parameters, provider defaults, and transport fields belong to a later
adapter layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from retry_semantics.environments.ticket import FrozenExecutableRequest
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

FROZEN_SYSTEM_MESSAGE = (
    "You are a tool-using assistant. Complete the user's task using the available "
    "tools."
)
CANONICAL_AMBIGUITY_TEXT = (
    "ToolError: The previous request timed out. Its outcome is unknown."
)
_CREATE_ARGUMENT_FIELDS = frozenset({"customer_id", "title", "description"})


class RegenerationContextProtocolError(ValueError):
    """A canonical Regeneration context violates the frozen V1 protocol."""


@dataclass(frozen=True, slots=True)
class FrozenToolDefinition:
    """One immutable V1 tool definition with its exact string parameters."""

    name: str
    description: str
    parameter_names: tuple[str, ...]
    required_parameter_names: tuple[str, ...] | None

    def as_dict(self) -> dict[str, Any]:
        parameters: dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                name: {"type": "string", "minLength": 1}
                for name in self.parameter_names
            },
        }
        if self.required_parameter_names is not None:
            parameters["required"] = list(self.required_parameter_names)
        return {
            "name": self.name,
            "description": self.description,
            "parameters": parameters,
        }


FROZEN_TOOL_CATALOG = (
    FrozenToolDefinition(
        name="create_ticket",
        description="Create one support ticket.",
        parameter_names=("customer_id", "title", "description"),
        required_parameter_names=("customer_id", "title", "description"),
    ),
    FrozenToolDefinition(
        name="list_tickets",
        description="List the support tickets currently present.",
        parameter_names=(),
        required_parameter_names=None,
    ),
)


@dataclass(frozen=True, slots=True)
class CreateTicketArguments:
    """The exact logical arguments copied from the authoritative frozen M."""

    customer_id: str
    title: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {
            "customer_id": self.customer_id,
            "title": self.title,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class CanonicalToolCall:
    """Structured historical representation of the original tool call M."""

    tool_call_id: str
    tool: str
    arguments_json: str
    arguments: CreateTicketArguments

    def as_dict(self) -> dict[str, Any]:
        """Return only fields that are part of model-visible history.

        ``arguments`` is parsed validation metadata. The exact raw
        ``arguments_json`` string is the historical representation a future
        provider adapter must use.
        """

        return {
            "tool_call_id": self.tool_call_id,
            "tool": self.tool,
            "arguments_json": self.arguments_json,
        }


@dataclass(frozen=True, slots=True)
class CanonicalContextMessage:
    """One message in the fixed pre-recovery Regeneration history."""

    role: str
    content: str | None
    tool_calls: tuple[CanonicalToolCall, ...]
    tool_call_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": [tool_call.as_dict() for tool_call in self.tool_calls],
            "tool_call_id": self.tool_call_id,
        }


@dataclass(frozen=True, slots=True)
class CanonicalRegenerationContext:
    """Immutable logical context shown before Regeneration's first decision."""

    messages: tuple[CanonicalContextMessage, ...]
    tools: tuple[FrozenToolDefinition, ...]
    canonical_context_bytes: bytes
    canonical_context_sha256: str

    @property
    def system_message(self) -> CanonicalContextMessage:
        return self.messages[0]

    @property
    def user_message(self) -> CanonicalContextMessage:
        return self.messages[1]

    @property
    def original_assistant_message(self) -> CanonicalContextMessage:
        return self.messages[2]

    @property
    def original_assistant_tool_call(self) -> CanonicalContextMessage:
        return self.messages[2]

    @property
    def ambiguity_tool_message(self) -> CanonicalContextMessage:
        return self.messages[3]

    @property
    def original_tool_call(self) -> CanonicalToolCall:
        return self.messages[2].tool_calls[0]

    def as_dict(self) -> dict[str, Any]:
        """Return a fresh logical value; mutating it cannot mutate this context."""

        return {
            "messages": [message.as_dict() for message in self.messages],
            "tools": [tool.as_dict() for tool in self.tools],
        }


def _fail(message: str) -> None:
    raise RegenerationContextProtocolError(message)


def _frozen_m_identity(
    frozen_original_request: FrozenExecutableRequest,
) -> tuple[str, str, CreateTicketArguments]:
    if type(frozen_original_request) is not FrozenExecutableRequest:
        _fail("frozen_original_request must be a FrozenExecutableRequest")
    try:
        request = json.loads(frozen_original_request.serialized_request)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegenerationContextProtocolError(
            f"frozen original request M is not valid JSON: {exc}"
        ) from exc
    if request["tool"] != "create_ticket":
        _fail("original request M must be an eligible create_ticket request")
    arguments = request["arguments"]
    return (
        request["tool_call_id"],
        request["tool"],
        CreateTicketArguments(
            customer_id=arguments["customer_id"],
            title=arguments["title"],
            description=arguments["description"],
        ),
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r}")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key {key!r}")
        value[key] = item
    return value


def _parse_arguments_json(arguments_json: str) -> CreateTicketArguments:
    if type(arguments_json) is not str:
        _fail("original assistant tool-call arguments_json must be a string")
    try:
        decoded = json.loads(
            arguments_json,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise RegenerationContextProtocolError(
            f"original assistant tool-call arguments_json is invalid JSON: {exc}"
        ) from exc
    if type(decoded) is not dict:
        _fail("original assistant tool-call arguments_json must decode to an object")
    if set(decoded) != _CREATE_ARGUMENT_FIELDS:
        _fail(
            "original assistant tool-call arguments_json fields must be exactly "
            f"{sorted(_CREATE_ARGUMENT_FIELDS)!r}"
        )
    for field in sorted(_CREATE_ARGUMENT_FIELDS):
        if type(decoded[field]) is not str or decoded[field] == "":
            _fail(
                "original assistant tool-call arguments_json fields must be "
                "non-empty strings"
            )
    return CreateTicketArguments(
        customer_id=decoded["customer_id"],
        title=decoded["title"],
        description=decoded["description"],
    )


def _validate_original_assistant_message(
    original_assistant_message: CanonicalContextMessage,
    *,
    frozen_m_identity: tuple[str, str, CreateTicketArguments],
) -> CanonicalToolCall:
    if type(original_assistant_message) is not CanonicalContextMessage:
        _fail("original_assistant_message must be a CanonicalContextMessage")
    if original_assistant_message.role != "assistant":
        _fail("original assistant message must have role='assistant'")
    if not (
        original_assistant_message.content is None
        or type(original_assistant_message.content) is str
    ):
        _fail("original assistant message content must be a string or null")
    if original_assistant_message.tool_call_id is not None:
        _fail("original assistant message must not have a message-level tool_call_id")
    if type(original_assistant_message.tool_calls) is not tuple:
        _fail("original assistant message tool_calls must be an immutable tuple")
    if len(original_assistant_message.tool_calls) != 1:
        _fail("original assistant message must contain exactly one V1 tool call")
    supplied_call = original_assistant_message.tool_calls[0]
    if type(supplied_call) is not CanonicalToolCall:
        _fail("original assistant message contains an unexpected tool-call type")
    parsed_raw_arguments = _parse_arguments_json(supplied_call.arguments_json)
    if type(supplied_call.arguments) is not CreateTicketArguments:
        _fail("original assistant tool-call parsed arguments have the wrong type")
    if parsed_raw_arguments != supplied_call.arguments:
        _fail(
            "original assistant tool-call arguments_json does not match stored "
            "parsed arguments"
        )
    frozen_tool_call_id, frozen_tool, frozen_arguments = frozen_m_identity
    if supplied_call.arguments != frozen_arguments:
        _fail("original assistant message arguments do not match frozen M")
    if supplied_call.tool != frozen_tool:
        _fail("original assistant message tool name does not match frozen M")
    if supplied_call.tool_call_id != frozen_tool_call_id:
        _fail("original assistant message tool-call ID does not match frozen M")
    return supplied_call


def _expected_messages(
    user_task: str,
    original_assistant_message: CanonicalContextMessage,
    original_tool_call_id: str,
) -> tuple[CanonicalContextMessage, ...]:
    return (
        CanonicalContextMessage(
            role="system",
            content=FROZEN_SYSTEM_MESSAGE,
            tool_calls=(),
            tool_call_id=None,
        ),
        CanonicalContextMessage(
            role="user",
            content=user_task,
            tool_calls=(),
            tool_call_id=None,
        ),
        original_assistant_message,
        CanonicalContextMessage(
            role="tool",
            content=CANONICAL_AMBIGUITY_TEXT,
            tool_calls=(),
            tool_call_id=original_tool_call_id,
        ),
    )


def build_canonical_regeneration_context(
    *,
    user_task: str,
    frozen_original_request: FrozenExecutableRequest,
    original_assistant_message: CanonicalContextMessage,
) -> CanonicalRegenerationContext:
    """Purely build the frozen pre-recovery context from model-visible artifacts.

    Hidden-world state and environment objects are intentionally absent from
    this boundary.  The supplied user task is copied without whitespace or
    Unicode normalization.  The executable M is parsed only to validate the
    already-frozen assistant message, which is inserted unchanged; neither its
    content nor its structured tool call is reconstructed or normalized.
    """

    if type(user_task) is not str or user_task == "":
        _fail("user_task must be a non-empty string")
    frozen_identity = _frozen_m_identity(frozen_original_request)
    original_tool_call = _validate_original_assistant_message(
        original_assistant_message,
        frozen_m_identity=frozen_identity,
    )
    messages = _expected_messages(
        user_task,
        original_assistant_message,
        original_tool_call.tool_call_id,
    )
    logical_context = {
        "messages": [message.as_dict() for message in messages],
        "tools": [tool.as_dict() for tool in FROZEN_TOOL_CATALOG],
    }
    context_bytes = canonical_json_bytes(logical_context)
    context = CanonicalRegenerationContext(
        messages=messages,
        tools=FROZEN_TOOL_CATALOG,
        canonical_context_bytes=context_bytes,
        canonical_context_sha256=sha256_hex(context_bytes),
    )
    validate_regeneration_context(
        context,
        frozen_original_request=frozen_original_request,
        original_assistant_message=original_assistant_message,
    )
    return context


def validate_regeneration_context(
    context: CanonicalRegenerationContext,
    *,
    frozen_original_request: FrozenExecutableRequest,
    original_assistant_message: CanonicalContextMessage,
) -> None:
    """Validate a context without repairing, executing, or inspecting state."""

    if type(context) is not CanonicalRegenerationContext:
        _fail("context must be a CanonicalRegenerationContext")
    if type(context.messages) is not tuple or len(context.messages) != 4:
        _fail("Regeneration context must contain exactly four messages")
    if any(
        type(message) is not CanonicalContextMessage for message in context.messages
    ):
        _fail("Regeneration context contains an unexpected message type")
    if type(context.tools) is not tuple or any(
        type(tool) is not FrozenToolDefinition for tool in context.tools
    ):
        _fail("Regeneration context contains an unexpected tool-definition type")
    if context.tools != FROZEN_TOOL_CATALOG:
        _fail("Regeneration tool catalog differs from the frozen V1 catalog")

    frozen_identity = _frozen_m_identity(frozen_original_request)
    original_tool_call = _validate_original_assistant_message(
        original_assistant_message,
        frozen_m_identity=frozen_identity,
    )
    user_task = context.messages[1].content
    if type(user_task) is not str or user_task == "":
        _fail("Regeneration user message must preserve a non-empty task string")
    expected_messages = _expected_messages(
        user_task,
        original_assistant_message,
        original_tool_call.tool_call_id,
    )
    if context.messages != expected_messages:
        _fail(
            "Regeneration messages differ from the frozen order, content, "
            "tool-call identity, or ambiguity linkage"
        )

    if type(context.canonical_context_bytes) is not bytes:
        _fail("canonical_context_bytes must be bytes")
    expected_bytes = canonical_json_bytes(context.as_dict())
    if context.canonical_context_bytes != expected_bytes:
        _fail("canonical context bytes do not match the logical context")
    if type(context.canonical_context_sha256) is not str:
        _fail("canonical_context_sha256 must be a string")
    expected_hash = sha256_hex(context.canonical_context_bytes)
    if context.canonical_context_sha256 != expected_hash:
        _fail("canonical context hash does not match canonical context bytes")


__all__ = [
    "CANONICAL_AMBIGUITY_TEXT",
    "FROZEN_SYSTEM_MESSAGE",
    "FROZEN_TOOL_CATALOG",
    "CanonicalContextMessage",
    "CanonicalRegenerationContext",
    "CanonicalToolCall",
    "CreateTicketArguments",
    "FrozenToolDefinition",
    "RegenerationContextProtocolError",
    "build_canonical_regeneration_context",
    "validate_regeneration_context",
]
