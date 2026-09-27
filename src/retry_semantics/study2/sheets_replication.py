"""Separately labelled Sheets replication; never reopens the historical primary.

The operator freezes a plan before OAuth. A consumed plan and any existing run
refuse reuse. Provider mutations never retry. All effects are dependency injected
so the complete orchestration can be exercised without network access.
"""
from __future__ import annotations

import copy
import json
import importlib.metadata
import platform
import tomllib
import os
import re
import subprocess
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from urllib.parse import quote

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.provider_paper_collection import (
    PaperCollectionError, _schedule, collect_sheets_arm, validate_run_directory,
)
from retry_semantics.study2.provider_paper_io import DurablePaperEvidence, PaperRequest
from retry_semantics.study2.provider_paper_model import PaperModelSession
from retry_semantics.study2.sheets_paper_blank_readiness import check_precollection_blank
from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest, read_target
from retry_semantics.study2.sheets_paper_readiness import check_topology, metadata_target

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = 'research/protocol/STUDY2_SHEETS_REPLICATION_V1.md'
MIN_REQUEST_INTERVAL = 1.1
FAMILY_TOKEN_RESERVE = 2100.0


def write_once(path: Path, value: dict) -> None:
    raw = canonical_json_bytes(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def code_identity(root: Path = ROOT) -> dict[str, str]:
    paths = sorted({*root.glob('src/**/*.py'), *root.glob('scripts/*.py'),
                    *root.glob('tests/*.py'), root / 'pyproject.toml', root / 'uv.lock', root / PROTOCOL})
    return {str(p.relative_to(root)): sha256_hex(p.read_bytes()) for p in paths}


def git_head(root: Path = ROOT, *, clean: bool = True) -> str:
    def git(*args):
        return subprocess.run(['git', *args], cwd=root, capture_output=True,
                              text=True, check=True).stdout.strip()
    if clean and git('status', '--porcelain', '--untracked-files=all'):
        raise PaperCollectionError('Commit the reviewed changes before freezing/running the replication plan')
    return git('rev-parse', 'HEAD')


def runtime_versions(root: Path = ROOT) -> dict:
    required = tomllib.loads((root / 'pyproject.toml').read_text())['project']['dependencies']
    versions = {}
    for pin in required:
        name, version = pin.split('==')
        installed = importlib.metadata.version(name)
        if installed != version:
            raise PaperCollectionError(f'Installed dependency differs from pin: {name}')
        versions[name] = installed
    return {'python': platform.python_version(), 'dependencies': versions}


def build_plan(namespace: str, *, root: Path = ROOT) -> dict:
    if re.fullmatch('[0-9a-f]{32}', namespace) is None:
        raise PaperCollectionError('invalid replication namespace')
    base = load_paper_manifest(root=root)
    return {
        'schema': 'study2-sheets-replication-plan-v1',
        'dataset_role': 'POST_INCIDENT_REPLICATION_NOT_PRIMARY_REPLACEMENT',
        'namespace': namespace, 'git_head': git_head(root),
        'base_manifest_sha256': sha256_hex(canonical_json_bytes(base)),
        'runtime_sha256': code_identity(root), 'runtime_versions': runtime_versions(root),
        'families': 64, 'arms': 256, 'request_interval_seconds': MIN_REQUEST_INTERVAL,
        'family_token_reserve_seconds': FAMILY_TOKEN_RESERVE,
        'operator_review_required': True,
        'independent_audit_claimed': False,
        'no_resume_no_refill': True,
    }


def check_plan(path: Path, *, root: Path = ROOT) -> dict:
    raw = path.read_bytes()
    plan = json.loads(raw)
    if raw != canonical_json_bytes(plan) or plan != build_plan(plan['namespace'], root=root):
        raise PaperCollectionError('Plan, source, protocol, or committed HEAD changed; do not execute')
    return plan


def bind_manifest(base: dict, namespace: str, spreadsheet_id: str,
                  *, qualification: bool = False) -> dict:
    """Change only harness-owned scope; copy scientific settings and schedule."""
    if re.fullmatch('[A-Za-z0-9_-]+', spreadsheet_id) is None:
        raise PaperCollectionError('invalid created spreadsheet ID')
    role = 'qualification' if qualification else 'replication'
    families = copy.deepcopy(base['families'][:1] if qualification else base['families'])
    for index, (_, arm) in enumerate(_schedule({'families': families})):
        arm['spreadsheet_id'] = spreadsheet_id
        arm['sheet_id'] = index + 1
        arm['arm_marker'] = 'RS2-SHEETS-V1-' + sha256_hex(
            f'{namespace}:{role}:{arm["arm_id"]}'.encode())[:32]
        arm['read_target'] = read_target(spreadsheet_id, arm['tab_title'])
    return {
        'schema': 'study2-sheets-replication-manifest-v1', 'dataset_role': role,
        'source_primary_manifest_sha256': sha256_hex(canonical_json_bytes(base)),
        'run_namespace': namespace,
        'spreadsheet_id': spreadsheet_id,
        'spreadsheet_title': f'retry-semantics-sheets-{role}-{namespace}',
        'model_visible_common': copy.deepcopy(base['model_visible_common']),
        'observation_policy': copy.deepcopy(base['observation_policy']),
        'schedule_definition': copy.deepcopy(base['schedule_definition']),
        'families': families,
    }


def create_request(manifest: dict) -> PaperRequest:
    body = {'properties': {'title': manifest['spreadsheet_title']}, 'sheets': [
        {'properties': {'sheetId': arm['sheet_id'], 'title': arm['tab_title'],
                        'sheetType': 'GRID',
                        'gridProperties': {'rowCount': 100, 'columnCount': 3}}}
        for _, arm in _schedule(manifest)]}
    fields = 'spreadsheetId,properties(title),sheets(properties(sheetId,title,sheetType,gridProperties(rowCount,columnCount)))'
    return PaperRequest('POST', 'https://sheets.googleapis.com/v4/spreadsheets?fields=' + quote(fields, safe=''),
                        (('content-type', 'application/json'),), canonical_json_bytes(body))


class PacedSession:
    def __init__(self, *, acquire, transport, event, clock=time.monotonic,
                 wall=time.time, sleep=time.sleep):
        self.acquire, self.transport, self.event = acquire, transport, event
        self.clock, self.wall, self.sleep = clock, wall, sleep
        self.token = None
        self.last_started = None
        self.generation = 0
        self.app_identity = None

    def ensure(self, seconds: float) -> bool:
        if (self.token is not None and self.token.expires_at - self.wall()
                > seconds + self.token.clock_uncertainty_seconds):
            return False
        self.token, metadata = self.acquire()
        self.generation += 1
        public = metadata.projection()
        app = public.get('public_config_sha256')
        if self.app_identity is not None and app != self.app_identity:
            raise PaperCollectionError('OAuth app configuration changed')
        self.app_identity = app
        self.event(f'oauth-{self.generation}', public)
        if self.token.expires_at - self.wall() <= seconds + self.token.clock_uncertainty_seconds:
            raise PaperCollectionError('fresh OAuth token cannot cover the next bounded stage')
        return True

    def send(self, request: PaperRequest):
        if self.last_started is not None:
            self.sleep(max(0.0, self.last_started + MIN_REQUEST_INTERVAL - self.clock()))
        if (self.token is None or self.token.expires_at - self.wall()
                <= 40 + self.token.clock_uncertainty_seconds):
            raise PaperCollectionError('token expired or insufficient; no dispatch, no automatic retry')
        self.last_started = self.clock()
        return self.transport(request, credential=self.token.value)


def run_replication(*, plan: dict, run_dir: Path, acquire, transport,
                    verify_access, model_complete, progress=print,
                    clock=time.monotonic, wall=time.time, sleep=time.sleep) -> dict:
    """Execute one consumed plan. CLI owns plan validation and exclusive claim."""
    run_dir = validate_run_directory(run_dir)
    run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_once(run_dir / 'plan.json', plan)
    base = load_paper_manifest()
    runtime = plan['runtime_sha256']
    plan_sha = sha256_hex(canonical_json_bytes(plan))

    def evidence(directory, manifest, family_id='SETUP', arm_id='SETUP'):
        return DurablePaperEvidence(directory, provider='sheets', family_id=family_id,
            arm_id=arm_id, manifest_sha256=sha256_hex(canonical_json_bytes(manifest)),
            runtime_sha256=runtime)

    setup = evidence(run_dir / 'setup', plan)
    session = PacedSession(acquire=acquire, transport=transport, event=setup.event,
                           clock=clock, wall=wall, sleep=sleep)
    principal = None
    access_index = 0
    experiment_id = None
    results = []

    def access(spreadsheet_id):
        nonlocal principal, access_index
        access_index += 1
        folder = run_dir / 'setup' / f'access-{access_index}'
        folder.mkdir(mode=0o700)
        observed = verify_access(folder, spreadsheet_id, session.token.value)
        if principal is not None and observed != principal:
            raise PaperCollectionError('OAuth principal changed')
        principal = observed

    def ensure(seconds):
        changed = session.ensure(seconds)
        if changed and experiment_id is not None:
            access(experiment_id)

    def create(qualification):
        prospective = bind_manifest(base, plan['namespace'], 'UNBOUND', qualification=qualification)
        response = setup.record('scope_create', create_request(prospective), session.send)
        if response.status != 200 or response.error is not None:
            raise PaperCollectionError('Spreadsheet creation uncertain/failed; preserve evidence, never resend')
        body = json.loads(response.body)
        spreadsheet_id = body['spreadsheetId']
        if spreadsheet_id == base['spreadsheet_id']:
            raise PaperCollectionError('provider returned historical scope')
        bound = bind_manifest(base, plan['namespace'], spreadsheet_id, qualification=qualification)
        expected = json.loads(create_request(bound).body)
        if body != {'spreadsheetId': spreadsheet_id, **expected}:
            raise PaperCollectionError('created topology differs from prospective request')
        access(spreadsheet_id)
        return bound

    def execute_family(manifest, family, directory, complete, *, control=False):
        family_results = []
        original = None
        for arm in sorted(family['arms'], key=lambda a: a['serial_position']):
            index = family['scheduled_attempt_index'] * 4 + arm['serial_position'] - 1
            ev = evidence(directory / f'{index:03d}-{family["family_id"]}-{arm["serial_position"]}',
                          manifest, family['family_id'], arm['arm_id'])
            model = PaperModelSession(provider='sheets', family=family,
                common=manifest['model_visible_common'],
                complete=scripted_control(arm) if control else complete, evidence=ev)
            if original is None:
                original = model.generate_original()
            model.original = original
            raw = canonical_json_bytes(original)
            ev.event('original-m-binding', {'provider': 'sheets', 'family_id': family['family_id'],
                'arm_id': arm['arm_id'], 'original_message_hex': raw.hex(),
                'original_message_sha256': sha256_hex(raw),
                'manifest_sha256': sha256_hex(canonical_json_bytes(manifest))})
            if arm['policy'] == 'LLM_REGENERATION':
                model.begin_regeneration()
            try:
                result, stopped = collect_sheets_arm(manifest=manifest, family=family, arm=arm,
                    evidence=ev, send=session.send, model=model, clock=clock,
                    wait_until=lambda target: sleep(max(0, target - clock())))
            except Exception as exc:
                ev.event('run-abort', {'reason': type(exc).__name__, 'arm_id': arm['arm_id']})
                raise
            family_results.append(result)
            progress(f'{manifest["dataset_role"]}: {index + 1}/{len(_schedule(manifest))} {arm["arm_id"]} {result.status} {result.reason}', flush=True)
            if stopped or result.reason.startswith(('pre_policy', 'H1_constructor', 'model_infrastructure', 'causal_ledger')):
                raise PaperCollectionError(f'collection stopped at {arm["arm_id"]}: {result.reason}')
        return family_results

    try:
        progress('Opening OAuth consent; use the same Google account throughout.', flush=True)
        ensure(FAMILY_TOKEN_RESERVE)
        qualification = create(True)
        write_once(run_dir / 'qualification-manifest.json', qualification)
        qfamily = qualification['families'][0]
        # A real pre-data model capability check, saved separately from synthetic policy controls.
        capability = PaperModelSession(provider='sheets', family=qfamily,
            common=qualification['model_visible_common'], complete=model_complete,
            evidence=evidence(run_dir / 'setup' / 'model-capability', qualification))
        capability.generate_original()

        def scripted_control(arm):
            def complete(payload):
                messages = payload['messages']
                if len(messages) == 2:
                    action, args = 'append_row', qfamily['target_semantic_m']
                elif len(messages) == 4:
                    action, args = (('append_row', qfamily['target_semantic_m'])
                                    if arm['hidden_world'] == 'H0' else ('list_rows', {}))
                else:
                    return {'choices': [{'message': {'role': 'assistant', 'content': 'Done'}, 'finish_reason': 'stop'}]}
                return {'choices': [{'message': {'role': 'assistant', 'content': None,
                    'tool_calls': [{'id': f'control-{len(messages)}', 'type': 'function',
                                   'function': {'name': action, 'arguments': json.dumps(args)}}]}, 'finish_reason': 'tool_calls'}]}
            return complete

        controls = execute_family(qualification, qfamily, run_dir / 'qualification', None, control=True)
        for arm, result in zip(sorted(qfamily['arms'], key=lambda a: a['serial_position']), controls):
            expected = 'DUPLICATE' if (arm['hidden_world'], arm['policy']) == ('H1', 'EXACT_REPLAY') else 'EXACTLY_ONE'
            if result.reason != expected:
                raise PaperCollectionError('live four-arm control failed; experiment not started')
        setup.event('qualification-pass', {'synthetic_policy_controls': True, 'experimental_observations': 0,
                                          'results': [asdict(r) for r in controls]})
        ensure(FAMILY_TOKEN_RESERVE)
        manifest = create(False)
        experiment_id = manifest['spreadsheet_id']
        if experiment_id == qualification['spreadsheet_id']:
            raise PaperCollectionError('qualification and experiment scopes overlap')
        write_once(run_dir / 'manifest.json', manifest)
        topology = setup.record('topology', PaperRequest('GET',
            'https://sheets.googleapis.com' + metadata_target(experiment_id), (), b''), session.send)
        if topology.error is not None:
            raise PaperCollectionError('topology transport incomplete')
        check_topology(manifest, topology.status, topology.body)
        for i, (_, arm) in enumerate(_schedule(manifest)):
            ensure(120)
            response = setup.record('precollection_blank', PaperRequest('GET',
                'https://sheets.googleapis.com' + arm['read_target'], (), b''), session.send)
            if response.error is not None:
                raise PaperCollectionError('blank-baseline transport incomplete')
            check_precollection_blank(manifest, arm, method='GET', target=arm['read_target'],
                                      status=response.status, raw=response.body)
            if (i + 1) % 32 == 0:
                progress(f'Blank readiness: {i + 1}/256', flush=True)
        setup.event('readiness-pass', {'blank_arms': 256, 'sole_owner': principal,
                                      'qualification_passed': True, 'operator_no_external_writers': True})
        collection = run_dir / 'collection'
        collection.mkdir(mode=0o700)
        write_once(collection / 'run-authorization.json', {
            'provider': 'sheets', 'dataset_role': plan['dataset_role'],
            'authorization_sha256': plan_sha, 'authorization_basis': 'operator-reviewed-replication-plan',
            'independent_audit_claimed': False, 'study2_paper_observations_before_run': 0,
            'manifest_sha256': sha256_hex(canonical_json_bytes(manifest)), 'runtime_sha256': runtime})
        for family in sorted(manifest['families'], key=lambda f: f['scheduled_attempt_index']):
            ensure(FAMILY_TOKEN_RESERVE)
            results.extend(execute_family(manifest, family, collection, model_complete))
        summary = {'status': 'COMPLETED', 'dataset_role': plan['dataset_role'],
                   'scheduled_arms': 256, 'projected_arms': len(results),
                   'counts': dict(Counter(r.status for r in results)),
                   'inconclusive_arms': sum(r.state_correct is None for r in results)}
    except BaseException as exc:
        summary = {'status': 'STOPPED_NO_RESUME', 'dataset_role': plan['dataset_role'],
                   'failure_type': type(exc).__name__,
                   'reason': str(exc) if isinstance(exc, PaperCollectionError) else type(exc).__name__,
                   'projected_arms_in_completed_families': len(results)}
        write_once(run_dir / 'run-summary.json', summary)
        raise
    write_once(run_dir / 'run-summary.json', summary)
    inventory = {str(p.relative_to(run_dir)): sha256_hex(p.read_bytes())
                 for p in sorted(run_dir.rglob('*')) if p.is_file()}
    write_once(run_dir / 'inventory.json', inventory)
    return summary
