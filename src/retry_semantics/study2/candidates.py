"""PROVISIONAL design records; no marker encoding, clients, or dispatch.

Idempotency knowledge is limited to the supplied Study 2 brief. No external
documentation was fetched in this offline phase. GitHub/Sheets absence of a
documented create key is not yet established, so these records use UNKNOWN.
"""

from retry_semantics.study2.contracts import (
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

_OBSERVATION_CONSTRAINTS = (
    "Inspect all matching objects, not just the first; pagination or range limits can hide duplicates.",
    "Ordering and timestamps alone cannot correlate an object to the intended mutation.",
    "Visibility/consistency guarantees are unresolved; not found may not mean not committed.",
    "Mutation-response IDs may supplement observation but cannot be required after ACK loss.",
)
_ISOLATION = IsolationRequirements(
    status=DesignStatus.UNRESOLVED,
    distinguish_from=tuple(IsolationBoundary),
    constraints=(
        "Choose a scope and correlation namespace that separates every required boundary.",
        "Do not mistake stale or engineering resources for the current logical object.",
        "Cleanup timing is unresolved; deleting resources can destroy duplicate evidence.",
    ),
)


def _candidate(
    provider: Provider, mutation: str, observation: str, resource: str,
    marker_constraint: str, isolation_question: str, idempotency: ProviderIdempotency,
) -> OperationCapability:
    return OperationCapability(
        provider=provider,
        status=DesignStatus.PROVISIONAL,
        mutation=MutationOperation(
            name=mutation, resource=resource, state_mutating=True,
            status=DesignStatus.PROVISIONAL,
            stable_request_parts=tuple(RequestIdentityPart),
        ),
        observation=ObservationOperation(
            name=observation, resource=resource, state_mutating=False,
            status=DesignStatus.PROVISIONAL,
            required_inputs=(ObservationInput.TARGET_SCOPE, ObservationInput.STUDY_MARKER),
            constraints=_OBSERVATION_CONSTRAINTS,
            supplemental_inputs=(ObservationInput.RESPONSE_ID,),
        ),
        correlation=CorrelationCapability(
            status=DesignStatus.PROVISIONAL,
            basis=CorrelationBasis.SCOPE_AND_MARKER,
            pre_dispatch_marker_supported=True,
            constraints=(
                marker_constraint,
                "Exact fields, encoding, persistence, and observation visibility need verification.",
                "Every duplicate must remain individually countable; marker matching alone is not uniqueness.",
                "How correlation survives changed generated parameters remains unresolved.",
            ),
        ),
        idempotency=idempotency,
        isolation=IsolationRequirements(
            status=_ISOLATION.status,
            distinguish_from=_ISOLATION.distinguish_from,
            constraints=(*_ISOLATION.constraints, isolation_question),
        ),
    )


GITHUB_ISSUES = _candidate(
    Provider.GITHUB, "create_issue", "list_issues", "issue",
    "Plausibly embed a pre-dispatch study identifier in writable issue content; location not selected.",
    "How will repository scope and markers distinguish runs, families, stale issues, and engineering activity?",
    ProviderIdempotency(
        capability=IdempotencyCapability.UNKNOWN,
        basis="No client-controlled create-request mechanism established in the supplied brief; documentation audit pending.",
        mechanism=None, runtime_key_requirements=(),
    ),
)

GOOGLE_SHEETS_ROWS = _candidate(
    Provider.GOOGLE_SHEETS, "append_row", "list_rows", "row",
    "Plausibly embed a pre-dispatch study identifier in writable cells; cells and encoding not selected.",
    "How will spreadsheet/tab/range scope and markers isolate runs and families without hiding appended rows?",
    ProviderIdempotency(
        capability=IdempotencyCapability.UNKNOWN,
        basis="No client-controlled append-request mechanism established in the supplied brief; documentation audit pending.",
        mechanism=None, runtime_key_requirements=(),
    ),
)

STRIPE_CUSTOMERS = _candidate(
    Provider.STRIPE, "create_customer", "list_customers", "customer",
    "Plausibly embed a pre-dispatch study identifier in customer fields/metadata; exact fields not selected. Test mode only.",
    "How will test-mode account scope and markers distinguish families, runs, and prior test customers?",
    ProviderIdempotency(
        capability=IdempotencyCapability.CLIENT_SUPPLIED_KEY,
        basis="Supplied Study 2 brief states documented client-supplied POST key support; scope, retention, equality, and error behavior need audit.",
        mechanism="Idempotency-Key",
        runtime_key_requirements=tuple(RuntimeKeyRequirement),
        key_reuse_constraints=(
            "Provider parameter comparison and mismatch/error behavior on key reuse remain unresolved.",
            "Changed mutation parameters under a stable runtime-owned key remain representable; runtime equality is not required.",
        ),
    ),
)

PROVISIONAL_CAPABILITIES = (GITHUB_ISSUES, GOOGLE_SHEETS_ROWS, STRIPE_CUSTOMERS)
