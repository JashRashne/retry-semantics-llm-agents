from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace

import pytest

from retry_semantics.experiment import (
    FIREWORKS_DEEPSEEK_PAPER_MANIFEST_ID,
    ManifestProtocolError,
    ScheduleStratum,
    build_fireworks_deepseek_engineering_manifest,
    build_fireworks_deepseek_paper_manifest,
)
from retry_semantics.experiment.paper_manifest import build_paper_manifest, paper_stratum_for
from retry_semantics.models import DEEPSEEK_V4_FLASH_0731_MODEL, ToolChoiceMode
from retry_semantics.runtime.exact_replay import EXACT_REPLAY
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.runtime.regeneration import LLM_REGENERATION
from retry_semantics.serialization import canonical_json_bytes, sha256_hex


@pytest.fixture(scope="module")
def manifest():
    return build_fireworks_deepseek_paper_manifest()


def test_exact_160_slots_and_manifest_id(manifest):
    assert manifest.manifest_id == FIREWORKS_DEEPSEEK_PAPER_MANIFEST_ID == (
        "primary-create-v1.3-fireworks-deepseek-v4-flash-0731-paper-001"
    )
    assert len(manifest.entries) == 160
    assert [entry.scheduled_attempt_index for entry in manifest.entries] == list(range(160))
    assert Counter(entry.replicate for entry in manifest.entries) == Counter({r: 8 for r in range(1, 21)})


@pytest.mark.parametrize("replicate", range(1, 21))
def test_exact_replicate_scenario_order(manifest, replicate):
    entries = manifest.entries[8 * (replicate - 1):8 * replicate]
    canonical = [f"CREATE-{s:03d}" for s in range(1, 9)]
    assert [entry.scenario_id for entry in entries] == (canonical if replicate % 2 else canonical[::-1])
    assert all(entry.replicate == replicate for entry in entries)


def test_global_balance_and_exact_canonical_index_formula(manifest):
    assert Counter(entry.scenario_id for entry in manifest.entries) == Counter(
        {f"CREATE-{s:03d}": 20 for s in range(1, 9)}
    )
    assert Counter(entry.schedule_stratum for entry in manifest.entries) == Counter({s: 40 for s in ScheduleStratum})
    strata = tuple(ScheduleStratum)
    for entry in manifest.entries:
        s = int(entry.scenario_id[-3:]) - 1
        assert entry.schedule_stratum is strata[((entry.replicate - 1) + s) % 4]
    # Even replicate queue position must never substitute for canonical s.
    assert manifest.entries[8].scenario_id == "CREATE-008"
    assert manifest.entries[8].schedule_stratum is ScheduleStratum.A


@pytest.mark.parametrize("scenario_id", [f"CREATE-{s:03d}" for s in range(1, 9)])
def test_per_scenario_stratum_and_constituent_dimensions(manifest, scenario_id):
    entries = [entry for entry in manifest.entries if entry.scenario_id == scenario_id]
    assert Counter(entry.schedule_stratum for entry in entries) == Counter({s: 5 for s in ScheduleStratum})
    assert Counter(entry.plan.hidden_world_order[0] for entry in entries) == Counter({world: 10 for world in HiddenWorld})
    assert Counter(entry.policy_orientation_bit for entry in entries) == Counter({0: 10, 1: 10})
    for world in HiddenWorld:
        assert Counter(entry.plan.arm_order(world)[0] for entry in entries) == Counter({EXACT_REPLAY: 10, LLM_REGENERATION: 10})


def test_stratum_semantics_are_existing_a_b_c_d(manifest):
    expected = {
        ScheduleStratum.A: (HiddenWorld.NOT_EXECUTED, 0),
        ScheduleStratum.B: (HiddenWorld.EXECUTED_ACK_LOST, 1),
        ScheduleStratum.C: (HiddenWorld.NOT_EXECUTED, 1),
        ScheduleStratum.D: (HiddenWorld.EXECUTED_ACK_LOST, 0),
    }
    for entry in manifest.entries:
        assert (entry.plan.hidden_world_order[0], entry.policy_orientation_bit) == expected[entry.schedule_stratum]
        first_world, second_world = entry.plan.hidden_world_order
        expected_first_policy = EXACT_REPLAY if entry.policy_orientation_bit == 0 else LLM_REGENERATION
        assert entry.plan.arm_order(first_world)[0] == expected_first_policy
        assert entry.plan.arm_order(second_world) == entry.plan.arm_order(first_world)[::-1]


def test_exact_seed_config_identity_and_sampling_freeze(manifest):
    for i, entry in enumerate(manifest.entries):
        assert entry.model_config.model_config_id == f"fireworks-deepseek-v4-flash-0731-paper-v1-s{i:03d}"
        assert entry.original_generation_config.seed == 30000 + i
        assert entry.regeneration_config.seed == 40000 + 10 * i
        assert entry.model_config.model.provider == "fireworks"
        assert entry.model_config.model.name == DEEPSEEK_V4_FLASH_0731_MODEL
        assert entry.model_config.model.version_or_digest is None
        for invocation in (entry.model_config.original_generation, entry.model_config.regeneration):
            config = invocation.model_call_config
            assert config.model == DEEPSEEK_V4_FLASH_0731_MODEL
            assert config.temperature == 0.0
            assert config.top_p == 1.0
            assert config.max_completion_tokens == 1024
            assert config.tool_choice.mode is ToolChoiceMode.AUTO
            assert config.parallel_tool_calls is False
            assert invocation.seed_supported is True
            assert config.provider_parameters == {"reasoning_effort": "none"}


def test_no_engineering_seed_overlap_including_derived_calls(manifest):
    engineering = build_fireworks_deepseek_engineering_manifest()
    def seeds(value):
        return {
            seed for entry in value.entries
            for seed in (entry.original_generation_config.seed, *(
                entry.regeneration_config.seed + call_index for call_index in range(4)
            ))
        }
    assert seeds(manifest).isdisjoint(seeds(engineering))
    assert engineering.manifest_hash == "18a128c9ff33997ae1713987bbc3bcde5bf1c597adae8df8970037edcb5c0a7b"


def test_canonical_bytes_hash_and_predata_freeze_provenance(manifest):
    second = build_fireworks_deepseek_paper_manifest()
    assert manifest == second
    assert manifest.canonical_bytes == second.canonical_bytes
    assert manifest.manifest_hash == second.manifest_hash == sha256_hex(manifest.canonical_bytes)
    assert len(manifest.canonical_bytes) == 240807
    assert manifest.manifest_hash == "a707909df1fcfaa99c6834394e74340788dfcf1d62545d25ff89bf6a6418a03c"
    decoded = json.loads(manifest.canonical_bytes)
    assert canonical_json_bytes(decoded) == manifest.canonical_bytes
    assert decoded["manifest_kind"] == "paper"
    assert decoded["paper_experiment_revision"] == "primary-create-v1.3"
    assert decoded["execution_semantics_revision"] == "primary-create-v1.2"
    freeze = decoded["primary_model_freeze"]
    assert freeze["frozen_before_paper_result_collection"] is True
    assert freeze["engineering_gate"]["paper_denominator"] is False
    assert freeze["selection_basis"] == [
        "PROTOCOL_COMPATIBILITY", "SUFFICIENT_FUNCTION_TOOL_CAPABILITY",
        "PRACTICAL_STUDENT_BUDGET", "SEPARATE_ENGINEERING_GATE_PASSED",
    ]


@pytest.mark.parametrize("mutation", ["index", "queue", "stratum", "plan", "duplicate_config"])
def test_invalid_materialization_is_rejected(manifest, mutation):
    with pytest.raises(ManifestProtocolError):
        if mutation == "index":
            replace(manifest.entries[0], scheduled_attempt_index=160)
        elif mutation == "queue":
            replace(manifest.entries[0], replicate=2)
        elif mutation == "stratum":
            replace(manifest.entries[0], schedule_stratum=ScheduleStratum.B)
        elif mutation == "plan":
            replace(manifest.entries[0], plan=manifest.entries[1].plan)
        else:
            duplicate = replace(manifest.entries[1], model_config=manifest.entries[0].model_config)
            replace(manifest, entries=(manifest.entries[0], duplicate, *manifest.entries[2:]))


@pytest.mark.parametrize("replicate", [0, 21, True, 1.0])
def test_invalid_replicate_rejected(replicate):
    with pytest.raises(ManifestProtocolError):
        paper_stratum_for(replicate, "CREATE-001")


def test_short_manifest_configs_rejected(manifest):
    with pytest.raises(ManifestProtocolError, match="160"):
        build_paper_manifest(manifest_id=manifest.manifest_id, slot_model_configs=tuple(
            entry.model_config for entry in manifest.entries[:-1]
        ))


@pytest.mark.parametrize("invocation", ["original_generation", "regeneration"])
def test_changed_paper_seed_namespace_rejected(manifest, invocation):
    entry = manifest.entries[0]
    existing = getattr(entry.model_config, invocation)
    config = replace(existing, model_call_config=replace(existing.model_call_config, seed=1))
    with pytest.raises(ManifestProtocolError, match="seed"):
        replace(entry, model_config=replace(entry.model_config, **{invocation: config}))
