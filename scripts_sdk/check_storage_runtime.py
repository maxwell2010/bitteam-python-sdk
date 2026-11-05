"""Opt-in real PostgreSQL storage checks against an explicit isolated local server.

No mocks or default-suite skips. Creates a random schema, uses only synthetic
candles, and drops only that schema. Example (synthetic local service):
python scripts_sdk/check_storage_runtime.py --postgres-dsn postgresql://postgres:postgres@127.0.0.1:5432/postgres
Never use a production database or a real credential for this check.
"""
import argparse
import asyncio
from pathlib import Path
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bitteam_sdk.models import Kline
from bitteam_sdk.storage.postgres import PostgresStorage


def candle(timestamp, *, symbol="SYNTH_A", interval="1m", close="1.000000000000000001"):
    return Kline(symbol, interval, timestamp, "1", "2", "0.5", close, "0.000000000000000001")


def local_dsn(value, schema, tag):
    url = urlsplit(value)
    if url.scheme not in ("postgres", "postgresql") or url.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Runtime checks require an explicit loopback PostgreSQL DSN")
    query = dict(parse_qsl(url.query))
    # All SDK tables live inside one random schema, even if the caller has a
    # different default search path. Do not inspect or modify existing tables.
    query.update(search_path=schema, application_name=tag)
    return urlunsplit(url._replace(query=urlencode(query)))


def runtime_tag(store, suffix=""):
    return dict(parse_qsl(urlsplit(store.dsn).query))["application_name"] + suffix


async def check_data_contract(store, admin, schema):
    for timestamp in (120000, 0, 60000):
        await store.save_kline(candle(timestamp))
    await store.save_kline(candle(60000, close="1.999999999999999999"))
    await store.save_kline(candle(0, symbol="SYNTH_B"))
    await store.save_kline(candle(0, interval="5m"))
    rows = await store.get_klines("SYNTH_A", "1m", 2)
    assert [row[0] for row in rows] == [60000, 120000], "Latest window is not chronological"
    assert rows[0][4:] == ("1.999999999999999999", "0.000000000000000001"), "Decimal strings changed"
    assert len(await store.get_klines("SYNTH_A", "1m")) == 3, "Upsert duplicated a key"
    assert len(await store.get_klines("SYNTH_B", "1m")) == 1, "Symbol isolation failed"
    assert len(await store.get_klines("SYNTH_A", "5m")) == 1, "Interval isolation failed"
    await admin.execute(f'TRUNCATE "{schema}".klines')
    await admin.execute(f'''INSERT INTO "{schema}".klines
        (symbol, interval, open_time, open_price, high_price, low_price, close_price, volume)
        SELECT 'SYNTH_A', '1m', i, '1','2','0.5','1','1' FROM generate_series(0,1999) i''')
    await store.save_kline(candle(2000))
    assert [row[0] for row in await store.get_klines("SYNTH_A", "1m", 3000)] == list(range(1, 2001)), "Retention is not latest 2000"


async def check_invalid_limits(store, admin, schema):
    for limit in (True, False, 0, -1, 1.5, None, "1"):
        try:
            await store.get_klines("SYNTH_A", "1m", limit)
        except ValueError:
            continue
        raise AssertionError("Invalid limit was accepted or produced a backend-specific error")


async def check_atomic_retention_error(store, admin, schema):
    import asyncpg
    await admin.execute(f'''CREATE FUNCTION "{schema}".fail_retention() RETURNS trigger
        LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'synthetic retention failure'; END$$''')
    await admin.execute(f'''CREATE TRIGGER fail_retention BEFORE DELETE ON "{schema}".klines
        FOR EACH STATEMENT EXECUTE FUNCTION "{schema}".fail_retention()''')
    try:
        try:
            await store.save_kline(candle(9000000, symbol="SYNTH_FAILURE"))
        except asyncpg.RaiseError:
            pass
        else:
            raise AssertionError("Synthetic server retention failure did not propagate")
        assert await store.get_klines("SYNTH_FAILURE", "1m") == [], "INSERT committed despite failed retention"
    finally:
        await admin.execute(f'DROP TRIGGER fail_retention ON "{schema}".klines')
        await admin.execute(f'DROP FUNCTION "{schema}".fail_retention()')


async def check_atomic_retention_cancellation(store, admin, schema):
    await admin.execute(f'''CREATE FUNCTION "{schema}".pause_retention() RETURNS trigger
        LANGUAGE plpgsql AS $$BEGIN PERFORM pg_sleep(30); RETURN NULL; END$$''')
    await admin.execute(f'''CREATE TRIGGER pause_retention BEFORE DELETE ON "{schema}".klines
        FOR EACH STATEMENT EXECUTE FUNCTION "{schema}".pause_retention()''')
    task = asyncio.create_task(store.save_kline(candle(9000001, symbol="SYNTH_CANCEL")))
    try:
        deadline = asyncio.get_running_loop().time() + 5
        while not await admin.fetchval("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name=$1 AND wait_event='PgSleep')", runtime_tag(store)):
            if task.done():
                await task
                raise AssertionError("Write completed without entering server retention wait")
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError("Server retention cancellation point was not reached")
            await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Write cancellation did not propagate")
        assert await store.get_klines("SYNTH_CANCEL", "1m") == [], "Cancelled retention left a committed INSERT"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await admin.execute(f'DROP TRIGGER pause_retention ON "{schema}".klines')
        await admin.execute(f'DROP FUNCTION "{schema}".pause_retention()')
    # A canceled real server operation must release/reset its pooled connection.
    await store.save_kline(candle(9000002, symbol="SYNTH_RECOVERY"))
    assert len(await store.get_klines("SYNTH_RECOVERY", "1m")) == 1


async def check_repeated_init(store, admin, schema):
    original = store.pool
    try:
        await store.init()
        assert store.pool is original, "Repeated init replaced and leaked an existing pool"
    finally:
        if store.pool is not original:
            await original.close()


async def check_concurrent_retention(store, admin, schema):
    await admin.execute(f'''INSERT INTO "{schema}".klines
        (symbol, interval, open_time, open_price, high_price, low_price, close_price, volume)
        SELECT 'SYNTH_CONCURRENT', '1m', i, '1','2','0.5','1','1' FROM generate_series(0,1998) i''')
    # Hold each real DELETE statement after it obtains its snapshot, exposing
    # overlapping writers that would each retain their own 2000-row snapshot.
    await admin.execute(f'''CREATE FUNCTION "{schema}".slow_retention() RETURNS trigger
        LANGUAGE plpgsql AS $$BEGIN PERFORM pg_sleep(0.3); RETURN NULL; END$$''')
    await admin.execute(f'''CREATE TRIGGER slow_retention BEFORE DELETE ON "{schema}".klines
        FOR EACH STATEMENT EXECUTE FUNCTION "{schema}".slow_retention()''')
    try:
        await asyncio.gather(store.save_kline(candle(1999, symbol="SYNTH_CONCURRENT")),
                             store.save_kline(candle(2000, symbol="SYNTH_CONCURRENT")))
        rows = await store.get_klines("SYNTH_CONCURRENT", "1m", 3000)
        assert [row[0] for row in rows] == list(range(1, 2001)), "Concurrent writers exceeded rolling retention or lost newest data"
    finally:
        await admin.execute(f'DROP TRIGGER slow_retention ON "{schema}".klines')
        await admin.execute(f'DROP FUNCTION "{schema}".slow_retention()')


async def check_two_pool_retention_one(store, admin, schema):
    """Real separate pools, controlled SQL lock timing, no production hooks."""
    first = PostgresStorage(local_dsn(store.dsn, schema, runtime_tag(store, "_poolA")), retention=1)
    second = PostgresStorage(local_dsn(store.dsn, schema, runtime_tag(store, "_poolB")), retention=1)
    symbol, interval = "SYNTH_DUAL_POOL", "1m"
    pending = []
    locked = False

    async def wait_until_blocked(task, tag):
        deadline = asyncio.get_running_loop().time() + 5
        while not await admin.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name=$1 AND wait_event='advisory')", tag):
            if task.done():
                await task
                raise AssertionError("Writer bypassed the real same-key advisory lock")
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError("Writer did not reach the real advisory lock barrier")
            await asyncio.sleep(0.01)

    try:
        await first.init()
        await second.init()
        assert first.pool is not second.pool, "The scenario requires two independent actual pools"
        await admin.execute("SELECT pg_advisory_lock(hashtext($1), hashtext($2))", symbol, interval)
        locked = True
        pending.append(asyncio.create_task(first.save_kline(candle(1, symbol=symbol, interval=interval))))
        await wait_until_blocked(pending[0], runtime_tag(first))
        pending.append(asyncio.create_task(second.save_kline(candle(2, symbol=symbol, interval=interval))))
        await wait_until_blocked(pending[1], runtime_tag(second))
        assert await first.get_klines(symbol, interval) == [], "A blocked writer changed committed data"
        # Both same-series writers remain blocked while other exact keys use
        # another actual connection from pool B and finish independently.
        await asyncio.wait_for(second.save_kline(candle(1, symbol="SYNTH_DUAL_OTHER", interval=interval)), 3)
        await asyncio.wait_for(second.save_kline(candle(1, symbol=symbol, interval="5m")), 3)
        assert all(not task.done() for task in pending), "Same-key barrier was released unexpectedly"
        await admin.execute("SELECT pg_advisory_unlock(hashtext($1), hashtext($2))", symbol, interval)
        locked = False
        await asyncio.wait_for(asyncio.gather(*pending), 5)
        assert [row[0] for row in await first.get_klines(symbol, interval)] == [2], "Separate pools exceeded retention=1 or lost latest data"
        assert [row[0] for row in await second.get_klines("SYNTH_DUAL_OTHER", interval)] == [1]
        assert [row[0] for row in await second.get_klines(symbol, "5m")] == [1]
        # Cancellation while waiting on another owner's same-key lock must
        # release that pool connection without affecting the committed candle.
        await admin.execute("SELECT pg_advisory_lock(hashtext($1), hashtext($2))", symbol, interval)
        locked = True
        cancelled = asyncio.create_task(first.save_kline(candle(3, symbol=symbol, interval=interval)))
        pending.append(cancelled)
        await wait_until_blocked(cancelled, runtime_tag(first))
        cancelled.cancel()
        try:
            await cancelled
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Same-key waiting writer cancellation did not propagate")
        assert [row[0] for row in await second.get_klines(symbol, interval)] == [2]
        await admin.execute("SELECT pg_advisory_unlock(hashtext($1), hashtext($2))", symbol, interval)
        locked = False
        await first.save_kline(candle(4, symbol=symbol, interval=interval))
        assert [row[0] for row in await second.get_klines(symbol, interval)] == [4], "Canceled writer prevented a fresh write from the same pool"
    finally:
        if locked:
            await admin.execute("SELECT pg_advisory_unlock(hashtext($1), hashtext($2))", symbol, interval)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        try:
            await first.close()
        finally:
            await second.close()


async def check_full_history_retention(store, admin, schema):
    for invalid in (True, False, 0, -1, 1.5, "2000"):
        try:
            PostgresStorage(store.dsn, retention=invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid retention policy was accepted")
    full = PostgresStorage(store.dsn, retention=None)
    try:
        await full.init()
        await admin.execute(f'''INSERT INTO "{schema}".klines
            (symbol, interval, open_time, open_price, high_price, low_price, close_price, volume)
            SELECT 'SYNTH_FULL', '1m', i, '1','2','0.5','1','1' FROM generate_series(0,1999) i''')
        for timestamp in range(2000, 2005):
            await full.save_kline(candle(timestamp, symbol="SYNTH_FULL"))
        assert [row[0] for row in await full.get_klines("SYNTH_FULL", "1m", 3000)] == list(range(2005)), "Full-history policy unexpectedly pruned data"
    finally:
        await full.close()


async def check_schema_init_failure(store, admin, schema):
    import asyncpg
    failed_dsn = local_dsn(store.dsn, schema + "_missing", runtime_tag(store, "_failed"))
    failed = PostgresStorage(failed_dsn)
    try:
        try:
            await failed.init()
        except asyncpg.InvalidSchemaNameError:
            pass
        else:
            raise AssertionError("Missing-schema init unexpectedly succeeded")
        assert failed.pool is None, "Failed initialization retained a live pool"
        assert await admin.fetchval("SELECT count(*) FROM pg_stat_activity WHERE application_name=$1", runtime_tag(store, "_failed")) == 0, "Failed initialization leaked server connections"
    finally:
        await failed.close()


async def check_cancelled_init(store, admin, schema):
    initializing = PostgresStorage(local_dsn(store.dsn, schema, runtime_tag(store, "_init")))
    task = None
    await admin.execute("BEGIN")
    try:
        await admin.execute(f'LOCK TABLE "{schema}".klines IN ACCESS EXCLUSIVE MODE')
        task = asyncio.create_task(initializing.init())
        deadline = asyncio.get_running_loop().time() + 5
        while True:
            # pg_stat snapshots are cached inside our explicit lock transaction.
            await admin.execute("SELECT pg_stat_clear_snapshot()")
            if await admin.fetchval("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name=$1 AND wait_event_type='Lock')", runtime_tag(store, "_init")):
                break
            if task.done():
                await task
                raise AssertionError("Initialization did not wait for the real schema lock")
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError("Initialization lock barrier was not reached")
            await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Initialization cancellation did not propagate")
        assert initializing.pool is None, "Cancelled initialization retained a usable pool"
        await admin.execute("SELECT pg_stat_clear_snapshot()")
        assert await admin.fetchval("SELECT count(*) FROM pg_stat_activity WHERE application_name=$1", runtime_tag(store, "_init")) == 0, "Cancelled initialization leaked server connections"
    finally:
        await admin.execute("ROLLBACK")
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await initializing.close()


async def check_close_lifecycle(store, admin, schema):
    await store.close()
    await store.close()
    assert store.pool is None, "Closed storage retains a closed pool as usable state"
    try:
        await store.get_klines("SYNTH_A", "1m")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Read after close must fail with a clear lifecycle error")


async def check_cancelled_close(store, admin, schema):
    closing = PostgresStorage(local_dsn(store.dsn, schema, runtime_tag(store, "_close")))
    task, pool, borrowed = None, None, None
    try:
        await closing.init()
        pool = closing.pool
        borrowed = await pool.acquire()
        task = asyncio.create_task(closing.close())
        while not pool.is_closing():
            if task.done():
                await task
                raise AssertionError("Close did not wait for its borrowed connection")
            await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Close cancellation did not propagate")
        # asyncpg's real Pool.close terminates connections when canceled. Verify
        # the actual server result rather than assuming a lost cleanup task.
        assert closing.pool is None
        deadline = asyncio.get_running_loop().time() + 3
        while await admin.fetchval("SELECT count(*) FROM pg_stat_activity WHERE application_name=$1", runtime_tag(store, "_close")):
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError("Cancelled close leaked server connections")
            await asyncio.sleep(0.01)
        await closing.close()
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if borrowed is not None:
            await pool.release(borrowed)
        await closing.close()


async def run(dsn):
    import asyncpg
    schema = "bitteam_storage_review_" + uuid.uuid4().hex
    scoped_dsn = local_dsn(dsn, schema, "btsdk_" + uuid.uuid4().hex)
    admin = await asyncpg.connect(dsn, timeout=10)
    store = PostgresStorage(scoped_dsn)
    failures = []
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        await store.init()
        print("PostgreSQL " + await admin.fetchval("SHOW server_version") + "; asyncpg " + asyncpg.__version__)
        for check in (check_data_contract, check_invalid_limits, check_atomic_retention_error,
                      check_atomic_retention_cancellation, check_repeated_init, check_concurrent_retention,
                      check_two_pool_retention_one,
                      check_full_history_retention, check_schema_init_failure,
                      check_cancelled_init, check_cancelled_close, check_close_lifecycle):
            try:
                await check(store, admin, schema)
            except Exception as error:
                failures.append(check.__name__)
                # Print only our fixed check name and error type, never DSN or
                # driver error strings that may include credentials/query data.
                print("FAIL " + check.__name__ + " (" + type(error).__name__ + ")")
            else:
                print("PASS " + check.__name__)
    finally:
        try:
            await store.close()
        finally:
            try:
                await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            finally:
                await admin.close()
    if failures:
        raise SystemExit("PostgreSQL runtime checks failed: " + ", ".join(failures))
    print("12 PostgreSQL runtime checks passed; isolated schema removed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-dsn", required=True, help="Explicit synthetic loopback PostgreSQL service only")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.postgres_dsn))
    except Exception:
        # Setup and cleanup failures occur outside the individual checks too.
        # Never let driver messages/DSNs escape through a CLI traceback.
        print("PostgreSQL runtime checks failed during setup or cleanup.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
