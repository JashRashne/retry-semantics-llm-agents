#!/usr/bin/env python3
"""Engineering smoke test only; this is not an experiment run."""

from __future__ import annotations

import argparse
import json
import os

from retry_semantics.models import (
    GroqModelClient,
    ModelCallConfig,
    ModelRequest,
    ToolChoice,
)
from retry_semantics.runtime.regeneration_context import (
    FROZEN_SYSTEM_MESSAGE,
    FROZEN_TOOL_CATALOG,
    CanonicalContextMessage,
)

ENGINEERING_DEFAULT_MODEL = "openai/gpt-oss-20b"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Engineering smoke test only; not an experiment run."
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GROQ_SMOKE_MODEL", ENGINEERING_DEFAULT_MODEL),
        help=(
            "Groq model ID. The default is only an engineering convenience and "
            "is not a frozen experimental model."
        ),
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if not os.environ.get("GROQ_API_KEY", "").strip():
        print(
            "GROQ_API_KEY is required. Set it in the environment and invoke "
            "this engineering smoke test manually."
        )
        return 2

    messages = (
        CanonicalContextMessage(
            role="system",
            content=FROZEN_SYSTEM_MESSAGE,
            tool_calls=(),
            tool_call_id=None,
        ),
        CanonicalContextMessage(
            role="user",
            content=(
                'Create exactly one support ticket for customer "SMOKE-CUST" '
                'with title "Engineering smoke test" and description '
                '"Engineering smoke test payload.".'
            ),
            tool_calls=(),
            tool_call_id=None,
        ),
    )
    request = ModelRequest(
        messages=messages,
        tools=FROZEN_TOOL_CATALOG,
        model_config=ModelCallConfig(
            model=args.model,
            temperature=0.0,
            seed=None,
            max_completion_tokens=256,
            tool_choice=ToolChoice.required(),
        ),
    )

    response = GroqModelClient(timeout_seconds=args.timeout_seconds).complete(request)
    usage = None
    if response.usage is not None:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
    summary = {
        "label": "engineering smoke test only; not an experiment run",
        "provider": response.provider,
        "requested_model": response.requested_model,
        "returned_model": response.returned_model,
        "finish_reason": response.finish_reason,
        "tool_names": [
            call.tool_name for call in response.assistant_message.tool_calls
        ],
        "raw_arguments": [
            call.arguments_json for call in response.assistant_message.tool_calls
        ],
        "usage": usage,
        "system_fingerprint": response.system_fingerprint,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
