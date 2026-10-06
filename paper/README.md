# Reader-first IEEE conference paper

`manuscript.md` is the editable main manuscript. `build_source.py` renders it into `main.tex`; `supplement/manuscript.md` renders into the separate `supplement.tex`. In both documents the first operative command is `\documentclass[conference]{IEEEtran}`. The title is unchanged. There are no custom font-family declarations, system-font file paths, geometry changes, font-size overrides, or spacing adjustments to shorten the paper.

## Reviewer revision, 6 October 2026

The current sources integrate the audited post-review no-model baseline from `../research/baselines/no_model/RESULTS.md`, separately from historical Replay--Regeneration matched cohorts. Manuscript tables omit significance tests against Replay while retaining stored paired intervals, bootstrap interactions, and descriptive marginal uncertainty. Original statistical outputs and evidence/provenance files remain unchanged. The presentation generators preserve these revisions, including the baseline column.

From `paper/`, compile the current main paper and supplement with the installed Tectonic, using cached resources only:

```sh
python3 scripts/build_rewrite_assets.py
python3 scripts/build_supplement_tables.py
python3 build_source.py
/opt/homebrew/bin/tectonic --only-cached --untrusted --keep-logs main.tex
/opt/homebrew/bin/tectonic --only-cached --untrusted --keep-logs supplement.tex
```

Both builds succeed. The core results table has no overfull box. The existing cached Tectonic font substitutions described below remain a publication-format limitation. `main.pdf` and `supplement.pdf` are current diagnostic builds; the `build/` artifacts and prior QA reports describe historical revisions. Historical QA scripts include prose assertions for those earlier revisions and are not evidence that the current reviewer revision was checked. No experiment or statistical estimator is needed to build the revised manuscript.

## Historical Pass C build status

**Font QA is blocked by the incomplete local TeX installation.** The custom `ieee_native_fonts.tex` mechanism has been removed. Figure text now embeds Bitstream Vera Sans from the ReportLab package, with no installed Arial requirement. The sources use standard IEEEtran and normal packages. A normal pdfLaTeX/TeX Live installation with IEEEtran and its standard Times, Helvetica, Courier, and math font resources is the intended portable workflow.

The available cached Tectonic installation uses XeLaTeX Unicode encoding and lacks Times/Courier font-family definitions. Offline builds silently substitute Latin Modern, including for bold, italic, and code text. Both candidate PDFs compile, but fail the font-substitution requirement; all candidate fonts are embedded. These candidates are **not publication-ready** and were not promoted over the accepted Pass B PDFs.

- `build/main.pdf` and `build/supplement.pdf`: retained Pass B artifacts, stale relative to the Pass C prose.
- `build/pass_c_candidate/main.pdf`: historical Pass C diagnostic candidate, 8 pages including references.
- `build/pass_c_candidate/supplement.pdf`: diagnostic candidate, 6 pages.
- `rewrite_review/PASS_C_QA.json`: explicit failed font QA, successful protected-input/numerical checks.
- `rewrite_review/PASS_C_FINAL_AUDIT.md`: reader audit, changes, hashes, warnings, and resource blocker.

No TeX packages were downloaded or installed. The build must remain local/offline; no research-provider access is involved.

## Portable build commands

With an already available, complete standard pdfLaTeX installation, run from `paper/`:

```sh
python3 scripts/build_rewrite_assets.py
python3 scripts/build_supplement_tables.py
python3 build_source.py
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build main.tex
bibtex build/main
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build main.tex
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build main.tex
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build supplement.tex
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build supplement.tex
```

These pdfLaTeX commands are documented but could not be executed here: pdfLaTeX and BibTeX are absent. Do not mistake the source's use of standard packages for verification of a successful build on an unavailable engine. The figure builder requires ReportLab; its packaged font is located through the package at runtime.

`scripts/check_rewrite.py` is a historical Pass C QA script tied to protected HEAD `69cd125d6e987ce4f02cb9c0f04d004d19952641`, its original evidence registry, and pre-review prose assertions. It is not a checker for the current reviewer revision and is excluded from current build/validation commands. Its scientific numerical checks remain unchanged.

For historical Pass C diagnostics only, the following commands require the original checkout, evidence registry, and manuscript from that revision; they are not a current validation workflow:

```sh
tectonic --only-cached --untrusted --keep-logs --keep-intermediates --outdir paper/build/pass_c_candidate paper/main.tex
tectonic --only-cached --untrusted --keep-logs --keep-intermediates --outdir paper/build/pass_c_candidate paper/supplement.tex
python3 paper/scripts/check_rewrite.py --pdf-dir build/pass_c_candidate
```

The historical QA command reports failed font QA on that revision. On macOS, Tectonic may need to run outside the sandbox for system-configuration initialization; `--only-cached --untrusted` remains required. No automatic resource fetching or custom replacement font mapping is an acceptable workaround.

## Evidence and presentation

Presentation assets read audited Pass A CSVs under `rewrite_plan/` and display stored counts, estimates, and intervals with presentation rounding. No-model cells read the explicit Success and Evaluable columns of `../research/baselines/no_model/RESULTS.md`; malformed, missing, duplicate, or inconsistent baseline rows stop generation before any output is written. They do not fit models, run tests, regenerate bootstrap draws, or alter evidence. Two figures and two tables appear in the main paper. The three unused legacy tables (`study1_table.tex`, `table2_external_paired.tex`, and `tableA2_descriptive_mcnemar.tex`) were restored to their historical versions after confirming that neither current manuscript includes them. `publication_data/`, the bibliography, research protocols, result artifacts, and Pass A files are unchanged.

The optional supplement retains scenarios, action paths, paired estimates and intervals, bootstrap details, descriptive marginal intervals, GitHub linkage and missing-arm sensitivity, Sheets incident provenance, Razorpay stopped prefixes, and marker/budget details. Replay--Regeneration significance tests are omitted from the revised manuscript tables; exact test outputs remain in stored historical evidence artifacts. The Pass A evidence report remains the historical source-path/hash registry, with the separate baseline record supplying its own audit provenance. Pass B audit receipts remain historical and unchanged. `scripts/check_rewrite.py` describes historical Pass C QA only and does not perform visual inspection.
