# Google Sheets live qualification procedure — DRAFT

**LIVE-GO CLOSED. ENGINEERING ONLY. This document grants no authorization.**
No procedure below was executed. No real credentials, live reads, mutations,
ambiguous live trials or paper observations occurred in this preparation phase.
The frozen offline contract and reconnaissance remain unchanged.

The offline live-preparation baseline has passed hostile audit and is frozen
(see `GOOGLE_SHEETS_LIVE_PREPARATION.md`). Before execution, all remaining BLOCKED
and required live-validation gates in `SHEETS_LIVE_GO_CHECKLIST_DRAFT.json` must
be satisfied through separately authorized phases. Credential preparation and
fixture provision, including any setup API mutations, require separate authorization.
This status update does not authorize Step 1 or any Google action.
Phase 1 offline prerequisites have passed final hostile audit and are frozen; see
`GOOGLE_SHEETS_LIVE_GO_PHASE1.md`. The connected socket/deadline/wire-capability
layer, real credential acquisition, TLS/trust qualification, fixture, actual human
authorization and all remaining BLOCKED/live-validation gates must still be closed
before execution. The frozen runtime pin is unchanged.
Use dedicated OAuth user preparation outside transport with the single `drive.file`
scope and same-app fixture grant, as designed there. No credential/OAuth flow is
implemented or authorized. Audit and close the remaining prerequisites first.
Injection of a fake socket is an offline qualification seam, not live permission.
A fresh journal does not constitute authorization for another live attempt.

Phase 2 now supplies frozen offline-tested fixture/reservation, connected GET-only
wire, same-socket typed TLS evidence persisted before HTTP serialization, final
raw-send authorization/readiness checks after request-start fsync, explicit spawn
implementation hashing, monotonic total-deadline and permanent local consumption
machinery; see `GOOGLE_SHEETS_LIVE_GO_PHASE2.md` and checklist `phase2_update`.
This is additive current-state provenance, not a change to the frozen steps below.
The independent Phase 2 audit required repairs; independent re-audit passed with
verdict SAFE TO FREEZE GOOGLE SHEETS PHASE 2 OFFLINE PREREQUISITES. Phase 2 offline
prerequisites are frozen; no real read is authorized by this freeze.
`drive.file` permits same-app-file operations including mutations; LIVE_READ_GO
is a local wire capability, not a read-only bearer grant. The read path must never
expose the bearer to a generic mutation-capable client. All real fixture,
acquisition, trust, actual response-shape and separate human read gates remain outstanding. No genuine
LIVE_READ_GO, real fixture, token, Google request or paper observation exists from
this phase. The original runtime pin and qualification steps remain unchanged.

1. Provision an isolated engineering spreadsheet and dedicated GRID sheet under
   separate setup authorization. Bind actual IDs, title, exactly three columns and
   frozen row count into the fixture manifest; store canonical manifest and hash.
   Choose the audited empty whole-grid baseline. Reserve a disjoint namespace/case
   and preserve its reservation record. No formulas, Tables, merged cells, unrelated
   data, concurrent writers, automation, sorting or structural edits. Attest controls
   that the API grid read cannot establish (writers, scripts/triggers, automation).
2. Prepare the engineering candidate offline once with the frozen builder. Validate
   fixture/case/content and preserve its exact body bytes and scientific identity.
   Candidate preparation is not a dispatch and requires no Google credential.
3. Check the exact runtime pin, interpreter/stdlib/SSL/source/serialization/lock/
   template hashes and platform release. Confirm future TLS certificate/hostname
   verification and connector/trust configuration under their separate live gate.
   This local pin check does not qualify real TLS behavior.
4. Prepare the separately authorized baseline-read token outside the verifier.
   Establish its issuer/scope/expiry provenance, clock uncertainty and readiness.
   This step does not authorize acquisition, OAuth or a read in this current phase.
5. Reserve the new exclusive 0600 evidence journal BEFORE any baseline GET. Supply
   the prepared candidate and baseline-read token to `EvidenceJournal`; construction
   runs `assert_token_safe` before the initial header is written. Persist lossless
   body/hash/identity, runtime and fixture/hash. No action claiming durable evidence
   may precede its journal reservation. A token/evidence collision invalidates the
   journal and aborts; do not erase prior evidence or silently switch/reissue.
6. Establish baseline using `ReadOnlyVerifier.inspect(token, marker, journal)` over
   the entire manifest grid. It rechecks token safety before read activation and
   persists initiation/status/summary in that existing journal. Any uncertainty
   aborts. Require zero marker matches AND zero nonempty entered rows, exact
   identity/title/extent, no Tables or merges. Zero alone is insufficient.
7. Only after baseline success, prepare the immutable mutation token outside
   dispatch. Select and audit its acquisition/provenance, issuer, scope, expiry
   source, clock uncertainty and conservative dispatch budget. Run the same
   `journal.assert_token_safe` check against existing/prospective evidence and
   check readiness before activating the mutation. `mutation_attempt` repeats
   this central check mechanically. No refresh callbacks/credential object may
   cross into dispatch. A separately exported token must pass safety even if it
   differs from the baseline-read token.
8. With a separately issued one-use live capability, perform one clean mutation,
   fault mode `none`, through the exact instrumented path and existing journal.
   A visible 2xx is a known HTTP result even if its body is missing. No
   response-triggered repair/reissue.
9. Inspect the journal and low-level connection trace: exactly one mutation
   initiation, one local completion, expected method/path/body/application identity,
   one fresh connect, no unclassified traffic, no redirect, auth refresh or reissue.
10. Perform one explicitly requested read-back with the GET verifier and persist its
    independent initiation/status/summary. A reused or separately prepared later
    read token must pass the same central safety check BEFORE read activation.
    Require one exact three-cell marker row and no unexpected entered content.
    Any additional traversal must be separately explicit, bounded and recorded.
    No implicit polling is implemented.
11. Establish actual candidate placement: expected empty-baseline landing is
    zero-based row 0, columns 0–2, no grid expansion and all data inside coverage.
    Reject unexpected placement and reopen fixture/candidate assumptions. Fake
    placement tests are not Google placement evidence.
12. Only after clean success/read-back and separately authorized fixture restoration
    or a new clean isolated fixture, qualify controlled ambiguous-outcome engineering.
    Freeze its new manifest and namespace/case, then repeat steps 2–7: prepare the
    candidate, check the pin, prepare the baseline-read token, reserve its journal,
    establish baseline, and only then prepare/check its mutation token. Select the
    fixed after-local-send/before-status fault before journal reservation; do not
    infer commit from close and do not contact a model.
13. Verify exactly one initiation and completion before any explicit policy entry,
    absent definitive status, matching identity, actual fault boundary and closure.
    The offline replay handoff only demonstrates an interface: any live replay needs
    its own explicit authorization/capability. This procedure does not authorize it.
    Any token prepared for explicit replay must pass the same central safety and
    readiness checks before replay activation, while reusing the frozen body bytes.
14. Read current state using the separate GET capability and its existing journal,
    with the central safety check for every read token. Keep zero/one/multiple matches
    and malformed/uncertain reads distinct. Zero is current non-observation, never
    historical H0/noncommit. Report visibility and coverage limits. Freeze any future
    repeat-read schedule independently; never reuse GitHub timing as evidence.
15. Keep every output engineering-only. No paper observations, endpoint winner,
    arm implementation, paper protocol or collection permission follows automatically.
    Setup/cleanup are separate authorized actions outside the trial window; cleanup
    cannot imply cancellation, rollback or deletion of engineering evidence.

Abort and prohibit further mutation on more than one pre-policy initiation,
uninstrumented/unknown traffic, serialized envelope/body mismatch, missing/duplicate/
wrong-order lifecycle facts, unexpected redirect, 401 or auth refresh/reissue,
fixture/namespace/baseline mismatch, unexpected placement/expansion, verifier
uncertainty, marker-content mismatch/duplicates, runtime or hash drift, secret-bearing
content/evidence, storage failure/incomplete artifact, or a definitive status being
classified as target ambiguity. Partial writes are `incomplete_send_unknown` and
cannot enter the first target gate. TLS/connect failure is a zero-dispatch negative
control, never a service-reached H0. Recovery after crash requires review and
read-only investigation; an absent result file is never permission to resend.

Visible 403/404/429/500/503 and other errors are terminal HTTP results for this
qualification; retain status and stop. A 2xx with lost body retains its status and
cannot enter replay qualification. Parser/transport/body-framing failures never
become zero marker matches. Evidence failure never triggers a mutation retry.
