import aiosqlite
from .base import StorageBackend
from ..models import Kline

class SQLiteStorage(StorageBackend):
    def __init__(self, path: str = "bitteam_klines.db"):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
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
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                INSERT INTO klines VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                    open_price=excluded.open_price, high_price=excluded.high_price,
                    low_price=excluded.low_price, close_price=excluded.close_price,
                    volume=excluded.volume
            """, (kline.symbol, kline.interval, kline.open_time,
                  kline.open, kline.high, kline.low, kline.close, kline.volume))
            await db.execute("""
                DELETE FROM klines WHERE rowid NOT IN (
                    SELECT rowid FROM klines 
                    WHERE symbol = ? AND interval = ?
                    ORDER BY open_time DESC LIMIT 2000
                ) AND symbol = ? AND interval = ?
            """, (kline.symbol, kline.interval, kline.symbol, kline.interval))
            await db.commit()

    async def get_klines(self, symbol: str, interval: str, limit: int = 1000):
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be positive")
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("""
                SELECT * FROM (SELECT open_time, open_price, high_price, low_price, close_price, volume
                FROM klines
                WHERE symbol = ? AND interval = ?
                ORDER BY open_time DESC LIMIT ?) ORDER BY open_time ASC
            """, (symbol, interval, limit))
            return await cursor.fetchall()
