#!/usr/bin/env python3
"""Run Study-2 cross-provider paper analysis and output tables and summaries.

Can analyze completed provider run directories or generate publication-ready
templates with explicit placeholders when runs are pending.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from retry_semantics.study2.github_paper_manifest import load_github_paper_manifest
from retry_semantics.study2.provider_paper_analysis import (
    analyze_arm_results,
    create_placeholder_provider_analysis,
    export_analysis_csv,
    generate_latex_summary_table,
    generate_markdown_summary_table,
    load_run_projections,
    serialize_analysis_to_dict,
)
from retry_semantics.study2.razorpay_paper_manifest import load_razorpay_paper_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-run-dir", type=Path, help="Path to completed GitHub paper run directory")
    parser.add_argument("--sheets-run-dir", type=Path, help="Path to completed Google Sheets paper run directory")
    parser.add_argument("--razorpay-run-dir", type=Path, help="Path to completed Razorpay paper run directory")
    parser.add_argument("--output-dir", type=Path, default=Path("research/results/study2"), help="Output directory for analysis artifacts")
    parser.add_argument("--placeholder-only", action="store_true", help="Generate explicit placeholder summaries without looking for run data")

    args = parser.parse_args()
    if not args.placeholder_only:
        for provider, path in (("GitHub", args.github_run_dir),
                               ("Google Sheets", args.sheets_run_dir),
                               ("Razorpay", args.razorpay_run_dir)):
            if path is not None and not path.is_dir():
                parser.error(f"{provider} run directory does not exist: {path}")
    output_dir = args.output_dir

    analyses = {}

    # GitHub
    if not args.placeholder_only and args.github_run_dir and args.github_run_dir.exists():
        gh_manifest = load_github_paper_manifest().as_json()
        gh_arms = load_run_projections(args.github_run_dir, gh_manifest, "github", expected_families=64)
        analyses["github"] = analyze_arm_results("github", gh_arms)
        print(f"Loaded {len(gh_arms)} GitHub arms.")
    else:
        analyses["github"] = create_placeholder_provider_analysis("github")
        print("GitHub: generated explicit placeholder analysis.")

    # Sheets
    if not args.placeholder_only and args.sheets_run_dir and args.sheets_run_dir.exists():
        # Load sheets manifest
        from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest as load_sheets_manifest
        sh_manifest = load_sheets_manifest()
        sh_arms = load_run_projections(args.sheets_run_dir, sh_manifest, "sheets", expected_families=64)
        analyses["sheets"] = analyze_arm_results("sheets", sh_arms)
        print(f"Loaded {len(sh_arms)} Google Sheets arms.")
    else:
        analyses["sheets"] = create_placeholder_provider_analysis("sheets")
        print("Google Sheets: generated explicit placeholder analysis.")

    # Razorpay
    if not args.placeholder_only and args.razorpay_run_dir and args.razorpay_run_dir.exists():
        rz_manifest = load_razorpay_paper_manifest()
        rz_arms = load_run_projections(args.razorpay_run_dir, rz_manifest, "razorpay", expected_families=64)
        analyses["razorpay"] = analyze_arm_results("razorpay", rz_arms)
        print(f"Loaded {len(rz_arms)} Razorpay arms.")
    else:
        analyses["razorpay"] = create_placeholder_provider_analysis("razorpay")
        print("Razorpay: generated explicit placeholder analysis.")

    # Write only after every supplied run has passed fail-closed validation.
    output_dir.mkdir(parents=True, exist_ok=True)
    md_table = generate_markdown_summary_table(analyses)
    latex_table = generate_latex_summary_table(analyses)
    dict_summary = serialize_analysis_to_dict(analyses)

    (output_dir / "study2_summary_table.md").write_text(md_table + "\n", encoding="utf-8")
    (output_dir / "study2_summary_table.tex").write_text(latex_table, encoding="utf-8")
    (output_dir / "study2_analysis_summary.json").write_text(
        json.dumps(dict_summary, indent=2) + "\n", encoding="utf-8"
    )
    export_analysis_csv(analyses, output_dir / "study2_analysis_summary.csv")

    print(f"\nSaved analysis artifacts to {output_dir}:")
    print(f" - {output_dir / 'study2_summary_table.md'}")
    print(f" - {output_dir / 'study2_summary_table.tex'}")
    print(f" - {output_dir / 'study2_analysis_summary.json'}")
    print(f" - {output_dir / 'study2_analysis_summary.csv'}")

    print("\nSummary Table:")
    print(md_table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
