"""L2 snapshots, exact depth metrics and local history of observed books.

The exchange's live publications are not assumed to be full snapshots or
ordered deltas. No historical book is fabricated from today's snapshot.
"""
import asyncio
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import sqlite3
import time

from .services import symbol_name


def exact_context_size(values, count=1):
    cost = 1
    for value in values:
        digits, exponent = len(value.as_tuple().digits), value.as_tuple().exponent
        if digits > 1000 or abs(exponent) > 1000:
            raise ValueError("Orderbook decimal exceeds supported precision bounds")
        cost = max(cost, digits + abs(exponent))
    return max(80, 2 * cost + len(str(count)) + 8)


@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    amount: Decimal


@dataclass(frozen=True)
class OrderBookSnapshot:
    symbol: str
    bids: tuple
    asks: tuple
    received_at_ms: int
    source: str = "rest_l2_snapshot"

    @classmethod
    def from_payload(cls, payload, symbol, *, received_at_ms=None):
        result = payload.get("result", payload) if isinstance(payload, dict) else None
        if not isinstance(result, dict) or not all(isinstance(result.get(k), list) for k in ("bids", "asks")):
            raise ValueError("Invalid orderbook snapshot structure")
        name = symbol_name(symbol)
        if result.get("symbol") and symbol_name(result["symbol"]) != name:
            raise ValueError("Orderbook belongs to another symbol")

        def levels(rows, reverse):
            combined, parsed = {}, []
            for row in rows:
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    raise ValueError("Invalid orderbook level")
                try:
                    price, amount = Decimal(str(row[0])), Decimal(str(row[1]))
                except InvalidOperation:
                    raise ValueError("Invalid decimal orderbook level") from None
                if not price.is_finite() or not amount.is_finite() or price <= 0 or amount < 0:
                    raise ValueError("Invalid orderbook values")
                parsed.append((price, amount))
            with localcontext() as context:
                context.prec = exact_context_size([v for row in parsed for v in row], len(parsed))
                for price, amount in parsed:
                    if amount:
                        combined[price] = combined.get(price, Decimal(0)) + amount
            return tuple(BookLevel(price, combined[price]) for price in sorted(combined, reverse=reverse))

        timestamp = time.time_ns() // 1_000_000 if received_at_ms is None else received_at_ms
        if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0:
            raise ValueError("received_at_ms must be Unix milliseconds")
        return cls(name.upper(), levels(result["bids"], True), levels(result["asks"], False), timestamp)

    @property
    def best_bid(self):
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self):
        return self.asks[0].price if self.asks else None

    @property
    def spread(self):
        if not self.bids or not self.asks:
            return None
        with localcontext() as context:
            context.prec = exact_context_size([self.best_ask, self.best_bid])
            return self.best_ask - self.best_bid

    @property
    def mid_price(self):
        if not self.bids or not self.asks:
            return None
        with localcontext() as context:
            context.prec = exact_context_size([self.best_ask, self.best_bid])
            return (self.best_ask + self.best_bid) / 2

    def depth(self, side, *, levels=None):
        if side not in ("bids", "asks"):
            raise ValueError("side must be bids or asks")
        if levels is not None and (isinstance(levels, bool) or not isinstance(levels, int) or levels < 1):
            raise ValueError("levels must be positive")
        base, quote, result = Decimal(0), Decimal(0), []
        selected = getattr(self, side)[:levels]
        with localcontext() as context:
            context.prec = exact_context_size([v for row in selected for v in (row.price, row.amount)], len(selected))
            for row in selected:
                base += row.amount
                quote += row.price * row.amount
                result.append({"price": row.price, "amount": row.amount, "cumulative_base": base, "cumulative_quote": quote})
        return result

    def imbalance(self, *, levels=10):
        bids, asks = self.depth("bids", levels=levels), self.depth("asks", levels=levels)
        buy = bids[-1]["cumulative_base"] if bids else Decimal(0)
        sell = asks[-1]["cumulative_base"] if asks else Decimal(0)
        with localcontext() as context:
            context.prec = exact_context_size([buy, sell])
            return (buy - sell) / (buy + sell) if buy + sell else None

    def as_dict(self):
        return {"symbol": self.symbol, "bids": [[str(r.price), str(r.amount)] for r in self.bids],
                "asks": [[str(r.price), str(r.amount)] for r in self.asks],
                "received_at_ms": self.received_at_ms, "source": self.source}


class MarketDataRecorder:
    """Local append-only observation store. Public data only, no credentials."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = asyncio.Lock()

    def _connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("CREATE TABLE IF NOT EXISTS observations (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, kind TEXT NOT NULL, received_at_ms INTEGER NOT NULL, payload TEXT NOT NULL)")
        connection.execute("CREATE INDEX IF NOT EXISTS obs_window ON observations(symbol, kind, received_at_ms, id)")
        return connection

    async def _insert(self, symbol, kind, timestamp, payload):
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        def insert():
            connection = self._connection()
            try:
                with connection:
                    connection.execute("INSERT INTO observations(symbol,kind,received_at_ms,payload) VALUES(?,?,?,?)",
                                       (symbol_name(symbol).upper(), kind, timestamp, encoded))
            finally:
                connection.close()
        async with self._lock:
            # Cancelling to_thread does not stop the worker. Keep the lock
            # until its transaction finishes, then deliver cancellation.
            worker = asyncio.create_task(asyncio.to_thread(insert))
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                while not worker.done():
                    try:
                        await asyncio.shield(worker)
                    except asyncio.CancelledError:
                        pass
                worker.result()
                raise

    async def record_snapshot(self, snapshot):
        if not isinstance(snapshot, OrderBookSnapshot):
            raise TypeError("Expected an OrderBookSnapshot")
        await self._insert(snapshot.symbol, "l2_snapshot", snapshot.received_at_ms, snapshot.as_dict())

    async def record_event(self, event, *, symbol):
        from datetime import datetime
        if getattr(event, "channel", None) not in {"orderbook", "trades", "tickers", "pairs"}:
            raise ValueError("Recorder accepts public market events only")
        timestamp = int(datetime.fromisoformat(event.received_at).timestamp() * 1000)
        await self._insert(symbol, "raw_" + event.channel, timestamp,
                           {"path": event.path, "payload": event.payload, "source": event.source,
                            "is_snapshot": False, "received_at": event.received_at})

    async def load(self, symbol, *, kind="l2_snapshot", start_ms=0, end_ms=None, limit=10000):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be positive")
        if isinstance(start_ms, bool) or not isinstance(start_ms, int) or start_ms < 0 or (end_ms is not None and (isinstance(end_ms, bool) or not isinstance(end_ms, int) or end_ms <= start_ms)):
            raise ValueError("Invalid millisecond range")
        def read():
            connection = self._connection()
            try:
                sql = "SELECT received_at_ms,payload FROM observations WHERE symbol=? AND kind=? AND received_at_ms>=?"
                args = [symbol_name(symbol).upper(), kind, start_ms]
                if end_ms is not None:
                    sql += " AND received_at_ms<?"
                    args.append(end_ms)
                sql += " ORDER BY received_at_ms,id LIMIT ?"
                args.append(limit + 1)
                rows = connection.execute(sql, args).fetchall()
                if len(rows) > limit:
                    raise ValueError("Recording range exceeds limit; narrow the range or increase limit")
                return [{"received_at_ms": timestamp, "payload": json.loads(payload)} for timestamp, payload in rows]
            finally:
                connection.close()
        async with self._lock:
            return await asyncio.to_thread(read)

    async def capture_orderbook(self, client, symbol, *, duration=60, interval=1, max_samples=10000):
        """Bound snapshot acquisition by duration; finish an already-started commit."""
        import math
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in (duration, interval)):
            raise ValueError("duration and interval must be finite positive seconds")
        if isinstance(max_samples, bool) or not isinstance(max_samples, int) or max_samples < 1:
            raise ValueError("max_samples must be positive")
        if math.ceil(duration / interval) > max_samples:
            raise ValueError("Capture exceeds max_samples")
        start = asyncio.get_running_loop().time()
        count = 0
        while asyncio.get_running_loop().time() - start < duration and count < max_samples:
            remaining = duration - (asyncio.get_running_loop().time() - start)
            try:
                snapshot = await asyncio.wait_for(client.get_orderbook_snapshot(symbol), remaining)
            except asyncio.TimeoutError:
                break
            await self.record_snapshot(snapshot)
            count += 1
            remaining = duration - (asyncio.get_running_loop().time() - start)
            if remaining > 0:
                await asyncio.sleep(min(interval, remaining))
        return count
