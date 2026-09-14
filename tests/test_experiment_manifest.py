from __future__ import annotations

import json
from collections import Counter
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import MappingProxyType

import pytest

import retry_semantics.runtime.scheduled_trial as scheduled_trial_module
from retry_semantics.environments.ticket import TicketEnvironment
from retry_semantics.experiment import (
    ENGINEERING_SLOT_COUNT,
    EXPERIMENT_VERSION,
    HIDDEN_WORLD_ORDER_SEED,
    POLICY_ORDER_SEED,
    EngineeringManifestEntry,
    EngineeringValidationManifest,
    ManifestInvocationConfig,
    ManifestModelConfig,
    ManifestModelIdentity,
    ManifestProtocolError,
    ScheduleStratum,
    build_engineering_validation_manifest,
    get_scenario,
    hidden_world_order_for_index,
    policy_orientation_bit_for_scenario,
    validate_catalog_task,
)
from retry_semantics.models import (
    ModelCallConfig,
    ModelClient,
    ModelRequestError,
    ToolChoice,
    build_groq_chat_completion_kwargs,
)
from retry_semantics.runtime.exact_replay import EXACT_REPLAY
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.runtime.original_generation import (
    build_v1_original_generation_request,
)
from retry_semantics.runtime.regeneration import LLM_REGENERATION
from retry_semantics.runtime.scheduled_trial import ScheduledTrialPlan

H0 = HiddenWorld.NOT_EXECUTED
H1 = HiddenWorld.EXECUTED_ACK_LOST
REPLAY_FIRST = (EXACT_REPLAY, LLM_REGENERATION)
REGENERATION_FIRST = (LLM_REGENERATION, EXACT_REPLAY)
MANIFEST_ID = "engineering-validation-test"
TRACE_SCHEMA_PATH = (
    Path(__file__).parents[1] / "research" / "protocol" / "trace_schema_v1.json"
)

EXPECTED_SCHEDULE = (
    (0, 1, "CREATE-001", (H0, H1), 0, 0, REPLAY_FIRST, REGENERATION_FIRST, "A"),
    (1, 1, "CREATE-002", (H1, H0), 1, 1, REPLAY_FIRST, REGENERATION_FIRST, "B"),
    (2, 1, "CREATE-003", (H0, H1), 0, 0, REPLAY_FIRST, REGENERATION_FIRST, "A"),
    (3, 1, "CREATE-004", (H1, H0), 1, 1, REPLAY_FIRST, REGENERATION_FIRST, "B"),
    (4, 1, "CREATE-005", (H0, H1), 0, 0, REPLAY_FIRST, REGENERATION_FIRST, "A"),
    (5, 1, "CREATE-006", (H1, H0), 1, 1, REPLAY_FIRST, REGENERATION_FIRST, "B"),
    (6, 1, "CREATE-007", (H0, H1), 0, 0, REPLAY_FIRST, REGENERATION_FIRST, "A"),
    (7, 1, "CREATE-008", (H1, H0), 1, 1, REPLAY_FIRST, REGENERATION_FIRST, "B"),
    (8, 2, "CREATE-008", (H0, H1), 0, 1, REGENERATION_FIRST, REPLAY_FIRST, "C"),
    (9, 2, "CREATE-007", (H1, H0), 1, 0, REGENERATION_FIRST, REPLAY_FIRST, "D"),
    (10, 2, "CREATE-006", (H0, H1), 0, 1, REGENERATION_FIRST, REPLAY_FIRST, "C"),
    (11, 2, "CREATE-005", (H1, H0), 1, 0, REGENERATION_FIRST, REPLAY_FIRST, "D"),
    (12, 2, "CREATE-004", (H0, H1), 0, 1, REGENERATION_FIRST, REPLAY_FIRST, "C"),
    (13, 2, "CREATE-003", (H1, H0), 1, 0, REGENERATION_FIRST, REPLAY_FIRST, "D"),
    (14, 2, "CREATE-002", (H0, H1), 0, 1, REGENERATION_FIRST, REPLAY_FIRST, "C"),
    (15, 2, "CREATE-001", (H1, H0), 1, 0, REGENERATION_FIRST, REPLAY_FIRST, "D"),
)


def _call_config(
    *,
    model: str,
    temperature: float,
    seed: int | None,
    max_output_tokens: int | None = 256,
    tool_choice: ToolChoice | None = None,
    top_p: float | None = None,
    parallel_tool_calls: bool | None = None,
    provider_parameters: object | None = None,
) -> ModelCallConfig:
    return ModelCallConfig(
        model=model,
        temperature=temperature,
        seed=seed,
        max_completion_tokens=max_output_tokens,
        tool_choice=ToolChoice.auto() if tool_choice is None else tool_choice,
        top_p=top_p,
        parallel_tool_calls=parallel_tool_calls,
        provider_parameters={} if provider_parameters is None else provider_parameters,
    )


def _invocation_config(
    *,
    model: str,
    temperature: float,
    seed: int | None,
    top_p: float = 0.9,
    max_output_tokens: int | None = 256,
    seed_supported: bool = True,
    parallel_tool_calls: bool | None = False,
    provider_parameters: object | None = None,
    tool_choice: ToolChoice | None = None,
) -> ManifestInvocationConfig:
    return ManifestInvocationConfig(
        model_call_config=_call_config(
            model=model,
            temperature=temperature,
            seed=seed,
            max_output_tokens=max_output_tokens,
            tool_choice=tool_choice,
            top_p=top_p,
            parallel_tool_calls=parallel_tool_calls,
            provider_parameters=provider_parameters,
        ),
        seed_supported=seed_supported,
    )


def _slot_configs(
    *,
    provider: str = "provider-neutral",
    model: str = "caller-model",
    version_or_digest: str | None = "caller-version-v1",
    temperature: float = 0.25,
    top_p: float = 0.9,
    max_output_tokens: int | None = 256,
    original_seed_offset: int | None = 10_000,
    regeneration_seed_offset: int | None = 20_000,
    seed_supported: bool = True,
    parallel_tool_calls: bool | None = False,
    provider_parameters: object | None = None,
    model_config_id_prefix: str = "explicit-config",
) -> tuple[ManifestModelConfig, ...]:
    def seed(offset: int | None, index: int) -> int | None:
        return None if offset is None else offset + index

    return tuple(
        ManifestModelConfig(
            model_config_id=f"{model_config_id_prefix}-{index:02d}",
            model=ManifestModelIdentity(
                provider=provider,
                name=model,
                version_or_digest=version_or_digest,
            ),
            original_generation=_invocation_config(
                model=model,
                temperature=temperature,
                seed=seed(original_seed_offset, index),
                top_p=top_p,
                max_output_tokens=max_output_tokens,
                seed_supported=seed_supported,
                parallel_tool_calls=parallel_tool_calls,
                provider_parameters=(
                    {"reasoning_effort": "default"}
                    if provider_parameters is None
                    else provider_parameters
                ),
            ),
            regeneration=_invocation_config(
                model=model,
                temperature=temperature,
                seed=seed(regeneration_seed_offset, index),
                top_p=top_p,
                max_output_tokens=max_output_tokens,
                seed_supported=seed_supported,
                parallel_tool_calls=parallel_tool_calls,
                provider_parameters=(
                    {"reasoning_effort": "default"}
                    if provider_parameters is None
                    else provider_parameters
                ),
            ),
        )
        for index in range(ENGINEERING_SLOT_COUNT)
    )


def _manifest(
    configs: tuple[ManifestModelConfig, ...] | None = None,
) -> EngineeringValidationManifest:
    return build_engineering_validation_manifest(
        manifest_id=MANIFEST_ID,
        slot_model_configs=_slot_configs() if configs is None else configs,
    )


def _entry_schedule(entry: EngineeringManifestEntry) -> tuple[object, ...]:
    return (
        entry.scheduled_attempt_index,
        entry.replicate,
        entry.scenario_id,
        entry.plan.hidden_world_order,
        entry.hidden_world_orientation_bit,
        entry.policy_orientation_bit,
        entry.plan.h0_arm_order,
        entry.plan.h1_arm_order,
        entry.schedule_stratum.value,
    )


def test_materializes_every_exact_frozen_slot_and_plan() -> None:
    manifest = _manifest()

    assert EXPERIMENT_VERSION == "primary-create-v1.2"
    assert HIDDEN_WORLD_ORDER_SEED == POLICY_ORDER_SEED == 0
    assert len(manifest.entries) == ENGINEERING_SLOT_COUNT == 16
    assert tuple(_entry_schedule(entry) for entry in manifest.entries) == (
        EXPECTED_SCHEDULE
    )
    for entry in manifest.entries:
        assert type(entry.plan) is ScheduledTrialPlan
        assert entry.plan.scheduled_attempt_ordinal == entry.scheduled_attempt_index
        assert entry.plan.manifest_id == MANIFEST_ID
        assert entry.plan.scenario_id == entry.scenario_id
        assert validate_catalog_task(entry.scenario_id, entry.plan.task_spec) is (
            entry.scenario
        )
        assert entry.plan.base_trial_id == (
            f"bt-{MANIFEST_ID}-{entry.scheduled_attempt_index:06d}"
        )


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (0, (H0, H1)),
        (1, (H1, H0)),
        (14, (H0, H1)),
        (15, (H1, H0)),
    ],
)
def test_hidden_world_order_is_exact_arithmetic(index: int, expected) -> None:
    assert hidden_world_order_for_index(index) == expected


@pytest.mark.parametrize("index", [-1, 16, True, 1.5])
def test_hidden_world_order_rejects_non_slot_indices(index: object) -> None:
    with pytest.raises(ManifestProtocolError, match="0 through 15"):
        hidden_world_order_for_index(index)  # type: ignore[arg-type]


def test_policy_orientation_is_exact_scenario_ordinal_arithmetic() -> None:
    assert tuple(
        policy_orientation_bit_for_scenario(f"CREATE-{ordinal:03d}")
        for ordinal in range(1, 9)
    ) == (0, 1, 0, 1, 0, 1, 0, 1)


def test_manifest_has_every_frozen_counterbalance() -> None:
    manifest = _manifest()
    hidden_first = Counter(
        entry.plan.hidden_world_order[0] for entry in manifest.entries
    )
    per_world: Counter[tuple[HiddenWorld, str]] = Counter()
    per_scenario: Counter[tuple[str, HiddenWorld, str]] = Counter()
    positions = {position: Counter() for position in range(1, 5)}

    for entry in manifest.entries:
        for world in (H0, H1):
            first_policy = entry.plan.arm_order(world)[0]
            per_world[(world, first_policy)] += 1
            per_scenario[(entry.scenario_id, world, first_policy)] += 1
        serial = tuple(
            policy
            for world in entry.plan.hidden_world_order
            for policy in entry.plan.arm_order(world)
        )
        for position, policy in enumerate(serial, start=1):
            positions[position][policy] += 1

    assert hidden_first == Counter({H0: 8, H1: 8})
    assert per_world == Counter(
        {
            (H0, EXACT_REPLAY): 8,
            (H0, LLM_REGENERATION): 8,
            (H1, EXACT_REPLAY): 8,
            (H1, LLM_REGENERATION): 8,
        }
    )
    for ordinal in range(1, 9):
        scenario_id = f"CREATE-{ordinal:03d}"
        for world in (H0, H1):
            assert Counter(
                {
                    policy: per_scenario[(scenario_id, world, policy)]
                    for policy in (EXACT_REPLAY, LLM_REGENERATION)
                }
            ) == Counter({EXACT_REPLAY: 1, LLM_REGENERATION: 1})
    expected_position = Counter({EXACT_REPLAY: 8, LLM_REGENERATION: 8})
    assert positions == {
        position: expected_position for position in range(1, 5)
    }
    assert Counter(entry.schedule_stratum for entry in manifest.entries) == Counter(
        {stratum: 4 for stratum in ScheduleStratum}
    )


def test_constant_policy_orientation_regression_is_detected() -> None:
    manifest = _manifest()
    assert {entry.policy_orientation_bit for entry in manifest.entries} == {0, 1}
    assert tuple(entry.policy_orientation_bit for entry in manifest.entries) == (
        0,
        1,
        0,
        1,
        0,
        1,
        0,
        1,
        1,
        0,
        1,
        0,
        1,
        0,
        1,
        0,
    )


def test_explicit_model_configs_and_seeds_are_preserved_without_derivation() -> None:
    configs = _slot_configs(
        model="explicit-neutral-model",
        temperature=0.625,
        original_seed_offset=31_000,
        regeneration_seed_offset=47_000,
    )
    manifest = _manifest(configs)

    for index, entry in enumerate(manifest.entries):
        assert entry.model_config is configs[index]
        assert (
            entry.original_generation_config
            is configs[index].original_generation.model_call_config
        )
        assert (
            entry.regeneration_config
            is configs[index].regeneration.model_call_config
        )
        assert entry.original_generation_config.seed == 31_000 + index
        assert entry.regeneration_config.seed == 47_000 + index
        assert entry.original_generation_config.temperature == 0.625
        assert entry.regeneration_config.temperature == 0.625
        assert entry.original_generation_config.model == "explicit-neutral-model"
        assert entry.regeneration_config.model == "explicit-neutral-model"
    assert HIDDEN_WORLD_ORDER_SEED == POLICY_ORDER_SEED == 0
    assert all(
        entry.original_generation_config.seed not in (0,)
        and entry.regeneration_config.seed not in (0,)
        for entry in manifest.entries
    )


def test_null_model_seeds_remain_null() -> None:
    manifest = _manifest(
        _slot_configs(
            original_seed_offset=None,
            regeneration_seed_offset=None,
        )
    )

    assert all(
        entry.original_generation_config.seed is None
        and entry.regeneration_config.seed is None
        for entry in manifest.entries
    )


def test_manifest_identity_is_deterministic_and_canonical() -> None:
    first = _manifest(_slot_configs())
    second = _manifest(_slot_configs())

    assert first == second
    assert first.entries == second.entries
    assert first.canonical_bytes == second.canonical_bytes
    assert first.manifest_hash == second.manifest_hash
    assert len(first.manifest_hash) == 64
    assert not first.canonical_bytes.endswith(b"\n")
    decoded = json.loads(first.canonical_bytes)
    assert decoded["experiment_version"] == "primary-create-v1.2"
    assert decoded["hidden_world_order_seed"] == 0
    assert decoded["policy_order_seed"] == 0
    assert len(decoded["entries"]) == 16
    model_config = decoded["entries"][0]["model_config"]
    assert set(model_config) == {
        "model_config_id",
        "model",
        "original_generation",
        "regeneration",
    }
    assert model_config["model"] == {
        "provider": "provider-neutral",
        "name": "caller-model",
        "version_or_digest": "caller-version-v1",
    }
    expected_sampling_keys = {
        "temperature",
        "top_p",
        "max_output_tokens",
        "seed",
        "seed_supported",
        "tool_choice",
        "parallel_tool_calls",
        "provider_parameters",
    }
    assert set(model_config["original_generation"]) == expected_sampling_keys
    assert set(model_config["regeneration"]) == expected_sampling_keys
    assert model_config["original_generation"] == (
        first.entries[0]
        .model_config.original_generation.as_trace_sampling_configuration()
    )
    assert model_config["regeneration"] == (
        first.entries[0]
        .model_config.regeneration.as_trace_sampling_configuration()
    )


@pytest.mark.parametrize(
    "configs",
    [
        _slot_configs(provider="changed-provider"),
        _slot_configs(model="changed-model"),
        _slot_configs(version_or_digest="changed-version"),
        _slot_configs(temperature=0.75),
        _slot_configs(top_p=0.8),
        _slot_configs(max_output_tokens=512),
        _slot_configs(original_seed_offset=11_000),
        _slot_configs(regeneration_seed_offset=21_000),
        _slot_configs(parallel_tool_calls=True),
        _slot_configs(provider_parameters={"reasoning_effort": "high"}),
        _slot_configs(model_config_id_prefix="changed-config"),
    ],
)
def test_treatment_relevant_model_input_changes_manifest_identity(configs) -> None:
    baseline = _manifest()
    changed = _manifest(configs)

    assert changed != baseline
    assert changed.canonical_bytes != baseline.canonical_bytes
    assert changed.manifest_hash != baseline.manifest_hash


def test_seed_supported_changes_identity_without_changing_null_seed() -> None:
    supported = _manifest(
        _slot_configs(
            original_seed_offset=None,
            regeneration_seed_offset=None,
            seed_supported=True,
        )
    )
    unsupported = _manifest(
        _slot_configs(
            original_seed_offset=None,
            regeneration_seed_offset=None,
            seed_supported=False,
        )
    )

    assert supported.canonical_bytes != unsupported.canonical_bytes
    assert supported.manifest_hash != unsupported.manifest_hash


@pytest.mark.parametrize(
    ("left", "right"),
    [(0, 0.0), (-0.0, 0.0)],
)
def test_temperature_numeric_equivalents_have_one_manifest_identity(
    left: float, right: float
) -> None:
    first = _manifest(_slot_configs(temperature=left))
    second = _manifest(_slot_configs(temperature=right))

    assert first == second
    assert first.canonical_bytes == second.canonical_bytes
    assert first.manifest_hash == second.manifest_hash
    assert first.entries[0].original_generation_config.temperature == 0.0
    assert json.loads(first.canonical_bytes)["entries"][0]["model_config"][
        "original_generation"
    ]["temperature"] == 0.0


@pytest.mark.parametrize(
    ("left", "right"),
    [(0, 0.0), (-0.0, 0.0), (1, 1.0)],
)
def test_top_p_numeric_equivalents_have_one_manifest_identity(
    left: float, right: float
) -> None:
    first = _manifest(_slot_configs(top_p=left))
    second = _manifest(_slot_configs(top_p=right))

    assert first == second
    assert first.canonical_bytes == second.canonical_bytes
    assert first.manifest_hash == second.manifest_hash
    assert first.entries[0].original_generation_config.top_p == float(left)


def test_provider_parameters_are_copied_recursively_and_immutable() -> None:
    parameters = {
        "reasoning": {"effort": "medium", "exclude": ["summaries"]},
        "service_tier": "standard",
    }
    manifest = _manifest(_slot_configs(provider_parameters=parameters))
    before_bytes = manifest.canonical_bytes
    before_hash = manifest.manifest_hash

    parameters["reasoning"]["effort"] = "changed"  # type: ignore[index]
    parameters["reasoning"]["exclude"].append("tools")  # type: ignore[index,union-attr]
    frozen = manifest.entries[0].original_generation_config.provider_parameters

    assert type(frozen) is MappingProxyType
    assert type(frozen["reasoning"]) is MappingProxyType  # type: ignore[index]
    assert type(frozen["reasoning"]["exclude"]) is tuple  # type: ignore[index]
    with pytest.raises(TypeError):
        frozen["service_tier"] = "priority"  # type: ignore[index]
    assert manifest.canonical_bytes == before_bytes
    assert manifest.manifest_hash == before_hash
    assert json.loads(before_bytes)["entries"][0]["model_config"][
        "original_generation"
    ]["provider_parameters"]["reasoning"]["effort"] == "medium"


def test_provider_parameter_key_order_does_not_change_identity() -> None:
    first = _manifest(
        _slot_configs(provider_parameters={"zeta": 1, "alpha": {"b": 2, "a": 1}})
    )
    second = _manifest(
        _slot_configs(provider_parameters={"alpha": {"a": 1, "b": 2}, "zeta": 1})
    )

    assert first == second
    assert first.canonical_bytes == second.canonical_bytes
    assert first.manifest_hash == second.manifest_hash


def test_trace_helpers_supply_every_frozen_required_configuration_field() -> None:
    config = _slot_configs()[0]
    schema = json.loads(TRACE_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert set(config.model.as_trace_model()) == set(
        schema["$defs"]["model"]["required"]
    )
    assert set(config.original_generation.as_trace_sampling_configuration()) == set(
        schema["$defs"]["samplingConfiguration"]["required"]
    )
    assert config.original_generation.as_trace_sampling_configuration()[
        "max_output_tokens"
    ] == config.original_generation.model_call_config.max_completion_tokens


def test_manifest_execution_fields_reach_real_provider_mapper() -> None:
    entry = _manifest(
        _slot_configs(
            provider="groq",
            temperature=0.375,
            top_p=0.625,
            max_output_tokens=444,
            parallel_tool_calls=True,
            provider_parameters={"reasoning_effort": "medium"},
        )
    ).entries[0]
    request = build_v1_original_generation_request(
        task_spec=entry.plan.task_spec,
        model_config=entry.original_generation_config,
    )

    payload = build_groq_chat_completion_kwargs(request)

    assert payload["model"] == entry.model_config.model.name
    assert payload["temperature"] == 0.375
    assert payload["top_p"] == 0.625
    assert payload["seed"] == 10_000
    assert payload["max_completion_tokens"] == 444
    assert payload["tool_choice"] == "auto"
    assert payload["parallel_tool_calls"] is True
    assert payload["reasoning_effort"] == "medium"


def test_manifest_rejects_missing_or_implicit_slot_model_inputs() -> None:
    configs = _slot_configs()
    with pytest.raises(ManifestProtocolError, match="exactly 16"):
        build_engineering_validation_manifest(
            manifest_id=MANIFEST_ID,
            slot_model_configs=configs[:-1],
        )
    with pytest.raises(ManifestProtocolError, match="exactly 16"):
        build_engineering_validation_manifest(  # type: ignore[arg-type]
            manifest_id=MANIFEST_ID,
            slot_model_configs=list(configs),
        )


def test_manifest_model_config_rejects_incoherent_or_unusable_inputs() -> None:
    identity = ManifestModelIdentity("provider", "model-a", None)
    original = _invocation_config(model="model-a", temperature=0.2, seed=1)
    regeneration = _invocation_config(model="model-b", temperature=0.2, seed=2)
    with pytest.raises(ManifestProtocolError, match="must agree"):
        ManifestModelConfig(
            model_config_id="mismatch",
            model=identity,
            original_generation=original,
            regeneration=regeneration,
        )
    with pytest.raises(ManifestProtocolError, match="tool_choice mode AUTO"):
        ManifestModelConfig(
            model_config_id="forced",
            model=identity,
            original_generation=replace(
                original,
                model_call_config=replace(
                    original.model_call_config,
                    tool_choice=ToolChoice.forced_function("create_ticket"),
                ),
            ),
            regeneration=replace(
                regeneration,
                model_call_config=replace(
                    regeneration.model_call_config, model="model-a"
                ),
            ),
        )
    with pytest.raises(ManifestProtocolError, match="Regeneration requires"):
        ManifestModelConfig(
            model_config_id="forced-regeneration",
            model=identity,
            original_generation=original,
            regeneration=replace(
                original,
                model_call_config=replace(
                    original.model_call_config,
                    seed=2,
                    tool_choice=ToolChoice.forced_function("create_ticket"),
                ),
            ),
        )


@pytest.mark.parametrize("provider", ["", None, 7])
def test_manifest_model_identity_rejects_invalid_provider(provider: object) -> None:
    with pytest.raises(ManifestProtocolError, match="provider"):
        ManifestModelIdentity(provider, "model", None)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["", None, 7])
def test_manifest_model_identity_rejects_invalid_name(name: object) -> None:
    with pytest.raises(ManifestProtocolError, match="name"):
        ManifestModelIdentity("provider", name, None)  # type: ignore[arg-type]


def test_manifest_model_identity_rejects_invalid_version_type() -> None:
    with pytest.raises(ManifestProtocolError, match="version_or_digest"):
        ManifestModelIdentity("provider", "model", 7)  # type: ignore[arg-type]


def test_manifest_invocation_rejects_incomplete_or_incoherent_sampling() -> None:
    with pytest.raises(ManifestProtocolError, match="must be explicit"):
        _invocation_config(
            model="model",
            temperature=0.2,
            seed=1,
            max_output_tokens=None,
        )
    with pytest.raises(ManifestProtocolError, match="seed must be null"):
        _invocation_config(
            model="model",
            temperature=0.2,
            seed=1,
            seed_supported=False,
        )
    with pytest.raises(ModelRequestError, match="top_p must be at most 1"):
        _invocation_config(
            model="model", temperature=0.2, seed=1, top_p=1.1
        )
    with pytest.raises(ModelRequestError, match="JSON object"):
        _invocation_config(
            model="model",
            temperature=0.2,
            seed=1,
            provider_parameters=["not", "an", "object"],
        )
    unsupported = _invocation_config(
        model="model",
        temperature=0.2,
        seed=None,
        seed_supported=False,
    )
    assert unsupported.model_call_config.seed is None


@pytest.mark.parametrize(
    "parameters",
    [
        {"api_key": "secret"},
        {"connection": {"access_token": "secret"}},
        {"request": {"Authorization": "Bearer secret"}},
        {"headers": {"X-Mode": "test"}},
    ],
)
def test_manifest_invocation_rejects_secret_provider_parameters(
    parameters: dict[str, object],
) -> None:
    with pytest.raises(ModelRequestError, match="secret field"):
        _invocation_config(
            model="model",
            temperature=0.2,
            seed=1,
            provider_parameters=parameters,
        )


def test_manifest_invocation_rejects_duplicate_sampling_fields() -> None:
    with pytest.raises(ModelRequestError, match="duplicates"):
        _invocation_config(
            model="model",
            temperature=0.2,
            seed=1,
            provider_parameters={"temperature": 0.2},
        )


def test_manifest_rejects_catalog_mismatch_inside_a_plan() -> None:
    manifest = _manifest()
    entry = manifest.entries[0]
    mismatched_plan = replace(
        entry.plan,
        task_spec=get_scenario("CREATE-002").task_spec,
    )

    with pytest.raises(ManifestProtocolError, match="task_spec does not match"):
        replace(entry, plan=mismatched_plan)


def test_manifest_types_and_nested_schedule_are_immutable() -> None:
    manifest = _manifest()
    entry = manifest.entries[0]

    with pytest.raises(FrozenInstanceError):
        manifest.entries = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        entry.replicate = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        entry.plan.h0_arm_order = REGENERATION_FIRST  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        entry.model_config.model.provider = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        entry.original_generation_config.top_p = 0.5  # type: ignore[misc]
    assert type(manifest.entries) is tuple


def test_manifest_construction_has_no_execution_side_effects(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("manifest construction crossed an execution boundary")

    monkeypatch.setattr(ModelClient, "complete", forbidden)
    monkeypatch.setattr(scheduled_trial_module, "run_scheduled_trial", forbidden)
    monkeypatch.setattr(
        scheduled_trial_module,
        "construct_trial_family_states",
        forbidden,
    )
    monkeypatch.setattr(scheduled_trial_module, "execute_exact_replay", forbidden)
    monkeypatch.setattr(
        scheduled_trial_module,
        "execute_llm_regeneration",
        forbidden,
    )
    monkeypatch.setattr(TicketEnvironment, "empty", forbidden)
    monkeypatch.setattr(TicketEnvironment, "execute_request", forbidden)

    manifest = _manifest()

    assert len(manifest.entries) == 16
