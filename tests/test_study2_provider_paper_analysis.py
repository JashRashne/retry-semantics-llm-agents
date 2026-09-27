"""Tests for Study-2 cross-provider paper analysis module and CLI pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

from retry_semantics.study2.provider_paper_analysis import (
    ArmResult,
    ProviderAnalysis,
    analyze_arm_results,
    create_placeholder_provider_analysis,
    export_analysis_csv,
    format_ci,
    format_delta,
    format_p,
    format_rate,
    generate_latex_summary_table,
    generate_markdown_summary_table,
    load_run_projections,
    serialize_analysis_to_dict,
)


def test_create_placeholder_provider_analysis():
    p = create_placeholder_provider_analysis("github", total_families=64)
    assert p.provider == "github"
    assert p.total_scheduled_families == 64
    assert p.total_scheduled_arms == 256
    assert p.completed_arms == 0
    assert p.evaluable_arms == 0
    assert p.is_placeholder is True
    assert p.h0_replay_rate is None
    assert p.h1_mcnemar_p is None
    assert p.interaction_delta is None


def test_format_helpers_with_placeholders():
    assert format_rate(10, 64, is_placeholder=True) == "[STUDY2-PENDING]"
    assert format_ci(-0.1, 0.2, is_placeholder=True) == "[STUDY2-PENDING]"
    assert format_p(0.001, is_placeholder=True) == "[STUDY2-PENDING]"
    assert format_delta(-0.5, is_placeholder=True) == "[STUDY2-PENDING]"

    assert format_rate(32, 64, is_placeholder=False) == "32/64 (50.0%)"
    assert format_ci(-0.123, 0.456, is_placeholder=False) == "[-12.30%, +45.60%]"
    assert format_p(0.00005, is_placeholder=False) == "5.000e-05"
    assert format_p(0.0432, is_placeholder=False) == "0.0432"
    assert format_delta(-0.25, is_placeholder=False) == "-25.00%"
    assert format_rate(0, 0) == "NA (0 paired)"
    assert format_ci(None, None) == "NA"
    assert format_p(None) == "NA"
    assert format_delta(None) == "NA"


def test_analyze_arm_results_synthetic_data():
    # Construct 4 families with known outcomes
    # Fam 0: H0 Replay=1, H0 Regen=1, H1 Replay=0, H1 Regen=1
    # Fam 1: H0 Replay=1, H0 Regen=1, H1 Replay=0, H1 Regen=1
    # Fam 2: H0 Replay=1, H0 Regen=1, H1 Replay=0, H1 Regen=0 (dup)
    # Fam 3: H0 Replay=1, H0 Regen=1, H1 Replay=0, H1 Regen=1
    arms = []
    for fam_idx in range(4):
        fam_id = f"FAM-{fam_idx}"
        # H0 Replay
        arms.append(ArmResult(
            provider="github", family_id=fam_id, arm_id=f"ARM-{fam_idx}-H0-REP",
            hidden_world="H0", policy="EXACT_REPLAY", status="SUCCESS", state_correct=1, reason="exact_one",
        ))
        # H0 Regen
        arms.append(ArmResult(
            provider="github", family_id=fam_id, arm_id=f"ARM-{fam_idx}-H0-REG",
            hidden_world="H0", policy="LLM_REGENERATION", status="SUCCESS", state_correct=1, reason="exact_one",
            model_calls=2, tool_action_attempts=1,
        ))
        # H1 Replay
        arms.append(ArmResult(
            provider="github", family_id=fam_id, arm_id=f"ARM-{fam_idx}-H1-REP",
            hidden_world="H1", policy="EXACT_REPLAY", status="FAILURE", state_correct=0, reason="duplicate_issue",
            duplicate_count=1,
        ))
        # H1 Regen
        regen_corr = 0 if fam_idx == 2 else 1
        arms.append(ArmResult(
            provider="github", family_id=fam_id, arm_id=f"ARM-{fam_idx}-H1-REG",
            hidden_world="H1", policy="LLM_REGENERATION", status="SUCCESS" if regen_corr else "FAILURE",
            state_correct=regen_corr, reason="exact_one" if regen_corr else "duplicate_issue",
            duplicate_count=1 if not regen_corr else 0,
            model_calls=3, tool_action_attempts=2,
        ))

    analysis = analyze_arm_results("github", arms, total_families=4)
    assert analysis.completed_arms == 16
    assert analysis.evaluable_arms == 16
    assert analysis.h0_paired_n == 4
    assert analysis.h0_replay_correct == 4
    assert analysis.h0_regen_correct == 4
    assert analysis.h0_delta == 0.0
    assert analysis.h0_mcnemar_p == 1.0

    assert analysis.h1_paired_n == 4
    assert analysis.h1_replay_correct == 0
    assert analysis.h1_regen_correct == 3
    assert analysis.h1_delta == -0.75  # 0/4 - 3/4 = -0.75
    assert analysis.duplicate_arms == 5  # 4 H1 Replay + 1 H1 Regen

    assert analysis.interaction_n == 4
    assert analysis.interaction_delta == -0.75  # (-0.75) - (0.0) = -0.75
    assert analysis.interaction_ci_lower is not None
    assert analysis.interaction_ci_upper is not None


def test_markdown_and_latex_table_generation():
    analyses = {
        "github": create_placeholder_provider_analysis("github", 64),
        "sheets": create_placeholder_provider_analysis("sheets", 64),
        "razorpay": create_placeholder_provider_analysis("razorpay", 64),
    }
    md = generate_markdown_summary_table(analyses)
    assert "| GitHub Issues | H0 (NOT_EXECUTED) | [STUDY2-PENDING] | [STUDY2-PENDING] |" in md
    assert "| Google Sheets | H1 (EXECUTED_ACK_LOST) | [STUDY2-PENDING] | [STUDY2-PENDING] |" in md
    assert "| Razorpay Orders | H1 (EXECUTED_ACK_LOST) | [STUDY2-PENDING] | [STUDY2-PENDING] |" in md

    latex = generate_latex_summary_table(analyses)
    assert "\\begin{table*}" in latex
    assert "GitHub Issues" in latex
    assert "[STUDY2-PENDING]" in latex


def test_serialization_and_csv_export(tmp_path: Path):
    analyses = {
        "github": create_placeholder_provider_analysis("github", 64),
        "sheets": create_placeholder_provider_analysis("sheets", 64),
        "razorpay": create_placeholder_provider_analysis("razorpay", 64),
    }
    data = serialize_analysis_to_dict(analyses)
    assert data["schema"] == "study2-cross-provider-analysis-v1"
    assert data["cross_provider_aggregate"]["total_scheduled_families"] == 192
    assert data["cross_provider_aggregate"]["total_scheduled_arms"] == 768
    for provider in ("github", "sheets", "razorpay"):
        for world in ("h0", "h1"):
            assert data["providers"][provider][world]["paired_n"] is None
            assert data["providers"][provider][world]["replay"]["correct"] is None
            assert data["providers"][provider][world]["regeneration"]["total"] is None

    csv_path = tmp_path / "test_summary.csv"
    export_analysis_csv(analyses, csv_path)
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    assert "github,H0,," in content
    assert "razorpay,H1,," in content


def _mock_run(tmp_path: Path):
    run_dir = tmp_path / "mock_run"
    run_dir.mkdir()
    manifest = {"families": [{"family_id": "FAM-001", "arms": []}]}
    paths = []
    for index, (world, policy) in enumerate((
        ("H0", "EXACT_REPLAY"), ("H0", "LLM_REGENERATION"),
        ("H1", "EXACT_REPLAY"), ("H1", "LLM_REGENERATION"),
    )):
        arm_id = f"FAM-001:{world}:{policy}"
        manifest["families"][0]["arms"].append({
            "arm_id": arm_id, "hidden_world": world, "policy": policy,
        })
        arm_dir = run_dir / f"{index:03d}-FAM-001-{index + 1}"
        arm_dir.mkdir()
        path = arm_dir / "arm-projection.json"
        path.write_text(json.dumps({"arm_id": arm_id, "projection": {
            "status": "SUCCESS", "state_correct": 1, "reason": "CORRECT",
        }}))
        paths.append(path)
    (run_dir / "run-authorization.json").write_text(json.dumps({
        "provider": "github", "study2_paper_observations_before_run": 0,
        "manifest_sha256": sha256_hex(canonical_json_bytes(manifest)),
        "runtime_sha256": {},
    }))
    return run_dir, manifest, paths


def test_load_run_projections_from_disk(tmp_path: Path):
    run_dir, manifest, _ = _mock_run(tmp_path)
    arms = load_run_projections(run_dir, manifest, "github")
    assert len(arms) == 4
    assert {a.arm_id for a in arms} == {a["arm_id"] for a in manifest["families"][0]["arms"]}


@pytest.mark.parametrize("corruption,match", [
    ("malformed_json", "unreadable projection"),
    ("unknown_arm", "unknown projection arm ID"),
    ("duplicate_projection", "duplicate projection arm ID"),
    ("invalid_state", "invalid projection verdict"),
    ("contradictory_status", "projection verdict"),
    ("unknown_status", "projection verdict"),
    ("contradictory_reason", "projection reason"),
    ("unknown_failure_reason", "projection reason"),
    ("missing_file", "missing projection"),
    ("incomplete", "incomplete run evidence"),
])
def test_load_run_rejects_corrupt_or_incomplete_evidence(tmp_path: Path, corruption: str, match: str):
    run_dir, manifest, paths = _mock_run(tmp_path)
    if corruption == "malformed_json":
        paths[0].write_text("{")
    elif corruption == "unknown_arm":
        data = json.loads(paths[0].read_text())
        data["arm_id"] = "UNSCHEDULED"
        paths[0].write_text(json.dumps(data))
    elif corruption == "duplicate_projection":
        data = json.loads(paths[0].read_text())
        data["arm_id"] = manifest["families"][0]["arms"][1]["arm_id"]
        paths[0].write_text(json.dumps(data))
    elif corruption == "invalid_state":
        data = json.loads(paths[0].read_text())
        data["projection"]["state_correct"] = 2
        paths[0].write_text(json.dumps(data))
    elif corruption == "contradictory_status":
        data = json.loads(paths[0].read_text())
        data["projection"]["status"] = "INCONCLUSIVE"
        paths[0].write_text(json.dumps(data))
    elif corruption == "unknown_status":
        data = json.loads(paths[0].read_text())
        data["projection"]["status"] = "OTHER"
        paths[0].write_text(json.dumps(data))
    elif corruption == "contradictory_reason":
        data = json.loads(paths[0].read_text())
        data["projection"]["reason"] = "DUPLICATE_EFFECT"
        paths[0].write_text(json.dumps(data))
    elif corruption == "unknown_failure_reason":
        data = json.loads(paths[0].read_text())
        data["projection"].update(status="FAILURE", state_correct=0, reason="perhaps_duplicate")
        paths[0].write_text(json.dumps(data))
    elif corruption == "missing_file":
        paths[0].unlink()
    else:
        paths[0].unlink()
        paths[0].parent.rmdir()
    with pytest.raises(ValueError, match=match):
        load_run_projections(run_dir, manifest, "github")


def test_stopped_run_and_unsupported_sheets_ingestion_fail_closed(tmp_path: Path):
    run_dir, manifest, _ = _mock_run(tmp_path)
    (run_dir / "run-stopped-test.json").write_text("{}")
    with pytest.raises(ValueError, match="stopped or aborted"):
        load_run_projections(run_dir, manifest, "github")
    with pytest.raises(ValueError, match="no frozen Google Sheets"):
        load_run_projections(run_dir, manifest, "sheets")


def test_run_requires_authorization_and_full_scheduled_family_count(tmp_path: Path):
    run_dir, manifest, _ = _mock_run(tmp_path)
    with pytest.raises(ValueError, match="expected 64 scheduled families"):
        load_run_projections(run_dir, manifest, "github", expected_families=64)
    (run_dir / "run-authorization.json").write_text("{")
    with pytest.raises(ValueError, match="malformed run-authorization"):
        load_run_projections(run_dir, manifest, "github")


@pytest.mark.parametrize("corruption", ["duplicate_family", "duplicate_arm", "duplicate_cell", "invalid_world", "invalid_policy"])
def test_load_run_rejects_invalid_manifest(tmp_path: Path, corruption: str):
    run_dir, manifest, _ = _mock_run(tmp_path)
    family = manifest["families"][0]
    if corruption == "duplicate_family":
        manifest["families"].append(dict(family))
    elif corruption == "duplicate_arm":
        family["arms"][1]["arm_id"] = family["arms"][0]["arm_id"]
    elif corruption == "duplicate_cell":
        family["arms"][1]["policy"] = "EXACT_REPLAY"
    elif corruption == "invalid_world":
        family["arms"][0]["hidden_world"] = "H2"
    else:
        family["arms"][0]["policy"] = "OTHER"
    auth_path = run_dir / "run-authorization.json"
    authorization = json.loads(auth_path.read_text())
    authorization["manifest_sha256"] = sha256_hex(canonical_json_bytes(manifest))
    auth_path.write_text(json.dumps(authorization))
    with pytest.raises(ValueError, match="manifest"):
        load_run_projections(run_dir, manifest, "github")


def test_primary_table_counts_use_only_evaluable_pairs():
    arms = []
    for fam, replay, regen in (("complete", 1, 0), ("replay_only", 0, None),
                               ("regen_only", None, 1)):
        for policy, correct in (("EXACT_REPLAY", replay), ("LLM_REGENERATION", regen)):
            arms.append(ArmResult("github", fam, f"{fam}:{policy}", "H0", policy,
                                  "INCONCLUSIVE" if correct is None else "SUCCESS" if correct else "FAILURE",
                                  correct, "test"))
    analysis = analyze_arm_results("github", arms, total_families=3)
    assert analysis.h0_paired_n == 1
    assert (analysis.h0_replay_correct, analysis.h0_replay_total) == (1, 1)
    assert (analysis.h0_regen_correct, analysis.h0_regen_total) == (0, 1)
    assert analysis.h0_delta == (analysis.h0_replay_correct - analysis.h0_regen_correct) / analysis.h0_paired_n
    assert analysis.descriptive_all_evaluable_arm_counts["H0"]["EXACT_REPLAY"] == {"correct": 1, "total": 2}
    assert analysis.descriptive_all_evaluable_arm_counts["H0"]["LLM_REGENERATION"] == {"correct": 1, "total": 2}
    md = generate_markdown_summary_table({"github": analysis})
    latex = generate_latex_summary_table({"github": analysis})
    assert "| H0 (NOT_EXECUTED) | 1 | 1/1 (100.0%) | 0/1 (0.0%) | +100.00% |" in md
    assert "1/1 (100.0\\%)" in latex and "0/1 (0.0\\%)" in latex


def test_taxonomy_uses_exact_frozen_reason_tokens():
    from retry_semantics.study2.provider_paper_analysis import extract_arm_result_from_dict
    arm = {"arm_id": "A", "hidden_world": "H1", "policy": "EXACT_REPLAY"}
    for reason, expected in (("DUPLICATE_EFFECT", (1, 0, 0)),
                             ("MISSING_EFFECT,WRONG_MUTATION", (0, 1, 1)),
                             ("not_a_duplicate_effect", (0, 0, 0))):
        result = extract_arm_result_from_dict("github", arm, {"projection": {
            "status": "FAILURE", "state_correct": 0, "reason": reason,
        }}, "F")
        assert (result.duplicate_count, result.missing_count, result.unintended_count) == expected
