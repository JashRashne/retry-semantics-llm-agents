"""One-shot Phase-3 Razorpay engineering gate. Import and prepare do no I/O to Razorpay."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
from pathlib import Path
import re
import time
from typing import Callable, Mapping
import uuid

import httpx

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import razorpay_phase2_readonly as p2
from retry_semantics.study2.razorpay_adapter import (
    DEFAULT_TRANSPORT_PROFILE, DispatchPermit, FrozenOrderCreateRequest,
    MARKER_KEY, MutationClassification, ObservationStatus, ORDER_AMOUNT,
    ORDER_CURRENCY, RazorpayCredentials, RazorpayOrderAdapter,
)


PLAN_FILENAME = "qualification_plan.json"
INTENT_FILENAME = "intent.json"
RESULT_FILENAME = "qualification_result.json"
CONFIRMATION = "EXECUTE_ONE_RAZORPAY_PHASE3_EXACT_REPLAY_VISIBILITY_QUALIFICATION"
TEST_MODE_CONFIRMATION = p2.TEST_MODE_CONFIRMATION
PLAN_SCHEMA = "razorpay-phase3-replay-visibility-plan-v1"
EVIDENCE_SCHEMA = "razorpay-phase3-replay-visibility-evidence-v1"
PAGE_CAP = 2
OFFSETS = (0, 5, 30, 120, 600)
MAX_GET_DISPATCHES = 13
TIMEOUT_SECONDS = 30.0
ORIGINAL_ID = "order_TfBuv3iQHQrz9p"
MARKER = "study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215"
BODY_SHA256 = "cb288039706bb57fd06c7bdcd7ac50d644c1f160c245258aae2931a26b7dd7b4"
IDENTITY_SHA256 = "a5d313c36e10d726e194178e585fdb2257d732d28a719d7f4a2cf8b9c25a05ed"
SCOPE_SHA256 = "5fcd0eb32375ef28ee232ad426a940ce06ee7b3f95281004c687aca964c123a6"
ORIGINAL_FROM = 1790103525
PHASE2_HASHES = {
    "research/study2/razorpay/RAZORPAY_PHASE2_READONLY_QUALIFICATION_LOCK.md": "4fd765e4c404396eaaab2ef8dc73e8221f0dd63b3da3d385179f5671a49bc18f",
    "research/study2/razorpay/evidence/phase2/direct_fetch.json": "83dd1df9146cb24d9e345886d2181184acee8b646ec7ed83c90e4c9544cabe24",
    "research/study2/razorpay/evidence/phase2/intent.json": "ade787a3d4458cb73747c7bb98a3ec029e53b1e039026f01a569ea0ab69d21df",
    "research/study2/razorpay/evidence/phase2/original_window_observation.json": "2fcc06d94e1524b4fdfcfd6c049539ed23f114b04fd8b71ed796a27a528dd7cc",
    "research/study2/razorpay/evidence/phase2/qualification_plan.json": "799ccb57896c51806d358e82b5de8245f41d870e36783b9992f3e00c5d1d8f59",
    "research/study2/razorpay/evidence/phase2/qualification_result.json": "c853d7de813445d4c93bdc77c12f0a377a0713933275b827ebf141a9485fcf96",
}
SOURCE_PATHS = (
    "src/retry_semantics/serialization.py",
    "src/retry_semantics/study2/razorpay_adapter.py",
    "src/retry_semantics/study2/razorpay_phase2_readonly.py",
    "src/retry_semantics/study2/razorpay_phase3_replay_visibility.py",
    "scripts/qualify_study2_razorpay_phase3.py",
    "tests/test_study2_razorpay_phase3_replay_visibility.py",
    "research/study2/razorpay/RAZORPAY_PHASE3_REPLAY_VISIBILITY_DRAFT.md",
)

QualificationError = p2.QualificationError


class TerminalStatus(str, Enum):
    RESOLVED = "RESOLVED"
    INCONCLUSIVE = "INCONCLUSIVE"
    LOCAL_PREFLIGHT_FAILED = "LOCAL_PREFLIGHT_FAILED"


@dataclass(frozen=True)
class ExecutionOutcome:
    status: TerminalStatus
    reason: str
    multiplicity_result: str
    visibility_result: str
    counts: dict[str, int]


def _json(path: Path) -> dict[str, object]:
    return p2._json_file(path)


def read_frozen_facts(root: Path) -> dict[str, object]:
    """Hash all frozen files, then derive the exact Phase-1 request facts."""
    facts = p2.read_phase1_facts(root)
    for relative, expected in PHASE2_HASHES.items():
        try:
            actual = sha256_hex((root / relative).read_bytes())
        except OSError:
            raise QualificationError("phase2_evidence_unavailable") from None
        if actual != expected:
            raise QualificationError("phase2_evidence_hash_mismatch")
    prefix = root / "research/study2/razorpay/evidence"
    phase1_plan = _json(prefix / "phase1/qualification_plan.json")
    mutation = _json(prefix / "phase1/mutation_1.json").get("adapter_evidence")
    phase2_plan = _json(prefix / "phase2/qualification_plan.json")
    phase2_result = _json(prefix / "phase2/qualification_result.json")
    phase2_observation = _json(prefix / "phase2/original_window_observation.json")
    phase2_fetch = _json(prefix / "phase2/direct_fetch.json")
    observed = phase2_observation.get("adapter_evidence")
    if not (
        type(mutation) is dict and type(observed) is dict
        and facts == {
            "provider_order_id": ORIGINAL_ID, "marker": MARKER,
            "original_from_timestamp": ORIGINAL_FROM,
            "original_to_timestamp": 1790104125,
            "credential_scope_fingerprint": SCOPE_SHA256,
        }
        and phase1_plan.get("transport_profile") == DEFAULT_TRANSPORT_PROFILE
        and phase1_plan.get("timeout_seconds") == TIMEOUT_SECONDS
        and mutation.get("request_body_sha256") == BODY_SHA256
        and mutation.get("request_identity_sha256") == IDENTITY_SHA256
        and mutation.get("credential_scope_fingerprint") == SCOPE_SHA256
        and phase2_plan.get("phase1_evidence_hashes") == p2.PHASE1_HASHES
        and phase2_plan.get("credential_scope_fingerprint") == SCOPE_SHA256
        and phase2_result.get("status") == "RESOLVED"
        and phase2_result.get("reason") == "later_list_visibility_established_under_original_window"
        and observed.get("status") == "structurally_completed_unqualified"
        and observed.get("matching_order_ids") == [ORIGINAL_ID]
        and phase2_observation.get("from_timestamp") == ORIGINAL_FROM
        and phase2_observation.get("to_timestamp") == 1790104125
        and phase2_fetch.get("validation_reason") == "validated"
    ):
        raise QualificationError("frozen_facts_invalid")
    return facts


def _frozen_request(facts: Mapping[str, object]) -> FrozenOrderCreateRequest:
    # The marker, amount, currency, receipt prohibition, timeout and scope all
    # come from verified Phase-1 bytes. The adapter defines canonical framing.
    try:
        request = FrozenOrderCreateRequest(
            provider_candidate="razorpay", operation="create_order", method="POST",
            origin="https://api.razorpay.com", path="/v1/orders",
            content_type="application/json",
            body=canonical_json_bytes({"amount": ORDER_AMOUNT, "currency": ORDER_CURRENCY,
                                       "notes": {MARKER_KEY: facts["marker"]}}),
            marker=facts["marker"], amount=ORDER_AMOUNT, currency=ORDER_CURRENCY,
            credential_scope_fingerprint=facts["credential_scope_fingerprint"],
            timeout_seconds=TIMEOUT_SECONDS, transport_profile=DEFAULT_TRANSPORT_PROFILE,
        )
    except Exception:
        raise QualificationError("frozen_request_invalid") from None
    if request.body_sha256 != BODY_SHA256 or request.identity_sha256 != IDENTITY_SHA256:
        raise QualificationError("frozen_request_hash_mismatch")
    if "receipt" in json.loads(request.body):
        raise QualificationError("frozen_request_receipt_present")
    return request


def read_source_hashes(root: Path) -> dict[str, str]:
    try:
        return {path: sha256_hex((root / path).read_bytes()) for path in SOURCE_PATHS}
    except OSError:
        raise QualificationError("source_file_unavailable") from None


def plan_file_sha256(package_dir: Path) -> str:
    return p2.plan_file_sha256(package_dir)


def _fixed_plan_fields(facts: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema": PLAN_SCHEMA, "phase": 3, "engineering_only": True,
        "paper_observations": 0, "provider_c_selection": "not_performed",
        "provider_candidate": "razorpay", "known_original_order_id": facts["provider_order_id"],
        "marker": facts["marker"], "amount": ORDER_AMOUNT, "currency": ORDER_CURRENCY,
        "receipt": "absent_prohibited", "request_body_sha256": BODY_SHA256,
        "request_identity_sha256": IDENTITY_SHA256,
        "expected_credential_scope_fingerprint": facts["credential_scope_fingerprint"],
        "observation_from": facts["original_from_timestamp"],
        "observation_lower_bound_source": "phase1_original_from",
        "observation_window_rule": "phase1_original_from..execution_anchor_plus_300",
        "page_cap": PAGE_CAP, "visibility_offsets_seconds": list(OFFSETS),
        "maximum_mutation_dispatches": 1, "maximum_post_dispatches": 1,
        "maximum_get_dispatches": MAX_GET_DISPATCHES,
        "mutation_retry": "prohibited", "http_retry": "prohibited",
        "polling_outside_frozen_schedule": "prohibited", "automatic_rerun": "prohibited",
        "cleanup": "prohibited", "ambiguity_injection": "prohibited", "llm_use": "prohibited",
        "authoritative_completeness_qualified": False,
        "phase1_evidence_hashes": dict(sorted(p2.PHASE1_HASHES.items())),
        "phase2_evidence_hashes": dict(sorted(PHASE2_HASHES.items())),
        "transport_profile": DEFAULT_TRANSPORT_PROFILE,
        "timeout_seconds": TIMEOUT_SECONDS,
        "qualification_confirmation": CONFIRMATION,
        "test_mode_operator_confirmation": TEST_MODE_CONFIRMATION,
        "runtime_versions": {"httpx": "0.28.1"},
    }


def prepare_package(
    repository_root: Path, package_dir: Path, *,
    _provenance_reader: Callable = p2.read_git_provenance,
    _source_hash_reader: Callable = read_source_hashes,
    _runtime_reader: Callable = p2.read_runtime_versions,
) -> dict[str, object]:
    root, destination = repository_root.resolve(), package_dir.resolve()
    p2._require_outside_repo(root, destination)
    facts = read_frozen_facts(root)
    _frozen_request(facts)
    provenance = dict(_provenance_reader(root))
    p2._require_provenance(provenance)
    runtime = dict(_runtime_reader())
    if runtime != {"httpx": "0.28.1"}:
        raise QualificationError("runtime_dependency_mismatch")
    qualification_id = str(uuid.uuid4())
    plan = {
        **_fixed_plan_fields(facts), "qualification_id": qualification_id,
        "prepared_utc": p2._utc_now(), "git_head": provenance["git_head"],
        "origin_main": provenance["origin_main"],
        "source_hashes": dict(sorted(_source_hash_reader(root).items())),
        "package_location_sha256": p2._location_hash(qualification_id, destination),
    }
    plan["plan_sha256"] = sha256_hex(canonical_json_bytes(plan))
    try:
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    except FileExistsError:
        raise QualificationError("package_already_exists") from None
    except OSError:
        raise QualificationError("package_create_failed") from None
    p2._write_exclusive_json(destination / PLAN_FILENAME, plan)
    return plan


def _load_plan(destination: Path, expected_hash: str, facts: Mapping[str, object]) -> dict[str, object]:
    if type(expected_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
        raise QualificationError("expected_plan_file_sha256_invalid")
    try:
        raw = (destination / PLAN_FILENAME).read_bytes()
    except OSError:
        raise QualificationError("plan_unavailable_or_invalid") from None
    if sha256_hex(raw) != expected_hash:
        raise QualificationError("plan_file_sha256_mismatch")
    try:
        plan = json.loads(raw)
    except (ValueError, UnicodeError):
        raise QualificationError("plan_unavailable_or_invalid") from None
    if type(plan) is not dict:
        raise QualificationError("plan_unavailable_or_invalid")
    without_hash = dict(plan)
    claimed = without_hash.pop("plan_sha256", None)
    if claimed != sha256_hex(canonical_json_bytes(without_hash)):
        raise QualificationError("plan_hash_mismatch")
    fixed = _fixed_plan_fields(facts)
    if any(plan.get(k) != v or type(plan.get(k)) is not type(v) for k, v in fixed.items()):
        raise QualificationError("plan_invariant_mismatch")
    if set(plan) != set(fixed) | {"qualification_id", "prepared_utc", "git_head", "origin_main", "source_hashes", "package_location_sha256", "plan_sha256"}:
        raise QualificationError("plan_shape_invalid")
    if (type(plan.get("git_head")) is not str
            or re.fullmatch(r"[0-9a-f]{40}", plan["git_head"]) is None
            or plan.get("origin_main") != plan["git_head"]):
        raise QualificationError("plan_git_provenance_invalid")
    if plan.get("package_location_sha256") != p2._location_hash(plan.get("qualification_id"), destination):
        raise QualificationError("package_location_mismatch")
    if type(plan.get("source_hashes")) is not dict or set(plan["source_hashes"]) != set(SOURCE_PATHS):
        raise QualificationError("plan_source_hashes_invalid")
    return plan


def preflight_package(repository_root: Path, package_dir: Path, expected_hash: str, *,
                      _provenance_reader: Callable = p2.read_git_provenance,
                      _source_hash_reader: Callable = read_source_hashes,
                      _runtime_reader: Callable = p2.read_runtime_versions) -> tuple[dict[str, object], dict[str, object]]:
    """Complete local validation before CLI credential prompts or provider traffic."""
    root, destination = repository_root.resolve(), package_dir.resolve()
    p2._require_outside_repo(root, destination)
    if not destination.is_dir():
        raise QualificationError("package_missing")
    # Check the operator-approved raw bytes before parsing any plan content.
    if type(expected_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
        raise QualificationError("expected_plan_file_sha256_invalid")
    if plan_file_sha256(destination) != expected_hash:
        raise QualificationError("plan_file_sha256_mismatch")
    facts = read_frozen_facts(root)
    plan = _load_plan(destination, expected_hash, facts)
    if (destination / INTENT_FILENAME).exists():
        raise QualificationError("package_already_consumed")
    try:
        entries = {entry.name for entry in destination.iterdir()}
    except OSError:
        raise QualificationError("package_unavailable") from None
    if entries != {PLAN_FILENAME}:
        raise QualificationError("package_not_pristine")
    provenance = dict(_provenance_reader(root))
    p2._require_provenance(provenance)
    if provenance["git_head"] != plan["git_head"] or provenance["origin_main"] != plan["origin_main"]:
        raise QualificationError("plan_git_provenance_mismatch")
    if dict(_source_hash_reader(root)) != plan["source_hashes"]:
        raise QualificationError("plan_source_hash_mismatch")
    if dict(_runtime_reader()) != plan["runtime_versions"]:
        raise QualificationError("runtime_dependency_mismatch")
    return plan, facts


def _counts() -> dict[str, int]:
    return dict.fromkeys((
        "baseline_get_dispatches", "direct_fetch_get_dispatches", "visibility_get_dispatches",
        "total_get_dispatches", "mutation_dispatch_attempts", "mutation_dispatches",
        "post_dispatches", "visibility_rounds_attempted", "visibility_rounds_completed",
    ), 0)


def _common(plan: Mapping[str, object], stage: str, counts: Mapping[str, int], synthetic: bool) -> dict[str, object]:
    return {
        "schema": EVIDENCE_SCHEMA, "phase": 3, "stage": stage,
        "recorded_utc": p2._utc_now(), "qualification_id": plan["qualification_id"],
        "plan_sha256": plan["plan_sha256"], "plan_file_sha256": plan["_authorized_file_hash"],
        "package_location_sha256": plan["package_location_sha256"],
        "engineering_only": True, "paper_observations": 0,
        "provider_candidate": "razorpay", "provider_c_selection": "not_performed",
        "synthetic_test_execution": synthetic, "live_qualification_evidence": not synthetic,
        "authoritative_completeness_qualified": False, "counts": dict(counts),
    }


def _terminal(destination: Path, plan: Mapping[str, object], counts: dict[str, int],
              status: TerminalStatus, reason: str, multiplicity: str, visibility: str,
              synthetic: bool, first_offset: int | None = None) -> ExecutionOutcome:
    if (counts["mutation_dispatches"] > 1 or counts["post_dispatches"] > 1
            or counts["total_get_dispatches"] > MAX_GET_DISPATCHES):
        raise QualificationError("dispatch_invariant_violated")
    evidence = _common(plan, "terminal", counts, synthetic)
    evidence.update({"status": status.value, "reason": reason,
                     "multiplicity_result": multiplicity, "visibility_result": visibility,
                     "first_successful_scheduled_offset_seconds": first_offset})
    p2._write_exclusive_json(destination / RESULT_FILENAME, evidence)
    return ExecutionOutcome(status, reason, multiplicity, visibility, dict(counts))


def _observe(adapter: RazorpayOrderAdapter, plan: Mapping[str, object],
             intent: Mapping[str, object], counts: dict[str, int], stage: str,
             synthetic: bool, offset: int | None = None):
    result = adapter.observe_orders(
        marker=plan["marker"], from_timestamp=intent["observation_from"],
        to_timestamp=intent["observation_to"], page_cap=PAGE_CAP,
    )
    key = "baseline_get_dispatches" if stage == "baseline_observation" else "visibility_get_dispatches"
    counts[key] += result.pages_requested
    counts["total_get_dispatches"] += result.pages_requested
    evidence = _common(plan, stage, counts, synthetic)
    evidence.update({
        "observation_from": intent["observation_from"],
        "observation_to": intent["observation_to"],
        "scheduled_offset_seconds": offset,
        "adapter_evidence": result.sanitized_evidence(),
    })
    filename = "baseline_observation.json" if offset is None else f"visibility_round_{offset}.json"
    p2._write_exclusive_json(intent["_destination"] / filename, evidence)
    return result


def _direct_fetch(client: httpx.Client, credentials: RazorpayCredentials,
                  order_id: str, marker: str, counts: dict[str, int]) -> tuple[dict[str, object], bool]:
    # An acknowledged ID is untrusted input: never allow it to alter the GET path.
    evidence: dict[str, object] = {
        "requested_provider_order_id": order_id, "provider_order_id": None,
        "http_status": None, "provider_created_at": None,
        "entity": None, "amount": None, "currency": None,
        "receipt_state": "unavailable", "exact_marker_match": False,
        "credential_scope_fingerprint": credentials.scope_fingerprint,
        "validation_reason": "direct_fetch_not_validated",
    }
    if re.fullmatch(r"order_[A-Za-z0-9]+", order_id) is None:
        evidence["validation_reason"] = "unsafe_order_id"
        return evidence, False
    outbound = client.build_request("GET", f"https://api.razorpay.com/v1/orders/{order_id}",
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
    evidence.update({
        "entity": "order" if value.get("entity") == "order" else "unexpected",
        "amount": value.get("amount") if type(value.get("amount")) is int else None,
        "currency": "INR" if value.get("currency") == "INR" else "unexpected",
        "receipt_state": "absent" if "receipt" not in value else
                         ("null" if value["receipt"] is None else "non_null"),
        "exact_marker_match": type(value.get("notes")) is dict and
                              value["notes"].get(MARKER_KEY) == marker,
    })
    valid = (
        type(value.get("id")) is str and value["id"] == order_id
        and value.get("entity") == "order"
        and type(value.get("amount")) is int and value["amount"] == ORDER_AMOUNT
        and value.get("currency") == ORDER_CURRENCY
        and ("receipt" not in value or value["receipt"] is None)
        and type(value.get("notes")) is dict and value["notes"].get(MARKER_KEY) == marker
        and type(value.get("created_at")) is int and value["created_at"] >= 0
    )
    if valid:
        evidence["provider_order_id"] = order_id
        evidence["provider_created_at"] = value["created_at"]
        evidence["validation_reason"] = "validated"
    return evidence, valid


def execute_package(
    repository_root: Path, package_dir: Path, *,
    execute_live_replay_visibility_qualification: bool,
    confirmation: str, test_mode_operator_confirmation: str,
    plan_file_sha256: str, key_id: str, key_secret: str,
    _provenance_reader: Callable = p2.read_git_provenance,
    _source_hash_reader: Callable = read_source_hashes,
    _runtime_reader: Callable = p2.read_runtime_versions,
    _synthetic_transport: httpx.MockTransport | None = None,
    _wall_clock: Callable[[], float] = time.time,
    _monotonic: Callable[[], float] = time.monotonic,
    _sleep: Callable[[float], None] = time.sleep,
    _synthetic_test_execution: bool = False,
) -> ExecutionOutcome:
    if execute_live_replay_visibility_qualification is not True:
        raise QualificationError("live_replay_visibility_flag_required")
    if confirmation != CONFIRMATION:
        raise QualificationError("confirmation_mismatch")
    if test_mode_operator_confirmation != TEST_MODE_CONFIRMATION:
        raise QualificationError("test_mode_operator_confirmation_required")
    if type(_synthetic_test_execution) is not bool:
        raise QualificationError("synthetic_execution_mode_invalid")
    production_seams = (
        _provenance_reader is p2.read_git_provenance and
        _source_hash_reader is read_source_hashes and
        _runtime_reader is p2.read_runtime_versions and
        _synthetic_transport is None and _wall_clock is time.time and
        _monotonic is time.monotonic and _sleep is time.sleep
    )
    if not _synthetic_test_execution and not production_seams:
        raise QualificationError("production_seam_injection_rejected")
    if _synthetic_test_execution and not isinstance(_synthetic_transport, httpx.MockTransport):
        raise QualificationError("synthetic_mock_transport_required")
    if type(key_id) is str and re.match(r"(?i)^rzp_live(?:_|$)", key_id):
        raise QualificationError("live_looking_key_id_rejected")
    try:
        credentials = RazorpayCredentials(key_id, key_secret)
    except Exception:
        raise QualificationError("credentials_invalid") from None
    root, destination = repository_root.resolve(), package_dir.resolve()
    plan, facts = preflight_package(
        root, destination, plan_file_sha256,
        _provenance_reader=_provenance_reader,
        _source_hash_reader=_source_hash_reader,
        _runtime_reader=_runtime_reader,
    )
    plan["_authorized_file_hash"] = plan_file_sha256
    counts = _counts()
    # Identity is checked before any provider traffic. A mismatch still consumes
    # the package so an operator cannot retry with different credentials.
    preflight_ok = credentials.scope_fingerprint == SCOPE_SHA256
    try:
        frozen = _frozen_request(facts)
    except QualificationError:
        preflight_ok = False
        frozen = None
    anchor_value = _wall_clock()
    if not math.isfinite(anchor_value) or anchor_value < 0:
        raise QualificationError("execution_anchor_invalid")
    execution_anchor = int(anchor_value)
    observation_to = execution_anchor + 300
    if observation_to <= ORIGINAL_FROM:
        raise QualificationError("observation_window_invalid")
    intent = _common(plan, "intent", counts, _synthetic_test_execution)
    intent.update({"session_consumed": True, "execution_started": True,
                   "execution_anchor_unix": execution_anchor,
                   "observation_from": ORIGINAL_FROM, "observation_to": observation_to,
                   "credential_scope_fingerprint": credentials.scope_fingerprint,
                   "maximum_get_dispatches": MAX_GET_DISPATCHES,
                   "maximum_post_dispatches": 1, "maximum_mutation_dispatches": 1})
    # O_EXCL is the one-shot race winner. Durable intent precedes the first GET.
    p2._write_exclusive_json(destination / INTENT_FILENAME, intent)
    if not preflight_ok or frozen is None:
        return _terminal(destination, plan, counts, TerminalStatus.LOCAL_PREFLIGHT_FAILED,
                         "credential_scope_or_request_identity_mismatch", "UNRESOLVED", "NOT_REACHED",
                         _synthetic_test_execution)
    window = {**intent, "_destination": destination}
    adapter = None
    direct_client = None
    multiplicity = "UNRESOLVED"
    visibility = "NOT_REACHED"
    try:
        adapter = RazorpayOrderAdapter(credentials, timeout_seconds=TIMEOUT_SECONDS)
        if _synthetic_test_execution:
            # Private offline seam: retain the production profile and exact
            # frozen identity while replacing only the in-memory transport.
            adapter._client.close()
            adapter._client = httpx.Client(transport=_synthetic_transport,
                                            timeout=httpx.Timeout(TIMEOUT_SECONDS),
                                            follow_redirects=False, trust_env=False)
        transport = _synthetic_transport if _synthetic_test_execution else httpx.HTTPTransport(retries=0)
        direct_client = httpx.Client(transport=transport, timeout=httpx.Timeout(TIMEOUT_SECONDS),
                                     follow_redirects=False, trust_env=False)
        baseline = _observe(adapter, plan, window, counts, "baseline_observation", _synthetic_test_execution)
        if baseline.status is not ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED:
            return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                             "baseline_observation_incomplete", multiplicity, visibility,
                             _synthetic_test_execution)
        ids = set(baseline.matching_order_ids)
        if ids != {ORIGINAL_ID} or baseline.matching_resource_count != 1:
            reason = ("baseline_exact_set_not_observed" if not ids or ORIGINAL_ID not in ids
                      else "baseline_unexpected_additional_match")
            return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                             reason, multiplicity, visibility, _synthetic_test_execution)
        counts["mutation_dispatch_attempts"] = 1
        mutation = adapter.dispatch_create_order(frozen, DispatchPermit())
        if mutation.dispatch_started:
            counts["mutation_dispatches"] = 1
            counts["post_dispatches"] = 1
        ack_monotonic = _monotonic()
        replay = _common(plan, "replay_mutation", counts, _synthetic_test_execution)
        replay.update({"adapter_evidence": mutation.sanitized_evidence(),
                       "marker": MARKER, "request_body_sha256": BODY_SHA256,
                       "request_identity_sha256": IDENTITY_SHA256,
                       "credential_scope_fingerprint": SCOPE_SHA256,
                       "transport_profile": DEFAULT_TRANSPORT_PROFILE})
        p2._write_exclusive_json(destination / "replay_mutation.json", replay)
        if mutation.classification is not MutationClassification.ACKNOWLEDGED_CREATE or not mutation.acknowledgement_valid:
            return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                             "replay_not_acknowledged", multiplicity, visibility,
                             _synthetic_test_execution)
        replay_id = mutation.provider_order_id
        multiplicity = ("SAME_RESOURCE_ID_ACKNOWLEDGED" if replay_id == ORIGINAL_ID
                        else "DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED")
        direct, valid = _direct_fetch(direct_client, credentials, replay_id, MARKER, counts)
        fetch_evidence = _common(plan, "direct_fetch_replay", counts, _synthetic_test_execution)
        fetch_evidence.update(direct)
        p2._write_exclusive_json(destination / "direct_fetch_replay.json", fetch_evidence)
        if not valid:
            return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                             "direct_fetch_not_validated", multiplicity, visibility,
                             _synthetic_test_execution)
        if not (intent["observation_from"] <= direct["provider_created_at"] <= intent["observation_to"]):
            return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                             "replay_created_at_outside_fixed_window", multiplicity, visibility,
                             _synthetic_test_execution)
        expected = {ORIGINAL_ID, replay_id}
        for offset in OFFSETS:
            remaining = ack_monotonic + offset - _monotonic()
            if remaining > 0:
                _sleep(remaining)
            counts["visibility_rounds_attempted"] += 1
            round_result = _observe(adapter, plan, window, counts, f"visibility_round_{offset}",
                                    _synthetic_test_execution, offset)
            if round_result.status is not ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED:
                visibility = "OBSERVATION_INCOMPLETE"
                return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                                 "visibility_observation_incomplete", multiplicity, visibility,
                                 _synthetic_test_execution)
            counts["visibility_rounds_completed"] += 1
            observed = set(round_result.matching_order_ids)
            if multiplicity == "DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED":
                if observed == expected and round_result.matching_resource_count == 2:
                    visibility = "EXACT_TWO_RESOURCE_SET_OBSERVED"
                    return _terminal(destination, plan, counts, TerminalStatus.RESOLVED,
                                     "exact_two_resource_set_observed", multiplicity, visibility,
                                     _synthetic_test_execution, offset)
                if observed == {ORIGINAL_ID} and round_result.matching_resource_count == 1:
                    continue
            else:
                if observed == {ORIGINAL_ID} and round_result.matching_resource_count == 1:
                    continue
            visibility = "UNEXPECTED_OR_NONMONOTONIC_LIST_SET"
            return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                             "unexpected_or_nonmonotonic_list_set", multiplicity, visibility,
                             _synthetic_test_execution)
        if multiplicity == "DISTINCT_SECOND_RESOURCE_ACKNOWLEDGED":
            visibility = "SECOND_RESOURCE_NOT_LIST_OBSERVED_WITHIN_BOUND"
            reason = "second_resource_not_list_observed_within_bound"
        else:
            visibility = "NO_DISTINCT_SECOND_RESOURCE_OBSERVED_UNDER_UNQUALIFIED_LIST"
            reason = "same_id_acknowledgement_inconclusive"
        return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE, reason,
                         multiplicity, visibility, _synthetic_test_execution)
    except QualificationError:
        raise
    except Exception:
        return _terminal(destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                         "qualification_internal_error", multiplicity, visibility,
                         _synthetic_test_execution)
    finally:
        if direct_client is not None:
            direct_client.close()
        if adapter is not None:
            adapter.close()
