"""Pure mapping from immutable V1.2 execution evidence to arm traces."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import jsonschema

from retry_semantics.environments.ticket import (
    EvaluationResult,
    TicketEnvironment,
    evaluate_ticket_state,
)
from retry_semantics.experiment.manifest import (
    EXPERIMENT_VERSION,
    EngineeringManifestEntry,
)
from retry_semantics.models.base import (
    ModelCallConfig,
    ModelRejectedGenerationError,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
    thaw_json_value,
)
from retry_semantics.runtime.exact_replay import EXACT_REPLAY, ExactReplayResult
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.runtime.regeneration import (
    ACTION_BUDGET_EXCEEDED,
    BUDGET_REJECTED_TOOL_CALL,
    INVALID_MODEL_TOOL_CALL,
    LLM_REGENERATION,
    MODEL_STOP,
    RegenerationAction,
    RegenerationResult,
)
from retry_semantics.runtime.scheduled_trial import EligibleMatchedTrialResult

TRACE_SCHEMA_VERSION = "trace-schema-v1"
ENVIRONMENT_VERSION = "ticket-env-v1"
_GIT_COMMIT = re.compile(r"[0-9a-f]{40,64}").fullmatch
_RFC3339_DATE_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})"
).fullmatch


class TraceSerializationError(ValueError):
    """Immutable execution evidence cannot form a truthful V1 arm trace."""


def is_trace_datetime(value: object) -> bool:
    """Return whether a value is an RFC 3339 JSON Schema date-time string."""

    return (
        type(value) is str
        and _RFC3339_DATE_TIME(value) is not None
        and jsonschema.FormatChecker().conforms(value, "date-time")
    )


@dataclass(frozen=True, slots=True)
class TraceRunMetadata:
    """Run-wide non-treatment metadata required by the frozen trace schema."""

    git_commit: str
    timestamp: str

    def __post_init__(self) -> None:
        if type(self.git_commit) is not str or _GIT_COMMIT(self.git_commit) is None:
            raise TraceSerializationError(
                "git_commit must be a lowercase 40-64 character hex digest"
            )
        if not is_trace_datetime(self.timestamp):
            raise TraceSerializationError(
                "timestamp must be a JSON Schema date-time value"
            )


def _state(snapshot: bytes) -> dict[str, Any]:
    try:
        environment = TicketEnvironment.clone_from_snapshot(snapshot)
    except (TypeError, ValueError) as exc:
        raise TraceSerializationError(f"invalid immutable state snapshot: {exc}") from exc
    return environment.state.as_dict()


def _model_config(config: ModelCallConfig) -> dict[str, Any]:
    return {
        "model": config.model,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "seed": config.seed,
        "max_completion_tokens": config.max_completion_tokens,
        "tool_choice": {
            "mode": config.tool_choice.mode.value,
            "function_name": config.tool_choice.function_name,
        },
        "parallel_tool_calls": config.parallel_tool_calls,
        "provider_parameters": thaw_json_value(config.provider_parameters),
    }


def _model_request(request: ModelRequest) -> dict[str, Any]:
    return {
        "messages": [message.as_dict() for message in request.messages],
        "tools": [tool.as_dict() for tool in request.tools],
        "model_config": _model_config(request.model_config),
    }


def _tool_call_raw(call: ModelToolCall) -> dict[str, Any]:
    return {
        "tool_call_id": thaw_json_value(call.tool_call_id),
        "tool_name": call.tool_name,
        "arguments_json": call.arguments_json,
        "parse_success": call.parse_success,
        "parsed_arguments": (
            None
            if call.parsed_arguments is None
            else thaw_json_value(call.parsed_arguments)
        ),
        "parse_error": call.parse_error,
        "tool_type": call.tool_type,
    }


def _model_response(response: ModelResponse) -> dict[str, Any]:
    usage = response.usage
    return {
        "assistant_message": {
            "role": response.assistant_message.role,
            "content": response.assistant_message.content,
            "tool_calls": [
                _tool_call_raw(call)
                for call in response.assistant_message.tool_calls
            ],
        },
        "finish_reason": response.finish_reason,
        "provider": response.provider,
        "requested_model": response.requested_model,
        "returned_model": response.returned_model,
        "usage": (
            None
            if usage is None
            else {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
        ),
        "system_fingerprint": response.system_fingerprint,
        "provider_request_id": response.provider_request_id,
    }


def rejected_generation_as_json(
    rejected: ModelRejectedGenerationError,
    *,
    model_call_index: int,
    derived_seed: int | None,
) -> dict[str, Any]:
    """Map readable rejected-generation evidence without parsing or repair."""

    return {
        "provider": rejected.provider,
        "provider_error_code": rejected.provider_error_code,
        "failed_generation": thaw_json_value(rejected.failed_generation),
        "provider_request_id": rejected.provider_request_id,
        "model_call_index": model_call_index,
        "derived_seed": derived_seed,
    }


def model_response_as_json(response: ModelResponse) -> dict[str, Any]:
    """Expose a deterministic raw provider-response mapping for ledger evidence."""

    return _model_response(response)


def model_request_as_json(request: ModelRequest) -> dict[str, Any]:
    """Expose a deterministic request mapping for ledger evidence."""

    return _model_request(request)


def _token_usage(response: ModelResponse | None) -> dict[str, int | None]:
    if response is None or response.usage is None:
        return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    return {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }


def _summed_recovery_usage(result: RegenerationResult) -> dict[str, int | None]:
    usages = [
        invocation.model_response.usage
        for invocation in result.model_invocations
        if invocation.model_response is not None
    ]
    values: dict[str, int | None] = {}
    for field_name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        field_values = [
            None if usage is None else getattr(usage, field_name) for usage in usages
        ]
        values[field_name] = (
            sum(value for value in field_values if value is not None)
            if field_values and all(value is not None for value in field_values)
            else None
        )
    return values


def _schema_tool_call(call: ModelToolCall | None) -> dict[str, Any] | None:
    if (
        call is None
        or type(call.tool_call_id) is not str
        or call.tool_call_id == ""
        or not call.parse_success
        or type(call.parsed_arguments) is not MappingProxyType
    ):
        return None
    return {
        "tool_call_id": call.tool_call_id,
        "tool": call.tool_name,
        "arguments": thaw_json_value(call.parsed_arguments),
    }


def _drift_class(action: RegenerationAction, original_arguments: dict[str, str]) -> str:
    if action.action_type == MODEL_STOP:
        return "D5_ABANDONMENT_OR_NO_MUTATION"
    if action.action_type == BUDGET_REJECTED_TOOL_CALL:
        return "D7_OTHER"
    call = action.tool_call
    if call is None or not call.parse_success or type(call.parsed_arguments) is not MappingProxyType:
        return "D7_OTHER"
    arguments = thaw_json_value(call.parsed_arguments)
    if call.tool_name == "list_tickets" and arguments == {} and action.validation_status == "VALID":
        return "D4_READ_OR_VERIFICATION"
    if call.tool_name != "create_ticket":
        return "D3_DIFFERENT_TOOL"
    if set(arguments) != {"customer_id", "title", "description"}:
        return "D7_OTHER"
    if arguments == original_arguments:
        return "D0_EXACT_REQUEST_MATCH"
    if arguments.get("customer_id") != original_arguments["customer_id"]:
        return "D2_IDENTIFIER_DRIFT"
    return "D1_SAME_TOOL_ARGUMENT_DRIFT"


def _regeneration_actions(
    result: RegenerationResult, original_arguments: dict[str, str]
) -> tuple[list[dict[str, Any]], list[str]]:
    mapped: list[dict[str, Any]] = []
    classes: list[str] = []
    for action in result.recovery_actions:
        drift = _drift_class(action, original_arguments)
        classes.append(drift)
        mapped.append(
            {
                "action_sequence": action.action_sequence,
                "actor": "MODEL",
                "action_type": action.action_type,
                "model_call_index": action.model_call_index,
                "provider_model_request_id": action.provider_model_request_id,
                "assistant_content": action.assistant_content,
                "tool_call": _schema_tool_call(action.tool_call),
                "serialized_request": (
                    None
                    if action.serialized_request is None
                    else action.serialized_request.decode("utf-8")
                ),
                "request_hash": action.request_hash,
                "validation_status": action.validation_status,
                "executed": action.executed,
                "mutating": action.mutating,
                "committed_effect_event_ids": list(action.committed_effect_event_ids),
                "model_visible_observation": action.model_visible_observation,
                "drift_class": drift,
            }
        )
    return mapped, classes


def _request_drift(actions: list[dict[str, Any]], classes: list[str]) -> dict[str, Any]:
    mutating_classes = [
        item["drift_class"] for item in actions if item["mutating"]
    ]
    first_mutating = mutating_classes[0] if mutating_classes else None
    return {
        "applicable": True,
        "per_action": [
            {"action_sequence": item["action_sequence"], "class": drift}
            for item, drift in zip(actions, classes, strict=True)
        ],
        "first_action_class": classes[0] if classes else None,
        "first_mutating_action_class": first_mutating,
        "terminal_class": (
            mutating_classes[-1]
            if mutating_classes
            else "D5_ABANDONMENT_OR_NO_MUTATION"
        ),
        "exact_request_preserved": first_mutating == "D0_EXACT_REQUEST_MATCH",
        "any_read": "D4_READ_OR_VERIFICATION" in classes,
        "any_exact_request_match": "D0_EXACT_REQUEST_MATCH" in classes,
        "any_argument_drift": "D1_SAME_TOOL_ARGUMENT_DRIFT" in classes,
        "any_identifier_drift": "D2_IDENTIFIER_DRIFT" in classes,
    }


def _effective_pair_evaluations(
    result: EligibleMatchedTrialResult, hidden_world: HiddenWorld
) -> tuple[EvaluationResult, EvaluationResult]:
    replay = result.h0_replay if hidden_world is HiddenWorld.NOT_EXECUTED else result.h1_replay
    regeneration = (
        result.h0_regeneration
        if hidden_world is HiddenWorld.NOT_EXECUTED
        else result.h1_regeneration
    )
    reasons = tuple(
        dict.fromkeys(replay.evaluation.exclusion_reasons + regeneration.evaluation.exclusion_reasons)
    )
    if not reasons:
        return replay.evaluation, regeneration.evaluation
    intended = result.original_generation.task_spec.expected_arguments

    def excluded(snapshot: bytes) -> EvaluationResult:
        state = TicketEnvironment.clone_from_snapshot(snapshot).state
        return evaluate_ticket_state(
            state,
            customer_id=intended.customer_id,
            title=intended.title,
            description=intended.description,
            infrastructure_failure=True,
            infrastructure_failure_reasons=reasons,
        )

    return excluded(replay.final_state_snapshot), excluded(regeneration.final_state_snapshot)


def _errors(
    arm_id: str,
    policy: str,
    result: ExactReplayResult | RegenerationResult,
    effective_evaluation: EvaluationResult,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if policy == LLM_REGENERATION:
        assert type(result) is RegenerationResult
        for invocation in result.model_invocations:
            if invocation.rejected_generation is not None:
                errors.append(
                    {
                        "error_id": f"{arm_id}:error-{len(errors) + 1}",
                        "category": "BEHAVIORAL",
                        "code": "MODEL_REJECTED_GENERATION",
                        "message": str(invocation.rejected_generation),
                        "behavioral": True,
                        "caused_exclusion": False,
                        "rejected_generation": rejected_generation_as_json(
                            invocation.rejected_generation,
                            model_call_index=invocation.model_call_index,
                            derived_seed=invocation.derived_seed,
                        ),
                    }
                )
            if invocation.infrastructure_error is not None:
                code = (
                    result.evaluation.exclusion_reasons[0]
                    if result.evaluation.exclusion_reasons
                    else "IMPLEMENTATION_BUG"
                )
                errors.append(
                    {
                        "error_id": f"{arm_id}:error-{len(errors) + 1}",
                        "category": "INFRASTRUCTURE",
                        "code": code,
                        "message": str(invocation.infrastructure_error),
                        "behavioral": False,
                        "caused_exclusion": True,
                    }
                )
        if result.termination_reason in (INVALID_MODEL_TOOL_CALL, ACTION_BUDGET_EXCEEDED):
            detail = next(
                (
                    action.validation_detail
                    for action in result.recovery_actions
                    if action.validation_detail is not None
                ),
                result.termination_reason,
            )
            errors.append(
                {
                    "error_id": f"{arm_id}:error-{len(errors) + 1}",
                    "category": "BEHAVIORAL",
                    "code": result.termination_reason.upper(),
                    "message": detail,
                    "behavioral": True,
                    "caused_exclusion": False,
                }
            )
    missing = [
        reason
        for reason in effective_evaluation.exclusion_reasons
        if reason not in result.evaluation.exclusion_reasons
    ]
    for reason in missing:
        errors.append(
            {
                "error_id": f"{arm_id}:error-{len(errors) + 1}",
                "category": "INFRASTRUCTURE",
                "code": reason,
                "message": "paired arm infrastructure exclusion propagated symmetrically",
                "behavioral": False,
                "caused_exclusion": True,
            }
        )
    return errors


def _lifecycle_events(
    execution: EligibleMatchedTrialResult,
    hidden_world: HiddenWorld,
    policy: str,
    arm_result: ExactReplayResult | RegenerationResult,
) -> list[dict[str, Any]]:
    payloads: list[tuple[str, dict[str, Any]]] = [
        ("RUN_STARTED", {}),
        ("STATE_INITIALIZED", {"state_hash": execution.initial_state_hash}),
        (
            "ORIGINAL_REQUEST_GENERATED",
            {"model_response": _model_response(execution.original_generation.model_response)},
        ),
        ("ORIGINAL_REQUEST_FROZEN", {"request_hash": execution.original_request_hash}),
    ]
    world = (
        execution.family_construction.not_executed
        if hidden_world is HiddenWorld.NOT_EXECUTED
        else execution.family_construction.executed_ack_lost
    )
    if world.original_request_executed:
        payloads.extend(
            [
                ("ORIGINAL_REQUEST_DISPATCHED", {"dispatch_count": 1}),
                (
                    "ORIGINAL_MUTATION_COMMITTED",
                    {"event_ids": list(world.original_commit_event_ids)},
                ),
            ]
        )
    payloads.extend(
        [
            ("AMBIGUITY_INJECTED", {}),
            ("STATE_CLONED", {"post_ambiguity_state_hash": world.post_ambiguity_state_hash}),
            ("RECOVERY_STARTED", {"policy": policy}),
        ]
    )
    if policy == EXACT_REPLAY:
        assert type(arm_result) is ExactReplayResult
        payloads.extend(
            [
                ("TOOL_REQUESTED", {"actor": "REPLAY_POLICY"}),
                ("TOOL_DISPATCHED", {"request_hash": arm_result.request_hash}),
                ("TOOL_COMMITTED", {"event_ids": list(arm_result.committed_effect_event_ids)}),
                ("TOOL_OBSERVED", {"observation": arm_result.model_visible_observation}),
            ]
        )
    else:
        assert type(arm_result) is RegenerationResult
        invocation_indexes = tuple(
            invocation.model_call_index for invocation in arm_result.model_invocations
        )
        if any(type(index) is not int for index in invocation_indexes) or (
            invocation_indexes != tuple(range(len(arm_result.model_invocations)))
        ):
            raise TraceSerializationError(
                "Regeneration invocation indexes must be zero-based and contiguous"
            )
        action_sequences = tuple(
            action.action_sequence for action in arm_result.recovery_actions
        )
        if any(type(sequence) is not int for sequence in action_sequences):
            raise TraceSerializationError(
                "Regeneration action_sequence values must be integers"
            )
        if any(
            current >= following
            for current, following in zip(
                action_sequences, action_sequences[1:], strict=False
            )
        ):
            raise TraceSerializationError(
                "Regeneration actions must be strictly increasing by action_sequence"
            )
        known_invocations = set(invocation_indexes)
        if any(
            type(action.model_call_index) is not int
            or action.model_call_index not in known_invocations
            for action in arm_result.recovery_actions
        ):
            raise TraceSerializationError(
                "Regeneration action references a nonexistent model invocation"
            )
        action_invocation_indexes = tuple(
            action.model_call_index for action in arm_result.recovery_actions
        )
        if action_invocation_indexes != tuple(sorted(action_invocation_indexes)):
            raise TraceSerializationError(
                "Regeneration action/invocation ordering is incoherent"
            )
        actions_by_invocation = {
            index: [
                action
                for action in arm_result.recovery_actions
                if action.model_call_index == index
            ]
            for index in invocation_indexes
        }
        emitted_action_sequences: set[int] = set()
        for invocation in arm_result.model_invocations:
            invocation_payload: dict[str, Any] = {
                "model_call_index": invocation.model_call_index,
                "derived_seed": invocation.derived_seed,
                "model_request": _model_request(invocation.model_request),
                "model_response": (
                    None
                    if invocation.model_response is None
                    else _model_response(invocation.model_response)
                ),
                "rejected_generation": (
                    None
                    if invocation.rejected_generation is None
                    else rejected_generation_as_json(
                        invocation.rejected_generation,
                        model_call_index=invocation.model_call_index,
                        derived_seed=invocation.derived_seed,
                    )
                ),
                "infrastructure_error": (
                    None
                    if invocation.infrastructure_error is None
                    else {
                        "type": type(invocation.infrastructure_error).__name__,
                        "message": str(invocation.infrastructure_error),
                    }
                ),
            }
            payloads.append(("MODEL_INVOKED", invocation_payload))
            for action in actions_by_invocation[invocation.model_call_index]:
                if action.action_sequence in emitted_action_sequences:
                    raise TraceSerializationError(
                        "Regeneration action would be emitted more than once"
                    )
                emitted_action_sequences.add(action.action_sequence)
                payloads.append(
                    (
                        "TOOL_REQUESTED",
                        {
                            "action_sequence": action.action_sequence,
                            "raw_tool_call": (
                                None
                                if action.tool_call is None
                                else _tool_call_raw(action.tool_call)
                            ),
                            "validation_detail": action.validation_detail,
                        },
                    )
                )
                if action.executed:
                    payloads.append(
                        (
                            "TOOL_DISPATCHED",
                            {"request_hash": action.request_hash},
                        )
                    )
                    if action.committed_effect_event_ids:
                        payloads.append(
                            (
                                "TOOL_COMMITTED",
                                {
                                    "event_ids": list(
                                        action.committed_effect_event_ids
                                    )
                                },
                            )
                        )
                    payloads.append(
                        (
                            "TOOL_OBSERVED",
                            {"observation": action.model_visible_observation},
                        )
                    )
        if len(emitted_action_sequences) != len(arm_result.recovery_actions):
            raise TraceSerializationError(
                "Regeneration action could not be associated with exactly one invocation"
            )
    payloads.extend(
        [
            ("RECOVERY_TERMINATED", {"termination_reason": arm_result.termination_reason}),
            ("FINAL_STATE_EVALUATED", {}),
            ("RUN_FINISHED", {}),
        ]
    )
    return [
        {"event_sequence": index, "event_type": event_type, "evaluator_payload": payload}
        for index, (event_type, payload) in enumerate(payloads, start=1)
    ]


def arm_trace_as_json(
    *,
    entry: EngineeringManifestEntry,
    execution: EligibleMatchedTrialResult,
    hidden_world: HiddenWorld,
    policy: str,
    metadata: TraceRunMetadata,
) -> dict[str, Any]:
    """Create one recovery-arm record conforming to trace_schema_v1.json."""

    if execution.plan != entry.plan:
        raise TraceSerializationError("execution plan does not match manifest entry")
    if policy not in (EXACT_REPLAY, LLM_REGENERATION):
        raise TraceSerializationError("unknown recovery policy")
    replay = execution.h0_replay if hidden_world is HiddenWorld.NOT_EXECUTED else execution.h1_replay
    regeneration = (
        execution.h0_regeneration
        if hidden_world is HiddenWorld.NOT_EXECUTED
        else execution.h1_regeneration
    )
    arm_result: ExactReplayResult | RegenerationResult = replay if policy == EXACT_REPLAY else regeneration
    replay_evaluation, regeneration_evaluation = _effective_pair_evaluations(execution, hidden_world)
    evaluation = replay_evaluation if policy == EXACT_REPLAY else regeneration_evaluation
    plan = execution.plan
    arm_id = plan.arm_id(hidden_world, policy)
    pair_order = plan.arm_order(hidden_world)
    world_evidence = (
        execution.family_construction.not_executed
        if hidden_world is HiddenWorld.NOT_EXECUTED
        else execution.family_construction.executed_ack_lost
    )
    context = execution.regeneration_context
    original_call = context.original_tool_call
    original_arguments = original_call.arguments.as_dict()
    if policy == EXACT_REPLAY:
        actions = [
            {
                "action_sequence": 1,
                "actor": "REPLAY_POLICY",
                "action_type": "TOOL_CALL",
                "model_call_index": None,
                "provider_model_request_id": None,
                "assistant_content": None,
                "tool_call": {
                    "tool_call_id": original_call.tool_call_id,
                    "tool": original_call.tool,
                    "arguments": original_arguments,
                },
                "serialized_request": execution.original_generation.serialized_original_request.decode("utf-8"),
                "request_hash": execution.original_request_hash,
                "validation_status": "VALID",
                "executed": True,
                "mutating": True,
                "committed_effect_event_ids": list(replay.committed_effect_event_ids),
                "model_visible_observation": replay.model_visible_observation,
                "drift_class": None,
            }
        ]
        drift = {
            "applicable": False,
            "per_action": [],
            "first_action_class": None,
            "first_mutating_action_class": None,
            "terminal_class": None,
            "exact_request_preserved": None,
            "any_read": False,
            "any_exact_request_match": False,
            "any_argument_drift": False,
            "any_identifier_drift": False,
        }
        recovery_usage = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
        regeneration_sampling = None
    else:
        actions, classes = _regeneration_actions(regeneration, original_arguments)
        drift = _request_drift(actions, classes)
        recovery_usage = _summed_recovery_usage(regeneration)
        regeneration_sampling = entry.model_config.regeneration.as_trace_sampling_configuration()
    final_state = _state(arm_result.final_state_snapshot)
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "experiment_version": EXPERIMENT_VERSION,
        "git_commit": metadata.git_commit,
        "timestamp": metadata.timestamp,
        "identifiers": {
            "run_id": plan.run_id(hidden_world, policy),
            "base_trial_id": plan.base_trial_id,
            "trial_family_id": plan.trial_family_id,
            "pair_id": plan.pair_id(hidden_world),
            "arm_id": arm_id,
            "scenario_id": entry.scenario_id,
            "manifest_id": plan.manifest_id,
        },
        "mutation_class": "CREATE",
        "recovery_policy": policy,
        "model": entry.model_config.model.as_trace_model(),
        "sampling": {
            "model_config_id": entry.model_config.model_config_id,
            "original_generation": entry.model_config.original_generation.as_trace_sampling_configuration(),
            "regeneration": regeneration_sampling,
        },
        "execution_order": {
            "family_hidden_world_order": [world.value for world in plan.hidden_world_order],
            "hidden_world_pair_position": plan.hidden_world_order.index(hidden_world) + 1,
            "pair_arm_order": list(pair_order),
            "arm_position": pair_order.index(policy) + 1,
            "arms_executed_serially": True,
        },
        "model_visible": {
            "system_prompt": context.system_message.content,
            "user_task": entry.scenario.user_task,
            "tools_exposed": [tool.as_dict() for tool in context.tools],
            "original_tool_call": {
                "provider_tool_call_id": original_call.tool_call_id,
                "tool": original_call.tool,
                "arguments_json": original_call.arguments_json,
                "arguments": original_arguments,
                "raw_assistant_content": context.original_assistant_message.content,
            },
            "canonical_ambiguous_observation": context.ambiguity_tool_message.content,
            "model_visible_context": [message.as_dict() for message in context.messages],
            "model_visible_context_hash": context.canonical_context_sha256,
        },
        "frozen_original": {
            "serialized_original_request": execution.original_generation.serialized_original_request.decode("utf-8"),
            "original_request_hash": execution.original_request_hash,
            "serialization_format": "canonical-json-v1-utf8-no-bom-no-newline",
            "eligibility_verified": True,
        },
        "recovery_actions": actions,
        "request_drift": drift,
        "usage": {
            "original_generation": _token_usage(execution.original_generation.model_response),
            "recovery": recovery_usage,
            "additional_llm_calls": arm_result.additional_llm_calls,
            "recovery_tool_calls_attempted": arm_result.recovery_tool_calls_attempted,
            "recovery_tool_calls_executed": arm_result.recovery_tool_calls_executed,
            "reported_cost": None,
        },
        "latency": {
            "hidden_world_construction_ms": execution.hidden_world_construction_ms,
            "recovery_wall_ms": arm_result.latency.recovery_wall_ms,
            "recovery_model_ms": arm_result.latency.recovery_model_ms,
            "recovery_tool_ms": arm_result.latency.recovery_tool_ms,
        },
        "evaluator_only": {
            "hidden_world": hidden_world.value,
            "original_request_executed": world_evidence.original_request_executed,
            "environment_version": ENVIRONMENT_VERSION,
            "intended_effect": original_arguments,
            "initial_state": _state(execution.family_construction.initial_state_snapshot),
            "initial_state_hash": execution.initial_state_hash,
            "post_ambiguity_state": _state(world_evidence.post_ambiguity_snapshot),
            "post_ambiguity_state_hash": world_evidence.post_ambiguity_state_hash,
            "committed_effects": final_state["mutation_events"],
            "final_state": final_state,
            "final_state_hash": arm_result.final_state_hash,
            "evaluation": evaluation.as_dict(),
            "lifecycle_events": _lifecycle_events(execution, hidden_world, policy, arm_result),
        },
        "errors": _errors(arm_id, policy, arm_result, evaluation),
        "termination_reason": arm_result.termination_reason,
    }


__all__ = [
    "TRACE_SCHEMA_VERSION",
    "TraceRunMetadata",
    "TraceSerializationError",
    "arm_trace_as_json",
    "model_request_as_json",
    "model_response_as_json",
    "rejected_generation_as_json",
]
