"""Explicit read-only P2P workflows over saved official frontend contracts.

Provenance: schemas/p2p_site.json get_accounts and get_withdrawal include
source URLs, offsets, source SHA256 values and the relevant JS excerpts.
Accounts: https://bit.team/p2p/_next/static/chunks/pages/_app-3772cf9af2d461b9.js
offset 522690, SHA256 2316cc9e89475e17ce2a2fae1378c40cb7e0eed706e80dc8f72925a7ff37ab49.
Withdrawal: https://bit.team/p2p/_next/static/chunks/6034-f2e976244927be8e.js
offset 6125, SHA256 3b46ec340896bc7fa2673c9b710798220aad5e83fd822515b12c8c027cdec685.
Withdrawal UI status evidence is documented in WITHDRAWAL_TRACKING.md.
These workflows never call mutation helpers or decide successful settlement.
"""
from copy import deepcopy

from .auth import BitTeamAPIError
from .p2p_models import P2PAccountSnapshot, P2PWithdrawalSnapshot
from .services import private_read_guard
from .transactions import transaction_evidence
from .withdrawal_tracking import read_withdrawal


def _check_envelope(payload):
    if (not isinstance(payload, dict) or payload.get("status") is False
            or payload.get("ok") is False or payload.get("errors")
            or payload.get("code", 200) != 200):
        raise BitTeamAPIError(502)


async def read_p2p_accounts(client):
    """Read API-v2 /auth/user and preserve account/user/total_usd fields.

    No wallet balance arithmetic, network availability, or spot currency-ID
    equivalence is inferred. No account calls occur until explicitly awaited.
    """
    guard = private_read_guard(client)
    guard()
    payload = await client.p2p.get_accounts()
    guard()
    _check_envelope(payload)
    if (not isinstance(payload.get("account"), list)
            or not all(isinstance(row, dict) for row in payload["account"])
            or "user" in payload and not isinstance(payload["user"], dict)):
        raise BitTeamAPIError(502)
    raw = deepcopy(payload)
    return P2PAccountSnapshot(tuple(deepcopy(raw["account"])), deepcopy(raw.get("user")),
                              deepcopy(raw.get("total_usd")), raw)


async def inspect_p2p_withdrawal(client, identifier):
    """Read one known P2P withdrawal and inspect its frontend-observed fields.

    The saved JS call site returns HTTP payload.data; this is deliberately not
    a heuristic search for a record. Unknown statuses remain unknown, status=1
    remains pending, and the requested identifier is retained independently
    from any record id. There is no create/confirm/cancel or terminal polling.
    """
    observation = await read_withdrawal(client, identifier, source="p2p")
    _check_envelope(observation.payload)
    row = observation.payload.get("data")
    if not isinstance(row, dict):
        raise BitTeamAPIError(502)
    return P2PWithdrawalSnapshot(observation, transaction_evidence(row, source="p2p"))
