DRAFT — NOT FROZEN — ZERO PAPER OBSERVATIONS

Study 2 Phase 2A documentation reconnaissance, checked **2026-09-17**.
Phase 1 milestone: `b34f8a7`. This is an engineering note, not the protocol.
No live GitHub API request was made, no token was used, and no issue was
created/modified. Documentation retrieval only; all cited pages were available.
No Study 2 paper observations exist. Study 1 remains closed.
The narrow remediation reused documentation retrieved during Phase 2A; no new
network or API call was made for remediation.

### Official documentation checked

- [Issues](https://docs.github.com/en/rest/issues/issues): repository listing,
  creation, examples, media types, permissions, status tables; update duplicate fields.
- [Pagination](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api): Link relations and traversal.
- [Best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api): serialization, mutation spacing, errors,
  redirects, conditional requests, stable list ordering.
- [Rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api): secondary limits and rate-limit responses.
- [Troubleshooting](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api): visibility, missing results, timeouts, permissions.
- [Getting started](https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api): methods, paths, headers, representations.
  Also checked the [older resources URL](https://docs.github.com/en/rest/overview/resources-in-the-rest-api), which redirects here.
- [JavaScript scripting](https://docs.github.com/en/rest/guides/scripting-with-the-rest-api-and-javascript): documented SDK retry behavior.
- [Dependency submission](https://docs.github.com/en/rest/dependency-graph/dependency-submission): deduplication search result assessed for applicability.
- [GitHub event types](https://docs.github.com/en/rest/using-the-rest-api/github-event-types): inspected during reconnaissance; not a basis for create/list guarantees.

Unversioned GitHub.com REST documentation was checked as retrieved on this date.
No API version is selected or frozen; a later adapter must bind and validate its
version and representation. No third-party source or SDK implementation supplies
provider evidence here.

### Established endpoint facts

Creation is `POST /repos/{owner}/{repo}/issues`; observation is
`GET /repos/{owner}/{repo}/issues`. Required path identities are owner and repo
(repository name without `.git`, both case-insensitive). Creation requires title;
body is writable. List examples include title/body. Listing defaults to
`state=open`, accepts `all`, and defaults to 30 entries/page, maximum 100.
Pull requests are distinguished by the `pull_request` key. Raw media type
`application/vnd.github.raw+json` includes body; full includes body/body_text/body_html;
text and HTML instead expose transformed body fields. Fine-grained permissions
are Issues write for creation and Issues read for listing; public listing can
be unauthenticated. Creation triggers notifications and can face secondary
limits. Labels can be silently dropped without push access.
[Source: issues](https://docs.github.com/en/rest/issues/issues).

Documented create statuses: **201 Created**, 400 Bad Request, 403 Forbidden,
404 Not Found, 410 Gone (issues disabled), 422 validation/spam, 503 unavailable.
List statuses: **200 OK**, 301 permanent redirect, 404 Not Found, 422 validation/spam.
These tables do not establish commit/noncommit guarantees after response loss,
timeout, or server failure; they are not an exhaustive failure classifier.
[Source: endpoint status tables](https://docs.github.com/en/rest/issues/issues).

Pagination supplies response Link URLs, including `rel="next"`. A last-page
link is not always available; single-page results can omit Link entirely.
[Source: pagination](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api).

### Minimum later observation contract (Study 2 requirements)

The immutable `github_semantics.py` record separates provider facts from these
design obligations. It is independent of Replay/Regeneration and performs no
dispatch. The generic GitHub candidate and all its strategies stay provisional.

Given owner/repository and study-controlled correlation content known **before
dispatch**, a complete observation must enumerate the entire selected repository
collection from page 1 with explicit **state=all**, follow every next Link until
exhaustion, inspect every entry, exclude pull requests by **key presence**, and
collect every issue belonging to the intended trial/family under a subsequently
validated correlation/isolation rule. Never stop on a match or infer membership
from list ordering, nearest timestamp, newest issue, or a create-response ID.

No narrowing filters (since, creator, assignee, labels, milestone, type, etc.)
are allowed by this minimum read contract. Preserve target scope, all-state
selection, and representation throughout traversal. Page size remains undecided;
100 is a ceiling, not completeness. An inaccessible/failed/malformed page,
unavailable correlation field, or incomplete traversal is **incomplete/unknown**,
never zero matching issues. A conditional 304 alone supplies no enumeration;
any future cache would need validated, complete corresponding representations.

The pure `is_issue_entry` predicate only excludes entries containing
`pull_request`, including empty/null values. Passing it does not prove trial
membership or validate the rest of a response. Later response validation must
precede counting. Matching observations MUST be counted as **distinct GitHub issue
resources**, never raw list entries. The machine-readable counting unit is
`distinct_issue_resources`, identity source is `list_response`, and identity field
is `number`. The identity is **((target owner, target repository), list-returned
issue number)**, using the same pre-dispatch repository scope throughout the read.
Creation-response IDs are optional supplements and cannot locate the family,
select its members, or supply the required deduplication identity.

The previously retrieved repository-list response includes `number`; Get an
issue documents `issue_number` as the number identifying the issue, within
`/repos/{owner}/{repo}/issues/{issue_number}`. This supports repository-scoped
identity, not global number uniqueness. Pull-request exclusion remains mandatory
and separate. The pure `issue_resource_identity` projection requires an integer
list-returned number and an explicit (owner, repo) scope; no fallback to a
create-response ID is allowed. It performs no pagination or collection.
[Identity basis: issues, repository listing and Get an issue](https://docs.github.com/en/rest/issues/issues).

A **duplicate LIST ENTRY** from page movement repeats the same scoped issue
identity and MUST count once, even if content/state changes between appearances.
**Distinct matching ISSUE RESOURCES** have different scoped issue identities
and remain separately countable, even with identical study-controlled content.
Those distinct resources can represent duplicate mutation effects; repeated
appearances of one resource cannot represent multiple mutations.

Traversal completeness is necessary, not a snapshot or eventual-visibility
guarantee. GitHub warns that additions/removals can shift pages even with stable
ordering. Concurrent changes, missing markers, deletion/transfer, and restricted
visibility can defeat a census. Isolation, preservation, convergence and eventual
enumeration still need engineering validation. No polling interval, waiting
duration, consistency timing or termination schedule is selected here.
Resource deduplication prevents false over-counting; it does NOT recover resources
missed because of page movement or guarantee a consistent snapshot.
[Page movement source: best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#make-requests-that-can-be-cached).

### Marker feasibility and unresolved questions

**Title and raw body are plausible candidates in principle, not a selected marker
design.** The API input/output descriptions support carrying pre-dispatch content;
they do not validate exact preservation for our eventual encoding. Nothing here
chooses title/body/both/labels, a marker string, namespace, account or repository.
Labels are not promoted to an equivalent candidate because of permission-dependent
dropping. Missing fields or transformed content cannot silently become nonmatches.

Live engineering validation is still needed for exact content round-trip,
Unicode/markdown/null/length edge cases for whichever candidate is later selected,
representation/decoder field availability, marker retention under future generated
parameter changes, edits and repository automation, collisions and isolation,
all-page visibility, concurrent page movement, and post-create list visibility.
Reason: documentation descriptions/examples do not provide experimental checks or
an exhaustive persistence/consistency guarantee. No such validation occurred.

Permissions remain unresolved for the eventual target/principal: documentation
cannot show access to an unselected repository. Private inaccessible resources
can return 404; paginated reads can omit resources unavailable to credentials.
“Not observed” therefore cannot by itself mean “not committed.” Timeout
documentation describes server termination, without a create-commit guarantee.
[Source: troubleshooting](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api).

### Idempotency audit: UNKNOWN retained

Checked create parameters/headers, general requests/headers/media documentation,
and conditional-request guidance. Searched official REST documentation for
`Idempotency-Key`, `idempotency`, `idempotent`, `deduplication`, `deduplicate`,
duplicate requests/create issue, and `If-None-Match` with POST. The issue page and
general getting-started page had no `idempoten...` match. No applicable create
mechanism was established. Search coverage is not exhaustive negative evidence.

The documented issue-update `duplicate_issue_id` marks an existing issue as a
duplicate; it is not described as deduplicating create requests. Dependency
submission's correlator/detector grouping applies to dependency snapshots, not
issue creation. These results do not establish a cross-endpoint mechanism.
[Sources: issues](https://docs.github.com/en/rest/issues/issues#update-an-issue),
[dependency submission](https://docs.github.com/en/rest/dependency-graph/dependency-submission).

GitHub says conditional unsafe-method requests are unsupported unless an endpoint
documents otherwise; creation documents no such exception in the inspected page.
This narrows one avenue, without excluding every client-controlled mechanism.
No explicit authoritative statement establishing absence was found. Thus
**IdempotencyCapability.UNKNOWN** remains; absence of a named key alone is
insufficient. Neither non-idempotence nor guaranteed duplicate creation is claimed.
[Source: conditional requests](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#use-conditional-requests).

### Hidden behavior and experiment interference

**A — documented by GitHub.** Best practices recommend serialized requests and,
for many mutations, at least one second between requests. Rate-limit handling
uses Retry-After, remaining/reset headers, otherwise at least a minute and
increasing waits on continued secondary failures. Continuing can cause a ban.
These are provider recommendations, not an implemented retry policy or chosen
experiment schedule. GitHub documents redirects (301, 302, 307 and potentially
others), advises following Location, and warns against ignoring repeated 4xx/5xx
and validation failures.
[Source: best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).

Rate-limit failures can be 403/429. Secondary limits cover concurrency, endpoint
points, CPU and content creation; content activity includes web/REST/GraphQL.
Thresholds can change and reasons can be undisclosed; secondary budget cannot be
queried. Other activity and preceding mutations could therefore interfere across
arms. Spam/abuse controls and notifications add operational side effects; no safe
throughput or independent arm behavior is established for an eventual target.
[Source: rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

GitHub's JavaScript guide states Octokit.js automatically retries requests on
errors except 400/401/403/404/422. This is a documented SDK risk, not a guarantee
about any eventual chosen dependency or its POST configuration.
[Source: catching errors](https://docs.github.com/en/rest/guides/scripting-with-the-rest-api-and-javascript#catching-all-errors).

**B — dependent on our eventual implementation.** Actual SDK/middleware and
HTTP-library retry defaults, connection recovery, redirect method/body handling,
credential forwarding, timeout behavior, cache/304 handling, header exposure,
field projection and error classification require inspection of the chosen
version/configuration and later engineering validation. POST retransmission
could add hidden attempts. No library is chosen, and no hidden retry behavior is
implemented or asserted for this project. Missing/lost responses and 5xx must not
be converted to a documented noncommit assumption.

### Adversarial answers

1. **Page 2+ duplicate?** Yes under a truncated read; contract requires exhaustive
   next-Link traversal even after matches.
2. **Closed duplicate?** Default open-only reads could miss it; explicit all is mandatory.
3. **PR counted?** A naive counter could; key-presence exclusion is deterministic.
4. **Lost-response number?** Never required; scope/marker precede dispatch, IDs supplement only.
5. **Missing marker candidate?** Body depends on representation; text/HTML can lack raw
   body. Future field projection/decoder and exact round-trip remain unvalidated.
6. **Not visible?** Yes; repository/principal access must be validated and missing
   access is not an empty census.
7. **Secondary limits across arms?** Yes, a plausible confound from shared activity
   and request history; independence is unvalidated.
8. **Silent POST retries?** Possible; GitHub documents SDK retries, while actual POST
   behavior depends on the eventual client. Audit every transport layer later.
9. **Enough evidence to change UNKNOWN?** No; no applicable mechanism or strong
   authoritative absence statement was established.
10. **Live work still needed?** Content/representation preservation, permissions,
    isolation, pagination under changes, visibility/convergence, transport attempt
    control, redirects/timeouts and rate-limit interference. None is tested live here.

### Offline validation boundary

Focused structural tests require no credentials, network, or repository. Full
regression validation uses the Phase 1 command below (recovered from its task
execution record); it clears every environment variable and disables socket
connection/DNS calls before pytest. These are unit tests, not Study 1 experiment
reruns, paper collection or Study 2 observations.
Fixed semantics cannot be supplied through constructor or replacement arguments.
Tests require rejection while accepting either `ValueError` or `TypeError` from
`dataclasses.replace`, since supported Python versions differ in that category.

```bash
.venv/bin/python -m pytest -q tests/test_study2_contracts.py tests/test_study2_github_semantics.py
.venv/bin/python -c 'import os; os.environ.clear(); import socket; deny = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network disabled for offline unit suite")); socket.socket.connect = deny; socket.socket.connect_ex = deny; socket.create_connection = deny; socket.getaddrinfo = deny; import pytest; raise SystemExit(pytest.main(["-q"]))'
```

No transport/authentication, retries, ambiguity injection, trial/scenario,
manifest, evidence schema, replicate/statistical choice, freezing or commit is
part of this phase.
