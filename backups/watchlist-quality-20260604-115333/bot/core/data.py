from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Optional

import pandas as pd
import pytz


class BaseDataProvider(ABC):
    @abstractmethod
    def get_bars(
        self,
        *,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str,
        timezone: str,
    ) -> pd.DataFrame:
        raise NotImplementedError


class YFinanceDataProvider(BaseDataProvider):
    def get_bars(
        self,
        *,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str,
        timezone: str,
    ) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("yfinance is required for YFinanceDataProvider") from exc

        df = yf.download(
            tickers=symbol,
            start=start,
            end=end,
            interval=timeframe,
            auto_adjust=False,
            progress=False,
        )
        if df.empty:
            return df
        df = df.rename(columns=str.lower)
        df = df.rename(columns={"adj close": "adj_close"})
        df.index = pd.to_datetime(df.index)
        tz = pytz.timezone(timezone)
        if df.index.tz is None:
            df.index = df.index.tz_localize(tz)
        df = df.reset_index().rename(columns={"index": "timestamp"})
        return df[["timestamp", "open", "high", "low", "close", "volume"]]


class CSVDataProvider(BaseDataProvider):
    def __init__(self, csv_path: str):
        self.csv_path = csv_path

    def get_bars(
        self,
        *,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str,
        timezone: str,
    ) -> pd.DataFrame:
        df = pd.read_csv(self.csv_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        tz = pytz.timezone(timezone)
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(tz)
        df = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)]
        return df[["timestamp", "open", "high", "low", "close", "volume"]]


class FuturesStubProvider(BaseDataProvider):
    def get_bars(
        self,
        *,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str,
        timezone: str,
    ) -> pd.DataFrame:
        raise NotImplementedError("Futures data provider not implemented. Use CSVDataProvider.")
