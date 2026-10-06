"""Same observation paths as Regeneration; no construction or scoring here."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from retry_semantics.baselines.no_model import CreateOutcome, Recovery, Target, recover
from retry_semantics.environments.ticket import FrozenExecutableRequest, SourceStage, TicketEnvironment
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2.github_adapter import HTTPResponse
from retry_semantics.study2.sheets_offline import FrozenMutation
from retry_semantics.study2.sheets_paper_adapter import project_list_rows, replay_request
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
from retry_semantics.study2.sheets_paper_readiness import check_grid
from retry_semantics.study2.sheets_paper_runner import validate_append_acknowledgement


@dataclass(frozen=True, slots=True)
class AdapterResult:
    recovery: Recovery
    decision_http_reads: int
    # Harness-only causal evidence. Never supplied to recover().
    acknowledged_resource_ids: tuple[int, ...] = ()
    observed_row_floor: int = 0
    acknowledged_writes: int = 0
    stored_request_identity_sha256: str | None = None


def ticket_recovery(environment: TicketEnvironment, original: FrozenExecutableRequest,
                    *, arm_id: str) -> AdapterResult:
    value = json.loads(original.serialized_request)
    if value["tool"] != "create_ticket":
        raise ValueError("original must create a ticket")
    args = value["arguments"]
    target = Target("ticket", tuple(args[k] for k in ("customer_id", "title", "description")))
    read = canonical_json_bytes({"tool": "list_tickets", "tool_call_id": "baseline-list",
                                 "arguments": {}})

    def list_once():
        return json.loads(environment.execute_request(read, source_stage=SourceStage.RECOVERY,
                                                     arm_id=arm_id))

    def create_once(raw):
        response = environment.execute_request(raw, source_stage=SourceStage.RECOVERY,
            arm_id=arm_id, expected_request_hash=original.request_hash)
        return CreateOutcome(acknowledgement_validated=response == b'{"status":"created"}')

    result = recover(target=target, stored_original=original.serialized_request,
        original_sha256=original.request_hash, list_once=list_once, create_once=create_once)
    return AdapterResult(result, 0, acknowledged_writes=int(
        result.create_outcome is not None and result.create_outcome.acknowledgement_validated),
        stored_request_identity_sha256=original.request_hash)


def github_recovery(*, manifest: dict, arm: dict, original: gh.FrozenIssueRequest,
                    api_version: str, fetch: Callable[[str], HTTPResponse],
                    dispatch: Callable[[gh.FrozenIssueRequest], HTTPResponse],
                    clock: Callable[[], float]) -> AdapterResult:
    # Scope/marker validation is existing machinery, not a new policy exception.
    sent = json.loads(original.body)
    suffix = arm["suffix"]
    if not sent["body"].endswith(suffix):
        raise ValueError("original attribution mismatch")
    intended = {"title": sent["title"], "body": sent["body"][:-len(suffix)]}
    expected = gh.serialize_create(manifest, arm, **intended,
                                    api_base="https://api.github.com", api_version=api_version)
    if original != expected:
        raise ValueError("stored original scope or content changed")
    reads = 0
    acknowledged = []

    def get(url):
        nonlocal reads
        reads += 1
        return fetch(url)

    def list_once():
        anchor = clock()
        census = gh.bounded_census(manifest, arm, api_version=api_version,
                                  fetch=get, elapsed=lambda: clock() - anchor)
        if not census.complete:
            return "ToolError: Issue observation incomplete."
        # Exact projection from github_paper_runtime.run_recovery.
        projected = [{"title": title, "body": body[:-len(suffix)]}
                     for _, title, body in census.issues if body.endswith(suffix)]
        return {"issues": sorted(projected, key=lambda row: (row["title"], row["body"]))}

    def create_once(raw):
        if raw is not original.body:
            raise ValueError("original body replaced")
        response = gh.exact_replay(original, expected, dispatch)
        try:
            number = gh.validate_create_ack(original, response, api_version)
        except ValueError:
            number = None
        if number is not None:
            acknowledged.append(number)
        return CreateOutcome(response.status,
            "TRANSPORT_ERROR" if response.read_error else None, number is not None)

    result = recover(target=Target("github", (intended["title"], intended["body"])),
        stored_original=original.body, original_sha256=sha256_hex(original.body),
        list_once=list_once, create_once=create_once)
    return AdapterResult(result, reads, tuple(acknowledged),
                         acknowledged_writes=len(acknowledged),
                         stored_request_identity_sha256=original.sha256)


def sheets_recovery(*, manifest: dict, arm: dict, original: FrozenMutation,
                    fetch: Callable[[], PaperHTTPResult],
                    dispatch: Callable[[FrozenMutation], PaperHTTPResult]) -> AdapterResult:
    # Extract intent from the stored append, not from evaluator classifications.
    values = json.loads(original.body)["requests"][0]["appendCells"]["rows"][0]["values"]
    marker, item, detail = (cell["userEnteredValue"]["stringValue"] for cell in values)
    from retry_semantics.study2.sheets_paper_adapter import prepare_paper_append
    if marker != arm["arm_marker"] or original != prepare_paper_append(arm, item, detail):
        raise ValueError("stored original scope or content changed")
    reads, floor, acks = 0, 0, 0

    def list_once():
        nonlocal reads, floor
        reads += 1
        response = fetch()
        if response.transport_error is not None:
            return "ToolError: Row observation incomplete."
        # No intended= argument: matching_intended_rows never drives a decision.
        observed = check_grid(manifest, arm, response.facts.http_status, response.body)
        floor = len(observed.entered_rows)
        return project_list_rows(observed, authority_qualified=True)

    def create_once(raw):
        nonlocal acks
        if raw is not original.body:
            raise ValueError("original body replaced")
        response = dispatch(replay_request(original))
        try:
            validate_append_acknowledgement(original, arm, response)
        except ValueError:
            pass
        else:
            acks += 1
        return CreateOutcome(response.facts.http_status,
                             "TRANSPORT_ERROR" if response.transport_error else None, bool(acks))

    result = recover(target=Target("sheets", (item, detail)), stored_original=original.body,
        original_sha256=sha256_hex(original.body), list_once=list_once, create_once=create_once)
    return AdapterResult(result, reads, observed_row_floor=floor, acknowledged_writes=acks,
                         stored_request_identity_sha256=original.identity_hash)
