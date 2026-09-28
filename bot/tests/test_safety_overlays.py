from datetime import datetime, timezone

from bot.core.event_filter import EventFilter
from bot.webhook_server import TradingViewWebhookEngine


def test_factor_exposure_blocks_a_concentrated_candidate():
    engine = TradingViewWebhookEngine(
        {
            "strategy": {"exits": {"correlation": {"enabled": True, "factor_exposure": {"enabled": True, "max_beta_adjusted_gross_pct": 1.0, "betas": {"NVDA": 1.5}}}}},
            "risk": {"max_consecutive_losses": 3},
            "webhook": {"auth_required": False, "execute_orders": False},
        }
    )
    result = engine._check_correlation("NVDA", [{"symbol": "NVDA", "market_value": "60000"}], candidate_notional=10000, equity=100000)

    assert result["ok"] is False
    assert result["reason"] == "beta_adjusted_gross_exposure_cap"


def test_event_filter_respects_the_configured_blackout_window():
    event_filter = EventFilter({"event_filter": {"enabled": True, "events": [{"timestamp": "2026-08-12T12:30:00Z", "label": "CPI", "type": "macro"}]}})
    event_filter._fetched_events = [(datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc), "CPI", "macro")]
    event_filter._last_fetch = datetime.now(timezone.utc)

    skipped, reason = event_filter.should_skip(now=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc))

    assert skipped is True
    assert "CPI" in reason
