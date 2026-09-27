"""Offline checks for a separate prospective V4.1 Study1B replication."""

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from retry_semantics.experiment import build_fireworks_deepseek_paper_manifest, paper
from retry_semantics.experiment.analysis_evidence import (
    MANIFEST_ID, MANIFEST_SHA256, STUDY1B_MANIFEST_ID,
    STUDY1B_MANIFEST_SHA256, extract_ticket_analysis,
)
from retry_semantics.experiment.fireworks_paper_study1b import (
    STUDY1B_MODEL, build_study1b_manifest,
)
from retry_semantics.models import DEEPSEEK_V4_FLASH_0731_MODEL
from test_paper_collection import METADATA
from test_paper_measurement_v2 import MeasuredOfflineClient, collect


def test_separate_model_manifest_and_frozen_design():
    old = build_fireworks_deepseek_paper_manifest()
    new = build_study1b_manifest()
    assert old.manifest_id == MANIFEST_ID
    assert old.manifest_hash == MANIFEST_SHA256
    assert new.manifest_id == STUDY1B_MANIFEST_ID != old.manifest_id
    assert new.manifest_hash == STUDY1B_MANIFEST_SHA256 != old.manifest_hash
    assert len(old.entries) == len(new.entries) == 160
    for index, (a, b) in enumerate(zip(old.entries, new.entries)):
        assert a.model_config.model.name == DEEPSEEK_V4_FLASH_0731_MODEL
        assert b.model_config.model.name == STUDY1B_MODEL
        assert b.scenario == a.scenario
        assert b.replicate == a.replicate
        assert b.schedule_stratum == a.schedule_stratum
        assert b.hidden_world_orientation_bit == a.hidden_world_orientation_bit
        assert b.policy_orientation_bit == a.policy_orientation_bit
        assert b.plan.hidden_world_order == a.plan.hidden_world_order
        assert b.plan.h0_arm_order == a.plan.h0_arm_order
        assert b.plan.h1_arm_order == a.plan.h1_arm_order
        assert b.plan.manifest_id != a.plan.manifest_id
        assert b.original_generation_config.seed == a.original_generation_config.seed == 30_000 + index
        assert b.regeneration_config.seed == a.regeneration_config.seed == 40_000 + 10 * index


def test_launch_path_cannot_name_study1a_or_enter_checkout():
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/run_study1b_paper.py"))
    run_dir = module["RUN_DIR"]
    assert run_dir.name == "study1b-v41-primary"
    assert module["REPOSITORY_ROOT"] not in run_dir.parents
    assert "study1a" not in str(run_dir).lower()


def test_launch_refuses_existing_run_before_any_model_call(tmp_path, monkeypatch):
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/run_study1b_paper.py"))
    main = module["main"]
    existing = tmp_path / "study1b-v41-primary"
    existing.mkdir()
    main.__globals__["RUN_DIR"] = existing
    monkeypatch.setenv("FIREWORKS_API_KEY", "offline-placeholder")
    with pytest.raises(SystemExit, match="no resume/refill"):
        main()


def test_launch_refuses_unreviewed_worktree_before_any_model_call(tmp_path, monkeypatch):
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/run_study1b_paper.py"))
    main = module["main"]
    main.__globals__["RUN_DIR"] = tmp_path / "study1b-v41-primary"
    monkeypatch.setenv("FIREWORKS_API_KEY", "offline-placeholder")
    calls = iter((SimpleNamespace(stdout="a" * 40 + "\n"), SimpleNamespace(stdout=" M unreviewed.py\n")))
    monkeypatch.setattr(main.__globals__["subprocess"], "run", lambda *args, **kwargs: next(calls))
    with pytest.raises(SystemExit, match="clean, audited commit"):
        main()


def test_cross_study_analysis_rejected_and_study1b_is_valid(tmp_path):
    old = build_fireworks_deepseek_paper_manifest()
    new = build_study1b_manifest()
    for name, manifest in (("study1a", old), ("study1b", new)):
        client = MeasuredOfflineClient(eligible={0})
        result = collect(manifest, client)
        assert client.original_slots == list(range(160))
        paper.persist_paper_collection_run(
            run_root=tmp_path / name, manifest=manifest,
            result=result, metadata=METADATA,
        )
    with pytest.raises(paper.PaperCollectionError, match="prospectively frozen"):
        extract_ticket_analysis(tmp_path / "study1a", tmp_path / "wrong-b", study1b=True)
    with pytest.raises(paper.PaperCollectionError, match="prospectively frozen"):
        extract_ticket_analysis(tmp_path / "study1b", tmp_path / "wrong-a")
    extract_ticket_analysis(tmp_path / "study1b", tmp_path / "analysis-b", study1b=True)
    provenance = json.loads((tmp_path / "analysis-b/analysis_provenance.json").read_bytes())
    assert provenance["source_manifest_id"] == STUDY1B_MANIFEST_ID
    assert provenance["source_manifest_sha256"] == STUDY1B_MANIFEST_SHA256


def test_existing_v2_collector_runs_study1b_once_offline(tmp_path):
    target = tmp_path / "study1b-v41-primary"
    manifest = build_study1b_manifest()
    client = MeasuredOfflineClient(eligible={0})
    paper.run_paper_collection(
        manifest=manifest, client=client, run_root=target,
        metadata=METADATA, evidence_revision=paper.EVIDENCE_V2,
    )
    paper.validate_paper_collection_bundle(target)
    assert client.original_slots == list(range(160))
    with pytest.raises(paper.PaperCollectionError, match="already exists"):
        paper.run_paper_collection(
            manifest=manifest, client=MeasuredOfflineClient(eligible={0}),
            run_root=target, metadata=METADATA, evidence_revision=paper.EVIDENCE_V2,
        )
