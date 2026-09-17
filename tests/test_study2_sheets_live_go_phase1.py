"""Frozen offline Phase 1 qualification: synthetic assertions, no credential I/O."""
from dataclasses import replace, FrozenInstanceError
import http.client
import json
import socket
import ssl
import time

import pytest

from retry_semantics.study2 import sheets_live_go_phase1 as phase
from retry_semantics.study2 import sheets_live_preparation as frozen

SECRET = "ya29.synthetic-phase1-sensitive-material"


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("offline socket/DNS/network disabled")
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname"):
        monkeypatch.setattr(socket, name, denied)
    # The ordinary constructor must not call connect either.
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", denied)


@pytest.fixture
def fixture():
    return frozen.Fixture("offline_fixture", 7, "RetrySemanticsEngineering", 100, 3, "phase1")


@pytest.fixture
def authorization(fixture):
    # A test-only assertion for a synthetic fixture, never saved or live-bound.
    return phase.LiveAuthorization(phase.Capability.LIVE_READ_GO, fixture.manifest_hash,
        phase.pin_hash(), phase.source_hash(), "synthetic_authorization", "synthetic_operator",
        time.time() - 10, time.time() + 1000, phase.CONFIRMATION)


@pytest.fixture
def clean_environment(monkeypatch):
    # Replaces only this process's mapping; never edits shell or user config.
    monkeypatch.setattr(phase.os, "environ", {})


@pytest.fixture
def provenance():
    return phase.CredentialProvenance("synthetic_account", "a" * 64, "1.2.3",
                                     100, 102, 1000, 2)


def construct(fixture, authorization=None, capability=phase.Capability.LIVE_READ_GO):
    return phase.ConnectorFactory().construct(capability=capability, fixture=fixture,
                                              timeout=5, authorization=authorization)


def test_export_only_immutable_material(provenance):
    token = phase.export_prepared_token(SECRET, provenance)
    assert type(token) is frozen.PreparedToken and token.expires_at == 1000
    assert SECRET not in repr(token)
    assert not hasattr(token, "refresh") and not hasattr(token, "before_request")
    with pytest.raises((FrozenInstanceError, TypeError)):
        token.refresh = lambda: pytest.fail("forbidden refresh")


def test_hostile_credential_never_inspected(provenance):
    class Hostile:
        def refresh(self, *args): pytest.fail("no refresh")
        def before_request(self, *args): pytest.fail("no callback")
        def __repr__(self): pytest.fail("no repr")
        def __str__(self): pytest.fail("no str")
    with pytest.raises(frozen.QualificationError):
        phase.export_prepared_token(Hostile(), provenance)
    with pytest.raises(frozen.QualificationError):
        phase.export_prepared_token(SECRET, Hostile())


@pytest.mark.parametrize("change", [
    {"account_alias": SECRET}, {"public_config_sha256": SECRET},
    {"library_version": SECRET}, {"granted_scopes": ("https://www.googleapis.com/auth/drive",)},
    {"requested_scopes": ()}, {"mechanism": "adc"}, {"expires_at": 100},
    {"prepared_at": 99}, {"clock_uncertainty_seconds": float("nan")},
])
def test_provenance_refuses_unqualified_fields(provenance, change):
    with pytest.raises(frozen.QualificationError): replace(provenance, **change)


def test_provenance_evidence_excludes_secrets_and_unknown_inputs(provenance):
    token = phase.export_prepared_token(SECRET, provenance)
    safe = provenance.evidence()
    assert SECRET not in json.dumps(safe) and "Bearer" not in json.dumps(safe)
    assert not any(type(v) is frozen.PreparedToken for v in safe.values())
    with pytest.raises(TypeError): phase.CredentialProvenance(token=token)
    with pytest.raises(TypeError): provenance.evidence(credentials=object())


@pytest.fixture
def budget():
    # Arithmetic-only fixtures, not selected production deadlines.
    return phase.ActionBudget(1, 2, 3, 4, 5, 6, 7, 8)


@pytest.mark.parametrize("remaining,ready", [(39, True), (38, False), (37, False), (0, False)])
def test_readiness_strict_sum_plus_uncertainty(budget, remaining, ready):
    assert budget.total_seconds == 36
    token = frozen.prepare_token(SECRET, expires_at=100 + remaining, clock_uncertainty_seconds=2)
    if ready: budget.check_ready(token, now=100)
    else:
        with pytest.raises(frozen.QualificationError): budget.check_ready(token, now=100)


@pytest.mark.parametrize("name", list(phase.ActionBudget.__dataclass_fields__))
@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan"), True])
def test_budget_requires_all_finite_positive_deadlines(budget, name, bad):
    with pytest.raises(frozen.QualificationError): replace(budget, **{name: bad})


def test_insufficient_token_aborts_before_factory(budget, fixture, authorization, monkeypatch):
    monkeypatch.setattr(phase.ConnectorFactory, "construct", lambda **kw: pytest.fail("no construction"))
    token = frozen.prepare_token(SECRET, expires_at=120, clock_uncertainty_seconds=2)
    with pytest.raises(frozen.QualificationError):
        budget.check_ready(token, now=100)
        construct(fixture, authorization)


def test_default_deny_before_ssl_or_connection(fixture, monkeypatch):
    monkeypatch.setattr(phase.ssl, "create_default_context", lambda **kw: pytest.fail("no SSL setup"))
    with pytest.raises(frozen.QualificationError): construct(fixture)


@pytest.mark.parametrize("allowed", list(phase.Capability))
@pytest.mark.parametrize("requested", list(phase.Capability))
def test_capabilities_have_no_implicit_escalation(fixture, authorization, clean_environment,
                                               allowed, requested):
    auth = replace(authorization, capability=allowed)
    if allowed is requested:
        connection, evidence = construct(fixture, auth, requested)
        assert evidence.capability is requested and connection.sock is None
        connection.close()
    else:
        with pytest.raises(frozen.QualificationError): construct(fixture, auth, requested)


@pytest.mark.parametrize("change", [
    {"fixture_manifest_sha256": "b" * 64}, {"runtime_pin_sha256": "b" * 64},
    {"connector_source_sha256": "b" * 64}, {"expires_at": time.time() - 1},
    {"authorized_at": time.time() + 100},
])
def test_hash_and_time_mismatch_preconstruction(fixture, authorization, monkeypatch, change):
    monkeypatch.setattr(phase.ssl, "create_default_context", lambda **kw: pytest.fail("no SSL setup"))
    with pytest.raises(frozen.QualificationError): construct(fixture, replace(authorization, **change))


@pytest.mark.parametrize("change", [{"operator_confirmation": "yes"}, {"engineering_only": False},
    {"gate_version": "other"}, {"purpose": "paper"}, {"capability": "LIVE_READ_GO"},
    {"operator_alias": SECRET}, {"fixture_manifest_sha256": "bad"}])
def test_authorization_shape_is_explicit(authorization, change):
    with pytest.raises(frozen.QualificationError): replace(authorization, **change)


def test_authorization_expiry_equality(fixture, authorization):
    with pytest.raises(frozen.QualificationError):
        phase.validate_authorization(authorization, authorization.capability, fixture,
                                     now=authorization.expires_at)


@pytest.mark.parametrize("name", sorted(phase.ENV_DENY))
@pytest.mark.parametrize("value", ["", SECRET])
def test_environment_gate_rejects_presence_without_values(name, value):
    with pytest.raises(frozen.QualificationError) as error:
        phase.environment_gate({name.lower(): value})
    assert SECRET not in str(error.value)


def test_environment_values_never_inspected():
    class Hostile:
        def __str__(self): pytest.fail("no str")
        def __repr__(self): pytest.fail("no repr")
        def __bool__(self): pytest.fail("no value test")
    assert phase.environment_gate({"PATH": Hostile()}).startswith("PASS")
    with pytest.raises(frozen.QualificationError): phase.environment_gate({"HTTPS_PROXY": Hostile()})


def test_environment_failure_pre_ssl(fixture, authorization, monkeypatch):
    monkeypatch.setattr(phase.os, "environ", {"SSLKEYLOGFILE": SECRET})
    monkeypatch.setattr(phase.ssl, "create_default_context", lambda **kw: pytest.fail("no SSL setup"))
    with pytest.raises(frozen.QualificationError): construct(fixture, authorization)


def test_real_stdlib_construction_without_socket(fixture, authorization, clean_environment):
    factory = phase.ConnectorFactory()
    connection, evidence = factory.construct(capability=authorization.capability,
        fixture=fixture, timeout=5, authorization=authorization)
    assert type(connection) is http.client.HTTPSConnection
    assert (connection.host, connection.port, connection.timeout) == (frozen.HOST, 443, 5)
    assert connection.sock is None and connection.auto_open == connection.debuglevel == 0
    phase.validate_context(connection._context)
    assert evidence.evidence()["hostname_check"] is True
    with pytest.raises(AssertionError): connection.connect()
    with pytest.raises(frozen.QualificationError):
        factory.construct(capability=authorization.capability, fixture=fixture,
                          timeout=5, authorization=authorization)
    connection.close()


@pytest.mark.parametrize("attack", ["hostname", "certificate", "keylog", "object", "no_ca", "tls_minimum"])
def test_malformed_context_fail_closed(fixture, authorization, clean_environment, monkeypatch, tmp_path, attack):
    context = ssl.create_default_context()
    if attack == "hostname": context.check_hostname = False
    elif attack == "certificate":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif attack == "keylog":
        context.keylog_filename = str(tmp_path / "empty-test-keylog")
    elif attack == "no_ca": context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    elif attack == "tls_minimum": context.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
    else: context = object()
    monkeypatch.setattr(phase.ssl, "create_default_context", lambda **kw: context)
    monkeypatch.setattr(phase.http.client, "HTTPSConnection", lambda *a, **kw: pytest.fail("no connection"))
    with pytest.raises(frozen.QualificationError): construct(fixture, authorization)


def test_constructor_error_no_secret_exception_evidence(fixture, authorization, clean_environment, monkeypatch):
    def fail(*args, **kwargs): raise RuntimeError(SECRET)
    monkeypatch.setattr(phase.http.client, "HTTPSConnection", fail)
    with pytest.raises(frozen.QualificationError) as error: construct(fixture, authorization)
    assert SECRET not in str(error.value) and error.value.__suppress_context__


def test_safe_connector_evidence_allowlist(fixture, authorization, clean_environment):
    connection, evidence = construct(fixture, authorization)
    safe = evidence.evidence()
    assert len(safe) == 22
    assert not set(safe) & {"token", "Authorization", "credentials", "exception", "environment"}
    assert SECRET not in json.dumps(safe)
    with pytest.raises(TypeError): evidence.evidence(token=SECRET)
    with pytest.raises(frozen.QualificationError): replace(evidence, runtime_sha256=SECRET)
    with pytest.raises(frozen.QualificationError): replace(evidence, authorization_id=SECRET)
    connection.close()


def test_runtime_drift_pre_ssl(fixture, authorization, monkeypatch):
    def drift(): raise frozen.QualificationError()
    monkeypatch.setattr(frozen, "check_runtime", drift)
    monkeypatch.setattr(phase.ssl, "create_default_context", lambda **kw: pytest.fail("no SSL setup"))
    with pytest.raises(frozen.QualificationError): construct(fixture, authorization)


@pytest.fixture
def construction_calls(monkeypatch):
    """Observe real offline SSL/connection construction, never connect/send."""
    calls = []
    real_ssl = phase.ssl.create_default_context
    real_https_init = phase.http.client.HTTPSConnection.__init__

    def ssl_constructor(*args, **kwargs):
        calls.append("ssl")
        return real_ssl(*args, **kwargs)

    def https_constructor(connection, *args, **kwargs):
        calls.append("https")
        return real_https_init(connection, *args, **kwargs)

    monkeypatch.setattr(phase.ssl, "create_default_context", ssl_constructor)
    monkeypatch.setattr(phase.http.client.HTTPSConnection, "__init__", https_constructor)
    return calls


def test_authorization_precheck_does_not_construct_or_consume(
        fixture, authorization, clean_environment, construction_calls):
    factory = phase.ConnectorFactory()
    with pytest.raises(frozen.QualificationError):
        factory.construct(capability=authorization.capability, fixture=fixture, timeout=5)
    assert construction_calls == []
    connection, _ = factory.construct(capability=authorization.capability,
        fixture=fixture, timeout=5, authorization=authorization)
    try:
        assert construction_calls == ["ssl", "https"] and connection.sock is None
    finally:
        connection.close()


def test_environment_precheck_does_not_construct_or_consume(
        fixture, authorization, clean_environment, construction_calls, monkeypatch):
    factory = phase.ConnectorFactory()
    monkeypatch.setattr(phase.os, "environ", {"HTTPS_PROXY": SECRET})
    with pytest.raises(frozen.QualificationError):
        factory.construct(capability=authorization.capability, fixture=fixture,
                          timeout=5, authorization=authorization)
    assert construction_calls == []
    monkeypatch.setattr(phase.os, "environ", {})
    connection, _ = factory.construct(capability=authorization.capability,
        fixture=fixture, timeout=5, authorization=authorization)
    try:
        assert construction_calls == ["ssl", "https"] and connection.sock is None
    finally:
        connection.close()


@pytest.mark.parametrize("boundary", ["ssl", "https"])
def test_construction_failure_after_prechecks_consumes_factory(
        fixture, authorization, clean_environment, construction_calls, monkeypatch, boundary):
    factory = phase.ConnectorFactory()

    def fail(*args, **kwargs):
        construction_calls.append(boundary)
        raise RuntimeError(SECRET)

    if boundary == "ssl": monkeypatch.setattr(phase.ssl, "create_default_context", fail)
    else: monkeypatch.setattr(phase.http.client.HTTPSConnection, "__init__", fail)
    expected = ["ssl"] if boundary == "ssl" else ["ssl", "https"]
    with pytest.raises(frozen.QualificationError):
        factory.construct(capability=authorization.capability, fixture=fixture,
                          timeout=5, authorization=authorization)
    assert construction_calls == expected
    with pytest.raises(frozen.QualificationError):
        factory.construct(capability=authorization.capability, fixture=fixture,
                          timeout=5, authorization=authorization)
    assert construction_calls == expected  # Refuses a second actual attempt.


def test_successful_construction_consumes_factory(
        fixture, authorization, clean_environment, construction_calls):
    factory = phase.ConnectorFactory()
    connection, _ = factory.construct(capability=authorization.capability,
        fixture=fixture, timeout=5, authorization=authorization)
    try:
        assert construction_calls == ["ssl", "https"] and connection.sock is None
        with pytest.raises(frozen.QualificationError):
            factory.construct(capability=authorization.capability, fixture=fixture,
                              timeout=5, authorization=authorization)
        assert construction_calls == ["ssl", "https"]
    finally:
        connection.close()
