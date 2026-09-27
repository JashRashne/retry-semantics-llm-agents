# Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes

**Author:** J. Rashne<br>
**Affiliation:** Independent Research<br>
**Correspondence:** `rashne.jash@gmail.com`<br>
**Date:** September 2026<br>
**Artifact Repository:** `https://github.com/JashRashne/retry-semantics-llm-agents`<br>
**Status:** Pre-Collection Draft (Study 1A Canonical Locked; Study 2 Model Amendment Pending)

---

## Abstract

Large Language Model (LLM) agents are increasingly entrusted with executing state-mutating operations across software systems, databases, and third-party web APIs. When an external mutation call encounters an ambiguous outcome—such as a network transport timeout or dropped HTTP connection—the client cannot determine whether the request was committed by the remote service or was not executed remotely. In distributed systems, this classical uncertainty is governed by transport-level retry protocols and idempotent endpoint design. However, LLM agent runtimes face a novel architectural fork at the retry boundary: **Exact Request Replay** (deterministically redispatching the identical synthesized request payload without invoking the model) versus **LLM Regeneration** (returning the ambiguity to the model context and allowing it to re-reason, inspect external state, or select alternative actions).

We present a controlled empirical study isolating this execution-boundary choice. We formalize an ambiguity model distinguishing two mutually exclusive hidden execution states: $H_0$ (the original mutation was not executed remotely) and $H_1$ (the original mutation committed, but its acknowledgment was lost). In **Study 1**, evaluating 160 matched four-arm families (640 total arms) on a controlled, non-idempotent Ticket Creation benchmark using DeepSeek-V4-Flash, we observe an extreme interaction between retry locus and hidden execution state. Under $H_0$, both Replay and Regeneration achieved 100.0% state correctness (160/160 each). Under $H_1$, Exact Request Replay suffered a 100.0% failure rate due to duplicate mutations (0/160 state-correct), whereas LLM Regeneration achieved 94.375% state correctness (151/160). The prespecified $H_1$ difference was $-94.375$ percentage points (paired Newcombe Method 10 95% CI: $[-97.013\%, -89.106\%]$; exact McNemar $p = 7.006 \times 10^{-46}$), with an interaction $(\Delta_{H1} - \Delta_{H0})$ of $-94.375$ percentage points (bootstrap 95% CI: $[-97.500\%, -90.625\%]$). Mechanistically, 100.0% of successful $H_1$ regeneration arms (151/151) executed an observation-before-write recovery sequence, whereas all unsuccessful arms (9/9) wrote before observing.

To evaluate whether these phenomena extend beyond the controlled benchmark, we present the prospective design, formal semantics contracts, and bounded observation schedule (OBS-1) for **Study 2**, spanning GitHub Issues, Google Sheets v4, and Razorpay Orders (64 scheduled families; 256 arms per provider; 768 total arms). The originally specified Fireworks serverless 0731 model became unavailable before collection and requires a separate prospective pre-data model-binding amendment after capability verification. Zero Study 2 paper observations have been executed, and all Study 2 empirical results remain explicit placeholders.

---

## 1. Introduction

Autonomous software agents powered by Large Language Models (LLMs) have progressed from conversational assistants to active agents capable of calling external tools, invoking REST endpoints, manipulating cloud spreadsheets, dispatching financial transactions, and issuing database mutations \cite{react, tau_bench}. As agents transition from read-only retrieval-augmented generation (RAG) to autonomous action, their reliability depends critically on how they handle transient execution failures.

In distributed systems, transient failures are inevitable. Network partitions, socket timeouts, gateway dropped connections (e.g., HTTP 504), and server restarts introduce *ambiguous execution outcomes* \cite{rfc9110}: a client sends a state-mutating command, receives no acknowledgment, and cannot definitively ascertain whether the command committed on the server prior to the disruption or was aborted before execution. Classical systems engineering resolves this ambiguity via two well-established mechanisms:
1. **Idempotent interfaces**, where requests carry unique client-generated idempotency keys allowing safe, deterministic transport-level replays; or
2. **Read-before-retry reconciliation**, where the client issues a non-mutating query to inspect current remote state before deciding whether to resend.

When these principles are mapped to LLM agent architectures, an unexamined ambiguity arises at the runtime boundary. When a tool call returns an ambiguous failure (e.g., `ToolError: Request timed out`), the agent framework must decide *what constitutes a retry*. Runtimes currently implement one of two contrasting semantics:
- **Exact Request Replay ($R_{\text{rep}}$):** The runtime infrastructure catches the error and redispatches the exact same HTTP request payload (identical URL, headers, and body bytes) previously generated by the model, bypassing further model inference.
- **LLM Regeneration ($R_{\text{reg}}$):** The runtime appends the ambiguous error message into the conversational context and re-invokes the LLM, granting the model the agency to decide the next action—which may include querying current state, synthesizing a new mutation, modifying arguments, or halting execution.

While both strategies are colloquially labeled "retries" in practitioner discourse and agent framework documentation, they represent fundamentally different execution regimes with diametrically opposed safety and cost profiles. Request Replay is computationally instantaneous and consumes zero additional model tokens, but risks blind duplicate execution if the original request had in fact committed. LLM Regeneration grants the agent the opportunity to inspect external state, but incurs latency, non-trivial token expense, and the risk of non-deterministic argument drift, tool hallucination, or looping.

Despite the proliferation of agent evaluation benchmarks, the literature lacks a rigorous, paired empirical measurement isolating the effect of this retry locus under controlled ground-truth hidden execution states.

### Contributions

This paper provides a paired empirical analysis and formal account of the Replay versus Regeneration retry boundary for state-mutating LLM agent tool calls:

1. **Formal Ambiguity and Recovery Model:** We formalize the distinction between Request Replay and LLM Regeneration across two ground-truth hidden execution worlds ($H_0$: mutation not executed remotely; $H_1$: mutation committed, acknowledgment lost), establishing a state-only projection framework for evaluating correctness.
2. **Controlled Benchmark Evaluation (Study 1A):** We report the canonical, locked results of 160 matched four-arm families (640 experimental arms) evaluated on a non-idempotent Ticket Creation benchmark using DeepSeek-V4-Flash. Both policies achieved 100.0% correctness under $H_0$. Under $H_1$, Replay produced duplicate mutations in 160/160 arms (0/160 correct), while Regeneration achieved 94.375% correctness ($p = 7.006 \times 10^{-46}$).
3. **Behavioral Mechanism Analysis:** We show that the success of LLM Regeneration under $H_1$ is strictly associated with an emergent *observation-before-write* pattern: 151/151 successful agents observed state prior to mutating, whereas 9/9 failed agents issued duplicate writes without prior observation.
4. **Cross-Provider External Validation Protocol (Study 2):** We design, formally specify, and freeze a pre-data multi-provider validation suite encompassing three real-world cloud APIs: GitHub Issues (eventual consistency, paginated list traversal), Google Sheets v4 (immediate grid visibility, OAuth scope constraints), and Razorpay Orders (financial test ledger, closed causal attribution).
5. **Rigorous Pre-Data Integrity:** In adherence to strict prospective protocol registration, zero Study 2 observations have been collected; existing provider manifests and evaluators are frozen, while the model binding and Google Sheets publication-ingestion path remain explicit pre-data work.

---

## 2. Motivation and Problem Formulation

Consider an LLM agent instructed to perform a business operation:

> *"Create a high-priority customer support ticket for Acme Corp regarding database latency."*

The model reasons and generates a tool call:
```json
{
  "name": "create_ticket",
  "arguments": {
    "customer_id": "cust_acme_101",
    "title": "Database latency escalation",
    "priority": "high"
  }
}
```

The runtime serializes this tool call into an HTTP `POST /api/v1/tickets` request. The socket is opened, bytes are pushed to the network layer, but the connection abruptly drops after 30 seconds with no HTTP status code returned.

```
       Client Runtime                       Remote Service
             |                                     |
             |--- POST /api/v1/tickets ----------->| [Commit?]
             |    (Socket Timeout / Dropped TCP)   |
             |<- - - - - - - - - - - - - - - - - - |
             |
             v
   Outcome is Ambiguous:
   Did the ticket commit?
```

From the perspective of the client runtime, two mutually exclusive ground-truth states exist:
- **World $H_0$ (NOT_EXECUTED):** The original mutation was not executed remotely; zero tickets exist on the server.
- **World $H_1$ (EXECUTED_ACK_LOST):** The database transaction committed and ticket `#9401` persisted, but the client did not receive the application acknowledgement. Exactly one ticket exists on the server.

Dispatch initiated, local send completed, remote receipt, remote commitment, and acknowledgement returned are distinct events. $H_0$ means no remote execution; it does not specify where dispatch or transport stopped.

### The Architectural Dilemma

Faced with this ambiguity, how should an autonomous agent framework respond?

- **Policy A (Request Replay):** The runtime executes a blind transport-level retry, dispatching the exact same `POST` payload. If the server does not enforce idempotency keys, World $H_0$ transitions to 1 ticket (Correct), but World $H_1$ transitions to 2 tickets (**Duplicate Side Effect / State Corruption**).
- **Policy B (LLM Regeneration):** The runtime exposes the failure to the model: `ToolError: Request timed out. Outcome unknown.` The LLM receives control. The model may choose to:
  1. Call `list_tickets(customer_id="cust_acme_101")` to verify current state;
  2. Re-issue `create_ticket(...)`;
  3. Change the parameters (semantic drift); or
  4. Abort and report failure to the user.

If the agent inspects state first, it can safely discover the committed ticket in $H_1$ and avoid duplication. However, if the model hallucinates, changes arguments, or re-executes without checking, it may introduce subtle state corruption or infinite retry loops.

The central research question of this paper is:

> **RQ:** Under identical ambiguous outcomes from state-mutating tool calls, how does deterministic Request Replay compare to LLM Regeneration in final-state correctness, duplicate creation, and recovery overhead across controlled environments and production cloud APIs?

---

## 3. Background and Related Work

### 3.1 Distributed Systems and Idempotence Foundations

The hazard of retrying state-mutating operations over unreliable networks is a foundational topic in distributed computing. RFC 9110 §9.2.2 formally defines an HTTP method as *idempotent* if the intended effect on the server of multiple identical requests is the same as for a single request \cite{rfc9110}. Methods such as `GET`, `PUT`, and `DELETE` are idempotent by specification, whereas `POST` and `PATCH` are non-idempotent.

When an ambiguous outcome occurs on a non-idempotent endpoint, compensating transactions \cite{sagas}, idempotency keys, and state reconciliation offer different controls. The GitHub Issues creation operation studied here has no native idempotency key in the frozen protocol, so its retry semantics require explicit attention to observed state.

### 3.2 LLM Tool Calling and Agent Reliability

Recent literature has explored LLM reasoning in interactive environments. The ReAct framework \cite{react} established the paradigm of interleaving reasoning ("thought") with action ("tool call") and observation. Benchmarks such as $\tau$-bench \cite{tau_bench} evaluate agent task completion across multi-turn user interactions in retail and airline domains, identifying high failure rates in multi-step workflows.

Closest to our investigation is the recent work by Mansoor et al. on *Verified Tool Calls* \cite{verified_tool_calls}, which investigates non-atomic tool failures and demonstrates that programmatic verification contracts improve agent reliability. Similarly, *Atomix* \cite{atomix} explores transactional semantics for multi-tool workflows, and *Agent Mesh* \cite{agent_mesh} investigates identity and evidence adequacy in multi-agent delegation.

### 3.3 Novelty and Research Positioning

To maintain scientific integrity, we explicitly demarcate what this paper does **not** claim to invent:
- We do **not** claim to invent ambiguous failure models or non-idempotent retry hazards (well-known since early network computing \cite{rfc9110, sagas});
- We do **not** claim to invent read-before-retry or verification patterns \cite{verified_tool_calls};
- We do **not** propose a new general-purpose agent framework or transactional engine.

Instead, our unique contribution is a **controlled, paired empirical dissection of the retry boundary itself**: isolating exact request replay from LLM regeneration under ground-truth $H_0$ and $H_1$ conditions, measuring their exact mathematical divergence, identifying the behavioral mechanisms of regeneration failure, and evaluating cross-provider feasibility across diverse production cloud architectures.

---

## 4. Formal Ambiguity and Execution Model

We model an agent executing in an environment characterized by a state $S \in \mathcal{S}$ and interacting with an external service via a set of tools $\mathcal{T} = \{T_{\text{mut}}, T_{\text{read}}\}$, where $T_{\text{mut}}$ is a state-mutating operation and $T_{\text{read}}$ is an observation operation.

### 4.1 The Tool-Call Opportunity and Linked Family

An experimental opportunity begins with a user task prompt $U$. The model, initialized with system prompt $S_0$ and tool schemas $\mathcal{T}$, generates an original assistant message containing a tool call $M = (\text{name}, \text{call\_id}, \text{args})$.

If $M$ is parseable, schema-valid, and task-correct, it is declared an *eligible original generation*. To eliminate sampling variance and ensure exact pairing, $M$ is frozen and evaluated across a linked four-arm family:

$$\mathcal{F} = \{ \text{Arm}(H_0, R_{\text{rep}}), \, \text{Arm}(H_0, R_{\text{reg}}), \, \text{Arm}(H_1, R_{\text{rep}}), \, \text{Arm}(H_1, R_{\text{reg}}) \}$$

All four arms inherit the identical initial logical state, identical prompt context, and identical synthesized tool call $M$.

### 4.2 The Two Hidden Execution Worlds

Let $W_{\text{arm}}$ be the deterministic mapping of $M$ into a concrete provider HTTP request (binding scope, credentials, and collision-free correlation markers).

- **World $H_0$ (NOT_EXECUTED):**
  $$W_{\text{arm}} \text{ is constructed and durably recorded, but } \mathbf{never} \text{ dispatched.}$$
  The pre-recovery external state satisfies:
  $$\text{Card}(\text{Effects}_{\text{pre}}) = 0$$

- **World $H_1$ (EXECUTED_ACK_LOST):**
  $$W_{\text{arm}} \text{ is dispatched exactly once to the provider and successfully committed.}$$
  The positive acknowledgment (e.g., HTTP 201 Created with resource ID) is captured by the harness for verification, but **strictly withheld** from the model context.
  The pre-recovery external state satisfies:
  $$\text{Card}(\text{Effects}_{\text{pre}}) = 1$$

### 4.3 Controlled Synthetic Ambiguity

In all four arms, the model receives an identical synthetic tool error response:
```text
ToolError: The previous request timed out. Its outcome is unknown.
```
No hidden state, provider IDs, or status codes leak into the model context.

### 4.4 Recovery Policies

1. **Exact Request Replay ($R_{\text{rep}}$):**
   The runtime takes the stored request bytes $W_{\text{arm}}$ and executes them over the network exactly once. The model is not invoked. Replay terminates immediately following this single dispatch.

2. **LLM Regeneration ($R_{\text{reg}}$):**
   The runtime appends the canonical `ToolError` message to the history and invokes the LLM. The model enters an iterative recovery loop governed by a strict action budget:
   - Maximum permitted tool actions: $B_{\text{actions}} = 3$;
   - Maximum permitted model completion calls: $B_{\text{calls}} = 4$.
   The model may issue read actions ($T_{\text{read}}$), mutation actions ($T_{\text{mut}}$), or terminate with a textual completion.

### 4.5 State-Only Evaluation and Logical Projection

Correctness is evaluated from provider-specific certified terminal-state evidence, never from intermediate model claims or HTTP return codes alone.

We define a projection function $\mathcal{P}: \mathcal{S}_{\text{ext}} \to \mathbb{Z}_{\ge 0} \times \mathbb{Z}_{\ge 0}$ mapping the external resource store to a tuple $(N_{\text{intended}}, N_{\text{unintended}})$, where:
- $N_{\text{intended}}$ is the count of distinct external resources matching the semantic requirements of task $U$ within the arm's isolated namespace.
- $N_{\text{unintended}}$ is the count of non-matching or corrupted resources.

The primary binary endpoint $\text{STATE\_CORRECT} \in \{0, 1\}$ is defined as:
$$\text{STATE\_CORRECT} = \begin{cases}
1 & \text{if } N_{\text{intended}} = 1 \text{ and } N_{\text{unintended}} = 0 \\
0 & \text{otherwise (Missing, Duplicate, or Unintended Effect)}
\end{cases}$$

If external state cannot be authoritatively certified by the evaluator prior to the observation deadline, the arm is classified as $\text{INCONCLUSIVE}$ and excluded from primary paired analysis.

---

## 5. Study 1: Controlled Benchmark Methodology

### 5.1 Experimental Setup

Study 1 evaluates the primary hypotheses on an isolated, deterministic Ticket Creation benchmark simulating an enterprise service-desk backend.
- **Scenarios:** 8 distinct ticket scenarios (`CREATE001` through `CREATE008`), specifying customer identifiers, problem domains, titles, and descriptions.
- **Replicates & Counterbalancing:** 20 replicates across 8 scenarios, yielding $N = 160$ scheduled family opportunities (640 total arms). Replicate ordering was strictly counterbalanced (odd replicates: $1 \to 8$; even replicates: $8 \to 1$).
- **Model Configuration:** DeepSeek-V4-Flash (`accounts/fireworks/models/deepseek-v4-flash-0731`) served via Fireworks serverless inference. Hyperparameters were frozen: temperature $T = 0.0$, top-$p = 1.0$, maximum completion tokens 1024, `parallel_tool_calls = False`, `reasoning_effort = "none"`.
- **Stopping Rule:** Exactly 160 scheduled opportunities; zero sample replacement, zero model shopping, and zero prompt tuning.

### 5.2 Statistical Plan and Estimands

For each hidden world $w \in \{H_0, H_1\}$, the primary estimand is the risk difference:
$$\Delta_w = \text{Rate}(\text{Replay})_{\text{correct}} - \text{Rate}(\text{Regeneration})_{\text{correct}}$$
evaluated over matched families where both arms are evaluable.

Statistical significance is assessed using:
- **Exact conditional McNemar tests** on discordant cell counts ($n_{10}, n_{01}$);
- **Paired Newcombe (1998) Method 10** two-sided 95% confidence intervals;
- **Holm-Bonferroni correction** across the two primary families ($H_0, H_1$);
- **Whole-family bootstrap** (10,000 replicates, seed 20260916) for the interaction contrast:
  $$\text{Interaction} = \Delta_{H1} - \Delta_{H0}$$

---

## 6. Study 1: Locked Empirical Results

Study 1 collection concluded on 2026-09-17 with zero dropped families, zero infrastructure aborts, and 100% data audit compliance. All results reported below are derived from the canonical, locked analysis artifact (`research/results/STUDY1_RESULTS_LOCK.md`).

### 6.1 Primary Correctness Findings

Table \ref{tab:study1-results} summarizes the primary estimands across the 160 matched families.

\input{tables/study1_table.tex}

#### World $H_0$ (NOT_EXECUTED)
When the initial mutation never reached the server, both policies achieved flawless recovery:
- Exact Replay: 160/160 state-correct ($1.000$);
- LLM Regeneration: 160/160 state-correct ($1.000$);
- Difference $\Delta_{H0} = 0.000$ percentage points;
- Paired Newcombe 95% CI: $[-2.345\%, +2.345\%]$;
- McNemar raw and Holm-adjusted $p = 1.000$.

#### World $H_1$ (EXECUTED_ACK_LOST)
When the initial mutation committed but its acknowledgment was withheld, the policies diverged completely:
- Exact Replay: **0/160 state-correct ($0.000$)**;
- LLM Regeneration: **151/160 state-correct ($0.94375$)**;
- Difference $\Delta_{H1} = -0.94375$ ($-94.375$ percentage points);
- Discordant counts: $n_{10} = 0$ (Replay correct, Regen incorrect), $n_{01} = 151$ (Replay incorrect, Regen correct), $n_{00} = 9$ (both incorrect), $n_{11} = 0$ (both correct);
- Paired Newcombe 95% CI: $[-97.013\%, -89.106\%]$;
- Exact McNemar raw $p = 7.006 \times 10^{-46}$; Holm-adjusted $p = 1.401 \times 10^{-45}$.

#### Prespecified Interaction
The interaction between retry locus and hidden world was:
$$\Delta_{H1} - \Delta_{H0} = -94.375 \text{ percentage points}$$
with a 10,000-replicate whole-family bootstrap 95% percentile confidence interval of $[-97.500\%, -90.625\%]$.

```text
Study 1 State Correctness Summary:
============================================================
World H0: Replay [160/160] (100%)  ==  Regen [160/160] (100%)
World H1: Replay [  0/160] (  0%)  <<  Regen [151/160] (94.4%)
============================================================
Interaction: -94.375 percentage points (p = 1.40e-45)
```

### 6.2 Failure Taxonomy and Behavioral Mechanism

Analysis of the 640 executed arms revealed sharp failure-mode segregation:
- **Duplicate Mutations:** Exact Replay produced duplicate mutations in 160/160 $H_1$ arms (100.0%), and 0/160 $H_0$ arms. LLM Regeneration produced duplicate mutations in 9/160 $H_1$ arms (5.625%), and 0/160 $H_0$ arms.
- **Missing or Wrong Mutations:** Zero missing or task-incorrect mutations occurred across all 640 arms.
- **Execution Integrity:** Zero malformed tool calls, zero schema rejections, and zero budget exhaustions were observed.

#### The Observation-Before-Write Mechanism
Why did LLM Regeneration succeed in 151 cases but fail in 9 cases under $H_1$?

We analyzed the action sequences generated by the model during recovery. Across the 160 $H_1$ regeneration arms:
- **151 arms** executed at least one `list_tickets` read action before attempting any mutation. Upon reading state, the model observed the existing ticket created during the $H_1$ constructor phase, recognized task completion, and halted without issuing further writes. Every one of these 151 arms achieved $\text{STATE\_CORRECT} = 1$.
- **9 arms** issued a `create_ticket` mutation immediately upon receiving the timeout error without first reading state. In all 9 instances, this created a duplicate ticket, resulting in $\text{STATE\_CORRECT} = 0$.
- Zero arms followed any other pattern.

The observed correspondence was absolute:
$$\text{Correctness} \iff \text{Observation-Before-Write}$$
*(Note: As prespecified, this is an observed mechanism association, not a randomized causal intervention.)*

### 6.3 Recovery Overhead

The safety of LLM Regeneration comes at a measurable overhead cost:

| World | Policy | Mean Model Calls | Mean Recovery Tool Calls |
|---|---|---:|---:|
| $H_0$ | Exact Replay | 0.00 | 1.00 |
| $H_0$ | LLM Regeneration | 3.70 | 2.70 |
| $H_1$ | Exact Replay | 0.00 | 1.00 |
| $H_1$ | LLM Regeneration | 2.03 | 1.03 |

Under $H_0$, regeneration spent an average of 3.70 model invocations and 2.70 tool calls (typically reading state, observing absence, issuing the creation, and reading state again to confirm). Under $H_1$, regeneration required 2.03 model invocations (reading state, observing presence, and issuing a terminal textual confirmation). Request Replay required zero model calls and exactly one tool dispatch in all cases.

---

## 7. Study 2: Cross-Provider External Validation Design

While Study 1 establishes internal validity in a controlled environment, production cloud APIs exhibit idiosyncratic behaviors that may alter these dynamics:
- Non-authoritative search indexing and delayed read visibility;
- Bounded list pagination and rate-limit quotas;
- Distinct transport framing and authentication lifecycles.

**Study 2** extends the investigation to three production cloud platforms: **GitHub Issues**, **Google Sheets v4**, and **Razorpay Orders**.

### 7.1 Provider Selection and Systems Diversity

Table \ref{tab:providers} compares the architectural characteristics of the selected providers.

\begin{table*}[t]
\centering
\small
\caption{Architectural Comparison of Selected External Providers for Study 2}
\label{tab:providers}
\begin{tabular}{lllll}
\hline
\textbf{Dimension} & \textbf{GitHub Issues} & \textbf{Google Sheets v4} & \textbf{Razorpay Orders} \\
\hline
Mutation Endpoint & `POST /repos/{o}/{r}/issues` & `POST /v4/spreadsheets/...:batchUpdate` & `POST /v1/orders` \\
Mutation Semantic & Append issue to repository & Append row to allocated tab & Insert order into ledger \\
Observation Method & `GET /repos/{o}/{r}/issues` & `GET /v4/spreadsheets/{id}` & `GET /v1/orders` \\
Read Scope & Repository issues (`state=all`) & Bounded grid `A1:C100` & Account-level order ledger \\
Pagination Model & `Link` header pagination & Fixed bounding box (1 GET) & Offset/count query pagination \\
Visibility Latency & Eventual (search/list lag) & Immediate grid data & Variable / non-authoritative list \\
Correlation Mechanism & Unique body suffix marker & Column A marker & `notes.retry_semantics_marker` \\
Authentication & Fine-grained GitHub PAT & OAuth2 `drive.file` Desktop & Basic Auth (Key ID : Secret) \\
\hline
\end{tabular}
\end{table*}

### 7.2 Experimental Unit and Allocation

- **Sample Size:** 64 scheduled family opportunities per provider $\times$ 4 serial arms = 256 arms per provider (768 total Study 2 arms).
- **Model Binding:** The originally specified Fireworks serverless 0731 model became unavailable before Study 2 collection. Study 2 remains pre-data and requires a prospective model-binding amendment after capability verification.
- **Provider Scopes:**
  - GitHub: Dedicated non-production sandbox repository (`JashRashne/retry-semantics-study2-github-sandbox`).
  - Google Sheets: One already-created spreadsheet with 256 isolated GRID tabs (one arm per tab), using audited OAuth same-app/principal access. `spreadsheets.create` must not be rerun.
  - Razorpay: Dedicated Test Mode merchant account with closed ledger verification.

---

## 8. Provider Methodologies and Bounded Observation Schedules

Evaluating external cloud systems requires bounding observation costs and preventing outcome-adaptive polling loops. We specify the frozen **OBS-1 Bounded Observation Schedule** governing post-recovery evaluation.

### 8.1 Monotonic Anchor and Horizon

Each arm defines an anchor $r_0$ recorded immediately upon recovery termination (after Replay dispatches or Regeneration stops/exhausts its budget). All observation rounds execute at fixed offsets from $r_0$. The global maximum observation horizon is capped at:
$$H = 1140 \text{ seconds (19 minutes)}$$

### 8.2 Provider-Specific Observation Rules

#### 1. GitHub Issues
- **Endpoint & Tool:** `create_issue` ($T_{\text{mut}}$) and `list_issues` ($T_{\text{read}}$).
- **Correlation:** The arm marker is `rs2gh1-` plus the first 32 lowercase hex characters of SHA-256(namespace + `:` + arm ID), where namespace is `d88836f3d4b57ed5c300d650ddfb0e3a`. The issue body ends with `<!-- retry-semantics-study2-gh:v1:{arm_marker} -->`.
- **Census Traversal:** Model reads and evaluator censuses traverse the complete bounded `GET /issues?state=all` Issues and PR census, following `next` rel-links to exhaustion, capped at 16 pages (1,600 maximum entries) and 540 seconds.
- **OBS-1 Schedule:** Exactly two complete-census opportunities:
  - Round 1: initiated at $r_0 + 0$s (deadline $+540$s);
  - Round 2: initiated at $r_0 + 600$s (deadline $+1140$s).

#### 2. Google Sheets v4
- **Endpoint & Tool:** `append_row` ($T_{\text{mut}}$ via `AppendCellsRequest`) and `list_rows` ($T_{\text{read}}$).
- **Correlation:** Column A contains the arm correlation marker; Columns B and C store item and detail.
- **Grid Traversal:** A single bounded `spreadsheets.get` querying range `A1:C100` retrieves all populated rows within 40 seconds (30s HTTP deadline + 10s local processing).
- **OBS-1 Schedule:** Exactly one immediate complete read at $r_0 + 0$s (deadline $+40$s).

#### 3. Razorpay Orders
- **Endpoint & Tool:** `create_order` ($T_{\text{mut}}$) and `list_orders` ($T_{\text{read}}$).
- **Correlation:** Harness injects `notes.retry_semantics_marker` into the provider request payload (hidden from model arguments).
- **Ledger Traversal:** `GET /v1/orders` queries up to 5 pages ($5 \times 100 = 500$ orders). Because Razorpay list traversal is not authoritatively complete, evaluation relies on a *closed causal ledger* tracking all dispatched HTTP requests and acknowledgments, supplemented by at most one optional H1 constructor-ID direct request plus at most three recovery Create-ID direct `GET /v1/orders/{id}` requests for independently known IDs.
- **OBS-1 Schedule:**
  - Round 1: initiated at $r_0 + 0$s (deadline $+170$s);
  - Round 2: initiated at $r_0 + 200$s (deadline $+370$s);
  - Direct GET supplements: executed sequentially, finishing by $+470$s.

---

## 9. Evaluator Semantics and Inconclusive Outcomes

To prevent evaluation bias, Study 2 enforces strict fail-closed evaluator semantics:

1. **State Correctness:**
   - $\text{STATE\_CORRECT} = 1$: Exactly one matching intended effect and zero unintended/duplicate effects identified in external storage.
   - $\text{STATE\_CORRECT} = 0$: Positively certified duplicate mutation, missing mutation, or corrupted resource.
2. **Inconclusive Handling ($\text{INCONCLUSIVE}$):**
   If network failures, provider rate limits, incomplete pagination, or observation timeouts prevent definitive determination of external state before the terminal deadline, the arm is labeled $\text{INCONCLUSIVE}$.
   - An inconclusive arm is **never** scored as model failure.
   - It is excluded from primary paired comparisons.
   - In accordance with V1.3 protocol rules, denominators are never backfilled or replaced.
3. **Early Stopping:** An observation round terminates early if and only if $\text{STATE\_CORRECT} = 0$ is definitively established by positive evidence (e.g., encountering two verified duplicate issue IDs).

---

## 10. Experimental Controls and Reproducibility

The frozen protocols specify the following controls; Study 2 collection remains pre-data:

1. **Writer and Baseline Controls:** Provider-specific readiness and baseline checks constrain writer scope and marker collisions before an arm proceeds.
2. **Sampling Contract:** The manifests specify $T = 0.0$ and top-$p = 1.0$, with provider-specific prespecified seeds.
3. **Model Requests:** The GitHub and Razorpay paper collectors send explicit conversation history with model requests.
4. **Transport Controls:** The frozen GitHub and Razorpay paper transport uses one HTTP send per request, disables automatic retries and redirects, and records dispatch, local-send, response, and transport-error evidence separately.
5. **Durable Evidence:** The GitHub and Razorpay collectors write exclusive JSON operation-intent, result, and selected event files. Request and response bodies have SHA-256 digests; Sheets uses a separate audited evidence path.

---

## 11. Study 2 Cross-Provider Analysis and Pre-Data Status

Table \ref{tab:study2-results} provides the prospective analysis template for Study 2.
For each provider and hidden world, matched N, both displayed correctness fractions, the risk difference, confidence interval, and McNemar test will use the same families with both arms evaluable. Scheduled family counts describe design size, not observed matched N.

\input{tables/study2_table.tex}

```text
Study 2 Prospective Execution Matrix:
========================================================================
Provider          Total Scheduled Families    Total Arms    Status
------------------------------------------------------------------------
GitHub Issues                64                   256       PENDING
Google Sheets                64                   256       PENDING
Razorpay Orders              64                   256       PENDING
========================================================================
Total Study 2                192                  768       PRE-DATA
```

### Pre-Data Protocol Integrity Declaration
In strict conformance with open-science standards:
- **Zero Study 2 paper observations have been collected.**
- Existing manifests, catalogues, readiness contracts, and evaluators are frozen; the model binding requires a separate prospective amendment.
- The GitHub and Razorpay publication-ingestion path is implemented and tested and refuses incomplete or corrupt run evidence; Google Sheets ingestion remains fail-closed pending a frozen run-projection schema.
- Empirical results will be populated only after a prospective pre-data model-binding amendment and capability verification.

---

## 12. Discussion and Systems Implications

The empirical findings from Study 1, paired with the cross-provider architecture of Study 2, provide actionable guidance for AI agent runtimes:

### 12.1 When is Replay Safe?
Exact Request Replay can be safe when repeated dispatch is semantically idempotent or deduplicated by the endpoint or surrounding protocol. One important mechanism is **strict, end-to-end server-side idempotency keys** (e.g., Stripe's `Idempotency-Key` or AWS client request tokens). The safety of replay depends on the endpoint's documented deduplication scope and retention rules.

### 12.2 When is Regeneration Necessary?
For non-idempotent state-mutating operations (such as GitHub Issues creation or Google Sheets `AppendCells`), **blind replay can duplicate effects when the original request committed but its acknowledgement was lost**. In our controlled benchmark, blind replay caused a 100.0% failure rate under $H_1$. For non-idempotent endpoints, runtimes can reconcile external state before another mutation, programmatically or through a bounded model read.

### 12.3 The Hidden Costs of Regeneration
While LLM Regeneration successfully mitigates duplicate mutations, it introduces significant operational tradeoffs:
- **Model-Call Cost:** Regeneration averaged 3.70 recovery model calls under $H_0$ and 2.03 under $H_1$; Replay made zero recovery model calls.
- **Latency:** Multi-step read-before-write sequences add significant wall-clock latency, compounding the duration of already slow agent workflows.
- **Residual Risk:** In 5.625% of $H_1$ cases, the model failed to observe state before writing, duplicating the mutation despite having the tools to verify.

### 12.4 Proposed Architectural Standard: Guarded Idempotence Wrappers
Agent runtimes should neither blindly replay nor unconditionally regenerate. Instead, we advocate for **Guarded Idempotence Wrappers**:
1. If the tool endpoint supports server-side idempotency keys, the runtime should attach a deterministic key and execute Request Replay.
2. If the endpoint is non-idempotent, the runtime should enforce a *mandatory verification probe* (programmatic or forced model-read) before permitting any retry mutation to be dispatched.

---

## 13. Threats to Validity

### 13.1 Internal Validity
- *Synthetic Ambiguity:* We injected synthetic timeout errors rather than waiting for natural network drops. This is a deliberate experimental control: natural drops cannot be randomized across matched $H_0/H_1$ worlds without violating causal pairing.
- *Prompt and Sampling Sensitivity:* Study 1 used a pinned sampling configuration; hosted inference can still vary across invocations.

### 13.2 Construct Validity
- *State-Only Correctness:* Study 1A used terminal ticket counts; Study 2 specifies provider-specific certified state evidence, avoiding subjective LLM-as-a-judge evaluation.
- *Budget Limits:* The 3-action / 4-call regeneration budget was chosen based on pilot feasibility. Expanding the budget could theoretically allow failed agents more opportunities to recover, but would increase cost and risk infinite loops.

### 13.3 External Validity
- *Model Diversity:* Study 1 focused on DeepSeek-V4-Flash. While this model demonstrates representative modern tool-calling capabilities, frontier models (e.g., GPT-4o, Claude 3.5 Sonnet) may exhibit different observation-before-write base rates.
- *API Diversity:* The pre-data Study 2 design incorporates three cloud architectures with different observation semantics.

### 13.4 Statistical Validity
- For Study 1A, the primary estimands, confidence intervals, and Holm-Bonferroni correction were prespecified prior to collection.

---

## 14. Ethics and Limitations

- **API Safety and Resource Quotas:** All experiments operate within dedicated developer sandboxes, test-mode credentials, and private repositories. Zero real currency, private personal data, or production infrastructure was exposed.
- **Negative Externalities:** Automated retry loops can generate unintended load or spam if unconstrained. Our protocol enforces strict request caps and timeouts.

---

## 15. Conclusion and Future Work

This paper investigated the Replay versus Regeneration boundary through a matched four-arm experimental protocol. In Study 1A, both policies achieved 100.0% correctness when the original mutation was not executed remotely ($H_0$). When it committed but its acknowledgment was lost ($H_1$), blind Replay produced duplicate effects in 160/160 arms, while Regeneration achieved 94.375% correctness. This result is specific to the studied benchmark and model.

The pre-data Study 2 protocol is designed to test how these dynamics behave across three cloud providers with different observation semantics.

```text
Final Research Status:
========================================================================
Study 1 (Controlled Ticket CREATE):    CANONICAL / LOCKED (N=160, p < 1e-44)
Study 2 (Cross-Provider Validation):   FROZEN PRE-DATA (OBS-1, N=192 fams)
Total Paper Observations Executed:     640 (Study 1) / 0 (Study 2)
========================================================================
```

---

## References

```bibtex
@techreport{rfc9110,
  title = {{HTTP Semantics}},
  author = {Fielding, Roy T. and Nottingham, Mark and Reschke, Julian},
  year = {2022},
  institution = {Internet Engineering Task Force},
  type = {RFC},
  number = {9110},
  url = {https://www.rfc-editor.org/rfc/rfc9110.html}
}

@inproceedings{sagas,
  title = {{Sagas}},
  author = {Garcia-Molina, Hector and Salem, Kenneth},
  year = {1987},
  booktitle = {Proceedings of the 1987 ACM SIGMOD International Conference on Management of Data},
  pages = {249--259}
}

@inproceedings{react,
  title = {{ReAct: Synergizing Reasoning and Acting in Language Models}},
  author = {Yao, Shunyu and Zhao, Jeffrey and Yu, Dian and Du, Nan and Shafran, Izhak and Narasimhan, Karthik and Cao, Yuan},
  year = {2023},
  booktitle = {International Conference on Learning Representations (ICLR)}
}

@misc{tau_bench,
  title = {{$\tau$-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains}},
  author = {Yao, Shunyu and Shinn, Noah and Razavi, Pedram and Narasimhan, Karthik},
  year = {2024},
  eprint = {2406.12045},
  archivePrefix = {arXiv}
}

@misc{verified_tool_calls,
  title = {{Verified Tool Calls Improve LLM Agent Reliability Under Non-Atomic Failures}},
  author = {Mansoor, Isham Kalappurackal and Phadke, Abhishek and Rana, Pratip},
  year = {2026},
  eprint = {2608.02645},
  archivePrefix = {arXiv}
}

@misc{atomix,
  title = {{Atomix: Transactional Execution for Stateful LLM Agent Tools}},
  author = {DeepSeek Research},
  year = {2026},
  eprint = {2608.10000},
  archivePrefix = {arXiv}
}

@misc{agent_mesh,
  title = {{Agent Mesh: Identity Adequacy and Evidence Adequacy in Multi-Agent Delegation}},
  author = {Rashne, Jash and Collaborators},
  year = {2026},
  eprint = {2608.26225},
  archivePrefix = {arXiv}
}
```
