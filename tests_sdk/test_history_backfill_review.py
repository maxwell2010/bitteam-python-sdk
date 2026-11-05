"""Bounded recovery and owned-history cleanup, entirely synthetic."""
import asyncio

import pytest

from bitteam_sdk.history import fetch_klines, HistoryProtocolError


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['protocol', 'provider', 'cancel'])
async def test_owned_history_cleanup_does_not_mask_primary_failure(monkeypatch, mode):
    entered = asyncio.Event()
    closed = []
    original = ValueError('synthetic provider failure')

    class Provider:
        async def get_klines(self, *args, **kwargs):
            if mode == 'protocol':
                return None
            if mode == 'provider':
                raise original
            entered.set()
            await asyncio.Future()

        async def close(self):
            closed.append(True)
            raise ConnectionError('synthetic cleanup failure')

    monkeypatch.setattr('bitteam_sdk.history.BitTeamWebSocket', Provider)
    task = asyncio.create_task(fetch_klines('BTC_USDT', start=0, end=60))
    if mode == 'cancel':
        await entered.wait()
        task.cancel()
    expected = {'protocol': HistoryProtocolError, 'provider': ValueError, 'cancel': asyncio.CancelledError}[mode]
    with pytest.raises(expected):
        await task
    assert closed == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize('early', [False, True])
async def test_owned_history_standalone_cleanup_failure_is_not_success(monkeypatch, early):
    from bitteam_sdk.history import iter_klines
    from bitteam_sdk.models import Kline

    class Provider:
        async def get_klines(self, *args, **kwargs):
            return [Kline('BTC_USDT', '1m', 0, '1', '1', '1', '1', '1')]

        async def close(self):
            raise ConnectionError('synthetic standalone cleanup failure')

    monkeypatch.setattr('bitteam_sdk.history.BitTeamWebSocket', Provider)
    if early:
        stream = iter_klines('BTC_USDT', start=0, end=60)
        await anext(stream)
        with pytest.raises(ConnectionError, match='standalone cleanup'):
            await stream.aclose()
    else:
        with pytest.raises(ConnectionError, match='standalone cleanup'):
            await fetch_klines('BTC_USDT', start=0, end=60)


def setup_recovery(monkeypatch, *, rows=None, blocked=False):
    from types import SimpleNamespace
    from bitteam_sdk.websocket import BitTeamWebSocket

    client = BitTeamWebSocket(timeout=1)
    sockets, frames = [], []
    entered = asyncio.Event()
    history_rows = [] if rows is None else rows

    class Peer:
        closed = False

        async def receive(self):
            await asyncio.Future()

        async def close(self):
            self.closed = True

        async def send_json(self, frame):
            frames.append(frame)
            response = {}
            if frame['type'] == 'request':
                entered.set()
                if blocked:
                    await asyncio.Future()
                # Deliberately keep a live overlap separate from history.
                for sub in client._subscriptions.values():
                    sub.queue.put_nowait({'t': 60, 'o': '1', 'h': '1', 'l': '1', 'c': '2', 'v': '1'})
                response = {'payload': {'result': {'data': history_rows}}}
            future = client._pending.get(frame['id'])
            if future is not None and not future.done():
                future.set_result(response)

    def session_factory(*args, **kwargs):
        session = SimpleNamespace(closed=False)
        async def connect(*args, **kwargs):
            peer = Peer()
            sockets.append(peer)
            return peer
        async def close():
            session.closed = True
        session.ws_connect, session.close = connect, close
        return session

    monkeypatch.setattr('bitteam_sdk.websocket.aiohttp.ClientSession', session_factory)
    monkeypatch.setattr('bitteam_sdk.websocket.aiohttp.TCPConnector', lambda **kwargs: None)
    return client, sockets, frames, entered


@pytest.mark.asyncio
@pytest.mark.parametrize('empty', [False, True])
async def test_recovery_returns_separate_half_open_history_and_live_iterator(monkeypatch, empty):
    from dataclasses import FrozenInstanceError
    from bitteam_sdk.history import recover_klines, KlineRecovery
    from bitteam_sdk.websocket import KlineStreamGap

    rows = [] if empty else [dict(t=t, o='1', h='1', l='1', c='1', v='1') for t in [0, 60, 120]]
    from bitteam_sdk import BitTeamClient
    client, sockets, frames, _ = setup_recovery(monkeypatch, rows=rows)
    owner = BitTeamClient()
    owner._history = client
    try:
        old = await client.subscribe_kline('BTC_USDT')
        result = await owner.recover_klines(old, start=0, end=120)
        assert isinstance(result, KlineRecovery)
        assert (result.start, result.end) == (0, 120)
        assert [row.open_time for row in result.candles] == ([] if empty else [0, 60000])
        assert result.subscription is not old
        assert not result.subscription.closed
        assert sockets[0].closed and not sockets[1].closed
        assert [frame['type'] for frame in frames] == ['hello', 'sub', 'hello', 'sub', 'request']
        assert frames[-1]['path'].endswith('?from=0&to=120')
        # The overlapping live candle remains separate, including its new close.
        live = await anext(result.subscription)
        assert (live.open_time, live.close) == (60000, '2')
        with pytest.raises(KlineStreamGap):
            await anext(old)
        with pytest.raises(FrozenInstanceError):
            result.start = 1
        assert not hasattr(result, 'complete')
    finally:
        await owner.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('kwargs', [
    {'start': 0, 'end': 0}, {'start': True, 'end': 60},
    {'start': 0, 'end': 120, 'chunk_bars': 0},
    {'start': 0, 'end': 120, 'limit': False},
    {'start': 0, 'end': 120, 'chunk_bars': 1, 'max_requests': 1},
])
async def test_recovery_validates_all_bounds_before_retiring_old_ref(monkeypatch, kwargs):
    from bitteam_sdk.history import recover_klines, HistoryLimitError
    client, sockets, frames, _ = setup_recovery(monkeypatch)
    try:
        old = await client.subscribe_kline('BTC_USDT')
        before = len(frames)
        with pytest.raises((ValueError, HistoryLimitError)):
            await recover_klines(old, **kwargs)
        assert len(frames) == before and len(sockets) == 1
        assert not sockets[0].closed
        assert client._subscriptions[old.path] is old
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cancelled_backfill_closes_replacement_without_closing_caller_transport(monkeypatch):
    from bitteam_sdk.history import recover_klines
    client, sockets, frames, entered = setup_recovery(monkeypatch, blocked=True)
    try:
        old = await client.subscribe_kline('BTC_USDT')
        task = asyncio.create_task(recover_klines(old, start=0, end=120))
        await entered.wait()
        replacement = client._subscriptions[old.path]
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert replacement.closed
        assert not client._subscriptions
        assert not sockets[-1].closed
        assert frames[-1]['type'] == 'unsub'
        assert len([frame for frame in frames if frame['type'] == 'request']) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_backfill_protocol_error_survives_replacement_close_failure(monkeypatch):
    from bitteam_sdk.history import recover_klines
    from bitteam_sdk.auth import BitTeamAPIError
    client, sockets, _, _ = setup_recovery(monkeypatch, rows=[{'t': 0}])
    old = await client.subscribe_kline('BTC_USDT')
    original_reconnect = client.reconnect

    async def reconnect(refs):
        replacements = await original_reconnect(refs)
        replacement = replacements[old.path]
        original_close = replacement.close
        async def failed_close():
            await original_close()
            raise OSError('synthetic replacement close failure')
        replacement.close = failed_close
        return replacements

    client.reconnect = reconnect
    try:
        with pytest.raises(BitTeamAPIError):
            await recover_klines(old, start=0, end=120)
        assert not client._subscriptions
        assert not sockets[-1].closed
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_client_recovery_rejects_foreign_ref_without_creating_history(monkeypatch):
    from bitteam_sdk import BitTeamClient
    client, sockets, frames, _ = setup_recovery(monkeypatch)
    owner = BitTeamClient()
    try:
        old = await client.subscribe_kline('BTC_USDT')
        before = len(frames)
        with pytest.raises(ValueError, match='belonging to this client'):
            await owner.recover_klines(old, start=0, end=60)
        assert owner._history is None
        assert len(frames) == before and len(sockets) == 1
        assert not sockets[0].closed
        assert client._subscriptions[old.path] is old
    finally:
        await owner.close()
        await client.close()


@pytest.mark.asyncio
async def test_repeated_cancel_waits_for_one_replacement_cleanup_behind_lock(monkeypatch):
    from bitteam_sdk.history import recover_klines
    client, _, frames, entered = setup_recovery(monkeypatch, blocked=True)
    task = None
    try:
        old = await client.subscribe_kline('BTC_USDT')
        task = asyncio.create_task(recover_klines(old, start=0, end=120))
        await entered.wait()
        replacement = client._subscriptions[old.path]
        cleanup_entered = asyncio.Event()
        cleanup_calls = []
        original_close = replacement.close
        async def close():
            cleanup_calls.append(True)
            cleanup_entered.set()
            await original_close()
        replacement.close = close
        await client._subscription_lock.acquire()
        task.cancel()
        await cleanup_entered.wait()
        assert replacement.closed
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), 'second cancellation abandoned replacement cleanup'
        client._subscription_lock.release()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not client._subscriptions
        assert [frame['type'] for frame in frames].count('unsub') == 1
        assert cleanup_calls == [True]
    finally:
        if client._subscription_lock.locked():
            client._subscription_lock.release()
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await client.close()
