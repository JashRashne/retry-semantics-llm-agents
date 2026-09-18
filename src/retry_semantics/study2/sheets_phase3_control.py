"""DRAFT Phase 3 local-only fixture, trust, issuance and preflight machinery.

No OAuth import, connector, DNS, TLS handshake or socket creation. SSLContext
construction reads local trust only. Operator assertions are not signatures.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib
import os
from pathlib import Path
import platform
import re
import ssl
import stat
import subprocess

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_live_go_phase1 as p1
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2 import sheets_phase2_control as p2
from retry_semantics.study2 import sheets_phase2_read as read

PROVISION_CONFIRMATION = "REVIEWED_SAME_APP_ENGINEERING_PROVISIONING"
PHASE2_COMMIT = "42460a77e6854f649ecdd4ac655df7393f058f86"
EXTRA_ENV_DENY = frozenset({"GOOGLE_APPLICATION_CREDENTIALS", "CLOUDSDK_CONFIG",
    "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE", "GOOGLE_AUTH_SUPPRESS_CREDENTIALS_WARNINGS",
    "PYTHONSTARTUP", "PYTHONINSPECT", "PYTHONUSERBASE", "DYLD_FALLBACK_LIBRARY_PATH",
    "DYLD_FALLBACK_FRAMEWORK_PATH", "DYLD_ROOT_PATH", "LD_AUDIT", "LD_DEBUG"})


def environment_gate():
    p1.environment_gate(os.environ)
    p2.require(not any(name.upper() in EXTRA_ENV_DENY or name.upper().startswith(
        ("DYLD_", "LD_", "GIT_")) for name in os.environ))


def load_json(path: Path, *, limit=65536):
    """Bounded regular private operator artifact; no links or discovery."""
    p2.require(path.is_absolute() and ".." not in path.parts)
    p2.require(not any(p.is_symlink() for p in (path, *path.parents)))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        p2._private_fd(fd)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            body = stream.read(limit + 1)
        p2.require(len(body) <= limit)
    finally:
        os.close(fd)
    value = p2.strict_json(body)
    p2.require(type(value) is dict and body == canonical_json_bytes(value) + b"\n")
    return value


def write_json(path: Path, value: dict):
    """Exclusive private output with file/parent fsync; never overwrite/refund."""
    p2.require(path.is_absolute() and ".." not in path.parts
               and not any(p.is_symlink() for p in (path, *path.parents)))
    data = canonical_json_bytes(value) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        p2._private_fd(fd)
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            p2.require(count > 0)
            view = view[count:]
        os.fsync(fd)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        os.close(fd)


@dataclass(frozen=True, slots=True)
class ProvisioningRecord:
    """Positive reviewed projection of a separate provisioning action, not proof."""
    identity_kind: str
    mechanism: str
    public_app_config_sha256: str
    account_alias: str
    spreadsheet_id: str
    sheet_id: int
    rows: int
    reservation_id: str
    operator_alias: str
    confirmed_at: float
    operator_confirmation: str
    isolated: bool
    no_automation_or_writers: bool
    engineering_only: bool = True
    schema: str = "sheets-phase3-provisioning-record-v1"

    def __post_init__(self):
        p2.require(all(type(getattr(self, n)) is str for n in (
            "schema", "mechanism", "identity_kind", "public_app_config_sha256", "account_alias",
            "spreadsheet_id", "reservation_id", "operator_alias", "operator_confirmation")))
        p2.require(self.schema == "sheets-phase3-provisioning-record-v1"
            and self.mechanism == "same-app-sheets-create-separately-authorized"
            and self.engineering_only is True and self.isolated is True
            and self.no_automation_or_writers is True
            and self.operator_confirmation == PROVISION_CONFIRMATION)
        p2.digest(self.public_app_config_sha256)
        p2.label(self.account_alias)
        p2.label(self.operator_alias)
        frozen._number(self.confirmed_at, positive=True)
        # Reuse frozen identity/range/namespace validation. Digest below covers
        # only this allowlisted independent provisioning record, no API body.
        p2.QualificationFixture(self.spreadsheet_id, self.sheet_id, self.rows,
            self.reservation_id, p2.SameAppProvenance("created_by_same_app",
                self.public_app_config_sha256, self.account_alias, "0" * 64), self.identity_kind)

    def projection(self):
        self.__post_init__()
        return asdict(self)

    @property
    def evidence_hash(self):
        return sha256_hex(canonical_json_bytes(self.projection()))

    def fixture(self):
        self.__post_init__()
        return p2.QualificationFixture(self.spreadsheet_id, self.sheet_id, self.rows,
            self.reservation_id, p2.SameAppProvenance("created_by_same_app",
                self.public_app_config_sha256, self.account_alias, self.evidence_hash), self.identity_kind)


def fixture_descriptor(record: ProvisioningRecord):
    p2.require(type(record) is ProvisioningRecord)
    fixture = record.fixture()
    return {"schema": "sheets-phase3-fixture-descriptor-v1", "executable": True,
        "provisioning_record": record.projection(), "provisioning_evidence_sha256": record.evidence_hash,
        "fixture": fixture.manifest, "fixture_hash": fixture.manifest_hash,
        "baseline_policy": "whole-grid-empty-or-retire-no-cleanup"}


def parse_fixture_descriptor(value: dict, *, _test_only=False):
    p2.require(type(value) is dict and set(value) == {"schema", "executable", "provisioning_record",
        "provisioning_evidence_sha256", "fixture", "fixture_hash", "baseline_policy"})
    p2.require(type(value["provisioning_record"]) is dict
        and set(value["provisioning_record"]) == set(ProvisioningRecord.__dataclass_fields__))
    record = ProvisioningRecord(**value["provisioning_record"])
    p2.require(_test_only or record.identity_kind == "PROVISIONED")
    p2.require(value == fixture_descriptor(record))
    return record.fixture()


@dataclass(frozen=True, slots=True)
class RuntimeConfiguration:
    """Operator-selected caps, not Google latency measurements or paper results.

    Stage allocations derive one total watchdog, not independent stage deadlines.
    All local work is included; safety and uncertainty are readiness additions.
    No operational default values are selected by the code.
    """
    dns_seconds: float
    tcp_seconds: float
    tls_seconds: float
    tls_evidence_seconds: float
    construction_seconds: float
    evidence_fsync_seconds: float
    status_seconds: float
    body_seconds: float
    parser_seconds: float
    verifier_seconds: float
    safety_seconds: float
    clock_uncertainty_seconds: float
    max_response_bytes: int
    max_cell_characters: int
    registry_root: str
    operator_basis: str
    schema: str = "sheets-phase3-runtime-configuration-v1"

    def __post_init__(self):
        p2.require(type(self.schema) is str and self.schema == "sheets-phase3-runtime-configuration-v1")
        for name in self.__dataclass_fields__:
            if name.endswith("_seconds"):
                frozen._number(getattr(self, name), positive=name != "clock_uncertainty_seconds")
        p2.label(self.operator_basis)
        self.read_configuration()

    @property
    def attempt_seconds(self):
        return sum(getattr(self, n) for n in self.__dataclass_fields__
                   if n.endswith("_seconds") and n not in ("clock_uncertainty_seconds", "safety_seconds"))

    def read_configuration(self):
        return read.ReadConfiguration(self.attempt_seconds, self.max_response_bytes,
                                      self.max_cell_characters, self.registry_root)

    def projection(self):
        self.__post_init__()
        return asdict(self)

    def check_ready(self, *, expires_at: float, clock_uncertainty_seconds: float, now: float):
        self.__post_init__()
        for value in (expires_at, clock_uncertainty_seconds, now):
            frozen._number(value)
        p2.require(clock_uncertainty_seconds == self.clock_uncertainty_seconds
            and expires_at - now > self.attempt_seconds + self.safety_seconds + clock_uncertainty_seconds)


def _trust_file(path: Path):
    # OpenSSL default CA links are normal. Record both selected and resolved
    # public trust paths plus metadata; refuse non-regular/unbounded material.
    resolved = path.resolve(strict=True)
    fd = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        p2.require(stat.S_ISREG(info.st_mode) and info.st_size <= 16 * 1024 * 1024
            and not stat.S_IMODE(info.st_mode) & 0o022)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(16 * 1024 * 1024 + 1)
        after = os.fstat(fd)
        fields = ("st_size", "st_mtime_ns", "st_ctime_ns", "st_ino", "st_dev", "st_mode", "st_uid")
        p2.require(len(data) == info.st_size and all(getattr(after, n) == getattr(info, n) for n in fields))
    finally:
        os.close(fd)
    return {"selected_path": str(path), "resolved_path": str(resolved), "bytes": len(data),
            "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "mtime_ns": info.st_mtime_ns,
            "sha256": sha256_hex(data)}


def trust_inventory():
    """Local trust configuration, never an offline route/peer authenticity claim."""
    environment_gate()  # BEFORE SSL creation, including keylog handling.
    paths = ssl.get_default_verify_paths()
    p2.require(paths.cafile is not None and paths.capath is not None)
    ca_file = _trust_file(Path(paths.cafile))
    directory = Path(paths.capath)
    p2.require(directory.is_dir() and not stat.S_IMODE(directory.stat().st_mode) & 0o022)
    # capath lazily loads certs. Bind every flat regular target and link identity;
    # refuse nested/special entries instead of silently omitting trust material.
    entries = sorted(directory.iterdir())
    p2.require(len(entries) <= 4096)
    material = [_trust_file(entry) for entry in entries]
    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    p1.validate_context(context)
    p2.require(ca_file == _trust_file(Path(paths.cafile))
        and material == [_trust_file(entry) for entry in sorted(directory.iterdir())])
    return {"schema": "sheets-phase3-trust-inventory-v1", "python": platform.python_version(),
        "openssl": ssl.OPENSSL_VERSION, "default_verify_paths": paths._asdict(),
        "ca_file": ca_file, "ca_directory": {"selected_path": str(directory),
            "resolved_path": str(directory.resolve()), "mode": stat.S_IMODE(directory.stat().st_mode),
            "uid": directory.stat().st_uid, "entry_count": len(entries),
            "material_sha256": sha256_hex(canonical_json_bytes(material))},
        "hostname_check": True, "verify_mode": "CERT_REQUIRED",
        "minimum_tls": int(context.minimum_version), "maximum_tls": int(context.maximum_version),
        "verify_flags": int(context.verify_flags), "options": int(context.options),
        "loaded_ca_count": context.cert_store_stats()["x509_ca"], "keylog": "disabled",
        "alpn_offering": "none-explicit-frozen-phase2", "environment": "PASS_NAMES_ONLY",
        "authenticity": "not-established-offline"}


def source_hash():
    directory = Path(__file__).parent
    files = {name: sha256_hex((directory / name).read_bytes()) for name in (
        "sheets_phase3_credentials.py", "sheets_phase3_control.py", "sheets_phase3_operator.py")}
    files["phase2"] = read.source_hash()
    for name in ("fixtures/qualification_fixture_phase3_template.json",
                 "SHEETS_PHASE3_OPERATOR_CONFIGURATION_TEMPLATE.json"):
        files[name] = sha256_hex((frozen.SHEETS_DOCS / name).read_bytes())
    return sha256_hex(canonical_json_bytes(files))


def runtime_projection(configuration: RuntimeConfiguration):
    p2.require(type(configuration) is RuntimeConfiguration)
    return {"schema": "sheets-phase3-runtime-pin-v1", "phase2_runtime_hash":
        read.runtime_hash(configuration.read_configuration()), "phase2_source_hash": read.source_hash(),
        "phase3_source_hash": source_hash(), "configuration": configuration.projection(),
        "repository_tool": {"path": "/usr/bin/git", "sha256": sha256_hex(Path("/usr/bin/git").read_bytes()),
            "fsmonitor": "disabled", "untracked_cache": "disabled", "submodules": "ignored"},
        "credential_stdlib_implementation": {name: sha256_hex(Path(importlib.import_module(name).__file__).read_bytes())
            for name in ("http.server", "urllib.parse", "secrets", "base64", "hashlib", "hmac", "_hashlib")},
        "trust_inventory": trust_inventory()}


def runtime_hash(configuration: RuntimeConfiguration):
    return sha256_hex(canonical_json_bytes(runtime_projection(configuration)))


@dataclass(frozen=True, slots=True)
class LocalConditions:
    """Explicit audit/operator conditions; no parent checklist status promotion."""
    hostile_audit_approved: bool
    private_posix_storage_reviewed: bool
    trust_material_stable_for_attempt: bool
    clock_basis_reviewed: bool
    provisioning_reviewed: bool
    engineering_only: bool = True

    def validate(self):
        p2.require(all(getattr(self, n) is True for n in self.__dataclass_fields__))


def repository_check(expected_head: str):
    environment_gate()
    p2.require(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head))
    def git(*args):
        result = subprocess.run(["/usr/bin/git", "-c", "core.fsmonitor=false", "-c",
            "core.untrackedCache=false", "-c", "submodule.recurse=false", *args],
            cwd=frozen.ROOT, capture_output=True, check=False)
        p2.require(result.returncode == 0)
        return result.stdout
    p2.require(git("rev-parse", "HEAD").decode("ascii").strip() == expected_head)
    p2.require(git("rev-parse", "--show-toplevel").decode("utf-8").strip() == str(frozen.ROOT))
    p2.require(not git("status", "--porcelain", "--ignore-submodules=all"))
    git("merge-base", "--is-ancestor", PHASE2_COMMIT, expected_head)


def checklist_local_gate():
    value = p2.strict_json((frozen.SHEETS_DOCS / "SHEETS_LIVE_GO_CHECKLIST_DRAFT.json").read_bytes())
    p2.require(type(value) is dict and value.get("live_go") == "CLOSED"
        and value.get("engineering_only") is True and type(value.get("paper_observations")) is int
        and value["paper_observations"] == 0)
    update = value.get("phase3_update")
    p2.require(type(update) is dict and update.get("read_issuance_required_local_conditions")
        == list(LocalConditions.__dataclass_fields__))


class RegistryInspection:
    """Read-only fd access; never initialize, reserve, claim or repair a registry."""
    def __init__(self, root: str):
        path = Path(root)
        p2.require(path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)))
        self._dir = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            p2._private_fd(self._dir, directory=True)
        except BaseException:
            os.close(self._dir)
            raise

    read = p2.LocalRegistry.read
    _reservations = p2.LocalRegistry._reservations
    check_claim = p2.LocalRegistry.check_claim

    def check_reserved(self, fixture):
        p2.require(p2.LocalRegistry.reservation(fixture) in self._reservations())

    def absent(self, authorization_id):
        p2.label(authorization_id)
        names = set(os.listdir(self._dir))
        p2.require(f"claim-{authorization_id}.json" not in names
                   and f"attempt-{authorization_id}.jsonl" not in names)

    def close(self):
        os.close(self._dir)


def authorization_projection(authorization: p1.LiveAuthorization):
    p2._validate_assertion_shape(authorization)
    value = asdict(authorization)
    value["capability"] = authorization.capability.value
    return value


def parse_authorization(value: dict):
    p2.require(type(value) is dict and set(value) == set(p1.LiveAuthorization.__dataclass_fields__))
    p2.require(value["capability"] == "LIVE_READ_GO")
    return p1.LiveAuthorization(**{**value, "capability": p1.Capability.LIVE_READ_GO})


def issuance_receipt(authorization, configuration, conditions):
    p2.require(type(conditions) is LocalConditions)
    conditions.validate()
    return {"schema": "sheets-phase3-issuance-receipt-v1", "authorization_hash":
        p2.authorization_hash(authorization), "phase3_runtime_hash": runtime_hash(configuration),
        "phase3_source_hash": source_hash(), "local_conditions": asdict(conditions)}


def preflight(*, descriptor: dict, configuration: RuntimeConfiguration, expected_pin: dict,
              expected_head: str, conditions: LocalConditions, now: float,
              credential_metadata=None, authorization=None, receipt=None, _test_only=False):
    """Deterministic local report; no credentials, authorization issuance or network.

    PASS without metadata is only local configuration readiness; issuance requires
    metadata, and execution also requires token/authorization/receipt. Read-dependent
    checklist gates are deliberately absent.
    """
    reasons = []
    fixture = None
    def check(code, operation):
        try:
            return operation()
        except Exception:
            reasons.append(code)
            return None
    check("environment", environment_gate)
    check("checklist_local_policy", checklist_local_gate)
    check("repository", lambda: repository_check(expected_head))
    check("conditions", lambda: (p2.require(type(conditions) is LocalConditions), conditions.validate()))
    check("runtime_pin", lambda: p2.require(runtime_projection(configuration) == expected_pin))
    fixture = check("fixture_provenance", lambda: parse_fixture_descriptor(descriptor, _test_only=_test_only))
    if fixture is not None:
        check("provisioning_time", lambda: p2.require(
            descriptor["provisioning_record"]["confirmed_at"] <= now))
        def registry_checks():
            inspection = RegistryInspection(configuration.registry_root)
            try:
                inspection.check_reserved(fixture)
                if authorization is not None:
                    inspection.absent(authorization.authorization_id)
            finally:
                inspection.close()
        check("reservation_or_spent", registry_checks)
    if credential_metadata is not None:
        def credential_checks():
            # Import only the immutable metadata type; no preparer construction.
            from retry_semantics.study2.sheets_phase3_credentials import AcquisitionMetadata
            p2.require(type(credential_metadata) is AcquisitionMetadata and fixture is not None)
            credential_metadata.__post_init__()
            p2.require(credential_metadata.public_config_sha256 == fixture.provenance.public_app_config_sha256
                and credential_metadata.account_alias == fixture.provenance.account_alias
                and credential_metadata.prepared_at <= now)
            configuration.check_ready(expires_at=credential_metadata.expires_at,
                clock_uncertainty_seconds=credential_metadata.clock_uncertainty_seconds, now=now)
        check("credential_readiness", credential_checks)
    if authorization is not None:
        def authorization_checks():
            p2.require(fixture is not None)
            p2.validate_read_authorization(authorization, fixture,
                read.runtime_hash(configuration.read_configuration()), read.source_hash(), now=now)
            p2.require(receipt == issuance_receipt(authorization, configuration, conditions))
        check("authorization_binding", authorization_checks)
    elif receipt is not None:
        reasons.append("authorization_binding")
    return {"schema": "sheets-phase3-preflight-report-v1", "status": "BLOCKED" if reasons else "PASS",
            "reasons": reasons, "scope": ("local-configuration-readiness" if authorization is None
            else "local-authorization-readiness") if credential_metadata is None else
            ("local-issuance-readiness" if authorization is None else "local-consumption-readiness"),
            "credential_metadata_supplied": credential_metadata is not None,
            "network": "not-performed", "live_go": "CLOSED", "paper_observations": 0}


def issue_authorization(*, descriptor, configuration, expected_pin, expected_head, conditions,
                        credential_metadata,
                        capability: str, fixture_hash: str, phase3_runtime_hash: str,
                        phase3_source_hash: str, authorization_id: str, operator_alias: str,
                        issued_at: float, expires_at: float, operator_confirmation: str,
                        purpose: str, engineering_only: bool, now: float, _test_only=False):
    """Local issuance only. Output remains the unmodified Phase 2 consumer schema.

    A required companion receipt binds the additive Phase 3 source/trust/budget.
    Direct Phase 2 callers do not enforce the receipt; operator use must use wrapper.
    """
    p2.require(capability == "LIVE_READ_GO" and purpose == p1.PURPOSE and engineering_only is True
               and credential_metadata is not None)
    report = preflight(descriptor=descriptor, configuration=configuration, expected_pin=expected_pin,
        expected_head=expected_head, conditions=conditions, now=now,
        credential_metadata=credential_metadata, _test_only=_test_only)
    p2.require(report["status"] == "PASS")
    fixture = parse_fixture_descriptor(descriptor, _test_only=_test_only)
    p2.require(fixture_hash == fixture.manifest_hash and phase3_runtime_hash == runtime_hash(configuration)
               and phase3_source_hash == source_hash())
    frozen._number(issued_at, positive=True)
    frozen._number(expires_at, positive=True)
    frozen._number(now, positive=True)
    # Issued now, enough time for the whole hard read plus safety, no long-lived
    # standing grant. Max lifetime is two complete readiness budgets; derived
    # from configuration, not an unexplained production constant.
    budget = configuration.attempt_seconds + configuration.safety_seconds + configuration.clock_uncertainty_seconds
    p2.require(issued_at <= now < expires_at and now - issued_at <= configuration.clock_uncertainty_seconds
        and budget < expires_at - now and expires_at - issued_at <= 2 * budget)
    authorization = p1.LiveAuthorization(p1.Capability.LIVE_READ_GO, fixture.manifest_hash,
        read.runtime_hash(configuration.read_configuration()), read.source_hash(), authorization_id,
        operator_alias, issued_at, expires_at, operator_confirmation)
    inspection = RegistryInspection(configuration.registry_root)
    try:
        inspection.absent(authorization_id)
    finally:
        inspection.close()
    return authorization, issuance_receipt(authorization, configuration, conditions)


def inspect_recovery(*, configuration, descriptor, authorization, _test_only=False):
    """Inspect typed evidence only. Never delete, resume, refund or infer remote state."""
    fixture = parse_fixture_descriptor(descriptor, _test_only=_test_only)
    inspection = RegistryInspection(configuration.registry_root)
    try:
        names = set(os.listdir(inspection._dir))
        claim = f"claim-{p2.label(authorization.authorization_id)}.json" in names
        attempt = f"attempt-{authorization.authorization_id}.jsonl" in names
        inspection.check_reserved(fixture)
        if claim:
            inspection.check_claim(authorization, fixture,
                read.runtime_hash(configuration.read_configuration()), read.source_hash())
        p2.require(not attempt or claim)
        result = "no-attempt-recorded"
        if attempt:
            evidence = read.AttemptEvidence(inspection, fixture, authorization.authorization_id,
                read.runtime_hash(configuration.read_configuration()), read.source_hash(), reserve=False)
            records = evidence.records()
            result = "terminal-recorded" if records[-1].get("stage") == read.Stage.TERMINAL.value else "incomplete"
        return {"schema": "sheets-phase3-recovery-report-v1", "claim_present": claim,
            "authorization_state": "SPENT" if claim or attempt else "not-recorded-not-renewed",
            "evidence": result, "remote_state": "not-inferred", "recovery": "operator-review-no-retry"}
    except Exception:
        pass
    finally:
        inspection.close()
    return {"schema": "sheets-phase3-recovery-report-v1", "authorization_state": "UNUSABLE",
        "evidence": "invalid-or-incomplete", "remote_state": "not-inferred", "recovery": "operator-review-no-retry"}
