"""Offline diagnostic boundaries; no files, credentials or services required."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import BitTeamAPIError

ROOT = Path(__file__).resolve().parents[1]
SECRET = 'SYNTHETIC-password-cookie-OTP-token-DO-NOT-EXPORT'


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts_sdk' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code', [(503, SECRET), (SECRET, 422), (True, False), (503, 401001)])
async def test_public_report_only_exports_integer_error_metadata(monkeypatch, capsys, status, code):
    module = load('live_public')
    error = BitTeamAPIError(status, code)
    fail = AsyncMock(side_effect=error)

    class Client:
        api = SimpleNamespace(**{name: fail for name in (
            'get_asset', 'get_stats', 'get_currencies', 'get_pairs', 'get_ccxt_pairs',
            'get_rates', 'get_orders', 'get_trades', 'get_cmc_assets', 'get_cmc_summary',
            'get_cmc_ticker', 'get_cmc_orderbook_by_pair', 'get_cmc_trades_by_pair',
            'get_orderbooks_by_symbol', 'get_pair_by_name', 'get_pairs_precisions', 'get_markdown_menu')})
        rest = SimpleNamespace(_send=fail, base_url='https://synthetic.invalid')
        history = SimpleNamespace(get_config=fail, get_server_time=fail, get_symbol=fail)
        get_klines = get_candles_from_trades = subscribe_kline = fail
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None

    reports = []
    monkeypatch.setattr(module, 'BitTeamClient', lambda **kwargs: Client())
    monkeypatch.setattr(Path, 'write_text', lambda self, text, **kwargs: reports.append(text))
    await module.main()
    assert SECRET not in reports[0] + capsys.readouterr().out
    entries = json.loads(reports[0])['rest']
    assert all(row['http_status'] == (status if type(status) is int else None) for row in entries)
    assert all(row['code'] == (code if type(code) is int else None) for row in entries)


@pytest.mark.parametrize('stage', ['connect', 'schema', 'init', 'drop', 'close'])
def test_storage_cli_sanitizes_setup_and_cleanup_failures(monkeypatch, capsys, stage):
    events = []
    async def execute(sql):
        events.append(sql.split()[0])
        if stage == 'schema' and sql.startswith('CREATE') or stage == 'drop' and sql.startswith('DROP'):
            raise RuntimeError(SECRET)
    async def close_admin():
        events.append('admin.close')
        if stage == 'close': raise RuntimeError(SECRET)
    admin = SimpleNamespace(execute=execute, close=close_admin,
                            fetchval=AsyncMock(return_value='synthetic-version'))
    async def connect(*args, **kwargs):
        if stage == 'connect': raise RuntimeError(SECRET)
        return admin
    class Store:
        def __init__(self, *args): pass
        async def init(self):
            if stage == 'init': raise RuntimeError(SECRET)
        async def close(self): events.append('store.close')
    # Both dependencies must be fake BEFORE importing the standalone script.
    # The normal SDK matrix intentionally does not install optional asyncpg.
    monkeypatch.setitem(sys.modules, 'asyncpg', SimpleNamespace(connect=connect, __version__='synthetic'))
    monkeypatch.setitem(sys.modules, 'bitteam_sdk.storage.postgres', SimpleNamespace(PostgresStorage=Store))
    module = load('check_storage_runtime')
    for name in vars(module).copy():
        if name.startswith('check_'): monkeypatch.setattr(module, name, AsyncMock())
    monkeypatch.setattr(sys, 'argv', ['check_storage_runtime.py', '--postgres-dsn', 'postgresql://synthetic:synthetic@localhost/test'])
    try:
        module.main()
    except BaseException as error:
        rendered = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        assert isinstance(error, SystemExit) and error.code == 1
        assert SECRET not in rendered
    else:
        pytest.fail('Failed runtime check must exit unsuccessfully')
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
    if stage != 'connect':
        assert 'store.close' in events and 'DROP' in events and 'admin.close' in events

@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['request', 'json'])
@pytest.mark.parametrize('kind', ['connection', 'timeout'])
async def test_rest_transport_errors_hide_driver_details(stage, kind):
    import aiohttp
    from bitteam_sdk.rest import BitTeamRestAPI
    error = aiohttp.ClientConnectionError(SECRET) if kind == 'connection' else asyncio.TimeoutError(SECRET)
    class Response:
        status = 200
        headers = {}
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def json(self): raise error
    class Session:
        def request(self, *args, **kwargs):
            if stage == 'request': raise error
            return Response()
    rest = BitTeamRestAPI()
    rest._get_session = AsyncMock(return_value=Session())
    with pytest.raises(BitTeamAPIError if kind == 'connection' else asyncio.TimeoutError) as caught:
        await rest._request('GET', '/synthetic', public=True)
    assert SECRET not in str(caught.value) + repr(caught.value)
    assert SECRET not in ''.join(traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__))
    assert rest._get_session.await_count == 1


def test_session_cli_hides_cache_provider_failure(monkeypatch, capsys):
    import runpy
    import bitteam_sdk
    def cache(*args, **kwargs): raise RuntimeError(SECRET)
    monkeypatch.setattr(bitteam_sdk, 'SessionCache', cache)
    monkeypatch.setattr(sys, 'argv', ['session_cli', 'status'])
    try:
        runpy.run_module('bitteam_sdk.session_cli', run_name='__main__')
    except BaseException as error:
        assert isinstance(error, SystemExit) and error.code == 1
        assert SECRET not in ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    else:
        pytest.fail('Cache failure must exit unsuccessfully')
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
