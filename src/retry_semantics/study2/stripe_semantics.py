"""Offline Stripe documentation evidence; not an adapter or frozen protocol.

The official-documentation facts represented here were supplied as checked on
2026-09-21.  This module performs no dispatch, credential lookup, observation,
replay, regeneration, or paper-data collection.
"""

from dataclasses import dataclass, field
from typing import Literal

from retry_semantics.study2.contracts import ObservationInput, RuntimeKeyRequirement


@dataclass(frozen=True, slots=True)
class StripeCustomerSemantics:
    """Documented Customer endpoint and response facts for later qualification."""

    mutation: tuple[str, str] = field(default=("POST", "/v1/customers"), init=False)
    observation: tuple[str, str] = field(default=("GET", "/v1/customers"), init=False)
    rejected_authoritative_observation: tuple[str, str] = field(
        default=("GET", "/v1/customers/search"), init=False,
    )
    mutation_name: Literal["create_customer"] = field(default="create_customer", init=False)
    observation_name: Literal["list_customers"] = field(default="list_customers", init=False)
    customer_id_field: Literal["id"] = field(default="id", init=False)
    livemode_field: Literal["livemode"] = field(default="livemode", init=False)
    correlation_field: Literal["email"] = field(default="email", init=False)
    mutation_accepts_correlation_field: bool = field(default=True, init=False)
    prohibited_mutation_parameters: tuple[Literal["test_clock"], ...] = field(
        default=("test_clock",), init=False,
    )
    mutation_schema_exclusion_enforced: bool = field(default=False, init=False)
    metadata_role: Literal["optional_supplemental_context"] = field(
        default="optional_supplemental_context", init=False,
    )
    request_id_header: Literal["Request-Id"] = field(default="Request-Id", init=False)
    request_id_required_under_ack_loss: bool = field(default=False, init=False)
    request_id_role: Literal["supplemental_when_acknowledgement_exists"] = field(
        default="supplemental_when_acknowledgement_exists", init=False,
    )


@dataclass(frozen=True, slots=True)
class StripeObservationRequirements:
    """Minimum complete-read design obligations, not a consistency guarantee."""

    filter_parameter: Literal["email"] = field(default="email", init=False)
    match_rule: Literal["exact_case_sensitive"] = field(
        default="exact_case_sensitive", init=False,
    )
    marker_origin: Literal["unique_synthetic_pre_dispatch"] = field(
        default="unique_synthetic_pre_dispatch", init=False,
    )
    real_person_email_allowed: bool = field(default=False, init=False)
    first_match_lookup_allowed: bool = field(default=False, init=False)
    pagination_cursor: Literal["starting_after"] = field(default="starting_after", init=False)
    page_completeness_signal: Literal["has_more"] = field(default="has_more", init=False)
    maximum_page_limit: int = field(default=100, init=False)
    pagination: Literal["follow_starting_after_until_exhausted"] = field(
        default="follow_starting_after_until_exhausted", init=False,
    )
    inspect_all_matching_pages: bool = field(default=True, init=False)
    process_every_returned_customer: bool = field(default=True, init=False)
    continue_while_has_more: bool = field(default=True, init=False)
    advance_requires_usable_final_customer_id: bool = field(default=True, init=False)
    malformed_pagination_result: Literal["unknown_or_incomplete"] = field(
        default="unknown_or_incomplete", init=False,
    )
    partial_read_is_complete: bool = field(default=False, init=False)
    omitted_test_clock_excludes_associated_customers: bool = field(default=True, init=False)
    arbitrary_test_clock_observation_supported: bool = field(default=False, init=False)
    customer_search_authoritative: bool = field(default=False, init=False)
    customer_search_rejection_reasons: tuple[str, ...] = field(default=(
        "Stripe warns against Customer Search for strict-consistency read-after-write flows.",
        "Customer Search propagation may lag.",
        "Customer Search is unavailable to merchants in India.",
    ), init=False)
    strict_list_consistency_documented: bool = field(default=False, init=False)
    read_after_write_visibility_qualified: bool = field(default=False, init=False)
    required_inputs: tuple[ObservationInput, ...] = field(default=(
        ObservationInput.TARGET_SCOPE, ObservationInput.STUDY_MARKER,
    ), init=False)
    supplemental_inputs: tuple[ObservationInput, ...] = field(
        default=(ObservationInput.RESPONSE_ID,), init=False,
    )


@dataclass(frozen=True, slots=True)
class StripeIdempotencySemantics:
    """Provider key behavior, kept separate from agent retry policy."""

    applicable_method: Literal["POST"] = field(default="POST", init=False)
    header: Literal["Idempotency-Key"] = field(default="Idempotency-Key", init=False)
    client_supplied: bool = field(default=True, init=False)
    enabled_by_this_semantics_slice: bool = field(default=False, init=False)
    enablement: Literal["explicit_future_runtime_or_protocol_decision"] = field(
        default="explicit_future_runtime_or_protocol_decision", init=False,
    )
    runtime_key_requirements: tuple[RuntimeKeyRequirement, ...] = field(
        default=tuple(RuntimeKeyRequirement), init=False,
    )
    stable_key_scope: Literal[
        "one_original_mutation_within_one_experimental_arm"
    ] = field(default="one_original_mutation_within_one_experimental_arm", init=False)
    independent_key_namespace_per_arm: bool = field(default=True, init=False)
    cross_arm_key_reuse_allowed: bool = field(default=False, init=False)
    cross_family_key_reuse_allowed: bool = field(default=False, init=False)
    cross_run_key_reuse_allowed: bool = field(default=False, init=False)
    record_created_only_after_endpoint_execution_begins: bool = field(
        default=True, init=False,
    )
    pre_execution_rejection_may_lack_record: bool = field(default=True, init=False)
    stored_result_parts: tuple[str, ...] = field(
        default=("status_code", "response_body"), init=False,
    )
    retained_same_key_returns_stored_result: bool = field(default=True, init=False)
    same_key_parameters_must_match: bool = field(default=True, init=False)
    parameter_mismatch_result: Literal["error"] = field(default="error", init=False)
    key_may_be_pruned_after_at_least_hours: int = field(default=24, init=False)
    replay_header: Literal["Idempotent-Replayed"] = field(
        default="Idempotent-Replayed", init=False,
    )
    replay_header_value: Literal["true"] = field(default="true", init=False)
    replay_header_required_for_state_correctness: bool = field(default=False, init=False)
    provider_idempotency_is_retry_policy: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class StripeEngineeringScope:
    """Fail-closed boundaries and unresolved work before any live engineering call."""

    documentation_reviewed_on: Literal["2026-09-21"] = field(
        default="2026-09-21", init=False,
    )
    official_reference_paths: tuple[str, ...] = field(default=(
        "/api/idempotent_requests",
        "/api/customers/create",
        "/api/customers/list",
        "/api/customers/search",
        "/api/request_ids",
        "/api/authentication",
        "/api/versioning",
        "/keys",
        "/error-low-level",
    ), init=False)
    evidence_kind: Literal["engineering_design_only"] = field(
        default="engineering_design_only", init=False,
    )
    protocol_status: Literal["draft_not_frozen"] = field(
        default="draft_not_frozen", init=False,
    )
    paper_observations: Literal[0] = field(default=0, init=False)
    provider_call_performed: bool = field(default=False, init=False)
    credentials_required_by_slice: bool = field(default=False, init=False)
    test_key_prefixes: tuple[str, ...] = field(
        default=("rk_test_", "sk_test_"), init=False,
    )
    live_mode_credentials_allowed: bool = field(default=False, init=False)
    required_customer_livemode: Literal[False] = field(default=False, init=False)
    reviewed_candidate_api_version: Literal["2026-08-26.dahlia"] = field(
        default="2026-08-26.dahlia", init=False,
    )
    explicit_api_version_pin_required_later: bool = field(default=True, init=False)
    ambiguous_outcome_stages: tuple[str, ...] = field(default=(
        "dispatch_initiated",
        "local_send_completed",
        "remote_received",
        "remote_committed",
        "acknowledgement_returned",
    ), init=False)
    stages_are_not_equivalent: bool = field(default=True, init=False)
    unresolved_items: tuple[str, ...] = field(default=(
        "Exact synthetic email marker encoding and namespace.",
        "Sandbox account and principal isolation from stale and engineering Customers.",
        "Enforce a frozen Customer mutation schema that rejects test_clock.",
        "Read-after-write visibility and convergence through complete list pagination.",
        "Final runtime decision to enable or omit an Idempotency-Key.",
        "Chosen client transport, hidden retries, error classification, and header capture.",
        "Frozen protocol API version, timing, polling, and termination rules.",
    ), init=False)


STRIPE_CUSTOMER_SEMANTICS = StripeCustomerSemantics()
STRIPE_OBSERVATION_REQUIREMENTS = StripeObservationRequirements()
STRIPE_IDEMPOTENCY_SEMANTICS = StripeIdempotencySemantics()
STRIPE_ENGINEERING_SCOPE = StripeEngineeringScope()
