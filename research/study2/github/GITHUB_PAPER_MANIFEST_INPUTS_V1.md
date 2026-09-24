# GitHub Study-2 paper manifest inputs V1

**FROZEN PRE-DATA MANIFEST-INPUT DECISION — INDEPENDENT HOSTILE AUDIT PASSED**

**STUDY-2 PAPER OBSERVATIONS = 0. COLLECTION BLOCKED.**

**Independent hostile-audit provenance**

- Audit status: `PASSED`
- Pre-freeze line count: `319`
- Pre-freeze SHA-256:
  `b45a8cc57a2873a1a02c8712eb8fcd391faac3786bce88d2be55e977de932641`
- Freeze scope: status/provenance wording only; all manifest-input decisions are
  unchanged.

Paper: *Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes*
Academic byline: J. Rashne

## 1. Authority and boundary

This record selects GitHub-specific inputs delegated to a later paper manifest.
It is not a manifest, adapter, evaluator, analysis amendment, readiness
qualification, or collection authorization. The frozen GitHub paper semantics
contract, 64-family catalogue, cross-provider protocol, V1.3 analysis plan,
analysis-amendment decision, external-provider amendment, and inherited V1
execution semantics retain authority. The choices identified below as **NEW
PRE-DATA MANIFEST-INPUT DECISION** were not previously frozen. Their values
were fixed here before any Study-2 paper observation and have now passed
independent hostile audit and freeze. No observed outcome motivated them.

Repository checkpoint used: `b3884fbec5c1980f6c643be85c6d68ebb95c5ca6`.

| Controlling artifact | SHA-256 |
| --- | --- |
| `research/study2/github/GITHUB_PAPER_SEMANTICS_CONTRACT.md` | `61d5a44eff8f22fc550a2fcf168c6056cff35ce50797e266c9f41896fa673b4a` |
| `research/study2/github/GITHUB_PAPER_FAMILY_CATALOGUE_V1.json` | `5c0aeaba02cd7baeaf8b3563f28816b7f2f5eae04a4652a607d1359ade1814b5` |
| `research/protocol/STUDY2_CROSS_PROVIDER_PROTOCOL_V1.md` | `d4d20ddba32dd80249f116463d57d92d12cc762d844cb6309099604a242035b2` |
| `research/protocol/primary_create_v1_3_analysis_plan.md` | `23ecd98293a5a7b3b399aed270f8cd257c1aa9b5070d3845575ac2e02580bf88` |
| `research/protocol/STUDY2_ANALYSIS_AMENDMENT_DECISION.md` | `05ded80d5dad442f278997bb0bdbca980f2d42261b0f6d058d08996970b443ba` |
| `research/protocol/STUDY2_EXTERNAL_PROVIDER_AMENDMENT_V1.md` | `21ff3b3ca90d27a46669e12bab62de89d7ddd191ba96dfa5a8e12c0a69521ecb` |

## 2. Exact paper repository selection

**NEW PRE-DATA MANIFEST-INPUT DECISION.** Select owner `JashRashne`, repository
`retry-semantics-study2-github-sandbox`, and exact full scope
`JashRashne/retry-semantics-study2-github-sandbox`.

```text
SCOPE_SELECTED = YES
SCOPE_QUALIFIED = NO
```

The repository's previous engineering use is historical baseline state only.
Engineering issues, markers, IDs, traces, and results are excluded from paper
families and denominators. Do not delete, edit, close, transfer, or clean up
those issues for this study. They remain in the raw issue-plus-PR baseline
and page count. This selection does not establish the repository's current
state, stable repository ID, authenticated principal, or access rights.

Before any paper collection, a separate readiness gate must bind and verify
the exact HTTPS API origin/base prefix, date-form API version, stable repository
identity and authenticated principal with Issues read/write access; completely
enumerate the raw `state=all` issue-plus-PR baseline; prove that baseline is at
most 860; establish exclusive-writer/quiescence controls; prove paper suffix
round-trip and authoritative traversal behavior; and qualify request,
secondary-rate-limit, and execution headroom. No value for a current baseline,
quota, credential, or principal is asserted here. Failure of a required gate
blocks this scope; it cannot be repaired by paper-outcome-driven substitution.

## 3. Paper run namespace and arm correlation

**NEW PRE-DATA MANIFEST-INPUT DECISION.** The one paper run namespace is
`d88836f3d4b57ed5c300d650ddfb0e3a`. It was sampled once as 128 bits from
the operating system's cryptographic random source and is now a fixed literal.
The namespace is 32 lowercase hexadecimal characters. No runtime sampling,
timestamp, semantic title/body, model output, or provider state participates
in later marker construction. It is evaluator-only and never model-visible.

For each frozen catalogue family ID `gh-fNNN`, reserve exactly these four
arm IDs, in this spelling:

```text
gh-fNNN:H0:EXACT_REPLAY
gh-fNNN:H0:LLM_REGENERATION
gh-fNNN:H1:EXACT_REPLAY
gh-fNNN:H1:LLM_REGENERATION
```

`H0` means `NOT_EXECUTED`; `H1` means `EXECUTED_ACK_LOST`. For each arm ID,
use the frozen GitHub contract's grammar exactly:

```text
arm_marker = "rs2gh1-" + first_32_lowercase_hex(
    SHA256(UTF8(run_namespace + ":" + arm_id)))
suffix = "\n\n<!-- retry-semantics-study2-gh:v1:" + arm_marker + " -->"
provider_raw_body = model_semantic_body + suffix
```

The exact UTF-8 hash input is the 32-character namespace, one ASCII colon,
then the entire case-sensitive arm ID. The first 32 lowercase hex characters
of the SHA-256 digest follow `rs2gh1-`. The suffix is appended only by the
harness to the arm-local provider request `W_arm`; it never changes the
family-wide generated semantic title/body or `M`. Original and Replay within
one arm retain the identical stored `W_arm` bytes/hash and suffix. Every
permitted Regeneration Create in that arm uses that same suffix. The later
manifest must materialize all 256 arm IDs, markers, exact suffixes, and
provider-body byte lengths/hashes before any dispatch.

The frozen catalogue has 64 distinct IDs and the four arm labels are distinct,
so all 256 arm IDs are unique. Exhaustive offline derivation with the literal
namespace produced 256 distinct 128-bit marker suffixes: no collision within
this reservation. Known historical engineering marker grammars use
`ENGINEERING-ONLY-` or `ENGINEERING-AMBIGUITY-ONLY-`, not `rs2gh1-` plus the
paper HTML suffix; those marker strings cannot equal a paper marker string.
This syntactic fact does **not** prove that an unknown existing issue body
lacks an exact paper suffix. Before manifest freeze, enter this fixed namespace
and all 256 deterministic arm reservations into the study's durable **local**
cross-run registry. Check that registry for prior use of the namespace by any
paper manifest/run known to the harness, and refuse reuse or an offline marker
collision. This local reservation check requires no GitHub request or live
baseline. The complete current repository baseline and exact live suffix-
collision scan belong to the later readiness gate, after manifest, adapter,
evaluator, and offline validation. A live exact-suffix collision makes the
selected manifest/scope **NOT READY**. It does not authorize silently changing
this namespace; pre-data resolution requires a new prospectively versioned
manifest/input revision, independent hostile audit, and freeze before collection.

## 4. Family order and four-arm counterbalancing

**NEW PRE-DATA MANIFEST-INPUT DECISION.** The 64 scheduled original-generation
opportunities execute exactly once in frozen catalogue order:
`gh-f001`, `gh-f002`, ..., `gh-f064`. Zero-based schedule index `i` is the
catalogue array index, 0 through 63. There is no family-order shuffle or
family-order seed. The catalogue contains one distinct task per family and
no frozen rule requires randomization of their order. This fixed order is
outcome-independent and keeps task materialization auditable. An ineligible
or invalid opportunity is retained and never replaced, refilled, resampled,
or moved to a later position.

**NEW PRE-DATA MANIFEST-INPUT DECISION.** Preserve the inherited V1 pair-block
meaning: one eligible family supplies one `M`, both hidden worlds, and the two
opposing policy orders, with four arms run serially. Use these GitHub-specific
scheduling controls and exact arithmetic for each scheduled index `i`:

```text
hidden_world_order_seed = 1
policy_order_seed = 1
hidden_world_orientation_bit = (hidden_world_order_seed + i) mod 2
policy_orientation_bit = (policy_order_seed + floor(i / 2)) mod 2

hidden_world_orientation_bit 0 -> [H0, H1]
hidden_world_orientation_bit 1 -> [H1, H0]
policy_orientation_bit 0 -> first world [EXACT_REPLAY, LLM_REGENERATION]
policy_orientation_bit 1 -> first world [LLM_REGENERATION, EXACT_REPLAY]
second world -> reverse of the first world's policy order
```

These are new Study-2 GitHub scheduling inputs, separate from all model seeds.
The two-index policy cadence is a prospective adaptation for 64 *unique*
families: using the V1.2 engineering scenario-ordinal parity together with
hidden-world alternation would confound policy order with world for this
catalogue. The inherited mapping from orientation bits to serial arm orders
is unchanged. The later manifest must materialize and validate each family's
hidden-world order, H0 policy order, H1 policy order, and four arm positions;
runtime recomputation or outcome-adaptive arm choice is prohibited.

For the first four families the `(hidden_world_orientation_bit,
policy_orientation_bit)` sequence is `(1,1)`, `(0,1)`, `(1,0)`, `(0,0)`;
it repeats every four families. Exhaustive offline calculation gives 16
families in each combination, 32 H0-first and 32 H1-first families, 32
Replay-first and 32 Regeneration-first assignments *within each hidden world*,
and 32 of each policy at each of the four serial arm positions. These are
properties of all 64 scheduled opportunities, not a promise that the
eligibility-filtered set will remain balanced.

## 5. Model and model-call seeds

The model science is inherited from the frozen cross-provider protocol and
its cited `primary_create_v1_3_collection_infrastructure.md` freeze:

| Field | Exact value |
| --- | --- |
| Provider | `fireworks` |
| Requested model | `accounts/fireworks/models/deepseek-v4-flash-0731` |
| `version_or_digest` in manifest identity | `null` |
| Temperature | `0.0` |
| `top_p` | `1.0` |
| Maximum completion tokens | `1024` |
| Tool choice | `AUTO` |
| Parallel tool calls | `false` |
| Provider parameters | `{"reasoning_effort":"none"}` |
| Seed support | `true`, as recorded by the cited model configuration; seed support is not a bitwise determinism guarantee |

The requested model remains `accounts/fireworks/models/deepseek-v4-flash-0731`
and the manifest identity uses `version_or_digest = null` unconditionally.
If Fireworks later exposes an independently verified immutable deployment
identifier, record it only as separate readiness/run provenance. It must not
silently replace the frozen manifest identity. Changing that identity requires
a new prospective manifest-input revision and independent audit before any
Study-2 paper observation.

The common V1 system message and GitHub `create_issue`, then `list_issues`,
tool definitions remain exactly as in the frozen protocol and GitHub contract.
The user task is materialized once from the frozen catalogue template and
literal title/body. It contains no family ID, arm ID, namespace, marker,
hidden-world label, policy label, or evaluator timing. Model availability and
tool compatibility remain a separate pre-data gate.

**NEW PRE-DATA MANIFEST-INPUT DECISION.** For zero-based family index `i` in
`0..63`, use exactly one original-generation model configuration and call:

```text
original_generation_seed(i) = 1_000_000 + i
```

Its 64 distinct integer seeds run from `1_000_000` through `1_000_063`.
Generate and serialize eligible `M` once for the family, then share it with
all four arms; no arm-local original generation exists.

**NEW PRE-DATA MANIFEST-INPUT DECISION.** For that same family, use one
Regeneration base seed in both H0 and H1 Regeneration arms:

```text
regeneration_base_seed(i) = 2_000_000 + 4*i
regeneration_seed(i, model_call_index) = regeneration_base_seed(i) + model_call_index
model_call_index in {0, 1, 2, 3}
```

The 64 distinct base seeds run from `2_000_000` through `2_000_252`, in
steps of four. Their derived model-call seeds occupy nonoverlapping blocks
and span `2_000_000` through `2_000_255`. The derivation and shared-world
rule are inherited from V1; only the GitHub-specific base schedule is new.
Indices count model invocations, not tool attempts. No seed is derived from
an outcome, world, arm, provider response, runtime random draw, wall clock,
or the order-control seeds. These ranges are deliberately disjoint from the
Ticket paper seed ranges in the cited infrastructure record; their numeric
values carry no claim of statistical independence or deterministic output.

## 6. Serial scheduling and infrastructure policy

**NEW PRE-DATA MANIFEST-INPUT DECISION.** Run one scheduled family at a time,
in Section 4 order. Within an eligible family, execute the already-materialized
four-arm order serially. Never overlap paper arms or GitHub mutation, baseline,
constructor, model-selected read, reconciliation, scheduled observation, or
evidence persistence activity in this repository. The next arm or family starts
only after the preceding unit's required evidence is durably persisted and
its fixed observer path has terminated under the frozen stop rule. For an
ineligible original generation, persist its scheduled-attempt evidence before
advancing. There is no extra minimum inter-arm or inter-family sleep beyond
serial completion and the frozen within-arm OBS-1 schedule. A readiness check
must establish that this exact policy is feasible with available quotas;
failure does not authorize adding adaptive spacing after paper collection.

Disable hidden retries, SDK/auth reissue, redirects, automatic resend,
parallel calls, and outcome-adaptive polling. A single connection failure,
timeout, `5xx`, malformed response, or incomplete read is recorded with its
dispatch/response evidence as infrastructure for the affected scheduled
operation. It receives no silent retry, replacement, rescue read, extra model
call, extra sleep, or shifted schedule. The fixed run otherwise continues
under its already-materialized serial schedule and frozen OBS-1 rules. A failed
or incomplete read is never interpreted as zero effects. The frozen construction,
evaluability, and V1.3 sensitivity rules determine its evidence treatment;
no outcome-dependent exclusion is added.

For **any GitHub `403`, HTTP `429`, or explicit secondary-rate-limit event**,
record the event and exact provider evidence; never retry the failed request.
If the current arm already entered policy execution, preserve only its later
OBS-1 observations already mandated at their fixed offsets, subject to the
frozen early-stop rules. Do not add an observation. An explicit provider
`Retry-After` or prohibition that makes a fixed observation impermissible is
not overridden: record that scheduled observation as infrastructure-unexecuted/
incomplete. After this arm reaches its fixed terminal evidence boundary,
terminate the GitHub provider run before another arm or family starts. If the
event occurs before an arm reaches policy entry, terminate the provider run
immediately, preserving the current scheduled-attempt/system evidence. Persist
scheduled-attempt/system evidence for every not-yet-started opportunity,
identifying the run-level infrastructure stop. This **same frozen run must
never resume** after quota reset, credential repair, or waiting. Do not replace,
refill, reorder, or append remaining families. These events are
provider/infrastructure evidence, not model behavior.

If this run-level stop occurs before Study-2 paper observation #1, a later
attempt is permitted only after the blocking condition is resolved and all
affected pre-data artifacts are prospectively versioned, independently audited,
and frozen again.

If the stop occurs after any Study-2 paper observation has been recorded, this
primary GitHub provider run is permanently closed. No later run may replace,
refill, complete, or supplement its unexecuted scheduled opportunities for the
same primary Study-2 analysis. Any later execution must be declared and governed
as a separate replication/follow-up dataset and must not be folded into the
frozen primary run.

OBS-1 is incorporated by provenance, without changing its timing: each arm's
post-recovery `r0` anchors GitHub starts at `+0` and `+600` seconds, completion
deadlines `+540` and `+1140`, and the common `H=1140`. Each traversal permits
1–16 validated requests and at most 540 elapsed seconds. The frozen H1
constructor opportunities and early-stop certificates also remain unchanged.
No extra round, shifted deadline, or observer rescue is authorized here.

## 7. Selection versus qualification and remaining gates

**SELECTED NOW:** exact repository string; one fixed paper namespace; 256
derivable arm IDs and markers; catalogue family order; hidden-world and policy
order controls; inherited model identity/configuration; new original and
Regeneration seed schedules; serial/failure policy. No paper outcome field is
present in this record.

**BEFORE MANIFEST FREEZE, OFFLINE/LOCAL ONLY:** register the fixed namespace
and 256 arm reservations in the durable cross-run registry; prove no known
paper-run namespace reuse and no derived-marker collision. This is not a live
repository qualification or a request to GitHub.

**NOT QUALIFIED NOW:** current repository baseline and the `<=860` proof;
stable repository identity; authenticated principal/access; exclusive-writer
control; live suffix preservation/collision absence; raw traversal and
terminal-state authority; provider/model capability; current request and
secondary-rate-limit headroom; final paper adapter/evaluator and manifest;
final hostile audit/readiness freeze;
separate collection authorization. The selected engineering repository
therefore remains unqualified for paper use.

This record makes no GitHub request and contains no credential, token, issue
number, live baseline, or authenticated-principal identifier. The repository
owner handle above is included only because it is the explicitly selected
repository identity. Any unresolved qualification or implementation gate
continues to block collection. **STUDY-2 PAPER OBSERVATIONS = 0. COLLECTION
BLOCKED.**
