# DRAFT — NOT FROZEN — ZERO PAPER OBSERVATIONS

These are design objects for investigation, not a protocol or provider selection.
GitHub/Sheets key capability remains **unknown / not yet established** here.
The contract also supports **no documented client-controlled mechanism**, which
must not be read as mathematical non-idempotence or proof of duplication.
The third external provider candidate is pending prospective access and semantics
qualification and therefore has no active capability record. Its allocation and
selection gate are recorded prospectively in
`research/protocol/STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md`.

| Candidate provider | Mutation | Observation | Retry-relevant idempotency capability | Plausible pre-dispatch correlation | Major unresolved isolation question | Major correctness risk | Investigate further? |
|---|---|---|---|---|---|---|---|
| GitHub | `create_issue` | `list_issues` | Unknown here; no create-request key established | Writable issue content, provisional; no field/format selected | What scope/namespace separates families, runs, stale issues, and engineering activity? | List filters, issue state, permissions, pagination, or mixed resource types could hide/miscount duplicates | Appears plausible enough to investigate; not verified |
| Google Sheets | `append_row` | `list_rows` (logical read, concrete API mapping unresolved) | Unknown here; no append-request key established | Writable row cells, provisional; no cells/format selected | What spreadsheet/tab/range and namespace isolate each logical object? | Append placement, range limits, edits, or value transformation could hide/misidentify rows | Appears plausible enough to investigate; not verified |

The additive `retry_semantics.study2` package describes stable operation, target
scope, payload, and runtime options (including a key **if enabled**) independently
of policy. It does not serialize or execute requests. Later JSON identity can
reuse the existing canonical serializer; JSON equality alone is not HTTP request
equality. API version, account/tenant, target, and semantic request options must
be covered by target scope/runtime options. Concrete binding remains unresolved.
Observation has separate required and supplemental input tuples. Response IDs
are legal supplements and are never required under ACK loss. The generic contract
allows either isolated target scope alone or scope plus a pre-dispatch marker,
with an explicit matching correlation basis. The current candidates provisionally
describe the latter and retain response IDs as optional supplements; no final
strategy is selected. Marker support does not establish correlation, isolation,
completeness, or visibility guarantees. Mutation and observation mappings each
have explicit status; overall establishment requires both mappings, correlation,
and isolation to be established and idempotency capability to be known. All real
candidate records and mappings remain provisional.

Risks requiring later resolution:

- Observation must enumerate every duplicate, across all pages/ranges and relevant
  states. First-match lookup, list ordering, timestamps, or a lost ACK's object ID
  are insufficient. Scanning account-wide state without trial isolation is also
  insufficient. Filters and visibility restrictions require audit.
- Stale resources can match current intent. Namespace collisions, concurrent
  edits/deletions, and eventual consistency can make both matches and “not found”
  ambiguous. A marker must persist and be visible on reads; its preservation when
  generated parameters change is unresolved. Matching a marker alone does not
  establish the payload's correctness or reveal unmarked unintended mutations.
- Cleanup could destroy evidence; retention and cleanup strategy are unresolved.
- Provider deduplication can mask duplicate requests independently of the LLM.
  If a key is later enabled, the runtime must own it and keep it stable only for
  retries/recovery of one original mutation in one arm. Replay and Regeneration
  require independent keys or namespaces, with no sharing across arms, families,
  or runs. Allowing generation to change its arm-local key invalidates that
  condition. Provider parameter comparison may produce a mismatch/error when
  generated parameters change; the
  runtime key requirements do not prohibit attempting changed parameters under
  the stable key. Provider key-reuse constraints are separately descriptive and
  unresolved. Key retention, scope, concurrency, and error caching need audit.
- SDK automatic retries and lower transport retries could add hidden mutation
  attempts. Account-wide rate limits, abuse protection, and concurrency could
  alter outcomes. No client or retry behavior is implemented here.

The current candidates retain their previously recorded mapping uncertainties.
The third external provider remains unselected and must pass prospective access
and semantics qualification before a capability record or implementation is
added. The external environment family allocations are fixed by the frozen V1.3
plan and prospectively preserved by the Study 2 amendment: 64 families for
GitHub, 64 for Google Sheets, and 64 for external provider C. Still unresolved
are Provider C's identity; its provider-specific scenario catalogue and exact
manifest; marker/correlation design; evaluator; scheduling and counterbalancing
implementation details where not otherwise frozen; evidence-schema/provider
binding; and any required provider-specific analysis amendment. There are no
trial families, execution policies, ambiguity injection, observations, or new
dependencies in this phase.
