"""Offline structural validation only; no external state or observations."""

from dataclasses import FrozenInstanceError, fields, replace

import pytest

from retry_semantics.study2.candidates import (
    GITHUB_ISSUES,
    GOOGLE_SHEETS_ROWS,
    PROVISIONAL_CAPABILITIES,
)
from retry_semantics.study2.contracts import (
    ContractValidationError,
    CorrelationBasis,
    CorrelationCapability,
    DesignStatus,
    IdempotencyCapability,
    IsolationBoundary,
    IsolationRequirements,
    MutationOperation,
    ObservationInput,
    ObservationOperation,
    OperationCapability,
    Provider,
    ProviderIdempotency,
    RequestIdentityPart,
    RuntimeKeyRequirement,
)

_SYNTHETIC_CLIENT_KEY = ProviderIdempotency(
    capability=IdempotencyCapability.CLIENT_SUPPLIED_KEY,
    basis="Synthetic client-key capability for generic contract validation.",
    mechanism="synthetic-key",
    runtime_key_requirements=tuple(RuntimeKeyRequirement),
    key_reuse_constraints=(
        "A runtime-owned key is stable for retries and recovery attempts for one original mutation within one experimental arm.",
        "Replay and Regeneration arms use independent keys or namespaces; keys are not shared across arms, families, or runs.",
        "Changed mutation parameters under the same key may be attempted; a provider may return a mismatch error.",
    ),
)


def test_provisional_candidates_are_distinct_operations_for_each_provider() -> None:
    assert [(c.provider, c.mutation.name, c.observation.name, c.mutation.resource)
            for c in PROVISIONAL_CAPABILITIES] == [
        (Provider.GITHUB, "create_issue", "list_issues", "issue"),
        (Provider.GOOGLE_SHEETS, "append_row", "list_rows", "row"),
    ]
    for candidate in PROVISIONAL_CAPABILITIES:
        assert candidate.mutation.state_mutating is True
        assert candidate.observation.state_mutating is False
        assert candidate.mutation.resource == candidate.observation.resource


@pytest.mark.parametrize("candidate", PROVISIONAL_CAPABILITIES)
def test_candidate_explicitly_describes_identity_correlation_and_isolation(candidate) -> None:
    assert set(candidate.mutation.stable_request_parts) == set(RequestIdentityPart)
    assert set(candidate.observation.required_inputs) == {
        ObservationInput.TARGET_SCOPE, ObservationInput.STUDY_MARKER,
    }
    assert candidate.status is DesignStatus.PROVISIONAL
    assert candidate.mutation.status is DesignStatus.PROVISIONAL
    assert candidate.observation.status is DesignStatus.PROVISIONAL
    assert candidate.correlation.status is DesignStatus.PROVISIONAL
    assert candidate.correlation.pre_dispatch_marker_supported is True
    assert candidate.correlation.basis is CorrelationBasis.SCOPE_AND_MARKER
    assert candidate.observation.supplemental_inputs == (ObservationInput.RESPONSE_ID,)
    assert candidate.isolation.status is DesignStatus.UNRESOLVED
    assert set(candidate.isolation.distinguish_from) == set(IsolationBoundary)
    assert candidate.observation.constraints
    assert candidate.correlation.constraints
    assert candidate.isolation.constraints


def test_idempotency_can_change_without_changing_mutation_or_observation() -> None:
    no_documented_mechanism = ProviderIdempotency(
        IdempotencyCapability.NO_DOCUMENTED_CLIENT_MECHANISM,
        "Synthetic structural example, not a claim about any provider.", None, (),
    )
    changed = replace(GITHUB_ISSUES, idempotency=no_documented_mechanism)
    assert changed.provider is GITHUB_ISSUES.provider
    assert changed.mutation is GITHUB_ISSUES.mutation
    assert changed.observation is GITHUB_ISSUES.observation
    assert changed.correlation is GITHUB_ISSUES.correlation
    assert changed.isolation is GITHUB_ISSUES.isolation


def test_client_key_capability_is_optional_and_arm_local_if_enabled() -> None:
    key = _SYNTHETIC_CLIENT_KEY
    assert key.capability is IdempotencyCapability.CLIENT_SUPPLIED_KEY
    assert key.mechanism == "synthetic-key"
    assert set(key.runtime_key_requirements) == set(RuntimeKeyRequirement)
    constraints = " ".join(key.key_reuse_constraints)
    assert "one original mutation within one experimental arm" in constraints
    assert "independent keys or namespaces" in constraints
    assert "not shared across arms, families, or runs" in constraints
    synthetic_candidate = replace(GITHUB_ISSUES, idempotency=key)
    for record in (synthetic_candidate, key, synthetic_candidate.mutation,
                   synthetic_candidate.observation):
        assert not {"policy", "retry_policy", "arm", "arm_id", "enabled"} & {
            field.name for field in fields(record)
        }


def test_client_key_capability_does_not_require_mutation_parameter_equality() -> None:
    capability = _SYNTHETIC_CLIENT_KEY
    assert {requirement.value for requirement in capability.runtime_key_requirements} == {
        "runtime_owned", "stable_across_retries",
    }
    assert capability.key_reuse_constraints
    # Exact replay's payload equality is distinct from the key's reuse rules.
    assert RequestIdentityPart.PAYLOAD in GITHUB_ISSUES.mutation.stable_request_parts
    changed = replace(GITHUB_ISSUES, idempotency=capability)
    assert changed.mutation is GITHUB_ISSUES.mutation


@pytest.mark.parametrize("with_marker", [False, True])
@pytest.mark.parametrize("with_response_id", [False, True])
def test_both_pre_dispatch_observation_forms_with_optional_response_id(with_marker, with_response_id) -> None:
    observation = replace(
        GITHUB_ISSUES.observation,
        required_inputs=(ObservationInput.TARGET_SCOPE,) + (
            (ObservationInput.STUDY_MARKER,) if with_marker else ()
        ),
        supplemental_inputs=(ObservationInput.RESPONSE_ID,) if with_response_id else (),
    )
    correlation = replace(
        GITHUB_ISSUES.correlation,
        basis=CorrelationBasis.SCOPE_AND_MARKER if with_marker else CorrelationBasis.ISOLATED_TARGET_SCOPE,
        pre_dispatch_marker_supported=with_marker,
    )
    candidate = replace(GITHUB_ISSUES, observation=observation, correlation=correlation)
    assert candidate.correlation.pre_dispatch_marker_supported is with_marker
    assert ObservationInput.RESPONSE_ID not in candidate.observation.required_inputs
    assert (ObservationInput.RESPONSE_ID in candidate.observation.supplemental_inputs) is with_response_id


@pytest.mark.parametrize("required_inputs", [(), (ObservationInput.STUDY_MARKER,)])
def test_supplemental_response_id_cannot_rescue_missing_pre_dispatch_basis(required_inputs) -> None:
    with pytest.raises(ContractValidationError):
        replace(
            GITHUB_ISSUES.observation, required_inputs=required_inputs,
            supplemental_inputs=(ObservationInput.RESPONSE_ID,),
        )


@pytest.mark.parametrize("supplemental_inputs", [
    (ObservationInput.RESPONSE_ID,) * 2,
    (ObservationInput.TARGET_SCOPE,),
    (ObservationInput.STUDY_MARKER,),
    [ObservationInput.RESPONSE_ID],
    ("mutation_response_id",),
])
def test_supplemental_inputs_reject_duplicates_overlap_and_invalid_types(supplemental_inputs) -> None:
    with pytest.raises(ContractValidationError):
        replace(GITHUB_ISSUES.observation, supplemental_inputs=supplemental_inputs)


@pytest.mark.parametrize("with_marker", [False, True])
def test_required_observation_basis_must_match_correlation_basis(with_marker) -> None:
    observation = replace(
        GITHUB_ISSUES.observation,
        required_inputs=(ObservationInput.TARGET_SCOPE,) + (
            (ObservationInput.STUDY_MARKER,) if with_marker else ()
        ),
    )
    correlation = replace(
        GITHUB_ISSUES.correlation,
        basis=CorrelationBasis.ISOLATED_TARGET_SCOPE if with_marker else CorrelationBasis.SCOPE_AND_MARKER,
    )
    with pytest.raises(ContractValidationError, match="basis must match"):
        replace(GITHUB_ISSUES, observation=observation, correlation=correlation)


@pytest.mark.parametrize("marker_support", [False, None])
def test_established_scope_correlation_does_not_require_marker_support(marker_support) -> None:
    scope_correlation = CorrelationCapability(
        status=DesignStatus.ESTABLISHED,
        basis=CorrelationBasis.ISOLATED_TARGET_SCOPE,
        pre_dispatch_marker_supported=marker_support,
        constraints=("Synthetic isolated scope is sufficient, without an embedded marker.",),
    )
    assert scope_correlation.status is DesignStatus.ESTABLISHED


def test_unknown_is_distinct_from_absence_of_documented_mechanism() -> None:
    assert GITHUB_ISSUES.idempotency.capability is IdempotencyCapability.UNKNOWN
    assert GOOGLE_SHEETS_ROWS.idempotency.capability is IdempotencyCapability.UNKNOWN
    assert IdempotencyCapability.UNKNOWN is not IdempotencyCapability.NO_DOCUMENTED_CLIENT_MECHANISM
    assert {item.value for item in IdempotencyCapability} == {
        "unknown", "no_documented_client_mechanism", "client_supplied_key",
    }


@pytest.mark.parametrize("required_inputs", [
    (ObservationInput.RESPONSE_ID,),
    (ObservationInput.TARGET_SCOPE, ObservationInput.RESPONSE_ID),
    tuple(ObservationInput),
])
def test_observation_cannot_require_mutation_response_even_with_a_marker(required_inputs) -> None:
    with pytest.raises(ContractValidationError, match="lost mutation response ID"):
        replace(GITHUB_ISSUES.observation, required_inputs=required_inputs, supplemental_inputs=())


@pytest.mark.parametrize("required_inputs", [
    (), (ObservationInput.STUDY_MARKER,),
])
def test_observation_needs_pre_dispatch_scope(required_inputs) -> None:
    with pytest.raises(ContractValidationError):
        replace(GITHUB_ISSUES.observation, required_inputs=required_inputs)


@pytest.mark.parametrize("part", tuple(RequestIdentityPart))
def test_partial_exact_replay_identity_is_rejected(part) -> None:
    with pytest.raises(ContractValidationError, match="all request parts"):
        replace(GITHUB_ISSUES.mutation, stable_request_parts=tuple(
            item for item in RequestIdentityPart if item is not part
        ))


@pytest.mark.parametrize("requirement", tuple(RuntimeKeyRequirement))
def test_key_reuse_cannot_omit_runtime_ownership_or_stability(requirement) -> None:
    with pytest.raises(ContractValidationError):
        replace(_SYNTHETIC_CLIENT_KEY, runtime_key_requirements=tuple(
            item for item in RuntimeKeyRequirement if item is not requirement
        ))


@pytest.mark.parametrize("capability", [
    IdempotencyCapability.UNKNOWN, IdempotencyCapability.NO_DOCUMENTED_CLIENT_MECHANISM,
])
def test_key_mechanism_cannot_be_attached_to_unknown_or_absent_support(capability) -> None:
    with pytest.raises(ContractValidationError, match="documented key support"):
        replace(_SYNTHETIC_CLIENT_KEY, capability=capability)


@pytest.mark.parametrize("mechanism", [None, "", " "])
def test_key_support_requires_a_named_mechanism(mechanism) -> None:
    with pytest.raises(ContractValidationError, match="key mechanism"):
        replace(_SYNTHETIC_CLIENT_KEY, mechanism=mechanism)


def test_unknown_correlation_remains_representable_without_claiming_establishment() -> None:
    unknown = CorrelationCapability(
        DesignStatus.UNRESOLVED, CorrelationBasis.SCOPE_AND_MARKER,
        None, ("Marker persistence and visibility unknown.",),
    )
    candidate = replace(GITHUB_ISSUES, correlation=unknown)
    assert candidate.correlation.pre_dispatch_marker_supported is None
    with pytest.raises(ContractValidationError, match="marker support"):
        replace(unknown, status=DesignStatus.ESTABLISHED)


def test_unsupported_correlation_cannot_back_a_marker_based_observation() -> None:
    unsupported = replace(GITHUB_ISSUES.correlation, pre_dispatch_marker_supported=False)
    with pytest.raises(ContractValidationError, match="possible marker support"):
        replace(GITHUB_ISSUES, correlation=unsupported)


@pytest.mark.parametrize("boundary", tuple(IsolationBoundary))
def test_isolation_cannot_silently_omit_a_boundary(boundary) -> None:
    with pytest.raises(ContractValidationError, match="all isolation boundaries"):
        replace(GITHUB_ISSUES.isolation, distinguish_from=tuple(
            item for item in IsolationBoundary if item is not boundary
        ))


@pytest.fixture
def synthetic_established():
    """Structural counterexample fixture, not a claim about any real provider."""
    return OperationCapability(
        provider=Provider.GITHUB,
        status=DesignStatus.ESTABLISHED,
        mutation=MutationOperation(
            name="synthetic_create", resource="synthetic_object",
            status=DesignStatus.ESTABLISHED, state_mutating=True,
            stable_request_parts=tuple(RequestIdentityPart),
        ),
        observation=ObservationOperation(
            name="synthetic_list", resource="synthetic_object",
            status=DesignStatus.ESTABLISHED, state_mutating=False,
            required_inputs=(ObservationInput.TARGET_SCOPE,),
            supplemental_inputs=(ObservationInput.RESPONSE_ID,),
            constraints=("Synthetic complete isolated-scope enumeration.",),
        ),
        correlation=CorrelationCapability(
            status=DesignStatus.ESTABLISHED,
            basis=CorrelationBasis.ISOLATED_TARGET_SCOPE,
            pre_dispatch_marker_supported=False,
            constraints=("Synthetic scope contains only the intended logical object and its duplicates.",),
        ),
        idempotency=ProviderIdempotency(
            capability=IdempotencyCapability.NO_DOCUMENTED_CLIENT_MECHANISM,
            basis="Synthetic known capability, not a GitHub claim.",
            mechanism=None, runtime_key_requirements=(),
        ),
        isolation=IsolationRequirements(
            status=DesignStatus.ESTABLISHED,
            distinguish_from=tuple(IsolationBoundary),
            constraints=("Synthetic scope separates every required boundary.",),
        ),
    )


def test_synthetic_fully_established_record_is_representable(synthetic_established) -> None:
    assert synthetic_established.status is DesignStatus.ESTABLISHED
    assert synthetic_established.correlation.pre_dispatch_marker_supported is False


@pytest.mark.parametrize("with_response_id", [False, True])
def test_scope_supplemental_marker_rejects_false_support(synthetic_established, with_response_id) -> None:
    observation = replace(
        synthetic_established.observation,
        supplemental_inputs=(ObservationInput.STUDY_MARKER,) + (
            (ObservationInput.RESPONSE_ID,) if with_response_id else ()
        ),
    )
    with pytest.raises(ContractValidationError, match="possible marker support"):
        replace(synthetic_established, status=DesignStatus.PROVISIONAL, observation=observation)


@pytest.mark.parametrize("with_response_id", [False, True])
def test_established_scope_cannot_hide_unsupported_supplemental_marker(synthetic_established, with_response_id) -> None:
    observation = replace(
        synthetic_established.observation,
        supplemental_inputs=(ObservationInput.STUDY_MARKER,) + (
            (ObservationInput.RESPONSE_ID,) if with_response_id else ()
        ),
    )
    with pytest.raises(ContractValidationError, match="possible marker support"):
        replace(synthetic_established, observation=observation)


@pytest.mark.parametrize("with_response_id", [False, True])
def test_supported_supplemental_marker_preserves_isolated_scope_basis(synthetic_established, with_response_id) -> None:
    candidate = replace(
        synthetic_established,
        observation=replace(
            synthetic_established.observation,
            supplemental_inputs=(ObservationInput.STUDY_MARKER,) + (
                (ObservationInput.RESPONSE_ID,) if with_response_id else ()
            ),
        ),
        correlation=replace(synthetic_established.correlation, pre_dispatch_marker_supported=True),
    )
    assert candidate.correlation.basis is CorrelationBasis.ISOLATED_TARGET_SCOPE
    assert candidate.observation.required_inputs == (ObservationInput.TARGET_SCOPE,)
    assert ObservationInput.STUDY_MARKER in candidate.observation.supplemental_inputs
    assert candidate.status is DesignStatus.ESTABLISHED


def test_scope_supplemental_response_id_allows_false_marker_support(synthetic_established) -> None:
    candidate = replace(synthetic_established)
    assert candidate.correlation.pre_dispatch_marker_supported is False
    assert candidate.observation.required_inputs == (ObservationInput.TARGET_SCOPE,)
    assert candidate.observation.supplemental_inputs == (ObservationInput.RESPONSE_ID,)
    assert candidate.status is DesignStatus.ESTABLISHED


@pytest.mark.parametrize("status,marker_support,valid", [
    (DesignStatus.PROVISIONAL, True, True),
    (DesignStatus.PROVISIONAL, None, True),
    (DesignStatus.PROVISIONAL, False, False),
    (DesignStatus.ESTABLISHED, True, True),
    (DesignStatus.ESTABLISHED, None, False),
    (DesignStatus.ESTABLISHED, False, False),
])
def test_required_marker_support_rules_remain_unchanged(synthetic_established, status, marker_support, valid) -> None:
    def compose():
        return replace(
            synthetic_established, status=status,
            observation=replace(
                synthetic_established.observation,
                required_inputs=(ObservationInput.TARGET_SCOPE, ObservationInput.STUDY_MARKER),
            ),
            correlation=replace(
                synthetic_established.correlation, status=status,
                basis=CorrelationBasis.SCOPE_AND_MARKER,
                pre_dispatch_marker_supported=marker_support,
            ),
        )

    if valid:
        assert compose().correlation.basis is CorrelationBasis.SCOPE_AND_MARKER
    else:
        with pytest.raises(ContractValidationError, match="marker support"):
            compose()


@pytest.mark.parametrize("part", ["mutation", "observation", "correlation", "isolation"])
@pytest.mark.parametrize("status", [DesignStatus.PROVISIONAL, DesignStatus.UNRESOLVED])
def test_establishment_rejects_each_unverified_mapping_or_capability(synthetic_established, part, status) -> None:
    with pytest.raises(ContractValidationError, match="unresolved prerequisites"):
        replace(synthetic_established, **{
            part: replace(getattr(synthetic_established, part), status=status),
        })


def test_establishment_rejects_unknown_idempotency(synthetic_established) -> None:
    with pytest.raises(ContractValidationError, match="unresolved prerequisites"):
        replace(synthetic_established, idempotency=GITHUB_ISSUES.idempotency)


def test_provisional_provider_cannot_be_promoted_by_changing_only_outer_status() -> None:
    for candidate in PROVISIONAL_CAPABILITIES:
        with pytest.raises(ContractValidationError, match="unresolved prerequisites"):
            replace(candidate, status=DesignStatus.ESTABLISHED)


@pytest.mark.parametrize("field,value", [
    ("provider", "synthetic"), ("provider", "github_protected"),
    ("status", "frozen"), ("mutation", None), ("observation", None),
    ("correlation", None), ("idempotency", None), ("isolation", None),
])
def test_invalid_contract_types_and_provider_arm_names_are_rejected(field, value) -> None:
    with pytest.raises(ContractValidationError):
        replace(GITHUB_ISSUES, **{field: value})


@pytest.mark.parametrize("record,changes", [
    (GITHUB_ISSUES.mutation, {"name": " "}),
    (GITHUB_ISSUES.mutation, {"resource": ""}),
    (GITHUB_ISSUES.mutation, {"status": "established"}),
    (GITHUB_ISSUES.mutation, {"state_mutating": False}),
    (GITHUB_ISSUES.mutation, {"state_mutating": 1}),
    (GITHUB_ISSUES.mutation, {"stable_request_parts": list(RequestIdentityPart)}),
    (GITHUB_ISSUES.observation, {"state_mutating": True}),
    (GITHUB_ISSUES.observation, {"state_mutating": 0}),
    (GITHUB_ISSUES.observation, {"status": "established"}),
    (GITHUB_ISSUES.observation, {"required_inputs": ("pre_dispatch_study_marker",)}),
    (GITHUB_ISSUES.observation, {"constraints": ()}),
    (GITHUB_ISSUES.observation, {"constraints": (" ",)}),
    (GITHUB_ISSUES.correlation, {"status": "provisional"}),
    (GITHUB_ISSUES.correlation, {"basis": "isolated_target_scope"}),
    (GITHUB_ISSUES.correlation, {"pre_dispatch_marker_supported": 1}),
    (GITHUB_ISSUES.isolation, {"status": "unresolved"}),
    (GITHUB_ISSUES.isolation, {"distinguish_from": (IsolationBoundary.RUN,) * 2}),
    (_SYNTHETIC_CLIENT_KEY, {"capability": "client_supplied_key"}),
    (_SYNTHETIC_CLIENT_KEY, {"basis": ""}),
    (_SYNTHETIC_CLIENT_KEY, {"runtime_key_requirements": ()}),
    (_SYNTHETIC_CLIENT_KEY, {"runtime_key_requirements": list(RuntimeKeyRequirement)}),
    (_SYNTHETIC_CLIENT_KEY, {"key_reuse_constraints": ["mutable"]}),
    (_SYNTHETIC_CLIENT_KEY, {"key_reuse_constraints": (" ",)}),
])
def test_malformed_or_contradictory_nested_specs_fail_at_construction(record, changes) -> None:
    with pytest.raises(ContractValidationError):
        replace(record, **changes)


def test_resource_and_operation_mismatches_are_rejected() -> None:
    with pytest.raises(ContractValidationError, match="mutation resource"):
        replace(GITHUB_ISSUES, observation=GOOGLE_SHEETS_ROWS.observation)
    with pytest.raises(ContractValidationError, match="must be distinct"):
        replace(GITHUB_ISSUES, observation=replace(
            GITHUB_ISSUES.observation, name=GITHUB_ISSUES.mutation.name,
        ))


@pytest.mark.parametrize("candidate", PROVISIONAL_CAPABILITIES)
def test_capability_graph_is_immutable(candidate) -> None:
    for record in (candidate, candidate.mutation, candidate.observation,
                   candidate.correlation, candidate.idempotency, candidate.isolation):
        field = fields(record)[0]
        with pytest.raises(FrozenInstanceError):
            setattr(record, field.name, getattr(record, field.name))
        hash(record)  # All nested collections are immutable and hashable.
