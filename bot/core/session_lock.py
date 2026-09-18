"""Trading Desk session-lock policy and durable settings helpers.

The lock deliberately governs *new entry exposure only*.  Position exits and
protective orders do not call this policy, so turning a session off can never
remove a stop or prevent a risk-reducing exit.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping
from zoneinfo import ZoneInfo


SESSION_LOCK_OPTIONS = {
    "all": {"label": "All permitted hours", "asset_types": None},
    "asia": {"label": "Asia (Tokyo)", "asset_types": {"forex", "future"}},
    "london": {"label": "London", "asset_types": {"forex", "future"}},
    "london_new_york_overlap": {"label": "London / New York overlap", "asset_types": {"forex", "future"}},
    "new_york": {"label": "New York", "asset_types": {"forex", "future"}},
    "us_cash": {"label": "US cash / RTH", "asset_types": {"equity"}},
}

_ASSET_ALIASES = {"stock": "equity", "stocks": "equity", "equities": "equity", "future": "future", "futures": "future", "fx": "forex", "currency": "forex", "currencies": "forex"}
_SETTINGS_PATH_ENV = "TRADING_BULL_SETTINGS_PATH"
_DEFAULT_SETTINGS_PATH = "/app/data/trading_bull_settings.json"


def session_lock_options() -> list[dict[str, str]]:
    return [{"id": option, "label": str(details["label"])} for option, details in SESSION_LOCK_OPTIONS.items()]


def normalize_session_lock(value: Any) -> str | None:
    cleaned = str(value or "").strip().lower().replace("/", "_").replace("-", "_").replace(" ", "_")
    aliases = {"all_sessions": "all", "tokyo": "asia", "london_ny_overlap": "london_new_york_overlap", "london_newyork_overlap": "london_new_york_overlap", "ny": "new_york", "newyork": "new_york", "rth": "us_cash", "us_cash_rth": "us_cash"}
    cleaned = aliases.get(cleaned, cleaned)
    return cleaned if cleaned in SESSION_LOCK_OPTIONS else None


def settings_path() -> Path:
    return Path(os.getenv(_SETTINGS_PATH_ENV, _DEFAULT_SETTINGS_PATH))


def session_scope(config: Mapping[str, Any], fallback: str) -> str:
    configured = ((config.get("session_lock") or {}).get("scope") if isinstance(config.get("session_lock"), Mapping) else None)
    # Scope by deployed bot, not by strategy profile. A copied/stale profile
    # must never make the Swing and intraday controls overwrite one another.
    raw = str(os.getenv("TRADING_BULL_SESSION_LOCK_SCOPE") or configured or fallback).strip().lower()
    safe = "".join(character if character.isalnum() or character in {"_", "-"} else "_" for character in raw)
    return safe[:80] or fallback


def read_session_lock(path: Path | str, scope: str) -> dict[str, Any]:
    settings, error, exists = _read_settings(Path(path))
    if error:
        return {"selection": "all", "settings_valid": False, "settings_status": "unavailable", "settings_error": error, "scope": scope}
    raw_locks = settings.get("session_locks", {})
    locks = raw_locks if isinstance(raw_locks, Mapping) else {}
    selection = normalize_session_lock(locks.get(scope, "all"))
    if selection is None:
        return {"selection": "all", "settings_valid": False, "settings_status": "invalid", "settings_error": "invalid_session_lock_selection", "scope": scope}
    return {"selection": selection, "settings_valid": True, "settings_status": "ready" if exists else "default", "scope": scope}


def update_session_lock(path: Path | str, scope: str, selection: Any) -> dict[str, Any]:
    normalized = normalize_session_lock(selection)
    if normalized is None:
        raise ValueError("session_lock must be one of: " + ", ".join(SESSION_LOCK_OPTIONS))
    _update_settings(Path(path), lambda settings: _set_session_lock(settings, scope, normalized))
    return read_session_lock(path, scope)


def update_settings_value(path: Path | str, key: str, value: Any) -> dict[str, Any]:
    if not str(key or "").strip():
        raise ValueError("settings key is required")
    return _update_settings(Path(path), lambda settings: {**settings, str(key): value})


def evaluate_session_lock(selection: str, *, asset_type: str = "", now: datetime | None = None, settings_valid: bool = True, settings_status: str = "ready", settings_error: str | None = None, scope: str = "") -> dict[str, Any]:
    current = _as_utc(now)
    normalized = normalize_session_lock(selection)
    if not settings_valid or normalized is None:
        return {"selection": normalized or "all", "label": "Session settings unavailable", "scope": scope, "entry_allowed": False, "active": False, "reason": "settings_unavailable", "lock_reason": "session_locked:settings_unavailable", "asset_type": _asset_category(asset_type), "settings_valid": False, "settings_status": settings_status, "settings_error": settings_error or "invalid_session_lock_selection", "current_time": current.isoformat(), "next_open_at": None, "window_end_at": None, "window_label": None}
    details = SESSION_LOCK_OPTIONS[normalized]
    category = _asset_category(asset_type)
    allowed_types = details["asset_types"]
    if allowed_types is not None and category and category not in allowed_types:
        return {"selection": normalized, "label": str(details["label"]), "scope": scope, "entry_allowed": False, "active": False, "reason": "asset_not_eligible", "lock_reason": f"session_locked:{normalized}", "asset_type": category, "eligible_asset_types": sorted(allowed_types), "settings_valid": True, "settings_status": settings_status, "current_time": current.isoformat(), "next_open_at": None, "window_end_at": None, "window_label": _window_label(normalized)}
    if normalized == "all":
        return {"selection": normalized, "label": str(details["label"]), "scope": scope, "entry_allowed": True, "active": True, "reason": "permitted_hours_defer_to_broker", "lock_reason": None, "asset_type": category, "settings_valid": True, "settings_status": settings_status, "current_time": current.isoformat(), "next_open_at": None, "window_end_at": None, "window_label": "Broker-permitted hours"}
    windows = _windows_for(normalized, current)
    active = next((window for window in windows if window[0] <= current < window[1]), None)
    upcoming = next((window for window in windows if current < window[0]), None)
    return {"selection": normalized, "label": str(details["label"]), "scope": scope, "entry_allowed": active is not None, "active": active is not None, "reason": "within_selected_session" if active else "outside_selected_session", "lock_reason": None if active else f"session_locked:{normalized}", "asset_type": category, "eligible_asset_types": sorted(allowed_types) if allowed_types is not None else None, "settings_valid": True, "settings_status": settings_status, "current_time": current.isoformat(), "window_start_at": active[0].isoformat() if active else None, "window_end_at": active[1].isoformat() if active else None, "next_open_at": upcoming[0].isoformat() if upcoming else None, "window_label": _window_label(normalized)}


def session_lock_state(path: Path | str, scope: str, *, asset_type: str = "", now: datetime | None = None) -> dict[str, Any]:
    stored = read_session_lock(path, scope)
    return evaluate_session_lock(str(stored["selection"]), asset_type=asset_type, now=now, settings_valid=bool(stored["settings_valid"]), settings_status=str(stored["settings_status"]), settings_error=stored.get("settings_error"), scope=scope)


def _set_session_lock(settings: dict[str, Any], scope: str, selection: str) -> dict[str, Any]:
    result = dict(settings)
    locks = dict(result.get("session_locks") or {})
    locks[scope] = selection
    result["session_locks"] = locks
    return result


def _asset_category(value: Any) -> str:
    cleaned = str(value or "").strip().lower()
    return _ASSET_ALIASES.get(cleaned, cleaned)


def _as_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)


def _window_label(selection: str) -> str:
    return {"asia": "09:00–18:00 Asia/Tokyo, weekdays", "london": "08:00–17:00 Europe/London, weekdays", "new_york": "08:00–17:00 America/New_York, weekdays", "london_new_york_overlap": "London and New York shared open hours, weekdays", "us_cash": "09:30–16:00 America/New_York, weekdays; broker holidays still apply"}.get(selection, "Broker-permitted hours")


def _windows_for(selection: str, now: datetime) -> list[tuple[datetime, datetime]]:
    if selection == "asia":
        return _zoned_windows(now, "Asia/Tokyo", time(9), time(18))
    if selection == "london":
        return _zoned_windows(now, "Europe/London", time(8), time(17))
    if selection == "new_york":
        return _zoned_windows(now, "America/New_York", time(8), time(17))
    if selection == "us_cash":
        return _zoned_windows(now, "America/New_York", time(9, 30), time(16))
    if selection == "london_new_york_overlap":
        london = _zoned_windows(now, "Europe/London", time(8), time(17))
        new_york = _zoned_windows(now, "America/New_York", time(8), time(17))
        return sorted({(max(london_start, ny_start), min(london_end, ny_end)) for london_start, london_end in london for ny_start, ny_end in new_york if max(london_start, ny_start) < min(london_end, ny_end)})
    return []


def _zoned_windows(now: datetime, timezone_name: str, start: time, end: time) -> list[tuple[datetime, datetime]]:
    zone = ZoneInfo(timezone_name)
    center = now.astimezone(zone).date()
    windows = []
    for offset in range(-1, 9):
        day = center + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        windows.append((datetime.combine(day, start, tzinfo=zone).astimezone(timezone.utc), datetime.combine(day, end, tzinfo=zone).astimezone(timezone.utc)))
    return windows


def _read_settings(path: Path) -> tuple[dict[str, Any], str | None, bool]:
    if not path.exists():
        return {}, None, False
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        return {}, f"settings_read_failed:{type(exc).__name__}", True
    if not isinstance(data, dict):
        return {}, "settings_not_an_object", True
    return data, None, True


@contextmanager
def _settings_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _update_settings(path: Path, mutate: Any) -> dict[str, Any]:
    with _settings_lock(path):
        settings, error, _exists = _read_settings(path)
        if error:
            settings = {}
        updated = mutate(dict(settings))
        if not isinstance(updated, dict):
            raise ValueError("settings mutation must return an object")
        _atomic_write(path, updated)
    return updated


def _atomic_write(path: Path, settings: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(settings), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
