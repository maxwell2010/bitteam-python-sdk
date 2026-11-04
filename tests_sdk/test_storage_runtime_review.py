"""Actual SQLite file runtime contracts; no optional database skips or mocks."""
import asyncio
import sqlite3

import pytest

from bitteam_sdk.models import Kline
from bitteam_sdk.storage.sqlite import SQLiteStorage


def kline(timestamp, *, symbol="SYNTH_A", interval="1m", close="1.000000000000000001"):
    return Kline(symbol, interval, timestamp, "1", "2", "0.5", close, "0.000000000000000001")


@pytest.mark.asyncio
async def test_sqlite_file_upsert_latest_chronological_order_and_namespace_isolation(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "synthetic.db"))
    await storage.init()
    await storage.init()
    for timestamp in (120000, 0, 60000):
        await storage.save_kline(kline(timestamp))
    await storage.save_kline(kline(60000, close="1.999999999999999999"))
    await storage.save_kline(kline(0, symbol="SYNTH_B"))
    await storage.save_kline(kline(0, interval="5m"))
    rows = await storage.get_klines("SYNTH_A", "1m", 2)
    assert [row[0] for row in rows] == [60000, 120000]
    assert rows[0][4:] == ("1.999999999999999999", "0.000000000000000001")
    assert len(await storage.get_klines("SYNTH_A", "1m")) == 3
    assert len(await storage.get_klines("SYNTH_B", "1m")) == 1
    assert len(await storage.get_klines("SYNTH_A", "5m")) == 1
    reopened = SQLiteStorage(storage.path)
    await reopened.init()
    assert await reopened.get_klines("SYNTH_A", "1m", 2) == rows


@pytest.mark.asyncio
async def test_sqlite_retains_latest_2000_per_symbol_interval_and_rolls_back_failed_retention(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "synthetic.db"))
    await storage.init()
    with sqlite3.connect(storage.path) as db:
        db.executemany("INSERT INTO klines VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            [("SYNTH_A", "1m", i, "1", "2", "0.5", "1", "1") for i in range(2000)])
    await storage.save_kline(kline(2000))
    assert [row[0] for row in await storage.get_klines("SYNTH_A", "1m", 3000)] == list(range(1, 2001))
    await storage.save_kline(kline(0, symbol="SYNTH_B"))
    await storage.save_kline(kline(0, interval="5m"))
    with sqlite3.connect(storage.path) as db:
        db.execute("CREATE TRIGGER fail_retention BEFORE DELETE ON klines BEGIN SELECT RAISE(ABORT, 'synthetic retention failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic retention failure"):
        await storage.save_kline(kline(2001))
    assert len(await storage.get_klines("SYNTH_A", "1m", 3000)) == 2000
    assert (await storage.get_klines("SYNTH_A", "1m", 1))[0][0] == 2000
    assert len(await storage.get_klines("SYNTH_B", "1m")) == 1
    assert len(await storage.get_klines("SYNTH_A", "5m")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [True, False, 0, -1, 1.5, None, "1"])
async def test_sqlite_invalid_limit_fails_consistently_before_opening_database(tmp_path, limit):
    path = tmp_path / "not-created.db"
    with pytest.raises(ValueError):
        await SQLiteStorage(str(path)).get_klines("SYNTH_A", "1m", limit)
    assert not path.exists()


@pytest.mark.asyncio
async def test_sqlite_cancelled_write_waiting_on_real_lock_does_not_persist_and_storage_reopens(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "synthetic.db"))
    await storage.init()
    lock = sqlite3.connect(storage.path)
    lock.execute("BEGIN EXCLUSIVE")
    task = asyncio.create_task(storage.save_kline(kline(0)))
    # The database remains exclusively locked while the coroutine begins its
    # aiosqlite worker exchange. Cancellation must never commit this write.
    await asyncio.sleep(0.03)
    task.cancel()
    lock.rollback()
    lock.close()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await storage.get_klines("SYNTH_A", "1m") == []
    await storage.save_kline(kline(60000))
    assert (await storage.get_klines("SYNTH_A", "1m"))[0][0] == 60000


@pytest.mark.asyncio
async def test_sqlite_memory_schema_and_rows_survive_operations_until_explicit_close():
    storage = SQLiteStorage(":memory:")
    try:
        await storage.init()
        await storage.save_kline(kline(0))
        await storage.init()
        assert (await storage.get_klines("SYNTH_A", "1m"))[0][0] == 0
        assert storage._memory_db is not None
    finally:
        await storage.close()
    assert storage._memory_db is None
    await storage.close()
    with pytest.raises(RuntimeError, match="closed"):
        await storage.get_klines("SYNTH_A", "1m")


@pytest.mark.asyncio
async def test_sqlite_memory_rollback_and_recovery_after_real_retention_error():
    storage = SQLiteStorage(":memory:", retention=1)
    try:
        await storage.init()
        await storage.save_kline(kline(0))
        await storage._memory_db.execute("CREATE TRIGGER fail_retention BEFORE DELETE ON klines BEGIN SELECT RAISE(ABORT, 'synthetic retention failure'); END")
        with pytest.raises(sqlite3.IntegrityError):
            await storage.save_kline(kline(60000))
        assert [row[0] for row in await storage.get_klines("SYNTH_A", "1m")] == [0]
        await storage._memory_db.execute("DROP TRIGGER fail_retention")
        await storage.save_kline(kline(120000))
        assert [row[0] for row in await storage.get_klines("SYNTH_A", "1m")] == [120000]
    finally:
        await storage.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("memory", [False, True])
async def test_sqlite_full_history_is_explicit_and_retains_more_than_2000_rows(tmp_path, memory):
    from bitteam_sdk.storage import get_storage
    storage = get_storage("sqlite", path=":memory:" if memory else str(tmp_path / "full-history.db"), retention=None)
    try:
        await storage.init()
        if memory:
            for timestamp in range(2005):
                await storage.save_kline(kline(timestamp))
        else:
            with sqlite3.connect(storage.path) as db:
                db.executemany("INSERT INTO klines VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    [("SYNTH_A", "1m", i, "1", "2", "0.5", "1", "1") for i in range(2000)])
            for timestamp in range(2000, 2005):
                await storage.save_kline(kline(timestamp))
        assert [row[0] for row in await storage.get_klines("SYNTH_A", "1m", 3000)] == list(range(2005))
    finally:
        await storage.close()


@pytest.mark.parametrize("retention", [True, False, 0, -1, 1.5, "2000"])
def test_sqlite_retention_requires_positive_integer_or_explicit_none(retention):
    with pytest.raises(ValueError):
        SQLiteStorage(":memory:", retention=retention)


@pytest.mark.asyncio
async def test_sqlite_memory_cancellation_rolls_back_pending_real_delete_and_recovers():
    import threading
    storage = SQLiteStorage(":memory:", retention=1)
    entered, release = threading.Event(), threading.Event()
    task = None
    def pause():
        entered.set()
        release.wait(5)
        return 0
    try:
        await storage.init()
        await storage.save_kline(kline(0))
        await storage._memory_db.create_function("synthetic_pause", 0, pause)
        await storage._memory_db.execute("CREATE TRIGGER pause_retention BEFORE DELETE ON klines BEGIN SELECT synthetic_pause(); END")
        task = asyncio.create_task(storage.save_kline(kline(60000)))
        assert await asyncio.to_thread(entered.wait, 3), "Real SQLite DELETE never entered the cancellation barrier"
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert [row[0] for row in await storage.get_klines("SYNTH_A", "1m")] == [0]
        await storage._memory_db.execute("DROP TRIGGER pause_retention")
        await storage.save_kline(kline(120000))
        assert [row[0] for row in await storage.get_klines("SYNTH_A", "1m")] == [120000]
    finally:
        release.set()
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await storage.close()
