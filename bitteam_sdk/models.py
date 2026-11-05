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
        """Convert rows/Kline objects to numeric OHLCV indexed by epoch time.

        The index retains the historical timezone-naive UTC representation.
        Numeric conversion is for analysis/plotting and can round decimal text
        to floating point; retain Kline/storage strings for exact money values.
        Input order and duplicate timestamps are preserved, not reconciled.
        """
        import pandas as pd
        df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume"])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])
        return df.set_index("open_time")
