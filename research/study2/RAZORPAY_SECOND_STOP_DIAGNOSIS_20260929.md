# Razorpay second stop: diagnosis and next action

Status: provider capacity remains unqualified. No third experimental launch is
prepared or authorized by these diagnostics. GitHub's checkout and process were
not changed. Both stopped Razorpay datasets retain their original evidence and
256-opportunity denominators.

## What the VM evidence establishes

- Original continuation: stopped after 2/256 evaluated arms on HTTP 429.
- Paced V1: stopped after 4/256 evaluated arms, with 2 SUCCESS and 2 FAILURE
  projections. Both failures were DUPLICATE_EFFECT research outcomes. The actual
  execution stop was HTTP 429 on arm 4's second scheduled Fetch All request.
- That 429 occurred at 2026-09-28 19:06:16 UTC. The previous request had completed
  199.597 seconds earlier. All V1 request gaps were at least three seconds.
  Therefore attributing this second stop to an immediate request burst is wrong.
- At 2026-09-29 04:15:07 UTC a fresh read-only diagnostic's first request to the
  same count=100 URL also received 429, with Retry-After 3. No experimental runner
  had been active for hours. This does not prove the account received no traffic
  from any source; the operator separately reports no other clients using it.
- A subsequent known-order GET and count=1 listing each returned 200. A later
  count=100 GET at 04:16:52 UTC also returned 200. The restriction is intermittent;
  those single successes do not establish reliable capacity.
- A prospective bounded engineering test at 04:17:52 UTC requested 30 read-only
  count=100 listings with at least ten seconds between requests. Requests 1–27
  returned 200; request 28 returned 429, Retry-After 3, at 04:22:46 UTC. The probe
  stopped immediately. It made no order mutations or experimental observations.

The provider's precise rate window, scope (account, endpoint, IP or other), and
reason for intermittent throttling remain unknown. Changing delays again is not
a verified repair. Neither response bodies nor logs indicate a Python exception
caused the 429. The collector obeyed the protocol's permanent rate-limit stop.

## Preserved VM evidence

- `/root/study2-data/razorpay-run` — original stopped continuation.
- `/root/study2-razorpay-replication/razorpay-run` — stopped paced V1.
- `/root/study2-razorpay-diagnostics/20260929T041507Z` — fresh count=100 refusal.
- `/root/study2-razorpay-diagnostics/20260929T041559Z` — endpoint comparison.
- `/root/study2-razorpay-diagnostics/20260929T041651Z` — count=100 recovery.
- `/root/study2-razorpay-diagnostics/20260929T041752Z` — sustained probe failure.

Each directory has a SHA-256 inventory. Keep all claims and provider orders.
Diagnostic reads are engineering-only and must not be pooled with experiment
outcomes. No independent audit or external timestamp is claimed.

All six inventories were checked against their complete directory contents.
Inventory-file SHA-256 values for the two experiments and sustained probe:

| Evidence | Inventory SHA-256 |
|---|---|
| Original | `e581c62dca2f74347d9e183976422e9f959dc722fd44bfddbc48ba0f1563b6be` |
| Paced V1 | `29cb0f0bea363eb0a642264a2aa3f5eee13f687b076616efb5f91327c1410a17` |
| Sustained probe | `d21041f8255146c59accba43be39c7c848e5691247eddf49de4135b485e6f783` |

## Ready-to-send support request (operator sends; no message sent by the agent)

Subject: Test Mode Orders API intermittently returns HTTP 429 at low request rate

Hello Razorpay Support,

I am conducting a bounded retry-semantics research experiment using my Razorpay
Test Mode account, with no real payments. I need predictable read capacity for
`GET /v1/orders?count=100&skip=0&from=1790621857&to=1790623477` and occasional
receipt-less Test Mode order creation. The experiment is serial and my account
has no other known clients. The source VM's public IPv4 is 159.65.144.248.

On 28 September 2026 at 19:06:16 UTC the Orders listing returned HTTP 429,
`Too many requests`, Retry-After 2, after approximately 200 seconds without a
preceding experiment request. On 29 September at 04:15 UTC the first read after
hours of experiment inactivity also returned 429, Retry-After 3. Known-ID reads
and some subsequent listings succeeded.

I then ran a read-only diagnostic at no more than six requests per minute:
27 consecutive count=100 listings succeeded, followed by HTTP 429 and Retry-After
3 on request 28 at 04:22:46 UTC. The diagnostic stopped on that response.

Could you please identify the applicable Test Mode account/endpoint/IP rate
limits and window, investigate why these low-rate requests are throttled, and
advise whether the quota can support this legitimate experiment or be increased?
Please confirm a sustainable request rate for count=100 Orders listings and
whether page size affects the request budget. I can provide sanitized response
evidence through your authenticated support channel. I will not send API secrets.

Thank you.

Razorpay's official error guidance recommends reducing frequency or contacting
Support for a limit increase:
https://razorpay.com/docs/errors/common#too-many-requests . Its generic retry advice
does not authorize changing this experiment's frozen no-retry rule.

## After the provider confirms a resolution

Use the installed diagnostic checkout, not either historical experiment checkout:

```bash
(
set -euo pipefail
cd /root/retry_semantics_razorpay_diagnostics
set -a
source /root/.config/retry-semantics/credentials.env
set +a
.venv/bin/python scripts/diagnose_study2_razorpay_capacity.py \
  --stopped-run /root/study2-razorpay-replication/razorpay-run \
  --output-parent /root/study2-razorpay-diagnostics
)
```

This takes roughly five minutes if all 30 reads succeed; it stops at the first
error, never writes orders, never retries, and never consumes a launch claim.
`passed: true` describes only that bounded probe, not guaranteed future capacity.
If it fails, preserve the new evidence and return it to Support. Do not loop until
a favourable probe occurs. Any later experiment needs a separately reviewed fresh
namespace and prospective operational conditions; no old launch command resumes it.

## Code repairs made during diagnosis

Future launcher summaries include the actual HTTP stop status, operation, arm,
Retry-After and result-file reference, preserving the scientific projections.
The reusable capacity diagnostic saves its plan before requests, binds the stopped
evidence and source code, enforces a fixed ten-second interval and 30-request cap,
and saves raw evidence and a final inventory even on a caught transport error.
