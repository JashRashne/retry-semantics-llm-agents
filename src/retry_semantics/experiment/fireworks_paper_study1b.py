"""Separate prospective V4.1 replication of the frozen Study-1 paper design."""

from retry_semantics.experiment.manifest import (
    ManifestInvocationConfig, ManifestModelConfig, ManifestModelIdentity,
)
from retry_semantics.experiment.paper_manifest import PAPER_SLOT_COUNT, build_paper_manifest
from retry_semantics.models import FIREWORKS_PROVIDER, ModelCallConfig, ToolChoice

STUDY1B_MODEL = "accounts/fireworks/models/deepseek-v4p1-flash"
STUDY1B_MANIFEST_ID = "primary-create-v1.3-fireworks-deepseek-v4p1-flash-study1b-paper-001"
STUDY1B_CONFIG_PREFIX = "fireworks-deepseek-v4p1-flash-study1b-paper-v1-s"


def _invocation(seed: int) -> ManifestInvocationConfig:
    return ManifestInvocationConfig(
        model_call_config=ModelCallConfig(
            model=STUDY1B_MODEL, temperature=0.0, top_p=1.0, seed=seed,
            max_completion_tokens=1024, tool_choice=ToolChoice.auto(),
            parallel_tool_calls=False,
            provider_parameters={"reasoning_effort": "none"},
        ),
        seed_supported=True,
    )


def build_study1b_manifest():
    """Keep scenario allocation and seed formulas identical to Study1A."""
    identity = ManifestModelIdentity(FIREWORKS_PROVIDER, STUDY1B_MODEL, None)
    configs = tuple(
        ManifestModelConfig(
            model_config_id=f"{STUDY1B_CONFIG_PREFIX}{index:03d}",
            model=identity,
            original_generation=_invocation(30_000 + index),
            regeneration=_invocation(40_000 + 10 * index),
        )
        for index in range(PAPER_SLOT_COUNT)
    )
    return build_paper_manifest(
        manifest_id=STUDY1B_MANIFEST_ID,
        slot_model_configs=configs,
        primary_model_freeze={
            "model": identity.as_trace_model(),
            "freeze_evidence_version": "study1b-v4p1-prospective-model-freeze-v1",
            "frozen_before_paper_result_collection": True,
            "selection_basis": ["0731_SERVERLESS_REMOVED", "NON_PAPER_V4P1_CAPABILITY_PASS"],
        },
    )
