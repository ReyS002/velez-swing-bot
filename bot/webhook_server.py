from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import threading
import time
from copy import deepcopy
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional
from zoneinfo import ZoneInfo

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
from .brokers.simulated import SimulatedBroker
from .calendar_feeds import CalendarFeedService
from .core.risk import RiskManager
from .core.types import Bar, OrderType, Side, Signal
from .core.utils import get_logger, log_event
from .core.trifecta import check_trifecta
from .core.velez_strategy import VelezInstitutionalStrategy, calculate_pyramid_add_qty
from .core.velez_lot_sizing import build_lot_plan, public_lot_config
from .journal_store import JournalStore


DASHBOARD_VERSION = "v6.22"


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _dashboard_auth_configured() -> bool:
    return bool(os.getenv("VELEZ_DASHBOARD_USERNAME", "").strip() and os.getenv("VELEZ_DASHBOARD_PASSWORD", "").strip())


def dashboard_auth_enabled() -> bool:
    return _bool_env("VELEZ_DASHBOARD_AUTH_ENABLED", _dashboard_auth_configured())


def _dashboard_auth_failed() -> Response:
    return Response(
        content="Trading Bull Desk authentication required",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Trading Bull Desk"', "Cache-Control": "no-store"},
    )


def _dashboard_auth_missing_config() -> Response:
    return Response(
        content="Trading Bull Desk authentication is enabled but credentials are not configured",
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )


def _dashboard_auth_allowed(request: Request) -> bool:
    username = os.getenv("VELEZ_DASHBOARD_USERNAME", "").strip()
    password = os.getenv("VELEZ_DASHBOARD_PASSWORD", "").strip()
    if not username or not password:
        return False
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "basic" or not token:
        return False
    try:
        import base64

        decoded = base64.b64decode(token, validate=True).decode("utf-8")
    except Exception:
        return False
    supplied_username, separator, supplied_password = decoded.partition(":")
    if separator != ":":
        return False
    return secrets.compare_digest(supplied_username, username) and secrets.compare_digest(supplied_password, password)


def _is_dashboard_surface(path: str) -> bool:
    return path in {"/", "/dashboard", "/dashboard/"} or path.startswith("/dashboard/assets") or path.startswith("/api/")


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
        elif include_health_check and configured and provider == "openai_compatible":
            api_key = os.getenv("WINSTON_LLM_API_KEY", "").strip()
            available = self._openai_compatible_available(base_url, api_key)
            detail = "AI provider reachable" if available else "AI provider not reachable"
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
            "thinking": self._openai_thinking_value("WINSTON_LLM"),
            "reasoning_effort": os.getenv("WINSTON_LLM_REASONING_EFFORT", "").strip() or None,
            "fallback": self._fallback_status("WINSTON_LLM_FALLBACK"),
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
            reply = self._reply_with_provider(provider, prompt)
        except Exception as exc:
            fallback_result = self._fallback_reply(prompt, exc)
            if fallback_result:
                response = dict(fallback)
                response.update(
                    {
                        "ok": True,
                        "intent": "ai_assistant",
                        "reply": fallback_result["reply"],
                        "provider": fallback_result["provider"],
                        "model": fallback_result["model"],
                        "llm_used": True,
                        "degraded": True,
                        "fallback_from": provider,
                        "fallback_reason": str(exc),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                return response
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

    def research_reply(self, topic: str, context: dict, fallback: dict, *, deep: bool = False) -> dict:
        provider_env = "WINSTON_DEEP_RESEARCH_LLM_PROVIDER" if deep else "WINSTON_RESEARCH_LLM_PROVIDER"
        provider = self._canonical_provider(os.getenv(provider_env, os.getenv("WINSTON_RESEARCH_LLM_PROVIDER", ""))) or self._llm_provider()
        if provider == "rule_based":
            return fallback

        try:
            reply = self._research_with_provider(provider, topic, context, deep=deep)
        except Exception as exc:
            fallback_result = self._fallback_research_reply(topic, context, exc, deep=deep)
            if fallback_result:
                response = dict(fallback)
                response.update(
                    {
                        "ok": True,
                        "reply": fallback_result["reply"],
                        "provider": fallback_result["provider"],
                        "model": fallback_result["model"],
                        "research_used": True,
                        "degraded": True,
                        "fallback_from": provider,
                        "fallback_reason": str(exc),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                return response
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
        model_env = "WINSTON_DEEP_RESEARCH_LLM_MODEL" if deep else "WINSTON_RESEARCH_LLM_MODEL"
        response.update(
            {
                "ok": True,
                "reply": reply,
                "provider": provider,
                "model": os.getenv(model_env, os.getenv("WINSTON_RESEARCH_LLM_MODEL", os.getenv("WINSTON_LLM_MODEL", "qwen3:1.7b"))).strip(),
                "research_used": True,
                "degraded": False,
                "mode": "deep_research" if deep else "research",
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

    def _reply_with_provider(self, provider: str, prompt: str) -> str:
        if provider == "ollama":
            return self._ollama_reply(prompt)
        if provider == "openai_compatible":
            return self._openai_compatible_reply(prompt)
        raise ValueError(f"unsupported_winston_llm_provider:{provider}")

    def _research_with_provider(self, provider: str, topic: str, context: dict, *, deep: bool = False) -> str:
        if provider == "ollama":
            return self._ollama_research_reply(topic, context, deep=deep)
        if provider == "openai_compatible":
            return self._openai_research_reply(topic, context, deep=deep)
        raise ValueError(f"unsupported_winston_research_provider:{provider}")

    def _ollama_reply(self, prompt: str, *, fallback: bool = False) -> str:
        prefix = "WINSTON_LLM_FALLBACK" if fallback else "WINSTON_LLM"
        base_url = os.getenv(f"{prefix}_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
        model = os.getenv(f"{prefix}_MODEL", "qwen3:1.7b").strip()
        if not base_url or not model:
            raise ValueError("ollama_provider_not_configured")
        payload = {
            "model": model,
            "messages": self._messages(prompt),
            "stream": False,
            "options": {
                "temperature": self._float_env(f"{prefix}_TEMPERATURE", 0.25),
                "num_predict": self._int_env(f"{prefix}_MAX_TOKENS", 180),
            },
        }
        think = self._optional_bool_env(f"{prefix}_THINK")
        if think is not None:
            payload["think"] = think
        response = requests.post(f"{base_url}/api/chat", json=payload, timeout=self._float_env(f"{prefix}_TIMEOUT_SECONDS", 20.0))
        response.raise_for_status()
        data = response.json()
        return self._clean_reply(data.get("message", {}).get("content"))

    def _ollama_research_reply(self, topic: str, context: dict, *, fallback: bool = False, deep: bool = False) -> str:
        if fallback:
            base_url = os.getenv("WINSTON_RESEARCH_FALLBACK_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
            model = os.getenv("WINSTON_RESEARCH_FALLBACK_MODEL", "qwen3.5:2b").strip()
            temp_env = "WINSTON_RESEARCH_FALLBACK_TEMPERATURE"
            tokens_env = "WINSTON_RESEARCH_FALLBACK_MAX_TOKENS"
            think_env = "WINSTON_RESEARCH_FALLBACK_THINK"
            timeout_env = "WINSTON_RESEARCH_FALLBACK_TIMEOUT_SECONDS"
        elif deep:
            base_url = os.getenv("WINSTON_DEEP_RESEARCH_LLM_BASE_URL", os.getenv("WINSTON_RESEARCH_LLM_BASE_URL", os.getenv("WINSTON_LLM_BASE_URL", "http://127.0.0.1:11434"))).strip().rstrip("/")
            model = os.getenv("WINSTON_DEEP_RESEARCH_LLM_MODEL", os.getenv("WINSTON_RESEARCH_LLM_MODEL", os.getenv("WINSTON_LLM_MODEL", "qwen3:1.7b"))).strip()
            temp_env = "WINSTON_DEEP_RESEARCH_TEMPERATURE"
            tokens_env = "WINSTON_DEEP_RESEARCH_MAX_TOKENS"
            think_env = "WINSTON_DEEP_RESEARCH_THINK"
            timeout_env = "WINSTON_DEEP_RESEARCH_TIMEOUT_SECONDS"
        else:
            base_url = os.getenv("WINSTON_RESEARCH_LLM_BASE_URL", os.getenv("WINSTON_LLM_BASE_URL", "http://127.0.0.1:11434")).strip().rstrip("/")
            model = os.getenv("WINSTON_RESEARCH_LLM_MODEL", os.getenv("WINSTON_LLM_MODEL", "qwen3:1.7b")).strip()
            temp_env = "WINSTON_RESEARCH_TEMPERATURE"
            tokens_env = "WINSTON_RESEARCH_MAX_TOKENS"
            think_env = "WINSTON_RESEARCH_THINK"
            timeout_env = "WINSTON_RESEARCH_TIMEOUT_SECONDS"
        if not base_url or not model:
            raise ValueError("ollama_research_provider_not_configured")
        payload = {
            "model": model,
            "messages": self._research_messages(topic, context, deep=deep),
            "stream": False,
            "options": {
                "temperature": self._float_env(temp_env, 0.2),
                "num_predict": self._int_env(tokens_env, 1200 if deep else 700),
            },
        }
        think = self._optional_bool_env(think_env)
        if think is not None:
            payload["think"] = think
        response = requests.post(f"{base_url}/api/chat", json=payload, timeout=self._float_env(timeout_env, 90.0))
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
        payload.update(self._openai_extra_body("WINSTON_LLM"))
        response = requests.post(url, headers=headers, json=payload, timeout=self._float_env("WINSTON_LLM_TIMEOUT_SECONDS", 20.0))
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("llm_returned_no_choices")
        return self._clean_reply(choices[0].get("message", {}).get("content"))

    def _openai_research_reply(self, topic: str, context: dict, *, deep: bool = False) -> str:
        if deep:
            base_url = os.getenv("WINSTON_DEEP_RESEARCH_LLM_BASE_URL", os.getenv("WINSTON_RESEARCH_LLM_BASE_URL", os.getenv("WINSTON_LLM_BASE_URL", ""))).strip().rstrip("/")
            model = os.getenv("WINSTON_DEEP_RESEARCH_LLM_MODEL", os.getenv("WINSTON_RESEARCH_LLM_MODEL", os.getenv("WINSTON_LLM_MODEL", ""))).strip()
            api_key = os.getenv("WINSTON_DEEP_RESEARCH_LLM_API_KEY", os.getenv("WINSTON_RESEARCH_LLM_API_KEY", os.getenv("WINSTON_LLM_API_KEY", ""))).strip()
            prefix = "WINSTON_DEEP_RESEARCH"
            temp_env = "WINSTON_DEEP_RESEARCH_TEMPERATURE"
            tokens_env = "WINSTON_DEEP_RESEARCH_MAX_TOKENS"
            timeout_env = "WINSTON_DEEP_RESEARCH_TIMEOUT_SECONDS"
            default_tokens = 1400
        else:
            base_url = os.getenv("WINSTON_RESEARCH_LLM_BASE_URL", os.getenv("WINSTON_LLM_BASE_URL", "")).strip().rstrip("/")
            model = os.getenv("WINSTON_RESEARCH_LLM_MODEL", os.getenv("WINSTON_LLM_MODEL", "")).strip()
            api_key = os.getenv("WINSTON_RESEARCH_LLM_API_KEY", os.getenv("WINSTON_LLM_API_KEY", "")).strip()
            prefix = "WINSTON_RESEARCH"
            temp_env = "WINSTON_RESEARCH_TEMPERATURE"
            tokens_env = "WINSTON_RESEARCH_MAX_TOKENS"
            timeout_env = "WINSTON_RESEARCH_TIMEOUT_SECONDS"
            default_tokens = 700
        if not base_url or not model:
            raise ValueError("openai_research_provider_not_configured")
        url = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": self._research_messages(topic, context, deep=deep),
            "temperature": self._float_env(temp_env, 0.18 if deep else 0.2),
            "max_tokens": self._int_env(tokens_env, default_tokens),
        }
        payload.update(self._openai_extra_body(prefix))
        response = requests.post(url, headers=headers, json=payload, timeout=self._float_env(timeout_env, 120.0 if deep else 90.0))
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
                "lifecycle": state.get("lifecycle"),
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
                    "When describing your abilities, say you can brief the desk, read watchlists/positions/risk, read active trade lifecycle, run Research Mode, route iPod and panel commands, and read back guarded approval status. "
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

    def _research_messages(self, topic: str, context: dict, *, deep: bool = False) -> List[dict]:
        if deep:
            instruction = (
                "You are Winston Deep Research Mode inside Trading Bull Desk. "
                "Produce a stronger trader prep memo from the provided context only: thesis, catalyst map, technical watch areas, risks, missing data, and next questions. "
                "Separate facts from inference, call out stale or missing data, and avoid personalized financial advice. "
                "Do not say you can trade. Do not invent news, prices, earnings, or fundamentals that are not present."
            )
            context_chars = self._int_env("WINSTON_DEEP_RESEARCH_CONTEXT_CHARS", 11000)
        else:
            instruction = (
                "You are Winston Research Mode inside Trading Bull Desk. "
                "Produce a concise trader prep note from the provided context only. "
                "Separate facts from inference, call out stale or missing data, and avoid personalized financial advice. "
                "Do not say you can trade. Do not invent news, prices, earnings, or fundamentals that are not present."
            )
            context_chars = self._int_env("WINSTON_RESEARCH_CONTEXT_CHARS", 7000)
        return [
            {
                "role": "system",
                "content": instruction,
            },
            {
                "role": "user",
                "content": (
                    f"Research topic: {topic.strip()[:500]}\n\n"
                    f"Context JSON:\n{json.dumps(context, default=str)[:context_chars]}"
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
        return self._canonical_provider(os.getenv("WINSTON_LLM_PROVIDER", "rule_based")) or "rule_based"

    def _canonical_provider(self, provider: str) -> str:
        provider = str(provider or "").strip().lower().replace("-", "_")
        if not provider:
            return ""
        aliases = {
            "none": "rule_based",
            "off": "rule_based",
            "disabled": "rule_based",
            "local": "ollama",
            "hermes": "ollama",
            "openai": "openai_compatible",
            "deepseek": "openai_compatible",
            "deepseek_api": "openai_compatible",
        }
        return aliases.get(provider, provider)

    def _fallback_status(self, prefix: str) -> Optional[dict]:
        provider = self._canonical_provider(os.getenv(f"{prefix}_PROVIDER", ""))
        if not provider or provider == "rule_based":
            return None
        model = os.getenv(f"{prefix}_MODEL", "").strip()
        base_url = os.getenv(f"{prefix}_BASE_URL", "").strip().rstrip("/")
        return {
            "provider": provider,
            "model": model,
            "configured": bool(model and base_url),
            "base_url": base_url,
        }

    def _fallback_reply(self, prompt: str, cause: Exception) -> Optional[dict]:
        provider = self._canonical_provider(os.getenv("WINSTON_LLM_FALLBACK_PROVIDER", ""))
        if not provider or provider == "rule_based":
            return None
        try:
            if provider == "ollama":
                reply = self._ollama_reply(prompt, fallback=True)
                model = os.getenv("WINSTON_LLM_FALLBACK_MODEL", "qwen3:1.7b").strip()
            else:
                raise ValueError(f"unsupported_winston_fallback_provider:{provider}")
        except Exception:
            return None
        return {"provider": provider, "model": model, "reply": reply, "cause": str(cause)}

    def _fallback_research_reply(self, topic: str, context: dict, cause: Exception, *, deep: bool = False) -> Optional[dict]:
        provider = self._canonical_provider(os.getenv("WINSTON_RESEARCH_FALLBACK_PROVIDER", ""))
        if not provider or provider == "rule_based":
            return None
        try:
            if provider == "ollama":
                reply = self._ollama_research_reply(topic, context, fallback=True, deep=deep)
                model = os.getenv("WINSTON_RESEARCH_FALLBACK_MODEL", "qwen3.5:2b").strip()
            else:
                raise ValueError(f"unsupported_winston_research_fallback_provider:{provider}")
        except Exception:
            return None
        return {"provider": provider, "model": model, "reply": reply, "cause": str(cause)}

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

    def _openai_compatible_available(self, base_url: str, api_key: str = "") -> bool:
        root = base_url.rstrip("/")
        url = f"{root}/models" if root.endswith("/v1") else f"{root}/v1/models"
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = requests.get(url, headers=headers, timeout=2.5)
            return response.status_code < 400
        except requests.RequestException:
            return False

    def _openai_extra_body(self, prefix: str) -> dict:
        extras: dict = {}
        thinking = self._openai_thinking_value(prefix)
        if thinking:
            extras["thinking"] = {"type": thinking}
        reasoning_effort = os.getenv(f"{prefix}_REASONING_EFFORT", "").strip()
        if reasoning_effort:
            extras["reasoning_effort"] = reasoning_effort
        for name in (f"{prefix}_EXTRA_BODY_JSON", f"{prefix}_LLM_EXTRA_BODY_JSON"):
            raw = os.getenv(name, "").strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid_{name.lower()}") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"{name.lower()}_must_be_object")
            extras.update(parsed)
        return extras

    def _openai_thinking_value(self, prefix: str) -> Optional[str]:
        raw = os.getenv(f"{prefix}_THINKING", "").strip().lower()
        raw = raw or os.getenv(f"{prefix}_LLM_THINKING", "").strip().lower()
        if raw in {"enabled", "disabled", "auto"}:
            return raw
        bool_value = self._optional_bool_env(f"{prefix}_THINK")
        if bool_value is None:
            return None
        return "enabled" if bool_value else "disabled"

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



def _create_broker():
    """Auto-detect broker: Alpaca if keys present, Simulated otherwise."""
    alpaca = AlpacaPaperBroker()
    if alpaca.is_configured():
        return alpaca
    return SimulatedBroker()


class TradingViewWebhookEngine:
    def __init__(self, config: dict, broker: Optional[Any] = None) -> None:
        self.config = config
        self.webhook_config = config.get("webhook", {})
        self.scanner_config = config.get("scanner", {})
        self.risk_config = config.get("risk", {})
        self.symbol_config = {item["symbol"]: item for item in config.get("symbols", [])}
        self.logger = get_logger("tradingview_webhook")
        self.strategy = VelezInstitutionalStrategy(config.get("velez_strategy", config.get("strategy", {})), self.logger)
        self.risk = RiskManager(self.risk_config)
        self.broker = broker or _create_broker()
        self.seen_alert_ids: Deque[str] = deque(maxlen=self.webhook_config.get("dedupe_cache_size", 1000))
        self.recent_decisions: Deque[dict] = deque(maxlen=self.webhook_config.get("dashboard_decisions", 80))
        self.started_at = datetime.now(timezone.utc)
        self.journal = JournalStore(self.config)
        self.winston = WinstonAIService(self)
        self.calendar = CalendarFeedService(self.broker, self.config, self.recent_decisions, journal=self.journal)
        self.scanner_strategy = VelezInstitutionalStrategy(config.get("velez_strategy", config.get("strategy", {})), self.logger)
        self.scanner_last_bar: Dict[str, datetime] = {}
        self.scanner_seen_alerts: Deque[str] = deque(maxlen=int(self.scanner_config.get("dedupe_cache_size", 1000) or 1000))
        self.scanner_symbol_cooldowns: Dict[str, datetime] = {}
        self.scanner_thread: Optional[threading.Thread] = None
        self.scanner_stop = threading.Event()
        self.scanner_lock = threading.Lock()
        self.notification_cache: Dict[str, datetime] = {}
        self.scanner_status: dict = {
            "enabled": bool(self.scanner_config.get("enabled", False)),
            "running": False,
            "mode": "warming",
            "control_mode": self._scanner_control_mode(),
            "last_scan_at": None,
            "last_error": None,
            "symbols_scanned": 0,
            "signals_found": 0,
            "skipped": [],
            "decisions": [],
            "pause": {"paused": False, "reason": None},
            "exposure": {},
            "today": self._scanner_today_summary(),
        }

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
            "dashboard_version": DASHBOARD_VERSION,
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
                "lot_sizing": public_lot_config(self.risk_config.get("lot_sizing")),
            },
            "guardrails": {
                "paper_only": self.webhook_config.get("paper_only", True),
                "time_in_force": self.webhook_config.get("time_in_force", "day"),
                "take_profit_r": self.webhook_config.get("take_profit_r"),
                "auth_required": self.webhook_config.get("auth_required", True),
                "approval_required": self._requires_order_approval(),
                "approval_mode_source": self._approval_mode_source(),
            },
            "symbols": symbols,
            "scanner": self.scanner_public_status(),
            "recent_decisions": recent,
            "pending_approvals": self.journal.public_pending_orders(),
            "alert_coverage": self.alert_coverage_payload(light=True),
            "lifecycle": self.lifecycle_payload(light=True, refresh=False),
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

    def scanner_public_status(self) -> dict:
        with self.scanner_lock:
            status = deepcopy(self.scanner_status)
        control_mode = self._scanner_control_mode()
        exposure = self._scanner_exposure_snapshot() if control_mode == "auto_submit" else status.get("exposure") or self._scanner_exposure_snapshot()
        status["control_mode"] = control_mode
        status["exposure"] = exposure
        status["config"] = {
            "enabled": bool(self.scanner_config.get("enabled", False)),
            "timeframe": str(self.scanner_config.get("timeframe", "1Min")),
            "interval_seconds": int(self.scanner_config.get("interval_seconds", 60) or 60),
            "history_bars": int(self.scanner_config.get("history_bars", 260) or 260),
            "auto_submit": control_mode == "auto_submit",
            "supported_assets": ["equity", "stock", "crypto", "future"],
            "futures_provider": str(self.scanner_config.get("futures_provider", "polygon")).lower(),
            "futures_configured": bool(self._polygon_api_key()),
            "futures_contracts": self.scanner_config.get("futures_contracts", {}),
            "note": "Hybrid scanner warms up first, then scans newly closed bars and routes signals through the same Velez/risk guardrails as TradingView. Futures use Polygon when POLYGON_API_KEY is configured.",
            "symbol_cooldown_seconds": self._scanner_symbol_cooldown_seconds(),
        }
        status["today"] = self._scanner_today_summary()
        return status

    def scanner_quality_payload(self, limit: int = 80) -> dict:
        entries = self._scanner_quality_entries(limit=limit)
        replayed = [self._scanner_quality_entry(item) for item in entries]
        counts = Counter(str(item.get("status") or "unknown") for item in replayed)
        outcome_counts = Counter(str((item.get("forward_outcome") or {}).get("outcome") or "unknown") for item in replayed)
        symbol_stats = self._scanner_symbol_stats(replayed)
        session_stats = self._scanner_session_stats(replayed)
        recommendations = self._watchlist_quality_recommendations(symbol_stats=symbol_stats, entries=replayed)
        return {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total": len(replayed),
                "accepted": counts.get("submitted", 0) + counts.get("proposed", 0) + counts.get("diagnostic", 0),
                "rejected": counts.get("rejected", 0),
                "skipped": counts.get("skipped", 0),
                "would_win": outcome_counts.get("hit_1r", 0) + outcome_counts.get("hit_2r", 0),
                "would_stop": outcome_counts.get("stopped", 0),
                "readback": self._scanner_quality_readback(replayed, symbol_stats),
            },
            "entries": replayed,
            "symbol_stats": symbol_stats,
            "session_stats": session_stats,
            "watchlist_recommendations": recommendations,
            "filters": self._scanner_session_filter_config(),
            "note": "Scanner Quality is measurement-only. It never submits broker orders.",
        }

    def watchlist_quality_payload(self) -> dict:
        quality = self.scanner_quality_payload(limit=120)
        actions = self.journal.get_setting("scanner.watchlist_quality_actions", {}) or {}
        symbols = []
        recommendation_by_symbol = {item.get("symbol"): item for item in quality.get("watchlist_recommendations", [])}
        for item in self.watchlist_symbols(include_disabled=True):
            symbol = item.get("symbol")
            symbols.append({
                **item,
                "quality": recommendation_by_symbol.get(symbol, {"symbol": symbol, "state": "keep_watching", "reason": "No scanner quality sample yet."}),
                "lane_action": actions.get(symbol, {}),
            })
        return {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbols": symbols,
            "recommendations": quality.get("watchlist_recommendations", []),
            "summary": quality.get("summary", {}),
            "note": "Watchlist Quality Manager recommends lane tuning. Applying changes requires the approval token.",
        }

    def apply_watchlist_quality_action(self, symbol: str, action: str, approval_token: str) -> dict:
        auth = self._authorize_approval_token(approval_token)
        if not auth.get("ok"):
            return auth
        cleaned_symbol = str(symbol or "").upper().strip()
        cleaned_action = str(action or "").lower().strip().replace("-", "_")
        allowed = {"promote", "keep_watching", "cool_down", "disable", "enable"}
        if cleaned_action not in allowed:
            return {"ok": False, "reason": "invalid_quality_action", "allowed": sorted(allowed)}
        row = self.journal.get_watchlist_symbol(cleaned_symbol)
        if not row:
            return {"ok": False, "reason": "watchlist_symbol_not_found"}
        if cleaned_action == "disable":
            self.journal.set_watchlist_enabled(cleaned_symbol, False)
        elif cleaned_action == "enable":
            self.journal.set_watchlist_enabled(cleaned_symbol, True)
        actions = self.journal.get_setting("scanner.watchlist_quality_actions", {}) or {}
        actions[cleaned_symbol] = {
            "action": cleaned_action,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.journal.set_setting("scanner.watchlist_quality_actions", actions)
        return {
            "ok": True,
            "symbol": cleaned_symbol,
            "action": cleaned_action,
            "watchlist_quality": self.watchlist_quality_payload(),
            "scanner": self.scanner_public_status(),
        }

    def send_scanner_quality_report(self, approval_token: str) -> dict:
        auth = self._authorize_approval_token(approval_token)
        if not auth.get("ok"):
            return auth
        quality = self.scanner_quality_payload(limit=120)
        recommendations = quality.get("watchlist_recommendations", [])
        best = next((item for item in recommendations if item.get("state") == "promote"), recommendations[0] if recommendations else {})
        worst = next((item for item in recommendations if item.get("state") == "disable_candidate"), recommendations[-1] if recommendations else {})
        summary = quality.get("summary", {})
        detail = (
            f"Scanner quality: {summary.get('total', 0)} events, {summary.get('would_win', 0)} replay wins, "
            f"{summary.get('would_stop', 0)} replay stops. Best: {best.get('symbol', 'N/A')} {best.get('state', '')}. "
            f"Watch: {worst.get('symbol', 'N/A')} {worst.get('state', '')}."
        )
        self._notify_event(
            key=f"scanner-quality-report:{datetime.now(timezone.utc).date().isoformat()}",
            title="Trading Bull scanner quality report",
            detail=detail,
            severity="info",
            payload={"kind": "scanner_quality_report", "timestamp": datetime.now(timezone.utc).isoformat(), "quality": quality},
            ignore_cooldown=True,
        )
        return {"ok": True, "message": detail, "quality": quality}

    def set_scanner_control_mode(self, mode: str, approval_token: str) -> dict:
        auth = self._authorize_approval_token(approval_token)
        if not auth.get("ok"):
            return auth
        cleaned = str(mode or "").strip().lower().replace("-", "_")
        aliases = {
            "auto": "auto_submit",
            "auto_submit": "auto_submit",
            "diagnostic": "diagnostic",
            "diagnostic_only": "diagnostic",
            "paper": "auto_submit",
            "paused": "paused",
            "pause": "paused",
            "off": "paused",
        }
        control_mode = aliases.get(cleaned)
        if not control_mode:
            return {"ok": False, "reason": "invalid_scanner_mode", "allowed": ["auto_submit", "diagnostic", "paused"]}
        self.journal.set_setting("scanner.control_mode", control_mode)
        self._update_scanner_status(control_mode=control_mode)
        return {"ok": True, "changed": True, "mode": control_mode, "scanner": self.scanner_public_status()}

    def start_scanner(self) -> None:
        if not bool(self.scanner_config.get("enabled", False)):
            self._update_scanner_status(running=False, mode="disabled", enabled=False)
            return
        if self.scanner_thread and self.scanner_thread.is_alive():
            return
        self.scanner_stop.clear()
        self.scanner_thread = threading.Thread(target=self._scanner_loop, name="velez-watchlist-scanner", daemon=True)
        self.scanner_thread.start()
        self._update_scanner_status(running=True, mode="warming", enabled=True)

    def stop_scanner_worker(self) -> None:
        self.scanner_stop.set()
        if self.scanner_thread and self.scanner_thread.is_alive():
            self.scanner_thread.join(timeout=5)
        self._update_scanner_status(running=False)

    def scanner_scan_once(self) -> dict:
        now = datetime.now(timezone.utc)
        control_mode = self._scanner_control_mode()
        symbols = self._scanner_symbols()
        symbols_scanned = 0
        signals_found = 0
        decisions_out: List[dict] = []
        errors: List[str] = []
        skipped: List[str] = []
        warmed = 0
        exposure = self._scanner_exposure_snapshot()
        pause = {"paused": False, "reason": None}
        if control_mode == "paused":
            pause = {"paused": True, "reason": "operator_paused", "detail": "Scanner is paused by operator control."}
            status = {
                "enabled": bool(self.scanner_config.get("enabled", False)),
                "running": bool(self.scanner_thread and self.scanner_thread.is_alive()),
                "mode": "paused",
                "control_mode": control_mode,
                "last_scan_at": now.isoformat(),
                "last_error": None,
                "symbols_scanned": 0,
                "signals_found": 0,
                "warmed_symbols": 0,
                "skipped": ["all:operator_paused"],
                "decisions": [],
                "pause": pause,
                "exposure": exposure,
                "today": self._scanner_today_summary(),
            }
            self._update_scanner_status(**status)
            return status
        if self._scanner_should_pause_for_exposure(exposure):
            pause = {
                "paused": True,
                "reason": "max_exposure_reached",
                "detail": f"{exposure.get('active_exposure', 0)} active exposures; max is {exposure.get('max_open_positions', 0)}.",
            }
            status = {
                "enabled": bool(self.scanner_config.get("enabled", False)),
                "running": bool(self.scanner_thread and self.scanner_thread.is_alive()),
                "mode": "paused",
                "control_mode": control_mode,
                "last_scan_at": now.isoformat(),
                "last_error": None,
                "symbols_scanned": 0,
                "signals_found": 0,
                "warmed_symbols": 0,
                "skipped": [f"all:{pause['reason']}"],
                "decisions": [],
                "pause": pause,
                "exposure": exposure,
                "today": self._scanner_today_summary(),
            }
            self._update_scanner_status(**status)
            self._notify_scanner_exposure_transition(True, exposure)
            self._notify_exposure_reduction_prompt(exposure)
            log_event(self.logger, "scanner_scan_paused", {key: value for key, value in status.items() if key != "decisions"})
            return status
        self._notify_scanner_exposure_transition(False, exposure)
        lifecycle_pause = self._scanner_lifecycle_pause()
        if lifecycle_pause.get("paused"):
            status = {
                "enabled": bool(self.scanner_config.get("enabled", False)),
                "running": bool(self.scanner_thread and self.scanner_thread.is_alive()),
                "mode": "paused",
                "control_mode": control_mode,
                "last_scan_at": now.isoformat(),
                "last_error": None,
                "symbols_scanned": 0,
                "signals_found": 0,
                "warmed_symbols": 0,
                "skipped": [f"all:{lifecycle_pause['reason']}"],
                "decisions": [],
                "pause": lifecycle_pause,
                "exposure": exposure,
                "today": self._scanner_today_summary(),
            }
            self._update_scanner_status(**status)
            log_event(self.logger, "scanner_scan_paused", {key: value for key, value in status.items() if key != "decisions"})
            return status

        for item in symbols:
            symbol = str(item.get("symbol") or "").upper().strip()
            asset_type = str(item.get("type") or item.get("asset_type") or "equity").lower()
            if not symbol:
                continue
            if asset_type not in {"equity", "stock", "crypto", "future", "futures"}:
                skipped.append(f"{symbol}:unsupported_asset:{asset_type}")
                continue
            if asset_type in {"future", "futures"} and not self._polygon_api_key():
                skipped.append(f"{symbol}:polygon_key_missing")
                continue
            session_block = self._scanner_session_block(symbol=symbol, asset_type=asset_type, now=now)
            if session_block:
                skipped.append(f"{symbol}:session:{session_block['reason']}")
                self._record_scanner_skip(symbol, f"session:{session_block['reason']}", session_block)
                continue
            try:
                bars = self._fetch_scanner_bars(symbol=symbol, asset_type=asset_type)
            except Exception as exc:
                errors.append(f"{symbol}:{exc}")
                continue
            closed = [bar for bar in bars if self._scanner_bar_is_closed(bar, now)]
            if not closed:
                continue
            symbols_scanned += 1
            last_seen = self.scanner_last_bar.get(symbol)
            if last_seen is None:
                for bar in closed:
                    self.scanner_strategy.on_bar(symbol, bar)
                self.scanner_last_bar[symbol] = closed[-1].timestamp
                warmed += 1
                continue
            new_bars = [bar for bar in closed if bar.timestamp > last_seen]
            for bar in new_bars:
                signals = self.scanner_strategy.on_bar(symbol, bar)
                self.scanner_last_bar[symbol] = bar.timestamp
                for signal in signals:
                    cooldown = self._scanner_symbol_cooldown(symbol, now)
                    if cooldown:
                        skipped.append(f"{symbol}:cooldown:{cooldown['reason']}")
                        continue
                    alert_id = self._scanner_alert_id(signal, bar)
                    if alert_id in self.scanner_seen_alerts:
                        continue
                    self.scanner_seen_alerts.append(alert_id)
                    signal.metadata["source"] = "vps_scanner"
                    signal.metadata["timeframe"] = str(self.scanner_config.get("timeframe", "1Min"))
                    signal.metadata["timestamp"] = bar.timestamp.isoformat()
                    signal.metadata["scanner"] = True
                    decision = self._build_order_decision(
                        signal,
                        alert_id,
                        dry_run=control_mode != "auto_submit",
                    )
                    self._remember_decisions([decision], alert_id)
                    self._record_scanner_symbol_cooldown(symbol, decision, now)
                    signals_found += 1
                    decisions_out.append(self._decision_snapshot(decision, alert_id))

        mode = "active" if self.scanner_last_bar else "warming"
        if skipped and all(":cooldown:" in item for item in skipped):
            mode = "cooldown"
        status = {
            "enabled": bool(self.scanner_config.get("enabled", False)),
            "running": bool(self.scanner_thread and self.scanner_thread.is_alive()),
            "mode": mode,
            "control_mode": control_mode,
            "last_scan_at": now.isoformat(),
            "last_error": "; ".join(errors[-4:]) if errors else None,
            "symbols_scanned": symbols_scanned,
            "signals_found": signals_found,
            "warmed_symbols": warmed,
            "skipped": skipped[-8:],
            "decisions": decisions_out[-8:],
            "pause": pause,
            "exposure": exposure,
            "today": self._scanner_today_summary(),
        }
        self._update_scanner_status(**status)
        log_event(self.logger, "scanner_scan_complete", {key: value for key, value in status.items() if key != "decisions"})
        return status

    def _scanner_loop(self) -> None:
        interval = max(15, int(self.scanner_config.get("interval_seconds", 60) or 60))
        self._update_scanner_status(running=True, mode="warming")
        while not self.scanner_stop.is_set():
            try:
                self.scanner_scan_once()
            except Exception as exc:  # pragma: no cover - worker safety net.
                self._update_scanner_status(last_error=str(exc), mode="error")
                log_event(self.logger, "scanner_scan_failed", {"reason": str(exc)})
            self.scanner_stop.wait(interval)
        self._update_scanner_status(running=False)

    def _scanner_symbols(self) -> List[dict]:
        configured = self.watchlist_symbols()
        allow = {
            str(item).upper().strip()
            for item in self.scanner_config.get("symbols", [])
            if str(item).strip()
        }
        exclude = {
            str(item).upper().strip()
            for item in self.scanner_config.get("exclude_symbols", [])
            if str(item).strip()
        }
        result = []
        for item in configured:
            symbol = str(item.get("symbol") or "").upper().strip()
            if not symbol or symbol in exclude:
                continue
            if allow and symbol not in allow:
                continue
            result.append(item)
        max_symbols = int(self.scanner_config.get("max_symbols", 25) or 25)
        return result[: max(1, max_symbols)]

    def _scanner_control_mode(self) -> str:
        configured = "auto_submit" if bool(self.scanner_config.get("auto_submit", True)) else "diagnostic"
        value = str(self.journal.get_setting("scanner.control_mode", configured) or configured).strip().lower()
        return value if value in {"auto_submit", "diagnostic", "paused"} else configured

    def _scanner_exposure_snapshot(self) -> dict:
        max_positions = int(self.risk_config.get("max_open_positions") or 0)
        control_mode = self._scanner_control_mode()
        if not self.broker.is_configured() or control_mode != "auto_submit":
            pending = self.journal.pending_orders()
            return {
                "active_exposure": 0,
                "max_open_positions": max_positions,
                "positions": 0,
                "open_orders": 0,
                "pending_approvals": len(pending),
                "source": "diagnostic",
                "items": {
                    "positions": [],
                    "open_orders": [],
                    "pending_approvals": [self.journal._public_pending(item) for item in pending],
                },
            }
        try:
            raw_positions = self.broker.get_positions_raw()
            raw_orders = self.broker.get_orders_raw(status="open", limit=100, direction="desc", nested=True)
            pending = self.journal.pending_orders()
        except Exception as exc:
            return {
                "active_exposure": 0,
                "max_open_positions": max_positions,
                "positions": 0,
                "open_orders": 0,
                "pending_approvals": 0,
                "source": "error",
                "error": str(exc)[:240],
                "items": {"positions": [], "open_orders": [], "pending_approvals": []},
            }
        position_symbols = {str(item.get("symbol") or "").upper().strip() for item in raw_positions if item.get("symbol")}
        order_symbols = {str(item.get("symbol") or "").upper().strip() for item in raw_orders if item.get("symbol")}
        pending_symbols = {str(item.get("symbol") or "").upper().strip() for item in pending if item.get("symbol")}
        return {
            "active_exposure": self._active_exposure_count(raw_positions, raw_orders),
            "max_open_positions": max_positions,
            "positions": len(raw_positions),
            "open_orders": len(raw_orders),
            "pending_approvals": len(pending),
            "source": "broker",
            "items": {
                "positions": [
                    {
                        "symbol": str(item.get("symbol") or "").upper().strip(),
                        "qty": item.get("qty"),
                        "side": item.get("side"),
                    }
                    for item in raw_positions[:20]
                ],
                "open_orders": [
                    {
                        "id": item.get("id"),
                        "symbol": str(item.get("symbol") or "").upper().strip(),
                        "side": item.get("side"),
                        "type": item.get("type"),
                        "qty": item.get("qty"),
                        "status": item.get("status"),
                        "counts_exposure": str(item.get("symbol") or "").upper().strip() not in position_symbols,
                    }
                    for item in raw_orders[:30]
                ],
                "pending_approvals": [self.journal._public_pending(item) for item in pending[:20]],
                "symbols": sorted(position_symbols | order_symbols | pending_symbols),
            },
        }

    def _scanner_should_pause_for_exposure(self, exposure: dict) -> bool:
        max_positions = int(exposure.get("max_open_positions") or 0)
        if max_positions <= 0:
            return False
        if not bool(self.scanner_config.get("pause_when_exposure_full", True)):
            return False
        return int(exposure.get("active_exposure") or 0) >= max_positions

    def _scanner_lifecycle_pause(self) -> dict:
        if self._scanner_control_mode() != "auto_submit":
            return {"paused": False, "reason": None}
        enabled = os.getenv("VELEZ_SCANNER_PAUSE_ON_LIFECYCLE_CRITICAL", "true").strip().lower() in {"1", "true", "yes", "on"}
        if not enabled or not self.broker.is_configured():
            return {"paused": False, "reason": None}
        try:
            lifecycle = self.lifecycle_payload(light=True, refresh=True)
        except Exception as exc:
            return {
                "paused": True,
                "reason": "lifecycle_check_failed",
                "detail": f"Lifecycle integrity check failed before scanner reopen: {exc}",
            }
        needs = lifecycle.get("summary", {}).get("needs_action", {}) or {}
        critical = [item for item in needs.get("items", []) if item.get("severity") == "critical"]
        if not critical:
            return {"paused": False, "reason": None}
        return {
            "paused": True,
            "reason": "lifecycle_critical",
            "detail": "; ".join(f"{item.get('symbol')}: {item.get('action')}" for item in critical[:4]),
            "critical_count": len(critical),
        }

    def _notify_exposure_reduction_prompt(self, exposure: dict) -> None:
        if not self.broker.is_configured():
            return
        lifecycle = self.lifecycle_payload(light=True, refresh=True)
        needs = lifecycle.get("summary", {}).get("needs_action", {}) or {}
        if any(item.get("severity") == "critical" for item in needs.get("items", [])):
            return
        plan = self._exposure_reduction_plan(lifecycle)
        suggestions = plan.get("suggestions", [])
        if not suggestions:
            return
        key = "exposure-reduction-prompt:" + datetime.now(timezone.utc).date().isoformat() + ":" + "|".join(item.get("symbol", "") for item in suggestions[:3])
        detail = "; ".join(
            f"{item.get('symbol')} {item.get('recommendation')} qty {item.get('options', [{}])[0].get('qty', 'n/a')}"
            for item in suggestions[:3]
        )
        self._notify_event(
            key=key,
            title="Trading Bull exposure is full",
            detail=f"Scanner is paused at {exposure.get('active_exposure')}/{exposure.get('max_open_positions')}. Reduction ideas: {detail}. Use Position Doctor approval controls to execute.",
            severity="info",
            payload={"kind": "exposure_reduction_prompt", "timestamp": datetime.now(timezone.utc).isoformat(), "exposure": exposure, "suggestions": suggestions[:3]},
        )

    def _scanner_symbol_cooldown_seconds(self) -> int:
        return self._int_env(
            "VELEZ_SCANNER_SYMBOL_COOLDOWN_SECONDS",
            int(self.scanner_config.get("symbol_cooldown_seconds", 900) or 900),
            minimum=0,
            maximum=86400,
        )

    def _scanner_symbol_cooldown(self, symbol: str, now: datetime) -> Optional[dict]:
        cooldown_seconds = self._scanner_symbol_cooldown_seconds()
        if cooldown_seconds <= 0:
            return None
        key = str(symbol or "").upper().strip()
        until = self.scanner_symbol_cooldowns.get(key)
        if not until or now >= until:
            self.scanner_symbol_cooldowns.pop(key, None)
            return None
        return {
            "symbol": key,
            "until": until.isoformat(),
            "seconds_remaining": int((until - now).total_seconds()),
            "reason": "symbol_cooldown",
        }

    def _record_scanner_symbol_cooldown(self, symbol: str, decision: WebhookDecision, now: datetime) -> None:
        if decision.status not in {"rejected", "ignored", "error"}:
            return
        cooldown_seconds = self._scanner_symbol_cooldown_seconds()
        if cooldown_seconds <= 0:
            return
        key = str(symbol or decision.symbol or "").upper().strip()
        if key:
            self.scanner_symbol_cooldowns[key] = now + timedelta(seconds=cooldown_seconds)

    def _scanner_today_summary(self) -> dict:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end = now.isoformat()
        try:
            entries = self.journal.decisions_between(start, end, limit=2000)
        except Exception:
            entries = list(self.recent_decisions)
        scanner_entries = [
            item for item in entries
            if ((item.get("chart_context") or {}).get("source") == "vps_scanner")
            or (((item.get("metadata") or {}).get("source_metadata") or {}).get("source") == "vps_scanner")
        ]
        counts = {"total": 0, "submitted": 0, "proposed": 0, "diagnostic": 0, "rejected": 0, "ignored": 0, "error": 0}
        rejected_reasons: Dict[str, int] = {}
        symbols: Dict[str, int] = {}
        for item in scanner_entries:
            status = str(item.get("status") or "unknown").lower()
            counts["total"] += 1
            if status in counts:
                counts[status] += 1
            reason = str(item.get("reason") or "")
            if status == "rejected" and reason:
                rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
            symbol = str(item.get("symbol") or "").upper().strip()
            if symbol:
                symbols[symbol] = symbols.get(symbol, 0) + 1
        return {
            "date": now.date().isoformat(),
            "counts": counts,
            "rejected_reasons": dict(sorted(rejected_reasons.items(), key=lambda item: item[1], reverse=True)[:6]),
            "top_symbols": dict(sorted(symbols.items(), key=lambda item: item[1], reverse=True)[:6]),
        }

    def _scanner_quality_entries(self, limit: int = 80) -> List[dict]:
        entries = self.journal.decision_entries(limit=max(50, min(int(limit) * 3, 500)))
        scanner_entries = [
            item for item in entries
            if ((item.get("chart_context") or {}).get("source") == "vps_scanner")
            or (((item.get("metadata") or {}).get("source_metadata") or {}).get("source") == "vps_scanner")
            or ((item.get("metadata") or {}).get("scanner_quality_event") is True)
        ]
        return scanner_entries[: max(1, min(int(limit), 200))]

    def _scanner_quality_entry(self, item: dict) -> dict:
        metadata = item.get("metadata") or {}
        source = metadata.get("source_metadata") or {}
        entry_price = self._float(item.get("entry_price") or source.get("entry_price") or source.get("close"))
        stop_price = self._float(item.get("stop_price") or source.get("stop_price"))
        status = str(item.get("status") or "unknown").lower()
        forward = self._scanner_forward_outcome(item, entry_price=entry_price, stop_price=stop_price)
        grade = self._scanner_decision_grade(status=status, forward=forward, entry_price=entry_price, stop_price=stop_price)
        return {
            "timestamp": item.get("timestamp"),
            "alert_ref": item.get("alert_ref"),
            "symbol": str(item.get("symbol") or "").upper().strip(),
            "status": status,
            "reason": item.get("reason"),
            "side": item.get("side"),
            "play": item.get("play"),
            "qty": item.get("qty"),
            "entry_price": self._round_or_none(entry_price),
            "stop_price": self._round_or_none(stop_price),
            "timeframe": item.get("timeframe") or source.get("timeframe"),
            "session_bucket": self._scanner_session_bucket(item.get("timestamp")),
            "forward_outcome": forward,
            "grade": grade,
            "lesson": self._scanner_decision_lesson(status, forward),
        }

    def _scanner_forward_outcome(self, item: dict, *, entry_price: Optional[float], stop_price: Optional[float]) -> dict:
        symbol = str(item.get("symbol") or "").upper().strip()
        side = str(item.get("side") or "").lower()
        if not symbol or entry_price is None or stop_price is None:
            return {"outcome": "unavailable", "reason": "missing_entry_or_stop"}
        risk = abs(entry_price - stop_price)
        if risk <= 0:
            return {"outcome": "unavailable", "reason": "invalid_risk"}
        try:
            cfg = self.symbol_config.get(symbol, {}) or self.journal.get_watchlist_symbol(symbol) or {}
            bars = self._fetch_scanner_bars(symbol=symbol, asset_type=str(cfg.get("type") or cfg.get("asset_type") or "equity").lower())
        except Exception as exc:
            return {"outcome": "unavailable", "reason": str(exc)[:160]}
        after = self._bars_after_timestamp(bars, item.get("timestamp"))
        if not after:
            return {"outcome": "pending", "reason": "no_forward_bars"}
        direction = 1 if side == "buy" else -1
        best_r = 0.0
        horizon = max(1, min(int(self.scanner_config.get("quality_forward_bars", 60) or 60), 390))
        for index, bar in enumerate(after[:horizon], start=1):
            favorable = (bar.high - entry_price) * direction if direction == 1 else (entry_price - bar.low)
            adverse = (entry_price - bar.low) if direction == 1 else (bar.high - entry_price)
            best_r = max(best_r, favorable / risk)
            if adverse >= risk:
                return {"outcome": "stopped", "bars": index, "best_r": round(best_r, 2)}
            if favorable >= 2 * risk:
                return {"outcome": "hit_2r", "bars": index, "best_r": round(max(best_r, 2.0), 2)}
            if favorable >= risk:
                return {"outcome": "hit_1r", "bars": index, "best_r": round(max(best_r, 1.0), 2)}
        return {"outcome": "open", "bars": min(len(after), horizon), "best_r": round(best_r, 2)}

    def _bars_after_timestamp(self, bars: List[Bar], timestamp: Any) -> List[Bar]:
        parsed = self._parse_datetime(timestamp)
        if not parsed:
            return bars[-min(len(bars), 60):]
        return [bar for bar in bars if bar.timestamp > parsed]

    def _scanner_decision_grade(self, *, status: str, forward: dict, entry_price: Optional[float], stop_price: Optional[float]) -> str:
        outcome = forward.get("outcome")
        if status == "skipped":
            return "SKIP"
        if entry_price is None or stop_price is None:
            return "INCOMPLETE"
        if outcome == "hit_2r":
            return "A"
        if outcome == "hit_1r":
            return "B"
        if outcome == "open":
            return "C"
        if outcome == "stopped":
            return "D"
        return "PENDING"

    def _scanner_decision_lesson(self, status: str, forward: dict) -> str:
        if status == "skipped":
            return "Skipped by scanner filter; keep it out unless later stats prove this window is productive."
        outcome = forward.get("outcome")
        if outcome in {"hit_2r", "hit_1r"}:
            return "Forward replay says the setup had clean follow-through."
        if outcome == "stopped":
            return "Forward replay hit the stop first; review setup quality and session bucket."
        if outcome == "open":
            return "Forward replay did not resolve inside the configured horizon."
        return "Waiting for enough forward bars or complete entry/stop data."

    def _scanner_symbol_stats(self, entries: List[dict]) -> List[dict]:
        grouped: Dict[str, List[dict]] = {}
        for item in entries:
            symbol = item.get("symbol") or "UNKNOWN"
            grouped.setdefault(symbol, []).append(item)
        stats = []
        for symbol, items in grouped.items():
            outcomes = Counter((item.get("forward_outcome") or {}).get("outcome") for item in items)
            accepted = [item for item in items if item.get("status") in {"submitted", "proposed", "diagnostic"}]
            stats.append({
                "symbol": symbol,
                "total": len(items),
                "accepted": len(accepted),
                "rejected": sum(1 for item in items if item.get("status") == "rejected"),
                "skipped": sum(1 for item in items if item.get("status") == "skipped"),
                "would_win": outcomes.get("hit_1r", 0) + outcomes.get("hit_2r", 0),
                "would_stop": outcomes.get("stopped", 0),
                "score": (outcomes.get("hit_1r", 0) + 2 * outcomes.get("hit_2r", 0)) - outcomes.get("stopped", 0),
            })
        return sorted(stats, key=lambda item: (item["score"], item["accepted"]), reverse=True)[:20]

    def _scanner_session_stats(self, entries: List[dict]) -> List[dict]:
        grouped: Dict[str, List[dict]] = {}
        for item in entries:
            grouped.setdefault(item.get("session_bucket") or "unknown", []).append(item)
        return [
            {
                "bucket": bucket,
                "total": len(items),
                "would_win": sum(1 for item in items if (item.get("forward_outcome") or {}).get("outcome") in {"hit_1r", "hit_2r"}),
                "would_stop": sum(1 for item in items if (item.get("forward_outcome") or {}).get("outcome") == "stopped"),
            }
            for bucket, items in sorted(grouped.items())
        ]

    def _scanner_quality_readback(self, entries: List[dict], symbol_stats: List[dict]) -> str:
        if not entries:
            return "No scanner quality events are recorded yet."
        best = symbol_stats[0]["symbol"] if symbol_stats else "none"
        return f"{len(entries)} scanner event(s) reviewed. Best current symbol lane: {best}."

    def _watchlist_quality_recommendations(self, *, symbol_stats: List[dict], entries: List[dict]) -> List[dict]:
        stats_by_symbol = {item.get("symbol"): item for item in symbol_stats}
        recommendations = []
        for row in self.watchlist_symbols(include_disabled=True):
            symbol = row.get("symbol")
            stats = stats_by_symbol.get(symbol, {})
            total = int(stats.get("total") or 0)
            accepted = int(stats.get("accepted") or 0)
            skipped = int(stats.get("skipped") or 0)
            rejected = int(stats.get("rejected") or 0)
            would_win = int(stats.get("would_win") or 0)
            would_stop = int(stats.get("would_stop") or 0)
            score = int(stats.get("score") or 0)
            if total < 3:
                state = "keep_watching"
                reason = "Needs at least 3 scanner quality events before lane tuning."
            elif accepted >= 2 and score >= 2 and would_win > would_stop:
                state = "promote"
                reason = "Forward replay favors this symbol; prioritize review."
            elif would_stop >= 2 and would_stop >= would_win:
                state = "disable_candidate"
                reason = "Repeated forward replay stops; consider disabling from scanner rotation."
            elif rejected + skipped >= max(3, accepted + would_win):
                state = "cool_down"
                reason = "Lane is producing mostly rejects/skips; reduce attention until behavior improves."
            else:
                state = "keep_watching"
                reason = "Mixed or incomplete evidence; keep collecting scanner quality samples."
            recommendations.append({
                "symbol": symbol,
                "state": state,
                "reason": reason,
                "enabled": row.get("enabled", True),
                "stats": {
                    "total": total,
                    "accepted": accepted,
                    "rejected": rejected,
                    "skipped": skipped,
                    "would_win": would_win,
                    "would_stop": would_stop,
                    "score": score,
                },
            })
        order = {"promote": 0, "disable_candidate": 1, "cool_down": 2, "keep_watching": 3}
        return sorted(recommendations, key=lambda item: (order.get(item["state"], 9), item["symbol"]))

    def _record_scanner_skip(self, symbol: str, reason: str, detail: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        snapshot = {
            "timestamp": now,
            "alert_ref": f"scanner-skip-{symbol.lower()}-{hashlib.sha1((reason + now).encode()).hexdigest()[:10]}",
            "status": "skipped",
            "reason": reason,
            "symbol": symbol,
            "side": "",
            "play": "scanner_filter",
            "qty": 0,
            "metadata": {"scanner_quality_event": True, "source_metadata": {"source": "vps_scanner"}, "detail": detail},
        }
        try:
            self.journal.record_decision(snapshot)
        except Exception as exc:
            log_event(self.logger, "scanner_skip_record_failed", {"symbol": symbol, "reason": reason, "error": str(exc)})

    def _scanner_session_filter_config(self) -> dict:
        return {
            "enabled": _bool_env("VELEZ_SCANNER_SESSION_FILTER_ENABLED", bool(self.scanner_config.get("session_filter_enabled", True))),
            "rth_start": str(self.scanner_config.get("rth_start", os.getenv("VELEZ_SCANNER_RTH_START", "09:35"))),
            "rth_end": str(self.scanner_config.get("rth_end", os.getenv("VELEZ_SCANNER_RTH_END", "15:45"))),
            "avoid_lunch": _bool_env("VELEZ_SCANNER_AVOID_LUNCH", bool(self.scanner_config.get("avoid_lunch", True))),
            "lunch_start": str(self.scanner_config.get("lunch_start", os.getenv("VELEZ_SCANNER_LUNCH_START", "11:45"))),
            "lunch_end": str(self.scanner_config.get("lunch_end", os.getenv("VELEZ_SCANNER_LUNCH_END", "13:30"))),
        }

    def _scanner_session_block(self, *, symbol: str, asset_type: str, now: datetime) -> Optional[dict]:
        cfg = self._scanner_session_filter_config()
        if not cfg["enabled"] or asset_type in {"crypto", "future", "futures"}:
            return None
        minutes = self._et_minutes(now)
        start = self._minutes_from_clock(cfg["rth_start"])
        end = self._minutes_from_clock(cfg["rth_end"])
        if minutes < start:
            return {"symbol": symbol, "reason": "premarket", "clock": self._clock_from_minutes(minutes), "allowed": f"{cfg['rth_start']}-{cfg['rth_end']} ET"}
        if minutes > end:
            return {"symbol": symbol, "reason": "late_session", "clock": self._clock_from_minutes(minutes), "allowed": f"{cfg['rth_start']}-{cfg['rth_end']} ET"}
        if cfg["avoid_lunch"]:
            lunch_start = self._minutes_from_clock(cfg["lunch_start"])
            lunch_end = self._minutes_from_clock(cfg["lunch_end"])
            if lunch_start <= minutes <= lunch_end:
                return {"symbol": symbol, "reason": "lunch_chop", "clock": self._clock_from_minutes(minutes), "allowed": f"outside {cfg['lunch_start']}-{cfg['lunch_end']} ET"}
        return None

    def _scanner_session_bucket(self, timestamp: Any) -> str:
        parsed = self._parse_datetime(timestamp) or datetime.now(timezone.utc)
        minutes = self._et_minutes(parsed)
        if minutes < self._minutes_from_clock("09:30"):
            return "premarket"
        if minutes < self._minutes_from_clock("11:45"):
            return "morning"
        if minutes <= self._minutes_from_clock("13:30"):
            return "lunch"
        if minutes <= self._minutes_from_clock("15:45"):
            return "afternoon"
        return "final_hour"

    def _et_minutes(self, value: datetime) -> int:
        local = value.astimezone(ZoneInfo("America/New_York"))
        return local.hour * 60 + local.minute

    def _minutes_from_clock(self, value: str) -> int:
        hour, _, minute = str(value or "00:00").partition(":")
        return int(hour or 0) * 60 + int(minute or 0)

    def _clock_from_minutes(self, minutes: int) -> str:
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def _notify_scanner_exposure_transition(self, paused: bool, exposure: dict) -> None:
        state = "paused" if paused else "active"
        previous = self.journal.get_setting("scanner.exposure_pause_state", None)
        if previous == state:
            return
        self.journal.set_setting("scanner.exposure_pause_state", state)
        if previous is None and not paused:
            return
        title = "Trading Bull scanner paused" if paused else "Trading Bull scanner resumed"
        detail = (
            f"Scanner paused at {exposure.get('active_exposure', 0)}/{exposure.get('max_open_positions', 0)} active exposure."
            if paused
            else f"Scanner resumed with {exposure.get('active_exposure', 0)}/{exposure.get('max_open_positions', 0)} active exposure."
        )
        self._notify_event(
            key=f"scanner-exposure-{state}:{datetime.now(timezone.utc).date().isoformat()}",
            title=title,
            detail=detail,
            severity="info",
            payload={
                "kind": "scanner_exposure_state",
                "state": state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "exposure": exposure,
            },
            ignore_cooldown=True,
        )

    def cancel_stale_scanner_orders(self, approval_token: str) -> dict:
        auth = self._authorize_approval_token(approval_token)
        if not auth.get("ok"):
            return auth
        if not self.broker.is_configured():
            return {"ok": False, "reason": "broker_not_configured"}
        if self.webhook_config.get("paper_only", True) and "paper-api.alpaca.markets" not in self.broker.config.base_url:
            return {"ok": False, "reason": "non_paper_alpaca_endpoint_blocked"}
        try:
            raw_positions = self.broker.get_positions_raw()
            raw_orders = self.broker.get_orders_raw(status="open", limit=100, direction="desc", nested=True)
        except Exception as exc:
            return {"ok": False, "reason": f"broker_snapshot_failed:{exc}"}
        position_symbols = {str(item.get("symbol") or "").upper().strip() for item in raw_positions if item.get("symbol")}
        stale = [order for order in raw_orders if self._stale_scanner_order(order, position_symbols)]
        canceled = []
        errors = []
        for order in stale:
            order_id = str(order.get("id") or "")
            if not order_id:
                continue
            try:
                if hasattr(self.broker, "cancel_order"):
                    response = self.broker.cancel_order(order_id)
                else:
                    response = self.broker._request("DELETE", f"/v2/orders/{order_id}")
                canceled.append({**self._order_snapshot(order), "cancel_response": response})
            except Exception as exc:
                errors.append({"id": order_id, "symbol": order.get("symbol"), "reason": str(exc)})
        return {
            "ok": not errors,
            "canceled": canceled,
            "errors": errors,
            "canceled_count": len(canceled),
            "stale_count": len(stale),
            "message": f"Canceled {len(canceled)} stale scanner order(s).",
            "scanner": self.scanner_public_status(),
        }

    def _stale_scanner_order(self, order: dict, position_symbols: set[str]) -> bool:
        symbol = str(order.get("symbol") or "").upper().strip()
        if not symbol or symbol in position_symbols:
            return False
        order_type = str(order.get("type") or order.get("order_type") or "").lower()
        if order_type in {"stop", "trailing_stop"}:
            return False
        client_order_id = str(order.get("client_order_id") or "")
        if client_order_id and not client_order_id.startswith("velez-"):
            return False
        status = str(order.get("status") or "").lower()
        return status in {"new", "accepted", "pending_new", "partially_filled"}

    def _fetch_scanner_bars(self, *, symbol: str, asset_type: str) -> List[Bar]:
        if asset_type == "crypto":
            return self._fetch_crypto_bars(symbol)
        if asset_type in {"future", "futures"}:
            return self._fetch_polygon_futures_bars(symbol)
        return self._fetch_stock_bars(symbol)

    def _fetch_stock_bars(self, symbol: str) -> List[Bar]:
        timeframe = str(self.scanner_config.get("timeframe", "1Min"))
        limit = max(50, min(int(self.scanner_config.get("history_bars", 260) or 260), 1000))
        params = {
            "symbols": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "feed": str(self.scanner_config.get("stock_feed", "iex")),
            "adjustment": str(self.scanner_config.get("adjustment", "raw")),
            "sort": "asc",
        }
        data = self._alpaca_data_request("/v2/stocks/bars", params=params)
        rows = (data.get("bars") or {}).get(symbol) or []
        return [self._bar_from_alpaca(item) for item in rows]

    def _fetch_crypto_bars(self, symbol: str) -> List[Bar]:
        timeframe = str(self.scanner_config.get("timeframe", "1Min"))
        limit = max(50, min(int(self.scanner_config.get("history_bars", 260) or 260), 1000))
        alpaca_symbol = self._alpaca_crypto_symbol(symbol)
        params = {
            "symbols": alpaca_symbol,
            "timeframe": timeframe,
            "limit": limit,
            "sort": "asc",
        }
        data = self._alpaca_data_request("/v1beta3/crypto/us/bars", params=params)
        rows = (data.get("bars") or {}).get(alpaca_symbol) or []
        return [self._bar_from_alpaca(item) for item in rows]

    def _fetch_polygon_futures_bars(self, symbol: str) -> List[Bar]:
        ticker = self._polygon_futures_ticker(symbol)
        resolution = self._polygon_resolution(str(self.scanner_config.get("futures_resolution") or self.scanner_config.get("timeframe", "1Min")))
        limit = max(50, min(int(self.scanner_config.get("history_bars", 260) or 260), 50000))
        data = self._polygon_request(f"/futures/vX/aggs/{ticker}", params={"resolution": resolution, "limit": limit})
        rows = data.get("results") or []
        return [self._bar_from_polygon_futures(item) for item in rows]

    def _alpaca_data_request(self, path: str, *, params: dict) -> dict:
        if not self.broker.is_configured():
            raise RuntimeError("missing_alpaca_credentials")
        url = f"{self.broker.config.data_url.rstrip('/')}{path}"
        response = requests.get(url, headers=self.broker._headers(), params=params, timeout=int(self.scanner_config.get("timeout_seconds", 20) or 20))
        if response.status_code >= 300:
            raise RuntimeError(f"alpaca_data_{response.status_code}:{response.text[:160]}")
        return response.json() if response.text else {}

    def _polygon_request(self, path: str, *, params: dict) -> dict:
        api_key = self._polygon_api_key()
        if not api_key:
            raise RuntimeError("missing_polygon_api_key")
        base_url = str(self.scanner_config.get("polygon_base_url") or os.getenv("POLYGON_BASE_URL", "https://api.polygon.io")).rstrip("/")
        request_params = dict(params)
        request_params["apiKey"] = api_key
        response = requests.get(
            f"{base_url}{path}",
            params=request_params,
            timeout=int(self.scanner_config.get("timeout_seconds", 20) or 20),
        )
        if response.status_code >= 300:
            sanitized = response.text.replace(api_key, "[REDACTED]")
            raise RuntimeError(f"polygon_data_{response.status_code}:{sanitized[:180]}")
        return response.json() if response.text else {}

    def _bar_from_alpaca(self, item: dict) -> Bar:
        return Bar(
            timestamp=self._timestamp(item.get("t")),
            open=float(item.get("o")),
            high=float(item.get("h")),
            low=float(item.get("l")),
            close=float(item.get("c")),
            volume=float(item.get("v") or 0),
        )

    def _bar_from_polygon_futures(self, item: dict) -> Bar:
        return Bar(
            timestamp=self._polygon_timestamp(item.get("window_start")),
            open=float(item.get("open")),
            high=float(item.get("high")),
            low=float(item.get("low")),
            close=float(item.get("close")),
            volume=float(item.get("volume") or 0),
        )

    def _polygon_api_key(self) -> str:
        return str(os.getenv("POLYGON_API_KEY") or os.getenv("MASSIVE_API_KEY") or self.scanner_config.get("polygon_api_key") or "").strip()

    def _polygon_futures_ticker(self, symbol: str) -> str:
        symbol = str(symbol or "").upper().strip()
        contracts = {str(key).upper(): str(value).upper() for key, value in (self.scanner_config.get("futures_contracts") or {}).items()}
        if symbol in contracts:
            return contracts[symbol]
        default_contracts = {"ES": "ESM6", "NQ": "NQM6", "MES": "MESM6", "MNQ": "MNQM6"}
        return default_contracts.get(symbol, symbol)

    def _polygon_resolution(self, timeframe: str) -> str:
        match = re.match(r"^(\d+)(Min|T|Hour|H|Day|D)$", str(timeframe or "1Min"), re.IGNORECASE)
        if not match:
            return "1min"
        count = int(match.group(1))
        unit = match.group(2).lower()
        if unit in {"hour", "h"}:
            return f"{count}hr"
        if unit in {"day", "d"}:
            return f"{count}day"
        return f"{count}min"

    def _polygon_timestamp(self, value: Any) -> datetime:
        numeric = self._float(value)
        if numeric is None:
            return datetime.now(timezone.utc)
        if numeric > 1_000_000_000_000_000_000:
            return datetime.fromtimestamp(numeric / 1_000_000_000, tz=timezone.utc)
        if numeric > 10_000_000_000:
            return datetime.fromtimestamp(numeric / 1000, tz=timezone.utc)
        return datetime.fromtimestamp(numeric, tz=timezone.utc)

    def _scanner_bar_is_closed(self, bar: Bar, now: datetime) -> bool:
        timeframe_seconds = self._timeframe_seconds(str(self.scanner_config.get("timeframe", "1Min")))
        delay = max(0, int(self.scanner_config.get("closed_bar_delay_seconds", 15) or 15))
        timestamp = bar.timestamp if bar.timestamp.tzinfo else bar.timestamp.replace(tzinfo=timezone.utc)
        return timestamp <= now - timedelta(seconds=timeframe_seconds + delay)

    def _timeframe_seconds(self, timeframe: str) -> int:
        match = re.match(r"^(\d+)(Min|T|Hour|H|Day|D)$", str(timeframe or "1Min"), re.IGNORECASE)
        if not match:
            return 60
        count = int(match.group(1))
        unit = match.group(2).lower()
        if unit in {"hour", "h"}:
            return count * 3600
        if unit in {"day", "d"}:
            return count * 86400
        return count * 60

    def _alpaca_crypto_symbol(self, symbol: str) -> str:
        cleaned = str(symbol or "").upper().replace("-", "/")
        if "/" in cleaned:
            return cleaned
        if cleaned.endswith("USD"):
            return f"{cleaned[:-3]}/USD"
        return f"{cleaned}/USD"

    def _scanner_alert_id(self, signal: Signal, bar: Bar) -> str:
        raw = "|".join(
            [
                "scanner",
                signal.symbol,
                signal.side.value,
                str(signal.metadata.get("play") or signal.reason),
                bar.timestamp.isoformat(),
                str(signal.metadata.get("entry_price")),
                str(signal.metadata.get("stop_price")),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _update_scanner_status(self, **updates) -> None:
        with self.scanner_lock:
            self.scanner_status.update(updates)

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

    def alert_coverage_payload(self, *, light: bool = False) -> dict:
        now = datetime.now(timezone.utc)
        symbols = self.watchlist_symbols()
        recent = self.journal.latest_decisions(limit=500)
        latest_by_symbol: Dict[str, dict] = {}
        for item in recent:
            symbol = str(item.get("symbol") or "").upper().strip()
            if symbol and symbol not in latest_by_symbol:
                latest_by_symbol[symbol] = item

        stale_minutes = self._int_env("VELEZ_ALERT_STALE_MINUTES", 240, minimum=5, maximum=1440)
        stale_seconds = stale_minutes * 60
        rows = []
        counts = Counter()
        payload_current = 0
        for item in symbols:
            symbol = str(item.get("symbol") or "").upper().strip()
            latest = latest_by_symbol.get(symbol)
            age_seconds = self._seconds_since(latest.get("timestamp")) if latest else None
            if latest is None:
                status = "never"
                detail = "No TradingView alert from this symbol has reached the journal yet."
            elif age_seconds is not None and age_seconds <= stale_seconds:
                status = "healthy"
                detail = f"Last alert received {self._age_label(latest.get('timestamp'))}."
            else:
                status = "stale"
                detail = f"Last alert is older than {stale_minutes} minutes."
            counts[status] += 1
            row = {
                "symbol": symbol,
                "type": item.get("type", "equity"),
                "enabled": item.get("enabled", True),
                "status": status,
                "detail": detail,
                "age_seconds": age_seconds,
                "last_alert": latest,
            }
            checklist = self._alert_coverage_checklist(item, latest, age_seconds, stale_seconds)
            row["checklist"] = checklist
            row["coverage_score"] = sum(1 for check in checklist if check.get("ok"))
            if latest and checklist[-1].get("ok"):
                payload_current += 1
            if light:
                row["last_alert"] = {
                    key: latest.get(key)
                    for key in ("timestamp", "status", "reason", "symbol", "side", "play", "timeframe", "alert_ref", "payload_version")
                } if latest else None
            rows.append(row)

        healthy = counts.get("healthy", 0)
        coverage_score = round((healthy / len(rows)) * 100) if rows else 0
        return {
            "ok": True,
            "timestamp": now.isoformat(),
            "stale_minutes": stale_minutes,
            "symbols_csv": ",".join(item.get("symbol", "") for item in symbols if item.get("symbol")),
            "summary": {
                "symbols": len(rows),
                "healthy": healthy,
                "stale": counts.get("stale", 0),
                "never": counts.get("never", 0),
                "coverage_score": coverage_score,
                "payload_current": payload_current,
                "needs_setup": counts.get("stale", 0) + counts.get("never", 0),
            },
            "rows": rows,
            "note": "TradingView Watchlist Alerts are configured inside TradingView. This panel confirms what the bot has actually received.",
        }

    def lifecycle_payload(self, light: bool = False, refresh: bool = True) -> dict:
        cached = self.journal.latest_lifecycle_snapshot()
        if not refresh:
            if cached:
                return self._light_lifecycle_payload(cached) if light else cached
            return self._empty_lifecycle_payload("No broker reconciliation snapshot has run yet.")

        now = datetime.now(timezone.utc)
        raw_positions, positions_error = self._raw_positions_for_lifecycle()
        raw_orders, orders_error = self._raw_orders_for_lifecycle()
        raw_fills, fills_error = self._raw_fills_for_lifecycle()
        decisions = self.journal.decision_entries(limit=1000)
        pending = self.journal.pending_orders()

        open_orders = [self._order_snapshot(item) for item in raw_orders]
        recent_fills = [self._fill_snapshot(item) for item in raw_fills]
        positions = [
            self._position_lifecycle(item, decisions=decisions, orders=open_orders, fills=recent_fills)
            for item in raw_positions
        ]
        guardrails = self._lifecycle_guardrails(
            positions=positions,
            open_orders=open_orders,
            pending=pending,
            decisions=decisions,
            errors={
                "positions": positions_error,
                "orders": orders_error,
                "fills": fills_error,
            },
        )
        # P1+V1+V2+P4: Auto-execute lifecycle actions
        auto_results = self._auto_lifecycle_actions(
            positions=positions,
            open_orders=open_orders,
            guardrails=guardrails,
        )
        # Filter guardrails to remove issues that were auto-repaired
        repaired_symbols = {
            r.get("symbol") for r in auto_results
            if r.get("status") == "submitted" and r.get("symbol")
        }
        repaired_actions = {
            r.get("action") for r in auto_results
            if r.get("status") == "submitted"
        }
        if repaired_symbols or repaired_actions:
            guardrails = [
                g for g in guardrails
                if not (
                    (g.get("symbol") in repaired_symbols and g.get("name") in {"missing_stop", "orphan_position", "journal_stop_only"})
                    or (g.get("name") == "max_positions_exceeded" and ("force_close_max_positions" in repaired_actions or "pre_close_flatten" in repaired_actions))
                )
            ]
        management_actions = sum(len(item.get("management", [])) for item in positions)
        needs_action = self._lifecycle_needs_action_summary(positions, guardrails)
        unrealized_pl = sum(self._float(item.get("unrealized_pl")) or 0.0 for item in positions)
        open_risk = sum(self._float(item.get("initial_risk_dollars")) or 0.0 for item in positions)
        r_values = [self._float(item.get("current_r_multiple")) for item in positions]
        r_values = [value for value in r_values if value is not None]
        payload = {
            "ok": not positions_error,
            "timestamp": now.isoformat(),
            "summary": {
                "open_positions": len(positions),
                "open_orders": len(open_orders),
                "recent_fills": len(recent_fills),
                "guardrails": len(guardrails),
                "management_actions": management_actions,
                "unrealized_pl": round(unrealized_pl, 2),
                "open_risk": round(open_risk, 2),
                "average_r_multiple": round(sum(r_values) / len(r_values), 2) if r_values else None,
                "needs_action": needs_action,
            },
            "positions": positions,
            "open_orders": open_orders,
            "recent_fills": [] if light else recent_fills,
            "guardrails": guardrails,
            "errors": {
                "positions": positions_error,
                "orders": orders_error,
                "fills": fills_error,
            },
            "readback": self._lifecycle_readback(positions, guardrails),
            "note": "Lifecycle reconciliation reads Alpaca paper positions, orders, and fills. Auto-actions repair missing stops, move stops to breakeven at 1R, enforce time stops, and force-close on max-positions violations.",
        }
        previous_lifecycle = self.journal.latest_lifecycle_snapshot()
        try:
            self.journal.save_lifecycle_snapshot(payload)
            self._record_lifecycle_outcomes(payload)
        except Exception as exc:
            log_event(self.logger, "lifecycle_journal_failed", {"reason": str(exc)})
        self._notify_lifecycle_guardrails(payload)
        self._notify_lifecycle_changes(payload, previous_lifecycle)
        self._notify_lifecycle_thresholds(payload)
        payload["outcomes"] = self.journal.latest_trade_outcomes(limit=12)
        return self._light_lifecycle_payload(payload) if light else payload

    def lifecycle_partial_plan(self) -> dict:
        lifecycle = self.lifecycle_payload(light=False, refresh=True)
        positions = lifecycle.get("positions", [])
        return {
            "ok": lifecycle.get("ok", True),
            "timestamp": lifecycle.get("timestamp"),
            "plans": [self._partial_plan_for_position(position) for position in positions],
            "summary": lifecycle.get("summary", {}),
            "note": "Partial plans are advisory. This endpoint does not submit exit orders.",
        }

    def lifecycle_doctor_payload(self) -> dict:
        lifecycle = self.lifecycle_payload(light=False, refresh=True)
        return {
            "ok": lifecycle.get("ok", True),
            "timestamp": lifecycle.get("timestamp"),
            "summary": lifecycle.get("summary", {}),
            "readback": lifecycle.get("readback"),
            "positions": [self._position_doctor_card(position) for position in lifecycle.get("positions", [])],
            "reduction_plan": self._exposure_reduction_plan(lifecycle),
            "scanner_reopen": self.scanner_reopen_check(lifecycle=lifecycle),
            "guardrails": lifecycle.get("guardrails", []),
            "note": "Position Doctor is guarded. Repair actions require the approval token and paper broker endpoint.",
        }

    def exposure_reduction_plan(self) -> dict:
        lifecycle = self.lifecycle_payload(light=False, refresh=True)
        return {
            "ok": lifecycle.get("ok", True),
            "timestamp": lifecycle.get("timestamp"),
            "plan": self._exposure_reduction_plan(lifecycle),
            "scanner_reopen": self.scanner_reopen_check(lifecycle=lifecycle),
            "note": "Reduction plans are advisory until an approval-token action submits a paper exit order.",
        }

    def scanner_reopen_check(self, *, lifecycle: Optional[dict] = None) -> dict:
        lifecycle = lifecycle or self.lifecycle_payload(light=True, refresh=True)
        scanner = self.scanner_public_status()
        exposure = scanner.get("exposure") or {}
        needs = lifecycle.get("summary", {}).get("needs_action", {}) or {}
        critical = [item for item in needs.get("items", []) if item.get("severity") == "critical"]
        active = int(exposure.get("active_exposure") or 0)
        max_open = int(exposure.get("max_open_positions") or 0)
        blockers = []
        if critical:
            blockers.append("lifecycle_critical")
        if max_open > 0 and active >= max_open:
            blockers.append("max_exposure_reached")
        pause = scanner.get("pause") or {}
        if pause.get("reason") in {"operator_paused", "symbol_cooldown"}:
            blockers.append(str(pause.get("reason")))
        return {
            "ok": True,
            "can_reopen": not blockers,
            "blockers": blockers,
            "active_exposure": active,
            "max_open_positions": max_open,
            "control_mode": scanner.get("control_mode"),
            "mode": scanner.get("mode"),
            "readback": "Scanner can hunt again." if not blockers else f"Scanner stays paused: {', '.join(blockers)}.",
        }

    def auto_claim_lifecycle_positions(self, approval_token: str) -> dict:
        auth = self._authorize_approval_token(approval_token)
        if not auth.get("ok"):
            return auth
        lifecycle = self.lifecycle_payload(light=False, refresh=True)
        decisions = self.journal.decision_entries(limit=500)
        claimed = []
        skipped = []
        for position in lifecycle.get("positions", []):
            symbol = str(position.get("symbol") or "").upper().strip()
            if position.get("linked_alert_ref"):
                skipped.append({"symbol": symbol, "reason": "already_linked"})
                continue
            candidates = self._claim_candidates_for_symbol(symbol, decisions, side=str(position.get("side") or ""))
            if not candidates:
                skipped.append({"symbol": symbol, "reason": "no_claim_candidate"})
                continue
            selected = candidates[0]
            claim = self._set_lifecycle_claim(symbol, selected)
            claimed.append({"symbol": symbol, "alert_ref": claim.get("alert_ref"), "status": selected.get("status")})
        return {
            "ok": True,
            "claimed": claimed,
            "skipped": skipped,
            "claimed_count": len(claimed),
            "lifecycle": self.lifecycle_payload(light=True, refresh=True),
        }

    def claim_lifecycle_position(self, symbol: str, alert_ref: str, approval_token: str) -> dict:
        auth = self._authorize_approval_token(approval_token)
        if not auth.get("ok"):
            return auth
        cleaned_symbol = str(symbol or "").upper().strip()
        cleaned_ref = str(alert_ref or "").strip()
        if not cleaned_symbol or not cleaned_ref:
            return {"ok": False, "reason": "symbol_and_alert_ref_required"}
        decision = self.journal.decision_by_alert_ref(cleaned_ref)
        if not decision:
            return {"ok": False, "reason": "journal_decision_not_found"}
        if str(decision.get("symbol") or "").upper().strip() != cleaned_symbol:
            return {"ok": False, "reason": "journal_symbol_mismatch"}
        if str(decision.get("status") or "").lower() not in {"submitted", "proposed", "diagnostic"}:
            return {"ok": False, "reason": "journal_decision_not_actionable"}
        claim = self._set_lifecycle_claim(cleaned_symbol, decision)
        return {"ok": True, "claim": claim, "lifecycle": self.lifecycle_payload(light=True, refresh=True)}

    def repair_lifecycle_stop(self, symbol: str, approval_token: str) -> dict:
        auth = self._authorize_approval_token(approval_token)
        if not auth.get("ok"):
            return auth
        if not self.broker.is_configured():
            return {"ok": False, "reason": "broker_not_configured"}
        if self.webhook_config.get("paper_only", True) and "paper-api.alpaca.markets" not in self.broker.config.base_url:
            return {"ok": False, "reason": "non_paper_alpaca_endpoint_blocked"}
        cleaned_symbol = str(symbol or "").upper().strip()
        lifecycle = self.lifecycle_payload(light=False, refresh=True)
        position = next((item for item in lifecycle.get("positions", []) if item.get("symbol") == cleaned_symbol), None)
        if not position:
            return {"ok": False, "reason": "position_not_found"}
        if position.get("stop_source") == "broker_open_order":
            return {"ok": True, "status": "already_protected", "symbol": cleaned_symbol, "lifecycle": self.lifecycle_payload(light=True, refresh=True)}
        linked = position.get("linked_decision") or {}
        stop_price = self._float(position.get("stop_price")) or self._float(linked.get("stop_price"))
        if stop_price is None:
            return {"ok": False, "reason": "missing_journal_stop_price", "symbol": cleaned_symbol}
        qty = self._position_qty_string(position)
        if not qty:
            return {"ok": False, "reason": "missing_position_qty", "symbol": cleaned_symbol}
        payload = {
            "symbol": cleaned_symbol,
            "qty": qty,
            "side": "sell" if str(position.get("side")) == "long" else "buy",
            "type": "stop",
            "time_in_force": self.webhook_config.get("time_in_force", "day"),
            "stop_price": f"{stop_price:.2f}",
            "client_order_id": f"manual-repair-stop-{cleaned_symbol.lower()}-{secrets.token_hex(8)}",
        }
        try:
            response = self.broker.submit_order_payload(payload)
        except Exception as exc:
            return {"ok": False, "reason": f"broker_stop_repair_failed:{exc}", "symbol": cleaned_symbol}
        self._notify_event(
            key=f"repair-stop:{cleaned_symbol}:{datetime.now(timezone.utc).isoformat()}",
            title="Trading Bull protective stop repaired",
            detail=f"{cleaned_symbol} stop submitted at {payload['stop_price']}",
            severity="info",
            payload={"kind": "protective_stop_repair", "timestamp": datetime.now(timezone.utc).isoformat(), "symbol": cleaned_symbol, "order": response},
            ignore_cooldown=True,
        )
        return {"ok": True, "status": "submitted", "symbol": cleaned_symbol, "order": response, "lifecycle": self.lifecycle_payload(light=True, refresh=True)}

    def reduce_lifecycle_position(self, symbol: str, fraction: float, approval_token: str) -> dict:
        auth = self._authorize_approval_token(approval_token)
        if not auth.get("ok"):
            return auth
        if not self.broker.is_configured():
            return {"ok": False, "reason": "broker_not_configured"}
        if self.webhook_config.get("paper_only", True) and "paper-api.alpaca.markets" not in self.broker.config.base_url:
            return {"ok": False, "reason": "non_paper_alpaca_endpoint_blocked"}
        cleaned_symbol = str(symbol or "").upper().strip()
        try:
            cleaned_fraction = float(fraction)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "invalid_fraction"}
        allowed = {0.25, 0.5, 1.0}
        if not any(abs(cleaned_fraction - item) < 1e-9 for item in allowed):
            return {"ok": False, "reason": "fraction_not_allowed", "allowed": sorted(allowed)}
        lifecycle = self.lifecycle_payload(light=False, refresh=True)
        needs = lifecycle.get("summary", {}).get("needs_action", {}) or {}
        critical = [item for item in needs.get("items", []) if item.get("severity") == "critical"]
        if critical:
            return {"ok": False, "reason": "lifecycle_critical_blocks_reduction", "critical": critical[:6]}
        position = next((item for item in lifecycle.get("positions", []) if item.get("symbol") == cleaned_symbol), None)
        if not position:
            return {"ok": False, "reason": "position_not_found"}
        qty_value = self._position_qty_number(position)
        if not qty_value:
            return {"ok": False, "reason": "missing_position_qty"}
        exit_qty = qty_value if abs(cleaned_fraction - 1.0) < 1e-9 else qty_value * cleaned_fraction
        if qty_value >= 1:
            exit_qty = max(1, int(exit_qty))
        exit_qty = min(exit_qty, qty_value)
        qty = self._format_qty(exit_qty)
        if not qty:
            return {"ok": False, "reason": "exit_qty_zero"}
        canceled = self._cancel_symbol_stop_orders(position)
        payload = {
            "symbol": cleaned_symbol,
            "qty": qty,
            "side": "sell" if str(position.get("side")) == "long" else "buy",
            "type": "market",
            "time_in_force": self.webhook_config.get("time_in_force", "day"),
            "client_order_id": f"manual-reduce-{cleaned_symbol.lower()}-{int(cleaned_fraction * 100)}-{secrets.token_hex(8)}",
        }
        try:
            response = self.broker.submit_order_payload(payload)
        except Exception as exc:
            return {"ok": False, "reason": f"broker_reduce_failed:{exc}", "symbol": cleaned_symbol, "canceled": canceled}
        self._notify_event(
            key=f"reduce-position:{cleaned_symbol}:{datetime.now(timezone.utc).isoformat()}",
            title="Trading Bull exposure reduction submitted",
            detail=f"{cleaned_symbol} {int(cleaned_fraction * 100)}% reduction submitted for qty {qty}.",
            severity="info",
            payload={"kind": "exposure_reduction", "timestamp": datetime.now(timezone.utc).isoformat(), "symbol": cleaned_symbol, "fraction": cleaned_fraction, "qty": qty, "order": response, "canceled": canceled},
            ignore_cooldown=True,
        )
        verification = self.post_exit_verification()
        return {
            "ok": True,
            "status": "submitted",
            "symbol": cleaned_symbol,
            "fraction": cleaned_fraction,
            "qty": qty,
            "canceled": canceled,
            "order": response,
            "verification": verification,
        }

    def post_exit_verification(self) -> dict:
        lifecycle = self.lifecycle_payload(light=True, refresh=True)
        scanner = self.scanner_public_status()
        return {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "lifecycle": lifecycle,
            "scanner": scanner,
            "scanner_reopen": self.scanner_reopen_check(lifecycle=lifecycle),
        }

    def move_eligible_stops_to_breakeven(self, approval_token: str) -> dict:
        auth = self._authorize_approval_token(approval_token)
        if not auth.get("ok"):
            return auth
        if not self.broker.is_configured():
            return {"ok": False, "reason": "broker_not_configured"}
        if self.webhook_config.get("paper_only", True) and "paper-api.alpaca.markets" not in self.broker.config.base_url:
            return {"ok": False, "reason": "non_paper_alpaca_endpoint_blocked"}
        lifecycle = self.lifecycle_payload(light=False, refresh=True)
        moved = []
        skipped = []
        for position in lifecycle.get("positions", []):
            if not self._breakeven_stop_due(position):
                skipped.append({"symbol": position.get("symbol"), "reason": "breakeven_not_due"})
                continue
            symbol = str(position.get("symbol") or "").upper().strip()
            qty = self._position_qty_string(position)
            entry_price = self._float(position.get("entry_price"))
            if not symbol or not qty or entry_price is None:
                skipped.append({"symbol": symbol, "reason": "missing_symbol_qty_or_entry"})
                continue
            stop_orders = [
                order for order in position.get("open_orders", [])
                if str(order.get("type") or "").lower() in {"stop", "stop_limit", "trailing_stop"}
            ]
            canceled = []
            try:
                for order in stop_orders:
                    order_id = str(order.get("id") or "")
                    if order_id and hasattr(self.broker, "cancel_order"):
                        self.broker.cancel_order(order_id)
                        canceled.append(order_id)
                payload = {
                    "symbol": symbol,
                    "qty": str(qty),
                    "side": "sell" if str(position.get("side")) == "long" else "buy",
                    "type": "stop",
                    "time_in_force": self.webhook_config.get("time_in_force", "day"),
                    "stop_price": f"{entry_price:.2f}",
                    "client_order_id": f"manual-breakeven-stop-{symbol.lower()}-{secrets.token_hex(8)}",
                }
                response = self.broker.submit_order_payload(payload)
                moved.append({"symbol": symbol, "qty": qty, "stop_price": round(entry_price, 2), "canceled": canceled, "order": response})
            except Exception as exc:
                skipped.append({"symbol": symbol, "reason": f"broker_stop_move_failed:{exc}"})
        result = {"ok": True, "moved": moved, "skipped": skipped, "moved_count": len(moved)}
        if moved:
            self._notify_event(
                key=f"breakeven-stop-move:{datetime.now(timezone.utc).isoformat()}",
                title="Trading Bull stops moved to breakeven",
                detail="; ".join(f"{item['symbol']} stop {item['stop_price']}" for item in moved),
                severity="info",
                payload={"kind": "breakeven_stop_move", "timestamp": datetime.now(timezone.utc).isoformat(), "moved": moved},
                ignore_cooldown=True,
            )
        result["lifecycle"] = self.lifecycle_payload(light=True, refresh=True)
        return result

    def lifecycle_outcomes_payload(self) -> dict:
        return {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "outcomes": self.journal.latest_trade_outcomes(limit=50),
        }

    def winston_lifecycle_readback(self) -> dict:
        lifecycle = self.lifecycle_payload(light=True, refresh=True)
        return {
            "ok": True,
            "intent": "trade_lifecycle",
            "reply": lifecycle.get("readback") or "Lifecycle reconciliation is ready, but no active position detail is available yet.",
            "provider": "winston_lifecycle_readback_v1",
            "llm_used": False,
            "lifecycle": lifecycle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def webhook_test_payload(self, payload: Optional[dict] = None) -> dict:
        payload = payload or {}
        auth = self._authorize_approval_token(str(payload.get("approval_token", "")))
        if not auth.get("ok"):
            return auth

        symbols = self.watchlist_symbols()
        symbol = str(payload.get("symbol") or (symbols[0].get("symbol") if symbols else "SPY") or "SPY").upper().strip()
        side = str(payload.get("side") or "buy").lower()
        if side not in {"buy", "sell"}:
            side = "buy"
        entry = self._float(payload.get("entry_price")) or 100.0
        stop = self._float(payload.get("stop_price"))
        if stop is None:
            stop = entry - 1.0 if side == "buy" else entry + 1.0
        test_payload = {
            "id": f"dashboard-dry-run-{int(datetime.now(timezone.utc).timestamp())}-{symbol}",
            "mode": "signal",
            "source": "dashboard_e2e_test",
            "symbol": symbol,
            "side": side,
            "play": "diagnostic_webhook_test",
            "order_type": "market",
            "entry_price": entry,
            "stop_price": stop,
            "close": entry,
            "timeframe": str(payload.get("timeframe") or "TEST"),
            "location": "diagnostic_dry_run",
            "diagnostic": True,
            "dry_run": True,
        }
        alert_id = self._alert_id(test_payload)
        decision = self._handle_signal_payload(test_payload, alert_id, dry_run=True)
        self._remember_decisions([decision], alert_id)
        return {
            "ok": decision.status not in {"rejected", "error"},
            "dry_run": True,
            "message": "Webhook pipe test completed without staging or submitting an order.",
            "decisions": [decision.__dict__],
            "coverage": self.alert_coverage_payload(light=True),
        }

    def risk_status_payload(self) -> dict:
        approval_required = self._requires_order_approval()
        token_configured = bool(
            os.getenv("VELEZ_APPROVAL_API_TOKEN", "").strip()
            or os.getenv(self.webhook_config.get("secret_env", "VELEZ_WEBHOOK_SECRET"), "").strip()
            or str(self.webhook_config.get("secret", "")).strip()
        )
        return {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "execution_armed": self._execute_orders(),
            "approval_required": approval_required,
            "approval_mode_source": self._approval_mode_source(),
            "approval_token_configured": token_configured,
            "pending_approvals": len(self.journal.pending_orders()),
            "risk": {
                "risk_per_trade": self.risk_config.get("risk_per_trade"),
                "max_dollar_risk_per_trade": self.risk_config.get("max_dollar_risk_per_trade"),
                "max_daily_loss_pct": self.risk_config.get("max_daily_loss_pct"),
                "max_open_positions": self.risk_config.get("max_open_positions"),
                "max_stop_pct": self.risk_config.get("max_stop_pct"),
                "max_order_qty": self.risk_config.get("max_order_qty"),
                "max_leverage": self.risk_config.get("max_leverage"),
                "pyramid_add_fraction": self.risk_config.get("pyramid_add_fraction", 0.5),
                "lot_sizing": public_lot_config(self.risk_config.get("lot_sizing")),
            },
            "guardrails": {
                "paper_only": self.webhook_config.get("paper_only", True),
                "time_in_force": self.webhook_config.get("time_in_force", "day"),
                "take_profit_r": self.webhook_config.get("take_profit_r"),
                "auth_required": self.webhook_config.get("auth_required", True),
            },
        }

    def notification_test_payload(self, channel: str = "all") -> dict:
        targets = self._notification_targets()
        if channel and channel != "all":
            targets = [target for target in targets if target.get("type") == channel]
        if not targets:
            return {"ok": False, "reason": "no_notification_targets_configured", "channel": channel or "all"}
        key = f"manual-test:{int(time.time())}"
        self._notify_event(
            key=key,
            title="Trading Bull Desk notification test",
            detail="Notification delivery is wired and reachable from the VPS.",
            severity="info",
            payload={
                "kind": "notification_test",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "channel": channel or "all",
            },
            ignore_cooldown=True,
        )
        return {
            "ok": True,
            "channel": channel or "all",
            "targets": [target.get("type") for target in targets],
            "message": "Notification test dispatched.",
        }

    def set_order_approval_required(self, enabled: bool, approval_token: str) -> dict:
        auth = self._authorize_approval_token(approval_token)
        if not auth.get("ok"):
            return auth
        self.journal.set_setting("require_order_approval", bool(enabled))
        return {**self.risk_status_payload(), "changed": True}

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
        perf = self._setup_performance_summary(days=90)
        perf_line = "Setup performance: "
        if perf.get("setups"):
            top = list(perf["setups"].items())[:3]
            perf_line += "; ".join(f"{setup} {stats['grade']}({stats['win_rate']:.0f}%/${stats['total_pnl']:,.0f})" for setup, stats in top)
        else:
            perf_line += "no closed trades in lookback period."
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
            perf_line,
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
                "performance": [perf_line],
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

    def send_daily_brief_notification(self) -> dict:
        targets = self._notification_targets()
        if not any(target.get("type") == "telegram" for target in targets):
            return {"ok": False, "reason": "telegram_not_configured"}
        brief = self.daily_brief_payload()
        lines = brief.get("lines", [])
        text_lines = lines[:8]
        if brief.get("pending_approvals"):
            text_lines.append(brief.get("sections", {}).get("approvals", ["Paper order approval pending."])[0])
        self._notify_event(
            key=f"daily-brief:{datetime.now(timezone.utc).date().isoformat()}:{int(time.time())}",
            title="Trading Bull Daily Brief",
            detail="\n".join(str(line) for line in text_lines if str(line).strip()),
            severity="info",
            payload={
                "kind": "daily_brief",
                "timestamp": brief.get("timestamp"),
                "voice_summary": brief.get("voice_summary"),
                "summary": brief.get("sections", {}),
                "telegram_audio": True,
            },
            ignore_cooldown=True,
        )
        return {
            "ok": True,
            "message": "Daily brief notification dispatched.",
            "telegram_audio_enabled": _bool_env("VELEZ_NOTIFY_TELEGRAM_AUDIO_ENABLED", False),
            "voice": self.winston.voice_status(),
            "brief": brief,
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

    def daily_close_report_payload(self) -> dict:
        now = datetime.now(timezone.utc)
        review = self.daily_review_payload()
        health = self.bot_health(light=True)
        coverage = self.alert_coverage_payload(light=True)
        risk = self.risk_status_payload()
        calendar = self.calendar_month()
        latest = [self._journal_entry(item) for item in self.journal.latest_decisions(limit=6)]
        coverage_summary = coverage.get("summary", {})
        pending = self.journal.public_pending_orders()
        actions = []
        if coverage_summary.get("needs_setup"):
            actions.append(f"Refresh or verify TradingView Watchlist Alerts for {coverage_summary.get('needs_setup')} symbol lane(s).")
        if pending:
            actions.append(f"Resolve {len(pending)} staged paper approval(s) before ending the day.")
        if health.get("overall") != "green":
            actions.append("Review yellow/red health checks before leaving the VPS unattended.")
        if not actions:
            actions.append("No urgent desk actions from the close report.")
        sections = {
            "performance": review.get("lines", [])[:5],
            "coverage": [
                f"Alert coverage score {coverage_summary.get('coverage_score', 0)}%.",
                f"{coverage_summary.get('healthy', 0)} healthy, {coverage_summary.get('stale', 0)} stale, {coverage_summary.get('never', 0)} never.",
            ],
            "risk": [
                f"Execution is {'armed' if risk.get('execution_armed') else 'proposal-only'}.",
                f"Approval gate is {'required' if risk.get('approval_required') else 'current auto-submit mode'} from {risk.get('approval_mode_source')}.",
                f"Max dollar risk per trade is ${float(risk.get('risk', {}).get('max_dollar_risk_per_trade') or 0):,.2f}.",
            ],
            "tomorrow": [
                self._watch_plan(self.dashboard_state(), calendar),
                "Carry forward only the cleanest setups: location, stop, size, then execution.",
            ],
            "action_items": actions,
        }
        return {
            "ok": True,
            "timestamp": now.isoformat(),
            "date": now.date().isoformat(),
            "title": "Daily Close Report",
            "summary": " ".join(section[0] for section in sections.values() if section),
            "sections": sections,
            "review": review,
            "health": health,
            "coverage": coverage,
            "latest": latest,
            "pending_approvals": pending,
        }

    def winston_morning_call_payload(self) -> dict:
        now = datetime.now(timezone.utc)
        local_hour = int(now.astimezone().hour)
        greeting = "Good morning" if local_hour < 12 else "Good afternoon" if local_hour < 18 else "Good evening"
        brief = self.daily_brief_payload()
        call_lines = [
            f"{greeting}. Trading Bull Desk is online.",
            *brief.get("lines", [])[:8],
            "I will keep trade approvals guarded and call out stale TradingView alert coverage from the command center.",
        ]
        return {
            "ok": True,
            "timestamp": now.isoformat(),
            "summary": " ".join(call_lines),
            "lines": call_lines,
            "brief": brief,
            "provider": "winston_morning_call_v1",
            "brain": self.winston.brain_status(),
            "voice": self.winston.voice_status(),
        }

    def trade_review_payload(self, alert_ref: str = "") -> dict:
        target = self.journal.decision_by_alert_ref(alert_ref) if alert_ref else None
        all_entries = self.journal.decision_entries(limit=500)
        if target is None and all_entries:
            target = all_entries[0]
        if target is None:
            return {"ok": False, "reason": "no_journal_entries"}

        entry = self._journal_entry(target)
        symbol = str(entry.get("symbol") or "").upper().strip()
        same_symbol = [item for item in all_entries if str(item.get("symbol") or "").upper().strip() == symbol]
        same_symbol_sorted = sorted(same_symbol, key=lambda item: self._timestamp_sort_key(item.get("timestamp")))
        target_ref = entry.get("alert_ref")
        target_index = next((idx for idx, item in enumerate(same_symbol_sorted) if item.get("alert_ref") == target_ref), -1)
        before = same_symbol_sorted[max(0, target_index - 2):target_index] if target_index >= 0 else []
        after = same_symbol_sorted[target_index + 1:target_index + 4] if target_index >= 0 else []
        status = str(entry.get("status") or "")
        checks = entry.get("checks", {})
        rule_read = [
            self._review_check("Location filter", checks.get("has_location"), "Setup carried a structural location tag."),
            self._review_check("Stop present", checks.get("has_stop"), "Entry had a defined invalidation level."),
            self._review_check("Sized order", checks.get("has_size"), "Risk sizing produced a non-zero quantity."),
            self._review_check("Actionable", checks.get("actionable_status"), "Signal became proposed or submitted."),
        ]
        verdict = "Actionable setup followed the core structure/risk checks." if status in {"proposed", "submitted", "diagnostic"} else f"Blocked by guardrail: {entry.get('reason', 'unknown')}."
        return {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entry": entry,
            "verdict": verdict,
            "rule_checks": rule_read,
            "timeline": {
                "before": [self._journal_entry(item) for item in before],
                "after": [self._journal_entry(item) for item in after],
            },
            "replay_scenario": self._setup_to_replay_scenario(entry.get("setup") or entry.get("play") or entry.get("reason")),
            "what_happened_after": self._what_happened_after(after),
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
            self._health_component("TradingView webhook", True, "listening", self._last_alert_label(last_alert)),
            self._health_component("VPS scanner", bool(self.scanner_public_status().get("running") or not self.scanner_config.get("enabled", False)), self.scanner_public_status().get("mode", "unknown"), self._scanner_health_detail()),
            self._health_component("Journal database", journal_ok, "ready" if journal_ok else "missing", str(self.journal.path)),
            self._health_component("Calendar feeds", True, "configured", "Alpaca, Alpha Vantage, and public macro feeds"),
            self._health_component("Winston brain", bool(winston.get("brain", {}).get("available")), winston.get("brain", {}).get("provider", "unknown"), winston.get("brain", {}).get("detail", "")),
            self._health_component("Winston voice", bool(winston.get("voice", {}).get("available")), winston.get("voice", {}).get("provider", "unknown"), winston.get("voice", {}).get("detail", "")),
        ]
        if positions_error:
            components.append(self._health_component("Positions", False, "needs check", positions_error))
        else:
            components.append(self._health_component("Positions", True, f"{len(positions)} open", "Broker position snapshot read"))
        lifecycle = self.journal.latest_lifecycle_snapshot()
        lifecycle_guardrails = int(lifecycle.get("summary", {}).get("guardrails") or 0) if lifecycle else 0
        components.append(
            self._health_component(
                "Lifecycle guardrails",
                lifecycle_guardrails == 0,
                "clear" if lifecycle_guardrails == 0 else f"{lifecycle_guardrails} alert(s)",
                lifecycle.get("readback", "Run lifecycle reconciliation from the command center.") if lifecycle else "No reconciliation snapshot yet.",
            )
        )
        hard_failures = [item for item in components if not item["ok"] and item["name"] in {"Alpaca paper", "Paper endpoint", "Journal database"}]
        soft_failures = [item for item in components if not item["ok"] and item["name"] not in {"Alpaca paper", "Paper endpoint", "Journal database"}]
        overall = "green" if not hard_failures and not soft_failures else "yellow" if not hard_failures else "red"
        summary = "All core services are ready" if overall == "green" else f"{len(hard_failures) + len(soft_failures)} component checks need attention"
        return {
            "ok": True,
            "timestamp": now.isoformat(),
            "overall": overall,
            "summary": summary,
            "dashboard_version": DASHBOARD_VERSION,
            "execution_armed": self._execute_orders(),
            "approval_required": self._requires_order_approval(),
            "last_alert": last_alert,
            "components": components if not light else components[:8],
        }

    def latency_payload(self) -> dict:
        started = time.perf_counter()

        def probe(name: str, func) -> dict:
            probe_started = time.perf_counter()
            try:
                detail = func()
                ok = True
                status = "ok"
            except Exception as exc:
                detail = str(exc)
                ok = False
                status = "error"
            elapsed_ms = round((time.perf_counter() - probe_started) * 1000, 1)
            return {
                "name": name,
                "ok": ok,
                "status": status,
                "latency_ms": elapsed_ms,
                "detail": str(detail)[:220],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        checks = [
            probe("API loop", lambda: f"uptime {int((datetime.now(timezone.utc) - self.started_at).total_seconds())}s"),
            probe("Journal read", lambda: f"{len(self.journal.latest_decisions(limit=5))} latest decisions"),
            probe("Alert coverage", lambda: f"{self.alert_coverage_payload(light=True).get('summary', {}).get('coverage_score', 0)}% coverage"),
            probe("Broker account", lambda: self.broker.validate_connection().get("account_status") if self.broker.is_configured() else "missing credentials"),
            probe("Winston status", lambda: self.winston.status(include_health_check=True).get("brain", {}).get("detail", "checked")),
        ]
        latencies = [item["latency_ms"] for item in checks]
        slow_threshold = self._float(os.getenv("VELEZ_LATENCY_WARN_MS", "1200")) or 1200.0
        slow = [item for item in checks if item["latency_ms"] > slow_threshold]
        failed = [item for item in checks if not item["ok"]]
        overall = "green" if not failed and not slow else "yellow" if not failed else "red"
        return {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall": overall,
            "uptime_seconds": int((datetime.now(timezone.utc) - self.started_at).total_seconds()),
            "total_latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "average_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
            "worst_latency_ms": max(latencies) if latencies else 0,
            "warn_threshold_ms": slow_threshold,
            "checks": checks,
            "summary": "All latency probes are within threshold." if overall == "green" else f"{len(failed)} failed, {len(slow)} slow probe(s).",
        }

    def vps_hardening_payload(self) -> dict:
        now = datetime.now(timezone.utc)
        data_dir = Path(os.getenv("VELEZ_DATA_DIR", "bot/data/runtime"))
        backup_dir = Path(os.getenv("VELEZ_BACKUP_DIR", "data/backups"))
        stack_root = Path(os.getenv("VELEZ_STACK_ROOT", "/opt/stacks/velez-trading-bot"))
        compose_restart = self._compose_restart_policy()
        checks = [
            self._health_component("Container restart", compose_restart == "unless-stopped", compose_restart or "unknown", "Docker Compose should restart the webhook after VPS reboot or crash"),
            self._health_component("Journal database", self.journal.path.exists(), "ready" if self.journal.path.exists() else "missing", str(self.journal.path)),
            self._health_component("Data directory", data_dir.exists(), "mounted" if data_dir.exists() else "check", str(data_dir)),
            self._health_component("Backup directory", backup_dir.exists() or backup_dir.parent.exists(), "ready" if backup_dir.exists() else "will create", str(backup_dir)),
            self._health_component("Public health", bool(os.getenv("VELEZ_PUBLIC_URL") or os.getenv("VELEZ_PUBLIC_HOST")), "configured" if os.getenv("VELEZ_PUBLIC_URL") or os.getenv("VELEZ_PUBLIC_HOST") else "local", os.getenv("VELEZ_PUBLIC_URL") or os.getenv("VELEZ_PUBLIC_HOST", "")),
        ]
        return {
            "ok": True,
            "timestamp": now.isoformat(),
            "overall": "green" if all(item["ok"] for item in checks[:3]) else "yellow",
            "checks": checks,
            "paths": {
                "stack_root": str(stack_root),
                "journal_db": str(self.journal.path),
                "backup_dir": str(backup_dir),
            },
            "helpers": [
                {"name": "Health check", "path": "bot/deploy/vps_healthcheck.sh", "purpose": "Curl the public health endpoints and fail loudly if the bot is down."},
                {"name": "Backup", "path": "bot/deploy/vps_backup.sh", "purpose": "Archive .env, config, journal database, Pine script, and deployment docs."},
                {"name": "Install hardening", "path": "bot/deploy/vps_hardening_install.sh", "purpose": "Install scripts on the VPS and add a daily cron backup."},
            ],
            "note": "Read-only status. Changing VPS cron or restart policy is handled by the deploy helper scripts, not by the public dashboard.",
        }

    def replay_payload(self, payload: dict) -> dict:
        symbol = str(payload.get("symbol") or (self.watchlist_symbols() or [{"symbol": "SPY"}])[0].get("symbol") or "SPY").upper().strip()
        scenario = str(payload.get("scenario") or "bull_elephant").strip() or "bull_elephant"
        bars_payload = payload.get("bars")
        bars = bars_payload if isinstance(bars_payload, list) and bars_payload else self._sample_replay_bars(scenario)
        equity = self._float(payload.get("equity")) or self.config.get("portfolio", {}).get("initial_cash", 100000)
        strategy = VelezInstitutionalStrategy(self._replay_strategy_config(scenario), self.logger)
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

    def risk_replay_payload(self, payload: dict) -> dict:
        replay = self.replay_payload(payload)
        equity = self._float(payload.get("equity")) or self.config.get("portfolio", {}).get("initial_cash", 100000)
        configured_budget = self._risk_budget(float(equity))
        requested = payload.get("risk_amounts")
        risk_lot_max = int(public_lot_config(self.risk_config.get("lot_sizing")).get("max_lots") or 4)
        if isinstance(requested, list) and requested:
            risk_amounts = [self._float(item) for item in requested]
            risk_amounts = [float(item) for item in risk_amounts if item and item > 0]
            risk_lots = {}
        else:
            lot_cfg = public_lot_config(self.risk_config.get("lot_sizing"))
            risk_lot_max = int(lot_cfg.get("max_lots") or 4)
            lot_fraction = float(lot_cfg.get("lot_risk_fraction") or 0.25)
            risk_lots = {
                round(configured_budget * lot_fraction * lot, 2): lot
                for lot in range(1, risk_lot_max + 1)
            }
            risk_amounts = sorted(risk_lots)
        max_order_qty = int(self.risk_config.get("max_order_qty", 10000))
        max_leverage = float(self.risk_config.get("max_leverage", 1.0))
        variants = []
        for event in (replay.get("events") or [])[-5:]:
            entry = self._float(event.get("entry_price"))
            stop = self._float(event.get("stop_price"))
            if entry is None or stop is None:
                continue
            symbol = str(event.get("symbol") or replay.get("symbol") or "").upper()
            sym_cfg = self.symbol_config.get(symbol, {}) or self.journal.get_watchlist_symbol(symbol) or {}
            multiplier = float(sym_cfg.get("contract_multiplier", 1.0) or 1.0)
            risk_per_unit = abs(entry - stop) * multiplier
            for amount in risk_amounts:
                lots = risk_lots.get(round(amount, 2))
                qty = self.risk.calculate_fixed_risk_position_size(
                    max_dollar_risk=amount,
                    entry_price=entry,
                    stop_price=stop,
                    contract_multiplier=multiplier,
                    max_order_qty=max_order_qty,
                    equity=float(equity),
                    max_leverage=max_leverage,
                )
                variants.append(
                    {
                        "symbol": symbol,
                        "scenario": replay.get("scenario"),
                        "play": event.get("play"),
                        "side": event.get("side"),
                        "lots": lots,
                        "lot_label": f"{lots}/{risk_lot_max} lots" if lots else "custom risk",
                        "risk_budget": amount,
                        "qty": qty,
                        "estimated_risk": round(risk_per_unit * qty, 2),
                        "risk_per_unit": round(risk_per_unit, 4),
                        "entry_price": entry,
                        "stop_price": stop,
                        "approval_mode": "approval_required" if self._requires_order_approval() else "current_auto_submit_mode",
                    }
                )
        result = {
            **replay,
            "mode": "risk_replay",
            "risk_replay": {
                "equity": equity,
                "configured_budget": configured_budget,
                "risk_amounts": risk_amounts,
                "variants": variants,
                "summary": self._risk_replay_summary(replay, variants),
                "guardrail": "Risk replay is a calculator only; it never submits broker orders.",
            },
        }
        self.journal.save_replay({**result, "scenario": f"{replay.get('scenario', 'replay')}_risk"})
        return result

    def _replay_strategy_config(self, scenario: str) -> dict:
        cfg = deepcopy(self.config.get("velez_strategy", self.config.get("strategy", {})))
        scenario_sections = {
            "bull_elephant": "elephant",
            "bear_180": "one_eighty",
            "buy_setup": "buy_sell_setup",
            "sell_setup": "buy_sell_setup",
            "nrb_acorn": "nrb_acorn",
            "color_change_add": "color_change",
            "fab4_trap": "fab4",
            "failed_new_high": "failed_breakout",
            "failed_new_low": "failed_breakout",
            "opening_gap_go": "opening_gap",
            "opening_gap_fade": "opening_gap",
            "time_space_breakout": "time_space",
        }
        target = scenario_sections.get(str(scenario or ""))
        if target:
            for section in ("elephant", "one_eighty", "tail", "buy_sell_setup", "nrb_acorn", "color_change", "fab4", "failed_breakout", "opening_gap", "time_space"):
                section_cfg = cfg.setdefault(section, {})
                section_cfg["enabled"] = section == target
            if target == "opening_gap":
                cfg.setdefault("opening_gap", {})["opening_window_minutes"] = 15
                cfg.setdefault("opening_gap", {})["structure_lookback"] = 30
            if target == "time_space":
                cfg.setdefault("time_space", {})["opening_window_minutes"] = 30
                cfg.setdefault("time_space", {})["structure_lookback"] = 30
        return cfg

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
        lot_plan = item.get("lot_plan") if isinstance(item.get("lot_plan"), dict) else {}
        if lot_plan:
            readback.append(
                f"Lot plan: {lot_plan.get('label', 'active')} | risk budget ${float(lot_plan.get('effective_risk_budget') or 0):,.2f}"
            )
        receipt = item.get("confidence_receipt") if isinstance(item.get("confidence_receipt"), dict) else self._confidence_receipt_from_entry(item, checks)
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
                "lot_plan": lot_plan,
            },
            "confidence_receipt": receipt,
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

    def _alert_coverage_checklist(self, symbol_row: dict, latest: Optional[dict], age_seconds: Optional[int], stale_seconds: int) -> List[dict]:
        payload_version = str((latest or {}).get("payload_version") or "").strip()
        has_required_payload = bool(
            latest
            and latest.get("symbol")
            and (latest.get("play") or latest.get("reason"))
            and latest.get("status")
        )
        return [
            self._health_component("Bot watchlist", bool(symbol_row.get("enabled", True)), "enabled" if symbol_row.get("enabled", True) else "disabled", "Symbol is saved in Trading Bull Desk."),
            self._health_component("TradingView reach", latest is not None, "seen" if latest else "not seen", "At least one alert reached the VPS journal." if latest else "Create or include this symbol in a TradingView Watchlist Alert."),
            self._health_component("Freshness", latest is not None and age_seconds is not None and age_seconds <= stale_seconds, "fresh" if latest and age_seconds is not None and age_seconds <= stale_seconds else "stale", self._age_label(latest.get("timestamp")) if latest else "No saved alert timestamp."),
            self._health_component("Payload fields", has_required_payload, "current" if has_required_payload else "review", "Symbol, play/reason, and status were present in the latest alert."),
            self._health_component("Pine payload", bool(payload_version) or has_required_payload, payload_version or "compatible", "Versioned Pine payload detected." if payload_version else "Compatible payload shape; version tag not supplied."),
        ]

    def _confidence_receipt(self, decision: WebhookDecision, snapshot: dict, order_payload: dict, metadata: dict) -> dict:
        source = metadata.get("source_metadata") if isinstance(metadata.get("source_metadata"), dict) else {}
        entry = self._float(snapshot.get("entry_price"))
        stop = self._float(snapshot.get("stop_price"))
        target = self._float(snapshot.get("take_profit_price"))
        qty = int(self._float(snapshot.get("qty")) or 0)
        location = snapshot.get("location")
        location_ok = bool(location)
        risk_per_unit = abs(entry - stop) if entry is not None and stop is not None else None
        risk_dollars = risk_per_unit * qty if risk_per_unit is not None and qty else None
        max_risk = self._float(metadata.get("max_dollar_risk") or snapshot.get("max_dollar_risk"))
        risk_ok = risk_dollars is not None and (max_risk is None or risk_dollars <= max_risk * 1.01)
        lot_plan = metadata.get("lot_plan") if isinstance(metadata.get("lot_plan"), dict) else snapshot.get("lot_plan") if isinstance(snapshot.get("lot_plan"), dict) else {}
        lot_ok = bool(lot_plan) or bool(metadata.get("scale_add"))
        rr_ok = True
        if target is not None and risk_per_unit:
            rr_ok = abs(target - entry) / risk_per_unit >= 1.0
        raw_checks = [
            ("Location qualified", location_ok, 20, "Structural location tag supplied."),
            ("Entry/stop defined", entry is not None and stop is not None, 20, "Trade has mathematical invalidation."),
            ("Risk sized", qty > 0 and risk_ok, 20, "Quantity respects configured risk budget."),
            ("Actionable status", decision.status in {"proposed", "submitted", "diagnostic"}, 15, "Signal passed execution/proposal gate."),
            ("Lot conviction", lot_ok, 5, "Velez 1-4 lot conviction ladder applied."),
            ("No chase flag", not bool(source.get("chased")), 10, "Alert was not marked as beyond the no-chase band."),
            ("Timeframe present", bool(snapshot.get("timeframe")), 5, "TradingView timeframe was included."),
            ("Payload compatible", bool(snapshot.get("symbol") and (snapshot.get("play") or snapshot.get("reason"))), 5, "Required alert fields were present."),
            ("Target/risk coherent", rr_ok, 0, "Take-profit relationship is coherent when configured."),
        ]
        checks = [
            {"name": name, "ok": bool(ok), "weight": weight, "detail": detail}
            for name, ok, weight, detail in raw_checks
        ]
        score = sum(item["weight"] for item in checks if item["ok"])
        if decision.status in {"rejected", "error"}:
            score = min(score, 45)
        if decision.status == "ignored":
            score = min(score, 35)
        grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"
        risk_readback = "Risk could not be computed from the alert."
        if risk_per_unit is not None:
            risk_readback = f"Risk/unit {risk_per_unit:g}; qty {qty}; estimated risk ${float(risk_dollars or 0):,.2f}."
        if lot_plan:
            risk_readback = (
                f"{lot_plan.get('label', 'Lot plan active')}; risk budget ${float(lot_plan.get('effective_risk_budget') or max_risk or 0):,.2f}. "
                f"{risk_readback}"
            )
        return {
            "score": score,
            "grade": grade,
            "accepted": decision.status in {"proposed", "submitted", "diagnostic"},
            "summary": f"{grade} receipt, {score}/100: {decision.reason}.",
            "checks": checks,
            "risk_readback": risk_readback,
            "lot_plan": lot_plan,
            "guardrail": "Paper-only Velez execution guardrails applied before any order submission.",
            "next_action": self._confidence_next_action(decision.status),
        }

    def _confidence_receipt_from_entry(self, entry: dict, checks: dict) -> dict:
        score = (
            (20 if checks.get("has_location") else 0)
            + (25 if checks.get("has_stop") else 0)
            + (25 if checks.get("has_size") else 0)
            + (20 if checks.get("actionable_status") else 0)
            + 10
        )
        if entry.get("status") in {"rejected", "error"}:
            score = min(score, 45)
        grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"
        return {
            "score": score,
            "grade": grade,
            "accepted": entry.get("status") in {"proposed", "submitted", "diagnostic"},
            "summary": f"{grade} receipt, {score}/100: {entry.get('reason', 'journal entry')}.",
            "checks": [
                {"name": "Location qualified", "ok": bool(checks.get("has_location")), "weight": 20, "detail": "Structural location tag supplied."},
                {"name": "Entry/stop defined", "ok": bool(checks.get("has_stop")), "weight": 25, "detail": "Trade has mathematical invalidation."},
                {"name": "Risk sized", "ok": bool(checks.get("has_size")), "weight": 25, "detail": "Quantity is non-zero."},
                {"name": "Actionable status", "ok": bool(checks.get("actionable_status")), "weight": 20, "detail": "Signal became proposed or submitted."},
            ],
            "risk_readback": "Legacy journal entry rebuilt from saved fields.",
            "guardrail": "Paper-only Velez execution guardrails applied before any order submission.",
            "next_action": self._confidence_next_action(str(entry.get("status") or "")),
        }

    def _confidence_next_action(self, status: str) -> str:
        if status == "submitted":
            return "Monitor Alpaca paper order and journal the management outcome."
        if status == "proposed":
            return "Review the readback and use guarded approval only if you want paper submission."
        if status == "diagnostic":
            return "Webhook pipe passed; create or verify the matching TradingView alert."
        if status in {"rejected", "error"}:
            return "Do not trade this alert; review the failed receipt checks first."
        return "Wait for the next qualified TradingView alert."

    def _review_check(self, name: str, ok: Any, detail: str) -> dict:
        return {
            "name": name,
            "ok": bool(ok),
            "status": "pass" if ok else "review",
            "detail": detail,
        }

    def _what_happened_after(self, entries: List[dict]) -> str:
        if not entries:
            return "No later journal decision for this symbol is saved yet."
        latest = entries[-1]
        return (
            f"Later journal activity: {latest.get('symbol')} {latest.get('play') or latest.get('reason')} "
            f"ended with status {latest.get('status', 'seen')}."
        )

    def _setup_to_replay_scenario(self, setup: Any) -> str:
        normalized = str(setup or "").lower()
        mapping = {
            "elephant": "bull_elephant",
            "bull_180": "bull_elephant",
            "bear_180": "bear_180",
            "velez_buy_setup": "buy_setup",
            "velez_sell_setup": "sell_setup",
            "buy_setup": "buy_setup",
            "sell_setup": "sell_setup",
            "nrb": "nrb_acorn",
            "acorn": "nrb_acorn",
            "color_change": "color_change_add",
            "fab4": "fab4_trap",
            "failed_new_high": "failed_new_high",
            "failed_new_low": "failed_new_low",
            "opening_gap_go": "opening_gap_go",
            "opening_gap_fade": "opening_gap_fade",
            "time_space": "time_space_breakout",
        }
        for key, value in mapping.items():
            if key in normalized:
                return value
        return "bull_elephant"

    def _timestamp_sort_key(self, value: Any) -> float:
        try:
            return self._timestamp(value).timestamp()
        except Exception:
            return 0.0

    def _seconds_since(self, value: Any) -> Optional[int]:
        try:
            parsed = self._timestamp(value)
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()))

    def _int_env(self, name: str, default: int, *, minimum: int, maximum: int) -> int:
        try:
            value = int(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(value, maximum))

    def _compose_restart_policy(self) -> str:
        configured = os.getenv("VELEZ_RESTART_POLICY", "").strip()
        if configured:
            return configured
        for candidate in (Path("docker-compose.yml"), Path("bot/deploy/docker-compose.yml")):
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError:
                continue
            match = re.search(r"restart:\s*([a-zA-Z0-9_-]+)", text)
            if match:
                return match.group(1)
        return "unknown"

    def _last_alert_label(self, decision: Optional[dict]) -> str:
        if not decision:
            return "No TradingView alerts logged yet"
        parts = [decision.get("symbol"), decision.get("play") or decision.get("reason"), decision.get("status")]
        return f"{' | '.join(str(part) for part in parts if part)} | {self._age_label(decision.get('timestamp'))}"

    def _scanner_health_detail(self) -> str:
        status = self.scanner_public_status()
        if not status.get("enabled"):
            return "Scanner disabled; TradingView webhooks remain active."
        if status.get("last_error"):
            return str(status.get("last_error"))[:220]
        if not status.get("last_scan_at"):
            return "Scanner starting and warming indicator history."
        skipped = status.get("skipped") or []
        suffix = f"; skipped {', '.join(skipped[:3])}" if skipped else ""
        return f"{status.get('symbols_scanned', 0)} lanes scanned, {status.get('signals_found', 0)} signal(s) on last pass{suffix}."

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
        if scenario in {"opening_gap_go", "opening_gap_fade", "time_space_breakout"}:
            return self._sample_opening_time_space_bars(scenario)

        now = datetime.now(timezone.utc).replace(microsecond=0)
        start = now - timedelta(minutes=5 * 230)
        bars: List[dict] = []
        bear_mode = scenario in {"bear_180", "sell_setup", "failed_new_high"}
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

        def add(open_price: float, high: float, low: float, close: float, volume: float = 1800) -> None:
            bars.append(
                {
                    "timestamp": (start + timedelta(minutes=5 * len(bars))).isoformat(),
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "volume": volume,
                }
            )

        if scenario == "bear_180":
            add(99.82, 100.32, 99.72, 100.2, 1900)
            add(100.15, 100.28, 99.62, 99.72, 2300)
        elif scenario == "buy_setup":
            add(100.16, 100.24, 99.98, 100.06, 1700)
            add(100.06, 100.22, 100.01, 100.17, 1900)
        elif scenario == "sell_setup":
            add(99.88, 100.05, 99.8, 99.98, 1700)
            add(99.98, 100.02, 99.82, 99.87, 1900)
        elif scenario == "nrb_acorn":
            add(100.13, 100.19, 100.09, 100.15, 1300)
            add(100.15, 100.28, 100.12, 100.24, 1900)
        elif scenario == "color_change_add":
            add(100.18, 100.22, 100.02, 100.08, 1200)
            add(100.08, 100.27, 100.04, 100.24, 1500)
        elif scenario == "fab4_trap":
            add(100.08, 100.2, 99.98, 100.05, 1200)
            add(100.05, 100.19, 99.99, 100.08, 1250)
            add(100.08, 100.32, 100.04, 100.24, 2200)
        elif scenario == "failed_new_high":
            add(99.94, 100.1, 99.9, 100.02, 1500)
            add(100.04, 100.38, 99.92, 100.0, 2300)
        elif scenario == "failed_new_low":
            add(100.08, 100.12, 99.92, 99.98, 1500)
            add(99.98, 100.08, 99.62, 100.02, 2300)
        else:
            add(100.06, 102.04, 99.92, 101.84, 2800)
        return bars

    def _sample_opening_time_space_bars(self, scenario: str) -> List[dict]:
        current_open = datetime(2026, 1, 6, 14, 30, tzinfo=timezone.utc)
        prev_end = datetime(2026, 1, 5, 20, 55, tzinfo=timezone.utc)
        start = prev_end - timedelta(minutes=5 * 223)
        bars: List[dict] = []
        for index in range(224):
            center = 99.6 + index * 0.0018
            open_price = center
            close_price = center + 0.03
            bars.append(
                {
                    "timestamp": (start + timedelta(minutes=5 * index)).isoformat(),
                    "open": round(open_price, 2),
                    "high": round(max(open_price, close_price) + 0.08, 2),
                    "low": round(min(open_price, close_price) - 0.08, 2),
                    "close": round(close_price, 2),
                    "volume": 900 + index,
                }
            )

        def add(offset_minutes: int, open_price: float, high: float, low: float, close: float, volume: float = 2400) -> None:
            bars.append(
                {
                    "timestamp": (current_open + timedelta(minutes=offset_minutes)).isoformat(),
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "volume": volume,
                }
            )

        if scenario == "opening_gap_fade":
            add(0, 103.5, 104.2, 102.0, 102.2, 2800)
        elif scenario == "time_space_breakout":
            add(0, 100.02, 100.08, 99.94, 100.03, 1800)
            add(2, 100.03, 100.25, 100.02, 100.18, 2300)
        else:
            add(0, 102.0, 103.1, 101.8, 103.0, 2600)
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
            "gap_direction": metadata.get("gap_direction"),
            "gap_pct": metadata.get("gap_pct"),
            "time_space_score": metadata.get("time_space_score"),
            "clean_space": metadata.get("clean_space"),
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

    def _risk_replay_summary(self, replay: dict, variants: List[dict]) -> str:
        if not replay.get("signals_found"):
            return "Risk replay found no qualified setup to size."
        if not variants:
            return "Replay found a setup, but entry/stop data was not sufficient for risk sizing."
        latest = variants[-1]
        return (
            f"Risk replay sized {len(variants)} what-if plan(s). Latest budget ${float(latest.get('risk_budget') or 0):,.2f} "
            f"maps to qty {latest.get('qty')} with estimated risk ${float(latest.get('estimated_risk') or 0):,.2f}."
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

        if self._lifecycle_prompt_intent(prompt):
            return self.winston_lifecycle_readback()

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

    def winston_deep_research(self, topic: str, symbol: Optional[str] = None) -> dict:
        cleaned_topic = " ".join(str(topic or "").split())[:500]
        if not cleaned_topic:
            return {"ok": False, "reason": "missing_topic"}
        symbol = str(symbol or self._symbol_from_text(cleaned_topic) or "").upper().strip()
        context = {
            "topic": cleaned_topic,
            "symbol": symbol,
            "depth": "deep_research",
            "daily_brief": self.daily_brief_payload(),
            "close_report": self.daily_close_report_payload(),
            "calendar": self.calendar_month(),
            "watchlist": self.watchlist_symbols(),
            "recent_decisions": self.journal.latest_decisions(limit=30),
            "latest_research": self.journal.latest_research(limit=5),
            "alert_coverage": self.alert_coverage_payload(light=True),
            "risk": self.risk_status_payload(),
            "alpha_vantage": self._alpha_research_context(symbol) if symbol else {},
        }
        fallback_reply = self._research_fallback(cleaned_topic, context)
        fallback = {
            "ok": True,
            "intent": "deep_research",
            "topic": cleaned_topic,
            "symbol": symbol,
            "reply": fallback_reply,
            "provider": "winston_deep_research_fallback_v1",
            "research_used": False,
            "mode": "deep_research",
            "context": self._public_research_context(context),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        result = self.winston.research_reply(cleaned_topic, context, fallback, deep=True)
        result["mode"] = "deep_research"
        self.journal.save_research(f"Deep: {cleaned_topic}", {key: value for key, value in result.items() if key != "context"})
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

    def _lifecycle_prompt_intent(self, prompt: str) -> bool:
        normalized = " ".join(str(prompt or "").lower().split())
        trade_action = re.search(r"\b(approve|submit|place|execute|cancel|close|liquidate|buy|sell|short|long)\b", normalized)
        trade_subject = re.search(r"\b(trade|order|position|shares|contracts|entry|stop)\b", normalized)
        if trade_action and trade_subject:
            return False
        lifecycle_words = (
            "active position",
            "open position",
            "active trade",
            "open trade",
            "trade lifecycle",
            "lifecycle",
            "r multiple",
            "r-multiple",
            "stop",
            "management",
            "manage",
            "breakeven",
            "partial",
            "unrealized",
            "p/l",
            "profit",
            "loss",
        )
        return any(word in normalized for word in lifecycle_words)

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
            "bull report": ("notes", "Opening Bull Report."),
            "bull": ("notes", "Opening Bull Report."),
            "after action": ("notes", "Opening Bull Report."),
            "review": ("notes", "Opening Bull Report."),
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
            "notes": ("notes", "Opening Bull Report."),
            "sticky": ("notes", "Opening Bull Report."),
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

        if "morning call" in normalized:
            call = self.winston_morning_call_payload()
            intent = "morning_call"
            reply = call["summary"]
        elif any(word in normalized for word in ("brief", "daily", "morning", "breakdown")):
            intent = "daily_brief"
            reply = brief["summary"]
        elif "watch" in normalized:
            intent = "watchlist"
            reply = f"Current watchlist: {symbols}. I am waiting for qualified Velez setups before any paper order can be proposed."
        elif any(word in normalized for word in ("position", "p/l", "profit", "loss", "lifecycle", "stop")):
            intent = "positions"
            lifecycle = self.lifecycle_payload(light=True, refresh=False)
            reply = lifecycle.get("readback") or f"{state.get('summary', {}).get('open_positions', 0)} positions are open with ${float(state.get('summary', {}).get('unrealized_pl') or 0):,.2f} unrealized P and L."
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

    def _handle_signal_payload(self, payload: dict, alert_id: str, *, dry_run: bool = False) -> WebhookDecision:
        try:
            signal = self._signal_from_payload(payload)
        except Exception as exc:
            return WebhookDecision(status="rejected", reason=str(exc))
        return self._build_order_decision(signal, alert_id, dry_run=dry_run)

    def _validate_lower_timeframe_signal(self, symbol: str, timeframe: str, side: str, metadata: dict) -> Optional[WebhookDecision]:
        """Gate 2m/5m signals with volume, trend, and bar-size checks.

        Returns None if the signal passes all gates, or a WebhookDecision
        with status='rejected' if any gate fails.
        """
        tf = str(timeframe or "").strip()
        if tf not in {"2", "5"}:
            return None  # Only gate 2m and 5m — 15m passes through

        cfg = self.config.get("velez_strategy", {}).get("lower_tf_filters", {})
        if not cfg.get("enabled", True):
            return None

        vol_mult = float(cfg.get("volume_mult", 1.5))
        range_mult = float(cfg.get("bar_range_mult", 1.0))
        trend_align = bool(cfg.get("trend_alignment", True))
        lookback = int(cfg.get("lookback_bars", 20))
        higher_tf = str(cfg.get("higher_tf", "15m"))

        try:
            import yfinance as yf
        except ImportError:
            self.logger.warning("lower_tf_filter_skip_yfinance_missing", extra={"symbol": symbol})
            return None  # Let signal through if yfinance isn't available

        # Fetch recent bars at the signal's timeframe for volume/range checks
        try:
            interval_map = {"2": "2m", "5": "5m"}
            interval = interval_map.get(tf, "5m")
            df = yf.download(symbol, period="5d", interval=interval, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            if df.empty or len(df) < max(lookback, 2):
                self.logger.info("lower_tf_filter_skip_insufficient_data", extra={"symbol": symbol, "bars": len(df)})
                return None
        except Exception as exc:
            self.logger.warning("lower_tf_filter_yfinance_error", extra={"symbol": symbol, "error": str(exc)})
            return None  # Let signal through on data errors

        import numpy as np
        import pandas as pd

        df["range"] = df["High"] - df["Low"]
        df["body"] = abs(df["Close"] - df["Open"])
        current = df.iloc[-1]
        window = df.iloc[-(lookback + 1):-1] if len(df) > lookback else df.iloc[:-1]

        # ── Gate 1: Volume ──
        if "Volume" in df.columns and vol_mult > 0:
            avg_vol = window["Volume"].mean()
            current_vol = float(current.get("Volume", 0) or 0)
            if avg_vol > 0 and current_vol < avg_vol * vol_mult:
                msg = (f"low_volume:{symbol} vol={current_vol:.0f} < "
                       f"{vol_mult}x avg={avg_vol:.0f}")
                self.logger.info("lower_tf_filter_rejected", extra={"symbol": symbol, "reason": "low_volume", "gate": f"vol<{vol_mult}x_avg"})
                return WebhookDecision("rejected", msg, symbol=symbol, side=side, play=str(metadata.get("play", "")))

        # ── Gate 2: Bar size ──
        if range_mult > 0:
            avg_range = window["range"].mean()
            current_range = float(current["range"])
            if avg_range > 0 and current_range < avg_range * range_mult:
                msg = (f"tiny_bar:{symbol} range={current_range:.4f} < "
                       f"{range_mult}x avg={avg_range:.4f}")
                self.logger.info("lower_tf_filter_rejected", extra={"symbol": symbol, "reason": "tiny_bar", "gate": f"range<{range_mult}x_avg"})
                return WebhookDecision("rejected", msg, symbol=symbol, side=side, play=str(metadata.get("play", "")))

        # ── Gate 3: Trend alignment (SMA20 vs SMA200 on higher timeframe) ──
        if trend_align:
            try:
                htf_df = yf.download(symbol, period="1mo", interval=higher_tf, progress=False)
                if isinstance(htf_df.columns, pd.MultiIndex):
                    htf_df.columns = htf_df.columns.droplevel(1)
                if not htf_df.empty and len(htf_df) >= 200:
                    htf_df["sma20"] = htf_df["Close"].rolling(20).mean()
                    htf_df["sma200"] = htf_df["Close"].rolling(200).mean()
                    last = htf_df.iloc[-1]
                    sma20 = float(last["sma20"])
                    sma200 = float(last["sma200"])
                    if not (np.isnan(sma20) or np.isnan(sma200)):
                        trend_up = sma20 > sma200
                        if side == "buy" and not trend_up:
                            msg = (f"trend_opposed:{symbol} 15m SMA20({sma20:.2f}) < "
                                   f"SMA200({sma200:.2f}) — rejecting buy")
                            self.logger.info("lower_tf_filter_rejected", extra={"symbol": symbol, "reason": "trend_opposed", "gate": "sma20<sma200"})
                            return WebhookDecision("rejected", msg, symbol=symbol, side=side, play=str(metadata.get("play", "")))
                        if side == "sell" and trend_up:
                            msg = (f"trend_opposed:{symbol} 15m SMA20({sma20:.2f}) > "
                                   f"SMA200({sma200:.2f}) — rejecting sell")
                            self.logger.info("lower_tf_filter_rejected", extra={"symbol": symbol, "reason": "trend_opposed", "gate": "sma20>sma200"})
                            return WebhookDecision("rejected", msg, symbol=symbol, side=side, play=str(metadata.get("play", "")))
            except Exception as exc:
                self.logger.warning("lower_tf_filter_trend_error", extra={"symbol": symbol, "error": str(exc)})
                # Let signal through on trend data errors

        return None  # All gates passed

    def _build_order_decision(self, signal: Signal, alert_id: str, *, dry_run: bool = False) -> WebhookDecision:
        symbol = signal.symbol
        metadata = signal.metadata
        side = signal.side.value
        play = str(metadata.get("play", signal.reason))
        entry_price = self._float(metadata.get("entry_price") or metadata.get("close"))
        stop_price = self._float(metadata.get("stop_price"))
        order_type = str(metadata.get("order_type", "market")).lower()

        if entry_price is None or stop_price is None:
            return WebhookDecision("rejected", "missing_entry_or_stop", symbol=symbol, side=side, play=play)
        if order_type not in {"market", "limit"}:
            return WebhookDecision("rejected", f"unsupported_order_type:{order_type}", symbol=symbol, side=side, play=play)
        max_stop_pct = self.risk_config.get("max_stop_pct", 0.1)
        if side == "buy" and stop_price >= entry_price:
            # Alert sent entry trigger as stop_price — auto-correct to a proper stop-loss below entry
            corrected = round(entry_price * (1 - max_stop_pct), 2)
            log_event(self.logger, "stop_auto_corrected", {"symbol": symbol, "side": side, "original_stop": stop_price, "corrected_stop": corrected, "reason": "alert_stop_was_entry_trigger"})
            stop_price = corrected
        if side == "sell" and stop_price <= entry_price:
            # Alert sent entry trigger as stop_price — auto-correct to a proper stop-loss above entry
            corrected = round(entry_price * (1 + max_stop_pct), 2)
            log_event(self.logger, "stop_auto_corrected", {"symbol": symbol, "side": side, "original_stop": stop_price, "corrected_stop": corrected, "reason": "alert_stop_was_entry_trigger"})
            stop_price = corrected
        if abs(entry_price - stop_price) / max(entry_price, 1e-9) > max_stop_pct:
            return WebhookDecision("rejected", "stop_distance_exceeds_guardrail", symbol=symbol, side=side, play=play)

        # ── Trifecta multi-timeframe confluency gate ──
        tf = str(metadata.get("timeframe", ""))
        trifecta_rejection = check_trifecta(
            symbol, tf, side,
            config=self.config.get("velez_strategy", self.config.get("strategy", {})),
            log=self.logger,
        )
        if trifecta_rejection is not None:
            return WebhookDecision("rejected", trifecta_rejection, symbol=symbol, side=side, play=play)

        # ── Lower-timeframe signal quality gates (2m/5m only) ──
        tf = str(metadata.get("timeframe", ""))
        tf_rejection = self._validate_lower_timeframe_signal(symbol, tf, side, metadata)
        if tf_rejection is not None:
            return tf_rejection

        if self.webhook_config.get("paper_only", True) and "paper-api.alpaca.markets" not in self.broker.config.base_url:
            return WebhookDecision("rejected", "non_paper_alpaca_endpoint_blocked", symbol=symbol, side=side, play=play)

        account = {}
        raw_positions: List[dict] = []
        raw_orders: List[dict] = []
        positions_count = 0
        if dry_run:
            account = {"equity": self.config.get("portfolio", {}).get("initial_cash", 100000)}
        elif self._execute_orders():
            try:
                account = self.broker.get_account()
                raw_positions = self.broker.get_positions_raw()
                raw_orders = self.broker.get_orders_raw(status="open", limit=100, direction="desc", nested=True)
                positions_count = self._active_exposure_count(raw_positions, raw_orders)
            except Exception as exc:
                return WebhookDecision("error", f"broker_account_check_failed:{exc}", symbol=symbol, side=side, play=play)
        else:
            account = {"equity": self.config.get("portfolio", {}).get("initial_cash", 100000)}

        equity = self._float(account.get("equity") or account.get("portfolio_value")) or self.config.get("portfolio", {}).get("initial_cash", 100000)
        limits = self.risk.check_limits(equity=equity, open_positions=positions_count)
        if not limits.allowed:
            return WebhookDecision("rejected", limits.reason, symbol=symbol, side=side, play=play)

        # #5: Correlation check — reject or warn on sector concentration
        corr_check = self._check_correlation(symbol, raw_positions)
        if not corr_check.get("ok"):
            return WebhookDecision("rejected", f"correlation:{corr_check.get('reason')}", symbol=symbol, side=side, play=play)

        max_risk_budget = self._risk_budget(equity)
        max_dollar_risk = max_risk_budget
        sym_cfg = self.symbol_config.get(symbol, {}) or self.journal.get_watchlist_symbol(symbol) or {}
        scale_add = str(metadata.get("scale_action") or "").lower() == "add_to_winner"
        scale_metadata: dict = {}
        lot_plan: dict = {}
        if scale_add:
            if not self._execute_orders():
                return WebhookDecision("rejected", "scale_add_requires_live_position_snapshot", symbol=symbol, side=side, play=play)
            add_result = self._scale_add_quantity(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                stop_price=stop_price,
                raw_positions=raw_positions,
                add_fraction=float(metadata.get("add_fraction") or self.risk_config.get("pyramid_add_fraction", 0.5) or 0.5),
            )
            if not add_result.get("ok"):
                return WebhookDecision("rejected", str(add_result.get("reason")), symbol=symbol, side=side, play=play)
            qty = int(add_result["qty"])
            scale_metadata = add_result
            lot_plan = {
                "enabled": True,
                "lots": "pyramid_add",
                "label": "50% add to winner",
                "risk_fraction": None,
                "effective_risk_budget": None,
                "max_risk_budget": round(float(max_risk_budget or 0.0), 2),
                "factors": ["mandatory_color_change_add", "50_percent_current_position"],
                "caps": [],
            }
        else:
            lot_plan = build_lot_plan(
                play=play,
                metadata=metadata,
                entry_price=entry_price,
                stop_price=stop_price,
                max_risk_budget=max_risk_budget,
                max_stop_pct=float(max_stop_pct or 0.0),
                config=self.risk_config.get("lot_sizing"),
            )
            max_dollar_risk = float(lot_plan.get("effective_risk_budget") or 0.0)
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
                "max_risk_budget": max_risk_budget,
                "lot_plan": lot_plan,
                "alert_id": alert_id,
                "source_metadata": metadata,
                "scale_add": scale_metadata if scale_add else None,
            },
        )

        if dry_run:
            decision.status = "diagnostic"
            decision.reason = "webhook_test_dry_run_no_order"
            decision.metadata["dry_run"] = True
            log_event(self.logger, "webhook_test_dry_run", decision.__dict__)
            return decision

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
        # P2: Post-entry stop verification — ensure bracket stop is actually attached
        if stop_price and isinstance(response, dict):
            response_stop = self._float(response.get("stop_loss", {}).get("stop_price") if isinstance(response.get("stop_loss"), dict) else response.get("stop_price"))
            has_stop_leg = response_stop is not None
            if not has_stop_leg:
                # Check legs for a stop order
                legs = response.get("legs", []) if isinstance(response.get("legs"), list) else []
                for leg in legs:
                    if str(leg.get("type") or "").lower() in {"stop", "stop_limit", "trailing_stop"}:
                        has_stop_leg = True
                        break
            if not has_stop_leg:
                # Submit standalone stop to protect the position
                stop_side = "sell" if side == "buy" else "buy"
                stop_payload = {
                    "symbol": symbol,
                    "qty": str(qty),
                    "side": stop_side,
                    "type": "stop",
                    "time_in_force": self.webhook_config.get("time_in_force", "day"),
                    "stop_price": f"{stop_price:.2f}",
                    "client_order_id": f"velez-verify-stop-{symbol.lower()}-{secrets.token_hex(6)}",
                }
                try:
                    self.broker.submit_order_payload(stop_payload)
                    log_event(self.logger, "stop_verification_repair", {"symbol": symbol, "stop_price": stop_price, "reason": "bracket_stop_missing_from_response"})
                except Exception as stop_exc:
                    log_event(self.logger, "stop_verification_failed", {"symbol": symbol, "error": str(stop_exc)})
        # P3: Auto-claim lifecycle position so journal link never rots
        decision_dict = {
            "alert_ref": alert_id,
            "symbol": symbol,
            "side": side,
            "play": play,
            "status": "submitted",
            "entry_price": entry_price,
            "stop_price": stop_price,
            "qty": qty,
        }
        self._set_lifecycle_claim(symbol, decision_dict)
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
        }
        for key in (
            "arena_model",
            "scale_action",
            "position_intent",
            "requires_existing_winner",
            "mandatory_add",
            "color_change_direction",
            "management_plan",
            "setup_family",
            "play_variant",
            "prior_close",
            "gap_direction",
            "gap_pct",
            "gap_fill_price",
            "first_open",
            "first_high",
            "first_low",
            "first_close",
            "opening_bars_seen",
            "minutes_since_open",
            "time_space_score",
            "time_score",
            "space_score",
            "clean_space",
            "clean_space_pct",
            "gap_fill_space_pct",
            "obstacle_price",
            "prior_structure_high",
            "prior_structure_low",
            "body_mult",
            "event_candle_body_mult",
            "body_range_pct",
            "upper_wick_pct",
            "lower_wick_pct",
            "tail_pct",
            "event_tail_pct",
            "recovery_pct",
            "body_recovery_pct",
            "sizing_lots",
            "lot_override",
            "power_candle",
            "sizing_grade",
            "chased",
        ):
            if key in payload:
                metadata[key] = payload[key]
        if "add_fraction" in payload:
            metadata["add_fraction"] = self._float(payload.get("add_fraction"))
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
        runtime_override = self.journal.get_setting("require_order_approval", None)
        if runtime_override is not None:
            return bool(runtime_override)
        configured = self.webhook_config.get("require_order_approval")
        if configured is not None:
            return bool(configured)
        return os.getenv("VELEZ_REQUIRE_ORDER_APPROVAL", "false").strip().lower() in {"1", "true", "yes", "on"}

    def _approval_mode_source(self) -> str:
        runtime_override = self.journal.get_setting("require_order_approval", None)
        if runtime_override is not None:
            return "runtime_dashboard"
        if self.webhook_config.get("require_order_approval") is not None:
            return "config"
        return "environment"

    def _scale_add_quantity(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        stop_price: float,
        raw_positions: List[dict],
        add_fraction: float,
    ) -> dict:
        position = self._matching_raw_position(raw_positions, symbol)
        if not position:
            return {"ok": False, "reason": "scale_add_requires_existing_position"}

        current_qty = self._position_signed_qty(position)
        if current_qty == 0:
            return {"ok": False, "reason": "scale_add_position_size_zero"}

        long_add = side == "buy"
        if long_add and current_qty <= 0:
            return {"ok": False, "reason": "scale_add_side_mismatch"}
        if not long_add and current_qty >= 0:
            return {"ok": False, "reason": "scale_add_side_mismatch"}

        avg_entry = self._float(position.get("avg_entry_price"))
        if avg_entry is None:
            return {"ok": False, "reason": "scale_add_missing_avg_entry"}

        profitable = entry_price > avg_entry if long_add else entry_price < avg_entry
        if not profitable:
            return {"ok": False, "reason": "scale_add_position_not_profitable"}

        risk_mitigated = stop_price >= avg_entry if long_add else stop_price <= avg_entry
        if not risk_mitigated:
            return {"ok": False, "reason": "scale_add_initial_risk_not_mitigated"}

        add_qty = int(abs(current_qty) * max(add_fraction, 0.0))
        if add_qty <= 0:
            add_qty = calculate_pyramid_add_qty(abs(current_qty))
        add_qty = min(add_qty, int(self.risk_config.get("max_order_qty", 10000)))
        if add_qty <= 0:
            return {"ok": False, "reason": "scale_add_qty_zero"}
        return {
            "ok": True,
            "qty": add_qty,
            "current_qty": current_qty,
            "avg_entry_price": avg_entry,
            "add_fraction": add_fraction,
            "reason": "mandatory_color_change_add_to_winner",
        }

    def _matching_raw_position(self, raw_positions: List[dict], symbol: str) -> Optional[dict]:
        wanted = str(symbol or "").upper()
        for item in raw_positions:
            if str(item.get("symbol") or "").upper() == wanted:
                return item
        return None

    def _active_exposure_count(self, raw_positions: List[dict], raw_orders: List[dict]) -> int:
        position_symbols = {
            str(item.get("symbol") or "").upper().strip()
            for item in raw_positions
            if str(item.get("symbol") or "").strip()
        }
        order_symbols = {
            str(item.get("symbol") or "").upper().strip()
            for item in raw_orders
            if str(item.get("symbol") or "").strip()
        }
        pending_symbols = {
            str(item.get("symbol") or "").upper().strip()
            for item in self.journal.pending_orders()
            if str(item.get("symbol") or "").strip()
        }
        return len(position_symbols | order_symbols | pending_symbols)

    def _position_signed_qty(self, item: dict) -> int:
        qty = int(float(item.get("qty") or 0))
        if str(item.get("side") or "").lower() == "short":
            qty = -abs(qty)
        return qty

    def _remember_decisions(self, decisions: List[WebhookDecision], alert_id: str) -> None:
        for decision in decisions:
            snapshot = self._decision_snapshot(decision, alert_id)
            self.recent_decisions.appendleft(snapshot)
            try:
                self.journal.record_decision(snapshot, decision.order_payload, decision.broker_response)
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
        snapshot = {
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
            "max_risk_budget": metadata.get("max_risk_budget"),
            "lot_plan": metadata.get("lot_plan"),
            "payload_version": source.get("payload_version") or source.get("pine_version") or source.get("script_version") or source.get("version"),
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
        snapshot["confidence_receipt"] = self._confidence_receipt(decision, snapshot, order_payload, metadata)
        return snapshot

    def _empty_lifecycle_payload(self, note: str) -> dict:
        return {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "open_positions": 0,
                "open_orders": 0,
                "recent_fills": 0,
                "guardrails": 0,
                "management_actions": 0,
                "unrealized_pl": 0,
                "open_risk": 0,
                "average_r_multiple": None,
            },
            "positions": [],
            "open_orders": [],
            "recent_fills": [],
            "guardrails": [],
            "outcomes": [],
            "errors": {},
            "readback": "No active positions are reconciled yet.",
            "note": note,
        }

    def _light_lifecycle_payload(self, payload: dict) -> dict:
        return {
            **payload,
            "recent_fills": [],
            "open_orders": payload.get("open_orders", [])[:20],
            "positions": payload.get("positions", [])[:20],
            "guardrails": payload.get("guardrails", [])[:20],
            "outcomes": payload.get("outcomes", [])[:12],
        }

    def _raw_positions_for_lifecycle(self) -> tuple[List[dict], Optional[str]]:
        if not self.broker.is_configured():
            return [], None
        try:
            data = self.broker.get_positions_raw()
        except Exception as exc:
            return [], str(exc)
        return data if isinstance(data, list) else [], None

    def _raw_orders_for_lifecycle(self) -> tuple[List[dict], Optional[str]]:
        if not self.broker.is_configured():
            return [], None
        if not hasattr(self.broker, "get_orders_raw"):
            return [], "broker_order_snapshot_not_supported"
        try:
            limit = self._int_env("VELEZ_LIFECYCLE_ORDER_LIMIT", 100, minimum=10, maximum=500)
            data = self.broker.get_orders_raw(status="open", limit=limit, direction="desc", nested=True)
        except Exception as exc:
            return [], str(exc)
        return data if isinstance(data, list) else [], None

    def _raw_fills_for_lifecycle(self) -> tuple[List[dict], Optional[str]]:
        if not self.broker.is_configured():
            return [], None
        if not hasattr(self.broker, "get_activities_raw"):
            return [], "broker_fill_snapshot_not_supported"
        try:
            days = self._int_env("VELEZ_LIFECYCLE_FILL_LOOKBACK_DAYS", 7, minimum=1, maximum=30)
            after = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
            data = self.broker.get_activities_raw(activity_types="FILL", after=after, direction="desc", page_size=100)
        except Exception as exc:
            return [], str(exc)
        return data if isinstance(data, list) else [], None

    def _position_lifecycle(self, item: dict, *, decisions: List[dict], orders: List[dict], fills: List[dict]) -> dict:
        symbol = str(item.get("symbol") or "").upper().strip()
        signed_qty = self._position_signed_qty(item)
        qty_abs = abs(signed_qty)
        side = str(item.get("side") or ("short" if signed_qty < 0 else "long")).lower()
        if side not in {"long", "short"}:
            side = "short" if signed_qty < 0 else "long"
        direction = 1 if side == "long" else -1
        linked = self._link_decision_for_symbol(symbol, decisions, side=side)
        symbol_orders = [order for order in orders if str(order.get("symbol") or "").upper() == symbol]
        broker_stop = self._stop_price_from_orders(symbol_orders)
        journal_stop = self._float(linked.get("stop_price")) if linked else None
        stop_price = broker_stop if broker_stop is not None else journal_stop
        stop_source = "broker_open_order" if broker_stop is not None else "journal_decision" if journal_stop is not None else "missing"

        entry_price = self._float(item.get("avg_entry_price")) or (self._float(linked.get("entry_price")) if linked else None)
        current_price = self._float(item.get("current_price"))
        market_value = self._float(item.get("market_value"))
        if current_price is None and market_value is not None and qty_abs:
            current_price = abs(market_value) / qty_abs
        unrealized_pl = self._float(item.get("unrealized_pl"))
        unrealized_plpc = self._float(item.get("unrealized_plpc"))
        risk_per_unit = abs(entry_price - stop_price) if entry_price is not None and stop_price is not None else None
        current_r = None
        if risk_per_unit and current_price is not None and entry_price is not None:
            current_r = ((current_price - entry_price) * direction) / risk_per_unit
        sym_cfg = self.symbol_config.get(symbol, {}) or self.journal.get_watchlist_symbol(symbol) or {}
        multiplier = self._float(sym_cfg.get("contract_multiplier")) or 1.0
        initial_risk = risk_per_unit * qty_abs * multiplier if risk_per_unit and qty_abs else None
        latest_fill = next((fill for fill in fills if str(fill.get("symbol") or "").upper() == symbol), None)
        management = self._position_management_actions(
            side=side,
            entry_price=entry_price,
            stop_price=stop_price,
            stop_source=stop_source,
            current_r=current_r,
            qty_abs=qty_abs,
        )
        return {
            "symbol": symbol,
            "qty": item.get("qty"),
            "signed_qty": signed_qty,
            "side": side,
            "avg_entry_price": self._round_or_none(entry_price),
            "current_price": self._round_or_none(current_price),
            "market_value": self._round_or_none(market_value),
            "unrealized_pl": self._round_or_none(unrealized_pl),
            "unrealized_plpc": unrealized_plpc,
            "entry_price": self._round_or_none(entry_price),
            "stop_price": self._round_or_none(stop_price),
            "stop_source": stop_source,
            "risk_per_unit": self._round_or_none(risk_per_unit),
            "initial_risk_dollars": self._round_or_none(initial_risk),
            "current_r_multiple": self._round_or_none(current_r),
            "linked_alert_ref": linked.get("alert_ref") if linked else None,
            "linked_setup": linked.get("play") or linked.get("setup") if linked else None,
            "linked_decision": self._public_lifecycle_decision(linked),
            "open_orders": symbol_orders,
            "latest_fill": latest_fill,
            "management": management,
            "next_action": self._next_management_action(management),
        }

    def _position_management_actions(
        self,
        *,
        side: str,
        entry_price: Optional[float],
        stop_price: Optional[float],
        stop_source: str,
        current_r: Optional[float],
        qty_abs: int,
    ) -> List[dict]:
        actions: List[dict] = []
        if stop_price is None:
            actions.append(
                {
                    "name": "Stop protection",
                    "status": "due",
                    "detail": "No broker or journal stop is linked to this open position.",
                }
            )
        elif stop_source == "journal_decision":
            actions.append(
                {
                    "name": "Broker stop check",
                    "status": "watch",
                    "detail": "A journal stop exists, but no matching open Alpaca stop order was seen.",
                }
            )
        if current_r is None:
            actions.append(
                {
                    "name": "R multiple",
                    "status": "watch",
                    "detail": "Entry, stop, or current price is missing, so management R cannot be computed yet.",
                }
            )
            return actions

        breakeven_due = False
        if entry_price is not None and stop_price is not None and current_r >= 1:
            breakeven_due = stop_price < entry_price if side == "long" else stop_price > entry_price
        if breakeven_due:
            actions.append(
                {
                    "name": "Breakeven stop review",
                    "status": "due",
                    "detail": "Trade is at or beyond 1R and the stop has not reached breakeven.",
                }
            )
        if current_r >= 1:
            actions.append(
                {
                    "name": "50% partial review",
                    "status": "watch",
                    "detail": f"Position is {current_r:.2f}R; review the planned partial-profit lane before adding risk.",
                }
            )
        if current_r >= 2:
            actions.append(
                {
                    "name": "Trail winner",
                    "status": "watch",
                    "detail": "Position is beyond 2R; monitor for Velez pullback or pivot trail logic.",
                }
            )
        if current_r < 0:
            actions.append(
                {
                    "name": "Drawdown watch",
                    "status": "watch",
                    "detail": f"Position is {current_r:.2f}R against entry; do not add unless the winner rules are satisfied.",
                }
            )
        if not actions:
            actions.append(
                {
                    "name": "Hold plan",
                    "status": "ok",
                    "detail": f"{qty_abs} units are active at {current_r:.2f}R; no lifecycle rule is due right now.",
                }
            )
        return actions

    def _breakeven_stop_due(self, position: dict) -> bool:
        current_r = self._float(position.get("current_r_multiple"))
        entry_price = self._float(position.get("entry_price"))
        stop_price = self._float(position.get("stop_price"))
        if current_r is None or current_r < 1 or entry_price is None or stop_price is None:
            return False
        side = str(position.get("side") or "").lower()
        return stop_price < entry_price if side == "long" else stop_price > entry_price

    def _partial_plan_for_position(self, position: dict) -> dict:
        qty_value = self._position_qty_number(position)
        current_r = self._float(position.get("current_r_multiple"))
        symbol = position.get("symbol")
        options = []
        for pct in (0.25, 0.5, 1.0):
            exit_qty = round(qty_value * pct, 8) if qty_value else 0
            if qty_value >= 1:
                exit_qty = max(1, int(exit_qty))
            options.append({"label": f"{int(pct * 100)}%", "fraction": pct, "qty": min(exit_qty, qty_value) if qty_value else 0})
        if current_r is None:
            recommendation = "hold"
            reason = "R multiple is unavailable, so no partial is suggested."
        elif current_r >= 2:
            recommendation = "50% or trail"
            reason = "Position is at or beyond 2R; review a larger partial or trailing plan."
        elif current_r >= 1:
            recommendation = "25%-50%"
            reason = "Position is at or beyond 1R; review first partial and breakeven stop."
        elif current_r <= -0.5:
            recommendation = "reduce risk"
            reason = "Position is in drawdown; consider reducing or holding only if the setup remains valid."
        else:
            recommendation = "hold"
            reason = "No partial threshold is due yet."
        return {
            "symbol": symbol,
            "side": position.get("side"),
            "qty": self._format_qty(qty_value),
            "current_r_multiple": self._round_or_none(current_r),
            "unrealized_pl": position.get("unrealized_pl"),
            "recommendation": recommendation,
            "reason": reason,
            "options": options,
            "guardrail": "Planner only. No exit order is submitted.",
        }

    def _exposure_reduction_plan(self, lifecycle: dict) -> dict:
        positions = lifecycle.get("positions", []) or []
        suggestions = []
        for position in positions:
            qty_value = self._position_qty_number(position)
            if not qty_value:
                continue
            r_multiple = self._float(position.get("current_r_multiple"))
            if r_multiple is None:
                recommendation = "25% review"
                reason = "R is unavailable; use the smallest reduction first if exposure must be freed."
                rank = 3
            elif r_multiple < 0:
                recommendation = "50%-100% review"
                reason = "Position is below entry in R terms; reducing losers frees risk first."
                rank = 0
            elif r_multiple >= 1:
                recommendation = "25%-50% partial"
                reason = "Position is profitable; trim without fully removing a working trade."
                rank = 1
            else:
                recommendation = "25% trim"
                reason = "Position is not at a major profit target; smallest trim frees one exposure lane."
                rank = 2
            options = []
            for fraction in (0.25, 0.5, 1.0):
                qty = qty_value if abs(fraction - 1.0) < 1e-9 else qty_value * fraction
                if qty_value >= 1:
                    qty = max(1, int(qty))
                options.append({"label": f"{int(fraction * 100)}%", "fraction": fraction, "qty": self._format_qty(min(qty, qty_value))})
            suggestions.append({
                "symbol": position.get("symbol"),
                "side": position.get("side"),
                "qty": self._position_qty_string(position),
                "current_r_multiple": self._round_or_none(r_multiple),
                "unrealized_pl": position.get("unrealized_pl"),
                "recommendation": recommendation,
                "reason": reason,
                "rank": rank,
                "options": options,
            })
        suggestions.sort(key=lambda item: (item.get("rank", 9), str(item.get("symbol") or "")))
        return {
            "suggestions": suggestions,
            "readback": "; ".join(f"{item['symbol']}: {item['recommendation']}" for item in suggestions[:3]) if suggestions else "No exposure reduction suggestions are available.",
        }

    def _lifecycle_needs_action_summary(self, positions: List[dict], guardrails: List[dict]) -> dict:
        items = []
        for guardrail in guardrails:
            severity = guardrail.get("severity") or "warn"
            items.append({
                "symbol": guardrail.get("symbol") or "desk",
                "action": guardrail.get("name"),
                "severity": severity,
                "detail": guardrail.get("detail"),
            })
        for position in positions:
            symbol = position.get("symbol")
            if self._breakeven_stop_due(position):
                items.append({
                    "symbol": symbol,
                    "action": "move_stop_to_breakeven",
                    "severity": "due",
                    "detail": "Position is at or beyond 1R and stop is not at breakeven.",
                })
            plan = self._partial_plan_for_position(position)
            if plan["recommendation"] != "hold":
                items.append({
                    "symbol": symbol,
                    "action": "partial_plan_review",
                    "severity": "watch",
                    "detail": plan["reason"],
                })
        priority = {"critical": 0, "due": 1, "warn": 2, "watch": 3, "info": 4}
        items.sort(key=lambda item: priority.get(str(item.get("severity")), 5))
        return {
            "count": len(items),
            "items": items[:12],
            "readback": "; ".join(f"{item['symbol']}: {item['action']}" for item in items[:4]) if items else "No lifecycle action is due.",
        }

    def _position_doctor_card(self, position: dict) -> dict:
        linked = position.get("linked_decision") or {}
        stop_source = position.get("stop_source") or "unknown"
        has_broker_stop = stop_source == "broker_open_order"
        can_repair_stop = stop_source == "journal_decision" and position.get("stop_price") is not None
        claim_candidates = []
        if not position.get("linked_alert_ref"):
            claim_candidates = [
                self._public_lifecycle_decision(item)
                for item in self._claim_candidates_for_symbol(
                    str(position.get("symbol") or ""),
                    self.journal.decision_entries(limit=500),
                    side=str(position.get("side") or ""),
                )[:3]
            ]
        actions = []
        if not position.get("linked_alert_ref"):
            actions.append({"name": "claim_position", "status": "available" if claim_candidates else "blocked", "detail": "Attach this broker position to a journal decision."})
        if has_broker_stop:
            actions.append({"name": "stop_check", "status": "ok", "detail": "Broker stop is linked."})
        elif can_repair_stop:
            actions.append({"name": "repair_stop", "status": "available", "detail": "Submit a broker stop from the linked journal stop."})
        else:
            actions.append({"name": "repair_stop", "status": "blocked", "detail": "No journal stop is available for a guarded repair."})
        return {
            "symbol": position.get("symbol"),
            "side": position.get("side"),
            "qty": self._position_qty_string(position),
            "entry_price": position.get("entry_price"),
            "current_price": position.get("current_price"),
            "stop_price": position.get("stop_price"),
            "stop_source": stop_source,
            "current_r_multiple": position.get("current_r_multiple"),
            "unrealized_pl": position.get("unrealized_pl"),
            "linked_alert_ref": position.get("linked_alert_ref"),
            "linked_setup": position.get("linked_setup"),
            "linked_decision": linked,
            "claim_candidates": [item for item in claim_candidates if item],
            "reduction_options": self._reduction_options_for_position(position),
            "actions": actions,
            "next_action": position.get("next_action"),
        }

    def _reduction_options_for_position(self, position: dict) -> List[dict]:
        qty_value = self._position_qty_number(position)
        if not qty_value:
            return []
        options = []
        for fraction in (0.25, 0.5, 1.0):
            qty = qty_value if abs(fraction - 1.0) < 1e-9 else qty_value * fraction
            if qty_value >= 1:
                qty = max(1, int(qty))
            options.append({"label": f"{int(fraction * 100)}%", "fraction": fraction, "qty": self._format_qty(min(qty, qty_value))})
        return options

    def _position_qty_number(self, position: dict) -> float:
        raw = position.get("qty")
        if raw in (None, ""):
            raw = position.get("signed_qty")
        value = self._float(raw)
        return abs(value or 0.0)

    def _position_qty_string(self, position: dict) -> str:
        return self._format_qty(self._position_qty_number(position))

    def _format_qty(self, value: float) -> str:
        if not value:
            return ""
        if abs(value - int(value)) < 1e-9:
            return str(int(value))
        return f"{value:.8f}".rstrip("0").rstrip(".")

    def _cancel_symbol_stop_orders(self, position: dict) -> List[str]:
        canceled = []
        for order in position.get("open_orders", []) or []:
            if str(order.get("type") or "").lower() not in {"stop", "stop_limit", "trailing_stop"}:
                continue
            order_id = str(order.get("id") or "")
            if not order_id or not hasattr(self.broker, "cancel_order"):
                continue
            self.broker.cancel_order(order_id)
            canceled.append(order_id)
        return canceled

    def _lifecycle_claims(self) -> dict:
        claims = self.journal.get_setting("lifecycle.position_claims", {}) or {}
        return claims if isinstance(claims, dict) else {}

    def _set_lifecycle_claim(self, symbol: str, decision: dict) -> dict:
        cleaned_symbol = str(symbol or decision.get("symbol") or "").upper().strip()
        claim = {
            "symbol": cleaned_symbol,
            "alert_ref": decision.get("alert_ref"),
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        }
        claims = self._lifecycle_claims()
        claims[cleaned_symbol] = claim
        self.journal.set_setting("lifecycle.position_claims", claims)
        return claim

    def _claim_candidates_for_symbol(self, symbol: str, decisions: List[dict], *, side: str = "") -> List[dict]:
        wanted = str(symbol or "").upper().strip()
        if not wanted:
            return []
        candidates = [
            item for item in decisions
            if str(item.get("symbol") or "").upper().strip() == wanted
            and str(item.get("status") or "").lower() in {"submitted", "proposed", "diagnostic"}
        ]
        side = str(side or "").lower()
        wanted_side = {"long": "buy", "short": "sell"}.get(side)
        if wanted_side:
            side_matches = [item for item in candidates if str(item.get("side") or "").lower() == wanted_side]
            if side_matches:
                candidates = side_matches
        return candidates

    def _auto_lifecycle_actions(
        self,
        *,
        positions: List[dict],
        open_orders: List[dict],
        guardrails: List[dict],
    ) -> List[dict]:
        """Auto-execute lifecycle fixes: repair missing stops, move to breakeven, enforce time stops, force-close on max positions."""
        results: List[dict] = []
        auto_execute = os.getenv("VELEZ_LIFECYCLE_AUTO_EXECUTE", "true").strip().lower() in {"1", "true", "yes", "on"}
        if not auto_execute:
            return results

        # P4: Force-close oldest position when max_positions exceeded
        max_positions = int(self.risk_config.get("max_open_positions") or 5)
        if max_positions > 0 and len(positions) > max_positions:
            excess = len(positions) - max_positions
            # Sort by timestamp (oldest first) using linked_decision or lifecycle data
            sorted_positions = sorted(
                positions,
                key=lambda p: str(p.get("linked_decision", {}).get("timestamp") or p.get("linked_alert_ref") or "z"),
            )
            for pos in sorted_positions[:excess]:
                sym = str(pos.get("symbol") or "")
                qty = self._position_qty_string(pos)
                if not qty or not sym:
                    continue
                # Only force-close if no open orders pending for this symbol
                has_open_order = any(
                    str(o.get("symbol") or "").upper() == sym and str(o.get("status") or "").lower() not in {"filled", "canceled", "expired", "rejected"}
                    for o in open_orders
                )
                if has_open_order:
                    continue
                exit_side = "sell" if str(pos.get("side") or "") == "long" else "buy"
                exit_payload = {
                    "symbol": sym,
                    "qty": qty,
                    "side": exit_side,
                    "type": "market",
                    "time_in_force": self.webhook_config.get("time_in_force", "day"),
                    "client_order_id": f"velez-force-close-{sym.lower()}-{secrets.token_hex(6)}",
                }
                try:
                    self.broker.submit_order_payload(exit_payload)
                    results.append({"action": "force_close_max_positions", "symbol": sym, "status": "submitted"})
                    log_event(self.logger, "auto_force_close", {"symbol": sym, "reason": "max_positions_exceeded"})
                except Exception as exc:
                    results.append({"action": "force_close_max_positions", "symbol": sym, "status": "failed", "error": str(exc)})

        # #1: Pre-close flatten — exit all positions 15 min before market close
        flatten_cfg = self.config.get("strategy", {}).get("exits", {}).get("auto_flatten", {})
        if flatten_cfg.get("enabled", True) and len(positions) > 0:
            try:
                from datetime import datetime, timezone, timedelta
                now_et = datetime.now(timezone.utc) - timedelta(hours=4)  # UTC to ET rough
                minutes_before = int(flatten_cfg.get("minutes_before_close", 15))
                # Market closes at 16:00 ET — flatten at 15:45 ET (19:45 UTC)
                close_hour, close_min = 15, 60 - minutes_before  # 15:45
                if now_et.hour == close_hour and now_et.minute >= close_min:
                    for pos in positions:
                        sym = str(pos.get("symbol") or "")
                        qty_str = self._position_qty_string(pos)
                        if not qty_str or not sym:
                            continue
                        has_pending = any(
                            str(o.get("symbol") or "").upper() == sym and str(o.get("status") or "").lower() not in {"filled", "canceled", "expired", "rejected"}
                            for o in open_orders
                        )
                        if has_pending:
                            continue
                        exit_side = "sell" if str(pos.get("side") or "") == "long" else "buy"
                        flatten_payload = {
                            "symbol": sym, "qty": qty_str,
                            "side": exit_side, "type": "market",
                            "time_in_force": self.webhook_config.get("time_in_force", "day"),
                            "client_order_id": f"velez-flatten-{sym.lower()}-{secrets.token_hex(6)}",
                        }
                        try:
                            self.broker.submit_order_payload(flatten_payload)
                            results.append({"action": "pre_close_flatten", "symbol": sym, "status": "submitted"})
                            log_event(self.logger, "auto_flatten_close", {"symbol": sym, "reason": "pre_close_protection"})
                        except Exception as exc:
                            results.append({"action": "pre_close_flatten", "symbol": sym, "status": "failed", "error": str(exc)})
            except Exception:
                pass

        for position in positions:
            symbol = str(position.get("symbol") or "")
            if not symbol:
                continue
            stop_source = str(position.get("stop_source") or "")
            entry_price = self._float(position.get("entry_price"))
            stop_price = self._float(position.get("stop_price"))
            current_r = self._float(position.get("current_r_multiple"))
            side = str(position.get("side") or "")
            qty = self._position_qty_string(position)

            # P1: Auto-repair missing stops — also covers journal_decision when broker stop vanished (e.g. partial fills cancel bracket)
            if stop_source in ("missing", "journal_decision") and entry_price is not None and qty:
                linked = position.get("linked_decision") or {}
                emergency_stop = self._float(linked.get("stop_price")) or stop_price
                if emergency_stop is None and entry_price:
                    # Fallback: compute emergency stop at 5% from entry
                    emergency_stop = round(entry_price * 0.95, 2) if side == "long" else round(entry_price * 1.05, 2)
                if emergency_stop is not None:
                    exit_side = "sell" if side == "long" else "buy"
                    stop_payload = {
                        "symbol": symbol,
                        "qty": qty,
                        "side": exit_side,
                        "type": "stop",
                        "time_in_force": self.webhook_config.get("time_in_force", "day"),
                        "stop_price": f"{emergency_stop:.2f}",
                        "client_order_id": f"velez-emergency-stop-{symbol.lower()}-{secrets.token_hex(6)}",
                    }
                    try:
                        self.broker.submit_order_payload(stop_payload)
                        results.append({"action": "emergency_stop_repair", "symbol": symbol, "stop_price": emergency_stop, "status": "submitted"})
                        log_event(self.logger, "auto_emergency_stop", {"symbol": symbol, "stop_price": emergency_stop})
                    except Exception as exc:
                        results.append({"action": "emergency_stop_repair", "symbol": symbol, "status": "failed", "error": str(exc)})

            # V1: Auto-move stop to breakeven at >= 1R
            if current_r is not None and current_r >= 1.0 and entry_price is not None and qty:
                breakeven_due = False
                if side == "long" and stop_price is not None and stop_price < entry_price:
                    breakeven_due = True
                elif side == "short" and stop_price is not None and stop_price > entry_price:
                    breakeven_due = True
                if breakeven_due:
                    # Cancel existing stop orders and submit new breakeven stop
                    self._cancel_symbol_stop_orders(position)
                    exit_side = "sell" if side == "long" else "buy"
                    be_payload = {
                        "symbol": symbol,
                        "qty": qty,
                        "side": exit_side,
                        "type": "stop",
                        "time_in_force": self.webhook_config.get("time_in_force", "day"),
                        "stop_price": f"{entry_price:.2f}",
                        "client_order_id": f"velez-be-stop-{symbol.lower()}-{secrets.token_hex(6)}",
                    }
                    try:
                        self.broker.submit_order_payload(be_payload)
                        results.append({"action": "breakeven_stop_move", "symbol": symbol, "entry_price": entry_price, "status": "submitted"})
                        log_event(self.logger, "auto_breakeven_stop", {"symbol": symbol, "current_r": current_r, "stop_moved_to": entry_price})
                    except Exception as exc:
                        results.append({"action": "breakeven_stop_move", "symbol": symbol, "status": "failed", "error": str(exc)})

            # #2: Auto-execute partial profit-taking at 1R and 2R
            partials_cfg = self.config.get("strategy", {}).get("exits", {}).get("partials_auto_execute", {})
            if partials_cfg.get("enabled", True) and current_r is not None and qty:
                partials_taken = self._partials_taken_for_symbol(symbol)
                if current_r >= float(partials_cfg.get("first_r", 1.0)) and "first" not in partials_taken and current_r < float(partials_cfg.get("second_r", 2.0)):
                    first_pct = float(partials_cfg.get("first_pct", 0.5))
                    exit_qty = max(1, int(self._position_qty_number(position) * first_pct))
                    if exit_qty > 0:
                        exit_side = "sell" if side == "long" else "buy"
                        partial_payload = {
                            "symbol": symbol, "qty": self._format_qty(exit_qty),
                            "side": exit_side, "type": "market",
                            "time_in_force": self.webhook_config.get("time_in_force", "day"),
                            "client_order_id": f"velez-partial-1r-{symbol.lower()}-{secrets.token_hex(6)}",
                        }
                        try:
                            self.broker.submit_order_payload(partial_payload)
                            self._record_partial_taken(symbol, "first")
                            results.append({"action": "partial_first_r", "symbol": symbol, "pct": first_pct, "status": "submitted"})
                            log_event(self.logger, "auto_partial_1r", {"symbol": symbol, "current_r": current_r, "exit_pct": first_pct})
                        except Exception as exc:
                            results.append({"action": "partial_first_r", "symbol": symbol, "status": "failed", "error": str(exc)})
                elif current_r >= float(partials_cfg.get("second_r", 2.0)) and "second" not in partials_taken:
                    second_pct = float(partials_cfg.get("second_pct", 0.25))
                    exit_qty = max(1, int(self._position_qty_number(position) * second_pct))
                    if exit_qty > 0:
                        exit_side = "sell" if side == "long" else "buy"
                        partial_payload = {
                            "symbol": symbol, "qty": self._format_qty(exit_qty),
                            "side": exit_side, "type": "market",
                            "time_in_force": self.webhook_config.get("time_in_force", "day"),
                            "client_order_id": f"velez-partial-2r-{symbol.lower()}-{secrets.token_hex(6)}",
                        }
                        try:
                            self.broker.submit_order_payload(partial_payload)
                            self._record_partial_taken(symbol, "second")
                            results.append({"action": "partial_second_r", "symbol": symbol, "pct": second_pct, "status": "submitted"})
                            log_event(self.logger, "auto_partial_2r", {"symbol": symbol, "current_r": current_r, "exit_pct": second_pct})
                        except Exception as exc:
                            results.append({"action": "partial_second_r", "symbol": symbol, "status": "failed", "error": str(exc)})

            # V2: Auto-enforce time stop — exit if position stale
            management = position.get("management", [])
            has_hold_plan = any(a.get("name") == "Hold plan" and a.get("status") == "ok" for a in management)
            has_drawdown = any(a.get("name") == "Drawdown watch" for a in management)
            if has_hold_plan and current_r is not None and current_r < 0.5 and qty:
                # Position is alive but flat/stale — check if it's been open long enough to time-stop
                linked = position.get("linked_decision", {}) or {}
                linked_ts = linked.get("timestamp")
                if linked_ts:
                    try:
                        from datetime import datetime, timezone, timedelta
                        created = datetime.fromisoformat(str(linked_ts).replace("Z", "+00:00"))
                        age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
                        # Exit positions older than 5 days with minimal movement
                        if age_hours > 120 and current_r < 0.3:
                            exit_side = "sell" if side == "long" else "buy"
                            exit_payload = {
                                "symbol": symbol,
                                "qty": qty,
                                "side": exit_side,
                                "type": "market",
                                "time_in_force": self.webhook_config.get("time_in_force", "day"),
                                "client_order_id": f"velez-time-stop-{symbol.lower()}-{secrets.token_hex(6)}",
                            }
                            try:
                                self.broker.submit_order_payload(exit_payload)
                                results.append({"action": "time_stop_exit", "symbol": symbol, "age_hours": round(age_hours, 1), "status": "submitted"})
                                log_event(self.logger, "auto_time_stop_exit", {"symbol": symbol, "age_hours": age_hours, "current_r": current_r})
                            except Exception as exc:
                                results.append({"action": "time_stop_exit", "symbol": symbol, "status": "failed", "error": str(exc)})
                    except Exception:
                        pass

        return results

    def _partials_taken_for_symbol(self, symbol: str) -> set:
        taken_json = self.journal.get_setting(f"partials_taken.{symbol.upper()}", "[]")
        try:
            import json
            parts = json.loads(str(taken_json))
            return set(parts) if isinstance(parts, list) else set()
        except Exception:
            return set()

    def _record_partial_taken(self, symbol: str, level: str) -> None:
        taken = self._partials_taken_for_symbol(symbol)
        taken.add(level)
        import json
        self.journal.set_setting(f"partials_taken.{symbol.upper()}", json.dumps(sorted(taken)))

    def _sector_for_symbol(self, symbol: str) -> str:
        groups = self.config.get("strategy", {}).get("exits", {}).get("correlation", {}).get("sector_groups", {})
        if not isinstance(groups, dict):
            return ""
        sym_upper = symbol.upper().strip()
        for sector, symbols in groups.items():
            if sym_upper in [s.upper().strip() for s in symbols]:
                return sector
        return ""

    def _check_correlation(self, symbol: str, positions: List[dict]) -> dict:
        corr_cfg = self.config.get("strategy", {}).get("exits", {}).get("correlation", {})
        if not corr_cfg.get("enabled", True):
            return {"ok": True, "sector": "", "existing_count": 0}
        sector = self._sector_for_symbol(symbol)
        if not sector:
            return {"ok": True, "sector": "", "existing_count": 0}
        existing = 0
        for pos in positions:
            pos_sym = str(pos.get("symbol") or "").upper().strip()
            if pos_sym == symbol.upper().strip():
                continue
            if self._sector_for_symbol(pos_sym) == sector:
                existing += 1
        max_corr = int(corr_cfg.get("max_correlation", 0.7) * 10)
        if existing >= 2:
            return {"ok": False, "sector": sector, "existing_count": existing, "reason": f"{existing} existing positions in {sector} sector"}
        if existing >= 1:
            return {"ok": True, "sector": sector, "existing_count": existing, "warning": "reduce_size", "reason": f"1 existing position in {sector} sector — consider reducing size"}
        return {"ok": True, "sector": sector, "existing_count": 0}

    def _setup_performance_summary(self, days: int = 90) -> dict:
        outcomes = self.journal.latest_trade_outcomes(limit=500)
        by_setup: dict = {}
        for o in outcomes:
            setup = str(o.get("status") or "").split("_")[0] if "_" in str(o.get("status") or "") else "other"
            pnl = float(o.get("pnl") or 0)
            if setup not in by_setup:
                by_setup[setup] = {"trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0, "total_r": 0.0}
            by_setup[setup]["trades"] += 1
            by_setup[setup]["total_pnl"] += pnl
            by_setup[setup]["total_r"] += float(o.get("r_multiple") or 0)
            if pnl > 0:
                by_setup[setup]["wins"] += 1
            elif pnl < 0:
                by_setup[setup]["losses"] += 1
        result = {}
        for setup, stats in sorted(by_setup.items(), key=lambda x: x[1]["total_pnl"], reverse=True):
            trades = stats["trades"]
            result[setup] = {
                "trades": trades,
                "win_rate": round(stats["wins"] / max(trades, 1) * 100, 1),
                "total_pnl": round(stats["total_pnl"], 2),
                "avg_r": round(stats["total_r"] / max(trades, 1), 2),
                "wins": stats["wins"],
                "losses": stats["losses"],
                "grade": "elite" if stats["total_pnl"] > 1000 and stats["win_rate"] > 60 else "solid" if stats["total_pnl"] > 0 else "review",
            }
        return {"period_days": days, "setups": result, "total_pnl": round(sum(s["total_pnl"] for s in by_setup.values()), 2)}

    def _next_management_action(self, actions: List[dict]) -> str:
        for status in ("due", "watch", "ok"):
            action = next((item for item in actions if item.get("status") == status), None)
            if action:
                return f"{action.get('name')}: {action.get('detail')}"
        return "No active management rule is due."

    def _order_snapshot(self, item: dict) -> dict:
        legs = item.get("legs") if isinstance(item.get("legs"), list) else []
        stop_price = self._stop_price_from_order(item)
        take_profit_price = self._take_profit_price_from_order(item)
        return {
            "id": item.get("id"),
            "client_order_id": item.get("client_order_id"),
            "symbol": str(item.get("symbol") or "").upper().strip(),
            "side": item.get("side"),
            "type": item.get("type"),
            "order_class": item.get("order_class"),
            "status": item.get("status"),
            "qty": item.get("qty"),
            "filled_qty": item.get("filled_qty"),
            "limit_price": item.get("limit_price"),
            "stop_price": self._round_or_none(stop_price),
            "take_profit_price": self._round_or_none(take_profit_price),
            "has_stop": stop_price is not None,
            "legs_count": len(legs),
            "submitted_at": item.get("submitted_at") or item.get("created_at"),
        }

    def _fill_snapshot(self, item: dict) -> dict:
        return {
            "id": item.get("id"),
            "transaction_time": item.get("transaction_time"),
            "symbol": str(item.get("symbol") or "").upper().strip(),
            "side": item.get("side"),
            "qty": item.get("qty"),
            "price": item.get("price"),
            "order_id": item.get("order_id"),
            "order_status": item.get("order_status"),
            "activity_type": item.get("activity_type"),
        }

    def _link_decision_for_symbol(self, symbol: str, decisions: List[dict], *, side: str = "") -> Optional[dict]:
        wanted = str(symbol or "").upper().strip()
        if not wanted:
            return None
        claim = self._lifecycle_claims().get(wanted)
        if isinstance(claim, dict) and claim.get("alert_ref"):
            claimed = self.journal.decision_by_alert_ref(str(claim.get("alert_ref")))
            if claimed and str(claimed.get("symbol") or "").upper().strip() == wanted:
                return claimed
        candidates = [item for item in decisions if str(item.get("symbol") or "").upper().strip() == wanted]
        side = str(side or "").lower()
        side_values = {"long": "buy", "short": "sell"}
        wanted_side = side_values.get(side)
        if wanted_side:
            side_matches = [item for item in candidates if str(item.get("side") or "").lower() == wanted_side]
            if side_matches:
                candidates = side_matches
        for status in ("submitted", "proposed", "diagnostic"):
            match = next((item for item in candidates if str(item.get("status") or "").lower() == status), None)
            if match:
                return match
        return None

    def _public_lifecycle_decision(self, decision: Optional[dict]) -> Optional[dict]:
        if not decision:
            return None
        return {
            key: decision.get(key)
            for key in (
                "timestamp",
                "alert_ref",
                "status",
                "reason",
                "symbol",
                "side",
                "play",
                "qty",
                "entry_price",
                "stop_price",
                "take_profit_price",
                "timeframe",
                "location",
            )
            if decision.get(key) not in (None, "")
        }

    def _stop_price_from_orders(self, orders: List[dict]) -> Optional[float]:
        for order in orders:
            price = self._float(order.get("stop_price")) or self._stop_price_from_order(order)
            if price is not None:
                return price
        return None

    def _stop_price_from_order(self, order: dict) -> Optional[float]:
        for key in ("stop_price", "trail_price"):
            price = self._float(order.get(key))
            if price is not None:
                return price
        stop_loss = order.get("stop_loss") if isinstance(order.get("stop_loss"), dict) else {}
        price = self._float(stop_loss.get("stop_price") or stop_loss.get("limit_price"))
        if price is not None:
            return price
        if str(order.get("type") or "").lower() in {"stop", "stop_limit", "trailing_stop"}:
            price = self._float(order.get("limit_price"))
            if price is not None:
                return price
        for leg in order.get("legs", []) if isinstance(order.get("legs"), list) else []:
            price = self._stop_price_from_order(leg)
            if price is not None:
                return price
        return None

    def _take_profit_price_from_order(self, order: dict) -> Optional[float]:
        take_profit = order.get("take_profit") if isinstance(order.get("take_profit"), dict) else {}
        price = self._float(take_profit.get("limit_price"))
        if price is not None:
            return price
        if str(order.get("type") or "").lower() == "limit" and str(order.get("order_class") or "").lower() in {"bracket", "oto", "oco"}:
            return self._float(order.get("limit_price"))
        for leg in order.get("legs", []) if isinstance(order.get("legs"), list) else []:
            if str(leg.get("type") or "").lower() == "limit":
                price = self._float(leg.get("limit_price"))
                if price is not None:
                    return price
        return None

    def _lifecycle_guardrails(
        self,
        *,
        positions: List[dict],
        open_orders: List[dict],
        pending: List[dict],
        decisions: List[dict],
        errors: dict,
    ) -> List[dict]:
        guardrails: List[dict] = []
        for name, error in errors.items():
            if error:
                guardrails.append(
                    {
                        "name": f"{name}_snapshot_error",
                        "severity": "warn",
                        "status": "needs_check",
                        "detail": str(error)[:240],
                    }
                )
        max_positions = int(self.risk_config.get("max_open_positions") or 0)
        if max_positions and len(positions) > max_positions:
            guardrails.append(
                {
                    "name": "max_positions_exceeded",
                    "severity": "critical",
                    "status": "over_limit",
                    "detail": f"{len(positions)} positions are open; configured max is {max_positions}.",
                }
            )
        warn_missing_stop = os.getenv("VELEZ_LIFECYCLE_WARN_MISSING_STOP", "true").strip().lower() in {"1", "true", "yes", "on"}
        pending_symbols = {str(item.get("symbol") or "").upper().strip() for item in pending}
        decision_symbols = {str(item.get("symbol") or "").upper().strip() for item in decisions}
        position_symbols = {str(item.get("symbol") or "").upper().strip() for item in positions}
        for position in positions:
            symbol = position.get("symbol")
            if not position.get("linked_alert_ref"):
                guardrails.append(
                    {
                        "name": "orphan_position",
                        "severity": "warn",
                        "status": "journal_link_missing",
                        "symbol": symbol,
                        "detail": "Open Alpaca position has no matching recent Trading Bull journal decision.",
                    }
                )
            if warn_missing_stop and position.get("stop_source") == "missing":
                guardrails.append(
                    {
                        "name": "missing_stop",
                        "severity": "critical",
                        "status": "needs_protection",
                        "symbol": symbol,
                        "detail": "Open position has no broker stop or journal stop linked.",
                    }
                )
            elif warn_missing_stop and position.get("stop_source") == "journal_decision":
                guardrails.append(
                    {
                        "name": "journal_stop_only",
                        "severity": "warn",
                        "status": "broker_stop_not_seen",
                        "symbol": symbol,
                        "detail": "Structural stop exists in the journal, but no matching open Alpaca stop order was seen.",
                    }
                )
            if symbol in pending_symbols:
                guardrails.append(
                    {
                        "name": "pending_order_overlaps_position",
                        "severity": "warn",
                        "status": "review_before_submit",
                        "symbol": symbol,
                        "detail": "A staged approval exists while a live position is already open.",
                    }
                )
        for order in open_orders:
            symbol = str(order.get("symbol") or "").upper().strip()
            if symbol and symbol not in decision_symbols and symbol not in position_symbols:
                guardrails.append(
                    {
                        "name": "open_order_without_journal",
                        "severity": "warn",
                        "status": "journal_link_missing",
                        "symbol": symbol,
                        "detail": "Open Alpaca order was not linked to a recent journal decision or live position.",
                    }
                )
        return guardrails

    def _lifecycle_readback(self, positions: List[dict], guardrails: List[dict]) -> str:
        if not positions:
            base = "No active Alpaca paper positions are open"
        else:
            snippets = []
            for item in positions[:3]:
                r_label = "R unknown" if item.get("current_r_multiple") is None else f"{float(item.get('current_r_multiple')):.2f}R"
                stop = item.get("stop_price")
                stop_label = f"stop {stop}" if stop is not None else "stop missing"
                pnl = self._float(item.get("unrealized_pl")) or 0.0
                snippets.append(f"{item.get('symbol')} {item.get('side')} {item.get('signed_qty')} at {r_label}, {stop_label}, P/L ${pnl:,.2f}")
            base = "; ".join(snippets)
        if guardrails:
            critical = [item for item in guardrails if item.get("severity") == "critical"]
            return f"{base}. Guardrails: {len(guardrails)} alert(s), {len(critical)} critical."
        return f"{base}. No lifecycle guardrail alerts are active."

    def _notify_lifecycle_guardrails(self, payload: dict) -> None:
        guardrails = payload.get("guardrails") or []
        if not guardrails:
            return
        severity_rank = {"info": 0, "warn": 1, "critical": 2}
        minimum = os.getenv("VELEZ_NOTIFY_MIN_SEVERITY", "warn").strip().lower() or "warn"
        min_rank = severity_rank.get(minimum, 1)
        selected = [
            item for item in guardrails
            if severity_rank.get(str(item.get("severity") or "warn").lower(), 1) >= min_rank
        ]
        if not selected:
            return

        critical_count = sum(1 for item in selected if item.get("severity") == "critical")
        symbols = sorted({str(item.get("symbol") or "desk").upper() for item in selected})
        detail_lines = []
        for item in selected[:8]:
            symbol = str(item.get("symbol") or "desk").upper()
            detail_lines.append(
                f"{symbol}: {item.get('name', 'guardrail')} - {item.get('detail') or item.get('status') or 'Review required.'}"
            )
        if len(selected) > 8:
            detail_lines.append(f"+{len(selected) - 8} more guardrail(s)")

        title = f"Trading Bull lifecycle guardrails: {len(selected)} active, {critical_count} critical"
        detail = "\n".join(detail_lines)
        key = "lifecycle:" + "|".join(
            sorted(
                f"{item.get('name')}:{item.get('symbol') or 'desk'}:{item.get('status')}"
                for item in selected
            )
        )
        self._notify_event(
            key=key,
            title=title,
            detail=detail,
            severity="critical" if critical_count else "warn",
            payload={
                "kind": "lifecycle_guardrails",
                "timestamp": payload.get("timestamp"),
                "summary": payload.get("summary", {}),
                "symbols": symbols,
                "guardrails": selected[:20],
                "readback": payload.get("readback"),
            },
        )

    def _notify_lifecycle_changes(self, payload: dict, previous: Optional[dict]) -> None:
        summary = payload.get("summary") or {}
        previous_summary = previous.get("summary", {}) if previous else {}
        position_symbols = sorted(str(item.get("symbol") or "").upper() for item in payload.get("positions", []) if item.get("symbol"))
        previous_symbols = sorted(str(item.get("symbol") or "").upper() for item in previous.get("positions", []) if item.get("symbol")) if previous else []
        position_count = int(summary.get("open_positions") or 0)
        previous_count = int(previous_summary.get("open_positions") or 0) if previous_summary else position_count

        changes = []
        if previous and (position_count != previous_count or position_symbols != previous_symbols):
            added = sorted(set(position_symbols) - set(previous_symbols))
            removed = sorted(set(previous_symbols) - set(position_symbols))
            changes.append(
                f"Open positions changed from {previous_count} to {position_count}. "
                f"Added: {', '.join(added) or 'none'}. Removed: {', '.join(removed) or 'none'}."
            )
            # Write terminal position_closed rows for removed symbols so journal doesn't accumulate stale open_position entries
            for removed_symbol in removed:
                try:
                    self.journal.record_trade_outcome({
                        "symbol": removed_symbol,
                        "status": "position_closed",
                        "pnl": None,
                        "r_multiple": None,
                        "notes": "Position no longer in broker — auto-closed by lifecycle reconciliation",
                    })
                except Exception:
                    pass

        recent_fills = payload.get("recent_fills") or []
        latest_fill_ids = [str(item.get("id") or "") for item in recent_fills[:25] if item.get("id")]
        previous_fill_setting = self.journal.get_setting("notification.last_fill_ids", None)
        previous_fill_ids = set(previous_fill_setting or [])
        new_fills = [] if previous_fill_setting is None else [
            item for item in recent_fills[:10] if str(item.get("id") or "") and str(item.get("id")) not in previous_fill_ids
        ]
        if latest_fill_ids:
            self.journal.set_setting("notification.last_fill_ids", latest_fill_ids)
        if new_fills:
            lines = []
            for fill in new_fills[:6]:
                lines.append(
                    f"{fill.get('symbol')}: {fill.get('side')} {fill.get('qty')} @ {fill.get('price')} ({fill.get('order_status')})"
                )
            if len(new_fills) > 6:
                lines.append(f"+{len(new_fills) - 6} more fill(s)")
            changes.append("New Alpaca fill activity:\n" + "\n".join(lines))

        if not changes:
            return
        key_source = "|".join(position_symbols) + "|" + "|".join(str(item.get("id")) for item in new_fills[:10])
        key = "lifecycle-change:" + hashlib.sha1(key_source.encode("utf-8")).hexdigest()[:16]
        self._notify_event(
            key=key,
            title="Trading Bull lifecycle changed",
            detail="\n".join(changes),
            severity="info",
            payload={
                "kind": "lifecycle_change",
                "timestamp": payload.get("timestamp"),
                "summary": summary,
                "positions": position_symbols,
                "new_fills": new_fills[:10],
            },
        )

    def _notify_lifecycle_thresholds(self, payload: dict) -> None:
        sent = set(self.journal.get_setting("notification.lifecycle_threshold_keys", []) or [])
        new_keys = set(sent)
        messages = []
        drawdown_threshold = self._float(os.getenv("VELEZ_NOTIFY_DRAWDOWN_R", "-0.5")) or -0.5
        for position in payload.get("positions", []):
            symbol = str(position.get("symbol") or "").upper().strip()
            r_multiple = self._float(position.get("current_r_multiple"))
            if not symbol or r_multiple is None:
                continue
            alert_ref = position.get("linked_alert_ref") or symbol
            thresholds = []
            if r_multiple >= 1:
                thresholds.append(("1R", "Position reached at least 1R; review partial and breakeven stop."))
            if r_multiple >= 2:
                thresholds.append(("2R", "Position reached at least 2R; review trailing or larger partial."))
            if r_multiple <= drawdown_threshold:
                thresholds.append(("drawdown", f"Position is at {r_multiple:.2f}R; review risk reduction."))
            for threshold, detail in thresholds:
                key = f"{alert_ref}:{symbol}:{threshold}"
                if key in sent:
                    continue
                new_keys.add(key)
                messages.append(f"{symbol} {threshold}: {detail}")
        if new_keys != sent:
            self.journal.set_setting("notification.lifecycle_threshold_keys", sorted(new_keys)[-500:])
        if not messages:
            return
        self._notify_event(
            key="lifecycle-threshold:" + hashlib.sha1("|".join(messages).encode("utf-8")).hexdigest()[:16],
            title="Trading Bull lifecycle threshold",
            detail="\n".join(messages[:8]),
            severity="info",
            payload={
                "kind": "lifecycle_threshold",
                "timestamp": payload.get("timestamp"),
                "messages": messages[:8],
                "summary": payload.get("summary"),
            },
        )

    def _notify_event(self, *, key: str, title: str, detail: str, severity: str, payload: dict, ignore_cooldown: bool = False) -> None:
        targets = self._notification_targets()
        if not targets:
            return
        cooldown = self._int_env("VELEZ_NOTIFY_COOLDOWN_SECONDS", 1800, minimum=0, maximum=86400)
        now = datetime.now(timezone.utc)
        last_sent = self.notification_cache.get(key)
        if not ignore_cooldown and cooldown and last_sent and (now - last_sent).total_seconds() < cooldown:
            return
        message = f"{title}\nSeverity: {severity.upper()}\n{detail}".strip()
        delivered = False
        for target in targets:
            try:
                if target["type"] == "file":
                    record = {
                        **payload,
                        "title": title,
                        "detail": detail,
                        "severity": severity,
                        "notified_at": now.isoformat(),
                    }
                    path = Path(target["path"]).expanduser()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
                    delivered = True
                    continue
                if target["type"] == "telegram":
                    response = requests.post(
                        f"https://api.telegram.org/bot{target['token']}/sendMessage",
                        json={"chat_id": target["chat_id"], "text": message[:3900]},
                        timeout=8,
                    )
                    if response.status_code < 300:
                        self._send_telegram_audio_notice(
                            target=target,
                            title=title,
                            message=message,
                            payload=payload,
                        )
                elif target["type"] == "discord":
                    response = requests.post(
                        target["url"],
                        json={"content": message[:1900], "embeds": [{"title": title[:256], "description": detail[:3900]}]},
                        timeout=8,
                    )
                else:
                    response = requests.post(
                        target["url"],
                        json={**payload, "title": title, "detail": detail, "severity": severity},
                        timeout=8,
                    )
                if response.status_code < 300:
                    delivered = True
                else:
                    log_event(self.logger, "notification_failed", {"target": target["type"], "status_code": response.status_code})
            except Exception as exc:
                log_event(self.logger, "notification_failed", {"target": target["type"], "reason": str(exc)})
        if delivered:
            self.notification_cache[key] = now

    def _send_telegram_audio_notice(self, *, target: dict, title: str, message: str, payload: dict) -> None:
        if not _bool_env("VELEZ_NOTIFY_TELEGRAM_AUDIO_ENABLED", False):
            return
        if str(payload.get("telegram_audio", "")).strip().lower() in {"0", "false", "no", "off", "skip"}:
            return
        max_chars = self._int_env("VELEZ_NOTIFY_TELEGRAM_AUDIO_MAX_CHARS", 700, minimum=120, maximum=2000)
        speech_text = str(payload.get("voice_summary") or payload.get("speech_text") or message)
        speech_text = " ".join(speech_text.split())[:max_chars]
        if not speech_text:
            return
        result = self.winston.synthesize_speech(speech_text)
        if not result.get("ok"):
            log_event(
                self.logger,
                "telegram_audio_notice_skipped",
                {"reason": result.get("reason", "tts_failed"), "provider": result.get("provider")},
            )
            return
        audio = result.get("content")
        if not audio:
            log_event(self.logger, "telegram_audio_notice_skipped", {"reason": "missing_audio_content"})
            return
        filename = "trading-bull-brief.mp3"
        caption = str(title or "Trading Bull Desk")[:1024]
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{target['token']}/sendAudio",
                data={
                    "chat_id": target["chat_id"],
                    "caption": caption,
                    "title": caption[:64],
                    "performer": "Trading Bull Desk",
                },
                files={"audio": (filename, io.BytesIO(audio), result.get("media_type") or "audio/mpeg")},
                timeout=self._int_env("VELEZ_NOTIFY_TELEGRAM_AUDIO_TIMEOUT_SECONDS", 20, minimum=5, maximum=120),
            )
            if response.status_code >= 300:
                log_event(
                    self.logger,
                    "telegram_audio_notice_failed",
                    {"status_code": response.status_code, "detail": response.text[:160]},
                )
        except Exception as exc:
            log_event(self.logger, "telegram_audio_notice_failed", {"reason": str(exc)})

    def _notification_targets(self) -> List[dict]:
        enabled = os.getenv("VELEZ_NOTIFY_ENABLED", "").strip().lower()
        generic_url = os.getenv("VELEZ_NOTIFY_WEBHOOK_URL", "").strip()
        discord_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip() or os.getenv("VELEZ_NOTIFY_DISCORD_WEBHOOK_URL", "").strip()
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or os.getenv("VELEZ_NOTIFY_TELEGRAM_BOT_TOKEN", "").strip()
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip() or os.getenv("VELEZ_NOTIFY_TELEGRAM_CHAT_ID", "").strip()
        file_path = os.getenv("VELEZ_NOTIFY_FILE", "").strip()
        configured = bool(generic_url or discord_url or file_path or (telegram_token and telegram_chat_id))
        if enabled in {"0", "false", "no", "off"}:
            return []
        if enabled not in {"1", "true", "yes", "on"} and not configured:
            return []
        targets: List[dict] = []
        if file_path:
            targets.append({"type": "file", "path": file_path})
        if generic_url:
            targets.append({"type": "webhook", "url": generic_url})
        if discord_url:
            targets.append({"type": "discord", "url": discord_url})
        if telegram_token and telegram_chat_id:
            targets.append({"type": "telegram", "token": telegram_token, "chat_id": telegram_chat_id})
        return targets

    def _record_lifecycle_outcomes(self, payload: dict) -> None:
        if os.getenv("VELEZ_LIFECYCLE_AUTORECORD_OUTCOMES", "true").strip().lower() not in {"1", "true", "yes", "on"}:
            return
        existing_keys = {str(item.get("event_key") or "") for item in self.journal.latest_trade_outcomes(limit=100)}
        now = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()

        def record_once(outcome: dict) -> None:
            key = str(outcome.get("event_key") or "")
            if key and key in existing_keys:
                return
            saved = self.journal.record_trade_outcome(outcome)
            existing_keys.add(str(saved.get("event_key") or key))

        for position in payload.get("positions", []):
            symbol = position.get("symbol")
            alert_ref = position.get("linked_alert_ref") or f"unlinked-{symbol}"
            r_multiple = self._float(position.get("current_r_multiple"))
            pnl = self._float(position.get("unrealized_pl"))
            base = {
                "timestamp": now,
                "alert_ref": alert_ref,
                "symbol": symbol,
                "r_multiple": self._round_or_none(r_multiple),
                "pnl": self._round_or_none(pnl),
                "setup": position.get("linked_setup"),
            }
            record_once(
                {
                    **base,
                    "event_key": f"{alert_ref}:{symbol}:open_position",
                    "status": "open_position",
                    "notes": position.get("next_action") or "Active position reconciled.",
                }
            )
            if r_multiple is not None and r_multiple >= 1:
                record_once(
                    {
                        **base,
                        "event_key": f"{alert_ref}:{symbol}:one_r_reached",
                        "status": "one_r_reached",
                        "notes": "Position reached at least 1R; review partial and breakeven stop rules.",
                    }
                )
            if r_multiple is not None and r_multiple >= 2:
                record_once(
                    {
                        **base,
                        "event_key": f"{alert_ref}:{symbol}:two_r_reached",
                        "status": "two_r_reached",
                        "notes": "Position reached at least 2R; trail-winner review is due.",
                    }
                )
        for guardrail in payload.get("guardrails", []):
            symbol = guardrail.get("symbol") or "desk"
            record_once(
                {
                    "timestamp": now,
                    "alert_ref": f"guardrail-{symbol}",
                    "symbol": symbol,
                    "status": f"guardrail_{guardrail.get('name')}",
                    "event_key": f"guardrail:{symbol}:{guardrail.get('name')}",
                    "notes": guardrail.get("detail") or guardrail.get("status") or "Lifecycle guardrail alert.",
                }
            )

    def _round_or_none(self, value: Any, places: int = 2) -> Optional[float]:
        number = self._float(value)
        return round(number, places) if number is not None else None

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

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        try:
            parsed = self._timestamp(value)
        except Exception:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


class OpsAuditLog:
    """Read-only audit log that redacts sensitive values from stored payloads.

    Writes one JSON object per line. Sensitive keys (token, api_key, secret,
    password, key, authorization) are replaced with '<redacted>' before
    writing and when reading back.

    This is a safety utility, not a security boundary — it prevents casual
    credential leaks in log files but does not replace proper secret management.
    """

    SENSITIVE_KEYS = frozenset({
        "token", "api_key", "secret", "password", "key", "authorization",
        "access_token", "refresh_token", "private_key", "credential",
    })

    def __init__(self, path: str) -> None:
        from pathlib import Path
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        import threading
        self._lock = threading.Lock()

    def record(self, event_type: str, payload: dict) -> None:
        import json as _json
        from datetime import datetime, timezone
        safe = self._redact(payload)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "payload": safe,
        }
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(_json.dumps(entry, sort_keys=True, default=str) + "\n")

    def recent(self, n: int = 10) -> list:
        import json as _json
        if not self._path.exists():
            return []
        entries: list = []
        with self._lock:
            lines = self._path.read_text(encoding="utf-8").strip().split("\n")
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    entries.append(_json.loads(line))
                except _json.JSONDecodeError:
                    continue
                if len(entries) >= n:
                    break
        return entries

    def _redact(self, value):
        if isinstance(value, dict):
            return {
                k: "<redacted>" if k.lower() in self.SENSITIVE_KEYS else self._redact(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self._redact(v) for v in value]
        return value


def create_app(config: dict):
    app = FastAPI(title="Trading Bull Desk Webhook", version="0.1.0")
    engine = TradingViewWebhookEngine(config)
    app.state.engine = engine
    app.state.apple_music = AppleMusicTokenService()
    dashboard_dir = Path(__file__).resolve().parent / "static" / "dashboard"
    dashboard_index = dashboard_dir / "index.html"

    if dashboard_dir.exists():
        app.mount("/dashboard/assets", StaticFiles(directory=str(dashboard_dir)), name="dashboard-assets")

    @app.middleware("http")
    async def dashboard_auth_gate(request: Request, call_next):
        if dashboard_auth_enabled() and _is_dashboard_surface(request.url.path):
            if not _dashboard_auth_configured():
                return _dashboard_auth_missing_config()
            if not _dashboard_auth_allowed(request):
                return _dashboard_auth_failed()
        return await call_next(request)

    @app.on_event("startup")
    async def startup_scanner() -> None:
        engine.start_scanner()

    @app.on_event("shutdown")
    async def shutdown_scanner() -> None:
        engine.stop_scanner_worker()

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

    @app.get("/api/bot/health")
    async def bot_health() -> JSONResponse:
        result = await run_in_threadpool(engine.bot_health)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/vps/latency")
    async def vps_latency() -> JSONResponse:
        result = await run_in_threadpool(engine.latency_payload)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/vps/hardening")
    async def vps_hardening() -> JSONResponse:
        result = await run_in_threadpool(engine.vps_hardening_payload)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/alerts/coverage")
    async def alert_coverage() -> JSONResponse:
        result = await run_in_threadpool(engine.alert_coverage_payload)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/scanner/status")
    async def scanner_status() -> JSONResponse:
        return JSONResponse(content=engine.scanner_public_status(), headers={"Cache-Control": "no-store"})

    @app.get("/api/scanner/quality")
    async def scanner_quality(limit: int = Query(80, ge=1, le=200)) -> JSONResponse:
        result = await run_in_threadpool(engine.scanner_quality_payload, limit)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/watchlist/quality")
    async def watchlist_quality() -> JSONResponse:
        result = await run_in_threadpool(engine.watchlist_quality_payload)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.post("/api/watchlist/quality/action")
    async def watchlist_quality_action(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(
            engine.apply_watchlist_quality_action,
            str(payload.get("symbol", "")),
            str(payload.get("action", "")),
            str(payload.get("approval_token", "")),
        )
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.post("/api/scanner/quality/notify")
    async def scanner_quality_notify(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(engine.send_scanner_quality_report, str(payload.get("approval_token", "")))
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.post("/api/scanner/mode")
    async def scanner_mode(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(
            engine.set_scanner_control_mode,
            str(payload.get("mode", "")),
            str(payload.get("approval_token", "")),
        )
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.post("/api/scanner/orders/cancel-stale")
    async def scanner_cancel_stale_orders(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(engine.cancel_stale_scanner_orders, str(payload.get("approval_token", "")))
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.get("/api/lifecycle/state")
    async def lifecycle_state() -> JSONResponse:
        result = await run_in_threadpool(engine.lifecycle_payload)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.post("/api/lifecycle/reconcile")
    async def lifecycle_reconcile() -> JSONResponse:
        result = await run_in_threadpool(engine.lifecycle_payload)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/lifecycle/outcomes")
    async def lifecycle_outcomes() -> JSONResponse:
        result = await run_in_threadpool(engine.lifecycle_outcomes_payload)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/lifecycle/partials/plan")
    async def lifecycle_partial_plan() -> JSONResponse:
        result = await run_in_threadpool(engine.lifecycle_partial_plan)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/lifecycle/doctor")
    async def lifecycle_doctor() -> JSONResponse:
        result = await run_in_threadpool(engine.lifecycle_doctor_payload)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/lifecycle/reduction/plan")
    async def lifecycle_reduction_plan() -> JSONResponse:
        result = await run_in_threadpool(engine.exposure_reduction_plan)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.get("/api/scanner/reopen-check")
    async def scanner_reopen_check() -> JSONResponse:
        result = await run_in_threadpool(engine.scanner_reopen_check)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.post("/api/lifecycle/actions/claim")
    async def lifecycle_claim(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(
            engine.claim_lifecycle_position,
            str(payload.get("symbol", "")),
            str(payload.get("alert_ref", "")),
            str(payload.get("approval_token", "")),
        )
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.post("/api/lifecycle/actions/auto-claim")
    async def lifecycle_auto_claim(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(engine.auto_claim_lifecycle_positions, str(payload.get("approval_token", "")))
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.post("/api/lifecycle/actions/repair-stop")
    async def lifecycle_repair_stop(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(engine.repair_lifecycle_stop, str(payload.get("symbol", "")), str(payload.get("approval_token", "")))
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.post("/api/lifecycle/actions/reduce")
    async def lifecycle_reduce(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(
            engine.reduce_lifecycle_position,
            str(payload.get("symbol", "")),
            payload.get("fraction", 0),
            str(payload.get("approval_token", "")),
        )
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.post("/api/lifecycle/actions/breakeven")
    async def lifecycle_breakeven(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(engine.move_eligible_stops_to_breakeven, str(payload.get("approval_token", "")))
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.post("/api/webhook/test")
    async def webhook_test(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(engine.webhook_test_payload, payload)
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.get("/api/risk/status")
    async def risk_status() -> JSONResponse:
        result = await run_in_threadpool(engine.risk_status_payload)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

    @app.post("/api/risk/approval-mode")
    async def risk_approval_mode(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(
            engine.set_order_approval_required,
            str(payload.get("enabled", "")).strip().lower() in {"1", "true", "yes", "on"},
            str(payload.get("approval_token", "")),
        )
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.post("/api/notifications/test")
    async def notification_test(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(engine.notification_test_payload, str(payload.get("channel", "all") or "all"))
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

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

    @app.post("/api/brief/daily/telegram")
    async def daily_brief_telegram() -> JSONResponse:
        result = await run_in_threadpool(engine.send_daily_brief_notification)
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(
            content=result,
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/review/daily")
    async def daily_review() -> JSONResponse:
        result = await run_in_threadpool(engine.daily_review_payload)
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/review/close")
    async def daily_close_report() -> JSONResponse:
        result = await run_in_threadpool(engine.daily_close_report_payload)
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/journal/review")
    async def journal_review(alert_ref: str = Query("", max_length=64)) -> JSONResponse:
        result = await run_in_threadpool(engine.trade_review_payload, alert_ref)
        status_code = 200 if result.get("ok") else 404
        return JSONResponse(content=result, status_code=status_code, headers={"Cache-Control": "no-store"})

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

    @app.post("/api/replay/risk")
    async def replay_risk(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(engine.risk_replay_payload, payload)
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

    @app.get("/api/winston/morning-call")
    async def winston_morning_call() -> JSONResponse:
        result = await run_in_threadpool(engine.winston_morning_call_payload)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})

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

    @app.post("/api/winston/deep-research")
    async def winston_deep_research(request: Request) -> JSONResponse:
        try:
            payload = await _payload_from_request(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await run_in_threadpool(
            engine.winston_deep_research,
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
