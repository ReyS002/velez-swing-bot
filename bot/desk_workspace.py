"""Read-only presentation configuration, shared by all Sovereign editions."""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse


def broker_provider(broker) -> str:
    selected = os.getenv("BULLPILOT_BROKER_PROVIDER", "").strip().lower()
    if selected:
        return selected
    name = type(broker).__name__.lower()
    return next((provider for provider in ("robinhood", "alpaca", "tradovate", "simulated") if provider in name), "broker")


def workspace_config(request, broker, *, product: str) -> dict:
    return {
        "product": product,
        "version": "sovereign-1.0.0",
        "broker_provider": broker_provider(broker),
        "account_mode": "subscription" if product == "Bull Pilot" else "workspace",
        "authenticated": bool(getattr(request.state, "dashboard_username", "") or getattr(request.state, "account", None)),
        "tier": getattr(request.state, "dashboard_tier", "Workspace"),
    }


def broadcast_config() -> dict:
    from .broadcast_channels import channel_catalog
    enabled = os.getenv("DESK_BROADCAST_ENABLED", os.getenv("BULLPILOT_BROADCAST_ENABLED", "true")).lower() in {"true", "1", "yes", "on"}
    video_id = os.getenv("DESK_BROADCAST_YOUTUBE_VIDEO_ID", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        video_id = ""
    video_url = os.getenv("DESK_BROADCAST_VIDEO_URL", "").strip()
    parsed = urlparse(video_url)
    # Only administrator-configured HTTPS media or bundled dashboard media.
    if not ((parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password) or video_url.startswith("/dashboard/assets/broadcast/")):
        video_url = ""
    channel = os.getenv("DESK_BROADCAST_YOUTUBE_CHANNEL_URL", "").strip()
    parsed_channel = urlparse(channel)
    if parsed_channel.scheme != "https" or parsed_channel.hostname not in {"youtube.com", "www.youtube.com"}:
        channel = ""
    channels = channel_catalog()
    if video_id or video_url:
        channels.insert(0, {"id": "assigned", "label": "Assigned broadcast", "kind": "replay", "youtube_video_id": video_id, "video_url": video_url, "youtube_channel_url": channel})
    return {"enabled": enabled, "youtube_video_id": video_id, "video_url": video_url, "youtube_channel_url": channel, "preview": not bool(video_id or video_url), "channels": channels, "default_channel": channels[0]["id"]}
