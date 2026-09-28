from __future__ import annotations

from PySide6 import QtGui


def app_font() -> QtGui.QFont:
    font = QtGui.QFont("Avenir Next")
    font.setPointSize(12)
    return font


def stylesheet() -> str:
    return """
    QMainWindow {
        background-color: #0f121a;
    }
    QMainWindow[session="pre"] {
        background-color: #101722;
    }
    QMainWindow[session="after"] {
        background-color: #11131c;
    }
    QMainWindow[session="closed"] {
        background-color: #0d1017;
    }
    QWidget {
        color: #eef2ff;
        font-family: "Avenir Next";
        font-size: 12px;
    }
    QTabWidget::pane {
        border: 1px solid #1d2232;
        background: #111624;
        border-radius: 10px;
        padding: 6px;
    }
    QTabBar::tab {
        background: #141b2b;
        color: #97a0b8;
        padding: 10px 16px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        margin-right: 4px;
    }
    QTabBar::tab:selected {
        background: #1b2438;
        color: #eef2ff;
    }
    QGroupBox {
        border: 1px solid #1f2a44;
        border-radius: 12px;
        margin-top: 12px;
        padding: 12px;
        background: #121827;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 4px 0 4px;
        color: #cfd6ee;
    }
    QLineEdit, QDateEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: #151d2f;
        border: 1px solid #22304d;
        border-radius: 8px;
        padding: 6px 8px;
        color: #eef2ff;
    }
    QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {
        border: 1px solid #4ebcff;
    }
    QCheckBox[chip="true"] {
        background: #141b2b;
        border: 1px solid #263451;
        border-radius: 14px;
        padding: 4px 10px;
        color: #d5dcf0;
    }
    QCheckBox[chip="true"]::indicator {
        width: 0px;
        height: 0px;
    }
    QCheckBox[chip="true"]:checked {
        background: #1f2a44;
    }
    QCheckBox#chip_sma_fast:checked {
        color: #4ebcff;
        border-color: #4ebcff;
    }
    QCheckBox#chip_sma_slow:checked {
        color: #ffab4d;
        border-color: #ffab4d;
    }
    QCheckBox#chip_ema:checked {
        color: #b97cff;
        border-color: #b97cff;
    }
    QCheckBox#chip_volume:checked {
        color: #4ed298;
        border-color: #4ed298;
    }
    QCheckBox#chip_atr:checked {
        color: #ffab4d;
        border-color: #ffab4d;
    }
    QCheckBox#chip_atr_bands:checked {
        color: #7aa2ff;
        border-color: #7aa2ff;
    }
    QCheckBox#chip_rsi:checked {
        color: #9ad36a;
        border-color: #9ad36a;
    }
    QCheckBox#chip_n2w:checked {
        color: #cfa76e;
        border-color: #cfa76e;
    }
    QPushButton {
        background: #ffab4d;
        color: #1a1c25;
        border: none;
        padding: 8px 14px;
        border-radius: 10px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: #ffbe6a;
    }
    QPushButton#tf_1m, QPushButton#tf_5m, QPushButton#tf_15m, QPushButton#tf_1h, QPushButton#tf_1d {
        background: #1a2336;
        color: #d5dcf0;
        border: 1px solid #263451;
        border-radius: 10px;
        padding: 6px 10px;
    }
    QPushButton#tf_1m:pressed, QPushButton#tf_5m:pressed, QPushButton#tf_15m:pressed, QPushButton#tf_1h:pressed, QPushButton#tf_1d:pressed {
        background: #24314d;
    }
    QPushButton:disabled {
        background: #2a3145;
        color: #8a93ad;
    }
    QToolButton#alert_bell {
        background: #141b2b;
        border: 1px solid #263451;
        border-radius: 8px;
        padding: 2px 6px;
        color: #d5dcf0;
    }
    QToolButton#alert_bell:checked {
        background: #2a3145;
        color: #f2c94c;
        border-color: #f2c94c;
    }
    QTableWidget {
        background: #0f141f;
        border: 1px solid #202b44;
        gridline-color: #202b44;
        selection-background-color: #24304b;
        selection-color: #eef2ff;
    }
    QTableWidget::item:focus {
        outline: none;
    }
    QTableWidget::item:selected {
        background: #2b3a57;
        color: #eef2ff;
    }
    QHeaderView::section {
        background: #141b2b;
        color: #b6c0db;
        border: none;
        padding: 6px;
    }
    QPlainTextEdit {
        background: #0e131d;
        border: 1px solid #202b44;
        border-radius: 8px;
        color: #c9d2ee;
    }
    QToolTip {
        background: #1a2336;
        color: #e6ecff;
        border: 1px solid #2b3655;
        border-radius: 6px;
        padding: 6px;
    }
    QScrollBar:vertical {
        background: #0f141f;
        width: 10px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #22304d;
        border-radius: 5px;
        min-height: 20px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QProgressBar {
        background: #111827;
        border: 1px solid #22304d;
        border-radius: 8px;
        text-align: center;
        color: #e6ecff;
    }
    QProgressBar::chunk {
        background: #4ed298;
        border-radius: 8px;
    }
    QFrame#dashboard_header {
        background: #101725;
        border: 1px solid #1f2a44;
        border-radius: 10px;
    }
    QLabel#header_market {
        font-weight: 600;
    }
    QLabel#header_refresh {
        color: #9ad36a;
    }
    QLabel#header_quality {
        color: #b6c0db;
    }
    QLabel#header_symbol {
        color: #cfd6ee;
    }
    """
