"""Launcher checks and synthetic offline arms, never scheduled scientific arms."""
import importlib.util
import inspect
import json
from pathlib import Path
import socket
import sys

import pytest

from retry_semantics.baselines import collection, preparation, readiness
from retry_semantics.baselines.collection_lock import freeze_lock
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.provider_paper_io import PaperTransportResult
from retry_semantics.study2.sheets_paper_readiness import check_topology
from test_no_model_baseline import github_fixture, sheets_fixture, grid_response

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "research/baselines/no_model/precollection_v3"


@pytest.fixture(autouse=True)
def no_network_or_model(monkeypatch):
    from retry_semantics.models.fireworks import FireworksModelClient
    from retry_semantics.models.groq import GroqModelClient
    from retry_semantics.study2.provider_paper_model import PaperModelSession
    calls = []
    def prohibited(*args, **kwargs):
        calls.append(1)
        raise AssertionError("network/model forbidden in launcher offline tests")
    monkeypatch.setattr(socket.socket, "connect", prohibited)
    monkeypatch.setattr(socket, "create_connection", prohibited)
    monkeypatch.setattr(FireworksModelClient, "complete", prohibited)
    monkeypatch.setattr(GroqModelClient, "complete", prohibited)
    monkeypatch.setattr(PaperModelSession, "_call", prohibited)
    yield
    assert calls == []


def transport_result(body, status=200, error=None):
    return PaperTransportResult(status, (), canonical_json_bytes(body), error,
        True, True, True, 0, 0)


def test_launcher_refuses_before_bindings_credentials_or_output(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("launcher_test", ROOT / "scripts/collect_no_model_baseline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "verified_package", lambda *a, **k: pytest.fail("unauthorized launch accessed bindings"))
    output = tmp_path / "output"
    with pytest.raises(collection.CollectionRefused, match="authorization"):
        module.main(["collect", "--bindings", str(tmp_path / "absent"), "--lock", str(tmp_path / "absent-lock"),
            "--lock-sha256", "0" * 64, "--output", str(output)])
    assert not output.exists()
    with pytest.raises(SystemExit) as exc:
        module.main([])
    assert exc.value.code == 2
    with pytest.raises(collection.CollectionRefused):
        collection.require_authorization("not-an-authorization")


def test_complete_896_package_and_exact_requests(tmp_path):
    path = tmp_path / "lock.json"
    lock = freeze_lock(ROOT, V3, path)
    package = collection.verified_package(V3 / "frozen_bindings", path, readiness.file_digest(path), root=ROOT)
    assert len(package["schedule"]) == 896
    assert len({(e["source_set"], e["source_family_id"], e["hidden_world"]) for e in package["schedule"]}) == 896
    assert all(e.get("fresh_physical_scope", {}).get("spreadsheet_id") != "UNBOUND"
               for e in package["schedule"] if e["source_set"] == "Sheets")
    assert lock["scientific_evaluations"] == lock["scientific_mutations"] == 0
    assert not (V3 / "frozen_bindings/COLLECTION_CONSUMED.json").exists()


@pytest.mark.parametrize("world", ["H0", "H1"])
def test_ticket_exact_constructor_once_fresh_clone(world, make_request, monkeypatch):
    original = make_request(title="Synthetic launcher ticket fixture")
    initial = collection.TicketEnvironment.empty().snapshot_bytes()
    events = []
    real = collection.TicketEnvironment.execute_request
    def tracked(self, raw, **kwargs):
        events.append((raw, kwargs["source_stage"]))
        return real(self, raw, **kwargs)
    monkeypatch.setattr(collection.TicketEnvironment, "execute_request", tracked)
    entry = {"hidden_world": world}
    snapshot, _ = collection.construct_ticket(entry, original, initial)
    assert len(events) == int(world == "H1")
    if events:
        assert events == [(original.serialized_request, collection.SourceStage.ORIGINAL)]
    assert len(collection.TicketEnvironment.clone_from_snapshot(snapshot).state.tickets) == int(world == "H1")
    assert collection.TicketEnvironment.clone_from_snapshot(initial).state.tickets == ()


def fixture_package(tmp_path, provider, world):
    if provider == "GitHub":
        manifest, arm, source, original = github_fixture(world)
    else:
        manifest, arm, source, original = sheets_fixture(world)
    entry = {"schedule_index": 0, "source_set": provider, "source_family_id": "SYNTHETIC_FIXTURE",
        "hidden_world": world, "arm": arm, "baseline_arm_id": arm["arm_id"],
        "semantic_target": source["semantic"], "stored_original_file": "stored/stored-original.json"}
    binding = tmp_path / "bindings"
    if provider == "GitHub": preparation.store_github(binding / "stored", original)
    else: preparation.store_sheets(binding / "stored", original)
    package = {"binding_dir": binding, "github_manifest": manifest, "sheets_topology": manifest,
        "lock": {"schedule_sha256": "0" * 64, "runtime_files": {}, "github_repository_id": 1}}
    return package, entry, original


@pytest.mark.parametrize("provider", ["GitHub", "Sheets"])
@pytest.mark.parametrize("world", ["H0", "H1"])
def test_complete_synthetic_provider_arm_one_original_max_one_recovery(tmp_path, provider, world):
    package, entry, original = fixture_package(tmp_path, provider, world)
    rows, posts = [], []
    arm = entry["arm"]
    def send(request):
        if request.method == "POST":
            posts.append(request)
            assert request.body == original.body
            if provider == "GitHub":
                rows.append(dict(json.loads(request.body), number=900, state="open"))
                return transport_result(rows[0], 201)
            rows.append((arm["arm_marker"], *entry["semantic_target"].values()))
            return transport_result({"spreadsheetId": arm["spreadsheet_id"], "replies": [{}]})
        if provider == "GitHub": return transport_result(rows)
        grid = grid_response(arm, rows)
        return PaperTransportResult(200, (), grid.body, None, True, True, True, 0, 0)
    now = [0]
    directory = tmp_path / "arm"
    directory.mkdir()
    result, stop = collection.execute_arm(entry, directory, package, github_send=send, sheets_send=send,
        before_provider_family=lambda *args: None, clock=lambda: now[0],
        wait_until=lambda target: now.__setitem__(0, target))
    assert not stop and result["final_correctness"] is True
    assert result["original_dispatch_count"] == int(world == "H1")
    assert result["write_count"] == int(world == "H0")
    assert len(posts) == 1 and result["read_count"] == 1 and result["model_call_count"] == 0
    assert arm["arm_marker"] not in str(result["observation"])
    assert "900" not in str(result["observation"])


@pytest.mark.parametrize("provider", ["GitHub", "Sheets"])
def test_synthetic_list_failure_stops_without_recovery_create(tmp_path, provider):
    package, entry, original = fixture_package(tmp_path, provider, "H0")
    calls, posts = [], []
    def send(request):
        calls.append(request)
        if request.method == "POST":
            posts.append(request)
            pytest.fail("LIST failure dispatched recovery CREATE")
        if len(calls) == 2:
            return transport_result({}, 503, "TimeoutError")
        if provider == "GitHub": return transport_result([])
        grid = grid_response(entry["arm"], [])
        return PaperTransportResult(200, (), grid.body, None, True, True, True, 0, 0)
    now = [0]
    directory = tmp_path / "arm"
    directory.mkdir()
    result, stop = collection.execute_arm(entry, directory, package, github_send=send, sheets_send=send,
        before_provider_family=lambda *args: None, clock=lambda: now[0],
        wait_until=lambda target: now.__setitem__(0, target))
    assert result["decision"] == "STOP" and result["intended_visible"] is None
    assert result["write_count"] == 0 and result["read_count"] == 1 and not posts


def synthetic_schedule():
    return [{"schedule_index": i, "source_set": "SYNTHETIC_NOT_SCIENTIFIC",
        "source_family_id": f"fixture-{i // 2}", "hidden_world": "H0" if i % 2 == 0 else "H1",
        "baseline_arm_id": f"synthetic-{i}"} for i in range(896)]


def test_stop_retains_896_opportunities_no_refill_serial(tmp_path):
    entries = synthetic_schedule()
    visited = []
    def execute(entry, directory):
        visited.append(entry["schedule_index"])
        result = collection._unrun(entry, "synthetic stub; no policy invoked")
        result["opportunity_status"] = "SYNTHETIC_EXECUTOR_STUB"
        return result, entry["schedule_index"] == 1
    summary = collection.run_serial(entries, tmp_path / "output", execute)
    assert visited == [0, 1]  # no policy invocation at all; 894 retained UNRUN
    assert summary["records"] == 896 and summary["unrun"] == 894 and summary["model_calls"] == 0
    assert len(list((tmp_path / "output").glob("*/result.json"))) == 896
    assert json.loads((tmp_path / "output/895/result.json").read_bytes())["opportunity_status"] == "UNRUN"
    with pytest.raises(collection.CollectionRefused, match="overwrite/resume"):
        collection.run_serial(entries, tmp_path / "output", lambda *args: pytest.fail("existing output executed"))


@pytest.mark.parametrize("provider", ["GitHub", "Sheets"])
def test_access_stop_blocks_further_dispatch_and_recovery(tmp_path, provider):
    package, entry, original = fixture_package(tmp_path, provider, "H0")
    calls = []
    def send(request):
        calls.append(request)
        if len(calls) == 2:
            return transport_result({}, 403)
        if provider == "GitHub": return transport_result([])
        grid = grid_response(entry["arm"], [])
        return PaperTransportResult(200, (), grid.body, None, True, True, True, 0, 0)
    directory = tmp_path / "arm"
    directory.mkdir()
    result, stop = collection.execute_arm(entry, directory, package, github_send=send, sheets_send=send,
        before_provider_family=lambda *args: None, clock=lambda: 0, wait_until=lambda _: pytest.fail("sleep after stop"))
    assert stop and len(calls) == 2
    assert result["write_count"] == 0 and result["unknown_unscorable"]


def test_failed_attempt_gate_namespace_and_old_evidence_unchanged():
    proof = json.loads((V3 / "preserved_before.json").read_bytes())["files"]
    assert all(readiness.file_digest(ROOT / name) == expected for name, expected in proof.items())
    assert readiness.verify_protected(ROOT / "research/baselines/no_model/protected_before.json") == 5942
    assert not any("model" in name for name in inspect.signature(collection.execute_arm).parameters)


def test_qualification_controls_do_not_overlap_scientific_markers_or_scope():
    entries = json.loads((V3 / "frozen_bindings/schedule.json").read_bytes())
    gh_markers = {e["provider_marker"] for e in entries if e["source_set"] == "GitHub"}
    sheet_markers = {e["provider_marker"] for e in entries if e["source_set"] == "Sheets"}
    gh = json.loads((V3 / "github_write_visibility_qualification/control_identity.json").read_bytes())
    sheet = json.loads((V3 / "sheets_readiness_serialization_fixed/separate_append_qualification/control_identity.json").read_bytes())
    assert gh["arm"]["arm_marker"] not in gh_markers
    assert sheet["arm"]["arm_marker"] not in sheet_markers
    assert sheet["arm"]["spreadsheet_id"] != entries[-1]["arm"]["spreadsheet_id"]
    assert len([json.loads(p.read_bytes()) for p in V3.rglob("*.result.json")
                if json.loads(p.read_bytes()).get("method") == "POST"]) == 5
