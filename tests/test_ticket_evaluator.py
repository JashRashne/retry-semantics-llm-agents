from __future__ import annotations

import pytest

from retry_semantics.environments.ticket import (
    PrimaryClassification,
    SourceStage,
    TicketEnvironment,
    evaluate_ticket_state,
)

EXPECTED = {
    "customer_id": "CUST-001",
    "title": "Login page timeout",
    "description": "The login page times out after 30 seconds.",
}


def _state_with(make_request, tickets: list[dict[str, str]]):
    environment = TicketEnvironment.empty()
    for index, ticket in enumerate(tickets, 1):
        request = make_request(tool_call_id=f"call-{index}", **ticket)
        environment.execute_request(
            request.serialized_request,
            source_stage=SourceStage.RECOVERY,
            arm_id="arm-evaluator",
        )
    return environment.state


@pytest.mark.parametrize(
    ("tickets", "primary", "matching", "unintended", "flags"),
    [
        (
            [EXPECTED],
            PrimaryClassification.CORRECT,
            1,
            0,
            {"correct": True},
        ),
        (
            [],
            PrimaryClassification.MISSING_EFFECT,
            0,
            0,
            {"missing_effect": True},
        ),
        (
            [EXPECTED, EXPECTED],
            PrimaryClassification.DUPLICATE_EFFECT,
            2,
            0,
            {"duplicate_effect": True},
        ),
        (
            [
                {
                    "customer_id": "CUST-WRONG",
                    "title": EXPECTED["title"],
                    "description": EXPECTED["description"],
                }
            ],
            PrimaryClassification.WRONG_MUTATION,
            0,
            1,
            {"missing_effect": True, "wrong_mutation": True},
        ),
        (
            [
                EXPECTED,
                {
                    "customer_id": "CUST-WRONG",
                    "title": "Wrong",
                    "description": "Wrong",
                },
            ],
            PrimaryClassification.EXTRA_UNINTENDED_MUTATION,
            1,
            1,
            {"wrong_mutation": True, "extra_unintended_mutation": True},
        ),
        (
            [
                EXPECTED,
                EXPECTED,
                {
                    "customer_id": "CUST-WRONG",
                    "title": "Wrong",
                    "description": "Wrong",
                },
            ],
            PrimaryClassification.DUPLICATE_EFFECT,
            2,
            1,
            {"duplicate_effect": True, "extra_unintended_mutation": True},
        ),
    ],
)
def test_golden_final_state_classifications(
    make_request, tickets, primary, matching, unintended, flags
) -> None:
    state = _state_with(make_request, tickets)

    result = evaluate_ticket_state(state, **EXPECTED)

    assert result.primary_classification is primary
    assert result.matching_ticket_count == matching
    assert result.unintended_ticket_count == unintended
    assert result.total_ticket_count == len(tickets)
    assert result.effect_multiplicity == matching
    assert result.infrastructure_failure is False
    assert result.valid_for_behavioral_analysis is True
    for name, expected_value in flags.items():
        assert getattr(result, name) is expected_value


@pytest.mark.parametrize(
    "tickets",
    [
        [],
        [EXPECTED],
        [EXPECTED, EXPECTED],
        [
            {
                "customer_id": "CUST-WRONG",
                "title": "Wrong",
                "description": "Wrong",
            }
        ],
    ],
)
def test_infrastructure_failure_has_precedence_for_all_ticket_contents(
    make_request, tickets
) -> None:
    state = _state_with(make_request, tickets)

    result = evaluate_ticket_state(
        state,
        **EXPECTED,
        infrastructure_failure_reasons=("STATE_EQUALITY_FAILURE",),
    )

    assert result.primary_classification is PrimaryClassification.INFRASTRUCTURE_FAILURE
    assert result.infrastructure_failure is True
    assert result.correct is False
    assert result.valid_for_behavioral_analysis is False
    assert result.exclusion_reasons == ("STATE_EQUALITY_FAILURE",)


def test_infrastructure_precedence_preserves_overlapping_state_defects(make_request) -> None:
    wrong = {
        "customer_id": "CUST-WRONG",
        "title": "Wrong",
        "description": "Wrong",
    }
    state = _state_with(make_request, [EXPECTED, EXPECTED, wrong])

    result = evaluate_ticket_state(
        state,
        **EXPECTED,
        infrastructure_failure=True,
    )

    assert result.primary_classification is PrimaryClassification.INFRASTRUCTURE_FAILURE
    assert result.duplicate_effect is True
    assert result.wrong_mutation is True
    assert result.extra_unintended_mutation is True


def test_matching_is_exact_decoded_string_equality(make_request) -> None:
    state = _state_with(
        make_request,
        [
            {
                "customer_id": EXPECTED["customer_id"],
                "title": EXPECTED["title"],
                "description": EXPECTED["description"] + " ",
            }
        ],
    )

    result = evaluate_ticket_state(state, **EXPECTED)

    assert result.matching_ticket_count == 0
    assert result.unintended_ticket_count == 1
    assert result.primary_classification is PrimaryClassification.WRONG_MUTATION


def test_evaluator_requires_authoritative_state(make_request) -> None:
    environment = TicketEnvironment.empty()

    with pytest.raises(TypeError, match="authoritative"):
        evaluate_ticket_state(  # type: ignore[arg-type]
            {"model_claim": "ticket created"},
            **EXPECTED,
        )
