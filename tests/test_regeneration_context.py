from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from retry_semantics.environments.ticket import SourceStage, TicketEnvironment
from retry_semantics.runtime.hidden_worlds import construct_trial_family_states
from retry_semantics.runtime.regeneration_context import (
    CANONICAL_AMBIGUITY_TEXT,
    FROZEN_SYSTEM_MESSAGE,
    FROZEN_TOOL_CATALOG,
    CanonicalContextMessage,
    CanonicalToolCall,
    CreateTicketArguments,
    RegenerationContextProtocolError,
    build_canonical_regeneration_context,
    validate_regeneration_context,
)
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

USER_TASK = (
    'Create exactly one support ticket for customer "CUST-001" with title '
    '"Login page timeout" and description '
    '"The login page times out after 30 seconds.".'
)


def _construct_family(request):
    return construct_trial_family_states(
        initial_state=TicketEnvironment.empty(),
        frozen_original_request=request,
        serialized_original_request=request.serialized_request,
        original_request_hash=request.request_hash,
        original_source_stage=SourceStage.ORIGINAL,
        original_arm_id=None,
    )


def _assistant_message(
    request,
    *,
    content: str | None = None,
    role: str = "assistant",
    message_tool_call_id: str | None = None,
    tool_calls: tuple[CanonicalToolCall, ...] | None = None,
) -> CanonicalContextMessage:
    request_value = json.loads(request.serialized_request)
    arguments = request_value["arguments"]
    original_call = CanonicalToolCall(
        tool_call_id=request_value["tool_call_id"],
        tool=request_value["tool"],
        arguments=CreateTicketArguments(
            customer_id=arguments["customer_id"],
            title=arguments["title"],
            description=arguments["description"],
        ),
    )
    return CanonicalContextMessage(
        role=role,
        content=content,
        tool_calls=(original_call,) if tool_calls is None else tool_calls,
        tool_call_id=message_tool_call_id,
    )


def _build(
    request,
    user_task: str = USER_TASK,
    original_assistant_message: CanonicalContextMessage | None = None,
):
    if original_assistant_message is None:
        original_assistant_message = _assistant_message(request)
    return build_canonical_regeneration_context(
        user_task=user_task,
        frozen_original_request=request,
        original_assistant_message=original_assistant_message,
    )


def test_canonical_ambiguity_has_exact_text_and_66_utf8_bytes() -> None:
    expected = (
        b"ToolError: The previous request timed out. Its outcome is unknown."
    )

    assert CANONICAL_AMBIGUITY_TEXT == expected.decode("utf-8")
    assert CANONICAL_AMBIGUITY_TEXT.encode("utf-8") == expected
    assert len(CANONICAL_AMBIGUITY_TEXT.encode("utf-8")) == 66


def test_system_prompt_is_exact_and_has_no_recovery_instruction(make_request) -> None:
    context = _build(make_request())

    assert FROZEN_SYSTEM_MESSAGE == (
        "You are a tool-using assistant. Complete the user's task using the "
        "available tools."
    )
    assert context.system_message.content == FROZEN_SYSTEM_MESSAGE
    assert context.system_message.content.encode("utf-8") == (
        b"You are a tool-using assistant. Complete the user's task using the "
        b"available tools."
    )


def test_message_order_and_fields_are_exact(make_request) -> None:
    request = make_request()
    original_assistant_message = _assistant_message(request)
    context = _build(request, original_assistant_message=original_assistant_message)

    assert [message.role for message in context.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]
    assert context.system_message.tool_calls == ()
    assert context.system_message.tool_call_id is None
    assert context.user_message.content == USER_TASK
    assert context.user_message.tool_calls == ()
    assert context.user_message.tool_call_id is None
    assert context.original_assistant_message is original_assistant_message
    assert context.original_assistant_message.content is None
    assert len(context.original_assistant_message.tool_calls) == 1
    assert context.original_assistant_message.tool_call_id is None
    assert context.ambiguity_tool_message.tool_calls == ()

    serialized = json.loads(context.canonical_context_bytes)
    assert set(serialized) == {"messages", "tools"}
    assert all(
        set(message) == {"role", "content", "tool_calls", "tool_call_id"}
        for message in serialized["messages"]
    )


@pytest.mark.parametrize(
    "assistant_content",
    [
        "I'll create the ticket.",
        "",
        None,
        "  Cr\N{LATIN SMALL LETTER E WITH ACUTE}er le ticket.\n  ",
    ],
)
def test_supplied_original_assistant_content_is_preserved_exactly(
    make_request,
    assistant_content,
) -> None:
    request = make_request()
    original_assistant_message = _assistant_message(
        request,
        content=assistant_content,
    )

    context = _build(
        request,
        original_assistant_message=original_assistant_message,
    )

    assert context.original_assistant_message is original_assistant_message
    assert context.original_assistant_message.content == assistant_content
    serialized_message = json.loads(context.canonical_context_bytes)["messages"][2]
    assert serialized_message["content"] == assistant_content


def test_tool_catalog_is_exactly_the_two_protocol_definitions(make_request) -> None:
    context = _build(make_request())

    assert context.tools is FROZEN_TOOL_CATALOG
    assert [tool.name for tool in context.tools] == [
        "create_ticket",
        "list_tickets",
    ]
    assert [tool.as_dict() for tool in context.tools] == [
        {
            "name": "create_ticket",
            "description": "Create one support ticket.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["customer_id", "title", "description"],
                "properties": {
                    "customer_id": {"type": "string", "minLength": 1},
                    "title": {"type": "string", "minLength": 1},
                    "description": {"type": "string", "minLength": 1},
                },
            },
        },
        {
            "name": "list_tickets",
            "description": "List the support tickets currently present.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
        },
    ]


def test_h0_h1_context_bytes_and_hashes_match_while_hidden_states_differ(
    make_request,
) -> None:
    request = make_request(tool_call_id="provider-original-call")
    family = _construct_family(request)
    h0_request = (
        family.not_executed.arm_states.llm_regeneration_state
        .frozen_original_request
    )
    h1_request = (
        family.executed_ack_lost.arm_states.llm_regeneration_state
        .frozen_original_request
    )
    original_assistant_message = _assistant_message(
        request,
        content="I'll create the ticket.",
    )

    h0_context = _build(
        h0_request,
        original_assistant_message=original_assistant_message,
    )
    h1_context = _build(
        h1_request,
        original_assistant_message=original_assistant_message,
    )

    assert (
        family.not_executed.post_ambiguity_state_hash
        != family.executed_ack_lost.post_ambiguity_state_hash
    )
    assert (
        family.not_executed.post_ambiguity_snapshot
        != family.executed_ack_lost.post_ambiguity_snapshot
    )
    assert h0_context.canonical_context_bytes == h1_context.canonical_context_bytes
    assert h0_context.canonical_context_sha256 == h1_context.canonical_context_sha256
    assert h0_context.original_assistant_message is original_assistant_message
    assert h1_context.original_assistant_message is original_assistant_message


def test_context_contains_no_hidden_evaluator_or_timing_data(make_request) -> None:
    family = _construct_family(make_request())
    context = _build(family.frozen_original_request)
    serialized = context.canonical_context_bytes
    logical_context = json.loads(serialized)

    forbidden_exact_keys = {
        "ticket_id",
        "mutation_events",
        "event_id",
        "next_ticket_id",
        "dispatch_count",
        "original_request_executed",
        "timestamp",
        "latency",
        "duration",
        "dispatch_time",
        "elapsed",
        "temperature",
        "seed",
        "top_p",
        "max_tokens",
        "max_output_tokens",
        "model",
        "provider",
    }

    def all_keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from all_keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from all_keys(child)

    present_keys = set(all_keys(logical_context))
    assert forbidden_exact_keys.isdisjoint(present_keys)
    for forbidden_value in (
        "NOT_EXECUTED",
        "EXECUTED_ACK_LOST",
        "CORRECT",
        "DUPLICATE_EFFECT",
        family.initial_state_hash,
        family.not_executed.post_ambiguity_state_hash,
        family.executed_ack_lost.post_ambiguity_state_hash,
    ):
        assert forbidden_value.encode("utf-8") not in serialized


def test_h1_success_acknowledgement_is_absent_and_only_ambiguity_is_visible(
    make_request,
) -> None:
    family = _construct_family(make_request())
    h1_context = _build(
        family.executed_ack_lost.arm_states.llm_regeneration_state
        .frozen_original_request
    )

    assert h1_context.ambiguity_tool_message.content == CANONICAL_AMBIGUITY_TEXT
    assert all(
        message.content != '{"status":"created"}'
        for message in h1_context.messages
    )
    assert b'\\"status\\":\\"created\\"' not in h1_context.canonical_context_bytes


def test_original_tool_call_identity_arguments_and_ambiguity_link_are_preserved(
    make_request,
) -> None:
    request = make_request(
        tool_call_id="call-original-987",
        customer_id="CUST-008",
        title="  Exact spacing  ",
        description="Unicode stays composed: caf\N{LATIN SMALL LETTER E WITH ACUTE}",
    )
    context = _build(request)
    call = context.original_tool_call
    executable_m = json.loads(request.serialized_request)

    assert call.tool == "create_ticket" == executable_m["tool"]
    assert call.tool_call_id == "call-original-987" == executable_m["tool_call_id"]
    assert call.arguments.as_dict() == executable_m["arguments"]
    assert context.ambiguity_tool_message.tool_call_id == call.tool_call_id


def test_user_task_is_preserved_without_whitespace_or_unicode_normalization(
    make_request,
) -> None:
    user_task = "  Create caf\N{LATIN SMALL LETTER E WITH ACUTE}\nexactly once.  "
    context = _build(make_request(), user_task)

    assert context.user_message.content == user_task
    assert context.user_message.content.encode("utf-8") == user_task.encode("utf-8")


def test_context_construction_causes_no_dispatch_or_state_mutation(
    make_request,
) -> None:
    family = _construct_family(make_request())
    arm_environments = (
        family.not_executed.arm_states.exact_replay_state.environment,
        family.not_executed.arm_states.llm_regeneration_state.environment,
        family.executed_ack_lost.arm_states.exact_replay_state.environment,
        family.executed_ack_lost.arm_states.llm_regeneration_state.environment,
    )
    snapshots_before = tuple(env.snapshot_bytes() for env in arm_environments)
    dispatches_before = tuple(env.dispatch_count for env in arm_environments)

    _build(family.frozen_original_request)
    _build(family.frozen_original_request)

    assert tuple(env.snapshot_bytes() for env in arm_environments) == snapshots_before
    assert tuple(env.dispatch_count for env in arm_environments) == dispatches_before
    assert tuple(len(env.state.mutation_events) for env in arm_environments) == (
        0,
        0,
        1,
        1,
    )


def test_builder_is_deterministic_and_hash_commits_to_logical_context(
    make_request,
) -> None:
    request = make_request()
    original_assistant_message = _assistant_message(
        request,
        content="  Stored assistant text.  ",
    )
    first = _build(
        request,
        original_assistant_message=original_assistant_message,
    )
    second = _build(
        request,
        original_assistant_message=original_assistant_message,
    )

    assert first == second
    assert first.original_assistant_message is original_assistant_message
    assert second.original_assistant_message is original_assistant_message
    assert first.canonical_context_bytes == canonical_json_bytes(first.as_dict())
    assert first.canonical_context_sha256 == sha256_hex(
        first.canonical_context_bytes
    )


def test_returned_logical_dict_cannot_mutate_immutable_context(make_request) -> None:
    context = _build(make_request())
    value = context.as_dict()
    value["messages"][0]["content"] = "tampered"
    value["tools"][0]["description"] = "tampered"

    assert context.system_message.content == FROZEN_SYSTEM_MESSAGE
    assert context.tools == FROZEN_TOOL_CATALOG
    with pytest.raises(FrozenInstanceError):
        context.canonical_context_sha256 = "0" * 64  # type: ignore[misc]


def test_assistant_message_and_m_call_id_mismatch_fails_without_repair(
    make_request,
) -> None:
    request = make_request(tool_call_id="frozen-call")
    assistant_message = _assistant_message(request, content="Keep this content.")
    wrong_call = replace(
        assistant_message.tool_calls[0],
        tool_call_id="different-call",
    )
    incoherent = replace(assistant_message, tool_calls=(wrong_call,))

    with pytest.raises(RegenerationContextProtocolError, match="tool-call ID"):
        _build(request, original_assistant_message=incoherent)
    assert incoherent.content == "Keep this content."
    assert incoherent.tool_calls[0].tool_call_id == "different-call"


def test_assistant_message_and_m_arguments_mismatch_fails_without_repair(
    make_request,
) -> None:
    request = make_request(title="Frozen title")
    assistant_message = _assistant_message(request)
    wrong_arguments = replace(
        assistant_message.tool_calls[0].arguments,
        title="Different title",
    )
    wrong_call = replace(
        assistant_message.tool_calls[0],
        arguments=wrong_arguments,
    )
    incoherent = replace(assistant_message, tool_calls=(wrong_call,))

    with pytest.raises(RegenerationContextProtocolError, match="arguments"):
        _build(request, original_assistant_message=incoherent)
    assert incoherent.tool_calls[0].arguments.title == "Different title"


def test_assistant_message_and_m_tool_name_mismatch_fails_without_repair(
    make_request,
) -> None:
    request = make_request()
    assistant_message = _assistant_message(request)
    wrong_call = replace(
        assistant_message.tool_calls[0],
        tool="list_tickets",
    )
    incoherent = replace(assistant_message, tool_calls=(wrong_call,))

    with pytest.raises(RegenerationContextProtocolError, match="tool name"):
        _build(request, original_assistant_message=incoherent)
    assert incoherent.tool_calls[0].tool == "list_tickets"


def test_original_assistant_message_wrong_role_fails(make_request) -> None:
    request = make_request()
    wrong_role = _assistant_message(request, role="user")

    with pytest.raises(RegenerationContextProtocolError, match="role='assistant'"):
        _build(request, original_assistant_message=wrong_role)


def test_original_assistant_message_multiple_tool_calls_fail(make_request) -> None:
    request = make_request()
    valid = _assistant_message(request)
    multiple = replace(
        valid,
        tool_calls=(valid.tool_calls[0], valid.tool_calls[0]),
    )

    with pytest.raises(RegenerationContextProtocolError, match="exactly one"):
        _build(request, original_assistant_message=multiple)


def test_original_assistant_message_level_tool_call_id_fails(make_request) -> None:
    request = make_request()
    invalid = _assistant_message(
        request,
        message_tool_call_id="not-valid-on-assistant-message",
    )

    with pytest.raises(RegenerationContextProtocolError, match="message-level"):
        _build(request, original_assistant_message=invalid)


def test_tampered_ambiguity_fails_validation(make_request) -> None:
    request = make_request()
    original_assistant_message = _assistant_message(request)
    context = _build(request, original_assistant_message=original_assistant_message)
    messages = list(context.messages)
    messages[3] = replace(messages[3], content=CANONICAL_AMBIGUITY_TEXT + " ")
    tampered = replace(context, messages=tuple(messages))

    with pytest.raises(RegenerationContextProtocolError, match="messages differ"):
        validate_regeneration_context(
            tampered,
            frozen_original_request=request,
            original_assistant_message=original_assistant_message,
        )


def test_tampered_tool_call_id_fails_validation(make_request) -> None:
    request = make_request(tool_call_id="original-call")
    original_assistant_message = _assistant_message(request)
    context = _build(request, original_assistant_message=original_assistant_message)
    messages = list(context.messages)
    wrong_call = replace(context.original_tool_call, tool_call_id="new-call")
    messages[2] = replace(messages[2], tool_calls=(wrong_call,))
    tampered = replace(context, messages=tuple(messages))

    with pytest.raises(RegenerationContextProtocolError, match="messages differ"):
        validate_regeneration_context(
            tampered,
            frozen_original_request=request,
            original_assistant_message=original_assistant_message,
        )


def test_tampered_tool_schema_fails_validation(make_request) -> None:
    request = make_request()
    original_assistant_message = _assistant_message(request)
    context = _build(request, original_assistant_message=original_assistant_message)
    wrong_create = replace(
        context.tools[0],
        parameter_names=("customer_id", "title"),
        required_parameter_names=("customer_id", "title"),
    )
    tampered = replace(context, tools=(wrong_create, context.tools[1]))

    with pytest.raises(RegenerationContextProtocolError, match="tool catalog"):
        validate_regeneration_context(
            tampered,
            frozen_original_request=request,
            original_assistant_message=original_assistant_message,
        )


def test_extra_message_fails_validation(make_request) -> None:
    request = make_request()
    original_assistant_message = _assistant_message(request)
    context = _build(request, original_assistant_message=original_assistant_message)
    extra = CanonicalContextMessage(
        role="assistant",
        content="Please retry.",
        tool_calls=(),
        tool_call_id=None,
    )
    tampered = replace(context, messages=context.messages + (extra,))

    with pytest.raises(RegenerationContextProtocolError, match="exactly four"):
        validate_regeneration_context(
            tampered,
            frozen_original_request=request,
            original_assistant_message=original_assistant_message,
        )


def test_tampered_canonical_bytes_or_hash_fails_validation(make_request) -> None:
    request = make_request()
    original_assistant_message = _assistant_message(request)
    context = _build(request, original_assistant_message=original_assistant_message)

    with pytest.raises(RegenerationContextProtocolError, match="bytes do not match"):
        validate_regeneration_context(
            replace(context, canonical_context_bytes=b"{}"),
            frozen_original_request=request,
            original_assistant_message=original_assistant_message,
        )
    with pytest.raises(RegenerationContextProtocolError, match="hash does not match"):
        validate_regeneration_context(
            replace(context, canonical_context_sha256="0" * 64),
            frozen_original_request=request,
            original_assistant_message=original_assistant_message,
        )


def test_different_frozen_m_fails_context_coherence_validation(make_request) -> None:
    original = make_request(tool_call_id="call-a", title="A")
    different = make_request(tool_call_id="call-b", title="B")
    original_assistant_message = _assistant_message(original)
    context = _build(
        original,
        original_assistant_message=original_assistant_message,
    )

    with pytest.raises(
        RegenerationContextProtocolError,
        match="does not match frozen M",
    ):
        validate_regeneration_context(
            context,
            frozen_original_request=different,
            original_assistant_message=original_assistant_message,
        )


def test_builder_has_no_hidden_world_environment_or_provider_boundary() -> None:
    signature = inspect.signature(build_canonical_regeneration_context)
    assert set(signature.parameters) == {
        "user_task",
        "frozen_original_request",
        "original_assistant_message",
    }
    assert "hidden_world" not in signature.parameters
    assert "environment" not in signature.parameters

    module_path = inspect.getsourcefile(build_canonical_regeneration_context)
    assert module_path is not None
    module_source = Path(module_path).read_text(encoding="utf-8").lower()
    for provider_dependency in ("import groq", "import openai", "import ollama"):
        assert provider_dependency not in module_source
