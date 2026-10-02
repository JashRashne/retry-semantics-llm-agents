# Supplement: Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes

## Scope and evidence guide

This separate supplement retains detail omitted from the main paper. It presents stored study results, collection provenance, and the post-hoc descriptive summaries recovered from the stored data. It introduces no new experimental observations or primary statistical procedure. Main-paper terminology applies: $H_0$ means Original action did not execute; $H_1$ means Executed, acknowledgement lost. These are execution-world labels, not null and alternative hypotheses.

The artifact evidence registry (`paper/rewrite_plan/PASS_A_EVIDENCE_REPORT.md`) is the complete source-path and SHA-256 registry, with source IDs A1--A7 for Study 1A, B1--B7 for Study 1B, G1 for the sealed GitHub archive, E1--E9 for external analysis and record linkage, S1--S3 for the Sheets replication, P1--P6 for protocols, M1--M3 for manifests, and C1--C3 for provider observation contracts. Its CSV companions retain full numerical precision, scenario identifiers, and action-path membership. This supplement explains the evidence rather than replacing that registry.

## Protocol chronology and model configuration

The original retry question and controlled backend were recorded in September 2026. Study 1A's prospective analysis plan was recorded on 16 September at commit `89e3f658cba8dfa87575b840dc9392fec981b165`. Collection on 17 September used checkpoint `add9a783df2fede9b05026f8e13c6c623fe5a3c5` and a predeclared 160-family allocation. The outcome record at `ab6fc82` followed collection; it is a post-data outcome record, not prospective registration. Repository history and run metadata support this ordering, but are not independent public preregistration.

Study 1A used DeepSeek V4 Flash (0731) through Fireworks serverless, ID `accounts/fireworks/models/deepseek-v4-flash-0731`. The later model-availability record documents its removal from that inference path and was made before Study 2 outcomes. Study 1B, collected 27 September 2026 at `4a3bed8c9f64136c7736b29e3105771993856898`, repeated the controlled design with DeepSeek V4.1 Flash, ID `accounts/fireworks/models/deepseek-v4p1-flash`. Study 2 subsequently used that exact requested ID and scalar settings. The record's operational explanation is historical evidence, not a current provider-availability check.

All studies requested temperature 0.0, top-p 1.0, maximum output tokens 1024, reasoning effort none, automatic tool choice, and no parallel tool calls. No immutable model digest was recorded, and hosted inference at temperature zero does not establish deterministic weights or execution. Controlled originals used seed `30000+i`; recovery bases used `40000+10i`. GitHub used `1000000+i` and `2000000+4i`; Sheets and Razorpay used `3000000+i` and `4000000+4i`. Continuation seeds increment by model-call index. Thus matching model/settings does not mean identical tool schemas, tasks, or seed schedules.

The four scheduling strata combine hidden-world order with policy order in the first hidden-world pair: A uses $H_0,H_1$ with Replay first; B uses $H_1,H_0$ with Regeneration first; C uses $H_0,H_1$ with Regeneration first; D uses $H_1,H_0$ with Replay first. The second pair reverses the policy order; each stratum has 40 families globally and five per scenario (`research/protocol/primary_experiment_v1.md` and `research/protocol/primary_create_v1_3_collection_infrastructure.md`).

The raw six-file collections and derived analysis hashes for both controlled studies were verified against the artifact evidence registry. Full paths and component hashes remain in that registry. Selected analysis and archive identities appear in Table \ref{tab:s-identities}; their full paths are in the registry.

\input{supplement/tables/source_identities.tex}

## Statistical details retained from the completed studies

### Paired estimates and tests

The main table displays retained paired estimates and intervals with one decimal of presentation rounding. The supplementary results artifact (`paper/rewrite_plan/PASS_A_RESULTS_TABLES.csv`) retains full precision and source identities. The endpoint is binary final-state correctness when state is evaluable, with Replay minus Regeneration as the paired contrast. Newcombe method 10 gives two-sided 95% paired intervals. Exact conditional two-sided McNemar tests use discordant pairs; Study 1A's multiplicity family contains exactly its two execution situations, with Holm adjustment.

Study 1B's existing extractor retains inherited primary/co-primary labels and a separate two-comparison Holm result. We report it scientifically as a model-transition replication; those labels do not authorize pooling it with Study 1A or expanding the initial confirmatory claim. GitHub and Sheets tests are secondary descriptive and unadjusted, without external significance decisions. Razorpay stopped prefixes have no authorized inferential tests or intervals.

Table \ref{tab:s-tests} retains the exact test outputs.

\input{supplement/tables/tests.tex}

### Interaction and whole-family bootstrap

The interaction is the already-executed paired difference minus the not-executed paired difference. For each retained complete family, the bootstrap resamples its entire four-outcome vector, preserving within-family linkage. Existing analyses use 10,000 percentile draws with seed 20260916. External percentile indexes are 249 and 9749 (zero based). No interaction p-value was frozen. The reported bootstrap estimates and intervals are the stored study outputs.

Table \ref{tab:s-interactions} retains the complete-family contrasts.

\input{supplement/tables/interactions.tex}

A degenerate interval, such as [-100,-100], reflects identical contributions in the observed sample and this resampling scheme; it does not establish absence of provider, task, or model uncertainty. The family bootstrap does not solve dependence from repeated fixed scenarios. Eight templates are not a clearly defensible random sample of independent scenario clusters. We therefore add no ad hoc cluster-aware test or bootstrap, and limit scenario evidence to descriptive counts.

### Post-hoc marginal boundary intervals

A post-hoc descriptive calculation using the stored data gives two-sided 95% exact Clopper--Pearson boundary intervals under a working binomial model. For all-success samples the lower bound is $0.025^{1/n}$; for all-failure samples the upper bound is $1-0.025^{1/n}$. These are marginal correctness intervals, distinct from paired contrast intervals. They do not account for repeated-scenario dependence, are not frozen primary statistics, and are not new tests of superiority or equivalence.

Table \ref{tab:s-marginal} gives the descriptive boundary intervals.

\input{supplement/tables/marginal.tex}

## Controlled-study scenarios and recovery actions

### Study 1A scenario breakdown: post-hoc descriptive

Each of eight scenarios has 20 separately scheduled original generations. In every scenario, both policies are correct in 20/20 not-executed cases and Replay in 0/20 already-executed cases. Table \ref{tab:s-scenarios} supplies Regeneration's already-executed breakdown; the supplementary scenario-results artifact (`paper/rewrite_plan/PASS_A_SCENARIO_RESULTS.csv`) gives all four cells, replicate numbers, and source hash. Failures occur across four templates, rather than only one or two. The support-incident descriptions differ, but all use the same ticket-create operation.

\input{supplement/tables/scenarios.tex}

### Executed action paths: post-hoc descriptive

Table \ref{tab:s-actions} describes executed tool sequences followed by a model stop. A stop consumes a model call but no tool action. These are descriptions of stored traces, not randomized mechanism assignments. Study 1A's 151 correct already-executed Regeneration cases read and stopped; all nine failures wrote first and produced exactly two matching tickets with zero unintended tickets. Five then read and described the duplicate, without a delete tool available; four stopped after the write and claimed success in unscored text. No observed sequence contained an additional recovery mutation.

\input{supplement/tables/actions.tex}

Study 1A not-executed Regeneration totals are 592 model calls, 432 tool actions, 272 reads, and 160 writes; means are 3.70 and 2.70 model/tool calls. Its already-executed totals are 325 model calls, 165 tools, 156 reads, and nine writes; means are 2.03125 and 1.03125. Five write--read--stop paths account for the extra five calls above an all-read--stop population, while four write--stop failures have the same count as read--stop successes. Mean counts alone do not identify all failures.

Study 1B not-executed totals are 610 model calls, 450 tools, 290 reads, and 160 writes; already-executed totals are 320 model calls, 160 reads, and zero writes. In Study 1B both situations have 160/160 read-first recoveries. The controlled studies record zero Regeneration malformed/rejected generation, invalid-tool/schema termination, wrong-content effect, and budget-exhaustion flags; all Study 1B Regeneration outcomes are correct. Full path members and hashes remain in the supplementary action-pattern artifact (`paper/rewrite_plan/PASS_A_ACTION_PATTERNS.csv`) and the original traces, rather than compressed call means.

## GitHub: state observation and collection provenance

### Mutation and observation contract

The operation is issue creation in `JashRashne/retry-semantics-study2-github-sandbox`: `POST /repos/{owner}/{repo}/issues` with semantic title and body. The model's `list_issues` tool uses `GET /repos/{owner}/{repo}/issues?state=all&per_page=100`, validating pagination links, excluding pull requests, and retaining duplicate trial-matching issues. The bounds permit up to 16 pages and 540 seconds per census. There is no search shortcut or direct issue-ID GET oracle. Model-visible absence includes a warning about possible nonvisibility.

Evaluation offers a census at recovery end and another 600 seconds later, subject to early stopping for a certified irreversible defect. Complete success requires the specified observation evidence; lower bounds are not complete absence or uniqueness proofs. A single complete read with one effect cannot repair a later incomplete required read. HTTP create status and textual success are not substitutes for final state.

### Why collection continued, and why there are not 301 trials

The original collector's pagination parser rejected opaque GitHub cursor URLs. After repair, the continuation preserved all 77 recoveries that had already entered a policy, including the one unknown Replay result, and selected only untouched identities. These consisted of 45 failed read-only baselines and 134 skipped opportunities: 179 later records. Of 122 original records plus 179 continuation records, 45 overlap before recovery began, leaving 256 unique policy/world identities. They are 64 planned families, not 301 independent observations.

The 45 earlier baseline records remain historical evidence and are excluded as replacements for the same untouched identities. Their replacement outcomes include 33 successes and 12 failures; selection was not based on choosing favorable policy results. A family spanning collection segments still uses its saved original assistant message, not a newly generated mutation. For family 20, the original identity is given in Table \ref{tab:s-identities}. Each evaluation's physical scope and marker differ, but the shared original semantic mutation premise is retained. Temporal drift remains a limitation.

The original entered segment has 19 matched not-executed pairs, Replay 19/19 versus Regeneration 16/19, and 19 already-executed pairs, 0/19 versus 19/19. The continuation has 44 matched not-executed pairs, both 44/44, and 45 already-executed pairs, 0/45 versus 45/45. These overlapping source summaries explain provenance; they are not new independent replications. The final record set has 187 correct, 68 incorrect, and one unknown outcome, with 63 complete four-evaluation families.

### The one non-evaluable result

One not-executed Replay recovery sent the stored POST, and its first census completed with a lower bound of one matching effect. The required later census failed pagination safety validation, so final correctness remains unknown. Its identifier is `gh-f020:H0:EXACT_REPLAY`. The retained archive member is `original-run/collection/076-gh-f020-1/arm-projection.json` under the sealed archive's top-level directory. This policy-entered case was not eligible for recollection. Its Regeneration partner is known incorrect, producing the different matched and all-evaluable not-executed denominators.

### Missing-arm sensitivity: post-hoc deterministic

The primary matched result is untouched. Assuming the unknown Replay state correct gives Replay 64/64 versus Regeneration 60/64, a +6.25 percentage-point contrast. Assuming it incorrect gives 63/64 versus 60/64, +4.6875 points. The retained matched contrast is 63/63 versus 60/63, +4.761904761904762 points. These count/point alternatives assign no probability and introduce no new CI or test. A one-effect lower bound does not exclude additional unintended or duplicate effects, so both possible binary scores are considered. The already-executed result is unaffected.

### Four missing required effects and attribution

The four not-executed Regeneration missing-effect cases all read twice; their final evaluator censuses were complete and showed zero intended effects. None exhausted budget. In family 2 the model attempted a correct mutation, received HTTP 504, and ended with unresolved dispatch outcome before final absence was established. It is a provider/runtime-ambiguous failure mechanism, not omission of a write. In families 6, 15, and 20, the model stopped after the two reads, citing visibility uncertainty and duplicate risk, with no mutation attempted. A mutation HTTP status is therefore not applicable to those three cases.

Table \ref{tab:s-github-missing} separates the four failure paths.

\input{supplement/tables/github_missing.tex}

The sealed evidence registry gives each projection and terminal model-message hash and member directory: original `004-gh-f002-1`, `020-gh-f006-1`, `058-gh-f015-3`, and continuation `000-gh-f020-2`. All four count among evaluable Regeneration outcomes; only three enter matched not-executed pairs. The state score does not eliminate transport ambiguity for the attempted HTTP 504 write. Separate certified external malformed/schema-rejected and infrastructure-attribution mappings are unavailable; no heuristic classification fills those gaps with zeros.

## Google Sheets: invalidation and separate replication

The primary attempt scheduled 64 four-evaluation families, or 256 opportunities. It recorded 128 results: 32 Replay and 32 Regeneration not-executed successes, and 32 per policy already-executed constructor rejections. The remaining 128 opportunities were invalidated skips. The collector set `DispatchFacts.acknowledgement_validated=True` before a validator that requires unvalidated raw transport facts. Valid acknowledgement evidence was consequently rejected before valid already-executed recovery could begin.

Common-protocol section 8 excludes the entire four-evaluation family when a shared execution-world constructor is invalid. All 64 families were affected, leaving zero behavioral arms, pairs, and complete families. Earlier not-executed successes remain historical records, not a usable primary comparison. The constructor defect is not a model failure and cannot be corrected by selectively retaining its favorable cells.

The implementation fix is `0761929d12366f840c24ebca2203f19b461962a7`. The owner authorized a new, separate replication before fresh collection, with plan checkpoint `b82f440beca27de89ce99a4ec114ad9e72bed5bf` on 28 September. It used a new spreadsheet and namespace, newly generated originals, the same scientific allocation/model/seeds/bounds, explicit collector repairs, pacing, and stronger operational stop handling. This is operator-reviewed authorization, not a claim of independent preregistration. The attempt is retained separately instead of retroactively repairing or replacing primary records.

The completed replication has 256 evaluable outcomes: 192 correct and 64 duplicate-producing Replay failures. Both policies are correct in 64/64 not-executed cases; in already-executed cases Replay is 0/64 and Regeneration 64/64. Regeneration executes 64 writes and 100 reads when the append is absent; it reads 64 times and never writes when it exists. No Regeneration budget exhaustion occurs. Four qualification controls are outside behavioral denominators. `append_row` maps to an `AppendCellsRequest` batch update; `list_rows` reads the assigned A1:C100 grid, with marker column A and semantic fields B/C.

The invalid primary's native directory and separately archived forensic directory, replication manifest/plan/run hashes, and protocol source are linked in the artifact evidence registry's Sheets incident section. Their separation is retained in every headline result and figure.

## Razorpay stopped prefixes and operational diagnostics

Each of three separate attempts scheduled 64 families and 256 recoveries. The first evaluated two, both incorrect duplicates, and left 254 unrun. The paced attempt evaluated four, two correct and two duplicate failures, and left 252 unrun. The host-migration attempt evaluated 12, seven correct and five duplicate failures, and left 244 unrun. These are incomplete observed prefixes, not a pooled sample of 18.

The first has one already-executed pair, both policies 0/1, and no not-executed pair. The paced attempt has one pair per situation: both 1/1 not-executed, both 0/1 already-executed. The host-migration attempt has three pairs per situation: both 3/3 not-executed, Replay 0/3 and Regeneration 1/3 already-executed. The prefix is mixed and unfavorable to any claim of uniform Regeneration success. No stopped-run confidence interval, test, provider-wide effectiveness estimate, or comparison of apparent rates across attempts is supported.

All collection stops have underlying HTTP 429 during Fetch All Orders reads. The historical exception wrappers are ValueError for the first and PaperCollectionError for the later attempts. An operational stop is not a policy failure, although positively established duplicates can remain known defects despite later throttled observation. Orders used Test Mode create and list operations, with causal dispatch/resource evidence supplementing list observations; list absence alone is not authoritative.

The detailed retained tables are `paper/publication_data/table5_razorpay_stops.csv`, `tableA4_razorpay_points.csv`, and `tableA5_razorpay_mechanisms.csv`, with raw receipt locations in the artifact evidence registry. Pacing, host paths, namespace separation, and capacity diagnostics are operational history, not randomized interventions. A same-target localization check saw 429 from one execution/source path and 200 from another. That does not isolate IP causality, identify a rate-limit algorithm, or establish a larger per-IP quota. Historical credential equality is also not independently established on one side.

## Correlation markers and recovery budgets

### Attribution markers

Controlled ticket studies use isolated cloned state and semantic matching, without external tag injection. GitHub uses `rs2gh1-` followed by the first 32 hexadecimal characters of SHA-256 over namespace, colon, and arm ID. The harness appends an HTML-comment suffix to the issue body: `<!-- retry-semantics-study2-gh:v1:<marker> -->`. It strips the exact suffix from model-visible records and checks requested title/body while counting distinct issues.

Sheets uses `RS2-SHEETS-V1-` with the same hash construction in column A; model-visible records contain only B/C content. Razorpay uses `study2_rzp_paper_` plus the derived token in `notes.retry_semantics_marker`; model arguments and projected reads omit it. The optional receipt field is omitted so it cannot mask duplicates through a key-like mechanism. This is a claim about the studied construction, not all provider idempotency behavior.

The protocols sample 128-bit namespaces and check their materialized marker registries and initial state for collisions, refusing collection on a collision. This is collision-controlled reservation, not mathematical proof of globally impossible collisions. Every write within one recovery retains the same trial marker, including duplicate or wrong-content writes. Providers see the metadata; the model does not. Tags change physical representation but not scored semantic fields or the exactly-one-effect requirement. They simplify attribution and trial-local filtering, and the experiment does not quantify the difficulty of unmarked reconciliation.

### Budget accounting

Replay has one deterministic dispatch and zero recovery model calls. Regeneration permits at most three tool-action attempts and four model calls; reads, writes, and invalid in-budget attempts consume actions, while text-only stop consumes only a call. Original generation, original-execution construction, and final evaluator observations are excluded. No hidden retries, repair completions, or budget refill occur. A census is one logical action with additional traversal limits, rather than one action per page.

The cap was chosen to permit read--write--optional-confirm and prevent loops, not optimize recovery performance. GitHub not-executed Regeneration has 16 budget-exhaustion terminals, all state-correct: five in original collection and 11 in continuation. Their family numbers are 5, 9, 13, 16, 17, 29, 37, 39, 40, 46, 47, 50, 55, 57, 60, and 63. No already-executed GitHub, controlled-study, or Sheets Regeneration case exhausts budget. Final textual correctness was not measured, so state-correct truncation does not establish a satisfactory user-facing answer.

## Model-visible recovery prompts and tool interfaces

The controlled, GitHub, and Sheets studies share the exact system message: *You are a tool-using assistant. Complete the user's task using the available tools.* The exact ambiguous tool-result message is *ToolError: The previous request timed out. Its outcome is unknown.* Recovery retains the original user task and stored assistant tool call before this message; subsequent tool results extend that history.

### Controlled ticket interface

The frozen task template is *Create exactly one support ticket for customer "{customer_id}" with title "{expected_title}" and description "{expected_description}".* The exact tool descriptions are `create_ticket`: *Create one support ticket.* and `list_tickets`: *List the support tickets currently present.* The read description contains no verification or reconciliation instruction. Full parameter schemas and recovery-context ordering are in `research/protocol/primary_experiment_v1.md`; the implementation is `src/retry_semantics/runtime/regeneration_context.py` at the Study 1A and Study 1B execution commits recorded above.

### GitHub interface

One frozen original task is *Create exactly one GitHub issue with title "Profile photo preview remains blank" and body "The profile photo preview stays blank after an image is selected." in this repository.* The exact tool descriptions are `create_issue`: *Create one issue with the specified title and body.* and `list_issues`: *List issues currently visible in this trial scope; an absent issue may still be unobserved.* Thus the absence warning is explicitly part of the read-tool description. The complete task catalogue and schemas are in `research/study2/github/GITHUB_PAPER_MANIFEST_V1.json`, whose bytes match both `original-run/manifest.json` and `continuation-run/manifest.json` in the sealed GitHub archive identified in the artifact evidence registry.

### Google Sheets interface

One frozen original task is *Append exactly one row with item "Blue notebook" and detail "A compact notebook with a matte blue cover.".* The exact tool descriptions are `append_row`: *Append one row with the specified item and detail to this trial's list.* and `list_rows`: *Read all rows currently in this trial's bounded list.* Full parameter schemas are in the `model_visible_common` field of `research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_V1.json`; that field is identical in the separate replication manifest (source S1 in the artifact evidence registry). The replication manifest contains its own frozen task catalogue. The read description specifies a bounded list and contains no explicit verification or reconciliation instruction.

## Artifact preservation and offline access

The repository retains stored protocols, source collections, evidence artifacts, result tables, and offline analysis scripts. The artifact evidence registry supplies source paths, scientifically relevant hashes, additional stored tables, and complete trace locators; supplementary CSV artifacts retain the stored numerical outputs. The bibliographic source is `research/references.bib`.

The main paper and supplement sources are `paper/manuscript.md` and `paper/supplement/manuscript.md`, respectively. Offline analysis scripts and source collections support reproducibility of the reported results; accessing the stored evidence and result tables requires no live research-provider requests.
