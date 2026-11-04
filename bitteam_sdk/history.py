"""Bounded, chunked public candle history over the verified history WSS.

Ranges use candle open times and are half-open [start, end), in UTC seconds.
The underlying server returns an inclusive end, so that row is excluded here.
This traverses every requested time chunk; it cannot manufacture candles the
server omits or guarantee that an exchange retains data before a listing.
"""
from datetime import datetime

from .models import Kline
from .services import symbol_name
from .websocket import BitTeamWebSocket, validate_candle_values


PERIOD_SECONDS = {'1m': 60, '5m': 300, '15m': 900, '1h': 3600, '1d': 86400}


class HistoryError(RuntimeError):
    pass


class HistoryLimitError(HistoryError):
    """A configured resource bound was reached; the result was not truncated."""


class HistoryProtocolError(HistoryError):
    """The provider returned rows that do not match the requested candle range."""


def utc_seconds(value, name):
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f'{name} datetime must have an explicit timezone')
        if value.microsecond:
            raise ValueError(f'{name} must use whole seconds')
        value = int(value.timestamp())
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f'{name} must be nonnegative Unix seconds or an aware datetime')
    return value


def positive_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f'{name} must be a positive integer')
    return value


async def iter_klines(symbol, interval='1m', *, start, end, source=None,
                      chunk_bars=1000, limit=1_000_000, max_requests=10_000):
    """Yield all supplied candles in [start, end) in chronological order.

    ``source`` may be an existing BitTeamWebSocket or a compatible provider.
    Caller-owned providers are never closed. Internally owned connections are
    closed on success, error, cancellation or explicit generator.aclose().

    ``limit`` is a maximum allowed number of candles, not a truncation request.
    Exceeding it raises HistoryLimitError. Sparse/empty chunks are valid and
    produce no artificial rows. Requests exceeding max_requests are rejected
    before accessing the provider.
    """
    name = symbol_name(symbol)
    if interval not in PERIOD_SECONDS:
        raise ValueError('Unsupported candle interval')
    start, end = utc_seconds(start, 'start'), utc_seconds(end, 'end')
    if start >= end:
        raise ValueError('Expected start < end')
    positive_integer(chunk_bars, 'chunk_bars')
    positive_integer(limit, 'limit')
    positive_integer(max_requests, 'max_requests')
    if chunk_bars > 10_000:
        raise ValueError('chunk_bars must not exceed 10000; larger server windows are not assumed')
    period = PERIOD_SECONDS[interval]
    # Split on UTC candle boundaries. The first request may begin inside a bar.
    cursor = start
    windows = []
    while cursor < end:
        stop = min(end, (cursor // period + chunk_bars) * period)
        windows.append((cursor, stop))
        if len(windows) > max_requests:
            raise HistoryLimitError('History requires more than max_requests; narrow the range or increase the bound')
        cursor = stop
    owned = source is None
    provider = BitTeamWebSocket() if owned else source
    count = 0
    previous = None
    try:
        for lower, upper in windows:
            response = await provider.get_klines(name, interval, start=lower, end=upper)
            if not isinstance(response, list):
                raise HistoryProtocolError('Candle provider must return a list')
            unique = {}
            for row in response:
                if not isinstance(row, Kline) or isinstance(row.open_time, bool) or not isinstance(row.open_time, int):
                    raise HistoryProtocolError('Candle provider returned a malformed candle')
                try:
                    validate_candle_values((row.open, row.high, row.low, row.close, row.volume))
                except ValueError:
                    raise HistoryProtocolError('Candle provider returned invalid market values') from None
                if row.open_time % (period * 1000):
                    raise HistoryProtocolError('Candle open time is not aligned to its UTC interval')
                if row.open_time < (lower // period) * period * 1000 or row.open_time > upper * 1000:
                    raise HistoryProtocolError('Candle provider returned data outside its requested window')
                if symbol_name(row.symbol) != name or row.interval != interval:
                    raise HistoryProtocolError('Candle provider returned another symbol or interval')
                # A bar containing a nonaligned start and the inclusive end bar
                # are outside the requested half-open range.
                if lower * 1000 <= row.open_time < upper * 1000:
                    if row.open_time in unique and row != unique[row.open_time]:
                        raise HistoryProtocolError('Conflicting duplicate candles in one history response')
                    unique[row.open_time] = row
            for timestamp in sorted(unique):
                if previous is not None and timestamp <= previous:
                    raise HistoryProtocolError('History failed to advance chronologically')
                if count == limit:
                    raise HistoryLimitError('History exceeds limit; increase it or request a narrower range')
                count += 1
                previous = timestamp
                yield unique[timestamp]
    finally:
        if owned:
            await provider.close()


async def fetch_klines(symbol, interval='1m', *, start, end, source=None,
                       chunk_bars=1000, limit=1_000_000, max_requests=10_000):
    """Collect iter_klines. A limit failure raises instead of returning a partial list."""
    return [row async for row in iter_klines(symbol, interval, start=start, end=end, source=source,
                                            chunk_bars=chunk_bars, limit=limit, max_requests=max_requests)]
