from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from retry_semantics.environments.ticket import FrozenExecutableRequest, SourceStage, TicketEnvironment
from retry_semantics.experiment import build_fireworks_deepseek_paper_manifest
from retry_semantics.experiment.analysis_evidence import (
    AnalysisMeasurementBlocker, extract_ticket_analysis, opportunity_state,
    operational_rates, sensitivity_pair, state_indicators, traced_recovery_facts,
)
from retry_semantics.experiment.paper import PaperCollectionError, _ledger_counts, validate_paper_collection_bundle, _ArmEvidenceClient
from retry_semantics.experiment.paper_measurement import EVIDENCE_V2, capture_arm_measurement, extend_paper_trace
from retry_semantics.models.measurement import ProviderRequestDispatchEvidence
from retry_semantics.experiment.trace import TraceRunMetadata, paper_arm_trace_as_json
from retry_semantics.models import (
    ModelAssistantMessage, ModelRejectedGenerationError, ModelResponse,
    ModelResponseError, ModelToolCall, freeze_json_value, parse_tool_arguments_json, thaw_json_value,
)
from retry_semantics.models.fireworks import capture_fireworks_chat_completion, DEEPSEEK_V4_FLASH_0731_MODEL
from retry_semantics.runtime.exact_replay import EXACT_REPLAY
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.runtime.original_generation import run_v1_original_generation_attempt
from retry_semantics.runtime.regeneration import LLM_REGENERATION
from retry_semantics.runtime.scheduled_trial import prepare_eligible_scheduled_trial, execute_prepared_recovery_arm
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

INTENDED = {"customer_id":"synthetic-customer","title":"synthetic-title","description":"synthetic-description"}


def request(arguments=INTENDED, *, tool="create_ticket", call_id="synthetic-call"):
    return FrozenExecutableRequest.from_value({"tool":tool,"tool_call_id":call_id,"arguments":arguments})


@pytest.mark.parametrize("world,matching,wrong,expected", [
    ("H0",1,0,[1,0,0,0]), ("H0",0,0,[0,1,0,0]),
    ("H0",2,0,[0,0,1,0]), ("H1",1,0,[1,0,0,0]),
    ("H1",2,0,[0,0,1,0]), ("H0",0,1,[0,1,0,1]),
    ("H1",2,1,[0,0,1,1]), ("H1",1,1,[0,0,0,1]),
])
def test_authoritative_state_indicators(world,matching,wrong,expected):
    env = TicketEnvironment.empty()
    for i in range(matching):
        env.execute_request(request(call_id=f"match-{i}").serialized_request,
                            source_stage=SourceStage.ORIGINAL if world == "H1" and i == 0 else SourceStage.RECOVERY,
                            arm_id=None if world == "H1" and i == 0 else "synthetic-arm")
    for i in range(wrong):
        env.execute_request(request({**INTENDED,"title":"wrong"},call_id=f"wrong-{i}").serialized_request,
                            source_stage=SourceStage.RECOVERY,arm_id="synthetic-arm")
    result = state_indicators(env.snapshot_bytes(),env.snapshot_hash(),INTENDED)
    assert [result[k] for k in ("STATE_CORRECT","MISSING_MUTATION","DUPLICATE_MUTATION","WRONG_MUTATION")] == expected


def test_unavailable_state_is_null_and_bad_hash_rejected():
    assert all(x is None for x in state_indicators(None,None,INTENDED).values())
    with pytest.raises(ValueError):
        state_indicators(TicketEnvironment.empty().snapshot_bytes(),"0"*64,INTENDED)


def tool(raw, name="create_ticket", call_id="synthetic-call"):
    success,parsed,error = parse_tool_arguments_json(raw)
    return ModelToolCall(call_id,name,raw,success,parsed,error,"function")


class ScriptedClient:
    """In-memory returned objects only; no provider adapter/transport calls."""
    provider = "fireworks"

    def __init__(self, scripts):
        self.scripts = iter(scripts)
        self.last_request_dispatch_evidence = ProviderRequestDispatchEvidence(0)

    def complete(self, request):
        self.last_request_dispatch_evidence = ProviderRequestDispatchEvidence(
            self.last_request_dispatch_evidence.invocation_sequence + 1, True, True)
        value = next(self.scripts)
        if isinstance(value,Exception):
            raise value
        return ModelResponse(ModelAssistantMessage("assistant",None,tuple(value)),
                             "tool_calls" if value else "stop",self.provider,
                             request.model_config.model,"synthetic-model",None,None,"synthetic-response")


def trace_fixture(policy,world,scripts):
    # Exactly one synthetic original generation and one synthetic arm, never a
    # 160-slot collector or engineering run. The trace uses the frozen serializer.
    entry = build_fireworks_deepseek_paper_manifest().entries[0]
    original = run_v1_original_generation_attempt(
        ScriptedClient([[tool(json.dumps(entry.scenario.task_spec.expected_arguments.as_dict()))]]),
        task_spec=entry.plan.task_spec, model_config=entry.original_generation_config)
    prepared = prepare_eligible_scheduled_trial(plan=entry.plan,original_generation=original,initial_state=TicketEnvironment.empty())
    client = _ArmEvidenceClient(ScriptedClient(scripts),EVIDENCE_V2)
    result = execute_prepared_recovery_arm(prepared,hidden_world=world,policy=policy,
                                          client=client,regeneration_config=entry.regeneration_config)
    trace = paper_arm_trace_as_json(entry=entry,prepared=prepared,hidden_world=world,policy=policy,
                                   arm_result=result,metadata=TraceRunMetadata("0"*40,"2026-09-16T00:00:00Z"))
    return extend_paper_trace(trace,capture_arm_measurement(prepared,world,policy,client,result)),entry


@pytest.mark.parametrize("policy,world,scripts,cost,observation,valid,budget,rejected", [
    (EXACT_REPLAY,HiddenWorld.NOT_EXECUTED,[],[0,0,1,1],None,1,None,None),
    (LLM_REGENERATION,HiddenWorld.NOT_EXECUTED,[[]],[1,0,0,0],0,1,0,0),
    (LLM_REGENERATION,HiddenWorld.EXECUTED_ACK_LOST,[[tool("{}","list_tickets")],[]],[2,1,0,1],1,1,0,0),
    (LLM_REGENERATION,HiddenWorld.NOT_EXECUTED,[[tool('{"customer_id":')]], [1,0,0,0],0,0,0,0),
    (LLM_REGENERATION,HiddenWorld.NOT_EXECUTED,[[tool("{}","list_tickets",f"read-{i}") for i in range(4)]], [1,3,0,3],1,0,1,0),
    (LLM_REGENERATION,HiddenWorld.NOT_EXECUTED,[ModelRejectedGenerationError("fireworks","tool_use_failed",freeze_json_value({"unparsed":"synthetic"}),"synthetic-id")],[1,0,0,0],0,0,0,1),
])
def test_structured_traced_behavior_and_cost(policy,world,scripts,cost,observation,valid,budget,rejected):
    trace,_ = trace_fixture(policy,world,scripts)
    facts = traced_recovery_facts(trace)
    assert [facts[k] for k in ("model_calls_issued","read_only_tool_calls_executed","state_mutating_tool_calls_executed","recovery_tool_calls_executed")] == cost
    assert facts["OBSERVATION_BEFORE_WRITE"] == observation
    assert facts["PROTOCOL_VALID_RECOVERY"] == valid
    assert facts["BUDGET_EXHAUSTED"] == budget
    assert facts["REJECTED_GENERATION"] == rejected
    assert facts["MALFORMED_GENERATION"] == (None if policy == EXACT_REPLAY else int(trace["termination_reason"] == "invalid_model_tool_call"))
    # Invalid behavior remains state-evaluable under the structured V2 mapping.
    assert trace["evaluator_only"]["final_state"] is not None


@pytest.mark.parametrize("read_first", [True,False])
def test_read_create_and_create_first_cost(read_first):
    entry = build_fireworks_deepseek_paper_manifest().entries[0]
    create = tool(json.dumps(entry.scenario.task_spec.expected_arguments.as_dict()))
    calls = [tool("{}","list_tickets"),create] if read_first else [create,tool("{}","list_tickets")]
    trace,_ = trace_fixture(LLM_REGENERATION,HiddenWorld.NOT_EXECUTED,[calls,[]])
    facts = traced_recovery_facts(trace)
    assert facts["OBSERVATION_BEFORE_WRITE"] == int(read_first)
    assert facts["recovery_tool_calls_executed"] == 2


def test_protocol_valid_can_be_state_incorrect():
    trace,entry = trace_fixture(LLM_REGENERATION,HiddenWorld.NOT_EXECUTED,[[]])
    assert traced_recovery_facts(trace)["PROTOCOL_VALID_RECOVERY"] == 1
    intended = entry.scenario.task_spec.expected_arguments.as_dict()
    assert state_indicators(canonical_json_bytes(trace["evaluator_only"]["final_state"]),trace["evaluator_only"]["final_state_hash"],intended)["STATE_CORRECT"] == 0


def test_infrastructure_trace_costs_fail_closed():
    trace,_ = trace_fixture(EXACT_REPLAY,HiddenWorld.NOT_EXECUTED,[])
    trace["evaluator_only"]["evaluation"]["infrastructure_failure"] = True
    with pytest.raises(AnalysisMeasurementBlocker):
        traced_recovery_facts(trace)


def test_no_text_classification():
    trace,_ = trace_fixture(LLM_REGENERATION,HiddenWorld.NOT_EXECUTED,[[]])
    baseline = traced_recovery_facts(trace)
    trace["errors"] = [{"message":"action_budget_exceeded rejected_generation malformed"}]
    trace["recovery_actions"][0]["assistant_content"] = "action_budget_exceeded"
    assert traced_recovery_facts(trace) == baseline


def test_adapter_structured_failure_stage_collision():
    base = {"choices":[{"message":{"role":"assistant","content":None,"tool_calls":[
        {"id":"synthetic","type":"function","function":{"name":"create_ticket","arguments":42}}]},"finish_reason":"tool_calls"}]}
    reasoning = copy.deepcopy(base)
    reasoning["choices"][0]["message"]["reasoning_content"] = "synthetic hidden content"
    retained = []
    for raw in (base,reasoning):
        with pytest.raises(ModelResponseError) as caught:
            capture_fireworks_chat_completion(raw,requested_model=DEEPSEEK_V4_FLASH_0731_MODEL)
        retained.append(canonical_json_bytes(thaw_json_value(caught.value.structured_evidence)))
    # Historical sanitized structures still collide; V2 category/stage separates
    # these paths prospectively without classifying their messages.
    assert retained[0] == retained[1]


def test_dispatch_does_not_prove_execution():
    env = TicketEnvironment.empty()
    with pytest.raises(ValueError):
        env.execute_request(request(tool="list_tickets",arguments={}).serialized_request,
                            source_stage=SourceStage.RECOVERY,arm_id="synthetic",expected_request_hash="0"*64)
    assert env.dispatch_count == 1
    assert env.snapshot_bytes() == TicketEnvironment.empty().snapshot_bytes()


def failure(scope="ARM"):
    return {"scope":scope,"policy_attributable":scope=="ARM"}


@pytest.mark.parametrize("a,b,expected", [
    (failure(),None,[0,1]), (None,failure(),[1,0]),
    (failure(),failure(),[0,0]), (failure("FAMILY_SYSTEM"),None,None),
])
def test_arm_attribution_sensitivity(a,b,expected):
    assert sensitivity_pair({"infrastructure_failure":a,"STATE_CORRECT":1,"BEHAVIORALLY_EVALUABLE_ARM":int(a is None)},
                            {"infrastructure_failure":b,"STATE_CORRECT":1,"BEHAVIORALLY_EVALUABLE_ARM":int(b is None)}) == expected


def test_missing_noninfra_state_is_not_sensitivity_zero():
    assert sensitivity_pair({"infrastructure_failure":None,"STATE_CORRECT":None,"BEHAVIORALLY_EVALUABLE_ARM":0},
                            {"infrastructure_failure":None,"STATE_CORRECT":1,"BEHAVIORALLY_EVALUABLE_ARM":1}) is None


def jsonl(records):
    return b"".join(canonical_json_bytes(r)+b"\n" for r in records)


@pytest.fixture
def synthetic_bundle(tmp_path):
    """Hand-built 160 terminal ledger records, no experiment execution."""
    manifest = build_fireworks_deepseek_paper_manifest()
    metadata = {"schema_version":"paper-run-metadata-v1","manifest_id":manifest.manifest_id,
                "manifest_sha256":manifest.manifest_hash,"paper_experiment_revision":"primary-create-v1.3",
                "execution_semantics_revision":"primary-create-v1.2","git_commit":"0"*40,"timestamp":"2026-09-16T00:00:00Z"}
    attempts,events = [],[]
    for entry in manifest.entries:
        i = entry.scheduled_attempt_index
        arms = [{"arm_id":entry.plan.arm_id(w,p),"hidden_world":w.value,"policy":p,
                 "attempted":False,"status":"NOT_ACTIVATED","trace_expected":False,
                 "infrastructure_failure":None,"pre_trace_evidence":None}
                for w in entry.plan.hidden_world_order for p in entry.plan.arm_order(w)]
        attempts.append({
            "schema_version":"paper-scheduled-attempt-v1",**{k:metadata[k] for k in ("manifest_id","manifest_sha256","paper_experiment_revision","execution_semantics_revision")},
            "manifest_kind":"paper","slot_index":i,"replicate":entry.replicate,"scenario_id":entry.scenario_id,"stratum":entry.schedule_stratum.value,
            "model_config_id":entry.model_config.model_config_id,"original_generation_seed":30000+i,"regeneration_base_seed":40000+10*i,
            "provider":"fireworks","requested_model":entry.original_generation_config.model,
            "attempt_started":True,"original_generation_attempted":True,
            "eligibility":{"taxonomy_version":"original-generation-eligibility-v1","outcome":"INELIGIBLE_BEHAVIORAL","ineligibility_reason":"NO_TOOL_CALL","detail":None},
            "original_generation_evidence":{},"original_generation_infrastructure":None,
            "reserved_base_trial_id":entry.plan.base_trial_id,"reserved_trial_family_id":entry.plan.trial_family_id,
            "trial_family_activated":False,"family_id":None,"recovery_construction_started":False,
            "expected_arm_opportunities_attempted":False,"family_system_failure":None,
            "arm_opportunities":arms,"terminal_status":"INELIGIBLE"})
        for event_type in ("ATTEMPT_STARTED","ORIGINAL_GENERATION_ATTEMPT_STARTED","SCHEDULED_ATTEMPT_TERMINATED"):
            events.append({"schema_version":"paper-collection-event-v1","event_sequence":len(events)+1,
                           **{k:metadata[k] for k in ("manifest_id","manifest_sha256","paper_experiment_revision","execution_semantics_revision")},
                           "slot_index":i,"event_type":event_type,"arm_id":None,
                           "terminal_status":"INELIGIBLE" if event_type=="SCHEDULED_ATTEMPT_TERMINATED" else None})
    summary = {"schema_version":"paper-collection-summary-v1",
               **{k:metadata[k] for k in ("manifest_id","manifest_sha256","paper_experiment_revision","execution_semantics_revision")},
               "manifest_kind":"paper","model_identities":[manifest.entries[0].model_config.model.as_trace_model()],
               **_ledger_counts(tuple(attempts)),"completion_status":"COMPLETE_RECORDED",
               "collection_events":len(events),"collection_events_sha256":sha256_hex(jsonl(events))}
    root = tmp_path / "synthetic-bundle"
    root.mkdir()
    for name,data in {"manifest.json":manifest.canonical_bytes,"run_metadata.json":canonical_json_bytes(metadata),
                      "scheduled_attempts.jsonl":jsonl(attempts),"arm_traces.jsonl":b"",
                      "collection_events.jsonl":jsonl(events),"paper_collection_summary.json":canonical_json_bytes(summary)}.items():
        (root/name).write_bytes(data)
    validate_paper_collection_bundle(root)
    return root


def test_validated_input_blocker_writes_nothing(synthetic_bundle,tmp_path):
    before = {p.name:sha256_hex(p.read_bytes()) for p in synthetic_bundle.iterdir()}
    for _ in range(2):
        with pytest.raises(PaperCollectionError,match="requires paper-collection-evidence-v2"):
            extract_ticket_analysis(synthetic_bundle,tmp_path / "analysis")
    assert before == {p.name:sha256_hex(p.read_bytes()) for p in synthetic_bundle.iterdir()}
    assert not (tmp_path / "analysis").exists()


@pytest.mark.parametrize("mutation", ["missing","wrong_manifest","wrong_provider","wrong_revision","provenance","extra"])
def test_bad_completed_input_rejected(synthetic_bundle,tmp_path,mutation):
    if mutation == "missing":
        (synthetic_bundle/"collection_events.jsonl").unlink()
    elif mutation == "extra":
        (synthetic_bundle/"unexpected.json").write_text("{}")
    else:
        name = "manifest.json" if mutation in ("wrong_manifest","wrong_provider","wrong_revision") else "run_metadata.json"
        record = json.loads((synthetic_bundle/name).read_bytes())
        if mutation == "wrong_manifest":
            record["manifest_id"] = "wrong-manifest"
        elif mutation == "wrong_provider":
            record["entries"][0]["model_config"]["model"]["provider"] = "wrong-provider"
        elif mutation == "wrong_revision":
            record["execution_semantics_revision"] = "wrong-revision"
        else:
            record["manifest_sha256"] = "0"*64
        (synthetic_bundle/name).write_bytes(canonical_json_bytes(record))
    with pytest.raises((PaperCollectionError,ValueError)):
        extract_ticket_analysis(synthetic_bundle,tmp_path/"analysis")
    assert not (tmp_path/"analysis").exists()


def test_in_progress_and_overlapping_output_rejected(synthetic_bundle,tmp_path):
    progress = tmp_path/"synthetic.in-progress"
    synthetic_bundle.rename(progress)
    with pytest.raises(PaperCollectionError):
        extract_ticket_analysis(progress,tmp_path/"analysis")
    with pytest.raises(ValueError):
        extract_ticket_analysis(progress,progress/"analysis")


def test_operational_denominators_include_eligible_prearm_failures(synthetic_bundle):
    records = [json.loads(line) for line in (synthetic_bundle/"scheduled_attempts.jsonl").read_bytes().splitlines()]
    records[0]["original_generation_infrastructure"] = {"scope":"ORIGINAL_GENERATION","policy_attributable":False}
    records[0]["eligibility"]["outcome"] = "INFRASTRUCTURE_FAILURE"
    for i in (1,2):
        records[i]["eligibility"]["outcome"] = "ELIGIBLE"
    records[1]["family_system_failure"] = failure("FAMILY_SYSTEM")
    records[2]["arm_opportunities"][0]["infrastructure_failure"] = failure()
    result = operational_rates(records)
    assert result["eligibility"] == {"numerator":2,"denominator":160,"rate":0.0125}
    assert result["original_generation_infrastructure_failure"]["denominator"] == 160
    assert result["original_generation_infrastructure_failure"]["numerator"] == 1
    assert result["pre_arm_system_family_failures"] == 1
    assert all(r["denominator"] == 2 for policies in result["recovery_infrastructure_failure"].values() for r in policies.values())
    assert sum(r["numerator"] for policies in result["recovery_infrastructure_failure"].values() for r in policies.values()) == 1


def test_state_correct_independent_of_arm_infrastructure():
    trace,entry = trace_fixture(EXACT_REPLAY,HiddenWorld.NOT_EXECUTED,[])
    arm = {"arm_id":trace["identifiers"]["arm_id"],"hidden_world":"NOT_EXECUTED","policy":EXACT_REPLAY,
           "status":"INFRASTRUCTURE_FAILURE_BEFORE_TRACE","infrastructure_failure":failure(),
           "pre_trace_evidence":{"authoritative_final_state_snapshot":canonical_json_bytes(trace["evaluator_only"]["final_state"]).decode(),
                                 "authoritative_final_state_sha256":trace["evaluator_only"]["final_state_hash"]}}
    attempt = {"slot_index":0,"replicate":1,"scenario_id":entry.scenario_id,"stratum":"A",
               "family_id":trace["identifiers"]["trial_family_id"],"reserved_trial_family_id":trace["identifiers"]["trial_family_id"],"family_system_failure":None}
    scenario = {"customer_id":entry.scenario.customer_id,"expected_title":entry.scenario.expected_title,"expected_description":entry.scenario.expected_description}
    assert opportunity_state(attempt,arm,None,scenario)["STATE_CORRECT"] == 1
    # Runtime correct and exclusion flags have no role in state-only derivation.
    trace["evaluator_only"]["evaluation"]["correct"] = False
    assert opportunity_state(attempt,arm,trace,scenario)["STATE_CORRECT"] == 1
