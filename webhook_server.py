from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import requests
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

try:
    import jwt
except ImportError:  # pragma: no cover - deployment requirements install PyJWT.
    jwt = None

from .brokers.alpaca import AlpacaPaperBroker
from .calendar_feeds import CalendarFeedService
from .core.risk import RiskManager
from .core.types import Bar, OrderType, Side, Signal
from .core.utils import get_logger, log_event
from .core.velez_strategy import VelezInstitutionalStrategy
from .journal_store import JournalStore


@dataclass
class WebhookDecision:
    status: str
    reason: str
    symbol: Optional[str] = None
    side: Optional[str] = None
    play: Optional[str] = None
    qty: int = 0
    order_payload: Optional[dict] = None
    broker_response: Optional[dict] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _ops_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_path(env_name: str, filename: str) -> Path:
    configured = os.getenv(env_name, "").strip()
    path = Path(configured or f"/app/data/{filename}").expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class OpsAuditLog:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path).expanduser() if path else _data_path("VELEZ_OPS_AUDIT_LOG", "ops_audit.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, payload: Optional[dict] = None, actor: str = "system") -> dict:
        row = {
            "timestamp": _ops_now(),
            "event": event,
            "actor": actor or "system",
            "payload": self._redact(payload or {}),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, default=str, sort_keys=True) + "\n")
        return row

    def recent(self, limit: int = 80) -> list[dict]:
        if not self.path.exists():
            return []
        rows = self.path.read_text(encoding="utf-8").splitlines()[-max(1, min(int(limit), 500)):]
        out: list[dict] = []
        for row in reversed(rows):
            try:
                out.append(json.loads(row))
            except ValueError:
                continue
        return out

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                lowered = str(key).lower()
                if any(marker in lowered for marker in ("secret", "token", "password", "key")):
                    redacted[key] = "<redacted>"
                else:
                    redacted[key] = self._redact(item)
            return redacted
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value


class OpsSafetyController:
    def __init__(self, audit: OpsAuditLog, path: Optional[str] = None) -> None:
        self.audit = audit
        self.path = Path(path).expanduser() if path else _data_path("VELEZ_SAFETY_STATE_FILE", "ops_safety_state.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def snapshot(self) -> dict:
        state = self._load()
        state.setdefault("kill_switch_enabled", False)
        state.setdefault("kill_switch_reason", "")
        state.setdefault("broker_paused", False)
        state.setdefault("broker_pause_reason", "")
        state.setdefault("heartbeat", {})
        state["ok_to_trade"] = not state["kill_switch_enabled"] and not state["broker_paused"]
        return state

    def set_kill_switch(self, enabled: bool, reason: str = "", actor: str = "ops") -> dict:
        state = self._load()
        state["kill_switch_enabled"] = bool(enabled)
        state["kill_switch_reason"] = str(reason or "manual")[:300]
        state["updated_at"] = _ops_now()
        self._save(state)
        self.audit.record("safety.kill_switch", {"enabled": enabled, "reason": reason}, actor)
        return self.snapshot()

    def set_broker_pause(self, paused: bool, reason: str = "", actor: str = "ops") -> dict:
        state = self._load()
        state["broker_paused"] = bool(paused)
        state["broker_pause_reason"] = str(reason or "manual")[:300]
        state["updated_at"] = _ops_now()
        self._save(state)
        self.audit.record("safety.broker_pause", {"paused": paused, "reason": reason}, actor)
        return self.snapshot()

    def heartbeat(self, component: str = "webhook", ok: bool = True, detail: str = "", actor: str = "system") -> dict:
        state = self._load()
        heartbeat = state.setdefault("heartbeat", {})
        heartbeat[str(component or "webhook")[:60]] = {"ok": bool(ok), "detail": str(detail or "")[:300], "timestamp": _ops_now()}
        state["updated_at"] = _ops_now()
        self._save(state)
        if not ok:
            self.audit.record("safety.heartbeat_failed", {"component": component, "detail": detail}, actor)
        return self.snapshot()

    def guard_trade(self) -> tuple[bool, str]:
        state = self.snapshot()
        if state.get("kill_switch_enabled"):
            return False, "ops_kill_switch"
        if state.get("broker_paused"):
            return False, "ops_broker_paused"
        return True, "ok"

    def _load(self) -> dict:
        if not self.path.exists():
            return {"created_at": _ops_now(), "updated_at": _ops_now()}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError:
            return {"created_at": _ops_now(), "updated_at": _ops_now(), "load_error": "invalid_state_file"}

    def _save(self, state: dict) -> None:
        self.path.write_text(json.dumps(state, default=str, indent=2, sort_keys=True), encoding="utf-8")


class OpsBurnInController:
    def __init__(self, audit: OpsAuditLog, path: Optional[str] = None) -> None:
        self.audit = audit
        self.path = Path(path).expanduser() if path else _data_path("VELEZ_BURN_IN_STATE_FILE", "burn_in_state.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def start(self, *, days: int = 3, actor: str = "ops") -> dict:
        now = datetime.now(timezone.utc)
        safe_days = max(1, min(int(days or 3), 14))
        state = {
            "active": True,
            "started_at": now.isoformat(),
            "ends_at": (now + timedelta(days=safe_days)).isoformat(),
            "days": safe_days,
            "updated_at": now.isoformat(),
        }
        self._save(state)
        self.audit.record("burn_in.start", state, actor)
        return self.status([])

    def stop(self, actor: str = "ops") -> dict:
        state = self._load()
        state["active"] = False
        state["stopped_at"] = _ops_now()
        state["updated_at"] = _ops_now()
        self._save(state)
        self.audit.record("burn_in.stop", state, actor)
        return self.status([])

    def status(self, decisions: list[dict]) -> dict:
        state = self._load()
        now = datetime.now(timezone.utc)
        started = self._dt(state.get("started_at"))
        ends = self._dt(state.get("ends_at"))
        active = bool(state.get("active", False))
        progress = 100.0
        if active and started and ends and ends > started:
            progress = max(0.0, min(100.0, ((now - started).total_seconds() / (ends - started).total_seconds()) * 100.0))
            if progress >= 100.0:
                active = False
                state["active"] = False
                state["completed_at"] = now.isoformat()
                self._save(state)
        executed = sum(1 for item in decisions if item.get("status") in {"submitted", "approved"})
        proposed = sum(1 for item in decisions if item.get("status") == "proposed")
        rejected = sum(1 for item in decisions if item.get("status") in {"rejected", "error"})
        total = max(1, proposed + executed + rejected)
        return {
            **state,
            "active": active,
            "progress_pct": round(progress, 2),
            "decision_counts": {"proposed": proposed, "executed": executed, "rejected": rejected},
            "rejection_rate": round(rejected / total, 4),
        }

    def _load(self) -> dict:
        if not self.path.exists():
            return {"active": False, "progress_pct": 100.0}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError:
            return {"active": False, "progress_pct": 100.0, "load_error": "invalid_state_file"}

    def _save(self, state: dict) -> None:
        self.path.write_text(json.dumps(state, default=str, indent=2, sort_keys=True), encoding="utf-8")

    def _dt(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None


class OpsRBAC:
    def __init__(self) -> None:
        self.tokens = {
            "owner": self._split(os.getenv("VELEZ_OPS_OWNER_TOKEN", "") or os.getenv("VELEZ_OPS_TOKEN", "")),
            "admin": self._split(os.getenv("VELEZ_OPS_ADMIN_TOKEN", "")),
            "viewer": self._split(os.getenv("VELEZ_OPS_VIEWER_TOKEN", "")),
        }
        self.permissions = {
            "ops_read": {"owner", "admin", "viewer"},
            "ops_write": {"owner", "admin"},
            "safety_toggle": {"owner"},
        }

    def identify(self, token: str = "") -> dict:
        cleaned = str(token or "").replace("Bearer ", "", 1).strip()
        for role, tokens in self.tokens.items():
            if cleaned and cleaned in tokens:
                return {"role": role, "authenticated": True, "configured": self.configured()}
        return {"role": "anonymous", "authenticated": False, "configured": self.configured()}

    def require(self, token: str, permission: str) -> dict:
        context = self.identify(token)
        if context["role"] not in self.permissions.get(permission, set()):
            raise HTTPException(status_code=403, detail=f"forbidden:{permission}")
        return context

    def configured(self) -> dict:
        return {role: bool(tokens) for role, tokens in self.tokens.items()}

    def _split(self, raw: str) -> set[str]:
        return {item.strip() for item in str(raw or "").split(",") if item.strip()}


class AppleMusicTokenService:
    def __init__(self) -> None:
        self.team_id = os.getenv("APPLE_MUSIC_TEAM_ID", "").strip()
        self.key_id = os.getenv("APPLE_MUSIC_KEY_ID", "").strip()
        self.private_key_path = os.getenv("APPLE_MUSIC_PRIVATE_KEY_PATH", "").strip()
        self.ttl_hours = self._ttl_hours(os.getenv("APPLE_MUSIC_TOKEN_TTL_HOURS", "12"))
        self.origins = self._origins(os.getenv("APPLE_MUSIC_TOKEN_ORIGINS", ""))
        self._tokens: Dict[bool, tuple[str, datetime]] = {}

    def status(self) -> dict:
        missing = []
        if not self.team_id:
            missing.append("APPLE_MUSIC_TEAM_ID")
        if not self.key_id:
            missing.append("APPLE_MUSIC_KEY_ID")
        if not self.private_key_path:
            missing.append("APPLE_MUSIC_PRIVATE_KEY_PATH")
        return {
            "configured": not missing and jwt is not None,
            "missing": missing,
            "key_id_tail": self._tail(self.key_id),
            "team_id_tail": self._tail(self.team_id),
            "token_ttl_hours": self.ttl_hours,
            "origin_locked": bool(self.origins),
            "library": "PyJWT" if jwt is not None else "missing_pyjwt",
        }

    def developer_token(self, include_origins: bool = True) -> dict:
        status = self.status()
        if not status["configured"]:
            return {"ok": False, "reason": "not_configured", **status}

        now = datetime.now(timezone.utc)
        cache_key = bool(include_origins and self.origins)
        cached = self._tokens.get(cache_key)
        if cached and cached[1] > now + timedelta(minutes=5):
            return self._response(cached[0], cached[1])

        key_path = Path(self.private_key_path).expanduser()
        if not key_path.exists():
            return {
                "ok": False,
                "reason": "private_key_path_missing",
                **status,
            }

        private_key = key_path.read_text(encoding="utf-8")
        expires_at = now + timedelta(hours=self.ttl_hours)
        payload = {
            "iss": self.team_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        if cache_key:
            payload["origin"] = self.origins
        headers = {"alg": "ES256", "kid": self.key_id}
        token = jwt.encode(payload, private_key, algorithm="ES256", headers=headers)
        self._tokens[cache_key] = (token, expires_at)
        return self._response(token, expires_at)

    def catalog_search(self, term: str, storefront: str = "us", limit: int = 6) -> dict:
        term = term.strip()
        if not term:
            return {"ok": False, "reason": "missing_term"}

        token_result = self.developer_token(include_origins=False)
        if not token_result.get("ok"):
            return token_result

        safe_storefront = "".join(char for char in storefront.lower() if char.isalnum() or char == "-") or "us"
        safe_limit = max(1, min(int(limit or 6), 12))
        try:
            response = requests.get(
                f"https://api.music.apple.com/v1/catalog/{safe_storefront}/search",
                headers={"Authorization": f"Bearer {token_result['developer_token']}"},
                params={
                    "term": term,
                    "types": "songs,albums,playlists",
                    "limit": safe_limit,
                },
                timeout=8,
            )
        except requests.RequestException as exc:
            return {"ok": False, "reason": "apple_music_search_unreachable", "detail": str(exc)}

        try:
            payload = response.json() if response.text.strip() else {}
        except ValueError:
            return {"ok": False, "reason": "apple_music_search_invalid_response"}

        if response.status_code >= 400:
            return {
                "ok": False,
                "reason": f"apple_music_search_{response.status_code}",
                "detail": payload.get("errors", payload),
            }

        return {
            "ok": True,
            "term": term,
            "storefront": safe_storefront,
            "results": payload.get("results", {}),
        }

    def _response(self, token: str, expires_at: datetime) -> dict:
        return {
            "ok": True,
            "developer_token": token,
            "expires_at": expires_at.isoformat(),
            **self.status(),
        }

    def _ttl_hours(self, value: str) -> int:
        try:
            hours = int(value)
        except (TypeError, ValueError):
            hours = 12
        return max(1, min(hours, 168))

    def _tail(self, value: str) -> str:
        return value[-4:] if value else ""

    def _origins(self, configured: str) -> List[str]:
        values = [item.strip() for item in configured.split(",") if item.strip()]
        if values:
            return values
        public_url = os.getenv("VELEZ_PUBLIC_URL", "").strip().rstrip("/")
        public_host = os.getenv("VELEZ_PUBLIC_HOST", "").strip()
        if public_url:
            return [public_url]
        if public_host:
            return [f"https://{public_host}"]
        return []


class WinstonAIService:
    rule_provider = "winston_rule_based_v1"

    def __init__(self, engine: "TradingViewWebhookEngine") -> None:
        self.engine = engine

    def status(self, *, include_health_check: bool = False) -> dict:
        return {
            "ok": True,
            "brain": self.brain_status(include_health_check=include_health_check),
            "voice": self.voice_status(include_health_check=include_health_check),
            "guardrails": {
                "voice_trade_submission": "guarded_paper_only",
                "paper_trade_readback_only": False,
                "requires_exact_approval_phrase": True,
                "requires_approval_token": True,
            },
        }

    def brain_status(self, *, include_health_check: bool = False) -> dict:
        provider = self._llm_provider()
        model = os.getenv("WINSTON_LLM_MODEL", "qwen3:1.7b").strip()
        base_url = os.getenv("WINSTON_LLM_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
        timeout = self._float_env("WINSTON_LLM_TIMEOUT_SECONDS", 20.0)

        if provider == "rule_based":
            return {
                "provider": self.rule_provider,
                "model": "local_guardrail_rules",
                "configured": True,
                "available": True,
                "detail": "Safe local Winston responses",
            }

        configured = bool(model and base_url)
        available = configured
        detail = "Configured"
        if include_health_check and configured and provider == "ollama":
            available = self._ollama_available(base_url)
            detail = "Ollama reachable" if available else "Ollama not reachable"
        elif provider == "openai_compatible" and not os.getenv("WINSTON_LLM_API_KEY", "").strip():
            detail = "No API key set; only works with local endpoints that do not require auth"
        elif not configured:
            detail = "Needs WINSTON_LLM_BASE_URL and WINSTON_LLM_MODEL"

        return {
            "provider": provider,
            "model": model,
            "configured": configured,
            "available": available,
            "base_url": base_url,
            "timeout_seconds": timeout,
            "think": self._optional_bool_env("WINSTON_LLM_THINK"),
            "detail": detail,
        }

    def voice_status(self, *, include_health_check: bool = False) -> dict:
        provider = os.getenv("WINSTON_TTS_PROVIDER", "browser").strip().lower() or "browser"
        if provider in {"browser", "none", "off", "disabled"}:
            return {
                "provider": "browser",
                "configured": True,
                "available": True,
                "voice": "browser_default",
                "model": "Web Speech API",
                "detail": "Browser speech synthesis fallback",
            }

        base_url = (
            os.getenv("WINSTON_TTS_BASE_URL", "").strip()
            or os.getenv("POCKETTTS_URL", "").strip()
            or "http://127.0.0.1:8018/v1"
        ).rstrip("/")
        api_key = os.getenv("WINSTON_TTS_API_KEY", "").strip() or os.getenv("POCKETTTS_API_KEY", "").strip()
        voice = (
            os.getenv("WINSTON_TTS_VOICE", "").strip()
            or os.getenv("POCKETTTS_DEFAULT_VOICE", "").strip()
            or "jarvis-intro1"
        )
        model = os.getenv("WINSTON_TTS_MODEL", "tts-1").strip()
        configured = bool(base_url and api_key and voice)
        available = configured
        detail = "Hermes PocketTTS bridge configured" if configured else "Needs WINSTON_TTS_API_KEY or POCKETTTS_API_KEY"
        if include_health_check and configured:
            available = self._tts_available(base_url)
            detail = "Hermes PocketTTS reachable" if available else "Hermes PocketTTS not reachable"
        return {
            "provider": "pockettts" if provider in {"pockettts", "openai_compatible"} else provider,
            "configured": configured,
            "available": available,
            "base_url": base_url,
            "voice": voice,
            "model": model,
            "detail": detail,
        }

    def reply(self, prompt: str, fallback: dict) -> dict:
        provider = self._llm_provider()
        if provider == "rule_based":
            return fallback

        if self._trade_action_intent(prompt):
            guarded = dict(fallback)
            guarded.update(
                {
                    "ok": True,
                    "intent": "guarded_trade_approval",
                    "reply": (
                        fallback.get("reply")
                        or "That is a guarded trading action. I can discuss structure, read back a pending paper order, "
                        "and only submit through the separate approval route when the exact phrase and approval token are provided."
                    ),
                    "provider": "winston_trade_guardrail_v1",
                    "llm_used": False,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return guarded

        try:
            if provider == "ollama":
                reply = self._ollama_reply(prompt)
            elif provider == "openai_compatible":
                reply = self._openai_compatible_reply(prompt)
            else:
                raise ValueError(f"unsupported_winston_llm_provider:{provider}")
        except Exception as exc:
            degraded = dict(fallback)
            degraded.update(
                {
                    "provider": self.rule_provider,
                    "llm_used": False,
                    "degraded": True,
                    "fallback_reason": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return degraded

        response = dict(fallback)
        response.update(
            {
                "ok": True,
                "intent": "ai_assistant",
                "reply": reply,
                "provider": provider,
                "model": os.getenv("WINSTON_LLM_MODEL", "qwen3:1.7b").strip(),
                "llm_used": True,
                "degraded": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return response

    def research_reply(self, topic: str, context: dict, fallback: dict) -> dict:
        provider = os.getenv("WINSTON_RESEARCH_LLM_PROVIDER", "").strip().lower().replace("-", "_") or self._llm_provider()
        if provider == "rule_based":
            return fallback

        try:
            if provider == "ollama":
                reply = self._ollama_research_reply(topic, context)
            elif provider == "openai_compatible":
                reply = self._openai_research_reply(topic, context)
            else:
                raise ValueError(f"unsupported_winston_research_provider:{provider}")
        except Exception as exc:
            degraded = dict(fallback)
            degraded.update(
                {
                    "provider": self.rule_provider,
                    "research_used": False,
                    "degraded": True,
                    "fallback_reason": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return degraded

        response = dict(fallback)
        response.update(
            {
                "ok": True,
                "reply": reply,
                "provider": provider,
                "model": os.getenv("WINSTON_RESEARCH_LLM_MODEL", os.getenv("WINSTON_LLM_MODEL", "qwen3:1.7b")).strip(),
                "research_used": True,
                "degraded": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return response

    def synthesize_speech(self, text: str) -> dict:
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            return {"ok": False, "reason": "missing_text", **self.voice_status()}
        cleaned = cleaned[: self._int_env("WINSTON_TTS_MAX_CHARS", 2400)]

        status = self.voice_status()
        if status.get("provider") != "pockettts" or not status.get("configured"):
            return {"ok": False, "reason": "server_tts_not_configured", **status}

        url = self._speech_url(str(status["base_url"]))
        api_key = os.getenv("WINSTON_TTS_API_KEY", "").strip() or os.getenv("POCKETTTS_API_KEY", "").strip()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "model": status.get("model") or "tts-1",
            "voice": status.get("voice") or "jarvis-intro1",
            "input": cleaned,
            "response_format": "mp3",
        }
        timeout = self._float_env("WINSTON_TTS_TIMEOUT_SECONDS", 30.0)
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            return {
                **status,
                "ok": False,
                "reason": "tts_unreachable",
                "detail": str(exc),
            }
        if response.status_code >= 400:
            return {
                **status,
                "ok": False,
                "reason": f"tts_http_{response.status_code}",
                "detail": response.text[:240],
            }
        media_type = response.headers.get("content-type", "audio/mpeg").split(";", 1)[0] or "audio/mpeg"
        return {
            "ok": True,
            "provider": status.get("provider"),
            "voice": status.get("voice"),
            "model": status.get("model"),
            "media_type": media_type,
            "content": response.content,
        }

    def _ollama_reply(self, prompt: str) -> str:
        base_url = os.getenv("WINSTON_LLM_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
        model = os.getenv("WINSTON_LLM_MODEL", "qwen3:1.7b").strip()
        if not base_url or not model:
            raise ValueError("ollama_provider_not_configured")
        payload = {
            "model": model,
            "messages": self._messages(prompt),
            "stream": False,
            "options": {
                "temperature": self._float_env("WINSTON_LLM_TEMPERATURE", 0.25),
                "num_predict": self._int_env("WINSTON_LLM_MAX_TOKENS", 180),
            },
        }
        think = self._optional_bool_env("WINSTON_LLM_THINK")
        if think is not None:
            payload["think"] = think
        response = requests.post(f"{base_url}/api/chat", json=payload, timeout=self._float_env("WINSTON_LLM_TIMEOUT_SECONDS", 20.0))
        response.raise_for_status()
        data = response.json()
        return self._clean_reply(data.get("message", {}).get("content"))

    def _ollama_research_reply(self, topic: str, context: dict) -> str:
        base_url = os.getenv("WINSTON_RESEARCH_LLM_BASE_URL", os.getenv("WINSTON_LLM_BASE_URL", "http://127.0.0.1:11434")).strip().rstrip("/")
        model = os.getenv("WINSTON_RESEARCH_LLM_MODEL", os.getenv("WINSTON_LLM_MODEL", "qwen3:1.7b")).strip()
        if not base_url or not model:
            raise ValueError("ollama_research_provider_not_configured")
        payload = {
            "model": model,
            "messages": self._research_messages(topic, context),
            "stream": False,
            "options": {
                "temperature": self._float_env("WINSTON_RESEARCH_TEMPERATURE", 0.2),
                "num_predict": self._int_env("WINSTON_RESEARCH_MAX_TOKENS", 700),
            },
        }
        think = self._optional_bool_env("WINSTON_RESEARCH_THINK")
        if think is not None:
            payload["think"] = think
        response = requests.post(f"{base_url}/api/chat", json=payload, timeout=self._float_env("WINSTON_RESEARCH_TIMEOUT_SECONDS", 90.0))
        response.raise_for_status()
        data = response.json()
        return self._clean_research_reply(data.get("message", {}).get("content"))

    def _openai_compatible_reply(self, prompt: str) -> str:
        base_url = os.getenv("WINSTON_LLM_BASE_URL", "").strip().rstrip("/")
        model = os.getenv("WINSTON_LLM_MODEL", "").strip()
        if not base_url or not model:
            raise ValueError("openai_compatible_provider_not_configured")
        url = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"
        api_key = os.getenv("WINSTON_LLM_API_KEY", "").strip()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": self._messages(prompt),
            "temperature": self._float_env("WINSTON_LLM_TEMPERATURE", 0.25),
            "max_tokens": self._int_env("WINSTON_LLM_MAX_TOKENS", 180),
        }
        response = requests.post(url, headers=headers, json=payload, timeout=self._float_env("WINSTON_LLM_TIMEOUT_SECONDS", 20.0))
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("llm_returned_no_choices")
        return self._clean_reply(choices[0].get("message", {}).get("content"))

    def _openai_research_reply(self, topic: str, context: dict) -> str:
        base_url = os.getenv("WINSTON_RESEARCH_LLM_BASE_URL", os.getenv("WINSTON_LLM_BASE_URL", "")).strip().rstrip("/")
        model = os.getenv("WINSTON_RESEARCH_LLM_MODEL", os.getenv("WINSTON_LLM_MODEL", "")).strip()
        if not base_url or not model:
            raise ValueError("openai_research_provider_not_configured")
        url = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"
        api_key = os.getenv("WINSTON_RESEARCH_LLM_API_KEY", os.getenv("WINSTON_LLM_API_KEY", "")).strip()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": self._research_messages(topic, context),
            "temperature": self._float_env("WINSTON_RESEARCH_TEMPERATURE", 0.2),
            "max_tokens": self._int_env("WINSTON_RESEARCH_MAX_TOKENS", 700),
        }
        response = requests.post(url, headers=headers, json=payload, timeout=self._float_env("WINSTON_RESEARCH_TIMEOUT_SECONDS", 90.0))
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("research_llm_returned_no_choices")
        return self._clean_research_reply(choices[0].get("message", {}).get("content"))

    def _messages(self, prompt: str) -> List[dict]:
        state = self.engine.dashboard_state()
        brief = self.engine.winston_brief()
        context = {
            "runtime": self.status(include_health_check=False),
            "desk": {
                "execution_armed": state.get("execution_armed"),
                "broker": state.get("broker"),
                "summary": state.get("summary"),
                "risk": state.get("risk"),
                "symbols": state.get("symbols"),
                "recent_decisions": state.get("recent_decisions", [])[:5],
            },
            "brief": brief.get("summary"),
        }
        return [
            {
                "role": "system",
                "content": (
                    "You are Winston, Rey's calm British AI operator inside Trading Bull Desk. "
                    "Answer like a concise voice assistant: direct, calm, and useful, with light dry wit only when natural. "
                    "Use only the provided desk context for broker, P/L, watchlist, risk, and alerts. "
                    "When asked what powers you, name the configured runtime brain and voice providers from context. "
                    "If asked for current news, company updates, earnings, FOMC, or web facts that are not in context, say that live news/data is not wired into this call yet. "
                    "When describing your abilities, say you can brief the desk, read watchlists/positions/risk, run Research Mode, route iPod and panel commands, and read back guarded approval status. "
                    "Never say you can execute trades, place orders, submit orders, or approve trades from normal chat or voice. "
                    "Do not give personalized financial advice. Do not claim you placed, approved, cancelled, bought, sold, or closed any trade. "
                    "Guarded paper trade approval can only happen through the separate pending-order approval route with an exact phrase and approval token."
                ),
            },
            {
                "role": "user",
                "content": f"Desk context JSON:\n{json.dumps(context, default=str)[:6000]}\n\nUser request:\n{prompt.strip()}",
            },
        ]

    def _research_messages(self, topic: str, context: dict) -> List[dict]:
        return [
            {
                "role": "system",
                "content": (
                    "You are Winston Research Mode inside Trading Bull Desk. "
                    "Produce a concise trader prep note from the provided context only. "
                    "Separate facts from inference, call out stale or missing data, and avoid personalized financial advice. "
                    "Do not say you can trade. Do not invent news, prices, earnings, or fundamentals that are not present."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Research topic: {topic.strip()[:500]}\n\n"
                    f"Context JSON:\n{json.dumps(context, default=str)[:self._int_env('WINSTON_RESEARCH_CONTEXT_CHARS', 7000)]}"
                ),
            },
        ]

    def _clean_reply(self, value: Any) -> str:
        text = " ".join(str(value or "").split())
        if not text:
            raise ValueError("llm_returned_empty_reply")
        return text[:900]

    def _clean_research_reply(self, value: Any) -> str:
        text = " ".join(str(value or "").split())
        if not text:
            raise ValueError("research_llm_returned_empty_reply")
        return text[:2400]

    def _llm_provider(self) -> str:
        provider = os.getenv("WINSTON_LLM_PROVIDER", "rule_based").strip().lower().replace("-", "_")
        aliases = {
            "none": "rule_based",
            "off": "rule_based",
            "disabled": "rule_based",
            "local": "ollama",
            "hermes": "ollama",
            "openai": "openai_compatible",
        }
        return aliases.get(provider, provider)

    def _trade_action_intent(self, prompt: str) -> bool:
        text = prompt.lower()
        action_words = ("approve", "submit", "place", "execute", "cancel", "close", "liquidate", "buy", "sell", "short", "long")
        trade_words = ("trade", "order", "position", "shares", "contracts", "entry", "stop")
        return any(word in text for word in action_words) and any(word in text for word in trade_words)

    def _speech_url(self, base_url: str) -> str:
        root = base_url.rstrip("/")
        if root.endswith("/v1"):
            return f"{root}/audio/speech"
        return f"{root}/v1/audio/speech"

    def _ollama_available(self, base_url: str) -> bool:
        try:
            response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=1.5)
            return response.status_code < 400
        except requests.RequestException:
            return False

    def _tts_available(self, base_url: str) -> bool:
        root = base_url.rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
        try:
            response = requests.get(f"{root}/api/health", timeout=1.5)
            return response.status_code < 500
        except requests.RequestException:
            return False

    def _float_env(self, name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            return default

    def _int_env(self, name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            return default

    def _optional_bool_env(self, name: str) -> Optional[bool]:
        value = os.getenv(name)
        if value is None or not value.strip():
            return None
        return value.strip().lower() in {"1", "true", "yes", "on"}


class TradingViewWebhookEngine:
    def __init__(self, config: dict, broker: Optional[AlpacaPaperBroker] = None) -> None:
        self.config = config
        self.webhook_config = config.get("webhook", {})
        self.risk_config = config.get("risk", {})
        self.symbol_config = {item["symbol"]: item for item in config.get("symbols", [])}
        self.logger = get_logger("tradingview_webhook")
        self.strategy = VelezInstitutionalStrategy(config.get("velez_strategy", config.get("strategy", {})), self.logger)
        self.risk = RiskManager(self.risk_config)
        self.broker = broker or AlpacaPaperBroker()
        self.seen_alert_ids: Deque[str] = deque(maxlen=self.webhook_config.get("dedupe_cache_size", 1000))
        self.recent_decisions: Deque[dict] = deque(maxlen=self.webhook_config.get("dashboard_decisions", 80))
        self.started_at = datetime.now(timezone.utc)
        self.journal = JournalStore(self.config)
        self.ops_audit = OpsAuditLog()
        self.safety = OpsSafetyController(self.ops_audit)
        self.burn_in = OpsBurnInController(self.ops_audit)
        self.winston = WinstonAIService(self)
        self.calendar = CalendarFeedService(self.broker, self.config, self.recent_decisions, journal=self.journal)

    def handle_payload(
        self,
        payload: dict,
        *,
        path_token: Optional[str] = None,
        header_secret: Optional[str] = None,
    ) -> dict:
        auth = self._authorize(payload, path_token, header_secret)
        if auth.status != "allowed":
            log_event(self.logger, "webhook_auth_rejected", {"reason": auth.reason})
            self._remember_decisions([auth], self._alert_id(payload))
            return {"ok": False, "decisions": [auth.__dict__]}

        alert_id = self._alert_id(payload)
        if alert_id in self.seen_alert_ids:
            decision = WebhookDecision(status="ignored", reason="duplicate_alert")
            self._remember_decisions([decision], alert_id)
            return {
                "ok": True,
                "duplicate": True,
                "decisions": [decision.__dict__],
            }
        self.seen_alert_ids.append(alert_id)

        mode = str(payload.get("mode", "signal")).lower()
        if mode == "bar":
            decisions = self._handle_bar_payload(payload, alert_id)
        elif mode == "signal":
            decisions = [self._handle_signal_payload(payload, alert_id)]
        else:
            decisions = [WebhookDecision(status="rejected", reason=f"unsupported_mode:{mode}")]

        self._remember_decisions(decisions, alert_id)
        return {"ok": all(d.status not in {"rejected", "error"} for d in decisions), "decisions": [d.__dict__ for d in decisions]}

    def dashboard_state(self) -> dict:
        broker_status = self.broker.validate_connection() if self.broker.is_configured() else {"ok": False, "reason": "missing_credentials"}
        positions, positions_error = self._positions_snapshot()
        unrealized_pl = sum(self._float(item.get("unrealized_pl")) or 0.0 for item in positions)
        now = datetime.now(timezone.utc)
        public_host = os.getenv("VELEZ_PUBLIC_HOST", "")
        public_url = os.getenv("VELEZ_PUBLIC_URL", "") or (f"https://{public_host}" if public_host else "")
        symbols = self.watchlist_symbols()
        recent = self.journal.latest_decisions(limit=self.webhook_config.get("dashboard_decisions", 80))
        if not recent:
            recent = list(self.recent_decisions)
        return {
            "ok": True,
            "dashboard_version": "v6.6",
            "timestamp": now.isoformat(),
            "uptime_seconds": int((now - self.started_at).total_seconds()),
            "execution_armed": self._execute_orders(),
            "public_url": public_url,
            "broker": broker_status,
            "paper_endpoint": self.broker.config.base_url.startswith("https://paper-api."),
            "positions": positions,
            "positions_error": positions_error,
            "summary": {
                "open_positions": len(positions),
                "unrealized_pl": round(unrealized_pl, 2),
                "symbols_watched": len(symbols),
                "recent_decisions": len(recent),
                "pending_approvals": len(self.journal.pending_orders()),
            },
            "risk": {
                "risk_per_trade": self.risk_config.get("risk_per_trade"),
                "max_dollar_risk_per_trade": self.risk_config.get("max_dollar_risk_per_trade"),
                "max_daily_loss_pct": self.risk_config.get("max_daily_loss_pct"),
                "max_open_positions": self.risk_config.get("max_open_positions"),
                "max_stop_pct": self.risk_config.get("max_stop_pct"),
                "pyramid_add_fraction": self.risk_config.get("pyramid_add_fraction", 0.5),
            },
            "guardrails": {
                "paper_only": self.webhook_config.get("paper_only", True),
                "time_in_force": self.webhook_config.get("time_in_force", "day"),
                "take_profit_r": self.webhook_config.get("take_profit_r"),
                "auth_required": self.webhook_config.get("auth_required", True),
            },
            "symbols": symbols,
            "recent_decisions": recent,
            "pending_approvals": self.journal.public_pending_orders(),
            "safety": self.safety.snapshot(),
            "burn_in": self.burn_in.status(recent),
            "apple_music": AppleMusicTokenService().status(),
            "winston": self.winston.status(),
        }

    def calendar_month(self) -> dict:
        self.calendar.config = {**self.config, "symbols": self.watchlist_symbols()}
        return self.calendar.month_payload()

    def watchlist_symbols(self, include_disabled: bool = False) -> List[dict]:
        return [
            {
                "symbol": item.get("symbol"),
                "type": item.get("type", "equity"),
                "contract_multiplier": item.get("contract_multiplier", 1),
                "session": item.get("session", "rth"),
                "enabled": item.get("enabled", True),
                "notes": item.get("notes", ""),
                "source": item.get("source", "config"),
            }
            for item in self.journal.list_watchlist(include_disabled=include_disabled)
        ]

    def add_watchlist_symbol(self, item: dict) -> dict:
        saved = self.journal.upsert_watchlist(item)
        self.symbol_config[saved["symbol"]] = {
            "symbol": saved["symbol"],
            "type": saved.get("type", "equity"),
            "contract_multiplier": saved.get("contract_multiplier", 1),
            "session": saved.get("session", "rth"),
        }
        return {"ok": True, "symbol": saved, "symbols": self.watchlist_symbols()}

    def remove_watchlist_symbol(self, symbol: str) -> dict:
        removed = self.journal.remove_watchlist(symbol)
        return {"ok": removed, "symbol": str(symbol or "").upper().strip(), "symbols": self.watchlist_symbols()}

    def winston_brief(self) -> dict:
        brief = self.daily_brief_payload()
        return {
            "ok": True,
            "timestamp": brief["timestamp"],
            "summary": brief["voice_summary"],
            "brief": brief,
            "watchlist": brief.get("watchlist", []),
            "positions": brief.get("positions", []),
            "recent_decisions": brief.get("recent_decisions", [])[:5],
            "risk": brief.get("risk", {}),
            "provider": "winston_daily_brief_v2",
            "brain": self.winston.brain_status(),
            "voice": self.winston.voice_status(),
        }

    def daily_brief_payload(self) -> dict:
        state = self.dashboard_state()
        calendar = self.calendar_month()
        health = self.bot_health(light=True)
        symbols = ", ".join(item.get("symbol", "") for item in state.get("symbols", []) if item.get("symbol")) or "no symbols configured"
        latest = state.get("recent_decisions", [None])[0] if state.get("recent_decisions") else None
        latest_text = "No TradingView alerts have reached the journal yet."
        if latest:
            latest_text = f"Latest alert: {latest.get('symbol', 'symbol')} {latest.get('play') or latest.get('reason', 'decision')} with status {latest.get('status', 'seen')}."
        broker = state.get("broker", {})
        summary = state.get("summary", {})
        risk = state.get("risk", {})
        pnl = calendar.get("pnl", {})
        session = calendar.get("session", {})
        events = calendar.get("events", [])[:4]
        earnings = calendar.get("earnings", [])[:4]
        pending = state.get("pending_approvals", [])
        event_text = "No high-priority macro events are loaded."
        if events:
            first = events[0]
            event_text = f"Next macro item: {first.get('date')} {first.get('time', '')} {first.get('title')} from {first.get('source')}."
        earnings_text = "No watchlist earnings are loaded in the current window."
        if earnings:
            first = earnings[0]
            earnings_text = f"Next earnings item: {first.get('date')} {first.get('symbol')} {first.get('name') or first.get('title')}."
        approval_text = "No paper orders are waiting for guarded approval."
        if pending:
            first = pending[0]
            approval_text = f"{len(pending)} paper order approval is waiting. Say or type exactly: {first.get('approval_phrase')}."
        health_text = f"Bot health is {health.get('overall', 'unknown')}: {health.get('summary', 'components checking')}."
        watch_plan = self._watch_plan(state, calendar)
        brief_lines = [
            f"Trading Bull Desk is {'armed for Alpaca paper execution' if state.get('execution_armed') else 'in proposal mode'}.",
            health_text,
            f"Broker status is {'connected to Alpaca Paper' if broker.get('ok') else 'not ready: ' + str(broker.get('reason', 'needs check'))}.",
            f"Watchlist: {symbols}.",
            f"Month P and L is ${float(pnl.get('month_pl') or 0):,.2f}; open-position mark is ${float(summary.get('unrealized_pl') or 0):,.2f}.",
            f"Market session: {session.get('status', 'unknown')} {session.get('label', '')}.",
            event_text,
            earnings_text,
            f"{summary.get('open_positions', 0)} positions are open.",
            f"Risk is capped at ${float(risk.get('max_dollar_risk_per_trade') or 0):,.2f} per trade and {risk.get('max_open_positions', 0)} max open positions.",
            latest_text,
            approval_text,
            watch_plan,
        ]
        return {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "voice_summary": " ".join(brief_lines),
            "lines": brief_lines,
            "readiness": health,
            "sections": {
                "desk": brief_lines[:4],
                "calendar": [f"Market session: {session.get('status', 'unknown')} {session.get('label', '')}.", event_text, earnings_text],
                "risk": [
                    f"{summary.get('open_positions', 0)} positions are open.",
                    f"Risk is capped at ${float(risk.get('max_dollar_risk_per_trade') or 0):,.2f} per trade and {risk.get('max_open_positions', 0)} max open positions.",
                ],
                "watch_plan": [watch_plan],
                "approvals": [approval_text],
            },
            "watchlist": state.get("symbols", []),
            "positions": state.get("positions", []),
            "recent_decisions": state.get("recent_decisions", [])[:5],
            "risk": risk,
            "calendar": {
                "range": calendar.get("range", {}),
                "pnl": pnl,
                "session": session,
                "events": events,
                "earnings": earnings,
            },
            "pending_approvals": pending,
        }

    def daily_review_payload(self) -> dict:
        now = datetime.now(timezone.utc)
        day = now.date().isoformat()
        decisions = self.journal.decisions_between(day, day, limit=500)
        state = self.dashboard_state()
        calendar = self.calendar_month()
        statuses = Counter(str(item.get("status") or "unknown") for item in decisions)
        plays = Counter(str(item.get("play") or item.get("reason") or "unknown") for item in decisions)
        symbols = Counter(str(item.get("symbol") or "unknown") for item in decisions)
        actionable = [item for item in decisions if item.get("status") in {"proposed", "submitted"}]
        blocked = [item for item in decisions if item.get("status") in {"rejected", "ignored", "error"}]
        pnl = calendar.get("pnl", {})
        lines = [
            f"{len(decisions)} alert decision{'s' if len(decisions) != 1 else ''} recorded today.",
            f"{len(actionable)} actionable, {len(blocked)} blocked or ignored.",
            f"Month P/L is ${float(pnl.get('month_pl') or 0):,.2f}; open-position mark is ${float(state.get('summary', {}).get('unrealized_pl') or 0):,.2f}.",
            f"Top setup: {plays.most_common(1)[0][0] if plays else 'none yet'}.",
            f"Top symbol: {symbols.most_common(1)[0][0] if symbols else 'none yet'}.",
        ]
        if blocked:
            lines.append(f"Most recent blocked reason: {blocked[0].get('reason', 'unknown')}.")
        if actionable:
            latest = actionable[0]
            lines.append(f"Latest actionable setup: {latest.get('symbol')} {latest.get('play') or latest.get('reason')} {latest.get('side')}.")
        lesson = "Stay patient until structure, location, and risk are all aligned."
        if statuses.get("rejected", 0) or statuses.get("ignored", 0):
            lesson = "The bot is filtering noise; review blocked reasons before loosening anything."
        if statuses.get("submitted", 0):
            lesson = "Review submitted trades for entry quality, stop placement, and whether the play followed location rules."
        return {
            "ok": True,
            "timestamp": now.isoformat(),
            "date": day,
            "summary": " ".join(lines),
            "lines": lines,
            "lesson": lesson,
            "counts": {
                "status": dict(statuses),
                "play": dict(plays),
                "symbol": dict(symbols),
                "decisions": len(decisions),
                "actionable": len(actionable),
                "blocked": len(blocked),
            },
            "latest": decisions[:8],
        }

    def journal_payload(self, limit: int = 40, symbol: str = "", status: str = "") -> dict:
        raw_entries = self.journal.decision_entries(limit=limit, symbol=symbol, status=status)
        entries = [self._journal_entry(item) for item in raw_entries]
        statuses = Counter(str(item.get("status") or "unknown") for item in raw_entries)
        plays = Counter(str(item.get("play") or item.get("reason") or "unknown") for item in raw_entries)
        symbols = Counter(str(item.get("symbol") or "unknown") for item in raw_entries)
        actionable = sum(1 for item in raw_entries if item.get("status") in {"proposed", "submitted"})
        blocked = sum(1 for item in raw_entries if item.get("status") in {"rejected", "ignored", "error"})
        latest_research = self.journal.latest_research(limit=4)
        latest_replays = self.journal.latest_replays(limit=3)
        return {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "entries": len(entries),
                "actionable": actionable,
                "blocked": blocked,
                "submitted": statuses.get("submitted", 0),
                "proposed": statuses.get("proposed", 0),
                "top_setup": plays.most_common(1)[0][0] if plays else "None",
                "top_symbol": symbols.most_common(1)[0][0] if symbols else "None",
            },
            "counts": {
                "status": dict(statuses),
                "play": dict(plays),
                "symbol": dict(symbols),
            },
            "entries": entries,
            "research": latest_research,
            "replays": latest_replays,
        }

    def bot_health(self, *, light: bool = False) -> dict:
        now = datetime.now(timezone.utc)
        broker_status = self.broker.validate_connection() if self.broker.is_configured() else {"ok": False, "reason": "missing_credentials"}
        positions, positions_error = self._positions_snapshot()
        latest = self.journal.latest_decisions(limit=1)
        last_alert = latest[0] if latest else None
        journal_ok = self.journal.path.exists()
        public_host = os.getenv("VELEZ_PUBLIC_HOST", "")
        public_url = os.getenv("VELEZ_PUBLIC_URL", "") or (f"https://{public_host}" if public_host else "")
        winston = self.winston.status(include_health_check=not light)
        components = [
            self._health_component("API", True, "online", f"Uptime {int((now - self.started_at).total_seconds())}s"),
            self._health_component("VPS public URL", bool(public_url), "configured" if public_url else "local only", public_url or "No public URL env set"),
            self._health_component("Alpaca paper", bool(broker_status.get("ok")), "connected" if broker_status.get("ok") else "needs check", broker_status.get("account_status") or broker_status.get("reason", "unknown")),
            self._health_component("Paper endpoint", bool(self.broker.config.base_url.startswith("https://paper-api.")), "locked" if self.broker.config.base_url.startswith("https://paper-api.") else "review", self.broker.config.base_url),
            self._health_component("Execution mode", True, "armed" if self._execute_orders() else "proposal", "Qualified alerts auto-submit to paper" if self._execute_orders() else "Orders are proposed only"),
            self._health_component("Ops safety", bool(self.safety.snapshot().get("ok_to_trade")), "clear" if self.safety.snapshot().get("ok_to_trade") else "blocked", self.safety.snapshot().get("kill_switch_reason") or self.safety.snapshot().get("broker_pause_reason") or "No ops block active"),
            self._health_component("TradingView webhook", True, "listening", self._last_alert_label(last_alert)),
            self._health_component("Journal database", journal_ok, "ready" if journal_ok else "missing", str(self.journal.path)),
            self._health_component("Calendar feeds", True, "configured", "Alpaca, Alpha Vantage, and public macro feeds"),
            self._health_component("Winston brain", bool(winston.get("brain", {}).get("available")), winston.get("brain", {}).get("provider", "unknown"), winston.get("brain", {}).get("detail", "")),
            self._health_component("Winston voice", bool(winston.get("voice", {}).get("available")), winston.get("voice", {}).get("provider", "unknown"), winston.get("voice", {}).get("detail", "")),
        ]
        if positions_error:
            components.append(self._health_component("Positions", False, "needs check", positions_error))
        else:
            components.append(self._health_component("Positions", True, f"{len(positions)} open", "Broker position snapshot read"))
        hard_failures = [item for item in components if not item["ok"] and item["name"] in {"Alpaca paper", "Paper endpoint", "Journal database"}]
        soft_failures = [item for item in components if not item["ok"] and item["name"] not in {"Alpaca paper", "Paper endpoint", "Journal database"}]
        overall = "green" if not hard_failures and not soft_failures else "yellow" if not hard_failures else "red"
        summary = "All core services are ready" if overall == "green" else f"{len(hard_failures) + len(soft_failures)} component checks need attention"
        return {
            "ok": True,
            "timestamp": now.isoformat(),
            "overall": overall,
            "summary": summary,
            "dashboard_version": "v6.6",
            "execution_armed": self._execute_orders(),
            "approval_required": self._requires_order_approval(),
            "last_alert": last_alert,
            "components": components if not light else components[:8],
        }

    def ops_readiness(self) -> dict:
        health = self.bot_health(light=True)
        state = self.dashboard_state()
        safety = self.safety.snapshot()
        burn_in = self.burn_in.status(state.get("recent_decisions", []))
        checks = [
            {"id": "api_health", "passed": health.get("overall") in {"green", "yellow"}, "detail": health.get("summary")},
            {"id": "paper_endpoint", "passed": bool(state.get("paper_endpoint")), "detail": self.broker.config.base_url},
            {"id": "execution_guarded", "passed": bool(state.get("guardrails", {}).get("paper_only")), "detail": "paper_only must remain true"},
            {"id": "safety_clear", "passed": bool(safety.get("ok_to_trade")), "detail": safety.get("kill_switch_reason") or safety.get("broker_pause_reason") or "clear"},
            {"id": "burn_in_complete", "passed": not bool(burn_in.get("active")) and float(burn_in.get("progress_pct", 0) or 0) >= 100, "detail": f"progress={burn_in.get('progress_pct')}"},
            {"id": "pending_approvals_clear", "passed": len(state.get("pending_approvals", [])) == 0, "detail": f"pending={len(state.get('pending_approvals', []))}"},
        ]
        return {
            "ok": True,
            "timestamp": _ops_now(),
            "ready_for_paper_auto_submit": all(item["passed"] for item in checks),
            "checks": checks,
            "safety": safety,
            "burn_in": burn_in,
        }

    def ops_uptime(self) -> dict:
        health = self.bot_health(light=True)
        self.safety.heartbeat("webhook", ok=True, detail=health.get("overall", "unknown"))
        return {"status": "ok" if health.get("overall") in {"green", "yellow"} else "degraded", "timestamp": _ops_now(), "health": health}

    def replay_payload(self, payload: dict) -> dict:
        symbol = str(payload.get("symbol") or (self.watchlist_symbols() or [{"symbol": "SPY"}])[0].get("symbol") or "SPY").upper().strip()
        scenario = str(payload.get("scenario") or "bull_elephant").strip() or "bull_elephant"
        bars_payload = payload.get("bars")
        bars = bars_payload if isinstance(bars_payload, list) and bars_payload else self._sample_replay_bars(scenario)
        equity = self._float(payload.get("equity")) or self.config.get("portfolio", {}).get("initial_cash", 100000)
        strategy = VelezInstitutionalStrategy(self.config.get("velez_strategy", self.config.get("strategy", {})), self.logger)
        events: List[dict] = []
        for index, raw_bar in enumerate(bars):
            try:
                bar = self._bar_from_replay(raw_bar, index=index, total=len(bars))
            except Exception:
                continue
            signals = strategy.on_bar(symbol, bar)
            for signal in signals:
                events.append(self._replay_signal_event(signal, equity))
        by_play = Counter(item["play"] for item in events)
        result = {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "scenario": scenario,
            "bars_loaded": len(bars),
            "signals_found": len(events),
            "by_play": dict(by_play),
            "events": events[-20:],
            "summary": self._replay_summary(events, len(bars)),
            "guardrail": "Replay mode never submits broker orders.",
        }
        self.journal.save_replay(result)
        return result

    def _watch_plan(self, state: dict, calendar: dict) -> str:
        symbols = [item.get("symbol") for item in state.get("symbols", []) if item.get("symbol")]
        events = calendar.get("timeline", [])[:5] or calendar.get("events", [])[:3] or calendar.get("earnings", [])[:3]
        event_hint = "no loaded macro or earnings catalysts"
        if events:
            first = events[0]
            event_hint = f"{first.get('date')} {first.get('title')}"
        focus = ", ".join(symbols[:6]) if symbols else "the configured watchlist"
        return f"Watch plan: focus on {focus}; respect the 20 SMA/200 SMA location filters and note {event_hint}."

    def _journal_entry(self, item: dict) -> dict:
        entry = self._float(item.get("entry_price"))
        stop = self._float(item.get("stop_price"))
        target = self._float(item.get("take_profit_price"))
        qty = int(self._float(item.get("qty")) or 0)
        side = str(item.get("side") or "").lower()
        risk_per_unit = abs(entry - stop) if entry is not None and stop is not None else None
        target_r = None
        if entry is not None and target is not None and risk_per_unit:
            target_r = abs(target - entry) / risk_per_unit
        symbol_cfg = self.symbol_config.get(str(item.get("symbol") or "").upper(), {}) or self.journal.get_watchlist_symbol(str(item.get("symbol") or "")) or {}
        multiplier = float(symbol_cfg.get("contract_multiplier", 1) or 1)
        risk_dollars = risk_per_unit * qty * multiplier if risk_per_unit is not None and qty else None
        location = item.get("location") or []
        if isinstance(location, str):
            location_text = location
        else:
            location_text = ", ".join(str(part) for part in location if part)
        checks = {
            "has_location": bool(location_text),
            "has_stop": stop is not None,
            "has_size": qty > 0,
            "actionable_status": item.get("status") in {"proposed", "submitted"},
        }
        score = sum(1 for value in checks.values() if value)
        if item.get("status") == "rejected":
            score = min(score, 2)
        grade = "A" if score >= 4 else "B" if score == 3 else "C" if score == 2 else "D"
        readback = [
            f"{item.get('status', 'seen')} | {item.get('reason', 'no reason logged')}",
            f"{str(side).upper() if side else 'SIDE'} {qty or ''} {item.get('symbol') or ''} via {item.get('play') or item.get('reason') or 'setup'}".strip(),
        ]
        if entry is not None and stop is not None:
            readback.append(f"Entry {entry:g}, stop {stop:g}, risk/unit {risk_per_unit:g}")
        if target_r is not None:
            readback.append(f"Target readback: {target_r:.2f}R")
        if location_text:
            readback.append(f"Location: {location_text}")
        return {
            **item,
            "setup": item.get("play") or item.get("reason") or "unknown",
            "grade": grade,
            "checks": checks,
            "metrics": {
                "risk_per_unit": risk_per_unit,
                "risk_dollars": round(risk_dollars, 2) if risk_dollars is not None else None,
                "target_r": round(target_r, 2) if target_r is not None else None,
                "contract_multiplier": multiplier,
            },
            "readback": readback,
        }

    def _health_component(self, name: str, ok: bool, status: str, detail: str) -> dict:
        return {
            "name": name,
            "ok": bool(ok),
            "status": str(status or "unknown"),
            "detail": str(detail or ""),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def _last_alert_label(self, decision: Optional[dict]) -> str:
        if not decision:
            return "No TradingView alerts logged yet"
        parts = [decision.get("symbol"), decision.get("play") or decision.get("reason"), decision.get("status")]
        return f"{' | '.join(str(part) for part in parts if part)} | {self._age_label(decision.get('timestamp'))}"

    def _age_label(self, value: Any) -> str:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return "time unknown"
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        seconds = max(0, int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()))
        if seconds < 60:
            return f"{seconds}s ago"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        return f"{minutes // 60}h ago"

    def _sample_replay_bars(self, scenario: str) -> List[dict]:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        start = now - timedelta(minutes=5 * 226)
        bars: List[dict] = []
        bear_mode = scenario == "bear_180"
        for index in range(224):
            center = 100 - index * 0.0004 if bear_mode else 100 + index * 0.0004
            open_price = center + 0.04 if bear_mode else center
            close_price = center if bear_mode else center + 0.04
            bars.append(
                {
                    "timestamp": (start + timedelta(minutes=5 * index)).isoformat(),
                    "open": round(open_price, 2),
                    "high": round(max(open_price, close_price) + 0.08, 2),
                    "low": round(min(open_price, close_price) - 0.08, 2),
                    "close": round(close_price, 2),
                    "volume": 1000 + index * 3,
                }
            )
        if scenario == "bear_180":
            bars.extend(
                [
                    {
                        "timestamp": (start + timedelta(minutes=5 * 224)).isoformat(),
                        "open": 99.82,
                        "high": 100.32,
                        "low": 99.72,
                        "close": 100.2,
                        "volume": 1900,
                    },
                    {
                        "timestamp": (start + timedelta(minutes=5 * 225)).isoformat(),
                        "open": 100.15,
                        "high": 100.28,
                        "low": 99.62,
                        "close": 99.72,
                        "volume": 2300,
                    },
                ]
            )
        else:
            bars.append(
                {
                    "timestamp": (start + timedelta(minutes=5 * 224)).isoformat(),
                    "open": 100.06,
                    "high": 102.04,
                    "low": 99.92,
                    "close": 101.84,
                    "volume": 2800,
                }
            )
        return bars

    def _bar_from_replay(self, raw: dict, *, index: int, total: int) -> Bar:
        timestamp = raw.get("timestamp") or raw.get("time") or (datetime.now(timezone.utc) - timedelta(minutes=5 * (total - index))).isoformat()
        values = {key: self._float(raw.get(key)) for key in ("open", "high", "low", "close")}
        if any(value is None for value in values.values()):
            raise ValueError("replay_bar_missing_ohlc")
        return Bar(
            timestamp=self._timestamp(timestamp),
            open=float(values["open"]),
            high=float(values["high"]),
            low=float(values["low"]),
            close=float(values["close"]),
            volume=self._float(raw.get("volume")) or 0.0,
        )

    def _replay_signal_event(self, signal: Signal, equity: float) -> dict:
        metadata = signal.metadata or {}
        entry = self._float(metadata.get("entry_price") or metadata.get("close"))
        stop = self._float(metadata.get("stop_price"))
        symbol = signal.symbol
        sym_cfg = self.symbol_config.get(symbol, {}) or self.journal.get_watchlist_symbol(symbol) or {}
        multiplier = float(sym_cfg.get("contract_multiplier", 1.0) or 1.0)
        qty = 0
        risk_dollars = 0.0
        if entry is not None and stop is not None:
            qty = self.risk.calculate_fixed_risk_position_size(
                max_dollar_risk=self._risk_budget(float(equity)),
                entry_price=entry,
                stop_price=stop,
                contract_multiplier=multiplier,
                max_order_qty=int(self.risk_config.get("max_order_qty", 10000)),
                equity=float(equity),
                max_leverage=float(self.risk_config.get("max_leverage", 1.0)),
            )
            risk_dollars = abs(entry - stop) * qty * multiplier
        timestamp = metadata.get("timestamp")
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        location = metadata.get("location", [])
        if isinstance(location, list):
            location = [str(item) for item in location]
        elif location:
            location = [str(location)]
        else:
            location = []
        return {
            "timestamp": timestamp,
            "symbol": symbol,
            "side": signal.side.value,
            "play": metadata.get("play") or signal.reason,
            "order_type": metadata.get("order_type"),
            "entry_price": entry,
            "stop_price": stop,
            "limit_price": metadata.get("limit_price"),
            "qty": qty,
            "risk_dollars": round(risk_dollars, 2),
            "location": location,
            "chased": bool(metadata.get("chased")),
            "distance_to_sma20_pct": metadata.get("distance_to_sma20_pct"),
        }

    def _replay_summary(self, events: List[dict], bars_loaded: int) -> str:
        if not events:
            return f"Replay scanned {bars_loaded} candles and found no qualified Velez setup."
        latest = events[-1]
        return (
            f"Replay scanned {bars_loaded} candles and found {len(events)} qualified setup"
            f"{'s' if len(events) != 1 else ''}. Latest: {latest.get('symbol')} {latest.get('play')} "
            f"{latest.get('side')} at {latest.get('entry_price')} with stop {latest.get('stop_price')}."
        )

    def winston_reply(self, message: str) -> dict:
        prompt = (message or "").strip()
        if not prompt:
            return {"ok": False, "reason": "missing_message"}

        phrase_result = self._approval_from_prompt(prompt)
        if phrase_result:
            return phrase_result

        command_result = self._fast_command_from_prompt(prompt)
        if command_result:
            return command_result

        fallback = self._winston_rule_reply(prompt)
        return self.winston.reply(prompt, fallback)

    def winston_research(self, topic: str, symbol: Optional[str] = None) -> dict:
        cleaned_topic = " ".join(str(topic or "").split())[:500]
        if not cleaned_topic:
            return {"ok": False, "reason": "missing_topic"}
        symbol = str(symbol or self._symbol_from_text(cleaned_topic) or "").upper().strip()
        context = {
            "topic": cleaned_topic,
            "symbol": symbol,
            "daily_brief": self.daily_brief_payload(),
            "calendar": self.calendar_month(),
            "watchlist": self.watchlist_symbols(),
            "recent_decisions": self.journal.latest_decisions(limit=12),
            "alpha_vantage": self._alpha_research_context(symbol) if symbol else {},
        }
        fallback_reply = self._research_fallback(cleaned_topic, context)
        fallback = {
            "ok": True,
            "intent": "research",
            "topic": cleaned_topic,
            "symbol": symbol,
            "reply": fallback_reply,
            "provider": "winston_research_fallback_v1",
            "research_used": False,
            "context": self._public_research_context(context),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        result = self.winston.research_reply(cleaned_topic, context, fallback)
        self.journal.save_research(cleaned_topic, {key: value for key, value in result.items() if key != "context"})
        return result

    def pending_approvals(self, include_inactive: bool = False) -> dict:
        items = self.journal.pending_orders(include_inactive=include_inactive)
        return {"ok": True, "pending": [self.journal._public_pending(item) for item in items]}

    def approve_pending_order(self, approval_id: str, approval_phrase: str, approval_token: str) -> dict:
        auth = self._authorize_approval_token(approval_token)
        if not auth.get("ok"):
            return auth
        if not self._execute_orders():
            return {"ok": False, "reason": "execution_not_armed"}
        if self.webhook_config.get("paper_only", True) and "paper-api.alpaca.markets" not in self.broker.config.base_url:
            return {"ok": False, "reason": "non_paper_alpaca_endpoint_blocked"}
        result = self.journal.approve_pending_order(approval_id, approval_phrase, self.broker)
        if result.get("ok"):
            log_event(self.logger, "pending_order_approved", {"id": approval_id, "symbol": result.get("pending", {}).get("symbol")})
        return result

    def _approval_from_prompt(self, prompt: str) -> Optional[dict]:
        match = re.search(r"\bapprove\s+paper\s+order\s+([a-f0-9]{8})\b", prompt, flags=re.IGNORECASE)
        if not match:
            return None
        pending = self.journal.get_pending_order(match.group(1).upper())
        if not pending:
            return {
                "ok": True,
                "intent": "guarded_trade_approval",
                "reply": "I heard an approval phrase, but that pending paper order is not staged or has expired.",
                "provider": "winston_trade_guardrail_v2",
                "llm_used": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "ok": True,
            "intent": "guarded_trade_approval",
            "reply": (
                f"I heard the phrase for {pending.get('symbol')} {pending.get('side')} {pending.get('qty')}. "
                "For safety, the browser must send the stored approval token through the guarded approval route before I submit the paper order."
            ),
            "pending": self.journal._public_pending(pending),
            "provider": "winston_trade_guardrail_v2",
            "llm_used": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _fast_command_from_prompt(self, prompt: str) -> Optional[dict]:
        text = " ".join(str(prompt or "").split())
        normalized = text.lower()
        music = self._music_command(text, normalized)
        if music:
            return music
        panel = self._panel_command(normalized)
        if panel:
            return panel
        return None

    def _music_command(self, text: str, normalized: str) -> Optional[dict]:
        if not any(word in normalized for word in ("music", "song", "track", "artist", "album", "playlist", "play", "pause", "resume", "skip", "next", "previous", "volume", "ipod", "now playing")):
            return None

        def response(reply: str, actions: List[dict], intent: str = "music_control") -> dict:
            return {
                "ok": True,
                "intent": intent,
                "reply": reply,
                "actions": actions,
                "provider": "winston_fast_command_router_v1",
                "llm_used": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        if re.search(r"\b(now playing|what'?s playing|current song|current track)\b", normalized):
            return response("Checking the iPod now-playing status.", [{"type": "music.now_playing"}])
        if re.search(r"\b(pause|stop)\b", normalized) and "approval" not in normalized:
            return response("Pausing the iPod.", [{"type": "music.pause"}])
        if re.search(r"\b(resume|continue)\b", normalized):
            return response("Resuming the iPod.", [{"type": "music.resume"}])
        if re.search(r"\b(skip|next)\b", normalized):
            return response("Skipping to the next track.", [{"type": "music.next"}])
        if re.search(r"\b(previous|back|last track)\b", normalized):
            return response("Going back one track.", [{"type": "music.previous"}])
        if "volume" in normalized:
            if re.search(r"\b(up|louder|raise|increase)\b", normalized):
                return response("Turning the iPod up a bit.", [{"type": "music.volume", "direction": "up"}])
            if re.search(r"\b(down|lower|quieter|decrease)\b", normalized):
                return response("Turning the iPod down a bit.", [{"type": "music.volume", "direction": "down"}])
            match = re.search(r"\b(\d{1,3})\s*(?:percent|%)\b", normalized)
            if match:
                pct = max(0, min(int(match.group(1)), 100))
                return response(f"Setting the iPod volume to {pct} percent.", [{"type": "music.volume", "value": pct / 100}])

        play_match = re.search(
            r"\b(?:play|put on|queue|start)\s+(?:(?P<kind>song|track|artist|album|playlist)\s+)?(?P<query>.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if play_match:
            query = self._clean_music_query(play_match.group("query"))
            kind = (play_match.group("kind") or "").lower()
            if query and query.lower() not in {"music", "a song", "some music"}:
                label = f"{kind} " if kind else ""
                return response(
                    f"On it. Searching Apple Music for {label}{query}.",
                    [{"type": "music.play_search", "query": query, "kind": kind or "auto"}],
                )
        return None

    def _clean_music_query(self, value: str) -> str:
        query = re.sub(r"\b(on|from|in)\s+(apple music|the ipod|ipod|music)\b", "", str(value or ""), flags=re.IGNORECASE)
        query = re.sub(r"^(some|the)\s+", "", query.strip(), flags=re.IGNORECASE)
        return " ".join(query.strip(" .!?\"'").split())[:120]

    def _panel_command(self, normalized: str) -> Optional[dict]:
        panels = {
            "music": ("music", "Opening the iPod."),
            "ipod": ("music", "Opening the iPod."),
            "mission": ("mission", "Opening the daily mission card."),
            "daily mission": ("mission", "Opening the daily mission card."),
            "journal": ("journal", "Opening the trade journal."),
            "after action": ("notes", "Opening the after-action review."),
            "review": ("notes", "Opening the after-action review."),
            "calendar": ("calendar", "Opening the calendar."),
            "laptop": ("laptop", "Opening command center."),
            "command": ("laptop", "Opening command center."),
            "health": ("laptop", "Opening bot health in command center."),
            "safe": ("safe", "Opening the safe."),
            "approval inbox": ("safe", "Opening the approval inbox."),
            "approvals": ("safe", "Opening the approval inbox."),
            "trading screen": ("tv", "Opening the trading screen."),
            "chart": ("tv", "Opening the trading screen."),
            "bookshelf": ("bookshelf", "Opening the strategy library."),
            "library": ("bookshelf", "Opening the strategy library."),
            "strategy": ("bookshelf", "Opening the strategy library."),
            "clock": ("clock", "Opening the market session clock."),
            "session": ("clock", "Opening the market session clock."),
            "window": ("window", "Opening market weather."),
            "weather": ("window", "Opening market weather."),
            "lamp": ("lamp", "Opening the risk mood light."),
            "risk light": ("lamp", "Opening the risk mood light."),
            "drawer": ("drawer", "Opening the backtest drawer."),
            "backtest": ("drawer", "Opening the backtest drawer."),
            "replay": ("drawer", "Opening the backtest drawer."),
            "notes": ("notes", "Opening sticky notes."),
            "sticky": ("notes", "Opening sticky notes."),
        }
        if not re.search(r"\b(open|show|go to|pull up|bring up)\b", normalized):
            return None
        for key, (panel, reply) in panels.items():
            if key in normalized:
                return {
                    "ok": True,
                    "intent": "desk_navigation",
                    "reply": reply,
                    "actions": [{"type": "panel.open", "panel": panel}],
                    "provider": "winston_fast_command_router_v1",
                    "llm_used": False,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
        return None

    def _winston_rule_reply(self, prompt: str) -> dict:
        normalized = prompt.lower()
        brief = self.winston_brief()
        state = self.dashboard_state()
        symbols = ", ".join(item.get("symbol", "") for item in state.get("symbols", []) if item.get("symbol")) or "no symbols configured"
        intent = "general"
        reply = "I can brief the desk, read the watchlist, check positions, summarize risk, or stage a guarded paper-trade approval readback."

        if any(word in normalized for word in ("brief", "daily", "morning", "breakdown")):
            intent = "daily_brief"
            reply = brief["summary"]
        elif "watch" in normalized:
            intent = "watchlist"
            reply = f"Current watchlist: {symbols}. I am waiting for qualified Velez setups before any paper order can be proposed."
        elif any(word in normalized for word in ("position", "p/l", "profit", "loss")):
            intent = "positions"
            summary = state.get("summary", {})
            reply = f"{summary.get('open_positions', 0)} positions are open with ${float(summary.get('unrealized_pl') or 0):,.2f} unrealized P and L."
        elif "risk" in normalized:
            intent = "risk"
            risk = state.get("risk", {})
            reply = (
                f"Risk is capped at ${float(risk.get('max_dollar_risk_per_trade') or 0):,.2f} per trade, "
                f"{risk.get('max_open_positions', 0)} max open positions, and {float(risk.get('max_daily_loss_pct') or 0) * 100:.2f}% daily loss cap."
            )
        elif any(word in normalized for word in ("approve", "trade", "order", "buy", "sell")):
            intent = "guarded_trade_approval"
            pending = self.journal.pending_orders()
            if pending:
                first = pending[0]
                reply = (
                    f"Trade approval is guarded. Pending paper order: {first.get('symbol')} {first.get('side')} "
                    f"{first.get('qty')} shares, entry {first.get('entry_price') or 'market'}, stop {first.get('stop_price')}. "
                    f"Say or type exactly: {first.get('approval_phrase')}. The browser approval token is still required."
                )
            else:
                reply = (
                    "Trade approval is guarded. I cannot submit anything from this call because I do not see a pending paper order readback. "
                    "A TradingView proposal must stage the order first, then I require the exact approval phrase and browser approval token."
                )

        return {
            "ok": True,
            "intent": intent,
            "reply": reply,
            "provider": "winston_rule_based_v1",
            "llm_used": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _authorize_approval_token(self, supplied: str) -> dict:
        expected = os.getenv("VELEZ_APPROVAL_API_TOKEN", "").strip()
        expected = expected or os.getenv(self.webhook_config.get("secret_env", "VELEZ_WEBHOOK_SECRET"), "").strip()
        expected = expected or str(self.webhook_config.get("secret", "")).strip()
        if not expected:
            return {"ok": False, "reason": "approval_token_not_configured"}
        if str(supplied or "").strip() != expected:
            return {"ok": False, "reason": "invalid_approval_token"}
        return {"ok": True}

    def _symbol_from_text(self, text: str) -> Optional[str]:
        configured = {item.get("symbol", "").upper() for item in self.watchlist_symbols()}
        for token in re.findall(r"\b[A-Z]{1,6}\b", text.upper()):
            if token in configured:
                return token
        return None

    def _alpha_research_context(self, symbol: str) -> dict:
        key = (
            os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
            or os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
            or os.getenv("AV_API_KEY", "").strip()
            or os.getenv("ALPHA_VINTAGE_API_KEY", "").strip()
        )
        if not key or not symbol:
            return {"configured": bool(key), "symbol": symbol, "overview": {}, "news": []}
        context = {"configured": True, "symbol": symbol, "overview": {}, "news": []}
        try:
            overview = requests.get(
                "https://www.alphavantage.co/query",
                params={"function": "OVERVIEW", "symbol": symbol, "apikey": key},
                timeout=float(os.getenv("CALENDAR_FEED_TIMEOUT_SECONDS", "8")),
            )
            if overview.status_code < 400:
                payload = overview.json() if overview.text.strip().startswith("{") else {}
                if payload and not payload.get("Note") and not payload.get("Information"):
                    keep = (
                        "Symbol",
                        "Name",
                        "Description",
                        "Sector",
                        "Industry",
                        "MarketCapitalization",
                        "PERatio",
                        "EPS",
                        "ProfitMargin",
                        "QuarterlyEarningsGrowthYOY",
                        "QuarterlyRevenueGrowthYOY",
                        "AnalystTargetPrice",
                    )
                    context["overview"] = {key_name: payload.get(key_name) for key_name in keep if payload.get(key_name)}
        except Exception as exc:
            context["overview_error"] = str(exc)
        try:
            news = requests.get(
                "https://www.alphavantage.co/query",
                params={"function": "NEWS_SENTIMENT", "tickers": symbol, "limit": 8, "apikey": key},
                timeout=float(os.getenv("CALENDAR_FEED_TIMEOUT_SECONDS", "8")),
            )
            if news.status_code < 400:
                payload = news.json() if news.text.strip().startswith("{") else {}
                feed = payload.get("feed") if isinstance(payload, dict) else []
                context["news"] = [
                    {
                        "title": item.get("title"),
                        "source": item.get("source"),
                        "time_published": item.get("time_published"),
                        "summary": item.get("summary"),
                        "url": item.get("url"),
                    }
                    for item in (feed or [])[:6]
                ]
        except Exception as exc:
            context["news_error"] = str(exc)
        return context

    def _research_fallback(self, topic: str, context: dict) -> str:
        symbol = context.get("symbol") or "the watchlist"
        calendar = context.get("calendar", {})
        events = calendar.get("events", [])[:3]
        news = context.get("alpha_vantage", {}).get("news", [])[:3]
        lines = [f"Research Mode fallback for {symbol}: {topic}."]
        if news:
            lines.append("Recent Alpha Vantage headlines: " + "; ".join(item.get("title", "Untitled") for item in news if item.get("title")))
        if events:
            lines.append("Macro calendar: " + "; ".join(f"{item.get('date')} {item.get('title')}" for item in events))
        if len(lines) == 1:
            lines.append("No external research rows were available, so I am limited to the current desk state, journal, and calendar.")
        lines.append("Treat this as prep context, not financial advice.")
        return " ".join(lines)

    def _public_research_context(self, context: dict) -> dict:
        alpha = context.get("alpha_vantage", {})
        return {
            "topic": context.get("topic"),
            "symbol": context.get("symbol"),
            "calendar_events": context.get("calendar", {}).get("events", [])[:5],
            "earnings": context.get("calendar", {}).get("earnings", [])[:5],
            "alpha_configured": alpha.get("configured"),
            "alpha_news_count": len(alpha.get("news", [])),
            "overview_available": bool(alpha.get("overview")),
        }

    def _handle_bar_payload(self, payload: dict, alert_id: str) -> List[WebhookDecision]:
        try:
            symbol = self._symbol(payload)
            bar = self._bar_from_payload(payload)
        except Exception as exc:
            return [WebhookDecision(status="rejected", reason=str(exc))]

        signals = self.strategy.on_bar(symbol, bar)
        if not signals:
            return [WebhookDecision(status="ignored", reason="no_qualified_velez_signal", symbol=symbol)]
        return [self._build_order_decision(signal, alert_id) for signal in signals]

    def _handle_signal_payload(self, payload: dict, alert_id: str) -> WebhookDecision:
        try:
            signal = self._signal_from_payload(payload)
        except Exception as exc:
            return WebhookDecision(status="rejected", reason=str(exc))
        return self._build_order_decision(signal, alert_id)

    def _build_order_decision(self, signal: Signal, alert_id: str) -> WebhookDecision:
        symbol = signal.symbol
        metadata = signal.metadata
        side = signal.side.value
        setup_direction = "long" if side == "buy" else "short"
        play = str(metadata.get("play", signal.reason))
        entry_price = self._float(metadata.get("entry_price") or metadata.get("close"))
        stop_price = self._float(metadata.get("stop_price"))
        order_type = str(metadata.get("order_type", "market")).lower()

        if entry_price is None or stop_price is None:
            return WebhookDecision("rejected", "missing_entry_or_stop", symbol=symbol, side=side, play=play)
        if order_type not in {"market", "limit"}:
            return WebhookDecision("rejected", f"unsupported_order_type:{order_type}", symbol=symbol, side=side, play=play)
        if side == "buy" and stop_price >= entry_price:
            return WebhookDecision("rejected", "long_stop_must_be_below_entry", symbol=symbol, side=side, play=play)
        if side == "sell" and stop_price <= entry_price:
            return WebhookDecision("rejected", "short_stop_must_be_above_entry", symbol=symbol, side=side, play=play)

        max_stop_pct = self.risk_config.get("max_stop_pct", 0.1)
        if abs(entry_price - stop_price) / max(entry_price, 1e-9) > max_stop_pct:
            return WebhookDecision("rejected", "stop_distance_exceeds_guardrail", symbol=symbol, side=side, play=play)

        # Multi-timeframe directional gate
        tf15_bias = str(metadata.get("tf15_bias", "")).lower()
        tf5_setup = str(metadata.get("tf5_setup", "")).lower()
        tf2_trigger = str(metadata.get("tf2_trigger", "")).lower()

        if tf15_bias and setup_direction:
            if tf15_bias == "bearish" and setup_direction == "long":
                return WebhookDecision("rejected", "tf15_bearish_blocks_long", symbol=symbol, side=side, play=play)
            if tf15_bias == "bullish" and setup_direction == "short":
                return WebhookDecision("rejected", "tf15_bullish_blocks_short", symbol=symbol, side=side, play=play)

            if tf15_bias == "neutral":
                if tf5_setup == "aligned" and tf2_trigger == "confirmed":
                    pass
                elif tf5_setup == "mixed":
                    return WebhookDecision("proposed", "caution_tf15_neutral_tf5_mixed", symbol=symbol, side=side, play=play, qty=0)

        if self.webhook_config.get("paper_only", True) and "paper-api.alpaca.markets" not in self.broker.config.base_url:
            return WebhookDecision("rejected", "non_paper_alpaca_endpoint_blocked", symbol=symbol, side=side, play=play)

        safety_ok, safety_reason = self.safety.guard_trade()
        if not safety_ok:
            return WebhookDecision("rejected", safety_reason, symbol=symbol, side=side, play=play)

        account = {}
        positions_count = 0
        if self._execute_orders():
            try:
                account = self.broker.get_account()
                positions_count = len(self.broker.get_positions_raw())
            except Exception as exc:
                return WebhookDecision("error", f"broker_account_check_failed:{exc}", symbol=symbol, side=side, play=play)
        else:
            account = {"equity": self.config.get("portfolio", {}).get("initial_cash", 100000)}

        equity = self._float(account.get("equity") or account.get("portfolio_value")) or self.config.get("portfolio", {}).get("initial_cash", 100000)
        limits = self.risk.check_limits(equity=equity, open_positions=positions_count)
        if not limits.allowed:
            return WebhookDecision("rejected", limits.reason, symbol=symbol, side=side, play=play)

        max_dollar_risk = self._risk_budget(equity)
        sym_cfg = self.symbol_config.get(symbol, {}) or self.journal.get_watchlist_symbol(symbol) or {}
        qty = self.risk.calculate_fixed_risk_position_size(
            max_dollar_risk=max_dollar_risk,
            entry_price=entry_price,
            stop_price=stop_price,
            contract_multiplier=float(sym_cfg.get("contract_multiplier", 1.0)),
            max_order_qty=int(self.risk_config.get("max_order_qty", 10000)),
            equity=equity,
            max_leverage=float(self.risk_config.get("max_leverage", 1.0)),
        )
        if qty <= 0:
            return WebhookDecision("rejected", "position_size_zero", symbol=symbol, side=side, play=play)

        take_profit_price = self._take_profit_price(side, entry_price, stop_price)
        client_order_id = f"velez-{hashlib.sha1(alert_id.encode('utf-8')).hexdigest()[:24]}"
        payload = self.broker.build_entry_payload(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            entry_price=entry_price if order_type == "limit" else None,
            stop_price=stop_price,
            client_order_id=client_order_id,
            time_in_force=self.webhook_config.get("time_in_force", "day"),
            take_profit_price=take_profit_price,
        )

        decision = WebhookDecision(
            status="proposed",
            reason="execution_disabled",
            symbol=symbol,
            side=side,
            play=play,
            qty=qty,
            order_payload=payload,
            metadata={
                "equity": equity,
                "max_dollar_risk": max_dollar_risk,
                "alert_id": alert_id,
                "source_metadata": metadata,
            },
        )

        requires_approval = self._requires_order_approval()
        if not self._execute_orders() or requires_approval:
            if requires_approval and self._execute_orders():
                decision.reason = "approval_required"
            log_event(self.logger, "order_proposed", decision.__dict__)
            return decision

        try:
            response = self.broker.submit_order_payload(payload)
        except Exception as exc:
            return WebhookDecision(
                "error",
                f"broker_order_failed:{exc}",
                symbol=symbol,
                side=side,
                play=play,
                qty=qty,
                order_payload=payload,
            )

        decision.status = "submitted"
        decision.reason = "submitted_to_alpaca_paper"
        decision.broker_response = response
        log_event(self.logger, "order_submitted", decision.__dict__)
        return decision

    def _authorize(self, payload: dict, path_token: Optional[str], header_secret: Optional[str]) -> WebhookDecision:
        expected = os.getenv(self.webhook_config.get("secret_env", "VELEZ_WEBHOOK_SECRET"), "")
        expected = expected or self.webhook_config.get("secret", "")
        if not self.webhook_config.get("auth_required", True):
            return WebhookDecision("allowed", "auth_disabled")
        if not expected:
            return WebhookDecision("rejected", "webhook_secret_not_configured")
        supplied = path_token or header_secret or payload.get("secret")
        if supplied != expected:
            return WebhookDecision("rejected", "invalid_webhook_secret")
        return WebhookDecision("allowed", "ok")

    def _signal_from_payload(self, payload: dict) -> Signal:
        symbol = self._symbol(payload)
        side = Side(str(payload["side"]).lower())
        order_type = str(payload.get("order_type", "market")).lower()
        entry_price = self._float(payload.get("entry_price") or payload.get("price") or payload.get("close"))
        stop_price = self._float(payload.get("stop_price") or payload.get("stop"))
        if entry_price is None or stop_price is None:
            raise ValueError("signal payload requires entry_price/close and stop_price")
        metadata = {
            "play": payload.get("play", payload.get("reason", "tradingview_signal")),
            "entry_price": entry_price,
            "stop_price": stop_price,
            "order_type": order_type,
            "limit_price": self._float(payload.get("limit_price")),
            "timeframe": payload.get("timeframe"),
            "source": payload.get("source", "tradingview"),
            "timestamp": payload.get("timestamp") or payload.get("time"),
            "location": payload.get("location"),
            "close": self._float(payload.get("close")) or entry_price,
            # Multi-timeframe directional gate fields
            "tf15_bias": payload.get("tf15_bias", ""),
            "tf5_setup": payload.get("tf5_setup", ""),
            "tf2_trigger": payload.get("tf2_trigger", ""),
        }
        return Signal(symbol=symbol, side=side, reason=str(metadata["play"]), metadata=metadata)

    def _bar_from_payload(self, payload: dict) -> Bar:
        timestamp = self._timestamp(payload.get("timestamp") or payload.get("time"))
        values = {key: self._float(payload.get(key)) for key in ("open", "high", "low", "close")}
        missing = [key for key, value in values.items() if value is None]
        if missing:
            raise ValueError(f"bar payload missing {','.join(missing)}")
        return Bar(
            timestamp=timestamp,
            open=values["open"],
            high=values["high"],
            low=values["low"],
            close=values["close"],
            volume=self._float(payload.get("volume")) or 0.0,
        )

    def _symbol(self, payload: dict) -> str:
        symbol = str(payload.get("broker_symbol") or payload.get("symbol") or "").upper().strip()
        if not symbol:
            raise ValueError("payload requires symbol or broker_symbol")
        return symbol.replace("NASDAQ:", "").replace("NYSE:", "").replace("AMEX:", "")

    def _risk_budget(self, equity: float) -> float:
        equity_risk = equity * float(self.risk_config.get("risk_per_trade", 0.005))
        fixed_cap = self.risk_config.get("max_dollar_risk_per_trade")
        if fixed_cap is None:
            return equity_risk
        return min(equity_risk, float(fixed_cap))

    def _take_profit_price(self, side: str, entry_price: float, stop_price: float) -> Optional[float]:
        r_multiple = self.webhook_config.get("take_profit_r")
        if r_multiple is None:
            return None
        risk = abs(entry_price - stop_price)
        if side == "buy":
            return entry_price + float(r_multiple) * risk
        return entry_price - float(r_multiple) * risk

    def _execute_orders(self) -> bool:
        env_enabled = os.getenv("VELEZ_EXECUTE_ORDERS", "false").lower() == "true"
        return bool(self.webhook_config.get("execute_orders", False) and env_enabled)

    def _requires_order_approval(self) -> bool:
        configured = self.webhook_config.get("require_order_approval")
        if configured is not None:
            return bool(configured)
        return os.getenv("VELEZ_REQUIRE_ORDER_APPROVAL", "false").strip().lower() in {"1", "true", "yes", "on"}

    def _remember_decisions(self, decisions: List[WebhookDecision], alert_id: str) -> None:
        for decision in decisions:
            snapshot = self._decision_snapshot(decision, alert_id)
            self.recent_decisions.appendleft(snapshot)
            try:
                self.journal.record_decision(snapshot, decision.order_payload, decision.broker_response)
                self.ops_audit.record("webhook.decision", {"status": snapshot.get("status"), "reason": snapshot.get("reason"), "symbol": snapshot.get("symbol"), "side": snapshot.get("side"), "qty": snapshot.get("qty")})
            except Exception as exc:
                log_event(self.logger, "journal_record_failed", {"reason": str(exc), "alert_ref": snapshot.get("alert_ref")})

    def _decision_snapshot(self, decision: WebhookDecision, alert_id: str) -> dict:
        metadata = decision.metadata or {}
        source = metadata.get("source_metadata") if isinstance(metadata.get("source_metadata"), dict) else {}
        order_payload = decision.order_payload or {}
        stop_loss = order_payload.get("stop_loss") if isinstance(order_payload.get("stop_loss"), dict) else {}
        take_profit = order_payload.get("take_profit") if isinstance(order_payload.get("take_profit"), dict) else {}
        symbol = decision.symbol or source.get("symbol") or ""
        timeframe = source.get("timeframe")
        chart_url = source.get("chart_url") or source.get("tradingview_url")
        if not chart_url and symbol:
            chart_symbol = str(source.get("tv_symbol") or source.get("broker_symbol") or source.get("symbol") or symbol).upper()
            chart_url = f"https://www.tradingview.com/chart/?symbol={chart_symbol}"
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": decision.status,
            "reason": decision.reason,
            "symbol": symbol,
            "side": decision.side,
            "play": decision.play,
            "qty": decision.qty,
            "order_type": order_payload.get("type") or source.get("order_type"),
            "entry_price": source.get("entry_price") or source.get("close") or order_payload.get("limit_price"),
            "stop_price": stop_loss.get("stop_price") or source.get("stop_price"),
            "take_profit_price": take_profit.get("limit_price"),
            "timeframe": timeframe,
            "location": source.get("location"),
            "max_dollar_risk": metadata.get("max_dollar_risk"),
            "alert_ref": hashlib.sha1(str(alert_id).encode("utf-8")).hexdigest()[:10],
            "chart_context": {
                "url": chart_url,
                "symbol": symbol,
                "timeframe": timeframe,
                "source": source.get("source", "tradingview"),
                "screenshot_status": "server_saved_chart_context_only",
                "note": "The VPS stores chart context from the alert. Browser screenshots can be captured from the desk canvas; TradingView iframes cannot be screenshotted by the server.",
            },
        }

    def _positions_snapshot(self) -> tuple[List[dict], Optional[str]]:
        if not self.broker.is_configured():
            return [], None
        try:
            raw_positions = self.broker.get_positions_raw()
        except Exception as exc:
            return [], str(exc)
        return [self._position_snapshot(item) for item in raw_positions], None

    def _position_snapshot(self, item: dict) -> dict:
        fields = (
            "symbol",
            "qty",
            "side",
            "avg_entry_price",
            "current_price",
            "market_value",
            "unrealized_pl",
            "unrealized_plpc",
            "change_today",
        )
        return {field: item.get(field) for field in fields if field in item}

    def _alert_id(self, payload: dict) -> str:
        supplied = payload.get("id") or payload.get("alert_id")
        if supplied:
            return str(supplied)
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _timestamp(self, value: Any) -> datetime:
        if value is None or value == "":
            return datetime.now(timezone.utc)
        if isinstance(value, (int, float)):
            if value > 10_000_000_000:
                return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
            return datetime.fromtimestamp(value, tz=timezone.utc)
        text = str(value)
        if text.isdigit():
            return self._timestamp(int(text))
        return datetime.fromisoformat(text.replace("Z", "+00:00"))

    def _float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def create_app(config: dict):
    app = FastAPI(title="Trading Bull Desk Webhook", version="0.1.0")
    engine = TradingViewWebhookEngine(config)
    app.state.engine = engine
    app.state.apple_music = AppleMusicTokenService()
    app.state.ops_rbac = OpsRBAC()
    dashboard_dir = Path(__file__).resolve().parent / "static" / "dashboard"
    dashboard_index = dashboard_dir / "index.html"

    if dashboard_dir.exists():
        app.mount("/dashboard/assets", StaticFiles(directory=str(dashboard_dir)), name="dashboard-assets")

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/dashboard")

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard() -> FileResponse:
        if not dashboard_index.exists():
            raise HTTPException(status_code=404, detail="dashboard assets are missing")
        return FileResponse(dashboard_index)

    @app.get("/dashboard/", include_in_schema=False)
    async def dashboard_slash() -> FileResponse:
        if not dashboard_index.exists():
            raise HTTPException(status_code=404, detail="dashboard assets are missing")
        return FileResponse(dashboard_index)

    @app.get("/health")
    async def health() -> dict:
        broker_status = engine.broker.validate_connection() if engine.broker.is_configured() else {"ok": False, "reason": "missing_credentials"}
        return {
            "ok": True,
            "execution_armed": engine._execute_orders(),
            "broker": broker_status,
        }

    @app.get("/api/dashboard/state")
    async def dashboard_state() -> dict:
        return engine.dashboard_state()

    def _ops_token(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return request.headers.get("x-api-key", "")

    @app.get("/api/ops/whoami")
    async def ops_whoami(request: Request) -> JSONResponse:
        return JSONResponse(content=app.state.ops_rbac.identify(_ops_token(request)), headers={"Cache-Control": "no-store"})

    @app.get("/api/ops/audit")
    async def ops_audit(request: Request, limit: int = Query(80, ge=1, le=300)) -> JSONResponse:
        app.state.ops_rbac.require(_ops_token(request), "ops_read")
        return JSONResponse(content={"ok": True, "entries": engine.ops_audit.recent(limit)}, headers={"Cache-Control": "no-store"})

    @app.get("/api/ops/readiness")
    async def ops_readiness(request: Request) -> JSONResponse:
        app.state.ops_rbac.require(_ops_token(request), "ops_read")
        return JSONResponse(content=engine.ops_readiness(), headers={"Cache-Control": "no-store"})

    @app.get("/api/ops/uptime")
    async def ops_uptime() -> JSONResponse:
        return JSONResponse(content=engine.ops_uptime(), headers={"Cache-Control": "no-store"})

    @app.get("/api/safety/state")
    async def safety_state(request: Request) -> JSONResponse:
        app.state.ops_rbac.require(_ops_token(request), "ops_read")
        return JSONResponse(content=engine.safety.snapshot(), headers={"Cache-Control": "no-store"})

    @app.post("/api/safety/kill-switch")
    async def safety_kill_switch(request: Request) -> JSONResponse:
        actor = app.state.ops_rbac.require(_ops_token(request), "safety_toggle")
        payload = await _payload_from_request(request)
        result = engine.safety.set_kill_switch(bool(payload.get("enabled")), str(payload.get("reason", "")), actor.get("role", "ops"))
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.post("/api/safety/broker-pause")
    async def safety_broker_pause(request: Request) -> JSONResponse:
        actor = app.state.ops_rbac.require(_ops_token(request), "ops_write")
        payload = await _payload_from_request(request)
        result = engine.safety.set_broker_pause(bool(payload.get("paused")), str(payload.get("reason", "")), actor.get("role", "ops"))
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/burn-in/status")
    async def burn_in_status(request: Request) -> JSONResponse:
        app.state.ops_rbac.require(_ops_token(request), "ops_read")
        return JSONResponse(content=engine.burn_in.status(engine.journal.latest_decisions(limit=500)), headers={"Cache-Control": "no-store"})

    @app.post("/api/burn-in/start")
    async def burn_in_start(request: Request) -> JSONResponse:
        actor = app.state.ops_rbac.require(_ops_token(request), "ops_write")
        payload = await _payload_from_request(request)
        result = engine.burn_in.start(days=int(payload.get("days", 3) or 3), actor=actor.get("role", "ops"))
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.post("/api/burn-in/stop")
    async def burn_in_stop(request: Request) -> JSONResponse:
        actor = app.state.ops_rbac.require(_ops_token(request), "ops_write")
        return JSONResponse(content=engine.burn_in.stop(actor=actor.get("role", "ops")), headers={"Cache-Control": "no-store"})

    @app.get("/api/bot/health")
    async def bot_health() -> JSONResponse:
        result = await run_in_threadpool(engine.bot_health)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/calendar/month")
    async def calendar_month() -> JSONResponse:
        result = await run_in_threadpool(engine.calendar_month)
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/brief/daily")
    async def daily_brief() -> JSONResponse:
        result = await run_in_threadpool(engine.daily_brief_payload)
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/review/daily")
    async def daily_review() -> JSONResponse:
        result = await run_in_threadpool(engine.daily_review_payload)
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/journal/recent")
    async def journal_recent(
        limit: int = Query(40, ge=1, le=200),
        symbol: str = Query("", max_length=16),
        status: str = Query("", max_length=24),
    ) -> JSONResponse:
        result = await run_in_threadpool(engine.journal_payload, limit, symbol, status)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/watchlist")
    async def watchlist() -> JSONResponse:
        return JSONResponse(
            content={"ok": True, "symbols": engine.watchlist_symbols(include_disabled=True)},
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/watchlist")
    async def add_watchlist_symbol(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
            result = await run_in_threadpool(engine.add_watchlist_symbol, payload)
        except ValueError as exc:
            return JSONResponse(content={"ok": False, "reason": str(exc)}, status_code=400, headers={"Cache-Control": "no-store"})
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.delete("/api/watchlist/{symbol}")
    async def remove_watchlist_symbol(symbol: str) -> JSONResponse:
        result = await run_in_threadpool(engine.remove_watchlist_symbol, symbol)
        status_code = 200 if result.get("ok") else 404
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.get("/api/replay/latest")
    async def replay_latest() -> JSONResponse:
        return JSONResponse(
            content={"ok": True, "runs": engine.journal.latest_replays(limit=5)},
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/replay/run")
    async def replay_run(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(engine.replay_payload, payload)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/orders/pending")
    async def pending_orders(include_inactive: bool = Query(False)) -> JSONResponse:
        result = await run_in_threadpool(engine.pending_approvals, include_inactive)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.post("/api/orders/pending/{approval_id}/approve")
    async def approve_pending_order(approval_id: str, request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(
            engine.approve_pending_order,
            approval_id,
            str(payload.get("approval_phrase", "")),
            str(payload.get("approval_token", "")),
        )
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.get("/api/apple-music/developer-token")
    async def apple_music_developer_token() -> JSONResponse:
        result = app.state.apple_music.developer_token()
        status_code = 200 if result.get("ok") else 503
        return JSONResponse(
            content=result,
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/apple-music/search")
    async def apple_music_search(
        term: str = Query(..., min_length=1, max_length=80),
        storefront: str = Query("us", min_length=2, max_length=8),
        limit: int = Query(6, ge=1, le=12),
    ) -> JSONResponse:
        result = await run_in_threadpool(app.state.apple_music.catalog_search, term, storefront, limit)
        status_code = 200 if result.get("ok") else 503
        return JSONResponse(
            content=result,
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/winston/brief")
    async def winston_brief() -> JSONResponse:
        return JSONResponse(
            content=engine.winston_brief(),
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/winston/status")
    async def winston_status() -> JSONResponse:
        return JSONResponse(
            content=engine.winston.status(include_health_check=True),
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/winston/message")
    async def winston_message(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(engine.winston_reply, str(payload.get("message", "")))
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(
            content=result,
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/winston/research")
    async def winston_research(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(
            engine.winston_research,
            str(payload.get("topic", "")),
            str(payload.get("symbol", "")) if payload.get("symbol") else None,
        )
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.post("/api/winston/speech")
    async def winston_speech(request: Request) -> Response:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(engine.winston.synthesize_speech, str(payload.get("text", "")))
        if not result.get("ok"):
            return JSONResponse(
                content={key: value for key, value in result.items() if key != "content"},
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        content = result.get("content", b"")
        return Response(
            content=content,
            media_type=str(result.get("media_type") or "audio/mpeg"),
            headers={
                "Cache-Control": "no-store",
                "X-Winston-Voice": str(result.get("voice") or ""),
                "X-Winston-Provider": str(result.get("provider") or ""),
            },
        )

    @app.post("/webhook/tradingview")
    async def tradingview_webhook(request: Request, x_velez_secret: Optional[str] = Header(default=None)) -> dict:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = engine.handle_payload(payload, header_secret=x_velez_secret)
        if not result.get("ok") and result["decisions"][0]["status"] == "rejected":
            raise HTTPException(status_code=400, detail=result)
        return result

    @app.post("/webhook/tradingview/{token}")
    async def tradingview_webhook_with_token(request: Request, token: str) -> dict:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = engine.handle_payload(payload, path_token=token)
        if not result.get("ok") and result["decisions"][0]["status"] == "rejected":
            raise HTTPException(status_code=400, detail=result)
        return result

    return app


async def _payload_from_request(request) -> dict:
    body = await request.body()
    if not body:
        return {}
    text = body.decode("utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"TradingView webhook body must be valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("TradingView webhook JSON must be an object")
    return data


def run_webhook_server(config: dict, *, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(create_app(config), host=host, port=port)
