"""DRAFT Phase 2 local control plane. No credential acquisition or network I/O.

POSIX private local filesystem only; operator assertions are not signatures.
Deleting/replacing the registry is outside the anti-replay guarantee and requires
operator incident review, never automatic recovery. No unconsume API exists.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
from typing import Iterator

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_live_go_phase1 as phase1
from retry_semantics.study2 import sheets_live_preparation as frozen


class Refused(frozen.QualificationError):
    pass


class Spent(Refused):
    """Existing claim, including incomplete/corrupt claim: never unused."""


def authorization_hash(authorization: phase1.LiveAuthorization) -> str:
    _validate_assertion_shape(authorization)
    # Hash a positive nonsecret operator-assertion projection, NEVER a token or
    # broad runtime/credential object. These are independent input domains.
    return sha256_hex(canonical_json_bytes({
        "gate_version": authorization.gate_version, "purpose": authorization.purpose,
        "authorization_id": authorization.authorization_id,
        "operator_alias": authorization.operator_alias,
        "authorized_at": authorization.authorized_at, "expires_at": authorization.expires_at,
        "operator_confirmation": authorization.operator_confirmation,
        "engineering_only": authorization.engineering_only,
        "capability": authorization.capability.value,
        "fixture_hash": authorization.fixture_manifest_sha256,
        "runtime_hash": authorization.runtime_pin_sha256,
        "source_hash": authorization.connector_source_sha256}))


def require(condition: object) -> None:
    if not condition:
        raise Refused()


def label(value: str) -> str:
    frozen._safe_label(value)
    return value


def digest(value: str) -> None:
    phase1._hash(value)


def strict_json(body: bytes) -> object:
    require(type(body) is bytes)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result
    def invalid(_):
        raise Refused()
    def finite_float(value):
        number = float(value)
        require(math.isfinite(number))
        return number
    try:
        # UTF-8 only: json.loads(bytes) otherwise accepts UTF-16/32 and BOM.
        return json.loads(body.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=invalid, parse_float=finite_float)
    except (UnicodeError, ValueError, RecursionError):
        raise Refused() from None


@dataclass(frozen=True, slots=True)
class SameAppProvenance:
    mode: str
    public_app_config_sha256: str
    account_alias: str
    provisioning_evidence_sha256: str

    def __post_init__(self) -> None:
        require(type(self.mode) is str and self.mode in ("created_by_same_app", "selected_through_same_app"))
        digest(self.public_app_config_sha256)
        digest(self.provisioning_evidence_sha256)
        label(self.account_alias)

    def projection(self) -> dict:
        return {"mode": self.mode, "public_app_config_sha256": self.public_app_config_sha256,
                "account_alias": self.account_alias,
                "provisioning_evidence_sha256": self.provisioning_evidence_sha256}


@dataclass(frozen=True, slots=True)
class QualificationFixture:
    spreadsheet_id: str
    sheet_id: int
    rows: int
    reservation_id: str
    provenance: SameAppProvenance
    identity_kind: str = "TEST_ONLY"
    schema: str = "sheets-phase2-fixture-v1"
    purpose: str = phase1.PURPOSE
    engineering_only: bool = True

    def __post_init__(self) -> None:
        require(type(self.schema) is str and type(self.purpose) is str
                and type(self.identity_kind) is str
                and self.schema == "sheets-phase2-fixture-v1" and self.purpose == phase1.PURPOSE
                and self.engineering_only is True and type(self.provenance) is SameAppProvenance)
        label(self.reservation_id)
        require(type(self.sheet_id) is int and 0 <= self.sheet_id <= 2147483647
                and type(self.rows) is int and 3 <= self.rows <= 1000)
        require(type(self.spreadsheet_id) is str
                and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.spreadsheet_id))
        require(self.identity_kind in ("TEST_ONLY", "PROVISIONED"))
        if self.identity_kind == "TEST_ONLY":
            require(self.spreadsheet_id.startswith("TEST_ONLY_"))
        else:
            require(len(self.spreadsheet_id) >= 20 and not re.search(
                r"test|offline|placeholder|draft|invalid|synthetic", self.spreadsheet_id, re.I))

    @property
    def title(self) -> str:
        return "RetrySemanticsEngineering"

    @property
    def columns(self) -> int:
        return 3

    @property
    def verifier_range(self) -> str:
        return f"'{self.title}'!A1:C{self.rows}"

    @property
    def marker_namespace(self) -> str:
        return sha256_hex(canonical_json_bytes({"spreadsheet_id": self.spreadsheet_id,
            "sheet_id": self.sheet_id, "reservation_id": self.reservation_id,
            "schema": self.schema}))

    def marker(self, case_id: str) -> str:
        return f"ENGINEERING-ONLY-{self.marker_namespace}-{label(case_id)}"

    @property
    def manifest(self) -> dict:
        return {"schema": self.schema, "purpose": self.purpose, "engineering_only": True,
                "identity_kind": self.identity_kind, "spreadsheet_id": self.spreadsheet_id,
                "sheet_id": self.sheet_id, "title": self.title, "sheet_type": "GRID",
                "rows": self.rows, "columns": 3, "verifier_range": self.verifier_range,
                "reservation_id": self.reservation_id, "marker_namespace": self.marker_namespace,
                "verifier_case_id": "qualification_read",
                "provenance": self.provenance.projection()}

    @property
    def manifest_hash(self) -> str:
        return sha256_hex(canonical_json_bytes(self.manifest))


def validate_fixture(fixture: QualificationFixture) -> None:
    require(type(fixture) is QualificationFixture)
    fixture.__post_init__()
    fixture.provenance.__post_init__()


def _private_fd(fd: int, *, directory: bool = False) -> None:
    info = os.fstat(fd)
    require((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
            and (directory or info.st_nlink == 1))


class LocalRegistry:
    """Permanent O_EXCL claims + serialized collision-checked reservations.

    Callers must select one persistent registry for all qualification attempts.
    Separate registries cannot provide global anti-replay. Parent directories,
    same-UID operators and filesystem fsync semantics are trusted prerequisites.
    """
    def __init__(self, path: Path) -> None:
        self._thread_lock = threading.RLock()
        self.path = Path(path).absolute()
        # No symlink traversal, including ancestors. Do not resolve away links.
        for ancestor in reversed((self.path, *self.path.parents)):
            if ancestor.exists() or ancestor.is_symlink():
                require(not ancestor.is_symlink())
        try:
            self.path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        else:
            parent = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        self._dir = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            _private_fd(self._dir, directory=True)
            self._lock = os.open("registry.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                                 0o600, dir_fd=self._dir)
            _private_fd(self._lock)
            os.fsync(self._lock)
            os.fsync(self._dir)
        except BaseException:
            os.close(self._dir)
            if hasattr(self, "_lock"):
                os.close(self._lock)
            raise

    @contextmanager
    def locked(self) -> Iterator[None]:
        with self._thread_lock:
            fcntl.flock(self._lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(self._lock, fcntl.LOCK_UN)

    def create(self, name: str, value: dict) -> None:
        require(re.fullmatch(r"(?:reservation|claim|attempt)-[A-Za-z0-9_-]{1,128}\.jsonl?", name))
        data = canonical_json_bytes(value) + b"\n"
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self._dir)
        try:
            _private_fd(fd)
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                require(count > 0)
                view = view[count:]
            os.fsync(fd)
            os.fsync(self._dir)
        finally:
            os.close(fd)
        # Any failure leaves the name in place; never unlink even an empty file.

    def read(self, name: str, *, limit: int = 65536) -> bytes:
        require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]+", name))
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self._dir)
        try:
            _private_fd(fd)
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(limit + 1)
            require(len(data) <= limit)
            return data
        finally:
            os.close(fd)

    def _reservations(self) -> list[dict]:
        records = []
        for name in os.listdir(self._dir):
            if name.startswith("reservation-"):
                data = self.read(name)
                record = strict_json(data)
                require(type(record) is dict and set(record) == {
                    "schema", "fixture_hash", "spreadsheet_id", "marker_namespace", "reservation_id"})
                require(record["schema"] == "sheets-local-reservation-v1")
                digest(record["fixture_hash"])
                digest(record["marker_namespace"])
                label(record["reservation_id"])
                require(name == f'reservation-{record["reservation_id"]}.json'
                        and type(record["spreadsheet_id"]) is str
                        and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", record["spreadsheet_id"])
                        and data == canonical_json_bytes(record) + b"\n")
                records.append(record)
        for index, record in enumerate(records):
            require(not any(any(record[key] == other[key] for key in (
                "fixture_hash", "spreadsheet_id", "marker_namespace", "reservation_id"))
                for other in records[:index]))
        return records

    @staticmethod
    def reservation(fixture: QualificationFixture) -> dict:
        validate_fixture(fixture)
        return {"schema": "sheets-local-reservation-v1", "fixture_hash": fixture.manifest_hash,
                "spreadsheet_id": fixture.spreadsheet_id,
                "marker_namespace": fixture.marker_namespace,
                "reservation_id": fixture.reservation_id}

    def reserve(self, fixture: QualificationFixture) -> None:
        desired = self.reservation(fixture)
        with self.locked():
            require(not any(any(record[key] == desired[key] for key in (
                "fixture_hash", "spreadsheet_id", "marker_namespace", "reservation_id"))
                for record in self._reservations()))
            self.create(f"reservation-{fixture.reservation_id}.json", desired)

    def check_reserved(self, fixture: QualificationFixture) -> None:
        require(self.reservation(fixture) in self._reservations())

    def consume(self, authorization: phase1.LiveAuthorization,
                fixture: QualificationFixture, runtime_hash: str, source_hash: str,
                *, now: float) -> dict:
        validate_read_authorization(authorization, fixture, runtime_hash, source_hash, now=now)
        record = {"schema": "sheets-live-read-consumption-v1", "engineering_only": True,
                  "authorization_id": authorization.authorization_id,
                  "authorization_assertion_sha256": authorization_hash(authorization),
                  "capability": "LIVE_READ_GO", "fixture_hash": fixture.manifest_hash,
                  "runtime_hash": runtime_hash, "source_hash": source_hash,
                  "consumed_at": now, "meaning": "local_operator_authorization_spent"}
        with self.locked():
            self.check_reserved(fixture)
            try:
                self.create(f"claim-{authorization.authorization_id}.json", record)
            except FileExistsError:
                raise Spent() from None
        return record

    def check_claim(self, authorization: phase1.LiveAuthorization, fixture: QualificationFixture,
                    runtime_hash: str, source_hash: str) -> None:
        assertion_hash = authorization_hash(authorization)
        authorization_id = authorization.authorization_id
        data = self.read(f"claim-{label(authorization_id)}.json")
        record = strict_json(data)
        require(type(record) is dict and set(record) == {"schema", "engineering_only",
            "authorization_id", "capability", "fixture_hash", "runtime_hash", "source_hash",
            "consumed_at", "meaning", "authorization_assertion_sha256"})
        frozen._number(record["consumed_at"])
        require(record["engineering_only"] is True)
        require(data == canonical_json_bytes(record) + b"\n")
        require(record == {"schema": "sheets-live-read-consumption-v1", "engineering_only": True,
            "authorization_id": authorization_id, "capability": "LIVE_READ_GO",
            "authorization_assertion_sha256": assertion_hash,
            "fixture_hash": fixture.manifest_hash, "runtime_hash": runtime_hash,
            "source_hash": source_hash, "consumed_at": record["consumed_at"],
            "meaning": "local_operator_authorization_spent"})

    def close(self) -> None:
        os.close(self._lock)
        os.close(self._dir)

    def __enter__(self) -> LocalRegistry:
        return self

    def __exit__(self, *args) -> None:
        self.close()


def validate_read_authorization(authorization: phase1.LiveAuthorization,
                                fixture: QualificationFixture, runtime_hash: str,
                                source_hash: str, *, now: float) -> None:
    validate_fixture(fixture)
    _validate_assertion_shape(authorization)
    digest(runtime_hash)
    digest(source_hash)
    frozen._number(now)
    require(authorization.capability is phase1.Capability.LIVE_READ_GO
            and authorization.fixture_manifest_sha256 == fixture.manifest_hash
            and authorization.runtime_pin_sha256 == runtime_hash
            and authorization.connector_source_sha256 == source_hash
            and authorization.authorized_at <= now < authorization.expires_at)


def _validate_assertion_shape(authorization: phase1.LiveAuthorization) -> None:
    require(type(authorization) is phase1.LiveAuthorization)
    require(all(type(getattr(authorization, name)) is str for name in (
        "gate_version", "purpose", "operator_confirmation")))
    authorization.__post_init__()
