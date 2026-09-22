"""Offline Stripe semantics invariants; no provider calls or paper observations."""

import ast
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from retry_semantics.study2.candidates import STRIPE_CUSTOMERS
from retry_semantics.study2.contracts import (
    ContractValidationError,
    DesignStatus,
    IdempotencyCapability,
    ObservationInput,
    RuntimeKeyRequirement,
)
from retry_semantics.study2.stripe_semantics import (
    STRIPE_CUSTOMER_SEMANTICS as FACTS,
    STRIPE_ENGINEERING_SCOPE as SCOPE,
    STRIPE_IDEMPOTENCY_SEMANTICS as IDEMPOTENCY,
    STRIPE_OBSERVATION_REQUIREMENTS as READ,
)


MODULE = Path(__file__).resolve().parents[1] / "src/retry_semantics/study2/stripe_semantics.py"


def test_module_is_declarative_and_has_no_provider_or_network_execution_path() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not imported_roots & {
        "stripe", "httpx", "requests", "urllib", "socket", "ssl", "os",
    }
    assert not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree))
    assert SCOPE.provider_call_performed is False
    assert SCOPE.credentials_required_by_slice is False


def test_customer_create_and_list_endpoint_mapping_is_documented() -> None:
    assert FACTS.mutation == ("POST", "/v1/customers")
    assert FACTS.observation == ("GET", "/v1/customers")
    assert FACTS.mutation_name == "create_customer"
    assert FACTS.observation_name == "list_customers"
    assert FACTS.customer_id_field == "id"
    assert FACTS.livemode_field == "livemode"
    assert FACTS.mutation_accepts_correlation_field
    assert FACTS.prohibited_mutation_parameters == ("test_clock",)
    assert FACTS.mutation_schema_exclusion_enforced is False


def test_exact_synthetic_email_is_the_required_pre_dispatch_marker() -> None:
    assert FACTS.correlation_field == READ.filter_parameter == "email"
    assert READ.match_rule == "exact_case_sensitive"
    assert READ.marker_origin == "unique_synthetic_pre_dispatch"
    assert READ.real_person_email_allowed is False
    assert READ.required_inputs == STRIPE_CUSTOMERS.observation.required_inputs
    assert set(READ.required_inputs) == {
        ObservationInput.TARGET_SCOPE, ObservationInput.STUDY_MARKER,
    }
    assert FACTS.metadata_role == "optional_supplemental_context"


def test_customer_search_is_never_the_authoritative_observer() -> None:
    assert FACTS.rejected_authoritative_observation == ("GET", "/v1/customers/search")
    assert READ.customer_search_authoritative is False
    assert len(READ.customer_search_rejection_reasons) == 3
    assert any("lag" in reason for reason in READ.customer_search_rejection_reasons)
    assert any("India" in reason for reason in READ.customer_search_rejection_reasons)


def test_complete_observation_requires_all_cursor_pages_not_first_match() -> None:
    assert READ.pagination_cursor == "starting_after"
    assert READ.page_completeness_signal == "has_more"
    assert READ.maximum_page_limit == 100
    assert READ.pagination == "follow_starting_after_until_exhausted"
    assert READ.inspect_all_matching_pages
    assert READ.process_every_returned_customer
    assert READ.continue_while_has_more
    assert READ.advance_requires_usable_final_customer_id
    assert READ.malformed_pagination_result == "unknown_or_incomplete"
    assert READ.first_match_lookup_allowed is False
    assert READ.partial_read_is_complete is False
    assert READ.strict_list_consistency_documented is False
    assert READ.read_after_write_visibility_qualified is False


def test_test_clock_is_prohibited_to_preserve_list_completeness() -> None:
    assert READ.omitted_test_clock_excludes_associated_customers
    assert READ.arbitrary_test_clock_observation_supported is False
    assert "Enforce a frozen Customer mutation schema that rejects test_clock." in SCOPE.unresolved_items
    constraints = " ".join(STRIPE_CUSTOMERS.observation.constraints)
    assert "mutation schema must reject test_clock" in constraints
    assert "arbitrary test-clock observation is not supported" in constraints


def test_idempotency_is_client_supplied_deferred_and_runtime_owned_if_enabled() -> None:
    assert STRIPE_CUSTOMERS.idempotency.capability is IdempotencyCapability.CLIENT_SUPPLIED_KEY
    assert IDEMPOTENCY.client_supplied
    assert IDEMPOTENCY.header == STRIPE_CUSTOMERS.idempotency.mechanism == "Idempotency-Key"
    assert IDEMPOTENCY.enabled_by_this_semantics_slice is False
    assert IDEMPOTENCY.enablement == "explicit_future_runtime_or_protocol_decision"
    assert set(IDEMPOTENCY.runtime_key_requirements) == set(RuntimeKeyRequirement)
    assert IDEMPOTENCY.runtime_key_requirements == STRIPE_CUSTOMERS.idempotency.runtime_key_requirements
    assert IDEMPOTENCY.stable_key_scope == "one_original_mutation_within_one_experimental_arm"
    assert IDEMPOTENCY.independent_key_namespace_per_arm
    assert IDEMPOTENCY.cross_arm_key_reuse_allowed is False
    assert IDEMPOTENCY.cross_family_key_reuse_allowed is False
    assert IDEMPOTENCY.cross_run_key_reuse_allowed is False
    assert IDEMPOTENCY.provider_idempotency_is_retry_policy is False


def test_documented_key_retention_execution_and_parameter_mismatch_caveats() -> None:
    assert IDEMPOTENCY.record_created_only_after_endpoint_execution_begins
    assert IDEMPOTENCY.pre_execution_rejection_may_lack_record
    assert set(IDEMPOTENCY.stored_result_parts) == {"status_code", "response_body"}
    assert IDEMPOTENCY.retained_same_key_returns_stored_result
    assert IDEMPOTENCY.same_key_parameters_must_match
    assert IDEMPOTENCY.parameter_mismatch_result == "error"
    assert IDEMPOTENCY.key_may_be_pruned_after_at_least_hours == 24


def test_ack_dependent_headers_are_supplemental_only() -> None:
    assert FACTS.request_id_header == "Request-Id"
    assert FACTS.request_id_required_under_ack_loss is False
    assert FACTS.request_id_role == "supplemental_when_acknowledgement_exists"
    assert READ.supplemental_inputs == (ObservationInput.RESPONSE_ID,)
    assert ObservationInput.RESPONSE_ID not in READ.required_inputs
    assert IDEMPOTENCY.replay_header == "Idempotent-Replayed"
    assert IDEMPOTENCY.replay_header_value == "true"
    assert IDEMPOTENCY.replay_header_required_for_state_correctness is False


def test_test_only_api_version_and_ambiguous_stage_boundaries_are_explicit() -> None:
    assert SCOPE.documentation_reviewed_on == "2026-09-21"
    assert "/api/customers/list" in SCOPE.official_reference_paths
    assert "/api/customers/search" in SCOPE.official_reference_paths
    assert set(SCOPE.test_key_prefixes) == {"rk_test_", "sk_test_"}
    assert SCOPE.live_mode_credentials_allowed is False
    assert SCOPE.required_customer_livemode is False
    assert SCOPE.reviewed_candidate_api_version == "2026-08-26.dahlia"
    assert SCOPE.explicit_api_version_pin_required_later
    assert SCOPE.ambiguous_outcome_stages == (
        "dispatch_initiated", "local_send_completed", "remote_received",
        "remote_committed", "acknowledgement_returned",
    )
    assert SCOPE.stages_are_not_equivalent


def test_documented_mappings_do_not_freeze_the_overall_capability() -> None:
    assert STRIPE_CUSTOMERS.mutation.status is DesignStatus.PROVISIONAL
    assert STRIPE_CUSTOMERS.observation.status is DesignStatus.PROVISIONAL
    assert STRIPE_CUSTOMERS.status is DesignStatus.PROVISIONAL
    assert STRIPE_CUSTOMERS.correlation.status is DesignStatus.PROVISIONAL
    assert STRIPE_CUSTOMERS.isolation.status is DesignStatus.UNRESOLVED
    assert READ.read_after_write_visibility_qualified is False
    assert SCOPE.protocol_status == "draft_not_frozen"
    assert SCOPE.unresolved_items
    with pytest.raises(ContractValidationError, match="unresolved prerequisites"):
        replace(STRIPE_CUSTOMERS, status=DesignStatus.ESTABLISHED)


def test_semantics_records_are_frozen_hashable_and_fail_closed() -> None:
    for record in (FACTS, READ, IDEMPOTENCY, SCOPE):
        with pytest.raises(FrozenInstanceError):
            setattr(record, fields(record)[0].name, None)
        hash(record)
    assert READ.first_match_lookup_allowed is False
    assert READ.partial_read_is_complete is False
    assert READ.customer_search_authoritative is False
    assert READ.arbitrary_test_clock_observation_supported is False
    assert IDEMPOTENCY.enabled_by_this_semantics_slice is False
    assert IDEMPOTENCY.cross_arm_key_reuse_allowed is False
    assert SCOPE.provider_call_performed is False
    assert SCOPE.credentials_required_by_slice is False
    assert SCOPE.live_mode_credentials_allowed is False


def test_slice_introduces_zero_paper_observations() -> None:
    assert SCOPE.evidence_kind == "engineering_design_only"
    assert SCOPE.paper_observations == 0
    assert not any(field.name in {"rows", "trials", "results"} for field in fields(SCOPE))
