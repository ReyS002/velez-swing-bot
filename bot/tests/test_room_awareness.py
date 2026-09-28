import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from bot.brokers.alpaca import AlpacaPaperBroker, AlpacaPaperConfig
from bot.room_awareness import ROOMS, RoomAwarenessService
from bot.webhook_server import TradingViewWebhookEngine, create_app


def config():
    return {
        "portfolio": {"initial_cash": 100000},
        "risk": {
            "risk_per_trade": 0.005,
            "max_dollar_risk_per_trade": 1000,
            "max_daily_loss_pct": 0.02,
            "max_open_positions": 3,
            "max_stop_pct": 0.1,
        },
        "webhook": {"auth_required": False, "execute_orders": False, "paper_only": True},
        "symbols": [{"symbol": "SPY", "contract_multiplier": 1}],
        "bullpilot_strategy": {},
    }


class FakeRoomEngine:
    def __init__(self):
        today = datetime.now(ZoneInfo("America/New_York")).date()
        tomorrow = today + timedelta(days=1)
        self.today = today.isoformat()
        self.tomorrow = tomorrow.isoformat()

    def dashboard_state(self):
        return {
            "execution_armed": False,
            "paper_endpoint": True,
            "broker": {
                "ok": True,
                "account_status": "ACTIVE",
                "paper": True,
                "account_number": "PA123456789",
                "account_number_tail": "6789",
            },
            "summary": {"open_positions": 1, "unrealized_pl": 125.5},
            "symbols": [{"symbol": "SPY"}, {"symbol": "QQQ"}],
            "recent_decisions": [
                {"timestamp": "2026-07-30T14:00:00Z", "symbol": "SPY", "play": "elephant_bar", "status": "qualified"}
            ],
            "scanner": {"enabled": True, "running": True, "control_mode": "advisory", "signals_found": 1},
            "alert_coverage": {"summary": {"ready": 2}},
            "risk": {
                "max_dollar_risk_per_trade": 1000,
                "max_daily_loss_pct": 0.02,
                "max_open_positions": 3,
            },
            "guardrails": {"auth_required": True, "api_key": "SHOULD-NOT-LEAK"},
            "pending_approvals": [{"id": "approval-1", "symbol": "SPY", "status": "pending", "token": "NOPE"}],
            "apple_music": {"configured": True, "key_id_tail": "ABCD", "missing": []},
            "winston": {
                "brain": {"provider": "xai", "model": "grok"},
                "voice": {"provider": "xai", "voice": "leo", "voice_locked": True, "available": True},
                "guardrails": {"read_only": True},
            },
        }

    def calendar_month(self):
        current = {
            "date": self.today,
            "time": "08:30 ET",
            "title": "Employment Situation",
            "source": "BLS",
            "importance": "high",
            "kind": "macro",
        }
        upcoming = {
            "date": self.tomorrow,
            "time": "16:00 ET",
            "title": "SPY earnings watch",
            "source": "Alpha Vantage",
            "importance": "high",
            "kind": "earnings",
            "symbol": "SPY",
        }
        return {
            "timestamp": "2026-07-30T12:00:00Z",
            "range": {"start": self.today, "end": self.tomorrow},
            "session": {"status": "open", "label": "Regular session"},
            "sessions": [
                {"date": self.today, "open": "09:30", "close": "16:00", "label": "Regular session"},
                {"date": self.tomorrow, "open": "09:30", "close": "16:00", "label": "Regular session"},
            ],
            "today": {"date": self.today, "alerts": [], "events": [current], "earnings": []},
            "events": [current],
            "earnings": [upcoming],
            "timeline": [current, upcoming],
            "sources": {"macro": {"status": "ready"}, "earnings": {"status": "ready"}},
            "pnl": {"daily": 125.5},
        }

    def market_news_payload(self, limit=12):
        return {
            "ok": True,
            "status": "ready",
            "source": "alpaca_news",
            "source_label": "Alpaca News powered by Benzinga",
            "timestamp": "2026-07-30T12:05:00Z",
            "headlines": [
                {
                    "headline": "Markets prepare for the next macro release",
                    "summary": "Investors review the scheduled data.",
                    "source": "Benzinga",
                    "created_at": "2026-07-30T12:00:00Z",
                    "symbols": ["SPY"],
                }
            ],
        }

    def journal_payload(self, limit=20):
        return {
            "summary": {"entries": 1, "actionable": 1, "blocked": 0, "top_setup": "elephant_bar", "top_symbol": "SPY"},
            "counts": {"qualified": 1},
            "entries": [{"timestamp": "2026-07-30T14:00:00Z", "symbol": "SPY", "play": "elephant_bar", "status": "qualified"}],
            "research": [{"topic": "SPY", "authorization": "Bearer NEVER-LEAK"}],
            "replays": [{"symbol": "SPY", "scenario": "bull_elephant", "signals_found": 2, "summary": "Two setups found."}],
        }

    def bot_health(self, light=True):
        return {"overall": "green", "summary": "All monitored components are healthy.", "components": []}

    def risk_status_payload(self):
        return {"risk": {"max_dollar_risk_per_trade": 1000}, "limits": {"positions_remaining": 2}, "guardrails": []}

    def daily_review_payload(self):
        return {"lesson": "Wait for location.", "counts": {"qualified": 1}, "lines": ["One qualified setup."]}

    def daily_close_report_payload(self):
        return {
            "title": "Bull Report",
            "summary": "The desk stayed inside risk.",
            "sections": {"performance": ["Up $125.50."], "action_items": ["Keep waiting for location."]},
        }

    def daily_brief_payload(self):
        return {"title": "Protect capital first", "lines": ["Wait for structure.", "Risk one unit."]}

    def mentor_report_payload(self, scope="weekly", days=7, alert_ref=""):
        return {
            "ok": True,
            "scope": scope,
            "mode": "retail",
            "headline": "Mentor sees strategy drift first.",
            "sample": {"discipline": {"confidence": "medium"}},
            "scorecards": [{"key": "risk_discipline", "score": 82}],
            "patterns": [{"key": "drift", "message": "Frequency rose."}],
            "recommendation": {"title": "Review drift", "instruction": "Compare current trade frequency."},
            "active_drills": [{"id": "DRILL1", "title": "Daily drill: Strategy drift"}],
            "guardrails": {"can_submit_orders": False, "can_change_risk": False},
            "winston_mentor_context_pack": {
                "version": "winston_mentor_context_pack_v1",
                "loaded": True,
                "summary": "Winston has compact read access to the Mentor Safe Enhancement Lab.",
                "tools": [
                    {"key": "daily_root_cause", "focus": "Strategy drift", "summary": "Daily Root-Cause Brief points first to Strategy drift."},
                    {"key": "broker_reconciliation", "score": 96, "summary": "Broker/Data Reconciliation score is 96/100."},
                    {"key": "drill_scheduler", "recommended": {"title": "Daily drill: Strategy drift"}},
                ],
                "read_only": True,
                "advisory_only": True,
            },
        }

    def winston_velez_principles_pack_payload(self):
        return {
            "ok": True,
            "context_pack": {
                "version": "winston_velez_principles_pack_v1",
                "loaded": True,
                "summary": "Winston has read-only access to the Velez strategy principles and setup rules used by the bot.",
                "setup_reference": [{"label": "Elephant Bar", "rule": "Dominant body near a key moving average."}],
                "read_only": True,
                "can_submit_orders": False,
            },
        }


def test_every_shared_room_is_readable_and_mentor_is_the_only_exception():
    service = RoomAwarenessService(FakeRoomEngine(), product_name="Velez Trading Bot", has_mentor=False)

    payload = service.payload(
        service.room_ids,
        client_context={
            "chart": {"symbol": "SPY"},
            "music": {"authorized": True, "is_playing": True, "now_playing": {"title": "Smooth Operator", "artist": "Sade"}},
            "phone": {"call_active": True, "muted": False},
            "notes": {"manual_note": "Desk note; api key is TOPSECRET123"},
        },
    )

    expected = set(ROOMS) - {"mentor"}
    assert payload["ok"] is True
    assert payload["coverage"] == {"requested": len(expected), "readable": len(expected), "failed": []}
    assert set(payload["rooms"]) == expected
    assert payload["intentional_exceptions"] == ["mentor is available in Bull Pilot only"]
    assert payload["rooms"]["music"]["data"]["player"]["now_playing"]["artist"] == "Sade"


def test_calendar_reports_current_and_upcoming_scheduled_news_events():
    engine = FakeRoomEngine()
    service = RoomAwarenessService(engine, product_name="Velez Trading Bot", has_mentor=False)

    room = service.payload("calendar")["rooms"]["calendar"]

    assert room["data"]["current_events"][0]["title"] == "Employment Situation"
    assert room["data"]["upcoming_events"][0]["title"] == "SPY earnings watch"
    assert room["data"]["current_news"][0]["headline"] == "Markets prepare for the next macro release"
    assert room["data"]["sources"]["macro"]["status"] == "ready"
    assert "Headlines are context" in room["data"]["scope_note"]


def test_mentor_room_includes_winston_context_pack_when_available():
    service = RoomAwarenessService(FakeRoomEngine(), product_name="Velez Trading Bot", has_mentor=True)

    room = service.payload("mentor")["rooms"]["mentor"]

    assert room["ok"] is True
    assert room["data"]["winston_mentor_context_pack"]["version"] == "winston_mentor_context_pack_v1"
    assert any("Root cause: Strategy drift" in item for item in room["facts"])
    assert any("Reconciliation: 96/100" in item for item in room["facts"])


def test_bookshelf_room_includes_winston_velez_principles_pack_when_available():
    service = RoomAwarenessService(FakeRoomEngine(), product_name="Velez Trading Bot", has_mentor=True)

    room = service.payload("bookshelf")["rooms"]["bookshelf"]

    assert room["ok"] is True
    assert room["data"]["winston_velez_principles_pack"]["version"] == "winston_velez_principles_pack_v1"
    assert room["data"]["winston_velez_principles_pack"]["read_only"] is True
    assert any("Velez Principles Pack" in item for item in room["facts"])


def test_connected_alpaca_news_request_is_read_only_and_bounded(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        text = '{"news":[]}'

        def json(self):
            return {"news": [{"id": 1, "headline": "Latest market headline"}]}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append((url, headers, params, timeout))
        return Response()

    monkeypatch.setattr("bot.brokers.alpaca.requests.get", fake_get)
    broker = AlpacaPaperBroker(
        AlpacaPaperConfig(key_id="masked-id", secret_key="masked-secret", timeout_seconds=5)
    )

    news = broker.get_news_raw(symbols="SPY,QQQ", limit=500)

    assert news[0]["headline"] == "Latest market headline"
    assert calls[0][0] == "https://data.alpaca.markets/v1beta1/news"
    assert calls[0][2] == {"sort": "desc", "limit": 50, "include_content": "false", "symbols": "SPY,QQQ"}


def test_market_news_degrades_cleanly_without_a_news_capable_broker():
    engine = TradingViewWebhookEngine(config(), broker=object())

    result = engine.market_news_payload()

    assert result["ok"] is False
    assert result["status"] == "not_configured"
    assert result["headlines"] == []


def test_room_payload_removes_secret_fields_and_redacts_secret_text():
    service = RoomAwarenessService(FakeRoomEngine(), product_name="Velez Trading Bot", has_mentor=False)

    payload = service.payload(["safe", "journal", "notes"], client_context={"notes": {"manual_note": "api key is TOPSECRET123"}})
    serialized = json.dumps(payload)

    assert "PA123456789" not in serialized
    assert "SHOULD-NOT-LEAK" not in serialized
    assert "NEVER-LEAK" not in serialized
    assert "TOPSECRET123" not in serialized
    assert payload["rooms"]["safe"]["data"]["broker"]["account_number_tail"] == "6789"
    assert "[REDACTED]" in serialized


def test_room_detection_covers_prior_blind_spots_and_whole_room():
    service = RoomAwarenessService(FakeRoomEngine(), product_name="Velez Trading Bot", has_mentor=False)
    cases = {
        "What is on my daily mission card?": ["mission"],
        "Summarize the trade journal.": ["journal"],
        "What does the Bull Report say?": ["notes"],
        "What is in the backtest drawer?": ["drawer"],
        "What does the desk clock say about market sessions?": ["clock"],
        "What upcoming news events are on the calendar?": ["calendar"],
    }

    for prompt, expected in cases.items():
        assert service.detect_rooms(prompt) == expected
    assert service.detect_rooms("Read everything in this room.") == service.room_ids


def test_winston_routes_room_questions_to_read_only_awareness(monkeypatch):
    monkeypatch.setenv("WINSTON_LLM_PROVIDER", "rule_based")
    engine = TradingViewWebhookEngine(config())
    awareness = RoomAwarenessService(FakeRoomEngine(), product_name="Velez Trading Bot", has_mentor=False)
    monkeypatch.setattr(engine, "room_awareness", awareness)

    result = engine.winston_reply("What does the Bull Report say?", {"notes": {"manual_note": "Protect the downside."}})

    assert result["ok"] is True
    assert result["intent"] == "room_awareness"
    assert result["provider"] == "winston_room_awareness_v1"
    assert result["rooms"] == ["notes"]
    assert result["room_awareness"]["read_only"] is True
    assert "desk stayed inside risk" in result["reply"]


def test_winston_falls_back_when_llm_incorrectly_denies_readable_room_context(monkeypatch):
    engine = TradingViewWebhookEngine(config())
    awareness = RoomAwarenessService(FakeRoomEngine(), product_name="Velez Trading Bot", has_mentor=False)
    monkeypatch.setattr(engine, "room_awareness", awareness)
    monkeypatch.setattr(
        engine.winston,
        "reply",
        lambda *args, **kwargs: {
            "ok": True,
            "reply": "I don't have any information on that mission card. Point me to the room.",
            "provider": "openai_compatible",
            "llm_used": True,
        },
    )

    result = engine.winston_reply("What is on my daily mission card?")

    assert result["provider"] == "winston_room_awareness_v1"
    assert result["fallback_reason"] == "llm_missed_room_context"
    assert "Protect capital first" in result["reply"]


def test_winston_capabilities_advertise_whole_room_and_news_access(monkeypatch):
    monkeypatch.setenv("WINSTON_LLM_PROVIDER", "rule_based")
    engine = TradingViewWebhookEngine(config())

    result = engine.winston_reply("What can you do?")

    assert "read every room object" in result["reply"]
    assert "scheduled events and recent headlines" in result["reply"]


def test_winston_llm_messages_include_room_context_with_security_instructions(monkeypatch):
    engine = TradingViewWebhookEngine(config())
    monkeypatch.setattr(engine, "dashboard_state", FakeRoomEngine().dashboard_state)
    monkeypatch.setattr(engine, "daily_brief_payload", FakeRoomEngine().daily_brief_payload)
    room_context = {"read_only": True, "rooms": {"calendar": {"summary": "One event is upcoming."}}}

    messages = engine.winston._messages("What is next?", room_context=room_context)

    assert "room-awareness context" in messages[0]["content"]
    assert "Never reveal or request credentials" in messages[0]["content"]
    assert "Room-awareness context JSON (primary source for this request)" in messages[1]["content"]
    assert "One event is upcoming." in messages[1]["content"]


def test_room_awareness_endpoint_and_browser_context_contract():
    client = TestClient(create_app(config()))

    response = client.get("/api/room-awareness?room=bookshelf")
    js = (Path(__file__).resolve().parents[1] / "static" / "dashboard" / "app.js").read_text()

    assert response.status_code == 200
    assert response.json()["requested_rooms"] == ["bookshelf"]
    assert response.json()["rooms"]["bookshelf"]["read_only"] is True
    assert "function winstonRoomContext()" in js
    assert "room_context: winstonRoomContext()" in js
