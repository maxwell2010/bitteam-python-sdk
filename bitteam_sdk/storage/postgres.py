"""PostgreSQL candle storage with atomic upsert and rolling retention.

retention=None explicitly disables pruning for full-history persistence.
Initialize once before use; repeated init is idempotent. close releases the
pool and later operations fail until a new explicit init.
"""
import asyncio
import asyncpg
from .base import StorageBackend, validate_limit, validate_retention
from ..models import Kline


class PostgresStorage(StorageBackend):
    def __init__(self, dsn: str, *, retention=2000):
        validate_retention(retention)
        self.dsn, self.retention = dsn, retention
        self.pool = None
        self._lifecycle_lock = asyncio.Lock()

    async def init(self):
        async with self._lifecycle_lock:
            if self.pool is not None:
                return
            pool = await asyncpg.create_pool(self.dsn)
            try:
                async with pool.acquire() as conn:
                    async with conn.transaction():
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
            except BaseException:
                await pool.close()
                raise
            self.pool = pool

    def _require_pool(self):
        if self.pool is None or self.pool.is_closing():
            raise RuntimeError("PostgreSQL storage is not initialized or is closed")
        return self.pool

    async def save_kline(self, kline: Kline):
        async with self._require_pool().acquire() as conn:
            async with conn.transaction():
                if self.retention is not None:
                    # Concurrent same-series writers must prune against a
                    # current snapshot after the previous writer commits.
                    # Hash collisions merely serialize unrelated series.
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
                                       kline.symbol, kline.interval)
                await conn.execute("""
                    INSERT INTO klines (symbol, interval, open_time, open_price, high_price, low_price, close_price, volume)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (symbol, interval, open_time) DO UPDATE SET
                        open_price=EXCLUDED.open_price, high_price=EXCLUDED.high_price,
                        low_price=EXCLUDED.low_price, close_price=EXCLUDED.close_price,
                        volume=EXCLUDED.volume
                """, kline.symbol, kline.interval, kline.open_time,
                   kline.open, kline.high, kline.low, kline.close, kline.volume)
                if self.retention is not None:
                    await conn.execute("""
                        DELETE FROM klines WHERE id NOT IN (
                            SELECT id FROM klines
                            WHERE symbol = $1 AND interval = $2
                            ORDER BY open_time DESC LIMIT $3
                        ) AND symbol = $1 AND interval = $2
                    """, kline.symbol, kline.interval, self.retention)

    async def get_klines(self, symbol: str, interval: str, limit: int = 1000):
        validate_limit(limit)
        async with self._require_pool().acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM (SELECT open_time, open_price, high_price, low_price, close_price, volume
                FROM klines
                WHERE symbol = $1 AND interval = $2
                ORDER BY open_time DESC LIMIT $3) AS latest ORDER BY open_time ASC
            """, symbol, interval, limit)
            return [(r["open_time"], r["open_price"], r["high_price"], r["low_price"], r["close_price"], r["volume"]) for r in rows]

    async def close(self):
        async with self._lifecycle_lock:
            if self.pool is not None:
                pool, self.pool = self.pool, None
                await pool.close()
