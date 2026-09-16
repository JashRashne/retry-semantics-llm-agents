"""Bounded provider-neutral V1.1 LLM Regeneration policy executor."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from retry_semantics.environments.ticket import (
    EvaluationResult,
    RequestValidationError,
    SourceStage,
    TicketEnvironment,
    evaluate_ticket_state,
)
from retry_semantics.models.base import (
    ModelCallConfig,
    ModelClient,
    ModelProviderError,
    ModelRejectedGenerationError,
    ModelRequest,
    ModelResponse,
    ModelResponseError,
    ModelToolCall,
    model_request_from_regeneration_context,
    parse_tool_arguments_json,
)
from retry_semantics.runtime.regeneration_context import (
    CanonicalContextMessage,
    CanonicalRegenerationContext,
    CreateTicketArguments,
    ModelVisibleToolCall,
)
from retry_semantics.runtime.exact_replay import RecoveryLatency
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

LLM_REGENERATION = "LLM_REGENERATION"
MODEL_STOPPED = "model_stopped"
ACTION_BUDGET_EXCEEDED = "action_budget_exceeded"
INVALID_MODEL_TOOL_CALL = "invalid_model_tool_call"
MODEL_REJECTED_GENERATION = "model_rejected_generation"
INFRASTRUCTURE_FAILURE = "infrastructure_failure"

TOOL_CALL = "TOOL_CALL"
MODEL_STOP = "MODEL_STOP"
INVALID_TOOL_CALL = "INVALID_TOOL_CALL"
BUDGET_REJECTED_TOOL_CALL = "BUDGET_REJECTED_TOOL_CALL"

VALID = "VALID"
INVALID = "INVALID"
NOT_APPLICABLE = "NOT_APPLICABLE"

_CREATE_TICKET = "create_ticket"
_LIST_TICKETS = "list_tickets"
_CREATE_ARGUMENT_FIELDS = frozenset({"customer_id", "title", "description"})
_MAX_TOOL_ACTION_ATTEMPTS = 3
_PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
_IMPLEMENTATION_BUG = "IMPLEMENTATION_BUG"


class RegenerationProtocolError(ValueError):
    """Caller input violates the frozen V1.1 Regeneration boundary."""


@dataclass(frozen=True, slots=True)
class RegenerationModelInvocation:
    """Complete audit evidence for one attempted ``ModelClient.complete`` call."""

    model_call_index: int
    derived_seed: int | None
    model_request: ModelRequest
    model_response: ModelResponse | None
    rejected_generation: ModelRejectedGenerationError | None
    infrastructure_error: Exception | None


@dataclass(frozen=True, slots=True)
class RegenerationAction:
    """One processed model decision or tool request in provider order."""

    action_sequence: int
    action_type: str
    model_call_index: int
    provider_model_request_id: str | None
    assistant_content: str | None
    tool_call: ModelToolCall | None
    serialized_request: bytes | None
    request_hash: str | None
    validation_status: str
    validation_detail: str | None
    executed: bool
    mutating: bool
    committed_effect_event_ids: tuple[str, ...]
    model_visible_observation: str | None


@dataclass(frozen=True, slots=True)
class RegenerationResult:
    """Auditable result of exactly one bounded V1.1 Regeneration arm."""

    arm_id: str
    model_invocations: tuple[RegenerationModelInvocation, ...]
    recovery_actions: tuple[RegenerationAction, ...]
    termination_reason: str
    tool_action_attempt_count: int
    recovery_tool_calls_attempted: int
    recovery_tool_calls_executed: int
    final_state_snapshot: bytes
    final_state_hash: str
    evaluation: EvaluationResult
    latency: RecoveryLatency = field(compare=False)
    policy: str = field(default=LLM_REGENERATION, init=False)

    @property
    def additional_llm_calls(self) -> int:
        return len(self.model_invocations)

    def __post_init__(self) -> None:
        if not 0 <= self.tool_action_attempt_count <= _MAX_TOOL_ACTION_ATTEMPTS:
            raise RegenerationProtocolError("tool-action count is outside V1.1 bounds")
        if not 0 <= self.recovery_tool_calls_attempted <= 4:
            raise RegenerationProtocolError(
                "attempted tool-call count is outside V1.1 bounds"
            )
        if not 0 <= self.recovery_tool_calls_executed <= 3:
            raise RegenerationProtocolError(
                "executed tool-call count is outside V1.1 bounds"
            )
        if self.recovery_tool_calls_executed > self.tool_action_attempt_count:
            raise RegenerationProtocolError(
                "executed tool calls cannot exceed in-budget action attempts"
            )
        if self.tool_action_attempt_count > self.recovery_tool_calls_attempted:
            raise RegenerationProtocolError(
                "in-budget action attempts cannot exceed considered tool requests"
            )
        if len(self.model_invocations) > 4:
            raise RegenerationProtocolError(
                "model invocation count is outside V1.1 bounds"
            )
        if tuple(
            invocation.model_call_index for invocation in self.model_invocations
        ) != tuple(range(len(self.model_invocations))):
            raise RegenerationProtocolError(
                "model-call indexes are not zero-based ordinals"
            )
        if self.final_state_hash != sha256_hex(self.final_state_snapshot):
            raise RegenerationProtocolError("final state snapshot/hash are incoherent")


@dataclass(frozen=True, slots=True)
class _ValidatedRequest:
    serialized_request: bytes
    request_hash: str
    mutating: bool


def _validate_inputs(
    environment: TicketEnvironment,
    context: CanonicalRegenerationContext,
    model_config: ModelCallConfig,
    arm_id: str,
) -> CreateTicketArguments:
    if type(environment) is not TicketEnvironment:
        raise RegenerationProtocolError("environment must be a TicketEnvironment")
    if type(context) is not CanonicalRegenerationContext:
        raise RegenerationProtocolError(
            "context must be a CanonicalRegenerationContext"
        )
    if type(model_config) is not ModelCallConfig:
        raise RegenerationProtocolError("model_config must be a ModelCallConfig")
    if type(arm_id) is not str or arm_id == "":
        raise RegenerationProtocolError("Regeneration requires a non-empty arm_id")
    arguments = context.original_tool_call.arguments
    if type(arguments) is not CreateTicketArguments:
        raise RegenerationProtocolError(
            "canonical context lacks the eligible original CREATE arguments"
        )
    return arguments


def _derived_config(
    base_config: ModelCallConfig, model_call_index: int
) -> ModelCallConfig:
    seed = (
        None
        if base_config.seed is None
        else base_config.seed + model_call_index
    )
    return replace(base_config, seed=seed)


def _assistant_history_message(response: ModelResponse) -> CanonicalContextMessage:
    raw_calls = tuple(
        ModelVisibleToolCall(
            tool_call_id=call.tool_call_id,
            tool=call.tool_name,
            arguments_json=call.arguments_json,
        )
        for call in response.assistant_message.tool_calls
    )
    return CanonicalContextMessage(
        role="assistant",
        content=response.assistant_message.content,
        tool_calls=raw_calls,
        tool_call_id=None,
    )


def _invalid(detail: str) -> tuple[None, str]:
    return None, detail


def _validate_tool_request(
    call: ModelToolCall,
) -> tuple[_ValidatedRequest | None, str | None]:
    """Validate without repairing or serializing an invalid request."""

    if call.tool_type != "function":
        return _invalid("tool-call type must be exactly 'function'")
    if type(call.tool_call_id) is not str or call.tool_call_id == "":
        return _invalid("tool-call ID must be a non-empty string")

    parse_success, parsed_arguments, parse_error = parse_tool_arguments_json(
        call.arguments_json
    )
    if parse_success != call.parse_success or (
        parse_success and parsed_arguments != call.parsed_arguments
    ) or (not parse_success and parse_error != call.parse_error):
        raise ModelResponseError(
            "captured recovery tool-call parse metadata is incoherent",
            failure_category="IMPLEMENTATION_INCOHERENCE",
            failure_stage="RECOVERY_PARSE_METADATA",
        )
    if not parse_success:
        return _invalid(parse_error or "arguments_json is malformed")
    if type(parsed_arguments) is not MappingProxyType:
        return _invalid("arguments_json must decode to an object")

    if call.tool_name == _CREATE_TICKET:
        if set(parsed_arguments) != _CREATE_ARGUMENT_FIELDS:
            return _invalid(
                "create_ticket fields must be exactly customer_id, title, and "
                "description"
            )
        if any(
            type(parsed_arguments[field]) is not str
            or parsed_arguments[field] == ""
            for field in _CREATE_ARGUMENT_FIELDS
        ):
            return _invalid("create_ticket fields must be non-empty strings")
        arguments = {
            "customer_id": parsed_arguments["customer_id"],
            "title": parsed_arguments["title"],
            "description": parsed_arguments["description"],
        }
        mutating = True
    elif call.tool_name == _LIST_TICKETS:
        if len(parsed_arguments) != 0:
            return _invalid("list_tickets arguments must be exactly empty")
        arguments = {}
        mutating = False
    else:
        return _invalid(f"unknown tool: {call.tool_name!r}")

    serialized = canonical_json_bytes(
        {
            "arguments": arguments,
            "tool": call.tool_name,
            "tool_call_id": call.tool_call_id,
        }
    )
    return _ValidatedRequest(
        serialized_request=serialized,
        request_hash=sha256_hex(serialized),
        mutating=mutating,
    ), None


def _finalize(
    *,
    arm_id: str,
    environment: TicketEnvironment,
    intended: CreateTicketArguments,
    invocations: list[RegenerationModelInvocation],
    actions: list[RegenerationAction],
    termination_reason: str,
    tool_action_attempt_count: int,
    recovery_tool_calls_attempted: int,
    recovery_tool_calls_executed: int,
    recovery_started_ns: int,
    recovery_model_ns: int,
    recovery_tool_ns: int,
    infrastructure_exclusion_reason: str | None = None,
) -> RegenerationResult:
    if infrastructure_exclusion_reason not in (
        None,
        _PROVIDER_UNAVAILABLE,
        _IMPLEMENTATION_BUG,
    ):
        raise RegenerationProtocolError(
            "unexpected infrastructure exclusion reason"
        )
    final_snapshot = environment.snapshot_bytes()
    evaluation = evaluate_ticket_state(
        environment.state,
        customer_id=intended.customer_id,
        title=intended.title,
        description=intended.description,
        infrastructure_failure=infrastructure_exclusion_reason is not None,
        infrastructure_failure_reasons=(
            ()
            if infrastructure_exclusion_reason is None
            else (infrastructure_exclusion_reason,)
        ),
    )
    return RegenerationResult(
        arm_id=arm_id,
        model_invocations=tuple(invocations),
        recovery_actions=tuple(actions),
        termination_reason=termination_reason,
        tool_action_attempt_count=tool_action_attempt_count,
        recovery_tool_calls_attempted=recovery_tool_calls_attempted,
        recovery_tool_calls_executed=recovery_tool_calls_executed,
        final_state_snapshot=final_snapshot,
        final_state_hash=sha256_hex(final_snapshot),
        evaluation=evaluation,
        latency=RecoveryLatency(
            recovery_wall_ms=(time.perf_counter_ns() - recovery_started_ns)
            / 1_000_000,
            recovery_model_ms=recovery_model_ns / 1_000_000,
            recovery_tool_ms=recovery_tool_ns / 1_000_000,
        ),
    )


def execute_llm_regeneration(
    environment: TicketEnvironment,
    *,
    context: CanonicalRegenerationContext,
    client: ModelClient,
    model_config: ModelCallConfig,
    arm_id: str,
) -> RegenerationResult:
    """Execute one bounded Regeneration arm against only the supplied state.

    One successful assistant response is appended once, then every processable
    tool request in that response is handled in provider order before another
    model invocation.  No hidden retry, resampling, repair, or verification is
    performed.
    """

    recovery_started_ns = time.perf_counter_ns()
    intended = _validate_inputs(environment, context, model_config, arm_id)
    invocations: list[RegenerationModelInvocation] = []
    actions: list[RegenerationAction] = []
    history = list(context.messages)
    tool_action_attempt_count = 0
    recovery_tool_calls_attempted = 0
    recovery_tool_calls_executed = 0
    recovery_model_ns = 0
    recovery_tool_ns = 0

    def finish(
        termination_reason: str,
        *,
        infrastructure_exclusion_reason: str | None = None,
    ) -> RegenerationResult:
        return _finalize(
            arm_id=arm_id,
            environment=environment,
            intended=intended,
            invocations=invocations,
            actions=actions,
            termination_reason=termination_reason,
            tool_action_attempt_count=tool_action_attempt_count,
            recovery_tool_calls_attempted=recovery_tool_calls_attempted,
            recovery_tool_calls_executed=recovery_tool_calls_executed,
            recovery_started_ns=recovery_started_ns,
            recovery_model_ns=recovery_model_ns,
            recovery_tool_ns=recovery_tool_ns,
            infrastructure_exclusion_reason=infrastructure_exclusion_reason,
        )

    while True:
        model_call_index = len(invocations)
        if model_call_index > 3:
            raise RegenerationProtocolError(
                "V1.1 cannot invoke the model beyond ordinal 3"
            )
        derived_config = _derived_config(model_config, model_call_index)
        request = (
            model_request_from_regeneration_context(context, derived_config)
            if model_call_index == 0
            else ModelRequest(
                messages=tuple(history),
                tools=context.tools,
                model_config=derived_config,
            )
        )

        model_started_ns = time.perf_counter_ns()
        try:
            response = client.complete(request)
        except ModelRejectedGenerationError as exc:
            recovery_model_ns += time.perf_counter_ns() - model_started_ns
            invocations.append(
                RegenerationModelInvocation(
                    model_call_index=model_call_index,
                    derived_seed=derived_config.seed,
                    model_request=request,
                    model_response=None,
                    rejected_generation=exc,
                    infrastructure_error=None,
                )
            )
            return finish(MODEL_REJECTED_GENERATION)
        except ModelProviderError as exc:
            recovery_model_ns += time.perf_counter_ns() - model_started_ns
            invocations.append(
                RegenerationModelInvocation(
                    model_call_index=model_call_index,
                    derived_seed=derived_config.seed,
                    model_request=request,
                    model_response=None,
                    rejected_generation=None,
                    infrastructure_error=exc,
                )
            )
            return finish(
                INFRASTRUCTURE_FAILURE,
                infrastructure_exclusion_reason=_PROVIDER_UNAVAILABLE,
            )

        recovery_model_ns += time.perf_counter_ns() - model_started_ns
        if type(response) is not ModelResponse:
            error = ModelResponseError(
                "ModelClient.complete() must return ModelResponse, got "
                f"{type(response).__name__}",
                failure_category="IMPLEMENTATION_INCOHERENCE",
                failure_stage="MODEL_CLIENT_RETURN_TYPE",
            )
            invocations.append(
                RegenerationModelInvocation(
                    model_call_index=model_call_index,
                    derived_seed=derived_config.seed,
                    model_request=request,
                    model_response=None,
                    rejected_generation=None,
                    infrastructure_error=error,
                )
            )
            return finish(
                INFRASTRUCTURE_FAILURE,
                infrastructure_exclusion_reason=_IMPLEMENTATION_BUG,
            )

        invocations.append(
            RegenerationModelInvocation(
                model_call_index=model_call_index,
                derived_seed=derived_config.seed,
                model_request=request,
                model_response=response,
                rejected_generation=None,
                infrastructure_error=None,
            )
        )
        calls = response.assistant_message.tool_calls
        history.append(_assistant_history_message(response))

        if not calls:
            actions.append(
                RegenerationAction(
                    action_sequence=len(actions) + 1,
                    action_type=MODEL_STOP,
                    model_call_index=model_call_index,
                    provider_model_request_id=response.provider_request_id,
                    assistant_content=response.assistant_message.content,
                    tool_call=None,
                    serialized_request=None,
                    request_hash=None,
                    validation_status=NOT_APPLICABLE,
                    validation_detail=None,
                    executed=False,
                    mutating=False,
                    committed_effect_event_ids=(),
                    model_visible_observation=None,
                )
            )
            return finish(MODEL_STOPPED)

        for call in calls:
            if tool_action_attempt_count == _MAX_TOOL_ACTION_ATTEMPTS:
                recovery_tool_calls_attempted += 1
                actions.append(
                    RegenerationAction(
                        action_sequence=len(actions) + 1,
                        action_type=BUDGET_REJECTED_TOOL_CALL,
                        model_call_index=model_call_index,
                        provider_model_request_id=response.provider_request_id,
                        assistant_content=response.assistant_message.content,
                        tool_call=call,
                        serialized_request=None,
                        request_hash=None,
                        validation_status=NOT_APPLICABLE,
                        validation_detail=None,
                        executed=False,
                        mutating=False,
                        committed_effect_event_ids=(),
                        model_visible_observation=None,
                    )
                )
                return finish(ACTION_BUDGET_EXCEEDED)

            tool_action_attempt_count += 1
            recovery_tool_calls_attempted += 1
            try:
                validated, invalid_detail = _validate_tool_request(call)
            except ModelProviderError as exc:
                # Adapter parse-metadata incoherence is infrastructure failure;
                # it is not reinterpreted as model behavior.
                last = invocations[-1]
                invocations[-1] = replace(last, infrastructure_error=exc)
                return finish(
                    INFRASTRUCTURE_FAILURE,
                    infrastructure_exclusion_reason=_IMPLEMENTATION_BUG,
                )
            if validated is None:
                actions.append(
                    RegenerationAction(
                        action_sequence=len(actions) + 1,
                        action_type=INVALID_TOOL_CALL,
                        model_call_index=model_call_index,
                        provider_model_request_id=response.provider_request_id,
                        assistant_content=response.assistant_message.content,
                        tool_call=call,
                        serialized_request=None,
                        request_hash=None,
                        validation_status=INVALID,
                        validation_detail=invalid_detail,
                        executed=False,
                        mutating=False,
                        committed_effect_event_ids=(),
                        model_visible_observation=None,
                    )
                )
                return finish(INVALID_MODEL_TOOL_CALL)

            events_before = len(environment.state.mutation_events)
            tool_started_ns = time.perf_counter_ns()
            try:
                observation_bytes = environment.execute_request(
                    validated.serialized_request,
                    source_stage=SourceStage.RECOVERY,
                    arm_id=arm_id,
                    expected_request_hash=validated.request_hash,
                )
            except RequestValidationError as exc:
                recovery_tool_ns += time.perf_counter_ns() - tool_started_ns
                last = invocations[-1]
                invocations[-1] = replace(last, infrastructure_error=exc)
                return finish(
                    INFRASTRUCTURE_FAILURE,
                    infrastructure_exclusion_reason=_IMPLEMENTATION_BUG,
                )
            recovery_tool_ns += time.perf_counter_ns() - tool_started_ns
            recovery_tool_calls_executed += 1
            observation = observation_bytes.decode("utf-8")
            new_events = environment.state.mutation_events[events_before:]
            actions.append(
                RegenerationAction(
                    action_sequence=len(actions) + 1,
                    action_type=TOOL_CALL,
                    model_call_index=model_call_index,
                    provider_model_request_id=response.provider_request_id,
                    assistant_content=response.assistant_message.content,
                    tool_call=call,
                    serialized_request=validated.serialized_request,
                    request_hash=validated.request_hash,
                    validation_status=VALID,
                    validation_detail=None,
                    executed=True,
                    mutating=validated.mutating,
                    committed_effect_event_ids=tuple(
                        event.event_id for event in new_events
                    ),
                    model_visible_observation=observation,
                )
            )
            history.append(
                CanonicalContextMessage(
                    role="tool",
                    content=observation,
                    tool_calls=(),
                    tool_call_id=call.tool_call_id,
                )
            )


__all__ = [
    "ACTION_BUDGET_EXCEEDED",
    "BUDGET_REJECTED_TOOL_CALL",
    "INFRASTRUCTURE_FAILURE",
    "INVALID",
    "INVALID_MODEL_TOOL_CALL",
    "INVALID_TOOL_CALL",
    "LLM_REGENERATION",
    "MODEL_REJECTED_GENERATION",
    "MODEL_STOP",
    "MODEL_STOPPED",
    "NOT_APPLICABLE",
    "TOOL_CALL",
    "VALID",
    "RegenerationAction",
    "RegenerationModelInvocation",
    "RegenerationProtocolError",
    "RegenerationResult",
    "execute_llm_regeneration",
]
