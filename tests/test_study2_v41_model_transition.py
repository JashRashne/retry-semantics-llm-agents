"""Offline proof that the pre-data amendment changes model identity only."""

import copy
import json
from pathlib import Path

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.github_paper_manifest import load_github_paper_manifest
from retry_semantics.study2.razorpay_paper_manifest import load_razorpay_paper_manifest
from retry_semantics.study2.sheets_paper_manifest_authority import load_authority
from retry_semantics.study2.sheets_paper_materialize import load_paper_manifest

ROOT = Path(__file__).resolve().parents[1]
MODEL = "accounts/fireworks/models/deepseek-v4p1-flash"


def _science_projection(value, *, sheets=False):
    value = copy.deepcopy(value)
    for key in ("status", "audit_provenance", "model_amendment_sha256", "manifest_id"):
        value.pop(key, None)
    if sheets:
        for decision, field in (("model", "name"), ("execution", "manifest_id")):
            value["decisions"][decision].pop("provenance", None)
            value["decisions"][decision]["value"].pop(field, None)
    else:
        for family in value["families"]:
            config = family["model_config"]
            config.pop("model_config_id", None)
            config["model"].pop("name", None)
    return sha256_hex(canonical_json_bytes(value))


def test_amendment_is_predata_and_nonpaper_capability_is_not_readiness():
    amendment = json.loads((ROOT / "research/protocol/STUDY2_V41_MODEL_AMENDMENT_V1.json").read_bytes())
    assert amendment["original_model"] == "accounts/fireworks/models/deepseek-v4-flash-0731"
    assert amendment["replacement_model"] == MODEL
    assert amendment["study2_paper_observations_at_amendment"] == 0
    assert amendment["provider_protocol_science_change"] is False
    assert amendment["readiness_model_capability_substitute"] is False
    assert amendment["status"] == "PREDATA_PENDING_INDEPENDENT_AUDIT"


def test_github_and_razorpay_science_projections_unchanged():
    github = load_github_paper_manifest().as_json()
    razorpay = load_razorpay_paper_manifest()
    assert _science_projection(github) == "502d9c4bbb886144ade653816d535d4186f2e6823ec5f949d114687c3d2823d6"
    assert _science_projection(razorpay) == "323d7b786f63106cd0a60e5aa4de5d1d3bf64b16bec6f969b8e1622d87f083d5"
    for manifest in (github, razorpay):
        assert manifest["study2_paper_observations"] == 0
        assert manifest["collection_status"] == "BLOCKED"
        assert len(manifest["families"]) == 64
        assert all(f["model_config"]["model"]["name"] == MODEL
                   for f in manifest["families"])


def test_sheets_authority_science_projection_unchanged():
    authority = load_authority()
    assert _science_projection(authority, sheets=True) == "84bf3713454eb1f5b2a3e2c7cd9ba6cbcc62bd9f538d9964ff10da8df12ca4a7"
    assert authority["decisions"]["model"]["value"]["name"] == MODEL
    assert authority["decisions"]["execution"]["value"]["study2_paper_observations"] == 0


def test_sheets_materialized_manifest_is_v41_and_predata():
    manifest = load_paper_manifest()
    assert manifest["collection_status"] == "BLOCKED"
    assert manifest["study2_paper_observations"] == 0
    assert len(manifest["families"]) == 64
    assert all(family["model_config"]["model"]["name"] == MODEL
               for family in manifest["families"])
    science = copy.deepcopy(manifest)
    for key in ("implementation_sha256", "manifest_authority_sha256",
                "model_amendment_sha256", "manifest_id"):
        science.pop(key, None)
    for family in science["families"]:
        family["model_config"].pop("model_config_id")
        family["model_config"]["model"].pop("name")
    assert sha256_hex(canonical_json_bytes(science)) == (
        "55a1ba8731820f050d81fac55a2f47f4d91832fe06c95cb75b8daefd0a3642ef"
    )
