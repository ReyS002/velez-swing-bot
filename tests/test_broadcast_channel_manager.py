from bot.broadcast_channels import channel_catalog
import json


def test_macro_defaults_are_grouped_and_academy_stays_separate(monkeypatch):
    monkeypatch.delenv("DESK_BROADCAST_CHANNELS_PATH", raising=False)
    channels = {channel["id"]: channel for channel in channel_catalog()}
    assert channels["fed"]["category"] == "Central Banks"
    assert channels["ecb"]["kind"] == "external"
    assert channels["imf"]["category"] == "Global Macro"
    assert channels["world-bank"]["category"] == "Global Macro"
    assert channels["academy"]["category"] == "Academy"
    assert channels["winston"]["private"] is True


def test_admin_catalog_additions_are_validated_and_capped(tmp_path, monkeypatch):
    additions = [
        {
            "id": f"macro-{index}",
            "label": f"Macro source {index}",
            "category": "Global Macro",
            "kind": "live",
            "youtube_video_id": f"videoID{index:04d}",
            "youtube_channel_url": "https://www.youtube.com/@official",
        }
        for index in range(6)
    ]
    additions.append({
        "id": "unsafe",
        "label": "Unsafe",
        "kind": "external",
        "youtube_channel_url": "javascript:alert(1)",
    })
    path = tmp_path / "channels.json"
    path.write_text(json.dumps({"channels": additions}), encoding="utf-8")
    monkeypatch.setenv("DESK_BROADCAST_CHANNELS_PATH", str(path))
    channels = channel_catalog()
    assert len(channels) == 14
    assert [channel["id"] for channel in channels[-4:]] == [f"macro-{index}" for index in range(4)]
    assert all(channel["id"] != "unsafe" for channel in channels)

