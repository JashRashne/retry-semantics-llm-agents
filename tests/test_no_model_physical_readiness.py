"""Synthetic non-scientific provider qualification; no live transport."""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from retry_semantics.baselines import physical_readiness as physical
from retry_semantics.baselines.precollection_readiness import ReadinessRefused
from retry_semantics.baselines.precollection_readiness import provision_sheets
from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2.provider_paper_io import PaperTransportResult
from retry_semantics.study2.github_paper_manifest import load_github_paper_manifest
from test_no_model_precollection import inputs
from test_no_model_baseline import grid_response

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def response(body, status=200, error=None):
    return PaperTransportResult(status, (), canonical_json_bytes(body), error,
        True, True, True, 0, 0)


@pytest.mark.parametrize("ambiguous", [False, True])
def test_github_one_non_scientific_control_never_scheduled_marker(tmp_path, ambiguous):
    sources, _, entries, _ = inputs()
    manifest = load_github_paper_manifest().as_json()
    scientific_markers = {e["provider_marker"] for e in entries if e["source_set"] == "GitHub"}
    rows, posts = [], []
    def send(req):
        if req.method == "POST":
            posts.append(req)
            assert "[QUALIFICATION CONTROL]" in json.loads(req.body)["title"]
            assert not any(marker in req.body.decode() for marker in scientific_markers)
            row = dict(json.loads(req.body), number=9000, state="open")
            rows.append(row)
            return response(row, 201, "TimeoutError" if ambiguous else None)
        if req.url.endswith("/permission"):
            return response({"permission": "admin"})
        if req.url.endswith("/user"):
            return response({"login": "JashRashne", "id": 1})
        if req.url.endswith("/rate_limit"):
            return response({"resources": {"core": {"remaining": 5000, "reset": int(time.time()) + 3600}}})
        if "issues?" in req.url:
            return response(rows)
        return response({"full_name": manifest["selected_repository"], "private": True,
            "has_issues": True, "owner": {"login": "JashRashne"}, "id": 1})
    kwargs = dict(directory=tmp_path / "control", manifest=manifest, entries=entries,
        namespace="a" * 32, send=send, attestation={"exclusive_writing_no_scripts_automation": True}, clock=lambda: 0)
    if ambiguous:
        with pytest.raises(ReadinessRefused, match="never resend"):
            physical.github_qualification(**kwargs)
        assert not (tmp_path / "control/final_readiness.json").exists()
    else:
        result = physical.github_qualification(**kwargs)
        assert result["status"] == "FULL_PROVIDER_READINESS_PASS"
        assert result["scientific_mutations"] == result["scientific_evaluations"] == 0
    assert len(posts) == 1


@pytest.mark.parametrize("ambiguous", [False, True])
def test_sheets_separate_four_tab_scope_exact_placement_no_retry(tmp_path, ambiguous):
    sources, _, _, topology = inputs()
    topology = dict(topology, spreadsheet_id="synthetic-baseline")
    base = json.loads(Path(sources["S1"]["path"]).read_bytes())
    rows, posts = [], []
    principal = {"permission_id": "synthetic"}
    folder = tmp_path / "qualification"
    class Session:
        token = SimpleNamespace(value="synthetic-bearer", expires_at=3600, clock_uncertainty_seconds=1)
        app_identity = "synthetic-app"
        def ensure(self, reserve): assert reserve == 180
        def send(self, request):
            assert "synthetic-baseline" not in request.url
            if request.method == "POST":
                posts.append(request)
                data = json.loads(request.body)
                if ":batchUpdate" not in request.url:
                    assert len(data["sheets"]) == 4
                    return response(dict(data, spreadsheetId="synthetic-qualification"))
                cell_values = data["requests"][0]["appendCells"]["rows"][0]["values"]
                row = tuple(cell["userEnteredValue"]["stringValue"] for cell in cell_values)
                scheduled = {a["arm_marker"] for f in topology["families"] for a in f["arms"]}
                assert row[0] not in scheduled
                rows.append(row)
                return response({"spreadsheetId": "synthetic-qualification", "replies": [{}]},
                    error="TimeoutError" if ambiguous else None)
            arm = json.loads((folder / "control_identity.json").read_bytes())["arm"]
            raw = grid_response(arm, rows)
            return PaperTransportResult(200, (), raw.body, None, True, True, True, 0, 0)
    kwargs = dict(directory=folder, topology=topology, base_manifest=base, namespace="b" * 32,
        session=Session(), verify_access=lambda *args: principal,
        baseline_principal=principal, wall=lambda: 0, clock=lambda: 0)
    if ambiguous:
        with pytest.raises(ValueError):
            physical.sheets_qualification(**kwargs)
        assert len(posts) == 2  # create + first ambiguous append; no second append
        assert not (folder / "qualification_pass.json").exists()
    else:
        result = physical.sheets_qualification(**kwargs)
        assert len(posts) == 3
        assert posts[1] == posts[2]
        assert result["status"] == "APPEND_PLACEMENT_VISIBILITY_PASS"
        assert result["scheduled_baseline_tabs_written"] == result["reserved_tabs_written"] == 0
        assert result["scientific_evaluations"] == result["scientific_mutations"] == 0


def test_actual_frozen_256_topology_serializes_before_oauth(tmp_path):
    _, _, _, topology = inputs()
    events, sent = [], []
    principal = {"permission_id": "synthetic"}
    metadata = SimpleNamespace(projection=lambda: {"public_config_sha256": "synthetic-app"})
    token = SimpleNamespace(value="synthetic", expires_at=4000, clock_uncertainty_seconds=1)
    def acquire():
        events.append("acquire")
        return token, metadata
    def transport(req, credential):
        events.append("create")
        sent.append(req)
        data = json.loads(req.body)
        return response(dict(data, spreadsheetId="synthetic-created"))
    result = provision_sheets(topology=topology, directory=tmp_path, acquire=acquire,
        transport=transport, verify_access=lambda *args: principal,
        writer_attestation={"exclusive_writing_no_scripts_automation": True},
        clock=lambda: 0, wall=lambda: 0, sleep=lambda _: None)
    assert events == ["acquire", "create"] and len(sent) == 1
    payload = json.loads(sent[0].body)
    assert len(payload["sheets"]) == 256
    expected = [(a["sheet_id"], a["tab_title"]) for f in topology["families"] for a in f["arms"]]
    assert [(s["properties"]["sheetId"], s["properties"]["title"]) for s in payload["sheets"]] == expected
    assert all(s["properties"]["gridProperties"] == {"rowCount": 100, "columnCount": 3}
               for s in payload["sheets"])
    assert "scheduled_attempt_index" not in topology["families"][0]
    assert result["spreadsheet_id"] == "synthetic-created"


def test_github_read_only_continuation_no_second_post(tmp_path):
    manifest = load_github_paper_manifest().as_json()
    _, _, entries, _ = inputs()
    rows = []
    post_count = []
    def send(req):
        if req.method == "POST":
            post_count.append(1)
            row = dict(json.loads(req.body), number=900, state="open")
            rows.append(row)
            return response(row, 201)
        if req.url.endswith("/permission"):
            return response({"permission": "admin"})
        if req.url.endswith("/user"):
            return response({"login": "JashRashne", "id": 1})
        if req.url.endswith("/rate_limit"):
            return response({"resources": {"core": {"remaining": 5000, "reset": int(time.time()) + 3600}}})
        if "issues?" in req.url:
            return response([])  # successful POST is initially invisible
        return response({"full_name": manifest["selected_repository"], "private": True,
            "has_issues": True, "owner": {"login": "JashRashne"}, "id": 1})
    prior = tmp_path / "prior"
    with pytest.raises(ReadinessRefused, match="visibility"):
        physical.github_qualification(directory=prior, manifest=manifest, entries=entries,
            namespace="a" * 32, send=send,
            attestation={"exclusive_writing_no_scripts_automation": True}, clock=lambda: 0)
    def visible_get(req):
        assert req.method == "GET"
        return response(rows) if "issues?" in req.url else send(req)
    result = physical.continue_github_visibility(prior=prior, directory=tmp_path / "continuation",
        manifest=manifest, entries=entries, send=visible_get,
        attestation={"exclusive_writing_no_scripts_automation": True}, clock=lambda: 600)
    assert post_count == [1]
    assert result["status"] == "FULL_PROVIDER_READINESS_PASS"
    assert result["readiness_qualification_mutations_in_continuation"] == 0
