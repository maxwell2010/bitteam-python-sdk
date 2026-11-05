"""History recovery cannot outlive its high-level owner; fake peers only."""
import asyncio
from types import SimpleNamespace

import pytest

from bitteam_sdk import BitTeamClient


def setup(monkeypatch, *, adopted=False):
    owner = BitTeamClient()
    if adopted:
        from bitteam_sdk.websocket import BitTeamWebSocket
        source = owner._history = BitTeamWebSocket()
    else:
        source = owner.history
    peers = []
    class Peer:
        closed = False
        def __init__(self):
            self.frames = []
        async def receive(self):
            await asyncio.Future()
        async def close(self):
            self.closed = True
        async def send_json(self, frame):
            self.frames.append(frame)
            response = {'payload': {'result': {'data': []}}} if frame['type'] == 'request' else {}
            future = source._pending.get(frame['id'])
            if future is not None and not future.done():
                future.set_result(response)
    def factory(*args, **kwargs):
        session = SimpleNamespace(closed=False)
        async def connect(*args, **kwargs):
            peer = Peer()
            peers.append(peer)
            return peer
        async def close():
            session.closed = True
        session.ws_connect, session.close = connect, close
        return session
    monkeypatch.setattr('bitteam_sdk.websocket.aiohttp.ClientSession', factory)
    monkeypatch.setattr('bitteam_sdk.websocket.aiohttp.TCPConnector', lambda **kwargs: None)
    return owner, source, peers


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['reconnect', 'fetch'])
async def test_owner_close_during_recovery_cannot_resurrect_or_return_success(monkeypatch, stage):
    owner, source, peers = setup(monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    original = source.reconnect if stage == 'reconnect' else source.get_klines
    async def gated(*args, **kwargs):
        result = await original(*args, **kwargs)
        entered.set()
        await release.wait()
        return result
    setattr(source, 'reconnect' if stage == 'reconnect' else 'get_klines', gated)
    old = await owner.subscribe_kline('BTC_USDT')
    task = asyncio.create_task(owner.recover_klines(old, start=0, end=120, chunk_bars=1))
    try:
        await entered.wait()
        await owner.close()
        release.set()
        with pytest.raises(RuntimeError, match='closed'):
            await task
        assert len(peers) == 2
        assert sum(frame['type'] == 'request' for peer in peers for frame in peer.frames) == (stage == 'fetch')
        assert all(peer.closed for peer in peers)
        assert not source._subscriptions
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await source.close()
        await owner.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['reconnect', 'fetch'])
async def test_late_cancellation_suppressed_by_io_cannot_become_recovery_success(monkeypatch, stage):
    owner, source, peers = setup(monkeypatch)
    entered, suppressed, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = source.reconnect if stage == 'reconnect' else source.get_klines
    async def gated(*args, **kwargs):
        result = await original(*args, **kwargs)
        entered.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            suppressed.set()
            await release.wait()
        return result
    setattr(source, 'reconnect' if stage == 'reconnect' else 'get_klines', gated)
    old = await owner.subscribe_kline('BTC_USDT')
    task = asyncio.create_task(owner.recover_klines(old, start=0, end=120, chunk_bars=1))
    try:
        await entered.wait()
        task.cancel()
        await suppressed.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), 'repeated cancellation abandoned late I/O drain'
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not source._subscriptions
        assert len(peers) == 2
        assert sum(frame['type'] == 'request' for peer in peers for frame in peer.frames) == (stage == 'fetch')
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await owner.close()


@pytest.mark.asyncio
async def test_closed_owner_blocks_late_reconnect_before_it_opens_a_socket(monkeypatch):
    owner, source, peers = setup(monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    original = source.reconnect
    async def gated(refs):
        entered.set()
        await release.wait()
        return await original(refs)
    source.reconnect = gated
    old = await owner.subscribe_kline('BTC_USDT')
    task = asyncio.create_task(owner.recover_klines(old, start=0, end=60))
    try:
        await entered.wait()
        await owner.close()
        release.set()
        with pytest.raises(RuntimeError, match='closed'):
            await task
        assert len(peers) == 1 and peers[0].closed
        assert not source._subscriptions
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await source.close()
        await owner.close()


@pytest.mark.asyncio
async def test_late_adopted_source_reopen_is_fully_closed_after_owner_close(monkeypatch):
    # Legacy/adopted resources have no bound owner hook. The facade's separate
    # owner guard must still reject the result and close the entire late source.
    owner, source, peers = setup(monkeypatch, adopted=True)
    entered, release = asyncio.Event(), asyncio.Event()
    original = source.get_klines
    async def gated(*args, **kwargs):
        result = await original(*args, **kwargs)
        entered.set()
        await release.wait()
        await source.connect()
        return result
    source.get_klines = gated
    old = await owner.subscribe_kline('BTC_USDT')
    task = asyncio.create_task(owner.recover_klines(old, start=0, end=60))
    try:
        await entered.wait()
        await owner.close()
        release.set()
        with pytest.raises(RuntimeError, match='closed'):
            await task
        assert len(peers) == 3 and all(peer.closed for peer in peers)
        assert not source._subscriptions
        assert source._session.closed
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await source.close()
        await owner.close()
