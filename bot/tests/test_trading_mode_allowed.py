import os
import json
import pytest
from unittest.mock import MagicMock
from bot.webhook_server import TradingViewWebhookEngine

def test_trading_mode_allowed_flow():
    # Setup mock config for Swing
    config = {
        "top_down": {
            "profile": "velez_swing"
        },
        "scanner": {
            "enabled": True,
            "symbols": []
        }
    }
    
    engine = TradingViewWebhookEngine(config)
    engine.logger = MagicMock()
    
    settings_path = "/app/data/trading_bull_settings.json"
    
    # Mocking reading from local settings file path on host during test environment
    os.makedirs("/app/data", exist_ok=True)
    
    # Case 1: Dual Mode -> Swing bot should be allowed
    with open(settings_path, "w") as f:
        json.dump({"trading_mode": "dual"}, f)
    assert engine._check_trading_mode_allowed() is True
    
    # Case 2: Intraday Mode -> Swing bot should be BLOCKED
    with open(settings_path, "w") as f:
        json.dump({"trading_mode": "intraday"}, f)
    assert engine._check_trading_mode_allowed() is False
    
    # Case 3: Swing Mode -> Swing bot should be allowed
    with open(settings_path, "w") as f:
        json.dump({"trading_mode": "swing"}, f)
    assert engine._check_trading_mode_allowed() is True
    
    # Case 4: Missing settings file -> Default to allowed (True)
    if os.path.exists(settings_path):
        os.remove(settings_path)
    assert engine._check_trading_mode_allowed() is True
