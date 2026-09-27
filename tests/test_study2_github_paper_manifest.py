"""Offline adversarial checks for the prospective GitHub paper inputs."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.github_paper_manifest import (
    FAMILY_COUNT,
    IMPLEMENTATION_CHECKPOINT,
    MANIFEST_ID,
    MODEL_AMENDMENT_PATH, MODEL_AMENDMENT_SHA256,
    MANIFEST_PATH,
    REGISTRY_PATH,
    REPOSITORY_ROOT,
    RUN_NAMESPACE,
    SELECTED_REPOSITORY,
    SOURCE_SHA256,
    GitHubPaperManifestError,
    build_github_paper_manifest,
    build_namespace_registry,
    load_github_paper_manifest,
    load_namespace_registry,
)

EXPECTED_REGISTRY_SHA256 = "3da0eecb0699d6fce087fff4c7e6adc9aa362676652522bb748c0a04825785c6"
EXPECTED_MANIFEST_SHA256 = "293d060384ca795cff92fe775bb031021731a6e1da035827db5f763eef5a1e05"


def _isolated_root(destination: Path) -> Path:
    for relative in SOURCE_SHA256:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    for relative in (REGISTRY_PATH, MANIFEST_PATH, MODEL_AMENDMENT_PATH):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return destination


def test_frozen_sources_and_exact_canonical_artifacts() -> None:
    assert IMPLEMENTATION_CHECKPOINT == "ce94954472d60717b82a286e398ac6da83831596"
    assert len(SOURCE_SHA256) == 7
    for relative, expected in SOURCE_SHA256.items():
        assert sha256_hex((REPOSITORY_ROOT / relative).read_bytes()) == expected

    registry = build_namespace_registry()
    manifest = build_github_paper_manifest()
    assert registry.canonical_bytes == build_namespace_registry().canonical_bytes
    assert manifest.canonical_bytes == build_github_paper_manifest().canonical_bytes
    assert registry.canonical_bytes == (REPOSITORY_ROOT / REGISTRY_PATH).read_bytes()
    assert manifest.canonical_bytes == (REPOSITORY_ROOT / MANIFEST_PATH).read_bytes()
    assert registry.canonical_bytes == canonical_json_bytes(registry.as_json())
    assert manifest.canonical_bytes == canonical_json_bytes(manifest.as_json())
    assert registry.sha256 == EXPECTED_REGISTRY_SHA256
    assert manifest.manifest_hash == EXPECTED_MANIFEST_SHA256
    assert load_namespace_registry().canonical_bytes == registry.canonical_bytes
    assert load_github_paper_manifest().canonical_bytes == manifest.canonical_bytes


def test_registry_exact_arm_set_and_collision_proof() -> None:
    registry = load_namespace_registry().as_json()
    assert set(registry) == {
        "schema", "status", "paper_only", "study2_paper_observations",
        "collection_status", "selected_repository", "run_namespace",
        "reservations", "collision_check", "implementation_checkpoint",
        "provenance_sha256", "audit_provenance",
    }
    assert registry["schema"] == "github-paper-namespace-reservation-v1"
    assert registry["status"] == "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"
    assert registry["audit_provenance"] == {
        "audit_status": "PASSED",
        "pre_freeze_canonical_bytes": 66752,
        "pre_freeze_sha256": "35fbd3fd760de1509e566f88cb8e9c66bfce2d9b44d4eee008e87043a0adb398",
        "freeze_scope": "STATUS_PROVENANCE_ONLY_NO_RESERVATION_OR_SCIENTIFIC_CHANGE",
    }
    assert registry["paper_only"] is True
    assert registry["selected_repository"] == SELECTED_REPOSITORY
    assert registry["run_namespace"] == RUN_NAMESPACE
    assert registry["study2_paper_observations"] == 0
    assert registry["collection_status"] == "BLOCKED"
    assert registry["collision_check"] == {
        "arm_ids_unique": True,
        "markers_unique": True,
        "suffixes_unique": True,
        "namespace_unique_among_known_local_registries": True,
        "markers_unique_among_known_local_registries": True,
    }

    rows = registry["reservations"]
    assert len(rows) == 256
    expected_ids = [
        f"gh-f{index:03d}:{world}:{policy}"
        for index in range(1, 65)
        for world in ("H0", "H1")
        for policy in ("EXACT_REPLAY", "LLM_REGENERATION")
    ]
    assert [row["arm_id"] for row in rows] == expected_ids
    markers = []
    suffixes = []
    for row in rows:
        expected_marker = "rs2gh1-" + hashlib.sha256(
            f"{RUN_NAMESPACE}:{row['arm_id']}".encode("utf-8")
        ).hexdigest()[:32]
        expected_suffix = f"\n\n<!-- retry-semantics-study2-gh:v1:{expected_marker} -->"
        assert row["arm_marker"] == expected_marker
        assert row["suffix"] == expected_suffix
        assert row["family_id"] == row["arm_id"].split(":")[0]
        assert row["hidden_world"] == row["arm_id"].split(":")[1]
        assert row["policy"] == row["arm_id"].split(":")[2]
        assert not expected_marker.startswith("ENGINEERING-ONLY-")
        assert not expected_marker.startswith("ENGINEERING-AMBIGUITY-ONLY-")
        markers.append(expected_marker)
        suffixes.append(expected_suffix)
    assert len(set(expected_ids)) == len(set(markers)) == len(set(suffixes)) == 256


def test_manifest_family_hierarchy_schedule_and_model_binding() -> None:
    value = load_github_paper_manifest().as_json()
    catalogue = json.loads((REPOSITORY_ROOT / "research/study2/github/GITHUB_PAPER_FAMILY_CATALOGUE_V1.json").read_text())
    families = value["families"]
    assert value["manifest_id"] == MANIFEST_ID
    assert value["manifest_kind"] == "paper"
    assert value["status"] == "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"
    assert value["audit_provenance"] == {
        "auditor_id": "openai-gpt-5.6-sol-independent-hostile-audit-v2",
        "audited_at_utc": "2026-09-27T12:30:39Z",
        "audit_report_sha256": "76aa91c013ecd2abd64f6b163337f65ddfddaa27218ade9f7cc0fd6aa1ee8cac",
        "audit_receipt_sha256": "237870fa523d98715e7340a4185c1fafaffa54967c4fbf902b81f40321c2596d",
        "audited_scientific_sha256": "771f30220cbd1a5ba11af33604fc11a2f9fb877b3f3422c490ce9e54cae9c87b",
    }
    assert value["model_amendment_sha256"] == MODEL_AMENDMENT_SHA256
    assert value["selected_repository"] == SELECTED_REPOSITORY
    assert value["scope_selected"] is True and value["scope_qualified"] is False
    assert value["run_namespace"] == RUN_NAMESPACE
    assert value["registry_sha256"] == EXPECTED_REGISTRY_SHA256
    assert value["study2_paper_observations"] == 0
    assert value["collection_status"] == "BLOCKED"
    assert value["observation_policy"]["id"] == "OBS-1"
    assert value["observation_policy"]["cross_provider_protocol_sha256"] == SOURCE_SHA256["research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md"]
    assert value["serial_failure_policy"] == {
        "id": "GITHUB_PAPER_MANIFEST_INPUTS_V1_SECTION_6",
        "source_sha256": SOURCE_SHA256["research/study2/github/GITHUB_PAPER_MANIFEST_INPUTS_V1.md"],
    }
    assert value["provider_request_status"] == "W_ARM_REQUIRES_FUTURE_ADAPTER_AND_READINESS_BINDING"
    assert value["schedule_definition"]["replacement"] == "PROHIBITED"
    assert value["schedule_definition"]["refill"] == "PROHIBITED"
    assert len(families) == FAMILY_COUNT
    assert [family["family_id"] for family in families] == [f"gh-f{i:03d}" for i in range(1, 65)]

    strata = Counter()
    first_world = Counter()
    first_policy = Counter()
    positions = Counter()
    all_arms = []
    original_ids = set()
    original_seeds = set()
    regeneration_bases = set()
    for index, (family, source) in enumerate(zip(families, catalogue["families"], strict=True)):
        family_id = family["family_id"]
        assert family["scheduled_attempt_index"] == index
        assert family["target_semantic_m"] == source["semantic_m"]
        assert family["target_semantic_m_sha256"] == sha256_hex(canonical_json_bytes(source["semantic_m"]))
        task = catalogue["task_template"].format(**source["semantic_m"])
        assert family["user_task"] == task
        assert family["user_task_sha256"] == sha256_hex(task.encode("utf-8"))
        assert family["original_generation_id"] == f"original:{family_id}"
        original_ids.add(family["original_generation_id"])

        hidden_bit = (1 + index) % 2
        policy_bit = (1 + index // 2) % 2
        assert family["hidden_world_orientation_bit"] == hidden_bit
        assert family["policy_orientation_bit"] == policy_bit
        hidden_order = ["H0", "H1"] if hidden_bit == 0 else ["H1", "H0"]
        first_order = ["EXACT_REPLAY", "LLM_REGENERATION"] if policy_bit == 0 else ["LLM_REGENERATION", "EXACT_REPLAY"]
        assert family["hidden_world_order"] == hidden_order
        assert family[f"{hidden_order[0].lower()}_policy_order"] == first_order
        assert family[f"{hidden_order[1].lower()}_policy_order"] == first_order[::-1]
        strata[(hidden_bit, policy_bit)] += 1
        first_world[hidden_order[0]] += 1
        for world in ("H0", "H1"):
            first_policy[(world, family[f"{world.lower()}_policy_order"][0])] += 1

        config = family["model_config"]
        assert config["model_config_id"] == f"fireworks-deepseek-v4p1-flash-study2-github-v1-f{index + 1:03d}"
        assert config["model"] == {
            "provider": "fireworks",
            "name": "accounts/fireworks/models/deepseek-v4p1-flash",
            "version_or_digest": None,
        }
        for stage, seed in (("original_generation", 1_000_000 + index), ("regeneration", 2_000_000 + 4 * index)):
            sampling = config[stage]
            assert sampling == {
                "temperature": 0.0,
                "top_p": 1.0,
                "max_output_tokens": 1024,
                "seed": seed,
                "seed_supported": True,
                "tool_choice": {"function_name": None, "mode": "AUTO"},
                "parallel_tool_calls": False,
                "provider_parameters": {"reasoning_effort": "none"},
            }
        original_seeds.add(config["original_generation"]["seed"])
        regeneration_bases.add(config["regeneration"]["seed"])

        assert len(family["arms"]) == 4
        assert [arm["serial_position"] for arm in family["arms"]] == [1, 2, 3, 4]
        assert [arm["hidden_world"] for arm in family["arms"]] == [hidden_order[0]] * 2 + [hidden_order[1]] * 2
        assert {arm["policy"] for arm in family["arms"]} == {"EXACT_REPLAY", "LLM_REGENERATION"}
        for arm in family["arms"]:
            assert arm["original_generation_id"] == family["original_generation_id"]
            assert arm["semantic_m_source_family_id"] == family_id
            assert arm["semantic_m_sha256"] == family["target_semantic_m_sha256"]
            assert arm["arm_id"] == f"{family_id}:{arm['hidden_world']}:{arm['policy']}"
            assert arm["provider_raw_body"] == source["semantic_m"]["body"] + arm["suffix"]
            raw_body = arm["provider_raw_body"].encode("utf-8")
            assert arm["provider_raw_body_utf8_length"] == len(raw_body)
            assert arm["provider_raw_body_sha256"] == sha256_hex(raw_body)
            assert all(token not in task for token in (family_id, arm["arm_id"], arm["arm_marker"], arm["suffix"], RUN_NAMESPACE, "H0", "H1", "EXACT_REPLAY", "LLM_REGENERATION", "OBS-1"))
            positions[(arm["serial_position"], arm["policy"])] += 1
            all_arms.append(arm["arm_id"])

    assert len(original_ids) == len(original_seeds) == len(regeneration_bases) == 64
    assert min(original_seeds) == 1_000_000 and max(original_seeds) == 1_000_063
    assert min(regeneration_bases) == 2_000_000 and max(regeneration_bases) == 2_000_252
    derived = {base + call_index for base in regeneration_bases for call_index in range(4)}
    assert len(derived) == 256 and min(derived) == 2_000_000 and max(derived) == 2_000_255
    assert len(set(all_arms)) == 256
    assert strata == Counter({(h, p): 16 for h in (0, 1) for p in (0, 1)})
    assert first_world == Counter({"H0": 32, "H1": 32})
    assert first_policy == Counter({(w, p): 32 for w in ("H0", "H1") for p in ("EXACT_REPLAY", "LLM_REGENERATION")})
    assert positions == Counter({(position, policy): 32 for position in range(1, 5) for policy in ("EXACT_REPLAY", "LLM_REGENERATION")})


def test_tampering_duplicate_keys_and_local_namespace_reuse_fail_closed(tmp_path: Path) -> None:
    root = _isolated_root(tmp_path)
    registry_path = root / REGISTRY_PATH
    manifest_path = root / MANIFEST_PATH
    original_registry = registry_path.read_bytes()
    original_manifest = manifest_path.read_bytes()

    registry_path.write_bytes(original_registry + b"\n")
    with pytest.raises(GitHubPaperManifestError, match="noncanonical"):
        load_namespace_registry(root)
    registry_path.write_bytes(original_registry.replace(b'"status":"FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"', b'"status":"ALTERED"'))
    with pytest.raises(GitHubPaperManifestError, match="differs"):
        load_namespace_registry(root)
    registry_path.write_bytes(b'{"schema":"a","schema":"b"}')
    with pytest.raises(GitHubPaperManifestError, match="duplicate JSON key"):
        load_namespace_registry(root)
    registry_path.write_bytes(original_registry)

    manifest_path.write_bytes(original_manifest.replace(b'"scope_qualified":false', b'"scope_qualified":true'))
    with pytest.raises(GitHubPaperManifestError, match="differs"):
        load_github_paper_manifest(root)
    manifest_path.write_bytes(original_manifest)

    other = root / "research/study2/github/GITHUB_PAPER_NAMESPACE_RESERVATION_V2.json"
    other.write_bytes(canonical_json_bytes({"run_namespace": "0" * 32, "reservations": []}))
    assert build_namespace_registry(root).canonical_bytes == original_registry
    other.write_bytes(canonical_json_bytes({
        "run_namespace": "0" * 32,
        "reservations": [{"arm_marker": load_namespace_registry(root).as_json()["reservations"][0]["arm_marker"]}],
    }))
    with pytest.raises(GitHubPaperManifestError, match="marker already reserved"):
        build_namespace_registry(root)
    other.write_bytes(canonical_json_bytes({"run_namespace": RUN_NAMESPACE, "reservations": []}))
    with pytest.raises(GitHubPaperManifestError, match="already reserved"):
        build_namespace_registry(root)
    other.unlink()

    source = root / "research/study2/github/GITHUB_PAPER_MANIFEST_INPUTS_V1.md"
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(GitHubPaperManifestError, match="hash mismatch"):
        build_namespace_registry(root)


def test_manifest_carries_no_observed_outcome_or_live_provider_identity() -> None:
    value = load_github_paper_manifest().as_json()
    forbidden = {
        "state_correct", "outcome", "observed_issue_id", "issue_number",
        "repository_numeric_id", "authenticated_principal", "token_scope",
        "current_baseline_count", "current_rate_limit", "credential",
    }

    def visit(item: object) -> None:
        if isinstance(item, dict):
            assert not forbidden.intersection(item)
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    assert value["study2_paper_observations"] == 0
    assert value["collection_status"] == "BLOCKED"
