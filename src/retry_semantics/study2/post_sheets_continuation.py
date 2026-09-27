"""Offline, audit-bound authorization for unstarted Study-2 providers only."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Any

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.provider_paper_readiness import (
    ROOT, ProviderReadinessError, _read_canonical, _require_committed, _when,
    check_readiness_lock, current_static_identity, readiness_artifact_paths,
)

PROVIDERS = frozenset(("github", "razorpay"))
AMENDMENT = Path("research/protocol/STUDY2_POST_SHEETS_INCIDENT_CONTINUATION_V1.json")
BASE_AUTHORIZATION = Path("research/study2/STUDY2_FINAL_COLLECTION_AUTHORIZATION_V1.json")
AUTHORIZATION = Path("research/study2/STUDY2_POST_SHEETS_CONTINUATION_AUTHORIZATION_V1.json")
AMENDMENT_RECEIPT = Path("research/protocol/STUDY2_POST_SHEETS_INCIDENT_AUDIT_RECEIPT_V1.json")
AMENDMENT_REPORT = Path("research/protocol/STUDY2_POST_SHEETS_INCIDENT_AUDIT_REPORT_V1.json")
BASE_SHA256 = "4cb8e3ed6be4d7842def2c30269a637effb43a560038abcf7996b9b97a5f826e"
COLLECTOR_SHA256 = "a68fa5f59134a8359f073999f82f93d819284457e7d8fe234f53baaf2044805d"
FIX_COMMIT = "0761929d12366f840c24ebca2203f19b461962a7"
COLLECTOR = "src/retry_semantics/study2/provider_paper_collection.py"


def _path(root: Path, value: Path) -> Path:
    return value if value.is_absolute() else root / value


def _fix_commit_collector_sha(root: Path) -> str:
    try:
        fixed_bytes = subprocess.run(
            ["/usr/bin/git", "show", f"{FIX_COMMIT}:{COLLECTOR}"],
            cwd=root, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProviderReadinessError("defect fix commit unavailable") from exc
    return sha256_hex(fixed_bytes)


def _check_amendment(root: Path, now: datetime, *, audited: bool) -> str:
    path = root / AMENDMENT
    base = root / BASE_AUTHORIZATION
    required = (path, base)
    if audited:
        required += (root / AMENDMENT_RECEIPT, root / AMENDMENT_REPORT)
    _require_committed(root, required)
    doc, digest = _read_canonical(path)
    _, base_digest = _read_canonical(base)
    expected = {
        "schema": "study2-post-sheets-incident-continuation-v1",
        "incident_provider": "sheets",
        "sheets_primary_status": "CLOSED_IMPLEMENTATION_INVALIDATED",
        "failed_external_run_path": "/Users/jashrashne/Library/Application Support/RetrySemantics/study2-sheets-primary-20260928-003851",
        "failed_run_start_identifier": "20260928-003851",
        "failed_run_file_inventory_sha256": "2c639daca8567c7a42a493bb1a2027bd5e41f92b824f2dbf3dbcf7532dfe2d8b",
        "failed_run_summary_sha256": "907011c71811f82c9c0a260c02cb059187a1e8b9cbe09788045d261940e8e877",
        "ack_fix_hostile_audit_zip_sha256": "21efd2689642f726055fc2ba04e70235f583faf126f5115749d894887cdd6552",
        "base_preincident_authorization_sha256": BASE_SHA256,
        "defect_fix_commit": FIX_COMMIT,
        "corrected_collector_sha256": COLLECTOR_SHA256,
        "sheets_primary_rerun_resume_refill_replacement": False,
        "future_sheets_execution": "SEPARATELY_GOVERNED_FOLLOW_UP_OR_REPLICATION_ONLY",
        "github_primary_status": "NOT_STARTED_ELIGIBLE_FOR_CONTINUATION",
        "razorpay_primary_status": "NOT_STARTED_ELIGIBLE_FOR_CONTINUATION",
        "treatment_science_change": False,
        "outcome_definition_change": False,
        "sample_size_change": False,
        "scheduling_change": False,
        "result": "PENDING_INDEPENDENT_AUDIT",
        "collection_authorized": False,
    }
    if doc != expected or base_digest != BASE_SHA256:
        raise ProviderReadinessError("incident amendment or historical authorization differs")
    if _fix_commit_collector_sha(root) != COLLECTOR_SHA256:
        raise ProviderReadinessError("defect fix collector bytes differ")
    if not audited:
        return digest
    receipt, _ = _read_canonical(root / AMENDMENT_RECEIPT)
    report, report_digest = _read_canonical(root / AMENDMENT_REPORT)
    if (set(receipt) != {"schema", "amendment_sha256", "audit_report_sha256",
                         "auditor_id", "audited_at_utc"}
            or receipt["schema"] != "study2-post-sheets-incident-audit-receipt-v1"
            or receipt["amendment_sha256"] != digest
            or receipt["audit_report_sha256"] != report_digest
            or type(receipt["auditor_id"]) is not str or not receipt["auditor_id"]
            or set(report) != {"schema", "amendment_sha256", "independent_auditor",
                               "result", "findings"}
            or report["schema"] != "study2-post-sheets-incident-audit-report-v1"
            or report["amendment_sha256"] != digest
            or report["independent_auditor"] != receipt["auditor_id"]
            or report["result"] != "PASS" or report["findings"] != []
            or _when(receipt["audited_at_utc"]) > now):
        raise ProviderReadinessError("incident amendment lacks independent audit")
    return digest


def continuation_intent_bytes(candidate: dict[str, Any]) -> bytes:
    """Compute exact future bytes for independent review; does not authorize."""
    if (set(candidate) != {"schema", "status", "collection_authorized",
                           "authorized_providers", "sheets_primary_status",
                           "incident_amendment_sha256", "base_preincident_authorization_sha256",
                           "defect_fix_collector_sha256",
                           "provider_readiness_lock_sha256", "provider_static_identities",
                           "authorized_at_utc"}
            or candidate["schema"] != "study2-post-sheets-continuation-authorization-v1"
            or candidate["status"] != "PENDING_INDEPENDENT_AUDIT"
            or candidate["collection_authorized"] is not False
            or candidate["authorized_providers"] != ["github", "razorpay"]
            or candidate["sheets_primary_status"] != "CLOSED_IMPLEMENTATION_INVALIDATED"
            or candidate["base_preincident_authorization_sha256"] != BASE_SHA256
            or candidate["defect_fix_collector_sha256"] != COLLECTOR_SHA256
            or set(candidate["provider_readiness_lock_sha256"]) != PROVIDERS
            or set(candidate["provider_static_identities"]) != PROVIDERS
            or any(type(identity.get("runtime_sha256")) is not dict
                   or COLLECTOR not in identity["runtime_sha256"]
                   for identity in candidate["provider_static_identities"].values())):
        raise ProviderReadinessError("invalid continuation candidate")
    final = dict(candidate, status="FROZEN_INDEPENDENT_AUDIT_PASSED",
                 collection_authorized=True)
    return canonical_json_bytes(final)


def prepare_continuation(*, readiness_lock_paths: dict[str, Path],
                         authorization_at: datetime, root: Path = ROOT,
                         now: datetime | None = None) -> tuple[dict[str, Any], str]:
    """Prepare a blocked candidate after audited provider readiness exists."""
    instant = now or datetime.now(timezone.utc)
    if (set(readiness_lock_paths) != PROVIDERS or instant.tzinfo is None
            or authorization_at.tzinfo is None or authorization_at <= instant):
        raise ProviderReadinessError("invalid continuation preparation inputs")
    amendment_sha = _check_amendment(root, instant, audited=True)
    locks = {name: _path(root, path) for name, path in readiness_lock_paths.items()}
    identities = {}
    for name, path in locks.items():
        evidence_dir, receipt, report = readiness_artifact_paths(name, path)
        identities[name] = check_readiness_lock(
            name, path, evidence_dir=evidence_dir, audit_receipt_path=receipt,
            audit_report_path=report, root=root, now=instant)
    doc = {
        "schema": "study2-post-sheets-continuation-authorization-v1",
        "status": "PENDING_INDEPENDENT_AUDIT",
        "collection_authorized": False,
        "authorized_providers": ["github", "razorpay"],
        "sheets_primary_status": "CLOSED_IMPLEMENTATION_INVALIDATED",
        "incident_amendment_sha256": amendment_sha,
        "base_preincident_authorization_sha256": BASE_SHA256,
        "defect_fix_collector_sha256": COLLECTOR_SHA256,
        "provider_readiness_lock_sha256": {name: _read_canonical(path)[1]
                                           for name, path in locks.items()},
        "provider_static_identities": identities,
        "authorized_at_utc": authorization_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    continuation_intent_bytes(doc)
    return doc, sha256_hex(canonical_json_bytes(doc))


def check_continuation_authorization(*, provider: str, provider_identity: dict[str, Any],
                                     readiness_lock_paths: dict[str, Path],
                                     authorization_path: Path, audit_receipt_path: Path,
                                     audit_report_path: Path, root: Path = ROOT,
                                     now: datetime | None = None) -> str:
    """Launch gate for GitHub/Razorpay; Sheets always fails before file access."""
    if provider not in PROVIDERS:
        raise ProviderReadinessError("Sheets primary is permanently closed")
    if type(readiness_lock_paths) is not dict or set(readiness_lock_paths) != PROVIDERS:
        raise ProviderReadinessError("exactly GitHub and Razorpay locks required")
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ProviderReadinessError("authorization time lacks zone")
    auth_path = _path(root, authorization_path)
    if auth_path != root / AUTHORIZATION:
        raise ProviderReadinessError("continuation authorization path differs")
    locks = {name: _path(root, path) for name, path in readiness_lock_paths.items()}
    receipt_path = _path(root, audit_receipt_path)
    report_path = _path(root, audit_report_path)
    _require_committed(root, (auth_path, receipt_path, report_path, *locks.values(),
                              root / "src/retry_semantics/study2/post_sheets_continuation.py"))
    amendment_sha = _check_amendment(root, instant, audited=True)
    auth, auth_sha = _read_canonical(auth_path)
    receipt, _ = _read_canonical(receipt_path)
    report, report_sha = _read_canonical(report_path)
    identities = auth.get("provider_static_identities")
    if type(identities) is not dict or set(identities) != PROVIDERS:
        raise ProviderReadinessError("continuation static identities missing")
    candidate = dict(auth, status="PENDING_INDEPENDENT_AUDIT",
                     collection_authorized=False)
    if (auth != dict(candidate, status="FROZEN_INDEPENDENT_AUDIT_PASSED",
                     collection_authorized=True)
            or continuation_intent_bytes(candidate) != canonical_json_bytes(auth)
            or auth["incident_amendment_sha256"] != amendment_sha
            or auth["provider_readiness_lock_sha256"] !=
                {name: _read_canonical(path)[1] for name, path in locks.items()}
            or _when(auth["authorized_at_utc"]) > instant
            or identities[provider] != provider_identity):
        raise ProviderReadinessError("continuation authorization missing or stale")
    for name, path in locks.items():
        current = current_static_identity(name, root=root)
        if identities[name] != current:
            raise ProviderReadinessError("continuation runtime identity differs")
        evidence_dir, provider_receipt, provider_report = readiness_artifact_paths(name, path)
        checked = check_readiness_lock(
            name, path, evidence_dir=evidence_dir, audit_receipt_path=provider_receipt,
            audit_report_path=provider_report, root=root, now=instant)
        if checked != current:
            raise ProviderReadinessError("continuation readiness identity differs")
    if (set(receipt) != {"schema", "authorization_sha256", "audit_report_sha256",
                         "auditor_id", "audited_at_utc"}
            or receipt["schema"] != "study2-post-sheets-continuation-audit-receipt-v1"
            or receipt["authorization_sha256"] != auth_sha
            or receipt["audit_report_sha256"] != report_sha
            or type(receipt["auditor_id"]) is not str or not receipt["auditor_id"]
            or set(report) != {"schema", "authorization_sha256", "independent_auditor",
                               "result", "findings"}
            or report["schema"] != "study2-post-sheets-continuation-audit-report-v1"
            or report["authorization_sha256"] != auth_sha
            or report["independent_auditor"] != receipt["auditor_id"]
            or report["result"] != "PASS" or report["findings"] != []
            or not (_when(receipt["audited_at_utc"]) <=
                    _when(auth["authorized_at_utc"]) <= instant)):
        raise ProviderReadinessError("continuation independent audit missing")
    return auth_sha
