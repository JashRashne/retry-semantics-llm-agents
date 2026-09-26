"""Fail-closed offline verification for later provider paper readiness locks.

This verifier neither gathers live evidence nor creates a lock. A lock can be
prepared only after independent audit of captured provider evidence; no paper
observation or collection authorization is produced here.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.github_paper_manifest import (
    MANIFEST_PATH as GITHUB_MANIFEST_PATH,
    REGISTRY_PATH as GITHUB_REGISTRY_PATH,
    load_github_paper_manifest,
    load_namespace_registry as load_github_namespace_registry,
)
from retry_semantics.study2.razorpay_paper_manifest import (
    REGISTRY_PATH as RAZORPAY_REGISTRY_PATH,
    load_razorpay_paper_manifest,
    load_namespace_registry as load_razorpay_namespace_registry,
    scientific_sha256 as razorpay_scientific_sha256,
)
from retry_semantics.study2.provider_paper_readiness_controls import (
    ControlEvidenceError, validate_github_control, validate_razorpay_control,
)
from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest as load_sheets_paper_manifest

ROOT = Path(__file__).resolve().parents[3]
RAZORPAY_MANIFEST_PATH = Path("research/study2/razorpay/RAZORPAY_PAPER_MANIFEST_V1.json")
SHEETS_MANIFEST_PATH = Path("research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_V1.json")
RUNTIME_FILES = {
    "github": ("src/retry_semantics/study2/github_paper_runtime.py",
               "src/retry_semantics/study2/github_paper_manifest.py",
               "src/retry_semantics/serialization.py",
               "src/retry_semantics/models/base.py",
               "src/retry_semantics/models/fireworks.py",
               "src/retry_semantics/study2/provider_paper_io.py",
               "src/retry_semantics/study2/provider_paper_model.py",
               "src/retry_semantics/study2/provider_paper_collection.py",
               "src/retry_semantics/study2/github_adapter.py",
               "src/retry_semantics/study2/provider_paper_readiness_controls.py",
               "src/retry_semantics/study2/provider_paper_readiness.py"),
    "razorpay": ("src/retry_semantics/study2/razorpay_paper_runtime.py",
                "src/retry_semantics/study2/razorpay_paper_manifest.py",
                "src/retry_semantics/study2/razorpay_adapter.py",
                "src/retry_semantics/runtime/regeneration_context.py",
                "src/retry_semantics/serialization.py",
                "src/retry_semantics/models/base.py",
                "src/retry_semantics/models/fireworks.py",
                "src/retry_semantics/study2/provider_paper_io.py",
                "src/retry_semantics/study2/provider_paper_model.py",
                "src/retry_semantics/study2/provider_paper_collection.py",
                "src/retry_semantics/study2/provider_paper_readiness_controls.py",
                "src/retry_semantics/study2/provider_paper_readiness.py"),
}
PROVIDER_CONTROLS = {
    "github": (
        "repository_identity_and_full_baseline", "authenticated_principal_access",
        "writer_exclusion", "suffix_roundtrip_and_collision_scan",
        "bounded_raw_traversal_authority", "quota_and_timing_headroom",
        "model_capability",
    ),
    "razorpay": (
        "test_mode_scope_access", "writer_exclusion",
        "marker_reservation_and_collision_scan", "bounded_fetch_all_capture",
        "closed_ledger_transport", "timing_headroom", "model_capability",
    ),
}
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class ProviderReadinessError(ValueError):
    """Missing, stale, or unaudited precollection evidence."""


def _read_canonical(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8_000_000:
        raise ProviderReadinessError("missing, symlinked, or oversized evidence")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise ProviderReadinessError("malformed JSON evidence") from exc
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise ProviderReadinessError("noncanonical evidence")
    return value, sha256_hex(raw)


def _safe_file(name: Any) -> str:
    if (type(name) is not str or re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None
            or name in (".", "..")):
        raise ProviderReadinessError("unsafe evidence filename")
    return name


def _when(value: Any) -> datetime:
    if type(value) is not str:
        raise ProviderReadinessError("missing evidence time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProviderReadinessError("invalid evidence time") from exc
    if parsed.tzinfo is None:
        raise ProviderReadinessError("evidence time lacks zone")
    return parsed.astimezone(timezone.utc)


def _check_capture_shape(provider: str, source: str,
                         request: dict[str, Any], response: dict[str, Any]) -> None:
    """Require recorded bytes and transport facts, never a verdict string."""
    if source == "provider_http_capture":
        origin = ("https://api.github.com" if provider == "github"
                  else "https://api.razorpay.com")
        if (not {"method", "url", "headers", "body_hex",
                 "dispatch_started", "attempt_count"} <= set(request)
                or not set(request) <= {"method", "url", "headers", "body_hex",
                                        "dispatch_started", "attempt_count",
                                        "credential_scope_fingerprint",
                                        "started_monotonic"}
                or request["method"] not in ("GET", "POST")
                or type(request["url"]) is not str
                or not request["url"].startswith(origin + "/")
                or type(request["headers"]) is not dict
                or any("authorization" in key.lower() for key in request["headers"])
                or type(request["body_hex"]) is not str
                or request["dispatch_started"] is not True
                or request["attempt_count"] != 1
                or not {"http_status", "headers", "body_hex",
                        "transport_complete", "redirect_followed"} <= set(response)
                or not set(response) <= {"http_status", "headers", "body_hex",
                                         "transport_complete", "redirect_followed",
                                         "ended_monotonic"}
                or type(response["http_status"]) is not int
                or type(response["headers"]) is not dict
                or type(response["body_hex"]) is not str
                or response["transport_complete"] is not True
                or response["redirect_followed"] is not False):
            raise ProviderReadinessError("provider capture lacks raw HTTP facts")
        try:
            bytes.fromhex(request["body_hex"])
            bytes.fromhex(response["body_hex"])
        except ValueError as exc:
            raise ProviderReadinessError("provider capture has invalid bytes") from exc
    elif source == "model_capability_capture":
        if (set(request) != {"model", "tools_sha256", "parameters_sha256",
                             "payload_hex", "payload_sha256"}
                or request["model"] !=
                    "accounts/fireworks/models/deepseek-v4-flash-0731"
                or any(type(request[key]) is not str or
                       _HASH.fullmatch(request[key]) is None
                       for key in ("tools_sha256", "parameters_sha256",
                                   "payload_sha256"))
                or type(request["payload_hex"]) is not str
                or set(response) != {"model_accepted", "tool_call_supported",
                                     "raw_response_sha256", "raw_response_hex"}
                or response["model_accepted"] is not True
                or response["tool_call_supported"] is not True
                or type(response["raw_response_sha256"]) is not str
                or _HASH.fullmatch(response["raw_response_sha256"]) is None
                or type(response["raw_response_hex"]) is not str):
            raise ProviderReadinessError("model capability lacks captured proof")
        try:
            payload = bytes.fromhex(request["payload_hex"])
            raw = bytes.fromhex(response["raw_response_hex"])
            if (len(payload) > 4_000_000 or len(raw) > 4_000_000
                    or sha256_hex(payload) != request["payload_sha256"] or
                    sha256_hex(raw) != response["raw_response_sha256"]):
                raise ValueError("model response digest differs")
        except ValueError as exc:
            raise ProviderReadinessError("model capability raw response differs") from exc
    else:
        if (source != "operator_access_inventory"
                or set(request) != {"scope", "principals", "writer_paths"}
                or type(request["principals"]) is not list
                or not request["principals"]
                or type(request["writer_paths"]) is not list
                or not request["writer_paths"]
                or set(response) != {"reviewed_by", "access_inventory_sha256"}
                or type(response["reviewed_by"]) is not str
                or not response["reviewed_by"]
                or type(response["access_inventory_sha256"]) is not str
                or _HASH.fullmatch(response["access_inventory_sha256"]) is None):
            raise ProviderReadinessError("operator inventory cannot prove provider result")


def current_static_identity(provider: str, *, root: Path = ROOT) -> dict[str, Any]:
    """Hash actual committed-intended bytes; no live qualification is inferred."""
    if provider not in PROVIDER_CONTROLS:
        raise ProviderReadinessError("unknown provider")
    path = (GITHUB_MANIFEST_PATH if provider == "github"
            else RAZORPAY_MANIFEST_PATH)
    if provider == "github":
        manifest_hash = load_github_paper_manifest(root).manifest_hash
    else:
        manifest, manifest_hash = _read_canonical(root / path)
        registry = load_razorpay_namespace_registry(root)
        try:
            if manifest != load_razorpay_paper_manifest(root):
                raise ProviderReadinessError("Razorpay manifest differs from inputs")
        except ValueError as exc:
            raise ProviderReadinessError("Razorpay manifest cannot be regenerated") from exc
        if (manifest.get("schema") != "razorpay-paper-manifest-v1"
                or manifest.get("status") != "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"
                or registry.get("status") != "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"
                or manifest.get("registry_semantic_sha256") !=
                    razorpay_scientific_sha256(registry)
                or len(manifest.get("families", ())) != 64):
            raise ProviderReadinessError("Razorpay paper manifest is not frozen")
    return {
        "provider": provider,
        "manifest_sha256": manifest_hash,
        "runtime_sha256": {
            relative: sha256_hex((root / relative).read_bytes())
            for relative in RUNTIME_FILES[provider]
        },
    }


def _require_committed(root: Path, paths: tuple[Path, ...]) -> None:
    """A reviewed lock and code must be exactly the committed bytes."""
    try:
        def git(*args: str) -> bytes:
            return subprocess.run(
                ["/usr/bin/git", "-c", "core.fsmonitor=false",
                 "-c", "core.untrackedCache=false", *args],
                cwd=root, capture_output=True, check=True,
            ).stdout
        if (git("rev-parse", "--show-toplevel").decode().strip() != str(root)
                or git("status", "--porcelain", "--ignore-submodules=all")):
            raise ProviderReadinessError("readiness repository is not clean")
        for path in paths:
            relative = path.relative_to(root)
            if path.is_symlink() or path.read_bytes() != git("show", "HEAD:" + str(relative)):
                raise ProviderReadinessError("readiness bytes differ from reviewed commit")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise ProviderReadinessError("readiness bytes are not committed") from exc


def check_readiness_lock(provider: str, lock_path: Path, *,
                         evidence_dir: Path, audit_receipt_path: Path,
                         audit_report_path: Path, root: Path = ROOT,
                         now: datetime | None = None) -> dict[str, Any]:
    """Accept only exact, fresh, audit-bound evidence and current code bytes."""
    identity = current_static_identity(provider, root=root)
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ProviderReadinessError("current time lacks zone")
    manifest_path = (GITHUB_MANIFEST_PATH if provider == "github"
                     else RAZORPAY_MANIFEST_PATH)
    registry_path = (GITHUB_REGISTRY_PATH if provider == "github"
                     else RAZORPAY_REGISTRY_PATH)
    _require_committed(root, (root / manifest_path, root / registry_path, lock_path,
                              root / "src/retry_semantics/study2/provider_paper_readiness.py",
                              *(root / p for p in RUNTIME_FILES[provider])))
    lock, _ = _read_canonical(lock_path)
    receipt, receipt_hash = _read_canonical(audit_receipt_path)
    report, report_hash = _read_canonical(audit_report_path)
    if (set(lock) != {"schema", "static_identity", "live_evidence_sha256",
                     "independent_audit_receipt_sha256", "study2_paper_observations",
                     "collection_authorized"}
            or lock["schema"] != f"{provider}-paper-readiness-lock-v1"
            or lock["static_identity"] != identity
            or lock["study2_paper_observations"] != 0
            or lock["collection_authorized"] is not False
            or lock["independent_audit_receipt_sha256"] != receipt_hash):
        raise ProviderReadinessError("stale or unauthorized readiness lock")
    hashes = lock["live_evidence_sha256"]
    if type(hashes) is not dict or set(hashes) != set(PROVIDER_CONTROLS[provider]):
        raise ProviderReadinessError("missing live readiness controls")
    if (set(receipt) != {"schema", "static_identity", "live_evidence_sha256",
                         "audit_report_sha256", "auditor_id", "audited_at_utc"}
            or receipt["schema"] != f"{provider}-paper-readiness-audit-receipt-v1"
            or receipt["static_identity"] != identity
            or receipt["live_evidence_sha256"] != hashes
            or receipt["audit_report_sha256"] != report_hash
            or type(receipt["auditor_id"]) is not str
            or not receipt["auditor_id"]
            or _when(receipt["audited_at_utc"]) > instant):
        raise ProviderReadinessError("independent audit receipt missing or stale")
    if (set(report) != {"schema", "static_identity", "live_evidence_sha256",
                        "independent_auditor", "result", "findings"}
            or report["schema"] != f"{provider}-paper-readiness-audit-report-v1"
            or report["static_identity"] != identity
            or report["live_evidence_sha256"] != hashes
            or report["independent_auditor"] != receipt["auditor_id"]
            or report["result"] != "PASS" or report["findings"] != []):
        raise ProviderReadinessError("independent audit report not passing")
    manifest = (load_github_paper_manifest(root).as_json() if provider == "github"
                else load_razorpay_paper_manifest(root))
    registry = (load_github_namespace_registry(root).as_json() if provider == "github"
                else load_razorpay_namespace_registry(root))
    context: dict[str, Any] = {}
    for control in PROVIDER_CONTROLS[provider]:
        digest = hashes[control]
        if type(digest) is not str or _HASH.fullmatch(digest) is None:
            raise ProviderReadinessError("invalid evidence hash")
        evidence, actual_hash = _read_canonical(evidence_dir / _safe_file(control + ".json"))
        if (actual_hash != digest
                or set(evidence) != {"schema", "control", "static_identity",
                                     "capture_kind", "capture_file",
                                     "capture_sha256", "captured_at_utc",
                                     "valid_until_utc", "qualified", "facts"}
                or evidence["schema"] != f"{provider}-paper-readiness-evidence-v1"
                or evidence["control"] != control
                or evidence["static_identity"] != identity
                or evidence["qualified"] is not True
                or type(evidence["facts"]) is not dict or not evidence["facts"]
                or evidence["capture_kind"] != (
                    "operator_access_inventory" if control == "writer_exclusion"
                    else "model_capability_capture" if control == "model_capability"
                    else "provider_http_capture")
                or not (_when(evidence["captured_at_utc"]) <=
                        _when(receipt["audited_at_utc"]) <= instant <=
                        _when(evidence["valid_until_utc"]))):
            raise ProviderReadinessError(f"unqualified or stale control: {control}")
        capture_path = evidence_dir / _safe_file(evidence["capture_file"])
        if (capture_path.is_symlink() or not capture_path.is_file()
                or capture_path.stat().st_size > 8_000_000
                or type(evidence["capture_sha256"]) is not str
                or sha256_hex(capture_path.read_bytes()) != evidence["capture_sha256"]):
            raise ProviderReadinessError(f"missing raw capture: {control}")
        capture, _ = _read_canonical(capture_path)
        if (set(capture) != {"schema", "source", "synthetic", "request_evidence",
                            "response_evidence", "captured_at_utc"}
                or capture["schema"] != f"{provider}-paper-readiness-capture-v1"
                or capture["source"] != evidence["capture_kind"]
                or capture["synthetic"] is not False
                or type(capture["request_evidence"]) is not dict
                or type(capture["response_evidence"]) is not dict
                or not capture["request_evidence"]
                or not capture["response_evidence"]
                or capture["captured_at_utc"] != evidence["captured_at_utc"]):
            raise ProviderReadinessError(f"synthetic or ungrounded capture: {control}")
        _check_capture_shape(provider, capture["source"],
                             capture["request_evidence"],
                             capture["response_evidence"])
        try:
            if provider == "github":
                validate_github_control(control, manifest, registry,
                                        evidence["facts"], capture, context)
            else:
                validate_razorpay_control(control, manifest, registry,
                                         evidence["facts"], capture, context)
        except (ControlEvidenceError, KeyError, TypeError, ValueError) as exc:
            raise ProviderReadinessError(f"control does not prove {control}") from exc
    return identity


def check_final_collection_authorization(*, provider: str,
                                         provider_identity: dict[str, Any],
                                         readiness_lock_paths: dict[str, Path],
                                         authorization_path: Path,
                                         audit_receipt_path: Path,
                                         audit_report_path: Path,
                                         root: Path = ROOT,
                                         now: datetime | None = None) -> str:
    """Verify a future, separately audited cross-provider authorization.

    This defines a read-only gate; it does not create or imply authorization.
    The caller must separately validate its provider-specific readiness lock.
    """
    if (provider not in PROVIDER_CONTROLS
            or type(readiness_lock_paths) is not dict
            or set(readiness_lock_paths) != {"github", "razorpay", "sheets"}):
        raise ProviderReadinessError("all provider readiness locks are required")
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ProviderReadinessError("authorization time lacks zone")
    _require_committed(root, (authorization_path, audit_receipt_path,
                              audit_report_path, *readiness_lock_paths.values()))
    authorization, authorization_hash = _read_canonical(authorization_path)
    receipt, _ = _read_canonical(audit_receipt_path)
    report, report_hash = _read_canonical(audit_report_path)
    lock_hashes = {name: _read_canonical(path)[1]
                   for name, path in readiness_lock_paths.items()}
    identities = authorization.get("provider_static_identities")
    if (set(authorization) != {
            "schema", "status", "collection_authorized",
            "provider_readiness_lock_sha256", "provider_static_identities",
            "authorized_at_utc", "study2_paper_observations_at_authorization"}
            or authorization["schema"] != "study2-final-collection-authorization-v1"
            or authorization["status"] != "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"
            or authorization["collection_authorized"] is not True
            or authorization["provider_readiness_lock_sha256"] != lock_hashes
            or type(identities) is not dict
            or set(identities) != set(lock_hashes)
            or identities[provider] != provider_identity
            or authorization["study2_paper_observations_at_authorization"] != 0
            or _when(authorization["authorized_at_utc"]) > instant):
        raise ProviderReadinessError("final collection authorization missing or stale")
    for p in ("github", "razorpay"):
        if identities.get(p) != current_static_identity(p, root=root):
            raise ProviderReadinessError(f"current static identity of {p} differs from authorization")
    for name, path in readiness_lock_paths.items():
        lock, _ = _read_canonical(path)
        if name == "sheets":
            try:
                sheets_manifest_hash = sha256_hex(
                    canonical_json_bytes(load_sheets_paper_manifest(root=root)))
            except Exception:
                _, sheets_manifest_hash = _read_canonical(root / SHEETS_MANIFEST_PATH)
            if (lock.get("schema") != "sheets-paper-readiness-lock-v1"
                    or lock.get("manifest_sha256") != sheets_manifest_hash
                    or identities[name] != {
                        "manifest_sha256": lock.get("manifest_sha256"),
                        "control_sha256": lock.get("control_sha256")}
                    or any(type(lock.get(key)) is not str or
                           _HASH.fullmatch(lock[key]) is None
                           for key in ("manifest_sha256", "receipt_sha256"))
                    or type(lock.get("control_sha256")) is not dict
                    or not lock["control_sha256"]
                    or any(type(digest) is not str or _HASH.fullmatch(digest) is None
                           for digest in lock["control_sha256"].values())):
                raise ProviderReadinessError("Sheets readiness lock identity differs")
        elif (lock.get("schema") != f"{name}-paper-readiness-lock-v1"
              or lock.get("static_identity") != identities[name]
              or lock.get("collection_authorized") is not False):
            raise ProviderReadinessError("provider readiness lock identity differs")
    if (set(receipt) != {"schema", "authorization_sha256",
                         "audit_report_sha256", "auditor_id", "audited_at_utc"}
            or receipt["schema"] != "study2-final-authorization-audit-receipt-v1"
            or receipt["authorization_sha256"] != authorization_hash
            or receipt["audit_report_sha256"] != report_hash
            or type(receipt["auditor_id"]) is not str
            or not receipt["auditor_id"]
            or _when(receipt["audited_at_utc"]) >
                _when(authorization["authorized_at_utc"])):
        raise ProviderReadinessError("independent final authorization receipt missing")
    if (set(report) != {"schema", "authorization_sha256",
                        "independent_auditor", "result", "findings"}
            or report["schema"] != "study2-final-authorization-audit-report-v1"
            or report["authorization_sha256"] != authorization_hash
            or report["independent_auditor"] != receipt["auditor_id"]
            or report["result"] != "PASS" or report["findings"] != []):
        raise ProviderReadinessError("independent final authorization audit not passing")
    return authorization_hash
