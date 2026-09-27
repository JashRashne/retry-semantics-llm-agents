"""Prepare a GitHub or Razorpay readiness lock from independently audited bytes.

This offline command does not create audit evidence. The ordinary committed
readiness verifier is reused with only its commit check deferred until review.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.provider_paper_readiness import (
    PROVIDER_CONTROLS, ROOT, ProviderReadinessError, _read_canonical,
    check_readiness_lock, current_static_identity, readiness_artifact_paths,
)
from retry_semantics.study2.github_paper_manifest import load_github_paper_manifest
from retry_semantics.study2.razorpay_paper_manifest import load_razorpay_paper_manifest


def prepare_lock(provider: str, *, root: Path = ROOT,
                 now: datetime | None = None) -> bytes:
    if provider not in ("github", "razorpay"):
        raise ProviderReadinessError("provider must be github or razorpay")
    now = now or datetime.now(timezone.utc)
    identity = current_static_identity(provider, root=root)
    manifest = (load_github_paper_manifest(root).as_json() if provider == "github"
                else load_razorpay_paper_manifest(root))
    if (manifest.get("study2_paper_observations") != 0
            or manifest.get("collection_status") != "BLOCKED"):
        raise ProviderReadinessError("provider is not blocked pre-data")
    target = root / "research" / "study2" / provider / (
        f"{provider.upper()}_PAPER_READINESS_LOCK_V1.json")
    evidence_dir, receipt_path, report_path = readiness_artifact_paths(provider, target)
    hashes = {control: _read_canonical(evidence_dir / f"{control}.json")[1]
              for control in PROVIDER_CONTROLS[provider]}
    receipt, receipt_hash = _read_canonical(receipt_path)
    _read_canonical(report_path)
    if (receipt.get("static_identity") != identity
            or receipt.get("live_evidence_sha256") != hashes):
        raise ProviderReadinessError("independent audit does not bind current evidence")
    raw = canonical_json_bytes({
        "schema": f"{provider}-paper-readiness-lock-v1",
        "static_identity": identity,
        "live_evidence_sha256": hashes,
        "independent_audit_receipt_sha256": receipt_hash,
        "study2_paper_observations": 0,
        "collection_authorized": False,
    })
    # Validate the exact candidate with the normal verifier before writing to
    # the canonical path. Only the eventual commit check is deferred.
    with tempfile.TemporaryDirectory() as temporary:
        candidate = Path(temporary) / target.name
        candidate.write_bytes(raw)
        check_readiness_lock(provider, candidate, evidence_dir=evidence_dir,
                             audit_receipt_path=receipt_path,
                             audit_report_path=report_path, root=root, now=now,
                             _candidate_uncommitted=True)
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=("github", "razorpay"))
    parser.add_argument("--prepare-lock-offline", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        raw = prepare_lock(args.provider)
        target = ROOT / "research" / "study2" / args.provider / (
            f"{args.provider.upper()}_PAPER_READINESS_LOCK_V1.json")
        with target.open("xb") as output:
            output.write(raw)
        print(sha256_hex(raw))
        return 0
    except Exception as exc:
        print(f"Readiness lock refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
