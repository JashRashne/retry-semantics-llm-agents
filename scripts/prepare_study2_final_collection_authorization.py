"""Prepare Study-2 cross-provider final collection authorization candidate.

Requires:
1. Valid, canonical readiness locks for all three providers (GitHub, Razorpay, Google Sheets).
2. Exactly 0 Study-2 paper observations across all providers.
3. Exact match with active V4.1 provider static identities.

Emits a candidate authorization artifact for independent audit review without
fabricating an audit PASS or premature collection authorization.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.provider_paper_readiness import (
    ProviderReadinessError,
    _read_canonical,
    _when,
    check_readiness_lock,
    current_static_identity,
    readiness_artifact_paths,
)


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


def prepare_final_authorization(
    *,
    github_lock_path: Path,
    razorpay_lock_path: Path,
    sheets_lock_path: Path,
    output_path: Path | None = None,
    root: Path | None = None,
    now: datetime | None = None,
    authorization_at: datetime | None = None,
) -> tuple[dict[str, Any], str]:
    """Verify all 3 provider locks and prepare canonical cross-provider authorization candidate."""
    lock_paths = {
        "github": github_lock_path,
        "razorpay": razorpay_lock_path,
        "sheets": sheets_lock_path,
    }
    base = root or Path(__file__).resolve().parents[1]
    lock_paths = {name: path if path.is_absolute() else base / path
                  for name, path in lock_paths.items()}

    lock_hashes: dict[str, str] = {}
    locks: dict[str, dict[str, Any]] = {}
    for name, path in lock_paths.items():
        if not path.is_file():
            raise ProviderReadinessError(f"Missing readiness lock for {name}: {path}")
        lock_doc, lock_sha = _read_canonical(path)
        locks[name] = lock_doc
        lock_hashes[name] = lock_sha

    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ProviderReadinessError("authorization preparation time lacks zone")
    # Verify every lock against its original evidence and independent audit.
    identities: dict[str, Any] = {}
    for name, path in lock_paths.items():
        evidence_dir, receipt, report = readiness_artifact_paths(name, path)
        identities[name] = check_readiness_lock(
            name, path, evidence_dir=evidence_dir,
            audit_receipt_path=receipt, audit_report_path=report,
            root=base, now=instant)

    # Verify zero observations
    for name, lock_doc in locks.items():
        obs = lock_doc.get("study2_paper_observations")
        if name != "sheets" and obs != 0:
            raise ProviderReadinessError(f"Provider {name} has non-zero paper observations: {obs}")

    # Gather exact active static identities
    planned = authorization_at or instant + timedelta(days=1)
    if planned.tzinfo is None or planned <= instant:
        raise ProviderReadinessError("planned authorization time must follow preparation")
    instant_iso = planned.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    # Construct authorization document (fail-closed candidate by default)
    auth_doc = {
        "schema": "study2-final-collection-authorization-v1",
        "status": "PENDING_INDEPENDENT_AUDIT",
        "collection_authorized": False,
        "provider_readiness_lock_sha256": lock_hashes,
        "provider_static_identities": identities,
        "authorized_at_utc": instant_iso,
        "study2_paper_observations_at_authorization": 0,
    }

    raw = canonical_json_bytes(auth_doc)
    doc_sha = sha256_hex(raw)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(raw)

    return auth_doc, doc_sha


def final_intent_bytes(candidate: dict[str, Any]) -> bytes:
    """Deterministic bytes for an auditor to review before activation."""
    if (set(candidate) != {"schema", "status", "collection_authorized",
                           "provider_readiness_lock_sha256", "provider_static_identities",
                           "authorized_at_utc", "study2_paper_observations_at_authorization"}
            or candidate["schema"] != "study2-final-collection-authorization-v1"
            or candidate["status"] != "PENDING_INDEPENDENT_AUDIT"
            or candidate["collection_authorized"] is not False
            or candidate["study2_paper_observations_at_authorization"] != 0):
        raise ProviderReadinessError("invalid final authorization candidate")
    final = dict(candidate, status="FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED",
                 collection_authorized=True)
    return canonical_json_bytes(final)


def finalize_final_authorization(*, candidate_path: Path, audit_receipt_path: Path,
                                 audit_report_path: Path, output_path: Path,
                                 now: datetime | None = None,
                                 root: Path | None = None) -> str:
    """Write final bytes only after independent audit binds their exact digest."""
    candidate, _ = _read_canonical(candidate_path)
    root = root or Path(__file__).resolve().parents[1]
    for name in ("github", "razorpay", "sheets"):
        stem = "GOOGLE_SHEETS" if name == "sheets" else name.upper()
        lock_path = root / "research/study2" / name / f"{stem}_PAPER_READINESS_LOCK_V1.json"
        evidence_dir, provider_receipt, provider_report = readiness_artifact_paths(name, lock_path)
        identity = check_readiness_lock(
            name, lock_path, evidence_dir=evidence_dir,
            audit_receipt_path=provider_receipt,
            audit_report_path=provider_report, root=root, now=now)
        if (candidate["provider_static_identities"].get(name) != identity
                or candidate["provider_readiness_lock_sha256"].get(name) !=
                _read_canonical(lock_path)[1]):
            raise ProviderReadinessError("candidate readiness binding changed")
    final_bytes = final_intent_bytes(candidate)
    final_hash = sha256_hex(final_bytes)
    receipt, _ = _read_canonical(audit_receipt_path)
    report, report_hash = _read_canonical(audit_report_path)
    instant = now or datetime.now(timezone.utc)
    if (set(receipt) != {"schema", "authorization_sha256", "audit_report_sha256",
                         "auditor_id", "audited_at_utc"}
            or receipt["schema"] != "study2-final-authorization-audit-receipt-v1"
            or receipt["authorization_sha256"] != final_hash
            or receipt["audit_report_sha256"] != report_hash
            or not receipt["auditor_id"]
            or set(report) != {"schema", "authorization_sha256", "independent_auditor",
                               "result", "findings"}
            or report["schema"] != "study2-final-authorization-audit-report-v1"
            or report["authorization_sha256"] != final_hash
            or report["independent_auditor"] != receipt["auditor_id"]
            or report["result"] != "PASS" or report["findings"] != []
            or not (_when(receipt["audited_at_utc"]) <=
                    _when(candidate["authorized_at_utc"]) <= instant)):
        raise ProviderReadinessError("independent audit does not bind final authorization bytes")
    with output_path.open("xb") as target:
        target.write(final_bytes)
    return final_hash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-lock", type=Path,
                        help="Path to committed github-paper-readiness-lock-v1 JSON")
    parser.add_argument("--razorpay-lock", type=Path,
                        help="Path to committed razorpay-paper-readiness-lock-v1 JSON")
    parser.add_argument("--sheets-lock", type=Path,
                        help="Path to committed sheets-paper-readiness-lock-v1 JSON")
    parser.add_argument("--output", type=Path, default=Path("research/study2/STUDY2_FINAL_COLLECTION_AUTHORIZATION_CANDIDATE_V1.json"),
                        help="Output path for candidate authorization artifact")
    parser.add_argument("--authorization-at-utc", type=str,
                        help="Planned activation time after independent audit (ISO 8601 UTC)")
    parser.add_argument("--finalize", action="store_true",
                        help="Activate an independently audited final intent")
    parser.add_argument("--show-final-intent-sha", action="store_true",
                        help="Print deterministic final byte digest for independent audit")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--audit-receipt", type=Path)
    parser.add_argument("--audit-report", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    _check_clean_git(root)

    if args.show_final_intent_sha:
        if not args.candidate or args.finalize:
            parser.error("--show-final-intent-sha requires --candidate only")
        candidate, _ = _read_canonical(args.candidate)
        print(sha256_hex(final_intent_bytes(candidate)))
        return 0
    if args.finalize:
        if not (args.candidate and args.audit_receipt and args.audit_report):
            parser.error("--finalize requires --candidate, --audit-receipt and --audit-report")
        doc_sha = finalize_final_authorization(
            candidate_path=args.candidate, audit_receipt_path=args.audit_receipt,
            audit_report_path=args.audit_report, output_path=args.output)
        print(doc_sha)
        return 0
    if not (args.github_lock and args.razorpay_lock and args.sheets_lock):
        parser.error("candidate preparation requires all three provider locks")
    planned = _when(args.authorization_at_utc) if args.authorization_at_utc else None
    auth_doc, doc_sha = prepare_final_authorization(
        github_lock_path=args.github_lock,
        razorpay_lock_path=args.razorpay_lock,
        sheets_lock_path=args.sheets_lock,
        output_path=args.output,
        root=root,
        authorization_at=planned,
    )

    print(f"[*] Prepared cross-provider final authorization candidate:")
    print(f"  - SHA-256: {doc_sha}")
    print(f"  - Status: {auth_doc['status']}")
    print(f"  - Collection Authorized: {auth_doc['collection_authorized']}")
    print(f"  - Providers bound: GitHub, Razorpay, Google Sheets")
    print(f"  - Target artifact: {args.output.resolve()}")
    print(f"[!] Requires independent hostile audit before collection authorization can be activated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
