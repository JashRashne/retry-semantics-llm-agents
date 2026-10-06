"""Prospective schedule and provider bindings, with no policy execution."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from retry_semantics.baselines import preparation, readiness
from retry_semantics.baselines.audit_closure import write_json
from retry_semantics.baselines.no_model import POLICY
from retry_semantics.serialization import canonical_json_bytes, sha256_hex

SETS = {"Study 1A": 160, "Study 1B": 160, "GitHub": 64, "Sheets": 64}


def build_schedule(mapping: list[dict], sources: dict, github_namespace: str,
                   sheets_namespace: str, spreadsheet_id: str = "UNBOUND") -> tuple[list, dict]:
    expected = {(name, row["family_id"]) for name in SETS for row in mapping if row["source_set"] == name}
    if len(mapping) != 448 or len(expected) != 448:
        raise ValueError("source population must have 448 unique families")
    for name, count in SETS.items():
        if sum(row["source_set"] == name for row in mapping) != count:
            raise ValueError("source count differs")
    manifests = {name: json.loads(Path(sources[key]["path"]).read_bytes())
                 for name, key in (("GitHub", "M1"), ("Sheets", "S1"))}
    old_markers = {name: {arm["arm_marker"] for f in m["families"] for arm in f["arms"]}
                   for name, m in manifests.items()}
    entries, physical_families = [], []
    for source_set in SETS:
        rows = sorted((row for row in mapping if row["source_set"] == source_set),
                      key=lambda row: row["family_id"])
        for family_index, row in enumerate(rows):
            source_family = (next(f for f in manifests[source_set]["families"]
                                 if f["family_id"] == row["family_id"])
                             if source_set in manifests else None)
            worlds = source_family["hidden_world_order"] if source_family else ["H0", "H1"]
            arms = []
            for ordinal, world in enumerate(worlds):
                identity = sha256_hex(canonical_json_bytes(row["semantic_target"]))
                entry = {"schedule_index": len(entries), "source_set": source_set,
                    "source_family_id": row["family_id"],
                    "source_original_identity": row["source_original_identity"],
                    "semantic_target": row["semantic_target"], "semantic_target_sha256": identity,
                    "hidden_world": world, "policy": POLICY, "provider_marker": None,
                    "fresh_physical_scope": None,
                    "baseline_arm_id": f"no-model:{source_set}:{row['family_id']}:{world}"}
                if source_set in manifests:
                    provider = "github" if source_set == "GitHub" else "sheets"
                    namespace = github_namespace if provider == "github" else sheets_namespace
                    arm = preparation.fresh_arm(namespace=namespace, family_id=row["family_id"],
                        hidden_world=world, provider=provider, old_markers=old_markers[source_set])
                    entry["baseline_arm_id"] = arm["arm_id"]
                    entry["provider_marker"] = arm["arm_marker"]
                    if provider == "github":
                        entry["fresh_physical_scope"] = manifests["GitHub"]["selected_repository"]
                    else:
                        arm, _ = preparation.bind_sheets(source_original={"semantic": row["semantic_target"]},
                            arm=arm, spreadsheet_id=spreadsheet_id, sheet_id=2 * family_index + ordinal + 1)
                        entry["fresh_physical_scope"] = {k: arm[k] for k in (
                            "spreadsheet_id", "sheet_id", "tab_title", "range", "read_target")}
                    entry["arm"] = arm
                    arms.append(arm)
                entries.append(entry)
            if source_set == "Sheets":
                # 128 unused scopes retain the inherited 256-tab topology. No
                # reserved arm belongs to the schedule or can be dispatched.
                for ordinal, world in enumerate(("H0", "H1")):
                    reserved = preparation.fresh_arm(namespace=sheets_namespace,
                        family_id="reserved:" + row["family_id"], hidden_world=world,
                        provider="sheets", old_markers=old_markers["Sheets"])
                    reserved, _ = preparation.bind_sheets(source_original={"semantic": row["semantic_target"]},
                        arm=reserved, spreadsheet_id=spreadsheet_id, sheet_id=129 + 2 * family_index + ordinal)
                    reserved["policy"] = "RESERVED_UNUSED"
                    arms.append(reserved)
                physical_families.append({"family_id": row["family_id"],
                    "target_semantic_m": row["semantic_target"], "user_task": source_family["user_task"],
                    "arms": arms})
    topology = {"schema": "post-feedback-no-model-sheets-topology-v1",
                "run_namespace": sheets_namespace, "spreadsheet_id": spreadsheet_id,
                "spreadsheet_title": "retry-semantics-no-model-baseline-" + sheets_namespace,
                "families": physical_families, "evaluation_tabs": 128, "reserved_tabs": 128}
    validate_schedule(entries, mapping, allow_unbound=spreadsheet_id == "UNBOUND")
    return entries, topology


def validate_schedule(entries: list[dict], mapping: list[dict], *, allow_unbound=False) -> None:
    if len(entries) != 896 or [e["schedule_index"] for e in entries] != list(range(896)):
        raise ValueError("exact 896-entry serial schedule required")
    by_source = {(r["source_set"], r["family_id"]): r for r in mapping}
    expected = {(name, family, world) for name, family in by_source for world in ("H0", "H1")}
    actual = {(e["source_set"], e["source_family_id"], e["hidden_world"]) for e in entries}
    if len(actual) != 896 or actual != expected:
        raise ValueError("duplicate or missing family/world entry")
    if len({e["baseline_arm_id"] for e in entries}) != 896:
        raise ValueError("duplicate baseline arm identity")
    for entry in entries:
        source = by_source[(entry["source_set"], entry["source_family_id"])]
        if (entry["source_original_identity"] != source["source_original_identity"]
                or entry["semantic_target"] != source["semantic_target"]
                or entry["semantic_target_sha256"] != sha256_hex(canonical_json_bytes(source["semantic_target"]))
                or entry["policy"] != POLICY):
            raise ValueError("source identity or target binding changed")
        if entry["source_set"] == "Sheets" and not allow_unbound:
            if entry["fresh_physical_scope"]["spreadsheet_id"] == "UNBOUND":
                raise ValueError("Sheets physical scope is not frozen")
    for name in ("GitHub", "Sheets"):
        markers = [e["provider_marker"] for e in entries if e["source_set"] == name]
        if len(markers) != len(set(markers)) or len(markers) != 128:
            raise ValueError("exactly 128 unique provider markers required")


def freeze_bindings(directory: Path, entries: list[dict], sources: dict,
                    *, mapping: list[dict], topology: dict) -> dict:
    """Store each original once, before any constructor or recovery dispatch."""
    if directory.exists():
        raise ValueError("binding directory already exists")
    # Refuse an incomplete physical freeze before producing partial files.
    validate_schedule(entries, mapping)
    directory.mkdir(parents=True)
    ticket_sets = {name: {e["family_id"]: e for e in readiness.ticket_originals(Path(sources[key]["path"]))}
                   for name, key in (("Study 1A", "A3"), ("Study 1B", "B3"))}
    github_manifest = json.loads(Path(sources["M1"]["path"]).read_bytes())
    frozen = copy.deepcopy(entries)
    for entry in frozen:
        arm_dir = directory / f"{entry['schedule_index']:03d}"
        arm_dir.mkdir()
        name = entry["source_set"]
        if name.startswith("Study 1"):
            source = ticket_sets[name][entry["source_family_id"]]
            request = source["request"]
            write_json(arm_dir / "stored-original.json", {
                "serialized_request_hex": request.serialized_request.hex(),
                "request_hash": request.request_hash,
                "initial_snapshot_hex": source["initial_snapshot"].hex()})
            identity = request.request_hash
        elif name == "GitHub":
            request = preparation.bind_github(manifest=github_manifest,
                source_original={"semantic": entry["semantic_target"]}, arm=entry["arm"],
                api_version="2022-11-28")
            preparation.store_github(arm_dir, request)
            identity = request.sha256
        else:
            arm = entry["arm"]
            if arm["spreadsheet_id"] == "UNBOUND":
                raise ValueError("cannot freeze unbound Sheets requests")
            _, request = preparation.bind_sheets(source_original={"semantic": entry["semantic_target"]},
                arm=arm, spreadsheet_id=arm["spreadsheet_id"], sheet_id=arm["sheet_id"])
            preparation.store_sheets(arm_dir, request)
            identity = request.identity_hash
        entry["stored_original_file"] = str((arm_dir / "stored-original.json").relative_to(directory))
        entry["stored_original_file_sha256"] = readiness.file_digest(arm_dir / "stored-original.json")
        entry["stored_request_identity_sha256"] = identity
    write_json(directory / "schedule.json", frozen)
    write_json(directory / "sheets_topology.json", topology)
    write_json(directory / "family_mapping.json", mapping)
    write_json(directory / "github_observer_authority.json", github_manifest)
    return {"entries": 896, "status": "BOUND_NOT_COLLECTED", "schedule_sha256": readiness.file_digest(directory / "schedule.json")}
