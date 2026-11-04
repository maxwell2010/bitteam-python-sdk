"""Independent L2 snapshot/recorder regressions; synthetic books and local SQLite."""
import asyncio
from decimal import Decimal, localcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bitteam_sdk.orderbook import OrderBookSnapshot, MarketDataRecorder


def book(timestamp=1000):
    return OrderBookSnapshot.from_payload({'bids': [['2','3'],['1','4']],
                                          'asks': [['3','1'],['4','2']]},
                                         'DEL/USDT', received_at_ms=timestamp)


def test_snapshot_normalizes_aggregates_orders_and_preserves_decimal_values():
    snapshot=OrderBookSnapshot.from_payload({'bids': [['1.1','0.1'],['1.2','0.2'],['1.1','0.2'],['1.3','0']],
                                               'asks': [['1.5','2'],['1.4','3']]},
                                              'del_usdt',received_at_ms=0)
    assert snapshot.symbol=='DEL_USDT'
    assert [(r.price,r.amount) for r in snapshot.bids]==[(Decimal('1.2'),Decimal('0.2')),(Decimal('1.1'),Decimal('0.3'))]
    assert [r.price for r in snapshot.asks]==[Decimal('1.4'),Decimal('1.5')]
    assert snapshot.received_at_ms==0
    assert snapshot.as_dict()['bids']==[['1.2','0.2'],['1.1','0.3']]


def test_exact_depth_and_best_prices():
    snapshot=book()
    assert snapshot.best_bid==2 and snapshot.best_ask==3
    assert snapshot.spread==1 and snapshot.mid_price==Decimal('2.5')
    levels=snapshot.depth('bids')
    assert levels[-1]['cumulative_base']==7
    assert levels[-1]['cumulative_quote']==10
    assert len(snapshot.depth('asks',levels=1))==1
    assert snapshot.imbalance(levels=1)==Decimal('0.5')
    empty=OrderBookSnapshot.from_payload({'bids':[],'asks':[]},'DEL_USDT')
    assert empty.spread is None and empty.mid_price is None and empty.imbalance() is None


def test_exact_depth_does_not_depend_on_callers_decimal_precision():
    with localcontext() as context:
        context.prec=16
        snapshot=OrderBookSnapshot.from_payload({
            'bids': [['12345678901234567890.123456789012345678','0.000000000000000001']],
            'asks': []},'DEL_USDT')
        assert snapshot.depth('bids')[0]['cumulative_quote']==Decimal('12.345678901234567890123456789012345678')
        combined=OrderBookSnapshot.from_payload({'bids': [['1','1.000000000000000000000000000001'],
                                                          ['1','0.000000000000000000000000000001']],
                                                'asks':[]},'DEL_USDT')
        assert combined.bids[0].amount==Decimal('1.000000000000000000000000000002')


def test_imbalance_does_not_overflow_or_round_inputs_with_external_decimal_context():
    snapshot = OrderBookSnapshot.from_payload({
        'bids': [['1', '1e100']], 'asks': [['2', '1e99']]}, 'DEL_USDT')
    expected = snapshot.imbalance()
    with localcontext() as context:
        context.prec = 2
        context.Emax = 999999
        assert snapshot.imbalance() == expected


@pytest.mark.asyncio
async def test_cancelled_record_waits_for_worker_commit_before_releasing_lock(tmp_path, monkeypatch):
    import threading
    recorder = MarketDataRecorder(tmp_path / 'cancelled.db')
    entered, release = threading.Event(), threading.Event()
    connection = recorder._connection

    def blocked_connection():
        entered.set()
        assert release.wait(3)
        return connection()

    monkeypatch.setattr(recorder, '_connection', blocked_connection)
    recording = asyncio.create_task(recorder.record_snapshot(book()))
    assert await asyncio.to_thread(entered.wait, 1)
    recording.cancel()
    reading = asyncio.create_task(recorder.load('DEL_USDT'))
    try:
        await asyncio.sleep(0.02)
        assert not recording.done() and not reading.done()
        recording.cancel()  # Repeated cancellation must not detach the worker.
        await asyncio.sleep(0.01)
        assert not recording.done() and not reading.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await recording
    assert len(await reading) == 1


@pytest.mark.parametrize('payload', [None,{}, {'bids':{},'asks':[]},
    {'bids':[['NaN','1']],'asks':[]}, {'bids':[['1','Infinity']],'asks':[]},
    {'bids':[['0','1']],'asks':[]}, {'bids':[['1','-1']],'asks':[]},
    {'bids':[['1']],'asks':[]}, {'symbol':'BTC_USDT','bids':[],'asks':[]}])
def test_malformed_or_wrong_symbol_book_is_rejected(payload):
    with pytest.raises(ValueError):
        OrderBookSnapshot.from_payload(payload,'DEL_USDT')


@pytest.mark.asyncio
async def test_sqlite_keeps_full_snapshots_separate_from_unclassified_live_events(tmp_path):
    recorder=MarketDataRecorder(tmp_path/'observations.db')
    await recorder.record_snapshot(book(1000))
    event=SimpleNamespace(channel='orderbook',path='/orderbooks/24',
        payload={'bids':[['2','1']],'asks':[],'updateId':123},
        source='synthetic-public-publication',received_at='2026-11-03T00:00:00+00:00')
    await recorder.record_event(event,symbol='DEL_USDT')
    snapshots=await recorder.load('del_usdt')
    publications=await recorder.load('DEL_USDT',kind='raw_orderbook')
    assert len(snapshots)==1 and len(publications)==1
    assert snapshots[0]['payload']['source']=='rest_l2_snapshot'
    assert snapshots[0]['payload']['bids'][0]==['2','3']
    assert publications[0]['payload']['is_snapshot'] is False
    assert publications[0]['payload']['payload']==event.payload
    # Reading another market cannot replay this market's history.
    assert await recorder.load('BTC_USDT')==[]


@pytest.mark.asyncio
async def test_sqlite_bounds_are_half_open_and_limit_is_never_silent(tmp_path):
    recorder=MarketDataRecorder(tmp_path/'observations.db')
    for timestamp in [0,1,2,3]:
        await recorder.record_snapshot(book(timestamp))
    result=await recorder.load('DEL_USDT',start_ms=1,end_ms=3,limit=2)
    assert [row['received_at_ms'] for row in result]==[1,2]
    with pytest.raises(ValueError,match='limit'):
        await recorder.load('DEL_USDT',limit=3)
    with pytest.raises(ValueError):
        await recorder.load('DEL_USDT',start_ms=True)
    with pytest.raises(ValueError):
        await recorder.load('DEL_USDT',end_ms=True)


@pytest.mark.asyncio
async def test_recorder_rejects_non_public_event_channel(tmp_path):
    recorder=MarketDataRecorder(tmp_path/'observations.db')
    with pytest.raises(ValueError):
        await recorder.record_event(SimpleNamespace(channel='balances'),symbol='DEL_USDT')
    assert not recorder.path.exists()


@pytest.mark.asyncio
async def test_capture_rejects_unbounded_request_before_accessing_client(tmp_path):
    recorder=MarketDataRecorder(tmp_path/'observations.db')
    client=SimpleNamespace(get_orderbook_snapshot=AsyncMock(return_value=book()))
    with pytest.raises(ValueError,match='max_samples'):
        await recorder.capture_orderbook(client,'DEL_USDT',duration=2,interval=0.1,max_samples=1)
    client.get_orderbook_snapshot.assert_not_awaited()
    assert not recorder.path.exists()


@pytest.mark.asyncio
async def test_capture_stops_hung_provider_at_deadline_without_insert(tmp_path):
    recorder=MarketDataRecorder(tmp_path/'observations.db')
    blocked=asyncio.Event()
    async def hanging(*args,**kwargs):
        await blocked.wait()
        return book()
    client=SimpleNamespace(get_orderbook_snapshot=hanging)
    started=asyncio.get_running_loop().time()
    count=await asyncio.wait_for(recorder.capture_orderbook(client,'DEL_USDT',duration=0.02,interval=0.01,max_samples=2),1)
    assert asyncio.get_running_loop().time()-started<0.5
    assert count==0
    assert not recorder.path.exists()


@pytest.mark.asyncio
async def test_capture_returns_number_of_committed_observations(tmp_path):
    recorder=MarketDataRecorder(tmp_path/'observations.db')
    calls=0
    async def snapshot(symbol):
        nonlocal calls
        calls+=1
        return book(calls)
    count=await recorder.capture_orderbook(SimpleNamespace(get_orderbook_snapshot=snapshot),'DEL_USDT',
                                           duration=0.04,interval=0.01,max_samples=4)
    stored=await recorder.load('DEL_USDT')
    assert 1<=count<=4
    assert len(stored)==count
    assert calls==count
