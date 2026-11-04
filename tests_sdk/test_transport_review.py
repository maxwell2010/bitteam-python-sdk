"""Independent regressions from the transport review; no external network."""
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest

from bitteam_sdk import AuthState, BitTeamAPIError, SessionAuth
from bitteam_sdk.rest import BitTeamRestAPI
from bitteam_sdk.websocket import BitTeamWebSocket, KlineSubscription


class FakeSocket:
    def __init__(self):
        self.closed = False
        self.frames = asyncio.Queue()

    async def receive(self):
        return await self.frames.get()

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_revoked_subscription_is_removed_and_can_be_subscribed_again():
    client = BitTeamWebSocket()
    socket = FakeSocket()
    client.ws = socket
    path = "/klines/del_usdt/1m"
    old = KlineSubscription(client, path, "del_usdt", "1m", asyncio.Queue())
    client._subscriptions[path] = old
    client._rpc = AsyncMock(return_value={})
    client._reader_task = asyncio.create_task(client._reader())
    try:
        socket.frames.put_nowait(SimpleNamespace(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"type": "revoke", "path": path, "message": {}})))
        with pytest.raises(ConnectionError):
            await asyncio.wait_for(anext(old), 0.5)
        assert path not in client._subscriptions

        replacement = await client.subscribe_kline("DEL/USDT", "1m")
        assert replacement is not old
        client._rpc.assert_awaited_once_with({"type": "sub", "path": path})
        assert client._subscriptions[path] is replacement
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_session_get_orders_resolves_normalized_pair_and_sends_where_filter():
    auth = SessionAuth()
    client = BitTeamRestAPI(auth=auth)
    auth.state, auth._access = AuthState.READY, "synthetic-access"
    client._pair_id = AsyncMock(return_value=24)
    payload = {"ok": True, "result": {"orders": []}}
    client._send = AsyncMock(return_value=payload)
    try:
        assert await client.get_orders("DEL/USDT") == payload
        client._pair_id.assert_awaited_once_with("del_usdt")
        args, kwargs = client._send.await_args
        assert args == ("GET", "https://bit.team/trade/api/ordersByUser")
        assert kwargs["params"]["where[pairId]"] == 24
        assert kwargs["params"]["type"] == "active"
        assert "pair" not in kwargs["params"]
    finally:
        await client.close()


class FakeResponse:
    status = 429

    def __init__(self, retry_after):
        self.headers = {"Retry-After": retry_after}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        return {"ok": False, "code": 429000}


class FakeSession:
    def __init__(self, response):
        self.response = response

    def request(self, *args, **kwargs):
        return self.response


@pytest.mark.asyncio
async def test_numeric_retry_after_is_not_shortened():
    client = BitTeamRestAPI()
    client._get_session = AsyncMock(return_value=FakeSession(FakeResponse("60")))
    with pytest.raises(BitTeamAPIError) as error:
        await client._send("GET", "https://bit.team/trade/api/pairs")
    assert error.value.retry_after == 60


@pytest.mark.asyncio
async def test_http_date_retry_after_is_recognized():
    future = datetime.now(timezone.utc) + timedelta(seconds=90)
    client = BitTeamRestAPI()
    client._get_session = AsyncMock(return_value=FakeSession(
        FakeResponse(format_datetime(future, usegmt=True))))
    with pytest.raises(BitTeamAPIError) as error:
        await client._send("GET", "https://bit.team/trade/api/pairs")
    assert error.value.retry_after is not None
    assert 88 <= error.value.retry_after <= 91


@pytest.mark.asyncio
async def test_retry_after_above_wait_budget_propagates_without_early_retry(monkeypatch):
    client = BitTeamRestAPI(max_read_retries=2, max_retry_wait=30)
    client._send = AsyncMock(side_effect=BitTeamAPIError(429, 429000, retry_after=60))
    sleep = AsyncMock()
    monkeypatch.setattr("bitteam_sdk.rest.asyncio.sleep", sleep)
    with pytest.raises(BitTeamAPIError) as error:
        await client._request("GET", "/pairs", public=True)
    assert error.value.retry_after == 60
    assert client._send.await_count == 1
    sleep.assert_not_awaited()
