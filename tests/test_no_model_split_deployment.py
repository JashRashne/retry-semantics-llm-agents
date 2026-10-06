"""Deployment-only adversarial tests: no scientific arm is ever executed."""
import builtins
import importlib.util
import json
import shutil
from pathlib import Path
import socket
import sys
import zipfile

import pytest
from retry_semantics.baselines import collection, readiness, partition_runtime
from retry_semantics.baselines import partitions as p
from retry_semantics.baselines.merge_partitions import validate_merge
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'research/baselines/no_model/split_deployment_v1'
V3 = ROOT / 'research/baselines/no_model/precollection_v3'


def load_script(name):
    spec = importlib.util.spec_from_file_location('split_test_' + name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def forbidden_science_and_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('scientific/network work reached deployment-only test')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(collection, 'execute_arm', forbidden)
    from retry_semantics.baselines import harness
    for name in ('run_ticket_arm', 'run_github_arm', 'run_sheets_arm'):
        monkeypatch.setattr(harness, name, forbidden)


@pytest.fixture
def schedule():
    return json.loads((V3 / 'frozen_bindings/schedule.json').read_bytes())


def test_exact_partition_counts_indices_union(schedule):
    manifest = p.build_manifest(schedule)
    assert manifest == json.loads((D / 'partition_manifest.json').read_bytes())
    groups = [p.selected_entries(schedule, manifest, key) for key in p.PARTITIONS]
    assert [len(group) for group in groups] == [640, 128, 128]
    indices = [{e['schedule_index'] for e in group} for group in groups]
    assert set.union(*indices) == set(range(896))
    assert all(not a & b for i, a in enumerate(indices) for b in indices[i + 1:])
    for group in groups:
        assert all(e == schedule[e['schedule_index']] for e in group)
        assert [e['schedule_index'] for e in group] == sorted(e['schedule_index'] for e in group)


def test_claims_independent_durable_and_no_reconsume(tmp_path):
    for key in ('github-vm', 'sheets-mac', 'tickets-local'):
        path = p.claim_partition(tmp_path, key, output=tmp_path / ('output-' + key),
            readiness_sha256='a' * 64, deployment_sha256='b' * 64)
        assert path.name == p.CLAIMS[key]
        assert sum((tmp_path / n).exists() for n in p.CLAIMS.values()) == ('github-vm', 'sheets-mac', 'tickets-local').index(key) + 1
        raw = path.read_bytes()
        with pytest.raises((ValueError, FileExistsError)):
            p.claim_partition(tmp_path, key, output=tmp_path / 'replacement', readiness_sha256='x', deployment_sha256='y')
        assert path.read_bytes() == raw


def test_claim_durability_failure_retains_claim_and_prevents_reconsume(tmp_path, monkeypatch):
    def failure(fd): raise OSError('synthetic fsync failure')
    monkeypatch.setattr(p.os, 'fsync', failure)
    with pytest.raises(OSError, match='fsync'):
        p.claim_partition(tmp_path, 'github-vm', output=tmp_path / 'never-started',
            readiness_sha256='a' * 64, deployment_sha256='b' * 64)
    assert (tmp_path / p.CLAIMS['github-vm']).is_file()
    with pytest.raises(ValueError, match='consumed'):
        p.claim_partition(tmp_path, 'github-vm', output=tmp_path / 'replacement',
            readiness_sha256='a' * 64, deployment_sha256='b' * 64)


@pytest.mark.parametrize('partition', list(p.PARTITIONS))
def test_factory_never_reaches_other_provider_credentials(schedule, partition, tmp_path, monkeypatch):
    manifest = p.build_manifest(schedule)
    package = {'partition': partition, 'schedule': schedule, 'partition_manifest': manifest}
    reached = []
    def factory(which):
        def build(*args):
            assert which == partition
            reached.append(which)
            return (lambda *args: None), (lambda *args: None)
        return build
    monkeypatch.setattr(partition_runtime, 'github_runtime', factory('github-vm'))
    monkeypatch.setattr(partition_runtime, 'sheets_runtime', factory('sheets-mac'))
    executor = partition_runtime.executor_for(package, tmp_path / 'not-created', Path('/not-read'))
    assert reached == ([] if partition == 'tickets-local' else [partition])
    for entry in schedule:
        if entry['source_set'] not in p.spec(partition)[1]:
            with pytest.raises(ValueError, match='outside selected partition'):
                executor(entry, tmp_path / 'not-created')
    assert not (tmp_path / 'not-created').exists()


@pytest.mark.parametrize('partition', list(p.PARTITIONS))
def test_real_factories_import_no_other_credentials(partition, tmp_path, monkeypatch, schedule):
    real_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if partition != 'sheets-mac' and name in ('run_sheets_paper_live_readiness_session', 'run_sheets_paper_append_qualification_session'):
            pytest.fail('wrong partition imports OAuth acquisition capability')
        if partition != 'github-vm' and name == 'prepare_no_model_precollection':
            pytest.fail('wrong partition imports GitHub credential loader')
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    package = {'partition': partition, 'schedule': schedule, 'partition_manifest': p.build_manifest(schedule)}
    partition_runtime.executor_for(package, tmp_path / 'not-created', Path('/not-read'))
    assert not (tmp_path / 'not-created').exists()


def test_no_authorization_no_collection_or_claim(tmp_path, monkeypatch):
    launcher = load_script('collect_no_model_baseline')
    monkeypatch.setattr(launcher, 'verified_package', lambda *a, **kw: pytest.fail('unauthorized file access'))
    args = ['collect', '--partition', 'github-vm', '--bindings', '/not-read', '--lock', '/not-read', '--lock-sha256', '0' * 64]
    with pytest.raises(collection.CollectionRefused, match='authorization'):
        launcher.main(args)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('extra', [[], ['--partition', 'all'], ['--partition', 'github-vm', '--partition', 'sheets-mac']])
def test_exactly_one_partition_cli_no_all(extra, monkeypatch):
    launcher = load_script('collect_no_model_baseline')
    # Synthetic gate bypass tests only argument refusal; no actual authorization supplied.
    monkeypatch.setattr(launcher, 'require_authorization', lambda _: None)
    monkeypatch.setattr(launcher, 'verified_package', lambda *a, **kw: pytest.fail('bad partition accessed runtime'))
    args = ['collect', '--bindings', '/not-read', '--lock', '/not-read', '--lock-sha256', '0' * 64,
        '--output', '/not-created'] + extra
    with pytest.raises(SystemExit) as e:
        launcher.main(args)
    assert e.value.code == 2


def test_serial_refuses_wrong_source_before_creating_output(schedule, tmp_path):
    for partition in p.PARTITIONS:
        wrong = next(e for e in schedule if e['source_set'] not in p.spec(partition)[1])
        with pytest.raises(ValueError, match='outside selected partition'):
            collection.run_serial([wrong], tmp_path / partition, lambda *a: pytest.fail('wrong-source execution'), partition=partition)
        assert not (tmp_path / partition).exists()


@pytest.fixture
def merge_fixture(schedule, tmp_path):
    manifest = p.build_manifest(schedule)
    lock = json.loads((V3 / 'collection_readiness_lock.json').read_bytes())
    sha = readiness.file_digest(V3 / 'collection_readiness_lock.json')
    dirs = {}
    for key in p.PARTITIONS:
        entries = p.selected_entries(schedule, manifest, key)
        folder = tmp_path / key
        dirs[key] = folder
        m = manifest['partitions'][key]
        metadata = dict(p.provenance(key), readiness_lock_sha256=sha, deployment_lock_sha256='b' * 64,
            schedule_sha256=lock['schedule_sha256'], partition_schedule_sha256=m['partition_schedule_sha256'],
            git_head=lock['git_head'], dependency_versions=lock['runtime_dependency_versions'])
        # Inert synthetic fixture: no constructor, evaluator or recovery invocation.
        collection.run_serial(entries, folder,
            lambda entry, _: (collection._unrun(entry, 'SYNTHETIC_OFFLINE_MERGE_FIXTURE'), True),
            partition=key, deployment_provenance=metadata)
    return dict(schedule=schedule, manifest=manifest, directories=dirs,
        readiness_lock=lock, readiness_sha256=sha, deployment_sha256='b' * 64)


def test_merge_exact_union_explicit_unrun_and_immutable(merge_fixture):
    before = {str(f): f.read_bytes() for folder in merge_fixture['directories'].values() for f in folder.rglob('*') if f.is_file()}
    result = validate_merge(**merge_fixture)
    assert result['counts'] == {'TICKETS_LOCAL': 640, 'GITHUB_VM': 128, 'SHEETS_MAC': 128}
    assert result['union'] == 896 and result['duplicates'] == result['provider_calls'] == 0
    assert before == {str(f): f.read_bytes() for folder in merge_fixture['directories'].values() for f in folder.rglob('*') if f.is_file()}


@pytest.mark.parametrize('attack', ['duplicate', 'missing', 'wrong-partition', 'request', 'index', 'world', 'provenance'])
def test_merge_rejects_adversarial_results(merge_fixture, attack):
    folder = merge_fixture['directories']['github-vm']
    file = sorted(folder.glob('*/result.json'))[0]
    value = json.loads(file.read_bytes())
    if attack == 'missing': file.unlink()
    elif attack == 'duplicate':
        other = sorted(folder.glob('*/result.json'))[1]; other.write_bytes(file.read_bytes())
    elif attack == 'provenance':
        other = folder / 'deployment_provenance.json'; data = json.loads(other.read_bytes()); data['execution_partition'] = 'SHEETS_MAC'; other.write_text(json.dumps(data))
    else:
        key, new = {'wrong-partition': ('execution_partition', 'SHEETS_MAC'),
            'request': ('stored_request_identity_sha256', '0' * 64),
            'index': ('schedule_index', 0), 'world': ('hidden_world', 'INVALID')}[attack]
        value[key] = new; file.write_text(json.dumps(value))
    with pytest.raises(ValueError): validate_merge(**merge_fixture)


def test_pinned_upgrade_same_lock_vm_exact_bytes_and_deterministic_package(tmp_path, monkeypatch):
    prepare = load_script('prepare_no_model_split_deployment')
    lock_path = tmp_path / 'upgrade.json'
    prepare.freeze_deployment(ROOT, lock_path)
    sha = readiness.file_digest(V3 / 'collection_readiness_lock.json')
    # No VM request re-serialization is allowed; scope verification is read-only.
    monkeypatch.setattr(collection.preparation, 'bind_github', lambda **kw: pytest.fail('VM regenerated request'))
    package = collection.verified_package(V3 / 'frozen_bindings', V3 / 'collection_readiness_lock.json', sha,
        root=ROOT, partition='github-vm', deployment_path=lock_path, deployment_sha256=readiness.file_digest(lock_path))
    assert len(package['selected_schedule']) == 128 and len(package['schedule']) == 896
    upgrade = json.loads(lock_path.read_bytes())
    assert set(upgrade['replacements']) == {'scripts/collect_no_model_baseline.py','src/retry_semantics/baselines/collection.py'}
    assert upgrade['readiness_lock_sha256'] == sha
    for name, v in upgrade['replacements'].items():
        assert readiness.file_digest(ROOT / v['previous_file']) == v['previous_sha256']
    # Independent temporary filesystem containing ONLY transfer inputs.
    small = tmp_path / 'root'; small.mkdir()
    old = json.loads((V3 / 'collection_readiness_lock.json').read_bytes())
    files = set(old['runtime_files']) | set(old['evidence_files']) | set(upgrade['deployment_runtime_files'])
    files |= {v['previous_file'] for v in upgrade['replacements'].values()}
    files |= {upgrade['partition_manifest_file'], str(prepare.V3 / 'collection_readiness_lock.json')}
    for name in old['binding_files']:
        if not name.endswith('/stored-original.json') or name in {e['stored_original_file'] for e in package['selected_schedule']}:
            files.add(str(prepare.V3 / 'frozen_bindings' / name))
    from retry_semantics.study2 import github_paper_manifest as authority
    files |= set(authority.SOURCE_SHA256) | {authority.MODEL_AMENDMENT_PATH, str(authority.REGISTRY_PATH), str(authority.MANIFEST_PATH)}
    files |= {str(f.relative_to(ROOT)) for f in (ROOT / 'research/study2').rglob('*PAPER_NAMESPACE_RESERVATION*.json')}
    for name in files:
        target = small / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / name, target)
    staged_lock = small / prepare.D / 'deployment_lock.json'; shutil.copyfile(lock_path, staged_lock)
    a, b = tmp_path / 'vm-a.zip', tmp_path / 'vm-b.zip'
    first = prepare.github_package(small, staged_lock, a)
    second = prepare.github_package(small, staged_lock, b)
    assert first['sha256'] == second['sha256'] and a.read_bytes() == b.read_bytes()
    with zipfile.ZipFile(a) as z:
        names = z.namelist()
        originals = [name for name in names if name.startswith(str(prepare.V3 / 'frozen_bindings') + '/') and name.endswith('/stored-original.json')]
        assert len(originals) == 128
        assert {name.split('/')[-2] for name in originals} == {f"{e['schedule_index']:03d}" for e in package['selected_schedule']}
        for name in originals: assert z.read(name) == (ROOT / name).read_bytes()
        assert not any(Path(name).name in {'.env', 'google-desktop-client.json'} for name in names)
    with pytest.raises(ValueError, match='overwrite'):
        prepare.github_package(small, staged_lock, a)


@pytest.mark.parametrize('partition', list(p.PARTITIONS))
def test_correct_route_has_no_wrong_provider_capability(schedule, partition, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    package = {'partition': partition, 'schedule': schedule, 'partition_manifest': p.build_manifest(schedule)}
    seen = []
    def inert(entry, directory, package, *, github_send, sheets_send, before_provider_family):
        if partition != 'github-vm':
            assert github_send is partition_runtime.forbidden_provider
            with pytest.raises(collection.CollectionRefused): github_send(None)
        if partition != 'sheets-mac':
            assert sheets_send is partition_runtime.forbidden_provider
            with pytest.raises(collection.CollectionRefused): sheets_send(None)
        if partition == 'tickets-local': assert before_provider_family is partition_runtime.forbidden_provider
        seen.append(entry['schedule_index'])
        return collection._unrun(entry, 'SYNTHETIC_DISPATCH_FIXTURE'), False
    monkeypatch.setattr(collection, 'execute_arm', inert)
    executor = partition_runtime.executor_for(package, tmp_path / 'not-created', Path('/not-read'))
    entry = p.selected_entries(schedule, package['partition_manifest'], partition)[0]
    executor(entry, tmp_path / 'not-created')
    altered = dict(entry, stored_request_identity_sha256='changed')
    with pytest.raises(collection.CollectionRefused, match='differs'):
        executor(altered, tmp_path / 'not-created')
    assert seen == [entry['schedule_index']]


def test_all_scientific_frozen_bytes_and_old_protected_files_unchanged():
    before = json.loads((D / 'frozen_before.json').read_bytes())['files']
    assert all(readiness.file_digest(ROOT / name) == sha for name, sha in before.items())
    assert readiness.verify_protected(ROOT / 'research/baselines/no_model/protected_before.json') == 5942
    # Collection-consumption claims are intentionally mutable lifecycle artifacts.
    # Their durability/no-reconsume semantics are tested independently above.
