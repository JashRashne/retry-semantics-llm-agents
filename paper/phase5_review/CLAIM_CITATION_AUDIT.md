# Claim-to-citation audit — Phase 5.1

Audit unit: each manuscript line containing an externally sourced factual assertion, split into separately testable clauses where several assertions share a line. Locations are current `paper/manuscript.md` line numbers. A citation placed after a clause supports that clause, not all adjacent prose. Sections containing study design, empirical counts, interpretation and limitations were checked separately against the frozen internal Phase 3/4.1 package; provider documentation is not used as evidence for study outcomes. "Pass" means the cited primary source supports the narrow claim; "internal" means no external citation is appropriate. Comparison limitations are claims about what a cited paper *studied*, not priority claims about all published work.

| Claim/location | Citation(s) | Support status | Action taken |
|---|---|---|---|
| L15: reasoning/action/observation loop | ReAct, ICLR 2023 | Pass; proceedings describes interleaving | Replaced broad unsupported list of applications with specific, sourced claim. |
| L15: terminal database-state agent evaluation | τ-bench, ICLR 2025 | Pass; published benchmark scores final DB state | Upgraded from arXiv 2024 manifestation; no retry-intervention claim assigned. |
| L17: lost reply leaves RPC execution uncertain | Birrell & Nelson, ACM TOCS 1984 | Pass; RPC failure semantics | Added original RPC source; moved RFC away from a claim it did not specifically support. |
| L17: illustrative network/error mechanisms | Birrell & Nelson plus construction description | Qualified/common systems mechanism | Retained as examples; no claim of measured prevalence. |
| L18: application-level logical identity can deduplicate delivery | Helland 2012 | Pass for application-level idempotence | Reworded previous overly broad claim that all idempotent interfaces carry unique keys. |
| L19: query current state before resend | Verified Tool Calls, arXiv 2026 | Pass; the source explicitly evaluates verify-before-retry | Cited the direct agent-tool recovery study; the query remains a design option rather than a guaranteed safe read. |
| L25: restored LLM may re-synthesize different request | ACRFence 2026 | Pass; the paper explicitly identifies this in checkpoint/restore | Added citation at first claim; no priority claim. |
| L35: definition of HTTP method idempotence and default method examples | RFC 9110 §9.2.2 | Pass; normative source | Kept at definition; no inference that POST/PATCH can never be made idempotent. |
| L37: compensation for long-lived transactions | Sagas 1987 | Pass; original SIGMOD paper | Kept proceedings citation and removed seed audit note. |
| L37: application-level idempotency | Helland 2012 | Pass | Added to factual mechanism phrase. |
| L37: GitHub Issues create field surface in frozen protocol | GitHub REST Issues docs plus internal frozen protocol | Partial by docs alone; internal protocol establishes no key used | Reworded from provider-wide "no native idempotency key" to frozen protocol's missing deduplication-key field. |
| L165: public Fireworks model identifiers | Fireworks V4 Flash and V4.1 model pages | Pass for identifiers only | Added official model pages; actual serving/configuration claims remain based on frozen run records. |
| L173: GitHub Issues list includes PRs | GitHub REST Issues docs | Pass; official endpoint warning | Added first provider fact citation; validated census/early-stop remain internal contract facts. |
| L173: Sheets AppendCells and bounded grid retrieval | Google AppendCellsRequest and spreadsheets.get | Pass for API shapes | Added official docs; docs are not used to assert study read completeness. |
| L173: Razorpay Orders create/list/known-ID GET | Razorpay Orders docs (three endpoints) | Pass for endpoint existence and shape | Added official docs. List completeness and causal-ledger authority remain internal assessments, not provider guarantees. |
| L192: McNemar paired proportions | McNemar 1947 | Pass for test family | Added at frozen procedure introduction; exact conditional implementation unchanged. |
| L193: paired Method 10 interval | Newcombe 1998 | Pass, including correct paired-data paper/DOI | Added at frozen procedure introduction. |
| L194: sequentially rejective multiplicity adjustment | Holm 1979 | Pass | Added at frozen procedure introduction. |
| L195: bootstrap | Efron 1979 | Pass for bootstrap foundation | Added; whole-family unit, draw count and seed are from internal protocol, not asserted by Efron. |
| L303: byte replay vs application deduplication | RFC 9110; Helland 2012 | Pass as a conceptual distinction | Added citations to Discussion; no provider-specific key-support inference. |
| L329: HTTP idempotence | RFC 9110 | Pass | Kept precise normative claim. |
| L329: RPC uncertainty | Birrell & Nelson | Pass | Added classical provenance. |
| L329: durable message identity/idempotence | Helland 2012 | Pass | Added as application-level mechanism, not a claim of exactly-once transport. |
| L329: compensation and distributed application recovery | Sagas; Helland 2007; Helland & Campbell 2009 | Pass for respective mechanisms | Added selective proceedings citations; no citation dump into results. |
| L331: ReAct loop | ReAct proceedings | Pass | Kept. |
| L331: τ-bench terminal state and repeated trials | τ-bench proceedings | Pass | Clarified supported benchmark properties; explicitly separated our retry intervention. |
| L331: ToolMaze dynamic replanning under perturbations | ToolMaze arXiv | Pass; adjacent benchmark only | Added, without miscasting it as hidden-commit paired evaluation. |
| L333: Verified Tool Calls non-atomic failures and wrapper ablations | Verified Tool Calls arXiv full text §§4–6 | Pass; simulated retry-only, verification-only and verify-before-retry arms | Expanded from compressed mention; does not claim it tests our policy assignment. |
| L333: Did It Happen? matched hidden worlds and C0–C3 | Sun Research Square preprint full text §§4.1–4.4 | Pass; canonical DOI and full-text mirror | Added essential close comparison; explicitly credits prior hidden-world pairing. |
| L333: ACRFence re-synthesized request and rollback defense | ACRFence arXiv | Pass | Added explicit distinction from matched recovery-policy experiment. |
| L333: AFT interface intervention and postcondition mechanisms | AFT arXiv full text | Pass | Added explicit distinction from retry-policy intervention. |
| L335: Atomix transactional tool runtime | Atomix arXiv | Pass | Kept, scoped to runtime mechanism. |
| L335: Agent Mesh identity/evidence primitives from incidents | Agent Mesh arXiv | Pass; source labels its controlled evaluation as future work | Corrected prior vague juxtaposition; no controlled-intervention attribution. |
| L335: CapLease durable authorization identity | CapLease arXiv | Pass | Added only for semantic identity across recovery. |
| L335: FinalityBench effect-level financial finality | FinalityBench arXiv | Pass | Added with explicit boundary; does not support our provider results. |
| L337: precise difference from closest work | Four closest primary papers plus this paper's frozen design | Supported as a bounded comparison, not exhaustive novelty | Replaced "unique"/"first" framing with narrow policy question; matrix in provenance report. |

## Internal-claim sweep

| Manuscript location | Claim class | Authority / action |
|---|---|---|
| Abstract L11; contributions L29–31; model/design L82–173 | Study construction, intervention, and interpretation | Frozen protocol and phase review. External citations in surrounding sentences do not certify these study-specific claims. No numerical or policy definition edits were made here except bibliography/model identity and the provider-documentation Methods sentence. |
| Study 1 L175–233 | Locked sample, statistics, outcomes, mechanisms and overhead | Study 1 lock and approved Phase 3 copied context; no new calculation or external-paper outcome citation. Four statistical citations identify original methods only. |
| Study 2 L235–287 | GitHub, Sheets and Razorpay counts, canonicalization, non-evaluability and observed-prefix limits | Approved Phase 3 JSON and sealed Phase 4.1 package; no provider documentation used to validate any observed result. |
| Discussion L289–309; threats L311–325 | Inference and study limits | Derived cautiously from frozen outcomes and design. Observation strength was not randomized; causal wording remains explicitly limited. Added classical citation only for the general replay/idempotency distinction. |
| Conclusion L339–344; reproducibility L345–350; appendices L351–end | Synthesis, source segments, diagnostics | Frozen internal evidence and Phase 5 integration records. Local machine path was replaced by repository/artifact statement; no external citation needed. |

Provider Test Mode documentation was considered but omitted because the current manuscript contains no Test Mode factual assertion. External sources do not support the published study's numeric estimates; those are anchored to the frozen artifact and checked by `paper/check_consistency.py`.
