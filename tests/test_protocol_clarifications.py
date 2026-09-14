from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_DIR = REPOSITORY_ROOT / "research" / "protocol"


def _read_protocol(name: str) -> str:
    return (PROTOCOL_DIR / name).read_text(encoding="utf-8")


def _trace_schema() -> dict:
    return json.loads(_read_protocol("trace_schema_v1.json"))


def _single_line(text: str) -> str:
    return " ".join(text.split())


@pytest.mark.parametrize(
    ("base_seed", "expected"),
    [
        (100, (100, 101, 102, 103)),
        (0, (0, 1, 2, 3)),
        (None, (None, None, None, None)),
    ],
)
def test_frozen_seed_formula_has_the_specified_results(base_seed, expected) -> None:
    protocol = _read_protocol("primary_experiment_v1.md")

    assert (
        "derived_seed(model_call_index) = base_seed + model_call_index" in protocol
    )
    assert tuple(
        None if base_seed is None else base_seed + call_index
        for call_index in range(4)
    ) == expected


def test_seed_derivation_is_bounded_matched_and_world_independent() -> None:
    primary = _single_line(_read_protocol("primary_experiment_v1.md"))
    invariants = _single_line(_read_protocol("protocol_invariants_v1.md"))

    assert "`model_call_index`, defined strictly as the zero-based ordinal" in primary
    assert "`model_call_index > 3`" in primary
    assert "If the base seed is absent or null, every derived seed is null" in primary
    for forbidden_input in (
        "hidden-world identity",
        "arm identity",
        "tool-action attempt count",
        "model output",
        "authoritative state",
        "hashing",
        "randomness",
        "modulo",
        "wrapping",
    ):
        assert forbidden_input in primary
        assert forbidden_input in invariants
    assert (
        "same derived seed at every model-call index present in both trajectories"
        in primary
    )
    assert "do not guarantee deterministic provider output" in primary


def test_two_actions_from_one_response_advance_model_ordinal_only_once() -> None:
    primary = _single_line(_read_protocol("primary_experiment_v1.md"))
    base_seed = 100
    first_response = {
        "model_call_index": 0,
        "tool_action_attempt_counts": (1, 2),
    }
    following_call_index = first_response["model_call_index"] + 1

    assert "One model response may consume multiple tool attempts" in primary
    assert "MUST NOT be reinvoked between tool requests" in primary
    assert first_response["tool_action_attempt_counts"] == (1, 2)
    assert following_call_index == 1
    assert base_seed + following_call_index == 101
    assert "the single permitted final model invocation has `model_call_index=1`" in (
        primary
    )
    forbidden_sequence = (
        "model call 0 -> tool request A -> model call 1 -> old tool request B"
    )
    assert forbidden_sequence not in primary


def test_trace_schema_bounds_zero_based_regeneration_call_indexes() -> None:
    action = _trace_schema()["$defs"]["recoveryAction"]
    model_call_index = action["properties"]["model_call_index"]

    assert model_call_index["type"] == ["integer", "null"]
    assert model_call_index["minimum"] == 0
    assert model_call_index["maximum"] == 3
    assert "independent of tool-action attempt count" in model_call_index["description"]

    attempted = _trace_schema()["$defs"]["usage"]["properties"][
        "recovery_tool_calls_attempted"
    ]
    assert attempted["minimum"] == 0
    assert attempted["maximum"] == 4
    assert "independent of model_call_index" in attempted["description"]


def test_budget_boundary_counts_only_first_over_budget_request() -> None:
    primary = _single_line(_read_protocol("primary_experiment_v1.md"))
    schema = _trace_schema()
    actions = schema["properties"]["recovery_actions"]
    usage = schema["$defs"]["usage"]["properties"]
    recovery_action = schema["$defs"]["recoveryAction"]
    budget_rule = recovery_action["allOf"][0]
    rejected = budget_rule["then"]["properties"]

    assert actions["maxItems"] == 4
    assert usage["recovery_tool_calls_attempted"]["maximum"] == 4
    assert usage["recovery_tool_calls_executed"]["maximum"] == 3
    assert budget_rule["if"]["properties"]["action_type"]["const"] == (
        "BUDGET_REJECTED_TOOL_CALL"
    )
    assert rejected["actor"]["const"] == "MODEL"
    assert rejected["validation_status"]["const"] == "NOT_APPLICABLE"
    assert rejected["executed"]["const"] is False
    assert rejected["mutating"]["const"] is False
    assert rejected["committed_effect_event_ids"]["maxItems"] == 0

    supplied_request_count = 10
    tool_action_attempt_count = min(supplied_request_count, 3)
    recovery_tool_calls_attempted = min(supplied_request_count, 4)
    unprocessed_raw_calls = supplied_request_count - recovery_tool_calls_attempted
    assert tool_action_attempt_count == 3
    assert recovery_tool_calls_attempted == 4
    assert unprocessed_raw_calls == 6
    assert "It never becomes four" in primary
    assert "not separately processed" in primary


def test_rejected_generation_termination_is_frozen_as_behavioral() -> None:
    primary = _single_line(_read_protocol("primary_experiment_v1.md"))
    invariants = _single_line(_read_protocol("protocol_invariants_v1.md"))
    schema = _trace_schema()

    assert "model_rejected_generation" in schema["properties"][
        "termination_reason"
    ]["enum"]
    assert "valid post-treatment behavioral observation" in primary
    assert "not an infrastructure failure or pre-treatment eligibility failure" in primary
    assert "failed invocation consumes zero Regeneration tool-action attempts" in primary
    assert "terminate without retry or a fabricated observation" in invariants
    assert "evaluate the authoritative state reached so far" in invariants
    assert (
        "termination is `model_rejected_generation`, not `action_budget_exceeded`"
        in primary
    )


def test_rejected_generation_trace_requires_nonexcluding_behavioral_evidence() -> None:
    schema = _trace_schema()
    evidence = schema["$defs"]["rejectedGenerationEvidence"]
    error = schema["$defs"]["error"]
    rejected_rule = next(
        rule
        for rule in schema["allOf"]
        if rule.get("if", {})
        .get("properties", {})
        .get("termination_reason", {})
        .get("const")
        == "model_rejected_generation"
    )
    required_error = rejected_rule["then"]["properties"]["errors"]["contains"]

    assert evidence["additionalProperties"] is False
    assert evidence["required"] == [
        "provider",
        "provider_error_code",
        "failed_generation",
        "provider_request_id",
        "model_call_index",
        "derived_seed",
    ]
    assert error["properties"]["rejected_generation"] == {
        "$ref": "#/$defs/rejectedGenerationEvidence",
        "description": (
            "Present for MODEL_REJECTED_GENERATION to preserve the existing "
            "readable behavioral evidence."
        ),
    }
    assert required_error["properties"]["category"]["const"] == "BEHAVIORAL"
    assert required_error["properties"]["code"]["const"] == (
        "MODEL_REJECTED_GENERATION"
    )
    assert required_error["properties"]["behavioral"]["const"] is True
    assert required_error["properties"]["caused_exclusion"]["const"] is False
    assert "rejected_generation" in required_error["required"]

    rejected_usage = rejected_rule["then"]["properties"]["usage"]["properties"]
    assert rejected_usage["additional_llm_calls"]["minimum"] == 1
    assert evidence["properties"]["model_call_index"]["minimum"] == 0
    assert evidence["properties"]["model_call_index"]["maximum"] == 3


def test_rejected_invocation_counts_as_llm_call_but_not_tool_action() -> None:
    primary = _single_line(_read_protocol("primary_experiment_v1.md"))
    base_seed = 50
    rejected_model_call_index = 2

    assert "first-call rejection has `model_call_index=0`" in primary
    assert "`additional_llm_calls=1`, and zero tool-action attempts" in primary
    assert "rejection at index 2 after two earlier invocations" in primary
    assert "`additional_llm_calls=3`" in primary
    assert base_seed + rejected_model_call_index == 52
    assert "No recovery-action record is manufactured" in primary


def test_experiment_revision_is_v1_2_and_schema_version_remains_v1() -> None:
    schema = _trace_schema()
    primary = _read_protocol("primary_experiment_v1.md")
    invariants = _read_protocol("protocol_invariants_v1.md")
    versioned_source_files = (
        REPOSITORY_ROOT / "src" / "retry_semantics" / "serialization.py",
        REPOSITORY_ROOT / "src" / "retry_semantics" / "environments" / "ticket.py",
        REPOSITORY_ROOT
        / "src"
        / "retry_semantics"
        / "runtime"
        / "regeneration_context.py",
    )

    assert "Experiment version: `primary-create-v1.2`" in primary
    assert "version `primary-create-v1.2`" in invariants
    assert schema["properties"]["experiment_version"]["const"] == (
        "primary-create-v1.2"
    )
    assert schema["properties"]["schema_version"]["const"] == "trace-schema-v1"
    for path in versioned_source_files:
        assert "primary-create-v1.2" in path.read_text(encoding="utf-8")
    for text in (primary, invariants, json.dumps(schema)):
        assert re.search(r"primary-create-v1(?!\.)", text) is None


def test_clarification_is_pre_experiment_and_executor_is_now_covered() -> None:
    primary = _single_line(_read_protocol("primary_experiment_v1.md"))
    coverage = _single_line(
        (REPOSITORY_ROOT / "tests" / "PROTOCOL_COVERAGE.md").read_text(
            encoding="utf-8"
        )
    )

    assert "Revision 1.2 was finalized before any live experimental run" in primary
    assert "Revision 1.1 was finalized before any live experimental run" in primary
    assert "bounded Regeneration executor" in coverage
    assert "base_seed + model_call_index" in coverage
