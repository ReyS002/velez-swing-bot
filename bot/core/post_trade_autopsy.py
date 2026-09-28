from __future__ import annotations

import hashlib
import html
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class PostTradeAutopsyEngine:
    """Evidence-only closed-trade review and entry-chart renderer."""

    VERSION = "post_trade_autopsy_v1"

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or {}

    def build(
        self,
        *,
        previous_position: dict,
        decision: dict,
        exit_fills: List[dict],
        chart_bars: List[dict],
        outcome: dict,
        created_at: Optional[str] = None,
        chart_source: str = "",
    ) -> dict:
        symbol = str(previous_position.get("symbol") or decision.get("symbol") or "").upper().strip()
        alert_ref = str(
            previous_position.get("linked_alert_ref")
            or decision.get("alert_ref")
            or f"unlinked-{symbol}"
        )
        event_key = str(outcome.get("event_key") or f"{alert_ref}:{symbol}:closed")
        entry_bar = self._entry_bar(chart_bars, decision.get("timestamp"))
        classification = self.classify_entry_bar(chart_bars, entry_bar)
        risk = self._risk_review(previous_position, decision, outcome)
        setup = self._setup_review(decision, classification)
        lesson = self._lesson(decision, classification, risk, outcome)
        bullets = [
            {
                "title": "Setup and location",
                "text": setup,
                "evidence": [value for value in (alert_ref, decision.get("journal_id")) if value],
            },
            {
                "title": "Risk and execution",
                "text": risk["text"],
                "evidence": [value for value in (alert_ref, outcome.get("id")) if value],
            },
            {
                "title": "Mentor lesson",
                "text": lesson,
                "evidence": [alert_ref],
            },
        ]
        return {
            "version": self.VERSION,
            "event_key": event_key,
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
            "alert_ref": alert_ref,
            "symbol": symbol,
            "status": "complete",
            "outcome_id": outcome.get("id"),
            "outcome": outcome,
            "decision": {
                key: decision.get(key)
                for key in (
                    "timestamp",
                    "alert_ref",
                    "symbol",
                    "side",
                    "play",
                    "location",
                    "entry_price",
                    "stop_price",
                    "take_profit_price",
                    "timeframe",
                    "confidence_receipt",
                    "market_context",
                )
            },
            "entry_bar": entry_bar,
            "bar_classification": classification,
            "exit_fills": exit_fills,
            "risk_review": risk,
            "bullets": bullets,
            "mentor_summary": " ".join(f"{index + 1}. {item['text']}" for index, item in enumerate(bullets)),
            "advisory_only": True,
            "chart_available": bool(chart_bars),
            "chart_source": str(chart_source or "connected_market_data") if chart_bars else "journal_context_only",
            "chart_bar_count": len(chart_bars),
        }

    def classify_entry_bar(self, bars: List[dict], entry_bar: Optional[dict]) -> dict:
        if not entry_bar:
            return {
                "label": "unavailable",
                "confidence": "insufficient",
                "reason": "Historical OHLC bars were unavailable for the linked entry.",
                "measurements": {},
            }
        index = bars.index(entry_bar) if entry_bar in bars else len(bars) - 1
        history = bars[max(0, index - 14) : index + 1]
        high = self._number(entry_bar.get("high"))
        low = self._number(entry_bar.get("low"))
        open_price = self._number(entry_bar.get("open"))
        close = self._number(entry_bar.get("close"))
        if None in {high, low, open_price, close} or high <= low:
            return {
                "label": "unavailable",
                "confidence": "insufficient",
                "reason": "The linked entry bar did not contain valid OHLC values.",
                "measurements": {},
            }
        ranges = [
            max(0.0, (self._number(item.get("high")) or 0) - (self._number(item.get("low")) or 0))
            for item in history[:-1]
        ]
        average_range = sum(ranges) / len(ranges) if ranges else high - low
        candle_range = high - low
        body = abs(close - open_price)
        body_ratio = body / candle_range
        upper_wick = high - max(open_price, close)
        lower_wick = min(open_price, close) - low
        close_position = (close - low) / candle_range
        volume = self._number(entry_bar.get("volume")) or 0.0
        historic_volumes = [self._number(item.get("volume")) or 0.0 for item in history[:-1]]
        average_volume = sum(historic_volumes) / len(historic_volumes) if historic_volumes else 0.0
        volume_ratio = volume / average_volume if average_volume > 0 else None
        range_ratio = candle_range / average_range if average_range > 0 else None
        direction = "bull" if close > open_price else "bear" if close < open_price else "neutral"

        if range_ratio is not None and range_ratio >= 1.5 and body_ratio >= 0.6 and (
            close_position >= 0.7 or close_position <= 0.3
        ):
            label = f"{direction}_elephant"
            reason = "Wide-range body with a decisive close matches the Velez elephant-bar profile."
        elif max(upper_wick, lower_wick) / candle_range >= 0.5 and body_ratio <= 0.45:
            tail_side = "lower" if lower_wick > upper_wick else "upper"
            label = f"{tail_side}_tail_bar"
            reason = f"The {tail_side} wick dominates the bar, matching a Velez tail-bar rejection."
        elif range_ratio is not None and range_ratio <= 0.65:
            label = "narrow_range_acorn"
            reason = "Range contracted materially versus recent bars, matching the NRB/Acorn profile."
        elif body_ratio <= 0.2:
            label = "indecision_bar"
            reason = "The body is small relative to total range, so the entry bar shows indecision."
        else:
            label = f"{direction}_trend_bar"
            reason = "The bar has directional body control but does not meet elephant, tail, or NRB thresholds."

        return {
            "label": label,
            "confidence": "high" if len(history) >= 10 else "medium" if len(history) >= 5 else "low",
            "reason": reason,
            "measurements": {
                "range": round(candle_range, 6),
                "body_ratio": round(body_ratio, 4),
                "close_position": round(close_position, 4),
                "range_vs_recent": round(range_ratio, 3) if range_ratio is not None else None,
                "volume_vs_recent": round(volume_ratio, 3) if volume_ratio is not None else None,
                "direction": direction,
            },
        }

    def render_svg(self, autopsy: dict, bars: List[dict], destination: Path) -> Optional[Path]:
        valid = [
            item
            for item in bars[-60:]
            if all(self._number(item.get(key)) is not None for key in ("open", "high", "low", "close"))
        ]
        if not valid:
            return None
        destination.parent.mkdir(parents=True, exist_ok=True)
        width, height = 1200, 650
        left, right, top, bottom = 72, 28, 54, 86
        plot_width = width - left - right
        plot_height = height - top - bottom
        prices = [
            self._number(item.get(key))
            for item in valid
            for key in ("high", "low")
        ]
        prices = [value for value in prices if value is not None]
        entry = self._number(autopsy.get("decision", {}).get("entry_price"))
        stop = self._number(autopsy.get("decision", {}).get("stop_price"))
        exit_price = self._number(autopsy.get("outcome", {}).get("exit_price"))
        prices.extend(value for value in (entry, stop, exit_price) if value is not None)
        low_price, high_price = min(prices), max(prices)
        pad = max((high_price - low_price) * 0.08, high_price * 0.001, 0.01)
        low_price -= pad
        high_price += pad

        def y(value: float) -> float:
            return top + ((high_price - value) / max(high_price - low_price, 1e-9)) * plot_height

        candle_step = plot_width / max(len(valid), 1)
        candle_width = max(3.0, min(12.0, candle_step * 0.58))
        elements: List[str] = []
        for index, item in enumerate(valid):
            x = left + candle_step * index + candle_step / 2
            open_price = float(item["open"])
            high = float(item["high"])
            low = float(item["low"])
            close = float(item["close"])
            color = "#36d399" if close >= open_price else "#fb7185"
            elements.append(
                f'<line x1="{x:.2f}" y1="{y(high):.2f}" x2="{x:.2f}" y2="{y(low):.2f}" stroke="{color}" stroke-width="2"/>'
            )
            body_top = min(y(open_price), y(close))
            body_height = max(2.0, abs(y(open_price) - y(close)))
            elements.append(
                f'<rect x="{x - candle_width / 2:.2f}" y="{body_top:.2f}" width="{candle_width:.2f}" '
                f'height="{body_height:.2f}" fill="{color}" rx="1"/>'
            )

        overlays = [
            ("ENTRY", entry, "#f5c451"),
            ("STOP", stop, "#fb7185"),
            ("EXIT", exit_price, "#60a5fa"),
        ]
        for label, value, color in overlays:
            if value is None:
                continue
            line_y = y(value)
            elements.append(
                f'<line x1="{left}" y1="{line_y:.2f}" x2="{width - right}" y2="{line_y:.2f}" '
                f'stroke="{color}" stroke-width="1.5" stroke-dasharray="8 6"/>'
            )
            elements.append(
                f'<text x="{width - right - 4}" y="{line_y - 6:.2f}" fill="{color}" '
                f'text-anchor="end" font-size="15" font-weight="700">{label} {value:.4f}</text>'
            )

        for index in range(6):
            price = high_price - (high_price - low_price) * index / 5
            line_y = y(price)
            elements.append(
                f'<line x1="{left}" y1="{line_y:.2f}" x2="{width - right}" y2="{line_y:.2f}" stroke="#23324a" stroke-width="1"/>'
            )
            elements.append(
                f'<text x="{left - 10}" y="{line_y + 5:.2f}" fill="#8fa4bd" text-anchor="end" font-size="13">{price:.4f}</text>'
            )

        title = html.escape(
            f"{autopsy.get('symbol', '')} · {autopsy.get('bar_classification', {}).get('label', 'entry review')}"
        )
        subtitle = html.escape(
            f"Ref {autopsy.get('alert_ref', '')} · {autopsy.get('outcome', {}).get('status', 'closed')} · "
            f"{autopsy.get('outcome', {}).get('r_multiple', '—')}R"
        )
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            '<rect width="100%" height="100%" fill="#09111f"/>'
            f'<text x="{left}" y="28" fill="#f5f7fb" font-size="21" font-family="Inter,Arial" font-weight="700">{title}</text>'
            f'<text x="{left}" y="48" fill="#8fa4bd" font-size="13" font-family="Inter,Arial">{subtitle}</text>'
            + "".join(elements)
            + f'<text x="{left}" y="{height - 28}" fill="#8fa4bd" font-size="13" font-family="Inter,Arial">'
            "Velez Mentor entry chart · journal and connected market-data evidence only</text>"
            "</svg>"
        )
        destination.write_text(svg, encoding="utf-8")
        return destination

    def _entry_bar(self, bars: List[dict], timestamp: Any) -> Optional[dict]:
        if not bars:
            return None
        target = self._datetime(timestamp)
        if target is None:
            return bars[-1]
        parsed = [(self._datetime(item.get("timestamp")), item) for item in bars]
        prior = [item for item in parsed if item[0] is not None and item[0] <= target]
        if prior:
            return max(prior, key=lambda item: item[0])[1]
        available = [item for item in parsed if item[0] is not None]
        return min(available, key=lambda item: abs((item[0] - target).total_seconds()))[1] if available else bars[-1]

    def _setup_review(self, decision: dict, classification: dict) -> str:
        play = str(decision.get("play") or decision.get("reason") or "unclassified setup").replace("_", " ")
        location = str(decision.get("location") or "").replace("_", " ")
        classification_label = str(classification.get("label") or "unavailable").replace("_", " ")
        if location:
            return (
                f"The journal labeled this {play} at {location}; the linked entry bar classified as "
                f"{classification_label}. {classification.get('reason')}"
            )
        return (
            f"The journal labeled this {play}, but structural location was missing. The linked entry bar classified as "
            f"{classification_label}; location discipline is the first review gap."
        )

    def _risk_review(self, position: dict, decision: dict, outcome: dict) -> dict:
        entry = self._number(position.get("entry_price")) or self._number(decision.get("entry_price"))
        stop = self._number(position.get("stop_price")) or self._number(decision.get("stop_price"))
        risk = self._number(position.get("initial_risk_dollars")) or self._number(decision.get("max_dollar_risk"))
        pnl = self._number(outcome.get("pnl"))
        r_multiple = self._number(outcome.get("r_multiple"))
        defined = entry is not None and stop is not None and entry != stop
        if not defined:
            text = "A verifiable entry-to-stop risk unit was missing, so outcome quality cannot override the risk-control failure."
        else:
            result = f"{r_multiple:.2f}R" if r_multiple is not None else f"${pnl:,.2f}" if pnl is not None else "an unmeasured result"
            text = (
                f"Risk was defined from {entry:.4f} to {stop:.4f}"
                f"{f' (${risk:,.2f} planned)' if risk is not None else ''}; the closed result was {result}. "
                "This is a terminal outcome, not an open-position milestone."
            )
        return {
            "defined_risk": defined,
            "entry_price": entry,
            "stop_price": stop,
            "planned_risk": risk,
            "pnl": pnl,
            "r_multiple": r_multiple,
            "text": text,
        }

    def _lesson(self, decision: dict, classification: dict, risk: dict, outcome: dict) -> str:
        if not risk.get("defined_risk"):
            return "Rehearse entry, invalidation, per-unit risk, and total Bull Matrix risk before the next five proposals."
        if not decision.get("location"):
            return "Replay five alerts and state market location before viewing the outcome; do not promote a setup whose location was unlabeled."
        value = self._number(outcome.get("r_multiple"))
        if value is None:
            value = self._number(outcome.get("pnl"))
        if value is not None and value < 0:
            return (
                f"Classify the loss as planned or process-driven: preserve the setup only if the "
                f"{classification.get('label', 'entry bar')} and location rules were valid at entry."
            )
        return (
            f"Preserve the repeatable checks behind the {classification.get('label', 'entry')} and compare the actual exit "
            "with the original target before changing the playbook."
        )

    def _datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _number(self, value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def stable_chart_name(self, event_key: str) -> str:
        return hashlib.sha256(str(event_key).encode("utf-8")).hexdigest()[:20] + ".svg"
