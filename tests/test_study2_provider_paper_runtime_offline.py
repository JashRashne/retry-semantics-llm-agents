"""Hostile offline checks for the provider paper boundaries."""

import json
import shutil
from dataclasses import replace

import pytest

from retry_semantics.serialization import sha256_hex
from retry_semantics.study2.github_adapter import HTTPResponse
from retry_semantics.study2.github_paper_manifest import (
    GitHubPaperManifestError,
    load_github_paper_manifest,
)
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2 import razorpay_paper_runtime as rz
from retry_semantics.study2 import provider_paper_readiness as ready
from retry_semantics.study2.razorpay_paper_manifest import (
    DRAFT as RAZORPAY_DRAFT,
    FROZEN as RAZORPAY_FROZEN,
    MANIFEST_PATH as RAZORPAY_MANIFEST_PATH,
    REGISTRY_PATH as RAZORPAY_REGISTRY_PATH,
    ROOT as RAZORPAY_ROOT,
    build_namespace_registry,
    build_razorpay_paper_manifest,
    freeze_status_only,
    load_namespace_registry,
    load_razorpay_paper_manifest,
    scientific_projection,
    scientific_sha256,
    SOURCE_SHA256,
)


@pytest.fixture(scope="module")
def github_case():
    manifest = load_github_paper_manifest().as_json()
    family = manifest["families"][0]
    return manifest, family, next(arm for arm in family["arms"]
                                  if arm["policy"] == "EXACT_REPLAY")


def _github_ack(request):
    sent = json.loads(request.body)
    return HTTPResponse(201, (), json.dumps({
        "number": 31, "title": sent["title"], "body": sent["body"],
        "state": "open",
    }).encode())


def test_github_replay_exact_bytes_zero_model_calls(github_case):
    manifest, family, arm = github_case
    original = gh.expected_original(manifest, family, arm,
                                    api_base="https://api.github.com",
                                    api_version="2022-11-28")
    seen = []
    h1_certificate = None
    if arm["hidden_world"] == "H1":
        target = family["target_semantic_m"]
        census = gh.Census(True, ((31, target["title"],
                                   target["body"] + arm["suffix"]),), 1, None, 1)
        h1_certificate = gh.certify_h1(
            manifest, family, arm, original, _github_ack(original),
            (gh.ScheduledCensus(0, 0, 540, census),))
    result = gh.run_recovery(manifest, family, arm, original,
                             api_version="2022-11-28",
                             dispatch=lambda request: (seen.append(request),
                                                       _github_ack(request))[1],
                             fetch=lambda _: pytest.fail("Replay read"),
                             elapsed=lambda: 0,
                             model_continue=lambda _: pytest.fail("Replay model"),
                             h1_certificate=h1_certificate)
    assert result.model_calls == 0
    assert seen == [original]
    assert seen[0].body is original.body
    with pytest.raises(gh.GitHubPaperError):
        gh.exact_replay(replace(original, body=original.body + b" "), original,
                        lambda _: pytest.fail("mutated Replay dispatched"))


def test_github_manifest_and_marker_tamper_rejected(github_case):
    manifest, family, arm = github_case
    changed = dict(manifest, manifest_id="wrong")
    with pytest.raises(gh.GitHubPaperError):
        gh.expected_original(changed, family, arm, api_base="https://api.github.com",
                             api_version="2022-11-28")
    with pytest.raises(gh.GitHubPaperError):
        gh.serialize_create(manifest, dict(arm, suffix="bad"), title="a", body="b",
                            api_base="https://api.github.com", api_version="2022-11-28")


def test_github_cap_and_incomplete_never_zero(github_case):
    manifest, family, arm = github_case
    page = HTTPResponse(200, (("Link", '<https://api.github.com/repos/JashRashne/retry-semantics-study2-github-sandbox/issues?state=all&per_page=100&page=2>; rel="next"'),), b"[]")
    count = 0

    def fetch(_):
        nonlocal count
        count += 1
        return page

    census = gh.bounded_census(manifest, arm, api_version="2022-11-28",
                               fetch=fetch, elapsed=lambda: 0)
    assert count == 2
    assert census.complete is False
    result = gh.evaluate_census(arm, family["target_semantic_m"], (census,), (),
                                isolation_proven=True, baseline_clear=True)
    assert result["status"] == "INCONCLUSIVE"
    assert result["state_correct"] is None


def test_github_visible_redirect_is_single_attempt(github_case):
    manifest, family, arm = github_case
    original = gh.expected_original(manifest, family, arm,
                                    api_base="https://api.github.com",
                                    api_version="2022-11-28")
    calls = []
    response = gh.exact_replay(original, original,
                               lambda request: (calls.append(request),
                                                HTTPResponse(307, (("Location", "https://other"),), b""))[1])
    assert response.status == 307
    assert len(calls) == 1
    assert gh.validate_create_ack(original, response, "2022-11-28") is None


def test_github_obs1_uses_only_frozen_starts(github_case):
    manifest, _, arm = github_case
    now = [10.0]
    starts = []

    def fetch(_):
        starts.append(now[0])
        return HTTPResponse(200, (), b"[]")

    rounds = gh.run_scheduled_censuses(
        manifest, arm, api_version="2022-11-28", anchor=10.0,
        clock=lambda: now[0], wait_until=lambda target: now.__setitem__(0, target),
        fetch=fetch)
    assert starts == [10.0, 610.0]
    assert [r.offset_seconds for r in rounds] == [0, 600]
    assert all(r.census.complete for r in rounds)


def test_github_obs1_with_matching_arm_issue(github_case):
    manifest, family, arm = github_case
    target = family["target_semantic_m"]
    now = [10.0]
    starts = []
    issue_payload = json.dumps([{
        "number": 42,
        "title": target["title"],
        "body": target["body"] + arm["suffix"],
        "state": "open",
    }]).encode()

    def fetch(_):
        starts.append(now[0])
        return HTTPResponse(200, (), issue_payload)

    rounds = gh.run_scheduled_censuses(
        manifest, arm, api_version="2022-11-28", anchor=10.0,
        clock=lambda: now[0], wait_until=lambda target_t: now.__setitem__(0, target_t),
        fetch=fetch, semantic_target=target)
    assert starts == [10.0, 610.0]
    assert len(rounds) == 2
    assert all(r.census.complete for r in rounds)
    assert all(len(r.census.issues) == 1 for r in rounds)
    verdict = gh.evaluate_census(
        arm, target, tuple(r.census for r in rounds), (42,),
        isolation_proven=True, baseline_clear=True)
    assert verdict["status"] == "SUCCESS"
    assert verdict["state_correct"] == 1
    assert verdict["reason"] == "CORRECT"
    assert verdict["lower_bound"] == 1

    # Hostile: wrong mutation detected via semantic_target breaks decisively on first round
    wrong_payload = json.dumps([{
        "number": 43,
        "title": "Wrong Title",
        "body": "Wrong body" + arm["suffix"],
        "state": "open",
    }]).encode()
    now_wrong = [10.0]
    wrong_starts = []

    def fetch_wrong(_):
        wrong_starts.append(now_wrong[0])
        return HTTPResponse(200, (), wrong_payload)

    wrong_rounds = gh.run_scheduled_censuses(
        manifest, arm, api_version="2022-11-28", anchor=10.0,
        clock=lambda: now_wrong[0], wait_until=lambda target_t: now_wrong.__setitem__(0, target_t),
        fetch=fetch_wrong, semantic_target=target)
    assert wrong_starts == [10.0]
    assert len(wrong_rounds) == 1


def test_github_regeneration_model_controls_changed_title(github_case):
    manifest, family, _ = github_case
    arm = next(x for x in family["arms"]
               if x["policy"] == "LLM_REGENERATION" and x["hidden_world"] == "H0")
    original = gh.expected_original(manifest, family, arm,
                                    api_base="https://api.github.com",
                                    api_version="2022-11-28")
    decisions = iter((gh.ModelDecision("create_issue", "Changed", "New body"),
                      gh.ModelDecision("finish")))
    seen = []
    result = gh.run_recovery(
        manifest, family, arm, original, api_version="2022-11-28",
        dispatch=lambda request: (seen.append(request), _github_ack(request))[1],
        fetch=lambda _: pytest.fail("unselected read"), elapsed=lambda: 0,
        model_continue=lambda _: next(decisions))
    assert result.model_calls == 2
    assert len(seen) == 1
    sent = json.loads(seen[0].body)
    assert sent["title"] == "Changed"
    assert sent["body"] == "New body" + arm["suffix"]


def test_github_duplicate_and_wrong_marker_never_count_as_one(github_case):
    _, family, arm = github_case
    target = family["target_semantic_m"]
    matched = tuple((number, target["title"], target["body"] + arm["suffix"])
                    for number in (31, 32))
    complete = gh.Census(True, matched, 1, None, 2)
    result = gh.evaluate_census(arm, target, (complete, complete), (31,),
                                isolation_proven=True, baseline_clear=True)
    assert result["state_correct"] == 0
    assert result["reason"] == "DUPLICATE_EFFECT"
    wrong = gh.Census(True, ((31, target["title"], target["body"] + "near"),),
                      1, None, 1)
    result = gh.evaluate_census(arm, target, (wrong, wrong), (31,),
                                isolation_proven=True, baseline_clear=True)
    assert result["status"] == "INCONCLUSIVE"
    assert result["state_correct"] is None


def _rz_ack(request, order_id="order_ABC123"):
    sent = json.loads(request.body)
    return rz.RawResponse(200, json.dumps({
        "id": order_id, "entity": "order", "amount": sent["amount"],
        "currency": sent["currency"], "receipt": None,
        "notes": {"retry_semantics_marker": request.marker},
    }).encode())


def _rz_request():
    return rz.serialize_create(arm_id="rz-f001:H0:EXACT_REPLAY",
                               marker="study2_rzp_paper_abc123",
                               scope_fingerprint="a" * 64,
                               amount=200, currency="INR")


def test_razorpay_replay_exact_bytes_no_model_or_read():
    request = _rz_request()
    calls = []
    result = rz.run_recovery(arm_id=request.arm_id, marker=request.marker,
                             scope_fingerprint=request.scope_fingerprint,
                             policy="EXACT_REPLAY", hidden_world="H0",
                             stored_original=request,
                             dispatch=lambda value: (calls.append(value), _rz_ack(value))[1],
                             list_orders=lambda: pytest.fail("Replay read"),
                             model_continue=lambda _: pytest.fail("Replay model"))
    assert result.model_calls == 0
    assert calls == [request]
    assert b"receipt" not in calls[0].body
    with pytest.raises(rz.RazorpayPaperError):
        rz.exact_replay(replace(request, body=request.body + b" "), request,
                        lambda _: pytest.fail("mutated Replay dispatched"))


def test_razorpay_regeneration_model_controls_changed_amount():
    request = _rz_request()
    seen = []
    decisions = iter((rz.ModelDecision("create_order", 300, "INR"),
                      rz.ModelDecision("finish")))
    result = rz.run_recovery(arm_id=request.arm_id, marker=request.marker,
                             scope_fingerprint=request.scope_fingerprint,
                             policy="LLM_REGENERATION", hidden_world="H0",
                             stored_original=request,
                             dispatch=lambda value: (seen.append(value), _rz_ack(value))[1],
                             model_continue=lambda _: next(decisions))
    assert result.model_calls == 2
    assert json.loads(seen[0].body)["amount"] == 300
    assert seen[0].marker == request.marker
    assert b"receipt" not in seen[0].body


def test_razorpay_ledger_never_uses_zero_list_as_absence():
    request = _rz_request()
    empty = rz.FetchAllRound(True, False, (), 1, None, False)
    unresolved = rz.evaluate_ledger(
        arm_id=request.arm_id, marker=request.marker,
        dispatches=(rz.LedgerDispatch(request, rz.RawResponse(None, b"", True),
                                      "recovery"),),
        rounds=(empty, empty), original_non_dispatch_certified=True,
        scope_and_writer_history_qualified=True,
        no_hidden_retry_or_redirect=True)
    assert unresolved["status"] == "INCONCLUSIVE"
    assert unresolved["state_correct"] is None
    assert unresolved["authoritative_completeness_qualified"] is False


def test_razorpay_one_dispatch_two_orders_is_infrastructure():
    request = _rz_request()
    second = rz.ValidatedOrder("order_OTHER", 200, "INR", request.marker)
    round_ = rz.FetchAllRound(True, False, (second,), 1, None, False)
    result = rz.evaluate_ledger(
        arm_id=request.arm_id, marker=request.marker,
        dispatches=(rz.LedgerDispatch(request, _rz_ack(request), "recovery"),),
        rounds=(round_,), original_non_dispatch_certified=True,
        scope_and_writer_history_qualified=True,
        no_hidden_retry_or_redirect=True)
    assert result["status"] == "INFRASTRUCTURE_FAILURE"
    assert result["state_correct"] is None


def test_razorpay_closed_ledger_can_prove_one_without_list_authority():
    request = _rz_request()
    result = rz.evaluate_ledger(
        arm_id=request.arm_id, marker=request.marker,
        dispatches=(rz.LedgerDispatch(request, _rz_ack(request), "recovery"),),
        rounds=(), original_non_dispatch_certified=True,
        scope_and_writer_history_qualified=True,
        no_hidden_retry_or_redirect=True)
    assert result["status"] == "SUCCESS"
    assert result["exact_set_proof"] == "CLOSED_CAUSAL_LEDGER"
    assert result["authoritative_completeness_qualified"] is False


def test_razorpay_redirect_terminates_without_resend():
    request = _rz_request()
    calls = []
    response = rz.exact_replay(request, request,
                               lambda value: (calls.append(value),
                                              rz.RawResponse(307, b""))[1])
    assert response.status == 307
    assert len(calls) == 1
    assert rz.validate_ack(request, response) is None


def test_razorpay_obs1_uses_0_200_and_no_unknown_direct_get():
    request = _rz_request()
    now = [20.0]
    starts = []

    def fetch(_):
        starts.append(now[0])
        return rz.RawResponse(200, b'{"entity":"collection","items":[]}')

    rounds, supplements = rz.run_scheduled_observation(
        marker=request.marker, t0=1_000, r0=20.0,
        clock=lambda: now[0], wait_until=lambda target: now.__setitem__(0, target),
        fetch=fetch, direct_get=lambda _: pytest.fail("unknown ID direct GET"))
    assert starts == [20.0, 220.0]
    assert [round_.offset_seconds for round_ in rounds] == [0, 200]
    assert supplements == ()
    assert all(round_.result.authoritative_completeness_qualified is False
               for round_ in rounds)


def test_razorpay_unrelated_historical_order_does_not_poison_list():
    request = _rz_request()
    page = {"entity": "collection", "items": [{
        "id": "order_HISTORICAL", "entity": "order", "amount": 500,
        "currency": "INR", "receipt": "ordinary-receipt", "notes": {},
    }]}
    result = rz.bounded_fetch_all(marker=request.marker, t0=1_000,
                                  fetch=lambda _: rz.RawResponse(200,
                                                                json.dumps(page).encode()),
                                  elapsed=lambda: 0)
    assert result.structurally_complete
    assert result.orders == ()
    assert result.authoritative_completeness_qualified is False


def test_readiness_rejects_missing_manifest_and_audit(tmp_path):
    github = ready.current_static_identity("github")
    assert github["manifest_sha256"] == load_github_paper_manifest().manifest_hash
    razorpay = ready.current_static_identity("razorpay")
    assert razorpay["manifest_sha256"] == sha256_hex((RAZORPAY_ROOT / RAZORPAY_MANIFEST_PATH).read_bytes())
    with pytest.raises(ready.ProviderReadinessError):
        ready.current_static_identity("razorpay", root=tmp_path)
    with pytest.raises(GitHubPaperManifestError):
        ready.current_static_identity("github", root=tmp_path)
    with pytest.raises(ready.ProviderReadinessError):
        ready.check_readiness_lock("github", tmp_path / "lock.json",
                                   evidence_dir=tmp_path,
                                   audit_receipt_path=tmp_path / "receipt.json",
                                   audit_report_path=tmp_path / "report.json")


def test_razorpay_draft_manifest_exact_and_non_authorizing():
    raw = (RAZORPAY_ROOT / RAZORPAY_MANIFEST_PATH).read_bytes()
    manifest = load_razorpay_paper_manifest()
    assert manifest["status"] == RAZORPAY_FROZEN
    assert scientific_projection(manifest) == scientific_projection(json.loads(build_razorpay_paper_manifest()))
    registry = load_namespace_registry()
    assert registry["status"] == RAZORPAY_FROZEN
    assert scientific_projection(registry) == scientific_projection(json.loads(build_namespace_registry()))
    assert len(manifest["families"]) == 64
    markers = [arm["marker"] for family in manifest["families"]
               for arm in family["arms"]]
    assert len(set(markers)) == 256
    assert manifest["collection_status"] == "BLOCKED"
    assert manifest["scope_qualified_currently"] is False
    assert manifest["study2_paper_observations"] == 0
    for family in manifest["families"]:
        for arm in family["arms"]:
            body = json.loads(bytes.fromhex(arm["provider_request_body_hex"]))
            assert set(body) == {"amount", "currency", "notes"}
            assert body["notes"] == {"retry_semantics_marker": arm["marker"]}


def test_readiness_rejects_verdict_strings_as_provider_capture():
    with pytest.raises(ready.ProviderReadinessError):
        ready._check_capture_shape("github", "provider_http_capture",
                                   {"statement": "provider qualified"},
                                   {"statement": "success"})
    with pytest.raises(ready.ProviderReadinessError):
        ready._check_capture_shape("razorpay", "operator_access_inventory",
                                   {"statement": "Fetch All complete"},
                                   {"statement": "authoritative"})


def test_razorpay_freeze_is_status_and_provenance_only():
    for raw in (build_namespace_registry(), build_razorpay_paper_manifest()):
        draft = json.loads(raw)
        assert draft["status"] == RAZORPAY_DRAFT
        audit = {"auditor_id": "offline-auditor",
                 "audit_report_sha256": "a" * 64,
                 "audit_receipt_sha256": "b" * 64,
                 "audited_at_utc": "2026-09-26T00:00:00Z",
                 "audited_scientific_sha256": scientific_sha256(draft)}
        frozen = json.loads(freeze_status_only(raw, audit))
        assert frozen["status"] == RAZORPAY_FROZEN
        assert scientific_projection(frozen) == scientific_projection(draft)
        for key in ("run_namespace", "reservations", "families",
                    "schedule_definition", "observation_policy"):
            if key in draft:
                assert frozen[key] == draft[key]
        with pytest.raises(ValueError):
            freeze_status_only(raw, dict(audit, audited_scientific_sha256="0" * 64))


def test_future_frozen_razorpay_envelopes_load_without_scientific_rematerialization(tmp_path):
    for relative in SOURCE_SHA256:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RAZORPAY_ROOT / relative, destination)
    for relative, draft_builder in (
        (RAZORPAY_REGISTRY_PATH, build_namespace_registry),
        (RAZORPAY_MANIFEST_PATH, build_razorpay_paper_manifest),
    ):
        raw_draft = draft_builder(tmp_path)
        draft = json.loads(raw_draft)
        audit = {"auditor_id": "synthetic-offline-test-only",
                 "audit_report_sha256": "a" * 64,
                 "audit_receipt_sha256": "b" * 64,
                 "audited_at_utc": "2026-09-26T00:00:00Z",
                 "audited_scientific_sha256": scientific_sha256(draft)}
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(freeze_status_only(raw_draft, audit))
    registry = load_razorpay_paper_manifest(tmp_path)
    assert registry["status"] == RAZORPAY_FROZEN
    assert scientific_projection(registry) == scientific_projection(
        load_razorpay_paper_manifest())


def _h1_razorpay_certificate():
    request = rz.serialize_create(arm_id="rz-f001:H1:EXACT_REPLAY",
                                  marker="study2_rzp_paper_h1abc",
                                  scope_fingerprint="a" * 64,
                                  amount=200, currency="INR")
    original = rz.LedgerDispatch(request, _rz_ack(request), "original")
    scope = rz.H1ScopeRecord("b" * 64, request.scope_fingerprint,
                             "c" * 64, "d" * 64, True)
    transport = rz.H1TransportRecord(request.sha256, 1, 1, 0, 0, 0,
                                      True, True, True)
    baseline = rz.FetchAllRound(True, False, (), 1, None, False)
    return request, original, scope, transport, baseline


def test_razorpay_h1_requires_closed_ledger_certificate():
    request, original, scope, transport, baseline = _h1_razorpay_certificate()
    with pytest.raises(rz.RazorpayPaperError):
        rz.run_recovery(arm_id=request.arm_id, marker=request.marker,
                        scope_fingerprint=request.scope_fingerprint,
                        policy="EXACT_REPLAY", hidden_world="H1",
                        stored_original=request, dispatch=lambda _: _rz_ack(request))
    certificate = rz.certify_h1(expected=request, original_dispatch=original,
                                baseline=baseline, positive_rounds=(),
                                scope=scope, transport=transport)
    result = rz.run_recovery(arm_id=request.arm_id, marker=request.marker,
                             scope_fingerprint=request.scope_fingerprint,
                             policy="EXACT_REPLAY", hidden_world="H1",
                             stored_original=request, dispatch=lambda _: _rz_ack(request),
                             h1_certificate=certificate)
    assert result.model_calls == 0
    assert certificate.order_id == "order_ABC123"


@pytest.mark.parametrize("change", [
    "uncertain", "duplicate_dispatch", "hidden_retry", "redirect", "incomplete",
    "duplicate_order", "unintended_order", "wrong_scope",
])
def test_razorpay_h1_hostile_refusals(change):
    request, original, scope, transport, baseline = _h1_razorpay_certificate()
    rounds = ()
    if change == "uncertain":
        original = replace(original, response=rz.RawResponse(None, b"", True))
    elif change == "duplicate_dispatch":
        transport = replace(transport, application_dispatches=2)
    elif change == "hidden_retry":
        transport = replace(transport, automatic_retries=1)
    elif change == "redirect":
        transport = replace(transport, redirect_follows=1)
    elif change == "incomplete":
        baseline = rz.FetchAllRound(False, False, (), 1, "incomplete", False)
    elif change == "duplicate_order":
        rounds = (rz.FetchAllRound(True, False,
                                  (rz.ValidatedOrder("order_SECOND", 200, "INR", request.marker),),
                                  1, None, False),)
    elif change == "unintended_order":
        rounds = (rz.FetchAllRound(True, False,
                                  (rz.ValidatedOrder("order_WRONG", 300, "INR", request.marker),),
                                  1, None, False),)
    else:
        scope = replace(scope, selected_scope_fingerprint="e" * 64)
    with pytest.raises(rz.RazorpayPaperError):
        rz.certify_h1(expected=request, original_dispatch=original,
                      baseline=baseline, positive_rounds=rounds,
                      scope=scope, transport=transport)


def test_razorpay_direct_get_requires_acknowledged_recovery_id():
    request = _rz_request()
    known = rz.known_recovery_order(
        rz.LedgerDispatch(request, _rz_ack(request), "recovery"))
    with pytest.raises(rz.RazorpayPaperError):
        rz.known_recovery_order(rz.LedgerDispatch(request, _rz_ack(request), "original"))
    now = [0.0]
    list_only = {"entity": "collection", "items": [{
        "id": "order_LISTONLY", "entity": "order", "amount": 200,
        "currency": "INR", "receipt": None,
        "notes": {"retry_semantics_marker": request.marker},
    }]}
    direct = []

    def observe(known_ids=()):
        now[0] = 0.0
        return rz.run_scheduled_observation(
            marker=request.marker, t0=1000, r0=0,
            arm_id=request.arm_id,
            scope_fingerprint=request.scope_fingerprint,
            clock=lambda: now[0], wait_until=lambda target: now.__setitem__(0, target),
            fetch=lambda _: rz.RawResponse(200, json.dumps(list_only).encode()),
            direct_get=lambda url: (direct.append(url), _rz_ack(request))[1],
            new_post_recovery_known_ids=known_ids)

    observe()
    assert direct == []
    observe((known, known))
    assert direct == [rz.ORIGIN + rz.PATH + "/order_ABC123"]
    with pytest.raises(rz.RazorpayPaperError):
        observe((replace(known, arm_id="other-arm"),))
    with pytest.raises(rz.RazorpayPaperError):
        observe((replace(known, request=replace(
            known.request, scope_fingerprint="b" * 64)),))


def test_razorpay_direct_get_refuses_more_than_three_independent_ids():
    request = _rz_request()
    known = []
    for index in range(4):
        body = json.loads(_rz_ack(request).body)
        body["id"] = f"order_UNIQUE{index}"
        response = rz.RawResponse(200, json.dumps(body).encode())
        known.append(rz.known_recovery_order(
            rz.LedgerDispatch(request, response, "recovery")))
    with pytest.raises(rz.RazorpayPaperError, match="budget"):
        rz.run_scheduled_observation(
            marker=request.marker, t0=1000, r0=0,
            arm_id=request.arm_id,
            scope_fingerprint=request.scope_fingerprint,
            clock=lambda: 0, wait_until=lambda _: None,
            fetch=lambda _: pytest.fail("budget must reject before read"),
            direct_get=lambda _: pytest.fail("budget must reject before GET"),
            new_post_recovery_known_ids=tuple(known))


def test_razorpay_decisive_stop_adds_no_later_round_or_supplement():
    request = _rz_request()
    now = [0.0]
    fetches = []
    rounds, supplements = rz.run_scheduled_observation(
        marker=request.marker, t0=1000, r0=0,
        clock=lambda: now[0], wait_until=lambda target: now.__setitem__(0, target),
        fetch=lambda url: (fetches.append(url),
                           rz.RawResponse(200, b'{"entity":"collection","items":[]}'))[1],
        direct_get=lambda _: pytest.fail("early stop must skip supplements"),
        decisive_stop=lambda so_far: len(so_far) == 1)
    assert [x.offset_seconds for x in rounds] == [0]
    assert len(fetches) == 1
    assert supplements == ()


def test_github_h1_constructor_stops_on_first_exact_one(github_case):
    manifest, family, arm = github_case
    target = family["target_semantic_m"]
    body = json.dumps([{"number": 91, "title": target["title"],
                        "body": target["body"] + arm["suffix"],
                        "state": "open"}]).encode()
    calls = []
    rounds = gh.run_h1_constructor(
        manifest, family, arm, api_version="2022-11-28", anchor=0,
        clock=lambda: 0, wait_until=lambda _: None,
        fetch=lambda url: (calls.append(url), HTTPResponse(200, (), body))[1])
    assert len(rounds) == 1
    assert len(calls) == 1


def test_github_h1_constructor_waits_after_zero_and_refuses_duplicate(github_case):
    manifest, family, arm = github_case
    target = family["target_semantic_m"]
    original = gh.expected_original(manifest, family, arm,
                                    api_base="https://api.github.com",
                                    api_version="2022-11-28")
    visible = {"number": 31, "title": target["title"],
               "body": target["body"] + arm["suffix"], "state": "open"}
    now = [0.0]
    calls = []

    def fetch(_):
        calls.append(now[0])
        return HTTPResponse(200, (), json.dumps([] if len(calls) == 1
                                                 else [visible]).encode())

    rounds = gh.run_h1_constructor(
        manifest, family, arm, api_version="2022-11-28", anchor=0,
        clock=lambda: now[0], wait_until=lambda target: now.__setitem__(0, target),
        fetch=fetch)
    assert calls == [0.0, 600.0]
    gh.certify_h1(manifest, family, arm, original, _github_ack(original), rounds)
    duplicate = gh.Census(True, ((31, target["title"], target["body"] + arm["suffix"]),
                                  (92, target["title"], target["body"] + arm["suffix"])),
                          1, None, 2)
    with pytest.raises(gh.GitHubPaperError):
        gh.certify_h1(manifest, family, arm, original, _github_ack(original),
                      (gh.ScheduledCensus(0, 0, 540, duplicate),))


def test_github_terminal_prev_link_completes_multi_page_census(github_case):
    manifest, _, arm = github_case
    base = "https://api.github.com/repos/" + manifest["selected_repository"] + "/issues"
    first = [{"number": i + 1, "title": "t", "body": "b", "state": "open"}
             for i in range(100)]
    second = [{"number": 101, "title": "t", "body": "b", "state": "open"}]
    pages = iter((
        HTTPResponse(200, (("Link", f'<{base}?state=all&per_page=100&page=2>; rel="next"'),),
                     json.dumps(first).encode()),
        HTTPResponse(200, (("Link", f'<{base}?state=all&per_page=100&page=1>; rel="prev", '
                                   f'<{base}?state=all&per_page=100&page=1>; rel="first"'),),
                     json.dumps(second).encode()),
    ))
    census = gh.bounded_census(manifest, arm, api_version="2022-11-28",
                               fetch=lambda _: next(pages), elapsed=lambda: 0)
    assert census.complete and census.requests == 2 and census.raw_entries == 101
    duplicate_pages = iter((
        HTTPResponse(200, (("Link", f'<{base}?state=all&per_page=100&page=2>; rel="next"'),),
                     json.dumps(first).encode()),
        HTTPResponse(200, (), json.dumps([first[0]]).encode()),
    ))
    duplicate = gh.bounded_census(manifest, arm, api_version="2022-11-28",
                                  fetch=lambda _: next(duplicate_pages), elapsed=lambda: 0)
    assert duplicate.complete is False


def test_duplicate_provider_json_keys_fail_closed(github_case):
    manifest, _, arm = github_case
    gh_census = gh.bounded_census(
        manifest, arm, api_version="2022-11-28",
        fetch=lambda _: HTTPResponse(200, (),
                                     b'[{"number":1,"number":2,"title":"t","body":"b","state":"open"}]'),
        elapsed=lambda: 0)
    assert gh_census.complete is False
    rz_round = rz.bounded_fetch_all(
        marker="study2_rzp_paper_test", t0=1000,
        fetch=lambda _: rz.RawResponse(
            200, b'{"entity":"collection","entity":"collection","items":[]}'),
        elapsed=lambda: 0)
    assert rz_round.structurally_complete is False


def test_v1_multiple_tool_calls_share_one_model_call_and_obey_provider_order(github_case):
    manifest, family, _ = github_case
    arm = next(x for x in family["arms"] if x["hidden_world"] == "H0"
               and x["policy"] == "LLM_REGENERATION")
    original = gh.expected_original(manifest, family, arm,
                                    api_base="https://api.github.com",
                                    api_version="2022-11-28")
    trace = []

    def decide(context):
        trace.append(("model", context["model_call_index"],
                      context["previous_tool_result"]))
        if context["model_call_index"] == 0:
            return (gh.ModelDecision("list_issues"),
                    gh.ModelDecision("create_issue", "new", "body"))
        return ()

    recovery = gh.run_recovery(
        manifest, family, arm, original, api_version="2022-11-28",
        dispatch=lambda req: (trace.append(("create",)), _github_ack(req))[1],
        fetch=lambda _: (trace.append(("read",)), HTTPResponse(200, (), b"[]"))[1],
        elapsed=lambda: 0, model_continue=decide)
    assert recovery.model_calls == 2
    assert [action.action for action in recovery.actions] == ["list_issues", "create_issue"]
    assert [item[0] for item in trace] == ["model", "read", "create", "model"]
    assert trace[-1][2] == [{"issues": []}, {"status": "created"}]


def test_v1_first_over_budget_call_is_not_dispatched(github_case):
    manifest, family, _ = github_case
    arm = next(x for x in family["arms"] if x["hidden_world"] == "H0"
               and x["policy"] == "LLM_REGENERATION")
    original = gh.expected_original(manifest, family, arm,
                                    api_base="https://api.github.com",
                                    api_version="2022-11-28")
    calls = []
    recovery = gh.run_recovery(
        manifest, family, arm, original, api_version="2022-11-28",
        dispatch=lambda _: pytest.fail("over-budget Create dispatched"),
        fetch=lambda _: HTTPResponse(200, (), b"[]"), elapsed=lambda: 0,
        model_continue=lambda context: (
            (gh.ModelDecision("list_issues"),) * 3 +
            (gh.ModelDecision("create_issue", "x", "y"),)
            if context["model_call_index"] == 0 else ()))
    assert recovery.model_calls == 1
    assert len(recovery.actions) == 3
    assert recovery.terminal_reason == "ACTION_BUDGET_EXCEEDED"


def test_github_rate_stop_inside_model_read_blocks_later_batch_mutation(github_case):
    manifest, family, _ = github_case
    arm = next(x for x in family["arms"] if x["hidden_world"] == "H0"
               and x["policy"] == "LLM_REGENERATION")
    original = gh.expected_original(manifest, family, arm,
                                    api_base="https://api.github.com",
                                    api_version="2022-11-28")
    stopped = [False]

    def fetch(_):
        stopped[0] = True
        return HTTPResponse(429, (), b"rate limited")

    recovery = gh.run_recovery(
        manifest, family, arm, original, api_version="2022-11-28",
        dispatch=lambda _: pytest.fail("post-stop Create dispatched"),
        fetch=fetch, elapsed=lambda: 0, should_stop=lambda: stopped[0],
        model_continue=lambda _: (gh.ModelDecision("list_issues"),
                                  gh.ModelDecision("create_issue", "x", "y")))
    assert recovery.terminal_reason == "PROVIDER_RUN_STOP"
    assert [x.action for x in recovery.actions] == ["list_issues"]
