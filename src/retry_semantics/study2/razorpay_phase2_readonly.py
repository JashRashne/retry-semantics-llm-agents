"""Single-use, read-only Phase-2 Razorpay engineering diagnostic.

The only outbound methods in this module and the reused list observer are GET.
No live call is made by preparation or by importing this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable, Mapping
import uuid

import httpx

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.razorpay_adapter import (
    DEFAULT_TRANSPORT_PROFILE,
    MARKER_KEY,
    ObservationStatus,
    ORDER_AMOUNT,
    ORDER_CURRENCY,
    RAZORPAY_ORIGIN,
    RazorpayCredentials,
    RazorpayOrderAdapter,
)


PLAN_FILENAME = "qualification_plan.json"
INTENT_FILENAME = "intent.json"
RESULT_FILENAME = "qualification_result.json"
CONFIRMATION = "EXECUTE_ONE_RAZORPAY_PHASE2_READONLY_DIAGNOSTIC"
TEST_MODE_CONFIRMATION = "SUPPLIED_CREDENTIALS_ARE_RAZORPAY_TEST_MODE"
PLAN_SCHEMA = "razorpay-phase2-readonly-plan-v1"
EVIDENCE_SCHEMA = "razorpay-phase2-readonly-evidence-v1"
PAGE_CAP = 2
PADDING_SECONDS = 300
TIMEOUT_SECONDS = 30.0
MAX_GET_DISPATCHES = 5

PHASE1_HASHES = {
    "research/study2/razorpay/RAZORPAY_LIVE_QUALIFICATION_PHASE1_LOCK.md": "2afc652fa636204613168e6ba5fd4640205c6728f8fb7e14eeb07c698425e551",
    "research/study2/razorpay/evidence/phase1/baseline_observation.json": "b7ff240542febde3255e49fd4d90179374b6b5404ef6d7190392a1f3e6fa1376",
    "research/study2/razorpay/evidence/phase1/intent.json": "9a4d5be20bf73a936ba8971f00a56a92c7b61d7badc21cf2b6841a656966503c",
    "research/study2/razorpay/evidence/phase1/mutation_1.json": "5393ee65d8a82db38e7190e516923c02a25d13f8cea23c4e8ec7a790ff06de2a",
    "research/study2/razorpay/evidence/phase1/observation_1.json": "a55f439d9cf383c0b6df7f760d4207c08efb6992feca9b2902ab664cbe2640f4",
    "research/study2/razorpay/evidence/phase1/qualification_plan.json": "1560f11a0b0d3fb69a143e4099e7e4c50e5ac237acc1ffb5d9a5525ae74138ca",
    "research/study2/razorpay/evidence/phase1/qualification_result.json": "5b3491664412712c1c77cbbab79dc248a81b7efafab916521f572ea6473d77c4",
}
SOURCE_PATHS = (
    "src/retry_semantics/serialization.py",
    "src/retry_semantics/study2/razorpay_adapter.py",
    "src/retry_semantics/study2/razorpay_phase2_readonly.py",
    "scripts/qualify_study2_razorpay_phase2.py",
    "tests/test_study2_razorpay_phase2_readonly.py",
    "research/study2/razorpay/RAZORPAY_PHASE2_READONLY_QUALIFICATION_DRAFT.md",
)


class QualificationError(RuntimeError):
    """Fixed-text refusal; provider and credential exceptions are discarded."""

    def __init__(self, reason: str) -> None:
        self.reason = reason if re.fullmatch(r"[a-z0-9_]{1,96}", reason) else "qualification_refused"
        super().__init__(self.reason)


class TerminalStatus(str, Enum):
    RESOLVED = "RESOLVED"
    INCONCLUSIVE = "INCONCLUSIVE"
    LOCAL_PREFLIGHT_FAILED = "LOCAL_PREFLIGHT_FAILED"


@dataclass(frozen=True)
class ExecutionOutcome:
    status: TerminalStatus
    reason: str
    counts: dict[str, int]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_file(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError, UnicodeError):
        raise QualificationError("evidence_unavailable_or_invalid") from None
    if type(value) is not dict:
        raise QualificationError("evidence_unavailable_or_invalid")
    return value


def read_phase1_facts(root: Path) -> dict[str, object]:
    """Verify every locked byte before deriving any Phase-2 target or scope."""
    for relative, expected in PHASE1_HASHES.items():
        try:
            actual = sha256_hex((root / relative).read_bytes())
        except OSError:
            raise QualificationError("phase1_evidence_unavailable") from None
        if actual != expected:
            raise QualificationError("phase1_evidence_hash_mismatch")
    prefix = root / "research/study2/razorpay/evidence/phase1"
    mutation = _json_file(prefix / "mutation_1.json").get("adapter_evidence")
    observation = _json_file(prefix / "observation_1.json")
    phase1_plan = _json_file(prefix / "qualification_plan.json")
    result = _json_file(prefix / "qualification_result.json")
    if type(mutation) is not dict or type(observation.get("adapter_evidence")) is not dict:
        raise QualificationError("phase1_facts_invalid")
    observed = observation["adapter_evidence"]
    if not (
        mutation.get("classification") == "ACKNOWLEDGED_CREATE"
        and mutation.get("acknowledgement_valid") is True
        and observed.get("status") == "structurally_completed_unqualified"
        and observed.get("matching_order_ids") == []
        and result.get("status") == "INCONCLUSIVE"
        and result.get("reason") == "observation_1_exact_set_not_observed"
        and mutation.get("provider_order_id") == "order_TfBuv3iQHQrz9p"
        and phase1_plan.get("marker") == observed.get("marker")
        and phase1_plan.get("marker") == "study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215"
        and phase1_plan.get("amount") == ORDER_AMOUNT
        and phase1_plan.get("currency") == ORDER_CURRENCY
        and phase1_plan.get("receipt") == "prohibited"
        and observation.get("from_timestamp") == 1790103525
        and observation.get("to_timestamp") == 1790104125
        and mutation.get("credential_scope_fingerprint") == observed.get("credential_scope_fingerprint")
        and re.fullmatch(r"[0-9a-f]{64}", str(mutation.get("credential_scope_fingerprint", "")))
    ):
        raise QualificationError("phase1_facts_invalid")
    return {
        "provider_order_id": mutation["provider_order_id"],
        "marker": phase1_plan["marker"],
        "original_from_timestamp": observation["from_timestamp"],
        "original_to_timestamp": observation["to_timestamp"],
        "credential_scope_fingerprint": mutation["credential_scope_fingerprint"],
    }


def read_git_provenance(root: Path) -> dict[str, object]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                ("git", "-C", str(root), *args), check=True, capture_output=True,
                text=True, timeout=15,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            raise QualificationError("git_provenance_unavailable") from None
    return {
        "clean": run("status", "--porcelain", "--untracked-files=all") == "",
        "git_head": run("rev-parse", "HEAD"),
        "origin_main": run("rev-parse", "origin/main"),
    }


def read_source_hashes(root: Path) -> dict[str, str]:
    try:
        return {path: sha256_hex((root / path).read_bytes()) for path in SOURCE_PATHS}
    except OSError:
        raise QualificationError("source_file_unavailable") from None


def read_runtime_versions() -> dict[str, str]:
    try:
        return {"httpx": importlib.metadata.version("httpx")}
    except importlib.metadata.PackageNotFoundError:
        raise QualificationError("runtime_dependency_unavailable") from None


def _require_provenance(provenance: Mapping[str, object]) -> None:
    if provenance.get("clean") is not True:
        raise QualificationError("working_tree_not_clean")
    if provenance.get("git_head") != provenance.get("origin_main"):
        raise QualificationError("head_origin_main_mismatch")
    if type(provenance.get("git_head")) is not str or re.fullmatch(r"[0-9a-f]{40}", provenance["git_head"]) is None:
        raise QualificationError("invalid_git_head")


def _require_outside_repo(root: Path, destination: Path) -> None:
    try:
        destination.resolve().relative_to(root.resolve())
    except ValueError:
        return
    raise QualificationError("package_must_be_outside_repository")


def _location_hash(qualification_id: str, destination: Path) -> str:
    try:
        if str(uuid.UUID(qualification_id)) != qualification_id:
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise QualificationError("qualification_id_invalid") from None
    return sha256_hex(canonical_json_bytes({
        "qualification_id": qualification_id,
        "resolved_package_directory": str(destination.resolve()),
    }))


def _write_exclusive_json(path: Path, value: Mapping[str, object]) -> None:
    data = canonical_json_bytes(dict(value)) + b"\n"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise QualificationError("artifact_already_exists") from None
    except OSError:
        raise QualificationError("artifact_create_failed") from None
    try:
        offset = 0
        while offset < len(data):
            count = os.write(fd, data[offset:])
            if count <= 0:
                raise OSError
            offset += count
        os.fsync(fd)
    except OSError:
        raise QualificationError("artifact_persistence_failed") from None
    finally:
        os.close(fd)
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        raise QualificationError("directory_persistence_failed") from None


def plan_file_sha256(package_dir: Path) -> str:
    try:
        return sha256_hex((package_dir.resolve() / PLAN_FILENAME).read_bytes())
    except OSError:
        raise QualificationError("plan_unavailable_or_invalid") from None


def prepare_package(
    repository_root: Path, package_dir: Path, *,
    _provenance_reader: Callable[[Path], Mapping[str, object]] = read_git_provenance,
    _source_hash_reader: Callable[[Path], Mapping[str, str]] = read_source_hashes,
    _runtime_reader: Callable[[], Mapping[str, str]] = read_runtime_versions,
) -> dict[str, object]:
    root, destination = repository_root.resolve(), package_dir.resolve()
    _require_outside_repo(root, destination)
    facts = read_phase1_facts(root)
    provenance = dict(_provenance_reader(root))
    _require_provenance(provenance)
    source_hashes = dict(_source_hash_reader(root))
    runtime = dict(_runtime_reader())
    if runtime != {"httpx": "0.28.1"}:
        raise QualificationError("runtime_dependency_mismatch")
    qualification_id = str(uuid.uuid4())
    plan: dict[str, object] = {
        "schema": PLAN_SCHEMA,
        "prepared_utc": _utc_now(),
        "qualification_id": qualification_id,
        "phase": 2,
        "read_only": True,
        "mutation_dispatch_maximum": 0,
        "post_dispatch_maximum": 0,
        "get_dispatch_maximum": MAX_GET_DISPATCHES,
        "provider_candidate": "razorpay",
        "engineering_only": True,
        "paper_observations": 0,
        "provider_c_selection": "not_performed",
        **facts,
        "provider_window_padding_seconds": PADDING_SECONDS,
        "page_cap": PAGE_CAP,
        "automatic_retry": "prohibited",
        "polling": "prohibited",
        "automatic_rerun": "prohibited",
        "cleanup": "prohibited",
        "transport_profile": DEFAULT_TRANSPORT_PROFILE,
        "timeout_seconds": TIMEOUT_SECONDS,
        "qualification_confirmation": CONFIRMATION,
        "test_mode_operator_confirmation": TEST_MODE_CONFIRMATION,
        "phase1_evidence_hashes": dict(sorted(PHASE1_HASHES.items())),
        "source_hashes": dict(sorted(source_hashes.items())),
        "git_head": provenance["git_head"],
        "origin_main": provenance["origin_main"],
        "runtime_versions": runtime,
        "package_location_sha256": _location_hash(qualification_id, destination),
    }
    plan["plan_sha256"] = sha256_hex(canonical_json_bytes(plan))
    try:
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    except FileExistsError:
        raise QualificationError("package_already_exists") from None
    except OSError:
        raise QualificationError("package_create_failed") from None
    _write_exclusive_json(destination / PLAN_FILENAME, plan)
    return plan


def _load_plan(destination: Path, expected_file_hash: str, facts: Mapping[str, object]) -> dict[str, object]:
    if type(expected_file_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_file_hash) is None:
        raise QualificationError("expected_plan_file_sha256_invalid")
    try:
        raw = (destination / PLAN_FILENAME).read_bytes()
    except OSError:
        raise QualificationError("plan_unavailable_or_invalid") from None
    if sha256_hex(raw) != expected_file_hash:
        raise QualificationError("plan_file_sha256_mismatch")
    try:
        plan = json.loads(raw)
    except (ValueError, UnicodeError):
        raise QualificationError("plan_unavailable_or_invalid") from None
    if type(plan) is not dict:
        raise QualificationError("plan_unavailable_or_invalid")
    without_hash = dict(plan)
    claimed_hash = without_hash.pop("plan_sha256", None)
    if claimed_hash != sha256_hex(canonical_json_bytes(without_hash)):
        raise QualificationError("plan_hash_mismatch")
    required = {
        "schema": PLAN_SCHEMA, "phase": 2, "read_only": True,
        "mutation_dispatch_maximum": 0, "post_dispatch_maximum": 0,
        "get_dispatch_maximum": MAX_GET_DISPATCHES, "provider_candidate": "razorpay",
        "engineering_only": True, "paper_observations": 0,
        "provider_c_selection": "not_performed", **facts,
        "provider_window_padding_seconds": PADDING_SECONDS, "page_cap": PAGE_CAP,
        "automatic_retry": "prohibited", "polling": "prohibited",
        "automatic_rerun": "prohibited", "cleanup": "prohibited",
        "transport_profile": DEFAULT_TRANSPORT_PROFILE, "timeout_seconds": TIMEOUT_SECONDS,
        "qualification_confirmation": CONFIRMATION,
        "test_mode_operator_confirmation": TEST_MODE_CONFIRMATION,
        "phase1_evidence_hashes": dict(sorted(PHASE1_HASHES.items())),
        "runtime_versions": {"httpx": "0.28.1"},
    }
    if any(plan.get(key) != value or type(plan.get(key)) is not type(value) for key, value in required.items()):
        raise QualificationError("plan_invariant_mismatch")
    if (type(plan.get("git_head")) is not str
            or re.fullmatch(r"[0-9a-f]{40}", plan["git_head"]) is None
            or plan.get("origin_main") != plan["git_head"]):
        raise QualificationError("plan_git_provenance_invalid")
    if plan.get("package_location_sha256") != _location_hash(plan.get("qualification_id"), destination):
        raise QualificationError("package_location_mismatch")
    if type(plan.get("source_hashes")) is not dict or set(plan["source_hashes"]) != set(SOURCE_PATHS):
        raise QualificationError("plan_source_hashes_invalid")
    return plan


def _counts() -> dict[str, int]:
    return {
        "direct_fetch_get_dispatches": 0,
        "original_window_get_dispatches": 0,
        "provider_window_get_dispatches": 0,
        "total_get_dispatches": 0,
        "post_dispatches": 0,
        "mutation_dispatches": 0,
    }


def _common(plan: Mapping[str, object], stage: str, counts: Mapping[str, int], *, synthetic: bool) -> dict[str, object]:
    return {
        "schema": EVIDENCE_SCHEMA, "phase": 2, "stage": stage,
        "recorded_utc": _utc_now(), "qualification_id": plan["qualification_id"],
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan["_authorized_file_hash"],
        "package_location_sha256": plan["package_location_sha256"],
        "provider_candidate": "razorpay", "engineering_only": True,
        "paper_observations": 0, "provider_c_selection": "not_performed",
        "synthetic_test_execution": synthetic,
        "live_qualification_evidence": not synthetic,
        "counts": dict(counts),
    }


def _terminal(destination: Path, plan: Mapping[str, object], counts: Mapping[str, int],
              status: TerminalStatus, reason: str, *, synthetic: bool) -> ExecutionOutcome:
    if counts["mutation_dispatches"] != 0 or counts["post_dispatches"] != 0 or counts["total_get_dispatches"] > MAX_GET_DISPATCHES:
        raise QualificationError("dispatch_invariant_violated")
    evidence = _common(plan, "terminal", counts, synthetic=synthetic)
    evidence.update({"status": status.value, "reason": reason,
                     "authoritative_completeness_qualified": False})
    _write_exclusive_json(destination / RESULT_FILENAME, evidence)
    return ExecutionOutcome(status, reason, dict(counts))


def _direct_fetch(client: httpx.Client, credentials: RazorpayCredentials,
                  plan: Mapping[str, object], counts: dict[str, int]) -> tuple[dict[str, object], bool]:
    order_id = plan["provider_order_id"]
    path = f"/v1/orders/{order_id}"
    evidence: dict[str, object] = {
        "requested_provider_order_id": order_id, "provider_order_id": None,
        "entity": None, "amount": None,
        "currency": None, "receipt_state": "unavailable", "status": None,
        "attempts": None, "exact_marker_match": False,
        "provider_created_at": None, "http_status": None,
        "request_path_sha256": sha256_hex(path.encode("ascii")),
        "credential_scope_fingerprint": credentials.scope_fingerprint,
        "source": "GET /v1/orders/:id", "provenance": "phase1_acknowledged_order_id",
        "validation_reason": "direct_fetch_not_validated",
    }
    outbound = client.build_request("GET", RAZORPAY_ORIGIN + path,
                                    headers={"Authorization": credentials._authorization_value()})
    counts["direct_fetch_get_dispatches"] += 1
    counts["total_get_dispatches"] += 1
    try:
        response = client.send(outbound)
    except Exception:
        evidence["validation_reason"] = "transport_exception"
        return evidence, False
    evidence["http_status"] = response.status_code
    if response.status_code != 200:
        evidence["validation_reason"] = "unexpected_http_status"
        return evidence, False
    try:
        value = json.loads(response.content)
    except (ValueError, UnicodeError):
        evidence["validation_reason"] = "malformed_json"
        return evidence, False
    if type(value) is not dict:
        evidence["validation_reason"] = "malformed_order"
        return evidence, False
    if type(value.get("id")) is str and value["id"] == order_id:
        evidence["provider_order_id"] = order_id
    evidence.update({
        "entity": "order" if value.get("entity") == "order" else "unexpected",
        "amount": value.get("amount") if type(value.get("amount")) is int else None,
        "currency": "INR" if value.get("currency") == "INR" else "unexpected",
        "receipt_state": "absent" if "receipt" not in value else ("null" if value["receipt"] is None else "non_null"),
        "status": value.get("status") if value.get("status") in ("created", "attempted", "paid") else "unrecognized",
        "attempts": value.get("attempts") if type(value.get("attempts")) is int else None,
        "provider_created_at": value.get("created_at") if type(value.get("created_at")) is int and value["created_at"] >= 0 else None,
    })
    notes = value.get("notes")
    evidence["exact_marker_match"] = (
        "notes" in value and type(notes) is dict and
        type(notes.get(MARKER_KEY)) is str and notes[MARKER_KEY] == plan["marker"]
    )
    valid = (
        value.get("id") == order_id and type(value.get("id")) is str
        and value.get("entity") == "order"
        and type(value.get("amount")) is int and value["amount"] == ORDER_AMOUNT
        and value.get("currency") == ORDER_CURRENCY
        and ("receipt" not in value or value["receipt"] is None)
        and evidence["exact_marker_match"] is True
        and type(value.get("created_at")) is int and value["created_at"] >= 0
    )
    evidence["validation_reason"] = "validated" if valid else "direct_fetch_not_validated"
    return evidence, valid


def _observation_evidence(plan: Mapping[str, object], stage: str, counts: Mapping[str, int],
                          result: object, window: tuple[int, int], *, synthetic: bool) -> dict[str, object]:
    evidence = _common(plan, stage, counts, synthetic=synthetic)
    evidence.update({
        "from_timestamp": window[0], "to_timestamp": window[1],
        "boundary_semantics_qualified": False,
        "adapter_evidence": result.sanitized_evidence(),
    })
    return evidence


def _observe(adapter: RazorpayOrderAdapter, plan: Mapping[str, object],
             window: tuple[int, int], stage: str, counts: dict[str, int]):
    result = adapter.observe_orders(marker=plan["marker"], from_timestamp=window[0],
                                    to_timestamp=window[1], page_cap=PAGE_CAP)
    key = "original_window_get_dispatches" if stage == "original_window_observation" else "provider_window_get_dispatches"
    counts[key] += result.pages_requested
    counts["total_get_dispatches"] += result.pages_requested
    return result


def execute_package(
    repository_root: Path, package_dir: Path, *,
    execute_live_readonly_diagnostic: bool,
    confirmation: str, test_mode_operator_confirmation: str,
    plan_file_sha256: str, key_id: str, key_secret: str,
    _provenance_reader: Callable[[Path], Mapping[str, object]] = read_git_provenance,
    _source_hash_reader: Callable[[Path], Mapping[str, str]] = read_source_hashes,
    _runtime_reader: Callable[[], Mapping[str, str]] = read_runtime_versions,
    _synthetic_transport: httpx.MockTransport | None = None,
    _synthetic_test_execution: bool = False,
) -> ExecutionOutcome:
    if execute_live_readonly_diagnostic is not True:
        raise QualificationError("live_readonly_flag_required")
    if confirmation != CONFIRMATION:
        raise QualificationError("confirmation_mismatch")
    if test_mode_operator_confirmation != TEST_MODE_CONFIRMATION:
        raise QualificationError("test_mode_operator_confirmation_required")
    if type(_synthetic_test_execution) is not bool:
        raise QualificationError("synthetic_execution_mode_invalid")
    production_seams = (
        _provenance_reader is read_git_provenance and
        _source_hash_reader is read_source_hashes and
        _runtime_reader is read_runtime_versions and _synthetic_transport is None
    )
    if not _synthetic_test_execution and not production_seams:
        raise QualificationError("production_seam_injection_rejected")
    if _synthetic_test_execution and not isinstance(_synthetic_transport, httpx.MockTransport):
        raise QualificationError("synthetic_mock_transport_required")
    if re.match(r"(?i)^rzp_live(?:_|$)", key_id):
        raise QualificationError("live_looking_key_id_rejected")
    try:
        credentials = RazorpayCredentials(key_id, key_secret)
    except Exception:
        raise QualificationError("credentials_invalid") from None
    root, destination = repository_root.resolve(), package_dir.resolve()
    _require_outside_repo(root, destination)
    if not destination.is_dir():
        raise QualificationError("package_missing")
    facts = read_phase1_facts(root)
    plan = _load_plan(destination, plan_file_sha256, facts)
    if (destination / INTENT_FILENAME).exists():
        raise QualificationError("package_already_consumed")
    try:
        entries = {entry.name for entry in destination.iterdir()}
    except OSError:
        raise QualificationError("package_unavailable") from None
    if entries != {PLAN_FILENAME}:
        raise QualificationError("package_not_pristine")
    provenance = dict(_provenance_reader(root))
    _require_provenance(provenance)
    if provenance["git_head"] != plan["git_head"] or provenance["origin_main"] != plan["origin_main"]:
        raise QualificationError("plan_git_provenance_mismatch")
    if dict(_source_hash_reader(root)) != plan["source_hashes"]:
        raise QualificationError("plan_source_hash_mismatch")
    if dict(_runtime_reader()) != plan["runtime_versions"]:
        raise QualificationError("runtime_dependency_mismatch")
    plan["_authorized_file_hash"] = plan_file_sha256
    counts = _counts()
    intent = _common(plan, "intent", counts, synthetic=_synthetic_test_execution)
    intent.update({"session_consumed": True, "execution_started": True,
                   "maximum_get_dispatches": MAX_GET_DISPATCHES,
                   "mutation_dispatch_maximum": 0})
    # O_EXCL is the irreversible race winner; fsync completes before first GET.
    _write_exclusive_json(destination / INTENT_FILENAME, intent)
    if credentials.scope_fingerprint != facts["credential_scope_fingerprint"]:
        return _terminal(destination, plan, counts, TerminalStatus.LOCAL_PREFLIGHT_FAILED,
                         "credential_scope_mismatch", synthetic=_synthetic_test_execution)
    direct_client = None
    adapter = None
    try:
        transport = _synthetic_transport if _synthetic_test_execution else httpx.HTTPTransport(retries=0)
        direct_client = httpx.Client(transport=transport, timeout=httpx.Timeout(TIMEOUT_SECONDS),
                                     follow_redirects=False, trust_env=False)
        if _synthetic_test_execution:
            adapter = RazorpayOrderAdapter(credentials, timeout_seconds=TIMEOUT_SECONDS,
                                           transport=transport, transport_profile="synthetic_mocktransport_offline_v1")
        else:
            adapter = RazorpayOrderAdapter(credentials, timeout_seconds=TIMEOUT_SECONDS)
        direct, valid = _direct_fetch(direct_client, credentials, plan, counts)
        evidence = _common(plan, "direct_fetch", counts, synthetic=_synthetic_test_execution)
        evidence.update(direct)
        _write_exclusive_json(destination / "direct_fetch.json", evidence)
        if not valid:
            return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                             "direct_fetch_not_validated", synthetic=_synthetic_test_execution)
        original_window = (plan["original_from_timestamp"], plan["original_to_timestamp"])
        original = _observe(adapter, plan, original_window, "original_window_observation", counts)
        _write_exclusive_json(destination / "original_window_observation.json",
                              _observation_evidence(plan, "original_window_observation", counts,
                                                    original, original_window, synthetic=_synthetic_test_execution))
        if original.status is not ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED:
            return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                             "original_window_observation_incomplete", synthetic=_synthetic_test_execution)
        ids = set(original.matching_order_ids)
        if ids == {plan["provider_order_id"]} and original.matching_resource_count == 1:
            return _terminal(destination, plan, counts, TerminalStatus.RESOLVED,
                             "later_list_visibility_established_under_original_window",
                             synthetic=_synthetic_test_execution)
        if ids:
            return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                             "original_window_unexpected_matching_resource", synthetic=_synthetic_test_execution)
        created_at = direct["provider_created_at"]
        provider_window = (created_at - PADDING_SECONDS, created_at + PADDING_SECONDS)
        if provider_window[0] < 0:
            return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                             "provider_window_bounds_invalid", synthetic=_synthetic_test_execution)
        provider = _observe(adapter, plan, provider_window, "provider_window_observation", counts)
        _write_exclusive_json(destination / "provider_window_observation.json",
                              _observation_evidence(plan, "provider_window_observation", counts,
                                                    provider, provider_window, synthetic=_synthetic_test_execution))
        if provider.status is not ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED:
            return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                             "provider_window_observation_incomplete", synthetic=_synthetic_test_execution)
        provider_ids = set(provider.matching_order_ids)
        if provider_ids == {plan["provider_order_id"]} and provider.matching_resource_count == 1:
            outside = not original_window[0] <= created_at <= original_window[1]
            reason = ("provider_timestamp_window_explains_phase1_miss" if outside
                      else "window_behavior_requires_further_review")
            status = TerminalStatus.RESOLVED if outside else TerminalStatus.INCONCLUSIVE
            return _terminal(destination, plan, counts, status, reason,
                             synthetic=_synthetic_test_execution)
        reason = ("direct_fetch_visible_list_visibility_not_established" if not provider_ids
                  else "provider_window_unexpected_matching_resource")
        return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                         reason, synthetic=_synthetic_test_execution)
    except QualificationError:
        raise
    except Exception:
        return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                         "diagnostic_internal_error", synthetic=_synthetic_test_execution)
    finally:
        if direct_client is not None:
            direct_client.close()
        if adapter is not None:
            adapter.close()
