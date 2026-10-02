import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def isolated_journal_db(monkeypatch, tmp_path):
    monkeypatch.setenv("VELEZ_JOURNAL_DB", str(tmp_path / "trading_bull_test.sqlite3"))
    monkeypatch.setenv("VELEZ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CALENDAR_MACRO_FEEDS_ENABLED", "false")
    monkeypatch.setenv("VELEZ_DASHBOARD_AUTH_ENABLED", "false")
    monkeypatch.setenv("VELEZ_DASHBOARD_TIER", "pro")
    monkeypatch.setenv("VELEZ_EXECUTE_ORDERS", "false")
    monkeypatch.setenv("VELEZ_LIFECYCLE_AUTO_EXECUTE", "false")
    monkeypatch.setenv("WINSTON_LLM_PROVIDER", "rule_based")
    monkeypatch.setenv("WINSTON_MENTOR_LLM_PROVIDER", "rule_based")


@pytest.fixture(autouse=True)
def offline_yahoo_bars(request, monkeypatch):
    """The Yahoo bar fallback reaches the network now that it forwards days_back: keep tests offline
    (the trifecta data tests exercise it themselves)."""
    if request.node.module.__name__.endswith("test_trifecta_data_timeframes"):
        return
    try:
        import pandas as pd
        from bot.core import trifecta
    except ImportError:
        return  # a minimal environment without pandas has no Yahoo path to stub

    monkeypatch.setattr(trifecta, "fetch_bars_yfinance", lambda *args, **kwargs: pd.DataFrame())
