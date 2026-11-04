"""Independent facade cleanup boundaries and example contracts; all calls fake."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import BitTeamClient, SessionAuth, AuthState


def ready_auth():
    auth = SessionAuth()
    auth.state, auth._access = AuthState.READY, "synthetic-access"
    return auth


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["logout", "clear_session"])
@pytest.mark.parametrize("boundary", ["owner_replaced", "new_epoch"])
async def test_private_cleanup_facade_does_not_target_session_changed_during_stream_close(method, boundary):
    original = ready_auth()
    client = BitTeamClient(auth=original)
    replacement = ready_auth()
    old_cleanup, new_cleanup = AsyncMock(), AsyncMock()
    setattr(original, method, old_cleanup)
    setattr(replacement, method, new_cleanup)
    async def close_stream():
        if boundary == "owner_replaced":
            client.rest.auth = replacement
        else:
            original._lifecycle += 1
    client._account_streams = SimpleNamespace(close=AsyncMock(side_effect=close_stream))
    try:
        with pytest.raises(asyncio.CancelledError):
            await getattr(client, method)()
        old_cleanup.assert_not_awaited()
        new_cleanup.assert_not_awaited()
    finally:
        client._account_streams = None
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["logout", "clear_session"])
async def test_private_cleanup_allows_same_session_token_refresh_while_closing_stream(method):
    auth = ready_auth()
    client = BitTeamClient(auth=auth)
    cleanup = AsyncMock()
    setattr(auth, method, cleanup)
    async def refresh_generation():
        auth._generation += 1
    client._account_streams = SimpleNamespace(close=AsyncMock(side_effect=refresh_generation))
    try:
        await getattr(client, method)()
        cleanup.assert_awaited_once_with()
    finally:
        client._account_streams = None
        await client.close()


def test_readme_offline_examples_run_without_http(monkeypatch):
    from pathlib import Path
    import re
    import aiohttp
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError("Pure README example must not create network resources")
    monkeypatch.setattr(aiohttp, "ClientSession", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```python\n(.*?)```", readme, re.S)
    assert blocks
    for block in blocks:
        exec(compile(block, "README.md", "exec"), {})
    assert (root / "bitteam_sdk/API_REFERENCE.md").is_file()


@pytest.mark.asyncio
async def test_public_example_uses_only_public_reads_and_closes_fake_client(monkeypatch, capsys):
    from bitteam_sdk import example
    calls = []
    class PublicClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            calls.append("close")
        async def get_trading_pairs(self):
            calls.append("pairs")
            return [{"name": "DEL_USDT"}]
        async def get_ticker(self, symbol):
            calls.append("ticker")
            return {"last_price": "1", "bid": None, "ask": None}
        async def get_klines(self, symbol, interval):
            calls.append("candles")
            return []
    monkeypatch.setattr(example, "BitTeamClient", PublicClient)
    await example.main()
    assert calls == ["pairs", "ticker", "candles", "close"]
    assert "Candles in the last day: 0" in capsys.readouterr().out


def test_plot_facade_forwards_explicit_headless_option_and_returns_chart(monkeypatch):
    import sys
    chart = object()
    frame = object()
    received = []
    def plot(value, title, *, show):
        received.append((value, title, show))
        return chart
    monkeypatch.setitem(sys.modules, "bitteam_sdk.charting", SimpleNamespace(plot_candles=plot))
    assert BitTeamClient.plot_klines(frame, "Synthetic", show=False) is chart
    assert BitTeamClient.plot_klines(frame) is chart
    assert received == [(frame, "Synthetic", False), (frame, "BitTeam", True)]


@pytest.mark.asyncio
@pytest.mark.parametrize("pair,book", [
    ({"lastPrice": ""}, {"bids": [], "asks": []}),
    ({"lastPrice": False}, {"bids": [], "asks": []}),
    ({"lastPrice": "NaN"}, {"bids": [], "asks": []}),
    ({"lastPrice": "Infinity"}, {"bids": [], "asks": []}),
    ({"lastPrice": "1"}, {"bids": ["12.5"], "asks": []}),
    ({"lastPrice": "1"}, {"bids": [["NaN", "2"]], "asks": []}),
])
async def test_ticker_does_not_invent_price_from_missing_or_malformed_public_data(pair, book):
    from bitteam_sdk import BitTeamAPIError
    client = BitTeamClient()
    client.get_trading_pair_info = AsyncMock(return_value=pair)
    client.get_orderbook = AsyncMock(return_value=book)
    try:
        with pytest.raises(BitTeamAPIError):
            await client.get_ticker("DEL_USDT")
        assert client.rest._session is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_ticker_preserves_known_zero_and_unknown_bid_ask_without_fabrication():
    from decimal import Decimal
    client = BitTeamClient()
    client.get_trading_pair_info = AsyncMock(return_value={"lastPrice": 0})
    client.get_orderbook = AsyncMock(return_value={"bids": [], "asks": []})
    try:
        ticker = await client.get_ticker("DEL_USDT")
        assert ticker["last_price"] == Decimal(0)
        assert ticker["bid"] is None and ticker["ask"] is None
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("pair", [{}, {"lastPrice": None}])
async def test_missing_ticker_last_price_stays_unknown_instead_of_zero(pair):
    client = BitTeamClient()
    client.get_trading_pair_info = AsyncMock(return_value=pair)
    client.get_orderbook = AsyncMock(return_value={"bids": [], "asks": []})
    try:
        assert (await client.get_ticker("DEL_USDT"))["last_price"] is None
    finally:
        await client.close()
