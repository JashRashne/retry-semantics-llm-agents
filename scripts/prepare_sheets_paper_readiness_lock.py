"""Offline final Sheets readiness-lock materializer; requires a later independent audit.

No OAuth, provider request, model call, or mutation exists here. The candidate
lock still requires independent review and a committed clean checkout before
the frozen qualify_readiness gate can accept it.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_materialize import (
    IMPLEMENTATION_PATHS, MANIFEST_PATH, REPOSITORY_ROOT, load_paper_manifest,
)
from retry_semantics.study2.sheets_paper_readiness import (
    READINESS_LOCK_PATH, PaperReadinessError, _durable_json,
    check_readiness_structure, readiness_requirements,
)

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import materialize_sheets_paper_readiness_controls as controls


class LockPreparationRefused(ValueError):
    """The current evidence is not sufficient for a readiness-lock candidate."""


def _git(*args: str, root: Path = REPOSITORY_ROOT) -> bytes:
    return subprocess.run(["git", "-c", "core.fsmonitor=false",
                           "-c", "core.untrackedCache=false", *args],
                          cwd=root, capture_output=True, check=True).stdout


def require_clean_committed_inputs(root: Path = REPOSITORY_ROOT) -> None:
    """Check reviewed input bytes before creating the as-yet-uncommitted lock."""
    try:
        if (Path(_git("rev-parse", "--show-toplevel", root=root).decode().strip()).resolve()
                != root.resolve()
                or _git("status", "--porcelain", "--ignore-submodules=all", root=root).strip()):
            raise LockPreparationRefused("input checkout is not clean and committed")
        for relative in (MANIFEST_PATH, *IMPLEMENTATION_PATHS):
            path = root / relative
            if path.is_symlink() or path.read_bytes() != _git("show", "HEAD:" + str(relative), root=root):
                raise LockPreparationRefused("manifest or implementation differs from HEAD")
        for name in readiness_requirements():
            relative = controls.OUTPUT_DIR / f"{name}.json"
            path = root / relative
            if path.is_symlink() or path.read_bytes() != _git("show", "HEAD:" + str(relative), root=root):
                raise LockPreparationRefused("control evidence differs from HEAD")
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        raise LockPreparationRefused("committed input check failed") from exc


def _validate_refs(value: object) -> None:
    if type(value) is dict:
        if set(value) == {"path", "sha256"}:
            path = Path(value["path"])
            if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                    or sha256_hex(path.read_bytes()) != value["sha256"]):
                raise LockPreparationRefused("control source byte hash differs")
        else:
            for child in value.values():
                _validate_refs(child)
    elif type(value) is list:
        for child in value:
            _validate_refs(child)


def require_independent_audit(receipt_path: Path, *, subject: dict,
                              control_sha256: dict[str, str],
                              topology_sha256: str,
                              baseline_sha256: dict[str, str]) -> tuple[dict, str]:
    """A separately supplied canonical receipt and actual report bytes are mandatory."""
    try:
        receipt, digest = _durable_json(receipt_path)
    except PaperReadinessError as exc:
        raise LockPreparationRefused("independent audit receipt missing or malformed") from exc
    audit = receipt.get("independent_audit")
    if (set(receipt) != {"schema", "subject", "independent_audit",
                        "control_sha256", "topology_sha256", "baseline_sha256"}
            or receipt["schema"] != "sheets-paper-readiness-audit-receipt-v1"
            or receipt["subject"] != subject
            or receipt["control_sha256"] != control_sha256
            or receipt["topology_sha256"] != topology_sha256
            or receipt["baseline_sha256"] != baseline_sha256
            or type(audit) is not dict
            or set(audit) != {"auditor_id", "audit_report_sha256",
                              "audit_report_file", "audited_at_utc"}
            or type(audit["auditor_id"]) is not str or not audit["auditor_id"]
            or type(audit["audited_at_utc"]) is not str or not audit["audited_at_utc"]
            or type(audit["audit_report_file"]) is not str
            or re.fullmatch(r"[A-Za-z0-9_.-]+", audit["audit_report_file"]) is None
            or audit["audit_report_file"] in (".", "..")
            or type(audit["audit_report_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", audit["audit_report_sha256"]) is None):
        raise LockPreparationRefused("independent audit receipt contradicts evidence")
    report = receipt_path.parent / audit["audit_report_file"]
    if (report.is_symlink() or not report.is_file()
            or report.stat().st_size > 1048576
            or sha256_hex(report.read_bytes()) != audit["audit_report_sha256"]):
        raise LockPreparationRefused("independent audit report missing or changed")
    return audit, digest


def prepare_lock(*, audit_receipt: Path, root: Path = REPOSITORY_ROOT,
                 capture_dir: Path = controls.CAPTURE_DIR) -> bytes:
    """Return exact lock bytes only after every pre-data gate succeeds."""
    manifest = load_paper_manifest(root=root)
    if (manifest.get("collection_status") != "BLOCKED"
            or manifest.get("readiness_status") != "NOT_QUALIFIED"
            or manifest.get("study2_paper_observations") != 0):
        raise LockPreparationRefused("manifest is not blocked pre-data")
    capture = controls._capture(manifest, capture_dir)
    arms = [arm for family in manifest["families"] for arm in family["arms"]]
    topology = (200, (capture_dir / "topology.response.json").read_bytes())
    baselines = {arm["arm_id"]:
                 ("GET", arm["read_target"], 200,
                  (capture_dir / f"baseline-{index:03d}.response.json").read_bytes())
                 for index, arm in enumerate(arms)}
    evidence_root = root / controls.OUTPUT_DIR
    index = {}
    records = {}
    for name in readiness_requirements():
        filename = f"{name}.json"
        value, digest = _durable_json(evidence_root / filename)
        records[name] = value
        index[name] = {"file": filename, "sha256": digest}
        _validate_refs(value["facts"])
    controls.validate_control_provenance(records, allow_late_evidence=True)
    actual = check_readiness_structure(
        manifest, topology_response=topology, baseline_responses=baselines,
        control_evidence=index, evidence_root=evidence_root)
    subject = {"spreadsheet_id": manifest["spreadsheet_id"],
               "manifest_sha256": sha256_hex(canonical_json_bytes(manifest))}
    audit, receipt_sha = require_independent_audit(
        audit_receipt, subject=subject, control_sha256=actual,
        topology_sha256=capture["topology_sha256"],
        baseline_sha256=capture["baseline_sha256"])
    require_clean_committed_inputs(root)
    return canonical_json_bytes({
        "schema": "sheets-paper-readiness-lock-v1",
        "receipt_sha256": receipt_sha, "independent_audit": audit,
        **subject, "topology_sha256": capture["topology_sha256"],
        "baseline_sha256": capture["baseline_sha256"], "control_sha256": actual})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--independent-audit-receipt", required=True, type=Path)
    parser.add_argument("--prepare-lock-offline", action="store_true", required=True)
    args = parser.parse_args()
    try:
        raw = prepare_lock(audit_receipt=args.independent_audit_receipt)
        target = REPOSITORY_ROOT / READINESS_LOCK_PATH
        with target.open("xb") as file:
            file.write(raw)
        print(sha256_hex(raw))
        return 0
    except Exception as exc:
        print(f"Readiness lock refused: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
