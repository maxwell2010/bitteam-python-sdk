# P2P read workflows and general authorization evidence

These are read contracts from saved official frontend excerpts, not a successful
account run. No account was accessed during cloud verification.

## Existing account and withdrawal reads

```python
# Requires an already authenticated SessionAuth with a general access_token.
# These lines make private reads when awaited; they were tested with fakes only.
accounts = await client.get_p2p_accounts()
snapshot = await client.inspect_p2p_withdrawal(existing_p2p_withdrawal_id)
```

`P2PAccountSnapshot.accounts` contains API-v2 account dictionaries. `user`,
`total_usd`, nested wallet fields and the full response remain raw. No Decimal
conversion, enabled-network claim or substitution of spot currency IDs occurs.
The saved `/auth/user` callsite reads top-level account/user/total_usd.

`P2PWithdrawalSnapshot` retains the original observation and conservative
transaction evidence from exactly `payload.data`, matching the saved callsite.
`requested_identifier` and `record_identifier` are separate. Their presence does
not prove a correspondence to spot transaction IDs or withdrawal orderId.
For `type=withdraw`, observed numeric -1/0/1 mean cancelled/created/pending;
other values stay unknown. There is no inferred successful terminal state,
blockchain finality, automatic confirmation or create-and-wait workflow.

Payload fields are excluded from snapshot repr and copied from the API result.
Copies are detached from transport payloads, not recursively immutable.
Held private resources also require their actual REST owner to retain the
same auth object; replacing client.rest.auth invalidates old references, even
when resource.auth and its lifecycle did not change. Public anonymous reads
remain allowed. Reads fail across account lifecycle changes; refresh within the same session
is allowed. Server and parsing errors propagate rather than becoming empty data.

## Provenance and limits

`bitteam_sdk/schemas/p2p_site.json` retains source URL, SHA256, offset and excerpt:

- Accounts: `_app-3772cf9af2d461b9.js`, offset 522690, SHA256
  `2316cc9e89475e17ce2a2fae1378c40cb7e0eed706e80dc8f72925a7ff37ab49`.
- Existing withdrawal: `6034-f2e976244927be8e.js`, offset 6125, SHA256
  `3b46ec340896bc7fa2673c9b710798220aad5e83fd822515b12c8c027cdec685`.
- Numeric withdrawal display mapping is described with its public source URL
  in `bitteam_sdk/WITHDRAWAL_TRACKING.md`. UI default-success is not a server enum.

These excerpts were inspected offline. The original JS bundles were not fetched
again in this continuation; BitTeam hosts are outside the executor allowlist.
Saved hashes are provenance identifiers, not a newly verified hash of a current
download. The full bundles are not in this checkout.

## General API-v2/P2P authorization renewal

The saved callsites establish general `access_token` bearer use. The `/auth/user`
error branch clears frontend auth/token state; the adjacent logout excerpt
mentions `access_token`, `refresh_token`, spot `access` and `refresh` cookies.
Cookie names and logout cleanup do not establish a refresh endpoint, method,
payload, rotation rules, expiry schedule or replay safety.

The implemented spot `/refresh-token` flow is a different contract and must not
be used to renew API-v2 general authorization. No general refresh endpoint or
automatic relogin is invented. Missing/locally expired general cookies fail
before dispatch. A private HTTP 401 is an AuthenticationError for that request
with one attempt, including a non-JSON/HTML response. The status alone does not
prove global token expiry: operation permissions, confirmation requirements
or an intermediary may have caused the rejection. There is no automatic token
blacklist, cookie clearing, spot refresh or replay. A subsequent independent
explicit call may use the same general cookie. Private in-flight transport
work is tracked so local session invalidation cancels blocked reads. Mutating
GET routes never receive retries.

Actual token expiry, revocation, rotation and renewal require a separately
authorized account experiment plus a verified renewal contract. No such
experiment, code delivery or financial operation was performed here.


## Pure preparation of the standard form body

```python
from bitteam_sdk import prepare_p2p_withdrawal

plan = prepare_p2p_withdrawal(
    selected_p2p_currency_id,
    address="caller-supplied-destination",
    amount="1.2500",
)
# No HTTP occurs. plan.payload is a detached body; plan.operation is metadata.
```

This is the confirmed active form body contract, separate from the legacy
create_new_withdraw helper's query currency_id. New fixed raw catalog operations
are create_withdrawal_body and create_withdrawal_to_stock_body; they do not
accept query parameters, switch routes automatically, flatten IDs or execute
plans implicitly. Exposing them is not proof of a valid full production request.
The frontend callsite reads data.id; its response need not carry status=true.
Explicit error envelopes still fail. No success/finality or spot ID link is
inferred from the returned id or HTTP200.

Planner fields: address,public,comment,label,sum,commission_booster_name,
currency_id. Amount must be positive plain ASCII decimal text and is preserved
exactly. Integercurrency_id, nonblank address and text comment/label are local
validation policies; they do not establish the full backend schema. public and
commission_booster_name are opaque copied values, with no guessed meaning or
fee calculation. Currency95's separate stock branch needs an unproven date/hash
contract, so the pure planner rejects it and the route stays explicitly raw.

Provenance: user-relayed anonymous staticGET200 by a local coordinator, not a
cloud financial request. Chunk6034 SHA3b46ec340896bc7fa2673c9b710798220aad5e83fd822515b12c8c027cdec685,
functionZ near5295; form Withdraw-56b2a70d301a037a.js SHA
cbffa511c29dcfeba14c4fa5f7c24a4b3dc47a4ab75761dd3e51745b246eee86,
41423bytes, form defaults near16625 and currency selection near21434.
SITE_INVENTORY records fullURLs and corrects the earlier form/query-helper
misattribution. The cloud run did not re-download the bundles or recalculate
those hashes. No real mutation, confirmation or code delivery was exercised.


## Separate internal-stock transfer preparation

```python
from bitteam_sdk import prepare_p2p_internal_transfer

plan = prepare_p2p_internal_transfer(selected_p2p_currency_id, "1.2500")
# Still pure: {currency_id, sum, internal_request: True}. Nothing is submitted.
```

This distinct manifest-linked callsite posts to the same stock endpoint but
uses a different body: currency_id,sum,internal_request=true. It does not read
response fields. It therefore has a separate raw operation,
create_internal_stock_transfer, without required data.id, address, date or
hash. The planner does not restrict this callsite to95 and does not infer that
every currency/account is eligible. Its local validation preserves positive
integer IDs and exact positive decimal text. The other wallet withdrawal form's
95/date/hash branch remains separate and unsupported by its standard planner.

Provenance: user-relayed local RAM/static review, manifest-linked
https://bit.team/p2p/_next/static/chunks/pages/Cabinet/WalletAction/SpotAssetsTransfer-370f165e27881048.js,
SHA f201f8530c9b0e65ecb5269f261d1e543c0b7b0e0881c0391b7ab8ed495efe28,
offset16015. No financial endpoint was exercised. The source's subsequent
refresh/success UI flow is not a settlement or blockchain-finality guarantee.

## Journal export contracts and UI labels

Journal methods expose only proven fixed paths and export query page1/limit999;
get_transaction_journal additionally requires type amount or system. No arbitrary
filters, multi-page traversal, retention or server-snapshot guarantee is inferred.
Full page/shared-module/API-base chain is recorded in schemas/p2p_site.json and
SITE_INVENTORY. The generic getRequestCabinet helper stays unexposed.

For P2P type=withdraw, TransactionEvidence.ui_state separately records the
explicit journal UI labels cancelled/created/confirmed/done for-1/0/1/2;
unknown values remain unknown. Main state1 remains pending and state2 remains
unknown. UI done does not prove completed exchange execution, exhaustive backend
status enums, transaction confirmations or blockchain finality. Raw status and
payload remain available; no equality to spot orderId/transaction.id is inferred.

## SessionAuth and transport ownership

Owner checks also cover SessionAuth cache save/load, token installation,
login/logout/refresh and cookie mutation. Stale A may clear its own memory but
cannot clear B's jar or delete a cache/profile that may be shared with B.
Replacing REST.auth cancels old tracked work and detaches its HTTP session.
New-owner requests use a fresh jar: a late old-response Set-Cookie is confined
to the retired jar, even when fake cancellation cleanup still processes it.
Retired session closure is shared and protected from caller cancellation;
concurrent close waits for it, and failed closure remains an error to later
callers. No old cookies are copied into the replacement owner's session.
These mechanisms were checked with real REST/client objects and fake RAM
transports/cache plus the existing local HTTPS suite, not a BitTeam account.


Final epoch boundary: successful REST auth detach increments the old auth
lifecycle as well as canceling work and retiring its jar. A -> B -> A cannot
make an old cancellation-immune reply or held subscription current again.
Returned A may issue fresh requests/refresh/subscriptions in its new epoch;
ordinary same-owner refresh/assignment remains allowed. Tokens, cache and
generation are not cleared by detach and no old jar is copied.
