"""CLI operator to capture and qualify GitHub Study-2 live readiness.

Requires explicit --execute-live-readiness flag, clean git checkout,
and valid provider/model credentials.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

from retry_semantics.study2.provider_paper_model import live_fireworks_completion
from retry_semantics.study2.github_live_readiness import capture_github_readiness
from retry_semantics.study2.github_paper_manifest import (
    load_github_paper_manifest,
    load_namespace_registry as load_github_namespace_registry,
)
from retry_semantics.study2.provider_paper_io import PaperRequest, one_shot_http
from retry_semantics.study2.provider_paper_readiness import (
    PROVIDER_CONTROLS,
    current_static_identity,
)


def _check_clean_git(root: Path) -> None:
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root, capture_output=True, check=True, text=True,
    ).stdout.strip()
    if Path(top).resolve() != root.resolve():
        raise SystemExit("Must be executed from repository root")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--ignore-submodules=all"],
        cwd=root, capture_output=True, check=True, text=True,
    ).stdout.strip()
    if status:
        raise SystemExit(f"Working tree is not clean:\n{status}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-live-readiness", action="store_true", required=True,
                        help="Explicit operator authorization for live provider qualification")
    parser.add_argument("--evidence-dir", type=Path, required=True,
                        help="Target directory for captured readiness evidence")
    parser.add_argument("--github-token", type=str, default=os.environ.get("GITHUB_TOKEN", ""),
                        help="GitHub Personal Access Token or fine-grained token")
    parser.add_argument("--fireworks-api-key", type=str, default=os.environ.get("FIREWORKS_API_KEY", ""),
                        help="Fireworks API Key for model capability qualification")
    parser.add_argument("--operator-id", type=str, default=os.environ.get("USER", "operator"),
                        help="Operator username or identifier for access inventory attestation")
    parser.add_argument("--api-version", type=str, default="2022-11-28",
                        help="Target GitHub API version header")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    _check_clean_git(root)

    if not args.github_token:
        raise SystemExit("Missing --github-token or GITHUB_TOKEN environment variable")
    if not args.fireworks_api_key:
        raise SystemExit("Missing --fireworks-api-key or FIREWORKS_API_KEY environment variable")

    manifest = load_github_paper_manifest(root=root).as_json()
    registry = load_github_namespace_registry(root=root).as_json()
    identity = current_static_identity("github", root=root)

    def http_send(req: PaperRequest):
        return one_shot_http(req, credential=args.github_token)

    def model_complete(model_name: str, tools: tuple[dict, ...], sampling: dict):
        payload = {
            "model": model_name,
            "tools": [{"type": "function", "function": tool} for tool in tools],
            "tool_choice": "auto", "parallel_tool_calls": False,
            "temperature": sampling["temperature"], "top_p": sampling["top_p"],
            "seed": sampling["seed"],
            "max_completion_tokens": sampling["max_output_tokens"],
            "reasoning_effort": "none",
            "messages": [{"role": "user", "content":
                          "Please create a new GitHub issue titled 'Test' with body 'Test body'."}],
        }
        return live_fireworks_completion(args.fireworks_api_key)(payload)

    print(f"[*] Starting GitHub live readiness qualification for repo: {manifest['selected_repository']}")
    hashes = capture_github_readiness(
        manifest=manifest,
        registry=registry,
        evidence_dir=args.evidence_dir,
        identity=identity,
        operator_id=args.operator_id,
        api_version=args.api_version,
        http_send=http_send,
        model_complete=model_complete,
    )

    print(f"[+] All 7 GitHub readiness controls successfully qualified and verified:")
    for ctrl in PROVIDER_CONTROLS["github"]:
        print(f"  - {ctrl}: {hashes[ctrl]}")
    print(f"[*] Evidence written to: {args.evidence_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
