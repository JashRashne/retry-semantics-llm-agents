"""Non-treatment model-boundary measurement identities and immutable facts."""

from dataclasses import dataclass

RESPONSE_FAILURE_STAGES = {
    "PROVIDER_RESPONSE_STRUCTURE": (
        "COMPLETION_ENVELOPE", "CHOICE_ENVELOPE", "NON_JSON_SUCCESS_BODY",
        "FINISH_REASON", "COMPLETION_MODEL", "TOKEN_USAGE",
        "SYSTEM_FINGERPRINT", "COMPLETION_ID",
    ),
    "MODEL_GENERATION_STRUCTURE": (
        "ASSISTANT_MESSAGE", "TOOL_CALL_LIST", "TOOL_CALL_FUNCTION",
        "TOOL_CALL_ID", "TOOL_CALL_NAME", "TOOL_CALL_ARGUMENTS",
        "TOOL_CALL_TYPE", "ASSISTANT_ROLE", "ASSISTANT_CONTENT",
        "ASSISTANT_MESSAGE_CAPTURE",
    ),
    "PROTOCOL_COMPATIBILITY": ("REASONING_POLICY",),
    "IMPLEMENTATION_INCOHERENCE": (
        "LOCAL_CAPTURE_CONFIGURATION", "TOOL_CALL_PARSE_METADATA",
        "RECOVERY_PARSE_METADATA",
        "MODEL_CLIENT_RETURN_TYPE",
    ),
}


@dataclass(frozen=True, slots=True)
class ResponseFailureEvidence:
    category: str
    stage: str

    def __post_init__(self):
        if self.stage not in RESPONSE_FAILURE_STAGES.get(self.category, ()):
            raise ValueError("unknown model response failure category/stage")

    def as_dict(self):
        return {"evidence_version": "model-response-failure-v2",
                "category": self.category, "stage": self.stage}


@dataclass(frozen=True, slots=True)
class ProviderRequestDispatchEvidence:
    """Transport invocation was attempted; does not assert server receipt."""
    invocation_sequence: int
    provider_request_dispatched: bool = False
    provider_response_returned: bool = False

    def __post_init__(self):
        if type(self.invocation_sequence) is not int or self.invocation_sequence < 0:
            raise ValueError("invalid provider invocation sequence")
        if type(self.provider_request_dispatched) is not bool or type(self.provider_response_returned) is not bool:
            raise ValueError("dispatch/response evidence must be boolean")
        if self.provider_response_returned and not self.provider_request_dispatched:
            raise ValueError("a returned provider response requires a transport attempt")

    def as_dict(self):
        return {"request_dispatch_evidence_version": "provider-request-dispatch-v1",
                "provider_invocation_sequence": self.invocation_sequence,
                "provider_request_dispatched": self.provider_request_dispatched,
                "provider_response_returned": self.provider_response_returned}
