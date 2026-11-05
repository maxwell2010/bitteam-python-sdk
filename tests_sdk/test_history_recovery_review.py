"""History recovery barriers use fake transports, with no HTTP/socket I/O."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk.websocket import BitTeamWebSocket
from bitteam_sdk.market_streams import BitTeamMarketStreams


class Socket:
    def __init__(self):
        self.closed = False

    async def receive(self):
        await asyncio.Future()

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_history_subscribe_does_not_return_ref_closing_behind_lock():
    client = BitTeamWebSocket()
    client.ws = Socket()
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []

    async def send(frame):
        sent.append(frame)
        if frame.get('path') == '/klines/btc_usdt/1m':
            entered.set()
            await release.wait()
        future = client._pending.get(frame['id'])
        if future is not None and not future.done():
            future.set_result({})

    client.ws.send_json = send
    old = await client.subscribe_kline('DEL_USDT')
    blocker = asyncio.create_task(client.subscribe_kline('BTC_USDT'))
    await entered.wait()
    pending = asyncio.create_task(client.subscribe_kline('DEL_USDT'))
    await asyncio.sleep(0)
    closing = asyncio.create_task(old.close())
    await asyncio.sleep(0)
    assert old.closed
    release.set()
    await blocker
    new = await pending
    await closing
    try:
        assert new is not old
        assert not new.closed
        assert client._subscriptions.get(new.path) is new
        assert [frame['type'] for frame in sent] == ['sub', 'sub', 'sub']
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [BitTeamWebSocket, BitTeamMarketStreams])
@pytest.mark.parametrize('cancel', [False, True])
async def test_hello_failure_preserves_primary_error_if_socket_close_fails(kind, cancel):
    client = kind()
    socket = Socket()
    original = asyncio.CancelledError() if cancel else ValueError('synthetic hello failure')

    async def fail_close():
        raise OSError('synthetic cleanup failure')

    socket.close = fail_close
    client._session = SimpleNamespace(closed=False, ws_connect=AsyncMock(return_value=socket), close=AsyncMock())
    client._rpc = AsyncMock(side_effect=original)
    with pytest.raises(type(original)) as raised:
        await client.connect()
    assert raised.value is original
    client._session.close.assert_awaited_once()
    assert client._reader_task is None
    assert client.ws is None


def history_with_fake_reconnect(queue_size=2):
    client = BitTeamWebSocket(queue_size=queue_size)
    sockets = []
    sent = []

    def make_socket():
        socket = Socket()
        sockets.append(socket)

        async def send(frame):
            sent.append(frame)
            future = client._pending.get(frame['id'])
            if future is not None and not future.done():
                future.set_result({})

        socket.send_json = send
        return socket

    client.ws = make_socket()
    async def connect():
        if client.ws is None or client.ws.closed:
            client.ws = make_socket()
    client.connect = connect
    return client, sockets, sent


@pytest.mark.asyncio
async def test_history_reconnect_replaces_requested_paths_and_gaps_all_old_refs():
    from bitteam_sdk import KlineStreamGap
    client, sockets, sent = history_with_fake_reconnect(queue_size=1)
    old = await client.subscribe_kline('BTC_USDT')
    omitted = await client.subscribe_kline('ETH_USDT', '5m')
    old.queue.put_nowait({'t': 1, 'o': '1', 'h': '1', 'l': '1', 'c': '1', 'v': '1'})
    restored = await client.reconnect([old, old])
    assert set(restored) == {old.path}
    new = restored[old.path]
    assert new is not old and not new.closed
    assert new.queue.maxsize == 1 and new.queue.empty()
    assert sockets[0].closed
    for ref in [old, omitted]:
        with pytest.raises(KlineStreamGap):
            await anext(ref)
        with pytest.raises(StopAsyncIteration):
            await anext(ref)
    before = len(sent)
    await old.close()
    assert len(sent) == before
    new.queue.put_nowait({'t': 2, 'o': '1', 'h': '1', 'l': '1', 'c': '1', 'v': '1'})
    assert (await anext(new)).open_time == 2000
    await client.close()


@pytest.mark.asyncio
async def test_history_reconnect_waiting_consumer_gets_gap_before_close_yields():
    from bitteam_sdk import KlineStreamGap
    client, sockets, _ = history_with_fake_reconnect()
    old = await client.subscribe_kline('BTC_USDT')
    waiting = asyncio.create_task(anext(old))
    await asyncio.sleep(0)

    async def close():
        sockets[0].closed = True
        # A consumer must already be awakened before transport shutdown finishes.
        with pytest.raises(KlineStreamGap):
            await asyncio.wait_for(waiting, 0.2)

    sockets[0].close = close
    await client.reconnect([old])
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', [False, True])
async def test_history_failed_reconnect_retires_partial_batch_preserving_primary(cancel):
    from bitteam_sdk import KlineStreamGap
    client, sockets, _ = history_with_fake_reconnect()
    first = await client.subscribe_kline('BTC_USDT')
    second = await client.subscribe_kline('ETH_USDT')
    original = asyncio.CancelledError() if cancel else ValueError('synthetic second ACK failure')
    partial = []

    async def rpc(frame):
        if frame['path'] == second.path:
            raise original
        partial.append(client._subscriptions[frame['path']])
        return {}

    client._rpc = rpc
    with pytest.raises(type(original)) as raised:
        await client.reconnect([first, second])
    assert raised.value is original
    assert sockets[-1].closed
    assert not client._subscriptions
    with pytest.raises(KlineStreamGap):
        await anext(partial[0])
    # An explicit retry can replace references from the failed batch.
    client._rpc = AsyncMock(return_value={})
    new = (await client.reconnect([first]))[first.path]
    assert new is not first and not new.closed
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['foreign', 'object', 'path', 'interval', 'symbol'])
async def test_history_reconnect_validates_before_retiring_active_connection(invalid):
    client, sockets, _ = history_with_fake_reconnect()
    old = await client.subscribe_kline('BTC_USDT')
    if invalid == 'foreign':
        other, _, _ = history_with_fake_reconnect()
        ref = await other.subscribe_kline('BTC_USDT')
    elif invalid == 'object':
        ref = object()
    else:
        ref = old
        setattr(ref, invalid, {'path': '/api/private', 'interval': '2m', 'symbol': 'ETH_USDT'}[invalid])
    with pytest.raises(ValueError):
        await client.reconnect([ref])
    assert not sockets[0].closed
    assert client._subscriptions
    await client.close()
    if invalid == 'foreign':
        await other.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [BitTeamWebSocket, BitTeamMarketStreams])
@pytest.mark.parametrize('cancel', [False, True])
async def test_second_sub_accepted_without_ack_closes_batch_then_explicit_retry(monkeypatch, kind, cancel):
    client = kind(timeout=0.03)
    sockets = []
    accepted = asyncio.Event()
    block = True
    partial = []

    class Peer(Socket):
        def __init__(self):
            super().__init__()
            self.frames = []

        async def send_json(self, frame):
            self.frames.append(frame)
            subs = [item for item in self.frames if item['type'] == 'sub']
            if block and len(sockets) == 2 and len(subs) == 2:
                partial.extend(client._subscriptions.values())
                accepted.set()
                await asyncio.Future()
            future = client._pending.get(frame['id'])
            if future is not None and not future.done():
                future.set_result({})

    def session_factory(*args, **kwargs):
        session = SimpleNamespace(closed=False)
        async def connect(*args, **kwargs):
            socket = Peer()
            sockets.append(socket)
            return socket
        async def close():
            session.closed = True
        session.ws_connect, session.close = connect, close
        return session

    monkeypatch.setattr('bitteam_sdk.websocket.aiohttp.ClientSession', session_factory)
    monkeypatch.setattr('bitteam_sdk.websocket.aiohttp.TCPConnector', lambda **kwargs: None)
    if kind is BitTeamWebSocket:
        old = [await client.subscribe_kline('BTC_USDT'), await client.subscribe_kline('ETH_USDT')]
    else:
        old = [await client.subscribe_pairs(), await client.subscribe_tickers()]
    task = asyncio.create_task(client.reconnect(old))
    await accepted.wait()
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else asyncio.TimeoutError):
        await task
    assert len(sockets) == 2 and sockets[-1].closed
    assert not client._subscriptions
    assert [frame['type'] for frame in sockets[-1].frames] == ['hello', 'sub', 'sub']
    for ref in old + partial[:1]:
        with pytest.raises(ConnectionError, match='may be missing'):
            await anext(ref)
    block = False
    replacements = await client.reconnect(old)
    assert set(replacements) == {ref.path for ref in old}
    assert len(sockets) == 3
    assert [frame['type'] for frame in sockets[-1].frames] == ['hello', 'sub', 'sub']
    await client.close()
