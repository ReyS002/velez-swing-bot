import pytest

pd = pytest.importorskip("pandas")

from bot.core import trifecta
from bot.webhook_server import TradingViewWebhookEngine


def _engine(monkeypatch, *, key=True, fallback=True, timeframe="1Day"):
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    if key:
        monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    config = {
        "portfolio": {"initial_cash": 100000},
        "risk": {"risk_per_trade": 0.005, "max_dollar_risk_per_trade": 1000, "max_daily_loss_pct": 0.02,
                 "max_consecutive_losses": 3, "max_open_positions": 3, "max_leverage": 2.0, "max_order_qty": 10000,
                 "max_stop_pct": 0.1},
        "webhook": {"auth_required": True, "secret": "s", "execute_orders": False, "paper_only": True},
        "event_filter": {"enabled": False},
        "scanner": {"timeframe": timeframe, "futures_yahoo_fallback": fallback, "symbols": ["ES"]},
        "symbols": [{"symbol": "ES", "type": "future", "contract_multiplier": 50}],
        "velez_strategy": {},
    }
    return TradingViewWebhookEngine(config)


def _frame(n=60):
    index = pd.date_range("2026-07-01", periods=n, freq="D")
    return pd.DataFrame({"Open": 5000.0, "High": 5010.0, "Low": 4990.0, "Close": 5005.0, "Volume": 1000}, index=index)


def _no_polygon(engine, monkeypatch, status="polygon_data_404:404 page not found"):
    def fail(*args, **kwargs):
        raise RuntimeError(status)
    monkeypatch.setattr(engine, "_polygon_request", fail)


def test_polygon_404_falls_back_to_yahoo_and_remembers_it(monkeypatch):
    engine = _engine(monkeypatch)
    calls = []
    monkeypatch.setattr(engine, "_polygon_request", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(RuntimeError("polygon_data_404:x")))
    seen = []
    monkeypatch.setattr(trifecta, "fetch_bars_yfinance", lambda ticker, interval, *a, **k: seen.append((ticker, interval)) or _frame())
    bars = engine._fetch_scanner_bars(symbol="ES", asset_type="future")
    assert len(bars) == 60 and seen == [("ES=F", "D")] and bars[-1].close == 5005.0 and bars[0].timestamp.tzinfo
    engine._fetch_scanner_bars(symbol="ES", asset_type="future")
    assert len(calls) == 1  # not entitled: Polygon is not asked again within the hour


def test_no_polygon_key_uses_yahoo_when_allowed_and_fails_otherwise(monkeypatch):
    monkeypatch.setattr(trifecta, "fetch_bars_yfinance", lambda *a, **k: _frame())
    assert len(_engine(monkeypatch, key=False)._fetch_scanner_bars(symbol="ES", asset_type="future")) == 60
    with pytest.raises(RuntimeError, match="missing_polygon_api_key"):
        _engine(monkeypatch, key=False, fallback=False)._fetch_scanner_bars(symbol="ES", asset_type="future")


def test_intraday_scans_never_use_yahoo(monkeypatch):
    engine = _engine(monkeypatch, timeframe="5Min")
    assert engine._futures_yahoo_fallback_allowed() is False
    _no_polygon(engine, monkeypatch)
    monkeypatch.setattr(trifecta, "fetch_bars_yfinance", lambda *a, **k: _frame())
    with pytest.raises(RuntimeError, match="polygon_data_404"):
        engine._fetch_scanner_bars(symbol="ES", asset_type="future")
    assert _engine(monkeypatch, timeframe="1Hour")._futures_yahoo_fallback_allowed() is True


def test_an_unmapped_root_and_empty_data_are_errors(monkeypatch):
    engine = _engine(monkeypatch, key=False)
    with pytest.raises(RuntimeError, match="yahoo_futures_unmapped"):
        engine._fetch_scanner_bars(symbol="ZZ", asset_type="future")
    monkeypatch.setattr(trifecta, "fetch_bars_yfinance", lambda *a, **k: pd.DataFrame())
    with pytest.raises(RuntimeError, match="yahoo_futures_no_data"):
        engine._fetch_scanner_bars(symbol="ES", asset_type="future")


def test_the_polygon_path_is_unchanged_when_it_works(monkeypatch):
    engine = _engine(monkeypatch)
    row = {"window_start": 1_790_000_000_000_000_000, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 3}
    monkeypatch.setattr(engine, "_polygon_request", lambda *a, **k: {"results": [row]})
    monkeypatch.setattr(trifecta, "fetch_bars_yfinance", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Yahoo used")))
    assert len(engine._fetch_scanner_bars(symbol="ES", asset_type="future")) == 1
