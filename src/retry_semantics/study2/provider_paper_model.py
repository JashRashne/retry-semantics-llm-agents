"""Frozen GitHub/Razorpay Fireworks original and continuation messages.

The capture/parser is the existing Fireworks boundary. A completion function is
injected for offline tests; the live function is one non-retrying HTTP request.
"""

from __future__ import annotations

import json
import re
import signal
import threading
from typing import Any, Callable

import httpx

from retry_semantics.models.base import ModelResponseError
from retry_semantics.models.fireworks import (
    FIREWORKS_CHAT_COMPLETIONS_URL, capture_fireworks_chat_completion,
)
from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2.provider_paper_io import DurablePaperEvidence


class PaperModelError(ValueError):
    """Model output or frozen model context differs."""


def live_fireworks_completion(api_key: str) -> Callable[[dict], dict]:
    if type(api_key) is not str or re.fullmatch(r"[!-~]+", api_key) is None:
        raise PaperModelError("missing model key")

    def complete(payload: dict) -> dict:
        if threading.current_thread() is not threading.main_thread():
            raise PaperModelError("absolute model deadline requires main thread")
        old_handler = signal.getsignal(signal.SIGALRM)
        if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
            raise PaperModelError("another absolute deadline is active")

        def expired(_signum: int, _frame: object) -> None:
            raise TimeoutError("absolute model deadline")

        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, 60.0)
        try:
            with httpx.Client(timeout=httpx.Timeout(60.0), follow_redirects=False,
                              transport=httpx.HTTPTransport(retries=0),
                              trust_env=False) as client:
                request = client.build_request(
                    "POST", FIREWORKS_CHAT_COMPLETIONS_URL, json=payload,
                    headers={"Authorization": "Bearer " + api_key,
                             "Content-Type": "application/json"})
                response = client.send(request, stream=True)
                try:
                    if response.status_code != 200:
                        raise PaperModelError("model completion failed")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 4_000_000:
                            raise PaperModelError("model response cap exceeded")
                        chunks.append(chunk)
                    return json.loads(b"".join(chunks))
                finally:
                    response.close()
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)

    return complete


class PaperModelSession:
    """One family original, then one isolated history per Regeneration arm."""

    def __init__(self, *, provider: str, family: dict, common: dict,
                 complete: Callable[[dict], dict],
                 evidence: DurablePaperEvidence):
        if provider not in ("github", "razorpay"):
            raise PaperModelError("unknown paper provider")
        self.provider = provider
        self.family = family
        self.common = common
        self.complete = complete
        self.evidence = evidence
        self.original: dict | None = None
        self.messages: list[dict] | None = None
        self.pending_tool_ids: list[str] = []
        self.next_index = 0

    def _call(self, messages: list[dict], phase: str, index: int) -> dict:
        config = self.family["model_config"]
        sampling = config["original_generation" if phase == "original" else "regeneration"]
        if (config["model"]["name"] !=
                "accounts/fireworks/models/deepseek-v4-flash-0731"
                or sampling["tool_choice"] != {"mode": "AUTO", "function_name": None}
                or sampling["parallel_tool_calls"] is not False
                or sampling["provider_parameters"] != {"reasoning_effort": "none"}):
            raise PaperModelError("frozen model configuration changed")
        tools = json.loads(canonical_json_bytes([
            {"type": "function", "function": tool}
            for tool in self.common["tools"]]))
        payload = {
            "model": config["model"]["name"],
            "messages": json.loads(canonical_json_bytes(messages)),
            "tools": tools, "tool_choice": "auto",
            "parallel_tool_calls": False, "temperature": sampling["temperature"],
            "top_p": sampling["top_p"], "seed": sampling["seed"] + index,
            "max_completion_tokens": sampling["max_output_tokens"],
            "reasoning_effort": "none",
        }
        payload_raw = canonical_json_bytes(payload)
        try:
            raw = self.complete(json.loads(payload_raw))
        except Exception as exc:
            self.evidence.event(f"model-failure-{phase}-{index}", {
                "provider": self.provider, "family_id": self.family["family_id"],
                "arm_id": self.evidence.arm_id, "phase": phase,
                "model_call_index": index, "failure_type": type(exc).__name__,
                "payload_sha256": sha256_hex(payload_raw),
            })
            raise PaperModelError("model completion infrastructure failure") from exc
        try:
            captured = capture_fireworks_chat_completion(
                raw, requested_model=payload["model"])
        except ModelResponseError as exc:
            self.evidence.event(f"model-failure-{phase}-{index}", {
                "provider": self.provider, "family_id": self.family["family_id"],
                "arm_id": self.evidence.arm_id, "phase": phase,
                "model_call_index": index,
                "failure_type": "ModelResponseError",
                "raw_response_sha256": sha256_hex(canonical_json_bytes(raw)),
                "raw_response_hex": canonical_json_bytes(raw).hex(),
            })
            raise PaperModelError("model response structure failure") from exc
        assistant = captured.assistant_message
        value = {
            "role": "assistant", "content": assistant.content,
            "tool_calls": [{"id": call.tool_call_id, "type": "function",
                            "function": {"name": call.tool_name,
                                         "arguments": call.arguments_json}}
                           for call in assistant.tool_calls],
        }
        self.evidence.event(f"model-{phase}-{index}", {
            "schema": "provider-paper-model-evidence-v1",
            "provider": self.provider, "family_id": self.family["family_id"],
            "arm_id": self.evidence.arm_id,
            "phase": phase, "model_call_index": index,
            "messages_tools_sha256": sha256_hex(canonical_json_bytes(
                {"messages": messages, "tools": tools})),
            "payload_sha256": sha256_hex(payload_raw),
            "raw_response_sha256": sha256_hex(canonical_json_bytes(raw)),
            "raw_response_hex": canonical_json_bytes(raw).hex(),
            "assistant_message": value,
        })
        return value

    def generate_original(self) -> dict:
        if self.original is not None:
            raise PaperModelError("original generation slot already consumed")
        messages = [
            {"role": "system", "content": self.common["system_message"]},
            {"role": "user", "content": self.family["user_task"]},
        ]
        value = self._call(messages, "original", 0)
        calls = value["tool_calls"]
        if len(calls) != 1:
            raise PaperModelError("original must select exactly one tool")
        call = calls[0]
        expected = ("create_issue" if self.provider == "github" else "create_order")
        try:
            args = json.loads(call["function"]["arguments"])
        except (ValueError, TypeError) as exc:
            raise PaperModelError("malformed original tool arguments") from exc
        if (call["function"]["name"] != expected
                or args != self.family["target_semantic_m"]):
            raise PaperModelError("original tool action differs from frozen family M")
        self.original = value
        return value

    def begin_regeneration(self) -> None:
        if self.original is None or self.messages is not None:
            raise PaperModelError("invalid Regeneration start")
        self.messages = [
            {"role": "system", "content": self.common["system_message"]},
            {"role": "user", "content": self.family["user_task"]},
            self.original,
            {"role": "tool", "tool_call_id": self.original["tool_calls"][0]["id"],
             "content": self.common["ambiguity_text"]},
        ]

    def next_actions(self, context: dict) -> tuple[tuple[str, dict], ...]:
        if (self.messages is None or context["model_call_index"] != self.next_index
                or context["seed"] !=
                self.family["model_config"]["regeneration"]["seed"] + self.next_index):
            raise PaperModelError("model continuation index or seed changed")
        previous = context["previous_tool_result"]
        if self.next_index == 0:
            if previous is not None:
                raise PaperModelError("unexpected initial tool result")
        else:
            if not self.pending_tool_ids:
                raise PaperModelError("missing prior tool call")
            results = previous if type(previous) is list else [previous]
            if len(results) != len(self.pending_tool_ids):
                raise PaperModelError("prior tool result count changed")
            for tool_id, item in zip(self.pending_tool_ids, results):
                if type(item) not in (dict, str):
                    raise PaperModelError("invalid prior tool result")
                self.messages.append({
                    "role": "tool", "tool_call_id": tool_id,
                    "content": (canonical_json_bytes(item).decode("utf-8")
                                if type(item) is dict else item),
                })
            self.pending_tool_ids = []
        value = self._call(self.messages, "regeneration", self.next_index)
        self.messages.append(value)
        self.next_index += 1
        calls = value["tool_calls"]
        if not calls:
            return ()
        if len({call["id"] for call in calls}) != len(calls):
            return (("invalid_output", {}),)
        self.pending_tool_ids = [call["id"] for call in calls]
        actions = []
        for call in calls:
            try:
                args = json.loads(call["function"]["arguments"])
            except (ValueError, TypeError):
                actions.append(("invalid_action", {}))
                continue
            if type(args) is not dict:
                actions.append(("invalid_action", {}))
                continue
            actions.append((call["function"]["name"], args))
        return tuple(actions)

    def next_action(self, context: dict) -> tuple[str, dict]:
        """Compatibility helper for single-call offline checks."""
        actions = self.next_actions(context)
        if not actions:
            return "finish", {}
        if len(actions) != 1:
            raise PaperModelError("multiple actions require batch runtime")
        return actions[0]
