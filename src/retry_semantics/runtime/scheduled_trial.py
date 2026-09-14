"""Smallest V1 orchestration boundary for one scheduled trial attempt."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeAlias

from retry_semantics.environments.ticket import (
    FrozenExecutableRequest,
    SourceStage,
    TicketEnvironment,
)
from retry_semantics.models.base import ModelCallConfig, ModelClient
from retry_semantics.runtime.exact_replay import (
    EXACT_REPLAY,
    ExactReplayResult,
    execute_exact_replay,
)
from retry_semantics.runtime.hidden_worlds import (
    ConstructedHiddenWorld,
    HiddenWorld,
    TrialFamilyStates,
    construct_trial_family_states,
)
from retry_semantics.runtime.original_generation import (
    EligibleOriginalGeneration,
    OriginalGenerationBehavioralFailure,
    OriginalGenerationAttemptResult,
    V1CreateTicketTaskSpec,
    run_v1_original_generation_attempt,
)
from retry_semantics.runtime.regeneration import (
    LLM_REGENERATION,
    RegenerationResult,
    execute_llm_regeneration,
)
from retry_semantics.runtime.regeneration_context import (
    CanonicalRegenerationContext,
    build_canonical_regeneration_context,
)
from retry_semantics.serialization import sha256_hex

_SCENARIO_ID = re.compile(r"CREATE-[0-9]{3}").fullmatch
_BASE_TRIAL_ID = re.compile(r"bt-.+-[0-9]{6}").fullmatch
_POLICIES = frozenset((EXACT_REPLAY, LLM_REGENERATION))


class ScheduledTrialProtocolError(ValueError):
    """A scheduled trial input violates the frozen V1 orchestration contract."""


def _validate_arm_order(name: str, order: object) -> None:
    if (
        type(order) is not tuple
        or len(order) != 2
        or any(type(policy) is not str for policy in order)
        or set(order) != _POLICIES
    ):
        raise ScheduledTrialProtocolError(
            f"{name} must contain EXACT_REPLAY and LLM_REGENERATION exactly once"
        )


@dataclass(frozen=True, slots=True)
class ScheduledTrialPlan:
    """One already-materialized manifest slot, without manifest generation logic."""

    manifest_id: str
    scheduled_attempt_ordinal: int
    scenario_id: str
    task_spec: V1CreateTicketTaskSpec
    hidden_world_order: tuple[HiddenWorld, HiddenWorld]
    h0_arm_order: tuple[str, str]
    h1_arm_order: tuple[str, str]

    def __post_init__(self) -> None:
        if type(self.manifest_id) is not str or self.manifest_id == "":
            raise ScheduledTrialProtocolError("manifest_id must be a non-empty string")
        if (
            type(self.scheduled_attempt_ordinal) is not int
            or not 0 <= self.scheduled_attempt_ordinal <= 999_999
        ):
            raise ScheduledTrialProtocolError(
                "scheduled_attempt_ordinal must fit the frozen six-digit identifier"
            )
        if _BASE_TRIAL_ID(self.base_trial_id) is None:
            raise ScheduledTrialProtocolError(
                "manifest_id cannot form a frozen base-trial identifier"
            )
        if type(self.scenario_id) is not str or _SCENARIO_ID(self.scenario_id) is None:
            raise ScheduledTrialProtocolError(
                "scenario_id must match the frozen CREATE-NNN convention"
            )
        if type(self.task_spec) is not V1CreateTicketTaskSpec:
            raise ScheduledTrialProtocolError(
                "task_spec must be a V1CreateTicketTaskSpec"
            )
        if (
            type(self.hidden_world_order) is not tuple
            or len(self.hidden_world_order) != 2
            or any(type(world) is not HiddenWorld for world in self.hidden_world_order)
            or set(self.hidden_world_order) != set(HiddenWorld)
        ):
            raise ScheduledTrialProtocolError(
                "hidden_world_order must contain H0 and H1 exactly once"
            )
        _validate_arm_order("h0_arm_order", self.h0_arm_order)
        _validate_arm_order("h1_arm_order", self.h1_arm_order)

    @property
    def base_trial_id(self) -> str:
        return f"bt-{self.manifest_id}-{self.scheduled_attempt_ordinal:06d}"

    @property
    def trial_family_id(self) -> str:
        return f"family-{self.base_trial_id}"

    def pair_id(self, hidden_world: HiddenWorld) -> str:
        if type(hidden_world) is not HiddenWorld:
            raise ScheduledTrialProtocolError(
                f"unknown hidden world: {hidden_world!r}"
            )
        suffix = "H0" if hidden_world is HiddenWorld.NOT_EXECUTED else "H1"
        return f"pair-{self.trial_family_id}-{suffix}"

    def arm_id(self, hidden_world: HiddenWorld, policy: str) -> str:
        if type(policy) is not str or policy not in _POLICIES:
            raise ScheduledTrialProtocolError(f"unknown recovery policy: {policy!r}")
        policy_suffix = "P1" if policy == EXACT_REPLAY else "P2"
        return f"{self.pair_id(hidden_world)}:{policy_suffix}"

    def run_id(self, hidden_world: HiddenWorld, policy: str) -> str:
        return f"run-{self.arm_id(hidden_world, policy)}"

    def arm_order(self, hidden_world: HiddenWorld) -> tuple[str, str]:
        if hidden_world is HiddenWorld.NOT_EXECUTED:
            return self.h0_arm_order
        if hidden_world is HiddenWorld.EXECUTED_ACK_LOST:
            return self.h1_arm_order
        raise ScheduledTrialProtocolError(f"unknown hidden world: {hidden_world!r}")


@dataclass(frozen=True, slots=True)
class PreTreatmentFailureTrialResult:
    """A scheduled attempt that cannot create hidden worlds or recovery arms."""

    plan: ScheduledTrialPlan
    original_generation: OriginalGenerationBehavioralFailure

    def __post_init__(self) -> None:
        if type(self.plan) is not ScheduledTrialPlan:
            raise ScheduledTrialProtocolError("plan has the wrong type")
        if type(self.original_generation) is not OriginalGenerationBehavioralFailure:
            raise ScheduledTrialProtocolError(
                "pre-treatment result requires a behavioral generation failure"
            )


@dataclass(frozen=True, slots=True)
class HiddenWorldConstructionEvidence:
    """Immutable pre-policy evidence for one constructed hidden world."""

    hidden_world: HiddenWorld
    post_ambiguity_snapshot: bytes
    post_ambiguity_state_hash: str
    original_request_executed: bool
    original_request_dispatch_count: int
    original_commit_event_ids: tuple[str, ...]
    exact_replay_starting_state_snapshot: bytes
    exact_replay_starting_state_hash: str
    llm_regeneration_starting_state_snapshot: bytes
    llm_regeneration_starting_state_hash: str

    def __post_init__(self) -> None:
        if type(self.hidden_world) is not HiddenWorld:
            raise ScheduledTrialProtocolError(
                "hidden-world evidence has the wrong type"
            )
        if type(self.post_ambiguity_snapshot) is not bytes:
            raise ScheduledTrialProtocolError(
                "post-ambiguity snapshot must be immutable bytes"
            )
        if self.post_ambiguity_state_hash != sha256_hex(
            self.post_ambiguity_snapshot
        ):
            raise ScheduledTrialProtocolError(
                "post-ambiguity snapshot/hash evidence is incoherent"
            )
        if type(self.original_request_executed) is not bool:
            raise ScheduledTrialProtocolError(
                "original-request execution evidence must be boolean"
            )
        if (
            type(self.original_request_dispatch_count) is not int
            or self.original_request_dispatch_count < 0
        ):
            raise ScheduledTrialProtocolError(
                "original-request dispatch evidence must be non-negative"
            )
        if type(self.original_commit_event_ids) is not tuple or any(
            type(event_id) is not str or event_id == ""
            for event_id in self.original_commit_event_ids
        ):
            raise ScheduledTrialProtocolError(
                "original commit event IDs must be immutable non-empty strings"
            )
        if self.exact_replay_starting_state_snapshot != (
            self.post_ambiguity_snapshot
        ) or self.llm_regeneration_starting_state_snapshot != (
            self.post_ambiguity_snapshot
        ):
            raise ScheduledTrialProtocolError(
                "policy-arm starts do not match their hidden-world snapshot"
            )
        if self.exact_replay_starting_state_hash != (
            self.post_ambiguity_state_hash
        ) or self.llm_regeneration_starting_state_hash != (
            self.post_ambiguity_state_hash
        ):
            raise ScheduledTrialProtocolError(
                "policy-arm start hashes do not match their hidden-world hash"
            )


@dataclass(frozen=True, slots=True)
class TrialFamilyConstructionEvidence:
    """Immutable evidence captured from one family before recovery begins."""

    initial_state_snapshot: bytes
    initial_state_hash: str
    frozen_original_request: FrozenExecutableRequest
    serialized_original_request: bytes
    original_request_hash: str
    not_executed: HiddenWorldConstructionEvidence
    executed_ack_lost: HiddenWorldConstructionEvidence

    def __post_init__(self) -> None:
        if type(self.initial_state_snapshot) is not bytes:
            raise ScheduledTrialProtocolError(
                "initial-state snapshot must be immutable bytes"
            )
        if self.initial_state_hash != sha256_hex(self.initial_state_snapshot):
            raise ScheduledTrialProtocolError(
                "initial-state snapshot/hash evidence is incoherent"
            )
        if type(self.frozen_original_request) is not FrozenExecutableRequest:
            raise ScheduledTrialProtocolError(
                "frozen original request evidence has the wrong type"
            )
        if self.serialized_original_request != (
            self.frozen_original_request.serialized_request
        ):
            raise ScheduledTrialProtocolError(
                "serialized original-request evidence is incoherent"
            )
        if self.original_request_hash != self.frozen_original_request.request_hash:
            raise ScheduledTrialProtocolError(
                "original-request hash evidence is incoherent"
            )
        if self.original_request_hash != sha256_hex(self.serialized_original_request):
            raise ScheduledTrialProtocolError(
                "original-request bytes/hash evidence is incoherent"
            )
        if (
            type(self.not_executed) is not HiddenWorldConstructionEvidence
            or self.not_executed.hidden_world is not HiddenWorld.NOT_EXECUTED
        ):
            raise ScheduledTrialProtocolError("family evidence lacks canonical H0")
        if (
            type(self.executed_ack_lost) is not HiddenWorldConstructionEvidence
            or self.executed_ack_lost.hidden_world
            is not HiddenWorld.EXECUTED_ACK_LOST
        ):
            raise ScheduledTrialProtocolError("family evidence lacks canonical H1")
        if (
            self.not_executed.original_request_executed
            or self.not_executed.original_request_dispatch_count != 0
            or self.not_executed.original_commit_event_ids != ()
            or self.not_executed.post_ambiguity_snapshot
            != self.initial_state_snapshot
            or self.not_executed.post_ambiguity_state_hash
            != self.initial_state_hash
        ):
            raise ScheduledTrialProtocolError(
                "H0 construction evidence is incoherent"
            )
        if (
            not self.executed_ack_lost.original_request_executed
            or self.executed_ack_lost.original_request_dispatch_count != 1
            or len(self.executed_ack_lost.original_commit_event_ids) != 1
            or self.executed_ack_lost.post_ambiguity_snapshot
            == self.initial_state_snapshot
            or self.executed_ack_lost.post_ambiguity_state_hash
            == self.initial_state_hash
        ):
            raise ScheduledTrialProtocolError(
                "H1 construction evidence is incoherent"
            )


@dataclass(frozen=True, slots=True)
class EligibleMatchedTrialResult:
    """The four composed recovery results for one eligible scheduled attempt."""

    plan: ScheduledTrialPlan
    original_generation: EligibleOriginalGeneration
    family_construction: TrialFamilyConstructionEvidence
    regeneration_context: CanonicalRegenerationContext
    h0_replay: ExactReplayResult
    h0_regeneration: RegenerationResult
    h1_replay: ExactReplayResult
    h1_regeneration: RegenerationResult

    def __post_init__(self) -> None:
        if type(self.plan) is not ScheduledTrialPlan:
            raise ScheduledTrialProtocolError("plan has the wrong type")
        if type(self.original_generation) is not EligibleOriginalGeneration:
            raise ScheduledTrialProtocolError(
                "matched result requires an eligible original generation"
            )
        if type(self.family_construction) is not TrialFamilyConstructionEvidence:
            raise ScheduledTrialProtocolError(
                "family_construction has the wrong type"
            )
        if type(self.regeneration_context) is not CanonicalRegenerationContext:
            raise ScheduledTrialProtocolError("regeneration_context has the wrong type")
        if type(self.h0_replay) is not ExactReplayResult or type(
            self.h1_replay
        ) is not ExactReplayResult:
            raise ScheduledTrialProtocolError("Replay results have the wrong type")
        if type(self.h0_regeneration) is not RegenerationResult or type(
            self.h1_regeneration
        ) is not RegenerationResult:
            raise ScheduledTrialProtocolError(
                "Regeneration results have the wrong type"
            )

        frozen = self.original_generation.frozen_executable_request
        if self.family_construction.frozen_original_request != frozen:
            raise ScheduledTrialProtocolError(
                "matched result does not share the single frozen request M"
            )
        if self.family_construction.serialized_original_request != (
            self.original_generation.serialized_original_request
        ) or self.family_construction.original_request_hash != (
            self.original_generation.original_request_hash
        ):
            raise ScheduledTrialProtocolError(
                "construction evidence does not match original request bytes/hash"
            )
        if self.regeneration_context.original_assistant_message != (
            self.original_generation.original_assistant_message
        ):
            raise ScheduledTrialProtocolError(
                "matched result does not share the original assistant evidence"
            )
        if self.h0_replay.request_hash != frozen.request_hash or (
            self.h1_replay.request_hash != frozen.request_hash
        ):
            raise ScheduledTrialProtocolError(
                "Replay results do not identify the single frozen request M"
            )
        if self.h0_regeneration.arm_id != self.plan.arm_id(
            HiddenWorld.NOT_EXECUTED, LLM_REGENERATION
        ) or self.h1_regeneration.arm_id != self.plan.arm_id(
            HiddenWorld.EXECUTED_ACK_LOST, LLM_REGENERATION
        ):
            raise ScheduledTrialProtocolError(
                "Regeneration results do not retain their scheduled arm IDs"
            )

    @property
    def original_request_hash(self) -> str:
        return self.original_generation.original_request_hash

    @property
    def initial_state_hash(self) -> str:
        return self.family_construction.initial_state_hash


ScheduledTrialResult: TypeAlias = (
    PreTreatmentFailureTrialResult | EligibleMatchedTrialResult
)


def _world(
    family: TrialFamilyStates, hidden_world: HiddenWorld
) -> ConstructedHiddenWorld:
    if hidden_world is HiddenWorld.NOT_EXECUTED:
        return family.not_executed
    if hidden_world is HiddenWorld.EXECUTED_ACK_LOST:
        return family.executed_ack_lost
    raise ScheduledTrialProtocolError(f"unknown hidden world: {hidden_world!r}")


def _capture_hidden_world_evidence(
    world: ConstructedHiddenWorld,
) -> HiddenWorldConstructionEvidence:
    replay = world.arm_states.exact_replay_state
    regeneration = world.arm_states.llm_regeneration_state
    return HiddenWorldConstructionEvidence(
        hidden_world=world.hidden_world,
        post_ambiguity_snapshot=world.post_ambiguity_snapshot,
        post_ambiguity_state_hash=world.post_ambiguity_state_hash,
        original_request_executed=world.original_request_executed,
        original_request_dispatch_count=world.original_request_dispatch_count,
        original_commit_event_ids=world.original_commit_event_ids,
        exact_replay_starting_state_snapshot=replay.starting_state_snapshot,
        exact_replay_starting_state_hash=replay.starting_state_hash,
        llm_regeneration_starting_state_snapshot=(
            regeneration.starting_state_snapshot
        ),
        llm_regeneration_starting_state_hash=regeneration.starting_state_hash,
    )


def _capture_family_construction_evidence(
    family: TrialFamilyStates,
) -> TrialFamilyConstructionEvidence:
    """Copy immutable evidence before any execution-local arm is mutated."""

    return TrialFamilyConstructionEvidence(
        initial_state_snapshot=family.initial_state_snapshot,
        initial_state_hash=family.initial_state_hash,
        frozen_original_request=family.frozen_original_request,
        serialized_original_request=family.serialized_original_request,
        original_request_hash=family.original_request_hash,
        not_executed=_capture_hidden_world_evidence(family.not_executed),
        executed_ack_lost=_capture_hidden_world_evidence(
            family.executed_ack_lost
        ),
    )


def run_scheduled_trial(
    client: ModelClient,
    *,
    plan: ScheduledTrialPlan,
    initial_state: TicketEnvironment | bytes,
    original_generation_config: ModelCallConfig,
    regeneration_config: ModelCallConfig,
) -> ScheduledTrialResult:
    """Execute exactly one scheduled original attempt and, if eligible, one family."""

    if type(plan) is not ScheduledTrialPlan:
        raise ScheduledTrialProtocolError("plan must be a ScheduledTrialPlan")

    original: OriginalGenerationAttemptResult = run_v1_original_generation_attempt(
        client,
        task_spec=plan.task_spec,
        model_config=original_generation_config,
    )
    if type(original) is OriginalGenerationBehavioralFailure:
        return PreTreatmentFailureTrialResult(
            plan=plan,
            original_generation=original,
        )
    if type(original) is not EligibleOriginalGeneration:
        raise ScheduledTrialProtocolError(
            "original-generation boundary returned an unknown result type"
        )

    family = construct_trial_family_states(
        initial_state=initial_state,
        frozen_original_request=original.frozen_executable_request,
        serialized_original_request=original.serialized_original_request,
        original_request_hash=original.original_request_hash,
        original_source_stage=SourceStage.ORIGINAL,
        original_arm_id=None,
    )
    family_construction = _capture_family_construction_evidence(family)
    context = build_canonical_regeneration_context(
        user_task=original.task_spec.user_task,
        frozen_original_request=original.frozen_executable_request,
        original_assistant_message=original.original_assistant_message,
    )

    replay_results: dict[HiddenWorld, ExactReplayResult] = {}
    regeneration_results: dict[HiddenWorld, RegenerationResult] = {}
    for hidden_world in plan.hidden_world_order:
        constructed_world = _world(family, hidden_world)
        for policy in plan.arm_order(hidden_world):
            arm_id = plan.arm_id(hidden_world, policy)
            if policy == EXACT_REPLAY:
                arm = constructed_world.arm_states.exact_replay_state
                replay_results[hidden_world] = execute_exact_replay(
                    arm.environment,
                    frozen_request=arm.frozen_original_request,
                    serialized_original_request=arm.serialized_original_request,
                    original_request_hash=arm.original_request_hash,
                    arm_id=arm_id,
                )
            else:
                arm = constructed_world.arm_states.llm_regeneration_state
                regeneration_results[hidden_world] = execute_llm_regeneration(
                    arm.environment,
                    context=context,
                    client=client,
                    model_config=regeneration_config,
                    arm_id=arm_id,
                )

    return EligibleMatchedTrialResult(
        plan=plan,
        original_generation=original,
        family_construction=family_construction,
        regeneration_context=context,
        h0_replay=replay_results[HiddenWorld.NOT_EXECUTED],
        h0_regeneration=regeneration_results[HiddenWorld.NOT_EXECUTED],
        h1_replay=replay_results[HiddenWorld.EXECUTED_ACK_LOST],
        h1_regeneration=regeneration_results[HiddenWorld.EXECUTED_ACK_LOST],
    )


__all__ = [
    "EligibleMatchedTrialResult",
    "HiddenWorldConstructionEvidence",
    "PreTreatmentFailureTrialResult",
    "ScheduledTrialPlan",
    "ScheduledTrialProtocolError",
    "ScheduledTrialResult",
    "TrialFamilyConstructionEvidence",
    "run_scheduled_trial",
]
