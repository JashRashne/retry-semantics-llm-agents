"""Deployment partitions only: never observe providers or invoke recovery."""
from __future__ import annotations
import json
import os
import platform
import socket
import sys
from pathlib import Path
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.baselines.audit_closure import write_json

PARTITIONS = {
    'tickets-local': ('TICKETS_LOCAL', ('Study 1A', 'Study 1B'), 640, 'MAC_OFFLINE'),
    'github-vm': ('GITHUB_VM', ('GitHub',), 128, 'VM_GITHUB_ONLY'),
    'sheets-mac': ('SHEETS_MAC', ('Sheets',), 128, 'MAC_SHEETS_ONLY'),
}
CLAIMS = {key: 'COLLECTION_CONSUMED_' + value[0] + '.json' for key, value in PARTITIONS.items()}


def spec(partition):
    if partition not in PARTITIONS:
        raise ValueError('exactly one valid execution partition required; no all mode')
    return PARTITIONS[partition]


def assert_entry(partition, entry):
    if entry['source_set'] not in spec(partition)[1]:
        raise ValueError('entry outside selected partition')


def build_manifest(schedule):
    if len(schedule) != 896 or [e['schedule_index'] for e in schedule] != list(range(896)):
        raise ValueError('complete original 896-entry schedule required')
    groups = {}
    union = set()
    for key, (name, source_sets, expected, machine_role) in PARTITIONS.items():
        entries = [e for e in schedule if e['source_set'] in source_sets]
        indices = [e['schedule_index'] for e in entries]
        if len(entries) != expected or union.intersection(indices):
            raise ValueError('partition count/overlap mismatch')
        union.update(indices)
        groups[key] = {'partition_name': name, 'machine_role': machine_role,
            'source_sets': list(source_sets), 'expected_arm_count': expected,
            'global_schedule_indices': indices,
            'partition_schedule_sha256': sha256_hex(canonical_json_bytes(entries)),
            'claim_file': CLAIMS[key]}
    if union != set(range(896)):
        raise ValueError('partition union differs from frozen schedule')
    return {'schema': 'no-model-split-deployment-v1',
        'schedule_sha256': sha256_hex(canonical_json_bytes(schedule)),
        'partitions': groups, 'union_arm_count': 896, 'pairwise_intersections': 0}


def selected_entries(schedule, manifest, partition):
    spec(partition)
    if manifest != build_manifest(schedule):
        raise ValueError('partition manifest differs from original schedule')
    indices = manifest['partitions'][partition]['global_schedule_indices']
    entries = [e for e in schedule if e['schedule_index'] in set(indices)]
    for entry in entries:
        assert_entry(partition, entry)
    return entries


def claim_partition(binding_dir, partition, *, output, readiness_sha256, deployment_sha256):
    path = binding_dir / CLAIMS[partition]
    if path.exists() or path.is_symlink():
        raise ValueError('partition already consumed; no resume/refill/replacement')
    # Exclusive create is the final guard against simultaneous launchers.
    value = {'execution_partition': spec(partition)[0],
        'output': str(output), 'readiness_lock_sha256': readiness_sha256,
        'deployment_lock_sha256': deployment_sha256, 'authorization_explicit': True,
        'one_use_no_resume_no_refill': True}
    with path.open('xb') as stream:
        stream.write(canonical_json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    directory_fd = os.open(binding_dir, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return path


def provenance(partition):
    return {'execution_partition': spec(partition)[0], 'declared_machine_role': spec(partition)[3],
        'hostname_record_only': socket.gethostname(), 'platform': platform.platform(),
        'python_version': platform.python_version(), 'python_executable': sys.executable,
        'hostname_used_for_partition_selection': False}


def runtime_expectations(root, readiness_lock, readiness_sha256, deployment_path, deployment_sha256):
    """Strict hash-chain upgrade of exactly the two deployment files, no science."""
    def digest(path):
        if path.is_symlink():
            raise ValueError('symlink deployment input')
        return sha256_hex(path.read_bytes())
    if deployment_path is None or digest(deployment_path) != deployment_sha256:
        raise ValueError('pinned deployment lock required')
    upgrade = json.loads(deployment_path.read_bytes())
    if upgrade['readiness_lock_sha256'] != readiness_sha256:
        raise ValueError('deployment lock does not bind original readiness lock')
    allowed = {'scripts/collect_no_model_baseline.py', 'src/retry_semantics/baselines/collection.py'}
    if set(upgrade['replacements']) != allowed:
        raise ValueError('deployment upgrade may replace only launcher/collection deployment guards')
    expected = dict(readiness_lock['runtime_files'])
    for name, replacement in upgrade['replacements'].items():
        if replacement['previous_sha256'] != expected[name] or digest(root / replacement['previous_file']) != expected[name]:
            raise ValueError('original audited runtime identity not preserved')
        expected[name] = replacement['current_sha256']
    for name, sha in upgrade['deployment_runtime_files'].items():
        if name in expected:
            raise ValueError('new deployment files cannot override accepted runtime')
        if digest(root / name) != sha:
            raise ValueError('deployment runtime/protocol identity differs: ' + name)
    for name, sha in expected.items():
        if digest(root / name) != sha:
            raise ValueError('accepted runtime identity differs: ' + name)
    expected.update(upgrade['deployment_runtime_files'])
    manifest_path = root / upgrade['partition_manifest_file']
    if digest(manifest_path) != upgrade['partition_manifest_sha256']:
        raise ValueError('partition manifest identity differs')
    return expected, json.loads(manifest_path.read_bytes()), upgrade
