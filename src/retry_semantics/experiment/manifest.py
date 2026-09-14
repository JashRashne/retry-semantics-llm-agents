"""Pure deterministic V1.2 engineering-manifest materialization."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum

from retry_semantics.experiment.catalog import (
    ScenarioCatalogError,
    ScenarioDefinition,
    get_scenario,
    validate_catalog_scenario,
    validate_catalog_task,
)
from retry_semantics.models.base import (
    ModelCallConfig,
    ToolChoiceMode,
    thaw_json_value,
)
from retry_semantics.runtime.exact_replay import EXACT_REPLAY
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.runtime.regeneration import LLM_REGENERATION
from retry_semantics.runtime.scheduled_trial import ScheduledTrialPlan
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

EXPERIMENT_VERSION = "primary-create-v1.2"
ENGINEERING_SLOT_COUNT = 16
HIDDEN_WORLD_ORDER_SEED = 0
POLICY_ORDER_SEED = 0

_H0_H1 = (HiddenWorld.NOT_EXECUTED, HiddenWorld.EXECUTED_ACK_LOST)
_H1_H0 = (HiddenWorld.EXECUTED_ACK_LOST, HiddenWorld.NOT_EXECUTED)
_REPLAY_FIRST = (EXACT_REPLAY, LLM_REGENERATION)
_REGENERATION_FIRST = (LLM_REGENERATION, EXACT_REPLAY)
_ENGINEERING_QUEUE = (
    (1, "CREATE-001"),
    (1, "CREATE-002"),
    (1, "CREATE-003"),
    (1, "CREATE-004"),
    (1, "CREATE-005"),
    (1, "CREATE-006"),
    (1, "CREATE-007"),
    (1, "CREATE-008"),
    (2, "CREATE-008"),
    (2, "CREATE-007"),
    (2, "CREATE-006"),
    (2, "CREATE-005"),
    (2, "CREATE-004"),
    (2, "CREATE-003"),
    (2, "CREATE-002"),
    (2, "CREATE-001"),
)


class ManifestProtocolError(ValueError):
    """A manifest value violates the frozen V1.2 materialization contract."""


class ScheduleStratum(str, Enum):
    """The four frozen hidden-world/policy scheduling combinations."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass(frozen=True, slots=True)
class ManifestModelIdentity:
    """Provider-neutral identity for the single model used by a base trial."""

    provider: str
    name: str
    version_or_digest: str | None

    def __post_init__(self) -> None:
        if type(self.provider) is not str or self.provider == "":
            raise ManifestProtocolError("model provider must be a non-empty string")
        if type(self.name) is not str or self.name == "":
            raise ManifestProtocolError("model name must be a non-empty string")
        if self.version_or_digest is not None and type(
            self.version_or_digest
        ) is not str:
            raise ManifestProtocolError(
                "model version_or_digest must be a string or null"
            )

    def as_trace_model(self) -> dict[str, object]:
        """Return the exact trace-schema model-identity shape."""

        return {
            "provider": self.provider,
            "name": self.name,
            "version_or_digest": self.version_or_digest,
        }


@dataclass(frozen=True, slots=True)
class ManifestInvocationConfig:
    """One trace-complete invocation configuration around ModelCallConfig."""

    model_call_config: ModelCallConfig
    seed_supported: bool

    def __post_init__(self) -> None:
        if type(self.model_call_config) is not ModelCallConfig:
            raise ManifestProtocolError(
                "model_call_config must be a ModelCallConfig"
            )
        if type(self.seed_supported) is not bool:
            raise ManifestProtocolError("seed_supported must be a bool")
        if not self.seed_supported and self.model_call_config.seed is not None:
            raise ManifestProtocolError(
                "seed must be null when seed_supported is false"
            )
        if self.model_call_config.max_completion_tokens is None:
            raise ManifestProtocolError(
                "max_completion_tokens must be explicit for manifest invocations"
            )

    def as_trace_sampling_configuration(self) -> dict[str, object]:
        """Return the exact trace-schema sampling-configuration shape."""

        config = self.model_call_config
        return {
            "temperature": config.temperature,
            "top_p": config.top_p,
            "max_output_tokens": config.max_completion_tokens,
            "seed": config.seed,
            "seed_supported": self.seed_supported,
            "tool_choice": {
                "function_name": config.tool_choice.function_name,
                "mode": config.tool_choice.mode.value,
            },
            "parallel_tool_calls": config.parallel_tool_calls,
            "provider_parameters": thaw_json_value(config.provider_parameters),
        }


@dataclass(frozen=True, slots=True)
class ManifestModelConfig:
    """Explicit provider-neutral model inputs for one scheduled slot."""

    model_config_id: str
    model: ManifestModelIdentity
    original_generation: ManifestInvocationConfig
    regeneration: ManifestInvocationConfig

    def __post_init__(self) -> None:
        if type(self.model_config_id) is not str or self.model_config_id == "":
            raise ManifestProtocolError(
                "model_config_id must be a non-empty string"
            )
        if type(self.model) is not ManifestModelIdentity:
            raise ManifestProtocolError("model must be a ManifestModelIdentity")
        if type(self.original_generation) is not ManifestInvocationConfig:
            raise ManifestProtocolError(
                "original_generation must be a ManifestInvocationConfig"
            )
        if type(self.regeneration) is not ManifestInvocationConfig:
            raise ManifestProtocolError(
                "regeneration must be a ManifestInvocationConfig"
            )
        original_config = self.original_generation.model_call_config
        regeneration_config = self.regeneration.model_call_config
        if (
            original_config.model != self.model.name
            or regeneration_config.model != self.model.name
        ):
            raise ManifestProtocolError(
                "manifest model name and both ModelCallConfig.model values must agree"
            )
        if original_config.tool_choice.mode is not ToolChoiceMode.AUTO:
            raise ManifestProtocolError(
                "V1 original generation requires tool_choice mode AUTO"
            )
        if regeneration_config.tool_choice.mode is not ToolChoiceMode.AUTO:
            raise ManifestProtocolError(
                "V1 Regeneration requires tool_choice mode AUTO"
            )


def hidden_world_order_for_index(
    scheduled_attempt_index: int,
) -> tuple[HiddenWorld, HiddenWorld]:
    """Materialize the frozen hidden-world order for one engineering slot."""

    if (
        type(scheduled_attempt_index) is not int
        or not 0 <= scheduled_attempt_index < ENGINEERING_SLOT_COUNT
    ):
        raise ManifestProtocolError(
            "scheduled_attempt_index must be an integer from 0 through 15"
        )
    orientation_bit = (
        HIDDEN_WORLD_ORDER_SEED + scheduled_attempt_index
    ) % 2
    return _H0_H1 if orientation_bit == 0 else _H1_H0


def _scenario_ordinal(scenario_id: str) -> int:
    scenario = get_scenario(scenario_id)
    return int(scenario.scenario_id.removeprefix("CREATE-"))


def policy_orientation_bit_for_scenario(scenario_id: str) -> int:
    """Materialize the frozen policy orientation from the scenario ordinal."""

    scenario_ordinal = _scenario_ordinal(scenario_id)
    return (POLICY_ORDER_SEED + scenario_ordinal - 1) % 2


def _policy_orders_for_scenario(
    scenario_id: str,
) -> tuple[tuple[str, str], tuple[str, str]]:
    if policy_orientation_bit_for_scenario(scenario_id) == 0:
        return _REPLAY_FIRST, _REGENERATION_FIRST
    return _REGENERATION_FIRST, _REPLAY_FIRST


def _schedule_stratum(
    hidden_world_order: tuple[HiddenWorld, HiddenWorld],
    policy_orientation_bit: int,
) -> ScheduleStratum:
    return {
        (_H0_H1, 0): ScheduleStratum.A,
        (_H1_H0, 1): ScheduleStratum.B,
        (_H0_H1, 1): ScheduleStratum.C,
        (_H1_H0, 0): ScheduleStratum.D,
    }[(hidden_world_order, policy_orientation_bit)]


@dataclass(frozen=True, slots=True)
class EngineeringManifestEntry:
    """One immutable, fully materialized engineering-validation slot."""

    scheduled_attempt_index: int
    replicate: int
    scenario: ScenarioDefinition
    hidden_world_orientation_bit: int
    policy_orientation_bit: int
    schedule_stratum: ScheduleStratum
    model_config: ManifestModelConfig
    plan: ScheduledTrialPlan

    def __post_init__(self) -> None:
        if (
            type(self.scheduled_attempt_index) is not int
            or not 0 <= self.scheduled_attempt_index < ENGINEERING_SLOT_COUNT
        ):
            raise ManifestProtocolError(
                "scheduled_attempt_index must be an integer from 0 through 15"
            )
        if type(self.replicate) is not int or self.replicate not in (1, 2):
            raise ManifestProtocolError("replicate must be 1 or 2")
        try:
            validate_catalog_scenario(self.scenario)
        except ScenarioCatalogError as exc:
            raise ManifestProtocolError(str(exc)) from exc
        if type(self.model_config) is not ManifestModelConfig:
            raise ManifestProtocolError(
                "model_config must be a ManifestModelConfig"
            )
        if type(self.plan) is not ScheduledTrialPlan:
            raise ManifestProtocolError("plan must be a ScheduledTrialPlan")

        expected_replicate, expected_scenario_id = _ENGINEERING_QUEUE[
            self.scheduled_attempt_index
        ]
        if (self.replicate, self.scenario.scenario_id) != (
            expected_replicate,
            expected_scenario_id,
        ):
            raise ManifestProtocolError(
                "entry does not match the frozen scenario/replicate queue"
            )

        hidden_world_order = hidden_world_order_for_index(
            self.scheduled_attempt_index
        )
        hidden_world_orientation_bit = (
            HIDDEN_WORLD_ORDER_SEED + self.scheduled_attempt_index
        ) % 2
        policy_orientation_bit = policy_orientation_bit_for_scenario(
            self.scenario.scenario_id
        )
        first_policy_order, second_policy_order = _policy_orders_for_scenario(
            self.scenario.scenario_id
        )
        if hidden_world_order[0] is HiddenWorld.NOT_EXECUTED:
            h0_arm_order = first_policy_order
            h1_arm_order = second_policy_order
        else:
            h0_arm_order = second_policy_order
            h1_arm_order = first_policy_order
        schedule_stratum = _schedule_stratum(
            hidden_world_order, policy_orientation_bit
        )

        if self.hidden_world_orientation_bit != hidden_world_orientation_bit:
            raise ManifestProtocolError(
                "hidden_world_orientation_bit does not match frozen arithmetic"
            )
        if self.policy_orientation_bit != policy_orientation_bit:
            raise ManifestProtocolError(
                "policy_orientation_bit does not match frozen arithmetic"
            )
        if self.schedule_stratum is not schedule_stratum:
            raise ManifestProtocolError(
                "schedule_stratum does not match frozen schedule metadata"
            )
        if (
            self.plan.scheduled_attempt_ordinal != self.scheduled_attempt_index
            or self.plan.scenario_id != self.scenario.scenario_id
            or self.plan.hidden_world_order != hidden_world_order
            or self.plan.h0_arm_order != h0_arm_order
            or self.plan.h1_arm_order != h1_arm_order
        ):
            raise ManifestProtocolError(
                "ScheduledTrialPlan does not match frozen schedule materialization"
            )
        try:
            validate_catalog_task(self.plan.scenario_id, self.plan.task_spec)
        except ScenarioCatalogError as exc:
            raise ManifestProtocolError(str(exc)) from exc

    @property
    def scenario_id(self) -> str:
        return self.scenario.scenario_id

    @property
    def original_generation_config(self) -> ModelCallConfig:
        return self.model_config.original_generation.model_call_config

    @property
    def regeneration_config(self) -> ModelCallConfig:
        return self.model_config.regeneration.model_call_config


@dataclass(frozen=True, slots=True)
class EngineeringValidationManifest:
    """The immutable 16-slot V1.2 engineering-validation manifest."""

    manifest_id: str
    entries: tuple[EngineeringManifestEntry, ...]

    def __post_init__(self) -> None:
        if type(self.manifest_id) is not str or self.manifest_id == "":
            raise ManifestProtocolError("manifest_id must be a non-empty string")
        if type(self.entries) is not tuple or len(self.entries) != (
            ENGINEERING_SLOT_COUNT
        ):
            raise ManifestProtocolError(
                "engineering manifest must contain exactly 16 immutable entries"
            )
        if any(type(entry) is not EngineeringManifestEntry for entry in self.entries):
            raise ManifestProtocolError(
                "entries must contain only EngineeringManifestEntry values"
            )
        for index, entry in enumerate(self.entries):
            if entry.scheduled_attempt_index != index:
                raise ManifestProtocolError(
                    "entries must be ordered by scheduled_attempt_index"
                )
            if entry.plan.manifest_id != self.manifest_id:
                raise ManifestProtocolError(
                    "entry ScheduledTrialPlan uses a different manifest_id"
                )
        self._validate_model_config_identities()
        self._validate_frozen_balance()

    def _validate_model_config_identities(self) -> None:
        identities: dict[str, ManifestModelConfig] = {}
        for entry in self.entries:
            identifier = entry.model_config.model_config_id
            previous = identities.setdefault(identifier, entry.model_config)
            if previous != entry.model_config:
                raise ManifestProtocolError(
                    "one model_config_id identifies multiple configurations"
                )

    def _validate_frozen_balance(self) -> None:
        hidden_first = Counter(
            entry.plan.hidden_world_order[0] for entry in self.entries
        )
        expected_hidden_first = Counter(
            {
                HiddenWorld.NOT_EXECUTED: 8,
                HiddenWorld.EXECUTED_ACK_LOST: 8,
            }
        )
        if hidden_first != expected_hidden_first:
            raise ManifestProtocolError("hidden-world first-position balance failed")

        per_world_policy: Counter[tuple[HiddenWorld, str]] = Counter()
        per_scenario_world: Counter[tuple[str, HiddenWorld, str]] = Counter()
        family_position: dict[int, Counter[str]] = {
            position: Counter() for position in range(1, 5)
        }
        strata = Counter(entry.schedule_stratum for entry in self.entries)
        for entry in self.entries:
            for hidden_world in _H0_H1:
                first_policy = entry.plan.arm_order(hidden_world)[0]
                per_world_policy[(hidden_world, first_policy)] += 1
                per_scenario_world[
                    (entry.scenario_id, hidden_world, first_policy)
                ] += 1
            ordered_policies = tuple(
                policy
                for hidden_world in entry.plan.hidden_world_order
                for policy in entry.plan.arm_order(hidden_world)
            )
            for position, policy in enumerate(ordered_policies, start=1):
                family_position[position][policy] += 1

        expected_per_world_policy = Counter(
            {
                (HiddenWorld.NOT_EXECUTED, EXACT_REPLAY): 8,
                (HiddenWorld.NOT_EXECUTED, LLM_REGENERATION): 8,
                (HiddenWorld.EXECUTED_ACK_LOST, EXACT_REPLAY): 8,
                (HiddenWorld.EXECUTED_ACK_LOST, LLM_REGENERATION): 8,
            }
        )
        if per_world_policy != expected_per_world_policy:
            raise ManifestProtocolError("per-world policy-order balance failed")

        for scenario in (get_scenario(item) for _, item in _ENGINEERING_QUEUE[:8]):
            for hidden_world in _H0_H1:
                if Counter(
                    {
                        policy: per_scenario_world[
                            (scenario.scenario_id, hidden_world, policy)
                        ]
                        for policy in (EXACT_REPLAY, LLM_REGENERATION)
                    }
                ) != Counter({EXACT_REPLAY: 1, LLM_REGENERATION: 1}):
                    raise ManifestProtocolError(
                        "per-scenario hidden-world policy balance failed"
                    )

        expected_position = Counter({EXACT_REPLAY: 8, LLM_REGENERATION: 8})
        if any(
            family_position[position] != expected_position
            for position in range(1, 5)
        ):
            raise ManifestProtocolError("absolute family-position balance failed")
        if strata != Counter({stratum: 4 for stratum in ScheduleStratum}):
            raise ManifestProtocolError("schedule-stratum balance failed")

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(
            {
                "entries": [_entry_as_json(entry) for entry in self.entries],
                "experiment_version": EXPERIMENT_VERSION,
                "hidden_world_order_seed": HIDDEN_WORLD_ORDER_SEED,
                "manifest_id": self.manifest_id,
                "manifest_kind": "engineering_validation",
                "policy_order_seed": POLICY_ORDER_SEED,
            }
        )

    @property
    def manifest_hash(self) -> str:
        return sha256_hex(self.canonical_bytes)


def _entry_as_json(entry: EngineeringManifestEntry) -> dict[str, object]:
    return {
        "hidden_world_orientation_bit": entry.hidden_world_orientation_bit,
        "model_config": {
            "model_config_id": entry.model_config.model_config_id,
            "model": entry.model_config.model.as_trace_model(),
            "original_generation": (
                entry.model_config.original_generation
                .as_trace_sampling_configuration()
            ),
            "regeneration": (
                entry.model_config.regeneration
                .as_trace_sampling_configuration()
            ),
        },
        "policy_orientation_bit": entry.policy_orientation_bit,
        "replicate": entry.replicate,
        "scenario": {
            "customer_id": entry.scenario.customer_id,
            "expected_description": entry.scenario.expected_description,
            "expected_title": entry.scenario.expected_title,
            "scenario_id": entry.scenario.scenario_id,
            "user_task": entry.scenario.user_task,
        },
        "schedule_stratum": entry.schedule_stratum.value,
        "scheduled_attempt_index": entry.scheduled_attempt_index,
        "scheduled_trial_plan": {
            "h0_arm_order": list(entry.plan.h0_arm_order),
            "h1_arm_order": list(entry.plan.h1_arm_order),
            "hidden_world_order": [
                hidden_world.value for hidden_world in entry.plan.hidden_world_order
            ],
            "manifest_id": entry.plan.manifest_id,
            "scenario_id": entry.plan.scenario_id,
            "scheduled_attempt_ordinal": entry.plan.scheduled_attempt_ordinal,
        },
    }


def build_engineering_validation_manifest(
    *,
    manifest_id: str,
    slot_model_configs: tuple[ManifestModelConfig, ...],
) -> EngineeringValidationManifest:
    """Materialize the exact 16 slots from explicit per-slot model inputs."""

    if type(slot_model_configs) is not tuple or len(slot_model_configs) != (
        ENGINEERING_SLOT_COUNT
    ):
        raise ManifestProtocolError(
            "slot_model_configs must explicitly contain exactly 16 configurations"
        )
    if any(type(config) is not ManifestModelConfig for config in slot_model_configs):
        raise ManifestProtocolError(
            "slot_model_configs must contain only ManifestModelConfig values"
        )

    entries: list[EngineeringManifestEntry] = []
    for scheduled_attempt_index, (replicate, scenario_id) in enumerate(
        _ENGINEERING_QUEUE
    ):
        # Frozen precedence: slot -> scenario/replicate -> world order -> policy order.
        scenario = get_scenario(scenario_id)
        hidden_world_order = hidden_world_order_for_index(scheduled_attempt_index)
        hidden_world_orientation_bit = (
            HIDDEN_WORLD_ORDER_SEED + scheduled_attempt_index
        ) % 2
        policy_orientation_bit = policy_orientation_bit_for_scenario(scenario_id)
        first_policy_order, second_policy_order = _policy_orders_for_scenario(
            scenario_id
        )
        if hidden_world_order[0] is HiddenWorld.NOT_EXECUTED:
            h0_arm_order = first_policy_order
            h1_arm_order = second_policy_order
        else:
            h0_arm_order = second_policy_order
            h1_arm_order = first_policy_order

        plan = ScheduledTrialPlan(
            manifest_id=manifest_id,
            scheduled_attempt_ordinal=scheduled_attempt_index,
            scenario_id=scenario_id,
            task_spec=scenario.task_spec,
            hidden_world_order=hidden_world_order,
            h0_arm_order=h0_arm_order,
            h1_arm_order=h1_arm_order,
        )
        entries.append(
            EngineeringManifestEntry(
                scheduled_attempt_index=scheduled_attempt_index,
                replicate=replicate,
                scenario=scenario,
                hidden_world_orientation_bit=hidden_world_orientation_bit,
                policy_orientation_bit=policy_orientation_bit,
                schedule_stratum=_schedule_stratum(
                    hidden_world_order, policy_orientation_bit
                ),
                model_config=slot_model_configs[scheduled_attempt_index],
                plan=plan,
            )
        )

    return EngineeringValidationManifest(
        manifest_id=manifest_id,
        entries=tuple(entries),
    )


__all__ = [
    "ENGINEERING_SLOT_COUNT",
    "EXPERIMENT_VERSION",
    "HIDDEN_WORLD_ORDER_SEED",
    "POLICY_ORDER_SEED",
    "EngineeringManifestEntry",
    "EngineeringValidationManifest",
    "ManifestInvocationConfig",
    "ManifestModelConfig",
    "ManifestModelIdentity",
    "ManifestProtocolError",
    "ScheduleStratum",
    "build_engineering_validation_manifest",
    "hidden_world_order_for_index",
    "policy_orientation_bit_for_scenario",
]
