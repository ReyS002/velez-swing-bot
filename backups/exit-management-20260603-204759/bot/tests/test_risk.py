from bot.core.risk import RiskManager
from bot.core.types import Side


def test_position_sizing():
    risk = RiskManager(
        {
            "risk_per_trade": 0.01,
            "max_daily_loss_pct": 0.02,
            "max_consecutive_losses": 3,
            "max_open_positions": 2,
            "max_leverage": 2.0,
            "max_order_qty": 1000,
        }
    )
    qty = risk.calculate_position_size(
        equity=100000,
        entry_price=100,
        stop_price=98,
        contract_multiplier=1,
        max_order_qty=1000,
        max_leverage=2.0,
    )
    assert qty > 0


def test_initial_stop_atr():
    risk = RiskManager(
        {
            "risk_per_trade": 0.01,
            "max_daily_loss_pct": 0.02,
            "max_consecutive_losses": 3,
            "max_open_positions": 2,
            "max_leverage": 2.0,
            "max_order_qty": 1000,
        }
    )
    stop = risk.initial_stop(side=Side.BUY, entry_price=100, atr=2, swing_level=None, config={"stop_type": "atr", "stop_atr_mult": 2})
    assert stop == 96
