"""Prospective analysis using only synthetic objects and offline V2 bundles."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from retry_semantics.experiment import build_fireworks_deepseek_paper_manifest
from retry_semantics.experiment import paper
from retry_semantics.experiment.analysis_evidence import (
    SOURCE_FILES, derive_arm, derive_families, extract_ticket_analysis, behavioral_rates,
    operational_rates, _analysis_validators,
)
from retry_semantics.models import ModelTimeoutError, ModelRequestError, ModelRejectedGenerationError, freeze_json_value
from retry_semantics.runtime.exact_replay import EXACT_REPLAY, ReplayProtocolError
from retry_semantics.runtime.regeneration import LLM_REGENERATION
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from test_paper_measurement_v2 import MeasuredOfflineClient, collect, adapter_failure
from test_paper_collection import METADATA, call
from test_fireworks_adapter import _completion


@pytest.fixture(scope="module")
def manifest():
    return build_fireworks_deepseek_paper_manifest()


def bundle(tmp_path,manifest,client, name="raw"):
    result = collect(manifest,client)
    root = tmp_path/name
    paper.persist_paper_collection_run(run_root=root,manifest=manifest,result=result,metadata=METADATA)
    return root


def rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def arm_for(root,slot=0,policy=LLM_REGENERATION,world="H0"):
    return next(a for a in rows(root/'analysis_arms.jsonl') if a['slot_index']==slot and a['policy']==policy and a['world']==world)


@pytest.fixture(scope="module")
def completed(tmp_path_factory,manifest):
    root=tmp_path_factory.mktemp('analysis-v2')
    arguments = manifest.entries[1].scenario.task_spec.expected_arguments.as_dict()
    scripts = {(0,0):[call('{}',tool='list_tickets')],(0,1):[],
               (1,0):[],(1,1):[call('{}',tool='list_tickets'),call(json.dumps(arguments))],(1,2):[],
               (2,0):[call('{"customer_id":')],
               (3,0):[],(3,1):adapter_failure(_completion(tool_calls=[{'id':'bad','type':'function','function':{'name':'create_ticket','arguments':42}}])),
               (4,0):[call('{}',tool='list_tickets')],(4,1):ModelTimeoutError('synthetic timeout'),
               (5,0):[],(5,1):[call('{}',tool='list_tickets',call_id=f'r-{i}') for i in range(4)],
               (6,0):ModelRejectedGenerationError('fireworks','tool_use_failed',freeze_json_value({'unparsed':'offline'}),'rejected'),
               (7,0):[],(7,1):adapter_failure(_completion(reasoning_content='synthetic secret reasoning'))}
    return bundle(root,manifest,MeasuredOfflineClient(eligible=set(range(8)),scripts=scripts,
                  original_errors={8:ModelTimeoutError('offline original timeout')}))


def test_complete_artifacts_schema_pairing_and_denominators(completed,tmp_path):
    out=tmp_path/'analysis'
    result=extract_ticket_analysis(completed,out)
    assert {p.name for p in out.iterdir()} == {'analysis_provenance.json','analysis_arms.jsonl','analysis_families.jsonl','analysis_results.json'}
    arms=rows(out/'analysis_arms.jsonl'); families=rows(out/'analysis_families.jsonl')
    assert len(arms)==32 and len(families)==8
    assert [(a['slot_index'],a['world'],a['policy']) for a in arms] == sorted((a['slot_index'],a['world'],a['policy']) for a in arms)
    validators=_analysis_validators()
    for a in arms: validators['analysis_arm_schema_v1.json'].validate(a)
    for f in families: validators['analysis_family_schema_v1.json'].validate(f)
    validators['analysis_results_schema_v1.json'].validate(result)
    provenance=json.loads((out/'analysis_provenance.json').read_bytes())
    validators['analysis_provenance_schema_v1.json'].validate(provenance)
    assert provenance['source_run_git_commit']==METADATA.git_commit
    assert provenance['source_run_timestamp']==METADATA.timestamp
    assert provenance['bootstrap_seed']==20260916 and provenance['bootstrap_replicates']==10000
    assert provenance['source_bundle_file_sha256']=={n:sha256_hex((completed/n).read_bytes()) for n in SOURCE_FILES}
    assert provenance['derived_artifact_sha256']=={n:sha256_hex((out/n).read_bytes()) for n in ('analysis_arms.jsonl','analysis_families.jsonl','analysis_results.json')}
    assert result['operational_rates']['eligibility']=={'numerator':8,'denominator':160,'rate':.05}
    assert result['operational_rates']['original_generation_infrastructure_failure']['numerator']==1
    assert result['operational_rates']['recovery_infrastructure_failure']['NOT_EXECUTED'][LLM_REGENERATION]=={'numerator':2,'denominator':8,'rate':.25}
    # Adapter model malformation is retained in the raw failure, excluded from true infra.
    malformed=arm_for(out,3)
    assert malformed['raw_infrastructure_failure'] is not None and malformed['infrastructure_failure'] is None
    assert malformed['MALFORMED_GENERATION']==1 and malformed['BEHAVIORALLY_EVALUABLE_ARM']==1
    assert malformed['STATE_CORRECT']==0 and malformed['PROTOCOL_VALID_RECOVERY']==0
    assert malformed['model_calls_issued']==1 and malformed['recovery_tool_calls_executed']==0
    assert families[3]['H0']['primary']==[1,0]
    assert families[4]['H0']['primary'] is None and families[4]['H0']['sensitivity']==[1,0]
    assert result['primary']['worlds']['H0']['N']==6
    assert result['primary']['worlds']['H0']['replay_correctness']['denominator']==6
    assert result['primary']['worlds']['H0']['regeneration_correctness']['denominator']==6
    assert result['primary']['interaction']['N']==6
    assert result['behavioral_rates']['H0'][LLM_REGENERATION]['failure_modes']['MALFORMED_GENERATION']=={'numerator':2,'denominator':6,'rate':2/6}
    assert result['behavioral_rates']['H0'][LLM_REGENERATION]['protocol_valid_recovery']['denominator']==8
    for p in out.glob('*.json'):assert not p.read_bytes().endswith(b'\n')
    for p in out.glob('*.jsonl'):assert p.read_bytes().endswith(b'\n')


@pytest.mark.parametrize('slot,costs,observation,malformed,rejected,budget,evaluable,valid',[
    (0,[2,1,0,1],1,0,0,0,1,1),
    (1,[2,1,1,2],1,0,0,0,1,1),
    (2,[1,0,0,0],0,1,0,0,1,0),
    (3,[1,0,0,0],0,1,0,0,1,0),
    (4,[2,1,0,1],1,0,0,0,0,0),
    (5,[1,3,0,3],1,0,0,1,1,0),
    (6,[1,0,0,0],0,0,1,0,1,0),
    (7,[1,0,0,0],0,0,0,0,0,0),
])
def test_v2_behavior_and_exact_cost(completed,tmp_path,slot,costs,observation,malformed,rejected,budget,evaluable,valid):
    out=tmp_path/'analysis';extract_ticket_analysis(completed,out);a=arm_for(out,slot)
    assert [a[k] for k in ('model_calls_issued','read_only_tool_calls_executed','state_mutating_tool_calls_executed','recovery_tool_calls_executed')]==costs
    assert [a[k] for k in ('OBSERVATION_BEFORE_WRITE','MALFORMED_GENERATION','REJECTED_GENERATION','BUDGET_EXHAUSTED','BEHAVIORALLY_EVALUABLE_ARM','PROTOCOL_VALID_RECOVERY')]==[observation,malformed,rejected,budget,evaluable,valid]
    replay=arm_for(out,slot,EXACT_REPLAY)
    assert [replay[k] for k in ('model_calls_issued','read_only_tool_calls_executed','state_mutating_tool_calls_executed','recovery_tool_calls_executed')]==[0,0,1,1]
    assert all(replay[k] is None for k in ('OBSERVATION_BEFORE_WRITE','MALFORMED_GENERATION','REJECTED_GENERATION','BUDGET_EXHAUSTED'))


def test_repeated_process_byte_hash_identity_and_raw_immutability(completed,tmp_path):
    before={n:sha256_hex((completed/n).read_bytes()) for n in SOURCE_FILES}
    outputs=[tmp_path/'process-a',tmp_path/'process-b']
    # No inherited credential environment, no networking code involved.
    for output in outputs:
        subprocess.run([sys.executable,'-m','retry_semantics.experiment.analysis_evidence',str(completed),str(output)],check=True,env={'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')},capture_output=True)
    hashes=[]
    for output in outputs:
        hashes.append({p.name:sha256_hex(p.read_bytes()) for p in output.iterdir()})
    assert hashes[0]==hashes[1]
    assert before=={n:sha256_hex((completed/n).read_bytes()) for n in SOURCE_FILES}
    for p in outputs[0].iterdir():assert p.read_bytes()==(outputs[1]/p.name).read_bytes()
    # A test-run artifact records reproducible full-export hashes for the audit.
    (tmp_path/'deterministic_hashes.json').write_bytes(canonical_json_bytes(hashes[0]))


@pytest.mark.parametrize('category,raw',[
    ('PROVIDER_RESPONSE_STRUCTURE',{'choices':'unreadable'}),
    ('PROTOCOL_COMPATIBILITY',_completion(reasoning_content='never retained')),
])
def test_nonmalformed_response_failure(manifest,tmp_path,category,raw):
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(scripts={(0,0):adapter_failure(raw)}))
    out=tmp_path/'analysis';extract_ticket_analysis(rawroot,out);a=arm_for(out)
    assert a['measurement_evidence']['model_invocations'][0]['response_failure']['category']==category
    assert a['MALFORMED_GENERATION']==0 and a['BEHAVIORALLY_EVALUABLE_ARM']==0
    assert a['STATE_CORRECT']==0 and a['STATE_CORRECT_SENSITIVITY']==0


def test_implementation_incoherence_not_malformed(manifest,tmp_path):
    broken=call('{"customer_id":');object.__setattr__(broken,'parse_success',True)
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(scripts={(0,0):[broken]}))
    out=tmp_path/'analysis';extract_ticket_analysis(rawroot,out);a=arm_for(out)
    assert a['measurement_evidence']['model_invocations'][0]['response_failure']['category']=='IMPLEMENTATION_INCOHERENCE'
    assert a['MALFORMED_GENERATION']==0 and a['BEHAVIORALLY_EVALUABLE_ARM']==0


@pytest.mark.parametrize('local',[False,True])
def test_pretrace_dispatch_zero_vs_transport_failure(manifest,tmp_path,local):
    error=ModelRequestError('local') if local else ModelTimeoutError('transport')
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(scripts={(0,0):error}))
    out=tmp_path/'analysis';extract_ticket_analysis(rawroot,out);a=arm_for(out)
    assert a['model_calls_issued']==int(not local) and a['recovery_tool_calls_executed']==0
    assert a['MALFORMED_GENERATION']==0 and a['PROTOCOL_VALID_RECOVERY']==0


@pytest.mark.parametrize('replay_success',[False,True])
def test_replay_executor_failure_prefix(manifest,tmp_path,monkeypatch,replay_success):
    real=paper.execute_prepared_recovery_arm
    def injected(prepared,**kwargs):
        if kwargs['policy']==EXACT_REPLAY and prepared.plan.scheduled_attempt_ordinal==0 and kwargs['hidden_world'] is HiddenWorld.NOT_EXECUTED:
            if replay_success:real(prepared,**kwargs)
            raise ReplayProtocolError('synthetic executor failure')
        return real(prepared,**kwargs)
    monkeypatch.setattr(paper,'execute_prepared_recovery_arm',injected)
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient())
    out=tmp_path/'analysis';extract_ticket_analysis(rawroot,out);a=arm_for(out,policy=EXACT_REPLAY)
    assert a['model_calls_issued']==0 and a['state_mutating_tool_calls_executed']==int(replay_success)
    assert a['BEHAVIORALLY_EVALUABLE_ARM']==0 and a['PROTOCOL_VALID_RECOVERY']==0
    assert a['STATE_CORRECT']==int(replay_success) and a['STATE_CORRECT_SENSITIVITY']==0


def test_unavailable_terminal_state_preserves_read_prefix(manifest,tmp_path,monkeypatch):
    from retry_semantics.experiment.paper_measurement import arm_environment
    real=paper.execute_prepared_recovery_arm
    def injected(prepared,**kwargs):
        if kwargs['policy']==LLM_REGENERATION and prepared.plan.scheduled_attempt_ordinal==0 and kwargs['hidden_world'] is HiddenWorld.NOT_EXECUTED:
            real(prepared,**kwargs)
            environment=arm_environment(prepared,kwargs['hidden_world'],kwargs['policy'])
            def unavailable():raise RuntimeError('synthetic unavailable snapshot')
            environment.snapshot_bytes=unavailable
            raise RuntimeError('synthetic escaped failure')
        return real(prepared,**kwargs)
    monkeypatch.setattr(paper,'execute_prepared_recovery_arm',injected)
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(scripts={(0,0):[call('{}',tool='list_tickets')],(0,1):[]}))
    out=tmp_path/'analysis';extract_ticket_analysis(rawroot,out);a=arm_for(out)
    assert a['model_calls_issued']==2 and a['read_only_tool_calls_executed']==1 and a['state_mutating_tool_calls_executed']==0
    assert a['OBSERVATION_BEFORE_WRITE']==1 and a['BEHAVIORALLY_EVALUABLE_ARM']==0
    assert all(a[k] is None for k in ('STATE_CORRECT','MISSING_MUTATION','DUPLICATE_MUTATION','WRONG_MUTATION'))


def test_prearm_nonattributable_family_failure(manifest,tmp_path,monkeypatch):
    real=paper.prepare_eligible_scheduled_trial
    def injected(**kwargs):
        if kwargs['plan'].scheduled_attempt_ordinal==0:raise RuntimeError('synthetic family construction')
        return real(**kwargs)
    monkeypatch.setattr(paper,'prepare_eligible_scheduled_trial',injected)
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient())
    out=tmp_path/'analysis';result=extract_ticket_analysis(rawroot,out)
    family=rows(out/'analysis_families.jsonl')[0]
    assert all(family[w]['primary'] is None and family[w]['sensitivity'] is None for w in ('H0','H1'))
    for a in rows(out/'analysis_arms.jsonl'):
        assert a['BEHAVIORALLY_EVALUABLE_ARM']==0 and a['PROTOCOL_VALID_RECOVERY'] is None
        assert a['STATE_CORRECT_SENSITIVITY'] is None and a['model_calls_issued'] is None
    assert result['operational_rates']['pre_arm_system_family_failures']==1
    assert result['behavioral_rates']['H0'][EXACT_REPLAY]['protocol_valid_recovery']['denominator']==0
    assert result['operational_rates']['recovery_infrastructure_failure']['NOT_EXECUTED'][EXACT_REPLAY]=={'numerator':0,'denominator':1,'rate':0.0}


def test_no_eligible_families_not_estimable(manifest,tmp_path):
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(eligible=set()))
    out=tmp_path/'analysis';result=extract_ticket_analysis(rawroot,out)
    assert (out/'analysis_arms.jsonl').read_bytes()==b'' and (out/'analysis_families.jsonl').read_bytes()==b''
    assert all(result['primary']['worlds'][w]['N']==0 for w in ('H0','H1'))
    assert result['primary']['holm']['family_fully_estimable'] is False
    assert all(result['primary']['holm']['tests'][w]['reject'] is None for w in ('H0','H1'))
    assert result['primary']['interaction']['estimate'] is None and result['materially_weakened'] is None


@pytest.mark.parametrize('mutation',['missing','progress','revision','evidence_revision','dispatch','journal','classification','trace_provenance','provider','model','manifest_id','hash'])
def test_invalid_input_never_creates_analysis(completed,tmp_path,mutation):
    import shutil
    rawroot=tmp_path/('raw.in-progress' if mutation=='progress' else 'raw')
    shutil.copytree(completed,rawroot)
    if mutation=='missing':(rawroot/'collection_events.jsonl').unlink()
    elif mutation in ('revision','evidence_revision','hash'):
        p=rawroot/'run_metadata.json';v=json.loads(p.read_bytes());v[{'revision':'execution_semantics_revision','evidence_revision':'collection_evidence_revision','hash':'manifest_sha256'}[mutation]]='wrong';p.write_bytes(canonical_json_bytes(v))
    elif mutation in ('dispatch','journal','classification'):
        p=rawroot/'scheduled_attempts.jsonl';v=rows(p);a=next(a for a in v[0]['arm_opportunities'] if a['policy']==LLM_REGENERATION)
        if mutation=='dispatch':a['measurement_evidence']['model_invocations'][0]['provider_request_dispatched']=False
        elif mutation=='journal':a['measurement_evidence']['successful_tool_executions'][0]['mutating']=True
        else:next(a for a in v[3]['arm_opportunities'] if a['policy']==LLM_REGENERATION and a['hidden_world']=='NOT_EXECUTED')['measurement_evidence']['model_invocations'][0]['response_failure']['category']='PROTOCOL_COMPATIBILITY'
        p.write_bytes(b''.join(canonical_json_bytes(r)+b'\n' for r in v))
    elif mutation=='trace_provenance':
        p=rawroot/'arm_traces.jsonl';v=rows(p);v[0]['git_commit']='f'*40;p.write_bytes(b''.join(canonical_json_bytes(r)+b'\n' for r in v))
    elif mutation in ('provider','model','manifest_id'):
        p=rawroot/'manifest.json';v=json.loads(p.read_bytes())
        if mutation=='manifest_id':v['manifest_id']='wrong'
        else:v['entries'][0]['model_config']['model']['provider' if mutation=='provider' else 'name']='wrong'
        p.write_bytes(canonical_json_bytes(v))
    out=tmp_path/'nested'/'analysis'
    with pytest.raises((ValueError,paper.PaperCollectionError)):
        extract_ticket_analysis(rawroot,out)
    assert not out.exists() and not out.parent.exists()


def test_v1_rejected_and_existing_output_never_overwritten(completed,tmp_path,manifest):
    out=tmp_path/'analysis';extract_ticket_analysis(completed,out)
    before={p.name:p.read_bytes() for p in out.iterdir()}
    with pytest.raises(FileExistsError):extract_ticket_analysis(completed,out)
    assert before=={p.name:p.read_bytes() for p in out.iterdir()}
    v1=tmp_path/'v1';result=paper.execute_paper_collection(manifest,MeasuredOfflineClient(),evidence_revision='paper-collection-evidence-v1')
    paper.persist_paper_collection_run(run_root=v1,manifest=manifest,result=result,metadata=METADATA)
    with pytest.raises(paper.PaperCollectionError,match='requires paper-collection-evidence-v2'):
        extract_ticket_analysis(v1,tmp_path/'v1-analysis')
    assert not (tmp_path/'v1-analysis').exists()


def test_create_first_observation_zero(manifest,tmp_path):
    args=manifest.entries[0].scenario.task_spec.expected_arguments.as_dict()
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(scripts={(0,0):[call(json.dumps(args)),call('{}',tool='list_tickets')],(0,1):[]}))
    out=tmp_path/'analysis';extract_ticket_analysis(rawroot,out);a=arm_for(out)
    assert a['OBSERVATION_BEFORE_WRITE']==0 and a['recovery_tool_calls_executed']==2
    assert a['STATE_CORRECT']==1 and a['PROTOCOL_VALID_RECOVERY']==1


def test_no_exception_or_provider_text_classification(completed):
    attempts=rows(completed/'scheduled_attempts.jsonl');traces={t['identifiers']['arm_id']:t for t in rows(completed/'arm_traces.jsonl')}
    opportunity=next(a for a in attempts[3]['arm_opportunities'] if a['policy']==LLM_REGENERATION and a['hidden_world']=='NOT_EXECUTED')
    scenario=json.loads((completed/'manifest.json').read_bytes())['entries'][3]['scenario']
    baseline=derive_arm(attempts[3],opportunity,traces[opportunity['arm_id']],scenario)
    opportunity=copy.deepcopy(opportunity);opportunity['infrastructure_failure']['diagnostic']['message']='timeout reasoning rejected budget'
    opportunity['infrastructure_failure']['diagnostic']['structured_evidence']={'text':'anything'}
    changed=derive_arm(attempts[3],opportunity,traces[opportunity['arm_id']],scenario)
    for k in ('MALFORMED_GENERATION','REJECTED_GENERATION','BUDGET_EXHAUSTED','BEHAVIORALLY_EVALUABLE_ARM','PROTOCOL_VALID_RECOVERY','STATE_CORRECT','model_calls_issued'):
        assert changed[k]==baseline[k]


def test_sensitivity_sign_reversal_integrated(manifest,tmp_path,monkeypatch):
    real=paper.execute_prepared_recovery_arm
    def injected(prepared,**kwargs):
        if kwargs['policy']==EXACT_REPLAY and prepared.plan.scheduled_attempt_ordinal in (1,2) and kwargs['hidden_world'] is HiddenWorld.NOT_EXECUTED:
            raise RuntimeError('offline attributable Replay failure')
        return real(prepared,**kwargs)
    monkeypatch.setattr(paper,'execute_prepared_recovery_arm',injected)
    scripts={}
    for slot,ordinal in [(1,1),(2,0)]:
        args=manifest.entries[slot].scenario.task_spec.expected_arguments.as_dict()
        scripts[slot,ordinal]=[call(json.dumps(args))]
        scripts[slot,ordinal+1]=[]
    scripts[1,0]=[]
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(eligible={0,1,2},scripts=scripts))
    result=extract_ticket_analysis(rawroot,tmp_path/'analysis')
    assert result['primary']['worlds']['H0']['delta']==1
    assert result['sensitivity']['worlds']['H0']['delta']==-1/3
    assert result['operational_fragility']['value'] is True
    assert result['operational_fragility']['sign_reversals']==['H0']


def test_sensitivity_holm_decision_changes_integrated(manifest,tmp_path):
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(eligible=set(range(7)),scripts={(6,0):ModelTimeoutError('offline'),(6,1):ModelTimeoutError('offline')}))
    result=extract_ticket_analysis(rawroot,tmp_path/'analysis')
    assert all(result['primary']['holm']['tests'][w]['reject'] is False for w in ('H0','H1'))
    assert all(result['sensitivity']['holm']['tests'][w]['reject'] is True for w in ('H0','H1'))
    assert result['operational_fragility']['holm_decision_changes']==['H0','H1']
    assert result['operational_fragility']['sign_reversals']==[]
    assert result['operational_fragility']['value'] is True


def test_both_attributable_failures_sensitivity_zero(manifest,tmp_path,monkeypatch):
    real=paper.execute_prepared_recovery_arm
    def injected(prepared,**kwargs):
        if prepared.plan.scheduled_attempt_ordinal==0 and kwargs['hidden_world'] is HiddenWorld.NOT_EXECUTED:
            if kwargs['policy']==LLM_REGENERATION:real(prepared,**kwargs)
            raise RuntimeError('offline attributable arm failure')
        return real(prepared,**kwargs)
    monkeypatch.setattr(paper,'execute_prepared_recovery_arm',injected)
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient())
    out=tmp_path/'analysis';result=extract_ticket_analysis(rawroot,out)
    f=rows(out/'analysis_families.jsonl')[0]
    assert f['H0']['primary'] is None and f['H0']['sensitivity']==[0,0]
    assert result['sensitivity']['worlds']['H0']['n00']==1
    assert result['primary']['holm']['family_fully_estimable'] is False
    assert all(result['primary']['holm']['tests'][w]['reject'] is None for w in ('H0','H1'))


def test_pretrace_model_generation_failure_still_evaluable(manifest,tmp_path,monkeypatch):
    real=paper.execute_prepared_recovery_arm
    def injected(prepared,**kwargs):
        if prepared.plan.scheduled_attempt_ordinal==0 and kwargs['policy']==LLM_REGENERATION and kwargs['hidden_world'] is HiddenWorld.NOT_EXECUTED:
            result=real(prepared,**kwargs)
            raise result.model_invocations[-1].infrastructure_error
        return real(prepared,**kwargs)
    monkeypatch.setattr(paper,'execute_prepared_recovery_arm',injected)
    error=adapter_failure(_completion(tool_calls=[{'id':'bad','type':'function','function':{'name':'create_ticket','arguments':42}}]))
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(scripts={(0,0):error}))
    out=tmp_path/'analysis';extract_ticket_analysis(rawroot,out);a=arm_for(out)
    assert a['termination_reason'] is None and a['source_trace_id'] is None
    assert a['MALFORMED_GENERATION']==1 and a['BEHAVIORALLY_EVALUABLE_ARM']==1
    assert a['STATE_CORRECT']==0 and a['PROTOCOL_VALID_RECOVERY']==0
    assert a['model_calls_issued']==1 and a['recovery_tool_calls_executed']==0


def test_read_then_pretrace_failure_keeps_terminal_state_and_prefix(manifest,tmp_path,monkeypatch):
    real=paper.execute_prepared_recovery_arm
    def injected(prepared,**kwargs):
        result=real(prepared,**kwargs)
        if prepared.plan.scheduled_attempt_ordinal==0 and kwargs['policy']==LLM_REGENERATION and kwargs['hidden_world'] is HiddenWorld.NOT_EXECUTED:
            raise RuntimeError('offline escaped post-read failure')
        return result
    monkeypatch.setattr(paper,'execute_prepared_recovery_arm',injected)
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(scripts={(0,0):[call('{}',tool='list_tickets')],(0,1):[]}))
    out=tmp_path/'analysis';extract_ticket_analysis(rawroot,out);a=arm_for(out)
    assert a['source_trace_id'] is None and a['STATE_CORRECT']==0
    assert a['model_calls_issued']==2 and a['read_only_tool_calls_executed']==1 and a['state_mutating_tool_calls_executed']==0
    assert a['OBSERVATION_BEFORE_WRITE']==1 and a['BEHAVIORALLY_EVALUABLE_ARM']==0


def test_failed_output_schema_validation_creates_nothing(completed,tmp_path,monkeypatch):
    import jsonschema
    import retry_semantics.experiment.analysis_evidence as evidence
    real=evidence._analysis_validators
    def validators():
        values=real()
        values['analysis_results_schema_v1.json']=jsonschema.Draft202012Validator({'const':'synthetic impossible result'})
        return values
    monkeypatch.setattr(evidence,'_analysis_validators',validators)
    with pytest.raises(jsonschema.ValidationError):extract_ticket_analysis(completed,tmp_path/'nested'/'analysis')
    assert not (tmp_path/'nested').exists()


def test_budget_precedence_does_not_reclassify_unprocessed_malformed_call(manifest,tmp_path):
    calls=[call('{}',tool='list_tickets',call_id=f'r-{i}') for i in range(3)]+[call('{"customer_id":')]
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(scripts={(0,0):calls}))
    out=tmp_path/'analysis';extract_ticket_analysis(rawroot,out);a=arm_for(out)
    assert a['BUDGET_EXHAUSTED']==1 and a['MALFORMED_GENERATION']==0
    assert a['BEHAVIORALLY_EVALUABLE_ARM']==1 and a['read_only_tool_calls_executed']==3


def test_inprogress_alias_rejected(completed,tmp_path):
    alias=tmp_path/'run.in-progress';alias.symlink_to(completed,target_is_directory=True)
    with pytest.raises(paper.PaperCollectionError,match='in-progress'):
        extract_ticket_analysis(alias,tmp_path/'analysis')
    assert not (tmp_path/'analysis').exists()


def test_bundle_changed_between_validation_and_capture_is_rejected(completed,tmp_path,monkeypatch):
    import shutil
    import retry_semantics.experiment.analysis_evidence as evidence
    rawroot=tmp_path/'raw';shutil.copytree(completed,rawroot)
    real=evidence.validate_paper_collection_bundle
    validations=0
    def changed(root):
        nonlocal validations
        real(root)
        validations+=1
        if validations==1:
            p=root/'run_metadata.json';v=json.loads(p.read_bytes());v['git_commit']='f'*40
            p.write_bytes(canonical_json_bytes(v))
    monkeypatch.setattr(evidence,'validate_paper_collection_bundle',changed)
    with pytest.raises(paper.PaperCollectionError):extract_ticket_analysis(rawroot,tmp_path/'analysis')
    assert not (tmp_path/'analysis').exists()


def test_source_changed_after_derivation_never_published(completed,tmp_path,monkeypatch):
    import shutil
    import retry_semantics.experiment.analysis_evidence as evidence
    rawroot=tmp_path/'raw';shutil.copytree(completed,rawroot)
    real=evidence._analysis_validators
    def changed():
        validators=real()
        p=rawroot/'run_metadata.json';v=json.loads(p.read_bytes());v['git_commit']='f'*40
        p.write_bytes(canonical_json_bytes(v))
        return validators
    monkeypatch.setattr(evidence,'_analysis_validators',changed)
    with pytest.raises(paper.PaperCollectionError,match='changed during analysis'):
        extract_ticket_analysis(rawroot,tmp_path/'analysis')
    assert not (tmp_path/'analysis').exists()


@pytest.mark.parametrize('kind,analysis_infrastructure',[
    ('MODEL_GENERATION_STRUCTURE',False),
    ('PROVIDER_RESPONSE_STRUCTURE',True),
    ('PROTOCOL_COMPATIBILITY',True),
    ('IMPLEMENTATION_INCOHERENCE',True),
    ('TIMEOUT',True),
    ('TRANSPORT',True),
    ('AUTHENTICATION',True),
    ('RATE_LIMIT',True),
    ('HTTP_500',True),
    ('PROVIDER_STATUS',True),
])
def test_original_generation_raw_vs_analysis_classification(manifest,tmp_path,kind,analysis_infrastructure):
    from retry_semantics.experiment.analysis_evidence import analysis_original_generation_infrastructure
    from retry_semantics.models import (
        ModelAuthenticationError, ModelRateLimitError, ModelTransportError,
        ModelProviderStatusError, ModelResponseError, capture_fireworks_chat_completion,
    )
    if kind=='MODEL_GENERATION_STRUCTURE':
        error=adapter_failure(_completion(tool_calls=[{
            'id':'original-malformed','type':'function',
            'function':{'name':'create_ticket','arguments':42},
        }]))
        assert error.response_failure.category=='MODEL_GENERATION_STRUCTURE'
        assert error.response_failure.stage=='TOOL_CALL_ARGUMENTS'
    elif kind=='PROVIDER_RESPONSE_STRUCTURE':
        error=adapter_failure({'choices':'invalid envelope'})
    elif kind=='PROTOCOL_COMPATIBILITY':
        error=adapter_failure(_completion(reasoning_content='offline reasoning never retained'))
    elif kind=='IMPLEMENTATION_INCOHERENCE':
        with pytest.raises(ModelResponseError) as caught:
            capture_fireworks_chat_completion(_completion(),requested_model='')
        error=caught.value
    else:
        error={
            'TIMEOUT':ModelTimeoutError('offline'),
            'TRANSPORT':ModelTransportError('offline'),
            'AUTHENTICATION':ModelAuthenticationError('offline'),
            'RATE_LIMIT':ModelRateLimitError('offline'),
            'HTTP_500':ModelProviderStatusError('offline',status_code=500),
            'PROVIDER_STATUS':ModelProviderStatusError('offline',status_code=400),
        }[kind]
    # Identical diagnostic text across distinct structured failure categories.
    error.args=('offline diagnostic text does not determine classification',)
    rawroot=bundle(tmp_path,manifest,MeasuredOfflineClient(
        eligible={1},original_errors={0:error,2:ModelTimeoutError('true original timeout')},
    ))
    before={name:(rawroot/name).read_bytes() for name in SOURCE_FILES}
    attempts=rows(rawroot/'scheduled_attempts.jsonl');original=attempts[0]
    assert original['eligibility']['outcome']=='INFRASTRUCTURE_FAILURE'
    assert original['original_generation_infrastructure'] is not None
    assert original['terminal_status']=='ORIGINAL_GENERATION_INFRASTRUCTURE_FAILURE'
    if hasattr(error,'response_failure'):
        classification=original['original_generation_infrastructure']['diagnostic']['response_failure']
        assert classification['category']==kind
        if kind=='MODEL_GENERATION_STRUCTURE':assert classification['stage']=='TOOL_CALL_ARGUMENTS'
    assert analysis_original_generation_infrastructure(original) is analysis_infrastructure
    assert analysis_original_generation_infrastructure(attempts[2]) is True
    assert analysis_original_generation_infrastructure(attempts[1]) is False
    raw_summary=json.loads(before['paper_collection_summary.json'])
    assert raw_summary['original_generation_infrastructure_failures']==2
    out=tmp_path/'analysis';result=extract_ticket_analysis(rawroot,out)
    assert result['operational_rates']['eligibility']=={'numerator':1,'denominator':160,'rate':1/160}
    expected=1+int(analysis_infrastructure)
    assert result['operational_rates']['original_generation_infrastructure_failure']=={
        'numerator':expected,'denominator':160,'rate':expected/160,
    }
    assert [f['slot_index'] for f in rows(out/'analysis_families.jsonl')]==[1]
    assert {a['slot_index'] for a in rows(out/'analysis_arms.jsonl')}=={1}
    assert before=={name:(rawroot/name).read_bytes() for name in SOURCE_FILES}
    assert b'offline reasoning never retained' not in b''.join(before.values())
