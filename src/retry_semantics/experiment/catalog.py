"""Exact immutable V1 CREATE scenario catalog."""

from __future__ import annotations

import re
from dataclasses import dataclass

from retry_semantics.runtime.original_generation import V1CreateTicketTaskSpec

_SCENARIO_ID = re.compile(r"CREATE-[0-9]{3}").fullmatch


class ScenarioCatalogError(ValueError):
    """A value does not belong to the frozen V1 scenario catalog."""


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    """One exact, immutable catalog record."""

    scenario_id: str
    customer_id: str
    expected_title: str
    expected_description: str
    user_task: str

    def __post_init__(self) -> None:
        if type(self.scenario_id) is not str or _SCENARIO_ID(self.scenario_id) is None:
            raise ScenarioCatalogError(
                "scenario_id must match the frozen CREATE-NNN convention"
            )
        # Reuse the request-boundary validation for exact ASCII and task-template rules.
        _ = self.task_spec

    @property
    def task_spec(self) -> V1CreateTicketTaskSpec:
        return V1CreateTicketTaskSpec(
            customer_id=self.customer_id,
            expected_title=self.expected_title,
            expected_description=self.expected_description,
            user_task=self.user_task,
        )


_SCENARIOS = (
    ScenarioDefinition(
        scenario_id="CREATE-001",
        customer_id="CUST-001",
        expected_title="Login page timeout",
        expected_description="The login page times out after 30 seconds.",
        user_task=(
            'Create exactly one support ticket for customer "CUST-001" with title '
            '"Login page timeout" and description '
            '"The login page times out after 30 seconds.".'
        ),
    ),
    ScenarioDefinition(
        scenario_id="CREATE-002",
        customer_id="CUST-002",
        expected_title="Billing address update failed",
        expected_description="The new billing address is not saved.",
        user_task=(
            'Create exactly one support ticket for customer "CUST-002" with title '
            '"Billing address update failed" and description '
            '"The new billing address is not saved.".'
        ),
    ),
    ScenarioDefinition(
        scenario_id="CREATE-003",
        customer_id="CUST-003",
        expected_title="Password reset link expired",
        expected_description="The password reset link expires immediately.",
        user_task=(
            'Create exactly one support ticket for customer "CUST-003" with title '
            '"Password reset link expired" and description '
            '"The password reset link expires immediately.".'
        ),
    ),
    ScenarioDefinition(
        scenario_id="CREATE-004",
        customer_id="CUST-004",
        expected_title="Mobile app crash on upload",
        expected_description="The mobile app crashes while uploading a photo.",
        user_task=(
            'Create exactly one support ticket for customer "CUST-004" with title '
            '"Mobile app crash on upload" and description '
            '"The mobile app crashes while uploading a photo.".'
        ),
    ),
    ScenarioDefinition(
        scenario_id="CREATE-005",
        customer_id="CUST-005",
        expected_title="Order confirmation missing",
        expected_description="No confirmation appears after the order is submitted.",
        user_task=(
            'Create exactly one support ticket for customer "CUST-005" with title '
            '"Order confirmation missing" and description '
            '"No confirmation appears after the order is submitted.".'
        ),
    ),
    ScenarioDefinition(
        scenario_id="CREATE-006",
        customer_id="CUST-006",
        expected_title="Account locked after verification",
        expected_description=(
            "The account remains locked after identity verification."
        ),
        user_task=(
            'Create exactly one support ticket for customer "CUST-006" with title '
            '"Account locked after verification" and description '
            '"The account remains locked after identity verification.".'
        ),
    ),
    ScenarioDefinition(
        scenario_id="CREATE-007",
        customer_id="CUST-007",
        expected_title="Report export incomplete",
        expected_description="The exported report omits the final page.",
        user_task=(
            'Create exactly one support ticket for customer "CUST-007" with title '
            '"Report export incomplete" and description '
            '"The exported report omits the final page.".'
        ),
    ),
    ScenarioDefinition(
        scenario_id="CREATE-008",
        customer_id="CUST-008",
        expected_title="Notification settings not saved",
        expected_description="Email notification settings revert after saving.",
        user_task=(
            'Create exactly one support ticket for customer "CUST-008" with title '
            '"Notification settings not saved" and description '
            '"Email notification settings revert after saving.".'
        ),
    ),
)


def all_scenarios() -> tuple[ScenarioDefinition, ...]:
    """Return the catalog in its frozen deterministic order."""

    return _SCENARIOS


def get_scenario(scenario_id: str) -> ScenarioDefinition:
    """Return the exact frozen definition for one scenario ID."""

    if type(scenario_id) is not str:
        raise ScenarioCatalogError("scenario_id must be a string")
    for scenario in _SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise ScenarioCatalogError(f"unknown frozen scenario_id: {scenario_id!r}")


def validate_catalog_scenario(scenario: ScenarioDefinition) -> ScenarioDefinition:
    """Reject custom contents presented under a frozen scenario ID."""

    if type(scenario) is not ScenarioDefinition:
        raise ScenarioCatalogError("scenario must be a ScenarioDefinition")
    frozen = get_scenario(scenario.scenario_id)
    if scenario != frozen:
        raise ScenarioCatalogError(
            "scenario contents do not match frozen catalog entry "
            f"{scenario.scenario_id}"
        )
    return frozen


def validate_catalog_task(
    scenario_id: str, task_spec: V1CreateTicketTaskSpec
) -> ScenarioDefinition:
    """Require a task specification to exactly match its catalog ID."""

    frozen = get_scenario(scenario_id)
    if type(task_spec) is not V1CreateTicketTaskSpec:
        raise ScenarioCatalogError("task_spec must be a V1CreateTicketTaskSpec")
    if task_spec != frozen.task_spec:
        raise ScenarioCatalogError(
            f"task_spec does not match frozen catalog entry {scenario_id}"
        )
    return frozen


__all__ = [
    "ScenarioCatalogError",
    "ScenarioDefinition",
    "all_scenarios",
    "get_scenario",
    "validate_catalog_scenario",
    "validate_catalog_task",
]
