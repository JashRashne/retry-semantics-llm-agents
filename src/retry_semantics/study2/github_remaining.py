"""User-authorized remaining-arm segment; never rewrites the stopped primary."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import provider_operator_launch as base
from retry_semantics.study2.provider_paper_collection import _schedule

ROLE = "GITHUB_REMAINING_ARMS_CONTINUATION_V1"
BASIS = "operator-authorized-github-remaining-v1"
CLAIM = "github-remaining-v1"
PROTOCOL = "research/protocol/STUDY2_GITHUB_REMAINING_CONTINUATION_V1.md"


def source_selection(source: Path):
    source = source.resolve(strict=True)
    if any(p.is_symlink() for p in source.rglob("*")):
        raise base.PaperCollectionError("Symlinked source evidence")
    inventory = json.loads((source / "inventory.json").read_bytes())
    if inventory != base.inventory(source):
        raise base.PaperCollectionError("Stopped source inventory changed")
    manifest = base.manifest_for("github")
    summary = json.loads((source / "summary.json").read_bytes())
    if (json.loads((source / "manifest.json").read_bytes()) != manifest
            or summary.get("state") != "STOPPED" or summary.get("provider") != "github"
            or summary.get("dataset_role") != base.ROLE):
        raise base.PaperCollectionError("Unexpected stopped source")
    schedule = _schedule(manifest)
    allowed = {a["arm_id"] for f, a in schedule}
    directories, originals, entered, stops = {}, {}, set(), {}
    collection = source / "collection"
    for p in collection.glob("run-stopped-*.json"):
        d = json.loads(p.read_bytes())
        if d["arm_id"] not in allowed or d["arm_id"] in stops:
            raise base.PaperCollectionError("Unknown or repeated source stop")
        stops[d["arm_id"]] = d
    if list(collection.rglob("run-abort.json")):
        raise base.PaperCollectionError("Aborted source requires separate review")
    for directory in sorted(p for p in collection.iterdir() if p.is_dir()):
        binding = json.loads((directory / "original-m-binding.json").read_bytes())
        arm_id, family_id = binding["arm_id"], binding["family_id"]
        if arm_id not in allowed or arm_id in directories:
            raise base.PaperCollectionError("Unknown or repeated source arm")
        directories[arm_id] = directory
        raw = bytes.fromhex(binding["original_message_hex"])
        if sha256_hex(raw) != binding["original_message_sha256"]:
            raise base.PaperCollectionError("Source original binding hash differs")
        message = json.loads(raw)
        if family_id in originals and originals[family_id] != message:
            raise base.PaperCollectionError("Family original changed within source")
        originals[family_id] = message
        generated = directory / "model-original-0.json"
        if generated.exists() and json.loads(generated.read_bytes())["assistant_message"] != message:
            raise base.PaperCollectionError("Generated original differs from binding")
        if (directory / "policy-entry.json").exists():
            if json.loads((directory / "policy-entry.json").read_bytes())["arm_id"] != arm_id:
                raise base.PaperCollectionError("Policy entry identity differs")
            entered.add(arm_id)
        else:
            projection = json.loads((directory / "arm-projection.json").read_bytes())
            if (projection.get("policy_entered") is not False
                    or projection["projection"]["reason"] != "pre_policy_baseline_or_run_stop"):
                raise base.PaperCollectionError("Unqualified candidate source projection")
            if any(json.loads(p.read_bytes()).get("method") != "GET"
                   for pattern in ("*.intent.json", "*.result.json") for p in directory.glob(pattern)):
                raise base.PaperCollectionError("Candidate arm already has a mutation intent")
    selected = []
    for family, arm in schedule:
        aid, fid = arm["arm_id"], family["family_id"]
        if aid in entered:
            continue
        if aid not in directories and (stops.get(aid, {}).get("reason") != "family_invalidated_before_policy"
                                      or stops[aid].get("executed") is not False):
            raise base.PaperCollectionError("Candidate arm lacks non-execution evidence")
        message = originals[fid]
        calls = message.get("tool_calls", [])
        if (len(calls) != 1 or calls[0]["function"]["name"] != "create_issue"
                or json.loads(calls[0]["function"]["arguments"]) != family["target_semantic_m"]):
            raise base.PaperCollectionError("Stored original differs from frozen semantic target")
        selected.append(aid)
    if len(entered) != 77 or len(selected) != 179 or len(stops) != 134:
        raise base.PaperCollectionError("Source differs from reviewed 77-entered/179-remaining incident")
    needed = {f["family_id"] for f, a in schedule if a["arm_id"] in selected}
    originals = {k: v for k, v in originals.items() if k in needed}
    identity = {"directory": str(source), "inventory_sha256": sha256_hex(canonical_json_bytes(inventory)),
                "previously_entered_arms": 77, "selected_arm_ids": selected,
                "family_original_sha256": {k: sha256_hex(canonical_json_bytes(v)) for k, v in originals.items()}}
    return identity, originals


def build_plan(source: Path, operator: str):
    source_identity, _ = source_selection(source)
    plan = base.build_plan("github", operator)
    plan.update(schema="github-remaining-arm-plan-v1", dataset_role=ROLE,
                source=source_identity, arms=179, families=45,
                protocol_sha256=sha256_hex((base.ROOT / PROTOCOL).read_bytes()))
    relative = "src/retry_semantics/study2/github_remaining.py"
    plan["static_identity"]["runtime_sha256"][relative] = sha256_hex((base.ROOT / relative).read_bytes())
    return plan


def check_plan(path):
    raw = path.read_bytes()
    plan = json.loads(raw)
    if path.is_symlink() or raw != canonical_json_bytes(plan) or plan != build_plan(
            Path(plan["source"]["directory"]), plan["operator"]):
        raise base.PaperCollectionError("Remaining plan/source/host/code changed")
    return plan


def registry_for(selected):
    registry = base.github_registry().as_json()
    registry["reservations"] = [r for r in registry["reservations"] if r["arm_id"] in selected]
    if len(registry["reservations"]) != len(selected):
        raise base.PaperCollectionError("Remaining marker allocation differs")
    registry.pop("audit_provenance", None)
    registry.update(status="OPERATOR_AUTHORIZED_REMAINING_SUBSET", independent_audit_claimed=False)
    return registry


def run(path, *, confirm_exclusive_writer, progress=print):
    if not confirm_exclusive_writer:
        raise base.PaperCollectionError("Exclusive repository writer attestation required")
    plan = check_plan(path)
    base.require_unconsumed(path, CLAIM)
    source, originals = source_selection(Path(plan["source"]["directory"]))
    selected = tuple(source["selected_arm_ids"])
    credential, model_key = base.credentials("github")
    transport = base.ProviderTransport("github", credential)
    directory = base.validate_run_directory(path.parent / "github-remaining-run")
    manifest = base.manifest_for("github")
    registry = registry_for(selected)
    claim = {"plan_sha256": sha256_hex(canonical_json_bytes(plan)), "run_dir": str(directory),
             "state": "CONSUMED_NO_AUTOMATIC_RESUME", "dataset_role": ROLE,
             "exclusive_writer_attested": True, "started_at_utc": datetime.now(timezone.utc).isoformat()}
    global_claim = base.claim_path(CLAIM)
    global_claim.parent.mkdir(parents=True, exist_ok=True)
    base.write_once(global_claim, claim)
    base.write_once(path.with_suffix(".started.json"), claim)
    directory.mkdir(parents=True)
    for name, data in (("plan", plan), ("manifest", manifest), ("remaining-registry", registry),
                       ("source-originals", originals), ("operator-attestation", claim)):
        base.write_once(directory / f"{name}.json", data)
    summary = {"provider": "github", "dataset_role": ROLE, "state": "STOPPED",
               "phase": "readiness", "scheduled_arms": len(selected), "evaluated_arms": 0,
               "previously_entered_arms_preserved": 77, "independent_audit_claimed": False}
    try:
        evidence = directory / "readiness"
        progress("github remaining: qualifying seven controls and unused suffixes", flush=True)
        hashes = base.capture_github_readiness(manifest=manifest, registry=registry,
            evidence_dir=evidence, identity=plan["static_identity"], operator_id=plan["operator"],
            api_version=plan["api_version"], http_send=transport,
            model_complete=base._capability("github", base.live_fireworks_completion(model_key)))
        if set(hashes) != set(base.PROVIDER_CONTROLS["github"]) or any(
                sha256_hex((evidence / f"{name}.json").read_bytes()) != digest for name, digest in hashes.items()):
            raise base.PaperCollectionError("Readiness evidence incomplete")
        lock = directory / "operator-readiness.json"
        base.write_once(lock, {"authorization_basis": BASIS, "control_sha256": hashes,
                              "independent_audit_claimed": False, "source_inventory_sha256": source["inventory_sha256"]})
        summary["phase"] = "collection"
        progress("github remaining: readiness PASS; beginning 179 remaining arms", flush=True)
        base._execute_provider_schedule(provider="github", run_dir=directory / "collection",
            manifest=manifest, identity=plan["static_identity"], lock_path=lock, evidence_dir=evidence,
            credential=credential, model_api_key=model_key, api_version=plan["api_version"],
            authorization_sha256=claim["plan_sha256"], authorization_basis=BASIS,
            progress=progress, http_send=transport, selected_arm_ids=selected,
            frozen_family_originals=originals)
        base.load_run_projections(directory / "collection", manifest, "github", expected_arm_ids=selected)
        summary["state"] = "COMPLETED_SEGMENT"
    except Exception as exc:
        summary["failure_type"] = type(exc).__name__
        if isinstance(exc, (base.PaperCollectionError, base.GitHubReadinessSessionError, base.ControlEvidenceError)):
            summary["failure_reason"] = str(exc)
    rows = [json.loads(p.read_bytes())["projection"] for p in (directory / "collection").glob("*/arm-projection.json")]
    summary.update(evaluated_arms=len(rows), verdicts=dict(Counter(p["status"] for p in rows)),
                   provider_stop_responses=base.provider_stops(directory),
                   ended_at_utc=datetime.now(timezone.utc).isoformat(), run_dir=str(directory))
    base.write_once(directory / "summary.json", summary)
    base.write_once(directory / "inventory.json", base.inventory(directory))
    return summary


def verify(directory):
    if json.loads((directory / "inventory.json").read_bytes()) != base.inventory(directory):
        raise base.PaperCollectionError("Continuation inventory changed")
    plan = json.loads((directory / "plan.json").read_bytes())
    source, originals = source_selection(Path(plan["source"]["directory"]))
    if source != plan["source"]:
        raise base.PaperCollectionError("Source segment changed")
    manifest = base.manifest_for("github")
    authorization = json.loads((directory / "collection/run-authorization.json").read_bytes())
    if (authorization["authorization_sha256"] != sha256_hex(canonical_json_bytes(plan))
            or authorization["runtime_sha256"] != plan["static_identity"]["runtime_sha256"]
            or json.loads((directory / "manifest.json").read_bytes()) != manifest
            or json.loads((directory / "source-originals.json").read_bytes()) != originals):
        raise base.PaperCollectionError("Continuation authorization/input binding differs")
    rows = base.load_run_projections(directory / "collection", manifest, "github",
                                    expected_arm_ids=tuple(source["selected_arm_ids"]))
    for f in (directory / "collection").glob("*/original-m-binding.json"):
        binding = json.loads(f.read_bytes())
        if binding["original_message_sha256"] != source["family_original_sha256"][binding["family_id"]]:
            raise base.PaperCollectionError("Family original regenerated or changed")
    summary = json.loads((directory / "summary.json").read_bytes())
    if (summary["state"] != "COMPLETED_SEGMENT" or summary["evaluated_arms"] != len(rows)
            or summary["verdicts"] != dict(Counter(r.status for r in rows))):
        raise base.PaperCollectionError("Continuation incomplete or summary differs")
    return summary
