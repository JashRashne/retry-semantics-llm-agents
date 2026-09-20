"""Hostile OFFLINE Phase 3 qualification. No real identities or authorizations."""
from dataclasses import FrozenInstanceError, asdict, replace
import base64
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import socket
import ssl
import time
from urllib.parse import parse_qs, urlsplit
import urllib.request

import pytest

from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2 import sheets_live_go_phase1 as p1
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2 import sheets_phase2_control as p2
from retry_semantics.study2 import sheets_phase2_read as read
from retry_semantics.study2 import sheets_phase3_control as control
from retry_semantics.study2 import sheets_phase3_credentials as credentials
from retry_semantics.study2 import sheets_phase3_operator as operator
from test_study2_sheets_phase2 import FakeTLS, Wire, payload

SECRET = "ya29.nonsecret-hostile-phase3-bearer"
REFRESH = "1//nonsecret-hostile-refresh"
CLIENT_SECRET = "nonsecret-hostile-client-secret"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*a, **kw):
        pytest.fail("real network forbidden in Phase 3 qualification")
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname",
                 "gethostbyname_ex", "getnameinfo"):
        monkeypatch.setattr(socket, name, denied)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", denied)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", denied)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(os, "environ", {})


@pytest.fixture
def config():
    return credentials.ClientConfig("123-abc.apps.googleusercontent.com", CLIENT_SECRET, "engineering_project")


@pytest.fixture
def record(config):
    return control.ProvisioningRecord("TEST_ONLY", "same-app-sheets-create-separately-authorized",
        config.public_hash, "engineering_account", "TEST_ONLY_phase3", 7, 100, "phase3_reservation",
        "test_operator", time.time() - 30, control.PROVISION_CONFIRMATION, True, True)


@pytest.fixture
def configuration(tmp_path):
    return control.RuntimeConfiguration(1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 1,
                                        100000, 512, str(tmp_path / "registry"), "TEST_ONLY_caps")


@pytest.fixture
def local(record, configuration, monkeypatch):
    monkeypatch.setattr(control, "repository_check", lambda expected: p2.require(expected == "a" * 40))
    conditions = control.LocalConditions(True, True, True, True, True)
    with p2.LocalRegistry(Path(configuration.registry_root)) as registry:
        registry.reserve(record.fixture())
    return dict(descriptor=control.fixture_descriptor(record), configuration=configuration,
        expected_pin=control.runtime_projection(configuration), expected_head="a" * 40,
        conditions=conditions)


def issue(local, **changes):
    now = time.time()
    values = dict(**local, capability="LIVE_READ_GO", fixture_hash=local["descriptor"]["fixture_hash"],
        credential_metadata=credentials.AcquisitionMetadata(
            local["descriptor"]["fixture"]["provenance"]["public_app_config_sha256"],
            "engineering_account", now - 2, now - 1, now + 3600, 1),
        phase3_runtime_hash=control.runtime_hash(local["configuration"]), phase3_source_hash=control.source_hash(),
        authorization_id="TEST_ONLY_authorization", operator_alias="test_operator", issued_at=now,
        expires_at=now + 20, operator_confirmation=p1.CONFIRMATION, purpose=p1.PURPOSE,
        engineering_only=True, now=now, _test_only=True)
    return control.issue_authorization(**{**values, **changes})


def token_body(**changes):
    return canonical_json_bytes({**dict(access_token=SECRET, expires_in=3600,
        scope=p1.SCOPE, token_type="Bearer", refresh_token=REFRESH), **changes})


def validate(body, config, **changes):
    now = time.time()
    return credentials.validate_token_response(body, config, **{**dict(account_alias="engineering_account",
        exchange_started_at=now - 2, prepared_at=now, clock_uncertainty_seconds=1), **changes})


def test_template_is_valid_and_nonexecutable():
    value = json.loads((frozen.SHEETS_DOCS / "fixtures/qualification_fixture_phase3_template.json").read_text())
    assert value["executable"] is False and value["expected_spreadsheet_id"] is None
    assert value["provisioning_record"] is None and value["paper_observations"] == 0
    with pytest.raises(frozen.QualificationError):
        control.parse_fixture_descriptor(value)


def test_fixture_record_hash_namespace_and_provenance(record):
    value = control.fixture_descriptor(record)
    fixture = control.parse_fixture_descriptor(value, _test_only=True)
    assert fixture.provenance.provisioning_evidence_sha256 == record.evidence_hash
    assert fixture.marker_namespace == value["fixture"]["marker_namespace"]
    assert fixture.verifier_range == "'RetrySemanticsEngineering'!A1:C100"
    assert replace(record, reservation_id="other").fixture().marker_namespace != fixture.marker_namespace
    assert replace(record, operator_alias="other").fixture().manifest_hash != fixture.manifest_hash
    with pytest.raises(frozen.QualificationError):
        control.parse_fixture_descriptor(value)


@pytest.mark.parametrize("field,value", [
    ("mechanism", "arbitrary-id"), ("mechanism", "selected-through-url"),
    ("public_app_config_sha256", ""), ("identity_kind", "DRAFT"),
    ("operator_confirmation", ""), ("engineering_only", False),
    ("isolated", False), ("no_automation_or_writers", False),
    ("sheet_id", True), ("rows", 1001), ("reservation_id", "secret"),
])
def test_incomplete_or_unreviewed_provenance_rejected(record, field, value):
    with pytest.raises(frozen.QualificationError):
        replace(record, **{field: value})


@pytest.mark.parametrize("field", ["fixture_hash", "provisioning_evidence_sha256", "marker_namespace",
                                  "bounded_read", "spreadsheet_id", "record"])
def test_fixture_tampering_rejected(record, field):
    value = control.fixture_descriptor(record)
    if field in ("fixture_hash", "provisioning_evidence_sha256"):
        value[field] = "0" * 64
    elif field == "record":
        value["provisioning_record"]["operator_alias"] = "other"
    else:
        value["fixture"][field] = "changed"
    with pytest.raises(frozen.QualificationError):
        control.parse_fixture_descriptor(value, _test_only=True)


def test_arbitrary_real_id_cannot_supply_missing_record(record):
    real = replace(record, identity_kind="PROVISIONED", spreadsheet_id="A" * 44)
    value = control.fixture_descriptor(real)
    value["provisioning_record"] = {"spreadsheet_id": "A" * 44}
    with pytest.raises(frozen.QualificationError):
        control.parse_fixture_descriptor(value)


def test_collision_and_reuse_fail_closed(local, record):
    with p2.LocalRegistry(Path(local["configuration"].registry_root)) as registry:
        for candidate in (record, replace(record, reservation_id="other"), replace(record, sheet_id=8)):
            with pytest.raises(frozen.QualificationError):
                registry.reserve(candidate.fixture())


def test_public_config_hash_excludes_secret_and_repr(config):
    assert replace(config, client_secret="another-secret").public_hash == config.public_hash
    assert replace(config, client_id="456.apps.googleusercontent.com").public_hash != config.public_hash
    assert CLIENT_SECRET not in repr(config) + json.dumps(config.public_projection())


def client_file(config):
    return {"installed": {"client_id": config.client_id, "client_secret": config.client_secret,
        "project_id": config.project_id, "auth_uri": credentials.AUTH_URI,
        "token_uri": credentials.TOKEN_URI, "auth_provider_x509_cert_url":
        "https://www.googleapis.com/oauth2/v1/certs", "redirect_uris": ["http://localhost"]}}


def test_explicit_private_config_no_ambient_discovery(config, tmp_path, monkeypatch):
    path = tmp_path / "client.json"
    control.write_json(path, client_file(config))
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/arbitrary-cache")
    assert credentials.load_client_config(path, reviewed_public_hash=config.public_hash).public_hash == config.public_hash
    with pytest.raises(credentials.CredentialRefused):
        credentials.load_client_config(tmp_path / "missing", reviewed_public_hash=config.public_hash)
    with pytest.raises(credentials.CredentialRefused):
        credentials.load_client_config()


@pytest.mark.parametrize("attack", ["web", "wrong-endpoint", "scope", "public-hash", "mode", "link", "extra", "duplicate"])
def test_bad_client_source_refused(config, tmp_path, attack):
    path = tmp_path / "client.json"
    value = client_file(config)
    if attack == "web": value = {"web": value["installed"]}
    if attack == "wrong-endpoint": value["installed"]["token_uri"] = "https://evil.invalid"
    if attack == "scope": value["installed"]["scope"] = "https://www.googleapis.com/auth/drive"
    if attack == "extra": value["cache"] = REFRESH
    control.write_json(path, value)
    if attack == "mode": path.chmod(0o644)
    if attack == "link":
        target = tmp_path / "link.json"
        target.symlink_to(path)
        path = target
    if attack == "duplicate": path.write_bytes(b'{"installed":{},"installed":{}}')
    with pytest.raises(credentials.CredentialRefused) as error:
        credentials.load_client_config(path, reviewed_public_hash="0" * 64 if attack == "public-hash" else config.public_hash)
    assert error.value.__context__ is None and error.value.__cause__ is None


def test_pkce_exact_scope_no_incremental_or_offline_access(config):
    preparer = credentials.DesktopPreparer(config)
    args = parse_qs(urlsplit(preparer.authorization_url("http://127.0.0.1:12345/")).query)
    assert args["scope"] == [p1.SCOPE] and args["code_challenge_method"] == ["S256"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(preparer._verifier.encode()).digest()).rstrip(b"=").decode()
    assert args["code_challenge"] == [challenge]
    assert args["access_type"] == ["online"] and args["include_granted_scopes"] == ["false"]
    assert preparer._verifier not in repr(preparer) and not hasattr(preparer, "refresh")


@pytest.mark.parametrize("uri", ["http://localhost:1234/", "https://evil.invalid/", "http://127.0.0.1:70000/",
                                  "http://127.0.0.1:1234/?scope=drive", "urn:ietf:wg:oauth:2.0:oob"])
def test_redirect_fail_closed(config, uri):
    with pytest.raises(credentials.CredentialRefused):
        credentials.DesktopPreparer(config).authorization_url(uri)


def test_valid_export_conservative_expiry_no_refresh_object(config):
    token, metadata = validate(token_body(), config, exchange_started_at=100, prepared_at=102)
    assert type(token) is frozen.PreparedToken and token.expires_at == 3700
    assert type(metadata.transport_provenance()) is p1.CredentialProvenance
    text = repr(token) + json.dumps(metadata.projection())
    assert all(secret not in text for secret in (SECRET, REFRESH, CLIENT_SECRET))
    assert not hasattr(token, "refresh")
    with pytest.raises(FrozenInstanceError): token.value = "other"


@pytest.mark.parametrize("change", [
    {"scope": ""}, {"scope": "https://www.googleapis.com/auth/drive"},
    {"scope": p1.SCOPE + " other"}, {"scope": p1.SCOPE + " " + p1.SCOPE},
    {"scope": [p1.SCOPE]}, {"token_type": "bearer"}, {"token_type": "DPoP"},
    {"expires_in": 0}, {"expires_in": -1}, {"expires_in": True}, {"expires_in": "3600"},
    {"expires_in": float("inf")}, {"expires_in": float("nan")},
    {"access_token": ""}, {"access_token": "a\r\nb"}, {"access_token": object()},
    {"access_token": "a" * 8193}, {"unexpected": SECRET},
])
def test_bad_token_contract_no_secret_errors(config, change):
    try:
        body = token_body(**change)
    except (ValueError, TypeError):
        body = json.dumps({**dict(access_token=SECRET, scope=p1.SCOPE, token_type="Bearer", expires_in=3600),
                           **change}, default=lambda _: None).encode()
    with pytest.raises(credentials.CredentialRefused) as error:
        validate(body, config)
    assert error.value.args == () and error.value.__context__ is None
    assert all(s not in repr(error.value) for s in (SECRET, REFRESH, CLIENT_SECRET))


@pytest.mark.parametrize("body", [b"{}", b"[]", b"{", b'{"access_token":"x","access_token":"y"}',
                                  b"\xff", b"null", b"a" * 65537])
def test_malformed_oauth_response(config, body):
    with pytest.raises(credentials.CredentialRefused): validate(body, config)


@pytest.mark.parametrize("field", ["scope", "token_type", "expires_in", "access_token"])
def test_missing_token_fields(config, field):
    value = json.loads(token_body())
    del value[field]
    with pytest.raises(credentials.CredentialRefused): validate(canonical_json_bytes(value), config)


def test_no_authorization_acquisition_default(config, monkeypatch):
    called = []
    monkeypatch.setattr(http.server, "HTTPServer", lambda *a: called.append(a))
    with pytest.raises(credentials.CredentialRefused):
        credentials.DesktopPreparer(config).acquire(operator_confirmation="",
            present_url=lambda _: pytest.fail("no UI"), account_alias="engineering_account",
            clock_uncertainty_seconds=1, consent_seconds=10, exchange_timeout_seconds=10)
    assert not called


def test_fake_token_exchange_one_post_no_retry_or_refresh(config, monkeypatch):
    session = credentials.DesktopPreparer(config)
    verifier = session._verifier
    calls = []
    class Response:
        status = 200
        chunked = False
        def getheaders(self): return [("Content-Length", str(len(token_body()))), ("Content-Type", "application/json")]
        def read(self, size): return token_body()
        def isclosed(self): return True
    class Connection:
        def __init__(self, host, port, **kw): calls.append((host, port))
        def connect(self): calls.append("connect")
        def request(self, method, path, body, headers):
            assert method == "POST" and path == "/token" and "DPoP" not in headers
            values = parse_qs(body.decode())
            assert values["grant_type"] == ["authorization_code"] and values["code_verifier"] == [verifier]
            assert "scope" not in values and "refresh_token" not in values
            calls.append("request")
        def getresponse(self): return Response()
        def close(self): calls.append("close")
    monkeypatch.setattr(credentials.http.client, "HTTPSConnection", Connection)
    uri = "http://127.0.0.1:12345/"
    callback = uri + "?code=TEST_ONLY_code&state=" + session._state + "&iss=https%3A%2F%2Faccounts.google.com"
    token, metadata = session._exchange(callback, uri, account_alias="engineering_account",
        clock_uncertainty_seconds=1, timeout_seconds=10)
    assert type(token) is frozen.PreparedToken and metadata.public_config_sha256 == config.public_hash
    with pytest.raises(credentials.CredentialRefused):
        session._exchange(callback, uri, account_alias="engineering_account", clock_uncertainty_seconds=1, timeout_seconds=10)
    assert calls.count("request") == calls.count("connect") == 1
    assert session._verifier == session._state == ""


@pytest.mark.parametrize("query", ["code=x&state=wrong&iss=https%3A%2F%2Faccounts.google.com",
                                    "error=access_denied", "code=x&state=y&scope=drive",
                                    "code=x&code=y&state=z", "code=x", "code=&state=y"])
def test_callback_refusal_spends_session_no_connect(config, query):
    session = credentials.DesktopPreparer(config)
    uri = "http://127.0.0.1:12345/"
    with pytest.raises(credentials.CredentialRefused):
        session._exchange(uri + "?" + query, uri, account_alias="engineering_account", clock_uncertainty_seconds=1, timeout_seconds=10)
    assert session._used


@pytest.mark.parametrize("suffix", [
    "",  # Missing issuer fails closed under the observed Google callback contract.
    "&iss=http%3A%2F%2Faccounts.google.com",
    "&iss=https%3A%2F%2Faccounts.google.com%2F",
    "&iss=accounts.google.com",
    "&iss=https%3A%2F%2FAccounts.google.com",
    "&iss=https%3A%2F%2Faccounts.google.com%3Fx%3D1",
    "&iss=https%3A%2F%2Faccounts.google.com%23x",
    "&iss=https%3A%2F%2Faccounts.google.com&scope=drive",
    "&iss=https%3A%2F%2Faccounts.google.com&iss=https%3A%2F%2Faccounts.google.com",
])
def test_callback_issuer_refusal_before_network(config, monkeypatch, suffix):
    session = credentials.DesktopPreparer(config)
    monkeypatch.setattr(credentials.ssl, "create_default_context",
                        lambda **kw: pytest.fail("TLS context after invalid callback"))
    uri = "http://127.0.0.1:12345/"
    with pytest.raises(credentials.CredentialRefused):
        session._exchange(uri + "?code=TEST_ONLY_code&state=" + session._state + suffix, uri,
                          account_alias="engineering_account", clock_uncertainty_seconds=1,
                          timeout_seconds=10)
    assert session._used and session._state == session._verifier == ""


@pytest.mark.parametrize("issuer", ["https%3A%2F%2Faccounts.google.com",
                                      "https%3A%2F%2Faccounts.google.com%2F"])
def test_error_callback_with_issuer_refused_without_exchange(config, monkeypatch, issuer):
    session = credentials.DesktopPreparer(config)
    monkeypatch.setattr(credentials.ssl, "create_default_context",
                        lambda **kw: pytest.fail("TLS context after error callback"))
    uri = "http://127.0.0.1:12345/"
    with pytest.raises(credentials.CredentialRefused):
        session._exchange(uri + "?error=access_denied&state=" + session._state + "&iss=" + issuer,
                          uri, account_alias="engineering_account", clock_uncertainty_seconds=1,
                          timeout_seconds=10)
    assert session._used and session._state == session._verifier == ""


def test_trust_inventory_local_policy_and_allowlist():
    value = control.trust_inventory()
    assert value["verify_mode"] == "CERT_REQUIRED" and value["hostname_check"] is True
    assert value["minimum_tls"] >= int(ssl.TLSVersion.TLSv1_2)
    assert value["keylog"] == "disabled" and value["loaded_ca_count"] > 0
    assert value["authenticity"] == "not-established-offline"
    text = json.dumps(value)
    assert "certificate_DER" not in text and SECRET not in text


@pytest.mark.parametrize("name", sorted(p1.ENV_DENY | control.EXTRA_ENV_DENY | {"DYLD_NEW_INJECTION", "LD_NEW_INJECTION", "GIT_CONFIG_PARAMETERS"}))
@pytest.mark.parametrize("value", ["", SECRET])
def test_ambient_override_refused_before_ssl(monkeypatch, name, value):
    monkeypatch.setenv(name.lower(), value)
    monkeypatch.setattr(ssl, "create_default_context", lambda **kw: pytest.fail("SSL before environment gate"))
    with pytest.raises(frozen.QualificationError): control.trust_inventory()


def test_trust_material_changes_runtime_binding(configuration, monkeypatch):
    before = control.runtime_hash(configuration)
    inventory = control.trust_inventory()
    inventory["ca_file"]["sha256"] = "a" * 64
    monkeypatch.setattr(control, "trust_inventory", lambda: inventory)
    assert control.runtime_hash(configuration) != before


@pytest.mark.parametrize("field", ["dns_seconds", "tls_evidence_seconds", "evidence_fsync_seconds", "parser_seconds",
                                   "safety_seconds", "clock_uncertainty_seconds", "max_response_bytes", "max_cell_characters"])
def test_budget_and_bounds_are_runtime_bound(configuration, field):
    modified = replace(configuration, **{field: getattr(configuration, field) + 1})
    assert control.runtime_hash(modified) != control.runtime_hash(configuration)


def test_readiness_strict_total_safety_and_clock(configuration):
    assert configuration.attempt_seconds == 10
    for remaining in (12, 13):
        with pytest.raises(frozen.QualificationError):
            configuration.check_ready(expires_at=100 + remaining, clock_uncertainty_seconds=1, now=100)
    configuration.check_ready(expires_at=113.01, clock_uncertainty_seconds=1, now=100)


def test_valid_fake_issuance_unchanged_phase2_schema(local):
    authorization, receipt = issue(local)
    restored = control.parse_authorization(control.authorization_projection(authorization))
    assert authorization == restored and receipt["authorization_hash"] == p2.authorization_hash(authorization)
    assert authorization.runtime_pin_sha256 == read.runtime_hash(local["configuration"].read_configuration())
    report = control.preflight(**local, now=time.time(), authorization=authorization, receipt=receipt, _test_only=True)
    assert report["status"] == "PASS" and report["network"] == "not-performed"


@pytest.mark.parametrize("change", [
    {"capability": "CLEAN_MUTATION_GO"}, {"capability": ""}, {"purpose": "paper"},
    {"engineering_only": False}, {"fixture_hash": "0" * 64}, {"phase3_runtime_hash": "0" * 64},
    {"phase3_source_hash": "0" * 64}, {"operator_confirmation": ""},
    {"expires_at": 0}, {"expires_at": float("inf")}, {"expires_at": time.time() + 3600},
    {"issued_at": time.time() + 1000}, {"issued_at": 1},
])
def test_bad_issuance_refused_no_network(local, change):
    with pytest.raises(frozen.QualificationError): issue(local, **change)


def test_issue_template_or_missing_conditions_refused(local):
    with pytest.raises(frozen.QualificationError): issue(local, descriptor={})
    with pytest.raises(frozen.QualificationError): issue(local, conditions=control.LocalConditions(False, True, True, True, True))


def test_preflight_pass_no_mutation_or_acquisition(local, monkeypatch):
    monkeypatch.setattr(credentials.DesktopPreparer, "acquire", lambda *a, **kw: pytest.fail("acquisition in preflight"))
    monkeypatch.setattr(control, "issue_authorization", lambda **kw: pytest.fail("issuance in preflight"))
    monkeypatch.setattr(p2.LocalRegistry, "__init__", lambda *a: pytest.fail("preflight writes registry"))
    report = control.preflight(**local, now=time.time(), _test_only=True)
    assert report["status"] == "PASS" and report["reasons"] == []
    assert report["credential_metadata_supplied"] is False


def test_preflight_deterministic_blocked_reasons(local):
    bad = {**local, "descriptor": {}, "expected_head": "b" * 40, "expected_pin": {},
        "conditions": control.LocalConditions(False, True, True, True, True)}
    report = control.preflight(**bad, now=time.time(), _test_only=True)
    assert report["status"] == "BLOCKED"
    assert report["reasons"] == ["repository", "conditions", "runtime_pin", "fixture_provenance"]


def test_no_registry_creation_on_preflight(tmp_path, local):
    configuration = replace(local["configuration"], registry_root=str(tmp_path / "absent"))
    report = control.preflight(**{**local, "configuration": configuration,
        "expected_pin": control.runtime_projection(configuration)}, now=time.time(), _test_only=True)
    assert report["reasons"] == ["reservation_or_spent"]
    assert not Path(configuration.registry_root).exists()


def test_real_repository_check_blocks_uncommitted_slice():
    with pytest.raises(frozen.QualificationError): control.repository_check(control.PHASE2_COMMIT)


def test_preflight_token_metadata_readiness_binding(local, config):
    _, metadata = validate(token_body(), config)
    report = control.preflight(**local, now=time.time(), credential_metadata=metadata, _test_only=True)
    assert report["status"] == "PASS"
    for changed in (replace(metadata, account_alias="other"), replace(metadata, clock_uncertainty_seconds=2),
                    replace(metadata, expires_at=time.time() + 5)):
        report = control.preflight(**local, now=time.time(), credential_metadata=changed, _test_only=True)
        assert report["reasons"] == ["credential_readiness"]


@pytest.mark.parametrize("change", [{"phase3_source_hash": "0" * 64}, {"phase3_runtime_hash": "0" * 64},
                                   {"authorization_hash": "0" * 64}, {"extra": SECRET}])
def test_receipt_tampering_refused(local, change):
    authorization, receipt = issue(local)
    report = control.preflight(**local, now=time.time(), authorization=authorization,
        receipt={**receipt, **change}, _test_only=True)
    assert report["reasons"] == ["authorization_binding"]


def fake_operational_seams(monkeypatch):
    parser = control.parse_fixture_descriptor
    monkeypatch.setattr(control, "parse_fixture_descriptor", lambda value, **kw: parser(value, _test_only=True))
    precheck = read._precheck
    monkeypatch.setattr(read, "_precheck", lambda *a, **kw: precheck(*a, **{**kw, "offline": True}))
    monkeypatch.setattr(read.ssl, "SSLSocket", FakeTLS)


@pytest.mark.parametrize("fault,expected", [(None, read.Outcome.ZERO), ("connect", read.Outcome.TRANSPORT),
    ("send", read.Outcome.TRANSPORT), ("status", read.Outcome.TRANSPORT),
    ("body", read.Outcome.TRANSPORT), ("truncated", read.Outcome.MALFORMED), ("construct", read.Outcome.CONSTRUCTION)])
def test_wrapper_one_frozen_attempt_spent_failure_no_refresh(local, config, record, monkeypatch, fault, expected):
    authorization, receipt = issue(local)
    token, metadata = validate(token_body(), config)
    fake_operational_seams(monkeypatch)
    wire = Wire(canonical_json_bytes(payload(record.fixture())), fault=fault)
    monkeypatch.setattr(read, "_construct", wire.construct)
    monkeypatch.setattr(credentials.DesktopPreparer, "acquire", lambda *a, **kw: pytest.fail("acquire from wrapper"))
    monkeypatch.setattr(control, "issue_authorization", lambda **kw: pytest.fail("issue from wrapper"))
    calls = []
    def supervise(fixture, configuration, token, provenance, authorization, root, deadline):
        calls.append("attempt")
        assert type(token) is frozen.PreparedToken and not hasattr(provenance, "refresh")
        with p2.LocalRegistry(root) as registry:
            return read._read_once(registry, fixture, configuration, token, provenance, authorization, deadline, offline=True)
    monkeypatch.setattr(read, "_supervise", supervise)
    result = operator.execute_read(**local, execute_live_read=True, token=token, metadata=metadata,
        authorization=authorization, receipt=receipt)
    assert result["summary"]["outcome"] == expected.value and result["next_action"] == "stop-no-retry"
    assert len(calls) == wire.constructs == 1
    assert wire.connects <= 1 and wire.responses <= 1 and len(wire.chunks) <= 1
    recovery = control.inspect_recovery(configuration=local["configuration"], descriptor=local["descriptor"],
        authorization=authorization, _test_only=True)
    assert recovery["authorization_state"] == "SPENT" and recovery["evidence"] == "terminal-recorded"
    with pytest.raises(frozen.QualificationError):
        operator.execute_read(**local, execute_live_read=True, token=token, metadata=metadata,
            authorization=authorization, receipt=receipt)
    assert len(calls) == 1
    files = [p for p in Path(local["configuration"].registry_root).iterdir() if p.is_file()]
    evidence = "".join(p.read_text() for p in files) + json.dumps(result)
    assert all(secret not in evidence for secret in (SECRET, REFRESH, CLIENT_SECRET))


@pytest.mark.parametrize("attack", ["no-flag", "no-auth", "no-receipt", "credential-object", "wrong-expiry", "unready", "scope-capability"])
def test_wrapper_denied_before_adapter(local, config, monkeypatch, attack):
    authorization, receipt = issue(local)
    token, metadata = validate(token_body(), config)
    values = dict(**local, execute_live_read=True, token=token, metadata=metadata, authorization=authorization, receipt=receipt)
    fake_operational_seams(monkeypatch)
    monkeypatch.setattr(read.ReadAdapter, "inspect", lambda *a, **kw: pytest.fail("adapter called before gates"))
    if attack == "no-flag": values["execute_live_read"] = False
    if attack == "no-auth": values["authorization"] = None
    if attack == "no-receipt": values["receipt"] = None
    if attack == "credential-object": values["token"] = object()
    if attack == "wrong-expiry": values["token"] = replace(token, expires_at=token.expires_at - 1)
    if attack == "unready":
        metadata = replace(metadata, expires_at=time.time() + 5)
        values.update(metadata=metadata, token=replace(token, expires_at=metadata.expires_at))
    if attack == "scope-capability": values["authorization"] = replace(authorization, capability=p1.Capability.CLEAN_MUTATION_GO)
    with pytest.raises(frozen.QualificationError): operator.execute_read(**values)


def test_recovery_never_repairs_incomplete_claim(local):
    authorization, _ = issue(local)
    root = Path(local["configuration"].registry_root)
    path = root / f"claim-{authorization.authorization_id}.json"
    path.touch(mode=0o600)
    report = control.inspect_recovery(configuration=local["configuration"], descriptor=local["descriptor"],
        authorization=authorization, _test_only=True)
    assert report["authorization_state"] == "UNUSABLE" and path.read_bytes() == b""
    with pytest.raises(frozen.QualificationError): issue(local)


def test_pipe_literal_only_and_no_disk(config):
    _, metadata = validate(token_body(), config)
    read_fd, write_fd = os.pipe()
    os.write(write_fd, SECRET.encode())
    os.close(write_fd)
    token = operator._token_from_pipe(read_fd, metadata)
    assert type(token) is frozen.PreparedToken and token.value == SECRET


def test_cli_preflight_refuses_missing_private_files_no_network(tmp_path, capsys):
    result = operator.main(["preflight", "--fixture", str(tmp_path / "missing"),
        "--configuration", str(tmp_path / "missing"), "--pin", str(tmp_path / "missing"),
        "--conditions", str(tmp_path / "missing"), "--expected-head", "a" * 40])
    assert result == 2 and json.loads(capsys.readouterr().out)["status"] == "BLOCKED"


def test_dry_procedure_has_no_action_and_keeps_stripe(capsys):
    assert operator.main(["procedure"]) == 0
    text = capsys.readouterr().out
    assert "Stripe TEST MODE" in text and "Stop." in text and "never retry" in text


def test_exclusive_artifact_pair_no_overwrite(tmp_path):
    path = tmp_path / "artifact.json"
    control.write_json(path, {"schema": "TEST_ONLY"})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError): control.write_json(path, {})
    assert control.load_json(path) == {"schema": "TEST_ONLY"}


@pytest.mark.parametrize("fault", ["connect", "request", "response", "status", "length", "duplicate-length",
                                   "chunked", "encoding", "type", "body", "parse"])
def test_oauth_exchange_failure_one_attempt_secret_safe(config, monkeypatch, fault):
    session = credentials.DesktopPreparer(config)
    uri = "http://127.0.0.1:12345/"
    callback = uri + "?code=TEST_ONLY_code&state=" + session._state + "&iss=https%3A%2F%2Faccounts.google.com"
    calls = []
    class Response:
        status = 401 if fault == "status" else 200
        chunked = fault == "chunked"
        def getheaders(self):
            headers = [("Content-Length", "99999" if fault == "length" else str(len(token_body()))),
                       ("Content-Type", "text/html" if fault == "type" else "application/json")]
            if fault == "duplicate-length": headers += [("content-length", "20")]
            if fault == "encoding": headers += [("Content-Encoding", "gzip")]
            return headers
        def read(self, count):
            if fault == "body": raise OSError(SECRET)
            return b"x" * len(token_body()) if fault == "parse" else token_body()
        def isclosed(self): return True
    class Connection:
        def __init__(self, *a, **kw): calls.append("construct")
        def connect(self):
            calls.append("connect")
            if fault == "connect": raise OSError(SECRET)
        def request(self, *a, **kw):
            calls.append("request")
            if fault == "request": raise OSError(SECRET)
        def getresponse(self):
            calls.append("response")
            if fault == "response": raise OSError(REFRESH)
            return Response()
        def close(self): calls.append("close")
    monkeypatch.setattr(credentials.http.client, "HTTPSConnection", Connection)
    with pytest.raises(credentials.CredentialRefused) as error:
        session._exchange(callback, uri, account_alias="engineering_account", clock_uncertainty_seconds=1, timeout_seconds=10)
    assert error.value.__context__ is None and error.value.args == ()
    assert session._used and session._verifier == session._state == ""
    with pytest.raises(credentials.CredentialRefused):
        session._exchange(callback, uri, account_alias="engineering_account", clock_uncertainty_seconds=1, timeout_seconds=10)
    assert calls.count("construct") == calls.count("close") == 1 and calls.count("request") <= 1


def test_fake_loopback_manual_consent_acquisition_no_browser(config, monkeypatch, capsys):
    session = credentials.DesktopPreparer(config)
    token, metadata = validate(token_body(), config)
    callback_paths = []
    class Server:
        server_port = 12345
        def __init__(self, address, handler):
            assert address == ("127.0.0.1", 0)
            self.handler = handler
        def handle_request(self):
            handler = object.__new__(self.handler)
            handler.path = callback_paths[0]
            handler.send_response = lambda code: None
            handler.send_header = lambda *a: None
            handler.end_headers = lambda: None
            handler.do_GET()
        def server_close(self): callback_paths.append("closed")
    def present(url):
        args = parse_qs(urlsplit(url).query)
        callback_paths.append("/?code=TEST_ONLY_code&state=" + args["state"][0]
                              + "&iss=https%3A%2F%2Faccounts.google.com")
    def exchange_once(callback, redirect, **kw):
        assert callback == redirect[:-1] + callback_paths[0]
        return token, metadata
    monkeypatch.setattr(http.server, "HTTPServer", Server)
    monkeypatch.setattr(session.__class__, "_exchange_once", lambda self, *a, **kw: exchange_once(*a, **kw))
    result = session.acquire(operator_confirmation=credentials.ACQUISITION_CONFIRMATION,
        present_url=present, account_alias="engineering_account", clock_uncertainty_seconds=1,
        consent_seconds=10, exchange_timeout_seconds=10)
    assert result == (token, metadata) and callback_paths[-1] == "closed"
    assert session._used and session._state == session._verifier == ""
    assert capsys.readouterr().out == ""


def test_oauth_ambient_adc_presence_rejected_no_listener(config, monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", SECRET)
    monkeypatch.setattr(http.server, "HTTPServer", lambda *a: pytest.fail("ambient ADC launch"))
    with pytest.raises(credentials.CredentialRefused):
        credentials.DesktopPreparer(config).acquire(operator_confirmation=credentials.ACQUISITION_CONFIRMATION,
            present_url=lambda _: pytest.fail("browser"), account_alias="engineering_account",
            clock_uncertainty_seconds=1, consent_seconds=10, exchange_timeout_seconds=10)


def test_hostile_credential_object_never_inspected(local, monkeypatch):
    class Hostile:
        def __repr__(self): pytest.fail("credential repr")
        def refresh(self, *a): pytest.fail("refresh")
        def __str__(self): pytest.fail("credential str")
    with pytest.raises(frozen.QualificationError):
        operator.execute_read(**local, execute_live_read=True, token=Hostile(), metadata=Hostile(),
            authorization=None, receipt=None)


def test_wrapper_arbitrary_failure_never_exports_exception(local, config, monkeypatch):
    authorization, receipt = issue(local)
    token, metadata = validate(token_body(), config)
    fake_operational_seams(monkeypatch)
    def fail(*a, **kw): raise RuntimeError(SECRET)
    monkeypatch.setattr(read.ReadAdapter, "inspect", fail)
    with pytest.raises(frozen.QualificationError) as error:
        operator.execute_read(**local, execute_live_read=True, token=token, metadata=metadata,
            authorization=authorization, receipt=receipt)
    assert SECRET not in str(error.value) and error.value.__context__ is None


def test_current_trust_capture_is_nonoperational_and_matches_local_policy():
    value = json.loads((frozen.SHEETS_DOCS / "SHEETS_PHASE3_TRUST_INVENTORY_DRAFT.json").read_text())
    assert value["operational_pin"] is False and value["live_go"] == "CLOSED"
    assert value["inventory"]["ca_file"]["sha256"] == control.trust_inventory()["ca_file"]["sha256"]


def test_recovery_invalid_evidence_is_unusable_not_zero(local):
    authorization, _ = issue(local)
    root = Path(local["configuration"].registry_root)
    path = root / f"attempt-{authorization.authorization_id}.jsonl"
    path.touch(mode=0o600)
    path.write_bytes(b'{"secret-bearing-arbitrary-event":"never-export"}')
    report = control.inspect_recovery(configuration=local["configuration"], descriptor=local["descriptor"],
        authorization=authorization, _test_only=True)
    assert report["authorization_state"] == "UNUSABLE"
    assert "never-export" not in json.dumps(report)


def test_no_baseline_contamination_cleanup(local, record, config, monkeypatch):
    authorization, receipt = issue(local)
    token, metadata = validate(token_body(), config)
    fake_operational_seams(monkeypatch)
    wire = Wire(canonical_json_bytes(payload(record.fixture(), [("unrelated-data", None, None)])))
    monkeypatch.setattr(read, "_construct", wire.construct)
    def supervise(fixture, configuration, token, provenance, authorization, root, deadline):
        with p2.LocalRegistry(root) as registry:
            return read._read_once(registry, fixture, configuration, token, provenance, authorization, deadline, offline=True)
    monkeypatch.setattr(read, "_supervise", supervise)
    result = operator.execute_read(**local, execute_live_read=True, token=token, metadata=metadata,
        authorization=authorization, receipt=receipt)
    assert result["summary"]["outcome"] == read.Outcome.ZERO.value
    assert result["summary"]["nonempty_rows"] == 1 and result["baseline"] == "unqualified-or-contaminated-retire-or-review"
    assert len(wire.chunks) == 1 and wire.chunks[0].startswith(b"GET ")


def test_trust_store_file_digest_rejects_unsafe_material(tmp_path):
    path = tmp_path / "ca.pem"
    path.write_bytes(b"TEST_ONLY_ca_public_material")
    before = control._trust_file(path)
    path.write_bytes(b"TEST_ONLY_ca_changed_material")
    assert control._trust_file(path)["sha256"] != before["sha256"]
    path.chmod(0o666)
    with pytest.raises(frozen.QualificationError): control._trust_file(path)


def test_repository_check_disables_external_helpers(monkeypatch):
    calls = []
    class Result:
        returncode = 0
        stdout = b""
    def run(command, **kw):
        calls.append(command)
        assert command[:7] == ["/usr/bin/git", "-c", "core.fsmonitor=false", "-c",
                              "core.untrackedCache=false", "-c", "submodule.recurse=false"]
        result = Result()
        if command[7:] == ["rev-parse", "HEAD"]: result.stdout = ("a" * 40 + "\n").encode()
        if command[7:] == ["rev-parse", "--show-toplevel"]: result.stdout = (str(frozen.ROOT) + "\n").encode()
        if command[7] == "status": assert "--ignore-submodules=all" in command
        return result
    monkeypatch.setattr(control.subprocess, "run", run)
    control.repository_check("a" * 40)
    assert len(calls) == 4
