"""Manual primary collection CLI for Study-2 Razorpay Orders.

Enforces:
- Clean, committed git working tree.
- External, non-existent run directory (no resume / write-once).
- Verified readiness lock and cross-provider collection authorization.
- Valid Test Mode scope credentials matching audited manifest.
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
    parser.add_argument("--razorpay-key-id", type=str, default=os.environ.get("RAZORPAY_KEY_ID", ""),
                        help="Razorpay Test Mode Key ID (rzp_test_...)")
    parser.add_argument("--razorpay-key-secret", type=str, default=os.environ.get("RAZORPAY_KEY_SECRET", ""),
                        help="Razorpay Test Mode Key Secret")
    parser.add_argument("--fireworks-api-key", type=str, default=os.environ.get("FIREWORKS_API_KEY", ""),
                        help="Fireworks API key for DeepSeek V4.1 model session")

    # Readiness and authorization artifacts
    parser.add_argument("--lock-path", type=Path,
                        default=Path("research/study2/razorpay/RAZORPAY_PAPER_READINESS_LOCK_V1.json"))
    parser.add_argument("--evidence-dir", type=Path,
                        default=Path("research/study2/razorpay/readiness_control_evidence"))
    parser.add_argument("--audit-receipt-path", type=Path,
                        default=Path("research/study2/razorpay/RAZORPAY_PAPER_READINESS_AUDIT_RECEIPT_V1.json"))
    parser.add_argument("--audit-report-path", type=Path,
                        default=Path("research/study2/razorpay/RAZORPAY_PAPER_READINESS_AUDIT_REPORT_V1.json"))

    # Cross-provider locks
    parser.add_argument("--github-lock-path", type=Path,
                        default=Path("research/study2/github/GITHUB_PAPER_READINESS_LOCK_V1.json"))
    parser.add_argument("--sheets-lock-path", type=Path,
                        default=Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_READINESS_LOCK_V1.json"))

    # Cross-provider authorization
    parser.add_argument("--collection-authorization-path", type=Path,
                        default=Path("research/study2/STUDY2_FINAL_COLLECTION_AUTHORIZATION_V1.json"))
    parser.add_argument("--collection-audit-receipt-path", type=Path,
                        default=Path("research/study2/STUDY2_FINAL_AUTHORIZATION_AUDIT_RECEIPT_V1.json"))
    parser.add_argument("--collection-audit-report-path", type=Path,
                        default=Path("research/study2/STUDY2_FINAL_AUTHORIZATION_AUDIT_REPORT_V1.json"))

    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    _check_clean_git(root)

    if not args.razorpay_key_id or not args.razorpay_key_secret:
        raise SystemExit("Missing --razorpay-key-id and --razorpay-key-secret (or RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET env vars)")
    if not args.fireworks_api_key:
        raise SystemExit("Missing --fireworks-api-key or FIREWORKS_API_KEY environment variable")

    try:
        args.run_dir = validate_run_directory(args.run_dir, root=root)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    credential = f"{args.razorpay_key_id}:{args.razorpay_key_secret}"
    all_locks = {
        "github": args.github_lock_path,
        "razorpay": args.lock_path,
        "sheets": args.sheets_lock_path,
    }

    print(f"[*] Starting Study-2 Razorpay primary collection into {args.run_dir.resolve()}")
    results = collect_provider_run(
        provider="razorpay",
        run_dir=args.run_dir,
        lock_path=args.lock_path,
        evidence_dir=args.evidence_dir,
        audit_receipt_path=args.audit_receipt_path,
        audit_report_path=args.audit_report_path,
        credential=credential,
        model_api_key=args.fireworks_api_key,
        all_provider_readiness_lock_paths=all_locks,
        collection_authorization_path=args.collection_authorization_path,
        collection_audit_receipt_path=args.collection_audit_receipt_path,
        collection_audit_report_path=args.collection_audit_report_path,
    )

    success_count = sum(1 for r in results if r.status == "SUCCESS")
    failure_count = sum(1 for r in results if r.status == "FAILURE")
    inconclusive_count = sum(1 for r in results if r.status == "INCONCLUSIVE")
    print(f"[+] Razorpay primary collection completed: {len(results)} arms evaluated")
    print(f"  - SUCCESS: {success_count}")
    print(f"  - FAILURE: {failure_count}")
    print(f"  - INCONCLUSIVE: {inconclusive_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
