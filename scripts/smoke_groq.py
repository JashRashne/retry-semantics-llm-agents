#!/usr/bin/env python3
"""Engineering smoke test only; this is not an experiment run."""

from __future__ import annotations

import argparse
import json
import os

from retry_semantics.models import (
    GroqModelClient,
    ModelCallConfig,
    ToolChoice,
)
from retry_semantics.runtime.original_generation import (
    EligibleOriginalGeneration,
    V1CreateTicketTaskSpec,
    render_v1_create_ticket_task,
    run_v1_original_generation_attempt,
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

    customer_id = "SMOKE-CUST"
    title = "Engineering smoke test"
    description = "Engineering smoke test payload."
    task_spec = V1CreateTicketTaskSpec(
        customer_id=customer_id,
        expected_title=title,
        expected_description=description,
        user_task=render_v1_create_ticket_task(
            customer_id=customer_id,
            expected_title=title,
            expected_description=description,
        ),
    )
    result = run_v1_original_generation_attempt(
        GroqModelClient(timeout_seconds=args.timeout_seconds),
        task_spec=task_spec,
        model_config=ModelCallConfig(
            model=args.model,
            temperature=0.0,
            seed=None,
            max_completion_tokens=256,
            tool_choice=ToolChoice.auto(),
        ),
    )

    response = result.model_response
    usage = None
    if response is not None and response.usage is not None:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
    eligible = isinstance(result, EligibleOriginalGeneration)
    returned_calls = (
        response.assistant_message.tool_calls if response is not None else ()
    )
    summary = {
        "label": "engineering smoke test only; not an experiment run",
        "outcome": "eligible" if eligible else "ineligible",
        "failure_reason": None if eligible else result.reason.value,
        "provider": response.provider if response is not None else "groq",
        "requested_model": (
            response.requested_model if response is not None else args.model
        ),
        "returned_model": response.returned_model if response is not None else None,
        "finish_reason": response.finish_reason if response is not None else None,
        "tool_names": [call.tool_name for call in returned_calls],
        "raw_arguments_json": [call.arguments_json for call in returned_calls],
        "frozen_m_hash": result.original_request_hash if eligible else None,
        "usage": usage,
        "system_fingerprint": (
            response.system_fingerprint if response is not None else None
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
