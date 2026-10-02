# Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes

## Abstract

An AI agent sends a state-changing tool request. The request times out, leaving the agent unable to tell whether nothing happened or the action succeeded and only its acknowledgement was lost. We compare Exact Replay, which sends the exact stored original request again, with LLM Regeneration, which returns the ambiguous result to the model and permits bounded continuation, including state inspection. Each matched comparison shares one original generated mutation and evaluates both hidden execution situations using final-state correctness. In Study 1A, a controlled ticket experiment with DeepSeek V4 Flash (0731), both policies were correct in 160/160 cases when the original action did not execute. When it executed but its acknowledgement was lost, Replay was correct in 0/160 and Regeneration in 151/160; nine write-first recoveries created duplicates. After that model became unavailable through Fireworks serverless inference, Study 1B repeated the experiment with DeepSeek V4.1 Flash: Regeneration inspected state and avoided another write in all 160 already-executed cases. GitHub and a separate Google Sheets replication each showed 64/64 correct already-executed Regeneration recoveries, but when the original action did not execute, four GitHub Regeneration recoveries left required effects missing, including one HTTP 504 write attempt. A third provider attempt was incomplete under repeated throttling and is reported only as mixed operational evidence. These results show why recovery must distinguish request identity from evidence about whether its effect already exists.

## Introduction

Suppose an agent is asked to create a customer-support issue. It sends a tool request, waits, and receives a timeout. Creating the issue again may finish the task if the first request never reached the service. It may create a duplicate if the service already created the issue and only the reply disappeared. The error message alone does not distinguish these situations. A successful recovery must resolve what happened to the effect, rather than merely obtain a successful response on another attempt.

Remote-call uncertainty and repeated delivery are established distributed-systems problems \cite{birrell_nelson,helland_idempotence}. Tool-using language models introduce a particular recovery boundary. A runtime can resend the stored request without consulting the model, or give the model the error and let it decide what to do next. The second choice can include reading the service, changing the request, or stopping. These choices matter because an agent's tool calls can create persistent resources, and a plausible final answer does not undo a duplicate or supply a missing effect.

We study two concrete policies: **Exact Replay** and **bounded LLM Regeneration**. Replay preserves the original request exactly and performs one redispatch. Regeneration returns control to the model for a limited sequence of reads, writes, and a possible textual stop. We ask how their final-state outcomes differ when the original action either did not execute or executed successfully with its acknowledgement lost. The comparison concerns CREATE-like, non-idempotent operations: support tickets, GitHub issues, and spreadsheet row appends. It does not establish a ranking for arbitrary state changes or for services with effective server-side deduplication.

The research proceeded in three steps. Study 1A established the contrast in a controlled ticket environment. When its hosted model became unavailable, Study 1B repeated that environment with the model chosen for the external study. Study 2 then tested the distinction against actual provider APIs, where observation and transport could themselves fail. We keep these studies separate: the first supplies the confirmatory comparison, the second bridges a model transition, and the external results provide descriptive validation.

Three findings organize the paper. First, the policies expose different failure modes after the same ambiguous observation: another delivery can duplicate an existing effect, whereas model continuation can leave a needed effect missing. Second, state-aware continuation avoided already-completed writes in the observed successful recoveries, but this behavior was neither forced nor guaranteed. Third, the central controlled pattern persisted across the model transition and appeared in the completed GitHub and Google Sheets validations, with qualifications about missing state, implementation validity, and bounded recovery.

## Recovery after an ambiguous tool call

### Two hidden execution situations

An acknowledgement is the service's reply confirming an action. Losing that reply does not imply losing the action. We distinguish two situations behind the same timeout:

- **Original action did not execute.** No intended effect exists before recovery, so completing the task requires a mutation.
- **Executed, acknowledgement lost.** The original action executed successfully, but its acknowledgement was lost. One intended effect already exists, so another unprotected create can produce a duplicate.

We later denote these execution worlds by $H_0$ and $H_1$, respectively. They are labels for hidden execution state, not statistical null and alternative hypotheses. Their frequencies in the experiment are assigned by design; we do not estimate how often either situation occurs in deployment.

For a create operation, sending identical bytes twice need not mean creating one resource. Idempotence means repeated requests have the same intended effect as one request \cite{rfc9110}. An application-level idempotency key can associate repeated deliveries with one logical operation \cite{helland_idempotence}. We study mutation paths without such a deduplication intervention. Thus Replay's risk after successful original execution is expected from the operation's semantics; its zero correctness in that situation is not evidence of a surprising defect in the replay implementation.

### Exact Replay and bounded LLM Regeneration

**Exact Replay** redispatches the stored original request once, preserving its URL, headers, and body bytes within that trial. It invokes no recovery model call and then terminates. Its advantage is request fidelity: it cannot change the requested content while reconsidering the task. Fidelity alone does not establish whether that request should be sent again.

**LLM Regeneration** appends the ambiguous tool result to the original conversation and invokes the same study model. The model may inspect state, issue a mutation, change arguments, or stop. At most three tool-action attempts and four model calls are permitted. Reads and writes both consume the action budget; a text-only stop consumes a model call but no tool action. Invalid in-budget tool attempts also consume an action, and an over-budget request is recorded but not executed. A recovery is budget-exhausted when the model requests another tool action after its three-action allowance has been spent; using all three permitted actions is not itself exhaustion. Original generation and final evaluator reads are outside this recovery budget.

The budget permits a compact read--write--confirm sequence while bounding loops. A high-level paginated list counts as one tool action even if it makes several HTTP requests; provider traversal limits apply separately. This cap is part of the policy evaluated here, not an estimate of the best recovery budget.

Regeneration is a **bundled policy**: it combines model reasoning, read-tool access, bounded multi-step continuation, and the ambiguous-outcome message. Replay receives none of those additional decision steps. The contrast therefore estimates the behavior of the bounded LLM Regeneration policy studied here, rather than isolating reasoning, observation access, or an intrinsic advantage of LLMs. Figure \ref{fig:figure1} illustrates the recovery boundary.

\input{figures/figure1.tex}

## Experimental design

### One original action, four linked recoveries

Each trial begins with a task and a model-generated mutation. An original call is eligible only if it is parseable, schema-valid, and correct for the requested task. We store that original assistant message and mutation unchanged before recovery. We call the four linked evaluations derived from it a **family**: two execution situations, each evaluated under both policies. A family is a matched unit, not four independent task examples. The comparison starts after a correct original call; it does not measure whether an agent selects the right initial action from scratch.

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

For each execution situation we report both policies' correctness counts and the paired difference, defined as Replay minus Regeneration in percentage points. Positive differences favor Replay's observed state correctness; negative differences favor Regeneration's. The paired unit is the shared original action. Table \ref{tab:results} reports the completed-study counts and two-sided 95% paired Newcombe method 10 intervals \cite{newcombe}; Figure \ref{fig:figure2} emphasizes how the contrasts change across the two hidden situations.

Study 1A retains its prespecified exact paired McNemar tests \cite{mcnemar}, with Holm adjustment across the two execution situations \cite{holm}. Its statistical plan was specified before collection. The plan was timestamped in repository history rather than independently preregistered. Study 1B is a separate model-transition replication. Study 2 was designed after Study 1A and retains a secondary descriptive role: we do not pool providers, turn external p-values into confirmatory decisions, or infer a deployment-wide success rate from equally allocated execution situations.

The prespecified interaction compares the paired policy differences between situations. For Study 1A, the prespecified interaction was -94.375 percentage points (95% whole-family bootstrap CI [-97.5, -90.625]). The whole-family bootstrap for this interaction \cite{efron_bootstrap} is retained in the public artifact repository, along with Study 1A's exact paired-test outputs and full-precision estimates. Scenario counts and action-path summaries recovered after collection are labeled post-hoc descriptive; the GitHub missing-arm alternatives are post-hoc sensitivity checks. Marginal intervals for perfect observed scores are also descriptive and do not replace paired intervals. We preserve the original procedures rather than add a cluster adjustment based on only eight fixed task templates.

\input{tables/passb_results.tex}

\input{figures/figure2.tex}

## Study 1A: controlled ticket experiment

### Results

Study 1A completed 160 eligible families and all 640 linked evaluations. When the original action did not execute, Replay and Regeneration were each correct in 160/160 cases. The paired difference was 0.0 percentage points (95% CI [-2.3, 2.3]; Holm-adjusted $p=1$). This observed agreement is not a formal equivalence result.

When the original action executed and its acknowledgement was lost, Replay was correct in 0/160 cases and Regeneration in 151/160 (94.4%). The paired difference was -94.4 percentage points (95% CI [-97.0, -89.1]; Holm-adjusted $p<0.001$). Replay created a second matching ticket in every such case, as expected when an unprotected create is sent again. The substantive behavioral question is whether Regeneration recognizes an existing effect and whether it reliably supplies an absent one.

### What the recovery traces establish

In all 151 correct already-executed Regeneration cases, the model read the ticket list and stopped without another write. The nine failures wrote first and each created a duplicate. Five then read and stopped; four stopped immediately after the write. No wrong-content mutation, malformed or rejected generation, or budget exhaustion was recorded. These valid but unnecessary writes show why schema correctness alone cannot establish recovery correctness.

Post-hoc scenario inspection places the nine failures across four of the eight templates, with failure counts of one, two, two, and four. Already-executed Regeneration correctness ranged from 16/20 to 20/20 across scenarios. This reveals scenario-level heterogeneity within the tested catalogue: four templates had no observed failures, while the remaining four had 1/20, 2/20, 2/20, and 4/20 failures; this does not support generalization to an unrestricted task population.

When the original action did not execute, 146/160 Regeneration recoveries read before writing; the remaining 14 wrote immediately. All were correct, and every recovery issued exactly one mutation. In the already-executed situation, the five write--read--stop paths explain the mean of 2.03 model calls rather than exactly two. The other four failed write--stop paths used the same number of calls as a successful read--stop path. Means alone therefore conceal some failures. The trace association between reading first and correctness is empirical; observing state was not randomized, and no universal observation-before-write rule follows.

## Study 1B: model-transition replication

Before external validation, DeepSeek V4 Flash (0731) became unavailable through the relevant Fireworks serverless path. We selected DeepSeek V4.1 Flash and repeated the controlled experiment on 27 September 2026 before collecting Study 2 outcomes. Study 1B was a model-transition replication of the same retry question, preserving the ticket scenarios, prompt, allocation, seed schedule, and recovery rules. It does not replace Study 1A or enlarge its primary sample.

Study 1B completed 160 families and 640 evaluations. When the original action did not execute, both policies were correct in 160/160 cases (paired difference 0.0 percentage points, 95% CI [-2.3, 2.3]). When the original action executed and its acknowledgement was lost, Replay was correct in 0/160 and Regeneration in 160/160 (difference -100.0 percentage points, 95% CI [-100.0, -96.7]).

In all 160 already-executed Regeneration evaluations, DeepSeek V4.1 Flash inspected state and stopped without another mutation. In all 160 not-executed evaluations, it read before writing; 130 also read again to confirm. No Regeneration state failure or budget exhaustion was recorded. The replication establishes that the controlled distinction remained visible with the model subsequently used in Study 2. It does not isolate why its behavior differed from Study 1A, establish model superiority, or remove differences between controlled and external observation.

## Study 2: external validation

Study 1 deliberately makes state observation clean and complete. Study 2 asks whether the recovery distinction remains visible when mutations and observations reach actual external services. It retains DeepSeek V4.1 Flash and the same recovery bounds, using dedicated provider scopes and 64 planned families per provider. GitHub and the separate Sheets replication supply completed comparisons. A third provider attempt supplies only incomplete operational evidence.

### GitHub issue creation

The mutation created a GitHub issue with the requested title and body in a dedicated sandbox repository, using the Issues POST endpoint \cite{github_issues_api}. The read tool listed issues through a bounded census: it followed and validated pagination links, included open and closed issues, and excluded pull requests. A complete traversal could span multiple pages. The model saw semantic records attributable to its trial, together with a warning that an absent issue might still be unobserved. It did not receive a direct status-query oracle for the original request.

Final-state evaluation used separate issue censuses at recovery end and, when required, 600 seconds later. Completeness required validated traversal within the protocol's bounds; an established irreversible duplicate could terminate observation early. A successful first census alone did not certify a final success if the required later census failed.

When the original action did not execute, the matched results were Replay 63/63 and Regeneration 60/63: a +4.8 percentage-point difference (95% paired CI [-1.8, 13.1]). When it executed and its acknowledgement was lost, Replay was correct in 0/64 and Regeneration in 64/64 (difference -100.0, 95% CI [-100.0, -92.0]). All 64 already-executed Replay failures were duplicates. These descriptive results preserve the distinction between avoiding another completed mutation and supplying one that remains needed.

Across all 64 evaluable not-executed Regeneration cases, four ended without the required effect. In three cases, the model stopped after two reads, citing uncertainty about visibility and the risk of creating a duplicate, without attempting a mutation. The fourth attempted the correct mutation after two reads, received HTTP 504, and subsequently had a confirmed missing final effect. That dispatch's provider/runtime failure mechanism remains ambiguous; it is not a model-chosen omission. None of the four terminated because of budget exhaustion.

One Replay case could not be scored because its first required census completed but its later confirmation census did not. Its Regeneration partner was one of the three no-write failures, so that pair is excluded from the matched not-executed result. This explains 60/63 in the paired table versus 60/64 among all evaluable Regeneration cases. The public artifact repository retains the unknown result and gives simple post-hoc alternatives for its possible binary score. No imputation changes the primary matched result.

An interrupted original collection was completed by a continuation using the same saved original requests. Earlier unresolved records for untouched recoveries were replaced, not counted as additional observations; detailed collection history is in the public artifact repository. Finally, 16/64 not-executed Regeneration cases terminated with budget exhaustion but still ended state-correct. This illustrates the endpoint's separation from procedural completion rather than explaining the missing effects.

### Google Sheets row appends

The Sheets mutation appended a row to a private, isolated trial list using an `AppendCellsRequest`; the read tool retrieved the assigned bounded grid through `spreadsheets.get` \cite{sheets_append_cells,sheets_get}. Intended content occupied two columns, with a harness attribution marker in a separate column. Final evaluation checked the complete assigned 100-row range for exactly one matching append and no unintended trial rows.

The first attempt contained an acknowledgement-validation implementation bug that prevented valid construction of the executed-but-acknowledgement-lost condition. In the invalid first attempt, every already-executed construction was rejected before recovery began, so no already-executed policy behavior was observed. Its 64 not-executed successes were discarded under the predefined family-level validity rule, leaving zero behavioral comparison families. The public artifact repository documents the failed attempt.

After correcting the bug, we ran a separate fresh replication using a new spreadsheet and namespace, with newly generated originals. This separate replication after the implementation fix does not retroactively replace the first attempt. In its 64 completed families, both policies were correct in 64/64 cases when the original append did not execute (difference 0.0 percentage points, 95% CI [-5.7, 5.7]). When it executed and its acknowledgement was lost, Replay was correct in 0/64 and Regeneration in 64/64 (difference -100.0, 95% CI [-100.0, -92.0]). Regeneration read state and issued no recovery mutation in all 64 already-executed cases.

### Incomplete Razorpay attempt

We also attempted external validation using Razorpay Test Mode order creation. Three separate collection attempts stopped under repeated HTTP 429 throttling after evaluating 2, 4, and 12 of 256 scheduled recoveries, respectively. The observed prefixes included duplicate effects under both policies, and Regeneration did not consistently recover correctly after the original action executed with its acknowledgement lost. Across the three stopped prefixes, the already-executed matched results were Replay versus Regeneration: 0/1 versus 0/1, 0/1 versus 0/1, and 0/3 versus 1/3, respectively. These incomplete, mixed results support no provider-level effectiveness inference. The public artifact repository retains separate prefix results and stop diagnostics.

## Discussion and limitations

### Different semantics, different failure modes

Replay answers a request-fidelity question: *send exactly what was sent before*. Regeneration answers a decision question: *given this uncertain outcome, what should happen next?* In the studied non-idempotent creates, request fidelity supplied the intended effect when it was absent but duplicated it when it existed. The bounded Regeneration policy frequently reconciled state and avoided another write, yet GitHub illustrated a possible converse failure mode: uncertainty about visibility could lead to stopping while a write remained necessary. Its HTTP 504 case also shows that even a chosen correct write need not produce a correct external state.

These observations support an explicit recovery contract. A runtime should distinguish request identity, evidence of execution, and the task's final-state requirement. When absence cannot be established, a read alone does not justify redispatch; when execution cannot be established, stopping alone does not complete the task. Server-supported deduplication, stronger receipts, or escalation may address that uncertainty. We have not evaluated those alternatives as recovery policies, so the practical lesson is to make guarantees explicit rather than adopt Regeneration as a default winner.

### Scope of the evidence

**Policy bundle and baselines.** We did not compare deterministic read-before-retry, idempotency-key recovery, or abort/escalate policies. Additional reads and model decisions are part of Regeneration's treatment. The study therefore cannot attribute the contrast solely to reasoning or show that a model is needed to obtain duplicate avoidance. Replay's already-executed result is partly determined by the non-idempotent create construction.

**Observation and instrumentation.** Study 1's complete local lists are cleaner than many production observations. The external scopes and harness-owned, model-hidden but provider-visible markers simplify attribution and read filtering. They preserve duplicates but do not measure uninstrumented reconciliation, unrelated concurrent activity, or arbitrary provider consistency models. Observation-before-write was an observed action pattern, not a guarantee of correctness. The three GitHub no-write failures occurred under an observation interface that explicitly warned the model that an absent issue might still be unobserved; their stopping behavior should therefore be interpreted as specific to this interface and warning rather than as a general property of LLM Regeneration.

**Tasks and models.** Eight templates repeated 20 times may create dependence beyond the matched family, limiting scenario-level generalization. We retain the prespecified family analysis and disclose scenario counts rather than claim a broad task sample or apply an ad hoc eight-cluster test. The model-transition replication supplies a bridge, but Study 1A and Study 2 still differ in model and environment; the design does not perfectly isolate model and provider effects. Hosted model IDs also lack immutable weight digests. Perfect observed scores do not imply zero population risk.

**Bounds and measurement.** Three tool actions and four model calls accommodate a short read--write--confirm path but may truncate other strategies. We did not optimize that cap or evaluate unrestricted recovery. State correctness omits natural-language answer quality, latency, token cost, and monetary cost. The GitHub cases that terminated with budget exhaustion despite correct state illustrate why those endpoints should not be conflated. We did not isolate why budget exhaustion was more frequent in the GitHub not-executed condition than in the controlled studies or Google Sheets.

**Construction and collection.** We construct ambiguity around a successful complete action or no execution, rather than sample natural failures, partial effects, or delayed execution. The real-world prevalence of either hidden situation is unknown, so no unconditional ranking follows. GitHub's one unknown score and interrupted collection, Sheets' invalid first attempt, and Razorpay's throttled prefixes limit external inference. Detailed provenance and the deterministic GitHub sensitivity checks support transparency without replacing those limits.

## Related work

Classical remote-procedure-call work explains execution uncertainty after communication failure \cite{birrell_nelson}. HTTP idempotence and application-level operation identity address repeat delivery \cite{rfc9110,helland_idempotence}; sagas address compensation in multi-step work \cite{sagas}. We do not propose these principles. ReAct supplies the reasoning--action--observation pattern \cite{react}, and $\tau$-bench evaluates agents against terminal database state across repeated trials \cite{tau_bench}. Those evaluation ideas motivate our state endpoint without determining this retry-policy contrast.

The closest recovery work further narrows the claim. *Verified Tool Calls* evaluates postcondition verification, verify-before-retry, and idempotency mechanisms under simulated non-atomic failures \cite{verified_tool_calls}. *Did It Happen?* places cases where the action had executed versus had not executed behind an identical timeout and varies reliability advice, status queries, and stable-key affordances \cite{did_it_happen}. Hidden-world pairing is therefore prior work, not our novelty. ACRFence studies how checkpoint-restored agents can re-synthesize requests and develops defenses against semantic rollback \cite{acrfence}; regenerated-request drift is also an established concern.

*Callability Is Not Operability*, through AFT-Bench, holds tasks and backends fixed while changing interfaces, including recovery and verification affordances \cite{aft}. Its interface intervention differs from our assignment of control after a stored original mutation. Our narrower contribution is the direct matched comparison between exact stored-request redispatch and bounded model continuation after the same original action and ambiguous observation, followed by external state evidence under provider-specific observation contracts. We do not claim priority for ambiguity, verification, idempotency, or model request drift.

## Conclusion

Exact Replay and bounded LLM Regeneration implement different recovery semantics. In the controlled studies and completed external comparisons, Replay duplicated already-completed non-idempotent creates, while Regeneration usually inspected state and avoided another mutation. GitHub also showed that bounded continuation could leave a still-required effect missing. The systems lesson is conditional: preserve the original request, establish what is known about its effect, and define when another mutation is justified. Neither identical bytes nor model reconsideration alone supplies a general recovery guarantee.

## Reproducibility

The public repository is `https://github.com/JashRashne/retry-semantics-llm-agents`. It provides research protocols, stored result artifacts, offline analysis scripts, build instructions, and optional supplementary material with detailed provenance. Model IDs are given in Section III. Presentation uses stored outcomes and requires no live research-provider access; detailed tests, intervals, and post-hoc summaries retain their separate evidence status.

## References

Bibliographic source: `research/references.bib`; retained unchanged.
