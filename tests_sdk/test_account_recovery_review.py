"""Account recovery protocol uses real SDK orchestration and RAM-only peers."""
import asyncio
from types import SimpleNamespace

import pytest

from bitteam_sdk import AuthState, SessionAuth
from bitteam_sdk.account_streams import BitTeamAccountStreams
from bitteam_sdk.rest import BitTeamRestAPI


class Socket:
    def __init__(self, stream):
        self.stream = stream
        self.closed = False
        self.frames = []
        self.on_frame = None

    async def send_json(self, frame):
        self.frames.append(frame)
        if self.on_frame:
            await self.on_frame(frame)
        future = self.stream._pending.get(frame['id'])
        if future is not None and not future.done():
            future.set_result({'payload': {}})

    async def receive(self):
        await asyncio.Future()

    async def close(self):
        self.closed = True


def setup(monkeypatch):
    auth = SessionAuth()
    owner = BitTeamRestAPI(auth=auth)
    auth.state, auth._access = AuthState.READY, 'synthetic-access-A'
    stream = BitTeamAccountStreams(auth)
    sockets = []

    def session_factory(*args, **kwargs):
        # SDK constructs a connector before the session. No actual session or
        # socket is opened; the connector is replaced below too.
        session = SimpleNamespace(closed=False)

        async def ws_connect(*args, **kwargs):
            socket = Socket(stream)
            sockets.append(socket)
            return socket

        async def close():
            session.closed = True

        session.ws_connect, session.close = ws_connect, close
        return session

    monkeypatch.setattr('bitteam_sdk.market_streams.aiohttp.ClientSession', session_factory)
    monkeypatch.setattr('bitteam_sdk.market_streams.aiohttp.TCPConnector', lambda **kwargs: None)
    return auth, owner, stream, sockets


@pytest.mark.asyncio
async def test_cancelled_second_private_sub_discards_partial_batch_and_allows_explicit_retry(monkeypatch):
    auth, owner, stream, sockets = setup(monkeypatch)
    try:
        original = [await stream.subscribe_balances(), await stream.subscribe_orders()]
        entered = asyncio.Event()
        original_send = Socket.send_json
        block = True

        async def gated_send(socket, frame):
            if block and len(sockets) >= 2 and frame.get('type') == 'sub' and frame.get('path') == '/orders':
                socket.frames.append(frame)  # Peer accepted the second SUB; ACK is missing.
                entered.set()
                await asyncio.Future()
            await original_send(socket, frame)

        monkeypatch.setattr(Socket, 'send_json', gated_send)
        task = asyncio.create_task(stream.reconnect(original))
        await entered.wait()
        assert set(stream._subscriptions) == {'/balances', '/orders'}
        assert [frame['type'] for frame in sockets[-1].frames] == ['hello', 'sub', 'sub']
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not stream._subscriptions
        assert sockets[-1].closed
        for old in original:
            with pytest.raises(ConnectionError, match='events may be missing'):
                await anext(old)
        assert len(sockets) == 2, 'retired iterators opened an unsolicited connection'
        block = False
        replacements = await stream.reconnect(original)
        assert set(replacements) == {'/balances', '/orders'}
        assert set(stream._subscriptions) == set(replacements)
        assert all(replacements[old.subscription.path].subscription is not old.subscription for old in original)
        assert len(sockets) == 3
    finally:
        await stream.close()
        await owner.close()


@pytest.mark.asyncio
async def test_refresh_between_private_subs_reauthenticates_before_next_sub(monkeypatch):
    auth, owner, stream, sockets = setup(monkeypatch)
    try:
        original = [await stream.subscribe_balances(), await stream.subscribe_orders()]
        original_send = Socket.send_json

        async def refresh_after_first(socket, frame):
            await original_send(socket, frame)
            if len(sockets) == 2 and frame.get('type') == 'sub' and frame.get('path') == '/balances':
                auth._access = 'synthetic-access-refreshed'
                auth._generation += 1

        monkeypatch.setattr(Socket, 'send_json', refresh_after_first)
        replacements = await stream.reconnect(original)
        assert set(replacements) == {'/balances', '/orders'}
        frames = sockets[-1].frames
        assert [frame['type'] for frame in frames] == ['hello', 'sub', 'reauth', 'sub']
        assert frames[0]['auth']['headers']['Authorization'] == 'Bearer synthetic-access-A'
        assert frames[2]['auth']['headers']['Authorization'] == 'Bearer synthetic-access-refreshed'
        assert stream._auth_generation == auth.generation
    finally:
        await stream.close()
        await owner.close()


@pytest.mark.asyncio
async def test_closed_account_iterator_does_not_open_a_replacement_socket(monkeypatch):
    auth, owner, stream, sockets = setup(monkeypatch)
    try:
        old = await stream.subscribe_balances()
        await old.close()
        await stream.close()
        with pytest.raises(StopAsyncIteration):
            await anext(old)
        assert len(sockets) == 1
    finally:
        await stream.close()
        await owner.close()


@pytest.mark.asyncio
async def test_private_reconnect_keeps_cancellation_when_secondary_cleanup_fails(monkeypatch):
    auth, owner, stream, sockets = setup(monkeypatch)
    original_send = Socket.send_json
    entered = asyncio.Event()
    task = None
    try:
        original = [await stream.subscribe_balances(), await stream.subscribe_orders()]

        async def gated(socket, frame):
            if len(sockets) == 2 and frame.get('path') == '/orders':
                entered.set()
                await asyncio.Future()
            await original_send(socket, frame)

        monkeypatch.setattr(Socket, 'send_json', gated)
        task = asyncio.create_task(stream.reconnect(original))
        await entered.wait()
        real_close = stream._session.close

        async def failed_session_close():
            await real_close()
            raise OSError('synthetic secondary cleanup failure')

        stream._session.close = failed_session_close
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not stream._subscriptions
        assert sockets[-1].closed
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        try:
            await stream.close()
        except OSError:
            pass  # Secondary cleanup failure is deliberately injected.
        await owner.close()
