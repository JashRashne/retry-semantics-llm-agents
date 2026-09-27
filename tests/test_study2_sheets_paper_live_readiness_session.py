"""Offline tests for the Sheets paper live readiness operator session bridge."""

from __future__ import annotations

import inspect
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from retry_semantics.serialization import sha256_hex
from retry_semantics.study2.sheets_live_preparation import PreparedToken
from retry_semantics.study2.sheets_paper_materialize import (
    IMPLEMENTATION_PATHS,
    MANIFEST_PATH,
    REPOSITORY_ROOT,
    build_paper_manifest,
    load_paper_manifest,
)
from retry_semantics.study2.sheets_paper_readiness import PaperReadinessError
import run_sheets_paper_live_readiness_session as session_mod
from run_sheets_paper_live_readiness_session import (
    FROZEN_MANIFEST_SHA256,
    FROZEN_RUNTIME_HEAD,
    LIVE_READINESS_CONFIRMATION,
    ReadinessSessionRefused,
    main,
    make_token_metadata,
    run_readiness_session,
    verify_repository_state,
)

TEST_OPERATOR_HEAD = "1111111111111111111111111111111111111111"


def _clean_git(*args: str, root: Path = REPOSITORY_ROOT, head: str = TEST_OPERATOR_HEAD) -> bytes:
    if args == ("rev-parse", "HEAD"):
        return (head + "\n").encode("utf-8")
    if args == ("rev-parse", "--show-toplevel"):
        return (str(root.resolve()) + "\n").encode("utf-8")
    if args == ("status", "--porcelain", "--ignore-submodules=all"):
        return b""
    if len(args) == 4 and args[:3] == ("merge-base", "--is-ancestor", FROZEN_RUNTIME_HEAD):
        return b""
    raise AssertionError(f"unexpected git invocation: {args}")


def test_prospective_manifest_bytes_and_sha_match():
    """Verify the prospective V4.1 manifest is the materialized manifest."""
    manifest_raw = (REPOSITORY_ROOT / MANIFEST_PATH).read_bytes()
    assert FROZEN_MANIFEST_SHA256 == (
        "7c9bddb797938e026344afe49650922219ca35febf9322bdfb62f402caa87991"
    )
    assert sha256_hex(manifest_raw) == FROZEN_MANIFEST_SHA256
    assert manifest_raw == build_paper_manifest()
    loaded = load_paper_manifest()
    assert loaded["status"] == "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"
    assert loaded["audit_provenance"]["auditor_id"] == "openai-gpt-5.6-sol-independent-hostile-audit-v2"
    assert loaded["study2_paper_observations"] == 0
    assert "scripts/run_sheets_paper_live_readiness_session.py" not in IMPLEMENTATION_PATHS


def test_resident_bearer_reaches_capture_and_never_persisted_or_printed(tmp_path, monkeypatch, capsys):
    """Test resident bearer passes to run_capture in memory and is never written or printed."""
    monkeypatch.setattr(session_mod, "_git", _clean_git)
    monkeypatch.setattr(session_mod, "load_paper_manifest", lambda **kw:
                        dict(load_paper_manifest(**kw),
                             status="FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"))

    secret_bearer = "secret-resident-bearer-sample-xyz987"
    now = time.time()
    fake_token = PreparedToken(
        value=secret_bearer,
        expires_at=now + 10000.0,
        clock_uncertainty_seconds=1.0,
    )

    capture_calls = []

    def fake_acquire(_client_path, present_url=None):
        return fake_token

    def fake_capture(*, manifest, bearer, evidence_dir, token_metadata):
        capture_calls.append({
            "manifest": manifest,
            "bearer": bearer,
            "evidence_dir": evidence_dir,
            "token_metadata": token_metadata,
        })
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "capture-state.json").write_text("{\"state\":\"dummy\"}")
        return "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"

    evidence_dir = tmp_path / "readiness-evidence-001"
    client_file = tmp_path / "fake-client.json"
    client_file.write_text("{}")

    state = run_readiness_session(
        client_path=client_file,
        evidence_dir=evidence_dir,
        execute_live_readiness=True,
        readiness_confirmation=LIVE_READINESS_CONFIRMATION,
        expected_head=TEST_OPERATOR_HEAD,
        acquire_token_fn=fake_acquire,
        run_capture_fn=fake_capture,
    )

    assert state == "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"
    assert len(capture_calls) == 1
    call = capture_calls[0]

    # 1. Resident bearer reached run_capture directly in memory
    assert call["bearer"] is secret_bearer
    assert call["evidence_dir"] == evidence_dir

    # 2. Metadata fields are exact
    expected_meta = {
        "schema": "sheets-paper-prepared-token-v1",
        "bearer_sha256": sha256_hex(secret_bearer.encode("utf-8")),
        "expires_at": fake_token.expires_at,
        "clock_uncertainty_seconds": 1.0,
    }
    assert call["token_metadata"] == expected_meta

    # 3. Bearer is never written to disk in evidence dir or anywhere under tmp_path
    for path in tmp_path.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert secret_bearer.encode("utf-8") not in content

    # 4. Bearer is never printed via main CLI execution
    evidence_dir2 = tmp_path / "readiness-evidence-002"
    argv = [
        "--client", str(client_file),
        "--evidence-dir", str(evidence_dir2),
        "--execute-live-readiness",
        "--confirmation", LIVE_READINESS_CONFIRMATION,
        "--expected-head", TEST_OPERATOR_HEAD,
    ]
    monkeypatch.setattr(session_mod, "acquire_resident_token", fake_acquire)
    monkeypatch.setattr(session_mod, "run_capture", fake_capture)

    capsys.readouterr()  # clear
    exit_code = main(argv)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"
    assert secret_bearer not in captured.out
    assert secret_bearer not in captured.err


def test_expired_or_short_lived_token_refuses_before_capture(tmp_path, monkeypatch):
    """Test that a token unable to cover the fixed readiness schedule is refused."""
    monkeypatch.setattr(session_mod, "_git", _clean_git)
    monkeypatch.setattr(session_mod, "load_paper_manifest", lambda **kw:
                        dict(load_paper_manifest(**kw),
                             status="FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED"))


    # Token expires in 10 seconds (cannot cover ~600s schedule)
    short_token = PreparedToken(
        value="short-lived-bearer-token",
        expires_at=time.time() + 10.0,
        clock_uncertainty_seconds=1.0,
    )

    capture_mock = Mock()
    client_file = tmp_path / "fake-client.json"
    client_file.write_text("{}")
    evidence_dir = tmp_path / "evidence-short"

    with pytest.raises(PaperReadinessError, match="cannot cover"):
        run_readiness_session(
            client_path=client_file,
            evidence_dir=evidence_dir,
            execute_live_readiness=True,
            readiness_confirmation=LIVE_READINESS_CONFIRMATION,
            expected_head=TEST_OPERATOR_HEAD,
            acquire_token_fn=lambda *_, **__: short_token,
            run_capture_fn=capture_mock,
        )

    capture_mock.assert_not_called()
    assert not evidence_dir.exists()


def test_dirty_repo_refuses_before_oauth(tmp_path, monkeypatch):
    """Test dirty working tree causes refusal before OAuth is attempted."""
    def dirty_git(*args: str, root: Path = REPOSITORY_ROOT) -> bytes:
        if args == ("rev-parse", "HEAD"):
            return (TEST_OPERATOR_HEAD + "\n").encode("utf-8")
        if args == ("rev-parse", "--show-toplevel"):
            return (str(root.resolve()) + "\n").encode("utf-8")
        if args == ("status", "--porcelain", "--ignore-submodules=all"):
            return b" M some_file.py\n"
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(session_mod, "_git", dirty_git)

    acquire_mock = Mock()
    with pytest.raises(ReadinessSessionRefused, match="dirty"):
        run_readiness_session(
            client_path=tmp_path / "client.json",
            evidence_dir=tmp_path / "evidence",
            execute_live_readiness=True,
            readiness_confirmation=LIVE_READINESS_CONFIRMATION,
            expected_head=TEST_OPERATOR_HEAD,
            acquire_token_fn=acquire_mock,
        )

    acquire_mock.assert_not_called()


def test_wrong_head_refuses_before_oauth(tmp_path, monkeypatch):
    """Test repository commit HEAD not matching --expected-head causes refusal before OAuth."""
    def wrong_head_git(*args: str, root: Path = REPOSITORY_ROOT) -> bytes:
        if args == ("rev-parse", "HEAD"):
            return b"0000000000000000000000000000000000000000\n"
        if args == ("rev-parse", "--show-toplevel"):
            return (str(root.resolve()) + "\n").encode("utf-8")
        if args == ("status", "--porcelain", "--ignore-submodules=all"):
            return b""
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(session_mod, "_git", wrong_head_git)

    acquire_mock = Mock()
    with pytest.raises(ReadinessSessionRefused, match="repository HEAD"):
        run_readiness_session(
            client_path=tmp_path / "client.json",
            evidence_dir=tmp_path / "evidence",
            execute_live_readiness=True,
            readiness_confirmation=LIVE_READINESS_CONFIRMATION,
            expected_head=TEST_OPERATOR_HEAD,
            acquire_token_fn=acquire_mock,
        )

    acquire_mock.assert_not_called()


def test_not_ancestor_refuses_before_oauth(tmp_path, monkeypatch):
    """Test current HEAD not having FROZEN_RUNTIME_HEAD as ancestor refuses before OAuth."""
    def non_ancestor_git(*args: str, root: Path = REPOSITORY_ROOT) -> bytes:
        if args == ("rev-parse", "HEAD"):
            return (TEST_OPERATOR_HEAD + "\n").encode("utf-8")
        if args == ("rev-parse", "--show-toplevel"):
            return (str(root.resolve()) + "\n").encode("utf-8")
        if args == ("status", "--porcelain", "--ignore-submodules=all"):
            return b""
        if len(args) == 4 and args[:3] == ("merge-base", "--is-ancestor", FROZEN_RUNTIME_HEAD):
            raise subprocess.CalledProcessError(1, ["git", *args])
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(session_mod, "_git", non_ancestor_git)

    acquire_mock = Mock()
    with pytest.raises(ReadinessSessionRefused, match="not an ancestor of HEAD"):
        run_readiness_session(
            client_path=tmp_path / "client.json",
            evidence_dir=tmp_path / "evidence",
            execute_live_readiness=True,
            readiness_confirmation=LIVE_READINESS_CONFIRMATION,
            expected_head=TEST_OPERATOR_HEAD,
            acquire_token_fn=acquire_mock,
        )

    acquire_mock.assert_not_called()


def test_manifest_sha_mismatch_refuses_before_oauth(tmp_path, monkeypatch):
    """Test altered frozen manifest SHA causes refusal before OAuth."""
    monkeypatch.setattr(session_mod, "_git", _clean_git)

    acquire_mock = Mock()
    with pytest.raises(ReadinessSessionRefused, match="frozen manifest SHA"):
        verify_repository_state(
            expected_head=TEST_OPERATOR_HEAD,
            frozen_manifest_sha256="0" * 64,
        )

    acquire_mock.assert_not_called()


def test_missing_expected_head_refuses():
    """Verify --expected-head is strictly required with no default."""
    with pytest.raises(ReadinessSessionRefused, match="expected_head is required"):
        verify_repository_state(expected_head="")

    # CLI parser exits when --expected-head is omitted
    with pytest.raises(SystemExit):
        main(["--client", "client.json", "--evidence-dir", "ev", "--execute-live-readiness", "--confirmation", LIVE_READINESS_CONFIRMATION])


def test_confirmation_and_flag_required_before_oauth(tmp_path):
    """Test missing execute flag or invalid confirmation refuses before OAuth."""
    acquire_mock = Mock()

    with pytest.raises(ReadinessSessionRefused, match="execute_live_readiness"):
        run_readiness_session(
            client_path=tmp_path / "client.json",
            evidence_dir=tmp_path / "evidence",
            execute_live_readiness=False,
            readiness_confirmation=LIVE_READINESS_CONFIRMATION,
            expected_head=TEST_OPERATOR_HEAD,
            acquire_token_fn=acquire_mock,
        )

    with pytest.raises(ReadinessSessionRefused, match="confirmation"):
        run_readiness_session(
            client_path=tmp_path / "client.json",
            evidence_dir=tmp_path / "evidence",
            execute_live_readiness=True,
            readiness_confirmation="WRONG_CONFIRMATION",
            expected_head=TEST_OPERATOR_HEAD,
            acquire_token_fn=acquire_mock,
        )

    acquire_mock.assert_not_called()


def test_existing_evidence_dir_refuses_before_oauth(tmp_path):
    """Test existing evidence directory refuses before OAuth."""
    existing_dir = tmp_path / "already-exists"
    existing_dir.mkdir()
    acquire_mock = Mock()

    with pytest.raises(ReadinessSessionRefused, match="already exists"):
        run_readiness_session(
            client_path=tmp_path / "client.json",
            evidence_dir=existing_dir,
            execute_live_readiness=True,
            readiness_confirmation=LIVE_READINESS_CONFIRMATION,
            expected_head=TEST_OPERATOR_HEAD,
            acquire_token_fn=acquire_mock,
        )

    acquire_mock.assert_not_called()


def test_no_spreadsheets_create_and_no_refresh_reissue():
    """Verify that no spreadsheets.create, mutation, or token refresh paths exist."""
    source = inspect.getsource(session_mod)
    assert "spreadsheets.create" not in source
    assert "refresh_token" not in source
    assert "POST /v4/spreadsheets" not in source
    assert "execute_provisioning" not in source
    assert "prepare_paper_append" not in source
    assert "execute_create_once" not in source


def test_make_token_metadata_validation():
    """Verify make_token_metadata validates token type and fields."""
    with pytest.raises(ReadinessSessionRefused, match="invalid token type"):
        make_token_metadata("not-a-token")  # type: ignore

    with pytest.raises(ReadinessSessionRefused, match="invalid bearer"):
        t = PreparedToken(value="valid", expires_at=100.0, clock_uncertainty_seconds=1.0)
        object.__setattr__(t, "value", "")
        make_token_metadata(t)
