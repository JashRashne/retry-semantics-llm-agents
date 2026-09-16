from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import replace
from pathlib import Path

import jsonschema
import pytest

import retry_semantics.experiment.paper as paper
from retry_semantics.environments.ticket import SnapshotValidationError
from retry_semantics.experiment import build_fireworks_deepseek_paper_manifest, get_scenario
from retry_semantics.experiment.paper import (
    ArmOpportunityStatus,
    EligibilityOutcome,
    InfrastructureEvidence,
    InfrastructureScope,
    InfrastructureStage,
    InfrastructureSubtype,
    PaperCollectionError,
    PaperCollectionFatalError,
    PaperCollectionPreflightError,
    execute_paper_collection,
    paper_arm_traces_as_json,
    persist_paper_collection_run,
    run_paper_collection,
    scheduled_paper_attempt_as_json,
    validate_paper_collection_bundle,
)
from retry_semantics.experiment.trace import TraceRunMetadata
from retry_semantics.models import (
    ModelAssistantMessage,
    ModelAuthenticationError,
    ModelProviderStatusError,
    ModelRateLimitError,
    ModelRejectedGenerationError,
    ModelResponse,
    ModelResponseError,
    ModelTimeoutError,
    ModelToolCall,
    ModelTransportError,
    freeze_json_value,
    parse_tool_arguments_json,
)
from retry_semantics.runtime.exact_replay import EXACT_REPLAY
from retry_semantics.runtime.hidden_worlds import HiddenWorld, TrialFamilyConstructionError
from retry_semantics.runtime.original_generation import OriginalGenerationFailureReason
from retry_semantics.runtime.regeneration import LLM_REGENERATION
from retry_semantics.serialization import canonical_json_bytes

METADATA = TraceRunMetadata(git_commit="c35be82" + "0" * 33, timestamp="2026-09-16T00:00:00+00:00")


def call(raw, *, call_id="offline-call", tool="create_ticket", tool_type="function"):
    success, parsed, error = parse_tool_arguments_json(raw)
    return ModelToolCall(call_id, tool, raw, success, parsed, error, tool_type)


class OfflineClient:
    provider = "fireworks"

    def __init__(self, *, eligible=None, original_errors=None, original_modes=None, recovery_errors=None, recovery_mode=None):
        self.eligible = {0} if eligible is None else eligible
        self.original_errors = original_errors or {}
        self.original_modes = original_modes or {}
        self.recovery_errors = recovery_errors or {}
        self.recovery_mode = recovery_mode
        self.original_slots = []
        self.original_tasks = []
        self.requests = []
        self.recovery_counts = Counter()
        self.active = False
        self.maximum_active = 0

    def complete(self, request):
        assert not self.active, "concurrent model invocation"
        self.active = True
        self.maximum_active = max(self.maximum_active, 1)
        self.requests.append(request)
        try:
            if len(request.messages) == 2:
                slot = request.model_config.seed - 30000
                self.original_slots.append(slot)
                self.original_tasks.append(request.messages[1].content)
                if slot in self.original_errors:
                    raise self.original_errors[slot]
                scenario = next(get_scenario(f"CREATE-{s:03d}") for s in range(1, 9) if get_scenario(f"CREATE-{s:03d}").user_task == request.messages[1].content)
                raw = json.dumps(scenario.task_spec.expected_arguments.as_dict())
                mode = self.original_modes.get(slot)
                calls = [call(raw, call_id=f"original-{slot}")] if slot in self.eligible else []
                if mode == "NO_TOOL_CALL":
                    calls = []
                elif mode == "MULTIPLE_TOOL_CALLS":
                    calls = [call(raw), call(raw, call_id="second")]
                elif mode == "WRONG_TOOL":
                    calls = [call("{}", tool="list_tickets")]
                elif mode == "INVALID_TOOL_CALL_TYPE":
                    calls = [call(raw, tool_type="unknown")]
                elif mode == "MISSING_OR_INVALID_TOOL_CALL_ID":
                    calls = [call(raw, call_id=None)]
                elif mode == "MALFORMED_ARGUMENT_JSON":
                    calls = [call('{"customer_id":')]
                elif mode == "INVALID_ARGUMENT_SHAPE":
                    calls = [call("{}")]
                elif mode == "TASK_INCORRECT_ARGUMENTS":
                    arguments = scenario.task_spec.expected_arguments.as_dict()
                    arguments["title"] = "Wrong title"
                    calls = [call(json.dumps(arguments))]
                elif mode == "REJECTED_GENERATION":
                    raise ModelRejectedGenerationError("fireworks", "tool_use_failed", freeze_json_value({"unparsed": "raw failed generation"}), f"rejected-{slot}")
            else:
                slot = (request.model_config.seed - 40000) // 10
                ordinal = self.recovery_counts[slot]
                self.recovery_counts[slot] += 1
                if (slot, ordinal) in self.recovery_errors:
                    raise self.recovery_errors[(slot, ordinal)]
                calls = []
                if self.recovery_mode == "malformed" and ordinal == 0:
                    calls = [call('{"customer_id":')]
                elif self.recovery_mode == "budget" and ordinal == 0:
                    calls = [call("{}", call_id=f"read-{i}", tool="list_tickets") for i in range(5)]
            return ModelResponse(
                assistant_message=ModelAssistantMessage("assistant", "offline response", tuple(calls)),
                finish_reason="tool_calls" if calls else "stop",
                provider=self.provider,
                requested_model=request.model_config.model,
                returned_model="offline-fake",
                usage=None,
                system_fingerprint=None,
                provider_request_id=f"offline-response-{len(self.requests)}",
            )
        finally:
            self.active = False


@pytest.fixture(scope="module")
def manifest():
    return build_fireworks_deepseek_paper_manifest()


@pytest.fixture(scope="module")
def collected(manifest):
    return execute_paper_collection(manifest, OfflineClient(eligible={0, 1}))


def ledger(result, index=0):
    return scheduled_paper_attempt_as_json(result.slot_outcomes[index], result.manifest_hash)


def test_all_160_originals_and_640_arm_opportunities_serial_once_in_order(manifest, monkeypatch):
    client = OfflineClient(eligible=set(range(160)))
    real_arm = paper.execute_prepared_recovery_arm
    arm_order = []
    active_arm = False
    def wrapped(prepared, **kwargs):
        nonlocal active_arm
        assert not active_arm
        active_arm = True
        try:
            arm_order.append(prepared.plan.arm_id(kwargs["hidden_world"], kwargs["policy"]))
            return real_arm(prepared, **kwargs)
        finally:
            active_arm = False
    monkeypatch.setattr(paper, "execute_prepared_recovery_arm", wrapped)
    result = execute_paper_collection(manifest, client)
    assert client.original_slots == list(range(160))
    assert client.original_tasks == [entry.scenario.user_task for entry in manifest.entries]
    assert len(client.requests) == 480
    assert client.maximum_active == 1
    assert arm_order == [entry.plan.arm_id(world, policy) for entry in manifest.entries for world in entry.plan.hidden_world_order for policy in entry.plan.arm_order(world)]
    assert result.summary.eligible_original_generations == 160
    assert result.summary.activated_families == 160
    assert result.summary.arm_opportunities == result.summary.arm_opportunities_attempted == 640
    assert result.summary.arm_traces_collected == 640
    assert len(result.collection_events) == 1280


def test_eligible_ledger_has_all_identity_seeds_and_family_links(collected, manifest):
    record = ledger(collected)
    assert record["eligibility"]["outcome"] == "ELIGIBLE"
    assert record["family_id"] == manifest.entries[0].plan.trial_family_id
    assert record["trial_family_activated"] is True
    assert record["recovery_construction_started"] is True
    assert record["expected_arm_opportunities_attempted"] is True
    assert record["original_generation_seed"] == 30000
    assert record["regeneration_base_seed"] == 40000
    assert record["manifest_sha256"] == manifest.manifest_hash
    assert len(record["arm_opportunities"]) == 4
    assert all(arm["attempted"] and arm["trace_expected"] for arm in record["arm_opportunities"])


@pytest.mark.parametrize("reason", list(OriginalGenerationFailureReason))
def test_ineligibility_taxonomy_is_direct_frozen_reason_mapping(manifest, reason):
    client = OfflineClient(original_modes={0: reason.value})
    result = execute_paper_collection(manifest, client)
    record = ledger(result)
    assert record["eligibility"]["taxonomy_version"] == "original-generation-eligibility-v1"
    assert record["eligibility"]["ineligibility_reason"] == reason.value
    assert record["eligibility"]["outcome"] == "INELIGIBLE_BEHAVIORAL"
    assert record["family_id"] is None
    assert not record["trial_family_activated"]
    assert all(not arm["attempted"] and not arm["trace_expected"] for arm in record["arm_opportunities"])
    assert paper_arm_traces_as_json(result, METADATA) == ()
    assert client.original_slots == list(range(160))
    assert client.recovery_counts == Counter()
    if reason is OriginalGenerationFailureReason.REJECTED_GENERATION:
        assert record["original_generation_evidence"]["rejected_generation"]["failed_generation"] == {"unparsed": "raw failed generation"}


@pytest.mark.parametrize(("error", "subtype"), [
    (ModelTimeoutError("timeout"), "TIMEOUT"),
    (ModelRateLimitError("rate limit"), "RATE_LIMIT"),
    (ModelTransportError("connection"), "TRANSPORT"),
    (ModelAuthenticationError("authentication"), "AUTHENTICATION"),
    (ModelProviderStatusError("server", status_code=503), "HTTP_5XX"),
    (ModelProviderStatusError("status", status_code=400), "PROVIDER_STATUS"),
    (ModelResponseError("unreadable response"), "PROVIDER_RESPONSE"),
])
def test_original_infrastructure_is_structured_no_retry_no_replacement(manifest, error, subtype):
    client = OfflineClient(eligible={0, 1}, original_errors={0: error})
    result = execute_paper_collection(manifest, client)
    record = ledger(result)
    failure = record["original_generation_infrastructure"]
    assert failure["subtype"] == subtype
    assert failure["scope"] == "ORIGINAL_GENERATION"
    assert failure["policy_attributable"] is False
    assert failure["attributable_arm_id"] is None
    assert record["eligibility"]["outcome"] == "INFRASTRUCTURE_FAILURE"
    assert record["eligibility"]["ineligibility_reason"] is None
    assert not record["trial_family_activated"]
    assert all(not arm["attempted"] for arm in record["arm_opportunities"])
    assert client.original_slots == list(range(160))
    assert result.summary.activated_families == 1
    assert client.recovery_counts == Counter({1: 2})


@pytest.mark.parametrize(("error", "subtype"), [
    (TrialFamilyConstructionError("family fault"), "FAMILY_CONSTRUCTION"),
    (SnapshotValidationError("clone fault"), "ENVIRONMENT_CLONE_SETUP"),
])
def test_pre_arm_family_failure_never_fabricates_policy_attribution(tmp_path, manifest, monkeypatch, error, subtype):
    real_prepare = paper.prepare_eligible_scheduled_trial
    def fail_one(**kwargs):
        if kwargs["plan"].scheduled_attempt_ordinal == 0:
            raise error
        return real_prepare(**kwargs)
    monkeypatch.setattr(paper, "prepare_eligible_scheduled_trial", fail_one)
    client = OfflineClient(eligible={0, 1})
    result = execute_paper_collection(manifest, client)
    record = ledger(result)
    assert record["eligibility"]["outcome"] == "ELIGIBLE"
    assert record["recovery_construction_started"] is True
    assert record["family_id"] is None
    assert not record["trial_family_activated"]
    assert record["family_system_failure"]["scope"] == "FAMILY_SYSTEM"
    assert record["family_system_failure"]["subtype"] == subtype
    assert not record["family_system_failure"]["policy_attributable"]
    assert record["family_system_failure"]["attributable_policy"] is None
    assert all(not arm["attempted"] for arm in record["arm_opportunities"])
    assert client.original_slots == list(range(160))
    assert result.summary.eligible_original_generations == 2
    assert result.summary.activated_families == 1
    assert len(paper_arm_traces_as_json(result, METADATA)) == 4
    persist_paper_collection_run(run_root=tmp_path / "family-failure", manifest=manifest, result=result, metadata=METADATA)
    validate_paper_collection_bundle(tmp_path / "family-failure")


def test_environment_setup_failure_before_original_is_nonattributable(tmp_path, manifest, monkeypatch):
    real_empty = paper.TicketEnvironment.empty
    calls = 0
    def fail_first():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("environment setup fault")
        return real_empty()
    monkeypatch.setattr(paper.TicketEnvironment, "empty", fail_first)
    client = OfflineClient(eligible=set())
    result = execute_paper_collection(manifest, client)
    record = ledger(result)
    assert record["attempt_started"] is True
    assert record["original_generation_attempted"] is False
    assert record["eligibility"]["outcome"] == "NOT_REACHED"
    assert record["family_system_failure"]["subtype"] == "ENVIRONMENT_SETUP"
    assert client.original_slots == list(range(1, 160))
    persist_paper_collection_run(run_root=tmp_path / "setup-failure", manifest=manifest, result=result, metadata=METADATA)
    validate_paper_collection_bundle(tmp_path / "setup-failure")


@pytest.mark.parametrize("policy", [EXACT_REPLAY, LLM_REGENERATION])
def test_failure_before_arm_trace_retains_paired_arm_and_later_slots(tmp_path, manifest, monkeypatch, policy):
    real_arm = paper.execute_prepared_recovery_arm
    attempts = []
    def fail_arm(prepared, **kwargs):
        arm_id = prepared.plan.arm_id(kwargs["hidden_world"], kwargs["policy"])
        attempts.append(arm_id)
        if prepared.plan.scheduled_attempt_ordinal == 0 and kwargs["hidden_world"] is HiddenWorld.NOT_EXECUTED and kwargs["policy"] == policy:
            raise RuntimeError("executor fault before result/trace")
        return real_arm(prepared, **kwargs)
    monkeypatch.setattr(paper, "execute_prepared_recovery_arm", fail_arm)
    client = OfflineClient(eligible={0, 1})
    result = execute_paper_collection(manifest, client)
    record = ledger(result)
    failed = next(arm for arm in record["arm_opportunities"] if arm["policy"] == policy and arm["hidden_world"] == "NOT_EXECUTED")
    assert failed["status"] == "INFRASTRUCTURE_FAILURE_BEFORE_TRACE"
    assert failed["trace_expected"] is False
    assert failed["infrastructure_failure"]["scope"] == "ARM"
    assert failed["infrastructure_failure"]["attributable_policy"] == policy
    assert failed["infrastructure_failure"]["attributable_arm_id"] == failed["arm_id"]
    assert failed["pre_trace_evidence"]["executor_dispatch_count"] == 0
    assert failed["pre_trace_evidence"]["model_calls_issued"] == 0
    assert failed["pre_trace_evidence"]["recovery_commit_event_ids"] == []
    assert failed["pre_trace_evidence"]["authoritative_final_state_snapshot"] is not None
    assert len(attempts) == 8 == len(set(attempts))
    traces = paper_arm_traces_as_json(result, METADATA)
    assert len(traces) == 7
    assert sum(trace["identifiers"]["trial_family_id"] == record["family_id"] for trace in traces) == 3
    assert all(not trace["evaluator_only"]["evaluation"]["infrastructure_failure"] for trace in traces)
    assert client.original_slots == list(range(160))
    persist_paper_collection_run(run_root=tmp_path / "arm-failure", manifest=manifest, result=result, metadata=METADATA)
    validate_paper_collection_bundle(tmp_path / "arm-failure")


def test_traced_regeneration_timeout_does_not_mark_replay_as_failed(manifest):
    result = execute_paper_collection(manifest, OfflineClient(recovery_errors={(0, 0): ModelTimeoutError("recovery timeout")}))
    record = ledger(result)
    failed = next(arm for arm in record["arm_opportunities"] if arm["infrastructure_failure"] is not None)
    assert failed["status"] == "INFRASTRUCTURE_FAILURE_WITH_TRACE"
    assert failed["infrastructure_failure"]["subtype"] == "TIMEOUT"
    traces = paper_arm_traces_as_json(result, METADATA)
    assert len(traces) == 4
    assert sum(trace["evaluator_only"]["evaluation"]["infrastructure_failure"] for trace in traces) == 1
    replay = next(trace for trace in traces if trace["recovery_policy"] == EXACT_REPLAY and trace["evaluator_only"]["hidden_world"] == "NOT_EXECUTED")
    assert replay["errors"] == []
    assert replay["evaluator_only"]["evaluation"]["infrastructure_failure"] is False


def test_replay_failure_after_commit_preserves_observed_state_without_fabricated_trace(manifest, monkeypatch):
    real_arm = paper.execute_prepared_recovery_arm
    def fail_after_commit(prepared, **kwargs):
        result = real_arm(prepared, **kwargs)
        if prepared.plan.scheduled_attempt_ordinal == 0 and kwargs["hidden_world"] is HiddenWorld.NOT_EXECUTED and kwargs["policy"] == EXACT_REPLAY:
            raise RuntimeError("failure after authoritative commit")
        return result
    monkeypatch.setattr(paper, "execute_prepared_recovery_arm", fail_after_commit)
    result = execute_paper_collection(manifest, OfflineClient())
    failed = ledger(result)["arm_opportunities"][0]
    evidence = failed["pre_trace_evidence"]
    assert not failed["trace_expected"]
    assert evidence["executor_dispatch_count"] == 1
    assert len(evidence["recovery_commit_event_ids"]) == 1
    assert len(json.loads(evidence["authoritative_final_state_snapshot"])["tickets"]) == 1
    assert "recovery_tool_calls_executed" not in evidence


def test_escaped_regeneration_failure_preserves_prior_raw_model_response(manifest, monkeypatch):
    real_arm = paper.execute_prepared_recovery_arm
    def fail_after_model(prepared, **kwargs):
        if prepared.plan.scheduled_attempt_ordinal == 0 and kwargs["hidden_world"] is HiddenWorld.NOT_EXECUTED and kwargs["policy"] == LLM_REGENERATION:
            request = paper.model_request_from_regeneration_context(prepared.regeneration_context, kwargs["regeneration_config"])
            kwargs["client"].complete(request)
            raise RuntimeError("failure after model response")
        return real_arm(prepared, **kwargs)
    monkeypatch.setattr(paper, "execute_prepared_recovery_arm", fail_after_model)
    result = execute_paper_collection(manifest, OfflineClient())
    failed = next(arm for arm in ledger(result)["arm_opportunities"] if arm["status"] == "INFRASTRUCTURE_FAILURE_BEFORE_TRACE")
    evidence = failed["pre_trace_evidence"]
    assert evidence["model_calls_issued"] == 1
    assert evidence["model_invocations"][0]["model_response"]["assistant_message"]["content"] == "offline response"


def test_original_unreadable_provider_structure_is_retained_as_diagnostic(manifest):
    error = ModelResponseError("unreadable", structured_evidence={"evidence_version": "offline-structure-v1", "raw_tool_calls": [{"function": {"arguments": 42}}]})
    result = execute_paper_collection(manifest, OfflineClient(original_errors={0: error}))
    assert ledger(result)["original_generation_infrastructure"]["diagnostic"]["structured_evidence"]["raw_tool_calls"][0]["function"]["arguments"] == 42


def test_unreadable_fireworks_tool_structure_retained_without_reasoning_state():
    from retry_semantics.models.fireworks import capture_fireworks_chat_completion, DEEPSEEK_V4_FLASH_0731_MODEL
    from retry_semantics.models import thaw_json_value
    raw = {"choices": [{"message": {
        "role": "assistant", "content": None,
        "reasoning_content": "forbidden hidden state",
        "tool_calls": [{"id": "raw-call", "type": "function", "function": {"name": "create_ticket", "arguments": 42}}],
    }, "finish_reason": "tool_calls"}]}
    # Use a different requested model to reach the same frozen structural parser
    # without the primary model's earlier explicit reasoning-mode guard.
    with pytest.raises(ModelResponseError) as caught:
        capture_fireworks_chat_completion(raw, requested_model="offline-other-model")
    evidence = thaw_json_value(caught.value.structured_evidence)
    assert evidence["completion"]["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] == 42
    assert b"reasoning_content" not in canonical_json_bytes(evidence)
    assert b"forbidden hidden state" not in canonical_json_bytes(evidence)
    with pytest.raises(ModelResponseError) as primary:
        capture_fireworks_chat_completion(raw, requested_model=DEEPSEEK_V4_FLASH_0731_MODEL)
    assert b"forbidden hidden state" not in canonical_json_bytes(thaw_json_value(primary.value.structured_evidence))


def test_runner_provider_neutral_without_fireworks_adapter(manifest):
    from retry_semantics.experiment.paper_manifest import build_paper_manifest
    configs = tuple(replace(entry.model_config, model=replace(entry.model_config.model, provider="offline-neutral-provider")) for entry in manifest.entries)
    neutral = build_paper_manifest(manifest_id="offline-neutral-paper", slot_model_configs=configs)
    client = OfflineClient(eligible=set())
    client.provider = "offline-neutral-provider"
    result = execute_paper_collection(neutral, client)
    assert client.original_slots == list(range(160))
    assert result.summary.ineligible_attempts == 160


def test_memory_corruption_is_runner_fatal_not_recorded_normal_infrastructure(manifest):
    client = OfflineClient(original_errors={0: MemoryError("memory corruption")})
    with pytest.raises(PaperCollectionFatalError):
        execute_paper_collection(manifest, client)
    assert client.original_slots == [0]


@pytest.mark.parametrize("mode", ["malformed", "budget"])
def test_raw_recovery_evidence_needed_for_later_analysis_is_preserved(manifest, mode):
    result = execute_paper_collection(manifest, OfflineClient(recovery_mode=mode))
    trace = next(trace for trace in paper_arm_traces_as_json(result, METADATA) if trace["recovery_policy"] == LLM_REGENERATION)
    invoked = next(event for event in trace["evaluator_only"]["lifecycle_events"] if event["event_type"] == "MODEL_INVOKED")
    calls = invoked["evaluator_payload"]["model_response"]["assistant_message"]["tool_calls"]
    if mode == "malformed":
        assert calls[0]["parse_success"] is False
        assert calls[0]["arguments_json"] == '{"customer_id":'
    else:
        assert len(calls) == 5
        assert len(trace["recovery_actions"]) == 4
    assert "STATE_CORRECT" not in trace
    assert "MALFORMED_GENERATION" not in trace


def test_nonarm_attribution_is_rejected():
    with pytest.raises(PaperCollectionError, match="fabricate"):
        InfrastructureEvidence(InfrastructureScope.FAMILY_SYSTEM, InfrastructureStage.FAMILY_CONSTRUCTION, InfrastructureSubtype.FAMILY_CONSTRUCTION, "RuntimeError", "fault", None, "arm-id", EXACT_REPLAY, HiddenWorld.NOT_EXECUTED)


def test_provider_preflight_before_slot_zero(manifest):
    client = OfflineClient()
    client.provider = "other-provider"
    with pytest.raises(PaperCollectionPreflightError):
        execute_paper_collection(manifest, client)
    assert client.requests == []


def test_journal_failure_is_runner_fatal_not_a_policy_outcome(manifest):
    client = OfflineClient(eligible=set())
    events = []
    def sink(event):
        if event["slot_index"] == 1:
            raise OSError("journal corruption")
        events.append(event)
    with pytest.raises(PaperCollectionFatalError) as caught:
        execute_paper_collection(manifest, client, event_sink=sink)
    assert client.original_slots == [0]
    assert caught.value.evidence.scope is InfrastructureScope.PERSISTENCE
    assert not caught.value.evidence.policy_attributable
    assert caught.value.active_slot_index == 1
    assert len(caught.value.completed_slot_outcomes) == 1


def test_bundle_atomic_coherent_and_deterministic(tmp_path, manifest, collected):
    first, second = tmp_path / "first", tmp_path / "second"
    for target in (first, second):
        persist_paper_collection_run(run_root=target, manifest=manifest, result=collected, metadata=METADATA)
        validate_paper_collection_bundle(target)
    assert {item.name for item in first.iterdir()} == {"manifest.json", "run_metadata.json", "scheduled_attempts.jsonl", "arm_traces.jsonl", "collection_events.jsonl", "paper_collection_summary.json"}
    for item in first.iterdir():
        assert item.read_bytes() == (second / item.name).read_bytes()
    summary = json.loads((first / "paper_collection_summary.json").read_bytes())
    assert summary["scheduled_attempts"] == 160
    assert summary["arm_traces_persisted"] == 8
    assert summary["completion_status"] == "COMPLETE_RECORDED"
    assert not any(key in summary for key in ("p_value", "STATE_CORRECT", "risk_difference", "confidence_interval"))


def test_write_failure_never_publishes_partial_bundle(tmp_path, manifest, collected, monkeypatch):
    real_write = paper._write_bytes
    def fail(path, data):
        if path.name == "arm_traces.jsonl":
            raise OSError("atomic write fault")
        real_write(path, data)
    monkeypatch.setattr(paper, "_write_bytes", fail)
    with pytest.raises(OSError):
        persist_paper_collection_run(run_root=tmp_path / "failed", manifest=manifest, result=collected, metadata=METADATA)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mutation", ["manifest", "summary", "slot_count", "arm_id"])
def test_incoherent_result_rejected_before_any_directory(tmp_path, manifest, collected, mutation):
    with pytest.raises(PaperCollectionError):
        if mutation == "manifest":
            invalid = replace(collected, manifest_hash="0" * 64)
        elif mutation == "summary":
            invalid = replace(collected, summary=replace(collected.summary, activated_families=3))
        elif mutation == "slot_count":
            invalid = replace(collected, slot_outcomes=collected.slot_outcomes[:-1])
        else:
            arm = replace(collected.slot_outcomes[0].arm_executions[0], arm_id="wrong-arm")
            invalid_slot = replace(collected.slot_outcomes[0], arm_executions=(arm, *collected.slot_outcomes[0].arm_executions[1:]))
            invalid = replace(collected, slot_outcomes=(invalid_slot, *collected.slot_outcomes[1:]))
        persist_paper_collection_run(run_root=tmp_path / "invalid", manifest=manifest, result=invalid, metadata=METADATA)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mutation", ["duplicate_trace", "missing_trace", "trace_model", "trace_manifest"])
def test_bad_trace_linkage_rejected(tmp_path, manifest, collected, monkeypatch, mutation):
    real_traces = paper.paper_arm_traces_as_json
    def bad(result, metadata):
        traces = list(real_traces(result, metadata))
        if mutation == "duplicate_trace":
            traces.append(traces[0])
        elif mutation == "missing_trace":
            traces.pop()
        elif mutation == "trace_model":
            traces[0]["model"]["name"] = "wrong-model"
        else:
            traces[0]["identifiers"]["manifest_id"] = "wrong-manifest"
        return tuple(traces)
    monkeypatch.setattr(paper, "paper_arm_traces_as_json", bad)
    with pytest.raises(PaperCollectionError):
        persist_paper_collection_run(run_root=tmp_path / "invalid", manifest=manifest, result=collected, metadata=METADATA)
    assert list(tmp_path.iterdir()) == []


def test_partial_bundle_is_rejected(tmp_path):
    target = tmp_path / "partial"
    target.mkdir()
    with pytest.raises(PaperCollectionError, match="partial"):
        validate_paper_collection_bundle(target)


@pytest.mark.parametrize("field", ["manifest_sha256", "model_config_id", "family_id", "provider", "original_generation_seed", "terminal_status", "recovery_construction_started"])
def test_persisted_ledger_tampering_rejected(tmp_path, manifest, collected, field):
    target = tmp_path / "bundle"
    persist_paper_collection_run(run_root=target, manifest=manifest, result=collected, metadata=METADATA)
    records = [json.loads(line) for line in (target / "scheduled_attempts.jsonl").read_bytes().splitlines()]
    records[0][field] = (
        30001 if field == "original_generation_seed"
        else "INELIGIBLE" if field == "terminal_status"
        else False if field == "recovery_construction_started" else "forged"
    )
    (target / "scheduled_attempts.jsonl").write_bytes(b"".join(canonical_json_bytes(record) + b"\n" for record in records))
    with pytest.raises((PaperCollectionError, jsonschema.ValidationError)):
        validate_paper_collection_bundle(target)


def test_run_journal_persistence_failure_retains_noncompleted_prefix_and_refuses_resume(tmp_path, manifest, monkeypatch):
    real_write = paper._write_bytes
    def fail(path, data):
        if path.name == "paper_collection_summary.json":
            raise OSError("final persistence fault")
        real_write(path, data)
    monkeypatch.setattr(paper, "_write_bytes", fail)
    target = tmp_path / "run"
    client = OfflineClient(eligible=set())
    with pytest.raises(PaperCollectionFatalError) as caught:
        run_paper_collection(manifest=manifest, client=client, run_root=target, metadata=METADATA)
    assert not target.exists()
    progress = tmp_path / ".run.in-progress"
    assert progress.is_dir()
    assert len((progress / "collection_events.jsonl").read_bytes().splitlines()) == 480
    assert len((progress / "scheduled_attempts.jsonl").read_bytes().splitlines()) == 160
    assert (progress / "arm_traces.jsonl").read_bytes() == b""
    fatal = json.loads((progress / "runner_fatal.json").read_bytes())
    assert fatal["schema_version"] == "paper-runner-fatal-v1"
    assert fatal["terminal_status"] == "RUNNER_FATAL"
    assert fatal["completed_slots_in_memory"] == 160
    assert fatal["infrastructure_failure"]["scope"] == "PERSISTENCE"
    assert fatal["resume_permitted"] is False
    run_metadata = json.loads((progress / "run_metadata.json").read_bytes())
    assert fatal["git_commit"] == run_metadata["git_commit"] == METADATA.git_commit
    assert fatal["timestamp"] == run_metadata["timestamp"] == METADATA.timestamp
    assert caught.value.result.summary.scheduled_attempts == 160
    assert caught.value.evidence.scope is InfrastructureScope.PERSISTENCE
    another = OfflineClient()
    with pytest.raises(PaperCollectionPreflightError, match="never"):
        run_paper_collection(manifest=manifest, client=another, run_root=target, metadata=METADATA)
    assert another.requests == []


def test_successful_run_publishes_journal_and_removes_progress(tmp_path, manifest):
    target = tmp_path / "run"
    result = run_paper_collection(manifest=manifest, client=OfflineClient(eligible=set()), run_root=target, metadata=METADATA)
    assert result.summary.scheduled_attempts == 160
    assert not (tmp_path / ".run.in-progress").exists()
    validate_paper_collection_bundle(target)


def test_existing_target_fails_before_any_model_call(tmp_path, manifest):
    target = tmp_path / "existing"
    target.mkdir()
    client = OfflineClient()
    with pytest.raises(PaperCollectionError, match="exists"):
        run_paper_collection(manifest=manifest, client=client, run_root=target, metadata=METADATA)
    assert client.requests == []


def test_run_metadata_is_fsynced_before_first_boundary_and_model_call(tmp_path, manifest, monkeypatch):
    progress = tmp_path / ".run.in-progress"
    synced = set()
    real_fsync = paper.os.fsync
    def fsync(fd):
        real_fsync(fd)
        stat = os.fstat(fd)
        synced.add((stat.st_dev, stat.st_ino))
    monkeypatch.setattr(paper.os, "fsync", fsync)
    def assert_setup():
        for path in (progress / "manifest.json", progress / "run_metadata.json", progress, tmp_path):
            stat = path.stat()
            assert (stat.st_dev, stat.st_ino) in synced
        record = json.loads((progress / "run_metadata.json").read_bytes())
        assert record == {
            "schema_version": "paper-run-metadata-v1",
            "manifest_id": manifest.manifest_id,
            "manifest_sha256": manifest.manifest_hash,
            "paper_experiment_revision": "primary-create-v1.3",
            "execution_semantics_revision": "primary-create-v1.2",
            "git_commit": METADATA.git_commit,
            "timestamp": METADATA.timestamp,
        }
    real_execute = paper.execute_paper_collection
    def execute(*args, **kwargs):
        assert_setup()
        assert (progress / "collection_events.jsonl").read_bytes() == b""
        return real_execute(*args, **kwargs)
    monkeypatch.setattr(paper, "execute_paper_collection", execute)
    class SetupCheckingClient(OfflineClient):
        def complete(self, request):
            if not self.requests:
                assert_setup()
            return super().complete(request)
    client = SetupCheckingClient(eligible=set())
    run_paper_collection(manifest=manifest, client=client, run_root=tmp_path / "run", metadata=METADATA)
    assert client.original_slots == list(range(160))


def test_slot_zero_interruption_retains_independent_run_provenance(tmp_path, manifest):
    class InterruptedClient(OfflineClient):
        def complete(self, request):
            self.requests.append(request)
            raise KeyboardInterrupt("offline process interruption")
    client = InterruptedClient()
    target = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        run_paper_collection(manifest=manifest, client=client, run_root=target, metadata=METADATA)
    progress = tmp_path / ".run.in-progress"
    assert (progress / "manifest.json").read_bytes() == manifest.canonical_bytes
    record = json.loads((progress / "run_metadata.json").read_bytes())
    assert record["git_commit"] == METADATA.git_commit
    assert record["timestamp"] == METADATA.timestamp
    events = [json.loads(line) for line in (progress / "collection_events.jsonl").read_bytes().splitlines()]
    assert [event["event_type"] for event in events] == ["ATTEMPT_STARTED", "ORIGINAL_GENERATION_ATTEMPT_STARTED"]
    assert all(event["slot_index"] == 0 for event in events)
    assert (progress / "scheduled_attempts.jsonl").read_bytes() == b""
    assert not target.exists()
    assert not (progress / "paper_collection_summary.json").exists()
    assert len(client.requests) == 1


def test_completed_bundle_requires_run_metadata(tmp_path, manifest, collected):
    target = tmp_path / "bundle"
    persist_paper_collection_run(run_root=target, manifest=manifest, result=collected, metadata=METADATA)
    (target / "run_metadata.json").unlink()
    with pytest.raises(PaperCollectionError, match="partial"):
        validate_paper_collection_bundle(target)


@pytest.mark.parametrize("field,value", [
    ("git_commit", "c35be82"),
    ("git_commit", "A" * 40),
    ("timestamp", "2026-09-16T00:00:00"),
    ("timestamp", "2026-02-30T00:00:00Z"),
    ("timestamp", "2026-09-16 00:00:00+00:00"),
    ("manifest_id", "wrong-manifest"),
    ("manifest_sha256", "0" * 64),
    ("paper_experiment_revision", "primary-create-v1.2"),
    ("execution_semantics_revision", "primary-create-v1.3"),
])
def test_invalid_run_metadata_rejected(tmp_path, manifest, collected, field, value):
    target = tmp_path / "bundle"
    persist_paper_collection_run(run_root=target, manifest=manifest, result=collected, metadata=METADATA)
    record = json.loads((target / "run_metadata.json").read_bytes())
    record[field] = value
    (target / "run_metadata.json").write_bytes(canonical_json_bytes(record))
    with pytest.raises((PaperCollectionError, paper.TraceSerializationError, jsonschema.ValidationError)):
        validate_paper_collection_bundle(target)


@pytest.mark.parametrize("field,value", [
    ("git_commit", "a" * 40),
    ("timestamp", "2026-09-16T00:00:01+00:00"),
])
def test_trace_run_metadata_mismatch_rejected(tmp_path, manifest, collected, field, value):
    target = tmp_path / "bundle"
    persist_paper_collection_run(run_root=target, manifest=manifest, result=collected, metadata=METADATA)
    records = [json.loads(line) for line in (target / "arm_traces.jsonl").read_bytes().splitlines()]
    records[0][field] = value
    (target / "arm_traces.jsonl").write_bytes(paper._jsonl(tuple(records)))
    with pytest.raises(PaperCollectionError, match="incoherent"):
        validate_paper_collection_bundle(target)


def test_final_validation_precedes_progress_cleanup(tmp_path, manifest, monkeypatch):
    target = tmp_path / "run"
    progress = tmp_path / ".run.in-progress"
    sequence = []
    real_validate = paper.validate_paper_collection_bundle
    real_cleanup = paper.shutil.rmtree
    def validate(root):
        assert progress.is_dir()
        real_validate(root)
        sequence.append("validated")
    def cleanup(root, *args, **kwargs):
        assert Path(root) == progress
        assert sequence == ["validated"]
        sequence.append("cleanup")
        real_cleanup(root, *args, **kwargs)
    monkeypatch.setattr(paper, "validate_paper_collection_bundle", validate)
    monkeypatch.setattr(paper.shutil, "rmtree", cleanup)
    run_paper_collection(manifest=manifest, client=OfflineClient(eligible=set()), run_root=target, metadata=METADATA)
    assert sequence == ["validated", "cleanup"]


def test_final_validation_failure_retains_progress_and_raises_fatal(tmp_path, manifest, monkeypatch):
    target = tmp_path / "run"
    progress = tmp_path / ".run.in-progress"
    def fail(root):
        assert Path(root) == target and progress.is_dir()
        raise PaperCollectionError("offline post-publication validation failure")
    monkeypatch.setattr(paper, "validate_paper_collection_bundle", fail)
    client = OfflineClient(eligible=set())
    with pytest.raises(PaperCollectionFatalError) as caught:
        run_paper_collection(manifest=manifest, client=client, run_root=target, metadata=METADATA)
    assert target.is_dir() and progress.is_dir()
    assert (progress / "run_metadata.json").is_file()
    assert caught.value.evidence.scope is InfrastructureScope.PERSISTENCE
    assert client.original_slots == list(range(160))
    fatal = json.loads((progress / "runner_fatal.json").read_bytes())
    assert fatal["git_commit"] == METADATA.git_commit
    assert fatal["timestamp"] == METADATA.timestamp


def test_cleanup_failure_after_verified_publication_is_not_collection_failure(tmp_path, manifest, monkeypatch, caplog):
    target = tmp_path / "run"
    progress = tmp_path / ".run.in-progress"
    real_cleanup = paper.shutil.rmtree
    def fail(root, *args, **kwargs):
        if Path(root) == progress:
            raise OSError("offline redundant-directory cleanup failure")
        return real_cleanup(root, *args, **kwargs)
    monkeypatch.setattr(paper.shutil, "rmtree", fail)
    client = OfflineClient(eligible=set())
    result = run_paper_collection(manifest=manifest, client=client, run_root=target, metadata=METADATA)
    assert result.summary.completion_status.value == "COMPLETE_RECORDED"
    assert progress.is_dir() and not (progress / "runner_fatal.json").exists()
    validate_paper_collection_bundle(target)
    assert client.original_slots == list(range(160))
    assert len(client.requests) == 160
    assert "remains complete" in caplog.text


def test_frozen_engineering_schema_is_unchanged_and_fake_engineering_traces_still_valid():
    schema_path = Path(__file__).parents[1] / "research/protocol/trace_schema_v1.json"
    schema = json.loads(schema_path.read_bytes())
    assert schema["properties"]["experiment_version"] == {"const": "primary-create-v1.2"}
    assert schema["properties"]["schema_version"] == {"const": "trace-schema-v1"}
    assert "paper_provenance" not in schema["properties"]
    # Existing engineering runner tests validate all their traces against this
    # exact unchanged schema, including symmetric pair-exclusion behavior.
