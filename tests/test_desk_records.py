import importlib.util
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("desk_records", ROOT / "bot" / "desk_records.py")
records = importlib.util.module_from_spec(spec)
spec.loader.exec_module(records)
NOW = datetime(2026, 9, 11, tzinfo=timezone.utc)


@pytest.fixture
def journal(tmp_path):
    path = tmp_path / "journal.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE decisions(alert_ref TEXT,broker_response_json TEXT);
            CREATE TABLE trade_outcomes(id INTEGER PRIMARY KEY,timestamp TEXT,alert_ref TEXT,
                symbol TEXT,status TEXT,pnl REAL,payload_json TEXT);
            CREATE TABLE research_notes(id INTEGER PRIMARY KEY,timestamp TEXT,topic TEXT,result_json TEXT);
        """)
        db.execute("INSERT INTO decisions VALUES (?,?)", ("owned", json.dumps({"id":"order-one"})))
    return path


def outcome(path, ref="owned", status="closed", pnl=10, terminal=True, timestamp="2026-09-10T12:00:00+00:00"):
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO trade_outcomes(timestamp,alert_ref,symbol,status,pnl,payload_json) VALUES (?,?,?,?,?,?)",
                   (timestamp,ref,"SPY",status,pnl,json.dumps({"terminal":terminal})))


def test_account_observations_do_not_become_bot_profit(journal):
    outcome(journal, ref="unlinked-SPY", pnl=1000)
    outcome(journal, status="open_position", pnl=150, terminal=False)
    outcome(journal, status="one_r_reached", pnl=50, terminal=False)
    outcome(journal, status="position_closed_stale", pnl=20, terminal=True)
    result = records.journal_performance(journal,"pilot","Bull Pilot",now=NOW)
    assert result["closed_trades"] == 0
    assert result["realized_pnl"] is None
    assert result["win_rate_pct"] is None
    assert result["unlinked_closes_excluded"] == 1


def test_duplicate_closes_not_double_counted(journal):
    outcome(journal,pnl=10)
    outcome(journal,pnl=12)
    result = records.journal_performance(journal,"velez","Velez",now=NOW)
    assert result["closed_trades"] == 1
    assert result["realized_pnl"] == 12


def test_missing_pnl_and_zero_are_distinct(journal):
    outcome(journal,pnl=None)
    result=records.journal_performance(journal,"swing","Swing",now=NOW)
    assert result["missing_pnl"] == 1 and result["realized_pnl"] is None
    outcome(journal,pnl=0)
    result=records.journal_performance(journal,"swing","Swing",now=NOW)
    assert result["realized_pnl"] == 0 and result["win_rate_pct"] == 0
    assert result["breakeven"] == 1


def test_period_and_ownership_isolation(journal):
    outcome(journal,pnl=100,timestamp="2025-01-01T12:00:00+00:00")
    outcome(journal,ref="another-bot",pnl=999)
    outcome(journal,pnl=-25)
    result=records.journal_performance(journal,"pilot","Bull Pilot",now=NOW)
    assert result["realized_pnl"] == -25
    assert len(result["trades"]) == 1


def test_saved_research_search_and_pagination(journal):
    with sqlite3.connect(journal) as db:
        for i in range(23):
            db.execute("INSERT INTO research_notes(timestamp,topic,result_json) VALUES (?,?,?)",
                       ("2026-09-10",f"Note {i}",json.dumps({"reply":"Margin 10% and SPY"})))
    first=records.research_payload(journal,"10%")
    second=records.research_payload(journal,"10%",20)
    assert first["total"] == 23 and len(first["notes"]) == 20 and len(second["notes"]) == 3
    assert set(n["id"] for n in first["notes"]).isdisjoint(n["id"] for n in second["notes"])
    assert records.research_payload(journal,"missing")["notes"] == []


def test_swarm_uses_closed_paper_trades_not_summary_backtests(tmp_path):
    path=tmp_path/"score.json"
    path.write_text(json.dumps({"generated_at":"2026-09-10T00:00:00+00:00","overall":{"realized_pnl_dollars":99999},
        "trades":[{"is_closed":True,"closed_at":"2026-09-10T12:00:00+00:00","pnl_dollars":-74.75,"symbol":"NVDA"},
                  {"is_closed":False,"pnl_dollars":1000}]}))
    result=records.swarm_performance(path,now=NOW)
    assert result["realized_pnl"] == -74.75 and result["closed_trades"] == 1
    assert result["stale"] is True


def test_sources_are_read_only(journal):
    with records.connect(journal) as db:
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM research_notes")

def test_routes_and_peer_scope(journal, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    monkeypatch.setenv("DESK_SWING_JOURNAL", str(journal))
    monkeypatch.setenv("DESK_SWARM_SCORECARD", str(journal.parent/"missing-scorecard.json"))
    for bot_id, expected in [("velez", 3), ("bull-pilot", 1), ("swing", 1)]:
        app = FastAPI()
        records.install_desk_records(app, SimpleNamespace(journal=SimpleNamespace(path=journal)), bot_id, bot_id)
        with TestClient(app) as client:
            response = client.get("/api/desk/performance?days=30")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            cards = response.json()["cards"]
            assert len(cards) == expected and cards[0]["bot_id"] == bot_id
            if bot_id == "velez":
                assert cards[1]["ok"] is True and cards[2]["ok"] is False
            assert client.get("/api/desk/research?offset=-1").status_code == 422
            assert client.get("/api/desk/performance?days=0").status_code == 422
            assert client.get("/api/desk/research?q=missing").json()["total"] == 0

