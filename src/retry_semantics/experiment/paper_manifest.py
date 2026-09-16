"""Deterministic primary-create-v1.3 Ticket paper-manifest materialization."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from retry_semantics.experiment.catalog import (
    ScenarioCatalogError,
    ScenarioDefinition,
    get_scenario,
    validate_catalog_scenario,
    validate_catalog_task,
)
from retry_semantics.experiment.manifest import (
    ManifestModelConfig,
    ManifestProtocolError,
    ScheduleStratum,
)
from retry_semantics.models.base import ModelCallConfig, freeze_json_value, thaw_json_value
from retry_semantics.runtime.exact_replay import EXACT_REPLAY
from retry_semantics.runtime.hidden_worlds import HiddenWorld
from retry_semantics.runtime.regeneration import LLM_REGENERATION
from retry_semantics.runtime.scheduled_trial import ScheduledTrialPlan
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

PAPER_EXPERIMENT_REVISION = "primary-create-v1.3"
INHERITED_EXECUTION_REVISION = "primary-create-v1.2"
PAPER_MANIFEST_KIND = "paper"
PAPER_SLOT_COUNT = 160
PAPER_REPLICATE_COUNT = 20

_SCENARIO_IDS = tuple(f"CREATE-{ordinal:03d}" for ordinal in range(1, 9))
_H0_H1 = (HiddenWorld.NOT_EXECUTED, HiddenWorld.EXECUTED_ACK_LOST)
_H1_H0 = (HiddenWorld.EXECUTED_ACK_LOST, HiddenWorld.NOT_EXECUTED)
_REPLAY_FIRST = (EXACT_REPLAY, LLM_REGENERATION)
_REGENERATION_FIRST = (LLM_REGENERATION, EXACT_REPLAY)
_STRATA = (
    ScheduleStratum.A,
    ScheduleStratum.B,
    ScheduleStratum.C,
    ScheduleStratum.D,
)


def paper_queue() -> tuple[tuple[int, str], ...]:
    """Return the exact 20-replicate alternating Ticket queue."""

    return tuple(
        (replicate, scenario_id)
        for replicate in range(1, PAPER_REPLICATE_COUNT + 1)
        for scenario_id in (
            _SCENARIO_IDS if replicate % 2 == 1 else tuple(reversed(_SCENARIO_IDS))
        )
    )


def paper_stratum_for(replicate: int, scenario_id: str) -> ScheduleStratum:
    """Apply the frozen ``(zero-based replicate + canonical scenario) % 4`` rule."""

    if type(replicate) is not int or not 1 <= replicate <= PAPER_REPLICATE_COUNT:
        raise ManifestProtocolError("paper replicate must be an integer from 1 through 20")
    try:
        scenario_index = _SCENARIO_IDS.index(scenario_id)
    except ValueError as exc:
        raise ManifestProtocolError("paper scenario must be in the frozen CREATE catalog") from exc
    return _STRATA[((replicate - 1) + scenario_index) % 4]


def _orders_for_stratum(
    stratum: ScheduleStratum,
) -> tuple[
    tuple[HiddenWorld, HiddenWorld], tuple[str, str], tuple[str, str], int, int
]:
    """Map A/B/C/D to their unchanged V1.2 execution-order semantics."""

    hidden_order, policy_bit = {
        ScheduleStratum.A: (_H0_H1, 0),
        ScheduleStratum.B: (_H1_H0, 1),
        ScheduleStratum.C: (_H0_H1, 1),
        ScheduleStratum.D: (_H1_H0, 0),
    }[stratum]
    first, second = (
        (_REPLAY_FIRST, _REGENERATION_FIRST)
        if policy_bit == 0
        else (_REGENERATION_FIRST, _REPLAY_FIRST)
    )
    if hidden_order[0] is HiddenWorld.NOT_EXECUTED:
        h0_order, h1_order = first, second
    else:
        h0_order, h1_order = second, first
    hidden_bit = 0 if hidden_order == _H0_H1 else 1
    return hidden_order, h0_order, h1_order, hidden_bit, policy_bit


@dataclass(frozen=True, slots=True)
class PaperManifestEntry:
    """One immutable, fully materialized V1.3 paper slot."""

    scheduled_attempt_index: int
    replicate: int
    scenario: ScenarioDefinition
    hidden_world_orientation_bit: int
    policy_orientation_bit: int
    schedule_stratum: ScheduleStratum
    model_config: ManifestModelConfig
    plan: ScheduledTrialPlan

    def __post_init__(self) -> None:
        if type(self.scheduled_attempt_index) is not int or not 0 <= self.scheduled_attempt_index < PAPER_SLOT_COUNT:
            raise ManifestProtocolError("paper slot index must be an integer from 0 through 159")
        try:
            validate_catalog_scenario(self.scenario)
        except ScenarioCatalogError as exc:
            raise ManifestProtocolError(str(exc)) from exc
        if type(self.model_config) is not ManifestModelConfig:
            raise ManifestProtocolError("model_config must be a ManifestModelConfig")
        if (
            self.model_config.original_generation.model_call_config.seed != 30_000 + self.scheduled_attempt_index
            or self.model_config.regeneration.model_call_config.seed != 40_000 + 10 * self.scheduled_attempt_index
        ):
            raise ManifestProtocolError("paper slot seeds must follow the frozen paper namespace")
        if type(self.plan) is not ScheduledTrialPlan:
            raise ManifestProtocolError("plan must be a ScheduledTrialPlan")
        expected_replicate, expected_scenario_id = paper_queue()[self.scheduled_attempt_index]
        if (self.replicate, self.scenario.scenario_id) != (expected_replicate, expected_scenario_id):
            raise ManifestProtocolError("entry does not match the frozen paper queue")
        expected_stratum = paper_stratum_for(self.replicate, self.scenario.scenario_id)
        hidden_order, h0_order, h1_order, hidden_bit, policy_bit = _orders_for_stratum(expected_stratum)
        if (
            self.schedule_stratum is not expected_stratum
            or self.hidden_world_orientation_bit != hidden_bit
            or self.policy_orientation_bit != policy_bit
        ):
            raise ManifestProtocolError("entry does not match the frozen paper stratum schedule")
        if (
            self.plan.scheduled_attempt_ordinal != self.scheduled_attempt_index
            or self.plan.scenario_id != self.scenario.scenario_id
            or self.plan.hidden_world_order != hidden_order
            or self.plan.h0_arm_order != h0_order
            or self.plan.h1_arm_order != h1_order
        ):
            raise ManifestProtocolError("ScheduledTrialPlan does not match the paper schedule")
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
class PaperExperimentManifest:
    """The immutable 160-slot V1.3 primary Ticket paper manifest."""

    manifest_id: str
    entries: tuple[PaperManifestEntry, ...]
    primary_model_freeze: object = None

    def __post_init__(self) -> None:
        if type(self.manifest_id) is not str or self.manifest_id == "":
            raise ManifestProtocolError("manifest_id must be a non-empty string")
        if type(self.entries) is not tuple or len(self.entries) != PAPER_SLOT_COUNT:
            raise ManifestProtocolError("paper manifest must contain exactly 160 immutable entries")
        if any(type(entry) is not PaperManifestEntry for entry in self.entries):
            raise ManifestProtocolError("paper entries must contain only PaperManifestEntry values")
        for index, entry in enumerate(self.entries):
            if entry.scheduled_attempt_index != index:
                raise ManifestProtocolError("paper entries must be in slot order")
            if entry.plan.manifest_id != self.manifest_id:
                raise ManifestProtocolError("paper entry uses a different manifest_id")
        if len({entry.model_config.model_config_id for entry in self.entries}) != PAPER_SLOT_COUNT:
            raise ManifestProtocolError("paper model_config_id values must be unique per slot")
        if self.primary_model_freeze is not None:
            source = self.primary_model_freeze
            if type(source) is not dict:
                source = thaw_json_value(source)
            object.__setattr__(self, "primary_model_freeze", freeze_json_value(source))
            if any(entry.model_config.model.as_trace_model() != source["model"] for entry in self.entries):
                raise ManifestProtocolError("primary model freeze identity does not match all slots")
        self._validate_balance()

    def _validate_balance(self) -> None:
        strata = Counter(entry.schedule_stratum for entry in self.entries)
        if strata != Counter({stratum: 40 for stratum in ScheduleStratum}):
            raise ManifestProtocolError("global paper stratum balance failed")
        for scenario_id in _SCENARIO_IDS:
            selected = [entry for entry in self.entries if entry.scenario_id == scenario_id]
            if len(selected) != PAPER_REPLICATE_COUNT:
                raise ManifestProtocolError("per-scenario paper replication failed")
            if Counter(entry.schedule_stratum for entry in selected) != Counter(
                {stratum: 5 for stratum in ScheduleStratum}
            ):
                raise ManifestProtocolError("per-scenario paper stratum balance failed")
            if Counter(entry.plan.hidden_world_order[0] for entry in selected) != Counter(
                {HiddenWorld.NOT_EXECUTED: 10, HiddenWorld.EXECUTED_ACK_LOST: 10}
            ):
                raise ManifestProtocolError("per-scenario hidden-world-first balance failed")
            for world in HiddenWorld:
                if Counter(entry.plan.arm_order(world)[0] for entry in selected) != Counter(
                    {EXACT_REPLAY: 10, LLM_REGENERATION: 10}
                ):
                    raise ManifestProtocolError("per-scenario policy-first balance failed")

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(
            {
                "entries": [_entry_as_json(entry) for entry in self.entries],
                "execution_semantics_revision": INHERITED_EXECUTION_REVISION,
                "manifest_id": self.manifest_id,
                "manifest_kind": PAPER_MANIFEST_KIND,
                "paper_experiment_revision": PAPER_EXPERIMENT_REVISION,
                "primary_model_freeze": None if self.primary_model_freeze is None else thaw_json_value(self.primary_model_freeze),
                "schedule_definition": {
                    "replicates": PAPER_REPLICATE_COUNT,
                    "scenario_count": len(_SCENARIO_IDS),
                    "scenario_order": "ODD_FORWARD_EVEN_REVERSE",
                    "stratum_formula": "(zero_based_replicate_index + canonical_scenario_index) % 4",
                },
            }
        )

    @property
    def manifest_hash(self) -> str:
        return sha256_hex(self.canonical_bytes)


def _entry_as_json(entry: PaperManifestEntry) -> dict[str, object]:
    return {
        "hidden_world_orientation_bit": entry.hidden_world_orientation_bit,
        "model_config": {
            "model_config_id": entry.model_config.model_config_id,
            "model": entry.model_config.model.as_trace_model(),
            "original_generation": entry.model_config.original_generation.as_trace_sampling_configuration(),
            "regeneration": entry.model_config.regeneration.as_trace_sampling_configuration(),
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
            "hidden_world_order": [world.value for world in entry.plan.hidden_world_order],
            "manifest_id": entry.plan.manifest_id,
            "scenario_id": entry.plan.scenario_id,
            "scheduled_attempt_ordinal": entry.plan.scheduled_attempt_ordinal,
        },
    }


def build_paper_manifest(
    *, manifest_id: str, slot_model_configs: tuple[ManifestModelConfig, ...],
    primary_model_freeze: dict[str, object] | None = None,
) -> PaperExperimentManifest:
    """Materialize the exact paper schedule from explicit per-slot model inputs."""

    if type(slot_model_configs) is not tuple or len(slot_model_configs) != PAPER_SLOT_COUNT:
        raise ManifestProtocolError("slot_model_configs must contain exactly 160 configurations")
    entries: list[PaperManifestEntry] = []
    for index, (replicate, scenario_id) in enumerate(paper_queue()):
        scenario = get_scenario(scenario_id)
        stratum = paper_stratum_for(replicate, scenario_id)
        hidden_order, h0_order, h1_order, hidden_bit, policy_bit = _orders_for_stratum(stratum)
        plan = ScheduledTrialPlan(
            manifest_id=manifest_id,
            scheduled_attempt_ordinal=index,
            scenario_id=scenario_id,
            task_spec=scenario.task_spec,
            hidden_world_order=hidden_order,
            h0_arm_order=h0_order,
            h1_arm_order=h1_order,
        )
        entries.append(
            PaperManifestEntry(
                scheduled_attempt_index=index,
                replicate=replicate,
                scenario=scenario,
                hidden_world_orientation_bit=hidden_bit,
                policy_orientation_bit=policy_bit,
                schedule_stratum=stratum,
                model_config=slot_model_configs[index],
                plan=plan,
            )
        )
    return PaperExperimentManifest(manifest_id=manifest_id, entries=tuple(entries), primary_model_freeze=primary_model_freeze)


__all__ = [
    "INHERITED_EXECUTION_REVISION",
    "PAPER_EXPERIMENT_REVISION",
    "PAPER_MANIFEST_KIND",
    "PAPER_REPLICATE_COUNT",
    "PAPER_SLOT_COUNT",
    "PaperExperimentManifest",
    "PaperManifestEntry",
    "build_paper_manifest",
    "paper_queue",
    "paper_stratum_for",
]
