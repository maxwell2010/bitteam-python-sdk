"""Real SQLite in synthetic temporary files with controlled worker timing."""
import asyncio
from pathlib import Path
import sqlite3
import threading

import pytest

from bitteam_sdk.orderbook import MarketDataRecorder


@pytest.mark.parametrize('path', [':memory:', Path(':memory:')])
def test_recorder_rejects_memory_before_sqlite_io(monkeypatch, path):
    def unexpected(*args, **kwargs):
        raise AssertionError('No SQLite I/O is allowed')
    monkeypatch.setattr(sqlite3, 'connect', unexpected)
    with pytest.raises(ValueError, match='file-backed'):
        MarketDataRecorder(path)


@pytest.mark.parametrize('close_error', [False, True])
def test_failed_real_schema_init_closes_connection_preserving_sql_error(tmp_path, monkeypatch, close_error):
    path = tmp_path / 'synthetic.db'
    original = sqlite3.connect
    with original(path) as db:
        db.execute('CREATE TABLE observations(id INTEGER)')
    closed = []
    class Connection(sqlite3.Connection):
        def close(self):
            super().close()
            closed.append(True)
            if close_error:
                raise OSError('synthetic secondary close failure')
    monkeypatch.setattr(sqlite3, 'connect', lambda *args, **kwargs: original(*args, **kwargs, factory=Connection))
    with pytest.raises(sqlite3.OperationalError, match='no such column'):
        MarketDataRecorder(path)._connection()
    assert closed == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['insert', 'read'])
@pytest.mark.parametrize('sql_failure', [False, True])
async def test_cancelled_worker_is_drained_under_lock(tmp_path, monkeypatch, operation, sql_failure):
    recorder = MarketDataRecorder(tmp_path / 'synthetic.db')
    original = sqlite3.connect
    connection = recorder._connection()
    if operation == 'insert' and sql_failure:
        connection.execute("CREATE TRIGGER reject_insert BEFORE INSERT ON observations BEGIN SELECT RAISE(ABORT,'synthetic SQL failure'); END")
    connection.close()
    entered, release = threading.Event(), threading.Event()
    closed = []
    class Connection(sqlite3.Connection):
        def execute(self, sql, *args):
            selected = sql.startswith('INSERT INTO') if operation == 'insert' else sql.startswith('SELECT received_at_ms')
            if selected:
                entered.set()
                if not release.wait(5):
                    raise AssertionError('Synthetic worker was not released')
                if operation == 'read' and sql_failure:
                    return super().execute('SELECT nonexistent_column FROM observations')
            return super().execute(sql, *args)
        def close(self):
            super().close()
            closed.append(True)
    monkeypatch.setattr(sqlite3, 'connect', lambda *args, **kwargs: original(*args, **kwargs, factory=Connection))
    task = asyncio.create_task(recorder._insert('BTC_USDT', 'synthetic', 0, {}) if operation == 'insert' else recorder.load('BTC_USDT'))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert recorder._lock.locked()
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed == [True]
        assert not recorder._lock.locked()
        with original(recorder.path) as db:
            count = db.execute('SELECT count(*) FROM observations').fetchone()[0]
        assert count == (1 if operation == 'insert' and not sql_failure else 0)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['insert', 'read'])
@pytest.mark.parametrize('primary_failure', [False, True])
async def test_sql_or_decode_failure_wins_secondary_close_failure(tmp_path, monkeypatch, operation, primary_failure):
    import json
    recorder = MarketDataRecorder(tmp_path / 'synthetic.db')
    db = recorder._connection()
    if primary_failure and operation == 'insert':
        db.execute("CREATE TRIGGER reject_insert BEFORE INSERT ON observations BEGIN SELECT RAISE(ABORT,'synthetic SQL failure'); END")
    if primary_failure and operation == 'read':
        db.execute("INSERT INTO observations VALUES(1,'BTC_USDT','l2_snapshot',0,'malformed JSON')")
        db.commit()
    db.close()
    original = sqlite3.connect
    closed = []
    class Connection(sqlite3.Connection):
        def close(self):
            super().close()
            closed.append(True)
            raise OSError('synthetic secondary close failure')
    monkeypatch.setattr(sqlite3, 'connect', lambda *args, **kwargs: original(*args, **kwargs, factory=Connection))
    expected = (sqlite3.IntegrityError if operation == 'insert' else json.JSONDecodeError) if primary_failure else OSError
    with pytest.raises(expected):
        if operation == 'insert':
            await recorder._insert('BTC_USDT', 'synthetic', 0, {})
        else:
            await recorder.load('BTC_USDT')
    assert closed == [True]
