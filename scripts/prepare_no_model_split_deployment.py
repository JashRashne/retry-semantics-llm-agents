"""Offline deployment lock/package construction. No scientific/provider actions."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from retry_semantics.baselines.audit_closure import write_json
from retry_semantics.baselines.partitions import build_manifest
from retry_semantics.serialization import sha256_hex

D = Path('research/baselines/no_model/split_deployment_v1')
V3 = Path('research/baselines/no_model/precollection_v3')
NEW_FILES = [
    'src/retry_semantics/baselines/partitions.py',
    'src/retry_semantics/baselines/partition_runtime.py',
    'src/retry_semantics/baselines/merge_partitions.py',
    'scripts/merge_no_model_partitions.py',
    'scripts/prepare_no_model_split_deployment.py',
    'tests/test_no_model_split_deployment.py',
    str(D / 'DEPLOYMENT_PROTOCOL.md'),
]
REPLACEMENTS = ['scripts/collect_no_model_baseline.py', 'src/retry_semantics/baselines/collection.py']


def freeze_deployment(root, output):
    original_path = root / V3 / 'collection_readiness_lock.json'
    original = json.loads(original_path.read_bytes())
    before = json.loads((root / D / 'frozen_before.json').read_bytes())['files']
    if any(sha256_hex((root / name).read_bytes()) != sha for name, sha in before.items()):
        raise ValueError('scientific frozen bytes changed')
    schedule = json.loads((root / V3 / 'frozen_bindings/schedule.json').read_bytes())
    manifest_file = D / 'partition_manifest.json'
    if json.loads((root / manifest_file).read_bytes()) != build_manifest(schedule):
        raise ValueError('partition manifest differs')
    upgrade = {'schema': 'no-model-deployment-only-upgrade-v1',
        'readiness_lock_sha256': sha256_hex(original_path.read_bytes()),
        'complete_schedule_sha256': original['schedule_sha256'],
        'partition_manifest_file': str(manifest_file),
        'partition_manifest_sha256': sha256_hex((root / manifest_file).read_bytes()),
        'replacements': {}, 'deployment_runtime_files': {},
        'scientific_evaluations': 0, 'scientific_provider_mutations': 0,
        'machine_binding': 'explicit partitions; hostname provenance only'}
    for name in REPLACEMENTS:
        previous = D / 'previous_deployment' / name
        if sha256_hex((root / previous).read_bytes()) != original['runtime_files'][name]:
            raise ValueError('archived original deployment source differs')
        upgrade['replacements'][name] = {'previous_sha256': original['runtime_files'][name],
            'previous_file': str(previous), 'current_sha256': sha256_hex((root / name).read_bytes())}
    for name in NEW_FILES:
        upgrade['deployment_runtime_files'][name] = sha256_hex((root / name).read_bytes())
    write_json(output, upgrade)
    return upgrade


def github_package(root, deployment_path, output):
    """Deterministic bytes: fixed ZIP metadata, sorted exact pinned files only."""
    if output.exists() or output.is_symlink():
        raise ValueError('VM artifact exists; no overwrite')
    deployment = json.loads(deployment_path.read_bytes())
    lock_path = V3 / 'collection_readiness_lock.json'
    original = json.loads((root / lock_path).read_bytes())
    if sha256_hex((root / lock_path).read_bytes()) != deployment['readiness_lock_sha256']:
        raise ValueError('original readiness lock mismatch')
    files = dict(original['runtime_files'])
    files.update(original['evidence_files'])  # Retain ALL original readiness/source checks.
    for name, replacement in deployment['replacements'].items():
        files[name] = replacement['current_sha256']
        files[replacement['previous_file']] = replacement['previous_sha256']
    files.update(deployment['deployment_runtime_files'])
    manifest_name = deployment['partition_manifest_file']
    files[manifest_name] = deployment['partition_manifest_sha256']
    files[str(lock_path)] = deployment['readiness_lock_sha256']
    files[str(deployment_path.relative_to(root))] = sha256_hex(deployment_path.read_bytes())
    bindings = V3 / 'frozen_bindings'
    schedule = json.loads((root / bindings / 'schedule.json').read_bytes())
    selected = {entry['stored_original_file'] for entry in schedule if entry['source_set'] == 'GitHub'}
    for name, sha in original['binding_files'].items():
        if name.endswith('/stored-original.json') and name not in selected:
            continue
        files[str(bindings / name)] = sha
    # Non-code frozen inputs read transitively by the existing scope authority.
    from retry_semantics.study2 import github_paper_manifest as authority
    resources = [*authority.SOURCE_SHA256, authority.MODEL_AMENDMENT_PATH,
        str(authority.REGISTRY_PATH), str(authority.MANIFEST_PATH)]
    resources += [str(p.relative_to(root)) for p in (root / 'research/study2').rglob('*PAPER_NAMESPACE_RESERVATION*.json')]
    for name in resources:
        files[name] = sha256_hex((root / name).read_bytes())
    from retry_semantics.baselines.partitions import runtime_expectations
    runtime_expectations(root, original, deployment['readiness_lock_sha256'],
        deployment_path, sha256_hex(deployment_path.read_bytes()))
    payload = {}
    for name, sha in sorted(files.items()):
        source = root / name
        if source.is_symlink() or any(p in {'.env', '.git', '.venv'} for p in source.parts):
            raise ValueError('forbidden VM input')
        raw = source.read_bytes()
        if sha256_hex(raw) != sha:
            raise ValueError('frozen VM input changed: ' + name)
        payload[name] = raw
    # Never include credential files; provenance and public app identity are permitted.
    if any('client-secret' in name or 'google-desktop-client.json' in name for name in payload):
        raise ValueError('OAuth client file prohibited')
    from retry_semantics.serialization import canonical_json_bytes
    payload['VM_PACKAGE_SHA256SUMS.json'] = canonical_json_bytes({'files': files,
        'readiness_lock_sha256': deployment['readiness_lock_sha256'],
        'deployment_lock_sha256': sha256_hex(deployment_path.read_bytes()),
        'expected_head': original['git_head'], 'partition': 'GITHUB_VM',
        'github_stored_request_files': 128, 'other_fresh_stored_request_files': 0,
        'credentials_included': False, 'scientific_evaluations': 0})
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            z.writestr(info, raw)
    return {'path': str(output), 'sha256': sha256_hex(output.read_bytes()),
        'payload_files': len(payload), 'github_request_files': len(selected)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('freeze', 'github-package'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--deployment-lock', type=Path)
    a = p.parse_args(argv)
    if a.action == 'freeze':
        value = freeze_deployment(ROOT, a.output)
        print(json.dumps({'deployment_lock_sha256': sha256_hex(a.output.read_bytes()), 'science_changed': False}))
    else:
        if a.deployment_lock is None: p.error('--deployment-lock required')
        print(json.dumps(github_package(ROOT, a.deployment_lock.resolve(), a.output)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
