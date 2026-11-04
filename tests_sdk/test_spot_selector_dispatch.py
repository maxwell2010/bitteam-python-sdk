"""Synthetic catalogs and fake REST only; no withdrawal request leaves tests."""
import pytest

from bitteam_sdk import BitTeamClient, SessionAuth, AuthState


def catalog(symbol):
    # Arbitrum is deliberately synthetic here, not an exchange-support claim.
    chains = ["Ethereum", "Arbitrum"] if symbol == "usdt" else ["Ethereum", "Tron"]
    return [{"id": 3, "symbol": symbol, "active": True, "status": 1,
        "txLimits": {"minWithdraw": "1", "maxWithdraw": "100"},
        "links": [{"blockChain": chain} for chain in chains]}]


@pytest.mark.asyncio
@pytest.mark.parametrize("session", [False, True])
@pytest.mark.parametrize("method", ["request_network_withdrawal", "create_withdrawal"])
@pytest.mark.parametrize("symbol,network", [("usdt", "Arbitrum"), ("synthetic", "Tron")])
async def test_unsupported_selector_never_reaches_submit_transport(session, method, symbol, network):
    client = BitTeamClient(auth=SessionAuth()) if session else BitTeamClient("synthetic-key", "synthetic-secret")
    if session:
        client.auth.state, client.auth._access = AuthState.READY, "synthetic-access"
    else:
        client._keys_validated = True
    calls = []
    async def fake_send(verb, url, **kwargs):
        calls.append((verb, url, kwargs))
        if verb == "GET":
            return {"result": {"count": 1, "currencies": catalog(symbol)}}
        return {"ok": True, "result": {"synthetic": True}}
    client.rest._send = fake_send
    try:
        with pytest.raises(ValueError):
            if method == "create_withdrawal":
                await client.create_withdrawal(symbol, "synthetic-only", "2", network=network)
            else:
                await client.request_network_withdrawal(symbol, address="synthetic-only", amount="2", network=network)
        assert calls and all(verb == "GET" for verb, _, _ in calls)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_unknown_catalog_network_remains_inspectable_without_submit_plan():
    client = BitTeamClient()
    async def fake_send(*args, **kwargs):
        return {"result": {"count": 1, "currencies": catalog("usdt")}}
    client.rest._send = fake_send
    try:
        choices = await client.get_withdrawal_networks("USDT")
        unknown = next(choice for choice in choices if choice.network == "Arbitrum")
        assert unknown.request_currency is None
        assert unknown.withdraw_enabled is None
        assert client.rest._session is None
    finally:
        await client.close()
