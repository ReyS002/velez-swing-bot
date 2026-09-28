from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any

from PySide6 import QtCore

from ..backtest.engine import BacktestEngine, BacktestResult
from ..core.data import YFinanceDataProvider, CSVDataProvider, FuturesStubProvider


@dataclass
class BacktestRequest:
    config: Dict[str, Any]
    symbols: List[Dict[str, Any]]
    start: datetime
    end: datetime
    timeframe: str


class BacktestWorker(QtCore.QThread):
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, request: BacktestRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        try:
            engine = BacktestEngine(self.request.config)
            result: BacktestResult = engine.run(
                self.request.symbols,
                self.request.start,
                self.request.end,
                self.request.timeframe,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


@dataclass
class ChartRequest:
    symbol_cfg: Dict[str, Any]
    start: datetime
    end: datetime
    timeframe: str
    timezone: str


class ChartWorker(QtCore.QThread):
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, request: ChartRequest) -> None:
        super().__init__()
        self.request = request

    def _provider(self):
        source = self.request.symbol_cfg.get("data_source", "yfinance")
        if source == "yfinance":
            return YFinanceDataProvider()
        if source == "csv":
            return CSVDataProvider(self.request.symbol_cfg["csv_path"])
        return FuturesStubProvider()

    def run(self) -> None:
        try:
            provider = self._provider()
            df = provider.get_bars(
                symbol=self.request.symbol_cfg["symbol"],
                start=self.request.start,
                end=self.request.end,
                timeframe=self.request.timeframe,
                timezone=self.request.timezone,
            )
            self.finished.emit(df)
        except Exception as exc:
            self.failed.emit(str(exc))
