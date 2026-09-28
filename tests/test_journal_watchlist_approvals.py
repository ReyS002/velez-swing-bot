from types import SimpleNamespace

from bot.webhook_server import TradingViewWebhookEngine


class FakeBroker:
    def __init__(self):
        self.config = SimpleNamespace(base_url="https://paper-api.alpaca.markets")
        self.submitted = []

    def is_configured(self):
        return True

    def validate_connection(self):
        return {"ok": True, "account_status": "ACTIVE", "paper": True}

    def get_account(self):
        return {"equity": "100000", "portfolio_value": "100000"}

    def get_positions_raw(self):
        return []

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
    assert health["dashboard_version"] == "v6.6"
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
