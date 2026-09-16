"""Frozen Fireworks DeepSeek configuration for the V1.3 paper collection."""

from __future__ import annotations

from retry_semantics.experiment.manifest import (
    ManifestInvocationConfig,
    ManifestModelConfig,
    ManifestModelIdentity,
)
from retry_semantics.experiment.paper_manifest import (
    PAPER_SLOT_COUNT,
    PaperExperimentManifest,
    build_paper_manifest,
)
from retry_semantics.models import (
    DEEPSEEK_V4_FLASH_0731_MODEL,
    FIREWORKS_PROVIDER,
    ModelCallConfig,
    ToolChoice,
)

FIREWORKS_DEEPSEEK_PAPER_MANIFEST_ID = (
    "primary-create-v1.3-fireworks-deepseek-v4-flash-0731-paper-001"
)
FIREWORKS_DEEPSEEK_PAPER_CONFIG_ID_PREFIX = (
    "fireworks-deepseek-v4-flash-0731-paper-v1-s"
)


def _invocation(seed: int) -> ManifestInvocationConfig:
    return ManifestInvocationConfig(
        model_call_config=ModelCallConfig(
            model=DEEPSEEK_V4_FLASH_0731_MODEL,
            temperature=0.0,
            top_p=1.0,
            seed=seed,
            max_completion_tokens=1024,
            tool_choice=ToolChoice.auto(),
            parallel_tool_calls=False,
            provider_parameters={"reasoning_effort": "none"},
        ),
        seed_supported=True,
    )


def build_fireworks_deepseek_paper_manifest() -> PaperExperimentManifest:
    """Build the exact audited 160-slot primary Ticket paper manifest."""

    identity = ManifestModelIdentity(
        provider=FIREWORKS_PROVIDER,
        name=DEEPSEEK_V4_FLASH_0731_MODEL,
        version_or_digest=None,
    )
    configs = tuple(
        ManifestModelConfig(
            model_config_id=f"{FIREWORKS_DEEPSEEK_PAPER_CONFIG_ID_PREFIX}{index:03d}",
            model=identity,
            original_generation=_invocation(30_000 + index),
            regeneration=_invocation(40_000 + 10 * index),
        )
        for index in range(PAPER_SLOT_COUNT)
    )
    return build_paper_manifest(
        manifest_id=FIREWORKS_DEEPSEEK_PAPER_MANIFEST_ID,
        slot_model_configs=configs,
        primary_model_freeze={
            "model": identity.as_trace_model(),
            "engineering_gate": {
                "manifest_id": "primary-create-v1.2-fireworks-deepseek-v4-flash-0731-eng-001",
                "manifest_sha256": "18a128c9ff33997ae1713987bbc3bcde5bf1c597adae8df8970037edcb5c0a7b",
                "paper_denominator": False,
                "status": "PASSED",
                "use": "PROTOCOL_COMPATIBILITY_VALIDATION_ONLY",
            },
            "freeze_evidence_version": "primary-model-freeze-v1",
            "frozen_before_paper_result_collection": True,
            "selection_basis": [
                "PROTOCOL_COMPATIBILITY",
                "SUFFICIENT_FUNCTION_TOOL_CAPABILITY",
                "PRACTICAL_STUDENT_BUDGET",
                "SEPARATE_ENGINEERING_GATE_PASSED",
            ],
        },
    )


__all__ = [
    "FIREWORKS_DEEPSEEK_PAPER_CONFIG_ID_PREFIX",
    "FIREWORKS_DEEPSEEK_PAPER_MANIFEST_ID",
    "build_fireworks_deepseek_paper_manifest",
]
