"""Public market subscriptions tested without a live account or network."""
import asyncio
from datetime import datetime
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest

from bitteam_sdk.market_streams import BitTeamMarketStreams, MarketEvent, MarketStreamGap, pair_identity


class FakeSocket:
    def __init__(self):
        self.closed = False
        self.frames = asyncio.Queue()
        self.closed_event = asyncio.Event()
        self.sent = []

    async def receive(self):
        return await self.frames.get()

    async def send_json(self, value):
        self.sent.append(value)

    async def close(self):
        self.closed = True
        self.closed_event.set()

    def publish(self, path, payload, *, kind="pub"):
        self.frames.put_nowait(SimpleNamespace(type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"type": kind, "path": path, "message": payload})))


def connected_client(queue_size=4):
    client = BitTeamMarketStreams(queue_size=queue_size)
    client.ws = FakeSocket()
    client._rpc = AsyncMock(return_value={})
    return client


def reconnect_without_network(client):
    async def connect():
        if client.ws is None or client.ws.closed:
            client.ws = FakeSocket()
    client.connect = AsyncMock(side_effect=connect)


@pytest.mark.asyncio
async def test_reconnect_replaces_bounded_queues_and_marks_every_old_stream_gap():
    client = connected_client(queue_size=1)
    old = await client.subscribe_orderbook(24)
    omitted = await client.subscribe_pairs()
    old.queue.put_nowait({"sequence": 7})
    old_socket = client.ws
    reconnect_without_network(client)
    restored = await client.reconnect([old, old])
    assert old_socket.closed
    assert set(restored) == {old.path}
    new = restored[old.path]
    assert new is not old and new.queue.maxsize == 1 and new.queue.empty()
    for subscription in (old, omitted):
        with pytest.raises(MarketStreamGap, match="snapshot"):
            await anext(subscription)
        with pytest.raises(StopAsyncIteration):
            await anext(subscription)
    assert client._rpc.await_args.args == ({"type": "sub", "path": old.path},)
    await client.close()


@pytest.mark.asyncio
async def test_reconnect_after_disconnect_uses_explicit_refs_and_old_close_cannot_unsubscribe_new():
    client = connected_client()
    old = await client.subscribe_trades(24)
    await client.ws.close()
    client._subscriptions.clear()  # Reader clears the registry on disconnect.
    reconnect_without_network(client)
    new = (await client.reconnect([old]))[old.path]
    calls = client._rpc.await_count
    await old.close()
    assert client._subscriptions[old.path] is new
    assert client._rpc.await_count == calls
    new.queue.put_nowait({"sequence": 99})
    assert (await anext(new)).payload == {"sequence": 99}
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [ConnectionError("ACK failed"), asyncio.CancelledError()])
async def test_reconnect_failed_or_cancelled_batch_closes_all_partial_subscriptions(failure):
    client = connected_client()
    first = await client.subscribe_pairs()
    second = await client.subscribe_tickers()
    reconnect_without_network(client)
    partial = []
    async def rpc(frame):
        if frame["path"] == second.path:
            raise failure
        partial.append(client._subscriptions[frame["path"]])
        return {}
    client._rpc = AsyncMock(side_effect=rpc)
    with pytest.raises(type(failure)):
        await client.reconnect([first, second])
    assert client.ws.closed and not client._subscriptions
    with pytest.raises(MarketStreamGap):
        await anext(partial[0])
    await client.close()


@pytest.mark.asyncio
async def test_reconnect_validation_does_not_close_live_connection():
    client = connected_client()
    other = connected_client()
    foreign = await other.subscribe_pairs()
    for invalid in ([foreign], [object()]):
        with pytest.raises(ValueError):
            await client.reconnect(invalid)
        assert not client.ws.closed
    private = await client._subscribe("/balances", "account_balances")
    with pytest.raises(ValueError):
        await client.reconnect([private])
    assert not client.ws.closed
    await client.close()
    await other.close()


@pytest.mark.asyncio
async def test_reconnect_wakes_waiting_consumer_with_gap_and_failed_connect_is_retryable():
    client = connected_client()
    old = await client.subscribe_pairs()
    waiting = asyncio.create_task(anext(old))
    await asyncio.sleep(0)
    client.connect = AsyncMock(side_effect=ConnectionError("hello failed"))
    with pytest.raises(ConnectionError, match="hello failed"):
        await client.reconnect([old])
    with pytest.raises(MarketStreamGap):
        await asyncio.wait_for(waiting, 0.5)
    assert not client._subscriptions
    reconnect_without_network(client)
    new = (await client.reconnect([old]))[old.path]
    assert new is not old and not new.closed
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,args,path,channel", [
    ("subscribe_tickers", (), "/prices", "tickers"),
    ("subscribe_pairs", (), "/pairs", "pairs"),
    ("subscribe_orderbook", (24,), "/orderbooks/24", "orderbook"),
    ("subscribe_trades", ("024",), "/trades/24", "trades"),
])
async def test_confirmed_subscription_paths_and_public_hello(method,args,path,channel):
    client = connected_client()
    try:
        sub = await getattr(client,method)(*args)
        assert sub.path == path and sub.channel == channel
        client._rpc.assert_awaited_once_with({"type":"sub","path":path})
        assert await client._hello_payload() == {"type":"hello","version":"2","auth":{"headers":{"Authorization":"jwt"}}}
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_orderbook_event_preserves_delta_and_arrival_time_without_fabricating_snapshot():
    client = connected_client()
    sub = await client.subscribe_orderbook(24)
    raw = {"type":"orderbooks.upgrade","data":{"pairId":24,"orderbooks":{"asks":[{"price":"1.1","quantity":"2"}]}}}
    before = datetime.now().astimezone()
    sub.queue.put_nowait(raw)
    await asyncio.sleep(0.01)
    consumed_after = datetime.now().astimezone()
    event = await anext(sub)
    assert isinstance(event,MarketEvent)
    assert event.payload is raw
    assert event.source == "websocket" and event.is_snapshot is False
    arrival = datetime.fromisoformat(event.received_at)
    assert before <= arrival < consumed_after
    await sub.close()
    with pytest.raises(StopAsyncIteration):
        await anext(sub)
    await client.close()


@pytest.mark.asyncio
async def test_shared_subscription_ack_is_not_resent_and_unsubscribe_is_explicit():
    client = connected_client()
    try:
        first = await client.subscribe_pairs()
        assert await client.subscribe_pairs() is first
        assert client._rpc.await_count == 1
        await first.close()
        assert "/pairs" not in client._subscriptions
        assert client._rpc.await_args.args == ({"type":"unsub","path":"/pairs"},)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_full_queue_fails_loudly_instead_of_silently_dropping_market_updates():
    client = connected_client(queue_size=1)
    sub = await client.subscribe_orderbook(24)
    client._reader_task = asyncio.create_task(client._reader())
    try:
        client.ws.publish(sub.path,{"data":{"updateId":1}})
        client.ws.publish(sub.path,{"data":{"updateId":2}})
        await asyncio.wait_for(client.ws.closed_event.wait(),0.5)
        assert sub.queue.qsize() <= 1
        with pytest.raises(ConnectionError):
            await asyncio.wait_for(anext(sub),0.5)
        with pytest.raises(StopAsyncIteration):
            await anext(sub)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_revoke_terminates_old_iterator_and_allows_fresh_subscription():
    client = connected_client()
    old = await client.subscribe_trades(24)
    client._reader_task = asyncio.create_task(client._reader())
    try:
        client.ws.publish(old.path,{},kind="revoke")
        with pytest.raises(ConnectionError):
            await asyncio.wait_for(anext(old),0.5)
        assert old.closed
        replacement = await client.subscribe_trades(24)
        assert replacement is not old
        assert client._rpc.await_count == 2
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_failed_subscription_is_not_left_in_registry():
    client = connected_client()
    client._rpc.side_effect = ConnectionError("synthetic failure")
    with pytest.raises(ConnectionError):
        await client.subscribe_pairs()
    assert not client._subscriptions
    await client.close()


@pytest.mark.asyncio
async def test_unsupported_rpc_and_history_are_not_misrepresented_as_working():
    client = connected_client()
    for call in [client.request("/pairs"),client.subscribe_kline("DEL_USDT")]:
        with pytest.raises(NotImplementedError):
            await call
    assert client._rpc.await_count == 0
    await client.close()


@pytest.mark.asyncio
async def test_authentication_hook_can_be_extended_without_changing_public_default():
    client = BitTeamMarketStreams()
    socket = FakeSocket()
    class FakeSession:
        closed = False
        ws_connect = AsyncMock(return_value=socket)
        async def close(self):
            self.closed = True
    session = FakeSession()
    client._session = session
    hello = {"type":"hello","version":"2","auth":{"headers":{"Authorization":"Bearer synthetic"}}}
    client._hello_payload = AsyncMock(return_value=hello)
    client._rpc = AsyncMock(return_value={})
    try:
        await client.connect()
        client._hello_payload.assert_awaited_once()
        client._rpc.assert_awaited_once_with(hello)
        assert session.ws_connect.await_args.kwargs["protocols"] == ["nes"]
    finally:
        await client.close()


@pytest.mark.parametrize("value", [0,-1,True,"../24","DEL_USDT","２４",None,1.5])
def test_pair_id_rejects_invalid_or_escaping_values(value):
    with pytest.raises(ValueError):
        pair_identity(value)


@pytest.mark.parametrize("value",[0,-1,True,1.5])
def test_market_queue_must_be_bounded(value):
    with pytest.raises(ValueError):
        BitTeamMarketStreams(queue_size=value)
