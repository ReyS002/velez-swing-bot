from collections import deque
from datetime import datetime, timezone

from bot.calendar_feeds import CalendarFeedService


class FakeBroker:
    def is_configured(self):
        return True

    def get_positions_raw(self):
        return [{"symbol": "SPY", "unrealized_pl": "125.34"}]

    def get_portfolio_history_raw(self, *, period="1M", timeframe="1D"):
        return {"equity": ["100000", "101250.50"], "profit_loss": ["0", "1250.50"]}

    def get_calendar_raw(self, *, start=None, end=None):
        return [{"date": "2026-05-28", "open": "09:30", "close": "16:00"}]


class MissingBroker:
    def is_configured(self):
        return False


class FakeResponse:
    status_code = 200

    def __init__(self, text):
        self.text = text


def config():
    return {
        "timezone": "America/New_York",
        "symbols": [
            {"symbol": "SPY", "type": "equity"},
            {"symbol": "ES", "type": "future"},
        ],
    }


def test_calendar_payload_wires_alpaca_alerts_earnings_and_macro(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "demo-key")
    monkeypatch.setenv("CALENDAR_MACRO_FEEDS_ENABLED", "true")

    def fake_get(url, params=None, timeout=None, headers=None):
        if "alphavantage.co" in url:
            return FakeResponse(
                "symbol,name,reportDate,fiscalDateEnding,estimate,currency\n"
                "SPY,SPDR S&P 500 ETF Trust,2026-05-29,2026-03-31,1.23,USD\n"
            )
        if "bls.ics" in url:
            return FakeResponse(
                "BEGIN:VCALENDAR\n"
                "BEGIN:VEVENT\n"
                "DTSTART:20260529T083000\n"
                "SUMMARY:Consumer Price Index\n"
                "END:VEVENT\n"
                "END:VCALENDAR\n"
            )
        return FakeResponse("<html><body>No matching scheduled events</body></html>")

    monkeypatch.setattr("bot.calendar_feeds.requests.get", fake_get)

    service = CalendarFeedService(
        FakeBroker(),
        config(),
        deque(
            [
                {
                    "timestamp": "2026-05-28T14:30:00Z",
                    "symbol": "SPY",
                    "status": "proposed",
                    "play": "elephant_bar",
                    "side": "buy",
                }
            ]
        ),
        now_fn=lambda: datetime(2026, 5, 28, 15, 0, tzinfo=timezone.utc),
    )

    payload = service.month_payload()

    assert payload["pnl"]["month_pl"] == 1250.5
    assert payload["pnl"]["unrealized_pl"] == 125.34
    assert payload["alerts"]["count"] == 1
    assert payload["session"]["status"] == "Open day"
    assert payload["earnings"][0]["symbol"] == "SPY"
    assert payload["events"][0]["title"] == "Consumer Price Index"
    assert payload["sources"]["alpha_vantage"]["ok"] is True


def test_calendar_payload_fails_soft_without_keys_or_broker(monkeypatch):
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("AV_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_VINTAGE_API_KEY", raising=False)
    monkeypatch.setenv("CALENDAR_MACRO_FEEDS_ENABLED", "false")

    service = CalendarFeedService(
        MissingBroker(),
        config(),
        deque(),
        now_fn=lambda: datetime(2026, 5, 28, 15, 0, tzinfo=timezone.utc),
    )

    payload = service.month_payload()

    assert payload["ok"] is True
    assert payload["pnl"]["month_pl"] == 0
    assert payload["sources"]["alpaca_pnl"]["reason"] == "missing_credentials"
    assert payload["sources"]["alpha_vantage"]["reason"] == "missing_api_key"
    assert payload["events"] == []


def test_release_html_parser_keeps_titles_compact(monkeypatch):
    monkeypatch.setenv("CALENDAR_MACRO_FEEDS_ENABLED", "false")
    service = CalendarFeedService(
        MissingBroker(),
        config(),
        deque(),
        now_fn=lambda: datetime(2026, 5, 28, 15, 0, tzinfo=timezone.utc),
    )

    html = """
    <html><body>
      May 28 8:30 AM N ews Personal Income and Outlays, April 2026 View
      May 28 8:30 AM N ews GDP (Second Estimate) and Corporate Profits, 1st Quarter 2026
    </body></html>
    """

    events = service._parse_release_html(
        html,
        "BEA",
        "https://www.bea.gov/news/schedule/full",
        datetime(2026, 5, 28, tzinfo=timezone.utc).date(),
        datetime(2026, 5, 31, tzinfo=timezone.utc).date(),
        ("PCE", "Personal Income", "GDP"),
    )

    assert events[0]["title"] == "Personal Income and Outlays, April 2026"
