"""CLI operator to capture and qualify Razorpay Study-2 live readiness.

Requires explicit --execute-live-readiness flag, clean git checkout,
and valid provider/model credentials in Test Mode.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

from retry_semantics.study2.provider_paper_model import live_fireworks_completion
from retry_semantics.study2.razorpay_live_readiness import capture_razorpay_readiness
from retry_semantics.study2.razorpay_paper_manifest import (
    load_razorpay_paper_manifest,
    load_namespace_registry as load_razorpay_namespace_registry,
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
    parser.add_argument("--razorpay-key-id", type=str, default=os.environ.get("RAZORPAY_KEY_ID", ""),
                        help="Razorpay Test Mode Key ID (rzp_test_...)")
    parser.add_argument("--razorpay-key-secret", type=str, default=os.environ.get("RAZORPAY_KEY_SECRET", ""),
                        help="Razorpay Test Mode Key Secret")
    parser.add_argument("--fireworks-api-key", type=str, default=os.environ.get("FIREWORKS_API_KEY", ""),
                        help="Fireworks API Key for model capability qualification")
    parser.add_argument("--operator-id", type=str, default=os.environ.get("USER", "operator"),
                        help="Operator username or identifier for access inventory attestation")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    _check_clean_git(root)

    if not args.razorpay_key_id or not args.razorpay_key_secret:
        raise SystemExit("Missing --razorpay-key-id and --razorpay-key-secret (or RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET env vars)")
    if not args.fireworks_api_key:
        raise SystemExit("Missing --fireworks-api-key or FIREWORKS_API_KEY environment variable")

    credential = f"{args.razorpay_key_id}:{args.razorpay_key_secret}"
    manifest = load_razorpay_paper_manifest(root=root)
    registry = load_razorpay_namespace_registry(root=root)
    identity = current_static_identity("razorpay", root=root)

    def http_send(req: PaperRequest):
        return one_shot_http(req, credential=credential)

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
                          "Please create an order with amount 200 and currency 'INR'."}],
        }
        return live_fireworks_completion(args.fireworks_api_key)(payload)

    print(f"[*] Starting Razorpay live readiness qualification for scope: {manifest['credential_scope_fingerprint']}")
    hashes = capture_razorpay_readiness(
        manifest=manifest,
        registry=registry,
        evidence_dir=args.evidence_dir,
        identity=identity,
        operator_id=args.operator_id,
        http_send=http_send,
        model_complete=model_complete,
    )

    print(f"[+] All 7 Razorpay readiness controls successfully qualified and verified:")
    for ctrl in PROVIDER_CONTROLS["razorpay"]:
        print(f"  - {ctrl}: {hashes[ctrl]}")
    print(f"[*] Evidence written to: {args.evidence_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
