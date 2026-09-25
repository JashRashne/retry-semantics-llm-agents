"""Prospective Google Sheets Study-2 paper live readiness session operator.

Acquires exactly one fresh resident PreparedToken using the audited drive.file
Desktop OAuth flow, keeps the bearer only in resident process memory, and
invokes the frozen run_capture() directly in the same process.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_sheets_paper_live_readiness as live_readiness
from retry_semantics.serialization import sha256_hex
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
    "5b6f273f248539684695ceb4cf81ecc71dc0c179a0fc94f73cd755914b315c27"
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
    if manifest_sha != frozen_manifest_sha256:
        raise ReadinessSessionRefused(
            f"frozen manifest SHA ({manifest_sha}) does not match expected ({frozen_manifest_sha256})"
        )


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
    if present_url is None:
        present_url = lambda url: print(url, flush=True)
    review = setup.review_client(client_path)
    client_config = setup.load_client_config(
        client_path, reviewed_public_hash=review["public_sha256"]
    )
    preparer = credentials.DesktopPreparer(client_config)
    token, _metadata = preparer.acquire(
        operator_confirmation=credentials.ACQUISITION_CONFIRMATION,
        present_url=present_url,
        account_alias=account_alias,
        clock_uncertainty_seconds=clock_uncertainty_seconds,
        consent_seconds=consent_seconds,
        exchange_timeout_seconds=exchange_timeout_seconds,
    )
    if type(token) is not PreparedToken:
        raise ReadinessSessionRefused("OAuth acquisition did not return PreparedToken")
    return token


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
) -> str:
    """Execute live readiness session: verify repo, acquire token into memory, run capture."""
    if execute_live_readiness is not True:
        raise ReadinessSessionRefused("execute_live_readiness flag must be True")
    if readiness_confirmation != LIVE_READINESS_CONFIRMATION:
        raise ReadinessSessionRefused("invalid readiness confirmation")
    if evidence_dir.exists():
        raise ReadinessSessionRefused(f"evidence directory already exists: {evidence_dir}")

    # 1. Refuse before OAuth if HEAD differs, repo is dirty, ancestor check fails, or manifest SHA differs
    verify_repository_state(expected_head=expected_head, root=root)

    # 2. Acquire exactly one fresh resident PreparedToken; never persist bearer
    if acquire_token_fn is None:
        acquire_token_fn = acquire_resident_token
    if run_capture_fn is None:
        run_capture_fn = run_capture

    token: PreparedToken | None = None
    try:
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

    args = parser.parse_args(argv)
    try:
        state = run_readiness_session(
            client_path=args.client,
            evidence_dir=args.evidence_dir,
            execute_live_readiness=args.execute_live_readiness,
            readiness_confirmation=args.confirmation,
            expected_head=args.expected_head,
        )
        print(state)
        return 0
    except Exception as exc:
        print(f"Readiness session refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
