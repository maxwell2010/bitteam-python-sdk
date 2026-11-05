"""Public facade timestamps must not become fabricated/truncated dates."""
from decimal import Decimal, localcontext, Inexact, Rounded
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import BitTeamAPIError
from bitteam_sdk.services import ServiceMethods


def client(timestamp):
    service = ServiceMethods()
    service.api = SimpleNamespace(get_cmc_trades_by_pair=AsyncMock(return_value=[
        {'trade_id': 1, 'timestamp': timestamp, 'price': '2', 'base_volume': '3'}]))
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize('timestamp', [True, False, 1000.9, '1000.9', None, 'NaN', float('inf'), {}, []])
async def test_malformed_timestamp_rejected_before_date_normalization(timestamp):
    with pytest.raises(BitTeamAPIError) as error:
        await client(timestamp).get_trade_history('DEL_USDT')
    assert error.value.status == 502


@pytest.mark.asyncio
@pytest.mark.parametrize('timestamp', [1000, '1000', '1000.0', Decimal('1000.0')])
async def test_whole_milliseconds_preserved_through_history_and_candles(timestamp):
    service = client(timestamp)
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = context.traps[Rounded] = True
        history = await service.get_trade_history('DEL_USDT')
        candles = await service.get_candles_from_trades('DEL_USDT')
    assert history[0]['timestamp'] == timestamp
    assert history[0]['createdAt'] == '1970-01-01T00:00:01+00:00'
    assert candles[0].open_time == 0
    assert candles[0].volume == '3'


@pytest.mark.asyncio
async def test_missing_timestamp_keeps_existing_history_representation():
    service = client(1000)
    del service.api.get_cmc_trades_by_pair.return_value[0]['timestamp']
    assert (await service.get_trade_history('DEL_USDT'))[0]['createdAt'] is None
