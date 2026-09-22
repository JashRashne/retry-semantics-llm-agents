# DRAFT — NOT FROZEN — ZERO PAPER OBSERVATIONS

These are design objects for investigation, not a protocol or provider selection.
No Stripe provider was contacted by this slice. Stripe official-documentation
facts supplied as independently checked on 2026-09-21 now support its endpoint,
exact-email list, and key-semantics records; this slice did not browse to re-fetch
them.
GitHub/Sheets key capability remains **unknown / not yet established** here.
The contract also supports **no documented client-controlled mechanism**, which
must not be read as mathematical non-idempotence or proof of duplication.

| Candidate provider | Mutation | Observation | Retry-relevant idempotency capability | Plausible pre-dispatch correlation | Major unresolved isolation question | Major correctness risk | Investigate further? |
|---|---|---|---|---|---|---|---|
| GitHub | `create_issue` | `list_issues` | Unknown here; no create-request key established | Writable issue content, provisional; no field/format selected | What scope/namespace separates families, runs, stale issues, and engineering activity? | List filters, issue state, permissions, pagination, or mixed resource types could hide/miscount duplicates | Appears plausible enough to investigate; not verified |
| Google Sheets | `append_row` | `list_rows` (logical read, concrete API mapping unresolved) | Unknown here; no append-request key established | Writable row cells, provisional; no cells/format selected | What spreadsheet/tab/range and namespace isolate each logical object? | Append placement, range limits, edits, or value transformation could hide/misidentify rows | Appears plausible enough to investigate; not verified |
| Stripe TEST MODE | `create_customer` (`POST /v1/customers`), documentation-supported but provisional mapping | `list_customers` (`GET /v1/customers`) with exact case-sensitive email filter, documentation-supported but provisional mapping; process every Customer and follow `starting_after` while `has_more=true` | Documented client-supplied POST `Idempotency-Key`; if enabled, each arm receives an independent key/namespace stable only for one original mutation's retries; enablement remains unresolved | Unique synthetic pre-dispatch Customer email; no real-person PII; metadata supplemental only | Qualify sandbox account/principal, `livemode=false`, namespace isolation, and live read-after-write visibility | Mutation schema must prohibit `test_clock`; malformed/incomplete pagination is unknown, not zero; provider deduplication is distinct from retry policy | Proceed only to separately authorized TEST/SANDBOX engineering qualification; overall capability and both operation mappings remain provisional |

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

Stripe's candidate operation mappings and email filter field are now documented
but remain provisional; its mutation schema must reject `test_clock`, because an
unscoped Customer list omits Customers associated with test clocks. Its
authoritative traversal must honor `has_more`, require a usable final Customer ID
before `starting_after` advancement, and fail closed on malformed pagination;
its marker encoding/namespace, isolation strategy, read-after-write visibility,
completeness/consistency qualification, runtime key enablement, frozen API version,
and eventual experimental role remain unresolved. Other candidates retain their
previously recorded mapping uncertainties. So do scenario/replicate
counts, multiplicity correction, schedule, counterbalancing, manifests, evidence
schema, and stopping rules. There are no trial families, execution policies,
ambiguity injection, observations, or new dependencies in this phase.
