#!/usr/bin/env python3
"""Run the separate, one-shot V4.1 Study1B paper replication."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from retry_semantics.experiment.fireworks_paper_study1b import build_study1b_manifest
from retry_semantics.experiment.paper import EVIDENCE_V2, run_paper_collection
from retry_semantics.experiment.trace import TraceRunMetadata
from retry_semantics.models import FireworksModelClient

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = Path.home() / "Library/Application Support/RetrySemantics/study1b-v41-primary"


def main() -> int:
    if not os.environ.get("FIREWORKS_API_KEY"):
        raise SystemExit("FIREWORKS_API_KEY is required")
    if RUN_DIR.exists() or RUN_DIR.with_name(f".{RUN_DIR.name}.in-progress").exists():
        raise SystemExit("Study1B primary run already exists or was interrupted; no resume/refill")
    if RUN_DIR == REPOSITORY_ROOT or REPOSITORY_ROOT in RUN_DIR.parents:
        raise SystemExit("Study1B evidence must be outside the repository")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=REPOSITORY_ROOT, check=True, capture_output=True, text=True,
    ).stdout
    if dirty:
        raise SystemExit("Study1B requires a clean, audited commit before collection")
    metadata = TraceRunMetadata(
        git_commit=commit,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    RUN_DIR.parent.mkdir(parents=True, exist_ok=True)
    client = FireworksModelClient()
    try:
        run_paper_collection(
            manifest=build_study1b_manifest(), client=client,
            run_root=RUN_DIR, metadata=metadata, evidence_revision=EVIDENCE_V2,
        )
    finally:
        client.close()
    print(f"Study1B evidence: {RUN_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
