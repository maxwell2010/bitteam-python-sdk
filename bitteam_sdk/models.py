from dataclasses import dataclass

@dataclass
class Precision:
    price: int
    amount: int

@dataclass
class Kline:
    symbol: str
    interval: str
    open_time: int
    open: str
    high: str
    low: str
    close: str
    volume: str

    @staticmethod
    def to_dataframe(rows: list):
        import pandas as pd
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume"])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])
        df.set_index("open_time", inplace=True)
        return df
