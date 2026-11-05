import plotly.graph_objects as go
import pandas as pd

def plot_candles(df: pd.DataFrame, title: str = "Candlestick Chart", *, show: bool = True):
    """Build a Plotly figure; use show=False for headless JSON/HTML export.

    Default display behavior is preserved. Empty input produces no figure.
    This helper does not perform financial calculations or fetch market data.
    """
    if df.empty:
        print("Нет данных для отображения")
        return
    fig = go.Figure(data=go.Candlestick(
        x=df.index,
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close']
    ))
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False
    )
    if show:
        fig.show()
    return fig
