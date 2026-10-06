"""Offline readiness tests; no historical/scheduled arm enters recovery."""
import ast
import inspect
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from retry_semantics.baselines import audit_closure, preparation, readiness, schedule
from retry_semantics.baselines import precollection_readiness as checks
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2.github_adapter import HTTPResponse
from retry_semantics.study2.sheets_paper_runner import certify_h1_constructor
from test_no_model_baseline import github_fixture, sheets_fixture, grid_response, sheets_ack
from retry_semantics.baselines.harness import certify_github_constructor

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "research/baselines/no_model/precollection_v2"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("network forbidden in offline precollection tests")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def inputs():
    folder = DIRECTORY / "source_binding_audit"
    metadata = json.loads((folder / "copy_manifest.json").read_bytes())
    sources = {key: dict(value, path=str(folder / value["path"]))
               for key, value in metadata["sources"].items()}
    mapping = json.loads((folder / "family_mapping.json").read_bytes())
    entries = json.loads((DIRECTORY / "prospective_schedule.json").read_bytes())
    topology = json.loads((DIRECTORY / "prospective_sheets_topology.json").read_bytes())
    return sources, mapping, entries, topology


def test_mapping_only_copies_all_448_exact_columns():
    table, proof = audit_closure.replay_copies(DIRECTORY / "source_binding_audit")
    assert table == inputs()[1]
    assert proof["unique_family_counts"] == schedule.SETS
    assert proof["copied_inputs_only"] and proof["total"] == 448
    columns = {"source_set", "family_id", "source_original_identity", "semantic_target", "source_path_or_archive_member"}
    assert all(set(row) == columns for row in table)
    assert all((DIRECTORY / "source_binding_audit" / p).is_file()
               for p in proof["pathlib_inputs_accessed"])


def test_mapping_tamper_refused_before_any_original_lookup(tmp_path):
    source = tmp_path / "source.json"
    source.write_bytes(b"modified")
    audit_closure.write_json(tmp_path / "copy_manifest.json", {
        "sources": {"A3": {"path": "source.json", "sha256": sha256_hex(b"expected")}},
        "copy_provenance": [], "historical_path_redirects": {}})
    with pytest.raises(ValueError, match="identity mismatch"):
        audit_closure.replay_copies(tmp_path)


def test_exact_896_unique_bound_source_identities():
    _, mapping, entries, _ = inputs()
    schedule.validate_schedule(entries, mapping, allow_unbound=True)
    assert {name: sum(e["source_set"] == name for e in entries) for name in schedule.SETS} == {
        "Study 1A": 320, "Study 1B": 320, "GitHub": 128, "Sheets": 128}
    assert len({(e["source_set"], e["source_family_id"], e["hidden_world"]) for e in entries}) == 896
    assert all(e["source_original_identity"] and e["semantic_target_sha256"] for e in entries)
    assert all("correctness" not in str(e.keys()) for e in entries)


@pytest.mark.parametrize("change", ["duplicate", "missing", "identity", "target", "marker"])
def test_schedule_adversarial_corruption_refused(change):
    _, mapping, entries, _ = inputs()
    if change == "duplicate":
        entries[1] = dict(entries[0], schedule_index=1)
    elif change == "missing":
        entries.pop()
    elif change == "identity":
        entries[0]["source_original_identity"] = "0" * 64
    elif change == "target":
        entries[0]["semantic_target"] = {"changed": "target"}
    else:
        entries[641]["provider_marker"] = entries[640]["provider_marker"]
    with pytest.raises(ValueError):
        schedule.validate_schedule(entries, mapping, allow_unbound=True)


def test_unbound_scope_refused_before_partial_full_freeze(tmp_path):
    sources, mapping, entries, topology = inputs()
    target = tmp_path / "bindings"
    with pytest.raises(ValueError, match="not frozen"):
        schedule.freeze_bindings(target, entries, sources, mapping=mapping, topology=topology)
    assert not target.exists()


def test_existing_output_cannot_overwrite(tmp_path):
    sources, mapping, entries, topology = inputs()
    target = tmp_path / "existing"
    target.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        schedule.freeze_bindings(target, entries, sources, mapping=mapping, topology=topology)
    audit_closure.write_json(target / "one.json", {"x": 1})
    with pytest.raises(FileExistsError):
        audit_closure.write_json(target / "one.json", {"x": 2})
    assert json.loads((target / "one.json").read_bytes()) == {"x": 1}


def test_128_fresh_github_exact_stored_originals():
    folder = DIRECTORY / "available_request_bindings"
    value = json.loads((folder / "partial_bindings.json").read_bytes())
    selected = [e for e in value["bound"] if e["source_set"] == "GitHub"]
    assert len(selected) == len({e["provider_marker"] for e in selected}) == 128
    manifest = json.loads(Path(inputs()[0]["M1"]["path"]).read_bytes())
    for entry in selected:
        path = folder / entry["stored_original_file"]
        assert readiness.file_digest(path) == entry["stored_original_file_sha256"]
        stored = preparation.load_github(path)
        expected = preparation.bind_github(manifest=manifest, arm=entry["arm"],
            source_original={"semantic": entry["semantic_target"]}, api_version="2022-11-28")
        assert stored == expected and stored.sha256 == entry["stored_request_identity_sha256"]
        assert json.loads(stored.body) == dict(entry["semantic_target"], body=entry["semantic_target"]["body"] + entry["arm"]["suffix"])


@pytest.mark.parametrize("defect", [None, "wrong_number", "wrong_semantics", "incomplete", "wrong_offset"])
def test_fresh_github_bridge_existing_h1_predicates(defect):
    manifest, arm, source, original = github_fixture("H1")
    family = {"family_id": "fixture", "target_semantic_m": source["semantic"]}
    row = {"number": 900, **json.loads(original.body), "state": "open"}
    ack = HTTPResponse(201, (), canonical_json_bytes(row))
    number, title, body = row["number"], row["title"], row["body"]
    if defect == "wrong_number": number += 1
    if defect == "wrong_semantics": title += " changed"
    census = gh.Census(defect != "incomplete", ((number, title, body),), 1,
                       "incomplete" if defect == "incomplete" else None, 1)
    rounds = (gh.ScheduledCensus(600 if defect == "wrong_offset" else 0, 0, 540, census),)
    with pytest.raises(gh.GitHubPaperError, match="absent from manifest"):
        gh.expected_original(manifest, family, arm, api_base="https://api.github.com", api_version="2022-11-28")
    if defect:
        with pytest.raises(ValueError):
            certify_github_constructor(manifest, family, arm, original, ack, rounds)
    else:
        certificate = certify_github_constructor(manifest, family, arm, original, ack, rounds)
        assert certificate.acknowledged_issue_number == 900 and certificate.original_request_sha256 == original.sha256


def test_fresh_sheets_h1_certification_only_synthetic():
    manifest, arm, source, original = sheets_fixture("H1")
    family = {"family_id": "fixture", "target_semantic_m": source["semantic"]}
    rows = [(arm["arm_marker"], *source["semantic"].values())]
    response = grid_response(arm, rows)
    certificate = certify_h1_constructor(manifest, family, arm, original, sheets_ack(arm),
        ("GET", arm["read_target"], 200, response.body))
    assert certificate.original_identity_sha256 == original.identity_hash
    assert certificate.arm_id == arm["arm_id"]
    changed = dict(arm, sheet_id=arm["sheet_id"] + 1)
    with pytest.raises(ValueError):
        certify_h1_constructor(manifest, family, changed, original, sheets_ack(arm),
            ("GET", arm["read_target"], 200, response.body))


def test_topology_128_evaluation_128_reserved_no_control_overlap():
    _, _, entries, topology = inputs()
    arms = [arm for f in topology["families"] for arm in f["arms"]]
    assert len(arms) == len({a["sheet_id"] for a in arms}) == 256
    reserved = {a["arm_id"] for a in arms if a["policy"] == "RESERVED_UNUSED"}
    assert len(reserved) == 128
    assert not reserved & {e["baseline_arm_id"] for e in entries}


def test_readiness_has_no_policy_or_evaluator_invocations():
    tree = ast.parse(inspect.getsource(checks))
    called = {getattr(node.func, "id", getattr(node.func, "attr", ""))
              for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert not {"recover", "github_recovery", "sheets_recovery", "evaluate_census", "run_ticket_arm"} & called
    evidence = json.loads((DIRECTORY / "github_readiness_network_access/readiness.json").read_bytes())
    assert evidence["readiness_only"] and evidence["scientific_evaluations"] == evidence["scientific_mutations"] == 0
    assert "final_correctness" not in evidence
    assert evidence["full_write_capability_qualification"] is False


def test_no_collection_mode_or_implicit_authorization():
    script = ROOT / "scripts/prepare_no_model_precollection.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert result.returncode == 2 and "required" in result.stderr
    result = subprocess.run([sys.executable, str(script), "collect", "--directory", str(DIRECTORY)], capture_output=True, text=True)
    assert result.returncode == 2 and "invalid choice" in result.stderr
    assert not (DIRECTORY / "frozen_bindings").exists()


def test_reviewed_files_byte_identical():
    identity = json.loads((ROOT / "research/baselines/no_model/implementation_identity.json").read_bytes())
    for path, expected in identity["files"].items():
        assert readiness.file_digest(ROOT / path) == expected


def test_all_transitive_required_modules_in_closure():
    entries = list((ROOT / "src/retry_semantics/baselines").glob("*.py"))
    entries += [ROOT / "scripts/prepare_no_model_precollection.py"]
    closure = audit_closure.implementation_closure(ROOT, entries)
    required = ["serialization", "study2/github_adapter", "study2/github_paper_manifest",
        "study2/sheets_offline", "study2/sheets_paper_http", "study2/sheets_paper_readiness",
        "study2/sheets_paper_materialize", "environments/ticket"]
    assert all("src/retry_semantics/" + path + ".py" in closure["files"] for path in required)
