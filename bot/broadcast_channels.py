"""Managed public channel assignments; no subscriber credentials reach the player."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse


def channel_catalog():
    channels = [
        {"id": "bloomberg", "label": "Bloomberg", "category": "Market News", "kind": "live", "youtube_video_id": "QB5BNdBFujE", "youtube_channel_url": "https://www.youtube.com/@markets"},
        {"id": "yahoo", "label": "Yahoo Finance", "category": "Market News", "kind": "live", "youtube_video_id": "KQp-e_XQnDE", "youtube_channel_url": "https://www.youtube.com/@YahooFinance"},
        {"id": "schwab", "label": "Schwab Network", "category": "Market News", "kind": "live", "youtube_video_id": "3etkI14QncQ", "youtube_channel_url": "https://www.youtube.com/@SchwabNetwork"},
        {"id": "tastylive", "label": "tastylive", "category": "Market Education", "kind": "replay", "youtube_video_id": "E5JcL8gjaZ8", "program": "Why the VIX Drops Before 3-Day Weekends", "youtube_channel_url": "https://www.youtube.com/@tastyliveshow"},
        {"id": "fed", "label": "Federal Reserve", "category": "Central Banks", "kind": "replay", "youtube_video_id": "wLyh5fSTLLw", "program": "What is the Fed?", "youtube_channel_url": "https://www.youtube.com/user/FedReserveBoard"},
        {"id": "ecb", "label": "European Central Bank", "category": "Central Banks", "kind": "external", "youtube_channel_url": "https://www.youtube.com/@ecbeuro"},
        {"id": "imf", "label": "International Monetary Fund", "category": "Global Macro", "kind": "external", "youtube_channel_url": "https://www.youtube.com/@IMF"},
        {"id": "world-bank", "label": "World Bank", "category": "Global Macro", "kind": "external", "youtube_channel_url": "https://www.youtube.com/@WorldBank"},
        {"id": "academy", "label": "Trading Bull Academy", "category": "Academy", "kind": "coming-soon"},
        {"id": "winston", "label": "Winston Desk Brief", "category": "Private", "kind": "brief", "private": True},
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
        label = str(update.get("label", "")).strip()
        category = str(update.get("category", "")).strip()
        if label:
            channel["label"] = label[:48]
        if category:
            channel["category"] = category[:32]
        if channel["kind"] in {"live", "replay"} and not (channel.get("youtube_video_id") or channel.get("youtube_playlist_id")):
            channel["kind"] = "external"
    known = {channel["id"] for channel in channels}
    for item in overrides.get("channels", []) if isinstance(overrides.get("channels"), list) else []:
        if not isinstance(item, dict) or len(channels) >= 14:
            continue
        channel_id = str(item.get("id", "")).strip().lower()
        label = str(item.get("label", "")).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,39}", channel_id) or channel_id in known or not label:
            continue
        video_id = str(item.get("youtube_video_id", "")).strip()
        playlist_id = str(item.get("youtube_playlist_id", "")).strip()
        url = str(item.get("youtube_channel_url", "")).strip()
        parsed = urlparse(url)
        valid_url = parsed.scheme == "https" and parsed.hostname in {"youtube.com", "www.youtube.com"} and not parsed.username
        valid_video = bool(re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id))
        valid_playlist = bool(re.fullmatch(r"[A-Za-z0-9_-]{10,80}", playlist_id))
        if not (valid_url or valid_video or valid_playlist):
            continue
        kind = str(item.get("kind", "external"))
        if kind not in {"live", "replay", "external", "coming-soon"}:
            kind = "external"
        if kind in {"live", "replay"} and not (valid_video or valid_playlist):
            kind = "external"
        channel = {"id": channel_id, "label": label[:48], "category": str(item.get("category") or "My Channels")[:32], "kind": kind}
        if valid_video:
            channel["youtube_video_id"] = video_id
        if valid_playlist:
            channel["youtube_playlist_id"] = playlist_id
        if valid_url:
            channel["youtube_channel_url"] = url
        channels.append(channel)
        known.add(channel_id)
    return channels
