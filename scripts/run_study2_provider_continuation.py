"""Prepare, check, run or verify the operator-reviewed GitHub/Razorpay continuation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from retry_semantics.study2 import provider_operator_launch as launch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "run", "verify"))
    parser.add_argument("--provider", choices=("github", "razorpay"))
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--operator-id", default=os.environ.get("USER", ""))
    parser.add_argument("--execute-continuation", action="store_true")
    parser.add_argument("--confirm-no-external-writers", action="store_true")
    parser.add_argument("--confirm-provider-never-started", action="store_true")
    args = parser.parse_args()
    if args.action == "verify":
        if args.run_dir is None:
            parser.error("verify requires --run-dir")
        print(json.dumps(launch.verify(args.run_dir), indent=2))
        return 0
    if args.action == "prepare":
        if not args.provider or args.state_dir is None:
            parser.error("prepare requires --provider and --state-dir")
        path = args.state_dir.expanduser().resolve() / f"{args.provider}.plan.json"
        launch.validate_run_directory(path)
        launch.require_unconsumed(path, args.provider)
        plan = launch.build_plan(args.provider, args.operator_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        launch.write_once(path, plan)
        print(f"Prepared {path}; no network requests made. Review before execution.")
        return 0
    if args.plan is None:
        parser.error("check/run requires --plan")
    plan = launch.check_plan(args.plan)
    launch.require_unconsumed(args.plan, plan["provider"])
    launch.credentials(plan["provider"])
    if args.action == "check":
        print("PASS: host, code, frozen inputs and credential syntax match; live readiness still required.")
        return 0
    if not args.execute_continuation:
        parser.error("run requires --execute-continuation")
    summary = launch.run(args.plan, confirm_no_external_writers=args.confirm_no_external_writers,
                         confirm_provider_never_started=args.confirm_provider_never_started)
    print(json.dumps(summary, indent=2))
    return 0 if summary["state"] == "COMPLETED" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc) if isinstance(exc, launch.PaperCollectionError) else type(exc).__name__
        print(f"Launch refused/stopped: {reason}. Preserve evidence; do not repeat a consumed launch.")
        raise SystemExit(2)
