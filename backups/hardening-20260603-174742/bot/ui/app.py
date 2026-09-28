from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, time as dtime
from typing import Dict, Any, List

import pytz

from PySide6 import QtCore, QtGui, QtWidgets

from ..core.utils import get_logger
from ..core.strategy import NarrowToWideStrategy
from ..core.types import Bar, Side
from ..backtest.engine import BacktestResult
from ..core.data import YFinanceDataProvider, CSVDataProvider, FuturesStubProvider
from .workers import BacktestRequest, BacktestWorker
from .theme import app_font, stylesheet
from .charts import CandleChartWidget, PerformancePanel

try:
    from PySide6.QtCharts import (
        QChart,
        QChartView,
        QBarSeries,
        QBarSet,
        QBarCategoryAxis,
        QValueAxis,
        QLineSeries,
        QDateTimeAxis,
    )
    CHARTS_AVAILABLE = True
except Exception:
    CHARTS_AVAILABLE = False


class LogEmitter(QtCore.QObject):
    message = QtCore.Signal(str)


class QtLogHandler(logging.Handler):
    def __init__(self, emitter: LogEmitter) -> None:
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        payload = {
            "ts": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            payload.update(record.extra)
        self.emitter.message.emit(json.dumps(payload, default=str))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Narrow→Wide Trading Console")
        self.setMinimumSize(1280, 800)
        self.setFont(app_font())

        self.settings = QtCore.QSettings("NarrowWide", "App")
        self.custom_watchlist: List[str] = []
        self.last_trades: List[Any] = []
        self.last_decision_traces: List[Any] = []

        self.log_emitter = LogEmitter()
        self.log_emitter.message.connect(self.append_log)

        self.logger = get_logger("ui")
        self._attach_log_handler("backtest")

        self._build_ui()
        self._build_menu()
        self._setup_shortcuts()
        self.worker: BacktestWorker | None = None
        self.chart_worker = None
        self.current_config: Dict[str, Any] | None = None
        self.active_positions: List[Dict[str, Any]] = []
        self._snapshot_map: Dict[str, Dict[str, Any]] = {}
        self._hist_filter: tuple[str, int] | None = None
        self._data_quality: Dict[str, Any] = {}
        self.alert_rules: List[Dict[str, Any]] = []
        self._alert_symbols: set[str] = set()
        self._alert_last_fired: Dict[tuple[str, str], datetime] = {}
        self._alert_min_interval_sec = 300
        self._prev_regime_map: Dict[str, str] = {}
        self._prev_atr_map: Dict[str, float] = {}
        self._prev_sma_map: Dict[str, Dict[str, float]] = {}
        self._alert_history: List[Dict[str, Any]] = []
        self._alert_last_error: str | None = None
        self._alert_last_error_at: datetime | None = None
        self.trade_notes: Dict[str, str] = {}
        self._refresh_interval_sec = 60
        self._next_refresh_due: datetime | None = None
        self._last_refresh_at: datetime | None = None
        self._refresh_symbols()
        self._load_settings()
        self.market_timer = QtCore.QTimer(self)
        self.market_timer.timeout.connect(self.update_market_status)
        self.market_timer.start(60_000)
        self.update_market_status()
        self.header_timer = QtCore.QTimer(self)
        self.header_timer.timeout.connect(self._tick_header_timer)
        self.header_timer.start(1000)
        self._mark_data_refreshed()

    def _attach_log_handler(self, logger_name: str) -> None:
        logger = logging.getLogger(logger_name)
        if not any(isinstance(h, QtLogHandler) for h in logger.handlers):
            handler = QtLogHandler(self.log_emitter)
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)

        title = QtWidgets.QLabel("Narrow→Wide Control")
        title.setFont(QtGui.QFont("Avenir Next", 18, QtGui.QFont.Weight.Bold))
        subtitle = QtWidgets.QLabel("State-aware trading ops")
        subtitle.setStyleSheet("color:#97a0b8;")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.tabs = QtWidgets.QTabWidget()
        self.dashboard_tab = self._build_dashboard_tab()
        self.backtest_tab = self._build_backtest_tab()
        self.replay_tab = self._build_replay_tab()
        self.analyzer_tab = self._build_analyzer_tab()
        self.risk_tab = self._build_risk_tab()
        self.monitor_tab = self._build_monitor_tab()
        self.alerts_tab = self._build_alerts_tab()
        self.config_tab = self._build_config_tab()
        self.trade_tab = self._build_trade_tab()
        self.logs_tab = self._build_logs_tab()
        self.settings_tab = self._build_settings_tab()

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.backtest_tab, "Backtest")
        self.tabs.addTab(self.replay_tab, "Replay")
        self.tabs.addTab(self.analyzer_tab, "Analyzer")
        self.tabs.addTab(self.risk_tab, "Risk")
        self.tabs.addTab(self.monitor_tab, "Monitor")
        self.tabs.addTab(self.alerts_tab, "Alerts")
        self.tabs.addTab(self.config_tab, "Config")
        self.tabs.addTab(self.trade_tab, "Trade")
        self.tabs.addTab(self.logs_tab, "Logs")
        self.tabs.addTab(self.settings_tab, "Settings")

        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

    def _build_menu(self) -> None:
        menu = self.menuBar()
        help_menu = menu.addMenu("Help")
        about_action = QtGui.QAction("About NarrowWide", self)
        about_action.triggered.connect(self.show_about)
        update_action = QtGui.QAction("Check for Updates", self)
        update_action.triggered.connect(self.check_for_updates)
        help_menu.addAction(update_action)
        help_menu.addAction(about_action)

    def _setup_shortcuts(self) -> None:
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F"), self, activated=lambda: self.watch_search.setFocus())
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+J"), self, activated=lambda: self.watch_jump_input.setFocus())
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+R"), self, activated=self.refresh_monitor)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+B"), self, activated=self.run_backtest)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+R"), self, activated=self._request_chart_update)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Up"), self, activated=lambda: self._step_watchlist(-1))
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Down"), self, activated=lambda: self._step_watchlist(1))
        QtGui.QShortcut(QtGui.QKeySequence("Alt+1"), self, activated=lambda: self.tabs.setCurrentWidget(self.dashboard_tab))
        QtGui.QShortcut(QtGui.QKeySequence("Alt+2"), self, activated=lambda: self.tabs.setCurrentWidget(self.backtest_tab))
        QtGui.QShortcut(QtGui.QKeySequence("Alt+3"), self, activated=lambda: self.tabs.setCurrentWidget(self.replay_tab))
        QtGui.QShortcut(QtGui.QKeySequence("Alt+4"), self, activated=lambda: self.tabs.setCurrentWidget(self.analyzer_tab))
        QtGui.QShortcut(QtGui.QKeySequence("Alt+5"), self, activated=lambda: self.tabs.setCurrentWidget(self.risk_tab))
        QtGui.QShortcut(QtGui.QKeySequence("Alt+6"), self, activated=lambda: self.tabs.setCurrentWidget(self.monitor_tab))
        QtGui.QShortcut(QtGui.QKeySequence("Alt+7"), self, activated=lambda: self.tabs.setCurrentWidget(self.alerts_tab))
        QtGui.QShortcut(QtGui.QKeySequence("Alt+8"), self, activated=lambda: self.tabs.setCurrentWidget(self.config_tab))
        QtGui.QShortcut(QtGui.QKeySequence("Alt+9"), self, activated=lambda: self.tabs.setCurrentWidget(self.settings_tab))

    def _build_dashboard_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.dashboard_header = QtWidgets.QFrame()
        self.dashboard_header.setObjectName("dashboard_header")
        header_layout = QtWidgets.QHBoxLayout(self.dashboard_header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(12)
        self.header_market_label = QtWidgets.QLabel("Market: --")
        self.header_market_label.setObjectName("header_market")
        self.header_countdown_label = QtWidgets.QLabel("Next: --")
        self.header_countdown_label.setObjectName("header_countdown")
        self.header_refresh_label = QtWidgets.QLabel("Data refresh: --")
        self.header_refresh_label.setObjectName("header_refresh")
        self.header_quality_label = QtWidgets.QLabel("Data: --")
        self.header_quality_label.setObjectName("header_quality")
        self.header_symbol_label = QtWidgets.QLabel("Symbol: --")
        self.header_symbol_label.setObjectName("header_symbol")
        header_layout.addWidget(self.header_market_label)
        header_layout.addWidget(self.header_countdown_label)
        header_layout.addWidget(self.header_refresh_label)
        header_layout.addWidget(self.header_quality_label)
        header_layout.addStretch()
        header_layout.addWidget(self.header_symbol_label)
        layout.addWidget(self.dashboard_header)

        self.pulse_bar = QtWidgets.QProgressBar()
        self.pulse_bar.setRange(0, 100)
        self.pulse_bar.setValue(50)
        self.pulse_bar.setTextVisible(True)
        self.pulse_bar.setFormat("PnL 0.00%")
        self.pulse_bar.setFixedHeight(10)
        layout.addWidget(self.pulse_bar)

        cards = QtWidgets.QHBoxLayout()
        cards.setSpacing(8)
        self.dashboard_kpis: Dict[str, QtWidgets.QLabel] = {}
        for label, value in [
            ("Equity", "$100,000"),
            ("Daily PnL", "$0"),
            ("Win Rate", "--"),
            ("Max DD", "--"),
        ]:
            box = QtWidgets.QGroupBox()
            box_layout = QtWidgets.QVBoxLayout(box)
            box_layout.setSpacing(4)
            box_layout.addWidget(QtWidgets.QLabel(label))
            val = QtWidgets.QLabel(value)
            val.setFont(QtGui.QFont("Avenir Next", 14, QtGui.QFont.Weight.Bold))
            box_layout.addWidget(val)
            self.dashboard_kpis[label] = val
            cards.addWidget(box)

        layout.addLayout(cards)

        status = QtWidgets.QGroupBox("State Snapshot")
        status_layout = QtWidgets.QVBoxLayout(status)
        self.dashboard_state_table = QtWidgets.QTableWidget(0, 5)
        self.dashboard_state_table.setHorizontalHeaderLabels(["Symbol", "Regime", "State", "Spread", "ATR%"])
        self.dashboard_state_table.horizontalHeader().setStretchLastSection(True)
        status_layout.addWidget(self.dashboard_state_table)

        summary_row = QtWidgets.QHBoxLayout()
        summary_row.setSpacing(8)
        market_box = QtWidgets.QGroupBox("Market Session")
        market_layout = QtWidgets.QVBoxLayout(market_box)
        market_layout.setSpacing(4)
        self.market_status_label = QtWidgets.QLabel("Market: --")
        self.market_status_label.setFont(QtGui.QFont("Avenir Next", 12, QtGui.QFont.Weight.Bold))
        self.market_countdown_label = QtWidgets.QLabel("Next event: --")
        self.market_symbol_label = QtWidgets.QLabel("Symbol: --")
        market_layout.addWidget(self.market_status_label)
        market_layout.addWidget(self.market_countdown_label)
        market_layout.addWidget(self.market_symbol_label)

        confidence_box = QtWidgets.QGroupBox("Signal Confidence")
        confidence_layout = QtWidgets.QVBoxLayout(confidence_box)
        confidence_layout.setSpacing(4)
        self.signal_confidence_label = QtWidgets.QLabel("No signal")
        self.signal_confidence_bar = QtWidgets.QProgressBar()
        self.signal_confidence_bar.setRange(0, 100)
        self.signal_confidence_bar.setValue(0)
        self.signal_confidence_bar.setFormat("%p%")
        self.signal_confidence_detail = QtWidgets.QLabel("Waiting for traces")
        self.signal_confidence_detail.setStyleSheet("color:#97a0b8;")
        confidence_layout.addWidget(self.signal_confidence_label)
        confidence_layout.addWidget(self.signal_confidence_bar)
        confidence_layout.addWidget(self.signal_confidence_detail)

        risk_box = QtWidgets.QGroupBox("Risk Meter")
        risk_layout = QtWidgets.QVBoxLayout(risk_box)
        risk_layout.setSpacing(4)
        self.daily_loss_label = QtWidgets.QLabel("Daily loss: --")
        self.daily_loss_progress = QtWidgets.QProgressBar()
        self.daily_loss_progress.setRange(0, 100)
        self.daily_loss_progress.setValue(0)
        self.daily_loss_progress.setFormat("%p%")
        risk_layout.addWidget(self.daily_loss_label)
        risk_layout.addWidget(self.daily_loss_progress)

        alert_health_box = QtWidgets.QGroupBox("Alert Health")
        alert_health_layout = QtWidgets.QVBoxLayout(alert_health_box)
        alert_health_layout.setSpacing(4)
        self.alert_health_label = QtWidgets.QLabel("Last alert: --")
        self.alert_health_error = QtWidgets.QLabel("Errors: --")
        self.alert_health_error.setStyleSheet("color:#97a0b8;")
        alert_health_layout.addWidget(self.alert_health_label)
        alert_health_layout.addWidget(self.alert_health_error)

        equity_box = QtWidgets.QGroupBox("Mini Equity Curve")
        equity_layout = QtWidgets.QVBoxLayout(equity_box)
        equity_layout.setSpacing(4)
        if CHARTS_AVAILABLE:
            self.dashboard_equity_chart = QChart()
            self.dashboard_equity_chart.setBackgroundBrush(QtGui.QColor("#0f121a"))
            self.dashboard_equity_chart.setPlotAreaBackgroundBrush(QtGui.QColor("#0e141f"))
            self.dashboard_equity_chart.setPlotAreaBackgroundVisible(True)
            self.dashboard_equity_chart.legend().hide()
            self.dashboard_equity_view = QChartView(self.dashboard_equity_chart)
            self.dashboard_equity_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            equity_layout.addWidget(self.dashboard_equity_view)
        else:
            self.dashboard_equity_chart = None
            equity_layout.addWidget(QtWidgets.QLabel("Mini equity chart unavailable."))

        summary_row.addWidget(market_box, 1)
        summary_row.addWidget(confidence_box, 1)
        summary_row.addWidget(risk_box, 1)
        summary_row.addWidget(alert_health_box, 1)
        summary_row.addWidget(equity_box, 2)

        insights_row = QtWidgets.QHBoxLayout()
        insights_row.setSpacing(8)
        risk_heatmap_box = QtWidgets.QGroupBox("Risk Exposure")
        risk_heatmap_layout = QtWidgets.QVBoxLayout(risk_heatmap_box)
        risk_heatmap_layout.setSpacing(4)
        self.dashboard_risk_table = QtWidgets.QTableWidget(0, 3)
        self.dashboard_risk_table.setHorizontalHeaderLabels(["Symbol", "Exposure", "Risk %"])
        self.dashboard_risk_table.horizontalHeader().setStretchLastSection(True)
        risk_heatmap_layout.addWidget(self.dashboard_risk_table)

        tape_box = QtWidgets.QGroupBox("Orders & Fills")
        tape_layout = QtWidgets.QVBoxLayout(tape_box)
        tape_layout.setSpacing(4)
        self.dashboard_tape = QtWidgets.QListWidget()
        tape_layout.addWidget(self.dashboard_tape)

        regime_box = QtWidgets.QGroupBox("Regime Transitions")
        regime_layout = QtWidgets.QVBoxLayout(regime_box)
        regime_layout.setSpacing(4)
        self.dashboard_regime_table = QtWidgets.QTableWidget(0, 4)
        self.dashboard_regime_table.setHorizontalHeaderLabels(["Symbol", "Time", "From", "To"])
        self.dashboard_regime_table.horizontalHeader().setStretchLastSection(True)
        regime_layout.addWidget(self.dashboard_regime_table)

        insights_row.addWidget(risk_heatmap_box, 1)
        insights_row.addWidget(tape_box, 1)
        insights_row.addWidget(regime_box, 1)

        micro_row = QtWidgets.QHBoxLayout()
        micro_row.setSpacing(8)
        sparklines_box = QtWidgets.QGroupBox("Symbol Sparklines")
        sparklines_layout = QtWidgets.QVBoxLayout(sparklines_box)
        sparklines_layout.setSpacing(4)
        self.dashboard_spark_table = QtWidgets.QTableWidget(0, 3)
        self.dashboard_spark_table.setHorizontalHeaderLabels(["Symbol", "PnL Spark", "Last"])
        self.dashboard_spark_table.horizontalHeader().setStretchLastSection(True)
        self.dashboard_spark_table.verticalHeader().setVisible(False)
        self.dashboard_spark_table.setRowHeight(0, 42)
        sparklines_layout.addWidget(self.dashboard_spark_table)

        hist_box = QtWidgets.QGroupBox("Risk Histogram")
        hist_layout = QtWidgets.QVBoxLayout(hist_box)
        hist_layout.setSpacing(4)
        if CHARTS_AVAILABLE:
            self.dashboard_risk_hist_chart = QChart()
            self.dashboard_risk_hist_chart.setBackgroundBrush(QtGui.QColor("#0f121a"))
            self.dashboard_risk_hist_chart.setPlotAreaBackgroundBrush(QtGui.QColor("#0e141f"))
            self.dashboard_risk_hist_chart.setPlotAreaBackgroundVisible(True)
            self.dashboard_risk_hist_chart.legend().hide()
            self.dashboard_risk_hist_view = QChartView(self.dashboard_risk_hist_chart)
            self.dashboard_risk_hist_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            self.dashboard_risk_hist_mode = QtWidgets.QComboBox()
            self.dashboard_risk_hist_mode.addItems(["Risk %", "ATR %"])
            self.dashboard_risk_hist_mode.currentTextChanged.connect(self._refresh_histogram_mode)
            hist_layout.addWidget(self.dashboard_risk_hist_mode)
            self.dashboard_risk_hist_filter_label = QtWidgets.QLabel("Filter: none")
            hist_layout.addWidget(self.dashboard_risk_hist_filter_label)
            hist_layout.addWidget(self.dashboard_risk_hist_view)
        else:
            self.dashboard_risk_hist_chart = None
            hist_layout.addWidget(QtWidgets.QLabel("Risk histogram unavailable."))

        micro_row.addWidget(sparklines_box, 2)
        micro_row.addWidget(hist_box, 1)

        actions_box = QtWidgets.QGroupBox("Quick Actions")
        actions_layout = QtWidgets.QHBoxLayout(actions_box)
        actions_layout.setSpacing(8)
        self.dashboard_backtest_btn = QtWidgets.QPushButton("Run Backtest")
        self.dashboard_backtest_btn.clicked.connect(self.run_backtest)
        self.dashboard_refresh_btn = QtWidgets.QPushButton("Refresh Snapshot")
        self.dashboard_refresh_btn.clicked.connect(self.refresh_monitor)
        self.dashboard_config_btn = QtWidgets.QPushButton("Open Config")
        self.dashboard_config_btn.clicked.connect(lambda: self.tabs.setCurrentWidget(self.config_tab))
        actions_layout.addWidget(self.dashboard_backtest_btn)
        actions_layout.addWidget(self.dashboard_refresh_btn)
        actions_layout.addWidget(self.dashboard_config_btn)
        actions_layout.addStretch()

        grid = QtWidgets.QHBoxLayout()
        grid.setSpacing(8)
        watch_box = QtWidgets.QGroupBox("Watchlist")
        watch_layout = QtWidgets.QVBoxLayout(watch_box)
        watch_layout.setSpacing(4)
        self.dashboard_watchlist = QtWidgets.QListWidget()
        self.dashboard_watchlist.itemSelectionChanged.connect(self.on_watchlist_change)
        watch_layout.addWidget(self.dashboard_watchlist)

        self.dashboard_watchlist_spark = QtWidgets.QTableWidget(0, 3)
        self.dashboard_watchlist_spark.setHorizontalHeaderLabels(["Symbol", "Spark", "Last"])
        self.dashboard_watchlist_spark.horizontalHeader().setStretchLastSection(True)
        self.dashboard_watchlist_spark.verticalHeader().setVisible(False)
        self.dashboard_watchlist_spark.setFixedHeight(160)
        watch_layout.addWidget(self.dashboard_watchlist_spark)

        chart_box = QtWidgets.QGroupBox("Chart")
        chart_layout = QtWidgets.QVBoxLayout(chart_box)
        chart_layout.setSpacing(4)
        self.dashboard_chart = CandleChartWidget()
        chart_layout.addWidget(self.dashboard_chart)

        right_col = QtWidgets.QVBoxLayout()
        right_col.setSpacing(8)
        signals_box = QtWidgets.QGroupBox("Latest Signals")
        signals_layout = QtWidgets.QVBoxLayout(signals_box)
        signals_layout.setSpacing(4)
        self.dashboard_signals = QtWidgets.QListWidget()
        signals_layout.addWidget(self.dashboard_signals)
        trades_box = QtWidgets.QGroupBox("Recent Trades")
        trades_layout = QtWidgets.QVBoxLayout(trades_box)
        trades_layout.setSpacing(4)
        self.dashboard_trades = QtWidgets.QTableWidget(0, 5)
        self.dashboard_trades.setHorizontalHeaderLabels(["Symbol", "Side", "Entry", "Exit", "PnL"])
        self.dashboard_trades.horizontalHeader().setStretchLastSection(True)
        trades_layout.addWidget(self.dashboard_trades)

        positions_box = QtWidgets.QGroupBox("Active Positions")
        positions_layout = QtWidgets.QVBoxLayout(positions_box)
        positions_layout.setSpacing(4)
        self.dashboard_positions = QtWidgets.QTableWidget(0, 5)
        self.dashboard_positions.setHorizontalHeaderLabels(["Symbol", "Side", "Qty", "Entry", "Unrealized"])
        self.dashboard_positions.horizontalHeader().setStretchLastSection(True)
        self.dashboard_positions_empty = QtWidgets.QLabel("No active positions")
        positions_layout.addWidget(self.dashboard_positions)
        positions_layout.addWidget(self.dashboard_positions_empty)
        right_col.addWidget(signals_box)
        right_col.addWidget(trades_box)
        right_col.addWidget(positions_box)

        grid.addWidget(watch_box, 1)
        grid.addWidget(chart_box, 3)
        grid.addLayout(right_col, 2)

        layout.addWidget(status)
        layout.addLayout(summary_row)
        layout.addLayout(insights_row)
        layout.addLayout(micro_row)
        layout.addWidget(actions_box)
        layout.addLayout(grid)
        layout.addStretch()
        return widget

    def _build_backtest_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        controls = QtWidgets.QGroupBox("Backtest Controls")
        form = QtWidgets.QGridLayout(controls)

        self.config_path = QtWidgets.QLineEdit(self._default_config_path())
        config_btn = QtWidgets.QPushButton("Browse")
        config_btn.clicked.connect(self.browse_config)

        self.symbols_input = QtWidgets.QLineEdit("SPY")
        self.tf_input = QtWidgets.QComboBox()
        self.tf_input.addItems(["1m", "5m", "15m", "1h", "1d"])

        self.tf_quick = QtWidgets.QHBoxLayout()
        for tf in ["1m", "5m", "15m", "1h", "1d"]:
            btn = QtWidgets.QPushButton(tf)
            btn.setObjectName(f"tf_{tf}")
            btn.clicked.connect(lambda _=None, t=tf: self.set_timeframe(t))
            self.tf_quick.addWidget(btn)
        self.tf_quick.addStretch()

        self.preset_input = QtWidgets.QComboBox()
        self.preset_input.addItems(["Custom", "Last 5 days", "Last 10 days", "Last 30 days", "YTD"])
        self.preset_input.currentTextChanged.connect(self.apply_preset)

        self.slippage_input = QtWidgets.QDoubleSpinBox()
        self.slippage_input.setSuffix(" bps")
        self.slippage_input.setRange(0, 50)
        self.slippage_input.setDecimals(2)
        self.slippage_input.setValue(1.0)

        self.commission_share_input = QtWidgets.QDoubleSpinBox()
        self.commission_share_input.setPrefix("$")
        self.commission_share_input.setRange(0, 10)
        self.commission_share_input.setDecimals(4)
        self.commission_share_input.setValue(0.0)

        self.commission_contract_input = QtWidgets.QDoubleSpinBox()
        self.commission_contract_input.setPrefix("$")
        self.commission_contract_input.setRange(0, 50)
        self.commission_contract_input.setDecimals(2)
        self.commission_contract_input.setValue(2.0)

        self.start_date = QtWidgets.QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QtCore.QDate.currentDate().addDays(-7))

        self.end_date = QtWidgets.QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QtCore.QDate.currentDate())

        self.run_btn = QtWidgets.QPushButton("Run Backtest")
        self.run_btn.clicked.connect(self.run_backtest)

        form.addWidget(QtWidgets.QLabel("Config"), 0, 0)
        form.addWidget(self.config_path, 0, 1)
        form.addWidget(config_btn, 0, 2)
        form.addWidget(QtWidgets.QLabel("Symbols"), 1, 0)
        form.addWidget(self.symbols_input, 1, 1)
        form.addWidget(QtWidgets.QLabel("Timeframe"), 1, 2)
        form.addWidget(self.tf_input, 1, 3)
        form.addWidget(QtWidgets.QLabel("Preset"), 2, 0)
        form.addWidget(self.preset_input, 2, 1)
        form.addWidget(QtWidgets.QLabel("Quick TF"), 2, 2)
        quick_container = QtWidgets.QWidget()
        quick_container.setLayout(self.tf_quick)
        form.addWidget(quick_container, 2, 3)
        form.addWidget(QtWidgets.QLabel("Start"), 3, 0)
        form.addWidget(self.start_date, 3, 1)
        form.addWidget(QtWidgets.QLabel("End"), 3, 2)
        form.addWidget(self.end_date, 3, 3)
        form.addWidget(QtWidgets.QLabel("Slippage"), 4, 0)
        form.addWidget(self.slippage_input, 4, 1)
        form.addWidget(QtWidgets.QLabel("Comm/Share"), 4, 2)
        form.addWidget(self.commission_share_input, 4, 3)
        form.addWidget(QtWidgets.QLabel("Comm/Contract"), 5, 0)
        form.addWidget(self.commission_contract_input, 5, 1)
        form.addWidget(self.run_btn, 6, 0)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        form.addWidget(self.progress, 6, 1, 1, 3)

        layout.addWidget(controls)

        self.bt_chart = CandleChartWidget()
        chart_box = QtWidgets.QGroupBox("Price Chart (TradingView-style)")
        chart_layout = QtWidgets.QVBoxLayout(chart_box)

        toggles = QtWidgets.QHBoxLayout()
        self.toggle_sma_fast = QtWidgets.QCheckBox("SMA20")
        self.toggle_sma_fast.setObjectName("chip_sma_fast")
        self.toggle_sma_fast.setProperty("chip", True)
        self.toggle_sma_fast.setChecked(True)
        self.toggle_sma_fast.stateChanged.connect(self.apply_chart_toggles)
        self.toggle_sma_slow = QtWidgets.QCheckBox("SMA200")
        self.toggle_sma_slow.setObjectName("chip_sma_slow")
        self.toggle_sma_slow.setProperty("chip", True)
        self.toggle_sma_slow.setChecked(True)
        self.toggle_sma_slow.stateChanged.connect(self.apply_chart_toggles)
        self.toggle_ema = QtWidgets.QCheckBox("EMA9")
        self.toggle_ema.setObjectName("chip_ema")
        self.toggle_ema.setProperty("chip", True)
        self.toggle_ema.setChecked(True)
        self.toggle_ema.stateChanged.connect(self.apply_chart_toggles)
        self.toggle_volume = QtWidgets.QCheckBox("Volume")
        self.toggle_volume.setObjectName("chip_volume")
        self.toggle_volume.setProperty("chip", True)
        self.toggle_volume.setChecked(True)
        self.toggle_volume.stateChanged.connect(self.apply_chart_toggles)
        self.toggle_atr = QtWidgets.QCheckBox("ATR14")
        self.toggle_atr.setObjectName("chip_atr")
        self.toggle_atr.setProperty("chip", True)
        self.toggle_atr.setChecked(True)
        self.toggle_atr.stateChanged.connect(self.apply_chart_toggles)
        self.toggle_atr_bands = QtWidgets.QCheckBox("ATR Bands")
        self.toggle_atr_bands.setObjectName("chip_atr_bands")
        self.toggle_atr_bands.setProperty("chip", True)
        self.toggle_atr_bands.setChecked(True)
        self.toggle_atr_bands.stateChanged.connect(self.apply_chart_toggles)
        self.toggle_rsi = QtWidgets.QCheckBox("RSI14")
        self.toggle_rsi.setObjectName("chip_rsi")
        self.toggle_rsi.setProperty("chip", True)
        self.toggle_rsi.setChecked(True)
        self.toggle_rsi.stateChanged.connect(self.apply_chart_toggles)
        self.toggle_n2w = QtWidgets.QCheckBox("N2W Bands")
        self.toggle_n2w.setObjectName("chip_n2w")
        self.toggle_n2w.setProperty("chip", True)
        self.toggle_n2w.setChecked(True)
        self.toggle_n2w.stateChanged.connect(self.apply_chart_toggles)

        self.pan_toggle = QtWidgets.QPushButton("Pan")
        self.pan_toggle.setCheckable(True)
        self.pan_toggle.toggled.connect(self.on_pan_toggle)
        self.zoom_in_btn = QtWidgets.QPushButton("Zoom In")
        self.zoom_in_btn.clicked.connect(lambda: self.bt_chart.zoom_by(0.9))
        self.zoom_out_btn = QtWidgets.QPushButton("Zoom Out")
        self.zoom_out_btn.clicked.connect(lambda: self.bt_chart.zoom_by(1.1))
        self.reset_zoom_btn = QtWidgets.QPushButton("Reset")
        self.reset_zoom_btn.clicked.connect(self.bt_chart.reset_zoom)
        self.autoscale_btn = QtWidgets.QPushButton("Autoscale")
        self.autoscale_btn.clicked.connect(self.bt_chart.autoscale)

        toggles.addWidget(self.toggle_sma_fast)
        toggles.addWidget(self.toggle_sma_slow)
        toggles.addWidget(self.toggle_ema)
        toggles.addWidget(self.toggle_volume)
        toggles.addWidget(self.toggle_atr)
        toggles.addWidget(self.toggle_atr_bands)
        toggles.addWidget(self.toggle_rsi)
        toggles.addWidget(self.toggle_n2w)
        toggles.addSpacing(12)
        toggles.addWidget(self.pan_toggle)
        toggles.addWidget(self.zoom_in_btn)
        toggles.addWidget(self.zoom_out_btn)
        toggles.addWidget(self.reset_zoom_btn)
        toggles.addWidget(self.autoscale_btn)
        toggles.addStretch()

        chart_layout.addLayout(toggles)
        chart_layout.addWidget(self.bt_chart)

        watch_box = QtWidgets.QGroupBox("Watchlist")
        watch_layout = QtWidgets.QVBoxLayout(watch_box)
        self.watch_search = QtWidgets.QLineEdit()
        self.watch_search.setPlaceholderText("Filter symbols")
        self.watch_search.textChanged.connect(self._filter_watchlist)
        filters_row = QtWidgets.QHBoxLayout()
        filters_row.setSpacing(6)
        self.watch_regime_filter = QtWidgets.QComboBox()
        self.watch_regime_filter.addItems(["Regime: All", "Bull", "Bear", "Neutral"])
        self.watch_regime_filter.currentTextChanged.connect(self._apply_watchlist_filters)
        self.watch_state_filter = QtWidgets.QComboBox()
        self.watch_state_filter.addItems(["State: All", "Narrow", "Wide"])
        self.watch_state_filter.currentTextChanged.connect(self._apply_watchlist_filters)
        self.watch_atr_filter = QtWidgets.QComboBox()
        self.watch_atr_filter.addItems(["ATR%: All", "<0.5%", "0.5-1%", "1-2%", "2%+"])
        self.watch_atr_filter.currentTextChanged.connect(self._apply_watchlist_filters)
        self.watch_jump_input = QtWidgets.QLineEdit()
        self.watch_jump_input.setPlaceholderText("Jump to symbol")
        self.watch_jump_input.setFixedWidth(140)
        self.watch_jump_input.returnPressed.connect(self._jump_to_symbol)
        self.watch_filter_clear = QtWidgets.QPushButton("Clear")
        self.watch_filter_clear.clicked.connect(self._reset_watch_filters)
        filters_row.addWidget(self.watch_regime_filter)
        filters_row.addWidget(self.watch_state_filter)
        filters_row.addWidget(self.watch_atr_filter)
        filters_row.addWidget(self.watch_jump_input)
        filters_row.addWidget(self.watch_filter_clear)
        self.watchlist = QtWidgets.QListWidget()
        self.watchlist.itemSelectionChanged.connect(self.on_watchlist_change)
        self.watch_add_input = QtWidgets.QLineEdit()
        self.watch_add_input.setPlaceholderText("Add symbol (e.g., AAPL)")
        self.watch_add_btn = QtWidgets.QPushButton("Add")
        self.watch_add_btn.clicked.connect(self.add_watch_symbol)
        self.watch_remove_btn = QtWidgets.QPushButton("Remove")
        self.watch_remove_btn.clicked.connect(self.remove_watch_symbol)

        watch_layout.addWidget(self.watch_search)
        watch_layout.addLayout(filters_row)
        watch_layout.addWidget(self.watchlist)
        watch_layout.addWidget(self.watch_add_input)
        watch_layout.addWidget(self.watch_add_btn)
        watch_layout.addWidget(self.watch_remove_btn)

        mid = QtWidgets.QHBoxLayout()
        mid.addWidget(watch_box, 1)
        mid.addWidget(chart_box, 3)

        self.metrics_table = QtWidgets.QTableWidget(0, 2)
        self.metrics_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.metrics_table.horizontalHeader().setStretchLastSection(True)

        self.trades_table = QtWidgets.QTableWidget(0, 7)
        self.trades_table.setHorizontalHeaderLabels(
            ["Symbol", "Entry", "Exit", "Qty", "Entry Px", "Exit Px", "PnL"]
        )
        self.trades_table.horizontalHeader().setStretchLastSection(True)

        layout.addLayout(mid)

        metrics_box = QtWidgets.QGroupBox("Metrics")
        metrics_layout = QtWidgets.QVBoxLayout(metrics_box)
        metrics_layout.addWidget(self.metrics_table)

        trades_box = QtWidgets.QGroupBox("Trades")
        trades_layout = QtWidgets.QVBoxLayout(trades_box)
        trades_layout.addWidget(self.trades_table)

        performance_box = QtWidgets.QGroupBox("Performance")
        performance_layout = QtWidgets.QVBoxLayout(performance_box)
        self.performance_panel = PerformancePanel()
        performance_layout.addWidget(self.performance_panel)

        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        split.addWidget(trades_box)
        split.addWidget(performance_box)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 1)
        self.trades_splitter = split

        export_bar = QtWidgets.QHBoxLayout()
        self.export_trades_btn = QtWidgets.QPushButton("Export Trades CSV")
        self.export_trades_btn.clicked.connect(self.export_trades_csv)
        self.export_metrics_btn = QtWidgets.QPushButton("Export Metrics CSV")
        self.export_metrics_btn.clicked.connect(self.export_metrics_csv)
        self.export_traces_btn = QtWidgets.QPushButton("Export Traces CSV")
        self.export_traces_btn.clicked.connect(self.export_traces_csv)
        export_bar.addWidget(self.export_trades_btn)
        export_bar.addWidget(self.export_metrics_btn)
        export_bar.addWidget(self.export_traces_btn)
        export_bar.addStretch()

        layout.addWidget(metrics_box)
        layout.addLayout(export_bar)
        layout.addWidget(split)

        return widget

    def _build_replay_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        controls = QtWidgets.QGroupBox("Replay Controls")
        form = QtWidgets.QGridLayout(controls)

        self.replay_symbol = QtWidgets.QComboBox()
        self.replay_symbol.setEditable(True)
        self.replay_tf = QtWidgets.QComboBox()
        self.replay_tf.addItems(["1m", "5m", "15m", "1h", "1d"])
        self.replay_start = QtWidgets.QDateEdit()
        self.replay_start.setCalendarPopup(True)
        self.replay_start.setDate(QtCore.QDate.currentDate().addDays(-5))
        self.replay_end = QtWidgets.QDateEdit()
        self.replay_end.setCalendarPopup(True)
        self.replay_end.setDate(QtCore.QDate.currentDate())

        self.replay_load_btn = QtWidgets.QPushButton("Load Replay")
        self.replay_load_btn.clicked.connect(self.load_replay_data)

        form.addWidget(QtWidgets.QLabel("Symbol"), 0, 0)
        form.addWidget(self.replay_symbol, 0, 1)
        form.addWidget(QtWidgets.QLabel("Timeframe"), 0, 2)
        form.addWidget(self.replay_tf, 0, 3)
        form.addWidget(QtWidgets.QLabel("Start"), 1, 0)
        form.addWidget(self.replay_start, 1, 1)
        form.addWidget(QtWidgets.QLabel("End"), 1, 2)
        form.addWidget(self.replay_end, 1, 3)
        form.addWidget(self.replay_load_btn, 2, 0)

        layout.addWidget(controls)

        self.replay_chart = CandleChartWidget()
        layout.addWidget(self.replay_chart)

        replay_controls = QtWidgets.QHBoxLayout()
        self.replay_prev = QtWidgets.QPushButton("◀")
        self.replay_prev.clicked.connect(lambda: self._step_replay(-1))
        self.replay_next = QtWidgets.QPushButton("▶")
        self.replay_next.clicked.connect(lambda: self._step_replay(1))
        self.replay_play = QtWidgets.QPushButton("Play")
        self.replay_play.setCheckable(True)
        self.replay_play.toggled.connect(self.toggle_replay_play)
        self.replay_speed = QtWidgets.QComboBox()
        self.replay_speed.addItems(["0.5x", "1x", "2x", "4x"])
        self.replay_speed.setCurrentText("1x")
        self.replay_speed.currentTextChanged.connect(self.update_replay_speed)
        self.replay_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.replay_slider.valueChanged.connect(self.update_replay_view)
        self.replay_status = QtWidgets.QLabel("No replay loaded")

        replay_controls.addWidget(self.replay_prev)
        replay_controls.addWidget(self.replay_next)
        replay_controls.addWidget(self.replay_play)
        replay_controls.addWidget(self.replay_speed)
        replay_controls.addWidget(self.replay_slider)
        replay_controls.addWidget(self.replay_status)

        layout.addLayout(replay_controls)
        return widget

    def _build_analyzer_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        self.analyzer_table = QtWidgets.QTableWidget(0, 8)
        self.analyzer_table.setHorizontalHeaderLabels(
            ["Symbol", "Trades", "Win %", "Avg Win", "Avg Loss", "Expectancy", "Avg R", "Avg MAE"]
        )
        self.analyzer_table.horizontalHeader().setStretchLastSection(True)
        self.analyzer_table.itemSelectionChanged.connect(self._on_analyzer_selection)

        layout.addWidget(self.analyzer_table)

        drill_box = QtWidgets.QGroupBox("Symbol Drilldown")
        drill_layout = QtWidgets.QVBoxLayout(drill_box)
        drill_metrics = QtWidgets.QHBoxLayout()
        self.drill_symbol_label = QtWidgets.QLabel("Symbol: --")
        self.drill_winrate_label = QtWidgets.QLabel("Win%: --")
        self.drill_expectancy_label = QtWidgets.QLabel("Expectancy: --")
        self.drill_maxdd_label = QtWidgets.QLabel("Max DD: --")
        drill_metrics.addWidget(self.drill_symbol_label)
        drill_metrics.addWidget(self.drill_winrate_label)
        drill_metrics.addWidget(self.drill_expectancy_label)
        drill_metrics.addWidget(self.drill_maxdd_label)
        drill_metrics.addStretch()
        drill_layout.addLayout(drill_metrics)
        if CHARTS_AVAILABLE:
            self.symbol_drill_chart = QChart()
            self.symbol_drill_chart.setBackgroundBrush(QtGui.QColor("#0f121a"))
            self.symbol_drill_chart.setPlotAreaBackgroundVisible(True)
            self.symbol_drill_chart.setPlotAreaBackgroundBrush(QtGui.QColor("#0e141f"))
            self.symbol_drill_chart.legend().hide()
            self.symbol_drill_view = QChartView(self.symbol_drill_chart)
            self.symbol_drill_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            drill_layout.addWidget(self.symbol_drill_view)
        else:
            self.symbol_drill_chart = None
            drill_layout.addWidget(QtWidgets.QLabel("Symbol drilldown chart unavailable (QtCharts missing)."))

        layout.addWidget(drill_box)

        if CHARTS_AVAILABLE:
            self.r_dist_chart = QChart()
            self.r_dist_chart.setBackgroundBrush(QtGui.QColor("#0f121a"))
            self.r_dist_chart.setPlotAreaBackgroundVisible(True)
            self.r_dist_chart.setPlotAreaBackgroundBrush(QtGui.QColor("#0e141f"))
            self.r_dist_view = QChartView(self.r_dist_chart)
            self.r_dist_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            layout.addWidget(self.r_dist_view)
        else:
            layout.addWidget(QtWidgets.QLabel("R-multiple chart unavailable (QtCharts missing)."))

        traces_box = QtWidgets.QGroupBox("Decision Traces")
        traces_layout = QtWidgets.QVBoxLayout(traces_box)
        filter_row = QtWidgets.QHBoxLayout()
        self.trace_filter_symbol = QtWidgets.QLineEdit()
        self.trace_filter_symbol.setPlaceholderText("Filter symbol")
        self.trace_filter_action = QtWidgets.QLineEdit()
        self.trace_filter_action.setPlaceholderText("Filter action")
        self.trace_filter_reason = QtWidgets.QLineEdit()
        self.trace_filter_reason.setPlaceholderText("Filter reason")
        self.trace_filter_symbol.textChanged.connect(self._render_traces_table)
        self.trace_filter_action.textChanged.connect(self._render_traces_table)
        self.trace_filter_reason.textChanged.connect(self._render_traces_table)

        filter_row.addWidget(self.trace_filter_symbol)
        filter_row.addWidget(self.trace_filter_action)
        filter_row.addWidget(self.trace_filter_reason)
        traces_layout.addLayout(filter_row)

        self.traces_table = QtWidgets.QTableWidget(0, 8)
        self.traces_table.setHorizontalHeaderLabels(
            ["Symbol", "Time", "Regime", "State", "Spread", "ATR%", "Action", "Reason"]
        )
        self.traces_table.horizontalHeader().setStretchLastSection(True)
        self.traces_table.itemSelectionChanged.connect(self.on_trace_selected)
        traces_layout.addWidget(self.traces_table)

        layout.addWidget(traces_box)

        journal_box = QtWidgets.QGroupBox("Trade Journal")
        journal_layout = QtWidgets.QHBoxLayout(journal_box)
        self.journal_table = QtWidgets.QTableWidget(0, 5)
        self.journal_table.setHorizontalHeaderLabels(["Symbol", "Entry", "Exit", "PnL", "Notes"])
        self.journal_table.horizontalHeader().setStretchLastSection(True)
        self.journal_table.itemChanged.connect(self._on_journal_item_changed)
        self.journal_table.itemSelectionChanged.connect(self._on_journal_selection_changed)
        self.journal_detail = QtWidgets.QPlainTextEdit()
        self.journal_detail.setReadOnly(True)
        self.journal_detail.setPlaceholderText("Select a trade to see its decision trace.")
        journal_layout.addWidget(self.journal_table, 2)
        journal_layout.addWidget(self.journal_detail, 1)
        layout.addWidget(journal_box)

        return widget

    def _build_risk_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        self.risk_table = QtWidgets.QTableWidget(0, 2)
        self.risk_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.risk_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.risk_table)

        return widget

    def _build_monitor_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        controls = QtWidgets.QHBoxLayout()
        self.monitor_refresh = QtWidgets.QPushButton("Refresh Snapshot")
        self.monitor_refresh.clicked.connect(self.refresh_monitor)
        controls.addWidget(self.monitor_refresh)
        controls.addStretch()
        layout.addLayout(controls)

        self.monitor_table = QtWidgets.QTableWidget(0, 5)
        self.monitor_table.setHorizontalHeaderLabels(["Symbol", "Price", "Regime", "N/W", "ATR%"])
        self.monitor_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.monitor_table)

        return widget

    def _build_alerts_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        config_box = QtWidgets.QGroupBox("Delivery Settings")
        config_layout = QtWidgets.QHBoxLayout(config_box)
        self.alert_webhook_url = QtWidgets.QLineEdit()
        self.alert_webhook_url.setPlaceholderText("Webhook URL")
        self.alert_telegram_token = QtWidgets.QLineEdit()
        self.alert_telegram_token.setPlaceholderText("Telegram bot token")
        self.alert_telegram_chat = QtWidgets.QLineEdit()
        self.alert_telegram_chat.setPlaceholderText("Telegram chat id")
        self.alert_test_btn = QtWidgets.QPushButton("Send Test")
        self.alert_test_btn.clicked.connect(self.send_test_alert)
        config_layout.addWidget(self.alert_webhook_url)
        config_layout.addWidget(self.alert_telegram_token)
        config_layout.addWidget(self.alert_telegram_chat)
        config_layout.addWidget(self.alert_test_btn)
        config_layout.addStretch()

        form_box = QtWidgets.QGroupBox("Create Alert Rule")
        form_layout = QtWidgets.QHBoxLayout(form_box)
        self.alert_symbol_input = QtWidgets.QLineEdit()
        self.alert_symbol_input.setPlaceholderText("Symbol (e.g., ES, SPY)")
        self.alert_condition_input = QtWidgets.QComboBox()
        self.alert_condition_input.addItems(
            [
                "N2W Breakout",
                "Regime Change",
                "ATR Spike",
                "SMA20 Cross",
                "SMA200 Cross",
                "Custom (manual)",
            ]
        )
        self.alert_channel_input = QtWidgets.QComboBox()
        self.alert_channel_input.addItems(["In-app", "Log", "Webhook", "Telegram"])
        self.alert_enabled_input = QtWidgets.QCheckBox("Enabled")
        self.alert_enabled_input.setChecked(True)
        self.alert_add_btn = QtWidgets.QPushButton("Add Rule")
        self.alert_add_btn.clicked.connect(self.add_alert_rule)
        form_layout.addWidget(self.alert_symbol_input)
        form_layout.addWidget(self.alert_condition_input)
        form_layout.addWidget(self.alert_channel_input)
        form_layout.addWidget(self.alert_enabled_input)
        form_layout.addWidget(self.alert_add_btn)
        form_layout.addStretch()

        self.alerts_table = QtWidgets.QTableWidget(0, 5)
        self.alerts_table.setHorizontalHeaderLabels(["Symbol", "Condition", "Channel", "Enabled", "Notes"])
        self.alerts_table.horizontalHeader().setStretchLastSection(True)
        self.alerts_table.itemChanged.connect(self._on_alert_table_item_changed)

        btn_row = QtWidgets.QHBoxLayout()
        self.alert_remove_btn = QtWidgets.QPushButton("Remove Selected")
        self.alert_remove_btn.clicked.connect(self.remove_alert_rule)
        btn_row.addWidget(self.alert_remove_btn)
        btn_row.addStretch()

        layout.addWidget(config_box)
        layout.addWidget(form_box)
        layout.addWidget(self.alerts_table)
        layout.addLayout(btn_row)
        return widget

    def _build_config_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        self.config_editor = QtWidgets.QPlainTextEdit()
        self.config_editor.setPlaceholderText("Edit config.yaml here")

        btns = QtWidgets.QHBoxLayout()
        self.config_load_btn = QtWidgets.QPushButton("Load")
        self.config_load_btn.clicked.connect(self.load_config_into_editor)
        self.config_validate_btn = QtWidgets.QPushButton("Validate")
        self.config_validate_btn.clicked.connect(self.validate_config_editor)
        self.config_save_btn = QtWidgets.QPushButton("Save")
        self.config_save_btn.clicked.connect(self.save_config_from_editor)
        self.config_status = QtWidgets.QLabel("")

        btns.addWidget(self.config_load_btn)
        btns.addWidget(self.config_validate_btn)
        btns.addWidget(self.config_save_btn)
        btns.addWidget(self.config_status)
        btns.addStretch()

        layout.addLayout(btns)
        layout.addWidget(self.config_editor)
        return widget

    def _build_trade_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        box = QtWidgets.QGroupBox("Live/Paper Trading")
        form = QtWidgets.QVBoxLayout(box)
        form.addWidget(QtWidgets.QLabel("Paper trading is available via replay mode in the Backtest tab."))
        form.addWidget(QtWidgets.QLabel("Live broker adapters are stubs and require explicit enablement."))
        layout.addWidget(box)
        layout.addStretch()
        return widget

    def _build_logs_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        return widget

    def _build_settings_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        box = QtWidgets.QGroupBox("Safety")
        form = QtWidgets.QVBoxLayout(box)
        form.addWidget(QtWidgets.QLabel("Live trading requires ENABLE_LIVE_TRADING=true and config enablement."))
        form.addWidget(QtWidgets.QLabel("Default risk settings are conservative."))
        layout.addWidget(box)

        app_box = QtWidgets.QGroupBox("App")
        app_layout = QtWidgets.QHBoxLayout(app_box)
        self.update_url_input = QtWidgets.QLineEdit()
        self.update_url_input.setPlaceholderText("Update URL (releases page)")
        self.update_check_btn = QtWidgets.QPushButton("Check for Updates")
        self.update_check_btn.clicked.connect(self.check_for_updates)
        app_layout.addWidget(self.update_url_input)
        app_layout.addWidget(self.update_check_btn)
        app_layout.addStretch()
        layout.addWidget(app_box)

        layout.addStretch()
        return widget

    def _default_config_path(self) -> str:
        here = os.path.abspath(os.path.dirname(__file__))
        return os.path.normpath(os.path.join(here, "..", "config.yaml"))

    def set_timeframe(self, tf: str) -> None:
        idx = self.tf_input.findText(tf)
        if idx >= 0:
            self.tf_input.setCurrentIndex(idx)

    def apply_preset(self, preset: str) -> None:
        today = QtCore.QDate.currentDate()
        if preset == "Last 5 days":
            self.start_date.setDate(today.addDays(-5))
            self.end_date.setDate(today)
        elif preset == "Last 10 days":
            self.start_date.setDate(today.addDays(-10))
            self.end_date.setDate(today)
        elif preset == "Last 30 days":
            self.start_date.setDate(today.addDays(-30))
            self.end_date.setDate(today)
        elif preset == "YTD":
            self.start_date.setDate(QtCore.QDate(today.year(), 1, 1))
            self.end_date.setDate(today)

    def browse_config(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select config", os.getcwd(), "YAML (*.yaml *.yml)")
        if path:
            self.config_path.setText(path)
            self._refresh_symbols()

    def _load_config(self, path: str) -> Dict[str, Any]:
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def run_backtest(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        config = self._load_config(self.config_path.text())
        self.current_config = config
        config["broker"]["slippage_bps"] = float(self.slippage_input.value())
        config["broker"]["commission_per_share"] = float(self.commission_share_input.value())
        config["broker"]["commission_per_contract"] = float(self.commission_contract_input.value())
        symbol_csv = self.symbols_input.text().strip()
        symbols = config["symbols"]
        if symbol_csv:
            wanted = {s.strip() for s in symbol_csv.split(",")}
            symbols = [s for s in symbols if s["symbol"] in wanted]

        start = self.start_date.date().toPython()
        end = self.end_date.date().toPython()
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())

        request = BacktestRequest(
            config=config,
            symbols=symbols,
            start=start_dt,
            end=end_dt,
            timeframe=self.tf_input.currentText(),
        )

        self.progress.setVisible(True)
        self.run_btn.setEnabled(False)
        self.worker = BacktestWorker(request)
        self.worker.finished.connect(self.on_backtest_finished)
        self.worker.failed.connect(self.on_backtest_failed)
        self.worker.start()

    def on_backtest_finished(self, result: BacktestResult) -> None:
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)
        self.last_metrics = result.metrics
        self.last_trades = result.trades
        self.last_decision_traces = result.decision_traces
        self._render_metrics(result.metrics)
        self._render_trades(result.trades)
        self._render_performance(result.trades)
        self._render_analyzer(result.trades)
        self._render_risk()
        self._render_dashboard(result.metrics, result.trades, result.decision_traces)
        self._request_chart_update()
        self._mark_data_refreshed()
        self._evaluate_alerts()
        self.append_log(json.dumps({"event": "backtest_complete", "trades": len(result.trades)}))

    def on_backtest_failed(self, error: str) -> None:
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)
        self.append_log(json.dumps({"event": "backtest_failed", "error": error}))

    def _request_chart_update(self) -> None:
        config = self.current_config or self._load_config(self.config_path.text())
        self.current_config = config
        symbol_csv = self.symbols_input.text().strip()
        symbols = config["symbols"]
        if symbol_csv:
            wanted = {s.strip() for s in symbol_csv.split(",")}
            symbols = [s for s in symbols if s["symbol"] in wanted]
        if not symbols:
            return

        selected_symbol = self._selected_symbol()
        self._chart_symbol = selected_symbol
        symbol_cfg = next((s for s in symbols if s["symbol"] == selected_symbol), None)
        if symbol_cfg is None:
            symbol_cfg = {
                "symbol": selected_symbol,
                "data_source": "yfinance",
                "timezone": config.get("timezone", "US/Eastern"),
                "session": "rth",
            }
        start = self.start_date.date().toPython()
        end = self.end_date.date().toPython()
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())
        tz = symbol_cfg.get("timezone", config.get("timezone", "US/Eastern"))
        self._chart_session = symbol_cfg.get("session")
        self._chart_timezone = tz

        try:
            provider = self._provider_for_symbol(symbol_cfg)
            df = provider.get_bars(
                symbol=symbol_cfg["symbol"],
                start=start_dt,
                end=end_dt,
                timeframe=self.tf_input.currentText(),
                timezone=tz,
            )
            self.on_chart_data(df)
        except Exception as exc:
            self.on_chart_failed(str(exc))

    def on_chart_data(self, df) -> None:
        if df is None or df.empty:
            self.append_log(json.dumps({"event": "chart_empty"}))
            return
        # compute SMAs for chart
        df = df.copy()
        strategy = (self.current_config or {}).get("strategy", {})
        sma_fast = int(strategy.get("sma_fast", 20))
        sma_slow = int(strategy.get("sma_slow", 200))
        ema_window = int(strategy.get("ema_power_window", 9))
        atr_period = int(strategy.get("atr_period", 14))

        df["sma_fast"] = df["close"].rolling(window=sma_fast).mean()
        df["sma_slow"] = df["close"].rolling(window=sma_slow).mean()
        df["ema_9"] = df["close"].ewm(span=ema_window, adjust=False).mean()
        high_low = df["high"] - df["low"]
        high_prev = (df["high"] - df["close"].shift()).abs()
        low_prev = (df["low"] - df["close"].shift()).abs()
        tr = high_low.to_frame("hl")
        tr["hp"] = high_prev
        tr["lp"] = low_prev
        df["atr_14"] = tr.max(axis=1).ewm(alpha=1 / atr_period, adjust=False).mean()
        delta = df["close"].diff()
        gains = delta.clip(lower=0)
        losses = (-delta).clip(lower=0)
        avg_gain = gains.ewm(alpha=1 / 14, adjust=False).mean()
        avg_loss = losses.ewm(alpha=1 / 14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-9)
        df["rsi_14"] = 100 - (100 / (1 + rs))

        markers = self._trade_markers_for_symbol(getattr(self, "_chart_symbol", ""))
        transitions = self._n2w_transitions_for_symbol(getattr(self, "_chart_symbol", ""))
        tzname = getattr(self, "_chart_timezone", (self.current_config or {}).get("timezone", "US/Eastern"))
        self._update_data_quality(df, tzname)
        self.bt_chart.set_data(
            df,
            sma_fast=sma_fast,
            sma_slow=sma_slow,
            ema_window=ema_window,
            session=self._chart_session,
            markers=markers,
            transitions=transitions,
        )
        self.dashboard_chart.set_data(
            df,
            sma_fast=sma_fast,
            sma_slow=sma_slow,
            ema_window=ema_window,
            session=self._chart_session,
            markers=markers,
            transitions=transitions,
        )
        focus_ts = getattr(self, "_trace_focus_ts", None)
        if focus_ts:
            self.bt_chart.focus_on_timestamp(focus_ts)
            self.dashboard_chart.focus_on_timestamp(focus_ts)
            self._trace_focus_ts = None
        self.apply_chart_toggles()

    def on_chart_failed(self, error: str) -> None:
        self.append_log(json.dumps({"event": "chart_failed", "error": error}))
        self._data_quality = {"status": "ERROR"}
        self._update_header_bar()

    def apply_chart_toggles(self) -> None:
        show_sma_fast = self.toggle_sma_fast.isChecked() if hasattr(self, "toggle_sma_fast") else True
        show_sma_slow = self.toggle_sma_slow.isChecked() if hasattr(self, "toggle_sma_slow") else True
        show_ema = self.toggle_ema.isChecked() if hasattr(self, "toggle_ema") else True
        show_volume = self.toggle_volume.isChecked() if hasattr(self, "toggle_volume") else True
        show_atr = self.toggle_atr.isChecked() if hasattr(self, "toggle_atr") else True
        show_atr_bands = self.toggle_atr_bands.isChecked() if hasattr(self, "toggle_atr_bands") else True
        show_rsi = self.toggle_rsi.isChecked() if hasattr(self, "toggle_rsi") else True
        show_n2w = self.toggle_n2w.isChecked() if hasattr(self, "toggle_n2w") else True

        self.bt_chart.set_visibility(
            show_sma_fast=show_sma_fast,
            show_sma_slow=show_sma_slow,
            show_ema=show_ema,
            show_atr_bands=show_atr_bands,
            show_volume=show_volume,
            show_atr=show_atr,
            show_rsi=show_rsi,
        )
        self.dashboard_chart.set_visibility(
            show_sma_fast=show_sma_fast,
            show_sma_slow=show_sma_slow,
            show_ema=show_ema,
            show_atr_bands=show_atr_bands,
            show_volume=show_volume,
            show_atr=show_atr,
            show_rsi=show_rsi,
        )
        self.bt_chart.set_transition_visible(show_n2w)
        self.dashboard_chart.set_transition_visible(show_n2w)

    def on_pan_toggle(self, enabled: bool) -> None:
        self.bt_chart.set_panning_enabled(enabled)
        self.dashboard_chart.set_panning_enabled(enabled)

    def _selected_symbol(self) -> str:
        if hasattr(self, "watchlist") and self.watchlist.currentItem():
            return self.watchlist.currentItem().text()
        if hasattr(self, "dashboard_watchlist") and self.dashboard_watchlist.currentItem():
            return self.dashboard_watchlist.currentItem().text()
        # fallback
        symbol_csv = self.symbols_input.text().strip()
        if symbol_csv:
            return symbol_csv.split(",")[0].strip()
        return ""

    def _active_watchlist(self) -> QtWidgets.QListWidget | None:
        if hasattr(self, "watchlist") and self.watchlist.hasFocus():
            return self.watchlist
        if hasattr(self, "dashboard_watchlist") and self.dashboard_watchlist.hasFocus():
            return self.dashboard_watchlist
        return self.watchlist if hasattr(self, "watchlist") else None

    def _step_watchlist(self, delta: int) -> None:
        list_widget = self._active_watchlist()
        if list_widget is None or list_widget.count() == 0:
            return
        row = list_widget.currentRow()
        if row < 0:
            row = 0
        row = max(0, min(list_widget.count() - 1, row + delta))
        list_widget.setCurrentRow(row)

    def on_watchlist_change(self) -> None:
        self._request_chart_update()
        self.update_market_status()
        self._update_header_bar()

    def _refresh_symbols(self) -> None:
        try:
            config = self._load_config(self.config_path.text())
        except Exception:
            return
        self.current_config = config
        symbols = [s["symbol"] for s in config.get("symbols", [])]
        for sym in self.custom_watchlist:
            if sym not in symbols:
                symbols.append(sym)
        if hasattr(self, "watchlist"):
            self._populate_watchlist(self.watchlist, symbols)
            if hasattr(self, "watch_search"):
                self._apply_watchlist_filters()
        if hasattr(self, "dashboard_watchlist"):
            self._populate_watchlist(self.dashboard_watchlist, symbols)
        if hasattr(self, "replay_symbol"):
            self.replay_symbol.clear()
            self.replay_symbol.addItems(symbols)
        if symbols:
            if hasattr(self, "watchlist"):
                self.watchlist.setCurrentRow(0)
            if hasattr(self, "dashboard_watchlist"):
                self.dashboard_watchlist.setCurrentRow(0)
        self._update_watchlist_badges()

    def _populate_watchlist(self, list_widget: QtWidgets.QListWidget, symbols: List[str]) -> None:
        selected = list_widget.currentItem().text() if list_widget.currentItem() else None
        list_widget.clear()
        for sym in symbols:
            item = QtWidgets.QListWidgetItem(sym)
            item.setSizeHint(QtCore.QSize(0, 48))
            list_widget.addItem(item)
            widget = self._build_watch_item_widget(sym)
            list_widget.setItemWidget(item, widget)
        if selected:
            for i in range(list_widget.count()):
                if list_widget.item(i).text() == selected:
                    list_widget.setCurrentRow(i)
                    break

    def _build_watch_item_widget(self, symbol: str) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        label = QtWidgets.QLabel(symbol)
        label.setObjectName("symbol_label")
        label.setMinimumWidth(62)
        spark_container = QtWidgets.QWidget()
        spark_container.setObjectName("spark_container")
        spark_container.setMinimumWidth(120)
        spark_container.setFixedHeight(28)
        spark_layout = QtWidgets.QHBoxLayout(spark_container)
        spark_layout.setContentsMargins(0, 0, 0, 0)
        spark_layout.setSpacing(0)
        spark_placeholder = QtWidgets.QLabel("—")
        spark_placeholder.setStyleSheet("color:#6c7896;")
        spark_layout.addWidget(spark_placeholder)
        alert_btn = QtWidgets.QToolButton()
        alert_btn.setObjectName("alert_bell")
        alert_btn.setCheckable(True)
        alert_btn.setText("🔔")
        alert_btn.setToolTip("Toggle alert")
        alert_btn.toggled.connect(lambda checked, sym=symbol: self._toggle_symbol_alert(sym, checked))
        badge = QtWidgets.QLabel()
        badge.setObjectName("regime_badge")
        badge.setMinimumWidth(90)
        badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(spark_container)
        layout.addWidget(alert_btn)
        layout.addWidget(badge)
        self._apply_badge_style(badge, symbol)
        return widget

    def _apply_badge_style(self, badge: QtWidgets.QLabel, symbol: str) -> None:
        snap = self._snapshot_map.get(symbol)
        text = "--"
        regime = "neutral"
        if snap:
            text = f"{snap.get('regime', '')}/{snap.get('state', '')}"
            regime = snap.get("regime", "neutral").lower()
        badge.setText(text)
        if "bull" in regime:
            badge.setStyleSheet("background:#1d3b2a;color:#8cffc4;border-radius:8px;padding:2px 6px;")
        elif "bear" in regime:
            badge.setStyleSheet("background:#3b1d1d;color:#ff8c8c;border-radius:8px;padding:2px 6px;")
        else:
            badge.setStyleSheet("background:#2a3145;color:#cfd6ee;border-radius:8px;padding:2px 6px;")

    def _update_watchlist_badges(self) -> None:
        lists: List[QtWidgets.QListWidget] = []
        if hasattr(self, "watchlist"):
            lists.append(self.watchlist)
        if hasattr(self, "dashboard_watchlist"):
            lists.append(self.dashboard_watchlist)
        for list_widget in lists:
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                widget = list_widget.itemWidget(item)
                if widget is None:
                    continue
                badge = widget.findChild(QtWidgets.QLabel, "regime_badge")
                if badge:
                    self._apply_badge_style(badge, item.text())
                bell = widget.findChild(QtWidgets.QToolButton, "alert_bell")
                if bell:
                    bell.blockSignals(True)
                    bell.setChecked(item.text() in self._alert_symbols)
                    bell.blockSignals(False)

    def _provider_for_symbol(self, symbol_cfg: Dict[str, Any]):
        source = symbol_cfg.get("data_source", "yfinance")
        if source == "yfinance":
            return YFinanceDataProvider()
        if source == "csv":
            return CSVDataProvider(symbol_cfg["csv_path"])
        return FuturesStubProvider()

    def _filter_watchlist(self, text: str) -> None:
        _ = text
        self._apply_watchlist_filters()

    def _reset_watch_filters(self) -> None:
        if hasattr(self, "watch_regime_filter"):
            self.watch_regime_filter.setCurrentIndex(0)
        if hasattr(self, "watch_state_filter"):
            self.watch_state_filter.setCurrentIndex(0)
        if hasattr(self, "watch_atr_filter"):
            self.watch_atr_filter.setCurrentIndex(0)
        if hasattr(self, "watch_search"):
            self.watch_search.clear()
        self._apply_watchlist_filters()

    def _jump_to_symbol(self) -> None:
        if not hasattr(self, "watch_jump_input"):
            return
        symbol = self.watch_jump_input.text().strip().upper()
        if not symbol:
            return
        symbols = [self.watchlist.item(i).text() for i in range(self.watchlist.count())] if hasattr(self, "watchlist") else []
        if symbol not in symbols:
            if symbol not in self.custom_watchlist:
                self.custom_watchlist.append(symbol)
            self._refresh_symbols()
        for list_widget in [w for w in [getattr(self, "watchlist", None), getattr(self, "dashboard_watchlist", None)] if w]:
            for i in range(list_widget.count()):
                if list_widget.item(i).text() == symbol:
                    list_widget.setCurrentRow(i)
                    break
        self.watch_jump_input.clear()

    def _apply_watchlist_filters(self) -> None:
        text = self.watch_search.text().lower().strip() if hasattr(self, "watch_search") else ""
        regime_filter = self.watch_regime_filter.currentText() if hasattr(self, "watch_regime_filter") else "Regime: All"
        state_filter = self.watch_state_filter.currentText() if hasattr(self, "watch_state_filter") else "State: All"
        atr_filter = self.watch_atr_filter.currentText() if hasattr(self, "watch_atr_filter") else "ATR%: All"

        def atr_bucket_from_label(label: str) -> int | None:
            if "0.5-1" in label:
                return 1
            if "1-2" in label:
                return 2
            if "2%+" in label:
                return 3
            if "<0.5" in label:
                return 0
            return None

        regime_target = regime_filter.split(":")[-1].strip().lower()
        state_target = state_filter.split(":")[-1].strip().lower()
        atr_bucket = atr_bucket_from_label(atr_filter)

        lists: List[QtWidgets.QListWidget] = []
        if hasattr(self, "watchlist"):
            lists.append(self.watchlist)
        if hasattr(self, "dashboard_watchlist"):
            lists.append(self.dashboard_watchlist)

        for list_widget in lists:
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                symbol = item.text()
                hidden = False
                if text and text not in symbol.lower():
                    hidden = True
                snap = self._snapshot_map.get(symbol, {})
                if regime_target != "all":
                    regime_val = str(snap.get("regime", "")).lower()
                    if regime_target not in regime_val:
                        hidden = True
                if state_target != "all":
                    state_val = str(snap.get("state", "")).lower()
                    if state_target not in state_val:
                        hidden = True
                if atr_bucket is not None:
                    try:
                        atr_val = float(snap.get("atr", 0.0) or 0.0)
                    except Exception:
                        atr_val = 0.0
                    if self._bucket_index(atr_val) != atr_bucket:
                        hidden = True
                item.setHidden(hidden)

    def add_watch_symbol(self) -> None:
        symbol = self.watch_add_input.text().strip().upper()
        if not symbol:
            return
        if symbol not in self.custom_watchlist:
            self.custom_watchlist.append(symbol)
        self.watch_add_input.clear()
        self._refresh_symbols()

    def remove_watch_symbol(self) -> None:
        item = self.watchlist.currentItem()
        if not item:
            return
        symbol = item.text()
        if symbol in self.custom_watchlist:
            self.custom_watchlist.remove(symbol)
        self._refresh_symbols()

    def add_alert_rule(self) -> None:
        if not hasattr(self, "alert_symbol_input"):
            return
        symbol = self.alert_symbol_input.text().strip().upper()
        if not symbol:
            return
        rule = {
            "symbol": symbol,
            "condition": self.alert_condition_input.currentText(),
            "channel": self.alert_channel_input.currentText(),
            "enabled": self.alert_enabled_input.isChecked(),
            "notes": "",
        }
        self.alert_rules.append(rule)
        self.alert_symbol_input.clear()
        self._render_alert_rules()

    def remove_alert_rule(self) -> None:
        if not hasattr(self, "alerts_table"):
            return
        rows = sorted({idx.row() for idx in self.alerts_table.selectedIndexes()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self.alert_rules):
                self.alert_rules.pop(row)
        self._render_alert_rules()

    def _render_alert_rules(self) -> None:
        if not hasattr(self, "alerts_table"):
            return
        self._alert_table_populating = True
        self.alerts_table.setRowCount(0)
        for rule in self.alert_rules:
            row = self.alerts_table.rowCount()
            self.alerts_table.insertRow(row)
            self.alerts_table.setItem(row, 0, QtWidgets.QTableWidgetItem(rule.get("symbol", "")))
            self.alerts_table.setItem(row, 1, QtWidgets.QTableWidgetItem(rule.get("condition", "")))
            self.alerts_table.setItem(row, 2, QtWidgets.QTableWidgetItem(rule.get("channel", "")))
            enabled_item = QtWidgets.QTableWidgetItem("Yes" if rule.get("enabled") else "No")
            enabled_item.setFlags(enabled_item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
            self.alerts_table.setItem(row, 3, enabled_item)
            notes_item = QtWidgets.QTableWidgetItem(rule.get("notes", ""))
            self.alerts_table.setItem(row, 4, notes_item)
        self._alert_table_populating = False
        self._sync_alert_symbols()
        self._update_watchlist_badges()

    def _on_alert_table_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if getattr(self, "_alert_table_populating", False):
            return
        row = item.row()
        if row < 0 or row >= len(self.alert_rules):
            return
        rule = self.alert_rules[row]
        if item.column() == 0:
            rule["symbol"] = item.text().strip().upper()
        elif item.column() == 1:
            rule["condition"] = item.text().strip()
        elif item.column() == 2:
            rule["channel"] = item.text().strip()
        elif item.column() == 3:
            rule["enabled"] = item.text().strip().lower() in ("yes", "true", "1", "on")
        elif item.column() == 4:
            rule["notes"] = item.text()
        self._sync_alert_symbols()
        self._update_watchlist_badges()

    def _sync_alert_symbols(self) -> None:
        symbols = set()
        for rule in self.alert_rules:
            if rule.get("condition") == "N2W Breakout" and rule.get("enabled", True):
                symbols.add(rule.get("symbol", "").upper())
        self._alert_symbols = symbols

    def _toggle_symbol_alert(self, symbol: str, enabled: bool) -> None:
        if not symbol:
            return
        if enabled:
            exists = any(r for r in self.alert_rules if r.get("symbol") == symbol and r.get("condition") == "N2W Breakout")
            if not exists:
                self.alert_rules.append(
                    {
                        "symbol": symbol,
                        "condition": "N2W Breakout",
                        "channel": "In-app",
                        "enabled": True,
                        "notes": "",
                    }
                )
        else:
            self.alert_rules = [
                r for r in self.alert_rules if not (r.get("symbol") == symbol and r.get("condition") == "N2W Breakout")
            ]
        self._render_alert_rules()

    def _render_performance(self, trades: List[Any]) -> None:
        if not trades:
            return
        equity = []
        drawdown = []
        times = []
        eq = self.current_config.get("portfolio", {}).get("initial_cash", 0) if self.current_config else 0
        peak = eq
        for trade in trades:
            eq += trade.pnl
            peak = max(peak, eq)
            dd = (eq - peak) / peak if peak else 0
            equity.append(eq)
            drawdown.append(dd)
            times.append(QtCore.QDateTime(trade.exit_time))
        self.performance_panel.set_series(times, equity, drawdown)

    def _render_analyzer(self, trades: List[Any]) -> None:
        if not trades:
            return
        # Aggregate per symbol
        stats = {}
        for t in trades:
            stats.setdefault(t.symbol, []).append(t)

        self.analyzer_table.setRowCount(0)
        for symbol, tlist in stats.items():
            wins = [t for t in tlist if t.pnl > 0]
            losses = [t for t in tlist if t.pnl < 0]
            win_rate = len(wins) / len(tlist) if tlist else 0
            avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0
            expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
            avg_r = sum(t.r_multiple for t in tlist) / len(tlist) if tlist else 0
            avg_mae = sum(t.mae for t in tlist) / len(tlist) if tlist else 0

            row = self.analyzer_table.rowCount()
            self.analyzer_table.insertRow(row)
            self.analyzer_table.setItem(row, 0, QtWidgets.QTableWidgetItem(symbol))
            self.analyzer_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(len(tlist))))
            self.analyzer_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{win_rate:.2%}"))
            self.analyzer_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{avg_win:.2f}"))
            self.analyzer_table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{avg_loss:.2f}"))
            self.analyzer_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{expectancy:.2f}"))
            self.analyzer_table.setItem(row, 6, QtWidgets.QTableWidgetItem(f"{avg_r:.2f}"))
            self.analyzer_table.setItem(row, 7, QtWidgets.QTableWidgetItem(f"{avg_mae:.2f}"))

        if CHARTS_AVAILABLE:
            # R-multiple distribution
            r_vals = [t.r_multiple for t in trades]
            if r_vals:
                bins = [-3, -2, -1, 0, 1, 2, 3, 4]
                counts = [0] * (len(bins) - 1)
                for r in r_vals:
                    for i in range(len(bins) - 1):
                        if bins[i] <= r < bins[i + 1]:
                            counts[i] += 1
                            break
                self.r_dist_chart.removeAllSeries()
                bar_set = QBarSet("R dist")
                bar_set.append(counts)
                series = QBarSeries()
                series.append(bar_set)
                axis_x = QBarCategoryAxis()
                axis_x.append([f"{bins[i]}..{bins[i+1]}" for i in range(len(bins) - 1)])
                axis_y = QValueAxis()
                axis_y.setRange(0, max(counts) if counts else 1)
                self.r_dist_chart.addSeries(series)
                self.r_dist_chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
                self.r_dist_chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignLeft)
                series.attachAxis(axis_x)
                series.attachAxis(axis_y)

        # Update drilldown and journal
        self._render_trade_journal(trades)
        selected = None
        if self.analyzer_table.currentRow() >= 0:
            selected = self.analyzer_table.item(self.analyzer_table.currentRow(), 0).text()
        if not selected and stats:
            selected = list(stats.keys())[0]
        if selected:
            self._update_symbol_drilldown(selected, trades)

    def _on_analyzer_selection(self) -> None:
        if self.analyzer_table.currentRow() < 0:
            return
        symbol_item = self.analyzer_table.item(self.analyzer_table.currentRow(), 0)
        if symbol_item:
            self._update_symbol_drilldown(symbol_item.text(), self.last_trades or [])

    def _update_symbol_drilldown(self, symbol: str, trades: List[Any]) -> None:
        if not symbol:
            return
        symbol_trades = [t for t in trades if t.symbol == symbol]
        self.drill_symbol_label.setText(f"Symbol: {symbol}")
        if not symbol_trades:
            self.drill_winrate_label.setText("Win%: --")
            self.drill_expectancy_label.setText("Expectancy: --")
            self.drill_maxdd_label.setText("Max DD: --")
            if self.symbol_drill_chart is not None:
                self.symbol_drill_chart.removeAllSeries()
            return

        wins = [t for t in symbol_trades if t.pnl > 0]
        losses = [t for t in symbol_trades if t.pnl < 0]
        win_rate = len(wins) / len(symbol_trades) if symbol_trades else 0.0
        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0.0
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

        # Equity curve + max drawdown
        equity = []
        times = []
        eq = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in symbol_trades:
            eq += t.pnl
            peak = max(peak, eq)
            dd = (eq - peak) / peak if peak else 0.0
            max_dd = min(max_dd, dd)
            equity.append(eq)
            times.append(QtCore.QDateTime(t.exit_time))

        self.drill_winrate_label.setText(f"Win%: {win_rate:.2%}")
        self.drill_expectancy_label.setText(f"Expectancy: {expectancy:.2f}")
        self.drill_maxdd_label.setText(f"Max DD: {max_dd:.2%}")

        if self.symbol_drill_chart is None:
            return
        self.symbol_drill_chart.removeAllSeries()
        series = QLineSeries()
        for t, v in zip(times, equity):
            series.append(t.toMSecsSinceEpoch(), v)
        self.symbol_drill_chart.addSeries(series)
        axis_x = QDateTimeAxis()
        axis_x.setFormat("MM-dd")
        axis_x.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_x.setGridLineColor(QtGui.QColor("#1c273a"))
        axis_y = QValueAxis()
        axis_y.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_y.setGridLineColor(QtGui.QColor("#1c273a"))
        if times:
            axis_x.setRange(times[0], times[-1])
        if equity:
            axis_y.setRange(min(equity), max(equity))
        self.symbol_drill_chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.symbol_drill_chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

    def _trade_key(self, trade: Any) -> str:
        return f"{trade.symbol}|{trade.entry_time.isoformat()}|{trade.exit_time.isoformat()}"

    def _render_trade_journal(self, trades: List[Any]) -> None:
        if not hasattr(self, "journal_table"):
            return
        self._journal_populating = True
        self.journal_table.setRowCount(0)
        for trade in trades:
            row = self.journal_table.rowCount()
            self.journal_table.insertRow(row)
            self.journal_table.setItem(row, 0, QtWidgets.QTableWidgetItem(trade.symbol))
            self.journal_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(trade.entry_time)))
            self.journal_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(trade.exit_time)))
            pnl_item = QtWidgets.QTableWidgetItem(f"{trade.pnl:.2f}")
            self.journal_table.setItem(row, 3, pnl_item)
            note_key = self._trade_key(trade)
            note_item = QtWidgets.QTableWidgetItem(self.trade_notes.get(note_key, ""))
            self.journal_table.setItem(row, 4, note_item)
        self._journal_populating = False

    def _on_journal_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if getattr(self, "_journal_populating", False):
            return
        if item.column() != 4:
            return
        row = item.row()
        if row < 0 or row >= len(self.last_trades or []):
            return
        trade = self.last_trades[row]
        self.trade_notes[self._trade_key(trade)] = item.text()

    def _on_journal_selection_changed(self) -> None:
        if not hasattr(self, "journal_table") or not self.last_trades:
            return
        row = self.journal_table.currentRow()
        if row < 0 or row >= len(self.last_trades):
            return
        trade = self.last_trades[row]
        trace = self._trace_for_trade(trade)
        if trace is None:
            self.journal_detail.setPlainText("No decision trace found for this trade.")
            return
        detail = [
            f"Symbol: {trace.symbol}",
            f"Time: {trace.timestamp}",
            f"Regime: {trace.regime}",
            f"State: {trace.narrow_wide}",
            f"Transition: {trace.transition_n2w}",
            f"Spread: {trace.spread}",
            f"ATR%: {trace.atr_percent}",
            f"Action: {trace.action}",
            f"Reason: {trace.reason}",
            f"Triggers: {trace.triggers}",
        ]
        self.journal_detail.setPlainText("\n".join(detail))

    def _trace_for_trade(self, trade: Any) -> Any | None:
        if not self.last_decision_traces:
            return None
        for trace in reversed(self.last_decision_traces):
            if trace.symbol != trade.symbol:
                continue
            if abs((trace.timestamp - trade.entry_time).total_seconds()) <= 600:
                return trace
        return None

    def send_test_alert(self) -> None:
        symbol = self._selected_symbol() or "TEST"
        payload = {"symbol": symbol, "condition": "Test", "detail": "Test alert", "timestamp": datetime.utcnow().isoformat()}
        self._dispatch_alert("In-app", payload)
        self._dispatch_alert("Log", payload)
        self._dispatch_alert("Webhook", payload)
        self._dispatch_alert("Telegram", payload)

    def _evaluate_alerts(self) -> None:
        if not self.alert_rules:
            return
        now = datetime.utcnow()
        config = self.current_config or {}
        alert_cfg = config.get("alerts", {})
        threshold = float(alert_cfg.get("atr_spike_threshold", 0.02))
        min_interval = int(alert_cfg.get("min_interval_sec", self._alert_min_interval_sec))
        self._alert_min_interval_sec = min_interval

        # Build latest traces per symbol for quick lookup
        last_trace: Dict[str, Any] = {}
        for tr in reversed(self.last_decision_traces or []):
            sym = getattr(tr, "symbol", None)
            if sym and sym not in last_trace:
                last_trace[sym] = tr

        for rule in self.alert_rules:
            if not rule.get("enabled", True):
                continue
            symbol = rule.get("symbol", "").upper()
            condition = rule.get("condition", "")
            channel = rule.get("channel", "In-app")
            if not symbol:
                continue

            fired = False
            detail = ""
            event_ts = now

            if condition == "N2W Breakout":
                tr = last_trace.get(symbol)
                if tr and getattr(tr, "transition_n2w", False):
                    event_ts = tr.timestamp
                    fired = True
                    detail = f"Transition N2W | action={getattr(tr, 'action', '')}"
            elif condition == "Regime Change":
                current = str(self._snapshot_map.get(symbol, {}).get("regime", ""))
                previous = self._prev_regime_map.get(symbol)
                if current and previous and current != previous:
                    fired = True
                    detail = f"{previous} → {current}"
                self._prev_regime_map[symbol] = current
            elif condition == "ATR Spike":
                try:
                    atr_val = float(self._snapshot_map.get(symbol, {}).get("atr", 0.0) or 0.0)
                except Exception:
                    atr_val = 0.0
                prev = self._prev_atr_map.get(symbol, 0.0)
                if prev < threshold <= atr_val:
                    fired = True
                    detail = f"ATR% {atr_val:.2%} >= {threshold:.2%}"
                self._prev_atr_map[symbol] = atr_val
            elif condition in ("SMA20 Cross", "SMA200 Cross"):
                snap = self._snapshot_map.get(symbol, {})
                try:
                    close_val = float(snap.get("close", 0.0) or 0.0)
                except Exception:
                    close_val = 0.0
                sma_key = "sma_fast" if condition == "SMA20 Cross" else "sma_slow"
                try:
                    sma_val = float(snap.get(sma_key, 0.0) or 0.0)
                except Exception:
                    sma_val = 0.0
                prev = self._prev_sma_map.get(symbol, {"close": close_val, "sma_fast": sma_val, "sma_slow": sma_val})
                prev_close = prev.get("close", close_val)
                prev_sma = prev.get(sma_key, sma_val)
                crossed_up = prev_close <= prev_sma and close_val > sma_val
                crossed_down = prev_close >= prev_sma and close_val < sma_val
                if crossed_up or crossed_down:
                    fired = True
                    direction = "up" if crossed_up else "down"
                    detail = f"{condition} cross {direction} (close {close_val:.2f}, sma {sma_val:.2f})"
                prev["close"] = close_val
                prev[sma_key] = sma_val
                self._prev_sma_map[symbol] = prev

            if not fired:
                continue

            if not self._should_fire_alert(symbol, condition, event_ts, min_interval):
                continue

            payload = {
                "symbol": symbol,
                "condition": condition,
                "detail": detail,
                "timestamp": event_ts.isoformat(),
            }
            self._dispatch_alert(channel, payload)

    def _should_fire_alert(self, symbol: str, condition: str, event_ts: datetime, min_interval: int) -> bool:
        key = (symbol, condition)
        last = self._alert_last_fired.get(key)
        if last and (event_ts - last).total_seconds() < min_interval:
            return False
        self._alert_last_fired[key] = event_ts
        return True

    def _dispatch_alert(self, channel: str, payload: Dict[str, Any]) -> None:
        msg = f"[ALERT] {payload.get('symbol')} {payload.get('condition')} | {payload.get('detail')}"
        if channel in ("In-app", "Log"):
            self.append_log(json.dumps({"event": "alert", **payload}))
            self._notify_system(msg)
            self._record_alert(payload)
            return
        if channel == "Webhook":
            url = self.alert_webhook_url.text().strip() if hasattr(self, "alert_webhook_url") else ""
            if not url:
                self._log_alert_error("webhook_missing", payload)
                return
            self._post_webhook(url, payload)
            return
        if channel == "Telegram":
            token = self.alert_telegram_token.text().strip() if hasattr(self, "alert_telegram_token") else ""
            chat_id = self.alert_telegram_chat.text().strip() if hasattr(self, "alert_telegram_chat") else ""
            if not token or not chat_id:
                self._log_alert_error("telegram_missing", payload)
                return
            self._post_telegram(token, chat_id, msg)

    def _notify_system(self, message: str) -> None:
        try:
            if not hasattr(self, "_tray"):
                icon = QtGui.QIcon()
                asset_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "narrowwide.png"))
                if os.path.exists(asset_path):
                    icon = QtGui.QIcon(asset_path)
                self._tray = QtWidgets.QSystemTrayIcon(icon, self)
                self._tray.setVisible(True)
            self._tray.showMessage("NarrowWide", message, QtWidgets.QSystemTrayIcon.MessageIcon.Information, 5000)
        except Exception:
            pass

    def _post_webhook(self, url: str, payload: Dict[str, Any]) -> None:
        import threading
        import urllib.request
        import hashlib
        import hmac

        def _send():
            try:
                secret = ""
                if self.current_config:
                    secret = self.current_config.get("alerts", {}).get("webhook_secret", "")
                data = json.dumps(payload).encode("utf-8")
                headers = {"Content-Type": "application/json"}
                if secret:
                    sig = hmac.new(secret.encode("utf-8"), data, hashlib.sha256).hexdigest()
                    headers["X-NarrowWide-Signature"] = sig
                req = urllib.request.Request(url, data=data, headers=headers)
                for attempt in range(3):
                    try:
                        urllib.request.urlopen(req, timeout=5)
                        self._record_alert(payload)
                        return
                    except Exception as exc:
                        if attempt == 2:
                            raise exc
                        time.sleep(1 + attempt)
            except Exception as exc:
                self._log_alert_error(f"webhook_error:{exc}", payload)

        threading.Thread(target=_send, daemon=True).start()

    def _post_telegram(self, token: str, chat_id: str, message: str) -> None:
        import threading
        import urllib.parse
        import urllib.request

        def _send():
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
                urllib.request.urlopen(url, data=data, timeout=5)
                self._record_alert({"symbol": "TELEGRAM", "condition": "sent", "detail": message, "timestamp": datetime.utcnow().isoformat()})
            except Exception as exc:
                self._log_alert_error(f"telegram_error:{exc}", {"detail": message})

        threading.Thread(target=_send, daemon=True).start()

    def _record_alert(self, payload: Dict[str, Any]) -> None:
        self._alert_history.append(payload)
        if len(self._alert_history) > 200:
            self._alert_history = self._alert_history[-200:]
        self._update_alert_health()

    def _log_alert_error(self, error: str, payload: Dict[str, Any]) -> None:
        self._alert_last_error = error
        self._alert_last_error_at = datetime.utcnow()
        self.append_log(json.dumps({"event": "alert_error", "error": error, **payload}))
        self._update_alert_health()

        self._render_traces_table()

    def _render_traces_table(self) -> None:
        if not hasattr(self, "traces_table"):
            return
        traces = self.last_decision_traces or []
        sym_filter = self.trace_filter_symbol.text().strip().lower() if hasattr(self, "trace_filter_symbol") else ""
        act_filter = self.trace_filter_action.text().strip().lower() if hasattr(self, "trace_filter_action") else ""
        reason_filter = self.trace_filter_reason.text().strip().lower() if hasattr(self, "trace_filter_reason") else ""

        self.traces_table.setRowCount(0)
        for t in traces:
            if sym_filter and sym_filter not in t.symbol.lower():
                continue
            if act_filter and act_filter not in str(t.action).lower():
                continue
            if reason_filter and reason_filter not in str(t.reason).lower():
                continue
            row = self.traces_table.rowCount()
            self.traces_table.insertRow(row)
            sym_item = QtWidgets.QTableWidgetItem(t.symbol)
            sym_item.setData(QtCore.Qt.ItemDataRole.UserRole, t)
            self.traces_table.setItem(row, 0, sym_item)
            self.traces_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(t.timestamp)))
            self.traces_table.setItem(row, 2, QtWidgets.QTableWidgetItem(t.regime.value))
            self.traces_table.setItem(row, 3, QtWidgets.QTableWidgetItem(t.narrow_wide.value))
            self.traces_table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{t.spread:.4f}" if t.spread else ""))
            self.traces_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{t.atr_percent:.4f}" if t.atr_percent else ""))
            self.traces_table.setItem(row, 6, QtWidgets.QTableWidgetItem(str(t.action)))
            self.traces_table.setItem(row, 7, QtWidgets.QTableWidgetItem(str(t.reason)))

    def on_trace_selected(self) -> None:
        items = self.traces_table.selectedItems()
        if not items:
            return
        row = items[0].row()
        symbol_item = self.traces_table.item(row, 0)
        symbol = symbol_item.text() if symbol_item else ""
        trace = symbol_item.data(QtCore.Qt.ItemDataRole.UserRole) if symbol_item else None
        if trace:
            try:
                self._trace_focus_ts = int(QtCore.QDateTime(trace.timestamp).toMSecsSinceEpoch())
            except Exception:
                self._trace_focus_ts = None
        # select symbol in watchlist and refresh chart
        for i in range(self.watchlist.count()):
            if self.watchlist.item(i).text() == symbol:
                self.watchlist.setCurrentRow(i)
                return
        # if symbol not in watchlist, add it
        if symbol not in self.custom_watchlist:
            self.custom_watchlist.append(symbol)
            self._refresh_symbols()
            for i in range(self.watchlist.count()):
                if self.watchlist.item(i).text() == symbol:
                    self.watchlist.setCurrentRow(i)
                    return

    def _render_risk(self) -> None:
        if not self.current_config:
            return
        risk_cfg = self.current_config.get("risk", {})
        rows = [
            ("Risk/Trade", risk_cfg.get("risk_per_trade")),
            ("Max Daily Loss %", risk_cfg.get("max_daily_loss_pct")),
            ("Max Cons. Losses", risk_cfg.get("max_consecutive_losses")),
            ("Max Open Positions", risk_cfg.get("max_open_positions")),
            ("Max Leverage", risk_cfg.get("max_leverage")),
            ("Max Stop %", risk_cfg.get("max_stop_pct")),
        ]
        self.risk_table.setRowCount(0)
        for k, v in rows:
            row = self.risk_table.rowCount()
            self.risk_table.insertRow(row)
            self.risk_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(k)))
            self.risk_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(v)))

    def load_replay_data(self) -> None:
        config = self.current_config or self._load_config(self.config_path.text())
        symbol = self.replay_symbol.currentText().strip()
        if not symbol:
            return
        symbol_cfg = next((s for s in config["symbols"] if s["symbol"] == symbol), None)
        if symbol_cfg is None:
            symbol_cfg = {"symbol": symbol, "data_source": "yfinance", "timezone": config.get("timezone", "US/Eastern")}
        self.replay_session = symbol_cfg.get("session")
        start = self.replay_start.date().toPython()
        end = self.replay_end.date().toPython()
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())
        provider = self._provider_for_symbol(symbol_cfg)
        df = provider.get_bars(
            symbol=symbol,
            start=start_dt,
            end=end_dt,
            timeframe=self.replay_tf.currentText(),
            timezone=symbol_cfg.get("timezone", config.get("timezone", "US/Eastern")),
        )
        if df.empty:
            self.replay_status.setText("No data")
            return
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Precompute signals and snapshots
        strategy = NarrowToWideStrategy(config["strategy"], self.logger)
        signals = []
        snapshots = []
        for i, row in df.iterrows():
            bar = Bar(
                timestamp=row["timestamp"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
            )
            sigs = strategy.on_bar(symbol, bar)
            snap = strategy.state_snapshot(symbol)
            snapshots.append(snap)
            for s in sigs:
                signals.append(
                    {
                        "idx": i,
                        "side": "buy" if s.side.value == "buy" else "sell",
                        "price": bar.close,
                        "ts": int(QtCore.QDateTime(bar.timestamp).toMSecsSinceEpoch()),
                    }
                )

        self.replay_df = df
        self.replay_signals = signals
        self.replay_snapshots = snapshots
        self.replay_slider.setMinimum(0)
        self.replay_slider.setMaximum(len(df) - 1)
        self.replay_slider.setValue(0)
        self.update_replay_view(0)

    def update_replay_view(self, idx: int) -> None:
        if not hasattr(self, "replay_df"):
            return
        df = self.replay_df.iloc[: idx + 1]
        markers = [m for m in self.replay_signals if m["idx"] <= idx]
        self.replay_chart.set_data(df, session=self.replay_session, markers=markers)
        snap = self.replay_snapshots[idx] if idx < len(self.replay_snapshots) else None
        if snap:
            self.replay_status.setText(
                f"{df.iloc[-1]['timestamp']} | Regime: {snap.regime.value} | State: {snap.narrow_wide.value} | Spread: {snap.spread}"
            )

    def _step_replay(self, step: int) -> None:
        if not hasattr(self, "replay_df"):
            return
        new_val = max(0, min(self.replay_slider.maximum(), self.replay_slider.value() + step))
        self.replay_slider.setValue(new_val)

    def toggle_replay_play(self, enabled: bool) -> None:
        if not hasattr(self, "replay_timer"):
            self.replay_timer = QtCore.QTimer()
            self.replay_timer.timeout.connect(lambda: self._step_replay(1))
        if enabled:
            self.replay_timer.start(self._replay_interval_ms())
            self.replay_play.setText("Pause")
        else:
            self.replay_timer.stop()
            self.replay_play.setText("Play")

    def update_replay_speed(self, _: str) -> None:
        if hasattr(self, "replay_timer") and self.replay_timer.isActive():
            self.replay_timer.start(self._replay_interval_ms())

    def _replay_interval_ms(self) -> int:
        speed_text = self.replay_speed.currentText() if hasattr(self, "replay_speed") else "1x"
        try:
            speed = float(speed_text.replace("x", ""))
        except ValueError:
            speed = 1.0
        base = 200
        return max(25, int(base / max(speed, 0.1)))

    def _trade_markers_for_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        markers: List[Dict[str, Any]] = []
        if not symbol or not self.last_trades:
            return markers
        for trade in self.last_trades:
            if trade.symbol != symbol:
                continue
            try:
                ts = int(QtCore.QDateTime(trade.entry_time).toMSecsSinceEpoch())
            except Exception:
                continue
            side_val = str(trade.side).lower() if trade.side is not None else "buy"
            if isinstance(trade.side, Side):
                side_val = trade.side.value
            side = "sell" if "sell" in side_val else "buy"
            markers.append({"ts": ts, "price": trade.entry_price, "side": side})
            try:
                exit_ts = int(QtCore.QDateTime(trade.exit_time).toMSecsSinceEpoch())
                markers.append({"ts": exit_ts, "price": trade.exit_price, "side": "exit"})
            except Exception:
                continue
        return markers

    def _n2w_transitions_for_symbol(self, symbol: str) -> List[int]:
        transitions: List[int] = []
        if not symbol or not self.last_decision_traces:
            return transitions
        for trace in self.last_decision_traces:
            if getattr(trace, "symbol", None) != symbol:
                continue
            if not getattr(trace, "transition_n2w", False):
                continue
            try:
                ts = int(QtCore.QDateTime(trace.timestamp).toMSecsSinceEpoch())
            except Exception:
                continue
            transitions.append(ts)
        return transitions

    def refresh_monitor(self) -> None:
        config = self.current_config or self._load_config(self.config_path.text())
        symbols = config.get("symbols", [])
        self.monitor_table.setRowCount(0)
        snapshot_rows = []
        for sym in symbols:
            provider = self._provider_for_symbol(sym)
            end = datetime.utcnow()
            start = end - timedelta(days=5)
            try:
                df = provider.get_bars(
                    symbol=sym["symbol"],
                    start=start,
                    end=end,
                    timeframe="1m",
                    timezone=sym.get("timezone", config.get("timezone", "US/Eastern")),
                )
            except Exception:
                continue
            if df.empty:
                continue
            df = df.sort_values("timestamp")
            strategy_cfg = config.get("strategy", {})
            sma_fast = int(strategy_cfg.get("sma_fast", 20))
            sma_slow = int(strategy_cfg.get("sma_slow", 200))
            df["sma_fast"] = df["close"].rolling(window=sma_fast).mean()
            df["sma_slow"] = df["close"].rolling(window=sma_slow).mean()
            # compute last snapshot
            strategy = NarrowToWideStrategy(config["strategy"], self.logger)
            for _, row in df.iterrows():
                bar = Bar(
                    timestamp=row["timestamp"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                )
                strategy.on_bar(sym["symbol"], bar)
            snap = strategy.state_snapshot(sym["symbol"])
            last_close = float(df.iloc[-1]["close"])
            last_sma_fast = float(df.iloc[-1]["sma_fast"]) if "sma_fast" in df.columns else None
            last_sma_slow = float(df.iloc[-1]["sma_slow"]) if "sma_slow" in df.columns else None
            row_idx = self.monitor_table.rowCount()
            self.monitor_table.insertRow(row_idx)
            self.monitor_table.setItem(row_idx, 0, QtWidgets.QTableWidgetItem(sym["symbol"]))
            self.monitor_table.setItem(row_idx, 1, QtWidgets.QTableWidgetItem(f"{df.iloc[-1]['close']:.2f}"))
            self.monitor_table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(snap.regime.value if snap else ""))
            self.monitor_table.setItem(row_idx, 3, QtWidgets.QTableWidgetItem(snap.narrow_wide.value if snap else ""))
            self.monitor_table.setItem(row_idx, 4, QtWidgets.QTableWidgetItem(f"{snap.atr_percent:.4f}" if snap and snap.atr_percent else ""))
            snapshot_rows.append(
                {
                    "symbol": sym["symbol"],
                    "regime": snap.regime.value if snap else "",
                    "state": snap.narrow_wide.value if snap else "",
                    "spread": f"{snap.spread:.4f}" if snap and snap.spread else "",
                    "atr": f"{snap.atr_percent:.4f}" if snap and snap.atr_percent else "",
                    "close": f"{last_close:.4f}",
                    "sma_fast": f"{last_sma_fast:.4f}" if last_sma_fast is not None else "",
                    "sma_slow": f"{last_sma_slow:.4f}" if last_sma_slow is not None else "",
                }
            )
        self._render_dashboard_snapshot(snapshot_rows)
        self._mark_data_refreshed()
        self._evaluate_alerts()

    def load_config_into_editor(self) -> None:
        path = self.config_path.text()
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.config_editor.setPlainText(f.read())
                self.config_status.setText("Loaded")
        except Exception as exc:
            self.config_status.setText(f"Load failed: {exc}")

    def validate_config_editor(self) -> None:
        import yaml
        try:
            cfg = yaml.safe_load(self.config_editor.toPlainText())
            if not isinstance(cfg, dict):
                raise ValueError("Config must be a mapping")
            self.config_status.setText("Valid")
        except Exception as exc:
            self.config_status.setText(f"Invalid: {exc}")

    def save_config_from_editor(self) -> None:
        path = self.config_path.text()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.config_editor.toPlainText())
            self.config_status.setText("Saved")
            self._refresh_symbols()
        except Exception as exc:
            self.config_status.setText(f"Save failed: {exc}")

    def export_trades_csv(self) -> None:
        if not self.last_trades:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export Trades", os.getcwd(), "CSV (*.csv)")
        if not path:
            return
        import csv

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["symbol", "entry_time", "exit_time", "qty", "entry_price", "exit_price", "pnl", "mfe", "mae", "r_multiple"])
            for t in self.last_trades:
                writer.writerow([t.symbol, t.entry_time, t.exit_time, t.qty, t.entry_price, t.exit_price, t.pnl, t.mfe, t.mae, t.r_multiple])

    def export_metrics_csv(self) -> None:
        if not hasattr(self, "last_metrics") or not self.last_metrics:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export Metrics", os.getcwd(), "CSV (*.csv)")
        if not path:
            return
        import csv

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "value"])
            for k, v in self.last_metrics.items():
                writer.writerow([k, v])

    def export_traces_csv(self) -> None:
        if not self.last_decision_traces:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export Decision Traces", os.getcwd(), "CSV (*.csv)")
        if not path:
            return
        import csv

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["symbol", "timestamp", "regime", "narrow_wide", "transition_n2w", "spread", "atr_percent", "action", "reason"])
            for t in self.last_decision_traces:
                writer.writerow([t.symbol, t.timestamp, t.regime, t.narrow_wide, t.transition_n2w, t.spread, t.atr_percent, t.action, t.reason])

    def _load_settings(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = self.settings.value("window/state")
        if state:
            self.restoreState(state)
        self.custom_watchlist = json.loads(self.settings.value("watchlist/custom", "[]"))
        last_config = self.settings.value("ui/last_config")
        if last_config:
            self.config_path.setText(last_config)
        last_update_url = self.settings.value("ui/update_url")
        if last_update_url and hasattr(self, "update_url_input"):
            self.update_url_input.setText(last_update_url)
        else:
            cfg = None
            try:
                cfg = self._load_config(self.config_path.text())
            except Exception:
                cfg = None
            if cfg and hasattr(self, "update_url_input"):
                self.update_url_input.setText(cfg.get("app", {}).get("update_url", ""))
        last_tf = self.settings.value("ui/last_tf")
        if last_tf:
            self.set_timeframe(last_tf)
        alert_rules = self.settings.value("alerts/rules")
        if alert_rules:
            try:
                self.alert_rules = json.loads(alert_rules)
            except Exception:
                self.alert_rules = []
        webhook_url = self.settings.value("alerts/webhook_url")
        if webhook_url and hasattr(self, "alert_webhook_url"):
            self.alert_webhook_url.setText(webhook_url)
        tg_token = self.settings.value("alerts/telegram_token")
        if tg_token and hasattr(self, "alert_telegram_token"):
            self.alert_telegram_token.setText(tg_token)
        tg_chat = self.settings.value("alerts/telegram_chat")
        if tg_chat and hasattr(self, "alert_telegram_chat"):
            self.alert_telegram_chat.setText(tg_chat)
        journal_notes = self.settings.value("journal/notes")
        if journal_notes:
            try:
                self.trade_notes = json.loads(journal_notes)
            except Exception:
                self.trade_notes = {}
        self._render_alert_rules()
        self._refresh_symbols()
        chart_sizes = self.settings.value("layout/chart_splitter_sizes")
        if chart_sizes:
            try:
                sizes = json.loads(chart_sizes)
                self.bt_chart.set_splitter_sizes(sizes)
                self.dashboard_chart.set_splitter_sizes(sizes)
            except Exception:
                pass
        if hasattr(self, "trades_splitter"):
            state = self.settings.value("layout/trades_splitter")
            if state:
                self.trades_splitter.restoreState(state)

    def _save_settings(self) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        self.settings.setValue("watchlist/custom", json.dumps(self.custom_watchlist))
        self.settings.setValue("ui/last_config", self.config_path.text())
        self.settings.setValue("ui/last_tf", self.tf_input.currentText())
        if hasattr(self, "update_url_input"):
            self.settings.setValue("ui/update_url", self.update_url_input.text())
        self.settings.setValue("alerts/rules", json.dumps(self.alert_rules))
        if hasattr(self, "alert_webhook_url"):
            self.settings.setValue("alerts/webhook_url", self.alert_webhook_url.text().strip())
        if hasattr(self, "alert_telegram_token"):
            self.settings.setValue("alerts/telegram_token", self.alert_telegram_token.text().strip())
        if hasattr(self, "alert_telegram_chat"):
            self.settings.setValue("alerts/telegram_chat", self.alert_telegram_chat.text().strip())
        self.settings.setValue("journal/notes", json.dumps(self.trade_notes))
        # Save splitter sizes if available
        if hasattr(self, "trades_splitter"):
            self.settings.setValue("layout/trades_splitter", self.trades_splitter.saveState())
        self.settings.setValue("layout/chart_splitter_sizes", json.dumps(self.bt_chart.splitter_sizes()))

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._save_settings()
        super().closeEvent(event)

    def _render_metrics(self, metrics: Dict[str, float]) -> None:
        self.metrics_table.setRowCount(0)
        for k, v in metrics.items():
            row = self.metrics_table.rowCount()
            self.metrics_table.insertRow(row)
            self.metrics_table.setItem(row, 0, QtWidgets.QTableWidgetItem(k))
            self.metrics_table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{v:.4f}"))

    def _render_trades(self, trades: List[Any]) -> None:
        self.trades_table.setRowCount(0)
        for trade in trades:
            row = self.trades_table.rowCount()
            self.trades_table.insertRow(row)
            self.trades_table.setItem(row, 0, QtWidgets.QTableWidgetItem(trade.symbol))
            self.trades_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(trade.entry_time)))
            self.trades_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(trade.exit_time)))
            self.trades_table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(trade.qty)))
            self.trades_table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{trade.entry_price:.2f}"))
            self.trades_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{trade.exit_price:.2f}"))
            self.trades_table.setItem(row, 6, QtWidgets.QTableWidgetItem(f"{trade.pnl:.2f}"))

    def append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def show_about(self) -> None:
        version = "0.1.0"
        if self.current_config:
            version = self.current_config.get("app", {}).get("version", version)
        QtWidgets.QMessageBox.information(
            self,
            "About NarrowWide",
            f"NarrowWide Trading Console\nVersion {version}\nEducational use only. Not financial advice.",
        )

    def check_for_updates(self) -> None:
        url = ""
        if hasattr(self, "update_url_input"):
            url = self.update_url_input.text().strip()
        if not url and self.current_config:
            url = self.current_config.get("app", {}).get("update_url", "")
        if not url:
            QtWidgets.QMessageBox.information(self, "Updates", "No update URL configured.")
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def update_market_status(self) -> None:
        if not hasattr(self, "market_status_label"):
            return
        config = self.current_config
        if config is None:
            try:
                config = self._load_config(self.config_path.text())
            except Exception:
                config = None
        if config is None:
            return

        symbol = self._selected_symbol()
        symbol_cfg = next((s for s in config.get("symbols", []) if s["symbol"] == symbol), None)
        if symbol_cfg is None and config.get("symbols"):
            symbol_cfg = config["symbols"][0]
            symbol = symbol_cfg["symbol"]

        tzname = (symbol_cfg or {}).get("timezone", config.get("timezone", "US/Eastern"))
        session = (symbol_cfg or {}).get("session", "rth")
        tz = pytz.timezone(tzname)
        now = datetime.now(tz)

        if session == "rth":
            status, countdown = self._rth_status(now, tz)
        else:
            status = "OPEN"
            countdown = "24h session"

        self.market_symbol_label.setText(f"Symbol: {symbol} ({session.upper()})")
        self.market_status_label.setText(f"Market: {status}")
        if status == "OPEN":
            color = "#4ed298"
            session_state = "open"
        elif status in ("PRE", "AFTER"):
            color = "#ffcc8c"
            session_state = "pre" if status == "PRE" else "after"
        else:
            color = "#ff5a5a"
            session_state = "closed"
        self.market_status_label.setStyleSheet(f"color: {color};")
        self.market_countdown_label.setText(countdown)
        self._market_status = status
        self._market_countdown = countdown
        self._market_symbol = symbol
        self._refresh_interval_sec = int(config.get("app", {}).get("refresh_interval_sec", self._refresh_interval_sec))
        self.setProperty("session", session_state)
        self.style().unpolish(self)
        self.style().polish(self)
        self._update_header_bar()

    def _rth_status(self, now: datetime, tz) -> tuple[str, str]:
        open_time = dtime(9, 30)
        close_time = dtime(16, 0)

        def next_weekday(d: datetime) -> datetime:
            nd = d
            while nd.weekday() >= 5:
                nd = nd + timedelta(days=1)
            return nd

        today = now.date()
        open_dt = tz.localize(datetime.combine(today, open_time))
        close_dt = tz.localize(datetime.combine(today, close_time))

        # weekend handling
        if now.weekday() >= 5:
            next_day = next_weekday(now + timedelta(days=1))
            next_open = tz.localize(datetime.combine(next_day.date(), open_time))
            return "CLOSED", f"Opens in {self._format_countdown(next_open - now)}"

        if now < open_dt:
            return "PRE", f"Opens in {self._format_countdown(open_dt - now)}"
        if now > close_dt:
            next_day = next_weekday(now + timedelta(days=1))
            next_open = tz.localize(datetime.combine(next_day.date(), open_time))
            return "AFTER", f"Opens in {self._format_countdown(next_open - now)}"

        return "OPEN", f"Closes in {self._format_countdown(close_dt - now)}"

    def _mark_data_refreshed(self) -> None:
        self._last_refresh_at = datetime.utcnow()
        self._next_refresh_due = self._last_refresh_at + timedelta(seconds=self._refresh_interval_sec)
        self._update_header_bar()

    def _tick_header_timer(self) -> None:
        self._update_header_bar()

    def _update_header_bar(self) -> None:
        if not hasattr(self, "header_market_label"):
            return
        status = getattr(self, "_market_status", "--")
        countdown = getattr(self, "_market_countdown", "--")
        symbol = self._selected_symbol() or getattr(self, "_market_symbol", "--")
        self.header_market_label.setText(f"Market: {status}")
        self.header_countdown_label.setText(countdown)
        color = "#4ed298" if status == "OPEN" else "#ff5a5a"
        self.header_market_label.setStyleSheet(f"color: {color};")

        refresh_text = "Data refresh: --"
        if self._next_refresh_due is not None:
            delta = self._next_refresh_due - datetime.utcnow()
            if delta.total_seconds() <= 0:
                refresh_text = "Data refresh: due"
            else:
                refresh_text = f"Data refresh in {self._format_countdown(delta)}"
        self.header_refresh_label.setText(refresh_text)

        snap = self._snapshot_map.get(symbol, {})
        regime = snap.get("regime", "--")
        state = snap.get("state", "--")
        spread = snap.get("spread", "--")
        atr = snap.get("atr", "--")
        self.header_symbol_label.setText(
            f"{symbol} | {regime}/{state} | Spread {spread} | ATR% {atr}"
        )

        quality = self._data_quality.get("status", "--")
        quality_color = "#9ad36a"
        if quality == "STALE":
            quality_color = "#ff8c8c"
        elif quality == "GAP":
            quality_color = "#ffcc8c"
        elif quality == "ERROR":
            quality_color = "#ff5a5a"
        self.header_quality_label.setText(f"Data: {quality}")
        self.header_quality_label.setStyleSheet(f"color: {quality_color};")

    def _timeframe_minutes(self, tf_text: str) -> int:
        tf_text = tf_text.strip().lower()
        if tf_text.endswith("m"):
            return int(tf_text[:-1])
        if tf_text.endswith("h"):
            return int(tf_text[:-1]) * 60
        if tf_text.endswith("d"):
            return int(tf_text[:-1]) * 1440
        return 1

    def _update_data_quality(self, df, tzname: str) -> None:
        if df is None or df.empty:
            self._data_quality = {"status": "ERROR"}
            self._update_header_bar()
            return
        last_ts = df["timestamp"].iloc[-1]
        prev_ts = df["timestamp"].iloc[-2] if len(df) > 1 else last_ts
        if hasattr(last_ts, "to_pydatetime"):
            last_ts = last_ts.to_pydatetime()
        if hasattr(prev_ts, "to_pydatetime"):
            prev_ts = prev_ts.to_pydatetime()
        tz = pytz.timezone(tzname)
        now = datetime.now(tz)
        if last_ts.tzinfo is None:
            last_ts = tz.localize(last_ts)
        if prev_ts.tzinfo is None:
            prev_ts = tz.localize(prev_ts)
        tf_minutes = self._timeframe_minutes(self.tf_input.currentText())
        stale_minutes = (now - last_ts).total_seconds() / 60.0
        gap_minutes = (last_ts - prev_ts).total_seconds() / 60.0

        status = "OK"
        if stale_minutes > tf_minutes * 2:
            status = "STALE"
        elif gap_minutes > tf_minutes * 2:
            status = "GAP"

        self._data_quality = {
            "status": status,
            "stale_minutes": stale_minutes,
            "gap_minutes": gap_minutes,
            "last_bar": last_ts.isoformat(),
        }
        self._update_header_bar()

    def _format_countdown(self, delta: timedelta) -> str:
        total = max(0, int(delta.total_seconds()))
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _render_dashboard(self, metrics: Dict[str, float], trades: List[Any], traces: List[Any]) -> None:
        if hasattr(self, "dashboard_kpis"):
            equity = metrics.get("ending_equity", 0.0)
            daily = metrics.get("total_pnl", 0.0)
            win_rate = metrics.get("win_rate", 0.0)
            max_dd = metrics.get("max_drawdown", 0.0)
            self.dashboard_kpis["Equity"].setText(f"${equity:,.2f}")
            self.dashboard_kpis["Daily PnL"].setText(f"${daily:,.2f}")
            self.dashboard_kpis["Win Rate"].setText(f"{win_rate:.2%}")
        self.dashboard_kpis["Max DD"].setText(f"{max_dd:.2%}")

        self._render_dashboard_trades(trades)
        self._render_dashboard_signals(traces)
        self._render_dashboard_risk(metrics)
        self._render_dashboard_equity(trades)
        self._render_active_positions(self.active_positions)
        self._render_dashboard_risk_heatmap()
        self._render_dashboard_tape(trades, traces)
        self._render_dashboard_regime_transitions(traces)
        self._render_dashboard_sparklines(trades)
        self._render_dashboard_risk_histogram()
        self._render_watchlist_sparklines(trades)
        self._update_signal_confidence()
        self._update_alert_health()
        self._update_pnl_pulse(metrics)

    def _render_dashboard_trades(self, trades: List[Any]) -> None:
        if not hasattr(self, "dashboard_trades"):
            return
        self.dashboard_trades.setRowCount(0)
        for trade in trades[-5:]:
            row = self.dashboard_trades.rowCount()
            self.dashboard_trades.insertRow(row)
            side = trade.side.value if getattr(trade, "side", None) else "-"
            self.dashboard_trades.setItem(row, 0, QtWidgets.QTableWidgetItem(trade.symbol))
            self.dashboard_trades.setItem(row, 1, QtWidgets.QTableWidgetItem(side))
            self.dashboard_trades.setItem(row, 2, QtWidgets.QTableWidgetItem(str(trade.entry_time)))
            self.dashboard_trades.setItem(row, 3, QtWidgets.QTableWidgetItem(str(trade.exit_time)))
            self.dashboard_trades.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{trade.pnl:.2f}"))

    def _render_dashboard_signals(self, traces: List[Any]) -> None:
        if not hasattr(self, "dashboard_signals"):
            return
        self.dashboard_signals.clear()
        for t in traces[-8:]:
            ts = getattr(t, "timestamp", "")
            self.dashboard_signals.addItem(f"{t.symbol} {t.action} | {t.reason} | {ts}")

    def _render_dashboard_risk(self, metrics: Dict[str, float]) -> None:
        if not hasattr(self, "daily_loss_progress"):
            return
        cfg = self.current_config or {}
        risk_cfg = cfg.get("risk", {})
        portfolio = cfg.get("portfolio", {})
        initial_cash = float(portfolio.get("initial_cash", 0) or 0)
        max_loss_pct = float(risk_cfg.get("max_daily_loss_pct", 0.02) or 0.02)
        pnl = float(metrics.get("total_pnl", 0.0))
        loss_pct = max(0.0, -pnl / initial_cash) if initial_cash else 0.0
        usage = min(1.0, loss_pct / max_loss_pct) if max_loss_pct else 0.0
        self.daily_loss_label.setText(f"Daily loss: {loss_pct:.2%} / {max_loss_pct:.2%}")
        self.daily_loss_progress.setValue(int(usage * 100))
        if usage < 0.5:
            color = "#4ed298"
        elif usage < 0.8:
            color = "#ffab4d"
        else:
            color = "#ff5a5a"
        self.daily_loss_progress.setStyleSheet(f"QProgressBar::chunk{{background:{color};}}")

    def _render_dashboard_equity(self, trades: List[Any]) -> None:
        if not CHARTS_AVAILABLE or not hasattr(self, "dashboard_equity_chart") or self.dashboard_equity_chart is None:
            return
        if not trades:
            self.dashboard_equity_chart.removeAllSeries()
            return
        cfg = self.current_config or {}
        initial_cash = float(cfg.get("portfolio", {}).get("initial_cash", 0) or 0)
        equity = []
        times = []
        eq = initial_cash
        for trade in trades:
            eq += trade.pnl
            equity.append(eq)
            times.append(QtCore.QDateTime(trade.exit_time))
        # Keep last 50 points
        equity = equity[-50:]
        times = times[-50:]

        self.dashboard_equity_chart.removeAllSeries()
        series = QLineSeries()
        series.setColor(QtGui.QColor("#4ed298"))
        for t, v in zip(times, equity):
            series.append(t.toMSecsSinceEpoch(), v)

        axis_x = QDateTimeAxis()
        axis_x.setFormat("MM-dd")
        axis_x.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_x.setGridLineColor(QtGui.QColor("#1c273a"))
        axis_y = QValueAxis()
        axis_y.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_y.setGridLineColor(QtGui.QColor("#1c273a"))
        if equity:
            axis_y.setRange(min(equity) * 0.98, max(equity) * 1.02 if max(equity) != 0 else 1)

        self.dashboard_equity_chart.addSeries(series)
        self.dashboard_equity_chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.dashboard_equity_chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignRight)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

    def _render_active_positions(self, positions: List[Dict[str, Any]]) -> None:
        if not hasattr(self, "dashboard_positions"):
            return
        self.dashboard_positions.setRowCount(0)
        if not positions:
            broker_cfg = (self.current_config or {}).get("broker", {})
            if broker_cfg.get("enable_live_trading"):
                self.dashboard_positions_empty.setText("No active positions")
            else:
                self.dashboard_positions_empty.setText("Live trading disabled (paper mode)")
            self.dashboard_positions_empty.setVisible(True)
            return
        self.dashboard_positions_empty.setVisible(False)
        for pos in positions:
            row = self.dashboard_positions.rowCount()
            self.dashboard_positions.insertRow(row)
            self.dashboard_positions.setItem(row, 0, QtWidgets.QTableWidgetItem(str(pos.get("symbol", ""))))
            self.dashboard_positions.setItem(row, 1, QtWidgets.QTableWidgetItem(str(pos.get("side", ""))))
            self.dashboard_positions.setItem(row, 2, QtWidgets.QTableWidgetItem(str(pos.get("qty", ""))))
            self.dashboard_positions.setItem(row, 3, QtWidgets.QTableWidgetItem(str(pos.get("entry", ""))))
            self.dashboard_positions.setItem(row, 4, QtWidgets.QTableWidgetItem(str(pos.get("unrealized", ""))))

    def _render_dashboard_snapshot(self, rows: List[Dict[str, str]]) -> None:
        if not hasattr(self, "dashboard_state_table"):
            return
        self.dashboard_state_table.setRowCount(0)
        self._snapshot_map = {}
        for r in rows:
            self._snapshot_map[r["symbol"]] = r
            row_idx = self.dashboard_state_table.rowCount()
            self.dashboard_state_table.insertRow(row_idx)
            self.dashboard_state_table.setItem(row_idx, 0, QtWidgets.QTableWidgetItem(r["symbol"]))
            self.dashboard_state_table.setItem(row_idx, 1, QtWidgets.QTableWidgetItem(r["regime"]))
            self.dashboard_state_table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(r["state"]))
            self.dashboard_state_table.setItem(row_idx, 3, QtWidgets.QTableWidgetItem(r["spread"]))
            self.dashboard_state_table.setItem(row_idx, 4, QtWidgets.QTableWidgetItem(r["atr"]))
        self._update_watchlist_badges()
        self._apply_watchlist_filters()
        self._update_header_bar()
        self._update_signal_confidence()

    def _render_dashboard_risk_heatmap(self) -> None:
        if not hasattr(self, "dashboard_risk_table"):
            return
        cfg = self.current_config or {}
        symbols = [s["symbol"] for s in cfg.get("symbols", [])]
        risk_map = self._risk_pct_by_symbol()
        exposure_map = self._exposure_by_symbol()
        self.dashboard_risk_table.setRowCount(0)
        for sym in symbols:
            row = self.dashboard_risk_table.rowCount()
            self.dashboard_risk_table.insertRow(row)
            exposure = exposure_map.get(sym, 0.0)
            risk_pct = risk_map.get(sym, 0.0)
            self.dashboard_risk_table.setItem(row, 0, QtWidgets.QTableWidgetItem(sym))
            self.dashboard_risk_table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"${exposure:,.2f}" if exposure else "$0.00"))
            risk_item = QtWidgets.QTableWidgetItem(f"{risk_pct:.2%}")
            if risk_pct >= 0.02:
                risk_item.setBackground(QtGui.QColor("#3b1d1d"))
                risk_item.setForeground(QtGui.QColor("#ff8c8c"))
            elif risk_pct >= 0.01:
                risk_item.setBackground(QtGui.QColor("#3b2e1d"))
                risk_item.setForeground(QtGui.QColor("#ffcc8c"))
            else:
                risk_item.setBackground(QtGui.QColor("#1d3b2a"))
                risk_item.setForeground(QtGui.QColor("#8cffc4"))
            self.dashboard_risk_table.setItem(row, 2, risk_item)
        self._apply_hist_filter()

    def _update_signal_confidence(self) -> None:
        if not hasattr(self, "signal_confidence_bar"):
            return
        symbol = self._selected_symbol()
        trace = None
        for tr in reversed(self.last_decision_traces or []):
            if getattr(tr, "symbol", None) == symbol:
                trace = tr
                break
        if trace is None:
            self.signal_confidence_bar.setValue(0)
            self.signal_confidence_label.setText("No signal")
            self.signal_confidence_detail.setText("Waiting for traces")
            return

        score = 35
        reasons: List[str] = []
        regime_val = getattr(trace.regime, "value", str(trace.regime)).lower()
        state_val = getattr(trace.narrow_wide, "value", str(trace.narrow_wide)).lower()
        if "bull" in regime_val or "bear" in regime_val:
            score += 20
            reasons.append("Regime aligned")
        if getattr(trace, "transition_n2w", False):
            score += 20
            reasons.append("N2W transition")
        if "wide" in state_val:
            score += 10
            reasons.append("Wide state")
        atr_pct = getattr(trace, "atr_percent", None)
        try:
            atr_val = float(atr_pct) if atr_pct is not None else None
        except Exception:
            atr_val = None
        if atr_val is not None:
            if 0.003 <= atr_val <= 0.02:
                score += 10
                reasons.append("ATR healthy")
            else:
                score -= 5
                reasons.append("ATR extreme")
        if getattr(trace, "action", "") == "entry":
            score += 5
        if "breakout" in str(getattr(trace, "reason", "")).lower():
            score += 5
            reasons.append("Breakout confirmed")

        score = max(0, min(100, score))
        self.signal_confidence_bar.setValue(score)
        self.signal_confidence_label.setText(f"{symbol} confidence: {score}%")
        self.signal_confidence_detail.setText(" · ".join(reasons) if reasons else "Model baseline")

    def _update_alert_health(self) -> None:
        if not hasattr(self, "alert_health_label"):
            return
        if self._alert_history:
            last = self._alert_history[-1]
            ts = last.get("timestamp", "")
            self.alert_health_label.setText(f"Last alert: {ts}")
        else:
            self.alert_health_label.setText("Last alert: --")
        if self._alert_last_error:
            err = self._alert_last_error
            ts = self._alert_last_error_at.isoformat() if self._alert_last_error_at else ""
            self.alert_health_error.setText(f"Errors: {err} {ts}")
            self.alert_health_error.setStyleSheet("color:#ff8c8c;")
        else:
            self.alert_health_error.setText("Errors: --")
            self.alert_health_error.setStyleSheet("color:#97a0b8;")

    def _pnl_curve_for_symbol(self, trades: List[Any], symbol: str, max_points: int) -> List[float]:
        sym_trades = [t for t in trades if getattr(t, "symbol", None) == symbol]
        pnl_curve: List[float] = []
        eq = 0.0
        for t in sym_trades:
            eq += float(getattr(t, "pnl", 0.0) or 0.0)
            pnl_curve.append(eq)
        if len(pnl_curve) < 2:
            pnl_curve = [0.0, eq]
        if max_points and len(pnl_curve) > max_points:
            pnl_curve = pnl_curve[-max_points:]
        return pnl_curve

    def _sparkline_tooltip(self, values: List[float]) -> str:
        if not values:
            return "No data"
        last_val = values[-1]
        slope = (values[-1] - values[0]) if len(values) > 1 else 0.0
        return f"Last: {last_val:.2f}\nSlope: {slope:+.2f}"

    def _make_sparkline_view(self, values: List[float], color: str, tooltip: str, height: int = 40) -> QChartView:
        chart = QChart()
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.legend().hide()
        chart.setMargins(QtCore.QMargins(0, 0, 0, 0))
        series = QLineSeries()
        series.setColor(QtGui.QColor(color))
        for i, val in enumerate(values):
            series.append(i, val)
        axis_x = QValueAxis()
        axis_x.setVisible(False)
        axis_y = QValueAxis()
        axis_y.setVisible(False)
        if values:
            lo = min(values)
            hi = max(values)
            if lo == hi:
                lo -= 1
                hi += 1
            axis_y.setRange(lo, hi)
        axis_x.setRange(0, max(len(values) - 1, 1))
        chart.addSeries(series)
        chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        view = QChartView(chart)
        view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        view.setStyleSheet("background:transparent;")
        view.setFixedHeight(height)
        view.setToolTip(tooltip)
        view.setMouseTracking(True)
        return view

    def _set_sparkline_in_container(self, container: QtWidgets.QWidget, values: List[float], color: str, height: int = 28) -> None:
        layout = container.layout()
        if layout is None:
            layout = QtWidgets.QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if len(values) < 2:
            placeholder = QtWidgets.QLabel("—")
            placeholder.setStyleSheet("color:#6c7896;")
            layout.addWidget(placeholder)
            return
        if CHARTS_AVAILABLE:
            tooltip = self._sparkline_tooltip(values)
            view = self._make_sparkline_view(values, color, tooltip, height=height)
            view.setMinimumWidth(110)
            layout.addWidget(view)
        else:
            label = QtWidgets.QLabel("n/a")
            label.setStyleSheet("color:#6c7896;")
            layout.addWidget(label)

    def _render_dashboard_sparklines(self, trades: List[Any]) -> None:
        if not hasattr(self, "dashboard_spark_table"):
            return
        cfg = self.current_config or {}
        symbols = [s["symbol"] for s in cfg.get("symbols", [])]
        self.dashboard_spark_table.setRowCount(0)
        for sym in symbols:
            row = self.dashboard_spark_table.rowCount()
            self.dashboard_spark_table.insertRow(row)
            self.dashboard_spark_table.setRowHeight(row, 42)
            self.dashboard_spark_table.setItem(row, 0, QtWidgets.QTableWidgetItem(sym))
            pnl_curve = self._pnl_curve_for_symbol(trades, sym, 30)
            last_val = pnl_curve[-1] if pnl_curve else 0.0
            self.dashboard_spark_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{last_val:.2f}"))

            if CHARTS_AVAILABLE:
                tooltip = self._sparkline_tooltip(pnl_curve)
                view = self._make_sparkline_view(pnl_curve, "#4ebcff", tooltip)
                self.dashboard_spark_table.setCellWidget(row, 1, view)
            else:
                self.dashboard_spark_table.setItem(row, 1, QtWidgets.QTableWidgetItem("n/a"))

    def _render_dashboard_risk_histogram(self) -> None:
        if not CHARTS_AVAILABLE or not hasattr(self, "dashboard_risk_hist_chart") or self.dashboard_risk_hist_chart is None:
            return
        mode = self.dashboard_risk_hist_mode.currentText() if hasattr(self, "dashboard_risk_hist_mode") else "Risk %"
        if mode == "ATR %":
            self._render_dashboard_risk_histogram_atr()
            return
        risk_map = self._risk_pct_by_symbol()
        bins = ["0-0.5%", "0.5-1%", "1-2%", "2%+"]
        counts = [0, 0, 0, 0]
        for pct in risk_map.values():
            if pct <= 0.005:
                counts[0] += 1
            elif pct <= 0.01:
                counts[1] += 1
            elif pct <= 0.02:
                counts[2] += 1
            else:
                counts[3] += 1
        self.dashboard_risk_hist_chart.removeAllSeries()
        for axis in list(self.dashboard_risk_hist_chart.axes()):
            self.dashboard_risk_hist_chart.removeAxis(axis)
        bar_set = QBarSet("Symbols")
        bar_set.append(counts)
        series = QBarSeries()
        series.append(bar_set)
        axis_x = QBarCategoryAxis()
        axis_x.append(bins)
        axis_y = QValueAxis()
        axis_y.setRange(0, max(1, max(counts) if counts else 1))
        axis_x.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_y.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_x.setGridLineColor(QtGui.QColor("#1c273a"))
        axis_y.setGridLineColor(QtGui.QColor("#1c273a"))
        self.dashboard_risk_hist_chart.addSeries(series)
        self.dashboard_risk_hist_chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.dashboard_risk_hist_chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        try:
            bar_set.clicked.disconnect()
        except Exception:
            pass
        bar_set.clicked.connect(lambda idx, m="Risk %": self._toggle_hist_filter(m, idx, bins))
        self._hist_filter_bins = bins
        self._apply_hist_filter()

    def _refresh_histogram_mode(self) -> None:
        self._hist_filter = None
        if hasattr(self, "dashboard_risk_hist_filter_label"):
            self.dashboard_risk_hist_filter_label.setText("Filter: none")
        self._render_dashboard_risk_histogram()

    def _render_dashboard_risk_histogram_atr(self) -> None:
        if not CHARTS_AVAILABLE or not hasattr(self, "dashboard_risk_hist_chart") or self.dashboard_risk_hist_chart is None:
            return
        symbols = [s["symbol"] for s in (self.current_config or {}).get("symbols", [])]
        # Use last known ATR% from dashboard snapshot if available
        atr_vals: List[float] = []
        if hasattr(self, "dashboard_state_table"):
            for i in range(self.dashboard_state_table.rowCount()):
                sym = self.dashboard_state_table.item(i, 0).text()
                if sym not in symbols:
                    continue
                atr_text = self.dashboard_state_table.item(i, 4).text()
                try:
                    atr_vals.append(float(atr_text))
                except Exception:
                    continue
        bins = ["0-0.5%", "0.5-1%", "1-2%", "2%+"]
        counts = [0, 0, 0, 0]
        for pct in atr_vals:
            if pct <= 0.005:
                counts[0] += 1
            elif pct <= 0.01:
                counts[1] += 1
            elif pct <= 0.02:
                counts[2] += 1
            else:
                counts[3] += 1
        self.dashboard_risk_hist_chart.removeAllSeries()
        for axis in list(self.dashboard_risk_hist_chart.axes()):
            self.dashboard_risk_hist_chart.removeAxis(axis)
        bar_set = QBarSet("ATR%")
        bar_set.append(counts)
        series = QBarSeries()
        series.append(bar_set)
        axis_x = QBarCategoryAxis()
        axis_x.append(bins)
        axis_y = QValueAxis()
        axis_y.setRange(0, max(1, max(counts) if counts else 1))
        axis_x.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_y.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_x.setGridLineColor(QtGui.QColor("#1c273a"))
        axis_y.setGridLineColor(QtGui.QColor("#1c273a"))
        self.dashboard_risk_hist_chart.addSeries(series)
        self.dashboard_risk_hist_chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.dashboard_risk_hist_chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        try:
            bar_set.clicked.disconnect()
        except Exception:
            pass
        bar_set.clicked.connect(lambda idx, m="ATR %": self._toggle_hist_filter(m, idx, bins))
        self._hist_filter_bins = bins
        self._apply_hist_filter()

    def _render_dashboard_tape(self, trades: List[Any], traces: List[Any]) -> None:
        if not hasattr(self, "dashboard_tape"):
            return
        events: List[tuple] = []
        for alert in self._alert_history[-6:]:
            ts = alert.get("timestamp")
            events.append((ts, f"ALERT {alert.get('symbol')} {alert.get('condition')} | {alert.get('detail')}"))
        for t in trades[-10:]:
            events.append((t.entry_time, f"FILL {t.symbol} {t.side.value if t.side else ''} @ {t.entry_price:.2f}"))
            events.append((t.exit_time, f"EXIT {t.symbol} @ {t.exit_price:.2f} PnL {t.pnl:.2f}"))
        for tr in traces[-20:]:
            ts = getattr(tr, "timestamp", None)
            events.append((ts, f"SIGNAL {tr.symbol} {tr.action} | {tr.reason}"))
        events = [e for e in events if e[0] is not None]
        events.sort(key=lambda x: x[0])
        events = events[-12:]
        self.dashboard_tape.clear()
        for ts, msg in events:
            self.dashboard_tape.addItem(f"{ts} · {msg}")

    def _render_dashboard_regime_transitions(self, traces: List[Any]) -> None:
        if not hasattr(self, "dashboard_regime_table"):
            return
        self.dashboard_regime_table.setRowCount(0)
        last_state: Dict[str, str] = {}
        rows: List[Dict[str, str]] = []
        for tr in traces:
            key = tr.symbol
            state = f"{tr.regime.value}/{tr.narrow_wide.value}"
            if key not in last_state:
                last_state[key] = state
                continue
            if last_state[key] != state:
                rows.append(
                    {
                        "symbol": key,
                        "time": str(getattr(tr, "timestamp", "")),
                        "from": last_state[key],
                        "to": state,
                    }
                )
                last_state[key] = state
        rows = rows[-10:]
        for r in rows:
            row = self.dashboard_regime_table.rowCount()
            self.dashboard_regime_table.insertRow(row)
            self.dashboard_regime_table.setItem(row, 0, QtWidgets.QTableWidgetItem(r["symbol"]))
            self.dashboard_regime_table.setItem(row, 1, QtWidgets.QTableWidgetItem(r["time"]))
            self.dashboard_regime_table.setItem(row, 2, QtWidgets.QTableWidgetItem(r["from"]))
            self.dashboard_regime_table.setItem(row, 3, QtWidgets.QTableWidgetItem(r["to"]))

    def _risk_pct_by_symbol(self) -> Dict[str, float]:
        cfg = self.current_config or {}
        symbols = [s["symbol"] for s in cfg.get("symbols", [])]
        risk_per_trade = float(cfg.get("risk", {}).get("risk_per_trade", 0.0) or 0.0)
        risk_map = {sym: risk_per_trade for sym in symbols}
        for pos in self.active_positions:
            sym = pos.get("symbol")
            if not sym:
                continue
            risk_map[sym] = float(pos.get("risk_pct", risk_per_trade) or risk_per_trade)
        return risk_map

    def _exposure_by_symbol(self) -> Dict[str, float]:
        exposure_map: Dict[str, float] = {}
        for pos in self.active_positions:
            sym = pos.get("symbol")
            if not sym:
                continue
            exposure_map[sym] = exposure_map.get(sym, 0.0) + float(pos.get("qty", 0) or 0) * float(
                pos.get("entry", 0) or 0
            )
        return exposure_map

    def _toggle_hist_filter(self, mode: str, idx: int, bins: List[str]) -> None:
        if self._hist_filter == (mode, idx):
            self._hist_filter = None
        else:
            self._hist_filter = (mode, idx)
        if hasattr(self, "dashboard_risk_hist_filter_label"):
            label = "Filter: none" if self._hist_filter is None else f"Filter: {bins[idx]}"
            self.dashboard_risk_hist_filter_label.setText(label)
        self._apply_hist_filter()

    def _apply_hist_filter(self) -> None:
        if not hasattr(self, "dashboard_risk_table"):
            return
        if self._hist_filter is None:
            for i in range(self.dashboard_risk_table.rowCount()):
                self.dashboard_risk_table.setRowHidden(i, False)
            return
        mode, idx = self._hist_filter
        risk_map = self._risk_pct_by_symbol()
        for i in range(self.dashboard_risk_table.rowCount()):
            sym = self.dashboard_risk_table.item(i, 0).text()
            if mode == "ATR %":
                snap = self._snapshot_map.get(sym, {})
                try:
                    val = float(snap.get("atr", 0.0) or 0.0)
                except Exception:
                    val = 0.0
            else:
                val = risk_map.get(sym, 0.0)
            bucket = self._bucket_index(val)
            self.dashboard_risk_table.setRowHidden(i, bucket != idx)

    def _bucket_index(self, value: float) -> int:
        if value <= 0.005:
            return 0
        if value <= 0.01:
            return 1
        if value <= 0.02:
            return 2
        return 3

    def _update_watchlist_spark_items(self, list_widget: QtWidgets.QListWidget, trades: List[Any]) -> None:
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            widget = list_widget.itemWidget(item)
            if widget is None:
                continue
            spark_container = widget.findChild(QtWidgets.QWidget, "spark_container")
            if spark_container is None:
                continue
            symbol = item.text()
            pnl_curve = self._pnl_curve_for_symbol(trades, symbol, 20)
            color = "#9ad36a"
            if pnl_curve and pnl_curve[-1] < 0:
                color = "#ff7a7a"
            self._set_sparkline_in_container(spark_container, pnl_curve, color, height=28)

    def _render_watchlist_sparklines(self, trades: List[Any]) -> None:
        if hasattr(self, "watchlist"):
            self._update_watchlist_spark_items(self.watchlist, trades)
        if hasattr(self, "dashboard_watchlist"):
            self._update_watchlist_spark_items(self.dashboard_watchlist, trades)
        if not hasattr(self, "dashboard_watchlist_spark"):
            return
        symbols = [self.dashboard_watchlist.item(i).text() for i in range(self.dashboard_watchlist.count())]
        self.dashboard_watchlist_spark.setRowCount(0)
        for sym in symbols[:6]:
            row = self.dashboard_watchlist_spark.rowCount()
            self.dashboard_watchlist_spark.insertRow(row)
            self.dashboard_watchlist_spark.setRowHeight(row, 42)
            self.dashboard_watchlist_spark.setItem(row, 0, QtWidgets.QTableWidgetItem(sym))
            pnl_curve = self._pnl_curve_for_symbol(trades, sym, 20)
            last_val = pnl_curve[-1] if pnl_curve else 0.0
            self.dashboard_watchlist_spark.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{last_val:.2f}"))
            if CHARTS_AVAILABLE:
                tooltip = self._sparkline_tooltip(pnl_curve)
                view = self._make_sparkline_view(pnl_curve, "#9ad36a", tooltip)
                self.dashboard_watchlist_spark.setCellWidget(row, 1, view)
            else:
                self.dashboard_watchlist_spark.setItem(row, 1, QtWidgets.QTableWidgetItem("n/a"))

    def _update_pnl_pulse(self, metrics: Dict[str, float]) -> None:
        if not hasattr(self, "dashboard_kpis"):
            return
        pnl = float(metrics.get("total_pnl", 0.0))
        cfg = self.current_config or {}
        initial_cash = float(cfg.get("portfolio", {}).get("initial_cash", 0) or 1)
        pct = pnl / initial_cash if initial_cash else 0.0
        max_pct = 0.02
        scaled = max(-max_pct, min(max_pct, pct))
        value = int(50 + (scaled / max_pct) * 50) if max_pct else 50
        if hasattr(self, "pulse_bar"):
            self.pulse_bar.setValue(max(0, min(100, value)))
            self.pulse_bar.setFormat(f"PnL {pct:+.2%}")
        base_color = "#1b2438"
        if pnl > 0:
            base_color = "#143a2a"
        elif pnl < 0:
            base_color = "#3a1b1b"
        # Apply to KPI group boxes
        for label in self.dashboard_kpis.values():
            parent = label.parent()
            if isinstance(parent, QtWidgets.QWidget):
                parent.setStyleSheet(f"QGroupBox{{background:{base_color};}}")


def run() -> None:
    app = QtWidgets.QApplication([])
    app.setStyleSheet(stylesheet())
    app.setFont(app_font())

    window = MainWindow()
    window.show()
    app.exec()
