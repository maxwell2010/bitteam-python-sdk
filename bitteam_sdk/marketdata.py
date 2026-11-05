"""Exact decimal candles derived from the public trades used by our terminal."""
from decimal import Context, Decimal, InvalidOperation, MAX_EMAX, MIN_EMIN, localcontext
from .models import Kline
from .services import symbol_name


def _exact_add(left, right):
    """Add finite decimals without rounding to an application precision context."""
    precision = max(left.adjusted(), right.adjusted()) - min(
        left.as_tuple().exponent, right.as_tuple().exponent) + 2
    if precision > 10000:
        raise ValueError("Market decimal addition exceeds supported precision bounds")
    # Exponent limits and traps also belong to the application context.
    with localcontext(Context(prec=precision, Emax=MAX_EMAX, Emin=MIN_EMIN)):
        return left + right


def aggregate_trades(trades, symbol, *, interval="1m"):
    periods = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
    if interval not in periods:
        raise ValueError("Unsupported candle interval")
    ticks, seen = [], set()
    for trade in trades:
        identity = trade.get("trade_id", trade.get("id"))
        if identity is not None:
            if str(identity) in seen:
                continue
            seen.add(str(identity))
        try:
            raw_timestamp = trade["timestamp"]
            timestamp_value = Decimal(str(raw_timestamp))
            if (isinstance(raw_timestamp, bool) or not timestamp_value.is_finite()
                    or timestamp_value != timestamp_value.to_integral_value()):
                raise ValueError("Timestamp must be whole milliseconds")
            timestamp = int(timestamp_value)
            price = Decimal(str(trade["price"]))
            amount = Decimal(str(trade.get("base_volume", trade.get("amount"))))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise ValueError("Malformed public trade") from None
        if timestamp < 0 or not price.is_finite() or not amount.is_finite() or price <= 0 or amount < 0:
            raise ValueError("Invalid public trade values")
        ticks.append((timestamp, price, amount))
    ticks.sort(key=lambda item: item[0])
    width, buckets = periods[interval] * 1000, {}
    for timestamp, price, amount in ticks:
        bucket = timestamp // width * width
        if bucket not in buckets:
            buckets[bucket] = [price, price, price, price, amount]
        else:
            values = buckets[bucket]
            values[1], values[2], values[3] = max(values[1], price), min(values[2], price), price
            values[4] = _exact_add(values[4], amount)
    return [Kline(symbol_name(symbol).upper(), interval, timestamp, *(str(v) for v in values))
            for timestamp, values in sorted(buckets.items())]


def order_execution(order, *, original_amount=None):
    """Do not infer full execution from closed status or amount==filled.

    Our terminal observed history rows rewritten to the filled amount. Supply
    the amount saved when placing the order to reliably detect partial fills.
    """
    value = order.get("filled", order.get("executedAmount", order.get("executed")))
    filled = None if value is None or isinstance(value, bool) else Decimal(str(value))
    original = None if original_amount is None else Decimal(str(original_amount))
    if filled is not None and (not filled.is_finite() or filled < 0):
        raise ValueError("Invalid filled amount")
    if original is not None and (not original.is_finite() or original <= 0):
        raise ValueError("Invalid original amount")
    known = original is not None and filled is not None
    return {"status": order.get("status"), "filled": filled, "original_amount": original,
            "remaining": max(Decimal(0), _exact_add(original, filled.copy_negate())) if known else None,
            "partial": (Decimal(0) < filled < original) if known else None}
