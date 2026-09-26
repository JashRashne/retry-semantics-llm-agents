"""Cross-control substitution and wrong-scope readiness attacks."""

import json

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.github_paper_manifest import (
    load_github_paper_manifest, load_namespace_registry as github_registry,
)
from retry_semantics.study2.razorpay_paper_manifest import (
    load_razorpay_paper_manifest, load_namespace_registry as razorpay_registry,
    scientific_sha256,
)
from retry_semantics.study2.provider_paper_readiness_controls import (
    ControlEvidenceError, validate_github_control, validate_razorpay_control,
)
from retry_semantics.study2 import github_paper_runtime as gh
from retry_semantics.study2 import razorpay_paper_runtime as rz
from retry_semantics.study2.provider_paper_readiness import (
    ProviderReadinessError, _check_capture_shape,
)


VERSION = "2022-11-28"
REPO = "JashRashne/retry-semantics-study2-github-sandbox"
GH_BASE = "https://api.github.com/repos/" + REPO


def pair(method, url, body, status=200, *, version=None, scope=None, extra=None):
    headers = {}
    response_headers = {}
    if version is not None:
        headers = {"X-GitHub-Api-Version": version,
                   "Accept": "application/vnd.github.raw+json"}
        response_headers = {"x-github-api-version-selected": version}
    if extra:
        response_headers.update(extra)
    request = {"method": method, "url": url, "headers": headers,
               "body_hex": "", "dispatch_started": True, "attempt_count": 1}
    if scope:
        request["credential_scope_fingerprint"] = scope
    response = {"http_status": status, "headers": response_headers,
                "body_hex": canonical_json_bytes(body).hex(),
                "transport_complete": True, "redirect_followed": False}
    return {"request": request, "response": response}


def capture(item):
    return {"request_evidence": item["request"],
            "response_evidence": item["response"],
            "source": "provider_http_capture"}


@pytest.fixture(scope="module")
def gh_inputs():
    return load_github_paper_manifest().as_json(), github_registry().as_json()


def gh_baseline(manifest, count=0, *, repo=REPO, version=VERSION, complete=True):
    identity = pair("GET", "https://api.github.com/repos/" + repo,
                    {"id": 41, "full_name": repo}, version=version)
    pages = []
    for page in range((count + 99) // 100 or 1):
        start = page * 100
        size = min(100, count - start)
        entries = [{"number": index + 1, "title": "t", "body": "b",
                    "state": "open"} for index in range(start, start + size)]
        page_url = GH_BASE + f"/issues?state=all&per_page=100&page={page + 1}"
        links = {}
        if (page + 1) * 100 <= count or (not complete and page == 0):
            next_url = GH_BASE + f"/issues?state=all&per_page=100&page={page + 2}"
            links = {"link": f'<{next_url}>; rel="next"'}
        pages.append(pair("GET", page_url, entries, version=VERSION, extra=links))
    facts = {"api_version": version, "repository_id": 41,
             "identity_recheck": identity, "baseline_pages": pages,
             "baseline_raw_entries": count}
    return facts, capture(identity)


def test_github_baseline_exact_scope_version_completion_and_cap(gh_inputs):
    manifest, registry = gh_inputs
    facts, primary = gh_baseline(manifest)
    context = {}
    validate_github_control("repository_identity_and_full_baseline",
                            manifest, registry, facts, primary, context)
    assert context["github_repository_id"] == 41
    for hostile in (
        gh_baseline(manifest, repo="someone/other"),
        gh_baseline(manifest, version="2020-01-01"),
        gh_baseline(manifest, complete=False),
        gh_baseline(manifest, count=861),
    ):
        with pytest.raises(ControlEvidenceError):
            validate_github_control("repository_identity_and_full_baseline",
                                    manifest, registry, *hostile, {})


def test_github_baseline_and_principal_cannot_swap_controls(gh_inputs):
    manifest, registry = gh_inputs
    facts, primary = gh_baseline(manifest)
    context = {}
    validate_github_control("repository_identity_and_full_baseline",
                            manifest, registry, facts, primary, context)
    with pytest.raises(ControlEvidenceError):
        validate_github_control("authenticated_principal_access",
                                manifest, registry, facts, primary, context)
    user = pair("GET", "https://api.github.com/user",
                {"id": 77, "login": "researcher"}, version=VERSION)
    read = pair("GET", GH_BASE + "/issues?state=all&per_page=100&page=1",
                [], version=VERSION)
    write = pair("POST", GH_BASE + "/issues",
                 {"number": 10}, status=201, version=VERSION)
    write["request"]["body_hex"] = canonical_json_bytes(
        {"title": "probe title", "body": "probe body"}).hex()
    principal = {"api_version": VERSION, "principal_id": 77,
                 "principal_login": "researcher", "repository_id": 41,
                 "issues_read_probe": read, "issues_write_probe": write}
    validate_github_control("authenticated_principal_access", manifest,
                            registry, principal, capture(user), context)

    # 1. Hostile: empty body_hex is rejected
    empty_body_write = pair("POST", GH_BASE + "/issues",
                            {"number": 10}, status=201, version=VERSION)
    empty_body_write["request"]["body_hex"] = ""
    with pytest.raises(ControlEvidenceError, match="body is empty or missing"):
        validate_github_control("authenticated_principal_access", manifest,
                                registry, dict(principal, issues_write_probe=empty_body_write),
                                capture(user), context)

    # 2. Hostile: lacking body or invalid body shape rejected
    for bad_body in (
        {"title": "only title"},
        {"body": "only body"},
        {"title": "t", "body": "b", "extra": 1},
        {"title": 123, "body": "b"},
        {"title": "t", "body": 123},
        ["not", "a", "dict"],
    ):
        bad_shape_write = pair("POST", GH_BASE + "/issues",
                               {"number": 10}, status=201, version=VERSION)
        bad_shape_write["request"]["body_hex"] = canonical_json_bytes(bad_body).hex()
        with pytest.raises(ControlEvidenceError):
            validate_github_control("authenticated_principal_access", manifest,
                                    registry, dict(principal, issues_write_probe=bad_shape_write),
                                    capture(user), context)

    bad_json_write = pair("POST", GH_BASE + "/issues",
                          {"number": 10}, status=201, version=VERSION)
    bad_json_write["request"]["body_hex"] = b"not-json".hex()
    with pytest.raises(ControlEvidenceError):
        validate_github_control("authenticated_principal_access", manifest,
                                registry, dict(principal, issues_write_probe=bad_json_write),
                                capture(user), context)

    # 3. Hostile: write probe consuming reserved suffix from registry must be rejected
    s0 = registry["reservations"][0]["suffix"]
    hostile_write = pair("POST", GH_BASE + "/issues",
                         {"number": 11, "title": "t", "body": "test body" + s0},
                         status=201, version=VERSION)
    hostile_write["request"]["body_hex"] = canonical_json_bytes(
        {"title": "t", "body": "test body" + s0}).hex()
    with pytest.raises(ControlEvidenceError, match="consumed reserved paper suffix"):
        validate_github_control("authenticated_principal_access", manifest,
                                registry, dict(principal, issues_write_probe=hostile_write),
                                capture(user), context)

    # 4. Safe non-paper write probe passes
    safe_write = pair("POST", GH_BASE + "/issues",
                      {"number": 12, "title": "t", "body": "safe qualification body"},
                      status=201, version=VERSION)
    safe_write["request"]["body_hex"] = canonical_json_bytes(
        {"title": "t", "body": "safe qualification body"}).hex()
    validate_github_control("authenticated_principal_access", manifest,
                            registry, dict(principal, issues_write_probe=safe_write),
                            capture(user), context)
    traversal = {"api_version": VERSION,
                 "baseline_pages_sha256": context["github_baseline_digest"],
                 "pages": facts["baseline_pages"], "page_cap": 16,
                 "request_timeout_seconds": 30,
                 "traversal_deadline_seconds": 540}
    with pytest.raises(ControlEvidenceError):
        validate_github_control("bounded_raw_traversal_authority", manifest,
                                registry, traversal, capture(user), context)


def test_github_suffix_collision_and_quota_refused(gh_inputs):
    manifest, registry = gh_inputs
    facts, primary = gh_baseline(manifest)
    context = {}
    validate_github_control("repository_identity_and_full_baseline",
                            manifest, registry, facts, primary, context)
    suffix = registry["reservations"][0]["suffix"]
    context["github_baseline"] = [{"body": "old" + suffix}]
    create = pair("POST", GH_BASE + "/issues",
                  {"number": 50, "title": "t", "body": "b" + suffix},
                  status=201, version=VERSION)
    create["request"]["body_hex"] = canonical_json_bytes(
        {"title": "t", "body": "b" + suffix}).hex()
    read = pair("GET", GH_BASE + "/issues?state=all&per_page=100&page=1",
                [{"number": 50, "title": "t", "body": "b" + suffix}],
                version=VERSION)
    suffix_facts = {"api_version": VERSION,
                    "baseline_pages_sha256": context["github_baseline_digest"],
                    "qualification_read": read}
    with pytest.raises(ControlEvidenceError):
        validate_github_control("suffix_roundtrip_and_collision_scan",
                                manifest, registry, suffix_facts, capture(create), context)

    # Clean baseline to isolate qualification suffix checks
    context["github_baseline"] = []

    # Hostile: qualification suffix consumed reserved paper suffix from registry
    hostile_create = pair("POST", GH_BASE + "/issues",
                          {"number": 51, "title": "t", "body": "probe" + suffix},
                          status=201, version=VERSION)
    hostile_create["request"]["body_hex"] = canonical_json_bytes(
        {"title": "t", "body": "probe" + suffix}).hex()
    hostile_read = pair("GET", GH_BASE + "/issues?state=all&per_page=100&page=1",
                        [{"number": 51, "title": "t", "body": "probe" + suffix}],
                        version=VERSION)
    hostile_suffix_facts = {"api_version": VERSION,
                            "baseline_pages_sha256": context["github_baseline_digest"],
                            "qualification_read": hostile_read}
    with pytest.raises(ControlEvidenceError, match="consumed reserved paper suffix"):
        validate_github_control("suffix_roundtrip_and_collision_scan",
                                manifest, registry, hostile_suffix_facts,
                                capture(hostile_create), context)

    # Hostile: qualification suffix syntax invalid
    bad_syntax_suffix = "\n\n<!-- retry-semantics-study2-gh:v1:rs2gh1-not-32-hex -->"
    bad_syntax_create = pair("POST", GH_BASE + "/issues",
                             {"number": 52, "title": "t", "body": "probe" + bad_syntax_suffix},
                             status=201, version=VERSION)
    bad_syntax_create["request"]["body_hex"] = canonical_json_bytes(
        {"title": "t", "body": "probe" + bad_syntax_suffix}).hex()
    bad_syntax_read = pair("GET", GH_BASE + "/issues?state=all&per_page=100&page=1",
                           [{"number": 52, "title": "t", "body": "probe" + bad_syntax_suffix}],
                           version=VERSION)
    bad_syntax_facts = {"api_version": VERSION,
                        "baseline_pages_sha256": context["github_baseline_digest"],
                        "qualification_read": bad_syntax_read}
    with pytest.raises(ControlEvidenceError, match="syntax invalid"):
        validate_github_control("suffix_roundtrip_and_collision_scan",
                                manifest, registry, bad_syntax_facts,
                                capture(bad_syntax_create), context)

    # Safe non-paper qualification suffix passes
    safe_suffix = "\n\n<!-- retry-semantics-study2-gh:v1:rs2gh1-" + "0" * 32 + " -->"
    safe_create = pair("POST", GH_BASE + "/issues",
                       {"number": 53, "title": "t", "body": "probe" + safe_suffix},
                       status=201, version=VERSION)
    safe_create["request"]["body_hex"] = canonical_json_bytes(
        {"title": "t", "body": "probe" + safe_suffix}).hex()
    safe_read = pair("GET", GH_BASE + "/issues?state=all&per_page=100&page=1",
                     [{"number": 53, "title": "t", "body": "probe" + safe_suffix}],
                     version=VERSION)
    safe_suffix_facts = {"api_version": VERSION,
                         "baseline_pages_sha256": context["github_baseline_digest"],
                         "qualification_read": safe_read}
    validate_github_control("suffix_roundtrip_and_collision_scan",
                            manifest, registry, safe_suffix_facts,
                            capture(safe_create), context)

    quota = pair("GET", "https://api.github.com/rate_limit",
                 {"resources": {"core": {"remaining": 1, "limit": 5000}}},
                 version=VERSION)
    quota_facts = {"api_version": VERSION, "repository_id": 41,
                   "max_creates": 640, "max_gets_per_arm": gh.MAX_GETS_PER_ARM,
                   "peak_requests_per_hour": 100,
                   "secondary_limit_qualified": True,
                   "immediate_requests_required": 32}
    with pytest.raises(ControlEvidenceError):
        validate_github_control("quota_and_timing_headroom", manifest, registry,
                                quota_facts, capture(quota), context)


def test_github_quota_timing_requires_measured_complete_traversal(gh_inputs):
    manifest, registry = gh_inputs
    baseline_facts, baseline_capture = gh_baseline(manifest)
    context = {}
    validate_github_control("repository_identity_and_full_baseline",
                            manifest, registry, baseline_facts,
                            baseline_capture, context)
    page = baseline_facts["baseline_pages"][0]
    page["request"]["started_monotonic"] = 10.0
    page["response"]["ended_monotonic"] = 15.0
    quota = pair("GET", "https://api.github.com/rate_limit",
                 {"resources": {"core": {"remaining": 1000, "limit": 5000}}},
                 version=VERSION)
    facts = {"api_version": VERSION, "repository_id": 41,
             "max_creates": 640, "max_gets_per_arm": gh.MAX_GETS_PER_ARM,
             "peak_requests_per_hour": 100,
             "secondary_limit_qualified": True,
             "immediate_requests_required": 32,
             "timed_pages": [page], "observed_max_request_seconds": 5.0,
             "observed_traversal_seconds": 5.0}
    validate_github_control("quota_and_timing_headroom", manifest, registry,
                            facts, capture(quota), context)
    # Hostile: magic 32 is rejected
    with pytest.raises(ControlEvidenceError):
        validate_github_control("quota_and_timing_headroom", manifest, registry,
                                dict(facts, max_gets_per_arm=32), capture(quota), context)
    # Hostile: 127 (one below derived 128 bound) is rejected
    with pytest.raises(ControlEvidenceError):
        validate_github_control("quota_and_timing_headroom", manifest, registry,
                                dict(facts, max_gets_per_arm=gh.MAX_GETS_PER_ARM - 1),
                                capture(quota), context)
    page["response"]["ended_monotonic"] = 45.0
    with pytest.raises(ControlEvidenceError):
        validate_github_control("quota_and_timing_headroom", manifest, registry,
                                facts, capture(quota), context)


@pytest.fixture(scope="module")
def rz_inputs():
    return load_razorpay_paper_manifest(), razorpay_registry()


def test_razorpay_wrong_scope_and_arbitrary_200_rejected(rz_inputs):
    manifest, registry = rz_inputs
    scope = manifest["credential_scope_fingerprint"]
    order_id = "order_TfBuv3iQHQrz9p"
    marker = "study2_razorpay_eng_2c351a8910944e468dd1a902b97e8215"
    probe = pair("GET", rz.ORIGIN + rz.PATH + "/" + order_id,
                 {"entity": "order", "id": order_id,
                  "notes": {"retry_semantics_marker": marker}}, scope=scope)
    facts = {"credential_scope_fingerprint": scope,
             "phase1_test_mode_lock_sha256":
                 "2afc652fa636204613168e6ba5fd4640205c6728f8fb7e14eeb07c698425e551",
             "historical_test_order_id": order_id,
             "historical_test_marker": marker}
    context = {}
    validate_razorpay_control("test_mode_scope_access", manifest,
                              registry, facts, capture(probe), context)
    wrong = pair("GET", rz.ORIGIN + "/v1/payments",
                 {"entity": "collection", "items": []}, scope=scope)
    with pytest.raises(ControlEvidenceError):
        validate_razorpay_control("test_mode_scope_access", manifest,
                                  registry, facts, capture(wrong), {})
    arbitrary = pair("GET", rz.ORIGIN + rz.PATH + "/" + order_id,
                     {"entity": "order", "id": "order_NOTHISTORICAL",
                      "notes": {"retry_semantics_marker": marker}}, scope=scope)
    with pytest.raises(ControlEvidenceError):
        validate_razorpay_control("test_mode_scope_access", manifest,
                                  registry, facts, capture(arbitrary), {})
    with pytest.raises(ControlEvidenceError):
        validate_razorpay_control("test_mode_scope_access", manifest,
                                  registry, dict(facts, credential_scope_fingerprint="0" * 64),
                                  capture(probe), {})


def test_razorpay_marker_collision_and_fetchall_cannot_substitute_transport(rz_inputs):
    manifest, registry = rz_inputs
    scope = manifest["credential_scope_fingerprint"]
    marker = registry["reservations"][0]["arm_marker"]
    t0 = 1000
    first, last = rz.window(t0)
    url = rz.ORIGIN + rz.PATH + f"?count=100&skip=0&from={first}&to={last}"
    order = {"id": "order_COLLIDE", "entity": "order", "amount": 200,
             "currency": "INR", "receipt": None,
             "notes": {"retry_semantics_marker": marker}}
    page = pair("GET", url, {"entity": "collection", "items": [order]},
                scope=scope)
    facts = {"credential_scope_fingerprint": scope,
             "registry_semantic_sha256": scientific_sha256(registry),
             "writer_history_audit_sha256": "a" * 64,
             "baseline": [page], "t0": t0,
             "no_preexisting_attributable_effect": True}
    with pytest.raises(ControlEvidenceError):
        validate_razorpay_control("marker_reservation_and_collision_scan",
                                  manifest, registry, facts, capture(page),
                                  {"razorpay_scope": scope,
                                   "razorpay_writer_inventory_sha": "a" * 64})
    with pytest.raises(ControlEvidenceError):
        validate_razorpay_control("closed_ledger_transport", manifest,
                                  registry, facts, capture(page),
                                  {"razorpay_scope": scope})


def test_razorpay_closed_ledger_transport_rejects_reserved_marker(rz_inputs):
    manifest, registry = rz_inputs
    scope = manifest["credential_scope_fingerprint"]
    orders = rz.ORIGIN + rz.PATH
    context = {"razorpay_scope": scope, "razorpay_account": scope}

    # 1. Hostile: qualification Create marker equals reserved paper marker from registry
    reserved_marker = registry["reservations"][0]["arm_marker"]
    bad_req_body = canonical_json_bytes({"amount": 200, "currency": "INR",
                                         "notes": {"retry_semantics_marker": reserved_marker}})
    bad_pair = pair("POST", orders, {"id": "order_bad", "entity": "order"}, scope=scope)
    bad_pair["request"]["body_hex"] = bad_req_body.hex()
    bad_facts = {
        "credential_scope_fingerprint": scope,
        "account_id": scope,
        "qualification_arm_id": "qualification:arm1",
        "request_identity_sha256": "0" * 64,
        "application_dispatches": 1,
        "network_dispatches": 1,
        "automatic_retries": 0,
        "redirect_follows": 0,
        "auth_resends": 0,
        "authoritative_completeness_qualified": False,
    }
    with pytest.raises(ControlEvidenceError, match="consumed reserved paper marker"):
        validate_razorpay_control("closed_ledger_transport", manifest, registry,
                                  bad_facts, capture(bad_pair), context)

    # 2. Safe non-paper qualification marker passes
    safe_marker = "study2_qual_safe_marker_01"
    safe_prepared = rz.serialize_create(
        arm_id="qualification:arm1",
        marker=safe_marker,
        scope_fingerprint=scope,
        amount=200,
        currency="INR",
    )
    safe_pair = pair("POST", orders, {"id": "order_safe", "entity": "order"}, scope=scope)
    safe_pair["request"]["body_hex"] = safe_prepared.body.hex()
    safe_facts = {
        "credential_scope_fingerprint": scope,
        "account_id": scope,
        "qualification_arm_id": "qualification:arm1",
        "request_identity_sha256": safe_prepared.sha256,
        "application_dispatches": 1,
        "network_dispatches": 1,
        "automatic_retries": 0,
        "redirect_follows": 0,
        "auth_resends": 0,
        "authoritative_completeness_qualified": False,
    }
    validate_razorpay_control("closed_ledger_transport", manifest, registry,
                              safe_facts, capture(safe_pair), context)


def test_model_capability_requires_raw_tool_call_and_cannot_replace_provider(gh_inputs):
    manifest, registry = gh_inputs
    tools_sha = sha256_hex(canonical_json_bytes(manifest["model_visible_common"]["tools"]))
    params_sha = sha256_hex(canonical_json_bytes(
        manifest["families"][0]["model_config"]["original_generation"]))
    completion = {"choices": [{"message": {"role": "assistant", "content": None,
                                "tool_calls": [{"id": "offline", "type": "function",
                                                "function": {"name": "create_issue",
                                                             "arguments": '{"title":"a","body":"b"}'}}]},
                                "finish_reason": "tool_calls"}]}
    raw = canonical_json_bytes(completion)
    config = manifest["families"][0]["model_config"]["original_generation"]
    payload = canonical_json_bytes({
        "model": "accounts/fireworks/models/deepseek-v4-flash-0731",
        "messages": [{"role": "user", "content": "offline capability probe"}],
        "tools": [{"type": "function", "function": tool}
                  for tool in manifest["model_visible_common"]["tools"]],
        "tool_choice": "auto", "parallel_tool_calls": False,
        "temperature": config["temperature"], "top_p": config["top_p"],
        "seed": config["seed"],
        "max_completion_tokens": config["max_output_tokens"],
        "reasoning_effort": "none",
    })
    model_capture = {
        "source": "model_capability_capture",
        "request_evidence": {"model": "accounts/fireworks/models/deepseek-v4-flash-0731",
                             "tools_sha256": tools_sha,
                             "parameters_sha256": params_sha,
                             "payload_hex": payload.hex(),
                             "payload_sha256": sha256_hex(payload)},
        "response_evidence": {"model_accepted": True,
                              "tool_call_supported": True,
                              "raw_response_sha256": sha256_hex(raw),
                              "raw_response_hex": raw.hex()},
    }
    facts = {"model": model_capture["request_evidence"]["model"],
             "tools_sha256": tools_sha, "parameters_sha256": params_sha,
             "manifest_sha256": sha256_hex(canonical_json_bytes(manifest))}
    _check_capture_shape("github", "model_capability_capture",
                         model_capture["request_evidence"],
                         model_capture["response_evidence"])
    validate_github_control("model_capability", manifest, registry,
                            facts, model_capture, {})
    with pytest.raises(ControlEvidenceError):
        validate_github_control("repository_identity_and_full_baseline",
                                manifest, registry, facts, model_capture, {})
    wrong = dict(model_capture["response_evidence"], raw_response_hex="00")
    with pytest.raises(ProviderReadinessError):
        _check_capture_shape("github", "model_capability_capture",
                             model_capture["request_evidence"], wrong)


def test_razorpay_timing_requires_measured_fetch_all_round(rz_inputs):
    manifest, registry = rz_inputs
    scope = manifest["credential_scope_fingerprint"]
    marker = registry["reservations"][0]["arm_marker"]
    t0 = 1000
    first, last = rz.window(t0)
    page = pair("GET", rz.ORIGIN + rz.PATH +
                f"?count=100&skip=0&from={first}&to={last}",
                {"entity": "collection", "items": []}, scope=scope)
    page["request"]["started_monotonic"] = 10.0
    page["response"]["ended_monotonic"] = 15.0
    facts = {"credential_scope_fingerprint": scope, "t0": t0,
             "request_cap_seconds": 30, "round_deadlines_seconds": [170, 370],
             "terminal_deadline_seconds": 470, "D_seconds": 1020,
             "observed_max_request_seconds": 5.0,
             "observed_max_round_seconds": 5.0,
             "timed_pages": [page]}
    context = {"razorpay_scope": scope, "razorpay_t0": t0,
               "razorpay_marker": marker}
    validate_razorpay_control("timing_headroom", manifest, registry,
                              facts, capture(page), context)
    page["response"]["ended_monotonic"] = 45.0
    with pytest.raises(ControlEvidenceError):
        validate_razorpay_control("timing_headroom", manifest, registry,
                                  facts, capture(page), context)
