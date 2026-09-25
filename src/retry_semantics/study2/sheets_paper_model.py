"""One-shot Fireworks continuation for the exact Sheets paper tool schema.

No import-time request. The caller supplies a prepared API key and later
invokes this only after collection authorization. Unlike the generic ticket
adapter, this keeps the frozen Sheets tool JSON (including ASCII patterns)
byte-for-byte at the schema level. No retries, redirects, or environment proxy.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from retry_semantics.models.base import ModelResponseError
from retry_semantics.models.fireworks import (
    FIREWORKS_CHAT_COMPLETIONS_URL, capture_fireworks_chat_completion,
)
from retry_semantics.serialization import canonical_json_bytes
from retry_semantics.study2.sheets_paper_materialize import _parse
from retry_semantics.study2.sheets_paper_runner import (
    ModelDecision, PaperRunnerError, RecoveryContext,
)


class SheetsModelError(PaperRunnerError):
    """Configured Sheets model call or response is invalid/incomplete."""


def _original_message(raw: bytes, intended: dict[str, str]) -> dict[str, Any]:
    try:
        value = _parse(raw)
        if (canonical_json_bytes(value) != raw or type(value) is not dict
                or set(value) != {"role", "content", "tool_calls"}
                or value["role"] != "assistant"
                or value["content"] is not None and type(value["content"]) is not str
                or type(value["tool_calls"]) is not list or len(value["tool_calls"]) != 1):
            raise SheetsModelError("invalid frozen original assistant message")
        call = value["tool_calls"][0]
        if (type(call) is not dict or set(call) != {"id", "type", "function"}
                or type(call["id"]) is not str or not call["id"]
                or call["type"] != "function" or type(call["function"]) is not dict
                or set(call["function"]) != {"name", "arguments"}
                or call["function"]["name"] != "append_row"
                or type(call["function"]["arguments"]) is not str
                or _parse(call["function"]["arguments"].encode("utf-8")) != intended):
            raise SheetsModelError("original M is not the sole intended append")
        return value
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise SheetsModelError("invalid frozen original assistant message") from exc


class SheetsFireworksContinuation:
    """Stateful exact-history model callback for `run_recovery`."""

    def __init__(self, *, api_key: str, intended: dict[str, str],
                 timeout_seconds: float = 30.0,
                 transport: httpx.BaseTransport | None = None):
        if type(api_key) is not str or not api_key or type(intended) is not dict:
            raise SheetsModelError("missing configured model identity")
        self._intended = intended
        self._messages: list[dict[str, Any]] | None = None
        self._pending_tool_id: str | None = None
        self._next_index = 0
        self._original_bytes: bytes | None = None
        self._client = httpx.Client(
            headers={"Authorization": "Bearer " + api_key,
                     "Content-Type": "application/json"},
            timeout=httpx.Timeout(timeout_seconds), follow_redirects=False,
            transport=httpx.HTTPTransport(retries=0) if transport is None else transport,
            trust_env=False)

    def close(self) -> None:
        self._client.close()

    def __call__(self, context: RecoveryContext) -> ModelDecision:
        if type(context) is not RecoveryContext or context.model_call_index != self._next_index:
            raise SheetsModelError("out-of-order model continuation")
        original = _original_message(context.original_model_message, self._intended)
        if self._messages is None:
            self._original_bytes = context.original_model_message
            call_id = original["tool_calls"][0]["id"]
            self._messages = [
                {"role": "system", "content": context.system_message},
                {"role": "user", "content": context.user_task},
                original,
                {"role": "tool", "tool_call_id": call_id,
                 "content": context.ambiguous_observation},
            ]
            if context.previous_tool_result is not None:
                raise SheetsModelError("unexpected first-call tool result")
        else:
            if context.original_model_message != self._original_bytes or self._pending_tool_id is None:
                raise SheetsModelError("model history diverged")
            previous = context.previous_tool_result
            if type(previous) is dict:
                content = canonical_json_bytes(previous).decode("utf-8")
            elif type(previous) is str:
                content = previous
            else:
                raise SheetsModelError("missing prior tool result")
            self._messages.append({"role": "tool", "tool_call_id": self._pending_tool_id,
                                   "content": content})
            self._pending_tool_id = None
        config = context.model_config["regeneration"]
        if (context.seed != config["seed"] + self._next_index
                or config["tool_choice"] != {"mode": "AUTO", "function_name": None}
                or config["parallel_tool_calls"] is not False
                or config["provider_parameters"] != {"reasoning_effort": "none"}):
            raise SheetsModelError("configured model continuation changed")
        payload = {
            "model": context.model_config["model"]["name"],
            "messages": self._messages,
            "tools": [{"type": "function", "function": tool} for tool in context.tools],
            "tool_choice": "auto", "parallel_tool_calls": False,
            "temperature": config["temperature"], "top_p": config["top_p"],
            "seed": context.seed, "max_completion_tokens": config["max_output_tokens"],
            "reasoning_effort": "none",
        }
        try:
            response = self._client.post(FIREWORKS_CHAT_COMPLETIONS_URL, json=payload)
            if response.status_code != 200:
                raise SheetsModelError("model provider returned non-200")
            captured = capture_fireworks_chat_completion(
                response.json(), requested_model=payload["model"])
        except (httpx.HTTPError, json.JSONDecodeError, ModelResponseError, ValueError) as exc:
            raise SheetsModelError("model provider call failed or was malformed") from exc
        assistant = captured.assistant_message
        calls = assistant.tool_calls
        self._messages.append({
            "role": "assistant", "content": assistant.content,
            "tool_calls": [{"id": c.tool_call_id, "type": "function",
                            "function": {"name": c.tool_name,
                                         "arguments": c.arguments_json}} for c in calls]})
        self._next_index += 1
        if not calls:
            return ModelDecision("finish")
        if len(calls) != 1:
            raise SheetsModelError("multiple model tool calls")
        call = calls[0]
        if type(call.tool_call_id) is not str or not call.tool_call_id:
            raise SheetsModelError("invalid model tool-call ID")
        try:
            args = _parse(call.arguments_json.encode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise SheetsModelError("invalid model tool arguments") from exc
        self._pending_tool_id = call.tool_call_id
        if call.tool_name == "append_row" and type(args) is dict and set(args) == {"item", "detail"}:
            return ModelDecision("append_row", args["item"], args["detail"])
        if call.tool_name == "list_rows" and args == {}:
            return ModelDecision("list_rows")
        raise SheetsModelError("model selected invalid Sheets tool action")
