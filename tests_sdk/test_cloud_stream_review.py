"""Synthetic timeout and reconnect regressions; no server or account access."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest

from bitteam_sdk.websocket import BitTeamWebSocket
from bitteam_sdk.market_streams import BitTeamMarketStreams, MarketStreamGap
from bitteam_sdk.account_streams import BitTeamAccountStreams
from bitteam_sdk.auth import SessionAuth, AuthState
from bitteam_sdk.rest import BitTeamRestAPI


class Socket:
    def __init__(self):
        self.closed = False
        self.incoming = asyncio.Queue()

    async def receive(self):
        return await self.incoming.get()

    async def close(self):
        self.closed = True

    async def send_json(self, payload):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [BitTeamWebSocket, BitTeamMarketStreams])
async def test_rpc_timeout_includes_blocked_send_and_releases_pending(kind):
    client = kind(timeout=0.01)
    client.ws = Socket()
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def blocked_send(payload):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    client.ws.send_json = blocked_send
    task = asyncio.create_task(client._rpc({"type": "request"}))
    try:
        await entered.wait()
        done, _ = await asyncio.wait([task], timeout=0.3)
        assert task in done, "SDK timeout did not cover send_json"
        with pytest.raises(asyncio.TimeoutError):
            await task
        assert cancelled.is_set()
        assert not client._pending
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [BitTeamWebSocket, BitTeamMarketStreams])
async def test_connection_timeout_cancels_handshake_and_closes_session(kind):
    client = kind(timeout=0.01)
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def blocked_handshake(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    session = SimpleNamespace(closed=False, ws_connect=blocked_handshake, close=AsyncMock())
    client._session = session
    task = asyncio.create_task(client.connect())
    try:
        await entered.wait()
        done, _ = await asyncio.wait([task], timeout=0.3)
        assert task in done, "SDK timeout did not cover WebSocket handshake"
        with pytest.raises(asyncio.TimeoutError):
            await task
        assert cancelled.is_set()
        assert client.ws is None and client._reader_task is None
        session.close.assert_awaited_once()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("private", [False, True])
async def test_reconnect_waiting_reader_observes_gap_during_async_socket_close(private):
    transport = None
    if private:
        auth = SessionAuth()
        transport = BitTeamRestAPI(auth=auth)
        auth.state, auth._access = AuthState.READY, "synthetic-access"
        client = BitTeamAccountStreams(auth)
        client._auth_generation = auth.generation
    else:
        client = BitTeamMarketStreams()
    socket = Socket()
    client.ws = socket
    client._rpc = AsyncMock(return_value={})
    old = await (client.subscribe_balances() if private else client.subscribe_pairs())
    path = old.subscription.path if private else old.path
    client._reader_task = asyncio.create_task(client._reader())
    consumer = asyncio.create_task(anext(old))
    await asyncio.sleep(0)

    async def asynchronous_close():
        socket.closed = True
        socket.incoming.put_nowait(SimpleNamespace(type=aiohttp.WSMsgType.CLOSED))
        # Model a transport close that yields while the reader and consumer run.
        await asyncio.wait([consumer], timeout=0.3)

    socket.close = asynchronous_close

    async def reconnect_without_network():
        if client.ws.closed:
            client.ws = Socket()

    client.connect = reconnect_without_network
    try:
        restored = await client.reconnect([old])
        with pytest.raises(MarketStreamGap):
            await consumer
        assert restored[path] is not old
    finally:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
        await client.close()
        if transport is not None:
            await transport.close()
