"""Deterministic analysis of Study-2 cross-provider paper collection evidence.

Processes run directories or projection records from GitHub, Google Sheets,
and Razorpay paper runs. Computes matched-pair tables, McNemar tests,
Newcombe Method 10 confidence intervals, interaction bootstraps, outcome
distributions, and cross-provider summaries.

When collection is pending or in progress, produces structured templates
with explicit placeholders without fabricating any observations.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from retry_semantics.experiment.analysis_statistics import (
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    PairedTable,
    exact_mcnemar,
    interaction_bootstrap,
    newcombe_paired_method10,
    rate,
    wilson_95,
)
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

PROVIDERS = ("github", "sheets", "razorpay")
WORLDS = ("H0", "H1")
POLICIES = ("EXACT_REPLAY", "LLM_REGENERATION")
SCHEDULED_FAMILIES_PER_PROVIDER = 64
SCHEDULED_ARMS_PER_PROVIDER = 256  # 64 families * 4 arms


@dataclass(frozen=True, slots=True)
class ArmResult:
    """Standardized projection of a single Study-2 arm."""

    provider: str
    family_id: str
    arm_id: str
    hidden_world: str  # H0 or H1
    policy: str  # EXACT_REPLAY or LLM_REGENERATION
    status: str  # SUCCESS, FAILURE, INCONCLUSIVE, INFRASTRUCTURE_FAILURE, PENDING
    state_correct: int | None  # 1, 0, or None if inconclusive/pending
    reason: str
    recovery_terminal: str | None = None
    tool_action_attempts: int = 0
    recovery_tool_calls_attempted: int = 0
    model_calls: int = 0
    duplicate_count: int = 0
    missing_count: int = 0
    unintended_count: int = 0

    @property
    def is_evaluable(self) -> bool:
        return self.state_correct is not None

    @property
    def outcome_label(self) -> str:
        if self.state_correct == 1:
            return "STATE_CORRECT"
        if self.state_correct == 0:
            if self.duplicate_count > 0:
                return "DUPLICATE_MUTATION"
            if self.missing_count > 0:
                return "MISSING_MUTATION"
            if self.unintended_count > 0:
                return "UNINTENDED_MUTATION"
            return "INCORRECT_STATE"
        if self.status == "INCONCLUSIVE":
            return "INCONCLUSIVE"
        if self.status == "INFRASTRUCTURE_FAILURE":
            return "INFRASTRUCTURE_FAILURE"
        return "PENDING"


@dataclass(frozen=True)
class ProviderAnalysis:
    """Comprehensive analysis for a single Study-2 provider."""

    provider: str
    total_scheduled_families: int
    total_scheduled_arms: int
    completed_arms: int
    evaluable_arms: int
    inconclusive_arms: int
    infrastructure_failure_arms: int
    # Primary counts are restricted to complete evaluable family/world pairs.
    h0_replay_correct: int
    h0_replay_total: int
    h0_regen_correct: int
    h0_regen_total: int
    h1_replay_correct: int
    h1_replay_total: int
    h1_regen_correct: int
    h1_regen_total: int
    # Failure taxonomy
    duplicate_arms: int
    missing_arms: int
    unintended_arms: int
    # Paired inference H0
    h0_paired_n: int
    h0_replay_rate: float | None
    h0_regen_rate: float | None
    h0_delta: float | None
    h0_ci_lower: float | None
    h0_ci_upper: float | None
    h0_mcnemar_p: float | None
    # Paired inference H1
    h1_paired_n: int
    h1_replay_rate: float | None
    h1_regen_rate: float | None
    h1_delta: float | None
    h1_ci_lower: float | None
    h1_ci_upper: float | None
    h1_mcnemar_p: float | None
    # Interaction
    interaction_n: int
    interaction_delta: float | None
    interaction_ci_lower: float | None
    interaction_ci_upper: float | None
    # Arm data
    arms: tuple[ArmResult, ...] = field(default_factory=tuple)
    is_placeholder: bool = False
    descriptive_all_evaluable_arm_counts: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)


def extract_arm_result_from_dict(
    provider: str,
    arm_dict: dict[str, Any],
    projection_data: dict[str, Any],
    family_id: str,
) -> ArmResult:
    """Extract standard ArmResult from an arm manifest entry and arm-projection event."""
    proj = projection_data["projection"]
    status = proj["status"]
    state_correct = proj["state_correct"]
    reason = proj["reason"]
    recovery_terminal = projection_data.get("recovery_terminal")

    # Counts
    # Frozen evaluators emit exact defect tokens, sometimes comma joined.
    defects = set(reason.split(",")) if status == "FAILURE" else set()
    vocabulary = ({"DUPLICATE_EFFECT", "MISSING_EFFECT", "WRONG_MUTATION"}
                  if provider in ("github", "razorpay") else
                  {"DUPLICATE", "MISSING", "EXTRA_UNINTENDED_MUTATION"})
    if status == "FAILURE" and not defects <= vocabulary:
        raise ValueError("provider projection uses foreign defect token")
    dup = int(bool(defects & vocabulary & {"DUPLICATE_EFFECT", "DUPLICATE"}))
    missing = int(bool(defects & vocabulary & {"MISSING_EFFECT", "MISSING"}))
    unintended = int(bool(defects & vocabulary & {"WRONG_MUTATION", "EXTRA_UNINTENDED_MUTATION"}))

    return ArmResult(
        provider=provider,
        family_id=family_id,
        arm_id=arm_dict.get("arm_id", projection_data.get("arm_id", "")),
        hidden_world=arm_dict.get("hidden_world", ""),
        policy=arm_dict.get("policy", ""),
        status=status,
        state_correct=state_correct,
        reason=reason,
        recovery_terminal=recovery_terminal,
        tool_action_attempts=int(projection_data.get("tool_action_attempt_count", 0)),
        recovery_tool_calls_attempted=int(projection_data.get("recovery_tool_calls_attempted", 0)),
        model_calls=int(projection_data.get("model_calls", 0)),
        duplicate_count=dup,
        missing_count=missing,
        unintended_count=unintended,
    )


def load_run_projections(
    run_dir: Path,
    manifest: dict[str, Any],
    provider: str,
    *,
    expected_families: int | None = None,
) -> list[ArmResult]:
    """Load a complete scheduled run; reject partial or corrupt publication evidence."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider}")
    if not run_dir.is_dir():
        raise ValueError(f"missing run directory: {run_dir}")
    if list(run_dir.glob("run-stopped-*.json")) or list(run_dir.rglob("run-abort.json")):
        raise ValueError("stopped or aborted primary run cannot be published as a complete result")
    try:
        authorization = json.loads((run_dir / "run-authorization.json").read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("missing or malformed run-authorization evidence") from exc
    if (type(authorization) is not dict or authorization.get("provider") != provider
            or authorization.get("study2_paper_observations_before_run") != 0
            or authorization.get("manifest_sha256") != sha256_hex(canonical_json_bytes(manifest))
            or type(authorization.get("runtime_sha256")) is not dict):
        raise ValueError("invalid run-authorization evidence")
    families = manifest.get("families")
    if type(families) is not list or not families:
        raise ValueError("manifest has no families")
    if expected_families is not None and len(families) != expected_families:
        raise ValueError(f"expected {expected_families} scheduled families, found {len(families)}")
    scheduled: dict[str, tuple[dict[str, Any], str]] = {}
    family_ids: set[str] = set()
    expected_cells = {(world, policy) for world in WORLDS for policy in POLICIES}
    for family in families:
        if type(family) is not dict or type(family.get("family_id")) is not str:
            raise ValueError("invalid manifest family")
        family_id = family["family_id"]
        if not family_id or family_id in family_ids:
            raise ValueError(f"duplicate/empty manifest family ID: {family_id}")
        family_ids.add(family_id)
        arms = family.get("arms")
        if type(arms) is not list or len(arms) != 4:
            raise ValueError(f"family {family_id} must schedule four arms")
        cells: set[tuple[str, str]] = set()
        for arm in arms:
            if type(arm) is not dict or type(arm.get("arm_id")) is not str or not arm["arm_id"]:
                raise ValueError(f"invalid manifest arm in {family_id}")
            cell = (arm.get("hidden_world"), arm.get("policy"))
            if cell not in expected_cells or cell in cells:
                raise ValueError(f"invalid or duplicate manifest cell in {family_id}: {cell}")
            if arm["arm_id"] in scheduled:
                raise ValueError(f"duplicate manifest arm ID: {arm['arm_id']}")
            if arm.get("family_id", family_id) != family_id:
                raise ValueError(f"manifest arm family mismatch: {arm['arm_id']}")
            cells.add(cell)
            scheduled[arm["arm_id"]] = (arm, family_id)
        if cells != expected_cells:
            raise ValueError(f"incomplete manifest family: {family_id}")

    results: list[ArmResult] = []
    seen: set[str] = set()
    arm_dirs = sorted(p for p in run_dir.iterdir() if p.is_dir())
    for arm_dir in arm_dirs:
        proj_file = arm_dir / "arm-projection.json"
        if not proj_file.exists():
            raise ValueError(f"missing projection: {proj_file}")
        try:
            proj_data = json.loads(proj_file.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"unreadable projection: {proj_file}") from exc
        if type(proj_data) is not dict:
            raise ValueError(f"invalid projection object: {proj_file}")
        arm_id = proj_data.get("arm_id")
        if type(arm_id) is not str or arm_id not in scheduled:
            raise ValueError(f"unknown projection arm ID: {arm_id}")
        if arm_id in seen:
            raise ValueError(f"duplicate projection arm ID: {arm_id}")
        proj = proj_data.get("projection")
        if type(proj) is not dict:
            raise ValueError(f"missing projection verdict: {arm_id}")
        status, correct, reason = proj.get("status"), proj.get("state_correct"), proj.get("reason")
        if (status not in ("SUCCESS", "FAILURE", "INCONCLUSIVE", "INFRASTRUCTURE_FAILURE")
                or type(correct) not in (int, type(None)) or correct not in (0, 1, None)
                or type(reason) is not str
                or (status == "SUCCESS") != (correct == 1)
                or (status == "FAILURE") != (correct == 0)
                or (status in ("INCONCLUSIVE", "INFRASTRUCTURE_FAILURE")) != (correct is None)):
            raise ValueError(f"contradictory/invalid projection verdict: {arm_id}")
        defect_tokens = reason.split(",")
        success_reason = "EXACTLY_ONE" if provider == "sheets" else "CORRECT"
        failure_reasons = ({"DUPLICATE", "MISSING", "EXTRA_UNINTENDED_MUTATION"}
                           if provider == "sheets" else
                           {"DUPLICATE_EFFECT", "MISSING_EFFECT", "WRONG_MUTATION"})
        if ((status == "SUCCESS" and reason != success_reason)
                or (status == "FAILURE" and (
                    not defect_tokens or len(defect_tokens) != len(set(defect_tokens))
                    or not set(defect_tokens) <= failure_reasons))):
            raise ValueError(f"unknown or contradictory frozen projection reason: {arm_id}")
        arm, family_id = scheduled[arm_id]
        seen.add(arm_id)
        results.append(extract_arm_result_from_dict(provider, arm, proj_data, family_id))
    if seen != set(scheduled):
        raise ValueError(f"incomplete run evidence: {len(seen)}/{len(scheduled)} projections; stopped or aborted arms cannot be assigned outcomes")
    return results


def analyze_arm_results(
    provider: str,
    arms: Sequence[ArmResult],
    total_families: int = SCHEDULED_FAMILIES_PER_PROVIDER,
) -> ProviderAnalysis:
    """Compute complete statistical summary for a provider from arm results."""
    total_scheduled_arms = total_families * 4
    if not arms:
        return create_placeholder_provider_analysis(provider, total_families)
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider}")

    # Group by family
    family_arms: dict[str, dict[tuple[str, str], ArmResult]] = {}
    arm_ids: set[str] = set()
    for arm in arms:
        if (arm.provider != provider or arm.hidden_world not in WORLDS
                or arm.policy not in POLICIES or type(arm.state_correct) not in (int, type(None))
                or arm.state_correct not in (0, 1, None)):
            raise ValueError(f"invalid analysis arm: {arm.arm_id}")
        if arm.arm_id in arm_ids:
            raise ValueError(f"duplicate analysis arm ID: {arm.arm_id}")
        arm_ids.add(arm.arm_id)
        fam = arm.family_id
        if fam not in family_arms:
            family_arms[fam] = {}
        cell = (arm.hidden_world, arm.policy)
        if cell in family_arms[fam]:
            raise ValueError(f"duplicate family/world/policy cell: {fam} {cell}")
        family_arms[fam][cell] = arm

    completed_arms = len(arms)
    evaluable_arms = sum(1 for a in arms if a.is_evaluable)
    inconclusive_arms = sum(1 for a in arms if a.status == "INCONCLUSIVE")
    infra_failure_arms = sum(1 for a in arms if a.status == "INFRASTRUCTURE_FAILURE")

    # Descriptive all-evaluable-arm counts; primary counts below use paired families.
    def cell_counts(world: str, pol: str) -> tuple[int, int]:
        relevant = [a for a in arms if a.hidden_world == world and a.policy == pol and a.is_evaluable]
        correct = sum(1 for a in relevant if a.state_correct == 1)
        return correct, len(relevant)

    descriptive = {
        world: {policy: dict(zip(("correct", "total"), cell_counts(world, policy)))
                for policy in POLICIES} for world in WORLDS
    }

    dup_count = sum(a.duplicate_count > 0 for a in arms)
    miss_count = sum(a.missing_count > 0 for a in arms)
    unint_count = sum(a.unintended_count > 0 for a in arms)

    # Paired comparisons
    def paired_stats(world: str) -> tuple[int, int, int, float | None, float | None, float | None, float | None, float | None, float | None]:
        pairs = []
        for fam_dict in family_arms.values():
            rep = fam_dict.get((world, "EXACT_REPLAY"))
            reg = fam_dict.get((world, "LLM_REGENERATION"))
            if rep and reg and rep.is_evaluable and reg.is_evaluable:
                pairs.append((rep.state_correct, reg.state_correct))

        if not pairs:
            return 0, 0, 0, None, None, None, None, None, None

        table = PairedTable.from_pairs(pairs)
        n = table.n
        rep_correct = table.n11 + table.n10
        reg_correct = table.n11 + table.n01
        rep_rate = rep_correct / n
        reg_rate = reg_correct / n
        delta = rep_rate - reg_rate
        ci = newcombe_paired_method10(table)
        p_val = exact_mcnemar(table)
        ci_lower = ci[0] if ci else None
        ci_upper = ci[1] if ci else None
        return n, rep_correct, reg_correct, rep_rate, reg_rate, delta, ci_lower, ci_upper, p_val

    h0_n, h0_rep_c, h0_reg_c, h0_rep_r, h0_reg_r, h0_d, h0_cil, h0_ciu, h0_p = paired_stats("H0")
    h1_n, h1_rep_c, h1_reg_c, h1_rep_r, h1_reg_r, h1_d, h1_cil, h1_ciu, h1_p = paired_stats("H1")

    # Interaction
    contributions = []
    for fam_dict in family_arms.values():
        h0_rep = fam_dict.get(("H0", "EXACT_REPLAY"))
        h0_reg = fam_dict.get(("H0", "LLM_REGENERATION"))
        h1_rep = fam_dict.get(("H1", "EXACT_REPLAY"))
        h1_reg = fam_dict.get(("H1", "LLM_REGENERATION"))
        if (
            h0_rep and h0_reg and h1_rep and h1_reg
            and h0_rep.is_evaluable and h0_reg.is_evaluable
            and h1_rep.is_evaluable and h1_reg.is_evaluable
        ):
            # Contribution: (H1_rep - H1_reg) - (H0_rep - H0_reg)
            c = (h1_rep.state_correct - h1_reg.state_correct) - (h0_rep.state_correct - h0_reg.state_correct)
            contributions.append(c)

    if contributions:
        boot_res = interaction_bootstrap(contributions)
        inter_n = boot_res["N"]
        inter_d = boot_res["estimate"]
        inter_cil, inter_ciu = boot_res["percentile_95_ci"] if boot_res["percentile_95_ci"] else (None, None)
    else:
        inter_n = 0
        inter_d = None
        inter_cil, inter_ciu = None, None

    return ProviderAnalysis(
        provider=provider,
        total_scheduled_families=total_families,
        total_scheduled_arms=total_scheduled_arms,
        completed_arms=completed_arms,
        evaluable_arms=evaluable_arms,
        inconclusive_arms=inconclusive_arms,
        infrastructure_failure_arms=infra_failure_arms,
        h0_replay_correct=h0_rep_c,
        h0_replay_total=h0_n,
        h0_regen_correct=h0_reg_c,
        h0_regen_total=h0_n,
        h1_replay_correct=h1_rep_c,
        h1_replay_total=h1_n,
        h1_regen_correct=h1_reg_c,
        h1_regen_total=h1_n,
        duplicate_arms=dup_count,
        missing_arms=miss_count,
        unintended_arms=unint_count,
        h0_paired_n=h0_n,
        h0_replay_rate=h0_rep_r,
        h0_regen_rate=h0_reg_r,
        h0_delta=h0_d,
        h0_ci_lower=h0_cil,
        h0_ci_upper=h0_ciu,
        h0_mcnemar_p=h0_p,
        h1_paired_n=h1_n,
        h1_replay_rate=h1_rep_r,
        h1_regen_rate=h1_reg_r,
        h1_delta=h1_d,
        h1_ci_lower=h1_cil,
        h1_ci_upper=h1_ciu,
        h1_mcnemar_p=h1_p,
        interaction_n=inter_n,
        interaction_delta=inter_d,
        interaction_ci_lower=inter_cil,
        interaction_ci_upper=inter_ciu,
        arms=tuple(arms),
        is_placeholder=False,
        descriptive_all_evaluable_arm_counts=descriptive,
    )


def create_placeholder_provider_analysis(
    provider: str,
    total_families: int = SCHEDULED_FAMILIES_PER_PROVIDER,
) -> ProviderAnalysis:
    """Create a structured pending/placeholder analysis for a provider."""
    total_arms = total_families * 4
    return ProviderAnalysis(
        provider=provider,
        total_scheduled_families=total_families,
        total_scheduled_arms=total_arms,
        completed_arms=0,
        evaluable_arms=0,
        inconclusive_arms=0,
        infrastructure_failure_arms=0,
        h0_replay_correct=0,
        h0_replay_total=total_families,
        h0_regen_correct=0,
        h0_regen_total=total_families,
        h1_replay_correct=0,
        h1_replay_total=total_families,
        h1_regen_correct=0,
        h1_regen_total=total_families,
        duplicate_arms=0,
        missing_arms=0,
        unintended_arms=0,
        h0_paired_n=total_families,
        h0_replay_rate=None,
        h0_regen_rate=None,
        h0_delta=None,
        h0_ci_lower=None,
        h0_ci_upper=None,
        h0_mcnemar_p=None,
        h1_paired_n=total_families,
        h1_replay_rate=None,
        h1_regen_rate=None,
        h1_delta=None,
        h1_ci_lower=None,
        h1_ci_upper=None,
        h1_mcnemar_p=None,
        interaction_n=total_families,
        interaction_delta=None,
        interaction_ci_lower=None,
        interaction_ci_upper=None,
        arms=(),
        is_placeholder=True,
    )


def format_rate(correct: int, total: int, is_placeholder: bool = False) -> str:
    if is_placeholder:
        return "[STUDY2-PENDING]"
    if total == 0:
        return "NA (0 paired)"
    pct = 100.0 * correct / total
    return f"{correct}/{total} ({pct:.1f}%)"


def format_ci(lower: float | None, upper: float | None, is_placeholder: bool = False) -> str:
    if is_placeholder:
        return "[STUDY2-PENDING]"
    if lower is None or upper is None:
        return "NA"
    return f"[{lower * 100:+.2f}%, {upper * 100:+.2f}%]"


def format_p(val: float | None, is_placeholder: bool = False) -> str:
    if is_placeholder:
        return "[STUDY2-PENDING]"
    if val is None:
        return "NA"
    if val < 1e-4:
        return f"{val:.3e}"
    return f"{val:.4f}"


def format_delta(val: float | None, is_placeholder: bool = False) -> str:
    if is_placeholder:
        return "[STUDY2-PENDING]"
    if val is None:
        return "NA"
    return f"{val * 100:+.2f}%"


def generate_markdown_summary_table(analyses: dict[str, ProviderAnalysis]) -> str:
    """Generate publication-ready Markdown table for Study-2 cross-provider results."""
    lines = [
        "| Provider | World | N Matched | Exact Replay | LLM Regeneration | Δ (Replay − Regen) | 95% CI (Newcombe) | McNemar p |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for p_name in ("github", "sheets", "razorpay"):
        a = analyses.get(p_name, create_placeholder_provider_analysis(p_name))
        display_name = {"github": "GitHub Issues", "sheets": "Google Sheets", "razorpay": "Razorpay Orders"}.get(p_name, p_name)

        # H0 row
        h0_rep = format_rate(a.h0_replay_correct, a.h0_replay_total, a.is_placeholder)
        h0_reg = format_rate(a.h0_regen_correct, a.h0_regen_total, a.is_placeholder)
        h0_d = format_delta(a.h0_delta, a.is_placeholder)
        h0_ci = format_ci(a.h0_ci_lower, a.h0_ci_upper, a.is_placeholder)
        h0_p = format_p(a.h0_mcnemar_p, a.is_placeholder)
        lines.append(f"| {display_name} | H0 (NOT_EXECUTED) | {'[STUDY2-PENDING]' if a.is_placeholder else a.h0_paired_n} | {h0_rep} | {h0_reg} | {h0_d} | {h0_ci} | {h0_p} |")

        # H1 row
        h1_rep = format_rate(a.h1_replay_correct, a.h1_replay_total, a.is_placeholder)
        h1_reg = format_rate(a.h1_regen_correct, a.h1_regen_total, a.is_placeholder)
        h1_d = format_delta(a.h1_delta, a.is_placeholder)
        h1_ci = format_ci(a.h1_ci_lower, a.h1_ci_upper, a.is_placeholder)
        h1_p = format_p(a.h1_mcnemar_p, a.is_placeholder)
        lines.append(f"| {display_name} | H1 (EXECUTED_ACK_LOST) | {'[STUDY2-PENDING]' if a.is_placeholder else a.h1_paired_n} | {h1_rep} | {h1_reg} | {h1_d} | {h1_ci} | {h1_p} |")

    return "\n".join(lines)


def generate_latex_summary_table(analyses: dict[str, ProviderAnalysis]) -> str:
    """Generate LaTeX tabular fragment for the Study-2 summary table."""
    rows = []
    for p_name in ("github", "sheets", "razorpay"):
        a = analyses.get(p_name, create_placeholder_provider_analysis(p_name))
        display_name = {"github": "GitHub Issues", "sheets": "Google Sheets", "razorpay": "Razorpay Orders"}.get(p_name, p_name)

        h0_rep = format_rate(a.h0_replay_correct, a.h0_replay_total, a.is_placeholder).replace("%", "\\%")
        h0_reg = format_rate(a.h0_regen_correct, a.h0_regen_total, a.is_placeholder).replace("%", "\\%")
        h0_d = format_delta(a.h0_delta, a.is_placeholder).replace("%", "\\%")
        h0_ci = format_ci(a.h0_ci_lower, a.h0_ci_upper, a.is_placeholder).replace("%", "\\%")
        h0_p = format_p(a.h0_mcnemar_p, a.is_placeholder)

        h1_rep = format_rate(a.h1_replay_correct, a.h1_replay_total, a.is_placeholder).replace("%", "\\%")
        h1_reg = format_rate(a.h1_regen_correct, a.h1_regen_total, a.is_placeholder).replace("%", "\\%")
        h1_d = format_delta(a.h1_delta, a.is_placeholder).replace("%", "\\%")
        h1_ci = format_ci(a.h1_ci_lower, a.h1_ci_upper, a.is_placeholder).replace("%", "\\%")
        h1_p = format_p(a.h1_mcnemar_p, a.is_placeholder)

        rows.append(f"\\multirow{{2}}{{*}}{{{display_name}}} & $H_0$ & {'[STUDY2-PENDING]' if a.is_placeholder else a.h0_paired_n} & {h0_rep} & {h0_reg} & {h0_d} & {h0_ci} & {h0_p} \\\\")
        rows.append(f" & $H_1$ & {'[STUDY2-PENDING]' if a.is_placeholder else a.h1_paired_n} & {h1_rep} & {h1_reg} & {h1_d} & {h1_ci} & {h1_p} \\\\ \\hline")

    latex = (
        "\\begin{table*}[t]\n"
        "\\centering\n"
        "\\small\n"
        "\\caption{Study 2 Cross-Provider External Validation: State Correctness Under Ambiguous Outcomes}\n"
        "\\label{tab:study2-results}\n"
        "\\begin{tabular}{llcccccc}\n"
        "\\hline\n"
        "\\textbf{Provider} & \\textbf{World} & \\textbf{N} & \\textbf{Exact Replay} & \\textbf{LLM Regen.} & $\\Delta$ (Replay - Regen) & \\textbf{95\\% CI} & \\textbf{McNemar $p$} \\\\\n"
        "\\hline\n"
        + "\n".join(rows) + "\n"
        "\\hline\n"
        "\\end{tabular}\n"
        "\\end{table*}\n"
    )
    return latex


def serialize_analysis_to_dict(analyses: dict[str, ProviderAnalysis]) -> dict[str, Any]:
    """Produce machine-readable JSON structure of the entire Study-2 analysis."""
    out: dict[str, Any] = {
        "schema": "study2-cross-provider-analysis-v1",
        "providers": {},
        "cross_provider_aggregate": {
            "total_scheduled_families": sum(a.total_scheduled_families for a in analyses.values()),
            "total_scheduled_arms": sum(a.total_scheduled_arms for a in analyses.values()),
            "total_completed_arms": sum(a.completed_arms for a in analyses.values()),
            "total_evaluable_arms": sum(a.evaluable_arms for a in analyses.values()),
            "total_inconclusive_arms": sum(a.inconclusive_arms for a in analyses.values()),
            "total_infrastructure_failures": sum(a.infrastructure_failure_arms for a in analyses.values()),
        },
    }

    for p_name, a in analyses.items():
        out["providers"][p_name] = {
            "is_placeholder": a.is_placeholder,
            "scheduled_families": a.total_scheduled_families,
            "scheduled_arms": a.total_scheduled_arms,
            "completed_arms": a.completed_arms,
            "evaluable_arms": a.evaluable_arms,
            "inconclusive_arms": a.inconclusive_arms,
            "infrastructure_failure_arms": a.infrastructure_failure_arms,
            "h0": {
                "replay": {"correct": None if a.is_placeholder else a.h0_replay_correct, "total": None if a.is_placeholder else a.h0_replay_total, "rate": a.h0_replay_rate},
                "regeneration": {"correct": None if a.is_placeholder else a.h0_regen_correct, "total": None if a.is_placeholder else a.h0_regen_total, "rate": a.h0_regen_rate},
                "paired_n": None if a.is_placeholder else a.h0_paired_n,
                "delta": a.h0_delta,
                "ci_95": [a.h0_ci_lower, a.h0_ci_upper],
                "mcnemar_p": a.h0_mcnemar_p,
            },
            "h1": {
                "replay": {"correct": None if a.is_placeholder else a.h1_replay_correct, "total": None if a.is_placeholder else a.h1_replay_total, "rate": a.h1_replay_rate},
                "regeneration": {"correct": None if a.is_placeholder else a.h1_regen_correct, "total": None if a.is_placeholder else a.h1_regen_total, "rate": a.h1_regen_rate},
                "paired_n": None if a.is_placeholder else a.h1_paired_n,
                "delta": a.h1_delta,
                "ci_95": [a.h1_ci_lower, a.h1_ci_upper],
                "mcnemar_p": a.h1_mcnemar_p,
            },
            "interaction": {
                "n": None if a.is_placeholder else a.interaction_n,
                "delta_h1_minus_h0": a.interaction_delta,
                "bootstrap_ci_95": [a.interaction_ci_lower, a.interaction_ci_upper],
            },
            "failure_taxonomy": {
                "duplicate_arms": None if a.is_placeholder else a.duplicate_arms,
                "missing_arms": None if a.is_placeholder else a.missing_arms,
                "unintended_arms": None if a.is_placeholder else a.unintended_arms,
            },
            "descriptive_all_evaluable_arm_counts": a.descriptive_all_evaluable_arm_counts,
        }
    return out


def export_analysis_csv(analyses: dict[str, ProviderAnalysis], output_path: Path) -> None:
    """Export machine-readable summary CSV."""
    fieldnames = [
        "provider",
        "world",
        "paired_n",
        "replay_correct",
        "replay_total",
        "replay_rate",
        "regen_correct",
        "regen_total",
        "regen_rate",
        "delta_replay_minus_regen",
        "ci_lower",
        "ci_upper",
        "mcnemar_p",
        "interaction_delta",
        "interaction_ci_lower",
        "interaction_ci_upper",
        "is_placeholder",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p_name, a in analyses.items():
            for world in ("H0", "H1"):
                if world == "H0":
                    rep_c, rep_t, rep_r = a.h0_replay_correct, a.h0_replay_total, a.h0_replay_rate
                    reg_c, reg_t, reg_r = a.h0_regen_correct, a.h0_regen_total, a.h0_regen_rate
                    n, d, cil, ciu, p = a.h0_paired_n, a.h0_delta, a.h0_ci_lower, a.h0_ci_upper, a.h0_mcnemar_p
                    inter_d, inter_cil, inter_ciu = None, None, None
                else:
                    rep_c, rep_t, rep_r = a.h1_replay_correct, a.h1_replay_total, a.h1_replay_rate
                    reg_c, reg_t, reg_r = a.h1_regen_correct, a.h1_regen_total, a.h1_regen_rate
                    n, d, cil, ciu, p = a.h1_paired_n, a.h1_delta, a.h1_ci_lower, a.h1_ci_upper, a.h1_mcnemar_p
                    inter_d, inter_cil, inter_ciu = a.interaction_delta, a.interaction_ci_lower, a.interaction_ci_upper

                writer.writerow({
                    "provider": p_name,
                    "world": world,
                    "paired_n": "" if a.is_placeholder else n,
                    "replay_correct": "" if a.is_placeholder else rep_c,
                    "replay_total": "" if a.is_placeholder else rep_t,
                    "replay_rate": rep_r if rep_r is not None else "",
                    "regen_correct": "" if a.is_placeholder else reg_c,
                    "regen_total": "" if a.is_placeholder else reg_t,
                    "regen_rate": reg_r if reg_r is not None else "",
                    "delta_replay_minus_regen": d if d is not None else "",
                    "ci_lower": cil if cil is not None else "",
                    "ci_upper": ciu if ciu is not None else "",
                    "mcnemar_p": p if p is not None else "",
                    "interaction_delta": inter_d if inter_d is not None else "",
                    "interaction_ci_lower": inter_cil if inter_cil is not None else "",
                    "interaction_ci_upper": inter_ciu if inter_ciu is not None else "",
                    "is_placeholder": a.is_placeholder,
                })
