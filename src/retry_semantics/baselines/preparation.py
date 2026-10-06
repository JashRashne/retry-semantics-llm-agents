"""Offline binding and persistence of fresh provider originals; no transport."""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from retry_semantics.baselines.harness import write_once
from retry_semantics.baselines.no_model import POLICY
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2.sheets_paper_adapter import prepare_paper_append
from retry_semantics.study2.sheets_paper_materialize import read_target
from retry_semantics.study2.sheets_paper_runner import store_original


def fresh_arm(*, namespace: str, family_id: str, hidden_world: str, provider: str,
              old_markers: set[str]) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", namespace) or hidden_world not in ("H0", "H1"):
        raise ValueError("invalid new namespace or construction")
    if provider not in ("github", "sheets"):
        raise ValueError("provider outside baseline scope")
    token = sha256_hex(canonical_json_bytes(["post-feedback-no-model-v1", namespace,
                                           provider, family_id, hidden_world]))[:32]
    marker = ("rs2gh1-" if provider == "github" else "RS2-SHEETS-V1-") + token
    if marker in old_markers:
        raise ValueError("namespace collides with historical attribution")
    arm = {"family_id": family_id, "arm_id": f"no-model:{namespace}:{family_id}:{hidden_world}",
           "hidden_world": hidden_world, "policy": POLICY, "arm_marker": marker}
    if provider == "github":
        arm["suffix"] = f"\n\n<!-- retry-semantics-study2-gh:v1:{marker} -->"
    return arm


def bind_github(*, manifest: dict, source_original: dict, arm: dict, api_version: str):
    """Rebind only the harness attribution suffix using existing Replay serializer."""
    semantic = source_original["semantic"]
    return gh.serialize_create(manifest, arm, **semantic,
                               api_base="https://api.github.com", api_version=api_version)


def bind_sheets(*, source_original: dict, arm: dict, spreadsheet_id: str, sheet_id: int):
    """Rebind scope/marker once before construction, then freeze W for recovery."""
    arm = dict(arm, spreadsheet_id=spreadsheet_id, sheet_id=sheet_id,
               tab_title=f"NMB_{sheet_id:03d}", range="A1:C100")
    arm["read_target"] = read_target(spreadsheet_id, arm["tab_title"])
    original = prepare_paper_append(arm, **source_original["semantic"])
    return arm, original


def store_github(directory: Path, original: gh.FrozenIssueRequest) -> None:
    value = asdict(original)
    value["body_hex"] = value.pop("body").hex()
    value["headers"] = [list(header) for header in original.headers]
    write_once(directory, "stored-original.json", {"request": value, "identity_sha256": original.sha256})


def load_github(path: Path) -> gh.FrozenIssueRequest:
    if path.is_symlink():
        raise ValueError("symlinked stored original")
    value = json.loads(path.read_bytes())
    request = value["request"]
    original = gh.FrozenIssueRequest(request["method"], request["url"],
        tuple(tuple(h) for h in request["headers"]), bytes.fromhex(request["body_hex"]),
        request["arm_id"], request["marker"])
    if original.sha256 != value["identity_sha256"]:
        raise ValueError("stored original identity changed")
    return original


def store_sheets(directory: Path, original) -> None:
    # Existing exclusive persistence/load_original machinery is the authority.
    directory.mkdir(parents=True, exist_ok=True)
    store_original(directory / "stored-original.json", original)
