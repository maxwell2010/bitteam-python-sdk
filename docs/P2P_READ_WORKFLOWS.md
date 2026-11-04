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
