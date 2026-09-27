"""Prepare or finalize offline Study-2 GitHub/Razorpay continuation authorization.

The incident amendment, its independent audit, and refreshed provider readiness
must be committed before preparation. Finalization additionally requires an
independent audit of the exact final authorization bytes.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.post_sheets_continuation import (
    AUTHORIZATION, ROOT, _path, continuation_intent_bytes, prepare_continuation,
)
from retry_semantics.study2.provider_paper_readiness import (
    ProviderReadinessError, _read_canonical, _when,
)

LOCKS = {
    name: Path(f"research/study2/{name}/{name.upper()}_PAPER_READINESS_LOCK_V1.json")
    for name in ("github", "razorpay")
}


def finalize_continuation(*, candidate_path: Path, receipt_path: Path,
                          report_path: Path, output_path: Path = ROOT / AUTHORIZATION,
                          root: Path = ROOT, now: datetime | None = None) -> str:
    instant = now or datetime.now(timezone.utc)
    candidate, _ = _read_canonical(_path(root, candidate_path))
    planned = _when(candidate["authorized_at_utc"])
    expected, _ = prepare_continuation(
        readiness_lock_paths=LOCKS, authorization_at=planned, root=root, now=instant)
    if candidate != expected:
        raise ProviderReadinessError("continuation candidate binding changed")
    final_bytes = continuation_intent_bytes(candidate)
    digest = sha256_hex(final_bytes)
    receipt, _ = _read_canonical(_path(root, receipt_path))
    report, report_sha = _read_canonical(_path(root, report_path))
    if (set(receipt) != {"schema", "authorization_sha256", "audit_report_sha256",
                         "auditor_id", "audited_at_utc"}
            or receipt["schema"] != "study2-post-sheets-continuation-audit-receipt-v1"
            or receipt["authorization_sha256"] != digest
            or receipt["audit_report_sha256"] != report_sha
            or type(receipt["auditor_id"]) is not str or not receipt["auditor_id"]
            or set(report) != {"schema", "authorization_sha256", "independent_auditor",
                               "result", "findings"}
            or report["schema"] != "study2-post-sheets-continuation-audit-report-v1"
            or report["authorization_sha256"] != digest
            or report["independent_auditor"] != receipt["auditor_id"]
            or report["result"] != "PASS" or report["findings"] != []
            or not (_when(receipt["audited_at_utc"]) <= instant < planned)):
        raise ProviderReadinessError("continuation independent audit missing")
    target = _path(root, output_path)
    if target != root / AUTHORIZATION:
        raise ProviderReadinessError("continuation output path differs")
    with target.open("xb") as stream:
        stream.write(final_bytes)
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization-at-utc", help="Future activation time, UTC")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--audit-receipt", type=Path)
    parser.add_argument("--audit-report", type=Path)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--output", type=Path,
                        help="Write-once candidate path; use an external absolute path")
    args = parser.parse_args()
    if args.finalize:
        if not (args.candidate and args.audit_receipt and args.audit_report):
            parser.error("finalize requires candidate, audit receipt, and audit report")
        print(finalize_continuation(candidate_path=args.candidate,
                                    receipt_path=args.audit_receipt,
                                    report_path=args.audit_report))
    else:
        if not args.authorization_at_utc:
            parser.error("preparation requires --authorization-at-utc")
        if args.output is None or not args.output.is_absolute():
            parser.error("preparation requires an external absolute --output path")
        if args.output.resolve(strict=False) == ROOT or ROOT in args.output.resolve(strict=False).parents:
            parser.error("candidate --output must be outside the repository")
        doc, digest = prepare_continuation(
            readiness_lock_paths=LOCKS, authorization_at=_when(args.authorization_at_utc))
        target = args.output
        with target.open("xb") as stream:
            stream.write(canonical_json_bytes(doc))
        print(digest)
        print(sha256_hex(continuation_intent_bytes(doc)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
