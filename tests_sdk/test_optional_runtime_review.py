"""Real pandas/Plotly over synthetic candles; no browser, HTTP or account data."""
from copy import deepcopy
from unittest.mock import Mock

import pandas as pd
import plotly.graph_objects as go
import pytest

from bitteam_sdk.charting import plot_candles
from bitteam_sdk.models import Kline


def rows():
    return [[0, "1.125", "2.5", "0.5", "1.75", "3.125"],
            [60000, "1.75", "3", "1.5", "2.25", "4"]]


def test_empty_frame_has_same_ohlcv_schema_and_datetime_index_as_nonempty():
    empty = Kline.to_dataframe([])
    populated = Kline.to_dataframe(rows())
    assert list(empty.columns) == list(populated.columns)
    assert isinstance(empty.index, pd.DatetimeIndex)
    assert empty.index.name == populated.index.name == "open_time"
    assert empty.index.tz == populated.index.tz


@pytest.mark.parametrize("kind", ["storage_rows", "klines"])
def test_dataframe_accepts_real_storage_rows_and_kline_objects(kind):
    source = rows() if kind == "storage_rows" else [
        Kline("SYNTH_USDT", "1m", *row) for row in rows()]
    before = deepcopy(source)
    frame = Kline.to_dataframe(source)
    assert frame.index.tolist() == [pd.Timestamp("1970-01-01"), pd.Timestamp("1970-01-01 00:01")]
    assert frame["close"].tolist() == [1.75, 2.25]
    assert frame["volume"].sum() == 7.125
    assert source == before


def test_dataframe_preserves_input_order_and_duplicate_timestamp_rows():
    source = [rows()[1], rows()[0], rows()[0]]
    frame = Kline.to_dataframe(source)
    assert frame.index.tolist() == [pd.Timestamp("1970-01-01 00:01"),
                                  pd.Timestamp("1970-01-01"), pd.Timestamp("1970-01-01")]
    assert len(frame) == 3


def test_real_plotly_headless_figure_serializes_without_showing_or_mutating_input(monkeypatch, tmp_path):
    show = Mock(side_effect=AssertionError("Headless mode must not open a browser"))
    monkeypatch.setattr(go.Figure, "show", show)
    frame = Kline.to_dataframe(rows())
    before = frame.copy(deep=True)
    figure = plot_candles(frame, "Synthetic runtime figure", show=False)
    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 1 and figure.data[0].type == "candlestick"
    assert figure.data[0].close.tolist() == [1.75, 2.25]
    assert figure.layout.xaxis.rangeslider.visible is False
    assert "Synthetic runtime figure" in figure.to_json()
    destination = tmp_path / "synthetic-figure.html"
    figure.write_html(destination, include_plotlyjs=True, full_html=True)
    assert destination.stat().st_size > 1000
    assert "Synthetic runtime figure" in destination.read_text(encoding="utf-8")
    show.assert_not_called()
    pd.testing.assert_frame_equal(frame, before)


def test_default_plot_mode_still_displays_and_returns_figure(monkeypatch):
    shown = []
    monkeypatch.setattr(go.Figure, "show", lambda self: shown.append(self))
    figure = plot_candles(Kline.to_dataframe(rows()))
    assert isinstance(figure, go.Figure)
    assert shown == [figure]


def test_empty_plot_does_not_open_browser(monkeypatch):
    show = Mock(side_effect=AssertionError("Empty chart must not open a browser"))
    monkeypatch.setattr(go.Figure, "show", show)
    assert plot_candles(Kline.to_dataframe([]), show=False) is None
    show.assert_not_called()


@pytest.mark.asyncio
async def test_client_public_dataframe_facade_uses_real_optional_libraries(monkeypatch):
    from unittest.mock import AsyncMock
    from bitteam_sdk import BitTeamClient
    client = BitTeamClient()
    client.get_klines = AsyncMock(return_value=[Kline("SYNTH_USDT", "1m", *row) for row in rows()])
    shown = []
    monkeypatch.setattr(go.Figure, "show", lambda self: shown.append(self))
    try:
        frame = await client.get_klines_df("SYNTH_USDT")
        figure = client.plot_klines(frame)
        assert isinstance(figure, go.Figure) and shown == [figure]
        headless = client.plot_klines(frame, show=False)
        assert isinstance(headless, go.Figure)
        assert shown == [figure]
        assert "candlestick" in headless.to_json()
        assert client.rest._session is None
    finally:
        await client.close()
