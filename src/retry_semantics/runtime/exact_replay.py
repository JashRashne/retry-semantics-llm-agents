"""One-shot V1 Exact Replay recovery semantics."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field

from retry_semantics.environments.ticket import (
    EvaluationResult,
    FrozenExecutableRequest,
    SourceStage,
    TicketEnvironment,
    evaluate_ticket_state,
)
from retry_semantics.serialization import sha256_hex

EXACT_REPLAY = "EXACT_REPLAY"
REPLAY_EXECUTED = "replay_executed"
_CREATED_OBSERVATION = b'{"status":"created"}'


class ReplayProtocolError(ValueError):
    """Exact Replay input or execution violated the frozen V1 protocol."""


@dataclass(frozen=True, slots=True)
class RecoveryLatency:
    """Evaluator-only recovery timing that never enters model context."""

    recovery_wall_ms: float
    recovery_model_ms: float
    recovery_tool_ms: float

    def __post_init__(self) -> None:
        for name, value in (
            ("recovery_wall_ms", self.recovery_wall_ms),
            ("recovery_model_ms", self.recovery_model_ms),
            ("recovery_tool_ms", self.recovery_tool_ms),
        ):
            if type(value) is not float or not math.isfinite(value) or value < 0:
                raise ReplayProtocolError(f"{name} must be a non-negative finite float")


@dataclass(frozen=True, slots=True)
class ExactReplayResult:
    """Deterministic result boundary for one successful Exact Replay action."""

    request_hash: str
    model_visible_observation: str
    committed_effect_event_ids: tuple[str, ...]
    final_state_snapshot: bytes
    final_state_hash: str
    evaluation: EvaluationResult
    latency: RecoveryLatency = field(compare=False)
    policy: str = field(default=EXACT_REPLAY, init=False)
    recovery_tool_calls_attempted: int = field(default=1, init=False)
    recovery_tool_calls_executed: int = field(default=1, init=False)
    additional_llm_calls: int = field(default=0, init=False)
    termination_reason: str = field(default=REPLAY_EXECUTED, init=False)


def _validate_replay_inputs(
    *,
    environment: TicketEnvironment,
    frozen_request: FrozenExecutableRequest,
    serialized_original_request: bytes,
    original_request_hash: str,
    arm_id: str,
) -> None:
    """Validate every redundant frozen-request representation before dispatch."""

    if type(environment) is not TicketEnvironment:
        raise ReplayProtocolError("environment must be a TicketEnvironment")
    if type(frozen_request) is not FrozenExecutableRequest:
        raise ReplayProtocolError(
            "frozen_request must be a FrozenExecutableRequest"
        )
    if type(serialized_original_request) is not bytes:
        raise ReplayProtocolError("serialized_original_request must be bytes")
    if type(original_request_hash) is not str:
        raise ReplayProtocolError("original_request_hash must be a string")
    if type(arm_id) is not str or arm_id == "":
        raise ReplayProtocolError("Exact Replay requires a non-empty arm_id")
    if frozen_request.serialized_request != serialized_original_request:
        raise ReplayProtocolError(
            "frozen request does not match serialized_original_request"
        )
    if frozen_request.request_hash != original_request_hash:
        raise ReplayProtocolError(
            "frozen request does not match original_request_hash"
        )
    if sha256_hex(serialized_original_request) != original_request_hash:
        raise ReplayProtocolError(
            "original_request_hash does not match serialized_original_request"
        )


def execute_exact_replay(
    environment: TicketEnvironment,
    *,
    frozen_request: FrozenExecutableRequest,
    serialized_original_request: bytes,
    original_request_hash: str,
    arm_id: str,
) -> ExactReplayResult:
    """Dispatch the exact frozen V1 CREATE bytes once, terminate, and evaluate.

    The caller must supply an Exact Replay arm environment produced from a
    hidden-world snapshot and that trial family's eligible original request M.
    No hidden-world label, read capability, or model dependency enters this
    boundary.
    """

    recovery_started_ns = time.perf_counter_ns()
    _validate_replay_inputs(
        environment=environment,
        frozen_request=frozen_request,
        serialized_original_request=serialized_original_request,
        original_request_hash=original_request_hash,
        arm_id=arm_id,
    )

    dispatch_count_before = environment.dispatch_count

    # This exact caller-supplied bytes object crosses the replay boundary. It is
    # not parsed, reconstructed, normalized, or reserialized by the policy.
    tool_started_ns = time.perf_counter_ns()
    observation = environment.execute_request(
        serialized_original_request,
        source_stage=SourceStage.RECOVERY,
        arm_id=arm_id,
        expected_request_hash=original_request_hash,
    )
    recovery_tool_ns = time.perf_counter_ns() - tool_started_ns

    if environment.dispatch_count - dispatch_count_before != 1:
        raise ReplayProtocolError("Exact Replay must dispatch exactly once")
    committed_events = tuple(
        event
        for event in environment.state.mutation_events
        if event.source_stage is SourceStage.RECOVERY and event.arm_id == arm_id
    )
    if len(committed_events) != 1:
        raise ReplayProtocolError(
            "eligible Exact Replay CREATE must commit exactly one event"
        )
    recovery_event = committed_events[0]
    if (
        recovery_event.source_stage is not SourceStage.RECOVERY
        or recovery_event.arm_id != arm_id
        or recovery_event.serialized_request is not serialized_original_request
        or recovery_event.request_hash != original_request_hash
    ):
        raise ReplayProtocolError("recovery mutation provenance is incoherent")
    if observation != _CREATED_OBSERVATION:
        raise ReplayProtocolError("eligible Exact Replay CREATE returned unexpectedly")

    # Parsing happens only after the sole recovery dispatch has terminated and
    # solely to supply M's frozen logical effect to the deterministic evaluator.
    # No parsed representation is ever sent back to the executor.
    request_value = json.loads(serialized_original_request)
    arguments = request_value["arguments"]
    final_state_snapshot = environment.snapshot_bytes()
    evaluation = evaluate_ticket_state(
        environment.state,
        customer_id=arguments["customer_id"],
        title=arguments["title"],
        description=arguments["description"],
    )

    recovery_wall_ns = time.perf_counter_ns() - recovery_started_ns
    return ExactReplayResult(
        request_hash=original_request_hash,
        model_visible_observation=observation.decode("utf-8"),
        committed_effect_event_ids=(recovery_event.event_id,),
        final_state_snapshot=final_state_snapshot,
        final_state_hash=sha256_hex(final_state_snapshot),
        evaluation=evaluation,
        latency=RecoveryLatency(
            recovery_wall_ms=recovery_wall_ns / 1_000_000,
            recovery_model_ms=0.0,
            recovery_tool_ms=recovery_tool_ns / 1_000_000,
        ),
    )
