"""Read-only partition verification or explicitly authorized one-partition collection."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from retry_semantics.baselines.collection import CollectionRefused, require_authorization, verified_package, run_serial
from retry_semantics.baselines.partitions import PARTITIONS, CLAIMS, selected_entries, claim_partition, provenance
from retry_semantics.baselines.audit_closure import write_json


class SinglePartition(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest) is not None:
            parser.error('exactly one --partition may be supplied')
        setattr(namespace, self.dest, values)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'collect'))
    parser.add_argument('--partition', choices=tuple(PARTITIONS), action=SinglePartition)
    parser.add_argument('--bindings', type=Path, required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--lock-sha256', required=True)
    parser.add_argument('--deployment-lock', type=Path)
    parser.add_argument('--deployment-lock-sha256')
    parser.add_argument('--authorization')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--client', type=Path,
        default=Path('/Users/jashrashne/Library/Application Support/RetrySemantics/oauth-client/google-desktop-client.json'))
    args = parser.parse_args(argv)
    if args.action == 'collect':
        require_authorization(args.authorization)  # FIRST: before file/credential/provider work
        if args.output is None:
            parser.error('collect requires a fresh --output directory')
    if args.partition is None or args.deployment_lock is None or args.deployment_lock_sha256 is None:
        parser.error('verify/collect require exactly one --partition and pinned --deployment-lock/--deployment-lock-sha256')
    package = verified_package(args.bindings.resolve(), args.lock.resolve(), args.lock_sha256, root=ROOT,
        partition=args.partition, deployment_path=args.deployment_lock.resolve(),
        deployment_sha256=args.deployment_lock_sha256)
    entries = selected_entries(package['schedule'], package['partition_manifest'], args.partition)
    partition = package['partition_manifest']['partitions'][args.partition]
    claim = package['binding_dir'] / CLAIMS[args.partition]
    consumed = claim.exists() or claim.is_symlink()
    if args.action == 'verify':
        print(json.dumps({'mode': 'READ_ONLY_NO_COLLECTION', 'partition': partition['partition_name'],
            'expected_arm_count': partition['expected_arm_count'], 'actual_arm_count': len(entries),
            'global_schedule_indices': [e['schedule_index'] for e in entries], 'consumed': consumed,
            'scientific_evaluations': None if consumed else 0, 'scientific_evaluations_this_verify': 0,
            'scientific_mutations_this_verify': 0, 'complete_schedule_arms': 896}))
        return 0
    if consumed:
        raise CollectionRefused('partition already consumed; no resume/refill/replacement')
    # A legacy global claim is ambiguous deployment evidence: refuse, never clear it.
    legacy = package['binding_dir'] / 'COLLECTION_CONSUMED.json'
    if legacy.exists() or legacy.is_symlink():
        raise CollectionRefused('legacy global consumption evidence requires review')
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if head != package['lock']['git_head']:
        raise CollectionRefused('repository HEAD differs from readiness lock')
    from retry_semantics.study2.sheets_phase3_control import environment_gate
    environment_gate()  # unchanged, before any arm; no automatic stripping
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or args.output.is_symlink() or output.exists():
        raise CollectionRefused('collection output must be fresh and outside repository')
    try:
        claim_partition(package['binding_dir'], args.partition, output=output,
            readiness_sha256=args.lock_sha256, deployment_sha256=args.deployment_lock_sha256)
    except (ValueError, FileExistsError) as exc:
        raise CollectionRefused(str(exc)) from exc
    from retry_semantics.baselines.partition_runtime import executor_for
    executor = executor_for(package, output, args.client)
    machine = dict(provenance(args.partition),
        readiness_lock_sha256=args.lock_sha256, deployment_lock_sha256=args.deployment_lock_sha256,
        schedule_sha256=package['lock']['schedule_sha256'],
        partition_schedule_sha256=partition['partition_schedule_sha256'], git_head=head,
        dependency_versions=package['lock']['runtime_dependency_versions'],
        runtime_files=package['execution_runtime_files'])
    result = run_serial(entries, output, executor, partition=args.partition,
        deployment_provenance=machine)
    print(json.dumps(dict(result, partition=partition['partition_name'])))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except CollectionRefused as exc:
        print('Collection refused: ' + str(exc), file=sys.stderr)
        raise SystemExit(2)
