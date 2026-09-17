"""Frozen offline Google Sheets LIVE-GO Phase 1 prerequisites.

No connected live runner or credential acquisition implementation. The returned
raw HTTPSConnection is a trusted implementation object, NOT capability-safe at
the wire boundary.

Authorization records are operator assertions, not cryptographic permissions or a
Python security sandbox. Production construction is denied without such a record.
The frozen socket seam remains unchanged and has no new default connector.
"""
from dataclasses import dataclass
from enum import Enum
import http.client
import os
from pathlib import Path
import re
import ssl
import threading
import time

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_live_preparation as frozen

SCOPE = "https://www.googleapis.com/auth/drive.file"
MECHANISM = "oauth-user-desktop-pkce-v1"
PURPOSE = "sheets-engineering-qualification"
CONFIRMATION = "EXPLICIT_OPERATOR_ENGINEERING_AUTHORIZATION"
# Reject even empty settings: a clean launch must explain/remove interference.
ENV_DENY = frozenset({
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "FTP_PROXY",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "SSLKEYLOGFILE", "OPENSSL_CONF", "OPENSSL_MODULES", "OPENSSL_ENGINES",
    "PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    "GRPC_DEFAULT_SSL_ROOTS_FILE_PATH", "NODE_EXTRA_CA_CERTS",
})


def _hash(value):
    frozen._require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value))


def environment_gate(environment):
    """Inspect names only; never retain/hash/stringify environment values."""
    frozen._require(all(type(name) is str for name in environment))
    frozen._require(not any(name.upper() in ENV_DENY for name in environment))
    return "PASS_OFFLINE_ENVIRONMENT_POLICY_V1"


@dataclass(frozen=True, slots=True)
class CredentialProvenance:
    """Explicit nonsecret metadata only; no raw response/config/credential input.

    Account alias is a separately assigned registry label, not a token-derived
    identity. Config hash covers only a reviewed public config projection.
    Times are local exchange bounds, not a claimed issuer iat.
    """
    account_alias: str
    public_config_sha256: str
    library_version: str
    exchange_started_at: float
    prepared_at: float
    expires_at: float
    clock_uncertainty_seconds: float
    requested_scopes: tuple[str, ...] = (SCOPE,)
    granted_scopes: tuple[str, ...] = (SCOPE,)
    mechanism: str = MECHANISM

    def __post_init__(self):
        frozen._safe_label(self.account_alias)
        _hash(self.public_config_sha256)
        frozen._require(type(self.library_version) is str and
                        re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", self.library_version))
        for value in (self.exchange_started_at, self.prepared_at, self.expires_at):
            frozen._number(value, positive=True)
        frozen._number(self.clock_uncertainty_seconds)
        frozen._require(self.exchange_started_at <= self.prepared_at < self.expires_at
                        and self.requested_scopes == self.granted_scopes == (SCOPE,)
                        and self.mechanism == MECHANISM)

    def evidence(self):
        return {"mechanism": MECHANISM, "requested_scopes": [SCOPE],
                "granted_scopes": [SCOPE], "account_alias": self.account_alias,
                "public_config_sha256": self.public_config_sha256,
                "acquisition_library": "google-auth-oauthlib",
                "library_version": self.library_version,
                "exchange_started_at": self.exchange_started_at,
                "prepared_at": self.prepared_at, "expires_at": self.expires_at,
                "expiry_basis": "exchange-start-plus-expires-in",
                "clock_uncertainty_seconds": self.clock_uncertainty_seconds}


def export_prepared_token(value, provenance):
    """Export literal material only. Does not acquire, inspect, or refresh auth."""
    frozen._require(type(provenance) is CredentialProvenance)
    return frozen.prepare_token(value, expires_at=provenance.expires_at,
                                clock_uncertainty_seconds=provenance.clock_uncertainty_seconds)


@dataclass(frozen=True, slots=True)
class ActionBudget:
    """Selected hard deadlines, not illustrative per-socket timeout estimates."""
    dns_seconds: float
    tcp_seconds: float
    tls_seconds: float
    send_seconds: float
    status_seconds: float
    body_seconds: float
    verifier_seconds: float
    safety_seconds: float

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            frozen._number(getattr(self, name), positive=True)
        frozen._number(self.total_seconds, positive=True)

    @property
    def total_seconds(self):
        return sum(getattr(self, name) for name in self.__dataclass_fields__)

    def check_ready(self, token, *, now):
        frozen._require(type(token) is frozen.PreparedToken)
        token.check_ready(now=now, dispatch_budget_seconds=self.total_seconds)


class Capability(Enum):
    LIVE_READ_GO = "LIVE_READ_GO"
    CLEAN_MUTATION_GO = "CLEAN_MUTATION_GO"
    AMBIGUITY_ENGINEERING_GO = "AMBIGUITY_ENGINEERING_GO"


@dataclass(frozen=True, slots=True)
class LiveAuthorization:
    capability: Capability
    fixture_manifest_sha256: str
    runtime_pin_sha256: str
    connector_source_sha256: str
    authorization_id: str
    operator_alias: str
    authorized_at: float
    expires_at: float
    operator_confirmation: str
    gate_version: str = "sheets-live-authorization-v1"
    purpose: str = PURPOSE
    engineering_only: bool = True

    def __post_init__(self):
        frozen._require(type(self.capability) is Capability)
        for value in (self.fixture_manifest_sha256, self.runtime_pin_sha256,
                      self.connector_source_sha256):
            _hash(value)
        frozen._safe_label(self.authorization_id)
        frozen._safe_label(self.operator_alias)
        frozen._number(self.authorized_at, positive=True)
        frozen._number(self.expires_at, positive=True)
        frozen._require(self.expires_at > self.authorized_at
                        and self.operator_confirmation == CONFIRMATION
                        and self.gate_version == "sheets-live-authorization-v1"
                        and self.purpose == PURPOSE and self.engineering_only is True)


def source_hash():
    return sha256_hex(Path(__file__).read_bytes())


def pin_hash():
    return sha256_hex((frozen.SHEETS_DOCS / "SHEETS_RUNTIME_PIN_DRAFT.json").read_bytes())


def validate_authorization(authorization, capability, fixture, *, now):
    frozen._require(type(authorization) is LiveAuthorization
                    and type(capability) is Capability and type(fixture) is frozen.Fixture)
    frozen._number(now)
    frozen._require(authorization.capability is capability
                    and authorization.fixture_manifest_sha256 == fixture.manifest_hash
                    and authorization.runtime_pin_sha256 == pin_hash()
                    and authorization.connector_source_sha256 == source_hash()
                    and authorization.authorized_at <= now < authorization.expires_at)
    return frozen.check_runtime()


def validate_context(context):
    frozen._require(type(context) is ssl.SSLContext
                    and context.protocol == ssl.PROTOCOL_TLS_CLIENT
                    and context.check_hostname is True
                    and context.verify_mode == ssl.CERT_REQUIRED
                    and context.keylog_filename is None
                    and context.minimum_version >= ssl.TLSVersion.TLSv1_2
                    and context.cert_store_stats()["x509_ca"] > 0)


@dataclass(frozen=True, slots=True)
class ConnectorEvidence:
    runtime_sha256: str
    runtime_pin_sha256: str
    connector_source_sha256: str
    authorization_id: str
    capability: Capability
    minimum_version: int
    maximum_version: int
    verify_flags: int
    options: int
    ca_count: int
    timeout_seconds: float

    def __post_init__(self):
        for value in (self.runtime_sha256, self.runtime_pin_sha256, self.connector_source_sha256):
            _hash(value)
        frozen._safe_label(self.authorization_id)
        frozen._require(type(self.capability) is Capability)
        for value in (self.minimum_version, self.maximum_version, self.verify_flags,
                      self.options, self.ca_count):
            frozen._require(type(value) is int)
        frozen._require(self.minimum_version >= int(ssl.TLSVersion.TLSv1_2)
                        and self.ca_count > 0)
        frozen._number(self.timeout_seconds, positive=True)

    def evidence(self):
        # Fixed constructor projection. Never accepts tokens/headers/exceptions.
        return {"schema": "sheets-connector-evidence-v1", "engineering_only": True,
                "implementation": "stdlib-httpsconnection-phase1-v1",
                "runtime_sha256": self.runtime_sha256,
                "runtime_pin_sha256": self.runtime_pin_sha256,
                "connector_source_sha256": self.connector_source_sha256,
                "openssl": ssl.OPENSSL_VERSION, "host": frozen.HOST, "port": 443,
                "timeout_seconds": self.timeout_seconds,
                "ssl_policy": "create-default-context-server-auth",
                "hostname_check": True, "certificate_verification": "CERT_REQUIRED",
                "minimum_version": self.minimum_version, "maximum_version": self.maximum_version,
                "verify_flags": self.verify_flags, "options": self.options,
                "loaded_ca_count": self.ca_count,
                "trust_source": "openssl-default-paths-not-yet-live-qualified",
                "environment_gate": "PASS_OFFLINE_ENVIRONMENT_POLICY_V1",
                "authorization_id": self.authorization_id,
                "capability": self.capability.value}


class ConnectorFactory:
    """One-use fresh HTTPSConnection construction, with no connect/send here.

    After authorization/runtime/environment and timeout prechecks succeed, the
    first actual construction attempt consumes this factory regardless of outcome.
    Precheck failure does not consume it. This is not durable authorization-ID
    consumption. The raw returned connection is a trusted implementation object,
    not a capability-safe public client; separation is construction-level only.

    Default deny, fixed host/port and real stdlib class. A socket may only be
    opened by a later separately audited adapter/runner. This phase supplies no
    connecting adapter: it must also enforce deadlines and bind capability to
    actual wire method/fault mode before the frozen socket seam can be used live.
    """
    def __init__(self):
        self._used = False
        self._lock = threading.Lock()

    def construct(self, *, capability, fixture, timeout, authorization=None):
        # No environment supplied by caller: actual production environment is
        # checked before SSL creation (especially SSLKEYLOGFILE).
        with self._lock:
            frozen._require(not self._used)
            runtime = validate_authorization(authorization, capability, fixture, now=time.time())
            frozen._number(timeout, positive=True)
            environment_gate(os.environ)
            # Prechecks passed: the first actual construction attempt consumes
            # this object on success or failure, not the durable authorization ID.
            self._used = True
            connection = None
            try:
                context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
                validate_context(context)
                connection = http.client.HTTPSConnection(frozen.HOST, 443,
                                                         timeout=timeout, context=context)
                connection.auto_open = 0
                connection.debuglevel = 0
                frozen._require(connection.sock is None and connection._tunnel_host is None)
                evidence = ConnectorEvidence(
                    sha256_hex(canonical_json_bytes(runtime)), pin_hash(), source_hash(),
                    authorization.authorization_id, capability, int(context.minimum_version),
                    int(context.maximum_version), int(context.verify_flags), int(context.options),
                    context.cert_store_stats()["x509_ca"], timeout)
                return connection, evidence
            except Exception:
                if connection is not None:
                    connection.close()
                raise frozen.QualificationError() from None
