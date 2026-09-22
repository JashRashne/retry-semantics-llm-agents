"""Two-stage Stripe TEST/SANDBOX engineering qualification gate.

``prepare`` is offline and creates one immutable package.  ``execute`` is the
only provider-capable path.  It permanently consumes the package before the
single Customer CREATE and observes only after a validated acknowledgement.
This module is engineering control code, not a Study 2 paper protocol.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
from importlib import metadata as importlib_metadata
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable
import uuid

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.stripe_adapter import (
    REVIEWED_STRIPE_API_VERSION,
    MutationDispatchEvidence,
    MutationDisposition,
    StripeAdapterError,
    StripeCustomerAdapter,
    StripeTestCredential,
)


PLAN_SCHEMA = "stripe-live-engineering-qualification-plan-v1"
INTENT_SCHEMA = "stripe-live-engineering-qualification-intent-v1"
MUTATION_RESULT_SCHEMA = "stripe-live-engineering-mutation-result-v1"
OBSERVATION_RESULT_SCHEMA = "stripe-live-engineering-observation-result-v1"
QUALIFICATION_RESULT_SCHEMA = "stripe-live-engineering-qualification-result-v1"
EXECUTE_CONFIRMATION = "EXECUTE_ONE_STRIPE_TEST_CUSTOMER_CREATE"
REVIEWED_HTTPX_VERSION = "0.28.1"
PLAN_FILENAME = "plan.json"
INTENT_FILENAME = "intent.json"
MUTATION_RESULT_FILENAME = "mutation_result.json"
OBSERVATION_RESULT_FILENAME = "observation_result.json"
QUALIFICATION_RESULT_FILENAME = "qualification_result.json"
PACKAGE_FILENAMES = frozenset(
    {
        PLAN_FILENAME,
        INTENT_FILENAME,
        MUTATION_RESULT_FILENAME,
        OBSERVATION_RESULT_FILENAME,
        QUALIFICATION_RESULT_FILENAME,
    }
)
RELEVANT_SOURCE_PATHS = (
    "pyproject.toml",
    "uv.lock",
    "src/retry_semantics/serialization.py",
    "src/retry_semantics/study2/stripe_adapter.py",
    "src/retry_semantics/study2/stripe_live_qualification.py",
    "scripts/qualify_study2_stripe_live.py",
)
_QUALIFICATION_ID = re.compile(r"stripe-eng-[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_GIT_OBJECT_ID = re.compile(r"[0-9a-f]{40,64}")


class StripeLiveQualificationError(RuntimeError):
    """Fixed, non-secret fail-closed control error."""


@dataclass(frozen=True, slots=True)
class PreparedQualification:
    package_dir: Path
    plan_path: Path
    plan_sha256: str
    plan: dict


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StripeLiveQualificationError(message)


def _run_git(repository_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ("git", *args),
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            env={
                "PATH": os.environ.get("PATH", ""),
                "LC_ALL": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise StripeLiveQualificationError("repository provenance check failed") from exc
    return completed.stdout.strip()


def _repository_state(repository_root: Path) -> tuple[str, str, str]:
    root = repository_root.resolve(strict=True)
    _require(_run_git(root, "rev-parse", "--show-toplevel") == str(root), "repository root mismatch")
    head = _run_git(root, "rev-parse", "HEAD")
    origin_main = _run_git(root, "rev-parse", "origin/main")
    full_status = _run_git(root, "status", "--porcelain")
    _require(_GIT_OBJECT_ID.fullmatch(head) is not None, "invalid repository HEAD")
    _require(_GIT_OBJECT_ID.fullmatch(origin_main) is not None, "invalid origin/main")
    return head, origin_main, full_status


def _httpx_runtime_version() -> str:
    try:
        value = importlib_metadata.version("httpx")
    except importlib_metadata.PackageNotFoundError as exc:
        raise StripeLiveQualificationError("reviewed httpx runtime unavailable") from exc
    _require(type(value) is str and bool(value), "invalid httpx runtime version")
    return value


def _source_hashes(repository_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in RELEVANT_SOURCE_PATHS:
        path = repository_root / relative
        _require(path.is_file() and not path.is_symlink(), "relevant source unavailable")
        result[relative] = sha256_hex(path.read_bytes())
    return result


def _idempotency_key(qualification_id: str) -> str:
    return f"retry-semantics-stripe-engineering-v1-{qualification_id}"


def _idempotency_identity(qualification_id: str) -> str:
    return sha256_hex(
        b"stripe-idempotency-key-v1\0" + _idempotency_key(qualification_id).encode("ascii")
    )


def _plan_hash(plan_without_hash: dict) -> str:
    return sha256_hex(canonical_json_bytes(plan_without_hash))


def _plan_without_hash(plan: dict) -> dict:
    return {key: value for key, value in plan.items() if key != "plan_sha256"}


def _validate_plan(plan: object) -> dict:
    _require(type(plan) is dict, "invalid qualification plan")
    required = {
        "schema",
        "qualification_id",
        "engineering_only",
        "paper_observations",
        "provider",
        "environment",
        "operation",
        "authoritative_observation",
        "correlation_email",
        "reviewed_stripe_api_version",
        "reviewed_httpx_version",
        "runtime_httpx_version",
        "idempotency",
        "expected_maximum_post_dispatches",
        "observation_policy",
        "cleanup",
        "mutation_retry",
        "automatic_rerun",
        "ambiguity_injection",
        "git_head",
        "origin_main",
        "source_sha256",
        "created_at",
        "plan_sha256",
    }
    _require(set(plan) == required, "invalid qualification plan fields")
    qualification_id = plan["qualification_id"]
    _require(
        type(qualification_id) is str and _QUALIFICATION_ID.fullmatch(qualification_id) is not None,
        "invalid qualification ID",
    )
    expected_idempotency = {
        "enabled_for_single_engineering_create": True,
        "key_derivation": "qualification-local-engineering-v1",
        "key_identity_sha256": _idempotency_identity(qualification_id),
        "second_post_permitted": False,
        "experiment": False,
    }
    expected_observation = {
        "start_only_after_validated_create_acknowledgement": True,
        "exact_case_sensitive_email_filter": True,
        "exhaustive_starting_after_pagination": True,
        "maximum_sequences": 1,
    }
    _require(plan["schema"] == PLAN_SCHEMA, "invalid plan schema")
    _require(plan["engineering_only"] is True, "engineering-only plan required")
    _require(type(plan["paper_observations"]) is int and plan["paper_observations"] == 0, "paper observations must be zero")
    _require(plan["provider"] == "stripe", "Stripe plan required")
    _require(plan["environment"] == "TEST/SANDBOX", "Stripe TEST/SANDBOX plan required")
    _require(plan["operation"] == "create_customer", "invalid mutation operation")
    _require(plan["authoritative_observation"] == "list_customers", "invalid observation operation")
    _require(plan["correlation_email"] == f"{qualification_id}@retry-semantics.invalid", "invalid correlation email")
    _require(plan["reviewed_stripe_api_version"] == REVIEWED_STRIPE_API_VERSION, "reviewed API version mismatch")
    _require(plan["reviewed_httpx_version"] == REVIEWED_HTTPX_VERSION, "reviewed httpx version mismatch")
    _require(plan["runtime_httpx_version"] == REVIEWED_HTTPX_VERSION, "unreviewed httpx runtime version")
    _require(plan["idempotency"] == expected_idempotency, "invalid engineering idempotency policy")
    _require(type(plan["expected_maximum_post_dispatches"]) is int and plan["expected_maximum_post_dispatches"] == 1, "one POST budget required")
    _require(plan["observation_policy"] == expected_observation, "invalid observation policy")
    _require(plan["cleanup"] == "prohibited", "cleanup must be prohibited")
    _require(plan["mutation_retry"] == "prohibited", "mutation retry must be prohibited")
    _require(plan["automatic_rerun"] == "prohibited", "automatic rerun must be prohibited")
    _require(plan["ambiguity_injection"] == "prohibited", "ambiguity injection must be prohibited")
    _require(type(plan["git_head"]) is str and _GIT_OBJECT_ID.fullmatch(plan["git_head"]) is not None, "invalid plan HEAD")
    _require(type(plan["origin_main"]) is str and _GIT_OBJECT_ID.fullmatch(plan["origin_main"]) is not None, "invalid plan origin/main")
    _require(plan["git_head"] == plan["origin_main"], "plan must bind a pushed checkpoint")
    source_hashes = plan["source_sha256"]
    _require(type(source_hashes) is dict and set(source_hashes) == set(RELEVANT_SOURCE_PATHS), "invalid source hash set")
    _require(all(type(value) is str and _SHA256.fullmatch(value) is not None for value in source_hashes.values()), "invalid source hash")
    _require(type(plan["created_at"]) is str and plan["created_at"].endswith("Z"), "invalid creation timestamp")
    try:
        parsed_created_at = datetime.fromisoformat(plan["created_at"].removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise StripeLiveQualificationError("invalid creation timestamp") from exc
    _require(parsed_created_at.tzinfo == timezone.utc, "UTC creation timestamp required")
    _require(type(plan["plan_sha256"]) is str and _SHA256.fullmatch(plan["plan_sha256"]) is not None, "invalid plan hash")
    _require(plan["plan_sha256"] == _plan_hash(_plan_without_hash(plan)), "plan hash mismatch")
    return plan


def build_plan(
    *,
    qualification_id: str,
    git_head: str,
    origin_main: str,
    source_sha256: dict[str, str],
    created_at: str,
    runtime_httpx_version: str = REVIEWED_HTTPX_VERSION,
) -> dict:
    """Build deterministic plan JSON from already-frozen material."""

    material = {
        "schema": PLAN_SCHEMA,
        "qualification_id": qualification_id,
        "engineering_only": True,
        "paper_observations": 0,
        "provider": "stripe",
        "environment": "TEST/SANDBOX",
        "operation": "create_customer",
        "authoritative_observation": "list_customers",
        "correlation_email": f"{qualification_id}@retry-semantics.invalid",
        "reviewed_stripe_api_version": REVIEWED_STRIPE_API_VERSION,
        "reviewed_httpx_version": REVIEWED_HTTPX_VERSION,
        "runtime_httpx_version": runtime_httpx_version,
        "idempotency": {
            "enabled_for_single_engineering_create": True,
            "key_derivation": "qualification-local-engineering-v1",
            "key_identity_sha256": _idempotency_identity(qualification_id),
            "second_post_permitted": False,
            "experiment": False,
        },
        "expected_maximum_post_dispatches": 1,
        "observation_policy": {
            "start_only_after_validated_create_acknowledgement": True,
            "exact_case_sensitive_email_filter": True,
            "exhaustive_starting_after_pagination": True,
            "maximum_sequences": 1,
        },
        "cleanup": "prohibited",
        "mutation_retry": "prohibited",
        "automatic_rerun": "prohibited",
        "ambiguity_injection": "prohibited",
        "git_head": git_head,
        "origin_main": origin_main,
        "source_sha256": dict(source_sha256),
        "created_at": created_at,
    }
    plan = {**material, "plan_sha256": _plan_hash(material)}
    return _validate_plan(plan)


def _open_directory(path: Path) -> int:
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _fsync_directory(path: Path) -> None:
    fd = _open_directory(path)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_exclusive_json(path: Path, value: dict) -> None:
    data = canonical_json_bytes(value) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            _require(written > 0, "qualification evidence write failed")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_directory(path.parent)


def _load_canonical_json(path: Path) -> dict:
    _require(path.is_file() and not path.is_symlink(), "qualification artifact unavailable")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        data = b""
        while len(data) <= 1_000_000:
            chunk = os.read(fd, min(65_536, 1_000_001 - len(data)))
            if not chunk:
                break
            data += chunk
        _require(len(data) <= 1_000_000, "qualification artifact too large")
    finally:
        os.close(fd)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StripeLiveQualificationError("invalid qualification artifact") from exc
    _require(type(value) is dict and data == canonical_json_bytes(value) + b"\n", "noncanonical qualification artifact")
    return value


def prepare_qualification(
    package_dir: Path,
    *,
    repository_root: Path,
    qualification_id: str | None = None,
    created_at: str | None = None,
) -> PreparedQualification:
    """Create one exclusive offline qualification package."""

    package_dir = Path(package_dir)
    repository_root = Path(repository_root).resolve(strict=True)
    _require(package_dir.is_absolute(), "absolute package directory required")
    _require(
        not package_dir.resolve(strict=False).is_relative_to(repository_root),
        "qualification package must be outside repository",
    )
    _require(not package_dir.exists(), "qualification package already exists")
    head, origin_main, full_status = _repository_state(repository_root)
    _require(full_status == "", "fully clean worktree required")
    _require(head == origin_main, "HEAD must equal pushed origin/main")
    runtime_httpx_version = _httpx_runtime_version()
    _require(runtime_httpx_version == REVIEWED_HTTPX_VERSION, "reviewed httpx runtime required")
    selected_id = qualification_id or f"stripe-eng-{uuid.uuid4().hex}"
    selected_time = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    plan = build_plan(
        qualification_id=selected_id,
        git_head=head,
        origin_main=origin_main,
        source_sha256=_source_hashes(repository_root),
        created_at=selected_time,
        runtime_httpx_version=runtime_httpx_version,
    )
    parent = package_dir.parent
    _require(parent.is_dir() and not parent.is_symlink(), "package parent directory unavailable")
    os.mkdir(package_dir, 0o700)
    _fsync_directory(parent)
    plan_path = package_dir / PLAN_FILENAME
    _write_exclusive_json(plan_path, plan)
    return PreparedQualification(package_dir, plan_path, plan["plan_sha256"], plan)


def _mutation_projection(evidence: MutationDispatchEvidence) -> dict:
    return {
        "schema": MUTATION_RESULT_SCHEMA,
        "engineering_only": True,
        "paper_observations": 0,
        "request_identity_sha256": evidence.request.identity_sha256,
        "request_body_sha256": evidence.request.body_sha256,
        "idempotency_key_identity_sha256": evidence.request.idempotency_key_identity_sha256,
        "credential_fingerprint": evidence.request.credential_fingerprint,
        "correlation_email": evidence.request.correlation_email,
        "api_version": evidence.request.api_version,
        "dispatch_lifecycle": evidence.request.dispatch_lifecycle.value,
        "response_received": evidence.acknowledgement.response_received,
        "status_code": evidence.acknowledgement.status_code,
        "acknowledged_customer_id": evidence.acknowledgement.customer_id,
        "provider_request_id": evidence.acknowledgement.request_id,
        "idempotent_replayed": evidence.acknowledgement.idempotent_replayed,
        "disposition": evidence.disposition.value,
        "remote_outcome": evidence.remote_outcome.value,
        "failure_reason": evidence.failure_reason,
    }


def _interrupted_mutation_projection(prepared) -> dict:
    return {
        "schema": MUTATION_RESULT_SCHEMA,
        "engineering_only": True,
        "paper_observations": 0,
        "request_identity_sha256": prepared.identity_sha256,
        "request_body_sha256": prepared.body_sha256,
        "idempotency_key_identity_sha256": prepared.idempotency_key_identity_sha256,
        "credential_fingerprint": prepared.credential_fingerprint,
        "correlation_email": prepared.correlation_email,
        "api_version": prepared.api_version,
        "dispatch_lifecycle": "dispatch_initiated",
        "response_received": False,
        "status_code": None,
        "acknowledged_customer_id": None,
        "provider_request_id": None,
        "idempotent_replayed": None,
        "disposition": "ambiguous_process_interruption",
        "remote_outcome": "unknown_ambiguous",
        "failure_reason": "exception_after_create_dispatch_boundary_entered",
    }


def _observation_projection(observation) -> dict:
    return {
        "schema": OBSERVATION_RESULT_SCHEMA,
        "engineering_only": True,
        "paper_observations": 0,
        "exact_email": observation.exact_email,
        "page_count": observation.page_count,
        "real_stripe_get_dispatches": observation.request_count,
        "complete": observation.complete,
        "matching_customer_ids": list(observation.matching_customer_ids),
        "matching_resource_count": observation.matching_resource_count,
        "additional_matching_resource_count": observation.additional_matching_resource_count,
        "failure_reason": observation.failure_reason,
        "last_status_code": observation.last_status_code,
        "conclusion": observation.conclusion.value,
    }


def _base_result(plan: dict, credential_fingerprint: str) -> dict:
    return {
        "schema": QUALIFICATION_RESULT_SCHEMA,
        "qualification_id": plan["qualification_id"],
        "plan_sha256": plan["plan_sha256"],
        "engineering_only": True,
        "paper_observations": 0,
        "provider": "stripe",
        "environment": "TEST/SANDBOX",
        "reviewed_stripe_api_version": REVIEWED_STRIPE_API_VERSION,
        "reviewed_httpx_version": plan["reviewed_httpx_version"],
        "runtime_httpx_version": plan["runtime_httpx_version"],
        "git_head": plan["git_head"],
        "origin_main": plan["origin_main"],
        "source_sha256": plan["source_sha256"],
        "credential_fingerprint": credential_fingerprint,
        "request_identity_sha256": None,
        "idempotency_key_identity_sha256": plan["idempotency"]["key_identity_sha256"],
        "provider_request_id": None,
        "idempotent_replayed": None,
        "acknowledged_customer_id": None,
        "acknowledged_customer_livemode": None,
        "observed_customer_ids": [],
        "real_stripe_create_dispatches": 0,
        "acknowledged_create_responses": 0,
        "validated_successful_creates": 0,
        "real_stripe_get_dispatches": 0,
        "complete_observations": 0,
        "matching_resource_count": 0,
        "additional_matching_resource_count": 0,
        "result": "NOT_PASS",
        "failure_reason": None,
    }


def _persist_result_best_effort(package_dir: Path, result: dict) -> None:
    try:
        _write_exclusive_json(package_dir / QUALIFICATION_RESULT_FILENAME, result)
    except Exception:
        pass


def _validate_execution_package(plan_path: Path, expected_plan_sha256: str, repository_root: Path) -> tuple[Path, dict]:
    _require(
        plan_path.is_absolute()
        and ".." not in plan_path.parts
        and plan_path.name == PLAN_FILENAME,
        "exact absolute plan path required",
    )
    _require(type(expected_plan_sha256) is str and _SHA256.fullmatch(expected_plan_sha256) is not None, "exact expected plan hash required")
    package_dir = plan_path.parent
    _require(
        not package_dir.resolve(strict=False).is_relative_to(repository_root),
        "qualification package must be outside repository",
    )
    _require(package_dir.is_dir() and not package_dir.is_symlink(), "qualification package unavailable")
    _require(plan_path.is_file() and not plan_path.is_symlink(), "qualification plan unavailable")
    _require(package_dir.stat().st_mode & 0o077 == 0, "private qualification package required")
    _require(plan_path.stat().st_mode & 0o077 == 0, "private qualification plan required")
    names = {entry.name for entry in package_dir.iterdir()}
    _require(names == {PLAN_FILENAME}, "qualification package already consumed or contains unexpected state")
    plan = _validate_plan(_load_canonical_json(plan_path))
    _require(plan["plan_sha256"] == expected_plan_sha256, "expected plan hash mismatch")
    head, origin_main, full_status = _repository_state(repository_root)
    _require(full_status == "", "fully clean worktree required")
    _require(head == origin_main, "HEAD must equal pushed origin/main")
    _require(head == plan["git_head"], "repository HEAD differs from plan")
    _require(origin_main == plan["origin_main"], "origin/main differs from plan")
    _require(_source_hashes(repository_root) == plan["source_sha256"], "relevant source differs from plan")
    runtime_httpx_version = _httpx_runtime_version()
    _require(runtime_httpx_version == REVIEWED_HTTPX_VERSION, "reviewed httpx runtime required")
    _require(runtime_httpx_version == plan["runtime_httpx_version"], "httpx runtime differs from plan")
    return package_dir, plan


def execute_qualification(
    plan_path: Path,
    *,
    expected_plan_sha256: str,
    execute_live_qualification: bool,
    operator_confirmation: str,
    repository_root: Path,
    credential_reader: Callable[[], str] | None = None,
    adapter_factory: Callable[[StripeTestCredential], StripeCustomerAdapter] | None = None,
) -> dict:
    """Consume and execute exactly one live-capable engineering attempt.

    Tests inject a synthetic credential with ``credential_reader`` and a mock
    transport with ``adapter_factory``.  The production CLI exposes neither.
    """

    _require(execute_live_qualification is True, "explicit live qualification flag required")
    _require(operator_confirmation == EXECUTE_CONFIRMATION, "exact operator confirmation required")
    repository_root = Path(repository_root).resolve(strict=True)
    package_dir, plan = _validate_execution_package(
        Path(plan_path), expected_plan_sha256, repository_root
    )
    reader = credential_reader or (lambda: getpass.getpass("Stripe TEST/SANDBOX secret key: "))
    credential_input_failed = False
    try:
        raw_credential = reader()
    except BaseException:
        raw_credential = None
        credential_input_failed = True
    if credential_input_failed:
        raise StripeLiveQualificationError("Stripe credential input failed")
    try:
        credential = StripeTestCredential(raw_credential)
    except StripeAdapterError:
        raw_credential = None
        raise StripeLiveQualificationError("explicit Stripe TEST/SANDBOX credential required") from None
    raw_credential = None

    factory = adapter_factory or (lambda validated: StripeCustomerAdapter(validated))
    adapter = None
    result = _base_result(plan, credential.fingerprint)
    mutation_persisted = False
    intent_owned = False
    try:
        adapter = factory(credential)
        session = adapter.prepare_customer_create(
            email=plan["correlation_email"],
            idempotency_key=_idempotency_key(plan["qualification_id"]),
        )
        prepared = session.prepared_evidence
        _require(prepared.idempotency_key_identity_sha256 == plan["idempotency"]["key_identity_sha256"], "idempotency identity mismatch")
        intent = {
            "schema": INTENT_SCHEMA,
            "qualification_id": plan["qualification_id"],
            "plan_sha256": plan["plan_sha256"],
            "engineering_only": True,
            "paper_observations": 0,
            "request_identity_sha256": prepared.identity_sha256,
            "request_body_sha256": prepared.body_sha256,
            "correlation_email": prepared.correlation_email,
            "idempotency_key_identity_sha256": prepared.idempotency_key_identity_sha256,
            "credential_fingerprint": prepared.credential_fingerprint,
            "intended_post_dispatch_budget": 1,
            "dispatch_consumed": True,
            "meaning": "create-may-have-committed-never-repeat",
        }
        try:
            _write_exclusive_json(package_dir / INTENT_FILENAME, intent)
        except FileExistsError:
            raise StripeLiveQualificationError(
                "qualification package already consumed"
            ) from None
        intent_owned = True
        result["request_identity_sha256"] = prepared.identity_sha256
        result["real_stripe_create_dispatches"] = 1
        try:
            mutation = session.dispatch()
        except BaseException:
            result["failure_reason"] = "exception_after_create_dispatch_boundary_entered"
            try:
                _write_exclusive_json(
                    package_dir / MUTATION_RESULT_FILENAME,
                    _interrupted_mutation_projection(prepared),
                )
            except Exception:
                pass
            _persist_result_best_effort(package_dir, result)
            return result

        mutation_record = _mutation_projection(mutation)
        result.update(
            acknowledged_create_responses=int(mutation.acknowledgement.response_received),
            validated_successful_creates=int(
                mutation.disposition is MutationDisposition.VALID_CUSTOMER_ACKNOWLEDGEMENT
            ),
            provider_request_id=mutation.acknowledgement.request_id,
            idempotent_replayed=mutation.acknowledgement.idempotent_replayed,
            acknowledged_customer_id=mutation.acknowledgement.customer_id,
            acknowledged_customer_livemode=(
                False
                if mutation.disposition is MutationDisposition.VALID_CUSTOMER_ACKNOWLEDGEMENT
                else None
            ),
        )
        try:
            _write_exclusive_json(package_dir / MUTATION_RESULT_FILENAME, mutation_record)
            mutation_persisted = True
        except Exception:
            result["failure_reason"] = "mutation_evidence_persistence_failed"
            _persist_result_best_effort(package_dir, result)
            return result

        if mutation.disposition is not MutationDisposition.VALID_CUSTOMER_ACKNOWLEDGEMENT:
            result["failure_reason"] = mutation.failure_reason or "create_acknowledgement_not_validated"
            _persist_result_best_effort(package_dir, result)
            return result

        if mutation.acknowledgement.idempotent_replayed is True:
            result["failure_reason"] = "provider_reported_idempotent_replay"
            _persist_result_best_effort(package_dir, result)
            return result

        try:
            observation = adapter.observe_customers(email=plan["correlation_email"])
        except BaseException:
            result["failure_reason"] = "exception_during_observation_sequence"
            _persist_result_best_effort(package_dir, result)
            return result
        observation_record = _observation_projection(observation)
        result.update(
            observed_customer_ids=list(observation.matching_customer_ids),
            real_stripe_get_dispatches=observation.request_count,
            complete_observations=int(observation.complete),
            matching_resource_count=observation.matching_resource_count,
            additional_matching_resource_count=observation.additional_matching_resource_count,
        )
        try:
            _write_exclusive_json(package_dir / OBSERVATION_RESULT_FILENAME, observation_record)
        except Exception:
            result["failure_reason"] = "observation_evidence_persistence_failed"
            _persist_result_best_effort(package_dir, result)
            return result
        acknowledged_id = mutation.acknowledgement.customer_id
        passed = (
            result["real_stripe_create_dispatches"] == 1
            and result["validated_successful_creates"] == 1
            and observation.complete
            and observation.matching_resource_count == 1
            and observation.additional_matching_resource_count == 0
            and observation.matching_customer_ids == (acknowledged_id,)
        )
        if passed:
            result["result"] = "PASS"
        elif not observation.complete:
            result["failure_reason"] = observation.failure_reason or "observation_incomplete"
        elif observation.matching_resource_count != 1:
            result["failure_reason"] = "matching_resource_count_not_one"
        else:
            result["failure_reason"] = "observed_customer_id_mismatch"
        _write_exclusive_json(package_dir / QUALIFICATION_RESULT_FILENAME, result)
        return result
    except StripeLiveQualificationError:
        if intent_owned:
            result["failure_reason"] = result["failure_reason"] or "local_failure_after_attempt_consumed"
            _persist_result_best_effort(package_dir, result)
        raise
    except Exception as exc:
        if intent_owned:
            result["failure_reason"] = "local_failure_after_attempt_consumed"
            _persist_result_best_effort(package_dir, result)
        raise StripeLiveQualificationError("live qualification failed closed") from exc
    finally:
        if adapter is not None:
            try:
                adapter.close()
            except Exception:
                if mutation_persisted:
                    pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stripe TEST/SANDBOX engineering qualification gate")
    parser.add_argument("--repository-root", type=Path, required=True)
    subcommands = parser.add_subparsers(dest="command", required=True)
    prepare = subcommands.add_parser("prepare", help="create an offline qualification plan")
    prepare.add_argument("--package-dir", type=Path, required=True)
    execute = subcommands.add_parser("execute", help="consume one authorized live attempt")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--expected-plan-sha256", required=True)
    execute.add_argument("--execute-live-qualification", action="store_true")
    execute.add_argument("--operator-confirmation", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            prepared = prepare_qualification(
                args.package_dir, repository_root=args.repository_root
            )
            print(f"PLAN_PATH={prepared.plan_path}")
            print(f"PLAN_SHA256={prepared.plan_sha256}")
            print("PROVIDER_CALLS=0")
            return 0
        result = execute_qualification(
            args.plan,
            expected_plan_sha256=args.expected_plan_sha256,
            execute_live_qualification=args.execute_live_qualification,
            operator_confirmation=args.operator_confirmation,
            repository_root=args.repository_root,
        )
        print(f"QUALIFICATION_RESULT={result['result']}")
        return 0 if result["result"] == "PASS" else 1
    except StripeLiveQualificationError as exc:
        print(f"REFUSED: {exc}")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
