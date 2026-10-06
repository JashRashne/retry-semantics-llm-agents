"""Offline copied-input audit and partial request freeze; never runs recover()."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from retry_semantics.baselines import preparation, readiness
from retry_semantics.baselines.audit_closure import implementation_closure, replay_copies, write_json
from retry_semantics.baselines.schedule import build_schedule, validate_schedule
from retry_semantics.study2.sheets_paper_readiness import check_topology
from retry_semantics.serialization import canonical_json_bytes


def audit(directory: Path, *, freeze_available=False):
    audit_dir = directory / "source_binding_audit"
    mapping, proof = replay_copies(audit_dir)
    assert mapping == json.loads((audit_dir / "family_mapping.json").read_bytes())
    metadata = json.loads((audit_dir / "copy_manifest.json").read_bytes())
    sources = {key: dict(value, path=str(audit_dir / value["path"]))
               for key, value in metadata["sources"].items()}
    namespaces = json.loads((directory / "namespaces.json").read_bytes())
    entries, topology = build_schedule(mapping, sources, namespaces["github"], namespaces["sheets"])
    assert entries == json.loads((directory / "prospective_schedule.json").read_bytes())
    validate_schedule(entries, mapping, allow_unbound=True)
    valid = json.loads(Path(sources["S1"]["path"]).read_bytes())
    old_arms = [a for family in valid["families"] for a in family["arms"]]
    assert len(old_arms) == len({a["sheet_id"] for a in old_arms}) == 256
    # Synthetic metadata tests only the shape accepted by the unchanged checker.
    # It is explicitly NOT live topology readiness evidence.
    simulated = {"spreadsheetId": valid["spreadsheet_id"],
        "properties": {"title": valid["spreadsheet_title"]}, "sheets": [
            {"properties": {"sheetId": a["sheet_id"], "title": a["tab_title"],
                "sheetType": "GRID", "gridProperties": {"rowCount": 100, "columnCount": 3}}}
            for a in old_arms]}
    check_topology(valid, 200, canonical_json_bytes(simulated))
    result = {"source_proof": proof, "schedule_entries": len(entries),
        "schedule_unique_family_worlds": len({(e["source_set"], e["source_family_id"], e["hidden_world"]) for e in entries}),
        "schedule_physical_status": "SHEETS_UNBOUND_NOT_COLLECTABLE",
        "topology_inheritance": {"valid_replication_manifest_sha256": sources["S1"]["sha256"],
            "old_tabs": len(old_arms), "new_evaluation_tabs": 128, "new_reserved_tabs": 128,
            "unchanged_check_topology_requires": 256,
            "check_shape_test": "SYNTHETIC_OFFLINE_ONLY_NOT_PROVIDER_EVIDENCE"},
        "scientific_evaluations": 0, "scientific_mutations": 0}
    if freeze_available:
        target = directory / "available_request_bindings"
        if target.exists():
            raise ValueError("partial binding freeze already exists; no overwrite")
        target.mkdir()
        gh_manifest = json.loads(Path(sources["M1"]["path"]).read_bytes())
        tickets = {name: {e["family_id"]: e for e in readiness.ticket_originals(Path(sources[key]["path"]))}
                   for name, key in (("Study 1A", "A3"), ("Study 1B", "B3"))}
        bound, pending = [], []
        for entry in entries:
            if entry["source_set"] == "Sheets":
                pending.append(entry["schedule_index"])
                continue
            folder = target / f"{entry['schedule_index']:03d}"
            if entry["source_set"] == "GitHub":
                original = preparation.bind_github(manifest=gh_manifest,
                    source_original={"semantic": entry["semantic_target"]},
                    arm=entry["arm"], api_version="2022-11-28")
                preparation.store_github(folder, original)
                identity = original.sha256
            else:
                source = tickets[entry["source_set"]][entry["source_family_id"]]
                original = source["request"]
                write_json(folder / "stored-original.json", {
                    "serialized_request_hex": original.serialized_request.hex(),
                    "request_hash": original.request_hash,
                    "initial_snapshot_hex": source["initial_snapshot"].hex()})
                identity = original.request_hash
            bound.append(dict(entry, stored_original_file=str((folder / "stored-original.json").relative_to(target)),
                stored_original_file_sha256=readiness.file_digest(folder / "stored-original.json"),
                stored_request_identity_sha256=identity))
        write_json(target / "partial_bindings.json", {"status": "INCOMPLETE_NOT_COLLECTABLE",
            "bound": bound, "unbound_schedule_indices": pending,
            "bound_tickets": 640, "bound_github": 128, "bound_sheets": 0,
            "scientific_evaluations": 0})
        result["available_bindings"] = {"tickets": 640, "github": 128, "sheets": 0}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--freeze-available", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = audit(args.directory.resolve(), freeze_available=args.freeze_available)
    write_json(args.output, result)
    print(json.dumps({"families": result["source_proof"]["unique_family_counts"],
        "total_families": 448, "schedule_entries": 896,
        "physical_status": result["schedule_physical_status"], "scientific_evaluations": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
