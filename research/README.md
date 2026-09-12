# Phase 1: research and evidence infrastructure

This directory tracks the ten user-specified starting references for a study of
retry semantics under ambiguous outcomes of state-mutating LLM agent tool calls.
The central distinction to investigate is replaying an already-generated request
versus invoking the LLM again to regenerate a tool call. Definitions and research
questions remain provisional.

Only bibliographic metadata has been populated. All analytical CSV fields,
including literature buckets, are blank. All reading statuses are `TODO`;
metadata verification does not mean that a source has been read. No findings,
limitations, novelty claims, contribution statements, or experiments are included.

## Files and personal workflow

- `literature.csv`: one source per row, stable citation keys and metadata provenance.
- `references.bib`: the same ten keys, using UTF-8 BibTeX.
- `notes/TEMPLATE.md`: blank template for future additions.
- `notes/*.md`: citation metadata plus unanswered personal reading questions.
- `research_questions.md`: provisional questions and unresolved scope decisions.
- `scripts/`: offline validators requiring only Python 3.9+ standard library.

Read each source yourself, fill its note in your own words, and record exact
sections/pages/figures/tables or other source locators beside analytical answers.
Keep an unresolved answer blank or `TODO`. Then transfer only your supported
classifications to the CSV. You control reading-status changes: `SKIMMED` means
you skimmed the source, `FULL_READ` means you read it fully, and `VERIFIED` means
you checked your recorded analytical claims against source evidence. These are
workflow labels, not judgments of scientific validity.

For a new source, copy the template, choose a unique key, add CSV and BibTeX
entries with that key, and set `notes_file` relative to this directory. Record
metadata source URLs and the actual metadata-check date. Re-run both validators.

## CSV conventions and controlled values

The CSV is UTF-8 with a header and standard CSV quoting. Authors are separated by
`; ` and retain source order. Multiple metadata URLs are separated by ` | `.
Use one value per enum cell; enum values are case-sensitive. Empty analytical
cells and `TODO` mean unassessed. `UNCLEAR` and `NOT_APPLICABLE` are personal
reading judgments; do not substitute them for unread material.

| Field | Allowed values |
| --- | --- |
| reading_status | TODO, SKIMMED, FULL_READ, VERIFIED |
| publication_status | STANDARD, CONFERENCE_PAPER, JOURNAL_ARTICLE, PREPRINT, TECHNICAL_REPORT, DOCUMENTATION, OTHER, UNCLEAR |
| literature_bucket | SYSTEMS_FOUNDATIONS, AGENT_METHODS, BENCHMARKS, AGENT_RELIABILITY, API_DOCUMENTATION, MODEL_DOCUMENTATION, OTHER, UNCLEAR |
| replay_or_regenerate | REPLAY, REGENERATE, BOTH, OTHER, UNCLEAR, NOT_APPLICABLE |
| real_or_simulated_system | REAL, SIMULATED, BOTH, CONCEPTUAL, UNCLEAR |
| state_mutating, retry_discussed, external_state_verified | YES, NO, PARTIAL, UNCLEAR, NOT_APPLICABLE |

All enum fields except `reading_status` and `publication_status` also accept
blank or `TODO`. `PARTIAL` requires an explanation in the note. Buckets are an
editable provisional organizational vocabulary; no source has been assigned one.
Update the validator and this table together if the vocabulary changes.

Bibliographic fields:

| Field | Meaning |
| --- | --- |
| citation_key | Stable unique key shared with BibTeX |
| title, authors | Source title and full source author list; documentation uses organizational attribution |
| year | Year of the cited manifestation; four digits, never the access year substituted for an unknown publication year |
| venue | Publication venue, report repository, standard series, or documentation provider |
| publication_status | Type of cited manifestation; PREPRINT means this entry cites arXiv, not that no later publication exists |
| doi | DOI as explicitly displayed or supplied; arXiv-issued DOIs identify arXiv records |
| arxiv_id | Identifier without URL, prefix, or version in the stored seed data; checked version recorded in metadata_notes |
| url | Primary source URL, optionally with a section anchor |
| notes_file | Note path relative to the directory containing literature.csv |
| metadata_sources | URLs consulted for bibliographic metadata only |
| metadata_checked_on | Date of metadata lookup in YYYY-MM-DD format; not Date read |
| metadata_notes | Bibliographic provenance, cited version, attribution and unresolved citation caveats only |
| missing_metadata | JSON object mapping deliberately missing required metadata fields to specific reasons; `{}` otherwise |

Personal analytical fields (all blank initially):

| Fields | Intended personal entry after reading |
| --- | --- |
| literature_bucket | Provisional organizational category |
| systems_concept, failure_model | Concepts and failure definition actually studied |
| state_mutating, external_system | Whether operations mutate state and which external system is considered |
| retry_discussed, retry_trigger | Whether retry is explicit and what initiates it |
| replay_or_regenerate | Classification supported by evidence about what is retried and whether the LLM is invoked again |
| external_state_verified | Whether external state or postconditions are checked before retrying; not bibliographic verification |
| idempotency_mechanism, compensation_mechanism, transactional_mechanism | Mechanism details in your own words, with evidence in the note |
| real_or_simulated_system | Environment classification established by reading |
| main_result_relevant_to_project, limitation_relevant_to_project | Your supported statements of demonstrated results and their limits |

Free-text analytical fields accept blank or `TODO`. The validators do not infer,
generate, or evaluate these answers. Detailed evidence stays in the linked note.

## Metadata scope and unresolved items

Metadata was checked on 2026-09-05 against the linked RFC, publisher, conference,
arXiv, and official documentation pages. No scientific conclusions were extracted.

- RFC 9110 lists Roy T. Fielding, Mark Nottingham, and Julian Reschke as editors;
  the CSV author field and BibTeX author field preserve those named contributors.
  The user-specified reading target is section 9.2.2, *Idempotent Methods*.
- Sagas retains the supplied proceedings DOI `10.1145/38713.38742`. The indexed
  [ACM publisher record](https://doi.org/10.1145/38713.38742) verifies the title,
  authors, year and proceedings but also displays the companion SIGMOD Record
  DOI `10.1145/38714.38742`. Direct publisher access was blocked. The precise DOI
  relationship remains for manual verification; no second entry was added.
- ReAct uses the verified ICLR 2023 publication year. Its arXiv record was first
  submitted in 2022; the stored DOI identifies that arXiv record.
- For tau_bench, verified_tool_calls, atomix, agent_mesh and qwen3, the cited
  manifestation is arXiv. A later conference/journal venue or acceptance status
  was not verified. This is not evidence of the absence of such a publication.
- [Agent Mesh](https://arxiv.org/abs/2608.26225) has the full subtitle *Identity
  Adequacy and Evidence Adequacy*. Its DOI is displayed by arXiv with registration
  pending; DOI resolution remains unverified.
- GitHub and Ollama documentation publication years and individual bylines were
  not verified. Years are deliberately blank with reasons in `missing_metadata`.
  Organizational attribution is used. No DOI or arXiv identifier was verified
  for those documentation pages; identifier blanks are permitted.

## Validation

From the repository root:

```sh
python3 research/scripts/validate_literature.py
python3 research/scripts/validate_bibliography.py
```

Defaults are resolved from the scripts' locations, so they also work from another
working directory. To check alternate files:

```sh
python3 research/scripts/validate_literature.py /absolute/path/literature.csv
python3 research/scripts/validate_bibliography.py --csv /absolute/path/literature.csv --bib /absolute/path/references.bib
```

The literature validator checks all required columns, duplicate keys, normalized
DOI and arXiv duplicates (including version variants), enum values, metadata
presence and basic syntax, and note-file existence. DOI and arXiv identifiers are
optional unless the venue is arXiv, which requires its identifier. Missing
`authors`, `year`, or `venue` can be acknowledged in `missing_metadata` with a
specific reason, producing a warning. Missing other mandatory metadata is an
error. Remove an exception when you populate its field; stale exceptions fail.

The bibliography validator checks key coverage and duplicate keys in both files,
and reports orphaned BibTeX entries. Orphans are informational, not errors. It
scans top-level BibTeX entries with nested braces, quotes and comments; it is not
a complete BibTeX parser or a field-by-field metadata comparison. Neither script
checks live URLs, DOI registration, citation truth, evidence quality, or whether
an analytical classification is justified. Successful validation is structural.

Both scripts exit 0 when no errors exist and 1 on errors. The seed literature
file intentionally produces two warnings for the undocumented publication years.
