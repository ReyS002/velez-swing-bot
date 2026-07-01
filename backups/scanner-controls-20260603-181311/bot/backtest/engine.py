from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from ..core.data import YFinanceDataProvider, CSVDataProvider, FuturesStubProvider
from ..core.execution import ExecutionSimulator
from ..core.portfolio import Portfolio
from ..core.risk import RiskManager
from ..core.strategy import NarrowToWideStrategy
from ..core.types import Bar, Order, OrderType, Side, TradeRecord, Signal, DecisionTrace, Regime, NarrowWideState
from ..core.utils import get_logger, log_event
from .metrics import compute_metrics


@dataclass
class BacktestResult:
    metrics: Dict[str, float]
    trades: List[TradeRecord]
    decision_traces: List[DecisionTrace]


class BacktestEngine:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.logger = get_logger("backtest")
        self.strategy = NarrowToWideStrategy(config["strategy"], self.logger)
        self.risk = RiskManager(config["risk"])
        self.execution = ExecutionSimulator(
            slippage_bps=config["broker"].get("slippage_bps", 0.0),
            commission_per_share=config["broker"].get("commission_per_share", 0.0),
            commission_per_contract=config["broker"].get("commission_per_contract", 0.0),
        )
        self.portfolio = Portfolio(cash=config["portfolio"]["initial_cash"])
        self.pending_orders: Dict[str, List[Order]] = {}
        self.contract_multipliers: Dict[str, float] = {}
        self.last_prices: Dict[str, float] = {}
        self.trades: List[TradeRecord] = []
        self.decision_traces: List[DecisionTrace] = []

    def _provider_for_symbol(self, symbol_cfg: dict):
        source = symbol_cfg.get("data_source", "yfinance")
        if source == "yfinance":
            return YFinanceDataProvider()
        if source == "csv":
            return CSVDataProvider(symbol_cfg["csv_path"])
        return FuturesStubProvider()

    def _load_data(self, symbols: List[dict], start: datetime, end: datetime, timeframe: str) -> Dict[str, pd.DataFrame]:
        data: Dict[str, pd.DataFrame] = {}
        for sym in symbols:
            provider = self._provider_for_symbol(sym)
            df = provider.get_bars(
                symbol=sym["symbol"],
                start=start,
                end=end,
                timeframe=timeframe,
                timezone=sym.get("timezone", self.config.get("timezone", "US/Eastern")),
            )
            if df.empty:
                continue
            if sym.get("session") == "rth":
                df = df.set_index("timestamp")
                df = df.between_time("09:30", "16:00")
                df = df.reset_index()
            data[sym["symbol"]] = df.sort_values("timestamp")
        return data

    def _to_bar(self, row: pd.Series) -> Bar:
        return Bar(
            timestamp=row["timestamp"],
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0)),
        )

    def _execute_pending(self, symbol: str, bar: Bar) -> None:
        pending = self.pending_orders.get(symbol, [])
        if not pending:
            return
        remaining: List[Order] = []
        for order in pending:
            position = self.portfolio.get_position(symbol)
            closing_position = False
            orig_qty = order.qty
            entry_side = None
            if position is not None:
                if (position.qty > 0 and order.side == Side.SELL) or (position.qty < 0 and order.side == Side.BUY):
                    closing_position = True
                    orig_qty = abs(position.qty)
                    entry_side = Side.BUY if position.qty > 0 else Side.SELL
            fill = self.execution.fill_order(
                order=order,
                bar_open=bar.open,
                bar_high=bar.high,
                bar_low=bar.low,
                timestamp=bar.timestamp,
                contract_multiplier=self.contract_multipliers[symbol],
            )
            if fill is None:
                continue
            pnl, position_closed = self.portfolio.apply_fill(fill, self.contract_multipliers[symbol])
            if position_closed:
                self.risk.update_after_trade(pnl)
                if closing_position and position is not None:
                    risk_per_unit = position.risk_per_share * orig_qty * self.contract_multipliers[symbol]
                    r_multiple = pnl / risk_per_unit if risk_per_unit > 0 else 0.0
                    mfe = position.max_favorable_excursion
                    mae = position.max_adverse_excursion
                    bars_held = position.bars_held
                else:
                    r_multiple = 0.0
                    mfe = 0.0
                    mae = 0.0
                    bars_held = 0
                self.trades.append(
                    TradeRecord(
                        symbol=symbol,
                        entry_time=order.metadata.get("entry_time", bar.timestamp),
                        exit_time=bar.timestamp,
                        qty=orig_qty,
                        entry_price=order.metadata.get("entry_price", fill.price),
                        exit_price=fill.price,
                        pnl=pnl,
                        reason=order.reason,
                        side=entry_side,
                        mfe=mfe,
                        mae=mae,
                        r_multiple=r_multiple,
                        bars_held=bars_held,
                    )
                )
        self.pending_orders[symbol] = remaining

    def _intrabar_exits(self, symbol: str, bar: Bar) -> None:
        position = self.portfolio.get_position(symbol)
        if position is None:
            return

        position.bars_held += 1
        if position.qty > 0:
            position.max_favorable_excursion = max(position.max_favorable_excursion, bar.high - position.entry_price)
            position.max_adverse_excursion = max(position.max_adverse_excursion, position.entry_price - bar.low)
        else:
            position.max_favorable_excursion = max(position.max_favorable_excursion, position.entry_price - bar.low)
            position.max_adverse_excursion = max(position.max_adverse_excursion, bar.high - position.entry_price)

        stop_hit = (bar.low <= position.stop_price) if position.qty > 0 else (bar.high >= position.stop_price)
        if stop_hit:
            orig_qty_signed = position.qty
            orig_qty = abs(position.qty)
            entry_side = Side.BUY if orig_qty_signed > 0 else Side.SELL
            order = Order(
                symbol=symbol,
                side=Side.SELL if position.qty > 0 else Side.BUY,
                qty=abs(position.qty),
                order_type=OrderType.MARKET,
                limit_price=None,
                timestamp=bar.timestamp,
                reason="stop",
                metadata={"entry_time": position.entry_time, "entry_price": position.entry_price},
            )
            fill = self.execution.fill_at_price(
                order=order,
                price=position.stop_price,
                timestamp=bar.timestamp,
                contract_multiplier=self.contract_multipliers[symbol],
            )
            pnl, position_closed = self.portfolio.apply_fill(fill, self.contract_multipliers[symbol])
            if position_closed:
                self.risk.update_after_trade(pnl)
                risk_per_unit = position.risk_per_share * orig_qty * self.contract_multipliers[symbol]
                r_multiple = pnl / risk_per_unit if risk_per_unit > 0 else 0.0
                self.trades.append(
                    TradeRecord(
                        symbol=symbol,
                        entry_time=position.entry_time,
                        exit_time=bar.timestamp,
                        qty=orig_qty,
                        entry_price=position.entry_price,
                        exit_price=fill.price,
                        pnl=pnl,
                        reason="stop",
                        side=entry_side,
                        mfe=position.max_favorable_excursion,
                        mae=position.max_adverse_excursion,
                        r_multiple=r_multiple,
                        bars_held=position.bars_held,
                    )
                )
            return

        partial_cfg = self.config["strategy"]["exits"].get("partials", {})
        if partial_cfg.get("enabled", True):
            first_r = partial_cfg.get("first_r", 1.0)
            second_r = partial_cfg.get("second_r", 2.0)
            first_pct = partial_cfg.get("first_pct", 0.5)
            second_pct = partial_cfg.get("second_pct", 0.25)

            target1 = position.entry_price + (first_r * position.risk_per_share * (1 if position.qty > 0 else -1))
            target2 = position.entry_price + (second_r * position.risk_per_share * (1 if position.qty > 0 else -1))

            if not position.partial_1_taken:
                hit = bar.high >= target1 if position.qty > 0 else bar.low <= target1
                if hit:
                    qty_exit = int(abs(position.qty) * first_pct)
                    if qty_exit > 0:
                        order = Order(
                            symbol=symbol,
                            side=Side.SELL if position.qty > 0 else Side.BUY,
                            qty=qty_exit,
                            order_type=OrderType.MARKET,
                            limit_price=None,
                            timestamp=bar.timestamp,
                            reason="partial_1",
                            metadata={"entry_time": position.entry_time, "entry_price": position.entry_price},
                        )
                        fill = self.execution.fill_at_price(
                            order=order,
                            price=target1,
                            timestamp=bar.timestamp,
                            contract_multiplier=self.contract_multipliers[symbol],
                        )
                        pnl, _ = self.portfolio.apply_fill(fill, self.contract_multipliers[symbol])
                        self.risk.update_after_trade(pnl)
                        position.partial_1_taken = True
                        if partial_cfg.get("move_stop_to_breakeven", True):
                            position.stop_price = position.entry_price

            if not position.partial_2_taken:
                hit = bar.high >= target2 if position.qty > 0 else bar.low <= target2
                if hit:
                    qty_exit = int(abs(position.qty) * second_pct)
                    if qty_exit > 0:
                        order = Order(
                            symbol=symbol,
                            side=Side.SELL if position.qty > 0 else Side.BUY,
                            qty=qty_exit,
                            order_type=OrderType.MARKET,
                            limit_price=None,
                            timestamp=bar.timestamp,
                            reason="partial_2",
                            metadata={"entry_time": position.entry_time, "entry_price": position.entry_price},
                        )
                        fill = self.execution.fill_at_price(
                            order=order,
                            price=target2,
                            timestamp=bar.timestamp,
                            contract_multiplier=self.contract_multipliers[symbol],
                        )
                        pnl, _ = self.portfolio.apply_fill(fill, self.contract_multipliers[symbol])
                        self.risk.update_after_trade(pnl)
                        position.partial_2_taken = True

    def _update_trailing_stop(self, symbol: str, bar: Bar) -> None:
        position = self.portfolio.get_position(symbol)
        if position is None:
            return
        indicators = self.strategy.indicator_snapshot(symbol)
        new_stop = self.risk.update_trailing_stop(
            position=position,
            close=bar.close,
            sma20=indicators.get("sma_fast"),
            atr=indicators.get("atr"),
            config=self.config["strategy"]["exits"],
        )
        if new_stop is not None:
            position.stop_price = new_stop

    def _schedule_time_stop(self, symbol: str, bar: Bar) -> None:
        position = self.portfolio.get_position(symbol)
        if position is None:
            return
        indicators = self.strategy.indicator_snapshot(symbol)
        if self.risk.time_stop_trigger(
            position=position,
            atr=indicators.get("atr"),
            close=bar.close,
            config=self.config["strategy"]["exits"]["time_stop"],
        ):
            order = Order(
                symbol=symbol,
                side=Side.SELL if position.qty > 0 else Side.BUY,
                qty=abs(position.qty),
                order_type=OrderType.MARKET,
                limit_price=None,
                timestamp=bar.timestamp,
                reason="time_stop",
                metadata={"entry_time": position.entry_time, "entry_price": position.entry_price},
            )
            self.pending_orders.setdefault(symbol, []).append(order)

    def _create_entry_order(self, signal: Signal, entry_price: float, stop_price: float, qty: int) -> Order:
        order_type = OrderType.MARKET
        limit_price = None
        if self.config["strategy"].get("entry", {}).get("use_limit", False):
            order_type = OrderType.LIMIT
            limit_price = entry_price

        return Order(
            symbol=signal.symbol,
            side=signal.side,
            qty=qty,
            order_type=order_type,
            limit_price=limit_price,
            timestamp=signal.metadata.get("timestamp", datetime.utcnow()),
            reason=signal.reason,
            metadata={
                "stop_price": stop_price,
                "risk_per_share": abs(entry_price - stop_price),
                "entry_price": entry_price,
                "entry_time": signal.metadata.get("timestamp", datetime.utcnow()),
            },
        )

    def run(self, symbols: List[dict], start: datetime, end: datetime, timeframe: str) -> BacktestResult:
        data = self._load_data(symbols, start, end, timeframe)
        if not data:
            return BacktestResult(metrics={}, trades=[], decision_traces=[])

        for sym in symbols:
            self.pending_orders[sym["symbol"]] = []
            self.contract_multipliers[sym["symbol"]] = sym.get("contract_multiplier", 1.0)

        all_times = sorted({ts for df in data.values() for ts in df["timestamp"]})
        for ts in all_times:
            for sym, df in data.items():
                row = df.loc[df["timestamp"] == ts]
                if row.empty:
                    continue
                bar = self._to_bar(row.iloc[0])
                self.last_prices[sym] = bar.close
                if self.risk.current_day != bar.timestamp.date():
                    self.risk.reset_day(bar.timestamp.date())

                self._execute_pending(sym, bar)
                self._intrabar_exits(sym, bar)

                signals = self.strategy.on_bar(sym, bar)
                for signal in signals:
                    limits = self.risk.check_limits(
                        equity=self.portfolio.equity(self.last_prices, self.contract_multipliers),
                        open_positions=self.portfolio.open_positions_count(),
                    )
                    if not limits.allowed:
                        log_event(self.logger, "risk_block", {"symbol": sym, "reason": limits.reason})
                        continue

                    atr = signal.metadata.get("atr")
                    if self.risk.check_circuit_breaker(signal.metadata.get("atr_percent")):
                        log_event(self.logger, "circuit_breaker", {"symbol": sym})
                        continue

                    swing_level = signal.metadata.get("swing_low") if signal.side == Side.BUY else signal.metadata.get("swing_high")
                    stop_price = self.risk.initial_stop(
                        side=signal.side,
                        entry_price=bar.close,
                        atr=atr,
                        swing_level=swing_level,
                        config=self.config["strategy"]["exits"],
                    )
                    if stop_price is None:
                        continue
                    max_stop_pct = self.config["risk"].get("max_stop_pct", 0.1)
                    if abs(bar.close - stop_price) / bar.close > max_stop_pct:
                        continue

                    qty = self.risk.calculate_position_size(
                        equity=self.portfolio.equity(self.last_prices, self.contract_multipliers),
                        entry_price=bar.close,
                        stop_price=stop_price,
                        contract_multiplier=self.contract_multipliers[sym],
                        max_order_qty=self.config["risk"].get("max_order_qty", 1000000),
                        max_leverage=self.config["risk"].get("max_leverage", 2.0),
                    )
                    if qty <= 0:
                        continue

                    order = self._create_entry_order(signal, bar.close, stop_price, qty)
                    self.pending_orders.setdefault(sym, []).append(order)
                    trace = DecisionTrace(
                        symbol=signal.symbol,
                        timestamp=signal.metadata.get("timestamp", bar.timestamp),
                        regime=Regime(signal.metadata.get("regime", "neutral")),
                        narrow_wide=NarrowWideState(signal.metadata.get("narrow_wide", "unknown")),
                        transition_n2w=signal.metadata.get("transition_n2w", False),
                        spread=signal.metadata.get("spread"),
                        atr_percent=signal.metadata.get("atr_percent"),
                        triggers={
                            "breakout_mode": self.config["strategy"].get("breakout_mode"),
                            "sma_fast": signal.metadata.get("sma_fast"),
                            "sma_slow": signal.metadata.get("sma_slow"),
                            "atr": signal.metadata.get("atr"),
                            "swing_high": signal.metadata.get("swing_high"),
                            "swing_low": signal.metadata.get("swing_low"),
                        },
                        sizing={"qty": qty, "entry": bar.close},
                        stops={"stop": stop_price},
                        action="entry",
                        reason=signal.reason,
                    )
                    log_event(self.logger, "decision_trace", trace.__dict__)
                    self.decision_traces.append(trace)

                self._update_trailing_stop(sym, bar)
                self._schedule_time_stop(sym, bar)

        metrics = compute_metrics(self.trades, self.config["portfolio"]["initial_cash"])
        return BacktestResult(metrics=metrics, trades=self.trades, decision_traces=self.decision_traces)
