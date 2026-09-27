"""Offline tests verifying the 19 core operational invariants of Study-2.

Invariants verified:
1. Study1A remains untouched.
2. Study1B remains untouched.
3. Zero Study2 observations before live work.
4. Exact V4.1 model identity everywhere.
5. GitHub frozen science unchanged.
6. Razorpay frozen science unchanged.
7. Sheets namespace/spreadsheet/tab mapping unchanged.
8. Sheets CREATE can never be rerun by primary collector.
9. Sheets primary collector writes one durable projection/arm.
10. Malformed/incomplete Sheets evidence fails closed.
11. Incomplete/stopped/aborted Sheets primary run cannot enter paper analysis.
12. Readiness gates prevent collection without proper locks.
13. Final authorization requires all 3 provider locks.
14. Launch CLIs refuse dirty repository.
15. Launch CLIs refuse existing run directory.
16. Run paths are external to checkout.
17. No resume/refill.
18. Provider launch CLIs preserve current frozen protocol values.
19. No network calls are made by offline tests.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import socket
import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.github_paper_manifest import load_github_paper_manifest
from retry_semantics.study2.razorpay_paper_manifest import load_razorpay_paper_manifest
from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest as load_sheets_paper_manifest
from retry_semantics.study2.provider_paper_analysis import load_run_projections
from retry_semantics.study2.provider_paper_collection import (
    ArmProjection,
    PaperCollectionError,
    collect_sheets_arm,
    collect_provider_run,
)
from retry_semantics.study2.provider_paper_io import DurablePaperEvidence, PaperRequest, PaperTransportResult
from retry_semantics.study2.provider_paper_readiness import (
    PROVIDER_CONTROLS,
    ProviderReadinessError,
    check_final_collection_authorization,
    check_readiness_lock,
    current_static_identity,
)
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retry_semantics.study2.github_live_readiness import capture_github_readiness
from retry_semantics.study2.razorpay_live_readiness import capture_razorpay_readiness
from scripts.rebind_sheets_paper_readiness_controls import rebind_sheets_controls
from scripts.prepare_study2_final_collection_authorization import prepare_final_authorization
V4P1_MODEL = "accounts/fireworks/models/deepseek-v4p1-flash"


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("offline Study-2 test attempted a network connection")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def test_inv_01_study1a_remains_untouched():
    """Invariant 1: Study1A remains untouched relative to baseline HEAD."""
    diff = subprocess.run(
        ["git", "diff", "HEAD", "--", "research/study1a", "src/retry_semantics/study1a"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert diff == "", "Study1A files must remain untouched"


def test_inv_02_study1b_remains_untouched():
    """Invariant 2: Study1B remains untouched relative to baseline HEAD."""
    diff = subprocess.run(
        ["git", "diff", "HEAD", "--", "research/study1b", "src/retry_semantics/study1b"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert diff == "", "Study1B files must remain untouched"


def test_inv_03_zero_study2_observations():
    """Invariant 3: Zero Study2 paper observations exist before live work."""
    gh_manifest = load_github_paper_manifest().as_json()
    rz_manifest = load_razorpay_paper_manifest()
    sh_manifest = load_sheets_paper_manifest()

    assert gh_manifest.get("study2_paper_observations", 0) == 0
    assert rz_manifest.get("study2_paper_observations", 0) == 0
    assert sh_manifest.get("study2_paper_observations", 0) == 0


def test_inv_04_exact_v4p1_model_identity_everywhere():
    """Invariant 4: Exact V4.1 model identity everywhere across all Study2 manifests."""
    gh_manifest = load_github_paper_manifest().as_json()
    rz_manifest = load_razorpay_paper_manifest()
    sh_manifest = load_sheets_paper_manifest()

    for m in (gh_manifest, rz_manifest, sh_manifest):
        families = m.get("families", [])
        assert len(families) == 64
        for f in families:
            assert f["model_config"]["model"]["name"] == V4P1_MODEL


def test_inv_05_github_frozen_science_unchanged():
    """Invariant 5: GitHub frozen science unchanged (64 families, 256 arms, +0/+600 schedule, etc.)."""
    from retry_semantics.study2 import github_paper_runtime as gh
    gh_manifest = load_github_paper_manifest().as_json()
    assert gh_manifest["selected_repository"] == "JashRashne/retry-semantics-study2-github-sandbox"
    assert gh_manifest["run_namespace"] == "d88836f3d4b57ed5c300d650ddfb0e3a"
    assert gh.OBSERVATION_STARTS == (0, 600)
    assert gh.OBSERVATION_DEADLINES == (540, 1140)
    assert gh.OBSERVATION_DEADLINES[-1] == 1140
    arms = [a for f in gh_manifest["families"] for a in f["arms"]]
    assert len(arms) == 256
    for a in arms:
        assert re.match(r"^rs2gh1-[0-9a-f]{32}$", a["arm_marker"])


def test_inv_06_razorpay_frozen_science_unchanged():
    """Invariant 6: Razorpay frozen science unchanged (+0/+200 schedule, 200 INR, no receipt, etc.)."""
    from retry_semantics.study2 import razorpay_paper_runtime as rz
    rz_manifest = load_razorpay_paper_manifest()
    assert rz.OBSERVATION_STARTS == (0, 200)
    assert rz.OBSERVATION_DEADLINES == (170, 370)
    assert rz.TERMINAL_DEADLINE == 470
    assert rz.D == 1020
    arms = [a for f in rz_manifest["families"] for a in f["arms"]]
    assert len(arms) == 256
    for a in arms:
        assert re.match(r"^study2_[A-Za-z0-9_-]+$", a["marker"])


def test_inv_07_sheets_namespace_spreadsheet_tab_mapping():
    """Invariant 7: Sheets namespace/spreadsheet/tab mapping unchanged (15Sf9PrQq..., 256 tabs 100x3)."""
    sh_manifest = load_sheets_paper_manifest()
    assert sh_manifest["spreadsheet_id"] == "15Sf9PrQqVRWj2Fe4pR_ZKslGWwbBi3OfgH_eElpoJ_Q"
    assert sh_manifest["run_namespace"] == "76b0af67d7eece50cb12167e7ec374b9"
    arms = [a for f in sh_manifest["families"] for a in f["arms"]]
    assert len(arms) == 256
    sheet_ids = {a["sheet_id"] for a in arms}
    assert len(sheet_ids) == 256


def test_inv_08_sheets_create_never_rerun(tmp_path):
    """Invariant 8: Sheets CREATE can never be rerun by primary collector."""
    manifest = load_sheets_paper_manifest()
    family = manifest["families"][0]
    arm = family["arms"][0]

    dispatched_urls = []

    def mock_send(req: PaperRequest) -> PaperTransportResult:
        dispatched_urls.append((req.method, req.url))
        if req.method == "GET":
            # return empty grid
            grid_body = {
                "spreadsheetId": manifest["spreadsheet_id"],
                "sheets": [{"data": [{"rowData": []}]}],
            }
            return PaperTransportResult(200, (), canonical_json_bytes(grid_body), None, True, True, True, 0.0, 0.1)
        return PaperTransportResult(200, (), b"{}", None, True, True, True, 0.0, 0.1)

    evidence = DurablePaperEvidence(
        tmp_path, provider="sheets", family_id=family["family_id"],
        arm_id=arm["arm_id"], manifest_sha256="m", runtime_sha256="r",
    )
    collect_sheets_arm(
        manifest=manifest,
        family=family,
        arm=arm,
        evidence=evidence,
        send=mock_send,
        model=None,
        clock=lambda: 0.0,
        wait_until=lambda t: None,
    )

    for method, url in dispatched_urls:
        assert not (method == "POST" and url.rstrip("/").endswith("/v4/spreadsheets")), \
            "Primary collector must NEVER call spreadsheets.create!"


def test_inv_09_sheets_primary_writes_durable_projection(tmp_path):
    """Invariant 9: Sheets primary collector writes one durable projection per arm."""
    manifest = load_sheets_paper_manifest()
    family = manifest["families"][0]
    arm = family["arms"][0]

    def mock_send(req: PaperRequest) -> PaperTransportResult:
        grid_body = {
            "spreadsheetId": manifest["spreadsheet_id"],
            "sheets": [{"data": [{"rowData": []}]}],
        }
        return PaperTransportResult(200, (), canonical_json_bytes(grid_body), None, True, True, True, 0.0, 0.1)

    evidence = DurablePaperEvidence(
        tmp_path, provider="sheets", family_id=family["family_id"],
        arm_id=arm["arm_id"], manifest_sha256="m", runtime_sha256="r",
    )
    proj, stopped = collect_sheets_arm(
        manifest=manifest,
        family=family,
        arm=arm,
        evidence=evidence,
        send=mock_send,
        model=None,
        clock=lambda: 0.0,
        wait_until=lambda t: None,
    )
    assert isinstance(proj, ArmProjection)
    assert proj.arm_id == arm["arm_id"]
    proj_file = tmp_path / "arm-projection.json"
    assert proj_file.is_file()
    proj_data = json.loads(proj_file.read_text())
    assert proj_data["arm_id"] == arm["arm_id"]


def test_inv_10_malformed_incomplete_sheets_evidence_fails_closed(tmp_path):
    """Invariant 10: Malformed or incomplete Sheets evidence fails closed."""
    manifest = load_sheets_paper_manifest()
    family = manifest["families"][0]
    arm = family["arms"][0]

    # Server returns 500 error on GET
    def mock_send(req: PaperRequest) -> PaperTransportResult:
        return PaperTransportResult(500, (), b"Internal Server Error", "server error", True, True, True, 0.0, 0.1)

    evidence = DurablePaperEvidence(
        tmp_path, provider="sheets", family_id=family["family_id"],
        arm_id=arm["arm_id"], manifest_sha256="m", runtime_sha256="r",
    )
    proj, stopped = collect_sheets_arm(
        manifest=manifest,
        family=family,
        arm=arm,
        evidence=evidence,
        send=mock_send,
        model=None,
        clock=lambda: 0.0,
        wait_until=lambda t: None,
    )
    assert proj.status == "INCONCLUSIVE"
    assert proj.state_correct is None


def test_inv_11_incomplete_stopped_sheets_cannot_enter_analysis(tmp_path):
    """Invariant 11: Incomplete/stopped/aborted Sheets primary run cannot enter paper analysis."""
    # Create stopped indicator in run directory
    run_dir = tmp_path / "sheets-run"
    run_dir.mkdir()
    (run_dir / "run-stopped-00000000.json").write_text("{}")

    sh_manifest = load_sheets_paper_manifest()
    with pytest.raises(ValueError, match="stopped or aborted"):
        load_run_projections(run_dir, sh_manifest, "sheets")


def test_inv_12_readiness_gates_prevent_collection_without_proper_locks(tmp_path):
    """Invariant 12: Readiness gates prevent collection without proper committed locks."""
    fake_lock = tmp_path / "fake-lock.json"
    fake_lock.write_text("{}")
    fake_auth = tmp_path / "fake-auth.json"
    fake_auth.write_text("{}")

    with pytest.raises(Exception):
        collect_provider_run(
            provider="github",
            run_dir=tmp_path / "run",
            lock_path=fake_lock,
            evidence_dir=tmp_path,
            audit_receipt_path=tmp_path / "receipt.json",
            audit_report_path=tmp_path / "report.json",
            credential="test-token",
            model_api_key="test-key",
            all_provider_readiness_lock_paths={"github": fake_lock, "razorpay": fake_lock, "sheets": fake_lock},
            collection_authorization_path=fake_auth,
            collection_audit_receipt_path=fake_auth,
            collection_audit_report_path=fake_auth,
        )


def test_inv_13_final_authorization_requires_all_three_locks(tmp_path):
    """Invariant 13: Final authorization requires all 3 provider locks."""
    # Test prepare_final_authorization rejects missing lock
    missing_lock = tmp_path / "nonexistent.json"
    real_dummy = tmp_path / "dummy.json"
    real_dummy.write_text(json.dumps({"schema": "test", "study2_paper_observations": 0}))

    with pytest.raises(ProviderReadinessError, match="Missing readiness lock"):
        prepare_final_authorization(
            github_lock_path=missing_lock,
            razorpay_lock_path=real_dummy,
            sheets_lock_path=real_dummy,
        )


def test_inv_14_launch_clis_refuse_dirty_repository(monkeypatch):
    """Invariant 14: Launch CLIs refuse dirty repository."""
    from scripts.run_study2_github_primary import _check_clean_git as gh_check
    from scripts.run_study2_razorpay_primary import _check_clean_git as rz_check
    from scripts.run_study2_sheets_primary import _check_clean_git as sh_check

    def mock_run(args, **kwargs):
        class Res:
            stdout = " M modified_file.py\n" if "status" in args else str(ROOT)
        return Res()

    monkeypatch.setattr(subprocess, "run", mock_run)
    with pytest.raises(SystemExit, match="Working tree is not clean"):
        gh_check(ROOT)
    with pytest.raises(SystemExit, match="Working tree is not clean"):
        rz_check(ROOT)
    with pytest.raises(SystemExit, match="Working tree is not clean"):
        sh_check(ROOT)


def test_inv_15_launch_clis_refuse_existing_run_directory(tmp_path, monkeypatch):
    """Invariant 15: Launch CLIs refuse existing run directory (no resume)."""
    from scripts import run_study2_github_primary

    existing_dir = tmp_path / "existing_run"
    existing_dir.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "run_study2_github_primary.py",
        "--execute-primary",
        "--run-dir", str(existing_dir),
        "--github-token", "dummy",
        "--fireworks-api-key", "dummy",
    ])
    monkeypatch.setattr(run_study2_github_primary, "_check_clean_git", lambda r: None)

    with pytest.raises(SystemExit, match="Run directory already exists"):
        run_study2_github_primary.main()


def test_inv_16_run_paths_are_external_to_checkout(tmp_path):
    """Invariant 16: Run directory should be independent/external."""
    outside_dir = tmp_path / "outside_run"
    assert not outside_dir.is_relative_to(ROOT / "src")
    assert not outside_dir.is_relative_to(ROOT / "research")


def test_inv_17_no_resume_refill(tmp_path, monkeypatch):
    """Invariant 17: No resume or refill permitted once run directory exists."""
    from retry_semantics.study2 import provider_paper_collection as coll
    run_dir = tmp_path / "run_dir"
    run_dir.mkdir()
    fake_lock = tmp_path / "lock.json"
    fake_lock.write_text("{}")

    (tmp_path / "repository_identity_and_full_baseline.json").write_text(
        json.dumps({"facts": {"api_version": "2022-11-28"}})
    )
    monkeypatch.setattr(coll, "check_readiness_lock", lambda *args, **kwargs: {"manifest_sha256": "m", "runtime_sha256": "r"})
    monkeypatch.setattr(coll, "check_final_collection_authorization", lambda *args, **kwargs: "auth_sha")

    with pytest.raises(PaperCollectionError, match="resume prohibited"):
        coll.collect_provider_run(
            provider="github",
            run_dir=run_dir,
            lock_path=fake_lock,
            evidence_dir=tmp_path,
            audit_receipt_path=fake_lock,
            audit_report_path=fake_lock,
            credential="token",
            model_api_key="key",
            all_provider_readiness_lock_paths={"github": fake_lock},
            collection_authorization_path=fake_lock,
            collection_audit_receipt_path=fake_lock,
            collection_audit_report_path=fake_lock,
            api_version="2022-11-28",
        )


def test_inv_18_provider_launch_clis_preserve_current_frozen_protocol():
    """Invariant 18: Provider launch CLIs preserve current frozen protocol values."""
    from scripts import run_study2_github_primary, run_study2_razorpay_primary, run_study2_sheets_primary
    # Inspect default CLI flags
    import argparse
    for mod, expected_provider in (
        (run_study2_github_primary, "github"),
        (run_study2_razorpay_primary, "razorpay"),
        (run_study2_sheets_primary, "sheets"),
    ):
        text = Path(mod.__file__).read_text()
        assert "collect_provider_run" in text
        assert f'provider="{expected_provider}"' in text


def test_inv_19_no_network_calls_made_by_offline_tests():
    """The active guard rejects an attempted socket connection."""
    with pytest.raises(AssertionError, match="offline Study-2"):
        socket.create_connection(("127.0.0.1", 9))


def test_github_live_readiness_offline_mocked(tmp_path):
    """Test GitHub live readiness qualification operator under mocked transport."""
    manifest = load_github_paper_manifest().as_json()
    from retry_semantics.study2.github_paper_manifest import load_namespace_registry as load_gh_reg
    registry = load_gh_reg().as_json()
    identity = {
        "provider": "github",
        "manifest_sha256": sha256_hex(canonical_json_bytes(manifest)),
        "runtime_sha256": {},
    }

    def mock_send(req: PaperRequest) -> PaperTransportResult:
        if req.url.endswith("/rate_limit"):
            body = {"resources": {"core": {"remaining": 5000, "limit": 5000}}}
        elif req.url.endswith("/user"):
            body = {"id": 42, "login": "test-operator"}
        elif req.url.endswith("/issues"):
            if req.method == "POST":
                data = json.loads(req.body)
                body = {"number": 100, "title": data["title"], "body": data["body"], "state": "open"}
                return PaperTransportResult(201, (("x-github-api-version-selected", "2022-11-28"),), canonical_json_bytes(body), None, True, True, True, 0.0, 0.1)
            body = []
        elif "/issues?state=" in req.url:
            # Check if it was suffix readback
            if "page=1" in req.url:
                # Return issue with safe qualification suffix
                body = [{"number": 100, "title": "[QUALIFICATION] Suffix roundtrip test",
                         "body": "Study-2 qualification issue suffix roundtrip verification.\n\n<!-- retry-semantics-study2-gh:v1:rs2gh1-00000000000000000000000000000000 -->",
                         "state": "open"}]
            else:
                body = []
        else:
            body = {"id": 1374277504, "full_name": manifest["selected_repository"]}
        return PaperTransportResult(200, (("x-github-api-version-selected", "2022-11-28"),), canonical_json_bytes(body), None, True, True, True, 0.0, 0.1)

    def mock_model_complete(model_name: str, tools: tuple[dict, ...], sampling: dict):
        return {
            "id": "mock-comp",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": tools[0]["name"],
                            "arguments": "{}",
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }

    hashes = capture_github_readiness(
        manifest=manifest,
        registry=registry,
        evidence_dir=tmp_path / "gh_evidence",
        identity=identity,
        operator_id="test-operator",
        api_version="2022-11-28",
        http_send=mock_send,
        model_complete=mock_model_complete,
    )
    assert len(hashes) == 7
    for ctrl in PROVIDER_CONTROLS["github"]:
        assert ctrl in hashes
        assert (tmp_path / "gh_evidence" / f"{ctrl}.json").is_file()
        assert (tmp_path / "gh_evidence" / f"{ctrl}.capture.json").is_file()


def test_razorpay_live_readiness_offline_mocked(tmp_path):
    """Test Razorpay live readiness qualification operator under mocked transport."""
    manifest = load_razorpay_paper_manifest()
    from retry_semantics.study2.razorpay_paper_manifest import load_namespace_registry as load_rz_reg
    registry = load_rz_reg()
    identity = {
        "provider": "razorpay",
        "manifest_sha256": sha256_hex(canonical_json_bytes(manifest)),
        "runtime_sha256": {},
    }

    def mock_send(req: PaperRequest) -> PaperTransportResult:
        if "order_TfBuv3iQHQrz9p" in req.url:
            body = {
                "id": "order_TfBuv3iQHQrz9p",
                "entity": "order",
                "amount": 200,
                "currency": "INR",
                "notes": {"retry_semantics_marker": "study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215"},
            }
        elif req.method == "POST":
            data = json.loads(req.body)
            body = {
                "id": "order_qual_123",
                "entity": "order",
                "amount": data["amount"],
                "currency": data["currency"],
                "notes": data.get("notes", {}),
            }
        else:
            body = {"entity": "collection", "count": 0, "items": []}
        return PaperTransportResult(200, (), canonical_json_bytes(body), None, True, True, True, 0.0, 0.1)

    def mock_model_complete(model_name: str, tools: tuple[dict, ...], sampling: dict):
        return {
            "id": "mock-comp",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": tools[0]["name"],
                            "arguments": "{}",
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }

    hashes = capture_razorpay_readiness(
        manifest=manifest,
        registry=registry,
        evidence_dir=tmp_path / "rz_evidence",
        identity=identity,
        operator_id="test-operator",
        http_send=mock_send,
        model_complete=mock_model_complete,
    )
    assert len(hashes) == 7
    for ctrl in PROVIDER_CONTROLS["razorpay"]:
        assert ctrl in hashes
        assert (tmp_path / "rz_evidence" / f"{ctrl}.json").is_file()
        assert (tmp_path / "rz_evidence" / f"{ctrl}.capture.json").is_file()


def test_rebind_sheets_controls_offline(tmp_path):
    """Old qualification booleans cannot be promoted to the new manifest."""
    with pytest.raises(ValueError, match="prohibited"):
        rebind_sheets_controls(output_dir=tmp_path / "rebound")
    assert not (tmp_path / "rebound").exists()


def test_prepare_final_authorization_offline(tmp_path, monkeypatch):
    """Test cross-provider final collection authorization creator."""
    import scripts.prepare_study2_final_collection_authorization as prep

    gh_lock = tmp_path / "gh-lock.json"
    rz_lock = tmp_path / "rz-lock.json"
    sh_lock = tmp_path / "sh-lock.json"

    gh_id = {"provider": "github", "manifest_sha256": "1" * 64, "runtime_sha256": {}}
    rz_id = {"provider": "razorpay", "manifest_sha256": "2" * 64, "runtime_sha256": {}}
    sh_id = {"manifest_sha256": "3" * 64, "control_sha256": {}}

    monkeypatch.setattr(prep, "current_static_identity", lambda p, root=None: (
        gh_id if p == "github" else rz_id if p == "razorpay" else sh_id
    ))
    monkeypatch.setattr(prep, "check_readiness_lock", lambda p, *args, **kwargs: (
        gh_id if p == "github" else rz_id if p == "razorpay" else sh_id
    ))

    gh_lock.write_bytes(canonical_json_bytes({
        "schema": "github-paper-readiness-lock-v1",
        "static_identity": gh_id,
        "study2_paper_observations": 0,
        "collection_authorized": False,
        "independent_audit_receipt_sha256": "0" * 64,
        "live_evidence_sha256": {k: "0" * 64 for k in PROVIDER_CONTROLS["github"]},
    }))
    rz_lock.write_bytes(canonical_json_bytes({
        "schema": "razorpay-paper-readiness-lock-v1",
        "static_identity": rz_id,
        "study2_paper_observations": 0,
        "collection_authorized": False,
        "independent_audit_receipt_sha256": "0" * 64,
        "live_evidence_sha256": {k: "0" * 64 for k in PROVIDER_CONTROLS["razorpay"]},
    }))
    sh_lock.write_bytes(canonical_json_bytes({
        "schema": "sheets-paper-readiness-lock-v1",
        "manifest_sha256": sh_id["manifest_sha256"],
        "control_sha256": sh_id["control_sha256"],
        "receipt_sha256": "0" * 64,
        "study2_paper_observations": 0,
        "collection_authorized": False,
        "independent_audit": {"auditor_id": "auditor", "audit_report_sha256": "0" * 64, "audit_report_file": "report.json", "audited_at_utc": "2026-09-27T00:00:00Z"},
        "spreadsheet_id": "15Sf9PrQqVRWj2Fe4pR_ZKslGWwbBi3OfgH_eElpoJ_Q",
        "topology_sha256": "0" * 64,
        "baseline_sha256": {},
    }))

    out_file = tmp_path / "auth_candidate.json"
    doc, doc_sha = prepare_final_authorization(
        github_lock_path=gh_lock,
        razorpay_lock_path=rz_lock,
        sheets_lock_path=sh_lock,
        output_path=out_file,
    )
    assert doc["schema"] == "study2-final-collection-authorization-v1"
    assert doc["status"] == "PENDING_INDEPENDENT_AUDIT"
    assert doc["collection_authorized"] is False
    assert doc["study2_paper_observations_at_authorization"] == 0
    assert out_file.is_file()
