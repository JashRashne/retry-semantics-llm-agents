# Local environment invariant coverage

This implementation deliberately covers only invariants enforceable at the
deterministic environment, hidden-world construction, and evaluator layers.

| Invariant | Current enforcement |
| --- | --- |
| INV-1 | Construction accepts one frozen M object plus explicit canonical bytes/hash, checks their coherence before dispatch, and gives that same immutable M to all four arm starts. Model-message/trace linkage remains pending. |
| INV-2 | Each hidden-world snapshot is serialized once and cloned into byte/hash-identical, independent policy-arm starting environments; family validation checks both pairs before recovery. |
| INV-6 | Evaluation accepts authoritative `TicketState` and uses exact state predicates only. |
| INV-7 | Family construction requires the fresh empty authoritative state, captures it without mutating the source, and creates every branch/arm by snapshot deserialization. |
| INV-8 | Ticket and immutable event are published atomically; H1 construction requires exactly one event matching its one ticket and H0 requires none. Events remain state-reconstructable. |
| INV-9 | The local executor has no retry/network layer; construction asserts zero original dispatches in H0 and exactly one in H1. Adapter-level retry enforcement remains pending. |
| INV-10 | H1 verifies and directly dispatches the supplied frozen bytes. Exact Replay itself is not implemented yet. |
| INV-15 | Construction rejects non-`create_ticket` M before dispatch and verifies H1's one ticket exactly matches M. Upstream scenario eligibility/original-generation logging remains pending. |
| INV-20 | Golden fixtures cover every primary class, overlaps, precedence, and exact matching. |
| INV-22 | Model-visible CREATE/LIST projections contain only frozen visible fields. |
| INV-24 | H0 and H1 originate from one captured initial snapshot; H0 is derived with zero dispatches, H1 with one, and each post-ambiguity snapshot is cloned twice without redispatch. |
| INV-25 | Environment mutation records are complete and reconciled during reconstruction. |
| INV-26 | Frozen M object/bytes/hash and H1's original event are checked for internal coherence across all four starting states. Assistant-message, context, and trace coherence remain pending. |

Pending until the corresponding policy/model/trace/runner layers exist: INV-3–5,
INV-11–14, INV-16–19, INV-21, INV-23, and INV-27. The portions explicitly noted
above remain pending for INV-1, INV-9, INV-10, INV-15, INV-25, and INV-26. No
mocks claim enforcement of those future behaviors.
