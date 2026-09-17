"""Documentation facts and minimum future read requirements, not an adapter.

Checked 2026-09-17; sources and limitations: research/study2/github/
GITHUB_SEMANTICS_DRAFT.md. Requirements are Study 2 design obligations,
not claims that GitHub provides an atomic or eventually consistent snapshot.
No target values, marker encoding, timing, transport, or execution policy.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from retry_semantics.study2.contracts import ContractValidationError, ObservationInput


@dataclass(frozen=True, slots=True)
class GitHubIssueSemantics:
    """Fixed provider facts; these are not configurable request options."""

    mutation: tuple[str, str] = field(
        default=("POST", "/repos/{owner}/{repo}/issues"), init=False,
    )
    observation: tuple[str, str] = field(
        default=("GET", "/repos/{owner}/{repo}/issues"), init=False,
    )
    required_target_parts: tuple[str, ...] = field(default=("owner", "repo"), init=False)
    content_candidates: tuple[str, ...] = field(default=("title", "body"), init=False)
    raw_body_media_types: tuple[str, ...] = field(default=(
        "application/vnd.github.raw+json", "application/vnd.github.full+json",
    ), init=False)
    default_list_state: str = field(default="open", init=False)
    default_per_page: int = field(default=30, init=False)
    maximum_per_page: int = field(default=100, init=False)
    create_statuses: tuple[int, ...] = field(
        default=(201, 400, 403, 404, 410, 422, 503), init=False,
    )
    list_statuses: tuple[int, ...] = field(default=(200, 301, 404, 422), init=False)
    rate_limit_statuses: tuple[int, ...] = field(default=(403, 429), init=False)


@dataclass(frozen=True, slots=True)
class GitHubObservationRequirements:
    """Necessary conditions for a later complete read; not proof of visibility.

    Start at page 1 in the pre-dispatch repository, preserve state=all and
    representation across every Link next page, and inspect every entry.
    A failed/missing page or inaccessible correlation field is incomplete,
    never an empty result. Membership still needs a validated scope/marker.
    """

    state: Literal["all"] = field(default="all", init=False)
    first_page: int = field(default=1, init=False)
    pagination: Literal["follow_link_next_to_exhaustion"] = field(
        default="follow_link_next_to_exhaustion", init=False,
    )
    inspect_every_entry: bool = field(default=True, init=False)
    narrowing_filters_allowed: bool = field(default=False, init=False)
    partial_read_is_complete: bool = field(default=False, init=False)
    required_inputs: tuple[ObservationInput, ...] = field(default=(
        ObservationInput.TARGET_SCOPE, ObservationInput.STUDY_MARKER,
    ), init=False)
    supplemental_inputs: tuple[ObservationInput, ...] = field(
        default=(ObservationInput.RESPONSE_ID,), init=False,
    )
    excluded_entry_key: Literal["pull_request"] = field(default="pull_request", init=False)
    counting_unit: Literal["distinct_issue_resources"] = field(
        default="distinct_issue_resources", init=False,
    )
    resource_identity_source: Literal["list_response"] = field(
        default="list_response", init=False,
    )
    resource_identity_field: Literal["number"] = field(default="number", init=False)

    def issue_resource_identity(
        self, target_repository: tuple[str, str], list_entry: Mapping[str, object],
    ) -> tuple[tuple[str, str], int]:
        """Identity for distinct-resource counting, not correlation or collection.

        Use the same pre-dispatch (owner, repo) scope throughout a traversal.
        Number is repository-scoped, not globally unique. Repeated appearances
        MUST count once by this identity, irrespective of other entry fields.
        Pull-request exclusion is a separate prerequisite to issue counting.
        """
        if (
            type(target_repository) is not tuple or len(target_repository) != 2
            or any(type(part) is not str or not part.strip() for part in target_repository)
        ):
            raise ContractValidationError("identity requires an (owner, repo) target scope")
        if not isinstance(list_entry, Mapping):
            raise ContractValidationError("identity requires a list-response mapping")
        number = list_entry.get(self.resource_identity_field)
        if type(number) is not int:
            raise ContractValidationError("identity requires a list-returned integer issue number")
        return target_repository, number

    def is_issue_entry(self, entry: Mapping[str, object]) -> bool:
        """Type exclusion only, never trial membership or full response validation.

        Key presence excludes even an empty/null value; truthiness is unsafe.
        The later adapter must validate responses before using this predicate.
        """
        if not isinstance(entry, Mapping):
            raise ContractValidationError("issue-list entry must be a mapping")
        return self.excluded_entry_key not in entry


GITHUB_ISSUE_SEMANTICS = GitHubIssueSemantics()
GITHUB_OBSERVATION_REQUIREMENTS = GitHubObservationRequirements()
