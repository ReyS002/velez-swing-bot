import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from bot.core.types import Bar, Side, Signal
from bot.webhook_server import TradingViewWebhookEngine, WebhookDecision, create_app


class ScannerBroker:
    def __init__(self, positions=None, orders=None):
        self.config = type("Config", (), {"base_url": "https://paper-api.alpaca.markets", "data_url": "https://data.alpaca.markets"})()
        self.positions = positions or []
        self.orders = orders or []
        self.canceled = []
        self.submitted = []

    def is_configured(self):
        return True

    def validate_connection(self):
        return {"ok": True, "paper": True}

    def get_account(self):
        return {"equity": "100000", "portfolio_value": "100000"}

    def get_positions_raw(self):
        return self.positions

    def get_orders_raw(self, **kwargs):
        return self.orders

    def cancel_order(self, order_id):
        self.canceled.append(order_id)
        self.orders = [order for order in self.orders if order.get("id") != order_id]
        return {}

    def submit_order_payload(self, payload):
        self.submitted.append(payload)
        return {"id": "unexpected-submission"}


def webhook_config():
    return {
        "portfolio": {"initial_cash": 100000},
        "risk": {
            "risk_per_trade": 0.005,
            "max_dollar_risk_per_trade": 1000,
            "max_daily_loss_pct": 0.02,
            "max_consecutive_losses": 3,
            "max_open_positions": 3,
            "max_leverage": 2.0,
            "max_order_qty": 10000,
            "max_stop_pct": 0.1,
        },
        "webhook": {
            "auth_required": True,
            "secret": "test-secret",
            "execute_orders": False,
            "paper_only": True,
            "time_in_force": "day",
        },
        "event_filter": {"enabled": False},
        "symbols": [{"symbol": "SPY", "contract_multiplier": 1}],
        "velez_strategy": {},
    }


def test_tradingview_signal_webhook_proposes_paper_order_without_execution():
    config = webhook_config()
    engine = TradingViewWebhookEngine(config)

    result = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
            "timestamp": "2026-01-01T14:30:00Z",
        },
        path_token="test-secret",
    )

    assert result["ok"]
    decision = result["decisions"][0]
    assert decision["status"] == "proposed"
    assert decision["qty"] == 62
    assert decision["metadata"]["lot_plan"]["lots"] == 1
    assert decision["metadata"]["lot_plan"]["effective_risk_budget"] == 125
    assert decision["order_payload"]["order_class"] == "oto"
    assert decision["order_payload"]["stop_loss"]["stop_price"] == "498.00"


def test_malformed_structured_pine_payload_is_rejected():
    engine = TradingViewWebhookEngine(webhook_config())
    result = engine.handle_payload(
        {
            "mode": "signal", "payload_version": "bullpilot.pine-signal.v2",
            "symbol": "SPY", "side": "buy", "play": "elephant_bar",
            "entry_price": 500, "stop_price": 498,
        },
        path_token="test-secret",
    )
    assert result["decisions"][0]["status"] == "rejected"
    assert result["decisions"][0]["reason"].startswith("malformed_pine_metadata:")


def test_velez_pine_payload_carries_versioned_prop_metadata():
    pine = (Path(__file__).parents[1] / "tradingview" / "velez_core_alerts.pine").read_text(encoding="utf-8")

    for field in ("payload_version", "signal_id", "profile_key", "rules_version", "point_value"):
        assert f'\\"{field}\\"' in pine
    assert "str.format_time(time" in pine


def test_watchlist_allowlist_blocks_rogue_symbol_and_accepts_configured_symbol():
    config = webhook_config()
    config["scanner"] = {"symbols": ["NVDA"]}
    engine = TradingViewWebhookEngine(config)

    blocked = engine.handle_payload(
        {"mode": "signal", "symbol": "OKTA", "side": "buy", "play": "elephant_bar", "entry_price": 100, "stop_price": 99},
        path_token="test-secret",
    )
    allowed = engine.handle_payload(
        {"mode": "signal", "symbol": "NVDA", "side": "buy", "play": "elephant_bar", "entry_price": 100, "stop_price": 99},
        path_token="test-secret",
    )

    assert blocked["ok"] is False
    assert blocked["decisions"][0]["reason"] == "symbol_not_in_watchlist:OKTA"
    assert allowed["ok"] is True
    assert allowed["decisions"][0]["status"] == "proposed"


def test_vwap_readback_is_available_after_completed_strategy_bars():
    engine = TradingViewWebhookEngine(webhook_config(), broker=ScannerBroker())
    start = datetime(2026, 8, 3, 14, 30, tzinfo=timezone.utc)
    engine.strategy.on_bar("SPY", Bar(start, 100, 100, 100, 100, 1_000))
    engine.strategy.on_bar("SPY", Bar(start + timedelta(minutes=1), 101, 102, 101, 102, 1_000))

    state = engine.vwap_state_payload("SPY")

    assert state["ok"] is True
    assert state["status"] == "ready"
    assert state["vwap"]["session_vwap"] is not None
    assert state["vwap"]["primary_variant"] == "session"


def test_webhook_confluence_conflict_reduces_to_a_quarter_starter(monkeypatch):
    config = webhook_config()
    config["velez_strategy"] = {"webhook_confluence": {"enabled": True}}
    engine = TradingViewWebhookEngine(config)
    monkeypatch.setattr(
        "bot.webhook_server.score_webhook_confluence",
        lambda *_args, **_kwargs: {"action": "starter", "multiplier": 0.25, "reason": "higher_timeframe_opposed:60"},
    )

    decision = engine.handle_payload(
        {"mode": "signal", "symbol": "SPY", "side": "buy", "play": "elephant_bar", "entry_price": 500, "stop_price": 498, "timeframe": "15m"},
        path_token="test-secret",
    )["decisions"][0]

    assert decision["status"] == "proposed"
    assert decision["qty"] == 15
    assert decision["metadata"]["confluence"]["action"] == "starter"


def test_tradingview_webhook_rejects_bad_secret():
    config = {
        "risk": {"max_consecutive_losses": 3, "max_open_positions": 3, "max_daily_loss_pct": 0.02},
        "webhook": {"auth_required": True, "secret": "right-secret"},
    }
    engine = TradingViewWebhookEngine(config)

    result = engine.handle_payload({"mode": "signal", "symbol": "SPY"}, path_token="wrong")

    assert not result["ok"]
    assert result["decisions"][0]["reason"] == "invalid_webhook_secret"


def test_velez_lot_conviction_ladder_sizes_power_locations_and_caps_chased_setups():
    engine = TradingViewWebhookEngine(webhook_config())

    power = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
            "location": "location_3_near_200_sma",
            "body_mult": 2.5,
        },
        path_token="test-secret",
    )["decisions"][0]

    assert power["metadata"]["lot_plan"]["lots"] == 4
    assert power["metadata"]["lot_plan"]["effective_risk_budget"] == 500
    assert power["qty"] == 250

    capped = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
            "location": "location_3_near_200_sma",
            "body_mult": 2.5,
            "chased": True,
        },
        path_token="test-secret",
    )["decisions"][0]

    assert capped["metadata"]["lot_plan"]["lots"] == 2
    assert capped["metadata"]["lot_plan"]["effective_risk_budget"] == 250
    assert capped["qty"] == 125


def test_dashboard_state_tracks_recent_decisions_without_secrets():
    config = webhook_config()
    engine = TradingViewWebhookEngine(config)

    engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "sell",
            "play": "bear_180",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 502,
            "timestamp": "2026-01-01T14:30:00Z",
            "secret": "test-secret",
        }
    )

    state = engine.dashboard_state()
    serialized = json.dumps(state)

    assert state["recent_decisions"][0]["symbol"] == "SPY"
    assert state["recent_decisions"][0]["side"] == "sell"
    assert state["recent_decisions"][0]["stop_price"] == "502.00"
    assert state["guardrails"]["auth_required"] is True
    assert "test-secret" not in serialized


def test_open_risk_rejects_unprotected_positions_and_caps_aggregate_risk():
    config = webhook_config()
    config["risk"]["max_total_open_risk_pct"] = 0.02
    engine = TradingViewWebhookEngine(config)

    unprotected = engine._open_risk_snapshot(
        [{"symbol": "SPY", "qty": "10", "side": "long", "avg_entry_price": "500"}],
        [],
    )
    assert unprotected["unprotected_symbols"] == ["SPY"]

    protected = engine._open_risk_snapshot(
        [{"symbol": "SPY", "qty": "10", "side": "long", "avg_entry_price": "500"}],
        [{"symbol": "SPY", "type": "market", "order_class": "oto", "stop_loss": {"stop_price": "498"}}],
    )
    assert protected["unprotected_symbols"] == []
    assert protected["open_risk"] == 20
    assert engine._aggregate_open_risk_cap(100000) == 2000


def test_broker_fill_ledger_counts_completed_fifo_lots_only():
    engine = TradingViewWebhookEngine(webhook_config())
    ledger = engine._completed_fill_ledger([
        {"symbol": "SPY", "side": "buy", "qty": "10", "price": "100", "transaction_time": "2026-01-01T10:00:00Z"},
        {"symbol": "SPY", "side": "sell", "qty": "10", "price": "110", "transaction_time": "2026-01-01T11:00:00Z"},
        {"symbol": "QQQ", "side": "buy", "qty": "5", "price": "100", "transaction_time": "2026-01-01T12:00:00Z"},
    ])

    assert ledger["closed_lots"] == 1
    assert ledger["realized_pnl"] == 100
    assert ledger["win_rate"] == 1
    assert ledger["open_lots_excluded"] == 1


def test_dashboard_auth_protects_dashboard_and_api_when_enabled(monkeypatch):
    monkeypatch.setenv("VELEZ_DASHBOARD_AUTH_ENABLED", "true")
    monkeypatch.setenv("VELEZ_DASHBOARD_USERNAME", "desk")
    monkeypatch.setenv("VELEZ_DASHBOARD_PASSWORD", "secret-pass")

    client = TestClient(create_app(webhook_config()))

    assert client.get("/health").status_code == 200
    assert client.get("/dashboard").status_code == 401
    assert client.get("/api/dashboard/state").status_code == 401

    token = base64.b64encode(b"desk:secret-pass").decode("ascii")
    response = client.get("/api/dashboard/state", headers={"Authorization": f"Basic {token}"})

    assert response.status_code == 200
    assert response.json()["dashboard_version"] == "v6.40.4"


def test_dashboard_auth_can_stay_disabled_for_local_development(monkeypatch):
    monkeypatch.delenv("VELEZ_DASHBOARD_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("VELEZ_DASHBOARD_USERNAME", raising=False)
    monkeypatch.delenv("VELEZ_DASHBOARD_PASSWORD", raising=False)

    client = TestClient(create_app(webhook_config()))

    assert client.get("/api/dashboard/state").status_code == 200


def test_notification_test_endpoint_dispatches_configured_target(monkeypatch, tmp_path):
    notify_file = tmp_path / "notification-tests.jsonl"
    monkeypatch.setenv("VELEZ_NOTIFY_FILE", str(notify_file))

    client = TestClient(create_app(webhook_config()))
    response = client.post("/api/notifications/test", json={"channel": "all"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "file" in payload["targets"]
    assert "notification_test" in notify_file.read_text()


def test_vps_scanner_warms_without_trading_old_bars(monkeypatch):
    config = webhook_config()
    config["scanner"] = {
        "enabled": True,
        "auto_submit": False,
        "timeframe": "1Min",
        "history_bars": 260,
        "closed_bar_delay_seconds": 0,
        "session_filter_enabled": False,
    }
    engine = TradingViewWebhookEngine(config)
    base = datetime.now(timezone.utc) - timedelta(minutes=320)
    bars = [
        Bar(
            timestamp=base + timedelta(minutes=index),
            open=100 + index * 0.01,
            high=100.2 + index * 0.01,
            low=99.8 + index * 0.01,
            close=100.05 + index * 0.01,
            volume=1000,
        )
        for index in range(260)
    ]
    monkeypatch.setattr(engine, "_fetch_stock_bars", lambda symbol: bars)

    status = engine.scanner_scan_once()

    assert status["warmed_symbols"] == 1
    assert status["signals_found"] == 0
    assert engine.journal.latest_decisions(limit=1) == []
    assert engine.scanner_public_status()["enabled"] is True


def test_scanner_pauses_when_max_exposure_reached():
    config = webhook_config()
    config["scanner"] = {"enabled": True, "auto_submit": True}
    broker = ScannerBroker(
        positions=[
            {"symbol": "SPY", "qty": "1"},
            {"symbol": "QQQ", "qty": "1"},
        ],
        orders=[{"symbol": "IWM", "qty": "1", "status": "new"}],
    )
    engine = TradingViewWebhookEngine(config, broker=broker)

    status = engine.scanner_scan_once()

    assert status["mode"] == "paused"
    assert status["pause"]["paused"] is True
    assert status["pause"]["reason"] == "max_exposure_reached"
    assert status["exposure"]["active_exposure"] == 3
    assert status["signals_found"] == 0


def test_scanner_control_mode_can_be_changed_with_approval_token(monkeypatch):
    monkeypatch.setenv("VELEZ_APPROVAL_API_TOKEN", "approval-token")
    config = webhook_config()
    config["scanner"] = {"enabled": True, "auto_submit": True}
    engine = TradingViewWebhookEngine(config)

    changed = engine.set_scanner_control_mode("diagnostic", "approval-token")
    status = engine.scanner_scan_once()

    assert changed["ok"] is True
    assert changed["mode"] == "diagnostic"
    assert engine.scanner_public_status()["control_mode"] == "diagnostic"
    assert status["control_mode"] == "diagnostic"
    assert status["pause"]["paused"] is False


def test_scanner_manual_pause_skips_scan_with_approval_token(monkeypatch):
    monkeypatch.setenv("VELEZ_APPROVAL_API_TOKEN", "approval-token")
    config = webhook_config()
    config["scanner"] = {"enabled": True, "auto_submit": True}
    engine = TradingViewWebhookEngine(config)
    engine.set_scanner_control_mode("paused", "approval-token")

    status = engine.scanner_scan_once()

    assert status["mode"] == "paused"
    assert status["control_mode"] == "paused"
    assert status["pause"]["reason"] == "operator_paused"
    assert status["symbols_scanned"] == 0


def test_scanner_session_filter_records_quality_skip(monkeypatch):
    config = webhook_config()
    config["scanner"] = {
        "enabled": True,
        "auto_submit": False,
        "session_filter_enabled": True,
        "rth_start": "23:59",
        "rth_end": "23:59",
    }
    engine = TradingViewWebhookEngine(config)

    status = engine.scanner_scan_once()
    quality = engine.scanner_quality_payload()

    assert any(item.startswith("SPY:session:") for item in status["skipped"])
    assert quality["summary"]["skipped"] >= 1
    assert quality["entries"][0]["status"] == "skipped"


def test_scanner_quality_forward_replay_grades_signal(monkeypatch):
    config = webhook_config()
    config["scanner"] = {"enabled": True, "auto_submit": False, "quality_forward_bars": 5}
    engine = TradingViewWebhookEngine(config)
    signal_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    engine.journal.record_decision(
        {
            "timestamp": signal_time.isoformat(),
            "alert_ref": "scanner-quality-spy",
            "status": "diagnostic",
            "reason": "webhook_test_dry_run_no_order",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "qty": 10,
            "entry_price": 100,
            "stop_price": 99,
            "metadata": {"source_metadata": {"source": "vps_scanner", "timestamp": signal_time.isoformat(), "entry_price": 100, "stop_price": 99}},
        }
    )
    bars = [
        Bar(timestamp=signal_time + timedelta(minutes=1), open=100, high=100.5, low=99.8, close=100.3, volume=1000),
        Bar(timestamp=signal_time + timedelta(minutes=2), open=100.3, high=101.2, low=100.1, close=101.0, volume=1100),
    ]
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type="equity": bars)

    quality = engine.scanner_quality_payload()

    assert quality["summary"]["accepted"] == 1
    assert quality["summary"]["would_win"] == 1
    assert quality["entries"][0]["forward_outcome"]["outcome"] == "hit_1r"
    assert quality["entries"][0]["grade"] == "B"


def test_watchlist_quality_recommends_and_applies_disable(monkeypatch):
    monkeypatch.setenv("VELEZ_APPROVAL_API_TOKEN", "approval-token")
    config = webhook_config()
    config["symbols"] = [{"symbol": "SPY", "type": "equity", "contract_multiplier": 1, "session": "rth"}]
    config["scanner"] = {"enabled": True, "auto_submit": False, "quality_forward_bars": 5}
    engine = TradingViewWebhookEngine(config)
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    for index in range(3):
        ts = base + timedelta(minutes=index)
        engine.journal.record_decision(
            {
                "timestamp": ts.isoformat(),
                "alert_ref": f"scanner-quality-spy-stop-{index}",
                "status": "diagnostic",
                "reason": "webhook_test_dry_run_no_order",
                "symbol": "SPY",
                "side": "buy",
                "play": "elephant_bar",
                "qty": 10,
                "entry_price": 100,
                "stop_price": 99,
                "metadata": {"source_metadata": {"source": "vps_scanner", "timestamp": ts.isoformat(), "entry_price": 100, "stop_price": 99}},
            }
        )
    bars = [
        Bar(timestamp=base + timedelta(minutes=4), open=100, high=100.2, low=98.8, close=99.0, volume=1000),
    ]
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type="equity": bars)

    quality = engine.watchlist_quality_payload()
    applied = engine.apply_watchlist_quality_action("SPY", "disable", "approval-token")

    assert quality["recommendations"][0]["state"] == "disable_candidate"
    assert applied["ok"] is True
    assert applied["watchlist_quality"]["symbols"][0]["enabled"] is False
    assert all(item["symbol"] != "SPY" for item in engine.watchlist_symbols())


def test_scanner_quality_report_writes_notification(monkeypatch, tmp_path):
    notify_file = tmp_path / "quality.jsonl"
    monkeypatch.setenv("VELEZ_APPROVAL_API_TOKEN", "approval-token")
    monkeypatch.setenv("VELEZ_NOTIFY_FILE", str(notify_file))
    engine = TradingViewWebhookEngine(webhook_config())

    result = engine.send_scanner_quality_report("approval-token")

    assert result["ok"] is True
    content = notify_file.read_text()
    assert "scanner_quality_report" in content


def test_scanner_cancel_stale_orders_only_removes_orphan_entries(monkeypatch):
    monkeypatch.setenv("VELEZ_APPROVAL_API_TOKEN", "approval-token")
    config = webhook_config()
    config["scanner"] = {"enabled": True, "auto_submit": True}
    broker = ScannerBroker(
        positions=[{"symbol": "SPY", "qty": "1"}],
        orders=[
            {"id": "stale-entry", "client_order_id": "velez-stale", "symbol": "IWM", "side": "buy", "type": "limit", "qty": "1", "status": "new"},
            {"id": "protective-stop", "client_order_id": "velez-stop", "symbol": "SPY", "side": "sell", "type": "stop", "qty": "1", "status": "new"},
            {"id": "manual-order", "client_order_id": "manual-1", "symbol": "QQQ", "side": "buy", "type": "limit", "qty": "1", "status": "new"},
        ],
    )
    engine = TradingViewWebhookEngine(config, broker=broker)

    result = engine.cancel_stale_scanner_orders("approval-token")

    assert result["ok"] is True
    assert result["canceled_count"] == 1
    assert broker.canceled == ["stale-entry"]
    assert [order["id"] for order in broker.orders] == ["protective-stop", "manual-order"]


def test_scanner_exposure_pause_and_resume_notifications(monkeypatch, tmp_path):
    notify_file = tmp_path / "scanner-notifications.jsonl"
    monkeypatch.setenv("VELEZ_NOTIFY_FILE", str(notify_file))
    config = webhook_config()
    config["scanner"] = {"enabled": True, "auto_submit": True}
    broker = ScannerBroker(
        positions=[
            {"symbol": "SPY", "qty": "1"},
            {"symbol": "QQQ", "qty": "1"},
            {"symbol": "IWM", "qty": "1"},
        ]
    )
    engine = TradingViewWebhookEngine(config, broker=broker)

    engine.scanner_scan_once()
    broker.positions = [{"symbol": "SPY", "qty": "1"}]
    engine.scanner_scan_once()

    content = notify_file.read_text()
    assert "scanner_exposure_state" in content
    assert "paused" in content
    assert "active" in content


def test_scanner_symbol_cooldown_suppresses_repeated_rejected_signals(monkeypatch):
    config = webhook_config()
    config["scanner"] = {
        "enabled": True,
        "auto_submit": False,
        "symbol_cooldown_seconds": 900,
        "closed_bar_delay_seconds": 0,
        "session_filter_enabled": False,
    }
    engine = TradingViewWebhookEngine(config)
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    bars = [
        Bar(timestamp=base + timedelta(minutes=1), open=100, high=101, low=99, close=100.5, volume=1000),
        Bar(timestamp=base + timedelta(minutes=2), open=100.5, high=101.5, low=100, close=101, volume=1100),
    ]
    engine.scanner_last_bar["SPY"] = base

    class RejectingStrategy:
        def on_bar(self, symbol, bar):
            return [
                Signal(
                    symbol=symbol,
                    side=Side.BUY,
                    reason="elephant_bar",
                    metadata={"play": "elephant_bar", "entry_price": bar.close, "stop_price": bar.close - 1},
                )
            ]

    engine.scanner_strategy = RejectingStrategy()
    calls = {"count": 0}

    def fake_fetch(symbol):
        calls["count"] += 1
        return bars[:1] if calls["count"] == 1 else bars

    monkeypatch.setattr(engine, "_fetch_stock_bars", fake_fetch)
    monkeypatch.setattr(
        engine,
        "_build_order_decision",
        lambda signal, alert_id, dry_run=False: WebhookDecision(
            status="rejected",
            reason="scanner_test_reject",
            symbol=signal.symbol,
            side=signal.side.value,
            play=signal.reason,
        ),
    )

    first = engine.scanner_scan_once()
    second = engine.scanner_scan_once()

    assert first["signals_found"] == 1
    assert second["signals_found"] == 0
    assert second["mode"] == "cooldown"
    assert any("SPY:cooldown:symbol_cooldown" == item for item in second["skipped"])
    assert len(engine.journal.latest_decisions(limit=10)) == 1


def test_polygon_futures_adapter_maps_contracts_and_bars(monkeypatch):
    config = webhook_config()
    config["scanner"] = {
        "enabled": True,
        "auto_submit": False,
        "timeframe": "1Min",
        "futures_provider": "polygon",
        "futures_contracts": {"ES": "ESM6"},
    }
    config["symbols"] = [{"symbol": "ES", "type": "future", "contract_multiplier": 50}]
    monkeypatch.setenv("POLYGON_API_KEY", "polygon-test-key")
    engine = TradingViewWebhookEngine(config)

    calls = []

    def fake_polygon(path, *, params):
        calls.append((path, params))
        return {
            "results": [
                {
                    "window_start": 1_756_000_000_000_000_000,
                    "open": 5000,
                    "high": 5005,
                    "low": 4998,
                    "close": 5002,
                    "volume": 12,
                }
            ]
        }

    monkeypatch.setattr(engine, "_polygon_request", fake_polygon)

    bars = engine._fetch_scanner_bars(symbol="ES", asset_type="future")

    assert calls[0][0] == "/futures/vX/aggs/ESM6"
    assert calls[0][1]["resolution"] == "1min"
    assert bars[0].close == 5002
    assert bars[0].volume == 12

def test_watch_only_is_a_hard_execution_gate(monkeypatch):
    config = webhook_config()
    config["webhook"]["execute_orders"] = True
    monkeypatch.setenv("VELEZ_EXECUTE_ORDERS", "true")
    monkeypatch.setenv("VELEZ_WATCH_ONLY", "true")
    engine = TradingViewWebhookEngine(config, broker=ScannerBroker())

    assert engine._watch_only() is True
    assert engine._execute_orders() is False
    assert engine.risk_status_payload()["watch_only"] is True


def test_watch_only_blocks_stale_order_cancellation(monkeypatch):
    broker = ScannerBroker(
        orders=[
            {
                "id": "stale-1",
                "symbol": "SPY",
                "type": "limit",
                "status": "new",
                "client_order_id": "velez-scanner-stale-1",
            }
        ]
    )
    monkeypatch.setenv("VELEZ_WATCH_ONLY", "true")
    engine = TradingViewWebhookEngine(webhook_config(), broker=broker)

    result = engine.cancel_stale_scanner_orders("test-secret")

    assert result == {"ok": False, "reason": "watch_only_enabled"}
    assert broker.canceled == []


def test_watch_only_blocks_every_engine_broker_mutation_path(monkeypatch):
    broker = ScannerBroker()
    config = webhook_config()
    config["webhook"]["execute_orders"] = True
    monkeypatch.setenv("VELEZ_EXECUTE_ORDERS", "true")
    monkeypatch.setenv("VELEZ_LIFECYCLE_AUTO_EXECUTE", "true")
    monkeypatch.setenv("VELEZ_WATCH_ONLY", "true")
    engine = TradingViewWebhookEngine(config, broker=broker)

    assert engine.approve_pending_order("missing", "APPROVE", "test-secret")["reason"] == "execution_not_armed"
    assert engine.repair_lifecycle_stop("SPY", "test-secret")["reason"] == "watch_only_enabled"
    assert engine.reduce_lifecycle_position("SPY", 0.5, "test-secret")["reason"] == "watch_only_enabled"
    assert engine.move_eligible_stops_to_breakeven("test-secret")["reason"] == "watch_only_enabled"
    assert engine.cancel_stale_scanner_orders("test-secret")["reason"] == "watch_only_enabled"
    assert engine._auto_lifecycle_actions(positions=[], open_orders=[], guardrails=[]) == []
    assert broker.submitted == []
    assert broker.canceled == []


def test_watch_only_legacy_alias_remains_supported(monkeypatch):
    monkeypatch.delenv("VELEZ_WATCH_ONLY", raising=False)
    monkeypatch.setenv("WATCH_ONLY", "true")
    engine = TradingViewWebhookEngine(webhook_config())

    assert engine._watch_only() is True


def test_rejected_symbol_records_safe_request_provenance(monkeypatch):
    monkeypatch.setenv("VELEZ_INPUT_AUDIT_SALT", "test-audit-salt")
    config = webhook_config()
    config["scanner"] = {"symbols": ["NVDA"]}
    client = TestClient(create_app(config))

    response = client.post(
        "/webhook/tradingview/test-secret",
        json={
            "mode": "signal",
            "symbol": "XRPUSD",
            "side": "buy",
            "play": "elephant_bar",
            "entry_price": 1,
            "stop_price": 0.9,
        },
        headers={"User-Agent": "TradingView-Webhook-Test/1.0", "X-Request-ID": "xrp-audit-1"},
    )

    assert response.status_code == 400
    source = response.json()["detail"]["decisions"][0]["metadata"]["input_source"]
    assert source["request_id"] == "xrp-audit-1"
    assert source["route"] == "/webhook/tradingview/{token}"
    assert source["user_agent"] == "TradingView-Webhook-Test/1.0"
    assert len(source["client_fingerprint"]) == 16
    assert "test-secret" not in json.dumps(source)
