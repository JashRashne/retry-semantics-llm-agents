"""Manual primary collection CLI for Study-2 GitHub Issues.

Enforces:
- Clean, committed git working tree.
- External, non-existent run directory (no resume / write-once).
- Verified readiness locks and audited post-Sheets continuation authorization.
- Explicit --execute-primary flag.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

from retry_semantics.study2.provider_paper_collection import collect_provider_run, validate_run_directory


def _check_clean_git(root: Path) -> None:
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root, capture_output=True, check=True, text=True,
    ).stdout.strip()
    if Path(top).resolve() != root.resolve():
        raise SystemExit("Must be executed from repository root")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--ignore-submodules=all"],
        cwd=root, capture_output=True, check=True, text=True,
    ).stdout.strip()
    if status:
        raise SystemExit(f"Working tree is not clean:\n{status}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-primary", action="store_true", required=True,
                        help="Explicit operator authorization to execute primary paper collection")
    parser.add_argument("--run-dir", type=Path, required=True,
                        help="External target directory for run evidence; must NOT exist")
    parser.add_argument("--github-token", type=str, default=os.environ.get("GITHUB_TOKEN", ""),
                        help="GitHub PAT for paper repository")
    parser.add_argument("--fireworks-api-key", type=str, default=os.environ.get("FIREWORKS_API_KEY", ""),
                        help="Fireworks API key for DeepSeek V4.1 model session")
    parser.add_argument("--api-version", type=str, default="2022-11-28",
                        help="GitHub API version header")

    # Readiness and authorization artifacts
    parser.add_argument("--lock-path", type=Path,
                        default=Path("research/study2/github/GITHUB_PAPER_READINESS_LOCK_V1.json"))
    parser.add_argument("--evidence-dir", type=Path,
                        default=Path("research/study2/github/readiness_control_evidence"))
    parser.add_argument("--audit-receipt-path", type=Path,
                        default=Path("research/study2/github/GITHUB_PAPER_READINESS_AUDIT_RECEIPT_V1.json"))
    parser.add_argument("--audit-report-path", type=Path,
                        default=Path("research/study2/github/GITHUB_PAPER_READINESS_AUDIT_REPORT_V1.json"))

    # Unstarted provider locks
    parser.add_argument("--razorpay-lock-path", type=Path,
                        default=Path("research/study2/razorpay/RAZORPAY_PAPER_READINESS_LOCK_V1.json"))
    # Post-Sheets continuation authorization
    parser.add_argument("--collection-authorization-path", type=Path,
                        default=Path("research/study2/STUDY2_POST_SHEETS_CONTINUATION_AUTHORIZATION_V1.json"))
    parser.add_argument("--collection-audit-receipt-path", type=Path,
                        default=Path("research/study2/STUDY2_POST_SHEETS_CONTINUATION_AUDIT_RECEIPT_V1.json"))
    parser.add_argument("--collection-audit-report-path", type=Path,
                        default=Path("research/study2/STUDY2_POST_SHEETS_CONTINUATION_AUDIT_REPORT_V1.json"))

    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    _check_clean_git(root)

    if not args.github_token:
        raise SystemExit("Missing --github-token or GITHUB_TOKEN environment variable")
    if not args.fireworks_api_key:
        raise SystemExit("Missing --fireworks-api-key or FIREWORKS_API_KEY environment variable")

    try:
        args.run_dir = validate_run_directory(args.run_dir, root=root)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    all_locks = {
        "github": args.lock_path,
        "razorpay": args.razorpay_lock_path,
    }

    print(f"[*] Starting Study-2 GitHub primary collection into {args.run_dir.resolve()}")
    results = collect_provider_run(
        provider="github",
        run_dir=args.run_dir,
        lock_path=args.lock_path,
        evidence_dir=args.evidence_dir,
        audit_receipt_path=args.audit_receipt_path,
        audit_report_path=args.audit_report_path,
        credential=args.github_token,
        model_api_key=args.fireworks_api_key,
        all_provider_readiness_lock_paths=all_locks,
        collection_authorization_path=args.collection_authorization_path,
        collection_audit_receipt_path=args.collection_audit_receipt_path,
        collection_audit_report_path=args.collection_audit_report_path,
        api_version=args.api_version,
    )

    from retry_semantics.study2.provider_paper_analysis import load_run_projections
    from retry_semantics.study2.github_paper_manifest import load_github_paper_manifest
    complete = True
    try:
        load_run_projections(args.run_dir, load_github_paper_manifest().as_json(), "github", expected_families=64)
    except ValueError:
        complete = False
    success_count = sum(1 for r in results if r.status == "SUCCESS")
    failure_count = sum(1 for r in results if r.status == "FAILURE")
    inconclusive_count = sum(1 for r in results if r.status == "INCONCLUSIVE")
    print(f"[+] GitHub primary collection {'COMPLETED' if complete else 'STOPPED/INCOMPLETE'}: {len(results)} arms evaluated")
    print(f"  - SUCCESS: {success_count}")
    print(f"  - FAILURE: {failure_count}")
    print(f"  - INCONCLUSIVE: {inconclusive_count}")
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
