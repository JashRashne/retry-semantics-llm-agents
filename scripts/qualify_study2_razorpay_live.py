#!/usr/bin/env python3
"""Operator CLI for the two-stage Razorpay engineering qualification gate."""

from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sys

from retry_semantics.study2.razorpay_live_qualification import (
    CONFIRMATION,
    TEST_MODE_CONFIRMATION,
    QualificationError,
    execute_package,
    plan_file_sha256,
    prepare_package,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or execute one Razorpay Test Mode engineering qualification"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--repository-root", type=Path, required=True)
    prepare.add_argument("--package-dir", type=Path, required=True)

    execute = commands.add_parser("execute")
    execute.add_argument("--repository-root", type=Path, required=True)
    execute.add_argument("--package-dir", type=Path, required=True)
    execute.add_argument("--execute-live-qualification", action="store_true")
    execute.add_argument("--confirmation", required=True)
    execute.add_argument("--plan-file-sha256", required=True)
    execute.add_argument("--confirm-test-mode-credentials", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            plan = prepare_package(args.repository_root, args.package_dir)
            plan_path = (args.package_dir.resolve() / "qualification_plan.json")
            print(f"PLAN_PATH={plan_path}")
            print(f"PLAN_FILE_SHA256={plan_file_sha256(args.package_dir)}")
            print(f"PLAN_CANONICAL_SHA256={plan['plan_sha256']}")
            print(f"QUALIFICATION_ID={plan['qualification_id']}")
            print(f"confirmation={CONFIRMATION}")
            print(f"test_mode_confirmation={TEST_MODE_CONFIRMATION}")
            return 0

        if not args.execute_live_qualification:
            raise QualificationError("live_execution_flag_required")
        if args.confirmation != CONFIRMATION:
            raise QualificationError("confirmation_mismatch")
        if not args.confirm_test_mode_credentials:
            raise QualificationError("test_mode_operator_confirmation_required")

        # Both credential components are read from a hidden terminal prompt.
        # Neither is accepted from argv, environment, files, or package JSON.
        key_id = getpass.getpass("Razorpay Test Mode Key ID (hidden): ")
        key_secret = getpass.getpass("Razorpay Test Mode Key Secret (hidden): ")
        outcome = execute_package(
            args.repository_root,
            args.package_dir,
            execute_live_qualification=True,
            confirmation=args.confirmation,
            test_mode_operator_confirmation=TEST_MODE_CONFIRMATION,
            plan_file_sha256=args.plan_file_sha256,
            key_id=key_id,
            key_secret=key_secret,
        )
        print(f"QUALIFICATION_STATUS={outcome.status.value}")
        print(f"QUALIFICATION_REASON={outcome.reason}")
        return 0 if outcome.status.value == "PASS" else 2
    except QualificationError as error:
        print(f"REFUSED={error.reason}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
