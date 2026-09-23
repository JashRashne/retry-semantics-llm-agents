#!/usr/bin/env python3
"""Prepare or explicitly execute one Phase-3 engineering qualification."""

from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sys

from retry_semantics.study2.razorpay_phase3_replay_visibility import (
    CONFIRMATION, TEST_MODE_CONFIRMATION, QualificationError,
    execute_package, plan_file_sha256, prepare_package, preflight_package,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Razorpay Phase-3 exact replay and bounded visibility gate")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--repository-root", type=Path, required=True)
    prepare.add_argument("--package-dir", type=Path, required=True)
    execute = commands.add_parser("execute")
    execute.add_argument("--repository-root", type=Path, required=True)
    execute.add_argument("--package-dir", type=Path, required=True)
    execute.add_argument("--execute-live-replay-visibility-qualification", action="store_true")
    execute.add_argument("--confirmation", required=True)
    execute.add_argument("--plan-file-sha256", required=True)
    execute.add_argument("--confirm-test-mode-credentials", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            plan = prepare_package(args.repository_root, args.package_dir)
            print(f"PLAN_PATH={args.package_dir.resolve() / 'qualification_plan.json'}")
            print(f"PLAN_FILE_SHA256={plan_file_sha256(args.package_dir)}")
            print(f"PLAN_CANONICAL_SHA256={plan['plan_sha256']}")
            print(f"QUALIFICATION_ID={plan['qualification_id']}")
            print(f"confirmation={CONFIRMATION}")
            print(f"test_mode_confirmation={TEST_MODE_CONFIRMATION}")
            return 0
        if not args.execute_live_replay_visibility_qualification:
            raise QualificationError("live_replay_visibility_flag_required")
        if args.confirmation != CONFIRMATION:
            raise QualificationError("confirmation_mismatch")
        if not args.confirm_test_mode_credentials:
            raise QualificationError("test_mode_operator_confirmation_required")
        preflight_package(args.repository_root, args.package_dir, args.plan_file_sha256)
        key_id = getpass.getpass("Razorpay Test Mode Key ID (hidden): ")
        key_secret = getpass.getpass("Razorpay Test Mode Key Secret (hidden): ")
        outcome = execute_package(
            args.repository_root, args.package_dir,
            execute_live_replay_visibility_qualification=True,
            confirmation=args.confirmation,
            test_mode_operator_confirmation=TEST_MODE_CONFIRMATION,
            plan_file_sha256=args.plan_file_sha256,
            key_id=key_id, key_secret=key_secret,
        )
        print(f"QUALIFICATION_STATUS={outcome.status.value}")
        print(f"QUALIFICATION_REASON={outcome.reason}")
        print(f"MULTIPLICITY_RESULT={outcome.multiplicity_result}")
        print(f"VISIBILITY_RESULT={outcome.visibility_result}")
        return 0 if outcome.status.value == "RESOLVED" else 2
    except QualificationError as error:
        print(f"REFUSED={error.reason}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
