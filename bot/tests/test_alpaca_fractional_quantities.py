from datetime import datetime, timezone

import pytest

from bot.brokers.alpaca import AlpacaPaperBroker
from bot.core.types import Order, OrderType, Side


def _order(*, side: Side, qty: float, position_intent: str | None = None) -> Order:
    metadata = {} if position_intent is None else {"position_intent": position_intent}
    return Order(
        symbol="TEST",
        side=side,
        qty=qty,
        order_type=OrderType.MARKET,
        limit_price=None,
        timestamp=datetime.now(timezone.utc),
        reason="fractional-test",
        metadata=metadata,
    )


def test_alpaca_reconciliation_preserves_fractional_long_and_short_quantities():
    broker = AlpacaPaperBroker()
    broker.get_positions_raw = lambda: [
        {"symbol": "LONG", "qty": "1.23456", "side": "long", "avg_entry_price": "10"},
        {"symbol": "SHORT", "qty": "2", "side": "short", "avg_entry_price": "20"},
    ]

    positions = {position.symbol: position for position in broker.get_positions()}

    assert positions["LONG"].qty == 1.2346
    assert positions["SHORT"].qty == -2.0


def test_fractional_long_entry_and_close_are_four_decimal_and_explicit():
    broker = AlpacaPaperBroker()

    entry = broker.order_payload_from_order(_order(side=Side.BUY, qty=1.23456), attach_stop_loss=False)
    close = broker.order_payload_from_order(
        _order(side=Side.SELL, qty=1.23456, position_intent="sell_to_close"),
        attach_stop_loss=False,
    )

    assert entry["position_intent"] == "buy_to_open"
    assert close["position_intent"] == "sell_to_close"
    assert entry["qty"] == close["qty"] == "1.2346"


def test_short_entry_and_cover_are_integer_only():
    broker = AlpacaPaperBroker()

    entry = broker.build_entry_payload(
        symbol="TEST",
        side="sell",
        qty=2.9876,
        order_type="market",
        entry_price=None,
        stop_price=11,
    )
    cover = broker.order_payload_from_order(
        _order(side=Side.BUY, qty=2.9876, position_intent="buy_to_close"),
        attach_stop_loss=False,
    )

    assert entry["position_intent"] == "sell_to_open"
    assert cover["position_intent"] == "buy_to_close"
    assert entry["qty"] == cover["qty"] == "2"


def test_fractional_short_entry_that_floors_to_zero_is_rejected():
    broker = AlpacaPaperBroker()

    with pytest.raises(ValueError, match="floors to zero"):
        broker.build_entry_payload(
            symbol="TEST",
            side="sell",
            qty=0.5,
            order_type="market",
            entry_price=None,
            stop_price=11,
        )


def test_position_intent_must_match_the_order_side():
    broker = AlpacaPaperBroker()

    with pytest.raises(ValueError, match="does not match sell side"):
        broker.order_payload_from_order(
            _order(side=Side.SELL, qty=1.25, position_intent="buy_to_open"),
            attach_stop_loss=False,
        )
