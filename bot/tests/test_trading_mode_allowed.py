import os
import json
import pytest
from unittest.mock import MagicMock
from bot.webhook_server import TradingViewWebhookEngine

def test_trading_mode_allowed_flow(tmp_path, monkeypatch):
    # Setup mock config for Intraday
    config = {
        "top_down": {
            "profile": "velez_intraday"
        },
        "scanner": {
            "enabled": True,
            "symbols": []
        }
    }
    
    engine = TradingViewWebhookEngine(config)
    engine.logger = MagicMock()
    
    settings_path = str(tmp_path / "trading_bull_settings.json")
    monkeypatch.setenv("TRADING_BULL_SETTINGS_PATH", settings_path)
    
    # Case 1: Dual Mode -> Intraday bot should be allowed
    with open(settings_path, "w") as f:
        json.dump({"trading_mode": "dual"}, f)
    assert engine._check_trading_mode_allowed() is True
    
    # Case 2: Intraday Mode -> Intraday bot should be allowed
    with open(settings_path, "w") as f:
        json.dump({"trading_mode": "intraday"}, f)
    assert engine._check_trading_mode_allowed() is True
    
    # Case 3: Swing Mode -> Intraday bot should be BLOCKED
    with open(settings_path, "w") as f:
        json.dump({"trading_mode": "swing"}, f)
    assert engine._check_trading_mode_allowed() is False
    
    # Case 4: Missing settings file -> Default to allowed (True)
    if os.path.exists(settings_path):
        os.remove(settings_path)
    assert engine._check_trading_mode_allowed() is True
