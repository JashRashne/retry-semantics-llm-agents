"""Synthetic measurement-only fixtures; no network or real provider credentials."""

import copy
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import httpx
import pytest

import retry_semantics.experiment.paper as paper
from retry_semantics.environments.ticket import TicketEnvironment, SourceStage
from retry_semantics.experiment.paper_measurement import EVIDENCE_V1, EVIDENCE_V2, arm_environment
from retry_semantics.models import (
    ModelAssistantMessage, ModelRequestError, ModelResponseError, ModelTimeoutError,
    capture_fireworks_chat_completion, model_request_from_regeneration_context,
    thaw_json_value,
)
from retry_semantics.models.measurement import ProviderRequestDispatchEvidence
from retry_semantics.runtime.exact_replay import EXACT_REPLAY
from retry_semantics.runtime.regeneration import LLM_REGENERATION
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from test_fireworks_adapter import _completion, _mock_client, _request
from test_paper_collection import OfflineClient, METADATA, call


class MeasuredOfflineClient(OfflineClient):
    """Explicit simulated transport facts; never connects to any provider."""
    def __init__(self, *, scripts=None, **kwargs):
        super().__init__(**kwargs)
        self.scripts = scripts or {}
        self._measurement = ProviderRequestDispatchEvidence(0)

    @property
    def last_request_dispatch_evidence(self):
        return self._measurement

    def complete(self, request):
        sequence = self._measurement.invocation_sequence + 1
        self._measurement = ProviderRequestDispatchEvidence(sequence)
        is_original = len(request.messages) == 2
        slot = request.model_config.seed - 30000 if is_original else (request.model_config.seed - 40000)//10
        ordinal = None if is_original else self.recovery_counts[slot]
        scripted = self.scripts.get((slot,ordinal))
        if isinstance(scripted,ModelRequestError):
            raise scripted
        self._measurement = ProviderRequestDispatchEvidence(sequence,True)
        try:
            response = super().complete(request)
            if isinstance(scripted,Exception):
                raise scripted
        except ModelTimeoutError:
            raise
        except Exception:
            self._measurement = ProviderRequestDispatchEvidence(sequence,True,True)
            raise
        self._measurement = ProviderRequestDispatchEvidence(sequence,True,True)
        if scripted is not None:
            response = replace(response,assistant_message=ModelAssistantMessage("assistant","offline response",tuple(scripted)),
                               finish_reason="tool_calls" if scripted else "stop")
        return response


@pytest.fixture(scope="module")
def manifest():
    return paper_manifest()


def paper_manifest():
    from retry_semantics.experiment import build_fireworks_deepseek_paper_manifest
    return build_fireworks_deepseek_paper_manifest()


def adapter_failure(completion, model=None):
    from retry_semantics.models import DEEPSEEK_V4_FLASH_0731_MODEL
    with pytest.raises(ModelResponseError) as caught:
        capture_fireworks_chat_completion(completion,requested_model=model or DEEPSEEK_V4_FLASH_0731_MODEL)
    return caught.value


@pytest.mark.parametrize("raw,category,stage", [
    (_completion(tool_calls=[{"id":"call","type":"function","function":{"name":"create_ticket","arguments":42}}]),"MODEL_GENERATION_STRUCTURE","TOOL_CALL_ARGUMENTS"),
    (_completion(reasoning_content="synthetic secret reasoning"),"PROTOCOL_COMPATIBILITY","REASONING_POLICY"),
    ({"choices":"not-a-list"},"PROVIDER_RESPONSE_STRUCTURE","COMPLETION_ENVELOPE"),
    (_completion(tool_calls={}),"MODEL_GENERATION_STRUCTURE","TOOL_CALL_LIST"),
    (_completion(content=42),"MODEL_GENERATION_STRUCTURE","ASSISTANT_CONTENT"),
    (_completion(model=42),"PROVIDER_RESPONSE_STRUCTURE","COMPLETION_MODEL"),
])
def test_nontextual_adapter_taxonomy(raw,category,stage):
    error = adapter_failure(raw)
    assert error.response_failure.category == category
    assert error.response_failure.stage == stage
    assert "synthetic secret reasoning" not in canonical_json_bytes(thaw_json_value(error.structured_evidence)).decode()
    with pytest.raises(FrozenInstanceError):
        error.response_failure.stage = "changed"


def test_hostile_collision_is_distinguishable_without_text():
    raw = _completion(tool_calls=[{"id":"call","type":"function","function":{"name":"create_ticket","arguments":42}}])
    reasoning = copy.deepcopy(raw)
    reasoning["choices"][0]["message"]["reasoning_content"] = "synthetic hidden text"
    arguments_error,reasoning_error = adapter_failure(raw),adapter_failure(reasoning)
    assert thaw_json_value(arguments_error.structured_evidence) == thaw_json_value(reasoning_error.structured_evidence)
    assert arguments_error.response_failure.as_dict() != reasoning_error.response_failure.as_dict()
    assert "reasoning_content" not in canonical_json_bytes(thaw_json_value(reasoning_error.structured_evidence)).decode()


@pytest.mark.parametrize("status", [200,400,401,403,429,500])
def test_http_transport_dispatch_evidence(make_request,status):
    attempts = []
    def handler(request):
        attempts.append(request)
        return httpx.Response(status,json=_completion())
    client = _mock_client(handler)
    try:
        if status == 200:
            client.complete(_request(make_request))
        else:
            with pytest.raises(Exception):
                client.complete(_request(make_request))
        evidence = client.last_request_dispatch_evidence
        assert evidence == ProviderRequestDispatchEvidence(1,True,True)
        assert len(attempts) == 1
    finally:
        client.close()


@pytest.mark.parametrize("error", [httpx.ReadTimeout("synthetic"),httpx.ConnectError("synthetic")])
def test_timeout_connection_dispatched_without_receipt_claim(make_request,error):
    attempts = []
    def handler(request):
        attempts.append(request)
        raise error
    client = _mock_client(handler)
    try:
        with pytest.raises(Exception):
            client.complete(_request(make_request))
        assert client.last_request_dispatch_evidence == ProviderRequestDispatchEvidence(1,True,False)
        assert len(attempts) == 1
    finally:
        client.close()


def test_local_validation_and_closed_client_are_not_transport_attempts(make_request):
    attempts = []
    client = _mock_client(lambda req: attempts.append(req))
    try:
        with pytest.raises(ModelRequestError):
            client.complete(_request(make_request,provider_parameters={"unsupported":"value"}))
        assert client.last_request_dispatch_evidence == ProviderRequestDispatchEvidence(1,False,False)
        assert attempts == []
        client.close()
        with pytest.raises(RuntimeError):
            client.complete(_request(make_request))
        assert client.last_request_dispatch_evidence == ProviderRequestDispatchEvidence(2,False,False)
    finally:
        client.close()


def test_200_capture_failure_has_exact_dispatch_fact(make_request):
    raw = _completion(tool_calls=[{"id":"call","type":"function","function":{"name":"create_ticket","arguments":42}}])
    client = _mock_client(lambda req:httpx.Response(200,json=raw))
    try:
        with pytest.raises(ModelResponseError) as caught:
            client.complete(_request(make_request))
        assert caught.value.response_failure.category == "MODEL_GENERATION_STRUCTURE"
        assert client.last_request_dispatch_evidence == ProviderRequestDispatchEvidence(1,True,True)
    finally:
        client.close()


def test_non_json_success_body_is_provider_structure(make_request):
    client = _mock_client(lambda req:httpx.Response(200,content=b"not-json"))
    try:
        with pytest.raises(ModelResponseError) as caught:
            client.complete(_request(make_request))
        assert caught.value.response_failure.stage == "NON_JSON_SUCCESS_BODY"
        assert caught.value.response_failure.category == "PROVIDER_RESPONSE_STRUCTURE"
        assert client.last_request_dispatch_evidence.provider_request_dispatched is True
    finally:
        client.close()


def test_successful_execution_journal_is_operational_only(make_request):
    env = TicketEnvironment.empty()
    before = env.snapshot_bytes()
    read = make_request(tool="list_tickets",tool_call_id="read")
    create = make_request(tool_call_id="create")
    with pytest.raises(ValueError):
        env.execute_request(read.serialized_request,source_stage=SourceStage.RECOVERY,arm_id="arm",expected_request_hash="0"*64)
    assert env.dispatch_count == 1 and env.successful_execution_journal == ()
    observation = env.execute_request(read.serialized_request,source_stage=SourceStage.RECOVERY,arm_id="arm")
    assert observation == b'{"tickets":[]}'
    assert env.snapshot_bytes() == before
    env.execute_request(create.serialized_request,source_stage=SourceStage.RECOVERY,arm_id="arm")
    journal = env.successful_execution_journal
    assert [e.execution_sequence for e in journal] == [1,2]
    assert [e.tool for e in journal] == ["list_tickets","create_ticket"]
    assert [e.mutating for e in journal] == [False,True]
    assert [e.tool_call_id for e in journal] == ["read","create"]
    assert [e.request_hash for e in journal] == [read.request_hash,create.request_hash]
    assert env.dispatch_count == 3
    with pytest.raises(FrozenInstanceError):
        journal[0].mutating = True
    clone = TicketEnvironment.clone_from_snapshot(env.snapshot_bytes())
    assert clone.successful_execution_journal == () and clone.dispatch_count == 0
    assert clone.snapshot_bytes() == env.snapshot_bytes()
    assert clone.snapshot_hash() == env.snapshot_hash()
    assert b"successful" not in env.snapshot_bytes() and b"request_hash" not in observation
    # Direct frozen state transition supplies an independent snapshot comparison
    # without involving operational journal construction.
    reference = TicketEnvironment.empty()
    reference._commit_create(json.loads(create.serialized_request),create.serialized_request,SourceStage.RECOVERY,"arm")
    assert reference.snapshot_bytes() == env.snapshot_bytes()


def collect(manifest,client):
    return paper.execute_paper_collection(manifest,client,evidence_revision=EVIDENCE_V2)


def h0_arm(result,policy):
    return next(a for a in result.slot_outcomes[0].arm_executions if a.hidden_world is HiddenWorld.NOT_EXECUTED and a.policy == policy)


def persist_and_validate(tmp_path,manifest,result):
    root = tmp_path/"v2-bundle"
    paper.persist_paper_collection_run(run_root=root,manifest=manifest,result=result,metadata=METADATA)
    paper.validate_paper_collection_bundle(root)
    assert len(list(root.iterdir())) == 6
    assert json.loads((root/"run_metadata.json").read_bytes())["collection_evidence_revision"] == EVIDENCE_V2
    return root


def test_read_then_pretrace_failure_prefix(tmp_path,manifest,monkeypatch):
    original = paper.execute_prepared_recovery_arm
    def fail_after_read(prepared,**kwargs):
        if prepared.plan.scheduled_attempt_ordinal==0 and kwargs["hidden_world"] is HiddenWorld.NOT_EXECUTED and kwargs["policy"]==LLM_REGENERATION:
            req = model_request_from_regeneration_context(prepared.regeneration_context,kwargs["regeneration_config"])
            kwargs["client"].complete(req)
            from retry_semantics.environments.ticket import FrozenExecutableRequest
            read = FrozenExecutableRequest.from_value({"tool":"list_tickets","tool_call_id":"read","arguments":{}})
            env = arm_environment(prepared,kwargs["hidden_world"],kwargs["policy"])
            env.execute_request(read.serialized_request,source_stage=SourceStage.RECOVERY,arm_id=prepared.plan.arm_id(kwargs["hidden_world"],kwargs["policy"]))
            raise RuntimeError("synthetic escaped failure after successful read")
        return original(prepared,**kwargs)
    monkeypatch.setattr(paper,"execute_prepared_recovery_arm",fail_after_read)
    result = collect(manifest,MeasuredOfflineClient(scripts={(0,0):[call("{}",tool="list_tickets",call_id="read")]}))
    evidence = thaw_json_value(h0_arm(result,LLM_REGENERATION).pre_trace_evidence)
    assert evidence["evidence_version"] == "pre-trace-arm-boundary-v2"
    assert evidence["model_calls_issued"] == 1
    assert [e["tool"] for e in evidence["successful_tool_executions"]] == ["list_tickets"]
    assert evidence["authoritative_final_state_snapshot"] is not None
    persist_and_validate(tmp_path,manifest,result)


def test_replay_failure_before_execution_has_empty_cost_prefix(tmp_path,manifest,monkeypatch):
    original = paper.execute_prepared_recovery_arm
    def fail_replay(prepared,**kwargs):
        if prepared.plan.scheduled_attempt_ordinal==0 and kwargs["hidden_world"] is HiddenWorld.NOT_EXECUTED and kwargs["policy"]==EXACT_REPLAY:
            raise RuntimeError("synthetic failure before dispatch")
        return original(prepared,**kwargs)
    monkeypatch.setattr(paper,"execute_prepared_recovery_arm",fail_replay)
    result = collect(manifest,MeasuredOfflineClient())
    measurement = thaw_json_value(h0_arm(result,EXACT_REPLAY).measurement_evidence)
    assert measurement["model_invocations"] == measurement["successful_tool_executions"] == []
    persist_and_validate(tmp_path,manifest,result)


def test_model_timeout_after_read_has_exact_prefix(tmp_path,manifest):
    result = collect(manifest,MeasuredOfflineClient(scripts={(0,0):[call("{}",tool="list_tickets")],(0,1):ModelTimeoutError("synthetic timeout")}))
    arm = h0_arm(result,LLM_REGENERATION)
    measurement = thaw_json_value(arm.measurement_evidence)
    assert sum(i["provider_request_dispatched"] for i in measurement["model_invocations"]) == 2
    assert [i["provider_response_returned"] for i in measurement["model_invocations"]] == [True,False]
    assert [e["mutating"] for e in measurement["successful_tool_executions"]] == [False]
    assert arm.result.final_state_snapshot is not None
    persist_and_validate(tmp_path,manifest,result)


@pytest.mark.parametrize("category", ["MODEL_GENERATION_STRUCTURE","PROTOCOL_COMPATIBILITY","PROVIDER_RESPONSE_STRUCTURE"])
def test_adapter_failure_prefix_is_durable_and_structured(tmp_path,manifest,category):
    raw = (_completion(tool_calls=[{"id":"call","type":"function","function":{"name":"create_ticket","arguments":42}}])
           if category=="MODEL_GENERATION_STRUCTURE" else _completion(reasoning_content="synthetic reasoning")
           if category=="PROTOCOL_COMPATIBILITY" else {"choices":"bad"})
    result = collect(manifest,MeasuredOfflineClient(scripts={(0,0):adapter_failure(raw)}))
    arm = h0_arm(result,LLM_REGENERATION)
    measurement = thaw_json_value(arm.measurement_evidence)
    assert measurement["model_invocations"][0]["provider_request_dispatched"] is True
    assert measurement["model_invocations"][0]["response_failure"]["category"] == category
    assert measurement["successful_tool_executions"] == []
    assert arm.result.termination_reason == "infrastructure_failure" # frozen runtime classification
    assert arm.result.final_state_snapshot is not None
    root = persist_and_validate(tmp_path,manifest,result)
    assert b"synthetic reasoning" not in (root/"arm_traces.jsonl").read_bytes()


def test_local_request_failure_pretrace_dispatch_zero(tmp_path,manifest):
    result = collect(manifest,MeasuredOfflineClient(scripts={(0,0):ModelRequestError("synthetic local validation")}))
    arm = h0_arm(result,LLM_REGENERATION)
    evidence = thaw_json_value(arm.pre_trace_evidence)
    assert evidence["model_calls_issued"] == 0
    assert len(evidence["model_invocations"]) == 1
    assert evidence["successful_tool_executions"] == []
    persist_and_validate(tmp_path,manifest,result)


def test_internal_parse_incoherence_classification_is_preserved(tmp_path,manifest):
    broken = call('{"customer_id":')
    object.__setattr__(broken,"parse_success",True)
    result = collect(manifest,MeasuredOfflineClient(scripts={(0,0):[broken]}))
    measurement = thaw_json_value(h0_arm(result,LLM_REGENERATION).measurement_evidence)
    failure = measurement["model_invocations"][0]["response_failure"]
    assert failure["category"] == "IMPLEMENTATION_INCOHERENCE"
    assert failure["stage"] == "RECOVERY_PARSE_METADATA"
    persist_and_validate(tmp_path,manifest,result)


def test_v1_v2_model_visible_and_treatment_evidence_are_identical(manifest):
    scripts = {(0,0):[call("{}",tool="list_tickets")],(0,1):[]}
    old = paper.execute_paper_collection(manifest,MeasuredOfflineClient(scripts=scripts),evidence_revision=EVIDENCE_V1)
    new = collect(manifest,MeasuredOfflineClient(scripts=scripts))
    for a,b in zip(paper.paper_arm_traces_as_json(old,METADATA),paper.paper_arm_traces_as_json(new,METADATA),strict=True):
        assert canonical_json_bytes(a["model_visible"]) == canonical_json_bytes(b["model_visible"])
        b = copy.deepcopy(b)
        b.pop("measurement_evidence")
        b["schema_version"] = "trace-schema-paper-v1"
        b["paper_provenance"].pop("collection_evidence_revision")
        b["paper_provenance"]["schema_version"] = "paper-provenance-v1"
        a.pop("latency"); b.pop("latency")
        assert canonical_json_bytes(a) == canonical_json_bytes(b)


@pytest.fixture(scope="module")
def completed(manifest):
    return collect(manifest,MeasuredOfflineClient(scripts={(0,0):[call("{}",tool="list_tickets")],(0,1):[]}))


@pytest.mark.parametrize("mutation", ["journal_order","tool_kind","arm_attribution","missing_dispatch","stale_sequence","missing_classification","mixed_metadata","unmatched_trace"])
def test_v2_measurement_tampering_rejected(tmp_path,manifest,completed,mutation):
    root = persist_and_validate(tmp_path,manifest,completed)
    attempts = [json.loads(line) for line in (root/"scheduled_attempts.jsonl").read_bytes().splitlines()]
    trace_records = [json.loads(line) for line in (root/"arm_traces.jsonl").read_bytes().splitlines()]
    arm = next(a for a in attempts[0]["arm_opportunities"] if a["hidden_world"]=="NOT_EXECUTED" and a["policy"]==LLM_REGENERATION)
    trace = next(t for t in trace_records if t["identifiers"]["arm_id"]==arm["arm_id"])
    measurement = arm["measurement_evidence"]
    if mutation=="journal_order": measurement["successful_tool_executions"][0]["execution_sequence"] = 2
    elif mutation=="tool_kind": measurement["successful_tool_executions"][0]["mutating"] = True
    elif mutation=="arm_attribution": measurement["successful_tool_executions"][0]["arm_id"] = "other-arm"
    elif mutation=="missing_dispatch": measurement["model_invocations"][0]["provider_request_dispatched"] = False
    elif mutation=="stale_sequence": measurement["model_invocations"][1]["provider_invocation_sequence"] = measurement["model_invocations"][0]["provider_invocation_sequence"]
    elif mutation=="missing_classification":
        measurement["model_invocations"][0]["boundary_error"] = {"exception_type":"ModelResponseError","message":"synthetic","structured_evidence":None}
    elif mutation=="mixed_metadata":
        metadata = json.loads((root/"run_metadata.json").read_bytes())
        metadata["schema_version"] = "paper-run-metadata-v1"
        metadata.pop("collection_evidence_revision")
        (root/"run_metadata.json").write_bytes(canonical_json_bytes(metadata))
    if mutation!="unmatched_trace": trace["measurement_evidence"] = copy.deepcopy(measurement)
    else: trace["measurement_evidence"]["successful_tool_executions"] = []
    (root/"scheduled_attempts.jsonl").write_bytes(paper._jsonl(tuple(attempts)))
    (root/"arm_traces.jsonl").write_bytes(paper._jsonl(tuple(trace_records)))
    with pytest.raises(Exception):
        paper.validate_paper_collection_bundle(root)


def test_durable_entry_default_v2_and_byte_determinism(tmp_path,manifest):
    first = paper.run_paper_collection(manifest=manifest,client=MeasuredOfflineClient(),run_root=tmp_path/"first",metadata=METADATA)
    assert first.collection_evidence_revision == EVIDENCE_V2
    # Re-publishing the same retained synthetic evidence must not regenerate
    # calls or states; all six files, including measurement records, are equal.
    paper.persist_paper_collection_run(manifest=manifest,result=first,run_root=tmp_path/"second",metadata=METADATA)
    assert {p.name:p.read_bytes() for p in (tmp_path/"first").iterdir()} == {p.name:p.read_bytes() for p in (tmp_path/"second").iterdir()}


def test_v2_missing_provider_measurement_rejected_before_any_slot(tmp_path,manifest):
    client = OfflineClient()
    with pytest.raises(paper.PaperCollectionPreflightError):
        paper.run_paper_collection(manifest=manifest,client=client,run_root=tmp_path/"rejected",metadata=METADATA)
    assert client.requests == [] and not (tmp_path/".rejected.in-progress").exists()


def test_manifest_identity_is_byte_identical(manifest):
    assert len(manifest.canonical_bytes) == 240807
    assert manifest.manifest_hash == "a707909df1fcfaa99c6834394e74340788dfcf1d62545d25ff89bf6a6418a03c"


def test_unavailable_state_still_retains_exact_cost_prefix(tmp_path,manifest,monkeypatch):
    original = paper.execute_prepared_recovery_arm
    def fail_snapshot(prepared,**kwargs):
        if prepared.plan.scheduled_attempt_ordinal==0 and kwargs["hidden_world"] is HiddenWorld.NOT_EXECUTED and kwargs["policy"]==LLM_REGENERATION:
            env = arm_environment(prepared,kwargs["hidden_world"],kwargs["policy"])
            def unavailable():
                raise RuntimeError("synthetic unavailable terminal snapshot")
            monkeypatch.setattr(env,"snapshot_bytes",unavailable)
        return original(prepared,**kwargs)
    monkeypatch.setattr(paper,"execute_prepared_recovery_arm",fail_snapshot)
    result = collect(manifest,MeasuredOfflineClient(scripts={(0,0):[call("{}",tool="list_tickets")],(0,1):[]}))
    evidence = thaw_json_value(h0_arm(result,LLM_REGENERATION).pre_trace_evidence)
    assert evidence["authoritative_final_state_snapshot"] is None
    assert evidence["authoritative_final_state_sha256"] is None
    assert evidence["state_capture_error"] is not None
    assert evidence["model_calls_issued"] == 2
    assert [e["mutating"] for e in evidence["successful_tool_executions"]] == [False]
    persist_and_validate(tmp_path,manifest,result)


def test_replay_success_then_escaped_failure_retains_one_write(tmp_path,manifest,monkeypatch):
    original = paper.execute_prepared_recovery_arm
    def fail_after_success(prepared,**kwargs):
        result = original(prepared,**kwargs)
        if prepared.plan.scheduled_attempt_ordinal==0 and kwargs["hidden_world"] is HiddenWorld.NOT_EXECUTED and kwargs["policy"]==EXACT_REPLAY:
            raise RuntimeError("synthetic error after Replay succeeds")
        return result
    monkeypatch.setattr(paper,"execute_prepared_recovery_arm",fail_after_success)
    result = collect(manifest,MeasuredOfflineClient())
    evidence = thaw_json_value(h0_arm(result,EXACT_REPLAY).pre_trace_evidence)
    assert evidence["model_calls_issued"] == 0
    assert [e["mutating"] for e in evidence["successful_tool_executions"]] == [True]
    persist_and_validate(tmp_path,manifest,result)


def test_commit_then_execution_failure_does_not_fabricate_success(make_request,monkeypatch):
    env = TicketEnvironment.empty()
    original = env._commit_create
    def fail_after_commit(*args):
        original(*args)
        raise RuntimeError("synthetic commit then execution failure")
    monkeypatch.setattr(env,"_commit_create",fail_after_commit)
    with pytest.raises(RuntimeError):
        env.execute_request(make_request().serialized_request,source_stage=SourceStage.RECOVERY,arm_id="arm")
    assert env.dispatch_count == 1
    assert len(env.state.mutation_events) == 1
    assert env.successful_execution_journal == ()


def test_model_client_return_type_incoherence_is_explicit(tmp_path,manifest):
    class InvalidReturnClient(MeasuredOfflineClient):
        def complete(self,request):
            if len(request.messages)==2:
                return super().complete(request)
            self._measurement = ProviderRequestDispatchEvidence(self._measurement.invocation_sequence+1,True,True)
            return object()
    result = collect(manifest,InvalidReturnClient())
    failure = thaw_json_value(h0_arm(result,LLM_REGENERATION).measurement_evidence)["model_invocations"][0]["response_failure"]
    assert failure["category"] == "IMPLEMENTATION_INCOHERENCE"
    assert failure["stage"] == "MODEL_CLIENT_RETURN_TYPE"
    persist_and_validate(tmp_path,manifest,result)


def test_v2_stale_provider_measurement_is_runner_fatal(manifest):
    class StaleClient(MeasuredOfflineClient):
        def complete(self,request):
            if len(request.messages)==2:
                return super().complete(request)
            return OfflineClient.complete(self,request)
    with pytest.raises(paper.PaperCollectionFatalError):
        collect(manifest,StaleClient())


@pytest.mark.parametrize("filename,expected", [
    ("paper_collection_event_schema_v1.json","b1d8f860dfa6c1c762c3fa64a555ccfa61879179052673c9818652a11c13b9e5"),
    ("paper_collection_summary_schema_v1.json","f52d4e299bc9dd6152ac91f6197b6a59f07ae19371689f030871b0ea0f261615"),
    ("paper_run_metadata_schema_v1.json","4f8d3fafe3b796244613af13bb1b1220231bd3b73732bf0eac85351297c66818"),
    ("paper_scheduled_attempt_schema_v1.json","85ddfad8e1c06cecb82e2606af100af8b7a88aebc98c2d7b7efd6a6e0b98b5e6"),
    ("paper_trace_schema_v1.json","00a38c9e1d16f460cdf29a85ff76a8f2243dbf5a9564ef5cd01d437ca6158627"),
    ("trace_schema_v1.json","8cd7d3389ade1146120b9f3349ae6f03d8bf8281f113b34d1f0a44f5c0ea8bdb"),
])
def test_committed_v1_schemas_are_byte_immutable(filename,expected):
    root = Path(__file__).resolve().parents[1]/"research/protocol"
    assert sha256_hex((root/filename).read_bytes()) == expected
