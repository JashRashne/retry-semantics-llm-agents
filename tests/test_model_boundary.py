from __future__ import annotations

import json
import math
from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from retry_semantics.environments.ticket import SourceStage, TicketEnvironment
from retry_semantics.models import (
    ModelCallConfig,
    ModelClient,
    ModelRequest,
    ModelRequestError,
    ModelResponse,
    ToolChoice,
    ToolChoiceMode,
    model_request_from_regeneration_context,
)
from retry_semantics.runtime.hidden_worlds import construct_trial_family_states
from retry_semantics.runtime.regeneration_context import (
    CanonicalContextMessage,
    CanonicalToolCall,
    CreateTicketArguments,
    build_canonical_regeneration_context,
)

USER_TASK = (
    'Create exactly one support ticket for customer "CUST-001" with title '
    '"Login page timeout" and description '
    '"The login page times out after 30 seconds.".'
)


def _family(request):
    return construct_trial_family_states(
        initial_state=TicketEnvironment.empty(),
        frozen_original_request=request,
        serialized_original_request=request.serialized_request,
        original_request_hash=request.request_hash,
        original_source_stage=SourceStage.ORIGINAL,
        original_arm_id=None,
    )


def _assistant_message(request, arguments_json: str | None = None):
    value = json.loads(request.serialized_request)
    arguments = value["arguments"]
    return CanonicalContextMessage(
        role="assistant",
        content=None,
        tool_calls=(
            CanonicalToolCall(
                tool_call_id=value["tool_call_id"],
                tool=value["tool"],
                arguments_json=(
                    json.dumps(arguments, separators=(",", ":"))
                    if arguments_json is None
                    else arguments_json
                ),
                arguments=CreateTicketArguments(**arguments),
            ),
        ),
        tool_call_id=None,
    )


def _context(request, arguments_json: str | None = None):
    return build_canonical_regeneration_context(
        user_task=USER_TASK,
        frozen_original_request=request,
        original_assistant_message=_assistant_message(request, arguments_json),
    )


def _config(seed: int | None = 17):
    return ModelCallConfig(
        model="test-model",
        temperature=0.0,
        seed=seed,
        max_completion_tokens=256,
        tool_choice=ToolChoice.auto(),
    )


def test_tool_choice_supports_all_required_provider_neutral_modes() -> None:
    assert ToolChoice.auto().mode is ToolChoiceMode.AUTO
    assert ToolChoice.required().mode is ToolChoiceMode.REQUIRED
    assert ToolChoice.none().mode is ToolChoiceMode.NONE
    forced = ToolChoice.forced_function("create_ticket")
    assert forced.mode is ToolChoiceMode.FORCED_FUNCTION
    assert forced.function_name == "create_ticket"


def test_forced_tool_choice_requires_a_name_and_other_modes_reject_one() -> None:
    with pytest.raises(ModelRequestError):
        ToolChoice(ToolChoiceMode.FORCED_FUNCTION)
    with pytest.raises(ModelRequestError):
        ToolChoice(ToolChoiceMode.AUTO, "create_ticket")


def test_model_call_config_is_immutable() -> None:
    config = _config()

    with pytest.raises(FrozenInstanceError):
        config.seed = 18  # type: ignore[misc]


def test_model_request_retains_complete_execution_configuration(make_request) -> None:
    input_parameters = {
        "reasoning": {"effort": "medium"},
        "tags": ["engineering", "v1.2"],
    }
    config = ModelCallConfig(
        model="test-model",
        temperature=0.25,
        seed=41,
        max_completion_tokens=321,
        tool_choice=ToolChoice.auto(),
        top_p=0.8,
        parallel_tool_calls=False,
        provider_parameters=input_parameters,
    )
    request = model_request_from_regeneration_context(
        _context(make_request()), config
    )

    input_parameters["reasoning"]["effort"] = "changed"  # type: ignore[index]
    assert request.model_config is config
    assert request.model_config.top_p == 0.8
    assert request.model_config.parallel_tool_calls is False
    assert request.model_config.provider_parameters == {
        "reasoning": {"effort": "medium"},
        "tags": ("engineering", "v1.2"),
    }
    assert type(request.model_config.provider_parameters) is MappingProxyType
    assert type(request.model_config.provider_parameters["reasoning"]) is (
        MappingProxyType
    )
    with pytest.raises(TypeError):
        request.model_config.provider_parameters["mode"] = (  # type: ignore[index]
            "changed"
        )


@pytest.mark.parametrize("top_p", [-0.01, 1.01, float("inf"), float("nan"), True])
def test_model_call_config_rejects_invalid_top_p(top_p: object) -> None:
    with pytest.raises(ModelRequestError, match="top_p"):
        ModelCallConfig(
            model="test-model",
            temperature=0.0,
            seed=1,
            max_completion_tokens=256,
            tool_choice=ToolChoice.auto(),
            top_p=top_p,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("parallel_tool_calls", [0, 1, "false", object()])
def test_model_call_config_rejects_invalid_parallel_tool_value(
    parallel_tool_calls: object,
) -> None:
    with pytest.raises(ModelRequestError, match="parallel_tool_calls"):
        ModelCallConfig(
            model="test-model",
            temperature=0.0,
            seed=1,
            max_completion_tokens=256,
            tool_choice=ToolChoice.auto(),
            parallel_tool_calls=parallel_tool_calls,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "provider_parameters",
    [
        [],
        {"unsupported_value": object()},
        {"non_finite": float("nan")},
        {1: "non-string key"},
        {"temperature": 0.2},
        {"nested": {"api_key": "secret"}},
    ],
)
def test_model_call_config_rejects_invalid_provider_parameters(
    provider_parameters: object,
) -> None:
    with pytest.raises(ModelRequestError, match="provider_parameters"):
        ModelCallConfig(
            model="test-model",
            temperature=0.0,
            seed=1,
            max_completion_tokens=256,
            tool_choice=ToolChoice.auto(),
            provider_parameters=provider_parameters,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(("temperature", "top_p"), [(0, -0.0), (-0.0, 1)])
def test_sampling_numbers_are_normalized_to_canonical_floats(
    temperature: float,
    top_p: float,
) -> None:
    config = ModelCallConfig(
        model="test-model",
        temperature=temperature,
        seed=1,
        max_completion_tokens=256,
        tool_choice=ToolChoice.auto(),
        top_p=top_p,
    )

    assert type(config.temperature) is float
    assert type(config.top_p) is float
    if config.temperature == 0.0:
        assert math.copysign(1.0, config.temperature) == 1.0
    if config.top_p == 0.0:
        assert math.copysign(1.0, config.top_p) == 1.0


def test_provider_neutral_request_contains_only_messages_tools_and_config(
    make_request,
) -> None:
    request = model_request_from_regeneration_context(
        _context(make_request()), _config()
    )

    assert set(request.__dataclass_fields__) == {
        "messages",
        "tools",
        "model_config",
    }
    for forbidden in (
        "hidden_world",
        "environment",
        "state_snapshot",
        "evaluator_result",
        "mutation_events",
        "dispatch_count",
        "policy_outcome",
    ):
        assert forbidden not in request.__dataclass_fields__


def test_context_hash_is_independent_of_model_call_config_and_seed(
    make_request,
) -> None:
    context = _context(make_request())
    before_bytes = context.canonical_context_bytes
    before_hash = context.canonical_context_sha256

    first = model_request_from_regeneration_context(context, _config(seed=1))
    second = model_request_from_regeneration_context(context, _config(seed=2))

    assert context.canonical_context_bytes == before_bytes
    assert context.canonical_context_sha256 == before_hash
    assert first.messages == second.messages
    assert first.tools == second.tools
    assert first.model_config.seed == 1
    assert second.model_config.seed == 2


def test_h0_h1_create_identical_provider_neutral_requests(make_request) -> None:
    original = make_request(tool_call_id="original-call")
    family = _family(original)
    assistant = _assistant_message(
        original,
        '{ "title": "Login page timeout", "customer_id": "CUST-001", '
        '"description": "The login page times out after 30 seconds." }',
    )
    h0_context = build_canonical_regeneration_context(
        user_task=USER_TASK,
        frozen_original_request=(
            family.not_executed.arm_states.llm_regeneration_state
            .frozen_original_request
        ),
        original_assistant_message=assistant,
    )
    h1_context = build_canonical_regeneration_context(
        user_task=USER_TASK,
        frozen_original_request=(
            family.executed_ack_lost.arm_states.llm_regeneration_state
            .frozen_original_request
        ),
        original_assistant_message=assistant,
    )

    assert h0_context == h1_context
    assert model_request_from_regeneration_context(
        h0_context, _config()
    ) == model_request_from_regeneration_context(h1_context, _config())


def test_fake_client_can_implement_the_small_protocol(make_request) -> None:
    class FakeClient:
        def complete(self, request: ModelRequest) -> ModelResponse:
            raise NotImplementedError

    assert isinstance(FakeClient(), ModelClient)
