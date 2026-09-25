"""Prospective read-only paper readiness capture; do not run before audit.

Later invocation requires --execute-read-only, prepared bearer and expiry
metadata, and a new evidence directory. This command performs no OAuth and
no mutation. It captures evidence pending independent audit; it never
qualifies collection.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_http import one_shot_request
from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest
from retry_semantics.study2.sheets_paper_readiness import (
    PaperReadinessError, check_blank_baselines, check_topology, metadata_target,
)

READS_PER_MINUTE = 60  # https://developers.google.com/workspace/sheets/api/limits
READ_INTERVAL_SECONDS = 2.0  # 30/minute, leaving headroom under the standard quota.
REQUEST_CAP_SECONDS = 30.0
LOCAL_ALLOWANCE_SECONDS = 10.0
TOKEN_ALLOWANCE_SECONDS = 60.0
READ_COUNT = 257


def preflight_capture(*, manifest: dict, token_metadata: dict,
                      bearer: str, now: float) -> float:
    """Check the full fixed schedule before any provider dispatch."""
    arms = [arm for family in manifest.get("families", []) for arm in family.get("arms", [])]
    if (len(arms) != 256 or type(token_metadata) is not dict
            or set(token_metadata) != {"schema", "bearer_sha256", "expires_at",
                                        "clock_uncertainty_seconds"}
            or token_metadata["schema"] != "sheets-paper-prepared-token-v1"
            or type(bearer) is not str or not bearer
            or token_metadata["bearer_sha256"] != sha256_hex(bearer.encode())
            or type(now) not in (int, float) or not math.isfinite(now)
            or type(token_metadata["expires_at"]) not in (int, float)
            or not math.isfinite(token_metadata["expires_at"])
            or type(token_metadata["clock_uncertainty_seconds"]) not in (int, float)
            or not math.isfinite(token_metadata["clock_uncertainty_seconds"])
            or token_metadata["clock_uncertainty_seconds"] < 0
            or READ_INTERVAL_SECONDS <= 60 / READS_PER_MINUTE):
        raise PaperReadinessError("readiness capture preflight malformed")
    planned_seconds = ((READ_COUNT - 1) * READ_INTERVAL_SECONDS
                       + REQUEST_CAP_SECONDS + LOCAL_ALLOWANCE_SECONDS
                       + TOKEN_ALLOWANCE_SECONDS)
    if token_metadata["expires_at"] - now <= (
            planned_seconds + token_metadata["clock_uncertainty_seconds"]):
        raise PaperReadinessError("prepared token cannot cover fixed readiness capture")
    return planned_seconds


def run_capture(*, manifest: dict, bearer: str, evidence_dir: Path,
                token_metadata: dict, wall_clock=time.time,
                monotonic=time.monotonic, sleep=time.sleep,
                transport=one_shot_request) -> str:
    """One fixed read schedule. Missed slots or failures stop without retry."""
    planned_seconds = preflight_capture(manifest=manifest, token_metadata=token_metadata,
                                        bearer=bearer, now=wall_clock())
    if evidence_dir.exists():
        raise PaperReadinessError("existing evidence directory")
    evidence_dir.mkdir(mode=0o700, parents=True)
    spreadsheet_id = manifest["spreadsheet_id"]
    arms = [arm for family in manifest["families"] for arm in family["arms"]]
    schedule = [("topology", metadata_target(spreadsheet_id))] + [
        (f"baseline-{index:03d}", arm["read_target"])
        for index, arm in enumerate(arms)]
    (evidence_dir / "capture-plan.json").write_bytes(canonical_json_bytes({
        "schema": "sheets-paper-readiness-capture-plan-v1",
        "manifest_sha256": sha256_hex(canonical_json_bytes(manifest)),
        "spreadsheet_id": spreadsheet_id, "read_count": READ_COUNT,
        "quota_per_minute": READS_PER_MINUTE,
        "interval_seconds": READ_INTERVAL_SECONDS,
        "planned_seconds": planned_seconds,
        "token_expiry": token_metadata["expires_at"],
        "clock_uncertainty_seconds": token_metadata["clock_uncertainty_seconds"]}))
    previous_dispatch_start: float | None = None
    responses = []
    for index, (name, target) in enumerate(schedule):
        if previous_dispatch_start is not None:
            remaining = (
                previous_dispatch_start
                + READ_INTERVAL_SECONDS
                - monotonic()
            )
            if remaining > 0:
                sleep(remaining)
        dispatch_start = monotonic()
        result = transport(method="GET", target=target, body=b"",
                           bearer=bearer, spreadsheet_id=spreadsheet_id,
                           max_response_bytes=1_048_576)
        previous_dispatch_start = dispatch_start
        raw = result.body
        (evidence_dir / f"{name}.response.json").write_bytes(raw)
        (evidence_dir / f"{name}.receipt.json").write_bytes(canonical_json_bytes({
            "schema": "sheets-paper-read-response-receipt-v1", "method": "GET",
            "target": target, "status": result.facts.http_status,
            "transport_error": result.transport_error,
            "dispatch_initiated": result.facts.initiated,
            "local_send_completed": result.facts.local_send_completed,
            "body_sha256": sha256_hex(raw), "spreadsheet_id": spreadsheet_id}))
        if result.facts.http_status != 200 or result.transport_error is not None:
            raise PaperReadinessError(f"incomplete or failed read: {name}")
        responses.append(("GET", target, 200, raw))
        if index == 0:
            check_topology(manifest, 200, raw)
    baselines = {arm["arm_id"]: response for arm, response in zip(arms, responses[1:])}
    check_blank_baselines(manifest, baselines)
    (evidence_dir / "capture-state.json").write_bytes(canonical_json_bytes({
        "schema": "sheets-paper-readiness-capture-state-v1",
        "state": "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT",
        "manifest_sha256": sha256_hex(canonical_json_bytes(manifest)),
        "spreadsheet_id": spreadsheet_id}))
    return "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-read-only", action="store_true", required=True)
    parser.add_argument("--bearer-file", type=Path, required=True)
    parser.add_argument("--prepared-token-metadata", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = load_paper_manifest()
    bearer = args.bearer_file.read_text(encoding="utf-8").strip()
    token_metadata = json.loads(args.prepared_token_metadata.read_bytes())
    state = run_capture(manifest=manifest, bearer=bearer,
                        evidence_dir=args.evidence_dir, token_metadata=token_metadata)
    print(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
