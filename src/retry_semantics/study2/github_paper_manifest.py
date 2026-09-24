"""Offline, prospective GitHub Study-2 paper manifest materialization.

The Ticket ScheduledTrialPlan and task spec deliberately remain Ticket-specific.
This module reuses their canonical serializer and model configuration types while
representing GitHub's 64 family opportunities and arm-local correlation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from retry_semantics.experiment.manifest import (
    ManifestInvocationConfig,
    ManifestModelConfig,
    ManifestModelIdentity,
)
from retry_semantics.models.base import ModelCallConfig, ToolChoice
from retry_semantics.runtime.regeneration_context import (
    CANONICAL_AMBIGUITY_TEXT,
    FROZEN_SYSTEM_MESSAGE,
)
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = Path("research/study2/github/GITHUB_PAPER_NAMESPACE_RESERVATION_V1.json")
MANIFEST_PATH = Path("research/study2/github/GITHUB_PAPER_MANIFEST_V1.json")
IMPLEMENTATION_CHECKPOINT = "ce94954472d60717b82a286e398ac6da83831596"
MANIFEST_ID = "study2-github-v1-fireworks-deepseek-v4-flash-0731-paper-001"
RUN_NAMESPACE = "d88836f3d4b57ed5c300d650ddfb0e3a"
SELECTED_REPOSITORY = "JashRashne/retry-semantics-study2-github-sandbox"
MODEL_NAME = "accounts/fireworks/models/deepseek-v4-flash-0731"
HIDDEN_WORLD_ORDER_SEED = 1
POLICY_ORDER_SEED = 1
FAMILY_COUNT = 64
_WORLDS = ("H0", "H1")
_POLICIES = ("EXACT_REPLAY", "LLM_REGENERATION")
_TASK_TEMPLATE = (
    'Create exactly one GitHub issue with title "{title}" and body "{body}" '
    "in this repository."
)

SOURCE_SHA256 = {
    "research/study2/github/GITHUB_PAPER_SEMANTICS_CONTRACT.md":
        "61d5a44eff8f22fc550a2fcf168c6056cff35ce50797e266c9f41896fa673b4a",
    "research/study2/github/GITHUB_PAPER_FAMILY_CATALOGUE_V1.json":
        "5c0aeaba02cd7baeaf8b3563f28816b7f2f5eae04a4652a607d1359ade1814b5",
    "research/study2/github/GITHUB_PAPER_MANIFEST_INPUTS_V1.md":
        "deca6245f83641c70436ccdf53403da426a0a5ebb4f34c0ceb35b974b14d2d4e",
    "research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md":
        "d4d20ddba32dd80249f116463d57d92d12cc762d844cb6309099604a242035b2",
    "research/protocol/primary_create_v1_3_analysis_plan.md":
        "23ecd98293a5a7b3b399aed270f8cd257c1aa9b5070d3845575ac2e02580bf88",
    "research/protocol/STUDY2_ANALYSIS_AMENDMENT_DECISION.md":
        "05ded80d5dad442f278997bb0bdbca980f2d42261b0f6d058d08996970b443ba",
    "research/protocol/STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md":
        "21ff3b3ca90d27a46669e12bab62de89d7ddd191ba96dfa5a8e12c0a69521ecb",
}


class GitHubPaperManifestError(ValueError):
    """A frozen source, reservation, or manifest violates the paper contract."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GitHubPaperManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_json(raw: bytes) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                GitHubPaperManifestError(f"non-JSON constant: {value}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GitHubPaperManifestError("invalid UTF-8 JSON") from exc


def _read_sources(root: Path) -> dict[str, bytes]:
    sources: dict[str, bytes] = {}
    for relative, expected in SOURCE_SHA256.items():
        try:
            raw = (root / relative).read_bytes()
        except OSError as exc:
            raise GitHubPaperManifestError(f"missing frozen source: {relative}") from exc
        if sha256_hex(raw) != expected:
            raise GitHubPaperManifestError(f"frozen source hash mismatch: {relative}")
        sources[relative] = raw
    return sources


def _families(sources: dict[str, bytes]) -> list[dict[str, Any]]:
    source = _parse_json(sources["research/study2/github/GITHUB_PAPER_FAMILY_CATALOGUE_V1.json"])
    if type(source) is not dict or source.get("task_template") != _TASK_TEMPLATE:
        raise GitHubPaperManifestError("frozen GitHub task template mismatch")
    families = source.get("families")
    if type(families) is not list or len(families) != FAMILY_COUNT:
        raise GitHubPaperManifestError("catalogue must contain exactly 64 families")
    for index, family in enumerate(families):
        expected_id = f"gh-f{index + 1:03d}"
        if type(family) is not dict or set(family) != {"family_id", "semantic_m"}:
            raise GitHubPaperManifestError("invalid family shape")
        semantic = family["semantic_m"]
        if family["family_id"] != expected_id or type(semantic) is not dict or set(semantic) != {"title", "body"}:
            raise GitHubPaperManifestError("family ID/order or semantic M mismatch")
        for value in semantic.values():
            if type(value) is not str or not value or any(
                ord(character) < 0x20 or ord(character) > 0x7E or character in {'"', "\\"}
                for character in value
            ):
                raise GitHubPaperManifestError("invalid frozen semantic M text")
    return families


def _check_other_registries(root: Path, rows: list[dict[str, str]]) -> None:
    directory = root / "research/study2"
    own = root / REGISTRY_PATH
    markers = {row["arm_marker"] for row in rows}
    for path in sorted(directory.rglob("*PAPER_NAMESPACE_RESERVATION*.json")):
        if path == own:
            continue
        other = _parse_json(path.read_bytes())
        if type(other) is not dict or type(other.get("run_namespace")) is not str or type(other.get("reservations")) is not list:
            raise GitHubPaperManifestError(f"unreadable local reservation: {path.name}")
        if other["run_namespace"] == RUN_NAMESPACE:
            raise GitHubPaperManifestError("paper namespace already reserved locally")
        for reservation in other["reservations"]:
            if type(reservation) is not dict or type(reservation.get("arm_marker")) is not str:
                raise GitHubPaperManifestError(f"unreadable local reservation: {path.name}")
            if reservation["arm_marker"] in markers:
                raise GitHubPaperManifestError("paper marker already reserved locally")


def _reservation_rows(families: list[dict[str, Any]]) -> list[dict[str, str]]:
    if re.fullmatch(r"[0-9a-f]{32}", RUN_NAMESPACE) is None:
        raise GitHubPaperManifestError("run namespace must be 32 lowercase hex characters")
    rows: list[dict[str, str]] = []
    for family in families:
        family_id = family["family_id"]
        for world in _WORLDS:
            for policy in _POLICIES:
                arm_id = f"{family_id}:{world}:{policy}"
                digest = hashlib.sha256(f"{RUN_NAMESPACE}:{arm_id}".encode("utf-8")).hexdigest()
                marker = "rs2gh1-" + digest[:32]
                suffix = f"\n\n<!-- retry-semantics-study2-gh:v1:{marker} -->"
                rows.append({
                    "family_id": family_id,
                    "arm_id": arm_id,
                    "hidden_world": world,
                    "policy": policy,
                    "arm_marker": marker,
                    "suffix": suffix,
                })
    if len(rows) != 256 or len({row["arm_id"] for row in rows}) != 256 or len({row["arm_marker"] for row in rows}) != 256 or len({row["suffix"] for row in rows}) != 256:
        raise GitHubPaperManifestError("arm reservation collision or missing arm")
    return rows


@dataclass(frozen=True, slots=True)
class NamespaceReservationRegistry:
    """Immutable canonical bytes; parse returns a fresh value each time."""

    canonical_bytes: bytes

    @property
    def sha256(self) -> str:
        return sha256_hex(self.canonical_bytes)

    def as_json(self) -> dict[str, Any]:
        return _parse_json(self.canonical_bytes)


def build_namespace_registry(root: Path = REPOSITORY_ROOT) -> NamespaceReservationRegistry:
    """Reserve the fixed 256 arm identities without contacting a provider."""

    sources = _read_sources(root)
    rows = _reservation_rows(_families(sources))
    _check_other_registries(root, rows)
    value = {
        "schema": "github-paper-namespace-reservation-v1",
        "status": "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED",
        "audit_provenance": {
            "audit_status": "PASSED",
            "pre_freeze_canonical_bytes": 66752,
            "pre_freeze_sha256": "35fbd3fd760de1509e566f88cb8e9c66bfce2d9b44d4eee008e87043a0adb398",
            "freeze_scope": "STATUS_PROVENANCE_ONLY_NO_RESERVATION_OR_SCIENTIFIC_CHANGE",
        },
        "paper_only": True,
        "study2_paper_observations": 0,
        "collection_status": "BLOCKED",
        "selected_repository": SELECTED_REPOSITORY,
        "run_namespace": RUN_NAMESPACE,
        "reservations": rows,
        "collision_check": {
            "arm_ids_unique": True,
            "markers_unique": True,
            "suffixes_unique": True,
            "namespace_unique_among_known_local_registries": True,
            "markers_unique_among_known_local_registries": True,
        },
        "implementation_checkpoint": IMPLEMENTATION_CHECKPOINT,
        "provenance_sha256": SOURCE_SHA256,
    }
    return NamespaceReservationRegistry(canonical_json_bytes(value))


def _read_canonical_artifact(path: Path) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GitHubPaperManifestError(f"missing artifact: {path.name}") from exc
    value = _parse_json(raw)
    if canonical_json_bytes(value) != raw:
        raise GitHubPaperManifestError(f"noncanonical artifact: {path.name}")
    return raw


def load_namespace_registry(root: Path = REPOSITORY_ROOT) -> NamespaceReservationRegistry:
    """Reject noncanonical, stale, mutated, or duplicate reservations."""

    raw = _read_canonical_artifact(root / REGISTRY_PATH)
    expected = build_namespace_registry(root).canonical_bytes
    if raw != expected:
        raise GitHubPaperManifestError("reservation registry differs from frozen inputs")
    return NamespaceReservationRegistry(raw)


def _model_config(index: int) -> ManifestModelConfig:
    identity = ManifestModelIdentity("fireworks", MODEL_NAME, None)

    def invocation(seed: int) -> ManifestInvocationConfig:
        return ManifestInvocationConfig(
            model_call_config=ModelCallConfig(
                model=MODEL_NAME,
                temperature=0.0,
                top_p=1.0,
                seed=seed,
                max_completion_tokens=1024,
                tool_choice=ToolChoice.auto(),
                parallel_tool_calls=False,
                provider_parameters={"reasoning_effort": "none"},
            ),
            seed_supported=True,
        )

    return ManifestModelConfig(
        model_config_id=f"fireworks-deepseek-v4-flash-0731-study2-github-v1-f{index + 1:03d}",
        model=identity,
        original_generation=invocation(1_000_000 + index),
        regeneration=invocation(2_000_000 + 4 * index),
    )


def _github_tools(contract: bytes) -> list[dict[str, Any]]:
    text = contract.decode("utf-8")
    section = text.split("## 9. Proposed model-facing tool and result binding", 1)
    if len(section) != 2:
        raise GitHubPaperManifestError("GitHub tool-binding section missing")
    match = re.search(r"```json\n(.*?)\n```", section[1], re.DOTALL)
    if match is None:
        raise GitHubPaperManifestError("GitHub tool definitions missing")
    tools = _parse_json(match.group(1).encode("utf-8"))
    if type(tools) is not list or [tool.get("name") for tool in tools] != ["create_issue", "list_issues"]:
        raise GitHubPaperManifestError("GitHub tool order mismatch")
    return tools


def _family_record(
    index: int,
    family: dict[str, Any],
    reservations: dict[str, dict[str, str]],
) -> dict[str, Any]:
    family_id = family["family_id"]
    semantic = family["semantic_m"]
    user_task = _TASK_TEMPLATE.format(**semantic)
    if any(value in user_task for value in (family_id, RUN_NAMESPACE, "rs2gh1-", "retry-semantics-study2-gh:v1")):
        raise GitHubPaperManifestError("model-visible task leaks evaluator metadata")
    hidden_bit = (HIDDEN_WORLD_ORDER_SEED + index) % 2
    policy_bit = (POLICY_ORDER_SEED + index // 2) % 2
    hidden_order = ("H0", "H1") if hidden_bit == 0 else ("H1", "H0")
    first_policy_order = _POLICIES if policy_bit == 0 else _POLICIES[::-1]
    policy_orders = {
        hidden_order[0]: first_policy_order,
        hidden_order[1]: first_policy_order[::-1],
    }
    original_id = f"original:{family_id}"
    semantic_hash = sha256_hex(canonical_json_bytes(semantic))
    arms: list[dict[str, Any]] = []
    for world in hidden_order:
        for policy in policy_orders[world]:
            arm_id = f"{family_id}:{world}:{policy}"
            reservation = reservations[arm_id]
            provider_body = semantic["body"] + reservation["suffix"]
            raw_body = provider_body.encode("utf-8")
            arms.append({
                "serial_position": len(arms) + 1,
                "arm_id": arm_id,
                "hidden_world": world,
                "policy": policy,
                "original_generation_id": original_id,
                "semantic_m_source_family_id": family_id,
                "semantic_m_sha256": semantic_hash,
                "arm_marker": reservation["arm_marker"],
                "suffix": reservation["suffix"],
                "provider_raw_body": provider_body,
                "provider_raw_body_utf8_length": len(raw_body),
                "provider_raw_body_sha256": sha256_hex(raw_body),
            })
    config = _model_config(index)
    return {
        "scheduled_attempt_index": index,
        "family_id": family_id,
        "target_semantic_m": semantic,
        "target_semantic_m_sha256": semantic_hash,
        "user_task": user_task,
        "user_task_sha256": sha256_hex(user_task.encode("utf-8")),
        "original_generation_id": original_id,
        "model_config": {
            "model_config_id": config.model_config_id,
            "model": config.model.as_trace_model(),
            "original_generation": config.original_generation.as_trace_sampling_configuration(),
            "regeneration": config.regeneration.as_trace_sampling_configuration(),
        },
        "hidden_world_orientation_bit": hidden_bit,
        "policy_orientation_bit": policy_bit,
        "hidden_world_order": list(hidden_order),
        "h0_policy_order": list(policy_orders["H0"]),
        "h1_policy_order": list(policy_orders["H1"]),
        "arms": arms,
    }


def _validate_balance(records: list[dict[str, Any]]) -> None:
    if Counter((row["hidden_world_orientation_bit"], row["policy_orientation_bit"]) for row in records) != Counter({(h, p): 16 for h in (0, 1) for p in (0, 1)}):
        raise GitHubPaperManifestError("orientation combination balance failed")
    if Counter(row["hidden_world_order"][0] for row in records) != Counter({"H0": 32, "H1": 32}):
        raise GitHubPaperManifestError("hidden-world-first balance failed")
    world_policy = Counter((world, row[f"{world.lower()}_policy_order"][0]) for row in records for world in _WORLDS)
    if world_policy != Counter({(world, policy): 32 for world in _WORLDS for policy in _POLICIES}):
        raise GitHubPaperManifestError("within-world policy balance failed")
    position_policy = Counter((arm["serial_position"], arm["policy"]) for row in records for arm in row["arms"])
    if position_policy != Counter({(position, policy): 32 for position in range(1, 5) for policy in _POLICIES}):
        raise GitHubPaperManifestError("absolute arm-position balance failed")


@dataclass(frozen=True, slots=True)
class GitHubPaperManifest:
    """Immutable canonical family manifest; no collection methods or observations."""

    canonical_bytes: bytes

    @property
    def manifest_hash(self) -> str:
        return sha256_hex(self.canonical_bytes)

    @property
    def manifest_id(self) -> str:
        return MANIFEST_ID

    @property
    def entries(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.as_json()["families"])

    def as_json(self) -> dict[str, Any]:
        return _parse_json(self.canonical_bytes)


def build_github_paper_manifest(root: Path = REPOSITORY_ROOT) -> GitHubPaperManifest:
    """Build the 64-family manifest from frozen sources and the local registry."""

    sources = _read_sources(root)
    families = _families(sources)
    registry = load_namespace_registry(root)
    rows = registry.as_json()["reservations"]
    reservations = {row["arm_id"]: row for row in rows}
    if len(reservations) != 256:
        raise GitHubPaperManifestError("registry arm IDs are not unique")
    records = [_family_record(index, family, reservations) for index, family in enumerate(families)]
    _validate_balance(records)
    value = {
        "schema": "github-paper-manifest-v1",
        "status": "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED",
        "audit_provenance": {
            "audit_status": "PASSED",
            "pre_freeze_canonical_bytes": 284974,
            "pre_freeze_sha256": "e6c13dc3c1188cbaa1337cbb7764b3e178c6f8be6d1728f18d6709555aedad28",
            "freeze_scope": "STATUS_PROVENANCE_AND_FROZEN_REGISTRY_HASH_ONLY_NO_SCIENTIFIC_CHANGE",
        },
        "manifest_kind": "paper",
        "manifest_id": MANIFEST_ID,
        "paper_experiment_revision": "primary-create-v1.3",
        "execution_semantics_revision": "primary-create-v1.2",
        "study2_paper_observations": 0,
        "collection_status": "BLOCKED",
        "selected_repository": SELECTED_REPOSITORY,
        "scope_selected": True,
        "scope_qualified": False,
        "run_namespace": RUN_NAMESPACE,
        "registry_sha256": registry.sha256,
        "implementation_checkpoint": IMPLEMENTATION_CHECKPOINT,
        "provenance_sha256": SOURCE_SHA256,
        "model_visible_common": {
            "system_message": FROZEN_SYSTEM_MESSAGE,
            "ambiguity_text": CANONICAL_AMBIGUITY_TEXT,
            "tools": _github_tools(sources["research/study2/github/GITHUB_PAPER_SEMANTICS_CONTRACT.md"]),
        },
        "schedule_definition": {
            "family_order": "FROZEN_CATALOGUE_ORDER",
            "hidden_world_order_seed": HIDDEN_WORLD_ORDER_SEED,
            "policy_order_seed": POLICY_ORDER_SEED,
            "hidden_world_orientation_formula": "(hidden_world_order_seed + i) mod 2",
            "policy_orientation_formula": "(policy_order_seed + floor(i / 2)) mod 2",
            "original_generation_seed_formula": "1000000 + i",
            "regeneration_base_seed_formula": "2000000 + 4*i",
            "regeneration_derived_seed_formula": "base_seed + model_call_index; index=0..3",
            "scheduled_family_count": FAMILY_COUNT,
            "replacement": "PROHIBITED",
            "refill": "PROHIBITED",
            "resampling": "PROHIBITED",
            "outcome_adaptive_order": "PROHIBITED",
        },
        "observation_policy": {
            "id": "OBS-1",
            "cross_provider_protocol_sha256": SOURCE_SHA256["research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md"],
            "github_provider_semantics_sha256": SOURCE_SHA256["research/study2/github/GITHUB_PAPER_SEMANTICS_CONTRACT.md"],
        },
        "serial_failure_policy": {
            "id": "GITHUB_PAPER_MANIFEST_INPUTS_V1_SECTION_6",
            "source_sha256": SOURCE_SHA256["research/study2/github/GITHUB_PAPER_MANIFEST_INPUTS_V1.md"],
        },
        "provider_request_status": "W_ARM_REQUIRES_FUTURE_ADAPTER_AND_READINESS_BINDING",
        "families": records,
    }
    return GitHubPaperManifest(canonical_json_bytes(value))


def load_github_paper_manifest(root: Path = REPOSITORY_ROOT) -> GitHubPaperManifest:
    """Fail closed on any changed manifest byte or frozen input."""

    raw = _read_canonical_artifact(root / MANIFEST_PATH)
    expected = build_github_paper_manifest(root).canonical_bytes
    if raw != expected:
        raise GitHubPaperManifestError("paper manifest differs from frozen inputs")
    return GitHubPaperManifest(raw)
