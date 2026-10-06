"""Offline merge validation; no credentials, provider calls, or result rewriting."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from retry_semantics.baselines.merge_partitions import validate_merge
from retry_semantics.baselines.partitions import build_manifest
from retry_semantics.serialization import sha256_hex
from retry_semantics.baselines.audit_closure import write_json


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bindings', type=Path, required=True)
    p.add_argument('--lock', type=Path, required=True)
    p.add_argument('--lock-sha256', required=True)
    p.add_argument('--deployment-lock', type=Path, required=True)
    p.add_argument('--deployment-lock-sha256', required=True)
    for name in ('tickets-local', 'github-vm', 'sheets-mac'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--report', type=Path, help='Optional NEW validation report; result inputs are never modified')
    a = p.parse_args(argv)
    if sha256_hex(a.lock.read_bytes()) != a.lock_sha256 or sha256_hex(a.deployment_lock.read_bytes()) != a.deployment_lock_sha256:
        raise ValueError('pinned readiness/deployment lock differs')
    lock = json.loads(a.lock.read_bytes()); deployment = json.loads(a.deployment_lock.read_bytes())
    if deployment['readiness_lock_sha256'] != a.lock_sha256:
        raise ValueError('deployment/readiness lock mismatch')
    raw = (a.bindings / 'schedule.json').read_bytes()
    if sha256_hex(raw) != lock['schedule_sha256']:
        raise ValueError('full schedule differs')
    schedule = json.loads(raw)
    result = validate_merge(schedule, build_manifest(schedule),
        {name: getattr(a, name.replace('-', '_')) for name in ('tickets-local', 'github-vm', 'sheets-mac')},
        readiness_lock=lock, readiness_sha256=a.lock_sha256, deployment_sha256=a.deployment_lock_sha256)
    if a.report: write_json(a.report, result)
    print(json.dumps({key: value for key, value in result.items() if key != 'input_sha256'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
