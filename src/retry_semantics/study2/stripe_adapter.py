"""Narrow Stripe Customer HTTP adapter for offline Study 2 qualification.

This module defines request construction and single-attempt behavior.  It does
not allocate paper-protocol identifiers, read credentials, retry mutations,
run observation after a failure, or provide crash-durable authorization.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import json
import math
import re
from urllib.parse import urlencode

import httpx

from retry_semantics.serialization import canonical_json_bytes, sha256_hex


STRIPE_API_ORIGIN = "https://api.stripe.com"
CUSTOMERS_PATH = "/v1/customers"
REVIEWED_STRIPE_API_VERSION = "2026-08-26.dahlia"
CUSTOMER_LIST_LIMIT = 100
DEFAULT_MAX_OBSERVATION_PAGES = 100
MAX_CONFIGURED_OBSERVATION_PAGES = 1_000
MAX_RESPONSE_BYTES = 1_000_000

_CUSTOMER_ID = re.compile(r"cus_[A-Za-z0-9]+")
_SYNTHETIC_EMAIL = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{0,63}"
    r"@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,188}[A-Za-z0-9])?\.invalid"
)
_IDEMPOTENCY_KEY = re.compile(r"[!-~]{1,255}")
_TEST_CREDENTIAL = re.compile(r"(?:sk|rk)_test_[A-Za-z0-9_]+")
_CREDENTIAL_FRAGMENT = re.compile(r"(?:sk|rk)_(?:test|live)_")


class StripeAdapterError(ValueError):
    """A fixed, non-secret configuration or local-state error."""


class DispatchLifecycle(str, Enum):
    PREPARED = "prepared"
    DISPATCH_INITIATED = "dispatch_initiated"
    RESPONSE_RECEIVED = "response_received"
    ACKNOWLEDGEMENT_VALIDATED = "acknowledgement_validated"


class MutationDisposition(str, Enum):
    VALID_CUSTOMER_ACKNOWLEDGEMENT = "valid_customer_acknowledgement"
    AMBIGUOUS_TRANSPORT_FAILURE = "ambiguous_transport_failure"
    HTTP_ACKNOWLEDGED_FAILURE = "http_acknowledged_failure"
    UNEXPECTED_REDIRECT = "unexpected_redirect"
    MALFORMED_ACKNOWLEDGEMENT = "malformed_acknowledgement"


class RemoteMutationOutcome(str, Enum):
    """No value in this enum is an H0/H1 hidden-world classification."""

    ACKNOWLEDGED_CUSTOMER = "acknowledged_customer"
    UNKNOWN_AMBIGUOUS = "unknown_ambiguous"
    UNKNOWN_AFTER_HTTP_ACKNOWLEDGEMENT = "unknown_after_http_acknowledgement"
    UNKNOWN_AFTER_MALFORMED_ACKNOWLEDGEMENT = (
        "unknown_after_malformed_acknowledgement"
    )


class ObservationConclusion(str, Enum):
    COMPLETED_READ_NOT_H0_PROOF = "completed_read_not_h0_proof"
    UNKNOWN_INCOMPLETE = "unknown_incomplete"


@dataclass(frozen=True, slots=True)
class StripeTestCredential:
    """Explicit test-mode credential whose raw value is never evidence."""

    value: str = field(repr=False, compare=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.value) is not str or _TEST_CREDENTIAL.fullmatch(self.value) is None:
            raise StripeAdapterError("explicit Stripe TEST/SANDBOX credential required")
        object.__setattr__(
            self,
            "fingerprint",
            sha256_hex(b"stripe-test-credential-v1\0" + self.value.encode("ascii")),
        )


def _require_synthetic_email(email: str) -> None:
    if (
        type(email) is not str
        or len(email) > 254
        or _SYNTHETIC_EMAIL.fullmatch(email) is None
    ):
        raise StripeAdapterError("synthetic .invalid correlation email required")


def _idempotency_fingerprint(key: str | None) -> str | None:
    if key is None:
        return None
    if (
        type(key) is not str
        or _IDEMPOTENCY_KEY.fullmatch(key) is None
        or _CREDENTIAL_FRAGMENT.search(key) is not None
    ):
        raise StripeAdapterError("valid explicit runtime-owned idempotency key required")
    return sha256_hex(b"stripe-idempotency-key-v1\0" + key.encode("ascii"))


@dataclass(frozen=True, slots=True)
class MutationRequestEvidence:
    identity_sha256: str
    operation: str
    target_scope: str
    method: str
    path: str
    body_sha256: str
    body_byte_count: int
    api_version: str
    idempotency_key_present: bool
    idempotency_key_identity_sha256: str | None
    credential_fingerprint: str
    correlation_email: str
    runtime_options: tuple[tuple[str, str], ...]
    dispatch_lifecycle: DispatchLifecycle


@dataclass(frozen=True, slots=True)
class FrozenCustomerCreateRequest:
    """Exact pre-dispatch representation; ``body`` is sent without re-encoding."""

    correlation_email: str
    body: bytes
    credential_fingerprint: str
    timeout_seconds: float
    idempotency_key: str | None = field(default=None, repr=False, compare=False)
    operation: str = field(default="create_customer", init=False)
    target_scope: str = field(init=False)
    method: str = field(default="POST", init=False)
    path: str = field(default=CUSTOMERS_PATH, init=False)
    api_version: str = field(default=REVIEWED_STRIPE_API_VERSION, init=False)
    body_sha256: str = field(init=False)
    idempotency_key_identity_sha256: str | None = field(init=False)
    identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_synthetic_email(self.correlation_email)
        if type(self.body) is not bytes:
            raise StripeAdapterError("frozen mutation body bytes required")
        expected = urlencode((("email", self.correlation_email),)).encode("ascii")
        if self.body != expected:
            raise StripeAdapterError("body must be the exact frozen Customer email form")
        if not re.fullmatch(r"[0-9a-f]{64}", self.credential_fingerprint):
            raise StripeAdapterError("valid credential fingerprint required")
        if (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise StripeAdapterError("finite positive timeout required")
        key_fingerprint = _idempotency_fingerprint(self.idempotency_key)
        body_hash = sha256_hex(self.body)
        target_scope = f"stripe:test-mode:{self.credential_fingerprint}"
        identity_material = {
            "operation": self.operation,
            "target_scope": target_scope,
            "provider_origin": STRIPE_API_ORIGIN,
            "method": self.method,
            "path": self.path,
            "content_type": "application/x-www-form-urlencoded",
            "body_hex": self.body.hex(),
            "body_byte_count": len(self.body),
            "stripe_api_version": self.api_version,
            # The exact runtime-owned key is identity material, but only its
            # domain-separated hash is exposed by evidence/repr.
            "idempotency_key": self.idempotency_key,
            "runtime_options": {
                "follow_redirects": False,
                "http_transport_retries": 0,
                "timeout_seconds": self.timeout_seconds,
                "trust_env": False,
            },
        }
        object.__setattr__(self, "target_scope", target_scope)
        object.__setattr__(self, "body_sha256", body_hash)
        object.__setattr__(self, "idempotency_key_identity_sha256", key_fingerprint)
        object.__setattr__(
            self, "identity_sha256", sha256_hex(canonical_json_bytes(identity_material))
        )

    def evidence(self, lifecycle: DispatchLifecycle) -> MutationRequestEvidence:
        return MutationRequestEvidence(
            identity_sha256=self.identity_sha256,
            operation=self.operation,
            target_scope=self.target_scope,
            method=self.method,
            path=self.path,
            body_sha256=self.body_sha256,
            body_byte_count=len(self.body),
            api_version=self.api_version,
            idempotency_key_present=self.idempotency_key is not None,
            idempotency_key_identity_sha256=self.idempotency_key_identity_sha256,
            credential_fingerprint=self.credential_fingerprint,
            correlation_email=self.correlation_email,
            runtime_options=(
                ("follow_redirects", "false"),
                ("http_transport_retries", "0"),
                ("timeout_seconds", repr(self.timeout_seconds)),
                ("trust_env", "false"),
            ),
            dispatch_lifecycle=lifecycle,
        )


@dataclass(frozen=True, slots=True)
class MutationAcknowledgementEvidence:
    response_received: bool
    status_code: int | None
    customer_id: str | None
    request_id: str | None
    idempotent_replayed: bool | None


@dataclass(frozen=True, slots=True)
class MutationDispatchEvidence:
    request: MutationRequestEvidence
    acknowledgement: MutationAcknowledgementEvidence
    disposition: MutationDisposition
    remote_outcome: RemoteMutationOutcome
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class CustomerObservationEvidence:
    exact_email: str
    page_count: int
    request_count: int
    complete: bool
    matching_customer_ids: tuple[str, ...]
    matching_resource_count: int
    additional_matching_resource_count: int
    marker_multiplicity: int
    failure_reason: str | None
    last_status_code: int | None
    conclusion: ObservationConclusion

    def __post_init__(self) -> None:
        if self.complete != (self.conclusion is ObservationConclusion.COMPLETED_READ_NOT_H0_PROOF):
            raise StripeAdapterError("observation conclusion and completeness disagree")
        if len(self.matching_customer_ids) != len(set(self.matching_customer_ids)):
            raise StripeAdapterError("matching Customer IDs must be distinct")
        if self.matching_resource_count != len(self.matching_customer_ids):
            raise StripeAdapterError("matching resource count mismatch")
        if self.additional_matching_resource_count != max(
            self.matching_resource_count - 1, 0
        ):
            raise StripeAdapterError("additional matching resource count mismatch")
        if self.marker_multiplicity != self.matching_resource_count:
            raise StripeAdapterError("marker multiplicity mismatch")


def _safe_supplemental_header(
    response: httpx.Response, name: str, credential: StripeTestCredential
) -> str | None:
    value = response.headers.get(name)
    if (
        value is None
        or not value
        or len(value) > 256
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or credential.value in value
    ):
        return None
    return value


def _decode_json(response: httpx.Response) -> object:
    content = response.content
    if not content or len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("invalid JSON response size")

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError("non-finite JSON number")

    return json.loads(
        content.decode("utf-8", errors="strict"),
        object_pairs_hook=object_pairs,
        parse_constant=reject_constant,
    )


def _customer_id(value: object) -> str:
    if type(value) is not str or _CUSTOMER_ID.fullmatch(value) is None:
        raise ValueError("unusable Customer ID")
    return value


class OneShotCustomerMutation:
    """Process-local one-use dispatch guard; not crash-durable authorization."""

    def __init__(
        self, adapter: StripeCustomerAdapter, request: FrozenCustomerCreateRequest
    ) -> None:
        self._adapter = adapter
        self.request = request
        self._consumed = False

    @property
    def consumed(self) -> bool:
        return self._consumed

    @property
    def prepared_evidence(self) -> MutationRequestEvidence:
        return self.request.evidence(DispatchLifecycle.PREPARED)

    def dispatch(self) -> MutationDispatchEvidence:
        if self._consumed:
            raise StripeAdapterError("mutation dispatch already consumed")
        # Consumption precedes the provider boundary and survives every return
        # or exception path in this process.
        self._consumed = True
        return self._adapter._dispatch_customer_create(self.request)


class StripeCustomerAdapter:
    """Fixed Customer CREATE/LIST adapter with caller-supplied credentials."""

    def __init__(
        self,
        credential: StripeTestCredential,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 10.0,
        max_observation_pages: int = DEFAULT_MAX_OBSERVATION_PAGES,
    ) -> None:
        if not isinstance(credential, StripeTestCredential):
            raise StripeAdapterError("explicit validated Stripe test credential required")
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise StripeAdapterError("finite positive timeout required")
        if (
            type(max_observation_pages) is not int
            or not 0 < max_observation_pages <= MAX_CONFIGURED_OBSERVATION_PAGES
        ):
            raise StripeAdapterError("bounded positive observation page limit required")
        self._credential = credential
        self.timeout_seconds = timeout_seconds
        self.max_observation_pages = max_observation_pages
        selected_transport = transport
        if selected_transport is None:
            selected_transport = httpx.HTTPTransport(retries=0)
        self._client = httpx.Client(
            transport=selected_transport,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> StripeCustomerAdapter:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _headers(self, *, mutation: FrozenCustomerCreateRequest | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._credential.value}",
            "Accept": "application/json",
            "Stripe-Version": REVIEWED_STRIPE_API_VERSION,
            "User-Agent": "retry-semantics-study2-stripe-engineering",
        }
        if mutation is not None:
            if mutation.credential_fingerprint != self._credential.fingerprint:
                raise StripeAdapterError("mutation credential scope mismatch")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            if mutation.idempotency_key is not None:
                headers["Idempotency-Key"] = mutation.idempotency_key
        return headers

    def prepare_customer_create(
        self, *, email: str, idempotency_key: str | None = None
    ) -> OneShotCustomerMutation:
        _require_synthetic_email(email)
        _idempotency_fingerprint(idempotency_key)
        body = urlencode((("email", email),)).encode("ascii")
        request = FrozenCustomerCreateRequest(
            correlation_email=email,
            body=body,
            credential_fingerprint=self._credential.fingerprint,
            timeout_seconds=self.timeout_seconds,
            idempotency_key=idempotency_key,
        )
        return OneShotCustomerMutation(self, request)

    def _dispatch_customer_create(
        self, frozen: FrozenCustomerCreateRequest
    ) -> MutationDispatchEvidence:
        request_evidence = frozen.evidence(DispatchLifecycle.DISPATCH_INITIATED)
        acknowledgement = MutationAcknowledgementEvidence(False, None, None, None, None)
        request = self._client.build_request(
            frozen.method,
            STRIPE_API_ORIGIN + frozen.path,
            headers=self._headers(mutation=frozen),
            content=frozen.body,
        )
        try:
            # Exactly one call; no retry loop and HTTPTransport retries are zero.
            response = self._client.send(request)
        except Exception:
            return MutationDispatchEvidence(
                request_evidence,
                acknowledgement,
                MutationDisposition.AMBIGUOUS_TRANSPORT_FAILURE,
                RemoteMutationOutcome.UNKNOWN_AMBIGUOUS,
                "transport_exception_after_dispatch_initiated",
            )

        request_evidence = frozen.evidence(DispatchLifecycle.RESPONSE_RECEIVED)
        request_id = _safe_supplemental_header(response, "Request-Id", self._credential)
        replayed_text = _safe_supplemental_header(
            response, "Idempotent-Replayed", self._credential
        )
        replayed = (
            True
            if replayed_text == "true"
            else False
            if replayed_text == "false"
            else None
        )
        acknowledgement = MutationAcknowledgementEvidence(
            True, response.status_code, None, request_id, replayed
        )
        if response.is_redirect:
            return MutationDispatchEvidence(
                request_evidence,
                acknowledgement,
                MutationDisposition.UNEXPECTED_REDIRECT,
                RemoteMutationOutcome.UNKNOWN_AFTER_HTTP_ACKNOWLEDGEMENT,
                "unexpected_redirect",
            )
        if response.status_code != 200:
            return MutationDispatchEvidence(
                request_evidence,
                acknowledgement,
                MutationDisposition.HTTP_ACKNOWLEDGED_FAILURE,
                RemoteMutationOutcome.UNKNOWN_AFTER_HTTP_ACKNOWLEDGEMENT,
                "unexpected_http_status",
            )
        customer_id = None
        try:
            payload = _decode_json(response)
            if type(payload) is not dict or payload.get("object") != "customer":
                raise ValueError("Customer object required")
            customer_id = _customer_id(payload.get("id"))
            if payload.get("email") != frozen.correlation_email:
                raise ValueError("correlation email mismatch")
            if payload.get("livemode") is not False:
                raise ValueError("test-mode Customer required")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            return MutationDispatchEvidence(
                request_evidence,
                acknowledgement,
                MutationDisposition.MALFORMED_ACKNOWLEDGEMENT,
                RemoteMutationOutcome.UNKNOWN_AFTER_MALFORMED_ACKNOWLEDGEMENT,
                "malformed_customer_acknowledgement",
            )
        acknowledgement = replace(acknowledgement, customer_id=customer_id)
        return MutationDispatchEvidence(
            frozen.evidence(DispatchLifecycle.ACKNOWLEDGEMENT_VALIDATED),
            acknowledgement,
            MutationDisposition.VALID_CUSTOMER_ACKNOWLEDGEMENT,
            RemoteMutationOutcome.ACKNOWLEDGED_CUSTOMER,
            None,
        )

    def _observation_result(
        self,
        email: str,
        page_count: int,
        request_count: int,
        customer_ids: list[str],
        *,
        complete: bool,
        failure_reason: str | None,
        last_status_code: int | None,
    ) -> CustomerObservationEvidence:
        return CustomerObservationEvidence(
            exact_email=email,
            page_count=page_count,
            request_count=request_count,
            complete=complete,
            matching_customer_ids=tuple(customer_ids),
            matching_resource_count=len(customer_ids),
            additional_matching_resource_count=max(len(customer_ids) - 1, 0),
            marker_multiplicity=len(customer_ids),
            failure_reason=failure_reason,
            last_status_code=last_status_code,
            conclusion=(
                ObservationConclusion.COMPLETED_READ_NOT_H0_PROOF
                if complete
                else ObservationConclusion.UNKNOWN_INCOMPLETE
            ),
        )

    def observe_customers(self, *, email: str) -> CustomerObservationEvidence:
        """Traverse exact-email Customer LIST pages; never infer H0 from zero."""

        _require_synthetic_email(email)
        customer_ids: list[str] = []
        seen_customer_ids: set[str] = set()
        cursors: set[str] = set()
        cursor: str | None = None
        page_count = 0
        request_count = 0
        last_status = None
        while True:
            if request_count >= self.max_observation_pages:
                return self._observation_result(
                    email,
                    page_count,
                    request_count,
                    customer_ids,
                    complete=False,
                    failure_reason="page_bound_exhausted",
                    last_status_code=last_status,
                )
            query = [("email", email), ("limit", str(CUSTOMER_LIST_LIMIT))]
            if cursor is not None:
                query.append(("starting_after", cursor))
            url = STRIPE_API_ORIGIN + CUSTOMERS_PATH + "?" + urlencode(query)
            request = self._client.build_request("GET", url, headers=self._headers())
            request_count += 1
            try:
                response = self._client.send(request)
            except Exception:
                return self._observation_result(
                    email,
                    page_count,
                    request_count,
                    customer_ids,
                    complete=False,
                    failure_reason="transport_exception",
                    last_status_code=last_status,
                )
            page_count += 1
            last_status = response.status_code
            if response.is_redirect:
                return self._observation_result(
                    email,
                    page_count,
                    request_count,
                    customer_ids,
                    complete=False,
                    failure_reason="unexpected_redirect",
                    last_status_code=last_status,
                )
            if response.status_code != 200:
                return self._observation_result(
                    email,
                    page_count,
                    request_count,
                    customer_ids,
                    complete=False,
                    failure_reason="unexpected_http_status",
                    last_status_code=last_status,
                )
            try:
                payload = _decode_json(response)
                if type(payload) is not dict or payload.get("object") != "list":
                    raise ValueError("Stripe list object required")
                data = payload.get("data")
                has_more = payload.get("has_more")
                if type(data) is not list or type(has_more) is not bool:
                    raise ValueError("complete list page required")
                page_customer_ids = []
                for entry in data:
                    if type(entry) is not dict or entry.get("object") != "customer":
                        raise ValueError("Customer list entry required")
                    customer_id = _customer_id(entry.get("id"))
                    entry_email = entry.get("email")
                    if type(entry_email) is not str or type(entry.get("livemode")) is not bool:
                        raise ValueError("complete Customer evaluation fields required")
                    if entry.get("livemode") is not False:
                        raise ValueError("test-mode Customer required")
                    if entry_email != email:
                        return self._observation_result(
                            email,
                            page_count,
                            request_count,
                            customer_ids,
                            complete=False,
                            failure_reason="exact_email_filter_contract_violation",
                            last_status_code=last_status,
                        )
                    if customer_id in seen_customer_ids:
                        return self._observation_result(
                            email,
                            page_count,
                            request_count,
                            customer_ids,
                            complete=False,
                            failure_reason="repeated_customer_id_across_pages",
                            last_status_code=last_status,
                        )
                    seen_customer_ids.add(customer_id)
                    page_customer_ids.append(customer_id)
                    customer_ids.append(customer_id)
                if not has_more:
                    return self._observation_result(
                        email,
                        page_count,
                        request_count,
                        customer_ids,
                        complete=True,
                        failure_reason=None,
                        last_status_code=last_status,
                    )
                if not page_customer_ids:
                    raise ValueError("pagination cursor unavailable")
                next_cursor = page_customer_ids[-1]
                if next_cursor == cursor or next_cursor in cursors:
                    raise ValueError("pagination cursor did not advance")
                cursors.add(next_cursor)
                cursor = next_cursor
            except (TypeError, ValueError, UnicodeError, RecursionError):
                return self._observation_result(
                    email,
                    page_count,
                    request_count,
                    customer_ids,
                    complete=False,
                    failure_reason="malformed_or_nonadvancing_pagination",
                    last_status_code=last_status,
                )
