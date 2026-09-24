# Google Sheets Study-2 paper scope live binding V1

**FROZEN PRE-DATA LIVE BINDING — PROVIDER EXECUTION NOT YET AUTHORIZED**

**STUDY-2 PAPER OBSERVATIONS = 0. COLLECTION BLOCKED.**

This live-binding implementation was independently hostile-audited from actual bytes and is frozen for source identity. This freeze does not grant collection readiness, authorize OAuth or provider execution, create a scope binding, or qualify collection. Canonical clean-start checkpoint: `HEAD = origin/main = ca0f169bbf4b0846409fb5c29b397565ca383a95`.

Independent final hostile-audit bundle SHA-256: `09a250eaca3a9cc4506cbe41602f4d855f7596d1cd93aa6f96d9d4fcbe4eb6dc`.

## Frozen paper dependencies verified from current disk bytes

| Path | SHA-256 |
| --- | --- |
| `research/study2/sheets/GOOGLE_SHEETS_PAPER_SCOPE_PROVISIONING_V1.md` | `1999e20672f487f8831d7d2f89bd42d954366ee87f10f7d16b9958371998e1ef` |
| `research/study2/sheets/GOOGLE_SHEETS_PAPER_SCOPE_CREATE_REQUEST_V1.json` | `6596f530ba6fb5799b65c48dc73c84a8a4265b515bfc3b83473176ea1747e880` |
| `src/retry_semantics/study2/sheets_paper_scope_provisioning.py` | `a3c34e6f4914b5a0d3cea6206feb169fbaf4c421ae301bce366791cd1873d3f7` |
| `tests/test_study2_sheets_paper_scope_provisioning.py` | `22528e5894ad0c07a1cdf794ebcb2d9cc8e0cc8f510183b08f7616cf4609c632` |
| `research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_INPUTS_V1.md` | `15a2357e99df0c856f99b8b5419e923be927cdfeef7535be4d21a475762e6109` |
| `research/study2/sheets/GOOGLE_SHEETS_PAPER_NAMESPACE_RESERVATION_V1.json` | `a8a8bcd2751c56b05e9a9a569a6ad5f16e7d260b6a8ce5fb57dd244aef594506` |

## Reused committed engineering implementation dependencies

The following are current SHA-256 values computed from disk. They are implementation dependencies, not new Sheets-paper scientific authority. The seven requested engineering modules were inspected; `sheets_phase4_operator.py` is listed separately because its resident-session pattern was studied but its implementation is not called by this paper operator. The other transitively loaded implementation modules are pinned as well.

| Path | SHA-256 |
| --- | --- |
| `src/retry_semantics/serialization.py` | `48cb2030382334abc9ea13079e5bc91ed58be08640667e78570e529ddaa48cce` |
| `src/retry_semantics/study2/sheets_live_preparation.py` | `c3f4c775d80507cef3776391126b663eb216e7e97d667aaa67bb1b29ea7cb7da` |
| `src/retry_semantics/study2/sheets_http_framing.py` | `50fb8f45bccaf8f0ff1895bc487cd8c85fe3ef47c79c2b51b2aa7a6b4a4949c8` |
| `src/retry_semantics/study2/sheets_phase3_credentials.py` | `86d466abfe05da6a648d170836a4142f51020d69881cafa02e642adcaace404b` |
| `src/retry_semantics/study2/sheets_phase3_operator.py` | `c582e06401c342ace183fceb002210dda01433c1fbc5cd5acad3079e970e3a86` |
| `src/retry_semantics/study2/sheets_phase4_setup.py` | `f6963dc2aaa45e9a159311ac1600f8831b1728e647dea26867b0587de127f4e5` |
| `src/retry_semantics/study2/sheets_phase4_control.py` | `22fa217e1e00d61b48b8ab23343a3484b29c94392bcac39a0d122a06755acb43` |
| `src/retry_semantics/study2/sheets_phase3_control.py` | `446f4edcf5c5be4f2111f1b9d668560c35234c491782c172c707c2b08b7e811a` |
| `src/retry_semantics/study2/sheets_phase2_control.py` | `1bfd8c9c1f69fb76da7fe95e65957e728d7b077411f462dae977843a24edd178` |
| `src/retry_semantics/study2/sheets_phase2_read.py` | `ea9d99ba6fb86fe3fe9cc1bf6429d30903389e22b62f4ab618ea6a4c2ee85603` |
| `src/retry_semantics/study2/sheets_live_go_phase1.py` | `61481329f0a3f2071987c3a63e28fbcf4b9a04dfa63fe1a4ffc03354364386b1` |
| `src/retry_semantics/study2/sheets_offline.py` | `b43140a566c64699b51e141ab48fadaaeca1d1eb4e3ec1c51fc18c8d4bcc568d` |
| `src/retry_semantics/study2/sheets_paper_registry.py` | `09bec0ece06bacefd357a2067f4c3a6955347825fa692e6ad587d14e1d746fa8` |

Inspected engineering operator, not called by this binding: `src/retry_semantics/study2/sheets_phase4_operator.py`, current SHA-256 `b252a54577fff20a898ea716207fa4cb67b0c7afb48ebc2ff61d6bf5898fd042`. The paper operator uses the same resident-process property without invoking the engineering fixture workflow.

## Frozen live-binding implementation source identities

| Path | Frozen SHA-256 |
| --- | --- |
| `src/retry_semantics/study2/sheets_paper_live_transport.py` | `1a2085a973b061e935fd266bd068bd48dd65376c91b8a2e6233a00e739255b34` |
| `src/retry_semantics/study2/sheets_paper_scope_operator.py` | `f284fa379bf413b44a50e47fa62826379b9cf9ac0a1ac74f92ba1859ec1d6193` |

## Exact live call graph and OAuth boundary

`reviewed installed-app client file` → frozen Phase 4 `review_client` and private `load_client_config` → frozen Phase 4 `acquire` preflight and durable OAuth intent → frozen Phase 3 `DesktopPreparer.acquire` with PKCE S256, state and issuer/scope validation, one IPv4 loopback callback and one authorization-code exchange → `PreparedToken` resident in the same process → paper operator checks expiry margin → frozen paper `execute_create_once` invokes a resident expiry-checking callable once → new `transport` receives only the exported transient bearer string → frozen paper exclusive create-intent, dispatch, result, response validation, and in-memory candidate machinery.

The only scope is `https://www.googleapis.com/auth/drive.file`. OAuth requires the existing exact confirmation `EXPLICIT_OPERATOR_OAUTH_ACQUISITION`. The downloaded installed-app file is an explicit private input outside the repository. The inherited OAuth setup machinery retains its own already-qualified engineering OAuth intent and nonsecret acquisition metadata under its reviewed configuration; this binding creates no second paper-create root or intent format. The paper operator passes no refresh-capable object into the transport. There is no refresh persistence, refresh callback, token reacquisition, bearer file, bearer argv/environment/JSON/evidence/hash, or credential cache. A failed OAuth attempt or provider attempt terminates the resident call. Python memory clearing is best effort and is not a secure-heap claim.

Before any OAuth acquisition or provider action, `provision-session` requires interactive stdin **and** stdout and disables core dumps with `resource.setrlimit(resource.RLIMIT_CORE, (0, 0))`. If either terminal check or the core-limit call fails, it refuses before OAuth. This is operational hardening of the resident process; it changes no request bytes, topology, provider semantics, retry or ambiguity semantics, or frozen provisioning state machine.

## Concrete HTTPS transport

Only `sheets.googleapis.com`, port `443`, method `POST`, and the exact frozen target below are accepted:

```text
/v4/spreadsheets?fields=spreadsheetId%2Cproperties%28title%29%2Csheets%28properties%28sheetId%2Ctitle%2CsheetType%2CgridProperties%28rowCount%2CcolumnCount%29%29%29
```

The adapter uses a fresh stdlib `http.client.HTTPSConnection` with `ssl.create_default_context`, the qualified `validate_context`, `auto_open = 0`, an explicit single `connect`, one `endheaders(body)` send using the exact gate-supplied bytes, no JSON parse or reserialization, and the qualified `read_json_body` framing checker. A main-thread process alarm bounds DNS/connect/TLS/send/status/body to 60 seconds; the HTTPS socket also has a 60-second timeout. The accepted JSON body limit is 131072 bytes. Redirects are returned as statuses; no redirect, status, connection, send, OAuth, or create retry is implemented. No SDK, requests, urllib3, proxy, fallback host, or reconnect-and-resend path exists.

An observed valid HTTP status is returned unchanged to the paper gate. If later body reading/framing fails, the adapter returns that status with empty bytes. Thus 401/403/429/5xx remain visible one-shot outcomes even on body failure; a visible 200 with incomplete body remains visible but fails the frozen gate's success validator and becomes uncertain. If no status is observed, the adapter raises only a fixed nonsecret transport refusal. DNS/connect/TLS failure, partial send, timeout, reset, and response loss are not evidence of remote nonexecution. Dispatch entered, local send completed, remote receipt, remote commit, and acknowledgement are distinct states. The frozen gate retains sole authority to interpret a 200 response, validate title/256 GRID 100×3 tabs and distinct IDs, and construct an in-memory scope-binding candidate. This binding has no second create state machine.

## Runtime source pinning and operator commands

The prospective source projection requires an externally reviewed exact full `--expected-head` that is later than the canonical checkpoint, matches `HEAD`, and has a clean working tree. It compares disk bytes with `git show HEAD:<path>` for every path in the operator's `PINNED` map (all six frozen paper inputs plus paper registry and the engineering modules listed above), the new plan document, new transport, and new operator. Frozen paper and engineering hashes must equal the exact constants; new module hashes must equal the exact prospective table above. The new plan document itself must equal its committed blob. An independent later audit and mechanical freeze must approve the full commit before any live execution; an arbitrary new clean commit is not authority by itself. This local pin assumes a trusted operator machine and no concurrent source changes while running.

`inspect --expected-head <reviewed-full-commit>` is offline and prints only source readiness. `client-review --client <private-installed-client-path>` runs the inherited local review and prints only its public SHA-256; no browser or network. `provision-session` is the only future OAuth/create path. It requires `--configuration`, `--client`, `--expected-head`, both `--execute-oauth` and `--execute-provisioning`, exact `--oauth-confirmation EXPLICIT_OPERATOR_OAUTH_ACQUISITION`, and exact `--paper-confirmation EXPLICIT_PRE_DATA_SHEETS_PAPER_SCOPE_CREATE`. Missing or wrong flags/confirmations fail before source review, browser, OAuth, or provider action. Before OAuth it checks the fixed paper root and absent intent. There is no paper evidence-root argument. The sole paper root remains `$HOME/Library/Application Support/RetrySemantics/sheets-paper-scope-v1-76b0af67d7eece50cb12167e7ec374b9/`; this offline task does not create it. The frozen paper gate exclusively writes create-intent, dispatch and result there. Its already-spent intent prevents a second create even if a caller tries again.

For `provision-session`, process exit `0` means only `CREATE_RESPONSE_VALIDATED_PENDING_AUDIT`. A visible HTTP failure, uncertain outcome, other state, or refusal exits `2`. Exit status is process signaling only: it does not retry, reacquire OAuth, redispatch, change the durable result, or promote uncertainty to success.

No real `GOOGLE_SHEETS_PAPER_SCOPE_BINDING_V1.json` exists from this work. **SCOPE_PROVISIONED = NO. SCOPE_IDS_BOUND = NO. SCOPE_QUALIFIED = NO. FINAL_MANIFEST_EXISTS = NO. STUDY-2 PAPER OBSERVATIONS = 0. COLLECTION BLOCKED.**
