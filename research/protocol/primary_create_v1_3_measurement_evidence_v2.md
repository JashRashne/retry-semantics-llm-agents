# Phase 1.5 — prospective paper measurement evidence V2

This revision resolves the V1 evidence gaps B1/B2 before any primary paper
observations. It adds operational measurement only. The frozen analysis plan,
manifest, eligibility and V1.2 execution semantics are unchanged. It does not
implement the full analysis extractor or change the supported statistical core.
The prior blocked extractor remains untouched pending its separately authorized
V2 implementation and audit.

## Provenance and schema selection

The prospective durable `run_paper_collection` entry point defaults to
`paper-collection-evidence-v2`. It writes the same six filenames, with no seventh
completed-bundle artifact. Run metadata states all three identities:

- paper experiment: `primary-create-v1.3`;
- execution semantics: `primary-create-v1.2`;
- collection evidence: `paper-collection-evidence-v2`.

V2 ledger, trace provenance and summary repeat the collection-evidence identity.
The V1 event schema remains sufficient: the independently persisted run metadata
and validated ledger/trace/summary select the measurement revision. The complete
bundle validator rejects mixed revisions, missing V2 evidence, stale or duplicate
request sequences, inconsistent prefixes and incompatible provenance.

| Filename | Prospective schema / identity |
| --- | --- |
| manifest.json | Existing frozen manifest, unchanged |
| run_metadata.json | `paper_run_metadata_schema_v2.json`, `paper-run-metadata-v2` |
| scheduled_attempts.jsonl | `paper_scheduled_attempt_schema_v2.json`, `paper-scheduled-attempt-v2` |
| arm_traces.jsonl | `paper_trace_schema_v2.json`, `trace-schema-paper-v2`, `paper-provenance-v2` |
| collection_events.jsonl | Existing immutable `paper_collection_event_schema_v1.json` |
| paper_collection_summary.json | `paper_collection_summary_schema_v2.json`, `paper-collection-summary-v2` |

`paper_measurement_schema_v2.json` is the shared schema for model invocation and
successful tool-execution records. All references resolve from local schemas.
Existing committed V1 schemas are retained byte-for-byte. Explicit V1 evidence
serialization and validation remain supported. The in-memory
`execute_paper_collection` API retains its V1 compatibility default; prospective
V2 callers must pass `evidence_revision="paper-collection-evidence-v2"` or use
the durable entry point, whose default is V2. Unsupported measurement clients
are rejected before the first slot or creation of an in-progress directory.

The existing atomic/fsynced write-ahead journal, unpublished temporary directory,
directory rename, completed-bundle validation and prefix cleanup order are
unchanged. V2 measurement data is carried in the ledger and arm traces on those
same persistence boundaries. Runner-fatal diagnostics in an in-progress prefix
use `paper-runner-fatal-v2` and repeat evidence provenance; they are not a
completed seventh file and do not authorize resume or retry.

## Structured response-failure taxonomy

`ModelResponseError.response_failure` is an immutable
`ResponseFailureEvidence(category, stage)`. Its JSON form has
`evidence_version="model-response-failure-v2"`, `category`, and `stage`.
The error is tagged at the actual failing operation; no exception-message
classification occurs. Its type, message, raising path and runtime handling
remain historical. Existing sanitized `structured_evidence` retains its V1
shape, so engineering trace payloads are unchanged. Only V2 measurement records
and V2 infrastructure diagnostics serialize the new discriminator.

| Category | Exact permitted stages |
| --- | --- |
| PROVIDER_RESPONSE_STRUCTURE | `COMPLETION_ENVELOPE`, `CHOICE_ENVELOPE`, `NON_JSON_SUCCESS_BODY`, `FINISH_REASON`, `COMPLETION_MODEL`, `TOKEN_USAGE`, `SYSTEM_FINGERPRINT`, `COMPLETION_ID` |
| MODEL_GENERATION_STRUCTURE | `ASSISTANT_MESSAGE`, `TOOL_CALL_LIST`, `TOOL_CALL_FUNCTION`, `TOOL_CALL_ID`, `TOOL_CALL_NAME`, `TOOL_CALL_ARGUMENTS`, `TOOL_CALL_TYPE`, `ASSISTANT_ROLE`, `ASSISTANT_CONTENT`, `ASSISTANT_MESSAGE_CAPTURE` |
| PROTOCOL_COMPATIBILITY | `REASONING_POLICY` |
| IMPLEMENTATION_INCOHERENCE | `LOCAL_CAPTURE_CONFIGURATION`, `TOOL_CALL_PARSE_METADATA`, `RECOVERY_PARSE_METADATA`, `MODEL_CLIENT_RETURN_TYPE` |

Stage meanings follow the named failing boundary in
`models/fireworks.py`; internal recovery parse-consistency and client-return-type
errors receive metadata tags at their existing raises in `runtime/regeneration.py`.
Those two edits add exception metadata only, without branching changes.

The hostile collision is now distinguishable: non-string tool arguments produce
`MODEL_GENERATION_STRUCTURE/TOOL_CALL_ARGUMENTS`; the earlier unexpected
non-null reasoning guard produces `PROTOCOL_COMPATIBILITY/REASONING_POLICY`.
The sanitized retained completion can still be identical; classification no
longer depends on it. Hidden reasoning content is never included in the new
discriminator or retained diagnostics. No new reasoning history is introduced.

Missing/non-object assistant message **inside an otherwise accessed choice** is
model-generation structure; missing/unreadable choice/message envelope access is
provider response structure. Invalid assistant role can fail during the
historical assistant-message constructor (`ASSISTANT_MESSAGE_CAPTURE`), while a
missing role fails at `ASSISTANT_ROLE`. Malformed argument JSON still produces a
captured `ModelToolCall` with `parse_success=false` and follows the existing
recovery `invalid_model_tool_call` path. No adapter exception is invented for it.

V2 diagnostics preserve the raw runtime infrastructure attribution even for
MODEL_GENERATION_STRUCTURE errors. V2 model records independently retain the
category so a later analysis can distinguish behavioral malformation from true
analysis infrastructure without changing the historical model-visible history
or action execution.

## Exact provider request dispatch boundary

`FireworksModelClient.last_request_dispatch_evidence` returns immutable
`ProviderRequestDispatchEvidence` with:

- `request_dispatch_evidence_version="provider-request-dispatch-v1"`;
- `provider_invocation_sequence` (client-wide monotone invocation ordinal);
- `provider_request_dispatched` (actual provider transport attempt);
- `provider_response_returned` (HTTP client call returned a response).

At entry to each existing `complete()` call, the client increments the ordinal
and resets both booleans false. `_DispatchEvidenceTransport.handle_request`
sets dispatch true immediately before delegating once to the existing transport.
It preserves the underlying zero retries, payload, headers, timeout, redirect
and trust-environment settings and delegates close. No callback changes a model
request, action decision or returned observation. A returned HTTP response sets
the response flag true before status handling or parsing.

| Path | dispatched | response returned |
| --- | --- | --- |
| Successful HTTP response | true | true |
| HTTP 4xx/5xx | true | true |
| Timeout/connection error at transport attempt | true | false |
| Returned HTTP success followed by adapter capture failure | true | true |
| Local request/config validation before transport | false | false |
| HTTP client closed / local request construction fails before transport | false | false |

This proves **transport invocation**, not provider receipt or completed inference.
The wrapper observes the actual transport callback rather than assuming
`httpx.Client.post()` entry proves a transport attempt.

The V2 arm evidence client snapshots the immutable record in `finally`, including
exceptions, and verifies the client ordinal advanced exactly once. Missing or
stale evidence is runner-fatal rather than counted as a dispatch. Other providers
or synthetic clients must expose the same explicit evidence capability for V2;
there is no complete-entry-count fallback. Original-generation ordinal gaps are
permitted in the recovery ledger; all retained recovery ordinals must still be
strictly increasing in serial paper execution order.

## Successful tool-execution journal

`TicketEnvironment.successful_execution_journal` is a tuple of immutable
`SuccessfulToolExecution` entries, appended only after the existing read or
create operation returns successfully. Each entry records:

`execution_sequence`, `tool`, `mutating`, `source_stage`, `arm_id`,
`request_hash`, `tool_call_id`.

Sequences are one-based, preserve actual execution order and are separate from
mutation-event numbering. The journal is not TicketState, is not serialized by
`snapshot_bytes()`, does not affect state hashes, never enters observations,
and is never read to select actions. Every clone starts with an empty journal
and the historical zero dispatch count. The old dispatch-count increment remains
before hash/request/stage validation.

A validation failure can increment dispatch count with no journal entry. A
successful list adds one read entry; a successful create adds one mutating entry.
A create that commits and subsequently fails before its tool operation returns
has authoritative commit evidence but **no successful-execution entry**. A
successful tool return followed by a later arm/executor failure retains its
successful entry. Costs follow the requested successful-execution measurement
contract; mutation commits remain separately available for terminal state.

## Persisted prefixes and mechanical validation

Every attempted V2 arm opportunity has `measurement_evidence`, with
`evidence_version="paper-arm-measurement-v2"`, `model_invocations` and
`successful_tool_executions`. Non-activated opportunities have null measurement
and no fabricated policy outcome. Each model invocation contains its raw frozen
request/response/rejected/boundary-error evidence plus the exact dispatch record
and nullable `response_failure`. Internal runtime response errors are merged by
the existing invocation index after the arm returns; this merges diagnostics
only and does not alter execution.

Pre-trace failures use `pre-trace-arm-boundary-v2`, retaining model invocation
records, successful execution prefix, terminal snapshot/hash or explicit capture
failure, mutation commit IDs and existing arm infrastructure attribution.
The diagnostic executor dispatch count remains present but is unnecessary for
cost derivation. Snapshot capture failure does not discard the operational
journal or dispatch records.

V2 traces retain their existing frozen V1.2 content plus paper-only
`measurement_evidence`. Validation checks:

- required schemas and matching run/ledger/trace/summary evidence revisions;
- model invocation indices, unique monotone provider ordinals, dispatch/returned
  coherence and matching model request/response/rejection/error records;
- exact failure category/stage agreement with arm diagnostics and presence for
  response errors, preventing silent unclassified adapter failures;
- successful execution ordering, tool/mutation kind, recovery arm attribution,
  request hashes and tool IDs;
- equality of the scheduled, pre-trace and trace measurement prefixes;
- exact agreement with executed recovery actions for clean traces; infrastructure
  traces retain successful prefixes even when an action result was not appended;
- journal mutations against available authoritative commits, while allowing
  separately retained commits from executions that failed before successful
  return; canonical authoritative trace snapshots/hashes are also checked;
- Replay has no model invocations, no reads, at most one successful create,
  and exactly one successful create on its completed trace path.

## Sufficient evidence for the later extractor

No final mapper is implemented here. The following future mappings require only
structured V2 evidence:

- Regeneration MALFORMED_GENERATION: captured ModelResponse with historical
  `invalid_model_tool_call`, **or** returned-provider adapter error with
  `response_failure.category == MODEL_GENERATION_STRUCTURE`.
- Provider/network/status, PROTOCOL_COMPATIBILITY, IMPLEMENTATION_INCOHERENCE,
  rejected-generation and budget paths are excluded from that malformed flag.
  Replay has no malformed/rejected/budget model outcome.
- `model_calls_issued`: count recovery invocation `provider_request_dispatched`
  values equal to true, including infrastructure/pre-trace prefixes.
- Executed read/write costs: count successful execution entries by `mutating`;
  total is read plus mutating. Executor dispatch count is never used.
- OBSERVATION_BEFORE_WRITE: ordered successful executions establish reads before
  first write, including read-then-stop. Requested but unexecuted calls do not count.

All authoritative terminal-state limitations remain explicit. Unavailable state
is not fabricated as behavioral failure, and pre-arm/system failures are not
assigned to a policy. No evidence gap B1/B2 remains for the future V2 extractor;
its implementation, statistical integration and hostile audit are still pending.

## Manifest and preservation requirements

Manifest ID:
`primary-create-v1.3-fireworks-deepseek-v4-flash-0731-paper-001`.
Canonical byte length: **240807**.
SHA256:
`a707909df1fcfaa99c6834394e74340788dfcf1d62545d25ff89bf6a6418a03c`.

Tests reconstruct the manifest without calls. Differential synthetic V1/V2 runs
produce byte-identical model-visible histories and frozen trace content after
removing only the V2 provenance/measurement extension and timing fields. Direct
synthetic state-transition comparisons prove unchanged snapshots and hashes.
Existing V1 paper and engineering regressions remain part of full-suite
verification. The original V1 schema and Phase-2 core file hashes are separately
checked against their pre-edit baseline.

All tests are offline. Fireworks transport tests use `httpx.MockTransport` and
dummy test credentials only; collection fixtures use explicitly simulated
in-memory transport facts. No live inference, paper collection, engineering
validation, credential loading, commit or push is authorized or performed.

## Verification for the Phase-1.5 working revision

- Targeted V2 measurement, Fireworks adapter, paper collection and manifest
  tests: **218 passed**, including **50 V2-specific cases**.
- Complete offline suite: **769 passed**.
- All nine preserved-file hashes match the pre-edit baseline: five V1 paper
  schemas, frozen engineering trace schema, frozen analysis plan and both
  Phase-2 source modules (`analysis_statistics.py`, `analysis_evidence.py`).
- Reconstructed manifest: exactly **240807 bytes**, with the frozen ID and
  SHA256 printed above.
- Re-publication of the same retained synthetic V2 evidence: all six output
  files are byte-identical, with no regenerated model requests or tool actions.
- No remaining B1/B2 measurement blocker for V2; the extractor remains
  intentionally incomplete and untouched for the next phase.

Changed/added implementation files are `models/base.py`, `models/fireworks.py`,
`models/measurement.py`, `environments/ticket.py`, `runtime/regeneration.py`,
`experiment/paper.py`, and `experiment/paper_measurement.py`, all beneath
`src/retry_semantics/`. Five prospective V2 schema files listed above/shared
measurement schema were added. Tests changed/added:
`test_fireworks_adapter.py`, `test_paper_collection.py`, and
`test_paper_measurement_v2.py`. This document is new; frozen protocol documents
were not rewritten.
