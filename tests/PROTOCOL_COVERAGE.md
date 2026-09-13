# Implemented invariant coverage

This implementation deliberately covers only invariants enforceable at the
deterministic environment, hidden-world construction, Exact Replay, evaluator,
and canonical Regeneration-context layers.

| Invariant | Current enforcement |
| --- | --- |
| INV-1 | Construction accepts one frozen M object plus explicit canonical bytes/hash, checks their coherence before dispatch, and gives that same immutable M to all four arm starts. The Regeneration context consumes the stored original assistant message, including its exact raw JSON argument string, and validates its single structured call against M without replacing it. The trace schema reserves that raw string separately; original-generation capture and full trace linkage remain pending. |
| INV-2 | Each hidden-world snapshot is serialized once and cloned into byte/hash-identical, independent policy-arm starting environments; family validation checks both pairs before recovery, and Exact Replay tests prove P1 execution leaves the P2 sibling unchanged. |
| INV-3 | The pure Regeneration context builder accepts only the exact user task, frozen M, and stored original assistant message; it fixes the complete four-message sequence and two-tool catalog. Tests pass the same stored message and raw argument text to H0/H1 and prove byte-identical contexts and SHA-256 hashes while authoritative state hashes differ. Original-generation capture remains pending. |
| INV-4 | Exact Replay has no model parameter, callback, interface, or dependency and its immutable result fixes `additional_llm_calls=0`. Later full traces will reconcile this with lifecycle instrumentation. |
| INV-5 | The canonical context has an exact closed structure and is constructed without a hidden-world or environment input. Hostile tests reject/scan for hidden labels, execution flags, evaluator classifications and IDs, mutation/state fields, and actual family state hashes. Later runtime/trace integration must ensure adapters consume only this representation. |
| INV-6 | Exact Replay passes the post-termination authoritative `TicketState` to the existing deterministic evaluator; no model claim or observation enters evaluation. |
| INV-7 | Family construction requires the fresh empty authoritative state, captures it without mutating the source, and creates every branch/arm by snapshot deserialization. |
| INV-8 | Ticket and immutable event are published atomically; Exact Replay requires one newly committed event, returns its ID, and verifies that event's frozen bytes/hash and RECOVERY provenance. Events remain state-reconstructable. |
| INV-9 | The local executor has no retry/network layer; Exact Replay contains one executor call and tests both a one-dispatch delta and no fallback call after an executor exception. Adapter-level retry enforcement remains pending. |
| INV-10 | Exact Replay verifies SHA-256 and representation equality before dispatch, then passes the caller-supplied `serialized_original_request` bytes object directly to the executor. A capture test proves object identity; parsing for evaluation occurs only after dispatch and is never reserialized. |
| INV-14 | Each call constructs a fresh immutable message/tool value with no session, thread, provider, or client input. Cross-trial provider-session integration tests remain pending with the adapter. |
| INV-15 | Construction rejects non-`create_ticket` M before dispatch and verifies H1's one ticket exactly matches M. Upstream scenario eligibility/original-generation logging remains pending. |
| INV-16 | The exact system prompt, four-message order/fields, catalog order, protocol tool descriptions, and both complete schemas are single frozen definitions. Validation rejects extra messages and any catalog/schema drift; original-generation reuse remains pending. |
| INV-17 | A successful Exact Replay result fixes attempted/executed recovery calls at one, the implementation has no loop or fallback, and dispatch-delta plus injected-error tests cover success and failure boundaries. The Regeneration budget remains pending. |
| INV-18 | The builder has no timing input and the canonical logical context permits only the frozen messages/tools fields. Hostile tests scan exact keys for timestamps, latency, duration, dispatch time, and elapsed fields; runtime diagnostic separation remains pending. |
| INV-20 | Golden evaluator fixtures cover every primary class, overlaps, precedence, and exact matching; Exact Replay adds the H0 `CORRECT` and H1 `DUPLICATE_EFFECT` state oracles. |
| INV-22 | Model-visible CREATE/LIST projections contain only frozen visible fields. |
| INV-24 | H0 and H1 originate from one captured initial snapshot; each post-ambiguity snapshot is cloned twice without redispatch. Executing both P1 arms leaves both P2 arms and all stored initial/world snapshot bytes unchanged. |
| INV-25 | The Exact Replay result records the one attempted/executed action, observation, new commit-event ID, termination reason, final snapshot/hash, and evaluation. Complete lifecycle events and schema-valid arm traces remain pending. |
| INV-26 | Exact Replay rejects disagreement among the immutable frozen M object, explicit bytes, and explicit hash before dispatch; its recovery event retains those exact bytes/hash. Regeneration preserves the supplied stored assistant message and raw `arguments_json`, strictly parses it, and rejects disagreement among raw arguments, stored parsed arguments, executable M, tool name, or original call ID. Canonical context and the trace schema's `model_visible_context` calls serialize only the raw argument string, while parsed arguments remain validation metadata. Ambiguity linkage, canonical bytes, and hash are also validated. Original-generation capture and full-trace coherence remain pending. |

Pending until the corresponding model/trace/runner layers exist: INV-11–13,
INV-19, INV-21, INV-23, and INV-27. The portions explicitly noted above remain
pending for INV-1, INV-4–5, INV-9, INV-14–18, INV-25, and INV-26. No mocks
claim enforcement of those future behaviors or of matched Regeneration sampling.
