# Test gaps: site, P2P, archive and CI

Latest audit date: 2026-11-05 (historical evidence below retains its dates). This is a scoped evidence matrix, not a claim of complete API coverage. No build/version bump or account requests were performed during this audit.

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

All routes below are relative to fixed `https://api-v2.bit.team/api/v2`. There are 84 operations: 61 extracted helpers plus 23 concrete derived call sites. 79 require SessionAuth general access_token, not API keys or spot access. Five are classified public. Seventeen GET operations mutate state; no live financial, confirmation, code-delivery or other mutation was exercised.

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
| create_withdrawal_body | POST /account/create-withdraw, currency_id in JSON body | SessionAuth | no | Offline routing; coordinator-reported public JS callsite, distinct from legacy query helper |
| create_withdrawal_to_stock_body | POST /account/create-withdraw-to-stock, numeric currency_id95 in body | SessionAuth | no | Explicit raw callsite only; date/hash algorithm and full production body remain unverified |
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

| get_currencies_with_commission | GET /data/currency/with-commission | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| create_wallbtc_operation | POST /wallbtc/operations/create | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| remove_blacklist_users | POST /user/blacklist/remove-users | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| get_email_notification_status | GET /user/notification-status-email | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| get_app_tokens | GET /user/get-app-tokens | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| get_business_payments | GET /user/business/get-payments | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| add_payment_system_temp | POST /user/add-payment-systems-temp | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| get_subscriptions | GET /subscription/list | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| get_active_subscription | GET /subscription/active | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| subscribe_subscription | POST /subscription/subscribe | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| renew_subscription | POST /subscription/renew | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| get_boost_price | GET /boost/get-price | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| get_subscription_price | GET /subscription/get-price | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| get_notifications | GET /user/get-notification | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| get_active_notifications | GET /user/get-active-notification | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| read_all_notifications | GET /user/read-all-notification | SessionAuth | yes | Offline only; user-relayed RAM callsite/trace, no private live verification |
| create_internal_stock_transfer | POST /account/create-withdraw-to-stock | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| get_account_transaction_journal | GET /transactions/account-transactions | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |
| get_transaction_journal | GET /transactions/get-transactions | SessionAuth | no | Offline only; user-relayed RAM callsite/trace, no private live verification |

P2P gaps: no real success/failure/idempotency/insufficient-balance/2FA/device-confirmation tests for mutations; no verified terminal withdrawal enums; two fixed journal paths are established by page/shared/base chain, with no arbitrary journal route inferred from generic getRequestCabinet. `/auth/user` account/additional_wallets/possible_wallets is preserved raw. Child currency IDs belong to API-v2, not spot; offline tests do not establish whether a network is currently enabled. There is no batch withdrawal guarantee. Unknown required body fields must be supplied from separately verified contracts.

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


## P2P withdrawal form callsite correction

New primary-source evidence was relayed by the user's local coordinator on
2026-11-04: anonymous public static GET HTTP200, no cookies/auth, chunk6034
SHA3b46ec340896bc7fa2673c9b710798220aad5e83fd822515b12c8c027cdec685 matches
its saved source hash. FunctionZ near offset5295 posts bodyt to standard
create-withdraw or, for numericcurrency95, create-withdraw-to-stock, then reads
response.data.data.id. This is distinct from legacy createNewWithdraw query
currency_id helper; SITE_INVENTORY's attribution of the active form to that
helper was corrected, not silently merged.

A second coordinator staticGET200 report identifies form bundle Withdraw-
56b2a70d301a037a.js,41423bytes,SHA
cbffa511c29dcfeba14c4fa5f7c24a4b3dc47a4ab75761dd3e51745b246eee86:
form defaults near16625 and selected-wallet currency_id near21434. These are
coordinator observations of public JS, not cloud bundle downloads, independently
recomputed hashes, account reads or successful financial endpoints. SourceURLs,
reported hashes, approximate offsets and exact supplied excerpts are retained
in schema/documentation. The older saved excerpt only established the existing
withdrawal-read callsite; its truncated neighboring function was not itself
proof of these new creation routes.

Catalog now separates65operations:61legacy helpers and4derived callsites.
Two fixed body creation routes preserve raw response envelopes and opaque id;
they do not infer transaction/orderId equality, successful withdrawal status,
confirmation, fees or finality. No automatic route switch or retry occurs.
SDK fixed-callsite policy forbids query parameters for these two body operations
to avoid mixing them with the legacy query helper; this is not a claim that the
backend globally rejects query parameters. Numeric95 is the raw stock branch;
string'95' is not JS number95. Its date/hash algorithm is not implemented.

The pure exported prepare_p2p_withdrawal builds only the standard body, with
currency_id,address,sum,public,comment,label,commission_booster_name. Input
validation is an explicit local policy, not a complete server schema. Exact
amount text and opaque public/commission values are preserved; there is no
network/address validation, balance/commission math, hash95 generation or HTTP.
Currency95 is explicitly unsupported by the planner. Low-level raw operations
still require separately verified caller input; exposing a route does not
establish a valid complete financial request.


## SessionAuth owner, transport retirement and final scoped evidence

The later reviewer identified stale SessionAuth itself as an owner boundary,
not just held resources. Independently reproduced with actual REST/client,
fake RAM cache and transport: stale save mixed A tokens with B cookies; resume,
login/logout and cleanup could use B's owner state. The final auth patch checks
ownership before cache load/save, cookie/token installation, network operations,
and inside scheduled operations, as well as after awaits. Stale clear only
changes A's memory and does not delete a possibly shared B profile or jar.
Initial23-case auth snapshot gave19failed/4passed; related current suites and
independent review passed. No real user cache was loaded, modified or recovered.

REST.auth replacement is now an explicit boundary: validates/binds the new
strategy, cancels old tracked work, retires the old HTTP session and creates a
fresh session/jar for the replacement. It does not copy cookies or delete A/B
caches. The final epoch review also increments the detached auth's lifecycle,
in addition to identity checks, to prevent A-to-B-to-A resurrection. A fake
response deliberately ignored first cancellation and applied a late Set-Cookie:
it remained in retired jarA, never jarB. The old session is closed through shared
shielded retirement work. Independent tests reproduced cancellation losing a
close, concurrent close returning early and a failed close becoming later
success; all3 now pass. Failed retirement remains observable, not guessed closed.
The actual local HTTPS integration suite also passed; no BitTeam account calls.

## Final RAM/journal contract scope

The16 RAM-inventory additions and internal-stock operation are separate from the
three publicly covered SiteAPI paths, which are not counted again. Catalog now
has84operations:61legacy helpers+23derived,79private/5public,17mutatingGET.
Counts describe registered contracts only. Exact source/offset/reported-contract
metadata and the bounded10-JS manifest scope are retained in schema. No complete
all-JS inventory, full backend body schema, permission matrix or API coverage is
claimed. /auth/login and /oauth/token of another auth-client were excluded.

Internal-stock transfer bodycurrency_id/sum/internal_request:true has a separate
raw-response contract with no data.id requirement and its own pure plan. It is
not constrained to the other form's95/date/hash branch; currency/account
eligibility is still unverified. No result fields were read by its primary
callsite, so the SDK does not manufacture them or infer financial success.

Two journal operations preserve only the proven page-prop -> module71801 ->
API-client77016 base chain and page1/limit999 export window, with amount/system
for the typed path. Unknown filters, general pagination and retention are
rejected/not claimed. Deals already mapped to operations/archive, not a new
operation. Generic arbitrary-url helper stays unavailable.

The journal UI switch in3812 offset6723 is exposed separately as ui_state:

| Raw P2P withdraw status | Conservative main state | Journal UI state |
|---|---|---|
|-1|cancelled|cancelled|
|0|created|created|
|1|pending|confirmed|
|2|unknown|done|
|other/unrecognized|unknown|unknown, with raw_status retained|

These are UI labels, not an exhaustive backend enum, settlement evidence,
blockchain confirmations or finality. ui_state_source records the shared source;
its reported SHA and provenance are documented, not rehashed in the cloud.

External blockers remain: real account expiry/renewal/revocation and delivery,
permissions and financial outcomes, complete required bodies for raw mutations,
95-form date/hash, orderId-to-spot-transaction identity, journal retention and
full multi-page export, market/docs/archive backend availability and successful
JSON schemas, private reconnect live behavior, replay and atomic L2 recovery.
The user-reported public static/RAM traces and earlier public-only probe failures
are distinguished from cloud offline execution. Full bundles/RAM logs were not
provided as cloud files; no new cloud public exchange probes or credential
access were used to remove those boundaries. No versions, builds, artifacts,
tags, releases, publications or real financial/account operations were performed.


## Pre-epoch local verification for this audit report

Configured Linux Python3.12.14 environment: **1271 passed, 1 native Windows
DPAPI skip**,1272collected; check_test_skips passed. This includes all confirmed
SessionAuth/REST owner fixes, withdrawal/RAM/journal operations and UI evidence,
with existing local HTTPS integration and independent cross-reviews. Exact
final head and observed CI run are maintained in draft PR#1 description after
GitHub API verification; distributions remain forbidden/skipped.

Intermediate full passes (907/1011/1211 plus native skip) refer to earlier suite
snapshots; they are not the final count. New pure prepare models are features,
not claims of a reproduced production financial failure. The raw route tests
prove offline routing/guards only. A mutable body selector was independently
reproduced changing while queued (4failed before dispatch revalidation, then
passed with zero fake dispatch on mismatch). No actual mutation was exercised.
An integration fixture was updated to the proven data.id response shape, not
used to relax the production response contract. Counts are not proof that all
SDK errors or website/API functionality have been covered.


## Final targeted owner epoch check and report status

The last reviewer asked whether A -> B -> A could restore identity while the
old lifecycle remained current. It was independently reproduced: a tracked
fake HTTP operation deliberately suppressed cancellation and returned a late
reply; held buffered/waiting account subscriptions also revived on the old
identity. Initial regressions: HTTP2failed/1passed, account subscriptions3failed.
This was a confirmed missing epoch boundary, not a speculative change.

Successful detach now increments the previous SessionAuth lifecycle before
canceling its pending operations. It does not call clear, delete cache, copy
cookies, alter tokens/READY-state or reset generation. Identity guards remain
in place. Old operations/subscriptions cannot revive after A -> B -> A; fresh
requests, refresh and new subscriptions on explicitly returned A use its current
epoch and pass. Same-object auth assignment and ordinary same-owner refresh
remain allowed. Invalid replacement is validated before changing the old epoch.
Six new regression cases and independent related owner checks passed.

**Final full cloud suite: 1277 passed, 1 native Windows DPAPI skip; 1278
collected, Linux Python3.12.14. check_test_skips passed.** The earlier1271 count
is the pre-epoch snapshot. The later user-requested spot-selector correction is recorded separately
below; it adds no network mapping. Final exact SHA and CI run/status are recorded in draft PR#1; an external
queued run is pending, never reported as success. No versions, builds, tags,
releases, publications, real cache/session access or financial/account calls.


## Final spot withdrawal selector correction

User-reported production-helper reproduction used only a synthetic catalog:
USDT id3, active=true/status1, limits1..100, Ethereum+Arbitrum, amount2 and a
synthetic destination. Arbitrum's presence in that fixture is not an exchange
support claim. The old prepare_withdrawal returned an Arbitrum plan without
any currency selector. Multi-network non-USDT choices likewise produced the
same indistinguishable payload when only currencyId was known.

The pure planner now fails closed if USDT has no established request_currency
mapping (even if it is the sole catalog link), or if a multi-network non-USDT
choice has no proven selector. withdrawal_networks may still expose unknown
chains as metadata with request_currency/withdraw_enabled unset. No arb,
baseSymbol, new network parameter or new chain support is invented. The three
observed USDT eth/trx/bnb mappings and single-native chain behavior remain.

Red:4failed/5passed pure regressions;8failed/1passed real-client fake-dispatch
cases across SessionAuth/API-key and both request_network_withdrawal and
create_withdrawal. Green:60 related cases, independently cross-reviewed;
unsupported selections cause zero fake POSTs. Only synthetic catalog GETs
were used by composite tests, with all HTTP replaced by fakes.

**Final local suite after this correction:1295passed,1nativeDPAPI skip,
1296collected, Linux Python3.12.14; check_test_skips passed.** Previous1277 is
the pre-selector snapshot. Exact updated head and observed CI status remain
in draft PR#1 description; externally queued jobs are pending, not success.
User cache, account/financial operations, versions/builds/releases untouched.

## Storage, optional runtime and source compatibility review (2026-11-04)

Baseline at 1cbb855: 1295 passed, one native DPAPI skip. All work below uses
synthetic data, fake account transports or isolated local runtimes; no BitTeam
account/financial endpoint or user cache was accessed. No SDK distribution was
built/installed, and version metadata remains frozen.

| Area | Actual verification and corrected behavior | Limits |
| --- | --- | --- |
| SQLite | 21 runtime regressions, including real file and :memory: connections; the original memory database disappeared after init. Owned memory connection now lasts until close; rollback/cancellation, series isolation and retention are exercised. | Synthetic local data only. |
| PostgreSQL | Real PostgreSQL 16.15, asyncpg 0.32.0, isolated tmpfs container and per-run disposable schema. Repeated init/failed init, atomic upsert+retention rollback/cancel, concurrent writers and close lifecycle exercised. Per-series transaction advisory lock prevents overlapping retention snapshots. | Not a mock result or a production deployment/load test. Dedicated CI service job runs the same standalone script; server absence is a failure, not a pytest skip. |
| History policy | Default rolling retention remains 2000 per symbol/interval; explicit retention=None preserves all rows for SQLite and PostgreSQL. Latest-first SQL results are returned chronologically. | Persistence is bounded by caller storage capacity in full-history mode. |
| DataFrame/charts | 8 real pandas/Plotly checks: pandas 3.1.1/Plotly 7.1.0 and independently pandas 2.2.3/Plotly 5.24.1, Python 3.12.14. Empty OHLCV now has DatetimeIndex and can resample. show=False returns Figure; JSON/self-contained HTML checked without browser or network renderer. | Numeric frames can round decimals; timestamps retain legacy naive UTC, input order and duplicates. Infinity acceptance was observed, not classified as a new crash or invented validation contract. |
| Core-only source | Fresh venv, requirements-sdk.txt only, Python 3.12.14 -I, explicit checkout root, all 33 exports, constructors/idempotent close and pure helpers passed. pandas/plotly/asyncpg/aiosqlite absent by module spec and distribution metadata. HTTP/connect/cache operations forbidden. | This is source-only verification, NOT installed-wheel verification; no SDK install/build. Separate CI job repeats it. |
| Facades/examples | Real README offline blocks execute with HTTP prohibited; captured auth protects client cleanup across awaits. Missing ticker price no longer fabricates zero; invalid/nonfinite/negative values reject. | Auth example is explicitly side-effecting and was not run against an account. |
| Source documentation | project.readme now resolves to tracked root README; legacy documentation preserved. Static regressions validate tracked readme, case-sensitive relative Markdown links and casefold path collisions. | No packaging artifact was generated; external links and heading anchors are not fetched/validated. |

CI policy now runs feature changes through pull_request only, preserves main
push checks and all eight Windows/Linux Python 3.10-3.13 matrix combinations,
and cancels superseded runs per workflow/event/PR-or-ref. PostgreSQL and core
source jobs are additional checks. Push/PR distribution steps remain disabled.

The previously queued runs 41864486890 (PR) and 41864480057 (push), both for
1cbb855, subsequently completed with six successful and two failed jobs each.
All four failed logs identify the same Python 3.10 test-only AttributeError:
Task.cancelling() is unavailable. The assertion now yields to the event loop
and checks that the pending task remains unfinished. No SDK behavior/check was
disabled. The original queue cause is not established by available metadata.
Cancellation of the duplicate was attempted while queued but GitHub returned
Forbidden; no cancellation occurred, and completed runs were not retried for
cancellation. Exact final SHA and CI evidence are recorded in draft PR #1.

The existing account/financial, public-live and limited static-JS provenance
boundaries above remain unchanged. This review does not establish complete
site coverage, backend terminal enums, token-expiry semantics, replay guarantees
or any new withdrawal-network selector.

Final targeted actual-PG check additionally uses TWO separate PostgresStorage
pools with retention=1 and a client-held real SQL advisory barrier. Server
pg_stat_activity proves both same-key writers are blocked; another symbol and
interval finish concurrently. Releasing the barrier leaves only the latest
row. Cancellation while waiting and a fresh subsequent write pass. The race
was NOT reproduced with the current database lock; no additional production
change was made. All 12 standalone PostgreSQL checks passed and disposable
schemas were removed.

Final full offline/default suite: **1362 passed, 1 native DPAPI skip**,
1363 collected, Linux Python3.12.14; skip audit passed. Runtime PostgreSQL checks
are separate actual-service checks, not hidden skips or mock passes. Exact-SHA
GitHub CI must be reported separately from these local results.

Exact-head CI at 0e25d0c passed all four Linux matrix jobs, actual PostgreSQL
and core source smoke. Windows exposed a test portability defect: README was
read with the platform default cp1252, raising UnicodeDecodeError. The offline
README regression now explicitly reads UTF-8, matching the tracked document.
This is a test correction, not a disabled Windows check. Final replacement SHA
and CI outcome are recorded in draft PR #1.

## Source inventory and manifest correction after 20e230 (2026-11-04)

Independent static review found MANIFEST.in excluded the canonical root README,
and package_source.py still referenced the removed SDK README and performed
archive creation at import. The old script was read, NEVER executed/imported.

package_source.py is now a stdlib-only public-file planner with a main guard:
explicit path inventory or Git-tracked allowlist, sorted relative names,
required-input checks, rejected traversal/symlinks/case collisions. Import does
not import SDK, invoke Git, create directories, ZIPs or checksums. Its CLI only
prints JSON; no archive writer remains. Public inputs include root README,
AGENTS, metadata/dev requirements, workflow, docs, SDK sources/schema/report
inputs, tests and verification scripts. Legacy README is preserved. Known
secret/cache/session/build/output paths are excluded; this is an audited source
allowlist, not a claim that arbitrary file contents can be classified as safe.

The actual setuptools FileList template processor is used WITHOUT a build
command to compare manifest selection with the source plan and reject synthetic
sensitive/runtime paths. Setuptools is an explicit development test dependency;
SDK metadata/version is unchanged. Processing the OLD manifest against the
public inventory reproduced missing README/AGENTS/docs inputs, without sdist.

A plain temporary copy of planned source files (no archive, no .git) now passes
the readme/link checker. An explicit standalone file inventory prevents querying
an enclosing Git repository. Regressions forbid Git for the VCS-free fixture
and run its copied CLI under Python -I -B, including explicit sibling planner
loading. This addresses extracted-source test inputs without adding a skip or
shipping .git. Focused checks:30 passed before the final full suite.

No ZIP/wheel/sdist, SDK installation, version change, release, real account call
or user-cache access was used. This is inventory/manifest/source-tree validation,
NOT installed-wheel or generated-sdist verification. Exact final SHA and all10
CI jobs are recorded in draft PR#1; previous 20e230 CI success predates these fixes.

Final source-plan suite: **1388 passed,1 native DPAPI skip**,1389 collected;
skip audit passed on Linux Python3.12.14. All30 focused source checks also ran
successfully from a plain copied source tree without .git (inside a parent
checkout), including planner CLI and isolated documentation CLI. Manifest
case-insensitive exclusions match the planner for tested synthetic secret,
session/cache/build variants. The final inventory changes are independently
reviewed. Exact-SHA CI remains a separate result in PR#1.

## Resumed cancellation, resources and diagnostics audit (2026-11-05)

Pinned baseline f8ae6e0:1388 passed,1 native DPAPI skip; skip audit passed.
Its successful10-job CI predates the following independently reproduced fixes.
All account/auth/transport tests use synthetic RAM objects; no user cache,
credentials, account request, code delivery or financial operation is involved.

| Area | Reproduced boundary and correction | Evidence/limits |
| --- | --- | --- |
| Account-check cleanup | Initial save, cleanup/cache step and final diagnostics failures could bypass transport close or mask cancellation. Nested cleanup now closes independently of report writes and preserves primary errors/cancellation; an interrupted check cannot report passed. | RAM-only failing save/step/cache/logout/close paths; ordinary failed-check False behavior retained when diagnostics work. Not a real account run. |
| WebSocket subscriptions | Same-path subscribe could ACK before a late UNSUB; accepted SUB cancellation/timeout left an unowned live server subscription. Lifecycle lock spans ACK; uncertain SUB/UNSUB retires connection and invalidates other refs. Old close rechecks subscription identity inside lock. | Production RPC with in-memory fake server and deterministic barriers, history+market; cancellation/timeout/second cancellation/close failure. No live server guarantee or replay inferred. |
| WebSocket resource close | Socket-close failure/cancellation skipped reader/session cleanup. Remaining resources now close before the original failure is raised. A retiring socket cannot be reused while its protected cleanup is pending. | Fake sessions/readers, including a failing close. A failure is not reported as successful shutdown. |
| Archive shutdown | Cancelled/concurrent close callers could return while the session remained open; a failed close became later apparent success. One shielded cleanup task remains awaitable and retains its failure. | Fake transport only; no claim of a newly successful public archive call. |
| REST owner epoch | API-key A -> B -> A could accept old private JSON because identity matched again. Transport epoch now invalidates prior-era queued dispatch and replies for all auth strategies. | Real REST _request/_send with fake limiter/response, GET/POST, direct and roundtrip replacement; same strategy assignment remains valid. Existing same-session refresh tests retained. |
| Diagnostic redaction | Arbitrary string error.code entered the anonymous report; driver setup/cleanup and session CLI failures escaped via raw tracebacks; REST and history/market WS client errors/timeouts exposed raw messages. | Synthetic sentinel strings, no live report written. Exported HTTP status/code restricted to plain integers; CLI exits remain nonzero, cleanup is exercised; transport errors do not trigger retries; WS connect/send/close sentinel regressions cover both classes. |
| Local input GUI | No production GUI defect reproduced. Actual Tk9.0 on isolated Xorg1.21.1.16 dummy display passed6 synthetic scenarios: paste/selection/CtrlV/ShiftInsert, show/hide, count/clear, masked TOTP/device inputs, Return/cancel and empty clipboard. | HTTP client creation forbidden, no account flow invoked. Standalone check_window_prompt_runtime.py requires a disposable display; no added pytest skip. Not native Codex UI, Windows/RU-layout, real2FA or logout delivery verification. Own Xorg stopped. |

The fake transport/script failures prove diagnostic boundary bypasses, not that
real secrets were actually leaked. Known frontend/static facts and historical
public-live results retain their earlier provenance; this resumed audit claims no new successful BitTeam live verification. Public-facade observations without an established
contract (for example None symbols or boolean limits) are not labelled defects.
Account expiry/renewal/revocation/delivery, financial outcomes/finality, ID links,
archive availability and live reconnect/replay remain external/unverified.

Version/install/distribution freeze continues: no SDK install, ZIP/wheel/sdist,
version/tag/release/publication or merge. Final full-suite/skip/CI results for the
replacement head are recorded below/in draft PR#1 independently of this baseline.

Full-suite integration initially found one outdated fake ACK fixture: it had no
replacement-session transport after uncertain-ACK retirement and could fall
through to connection establishment. It now supplies an explicit fake replacement
socket/hello and asserts the old socket is closed and exactly two user SUBs
occur;51 related cases passed. No service availability or live result is inferred
from that failed fixture. Account/financial operations were never involved.

Final resumed full suite: **1458 passed,1 native Windows DPAPI skip**,
1459 collected, Linux Python3.12.14; skip audit passed.70 new meaningful
regressions cover the reproduced boundaries; count is not an all-bugs claim.
Independent cross-reviews passed for cleanup, WS, REST/archive and diagnostics.
Actual GUI6checks remain a separate runtime result, not mocked/default pytest
or Windows proof. No new skips; final exact-SHA10-job CI is recorded in PR#1.
