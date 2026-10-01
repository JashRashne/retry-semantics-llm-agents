# Phase 5 canonical paper integration

Status: COMPLETE; compiled canonical-paper candidate for review. No commit or push.

Approved Phase 4.1 manifest SHA-256: `671d1dff2e2995c14646cd5f46568430f606a749d6671cc608e9c9ee6950717d`.

## Source and build

Modified existing canonical files: `paper/main.tex`, `paper/manuscript.md`, `paper/tables/study1_table.tex`, `paper/tables/study2_table.tex`. Added deterministic source/QA scripts, README, six approved vector PDF figures and wrappers, quantitative data copies, table inputs, compiled PDF and review receipts. The complete changed/new-file list is in `GIT_STATE_AFTER.json`.

LaTeX template: existing IEEEtran 10pt journal compsoc, two-column main text; one-column appendix. Existing curated `research/references.bib` is byte-identical. `PAPER_STATE_BEFORE.json` records pre-edit source hashes and Git state. The old zero-observation Study 2 placeholders and prospective readiness language are superseded.

Commands from repository root:

```sh
python3 paper/build_source.py
mkdir -p paper/build
tectonic --only-cached --untrusted --keep-logs --keep-intermediates --outdir paper/build paper/main.tex
python3 paper/check_consistency.py --receipt paper/phase5_review/CONSISTENCY_QA.json
```

Compiled PDF: `/Users/jashrashne/Desktop/retry_semantics/paper/build/main.pdf`. Pages: **14**. SHA-256: `8f76d06eb11997aeff7789d0320070fe07d57a609b65e46f921110ff9a9f61e4`.

Initial Tectonic cache was incomplete. Built-in standalone compiler preparation timed out. The installed Tectonic fetched missing TeX assets during the authorized build; subsequent final build used cached assets only. No compiler/plugin was installed and no experimental provider/API request was made.

## Abstract

An ambiguous tool-call outcome leaves an agent uncertain whether a state mutation failed to execute or executed without a returned acknowledgement. Retrying the same request and returning the ambiguity to a language model are different recovery policies. We compare Exact Replay and LLM Regeneration in matched four-arm families that cross policy with hidden execution world: H0, where the original mutation did not execute, and H1, where it executed but acknowledgement was lost. In the locked confirmatory Ticket CREATE experiment, both policies were correct in 160/160 H0 arms. In H1, Replay was correct in 0/160 and Regeneration in 151/160; the Replay-minus-Regeneration difference was -94.3750 percentage points (95% paired CI [-97.0128, -89.1060] pp). Canonical GitHub external-replication coverage and a separately authorized Google Sheets post-incident replication reproduce the large hidden-world reversal: H1 Replay was correct in 0/64 and 0/64, respectively, while Regeneration was correct in 64/64 and 64/64. GitHub additionally recorded H0 Regeneration missing effects. The original Sheets attempt was invalidated by a shared constructor defect and contributes no behavioral denominator. Three separate Razorpay runs stopped under provider throttling and contribute observed-prefix and operational evidence. Under these controlled ambiguous-outcome constructions, retry correctness varies sharply with hidden execution state, while safe recovery also depends on what terminal state can be authoritatively established; the evidence supports designing runtimes around that uncertainty rather than an unconditional retry strategy.

## Structure

Abstract; 1 Introduction; 2 Background and problem formulation; 3 Retry semantics and experimental model; 4 Experimental design and analysis hierarchy; 5 Study 1 controlled confirmatory experiment (retained methodology, locked results, mechanism association and recovery overhead); 6 Study 2 external validation (GitHub, Sheets, Razorpay, cross-provider synthesis); 7 Discussion; 8 Threats to validity; 9 Related work; 10 Conclusion; 11 Reproducibility; Appendices A GitHub source segments, B secondary descriptive McNemar values, C state defects/evaluability, D Razorpay observed prefixes and diagnostics; References.

## Figures and tables

Main figures: 1 conceptual retry model, 2 four-arm family, 3 main external effects, 4 policy correctness. Appendix figures: 5 state-defect/evaluability matrix, 6 separate Razorpay stop sequence (approved Figure S1 asset, numbered consecutively in the canonical paper).

Main tables: 1 environments and evidence status, 2 locked Study 1 results, 3 existing descriptive Study 1 recovery overhead, 4 external paired results, 5 complete-family interactions. Appendix tables: 6 GitHub source segments, 7 external descriptive McNemar values, 8 all-evaluable state defects, 9 Razorpay stops, 10 Razorpay observed-prefix points, 11 separate Razorpay state defects. All are referenced in prose and have unique labels.

## Validation and limitations

All approved numerical checkpoints pass against actual Phase 3 JSON. Ten table CSVs, six figure-data CSVs and six PDF figures are byte-identical to Phase 4.1. All 135 frozen Phase 4.1 payload hashes remain valid, including frozen numerical source snapshots. Twelve Study 2 numeric result/interpretation paragraphs match the approved candidate or its unchanged table notes. The Study 1 lock and bibliography are unchanged. No result, estimator, canonicalization, inferential role or scientific evidence was modified or recomputed.

Citation check: all seven cited keys have existing bibliography entries, no duplicates/broken keys/placeholders; BibTeX has no warnings. All ten existing bibliography records have title/author fields; dated arXiv preprints use internally consistent year fields; ReAct correctly uses its ICLR 2023 year alongside a 2022 arXiv identifier. Undated documentation uses access dates without invented publication dates. Conflicting embedded old Markdown Atomix/Agent Mesh metadata was removed in favor of the existing curated bibliography.

No external literature verification occurred. Later verification topics: primary Newcombe Method 10 methodology, Holm/whole-family bootstrap references, classical uncertain RPC execution guarantees if literature coverage is expanded. Existing metadata caveats remain: Sagas companion DOI relationship, Agent Mesh DOI resolution, later publication venues for preprints.

Latest final PDF: all 14 pages visually inspected after Poppler rendering. Zero overfull boxes, missing characters, font warnings, undefined citations/references or duplicate labels. Fifteen underfull hbox warnings remain (paragraph/table spacing); no visual overflow or clipping. PDF page-canvas character bounds pass.

Git HEAD/branch/index unchanged; edits are unstaged and confined to paper files. Linked Razorpay worktree stays clean. No commit or push. The approved archive/evidence remains untouched.

## Substantive changes

Integrated approved external results and incident governance into the canonical paper while retaining accurate introduction/context, mathematical definitions, Study 1 methodology/results/mechanism/overhead, and existing related-work citations. Updated Discussion, Threats, Conclusion and reproducibility wording from Phase 4.1. Removed stale pre-data placeholders, the erroneous Markdown interaction p-value attachment, and conflicting embedded bibliography metadata. Preserved the GitHub non-evaluable arm, separate Sheets post-incident status, separate Razorpay prefixes and descriptive external inference. Added vector figures, approved tables, automatic numbering/references and deterministic publication-source/build checks.

## Git status --short

```text
 M paper/main.tex
 M paper/manuscript.md
 M paper/tables/study1_table.tex
 M paper/tables/study2_table.tex
?? paper/README.md
?? paper/build/
?? paper/build_source.py
?? paper/check_consistency.py
?? paper/figures/
?? paper/phase5_review/
?? paper/publication_data/
?? paper/tables/study1_overhead.tex
?? paper/tables/table1_environments.tex
?? paper/tables/table2_external_paired.tex
?? paper/tables/table3_interactions.tex
?? paper/tables/table4_failure_mechanisms.tex
?? paper/tables/table5_razorpay_stops.tex
?? paper/tables/tableA1_github_segments.tex
?? paper/tables/tableA2_descriptive_mcnemar.tex
?? paper/tables/tableA4_razorpay_points.tex
?? paper/tables/tableA5_razorpay_mechanisms.tex
```

## Git diff --stat

```text
 paper/main.tex                | 733 +++++++++++++++++++++++++++---------------
 paper/manuscript.md           | 525 +++++++++++-------------------
 paper/tables/study1_table.tex |  27 +-
 paper/tables/study2_table.tex |  22 +-
 4 files changed, 677 insertions(+), 630 deletions(-)
```
