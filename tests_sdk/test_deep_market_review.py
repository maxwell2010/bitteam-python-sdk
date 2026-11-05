"""Offline market-data integrity checks; no exchange requests."""
from decimal import localcontext
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk.auth import BitTeamAPIError
from bitteam_sdk.marketdata import aggregate_trades, order_execution
from bitteam_sdk.websocket import BitTeamWebSocket


@pytest.mark.parametrize("result", [None, [], "invalid", 123, True])
@pytest.mark.asyncio
async def test_history_rejects_malformed_result_envelope(result):
    client = BitTeamWebSocket()
    client.request = AsyncMock(return_value={"result": result})
    with pytest.raises(BitTeamAPIError):
        await client.get_klines("DEL_USDT", start=0, end=60)


@pytest.mark.parametrize("timestamp", [True, False, 59999.9, -0.5, "Infinity"])
def test_aggregation_rejects_timestamps_instead_of_moving_trades_to_other_bars(timestamp):
    trade = {"timestamp": timestamp, "price": "1.5", "amount": "2"}
    with pytest.raises(ValueError):
        aggregate_trades([trade], "DEL_USDT")


@pytest.mark.parametrize("precision", [6, 28])
def test_aggregation_keeps_exact_volume_with_application_decimal_context(precision):
    trades = [
        {"timestamp": 0, "price": "1.123456789", "amount": "1234567890123456789012345678.123456789"},
        {"timestamp": 1000, "price": "1.223456789", "amount": "0.000000001"},
    ]
    with localcontext() as context:
        context.prec = precision
        candle = aggregate_trades(trades, "DEL_USDT")[0]
    assert candle.volume == "1234567890123456789012345678.123456790"
    assert candle.open == "1.123456789" and candle.close == "1.223456789"


def test_order_remaining_keeps_exact_precision_independent_of_decimal_context():
    with localcontext() as context:
        context.prec = 6
        result = order_execution({"filled": "0.000000001"}, original_amount="123.123456789")
    assert str(result["remaining"]) == "123.123456788"


def test_exact_volume_ignores_ambient_exponent_limits_and_inexact_traps():
    from decimal import Decimal, Inexact, Rounded
    trades = [
        {"timestamp": 0, "price": "1", "amount": "1E+20"},
        {"timestamp": 1, "price": "1", "amount": "0.000000001"},
    ]
    with localcontext() as context:
        context.prec, context.Emax, context.Emin = 6, 9, -9
        context.traps[Inexact] = context.traps[Rounded] = True
        result = aggregate_trades(trades, "DEL_USDT")[0]
    assert Decimal(result.volume) == Decimal("100000000000000000000.000000001")


def test_timestamp_validation_does_not_signal_rounding_in_ambient_context():
    from decimal import Inexact, Rounded
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = context.traps[Rounded] = True
        result = aggregate_trades([{"timestamp": "60000.0", "price": "1", "amount": "1"}], "DEL_USDT")
        with pytest.raises(ValueError):
            aggregate_trades([{"timestamp": "60000.1", "price": "1", "amount": "1"}], "DEL_USDT")
    assert result[0].open_time == 60000


def test_pathological_exponent_gap_fails_without_giant_precision_allocation():
    trades = [
        {"timestamp": 0, "price": "1", "amount": "1E+1000000"},
        {"timestamp": 1, "price": "1", "amount": "1"},
    ]
    with pytest.raises(ValueError, match="precision bounds"):
        aggregate_trades(trades, "DEL_USDT")
