"""Small, declarative external-operation contracts. Not a frozen protocol."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ContractValidationError(ValueError):
    """An operation description is unsupported or internally contradictory."""


class Provider(str, Enum):
    GITHUB = "github"
    GOOGLE_SHEETS = "google_sheets"
    STRIPE = "stripe"


class DesignStatus(str, Enum):
    ESTABLISHED = "established"
    PROVISIONAL = "provisional"
    UNRESOLVED = "unresolved"


class RequestIdentityPart(str, Enum):
    """Must remain stable for exact replay, including options when present.

    This describes identity, not a wire format. Any later JSON representation
    should reuse retry_semantics.serialization.canonical_json_bytes; canonical
    JSON alone does not establish equality of provider HTTP requests.
    """

    OPERATION = "operation"
    TARGET_SCOPE = "target_scope"
    PAYLOAD = "payload"
    RUNTIME_OPTIONS = "runtime_options"


class ObservationInput(str, Enum):
    TARGET_SCOPE = "pre_dispatch_target_scope"
    STUDY_MARKER = "pre_dispatch_study_marker"
    RESPONSE_ID = "mutation_response_id"


class CorrelationBasis(str, Enum):
    ISOLATED_TARGET_SCOPE = "isolated_target_scope"
    SCOPE_AND_MARKER = "scope_and_marker"


class IdempotencyCapability(str, Enum):
    NO_DOCUMENTED_CLIENT_MECHANISM = "no_documented_client_mechanism"
    CLIENT_SUPPLIED_KEY = "client_supplied_key"
    UNKNOWN = "unknown"


class RuntimeKeyRequirement(str, Enum):
    RUNTIME_OWNED = "runtime_owned"
    STABLE_ACROSS_RETRIES = "stable_across_retries"


class IsolationBoundary(str, Enum):
    TRIAL_OR_FAMILY = "other_trial_or_family"
    ENGINEERING = "previous_engineering_activity"
    STALE_RESOURCES = "stale_resources"
    PROVIDER = "other_provider"
    RUN = "other_run"


def _require_type(value: object, expected: type, name: str) -> None:
    if type(value) is not expected:
        raise ContractValidationError(f"{name} must be a {expected.__name__}")


def _text(value: str, name: str) -> None:
    if type(value) is not str or not value.strip():
        raise ContractValidationError(f"{name} must be a non-empty string")


def _items(value: tuple, expected: type, name: str, *, allow_empty: bool = False) -> None:
    _require_type(value, tuple, name)
    if (not value and not allow_empty) or any(type(item) is not expected for item in value):
        raise ContractValidationError(f"{name} must contain {expected.__name__} values")
    if len(set(value)) != len(value):
        raise ContractValidationError(f"{name} must not contain duplicates")
    if expected is str:
        for item in value:
            _text(item, name)


@dataclass(frozen=True, slots=True)
class MutationOperation:
    name: str
    resource: str
    status: DesignStatus
    state_mutating: bool
    stable_request_parts: tuple[RequestIdentityPart, ...]

    def __post_init__(self) -> None:
        _text(self.name, "mutation name")
        _text(self.resource, "mutation resource")
        _require_type(self.status, DesignStatus, "mutation status")
        if self.state_mutating is not True:
            raise ContractValidationError("mutation must be state mutating")
        _items(self.stable_request_parts, RequestIdentityPart, "stable_request_parts")
        if set(self.stable_request_parts) != set(RequestIdentityPart):
            raise ContractValidationError("exact replay identity must include all request parts")


@dataclass(frozen=True, slots=True)
class ObservationOperation:
    """Required inputs must suffice without an ACK; supplements need not exist."""

    name: str
    resource: str
    status: DesignStatus
    state_mutating: bool
    required_inputs: tuple[ObservationInput, ...]
    constraints: tuple[str, ...]
    supplemental_inputs: tuple[ObservationInput, ...] = ()

    def __post_init__(self) -> None:
        _text(self.name, "observation name")
        _text(self.resource, "observation resource")
        _require_type(self.status, DesignStatus, "observation status")
        if self.state_mutating is not False:
            raise ContractValidationError("observation must be read only")
        _items(self.required_inputs, ObservationInput, "required_inputs")
        _items(self.supplemental_inputs, ObservationInput, "supplemental_inputs", allow_empty=True)
        if set(self.required_inputs) & set(self.supplemental_inputs):
            raise ContractValidationError("required and supplemental inputs must not overlap")
        _items(self.constraints, str, "observation constraints")
        if ObservationInput.RESPONSE_ID in self.required_inputs:
            raise ContractValidationError("observation cannot require a lost mutation response ID")
        if ObservationInput.TARGET_SCOPE not in self.required_inputs:
            raise ContractValidationError("observation requires pre-dispatch target scope")


@dataclass(frozen=True, slots=True)
class CorrelationCapability:
    status: DesignStatus
    basis: CorrelationBasis
    pre_dispatch_marker_supported: bool | None
    constraints: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_type(self.status, DesignStatus, "correlation status")
        _require_type(self.basis, CorrelationBasis, "correlation basis")
        if self.pre_dispatch_marker_supported is not None:
            _require_type(self.pre_dispatch_marker_supported, bool, "marker support")
        _items(self.constraints, str, "correlation constraints")
        if (
            self.status is DesignStatus.ESTABLISHED
            and self.basis is CorrelationBasis.SCOPE_AND_MARKER
            and self.pre_dispatch_marker_supported is not True
        ):
            raise ContractValidationError("established correlation requires marker support")


@dataclass(frozen=True, slots=True)
class ProviderIdempotency:
    """API capability only, not enablement or an agent retry policy.

    runtime_key_requirements apply ONLY IF a future runtime enables the key.
    They constrain the key, not mutation parameters. key_reuse_constraints
    describe provider comparison/mismatch behavior, which may be unresolved.
    No value here asserts mathematical idempotence or non-duplication.
    """

    capability: IdempotencyCapability
    basis: str
    mechanism: str | None
    runtime_key_requirements: tuple[RuntimeKeyRequirement, ...]
    key_reuse_constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_type(self.capability, IdempotencyCapability, "idempotency capability")
        _text(self.basis, "idempotency basis")
        _require_type(self.runtime_key_requirements, tuple, "runtime_key_requirements")
        _items(self.key_reuse_constraints, str, "key_reuse_constraints", allow_empty=True)
        if self.capability is IdempotencyCapability.CLIENT_SUPPLIED_KEY:
            _text(self.mechanism, "key mechanism")
            _items(self.runtime_key_requirements, RuntimeKeyRequirement, "runtime_key_requirements")
            if set(self.runtime_key_requirements) != set(RuntimeKeyRequirement):
                raise ContractValidationError("key reuse requires runtime ownership and stability")
        elif self.mechanism is not None or self.runtime_key_requirements or self.key_reuse_constraints:
            raise ContractValidationError("key requirements require documented key support")


@dataclass(frozen=True, slots=True)
class IsolationRequirements:
    status: DesignStatus
    distinguish_from: tuple[IsolationBoundary, ...]
    constraints: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_type(self.status, DesignStatus, "isolation status")
        _items(self.distinguish_from, IsolationBoundary, "distinguish_from")
        _items(self.constraints, str, "isolation constraints")
        if set(self.distinguish_from) != set(IsolationBoundary):
            raise ContractValidationError("all isolation boundaries must be explicit")


@dataclass(frozen=True, slots=True)
class OperationCapability:
    provider: Provider
    status: DesignStatus
    mutation: MutationOperation
    observation: ObservationOperation
    correlation: CorrelationCapability
    idempotency: ProviderIdempotency
    isolation: IsolationRequirements

    def __post_init__(self) -> None:
        for name, expected in (
            ("provider", Provider), ("status", DesignStatus),
            ("mutation", MutationOperation), ("observation", ObservationOperation),
            ("correlation", CorrelationCapability), ("idempotency", ProviderIdempotency),
            ("isolation", IsolationRequirements),
        ):
            _require_type(getattr(self, name), expected, name)
        if self.mutation.resource != self.observation.resource:
            raise ContractValidationError("observation must inspect the mutation resource")
        if self.mutation.name == self.observation.name:
            raise ContractValidationError("mutation and observation must be distinct")
        requires_marker = ObservationInput.STUDY_MARKER in self.observation.required_inputs
        if requires_marker != (self.correlation.basis is CorrelationBasis.SCOPE_AND_MARKER):
            raise ContractValidationError("correlation basis must match required observation inputs")
        uses_marker = requires_marker or (
            ObservationInput.STUDY_MARKER in self.observation.supplemental_inputs
        )
        if uses_marker and self.correlation.pre_dispatch_marker_supported is False:
            raise ContractValidationError("marker-based observation requires possible marker support")
        if self.status is DesignStatus.ESTABLISHED and (
            self.mutation.status is not DesignStatus.ESTABLISHED
            or self.observation.status is not DesignStatus.ESTABLISHED
            or self.correlation.status is not DesignStatus.ESTABLISHED
            or self.isolation.status is not DesignStatus.ESTABLISHED
            or self.idempotency.capability is IdempotencyCapability.UNKNOWN
        ):
            raise ContractValidationError("established capability has unresolved prerequisites")
