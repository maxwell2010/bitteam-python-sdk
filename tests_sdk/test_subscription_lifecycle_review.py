"""Deterministic nes lifecycle races, using an in-memory server only."""
import asyncio

import pytest

from bitteam_sdk.websocket import BitTeamWebSocket
from bitteam_sdk.market_streams import BitTeamMarketStreams


class ServerSocket:
    def __init__(self, client):
        self.client = client
        self.closed = False
        self.paths = set()
        self.block = None
        self.accepted = asyncio.Event()
        self.release = asyncio.Event()

    async def send_json(self, frame):
        operation, path = frame['type'], frame.get('path')
        if operation == 'sub':
            self.paths.add(path)
        if operation == self.block:
            self.accepted.set()
            await self.release.wait()
        if operation == 'unsub':
            self.paths.discard(path)
        future = self.client._pending.get(frame['id'])
        if future is not None and not future.done():
            future.set_result({})

    async def close(self):
        self.closed = True
        self.paths.clear()


def setup(kind):
    client = kind(timeout=0.03)
    socket = ServerSocket(client)
    client.ws = socket
    return client, socket


async def subscribe(client):
    if isinstance(client, BitTeamMarketStreams):
        return await client.subscribe_pairs()
    return await client.subscribe_kline('BTC_USDT')


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [BitTeamWebSocket, BitTeamMarketStreams])
async def test_unsubscribe_serializes_new_same_path_subscribe(kind):
    client, socket = setup(kind)
    old = await subscribe(client)
    socket.block = 'unsub'
    closing = asyncio.create_task(old.close())
    await socket.accepted.wait()
    replacement = asyncio.create_task(subscribe(client))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    socket.release.set()
    try:
        await closing
        new = await replacement
        assert client._subscriptions[new.path] is new
        assert new.path in socket.paths
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [BitTeamWebSocket, BitTeamMarketStreams])
@pytest.mark.parametrize('failure', ['cancel', 'timeout'])
async def test_accepted_sub_without_ack_retires_connection(kind, failure):
    client, socket = setup(kind)
    existing = await subscribe(client)
    socket.block = 'sub'
    task = asyncio.create_task(client.subscribe_tickers() if isinstance(client, BitTeamMarketStreams)
                               else client.subscribe_kline('ETH_USDT'))
    await socket.accepted.wait()
    if failure == 'cancel':
        task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError if failure == 'cancel' else asyncio.TimeoutError):
            await task
        assert socket.closed, 'accepted subscription remained active without a local owner'
        assert not socket.paths
        assert not client._subscriptions
        with pytest.raises(ConnectionError):
            await anext(existing)
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [BitTeamWebSocket, BitTeamMarketStreams])
@pytest.mark.parametrize('failure', ['cancel', 'timeout'])
async def test_unacknowledged_unsubscribe_invalidates_other_paths(kind, failure):
    client, socket = setup(kind)
    old = await subscribe(client)
    other = await (client.subscribe_tickers() if isinstance(client, BitTeamMarketStreams)
                   else client.subscribe_kline('ETH_USDT'))
    socket.block = 'unsub'
    task = asyncio.create_task(old.close())
    await socket.accepted.wait()
    if failure == 'cancel':
        task.cancel()
    with pytest.raises(asyncio.CancelledError if failure == 'cancel' else asyncio.TimeoutError):
        await task
    assert socket.closed
    assert not client._subscriptions
    with pytest.raises(ConnectionError):
        await anext(other)
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('close_failure', [False, True])
async def test_cleanup_survives_second_cancellation_and_close_error(close_failure):
    client, socket = setup(BitTeamMarketStreams)
    old = await subscribe(client)
    socket.block = 'sub'
    entered, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def close():
        entered.set()
        await release.wait()
        finished.set()
        if close_failure:
            raise RuntimeError('synthetic close failure')
        socket.closed = True
        socket.paths.clear()

    socket.close = close
    task = asyncio.create_task(client.subscribe_tickers())
    await socket.accepted.wait()
    task.cancel()
    await entered.wait()
    with pytest.raises(ConnectionError, match='retiring'):
        await client._rpc({'type': 'request'})
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(ConnectionError):
        await anext(old)
    release.set()
    await finished.wait()
    # Let the protected cleanup finalize socket retirement after close raised.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert client.ws is None or client.ws.closed
    assert not client._subscriptions


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [BitTeamWebSocket, BitTeamMarketStreams])
async def test_old_close_waiting_for_lock_does_not_remove_replacement(kind):
    client, socket = setup(kind)
    old = await subscribe(client)
    await client._subscription_lock.acquire()
    closing = asyncio.create_task(old.close())
    await asyncio.sleep(0)
    # A reconnect/subscription owner holds the lock while replacing the ref.
    client._subscriptions.pop(old.path)
    if isinstance(client, BitTeamMarketStreams):
        new = await client._subscribe_unlocked(old.path, old.channel)
    else:
        new = await client._subscribe_kline('BTC_USDT', '1m')
    client._subscription_lock.release()
    await closing
    try:
        assert client._subscriptions.get(old.path) is new
        assert new.path in socket.paths
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [BitTeamWebSocket, BitTeamMarketStreams])
@pytest.mark.parametrize('failure', [OSError('synthetic close failure'), asyncio.CancelledError()])
async def test_socket_close_failure_still_closes_session_and_reader(kind, failure):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    client, socket = setup(kind)
    old = await subscribe(client)
    client._session = SimpleNamespace(close=AsyncMock(), closed=False)
    reader_finished = asyncio.Event()

    async def reader():
        try:
            await asyncio.Future()
        finally:
            reader_finished.set()

    client._reader_task = asyncio.create_task(reader())
    await asyncio.sleep(0)

    async def failing_close():
        raise failure

    socket.close = failing_close
    with pytest.raises(type(failure)):
        await client.close()
    client._session.close.assert_awaited_once()
    assert reader_finished.is_set()
    assert not client._subscriptions
    with pytest.raises(StopAsyncIteration):
        await anext(old)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [BitTeamWebSocket, BitTeamMarketStreams])
@pytest.mark.parametrize('stage', ['connect', 'send', 'close'])
@pytest.mark.parametrize('timeout', [False, True])
async def test_typed_transport_errors_never_expose_server_diagnostics(kind, stage, timeout):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import aiohttp

    sentinel = 'SYNTHETIC-OTP-cookie-password'
    error = asyncio.TimeoutError(sentinel) if timeout else aiohttp.ClientConnectionError(sentinel)
    client, socket = setup(kind)

    async def fail(*args, **kwargs):
        raise error

    if stage == 'connect':
        client.ws = None
        client._session = SimpleNamespace(closed=False, ws_connect=fail, close=AsyncMock())
        operation = client.connect()
    elif stage == 'send':
        socket.send_json = fail
        operation = client._rpc({'type': 'request'})
    else:
        socket.close = fail
        operation = client.close()
    with pytest.raises(asyncio.TimeoutError if timeout else ConnectionError) as raised:
        await operation
    assert sentinel not in str(raised.value)
    assert sentinel not in repr(raised.value)
    assert raised.value.__suppress_context__
    assert raised.value.__cause__ is None
    import traceback
    formatted = ''.join(traceback.format_exception(type(raised.value), raised.value, raised.value.__traceback__))
    assert sentinel not in formatted
    if stage == 'connect':
        client._session.close.assert_awaited_once()
