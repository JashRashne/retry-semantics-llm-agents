"""Fireworks DeepSeek candidate inputs for V1.2 engineering validation."""

from __future__ import annotations

from retry_semantics.experiment.manifest import (
    ENGINEERING_SLOT_COUNT,
    EngineeringValidationManifest,
    ManifestInvocationConfig,
    ManifestModelConfig,
    ManifestModelIdentity,
    build_engineering_validation_manifest,
)
from retry_semantics.models import (
    DEEPSEEK_V4_FLASH_0731_MODEL,
    FIREWORKS_PROVIDER,
    ModelCallConfig,
    ToolChoice,
)

FIREWORKS_DEEPSEEK_ENGINEERING_MANIFEST_ID = (
    "primary-create-v1.2-fireworks-deepseek-v4-flash-0731-eng-001"
)
FIREWORKS_DEEPSEEK_ENGINEERING_CONFIG_ID_PREFIX = (
    "fireworks-deepseek-v4-flash-0731-eng-v1-s"
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


def build_fireworks_deepseek_engineering_manifest(
) -> EngineeringValidationManifest:
    """Materialize the audited Fireworks candidate into the frozen 16 slots."""

    identity = ManifestModelIdentity(
        provider=FIREWORKS_PROVIDER,
        name=DEEPSEEK_V4_FLASH_0731_MODEL,
        version_or_digest=None,
    )
    slot_model_configs = tuple(
        ManifestModelConfig(
            model_config_id=(
                f"{FIREWORKS_DEEPSEEK_ENGINEERING_CONFIG_ID_PREFIX}{index:02d}"
            ),
            model=identity,
            original_generation=_invocation(10_000 + index),
            regeneration=_invocation(20_000 + 10 * index),
        )
        for index in range(ENGINEERING_SLOT_COUNT)
    )
    return build_engineering_validation_manifest(
        manifest_id=FIREWORKS_DEEPSEEK_ENGINEERING_MANIFEST_ID,
        slot_model_configs=slot_model_configs,
    )


__all__ = [
    "FIREWORKS_DEEPSEEK_ENGINEERING_CONFIG_ID_PREFIX",
    "FIREWORKS_DEEPSEEK_ENGINEERING_MANIFEST_ID",
    "build_fireworks_deepseek_engineering_manifest",
]
