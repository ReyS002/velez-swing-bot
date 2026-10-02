"""The Yahoo bar wrapper forwards days_back to the fetch it wraps."""

import pandas as pd

from bot.webhook_server import yahoo_fetch_bars_safe


def test_yahoo_wrapper_forwards_days_back():
    seen = {}

    def fetch(symbol, timeframe, days_back=60):
        seen.update(symbol=symbol, timeframe=timeframe, days_back=days_back)
        return pd.DataFrame({"Close": [1.0]})

    frame = yahoo_fetch_bars_safe("SPY", "D", days_back=120, fetch_impl=fetch)
    assert not frame.empty and seen["days_back"] == 120
    yahoo_fetch_bars_safe("SPY", "D", fetch_impl=fetch)
    assert seen["days_back"] == 60  # not given: the fetch's own default
