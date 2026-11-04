import asyncpg
from .base import StorageBackend
from ..models import Kline

class PostgresStorage(StorageBackend):
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def init(self):
        self.pool = await asyncpg.create_pool(self.dsn)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS klines (
                    id SERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    open_time BIGINT NOT NULL,
                    open_price TEXT NOT NULL,
                    high_price TEXT NOT NULL,
                    low_price TEXT NOT NULL,
                    close_price TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    UNIQUE(symbol, interval, open_time)
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_klines ON klines(symbol, interval, open_time)")

    async def save_kline(self, kline: Kline):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO klines (symbol, interval, open_time, open_price, high_price, low_price, close_price, volume)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (symbol, interval, open_time) DO UPDATE SET
                    open_price=EXCLUDED.open_price, high_price=EXCLUDED.high_price,
                    low_price=EXCLUDED.low_price, close_price=EXCLUDED.close_price,
                    volume=EXCLUDED.volume
            """, kline.symbol, kline.interval, kline.open_time,
               kline.open, kline.high, kline.low, kline.close, kline.volume)

            await conn.execute("""
                DELETE FROM klines WHERE id NOT IN (
                    SELECT id FROM klines 
                    WHERE symbol = $1 AND interval = $2
                    ORDER BY open_time DESC LIMIT 2000
                ) AND symbol = $1 AND interval = $2
            """, kline.symbol, kline.interval)

    async def get_klines(self, symbol: str, interval: str, limit: int = 1000):
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be positive")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM (SELECT open_time, open_price, high_price, low_price, close_price, volume
                FROM klines
                WHERE symbol = $1 AND interval = $2
                ORDER BY open_time DESC LIMIT $3) AS latest ORDER BY open_time ASC
            """, symbol, interval, limit)
            return [(r["open_time"], r["open_price"], r["high_price"], r["low_price"], r["close_price"], r["volume"]) for r in rows]

    async def close(self):
        if self.pool is not None:
            await self.pool.close()
