"""Local L2 reconciliation and Decimal isolation; synthetic data/fake peers only."""
import asyncio
from dataclasses import FrozenInstanceError
from decimal import (Decimal, localcontext, Inexact, Rounded, Subnormal, Clamped,
                     ROUND_DOWN)
from types import SimpleNamespace

import pytest

from bitteam_sdk import BitTeamClient
from bitteam_sdk.orderbook import OrderBookSnapshot, reconcile_book


@pytest.mark.parametrize('method', ['parse', 'spread', 'mid_price', 'depth', 'imbalance'])
@pytest.mark.parametrize('exponent', ['10', '-10'])
def test_book_arithmetic_isolated_from_decimal_exponents_rounding_and_traps(method, exponent):
    payload = {'bids': [[f'1e{exponent}', f'1e{exponent}'], [f'1e{exponent}', f'1e{exponent}']],
               'asks': [[f'2e{exponent}', f'1e{exponent}']]}
    snapshot = OrderBookSnapshot.from_payload(payload, 'BTC_USDT')

    def result():
        if method == 'parse':
            return OrderBookSnapshot.from_payload(payload, 'BTC_USDT').as_dict() | {'received_at_ms': 0}
        if method in ('spread', 'mid_price'):
            return getattr(snapshot, method)
        return getattr(snapshot, method)('bids') if method == 'depth' else snapshot.imbalance()

    expected = result()
    with localcontext() as context:
        context.prec, context.Emax, context.Emin = 2, 9, -9
        context.rounding = ROUND_DOWN
        for trap in (Inexact, Rounded, Subnormal, Clamped):
            context.traps[trap] = True
        before = context.copy()
        assert result() == expected
        assert context.prec == before.prec and context.Emax == before.Emax and context.Emin == before.Emin
        assert context.rounding == before.rounding and context.traps == before.traps
        assert context.flags == before.flags


class Peer:
    def __init__(self, market):
        self.market, self.closed, self.frames = market, False, []
        self.before_ack = None

    async def send_json(self, frame):
        self.frames.append(frame)
        if self.before_ack:
            await self.before_ack(frame)
        future = self.market._pending.get(frame['id'])
        if future is not None and not future.done():
            future.set_result({})

    async def receive(self):
        await asyncio.Future()

    async def close(self):
        self.closed = True


def setup(monkeypatch):
    client = BitTeamClient()
    market, peers, calls = client.market, [], []

    def factory(*args, **kwargs):
        session = SimpleNamespace(closed=False)
        async def connect(*args, **kwargs):
            peer = Peer(market)
            peers.append(peer)
            return peer
        async def close():
            session.closed = True
        session.ws_connect, session.close = connect, close
        return session

    monkeypatch.setattr('bitteam_sdk.market_streams.aiohttp.ClientSession', factory)
    monkeypatch.setattr('bitteam_sdk.market_streams.aiohttp.TCPConnector', lambda **kwargs: None)

    async def send(method, url, **kwargs):
        calls.append((method, url))
        if url.endswith('/pairs'):
            return {'result': {'pairs': [{'name': 'BTC_USDT', 'id': 24}]}}
        assert url.endswith('/orderbooks/btc_usdt')
        return {'result': {'bids': [['2', '3']], 'asks': [['4', '1']]}}

    client.rest._send = send
    return client, peers, calls


@pytest.mark.asyncio
async def test_reconciliation_returns_fresh_snapshot_and_raw_ref_without_applying_buffer(monkeypatch):
    client, peers, calls = setup(monkeypatch)
    try:
        old = await client.subscribe_orderbook('BTC_USDT')
        omitted = await client.market.subscribe_tickers()
        send = client.rest._send
        raw = {'bids': [['999', '10']], 'firstUpdateId': 1, 'lastUpdateId': 999}

        async def publish_during_snapshot(method, url, **kwargs):
            if '/orderbooks/' in url:
                client.market._subscriptions[old.path].queue.put_nowait(raw)
            return await send(method, url, **kwargs)

        client.rest._send = publish_during_snapshot
        result = await client.reconcile_book('BTC/USDT', old)
        assert result.snapshot.best_bid == Decimal(2)
        assert result.subscription is not old
        assert result.subscription.path == '/orderbooks/24'
        assert not result.continuity_guaranteed and not result.events_applied
        with pytest.raises(FrozenInstanceError):
            result.events_applied = True
        assert (await anext(result.subscription)).payload is raw
        for ref in (old, omitted):
            with pytest.raises(ConnectionError, match='events may be missing'):
                await anext(ref)
        assert peers[0].closed and len(peers) == 2
        assert [frame['type'] for frame in peers[-1].frames] == ['hello', 'sub']
        assert [method for method, _ in calls] == ['GET', 'GET']
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('problem', ['timeout', 'malformed', 'wrong_symbol'])
async def test_snapshot_failure_closes_fresh_ref_preserving_old_gap(monkeypatch, problem):
    client, peers, calls = setup(monkeypatch)
    try:
        old = await client.subscribe_orderbook('BTC_USDT')
        async def fail(*args, **kwargs):
            assert len(peers) == 2
            if problem == 'timeout':
                raise asyncio.TimeoutError('synthetic timeout')
            if problem == 'malformed':
                return {'result': {}}
            return {'result': {'symbol': 'ETH_USDT', 'bids': [], 'asks': []}}
        client.rest._send = fail
        with pytest.raises(asyncio.TimeoutError if problem == 'timeout' else ValueError):
            await reconcile_book(client, 'BTC_USDT', old)
        assert not client.market._subscriptions
        assert [f['type'] for f in peers[-1].frames] == ['hello', 'sub', 'unsub']
        with pytest.raises(ConnectionError, match='events may be missing'):
            await anext(old)
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['foreign', 'channel', 'pair'])
async def test_invalid_reference_rejected_before_reconnect(monkeypatch, invalid):
    client, peers, calls = setup(monkeypatch)
    other = None
    try:
        old = await client.subscribe_orderbook('BTC_USDT')
        if invalid == 'foreign':
            other = BitTeamClient()
            old.client = other.market
        elif invalid == 'channel':
            old.channel = 'trades'
        else:
            old.path = '/orderbooks/999'
        with pytest.raises(ValueError):
            await reconcile_book(client, 'BTC_USDT', old)
        assert len(peers) == 1 and not peers[0].closed
    finally:
        await client.close()
        if other:
            await other.close()


@pytest.mark.asyncio
async def test_cancelled_snapshot_waits_for_one_cleanup_even_after_second_cancel(monkeypatch):
    client, peers, calls = setup(monkeypatch)
    entered, cleanup_entered, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    task = None
    try:
        old = await client.subscribe_orderbook('BTC_USDT')
        async def fail(*args, **kwargs):
            async def before_ack(frame):
                if frame['type'] == 'unsub':
                    cleanup_entered.set()
                    await release.wait()
            peers[-1].before_ack = before_ack
            entered.set()
            await asyncio.Future()
        client.rest._send = fail
        task = asyncio.create_task(reconcile_book(client, 'BTC_USDT', old))
        await entered.wait()
        task.cancel()
        await cleanup_entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not client.market._subscriptions
        assert [frame['type'] for frame in peers[-1].frames].count('unsub') == 1
    finally:
        release.set()
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await client.close()
