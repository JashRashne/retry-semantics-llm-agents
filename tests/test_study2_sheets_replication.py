"""Behavioral integration tests: real collector/model parser against a stateful API double."""
import copy
import json
import socket
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_replication as replication
from retry_semantics.study2.provider_paper_collection import collect_sheets_arm
from retry_semantics.study2.provider_paper_io import DurablePaperEvidence, PaperTransportResult
from retry_semantics.study2.provider_paper_model import PaperModelSession
from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest
from scripts.run_study2_sheets_replication import verify_run


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*a, **kw):
        raise AssertionError('unexpected network in offline test')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)


class API:
    def __init__(self):
        self.sheets = {}
        self.requests = []
        self.elapsed = 100.0
        self.fail_post = None
        self.read_error = False

    def sleep(self, seconds):
        self.elapsed += seconds

    def response(self, body, status=200, error=None):
        return PaperTransportResult(status, (), canonical_json_bytes(body), error,
                                    True, True, True, self.elapsed, self.elapsed)

    def send(self, request, **kw):
        self.requests.append(request)
        url = urlsplit(request.url)
        if request.method == 'POST' and url.path == '/v4/spreadsheets':
            doc = json.loads(request.body)
            sid = f'new-{len(self.sheets) + 1}'
            self.sheets[sid] = copy.deepcopy(doc)
            return self.response({'spreadsheetId': sid, **doc})
        sid = url.path.split('/')[-1].replace(':batchUpdate', '')
        doc = self.sheets[sid]
        if request.method == 'POST':
            if self.fail_post:
                return self.response({}, self.fail_post)
            append = json.loads(request.body)['requests'][0]['appendCells']
            sheet = next(s for s in doc['sheets'] if s['properties']['sheetId'] == append['sheetId'])
            sheet.setdefault('data', [{'rowData': []}])[0]['rowData'].extend(append['rows'])
            return self.response({'spreadsheetId': sid, 'replies': [{}], 'commentUpdateState': 'NO_UPDATES_REQUESTED'})
        if 'ranges' not in parse_qs(url.query):
            return self.response({'spreadsheetId': sid, 'properties': doc['properties'],
                                  'sheets': [{'properties': s['properties']} for s in doc['sheets']]})
        title = parse_qs(url.query)['ranges'][0].split('!')[0].strip("'")
        sheet = next(s for s in doc['sheets'] if s['properties']['title'] == title)
        # Real Google blank response omits data; populated responses include it.
        return self.response({'spreadsheetId': sid, 'sheets': [sheet]},
                             error='TimeoutError' if self.read_error else None)


def completion(action, args=None):
    if action == 'finish':
        return {'choices': [{'message': {'role': 'assistant', 'content': 'Done'}, 'finish_reason': 'stop'}]}
    return {'choices': [{'message': {'role': 'assistant', 'content': None,
            'tool_calls': [{'id': 'call-1', 'type': 'function',
                           'function': {'name': action, 'arguments': json.dumps(args or {})}}]},
                        'finish_reason': 'tool_calls'}]}


def model_complete(payload):
    if len(payload['messages']) == 2:
        # All 64 scenarios differ. Obtain the exact semantic object from their frozen task.
        family = next(f for f in load_paper_manifest()['families']
                      if f['user_task'] == payload['messages'][1]['content'])
        return completion('append_row', family['target_semantic_m'])
    if len(payload['messages']) == 4:
        return completion('append_row', json.loads(payload['messages'][2]['tool_calls'][0]['function']['arguments']))
    return completion('finish')


def setup_arm(tmp_path, *, world, policy, decisions=None):
    base = load_paper_manifest()
    manifest = replication.bind_manifest(base, 'a' * 32, 'new-1', qualification=True)
    family = manifest['families'][0]
    arm = next(a for a in family['arms'] if (a['hidden_world'], a['policy']) == (world, policy))
    api = API()
    api.sheets['new-1'] = json.loads(replication.create_request(manifest).body)
    evidence = DurablePaperEvidence(tmp_path / 'arm', provider='sheets',
        family_id=family['family_id'], arm_id=arm['arm_id'],
        manifest_sha256=sha256_hex(canonical_json_bytes(manifest)), runtime_sha256={})
    steps = iter(decisions or [])
    def complete(payload):
        if len(payload['messages']) == 2:
            return completion('append_row', family['target_semantic_m'])
        if decisions is None:
            return model_complete(payload)
        decision = next(steps)
        if isinstance(decision, Exception):
            raise decision
        return decision
    model = PaperModelSession(provider='sheets', family=family,
        common=manifest['model_visible_common'], complete=complete, evidence=evidence)
    model.generate_original()
    if policy == 'LLM_REGENERATION':
        model.begin_regeneration()
    def run():
        return collect_sheets_arm(manifest=manifest, family=family, arm=arm,
            evidence=evidence, send=api.send, model=model,
            clock=lambda: api.elapsed, wait_until=lambda t: None)
    return api, evidence, run


@pytest.mark.parametrize('world,policy,reason,posts', [
    ('H0', 'EXACT_REPLAY', 'EXACTLY_ONE', 1),
    ('H1', 'EXACT_REPLAY', 'DUPLICATE', 2),
    ('H0', 'LLM_REGENERATION', 'EXACTLY_ONE', 1),
    ('H1', 'LLM_REGENERATION', 'DUPLICATE', 2),
])
def test_all_four_real_collector_paths(tmp_path, world, policy, reason, posts):
    api, ev, run = setup_arm(tmp_path, world=world, policy=policy)
    result, stopped = run()
    assert not stopped and result.reason == reason
    writes = [r for r in api.requests if r.method == 'POST']
    assert len(writes) == posts
    if world == 'H1' and policy == 'EXACT_REPLAY':
        assert writes[0] == writes[1]
        assert (ev.directory / 'h1-constructor.json').exists()
    if policy == 'EXACT_REPLAY':
        assert not list(ev.directory.glob('model-regeneration-*'))


def test_fourth_action_is_measured_without_fourth_dispatch(tmp_path):
    args = load_paper_manifest()['families'][0]['target_semantic_m']
    api, ev, run = setup_arm(tmp_path, world='H0', policy='LLM_REGENERATION',
                            decisions=[completion('append_row', args)] * 4)
    result, _ = run()
    assert result.reason == 'DUPLICATE'
    assert len([r for r in api.requests if r.method == 'POST']) == 3
    assert json.loads((ev.directory / 'arm-projection.json').read_bytes())['recovery_terminal'] == 'ACTION_BUDGET_EXCEEDED'


@pytest.mark.parametrize('action,args', [('append_row', {'item': 'x', 'detail': 'y', 'sheet_id': 99}),
                                        ('list_rows', {'extra': 'forbidden'}),
                                        ('delete_everything', {})])
def test_invalid_model_arguments_never_dispatch(tmp_path, action, args):
    api, ev, run = setup_arm(tmp_path, world='H1', policy='LLM_REGENERATION',
                            decisions=[completion(action, args), completion('finish')])
    result, _ = run()
    assert result.reason == 'EXACTLY_ONE'
    assert len([r for r in api.requests if r.method == 'POST']) == 1  # H1 constructor only
    projection = json.loads((ev.directory / 'arm-projection.json').read_bytes())
    assert projection['tool_action_attempt_count'] == 1


def test_model_failure_keeps_final_state_evidence_but_excludes_behavior(tmp_path):
    api, ev, run = setup_arm(tmp_path, world='H1', policy='LLM_REGENERATION',
                            decisions=[TimeoutError('synthetic')])
    result, _ = run()
    assert result.reason == 'model_infrastructure_failure' and result.state_correct is None
    assert (ev.directory / 'model-failure-regeneration-0.json').exists()


@pytest.mark.parametrize('status', [401, 403, 429])
def test_provider_stop_never_resends(tmp_path, status):
    api, ev, run = setup_arm(tmp_path, world='H1', policy='EXACT_REPLAY')
    api.fail_post = status
    result, stopped = run()
    assert stopped and result.state_correct is None
    assert len([r for r in api.requests if r.method == 'POST']) == 1


def test_complete_parseable_body_with_transport_error_cannot_certify(tmp_path):
    api, ev, run = setup_arm(tmp_path, world='H1', policy='EXACT_REPLAY')
    api.read_error = True
    result, _ = run()
    assert result.state_correct is None
    assert not [r for r in api.requests if r.method == 'POST']


def test_complete_256_arm_run_and_integrity_verification(tmp_path):
    api = API()
    def acquire():
        token = SimpleNamespace(value='fake-bearer', expires_at=api.elapsed + 3600,
                                clock_uncertainty_seconds=1)
        metadata = SimpleNamespace(projection=lambda: {'expires_at': token.expires_at})
        return token, metadata
    plan = {'namespace': 'b' * 32, 'runtime_sha256': {},
            'dataset_role': 'POST_INCIDENT_REPLICATION_NOT_PRIMARY_REPLACEMENT'}
    path = tmp_path / 'run'
    summary = replication.run_replication(plan=plan, run_dir=path, acquire=acquire,
        transport=api.send, verify_access=lambda *a: {'permission_id': 'sole-owner'},
        model_complete=model_complete, progress=lambda *a, **kw: None,
        clock=lambda: api.elapsed, wall=lambda: api.elapsed, sleep=api.sleep)
    assert summary['status'] == 'COMPLETED' and summary['projected_arms'] == 256
    assert verify_run(path) == summary
    assert len(api.sheets) == 2
    assert len(list((path / 'qualification').glob('*/arm-projection.json'))) == 4
    assert len(list((path / 'collection').glob('*/arm-projection.json'))) == 256
    saved = json.loads((path / 'manifest.json').read_bytes())
    historical = load_paper_manifest()
    assert saved['spreadsheet_id'] != historical['spreadsheet_id']
    for new, old in zip(saved['families'], historical['families']):
        assert new['model_config'] == old['model_config']
        assert new['user_task'] == old['user_task']
    (path / 'collection' / 'run-authorization.json').write_bytes(b'{}')
    with pytest.raises(ValueError, match='inventory'):
        verify_run(path)


def test_pacing_and_token_reacquisition_only_on_explicit_stage_boundary():
    api = API()
    issued = []
    def acquire():
        issued.append(api.elapsed)
        return (SimpleNamespace(value='secret', expires_at=api.elapsed + 3600, clock_uncertainty_seconds=1),
                SimpleNamespace(projection=lambda: {}))
    starts = []
    session = replication.PacedSession(acquire=acquire,
        transport=lambda *a, **kw: starts.append(api.elapsed), event=lambda *a: None,
        clock=lambda: api.elapsed, wall=lambda: api.elapsed, sleep=api.sleep)
    assert session.ensure(2100)
    session.send(None); session.send(None)
    assert starts[1] - starts[0] >= 1.1 - 1e-9
    api.elapsed += 2000
    assert session.ensure(2100)
    assert len(issued) == 2
    api.elapsed += 3570
    with pytest.raises(ValueError, match='token'):
        session.send(None)
    assert len(issued) == 2


def test_plan_rejects_source_drift_and_noncanonical_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(replication, 'git_head', lambda root: 'a' * 40)
    monkeypatch.setattr(replication, 'code_identity', lambda root: {'source': 'b' * 64})
    plan = replication.build_plan('a' * 32)
    target = tmp_path / 'plan.json'
    replication.write_once(target, plan)
    assert replication.check_plan(target) == plan
    monkeypatch.setattr(replication, 'code_identity', lambda root: {'source': 'c' * 64})
    with pytest.raises(ValueError, match='changed'):
        replication.check_plan(target)
    with pytest.raises(FileExistsError):
        replication.write_once(target, plan)


def test_cli_consumed_plan_refuses_before_any_oauth(tmp_path, monkeypatch):
    from scripts import run_study2_sheets_replication as cli
    plan = tmp_path / 'plan.json'
    plan.write_text('{}')
    plan.with_name('plan.json.started').write_text('{}')
    monkeypatch.setattr(cli, 'check_plan', lambda p: {})
    with pytest.raises(SystemExit) as exc:
        cli.main(['run', '--plan', str(plan)])
    assert exc.value.code == 2


def test_failed_live_control_stops_before_experiment_creation(tmp_path):
    api = API()
    api.fail_post = 429
    token = SimpleNamespace(value='fake', expires_at=99999, clock_uncertainty_seconds=1)
    plan = {'namespace': 'c' * 32, 'runtime_sha256': {}, 'dataset_role': 'replication'}
    directory = tmp_path / 'failed'
    with pytest.raises(ValueError, match='stopped'):
        replication.run_replication(plan=plan, run_dir=directory,
            acquire=lambda: (token, SimpleNamespace(projection=lambda: {})),
            transport=api.send, verify_access=lambda *a: {'id': 'owner'},
            model_complete=model_complete, progress=lambda *a, **kw: None,
            clock=lambda: api.elapsed, wall=lambda: api.elapsed, sleep=api.sleep)
    assert len(api.sheets) == 1
    assert not (directory / 'collection').exists()
    assert json.loads((directory / 'run-summary.json').read_bytes())['status'] == 'STOPPED_NO_RESUME'
    with pytest.raises(ValueError, match='stopped or incomplete'):
        verify_run(directory)


def test_disappearing_acknowledged_row_is_not_a_behavioral_failure(tmp_path):
    api, ev, run = setup_arm(tmp_path, world='H1', policy='EXACT_REPLAY')
    original_response = api.response
    def response(body, status=200, error=None):
        if 'sheets' in body and len([r for r in api.requests if r.method == 'POST']) == 2:
            body = copy.deepcopy(body)
            body['sheets'][0]['data'] = [{}]  # Complete explicit blank, contradicts two acks.
        return original_response(body, status, error)
    api.response = response
    result, _ = run()
    assert result.state_correct is None
    assert result.reason == 'causal_ledger_contradiction'
    doc = json.loads((ev.directory / 'arm-projection.json').read_bytes())
    assert doc['minimum_rows_from_causal_evidence'] == 2
