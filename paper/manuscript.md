# Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes

## Abstract

An ambiguous timeout after a state-mutating tool call leaves a recovery controller to determine whether the intended effect exists and whether another mutation is justified. We study this state-reconciliation problem through Exact Replay, bounded LLM Regeneration, and a post-review deterministic observe-then-create-if-absent baseline. Controlled ticket experiments and live GitHub and Google Sheets validation score final external state. Replay duplicates an already-completed unprotected CREATE by construction. Regeneration often inspects state and avoids that duplicate: it succeeds in 151/160 already-executed cases in the first ticket study, 160/160 in the model-transition replication, and 64/64 each on GitHub and Sheets. GitHub also exposes missing-effect failures: four of 64 evaluable Regeneration recoveries leave a required issue absent, including one HTTP 504 write attempt. The deterministic baseline succeeds in all 896 post-review opportunities with usable decision observations and zero LLM calls. In these tested observable-state settings, model reasoning was not required for the recovery decision. The central abstraction separates stored request identity, evidence about external state, and the rule authorizing another mutation.

## Introduction

Suppose an agent sends a request to create a customer-support issue and receives a timeout. The runtime cannot tell whether the write failed to execute or succeeded with its acknowledgement lost. Sending the same bytes again preserves the request, but deciding whether another issue is needed requires evidence about external state. Recovery therefore has three distinct concerns: stored request identity, evidence that the intended effect exists, and a rule deciding whether another mutation is justified.

Remote-call uncertainty and repeated delivery are established distributed-systems problems \cite{birrell_nelson,helland_idempotence}. Tool-using language models expose a recovery boundary where the runtime can redispatch the stored request or return control to the model. Model continuation can read state, reconsider the action, and stop. That flexibility makes state reconciliation possible, but a deterministic controller may obtain the same evidence and make the decision without a model.

We examine CREATE-like, non-idempotent operations: support tickets, GitHub issues, and spreadsheet row appends. The original studies compare **Exact Replay**, a single redispatch of the stored request, with **bounded LLM Regeneration**, a limited continuation that can read, write, or stop. A **post-review deterministic no-model baseline** reads once and dispatches the stored original CREATE only when a usable observation does not show the intended effect. Study 1A supplies the original planned controlled comparison; Study 1B bridges a model-availability transition; Study 2 provides descriptive live validation. The baseline is a separate descriptive addition.

The contributions are threefold:

- **Recovery-control semantics.** We distinguish request fidelity from effect evidence and the decision to mutate again. The paired hidden-outcome design follows prior recovery work \cite{did_it_happen}; the focus here is what each controller does after a stored state-mutating call becomes ambiguous.
- **Live state validation.** Controlled ticket studies and completed GitHub and Sheets comparisons show both duplicate-producing writes and missing required effects. GitHub demonstrates that bounded model continuation can stop while a mutation is still needed.
- **A deterministic state-aware comparison.** The post-review rule succeeds in 896/896 opportunities with zero LLM calls. With usable state observations in the tested environments, it matches or exceeds Regeneration's observed correctness, showing that these decisions did not require model reasoning.

## Recovery after an ambiguous tool call

### Two hidden execution situations

An acknowledgement is the service's reply confirming an action. Losing that reply does not imply losing the action. We distinguish two situations behind the same timeout:

- **Original action did not execute.** No intended effect exists before recovery, so completing the task requires a mutation.
- **Executed, acknowledgement lost.** The original action executed successfully, but its acknowledgement was lost. One intended effect already exists, so another unprotected create can produce a duplicate.

We later denote these execution worlds by $H_0$ and $H_1$, respectively. They are labels for hidden execution state, not statistical null and alternative hypotheses. Their frequencies in the experiment are assigned by design; we do not estimate how often either situation occurs in deployment.

For a create operation, sending identical bytes twice need not mean creating one resource. Idempotence means repeated requests have the same intended effect as one request \cite{rfc9110}. An application-level idempotency key can associate repeated deliveries with one logical operation \cite{helland_idempotence}. We study mutation paths without such a deduplication intervention. Replay is a semantic reference arm: after successful execution, another unprotected CREATE duplicates the effect by construction.

### Recovery policies

**Exact Replay** redispatches the stored original request once, preserving its URL, headers, and body bytes within that trial. It invokes no recovery model call and then terminates. Its advantage is request fidelity: it cannot change the requested content while reconsidering the task. Fidelity alone does not establish whether that request should be sent again.

**LLM Regeneration** appends the ambiguous tool result to the original conversation and invokes the same study model. The model may inspect state, issue a mutation, change arguments, or stop. At most three tool-action attempts and four model calls are permitted. Reads and writes both consume the action budget; a text-only stop consumes a model call but no tool action. Invalid in-budget tool attempts also consume an action, and an over-budget request is recorded but not executed. A recovery is budget-exhausted when the model requests another tool action after its three-action allowance has been spent; using all three permitted actions is not itself exhaustion. Original generation and final evaluator reads are outside this recovery budget.

The budget permits a compact read--write--confirm sequence while bounding loops. A high-level paginated list counts as one tool action even if it makes several HTTP requests; provider traversal limits apply separately. This cap defines the evaluated Regeneration policy.

**Deterministic no-model baseline.** Added after reviewer feedback, this fixed rule makes one decision LIST/logical read. If the observation is unusable, it stops; an unusable read is never treated as absence. If the exact intended effect is visible, it stops without writing. Otherwise, it dispatches the stored original CREATE once and stops. It makes zero LLM calls, permits at most one recovery CREATE, and has no loop or second decision read. It uses the same semantic observation interface as Regeneration, without a hidden $H_0$/$H_1$ oracle, evaluator-only evidence, an original resource ID hidden from Regeneration, or an idempotency key. A required write retains the stored original request and request identity.

Figure \ref{fig:figure1} shows the original Replay--Regeneration recovery boundary; the baseline adds a fixed controller that uses state evidence and the stored request.

\input{figures/figure1.tex}

## Experimental design

### One original action, four linked recoveries

Each original Replay--Regeneration trial begins with a task and a model-generated mutation. An original call is eligible only if it is parseable, schema-valid, and correct for the requested task. We store that original assistant message and mutation unchanged before recovery. We call the four linked evaluations derived from it a **family**: two execution situations, each evaluated under Replay and Regeneration. A family is a matched unit, not four independent task examples. The comparison starts after a correct original call; it does not measure whether an agent selects the right initial action from scratch.

Each evaluation uses an isolated copy of the logical initial state or a dedicated external trial scope. The same original semantic action and prompt history are shared across its family, while physical provider resources remain isolated. In the not-executed situation, the harness records the request but does not dispatch it. In the already-executed situation, it dispatches the original once, verifies successful execution, and withholds the acknowledgement from recovery. This construction gives known starting state for both situations instead of relying on naturally occurring timeouts with uncertain ground truth.

Both situations expose the same synthetic message: *The previous request timed out. Its outcome is unknown.* Neither the hidden situation nor the original resource identifier is supplied to the model. Replay sends the saved request; Regeneration receives the unchanged preceding conversation and this ambiguous result. Subsequent read-tool responses may reveal state. The experiment thus holds the original decision fixed while varying who controls recovery.

Study 1 uses eight ticket scenarios repeated 20 times, giving 160 families per controlled study. Each replicate has a separately scheduled original generation, but the task templates recur. The scenarios describe different support incidents; all ask for a ticket creation using the same operation and tool interface. Alternating scenario order and four balanced scheduling strata reduce simple order confounding. These are 160 repeated opportunities across eight templates, not 160 unrelated task types.

### Models, tools, and study roles

Study 1A used **DeepSeek V4 Flash (0731)** through Fireworks serverless inference, with model identifier `accounts/fireworks/models/deepseek-v4-flash-0731`. Study 1B and Study 2 used **DeepSeek V4.1 Flash** through the same inference provider, identifier `accounts/fireworks/models/deepseek-v4p1-flash`. All studies requested temperature 0.0, top-p 1.0, maximum output tokens 1024, reasoning effort none, automatic tool selection, and disabled parallel tool calls. An immutable hosted-model digest was not recorded.

The controlled studies offered `create_ticket` and `list_tickets`. External trials offered the corresponding create/list tools: `create_issue` and `list_issues` for GitHub, and `append_row` and `list_rows` for Sheets. Study 1B and Study 2 share the exact requested model ID and scalar inference settings, but provider-specific tasks, schemas, scopes, and seed schedules differ. Table \ref{tab:overview} summarizes the completed studies.

\input{tables/passb_overview.tex}

### Final external state is the endpoint

A recovery is **state-correct** when the final system contains exactly one intended effect and no unintended effects attributable to the trial. Task fields must match the requested content. Zero intended effects is a missing effect; multiple matching resources are duplicates; additional nonmatching trial resources are unintended effects. An HTTP success response or the model's completion claim is insufficient. When the required observations cannot certify final state, the outcome remains unknown and is excluded from the corresponding matched comparison, rather than assigned a zero score.

Natural-language answer quality is not scored. Latency, token use, and monetary cost are outside the endpoint. Tool and model-call counts describe recovery work but are not a cost-normalized comparison. In particular, procedural termination and state correctness can disagree: a recovery can terminate with budget exhaustion after already producing the correct state.

Controlled ticket reads expose complete trial-local state. External reads follow provider-specific contracts described below. For attribution, the harness attaches a unique trial marker to provider state and removes it from model-visible results. The marker is not exposed as a tool argument or in the task; it is provider-visible metadata, not an idempotency key, and does not suppress duplicate writes. Marker-based filtering gives the model trial-local semantic records, simplifying attribution relative to some production systems. The public artifact repository details placement, collision checks, and observation rules.

### Matched analysis and evidence status

The historical Replay--Regeneration comparison uses the shared original action as its paired unit. Table \ref{tab:results} retains correctness counts and two-sided 95% paired Newcombe method 10 intervals \cite{newcombe} for the difference, Replay minus Regeneration, in percentage points. Figure \ref{fig:figure2} displays those historical contrasts. Replay supplies a semantic reference; its deterministic already-executed failure requires no significance test. We omit Replay--Regeneration hypothesis tests from the manuscript while preserving the original statistical outputs in the evidence artifacts.

Study 1A's analysis plan was specified before collection and timestamped in repository history, without independent preregistration. Study 1B is a separate model-transition replication. Study 2 retains a secondary descriptive role, with providers reported separately. Stored whole-family bootstrap interaction intervals \cite{efron_bootstrap}, full-precision paired estimates, and post-hoc descriptive marginal intervals remain in the supplement. Scenario counts and action-path summaries are post-hoc descriptive; GitHub missing-arm alternatives are post-hoc sensitivity checks.

The no-model baseline was added post-review and independently evaluated 896 frozen opportunities: 640 ticket, 128 GitHub, and 128 valid Sheets-replication cases. It is reported descriptively, without a paired contrast, confidence interval, or significance test. Its complete 64-case GitHub $H_0$ cohort is separate from the historical 63-pair analysis.

\input{tables/passb_results.tex}

\input{figures/figure2.tex}

## Study 1A: controlled ticket experiment

### Results

Study 1A completed 160 eligible families and all 640 linked evaluations. When the original action did not execute, Replay and Regeneration were each correct in 160/160 cases.

After execution with acknowledgement loss, Regeneration was correct in 151/160 cases (94.4%); nine recoveries duplicated the ticket. Replay scored 0/160 because every redispatch created a second ticket. Table \ref{tab:results} retains the paired uncertainty intervals.

### What the recovery traces establish

In all 151 correct already-executed Regeneration cases, the model read the ticket list and stopped without another write. The nine failures wrote first and each created a duplicate. Five then read and stopped; four stopped immediately after the write. No wrong-content mutation, malformed or rejected generation, or budget exhaustion was recorded. These valid but unnecessary writes show why schema correctness alone cannot establish recovery correctness.

Post-hoc scenario inspection places the nine failures across four of the eight templates, with failure counts of one, two, two, and four. Already-executed Regeneration correctness ranged from 16/20 to 20/20 across scenarios. Four templates had no observed failures; the remaining four had 1/20, 2/20, 2/20, and 4/20 failures.

When the original action did not execute, 146/160 Regeneration recoveries read before writing; the remaining 14 wrote immediately. All were correct, and every recovery issued exactly one mutation. In the already-executed situation, the five write--read--stop paths explain the mean of 2.03 model calls rather than exactly two. The other four failed write--stop paths used the same number of calls as a successful read--stop path. Means alone therefore conceal some failures.

## Study 1B: model-transition replication

Before external validation, DeepSeek V4 Flash (0731) became unavailable through the relevant Fireworks serverless path. We selected DeepSeek V4.1 Flash and repeated the controlled experiment on 27 September 2026 before collecting Study 2 outcomes. Study 1B was a model-transition replication of the same retry question, preserving the ticket scenarios, prompt, allocation, seed schedule, and recovery rules. It is reported separately from Study 1A.

Study 1B completed 160 families and 640 evaluations. Replay and Regeneration were each correct in 160/160 not-executed cases. After execution with acknowledgement loss, Replay was correct in 0/160 and Regeneration in 160/160.

In all 160 already-executed Regeneration evaluations, DeepSeek V4.1 Flash inspected state and stopped without another mutation. In all 160 not-executed evaluations, it read before writing; 130 also read again to confirm. No Regeneration state failure or budget exhaustion was recorded. The controlled recovery pattern persisted with the model subsequently used in Study 2.

## Study 2: external validation

Study 1 deliberately makes state observation clean and complete. Study 2 asks whether the recovery distinction remains visible when mutations and observations reach actual external services. It retains DeepSeek V4.1 Flash and the same recovery bounds, using dedicated provider scopes and 64 planned families per provider. GitHub and the separate Sheets replication supply completed comparisons. A third provider attempt supplies only incomplete operational evidence.

### GitHub issue creation

The mutation created a GitHub issue with the requested title and body in a dedicated sandbox repository, using the Issues POST endpoint \cite{github_issues_api}. The read tool listed issues through a bounded census: it followed and validated pagination links, included open and closed issues, and excluded pull requests. A complete traversal could span multiple pages. The model saw semantic records attributable to its trial, together with a warning that an absent issue might still be unobserved. It did not receive a direct status-query oracle for the original request.

Final-state evaluation used separate issue censuses at recovery end and, when required, 600 seconds later. Completeness required validated traversal within the protocol's bounds; an established irreversible duplicate could terminate observation early. A successful first census alone did not certify a final success if the required later census failed.

When the original action did not execute, the historical matched results were Replay 63/63 and Regeneration 60/63: a +4.8 percentage-point difference (95% paired CI [-1.8, 13.1]). After execution with acknowledgement loss, Replay scored 0/64 through duplicates and Regeneration 64/64.

Across all 64 evaluable not-executed Regeneration cases, four ended without the required effect. In three cases, the model stopped after two reads, citing uncertainty about visibility and the risk of creating a duplicate, without attempting a mutation. The fourth attempted the correct mutation after two reads, received HTTP 504, and subsequently had a confirmed missing final effect. That dispatch's provider/runtime failure mechanism remains ambiguous; it is not a model-chosen omission. None of the four terminated because of budget exhaustion.

One Replay case could not be scored because its first required census completed but its later confirmation census did not. Its Regeneration partner was one of the three no-write failures, so that pair is excluded from the matched not-executed result. This explains 60/63 in the paired table versus 60/64 among all evaluable Regeneration cases. The public artifact repository retains the unknown result and gives simple post-hoc alternatives for its possible binary score. No imputation changes the primary matched result.

An interrupted original collection was completed by a continuation using the same saved original requests. Earlier unresolved records for untouched recoveries were replaced, not counted as additional observations; detailed collection history is in the public artifact repository. Finally, 16/64 not-executed Regeneration cases terminated with budget exhaustion but still ended state-correct. This illustrates the endpoint's separation from procedural completion rather than explaining the missing effects.

### Google Sheets row appends

The Sheets mutation appended a row to a private, isolated trial list using an `AppendCellsRequest`; the read tool retrieved the assigned bounded grid through `spreadsheets.get` \cite{sheets_append_cells,sheets_get}. Intended content occupied two columns, with a harness attribution marker in a separate column. Final evaluation checked the complete assigned 100-row range for exactly one matching append and no unintended trial rows.

The first attempt contained an acknowledgement-validation implementation bug that prevented valid construction of the executed-but-acknowledgement-lost condition. In the invalid first attempt, every already-executed construction was rejected before recovery began, so no already-executed policy behavior was observed. Its 64 not-executed successes were discarded under the predefined family-level validity rule, leaving zero behavioral comparison families. The public artifact repository documents the failed attempt.

After correcting the bug, we ran a separate fresh replication using a new spreadsheet and namespace, with newly generated originals. The invalid first attempt remains separately preserved. In 64 completed families, Replay and Regeneration were each correct in 64/64 not-executed cases. After execution with acknowledgement loss, Replay was correct in 0/64 and Regeneration in 64/64. Regeneration read state and issued no recovery mutation in all 64 already-executed cases.

### Incomplete Razorpay attempt

We also attempted external validation using Razorpay Test Mode order creation. Three separate collection attempts stopped under repeated HTTP 429 throttling after evaluating 2, 4, and 12 of 256 scheduled recoveries, respectively. The observed prefixes included duplicate effects under both policies, and Regeneration did not consistently recover correctly after the original action executed with its acknowledgement lost. Across the three stopped prefixes, the already-executed matched results were Replay versus Regeneration: 0/1 versus 0/1, 0/1 versus 0/1, and 0/3 versus 1/3, respectively. The public artifact repository retains separate prefix results and stop diagnostics.

## Deterministic no-model baseline

The rule was final-state correct in 896/896 post-review opportunities, with zero unknown outcomes and zero model calls. All 896 decision observations were usable. In all 448 $H_0$ cases, the single read showed no intended effect and the stored CREATE succeeded. In all 448 $H_1$ cases, the effect was visible and the controller stopped without another mutation. Ticket cases contributed 640/640 successes; GitHub and Sheets contributed 128/128 each. Table \ref{tab:results} gives the eight strata.

On their respective evaluable cohorts, the rule exceeded Regeneration's observed correctness in Study 1A $H_1$ (160/160 versus 151/160) and GitHub $H_0$ (64/64 versus 60/64), and matched it in the remaining strata. The GitHub comparison is descriptive across separate cohorts; the historical primary analysis remains 63 matched Replay--Regeneration pairs.

## Discussion and limitations

### State reconciliation and recovery control

Replay preserves request identity but makes no use of state evidence. Regeneration can acquire evidence and reconsider the action, yet GitHub shows that it can also stop while a required effect remains missing. Three recoveries omitted the write; a fourth attempted the correct write and received HTTP 504. The latter shows that choosing a justified mutation and achieving the final state are separate requirements.

The deterministic baseline materially changes the interpretation. With usable observations, a fixed controller matched or exceeded Regeneration's observed correctness in every tested stratum, without model calls. These recovery decisions therefore do not demonstrate a need for LLM reasoning. The useful abstraction is stored request identity, evidence about external state, and a recovery rule deciding whether another mutation is justified.

This abstraction also identifies unresolved decisions. A controller needs an observation contract strong enough to support its action: an unusable read cannot establish absence, and stopping without evidence of execution can leave the task incomplete. Server-supported deduplication, stronger receipts, or escalation are possible mechanisms for handling that uncertainty.

### Scope of the evidence

**Baseline and observation quality.** The no-model baseline is a post-review descriptive evaluation on its own cohort. Its external cases were collected separately from the historical policy arms, rather than as contemporaneous paired provider measurements. All 896 decision observations were usable; stale, incomplete, noisy, or unusable observation behavior remains untested. The policy specifies STOP on an unusable read, but this branch was not exercised. Complete local lists, isolated external scopes, and harness-owned attribution markers simplify reconciliation. The markers are hidden from the model, visible to providers, and preserve duplicate writes. Uninstrumented reconciliation, unrelated concurrent activity, and arbitrary consistency models remain outside the evaluation. GitHub's read interface warned that an absent issue might still be unobserved, a relevant condition for its three no-write failures.

**Policy and model attribution.** Regeneration bundles model reasoning, observation access, and bounded continuation. Read-first behavior was observed, not randomized. The baseline demonstrates sufficiency of one controller in these settings, without isolating which Regeneration component caused each outcome. Idempotency-key recovery and abort/escalate policies were not evaluated. The availability-driven model transition and provider changes also prevent a clean attribution of Study 1A--Study 2 differences to the model. Hosted model IDs lack immutable weight digests.

**Task scope and uncertainty.** Eight ticket templates repeated 20 times may induce dependence beyond the matched family. The retained family-level intervals and descriptive scenario counts concern this fixed catalogue. Controlled tasks and two completed external services provide limited coverage of deployment behavior; perfect observed scores do not establish zero population risk. The equally allocated hidden situations do not estimate their real-world prevalence or an unconditional policy ranking.

**Bounds and endpoints.** Regeneration's three-action, four-call budget accommodates a short read--write--confirm path; longer strategies and other caps were not tested. Final-state correctness omits answer quality, latency, token use, and monetary cost. Sixteen GitHub recoveries exhausted their budget with correct state, so procedural completion and state correctness measure different outcomes.

**Failure construction and collection.** The studies construct ambiguity around either complete successful execution or no execution. Natural failures, partial effects, and delayed execution were not sampled. GitHub retained one unknown Replay score and required interrupted-collection continuation. The first Sheets attempt was invalid; its separate valid replication supplies the reported results. Razorpay remained incomplete under throttling and supplies only operational evidence. Provenance and GitHub missing-arm sensitivity checks retain these collection limits.

## Related work

Classical remote-procedure-call work explains execution uncertainty after communication failure \cite{birrell_nelson}. HTTP idempotence and application-level operation identity address repeat delivery \cite{rfc9110,helland_idempotence}; sagas address compensation in multi-step work \cite{sagas}. ReAct supplies the reasoning--action--observation pattern \cite{react}, and $\tau$-bench evaluates agents against terminal database state across repeated trials \cite{tau_bench}. Those evaluation ideas motivate our final-state endpoint.

The closest recovery work further narrows the claim. *Verified Tool Calls* evaluates postcondition verification, verify-before-retry, and idempotency mechanisms under simulated non-atomic failures \cite{verified_tool_calls}. *Did It Happen?* places cases where the action had executed versus had not executed behind an identical timeout and varies reliability advice, status queries, and stable-key affordances \cite{did_it_happen}. Hidden-world pairing is therefore prior work, not our novelty. ACRFence studies how checkpoint-restored agents can re-synthesize requests and develops defenses against semantic rollback \cite{acrfence}; regenerated-request drift is also an established concern.

*Callability Is Not Operability*, through AFT-Bench, holds tasks and backends fixed while changing interfaces, including recovery and verification affordances \cite{aft}. Relative to the paired-outcome design already used in *Did It Happen?* \cite{did_it_happen}, this paper focuses on recovery control for stored non-idempotent CREATE calls: request identity, evidence that an effect exists, and authorization of another mutation. Live GitHub and Sheets validation extends the controlled ticket evidence, and the post-review deterministic baseline tests whether a fixed state-aware rule suffices for these decisions. The contribution is this focused semantics and validation, rather than the paired hidden-outcome design itself.

## Conclusion

Ambiguous state-mutating retries require reconciliation of external state. Replay preserves the stored request but ignores evidence that its effect already exists. Bounded Regeneration often acquires that evidence and avoids another mutation, yet GitHub shows that it can leave a required effect missing. The post-review deterministic controller succeeded in 896/896 opportunities with usable observations and zero LLM calls, showing that a simple rule sufficed in these tested settings. Recovery control should separate request identity, state evidence, and the decision authorizing another mutation.

## Reproducibility

The public repository is `https://github.com/JashRashne/retry-semantics-llm-agents`. It provides research protocols, stored result artifacts, offline analysis scripts, build instructions, and optional supplementary material with detailed provenance. Model IDs are given in Section III. Presentation uses stored outcomes and requires no live research-provider access; archived tests, retained intervals, and post-hoc summaries retain their separate evidence status. The authoritative post-review baseline summary is `research/baselines/no_model/RESULTS.md`.

## References

Bibliographic source: `research/references.bib`; retained unchanged.
