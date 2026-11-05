"""Extended-check diagnostic failures use RAM transports and report intercepts."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


ROOT = Path(__file__).resolve().parents[1]
SECRET = "SYNTHETIC-private-diagnostic"


def load():
    spec = importlib.util.spec_from_file_location("extended_boundary", ROOT / "scripts_sdk/live_extended.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Subscription:
    async def __anext__(self): return {}
    async def close(self): pass


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["subscribe", "sub_close", "resume", "resume_false", "public_enter", "public_exit", "account_enter", "account_exit", "raw_status"])
async def test_setup_acquisition_and_cleanup_failures_still_emit_sanitized_report(monkeypatch, capsys, failure):
    module = load()
    reports = []
    calls = []
    class Failure(RuntimeError):
        status = SECRET
    class Sub(Subscription):
        async def close(self):
            if failure == "sub_close": raise Failure(SECRET)
    class Client:
        def __init__(self, **kwargs):
            self.account = "auth" in kwargs
            ok = AsyncMock(return_value={})
            self.site = SimpleNamespace(**{name: ok for name in ["get_coins", "get_currencies", "get_advertisements", "get_news_posts"]})
            self.get_withdrawal_networks = self.get_orderbook_snapshot = self.fetch_klines = ok
            self.get_balance = self.refresh = ok
            self.p2p = SimpleNamespace(get_accounts=ok)
            self.account_streams = SimpleNamespace(subscribe_balances=ok, subscribe_orders=ok)
            if failure == "raw_status": self.site.get_coins = AsyncMock(side_effect=Failure(SECRET))
        async def subscribe_orderbook(self, *args):
            if failure == "subscribe": raise Failure(SECRET)
            return Sub()
        async def resume_session(self):
            calls.append("resume")
            if failure == "resume": raise Failure(SECRET)
            return failure != "resume_false"
        async def __aenter__(self):
            if failure == ("account_enter" if self.account else "public_enter"): raise Failure(SECRET)
            return self
        async def __aexit__(self, *args):
            calls.append("account_exit" if self.account else "public_exit")
            if failure == ("account_exit" if self.account else "public_exit"): raise Failure(SECRET)
    monkeypatch.setattr(module, "BitTeamClient", Client)
    monkeypatch.setattr(module, "SessionCache", lambda profile: object())
    monkeypatch.setattr(module, "SessionAuth", lambda **kwargs: object())
    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(Path, "write_text", lambda path, text, **kwargs: reports.append(text))
    await module.main("synthetic-profile")
    assert len(reports) == 1
    output = capsys.readouterr()
    assert SECRET not in reports[0] + output.out + output.err
    report = json.loads(reports[0])
    failed = [row for group in ("public", "account") for row in report[group] if not row["ok"]]
    assert failed
    assert all(row.get("status") is None for row in failed)
    if failure in {"resume", "resume_false"}:
        assert not any(row["operation"] == "refresh" for row in report["account"])
    assert "public_exit" in calls or failure == "public_enter"


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected', [(503, 503), (True, None), (SECRET, None), (None, None)])
async def test_transport_setup_exports_only_plain_integer_status(monkeypatch, status, expected):
    module = load()
    reports = []
    class Failure(RuntimeError): pass
    error = Failure(SECRET)
    error.status = status
    def client(**kwargs): raise error
    monkeypatch.setattr(module, 'BitTeamClient', client)
    monkeypatch.setattr(Path, 'mkdir', lambda *args, **kwargs: None)
    monkeypatch.setattr(Path, 'write_text', lambda path, text, **kwargs: reports.append(text))
    await module.main()
    row = json.loads(reports[0])['public'][0]
    assert not row['ok']
    assert row['status'] == expected
    assert SECRET not in reports[0]


@pytest.mark.asyncio
async def test_extended_cancellation_propagates_without_reporting_success(monkeypatch):
    import asyncio
    module = load()
    cancellation = asyncio.CancelledError('synthetic')
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): raise cancellation
        async def __aexit__(self, *args): raise AssertionError('enter did not complete')
    reports = []
    monkeypatch.setattr(module, 'BitTeamClient', Client)
    monkeypatch.setattr(Path, 'write_text', lambda *args, **kwargs: reports.append(args))
    with pytest.raises(asyncio.CancelledError) as error:
        await module.main()
    assert error.value is cancellation
    assert not reports
