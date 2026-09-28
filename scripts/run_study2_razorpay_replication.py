"""Prepare/check/run/verify the once-only paced Razorpay replication."""
import argparse
import json
from pathlib import Path
import uuid

from retry_semantics.study2 import razorpay_paced_replication as replication


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "run", "verify"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--stopped-run", type=Path)
    parser.add_argument("--operator-id")
    parser.add_argument("--execute-replication", action="store_true")
    parser.add_argument("--confirm-no-external-writers", action="store_true")
    args = parser.parse_args()
    path = args.plan.expanduser().absolute()
    if args.action == "verify":
        print(json.dumps(replication.verify(path.parent / "razorpay-run"), indent=2))
        return 0
    if args.action == "prepare":
        if not args.stopped_run or not args.operator_id:
            parser.error("prepare requires --stopped-run and --operator-id")
        replication.base.validate_run_directory(path)
        replication.base.require_unconsumed(path, replication.CLAIM)
        plan = replication.build_plan(uuid.uuid4().hex, args.operator_id, args.stopped_run)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        replication.base.write_once(path, plan)
        print(f"Prepared {path}; original evidence preserved; no network requests made.")
        return 0
    replication.check_plan(path)
    replication.base.require_unconsumed(path, replication.CLAIM)
    replication.base.credentials("razorpay")
    if args.action == "check":
        print("PASS: host/code/namespace/stopped evidence/credentials; live readiness runs only at launch.")
        return 0
    if not args.execute_replication:
        parser.error("run requires --execute-replication")
    summary = replication.run(path, confirm_no_external_writers=args.confirm_no_external_writers,
                              confirm_separate_replication=args.execute_replication)
    print(json.dumps(summary, indent=2))
    return 0 if summary["state"] == "COMPLETED" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc) if isinstance(exc, replication.base.PaperCollectionError) else type(exc).__name__
        print(f"Replication refused/stopped: {reason}. Preserve evidence; do not repeat a consumed launch.")
        raise SystemExit(2)
