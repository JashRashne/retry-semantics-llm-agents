# Reader-first IEEE conference paper

`manuscript.md` is the editable main manuscript. `build_source.py` renders it into `main.tex`; `supplement/manuscript.md` renders into the separate `supplement.tex`. In both documents the first operative command is `\documentclass[conference]{IEEEtran}`. The title is unchanged. There are no custom font-family declarations, system-font file paths, geometry changes, font-size overrides, or spacing adjustments to shorten the paper.

## Pass C build status

**Font QA is blocked by the incomplete local TeX installation.** The custom `ieee_native_fonts.tex` mechanism has been removed. Figure text now embeds Bitstream Vera Sans from the ReportLab package, with no installed Arial requirement. The sources use standard IEEEtran and normal packages. A normal pdfLaTeX/TeX Live installation with IEEEtran and its standard Times, Helvetica, Courier, and math font resources is the intended portable workflow.

The available cached Tectonic installation uses XeLaTeX Unicode encoding and lacks Times/Courier font-family definitions. Offline builds silently substitute Latin Modern, including for bold, italic, and code text. Both candidate PDFs compile, but fail the font-substitution requirement; all candidate fonts are embedded. These candidates are **not publication-ready** and were not promoted over the accepted Pass B PDFs.

- `build/main.pdf` and `build/supplement.pdf`: retained Pass B artifacts, stale relative to the Pass C prose.
- `build/pass_c_candidate/main.pdf`: current-source diagnostic candidate, 8 pages including references.
- `build/pass_c_candidate/supplement.pdf`: diagnostic candidate, 6 pages.
- `rewrite_review/PASS_C_QA.json`: explicit failed font QA, successful protected-input/numerical checks.
- `rewrite_review/PASS_C_FINAL_AUDIT.md`: reader audit, changes, hashes, warnings, and resource blocker.

No TeX packages were downloaded or installed. The build must remain local/offline; no research-provider access is involved.

## Portable build commands

With an already available, complete standard pdfLaTeX installation, run from `paper/`:

```sh
python3 scripts/build_rewrite_assets.py
python3 build_source.py
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build main.tex
bibtex build/main
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build main.tex
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build main.tex
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build supplement.tex
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build supplement.tex
python3 scripts/check_rewrite.py
```

These pdfLaTeX commands are documented but could not be executed here: pdfLaTeX and BibTeX are absent. Do not mistake the source's use of standard packages for verification of a successful build on an unavailable engine. The figure builder requires ReportLab; its packaged font is located through the package at runtime.

To reproduce the **rejected** cached Tectonic diagnostics from the repository root:

```sh
tectonic --only-cached --untrusted --keep-logs --keep-intermediates --outdir paper/build/pass_c_candidate paper/main.tex
tectonic --only-cached --untrusted --keep-logs --keep-intermediates --outdir paper/build/pass_c_candidate paper/supplement.tex
python3 paper/scripts/check_rewrite.py --pdf-dir build/pass_c_candidate
```

The QA command deliberately exits unsuccessfully for font substitutions and records the reason. On macOS, Tectonic may need to run outside the sandbox for system-configuration initialization; `--only-cached --untrusted` remains required. No automatic resource fetching or custom replacement font mapping is an acceptable workaround.

## Evidence and presentation

Presentation assets read audited Pass A CSVs under `rewrite_plan/` and display stored counts, estimates, and intervals with presentation rounding. They do not fit models, run tests, regenerate bootstrap draws, or alter evidence. Two figures and two tables appear in the main paper. Historical unused assets remain unchanged. `publication_data/`, the bibliography, research protocols, result artifacts, and Pass A files are unchanged.

The optional supplement retains scenarios, action paths, exact test outputs, bootstrap details, descriptive marginal intervals, GitHub linkage and missing-arm sensitivity, Sheets incident provenance, Razorpay stopped prefixes, and marker/budget details. The Pass A evidence report remains the source-path/hash registry. Pass B audit receipts remain historical and unchanged. `scripts/check_rewrite.py` now accepts a PDF directory and receipt path, compares stored values without reanalysis, rejects stale abstract text, checks embedded fonts and substitutions, and writes Pass C QA by default. It does not perform visual inspection.
