"""SQLite candle storage, rolling by default or full-history with retention=None.

File databases use short-lived connections. A :memory: database owns one
connection until close so its schema and rows survive between operations.
"""
import asyncio
from contextlib import asynccontextmanager

import aiosqlite
from .base import StorageBackend, validate_limit, validate_retention
from ..models import Kline


class SQLiteStorage(StorageBackend):
    def __init__(self, path: str = "bitteam_klines.db", *, retention=2000):
        validate_retention(retention)
        self.path, self.retention = path, retention
        self._memory_db = None
        self._lock = asyncio.Lock()
        self._closed = False

    @asynccontextmanager
    async def _connection(self):
        async with self._lock:
            if self._closed:
                raise RuntimeError("SQLite storage is closed")
            if str(self.path) == ":memory:":
                if self._memory_db is None:
                    self._memory_db = await aiosqlite.connect(self.path)
                try:
                    yield self._memory_db
                except BaseException:
                    # A persistent connection must not carry an interrupted
                    # write transaction into the next operation.
                    await self._memory_db.rollback()
                    raise
            else:
                async with aiosqlite.connect(self.path) as db:
                    yield db

    async def init(self):
        async with self._connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS klines (
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    open_time INTEGER NOT NULL,
                    open_price TEXT NOT NULL,
                    high_price TEXT NOT NULL,
                    low_price TEXT NOT NULL,
                    close_price TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    UNIQUE(symbol, interval, open_time)
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_klines ON klines(symbol, interval, open_time)")
            await db.commit()

    async def save_kline(self, kline: Kline):
        async with self._connection() as db:
            await db.execute("""
                INSERT INTO klines VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                    open_price=excluded.open_price, high_price=excluded.high_price,
                    low_price=excluded.low_price, close_price=excluded.close_price,
                    volume=excluded.volume
            """, (kline.symbol, kline.interval, kline.open_time,
                  kline.open, kline.high, kline.low, kline.close, kline.volume))
            if self.retention is not None:
                await db.execute("""
                    DELETE FROM klines WHERE rowid NOT IN (
                        SELECT rowid FROM klines
                        WHERE symbol = ? AND interval = ?
                        ORDER BY open_time DESC LIMIT ?
                    ) AND symbol = ? AND interval = ?
                """, (kline.symbol, kline.interval, self.retention, kline.symbol, kline.interval))
            await db.commit()

    async def get_klines(self, symbol: str, interval: str, limit: int = 1000):
        validate_limit(limit)
        async with self._connection() as db:
            async with db.execute("""
                SELECT * FROM (SELECT open_time, open_price, high_price, low_price, close_price, volume
                FROM klines
                WHERE symbol = ? AND interval = ?
                ORDER BY open_time DESC LIMIT ?) ORDER BY open_time ASC
            """, (symbol, interval, limit)) as cursor:
                return await cursor.fetchall()

    async def close(self):
        async with self._lock:
            self._closed = True
            if self._memory_db is not None:
                db, self._memory_db = self._memory_db, None
                await db.close()
