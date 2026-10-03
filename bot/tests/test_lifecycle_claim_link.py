"""A position's journal decision must be found from its claim, however old the decision is."""

from bot.tests.test_velez_daily_range_profit_taking import lifecycle_engine


def _record(engine, alert_id, symbol="TSLA", side="sell", status="submitted"):
    decision = type("D", (), {"status": status, "reason": "", "symbol": symbol, "side": side, "play": "elephant",
                              "qty": 73, "order_payload": None, "broker_response": None, "metadata": {}})()
    engine._remember_decisions([decision], alert_id)


def test_the_auto_claim_uses_the_form_decisions_are_filed_under(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    _record(engine, "alert-raw-id-1")
    engine._set_lifecycle_claim("TSLA", {"alert_ref": engine._decision_alert_ref("alert-raw-id-1")})
    linked = engine._link_decision_for_symbol("TSLA", [], side="short")
    assert linked and linked["alert_ref"] == engine._decision_alert_ref("alert-raw-id-1")


def test_a_claim_holding_the_raw_alert_id_still_resolves(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    _record(engine, "alert-raw-id-2")
    engine._set_lifecycle_claim("TSLA", {"alert_ref": "alert-raw-id-2"})  # claims written before the fix
    linked = engine._link_decision_for_symbol("TSLA", [], side="short")
    assert linked and linked["status"] == "submitted"


def test_a_claim_resolves_even_when_the_newest_rows_are_all_rejections(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    _record(engine, "alert-old", symbol="HOOD", side="sell")
    engine._set_lifecycle_claim("HOOD", {"alert_ref": "alert-old"})
    for i in range(30):
        _record(engine, f"rej-{i}", symbol="HOOD", side="sell", status="rejected")
    newest_only = engine.journal.decision_entries(limit=10)  # the window an orphan lookup used to see
    assert all(row["status"] == "rejected" for row in newest_only)
    linked = engine._link_decision_for_symbol("HOOD", newest_only, side="short")
    assert linked and linked["status"] == "submitted"


def test_a_later_rejection_of_the_same_alert_does_not_replace_the_executed_decision(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    _record(engine, "alert-two-signals", symbol="TSLA", side="sell", status="submitted")
    _record(engine, "alert-two-signals", symbol="TSLA", side="sell", status="rejected")  # same bar, a second signal
    engine._set_lifecycle_claim("TSLA", {"alert_ref": "alert-two-signals"})
    linked = engine._link_decision_for_symbol("TSLA", [], side="short")
    assert linked and linked["status"] == "submitted"


def test_a_claim_for_the_other_side_or_an_unexecuted_decision_does_not_own_the_position(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    _record(engine, "alert-buy", symbol="TSLA", side="buy")
    engine._set_lifecycle_claim("TSLA", {"alert_ref": "alert-buy"})
    assert engine._link_decision_for_symbol("TSLA", [], side="short") is None  # a short is not this long's
    _record(engine, "alert-rej", symbol="HOOD", side="sell", status="rejected")
    engine._set_lifecycle_claim("HOOD", {"alert_ref": "alert-rej"})
    assert engine._link_decision_for_symbol("HOOD", [], side="short") is None


def test_a_directionless_decision_does_not_own_a_position(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    _record(engine, "alert-nodir", symbol="TSLA", side="")
    engine._set_lifecycle_claim("TSLA", {"alert_ref": "alert-nodir"})
    assert engine._link_decision_for_symbol("TSLA", [], side="short") is None


def test_several_executed_decisions_on_one_alert_resolve_by_symbol_and_side(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    _record(engine, "alert-multi", symbol="TSLA", side="sell")
    _record(engine, "alert-multi", symbol="TSLA", side="buy")    # a later, opposite-side signal from the same bar
    _record(engine, "alert-multi", symbol="HOOD", side="sell")   # and another symbol's, newest of all
    engine._set_lifecycle_claim("TSLA", {"alert_ref": "alert-multi"})
    linked = engine._link_decision_for_symbol("TSLA", [], side="short")
    assert linked and linked["symbol"] == "TSLA" and linked["side"] == "sell"


def test_a_claim_with_no_matching_decision_is_not_rescued_by_the_recent_window(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    _record(engine, "alert-claimed", symbol="TSLA", side="buy")           # the claimed decision is the other side
    _record(engine, "alert-lookalike", symbol="TSLA", side="sell")        # a recent sell for the same symbol
    engine._set_lifecycle_claim("TSLA", {"alert_ref": "alert-claimed"})
    recent = engine.journal.decision_entries(limit=50)
    assert engine._link_decision_for_symbol("TSLA", recent, side="short") is None


def test_claims_are_dropped_once_their_position_is_gone_but_not_while_fresh_or_working(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    claims = {
        "HOOD": {"claim_type": "trading_bull_journal", "symbol": "HOOD", "alert_ref": "a", "claimed_at": old},
        "TSLA": {"claim_type": "trading_bull_journal", "symbol": "TSLA", "alert_ref": "b", "claimed_at": old},
        "UBER": {"claim_type": "trading_bull_journal", "symbol": "UBER", "alert_ref": "c",
                 "claimed_at": datetime.now(timezone.utc).isoformat()},  # made a moment ago, order not filled yet
        "EXT": {"claim_type": "external", "symbol": "EXT", "claimed_at": old},
    }
    engine.journal.set_setting("lifecycle.position_claims", claims)
    engine._prune_lifecycle_claims({"TSLA"})  # TSLA still held
    left = engine._lifecycle_claims()
    assert set(left) == {"TSLA", "UBER", "EXT"}  # HOOD's position is gone; fresh and external claims stay


def test_concurrent_claim_writes_survive_a_prune(monkeypatch, tmp_path):
    import threading
    from datetime import datetime, timedelta, timezone
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    engine.journal.set_setting("lifecycle.position_claims", {
        "HOOD": {"claim_type": "trading_bull_journal", "symbol": "HOOD", "alert_ref": "a", "claimed_at": old}})
    errors = []

    def writer(i):
        try:
            engine._set_lifecycle_claim(f"SYM{i}", {"alert_ref": f"r{i}"})
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    engine._prune_lifecycle_claims(set())
    for t in threads:
        t.join()
    assert not errors
    assert {f"SYM{i}" for i in range(8)} <= set(engine._lifecycle_claims())  # none lost to the prune's write
    assert "HOOD" not in engine._lifecycle_claims()


def test_claims_are_not_pruned_without_a_complete_order_snapshot(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    engine.journal.set_setting("lifecycle.position_claims", {
        "HOOD": {"claim_type": "trading_bull_journal", "symbol": "HOOD", "alert_ref": "a", "claimed_at": old}})
    monkeypatch.setattr(engine, "_raw_positions_for_lifecycle", lambda: ([], None))
    monkeypatch.setattr(engine, "_raw_fills_for_lifecycle", lambda: ([], None))
    monkeypatch.setattr(broker, "is_configured", lambda: True, raising=False)
    monkeypatch.setattr(engine, "_raw_orders_for_lifecycle", lambda: ([], "orders_unavailable"))
    engine.lifecycle_payload(allow_auto_actions=False)
    assert "HOOD" in engine._lifecycle_claims()  # orders unknown: a working entry could still be out there
    monkeypatch.setattr(engine, "_raw_orders_for_lifecycle", lambda: ([], None))
    engine.lifecycle_payload(allow_auto_actions=False)
    assert "HOOD" not in engine._lifecycle_claims()  # complete picture, nothing held or working


def test_a_symbol_that_just_filled_keeps_its_claim(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    engine.journal.set_setting("lifecycle.position_claims", {
        "HOOD": {"claim_type": "trading_bull_journal", "symbol": "HOOD", "alert_ref": "a", "claimed_at": old}})
    just_now = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    monkeypatch.setattr(engine, "_raw_positions_for_lifecycle", lambda: ([], None))   # read before the fill
    monkeypatch.setattr(engine, "_raw_orders_for_lifecycle", lambda: ([], None))      # read after it
    monkeypatch.setattr(engine, "_raw_fills_for_lifecycle", lambda: ([{"symbol": "HOOD", "transaction_time": just_now}], None))
    monkeypatch.setattr(broker, "is_configured", lambda: True, raising=False)
    engine.lifecycle_payload(allow_auto_actions=False)
    assert "HOOD" in engine._lifecycle_claims()


def test_without_a_fill_feed_a_claim_goes_only_after_several_flat_passes_over_time(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    engine.journal.set_setting("lifecycle.position_claims", {
        "HOOD": {"claim_type": "trading_bull_journal", "symbol": "HOOD", "alert_ref": "a", "claimed_at": old}})
    monkeypatch.setattr(engine, "_raw_positions_for_lifecycle", lambda: ([], None))
    monkeypatch.setattr(engine, "_raw_orders_for_lifecycle", lambda **_kw: ([], None))
    monkeypatch.setattr(engine, "_raw_fills_for_lifecycle", lambda: ([], "broker_fill_snapshot_not_supported"))
    monkeypatch.setattr(broker, "is_configured", lambda: True, raising=False)
    for _ in range(5):  # many passes, but all within the same moment: not enough time has gone by
        engine.lifecycle_payload(allow_auto_actions=False)
    assert "HOOD" in engine._lifecycle_claims()
    engine._claim_flat_seen["HOOD"][1] -= timedelta(minutes=5)  # the first flat pass was five minutes ago
    engine.lifecycle_payload(allow_auto_actions=False)
    assert "HOOD" not in engine._lifecycle_claims()


def test_a_claim_that_turns_live_again_resets_its_flat_count(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    engine.journal.set_setting("lifecycle.position_claims", {
        "HOOD": {"claim_type": "trading_bull_journal", "symbol": "HOOD", "alert_ref": "a", "claimed_at": old}})
    for _ in range(2):
        engine._prune_lifecycle_claims(set(), flat_passes=3, flat_seconds=0)
    engine._prune_lifecycle_claims({"HOOD"}, flat_passes=3, flat_seconds=0)  # held again
    engine._prune_lifecycle_claims(set(), flat_passes=3, flat_seconds=0)
    assert "HOOD" in engine._lifecycle_claims()  # the count started over
