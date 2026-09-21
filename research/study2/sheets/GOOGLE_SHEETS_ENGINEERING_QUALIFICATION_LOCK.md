# Google Sheets Engineering Qualification Lock

**Project:** Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes
**Academic Byline:** J. Rashne
**Study:** Study 2 — Multi-Provider External Validation (Google Sheets Adapter)
**Phase:** Phase 4 Live Engineering Qualification
**Status:** COMPLETE / CLOSED / CANONICAL
**Document Role:** Immutable post-qualification provenance and results lock. This document is **not** a prospective protocol or experimental data record.
**Frozen Base Commit:** `0fda488c702ebbe53bb2e3a546c575b502fc73ef` (`HEAD == origin/main`)

---

## 1. Purpose of this Lock

This document records the canonical result and immutable operational state of the Google Sheets Study 2 live engineering qualification.

Following this lock:
- The Google Sheets live engineering qualification is **COMPLETE** and **CLOSED**.
- Exactly one real spreadsheet fixture was created and validated; that creation will not be repeated under this qualification.
- Exactly one real baseline `read-current` GET request was dispatched and validated with HTTP 200 OK; the engineering GET is strictly stop-no-retry.
- No further engineering-qualification requests, retries, or authorizations against this retained qualification package or fixture are authorized.
- Any future Study 2 paper experiment requires a separate hostile-audited, frozen paper protocol and separate explicit authorization; this qualification lock itself grants NO authority for future paper calls.
- The canonical counts and artifact inventory documented below are frozen.

---

## 2. Strict Boundary: Engineering Qualification vs. Paper Data

A fundamental separation governs this lock:

1. **Engineering Qualification (COMPLETE):**
   - Live qualification succeeded under fail-closed engineering controls.
   - Total real `spreadsheets.create` calls = 1.
   - Total real Sheets mutations = 1.
   - Total real Sheets GET dispatches = 1.
   - Total successful real Sheets GETs = 1 (HTTP 200).
   - Same validated fixture adopted and reused; zero duplicate mutations.

2. **Study 2 Paper Data (NOT STARTED):**
   - **Paper observations = 0.**
   - The Study 2 experimental paper data collection has **NOT** started.
   - The successful engineering baseline GET is **not** an experimental observation.
   - Replay and Regeneration retry semantics have **NOT** been tested on Google Sheets.
   - No experimental prompt, LLM tool dispatch, ambiguity injection, or replay trial has been executed on Google Sheets.

---

## 3. Canonical Real Outcome and Operational Counters

| Metric | Canonical Count | Description |
| :--- | :---: | :--- |
| **OAuth attempts** | **9** | Total interactive OAuth authorization flows initiated across retained packages |
| **Accepted acquisitions** | **6** | Successful nonsecret acquisitions persisted (#4, #5, #6, #7, #8, #9) |
| **Real spreadsheet CREATEs** | **1** | Validated `spreadsheets.create` call in OAuth attempt #5 (HTTP 200) |
| **Real Sheets mutations** | **1** | The single spreadsheet fixture creation above; no subsequent mutations |
| **Real Sheets GET dispatches** | **1** | Dispatched under authorization #4 via compact `read-current` |
| **Successful real Sheets GETs** | **1** | Validated HTTP 200 empty grid baseline response |
| **Study 2 Paper observations** | **0** | Experimental paper data collection has not started |

---

## 4. Full Historical Lineage of Authorizations and Attempts

The qualification process operated under strict fail-closed criteria, preserving durable evidence at every stage:

1. **OAuth attempt #1:** Authorization callback received; rejected by the then-frozen parser due to issuer (`iss`) parameter handling. `oauth-intent.json` permanently spent; no local acquisition.
2. **OAuth attempt #2:** Authorization callback received; rejected by the then-frozen parser due to returned `scope` parameter handling. `oauth-intent.json` permanently spent; no local acquisition.
3. **OAuth attempt #3:** Callback matched accepted shape, but acquisition returned `BLOCKED` before local acquisition persistence (exact stage unrecorded by earlier build). Intent spent; no local acquisition.
4. **OAuth attempt #4:** Executed in a fresh reviewed package bound to frozen commit `594c95f`. Accepted `acquisition.json` produced; resident session reached prompt and was intentionally terminated with `stop` before provisioning. Zero Google Sheets API requests (no Sheets CREATE or GET requests; OAuth token exchange accounted separately in OAuth attempt #4).
5. **OAuth attempt #5 / CREATE / Authorization #1:** Executed in a fresh reviewed package. Produced accepted acquisition. Dispatched one `spreadsheets.create` returning HTTP 200 for a 100-row, 3-column engineering grid with sheet ID 1. Fixture hash: `262c5f5be30875c077c54bb66f21dae3f7859a58c6af8464c34517d0086b9ec2`; provisioning hash: `958372a4e213f9c22ffad374efbdcc06cc8359cdd36f2f418e0189d457bce1cf`. Reservation registered. `LIVE_READ_GO` authorization #1 was issued (`602cd05f8f98e8403cc0f97f1d62845682e35bdb278e2d32573765b720a4b77e`), but its validity window expired before read command execution. **Expired unused; zero read dispatch.**
6. **OAuth attempt #6 / Authorization #2:** Reviewed expired-unused-read successor package. Adopted the existing validated fixture without repeating CREATE. Post-setup preflight passed. `LIVE_READ_GO` authorization #2 issued, but expired unused due to operator timing. **Expired unused; zero read dispatch.**
7. **OAuth attempt #7 / Authorization #3:** Reviewed successor package bound to frozen commit `739b30e4d5b34997defa9beb0eabcb0d40084677`. Adopted the existing validated fixture. Post-setup preflight passed. `LIVE_READ_GO` authorization #3 issued. Operator attempted to paste the verbose `read` command (~1410 bytes), but macOS canonical TTY buffer truncated the line at 1024 bytes (`MAX_CANON`, exactly at `.../phase4-recei`). The truncated line was never executed; session was interrupted (Ctrl+C). **Expired unused; zero read dispatch.**
8. **OAuth attempt #8:** Reviewed unused-read successor package. Accepted acquisition written. Resident session explicitly stopped before fixture adoption. Authorization #4 was **not** issued in this package.
9. **OAuth attempt #9 / Authorization #4 / First GET (SUCCESS):** Recovered via the reviewed reused-fixture branch of `supersede-unused-acquisition` (v2), creating fresh successor package `sheets-phase4-unused-acquisition-successor-df5e884b07bb3c9b2fed18049767bd01eb08782cee5e1646900b93962a04a238`. Fresh client review, startup, and offline pin passed under frozen HEAD `0fda488c702ebbe53bb2e3a546c575b502fc73ef`. OAuth attempt #9 accepted. The historical validated fixture (`262c5f5be30875c077c54bb66f21dae3f7859a58c6af8464c34517d0086b9ec2`) was adopted without recreation. Post-setup preflight passed. `LIVE_READ_GO` authorization #4 was issued (hash: `5c16ad01b5fe82182b4332827ab5a46e3e047a90c110399ff9ad58f30e9cb945`). The compact resident command `read-current --execute-live-read --token-input resident-memory` was executed exactly once.

---

## 5. First Successful Read Result

The live GET dispatch produced the following canonical result:

```yaml
schema: sheets-phase3-first-read-result-v1
http_status: 200
baseline: suitable-current-empty-grid
byte_count: 356
nonempty_rows: 0
matching_rows: []
outcome: zero_matches_currently_not_observed
engineering_only: true
paper_observations: 0
next_action: stop-no-retry
```

The response validated the exact grid extent, zero marker matches, and zero entered rows, confirming a clean, uncontaminated baseline.

---

## 6. Real Successor Package Inventory

**Storage Root:**
`/Users/jashrashne/Library/Application Support/RetrySemantics/sheets-phase4-unused-acquisition-successor-df5e884b07bb3c9b2fed18049767bd01eb08782cee5e1646900b93962a04a238`

### Root Artifacts (17 files present)
- `acquisition.json`
- `authorization.json`
- `client-review.json`
- `conditions.json`
- `fixture-adoption.json`
- `fixture.json`
- `issue-intent.json`
- `oauth-intent.json`
- `offline-pin.json`
- `operator.json`
- `phase3-receipt.json`
- `phase4-receipt.json`
- `read-intent.json`
- `read-pin.json`
- `result.json`
- `startup.json`
- `unused-acquisition-supersession.json`

### Excluded Setup/Provisioning Artifacts (4 files absent)
- `create-intent.json` (absent — proves CREATE was not executed in this package)
- `create-result.json` (absent)
- `provisioning.json` (absent)
- `provisioning-review.json` (absent)

### Registry Directory (`registry/`)
- `attempt-successor-7959853ec8f38f367c8609f85522b2fb.jsonl`
- `claim-successor-7959853ec8f38f367c8609f85522b2fb.json`
- `registry.lock`
- `reservation-sheets_phase4_first_fixture.json`

---

## 7. Independent Hostile Audit Verifications

An independent hostile audit verified the following properties of the live run:
1. **Authorization Binding:** `read-intent.json`, `result.json`, `phase3-receipt.json`, and `phase4-receipt.json` all bind to the exact same authorization (#4: `5c16ad01b5fe82182b4332827ab5a46e3e047a90c110399ff9ad58f30e9cb945`).
2. **Fixture Integrity:** `fixture.json`, `read-pin.json`, `issue-intent.json`, and `fixture-adoption.json` all bind to the exact historical fixture hash (`262c5f5be30875c077c54bb66f21dae3f7859a58c6af8464c34517d0086b9ec2`).
3. **Fresh Acquisition:** OAuth attempt #9 was fresh relative to the recovery transition boundary; no predecessor token metadata satisfied the preflight gate.
4. **Zero Credential Leakage:** No access token, refresh token, client secret, PKCE verifier, authorization code, ID token, or Bearer credential was persisted into evidence or the repository.
5. **Git Immutability:** Repository `HEAD` and `origin/main` remained frozen at `0fda488c702ebbe53bb2e3a546c575b502fc73ef` throughout live operations.
6. **No Remote Claims:** No claim of remote token revocation is made; no Google Sheets API action beyond the 1 validated CREATE and 1 validated GET was dispatched (OAuth authorization flows and token exchanges are accounted separately across the nine OAuth attempts).

---

## 8. Frozen Status

With the completion of this engineering qualification run, the Google Sheets adapter is verified as capable of:
- Establishing an authenticated TLS 1.3 connection to Google APIs;
- Issuing/validating one-use, bounded-lifetime internal LIVE_READ_GO authorization artifacts with strict client/runtime/source bindings;
- Reading and validating an isolated empty grid via GET with strict response framing;
- Enforcing hard stop-no-retry semantics upon successful baseline verification.

**This engineering qualification is closed. No further engineering-qualification requests, retries, or authorizations against this retained qualification package or fixture are authorized. The successful engineering baseline GET is stop-no-retry. Any future Study 2 paper experiment requires a separate hostile-audited, frozen paper protocol and separate explicit authorization; this engineering qualification lock itself grants NO authority for future paper calls.**
