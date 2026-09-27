"""Manual primary collection CLI for Study-2 Google Sheets AppendCells.

Enforces:
- Clean, committed git working tree.
- External, non-existent run directory (no resume / write-once).
- Verified readiness lock and cross-provider collection authorization.
- Valid OAuth bearer token for the audited app/principal.
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
    raise SystemExit("Sheets primary permanently closed after observed run stop")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-primary", action="store_true", required=True,
                        help="Explicit operator authorization to execute primary paper collection")
    parser.add_argument("--run-dir", type=Path, required=True,
                        help="External target directory for run evidence; must NOT exist")
    parser.add_argument("--bearer-token", type=str,
                        default=os.environ.get("GOOGLE_SHEETS_TOKEN", os.environ.get("SHEETS_BEARER_TOKEN", "")),
                        help="Valid Google OAuth bearer token for audited app/principal")
    parser.add_argument("--bearer-file", type=Path,
                        help="Owner-only external bearer file produced by the readiness session")
    parser.add_argument("--fireworks-api-key", type=str, default=os.environ.get("FIREWORKS_API_KEY", ""),
                        help="Fireworks API key for DeepSeek V4.1 model session")

    # Readiness and authorization artifacts
    parser.add_argument("--lock-path", type=Path,
                        default=Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_READINESS_LOCK_V1.json"))
    parser.add_argument("--evidence-dir", type=Path,
                        default=Path("research/study2/sheets/readiness_control_evidence"))
    parser.add_argument("--audit-receipt-path", type=Path,
                        default=Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_READINESS_AUDIT_RECEIPT_V1.json"))
    parser.add_argument("--audit-report-path", type=Path,
                        default=Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_READINESS_AUDIT_REPORT_V1.json"))

    # Cross-provider locks
    parser.add_argument("--github-lock-path", type=Path,
                        default=Path("research/study2/github/GITHUB_PAPER_READINESS_LOCK_V1.json"))
    parser.add_argument("--razorpay-lock-path", type=Path,
                        default=Path("research/study2/razorpay/RAZORPAY_PAPER_READINESS_LOCK_V1.json"))

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

    if args.bearer_file is not None:
        path = args.bearer_file
        resolved = path.resolve(strict=True)
        mode = path.stat().st_mode & 0o777
        if (path.is_symlink() or path.stat().st_uid != os.getuid()
                or resolved == root.resolve()
                or root.resolve() in resolved.parents or mode != 0o600
                or path.stat().st_size > 8192 or args.bearer_token):
            raise SystemExit("Bearer file must be private, external, and exclusive")
        args.bearer_token = path.read_text(encoding="utf-8")

    if not args.bearer_token:
        raise SystemExit("Missing --bearer-token or GOOGLE_SHEETS_TOKEN / SHEETS_BEARER_TOKEN environment variable")
    if not args.fireworks_api_key:
        raise SystemExit("Missing --fireworks-api-key or FIREWORKS_API_KEY environment variable")

    try:
        args.run_dir = validate_run_directory(args.run_dir, root=root)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    all_locks = {
        "github": args.github_lock_path,
        "razorpay": args.razorpay_lock_path,
        "sheets": args.lock_path,
    }

    print(f"[*] Starting Study-2 Google Sheets primary collection into {args.run_dir.resolve()}")
    results = collect_provider_run(
        provider="sheets",
        run_dir=args.run_dir,
        lock_path=args.lock_path,
        evidence_dir=args.evidence_dir,
        audit_receipt_path=args.audit_receipt_path,
        audit_report_path=args.audit_report_path,
        credential=args.bearer_token,
        model_api_key=args.fireworks_api_key,
        all_provider_readiness_lock_paths=all_locks,
        collection_authorization_path=args.collection_authorization_path,
        collection_audit_receipt_path=args.collection_audit_receipt_path,
        collection_audit_report_path=args.collection_audit_report_path,
    )

    success_count = sum(1 for r in results if r.status == "SUCCESS")
    failure_count = sum(1 for r in results if r.status == "FAILURE")
    inconclusive_count = sum(1 for r in results if r.status == "INCONCLUSIVE")
    print(f"[+] Google Sheets primary collection completed: {len(results)} arms evaluated")
    print(f"  - SUCCESS: {success_count}")
    print(f"  - FAILURE: {failure_count}")
    print(f"  - INCONCLUSIVE: {inconclusive_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
