# Razorpay Phase 3 replay and visibility qualification

**DRAFT / NOT FROZEN**

**ENGINEERING QUALIFICATION ONLY**

**ONE MUTATION MAXIMUM · ONE POST MAXIMUM · NO MUTATION RETRY**

**BOUNDED READ-ONLY VISIBILITY SCHEDULE**

**NOT PAPER DATA · PROVIDER C REMAINS TBD · STUDY 2 PAPER OBSERVATIONS = 0**

**NO LIVE PHASE-3 CALL HAS YET BEEN PERFORMED**

## Questions and interpretation

The multiplicity question asks whether one exact replay of the receipt-less Phase-1 Create Order request receives a validated acknowledgement for a distinct second Order ID. That result establishes only this particular engineering case. A same-ID acknowledgement does not establish provider-wide idempotence.

The observer question asks whether a prospectively bounded Fetch All schedule observes exactly the original ID and any distinct replay ID. Phase 2 showed that the original Order, missed by the immediate Phase-1 list observation, later appeared under the *same historical window*. This motivates a fixed window and a bounded schedule. It does not measure the delay to visibility.

If the first exact two-ID observation occurs at a scheduled offset, the second resource was observed **by that scheduled observation**. The transition may have occurred between rounds. `authoritative_completeness_qualified` remains `false`: seeing the expected set does not prove Fetch All is generally complete.

## Frozen gate

Preparation is a local-only operation. It checks clean Git and `HEAD == origin/main`, every locked Phase-1 and Phase-2 byte hash, the Phase-1 request body and identity hashes, source hashes, and the `httpx` version. It creates one new package outside the repository, bound to its resolved path, with a canonical plan hash and an operator-visible whole-file SHA256. No real package is prepared by this draft work.

Execution requires the dedicated flag, exact confirmation phrase, operator-approved plan-file hash, and explicit Test Mode credential confirmation. Credentials come from hidden prompts and are neither accepted as CLI arguments nor persisted. The credential-scope fingerprint must match Phase 1. The exact frozen request is reconstructed and hash-checked before provider traffic. Production uses `HTTPTransport(retries=0)`, no redirects, no environment trust, and a finite timeout. Synthetic transport is private to offline tests.

Execution captures Unix anchor `T` and fixes the list window as `from=1790103525`, `to=T+300` in `intent.json`. The intent is created exclusively and fsynced before any GET. Its existence permanently consumes the package, including after a crash. A race loser makes no provider call and writes no terminal result.

The baseline traverses at most two pages of 100 Orders under that fixed window. Only a structurally complete exact singleton `{order_TfBuv3iQHQrz9p}` permits the one replay POST. The replay uses a fresh one-use dispatch permit and is never retried after any result. A validated acknowledgement is followed by one direct GET of its ID and strict identity validation. A failed direct fetch stops the schedule. After direct fetch, the provider-created timestamp must fall inside the already-frozen list window (`observation_from <= provider_created_at <= observation_to`) before bounded list visibility can be evaluated. If outside, the window is not modified, no visibility rounds are run, any already-established multiplicity fact is preserved, and the execution terminates INCONCLUSIVE (`replay_created_at_outside_fixed_window`) because observer qualification was not evaluable.

Visibility rounds target absolute offsets `0, 5, 30, 120, 600` seconds from completion of the replay acknowledgement. Each uses the same window and at most two pages. For a distinct replay ID, an exact two-ID set resolves the observer dimension and stops immediately; original-only continues; any other complete set or an incomplete observation stops inconclusive. If only the original appears through +600, the second resource is **not list-observed within the bound**; it is not declared absent. For a same-ID acknowledgement, exact singleton observations through the bound remain inconclusive under an unqualified list observer.

The hard ceiling is **one POST and thirteen GETs**: baseline 2, direct fetch 1, visibility 5 × 2. There is no cleanup mutation, payment action, LLM, ambiguity injection, ad-hoc continuation, or automatic rerun. Neither an engineering result nor this gate selects Provider C or changes Study 2 paper observations.
