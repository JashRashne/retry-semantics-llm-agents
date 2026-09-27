"""Freeze, check, execute, or verify a separately labelled Sheets replication."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import uuid

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.provider_paper_io import one_shot_http
from retry_semantics.study2.provider_paper_model import live_fireworks_completion
from retry_semantics.study2.provider_paper_collection import PaperCollectionError, validate_run_directory
from retry_semantics.study2.sheets_replication import (
    ROOT, build_plan, check_plan, run_replication, write_once,
)


def verify_run(run_dir: Path) -> dict:
    summary = json.loads((run_dir / 'run-summary.json').read_bytes())
    if summary.get('status') != 'COMPLETED' or summary.get('projected_arms') != 256:
        raise ValueError('Run is stopped or incomplete; preserve it and do not restart/refill')
    inventory = json.loads((run_dir / 'inventory.json').read_bytes())
    actual = {str(p.relative_to(run_dir)): sha256_hex(p.read_bytes())
              for p in sorted(run_dir.rglob('*')) if p.is_file() and p != run_dir / 'inventory.json'}
    if inventory != actual:
        raise ValueError('Evidence file inventory changed')
    from retry_semantics.study2.provider_paper_analysis import load_run_projections
    manifest = json.loads((run_dir / 'manifest.json').read_bytes())
    projections = load_run_projections(run_dir / 'collection', manifest, 'sheets', expected_families=64)
    if len(projections) != 256:
        raise ValueError('Missing arm projections')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'check', 'run', 'verify'])
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--client', type=Path)
    parser.add_argument('--execute-replication', action='store_true')
    parser.add_argument('--confirm-no-external-writers', action='store_true',
                        help='Keep both new spreadsheets private, unedited, and free of scripts/automation')
    args = parser.parse_args(argv)
    if args.action == 'verify':
        if args.run_dir is None:
            parser.error('verify requires --run-dir')
        print(json.dumps(verify_run(args.run_dir), indent=2))
        return 0
    if args.plan is None or not args.plan.is_absolute():
        parser.error('--plan must be an absolute, external path')
    resolved = args.plan.resolve(strict=False)
    if resolved == ROOT or ROOT in resolved.parents or args.plan.is_symlink():
        parser.error('plan must be outside the repository, not a symlink')
    if args.action == 'prepare':
        write_once(args.plan, build_plan(uuid.uuid4().hex))
        print(f'Plan frozen: {args.plan}')
        return 0
    plan = check_plan(args.plan)
    claim = args.plan.with_name(args.plan.name + '.started')
    if claim.exists() or claim.is_symlink():
        parser.error('plan already consumed; no resume, rerun, or refill')
    if args.action == 'check':
        print('PASS: committed code and replication plan match. No network requests made.')
        return 0
    if not (args.execute_replication and args.confirm_no_external_writers
            and args.run_dir is not None and args.client is not None):
        parser.error('run requires --execute-replication, --confirm-no-external-writers, --run-dir, and --client')
    run_dir = validate_run_directory(args.run_dir)
    complete = live_fireworks_completion(os.environ.get('FIREWORKS_API_KEY', ''))
    # Imports reused OAuth and Drive boundaries, without invoking old primary readiness gates.
    import run_sheets_paper_live_readiness_session as oauth
    import run_sheets_paper_append_qualification_session as qualification
    oauth.setup.review_client(args.client)
    write_once(claim, {'plan_sha256': sha256_hex(canonical_json_bytes(plan)),
                       'run_dir': str(run_dir), 'state': 'CONSUMED_NO_RESUME'})

    def access(folder, spreadsheet_id, bearer):
        principal, _, _ = qualification._drive_evidence(
            evidence_dir=folder, paper_id=spreadsheet_id, bearer=bearer,
            drive_get=qualification.drive_get_once)
        return principal

    summary = run_replication(plan=plan, run_dir=run_dir,
        acquire=lambda: oauth.acquire_session_authority(args.client),
        transport=one_shot_http, verify_access=access, model_complete=complete)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Provider/OAuth error text may contain sensitive material. Evidence records types.
        reason = str(exc) if isinstance(exc, PaperCollectionError) else type(exc).__name__
        print(f'Replication refused/stopped: {reason}. Preserve any run evidence; do not repeat a consumed run command.')
        raise SystemExit(2)
