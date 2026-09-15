"""Deterministic runtime primitives for retry-semantics experiments."""

from retry_semantics.runtime.exact_replay import (
    EXACT_REPLAY,
    REPLAY_EXECUTED,
    ExactReplayResult,
    RecoveryLatency,
    ReplayProtocolError,
    execute_exact_replay,
)

from retry_semantics.runtime.hidden_worlds import (
    ConstructedHiddenWorld,
    HiddenWorld,
    HiddenWorldArmStates,
    PolicyArmStartingState,
    TrialFamilyConstructionError,
    TrialFamilyStates,
    construct_trial_family_states,
    validate_trial_family_states,
)
from retry_semantics.runtime.regeneration_context import (
    CANONICAL_AMBIGUITY_TEXT,
    FROZEN_SYSTEM_MESSAGE,
    FROZEN_TOOL_CATALOG,
    CanonicalContextMessage,
    CanonicalRegenerationContext,
    CanonicalToolCall,
    CreateTicketArguments,
    FrozenToolDefinition,
    ModelVisibleToolCall,
    RegenerationContextProtocolError,
    build_canonical_regeneration_context,
    validate_regeneration_context,
)

__all__ = [
    "EXACT_REPLAY",
    "REPLAY_EXECUTED",
    "CANONICAL_AMBIGUITY_TEXT",
    "FROZEN_SYSTEM_MESSAGE",
    "FROZEN_TOOL_CATALOG",
    "CanonicalContextMessage",
    "CanonicalRegenerationContext",
    "CanonicalToolCall",
    "ConstructedHiddenWorld",
    "CreateTicketArguments",
    "ExactReplayResult",
    "RecoveryLatency",
    "FrozenToolDefinition",
    "HiddenWorld",
    "HiddenWorldArmStates",
    "ModelVisibleToolCall",
    "PolicyArmStartingState",
    "ReplayProtocolError",
    "RegenerationContextProtocolError",
    "TrialFamilyConstructionError",
    "TrialFamilyStates",
    "build_canonical_regeneration_context",
    "construct_trial_family_states",
    "execute_exact_replay",
    "validate_regeneration_context",
    "validate_trial_family_states",
]
