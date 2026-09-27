"""Prospective Google Sheets Study-2 paper live readiness session operator.

Acquires exactly one fresh resident PreparedToken using the audited drive.file
Desktop OAuth flow and invokes frozen run_capture() in the same process.
An explicit dynamic-authority run writes the same bearer to a new owner-only
file outside the repository for the later, separately authorized primary.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_sheets_paper_live_readiness as live_readiness
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.sheets_live_preparation import PreparedToken
from retry_semantics.study2.sheets_paper_materialize import (
    MANIFEST_PATH,
    load_paper_manifest,
)
from retry_semantics.study2.sheets_paper_registry import REPOSITORY_ROOT
from retry_semantics.study2 import sheets_phase3_credentials as credentials
from retry_semantics.study2 import sheets_phase4_setup as setup

FROZEN_RUNTIME_HEAD = "f002fdfa3e17a168ce5fef2ccdcee9af386fc17a"
FROZEN_MANIFEST_SHA256 = (
    "7c9bddb797938e026344afe49650922219ca35febf9322bdfb62f402caa87991"
)
LIVE_READINESS_CONFIRMATION = "EXPLICIT_SHEETS_PAPER_LIVE_READINESS"

preflight_capture = live_readiness.preflight_capture
run_capture = live_readiness.run_capture


class ReadinessSessionRefused(ValueError):
    """Operator input, git state, or OAuth acquisition violates protocol."""


def _git(*args: str, root: Path = REPOSITORY_ROOT) -> bytes:
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", *args],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return result.stdout


def verify_repository_state(
    *,
    expected_head: str,
    root: Path = REPOSITORY_ROOT,
    frozen_runtime_head: str = FROZEN_RUNTIME_HEAD,
    frozen_manifest_sha256: str = FROZEN_MANIFEST_SHA256,
) -> None:
    """Verify repository HEAD, working tree cleanliness, ancestry, and manifest before OAuth."""
    if not expected_head or type(expected_head) is not str:
        raise ReadinessSessionRefused("expected_head is required")
    try:
        current_head = _git("rev-parse", "HEAD", root=root).decode("utf-8").strip()
        if current_head != expected_head:
            raise ReadinessSessionRefused(
                f"repository HEAD ({current_head}) does not match expected ({expected_head})"
            )
        top_level = _git("rev-parse", "--show-toplevel", root=root).decode("utf-8").strip()
        if Path(top_level).resolve() != root.resolve():
            raise ReadinessSessionRefused("not executing from repository root")
        status = _git("status", "--porcelain", "--ignore-submodules=all", root=root)
        if status.strip():
            raise ReadinessSessionRefused("repository working tree is dirty")
        try:
            _git("merge-base", "--is-ancestor", frozen_runtime_head, current_head, root=root)
        except subprocess.CalledProcessError as exc:
            raise ReadinessSessionRefused(
                f"frozen runtime checkpoint ({frozen_runtime_head}) is not an ancestor of HEAD ({current_head})"
            ) from exc
    except Exception as exc:
        if isinstance(exc, ReadinessSessionRefused):
            raise
        raise ReadinessSessionRefused(f"git check failed: {exc}") from exc

    manifest_bytes = (root / MANIFEST_PATH).read_bytes()
    manifest_sha = sha256_hex(manifest_bytes)
    manifest = load_paper_manifest(root=root)
    # The pending manifest's fixed digest changes when its audited status is
    # frozen. A clean committed, independently frozen and regenerated manifest
    # is the authority for that later state.
    if manifest_sha != frozen_manifest_sha256:
        raise ReadinessSessionRefused(
            f"frozen manifest SHA ({manifest_sha}) does not match expected ({frozen_manifest_sha256})"
        )
    if manifest.get("status") != "FROZEN_INDEPENDENT_HOSTILE_AUDIT_PASSED":
        raise ReadinessSessionRefused("Sheets paper manifest is pending independent audit")


def acquire_resident_token(
    client_path: Path,
    *,
    present_url: Callable[[str], None] | None = None,
    account_alias: str = "operator",
    consent_seconds: float = 300.0,
    exchange_timeout_seconds: float = 30.0,
    clock_uncertainty_seconds: float = 1.0,
) -> PreparedToken:
    """Acquire fresh PreparedToken using audited drive.file desktop OAuth flow."""
    token, _ = acquire_session_authority(
        client_path, present_url=present_url, account_alias=account_alias,
        consent_seconds=consent_seconds,
        exchange_timeout_seconds=exchange_timeout_seconds,
        clock_uncertainty_seconds=clock_uncertainty_seconds)
    return token


def acquire_session_authority(
    client_path: Path, *, present_url: Callable[[str], None] | None = None,
    account_alias: str = "operator", consent_seconds: float = 300.0,
    exchange_timeout_seconds: float = 30.0,
    clock_uncertainty_seconds: float = 1.0,
) -> tuple[PreparedToken, credentials.AcquisitionMetadata]:
    """Retain nonsecret acquisition authority for the same resident bearer."""
    if present_url is None:
        present_url = lambda url: print(url, flush=True)
    review = setup.review_client(client_path)
    client_config = setup.load_client_config(
        client_path, reviewed_public_hash=review["public_sha256"]
    )
    preparer = credentials.DesktopPreparer(client_config)
    token, metadata = preparer.acquire(
        operator_confirmation=credentials.ACQUISITION_CONFIRMATION,
        present_url=present_url,
        account_alias=account_alias,
        clock_uncertainty_seconds=clock_uncertainty_seconds,
        consent_seconds=consent_seconds,
        exchange_timeout_seconds=exchange_timeout_seconds,
    )
    if (type(token) is not PreparedToken
            or type(metadata) is not credentials.AcquisitionMetadata
            or metadata.public_config_sha256 != review["public_sha256"]
            or token.expires_at != metadata.expires_at):
        raise ReadinessSessionRefused("OAuth acquisition authority differs")
    return token, metadata


def make_token_metadata(token: PreparedToken) -> dict[str, Any]:
    """Construct nonsecret metadata expected by preflight_capture."""
    if type(token) is not PreparedToken:
        raise ReadinessSessionRefused("invalid token type")
    if type(token.value) is not str or not token.value:
        raise ReadinessSessionRefused("invalid bearer value")
    return {
        "schema": "sheets-paper-prepared-token-v1",
        "bearer_sha256": sha256_hex(token.value.encode("utf-8")),
        "expires_at": token.expires_at,
        "clock_uncertainty_seconds": token.clock_uncertainty_seconds,
    }


def run_readiness_session(
    *,
    client_path: Path,
    evidence_dir: Path,
    execute_live_readiness: bool,
    readiness_confirmation: str,
    expected_head: str,
    root: Path = REPOSITORY_ROOT,
    acquire_token_fn: Callable[..., PreparedToken] | None = None,
    run_capture_fn: Callable[..., str] | None = None,
    present_url: Callable[[str], None] | None = None,
    capture_dynamic_authority: bool = False,
    acquire_authority_fn: Callable[..., tuple[PreparedToken, credentials.AcquisitionMetadata]] | None = None,
    drive_get_fn: Callable[..., Any] | None = None,
    bearer_file: Path | None = None,
) -> str:
    """Execute live readiness session: verify repo, acquire token into memory, run capture."""
    if execute_live_readiness is not True:
        raise ReadinessSessionRefused("execute_live_readiness flag must be True")
    if readiness_confirmation != LIVE_READINESS_CONFIRMATION:
        raise ReadinessSessionRefused("invalid readiness confirmation")
    if evidence_dir.exists():
        raise ReadinessSessionRefused(f"evidence directory already exists: {evidence_dir}")
    if capture_dynamic_authority:
        if bearer_file is None:
            raise ReadinessSessionRefused("external bearer_file is required for later primary")
        target = bearer_file.resolve(strict=False)
        if (target == root.resolve() or root.resolve() in target.parents
                or bearer_file.exists() or bearer_file.is_symlink()
                or not bearer_file.parent.is_dir()):
            raise ReadinessSessionRefused("bearer file must be new and outside repository")

    # 1. Refuse before OAuth if HEAD differs, repo is dirty, ancestor check fails, or manifest SHA differs
    verify_repository_state(expected_head=expected_head, root=root)

    # 2. Acquire exactly one fresh resident PreparedToken; never persist bearer
    if acquire_token_fn is None:
        acquire_token_fn = acquire_resident_token
    if run_capture_fn is None:
        run_capture_fn = run_capture

    token: PreparedToken | None = None
    try:
        metadata = None
        if capture_dynamic_authority:
            if acquire_authority_fn is None:
                acquire_authority_fn = acquire_session_authority
            token, metadata = acquire_authority_fn(client_path, present_url=present_url)
        else:
            token = acquire_token_fn(client_path, present_url=present_url)
        if type(token) is not PreparedToken:
            raise ReadinessSessionRefused("acquired token is not PreparedToken")

        # 3. Construct readiness metadata directly from resident token
        token_metadata = make_token_metadata(token)
        manifest = load_paper_manifest(root=root)

        # 4. Check schedule coverage before dispatch
        preflight_capture(
            manifest=manifest,
            token_metadata=token_metadata,
            bearer=token.value,
            now=time.time(),
        )

        # 5. Invoke frozen run_capture in the same process with resident bearer
        state = run_capture_fn(
            manifest=manifest,
            bearer=token.value,
            evidence_dir=evidence_dir,
            token_metadata=token_metadata,
        )
        if capture_dynamic_authority:
            # The same in-memory bearer that read every readiness baseline now
            # proves its Drive principal and sole-owner file access.
            import run_sheets_paper_append_qualification_session as qualification
            if drive_get_fn is None:
                drive_get_fn = qualification.drive_get_once
            principal, inventory_hash, _ = qualification._drive_evidence(
                evidence_dir=evidence_dir, paper_id=manifest["spreadsheet_id"],
                bearer=token.value, drive_get=drive_get_fn)
            review = setup.review_client(client_path)
            if (type(metadata) is not credentials.AcquisitionMetadata
                    or metadata.public_config_sha256 != review["public_sha256"]
                    or metadata.expires_at != token.expires_at
                    or state != "READINESS_CAPTURED_PENDING_INDEPENDENT_AUDIT"):
                raise ReadinessSessionRefused("dynamic session authority differs")
            dynamic = {
                "schema": "sheets-paper-dynamic-session-v1",
                "client_id": review["public"]["client_id"],
                "public_config_sha256": review["public_sha256"],
                "acquisition": metadata.projection(),
                "token_metadata": token_metadata,
                "principal": principal,
                "permission_inventory_sha256": inventory_hash,
                "capture_plan_sha256": sha256_hex((evidence_dir / "capture-plan.json").read_bytes()),
                "capture_state_sha256": sha256_hex((evidence_dir / "capture-state.json").read_bytes()),
            }
            with (evidence_dir / "dynamic-session.json").open("xb") as output:
                output.write(canonical_json_bytes(dynamic))
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(bearer_file, flags, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(token.value.encode("utf-8"))
                output.flush()
                os.fsync(output.fileno())
        return state
    finally:
        token = None  # Best-effort resident cleanup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Google Sheets Study-2 Paper Live Readiness Session"
    )
    parser.add_argument(
        "--client",
        type=Path,
        required=True,
        help="Google Desktop OAuth client credentials JSON",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        required=True,
        help="New evidence directory path",
    )
    parser.add_argument(
        "--execute-live-readiness",
        action="store_true",
        required=True,
        help="Explicit live readiness execute flag",
    )
    parser.add_argument(
        "--confirmation",
        required=True,
        help="Explicit live readiness confirmation string",
    )
    parser.add_argument(
        "--expected-head",
        required=True,
        help="Expected repository commit HEAD (audited operator-bridge commit)",
    )
    parser.add_argument("--capture-dynamic-authority", action="store_true",
                        help="Capture same-bearer Drive principal and ACL evidence")
    parser.add_argument("--bearer-file", type=Path,
                        help="New owner-only bearer file outside the repository for later primary")

    args = parser.parse_args(argv)
    try:
        state = run_readiness_session(
            client_path=args.client,
            evidence_dir=args.evidence_dir,
            execute_live_readiness=args.execute_live_readiness,
            readiness_confirmation=args.confirmation,
            expected_head=args.expected_head,
            capture_dynamic_authority=args.capture_dynamic_authority,
            bearer_file=args.bearer_file,
        )
        print(state)
        return 0
    except Exception as exc:
        print(f"Readiness session refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
