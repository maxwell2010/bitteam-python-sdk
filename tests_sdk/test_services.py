import asyncio
from decimal import Decimal
import pytest
from yarl import URL
from bitteam_sdk import AuthState, BitTeamClient, SessionAuth, BitTeamAPIError
from bitteam_sdk.marketdata import aggregate_trades, order_execution
from bitteam_sdk.models import Kline
from bitteam_sdk.storage.sqlite import SQLiteStorage
from bitteam_sdk.websocket import BitTeamWebSocket
from test_auth import environment


@pytest.mark.asyncio
async def test_market_methods_preserve_shapes_and_use_real_bid_ask(environment):
    state, create = environment
    c = await create()
    assert await c.get_symbols() == ['DEL_USDT']
    assert (await c.get_trading_pairs())[0]['base'] == 'DEL'
    ticker = await c.get_ticker('DEL/USDT')
    assert ticker['last_price'] == Decimal('1.23456789')
    assert ticker['bid'] == Decimal('1.20')
    assert ticker['ask'] == Decimal('1.21')
    assert len((await c.get_orderbook('DEL_USDT', 1))['bids']) == 1
    assert (await c.get_trade_history('DEL_USDT', 1))[0]['trade_id'] == 2
    latest = (await c.get_trade_history('DEL_USDT', 1))[0]
    assert latest['id'] == 2 and latest['amount'] == '4'
    assert latest['createdAt'].endswith('+00:00')
    candles = await c.get_candles_from_trades('DEL_USDT')
    assert candles[0].volume == '6'
    assert all('Authorization' not in row['headers'] for row in state['calls'])


@pytest.mark.asyncio
@pytest.mark.parametrize('key_mode', [False, True])
async def test_service_orders_trades_cancel_and_filters(environment, key_mode):
    state, create = environment
    c = await create(key_mode=key_mode)
    if key_mode:
        await c.init()
        assert await c.get_balances() == {}
    else:
        await c.login('person@example.test', 'secret-password')
    assert (await c.get_open_orders('DEL/USDT'))[0]['id'] == 10
    assert (await c.get_user_trades(pair='DEL/USDT'))[0]['makerOrderId'] == 10
    assert await c.get_order_status(10) == 'executed'
    order = await c.order_info(10)
    status = order_execution(order, original_amount='20')
    assert status['partial'] is True
    assert status['remaining'] == Decimal('11.286')
    await c.cancel_order(10)
    await c.cancel_all_orders(pair_id=9)
    calls = [r for r in state['calls'] if r['path'].endswith(('cancelorder', '/order/cancel'))]
    assert calls[0]['body'] == {'id': '10' if key_mode else 10}
    session_orders = [r for r in state['calls'] if r['path'].endswith('/ordersByUser')]
    if session_orders:
        assert session_orders[0]['query']['where[pairId]'] == '9'
    else:
        assert [r for r in state['calls'] if r['path'].endswith('/ccxt/ordersOfUser')][0]['query']['pair'] == 'del_usdt'


@pytest.mark.asyncio
async def test_history_pagination_handles_multiple_pages_without_truncation(environment):
    state, create = environment
    c = await create(key_mode=True)
    await c.init()
    state['pages'] = {0: [{'id': 1}, {'id': 2}], 2: [{'id': 3}]}
    assert [r['id'] async for r in c.iter_user_orders(page_size=2)] == [1, 2, 3]
    state['pages'] = {0: [{'id': 1}, {'id': 2}], 2: [{'id': 1}, {'id': 2}]}
    with pytest.raises(RuntimeError, match='repeated'):
        _ = [r async for r in c.iter_user_orders(page_size=2)]


@pytest.mark.asyncio
async def test_withdrawal_confirmation_is_explicit_and_not_repeated(environment):
    state, create = environment
    c = await create()
    await c.login('person@example.test', 'secret-password')
    await c.request_withdrawal(currency_id=9, amount=Decimal('0.01'), address='test-address')
    await c.send_withdrawal_email_code('example-id')
    await c.confirm_withdrawal(order_id='example-id', email_code=123456, totp='012345')
    rows = [r for r in state['calls'] if r['path'].endswith('/withdraw/confirm')]
    assert len(rows) == 1
    assert rows[0]['body']['token2FA'] == '012345'
    with pytest.raises(ValueError):
        await c.confirm_withdrawal(order_id='example-id', email_code=1)
    assert len([r for r in state['calls'] if r['path'].endswith('/withdraw/confirm')]) == 1


@pytest.mark.asyncio
async def test_read_retries_rate_limit_but_writes_do_not(environment):
    state, create = environment
    c = await create()
    assert await c.rest._request('GET', '/flaky', public=True) == {'ok': True}
    assert state['counts']['/trade/api/flaky'] == 3
    state['counts']['/trade/api/flaky'] = 0
    with pytest.raises(BitTeamAPIError):
        await c.rest._request('POST', '/flaky', data={}, public=True)
    assert state['counts']['/trade/api/flaky'] == 1


@pytest.mark.asyncio
async def test_get_with_side_effect_is_not_replayed(environment, monkeypatch):
    state, create = environment
    c = await create()
    await c.login('person@example.test', 'secret-password')
    calls = 0
    async def rejected(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise BitTeamAPIError(503, retry_after=0)
    monkeypatch.setattr(c.rest, '_send', rejected)
    with pytest.raises(BitTeamAPIError):
        await c.create_deposit_address(9)
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('amount,price', [('NaN','1'), ('Infinity','1'), ('0','1'), ('1','-1'), ('0.0000000000000000001','1')])
async def test_invalid_order_cannot_reach_exchange(environment, amount, price):
    state, create = environment
    c = await create(key_mode=True)
    await c.init()
    with pytest.raises(ValueError):
        await c.create_order('DEL_USDT', 'buy', price=price, amount=amount)
    assert state['counts']['/trade/api/ccxt/ordercreate'] == 0


def test_candles_are_sorted_deduplicated_exact_and_do_not_fill_empty_intervals():
    trades = [
        {'trade_id': 3, 'timestamp': 180001, 'price': '0.3', 'base_volume': '0.2'},
        {'trade_id': 2, 'timestamp': 2000, 'price': '0.2', 'base_volume': '0.2'},
        {'trade_id': 1, 'timestamp': 1000, 'price': '0.1', 'base_volume': '0.1'},
        {'trade_id': 2, 'timestamp': 2000, 'price': '0.2', 'base_volume': '0.2'},
    ]
    result = aggregate_trades(trades, 'DEL_USDT')
    assert [k.open_time for k in result] == [0, 180000]
    assert (result[0].open, result[0].close, result[0].volume) == ('0.1','0.2','0.3')
    assert order_execution({'status': 'executed', 'amount': '2', 'executed': True})['partial'] is None


@pytest.mark.asyncio
async def test_sqlite_updates_forming_candle_and_returns_latest_window(tmp_path):
    storage = SQLiteStorage(str(tmp_path / 'candles.db'))
    await storage.init()
    for i in range(4):
        await storage.save_kline(Kline('DEL_USDT','1m',i,'1','2','1','1','1'))
    await storage.save_kline(Kline('DEL_USDT','1m',3,'1','3','1','3','5'))
    result = await storage.get_klines('DEL_USDT','1m',2)
    assert [r[0] for r in result] == [2,3]
    assert result[-1][-2:] == ('3','5')


async def local_history(environment):
    state, create = environment
    c = await create()
    port = URL(c.rest.base_url).port
    ws = BitTeamWebSocket(url=f'wss://spot.bitteam.test:{port}/history', timeout=0.5)
    ws._session = c.rest._session
    return state, ws


@pytest.mark.asyncio
async def test_nes_handshake_history_subscription_ping_fragmentation(environment):
    state, ws = await local_history(environment)
    async with ws:
        assert '15' in (await ws.get_config())['supported_resolutions']
        data = await ws.get_klines('DEL_USDT','15m',start=1,end=2000)
        assert data[0].open_time == 1000000
        assert data[0].volume == '2.5'
        assert await ws.request('/api/tw/chunked') == {'result': {'data': []}}
        sub = await ws.subscribe_kline('DEL_USDT','1m')
        candle = await asyncio.wait_for(anext(sub),1)
        assert candle.close == '2'
        await asyncio.sleep(0.01)
        assert state['counts']['ws_pongs'] >= 1
        await sub.close()
        with pytest.raises(StopAsyncIteration):
            await anext(sub)


@pytest.mark.asyncio
@pytest.mark.parametrize('route,exception', [('invalid',BitTeamAPIError),('disconnect',ConnectionError),('timeout',asyncio.TimeoutError)])
async def test_nes_failure_paths_clean_pending_and_do_not_leak_secrets(environment, route, exception):
    _, ws = await local_history(environment)
    async with ws:
        with pytest.raises(exception) as error:
            await ws.request('/api/tw/'+route)
        assert 'secret-password' not in str(error.value)
        assert not ws._pending


def test_no_credentials_needed_for_public_sdk_and_no_insecure_websocket():
    c = BitTeamClient()
    assert c.auth.__class__.__name__ == 'PublicAuth'
    with pytest.raises(ValueError):
        BitTeamWebSocket(url='ws://localhost')
    with pytest.raises(NotImplementedError):
        BitTeamWebSocket(api_key='key',api_secret='secret')
