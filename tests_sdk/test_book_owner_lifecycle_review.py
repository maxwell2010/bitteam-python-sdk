"""L2 composite owner/cancellation boundaries, fake peers and synthetic HTTP only."""
import asyncio

import pytest

from bitteam_sdk.orderbook import reconcile_book
from test_book_reconciliation_review import setup, Peer


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['pair', 'reconnect', 'snapshot'])
@pytest.mark.parametrize('boundary', ['close', 'cancel'])
async def test_late_composite_io_cannot_return_after_owner_close_or_caller_cancel(monkeypatch, stage, boundary):
    client, peers, calls = setup(monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    task = None
    try:
        old = await client.subscribe_orderbook('BTC_USDT')
        original_send, original_reconnect = client.rest._send, client.market.reconnect

        async def wait_ignoring_cancel():
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()  # Deliberately hostile compatible provider.

        if stage == 'reconnect':
            async def late_reconnect(refs):
                result = await original_reconnect(refs)
                await wait_ignoring_cancel()
                return result
            monkeypatch.setattr(client.market, 'reconnect', late_reconnect)
        else:
            if stage == 'pair':
                client.rest._pairs = None
            async def late_send(method, url, **kwargs):
                if (stage == 'pair' and url.endswith('/pairs')) or (stage == 'snapshot' and '/orderbooks/' in url):
                    await wait_ignoring_cancel()
                return await original_send(method, url, **kwargs)
            monkeypatch.setattr(client.rest, '_send', late_send)

        task = asyncio.create_task(reconcile_book(client, 'BTC_USDT', old))
        await entered.wait()
        if boundary == 'close':
            await client.close()
        else:
            task.cancel()
            await asyncio.sleep(0)
        release.set()
        with pytest.raises(RuntimeError if boundary == 'close' else asyncio.CancelledError):
            await task
        if boundary == 'close':
            assert all(peer.closed for peer in peers)
            assert client._market._session is None or client._market._session.closed
        elif stage != 'pair':
            assert not client.market._subscriptions
        assert len([url for _, url in calls if '/orderbooks/' in url]) <= 1
    finally:
        release.set()
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_stock_reconnect_hello_racing_owner_close_does_not_resurrect_market(monkeypatch):
    client, peers, calls = setup(monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    task = closing = None
    try:
        old = await client.subscribe_orderbook('BTC_USDT')
        original_send = Peer.send_json

        async def gated_hello(peer, frame):
            if len(peers) == 2 and frame['type'] == 'hello':
                entered.set()
                await release.wait()
            await original_send(peer, frame)

        monkeypatch.setattr(Peer, 'send_json', gated_hello)
        task = asyncio.create_task(client.reconcile_book('BTC_USDT', old))
        await entered.wait()
        closing = asyncio.create_task(client.close())
        while not client.rest._closed:
            await asyncio.sleep(0)
        release.set()
        await closing
        with pytest.raises(RuntimeError, match='closed'):
            await task
        assert all(peer.closed for peer in peers)
        assert client._market._session.closed
        assert not any('/orderbooks/' in url for _, url in calls)
    finally:
        release.set()
        for pending in (task, closing):
            if pending:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        # Explicitly drain the captured resource even if this test detects a
        # resurrected socket after BitTeamClient.close() already completed.
        await client._market.close()
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('symbol', ['', 'BTC', '../BTC_USDT', 'BTC_USDT?x=1'])
async def test_bad_symbol_rejected_before_pair_io_or_stream_replacement(monkeypatch, symbol):
    client, peers, calls = setup(monkeypatch)
    try:
        old = await client.subscribe_orderbook('BTC_USDT')
        before = list(calls)
        with pytest.raises(ValueError):
            await reconcile_book(client, symbol, old)
        assert calls == before
        assert len(peers) == 1 and not peers[0].closed
    finally:
        await client.close()
