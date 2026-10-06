"""Behavioral tests use synthetic offline fixtures, never historical M recovery."""
import ast
import inspect
import json
import socket
from pathlib import Path

import pytest

from retry_semantics.baselines import adapters, harness, no_model, preparation, readiness
from retry_semantics.baselines.no_model import CreateOutcome, Target, recover
from retry_semantics.environments.ticket import SourceStage, TicketEnvironment
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2.github_adapter import HTTPResponse
from retry_semantics.study2.github_paper_manifest import load_github_paper_manifest
from retry_semantics.study2.sheets_paper_adapter import DispatchFacts
from retry_semantics.study2.sheets_paper_http import PaperHTTPResult
from retry_semantics.study2.sheets_paper_runner import load_original


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    from retry_semantics.models.fireworks import FireworksModelClient
    from retry_semantics.models.groq import GroqModelClient
    from retry_semantics.study2.provider_paper_model import PaperModelSession
    calls = []
    def model_denied(*args, **kwargs):
        calls.append(1)
        raise AssertionError("model prohibited in baseline")
    monkeypatch.setattr(FireworksModelClient, "complete", model_denied)
    monkeypatch.setattr(GroqModelClient, "complete", model_denied)
    monkeypatch.setattr(PaperModelSession, "_call", model_denied)
    def denied(*args, **kwargs):
        raise AssertionError("network prohibited in baseline offline tests")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    yield
    assert calls == [], "a recovery attempted a model call, even if it caught the error"


@pytest.mark.parametrize("environment,values", [
    ("ticket", ("C", "T", "D")), ("github", ("T", "D")), ("sheets", ("I", "D"))])
@pytest.mark.parametrize("present", [False, True])
def test_visible_or_absent_one_read_exact_original(environment, values, present):
    events = []
    original = b'{ "stored": "original bytes, not canonicalized" }'
    target = Target(environment, values)
    row = dict(zip(no_model.FIELDS[environment], values))
    observation = {no_model.COLLECTIONS[environment]: [row] if present else []}
    if environment == "sheets":
        observation["read_complete"] = True

    def read():
        events.append("LIST")
        return observation

    def create(raw):
        assert raw is original
        events.append("CREATE")
        return CreateOutcome(201)

    r = recover(target=target, stored_original=original, original_sha256=sha256_hex(original),
                list_once=read, create_once=create)
    assert events == (["LIST"] if present else ["LIST", "CREATE"])
    assert (r.read_count, r.write_count, r.model_call_count) == (1, int(not present), 0)
    assert r.intended_visible is present
    assert r.decision == ("STOP" if present else "CREATE")


@pytest.mark.parametrize("observation", [
    None, "ToolError: Issue observation incomplete.", {"issues": None},
    {"issues": [], "complete": True},
    {"issues": [{"title": "T", "body": "D", "number": 10}]},
    {"issues": [{"title": 2, "body": "D"}]},
])
def test_failed_or_richer_list_is_not_absence(observation):
    writes = []
    r = recover(target=Target("github", ("T", "D")), stored_original=b"x",
        original_sha256=sha256_hex(b"x"), list_once=lambda: observation,
        create_once=lambda raw: writes.append(raw))
    assert r.list_outcome == "OBSERVATION_FAILURE"
    assert r.intended_visible is None and r.decision == "STOP"
    assert not writes and r.write_count == 0


def test_list_transport_exception_stops():
    events = []
    def read():
        events.append("read")
        raise TimeoutError("secret must not be logged")
    r = recover(target=Target("ticket", ("C", "T", "D")), stored_original=b"x",
        original_sha256=sha256_hex(b"x"), list_once=read,
        create_once=lambda raw: events.append("write"))
    assert events == ["read"] and r.intended_visible is None
    assert r.list_outcome == "READ_ERROR:TimeoutError"


def test_create_timeout_no_retry_or_confirmation():
    events = []
    def create(raw):
        events.append("write")
        raise TimeoutError()
    r = recover(target=Target("github", ("T", "D")), stored_original=b"x",
        original_sha256=sha256_hex(b"x"),
        list_once=lambda: events.append("read") or {"issues": []}, create_once=create)
    assert events == ["read", "write"] and r.write_count == 1
    assert r.create_outcome.error == "CREATE_ERROR:TimeoutError"


def test_duplicate_visible_still_stops():
    row = {"title": "T", "body": "D"}
    r = recover(target=Target("github", ("T", "D")), stored_original=b"x",
        original_sha256=sha256_hex(b"x"), list_once=lambda: {"issues": [row, row]},
        create_once=lambda raw: pytest.fail("write on visible target"))
    assert r.intended_visible and r.write_count == 0


@pytest.mark.parametrize("different", ["t", "T ", "T\n", "Ｔ"])
def test_match_is_exact_not_semantic(different):
    writes = []
    r = recover(target=Target("github", ("T", "D")), stored_original=b"x",
        original_sha256=sha256_hex(b"x"),
        list_once=lambda: {"issues": [{"title": different, "body": "D"}]},
        create_once=lambda raw: writes.append(raw) or CreateOutcome())
    assert len(writes) == 1 and not r.intended_visible


def test_no_model_hidden_state_or_evaluator_capability():
    tree = ast.parse(inspect.getsource(no_model))
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert set(imports) == {"__future__", "dataclasses", "typing", "retry_semantics.serialization"}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not ({"H0", "H1", "evaluate_census", "evaluate_ticket_state", "check_grid",
                 "model", "hidden_world", "evaluator_only", "ModelClient"} & names)
    assert set(inspect.signature(recover).parameters) == {
        "target", "stored_original", "original_sha256", "list_once", "create_once"}
    assert Target.__slots__ == ("environment", "values")
    for forbidden in ("hidden_world", "evaluator_only", "model_continue"):
        with pytest.raises(TypeError):
            recover(**{forbidden: "H1"})
    # The autouse fixture also asserts actual model-boundary tripwires stayed unused.
    assert "model_call_count" not in inspect.signature(no_model.Recovery).parameters


def test_hash_mismatch_before_any_action():
    events = []
    with pytest.raises(ValueError, match="hash mismatch"):
        recover(target=Target("github", ("T", "D")), stored_original=b"x",
            original_sha256=sha256_hex(b"changed"),
            list_once=lambda: events.append("read"), create_once=lambda b: events.append("write"))
    assert events == []


@pytest.mark.parametrize("present", [False, True])
def test_ticket_actual_executor_and_evaluator_order(make_request, monkeypatch, present):
    original = make_request(title="Synthetic baseline fixture")
    env = TicketEnvironment.empty()
    if present:
        env.execute_request(original.serialized_request, source_stage=SourceStage.ORIGINAL, arm_id=None)
    events = []
    execute = TicketEnvironment.execute_request
    evaluate = harness.evaluate_ticket_state
    def tracked(self, raw, **kwargs):
        events.append(json.loads(raw)["tool"])
        return execute(self, raw, **kwargs)
    def final(state, **kwargs):
        events.append("evaluate")
        return evaluate(state, **kwargs)
    monkeypatch.setattr(TicketEnvironment, "execute_request", tracked)
    monkeypatch.setattr(harness, "evaluate_ticket_state", final)
    r = harness.run_ticket_arm(study="Synthetic", family_id="fixture", trial_id="fixture",
        hidden_world="H1" if present else "H0", starting_snapshot=env.snapshot_bytes(),
        original=original, arm_id="synthetic-arm")
    assert events == (["list_tickets", "evaluate"] if present else
                      ["list_tickets", "create_ticket", "evaluate"])
    assert r["final_correctness"] is True and r["matching_intended_effects"] == 1
    if not present:
        event = r["final_evaluator_state"]["snapshot"]["mutation_events"][-1]
        assert event["serialized_request"].encode() == original.serialized_request


def github_fixture(world="H0"):
    manifest = load_github_paper_manifest().as_json()
    arm = preparation.fresh_arm(namespace="a" * 32, family_id="fixture", hidden_world=world,
                               provider="github", old_markers=set())
    source = {"semantic": {"title": "Synthetic test issue", "body": "Synthetic test body"}}
    original = preparation.bind_github(manifest=manifest, source_original=source,
                                      arm=arm, api_version="2022-11-28")
    return manifest, arm, source, original


@pytest.mark.parametrize("present", [False, True])
def test_github_projection_and_exact_frozen_dispatch(present, monkeypatch):
    manifest, arm, source, original = github_fixture()
    reads, writes = [], []
    def fetch(url):
        reads.append(url)
        entries = [{"number": 9001, **json.loads(original.body), "state": "closed"}] if present else []
        # Foreign issue and PR must not appear in the projection.
        entries += [{"number": 2, "title": "Foreign", "body": "Foreign", "state": "open"},
                    {"number": 3, **json.loads(original.body), "state": "open", "pull_request": {}}]
        return HTTPResponse(200, (), canonical_json_bytes(entries))
    def dispatch(request):
        assert request is original and request.body is original.body
        writes.append(request)
        return HTTPResponse(201, (), canonical_json_bytes(
            {"number": 4, **json.loads(request.body), "state": "open"}))
    monkeypatch.setattr(gh, "evaluate_census", lambda *a, **k: pytest.fail("oracle during recovery"))
    r = adapters.github_recovery(manifest=manifest, arm=arm, original=original,
        api_version="2022-11-28", fetch=fetch, dispatch=dispatch, clock=lambda: 0)
    assert len(reads) == 1 and len(writes) == int(not present)
    observation = json.loads(r.recovery.observation)
    assert observation == {"issues": [source["semantic"]] if present else []}
    assert r.recovery.model_call_count == 0


def test_github_partial_positive_not_usable_and_single_traversal():
    manifest, arm, _, original = github_fixture()
    calls = []
    def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            return HTTPResponse(200, (("link", '<' + url.replace('&page=1', '&page=2') + '>; rel="next"'),),
                canonical_json_bytes([{"number": 1, **json.loads(original.body), "state": "open"}]))
        return HTTPResponse(503, (), b"unavailable")
    r = adapters.github_recovery(manifest=manifest, arm=arm, original=original,
        api_version="2022-11-28", fetch=fetch,
        dispatch=lambda x: pytest.fail("write on incomplete census"), clock=lambda: 0)
    assert len(calls) == r.decision_http_reads == 2
    assert r.recovery.read_count == 1 and r.recovery.intended_visible is None


def sheets_fixture(world="H0"):
    arm = preparation.fresh_arm(namespace="b" * 32, family_id="fixture", hidden_world=world,
                               provider="sheets", old_markers=set())
    source = {"semantic": {"item": "Synthetic item", "detail": "Synthetic detail"}}
    arm, original = preparation.bind_sheets(source_original=source, arm=arm,
                                            spreadsheet_id="synthetic-sheet", sheet_id=1)
    return {"spreadsheet_id": "synthetic-sheet"}, arm, source, original


def grid_response(arm, rows, *, omit_data=False, error=None):
    sheet = {"properties": {"sheetId": arm["sheet_id"], "title": arm["tab_title"],
        "sheetType": "GRID", "gridProperties": {"rowCount": 100, "columnCount": 3}}}
    if not omit_data:
        sheet["data"] = [{"startRow": 0, "startColumn": 0,
            "rowData": [{"values": [{"userEnteredValue": {"stringValue": s}} for s in row]}
                        for row in rows]}]
    return PaperHTTPResult(DispatchFacts(True, True, 200), canonical_json_bytes(
        {"spreadsheetId": arm["spreadsheet_id"], "sheets": [sheet]}), error)


def sheets_ack(arm):
    return PaperHTTPResult(DispatchFacts(True, True, 200), canonical_json_bytes(
        {"spreadsheetId": arm["spreadsheet_id"], "replies": [{}]}), None)


@pytest.mark.parametrize("present", [False, True])
def test_sheets_projection_no_evaluator_matching_and_exact_write(monkeypatch, present):
    manifest, arm, source, original = sheets_fixture()
    rows = [(arm["arm_marker"], *source["semantic"].values())] if present else []
    reads, writes = [], []
    def fetch():
        reads.append(1)
        return grid_response(arm, rows)
    def dispatch(request):
        assert request is original and request.body is original.body
        writes.append(request)
        return sheets_ack(arm)
    real_check = adapters.check_grid
    def checked(*args, **kwargs):
        assert "intended" not in kwargs
        return real_check(*args, **kwargs)
    monkeypatch.setattr(adapters, "check_grid", checked)
    r = adapters.sheets_recovery(manifest=manifest, arm=arm, original=original,
                                fetch=fetch, dispatch=dispatch)
    assert len(reads) == 1 and len(writes) == int(not present)
    assert json.loads(r.recovery.observation) == {
        "rows": [source["semantic"]] if present else [], "read_complete": True}


@pytest.mark.parametrize("failure", ["omitted_empty", "unexpected_row", "transport"])
def test_sheets_list_failure_cannot_create(failure):
    manifest, arm, _, original = sheets_fixture()
    rows = [("foreign-marker", "other", "other")] if failure == "unexpected_row" else []
    response = grid_response(arm, rows, omit_data=failure == "omitted_empty",
                             error="TimeoutError" if failure == "transport" else None)
    r = adapters.sheets_recovery(manifest=manifest, arm=arm, original=original,
        fetch=lambda: response, dispatch=lambda req: pytest.fail("write on LIST failure"))
    assert r.recovery.intended_visible is None and r.recovery.write_count == 0


@pytest.mark.parametrize("committed", [False, True])
def test_sheets_final_state_scores_ambiguous_write(committed):
    manifest, arm, source, original = sheets_fixture()
    events, rows = [], []
    def fetch():
        events.append("read")
        return grid_response(arm, rows)
    def dispatch(req):
        events.append("write")
        if committed:
            rows.append((arm["arm_marker"], *source["semantic"].values()))
        return PaperHTTPResult(DispatchFacts(True, True), b"", "TimeoutError")
    r = harness.run_sheets_arm(manifest=manifest, family={"family_id": "fixture",
        "target_semantic_m": source["semantic"]}, arm=arm, original=original,
        fetch=fetch, dispatch=dispatch, clock=lambda: 0, baseline_clear=True, isolation_proven=True)
    assert events == ["read", "write", "read"]
    assert r["final_correctness"] is committed and not r["unknown_unscorable"]
    assert r["read_count"] == 1 and r["final_evaluator_http_reads"] == 1


def test_sheets_final_incomplete_keeps_unknown():
    manifest, arm, source, original = sheets_fixture()
    r = harness.run_sheets_arm(manifest=manifest, family={"family_id": "fixture",
        "target_semantic_m": source["semantic"]}, arm=arm, original=original,
        fetch=lambda: grid_response(arm, [], omit_data=True),
        dispatch=lambda req: pytest.fail("unexpected write"), clock=lambda: 0,
        baseline_clear=True, isolation_proven=True)
    assert r["unknown_unscorable"] and r["final_correctness"] is None
    assert r["unknown_reason"] == "INCOMPLETE"


def test_fresh_provider_persistence_roundtrip_and_collision(tmp_path):
    manifest, arm, _, original = github_fixture()
    preparation.store_github(tmp_path / "gh", original)
    assert preparation.load_github(tmp_path / "gh/stored-original.json") == original
    with pytest.raises(FileExistsError):
        preparation.store_github(tmp_path / "gh", original)
    _, sheet_arm, _, sheet_original = sheets_fixture()
    preparation.store_sheets(tmp_path / "sheets", sheet_original)
    assert load_original(tmp_path / "sheets/stored-original.json") == sheet_original
    with pytest.raises(ValueError, match="collides"):
        preparation.fresh_arm(namespace="a" * 32, family_id="fixture", hidden_world="H0",
                              provider="github", old_markers={arm["arm_marker"]})


def test_protected_old_artifacts_unchanged():
    root = Path(__file__).resolve().parents[1]
    assert readiness.verify_protected(root / "research/baselines/no_model/protected_before.json") == 5942


def test_historical_counts_have_no_imputed_baseline():
    root = Path(__file__).resolve().parents[1]
    sources = json.loads((root / "research/baselines/no_model/sources.json").read_bytes())
    rows = readiness.historical_counts(sources)
    assert len(rows) == 8 and all(r["no_model"]["correct"] is None for r in rows)
    assert rows[0]["replay"] == {"correct": 160, "scored": 160, "scheduled": 160}
    assert rows[1]["regeneration"]["correct"] == 151
    github_h0 = rows[4]
    assert github_h0["replay"]["scored"] == 63
    assert github_h0["regeneration"]["scored"] == 64


@pytest.mark.parametrize("world", ["H0", "H1"])
def test_github_harness_final_endpoint_and_hidden_id_separation(world, tmp_path):
    manifest, arm, source, original = github_fixture(world)
    family = {"family_id": "fixture", "target_semantic_m": source["semantic"]}
    rows = [{"number": 900, **json.loads(original.body), "state": "open"}] if world == "H1" else []
    events = []
    now = [0.0]
    def fetch(url):
        events.append("GET")
        return HTTPResponse(200, (), canonical_json_bytes(rows))
    def dispatch(req):
        assert req is original
        events.append("POST")
        rows.append({"number": 901, **json.loads(req.body), "state": "open"})
        # A lost ACK must still be correct if final state is exact one.
        return HTTPResponse(0, (), b"", "TimeoutError")
    certificate = None
    if world == "H1":
        ack = HTTPResponse(201, (), canonical_json_bytes(rows[0]))
        census = gh.Census(True, ((900, rows[0]["title"], rows[0]["body"]),), 1, None, 1)
        rounds = (gh.ScheduledCensus(0, 0, 540, census),)
        certificate = harness.certify_github_constructor(manifest, family, arm, original, ack, rounds)
    def wait(until):
        now[0] = until
    r = harness.run_github_arm(manifest=manifest, family=family, arm=arm, original=original,
        api_version="2022-11-28", fetch=fetch, dispatch=dispatch, clock=lambda: now[0],
        wait_until=wait, baseline_clear=True, isolation_proven=True, h1_certificate=certificate)
    assert events == (["GET", "GET", "GET"] if world == "H1" else ["GET", "POST", "GET", "GET"])
    assert r["final_correctness"] is True and r["matching_intended_effects"] == 1
    assert r["model_call_count"] == 0 and r["read_count"] == 1
    assert "number" not in str(r["observation"]) and "900" not in str(r["observation"])
    harness.write_once(tmp_path / "new-evidence", "result.json", r)
    stored = json.loads((tmp_path / "new-evidence/result.json").read_bytes())
    assert stored == r


def test_visible_target_plus_unintended_sheets_effect_is_not_correct():
    manifest, arm, source, original = sheets_fixture()
    rows = [(arm["arm_marker"], *source["semantic"].values()),
            (arm["arm_marker"], "Wrong", "Wrong")]
    r = harness.run_sheets_arm(manifest=manifest, family={"family_id": "fixture",
        "target_semantic_m": source["semantic"]}, arm=arm, original=original,
        fetch=lambda: grid_response(arm, rows),
        dispatch=lambda req: pytest.fail("write on visible intended effect"), clock=lambda: 0,
        baseline_clear=True, isolation_proven=True)
    assert r["write_count"] == 0 and r["final_correctness"] is False
    assert r["matching_intended_effects"] == 1 and r["unintended_attributable_effects"] == 1


class HiddenInformationTripwire(dict):
    def __getitem__(self, key):
        if key in ("hidden_world", "evaluator_only", "original_id", "final_state"):
            raise AssertionError("decision adapter inspected forbidden information")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key in ("hidden_world", "evaluator_only", "original_id", "final_state"):
            raise AssertionError("decision adapter inspected forbidden information")
        return super().get(key, default)


@pytest.mark.parametrize("world", ["H0", "H1"])
def test_provider_decision_cannot_inspect_harness_label(world):
    manifest, arm, source, original = github_fixture(world)
    arm = HiddenInformationTripwire(arm)
    r = adapters.github_recovery(manifest=manifest, arm=arm, original=original,
        api_version="2022-11-28", fetch=lambda url: HTTPResponse(200, (), b"[]"),
        dispatch=lambda req: HTTPResponse(422, (), b"{}"), clock=lambda: 0)
    assert r.recovery.decision == "CREATE" and r.recovery.intended_visible is False
    manifest, arm, source, original = sheets_fixture(world)
    arm = HiddenInformationTripwire(arm)
    r = adapters.sheets_recovery(manifest=manifest, arm=arm, original=original,
        fetch=lambda: grid_response(arm, []), dispatch=lambda req: sheets_ack(arm))
    assert r.recovery.decision == "CREATE" and r.recovery.intended_visible is False


def test_ticket_list_failure_still_scores_authoritative_final_state(make_request, monkeypatch):
    original = make_request(title="Synthetic failure fixture")
    env = TicketEnvironment.empty()
    env.execute_request(original.serialized_request, source_stage=SourceStage.ORIGINAL, arm_id=None)
    execute = TicketEnvironment.execute_request
    def failed(self, raw, **kwargs):
        if json.loads(raw)["tool"] == "list_tickets":
            raise TimeoutError()
        return execute(self, raw, **kwargs)
    monkeypatch.setattr(TicketEnvironment, "execute_request", failed)
    r = harness.run_ticket_arm(study="Synthetic", family_id="fixture", trial_id="fixture",
        hidden_world="H1", starting_snapshot=env.snapshot_bytes(), original=original, arm_id="synthetic")
    assert r["list_outcome"] == "READ_ERROR:TimeoutError" and r["write_count"] == 0
    assert r["final_correctness"] is True and r["model_call_count"] == 0


@pytest.mark.parametrize("provider", ["github", "sheets"])
def test_final_transport_exception_retains_unknown(provider):
    calls = []
    if provider == "github":
        manifest, arm, source, original = github_fixture()
        def fetch(url):
            calls.append(1)
            if len(calls) > 1:
                raise TimeoutError()
            return HTTPResponse(200, (), b"[]")
        now = [0]
        def wait(until):
            now[0] = until
        r = harness.run_github_arm(manifest=manifest, family={"family_id": "fixture",
            "target_semantic_m": source["semantic"]}, arm=arm, original=original,
            api_version="2022-11-28", fetch=fetch, dispatch=lambda req: HTTPResponse(422, (), b"{}"),
            clock=lambda: now[0], wait_until=wait, baseline_clear=True, isolation_proven=True)
        assert len(calls) == 3  # One decision traversal, two scheduled evaluator traversals.
    else:
        manifest, arm, source, original = sheets_fixture()
        def fetch():
            calls.append(1)
            if len(calls) > 1:
                raise TimeoutError()
            return grid_response(arm, [])
        r = harness.run_sheets_arm(manifest=manifest, family={"family_id": "fixture",
            "target_semantic_m": source["semantic"]}, arm=arm, original=original,
            fetch=fetch, dispatch=lambda req: sheets_ack(arm), clock=lambda: 0,
            baseline_clear=True, isolation_proven=True)
        assert len(calls) == 2
    assert r["unknown_unscorable"] and r["final_correctness"] is None
    assert r["read_count"] == r["write_count"] == 1 and r["model_call_count"] == 0


def test_unentered_construction_failure_retained_as_unscorable():
    r = harness.unentered_record(study="Synthetic", family_id="fixture", trial_id="fixture",
        hidden_world="H1", reason="H1_constructor_unqualified")
    assert not r["list_attempted"] and r["decision"] is None
    assert r["unknown_unscorable"] and r["final_correctness"] is None
    assert (r["read_count"], r["write_count"], r["model_call_count"]) == (0, 0, 0)
