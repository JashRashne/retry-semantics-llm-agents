from __future__ import annotations

import json
from collections import Counter

import httpx

from retry_semantics.experiment import (
    ENGINEERING_SLOT_COUNT,
    FIREWORKS_DEEPSEEK_ENGINEERING_CONFIG_ID_PREFIX,
    FIREWORKS_DEEPSEEK_ENGINEERING_MANIFEST_ID,
    ScheduleStratum,
    build_fireworks_deepseek_engineering_manifest,
    validate_manifest_provider,
)
from retry_semantics.models import (
    DEEPSEEK_V4_FLASH_0731_MODEL,
    FIREWORKS_PROVIDER,
    FireworksModelClient,
    ToolChoiceMode,
)
from retry_semantics.runtime.exact_replay import EXACT_REPLAY
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.runtime.regeneration import LLM_REGENERATION

EXPECTED_SCENARIOS = (
    "CREATE-001",
    "CREATE-002",
    "CREATE-003",
    "CREATE-004",
    "CREATE-005",
    "CREATE-006",
    "CREATE-007",
    "CREATE-008",
    "CREATE-008",
    "CREATE-007",
    "CREATE-006",
    "CREATE-005",
    "CREATE-004",
    "CREATE-003",
    "CREATE-002",
    "CREATE-001",
)


def test_candidate_manifest_has_exact_fireworks_identity_and_configs() -> None:
    manifest = build_fireworks_deepseek_engineering_manifest()

    assert manifest.manifest_id == FIREWORKS_DEEPSEEK_ENGINEERING_MANIFEST_ID
    assert manifest.manifest_id == (
        "primary-create-v1.2-fireworks-deepseek-v4-flash-0731-eng-001"
    )
    assert len(manifest.entries) == ENGINEERING_SLOT_COUNT == 16
    for index, entry in enumerate(manifest.entries):
        assert entry.model_config.model_config_id == (
            f"{FIREWORKS_DEEPSEEK_ENGINEERING_CONFIG_ID_PREFIX}{index:02d}"
        )
        assert entry.model_config.model.provider == FIREWORKS_PROVIDER
        assert entry.model_config.model.name == DEEPSEEK_V4_FLASH_0731_MODEL
        assert entry.model_config.model.version_or_digest is None
        for invocation in (
            entry.model_config.original_generation,
            entry.model_config.regeneration,
        ):
            config = invocation.model_call_config
            assert config.model == DEEPSEEK_V4_FLASH_0731_MODEL
            assert config.temperature == 0.0
            assert config.top_p == 1.0
            assert config.max_completion_tokens == 1024
            assert config.tool_choice.mode is ToolChoiceMode.AUTO
            assert config.parallel_tool_calls is False
            assert config.provider_parameters == {"reasoning_effort": "none"}
            assert invocation.seed_supported is True
        assert entry.original_generation_config.seed == 10_000 + index
        assert entry.regeneration_config.seed == 20_000 + 10 * index


def test_candidate_uses_unchanged_frozen_schedule_and_balance() -> None:
    manifest = build_fireworks_deepseek_engineering_manifest()

    assert tuple(entry.scenario_id for entry in manifest.entries) == (
        EXPECTED_SCENARIOS
    )
    assert tuple(entry.replicate for entry in manifest.entries) == (
        (1,) * 8 + (2,) * 8
    )
    assert Counter(entry.schedule_stratum for entry in manifest.entries) == Counter(
        {stratum: 4 for stratum in ScheduleStratum}
    )
    assert Counter(
        entry.plan.hidden_world_order[0] for entry in manifest.entries
    ) == Counter(
        {
            HiddenWorld.NOT_EXECUTED: 8,
            HiddenWorld.EXECUTED_ACK_LOST: 8,
        }
    )
    for hidden_world in HiddenWorld:
        assert Counter(
            entry.plan.arm_order(hidden_world)[0] for entry in manifest.entries
        ) == Counter({EXACT_REPLAY: 8, LLM_REGENERATION: 8})


def test_candidate_serialization_and_hash_are_deterministic() -> None:
    first = build_fireworks_deepseek_engineering_manifest()
    second = build_fireworks_deepseek_engineering_manifest()

    assert first == second
    assert first.canonical_bytes == second.canonical_bytes
    assert first.manifest_hash == second.manifest_hash
    assert len(first.manifest_hash) == 64
    decoded = json.loads(first.canonical_bytes)
    assert decoded["experiment_version"] == "primary-create-v1.2"
    assert decoded["manifest_kind"] == "engineering_validation"
    assert decoded["manifest_id"] == FIREWORKS_DEEPSEEK_ENGINEERING_MANIFEST_ID


def test_fireworks_client_passes_provider_preflight_without_http() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise AssertionError("provider preflight must not make an HTTP request")

    manifest = build_fireworks_deepseek_engineering_manifest()
    client = FireworksModelClient(
        api_key="offline-test-credential",
        transport=httpx.MockTransport(handler),
    )

    assert validate_manifest_provider(manifest, client) == FIREWORKS_PROVIDER
    assert attempts == 0
