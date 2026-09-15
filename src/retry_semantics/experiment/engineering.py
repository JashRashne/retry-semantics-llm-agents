"""Serial V1.2 engineering validation and atomic evidence persistence."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import jsonschema

from retry_semantics.environments.ticket import TicketEnvironment, evaluate_ticket_state
from retry_semantics.experiment.manifest import (
    ENGINEERING_SLOT_COUNT,
    EngineeringManifestEntry,
    EngineeringValidationManifest,
    ScheduleStratum,
)
from retry_semantics.experiment.trace import (
    TraceRunMetadata,
    TraceSerializationError,
    arm_trace_as_json,
    is_trace_datetime,
    model_request_as_json,
    model_response_as_json,
    rejected_generation_as_json,
)
from retry_semantics.models.base import (
    ModelClient,
    ModelProviderError,
    ModelProviderStatusError,
)
from retry_semantics.runtime.exact_replay import EXACT_REPLAY
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.runtime.regeneration import LLM_REGENERATION, RegenerationResult
from retry_semantics.runtime.scheduled_trial import (
    EligibleMatchedTrialResult,
    PreTreatmentFailureTrialResult,
    ScheduledTrialResult,
    run_scheduled_trial,
)
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

_TRACE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "research"
    / "protocol"
    / "trace_schema_v1.json"
)


class EngineeringValidationFailureReason(str, Enum):
    """Narrow V1.2 engineering-stage failure taxonomy."""

    INSUFFICIENT_ELIGIBLE_FAMILIES = "INSUFFICIENT_ELIGIBLE_FAMILIES"
    MISSING_ELIGIBLE_STRATUM = "MISSING_ELIGIBLE_STRATUM"
    ELIGIBLE_FAMILY_INVARIANT_FAILURE = "ELIGIBLE_FAMILY_INVARIANT_FAILURE"
    MANIFEST_PROVIDER_MISMATCH = "MANIFEST_PROVIDER_MISMATCH"


class ScheduledAttemptKind(str, Enum):
    ELIGIBLE_FAMILY = "ELIGIBLE_FAMILY"
    INELIGIBLE_PRETREATMENT = "INELIGIBLE_PRETREATMENT"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


class EngineeringValidationError(ValueError):
    """An engineering run cannot safely start or be persisted."""


class EngineeringValidationPreflightError(EngineeringValidationError):
    """Provider identity does not match every manifest slot."""

    reason = EngineeringValidationFailureReason.MANIFEST_PROVIDER_MISMATCH


@dataclass(frozen=True, slots=True)
class OriginalGenerationInfrastructureEvidence:
    """Sanitized exact evidence available from one provider-boundary failure."""

    exception_type: str
    message: str
    status_code: int | None


@dataclass(frozen=True, slots=True)
class ScheduledAttemptExecution:
    """One retained scheduled slot outcome in frozen manifest order."""

    entry: EngineeringManifestEntry
    kind: ScheduledAttemptKind
    result: ScheduledTrialResult | None
    infrastructure_failure: OriginalGenerationInfrastructureEvidence | None
    invariant_failures: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.kind is ScheduledAttemptKind.ELIGIBLE_FAMILY:
            if type(self.result) is not EligibleMatchedTrialResult or self.infrastructure_failure is not None:
                raise EngineeringValidationError("eligible slot evidence is incoherent")
        elif self.kind is ScheduledAttemptKind.INELIGIBLE_PRETREATMENT:
            if type(self.result) is not PreTreatmentFailureTrialResult or self.infrastructure_failure is not None:
                raise EngineeringValidationError("ineligible slot evidence is incoherent")
        elif self.kind is ScheduledAttemptKind.INFRASTRUCTURE_FAILURE:
            if self.result is not None or type(self.infrastructure_failure) is not OriginalGenerationInfrastructureEvidence:
                raise EngineeringValidationError("infrastructure slot evidence is incoherent")
        else:
            raise EngineeringValidationError("unknown scheduled-attempt kind")


@dataclass(frozen=True, slots=True)
class EligibleStratumCounts:
    A: int
    B: int
    C: int
    D: int

    def as_dict(self) -> dict[str, int]:
        return {"A": self.A, "B": self.B, "C": self.C, "D": self.D}


@dataclass(frozen=True, slots=True)
class EngineeringValidationSummary:
    scheduled_attempts: int
    original_generation_attempts: int
    eligible_trial_families: int
    ineligible_pretreatment_attempts: int
    infrastructure_failed_attempts: int
    eligible_stratum_counts: EligibleStratumCounts
    passed: bool
    failure_reasons: tuple[EngineeringValidationFailureReason, ...]


@dataclass(frozen=True, slots=True)
class EngineeringValidationResult:
    manifest_id: str
    manifest_hash: str
    slot_outcomes: tuple[ScheduledAttemptExecution, ...]
    summary: EngineeringValidationSummary


def _client_provider(client: ModelClient) -> str:
    try:
        provider = client.provider
    except AttributeError as exc:
        raise EngineeringValidationPreflightError(
            "ModelClient must expose an explicit provider identity"
        ) from exc
    if type(provider) is not str or provider == "":
        raise EngineeringValidationPreflightError(
            "ModelClient provider identity must be a non-empty string"
        )
    return provider


def validate_manifest_provider(
    manifest: EngineeringValidationManifest, client: ModelClient
) -> str:
    """Fail before slot zero unless one explicit client provider matches all slots."""

    if type(manifest) is not EngineeringValidationManifest:
        raise EngineeringValidationError("manifest has the wrong type")
    actual = _client_provider(client)
    expected = {entry.model_config.model.provider for entry in manifest.entries}
    if expected != {actual}:
        raise EngineeringValidationPreflightError(
            f"manifest providers {sorted(expected)!r} do not match ModelClient provider {actual!r}"
        )
    return actual


def _provider_response_failures(
    entry: EngineeringManifestEntry, result: EligibleMatchedTrialResult
) -> list[str]:
    failures: list[str] = []
    expected_provider = entry.model_config.model.provider
    expected_model = entry.model_config.model.name
    original = result.original_generation
    if original.model_request.model_config != entry.original_generation_config:
        failures.append("ORIGINAL_GENERATION_CONFIG_MISMATCH")
    if original.model_response.provider != expected_provider:
        failures.append("ORIGINAL_RESPONSE_PROVIDER_MISMATCH")
    if original.model_response.requested_model != expected_model:
        failures.append("ORIGINAL_RESPONSE_MODEL_MISMATCH")
    for regeneration in (result.h0_regeneration, result.h1_regeneration):
        for invocation in regeneration.model_invocations:
            expected_seed = (
                None
                if entry.regeneration_config.seed is None
                else entry.regeneration_config.seed + invocation.model_call_index
            )
            if invocation.derived_seed != expected_seed:
                failures.append("REGENERATION_DERIVED_SEED_MISMATCH")
            if invocation.model_request.model_config.seed != expected_seed:
                failures.append("REGENERATION_REQUEST_SEED_MISMATCH")
            request_without_seed = invocation.model_request.model_config
            if (
                request_without_seed.model != entry.regeneration_config.model
                or request_without_seed.temperature != entry.regeneration_config.temperature
                or request_without_seed.top_p != entry.regeneration_config.top_p
                or request_without_seed.max_completion_tokens
                != entry.regeneration_config.max_completion_tokens
                or request_without_seed.tool_choice != entry.regeneration_config.tool_choice
                or request_without_seed.parallel_tool_calls
                != entry.regeneration_config.parallel_tool_calls
                or request_without_seed.provider_parameters
                != entry.regeneration_config.provider_parameters
            ):
                failures.append("REGENERATION_CONFIG_MISMATCH")
            if invocation.model_response is not None:
                if invocation.model_response.provider != expected_provider:
                    failures.append("REGENERATION_RESPONSE_PROVIDER_MISMATCH")
                if invocation.model_response.requested_model != expected_model:
                    failures.append("REGENERATION_RESPONSE_MODEL_MISMATCH")
            if (
                invocation.rejected_generation is not None
                and invocation.rejected_generation.provider != expected_provider
            ):
                failures.append("REJECTED_GENERATION_PROVIDER_MISMATCH")
    return failures


def _validate_regeneration_result(
    entry: EngineeringManifestEntry,
    result: EligibleMatchedTrialResult,
    hidden_world: HiddenWorld,
    regeneration: RegenerationResult,
) -> list[str]:
    failures: list[str] = []
    expected_arm_id = entry.plan.arm_id(hidden_world, LLM_REGENERATION)
    if regeneration.arm_id != expected_arm_id:
        failures.append("REGENERATION_ARM_ID_MISMATCH")
    state = TicketEnvironment.clone_from_snapshot(regeneration.final_state_snapshot).state
    intended = entry.plan.task_spec.expected_arguments
    recomputed = evaluate_ticket_state(
        state,
        customer_id=intended.customer_id,
        title=intended.title,
        description=intended.description,
        infrastructure_failure=regeneration.evaluation.infrastructure_failure,
        infrastructure_failure_reasons=regeneration.evaluation.exclusion_reasons,
    )
    if recomputed != regeneration.evaluation:
        failures.append("REGENERATION_EVALUATION_MISMATCH")
    event_ids = {event.event_id for event in state.mutation_events}
    for action in regeneration.recovery_actions:
        if not set(action.committed_effect_event_ids).issubset(event_ids):
            failures.append("REGENERATION_COMMIT_EVENT_MISSING")
    for event in state.mutation_events:
        if event.source_stage.value == "RECOVERY" and event.arm_id != expected_arm_id:
            failures.append("REGENERATION_MUTATION_PROVENANCE_MISMATCH")
    return failures


def validate_eligible_family(
    entry: EngineeringManifestEntry, result: EligibleMatchedTrialResult
) -> tuple[str, ...]:
    """Validate frozen invariants available from returned immutable evidence."""

    failures: list[str] = []
    if result.plan != entry.plan:
        failures.append("MANIFEST_PLAN_MISMATCH")
    construction = result.family_construction
    empty = TicketEnvironment.empty().snapshot_bytes()
    if construction.initial_state_snapshot != empty:
        failures.append("INITIAL_STATE_NOT_FRESH")
    if construction.initial_state_hash != sha256_hex(construction.initial_state_snapshot):
        failures.append("INITIAL_STATE_HASH_MISMATCH")
    if result.original_request_hash != sha256_hex(
        result.original_generation.serialized_original_request
    ):
        failures.append("FROZEN_REQUEST_HASH_MISMATCH")
    if result.regeneration_context.canonical_context_sha256 != sha256_hex(
        result.regeneration_context.canonical_context_bytes
    ):
        failures.append("REGENERATION_CONTEXT_HASH_MISMATCH")
    if result.h0_replay.additional_llm_calls != 0 or result.h1_replay.additional_llm_calls != 0:
        failures.append("REPLAY_MODEL_INVOCATION")
    if (
        result.h0_replay.recovery_tool_calls_attempted != 1
        or result.h0_replay.recovery_tool_calls_executed != 1
        or result.h1_replay.recovery_tool_calls_attempted != 1
        or result.h1_replay.recovery_tool_calls_executed != 1
    ):
        failures.append("REPLAY_DISPATCH_COUNT_MISMATCH")
    for hidden_world, replay in (
        (HiddenWorld.NOT_EXECUTED, result.h0_replay),
        (HiddenWorld.EXECUTED_ACK_LOST, result.h1_replay),
    ):
        replay_state = TicketEnvironment.clone_from_snapshot(replay.final_state_snapshot).state
        expected_arm = entry.plan.arm_id(hidden_world, EXACT_REPLAY)
        recovery_events = [
            event for event in replay_state.mutation_events if event.source_stage.value == "RECOVERY"
        ]
        if len(recovery_events) != 1 or recovery_events[0].arm_id != expected_arm:
            failures.append("REPLAY_MUTATION_PROVENANCE_MISMATCH")
        intended = entry.plan.task_spec.expected_arguments
        recomputed = evaluate_ticket_state(
            replay_state,
            customer_id=intended.customer_id,
            title=intended.title,
            description=intended.description,
        )
        if recomputed != replay.evaluation:
            failures.append("REPLAY_EVALUATION_MISMATCH")
    failures.extend(
        _validate_regeneration_result(
            entry, result, HiddenWorld.NOT_EXECUTED, result.h0_regeneration
        )
    )
    failures.extend(
        _validate_regeneration_result(
            entry, result, HiddenWorld.EXECUTED_ACK_LOST, result.h1_regeneration
        )
    )
    shared = min(
        len(result.h0_regeneration.model_invocations),
        len(result.h1_regeneration.model_invocations),
    )
    for index in range(shared):
        h0 = result.h0_regeneration.model_invocations[index]
        h1 = result.h1_regeneration.model_invocations[index]
        if h0.derived_seed != h1.derived_seed:
            failures.append("HIDDEN_WORLD_REGENERATION_SEED_MISMATCH")
        if index == 0 and h0.model_request != h1.model_request:
            failures.append("INITIAL_REGENERATION_REQUEST_MISMATCH")
    failures.extend(_provider_response_failures(entry, result))
    return tuple(dict.fromkeys(failures))


def _summary(outcomes: tuple[ScheduledAttemptExecution, ...]) -> EngineeringValidationSummary:
    eligible = [item for item in outcomes if item.kind is ScheduledAttemptKind.ELIGIBLE_FAMILY]
    strata = Counter(item.entry.schedule_stratum for item in eligible)
    stratum_counts = EligibleStratumCounts(
        A=strata[ScheduleStratum.A],
        B=strata[ScheduleStratum.B],
        C=strata[ScheduleStratum.C],
        D=strata[ScheduleStratum.D],
    )
    reasons: list[EngineeringValidationFailureReason] = []
    if len(eligible) < 8:
        reasons.append(EngineeringValidationFailureReason.INSUFFICIENT_ELIGIBLE_FAMILIES)
    if any(count == 0 for count in stratum_counts.as_dict().values()):
        reasons.append(EngineeringValidationFailureReason.MISSING_ELIGIBLE_STRATUM)
    if any(item.invariant_failures for item in eligible):
        reasons.append(EngineeringValidationFailureReason.ELIGIBLE_FAMILY_INVARIANT_FAILURE)
    return EngineeringValidationSummary(
        scheduled_attempts=len(outcomes),
        original_generation_attempts=len(outcomes),
        eligible_trial_families=len(eligible),
        ineligible_pretreatment_attempts=sum(
            item.kind is ScheduledAttemptKind.INELIGIBLE_PRETREATMENT for item in outcomes
        ),
        infrastructure_failed_attempts=sum(
            item.kind is ScheduledAttemptKind.INFRASTRUCTURE_FAILURE for item in outcomes
        ),
        eligible_stratum_counts=stratum_counts,
        passed=not reasons,
        failure_reasons=tuple(reasons),
    )


def execute_engineering_validation(
    manifest: EngineeringValidationManifest, client: ModelClient
) -> EngineeringValidationResult:
    """Execute every frozen slot once, serially, without replacement or retry."""

    validate_manifest_provider(manifest, client)
    outcomes: list[ScheduledAttemptExecution] = []
    for entry in manifest.entries:
        try:
            result = run_scheduled_trial(
                client,
                plan=entry.plan,
                initial_state=TicketEnvironment.empty(),
                original_generation_config=entry.original_generation_config,
                regeneration_config=entry.regeneration_config,
            )
        except ModelProviderError as exc:
            outcomes.append(
                ScheduledAttemptExecution(
                    entry=entry,
                    kind=ScheduledAttemptKind.INFRASTRUCTURE_FAILURE,
                    result=None,
                    infrastructure_failure=OriginalGenerationInfrastructureEvidence(
                        exception_type=type(exc).__name__,
                        message=str(exc),
                        status_code=(
                            exc.status_code
                            if isinstance(exc, ModelProviderStatusError)
                            else None
                        ),
                    ),
                    invariant_failures=(),
                )
            )
            continue
        if type(result) is PreTreatmentFailureTrialResult:
            outcome = ScheduledAttemptExecution(
                entry=entry,
                kind=ScheduledAttemptKind.INELIGIBLE_PRETREATMENT,
                result=result,
                infrastructure_failure=None,
                invariant_failures=(),
            )
        elif type(result) is EligibleMatchedTrialResult:
            outcome = ScheduledAttemptExecution(
                entry=entry,
                kind=ScheduledAttemptKind.ELIGIBLE_FAMILY,
                result=result,
                infrastructure_failure=None,
                invariant_failures=validate_eligible_family(entry, result),
            )
        else:
            raise EngineeringValidationError("scheduled-trial boundary returned an unknown type")
        outcomes.append(outcome)
    frozen_outcomes = tuple(outcomes)
    if len(frozen_outcomes) != ENGINEERING_SLOT_COUNT:
        raise EngineeringValidationError("runner did not retain exactly 16 slots")
    return EngineeringValidationResult(
        manifest_id=manifest.manifest_id,
        manifest_hash=manifest.manifest_hash,
        slot_outcomes=frozen_outcomes,
        summary=_summary(frozen_outcomes),
    )


def scheduled_attempt_as_json(
    execution: ScheduledAttemptExecution, manifest_hash: str
) -> dict[str, object]:
    entry = execution.entry
    record: dict[str, object] = {
        "scheduled_attempt_index": entry.scheduled_attempt_index,
        "replicate": entry.replicate,
        "scenario_id": entry.scenario_id,
        "schedule_stratum": entry.schedule_stratum.value,
        "manifest_id": entry.plan.manifest_id,
        "manifest_hash": manifest_hash,
        "reserved_base_trial_id": entry.plan.base_trial_id,
        "reserved_trial_family_id": entry.plan.trial_family_id,
        "model_config_id": entry.model_config.model_config_id,
        "model": entry.model_config.model.as_trace_model(),
        "original_generation_sampling": entry.model_config.original_generation.as_trace_sampling_configuration(),
        "outcome": execution.kind.value,
        "matched_family_constructed": execution.kind is ScheduledAttemptKind.ELIGIBLE_FAMILY,
        "invariant_failures": list(execution.invariant_failures),
        "linked_arm_ids": [],
        "original_generation": None,
        "infrastructure_failure": None,
    }
    if execution.kind is ScheduledAttemptKind.INFRASTRUCTURE_FAILURE:
        assert execution.infrastructure_failure is not None
        evidence = execution.infrastructure_failure
        record["infrastructure_failure"] = {
            "exception_type": evidence.exception_type,
            "message": evidence.message,
            "status_code": evidence.status_code,
        }
        return record
    assert execution.result is not None
    original = execution.result.original_generation
    original_record: dict[str, object] = {
        "model_request": model_request_as_json(original.model_request),
        "eligibility_reason": getattr(original, "reason", None).value if hasattr(original, "reason") else None,
        "detail": getattr(original, "detail", None),
        "model_response": (
            None if original.model_response is None else model_response_as_json(original.model_response)
        ),
        "rejected_generation": None,
    }
    rejected = getattr(original, "rejected_generation", None)
    if rejected is not None:
        original_record["rejected_generation"] = rejected_generation_as_json(
            rejected,
            model_call_index=0,
            derived_seed=entry.original_generation_config.seed,
        )
    record["original_generation"] = original_record
    if execution.kind is ScheduledAttemptKind.ELIGIBLE_FAMILY:
        record["linked_arm_ids"] = [
            entry.plan.arm_id(hidden_world, policy)
            for hidden_world in entry.plan.hidden_world_order
            for policy in entry.plan.arm_order(hidden_world)
        ]
    return record


def engineering_summary_as_json(result: EngineeringValidationResult) -> dict[str, object]:
    return {
        "manifest_id": result.manifest_id,
        "manifest_hash": result.manifest_hash,
        "scheduled_attempts": result.summary.scheduled_attempts,
        "original_generation_attempts": result.summary.original_generation_attempts,
        "eligible_trial_families": result.summary.eligible_trial_families,
        "ineligible_pretreatment_attempts": result.summary.ineligible_pretreatment_attempts,
        "infrastructure_failed_attempts": result.summary.infrastructure_failed_attempts,
        "eligible_stratum_counts": result.summary.eligible_stratum_counts.as_dict(),
        "passed": result.summary.passed,
        "failure_reasons": [reason.value for reason in result.summary.failure_reasons],
        "eligible_family_invariant_failures": [
            {
                "scheduled_attempt_index": item.entry.scheduled_attempt_index,
                "failures": list(item.invariant_failures),
            }
            for item in result.slot_outcomes
            if item.invariant_failures
        ],
    }


def arm_traces_as_json(
    result: EngineeringValidationResult, metadata: TraceRunMetadata
) -> tuple[dict[str, object], ...]:
    traces: list[dict[str, object]] = []
    for outcome in result.slot_outcomes:
        if outcome.kind is not ScheduledAttemptKind.ELIGIBLE_FAMILY:
            continue
        assert type(outcome.result) is EligibleMatchedTrialResult
        for hidden_world in outcome.entry.plan.hidden_world_order:
            for policy in outcome.entry.plan.arm_order(hidden_world):
                traces.append(
                    arm_trace_as_json(
                        entry=outcome.entry,
                        execution=outcome.result,
                        hidden_world=hidden_world,
                        policy=policy,
                        metadata=metadata,
                    )
                )
    return tuple(traces)


def _jsonl(records: tuple[dict[str, object], ...]) -> bytes:
    return b"".join(canonical_json_bytes(record) + b"\n" for record in records)


def _write_bytes(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _validate_result_manifest_coherence(
    manifest: EngineeringValidationManifest,
    result: EngineeringValidationResult,
) -> None:
    """Reject a mixed or caller-forged manifest/result persistence bundle."""

    if type(manifest) is not EngineeringValidationManifest:
        raise EngineeringValidationError("manifest has the wrong type")
    if type(result) is not EngineeringValidationResult:
        raise EngineeringValidationError("result has the wrong type")
    expected_hash = sha256_hex(manifest.canonical_bytes)
    if manifest.manifest_hash != expected_hash:
        raise EngineeringValidationError("manifest hash is internally incoherent")
    if result.manifest_id != manifest.manifest_id:
        raise EngineeringValidationError("result manifest_id does not match manifest")
    if result.manifest_hash != manifest.manifest_hash:
        raise EngineeringValidationError("result manifest_hash does not match manifest")
    if len(manifest.entries) != ENGINEERING_SLOT_COUNT:
        raise EngineeringValidationError("manifest must contain exactly 16 entries")
    if type(result.slot_outcomes) is not tuple or len(
        result.slot_outcomes
    ) != ENGINEERING_SLOT_COUNT:
        raise EngineeringValidationError("result must retain exactly 16 slot outcomes")
    for index, (outcome, entry) in enumerate(
        zip(result.slot_outcomes, manifest.entries, strict=True)
    ):
        if type(outcome) is not ScheduledAttemptExecution:
            raise EngineeringValidationError("result contains an invalid slot outcome")
        if outcome.entry != entry:
            raise EngineeringValidationError(
                f"result slot {index} does not match manifest entry"
            )
        if outcome.entry.scheduled_attempt_index != index:
            raise EngineeringValidationError(
                f"result slot {index} has the wrong scheduled_attempt_index"
            )
        if outcome.kind is ScheduledAttemptKind.ELIGIBLE_FAMILY:
            if type(outcome.result) is not EligibleMatchedTrialResult:
                raise EngineeringValidationError(
                    "eligible slot does not retain a matched-trial result"
                )
            expected_failures = validate_eligible_family(entry, outcome.result)
            if outcome.invariant_failures != expected_failures:
                raise EngineeringValidationError(
                    "retained eligible-family invariant failures do not match "
                    "recomputed evidence"
                )
        elif outcome.invariant_failures != ():
            raise EngineeringValidationError(
                "non-eligible slot cannot retain eligible-family invariant failures"
            )
    if result.summary != _summary(result.slot_outcomes):
        raise EngineeringValidationError(
            "result summary does not match retained slot outcomes"
        )


def _validate_arm_traces_against_frozen_schema(
    traces: tuple[dict[str, object], ...],
) -> None:
    """Validate the schema and every trace, including JSON Schema formats."""

    try:
        schema = json.loads(_TRACE_SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        )
        for index, trace in enumerate(traces):
            if not isinstance(trace, dict):
                raise TraceSerializationError(
                    f"arm trace at index {index} is not a JSON object"
                )
            if not is_trace_datetime(trace.get("timestamp")):
                raise TraceSerializationError(
                    f"arm trace at index {index} does not validate: "
                    "timestamp is not an RFC 3339 date-time"
                )
            try:
                validator.validate(trace)
            except jsonschema.ValidationError as exc:
                identifiers = trace.get("identifiers")
                arm_id = (
                    identifiers.get("arm_id", f"index {index}")
                    if isinstance(identifiers, dict)
                    else f"index {index}"
                )
                raise TraceSerializationError(
                    f"arm trace {arm_id!r} does not validate: {exc.message}"
                ) from exc
    except TraceSerializationError:
        raise
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise TraceSerializationError(
            f"frozen trace schema could not be validated: {exc}"
        ) from exc


def persist_engineering_validation_run(
    *,
    run_root: Path,
    manifest: EngineeringValidationManifest,
    result: EngineeringValidationResult,
    metadata: TraceRunMetadata,
) -> None:
    """Publish all canonical run files atomically as one new local directory."""

    _validate_result_manifest_coherence(manifest, result)
    attempts = tuple(
        scheduled_attempt_as_json(outcome, result.manifest_hash)
        for outcome in result.slot_outcomes
    )
    traces = arm_traces_as_json(result, metadata)
    _validate_arm_traces_against_frozen_schema(traces)
    manifest_bytes = manifest.canonical_bytes
    attempts_bytes = _jsonl(attempts)
    traces_bytes = _jsonl(traces)
    summary_bytes = canonical_json_bytes(engineering_summary_as_json(result))

    target = Path(run_root)
    if target.exists():
        raise EngineeringValidationError("target engineering run directory already exists")
    parent = target.parent
    if not parent.is_dir():
        raise EngineeringValidationError("target parent directory must already exist")
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=parent))
    try:
        _write_bytes(temporary / "manifest.json", manifest_bytes)
        _write_bytes(temporary / "scheduled_attempts.jsonl", attempts_bytes)
        _write_bytes(temporary / "arm_traces.jsonl", traces_bytes)
        _write_bytes(
            temporary / "engineering_summary.json",
            summary_bytes,
        )
        directory_fd = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        os.rename(temporary, target)
        parent_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def run_engineering_validation(
    *,
    manifest: EngineeringValidationManifest,
    client: ModelClient,
    run_root: Path,
    metadata: TraceRunMetadata,
) -> EngineeringValidationResult:
    """Preflight, execute all 16 slots, and atomically persist their evidence."""

    target = Path(run_root)
    if target.exists():
        raise EngineeringValidationError("target engineering run directory already exists")
    result = execute_engineering_validation(manifest, client)
    persist_engineering_validation_run(
        run_root=target,
        manifest=manifest,
        result=result,
        metadata=metadata,
    )
    return result


__all__ = [
    "EligibleStratumCounts",
    "EngineeringValidationError",
    "EngineeringValidationFailureReason",
    "EngineeringValidationPreflightError",
    "EngineeringValidationResult",
    "EngineeringValidationSummary",
    "OriginalGenerationInfrastructureEvidence",
    "ScheduledAttemptExecution",
    "ScheduledAttemptKind",
    "arm_traces_as_json",
    "engineering_summary_as_json",
    "execute_engineering_validation",
    "persist_engineering_validation_run",
    "run_engineering_validation",
    "scheduled_attempt_as_json",
    "validate_eligible_family",
    "validate_manifest_provider",
]
