# Local environment invariant coverage

This implementation deliberately covers only invariants enforceable at the
deterministic environment/evaluator layer.

| Invariant | Current enforcement |
| --- | --- |
| INV-2 | One canonical snapshot can instantiate byte-identical, independent policy-arm states. |
| INV-6 | Evaluation accepts authoritative `TicketState` and uses exact state predicates only. |
| INV-7 | Empty construction creates isolated objects; no mutating reset API exists. |
| INV-8 | Ticket and immutable event are published in one state transition; events reconstruct state. |
| INV-9 | The local executor has one dispatch counter and no retry/network layer. |
| INV-10 | The executor accepts exact canonical bytes, optionally verifies their frozen hash, and rejects byte-different encodings. |
| INV-20 | Golden fixtures cover every primary class, overlaps, precedence, and exact matching. |
| INV-22 | Model-visible CREATE/LIST projections contain only frozen visible fields. |
| INV-24 | Snapshot primitives support deriving once and cloning twice from the same bytes. |
| INV-25 | Environment mutation records are complete and reconciled during reconstruction. |

Pending until the corresponding runtime/model/trace layers exist: INV-1,
INV-3–5, INV-11–19, INV-21, INV-23, INV-26, and INV-27. Full runtime-level
parts of INV-2, INV-9, INV-10, INV-24, and INV-25 also remain pending. No mocks
claim enforcement of those future behaviors.
