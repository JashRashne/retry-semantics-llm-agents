"""PROVISIONAL design records; no marker encoding, clients, or dispatch.

GitHub documentation reconnaissance is recorded in github_semantics.py and
research/study2/github/GITHUB_SEMANTICS_DRAFT.md; its capability is provisional.
Stripe documentation evidence is recorded in stripe_semantics.py and
research/study2/stripe/STRIPE_SEMANTICS_DRAFT.md; its capability is provisional.
Sheets knowledge remains limited here to the earlier candidate record.
GitHub/Sheets absence of a documented create key is not established: UNKNOWN.
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
    *, marker_verification_constraint: str = (
        "Exact fields, encoding, persistence, and observation visibility need verification."
    ),
    additional_observation_constraints: tuple[str, ...] = (),
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
            constraints=(*_OBSERVATION_CONSTRAINTS, *additional_observation_constraints),
            supplemental_inputs=(ObservationInput.RESPONSE_ID,),
        ),
        correlation=CorrelationCapability(
            status=DesignStatus.PROVISIONAL,
            basis=CorrelationBasis.SCOPE_AND_MARKER,
            pre_dispatch_marker_supported=True,
            constraints=(
                marker_constraint,
                marker_verification_constraint,
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
    "Official create/list docs expose title and raw body as content candidates; field/format and persistence unvalidated. See github_semantics.py.",
    "How will repository scope and markers distinguish runs, families, stale issues, and engineering activity?",
    ProviderIdempotency(
        capability=IdempotencyCapability.UNKNOWN,
        basis="Official REST endpoint/general/conditional-request docs and idempotency/deduplication searches did not establish create-request support or its absence; see GITHUB_SEMANTICS_DRAFT.md (2026-09-17).",
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
    "Use a unique synthetic pre-dispatch Customer email as the marker; list_customers supports an exact case-sensitive email filter. Never use real-person email/PII.",
    "Qualify a sandbox/test account scope and marker namespace that distinguish families, runs, stale Customers, and engineering activity; require livemode=false.",
    ProviderIdempotency(
        capability=IdempotencyCapability.CLIENT_SUPPLIED_KEY,
        basis="Official Stripe API documentation supplied as checked 2026-09-21 establishes client-supplied Idempotency-Key support for POST requests, retained-result replay, parameter comparison, mismatch errors, and the at-least-24-hour pruning caveat; see STRIPE_SEMANTICS_DRAFT.md.",
        mechanism="Idempotency-Key",
        runtime_key_requirements=tuple(RuntimeKeyRequirement),
        key_reuse_constraints=(
            "Stripe compares parameters when a retained key is reused and returns an error when they do not match the original request.",
            "A retained key returns the first request's status code and response body once endpoint execution began.",
            "Keys may be pruned after they are at least 24 hours old; a request rejected before endpoint execution may lack an idempotency record.",
            "If enabled, one runtime-owned key is stable only for retries and recovery attempts for one original mutation within one experimental arm.",
            "Replay and Regeneration arms require independent keys or namespaces; keys must not be shared across arms, families, or runs.",
            "Changed mutation parameters under a stable runtime-owned key remain representable; runtime equality is not required.",
        ),
    ),
    marker_verification_constraint=(
        "Email marker encoding/namespace, persistence, and read-after-write visibility still require engineering qualification."
    ),
    additional_observation_constraints=(
        "Use GET /v1/customers with the exact case-sensitive email filter; Customer Search is not authoritative.",
        "The eventual frozen Customer mutation schema must reject test_clock; arbitrary test-clock observation is not supported.",
        "Process every returned Customer and follow starting_after while has_more=true; require a usable final Customer ID before advancing.",
        "Malformed or inconsistent pagination is UNKNOWN/INCOMPLETE, never zero; first-match lookup is prohibited.",
        "No strict list consistency or read-after-write visibility guarantee is claimed.",
    ),
)

PROVISIONAL_CAPABILITIES = (GITHUB_ISSUES, GOOGLE_SHEETS_ROWS, STRIPE_CUSTOMERS)
