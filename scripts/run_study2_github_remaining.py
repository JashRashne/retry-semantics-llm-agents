"""Prepare/check/run/verify the explicitly authorized remaining GitHub arms."""
import argparse
import json
from pathlib import Path
from retry_semantics.study2 import github_remaining as launch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "run", "verify"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--source-run", type=Path)
    parser.add_argument("--operator-id")
    parser.add_argument("--execute-remaining", action="store_true")
    parser.add_argument("--confirm-exclusive-writer", action="store_true")
    args = parser.parse_args()
    path = args.plan.expanduser().absolute()
    if args.action == "verify":
        print(json.dumps(launch.verify(path.parent / "github-remaining-run"), indent=2))
        return 0
    if args.action == "prepare":
        if not args.source_run or not args.operator_id:
            parser.error("prepare requires --source-run and --operator-id")
        launch.base.validate_run_directory(path)
        launch.base.require_unconsumed(path, launch.CLAIM)
        plan = launch.build_plan(args.source_run, args.operator_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        launch.base.write_once(path, plan)
        print(f"Prepared {path}: 179 remaining, 77 preserved; no API calls.")
        return 0
    launch.check_plan(path)
    launch.base.require_unconsumed(path, launch.CLAIM)
    launch.base.credentials("github")
    if args.action == "check":
        print("PASS: source evidence, unused-arm selection, originals, code and host")
        return 0
    if not args.execute_remaining:
        parser.error("run requires --execute-remaining")
    result = launch.run(path, confirm_exclusive_writer=args.confirm_exclusive_writer)
    print(json.dumps(result, indent=2))
    return 0 if result["state"] == "COMPLETED_SEGMENT" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("Remaining launch refused:", str(exc) if isinstance(exc, launch.base.PaperCollectionError) else type(exc).__name__)
        raise SystemExit(2)
