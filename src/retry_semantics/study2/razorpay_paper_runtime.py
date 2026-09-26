"""Razorpay paper request and evidence rules, with injected effects only.

The engineering adapter cannot serialize changed Regeneration arguments; this
paper boundary does so without inserting a receipt or an idempotency key.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

from retry_semantics.serialization import canonical_json_bytes, sha256_hex

ORIGIN = "https://api.razorpay.com"
PATH = "/v1/orders"
OBSERVATION_STARTS = (0, 200)
OBSERVATION_DEADLINES = (170, 370)
TERMINAL_DEADLINE = 470
D = 1020
PAGE_CAP = 5
PAGE_SIZE = 100
AMBIGUITY = "ToolError: The previous request timed out. Its outcome is unknown."
_MARKER = re.compile(r"study2_[A-Za-z0-9_-]{1,56}\Z")
_ORDER_ID = re.compile(r"order_[A-Za-z0-9]+\Z")
_HASH64 = re.compile(r"[0-9a-f]{64}\Z")


class RazorpayPaperError(ValueError):
    """Malformed paper input or missing provider evidence."""


@dataclass(frozen=True, slots=True)
class FrozenOrderRequest:
    method: str
    url: str
    body: bytes
    marker: str
    scope_fingerprint: str
    arm_id: str

    @property
    def sha256(self) -> str:
        return sha256_hex(canonical_json_bytes({
            "method": self.method, "url": self.url, "body_hex": self.body.hex(),
            "marker": self.marker, "scope_fingerprint": self.scope_fingerprint,
            "arm_id": self.arm_id,
        }))


@dataclass(frozen=True, slots=True)
class RawResponse:
    status: int | None
    body: bytes
    transport_error: bool = False


def serialize_create(*, arm_id: str, marker: str, scope_fingerprint: str,
                     amount: int, currency: str) -> FrozenOrderRequest:
    if (type(arm_id) is not str or not arm_id
            or type(marker) is not str or _MARKER.fullmatch(marker) is None
            or type(scope_fingerprint) is not str
            or re.fullmatch(r"[0-9a-f]{64}", scope_fingerprint) is None
            or type(amount) is not int or amount < 1
            or type(currency) is not str
            or re.fullmatch(r"[A-Z]{3}", currency) is None):
        raise RazorpayPaperError("invalid Create Order arguments or scope")
    body = canonical_json_bytes({"amount": amount, "currency": currency,
                                 "notes": {"retry_semantics_marker": marker}})
    return FrozenOrderRequest("POST", ORIGIN + PATH, body, marker,
                              scope_fingerprint, arm_id)


def exact_replay(stored: FrozenOrderRequest, expected: FrozenOrderRequest,
                 dispatch: Callable[[FrozenOrderRequest], RawResponse]) -> RawResponse:
    if type(stored) is not FrozenOrderRequest or stored != expected:
        raise RazorpayPaperError("stored original request changed")
    response = dispatch(stored)
    if type(response) is not RawResponse:
        raise RazorpayPaperError("missing raw dispatch evidence")
    return response


def _decode(raw: bytes) -> Any:
    if type(raw) is not bytes or len(raw) > 4_000_000:
        raise RazorpayPaperError("missing or oversized response")
    try:
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate provider JSON key")
                value[key] = item
            return value
        return json.loads(raw, object_pairs_hook=unique)
    except (UnicodeError, ValueError) as exc:
        raise RazorpayPaperError("malformed response") from exc


@dataclass(frozen=True, slots=True)
class ValidatedOrder:
    order_id: str
    amount: int
    currency: str
    marker: str


def _order(entry: Any, marker: str) -> ValidatedOrder | None:
    if type(entry) is not dict:
        raise RazorpayPaperError("invalid Order object")
    notes = entry.get("notes")
    if (type(entry.get("id")) is not str or _ORDER_ID.fullmatch(entry["id"]) is None
            or entry.get("entity") != "order"
            or type(entry.get("amount")) is not int or entry["amount"] < 1
            or type(entry.get("currency")) is not str
            or re.fullmatch(r"[A-Z]{3}", entry["currency"]) is None):
        raise RazorpayPaperError("invalid Order fields")
    actual_marker = notes.get("retry_semantics_marker") if type(notes) is dict else None
    if actual_marker != marker:
        return None
    if "receipt" not in entry or entry["receipt"] is not None:
        raise RazorpayPaperError("arm Order receipt changed")
    return ValidatedOrder(entry["id"], entry["amount"],
                          entry["currency"], marker)


def validate_ack(request: FrozenOrderRequest,
                 response: RawResponse) -> ValidatedOrder | None:
    if type(response) is not RawResponse or response.transport_error or response.status != 200:
        return None
    try:
        order = _order(_decode(response.body), request.marker)
        sent = _decode(request.body)
    except (RazorpayPaperError, KeyError, TypeError):
        return None
    if (type(sent) is not dict or order is None or order.amount != sent.get("amount")
            or order.currency != sent.get("currency")):
        return None
    return order


@dataclass(frozen=True, slots=True)
class FetchAllRound:
    structurally_complete: bool
    authoritative_completeness_qualified: bool
    orders: tuple[ValidatedOrder, ...]
    pages_requested: int
    reason: str | None
    pagination_instability: bool

    def __post_init__(self) -> None:
        if (self.authoritative_completeness_qualified is not False
                or type(self.pages_requested) is not int
                or not 0 <= self.pages_requested <= PAGE_CAP
                or (self.structurally_complete and self.reason is not None)
                or (not self.structurally_complete and not self.reason)
                or any(type(order) is not ValidatedOrder for order in self.orders)):
            raise RazorpayPaperError("invalid non-authoritative Fetch All evidence")


@dataclass(frozen=True, slots=True)
class ScheduledFetchAll:
    offset_seconds: int
    started_at: float | None
    deadline_at: float
    result: FetchAllRound


@dataclass(frozen=True, slots=True)
class SupplementalGet:
    order_id: str
    started_at: float
    validated_order: ValidatedOrder | None
    http_status: int | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class KnownRecoveryOrder:
    """A recovery Create acknowledgement, never a list-only discovery."""

    order_id: str
    arm_id: str
    request: FrozenOrderRequest
    response: RawResponse
    stage: str


def known_recovery_order(dispatch: LedgerDispatch) -> KnownRecoveryOrder:
    if type(dispatch) is not LedgerDispatch or dispatch.stage != "recovery":
        raise RazorpayPaperError("supplement requires recovery Create")
    order = validate_ack(dispatch.request, dispatch.response)
    if order is None:
        raise RazorpayPaperError("supplement ID lacks acknowledged Create")
    return KnownRecoveryOrder(order.order_id, dispatch.request.arm_id,
                              dispatch.request, dispatch.response, dispatch.stage)


def run_scheduled_observation(*, marker: str, t0: int, r0: float,
                              arm_id: str | None = None,
                              scope_fingerprint: str | None = None,
                              clock: Callable[[], float],
                              wait_until: Callable[[float], None],
                              fetch: Callable[[str], RawResponse],
                              direct_get: Callable[[str], RawResponse],
                              new_post_recovery_known_ids: tuple[KnownRecoveryOrder, ...] = (),
                              decisive_stop: Callable[[tuple[ScheduledFetchAll, ...]], bool] | None = None,
                              ) -> tuple[tuple[ScheduledFetchAll, ...],
                                                    tuple[SupplementalGet, ...]]:
    """OBS-1 +0/+200 and up to three one-shot known-ID supplements."""
    rounds: list[ScheduledFetchAll] = []
    ids: list[str] = []
    for known in new_post_recovery_known_ids:
        if (type(known) is not KnownRecoveryOrder or known.stage != "recovery"
                or arm_id is None or scope_fingerprint is None
                or known.arm_id != arm_id
                or known.arm_id != known.request.arm_id
                or known.request.scope_fingerprint != scope_fingerprint
                or known.request.marker != marker
                or (ack := validate_ack(known.request, known.response)) is None
                or ack.order_id != known.order_id):
            raise RazorpayPaperError("supplement ID lacks independent provenance")
        if known.order_id not in ids:
            ids.append(known.order_id)
    if len(ids) > 3:
        raise RazorpayPaperError("known-ID supplement budget exceeded")
    for offset, deadline in zip(OBSERVATION_STARTS, OBSERVATION_DEADLINES):
        target = r0 + offset
        limit = r0 + deadline
        if clock() < target:
            wait_until(target)
        started = clock()
        if started >= limit:
            result = FetchAllRound(False, False, (), 0, "missed_round", False)
            rounds.append(ScheduledFetchAll(offset, None, limit, result))
        else:
            result = bounded_fetch_all(marker=marker, t0=t0, fetch=fetch,
                                       elapsed=lambda: clock() - target)
            if clock() > limit:
                result = FetchAllRound(False, False, result.orders,
                                       result.pages_requested,
                                       "completion_deadline", result.pagination_instability)
            rounds.append(ScheduledFetchAll(offset, started, limit, result))
        if decisive_stop is not None and decisive_stop(tuple(rounds)):
            return tuple(rounds), ()
    supplements: list[SupplementalGet] = []
    supplement_start = r0 + 370
    if ids and clock() < supplement_start:
        wait_until(supplement_start)
    for order_id in ids:
        started = clock()
        if started >= r0 + TERMINAL_DEADLINE:
            break
        response = direct_get(ORIGIN + PATH + "/" + order_id)
        if type(response) is not RawResponse:
            raise RazorpayPaperError("missing raw direct-GET evidence")
        validated = None
        reason = "failed_known_id_get"
        if (type(response) is RawResponse and not response.transport_error
                and response.status == 200 and clock() <= r0 + TERMINAL_DEADLINE):
            try:
                validated = _order(_decode(response.body), marker)
                if validated is None:
                    reason = "known_id_marker_mismatch"
                elif validated.order_id != order_id:
                    validated = None
                    reason = "known_id_identity_mismatch"
                else:
                    reason = None
            except RazorpayPaperError:
                reason = "malformed_known_id_response"
        elif clock() > r0 + TERMINAL_DEADLINE:
            reason = "late_known_id_get"
        supplements.append(SupplementalGet(
            order_id, started, validated, response.status, reason))
    return tuple(rounds), tuple(supplements)


def window(t0: int) -> tuple[int, int]:
    if type(t0) is not int or t0 < 300:
        raise RazorpayPaperError("invalid activation anchor")
    return t0 - 300, t0 + D + 300


def bounded_fetch_all(*, marker: str, t0: int,
                      fetch: Callable[[str], RawResponse],
                      elapsed: Callable[[], float]) -> FetchAllRound:
    """Five-page structural traversal; even completion has no absence authority."""
    if type(marker) is not str or _MARKER.fullmatch(marker) is None:
        raise RazorpayPaperError("invalid marker")
    start, end = window(t0)
    found: dict[str, ValidatedOrder] = {}
    seen_ids: set[str] = set()
    instability = False
    for page in range(PAGE_CAP):
        if elapsed() > 170:
            return FetchAllRound(False, False, tuple(found.values()), page,
                                 "round_deadline", instability)
        query = urlencode((("count", "100"), ("skip", str(page * 100)),
                           ("from", str(start)), ("to", str(end))))
        response = fetch(ORIGIN + PATH + "?" + query)
        if type(response) is not RawResponse:
            raise RazorpayPaperError("missing raw list response")
        if response.transport_error or response.status != 200 or elapsed() > 170:
            return FetchAllRound(False, False, tuple(found.values()), page + 1,
                                 "failed_or_late_page", instability)
        try:
            value = _decode(response.body)
            if (type(value) is not dict or value.get("entity") != "collection"
                    or type(value.get("items")) is not list
                    or len(value["items"]) > PAGE_SIZE):
                raise RazorpayPaperError("invalid list page")
            for entry in value["items"]:
                order = _order(entry, marker)
                order_id = entry["id"]
                if order_id in seen_ids:
                    instability = True
                seen_ids.add(order_id)
                if order is None:
                    continue
                if order.order_id in found:
                    instability = True
                    if found[order.order_id] != order:
                        raise RazorpayPaperError("Order field drift")
                found[order.order_id] = order
            if len(value["items"]) < PAGE_SIZE:
                return FetchAllRound(not instability, False,
                                     tuple(found.values()), page + 1,
                                     "pagination_instability" if instability else None,
                                     instability)
        except RazorpayPaperError:
            return FetchAllRound(False, False, tuple(found.values()), page + 1,
                                 "malformed_page", instability)
    return FetchAllRound(False, False, tuple(found.values()), PAGE_CAP,
                         "page_cap_without_terminal_page", instability)


@dataclass(frozen=True, slots=True)
class LedgerDispatch:
    request: FrozenOrderRequest
    response: RawResponse
    stage: str


@dataclass(frozen=True, slots=True)
class H1TransportRecord:
    request_sha256: str
    application_dispatches: int
    network_dispatches: int
    automatic_retries: int
    redirect_follows: int
    auth_resends: int
    dispatch_initiated: bool
    local_send_completed: bool
    response_received: bool


@dataclass(frozen=True, slots=True)
class H1ScopeRecord:
    manifest_sha256: str
    selected_scope_fingerprint: str
    readiness_lock_sha256: str
    writer_exclusion_audit_sha256: str
    marker_reserved: bool


@dataclass(frozen=True, slots=True)
class H1Certificate:
    original_request_sha256: str
    arm_id: str
    order_id: str
    original_dispatch: LedgerDispatch
    baseline: FetchAllRound
    positive_rounds: tuple[FetchAllRound, ...]
    scope: H1ScopeRecord
    transport: H1TransportRecord
    direct_known_id_response: RawResponse | None


def certify_h1(*, expected: FrozenOrderRequest,
               original_dispatch: LedgerDispatch, baseline: FetchAllRound,
               positive_rounds: tuple[FetchAllRound, ...],
               scope: H1ScopeRecord, transport: H1TransportRecord,
               direct_known_id_response: RawResponse | None = None) -> H1Certificate:
    """Certify one acknowledged H1 Order from the closed, one-shot ledger.

    The selected scope record must originate from the later audited readiness
    lock; this function also checks its exact request/scope binding.
    """
    if (type(expected) is not FrozenOrderRequest
            or type(original_dispatch) is not LedgerDispatch
            or original_dispatch.stage != "original"
            or original_dispatch.request != expected
            or type(scope) is not H1ScopeRecord
            or type(transport) is not H1TransportRecord
            or type(baseline) is not FetchAllRound
            or type(positive_rounds) is not tuple
            or any(type(row) is not FetchAllRound for row in positive_rounds)
            or scope.selected_scope_fingerprint != expected.scope_fingerprint
            or not scope.marker_reserved
            or any(type(value) is not str or _HASH64.fullmatch(value) is None
                   for value in (scope.manifest_sha256,
                                 scope.readiness_lock_sha256,
                                 scope.writer_exclusion_audit_sha256))
            or transport.request_sha256 != expected.sha256
            or transport.application_dispatches != 1
            or transport.network_dispatches != 1
            or transport.automatic_retries != 0
            or transport.redirect_follows != 0
            or transport.auth_resends != 0
            or transport.dispatch_initiated is not True
            or transport.local_send_completed is not True
            or transport.response_received is not True
            or not baseline.structurally_complete
            or baseline.pagination_instability
            or baseline.orders):
        raise RazorpayPaperError("H1 constructor ledger or scope unqualified")
    ack = validate_ack(expected, original_dispatch.response)
    if ack is None or ack.amount != 200 or ack.currency != "INR":
        raise RazorpayPaperError("H1 original acknowledgement invalid")
    if direct_known_id_response is not None:
        if (type(direct_known_id_response) is not RawResponse
                or direct_known_id_response.transport_error
                or direct_known_id_response.status != 200):
            raise RazorpayPaperError("H1 known-ID validation failed")
        direct = _order(_decode(direct_known_id_response.body), expected.marker)
        if direct != ack:
            raise RazorpayPaperError("H1 direct GET differs from acknowledged ID")
    conclusion = evaluate_ledger(
        arm_id=expected.arm_id, marker=expected.marker,
        dispatches=(original_dispatch,), rounds=positive_rounds,
        original_non_dispatch_certified=False,
        scope_and_writer_history_qualified=True,
        no_hidden_retry_or_redirect=True,
    )
    if (conclusion["status"] != "SUCCESS"
            or conclusion["state_correct"] != 1
            or conclusion.get("exact_set_proof") != "CLOSED_CAUSAL_LEDGER"):
        raise RazorpayPaperError("H1 exact-one Order not certified")
    return H1Certificate(expected.sha256, expected.arm_id, ack.order_id,
                         original_dispatch, baseline, positive_rounds,
                         scope, transport, direct_known_id_response)


def evaluate_ledger(*, arm_id: str, marker: str,
                    dispatches: tuple[LedgerDispatch, ...],
                    rounds: tuple[FetchAllRound, ...],
                    original_non_dispatch_certified: bool,
                    scope_and_writer_history_qualified: bool,
                    no_hidden_retry_or_redirect: bool) -> dict[str, Any]:
    """Closed-ledger exactness; Fetch All zero matches have no negative force."""
    observed = {order.order_id: order for round_ in rounds for order in round_.orders}
    lower_intended = sum(order.amount == 200 and order.currency == "INR"
                         for order in observed.values())
    lower_unintended = len(observed) - lower_intended
    base = {"matching_order_count_lower_bound": lower_intended,
            "unintended_order_count_lower_bound": lower_unintended,
            "authoritative_completeness_qualified": False,
            "exact_set_established": False, "state_correct": None}
    if not scope_and_writer_history_qualified or not no_hidden_retry_or_redirect:
        return {**base, "status": "INCONCLUSIVE", "reason": "scope_or_transport_unqualified"}
    if any(d.request.arm_id != arm_id or d.request.marker != marker
           for d in dispatches):
        return {**base, "status": "INFRASTRUCTURE_FAILURE",
                "reason": "dispatch_scope_mismatch"}
    originals = [d for d in dispatches if d.stage == "original"]
    if original_non_dispatch_certified and originals:
        return {**base, "status": "INFRASTRUCTURE_FAILURE",
                "reason": "H0_original_dispatched"}
    if not original_non_dispatch_certified and len(originals) != 1:
        return {**base, "status": "INCONCLUSIVE", "reason": "original_unproven"}
    acks = [validate_ack(d.request, d.response) for d in dispatches]
    known = [ack for ack in acks if ack is not None]
    ids = [ack.order_id for ack in known]
    if len(ids) != len(set(ids)):
        return {**base, "status": "INFRASTRUCTURE_FAILURE",
                "reason": "acknowledged_id_reused"}
    if any(ack is None for ack in acks):
        return {**base, "status": "INCONCLUSIVE",
                "reason": "unacknowledged_dispatch"}
    if any(order.order_id not in ids for order in observed.values()):
        if len(dispatches) == 1:
            return {**base, "status": "INFRASTRUCTURE_FAILURE",
                    "reason": "one_dispatch_multiple_orders"}
        return {**base, "status": "INCONCLUSIVE",
                "reason": "unlinked_positive_order"}
    if any(observed[id_] != ack for id_, ack in zip(ids, known) if id_ in observed):
        return {**base, "status": "INFRASTRUCTURE_FAILURE",
                "reason": "provider_order_drift"}
    intended = sum(ack.amount == 200 and ack.currency == "INR" for ack in known)
    unintended = len(known) - intended
    defects = []
    if intended == 0:
        defects.append("MISSING_EFFECT")
    if intended > 1:
        defects.append("DUPLICATE_EFFECT")
    if unintended:
        defects.append("WRONG_MUTATION")
    return {**base, "matching_order_count_lower_bound": max(lower_intended, intended),
            "unintended_order_count_lower_bound": max(lower_unintended, unintended),
            "exact_set_established": True, "exact_set_proof": "CLOSED_CAUSAL_LEDGER",
            "status": "FAILURE" if defects else "SUCCESS",
            "state_correct": 0 if defects else 1,
            "reason": ",".join(defects) if defects else "CORRECT"}


@dataclass(frozen=True, slots=True)
class ModelDecision:
    action: str
    amount: int | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    dispatches: tuple[LedgerDispatch, ...]
    model_calls: int
    actions: tuple[str, ...]
    terminal_reason: str


def run_recovery(*, arm_id: str, marker: str, scope_fingerprint: str,
                 policy: str, hidden_world: str, stored_original: FrozenOrderRequest,
                 dispatch: Callable[[FrozenOrderRequest], RawResponse],
                 list_orders: Callable[[], FetchAllRound] | None = None,
                 model_continue: Callable[[dict[str, Any]], ModelDecision | tuple[ModelDecision, ...]] | None = None,
                 should_stop: Callable[[], bool] | None = None,
                 h1_certificate: H1Certificate | None = None,
                 user_task: str = "Create exactly one order for amount 200 in currency INR.",
                 base_seed: int = 0) -> RecoveryResult:
    """One frozen Replay or at most three model-selected actions.

    A live caller must additionally certify baseline, isolation, manifest
    identity, H1 closed ledger, and readiness before invoking this boundary.
    """
    expected = serialize_create(arm_id=arm_id, marker=marker,
                                scope_fingerprint=scope_fingerprint,
                                amount=200, currency="INR")
    if stored_original != expected:
        raise RazorpayPaperError("stored original changed")
    if hidden_world == "H1":
        if type(h1_certificate) is not H1Certificate:
            raise RazorpayPaperError("uncertified H1 original")
        checked = certify_h1(
            expected=expected,
            original_dispatch=h1_certificate.original_dispatch,
            baseline=h1_certificate.baseline,
            positive_rounds=h1_certificate.positive_rounds,
            scope=h1_certificate.scope,
            transport=h1_certificate.transport,
            direct_known_id_response=h1_certificate.direct_known_id_response,
        )
        if checked != h1_certificate:
            raise RazorpayPaperError("H1 certificate changed")
    elif hidden_world != "H0" or h1_certificate is not None:
        raise RazorpayPaperError("invalid world constructor")
    if policy == "EXACT_REPLAY":
        response = exact_replay(stored_original, expected, dispatch)
        return RecoveryResult((LedgerDispatch(expected, response, "recovery"),),
                              0, ("create_order",), "REPLAY_TERMINATED")
    if policy != "LLM_REGENERATION" or model_continue is None:
        raise RazorpayPaperError("missing model continuation")
    actions: list[str] = []
    dispatches: list[LedgerDispatch] = []
    previous: Any = None
    for index in range(4):
        if should_stop is not None and should_stop():
            return RecoveryResult(tuple(dispatches), index,
                                  tuple(actions), "PROVIDER_RUN_STOP")
        emitted = model_continue({
            "user_task": user_task, "ambiguity": AMBIGUITY,
            "previous_tool_result": previous,
            "model_call_index": index, "seed": base_seed + index,
        })
        if type(emitted) is ModelDecision:
            decisions = (emitted,)
        elif type(emitted) is tuple and all(type(x) is ModelDecision for x in emitted):
            decisions = emitted
        else:
            raise RazorpayPaperError("invalid model decision")
        if not decisions:
            return RecoveryResult(tuple(dispatches), index + 1, tuple(actions),
                                  "MODEL_FINISHED")
        previous_results: list[Any] = []
        for decision in decisions:
            if should_stop is not None and should_stop():
                return RecoveryResult(tuple(dispatches), index + 1,
                                      tuple(actions), "PROVIDER_RUN_STOP")
            if decision.action == "invalid_output":
                return RecoveryResult(tuple(dispatches), index + 1,
                                      tuple(actions), "MODEL_INVALID_OUTPUT")
            if decision.action == "model_infrastructure_failure":
                return RecoveryResult(tuple(dispatches), index + 1,
                                      tuple(actions), "MODEL_INFRASTRUCTURE_FAILURE")
            if decision.action == "finish":
                return RecoveryResult(tuple(dispatches), index + 1,
                                      tuple(actions), "MODEL_FINISHED")
            if len(actions) == 3:
                return RecoveryResult(tuple(dispatches), index + 1,
                                      tuple(actions), "ACTION_BUDGET_EXCEEDED")
            if decision.action == "create_order":
                if type(decision.amount) is not int or type(decision.currency) is not str:
                    actions.append("invalid_create_order")
                    previous_results.append("ToolError: Invalid tool arguments.")
                    continue
                try:
                    request = serialize_create(arm_id=arm_id, marker=marker,
                                               scope_fingerprint=scope_fingerprint,
                                               amount=decision.amount,
                                               currency=decision.currency)
                except RazorpayPaperError:
                    actions.append("invalid_create_order")
                    previous_results.append("ToolError: Invalid tool arguments.")
                    continue
                response = dispatch(request)
                if type(response) is not RawResponse:
                    raise RazorpayPaperError("missing raw dispatch evidence")
                actions.append("create_order")
                dispatches.append(LedgerDispatch(request, response, "recovery"))
                if validate_ack(request, response) is None:
                    return RecoveryResult(tuple(dispatches), index + 1,
                                          tuple(actions), "MUTATION_OUTCOME_UNRESOLVED")
                previous_results.append({"status": "created"})
            elif decision.action == "list_orders":
                if (decision.amount is not None or decision.currency is not None
                        or list_orders is None):
                    actions.append("invalid_list_orders")
                    previous_results.append("ToolError: Invalid tool arguments.")
                    continue
                observed = list_orders()
                if type(observed) is not FetchAllRound:
                    raise RazorpayPaperError("missing bounded list evidence")
                actions.append("list_orders")
                if observed.structurally_complete:
                    projected = [{"amount": order.amount, "currency": order.currency}
                                 for order in observed.orders]
                    previous_results.append({"orders": sorted(
                        projected, key=lambda x: (x["amount"], x["currency"])),
                        "list_traversal_complete": True})
                else:
                    previous_results.append("ToolError: Order observation incomplete.")
                if should_stop is not None and should_stop():
                    return RecoveryResult(tuple(dispatches), index + 1,
                                          tuple(actions), "PROVIDER_RUN_STOP")
            else:
                actions.append("invalid_action")
                previous_results.append("ToolError: Invalid tool action.")
        previous = (previous_results[0] if len(previous_results) == 1
                    else previous_results)
    return RecoveryResult(tuple(dispatches), 4, tuple(actions), "MODEL_CALL_LIMIT")
