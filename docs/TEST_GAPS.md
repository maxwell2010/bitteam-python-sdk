# Test gaps: site, P2P, archive and CI

Audit date: 2026-11-04. This is a scoped evidence matrix, not a claim of complete API coverage. No build/version bump or account requests were performed during this audit.

## Evidence and status definitions

- **Historical live**: an earlier saved check reports success. It does not establish current availability or validate all parameter combinations.
- **Offline only**: fixed JS contract and local fake-response tests; no successful live check documented for this operation.
- **Unavailable in snapshot**: an earlier public probe returned an error, timed out, or returned HTML after redirect. The service was not re-probed here.
- `output-sdk/research_site_inventory.json` (2026-11-03), `routes[]`: public URL/query/response-shape evidence. `evidence[]` and `sources[]` retain JS provenance.
- `bitteam_sdk/EXTENDED_CHECKS.json` (2026-11-03): saved success flags, including public news posts/categories and the separately performed P2P account read. This audit does not access that account or its cache.
- `bitteam_sdk/schemas/p2p_site.json`: operation/source URL/offset/excerpt/SHA and derived-callsite metadata. Catalog routing tests do not independently establish backend semantics.
- `output-sdk/site-gap-before.json` and `output-sdk/site-gap-after.json`: local coverage evidence. These files are diagnostic outputs, not shipped account data.

## Public site API matrix

Base aliases: v2 = `https://api-v2.bit.team/api/v2`; market = `https://bitteam-market-back.bit.team/api`; docs = `https://docs-api.bit.team/api/v1`; blog = `https://bit.team/blog/wp-json/wp/v2`.

All methods are anonymous and use a separate DummyCookieJar, TLS verification and no redirects. Chart POST is a fixed read-only JS contract, not a financial operation; it was not invoked live in this audit.

| SDK method | Fixed route | Evidence/status | Remaining gap |
|---|---|---|---|
| get_coins | v2 GET /public/coins/list | Historical live: v2_coins | Network-child visibility is not withdrawal availability |
| get_currencies | v2 GET /public/currencies/list | Historical live: v2_currencies | Other locales and catalog changes |
| get_rates_by_period | v2 GET /public/rates-by-period | Historical live: v2_rates_period_day, coin_id=3/currency_id=2/type=day/period=1 | Other period/type combinations and IDs |
| get_static_menu | v2 GET /public/static-page/{project_id}/get-all-menu | Historical live: v2_static_menu_en, project_id=2 | en-US had 422; other projects not checked |
| get_static_page | v2 GET /public/static-page/{project_id}/{category_id}/{page_id} | Historical live: v2_static_page, 2/1/41 | Other pages/locales |
| get_p2p_currencies | v2 GET /get/data-init-currency | Historical live: p2p_coins, type=coin,token | type=valute had a success then timeout; not reliable |
| get_payment_methods | v2 GET /get/data-init-payment-method | Historical live: p2p_payments, RUB | Other fiat catalogs and provider rules |
| get_advertisement_limits | v2 GET /anunt/get-limit-percent | Historical live: p2p_limits | Values may change |
| get_advertisements | v2 GET /anunt/get | Historical live: p2p_adverts, buy/BTC/RUB/limit2/offset0 | sell, sorting, payment, sum, online filters not live checked; response may contain payment details |
| get_crypto_map | market GET /cryptocurrency/map | Unavailable in snapshot: market_map redirected to HTML | No usable map JSON established |
| get_crypto_map(category=...) | market GET /cryptocurrency/map/categories/{category} | Offline only: JS + local routing | Categories and result semantics unverified |
| get_crypto_map(tag=...) | market GET /cryptocurrency/map?tag=... | Offline only: JS + local routing | Tags unverified |
| get_crypto | market GET /cryptocurrency/one/{alias} | Unavailable in snapshot: market_coin timeout | Sample bitcoin alias not validated through a working map |
| get_crypto_history | market GET /cryptocurrency/historical/{coin} | Unavailable in snapshot: market_history timeout | Bounds/schema/enums unverified |
| get_market_pairs | market GET /market_pairs/coin/{coin} | Unavailable in snapshot: market_pairs timeout | Pagination and schemas unverified |
| get_crypto_metadata | market GET /page/coin-meta/{coin} | Unavailable in snapshot: market_meta timeout | en-US/ru-RU observed in JS, server contract unverified |
| get_common_cryptos | market GET /core/common/cryptos | Unavailable in snapshot: market_cryptos timeout | No valid JSON sample |
| get_common_markets | market GET /core/common/markets | Unavailable in snapshot: market_markets timeout | No valid JSON sample |
| get_crypto_chart | market POST /cryptocurrency/chart | Offline only: id/period JS contract + fake response | No live POST; IDs/period enums/server schema unverified |
| get_docs_pages | docs GET /pages | Unavailable in snapshot: docs_pages HTTP502 HTML | Search/locales/JSON schema unverified |
| get_news_posts | blog GET /posts | Historical live: EXTENDED_CHECKS public.news_rest_posts | Other filters/date ranges/categories/content semantics |
| get_news_post | blog GET /posts/{id} | Offline routing; SITE_INVENTORY reports earlier confirmation | No per-id machine success record in checked JSON report |
| get_news_categories | blog GET /categories | Historical live: EXTENDED_CHECKS public.news_categories | Other pages/locales |

## P2P per-operation matrix

All routes below are relative to fixed `https://api-v2.bit.team/api/v2`. There are 63 operations: 61 extracted helpers plus 2 concrete derived call sites. 58 require SessionAuth general access_token, not API keys or spot access. Five are classified public. Sixteen GET operations mutate state; no live financial, confirmation, code-delivery or other mutation was exercised.

Every row has a local synthetic routing test in `test_p2p_api.py`. Those tests verify dispatch/auth placement/defaults, not valid production request bodies or real account outcomes. Unknown body schemas remain explicit caller dicts.

| Operation | HTTP route | Access | Mutating GET | Evidence/status |
|---|---|---|---|---|
| accept_operation | GET /operations/accept-operation | SessionAuth | yes | Offline only |
| add_advert_to_favorites | POST /user/deal-favorites/add | SessionAuth | no | Offline only |
| add_payment_system | POST /user/add-payment-systems | SessionAuth | no | Offline only |
| cancel_operation | GET /operations/cancel-operation | SessionAuth | yes | Offline only |
| cancel_withdraw | GET /account/cancel-withdraw/{withdraw_id} | SessionAuth | yes | Offline only |
| change_status_advert | POST /anunt/change-status-advert | SessionAuth | no | Offline only |
| change_status_all | GET /user/change-status-all | SessionAuth | yes | Offline only |
| check_telegram_permission_code | POST /telegram/check-telegram-permission-code | SessionAuth | no | Offline only |
| confirm_new_withdraw | GET /account/verification-withdraw/{code} | SessionAuth | yes | Offline only |
| create_new_advert | POST /anunt/create-new-advert | SessionAuth | no | Offline only |
| create_new_wallet_for_account | GET /account/create-wallet/{currency_id} | SessionAuth | yes | Offline only |
| create_new_withdraw | POST /account/create-withdraw | SessionAuth | no | Offline only |
| create_operation | POST /operations/create | SessionAuth | no | Offline only |
| create_ticket | POST /support/ticket/create | SessionAuth | no | Offline only |
| del_payment_system | GET /user/del-payment-systems/{payment_id} | SessionAuth | yes | Offline only |
| delete_advert_from_archive | GET /anunt/restore-advert/{advert_id} | SessionAuth | yes | Offline only |
| delete_advert_from_favorites | POST /user/deal-favorites/delete | SessionAuth | no | Offline only |
| delete_advert_user | GET /anunt/delete-advert/{advert_id} | SessionAuth | yes | Offline only |
| dispute_operation | POST /operations/dispute-operation | SessionAuth | no | Offline only |
| get_accounts | GET /auth/user | SessionAuth | no | Historical live: EXTENDED_CHECKS account.p2p_account_wallets_read; derived callsite |
| get_active_operations | GET /operations/active | SessionAuth | no | Offline only |
| get_advert_edit | GET /anunt/get-edit-advert/{advert_id} | SessionAuth | no | Offline only |
| get_answers | GET /chatbot/process | public | no | Offline only |
| get_archive_operations | GET /operations/archive | SessionAuth | no | Offline only |
| get_archive_payment_system | GET /user/get-payment-detail | SessionAuth | no | Offline only |
| get_archived_adverts | GET /anunt/my-advert | SessionAuth | no | Offline only |
| get_auth_google | GET /user/auth-google-first | SessionAuth | yes | Offline only |
| get_auth_google_active | GET /user/auth-google-active | SessionAuth | yes | Offline only |
| get_auth_google_confirm | GET /user/auth-google-confirm | SessionAuth | yes | Offline only |
| get_cities_list | GET /city/get | public | no | Offline only |
| get_commission_btt | GET /commission/list | public | no | Offline only |
| get_favorites_adverts | GET /user/deal-favorites/list | SessionAuth | no | Offline only |
| get_messages_operation | GET /operations/get-messages | SessionAuth | no | Offline only |
| get_messages_support | GET /support/ticket/{ticket_id}/messages | SessionAuth | no | Offline only |
| get_my_advert | GET /anunt/my-advert | SessionAuth | no | Offline only |
| get_operation | GET /operations/get-operation | SessionAuth | no | Offline only |
| get_payments_systems_list | GET /user/get-payment-systems | SessionAuth | no | Offline only |
| get_questions | GET /chatbot/process | public | no | Offline only |
| get_source_price | GET /anunt/get-price-source | SessionAuth | no | Offline only |
| get_subjects | GET /chatbot/process | public | no | Offline only |
| get_ticket_subjects | GET /support/list-subjects | SessionAuth | no | Offline only |
| get_tickets | GET /support/list-tickets | SessionAuth | no | Offline only |
| get_user_avatars | GET /avatar/index-by-auth-user | SessionAuth | no | Offline only |
| get_user_payments | GET /user/get-payment-detail | SessionAuth | no | Offline only |
| get_withdrawal | GET /transactions/get-withdraw-by-id/{withdraw_id} | SessionAuth | no | Offline only; derived callsite |
| load_user_review | GET /user/get-user-review | SessionAuth | no | Offline only |
| load_user_statistic | GET /user/get-user-statistic | SessionAuth | no | Offline only |
| pay_operation | GET /operations/pay-operation | SessionAuth | yes | Offline only |
| remove_all_app_token_api | POST /user/remove-all-app-token | SessionAuth | no | Offline only |
| remove_app_token_api | POST /user/remove-app-token | SessionAuth | no | Offline only |
| remove_ticket | POST /support/ticket/{ticket_id}/close | SessionAuth | no | Offline only |
| resend_operation_email | GET /account/resend-email/{operation_id} | SessionAuth | yes | Offline only |
| save_advert_edit | POST /anunt/save-edit-advert/{advert_id} | SessionAuth | no | Offline only |
| save_review_to_user | POST /operations/review-operation | SessionAuth | no | Offline only |
| send_coin_operation | GET /operations/send-coin-operation | SessionAuth | yes | Offline only |
| send_messages_operation | POST /operations/send-message | SessionAuth | no | Offline only |
| send_messages_support | POST /support/send-messages | SessionAuth | no | Offline only |
| send_telegram_permission_code | POST /telegram/send-telegram-permission-code | SessionAuth | no | Offline only |
| send_test_message_api | POST /telegram/send-message | SessionAuth | no | Offline only |
| set_language | GET /user/set-language | SessionAuth | yes | Offline only |
| set_user_avatar | POST /avatar/set-active-avatar | SessionAuth | no | Offline only |
| update_login | POST /user/update-login | SessionAuth | no | Offline only |
| upload_verification | POST /user/verification-user | SessionAuth | no | Offline only |

P2P gaps: no real success/failure/idempotency/insufficient-balance/2FA/device-confirmation tests for mutations; no verified terminal withdrawal enums; no journal index route inferred from generic getRequestCabinet. `/auth/user` account/additional_wallets/possible_wallets is preserved raw. Child currency IDs belong to API-v2, not spot; offline tests do not establish whether a network is currently enabled. There is no batch withdrawal guarantee. Unknown required body fields must be supplied from separately verified contracts.

## Archive matrix

Fixed base `https://archive.bit.team/api`; GET only, separate anonymous cookie jar, TLS and no redirects. Private calls require production SessionAuth spot bearer and matching production auth/spot origins.

| SDK method | Route | Status | Local evidence / remaining gap |
|---|---|---|---|
| get_trades | /trades | Unavailable in snapshot: archive_trades timeout | Anonymous routing, limits, malformed/HTML/redirect/error responses, cancellation and session cleanup tested with fakes; no valid production archive JSON established |
| get_user_orders | /ordersByUser | Offline only | Auth type/state/unbound/closed/origin guards and spot bearer routing tested; no account call |
| get_user_trades | /tradesByUser | Offline only | Fixed read-only route and raw result preservation tested; no account call |

Archive pagination is bounded locally when limit/page/offset are provided. Server-supported filters, defaults, ordering, retention and maximum pages remain unverified. Network failures are returned, never replaced with synthetic history.

## Confirmed fixes and local regression evidence

- P2P non-200 envelope code can no longer succeed solely because status=true and data exists.
- P2P/site None and boolean identifiers are rejected before they can become literal URL segments.
- Archive unbound SessionAuth fails with AuthenticationError; custom auth origin cannot leak a spot bearer into fixed production archive.
- Site/chart/archive aiohttp errors and timeouts are sanitized without retries; cancellation propagates. Chart error arrays cannot become success.
- Site queued behind its limiter rechecks closed state before issuing GET/chart POST. Archive close is idempotent.
- Archive accepts only dictionary query parameters and enforces supplied pagination bounds.
- Wheel smoke now passes pip --isolated as well as Python -I: inherited PIP_TARGET/user pip settings cannot redirect this supposedly isolated installation.

New regressions: `tests_sdk/test_site_transport_review.py` (47 cases), `tests_sdk/test_ci_scripts_review.py` (8 cases). They use synthetic responses, cookies and mock subprocess/venv operations; they do not install/build packages or call accounts.

Focused coverage command:

```text
python -m pytest -c tests_sdk/pytest.ini tests_sdk/test_site_transport_review.py tests_sdk/test_site_api.py tests_sdk/test_p2p_api.py tests_sdk/test_extended_facade.py --cov=bitteam_sdk.site_api --cov=bitteam_sdk.p2p_api --cov=bitteam_sdk.archive --cov-branch --cov-report=term-missing --cov-report=json:output-sdk/site-gap-after.json -q
```

Observed: 185 passed. Percentages below combine statements and branch destinations; they are not live API coverage:

| Module | Before audit | After fixes/regressions | Lines covered / statements | Branch destinations covered / total |
|---|---|---|---|---|
| site_api.py | 86% | 89% | 186/205 | 75/88 |
| p2p_api.py | 83% | 84% | 120/140 | 65/80 |
| archive.py | 58% | 92% | 70/75 | 32/36 |

Remaining code gaps include optional certifi-import fallback, several invalid configuration/body/query cases, and context-manager branches. No forced platform/coverage skips were added to inflate the numbers. The total across these modules is about 88%, not 100%.

## Scripts and CI portability

- Workflow `.github/workflows/sdk.yml`: Windows/Linux x Python 3.10, 3.11, 3.12, 3.13; push/PR run the full offline suite, skip audit and upload JUnit only. Build, fresh-venv wheel smoke and distribution upload require manual workflow_dispatch with verify_distribution=true (default false). Historical run 41847439819 was inspected through GitHub API during cloud continuation: all eight Windows/Linux Python 3.10-3.13 jobs succeeded, including pytest and skip audit; distribution steps were skipped. This does not validate subsequent changes.
- Existing real Windows DPAPI roundtrip is the only allowed non-Windows skip. Portable encrypted-cache tests use their synthetic Fernet protector on all platforms. Windows must execute native DPAPI; it is not skipped there.
- `check_test_skips.py` rejects an empty JUnit report and unexpected skips; negative regression cases cover Windows and Linux names/classnames.
- `check_wheel.py` uses an explicit single wheel, a fresh venv, Python -I, pip --isolated and an external temporary working directory. It validates installed-version metadata, bundled schemas/catalogs and core callable facades while blocking SDK network/session creation. It is a smoke, not a run of all unit tests against the installed artifact. Optional sqlite/postgres module files are checked; optional feature behavior needs its dependency extras.
- `test_ci_scripts_review.py` mocks subprocess and venv creation, so the new pip-isolation branch is not claimed to be an actual fresh install. No new wheel or source archive was built during this audit.
- Earlier local Windows checks were 581 passed on Python3.10 and 3.11, 578 on Python3.12 at an older suite snapshot. These counts are historical; they exclude this audit's new regressions and subsequent parallel changes.
- Local Linux WSL has Python3.12 but lacks ensurepip/venv and pytest dependencies; it was not configured. Python3.13 is not installed locally. This historical local limitation is superseded for the earlier main snapshot by observed CI run 41847439819; the current cloud baseline also ran Linux Python 3.12.14.
- Public live scripts are opt-in and excluded from CI. `live_extended.py --account-profile` has an explicit account mode; it was not used. The sample reports record UTC run time rather than a hardcoded date. Public sample pairs/IDs and market/news backend availability can change.
- Building/installing is intentionally not part of this audit run. Push/PR never build distributions; explicit manual verify_distribution=true is required after the agreed verification gate. No release/publish step exists in the workflow.

Priority remaining validation: Windows/Linux 3.10-3.13 CI for new changes, installed-artifact full test run after authorized build, public market/docs/archive availability and schemas, optional PostgreSQL/chart runtime coverage. Real account/financial/2FA delivery testing requires its separately authorized scope and cannot be replaced by catalog route-count tests.


## Cloud continuation evidence (2026-11-04)

| Check | Actual result | Boundary |
|---|---|---|
| Initial main 8215216, Linux Python 3.12.14, configured venv | 706 passed, 1 native DPAPI skip; check_test_skips passed | Synthetic suite, including local HTTPS; no account calls |
| Sandbox-only baseline attempt | Local TCP bind denied; interrupted after stalled recorder test | Environment restriction, not SDK success; repeated with local socket access |
| Historical GitHub run [41847439819](https://github.com/maxwell2010/bitteam-python-sdk/actions/runs/41847439819) | Eight jobs success, Windows/Linux Python 3.10-3.13; pytest and skip audit success | Prior main; build/wheel steps skipped |
| Final cloud suite | 752 passed, 1 native DPAPI skip; check_test_skips passed | Linux Python 3.12.14, 753 collected; code commit 5f65dca CI also passed (see below) |
| Archive lifecycle regressions | Initial four tests failed before fix; auth-replacement follow-up also failed before fix; final seven cases pass | Synthetic auth and fake transport only |
| Private read / polling / pagination regressions | 33 new cases; initial red runs reproduced account-boundary and identifier defects; 139 related tests passed | Session replacement/logout invalidates reads, buffered rows and subsequent pages; same-session refresh allowed |
| Stream regressions | Initial five cases failed; six final cases and 103 related tests passed | Blocked send/handshake timeout, public/private reconnect gap; no live replay evidence |

No public exchange probes were made: the configured HTTP allowlist does not include BitTeam hosts. No secrets, removed session caches, account endpoints, financial operations, code delivery, builds, tags or releases were used. Account delivery/expiry, financial outcomes, terminal withdrawal statuses, orderId-to-transaction.id mapping and replay remain unverified.

Independent agents cross-reviewed read/archive and stream changes and reran the other area’s synthetic regressions. New tests: test_read_lifecycle_review.py (33), test_cloud_stream_review.py (6), test_cloud_archive_review.py (7). Coverage percentages above belong to the previous audit and were not recomputed.

Code commit `5f65dca`: PR CI [run 41853806810](https://github.com/maxwell2010/bitteam-python-sdk/actions/runs/41853806810) inspected through GitHub API: all eight Windows/Linux Python 3.10-3.13 jobs completed successfully; pytest and skip audit succeeded in each. Distribution build/smoke/upload steps were skipped. This evidence applies to that code commit; this subsequent documentation-only record does not claim a separately observed CI result.


## Second cloud continuation: contract and independent audit

At start, GitHub API confirmed PR #1 open/draft, merged=false, head
`1e46568aebfaf7109e349e50727f0bbe5ed06e8a`, branch
`fix/cloud-lifecycle-timeouts`; remote branch and pull ref matched.
Run [41854178833](https://github.com/maxwell2010/bitteam-python-sdk/actions/runs/41854178833)
completed all eight Windows/Linux Python3.10-3.13 jobs successfully, pytest and
skip audit included; builds were skipped. This is start-state evidence.

| Direction | Implemented and checked offline | Remaining evidence boundary |
|---|---|---|
| P2P account/withdrawal read scenarios | Typed snapshots, client facades, exact frontend payload.data extraction, detached raw fields, redacted repr, separate requested/record IDs, conservative statuses | Saved source excerpts and provenance hashes; no current bundle refetch or account call; no financial outcome or full wallet schema |
| General API-v2 authorization failure | Missing/locally expired cookie fails; private HTTP401 is a per-request typed auth error, without blacklist, clear, spot refresh or mutation retry; lifecycle/identity guards and tracked cancellation | HTTP401, including HTML, does not prove global token expiry. No proven general renewal or token-invalid code contract; same-cookie independent calls remain allowed |
| Market/history integrity | Malformed history result becomes APIError502; boolean/fractional/nonfinite trade timestamps rejected; exact candle volume/order remainder independent of ambient decimal context | Pathological decimal precision above10000 fails explicitly; no additional server status/OHLC/replay guarantees |
| Priority P2P account-boundary checks | Queue during A->logout/login B prevents mutating GET/POST dispatch; identity/owner close, late JSON, same-session refresh and in-flight invalidation tested | Fake cookies, transports and responses only; no mutations actually sent to exchange |
| Priority REST auth identity | Same lifecycle on replacement auth does not authorize stale headers; capture identity through dispatch, limiter/session/JSON, retry and refresh | Five original regressions failed before fix; real REST orchestration with fake HTTP session only |
| Extensible withdrawal composite guard | Overridden prepare helper crossing lifecycle/close fails before mocked submit; same-session refresh allowed | Does not establish a stock public-GET race. Existing tracked sends already cancel stock network_withdrawal/create_order/get_user_orders(pair) when lifecycle changes during the public GET; three preservation regressions cover that behavior |

See [P2P_READ_WORKFLOWS.md](P2P_READ_WORKFLOWS.md) for exact saved provenance,
read-only examples and the general renewal investigation. No new public
BitTeam live reads were performed: exchange/frontend hosts are not in the
executor allowlist, and no alternate route was used. Historical live rows
above remain historical, not reconfirmed. No real secrets, restored caches,
account/financial operations, codes, versions, tags, distributions or releases.


### Independently supplied local evidence (2026-11-04)

Provenance: the user relayed a local reviewer and an external coordinator's
observations in this chat. These were not executed by this cloud environment,
no local output files were supplied, and no independent raw probe log was
inspected here. They are reported evidence, separate from cloud-observed tests.

The local reviewer used the production P2P call implementation with a fake
limiter/response, without network or files. `change_status_all` began in account
A; changing lifecycle and cookie to B during limiter.acquire led to an actual
FakeSession.request with Bearer B. A late response.json returned A's payload
after the switch to B. The new synthetic regressions include this exact
mutating helper, plus other mutating GET/POST paths, identity and close cases.

External coordinator public-only probes used no cookies/auth, TLS certifi,
redirects=false and an 8-second deadline per request:

| Public GET from local host | Reported result | What it does not establish |
|---|---|---|
| https://bitteam-market-back.bit.team/api/cryptocurrency/map | TimeoutError | Permanent unavailability or valid backend schema |
| https://bitteam-market-back.bit.team/api/core/common/cryptos | TimeoutError | Permanent unavailability or valid backend schema |
| https://docs-api.bit.team/api/v1/pages | HTTP502, text/html | Persistent failure or valid JSON contract |
| https://archive.bit.team/api/trades?limit=1&offset=0 | TimeoutError | Permanent unavailability, pagination semantics or parameter correctness |

No private/financial endpoint was called in those probes; results were not
saved to local files. These reported current failures supplement historical
matrix rows without converting them into successful live verification.


Pre-blocking-review cloud verification: Linux Python3.12.14 in the
configured /workspace/venvs/bitteam-sdk environment, full suite 853 passed,
1 native Windows DPAPI skip (854 collected), check_test_skips passed.
101 new tests in this continuation: P2P workflows31, facade1, auth38,
deep market16, REST auth identity9, withdrawal orchestration6. Counts describe
local synthetic coverage, not absence of errors or production API coverage.
Initial REST auth identity regressions gave5failed/1passed; after fixes the
nine-case suite passed, including task scheduling, retry and refresh boundaries.
The production code and related regressions were independently cross-reviewed
by agents; network probes supplied by the user retain the separate provenance
above. New CI must be observed for the pushed commit, not inferred from this
local run or prior successful jobs.


Observed code-commit CI: `0de21edb3d2cd58b4c9a5478af612775b914fb82`, PR
[run41856293623](https://github.com/maxwell2010/bitteam-python-sdk/actions/runs/41856293623).
GitHub API showed all8 Windows/Linux Python3.10-3.13 jobs completed successfully;
pytest and skip audit succeeded in every job, build/wheel smoke/upload steps
were skipped. This entry records that code commit; subsequent documentation
record commits do not inherit an unobserved CI result.


### Review correction: HTTP401 does not prove general-token invalidity

Blocking review identified an unsupported inference in code commit0de21ed:
private HTTP401 (including HTML) populated a persistent rejection blacklist.
No primary-source contract establishes that every private operation's401 means
a globally invalid general token. Permission/confirmation-specific failures or
an intermediary response cannot be ruled out. That blacklist is removed from
the final implementation, not merely bounded or renamed. The earlier successful
CI demonstrates execution of the earlier patch, not the correctness of that
inference. Per-request AuthenticationError remains; independent get_accounts
with the same general cookie is allowed after an operation returns JSON or
HTML401. No automatic clear, refresh, retry or replay occurs. New synthetic
regressions reproduce the blacklist failure before removal. General renewal
and actual token expiry remain unverified.


Post-review final cloud verification: 856 passed,1 native DPAPI skip (857
collected), check_test_skips passed on LinuxPython3.12.14. The current auth
review file has41cases; total added tests since initial PR head1e46568 is104.
New per-request401 regressions gave8failed/33passed on the blacklist patch,
then passed after removal; independent reviewer reran158 related cases.
No primary-source proof of a universal token-invalid401 contract was found.
Final correction CI evidence (exact SHA/run/status) is recorded in the
[existing draft PR#1](https://github.com/maxwell2010/bitteam-python-sdk/pull/1)
after observing GitHub API, separately from the historical code-commit runs
above. CI success proves these tests executed, not server semantics.


## Held-resource owner identity review

A further independent reviewer reported a distinct boundary: lazy P2P,
account-stream and archive resources retain authA while their actual owner
client.rest.auth is replaced by authB; authA lifecycle need not change. Resource
identity/lifecycle checks alone did not detect this.

The cloud agents independently reproduced this with actual BitTeamClient and
BitTeamRestAPI owners and fake HTTP/WebSocket transports. Resources remained
bound to unchanged authA, the real owner held bound authB, and P2P used a shared
owner cookie jar containing B. No HTTP, account, cache or financial operations
were used. Initial red runs: P2P10failed/2passed, archive8failed/2passed,
account streams12failed/1passed.

| Guard/check | Final behavior | Synthetic coverage |
|---|---|---|
| Real REST owner identity | Requires transport.auth is resource.auth, even when lifecycle numbers match or owner.auth is missing | Shared SessionAuth owner helper5cases |
| Held P2P reference | Fails before await/dispatch and after JSON, including queued/scheduled mutations, unchanged resource.auth A and B.clear |18cases; anonymous public calls and sameA refresh remain allowed |
| Held private archive reference | Fails before session acquisition/dispatch and after valid or malformed JSON, before/after B.clear |12cases; public get_trades and sameA refresh remain allowed |
| Held account stream / iterator | Owner check before hello/sub/request/reauth, inside RPC dispatch/reply boundaries and before/after iterator waits |16cases, including buffered and waiting consumers; no old event is returned after owner switch |
| Duck-typed compatibility | Legacy transports lacking auth attribute stay usable; explicit mismatch fails; actual BitTeamRestAPI has no missing-attribute fallback | Covered without weakening real-owner checks |

No lazy-property recreation is relied on: previously issued resource references
perform their own owner checks. The anonymous RPC validation hook is a no-op;
public market/history resources do not acquire account restrictions. A waiting
consumer is checked when it starts/resumes; direct rest.auth assignment is not
claimed to synchronously wake all waiting tasks. Reconnect still has no replay
or atomic L2 guarantee.

Final full cloud suite:907passed,1nativeDPAPI skip (908collected), skip audit
passed on LinuxPython3.12.14.51new owner regressions; independent agents
cross-reviewed and reran the other areas. These counts and fake transports do
not prove all errors removed or any live financial result. Exact final
SHA/run/observed CI status is recorded on the same draft PR#1 after API checks.

The initial full owner run had904passed1skip before three final stream owner-compatibility cases were collected; the final full907passed1skip run includes them. Native DPAPI is the sole skip and skip audit passed.
