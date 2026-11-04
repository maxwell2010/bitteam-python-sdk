from datetime import datetime, timedelta, timezone
import pytest
from bitteam_sdk.history import (fetch_klines, iter_klines, HistoryLimitError, HistoryProtocolError)
from bitteam_sdk.models import Kline


def candle(timestamp, symbol='DEL_USDT', interval='1m', close='1'):
    return Kline(symbol, interval, timestamp*1000, '1','1','1',close,'2')


class InclusiveProvider:
    def __init__(self, rows):
        self.rows, self.calls, self.closed = rows, [], False
    async def get_klines(self, symbol, interval, *, start, end):
        self.calls.append((symbol,interval,start,end))
        # Unsorted, inclusive, duplicated response matching observed boundaries.
        selected=[r for r in self.rows if start//60*60000 <= r.open_time <= end*1000]
        return list(reversed(selected))+selected
    async def close(self):
        self.closed=True


@pytest.mark.asyncio
@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', None])
async def test_compatible_provider_cannot_inject_invalid_market_values(value):
    row = candle(0)
    row.volume = value
    with pytest.raises(HistoryProtocolError, match='market values'):
        await fetch_klines('DEL_USDT', start=0, end=60, source=InclusiveProvider([row]))


@pytest.mark.asyncio
async def test_chunks_include_every_requested_bar_once_without_final_endpoint():
    source=InclusiveProvider([candle(t) for t in range(0,421,60)])
    rows=await fetch_klines('DEL/USDT',start=0,end=420,source=source,chunk_bars=2)
    assert [r.open_time for r in rows]==list(range(0,420000,60000))
    assert [(c[2],c[3]) for c in source.calls]==[(0,120),(120,240),(240,360),(360,420)]
    assert not source.closed


@pytest.mark.asyncio
async def test_sparse_chunks_do_not_stop_early_or_fill_missing_candles():
    source=InclusiveProvider([candle(0),candle(360)])
    rows=await fetch_klines('del_usdt',start=0,end=420,source=source,chunk_bars=2)
    assert [r.open_time for r in rows]==[0,360000]
    assert len(source.calls)==4


@pytest.mark.asyncio
async def test_non_aligned_start_and_explicit_timezone_are_handled_in_utc():
    source=InclusiveProvider([candle(t) for t in range(0,301,60)])
    local=timezone(timedelta(hours=7))
    start=datetime(1970,1,1,7,0,30,tzinfo=local)
    end=datetime(1970,1,1,0,4,30,tzinfo=timezone.utc)
    result=await fetch_klines('DEL_USDT',start=start,end=end,source=source,chunk_bars=2)
    assert [r.open_time for r in result]==[60000,120000,180000,240000]


@pytest.mark.asyncio
async def test_limit_raises_instead_of_silently_returning_partial_history():
    source=InclusiveProvider([candle(t) for t in range(0,301,60)])
    with pytest.raises(HistoryLimitError,match='exceeds limit'):
        await fetch_klines('DEL_USDT',start=0,end=300,source=source,chunk_bars=2,limit=3)
    assert not source.closed


@pytest.mark.asyncio
async def test_request_budget_rejects_before_first_request():
    source=InclusiveProvider([])
    with pytest.raises(HistoryLimitError,match='max_requests'):
        await fetch_klines('DEL_USDT',start=0,end=600,source=source,chunk_bars=1,max_requests=2)
    assert not source.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('kwargs',[{'start':True,'end':60},{'start':0,'end':0},
    {'start':-1,'end':60},{'start':0.1,'end':60},{'start':datetime(2026,1,1),'end':1800000000},
    {'start':0,'end':60,'chunk_bars':0},{'start':0,'end':60,'chunk_bars':10001},
    {'start':0,'end':60,'limit':False},{'start':0,'end':60,'max_requests':0}])
async def test_invalid_bounds_are_rejected_without_provider_calls(kwargs):
    source=InclusiveProvider([])
    with pytest.raises(ValueError):
        await fetch_klines('DEL_USDT',source=source,**kwargs)
    assert not source.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',[candle(60,'BTC_USDT'),candle(60,interval='5m'),candle(600),
                                Kline('DEL_USDT','1m',1,'1','1','1','1','1')])
async def test_provider_cannot_return_another_market_or_out_of_bounds_data(bad):
    class Broken(InclusiveProvider):
        async def get_klines(self,*args,**kwargs):return [bad]
    with pytest.raises(HistoryProtocolError):
        await fetch_klines('DEL_USDT',start=0,end=120,source=Broken([]))


@pytest.mark.asyncio
async def test_conflicting_duplicate_is_not_silently_overwritten():
    class Broken(InclusiveProvider):
        async def get_klines(self,*args,**kwargs):return [candle(60),candle(60,close='2')]
    with pytest.raises(HistoryProtocolError,match='Conflicting'):
        await fetch_klines('DEL_USDT',start=0,end=120,source=Broken([]))


@pytest.mark.asyncio
async def test_owned_connection_is_closed_if_consumer_stops_early(monkeypatch):
    source=InclusiveProvider([candle(0),candle(60)])
    monkeypatch.setattr('bitteam_sdk.history.BitTeamWebSocket',lambda:source)
    stream=iter_klines('DEL_USDT',start=0,end=120)
    assert (await anext(stream)).open_time==0
    await stream.aclose()
    assert source.closed
