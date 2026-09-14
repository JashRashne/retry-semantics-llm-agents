from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from retry_semantics.experiment.catalog import (
    ScenarioCatalogError,
    ScenarioDefinition,
    all_scenarios,
    get_scenario,
    validate_catalog_scenario,
    validate_catalog_task,
)
from retry_semantics.models import ModelRequestError
from retry_semantics.runtime.original_generation import V1CreateTicketTaskSpec


EXPECTED_CATALOG = (
    (
        "CREATE-001",
        "CUST-001",
        "Login page timeout",
        "The login page times out after 30 seconds.",
        'Create exactly one support ticket for customer "CUST-001" with title '
        '"Login page timeout" and description '
        '"The login page times out after 30 seconds.".',
    ),
    (
        "CREATE-002",
        "CUST-002",
        "Billing address update failed",
        "The new billing address is not saved.",
        'Create exactly one support ticket for customer "CUST-002" with title '
        '"Billing address update failed" and description '
        '"The new billing address is not saved.".',
    ),
    (
        "CREATE-003",
        "CUST-003",
        "Password reset link expired",
        "The password reset link expires immediately.",
        'Create exactly one support ticket for customer "CUST-003" with title '
        '"Password reset link expired" and description '
        '"The password reset link expires immediately.".',
    ),
    (
        "CREATE-004",
        "CUST-004",
        "Mobile app crash on upload",
        "The mobile app crashes while uploading a photo.",
        'Create exactly one support ticket for customer "CUST-004" with title '
        '"Mobile app crash on upload" and description '
        '"The mobile app crashes while uploading a photo.".',
    ),
    (
        "CREATE-005",
        "CUST-005",
        "Order confirmation missing",
        "No confirmation appears after the order is submitted.",
        'Create exactly one support ticket for customer "CUST-005" with title '
        '"Order confirmation missing" and description '
        '"No confirmation appears after the order is submitted.".',
    ),
    (
        "CREATE-006",
        "CUST-006",
        "Account locked after verification",
        "The account remains locked after identity verification.",
        'Create exactly one support ticket for customer "CUST-006" with title '
        '"Account locked after verification" and description '
        '"The account remains locked after identity verification.".',
    ),
    (
        "CREATE-007",
        "CUST-007",
        "Report export incomplete",
        "The exported report omits the final page.",
        'Create exactly one support ticket for customer "CUST-007" with title '
        '"Report export incomplete" and description '
        '"The exported report omits the final page.".',
    ),
    (
        "CREATE-008",
        "CUST-008",
        "Notification settings not saved",
        "Email notification settings revert after saving.",
        'Create exactly one support ticket for customer "CUST-008" with title '
        '"Notification settings not saved" and description '
        '"Email notification settings revert after saving.".',
    ),
)


def _catalog_values() -> tuple[tuple[str, str, str, str, str], ...]:
    return tuple(
        (
            scenario.scenario_id,
            scenario.customer_id,
            scenario.expected_title,
            scenario.expected_description,
            scenario.user_task,
        )
        for scenario in all_scenarios()
    )


def test_catalog_exactly_matches_all_eight_frozen_scenarios() -> None:
    assert _catalog_values() == EXPECTED_CATALOG
    assert len(all_scenarios()) == 8
    assert len({scenario.scenario_id for scenario in all_scenarios()}) == 8


def test_catalog_values_and_materialized_tasks_satisfy_frozen_constraints() -> None:
    for scenario in all_scenarios():
        values = (
            scenario.customer_id,
            scenario.expected_title,
            scenario.expected_description,
        )
        assert all(value for value in values)
        assert all('"' not in value for value in values)
        assert all(
            0x20 <= ord(character) <= 0x7E
            for value in values
            for character in value
        )
        assert scenario.user_task == (
            f'Create exactly one support ticket for customer "{scenario.customer_id}" '
            f'with title "{scenario.expected_title}" and description '
            f'"{scenario.expected_description}".'
        )
        assert type(scenario.task_spec) is V1CreateTicketTaskSpec


def test_catalog_order_and_lookup_are_deterministic() -> None:
    first = all_scenarios()
    second = all_scenarios()

    assert type(first) is tuple
    assert first is second
    assert tuple(scenario.scenario_id for scenario in first) == tuple(
        f"CREATE-{ordinal:03d}" for ordinal in range(1, 9)
    )
    for scenario in first:
        assert get_scenario(scenario.scenario_id) is scenario
        assert validate_catalog_scenario(scenario) is scenario
        assert validate_catalog_task(scenario.scenario_id, scenario.task_spec) is (
            scenario
        )


@pytest.mark.parametrize("scenario_id", ["CREATE-000", "CREATE-009", "OTHER-001"])
def test_unknown_scenario_ids_fail(scenario_id: str) -> None:
    with pytest.raises(ScenarioCatalogError, match="unknown frozen scenario_id"):
        get_scenario(scenario_id)


def test_known_id_rejects_another_scenarios_exact_task() -> None:
    with pytest.raises(ScenarioCatalogError, match="does not match"):
        validate_catalog_task("CREATE-003", get_scenario("CREATE-002").task_spec)


def test_known_id_rejects_modified_scenario_contents() -> None:
    modified = replace(
        get_scenario("CREATE-003"),
        expected_description="The password reset link expires immediately!",
        user_task=(
            'Create exactly one support ticket for customer "CUST-003" with title '
            '"Password reset link expired" and description '
            '"The password reset link expires immediately!".'
        ),
    )

    with pytest.raises(ScenarioCatalogError, match="do not match"):
        validate_catalog_scenario(modified)
    with pytest.raises(ScenarioCatalogError, match="does not match"):
        validate_catalog_task("CREATE-003", modified.task_spec)


def test_malformed_scenario_values_and_task_text_fail() -> None:
    with pytest.raises(ModelRequestError, match="printable ASCII"):
        ScenarioDefinition(
            scenario_id="CREATE-001",
            customer_id="CUST-001\n",
            expected_title="Login page timeout",
            expected_description="The login page times out after 30 seconds.",
            user_task="invalid",
        )
    with pytest.raises(ModelRequestError, match="exactly match"):
        ScenarioDefinition(
            scenario_id="CREATE-001",
            customer_id="CUST-001",
            expected_title="Login page timeout",
            expected_description="The login page times out after 30 seconds.",
            user_task="modified task",
        )


def test_catalog_and_scenarios_are_immutable() -> None:
    scenarios = all_scenarios()

    with pytest.raises(FrozenInstanceError):
        scenarios[0].scenario_id = "CREATE-008"  # type: ignore[misc]
    extended = scenarios + (scenarios[0],)
    assert len(extended) == 9
    assert all_scenarios() is scenarios
    assert len(all_scenarios()) == 8
