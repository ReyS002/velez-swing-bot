from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, Optional

import pytz


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            payload.update(record.extra)
        return json.dumps(payload, default=str)


def log_event(logger: logging.Logger, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    logger.info(message, extra={"extra": extra or {}})


def to_utc(dt: datetime, tz_name: str) -> datetime:
    tz = pytz.timezone(tz_name)
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    return dt.astimezone(pytz.utc)


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def round_to_tick(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        return price
    return round(price / tick_size) * tick_size


def asdict_safe(obj: Any) -> Dict[str, Any]:
    try:
        return asdict(obj)
    except Exception:
        return {"value": str(obj)}
