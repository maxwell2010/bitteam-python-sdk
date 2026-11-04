"""Deterministic disconnect/cancellation regressions; no real sockets/accounts."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk.websocket import BitTeamWebSocket, candle
from bitteam_sdk.auth import BitTeamAPIError
from bitteam_sdk.market_streams import BitTeamMarketStreams


class Socket:
    def __init__(self, closed=False):
        self.closed = closed

    async def close(self):
        self.closed = True

    async def receive(self):
        await asyncio.Future()

    async def send_json(self, payload):
        pass


def connected():
    client = BitTeamWebSocket(queue_size=1)
    client.ws = Socket()
    client._rpc = AsyncMock(return_value={})
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [None, ConnectionError("disconnected")])
async def test_history_iterator_stays_terminal_after_close_or_disconnect(terminal):
    client = connected()
    sub = await client.subscribe_kline("DEL_USDT")
    sub.queue.put_nowait(terminal)
    with pytest.raises(StopAsyncIteration if terminal is None else ConnectionError):
        await anext(sub)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(sub), 0.2)
    await client.close()


@pytest.mark.asyncio
async def test_history_old_reference_cannot_close_a_replacement_subscription():
    client = connected()
    old = await client.subscribe_kline("DEL_USDT")
    client._subscriptions.clear()  # Disconnected reader retires old registry.
    new = await client.subscribe_kline("DEL_USDT")
    await old.close()
    assert client._subscriptions[new.path] is new
    assert client._rpc.await_count == 2  # No stale unsubscribe frame.
    await client.close()


@pytest.mark.asyncio
async def test_concurrent_history_subscriber_waits_for_ack_and_retries_failed_ack():
    client = connected()
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def rpc(frame):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
            raise ConnectionError("ACK rejected")
        return {}

    client._rpc = AsyncMock(side_effect=rpc)
    first = asyncio.create_task(client.subscribe_kline("DEL_USDT"))
    await entered.wait()
    second = asyncio.create_task(client.subscribe_kline("DEL_USDT"))
    await asyncio.sleep(0)
    assert not second.done()
    release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert isinstance(results[0], ConnectionError)
    assert client._subscriptions[results[1].path] is results[1]
    assert calls == 2
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [BitTeamWebSocket, BitTeamMarketStreams])
async def test_new_connection_waits_until_old_reader_can_no_longer_clear_registry(kind):
    client = kind()
    client.ws = Socket(closed=True)
    started = asyncio.Event()
    sequence = []

    async def old_reader():
        try:
            started.set()
            await asyncio.Future()
        finally:
            sequence.append("old finalized")
            client._subscriptions.clear()

    client._reader_task = asyncio.create_task(old_reader())
    await started.wait()
    new_socket = Socket()

    async def ws_connect(*args, **kwargs):
        sequence.append("new connected")
        client._subscriptions["new marker"] = object()
        return new_socket

    client._session = SimpleNamespace(closed=False, ws_connect=ws_connect, close=AsyncMock())
    client._rpc = AsyncMock(return_value={})
    await client.connect()
    assert sequence == ["old finalized", "new connected"]
    assert "new marker" in client._subscriptions
    client._subscriptions.clear()
    await client.close()


@pytest.mark.parametrize("size", [0, -1, True, 1.5])
def test_history_queue_cannot_be_unbounded_or_invalid(size):
    with pytest.raises(ValueError, match="queue_size"):
        BitTeamWebSocket(queue_size=size)


@pytest.mark.parametrize("patch", [
    {"o": None}, {"c": "NaN"}, {"v": "Infinity"}, {"v": "-1"},
    {"t": True}, {"t": -1}, {"t": "0.25"}, {"t": "Infinity"},
])
def test_candle_parser_rejects_corrupt_values_and_noninteger_timestamps(patch):
    raw = dict(t=0, o="1", h="2", l="0.5", c="1.5", v="3")
    raw.update(patch)
    with pytest.raises(BitTeamAPIError):
        candle("DEL_USDT", "1m", raw)


@pytest.mark.asyncio
async def test_close_fails_pending_rpc_even_without_a_running_reader():
    client = BitTeamWebSocket(timeout=60)
    client.ws = Socket()
    request = asyncio.create_task(client._rpc({"type": "request", "path": "/api/tw/time"}))
    await asyncio.sleep(0)
    assert client._pending
    await client.close()
    with pytest.raises(ConnectionError, match="closed"):
        await asyncio.wait_for(request, 0.2)
    assert not client._pending


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [BitTeamWebSocket, BitTeamMarketStreams])
async def test_close_during_connection_waits_for_handshake_and_closes_result(kind):
    client = kind()
    entered, release = asyncio.Event(), asyncio.Event()
    socket = Socket()

    async def ws_connect(*args, **kwargs):
        entered.set()
        await release.wait()
        return socket

    client._session = SimpleNamespace(closed=False, ws_connect=ws_connect, close=AsyncMock())
    client._rpc = AsyncMock(return_value={})
    opening = asyncio.create_task(client.connect())
    await entered.wait()
    closing = asyncio.create_task(client.close())
    await asyncio.sleep(0)
    assert not closing.done()
    release.set()
    await asyncio.gather(opening, closing)
    assert socket.closed
    client._session.close.assert_awaited_once()
