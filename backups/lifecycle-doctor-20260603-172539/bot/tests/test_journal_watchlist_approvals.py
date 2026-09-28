from types import SimpleNamespace

from bot.webhook_server import TradingViewWebhookEngine


class FakeBroker:
    def __init__(self, positions=None, orders=None, activities=None):
        self.config = SimpleNamespace(base_url="https://paper-api.alpaca.markets")
        self.submitted = []
        self.canceled = []
        self.positions = positions or []
        self.orders = orders or []
        self.activities = activities or []

    def is_configured(self):
        return True

    def validate_connection(self):
        return {"ok": True, "account_status": "ACTIVE", "paper": True}

    def get_account(self):
        return {"equity": "100000", "portfolio_value": "100000"}

    def get_positions_raw(self):
        return self.positions

    def get_orders_raw(self, **kwargs):
        return self.orders

    def get_activities_raw(self, **kwargs):
        return self.activities

    def build_entry_payload(
        self,
        *,
        symbol,
        side,
        qty,
        order_type,
        entry_price,
        stop_price,
        client_order_id,
        time_in_force,
        take_profit_price=None,
    ):
        payload = {
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "type": order_type,
            "client_order_id": client_order_id,
            "time_in_force": time_in_force,
            "stop_loss": {"stop_price": f"{float(stop_price):.2f}"},
        }
        if order_type == "limit":
            payload["limit_price"] = f"{float(entry_price):.2f}"
        if take_profit_price:
            payload["take_profit"] = {"limit_price": f"{float(take_profit_price):.2f}"}
        return payload

    def submit_order_payload(self, payload):
        self.submitted.append(payload)
        return {"id": "paper-order-1", "status": "accepted", **payload}

    def cancel_order(self, order_id):
        self.canceled.append(order_id)
        self.orders = [order for order in self.orders if order.get("id") != order_id]
        return {}


def config():
    return {
        "portfolio": {"initial_cash": 100000},
        "risk": {
            "risk_per_trade": 0.005,
            "max_dollar_risk_per_trade": 1000,
            "max_daily_loss_pct": 0.02,
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
        "symbols": [{"symbol": "SPY", "type": "equity", "contract_multiplier": 1, "session": "rth"}],
        "velez_strategy": {},
    }


def test_proposed_order_is_persisted_and_can_be_approved_with_token(monkeypatch):
    monkeypatch.setenv("VELEZ_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("VELEZ_APPROVAL_API_TOKEN", "approval-token")
    broker = FakeBroker()
    engine = TradingViewWebhookEngine(config(), broker=broker)

    result = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
        },
        path_token="test-secret",
    )

    assert result["ok"]
    assert engine.journal.latest_decisions(1)[0]["status"] == "proposed"
    pending = engine.pending_approvals()["pending"]
    assert len(pending) == 1
    assert pending[0]["approval_phrase"].startswith("APPROVE PAPER ORDER")

    engine.webhook_config["execute_orders"] = True
    monkeypatch.setenv("VELEZ_EXECUTE_ORDERS", "true")
    approved = engine.approve_pending_order(pending[0]["id"], pending[0]["approval_phrase"], "approval-token")

    assert approved["ok"] is True
    assert approved["status"] == "submitted"
    assert broker.submitted[0]["symbol"] == "SPY"
    assert engine.pending_approvals()["pending"] == []


def test_watchlist_updates_and_daily_brief_reads_pending_order():
    engine = TradingViewWebhookEngine(config(), broker=FakeBroker())

    add = engine.add_watchlist_symbol({"symbol": "QQQ", "type": "equity"})
    assert add["ok"] is True
    assert any(item["symbol"] == "QQQ" for item in engine.watchlist_symbols())

    engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "sell",
            "play": "bear_180",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 502,
        },
        path_token="test-secret",
    )

    brief = engine.daily_brief_payload()
    assert "QQQ" in ", ".join(item["symbol"] for item in brief["watchlist"])
    assert brief["pending_approvals"]
    assert "paper order approval is waiting" in brief["voice_summary"]

    removed = engine.remove_watchlist_symbol("QQQ")
    assert removed["ok"] is True
    assert all(item["symbol"] != "QQQ" for item in engine.watchlist_symbols())


def test_require_order_approval_holds_armed_execution(monkeypatch):
    monkeypatch.setenv("VELEZ_EXECUTE_ORDERS", "true")
    monkeypatch.setenv("VELEZ_REQUIRE_ORDER_APPROVAL", "true")
    cfg = config()
    cfg["webhook"]["execute_orders"] = True
    broker = FakeBroker()
    engine = TradingViewWebhookEngine(cfg, broker=broker)

    result = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
        },
        path_token="test-secret",
    )

    assert result["ok"] is True
    assert result["decisions"][0]["status"] == "proposed"
    assert result["decisions"][0]["reason"] == "approval_required"
    assert broker.submitted == []
    assert len(engine.pending_approvals()["pending"]) == 1


def test_color_change_add_uses_half_current_position_size(monkeypatch):
    monkeypatch.setenv("VELEZ_EXECUTE_ORDERS", "true")
    cfg = config()
    cfg["webhook"]["execute_orders"] = True
    broker = FakeBroker(
        positions=[
            {
                "symbol": "SPY",
                "qty": "500",
                "side": "long",
                "avg_entry_price": "100.00",
                "current_price": "103.00",
            }
        ]
    )
    engine = TradingViewWebhookEngine(cfg, broker=broker)

    result = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "color_change_add",
            "order_type": "market",
            "entry_price": 103,
            "stop_price": 100.5,
            "scale_action": "add_to_winner",
            "add_fraction": 0.5,
            "requires_existing_winner": True,
            "mandatory_add": True,
        },
        path_token="test-secret",
    )

    assert result["ok"] is True
    decision = result["decisions"][0]
    assert decision["status"] == "submitted"
    assert decision["qty"] == 250
    assert broker.submitted[0]["qty"] == "250"


def test_research_mode_returns_fallback_and_saves_note(monkeypatch):
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    engine = TradingViewWebhookEngine(config(), broker=FakeBroker())

    result = engine.winston_research("SPY prep")

    assert result["ok"] is True
    assert result["intent"] == "research"
    assert result["research_used"] is False
    assert engine.journal.latest_research(1)[0]["topic"] == "SPY prep"


def test_v61_journal_health_and_replay_payloads():
    engine = TradingViewWebhookEngine(config(), broker=FakeBroker())
    engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
        },
        path_token="test-secret",
    )

    journal = engine.journal_payload()
    assert journal["ok"] is True
    assert journal["summary"]["entries"] == 1
    assert journal["entries"][0]["grade"] in {"A", "B", "C", "D"}
    assert journal["entries"][0]["readback"]
    assert journal["entries"][0]["chart_context"]["url"].startswith("https://www.tradingview.com/chart/")

    health = engine.bot_health()
    assert health["ok"] is True
    assert health["dashboard_version"] == "v6.21"
    assert any(item["name"] == "TradingView webhook" for item in health["components"])

    replay = engine.replay_payload({"symbol": "SPY", "scenario": "bull_elephant"})
    assert replay["ok"] is True
    assert replay["bars_loaded"] > 200
    assert replay["signals_found"] >= 1
    assert any(item["play"] == "elephant_bar" for item in replay["events"])
    assert engine.journal.latest_replays(1)[0]["signals_found"] >= 1


def test_winston_fast_router_returns_music_actions():
    engine = TradingViewWebhookEngine(config(), broker=FakeBroker())

    play = engine.winston_reply("Winston play Sade on the iPod")
    assert play["ok"] is True
    assert play["provider"] == "winston_fast_command_router_v1"
    assert play["intent"] == "music_control"
    assert play["actions"][0]["type"] == "music.play_search"
    assert play["actions"][0]["query"] == "Sade"
    assert play["llm_used"] is False

    pause = engine.winston_reply("pause music")
    assert pause["actions"][0]["type"] == "music.pause"

    nav = engine.winston_reply("open the music panel")
    assert nav["intent"] == "desk_navigation"
    assert nav["actions"][0] == {"type": "panel.open", "panel": "music"}


def test_v66_daily_review_and_room_router():
    engine = TradingViewWebhookEngine(config(), broker=FakeBroker())
    engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
        },
        path_token="test-secret",
    )

    review = engine.daily_review_payload()
    assert review["ok"] is True
    assert review["counts"]["decisions"] >= 1
    assert review["lesson"]

    mission = engine.winston_reply("open the daily mission")
    assert mission["intent"] == "desk_navigation"
    assert mission["actions"][0] == {"type": "panel.open", "panel": "mission"}

    inbox = engine.winston_reply("show approval inbox")
    assert inbox["actions"][0] == {"type": "panel.open", "panel": "safe"}

    after_action = engine.winston_reply("open after action review")
    assert after_action["actions"][0] == {"type": "panel.open", "panel": "notes"}

    bull_report = engine.winston_reply("open bull report")
    assert bull_report["actions"][0] == {"type": "panel.open", "panel": "notes"}


def test_v616_coverage_webhook_test_risk_toggle_and_review(monkeypatch):
    monkeypatch.setenv("VELEZ_APPROVAL_API_TOKEN", "approval-token")
    engine = TradingViewWebhookEngine(config(), broker=FakeBroker())

    coverage = engine.alert_coverage_payload()
    assert coverage["ok"] is True
    assert coverage["summary"]["never"] >= 1

    test = engine.webhook_test_payload({"approval_token": "approval-token", "symbol": "SPY"})
    assert test["ok"] is True
    assert test["dry_run"] is True
    assert test["decisions"][0]["status"] == "diagnostic"
    assert engine.pending_approvals()["pending"] == []

    coverage_after = engine.alert_coverage_payload()
    assert coverage_after["summary"]["healthy"] >= 1

    review = engine.trade_review_payload(engine.journal.latest_decisions(1)[0]["alert_ref"])
    assert review["ok"] is True
    assert review["rule_checks"]
    assert review["replay_scenario"]

    risk = engine.set_order_approval_required(True, "approval-token")
    assert risk["ok"] is True
    assert risk["approval_required"] is True
    assert engine._requires_order_approval() is True

    morning = engine.winston_morning_call_payload()
    assert morning["ok"] is True
    assert "Trading Bull Desk is online" in morning["summary"]

    hardening = engine.vps_hardening_payload()
    assert hardening["ok"] is True
    assert hardening["helpers"]


def test_v618_close_report_confidence_receipts_risk_replay_and_latency(monkeypatch):
    monkeypatch.setenv("VELEZ_APPROVAL_API_TOKEN", "approval-token")
    engine = TradingViewWebhookEngine(config(), broker=FakeBroker())

    result = engine.webhook_test_payload({"approval_token": "approval-token", "symbol": "SPY"})
    assert result["ok"] is True

    entry = engine.journal_payload()["entries"][0]
    assert entry["confidence_receipt"]["score"] > 0
    assert entry["confidence_receipt"]["checks"]

    coverage = engine.alert_coverage_payload()
    assert coverage["summary"]["coverage_score"] >= 0
    assert coverage["rows"][0]["checklist"]

    close = engine.daily_close_report_payload()
    assert close["ok"] is True
    assert close["sections"]["action_items"]

    risk_replay = engine.risk_replay_payload({"symbol": "SPY", "scenario": "bull_elephant"})
    assert risk_replay["ok"] is True
    assert risk_replay["risk_replay"]["variants"]
    assert "never submits" in risk_replay["risk_replay"]["guardrail"]

    latency = engine.latency_payload()
    assert latency["ok"] is True
    assert latency["checks"]
    assert latency["total_latency_ms"] >= 0


def test_v619_lifecycle_reconciles_positions_orders_outcomes_and_winston_readback(monkeypatch):
    monkeypatch.setenv("VELEZ_AUTO_STAGE_PROPOSED_ORDERS", "false")
    broker = FakeBroker(
        positions=[
            {
                "symbol": "SPY",
                "qty": "100",
                "side": "long",
                "avg_entry_price": "500.00",
                "current_price": "502.50",
                "market_value": "50250",
                "unrealized_pl": "250.00",
                "unrealized_plpc": "0.005",
            }
        ],
        orders=[
            {
                "id": "stop-1",
                "client_order_id": "velez-stop-1",
                "symbol": "SPY",
                "side": "sell",
                "type": "stop",
                "status": "accepted",
                "qty": "100",
                "stop_price": "498.00",
                "submitted_at": "2026-01-01T15:00:00Z",
            }
        ],
        activities=[
            {
                "id": "fill-1",
                "activity_type": "FILL",
                "transaction_time": "2026-01-01T14:30:00Z",
                "symbol": "SPY",
                "side": "buy",
                "qty": "100",
                "price": "500.00",
                "order_id": "entry-1",
                "order_status": "filled",
            }
        ],
    )
    engine = TradingViewWebhookEngine(config(), broker=broker)
    engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
            "location": "at_20_sma",
        },
        path_token="test-secret",
    )

    lifecycle = engine.lifecycle_payload()

    assert lifecycle["ok"] is True
    assert lifecycle["summary"]["open_positions"] == 1
    assert lifecycle["summary"]["open_orders"] == 1
    assert lifecycle["positions"][0]["current_r_multiple"] == 1.25
    assert lifecycle["positions"][0]["stop_source"] == "broker_open_order"
    assert lifecycle["positions"][0]["linked_alert_ref"]
    assert lifecycle["guardrails"] == []
    assert engine.journal.latest_lifecycle_snapshot()["summary"]["open_positions"] == 1
    assert any(item["status"] == "one_r_reached" for item in engine.lifecycle_outcomes_payload()["outcomes"])

    readback = engine.winston_reply("what are my active positions and stops?")
    assert readback["intent"] == "trade_lifecycle"
    assert "SPY" in readback["reply"]
    assert "1.25R" in readback["reply"]


def test_lifecycle_breakeven_action_replaces_due_stop(monkeypatch):
    monkeypatch.setenv("VELEZ_APPROVAL_API_TOKEN", "approval-token")
    broker = FakeBroker(
        positions=[
            {
                "symbol": "SPY",
                "qty": "100",
                "side": "long",
                "avg_entry_price": "500.00",
                "current_price": "503.00",
                "unrealized_pl": "300.00",
            }
        ],
        orders=[
            {
                "id": "stop-1",
                "client_order_id": "velez-stop-1",
                "symbol": "SPY",
                "side": "sell",
                "type": "stop",
                "status": "new",
                "qty": "100",
                "stop_price": "498.00",
            }
        ],
    )
    engine = TradingViewWebhookEngine(config(), broker=broker)

    result = engine.move_eligible_stops_to_breakeven("approval-token")

    assert result["ok"] is True
    assert result["moved_count"] == 1
    assert broker.canceled == ["stop-1"]
    assert broker.submitted[-1]["symbol"] == "SPY"
    assert broker.submitted[-1]["side"] == "sell"
    assert broker.submitted[-1]["type"] == "stop"
    assert broker.submitted[-1]["stop_price"] == "500.00"


def test_lifecycle_partial_plan_and_needs_action_summary():
    broker = FakeBroker(
        positions=[
            {
                "symbol": "SPY",
                "qty": "100",
                "side": "long",
                "avg_entry_price": "500.00",
                "current_price": "502.50",
                "unrealized_pl": "250.00",
            }
        ],
        orders=[
            {
                "id": "stop-1",
                "symbol": "SPY",
                "side": "sell",
                "type": "stop",
                "status": "new",
                "qty": "100",
                "stop_price": "498.00",
            }
        ],
    )
    engine = TradingViewWebhookEngine(config(), broker=broker)

    lifecycle = engine.lifecycle_payload()
    plan = engine.lifecycle_partial_plan()

    assert lifecycle["summary"]["needs_action"]["count"] >= 2
    assert any(item["action"] == "move_stop_to_breakeven" for item in lifecycle["summary"]["needs_action"]["items"])
    assert plan["plans"][0]["recommendation"] == "25%-50%"
    assert plan["plans"][0]["options"][1]["qty"] == 50
    assert "does not submit" in plan["note"]


def test_lifecycle_threshold_notifications_write_file(monkeypatch, tmp_path):
    notify_file = tmp_path / "thresholds.jsonl"
    monkeypatch.setenv("VELEZ_NOTIFY_FILE", str(notify_file))
    broker = FakeBroker(
        positions=[
            {
                "symbol": "SPY",
                "qty": "100",
                "side": "long",
                "avg_entry_price": "500.00",
                "current_price": "502.50",
                "unrealized_pl": "250.00",
            }
        ],
        orders=[
            {
                "id": "stop-1",
                "symbol": "SPY",
                "side": "sell",
                "type": "stop",
                "status": "new",
                "qty": "100",
                "stop_price": "498.00",
            }
        ],
    )
    engine = TradingViewWebhookEngine(config(), broker=broker)

    engine.lifecycle_payload()
    engine.lifecycle_payload()

    content = notify_file.read_text()
    assert content.count("lifecycle_threshold") == 1
    assert "1R" in content


def test_v619_lifecycle_flags_orphan_position_without_stop():
    broker = FakeBroker(
        positions=[
            {
                "symbol": "QQQ",
                "qty": "50",
                "side": "long",
                "avg_entry_price": "400.00",
                "current_price": "399.00",
                "unrealized_pl": "-50.00",
            }
        ]
    )
    engine = TradingViewWebhookEngine(config(), broker=broker)

    lifecycle = engine.lifecycle_payload()
    names = {item["name"] for item in lifecycle["guardrails"]}

    assert "orphan_position" in names
    assert "missing_stop" in names


def test_lifecycle_does_not_link_rejected_decision_to_open_position():
    broker = FakeBroker(
        positions=[
            {
                "symbol": "SPY",
                "qty": "10",
                "side": "long",
                "avg_entry_price": "500.00",
                "current_price": "501.00",
                "unrealized_pl": "10.00",
            }
        ],
        orders=[
            {
                "id": "stop-1",
                "symbol": "SPY",
                "side": "sell",
                "type": "stop",
                "status": "accepted",
                "qty": "10",
                "stop_price": "498.00",
            }
        ],
    )
    engine = TradingViewWebhookEngine(config(), broker=broker)
    engine.journal.record_decision(
        {
            "timestamp": "2026-01-01T15:00:00+00:00",
            "alert_ref": "rejected-spy",
            "status": "rejected",
            "reason": "max_open_positions",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "qty": 0,
            "entry_price": 500,
            "stop_price": 498,
        }
    )

    lifecycle = engine.lifecycle_payload()

    assert lifecycle["positions"][0]["linked_alert_ref"] is None
    assert any(item["name"] == "orphan_position" and item["symbol"] == "SPY" for item in lifecycle["guardrails"])


def test_order_guard_counts_open_order_exposure_before_submit(monkeypatch):
    monkeypatch.setenv("VELEZ_EXECUTE_ORDERS", "true")
    monkeypatch.setenv("VELEZ_REQUIRE_ORDER_APPROVAL", "false")
    cfg = config()
    cfg["webhook"]["execute_orders"] = True
    broker = FakeBroker(
        positions=[
            {"symbol": "SPY", "qty": "10", "side": "long"},
            {"symbol": "QQQ", "qty": "5", "side": "long"},
        ],
        orders=[
            {
                "id": "pending-entry",
                "symbol": "IWM",
                "side": "buy",
                "type": "limit",
                "status": "new",
                "qty": "10",
                "limit_price": "200.00",
            }
        ],
    )
    engine = TradingViewWebhookEngine(cfg, broker=broker)

    result = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "NVDA",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 220,
            "stop_price": 218,
            "location": "at_20_sma",
        },
        path_token="test-secret",
    )

    assert result["ok"] is False
    assert result["decisions"][0]["status"] == "rejected"
    assert result["decisions"][0]["reason"] == "max_open_positions"
    assert broker.submitted == []


def test_lifecycle_guardrails_send_configured_notification(monkeypatch):
    monkeypatch.setenv("VELEZ_NOTIFY_WEBHOOK_URL", "https://hooks.example/trading-bull")
    monkeypatch.setenv("VELEZ_NOTIFY_COOLDOWN_SECONDS", "3600")
    posts = []

    class FakeResponse:
        status_code = 200

    def fake_post(url, json=None, timeout=None, headers=None):
        posts.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)
    cfg = config()
    cfg["risk"]["max_open_positions"] = 1
    broker = FakeBroker(
        positions=[
            {"symbol": "SPY", "qty": "10", "side": "long", "avg_entry_price": "500", "current_price": "499"},
            {"symbol": "QQQ", "qty": "5", "side": "long", "avg_entry_price": "450", "current_price": "448"},
        ]
    )
    engine = TradingViewWebhookEngine(cfg, broker=broker)

    first = engine.lifecycle_payload()
    second = engine.lifecycle_payload()

    assert first["summary"]["guardrails"] >= 3
    assert second["summary"]["guardrails"] >= 3
    assert len(posts) == 1
    assert posts[0]["url"] == "https://hooks.example/trading-bull"
    assert posts[0]["json"]["kind"] == "lifecycle_guardrails"
    assert posts[0]["json"]["severity"] == "critical"
    assert "max_positions_exceeded" in posts[0]["json"]["detail"]


def test_lifecycle_guardrails_can_write_notification_file(monkeypatch, tmp_path):
    notify_file = tmp_path / "notifications.jsonl"
    monkeypatch.setenv("VELEZ_NOTIFY_FILE", str(notify_file))
    cfg = config()
    cfg["risk"]["max_open_positions"] = 1
    broker = FakeBroker(
        positions=[
            {"symbol": "SPY", "qty": "10", "side": "long", "avg_entry_price": "500", "current_price": "499"},
            {"symbol": "QQQ", "qty": "5", "side": "long", "avg_entry_price": "450", "current_price": "448"},
        ]
    )
    engine = TradingViewWebhookEngine(cfg, broker=broker)

    lifecycle = engine.lifecycle_payload()

    assert lifecycle["summary"]["guardrails"] >= 3
    content = notify_file.read_text()
    assert "lifecycle_guardrails" in content
    assert "max_positions_exceeded" in content
