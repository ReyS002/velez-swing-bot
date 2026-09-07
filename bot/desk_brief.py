"""Private, timestamped desk briefings and context-bound Winston follow-ups."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import threading
import time
import uuid


def brief_owner(request) -> str:
    account = getattr(request.state, "account", None) or {}
    identity = account.get("email") or request.headers.get("authorization") or "workspace"
    return hashlib.sha256(str(identity).encode()).hexdigest()


def build_brief(daily: dict, market: dict, *, product: str, provider: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    sections = []
    def section(key, title, text, sources, **extra):
        sections.append({"id": key, "title": title, "text": text, "sources": sources, **extra})

    quotes = [q for q in market.get("items", []) if q.get("price") is not None]
    context_quotes = [q for q in quotes if q["symbol"] in {"SPY", "QQQ", "VIX"}][:3]
    changes = []
    for q in context_quotes:
        change = q.get("change_percent")
        suffix = f", {'up' if change >= 0 else 'down'} {abs(change):.2f} percent" if isinstance(change, (int, float)) else ""
        changes.append(f"{q['symbol']} is {q['price']:,.2f}{suffix}")
    session = market.get("market_status", "unknown")
    status = "The equity market is closed; these are last available prices. " if session == "closed" else ""
    stale = "Some quotes are stale or have unknown update times. " if any(q.get("stale") for q in quotes) else ""
    section("market", "Market snapshot", f"Here is your {product} desk brief. {status}{stale}" +
            ("; ".join(changes) + ". " if changes else "Market quotes are unavailable. ") +
            "This briefing uses one saved snapshot; prices can change after it is prepared.",
            list(dict.fromkeys(q.get("source") for q in quotes if q.get("source"))), quotes=quotes,
            as_of=market.get("as_of"), stale=market.get("stale", False))

    calendar = daily.get("calendar", {})
    events, earnings = calendar.get("events", []), calendar.get("earnings", [])
    event_lines = [f"{e.get('title', 'Economic release')} is listed for {e.get('date', 'a date not supplied')} {e.get('time', '')}".strip() + "." for e in events[:1]]
    if not event_lines:
        event_lines = ["No economic events are loaded in this snapshot."]
    if earnings:
        event_lines.append("Earnings to review: " + "; ".join(f"{e.get('symbol')} on {e.get('date')}" for e in earnings[:2]) + ".")
        event_lines.append("The earnings source supplies dates, without confirmed release times.")
    else:
        event_lines.append("No matching earnings dates are loaded.")
    av = calendar.get("sources", {}).get("alpha_vantage", {})
    if not av.get("ok", False):
        event_lines.append("The earnings feed needs a refresh or is unavailable.")
    section("calendar", "Events ahead", " ".join(event_lines),
            list(dict.fromkeys(e.get("source", "Calendar") for e in events[:1] + earnings[:2])),
            events=events, earnings=earnings, earnings_source=av)

    watchlist, positions = daily.get("watchlist", []), daily.get("positions", [])
    names = [str(p.get("symbol")) for p in positions[:3] if p.get("symbol")]
    watch = [str(p.get("symbol")) for p in watchlist[:3] if p.get("symbol")]
    position_text = f"This desk has {len(positions)} reported open positions and {len(watchlist)} watchlist symbols. "
    position_text += ("Open positions include " + ", ".join(names) + ". ") if names else "No open positions are reported in this snapshot. "
    position_text += ("On your watchlist: " + ", ".join(watch) + ". ") if watch else ""
    decisions = daily.get("recent_decisions", [])
    if decisions:
        latest = decisions[0]
        position_text += f"The latest journal item is {latest.get('symbol', 'an unlabelled symbol')}, with status {latest.get('status', 'unknown')}."
    else:
        position_text += "No recent journal decisions are loaded."
    section("watchlist", "Your desk", position_text, [product + " account snapshot"], positions=positions, watchlist=watchlist, recent_decisions=decisions)

    broker, risk = daily.get("broker", {}), daily.get("risk", {})
    broker_text = f"{provider} reports connected" if broker.get("ok") else f"{provider} is not ready"
    state_text = "Execution is armed" if daily.get("execution_armed") else "The desk is in proposal mode"
    risk_value = risk.get("max_dollar_risk_per_trade")
    risk_text = f"The configured risk cap is {float(risk_value):,.0f} dollars per trade. " if isinstance(risk_value, (int, float)) else ""
    approval_text = f"There are {len(daily.get("pending_approvals", []))} pending approvals to review in Command. "
    if not broker.get("ok"):
        approval_text += "Position coverage may be incomplete until the broker reconnects. "
    section("status", "Readiness", f"{state_text}, and {broker_text}. {risk_text}{approval_text}Display quotes use their own data connections. "
            "You can ask Winston about this exact briefing, or refresh it to capture a new snapshot.", [product + " runtime status"])
    narration = " ".join(s["text"] for s in sections)
    return {"ok": True, "id": uuid.uuid4().hex, "title": "Winston Desk Brief", "product": product,
            "generated_at": now, "snapshot_at": daily.get("timestamp", now), "private": True, "facts_only": True,
            "sections": sections, "narration": narration, "estimated_seconds": round(len(narration.split()) / 2.2),
            "voice": "Winston", "source_status": {"market": market.get("source"), "earnings": av}, "followup_ttl_seconds": 1800}


class DeskBriefService:
    def __init__(self, daily, market, winston, *, product, provider):
        self.daily, self.market, self.winston = daily, market, winston
        self.product, self.provider = product, provider
        self._snapshots = OrderedDict()
        self._lock = threading.Lock()

    def create(self, owner):
        value = build_brief(self.daily(), self.market(), product=self.product, provider=self.provider())
        with self._lock:
            self._snapshots[(owner, value["id"])] = {"expires": time.monotonic() + 1800, "brief": deepcopy(value), "history": []}
            while len(self._snapshots) > 128:
                self._snapshots.popitem(last=False)
        return value

    def ask(self, owner, brief_id, question):
        question = str(question or "").strip()[:1000]
        if not question:
            return {"ok": False, "reason": "question_required"}
        with self._lock:
            saved = self._snapshots.get((owner, brief_id))
            if not saved or saved["expires"] < time.monotonic():
                return {"ok": False, "reason": "brief_expired_or_unavailable"}
            context = {"snapshot": deepcopy(saved["brief"]), "conversation": deepcopy(saved["history"])}
        # The summary and sources fit before optional detailed position arrays in LLM context.
        context["snapshot"] = {k: context["snapshot"][k] for k in ("id", "snapshot_at", "narration", "source_status")}
        fallback = {"ok": True, "reply": "The saved briefing says: " + context["snapshot"]["narration"], "degraded": True}
        result = self.winston.brief_reply(question, context, fallback)
        reply = str(result.get("reply") or fallback["reply"])
        with self._lock:
            current = self._snapshots.get((owner, brief_id))
            if current:
                current["history"] = (current["history"] + [{"question": question, "reply": reply}])[-4:]
        return {"ok": True, "brief_id": brief_id, "snapshot_at": context["snapshot"]["snapshot_at"],
                "reply": reply, "degraded": bool(result.get("degraded")), "provider": result.get("provider", "saved_brief"),
                "interpretation": True}
