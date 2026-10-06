# Deployment correction only — collection remains unauthorized

The accepted no-model rule, evaluators, all 896 entries (including original
indices/order/worlds), semantic targets, markers, stored request bytes, physical
bindings and readiness evidence remain unchanged. This protocol supersedes only
the global-machine/global-consumption portions of the prior launcher protocol.
The original readiness lock is retained with exactly the same digest. A separate
pinned deployment lock binds the corrected launcher and archives the original
bytes of its two changed deployment files. All other accepted runtime identities,
Python/dependency versions and readiness evidence checks remain mandatory.

## Exact partition and machine roles

* TICKETS_LOCAL / tickets-local: 640 Study 1A/1B arms; MAC, logical state only.
* GITHUB_VM / github-vm: 128 GitHub arms; VM, GitHub capability only.
* SHEETS_MAC / sheets-mac: 128 Sheets arms; MAC, Sheets capability only.

The frozen partition manifest binds filtered schedule hashes and original global
indices. Its union is exactly 896 with empty pairwise intersections. No entry is
renumbered, reordered, refilled or replaced. Each partition executes serially in
its original global order. There is no all-partitions collection mode. The
explicit partition selects the machine role; hostname/platform are recorded as
provenance, never used as a scientific condition or automatic role selector.

## Launch and durable consumption

Both verify and collect require exactly one partition and pinned original
readiness/deployment lock hashes. Collect still requires deliberate authorization
and exact HEAD/Python/dependency identities. No authorization is supplied here.
The unchanged names-only environment gate remains mandatory; only the reviewed
GIT_PAGER child-launch removal is permitted without further review.

Each partition has its own exclusive-create consumption claim in the authoritative
binding directory, named COLLECTION_CONSUMED_<PARTITION>.json. Claims include the
output path and both lock identities, persist on failure and never clear or
replace another claim. Each partition must have exactly one authoritative
installation/claim store (GitHub on VM; tickets/Sheets on Mac). Do not extract a
second scientific installation, discard/recreate a claim directory, or relocate
a spent claim. Like the previous local-file lock, these claims are not a
cross-copy/distributed coordinator; copies are audit/transfer artifacts, not a
license to rerun an opportunity. An old global claim is refused and retained.

Each partition writes a distinct fresh output directory outside the repository.
Machine/runtime/partition provenance is persisted before arm execution. Every
result, including explicit UNRUN after stop, retains its original global index,
source/request identities and owning partition. Stop behavior is unchanged
within a partition; no resume/refill/replacement or mutation retry exists.

Tickets have no provider capability or credential factory. GitHub has no Google
OAuth factory; Sheets has no GitHub credential factory. Independent guards reject
wrong-source or altered entries before execution. The decision/scoring paths,
constructor behavior and existing transport/preflight checks are unchanged.

## GitHub VM transfer

Transfer the HEAD Git bundle and deterministic GitHub runtime ZIP identified in
VM_TRANSFER.json. Clone the bundle at the exact recorded main HEAD, then extract
the ZIP over that checkout. The ZIP carries the full 896-entry schedule and
original readiness lock, all identity-check inputs, accepted runtime, deployment
lock/manifest, and only the 128 fresh GitHub stored request files. Nonsecret
Sheets/source-readiness evidence and transitively imported code are required to
verify the same whole original lock; they confer no Sheets OAuth capability.
Fresh ticket/Sheets stored requests are omitted from this VM package. All relevant
GitHub file/request hashes must verify. No frozen request is rebound/recreated
on the VM. The existing GitHub scope authority is checked without serialization.

Private VM credentials: GITHUB_TOKEN or FINE_GRAIN_GITHUB_TOKEN (one valid GitHub
sandbox credential); no Google OAuth secret/token is transferred. No credentials,
.env, OAuth consent URLs or private tokens belong in any transfer/audit artifact.
Use the pinned Python/dependency versions in the original readiness lock. A
version mismatch refuses collection; do not loosen that check for Linux.
Run the exact read-only verification command in VM_TRANSFER.json before any
future separately authorized launch. Verification reports partition/count/global
indices and consumed state; it cannot launch construction, recovery or scoring.

## Offline merge

merge_no_model_partitions.py accepts three distinct completed output directories
with their explicit roles, the complete bindings and pinned lock hashes. It
requires 640/128/128 explicit records, exact source/request identities, global
indices and owning-partition provenance, no duplicates or implicit omissions.
Every stopped opportunity must appear as UNRUN in its owning directory. It
validates the exact union of 896 and never contacts providers or rewrites results.
Any optional validation report uses a new path. It adds no statistics or scoring
rule. Missing/duplicate/migrated opportunities fail rather than being repaired.

All tests in this correction pass are offline synthetic stubs or byte/hash
verification. No scheduled scientific arm enters a constructor or recover().
Scientific evaluations and provider mutations remain zero.
