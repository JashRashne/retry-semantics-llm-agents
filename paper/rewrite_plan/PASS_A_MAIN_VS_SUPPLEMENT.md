# Pass A main paper versus supplement blueprint

Planning only. Keep the title **Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes**. Prefer eight total IEEE pages including references; nine is the absolute ceiling, not a target. The current hash-matched PDF has 15 pages. No figures, tables, source or abstract were edited. Facts and precise evidence identities are in [PASS_A_EVIDENCE_REPORT.md](</Users/jashrashne/Desktop/retry_semantics/paper/rewrite_plan/PASS_A_EVIDENCE_REPORT.md>); all 22 reviewer topics are in [PASS_A_REVIEWER_TRIAGE.md](</Users/jashrashne/Desktop/retry_semantics/paper/rewrite_plan/PASS_A_REVIEWER_TRIAGE.md>).

## 1. Main-paper story

Start with creating an issue after a timeout: the request may have done nothing, or it may have created the issue without returning an acknowledgement. Repeating the request can repair the first situation and duplicate the second. Returning control to the LLM permits observation and stopping, but can also produce a duplicate, omit a required write, or hit a budget. We compare those complete policies on matched originals, not an isolated reasoning or read intervention.

The chronological evidence chain must be visible: Study 1A establishes the controlled contrast; removal of its hosted model forces a prospectively recorded transition; Study 1B repeats the controlled test with DeepSeek V4.1 Flash; Study 2 tests that replacement model on external operations. GitHub shows both effective executed/lost reconciliation and some not-executed missing effects. A separately authorized Sheets replication confirms the completed pattern after a disclosed collector incident. Razorpay remains a short incomplete-result disclosure. End with conditional runtime implications, not a universal policy winner or validated new controller.

The main paper must explain final-state correctness, one intended and zero unintended effects, hidden-world construction, available read tools, marker-filtered trial scope, fixed budgets, and unknown-state handling before introducing mathematical details. Natural-language responses are unscored; latency/tokens/cost are outside the endpoint. Synthetic ambiguous messages are injected after known execution states, not sampled natural network failures. No magical model-visible correlation keys, oracle provider receipts, or automatically forced verification should be implied.

## 2. Content allocation

| Content | Main paper | Supplement |
| --- | --- | --- |
| Concrete hook and policy contrast | One issue-create example; define Exact Replay and bounded LLM Regeneration as unequal policy bundles | Exact system message, ambiguity bytes and tool schemas |
| Matched family | One original generated once, four isolated arms, two hidden states, shared initial semantic conditions; define “family” in one sentence | Fork/projection equality, serialization/request hashes, seed/order formulas, all protocol invariants |
| Scope and endpoint | CREATE-like endpoints, final external state, exactly-one/zero-unintended, unknown state retained; text/cost limits explicit | Provider state/effect proofs and full evaluator rules |
| Chronology/model overview | Compact Study 1A→1B→2 bridge; full names and model IDs in overview or one footnote; availability-driven transition | Full model configs, null digest, seeds, pre-data amendment/capability and commit timeline |
| Study 1A design and result | Eight scenarios×20,160 families; exact correctness counts, both paired effects/CIs, two-test Holm; nine write-first duplicates across four scenarios | Full8-row scenario table, all nine traces, statistical inputs, sensitivity/overhead, full-precision tests and interaction machinery |
| Study 1B | Dedicated brief subsection:160 families; not-executed both 160/160; executed/lost Replay 0/160 versus Regeneration 160/160; all read then stop, zero recovery writes | Full frozen analysis/provenance, paired CIs and exact tests, action motifs, no pooling with 1A |
| GitHub | Actual issue operation/read, matched results63/63 vs60/63 and 0/64 vs64/64; one unknown Replay explained; four missing effects separated into three no-write stops and one504;16 correct budget terminals | f020 deterministic sensitivity, full raw/member hashes,45 supersessions, original/continuation segments, split-family original identity, observation timing/pagination/visibility caps, case traces |
| Sheets | Five-sentence incident-to-replication explanation; primary behavioral denominator zero; fresh separate replication 64-family result | Constructor defect/acknowledgement provenance, primary128 projections/128 skips, repair/governance differences, new namespace/topology and operational safeguards |
| Razorpay | One short paragraph (about75 words) acknowledging three incomplete mixed prefixes under 429 | Separate2/4/12-arm prefix results; raw stop diagnostics; pacing/host/source-scope evidence, credential-hash limitation; no pooled18-arm inference |
| Statistics | Counts, rounded paired effects/CIs, confirmatory procedure only for 1A; secondary role elsewhere; perfect finite-sample caution | Full exact descriptive p-values, interaction/bootstrap details, post-hoc marginal intervals, scenario table; no invented cluster analysis |
| Mechanisms and overhead | One paragraph describing association and bounded extra actions; no causal guarantee | Full motifs, executed/attempted counts and model-call accounting |
| Limitations | Bundled policy, missing deterministic/key-enabled baselines, fixed budget, clean initial state, marker-filtered reads, eight templates/two requested model versions, synthetic ambiguity, epochs/missingness, narrow providers | Detailed provider assumptions and known provenance gaps |
| Related work | Two or three compact paragraphs around recovery/verification/idempotency; narrow distinct policy question | Extended comparison only if useful; no claim of priority for ambiguity pairing |
| Practical conclusion | Conditional advice: preserve request identity, distinguish unknown outcome from no effect, reconcile with adequate observations, retain state/procedure separation | No new controller benchmark, recipe guarantee or operational provider recommendation |
| Reproducibility | One short paragraph linking frozen data/protocol/code identities and supplement | Full hashes, lock/protocol history, analysis inputs and packaging receipts; exact PDF extraction/build check after Pass B |

Main-space incident disclosures cannot be removed merely because details move to supplement. The reader must still know why there are63 GitHub not-executed pairs, why Sheets is a separate replication, why model names change, and why Razorpay does not enter completed-study comparisons.

## 3. Exact proposed Pass B section structure and eight-page budget

Use ten compact numbered sections in the requested chronological order. The three empirical sections have short subsections, not repeated Methods/statistical tutorials. Allocate roughly3000–3700 prose words excluding references/captions; page fit must be verified in the actual IEEE template and depends on venue requirements. These fractions are design targets, not a claim of measured future layout.

| Pages of eight-page total | Section | Content and suggested prose size |
| --- | --- | --- |
| 0.40 | Title, abstract, keywords | Existing title; six-sentence abstract around180–220 words |
| 0.60 | 1. Introduction | Concrete incident, why retry policies differ, narrow research question and contribution;350–450 words |
| 0.65 | 2. Recovery after an ambiguous tool call | Hidden situations, policy bundles, conceptual Figure 1;200–300 words |
| 1.20 | 3. Experimental design | 3.1 Matched families and synthetic ambiguity;3.2 Models, tools and budgets;3.3 State-only endpoint and analysis. Table 1;450–550 words |
| 0.95 | 4. Study 1A: controlled experiment | 4.1 Setup;4.2 Correctness and observed recovery behavior. Main paired effect, conditional scope, failures distributed over four templates;350–450 words |
| 0.35 | 5. Study 1B: model-transition replication | Why model changed, why bridge needed, exact 160-family results, zero executed/lost recovery mutations;180–220 words |
| 1.45 | 6. Study 2: external validation | 6.1 GitHub issue creation;6.2 Google Sheets row appends;6.3 Incomplete Razorpay attempts. Compact Figure 2 and Table 2;550–700 words |
| 0.95 | 7. Discussion and limitations | Conditional runtime lessons; bundles/baselines/observations/models/templates/budgets/epochs;400–500 words |
| 0.45 | 8. Related work | Compact comparison, positioned around existing recovery/verification literature;250–350 words |
| 0.15 | 9. Conclusion | Practical conditional result;80–120 words |
| 0.10 | 10. Reproducibility | Frozen local evidence, analysis/prespecification and supplement pointer;70–100 words |
| 0.75 | References | Current bibliography; selected citations in compact related-work discussion. No bibliography edits in Pass A |
| **8.00** | **Total** | Figures/tables/captions included within section allocations |

Reference allowance may need0.9–1.0 pages for the existing citation count, leaving little margin. If the first real eight-page build overflows, shorten repeated prose and shrink content scope by moving detailed statistics/provenance before reducing readability. An extra page up to nine can absorb necessary references/layout; do not squeeze fonts, omit failures, delete endpoint/budget limitations, or remove Study 1B to force eight. If substantial excess remains, combine Sections 4 and 5 under “Controlled experiments” with explicitly named1A/1B subsections, while preserving chronology; the ten-section version is the primary recommendation.

No main-paper appendices are proposed. Supplement is a separate artifact, not an appendix that silently pushes the paper over nine pages. Venue instructions may constrain supplementary availability; if unavailable, the same transparency disclosures stay in the main text and detailed local evidence remains an archival pointer.

## 4. Minimal figure and table blueprint

No figures or tables are edited in Pass A. Preserve scientific values and uncertainty roles when preparing later assets. Main set: **two figures, two tables; no Table 3**.

**Figure 1: Ambiguous outcome and the two recovery policies.** One compact combined conceptual figure: “Create exactly one issue”→original call→identical timeout message; two hidden situations (“Not executed: no issue” and “Executed, acknowledgement lost: one issue”); Exact Replay's one redispatch versus LLM Regeneration's optional read/write/stop loop. Show final-state scoring (“exactly one intended effect, no unintended effects”) and cap in small annotations. The model-facing timeout is identical, with world labels outside the model context. Do not draw forced reads or guaranteed Regeneration success. A small bottom ribbon can show Study 1A→availability-driven model transition→Study 1B→Study 2 only if legible; otherwise Table 1 handles chronology. This merges the current two conceptual figures.

**Figure 2: Completed-study correctness.** Two panels labelled “Original not executed” and “Executed, acknowledgement lost.” Four study rows: Study 1A;Study 1B;GitHub;Google Sheets separate replication. Two policy marks/bars per row. Prefer exact count labels over pretending perfect scores are certain. Plot matched denominators: GitHub not-executed63; all other completed external rows64; controlled rows160. Add a caption/footnote: one GitHub Replay score is unknown; all-evaluable GitHub Regeneration60/64 differs from matched60/63; Sheets invalid primary excluded. No error bars unless labelled marginal post-hoc intervals; if error bars are used, do not substitute paired-effect CIs for score CIs. A count-only plot with paired effects in Table 2 is cleaner. No Razorpay bar, equal-world average, or pooled total.

**Table 1: Study overview (four compact rows).** Columns: study; full model name; environment/actual operation; purpose/role. Study 1A DeepSeek V4 Flash (0731), controlled ticket creation, confirmatory;Study 1B DeepSeek V4.1 Flash, same backend, transition replication;Study 2 GitHub DeepSeek V4.1 Flash, issue creation, external validation across preserved epochs;Study 2 Sheets DeepSeek V4.1 Flash, row append, separate post-incident external replication. A shared footnote identifies Fireworks and exact IDs, same scalar inference settings, different seeds/tools,160/160/64/64 allocations. Razorpay belongs to the transparency paragraph, not a fifth coequal result row.

**Table 2: Core correctness and paired effects (eight rows).** Columns: study; execution situation; matched families; Replay correct;Regeneration correct;Replay−Regeneration pp and paired 95% CI. Main prose explains one frozen Study 1A Holm result. Values are rounded for display only:

| Study | Situation | N | Replay | Regeneration | Difference (pp), paired 95% CI |
| --- | --- | --- | --- | --- | --- |
| Study 1A | Not executed | 160 | 160/160 | 160/160 | 0.0 [-2.3,2.3] |
| Study 1A | Executed/lost | 160 | 0/160 | 151/160 | -94.4 [-97.0,-89.1] |
| Study 1B | Not executed | 160 | 160/160 | 160/160 | 0.0 [-2.3,2.3] |
| Study 1B | Executed/lost | 160 | 0/160 | 160/160 | -100.0 [-100.0,-96.7] |
| GitHub | Not executed | 63 | 63/63 | 60/63 | +4.8 [-1.8,13.1] |
| GitHub | Executed/lost | 64 | 0/64 | 64/64 | -100.0 [-100.0,-92.0] |
| Sheets replication | Not executed | 64 | 64/64 | 64/64 | 0.0 [-5.7,5.7] |
| Sheets replication | Executed/lost | 64 | 0/64 | 64/64 | -100.0 [-100.0,-92.0] |

Table 2 is the numeric authority; Figure 2 supplies visual comparison. Avoid repeating every row in prose. The figure/table overlap is limited and purposeful, with uncertainty in the table. If space is tight, drop Figure 2 before dropping explanatory Methods, model bridge or incident disclosures; the preferred set remains the user's two-figure/two-table proposal. A dedicated mechanism table is unnecessary in main text: one paragraph covers nine controlled duplicates and four GitHub missing effects.

## 5. Abstract blueprint (outline only; no final abstract rewrite)

1. **Concrete hook:** A timed-out issue-create call can leave an agent unsure whether nothing happened or the issue was created without an acknowledgement; the next action can omit or duplicate the effect.
2. **Policy/design:** Explain Exact Replay versus bounded LLM Regeneration, matched on one frozen original action, with final-state rather than answer-text scoring.
3. **Study 1A:** Controlled160-family experiment: both policies160/160 when unexecuted; after execution with acknowledgement lost, Replay 0/160 versus Regeneration 151/160 (optionally the -94.4pp paired effect).
4. **Study 1B/model bridge:** Availability-driven transition from DeepSeek V4 Flash (0731) to DeepSeek V4.1 Flash; separate160-family controlled replication yields both 160/160 when unexecuted and 0/160 versus 160/160 when executed/lost. Avoid broad cross-model superiority inference.
5. **External transfer:** GitHub and separately authorized Sheets replication each give0/64 Replay versus 64/64 Regeneration after executed/lost; mention GitHub not-executed missing effects and its63-pair matched sample if giving that world's scores. One compressed sentence can say “with some missing effects in GitHub's not-executed condition” without misattributing504.
6. **Practical conclusion:** Recovery depends on hidden execution state and adequate observation; preserve request identity and reconcile with certified state rather than relying on an unconditional policy. No guarantee of a proposed controller.

Use full names when naming models, ordinary descriptions instead of H0/H1, no internal revision enums, no process receipts, and no Razorpay. This is an outline, not final abstract text. The main paper—not the abstract—must explain Sheets invalidation and the GitHub unknown arm fully.

## 6. Supplement organization

1. **Protocol and chronology:** exact original task/tool/request freeze, family semantics, study roles, pre-data commits/timestamps, model transition; hashes/digests and historical path relocation caveats. Distinguish prospective plan from post-data results lock, local freeze from public preregistration.
2. **Controlled experiments:** complete 8-scenario×20 table;1A/1B action motifs/cost counters and nine failure traces; all frozen paired tests/CIs, sensitivity and interaction draws/seed;1B inherited extractor labels explained.
3. **Descriptive uncertainty:** rounded/full-precision statistical mapping, marginal Clopper–Pearson boundary intervals explicitly post-hoc under a working binomial model; no invented cluster test. Scenario robustness described without implying a task-population sample.
4. **GitHub evidence:** mutation/read rules; OBS timing/completeness; source epochs and 45 supersessions; source-segment summaries;family 20 saved-original linkage; non-evaluable Replay proof and two deterministic sensitivity cases; four missing-effect traces and 16 budget-terminal outcomes.
5. **Sheets incident:**128 projections/128 skipped opportunities; raw acknowledgement/constructor defect; whole-family invalidation and zero primary denominator; corrected code and separate fresh-run authorization, scientific/operational differences and complete replication.
6. **Razorpay transparency:** three separate observed prefixes and schedules;429 raw stop receipts; effect attribution/duplicates, receipt omission and observation limitations; diagnostic/pacing/host history with no provider-wide/IP inference.
7. **Additional publication material:** full source/failure/interaction tables and additional figures where useful, not automatic duplication of every main asset; reproducibility commands/receipt identities and final PDF code-extraction QA after Pass B.

Eight pages require removing narrative repetition, process-heavy labels and long audit histories from the main text. They do not require changing frozen science. No title change, new experiment, re-canonicalization, commit or push is recommended or performed in Pass A.
