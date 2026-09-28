import pytest

from bot.brokers.alpaca_retry import AlpacaStopRetryMixin
from bot.brokers.alpaca import AlpacaPaperBroker


class DummyAlpacaBroker(AlpacaStopRetryMixin):
    def __init__(self, responses, *, positions, open_orders=None, add_stop_on_success=True):
        self.responses = list(responses)
        self.positions = list(positions)
        self.open_orders = list(open_orders or [])
        self.add_stop_on_success = add_stop_on_success
        self.call_count = 0
        self.submitted_payloads = []

    def get_positions_raw(self):
        return self.positions

    def get_orders_raw(self, **_kwargs):
        return self.open_orders

    def submit_order_payload(self, payload):
        self.submitted_payloads.append(dict(payload))
        response = self.responses[self.call_count]
        self.call_count += 1
        if isinstance(response, Exception):
            raise response
        if self.add_stop_on_success and response.get("id"):
            self.open_orders.append(
                {
                    "id": response["id"],
                    "symbol": payload["symbol"],
                    "side": payload["side"],
                    "type": payload["type"],
                    "stop_price": payload["stop_price"],
                }
            )
        return response


def test_retry_is_wired_into_the_real_alpaca_broker():
    assert issubclass(AlpacaPaperBroker, AlpacaStopRetryMixin)


def test_stop_retry_verifies_open_stop_on_first_attempt():
    broker = DummyAlpacaBroker(
        [{"id": "stop-123", "status": "new"}],
        positions=[{"symbol": "AAPL", "side": "long", "qty": "10"}],
    )

    response = broker.submit_standalone_stop_with_retry(
        symbol="AAPL", qty=10, side="buy", stop_price=150.00, max_retries=3, backoff_factor=0.0
    )

    assert response["status"] == "verified"
    assert response["verified"] is True
    assert broker.call_count == 1
    assert broker.submitted_payloads[0]["side"] == "sell"


def test_stop_retry_reuses_client_id_after_timeout_then_verifies():
    broker = DummyAlpacaBroker(
        [RuntimeError("Network timeout"), {"id": "stop-456", "status": "accepted"}],
        positions=[{"symbol": "MSFT", "side": "short", "qty": "50"}],
    )

    response = broker.submit_standalone_stop_with_retry(
        symbol="MSFT", qty=50, side="sell", stop_price=400.00, client_order_id="entry-msft", max_retries=3, backoff_factor=0.0
    )

    assert response["status"] == "verified"
    assert broker.call_count == 2
    assert broker.submitted_payloads[0]["client_order_id"] == broker.submitted_payloads[1]["client_order_id"]
    assert broker.submitted_payloads[0]["side"] == "buy"


def test_existing_nested_stop_prevents_duplicate_submission():
    broker = DummyAlpacaBroker(
        [],
        positions=[{"symbol": "SPY", "side": "long", "qty": "3"}],
        open_orders=[
            {
                "id": "parent-1",
                "symbol": "SPY",
                "side": "buy",
                "type": "market",
                "legs": [{"id": "stop-1", "symbol": "SPY", "side": "sell", "type": "stop"}],
            }
        ],
    )

    response = broker.submit_standalone_stop_with_retry(
        symbol="SPY", qty=3, side="buy", stop_price=498.0, max_retries=3, backoff_factor=0.0
    )

    assert response["status"] == "verified_existing"
    assert broker.call_count == 0


def test_flat_position_skips_stop_to_prevent_reversal():
    broker = DummyAlpacaBroker([{"id": "should-not-submit"}], positions=[])

    response = broker.submit_standalone_stop_with_retry(
        symbol="TSLA", qty=5, side="buy", stop_price=200.0, max_retries=3, backoff_factor=0.0
    )

    assert response["status"] == "skipped_no_open_position"
    assert broker.call_count == 0


def test_stop_retry_exhausted_raises_after_unverified_attempts():
    broker = DummyAlpacaBroker(
        [RuntimeError("Error 1"), RuntimeError("Error 2"), RuntimeError("Error 3")],
        positions=[{"symbol": "TSLA", "side": "long", "qty": "5"}],
    )

    with pytest.raises(RuntimeError, match="Failed to submit standalone stop"):
        broker.submit_standalone_stop_with_retry(
            symbol="TSLA", qty=5, side="buy", stop_price=200.0, max_retries=3, backoff_factor=0.0
        )
    assert broker.call_count == 3
