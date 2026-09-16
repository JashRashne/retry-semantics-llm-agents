"""Provider-neutral V1.3 paper collection and atomic evidence persistence."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import TypeAlias

import jsonschema
from referencing import Registry, Resource

from retry_semantics.environments.ticket import (
    SnapshotValidationError,
    TicketEnvironment,
    evaluate_ticket_state,
)
from retry_semantics.experiment.paper_manifest import (
    INHERITED_EXECUTION_REVISION,
    PAPER_EXPERIMENT_REVISION,
    PAPER_SLOT_COUNT,
    PaperExperimentManifest,
    PaperManifestEntry,
    _orders_for_stratum,
    paper_queue,
    paper_stratum_for,
)
from retry_semantics.experiment.trace import (
    TraceRunMetadata,
    TraceSerializationError,
    is_trace_datetime,
    model_request_as_json,
    model_response_as_json,
    paper_arm_trace_as_json,
    rejected_generation_as_json,
)
from retry_semantics.models.base import (
    ModelAuthenticationError,
    ModelClient,
    ModelProviderStatusError,
    ModelRateLimitError,
    ModelRejectedGenerationError,
    ModelResponse,
    ModelResponseError,
    ModelTimeoutError,
    ModelTransportError,
    model_request_from_regeneration_context,
    freeze_json_value,
    thaw_json_value,
)
from retry_semantics.runtime.exact_replay import EXACT_REPLAY, ExactReplayResult
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.runtime.original_generation import (
    EligibleOriginalGeneration,
    OriginalGenerationBehavioralFailure,
    build_v1_original_generation_request,
    run_v1_original_generation_attempt,
)
from retry_semantics.runtime.regeneration import (
    INFRASTRUCTURE_FAILURE,
    LLM_REGENERATION,
    RegenerationResult,
)
from retry_semantics.runtime.scheduled_trial import (
    PreparedEligibleTrial,
    execute_prepared_recovery_arm,
    prepare_eligible_scheduled_trial,
)
from retry_semantics.runtime.regeneration_context import RegenerationContextProtocolError
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

_ROOT = Path(__file__).resolve().parents[3]
_TRACE_SCHEMA_PATH = _ROOT / "research" / "protocol" / "trace_schema_v1.json"
_PAPER_TRACE_SCHEMA_PATH = _ROOT / "research" / "protocol" / "paper_trace_schema_v1.json"
_LEDGER_SCHEMA_PATH = _ROOT / "research" / "protocol" / "paper_scheduled_attempt_schema_v1.json"
_EVENT_SCHEMA_PATH = _ROOT / "research" / "protocol" / "paper_collection_event_schema_v1.json"
_SUMMARY_SCHEMA_PATH = _ROOT / "research" / "protocol" / "paper_collection_summary_schema_v1.json"
_RUN_METADATA_SCHEMA_PATH = _ROOT / "research" / "protocol" / "paper_run_metadata_schema_v1.json"
PAPER_LEDGER_SCHEMA_VERSION = "paper-scheduled-attempt-v1"
PAPER_SUMMARY_SCHEMA_VERSION = "paper-collection-summary-v1"


class EligibilityOutcome(str, Enum):
    NOT_REACHED = "NOT_REACHED"
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE_BEHAVIORAL = "INELIGIBLE_BEHAVIORAL"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


class InfrastructureScope(str, Enum):
    ORIGINAL_GENERATION = "ORIGINAL_GENERATION"
    FAMILY_SYSTEM = "FAMILY_SYSTEM"
    ARM = "ARM"
    PERSISTENCE = "PERSISTENCE"


class InfrastructureStage(str, Enum):
    ENVIRONMENT_SETUP = "ENVIRONMENT_SETUP"
    ENVIRONMENT_CLONE_SETUP = "ENVIRONMENT_CLONE_SETUP"
    ORIGINAL_GENERATION = "ORIGINAL_GENERATION"
    FAMILY_CONSTRUCTION = "FAMILY_CONSTRUCTION"
    REGENERATION_CONTEXT_CONSTRUCTION = "REGENERATION_CONTEXT_CONSTRUCTION"
    ARM_EXECUTION = "ARM_EXECUTION"
    TRACE_SERIALIZATION = "TRACE_SERIALIZATION"
    PERSISTENCE = "PERSISTENCE"


class InfrastructureSubtype(str, Enum):
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    AUTHENTICATION = "AUTHENTICATION"
    HTTP_5XX = "HTTP_5XX"
    PROVIDER_STATUS = "PROVIDER_STATUS"
    TRANSPORT = "TRANSPORT"
    PROVIDER_RESPONSE = "PROVIDER_RESPONSE"
    FAMILY_CONSTRUCTION = "FAMILY_CONSTRUCTION"
    ENVIRONMENT_SETUP = "ENVIRONMENT_SETUP"
    ENVIRONMENT_CLONE_SETUP = "ENVIRONMENT_CLONE_SETUP"
    ARM_EXECUTION = "ARM_EXECUTION"
    PERSISTENCE = "PERSISTENCE"
    IMPLEMENTATION = "IMPLEMENTATION"


class ArmOpportunityStatus(str, Enum):
    NOT_ACTIVATED = "NOT_ACTIVATED"
    COMPLETED_TRACE = "COMPLETED_TRACE"
    INFRASTRUCTURE_FAILURE_WITH_TRACE = "INFRASTRUCTURE_FAILURE_WITH_TRACE"
    INFRASTRUCTURE_FAILURE_BEFORE_TRACE = "INFRASTRUCTURE_FAILURE_BEFORE_TRACE"


class ScheduledAttemptStatus(str, Enum):
    INELIGIBLE = "INELIGIBLE"
    ORIGINAL_GENERATION_INFRASTRUCTURE_FAILURE = "ORIGINAL_GENERATION_INFRASTRUCTURE_FAILURE"
    FAMILY_SYSTEM_FAILURE = "FAMILY_SYSTEM_FAILURE"
    RECOVERY_COMPLETE = "RECOVERY_COMPLETE"
    RECOVERY_COMPLETE_WITH_ARM_INFRASTRUCTURE = "RECOVERY_COMPLETE_WITH_ARM_INFRASTRUCTURE"


class CollectionCompletionStatus(str, Enum):
    COMPLETE_RECORDED = "COMPLETE_RECORDED"


class PaperCollectionError(ValueError):
    """A paper run cannot safely start, serialize, or be published."""


class PaperCollectionPreflightError(PaperCollectionError):
    """Manifest/client identity mismatch before slot zero."""


class PaperCollectionFatalError(PaperCollectionError):
    """Unrecoverable evidence/persistence corruption; never retry the run.

    The retained result and structured evidence may be saved by the caller in a
    separate diagnostic location.  They are not a completed paper bundle.
    """

    def __init__(self, message: str, *, evidence, result=None) -> None:
        super().__init__(message)
        self.evidence = evidence
        self.result = result
        self.completed_slot_outcomes = ()
        self.active_slot_index = None


@dataclass(frozen=True, slots=True)
class InfrastructureEvidence:
    scope: InfrastructureScope
    stage: InfrastructureStage
    subtype: InfrastructureSubtype
    exception_type: str
    message: str
    status_code: int | None
    attributable_arm_id: str | None = None
    attributable_policy: str | None = None
    attributable_hidden_world: HiddenWorld | None = None
    structured_evidence: object = None

    def __post_init__(self) -> None:
        if self.scope is InfrastructureScope.ARM:
            if (
                type(self.attributable_arm_id) is not str
                or self.attributable_arm_id == ""
                or self.attributable_policy not in (EXACT_REPLAY, LLM_REGENERATION)
                or type(self.attributable_hidden_world) is not HiddenWorld
            ):
                raise PaperCollectionError("arm infrastructure attribution is incomplete")
        elif any(value is not None for value in (
            self.attributable_arm_id, self.attributable_policy, self.attributable_hidden_world
        )):
            raise PaperCollectionError("non-arm infrastructure cannot fabricate policy attribution")

    @property
    def policy_attributable(self) -> bool:
        return self.scope is InfrastructureScope.ARM


ArmResult: TypeAlias = ExactReplayResult | RegenerationResult


@dataclass(frozen=True, slots=True)
class PaperArmExecution:
    hidden_world: HiddenWorld
    policy: str
    arm_id: str
    attempted: bool
    status: ArmOpportunityStatus
    result: ArmResult | None
    infrastructure_failure: InfrastructureEvidence | None
    pre_trace_evidence: object = None

    def __post_init__(self) -> None:
        if type(self.hidden_world) is not HiddenWorld or self.policy not in (EXACT_REPLAY, LLM_REGENERATION):
            raise PaperCollectionError("arm world/policy is invalid")
        if self.status is ArmOpportunityStatus.NOT_ACTIVATED:
            if self.attempted or self.result is not None or self.infrastructure_failure is not None:
                raise PaperCollectionError("non-activated arm evidence is incoherent")
        elif self.status is ArmOpportunityStatus.COMPLETED_TRACE:
            if not self.attempted or self.result is None or self.infrastructure_failure is not None:
                raise PaperCollectionError("completed arm evidence is incoherent")
        elif self.status is ArmOpportunityStatus.INFRASTRUCTURE_FAILURE_WITH_TRACE:
            if not self.attempted or type(self.result) is not RegenerationResult or self.infrastructure_failure is None:
                raise PaperCollectionError("traced infrastructure arm evidence is incoherent")
        elif self.status is ArmOpportunityStatus.INFRASTRUCTURE_FAILURE_BEFORE_TRACE:
            if not self.attempted or self.result is not None or self.infrastructure_failure is None:
                raise PaperCollectionError("pre-trace arm failure evidence is incoherent")
        else:
            raise PaperCollectionError("unknown arm opportunity status")
        if self.result is not None:
            expected_type = ExactReplayResult if self.policy == EXACT_REPLAY else RegenerationResult
            if type(self.result) is not expected_type:
                raise PaperCollectionError("arm result does not match policy")
        if self.infrastructure_failure is not None:
            evidence = self.infrastructure_failure
            if (
                evidence.scope is not InfrastructureScope.ARM
                or evidence.attributable_arm_id != self.arm_id
                or evidence.attributable_policy != self.policy
                or evidence.attributable_hidden_world is not self.hidden_world
            ):
                raise PaperCollectionError("arm failure attribution does not match opportunity")
        if self.pre_trace_evidence is not None and self.status is not ArmOpportunityStatus.INFRASTRUCTURE_FAILURE_BEFORE_TRACE:
            raise PaperCollectionError("pre-trace evidence belongs only to an absent failed arm trace")


@dataclass(frozen=True, slots=True)
class PaperScheduledAttemptExecution:
    entry: PaperManifestEntry
    attempt_started: bool
    original_generation_attempted: bool
    eligibility_outcome: EligibilityOutcome
    original_generation: EligibleOriginalGeneration | OriginalGenerationBehavioralFailure | None
    original_generation_infrastructure: InfrastructureEvidence | None
    trial_family_activated: bool
    family_id: str | None
    recovery_construction_started: bool
    prepared: PreparedEligibleTrial | None
    family_system_failure: InfrastructureEvidence | None
    arm_executions: tuple[PaperArmExecution, ...]
    terminal_status: ScheduledAttemptStatus

    def __post_init__(self) -> None:
        if type(self.entry) is not PaperManifestEntry or not self.attempt_started:
            raise PaperCollectionError("scheduled attempt must retain its started manifest slot")
        expected_arms = tuple(
            (world, policy, self.entry.plan.arm_id(world, policy))
            for world in self.entry.plan.hidden_world_order
            for policy in self.entry.plan.arm_order(world)
        )
        if type(self.arm_executions) is not tuple or tuple(
            (arm.hidden_world, arm.policy, arm.arm_id) for arm in self.arm_executions
        ) != expected_arms:
            raise PaperCollectionError("arm opportunities do not match the manifest order/IDs")
        if self.eligibility_outcome is EligibilityOutcome.INELIGIBLE_BEHAVIORAL:
            if type(self.original_generation) is not OriginalGenerationBehavioralFailure or not self.original_generation_attempted:
                raise PaperCollectionError("behavioral ineligibility evidence is incoherent")
            expected_terminal = ScheduledAttemptStatus.INELIGIBLE
        elif self.eligibility_outcome is EligibilityOutcome.INFRASTRUCTURE_FAILURE:
            if self.original_generation is not None or self.original_generation_infrastructure is None or not self.original_generation_attempted:
                raise PaperCollectionError("original infrastructure evidence is incoherent")
            expected_terminal = ScheduledAttemptStatus.ORIGINAL_GENERATION_INFRASTRUCTURE_FAILURE
        elif self.eligibility_outcome is EligibilityOutcome.NOT_REACHED:
            if self.original_generation is not None or self.original_generation_attempted or self.family_system_failure is None:
                raise PaperCollectionError("not-reached original evidence is incoherent")
            expected_terminal = ScheduledAttemptStatus.FAMILY_SYSTEM_FAILURE
        elif self.eligibility_outcome is EligibilityOutcome.ELIGIBLE:
            if type(self.original_generation) is not EligibleOriginalGeneration or not self.original_generation_attempted or not self.recovery_construction_started:
                raise PaperCollectionError("eligible original evidence is incoherent")
            expected_terminal = (
                ScheduledAttemptStatus.FAMILY_SYSTEM_FAILURE
                if not self.trial_family_activated
                else ScheduledAttemptStatus.RECOVERY_COMPLETE_WITH_ARM_INFRASTRUCTURE
                if any(arm.infrastructure_failure is not None for arm in self.arm_executions)
                else ScheduledAttemptStatus.RECOVERY_COMPLETE
            )
        else:
            raise PaperCollectionError("unknown eligibility outcome")
        if self.terminal_status is not expected_terminal:
            raise PaperCollectionError("terminal attempt status is incoherent")
        if self.original_generation is not None and (
            self.original_generation.task_spec != self.entry.plan.task_spec
            or self.original_generation.model_request.model_config != self.entry.original_generation_config
        ):
            raise PaperCollectionError("original-generation evidence does not match slot")
        if self.original_generation_infrastructure is not None and (
            self.eligibility_outcome is not EligibilityOutcome.INFRASTRUCTURE_FAILURE
            or self.original_generation_infrastructure.scope is not InfrastructureScope.ORIGINAL_GENERATION
        ):
            raise PaperCollectionError("original infrastructure scope/outcome is incoherent")
        if self.trial_family_activated:
            if self.prepared is None or self.family_id != self.entry.plan.trial_family_id or self.family_system_failure is not None:
                raise PaperCollectionError("activated family linkage is incoherent")
            if self.prepared.plan != self.entry.plan or self.prepared.original_generation != self.original_generation:
                raise PaperCollectionError("prepared family does not match original/slot")
            if not all(arm.attempted for arm in self.arm_executions):
                raise PaperCollectionError("activated family must retain all four attempted arm opportunities")
        elif self.prepared is not None or self.family_id is not None or any(arm.attempted for arm in self.arm_executions):
            raise PaperCollectionError("non-activated family cannot fabricate arms or family ID")
        if self.family_system_failure is not None and self.family_system_failure.scope is not InfrastructureScope.FAMILY_SYSTEM:
            raise PaperCollectionError("family/system failure has the wrong scope")
        if self.terminal_status is ScheduledAttemptStatus.FAMILY_SYSTEM_FAILURE and self.family_system_failure is None:
            raise PaperCollectionError("family/system failure lacks evidence")

    @property
    def expected_arm_opportunities_attempted(self) -> bool:
        return self.trial_family_activated and all(item.attempted for item in self.arm_executions)


@dataclass(frozen=True, slots=True)
class PaperCollectionSummary:
    scheduled_attempts: int
    attempts_started: int
    original_generations_attempted: int
    eligible_original_generations: int
    ineligible_attempts: int
    original_generation_infrastructure_failures: int
    activated_families: int
    arm_opportunities: int
    arm_opportunities_attempted: int
    arm_traces_collected: int
    arm_level_infrastructure_failures: int
    system_family_construction_failures: int
    completion_status: CollectionCompletionStatus


@dataclass(frozen=True, slots=True)
class PaperCollectionResult:
    manifest_id: str
    manifest_hash: str
    slot_outcomes: tuple[PaperScheduledAttemptExecution, ...]
    summary: PaperCollectionSummary
    collection_events: tuple[dict[str, object], ...]


def _client_provider(client: ModelClient) -> str:
    provider = getattr(client, "provider", None)
    if type(provider) is not str or provider == "":
        raise PaperCollectionPreflightError("ModelClient must expose a provider identity")
    return provider


def validate_paper_manifest_provider(manifest: PaperExperimentManifest, client: ModelClient) -> str:
    """Reject provider mismatch before any model invocation."""

    if type(manifest) is not PaperExperimentManifest:
        raise PaperCollectionError("manifest has the wrong type")
    actual = _client_provider(client)
    expected = {entry.model_config.model.provider for entry in manifest.entries}
    if expected != {actual}:
        raise PaperCollectionPreflightError(
            f"manifest providers {sorted(expected)!r} do not match ModelClient provider {actual!r}"
        )
    return actual


def _subtype(exc: Exception, *, stage: InfrastructureStage) -> InfrastructureSubtype:
    if isinstance(exc, ModelTimeoutError):
        return InfrastructureSubtype.TIMEOUT
    if isinstance(exc, ModelRateLimitError):
        return InfrastructureSubtype.RATE_LIMIT
    if isinstance(exc, ModelAuthenticationError):
        return InfrastructureSubtype.AUTHENTICATION
    if isinstance(exc, ModelProviderStatusError):
        return InfrastructureSubtype.HTTP_5XX if exc.status_code is not None and 500 <= exc.status_code <= 599 else InfrastructureSubtype.PROVIDER_STATUS
    if isinstance(exc, ModelTransportError):
        return InfrastructureSubtype.TRANSPORT
    if isinstance(exc, ModelResponseError):
        return InfrastructureSubtype.PROVIDER_RESPONSE
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, SnapshotValidationError):
            return InfrastructureSubtype.ENVIRONMENT_CLONE_SETUP
        cause = cause.__cause__
    if stage is InfrastructureStage.ENVIRONMENT_SETUP:
        return InfrastructureSubtype.ENVIRONMENT_SETUP
    if stage in (InfrastructureStage.FAMILY_CONSTRUCTION, InfrastructureStage.REGENERATION_CONTEXT_CONSTRUCTION):
        return InfrastructureSubtype.FAMILY_CONSTRUCTION
    if stage is InfrastructureStage.ARM_EXECUTION:
        return InfrastructureSubtype.ARM_EXECUTION
    if stage is InfrastructureStage.PERSISTENCE:
        return InfrastructureSubtype.PERSISTENCE
    return InfrastructureSubtype.IMPLEMENTATION


def _infrastructure(
    exc: Exception,
    *,
    scope: InfrastructureScope,
    stage: InfrastructureStage,
    arm_id: str | None = None,
    policy: str | None = None,
    hidden_world: HiddenWorld | None = None,
) -> InfrastructureEvidence:
    return InfrastructureEvidence(
        scope=scope,
        stage=stage,
        subtype=_subtype(exc, stage=stage),
        exception_type=type(exc).__name__,
        message=str(exc),
        status_code=exc.status_code if isinstance(exc, ModelProviderStatusError) else None,
        attributable_arm_id=arm_id,
        attributable_policy=policy,
        attributable_hidden_world=hidden_world,
        structured_evidence=getattr(exc, "structured_evidence", None),
    )


class _ArmEvidenceClient:
    """Pass through the exact client call once while retaining escaped evidence."""

    def __init__(self, client: ModelClient) -> None:
        self.client = client
        self.invocations: list[dict[str, object]] = []

    @property
    def provider(self) -> str:
        return self.client.provider

    def complete(self, request):
        record = {
            "model_call_index": len(self.invocations),
            "model_request": model_request_as_json(request),
            "model_response": None,
            "rejected_generation": None,
            "boundary_error": None,
        }
        self.invocations.append(record)
        try:
            response = self.client.complete(request)
        except ModelRejectedGenerationError as exc:
            record["rejected_generation"] = rejected_generation_as_json(
                exc, model_call_index=record["model_call_index"], derived_seed=request.model_config.seed
            )
            raise
        except Exception as exc:
            record["boundary_error"] = {
                "exception_type": type(exc).__name__,
                "message": str(exc),
                "structured_evidence": (
                    None if getattr(exc, "structured_evidence", None) is None
                    else thaw_json_value(exc.structured_evidence)
                ),
            }
            raise
        if type(response) is ModelResponse:
            record["model_response"] = model_response_as_json(response)
        return response


def _pre_trace_arm_evidence(prepared, hidden_world, policy, client):
    """Capture authoritative facts without inventing executed-call counters."""

    world = prepared.family.not_executed if hidden_world is HiddenWorld.NOT_EXECUTED else prepared.family.executed_ack_lost
    arm = world.arm_states.exact_replay_state if policy == EXACT_REPLAY else world.arm_states.llm_regeneration_state
    environment = arm.environment
    snapshot = None
    snapshot_hash = None
    commit_ids = None
    capture_error = None
    try:
        snapshot_bytes = environment.snapshot_bytes()
        state = TicketEnvironment.clone_from_snapshot(snapshot_bytes).state
        snapshot = snapshot_bytes.decode("utf-8")
        snapshot_hash = sha256_hex(snapshot_bytes)
        commit_ids = [event.event_id for event in state.mutation_events if event.arm_id == prepared.plan.arm_id(hidden_world, policy) and event.source_stage.value == "RECOVERY"]
    except MemoryError:
        raise
    except Exception as exc:
        capture_error = {"exception_type": type(exc).__name__, "message": str(exc)}
    try:
        dispatch_count = environment.dispatch_count
    except MemoryError:
        raise
    except Exception:
        dispatch_count = None
    return freeze_json_value({
        "evidence_version": "pre-trace-arm-boundary-v1",
        "model_calls_issued": len(client.invocations),
        "model_invocations": client.invocations,
        "executor_dispatch_count": dispatch_count,
        "authoritative_final_state_snapshot": snapshot,
        "authoritative_final_state_sha256": snapshot_hash,
        "recovery_commit_event_ids": commit_ids,
        "state_capture_error": capture_error,
    })


def _arm_failure_from_result(
    *, entry: PaperManifestEntry, hidden_world: HiddenWorld, policy: str, result: RegenerationResult
) -> InfrastructureEvidence:
    error = next(
        invocation.infrastructure_error
        for invocation in result.model_invocations
        if invocation.infrastructure_error is not None
    )
    assert isinstance(error, Exception)
    return _infrastructure(
        error,
        scope=InfrastructureScope.ARM,
        stage=InfrastructureStage.ARM_EXECUTION,
        arm_id=entry.plan.arm_id(hidden_world, policy),
        policy=policy,
        hidden_world=hidden_world,
    )


def _empty_arms(entry: PaperManifestEntry) -> tuple[PaperArmExecution, ...]:
    return tuple(
        PaperArmExecution(
            hidden_world=world,
            policy=policy,
            arm_id=entry.plan.arm_id(world, policy),
            attempted=False,
            status=ArmOpportunityStatus.NOT_ACTIVATED,
            result=None,
            infrastructure_failure=None,
        )
        for world in entry.plan.hidden_world_order
        for policy in entry.plan.arm_order(world)
    )


def _failed_before_original(
    entry: PaperManifestEntry, evidence: InfrastructureEvidence
) -> PaperScheduledAttemptExecution:
    return PaperScheduledAttemptExecution(
        entry=entry,
        attempt_started=True,
        original_generation_attempted=False,
        eligibility_outcome=EligibilityOutcome.NOT_REACHED,
        original_generation=None,
        original_generation_infrastructure=None,
        trial_family_activated=False,
        family_id=None,
        recovery_construction_started=False,
        prepared=None,
        family_system_failure=evidence,
        arm_executions=_empty_arms(entry),
        terminal_status=ScheduledAttemptStatus.FAMILY_SYSTEM_FAILURE,
    )


def _execute_slot(
    entry: PaperManifestEntry,
    client: ModelClient,
    emit: Callable[..., None],
) -> PaperScheduledAttemptExecution:
    emit("ATTEMPT_STARTED", entry=entry)
    try:
        initial_state = TicketEnvironment.empty()
    except MemoryError:
        raise
    except Exception as exc:
        return _failed_before_original(
            entry,
            _infrastructure(exc, scope=InfrastructureScope.FAMILY_SYSTEM, stage=InfrastructureStage.ENVIRONMENT_SETUP),
        )

    emit("ORIGINAL_GENERATION_ATTEMPT_STARTED", entry=entry)
    try:
        original = run_v1_original_generation_attempt(
            client,
            task_spec=entry.plan.task_spec,
            model_config=entry.original_generation_config,
        )
    except MemoryError:
        raise
    except Exception as exc:
        evidence = _infrastructure(
            exc,
            scope=InfrastructureScope.ORIGINAL_GENERATION,
            stage=InfrastructureStage.ORIGINAL_GENERATION,
        )
        return PaperScheduledAttemptExecution(
            entry=entry,
            attempt_started=True,
            original_generation_attempted=True,
            eligibility_outcome=EligibilityOutcome.INFRASTRUCTURE_FAILURE,
            original_generation=None,
            original_generation_infrastructure=evidence,
            trial_family_activated=False,
            family_id=None,
            recovery_construction_started=False,
            prepared=None,
            family_system_failure=None,
            arm_executions=_empty_arms(entry),
            terminal_status=ScheduledAttemptStatus.ORIGINAL_GENERATION_INFRASTRUCTURE_FAILURE,
        )
    if type(original) is OriginalGenerationBehavioralFailure:
        return PaperScheduledAttemptExecution(
            entry=entry,
            attempt_started=True,
            original_generation_attempted=True,
            eligibility_outcome=EligibilityOutcome.INELIGIBLE_BEHAVIORAL,
            original_generation=original,
            original_generation_infrastructure=None,
            trial_family_activated=False,
            family_id=None,
            recovery_construction_started=False,
            prepared=None,
            family_system_failure=None,
            arm_executions=_empty_arms(entry),
            terminal_status=ScheduledAttemptStatus.INELIGIBLE,
        )
    if type(original) is not EligibleOriginalGeneration:
        raise PaperCollectionError("original-generation boundary returned an unknown type")

    emit("RECOVERY_CONSTRUCTION_STARTED", entry=entry)
    try:
        prepared = prepare_eligible_scheduled_trial(
            plan=entry.plan,
            original_generation=original,
            initial_state=initial_state,
        )
    except MemoryError:
        raise
    except Exception as exc:
        evidence = _infrastructure(
            exc,
            scope=InfrastructureScope.FAMILY_SYSTEM,
            stage=(
                InfrastructureStage.REGENERATION_CONTEXT_CONSTRUCTION
                if isinstance(exc, RegenerationContextProtocolError)
                else InfrastructureStage.FAMILY_CONSTRUCTION
            ),
        )
        return PaperScheduledAttemptExecution(
            entry=entry,
            attempt_started=True,
            original_generation_attempted=True,
            eligibility_outcome=EligibilityOutcome.ELIGIBLE,
            original_generation=original,
            original_generation_infrastructure=None,
            trial_family_activated=False,
            family_id=None,
            recovery_construction_started=True,
            prepared=None,
            family_system_failure=evidence,
            arm_executions=_empty_arms(entry),
            terminal_status=ScheduledAttemptStatus.FAMILY_SYSTEM_FAILURE,
        )

    arms: list[PaperArmExecution] = []
    for hidden_world in entry.plan.hidden_world_order:
        for policy in entry.plan.arm_order(hidden_world):
            arm_id = entry.plan.arm_id(hidden_world, policy)
            emit("ARM_OPPORTUNITY_ATTEMPT_STARTED", entry=entry, arm_id=arm_id)
            arm_client = _ArmEvidenceClient(client)
            try:
                result = execute_prepared_recovery_arm(
                    prepared,
                    hidden_world=hidden_world,
                    policy=policy,
                    client=arm_client,
                    regeneration_config=entry.regeneration_config,
                )
            except MemoryError:
                raise
            except Exception as exc:
                evidence = _infrastructure(
                    exc,
                    scope=InfrastructureScope.ARM,
                    stage=InfrastructureStage.ARM_EXECUTION,
                    arm_id=arm_id,
                    policy=policy,
                    hidden_world=hidden_world,
                )
                arms.append(
                    PaperArmExecution(
                        hidden_world=hidden_world,
                        policy=policy,
                        arm_id=arm_id,
                        attempted=True,
                        status=ArmOpportunityStatus.INFRASTRUCTURE_FAILURE_BEFORE_TRACE,
                        result=None,
                        infrastructure_failure=evidence,
                        pre_trace_evidence=_pre_trace_arm_evidence(prepared, hidden_world, policy, arm_client),
                    )
                )
                continue
            if type(result) is RegenerationResult and result.termination_reason == INFRASTRUCTURE_FAILURE:
                status = ArmOpportunityStatus.INFRASTRUCTURE_FAILURE_WITH_TRACE
                evidence = _arm_failure_from_result(
                    entry=entry, hidden_world=hidden_world, policy=policy, result=result
                )
            else:
                status = ArmOpportunityStatus.COMPLETED_TRACE
                evidence = None
            arms.append(
                PaperArmExecution(
                    hidden_world=hidden_world,
                    policy=policy,
                    arm_id=arm_id,
                    attempted=True,
                    status=status,
                    result=result,
                    infrastructure_failure=evidence,
                )
            )
    any_arm_failure = any(item.infrastructure_failure is not None for item in arms)
    return PaperScheduledAttemptExecution(
        entry=entry,
        attempt_started=True,
        original_generation_attempted=True,
        eligibility_outcome=EligibilityOutcome.ELIGIBLE,
        original_generation=original,
        original_generation_infrastructure=None,
        trial_family_activated=True,
        family_id=entry.plan.trial_family_id,
        recovery_construction_started=True,
        prepared=prepared,
        family_system_failure=None,
        arm_executions=tuple(arms),
        terminal_status=(
            ScheduledAttemptStatus.RECOVERY_COMPLETE_WITH_ARM_INFRASTRUCTURE
            if any_arm_failure
            else ScheduledAttemptStatus.RECOVERY_COMPLETE
        ),
    )


def _summary(outcomes: tuple[PaperScheduledAttemptExecution, ...]) -> PaperCollectionSummary:
    arms = [arm for outcome in outcomes for arm in outcome.arm_executions if outcome.trial_family_activated]
    return PaperCollectionSummary(
        scheduled_attempts=len(outcomes),
        attempts_started=sum(item.attempt_started for item in outcomes),
        original_generations_attempted=sum(item.original_generation_attempted for item in outcomes),
        eligible_original_generations=sum(item.eligibility_outcome is EligibilityOutcome.ELIGIBLE for item in outcomes),
        ineligible_attempts=sum(item.eligibility_outcome is EligibilityOutcome.INELIGIBLE_BEHAVIORAL for item in outcomes),
        original_generation_infrastructure_failures=sum(item.eligibility_outcome is EligibilityOutcome.INFRASTRUCTURE_FAILURE for item in outcomes),
        activated_families=sum(item.trial_family_activated for item in outcomes),
        arm_opportunities=len(arms),
        arm_opportunities_attempted=sum(item.attempted for item in arms),
        arm_traces_collected=sum(item.result is not None for item in arms),
        arm_level_infrastructure_failures=sum(item.infrastructure_failure is not None for item in arms),
        system_family_construction_failures=sum(item.family_system_failure is not None for item in outcomes),
        completion_status=CollectionCompletionStatus.COMPLETE_RECORDED,
    )


def execute_paper_collection(
    manifest: PaperExperimentManifest,
    client: ModelClient,
    *,
    event_sink: Callable[[dict[str, object]], None] | None = None,
    scheduled_attempt_sink: Callable[[PaperScheduledAttemptExecution], None] | None = None,
) -> PaperCollectionResult:
    """Attempt every paper slot once, serially, in manifest order."""

    validate_paper_manifest_provider(manifest, client)
    manifest_hash = manifest.manifest_hash
    events: list[dict[str, object]] = []
    outcomes_list: list[PaperScheduledAttemptExecution] = []

    def emit(event_type: str, *, entry: PaperManifestEntry, arm_id=None, terminal_status=None) -> None:
        event = {
            "schema_version": "paper-collection-event-v1",
            "event_sequence": len(events) + 1,
            "manifest_id": manifest.manifest_id,
            "manifest_sha256": manifest_hash,
            "paper_experiment_revision": PAPER_EXPERIMENT_REVISION,
            "execution_semantics_revision": INHERITED_EXECUTION_REVISION,
            "slot_index": entry.scheduled_attempt_index,
            "event_type": event_type,
            "arm_id": arm_id,
            "terminal_status": terminal_status,
        }
        if event_sink is not None:
            try:
                event_sink(event)
            except Exception as exc:
                raise PaperCollectionFatalError(
                    "scheduled-opportunity journal failed; safe continuation is impossible",
                    evidence=_infrastructure(exc, scope=InfrastructureScope.PERSISTENCE, stage=InfrastructureStage.PERSISTENCE),
                ) from exc
        events.append(event)

    for entry in manifest.entries:
        try:
            outcome = _execute_slot(entry, client, emit)
            if scheduled_attempt_sink is not None:
                try:
                    scheduled_attempt_sink(outcome)
                except Exception as exc:
                    raise PaperCollectionFatalError(
                        "scheduled-attempt persistence failed; safe continuation is impossible",
                        evidence=_infrastructure(exc, scope=InfrastructureScope.PERSISTENCE, stage=InfrastructureStage.PERSISTENCE),
                    ) from exc
            emit("SCHEDULED_ATTEMPT_TERMINATED", entry=entry, terminal_status=outcome.terminal_status.value)
        except PaperCollectionFatalError as exc:
            exc.completed_slot_outcomes = tuple(outcomes_list)
            exc.active_slot_index = entry.scheduled_attempt_index
            raise
        except Exception as exc:
            fatal = PaperCollectionFatalError(
                "runner evidence corruption; safe continuation is impossible",
                evidence=_infrastructure(exc, scope=InfrastructureScope.FAMILY_SYSTEM, stage=InfrastructureStage.TRACE_SERIALIZATION),
            )
            fatal.completed_slot_outcomes = tuple(outcomes_list)
            fatal.active_slot_index = entry.scheduled_attempt_index
            raise fatal from exc
        outcomes_list.append(outcome)
    outcomes = tuple(outcomes_list)
    if len(outcomes) != PAPER_SLOT_COUNT:
        raise PaperCollectionError("runner did not retain all 160 scheduled slots")
    return PaperCollectionResult(
        manifest_id=manifest.manifest_id,
        manifest_hash=manifest_hash,
        slot_outcomes=outcomes,
        summary=_summary(outcomes),
        collection_events=tuple(events),
    )


def _infrastructure_as_json(evidence: InfrastructureEvidence | None) -> dict[str, object] | None:
    if evidence is None:
        return None
    return {
        "scope": evidence.scope.value,
        "stage": evidence.stage.value,
        "subtype": evidence.subtype.value,
        "policy_attributable": evidence.policy_attributable,
        "attributable_arm_id": evidence.attributable_arm_id,
        "attributable_policy": evidence.attributable_policy,
        "attributable_hidden_world": None if evidence.attributable_hidden_world is None else evidence.attributable_hidden_world.value,
        "diagnostic": {
            "exception_type": evidence.exception_type,
            "message": evidence.message,
            "status_code": evidence.status_code,
            "structured_evidence": (
                None if evidence.structured_evidence is None else thaw_json_value(evidence.structured_evidence)
            ),
        },
    }


def _original_as_json(execution: PaperScheduledAttemptExecution) -> dict[str, object]:
    entry = execution.entry
    generated = execution.original_generation
    request = (
        generated.model_request
        if generated is not None
        else build_v1_original_generation_request(
            task_spec=entry.plan.task_spec,
            model_config=entry.original_generation_config,
        )
    )
    return {
        "model_request": model_request_as_json(request),
        "model_response": (
            None if generated is None or generated.model_response is None else model_response_as_json(generated.model_response)
        ),
        "rejected_generation": (
            None
            if generated is None or getattr(generated, "rejected_generation", None) is None
            else rejected_generation_as_json(
                generated.rejected_generation,
                model_call_index=0,
                derived_seed=entry.original_generation_config.seed,
            )
        ),
    }


def scheduled_paper_attempt_as_json(
    execution: PaperScheduledAttemptExecution, manifest_hash: str
) -> dict[str, object]:
    entry = execution.entry
    behavioral = execution.original_generation if type(execution.original_generation) is OriginalGenerationBehavioralFailure else None
    return {
        "schema_version": PAPER_LEDGER_SCHEMA_VERSION,
        "manifest_id": entry.plan.manifest_id,
        "manifest_sha256": manifest_hash,
        "paper_experiment_revision": PAPER_EXPERIMENT_REVISION,
        "execution_semantics_revision": INHERITED_EXECUTION_REVISION,
        "manifest_kind": "paper",
        "slot_index": entry.scheduled_attempt_index,
        "replicate": entry.replicate,
        "scenario_id": entry.scenario_id,
        "stratum": entry.schedule_stratum.value,
        "model_config_id": entry.model_config.model_config_id,
        "original_generation_seed": entry.original_generation_config.seed,
        "regeneration_base_seed": entry.regeneration_config.seed,
        "provider": entry.model_config.model.provider,
        "requested_model": entry.model_config.model.name,
        "attempt_started": execution.attempt_started,
        "original_generation_attempted": execution.original_generation_attempted,
        "eligibility": {
            "taxonomy_version": "original-generation-eligibility-v1",
            "outcome": execution.eligibility_outcome.value,
            "ineligibility_reason": None if behavioral is None else behavioral.reason.value,
            "detail": None if behavioral is None else behavioral.detail,
        },
        "original_generation_evidence": _original_as_json(execution) if execution.original_generation_attempted else None,
        "original_generation_infrastructure": _infrastructure_as_json(execution.original_generation_infrastructure),
        "reserved_base_trial_id": entry.plan.base_trial_id,
        "reserved_trial_family_id": entry.plan.trial_family_id,
        "trial_family_activated": execution.trial_family_activated,
        "family_id": execution.family_id,
        "recovery_construction_started": execution.recovery_construction_started,
        "expected_arm_opportunities_attempted": execution.expected_arm_opportunities_attempted,
        "family_system_failure": _infrastructure_as_json(execution.family_system_failure),
        "arm_opportunities": [
            {
                "arm_id": arm.arm_id,
                "hidden_world": arm.hidden_world.value,
                "policy": arm.policy,
                "attempted": arm.attempted,
                "status": arm.status.value,
                "trace_expected": arm.result is not None,
                "infrastructure_failure": _infrastructure_as_json(arm.infrastructure_failure),
                "pre_trace_evidence": None if arm.pre_trace_evidence is None else thaw_json_value(arm.pre_trace_evidence),
            }
            for arm in execution.arm_executions
        ],
        "terminal_status": execution.terminal_status.value,
    }


def paper_arm_traces_as_json(
    result: PaperCollectionResult, metadata: TraceRunMetadata
) -> tuple[dict[str, object], ...]:
    return _outcome_arm_traces_as_json(result.slot_outcomes, metadata)


def _outcome_arm_traces_as_json(outcomes, metadata):
    traces: list[dict[str, object]] = []
    for outcome in outcomes:
        if outcome.prepared is None:
            continue
        for arm in outcome.arm_executions:
            if arm.result is None:
                continue
            traces.append(
                paper_arm_trace_as_json(
                    entry=outcome.entry,
                    prepared=outcome.prepared,
                    hidden_world=arm.hidden_world,
                    policy=arm.policy,
                    arm_result=arm.result,
                    metadata=metadata,
                )
            )
    return tuple(traces)


def paper_summary_as_json(result: PaperCollectionResult) -> dict[str, object]:
    summary = result.summary
    return {
        "schema_version": PAPER_SUMMARY_SCHEMA_VERSION,
        "manifest_id": result.manifest_id,
        "manifest_sha256": result.manifest_hash,
        "paper_experiment_revision": PAPER_EXPERIMENT_REVISION,
        "execution_semantics_revision": INHERITED_EXECUTION_REVISION,
        "manifest_kind": "paper",
        "model_identities": [json.loads(value) for value in sorted({
            canonical_json_bytes(item.entry.model_config.model.as_trace_model())
            for item in result.slot_outcomes
        })],
        "scheduled_attempts": summary.scheduled_attempts,
        "attempts_started": summary.attempts_started,
        "original_generations_attempted": summary.original_generations_attempted,
        "eligible_original_generations": summary.eligible_original_generations,
        "ineligible_attempts": summary.ineligible_attempts,
        "original_generation_infrastructure_failures": summary.original_generation_infrastructure_failures,
        "activated_families": summary.activated_families,
        "arm_opportunities": summary.arm_opportunities,
        "arm_opportunities_attempted": summary.arm_opportunities_attempted,
        "arm_traces_persisted": summary.arm_traces_collected,
        "arm_level_infrastructure_failures": summary.arm_level_infrastructure_failures,
        "system_family_construction_failures": summary.system_family_construction_failures,
        "completion_status": summary.completion_status.value,
        "collection_events": len(result.collection_events),
        "collection_events_sha256": sha256_hex(_jsonl(result.collection_events)),
    }


def _jsonl(records: tuple[dict[str, object], ...]) -> bytes:
    return b"".join(canonical_json_bytes(record) + b"\n" for record in records)


def _write_bytes(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _load_schema(path: Path) -> dict[str, object]:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        return schema
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise PaperCollectionError(f"evidence schema could not be loaded: {exc}") from exc


def _run_metadata_as_json(
    manifest: PaperExperimentManifest, metadata: TraceRunMetadata
) -> dict[str, object]:
    if type(metadata) is not TraceRunMetadata:
        raise PaperCollectionPreflightError("run metadata must be TraceRunMetadata")
    record = {
        "schema_version": "paper-run-metadata-v1",
        "manifest_id": manifest.manifest_id,
        "manifest_sha256": manifest.manifest_hash,
        "paper_experiment_revision": PAPER_EXPERIMENT_REVISION,
        "execution_semantics_revision": INHERITED_EXECUTION_REVISION,
        "git_commit": metadata.git_commit,
        "timestamp": metadata.timestamp,
    }
    _validate_run_metadata(record)
    return record


def _validate_run_metadata(record: dict[str, object]) -> None:
    jsonschema.Draft202012Validator(
        _load_schema(_RUN_METADATA_SCHEMA_PATH),
        format_checker=jsonschema.FormatChecker(),
    ).validate(record)
    # Reuse the exact frozen trace rules, including strict RFC3339 syntax.
    TraceRunMetadata(git_commit=record["git_commit"], timestamp=record["timestamp"])


def _validate_records(
    attempts: tuple[dict[str, object], ...],
    traces: tuple[dict[str, object], ...],
    events: tuple[dict[str, object], ...],
) -> None:
    ledger_validator = jsonschema.Draft202012Validator(_load_schema(_LEDGER_SCHEMA_PATH))
    frozen_schema = _load_schema(_TRACE_SCHEMA_PATH)
    registry = Registry().with_resource(frozen_schema["$id"], Resource.from_contents(frozen_schema))
    trace_validator = jsonschema.Draft202012Validator(
        _load_schema(_PAPER_TRACE_SCHEMA_PATH),
        registry=registry,
        format_checker=jsonschema.FormatChecker(),
    )
    for record in attempts:
        ledger_validator.validate(record)
    event_validator = jsonschema.Draft202012Validator(_load_schema(_EVENT_SCHEMA_PATH))
    for event in events:
        event_validator.validate(event)
    for trace in traces:
        if not is_trace_datetime(trace.get("timestamp")):
            raise TraceSerializationError("paper arm trace timestamp is invalid")
        trace_validator.validate(trace)


def _validate_result_coherence(
    manifest: PaperExperimentManifest, result: PaperCollectionResult
) -> None:
    if type(manifest) is not PaperExperimentManifest or type(result) is not PaperCollectionResult:
        raise PaperCollectionError("manifest/result has the wrong type")
    if result.manifest_id != manifest.manifest_id or result.manifest_hash != manifest.manifest_hash:
        raise PaperCollectionError("manifest/result identity is incoherent")
    if sha256_hex(manifest.canonical_bytes) != manifest.manifest_hash:
        raise PaperCollectionError("manifest hash is incoherent")
    if len(result.slot_outcomes) != PAPER_SLOT_COUNT:
        raise PaperCollectionError("paper result must retain exactly 160 slots")
    for index, (outcome, entry) in enumerate(zip(result.slot_outcomes, manifest.entries, strict=True)):
        if outcome.entry != entry or entry.scheduled_attempt_index != index:
            raise PaperCollectionError("paper result slot order does not match manifest")
        if len({arm.arm_id for arm in outcome.arm_executions}) != 4:
            raise PaperCollectionError("scheduled attempt has duplicate arm IDs")
        outcome.__post_init__()
        if outcome.original_generation is not None:
            response = outcome.original_generation.model_response
            if response is not None and (
                response.provider != entry.model_config.model.provider
                or response.requested_model != entry.model_config.model.name
            ):
                raise PaperCollectionError("original response provider/model identity is incoherent")
        for arm in outcome.arm_executions:
            arm.__post_init__()
            if arm.result is None:
                continue
            if outcome.prepared is None:
                raise PaperCollectionError("arm result lacks prepared family evidence")
            arm_result = arm.result
            if sha256_hex(arm_result.final_state_snapshot) != arm_result.final_state_hash:
                raise PaperCollectionError("arm final-state hash is incoherent")
            intended = entry.plan.task_spec.expected_arguments
            state = TicketEnvironment.clone_from_snapshot(arm_result.final_state_snapshot).state
            recomputed = evaluate_ticket_state(
                state,
                customer_id=intended.customer_id,
                title=intended.title,
                description=intended.description,
                infrastructure_failure=arm_result.evaluation.infrastructure_failure,
                infrastructure_failure_reasons=arm_result.evaluation.exclusion_reasons,
            )
            if recomputed != arm_result.evaluation:
                raise PaperCollectionError("arm evaluation is incoherent with retained state")
            if type(arm_result) is ExactReplayResult:
                if arm_result.request_hash != outcome.prepared.original_generation.original_request_hash:
                    raise PaperCollectionError("Replay does not identify the family's frozen request")
            else:
                if arm_result.arm_id != arm.arm_id:
                    raise PaperCollectionError("Regeneration result has the wrong arm ID")
                for invocation in arm_result.model_invocations:
                    seed = None if entry.regeneration_config.seed is None else entry.regeneration_config.seed + invocation.model_call_index
                    config = replace(entry.regeneration_config, seed=seed)
                    if invocation.derived_seed != seed or invocation.model_request.model_config != config:
                        raise PaperCollectionError("Regeneration configuration/seed evidence is incoherent")
                    if invocation.model_call_index == 0 and invocation.model_request != model_request_from_regeneration_context(outcome.prepared.regeneration_context, config):
                        raise PaperCollectionError("initial Regeneration context is incoherent")
                    if invocation.model_response is not None and (
                        invocation.model_response.provider != entry.model_config.model.provider
                        or invocation.model_response.requested_model != entry.model_config.model.name
                    ):
                        raise PaperCollectionError("Regeneration response identity is incoherent")
            if arm_result.evaluation.infrastructure_failure != (arm.infrastructure_failure is not None):
                raise PaperCollectionError("arm infrastructure status is incoherent")
    if result.summary != _summary(result.slot_outcomes):
        raise PaperCollectionError("paper collection summary is incoherent")


def _ledger_counts(attempts: tuple[dict[str, object], ...]) -> dict[str, int]:
    active_arms = [
        arm for attempt in attempts if attempt["trial_family_activated"]
        for arm in attempt["arm_opportunities"]
    ]
    return {
        "scheduled_attempts": len(attempts),
        "attempts_started": sum(attempt["attempt_started"] for attempt in attempts),
        "original_generations_attempted": sum(attempt["original_generation_attempted"] for attempt in attempts),
        "eligible_original_generations": sum(attempt["eligibility"]["outcome"] == "ELIGIBLE" for attempt in attempts),
        "ineligible_attempts": sum(attempt["eligibility"]["outcome"] == "INELIGIBLE_BEHAVIORAL" for attempt in attempts),
        "original_generation_infrastructure_failures": sum(attempt["original_generation_infrastructure"] is not None for attempt in attempts),
        "activated_families": sum(attempt["trial_family_activated"] for attempt in attempts),
        "arm_opportunities": len(active_arms),
        "arm_opportunities_attempted": sum(arm["attempted"] for arm in active_arms),
        "arm_traces_persisted": sum(arm["trace_expected"] for arm in active_arms),
        "arm_level_infrastructure_failures": sum(arm["infrastructure_failure"] is not None for arm in active_arms),
        "system_family_construction_failures": sum(attempt["family_system_failure"] is not None for attempt in attempts),
    }


def _validate_bundle_data(
    *,
    manifest_json: dict[str, object],
    manifest_hash: str,
    attempts: tuple[dict[str, object], ...],
    traces: tuple[dict[str, object], ...],
    summary: dict[str, object],
    events: tuple[dict[str, object], ...],
    run_metadata: dict[str, object],
) -> None:
    """Cross-check all authoritative bundle identities and operational counts."""

    jsonschema.Draft202012Validator(_load_schema(_SUMMARY_SCHEMA_PATH)).validate(summary)
    _validate_run_metadata(run_metadata)
    if (
        run_metadata["manifest_id"] != manifest_json["manifest_id"]
        or run_metadata["manifest_sha256"] != manifest_hash
        or run_metadata["paper_experiment_revision"] != PAPER_EXPERIMENT_REVISION
        or run_metadata["execution_semantics_revision"] != INHERITED_EXECUTION_REVISION
    ):
        raise PaperCollectionError("run metadata manifest/revision identity is incoherent")

    if (
        manifest_json.get("manifest_kind") != "paper"
        or manifest_json.get("paper_experiment_revision") != PAPER_EXPERIMENT_REVISION
        or manifest_json.get("execution_semantics_revision") != INHERITED_EXECUTION_REVISION
    ):
        raise PaperCollectionError("manifest paper/execution revision identity is incoherent")
    entries = manifest_json.get("entries", [])
    if len(entries) != PAPER_SLOT_COUNT or len(attempts) != PAPER_SLOT_COUNT:
        raise PaperCollectionError("manifest/ledger population must be exactly 160")
    if [item["slot_index"] for item in attempts] != list(range(PAPER_SLOT_COUNT)):
        raise PaperCollectionError("scheduled ledger slot order is incoherent")
    manifest_id = manifest_json["manifest_id"]
    expected_trace_ids: list[str] = []
    trace_links: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
    for index, (entry, attempt) in enumerate(zip(entries, attempts, strict=True)):
        replicate, scenario_id = paper_queue()[index]
        if entry["scheduled_attempt_index"] != index or entry["replicate"] != replicate or entry["scenario"]["scenario_id"] != scenario_id:
            raise PaperCollectionError("manifest frozen scenario/replicate queue is incoherent")
        if entry["schedule_stratum"] != paper_stratum_for(replicate, scenario_id).value:
            raise PaperCollectionError("manifest frozen stratum schedule is incoherent")
        hidden, h0, h1, hidden_bit, policy_bit = _orders_for_stratum(paper_stratum_for(replicate, scenario_id))
        plan = entry["scheduled_trial_plan"]
        if (
            plan["hidden_world_order"] != [world.value for world in hidden]
            or plan["h0_arm_order"] != list(h0) or plan["h1_arm_order"] != list(h1)
            or plan["manifest_id"] != manifest_json["manifest_id"]
            or plan["scenario_id"] != scenario_id or plan["scheduled_attempt_ordinal"] != index
            or entry["hidden_world_orientation_bit"] != hidden_bit
            or entry["policy_orientation_bit"] != policy_bit
        ):
            raise PaperCollectionError("manifest frozen execution order is incoherent")
        config = entry["model_config"]
        if config["original_generation"]["seed"] != 30_000 + index or config["regeneration"]["seed"] != 40_000 + 10 * index:
            raise PaperCollectionError("manifest frozen paper seed schedule is incoherent")
        expected = {
            "manifest_id": manifest_id,
            "manifest_sha256": manifest_hash,
            "paper_experiment_revision": PAPER_EXPERIMENT_REVISION,
            "execution_semantics_revision": INHERITED_EXECUTION_REVISION,
            "manifest_kind": "paper",
            "slot_index": index,
            "replicate": replicate,
            "scenario_id": scenario_id,
            "stratum": entry["schedule_stratum"],
            "model_config_id": config["model_config_id"],
            "original_generation_seed": config["original_generation"]["seed"],
            "regeneration_base_seed": config["regeneration"]["seed"],
            "provider": config["model"]["provider"],
            "requested_model": config["model"]["name"],
        }
        if any(attempt[key] != value for key, value in expected.items()):
            raise PaperCollectionError("scheduled ledger identity/configuration does not match manifest")
        base_id = f"bt-{manifest_id}-{index:06d}"
        family_id = f"family-{base_id}"
        if attempt["reserved_base_trial_id"] != base_id or attempt["reserved_trial_family_id"] != family_id:
            raise PaperCollectionError("reserved family identifier linkage is incoherent")
        activated = attempt["trial_family_activated"]
        eligibility = attempt["eligibility"]
        outcome = eligibility["outcome"]
        original_attempted = attempt["original_generation_attempted"]
        original_failure = attempt["original_generation_infrastructure"] is not None
        system_failure = attempt["family_system_failure"] is not None
        if (
            not attempt["attempt_started"]
            or original_attempted != (outcome != EligibilityOutcome.NOT_REACHED.value)
            or (attempt["original_generation_evidence"] is not None) != original_attempted
            or original_failure != (outcome == EligibilityOutcome.INFRASTRUCTURE_FAILURE.value)
            or (eligibility["ineligibility_reason"] is not None) != (outcome == EligibilityOutcome.INELIGIBLE_BEHAVIORAL.value)
            or attempt["recovery_construction_started"] != (outcome == EligibilityOutcome.ELIGIBLE.value)
            or activated != (outcome == EligibilityOutcome.ELIGIBLE.value and not system_failure)
            or system_failure != (outcome == EligibilityOutcome.NOT_REACHED.value or outcome == EligibilityOutcome.ELIGIBLE.value and not activated)
        ):
            raise PaperCollectionError("scheduled eligibility/construction evidence is incoherent")
        expected_terminal = (
            ScheduledAttemptStatus.INELIGIBLE.value if outcome == EligibilityOutcome.INELIGIBLE_BEHAVIORAL.value
            else ScheduledAttemptStatus.ORIGINAL_GENERATION_INFRASTRUCTURE_FAILURE.value if original_failure
            else ScheduledAttemptStatus.FAMILY_SYSTEM_FAILURE.value if system_failure
            else ScheduledAttemptStatus.RECOVERY_COMPLETE_WITH_ARM_INFRASTRUCTURE.value if any(arm["infrastructure_failure"] is not None for arm in attempt["arm_opportunities"])
            else ScheduledAttemptStatus.RECOVERY_COMPLETE.value
        )
        if attempt["terminal_status"] != expected_terminal:
            raise PaperCollectionError("scheduled terminal status is incoherent")
        if attempt["family_id"] != (family_id if activated else None):
            raise PaperCollectionError("activated family identifier linkage is incoherent")
        plan = entry["scheduled_trial_plan"]
        expected_arms = []
        for world in plan["hidden_world_order"]:
            world_suffix = "H0" if world == HiddenWorld.NOT_EXECUTED.value else "H1"
            order = plan["h0_arm_order"] if world_suffix == "H0" else plan["h1_arm_order"]
            for policy in order:
                arm_suffix = "P1" if policy == EXACT_REPLAY else "P2"
                expected_arms.append((f"pair-{family_id}-{world_suffix}:{arm_suffix}", world, policy))
        arms = attempt["arm_opportunities"]
        if [(arm["arm_id"], arm["hidden_world"], arm["policy"]) for arm in arms] != expected_arms:
            raise PaperCollectionError("arm opportunity order/IDs do not match manifest")
        if attempt["expected_arm_opportunities_attempted"] != (activated and all(arm["attempted"] for arm in arms)):
            raise PaperCollectionError("expected arm-attempt status is incoherent")
        for arm in arms:
            status = arm["status"]
            trace_expected = status in (
                ArmOpportunityStatus.COMPLETED_TRACE.value,
                ArmOpportunityStatus.INFRASTRUCTURE_FAILURE_WITH_TRACE.value,
            )
            has_failure = status in (
                ArmOpportunityStatus.INFRASTRUCTURE_FAILURE_WITH_TRACE.value,
                ArmOpportunityStatus.INFRASTRUCTURE_FAILURE_BEFORE_TRACE.value,
            )
            if arm["attempted"] != activated or arm["trace_expected"] != trace_expected or (arm["infrastructure_failure"] is not None) != has_failure:
                raise PaperCollectionError("arm opportunity status is incoherent")
            if not activated and status != ArmOpportunityStatus.NOT_ACTIVATED.value:
                raise PaperCollectionError("non-activated family fabricates an arm outcome")
            failure = arm["infrastructure_failure"]
            if failure is not None and (
                failure["scope"] != "ARM" or not failure["policy_attributable"]
                or failure["attributable_arm_id"] != arm["arm_id"]
                or failure["attributable_policy"] != arm["policy"]
                or failure["attributable_hidden_world"] != arm["hidden_world"]
            ):
                raise PaperCollectionError("arm infrastructure attribution is incoherent")
            pre_trace = arm["pre_trace_evidence"]
            if (pre_trace is not None) != (status == ArmOpportunityStatus.INFRASTRUCTURE_FAILURE_BEFORE_TRACE.value):
                raise PaperCollectionError("absent arm trace boundary evidence is incoherent")
            if pre_trace is not None:
                snapshot = pre_trace["authoritative_final_state_snapshot"]
                snapshot_hash = pre_trace["authoritative_final_state_sha256"]
                if pre_trace["model_calls_issued"] != len(pre_trace["model_invocations"]):
                    raise PaperCollectionError("pre-trace model-call evidence is incoherent")
                if snapshot is None:
                    if snapshot_hash is not None or pre_trace["recovery_commit_event_ids"] is not None or pre_trace["state_capture_error"] is None:
                        raise PaperCollectionError("pre-trace missing snapshot evidence is incoherent")
                else:
                    state = TicketEnvironment.clone_from_snapshot(snapshot.encode("utf-8")).state
                    commits = [event.event_id for event in state.mutation_events if event.arm_id == arm["arm_id"] and event.source_stage.value == "RECOVERY"]
                    if snapshot_hash != sha256_hex(snapshot.encode("utf-8")) or commits != pre_trace["recovery_commit_event_ids"] or pre_trace["state_capture_error"] is not None:
                        raise PaperCollectionError("pre-trace authoritative state evidence is incoherent")
            if trace_expected:
                expected_trace_ids.append(arm["arm_id"])
                trace_links[arm["arm_id"]] = (attempt, config)
        for field, scope in (("original_generation_infrastructure", "ORIGINAL_GENERATION"), ("family_system_failure", "FAMILY_SYSTEM")):
            failure = attempt[field]
            if failure is not None and (
                failure["scope"] != scope or failure["policy_attributable"]
                or any(failure[key] is not None for key in (
                    "attributable_arm_id", "attributable_policy", "attributable_hidden_world"
                ))
            ):
                raise PaperCollectionError("pre-arm infrastructure fabricates policy attribution")
    trace_ids = [trace["identifiers"]["arm_id"] for trace in traces]
    if len(expected_trace_ids) != len(set(expected_trace_ids)) or len(trace_ids) != len(set(trace_ids)):
        raise PaperCollectionError("duplicate arm ID in paper bundle")
    if trace_ids != expected_trace_ids:
        raise PaperCollectionError("arm trace linkage/order is incoherent")
    for trace in traces:
        attempt, config = trace_links[trace["identifiers"]["arm_id"]]
        linked_arm = next(arm for arm in attempt["arm_opportunities"] if arm["arm_id"] == trace["identifiers"]["arm_id"])
        if (
            trace["git_commit"] != run_metadata["git_commit"]
            or trace["timestamp"] != run_metadata["timestamp"]
            or trace["identifiers"]["manifest_id"] != manifest_id
            or trace["identifiers"]["trial_family_id"] != attempt["family_id"]
            or trace["identifiers"]["base_trial_id"] != attempt["reserved_base_trial_id"]
            or trace["identifiers"]["scenario_id"] != attempt["scenario_id"]
            or trace["model"] != config["model"]
            or trace["sampling"]["model_config_id"] != config["model_config_id"]
            or trace["sampling"]["original_generation"] != config["original_generation"]
            or (trace["recovery_policy"] == LLM_REGENERATION and trace["sampling"]["regeneration"] != config["regeneration"])
            or trace["recovery_policy"] != linked_arm["policy"]
            or trace["evaluator_only"]["hidden_world"] != linked_arm["hidden_world"]
            or trace["evaluator_only"]["evaluation"]["infrastructure_failure"] != (linked_arm["infrastructure_failure"] is not None)
            or trace["identifiers"]["pair_id"] != linked_arm["arm_id"].split(":")[0]
            or trace["identifiers"]["run_id"] != f"run-{linked_arm['arm_id']}"
        ):
            raise PaperCollectionError("arm trace identity/configuration is incoherent")
    for key, value in _ledger_counts(attempts).items():
        if summary.get(key) != value:
            raise PaperCollectionError(f"bundle summary count {key} is incoherent")
    if (
        summary.get("schema_version") != PAPER_SUMMARY_SCHEMA_VERSION
        or summary.get("manifest_id") != manifest_id
        or summary.get("manifest_sha256") != manifest_hash
        or summary.get("paper_experiment_revision") != PAPER_EXPERIMENT_REVISION
        or summary.get("execution_semantics_revision") != INHERITED_EXECUTION_REVISION
        or summary.get("manifest_kind") != "paper"
        or summary.get("completion_status") != CollectionCompletionStatus.COMPLETE_RECORDED.value
        or summary.get("model_identities") != [json.loads(value) for value in sorted({
            canonical_json_bytes(entry["model_config"]["model"]) for entry in entries
        })]
    ):
        raise PaperCollectionError("collection summary identity/completion is incoherent")
    expected_events = []
    for attempt in attempts:
        index = attempt["slot_index"]
        expected_events.append(("ATTEMPT_STARTED", index, None, None))
        if attempt["original_generation_attempted"]:
            expected_events.append(("ORIGINAL_GENERATION_ATTEMPT_STARTED", index, None, None))
        if attempt["recovery_construction_started"]:
            expected_events.append(("RECOVERY_CONSTRUCTION_STARTED", index, None, None))
        for arm in attempt["arm_opportunities"]:
            if arm["attempted"]:
                expected_events.append(("ARM_OPPORTUNITY_ATTEMPT_STARTED", index, arm["arm_id"], None))
        expected_events.append(("SCHEDULED_ATTEMPT_TERMINATED", index, None, attempt["terminal_status"]))
    if [(event["event_type"], event["slot_index"], event["arm_id"], event["terminal_status"]) for event in events] != expected_events:
        raise PaperCollectionError("scheduled-opportunity event journal is incoherent")
    for sequence, event in enumerate(events, start=1):
        if (
            event["event_sequence"] != sequence or event["manifest_id"] != manifest_id
            or event["manifest_sha256"] != manifest_hash
        ):
            raise PaperCollectionError("event journal sequence/identity is incoherent")
    if summary.get("collection_events") != len(events) or summary.get("collection_events_sha256") != sha256_hex(_jsonl(events)):
        raise PaperCollectionError("event journal summary hash/count is incoherent")


def persist_paper_collection_run(
    *,
    run_root: Path,
    manifest: PaperExperimentManifest,
    result: PaperCollectionResult,
    metadata: TraceRunMetadata,
) -> None:
    """Publish the six-file completed paper evidence bundle atomically."""

    run_metadata = _run_metadata_as_json(manifest, metadata)
    _validate_result_coherence(manifest, result)
    attempts = tuple(scheduled_paper_attempt_as_json(item, result.manifest_hash) for item in result.slot_outcomes)
    traces = paper_arm_traces_as_json(result, metadata)
    _validate_records(attempts, traces, result.collection_events)
    linked_trace_ids = {
        arm["arm_id"]
        for attempt in attempts
        for arm in attempt["arm_opportunities"]
        if arm["trace_expected"]
    }
    trace_ids = [trace["identifiers"]["arm_id"] for trace in traces]
    if len(trace_ids) != len(set(trace_ids)):
        raise PaperCollectionError("duplicate arm trace ID")
    if set(trace_ids) != linked_trace_ids:
        raise PaperCollectionError("arm trace linkage is incoherent")
    summary_json = paper_summary_as_json(result)
    if summary_json["arm_traces_persisted"] != len(traces):
        raise PaperCollectionError("summary arm trace count is incoherent")
    _validate_bundle_data(
        manifest_json=json.loads(manifest.canonical_bytes),
        manifest_hash=manifest.manifest_hash,
        attempts=attempts,
        traces=traces,
        summary=summary_json,
        events=result.collection_events,
        run_metadata=run_metadata,
    )

    target = Path(run_root)
    if target.exists():
        raise PaperCollectionError("target paper run directory already exists")
    if not target.parent.is_dir():
        raise PaperCollectionError("target parent directory must already exist")
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent))
    try:
        _write_bytes(temporary / "manifest.json", manifest.canonical_bytes)
        _write_bytes(temporary / "run_metadata.json", canonical_json_bytes(run_metadata))
        _write_bytes(temporary / "scheduled_attempts.jsonl", _jsonl(attempts))
        _write_bytes(temporary / "arm_traces.jsonl", _jsonl(traces))
        _write_bytes(temporary / "collection_events.jsonl", _jsonl(result.collection_events))
        _write_bytes(temporary / "paper_collection_summary.json", canonical_json_bytes(summary_json))
        directory_fd = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        os.rename(temporary, target)
        parent_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def validate_paper_collection_bundle(run_root: Path) -> None:
    """Reject partial, noncanonical, or internally incoherent published bundles."""

    root = Path(run_root)
    expected = {
        "manifest.json",
        "run_metadata.json",
        "scheduled_attempts.jsonl",
        "arm_traces.jsonl",
        "paper_collection_summary.json",
        "collection_events.jsonl",
    }
    if not root.is_dir() or {item.name for item in root.iterdir()} != expected:
        raise PaperCollectionError("paper bundle is partial or contains unexpected files")
    manifest_bytes = (root / "manifest.json").read_bytes()
    if canonical_json_bytes(json.loads(manifest_bytes)) != manifest_bytes:
        raise PaperCollectionError("manifest serialization is not canonical")
    manifest_hash = sha256_hex(manifest_bytes)
    run_metadata_bytes = (root / "run_metadata.json").read_bytes()
    run_metadata = json.loads(run_metadata_bytes)
    if canonical_json_bytes(run_metadata) != run_metadata_bytes:
        raise PaperCollectionError("run metadata serialization is not canonical")
    def records(filename):
        data = (root / filename).read_bytes()
        parsed = tuple(json.loads(line) for line in data.splitlines())
        if _jsonl(parsed) != data:
            raise PaperCollectionError(f"{filename} serialization is not canonical")
        return parsed
    attempts = records("scheduled_attempts.jsonl")
    traces = records("arm_traces.jsonl")
    events = records("collection_events.jsonl")
    summary_bytes = (root / "paper_collection_summary.json").read_bytes()
    summary = json.loads(summary_bytes)
    if canonical_json_bytes(summary) != summary_bytes:
        raise PaperCollectionError("summary serialization is not canonical")
    _validate_records(attempts, traces, events)
    _validate_bundle_data(
        manifest_json=json.loads(manifest_bytes), manifest_hash=manifest_hash,
        attempts=attempts, traces=traces, summary=summary, events=events,
        run_metadata=run_metadata,
    )


def run_paper_collection(
    *,
    manifest: PaperExperimentManifest,
    client: ModelClient,
    run_root: Path,
    metadata: TraceRunMetadata,
) -> PaperCollectionResult:
    """Collect once, publish and validate six files, then clean the prefix.

    An OSError removing an already-redundant prefix is logged, not a collection
    failure: the verified published bundle remains valid and is never rerun.
    """

    target = Path(run_root)
    if target.exists():
        raise PaperCollectionError("target paper run directory already exists")
    if not target.parent.is_dir():
        raise PaperCollectionError("target parent directory must already exist")
    validate_paper_manifest_provider(manifest, client)
    run_metadata = _run_metadata_as_json(manifest, metadata)
    manifest_hash = manifest.manifest_hash
    progress = target.with_name(f".{target.name}.in-progress")
    if progress.exists():
        raise PaperCollectionPreflightError("interrupted/in-progress evidence exists; this run must never be resumed or retried")
    progress.mkdir()
    def retain_fatal_diagnostic(fatal):
        # Best effort only: a broken storage system cannot promise its own log.
        # This file is never accepted as part of a completed bundle.
        result = fatal.result
        diagnostic = {
            "schema_version": "paper-runner-fatal-v1",
            "manifest_id": manifest.manifest_id,
            "manifest_sha256": manifest_hash,
            "paper_experiment_revision": PAPER_EXPERIMENT_REVISION,
            "execution_semantics_revision": INHERITED_EXECUTION_REVISION,
            "git_commit": run_metadata["git_commit"],
            "timestamp": run_metadata["timestamp"],
            "terminal_status": "RUNNER_FATAL",
            "safe_to_continue": False,
            "resume_permitted": False,
            "active_slot_index": fatal.active_slot_index,
            "completed_slots_in_memory": len(fatal.completed_slot_outcomes) if result is None else len(result.slot_outcomes),
            "infrastructure_failure": _infrastructure_as_json(fatal.evidence),
        }
        try:
            _write_bytes(progress / "runner_fatal.json", canonical_json_bytes(diagnostic))
        except Exception:
            pass
    try:
        _write_bytes(progress / "manifest.json", manifest.canonical_bytes)
        _write_bytes(progress / "run_metadata.json", canonical_json_bytes(run_metadata))
        _write_bytes(progress / "collection_events.jsonl", b"")
        _write_bytes(progress / "scheduled_attempts.jsonl", b"")
        _write_bytes(progress / "arm_traces.jsonl", b"")
        for directory in (progress, progress.parent):
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        def append_records(filename, records):
            with (progress / filename).open("ab") as stream:
                stream.write(_jsonl(tuple(records)))
                stream.flush()
                os.fsync(stream.fileno())
        def event_sink(event):
            append_records("collection_events.jsonl", (event,))
        def scheduled_attempt_sink(outcome):
            append_records("scheduled_attempts.jsonl", (scheduled_paper_attempt_as_json(outcome, manifest_hash),))
            append_records("arm_traces.jsonl", _outcome_arm_traces_as_json((outcome,), metadata))
        result = execute_paper_collection(
            manifest, client, event_sink=event_sink, scheduled_attempt_sink=scheduled_attempt_sink
        )
        persist_paper_collection_run(
            run_root=target, manifest=manifest, result=result, metadata=metadata
        )
        validate_paper_collection_bundle(target)
    except PaperCollectionFatalError as fatal:
        retain_fatal_diagnostic(fatal)
        raise
    except Exception as exc:
        fatal = PaperCollectionFatalError(
            "paper persistence failed; retained in-progress evidence must be audited, never rerun",
            evidence=_infrastructure(exc, scope=InfrastructureScope.PERSISTENCE, stage=InfrastructureStage.PERSISTENCE),
            result=locals().get("result"),
        )
        retain_fatal_diagnostic(fatal)
        raise fatal from exc
    try:
        shutil.rmtree(progress)
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Verified paper bundle %s remains complete; redundant prefix cleanup failed: %s",
            target, exc,
        )
    return result


__all__ = [
    "ArmOpportunityStatus",
    "CollectionCompletionStatus",
    "EligibilityOutcome",
    "InfrastructureEvidence",
    "InfrastructureScope",
    "InfrastructureStage",
    "InfrastructureSubtype",
    "PAPER_LEDGER_SCHEMA_VERSION",
    "PAPER_SUMMARY_SCHEMA_VERSION",
    "PaperArmExecution",
    "PaperCollectionError",
    "PaperCollectionFatalError",
    "PaperCollectionPreflightError",
    "PaperCollectionResult",
    "PaperCollectionSummary",
    "PaperScheduledAttemptExecution",
    "ScheduledAttemptStatus",
    "execute_paper_collection",
    "paper_arm_traces_as_json",
    "paper_summary_as_json",
    "persist_paper_collection_run",
    "run_paper_collection",
    "scheduled_paper_attempt_as_json",
    "validate_paper_collection_bundle",
    "validate_paper_manifest_provider",
]
