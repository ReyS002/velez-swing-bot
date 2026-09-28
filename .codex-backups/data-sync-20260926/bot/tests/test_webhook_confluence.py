import pandas as pd

from bot.core.trifecta import normalize_timeframe, score_webhook_confluence


def _trend(up: bool) -> pd.DataFrame:
    values = list(range(100, 160)) if up else list(range(160, 100, -1))
    return pd.DataFrame({"Open": values, "High": values, "Low": values, "Close": values, "Volume": [1000] * len(values)})


def test_one_higher_timeframe_conflict_becomes_quarter_starter():
    frames = {"15": _trend(True), "60": _trend(False), "240": _trend(True)}
    result = score_webhook_confluence("SPY", "15m", "buy", {"webhook_confluence": {"enabled": True}}, fetcher=lambda _symbol, tf: frames[tf])

    assert normalize_timeframe("4h") == "240"
    assert result["action"] == "starter"
    assert result["multiplier"] == 0.25
    assert result["higher_opposed"] == 1


def test_both_higher_timeframe_conflicts_skip_the_signal():
    frames = {"15": _trend(True), "60": _trend(False), "240": _trend(False)}
    result = score_webhook_confluence("SPY", "15", "buy", {"webhook_confluence": {"enabled": True}}, fetcher=lambda _symbol, tf: frames[tf])

    assert result["action"] == "skip"
    assert result["multiplier"] == 0.0
    assert result["reason"] == "both_higher_timeframes_opposed"


def test_missing_higher_timeframe_cannot_promote_a_full_size_order():
    frames = {"15": _trend(True), "60": _trend(True), "240": pd.DataFrame()}
    result = score_webhook_confluence("SPY", "15", "buy", {"webhook_confluence": {"enabled": True}}, fetcher=lambda _symbol, tf: frames[tf])

    assert result["action"] == "starter"
    assert result["multiplier"] == 0.25
    assert result["reason"] == "higher_timeframe_data_unavailable:240"
