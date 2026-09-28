from __future__ import annotations

from typing import Optional, Dict, Any, List, Tuple
import bisect

from PySide6 import QtCore, QtGui, QtWidgets

try:
    from PySide6.QtCharts import (
        QChart,
        QChartView,
        QCandlestickSeries,
        QCandlestickSet,
        QLineSeries,
        QScatterSeries,
        QValueAxis,
        QDateTimeAxis,
        QLogValueAxis,
    )

    CHARTS_AVAILABLE = True
except Exception:
    CHARTS_AVAILABLE = False


class CrosshairChartView(QChartView):
    hovered = QtCore.Signal(dict)
    def __init__(self, chart: QChart) -> None:
        super().__init__(chart)
        self.setMouseTracking(True)
        self._timestamps: List[int] = []
        self._rows: List[Dict[str, Any]] = []
        self._indicator_keys: List[str] = []
        self._indicator_labels: Dict[str, str] = {}
        self._axis_x: Optional[QDateTimeAxis] = None
        self._axis_y: Optional[QValueAxis] = None
        self._panning_enabled = False
        self._last_pos: Optional[QtCore.QPointF] = None

        self._vline = QtWidgets.QGraphicsLineItem()
        self._hline = QtWidgets.QGraphicsLineItem()
        pen = QtGui.QPen(QtGui.QColor("#2b3655"))
        pen.setWidth(1)
        self._vline.setPen(pen)
        self._hline.setPen(pen)
        self._vline.setZValue(10)
        self._hline.setZValue(10)

        self._tooltip = QtWidgets.QGraphicsSimpleTextItem()
        self._tooltip.setBrush(QtGui.QBrush(QtGui.QColor("#cfd6ee")))
        self._tooltip.setZValue(11)

        self._price_label = QtWidgets.QGraphicsSimpleTextItem()
        self._price_label.setBrush(QtGui.QBrush(QtGui.QColor("#e6ecff")))
        self._price_label.setZValue(12)
        self._price_bg = QtWidgets.QGraphicsPathItem()
        self._price_bg.setBrush(QtGui.QBrush(QtGui.QColor("#1a2336")))
        self._price_bg.setPen(QtGui.QPen(QtGui.QColor("#2b3655")))
        self._price_bg.setZValue(11)

        self._time_label = QtWidgets.QGraphicsSimpleTextItem()
        self._time_label.setBrush(QtGui.QBrush(QtGui.QColor("#e6ecff")))
        self._time_label.setZValue(12)
        self._time_bg = QtWidgets.QGraphicsPathItem()
        self._time_bg.setBrush(QtGui.QBrush(QtGui.QColor("#1a2336")))
        self._time_bg.setPen(QtGui.QPen(QtGui.QColor("#2b3655")))
        self._time_bg.setZValue(11)
        self._pill_radius = 6

        scene = chart.scene()
        if scene is not None:
            scene.addItem(self._vline)
            scene.addItem(self._hline)
            scene.addItem(self._tooltip)
            scene.addItem(self._price_bg)
            scene.addItem(self._time_bg)
            scene.addItem(self._price_label)
            scene.addItem(self._time_label)
        self._hide_crosshair()

    def set_data_reference(
        self,
        timestamps: List[int],
        rows: List[Dict[str, Any]],
        indicator_keys: List[str],
        indicator_labels: Dict[str, str] | None = None,
    ) -> None:
        self._timestamps = timestamps
        self._rows = rows
        self._indicator_keys = indicator_keys
        self._indicator_labels = indicator_labels or {}

    def set_axes(self, axis_x: QDateTimeAxis, axis_y: QValueAxis) -> None:
        self._axis_x = axis_x
        self._axis_y = axis_y

    def set_panning_enabled(self, enabled: bool) -> None:
        self._panning_enabled = enabled

    def _hide_crosshair(self) -> None:
        self._vline.hide()
        self._hline.hide()
        self._tooltip.hide()
        self._price_label.hide()
        self._time_label.hide()
        self._price_bg.hide()
        self._time_bg.hide()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._panning_enabled:
            self._handle_pan(event)
        if not self._timestamps:
            self._hide_crosshair()
            return
        chart = self.chart()
        if chart is None:
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        plot = chart.plotArea()
        if not plot.contains(scene_pos):
            self._hide_crosshair()
            return

        self._vline.setLine(scene_pos.x(), plot.top(), scene_pos.x(), plot.bottom())
        self._hline.setLine(plot.left(), scene_pos.y(), plot.right(), scene_pos.y())
        self._vline.show()
        self._hline.show()

        value = chart.mapToValue(scene_pos)
        idx = bisect.bisect_left(self._timestamps, value.x())
        if idx >= len(self._timestamps):
            idx = len(self._timestamps) - 1
        if idx > 0 and abs(self._timestamps[idx] - value.x()) > abs(self._timestamps[idx - 1] - value.x()):
            idx -= 1

        row = self._rows[idx]
        parts = [
            row.get("timestamp", ""),
            f"O:{row.get('open', 0):.2f}",
            f"H:{row.get('high', 0):.2f}",
            f"L:{row.get('low', 0):.2f}",
            f"C:{row.get('close', 0):.2f}",
            f"V:{row.get('volume', 0):.0f}",
        ]
        for key in self._indicator_keys:
            val = row.get(key)
            if val is None or val != val:
                continue
            label = self._indicator_labels.get(key, key.upper())
            parts.append(f"{label}: {val:.2f}")

        self._tooltip.setText("  ".join(parts))
        self._tooltip.setPos(scene_pos.x() + 12, scene_pos.y() - 24)
        self._tooltip.show()

        # axis labels
        time_text = QtCore.QDateTime.fromMSecsSinceEpoch(int(self._timestamps[idx])).toString("MM-dd HH:mm")
        price_text = f"{value.y():.2f}"
        self._time_label.setText(time_text)
        self._price_label.setText(price_text)

        time_rect = self._time_label.boundingRect()
        price_rect = self._price_label.boundingRect()

        time_x = max(plot.left(), min(scene_pos.x() - time_rect.width() / 2, plot.right() - time_rect.width()))
        time_y = plot.bottom() + 6
        price_x = plot.right() + 8
        price_y = max(plot.top(), min(scene_pos.y() - price_rect.height() / 2, plot.bottom() - price_rect.height()))

        time_rect_box = QtCore.QRectF(time_x - 6, time_y - 2, time_rect.width() + 12, time_rect.height() + 6)
        price_rect_box = QtCore.QRectF(price_x - 6, price_y - 2, price_rect.width() + 12, price_rect.height() + 6)
        time_path = QtGui.QPainterPath()
        time_path.addRoundedRect(time_rect_box, self._pill_radius, self._pill_radius)
        price_path = QtGui.QPainterPath()
        price_path.addRoundedRect(price_rect_box, self._pill_radius, self._pill_radius)
        self._time_bg.setPath(time_path)
        self._price_bg.setPath(price_path)

        self._time_label.setPos(time_x, time_y)
        self._price_label.setPos(price_x, price_y)
        self._time_label.show()
        self._price_label.show()
        self._time_bg.show()
        self._price_bg.show()

        self.hovered.emit(row)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._panning_enabled and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._last_pos = event.position()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._last_pos = None
        super().mouseReleaseEvent(event)

    def _handle_pan(self, event: QtGui.QMouseEvent) -> None:
        if self._last_pos is None or self._axis_x is None or self._axis_y is None:
            return
        delta = event.position() - self._last_pos
        self._last_pos = event.position()
        chart = self.chart()
        plot = chart.plotArea()
        if plot.width() == 0 or plot.height() == 0:
            return
        dx = -delta.x() / plot.width()
        dy = delta.y() / plot.height()

        x_min = self._axis_x.min().toMSecsSinceEpoch()
        x_max = self._axis_x.max().toMSecsSinceEpoch()
        y_min = self._axis_y.min()
        y_max = self._axis_y.max()
        x_range = x_max - x_min
        y_range = y_max - y_min

        self._axis_x.setRange(
            QtCore.QDateTime.fromMSecsSinceEpoch(int(x_min + dx * x_range)),
            QtCore.QDateTime.fromMSecsSinceEpoch(int(x_max + dx * x_range)),
        )
        self._axis_y.setRange(y_min + dy * y_range, y_max + dy * y_range)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if self._axis_x is None or self._axis_y is None:
            return super().wheelEvent(event)
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 0.9 if delta > 0 else 1.1
        chart = self.chart()
        pos = event.position()
        value = chart.mapToValue(pos)

        x_min = self._axis_x.min().toMSecsSinceEpoch()
        x_max = self._axis_x.max().toMSecsSinceEpoch()
        x_center = int(value.x())
        x_min = int(x_center + (x_min - x_center) * factor)
        x_max = int(x_center + (x_max - x_center) * factor)

        y_min = self._axis_y.min()
        y_max = self._axis_y.max()
        y_center = value.y()
        y_min = y_center + (y_min - y_center) * factor
        y_max = y_center + (y_max - y_center) * factor

        self._axis_x.setRange(
            QtCore.QDateTime.fromMSecsSinceEpoch(x_min),
            QtCore.QDateTime.fromMSecsSinceEpoch(x_max),
        )
        self._axis_y.setRange(y_min, y_max)
        event.accept()


class CandleChartWidget(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.ohlc_bar = QtWidgets.QLabel("O: --  H: --  L: --  C: --  V: --")
        self.ohlc_bar.setStyleSheet("color:#cfd6ee; padding:4px 6px; background:#111827; border-radius:6px;")
        layout.addWidget(self.ohlc_bar)
        self.stack = QtWidgets.QStackedLayout()
        layout.addLayout(self.stack)

        self.placeholder = QtWidgets.QLabel(
            "Chart unavailable. Ensure PySide6 QtCharts is installed."
        )
        self.placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.chart_view: Optional[QChartView] = None
        self.chart: Optional[QChart] = None
        self.volume_view: Optional[QChartView] = None
        self.volume_chart: Optional[QChart] = None
        self.atr_view: Optional[QChartView] = None
        self.atr_chart: Optional[QChart] = None
        self.rsi_view: Optional[QChartView] = None
        self.rsi_chart: Optional[QChart] = None

        self._series = {}
        self._axes = {}
        self._rows: List[Dict[str, Any]] = []
        self._timestamps: List[int] = []
        self._base_range: Dict[str, float] = {}
        self._last_price_marker: Tuple[QtWidgets.QGraphicsLineItem, QtWidgets.QGraphicsRectItem, QtWidgets.QGraphicsSimpleTextItem] | None = None
        self._session_lines: List[QtWidgets.QGraphicsLineItem] = []
        self._session_shades: List[QtWidgets.QGraphicsRectItem] = []
        self._transition_shades: List[QtWidgets.QGraphicsRectItem] = []
        self._show_transitions = True
        self._legend_sma_fast = 20
        self._legend_sma_slow = 200
        self._legend_ema = 9
        self._marker_series: Dict[str, Optional[QScatterSeries]] = {"buy": None, "sell": None}

        if CHARTS_AVAILABLE:
            self.chart = QChart()
            gradient = QtGui.QLinearGradient(0, 0, 0, 1)
            gradient.setCoordinateMode(QtGui.QGradient.CoordinateMode.ObjectBoundingMode)
            gradient.setColorAt(0.0, QtGui.QColor("#0f121a"))
            gradient.setColorAt(1.0, QtGui.QColor("#121a2b"))
            self.chart.setBackgroundBrush(QtGui.QBrush(gradient))
            self.chart.setPlotAreaBackgroundBrush(QtGui.QColor("#0e141f"))
            self.chart.setPlotAreaBackgroundVisible(True)
            self.chart.legend().setLabelColor(QtGui.QColor("#cfd6ee"))

            self.chart_view = CrosshairChartView(self.chart)
            self.chart_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            self.chart_view.hovered.connect(self._update_ohlc_bar)

            self.volume_chart = QChart()
            self.volume_chart.setBackgroundBrush(QtGui.QColor("#0f121a"))
            self.volume_chart.setPlotAreaBackgroundBrush(QtGui.QColor("#0e141f"))
            self.volume_chart.setPlotAreaBackgroundVisible(True)
            self.volume_chart.legend().hide()

            self.volume_view = QChartView(self.volume_chart)
            self.volume_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            self.volume_view.setFixedHeight(140)

            self.atr_chart = QChart()
            self.atr_chart.setBackgroundBrush(QtGui.QColor("#0f121a"))
            self.atr_chart.setPlotAreaBackgroundBrush(QtGui.QColor("#0e141f"))
            self.atr_chart.setPlotAreaBackgroundVisible(True)
            self.atr_chart.legend().hide()

            self.atr_view = QChartView(self.atr_chart)
            self.atr_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            self.atr_view.setFixedHeight(120)

            self.rsi_chart = QChart()
            self.rsi_chart.setBackgroundBrush(QtGui.QColor("#0f121a"))
            self.rsi_chart.setPlotAreaBackgroundBrush(QtGui.QColor("#0e141f"))
            self.rsi_chart.setPlotAreaBackgroundVisible(True)
            self.rsi_chart.legend().hide()

            self.rsi_view = QChartView(self.rsi_chart)
            self.rsi_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            self.rsi_view.setFixedHeight(120)

            self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
            self.splitter.addWidget(self.chart_view)
            self.splitter.addWidget(self.volume_view)
            self.splitter.addWidget(self.atr_view)
            self.splitter.addWidget(self.rsi_view)
            self.splitter.setStretchFactor(0, 6)
            self.splitter.setStretchFactor(1, 2)
            self.splitter.setStretchFactor(2, 2)
            self.splitter.setStretchFactor(3, 2)

            self.stack.addWidget(self.splitter)
            self.stack.setCurrentWidget(self.splitter)
        else:
            self.stack.addWidget(self.placeholder)
            self.stack.setCurrentWidget(self.placeholder)

    def set_data(
        self,
        df,
        sma_fast: int = 20,
        sma_slow: int = 200,
        ema_window: int = 9,
        max_points: int = 400,
        session: str | None = None,
        markers: List[Dict[str, Any]] | None = None,
        transitions: List[int] | None = None,
    ) -> None:
        if not CHARTS_AVAILABLE or self.chart is None:
            return
        if df is None or df.empty:
            self._show_placeholder("No data available for chart")
            return

        if len(df) > max_points:
            df = df.tail(max_points)

        self._legend_sma_fast = sma_fast
        self._legend_sma_slow = sma_slow
        self._legend_ema = ema_window

        self.chart.removeAllSeries()
        self.volume_chart.removeAllSeries()
        self.atr_chart.removeAllSeries()
        self.rsi_chart.removeAllSeries()
        self._clear_transition_bands()

        candle_series = QCandlestickSeries()
        candle_series.setIncreasingColor(QtGui.QColor(0, 0, 0, 0))
        candle_series.setDecreasingColor(QtGui.QColor("#ff5a5a"))
        candle_series.setName("Price")
        try:
            candle_series.setBodyOutlineVisible(True)
        except Exception:
            pass

        # Ensure timestamps are in ms since epoch
        timestamps = []
        lows = []
        highs = []
        rows = []
        for _, row in df.iterrows():
            ts = row["timestamp"]
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
            ts_ms = int(QtCore.QDateTime(ts).toMSecsSinceEpoch())
            timestamps.append(ts_ms)
            lows.append(float(row["low"]))
            highs.append(float(row["high"]))
            open_ = float(row["open"])
            close_ = float(row["close"])
            candle = QCandlestickSet(
                open_,
                float(row["high"]),
                float(row["low"]),
                close_,
                ts_ms,
            )
            try:
                if close_ >= open_:
                    candle.setBrush(QtGui.QBrush(QtCore.Qt.GlobalColor.transparent))
                    pen = QtGui.QPen(QtGui.QColor("#4ed298"))
                    pen.setWidth(2)
                    candle.setPen(pen)
                else:
                    candle.setBrush(QtGui.QBrush(QtGui.QColor("#ff5a5a")))
                    pen = QtGui.QPen(QtGui.QColor("#ff5a5a"))
                    pen.setWidth(2)
                    candle.setPen(pen)
            except Exception:
                pass
            candle_series.append(candle)
            rows.append(
                {
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M"),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0)),
                    "sma_fast": float(row["sma_fast"]) if "sma_fast" in row and row["sma_fast"] == row["sma_fast"] else None,
                    "sma_slow": float(row["sma_slow"]) if "sma_slow" in row and row["sma_slow"] == row["sma_slow"] else None,
                    "ema": float(row["ema_9"]) if "ema_9" in row and row["ema_9"] == row["ema_9"] else None,
                    "atr": float(row["atr_14"]) if "atr_14" in row and row["atr_14"] == row["atr_14"] else None,
                    "rsi": float(row["rsi_14"]) if "rsi_14" in row and row["rsi_14"] == row["rsi_14"] else None,
                }
            )

        if rows:
            self._update_ohlc_bar(rows[-1])

        # SMA lines
        sma_fast_series = QLineSeries()
        sma_fast_series.setName(f"SMA{sma_fast}")
        sma_fast_series.setColor(QtGui.QColor("#4ebcff"))

        sma_slow_series = QLineSeries()
        sma_slow_series.setName(f"SMA{sma_slow}")
        sma_slow_series.setColor(QtGui.QColor("#ffab4d"))

        ema_series = QLineSeries()
        ema_series.setName(f"EMA{ema_window}")
        ema_series.setColor(QtGui.QColor("#b97cff"))

        atr_upper = QLineSeries()
        atr_upper.setName("ATR+1x")
        atr_upper_pen = QtGui.QPen(QtGui.QColor("#7aa2ff"))
        atr_upper_pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        atr_upper.setPen(atr_upper_pen)

        atr_lower = QLineSeries()
        atr_lower.setName("ATR-1x")
        atr_lower_pen = QtGui.QPen(QtGui.QColor("#7aa2ff"))
        atr_lower_pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        atr_lower.setPen(atr_lower_pen)

        if "sma_fast" in df.columns:
            for ts_ms, val in zip(timestamps, df["sma_fast"].tolist()):
                if val == val:
                    sma_fast_series.append(ts_ms, float(val))
        if "sma_slow" in df.columns:
            for ts_ms, val in zip(timestamps, df["sma_slow"].tolist()):
                if val == val:
                    sma_slow_series.append(ts_ms, float(val))
        if "ema_9" in df.columns:
            for ts_ms, val in zip(timestamps, df["ema_9"].tolist()):
                if val == val:
                    ema_series.append(ts_ms, float(val))
        if "atr_14" in df.columns:
            for ts_ms, close_val, atr_val in zip(timestamps, df["close"].tolist(), df["atr_14"].tolist()):
                if atr_val == atr_val:
                    atr_upper.append(ts_ms, float(close_val) + float(atr_val))
                    atr_lower.append(ts_ms, float(close_val) - float(atr_val))

        self.chart.addSeries(candle_series)
        self.chart.addSeries(sma_fast_series)
        self.chart.addSeries(sma_slow_series)
        self.chart.addSeries(ema_series)
        self.chart.addSeries(atr_upper)
        self.chart.addSeries(atr_lower)

        axis_x = QDateTimeAxis()
        axis_x.setFormat("MM-dd HH:mm")
        axis_x.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_x.setGridLineColor(QtGui.QColor("#1c273a"))
        try:
            axis_x.setMinorGridLineColor(QtGui.QColor("#141b2b"))
        except Exception:
            pass
        axis_x.setTickCount(6)

        axis_y = QValueAxis()
        axis_y.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_y.setGridLineColor(QtGui.QColor("#1c273a"))
        try:
            axis_y.setMinorGridLineColor(QtGui.QColor("#141b2b"))
        except Exception:
            pass

        if timestamps:
            axis_x.setRange(
                QtCore.QDateTime.fromMSecsSinceEpoch(min(timestamps)),
                QtCore.QDateTime.fromMSecsSinceEpoch(max(timestamps)),
            )
        if lows and highs:
            axis_y.setRange(min(lows), max(highs))

        self.chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignRight)

        candle_series.attachAxis(axis_x)
        candle_series.attachAxis(axis_y)
        sma_fast_series.attachAxis(axis_x)
        sma_fast_series.attachAxis(axis_y)
        sma_slow_series.attachAxis(axis_x)
        sma_slow_series.attachAxis(axis_y)
        ema_series.attachAxis(axis_x)
        ema_series.attachAxis(axis_y)
        atr_upper.attachAxis(axis_x)
        atr_upper.attachAxis(axis_y)
        atr_lower.attachAxis(axis_x)
        atr_lower.attachAxis(axis_y)

        if isinstance(self.chart_view, CrosshairChartView):
            self.chart_view.set_axes(axis_x, axis_y)

        # Volume panel (vertical bars using line segments)
        volumes = df["volume"].tolist() if "volume" in df.columns else [0 for _ in timestamps]
        vol_axis_x = QDateTimeAxis()
        vol_axis_x.setFormat("MM-dd HH:mm")
        vol_axis_x.setLabelsColor(QtGui.QColor("#b6c0db"))
        vol_axis_x.setGridLineColor(QtGui.QColor("#1c273a"))
        vol_axis_x.setTickCount(4)

        vol_axis_y = QValueAxis()
        vol_axis_y.setLabelsColor(QtGui.QColor("#b6c0db"))
        vol_axis_y.setGridLineColor(QtGui.QColor("#1c273a"))
        vol_max = max(volumes) if volumes else 1
        vol_axis_y.setRange(0, max(vol_max, 1))

        self.volume_chart.addAxis(vol_axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.volume_chart.addAxis(vol_axis_y, QtCore.Qt.AlignmentFlag.AlignRight)

        vol_series_list = []
        for ts_ms, vol, open_, close_ in zip(timestamps, volumes, df["open"].tolist(), df["close"].tolist()):
            bar_series = QLineSeries()
            color = QtGui.QColor("#4ed298") if close_ >= open_ else QtGui.QColor("#ff5a5a")
            pen = QtGui.QPen(color)
            pen.setWidth(2)
            bar_series.setPen(pen)
            bar_series.append(ts_ms, 0)
            bar_series.append(ts_ms, float(vol))
            self.volume_chart.addSeries(bar_series)
            bar_series.attachAxis(vol_axis_x)
            bar_series.attachAxis(vol_axis_y)
            vol_series_list.append(bar_series)

        # ATR panel
        atr_series = QLineSeries()
        atr_series.setColor(QtGui.QColor("#ffab4d"))
        if "atr_14" in df.columns:
            for ts_ms, val in zip(timestamps, df["atr_14"].tolist()):
                if val == val:
                    atr_series.append(ts_ms, float(val))
        atr_axis_x = QDateTimeAxis()
        atr_axis_x.setFormat("MM-dd HH:mm")
        atr_axis_x.setLabelsColor(QtGui.QColor("#b6c0db"))
        atr_axis_x.setGridLineColor(QtGui.QColor("#1c273a"))
        atr_axis_x.setTickCount(4)
        atr_axis_y = QValueAxis()
        atr_axis_y.setLabelsColor(QtGui.QColor("#b6c0db"))
        atr_axis_y.setGridLineColor(QtGui.QColor("#1c273a"))
        max_atr = df["atr_14"].max() if "atr_14" in df.columns else 1
        atr_axis_y.setRange(0, max(max_atr, 1))

        self.atr_chart.addSeries(atr_series)
        self.atr_chart.addAxis(atr_axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.atr_chart.addAxis(atr_axis_y, QtCore.Qt.AlignmentFlag.AlignRight)
        atr_series.attachAxis(atr_axis_x)
        atr_series.attachAxis(atr_axis_y)

        # RSI panel
        rsi_series = QLineSeries()
        rsi_series.setColor(QtGui.QColor("#9ad36a"))
        if "rsi_14" in df.columns:
            for ts_ms, val in zip(timestamps, df["rsi_14"].tolist()):
                if val == val:
                    rsi_series.append(ts_ms, float(val))
        rsi_axis_x = QDateTimeAxis()
        rsi_axis_x.setFormat("MM-dd HH:mm")
        rsi_axis_x.setLabelsColor(QtGui.QColor("#b6c0db"))
        rsi_axis_x.setGridLineColor(QtGui.QColor("#1c273a"))
        rsi_axis_x.setTickCount(4)
        rsi_axis_y = QValueAxis()
        rsi_axis_y.setLabelsColor(QtGui.QColor("#b6c0db"))
        rsi_axis_y.setGridLineColor(QtGui.QColor("#1c273a"))
        rsi_axis_y.setRange(0, 100)

        self.rsi_chart.addSeries(rsi_series)
        self.rsi_chart.addAxis(rsi_axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.rsi_chart.addAxis(rsi_axis_y, QtCore.Qt.AlignmentFlag.AlignRight)
        rsi_series.attachAxis(rsi_axis_x)
        rsi_series.attachAxis(rsi_axis_y)

        # Sync x-axes across panes
        def sync_x(min_dt: QtCore.QDateTime, max_dt: QtCore.QDateTime) -> None:
            vol_axis_x.setRange(min_dt, max_dt)
            atr_axis_x.setRange(min_dt, max_dt)
            rsi_axis_x.setRange(min_dt, max_dt)

        axis_x.rangeChanged.connect(sync_x)
        sync_x(axis_x.min(), axis_x.max())

        self.stack.setCurrentWidget(self.chart_view)

        self._series = {
            "sma_fast": sma_fast_series,
            "sma_slow": sma_slow_series,
            "ema": ema_series,
            "atr_upper": atr_upper,
            "atr_lower": atr_lower,
            "volume": vol_series_list,
            "atr": atr_series,
            "rsi": rsi_series,
        }
        self._axes = {
            "price_x": axis_x,
            "price_y": axis_y,
            "vol_x": vol_axis_x,
            "vol_y": vol_axis_y,
            "atr_x": atr_axis_x,
            "atr_y": atr_axis_y,
            "rsi_x": rsi_axis_x,
            "rsi_y": rsi_axis_y,
        }
        self._timestamps = timestamps
        self._rows = rows
        if timestamps and lows and highs:
            self._base_range = {
                "x_min": min(timestamps),
                "x_max": max(timestamps),
                "y_min": min(lows),
                "y_max": max(highs),
            }
        if isinstance(self.chart_view, CrosshairChartView):
            self.chart_view.set_data_reference(
                timestamps,
                rows,
                ["sma_fast", "sma_slow", "ema", "atr", "rsi"],
                {
                    "sma_fast": f"SMA{sma_fast}",
                    "sma_slow": f"SMA{sma_slow}",
                    "ema": f"EMA{ema_window}",
                    "atr": "ATR14",
                    "rsi": "RSI14",
                },
            )

        # Last price marker
        self._render_last_price_marker(timestamps, df)

        # Session separators (day boundaries)
        self._render_session_separators(timestamps)

        # Session shading (RTH vs ETH)
        self._render_session_shading(df, session)

        # Markers (signals)
        if markers:
            self.set_markers(markers)
        if transitions:
            self.set_transition_bands(transitions)

        # Subtle watermark inside plot area
        if self.chart is not None:
            watermark = QtWidgets.QGraphicsSimpleTextItem("NARROW→WIDE")
            watermark.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 18)))
            watermark.setZValue(0)
            scene = self.chart.scene()
            if scene is not None:
                scene.addItem(watermark)
                plot = self.chart.plotArea()
                watermark.setPos(plot.left() + 10, plot.top() + 10)

    def _show_placeholder(self, text: str) -> None:
        self.placeholder.setText(text)
        self.stack.setCurrentWidget(self.placeholder)

    def _update_ohlc_bar(self, row: Dict[str, Any]) -> None:
        if not row:
            return
        o = row.get("open", 0.0)
        h = row.get("high", 0.0)
        l = row.get("low", 0.0)
        c = row.get("close", 0.0)
        v = row.get("volume", 0.0)
        sma_fast = row.get("sma_fast")
        sma_slow = row.get("sma_slow")
        ema = row.get("ema")
        atr = row.get("atr")
        rsi = row.get("rsi")
        parts = [
            f"O {o:.2f}",
            f"H {h:.2f}",
            f"L {l:.2f}",
            f"C {c:.2f}",
            f"V {v:.0f}",
        ]
        if sma_fast is not None:
            parts.append(f"SMA{self._legend_sma_fast} {sma_fast:.2f}")
        if sma_slow is not None:
            parts.append(f"SMA{self._legend_sma_slow} {sma_slow:.2f}")
        if ema is not None:
            parts.append(f"EMA{self._legend_ema} {ema:.2f}")
        if atr is not None:
            parts.append(f"ATR14 {atr:.2f}")
        if rsi is not None:
            parts.append(f"RSI14 {rsi:.2f}")
        self.ohlc_bar.setText("  |  ".join(parts))

    def set_visibility(
        self,
        *,
        show_sma_fast: bool = True,
        show_sma_slow: bool = True,
        show_ema: bool = True,
        show_atr_bands: bool = True,
        show_volume: bool = True,
        show_atr: bool = True,
        show_rsi: bool = True,
    ) -> None:
        if not self._series:
            return
        self._series["sma_fast"].setVisible(show_sma_fast)
        self._series["sma_slow"].setVisible(show_sma_slow)
        self._series["ema"].setVisible(show_ema)
        self._series["atr_upper"].setVisible(show_atr_bands)
        self._series["atr_lower"].setVisible(show_atr_bands)
        if self.volume_view is not None:
            self.volume_view.setVisible(show_volume)
        if self.atr_view is not None:
            self.atr_view.setVisible(show_atr)
        if self.rsi_view is not None:
            self.rsi_view.setVisible(show_rsi)

    def set_panning_enabled(self, enabled: bool) -> None:
        if isinstance(self.chart_view, CrosshairChartView):
            self.chart_view.set_panning_enabled(enabled)

    def splitter_sizes(self) -> List[int]:
        if hasattr(self, "splitter"):
            return self.splitter.sizes()
        return []

    def set_splitter_sizes(self, sizes: List[int]) -> None:
        if hasattr(self, "splitter") and sizes:
            self.splitter.setSizes(sizes)

    def zoom_by(self, factor: float) -> None:
        axis_x = self._axes.get("price_x")
        axis_y = self._axes.get("price_y")
        if axis_x is None or axis_y is None:
            return
        x_min = axis_x.min().toMSecsSinceEpoch()
        x_max = axis_x.max().toMSecsSinceEpoch()
        y_min = axis_y.min()
        y_max = axis_y.max()
        x_center = (x_min + x_max) / 2
        y_center = (y_min + y_max) / 2
        axis_x.setRange(
            QtCore.QDateTime.fromMSecsSinceEpoch(int(x_center + (x_min - x_center) * factor)),
            QtCore.QDateTime.fromMSecsSinceEpoch(int(x_center + (x_max - x_center) * factor)),
        )
        axis_y.setRange(
            y_center + (y_min - y_center) * factor,
            y_center + (y_max - y_center) * factor,
        )

    def reset_zoom(self) -> None:
        if not self._base_range:
            return
        axis_x = self._axes.get("price_x")
        axis_y = self._axes.get("price_y")
        if axis_x is None or axis_y is None:
            return
        axis_x.setRange(
            QtCore.QDateTime.fromMSecsSinceEpoch(int(self._base_range["x_min"])),
            QtCore.QDateTime.fromMSecsSinceEpoch(int(self._base_range["x_max"])),
        )
        axis_y.setRange(self._base_range["y_min"], self._base_range["y_max"])

    def autoscale(self) -> None:
        if not self._base_range:
            return
        axis_y = self._axes.get("price_y")
        if axis_y is None:
            return
        axis_y.setRange(self._base_range["y_min"], self._base_range["y_max"])

    def focus_on_timestamp(self, ts_ms: int, window: int = 50) -> None:
        if not self._timestamps or not self._rows:
            return
        axis_x = self._axes.get("price_x")
        axis_y = self._axes.get("price_y")
        if axis_x is None or axis_y is None:
            return
        idx = bisect.bisect_left(self._timestamps, ts_ms)
        idx = max(0, min(len(self._timestamps) - 1, idx))
        start_idx = max(0, idx - window)
        end_idx = min(len(self._timestamps) - 1, idx + window)
        axis_x.setRange(
            QtCore.QDateTime.fromMSecsSinceEpoch(int(self._timestamps[start_idx])),
            QtCore.QDateTime.fromMSecsSinceEpoch(int(self._timestamps[end_idx])),
        )
        lows = [r.get("low") for r in self._rows[start_idx : end_idx + 1] if r.get("low") is not None]
        highs = [r.get("high") for r in self._rows[start_idx : end_idx + 1] if r.get("high") is not None]
        if lows and highs:
            axis_y.setRange(min(lows), max(highs))

    def set_markers(self, markers: List[Dict[str, Any]]) -> None:
        if self.chart is None:
            return
        # Remove old marker series
        for key, series in self._marker_series.items():
            if series is not None:
                self.chart.removeSeries(series)
        self._marker_series = {"buy": None, "sell": None, "exit": None}

        buy_series = QScatterSeries()
        buy_series.setMarkerSize(10)
        buy_series.setColor(QtGui.QColor("#4ed298"))
        buy_series.setBorderColor(QtGui.QColor("#1f6f4e"))

        sell_series = QScatterSeries()
        sell_series.setMarkerSize(10)
        sell_series.setColor(QtGui.QColor("#ff5a5a"))
        sell_series.setBorderColor(QtGui.QColor("#9b2c2c"))

        exit_series = QScatterSeries()
        exit_series.setMarkerShape(QScatterSeries.MarkerShape.Rectangle)
        exit_series.setMarkerSize(8)
        exit_series.setColor(QtGui.QColor("#f2c94c"))
        exit_series.setBorderColor(QtGui.QColor("#b0891f"))

        for m in markers:
            ts = m.get("ts")
            price = m.get("price")
            side = m.get("side")
            if ts is None or price is None:
                continue
            if side == "buy":
                buy_series.append(ts, price)
            elif side == "exit":
                exit_series.append(ts, price)
            else:
                sell_series.append(ts, price)

        axis_x = self._axes.get("price_x")
        axis_y = self._axes.get("price_y")
        if axis_x is None or axis_y is None:
            return
        self.chart.addSeries(buy_series)
        self.chart.addSeries(sell_series)
        self.chart.addSeries(exit_series)
        buy_series.attachAxis(axis_x)
        buy_series.attachAxis(axis_y)
        sell_series.attachAxis(axis_x)
        sell_series.attachAxis(axis_y)
        exit_series.attachAxis(axis_x)
        exit_series.attachAxis(axis_y)
        self._marker_series = {"buy": buy_series, "sell": sell_series, "exit": exit_series}

    def set_transition_visible(self, enabled: bool) -> None:
        self._show_transitions = enabled
        for rect in self._transition_shades:
            rect.setVisible(enabled)

    def set_transition_bands(self, transitions: List[int], band_bars: int = 1) -> None:
        if self.chart is None or not self._timestamps:
            return
        self._clear_transition_bands()
        axis_y = self._axes.get("price_y")
        if axis_y is None:
            return
        plot = self.chart.plotArea()
        for ts in transitions:
            idx = bisect.bisect_left(self._timestamps, ts)
            idx = max(0, min(len(self._timestamps) - 1, idx))
            start_idx = max(0, idx - band_bars)
            end_idx = min(len(self._timestamps) - 1, idx + band_bars)
            ts_start = self._timestamps[start_idx]
            ts_end = self._timestamps[end_idx]
            x1 = self.chart.mapToPosition(QtCore.QPointF(ts_start, axis_y.max())).x()
            x2 = self.chart.mapToPosition(QtCore.QPointF(ts_end, axis_y.max())).x()
            width = max(6.0, abs(x2 - x1))
            rect = QtWidgets.QGraphicsRectItem(min(x1, x2), plot.top(), width, plot.height())
            rect.setBrush(QtGui.QBrush(QtGui.QColor(178, 138, 74, 70)))
            rect.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
            rect.setZValue(0.7)
            rect.setVisible(self._show_transitions)
            scene = self.chart.scene()
            if scene is not None:
                scene.addItem(rect)
                self._transition_shades.append(rect)

    def _clear_transition_bands(self) -> None:
        if self.chart is None:
            self._transition_shades = []
            return
        scene = self.chart.scene()
        if scene is None:
            self._transition_shades = []
            return
        for rect in self._transition_shades:
            scene.removeItem(rect)
        self._transition_shades = []

    def _render_last_price_marker(self, timestamps: List[int], df) -> None:
        if self.chart is None or not timestamps or df.empty:
            return
        last_row = df.iloc[-1]
        last_price = float(last_row["close"])
        prev_price = float(df.iloc[-2]["close"]) if len(df) > 1 else last_price
        color = QtGui.QColor("#4ed298") if last_price >= prev_price else QtGui.QColor("#ff5a5a")
        pct = ((last_price - prev_price) / prev_price * 100) if prev_price else 0.0

        scene = self.chart.scene()
        if scene is None:
            return

        # Clean previous marker
        if self._last_price_marker:
            for item in self._last_price_marker:
                scene.removeItem(item)

        plot = self.chart.plotArea()
        axis_y = self._axes.get("price_y")
        if axis_y is None:
            return

        # Map last price to scene y
        y = self.chart.mapToPosition(QtCore.QPointF(timestamps[-1], last_price)).y()

        line = QtWidgets.QGraphicsLineItem(plot.left(), y, plot.right(), y)
        pen = QtGui.QPen(color)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setWidth(1)
        line.setPen(pen)
        line.setZValue(2)

        label = QtWidgets.QGraphicsSimpleTextItem(f"{last_price:.2f}  {pct:+.2f}%")
        label.setBrush(QtGui.QBrush(QtGui.QColor("#e6ecff")))
        label.setZValue(3)
        rect = QtWidgets.QGraphicsRectItem()
        rect.setBrush(QtGui.QBrush(color))
        rect.setPen(QtGui.QPen(color))
        rect.setZValue(2)

        r = label.boundingRect()
        rect.setRect(plot.right() + 8, y - r.height() / 2 - 2, r.width() + 12, r.height() + 6)
        label.setPos(plot.right() + 14, y - r.height() / 2)

        scene.addItem(line)
        scene.addItem(rect)
        scene.addItem(label)
        self._last_price_marker = (line, rect, label)

    def _render_session_separators(self, timestamps: List[int]) -> None:
        if self.chart is None or not timestamps:
            return
        scene = self.chart.scene()
        if scene is None:
            return
        # Remove previous
        for line in self._session_lines:
            scene.removeItem(line)
        self._session_lines = []

        plot = self.chart.plotArea()
        last_day = None
        for ts in timestamps:
            dt = QtCore.QDateTime.fromMSecsSinceEpoch(ts).date()
            if last_day is None:
                last_day = dt
                continue
            if dt != last_day:
                x = self.chart.mapToPosition(QtCore.QPointF(ts, 0)).x()
                line = QtWidgets.QGraphicsLineItem(x, plot.top(), x, plot.bottom())
                pen = QtGui.QPen(QtGui.QColor("#1b263a"))
                pen.setStyle(QtCore.Qt.PenStyle.DashLine)
                pen.setWidth(1)
                line.setPen(pen)
                line.setZValue(1)
                scene.addItem(line)
                self._session_lines.append(line)
                last_day = dt

    def _render_session_shading(self, df, session: str | None) -> None:
        if self.chart is None:
            return
        scene = self.chart.scene()
        if scene is None:
            return
        # Clear previous shading
        for rect in self._session_shades:
            scene.removeItem(rect)
        self._session_shades = []

        if session != "rth":
            return
        if df is None or df.empty:
            return

        plot = self.chart.plotArea()
        axis_y = self._axes.get("price_y")
        if axis_y is None:
            return

        df_sorted = df.sort_values("timestamp")
        df_sorted["date"] = df_sorted["timestamp"].dt.date
        for day, day_df in df_sorted.groupby("date"):
            base_ts = day_df.iloc[0]["timestamp"]
            if hasattr(base_ts, "to_pydatetime"):
                base_ts = base_ts.to_pydatetime()
            # RTH window
            rth_start = base_ts.replace(hour=9, minute=30, second=0, microsecond=0)
            rth_end = base_ts.replace(hour=16, minute=0, second=0, microsecond=0)
            day_start = day_df.iloc[0]["timestamp"]
            day_end = day_df.iloc[-1]["timestamp"]

            for seg_start, seg_end in [(day_start, rth_start), (rth_end, day_end)]:
                if seg_end <= seg_start:
                    continue
                if hasattr(seg_start, "to_pydatetime"):
                    seg_start = seg_start.to_pydatetime()
                if hasattr(seg_end, "to_pydatetime"):
                    seg_end = seg_end.to_pydatetime()
                x1 = self.chart.mapToPosition(QtCore.QPointF(QtCore.QDateTime(seg_start).toMSecsSinceEpoch(), axis_y.max())).x()
                x2 = self.chart.mapToPosition(QtCore.QPointF(QtCore.QDateTime(seg_end).toMSecsSinceEpoch(), axis_y.max())).x()
                rect = QtWidgets.QGraphicsRectItem(min(x1, x2), plot.top(), abs(x2 - x1), plot.height())
                rect.setBrush(QtGui.QBrush(QtGui.QColor(20, 25, 35, 80)))
                rect.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
                rect.setZValue(0.5)
                scene.addItem(rect)
                self._session_shades.append(rect)


class PerformancePanel(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        self.log_toggle = QtWidgets.QCheckBox("Log Scale")
        self.overlay_toggle = QtWidgets.QCheckBox("Overlay DD")
        self.sharpe_toggle = QtWidgets.QCheckBox("Rolling Sharpe")
        self.sharpe_window = QtWidgets.QSpinBox()
        self.sharpe_window.setRange(5, 200)
        self.sharpe_window.setValue(20)
        self.sharpe_window.setSuffix(" bars")
        self.sharpe_window.setFixedWidth(110)
        controls.addWidget(self.log_toggle)
        controls.addWidget(self.overlay_toggle)
        controls.addWidget(self.sharpe_toggle)
        controls.addWidget(self.sharpe_window)
        controls.addStretch()
        layout.addLayout(controls)

        self.stack = QtWidgets.QStackedLayout()
        layout.addLayout(self.stack)

        self.placeholder = QtWidgets.QLabel("Performance charts unavailable.")
        self.placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.equity_chart: Optional[QChart] = None
        self.drawdown_chart: Optional[QChart] = None
        self.equity_view: Optional[QChartView] = None
        self.drawdown_view: Optional[QChartView] = None
        self._times: List[QtCore.QDateTime] = []
        self._equity: List[float] = []
        self._drawdown: List[float] = []
        self._splitter: Optional[QtWidgets.QSplitter] = None

        if CHARTS_AVAILABLE:
            self.equity_chart = QChart()
            self.equity_chart.setBackgroundBrush(QtGui.QColor("#0f121a"))
            self.equity_chart.setPlotAreaBackgroundBrush(QtGui.QColor("#0e141f"))
            self.equity_chart.setPlotAreaBackgroundVisible(True)
            self.equity_chart.legend().hide()

            self.drawdown_chart = QChart()
            self.drawdown_chart.setBackgroundBrush(QtGui.QColor("#0f121a"))
            self.drawdown_chart.setPlotAreaBackgroundBrush(QtGui.QColor("#0e141f"))
            self.drawdown_chart.setPlotAreaBackgroundVisible(True)
            self.drawdown_chart.legend().hide()

            self.equity_view = QChartView(self.equity_chart)
            self.equity_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            self.drawdown_view = QChartView(self.drawdown_chart)
            self.drawdown_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

            splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
            splitter.addWidget(self.equity_view)
            splitter.addWidget(self.drawdown_view)
            splitter.setStretchFactor(0, 2)
            splitter.setStretchFactor(1, 1)
            self._splitter = splitter

            self.stack.addWidget(splitter)
            self.stack.setCurrentWidget(splitter)
        else:
            self.stack.addWidget(self.placeholder)
            self.stack.setCurrentWidget(self.placeholder)

        self.log_toggle.stateChanged.connect(self._render)
        self.overlay_toggle.stateChanged.connect(self._render)
        self.sharpe_toggle.stateChanged.connect(self._render)
        self.sharpe_window.valueChanged.connect(self._render)

    def set_series(self, times: List[QtCore.QDateTime], equity: List[float], drawdown: List[float]) -> None:
        self._times = times
        self._equity = equity
        self._drawdown = drawdown
        self._render()

    def _clear_chart(self, chart: QChart) -> None:
        for axis in list(chart.axes()):
            chart.removeAxis(axis)
        chart.removeAllSeries()

    def _rolling_sharpe(self, window: int) -> List[Tuple[int, float]]:
        values = self._equity
        if len(values) < 2 or window < 2:
            return []
        returns: List[float] = []
        for i in range(1, len(values)):
            prev = values[i - 1]
            returns.append((values[i] - prev) / prev if prev else 0.0)
        out: List[Tuple[int, float]] = []
        if len(returns) < window:
            return out
        for i in range(window - 1, len(returns)):
            slice_ = returns[i - window + 1 : i + 1]
            mean = sum(slice_) / window
            var = sum((r - mean) ** 2 for r in slice_) / window
            std = var ** 0.5
            sharpe = (mean / std * (window ** 0.5)) if std > 0 else 0.0
            out.append((i + 1, sharpe))
        return out

    def _render(self) -> None:
        if not CHARTS_AVAILABLE or self.equity_chart is None or self.drawdown_chart is None:
            return
        if not self._times or not self._equity:
            self._clear_chart(self.equity_chart)
            self._clear_chart(self.drawdown_chart)
            return

        overlay = self.overlay_toggle.isChecked()
        show_sharpe = self.sharpe_toggle.isChecked()
        log_scale = self.log_toggle.isChecked()

        if self.drawdown_view is not None:
            self.drawdown_view.setVisible(not overlay)
        if self._splitter is not None:
            if overlay:
                self._splitter.setSizes([1, 0])
            else:
                sizes = self._splitter.sizes()
                if sizes and sizes[-1] == 0:
                    self._splitter.setSizes([2, 1])

        self._clear_chart(self.equity_chart)
        self._clear_chart(self.drawdown_chart)

        equity_series = QLineSeries()
        equity_series.setColor(QtGui.QColor("#4ed298"))
        for t, v in zip(self._times, self._equity):
            equity_series.append(t.toMSecsSinceEpoch(), v)

        axis_x = QDateTimeAxis()
        axis_x.setFormat("MM-dd")
        axis_x.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_x.setGridLineColor(QtGui.QColor("#1c273a"))

        min_eq = min(self._equity)
        max_eq = max(self._equity)
        if log_scale and min_eq > 0:
            axis_y: QValueAxis | QLogValueAxis = QLogValueAxis()
            axis_y.setBase(10)
            axis_y.setRange(min_eq * 0.95, max_eq * 1.05)
        else:
            axis_y = QValueAxis()
            axis_y.setRange(min_eq * 0.98, max_eq * 1.02 if max_eq != 0 else 1)
        axis_y.setLabelsColor(QtGui.QColor("#b6c0db"))
        axis_y.setGridLineColor(QtGui.QColor("#1c273a"))

        self.equity_chart.addSeries(equity_series)
        self.equity_chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.equity_chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignRight)
        equity_series.attachAxis(axis_x)
        equity_series.attachAxis(axis_y)

        # Drawdown / sharpe overlays
        dd_series = QLineSeries()
        dd_series.setColor(QtGui.QColor("#ff5a5a"))
        for t, v in zip(self._times, self._drawdown):
            dd_series.append(t.toMSecsSinceEpoch(), v)

        sharpe_points = self._rolling_sharpe(self.sharpe_window.value()) if show_sharpe else []
        sharpe_series = QLineSeries()
        sharpe_series.setColor(QtGui.QColor("#ffd166"))
        for idx, val in sharpe_points:
            sharpe_series.append(self._times[idx].toMSecsSinceEpoch(), val)

        if overlay:
            axis_dd = QValueAxis()
            axis_dd.setLabelsColor(QtGui.QColor("#b6c0db"))
            axis_dd.setGridLineColor(QtGui.QColor("#1c273a"))
            dd_min = min(self._drawdown) if self._drawdown else 0.0
            dd_max = max(self._drawdown) if self._drawdown else 0.0
            sharpe_vals = [v for _, v in sharpe_points] if sharpe_points else []
            if sharpe_vals:
                dd_min = min(dd_min, min(sharpe_vals))
                dd_max = max(dd_max, max(sharpe_vals))
            axis_dd.setRange(dd_min * 1.05, dd_max * 1.05 if dd_max != 0 else 1)

            self.equity_chart.addSeries(dd_series)
            self.equity_chart.addAxis(axis_dd, QtCore.Qt.AlignmentFlag.AlignLeft)
            dd_series.attachAxis(axis_x)
            dd_series.attachAxis(axis_dd)
            if show_sharpe:
                self.equity_chart.addSeries(sharpe_series)
                sharpe_series.attachAxis(axis_x)
                sharpe_series.attachAxis(axis_dd)
        else:
            # Drawdown chart
            dd_axis_x = QDateTimeAxis()
            dd_axis_x.setFormat("MM-dd")
            dd_axis_x.setLabelsColor(QtGui.QColor("#b6c0db"))
            dd_axis_x.setGridLineColor(QtGui.QColor("#1c273a"))
            dd_axis_y = QValueAxis()
            dd_axis_y.setLabelsColor(QtGui.QColor("#b6c0db"))
            dd_axis_y.setGridLineColor(QtGui.QColor("#1c273a"))

            dd_min = min(self._drawdown) if self._drawdown else 0.0
            dd_max = max(self._drawdown) if self._drawdown else 0.0
            sharpe_vals = [v for _, v in sharpe_points] if sharpe_points else []
            if sharpe_vals:
                dd_min = min(dd_min, min(sharpe_vals))
                dd_max = max(dd_max, max(sharpe_vals))
            dd_axis_y.setRange(dd_min * 1.05, dd_max * 1.05 if dd_max != 0 else 1)

            self.drawdown_chart.addSeries(dd_series)
            self.drawdown_chart.addAxis(dd_axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
            self.drawdown_chart.addAxis(dd_axis_y, QtCore.Qt.AlignmentFlag.AlignRight)
            dd_series.attachAxis(dd_axis_x)
            dd_series.attachAxis(dd_axis_y)

            if show_sharpe:
                self.drawdown_chart.addSeries(sharpe_series)
                sharpe_series.attachAxis(dd_axis_x)
                sharpe_series.attachAxis(dd_axis_y)
