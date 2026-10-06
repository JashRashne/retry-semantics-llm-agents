"""Offline structural validation of three immutable partition result directories."""
from __future__ import annotations
import json
from pathlib import Path
from retry_semantics.baselines.partitions import PARTITIONS, build_manifest, selected_entries
from retry_semantics.serialization import sha256_hex


def validate_merge(schedule, manifest, directories, *, readiness_lock, readiness_sha256, deployment_sha256):
    if set(directories) != set(PARTITIONS) or manifest != build_manifest(schedule):
        raise ValueError('exactly the three frozen partitions required')
    if len({Path(p).resolve() for p in directories.values()}) != 3:
        raise ValueError('partition result directories must be distinct')
    identities = {}; counts = {}; seen = set()
    for partition, folder in directories.items():
        folder = Path(folder)
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError('nonregular result directory')
        def read(path):
            if path.is_symlink() or not path.is_file():
                raise ValueError('missing or nonregular result evidence: ' + str(path))
            raw = path.read_bytes()
            identities[str(path)] = sha256_hex(raw)
            return json.loads(raw)
        expected = selected_entries(schedule, manifest, partition)
        opportunities = read(folder / 'scheduled_opportunities.json')
        if opportunities != expected:
            raise ValueError('missing/duplicate/wrong-partition frozen opportunities')
        metadata = manifest['partitions'][partition]
        provenance = read(folder / 'deployment_provenance.json')
        if (provenance['execution_partition'] != metadata['partition_name']
                or provenance['declared_machine_role'] != metadata['machine_role']
                or provenance['readiness_lock_sha256'] != readiness_sha256
                or provenance['deployment_lock_sha256'] != deployment_sha256
                or provenance['schedule_sha256'] != readiness_lock['schedule_sha256']
                or provenance['partition_schedule_sha256'] != metadata['partition_schedule_sha256']
                or provenance['git_head'] != readiness_lock['git_head']
                or provenance['dependency_versions'] != readiness_lock['runtime_dependency_versions']):
            raise ValueError('wrong-partition/machine/runtime provenance')
        result_paths = sorted(folder.glob('*/result.json'))
        if len(result_paths) != len(expected):
            raise ValueError('missing/extra result; UNRUN must be explicit in its owning partition')
        by_index = {entry['schedule_index']: entry for entry in expected}
        for path in result_paths:
            if path.parent.is_symlink():
                raise ValueError('symlink arm directory')
            record = read(path)
            index = record['schedule_index']
            if index in seen:
                raise ValueError('duplicate global schedule_index')
            if index not in by_index or path.parent.name != f'{index:03d}':
                raise ValueError('result migrated outside owning partition')
            entry = by_index[index]
            for key in ('source_set', 'source_family_id', 'source_original_identity',
                        'baseline_arm_id', 'semantic_target_sha256', 'stored_request_identity_sha256', 'hidden_world'):
                if record.get(key) != entry[key]:
                    raise ValueError('source/request binding mismatch: ' + key)
            if record.get('execution_partition') != metadata['partition_name']:
                raise ValueError('wrong-partition result')
            if record.get('model_call_count') != 0:
                raise ValueError('nonzero model capability/result')
            if record.get('opportunity_status') == 'UNRUN' and any(
                    record.get(k) for k in ('list_attempted', 'recovery_create_attempted', 'read_count', 'write_count')):
                raise ValueError('UNRUN contains recovery actions')
            seen.add(index)
        summary = read(folder / 'run_summary.json')
        if summary['scheduled'] != len(expected) or summary['records'] != len(expected) or summary['execution_partition'] != metadata['partition_name']:
            raise ValueError('partition summary count/name mismatch')
        counts[metadata['partition_name']] = len(expected)
    if seen != {entry['schedule_index'] for entry in schedule}:
        raise ValueError('missing global opportunity; no implicit missing results')
    return {'status': 'OFFLINE_PARTITION_UNION_VALIDATED', 'counts': counts,
        'global_schedule_indices': sorted(seen), 'union': len(seen), 'duplicates': 0,
        'input_sha256': identities, 'provider_calls': 0, 'results_modified': False}
