# Prospective collection launcher protocol — no collection authorization

This supplements, and does not change, the accepted `../PROTOCOL.md`. The
baseline remains an explicitly post-feedback evaluation, not part of the
prespecified Study 1A analysis. No baseline result has been collected and no
inferential analysis or manuscript change is authorized here.

## Frozen population and exact requests

Use only `frozen_bindings/schedule.json`, in ascending schedule_index order:
320 Study 1A, 320 Study 1B, 128 GitHub, 128 valid-replication Sheets arms, exactly
896 opportunities from the 448 copied source families. Each family has H0/H1.
The copied-source five-column mapping and prospective order are unchanged.
Each arm binds its source original identity, exact semantic target/hash,
construction label, arm ID, marker/scope, stored request file/hash and whole
request identity. Ticket buffers are the exact copied original requests.
Provider requests rebind only the permitted fresh scope/attribution, through
the existing serializers, before any scientific constructor or recovery.

Full physical bindings have zero UNBOUND scopes. The baseline spreadsheet has
128 evaluation tabs and 128 reserved/unused tabs. Its 256-tab topology has the
same GRID extent (100 × 3) and selected-grid semantics as the valid replication.
Qualification effects are on a separate four-tab spreadsheet, never any of
these 256 baseline tabs. GitHub qualification uses a disjoint marker.

## Authorization and one-use execution

The launcher has explicit `verify` and `collect` actions, with no default.
Verify is read-only and does not execute constructors, policy or evaluators.
Collect refuses unless the caller supplies the exact authorization string
defined in `collection.AUTHORIZATION`, plus a pinned lock SHA-256 and a fresh
output directory outside the repository. No such authorization was supplied
in this pass. Runtime, dependency versions, source/evidence and every frozen
request are verified first. The existing Sheets environment gate runs before
any scientific arm. A child launch may remove GIT_PAGER only; any other
forbidden name requires review, not automatic stripping.

After authorization, a write-once COLLECTION_CONSUMED.json claim consumes the
schedule. Existing claims or output directories refuse reuse. There is no
resume, overwrite, refill, result replacement, automatic repair or mutation
retry. A spent schedule remains spent after credential, infrastructure or
collection failure. Raw intents precede possible transport dispatch, and
results preserve HTTP status, dispatch facts, errors and raw body bytes.

## Construction, recovery, scoring

Ticket arms clone the frozen empty logical snapshot. H0 does not dispatch the
original; H1 dispatches the stored original exactly once. The accepted harness
checks the constructed state before fixed recovery and then invokes the
unchanged logical final-state evaluator.

Provider arms first independently qualify a blank fresh marker/grid with the
same inherited observation path. H0 does not dispatch the original. H1 dispatches
the exact stored original once, requires a validated acknowledgement, then
certifies exactly one intended effect independently. GitHub uses inherited
constructor +0/optional +600 starts and the accepted fresh-arm certificate
bridge. Sheets uses its unchanged acknowledgement and strict selected-grid H1
certificate. An unqualified constructor remains unknown/unscorable, with no
policy invocation and no replacement opportunity.

Only then enter the accepted rule: LIST once; unusable observation means STOP;
exact intended effect visible means STOP; otherwise dispatch the same stored
CREATE once and STOP. No model client/continuation is supplied. No H0/H1,
constructor acknowledgement/resource ID, evaluator state or provider marker/ID
is supplied to the decision. Existing projections strip those fields. One
GitHub logical LIST may traverse at most 16 pages, as in Regeneration.

Post-recovery scoring remains the accepted harness: GitHub fixed final census
+0/+600 with the existing deadlines and attribution/correctness rules; Sheets
one final selected-grid GET within its existing 40-second endpoint bound and
causal-floor check; ticket exact logical-state scoring. HTTP success alone
does not imply correctness. Unknown/unusable evidence stays unknown; a usable
final evaluator can score the endpoint after a failed recovery observation.

## Provider stops and opportunity retention

GitHub access/rate status 401/403/429 or a secondary-rate-limit response stops
further provider dispatch. Sheets 401/403/429 does likewise. No GET or POST is
sent after such a stop; an unavailable scheduled evaluator remains incomplete.
The serial launcher retains all later schedule entries as UNRUN with bound
source identity and zero recovery actions. Unexpected unhandled failures or
post-entry harness failures also stop the remainder. A pre-entry uncertified
constructor is retained unknown and the existing order continues unless a
provider stop occurred. No failed opportunity is refilled.

Per-family GitHub access/principal/repository/quota checks and the existing
Sheets 1.1-second pacing and 2100-second family token reserve occur outside
the decision. Fresh OAuth sessions must use the same app and original valid
replication principal/sole-owner constraints. Tokens are never persisted.

## Reporting

Future results are write-once per-arm JSON, separate from old artifacts and
the manuscript. Keep scheduled, scored, correct and unknown/unrun counts
distinct. First report descriptive Replay/Regeneration/no-model counts by
Study × execution situation. Do not invent new p-values or claim the third
policy was preregistered. Final inference requires a separate decision after
collection and hostile audit. Neither descriptive_counts.csv nor paper/main.tex
is written by this launcher.
