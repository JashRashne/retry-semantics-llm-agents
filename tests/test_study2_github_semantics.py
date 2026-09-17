"""Offline invariants of documentation facts and future read requirements."""

from dataclasses import FrozenInstanceError, fields, replace

import pytest

from retry_semantics.study2.candidates import GITHUB_ISSUES
from retry_semantics.study2.contracts import (
    ContractValidationError, DesignStatus, IdempotencyCapability, ObservationInput,
)
from retry_semantics.study2.github_semantics import (
    GITHUB_ISSUE_SEMANTICS as FACTS,
    GITHUB_OBSERVATION_REQUIREMENTS as READ,
)


def test_create_and_observe_are_distinct_operations_on_the_same_repository_collection():
    # Different paths would misrepresent the provider: method+path is identity.
    assert FACTS.mutation != FACTS.observation
    assert FACTS.mutation[1] == FACTS.observation[1]
    assert {FACTS.mutation[0], FACTS.observation[0]} == {"POST", "GET"}
    assert set(FACTS.required_target_parts) == {"owner", "repo"}
    for part in FACTS.required_target_parts:
        assert "{" + part + "}" in FACTS.mutation[1]


@pytest.mark.parametrize("changes", [
    {"state": "open"}, {"state": "closed"}, {"state": None},
    {"first_page": 2}, {"pagination": "first_page_only"},
    {"inspect_every_entry": False}, {"narrowing_filters_allowed": True},
    {"partial_read_is_complete": True}, {"excluded_entry_key": "unused"},
    {"required_inputs": (ObservationInput.RESPONSE_ID,)},
    {"counting_unit": "raw_list_entries"},
    {"resource_identity_source": "create_response"},
    {"resource_identity_field": "id"},
])
def test_read_requirements_cannot_be_configured_to_hide_duplicates(changes):
    # Supported Python versions differ in the dataclasses failure category.
    with pytest.raises((ValueError, TypeError)):
        replace(READ, **changes)
    with pytest.raises(TypeError):
        type(READ)(**changes)


def test_all_states_and_exhaustive_pages_are_mandatory_even_after_a_match():
    assert FACTS.default_list_state != READ.state
    assert READ.state == "all"
    assert READ.first_page == 1
    assert READ.pagination == "follow_link_next_to_exhaustion"
    assert READ.inspect_every_entry
    assert not READ.narrowing_filters_allowed
    assert not READ.partial_read_is_complete


@pytest.mark.parametrize("pr_value", [{"url": "synthetic"}, {}, None, False])
def test_pull_request_cannot_pass_issue_exclusion_even_with_identical_content(pr_value):
    issue = {"title": "synthetic content", "body": "synthetic content"}
    pull_request = {**issue, "pull_request": pr_value}
    assert READ.is_issue_entry(issue)
    assert not READ.is_issue_entry(pull_request)


@pytest.mark.parametrize("entry", [None, [], "pull_request"])
def test_type_exclusion_does_not_treat_non_objects_as_issues(entry):
    with pytest.raises(ContractValidationError):
        READ.is_issue_entry(entry)


def test_correlation_inputs_survive_total_loss_of_create_response():
    assert READ.required_inputs == GITHUB_ISSUES.observation.required_inputs
    assert ObservationInput.RESPONSE_ID not in READ.required_inputs
    assert READ.supplemental_inputs == GITHUB_ISSUES.observation.supplemental_inputs
    assert ObservationInput.TARGET_SCOPE in READ.required_inputs
    assert ObservationInput.STUDY_MARKER in READ.required_inputs
    assert READ.is_issue_entry({"title": "synthetic", "body": "synthetic"})


def test_marker_feasibility_does_not_freeze_marker_or_provider_capability():
    assert set(FACTS.content_candidates) == {"title", "body"}
    assert FACTS.raw_body_media_types  # Body feasibility is representation-dependent.
    for record in (GITHUB_ISSUES, GITHUB_ISSUES.mutation,
                   GITHUB_ISSUES.observation, GITHUB_ISSUES.correlation):
        assert record.status is DesignStatus.PROVISIONAL
    assert GITHUB_ISSUES.isolation.status is DesignStatus.UNRESOLVED
    assert GITHUB_ISSUES.idempotency.capability is IdempotencyCapability.UNKNOWN
    with pytest.raises(ContractValidationError, match="unresolved prerequisites"):
        replace(GITHUB_ISSUES, status=DesignStatus.ESTABLISHED)


def test_semantics_have_no_credentials_target_values_marker_choice_or_experiment_arm():
    for record in (FACTS, READ):
        names = {f.name for f in fields(record)}
        assert not names & {
            "token", "owner", "repo", "account", "marker", "marker_field",
            "namespace", "arm", "policy", "replay", "regeneration", "client",
        }
        with pytest.raises(TypeError):
            type(record)(token="synthetic", owner="synthetic", repo="synthetic")
        with pytest.raises(FrozenInstanceError):
            setattr(record, fields(record)[0].name, None)
        hash(record)


def test_counting_requires_distinct_resources_identified_from_list_response():
    assert READ.counting_unit == "distinct_issue_resources"
    assert READ.resource_identity_source == "list_response"
    scope = ("synthetic-owner", "synthetic-repository")
    assert READ.issue_resource_identity(scope, {"number": 17}) == (scope, 17)
    # No create-response ID is supplied; missing list number has no ID fallback.
    with pytest.raises(ContractValidationError, match="list-returned"):
        READ.issue_resource_identity(scope, {"id": 17})


def test_repeated_list_appearances_have_one_resource_identity_despite_content_changes():
    scope = ("synthetic-owner", "synthetic-repository")
    first = READ.issue_resource_identity(scope, {"number": 17, "state": "open"})
    repeated = READ.issue_resource_identity(scope, {"number": 17, "state": "closed"})
    assert first == repeated
    assert len({first, repeated}) == 1  # Two list entries cannot imply two resources.


def test_distinct_matching_issues_remain_distinguishable_with_identical_content():
    scope = ("synthetic-owner", "synthetic-repository")
    first = READ.issue_resource_identity(scope, {"number": 17, "title": "synthetic"})
    second = READ.issue_resource_identity(scope, {"number": 18, "title": "synthetic"})
    assert first != second
    assert len({first, second}) == 2


def test_issue_number_identity_is_scoped_to_the_target_repository():
    entry = {"number": 17}
    identities = {
        READ.issue_resource_identity(("synthetic-owner", "synthetic-repository"), entry),
        READ.issue_resource_identity(("synthetic-owner", "other-repository"), entry),
        READ.issue_resource_identity(("other-owner", "synthetic-repository"), entry),
    }
    assert len(identities) == 3  # Number alone has no global uniqueness claim.


@pytest.mark.parametrize("scope", [None, (), ("owner",), ("", "repo"), ["owner", "repo"]])
def test_resource_identity_cannot_omit_or_weaken_repository_scope(scope):
    with pytest.raises(ContractValidationError, match="target scope"):
        READ.issue_resource_identity(scope, {"number": 17})


@pytest.mark.parametrize("entry", [None, [], {}, {"number": None}, {"number": "17"}, {"number": True}])
def test_unavailable_or_invalid_list_identity_is_rejected_instead_of_counted(entry):
    with pytest.raises(ContractValidationError):
        READ.issue_resource_identity(("synthetic-owner", "synthetic-repository"), entry)


def test_pull_request_exclusion_is_separate_from_resource_deduplication():
    scope = ("synthetic-owner", "synthetic-repository")
    issue = {"number": 17, "title": "synthetic"}
    pull_request = {"number": 18, "title": "synthetic", "pull_request": {}}
    # An identity does not establish issue type; PR exclusion must still run.
    assert READ.issue_resource_identity(scope, issue) != READ.issue_resource_identity(scope, pull_request)
    assert READ.is_issue_entry(issue)
    assert not READ.is_issue_entry(pull_request)
