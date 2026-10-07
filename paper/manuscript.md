# Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes

## Abstract

A timeout after a non-idempotent CREATE leaves its execution outcome unknown: another write may complete the task or duplicate an existing effect. We compare Exact Replay, bounded LLM Regeneration, and a deterministic verify-before-retry reference after a stored, initially correct call. Controlled tickets and external mutations are scored against final state. Unlike simulated-service studies, the external validation executes mutations against live GitHub and Google Sheets endpoints. All model-based results use two hosted versions of one DeepSeek model family, with reasoning effort requested as none. Replay duplicates already-completed unprotected creates. In already-executed cases, Regeneration is correct in 151/160 opportunities in Study 1A, 160/160 in Study 1B, and 64/64 each on GitHub and Sheets. GitHub not-executed Regeneration is correct in 60/64 evaluable cases: three recoveries stop without attempting the required write; one attempts the correct write, receives HTTP 504, and leaves the intended effect absent. The minimal keyless deterministic reference achieves 896/896 correct outcomes on separately evaluated opportunities with zero recovery model calls. The fixed rule was sufficient where effect observations were usable, exactly matchable, and available at the decision read. Noisy, delayed, incomplete, or otherwise ambiguous observations remain outside the reference's evidence.

## Introduction

Suppose an agent sends a request to create a support ticket and receives a timeout. The response does not reveal whether the mutation never executed or succeeded with its acknowledgement lost. Redispatching the stored request preserves its content, but can create a second ticket when the first already exists. Recovery therefore turns on three questions: what request to redispatch, what effect already exists, and whether another mutation is justified.

Remote-call uncertainty and repeated delivery are established distributed-systems problems \cite{birrell_nelson,helland_idempotence}. Verification-before-retry is also established in agent recovery: a controller checks whether an intended effect exists before permitting another write \cite{verified_tool_calls,limbo}. A tool-using runtime can instead return control to the model, whose continuation may inspect state, write, or stop. This flexibility can suppress duplicates, but can also leave a needed mutation unattempted.

We examine this boundary for support-ticket creation, GitHub issue creation, and spreadsheet row appends. **Exact Replay** redispatches the stored mutation once. **Bounded LLM Regeneration** continues the conversation with access to read and write tools. The **deterministic verify-before-retry reference** makes one decision read and dispatches the stored CREATE only when a usable observation does not show the exact intended effect. The comparison begins after an initially correct call; it concerns recovery control rather than initial task planning.

Study 1A evaluates controlled tickets, Study 1B repeats the comparison across a model-availability transition, and Study 2 validates effects through live GitHub and Sheets operations. Counterfactual executed/not-executed ambiguity follows prior evaluation work \cite{did_it_happen,limbo}. The paper's role is a focused empirical comparison with a minimal deterministic reference.

The contributions are threefold:

- **Focused recovery comparison.** We compare Exact Replay with bounded LLM continuation after an ambiguous, initially correct stored CREATE under matched NE/AE conditions.
- **Live effect validation.** Unlike simulated-service studies \cite{verified_tool_calls,limbo}, we score final effects on live GitHub and Google Sheets endpoints, distinguishing duplicates, model stops without required writes, and a correct write attempt followed by HTTP 504 and a missing effect; evaluator uncertainty remains explicit.
- **Deterministic reference.** We evaluate a one-read keyless rule as a restricted form of established verification-aware recovery, observing 896/896 correct outcomes in separately evaluated cases with usable decision observations and zero recovery model calls.

## Recovery after an ambiguous tool call

### Two hidden execution situations

An acknowledgement is the service's reply confirming an action. Losing that reply does not imply losing the action. We distinguish two situations behind the same timeout:

- **NE (not-executed).** The original action did not execute. No intended effect exists before recovery, so completing the task requires a mutation.
- **AE (already-executed).** The original action executed successfully, but its acknowledgement was lost. One intended effect already exists, so another unprotected create can produce a duplicate.

These execution conditions are assigned by design; their frequencies do not estimate deployment prevalence.

For a create operation, sending identical bytes twice need not mean creating one resource. Idempotence means repeated requests have the same intended effect as one request \cite{rfc9110}. An application-level idempotency key can associate repeated deliveries with one logical operation \cite{helland_idempotence}. We study mutation paths without such a deduplication intervention. Replay is a semantic reference arm: after successful execution, another unprotected CREATE duplicates the effect by construction.

### Recovery policies

**Exact Replay** redispatches the stored original request once, preserving its URL, headers, and body bytes within that trial, then stops. It makes zero recovery model calls. This provides stored-request fidelity, but does not determine whether another mutation is justified or supply service-enforced deduplication. Replay is the semantic reference for unconditional redispatch.

**Bounded LLM Regeneration** appends the ambiguous tool result to the original conversation and invokes the same study model. The model may inspect state, issue a mutation, change arguments, or stop. At most three tool-action attempts and four model calls are permitted. Reads and writes both consume the action budget; a text-only stop consumes a model call but no tool action. Invalid in-budget tool attempts also consume an action, and an over-budget request is recorded but not executed. A recovery is budget-exhausted when the model requests another tool action after its three-action allowance has been spent; using all three permitted actions is not itself exhaustion. Original generation and final evaluator reads are outside this recovery budget.

The budget permits a compact read--write--confirm sequence while bounding loops. A high-level paginated list counts as one tool action even if it makes several HTTP requests; provider traversal limits apply separately. This cap defines the evaluated Regeneration policy.

**Deterministic verify-before-retry reference** makes one decision LIST/logical read. If the observation is unusable, it stops; an unusable read is never treated as absence. If the exact intended effect is visible, it stops without writing. Otherwise, it dispatches the stored original CREATE once and stops. It makes zero recovery model calls, permits at most one recovery CREATE, and has no loop or second decision read. It uses Regeneration's semantic observation interface, with no hidden execution-world oracle, evaluator-only evidence, original resource ID unavailable to Regeneration, or idempotency key. A dispatched mutation retains stored-request fidelity. This is a deliberately restricted instantiation of verification-before-retry \cite{verified_tool_calls}.

Figure \ref{fig:figure1} compares the three controllers at this recovery boundary, distinguishing the matched Replay--Regeneration comparison from the separately evaluated deterministic reference.

\input{figures/figure1.tex}

## Experimental design

### One original action, four linked recoveries

Each Replay--Regeneration trial begins with a task and a model-generated mutation. An original call is eligible only if it is parseable, schema-valid, and correct for the requested task. We store that assistant message and mutation unchanged before recovery. The four linked evaluations form a **family**: two execution situations, each evaluated under Replay and Regeneration. A family is the matched unit. The reference cohorts sit outside this four-evaluation comparison.

Each evaluation uses an isolated copy of the logical initial state or a dedicated external trial scope. The same original semantic action and prompt history are shared across its family, while physical provider resources remain isolated. In the not-executed situation, the harness records the request but does not dispatch it. In the already-executed situation, it dispatches the original once, verifies successful execution, and withholds the acknowledgement from recovery. This construction gives known starting state for both situations instead of relying on naturally occurring timeouts with uncertain ground truth.

Both situations expose the same synthetic message: *The previous request timed out. Its outcome is unknown.* Neither the hidden situation nor the original resource identifier is supplied to the model. Replay sends the saved request; Regeneration receives the unchanged preceding conversation and this ambiguous result. Subsequent read-tool responses may reveal state. The experiment thus holds the original decision fixed while varying who controls recovery.

Study 1 uses 160 repeated opportunities across eight ticket templates, with 20 repeats per template in each controlled study. Each replicate has a separately scheduled original generation and supplies one matched family. The templates describe different support incidents; all ask for a ticket creation using the same operation and tool interface. Alternating template order and four balanced scheduling strata reduce simple order confounding.

### Models, tools, and study roles

Study 1A used **DeepSeek V4 Flash (0731)** through Fireworks serverless inference, with model identifier `accounts/fireworks/models/deepseek-v4-flash-0731`. Study 1B and Study 2 used **DeepSeek V4.1 Flash** through the same inference provider, identifier `accounts/fireworks/models/deepseek-v4p1-flash`. All studies requested temperature 0.0, top-p 1.0, maximum output tokens 1024, reasoning effort none, automatic tool selection, and disabled parallel tool calls.

The controlled studies offered `create_ticket` and `list_tickets`. External trials offered the corresponding create/list tools: `create_issue` and `list_issues` for GitHub, and `append_row` and `list_rows` for Sheets. Study 1B and Study 2 share the exact requested model ID and scalar inference settings, but provider-specific tasks, schemas, scopes, and seed schedules differ. Table \ref{tab:overview} summarizes the completed studies.

\input{tables/passb_overview.tex}

### Final external state is the endpoint

A recovery is **state-correct** when the final system contains exactly one intended effect and no unintended effects attributable to the trial. Task fields must match the requested content. Zero intended effects is a missing effect; multiple matching resources are duplicates; additional nonmatching trial resources are unintended effects. An HTTP success response or the model's completion claim is insufficient. When the required observations cannot certify final state, the outcome remains unknown and is excluded from the corresponding matched comparison, rather than assigned a zero score.

Tool and model-call counts describe recovery work. Procedural termination and state correctness can disagree: a recovery can terminate with budget exhaustion after already producing the correct state.

Controlled ticket reads expose complete trial-local state. External reads follow the provider-specific contracts described below. For attribution, the harness attaches a unique trial marker to provider state and removes it from model-visible results. The marker is not exposed as a tool argument or in the task; it is provider-visible metadata, not an idempotency key, and does not suppress duplicate writes. Marker-based filtering produces trial-local semantic records. The public artifact repository details placement, collision checks, and observation rules.

### Results presentation

Table \ref{tab:results} reports observed final-state correctness counts. Replay's AE failure follows from unprotected CREATE semantics. Figure \ref{fig:figure2} shows recovery paths that distinguish duplicate writes, stops without required writes, and a transport-failed write attempt.

### Evidence status

Replay--Regeneration comparisons use matched original-action families. Study 1A's analysis plan was specified before collection and timestamped in repository history, without independent preregistration; Study 1B is a model-transition replication. Study 2 provides secondary external validation, with providers reported separately. The deterministic verify-before-retry reference uses separate cohorts, called **reference cohorts** below. Their opportunities were fixed before reference collection and were not selected based on its outcomes; this is the meaning of **frozen** in the tables and figures. Reference results are descriptive, without a paired contrast, confidence interval, or significance test. Scenario and action-path summaries are descriptive, and GitHub missing-arm alternatives are post-hoc sensitivity checks. Existing statistical outputs remain in supplementary evidence: full-precision paired Newcombe method 10 intervals \cite{newcombe}, whole-family bootstrap interaction intervals \cite{efron_bootstrap}, post-hoc marginal intervals, and archived significance tests. The invalid first Sheets collection contributes no behavioral comparison; incomplete Razorpay collections supply operational evidence only.

\input{tables/passb_results.tex}

\input{figures/figure2.tex}

## Study 1A: controlled ticket experiment

### Results

Study 1A completed 160 eligible families and all 640 linked evaluations. When the original action did not execute, Replay and Regeneration were each correct in 160/160 cases.

After execution with acknowledgement loss, Regeneration was correct in 151/160 cases (94.4%); nine recoveries duplicated the ticket. Replay scored 0/160 because every redispatch created a second ticket.

### What the recovery traces establish

In all 151 correct already-executed Regeneration cases, the model read the ticket list and stopped without another write. The nine failures wrote first and each created a duplicate. Five then read and stopped; four stopped immediately after the write. No wrong-content mutation, malformed or rejected generation, or budget exhaustion was recorded. These valid but unnecessary writes show why schema correctness alone cannot establish recovery correctness.

Scenario inspection places the nine failures across four of the eight templates, with failure counts of one, two, two, and four. Already-executed Regeneration correctness ranged from 16/20 to 20/20 across scenarios. Four templates had no observed failures; the remaining four had 1/20, 2/20, 2/20, and 4/20 failures.

When the original action did not execute, 146/160 Regeneration recoveries read before writing; the remaining 14 wrote immediately. All were correct, and every recovery issued exactly one mutation. In the already-executed situation, the five write--read--stop paths explain the mean of 2.03 model calls rather than exactly two. The other four failed write--stop paths used the same number of calls as a successful read--stop path. Means alone therefore conceal some failures.

## Study 1B: model-transition replication

Before external validation, DeepSeek V4 Flash (0731) became unavailable through the relevant Fireworks serverless path. We selected DeepSeek V4.1 Flash and repeated the controlled experiment on 27 September 2026 before collecting Study 2 outcomes. Study 1B was a model-transition replication of the same retry question, preserving the ticket scenarios, prompt, allocation, seed schedule, and recovery rules. It is reported separately from Study 1A.

Study 1B completed 160 families and 640 evaluations. Replay and Regeneration were each correct in 160/160 not-executed cases. After execution with acknowledgement loss, Replay was correct in 0/160 and Regeneration in 160/160.

In all 160 already-executed Regeneration evaluations, DeepSeek V4.1 Flash inspected state and stopped without another mutation. In all 160 not-executed evaluations, it read before writing; 130 also read again to confirm. No Regeneration state failure or budget exhaustion was recorded. The controlled recovery pattern persisted with the model subsequently used in Study 2.

## Study 2: external validation

Study 1 deliberately makes state observation clean and complete. Study 2 asks whether the recovery distinction remains visible when mutations and observations reach actual external services. It retains DeepSeek V4.1 Flash and the same recovery bounds, using dedicated provider scopes and 64 planned families per provider. GitHub and the separate Sheets replication supply completed comparisons. A third external provider attempt, Razorpay, remained incomplete under sustained throttling and is reported only as operational evidence in the supplement.

### GitHub issue creation

The mutation created a GitHub issue with the requested title and body in a dedicated sandbox repository, using the Issues POST endpoint \cite{github_issues_api}. The read tool listed issues through a bounded census: it followed and validated pagination links, included open and closed issues, and excluded pull requests. A complete traversal could span multiple pages. The model saw semantic records attributable to its trial, together with a warning that an absent issue might still be unobserved. It did not receive a direct status-query oracle for the original request.

Final-state evaluation used separate issue censuses at recovery end and, when required, 600 seconds later. Completeness required validated traversal within the protocol's bounds; an established irreversible duplicate could terminate observation early. A successful first census alone did not certify a final success if the required later census failed.

Across 63 matched NE pairs, Replay was correct in 63/63 cases and Regeneration in 60/63. In AE cases, Replay scored 0/64 through duplicates and Regeneration 64/64.

Across all 64 evaluable NE Regeneration arms, correctness was 60/64. Three recoveries (3/64) stopped after two reads, citing visibility uncertainty and duplicate risk, without attempting the required write. One recovery (1/64) attempted the correct mutation after two reads, received HTTP 504, and had no intended effect at final evaluation. The latter is an endpoint failure with an unresolved provider/runtime mechanism, not a model decision to omit the mutation. None of these four recoveries terminated because of budget exhaustion.

One NE Replay outcome remained unknown because the required later confirmation census failed. Its Regeneration partner was one of the three no-write failures, so the pair is excluded from the matched result. This explains 60/63 in Table \ref{tab:results} versus 60/64 among all evaluable NE Regeneration arms; the unknown Replay outcome and sensitivity alternatives remain in supplementary evidence.

The continuation retained cases whose recovery had begun and completed only untouched opportunities; it did not replace entered cases or add independent observations. Separately, 16/64 NE Regeneration cases terminated with budget exhaustion but still ended state-correct; this procedural outcome does not explain the missing effects.

### Google Sheets row appends

The Sheets mutation appended a row to a private, isolated trial list using an `AppendCellsRequest`; the read tool retrieved the assigned bounded grid through `spreadsheets.get` \cite{sheets_append_cells,sheets_get}. Intended content occupied two columns, with a harness attribution marker in a separate column. Final evaluation checked the complete assigned 100-row range for exactly one matching append and no unintended trial rows.

The first collection was invalid because of an acknowledgement-validation construction bug; zero behavioral comparison families were retained. Its provenance remains in the supplement.

After correction, a fresh replication completed 64 families. Replay and Regeneration were each correct in 64/64 NE cases. In AE cases, Replay was correct in 0/64 and Regeneration in 64/64. Regeneration read state and issued no recovery mutation in all 64 AE cases.

## Deterministic verify-before-retry reference

Evaluated separately from the model arms, the fixed rule was final-state correct in 896/896 reference opportunities, with zero unknown outcomes and zero recovery model calls. All 896 decision observations were usable. In all 448 NE cases, the single read showed no intended effect and the stored CREATE succeeded. In all 448 AE cases, the effect was visible and the controller stopped without another mutation. Tickets contributed 640/640 successes; GitHub and Sheets contributed 128/128 each. Each execution condition scored 160/160 in each ticket study and 64/64 on each live service. Table \ref{tab:results} gives the eight strata.

The observed recovery path was one read followed by either a stored-request dispatch or a stop without writing. Final-state evaluation, rather than the controller's termination, certified these outcomes.

## Discussion and limitations

### State reconciliation and recovery control

Stored-request fidelity tells a controller what to redispatch; effect evidence helps determine whether another mutation is justified. Exact Replay retains the request but does not consult state. Regeneration often inspected state and avoided a duplicate, yet three GitHub not-executed recoveries stopped without attempting the required write. A fourth attempted the correct write, received HTTP 504, and left the intended effect absent. A justified write attempt can still fail to produce its effect.

The fixed rule was sufficient across all 896 reference opportunities where the decision read resolved the intended effect, without recovery model calls. These descriptive results neither isolate the contribution of reasoning within Regeneration nor establish a general ranking of recovery policies. The rule dispatches once and stops, so its successful writes do not establish resilience to the same HTTP 504 failure.

The unresolved boundary is evidence that cannot settle the recovery decision. An unusable read cannot establish absence; even an accurate read of current state cannot exclude a later commit by an in-flight original request \cite{limbo}. Stopping can leave required work incomplete, while redispatch can duplicate it. Stable operation keys, queryable outcomes with suitable execution guarantees, or escalation require stronger contracts than the reference evaluated here.

### Scope of the evidence

**Observation quality.** Decision reads used complete local lists and exact semantic matching. All reference reads were usable; stale, noisy, incomplete, delayed, or unusable observations and STOP-on-unusable were untested.

**Observation environment.** Isolated provider scopes and attribution markers visible to providers but hidden from the model simplified trial-local reconciliation. GitHub warned that absent issues might be unobserved, contextualizing its three no-write stops. Unmarked reconciliation and unrelated concurrent activity remain untested.

**Reference collection.** External reference cohorts were collected separately from Replay and Regeneration, without a contemporaneous paired deterministic control.

**Policy and model scope.** The studies used two hosted versions of one DeepSeek family, reasoning effort requested as none, and no recorded immutable weight digest. Regeneration combines reasoning, observation access, and bounded continuation; read-first behavior was observed, not randomized. Model availability and provider changes confound between-study attribution to the model. Idempotency keys, abort/escalate policies, longer continuations, and other recovery budgets were untested.

**Task coverage and dependence.** Eight ticket templates repeated 20 times yield 160 opportunities, not 160 independent task types. Template dependence remains beyond the matched family, and family-level intervals concern this fixed catalogue. Completed live validation is limited to GitHub and Sheets. Perfect observed scores do not establish zero population risk, and equally allocated execution conditions do not estimate deployment prevalence.

**Failure and endpoint scope.** Ambiguity was constructed around either complete successful execution or no execution; natural failure rates, late commits, delayed execution, and partial effects were not sampled. Final-state correctness measures neither latency, cost, nor natural-language answer quality, and does not provide an execution ledger of transient effects. A correct recovery action can still fail to produce the effect, as the HTTP 504 case demonstrates. GitHub continuation and its unknown Replay outcome preserve collection limits described above.

## Related work

Classical remote-procedure-call work describes execution uncertainty after communication failure \cite{birrell_nelson}. HTTP idempotence distinguishes repeatable effects from request fidelity, and application-level operation identity can support deduplication \cite{rfc9110,helland_idempotence}. Sagas address compensation in multi-step work \cite{sagas}. ReAct supplies the reasoning--action--observation pattern \cite{react}; $\tau$-bench evaluates tool-using agents against terminal database state across repeated trials \cite{tau_bench}.

Mansoor et al.'s *Verified Tool Calls* combines task-specific postcondition checks, verify-before-retry logic, and stable idempotency keys under simulated non-atomic failures \cite{verified_tool_calls}. Its verifier distinguishes satisfied, unsatisfied, and inconclusive state; keyless verification leaves a race window. Our deterministic reference is a restricted keyless instantiation of this recovery principle, rather than their complete wrapper. *Did It Happen?* places executed and not-executed outcomes behind an identical timeout and varies reliability advice, status queries, and stable-key affordances \cite{did_it_happen}. Counterfactual hidden-world pairing follows that prior design.

Li's closely related study, *Where Does Exactly-Once Live?*, introduces Limbo across a broader model, harness, fault, and tool-contract space \cite{limbo}. It includes counterfactual ambiguity, a verify-before-retry baseline, late commits, redelivery, and a keys-everywhere contract intervention. Limbo uses simulated services; our GitHub and Sheets runs use live endpoints, with provider pagination and an observed HTTP 504, but at much smaller scale: 64 families per provider and one model family. Its results and late-commit proposition delimit verification: without a known bound on in-flight execution, a keyless observation-based policy cannot guarantee both bounded completion and exactly-once effects. Our constructed execution conditions cover a narrower observation setting.

Atomix provides broader transactional settlement semantics \cite{atomix}. Its runtime records read and effect scopes, seals transaction footprints, and uses per-resource progress frontiers to permit settlement. Bufferable effects are deferred, reversible effects can be compensated, and irreversible effects remain gated until commit. This composition addresses faults, contention, and speculation subject to adapter and progress contracts. Our controllers address recovery after a single ambiguous CREATE, without providing transactional settlement.

ACRFence examines request re-synthesis after checkpoint restoration and defenses against semantic rollback \cite{acrfence}. *Callability Is Not Operability*, through AFT-Bench, holds tasks and backends fixed while changing interfaces, including recovery and verification affordances \cite{aft}. These works establish the importance of request fidelity and available evidence. Our narrower empirical role is to compare stored-request replay with bounded continuation, validate final effects on tickets and live GitHub/Sheets operations, and evaluate the sufficiency of a minimal keyless reference under usable observations.

## Conclusion

After an ambiguous mutation, preserving the original request cannot determine whether another write is justified. Exact Replay cannot consult effect evidence; bounded model continuation often reconciles state correctly but can also stop without a needed mutation. With usable, exactly matchable observations, the deterministic verify-before-retry rule was sufficient in the reference cohorts: 896/896 correct outcomes with zero recovery model calls. Noisy, delayed, incomplete, or otherwise ambiguous observations remain the unresolved boundary for this reference.

## Reproducibility

The public repository is `https://github.com/JashRashne/retry-semantics-llm-agents`. It provides research protocols, stored result artifacts, offline analysis scripts, build instructions, and optional supplementary material with detailed provenance. Model IDs are given in Section III. Presentation uses stored outcomes and requires no live research-provider access. Deterministic-reference results, audit summaries, and archive hashes are in `research/baselines/no_model/RESULTS.md`.

\section*{Acknowledgment}

Generative AI tools were used during the preparation of this work. OpenAI ChatGPT and Anthropic Claude were used for independent manuscript review, language and style editing, and consistency checks. OpenAI Codex was used for code assistance, including test development and paper–repository consistency checks. The author designed and executed the experiments, verified the reported results and source artifacts, reviewed all AI-assisted outputs, and takes full responsibility for the content of the paper.

## References

Bibliographic source: `research/references.bib`.
