from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import jsonschema
import pytest

import retry_semantics.experiment.engineering as engineering_module
from retry_semantics.experiment import (
    ENGINEERING_SLOT_COUNT,
    EngineeringValidationError,
    EngineeringValidationFailureReason,
    EngineeringValidationPreflightError,
    ManifestInvocationConfig,
    ManifestModelConfig,
    ManifestModelIdentity,
    ScheduledAttemptKind,
    TraceRunMetadata,
    TraceSerializationError,
    arm_trace_as_json,
    arm_traces_as_json,
    build_engineering_validation_manifest,
    execute_engineering_validation,
    get_scenario,
    persist_engineering_validation_run,
    run_engineering_validation,
)
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.runtime.regeneration import LLM_REGENERATION
from retry_semantics.models import (
    ModelAssistantMessage,
    ModelCallConfig,
    ModelRequest,
    ModelRejectedGenerationError,
    ModelResponse,
    ModelTimeoutError,
    ModelToolCall,
    ModelUsage,
    ToolChoice,
    freeze_json_value,
    parse_tool_arguments_json,
)

PROVIDER = "scripted-provider"
MODEL = "scripted-model"
METADATA = TraceRunMetadata(
    git_commit="1cdcfe2" + "0" * 33,
    timestamp="2026-09-15T00:00:00+00:00",
)
TRACE_SCHEMA = json.loads(
    (Path(__file__).parents[1] / "research/protocol/trace_schema_v1.json").read_text(
        encoding="utf-8"
    )
)


def _invocation(seed: int) -> ManifestInvocationConfig:
    return ManifestInvocationConfig(
        model_call_config=ModelCallConfig(
            model=MODEL,
            temperature=0.0,
            seed=seed,
            max_completion_tokens=128,
            tool_choice=ToolChoice.auto(),
            top_p=1.0,
            parallel_tool_calls=False,
            provider_parameters={},
        ),
        seed_supported=True,
    )


def _manifest(
    provider: str = PROVIDER, *, manifest_id: str = "engineering-runner-test"
):
    return build_engineering_validation_manifest(
        manifest_id=manifest_id,
        slot_model_configs=tuple(
            ManifestModelConfig(
                model_config_id=f"scripted-{index:02d}",
                model=ManifestModelIdentity(provider, MODEL, "scripted-v1"),
                original_generation=_invocation(10_000 + index),
                regeneration=_invocation(20_000 + index),
            )
            for index in range(ENGINEERING_SLOT_COUNT)
        ),
    )


def _tool_call(raw: str, *, call_id: str, tool: str = "create_ticket") -> ModelToolCall:
    parsed, arguments, error = parse_tool_arguments_json(raw)
    return ModelToolCall(
        tool_call_id=call_id,
        tool_name=tool,
        arguments_json=raw,
        parse_success=parsed,
        parsed_arguments=arguments,
        parse_error=error,
        tool_type="function",
    )


def _response(
    request: ModelRequest,
    *calls: ModelToolCall,
    content: str | None = None,
    request_id: str,
) -> ModelResponse:
    return ModelResponse(
        assistant_message=ModelAssistantMessage(
            role="assistant", content=content, tool_calls=tuple(calls)
        ),
        finish_reason="tool_calls" if calls else "stop",
        provider=PROVIDER,
        requested_model=request.model_config.model,
        returned_model="scripted-model-v1",
        usage=ModelUsage(10, 3, 13),
        system_fingerprint="scripted-fingerprint",
        provider_request_id=request_id,
    )


class ScriptedEngineeringClient:
    provider = PROVIDER

    def __init__(
        self,
        *,
        eligible_indices: set[int],
        infrastructure_indices: set[int] | None = None,
        rejected_original_indices: set[int] | None = None,
        malformed_recovery_call: int | None = None,
        rejected_recovery_call: int | None = None,
        recovery_infrastructure_call: int | None = None,
        overbudget_recovery_call: int | None = None,
        interleaved_recovery: bool = False,
        multiple_action_recovery: bool = False,
    ) -> None:
        self.eligible_indices = eligible_indices
        self.infrastructure_indices = infrastructure_indices or set()
        self.rejected_original_indices = rejected_original_indices or set()
        self.malformed_recovery_call = malformed_recovery_call
        self.rejected_recovery_call = rejected_recovery_call
        self.recovery_infrastructure_call = recovery_infrastructure_call
        self.overbudget_recovery_call = overbudget_recovery_call
        self.interleaved_recovery = interleaved_recovery
        self.multiple_action_recovery = multiple_action_recovery
        self.requests: list[ModelRequest] = []
        self.original_indices: list[int] = []
        self.recovery_calls = 0

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if len(request.messages) == 2:
            index = len(self.original_indices)
            self.original_indices.append(index)
            if index in self.infrastructure_indices:
                raise ModelTimeoutError(f"provider timeout at slot {index}")
            if index in self.rejected_original_indices:
                raise ModelRejectedGenerationError(
                    provider=PROVIDER,
                    provider_error_code="tool_use_failed",
                    failed_generation=freeze_json_value(
                        {"raw": f"rejected original {index}"}
                    ),
                    provider_request_id=f"rejected-original-{index}",
                )
            if index not in self.eligible_indices:
                return _response(
                    request,
                    content=f"no tool for slot {index}",
                    request_id=f"original-{index}",
                )
            user_task = request.messages[1].content
            scenario = next(
                scenario
                for scenario in (get_scenario(f"CREATE-{ordinal:03d}") for ordinal in range(1, 9))
                if scenario.user_task == user_task
            )
            call = _tool_call(
                json.dumps(scenario.task_spec.expected_arguments.as_dict(), separators=(",", ":")),
                call_id=f"original-call-{index}",
            )
            return _response(
                request,
                call,
                content=f"create slot {index}",
                request_id=f"original-{index}",
            )
        recovery_index = self.recovery_calls
        self.recovery_calls += 1
        if self.rejected_recovery_call == recovery_index:
            raise ModelRejectedGenerationError(
                provider=PROVIDER,
                provider_error_code="tool_use_failed",
                failed_generation=freeze_json_value(
                    {"raw": "rejected malformed generation"}
                ),
                provider_request_id="rejected-recovery-request",
            )
        if self.recovery_infrastructure_call == recovery_index:
            raise ModelTimeoutError("recovery provider timeout")
        if self.overbudget_recovery_call == recovery_index:
            return _response(
                request,
                *(
                    _tool_call("{}", call_id=f"read-{index}", tool="list_tickets")
                    for index in range(5)
                ),
                request_id=f"recovery-{recovery_index}",
            )
        if self.interleaved_recovery and recovery_index == 0:
            return _response(
                request,
                _tool_call("{}", call_id="interleaved-read", tool="list_tickets"),
                request_id="interleaved-recovery-0",
            )
        if self.interleaved_recovery and recovery_index == 1:
            user_task = request.messages[1].content
            scenario = next(
                scenario
                for scenario in (
                    get_scenario(f"CREATE-{ordinal:03d}")
                    for ordinal in range(1, 9)
                )
                if scenario.user_task == user_task
            )
            return _response(
                request,
                _tool_call(
                    json.dumps(
                        scenario.task_spec.expected_arguments.as_dict(),
                        separators=(",", ":"),
                    ),
                    call_id="interleaved-create",
                ),
                request_id="interleaved-recovery-1",
            )
        if self.multiple_action_recovery and recovery_index == 0:
            return _response(
                request,
                _tool_call("{}", call_id="multi-read-1", tool="list_tickets"),
                _tool_call("{}", call_id="multi-read-2", tool="list_tickets"),
                request_id="multiple-action-recovery-0",
            )
        if self.malformed_recovery_call == recovery_index:
            return _response(
                request,
                _tool_call('{"customer_id":', call_id="malformed-recovery"),
                request_id=f"recovery-{recovery_index}",
            )
        return _response(
            request,
            content=f"stop recovery {recovery_index}",
            request_id=f"recovery-{recovery_index}",
        )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _event_marker(event: dict[str, object]) -> tuple[str, int | None]:
    payload = event["evaluator_payload"]
    assert isinstance(payload, dict)
    if event["event_type"] == "MODEL_INVOKED":
        return ("MODEL_INVOKED", payload["model_call_index"])
    if event["event_type"] == "TOOL_REQUESTED":
        return ("TOOL_REQUESTED", payload["action_sequence"])
    return (str(event["event_type"]), None)


def test_all_16_slots_execute_once_in_order_without_early_stop() -> None:
    client = ScriptedEngineeringClient(eligible_indices=set(range(16)))

    result = execute_engineering_validation(_manifest(), client)

    assert client.original_indices == list(range(16))
    assert result.summary.scheduled_attempts == 16
    assert result.summary.original_generation_attempts == 16
    assert result.summary.eligible_trial_families == 16
    assert result.summary.passed is True
    assert len(client.requests) == 48
    assert len(arm_traces_as_json(result, METADATA)) == 64
    assert all(not outcome.invariant_failures for outcome in result.slot_outcomes)


@pytest.mark.parametrize(
    ("eligible", "passes_threshold"),
    [
        ({0, 1, 2, 3, 8, 9, 10}, False),
        ({0, 1, 2, 3, 8, 9, 10, 11}, True),
        (set(range(16)), True),
    ],
)
def test_eligibility_threshold_has_no_queue_extension(
    eligible: set[int], passes_threshold: bool
) -> None:
    client = ScriptedEngineeringClient(eligible_indices=eligible)

    result = execute_engineering_validation(_manifest(), client)

    assert client.original_indices == list(range(16))
    assert result.summary.eligible_trial_families == len(eligible)
    assert (
        EngineeringValidationFailureReason.INSUFFICIENT_ELIGIBLE_FAMILIES
        not in result.summary.failure_reasons
    ) is passes_threshold


def test_eight_eligible_only_in_a_b_fails_stratum_coverage() -> None:
    result = execute_engineering_validation(
        _manifest(), ScriptedEngineeringClient(eligible_indices=set(range(8)))
    )

    assert result.summary.eligible_stratum_counts.as_dict() == {"A": 4, "B": 4, "C": 0, "D": 0}
    assert EngineeringValidationFailureReason.MISSING_ELIGIBLE_STRATUM in result.summary.failure_reasons
    assert result.summary.passed is False


def test_eight_eligible_with_a_b_c_d_coverage_can_pass() -> None:
    eligible = {0, 1, 2, 3, 8, 9, 10, 11}
    result = execute_engineering_validation(
        _manifest(), ScriptedEngineeringClient(eligible_indices=eligible)
    )

    assert result.summary.eligible_stratum_counts.as_dict() == {"A": 2, "B": 2, "C": 2, "D": 2}
    assert result.summary.failure_reasons == ()
    assert result.summary.passed is True


def test_any_eligible_family_invariant_failure_fails_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_validator = engineering_module.validate_eligible_family

    def fail_slot_zero(entry, result):
        if entry.scheduled_attempt_index == 0:
            return ("SIMULATED_FROZEN_INVARIANT_FAILURE",)
        return real_validator(entry, result)

    monkeypatch.setattr(engineering_module, "validate_eligible_family", fail_slot_zero)
    result = execute_engineering_validation(
        _manifest(), ScriptedEngineeringClient(eligible_indices=set(range(16)))
    )

    assert result.slot_outcomes[0].invariant_failures == (
        "SIMULATED_FROZEN_INVARIANT_FAILURE",
    )
    assert EngineeringValidationFailureReason.ELIGIBLE_FAMILY_INVARIANT_FAILURE in result.summary.failure_reasons
    assert result.summary.passed is False


def test_provider_mismatch_fails_before_slot_zero() -> None:
    client = ScriptedEngineeringClient(eligible_indices=set(range(16)))

    with pytest.raises(EngineeringValidationPreflightError) as caught:
        execute_engineering_validation(_manifest(provider="different-provider"), client)

    assert caught.value.reason is EngineeringValidationFailureReason.MANIFEST_PROVIDER_MISMATCH
    assert client.requests == []


def test_original_provider_failure_is_retained_and_later_slots_continue() -> None:
    client = ScriptedEngineeringClient(
        eligible_indices=set(range(16)), infrastructure_indices={3}
    )

    result = execute_engineering_validation(_manifest(), client)

    assert client.original_indices == list(range(16))
    assert result.summary.infrastructure_failed_attempts == 1
    assert result.summary.eligible_trial_families == 15
    failed = result.slot_outcomes[3]
    assert failed.kind is ScheduledAttemptKind.INFRASTRUCTURE_FAILURE
    assert failed.infrastructure_failure is not None
    assert failed.infrastructure_failure.message == "provider timeout at slot 3"
    assert client.recovery_calls == 30


def test_persistence_keeps_pretreatment_slot_without_arm_traces(tmp_path: Path) -> None:
    client = ScriptedEngineeringClient(eligible_indices={0, 1, 2, 3, 8, 9, 10, 11})
    target = tmp_path / "run"

    result = run_engineering_validation(
        manifest=_manifest(), client=client, run_root=target, metadata=METADATA
    )

    attempts = _read_jsonl(target / "scheduled_attempts.jsonl")
    traces = _read_jsonl(target / "arm_traces.jsonl")
    assert len(attempts) == 16
    assert len(traces) == 32
    ineligible = attempts[4]
    assert ineligible["outcome"] == "INELIGIBLE_PRETREATMENT"
    assert ineligible["matched_family_constructed"] is False
    assert ineligible["linked_arm_ids"] == []
    assert ineligible["original_generation"]["eligibility_reason"] == "NO_TOOL_CALL"
    assert all(trace["identifiers"]["base_trial_id"] != ineligible["reserved_base_trial_id"] for trace in traces)
    assert result.summary.scheduled_attempts == 16


def test_pretreatment_rejected_generation_is_preserved_in_ledger(
    tmp_path: Path,
) -> None:
    target = tmp_path / "run"
    run_engineering_validation(
        manifest=_manifest(),
        client=ScriptedEngineeringClient(
            eligible_indices=set(range(16)), rejected_original_indices={4}
        ),
        run_root=target,
        metadata=METADATA,
    )

    attempts = _read_jsonl(target / "scheduled_attempts.jsonl")
    rejected = attempts[4]
    assert rejected["outcome"] == "INELIGIBLE_PRETREATMENT"
    assert rejected["linked_arm_ids"] == []
    evidence = rejected["original_generation"]["rejected_generation"]
    assert evidence["failed_generation"] == {"raw": "rejected original 4"}
    assert evidence["provider_request_id"] == "rejected-original-4"


def test_every_trace_validates_and_linkage_is_exact(tmp_path: Path) -> None:
    target = tmp_path / "run"
    run_engineering_validation(
        manifest=_manifest(),
        client=ScriptedEngineeringClient(eligible_indices=set(range(16))),
        run_root=target,
        metadata=METADATA,
    )
    attempts = _read_jsonl(target / "scheduled_attempts.jsonl")
    traces = _read_jsonl(target / "arm_traces.jsonl")
    validator = jsonschema.Draft202012Validator(
        TRACE_SCHEMA, format_checker=jsonschema.FormatChecker()
    )

    assert len(traces) == 64
    for trace in traces:
        validator.validate(trace)
    trace_ids = [trace["identifiers"]["arm_id"] for trace in traces]
    assert len(trace_ids) == len(set(trace_ids))
    linked_ids = [arm_id for attempt in attempts for arm_id in attempt["linked_arm_ids"]]
    assert sorted(linked_ids) == sorted(trace_ids)
    for attempt in attempts:
        assert len(attempt["linked_arm_ids"]) == 4


def test_regeneration_lifecycle_preserves_model_tool_interleaving() -> None:
    result = execute_engineering_validation(
        _manifest(),
        ScriptedEngineeringClient(
            eligible_indices=set(range(16)), interleaved_recovery=True
        ),
    )
    trace = next(
        trace
        for trace in arm_traces_as_json(result, METADATA)
        if trace["usage"]["additional_llm_calls"] == 3
    )
    markers = [
        _event_marker(event)
        for event in trace["evaluator_only"]["lifecycle_events"]
        if event["event_type"]
        in {
            "MODEL_INVOKED",
            "TOOL_REQUESTED",
            "TOOL_DISPATCHED",
            "TOOL_COMMITTED",
            "TOOL_OBSERVED",
        }
    ]

    assert markers == [
        ("MODEL_INVOKED", 0),
        ("TOOL_REQUESTED", 1),
        ("TOOL_DISPATCHED", None),
        ("TOOL_OBSERVED", None),
        ("MODEL_INVOKED", 1),
        ("TOOL_REQUESTED", 2),
        ("TOOL_DISPATCHED", None),
        ("TOOL_COMMITTED", None),
        ("TOOL_OBSERVED", None),
        ("MODEL_INVOKED", 2),
        ("TOOL_REQUESTED", 3),
    ]


def test_regeneration_lifecycle_groups_multiple_actions_under_one_invocation() -> None:
    result = execute_engineering_validation(
        _manifest(),
        ScriptedEngineeringClient(
            eligible_indices=set(range(16)), multiple_action_recovery=True
        ),
    )
    trace = next(
        trace
        for trace in arm_traces_as_json(result, METADATA)
        if trace["usage"]["additional_llm_calls"] == 2
        and len(trace["recovery_actions"]) == 3
    )
    markers = [
        _event_marker(event)
        for event in trace["evaluator_only"]["lifecycle_events"]
        if event["event_type"]
        in {"MODEL_INVOKED", "TOOL_REQUESTED", "TOOL_DISPATCHED", "TOOL_OBSERVED"}
    ]

    assert markers == [
        ("MODEL_INVOKED", 0),
        ("TOOL_REQUESTED", 1),
        ("TOOL_DISPATCHED", None),
        ("TOOL_OBSERVED", None),
        ("TOOL_REQUESTED", 2),
        ("TOOL_DISPATCHED", None),
        ("TOOL_OBSERVED", None),
        ("MODEL_INVOKED", 1),
        ("TOOL_REQUESTED", 3),
    ]


def test_regeneration_lifecycle_rejects_action_for_missing_invocation() -> None:
    result = execute_engineering_validation(
        _manifest(), ScriptedEngineeringClient(eligible_indices=set(range(16)))
    )
    outcome = result.slot_outcomes[0]
    execution = outcome.result
    assert execution is not None
    regeneration = execution.h0_regeneration
    malformed_action = replace(
        regeneration.recovery_actions[0], model_call_index=99
    )
    malformed_execution = replace(
        execution,
        h0_regeneration=replace(
            regeneration, recovery_actions=(malformed_action,)
        ),
    )

    with pytest.raises(TraceSerializationError, match="nonexistent"):
        arm_trace_as_json(
            entry=outcome.entry,
            execution=malformed_execution,
            hidden_world=HiddenWorld.NOT_EXECUTED,
            policy=LLM_REGENERATION,
            metadata=METADATA,
        )


def test_malformed_raw_arguments_survive_schema_valid_trace() -> None:
    result = execute_engineering_validation(
        _manifest(),
        ScriptedEngineeringClient(
            eligible_indices=set(range(16)), malformed_recovery_call=0
        ),
    )
    trace = next(
        trace
        for trace in arm_traces_as_json(result, METADATA)
        if trace["termination_reason"] == "invalid_model_tool_call"
    )
    jsonschema.Draft202012Validator(TRACE_SCHEMA).validate(trace)
    invoked = next(
        event
        for event in trace["evaluator_only"]["lifecycle_events"]
        if event["event_type"] == "MODEL_INVOKED"
    )
    raw_call = invoked["evaluator_payload"]["model_response"]["assistant_message"]["tool_calls"][0]
    assert raw_call["arguments_json"] == '{"customer_id":'
    assert raw_call["parse_success"] is False
    assert trace["recovery_actions"][0]["tool_call"] is None


def test_rejected_generation_evidence_maps_without_manufactured_action() -> None:
    result = execute_engineering_validation(
        _manifest(),
        ScriptedEngineeringClient(
            eligible_indices=set(range(16)), rejected_recovery_call=0
        ),
    )
    trace = next(
        trace
        for trace in arm_traces_as_json(result, METADATA)
        if trace["termination_reason"] == "model_rejected_generation"
    )

    jsonschema.Draft202012Validator(TRACE_SCHEMA).validate(trace)
    assert trace["recovery_actions"] == []
    evidence = trace["errors"][0]["rejected_generation"]
    assert evidence["failed_generation"] == {"raw": "rejected malformed generation"}
    assert evidence["model_call_index"] == 0
    assert evidence["derived_seed"] == 20_000


def test_extra_budget_calls_remain_only_in_raw_model_response() -> None:
    result = execute_engineering_validation(
        _manifest(),
        ScriptedEngineeringClient(
            eligible_indices=set(range(16)), overbudget_recovery_call=0
        ),
    )
    trace = next(
        trace
        for trace in arm_traces_as_json(result, METADATA)
        if trace["termination_reason"] == "action_budget_exceeded"
    )

    jsonschema.Draft202012Validator(TRACE_SCHEMA).validate(trace)
    assert len(trace["recovery_actions"]) == 4
    assert trace["recovery_actions"][-1]["action_type"] == "BUDGET_REJECTED_TOOL_CALL"
    invoked = next(
        event
        for event in trace["evaluator_only"]["lifecycle_events"]
        if event["event_type"] == "MODEL_INVOKED"
    )
    raw_calls = invoked["evaluator_payload"]["model_response"]["assistant_message"]["tool_calls"]
    assert [call["tool_call_id"] for call in raw_calls] == [
        "read-0", "read-1", "read-2", "read-3", "read-4"
    ]
    assert all(action["tool_call"]["tool_call_id"] != "read-4" for action in trace["recovery_actions"])


def test_pair_infrastructure_exclusion_is_symmetric_in_arm_traces() -> None:
    result = execute_engineering_validation(
        _manifest(),
        ScriptedEngineeringClient(
            eligible_indices=set(range(16)), recovery_infrastructure_call=0
        ),
    )
    traces = arm_traces_as_json(result, METADATA)
    failed = next(trace for trace in traces if trace["termination_reason"] == "infrastructure_failure")
    pair_id = failed["identifiers"]["pair_id"]
    pair = [trace for trace in traces if trace["identifiers"]["pair_id"] == pair_id]

    assert len(pair) == 2
    for trace in pair:
        jsonschema.Draft202012Validator(TRACE_SCHEMA).validate(trace)
        evaluation = trace["evaluator_only"]["evaluation"]
        assert evaluation["valid_for_behavioral_analysis"] is False
        assert evaluation["exclusion_reasons"] == ["PROVIDER_UNAVAILABLE"]


def _logical_trace(trace: dict[str, object]) -> dict[str, object]:
    copy = json.loads(json.dumps(trace))
    copy.pop("timestamp")
    copy.pop("latency")
    return copy


def test_deterministic_runs_have_equal_logical_records(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for target in (first, second):
        run_engineering_validation(
            manifest=_manifest(),
            client=ScriptedEngineeringClient(eligible_indices=set(range(16))),
            run_root=target,
            metadata=METADATA,
        )

    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
    assert (first / "scheduled_attempts.jsonl").read_bytes() == (second / "scheduled_attempts.jsonl").read_bytes()
    assert (first / "engineering_summary.json").read_bytes() == (second / "engineering_summary.json").read_bytes()
    assert [_logical_trace(trace) for trace in _read_jsonl(first / "arm_traces.jsonl")] == [
        _logical_trace(trace) for trace in _read_jsonl(second / "arm_traces.jsonl")
    ]


def test_write_failure_never_publishes_partial_completed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest()
    result = execute_engineering_validation(
        manifest, ScriptedEngineeringClient(eligible_indices=set(range(16)))
    )
    target = tmp_path / "failed-run"
    real_write = engineering_module._write_bytes

    def fail_on_traces(path: Path, data: bytes) -> None:
        if path.name == "arm_traces.jsonl":
            raise OSError("simulated write failure")
        real_write(path, data)

    monkeypatch.setattr(engineering_module, "_write_bytes", fail_on_traces)
    with pytest.raises(OSError, match="simulated write failure"):
        persist_engineering_validation_run(
            run_root=target, manifest=manifest, result=result, metadata=METADATA
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_persistence_rejects_mismatched_manifest_result_before_temp_directory(
    tmp_path: Path,
) -> None:
    manifest_a = _manifest(manifest_id="engineering-manifest-a")
    manifest_b = _manifest(manifest_id="engineering-manifest-b")
    result_a = execute_engineering_validation(
        manifest_a, ScriptedEngineeringClient(eligible_indices=set(range(16)))
    )
    target = tmp_path / "mixed-run"

    with pytest.raises(EngineeringValidationError, match="manifest_id"):
        persist_engineering_validation_run(
            run_root=target,
            manifest=manifest_b,
            result=result_a,
            metadata=METADATA,
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_persistence_rejects_altered_summary_before_temp_directory(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    result = execute_engineering_validation(
        manifest, ScriptedEngineeringClient(eligible_indices=set(range(16)))
    )
    altered = replace(
        result,
        summary=replace(result.summary, eligible_trial_families=15),
    )
    target = tmp_path / "altered-summary"

    with pytest.raises(EngineeringValidationError, match="summary"):
        persist_engineering_validation_run(
            run_root=target,
            manifest=manifest,
            result=altered,
            metadata=METADATA,
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_persistence_recomputes_every_eligible_family_invariant_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest()
    result = execute_engineering_validation(
        manifest, ScriptedEngineeringClient(eligible_indices=set(range(16)))
    )
    target = tmp_path / "forged-cleared-invariants"
    checked_indexes: list[int] = []

    def persistence_validator(entry, execution):
        checked_indexes.append(entry.scheduled_attempt_index)
        return (
            ("SIMULATED_FAILURE",)
            if entry.scheduled_attempt_index == 15
            else ()
        )

    monkeypatch.setattr(
        engineering_module, "validate_eligible_family", persistence_validator
    )

    with pytest.raises(EngineeringValidationError, match="recomputed evidence"):
        persist_engineering_validation_run(
            run_root=target,
            manifest=manifest,
            result=result,
            metadata=METADATA,
        )

    assert checked_indexes == list(range(16))
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_persistence_rejects_forged_cached_failure_with_matching_summary(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    result = execute_engineering_validation(
        manifest, ScriptedEngineeringClient(eligible_indices=set(range(16)))
    )
    forged_outcome = replace(
        result.slot_outcomes[0], invariant_failures=("FAKE_FAILURE",)
    )
    forged_slots = (forged_outcome, *result.slot_outcomes[1:])
    forged_result = replace(
        result,
        slot_outcomes=forged_slots,
        summary=engineering_module._summary(forged_slots),
    )
    target = tmp_path / "forged-added-invariants"

    with pytest.raises(EngineeringValidationError, match="recomputed evidence"):
        persist_engineering_validation_run(
            run_root=target,
            manifest=manifest,
            result=forged_result,
            metadata=METADATA,
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_persistence_detects_invariant_failure_in_retained_execution_evidence(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    result = execute_engineering_validation(
        manifest, ScriptedEngineeringClient(eligible_indices=set(range(16)))
    )
    original_outcome = result.slot_outcomes[0]
    execution = original_outcome.result
    assert execution is not None
    regeneration = execution.h0_regeneration
    inconsistent_regeneration = replace(
        regeneration,
        evaluation=replace(
            regeneration.evaluation,
            matching_ticket_count=regeneration.evaluation.matching_ticket_count + 1,
        ),
    )
    inconsistent_execution = replace(
        execution, h0_regeneration=inconsistent_regeneration
    )
    forged_outcome = replace(
        original_outcome,
        result=inconsistent_execution,
        invariant_failures=(),
    )
    forged_result = replace(
        result,
        slot_outcomes=(forged_outcome, *result.slot_outcomes[1:]),
    )
    target = tmp_path / "inconsistent-execution"

    with pytest.raises(EngineeringValidationError, match="recomputed evidence"):
        persist_engineering_validation_run(
            run_root=target,
            manifest=manifest,
            result=forged_result,
            metadata=METADATA,
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_production_schema_validation_failure_creates_no_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest()
    result = execute_engineering_validation(
        manifest, ScriptedEngineeringClient(eligible_indices=set(range(16)))
    )
    target = tmp_path / "schema-invalid"
    real_serializer = engineering_module.arm_traces_as_json

    def schema_invalid_traces(result, metadata):
        traces = list(real_serializer(result, metadata))
        del traces[0]["schema_version"]
        return tuple(traces)

    monkeypatch.setattr(
        engineering_module, "arm_traces_as_json", schema_invalid_traces
    )

    with pytest.raises(TraceSerializationError, match="does not validate"):
        persist_engineering_validation_run(
            run_root=target,
            manifest=manifest,
            result=result,
            metadata=METADATA,
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_production_timestamp_format_failure_creates_no_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest()
    result = execute_engineering_validation(
        manifest, ScriptedEngineeringClient(eligible_indices=set(range(16)))
    )
    target = tmp_path / "timestamp-invalid"
    real_serializer = engineering_module.arm_traces_as_json

    def timestamp_invalid_traces(result, metadata):
        traces = list(real_serializer(result, metadata))
        traces[0]["timestamp"] = "2026-09-15 00:00:00+00:00"
        return tuple(traces)

    monkeypatch.setattr(
        engineering_module, "arm_traces_as_json", timestamp_invalid_traces
    )

    with pytest.raises(TraceSerializationError, match="does not validate"):
        persist_engineering_validation_run(
            run_root=target,
            manifest=manifest,
            result=result,
            metadata=METADATA,
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_schema_invalid_timestamp_metadata_cannot_publish(tmp_path: Path) -> None:
    target = tmp_path / "invalid-timestamp"

    with pytest.raises(TraceSerializationError, match="date-time"):
        TraceRunMetadata(
            git_commit=METADATA.git_commit,
            timestamp="2026-09-15 00:00:00+00:00",
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_persisted_trace_is_joinable_to_engineering_validation_bundle(
    tmp_path: Path,
) -> None:
    target = tmp_path / "engineering-run"
    run_engineering_validation(
        manifest=_manifest(),
        client=ScriptedEngineeringClient(eligible_indices=set(range(16))),
        run_root=target,
        metadata=METADATA,
    )
    persisted_manifest = json.loads(
        (target / "manifest.json").read_text(encoding="utf-8")
    )
    attempts = _read_jsonl(target / "scheduled_attempts.jsonl")
    traces = _read_jsonl(target / "arm_traces.jsonl")
    summary = json.loads(
        (target / "engineering_summary.json").read_text(encoding="utf-8")
    )

    assert persisted_manifest["manifest_kind"] == "engineering_validation"
    manifest_id = persisted_manifest["manifest_id"]
    assert summary["manifest_id"] == manifest_id
    assert {attempt["manifest_id"] for attempt in attempts} == {manifest_id}
    assert {trace["identifiers"]["manifest_id"] for trace in traces} == {
        manifest_id
    }


def test_existing_target_fails_before_any_model_call(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    client = ScriptedEngineeringClient(eligible_indices=set(range(16)))

    with pytest.raises(Exception, match="already exists"):
        run_engineering_validation(
            manifest=_manifest(), client=client, run_root=target, metadata=METADATA
        )

    assert client.requests == []
