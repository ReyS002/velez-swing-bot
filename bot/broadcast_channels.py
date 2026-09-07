"""Managed public channel assignments; no subscriber credentials reach the player."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse


def channel_catalog():
    channels = [
        {"id": "bloomberg", "label": "Bloomberg", "kind": "live", "youtube_video_id": "QB5BNdBFujE", "youtube_channel_url": "https://www.youtube.com/@markets"},
        {"id": "yahoo", "label": "Yahoo Finance", "kind": "live", "youtube_video_id": "KQp-e_XQnDE", "youtube_channel_url": "https://www.youtube.com/@YahooFinance"},
        {"id": "schwab", "label": "Schwab Network", "kind": "live", "youtube_video_id": "3etkI14QncQ", "youtube_channel_url": "https://www.youtube.com/@SchwabNetwork"},
        {"id": "tastylive", "label": "tastylive", "kind": "replay", "youtube_video_id": "E5JcL8gjaZ8", "program": "Why the VIX Drops Before 3-Day Weekends", "youtube_channel_url": "https://www.youtube.com/@tastyliveshow"},
        {"id": "fed", "label": "Federal Reserve", "kind": "replay", "youtube_video_id": "wLyh5fSTLLw", "program": "What is the Fed?", "youtube_channel_url": "https://www.youtube.com/@FederalReserve"},
        {"id": "academy", "label": "Trading Bull Academy", "kind": "coming-soon"},
        {"id": "winston", "label": "Winston Desk Brief", "kind": "brief", "private": True},
    ]
    # Optional, administrator-owned JSON assignments allow stream rotations without builds.
    path = os.getenv("DESK_BROADCAST_CHANNELS_PATH", "")
    try:
        overrides = json.loads(Path(path).read_text()) if path else {}
        if not isinstance(overrides, dict):
            overrides = {}
    except (OSError, ValueError):
        overrides = {}
    for channel in channels:
        update = overrides.get(channel["id"], {})
        if not isinstance(update, dict) or channel["id"] == "winston":
            continue
        for key, pattern in (("youtube_video_id", r"[A-Za-z0-9_-]{11}"), ("youtube_playlist_id", r"[A-Za-z0-9_-]{10,80}")):
            value = str(update.get(key, ""))
            if re.fullmatch(pattern, value):
                channel[key] = value
        url = str(update.get("youtube_channel_url", ""))
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.hostname in {"youtube.com", "www.youtube.com"} and not parsed.username:
            channel["youtube_channel_url"] = url
        if update.get("kind") in {"live", "replay", "external", "coming-soon"}:
            channel["kind"] = update["kind"]
        if channel["kind"] in {"live", "replay"} and not (channel.get("youtube_video_id") or channel.get("youtube_playlist_id")):
            channel["kind"] = "external"
    return channels
