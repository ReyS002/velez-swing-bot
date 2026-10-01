from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Deque, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - keeps the strategy portable if zoneinfo is unavailable.
    ZoneInfo = None

from . import velez_doctrine as doctrine
from .indicators import RollingATR, RollingSMA, RollingSlope
from .types import Bar, OrderType, Signal, Side
from .utils import safe_div
from .vwap_engine import VWAPEngine, VWAPContext, attach_vwap_metadata, vwap_hard_filter_reason


class VelezPlay(str, Enum):
    ELEPHANT = "elephant_bar"
    BULL_180 = "bull_180"
    BEAR_180 = "bear_180"
    BOTTOMING_TAIL = "bottoming_tail"
    TOPPING_TAIL = "topping_tail"
    BUY_SETUP = "velez_buy_setup"
    SELL_SETUP = "velez_sell_setup"
    NRB_ACORN = "nrb_acorn"
    COLOR_CHANGE_ADD = "color_change_add"
    FAB4_TRAP_BREAKOUT = "fab4_trap_breakout"
    FAILED_NEW_HIGH = "failed_new_high"
    FAILED_NEW_LOW = "failed_new_low"
    OPENING_GAP_GO = "opening_gap_go"
    OPENING_GAP_FADE = "opening_gap_fade"
    TIME_SPACE_BREAKOUT = "time_space_breakout"


class VelezLocation(str, Enum):
    NEAR_20 = "location_1_near_20_sma"
    EXTENDED_20 = "location_2_extended_from_20_sma"
    NEAR_200 = "location_3_near_200_sma"


@dataclass(frozen=True)
class CandleShape:
    body: float
    range: float
    upper_wick: float
    lower_wick: float
    body_midpoint: float
    bullish: bool
    bearish: bool


@dataclass(frozen=True)
class LocationAssessment:
    locations: List[VelezLocation]
    near_20: bool
    extended_above_20: bool
    extended_below_20: bool
    near_200: bool
    sma20: Optional[float]
    sma200: Optional[float]
    sma20_slope: Optional[float]
    sma200_slope: Optional[float]
    distance_to_sma20_pct: Optional[float]

    @property
    def actionable(self) -> bool:
        return bool(self.locations)


@dataclass
class OpeningGapState:
    session_date: Optional[object] = None
    prior_close: Optional[float] = None
    first_open: Optional[float] = None
    first_high: Optional[float] = None
    first_low: Optional[float] = None
    first_close: Optional[float] = None
    gap_direction: Optional[str] = None
    gap_pct: Optional[float] = None
    bars_seen: int = 0
    last_minutes_since_open: Optional[int] = None
    go_used: bool = False
    fade_used: bool = False
    breakout_used: bool = False


@dataclass
class VelezContext:
    sma20: RollingSMA
    sma200: RollingSMA
    sma20_slope: RollingSlope
    sma200_slope: RollingSlope
    atr: RollingATR
    vwap: VWAPEngine
    bars: Deque[Bar]
    bodies: Deque[float]
    volumes: Deque[float]
    prev_sma20: Optional[float] = None
    prev_sma200: Optional[float] = None
    prev_close: Optional[float] = None
    last_location: Optional[LocationAssessment] = None
    last_vwap: Optional[VWAPContext] = None
    color_add_used: Dict[str, bool] = field(default_factory=lambda: {"buy": False, "sell": False})
    opening_gap: OpeningGapState = field(default_factory=OpeningGapState)
    # 20 SMA history for the doctrine's slant read (now / 5 bars ago / 10 bars ago).
    sma20_hist: Deque[Optional[float]] = field(default_factory=lambda: deque(maxlen=2 * doctrine.SLOPE_LOOKBACK + 1))
    # Event-bar setups waiting for a later bar to break them, keyed by side.
    armed: Dict[str, dict] = field(default_factory=dict)
    last_market_state: Optional[dict] = None


@dataclass(frozen=True)
class PyramidDecision:
    allowed: bool
    qty: int
    reason: str
    metadata: Dict[str, object] = field(default_factory=dict)


def candle_shape(bar: Bar) -> CandleShape:
    body = abs(bar.close - bar.open)
    bar_range = max(bar.high - bar.low, 0.0)
    upper = max(bar.high - max(bar.open, bar.close), 0.0)
    lower = max(min(bar.open, bar.close) - bar.low, 0.0)
    return CandleShape(
        body=body,
        range=bar_range,
        upper_wick=upper,
        lower_wick=lower,
        body_midpoint=(bar.open + bar.close) / 2.0,
        bullish=bar.close > bar.open,
        bearish=bar.close < bar.open,
    )


# A day opening this far from the prior close is a split or bad print, not volatility.
DAILY_DISCONTINUITY_PCT = 0.30


def daily_rows_before(rows: List[dict], day) -> List[dict]:
    """Completed daily rows (rulebook dicts, oldest first) labeled before trading date `day`."""
    out = []
    for row in rows or []:
        label = doctrine.daily_bar_date(row.get("t")) if row.get("t") is not None else None
        if label is not None and label < day:
            out.append(row)
    return out


def split_safe_daily_rows(rows: List[dict]) -> List[dict]:
    """Daily rows after the latest split-sized gap (a split is not volatility).

    Rows already adjusted for splits (`split_adjusted`) are kept whole: a big gap there is a
    real move (earnings, news), and dropping the history would blind the ATR rules for weeks.
    """
    rows = list(rows)
    if rows and all(row.get("split_adjusted") for row in rows):
        return rows
    for i in range(len(rows) - 1, 0, -1):
        prior_close = rows[i - 1]["c"]
        if prior_close and abs(rows[i]["o"] / prior_close - 1.0) > DAILY_DISCONTINUITY_PCT:
            return rows[i:]
    return rows


def session_overlap_bars(bars: List[dict], as_of=None, spacing_seconds: Optional[float] = None) -> List[dict]:
    """Today's regular-session bars, including a bar that starts before 09:30 and ends after it.

    Hourly feeds label the 09:30-10:00 aggregate 09:00; the rulebook's session_bars() filters
    on the start timestamp and would drop the opening range. `spacing_seconds` defaults to the
    median spacing of the last bars.
    """
    stamps = [b for b in bars or [] if b.get("t") is not None]
    if not stamps:
        return []
    if spacing_seconds is None:
        recent = stamps[-6:]
        gaps = sorted((b["t"] - a["t"]).total_seconds() for a, b in zip(recent, recent[1:]) if b["t"] > a["t"])
        spacing_seconds = gaps[len(gaps) // 2] if gaps else 0.0
    last = doctrine._local(as_of or stamps[-1]["t"])
    if last is None:
        return []
    open_dt = datetime.combine(last.date(), doctrine.SESSION_OPEN, tzinfo=last.tzinfo)
    close_dt = datetime.combine(last.date(), doctrine.SESSION_CLOSE, tzinfo=last.tzinfo)
    out = []
    for b in stamps:
        start = doctrine._local(b["t"])
        if start is None or start.date() != last.date() or start > last or start >= close_dt:
            continue
        if start >= open_dt or start + timedelta(seconds=spacing_seconds) > open_dt:
            out.append(b)
    return out


def session_high_low_overlap(bars: List[dict], as_of=None) -> tuple:
    """Today's regular-session high and low, counting a bar that straddles the open."""
    today = session_overlap_bars(bars, as_of)
    if not today:
        return None, None
    return max(b["h"] for b in today), min(b["l"] for b in today)


def utc_daily_rows(bars: List[dict], before) -> List[dict]:
    """Daily rows aggregated by UTC date from intraday or daily bars (non-equities trade around the
    clock), keeping the days before `before`."""
    rows: List[dict] = []
    for b in sorted((b for b in bars or [] if b.get("t") is not None), key=lambda b: b["t"]):
        t = b["t"] if b["t"].tzinfo else b["t"].replace(tzinfo=timezone.utc)
        day = t.astimezone(timezone.utc).date()
        if day >= before:
            continue
        if rows and rows[-1]["_day"] == day:
            row = rows[-1]
            row.update(h=max(row["h"], b["h"]), l=min(row["l"], b["l"]), c=b["c"])
        else:
            # Crypto and futures have no share splits: every gap in their history is real.
            rows.append({"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": 0.0, "_day": day,
                         "split_adjusted": True, "t": datetime(day.year, day.month, day.day, tzinfo=timezone.utc)})
    for row in rows:
        row.pop("_day", None)
    return rows


def daily_atr_from_rows(rows: List[dict]) -> Optional[float]:
    """The rulebook's daily ATR from completed daily rows, or None without a full reading.

    A full ATR needs DAILY_ATR_PERIOD + 1 rows after the latest split-sized gap; a partial
    average never arms a rule.
    """
    rows = split_safe_daily_rows(rows)
    if len(rows) <= doctrine.DAILY_ATR_PERIOD:
        return None
    return doctrine.atr(rows[-(doctrine.DAILY_ATR_PERIOD + 1):], doctrine.DAILY_ATR_PERIOD)


class VelezInstitutionalStrategy:
    """Oliver Velez candle-play engine with strict SMA location gating."""

    def __init__(self, config: dict, logger=None) -> None:
        self.config = config
        self.logger = logger
        self.symbols: Dict[str, VelezContext] = {}
        # Index bars (SPY/QQQ) for the market-bias rule; fed by the scanner, never traded.
        self.market_bars: Dict[str, List[dict]] = {}
        # Configured futures/FX/crypto symbols: the equity session windows don't apply.
        self.non_equity_symbols: set = set()
        # Completed daily bars for the daily-range rule (rulebook 2026.10.5), as rulebook dicts.
        # Set by the live server; None in backtests and replays, where the rule is not enforced.
        self.daily_bars_provider: Optional[Callable[[str], List[dict]]] = None
        # Today's regular-session bars from the live feed, so the day's extremes survive a short
        # local history (1-minute bars roll the open out by midday) and bare alerts are measured.
        self.session_bars_provider: Optional[Callable[[str], List[dict]]] = None
        self._validate_setup_allowlist()

    def _get_context(self, symbol: str) -> VelezContext:
        if symbol in self.symbols:
            return self.symbols[symbol]

        cfg = self.config
        history = max(
            cfg.get("sma_slow", 200),
            cfg.get("history_bars", 220),
            cfg.get("elephant", {}).get("body_lookback", 5) + 5,
        )
        ctx = VelezContext(
            sma20=RollingSMA(cfg.get("sma_fast", 20)),
            sma200=RollingSMA(cfg.get("sma_slow", 200)),
            sma20_slope=RollingSlope(cfg.get("slope_lookback", 5)),
            sma200_slope=RollingSlope(cfg.get("slope_lookback", 5)),
            atr=RollingATR(cfg.get("atr_period", 14)),
            vwap=VWAPEngine(cfg.get("vwap", {})),
            bars=deque(maxlen=history),
            bodies=deque(maxlen=history),
            volumes=deque(maxlen=history),
        )
        self.symbols[symbol] = ctx
        return ctx

    def on_bar(self, symbol: str, bar: Bar) -> List[Signal]:
        ctx = self._get_context(symbol)
        shape = candle_shape(bar)

        sma20 = ctx.sma20.update(bar.close)
        sma200 = ctx.sma200.update(bar.close)
        slope20 = ctx.sma20_slope.update(sma20)
        slope200 = ctx.sma200_slope.update(sma200)
        atr = ctx.atr.update(bar)
        vwap = ctx.vwap.update(bar, atr=atr)
        ctx.last_vwap = vwap
        location = self._assess_location(bar, sma20, sma200, slope20, slope200, atr)
        ctx.last_location = location
        ctx.sma20_hist.append(sma20)
        self._update_opening_gap_state(ctx, bar)

        signals: List[Signal] = []
        signals.extend(self._opening_gap_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._time_space_breakout_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._elephant_bar_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._one_eighty_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._tail_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._failed_breakout_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._color_change_add_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._buy_sell_setup_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._nrb_acorn_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._fab4_trap_signals(symbol, bar, shape, ctx, location, atr))
        # Before prioritisation, deliberately: _prioritized_signals keeps only
        # one signal per side, so filtering afterwards would let a disallowed
        # play suppress an allowed one that would otherwise have fired.
        signals = self._setup_allowlist_filter(signals)
        signals = self._prioritized_signals(signals)
        signals = [
            signal for signal in signals
            if vwap_hard_filter_reason(vwap, signal.side, self.config.get("vwap", {})) is None
        ]
        for signal in signals:
            attach_vwap_metadata(signal.metadata, vwap, signal.side, self.config.get("vwap", {}))
        if self._doctrine_enabled():
            signals = self._apply_doctrine(symbol, bar, ctx, location, atr, signals)

        ctx.prev_close = bar.close
        ctx.prev_sma20 = sma20
        ctx.prev_sma200 = sma200
        ctx.bars.append(bar)
        ctx.bodies.append(shape.body)
        ctx.volumes.append(bar.volume)
        return signals

    def indicator_snapshot(self, symbol: str) -> dict:
        ctx = self.symbols.get(symbol)
        if ctx is None:
            return {}
        return {
            "sma_fast": ctx.prev_sma20,
            "sma_slow": ctx.prev_sma200,
            "atr": ctx.atr.atr,
            "location": ctx.last_location,
            "vwap": ctx.last_vwap.as_dict() if ctx.last_vwap is not None else {},
            "market_state": ctx.last_market_state,
        }

    # ---- Velez doctrine: the rules every entry must pass ----
    #
    # These are the owner's non-negotiables (see CLAUDE.md). They run after the
    # play detectors, so a detector can never trade around them:
    #   * the 200 SMA is a veto, never a trigger;
    #   * no trend (continuation) entries in the wide state -- the climax;
    #   * exhausting elephants are exits, not entries;
    #   * event-bar plays enter on the BREAK of the event bar, never its close.

    def _doctrine_cfg(self) -> dict:
        return self.config.get("doctrine") or {}

    def _doctrine_enabled(self) -> bool:
        return bool(self._doctrine_cfg().get("enabled", True))

    def _slope_label(self, slope: Optional[float]) -> Optional[str]:
        if slope is None:
            return None
        if self._slope_is_rising(slope):
            return "rising"
        if self._slope_is_declining(slope):
            return "falling"
        return "flat"

    def _doctrine_market_state(self, ctx: VelezContext, bar: Bar, location: LocationAssessment, atr: Optional[float]) -> dict:
        cfg = self._doctrine_cfg()
        hist = list(ctx.sma20_hist)
        lb = doctrine.SLOPE_LOOKBACK
        now = hist[-1] if hist else None
        mid = hist[-1 - lb] if len(hist) > lb else None
        old = hist[-1 - 2 * lb] if len(hist) > 2 * lb else None
        slant = doctrine.slant_from_smas(now, mid, old, atr)
        state = None
        spread_pct = None
        if location.sma20 is not None and location.sma200 is not None:
            spread_pct = abs(location.sma20 - location.sma200) / max(bar.close, 1e-9)
            state = doctrine.classify_state(
                spread_pct,
                slant,
                narrow_pct=float(cfg.get("narrow_state_pct", doctrine.NARROW_STATE_PCT)),
                wide_pct=float(cfg.get("wide_state_pct", doctrine.WIDE_STATE_PCT)),
            )
        result = {
            "state": state,
            "state_rule": doctrine.MARKET_STATES.get(state or "", {}).get("velez_action_rule"),
            "sma_spread_pct": spread_pct,
            "sma20_slant": slant,
            "atr": atr,
        }
        ctx.last_market_state = result
        return result

    def _doctrine_gate(
        self,
        signal: Signal,
        bar: Bar,
        location: LocationAssessment,
        market: dict,
        event_open: Optional[float] = None,
        decision_at: Optional[datetime] = None,
        entry_at: Optional[float] = None,
    ) -> dict:
        """`decision_at` overrides the entry time (a bare alert is judged when it arrives, not at the cached bar).
        `entry_at` is the planned entry price when it isn't the bar's close (a limit at the breakout level)."""
        play = str(signal.metadata.get("play") or signal.reason)
        # Three-finger spread: stretch from the 20 SMA in ATR. Event-bar plays are measured from the
        # event bar's open (an igniting elephant leaving the 20 is not a chase); plays that fire
        # immediately are measured where they fill, at the bar's close.
        if event_open is not None:
            ref = event_open
        elif play in doctrine.EVENT_BAR_PLAYS:
            ref = bar.open
        else:
            ref = bar.close
        ext, ext_side = doctrine.extension_atr(ref, location.sma20, market.get("atr"))
        return doctrine.entry_gate(
            "long" if signal.side == Side.BUY else "short",
            play,
            price=bar.close,
            sma200=location.sma200,
            sma200_slope=self._slope_label(location.sma200_slope),
            state=market.get("state"),
            near_200=location.near_200,
            elephant_origin=signal.metadata.get("elephant_origin_class"),
            metadata=signal.metadata,
            extension_atr=ext,
            extension_side=ext_side,
            decision_time=(
                (decision_at if self._session_applies(signal.symbol) else None)
                if decision_at is not None else self._decision_time(signal.symbol, bar)
            ),
            market_bias=self._market_bias(signal.symbol, decision_at or bar.timestamp),
            range_used=self._range_used(signal, bar, decision_at, entry_at),
        )

    # ── Daily range used (rulebook 2026.10.5) ──

    def _range_used(
        self,
        signal: Signal,
        bar: Optional[Bar],
        decision_at: Optional[datetime] = None,
        entry_at: Optional[float] = None,
    ) -> Optional[float]:
        """Daily ATRs today's move has covered in the signal's direction, for the entry gate.

        Today's high and low come from the local bars and, live, from the session feed (the
        local history can be too short to hold the open). Without a bar (a bare alert) the
        price is the feed's latest. None (not enforced) when the rule is off, for non-equities,
        without a live daily-bar source, or when the daily ATR or today's session can't be read.
        `range_block` moves the veto: the value is scaled so the rulebook's 1.0 lands on it.
        """
        cfg = self._doctrine_cfg()
        if not cfg.get("daily_range", False) or self.daily_bars_provider is None:
            return None
        symbol = str(signal.symbol).upper()
        if not self._is_equity(symbol):
            return None
        at = decision_at or (bar.timestamp if bar is not None else None)
        local = doctrine._local(at) if at is not None else None
        if local is None:
            return None
        try:
            rows = self.daily_bars_provider(symbol) or []
        except Exception:
            return None
        atr_value = daily_atr_from_rows(daily_rows_before(rows, local.date()))
        if not atr_value:
            return None
        highs: List[float] = []
        lows: List[float] = []
        ctx = self.symbols.get(signal.symbol) or self.symbols.get(symbol)
        intraday = [doctrine.bar_dict(b) for b in ctx.bars] if ctx is not None else []
        if bar is not None:
            current = doctrine.bar_dict(bar)
            if not intraday or intraday[-1]["t"] != current["t"]:
                intraday.append(current)
        price = bar.close if bar is not None else None
        if decision_at is not None:
            # A bare alert is judged where it would enter: its proposed price, else the freshest
            # close in the local bars or the session feed (the cached chart bar can be an hour old).
            try:
                proposed = float(signal.metadata.get("entry_price") or 0)
            except (TypeError, ValueError):
                proposed = 0.0
            price = proposed if proposed > 0 else None
        feeds = [intraday]
        if self.session_bars_provider is not None:
            try:
                feeds.append(list(self.session_bars_provider(symbol) or []))
            except Exception:
                pass
        freshest = None
        for series in feeds:
            if not series:
                continue
            high, low = session_high_low_overlap(series, as_of=at)
            if high is None:
                continue
            highs.append(high)
            lows.append(low)
            today = session_overlap_bars(series, as_of=at)
            if today and (freshest is None or today[-1]["t"] > freshest["t"]):
                freshest = today[-1]
        if price is None and freshest is not None:
            price = freshest["c"]
        if entry_at is not None and entry_at > 0:
            price = entry_at  # the planned entry (a limit at the breakout level), not where the bar closed
        if price is None or not highs:
            return None
        side = "long" if signal.side == Side.BUY else "short"
        # The unrounded ratio: 0.996 has not covered the daily ATR yet.
        used = doctrine.daily_range_used(atr_value, max(highs), min(lows), price, side).get("used_in_direction_raw")
        if used is None:
            return None
        block = float(cfg.get("range_block", doctrine.RANGE_USED_BLOCK) or doctrine.RANGE_USED_BLOCK)
        return used * doctrine.RANGE_USED_BLOCK / block if block > 0 else None

    # ── Session windows and trading with the market (rulebook 2026.10.1) ──

    def update_market_index(self, symbol: str, bars: List[Bar]) -> None:
        """Feed index bars (SPY/QQQ) used only for the market bias. They never generate signals."""
        self.market_bars[str(symbol).upper()] = [doctrine.bar_dict(b) for b in bars]

    def set_symbol_types(self, symbols: List[dict]) -> None:
        """Record which configured symbols are not equities (type future/forex/crypto/...)."""
        self.non_equity_symbols = {
            str(item.get("symbol") or "").upper()
            for item in symbols or []
            if str(item.get("type") or item.get("asset_type") or "equity").lower() not in {"equity", "stock", "etf"}
        }

    def _market_indexes(self) -> List[str]:
        return [str(s).upper() for s in self._doctrine_cfg().get("market_indexes", ["SPY", "QQQ"])]

    def _market_bias(self, symbol: str, as_of: Optional[datetime]) -> Optional[str]:
        """long / short / none from SPY/QQQ, using only index bars at or before `as_of`.

        None (rule off, or the symbol is itself an index) and "unknown" (no index data)
        are not enforced by the gate.
        """
        if not self._doctrine_cfg().get("market_bias", False) or str(symbol).upper() in self._market_indexes():
            return None
        series = []
        for index in self._market_indexes():
            bars = self.market_bars.get(index)
            if bars is None:
                ctx = self.symbols.get(index)
                bars = [doctrine.bar_dict(b) for b in ctx.bars] if ctx is not None else []
            if as_of is not None:
                try:
                    bars = [b for b in bars if b["t"] is None or b["t"] <= as_of]
                except TypeError:  # naive vs aware timestamps: use what we have
                    pass
                # A stale series (a feed outage) must not keep steering entries: treat it as missing.
                try:
                    if bars and bars[-1]["t"] is not None and as_of - bars[-1]["t"] > timedelta(days=4):
                        bars = []
                except TypeError:
                    pass
            series.append(bars[-300:])
        return doctrine.market_bias(*series)["bias"]

    def _context_free_gate(self, signal: Signal, at: datetime) -> dict:
        """Session windows and market bias for a signal on a symbol with no bar context."""
        play = str(signal.metadata.get("play") or signal.reason)
        return doctrine.entry_gate(
            "long" if signal.side == Side.BUY else "short",
            play,
            price=0.0,
            sma200=None,
            sma200_slope=None,
            state=None,
            near_200=False,
            metadata=signal.metadata,
            decision_time=at if self._session_applies(signal.symbol) else None,
            market_bias=self._market_bias(signal.symbol, at),
            range_used=self._range_used(signal, None, at),
        )

    def _session_applies(self, symbol: str) -> bool:
        """Session windows are for equities; configured futures/FX/crypto are exempt."""
        if not self._doctrine_cfg().get("session_windows", False):
            return False
        return self._is_equity(symbol)

    def _is_equity(self, symbol: str) -> bool:
        """US equities only: configured futures/FX/crypto (and their ticker shapes) are not."""
        sym = str(symbol).upper()
        configured = {str(s).upper() for s in self._doctrine_cfg().get("non_equity_symbols", [])} | self.non_equity_symbols
        # Broker aliases drop the separator (EURUSD for EUR/USD, BTCUSD for BTC/USD): compare without it.
        canonical = {c.replace("/", "").replace("-", "") for c in configured}
        if sym.replace("/", "").replace("-", "") in canonical:
            return False
        return not (sym in configured or "/" in sym or sym.startswith("^") or sym.endswith(("=F", "=X", "-USD")))


    def _decision_time(self, symbol: str, bar: Bar) -> Optional[datetime]:
        """When an entry off this bar would be taken (its close), for the session windows.

        None (not enforced) for non-equities and for daily or longer bars.
        """
        if not self._session_applies(symbol):
            return None
        ctx = self.symbols.get(symbol)
        history = [b for b in list(ctx.bars)[-6:] if b.timestamp < bar.timestamp] if ctx is not None else []
        # The rulebook's decision_time: bar close from the spacing, capped at the 16:00 bell.
        return doctrine.decision_time([doctrine.bar_dict(b) for b in history + [bar]])

    def _needs_break(self, signal: Signal) -> bool:
        """Event-bar plays at MARKET wait for the break. A Velez 50% limit entry is already a planned entry."""
        if not self._doctrine_cfg().get("break_of_event_bar", True):
            return False
        play = str(signal.metadata.get("play") or signal.reason)
        order_type = str(signal.metadata.get("order_type") or OrderType.MARKET.value)
        return play in doctrine.EVENT_BAR_PLAYS and order_type == OrderType.MARKET.value

    def admit_external(self, symbol: str, signals: List[Signal], bar: Optional[Bar] = None) -> List[Signal]:
        """Run signals produced outside on_bar (extensions, TradingView alerts) through the same doctrine.

        With `bar` (the event bar just processed by on_bar), event-bar plays are
        armed for the break exactly like engine signals. Without it (a bare
        alert), the hard gates still apply whenever this engine has seen the
        symbol; otherwise the signal is tagged unverified.
        """
        if not signals or not self._doctrine_enabled():
            return signals
        ctx = self.symbols.get(symbol)
        # A bare alert (no bar) is judged at the moment it arrives.
        received = None if bar is not None else datetime.now(timezone.utc)
        if ctx is None or ctx.last_location is None or not ctx.bars:
            # No chart context: the 200/state/spread gates can't run, but the session
            # windows and the market bias don't need the stock's bars.
            kept: List[Signal] = []
            for signal in signals:
                gate = self._context_free_gate(signal, received or bar.timestamp)
                signal.metadata["doctrine"] = {"version": doctrine.DOCTRINE_VERSION, "verified": False,
                                               "reason": "no_bar_context_for_symbol", **gate}
                if not gate["allowed"]:
                    self._log_doctrine("doctrine_entry_blocked", signal, gate["reasons"])
                    continue
                kept.append(signal)
            return kept
        location = ctx.last_location
        market = ctx.last_market_state or {}
        price_bar = bar or ctx.bars[-1]
        out: List[Signal] = []
        for signal in signals:
            gate = self._doctrine_gate(signal, price_bar, location, market, decision_at=received)
            signal.metadata["doctrine"] = {"version": doctrine.DOCTRINE_VERSION, "verified": True, **gate,
                                           "market_state": market}
            if not gate["allowed"]:
                self._log_doctrine("doctrine_entry_blocked", signal, gate["reasons"])
                continue
            if bar is not None and self._needs_break(signal) and signal.metadata.get("stop_price") is not None:
                side = signal.side.value
                ctx.armed[side] = {
                    "signal": signal,
                    "trigger": doctrine.break_trigger(
                        "long" if signal.side == Side.BUY else "short", bar.high, bar.low, self._tick_size(symbol)
                    ),
                    "event_open": bar.open,
                    "event_high": bar.high,
                    "event_low": bar.low,
                    "bars_left": int(self._doctrine_cfg().get("trigger_window_bars", 1)),
                    "armed_at": bar.timestamp,
                }
                self._log_doctrine("doctrine_setup_armed", signal, [f"trigger={ctx.armed[side]['trigger']}"])
                continue
            out.append(signal)
        return out

    def _apply_doctrine(
        self,
        symbol: str,
        bar: Bar,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
        signals: List[Signal],
    ) -> List[Signal]:
        market = self._doctrine_market_state(ctx, bar, location, atr)
        out = self._fire_armed(symbol, bar, ctx, location, market, atr)
        for signal in signals:
            gate = self._doctrine_gate(signal, bar, location, market)
            signal.metadata["doctrine"] = {"version": doctrine.DOCTRINE_VERSION, **gate, "market_state": market}
            if not gate["allowed"]:
                self._log_doctrine("doctrine_entry_blocked", signal, gate["reasons"])
                continue
            if self._needs_break(signal):
                side = signal.side.value
                ctx.armed[side] = {
                    "signal": signal,
                    "trigger": doctrine.break_trigger(
                        "long" if signal.side == Side.BUY else "short", bar.high, bar.low, self._tick_size(symbol)
                    ),
                    "event_open": bar.open,
                    "event_high": bar.high,
                    "event_low": bar.low,
                    "bars_left": int(self._doctrine_cfg().get("trigger_window_bars", 1)),
                    "armed_at": bar.timestamp,
                }
                self._log_doctrine("doctrine_setup_armed", signal, [f"trigger={ctx.armed[side]['trigger']}"])
                continue
            out.append(signal)
        return self._prioritized_signals(out)

    def _fire_armed(
        self,
        symbol: str,
        bar: Bar,
        ctx: VelezContext,
        location: LocationAssessment,
        market: dict,
        atr: Optional[float],
    ) -> List[Signal]:
        fired: List[Signal] = []
        for side_key, armed in list(ctx.armed.items()):
            original: Signal = armed["signal"]
            long = original.side == Side.BUY
            stop = float(original.metadata["stop_price"])
            trigger = float(armed["trigger"])
            broke = bar.high >= trigger if long else bar.low <= trigger
            invalidated = bar.low <= stop if long else bar.high >= stop
            if invalidated:
                # Stop traded before (or with) the break: the setup failed. No entry.
                del ctx.armed[side_key]
                self._log_doctrine("doctrine_setup_invalidated", original, ["stop_traded_before_break"])
                continue
            if not broke:
                armed["bars_left"] -= 1
                if armed["bars_left"] <= 0:
                    del ctx.armed[side_key]
                    self._log_doctrine("doctrine_setup_expired", original, ["no_break_within_window"])
                continue
            del ctx.armed[side_key]
            max_chase = float(self._doctrine_cfg().get("max_chase_atr", 0.25)) * float(atr or 0.0)
            chase = abs(bar.close - trigger)
            if chase <= max(max_chase, self._tick_size(symbol)):
                order_type, entry_price, limit_price = OrderType.MARKET, bar.close, None
            else:
                # Price already ran past the break: don't chase, bid the breakout level.
                order_type, entry_price, limit_price = OrderType.LIMIT, trigger, trigger
            gate = self._doctrine_gate(
                original, bar, location, market, event_open=armed.get("event_open"), entry_at=entry_price
            )
            if not gate["allowed"]:
                self._log_doctrine("doctrine_entry_blocked", original, gate["reasons"])
                continue
            metadata = dict(original.metadata)
            metadata.update(
                {
                    "entry_type": "break_of_event_bar",
                    "event_bar_high": armed["event_high"],
                    "event_bar_low": armed["event_low"],
                    "event_bar_timestamp": armed["armed_at"],
                    "trigger_price": trigger,
                    "order_type": order_type.value,
                    "entry_price": entry_price,
                    "limit_price": limit_price,
                    "chased": chase > max_chase,
                    "close": bar.close,
                    "timestamp": bar.timestamp,
                    "management_plan": self._management_plan(original.side, entry_price, stop),
                    "doctrine": {"version": doctrine.DOCTRINE_VERSION, **gate, "market_state": market},
                }
            )
            fired.append(Signal(symbol=symbol, side=original.side, reason=original.reason, metadata=metadata))
        return fired

    def _log_doctrine(self, event: str, signal: Signal, reasons: List[str]) -> None:
        if self.logger is None:
            return
        try:
            from .utils import log_event

            log_event(self.logger, event, {
                "symbol": signal.symbol,
                "side": signal.side.value,
                "play": signal.metadata.get("play") or signal.reason,
                "reasons": reasons,
            })
        except Exception:  # pragma: no cover - logging must never break signal flow.
            pass

    def _assess_location(
        self,
        bar: Bar,
        sma20: Optional[float],
        sma200: Optional[float],
        slope20: Optional[float],
        slope200: Optional[float],
        atr: Optional[float],
    ) -> LocationAssessment:
        near_pct = self.config.get("near_sma_pct", 0.0025)
        near_atr_mult = self.config.get("near_sma_atr_mult", 0.35)
        extended_pct = self.config.get("extended_sma_pct", 0.012)
        extended_atr_mult = self.config.get("extended_sma_atr_mult", 1.0)

        def near_sma(sma: Optional[float]) -> bool:
            if sma is None:
                return False
            pct_ok = abs(bar.close - sma) / max(bar.close, 1e-9) <= near_pct
            atr_ok = atr is not None and abs(bar.close - sma) <= near_atr_mult * atr
            touched = bar.low <= sma <= bar.high
            return pct_ok or atr_ok or touched

        near20 = near_sma(sma20)
        near200 = near_sma(sma200)

        extended_above = False
        extended_below = False
        distance_pct: Optional[float] = None
        if sma20 is not None:
            distance = bar.close - sma20
            distance_pct = safe_div(distance, sma20)
            pct_extended = abs(distance_pct) >= extended_pct
            atr_extended = atr is not None and abs(distance) >= extended_atr_mult * atr
            if pct_extended or atr_extended:
                extended_above = distance > 0
                extended_below = distance < 0

        locations: List[VelezLocation] = []
        if near20:
            locations.append(VelezLocation.NEAR_20)
        if extended_above or extended_below:
            locations.append(VelezLocation.EXTENDED_20)
        if near200:
            locations.append(VelezLocation.NEAR_200)

        return LocationAssessment(
            locations=locations,
            near_20=near20,
            extended_above_20=extended_above,
            extended_below_20=extended_below,
            near_200=near200,
            sma20=sma20,
            sma200=sma200,
            sma20_slope=slope20,
            sma200_slope=slope200,
            distance_to_sma20_pct=distance_pct,
        )

    def _opening_gap_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("opening_gap", {})
        if not cfg.get("enabled", True) or not location.actionable:
            return []

        state = ctx.opening_gap
        if not self._opening_state_ready(state):
            return []
        if state.last_minutes_since_open is None or state.last_minutes_since_open > cfg.get("opening_window_minutes", 15):
            return []
        if state.bars_seen > cfg.get("max_signal_bars", 3):
            return []
        gap_pct = float(state.gap_pct or 0.0)
        if abs(gap_pct) < cfg.get("min_gap_pct", 0.003):
            return []
        if abs(gap_pct) > cfg.get("max_gap_pct", 0.08):
            return []

        first_range = max(float(state.first_high or 0.0) - float(state.first_low or 0.0), 0.0)
        if first_range <= 0:
            return []
        close_pos = safe_div(bar.close - float(state.first_low), first_range)
        close_weak_pos = safe_div(float(state.first_high) - bar.close, first_range)
        upper_rejection = safe_div(shape.upper_wick, shape.range)
        lower_rejection = safe_div(shape.lower_wick, shape.range)
        min_close_pos = cfg.get("first_bar_close_position_pct", 0.65)
        rejection_pct = cfg.get("fade_rejection_wick_pct", 0.35)
        gap_fill_space_pct = cfg.get("min_gap_fill_space_pct", 0.002)

        signals: List[Signal] = []
        gap_up = gap_pct > 0
        go_metrics = self._time_space_metrics(ctx, bar, state, location, atr, Side.BUY if gap_up else Side.SELL, cfg)
        if not state.go_used and go_metrics["clean_space"] and go_metrics["score"] >= cfg.get("min_time_space_score", 0.65):
            if gap_up:
                first_bar_control = state.bars_seen == 1 and shape.bullish and close_pos >= min_close_pos
                opening_range_break = state.bars_seen > 1 and shape.bullish and bar.close > float(state.first_high)
                if first_bar_control or opening_range_break:
                    state.go_used = True
                    signals.append(
                        self._build_signal(
                            symbol=symbol,
                            side=Side.BUY,
                            play=VelezPlay.OPENING_GAP_GO,
                            bar=bar,
                            shape=shape,
                            location=location,
                            stop_price=self._stop_below(symbol, min(float(state.first_low), bar.low)),
                            trigger_price=float(state.first_high),
                            metadata=self._opening_metadata("gap_and_go", state, go_metrics, atr),
                        )
                    )
            else:
                first_bar_control = state.bars_seen == 1 and shape.bearish and close_weak_pos >= min_close_pos
                opening_range_break = state.bars_seen > 1 and shape.bearish and bar.close < float(state.first_low)
                if first_bar_control or opening_range_break:
                    state.go_used = True
                    signals.append(
                        self._build_signal(
                            symbol=symbol,
                            side=Side.SELL,
                            play=VelezPlay.OPENING_GAP_GO,
                            bar=bar,
                            shape=shape,
                            location=location,
                            stop_price=self._stop_above(symbol, max(float(state.first_high), bar.high)),
                            trigger_price=float(state.first_low),
                            metadata=self._opening_metadata("gap_and_go", state, go_metrics, atr),
                        )
                    )
        if signals:
            return signals

        if state.fade_used:
            return []

        if gap_up:
            fill_space = safe_div(bar.close - float(state.prior_close), bar.close)
            fade_context = location.extended_above_20 or location.near_200 or not go_metrics["clean_space"]
            fade_trigger = shape.bearish and (bar.close < float(state.first_open) or upper_rejection >= rejection_pct or close_weak_pos >= min_close_pos)
            if fade_context and fade_trigger and fill_space >= gap_fill_space_pct:
                state.fade_used = True
                metrics = self._time_space_metrics(ctx, bar, state, location, atr, Side.SELL, cfg)
                signals.append(
                    self._build_signal(
                        symbol=symbol,
                        side=Side.SELL,
                        play=VelezPlay.OPENING_GAP_FADE,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_above(symbol, max(float(state.first_high), bar.high)),
                        trigger_price=float(state.first_open),
                        metadata=self._opening_metadata("gap_fade_to_prior_close", state, metrics, atr),
                    )
                )
        else:
            fill_space = safe_div(float(state.prior_close) - bar.close, bar.close)
            fade_context = location.extended_below_20 or location.near_200 or not go_metrics["clean_space"]
            fade_trigger = shape.bullish and (bar.close > float(state.first_open) or lower_rejection >= rejection_pct or close_pos >= min_close_pos)
            if fade_context and fade_trigger and fill_space >= gap_fill_space_pct:
                state.fade_used = True
                metrics = self._time_space_metrics(ctx, bar, state, location, atr, Side.BUY, cfg)
                signals.append(
                    self._build_signal(
                        symbol=symbol,
                        side=Side.BUY,
                        play=VelezPlay.OPENING_GAP_FADE,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_below(symbol, min(float(state.first_low), bar.low)),
                        trigger_price=float(state.first_open),
                        metadata=self._opening_metadata("gap_fade_to_prior_close", state, metrics, atr),
                    )
                )

        return signals

    def _time_space_breakout_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("time_space", {})
        if not cfg.get("enabled", True) or not (location.near_20 or location.near_200):
            return []
        state = ctx.opening_gap
        if not self._opening_state_ready(state):
            return []
        if state.breakout_used:
            return []
        if state.bars_seen < cfg.get("min_bars_after_open", 2) or state.bars_seen > cfg.get("max_signal_bars", 6):
            return []
        if state.last_minutes_since_open is None or state.last_minutes_since_open > cfg.get("opening_window_minutes", 30):
            return []
        if abs(float(state.gap_pct or 0.0)) >= cfg.get("max_neutral_gap_pct", 0.003):
            return []

        if shape.bullish and bar.close > float(state.first_high) and self._bullish_ma_context(location):
            metrics = self._time_space_metrics(ctx, bar, state, location, atr, Side.BUY, cfg)
            if metrics["clean_space"] and metrics["score"] >= cfg.get("min_time_space_score", 0.65):
                state.breakout_used = True
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.BUY,
                        play=VelezPlay.TIME_SPACE_BREAKOUT,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_below(symbol, min(float(state.first_low), bar.low)),
                        trigger_price=float(state.first_high),
                        metadata=self._opening_metadata("opening_range_time_space_breakout", state, metrics, atr),
                    )
                ]

        if shape.bearish and bar.close < float(state.first_low) and self._bearish_ma_context(location):
            metrics = self._time_space_metrics(ctx, bar, state, location, atr, Side.SELL, cfg)
            if metrics["clean_space"] and metrics["score"] >= cfg.get("min_time_space_score", 0.65):
                state.breakout_used = True
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.SELL,
                        play=VelezPlay.TIME_SPACE_BREAKOUT,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_above(symbol, max(float(state.first_high), bar.high)),
                        trigger_price=float(state.first_low),
                        metadata=self._opening_metadata("opening_range_time_space_breakout", state, metrics, atr),
                    )
                ]
        return []

    def _elephant_bar_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("elephant", {})
        if not cfg.get("enabled", True) or not location.actionable:
            return []

        lookback = cfg.get("body_lookback", 5)
        # Velez classifies elephant bars by where they ORIGINATE relative to the
        # 20 SMA, and only some of those classes are entries. See
        # _elephant_origin_class(). Default "any" preserves live behaviour.
        location_mode = str(cfg.get("location_mode", "any"))
        if len(ctx.bodies) < lookback or len(ctx.bars) < lookback:
            return []
        avg_body = sum(list(ctx.bodies)[-lookback:]) / lookback
        if avg_body <= 0 or shape.body < cfg.get("min_body_mult", 1.8) * avg_body:
            return []
        if shape.range <= 0:
            return []
        max_each_wick_pct = cfg.get("max_each_wick_pct", 0.2)
        max_total_wick_pct = cfg.get("max_total_wick_pct", 0.35)
        if shape.upper_wick / shape.range > max_each_wick_pct:
            return []
        if shape.lower_wick / shape.range > max_each_wick_pct:
            return []
        if (shape.upper_wick + shape.lower_wick) / shape.range > max_total_wick_pct:
            return []

        prior = list(ctx.bars)[-cfg.get("structure_lookback", 5) :]
        prior_high = max(b.high for b in prior)
        prior_low = min(b.low for b in prior)
        bullish_cross = self._crosses_ma_up(bar, ctx, location)
        bearish_cross = self._crosses_ma_down(bar, ctx, location)

        origin_class = self._elephant_origin_class(bar, shape, ctx, location, atr, cfg)
        if location_mode == "igniting" and origin_class != "igniting":
            return []
        if location_mode == "exclude_exhaustion" and origin_class == "exhausting":
            return []

        if shape.bullish and (bar.close > prior_high or bullish_cross):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.ELEPHANT,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, bar.low),
                    trigger_price=prior_high,
                    force_limit=self._is_climactic(shape, avg_body, atr, cfg),
                    metadata={
                        "avg_body": avg_body,
                        "body_mult": safe_div(shape.body, avg_body),
                        "prior_high": prior_high,
                        "prior_low": prior_low,
                        "elephant_origin_class": origin_class,
                        "atr": atr,
                    },
                )
            ]

        if shape.bearish and (bar.close < prior_low or bearish_cross):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.ELEPHANT,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, bar.high),
                    trigger_price=prior_low,
                    force_limit=self._is_climactic(shape, avg_body, atr, cfg),
                    metadata={
                        "avg_body": avg_body,
                        "body_mult": safe_div(shape.body, avg_body),
                        "prior_high": prior_high,
                        "prior_low": prior_low,
                        "elephant_origin_class": origin_class,
                        "atr": atr,
                    },
                )
            ]

        return []

    def _one_eighty_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("one_eighty", {})
        if not cfg.get("enabled", True) or len(ctx.bars) < 1:
            return []

        # A 180 is an exhaustion reversal. Velez puts reversals where price is
        # *extended away* from the 20 SMA, or rejecting a major average like the
        # 200 -- not sitting in the trap zone on the 20, which is where a
        # pullback continuation (Location 1) belongs. Firing both from the same
        # near-MA gate makes the two setups the same trade wearing two names.
        #
        # "near_ma" is the shipped behaviour and stays the default.
        mode = str(cfg.get("location_mode", "near_ma"))
        if mode == "near_ma":
            if not (location.near_20 or location.near_200):
                return []
        elif mode == "extended":
            if not (location.extended_above_20 or location.extended_below_20):
                return []
        elif mode == "extended_or_200":
            if not (
                location.extended_above_20
                or location.extended_below_20
                or location.near_200
            ):
                return []
        else:
            raise ValueError(f"unknown one_eighty.location_mode: {mode!r}")

        prev = ctx.bars[-1]
        prev_shape = candle_shape(prev)
        if prev_shape.body <= 0 or shape.body <= 0:
            return []

        recover_pct = cfg.get("recover_pct", 0.8)
        sequence_low = min(prev.low, bar.low)
        sequence_high = max(prev.high, bar.high)

        if prev_shape.bearish and shape.bullish:
            recovery_mark = prev.close + (prev.open - prev.close) * recover_pct
            actual_recovery = safe_div(bar.close - prev.close, prev.open - prev.close)
            if bar.close >= recovery_mark and self._one_eighty_context(location, Side.BUY, mode):
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.BUY,
                        play=VelezPlay.BULL_180,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_below(symbol, sequence_low),
                        trigger_price=recovery_mark,
                        metadata={
                            "bar1_open": prev.open,
                            "bar1_close": prev.close,
                            "recovery_mark": recovery_mark,
                            "recovery_pct": actual_recovery,
                            "atr": atr,
                        },
                    )
                ]

        if prev_shape.bullish and shape.bearish:
            recovery_mark = prev.close - (prev.close - prev.open) * recover_pct
            actual_recovery = safe_div(prev.close - bar.close, prev.close - prev.open)
            if bar.close <= recovery_mark and self._one_eighty_context(location, Side.SELL, mode):
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.SELL,
                        play=VelezPlay.BEAR_180,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_above(symbol, sequence_high),
                        trigger_price=recovery_mark,
                        metadata={
                            "bar1_open": prev.open,
                            "bar1_close": prev.close,
                            "recovery_mark": recovery_mark,
                            "recovery_pct": actual_recovery,
                            "atr": atr,
                        },
                    )
                ]

        return []

    def _tail_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("tail", {})
        if not cfg.get("enabled", True) or shape.range <= 0:
            return []

        tail_pct = cfg.get("min_tail_pct", 0.66)
        declined = self._multi_bar_decline(ctx, cfg.get("trend_bars", 3))
        rallied = self._multi_bar_rally(ctx, cfg.get("trend_bars", 3))

        continuation_ok = bool(cfg.get("continuation_at_20", True))
        if shape.lower_wick / shape.range >= tail_pct:
            valid_location = (declined and location.extended_below_20) or (
                location.near_200 and self._slope_is_rising(location.sma200_slope)
            )
            if not valid_location and continuation_ok and location.near_20 and self._bull_trend(location) and self._slope_is_rising(location.sma20_slope):
                # Velez's bread-and-butter tail: a pullback rejected at a rising 20.
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.BUY,
                        play=VelezPlay.BOTTOMING_TAIL,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_below(symbol, bar.low),
                        trigger_price=bar.high,
                        force_limit=cfg.get("prefer_tail_limit", True),
                        limit_price=bar.low + shape.lower_wick * 0.5,
                        metadata={"tail_pct": shape.lower_wick / shape.range, "atr": atr,
                                  "setup_family": "continuation", "tail_context": "pullback_to_rising_20"},
                    )
                ]
            if valid_location:
                limit_price = bar.low + shape.lower_wick * 0.5
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.BUY,
                        play=VelezPlay.BOTTOMING_TAIL,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_below(symbol, bar.low),
                        trigger_price=bar.close,
                        force_limit=cfg.get("prefer_tail_limit", True),
                        limit_price=limit_price,
                        metadata={"tail_pct": shape.lower_wick / shape.range, "atr": atr},
                    )
                ]

        if shape.upper_wick / shape.range >= tail_pct:
            valid_location = (rallied and location.extended_above_20) or (
                location.near_200 and self._slope_is_declining(location.sma200_slope)
            )
            if not valid_location and continuation_ok and location.near_20 and self._bear_trend(location) and self._slope_is_declining(location.sma20_slope):
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.SELL,
                        play=VelezPlay.TOPPING_TAIL,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_above(symbol, bar.high),
                        trigger_price=bar.low,
                        force_limit=cfg.get("prefer_tail_limit", True),
                        limit_price=bar.high - shape.upper_wick * 0.5,
                        metadata={"tail_pct": shape.upper_wick / shape.range, "atr": atr,
                                  "setup_family": "continuation", "tail_context": "rally_to_falling_20"},
                    )
                ]
            if valid_location:
                limit_price = bar.high - shape.upper_wick * 0.5
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.SELL,
                        play=VelezPlay.TOPPING_TAIL,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_above(symbol, bar.high),
                        trigger_price=bar.close,
                        force_limit=cfg.get("prefer_tail_limit", True),
                        limit_price=limit_price,
                        metadata={"tail_pct": shape.upper_wick / shape.range, "atr": atr},
                    )
                ]

        return []

    def _buy_sell_setup_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("buy_sell_setup", {})
        if not cfg.get("enabled", True) or len(ctx.bars) < cfg.get("pullback_bars", 2):
            return []
        if shape.body <= 0 or not (location.near_20 or location.near_200):
            return []

        lookback = cfg.get("pullback_bars", 2)
        recent = list(ctx.bars)[-lookback:]
        prior_high = max(item.high for item in recent)
        prior_low = min(item.low for item in recent)
        pulled_back = self._recent_pullback(recent)
        pushed_up = self._recent_pushup(recent)

        if (
            self._bull_trend(location)
            and pulled_back
            and shape.bullish
            and (bar.close > prior_high or (location.sma20 is not None and bar.close > location.sma20))
        ):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.BUY_SETUP,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, min(prior_low, bar.low)),
                    trigger_price=prior_high,
                    metadata={
                        "pullback_bars": lookback,
                        "prior_high": prior_high,
                        "prior_low": prior_low,
                        "atr": atr,
                    },
                )
            ]

        if (
            self._bear_trend(location)
            and pushed_up
            and shape.bearish
            and (bar.close < prior_low or (location.sma20 is not None and bar.close < location.sma20))
        ):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.SELL_SETUP,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, max(prior_high, bar.high)),
                    trigger_price=prior_low,
                    metadata={
                        "pullback_bars": lookback,
                        "prior_high": prior_high,
                        "prior_low": prior_low,
                        "atr": atr,
                    },
                )
            ]
        return []

    def _nrb_acorn_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("nrb_acorn", {})
        lookback = cfg.get("range_lookback", 7)
        if not cfg.get("enabled", True) or not location.actionable or len(ctx.bars) < max(2, lookback):
            return []

        prev = ctx.bars[-1]
        prev_range = max(prev.high - prev.low, 0.0)
        ranges = [max(item.high - item.low, 0.0) for item in list(ctx.bars)[-lookback:]]
        avg_range = sum(ranges) / len(ranges) if ranges else 0.0
        range_ok = avg_range > 0 and prev_range <= cfg.get("max_range_mult", 0.65) * avg_range
        atr_ok = atr is not None and prev_range <= cfg.get("max_atr_mult", 0.55) * atr
        if not (range_ok or atr_ok):
            return []

        if self._bull_trend(location) and bar.close > prev.high and shape.bullish:
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.NRB_ACORN,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, prev.low),
                    trigger_price=prev.high,
                    metadata={"nrb_range": prev_range, "avg_range": avg_range, "atr": atr},
                )
            ]
        if self._bear_trend(location) and bar.close < prev.low and shape.bearish:
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.NRB_ACORN,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, prev.high),
                    trigger_price=prev.low,
                    metadata={"nrb_range": prev_range, "avg_range": avg_range, "atr": atr},
                )
            ]
        return []

    def _color_change_add_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("color_change", {})
        if not cfg.get("enabled", True) or len(ctx.bars) < 1:
            return []
        prev = ctx.bars[-1]
        prev_shape = candle_shape(prev)
        if prev_shape.body <= 0 or shape.body <= 0:
            return []

        if not self._bull_trend(location):
            ctx.color_add_used["buy"] = False
        if not self._bear_trend(location):
            ctx.color_add_used["sell"] = False

        if (
            not ctx.color_add_used.get("buy", False)
            and self._bull_trend(location)
            and (location.near_20 or location.near_200)
            and prev_shape.bearish
            and shape.bullish
            and bar.close > prev.high
        ):
            ctx.color_add_used["buy"] = True
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.COLOR_CHANGE_ADD,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, min(prev.low, bar.low)),
                    trigger_price=prev.high,
                    metadata=self._color_add_metadata("buy", atr),
                )
            ]

        if (
            not ctx.color_add_used.get("sell", False)
            and self._bear_trend(location)
            and (location.near_20 or location.near_200)
            and prev_shape.bullish
            and shape.bearish
            and bar.close < prev.low
        ):
            ctx.color_add_used["sell"] = True
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.COLOR_CHANGE_ADD,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, max(prev.high, bar.high)),
                    trigger_price=prev.low,
                    metadata=self._color_add_metadata("sell", atr),
                )
            ]
        return []

    def _fab4_trap_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("fab4", {})
        lookback = cfg.get("breakout_lookback", 5)
        if not cfg.get("enabled", True) or not location.actionable or len(ctx.bars) < lookback:
            return []
        if location.sma20 is None or location.sma200 is None:
            return []

        sma_spread_pct = abs(location.sma20 - location.sma200) / max(bar.close, 1e-9)
        compressed_sma = sma_spread_pct <= cfg.get("max_sma_spread_pct", 0.006)
        compressed_atr = atr is not None and abs(location.sma20 - location.sma200) <= cfg.get("max_sma_spread_atr_mult", 0.65) * atr
        if not (compressed_sma or compressed_atr):
            return []

        recent = list(ctx.bars)[-lookback:]
        prior_high = max(item.high for item in recent)
        prior_low = min(item.low for item in recent)
        zone_range = prior_high - prior_low
        range_ok = atr is None or zone_range <= cfg.get("max_zone_atr_mult", 3.0) * atr
        if not range_ok:
            return []

        if shape.bullish and bar.close > prior_high and self._slope_is_flat_or_rising(location.sma20_slope):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.FAB4_TRAP_BREAKOUT,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, prior_low),
                    trigger_price=prior_high,
                    metadata={
                        "sma_spread_pct": sma_spread_pct,
                        "zone_range": zone_range,
                        "atr": atr,
                    },
                )
            ]
        if shape.bearish and bar.close < prior_low and self._slope_is_flat_or_declining(location.sma20_slope):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.FAB4_TRAP_BREAKOUT,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, prior_high),
                    trigger_price=prior_low,
                    metadata={
                        "sma_spread_pct": sma_spread_pct,
                        "zone_range": zone_range,
                        "atr": atr,
                    },
                )
            ]
        return []

    def _failed_breakout_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("failed_breakout", {})
        lookback = cfg.get("structure_lookback", 10)
        if not cfg.get("enabled", True) or len(ctx.bars) < lookback or shape.range <= 0:
            return []

        recent = list(ctx.bars)[-lookback:]
        prior_high = max(item.high for item in recent)
        prior_low = min(item.low for item in recent)
        upper_rejection = shape.upper_wick / shape.range >= cfg.get("min_rejection_wick_pct", 0.35)
        lower_rejection = shape.lower_wick / shape.range >= cfg.get("min_rejection_wick_pct", 0.35)

        high_extended = (
            location.sma20 is not None
            and (bar.high - location.sma20) / max(location.sma20, 1e-9) >= self.config.get("extended_sma_pct", 0.012)
        )
        failed_high_context = high_extended or location.extended_above_20 or (location.near_200 and self._slope_is_flat_or_declining(location.sma200_slope))
        if bar.high > prior_high and bar.close < prior_high and (shape.bearish or upper_rejection) and failed_high_context:
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.FAILED_NEW_HIGH,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, bar.high),
                    trigger_price=prior_high,
                    metadata={
                        "prior_high": prior_high,
                        "failed_breakout": "new_high",
                        "rejection_wick_pct": shape.upper_wick / shape.range,
                        "atr": atr,
                    },
                )
            ]

        low_extended = (
            location.sma20 is not None
            and (location.sma20 - bar.low) / max(location.sma20, 1e-9) >= self.config.get("extended_sma_pct", 0.012)
        )
        failed_low_context = low_extended or location.extended_below_20 or (location.near_200 and self._slope_is_flat_or_rising(location.sma200_slope))
        if bar.low < prior_low and bar.close > prior_low and (shape.bullish or lower_rejection) and failed_low_context:
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.FAILED_NEW_LOW,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, bar.low),
                    trigger_price=prior_low,
                    metadata={
                        "prior_low": prior_low,
                        "failed_breakout": "new_low",
                        "rejection_wick_pct": shape.lower_wick / shape.range,
                        "atr": atr,
                    },
                )
            ]
        return []

    def _update_opening_gap_state(self, ctx: VelezContext, bar: Bar) -> OpeningGapState:
        state = ctx.opening_gap
        local_dt = self._local_timestamp(bar.timestamp)
        session_date = local_dt.date()
        if state.session_date != session_date:
            prior_close = ctx.prev_close
            if prior_close is None and ctx.bars:
                prior_close = ctx.bars[-1].close
            ctx.opening_gap = OpeningGapState(session_date=session_date, prior_close=prior_close)
            state = ctx.opening_gap

        minutes_since_open = self._minutes_since_open(local_dt)
        if minutes_since_open < 0:
            return state

        window = max(
            int(self.config.get("opening_gap", {}).get("opening_window_minutes", 15)),
            int(self.config.get("time_space", {}).get("opening_window_minutes", 30)),
        )
        if minutes_since_open > window:
            return state

        if state.bars_seen == 0:
            state.first_open = bar.open
            state.first_high = bar.high
            state.first_low = bar.low
            state.first_close = bar.close
        state.bars_seen += 1
        state.last_minutes_since_open = minutes_since_open

        if state.prior_close:
            state.gap_pct = safe_div(float(state.first_open or bar.open) - float(state.prior_close), float(state.prior_close))
            if state.gap_pct > 0:
                state.gap_direction = "up"
            elif state.gap_pct < 0:
                state.gap_direction = "down"
            else:
                state.gap_direction = "flat"
        return state

    def _opening_state_ready(self, state: OpeningGapState) -> bool:
        return all(
            value is not None
            for value in (
                state.prior_close,
                state.first_open,
                state.first_high,
                state.first_low,
                state.first_close,
                state.gap_pct,
            )
        )

    def _time_space_metrics(
        self,
        ctx: VelezContext,
        bar: Bar,
        state: OpeningGapState,
        location: LocationAssessment,
        atr: Optional[float],
        side: Side,
        cfg: dict,
    ) -> dict:
        prior_bars = self._prior_session_bars(ctx, state.session_date, cfg.get("structure_lookback", 30))
        prior_high = max((item.high for item in prior_bars), default=None)
        prior_low = min((item.low for item in prior_bars), default=None)
        min_space_pct = cfg.get("min_clean_space_pct", 0.004)
        breakout_bonus_pct = cfg.get("breakout_space_bonus_pct", min_space_pct * 1.5)

        if side == Side.BUY:
            obstacle_price = prior_high
            if obstacle_price is None or bar.close >= obstacle_price:
                clean_space_pct = breakout_bonus_pct
                clean_space = True
            else:
                clean_space_pct = safe_div(obstacle_price - bar.close, bar.close)
                clean_space = clean_space_pct >= min_space_pct
            gap_fill_space_pct = abs(safe_div(bar.close - float(state.prior_close or bar.close), bar.close))
        else:
            obstacle_price = prior_low
            if obstacle_price is None or bar.close <= obstacle_price:
                clean_space_pct = breakout_bonus_pct
                clean_space = True
            else:
                clean_space_pct = safe_div(bar.close - obstacle_price, bar.close)
                clean_space = clean_space_pct >= min_space_pct
            gap_fill_space_pct = abs(safe_div(float(state.prior_close or bar.close) - bar.close, bar.close))

        minutes = max(int(state.last_minutes_since_open or 0), 0)
        window = max(float(cfg.get("opening_window_minutes", 15) or 15), 1.0)
        time_score = max(0.0, 1.0 - min(minutes / window, 1.0))
        space_score = min(max(safe_div(clean_space_pct, min_space_pct), 0.0), 1.0) if min_space_pct > 0 else 1.0
        gap_score = min(abs(float(state.gap_pct or 0.0)) / max(float(cfg.get("target_gap_pct", 0.01) or 0.01), 1e-9), 1.0)
        location_score = 1.0 if (location.near_20 or location.near_200) else 0.7 if location.extended_above_20 or location.extended_below_20 else 0.0
        atr_score = 0.0
        first_range = abs(float(state.first_high or 0.0) - float(state.first_low or 0.0))
        if atr and atr > 0 and first_range > 0:
            atr_score = min(first_range / atr, 1.0)
        score = (time_score * 0.25) + (space_score * 0.35) + (gap_score * 0.15) + (location_score * 0.2) + (atr_score * 0.05)

        return {
            "score": round(score, 4),
            "time_score": round(time_score, 4),
            "space_score": round(space_score, 4),
            "gap_score": round(gap_score, 4),
            "location_score": round(location_score, 4),
            "clean_space": bool(clean_space),
            "clean_space_pct": round(clean_space_pct, 6),
            "gap_fill_space_pct": round(gap_fill_space_pct, 6),
            "obstacle_price": obstacle_price,
            "prior_structure_high": prior_high,
            "prior_structure_low": prior_low,
        }

    def _opening_metadata(self, variant: str, state: OpeningGapState, metrics: dict, atr: Optional[float]) -> dict:
        return {
            "setup_family": "opening_gap_time_space",
            "play_variant": variant,
            "prior_close": state.prior_close,
            "gap_direction": state.gap_direction,
            "gap_pct": state.gap_pct,
            "gap_fill_price": state.prior_close,
            "first_open": state.first_open,
            "first_high": state.first_high,
            "first_low": state.first_low,
            "first_close": state.first_close,
            "opening_bars_seen": state.bars_seen,
            "minutes_since_open": state.last_minutes_since_open,
            "time_space_score": metrics.get("score"),
            "time_score": metrics.get("time_score"),
            "space_score": metrics.get("space_score"),
            "clean_space": metrics.get("clean_space"),
            "clean_space_pct": metrics.get("clean_space_pct"),
            "gap_fill_space_pct": metrics.get("gap_fill_space_pct"),
            "obstacle_price": metrics.get("obstacle_price"),
            "prior_structure_high": metrics.get("prior_structure_high"),
            "prior_structure_low": metrics.get("prior_structure_low"),
            "atr": atr,
        }

    def _prior_session_bars(self, ctx: VelezContext, session_date: object, lookback: int) -> List[Bar]:
        selected = [
            item
            for item in ctx.bars
            if self._local_timestamp(item.timestamp).date() != session_date
        ]
        if not selected:
            selected = list(ctx.bars)
        return selected[-max(int(lookback or 1), 1) :]

    def _local_timestamp(self, value: datetime) -> datetime:
        if value.tzinfo is None or ZoneInfo is None:
            return value
        tz_name = str(self.config.get("timezone") or self.config.get("session_timezone") or "America/New_York")
        if tz_name == "US/Eastern":
            tz_name = "America/New_York"
        try:
            return value.astimezone(ZoneInfo(tz_name))
        except Exception:
            return value

    def _minutes_since_open(self, local_dt: datetime) -> int:
        cfg = self.config.get("opening_gap", {})
        open_hour = int(cfg.get("session_open_hour", 9))
        open_minute = int(cfg.get("session_open_minute", 30))
        return (local_dt.hour * 60 + local_dt.minute) - (open_hour * 60 + open_minute)

    def _build_signal(
        self,
        *,
        symbol: str,
        side: Side,
        play: VelezPlay,
        bar: Bar,
        shape: CandleShape,
        location: LocationAssessment,
        stop_price: float,
        trigger_price: float,
        force_limit: bool = False,
        limit_price: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> Signal:
        order_type = OrderType.MARKET
        selected_limit = limit_price
        no_chase_pct = self.config.get("entry", {}).get("no_chase_body_pct", 0.05)
        chase_distance = abs(bar.close - trigger_price)
        chased = shape.body > 0 and chase_distance > (no_chase_pct * shape.body)
        if force_limit or chased:
            order_type = OrderType.LIMIT
            if selected_limit is None:
                selected_limit = shape.body_midpoint

        payload = {
            "play": play.value,
            "entry_price": bar.close if order_type == OrderType.MARKET else selected_limit,
            "stop_price": stop_price,
            "trigger_price": trigger_price,
            "order_type": order_type.value,
            "limit_price": selected_limit,
            "chased": chased,
            "location": [loc.value for loc in location.locations],
            "event_candle_body": shape.body,
            "event_candle_range": shape.range,
            "body_range_pct": safe_div(shape.body, shape.range),
            "upper_wick_pct": safe_div(shape.upper_wick, shape.range),
            "lower_wick_pct": safe_div(shape.lower_wick, shape.range),
            "sma20": location.sma20,
            "sma200": location.sma200,
            "sma20_slope": location.sma20_slope,
            "sma200_slope": location.sma200_slope,
            "distance_to_sma20_pct": location.distance_to_sma20_pct,
            "close": bar.close,
            "timestamp": bar.timestamp,
            "management_plan": self._management_plan(side, bar.close if order_type == OrderType.MARKET else selected_limit, stop_price),
        }
        if metadata:
            payload.update(metadata)

        return Signal(
            symbol=symbol,
            side=side,
            reason=play.value,
            metadata=payload,
        )

    def _crosses_ma_up(self, bar: Bar, ctx: VelezContext, location: LocationAssessment) -> bool:
        if ctx.prev_close is None:
            return False
        crossed20 = (
            ctx.prev_sma20 is not None
            and ctx.prev_close <= ctx.prev_sma20
            and bar.close > ctx.prev_sma20
            and self._slope_is_flat_or_rising(location.sma20_slope)
        )
        crossed200 = (
            ctx.prev_sma200 is not None
            and ctx.prev_close <= ctx.prev_sma200
            and bar.close > ctx.prev_sma200
            and self._slope_is_flat_or_rising(location.sma200_slope)
        )
        return crossed20 or crossed200

    def _crosses_ma_down(self, bar: Bar, ctx: VelezContext, location: LocationAssessment) -> bool:
        if ctx.prev_close is None:
            return False
        crossed20 = (
            ctx.prev_sma20 is not None
            and ctx.prev_close >= ctx.prev_sma20
            and bar.close < ctx.prev_sma20
            and self._slope_is_flat_or_declining(location.sma20_slope)
        )
        crossed200 = (
            ctx.prev_sma200 is not None
            and ctx.prev_close >= ctx.prev_sma200
            and bar.close < ctx.prev_sma200
            and self._slope_is_flat_or_declining(location.sma200_slope)
        )
        return crossed20 or crossed200

    def _elephant_origin_class(
        self,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
        cfg: dict,
    ) -> str:
        """Classify an elephant bar the way Velez does: by where it BEGINS.

        Velez splits wide-range bars into three kinds, and they are not the
        same trade:

        * **igniting** -- originates at or near the 20 SMA and starts a new
          move. This is the one he takes; follow-through is expected.
        * **continuation** -- originates away from the 20 SMA but early, after
          an igniting bar. Momentum continues.
        * **exhausting** -- originates far from the 20 SMA *after a move that
          has already been underway*. This is the final push and it commonly
          precedes a reversal. Buying it is taking the wrong side.

        The distinction is the bar's ORIGIN, not its close. That matters here
        because ``_assess_location`` measures ``bar.close``: a textbook igniting
        elephant opens on the average and closes far above it, so the shared
        location assessment labels it ``extended_above_20`` -- the exhaustion
        signature -- purely because of its own body. Measuring the open (and
        allowing a bar whose range straddles the average) restores the
        distinction Velez actually draws.
        """
        sma20 = location.sma20
        if sma20 is None:
            return "unknown"

        near_mult = float(cfg.get("origin_near_atr_mult", 0.5))
        band = near_mult * atr if atr is not None else abs(sma20) * float(
            self.config.get("near_sma_pct", 0.0025)
        )
        origin = bar.open
        straddles = bar.low <= sma20 <= bar.high
        if straddles or abs(origin - sma20) <= band:
            return "igniting"

        run_bars = int(cfg.get("exhaustion_run_bars", 3))
        if shape.bullish and origin > sma20 and self._multi_bar_rally(ctx, run_bars):
            return "exhausting"
        if shape.bearish and origin < sma20 and self._multi_bar_decline(ctx, run_bars):
            return "exhausting"
        return "continuation"

    def _is_climactic(self, shape: CandleShape, avg_body: float, atr: Optional[float], cfg: dict) -> bool:
        if avg_body > 0 and shape.body >= cfg.get("climactic_body_mult", 3.0) * avg_body:
            return True
        return atr is not None and shape.range >= cfg.get("climactic_atr_mult", 2.2) * atr

    def _bullish_ma_context(self, location: LocationAssessment) -> bool:
        if location.near_20 and self._slope_is_flat_or_rising(location.sma20_slope):
            return True
        return location.near_200 and self._slope_is_flat_or_rising(location.sma200_slope)

    def _bearish_ma_context(self, location: LocationAssessment) -> bool:
        if location.near_20 and self._slope_is_flat_or_declining(location.sma20_slope):
            return True
        return location.near_200 and self._slope_is_flat_or_declining(location.sma200_slope)

    def _one_eighty_context(
        self, location: LocationAssessment, side: Side, mode: str
    ) -> bool:
        """Directional context for a 180 reversal under the selected location mode.

        In ``near_ma`` this is the shipped behaviour verbatim. In the extended
        modes the direction check inverts, and has to: a reversal *up* is taken
        when price is stretched **below** the average and exhausting, not when
        it is stretched above it. Reusing ``_bullish_ma_context`` there would
        also never fire, because that helper itself requires a near-MA location.
        """
        if mode == "near_ma":
            return (
                self._bullish_ma_context(location)
                if side == Side.BUY
                else self._bearish_ma_context(location)
            )

        if side == Side.BUY:
            if location.extended_below_20:
                return True
            return mode == "extended_or_200" and location.near_200 and self._slope_is_flat_or_rising(
                location.sma200_slope
            )

        if location.extended_above_20:
            return True
        return mode == "extended_or_200" and location.near_200 and self._slope_is_flat_or_declining(
            location.sma200_slope
        )

    def _bull_trend(self, location: LocationAssessment) -> bool:
        if location.sma20 is None:
            return False
        if location.sma200 is not None and location.sma20 < location.sma200:
            return False
        return self._slope_is_flat_or_rising(location.sma20_slope)

    def _bear_trend(self, location: LocationAssessment) -> bool:
        if location.sma20 is None:
            return False
        if location.sma200 is not None and location.sma20 > location.sma200:
            return False
        return self._slope_is_flat_or_declining(location.sma20_slope)

    def _recent_pullback(self, bars: List[Bar]) -> bool:
        if not bars:
            return False
        bearish = any(item.close < item.open for item in bars)
        lower_close = any(bars[i].close < bars[i - 1].close for i in range(1, len(bars)))
        return bearish or lower_close

    def _recent_pushup(self, bars: List[Bar]) -> bool:
        if not bars:
            return False
        bullish = any(item.close > item.open for item in bars)
        higher_close = any(bars[i].close > bars[i - 1].close for i in range(1, len(bars)))
        return bullish or higher_close

    def _color_add_metadata(self, direction: str, atr: Optional[float]) -> dict:
        return {
            "atr": atr,
            "position_intent": "mandatory_add_after_first_color_change",
            "scale_action": "add_to_winner",
            "add_fraction": self.config.get("color_change", {}).get("add_fraction", 0.5),
            "requires_existing_winner": True,
            "mandatory_add": True,
            "color_change_direction": direction,
        }

    def _management_plan(self, side: Side, entry_price: Optional[float], stop_price: float) -> dict:
        cfg = self.config.get("management", {})
        entry = float(entry_price or 0.0)
        risk = abs(entry - stop_price)
        first_r = float(cfg.get("first_target_r", 1.0))
        second_r = float(cfg.get("second_target_r", 2.0))
        sign = 1 if side == Side.BUY else -1
        return {
            "enabled": cfg.get("enabled", True),
            "first_target_r": first_r,
            "first_target_price": round(entry + sign * risk * first_r, 4) if risk > 0 else None,
            "first_take_profit_pct": cfg.get("first_take_profit_pct", 0.5),
            "second_target_r": second_r,
            "second_target_price": round(entry + sign * risk * second_r, 4) if risk > 0 else None,
            "bar_3_profit_check": True,
            "move_stop_to_breakeven_after_first_target": True,
            "bar_by_bar_trailing_after_bars": cfg.get("trail_after_bars", 3),
            "momentum_exhaustion_bars": cfg.get("momentum_exhaustion_bars", 5),
        }

    def _prioritized_signals(self, signals: List[Signal]) -> List[Signal]:
        if not signals:
            return []
        priority = {
            VelezPlay.OPENING_GAP_GO.value: 5,
            VelezPlay.OPENING_GAP_FADE.value: 6,
            VelezPlay.TIME_SPACE_BREAKOUT.value: 7,
            VelezPlay.BULL_180.value: 10,
            VelezPlay.BEAR_180.value: 10,
            VelezPlay.ELEPHANT.value: 20,
            VelezPlay.BOTTOMING_TAIL.value: 30,
            VelezPlay.TOPPING_TAIL.value: 30,
            VelezPlay.FAILED_NEW_HIGH.value: 40,
            VelezPlay.FAILED_NEW_LOW.value: 40,
            VelezPlay.COLOR_CHANGE_ADD.value: 50,
            VelezPlay.BUY_SETUP.value: 60,
            VelezPlay.SELL_SETUP.value: 60,
            VelezPlay.NRB_ACORN.value: 70,
            VelezPlay.FAB4_TRAP_BREAKOUT.value: 80,
        }
        selected: Dict[Side, Signal] = {}
        for signal in sorted(signals, key=lambda item: priority.get(str(item.metadata.get("play") or item.reason), 999)):
            if signal.side not in selected:
                selected[signal.side] = signal
        return list(selected.values())

    def _slope_tolerance(self) -> float:
        return self.config.get("slope_tolerance", 1e-9)

    def _slope_is_rising(self, slope: Optional[float]) -> bool:
        return slope is not None and slope > self._slope_tolerance()

    def _slope_is_declining(self, slope: Optional[float]) -> bool:
        return slope is not None and slope < -self._slope_tolerance()

    def _slope_is_flat_or_rising(self, slope: Optional[float]) -> bool:
        return slope is None or slope >= -self._slope_tolerance()

    def _slope_is_flat_or_declining(self, slope: Optional[float]) -> bool:
        return slope is None or slope <= self._slope_tolerance()

    def _multi_bar_decline(self, ctx: VelezContext, count: int) -> bool:
        if len(ctx.bars) < count:
            return False
        bars = list(ctx.bars)[-count:]
        return all(bars[i].close < bars[i - 1].close for i in range(1, len(bars)))

    def _multi_bar_rally(self, ctx: VelezContext, count: int) -> bool:
        if len(ctx.bars) < count:
            return False
        bars = list(ctx.bars)[-count:]
        return all(bars[i].close > bars[i - 1].close for i in range(1, len(bars)))

    def _tick_size(self, symbol: str) -> float:
        tick_cfg = self.config.get("tick_size", {})
        if isinstance(tick_cfg, dict):
            return float(tick_cfg.get(symbol, tick_cfg.get("default", 0.01)))
        return float(tick_cfg or 0.01)

    def _stop_below(self, symbol: str, price: float) -> float:
        return self._round_to_tick(symbol, price - self._tick_size(symbol))

    def _stop_above(self, symbol: str, price: float) -> float:
        return self._round_to_tick(symbol, price + self._tick_size(symbol))

    def _round_to_tick(self, symbol: str, price: float) -> float:
        tick = self._tick_size(symbol)
        if tick <= 0:
            return price
        rounded = round(price / tick) * tick
        decimals = max(0, len(f"{tick:.10f}".rstrip("0").split(".")[-1]))
        return round(rounded, decimals)

    # ---- setup allowlist: one source of truth for what is live ----

    @staticmethod
    def _normalise_play_names(values) -> set:
        if isinstance(values, (str, bytes)):
            values = [values]
        return {
            str(item).strip().lower()
            for item in (values or [])
            if str(item).strip()
        }

    def _validate_setup_allowlist(self) -> None:
        """Fail at construction on an unknown play name, not silently at runtime.

        A typo in this list is the exact failure mode the list exists to
        prevent: ``elephant`` instead of ``elephant_bar`` would quietly permit
        nothing at all and the bot would simply stop trading, looking healthy.
        """
        cfg = self.config.get("setup_allowlist") or {}
        if not isinstance(cfg, dict):
            raise ValueError("setup_allowlist must be a mapping")
        known = {play.value for play in VelezPlay}
        for key in ("allowed_plays", "excluded_plays"):
            unknown = sorted(self._normalise_play_names(cfg.get(key)) - known)
            if unknown:
                raise ValueError(
                    f"setup_allowlist.{key} has unknown play(s): {', '.join(unknown)}. "
                    f"Valid plays: {', '.join(sorted(known))}"
                )

    def describe_setup_allowlist(self) -> dict:
        """What is live-tradeable right now, and on what stated evidence.

        Intended for the webhook/dashboard so "what is actually enabled and
        why" is answerable from one place instead of by reading nine scattered
        ``enabled:`` flags.
        """
        cfg = self.config.get("setup_allowlist") or {}
        allowed = sorted(self._normalise_play_names(cfg.get("allowed_plays")))
        excluded = sorted(self._normalise_play_names(cfg.get("excluded_plays")))
        active = bool(cfg.get("enabled", False))
        known = sorted(play.value for play in VelezPlay)
        if not active:
            effective = known
        elif bool(cfg.get("require_explicit", False)) and not allowed:
            effective = []
        else:
            effective = [
                play for play in known
                if play not in excluded and (not allowed or play in allowed)
            ]
        return {
            "enabled": active,
            "allowed_plays": allowed,
            "excluded_plays": excluded,
            "require_explicit": bool(cfg.get("require_explicit", False)),
            "effective_plays": effective,
            "reason": cfg.get("reason"),
            "evidence": cfg.get("evidence"),
        }

    def _setup_allowlist_filter(self, signals: List[Signal]) -> List[Signal]:
        """Gate signals on the allowlist. Inert unless explicitly enabled.

        This sits ALONGSIDE the per-play ``enabled:`` flags rather than
        replacing them, because the two answer different questions. A play's
        own flag decides whether its detector runs at all -- which matters
        beyond cost, since several detectors mutate per-session state
        (``opening_gap.go_used``, ``ctx.color_add_used``) that would otherwise
        diverge. This list decides whether a detector's output is
        live-tradeable, and is the single auditable record of that decision.
        """
        cfg = self.config.get("setup_allowlist") or {}
        if not signals or not cfg.get("enabled", False):
            return signals

        allowed = self._normalise_play_names(cfg.get("allowed_plays"))
        excluded = self._normalise_play_names(cfg.get("excluded_plays"))
        if bool(cfg.get("require_explicit", False)) and not allowed:
            # Fail closed: an empty list under require_explicit means "nothing
            # has been signed off", which must never mean "everything".
            return []

        kept: List[Signal] = []
        for signal in signals:
            play = str(signal.metadata.get("play") or signal.reason or "").strip().lower()
            if play in excluded:
                continue
            if allowed and play not in allowed:
                continue
            kept.append(signal)
        return kept


def calculate_core_position_size(
    *,
    max_dollar_risk: float,
    entry_price: float,
    stop_price: float,
    contract_multiplier: float = 1.0,
    max_order_qty: int = 1000000,
) -> int:
    risk_per_unit = abs(entry_price - stop_price) * contract_multiplier
    if max_dollar_risk <= 0 or risk_per_unit <= 0:
        return 0
    return max(0, min(int(max_dollar_risk / risk_per_unit), max_order_qty))


def calculate_pyramid_add_qty(current_qty: int, max_core_qty: Optional[int] = None) -> int:
    add_qty = int(abs(current_qty) * 0.5)
    if max_core_qty is not None:
        add_qty = min(add_qty, max(0, max_core_qty - abs(current_qty)))
    return max(0, add_qty)


def evaluate_pyramid_add(
    *,
    current_qty: int,
    entry_price: float,
    stop_price: float,
    current_price: float,
    current_volume: float,
    recent_volumes: List[float],
    max_core_qty: Optional[int] = None,
) -> PyramidDecision:
    if current_qty == 0:
        return PyramidDecision(False, 0, "no_position")

    long_position = current_qty > 0
    profitable = current_price > entry_price if long_position else current_price < entry_price
    if not profitable:
        return PyramidDecision(False, 0, "position_not_profitable")

    risk_mitigated = stop_price >= entry_price if long_position else stop_price <= entry_price
    if not risk_mitigated:
        return PyramidDecision(False, 0, "initial_risk_not_mitigated")

    volume_ok = True
    avg_recent_volume = None
    if recent_volumes:
        avg_recent_volume = sum(recent_volumes) / len(recent_volumes)
        volume_ok = current_volume < avg_recent_volume
    if not volume_ok:
        return PyramidDecision(
            False,
            0,
            "opposing_or_pullback_volume_not_diminishing",
            {"avg_recent_volume": avg_recent_volume},
        )

    qty = calculate_pyramid_add_qty(current_qty, max_core_qty)
    if qty <= 0:
        return PyramidDecision(False, 0, "max_core_capacity_reached")
    return PyramidDecision(True, qty, "ok", {"avg_recent_volume": avg_recent_volume})
