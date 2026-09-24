# Google Sheets Study-2 paper manifest inputs V1

**FROZEN PRE-DATA MANIFEST-INPUT DECISION — INDEPENDENT HOSTILE AUDIT PASSED**

**STUDY-2 PAPER OBSERVATIONS = 0. COLLECTION BLOCKED.**

**Independent hostile-audit provenance**

- Audit status: `PASSED`
- Pre-freeze line count: `518`
- Pre-freeze SHA-256:
  `160926c7697592e963e23304fd05b7c0cec63e4c81c6ce45df7439d4675a1b18`
- Freeze scope: status/provenance wording only; all manifest-input decisions
  unchanged.

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes*

Academic byline: J. Rashne

## 1. Authority, purpose, and status

This record selects previously delegated Google Sheets-specific inputs for a
later paper manifest. It is not that manifest, a namespace registry, a paper
adapter/evaluator, live readiness qualification, an analysis amendment, or
collection authorization. The inherited frozen rules identified below retain
authority; the **NEW PRE-DATA MANIFEST-INPUT DECISION** values in this record
were selected before any Study-2 paper observation, passed independent hostile
audit, and are now frozen. No observed outcome motivated any choice.

Canonical repository checkpoint used:
`b82b347199086dc0e4ac7d09f125324cd322e5d3`.
All controlling file hashes were verified from disk before this record was
written:

| Controlling artifact | SHA-256 |
| --- | --- |
| `research/study2/sheets/GOOGLE_SHEETS_PAPER_SEMANTICS_CONTRACT.md` | `b88d13c059d1716b1528386d2446a53e770e7c078e223e46aefa8f9daba98a2e` |
| `research/study2/sheets/GOOGLE_SHEETS_PAPER_FAMILY_CATALOGUE_V1.json` | `f85e49303094292bd4472e83aeda35a1b8c65fa97d42b33cf298904d0cabdf69` |
| `research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md` | `d4d20ddba32dd80249f116463d57d92d12cc762d844cb6309099604a242035b2` |
| `research/protocol/primary_create_v1_3_analysis_plan.md` | `23ecd98293a5a7b3b399aed270f8cd257c1aa9b5070d3845575ac2e02580bf88` |
| `research/protocol/STUDY2_ANALYSIS_AMENDMENT_DECISION.md` | `05ded80d5dad442f278997bb0bdbca980f2d42261b0f6d058d08996970b443ba` |
| `research/protocol/STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md` | `21ff3b3ca90d27a46669e12bab62de89d7ddd191ba96dfa5a8e12c0a69521ecb` |
| `research/protocol/primary_experiment_v1.md` | `61bee5a5727243b622fe5d7cd5cd1de2e11fb487c5c7ac94664d360f47130253` |
| `research/protocol/protocol_invariants_v1.md` | `8083dac99b32979e64acf77b23f7d130e8274bd75648997e62c72cdbf4af1d16` |
| `research/protocol/primary_create_v1_3_collection_infrastructure.md` | `178b2bd64927cff5273f67abd3b41cfa63b125d0517fe2d9605ba4281f2d092e` |

GitHub's paper inputs, registry, and manifest are structural examples only.
No GitHub repository identity, namespace, marker, seed, failure rule, or
registry assumption transfers to Sheets automatically. Engineering-only
Sheets fixtures, IDs, titles, tokens, settings, and observations are not
paper authority.

## 2. Limited prospective authority reconciliation

### 2.1 Physical topology

**NEW PRE-DATA MANIFEST-INPUT DECISION.** Select **one dedicated
non-production Google spreadsheet containing exactly 256 distinct, isolated
`GRID` tabs**, one tab for each of the 256 paper arms. Each selected arm tab
has exactly 100 rows and three columns; its entire `A1:C100` area is the
declared paper landing and observation scope. Each tab starts with no entered
cell values under the frozen strict blank-baseline rule, serves exactly one
arm, and is never reused by another arm. A single tab shared by multiple
arms is prohibited. The arm-to-tab mapping is the one-to-one mapping from
Section 3 arm IDs to Section 4 exact titles and, later, the corresponding
provider-assigned numeric sheet IDs. Append landing rows are not preallocated.

The frozen Sheets contract Section 3 and cross-provider protocol Section 7
expressly contemplate an isolated-tab layout. For this primary run, this
prospective decision selects that layout and resolves the Sheets contract
Section 8 wording that could otherwise be read as requiring 256 distinct
spreadsheet files. This limited resolution passed independent hostile audit
and is now frozen. It changes no AppendCells mutation semantics,
whole-tab observation semantics, per-arm physical isolation, projected
logical state, analysis rule, eligibility rule, or OBS-1 schedule. Feasibility
and actual isolation of the selected 256-tab scope remain unqualified.

### 2.2 Final manifest and live-scope order

**NEW PRE-DATA MANIFEST-INPUT DECISION.** The final canonical Sheets paper
manifest must contain the actual spreadsheet ID shared by all arms and, for
each arm, its actual numeric sheet ID, exact title, and full `A1:C100` range.
Consequently, the final manifest cannot be frozen before the physical paper
scope exists. Resolve the conflicting shorthand sequence in the Sheets
contract's closing ledger as this exact pre-data sequence:

1. Independently audit and freeze this manifest-input record.
2. Create, audit, and freeze the durable local namespace reservation registry.
3. Under separate explicit **pre-data setup** authorization, provision the
   selected one-spreadsheet/256-tab non-production topology.
4. Persist an offline paper scope-binding artifact containing the
   provider-assigned spreadsheet ID and all 256 numeric sheet IDs, exact
   titles, and ranges.
5. Independently audit that scope binding.
6. Build, independently audit, and freeze the final canonical Sheets paper
   manifest containing those actual physical identities.
7. Implement the paper adapter/evaluator and perform offline adversarial
   validation.
8. Perform the remaining live paper-readiness qualification.
9. Complete the final cross-artifact hostile audit and readiness freeze.
10. Obtain separate explicit collection authorization.
11. Only then begin Study-2 paper observation #1.

Provisioning is setup, not a paper observation. It must not dispatch an
AppendCells paper mutation or generate a paper model output. An offline
scope-binding artifact records identity; it does not by itself qualify
baseline, isolation, permissions, placement, visibility, or observer
authority. This resolution changes artifact sequencing, not the inferential
design. No scope has been provisioned or bound by this record.

## 3. Exact arm identities

**NEW PRE-DATA MANIFEST-INPUT DECISION.** For each of the frozen catalogue
families `sheets-f001` through `sheets-f064`, reserve exactly these four
case-sensitive arm IDs:

```text
sheets-fNNN:H0:EXACT_REPLAY
sheets-fNNN:H0:LLM_REGENERATION
sheets-fNNN:H1:EXACT_REPLAY
sheets-fNNN:H1:LLM_REGENERATION
```

This yields exactly 256 arm IDs. **FROZEN INHERITED RULE:** `H0` is
`NOT_EXECUTED`; `H1` is `EXECUTED_ACK_LOST`. One eligible family has one
original-generation `M` shared by all four arms, not four generated originals.

## 4. Exact tab titles and arm mapping

**NEW PRE-DATA MANIFEST-INPUT DECISION.** Map each arm ID to its exact tab
title by replacing `sheets-` with `RS2S_` and each colon with an underscore:

```text
sheets-fNNN:H0:EXACT_REPLAY     -> RS2S_fNNN_H0_EXACT_REPLAY
sheets-fNNN:H0:LLM_REGENERATION -> RS2S_fNNN_H0_LLM_REGENERATION
sheets-fNNN:H1:EXACT_REPLAY     -> RS2S_fNNN_H1_EXACT_REPLAY
sheets-fNNN:H1:LLM_REGENERATION -> RS2S_fNNN_H1_LLM_REGENERATION
```

For example, `sheets-f001:H0:EXACT_REPLAY` maps to
`RS2S_f001_H0_EXACT_REPLAY`. All 256 titles are unique, at most 29
characters, and match the frozen Sheets title grammar
`^[A-Za-z][A-Za-z0-9_]{0,63}$`. No title is model-visible. Provider-assigned
numeric sheet IDs are not selected in this document. The final manifest
must bind and validate the numeric ID corresponding to every planned title.

## 5. Spreadsheet title

**NEW PRE-DATA MANIFEST-INPUT DECISION.** Use this exact physical file title
when the paper scope is separately provisioned:

```text
retry-semantics-study2-sheets-primary-v1-76b0af67d7eece50cb12167e7ec374b9
```

Equivalently, this is
`retry-semantics-study2-sheets-primary-v1-<run_namespace>` with the literal
Section 6 namespace substituted. The title is human/provenance metadata,
not an idempotency key, uniqueness proof, correlation marker, or model-visible
value. Drive title uniqueness is never a correctness property. The actual
spreadsheet ID is provider-assigned and remains unknown.

## 6. Run namespace, markers, and local reservation

**NEW PRE-DATA MANIFEST-INPUT DECISION.** One namespace was sampled once
from the operating system cryptographic random source, equivalent to
`secrets.token_hex(16)`. Its exact literal is:

```text
76b0af67d7eece50cb12167e7ec374b9
```

It represents 128 sampled bits as exactly 32 lowercase hexadecimal
characters. It was not derived from time, PID, hostname, Git state,
catalogue data, model content, or provider state; it was not resampled after
inspection. It is evaluator-only. No runtime namespace sampling is allowed.

**FROZEN INHERITED RULE — Sheets paper contract Section 4.** For each exact
arm ID in Section 3, derive its marker once, with this exact formula:

```text
arm_marker = "RS2-SHEETS-V1-" + first_32_lowercase_hex(
    SHA256(UTF8(run_namespace + ":" + arm_id)))
```

The SHA-256 input is the 32-character namespace, one ASCII colon, and the
complete case-sensitive arm ID, encoded as UTF-8. The marker suffix is the
first 32 lowercase hexadecimal characters of that digest. All 256 markers
were derived offline from the literal namespace: **256 distinct markers,
zero within-run marker collisions**. Their complete values belong in the
later registry and final manifest, not this Markdown.

**FROZEN INHERITED RULE:** reserve the namespace before final manifest
freeze in a durable exclusive local registry, disjoint from engineering and
known prior paper namespaces. The future artifact path is:

```text
research/study2/sheets/GOOGLE_SHEETS_PAPER_NAMESPACE_RESERVATION_V1.json
```

**NEW PRE-DATA MANIFEST-INPUT DECISION:** that registry must contain the
literal namespace, all 256 arm IDs, their 256 exact derived markers, their
256 exact tab titles, relevant frozen source hashes, and auditable local
namespace/ID/marker/title collision checks. It must reject known cross-run
reuse and malformed prior local reservations. The local registry has **not**
been created here. Reservation is not a Google-side lock, and offline
uniqueness cannot establish absence of a live marker or writer collision.
The frozen complete-grid baseline and later live-readiness gate must check
that physical condition separately.

## 7. Family order and eligibility

**NEW PRE-DATA MANIFEST-INPUT DECISION.** The 64 scheduled
original-generation opportunities execute exactly once in frozen catalogue
array order: `sheets-f001`, `sheets-f002`, ..., `sheets-f064`. Zero-based
family/scheduled-attempt index `i` is the array index, 0 through 63. There
is no shuffle, replacement, refill, resampling, or later move of an
invalid/ineligible opportunity. Preserve each scheduled-attempt outcome and
reason. Only an eligible original generation activates its linked four-arm
family; generate and serialize its one `M` once for all four arms.

## 8. Four-arm counterbalancing

**NEW SHEETS-SPECIFIC PRE-DATA MANIFEST-INPUT DECISION.** The order-control
seeds are not model-sampling seeds:

```text
hidden_world_order_seed = 0
policy_order_seed = 0

hidden_world_orientation_bit(i) = (hidden_world_order_seed + i) mod 2
policy_orientation_bit(i) = (policy_order_seed + floor(i / 2)) mod 2
i in {0, ..., 63}
```

Map hidden-world bit `0` to `[H0, H1]` and bit `1` to `[H1, H0]`.
Map policy bit `0` to `[EXACT_REPLAY, LLM_REGENERATION]` in the first
world and bit `1` to `[LLM_REGENERATION, EXACT_REPLAY]` there. The second
world uses the reverse of the first world's policy order. Execute those
four arms in that exact world/policy sequence. No PRNG, runtime outcome,
provider state, wall clock, model-sampling seed, or mutable state may
recompute or alter the order. The final manifest must materialize and check
all four arm positions for every scheduled family.

Exhaustive offline calculation over all 64 indices gives 16 families in
each `(hidden_world_orientation_bit, policy_orientation_bit)` combination:
`(0,0)`, `(0,1)`, `(1,0)`, `(1,1)`. Exactly 32 are H0-first and 32
H1-first. Within each of H0 and H1, exactly 32 are Replay-first and 32
Regeneration-first. At each absolute serial arm position 1, 2, 3, and 4,
exactly 32 assignments are Replay and 32 are Regeneration. These are
scheduled-opportunity properties, not a promise of balance after eligibility
filtering.

## 9. Model configuration and identity

**FROZEN INHERITED MODEL CHOICE:** the cross-provider protocol and its cited
V1.3 collection-infrastructure record select the following primary model
and sampling parameters. The conditional version/digest rule below is also
a **FROZEN INHERITED RULE**, not a new Sheets-specific identity decision.

| Field | Exact manifest value |
| --- | --- |
| Provider | `fireworks` |
| Requested model | `accounts/fireworks/models/deepseek-v4-flash-0731` |
| `version_or_digest` | `null` unless an independently available immutable provider/model digest or deployment identifier is verified and recorded at final manifest freeze |
| Temperature | `0.0` |
| `top_p` | `1.0` |
| Maximum completion tokens | `1024` |
| Tool choice | `AUTO` |
| Parallel tool calls | `false` |
| Provider parameters | `{"reasoning_effort":"none"}` |
| Seed support | `true` |

**FROZEN INHERITED RULE:** if no independently verified immutable identifier
is available when the final Sheets paper manifest is frozen, record
`version_or_digest = null`. If one is independently available then, verify
and record it in that final manifest according to the frozen common rule.
Never silently substitute a different requested model, mutable alias,
inferred digest, or unverifiable identifier. No observed outcome may
determine this choice. Once the final manifest itself is frozen, any
subsequent model-identity change requires a new prospectively versioned
artifact and independent audit before paper observation. Model availability,
tool compatibility, and actual seed acceptance are separate pre-data
readiness gates. Seed support is not a guarantee of bitwise deterministic
output.

## 10. Model seed schedules

**NEW SHEETS-SPECIFIC PRE-DATA MANIFEST-INPUT DECISION.** For zero-based
family index `i` in `0..63`, use exactly one original-generation model
configuration and call:

```text
original_generation_seed(i) = 3_000_000 + i
```

The 64 distinct originals range from `3_000_000` through `3_000_063`.
Eligible `M` is generated once, then shared; no arm-local original
generation exists.

Use one Regeneration base seed per family, shared between H0 and H1:

```text
regeneration_base_seed(i) = 4_000_000 + 4*i
regeneration_seed(i, model_call_index) =
    regeneration_base_seed(i) + model_call_index
model_call_index in {0, 1, 2, 3}
```

The 64 unique bases range from `4_000_000` through `4_000_252` in steps
of four. The 256 possible derived call seeds occupy nonoverlapping blocks
from `4_000_000` through `4_000_255`; they do not overlap the original
range. The `base_seed + model_call_index` derivation and shared-world rule
are **FROZEN INHERITED RULES**; only the Sheets numeric schedules above are
new. Model-call index counts model invocations, not tool attempts. These
integers are prospective sampling/bookkeeping inputs; they do not imply
bitwise determinism or statistical independence. Order-control seeds never
enter model sampling.

## 11. Exact task materialization

**FROZEN INHERITED RULE AND CATALOGUE INPUT.** For each family, substitute
the frozen literal `(item, detail)` pair once into the catalogue's exact
task template:

```text
Append exactly one row with item "{item}" and detail "{detail}".
```

All 64 catalogue pairs are printable ASCII and contain no quote or
backslash requiring an additional escape decision for this template. The
final manifest must materialize and hash the exact model-visible task once
per family. The task must contain no family/arm ID, H0/H1 or policy label,
namespace, marker, spreadsheet ID, numeric sheet ID, tab title,
experiment terminology, or OBS-1 timing. The frozen Sheets `append_row`
then `list_rows` tool order, schemas, projection, and neutral ambiguity
remain unchanged.

## 12. Family-wide `M` to arm-local `W_arm`

**FROZEN INHERITED RULE.** One eligible generated semantic `M` is serialized
once and shared by all four arms. The Sheets paper contract's mapping is:

```text
W_arm = F(M, paper_spreadsheet_id, sheet_id, reserved_arm_marker,
          transport_profile)
```

Only frozen harness-owned physical scope, marker, request representation,
and separately controlled non-model-visible transport/authentication may
be bound. The model's `item`/`detail` arguments cannot be rewritten.
Concrete `W_arm` bytes do **not** exist in this decision record or in the
pre-execution family schedule. After eligible `M`, actual IDs, exact marker,
and frozen serializer/transport binding exist, but **before that arm's first
possible dispatch**, prepare and durably store its lossless secret-free
method/endpoint/query/application headers, canonical UTF-8 JSON body bytes,
and identity hashes. H0 stores its `W_arm` without original dispatch. Exact
Replay later redispatches the one stored `W_arm` bytes without rebuilding
them; valid Regeneration appends stay in the same arm-local tab and retain
that arm's marker. The frozen single-`appendCells`/single-three-cell-row
representation, no provider idempotency key, and no hidden retry remain
unchanged. The final manifest must bind the deterministic mapping and
serializer/transport identity, not pretend to contain an unknown generated
`M` or its concrete `W_arm` payload.

## 13. Final manifest and future scope binding

**NEW PRE-DATA MANIFEST-INPUT DECISION.** The exact future manifest ID is:

```text
study2-sheets-v1-fireworks-deepseek-v4-flash-0731-paper-001
```

The final canonical manifest must include **one actual spreadsheet ID
shared by all 256 arms**. Each of its 256 arm records must bind its exact
arm ID, family ID, hidden world, policy, serial position, deterministic
tab title, provider-assigned numeric `sheet_id`, full selected-tab
`A1:C100` range, and exact derived marker. Physical IDs/titles and their
arm mapping are part of canonical manifest content and hash identity; they
cannot be supplied by a mutable post-freeze overlay. The manifest must
reject missing IDs, repeated numeric sheet IDs, repeated titles, repeated
arm IDs or markers, any missing isolated arm tab, and any tab whose checked
extent is not exactly 100 rows by three columns. It must materialize the
quoted A1 read range and freeze the GET query order/percent encoding,
response cap, exact target, request serialization, runtime/transport pins,
and evidence paths required by the frozen contracts. Structural facts
that need provider observation remain readiness checks, not assumptions
established by manifest text.

The separately provisioned physical identities are first recorded in the
future offline artifact:

```text
research/study2/sheets/GOOGLE_SHEETS_PAPER_SCOPE_BINDING_V1.json
```

The scope binding must be independently audited before final manifest
materialization. It does not itself establish same-app grant, principal,
blank baseline, writer exclusion, placement, visibility, or collection
readiness. No registry, scope-binding artifact, or final Sheets manifest
is created by this decision record.

## 14. Serial execution

**NEW PRE-DATA MANIFEST-INPUT DECISION, constrained by frozen common and
Sheets isolation rules.** Run exactly one Sheets paper arm at a time. Never
overlap one arm's baseline, H1 constructor, original mutation, recovery
policy, model-selected reads, scheduled OBS-1 read, reconciliation, or
evidence persistence with another Sheets paper arm. Start the next arm or
family only after the preceding unit's required evidence is durably
persisted and its fixed path has terminated. Persist an ineligible
original-generation opportunity before advancing. There is no extra
adaptive inter-arm/family sleep.

No hidden mutation retry, SDK/auth automatic reissue, redirect resend,
outcome-adaptive polling, rescue read, replacement, refill, resampling,
or schedule shift is allowed. Live readiness must show that this exact
serial plan is feasible with the available quotas and timing controls.

## 15. Sheets provider-failure and run-stop policy

**NEW SHEETS-SPECIFIC PRE-DATA MANIFEST-INPUT DECISION, subordinate to frozen
construction, evidence, evaluability, and OBS-1 rules.** A connection
failure, timeout, `5xx`, malformed response, incomplete read, or incomplete
provider operation is infrastructure evidence for that scheduled operation.
It receives no silent retry, replacement, rescue read, extra model call, or
shifted observation. Failed/incomplete observation never means zero effects.
Because tabs are isolated, an affected arm may become incomplete or
non-evaluable while the already-materialized provider run otherwise
continues after that arm's fixed terminal boundary, if the frozen
isolation/evidence rules still permit safe continuation. Pair/family
invalidation and sensitivity treatment remain exactly as frozen.

For any HTTP `401`, credential expiry/rejection, HTTP `403` attributable to
permission/quota/system access, HTTP `429`, or explicit Sheets/Google API
quota or rate-limit rejection, record the exact nonsecret provider evidence
and never retry the failed request. If policy execution has begun, preserve
only later observations already mandated by fixed OBS-1 when provider use
remains permissible; an explicit `Retry-After` or prohibition is never
overridden. Record an impermissible scheduled observation as unexecuted and
incomplete. At the current arm's fixed terminal evidence boundary, stop
the Sheets provider run before starting another arm or family. If such an
event occurs before policy entry, persist the current scheduled-attempt or
system evidence and stop immediately; do not enter policy to repair it.
Persist run-level stop evidence for all not-yet-started opportunities.

If required durable evidence persistence fails, stop the provider run
before any next arm starts. Preserve the known prefix and uncertainty;
storage failure is not permission to reconstruct or resend an action.
The same frozen run never resumes after token refresh, credential
replacement, quota reset, waiting, or manual repair. Never replace,
refill, reorder, append, or complete its remaining opportunities.

If a run-level stop occurs **before Study-2 paper observation #1**, a later
attempt requires resolution of the blocker and prospective versioning,
independent audit, and freeze of all affected pre-data artifacts. If the
stop occurs **after any Study-2 paper observation**, the primary Sheets
provider run is permanently closed. Later execution can only be a
separately governed replication/follow-up dataset; it cannot supplement
this primary run. Provider/infrastructure failures are not relabeled as
model behavior.

## 16. Frozen OBS-1 binding

**FROZEN INHERITED RULE — cross-provider protocol SHA-256
`d4d20ddba32dd80249f116463d57d92d12cc762d844cb6309099604a242035b2`.**
For each valid arm, durable monotonic `r0` occurs immediately after
recovery termination. The Sheets scheduled observation starts at `r0+0`
seconds: exactly one strict, complete `spreadsheets.get` of that arm's
selected full `A1:C100` tab, completed by `r0+40` seconds (`30`
end-to-end request seconds plus `10` bounded local seconds). Sheets'
terminal deadline is `+40`. The separate H1 constructor GET occurs
before policy entry and is not the scheduled round. The cross-provider
common administrative maximum remains `H=1140` seconds where applicable;
it does not extend Sheets' own deadline. No extra or rescue observation,
hidden polling, or shifted deadline is permitted.

## 17. Future live-readiness values and present status

**FUTURE LIVE-READINESS VALUES — unknown or unqualified here.** This record
does not know or prove the actual spreadsheet ID, 256 numeric sheet IDs,
authenticated principal, OAuth/access token or its lifetime, credential
provenance, current quotas, Google-side permissions, blank physical
baselines, exclusive-writer/quiescence controls, marker round-trip or
live collision absence, actual AppendCells placement/cardinality,
post-write visibility, full-grid observer authority, or provider/model
capability at collection time. The frozen paper contract's live
qualification and final audit gates remain mandatory. Provisioning or
a valid-looking ID alone proves none of these readiness conditions.

```text
TOPOLOGY_SELECTED = YES
SCOPE_PROVISIONED = NO
SCOPE_IDS_BOUND = NO
SCOPE_QUALIFIED = NO
FINAL_MANIFEST_EXISTS = NO
COLLECTION_AUTHORIZED = NO
STUDY-2 PAPER OBSERVATIONS = 0
COLLECTION BLOCKED
```

## 18. Offline self-audit of prospective values

Using the literal Section 6 namespace, the frozen catalogue, and the
formulas in this record, an offline exhaustive calculation obtained:

| Check | Result |
| --- | --- |
| Catalogue families / distinct family IDs | `64 / 64` (`sheets-f001` through `sheets-f064`) |
| Arm IDs / distinct arm IDs | `256 / 256` |
| Deterministic titles / distinct titles | `256 / 256`; all pass the frozen title grammar; maximum length `29` |
| Derived markers / distinct markers | `256 / 256`; collision count `0` |
| Namespace format | Exactly 32 lowercase hexadecimal characters; one OS-random sample |
| `(hidden_bit, policy_bit)` counts | `(0,0)=16`, `(0,1)=16`, `(1,0)=16`, `(1,1)=16` |
| First world | `H0=32`, `H1=32` |
| First policy within each world | H0 Replay `32`, H0 Regeneration `32`; H1 Replay `32`, H1 Regeneration `32` |
| Absolute positions 1–4 | Each has Replay `32` and Regeneration `32` |
| Original seeds | 64 unique; `3_000_000..3_000_063` |
| Regeneration bases | 64 unique; `4_000_000..4_000_252` |
| Derived Regeneration seeds | 256 unique; `4_000_000..4_000_255` |
| Original/Regeneration seed overlap | None |

These checks establish arithmetic and within-record uniqueness only. The
future exclusive registry must still check prior local reservations, and
live paper readiness must independently check the selected Google scope.
No Google, Fireworks, OAuth, browser, or network action was performed for
this record. **STUDY-2 PAPER OBSERVATIONS = 0. COLLECTION BLOCKED.**
