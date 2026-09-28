from unittest.mock import Mock

import pandas as pd
import pytest
import yfinance as yf

from bot.core import trifecta


def bars(start="2026-09-25 09:30", periods=60, freq="2min"):
    values = list(range(100, 100 + periods))
    return pd.DataFrame(
        {"Open": values, "High": [v + 2 for v in values],
         "Low": [v - 1 for v in values], "Close": [v + 1 for v in values],
         "Volume": [10] * periods},
        index=pd.date_range(start, periods=periods, freq=freq, tz="America/New_York"),
    )


@pytest.mark.parametrize("interval", ["1", "2", "3", "5", "10", "15", "30", "60", "120", "240", "2m", "4h", "bogus"])
def test_tradier_history_never_substitutes_daily_for_intraday(monkeypatch, interval):
    request = Mock()
    monkeypatch.setattr(trifecta.requests, "get", request)
    assert trifecta.fetch_bars_tradier("AAPL", interval, token="test-token").empty
    request.assert_not_called()


@pytest.mark.parametrize("interval,expected", [("D", "daily"), ("W", "weekly"), ("M", "monthly")])
def test_tradier_calendar_intervals_unchanged(monkeypatch, interval, expected):
    response = Mock(status_code=200)
    response.json.return_value = {"history": {"day": [{"date": "2026-09-25", "open": 1, "high": 3, "low": 1, "close": 2, "volume": 10}]}}
    request = Mock(return_value=response)
    monkeypatch.setattr(trifecta.requests, "get", request)
    assert len(trifecta.fetch_bars_tradier("AAPL", interval, token="test-token")) == 1
    assert request.call_args.kwargs["params"]["interval"] == expected


@pytest.mark.parametrize("symbol", ["EURUSD=X", "ES=F", "^GSPC"])
def test_existing_non_equity_fast_skip_preserved(monkeypatch, symbol):
    request = Mock()
    monkeypatch.setattr(trifecta.requests, "get", request)
    assert trifecta.fetch_bars_tradier(symbol, "D", token="test-token").empty
    request.assert_not_called()


@pytest.mark.parametrize("interval,provider,period", [
    ("1", "1m", "5d"), ("2", "2m", "5d"), ("2m", "2m", "5d"),
    ("3", "1m", "5d"), ("5", "5m", "5d"), ("10", "5m", "1mo"),
    ("15", "15m", "1mo"), ("30", "30m", "1mo"),
    ("60", "60m", "3mo"), ("120", "60m", "6mo"), ("240", "60m", "6mo"),
    ("4h", "60m", "6mo"), ("D", "1d", "1y"), ("W", "1wk", "3mo"), ("M", "1mo", "3mo"),
])
def test_yahoo_requests_only_supported_source_intervals(monkeypatch, interval, provider, period):
    download = Mock(return_value=bars(freq="1min"))
    monkeypatch.setattr(yf, "download", download)
    assert not trifecta.fetch_bars_yfinance("AAPL", interval).empty
    assert download.call_args.kwargs["interval"] == provider
    assert download.call_args.kwargs["period"] == period


def test_unknown_timeframe_fails_closed_without_daily_request(monkeypatch):
    download = Mock()
    monkeypatch.setattr(yf, "download", download)
    assert trifecta.fetch_bars_yfinance("AAPL", "bogus").empty
    download.assert_not_called()


@pytest.mark.parametrize("interval,source_minutes,target_minutes", [("3", 1, 3), ("10", 5, 10), ("120", 60, 120), ("240", 60, 240)])
def test_derived_bars_aggregate_ohlcv_without_crossing_sessions(monkeypatch, interval, source_minutes, target_minutes):
    count = target_minutes // source_minutes
    first = bars(periods=count * 2, freq=f"{source_minutes}min")
    second = bars(start="2026-09-28 09:30", periods=count * 2, freq=f"{source_minutes}min")
    monkeypatch.setattr(yf, "download", Mock(return_value=pd.concat([first, second])))
    result = trifecta.fetch_bars_yfinance("AAPL", interval)
    assert len(result) == 4
    assert result.index[0] == first.index[0]
    assert result.index[2] == second.index[0]
    assert result.index[1] - result.index[0] == pd.Timedelta(minutes=target_minutes)
    assert result.iloc[0].to_dict() == {"Open": 100, "High": 101 + count, "Low": 99, "Close": 100 + count, "Volume": count * 10}


def test_intraday_dispatch_reaches_yahoo_with_real_timestamps(monkeypatch):
    request = Mock()
    expected = bars()
    monkeypatch.setattr(trifecta.requests, "get", request)
    monkeypatch.setattr(yf, "download", Mock(return_value=expected))
    result = trifecta.fetch_bars("AAPL", "2", token="test-token")
    request.assert_not_called()
    pd.testing.assert_frame_equal(result, expected)


def test_yahoo_failure_returns_empty_not_daily(monkeypatch):
    request = Mock()
    monkeypatch.setattr(trifecta.requests, "get", request)
    monkeypatch.setattr(yf, "download", Mock(side_effect=RuntimeError("unavailable")))
    assert trifecta.fetch_bars("AAPL", "2", token="test-token").empty
    request.assert_not_called()


@pytest.mark.parametrize("age_minutes,expected_state,expected_action", [(1, "aligned", "full_size"), (120, "stale", "skip")])
def test_freshness_protection_unchanged(age_minutes, expected_state, expected_action):
    frame = bars()
    frame.index = pd.date_range(end=pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=age_minutes), periods=len(frame), freq="2min")
    result = trifecta.score_webhook_confluence("AAPL", "2", "buy", {"webhook_confluence": {
        "enabled": True, "higher_timeframes": [], "max_bar_age_minutes": {"2": 5}}}, fetcher=lambda *_: frame)
    assert result["timeframes"]["2"]["state"] == expected_state
    assert result["action"] == expected_action
