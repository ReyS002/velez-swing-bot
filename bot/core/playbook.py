"""Searchable, versioned Velez playbook metadata for the Desk UI."""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable, List, Mapping


PLAYBOOK_VERSION = "velez_playbook_v1"


PLAYBOOK = [
    {
        "id": "elephant_bar",
        "title": "Elephant Bar",
        "aliases": ["elephant", "institutional ignition"],
        "qualification": ["Dominant real body versus recent bars", "Small opposing wicks", "Breaks structure at the 20 SMA, 200 SMA, or qualified extension"],
        "invalidation": "Price trades one tick beyond the opposite end of the qualifying bar or the required location is absent.",
        "preferred_regime": ["risk_on_trend", "risk_off_trend", "selective with aligned direction"],
        "entry_trigger": "Qualified close through structure; use a 50% body retracement when the event is climactic or chased.",
        "stop_logic": "One tick beyond the opposite end of the Elephant Bar.",
        "target_logic": "Use the configured R plan, first partial near 1R, and the next target near 2R when structure permits.",
        "failure_modes": ["No structural location", "Oversized opposing wick", "Chasing beyond the configured threshold", "Immediate failed break"],
    },
    {
        "id": "one_eighty_reversal",
        "title": "Bull / Bear 180",
        "aliases": ["bull 180", "bear 180", "one eighty"],
        "qualification": ["Two opposing bars", "Second bar recovers 80–100% of the first body", "Occurs at a qualified moving-average location"],
        "invalidation": "The two-bar low breaks for a Bull 180 or the two-bar high breaks for a Bear 180.",
        "preferred_regime": ["selective", "mixed_or_transition", "trend pullback at structure"],
        "entry_trigger": "Recovery through the 80% threshold or the confirming close of bar two.",
        "stop_logic": "One tick beyond the extreme of the two-bar sequence.",
        "target_logic": "First objective at 1R; second objective at 2R or the next verified structure level.",
        "failure_modes": ["Recovery below 80%", "No moving-average location", "Entering before bar-two confirmation", "Strong top-down opposition"],
    },
    {
        "id": "tail_reversal",
        "title": "Topping / Bottoming Tail",
        "aliases": ["tail", "failed auction"],
        "qualification": ["Tail is at least 66% of candle range", "Price is extended or testing a major moving average", "Close confirms rejection"],
        "invalidation": "Price breaks one tick beyond the tail extreme.",
        "preferred_regime": ["mixed_or_transition", "selective", "extended trend exhaustion"],
        "entry_trigger": "Confirmed close or a 50% retracement entry when the rule set permits.",
        "stop_logic": "One tick beyond the tail wick extreme.",
        "target_logic": "Use 1R/2R objectives and the next verified structure; do not assume a full trend reversal.",
        "failure_modes": ["Tail below 66%", "Middle-of-range location", "No rejection confirmation", "Continuation through the extreme"],
    },
    {
        "id": "buy_sell_setup",
        "title": "Velez Buy / Sell Setup",
        "aliases": ["buy setup", "sell setup", "controlled pullback"],
        "qualification": ["Trend and moving-average structure agree", "Pullback is controlled", "Trigger bar reclaims the pullback pivot or 20 SMA"],
        "invalidation": "The controlled pullback low/high fails or moving-average structure loses alignment.",
        "preferred_regime": ["risk_on_trend", "risk_off_trend"],
        "entry_trigger": "Break of the confirming trigger bar after the controlled pullback.",
        "stop_logic": "One tick beyond the pullback sequence extreme.",
        "target_logic": "Scale against 1R/2R and nearby structure while preserving the original risk cap.",
        "failure_modes": ["Deep high-volume pullback", "Flat or opposing trend", "Late entry after expansion", "No clean space"],
    },
    {
        "id": "nrb_acorn",
        "title": "NRB / Acorn",
        "aliases": ["nrb", "acorn", "narrow range"],
        "qualification": ["Narrow-range pause", "Existing qualified trend", "Break resumes with directional confirmation"],
        "invalidation": "Price breaks the opposite side of the narrow-range bar.",
        "preferred_regime": ["risk_on_trend", "risk_off_trend"],
        "entry_trigger": "Directional break of the narrow-range pause bar.",
        "stop_logic": "One tick beyond the opposite side of the pause bar.",
        "target_logic": "Use the configured R ladder and prior trend structure.",
        "failure_modes": ["Pause occurs in chop", "Range is not meaningfully narrow", "False break with no volume support", "Obstacle too close"],
    },
    {
        "id": "color_change_add",
        "title": "First Color-Change Add",
        "aliases": ["color change", "pyramid", "add to winner"],
        "qualification": ["Existing winning position", "Initial risk already mitigated", "First directional color change clears the pullback pivot", "Pullback volume fades"],
        "invalidation": "The position is not profitable, risk is not mitigated, or the pullback pivot fails.",
        "preferred_regime": ["risk_on_trend", "risk_off_trend"],
        "entry_trigger": "First confirming color change after the controlled pullback.",
        "stop_logic": "Use the new pullback structure without increasing total authorized risk.",
        "target_logic": "Manage with the original position plan; the add is never a new oversized core.",
        "failure_modes": ["Adding to a loser", "Add exceeds 50% of current size", "High-volume opposition", "Original risk not mitigated"],
    },
    {
        "id": "fab4_trap",
        "title": "Fab 4 Trap-Zone Breakout",
        "aliases": ["fab 4", "trap zone", "compression"],
        "qualification": ["20 SMA, 200 SMA, price, and recent range compress", "Zone boundaries are verified", "Close breaks with directional control"],
        "invalidation": "Price crosses the opposite side of the compression zone.",
        "preferred_regime": ["mixed_or_transition", "quiet", "selective"],
        "entry_trigger": "Confirmed close through the trap-zone boundary.",
        "stop_logic": "One tick beyond the opposite edge of the compressed zone.",
        "target_logic": "First objective at 1R; then the next clean structure or 2R.",
        "failure_modes": ["Loose rather than compressed averages", "Break into nearby obstacle", "No directional close", "Expansion already exhausted"],
    },
    {
        "id": "failed_breakout",
        "title": "Failed New High / Low",
        "aliases": ["failed new high", "failed new low", "failed breakout"],
        "qualification": ["Fresh extreme", "Rejection closes back through prior structure", "Extension or 200 SMA context supports a failed auction"],
        "invalidation": "Price reclaims the failed extreme.",
        "preferred_regime": ["mixed_or_transition", "selective", "extended trend exhaustion"],
        "entry_trigger": "Close back inside structure after the failed extreme.",
        "stop_logic": "One tick beyond the failed high or low.",
        "target_logic": "Target the opposite side of the local range, then 2R only if space remains.",
        "failure_modes": ["No fresh extreme", "Weak rejection", "Countertrend without extension", "Re-entry through the extreme"],
    },
    {
        "id": "opening_gap_go",
        "title": "Opening Gap Go",
        "aliases": ["gap go", "opening drive"],
        "qualification": ["Gap meets configured minimum", "First-bar control agrees", "Clean space exists beyond prior structure", "Opening-window timing is valid"],
        "invalidation": "The opening range fails or the gap immediately loses directional control.",
        "preferred_regime": ["risk_on_trend", "risk_off_trend", "strong directional open"],
        "entry_trigger": "First-bar control or qualified opening-range break.",
        "stop_logic": "One tick beyond the opening-range invalidation.",
        "target_logic": "Use 1R/2R plus the next verified obstacle; stop when clean space is consumed.",
        "failure_modes": ["Gap too small or too large for configuration", "No first-bar control", "Obstacle too close", "Late opening entry"],
    },
    {
        "id": "opening_gap_fade",
        "title": "Opening Gap Fade",
        "aliases": ["gap fade", "gap fill"],
        "qualification": ["Gap rejects into extension, 200 SMA, or nearby structure", "Rejection candle confirms", "Adequate space remains toward prior close"],
        "invalidation": "Price breaks the rejected opening extreme.",
        "preferred_regime": ["mixed_or_transition", "selective", "exhausted opening gap"],
        "entry_trigger": "Confirmed rejection back toward the prior close.",
        "stop_logic": "One tick beyond the rejected opening extreme.",
        "target_logic": "Prior close is the principal gap-fill reference; use partials if structure interrupts the path.",
        "failure_modes": ["No rejection", "Insufficient gap-fill space", "Strong aligned opening drive", "Entry after most of the gap is filled"],
    },
    {
        "id": "time_space_breakout",
        "title": "Time + Space Breakout",
        "aliases": ["time and space", "opening range breakout"],
        "qualification": ["Small-gap open", "Opening range is established", "Break occurs inside the configured time window", "Clean space and location scores qualify"],
        "invalidation": "Price loses the opposite side of the opening range or the clean-space premise disappears.",
        "preferred_regime": ["selective", "risk_on_trend", "risk_off_trend"],
        "entry_trigger": "Qualified early-range break after time, space, location, and range checks.",
        "stop_logic": "One tick beyond the opening-range invalidation.",
        "target_logic": "Use verified obstacle levels and the configured 1R/2R management plan.",
        "failure_modes": ["Break outside the time window", "No clean space", "Poor location score", "Opening range too wide"],
    },
]


def searchable_playbook(query: str = "", setup: str = "") -> dict:
    needle = " ".join(str(query or "").lower().split())
    setup_key = str(setup or "").lower().replace("-", "_").replace(" ", "_")
    entries: List[dict] = []
    for raw in PLAYBOOK:
        haystack = " ".join(
            [raw["id"], raw["title"], *raw.get("aliases", []), *raw.get("qualification", []), *raw.get("failure_modes", [])]
        ).lower()
        matches_setup = not setup_key or setup_key == raw["id"] or setup_key in {alias.replace(" ", "_") for alias in raw.get("aliases", [])}
        if matches_setup and (not needle or needle in haystack):
            entry = deepcopy(raw)
            entry["examples"] = []
            entry["example_state"] = "Unavailable until a verified journal/replay example is linked."
            entries.append(entry)
    return {
        "ok": True,
        "version": PLAYBOOK_VERSION,
        "query": query or "",
        "setup": setup or "",
        "count": len(entries),
        "entries": entries,
        "source": "velez_strategy_engine_and_versioned_playbook",
        "advisory_only": True,
    }


def link_playbook_entries(entries: Iterable[Mapping[str, object]], decisions: Iterable[Mapping[str, object]]) -> List[dict]:
    linked = []
    decision_rows = list(decisions)
    for raw in entries:
        entry = deepcopy(dict(raw))
        aliases = {entry.get("id", ""), *(str(item).lower().replace(" ", "_") for item in entry.get("aliases", []))}
        refs = []
        for decision in decision_rows:
            play = str(decision.get("play") or decision.get("setup") or "").lower().replace(" ", "_")
            if play in aliases or any(alias and alias in play for alias in aliases):
                if decision.get("alert_ref"):
                    refs.append(str(decision["alert_ref"]))
        entry["detected_alert_refs"] = list(dict.fromkeys(refs))[:20]
        linked.append(entry)
    return linked
