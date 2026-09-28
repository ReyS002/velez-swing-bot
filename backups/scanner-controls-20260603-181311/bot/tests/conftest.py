import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def isolated_journal_db(monkeypatch, tmp_path):
    monkeypatch.setenv("VELEZ_JOURNAL_DB", str(tmp_path / "trading_bull_test.sqlite3"))
    monkeypatch.setenv("CALENDAR_MACRO_FEEDS_ENABLED", "false")
