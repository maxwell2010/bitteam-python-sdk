import plotly.graph_objects as go
import pandas as pd

def plot_candles(df: pd.DataFrame, title: str = "Candlestick Chart"):
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
    fig.show()