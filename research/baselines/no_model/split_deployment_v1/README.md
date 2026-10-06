# Split-deployment hostile audit candidate

This corrects deployment only. No scientific evaluations, provider reads,
scientific provider mutations, readiness mutations, manuscript edits or
commit/push occurred in this pass. All three consumption claims remain absent.

The exact three partitions retain global indices:

| Partition | Machine role | Arms | Global indices |
|---|---|---:|---|
| TICKETS_LOCAL | Mac, offline | 640 | 0–639 |
| GITHUB_VM | VM, GitHub only | 128 | 640–767 |
| SHEETS_MAC | Mac, Sheets only | 128 | 768–895 |

Union 896; pairwise intersections zero. Each partition has an independent
exclusive-create claim. File and directory fsync complete before execution;
a failed claim flush leaves evidence and refuses reuse. No resume/refill or
replacement exists. The CLI requires exactly one partition (repeated flags and
'all' refuse), original readiness lock, deployment lock and explicit collection
authorization. This pass supplied no authorization. Machine role is explicit;
actual hostname/platform are recorded before execution, not used as conditions.

Only collection.py (deployment verification/filtering/provenance) and the
collection CLI were modified relative to the previous candidate. New code:
partitions.py, partition_runtime.py, merge_partitions.py, merge CLI, offline
freeze/package CLI, and the split-deployment tests. deployment_changes.patch
contains the exact prior-to-current diff plus new-file contents. Accepted
no_model.py/adapters/harness/preparation/readiness and their protocol remain
byte-identical. No construction, recovery, observation or scoring rule changed.

UNCHANGED_PROOF.json verifies 3,584 frozen files across the prior audit inputs,
readiness evidence, schedule, 896 request bindings, manuscript/table and accepted
identities; separately verifies all 5,942 protected artifacts. The complete
schedule remains hash 51957d59e997a70dee1cd0b16baf3c4cf805da0cc9d8a2f0cad4727e5c1a804d.

The original readiness lock remains unchanged, hash
2e73e736aaa8fd01ace0a4e7c86f55aac33be41ea022ad8ad67eb692b535c59a.
The deployment lock explicitly chains to it and changes only two allowed runtime
identities, preserving their original bytes. Every other original runtime,
source/readiness evidence check and dependency-version check remains required.
Relevant request bytes are verified for the selected partition, and the entire
896-entry schedule is always verified. No GitHub request is serialized/rebound
on the VM: stored bytes and the existing scope authority are checked directly.

VM_TRANSFER.json specifies exact artifacts/hashes, HEAD, lock hashes, GitHub
partition hash, private credential names and the exact read-only VM command.
The Git bundle was verified and cloned offline; the runtime ZIP overlaid that
independent clone and the GitHub-only verifier passed. The package contains only
128 fresh stored GitHub requests, plus full schedule/identity/readiness inputs
needed to preserve the original lock checks. No fresh ticket/Sheets requests,
.env or OAuth client secrets are included. Old nonsecret Sheets readiness/source
inputs and transitively imported definitions are retained to check the same lock.
Package construction passed a byte-for-byte deterministic double-build test.

This pass did not connect to the actual VM. Its private credential remains there;
the exact read-only VM verification command must pass with Python 3.11.14 and
pinned dependency versions before any future collection authorization. The
repository has one authoritative claim store per partition; claims are not a
distributed lock across independently copied installations. Audit/verification
copies must never become a second scientific installation of a spent partition.

The focused/inherited suite passed 164 tests. After adding fsync claim durability
and its failure-retention test, the final deployment suite passed 27 tests.
Raw commands/stdout/stderr are under verification/. Tests exercise real dispatcher
and claim guards, synthetic immutable UNRUN result directories and offline merge,
wrong-partition/credential routing, deterministic package/exact frozen bytes,
all accepted-policy invariants, and old artifact preservation. Scheduled arms
never entered any scientific constructor, recover(), model or evaluator in this
correction pass. Counts written in synthetic pytest fixtures are not scientific
outcomes. No descriptive_counts.csv or result table was populated.

The offline merge validates all three completed partition directories with
explicit UNRUN records after stop, exact indices/identities/ownership and no
missing/duplicate/migrated opportunities. It performs no provider work and never
modifies input results. This package includes no inferential analysis.
