"""Two-stage, fail-closed Razorpay Test Mode engineering qualification gate.

``prepare`` is purely local.  ``execute`` is single-use and is the only path in
this module that can cross the provider boundary.  This is engineering
qualification infrastructure, not Study 2 paper collection.
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
import time
from typing import Callable, Mapping
import uuid

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.razorpay_adapter import (
    DEFAULT_TRANSPORT_PROFILE,
    DispatchPermit,
    FrozenOrderCreateRequest,
    MutationClassification,
    ObservationResult,
    ObservationStatus,
    RazorpayCredentials,
    RazorpayOrderAdapter,
)


PROVIDER_CANDIDATE = "razorpay"
ENVIRONMENT = "TEST_MODE_ENGINEERING"
CONFIRMATION = "EXECUTE_ONE_RAZORPAY_TEST_ORDER_MULTIPLICITY_QUALIFICATION"
TEST_MODE_CONFIRMATION = "SUPPLIED_CREDENTIALS_ARE_RAZORPAY_TEST_MODE"
PLAN_FILENAME = "qualification_plan.json"
INTENT_FILENAME = "intent.json"
RESULT_FILENAME = "qualification_result.json"
PLAN_SCHEMA = "razorpay-live-engineering-qualification-plan-v1"
EVIDENCE_SCHEMA = "razorpay-live-engineering-qualification-evidence-v1"
PAGE_CAP = 2
WINDOW_PADDING_SECONDS = 300
TIMEOUT_SECONDS = 30.0

FROZEN_HASHES = {
    "research/study2/razorpay/RAZORPAY_SEMANTICS_RECONNAISSANCE.md": (
        "b4acf4dc8a7bdfe150fbe6abe812c3508c18ff27566f219a651bd2e1377cd4ac"
    ),
    "src/retry_semantics/study2/razorpay_adapter.py": (
        "82a974167cc11e3bd4a6a2d504811f479d68e1d18870c0bb987fb18d40e3a325"
    ),
    "tests/test_study2_razorpay_adapter.py": (
        "607999e21211401d7d900b2f7afd13023fc836dc9a4ac954ba5f38ade2847e97"
    ),
    "research/study2/razorpay/RAZORPAY_ADAPTER_ENGINEERING_DRAFT.md": (
        "42e04744a24ba030046041cef271d7f00480b4148cc00d147ade928c1f6097ad"
    ),
}

RELEVANT_SOURCE_PATHS = (
    "scripts/qualify_study2_razorpay_live.py",
    "src/retry_semantics/serialization.py",
    "src/retry_semantics/study2/razorpay_adapter.py",
    "src/retry_semantics/study2/razorpay_live_qualification.py",
)


class QualificationError(RuntimeError):
    """Fixed-text local refusal; arbitrary provider/credential text is discarded."""

    def __init__(self, reason: str = "qualification_refused") -> None:
        if not re.fullmatch(r"[a-z0-9_]{1,96}", reason):
            reason = "qualification_refused"
        self.reason = reason
        super().__init__(reason)


class TerminalStatus(str, Enum):
    PASS = "PASS"
    NON_PASS = "NON_PASS"
    INCONCLUSIVE = "INCONCLUSIVE"
    LOCAL_PREFLIGHT_FAILED = "LOCAL_PREFLIGHT_FAILED"


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    status: TerminalStatus
    reason: str
    mutation_dispatches: int
    baseline_observation_sequences: int
    post_create_observation_sequences: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ("git", "-C", str(root), *arguments),
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        raise QualificationError("git_provenance_unavailable") from None
    return completed.stdout.strip()


def read_git_provenance(repository_root: Path) -> dict[str, object]:
    root = repository_root.resolve()
    dirty = _run_git(root, "status", "--porcelain", "--untracked-files=all")
    head = _run_git(root, "rev-parse", "HEAD")
    origin_main = _run_git(root, "rev-parse", "origin/main")
    return {"clean": dirty == "", "git_head": head, "origin_main": origin_main}


def read_source_hashes(repository_root: Path) -> dict[str, str]:
    root = repository_root.resolve()
    result: dict[str, str] = {}
    for relative in sorted(set(RELEVANT_SOURCE_PATHS) | set(FROZEN_HASHES)):
        path = root / relative
        try:
            result[relative] = sha256_hex(path.read_bytes())
        except OSError:
            raise QualificationError("source_file_unavailable") from None
    return result


def read_runtime_versions() -> dict[str, str]:
    try:
        return {"httpx": importlib.metadata.version("httpx")}
    except importlib.metadata.PackageNotFoundError:
        raise QualificationError("runtime_dependency_unavailable") from None


def _validate_provenance(
    provenance: Mapping[str, object], source_hashes: Mapping[str, str]
) -> None:
    if provenance.get("clean") is not True:
        raise QualificationError("working_tree_not_clean")
    head = provenance.get("git_head")
    if type(head) is not str or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise QualificationError("invalid_git_head")
    if provenance.get("origin_main") != head:
        raise QualificationError("head_origin_main_mismatch")
    for relative, expected in FROZEN_HASHES.items():
        if source_hashes.get(relative) != expected:
            raise QualificationError("frozen_source_hash_mismatch")


def _plan_without_hash(
    *,
    qualification_id: str,
    marker: str,
    provenance: Mapping[str, object],
    source_hashes: Mapping[str, str],
    runtime_versions: Mapping[str, str],
    package_location_sha256: str,
) -> dict[str, object]:
    return {
        "schema": PLAN_SCHEMA,
        "prepared_utc": _utc_now(),
        "qualification_id": qualification_id,
        "marker": marker,
        "engineering_only": True,
        "paper_observations": 0,
        "provider_candidate": PROVIDER_CANDIDATE,
        "provider_c_selection": "not_performed",
        "environment": ENVIRONMENT,
        "amount": 200,
        "currency": "INR",
        "receipt": "prohibited",
        "maximum_mutation_dispatches": 2,
        "baseline_observation_maximum": 1,
        "post_create_observation_maximum": 2,
        "maximum_get_dispatches": 3 * PAGE_CAP,
        "maximum_post_dispatches": 2,
        "observation_page_cap": PAGE_CAP,
        "observation_window_padding_seconds": WINDOW_PADDING_SECONDS,
        "automatic_mutation_retry": "prohibited",
        "automatic_observation_retry_or_polling": "prohibited",
        "ambiguity_injection": "prohibited",
        "replay_regeneration_experiment": "prohibited",
        "cleanup_delete": "unavailable_not_attempted",
        "transport_profile": DEFAULT_TRANSPORT_PROFILE,
        "timeout_seconds": TIMEOUT_SECONDS,
        "qualification_confirmation": CONFIRMATION,
        "test_mode_operator_confirmation": TEST_MODE_CONFIRMATION,
        "git_head": provenance["git_head"],
        "origin_main": provenance["origin_main"],
        "frozen_hashes": dict(sorted(FROZEN_HASHES.items())),
        "source_hashes": dict(sorted(source_hashes.items())),
        "runtime_versions": dict(sorted(runtime_versions.items())),
        "package_location_sha256": package_location_sha256,
    }


def _with_plan_hash(plan_without_hash: Mapping[str, object]) -> dict[str, object]:
    plan = dict(plan_without_hash)
    plan["plan_sha256"] = sha256_hex(canonical_json_bytes(plan_without_hash))
    return plan


def _package_location_sha256(qualification_id: str, package_dir: Path) -> str:
    """Bind a qualification ID to one resolved directory without storing its path."""

    try:
        parsed = uuid.UUID(qualification_id)
    except (TypeError, ValueError, AttributeError):
        raise QualificationError("qualification_id_invalid") from None
    if str(parsed) != qualification_id:
        raise QualificationError("qualification_id_invalid")
    return sha256_hex(
        canonical_json_bytes(
            {
                "qualification_id": qualification_id,
                "resolved_package_directory": str(package_dir.resolve()),
            }
        )
    )


def plan_file_sha256(package_dir: Path) -> str:
    """Hash the exact persisted plan bytes used as the operator anchor."""

    try:
        return sha256_hex((package_dir.resolve() / PLAN_FILENAME).read_bytes())
    except OSError:
        raise QualificationError("plan_unavailable_or_invalid") from None


def _require_outside_repository(repository_root: Path, package_dir: Path) -> None:
    try:
        package_dir.resolve().relative_to(repository_root.resolve())
    except ValueError:
        return
    raise QualificationError("package_must_be_outside_repository")


def _write_exclusive_json(path: Path, value: Mapping[str, object]) -> None:
    data = canonical_json_bytes(dict(value)) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise QualificationError("artifact_already_exists") from None
    except OSError:
        raise QualificationError("artifact_create_failed") from None
    try:
        written = 0
        while written < len(data):
            count = os.write(descriptor, data[written:])
            if count <= 0:
                raise OSError
            written += count
        os.fsync(descriptor)
    except OSError:
        raise QualificationError("artifact_persistence_failed") from None
    finally:
        os.close(descriptor)
    try:
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError:
        raise QualificationError("directory_persistence_failed") from None


def prepare_package(
    repository_root: Path,
    package_dir: Path,
    *,
    _provenance_reader: Callable[[Path], Mapping[str, object]] = read_git_provenance,
    _source_hash_reader: Callable[[Path], Mapping[str, str]] = read_source_hashes,
    _runtime_reader: Callable[[], Mapping[str, str]] = read_runtime_versions,
) -> dict[str, object]:
    """Create a new plan-only package without constructing an HTTP adapter."""

    root = repository_root.resolve()
    destination = package_dir.resolve()
    _require_outside_repository(root, destination)

    provenance = dict(_provenance_reader(root))
    source_hashes = dict(_source_hash_reader(root))
    runtime_versions = dict(_runtime_reader())
    _validate_provenance(provenance, source_hashes)
    if runtime_versions.get("httpx") != "0.28.1":
        raise QualificationError("runtime_dependency_mismatch")

    qualification_id = str(uuid.uuid4())
    marker = f"study2_razorpay_eng_{uuid.uuid4().hex}"
    location_sha256 = _package_location_sha256(qualification_id, destination)
    plan = _with_plan_hash(
        _plan_without_hash(
            qualification_id=qualification_id,
            marker=marker,
            provenance=provenance,
            source_hashes=source_hashes,
            runtime_versions=runtime_versions,
            package_location_sha256=location_sha256,
        )
    )
    try:
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    except FileExistsError:
        raise QualificationError("package_already_exists") from None
    except OSError:
        raise QualificationError("package_create_failed") from None
    _write_exclusive_json(destination / PLAN_FILENAME, plan)
    return plan


def _load_plan(package_dir: Path, expected_file_sha256: str) -> dict[str, object]:
    path = package_dir / PLAN_FILENAME
    if (
        type(expected_file_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", expected_file_sha256) is None
    ):
        raise QualificationError("expected_plan_file_sha256_invalid")
    try:
        raw = path.read_bytes()
    except OSError:
        raise QualificationError("plan_unavailable_or_invalid") from None
    if sha256_hex(raw) != expected_file_sha256:
        raise QualificationError("plan_file_sha256_mismatch")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise QualificationError("plan_unavailable_or_invalid") from None
    if type(value) is not dict:
        raise QualificationError("plan_unavailable_or_invalid")
    claimed = value.get("plan_sha256")
    unhashed = dict(value)
    unhashed.pop("plan_sha256", None)
    if type(claimed) is not str or claimed != sha256_hex(canonical_json_bytes(unhashed)):
        raise QualificationError("plan_hash_mismatch")
    required = {
        "schema": PLAN_SCHEMA,
        "engineering_only": True,
        "paper_observations": 0,
        "provider_candidate": PROVIDER_CANDIDATE,
        "environment": ENVIRONMENT,
        "amount": 200,
        "currency": "INR",
        "receipt": "prohibited",
        "maximum_mutation_dispatches": 2,
        "baseline_observation_maximum": 1,
        "post_create_observation_maximum": 2,
        "maximum_get_dispatches": 3 * PAGE_CAP,
        "maximum_post_dispatches": 2,
        "observation_page_cap": PAGE_CAP,
        "observation_window_padding_seconds": WINDOW_PADDING_SECONDS,
        "automatic_mutation_retry": "prohibited",
        "automatic_observation_retry_or_polling": "prohibited",
        "ambiguity_injection": "prohibited",
        "replay_regeneration_experiment": "prohibited",
        "provider_c_selection": "not_performed",
        "cleanup_delete": "unavailable_not_attempted",
        "transport_profile": DEFAULT_TRANSPORT_PROFILE,
        "timeout_seconds": TIMEOUT_SECONDS,
        "qualification_confirmation": CONFIRMATION,
        "test_mode_operator_confirmation": TEST_MODE_CONFIRMATION,
        "frozen_hashes": dict(sorted(FROZEN_HASHES.items())),
        "runtime_versions": {"httpx": "0.28.1"},
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        raise QualificationError("plan_invariant_mismatch")
    if not re.fullmatch(r"study2_[A-Za-z0-9_-]{1,56}", str(value.get("marker", ""))):
        raise QualificationError("plan_marker_invalid")
    _package_location_sha256(str(value.get("qualification_id", "")), package_dir)
    if value.get("package_location_sha256") != _package_location_sha256(
        value["qualification_id"], package_dir
    ):
        raise QualificationError("package_location_mismatch")
    if type(value.get("source_hashes")) is not dict:
        raise QualificationError("plan_source_hashes_invalid")
    return value


def _validate_execution_preflight(
    root: Path,
    package_dir: Path,
    plan: Mapping[str, object],
    provenance_reader: Callable[[Path], Mapping[str, object]],
    source_hash_reader: Callable[[Path], Mapping[str, str]],
    runtime_reader: Callable[[], Mapping[str, str]],
) -> dict[str, object]:
    if (package_dir / INTENT_FILENAME).exists():
        raise QualificationError("package_already_consumed")
    try:
        entries = {path.name for path in package_dir.iterdir()}
    except OSError:
        raise QualificationError("package_unavailable") from None
    if entries != {PLAN_FILENAME}:
        raise QualificationError("package_not_pristine")
    provenance = dict(provenance_reader(root))
    source_hashes = dict(source_hash_reader(root))
    runtime_versions = dict(runtime_reader())
    _validate_provenance(provenance, source_hashes)
    if provenance["git_head"] != plan.get("git_head"):
        raise QualificationError("plan_git_head_mismatch")
    if provenance["origin_main"] != plan.get("origin_main"):
        raise QualificationError("plan_origin_main_mismatch")
    if source_hashes != plan.get("source_hashes"):
        raise QualificationError("plan_source_hash_mismatch")
    if runtime_versions != plan.get("runtime_versions"):
        raise QualificationError("runtime_dependency_mismatch")
    return provenance


def _common_evidence(
    plan: Mapping[str, object],
    stage: str,
    counts: Mapping[str, int],
    *,
    synthetic_test_execution: bool,
) -> dict[str, object]:
    return {
        "schema": EVIDENCE_SCHEMA,
        "qualification_id": plan["qualification_id"],
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan["_authorized_plan_file_sha256"],
        "package_location_sha256": plan["package_location_sha256"],
        "provider_candidate": PROVIDER_CANDIDATE,
        "engineering_only": True,
        "paper_observations": 0,
        "source_head": plan["git_head"],
        "stage": stage,
        "recorded_utc": _utc_now(),
        "counts": dict(counts),
        "synthetic_test_execution": synthetic_test_execution,
        "live_qualification_evidence": not synthetic_test_execution,
    }


def _observation_window(clock: Callable[[], float]) -> tuple[int, int]:
    center = int(clock())
    return center - WINDOW_PADDING_SECONDS, center + WINDOW_PADDING_SECONDS


def _observation_evidence(
    plan: Mapping[str, object],
    stage: str,
    counts: Mapping[str, int],
    result: ObservationResult,
    window: tuple[int, int],
    *,
    synthetic_test_execution: bool,
) -> dict[str, object]:
    evidence = _common_evidence(
        plan,
        stage,
        counts,
        synthetic_test_execution=synthetic_test_execution,
    )
    evidence.update(
        {
            "from_timestamp": window[0],
            "to_timestamp": window[1],
            "boundary_semantics_qualified": False,
            "total_returned_order_items_encountered": None,
            "total_item_count_unavailable_from_frozen_adapter": True,
            "adapter_evidence": result.sanitized_evidence(),
        }
    )
    return evidence


def _mutation_evidence(
    plan: Mapping[str, object],
    stage: str,
    counts: Mapping[str, int],
    result: object,
    *,
    same_object_as_first: bool,
    synthetic_test_execution: bool,
) -> dict[str, object]:
    evidence = _common_evidence(
        plan,
        stage,
        counts,
        synthetic_test_execution=synthetic_test_execution,
    )
    evidence.update(
        {
            "same_frozen_request_object_as_first": same_object_as_first,
            "adapter_evidence": result.sanitized_evidence(),
        }
    )
    return evidence


def _terminal(
    package_dir: Path,
    plan: Mapping[str, object],
    counts: Mapping[str, int],
    status: TerminalStatus,
    reason: str,
    *,
    synthetic_test_execution: bool,
) -> ExecutionOutcome:
    evidence = _common_evidence(
        plan,
        "terminal",
        counts,
        synthetic_test_execution=synthetic_test_execution,
    )
    evidence.update(
        {
            "status": status.value,
            "reason": reason,
            "authoritative_completeness_qualified": False,
            "provider_c_selection": "not_performed",
        }
    )
    _write_exclusive_json(package_dir / RESULT_FILENAME, evidence)
    return ExecutionOutcome(
        status=status,
        reason=reason,
        mutation_dispatches=counts["mutation_dispatches"],
        baseline_observation_sequences=counts["baseline_observation_sequences"],
        post_create_observation_sequences=counts[
            "post_create_observation_sequences"
        ],
    )


def _reject_live_looking_key_id(key_id: str) -> None:
    if re.match(r"(?i)^rzp_live(?:_|$)", key_id):
        raise QualificationError("live_looking_key_id_rejected")


def execute_package(
    repository_root: Path,
    package_dir: Path,
    *,
    execute_live_qualification: bool,
    confirmation: str,
    test_mode_operator_confirmation: str,
    plan_file_sha256: str,
    key_id: str,
    key_secret: str,
    _provenance_reader: Callable[[Path], Mapping[str, object]] = read_git_provenance,
    _source_hash_reader: Callable[[Path], Mapping[str, str]] = read_source_hashes,
    _runtime_reader: Callable[[], Mapping[str, str]] = read_runtime_versions,
    _test_adapter_factory: Callable[[RazorpayCredentials], object] | None = None,
    _clock: Callable[[], float] = time.time,
    _synthetic_test_execution: bool = False,
) -> ExecutionOutcome:
    """Consume and execute exactly one qualification package.

    ``_test_adapter_factory`` is an offline-only seam.  The production path
    constructs the frozen adapter with its audited default transport profile.
    """

    if execute_live_qualification is not True:
        raise QualificationError("live_execution_flag_required")
    if confirmation != CONFIRMATION:
        raise QualificationError("confirmation_mismatch")
    if test_mode_operator_confirmation != TEST_MODE_CONFIRMATION:
        raise QualificationError("test_mode_operator_confirmation_required")
    if (
        type(plan_file_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", plan_file_sha256) is None
    ):
        raise QualificationError("expected_plan_file_sha256_invalid")
    production_seams = (
        _test_adapter_factory is None
        and _provenance_reader is read_git_provenance
        and _source_hash_reader is read_source_hashes
        and _runtime_reader is read_runtime_versions
        and _clock is time.time
    )
    if _synthetic_test_execution is False and not production_seams:
        raise QualificationError("production_seam_injection_rejected")
    if _synthetic_test_execution is True and _test_adapter_factory is None:
        raise QualificationError("synthetic_adapter_factory_required")
    if type(_synthetic_test_execution) is not bool:
        raise QualificationError("synthetic_execution_mode_invalid")
    _reject_live_looking_key_id(key_id)
    try:
        credentials = RazorpayCredentials(key_id, key_secret)
    except Exception:
        raise QualificationError("credentials_invalid") from None

    root = repository_root.resolve()
    destination = package_dir.resolve()
    _require_outside_repository(root, destination)
    if not destination.is_dir():
        raise QualificationError("package_missing")
    plan = _load_plan(destination, plan_file_sha256)
    plan["_authorized_plan_file_sha256"] = plan_file_sha256
    provenance = _validate_execution_preflight(
        root,
        destination,
        plan,
        _provenance_reader,
        _source_hash_reader,
        _runtime_reader,
    )

    counts = {
        "mutation_dispatch_attempts": 0,
        "mutation_dispatches": 0,
        "baseline_observation_sequences": 0,
        "post_create_observation_sequences": 0,
        "get_dispatches": 0,
    }
    intent = _common_evidence(
        plan,
        "intent",
        counts,
        synthetic_test_execution=_synthetic_test_execution,
    )
    intent.update(
        {
            "session_consumed": True,
            "execution_started": True,
            "marker": plan["marker"],
            "maximum_mutation_dispatches": 2,
            "no_automatic_rerun": True,
            "current_git_head": provenance["git_head"],
            "current_source_hashes": plan["source_hashes"],
        }
    )
    # Atomic O_EXCL acquisition is both the execution lock and irreversible
    # consumption marker.  It is durable before any adapter/provider action.
    _write_exclusive_json(destination / INTENT_FILENAME, intent)

    adapter = None
    try:
        if _test_adapter_factory is None:
            adapter = RazorpayOrderAdapter(credentials, timeout_seconds=TIMEOUT_SECONDS)
        else:
            adapter = _test_adapter_factory(credentials)

        frozen: FrozenOrderCreateRequest = adapter.prepare_create_order(plan["marker"])
        if (
            _synthetic_test_execution
            and frozen.transport_profile == DEFAULT_TRANSPORT_PROFILE
        ):
            return _terminal(
                destination,
                plan,
                counts,
                TerminalStatus.LOCAL_PREFLIGHT_FAILED,
                "synthetic_default_transport_rejected",
                synthetic_test_execution=True,
            )
        if _test_adapter_factory is None and (
            frozen.transport_profile != DEFAULT_TRANSPORT_PROFILE
            or frozen.timeout_seconds != TIMEOUT_SECONDS
        ):
            return _terminal(
                destination,
                plan,
                counts,
                TerminalStatus.LOCAL_PREFLIGHT_FAILED,
                "audited_transport_profile_not_pinned",
                synthetic_test_execution=_synthetic_test_execution,
            )

        counts["baseline_observation_sequences"] = 1
        window = _observation_window(_clock)
        baseline = adapter.observe_orders(
            marker=plan["marker"],
            from_timestamp=window[0],
            to_timestamp=window[1],
            page_cap=PAGE_CAP,
        )
        counts["get_dispatches"] += baseline.pages_requested
        _write_exclusive_json(
            destination / "baseline_observation.json",
            _observation_evidence(
                plan,
                "baseline_observation",
                counts,
                baseline,
                window,
                synthetic_test_execution=_synthetic_test_execution,
            ),
        )
        if baseline.status is not ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED:
            return _terminal(
                destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                "baseline_observation_incomplete",
                synthetic_test_execution=_synthetic_test_execution,
            )
        if set(baseline.matching_order_ids):
            return _terminal(
                destination, plan, counts, TerminalStatus.NON_PASS,
                "baseline_marker_collision",
                synthetic_test_execution=_synthetic_test_execution,
            )

        counts["mutation_dispatch_attempts"] = 1
        first = adapter.dispatch_create_order(frozen, DispatchPermit())
        if first.dispatch_started:
            counts["mutation_dispatches"] += 1
        _write_exclusive_json(
            destination / "mutation_1.json",
            _mutation_evidence(
                plan,
                "mutation_1",
                counts,
                first,
                same_object_as_first=True,
                synthetic_test_execution=_synthetic_test_execution,
            ),
        )
        if first.classification is not MutationClassification.ACKNOWLEDGED_CREATE:
            return _terminal(
                destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                "mutation_1_not_acknowledged",
                synthetic_test_execution=_synthetic_test_execution,
            )
        order_id_1 = first.provider_order_id

        counts["post_create_observation_sequences"] = 1
        window = _observation_window(_clock)
        observation_1 = adapter.observe_orders(
            marker=plan["marker"],
            from_timestamp=window[0],
            to_timestamp=window[1],
            page_cap=PAGE_CAP,
        )
        counts["get_dispatches"] += observation_1.pages_requested
        _write_exclusive_json(
            destination / "observation_1.json",
            _observation_evidence(
                plan,
                "observation_1",
                counts,
                observation_1,
                window,
                synthetic_test_execution=_synthetic_test_execution,
            ),
        )
        if (
            observation_1.status
            is not ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED
            or set(observation_1.matching_order_ids) != {order_id_1}
            or len(observation_1.matching_order_ids) != 1
        ):
            return _terminal(
                destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                "observation_1_exact_set_not_observed",
                synthetic_test_execution=_synthetic_test_execution,
            )

        counts["mutation_dispatch_attempts"] = 2
        second = adapter.dispatch_create_order(frozen, DispatchPermit())
        if second.dispatch_started:
            counts["mutation_dispatches"] += 1
        _write_exclusive_json(
            destination / "mutation_2.json",
            _mutation_evidence(
                plan,
                "mutation_2",
                counts,
                second,
                same_object_as_first=True,
                synthetic_test_execution=_synthetic_test_execution,
            ),
        )
        if second.classification is not MutationClassification.ACKNOWLEDGED_CREATE:
            return _terminal(
                destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                "mutation_2_not_acknowledged",
                synthetic_test_execution=_synthetic_test_execution,
            )
        order_id_2 = second.provider_order_id
        if order_id_2 == order_id_1:
            return _terminal(
                destination, plan, counts, TerminalStatus.NON_PASS,
                "mutation_2_reused_provider_id",
                synthetic_test_execution=_synthetic_test_execution,
            )
        if (
            second.request_identity_sha256 != first.request_identity_sha256
            or second.request_body_sha256 != first.request_body_sha256
        ):
            return _terminal(
                destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                "post_dispatch_request_identity_invariant_failed",
                synthetic_test_execution=_synthetic_test_execution,
            )

        counts["post_create_observation_sequences"] = 2
        window = _observation_window(_clock)
        observation_2 = adapter.observe_orders(
            marker=plan["marker"],
            from_timestamp=window[0],
            to_timestamp=window[1],
            page_cap=PAGE_CAP,
        )
        counts["get_dispatches"] += observation_2.pages_requested
        _write_exclusive_json(
            destination / "observation_2.json",
            _observation_evidence(
                plan,
                "observation_2",
                counts,
                observation_2,
                window,
                synthetic_test_execution=_synthetic_test_execution,
            ),
        )
        expected = {order_id_1, order_id_2}
        actual = set(observation_2.matching_order_ids)
        if observation_2.status is not ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED:
            return _terminal(
                destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                "observation_2_incomplete",
                synthetic_test_execution=_synthetic_test_execution,
            )
        if actual != expected or len(observation_2.matching_order_ids) != 2:
            status = (
                TerminalStatus.NON_PASS
                if len(actual) > 2 or bool(actual - expected)
                else TerminalStatus.INCONCLUSIVE
            )
            return _terminal(
                destination, plan, counts, status,
                "observation_2_exact_set_not_observed",
                synthetic_test_execution=_synthetic_test_execution,
            )
        if (
            counts["mutation_dispatch_attempts"] != 2
            or counts["mutation_dispatches"] != 2
            or counts["baseline_observation_sequences"] != 1
            or counts["post_create_observation_sequences"] != 2
            or not 0 <= counts["get_dispatches"] <= 3 * PAGE_CAP
        ):
            return _terminal(
                destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                "post_dispatch_counter_invariant_failed",
                synthetic_test_execution=_synthetic_test_execution,
            )
        return _terminal(
            destination, plan, counts, TerminalStatus.PASS,
            "controlled_orders_immediately_observed",
            synthetic_test_execution=_synthetic_test_execution,
        )
    except QualificationError:
        raise
    except BaseException:
        # Never persist exception text: transport exceptions can retain requests
        # containing Authorization.
        if not (destination / RESULT_FILENAME).exists():
            return _terminal(
                destination, plan, counts, TerminalStatus.INCONCLUSIVE,
                "unexpected_local_exception",
                synthetic_test_execution=_synthetic_test_execution,
            )
        raise QualificationError("qualification_failed_closed") from None
    finally:
        if adapter is not None:
            try:
                adapter.close()
            except BaseException:
                pass
