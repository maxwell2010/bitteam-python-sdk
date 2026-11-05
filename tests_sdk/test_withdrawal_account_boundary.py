"""Synthetic orchestration only; the submission transport is always mocked."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import BitTeamClient, SessionAuth, AuthState


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["login", "close"])
async def test_network_withdrawal_never_submits_after_preparation_crosses_boundary(boundary):
    # This exercises an overridden/extensible helper, not a stock GET race.
    client = BitTeamClient(auth=SessionAuth())
    client.auth.state = AuthState.READY
    client.auth._access = "synthetic"
    client.rest._request = AsyncMock()

    async def prepare(*args, **kwargs):
        if boundary == "login":
            client.auth._lifecycle += 1
        else:
            client._closed = True
        return {"payload": {"synthetic": True}}

    client.prepare_withdrawal = prepare
    try:
        with pytest.raises(asyncio.CancelledError if boundary == "login" else RuntimeError):
            await client.request_network_withdrawal("USDT", amount="1", address="synthetic")
        client.rest._request.assert_not_awaited()
    finally:
        client._closed = False
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["network_withdrawal", "create_order", "user_orders"])
async def test_stock_composites_already_cancel_when_public_get_crosses_lifecycle(operation):
    client = BitTeamClient(auth=SessionAuth())
    client.auth.state, client.auth._access = AuthState.READY, "synthetic"
    calls = []

    async def fake_send(method, url, **kwargs):
        calls.append((method, url))
        assert method == "GET"
        client.auth._lifecycle += 1
        if url.endswith("/currencies"):
            return {"result": {"count": 1, "currencies": [{
                "id": 2, "symbol": "eth", "active": True, "status": 1,
                "blockChain": "Ethereum", "links": [], "txLimits": {}}]}}
        return {"result": {"pairs": [{"id": 24, "name": "del_usdt"}]}}

    client.rest._send = fake_send
    try:
        with pytest.raises(asyncio.CancelledError):
            if operation == "network_withdrawal":
                await client.request_network_withdrawal("ETH", amount="1", address="synthetic")
            elif operation == "create_order":
                await client.create_order("DEL_USDT", "buy", price="1", amount="1")
            else:
                await client.get_user_orders(pair="DEL_USDT")
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_network_withdrawal_allows_refresh_in_same_session():
    client = BitTeamClient(auth=SessionAuth())
    client.auth.state = AuthState.READY
    client.auth._access = "synthetic"
    client.rest._request = AsyncMock(return_value={"ok": True})

    async def prepare(*args, **kwargs):
        client.auth._generation += 1
        return {"payload": {"synthetic": True}}

    client.prepare_withdrawal = prepare
    try:
        assert await client.request_network_withdrawal("USDT", amount="1", address="synthetic") == {"ok": True}
        client.rest._request.assert_awaited_once()
    finally:
        await client.close()
