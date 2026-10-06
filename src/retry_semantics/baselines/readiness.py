"""Read-only inspection of locked originals; never dispatch or evaluate a baseline."""
from __future__ import annotations

import hashlib
import json
import tarfile
from collections import Counter
from pathlib import Path

from retry_semantics.environments.ticket import FrozenExecutableRequest, TicketEnvironment
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_paper_runner import load_original


def file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verified_sources(registry: Path) -> dict:
    sources = json.loads(registry.read_bytes())
    for key, source in sources.items():
        if file_digest(Path(source["path"])) != source["sha256"]:
            raise ValueError("frozen source changed: " + key)
    return sources


def verify_protected(inventory: Path) -> int:
    values = json.loads(inventory.read_bytes())
    for path, expected in values.items():
        if file_digest(Path(path)) != expected:
            raise ValueError("protected file changed: " + path)
    return len(values)


def ticket_originals(path: Path) -> list[dict]:
    """Recover M and the *initial* state; never use an old terminal state."""
    families = {}
    seen = set()
    for line in path.read_text().splitlines():
        trace = json.loads(line)
        ids, frozen, evaluator = trace["identifiers"], trace["frozen_original"], trace["evaluator_only"]
        raw = frozen["serialized_original_request"].encode("utf-8")
        request = FrozenExecutableRequest(raw, frozen["original_request_hash"])
        if not frozen["eligibility_verified"] or json.loads(raw)["tool"] != "create_ticket":
            raise ValueError("ineligible original")
        initial = canonical_json_bytes(evaluator["initial_state"])
        if sha256_hex(initial) != evaluator["initial_state_hash"]:
            raise ValueError("initial state hash mismatch")
        if TicketEnvironment.clone_from_snapshot(initial).state.tickets:
            raise ValueError("unexpected nonempty controlled initial state")
        family = ids["trial_family_id"]
        identity = (family, evaluator["hidden_world"], trace["recovery_policy"])
        if identity in seen:
            raise ValueError("duplicate old arm")
        seen.add(identity)
        entry = {"family_id": family, "trial_id": ids["base_trial_id"],
                 "scenario_id": ids["scenario_id"], "request": request,
                 "initial_snapshot": initial}
        if family in families and families[family] != entry:
            raise ValueError("family original or initial state changed across arms")
        families[family] = entry
    if len(families) != 160 or len(seen) != 640:
        raise ValueError("incomplete frozen ticket set")
    worlds = {"NOT_EXECUTED", "EXECUTED_ACK_LOST"}
    if seen != {(f, w, p) for f in families for w in worlds
                for p in ("EXACT_REPLAY", "LLM_REGENERATION")}:
        raise ValueError("unexpected frozen ticket arm allocation")
    return list(families.values())


def provider_originals(sources: dict) -> dict[str, list[dict]]:
    """Verify all canonical W/M bindings, including the split GitHub family 20.

    The canonical ledger chooses sources only; no score enters policy inputs.
    Read archive members in memory, never extract them into old run directories.
    """
    ledger = [json.loads(line) for line in Path(sources["E1"]["path"]).read_text().splitlines()]
    rows = [r for r in ledger if r["provider"] == "github" or
            (r["provider"] == "sheets" and r["dataset_id"] == "sheets_replication")]
    index = json.loads(Path(sources["E9"]["path"]).read_bytes())["files"]
    member_hashes = {r["archive_member"]: r["sha256"] for r in index if r["archive_member"]}
    wanted = set()
    for row in rows:
        if row["provider"] == "github":
            parent = row["archive_member"].rsplit("/", 1)[0]
            wanted.update(parent + "/" + name for name in ("frozen-W-arm.json", "original-m-binding.json"))
    members = {}
    with tarfile.open(sources["G1"]["path"], "r|gz") as archive:
        for member in archive:
            if member.name in wanted:
                if not member.isfile():
                    raise ValueError("non-file source archive member")
                raw = archive.extractfile(member).read()
                if sha256_hex(raw) != member_hashes[member.name]:
                    raise ValueError("archive source hash mismatch")
                members[member.name] = json.loads(raw)
    if set(members) != wanted:
        raise ValueError("missing provider original source")
    result = {"github": {}, "sheets": {}}
    manifests = {
        "github": json.loads(Path(sources["M1"]["path"]).read_bytes()),
        "sheets": json.loads(Path(sources["S1"]["path"]).read_bytes()),
    }
    for row in rows:
        provider, family_id = row["provider"], row["family_id"]
        family = next(f for f in manifests[provider]["families"] if f["family_id"] == family_id)
        arm = next(a for a in family["arms"] if a["arm_id"] == row["arm_id"])
        if provider == "github":
            parent = row["archive_member"].rsplit("/", 1)[0]
            w = members[parent + "/frozen-W-arm.json"]
            binding = members[parent + "/original-m-binding.json"]
            raw_m = bytes.fromhex(binding["original_message_hex"])
            if sha256_hex(raw_m) != row["original_m_sha256"]:
                raise ValueError("GitHub family M hash mismatch")
            original_message = json.loads(raw_m)
            body = bytes.fromhex(w["body_hex"])
            if sha256_hex(body) != row["frozen_w_body_sha256"]:
                raise ValueError("GitHub W body hash mismatch")
            sent = json.loads(body)
            if not sent["body"].endswith(arm["suffix"]):
                raise ValueError("GitHub source attribution mismatch")
            semantic = {"title": sent["title"], "body": sent["body"][:-len(arm["suffix"])]}
        else:
            parent = Path(row["source_projection_path"]).parent
            original = load_original(parent / "stored-original.json")
            binding = json.loads((parent / "original-m-binding.json").read_bytes())
            raw_m = bytes.fromhex(binding["original_message_hex"])
            if sha256_hex(raw_m) != row["original_m_sha256"]:
                raise ValueError("Sheets family M hash mismatch")
            original_message = json.loads(raw_m)
            cells = json.loads(original.body)["requests"][0]["appendCells"]["rows"][0]["values"]
            marker, item, detail = (c["userEnteredValue"]["stringValue"] for c in cells)
            if marker != arm["arm_marker"] or sha256_hex(original.body) != row["frozen_w_body_sha256"]:
                raise ValueError("Sheets W body or attribution mismatch")
            semantic = {"item": item, "detail": detail}
        call = original_message["tool_calls"][0]["function"]
        if (semantic != family["target_semantic_m"] or json.loads(call["arguments"]) != semantic
                or call["name"] != ("create_issue" if provider == "github" else "append_row")):
            raise ValueError("stored semantic original differs")
        entry = {"family_id": family_id, "user_task": family["user_task"],
                 "semantic": semantic, "original_message_sha256": sha256_hex(raw_m)}
        old = result[provider].get(family_id)
        if old is not None and old != entry:
            raise ValueError("family M differs across canonical arms")
        result[provider][family_id] = entry
    if any(len(v) != 64 for v in result.values()):
        raise ValueError("incomplete provider family set")
    return {k: list(v.values()) for k, v in result.items()}


def historical_counts(sources: dict) -> list[dict]:
    """Descriptive frozen per-policy denominators; no tests or imputation."""
    counts = Counter()
    for study, key in (("Study 1A", "A3"), ("Study 1B", "B3")):
        for line in Path(sources[key]["path"]).read_text().splitlines():
            t = json.loads(line)
            world = {"NOT_EXECUTED": "H0", "EXECUTED_ACK_LOST": "H1"}[
                t["evaluator_only"]["hidden_world"]]
            correct = t["evaluator_only"]["evaluation"]["correct"]
            counts[(study, world, t["recovery_policy"], "scheduled")] += 1
            counts[(study, world, t["recovery_policy"], "scored")] += 1
            counts[(study, world, t["recovery_policy"], "correct")] += int(correct)
    for line in Path(sources["E1"]["path"]).read_text().splitlines():
        r = json.loads(line)
        if r["provider"] == "github":
            study = "GitHub"
        elif r["provider"] == "sheets" and r["dataset_id"] == "sheets_replication":
            study = "Sheets valid replication"
        else:
            continue
        prefix = (study, r["hidden_world"], r["policy"])
        counts[(*prefix, "scheduled")] += 1
        if r["state_correct"] is not None:
            counts[(*prefix, "scored")] += 1
            counts[(*prefix, "correct")] += int(r["state_correct"])
    rows = []
    for study in ("Study 1A", "Study 1B", "GitHub", "Sheets valid replication"):
        for world in ("H0", "H1"):
            row = {"study": study, "execution_situation": world}
            for policy, name in (("EXACT_REPLAY", "replay"), ("LLM_REGENERATION", "regeneration")):
                prefix = (study, world, policy)
                row[name] = {k: counts[(*prefix, k)] for k in ("correct", "scored", "scheduled")}
            row["no_model"] = {"correct": None, "scored": 0,
                               "planned": 160 if study.startswith("Study 1") else 64,
                               "status": "NOT_COLLECTED"}
            rows.append(row)
    return rows
