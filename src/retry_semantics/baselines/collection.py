"""Serial, one-use collection orchestration. Importing performs no collection.

The CLI separately requires explicit authorization, a pinned readiness lock and
fresh output. No model/session/callback can be supplied to this runner.
"""
from __future__ import annotations

import json
import importlib.metadata
import platform
import time
from pathlib import Path
from urllib.parse import urlsplit

from retry_semantics.baselines import harness, preparation, readiness
from retry_semantics.baselines.audit_closure import write_json
from retry_semantics.baselines.schedule import validate_schedule
from retry_semantics.environments.ticket import FrozenExecutableRequest, SourceStage, TicketEnvironment
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2.github_adapter import HTTPResponse
from retry_semantics.study2.provider_paper_io import DurablePaperEvidence, PaperRequest
from retry_semantics.study2.sheets_paper_adapter import DispatchFacts, prepare_paper_append
from retry_semantics.study2.sheets_paper_blank_readiness import check_precollection_blank
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
from retry_semantics.study2.sheets_paper_runner import load_original, certify_h1_constructor, validate_append_acknowledgement

AUTHORIZATION = "AUTHORIZE_NO_MODEL_BASELINE_COLLECTION_V1"


class CollectionRefused(ValueError):
    pass


class ProviderStopped(RuntimeError):
    pass


def require_authorization(value):
    if value != AUTHORIZATION:
        raise CollectionRefused("scientific collection requires deliberate explicit authorization")


def verified_package(binding_dir: Path, lock_path: Path, expected_lock_sha256: str,
                     *, root: Path, partition=None, deployment_path=None,
                     deployment_sha256=None) -> dict:
    """Read-only verification; validates every frozen request before dispatch."""
    if lock_path.is_symlink() or readiness.file_digest(lock_path) != expected_lock_sha256:
        raise CollectionRefused("readiness lock identity differs")
    lock = json.loads(lock_path.read_bytes())
    if lock["scientific_evaluations"] != 0 or lock["scientific_mutations"] != 0:
        raise CollectionRefused("lock is not prospective")
    if platform.python_version() != lock["python_version"] or any(
            importlib.metadata.version(name) != version
            for name, version in lock["runtime_dependency_versions"].items()):
        raise CollectionRefused("Python/dependency runtime differs from frozen qualification")
    runtime_files = lock["runtime_files"]
    partition_manifest = deployment_lock = None
    if partition is not None:
        from retry_semantics.baselines.partitions import runtime_expectations, spec
        try:
            spec(partition)
            runtime_files, partition_manifest, deployment_lock = runtime_expectations(
                root, lock, expected_lock_sha256, deployment_path, deployment_sha256)
        except ValueError as exc:
            raise CollectionRefused(str(exc)) from exc
    for name, expected in runtime_files.items():
        path = root / name
        if path.is_symlink() or readiness.file_digest(path) != expected:
            raise CollectionRefused("runtime/protocol identity differs: " + name)
    for name, expected in lock["evidence_files"].items():
        path = root / name
        if path.is_symlink() or readiness.file_digest(path) != expected:
            raise CollectionRefused("readiness/source binding evidence differs: " + name)
    schedule = json.loads((binding_dir / "schedule.json").read_bytes())
    if readiness.file_digest(binding_dir / "schedule.json") != lock["schedule_sha256"]:
        raise CollectionRefused("complete schedule identity differs")
    selected = schedule
    if partition is not None:
        from retry_semantics.baselines.partitions import selected_entries
        selected = selected_entries(schedule, partition_manifest, partition)
    relevant = {e["stored_original_file"] for e in selected}
    for name, expected in lock["binding_files"].items():
        if partition is not None and name.endswith("/stored-original.json") and name not in relevant:
            continue  # Other partitions' exact hashes remain sealed in the SAME original lock.
        path = binding_dir / name
        if path.is_symlink() or not path.resolve().is_relative_to(binding_dir.resolve()) or readiness.file_digest(path) != expected:
            raise CollectionRefused("frozen binding identity differs: " + name)
    mapping = json.loads((binding_dir / "family_mapping.json").read_bytes())
    validate_schedule(schedule, mapping)
    github_manifest = json.loads((binding_dir / "github_observer_authority.json").read_bytes())
    topology = json.loads((binding_dir / "sheets_topology.json").read_bytes())
    for entry in selected:
        path = binding_dir / entry["stored_original_file"]
        if (not path.resolve().is_relative_to(binding_dir.resolve()) or path.is_symlink()
                or readiness.file_digest(path) != entry["stored_original_file_sha256"]):
            raise CollectionRefused("stored original changed")
        if entry["source_set"].startswith("Study 1"):
            value = json.loads(path.read_bytes())
            request = FrozenExecutableRequest(bytes.fromhex(value["serialized_request_hex"]), value["request_hash"])
            args = json.loads(request.serialized_request)["arguments"]
            initial = TicketEnvironment.clone_from_snapshot(bytes.fromhex(value["initial_snapshot_hex"]))
            if initial.state.tickets or initial.state.mutation_events or args != entry["semantic_target"]:
                raise CollectionRefused("ticket source/state mismatch")
            identity = request.request_hash
        elif entry["source_set"] == "GitHub":
            request = preparation.load_github(path)
            if partition is None:
                expected = preparation.bind_github(manifest=github_manifest, arm=entry["arm"],
                    source_original={"semantic": entry["semantic_target"]}, api_version="2022-11-28")
                if request != expected:
                    raise CollectionRefused("GitHub stored original mismatch")
            elif request.url != gh._scope(github_manifest, entry["arm"],
                    "https://api.github.com", "2022-11-28"):
                raise CollectionRefused("GitHub frozen scope authority differs")
            # Partition deployment loads the already hash-bound exact request;
            # no request is reconstructed or rebound on the VM.
            identity = request.sha256
        else:
            request = load_original(path)
            if (entry["arm"]["spreadsheet_id"] != topology["spreadsheet_id"]
                    or request != prepare_paper_append(entry["arm"], **entry["semantic_target"])):
                raise CollectionRefused("Sheets stored original mismatch")
            identity = request.identity_hash
        if identity != entry["stored_request_identity_sha256"]:
            raise CollectionRefused("request identity differs")
    for provider in ("github", "sheets"):
        provider_ready = json.loads((root / lock[provider + "_readiness_file"]).read_bytes())
        if provider_ready["status"] != "FULL_PROVIDER_READINESS_PASS":
            raise CollectionRefused("provider not fully ready")
    return {"lock": lock, "schedule": schedule, "github_manifest": github_manifest,
            "sheets_topology": topology, "binding_dir": binding_dir, "root": root,
            "partition": partition, "selected_schedule": selected,
            "partition_manifest": partition_manifest, "deployment_lock": deployment_lock,
            "execution_runtime_files": runtime_files}


def _unrun(entry, reason):
    return dict(harness.unentered_record(study=entry["source_set"],
        family_id=entry["source_family_id"], trial_id=entry["baseline_arm_id"],
        hidden_world=entry["hidden_world"], reason=reason),
        schedule_index=entry["schedule_index"], opportunity_status="UNRUN")


def run_serial(entries, output: Path, execute, *, partition=None, deployment_provenance=None):
    """One serial traversal. The injected executor is internal, never a model.

    Offline tests supply an inert synthetic executor; production CLI supplies
    execute_arm after authorization/identity checks. There is no resume path.
    """
    if partition is not None:
        from retry_semantics.baselines.partitions import assert_entry
        for entry in entries:
            assert_entry(partition, entry)
    if output.exists() or output.is_symlink():
        raise CollectionRefused("output directory exists; overwrite/resume forbidden")
    output.mkdir(parents=True, mode=0o700)
    if deployment_provenance is not None:
        write_json(output / "deployment_provenance.json", deployment_provenance)
    write_json(output / "scheduled_opportunities.json", entries)
    stop_reason = None
    records = []
    for entry in entries:
        directory = output / f"{entry['schedule_index']:03d}"
        directory.mkdir()
        if stop_reason:
            result = _unrun(entry, stop_reason)
        else:
            try:
                result, stop = execute(entry, directory)
                if stop:
                    stop_reason = "PROVIDER_STOP_NO_REFILL"
            except Exception as exc:
                # Raw intent/result evidence remains in the arm directory. A
                # fatal unhandled failure stops the run, never repeats an arm.
                result = _unrun(entry, "FATAL_RUN_STOP:" + type(exc).__name__)
                result["opportunity_status"] = "ATTEMPT_FAILED_ENDPOINT_UNAVAILABLE"
                stop_reason = "FATAL_RUN_STOP_NO_REFILL"
        # Unrun opportunities keep the same complete source/request binding as
        # attempted ones; no observation is synthesized for the missing arm.
        result = dict(result, schedule_index=entry["schedule_index"],
            source_set=entry["source_set"], source_family_id=entry["source_family_id"],
            source_original_identity=entry.get("source_original_identity"),
            baseline_arm_id=entry["baseline_arm_id"],
            semantic_target_sha256=entry.get("semantic_target_sha256"))
        result.setdefault("stored_request_identity_sha256", entry.get("stored_request_identity_sha256"))
        if partition is not None:
            from retry_semantics.baselines.partitions import spec
            result["execution_partition"] = spec(partition)[0]
        harness.write_once(directory, "result.json", result)
        records.append(result)
    summary = {"scheduled": len(entries), "records": len(records),
        "status": "STOPPED_REMAINDER_RETAINED" if stop_reason else "COMPLETED",
        "unrun": sum(r.get("opportunity_status") == "UNRUN" for r in records),
        "model_calls": sum(r["model_call_count"] for r in records),
        "no_resume_no_refill": True}
    if partition is not None:
        from retry_semantics.baselines.partitions import spec
        summary["execution_partition"] = spec(partition)[0]
    write_json(output / "run_summary.json", summary)
    return summary


def construct_ticket(entry, original, initial_snapshot):
    """A fresh clone; H0 dispatches nothing, H1 dispatches exact original once."""
    environment = TicketEnvironment.clone_from_snapshot(initial_snapshot)
    if environment.state.tickets or environment.state.mutation_events:
        raise CollectionRefused("ticket initial state is not fresh")
    response = None
    if entry["hidden_world"] == "H1":
        response = environment.execute_request(original.serialized_request,
            source_stage=SourceStage.ORIGINAL, arm_id=None,
            expected_request_hash=original.request_hash)
    elif entry["hidden_world"] != "H0":
        raise CollectionRefused("invalid construction")
    return environment.snapshot_bytes(), response


class ArmTransport:
    """One-shot raw journal, exact mutation identity/caps, provider stop guard."""
    def __init__(self, entry, original, journal, send, *, repository_id=None):
        self.entry, self.original, self.journal, self.send = entry, original, journal, send
        self.repository_id = repository_id
        self.phase = "BASELINE"
        self.stopped = False
        self.original_calls = self.recovery_calls = self.policy_fetch_starts = 0
        self.policy_entered = False

    def _record(self, kind, request):
        if self.stopped:
            raise ProviderStopped("no provider dispatch after access/rate stop")
        parsed = urlsplit(request.url)
        if self.entry["source_set"] == "GitHub":
            scope = "/repos/" + gh.SELECTED_REPOSITORY + "/issues"
            allowed = {scope, f"/repositories/{self.repository_id}/issues"}
            if parsed.hostname != "api.github.com" or parsed.path not in allowed:
                raise CollectionRefused("GitHub request escaped frozen scope")
        else:
            scope = "/v4/spreadsheets/" + self.entry["arm"]["spreadsheet_id"]
            if parsed.hostname != "sheets.googleapis.com" or parsed.path not in {scope, scope + ":batchUpdate"}:
                raise CollectionRefused("Sheets request escaped frozen scope")
        result = self.journal.record(kind, request, self.send)
        secondary = (self.entry["source_set"] == "GitHub"
                     and b"secondary rate limit" in result.body.lower())
        if result.status in (401, 403, 429) or secondary:
            self.stopped = True
            self.journal.event("provider-stop-" + str(self.journal.index), {
                "status": result.status, "secondary_rate_limit": secondary,
                "policy_entered": self.policy_entered, "no_further_provider_dispatch": True})
        return result

    def fetch(self, url=None):
        if self.entry["source_set"] == "GitHub":
            initial = url.endswith("?state=all&per_page=100&page=1")
            if self.phase == "POLICY_AND_EVALUATOR" and initial:
                self.policy_fetch_starts += 1
            operation = ("POLICY_LIST_PAGE" if self.policy_fetch_starts == 1 else "FINAL_EVALUATOR_PAGE") if self.phase == "POLICY_AND_EVALUATOR" else self.phase + "_PAGE"
            request = PaperRequest("GET", url, (("Accept", "application/vnd.github.raw+json"),
                ("X-GitHub-Api-Version", "2022-11-28")), b"")
        else:
            if self.phase == "POLICY_AND_EVALUATOR":
                self.policy_fetch_starts += 1
            operation = ("POLICY_LIST_GET" if self.policy_fetch_starts == 1 else "FINAL_EVALUATOR_GET") if self.phase == "POLICY_AND_EVALUATOR" else self.phase + "_GET"
            request = PaperRequest("GET", "https://sheets.googleapis.com" + self.entry["arm"]["read_target"], (), b"")
        result = self._record(operation, request)
        if self.entry["source_set"] == "GitHub":
            return HTTPResponse(result.status or 0, result.headers, result.body, result.error)
        return PaperHTTPResult(DispatchFacts(result.dispatch_initiated,
            result.local_send_completed is True, result.status), result.body, result.error)

    def dispatch(self, request):
        if request is not self.original:
            raise CollectionRefused("mutation replaced stored original")
        if self.phase == "CONSTRUCTOR":
            if self.entry["hidden_world"] != "H1" or self.original_calls:
                raise CollectionRefused("original dispatch forbidden or repeated")
            self.original_calls += 1
            operation = "H1_ORIGINAL_CREATE_ONCE"
        elif self.phase == "POLICY_AND_EVALUATOR":
            if self.recovery_calls:
                raise CollectionRefused("recovery mutation cap exceeded")
            self.recovery_calls += 1
            operation = "POLICY_STORED_CREATE_ONCE"
        else:
            raise CollectionRefused("mutation outside constructor/recovery stage")
        url = request.url if self.entry["source_set"] == "GitHub" else "https://sheets.googleapis.com" + request.uri
        response = self._record(operation, PaperRequest(request.method, url, request.headers, request.body))
        if self.entry["source_set"] == "GitHub":
            return HTTPResponse(response.status or 0, response.headers, response.body, response.error)
        return PaperHTTPResult(DispatchFacts(response.dispatch_initiated,
            response.local_send_completed is True, response.status), response.body, response.error)


def execute_arm(entry, directory, package, *, github_send, sheets_send,
                before_provider_family, clock=time.monotonic, wait_until=None):
    path = package["binding_dir"] / entry["stored_original_file"]
    if entry["source_set"].startswith("Study 1"):
        saved = json.loads(path.read_bytes())
        original = FrozenExecutableRequest(bytes.fromhex(saved["serialized_request_hex"]), saved["request_hash"])
        starting, response = construct_ticket(entry, original, bytes.fromhex(saved["initial_snapshot_hex"]))
        write_json(directory / "constructor.json", {"hidden_world": entry["hidden_world"],
            "original_dispatch_count": int(response is not None), "original_request_hex": original.serialized_request.hex(),
            "original_result_hex": None if response is None else response.hex(),
            "starting_snapshot_hex": starting.hex()})
        result = harness.run_ticket_arm(study=entry["source_set"], family_id=entry["source_family_id"],
            trial_id=entry["baseline_arm_id"], hidden_world=entry["hidden_world"],
            starting_snapshot=starting, original=original, arm_id=entry["baseline_arm_id"])
        return dict(result, opportunity_status="EVALUATED"), False
    original = preparation.load_github(path) if entry["source_set"] == "GitHub" else load_original(path)
    before_provider_family(entry, directory)
    ev = DurablePaperEvidence(directory / "operations", provider=entry["source_set"].lower(),
        family_id=entry["source_family_id"], arm_id=entry["baseline_arm_id"],
        manifest_sha256=package["lock"]["schedule_sha256"],
        runtime_sha256=package.get("execution_runtime_files", package["lock"]["runtime_files"]))
    send = github_send if entry["source_set"] == "GitHub" else sheets_send
    guard = ArmTransport(entry, original, ev, send,
        repository_id=package["lock"]["github_repository_id"])
    arm, family = entry["arm"], {"family_id": entry["source_family_id"], "target_semantic_m": entry["semantic_target"]}
    def wait(deadline):
        # No sleeping or provider operation after a prohibited dispatch.
        if guard.stopped:
            return
        if wait_until is not None:
            wait_until(deadline)
        else:
            while clock() < deadline and not guard.stopped:
                time.sleep(min(30, deadline - clock()))
    certificate = None
    try:
        if entry["source_set"] == "GitHub":
            manifest = package["github_manifest"]
            anchor = clock()
            baseline = gh.bounded_census(manifest, arm, api_version="2022-11-28",
                fetch=guard.fetch, elapsed=lambda: clock()-anchor)
            clear = baseline.complete and not any(body.endswith(arm["suffix"]) for _, _, body in baseline.issues)
        else:
            manifest = package["sheets_topology"]
            baseline = guard.fetch()
            if baseline.transport_error:
                raise CollectionRefused("preconstruction blank transport failed")
            check_precollection_blank(manifest, arm, method="GET", target=arm["read_target"],
                status=baseline.facts.http_status, raw=baseline.body)
            clear = True
        if not clear or guard.stopped:
            raise CollectionRefused("preconstruction scope blankness not certified")
        guard.phase = "CONSTRUCTOR"
        if entry["hidden_world"] == "H1":
            acknowledgement = guard.dispatch(original)
            if guard.stopped:
                raise ProviderStopped()
            if entry["source_set"] == "GitHub":
                if gh.validate_create_ack(original, acknowledgement, "2022-11-28") is None:
                    raise CollectionRefused("H1 acknowledgement not certified; no resend")
                rounds = gh.run_h1_constructor(manifest, family, arm, api_version="2022-11-28",
                    anchor=clock(), clock=clock, wait_until=wait, fetch=guard.fetch,
                    should_abort=lambda: guard.stopped)
                certificate = harness.certify_github_constructor(manifest, family, arm, original, acknowledgement, rounds)
            else:
                validate_append_acknowledgement(original, arm, acknowledgement)
                observed = guard.fetch()
                if observed.transport_error:
                    raise CollectionRefused("H1 read transport failure")
                certificate = certify_h1_constructor(manifest, family, arm, original, acknowledgement,
                    ("GET", arm["read_target"], observed.facts.http_status, observed.body))
        elif entry["hidden_world"] != "H0":
            raise CollectionRefused("invalid world")
        ev.event("constructor-certified", {"hidden_world": entry["hidden_world"],
            "original_dispatch_count": guard.original_calls, "baseline_clear": True,
            "h1_certificate": None if certificate is None else json.loads(json.dumps(asdict_certificate(certificate)))})
        if guard.stopped:
            raise ProviderStopped()
        guard.phase = "POLICY_AND_EVALUATOR"
        guard.policy_entered = True
        ev.event("policy-entry", {"original_dispatch_count": guard.original_calls,
            "zero_model_capability": True, "hidden_world_harness_only": entry["hidden_world"]})
        common = dict(manifest=manifest, family=family, arm=arm, original=original,
            fetch=guard.fetch, dispatch=guard.dispatch, clock=clock, baseline_clear=True,
            isolation_proven=True, h1_certificate=certificate)
        if entry["source_set"] == "GitHub":
            result = harness.run_github_arm(**common, api_version="2022-11-28", wait_until=wait)
        else:
            result = harness.run_sheets_arm(**common)
        if result["model_call_count"] != 0 or result["read_count"] != 1 or result["write_count"] > 1:
            raise CollectionRefused("accepted policy invariant violation")
        return dict(result, opportunity_status="EVALUATED", original_dispatch_count=guard.original_calls), guard.stopped
    except Exception as exc:
        reason = "PROVIDER_STOP" if guard.stopped else type(exc).__name__
        result = _unrun(entry, reason)
        result.update(opportunity_status="CONSTRUCTION_UNQUALIFIED" if not guard.policy_entered else "ENDPOINT_UNAVAILABLE",
            original_dispatch_count=guard.original_calls)
        if guard.policy_entered:
            result.update(list_attempted=guard.policy_fetch_starts > 0,
                list_outcome="ENDPOINT_RECORD_UNAVAILABLE", read_count=int(guard.policy_fetch_starts > 0),
                write_count=guard.recovery_calls, recovery_create_attempted=guard.recovery_calls > 0)
        ev.event("attempt-unknown", {"reason": reason, "policy_entered": guard.policy_entered,
            "original_dispatch_count": guard.original_calls, "recovery_dispatch_attempts": guard.recovery_calls})
        # Access/rate stop and any unexpected post-entry harness error stop the
        # remainder. A failed pre-entry constructor is retained, never refilled.
        return result, guard.stopped or guard.policy_entered


def asdict_certificate(certificate):
    from dataclasses import asdict
    value = asdict(certificate)
    def convert(item):
        if isinstance(item, bytes): return {"raw_hex": item.hex()}
        if isinstance(item, dict): return {key: convert(v) for key, v in item.items()}
        if isinstance(item, (tuple, list)): return [convert(v) for v in item]
        return item
    return convert(value)
