"""Regression for actual cursor links and the isolated 179-arm continuation."""
from datetime import datetime, timezone
from dataclasses import replace
import json
from urllib.parse import urlsplit, parse_qs

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2 import github_remaining as remaining
from retry_semantics.study2 import provider_operator_launch as base
from retry_semantics.study2 import provider_paper_collection as collection
from retry_semantics.study2.provider_paper_io import PaperTransportResult
from test_study2_provider_operator_launch import API, completion, offline

PATH = "/repos/JashRashne/retry-semantics-study2-github-sandbox/issues"
CANONICAL = "/repositories/1374277504/issues"
CURSOR = "Y3Vyc29yOnYyOpLPAAABoK8qQKjPAAAAAUcKdas%3D"


def test_recorded_cursor_link_is_followed_verbatim_and_terminal_prev_works():
    target = f"https://api.github.com{CANONICAL}?state=all&per_page=100&page=2&after={CURSOR}"
    assert gh._next_url(f'<{target}>; rel="next"', 1, None, PATH) == (target, CANONICAL)
    prev = f"https://api.github.com{CANONICAL}?state=all&per_page=100&page=1&before={CURSOR}"
    assert gh._next_url(f'<{prev}>; rel="prev"', 2, CANONICAL, PATH) == (None, CANONICAL)


@pytest.mark.parametrize("suffix", ["&after=", "&after=%0A", "&after=x&after=y", "&before=x",
                                     "&since=1", "&after=x&state=open", "&after=x#fragment"])
def test_cursor_fix_does_not_accept_changed_or_unsafe_query(suffix):
    target = f"https://api.github.com{CANONICAL}?state=all&per_page=100&page=2{suffix}"
    with pytest.raises(gh.GitHubPaperError):
        gh._next_url(f'<{target}>; rel="next"', 1, None, PATH)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    c = root / "collection"
    c.mkdir(parents=True)
    manifest = base.manifest_for("github")
    base.write_once(root / "manifest.json", manifest)
    base.write_once(root / "summary.json", {"provider": "github", "state": "STOPPED", "dataset_role": base.ROLE})
    for i, (family, arm) in enumerate(collection._schedule(manifest)):
        aid, fid = arm["arm_id"], family["family_id"]
        if i >= 77 and i != 77 and i % 4 != 0:
            base.write_once(c / f"run-stopped-{i}.json", {"arm_id": aid, "executed": False,
                "reason": "family_invalidated_before_policy"})
            continue
        directory = c / f"{i:03d}"
        directory.mkdir()
        message = completion("create_issue", family["target_semantic_m"])["choices"][0]["message"]
        raw = canonical_json_bytes(message)
        base.write_once(directory / "original-m-binding.json", {"arm_id": aid, "family_id": fid,
            "original_message_hex": raw.hex(), "original_message_sha256": sha256_hex(raw)})
        if i % 4 == 0:
            base.write_once(directory / "model-original-0.json", {"assistant_message": message})
        if i < 77:
            base.write_once(directory / "policy-entry.json", {"arm_id": aid})
        else:
            base.write_once(directory / "arm-projection.json", {"policy_entered": False,
                "projection": {"reason": "pre_policy_baseline_or_run_stop"}})
    base.write_once(root / "inventory.json", base.inventory(root))
    return root


def test_selection_preserves_77_entered_arms_and_45_originals(source):
    identity, originals = remaining.source_selection(source)
    assert len(identity["selected_arm_ids"]) == 179 and len(originals) == 45
    assert identity["selected_arm_ids"][0] == "gh-f020:H0:LLM_REGENERATION"
    assert len(remaining.registry_for(identity["selected_arm_ids"])["reservations"]) == 179


def test_candidate_with_mutation_intent_is_refused_even_if_inventory_resealed(source):
    base.write_once(source / "collection/077/00000.intent.json", {"method": "POST"})
    (source / "inventory.json").write_bytes(canonical_json_bytes(base.inventory(source)))
    with pytest.raises(base.PaperCollectionError, match="mutation intent"):
        remaining.source_selection(source)


def test_source_evidence_change_is_refused(source):
    (source / "summary.json").write_text("{}")
    with pytest.raises(base.PaperCollectionError, match="inventory"):
        remaining.source_selection(source)


def test_full_remaining_launch_cursor_api_and_frozen_originals(tmp_path, monkeypatch, source):
    manifest = base.manifest_for("github")
    api = API("github", manifest)
    api.entries = [{"number": i+1, "title": "historical", "body": "historical", "state": "open"}
                   for i in range(101)]
    api.entries[0]["body"] += manifest["families"][0]["arms"][0]["suffix"]
    monkeypatch.setattr(base, "git_head", lambda: "a" * 40)
    monkeypatch.setattr(base, "claim_path", lambda p: tmp_path / "claims" / f"{p}.json")
    monkeypatch.setattr(base, "credentials", lambda p: ("fake", "fake"))
    monkeypatch.setattr(collection.time, "monotonic", lambda: api.now)
    monkeypatch.setattr(collection.time, "time", lambda: api.now)
    monkeypatch.setattr(collection.time, "sleep", lambda delay: setattr(api, "now", api.now+delay))
    monkeypatch.setattr(collection, "live_fireworks_completion", lambda key: api.complete)
    monkeypatch.setattr(base, "live_fireworks_completion", lambda key: api.complete)
    seen = []
    def send(req, **kwargs):
        seen.append(req)
        url = urlsplit(req.url)
        special = ({"id": 42, "login": "operator"} if url.path == "/user" else
                   {"resources": {"core": {"limit": 5000, "remaining": 4900}}} if url.path == "/rate_limit" else
                   {"id": 1374277504, "full_name": manifest["selected_repository"]} if url.path == "/repos/"+manifest["selected_repository"] else None)
        if special is not None:
            response = PaperTransportResult(200, (), canonical_json_bytes(special), None, True, True, True, api.now, api.now)
        else:
            response = api.send(req)
            if req.method == "GET":
                page = int(parse_qs(url.query)["page"][0])
                link = (f'<https://api.github.com{CANONICAL}?state=all&per_page=100&page={page+1}&after={CURSOR}>; rel="next"'
                        if page*100 < len(api.entries) else
                        f'<https://api.github.com{CANONICAL}?state=all&per_page=100&page={page-1}&before={CURSOR}>; rel="prev"')
                response = replace(response, headers=(("Link", link),))
        return replace(response, headers=response.headers+(("x-github-api-version-selected", "2022-11-28"),))
    monkeypatch.setattr(base, "ProviderTransport", lambda *a: lambda req: send(req))
    capture = base.capture_github_readiness
    monkeypatch.setattr(base, "capture_github_readiness", lambda **kw: capture(**kw,
        monotonic_fn=lambda: api.now, now_fn=lambda: datetime.fromtimestamp(api.now, timezone.utc)))
    plan = tmp_path / "remaining.plan.json"
    before = base.inventory(source)
    base.write_once(plan, remaining.build_plan(source, "operator"))
    result = remaining.run(plan, confirm_exclusive_writer=True, progress=lambda *a, **kw: None)
    assert result["state"] == "COMPLETED_SEGMENT", result
    assert result["evaluated_arms"] == 179
    assert api.model_originals == 0, "family original regenerated"
    assert remaining.verify(tmp_path / "github-remaining-run") == result
    assert base.inventory(source) == before
    assert any("after=" in r.url for r in seen)
    assert not list((tmp_path / "github-remaining-run/collection").glob("*/model-original-0.json"))
    with pytest.raises(base.PaperCollectionError, match="consumed"):
        remaining.run(plan, confirm_exclusive_writer=True)
