"""Shared, bar-close VWAP context for Trading Bull strategy engines.

This module intentionally has no broker, network, or strategy dependency.  It
can be vendored unchanged by independently deployed bots and consumes any bar
object with ``timestamp``, ``high``, ``low``, ``close``, and ``volume`` fields.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Deque, Dict, Iterable, List, Mapping, Optional, Tuple

try:  # pragma: no cover - standard on supported Python versions.
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


ENGINE_VERSION = "shared_vwap_engine_v1"


DEFAULT_VWAP_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "bias_enabled": True,
    "scoring_enabled": True,
    "setup_confluence_enabled": True,
    "hard_filter_enabled": False,
    "session_vwap": True,
    "weekly_vwap": False,
    "anchored_vwap": False,
    "primary_variant": "session",
    "timezone": "America/New_York",
    "market_session": "equity_rth",
    "include_extended_hours": False,
    "session_open": "09:30",
    "session_close": "16:00",
    "futures_rollover_hour": 18,
    "slope_lookback": 5,
    "reclaim_confirmation_bars": 2,
    "bounce_confirmation_bars": 2,
    "score": {
        "above_vwap": 5,
        "aligned_slope": 3,
        "reclaim": 4,
        "bounce": 4,
        "rejection": 4,
        "strong_disagreement_penalty": -5,
        "flat_choppy_penalty": -3,
        "excessive_extension_penalty": -3,
    },
    "thresholds": {
        "neutral_distance_pct": 0.001,
        "compression_distance_atr": 0.20,
        "compression_distance_pct": 0.001,
        "compression_crosses": 2,
        "compression_lookback": 5,
        "extension_distance_atr": 1.50,
        "extension_distance_pct": 0.015,
        "slope_flat_atr_fraction": 0.02,
        "slope_flat_price_pct": 0.0001,
    },
    "confluence": {
        "premium_score": 12,
        "strong_score": 8,
        "moderate_score": 4,
        "conflict_score": -3,
        "relative_volume_min": 1.0,
    },
    "anchors": {},
}


def merged_vwap_config(config: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return a complete, non-mutating VWAP configuration."""

    source = dict(config or {})
    merged: Dict[str, Any] = {}
    for key, default in DEFAULT_VWAP_CONFIG.items():
        supplied = source.get(key)
        if isinstance(default, dict):
            value = dict(default)
            if isinstance(supplied, Mapping):
                value.update(supplied)
            merged[key] = value
        else:
            merged[key] = default if supplied is None else supplied
    for key, value in source.items():
        merged.setdefault(key, value)
    variant = str(merged.get("primary_variant") or "session").lower()
    merged["primary_variant"] = variant if variant in {"session", "weekly"} else "session"
    return merged


def _finite_number(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _safe_div(numerator: float, denominator: float) -> Optional[float]:
    return numerator / denominator if abs(denominator) > 1e-12 else None


def _side_value(side: Any) -> str:
    value = getattr(side, "value", side)
    return str(value or "").lower().strip()


@dataclass(frozen=True)
class ScoreContribution:
    key: str
    points: int
    reason: str


@dataclass(frozen=True)
class VWAPConfluence:
    score: int
    classification: str
    reasons: List[str]
    contributions: List[ScoreContribution]
    directional_fit: str
    setup_checks: Dict[str, bool]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "classification": self.classification,
            "reasons": list(self.reasons),
            "contributions": [asdict(item) for item in self.contributions],
            "directional_fit": self.directional_fit,
            "setup_checks": dict(self.setup_checks),
        }


@dataclass(frozen=True)
class VWAPContext:
    enabled: bool
    available: bool
    reason: Optional[str]
    timestamp: Optional[str]
    price: Optional[float]
    session_vwap: Optional[float]
    weekly_vwap: Optional[float]
    anchored_vwap: Dict[str, float]
    primary_variant: str
    primary_vwap: Optional[float]
    position: str
    slope: Optional[float]
    slope_label: str
    distance: Optional[float]
    distance_pct: Optional[float]
    distance_atr: Optional[float]
    reclaim: bool
    loss: bool
    bounce: bool
    rejection: bool
    cross_up: bool
    cross_down: bool
    compression: bool
    extension: bool
    long_alignment: bool
    short_alignment: bool
    trend_persistence: int
    confidence: float
    reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "engine_version": ENGINE_VERSION,
            "enabled": self.enabled,
            "available": self.available,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "price": self.price,
            "session_vwap": self.session_vwap,
            "weekly_vwap": self.weekly_vwap,
            "anchored_vwap": dict(self.anchored_vwap),
            "primary_variant": self.primary_variant,
            "primary_vwap": self.primary_vwap,
            "position": self.position,
            "slope": self.slope,
            "slope_label": self.slope_label,
            "distance": self.distance,
            "distance_pct": self.distance_pct,
            "distance_atr": self.distance_atr,
            "reclaim": self.reclaim,
            "loss": self.loss,
            "bounce": self.bounce,
            "rejection": self.rejection,
            "cross_up": self.cross_up,
            "cross_down": self.cross_down,
            "compression": self.compression,
            "extension": self.extension,
            "long_alignment": self.long_alignment,
            "short_alignment": self.short_alignment,
            "trend_persistence": self.trend_persistence,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
        }


@dataclass
class _AnchorState:
    timestamp: datetime
    cumulative_pv: float = 0.0
    cumulative_volume: float = 0.0


class VWAPEngine:
    """Stateful session/weekly/anchored VWAP calculator using completed bars."""

    def __init__(self, config: Optional[Mapping[str, Any]] = None) -> None:
        self.config = merged_vwap_config(config)
        self._session_key: Optional[date] = None
        self._week_key: Optional[Tuple[int, int]] = None
        self._session_pv = 0.0
        self._session_volume = 0.0
        self._weekly_pv = 0.0
        self._weekly_volume = 0.0
        self._primary_values: Deque[float] = deque(maxlen=max(int(self.config["slope_lookback"]), 2))
        self._positions: Deque[str] = deque(maxlen=max(int(self.config["thresholds"]["compression_lookback"]), 2))
        self._prev_price: Optional[float] = None
        self._prev_primary: Optional[float] = None
        self._above_streak = 0
        self._below_streak = 0
        self._reclaim_pending = False
        self._loss_pending = False
        self._bounce_armed = False
        self._rejection_armed = False
        self._anchors: Dict[str, _AnchorState] = {}
        self.last_context = self._empty_context("not_warmed")
        self._load_configured_anchors()

    def _load_configured_anchors(self) -> None:
        for name, timestamp in dict(self.config.get("anchors") or {}).items():
            if isinstance(timestamp, Mapping):
                timestamp = timestamp.get("timestamp")
            parsed = self._parse_timestamp(timestamp)
            if parsed is not None:
                self.set_anchor(str(name), parsed)

    def _parse_timestamp(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    def set_anchor(self, name: str, timestamp: datetime) -> None:
        """Start an anchored VWAP at a supplied timestamp for future bars."""

        clean = str(name or "").strip().lower().replace(" ", "_")
        if not clean:
            raise ValueError("anchor name is required")
        self._anchors[clean] = _AnchorState(timestamp=timestamp)

    def clear_anchor(self, name: str) -> None:
        self._anchors.pop(str(name or "").strip().lower().replace(" ", "_"), None)

    def anchors(self) -> Dict[str, str]:
        return {name: item.timestamp.isoformat() for name, item in self._anchors.items()}

    def _local_timestamp(self, value: datetime) -> datetime:
        if value.tzinfo is None or ZoneInfo is None:
            return value
        try:
            return value.astimezone(ZoneInfo(str(self.config["timezone"])))
        except Exception:
            return value

    def _session_identifier(self, local_dt: datetime) -> date:
        mode = str(self.config.get("market_session") or "equity_rth").lower()
        if mode == "futures":
            rollover = int(self.config.get("futures_rollover_hour") or 18)
            return local_dt.date() + timedelta(days=1) if local_dt.hour >= rollover else local_dt.date()
        return local_dt.date()

    def _is_included_session(self, local_dt: datetime) -> bool:
        mode = str(self.config.get("market_session") or "equity_rth").lower()
        if mode in {"crypto", "crypto_24x7", "24x7", "futures"} or bool(self.config.get("include_extended_hours")):
            return True
        if mode != "equity_rth":
            return True
        open_at = _clock(str(self.config.get("session_open") or "09:30"), time(9, 30))
        close_at = _clock(str(self.config.get("session_close") or "16:00"), time(16, 0))
        return open_at <= local_dt.time().replace(tzinfo=None) <= close_at

    def _empty_context(self, reason: str) -> VWAPContext:
        return VWAPContext(
            enabled=bool(self.config.get("enabled")), available=False, reason=reason,
            timestamp=None, price=None, session_vwap=None, weekly_vwap=None,
            anchored_vwap={}, primary_variant=str(self.config.get("primary_variant") or "session"),
            primary_vwap=None, position="unknown", slope=None, slope_label="unknown",
            distance=None, distance_pct=None, distance_atr=None, reclaim=False, loss=False,
            bounce=False, rejection=False, cross_up=False, cross_down=False, compression=False,
            extension=False, long_alignment=False, short_alignment=False, trend_persistence=0,
            confidence=0.0, reasons=[reason],
        )

    def update(self, bar: Any, *, atr: Optional[float] = None) -> VWAPContext:
        """Consume one completed bar and return its fully confirmed VWAP context."""

        if not bool(self.config.get("enabled")):
            self.last_context = self._empty_context("disabled")
            return self.last_context
        timestamp = getattr(bar, "timestamp", None)
        if not isinstance(timestamp, datetime):
            self.last_context = self._empty_context("missing_timestamp")
            return self.last_context
        high = _finite_number(getattr(bar, "high", None))
        low = _finite_number(getattr(bar, "low", None))
        close = _finite_number(getattr(bar, "close", None))
        volume = _finite_number(getattr(bar, "volume", None))
        if high is None or low is None or close is None:
            self.last_context = self._empty_context("missing_price")
            return self.last_context
        if volume is None or volume <= 0:
            self.last_context = self._empty_context("missing_or_zero_volume")
            return self.last_context
        local_dt = self._local_timestamp(timestamp)
        if not self._is_included_session(local_dt):
            self.last_context = self._empty_context("outside_configured_session")
            return self.last_context

        session_key = self._session_identifier(local_dt)
        week_key = local_dt.isocalendar()[:2]
        if session_key != self._session_key:
            self._session_key = session_key
            self._session_pv = 0.0
            self._session_volume = 0.0
            self._primary_values.clear()
            self._positions.clear()
            self._prev_price = None
            self._prev_primary = None
            self._above_streak = 0
            self._below_streak = 0
            self._reclaim_pending = False
            self._loss_pending = False
            self._bounce_armed = False
            self._rejection_armed = False
        if week_key != self._week_key:
            self._week_key = week_key
            self._weekly_pv = 0.0
            self._weekly_volume = 0.0

        typical_price = (high + low + close) / 3.0
        pv = typical_price * volume
        self._session_pv += pv
        self._session_volume += volume
        self._weekly_pv += pv
        self._weekly_volume += volume
        session_vwap = _safe_div(self._session_pv, self._session_volume) if self.config.get("session_vwap") else None
        weekly_vwap = _safe_div(self._weekly_pv, self._weekly_volume) if self.config.get("weekly_vwap") else None
        anchored = self._update_anchors(timestamp, pv, volume)
        primary_variant = str(self.config.get("primary_variant") or "session")
        primary = weekly_vwap if primary_variant == "weekly" and weekly_vwap is not None else session_vwap
        if primary is None:
            self.last_context = self._empty_context("vwap_variant_disabled")
            return self.last_context

        return self._build_context(
            timestamp=timestamp,
            price=close,
            high=high,
            low=low,
            primary=primary,
            session_vwap=session_vwap,
            weekly_vwap=weekly_vwap,
            anchored=anchored,
            atr=_finite_number(atr),
        )

    def _update_anchors(self, timestamp: datetime, pv: float, volume: float) -> Dict[str, float]:
        values: Dict[str, float] = {}
        if not bool(self.config.get("anchored_vwap")):
            return values
        for name, anchor in self._anchors.items():
            if timestamp < anchor.timestamp:
                continue
            anchor.cumulative_pv += pv
            anchor.cumulative_volume += volume
            value = _safe_div(anchor.cumulative_pv, anchor.cumulative_volume)
            if value is not None:
                values[name] = value
        return values

    def _build_context(
        self,
        *,
        timestamp: datetime,
        price: float,
        high: float,
        low: float,
        primary: float,
        session_vwap: Optional[float],
        weekly_vwap: Optional[float],
        anchored: Dict[str, float],
        atr: Optional[float],
    ) -> VWAPContext:
        thresholds = self.config["thresholds"]
        distance = price - primary
        distance_pct = _safe_div(distance, primary)
        distance_atr = _safe_div(distance, atr) if atr and atr > 0 else None
        neutral_pct = abs(float(thresholds["neutral_distance_pct"]))
        position = "above" if (distance_pct or 0.0) > neutral_pct else "below" if (distance_pct or 0.0) < -neutral_pct else "near"
        prior_position = self._positions[-1] if self._positions else "unknown"
        cross_up = prior_position == "below" and position == "above"
        cross_down = prior_position == "above" and position == "below"
        self._positions.append(position)
        self._primary_values.append(primary)
        slope = _safe_div(self._primary_values[-1] - self._primary_values[0], len(self._primary_values) - 1) if len(self._primary_values) >= 2 else None
        flat_threshold = (
            max(atr * float(thresholds["slope_flat_atr_fraction"]), abs(primary) * 0.00001)
            if atr is not None and atr > 0
            else abs(primary) * float(thresholds.get("slope_flat_price_pct", 0.0001))
        )
        slope_label = "rising" if slope is not None and slope > flat_threshold else "falling" if slope is not None and slope < -flat_threshold else "flat"

        if position == "above":
            self._above_streak += 1
            self._below_streak = 0
        elif position == "below":
            self._below_streak += 1
            self._above_streak = 0
        else:
            self._above_streak = 0
            self._below_streak = 0

        confirm_bars = max(int(self.config["reclaim_confirmation_bars"]), 1)
        reclaim = bool(self._reclaim_pending and self._above_streak >= confirm_bars and price > (self._prev_price or price))
        loss = bool(self._loss_pending and self._below_streak >= confirm_bars and price < (self._prev_price or price))
        self._reclaim_pending = cross_up
        self._loss_pending = cross_down

        proximity = self._is_near(distance_pct, distance_atr)
        approached_from_above = prior_position == "above" and (proximity or low <= primary)
        approached_from_below = prior_position == "below" and (proximity or high >= primary)
        bounce_bars = max(int(self.config["bounce_confirmation_bars"]), 1)
        bounce = bool(self._bounce_armed and self._above_streak >= bounce_bars and price > (self._prev_price or price))
        rejection = bool(self._rejection_armed and self._below_streak >= bounce_bars and price < (self._prev_price or price))
        self._bounce_armed = approached_from_above
        self._rejection_armed = approached_from_below

        recent_crosses = sum(1 for previous, current in zip(self._positions, list(self._positions)[1:]) if {previous, current} == {"above", "below"})
        compression = bool(proximity or (recent_crosses >= int(thresholds["compression_crosses"]) and slope_label == "flat"))
        extension = bool(
            (distance_atr is not None and abs(distance_atr) >= float(thresholds["extension_distance_atr"]))
            or (distance_pct is not None and abs(distance_pct) >= float(thresholds["extension_distance_pct"]))
        )
        long_alignment = position == "above" and slope_label == "rising" and not compression
        short_alignment = position == "below" and slope_label == "falling" and not compression
        persistence = self._above_streak if position == "above" else self._below_streak if position == "below" else 0
        confidence = 0.25
        if long_alignment or short_alignment:
            confidence = min(0.95, 0.55 + min(persistence, 5) * 0.06 + (0.08 if not extension else 0.0))
        elif position == "near" or compression:
            confidence = 0.25
        elif slope_label != "flat":
            confidence = 0.45
        reasons = self._context_reasons(position, slope_label, reclaim, loss, bounce, rejection, compression, extension)
        self._prev_price = price
        self._prev_primary = primary
        self.last_context = VWAPContext(
            enabled=True, available=True, reason=None, timestamp=timestamp.isoformat(), price=price,
            session_vwap=session_vwap, weekly_vwap=weekly_vwap, anchored_vwap=anchored,
            primary_variant=str(self.config.get("primary_variant") or "session"), primary_vwap=primary,
            position=position, slope=slope, slope_label=slope_label, distance=distance,
            distance_pct=distance_pct, distance_atr=distance_atr, reclaim=reclaim, loss=loss,
            bounce=bounce, rejection=rejection, cross_up=cross_up, cross_down=cross_down,
            compression=compression, extension=extension, long_alignment=long_alignment,
            short_alignment=short_alignment, trend_persistence=persistence, confidence=confidence,
            reasons=reasons,
        )
        return self.last_context

    def _is_near(self, distance_pct: Optional[float], distance_atr: Optional[float]) -> bool:
        thresholds = self.config["thresholds"]
        return bool(
            (distance_atr is not None and abs(distance_atr) <= float(thresholds["compression_distance_atr"]))
            or (distance_pct is not None and abs(distance_pct) <= float(thresholds["compression_distance_pct"]))
        )

    @staticmethod
    def _context_reasons(position: str, slope: str, reclaim: bool, loss: bool, bounce: bool, rejection: bool, compression: bool, extension: bool) -> List[str]:
        reasons = [f"Price is {position} primary VWAP; VWAP is {slope}."]
        if reclaim:
            reasons.append("VWAP reclaim confirmed on closed bars.")
        if loss:
            reasons.append("VWAP loss confirmed on closed bars.")
        if bounce:
            reasons.append("VWAP bounce confirmed on closed bars.")
        if rejection:
            reasons.append("VWAP rejection confirmed on closed bars.")
        if compression:
            reasons.append("Price is compressed around VWAP or repeatedly crossing it.")
        if extension:
            reasons.append("Price is extended from VWAP.")
        return reasons


def score_vwap_context(context: VWAPContext, side: Any, config: Optional[Mapping[str, Any]] = None, setup_metadata: Optional[Mapping[str, Any]] = None) -> VWAPConfluence:
    """Produce explicit, configurable VWAP confluence for an existing setup."""

    cfg = merged_vwap_config(config)
    direction = _side_value(side)
    score_cfg = cfg["score"]
    contributions: List[ScoreContribution] = []
    if not context.enabled or not context.available or not bool(cfg.get("scoring_enabled")):
        return VWAPConfluence(0, "NEUTRAL", ["VWAP scoring is disabled or unavailable."], contributions, "unknown", {})
    is_long = direction == "buy"
    is_short = direction == "sell"
    aligned_position = (is_long and context.position == "above") or (is_short and context.position == "below")
    aligned_slope = (is_long and context.slope_label == "rising") or (is_short and context.slope_label == "falling")
    opposing_position = (is_long and context.position == "below") or (is_short and context.position == "above")
    opposing_slope = (is_long and context.slope_label == "falling") or (is_short and context.slope_label == "rising")
    if bool(cfg.get("bias_enabled")) and aligned_position:
        _add(contributions, "price_position", score_cfg["above_vwap"], f"{_signed(score_cfg['above_vwap'])} price is on the {('bullish' if is_long else 'bearish')} side of VWAP")
    if bool(cfg.get("bias_enabled")) and aligned_slope:
        _add(contributions, "slope", score_cfg["aligned_slope"], f"{_signed(score_cfg['aligned_slope'])} VWAP slope confirms direction")
    if (is_long and context.reclaim) or (is_short and context.loss):
        _add(contributions, "reclaim_or_loss", score_cfg["reclaim"], f"{_signed(score_cfg['reclaim'])} confirmed VWAP {'reclaim' if is_long else 'loss'}")
    if (is_long and context.bounce) or (is_short and context.rejection):
        event_points = score_cfg["bounce"] if is_long else score_cfg["rejection"]
        _add(contributions, "bounce_or_rejection", event_points, f"{_signed(event_points)} confirmed VWAP {'bounce' if is_long else 'rejection'}")
    if bool(cfg.get("bias_enabled")) and opposing_position and opposing_slope:
        _add(contributions, "strong_disagreement", score_cfg["strong_disagreement_penalty"], f"{_signed(score_cfg['strong_disagreement_penalty'])} price and slope oppose direction")
    if context.compression or (context.position == "near" and context.slope_label == "flat"):
        _add(contributions, "compression", score_cfg["flat_choppy_penalty"], f"{_signed(score_cfg['flat_choppy_penalty'])} VWAP is flat/compressed")
    if context.extension:
        _add(contributions, "extension", score_cfg["excessive_extension_penalty"], f"{_signed(score_cfg['excessive_extension_penalty'])} price is extended from VWAP")
    total = int(sum(item.points for item in contributions))
    checks = _setup_checks(is_long, is_short, setup_metadata or {}, cfg)
    classification = _classification(total, checks, cfg) if bool(cfg.get("setup_confluence_enabled")) else "NEUTRAL"
    fit = "aligned" if aligned_position and aligned_slope else "conflict" if opposing_position and opposing_slope else "mixed"
    reasons = [item.reason for item in contributions] or ["No directional VWAP contribution."]
    return VWAPConfluence(total, classification, reasons, contributions, fit, checks)


def attach_vwap_metadata(metadata: Dict[str, Any], context: VWAPContext, side: Any, config: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Attach serializable VWAP context without changing order semantics."""

    cfg = merged_vwap_config(config)
    payload = context.as_dict()
    confluence = score_vwap_context(context, side, cfg, metadata)
    payload["score"] = confluence.score
    payload["score_reasons"] = list(confluence.reasons)
    payload["confluence"] = confluence.as_dict()
    payload["trade_management_context"] = {
        "long_vwap_loss": bool(context.loss),
        "short_vwap_reclaim": bool(context.reclaim),
        "mean_reversion_reference": context.primary_vwap,
        "advisory_only": True,
    }
    metadata["vwap"] = payload
    metadata["vwap_score"] = confluence.score
    metadata["vwap_confluence"] = confluence.classification
    metadata["vwap_score_reasons"] = list(confluence.reasons)
    metadata["vwap_alert"] = compact_vwap_alert(context, confluence)
    return metadata


def vwap_hard_filter_reason(context: VWAPContext, side: Any, config: Optional[Mapping[str, Any]] = None) -> Optional[str]:
    """Return an explicit optional-filter reason; defaults to no filtering."""

    cfg = merged_vwap_config(config)
    if not bool(cfg.get("hard_filter_enabled")) or not context.available:
        return None
    direction = _side_value(side)
    strong_opposition = (direction == "buy" and context.short_alignment) or (direction == "sell" and context.long_alignment)
    if strong_opposition:
        return "vwap_hard_filter:opposite_price_and_slope_alignment"
    return None


def compact_vwap_alert(context: VWAPContext, confluence: VWAPConfluence) -> str:
    """Compact alert/readback text; callers decide whether to send it."""

    if not context.available:
        return "VWAP: unavailable"
    distance = f"{context.distance_atr:+.2f} ATR" if context.distance_atr is not None else f"{(context.distance_pct or 0.0):+.2%}"
    event = "reclaim" if context.reclaim else "loss" if context.loss else "bounce" if context.bounce else "rejection" if context.rejection else "none"
    return f"VWAP: {context.position.title()} / {context.slope_label}; {distance}; event {event}; {confluence.classification}; score {confluence.score:+d}"


def _setup_checks(is_long: bool, is_short: bool, metadata: Mapping[str, Any], cfg: Mapping[str, Any]) -> Dict[str, bool]:
    sma20 = _finite_number(metadata.get("sma20"))
    sma200 = _finite_number(metadata.get("sma200"))
    volume_ratio = _finite_number(metadata.get("volume_ratio") or metadata.get("opening_relative_volume"))
    sma_aligned = (is_long and sma20 is not None and sma200 is not None and sma20 > sma200) or (is_short and sma20 is not None and sma200 is not None and sma20 < sma200)
    volume_aligned = volume_ratio is not None and volume_ratio >= float(cfg["confluence"]["relative_volume_min"])
    return {
        "sma_structure_aligned": sma_aligned,
        "relative_volume_aligned": volume_aligned,
        "existing_play_present": bool(metadata.get("play") or metadata.get("base_play")),
    }


def _classification(score: int, checks: Mapping[str, bool], cfg: Mapping[str, Any]) -> str:
    levels = cfg["confluence"]
    if score <= int(levels["conflict_score"]):
        return "VWAP CONFLICT"
    if score >= int(levels["premium_score"]) and all(checks.values()):
        return "PREMIUM VWAP CONFLUENCE"
    if score >= int(levels["strong_score"]):
        return "STRONG VWAP CONFLUENCE"
    if score >= int(levels["moderate_score"]):
        return "MODERATE VWAP CONFLUENCE"
    return "NEUTRAL"


def _add(items: List[ScoreContribution], key: str, points: Any, reason: str) -> None:
    value = int(points or 0)
    if value:
        items.append(ScoreContribution(key=key, points=value, reason=reason))


def _signed(value: Any) -> str:
    number = int(value or 0)
    return f"{number:+d}"


def _clock(value: str, fallback: time) -> time:
    try:
        hour, minute = value.split(":", 1)
        return time(int(hour), int(minute))
    except (TypeError, ValueError):
        return fallback
