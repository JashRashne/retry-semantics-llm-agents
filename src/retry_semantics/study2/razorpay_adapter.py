"""Offline-only engineering adapter for the Razorpay Order candidate.

This module encodes candidate request and observation mechanics.  It does not
select Razorpay as Provider C, establish Test Mode, implement retry policy, or
claim that an offset traversal is authoritatively complete.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import Enum
import json
import math
import re
from threading import Lock
from urllib.parse import urlencode

import httpx

from retry_semantics.serialization import canonical_json_bytes, sha256_hex


PROVIDER_CANDIDATE = "razorpay"
CREATE_ORDER_OPERATION = "create_order"
RAZORPAY_ORIGIN = "https://api.razorpay.com"
ORDERS_PATH = "/v1/orders"
ORDERS_URL = RAZORPAY_ORIGIN + ORDERS_PATH
CONTENT_TYPE = "application/json"
MARKER_KEY = "retry_semantics_marker"
ORDER_AMOUNT = 200
ORDER_CURRENCY = "INR"
PAGE_SIZE = 100
EXPECTED_HTTP_SUCCESS = 200
DEFAULT_TRANSPORT_PROFILE = (
    "httpx_httptransport_retries0_no_redirects_no_trust_env_v1"
)

_MARKER_PATTERN = re.compile(r"study2_[A-Za-z0-9_-]{1,56}\Z")
_TRANSPORT_PROFILE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


class RazorpayAdapterValidationError(ValueError):
    """Safe local validation error whose text never includes supplied values."""


class MutationClassification(str, Enum):
    PRE_DISPATCH_REJECTED = "PRE_DISPATCH_REJECTED"
    ACKNOWLEDGED_CREATE = "ACKNOWLEDGED_CREATE"
    UNKNOWN_AFTER_DISPATCH = "UNKNOWN_AFTER_DISPATCH"


class ObservationStatus(str, Enum):
    STRUCTURALLY_COMPLETED_UNQUALIFIED = "structurally_completed_unqualified"
    INCOMPLETE = "incomplete"
    MALFORMED = "malformed"
    TRANSPORT_FAILED = "transport_failed"


class ObservationConclusion(str, Enum):
    ZERO_MATCHES_READ_NOT_H0_PROOF = "ZERO_MATCHES_READ_NOT_H0_PROOF"
    MATCHES_OBSERVED_UNQUALIFIED = "MATCHES_OBSERVED_UNQUALIFIED"
    OBSERVATION_INCOMPLETE = "OBSERVATION_INCOMPLETE"


def _require_timeout(value: float) -> float:
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise RazorpayAdapterValidationError("finite positive timeout required")
    return float(value)


def validate_marker(marker: str) -> str:
    """Require a deliberately narrow, synthetic, ASCII-only marker shape."""

    if type(marker) is not str or _MARKER_PATTERN.fullmatch(marker) is None:
        raise RazorpayAdapterValidationError("safe synthetic marker required")
    return marker


def _require_transport_profile(value: str) -> str:
    if (
        type(value) is not str
        or _TRANSPORT_PROFILE_PATTERN.fullmatch(value) is None
    ):
        raise RazorpayAdapterValidationError("explicit transport profile required")
    return value


class RazorpayCredentials:
    """Transport-only credentials with a one-way evidence scope.

    Syntax does not establish Test Mode.  In particular, no prefix is inspected
    or interpreted.  The secret is intentionally unavailable through repr/str or
    any evidence projection.
    """

    __slots__ = ("_key_id", "_key_secret", "_scope_fingerprint")

    def __init__(self, key_id: str, key_secret: str) -> None:
        if (
            type(key_id) is not str
            or type(key_secret) is not str
            or not key_id
            or not key_secret
        ):
            raise RazorpayAdapterValidationError("nonempty Razorpay credentials required")
        if any(character in key_id + key_secret for character in ("\r", "\n", "\0")):
            raise RazorpayAdapterValidationError("invalid Razorpay credential characters")
        self._key_id = key_id
        self._key_secret = key_secret
        scope_material = canonical_json_bytes(
            {
                "key_id": key_id,
                "key_secret": key_secret,
                "provider_candidate": PROVIDER_CANDIDATE,
            }
        )
        self._scope_fingerprint = sha256_hex(scope_material)

    @property
    def scope_fingerprint(self) -> str:
        return self._scope_fingerprint

    def _authorization_value(self) -> str:
        material = f"{self._key_id}:{self._key_secret}".encode("utf-8")
        return "Basic " + base64.b64encode(material).decode("ascii")

    def __repr__(self) -> str:
        return (
            "RazorpayCredentials(scope_fingerprint="
            f"'{self._scope_fingerprint}')"
        )

    __str__ = __repr__


class DispatchPermit:
    """Process-local, one-shot authorization for one mutation dispatch attempt."""

    __slots__ = ("_consumed", "_lock")

    def __init__(self) -> None:
        self._consumed = False
        self._lock = Lock()

    @property
    def consumed(self) -> bool:
        with self._lock:
            return self._consumed

    def consume(self) -> bool:
        """Consume before the transport boundary; never refunds on failure."""

        with self._lock:
            if self._consumed:
                return False
            self._consumed = True
            return True

    def __repr__(self) -> str:
        return f"DispatchPermit(consumed={self.consumed})"


@dataclass(frozen=True, slots=True)
class FrozenOrderCreateRequest:
    provider_candidate: str
    operation: str
    method: str
    origin: str
    path: str
    content_type: str
    body: bytes
    marker: str
    amount: int
    currency: str
    credential_scope_fingerprint: str
    timeout_seconds: float
    transport_profile: str

    def __post_init__(self) -> None:
        validate_marker(self.marker)
        expected_body = canonical_json_bytes(
            {
                "amount": ORDER_AMOUNT,
                "currency": ORDER_CURRENCY,
                "notes": {MARKER_KEY: self.marker},
            }
        )
        checks = (
            self.provider_candidate == PROVIDER_CANDIDATE,
            self.operation == CREATE_ORDER_OPERATION,
            self.method == "POST",
            self.origin == RAZORPAY_ORIGIN,
            self.path == ORDERS_PATH,
            self.content_type == CONTENT_TYPE,
            type(self.body) is bytes and self.body == expected_body,
            type(self.amount) is int and self.amount == ORDER_AMOUNT,
            self.currency == ORDER_CURRENCY,
            type(self.credential_scope_fingerprint) is str
            and bool(self.credential_scope_fingerprint),
            _require_timeout(self.timeout_seconds) == self.timeout_seconds,
            _require_transport_profile(self.transport_profile) == self.transport_profile,
        )
        if not all(checks):
            raise RazorpayAdapterValidationError("invalid frozen Order request")

    @property
    def url(self) -> str:
        return self.origin + self.path

    @property
    def body_sha256(self) -> str:
        return sha256_hex(self.body)

    def identity_bytes(self) -> bytes:
        """Canonical identity includes the exact body bytes, not dict equality."""

        return canonical_json_bytes(
            {
                "amount": self.amount,
                "body_base64": base64.b64encode(self.body).decode("ascii"),
                "content_type": self.content_type,
                "credential_scope_fingerprint": self.credential_scope_fingerprint,
                "currency": self.currency,
                "marker": self.marker,
                "method": self.method,
                "operation": self.operation,
                "origin": self.origin,
                "path": self.path,
                "provider_candidate": self.provider_candidate,
                "timeout_seconds": self.timeout_seconds,
                "transport_profile": self.transport_profile,
            }
        )

    @property
    def identity_sha256(self) -> str:
        return sha256_hex(self.identity_bytes())


@dataclass(frozen=True, slots=True)
class MutationResult:
    dispatch_started: bool
    local_transport_completed: bool
    acknowledgement_valid: bool
    http_status: int | None
    sanitized_response_metadata: tuple[tuple[str, str], ...]
    provider_order_id: str | None
    classification: MutationClassification
    request_identity_sha256: str | None
    request_body_sha256: str | None
    credential_scope_fingerprint: str
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.sanitized_response_metadata) is not tuple:
            raise RazorpayAdapterValidationError("immutable response metadata required")
        if self.classification is MutationClassification.PRE_DISPATCH_REJECTED:
            if self.dispatch_started or self.local_transport_completed or self.acknowledgement_valid:
                raise RazorpayAdapterValidationError("invalid pre-dispatch result")
        elif not self.dispatch_started:
            raise RazorpayAdapterValidationError("post-dispatch result requires dispatch")
        if self.classification is MutationClassification.ACKNOWLEDGED_CREATE:
            if not (
                self.local_transport_completed
                and self.acknowledgement_valid
                and self.http_status == EXPECTED_HTTP_SUCCESS
                and self.provider_order_id
            ):
                raise RazorpayAdapterValidationError("invalid acknowledged result")
        elif self.acknowledgement_valid or self.provider_order_id is not None:
            raise RazorpayAdapterValidationError("unacknowledged result cannot claim Order ID")

    def sanitized_evidence(self) -> dict[str, object]:
        return {
            "acknowledgement_valid": self.acknowledgement_valid,
            "classification": self.classification.value,
            "credential_scope_fingerprint": self.credential_scope_fingerprint,
            "dispatch_started": self.dispatch_started,
            "failure_reason": self.failure_reason,
            "http_status": self.http_status,
            "local_transport_completed": self.local_transport_completed,
            "provider_candidate": PROVIDER_CANDIDATE,
            "provider_order_id": self.provider_order_id,
            "request_body_sha256": self.request_body_sha256,
            "request_identity_sha256": self.request_identity_sha256,
            "response_metadata": [list(item) for item in self.sanitized_response_metadata],
        }


@dataclass(frozen=True, slots=True)
class OrderObservationRequest:
    marker: str
    from_timestamp: int
    to_timestamp: int
    credential_scope_fingerprint: str
    page_cap: int
    timeout_seconds: float

    def __post_init__(self) -> None:
        validate_marker(self.marker)
        if (
            type(self.from_timestamp) is not int
            or type(self.to_timestamp) is not int
            or self.from_timestamp < 0
            or self.to_timestamp < 0
            or self.from_timestamp > self.to_timestamp
        ):
            raise RazorpayAdapterValidationError("valid explicit observation window required")
        if type(self.page_cap) is not int or self.page_cap <= 0:
            raise RazorpayAdapterValidationError("finite positive page cap required")
        if (
            type(self.credential_scope_fingerprint) is not str
            or not self.credential_scope_fingerprint
        ):
            raise RazorpayAdapterValidationError("credential scope required")
        _require_timeout(self.timeout_seconds)

    def query_for_skip(self, skip: int) -> str:
        if type(skip) is not int or skip < 0 or skip % PAGE_SIZE:
            raise RazorpayAdapterValidationError("valid page offset required")
        return urlencode(
            (
                ("count", str(PAGE_SIZE)),
                ("skip", str(skip)),
                ("from", str(self.from_timestamp)),
                ("to", str(self.to_timestamp)),
            )
        )

    def url_for_skip(self, skip: int) -> str:
        return f"{ORDERS_URL}?{self.query_for_skip(skip)}"


@dataclass(frozen=True, slots=True)
class ObservationResult:
    status: ObservationStatus
    authoritative_completeness_qualified: bool
    structurally_completed: bool
    matching_order_ids: tuple[str, ...]
    matching_resource_count: int | None
    additional_matching_resource_count: int | None
    pages_requested: int
    pages_completed: int
    page_skips: tuple[int, ...]
    page_query_sha256: tuple[str, ...]
    http_statuses: tuple[int, ...]
    pagination_instability: bool
    incomplete_reason: str | None
    conclusion: ObservationConclusion
    marker: str
    credential_scope_fingerprint: str

    def __post_init__(self) -> None:
        if self.authoritative_completeness_qualified is not False:
            raise RazorpayAdapterValidationError("authoritative completeness is unqualified")
        if (
            type(self.page_skips) is not tuple
            or type(self.page_query_sha256) is not tuple
            or type(self.http_statuses) is not tuple
            or self.pages_requested != len(self.page_skips)
            or self.pages_requested != len(self.page_query_sha256)
            or self.pages_completed < 0
            or self.pages_completed > self.pages_requested
            or len(self.http_statuses) > self.pages_requested
        ):
            raise RazorpayAdapterValidationError("inconsistent observation page evidence")
        if self.status is ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED:
            if (
                not self.structurally_completed
                or self.incomplete_reason is not None
                or self.pages_completed != self.pages_requested
                or len(self.http_statuses) != self.pages_requested
                or len(set(self.matching_order_ids)) != len(self.matching_order_ids)
            ):
                raise RazorpayAdapterValidationError("invalid structural completion")
            expected_count = len(self.matching_order_ids)
            if self.matching_resource_count != expected_count:
                raise RazorpayAdapterValidationError("matching count disagreement")
            if self.additional_matching_resource_count != max(0, expected_count - 1):
                raise RazorpayAdapterValidationError("additional count disagreement")
            expected_conclusion = (
                ObservationConclusion.ZERO_MATCHES_READ_NOT_H0_PROOF
                if expected_count == 0
                else ObservationConclusion.MATCHES_OBSERVED_UNQUALIFIED
            )
            if self.conclusion is not expected_conclusion:
                raise RazorpayAdapterValidationError("invalid observation conclusion")
        else:
            if (
                self.structurally_completed
                or self.matching_resource_count is not None
                or self.additional_matching_resource_count is not None
                or self.incomplete_reason is None
                or self.conclusion is not ObservationConclusion.OBSERVATION_INCOMPLETE
            ):
                raise RazorpayAdapterValidationError("incomplete observation cannot claim counts")

    def sanitized_evidence(self) -> dict[str, object]:
        return {
            "additional_matching_resource_count": self.additional_matching_resource_count,
            "authoritative_completeness_qualified": False,
            "conclusion": self.conclusion.value,
            "credential_scope_fingerprint": self.credential_scope_fingerprint,
            "http_statuses": list(self.http_statuses),
            "incomplete_reason": self.incomplete_reason,
            "marker": self.marker,
            "matching_order_ids": list(self.matching_order_ids),
            "matching_resource_count": self.matching_resource_count,
            "page_query_sha256": list(self.page_query_sha256),
            "page_skips": list(self.page_skips),
            "pages_completed": self.pages_completed,
            "pages_requested": self.pages_requested,
            "pagination_instability": self.pagination_instability,
            "provider_candidate": PROVIDER_CANDIDATE,
            "status": self.status.value,
            "structurally_completed": self.structurally_completed,
        }


def _response_metadata(response: httpx.Response) -> tuple[tuple[str, str], ...]:
    """Return only fixed derived metadata, never raw response headers/body."""

    return (
        ("body_length", str(len(response.content))),
        ("content_type_present", str("content-type" in response.headers).lower()),
    )


def _valid_order_acknowledgement(
    value: object, request: FrozenOrderCreateRequest
) -> str | None:
    if type(value) is not dict:
        return None
    order_id = value.get("id")
    notes = value.get("notes")
    if (
        type(order_id) is not str
        or not order_id.strip()
        or value.get("entity") != "order"
        or type(value.get("amount")) is not int
        or value.get("amount") != request.amount
        or value.get("currency") != request.currency
        or value.get("status") != "created"
        or type(value.get("attempts")) is not int
        or value.get("attempts") != 0
        or type(value.get("amount_paid")) is not int
        or value.get("amount_paid") != 0
        or type(notes) is not dict
        or notes.get(MARKER_KEY) != request.marker
        or ("receipt" in value and value["receipt"] is not None)
    ):
        return None
    return order_id


class RazorpayOrderAdapter:
    """Candidate Order adapter with injectable, single-attempt HTTP transport."""

    def __init__(
        self,
        credentials: RazorpayCredentials,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        transport_profile: str | None = None,
    ) -> None:
        if not isinstance(credentials, RazorpayCredentials):
            raise RazorpayAdapterValidationError("Razorpay credentials required")
        self._credentials = credentials
        self._timeout_seconds = _require_timeout(timeout_seconds)
        if transport is None:
            if transport_profile is not None:
                raise RazorpayAdapterValidationError(
                    "default transport profile is fixed"
                )
            resolved_transport = httpx.HTTPTransport(retries=0)
            self._transport_profile = DEFAULT_TRANSPORT_PROFILE
        else:
            if transport_profile is None:
                raise RazorpayAdapterValidationError(
                    "injected transport requires explicit profile"
                )
            resolved_transport = transport
            self._transport_profile = _require_transport_profile(transport_profile)
            if self._transport_profile == DEFAULT_TRANSPORT_PROFILE:
                raise RazorpayAdapterValidationError(
                    "default transport profile is reserved"
                )
        self._client = httpx.Client(
            transport=resolved_transport,
            timeout=httpx.Timeout(self._timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )

    def __repr__(self) -> str:
        return (
            "RazorpayOrderAdapter(credential_scope_fingerprint="
            f"'{self._credentials.scope_fingerprint}', "
            f"timeout_seconds={self._timeout_seconds}, "
            f"transport_profile='{self._transport_profile}')"
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RazorpayOrderAdapter:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def prepare_create_order(self, marker: str) -> FrozenOrderCreateRequest:
        marker = validate_marker(marker)
        body = canonical_json_bytes(
            {
                "amount": ORDER_AMOUNT,
                "currency": ORDER_CURRENCY,
                "notes": {MARKER_KEY: marker},
            }
        )
        return FrozenOrderCreateRequest(
            provider_candidate=PROVIDER_CANDIDATE,
            operation=CREATE_ORDER_OPERATION,
            method="POST",
            origin=RAZORPAY_ORIGIN,
            path=ORDERS_PATH,
            content_type=CONTENT_TYPE,
            body=body,
            marker=marker,
            amount=ORDER_AMOUNT,
            currency=ORDER_CURRENCY,
            credential_scope_fingerprint=self._credentials.scope_fingerprint,
            timeout_seconds=self._timeout_seconds,
            transport_profile=self._transport_profile,
        )

    def create_order(self, marker: str, permit: DispatchPermit) -> MutationResult:
        """Validate, freeze, and make at most one authorized dispatch attempt."""

        try:
            request = self.prepare_create_order(marker)
        except RazorpayAdapterValidationError:
            return self._pre_dispatch_result("local_validation_rejected")
        return self.dispatch_create_order(request, permit)

    def _pre_dispatch_result(
        self,
        reason: str,
        request: FrozenOrderCreateRequest | None = None,
    ) -> MutationResult:
        return MutationResult(
            dispatch_started=False,
            local_transport_completed=False,
            acknowledgement_valid=False,
            http_status=None,
            sanitized_response_metadata=(),
            provider_order_id=None,
            classification=MutationClassification.PRE_DISPATCH_REJECTED,
            request_identity_sha256=(request.identity_sha256 if request else None),
            request_body_sha256=(request.body_sha256 if request else None),
            credential_scope_fingerprint=self._credentials.scope_fingerprint,
            failure_reason=reason,
        )

    def dispatch_create_order(
        self,
        request: FrozenOrderCreateRequest,
        permit: DispatchPermit,
    ) -> MutationResult:
        if not isinstance(request, FrozenOrderCreateRequest):
            return self._pre_dispatch_result("invalid_frozen_request")
        if (
            request.credential_scope_fingerprint
            != self._credentials.scope_fingerprint
            or request.timeout_seconds != self._timeout_seconds
            or request.transport_profile != self._transport_profile
        ):
            return self._pre_dispatch_result("request_scope_mismatch", request)
        if not isinstance(permit, DispatchPermit):
            return self._pre_dispatch_result("dispatch_permit_unavailable", request)

        try:
            authorization = self._credentials._authorization_value()
            outbound = self._client.build_request(
                request.method,
                request.url,
                headers={
                    "Authorization": authorization,
                    "Content-Type": request.content_type,
                },
                content=request.body,
            )
        except Exception:
            # This is still local: no dispatch permit was consumed and no
            # transport boundary was crossed.  Discard potentially sensitive
            # exception text.
            return self._pre_dispatch_result(
                "outbound_request_construction_failed", request
            )
        if not permit.consume():
            return self._pre_dispatch_result("dispatch_permit_unavailable", request)
        try:
            response = self._client.send(outbound)
        except Exception:
            # Never retain/chain raw transport exceptions; request objects can
            # carry Authorization.  Permit remains consumed.
            return MutationResult(
                dispatch_started=True,
                local_transport_completed=False,
                acknowledgement_valid=False,
                http_status=None,
                sanitized_response_metadata=(),
                provider_order_id=None,
                classification=MutationClassification.UNKNOWN_AFTER_DISPATCH,
                request_identity_sha256=request.identity_sha256,
                request_body_sha256=request.body_sha256,
                credential_scope_fingerprint=self._credentials.scope_fingerprint,
                failure_reason="transport_exception",
            )

        metadata = _response_metadata(response)
        if response.status_code != EXPECTED_HTTP_SUCCESS:
            return self._unknown_response(
                request, response.status_code, metadata, "unexpected_http_status"
            )
        try:
            value = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._unknown_response(
                request, response.status_code, metadata, "malformed_json_acknowledgement"
            )
        order_id = _valid_order_acknowledgement(value, request)
        if order_id is None:
            return self._unknown_response(
                request, response.status_code, metadata, "invalid_acknowledgement"
            )
        return MutationResult(
            dispatch_started=True,
            local_transport_completed=True,
            acknowledgement_valid=True,
            http_status=response.status_code,
            sanitized_response_metadata=metadata,
            provider_order_id=order_id,
            classification=MutationClassification.ACKNOWLEDGED_CREATE,
            request_identity_sha256=request.identity_sha256,
            request_body_sha256=request.body_sha256,
            credential_scope_fingerprint=self._credentials.scope_fingerprint,
        )

    def _unknown_response(
        self,
        request: FrozenOrderCreateRequest,
        status: int,
        metadata: tuple[tuple[str, str], ...],
        reason: str,
    ) -> MutationResult:
        return MutationResult(
            dispatch_started=True,
            local_transport_completed=True,
            acknowledgement_valid=False,
            http_status=status,
            sanitized_response_metadata=metadata,
            provider_order_id=None,
            classification=MutationClassification.UNKNOWN_AFTER_DISPATCH,
            request_identity_sha256=request.identity_sha256,
            request_body_sha256=request.body_sha256,
            credential_scope_fingerprint=self._credentials.scope_fingerprint,
            failure_reason=reason,
        )

    def prepare_observation(
        self,
        *,
        marker: str,
        from_timestamp: int,
        to_timestamp: int,
        page_cap: int,
    ) -> OrderObservationRequest:
        return OrderObservationRequest(
            marker=marker,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            credential_scope_fingerprint=self._credentials.scope_fingerprint,
            page_cap=page_cap,
            timeout_seconds=self._timeout_seconds,
        )

    def observe_orders(
        self,
        *,
        marker: str,
        from_timestamp: int,
        to_timestamp: int,
        page_cap: int,
    ) -> ObservationResult:
        request = self.prepare_observation(
            marker=marker,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            page_cap=page_cap,
        )
        return self.execute_observation(request)

    def execute_observation(self, request: OrderObservationRequest) -> ObservationResult:
        if not isinstance(request, OrderObservationRequest):
            raise RazorpayAdapterValidationError("observation request required")
        if (
            request.credential_scope_fingerprint
            != self._credentials.scope_fingerprint
            or request.timeout_seconds != self._timeout_seconds
        ):
            raise RazorpayAdapterValidationError("observation scope mismatch")

        seen_ids: set[str] = set()
        matching_ids: list[str] = []
        page_skips: list[int] = []
        query_digests: list[str] = []
        statuses: list[int] = []
        pages_completed = 0

        for page_index in range(request.page_cap):
            skip = page_index * PAGE_SIZE
            query = request.query_for_skip(skip)
            page_skips.append(skip)
            query_digests.append(sha256_hex(query.encode("ascii")))
            outbound = self._client.build_request(
                "GET",
                request.url_for_skip(skip),
                headers={"Authorization": self._credentials._authorization_value()},
            )
            try:
                response = self._client.send(outbound)
            except Exception:
                return self._incomplete_observation(
                    request,
                    ObservationStatus.TRANSPORT_FAILED,
                    matching_ids,
                    page_skips,
                    query_digests,
                    statuses,
                    pages_completed,
                    "transport_exception",
                )
            statuses.append(response.status_code)
            if response.status_code != EXPECTED_HTTP_SUCCESS:
                return self._incomplete_observation(
                    request,
                    ObservationStatus.INCOMPLETE,
                    matching_ids,
                    page_skips,
                    query_digests,
                    statuses,
                    pages_completed,
                    "unexpected_http_status",
                )
            try:
                value = json.loads(response.content)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._incomplete_observation(
                    request,
                    ObservationStatus.MALFORMED,
                    matching_ids,
                    page_skips,
                    query_digests,
                    statuses,
                    pages_completed,
                    "malformed_json_collection",
                )
            if (
                type(value) is not dict
                or value.get("entity") != "collection"
                or type(value.get("items")) is not list
                or len(value["items"]) > PAGE_SIZE
            ):
                return self._incomplete_observation(
                    request,
                    ObservationStatus.MALFORMED,
                    matching_ids,
                    page_skips,
                    query_digests,
                    statuses,
                    pages_completed,
                    "malformed_collection_shape",
                )

            items = value["items"]
            for item in items:
                if (
                    type(item) is not dict
                    or item.get("entity") != "order"
                    or type(item.get("id")) is not str
                    or not item["id"].strip()
                ):
                    return self._incomplete_observation(
                        request,
                        ObservationStatus.MALFORMED,
                        matching_ids,
                        page_skips,
                        query_digests,
                        statuses,
                        pages_completed,
                        "malformed_order_item",
                    )
                order_id = item["id"]
                if order_id in seen_ids:
                    return self._incomplete_observation(
                        request,
                        ObservationStatus.INCOMPLETE,
                        matching_ids,
                        page_skips,
                        query_digests,
                        statuses,
                        pages_completed,
                        "repeated_order_id",
                        pagination_instability=True,
                    )
                seen_ids.add(order_id)

                if "notes" not in item:
                    return self._incomplete_observation(
                        request,
                        ObservationStatus.MALFORMED,
                        matching_ids,
                        page_skips,
                        query_digests,
                        statuses,
                        pages_completed,
                        "missing_notes_field",
                    )
                notes = item["notes"]
                if type(notes) is not dict:
                    return self._incomplete_observation(
                        request,
                        ObservationStatus.MALFORMED,
                        matching_ids,
                        page_skips,
                        query_digests,
                        statuses,
                        pages_completed,
                        "malformed_notes",
                    )
                missing_marker = object()
                marker_value = notes.get(MARKER_KEY, missing_marker)
                if marker_value is missing_marker:
                    continue
                if type(marker_value) is not str:
                    return self._incomplete_observation(
                        request,
                        ObservationStatus.MALFORMED,
                        matching_ids,
                        page_skips,
                        query_digests,
                        statuses,
                        pages_completed,
                        "malformed_marker_value",
                    )
                if marker_value == request.marker:
                    matching_ids.append(order_id)

            pages_completed += 1
            if len(items) < PAGE_SIZE:
                count = len(matching_ids)
                return ObservationResult(
                    status=ObservationStatus.STRUCTURALLY_COMPLETED_UNQUALIFIED,
                    authoritative_completeness_qualified=False,
                    structurally_completed=True,
                    matching_order_ids=tuple(matching_ids),
                    matching_resource_count=count,
                    additional_matching_resource_count=max(0, count - 1),
                    pages_requested=len(page_skips),
                    pages_completed=pages_completed,
                    page_skips=tuple(page_skips),
                    page_query_sha256=tuple(query_digests),
                    http_statuses=tuple(statuses),
                    pagination_instability=False,
                    incomplete_reason=None,
                    conclusion=(
                        ObservationConclusion.ZERO_MATCHES_READ_NOT_H0_PROOF
                        if count == 0
                        else ObservationConclusion.MATCHES_OBSERVED_UNQUALIFIED
                    ),
                    marker=request.marker,
                    credential_scope_fingerprint=request.credential_scope_fingerprint,
                )

        return self._incomplete_observation(
            request,
            ObservationStatus.INCOMPLETE,
            matching_ids,
            page_skips,
            query_digests,
            statuses,
            pages_completed,
            "page_cap_exceeded",
        )

    @staticmethod
    def _incomplete_observation(
        request: OrderObservationRequest,
        status: ObservationStatus,
        matching_ids: list[str],
        page_skips: list[int],
        query_digests: list[str],
        statuses: list[int],
        pages_completed: int,
        reason: str,
        *,
        pagination_instability: bool = False,
    ) -> ObservationResult:
        return ObservationResult(
            status=status,
            authoritative_completeness_qualified=False,
            structurally_completed=False,
            matching_order_ids=tuple(matching_ids),
            matching_resource_count=None,
            additional_matching_resource_count=None,
            pages_requested=len(page_skips),
            pages_completed=pages_completed,
            page_skips=tuple(page_skips),
            page_query_sha256=tuple(query_digests),
            http_statuses=tuple(statuses),
            pagination_instability=pagination_instability,
            incomplete_reason=reason,
            conclusion=ObservationConclusion.OBSERVATION_INCOMPLETE,
            marker=request.marker,
            credential_scope_fingerprint=request.credential_scope_fingerprint,
        )
