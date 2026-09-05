import struct
import zlib
from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "static" / "dashboard"


def _png_rgb_at(path: Path, x: int, y: int) -> tuple[int, int, int]:
    payload = path.read_bytes()
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    offset = 8
    width = height = color_type = None
    idat = []
    while offset < len(payload):
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        kind = payload[offset + 4 : offset + 8]
        chunk = payload[offset + 8 : offset + 8 + length]
        offset += length + 12
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
            assert bit_depth == 8
            assert interlace == 0
        elif kind == b"IDAT":
            idat.append(chunk)
    assert width is not None and height is not None and color_type in {2, 6}
    bpp = 4 if color_type == 6 else 3
    stride = width * bpp
    raw = zlib.decompress(b"".join(idat))
    previous = [0] * stride
    rows = []
    raw_offset = 0
    for _ in range(height):
        filter_type = raw[raw_offset]
        raw_offset += 1
        row = list(raw[raw_offset : raw_offset + stride])
        raw_offset += stride
        for index, value in enumerate(row):
            left = row[index - bpp] if index >= bpp else 0
            up = previous[index]
            up_left = previous[index - bpp] if index >= bpp else 0
            if filter_type == 1:
                row[index] = (value + left) & 255
            elif filter_type == 2:
                row[index] = (value + up) & 255
            elif filter_type == 3:
                row[index] = (value + ((left + up) // 2)) & 255
            elif filter_type == 4:
                estimate = left + up - up_left
                predictor = min((left, up, up_left), key=lambda item: abs(estimate - item))
                row[index] = (value + predictor) & 255
            else:
                assert filter_type == 0
        rows.append(row)
        previous = row
    index = x * bpp
    return tuple(rows[y][index : index + 3])


def test_v623_phone_art_and_winston_voice_lock_are_wired():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    assert "winston-conference-phone.png?v=6.23.5" in html
    assert "v623-room-night.png" in css
    assert "v623-room-day.png" in css
    assert 'const WINSTON_REQUIRED_VOICE = "winston";' in js
    assert "voice lock rejected" in js
    assert "Winston voice unavailable — generic voice blocked" in js
    assert "splitWinstonSpeech" in js
    assert "requestWinstonMorningCall();" not in js[js.index("function startWinstonCall()") : js.index("function endWinstonCall()")]
    speech = js[js.index("async function speakWinston") : js.index("function refreshWinstonPanel")]
    assert speech.index("stopWinstonAudio();") < speech.index("await refreshWinstonStatus();")
    assert "if (speechId !== winstonState.speechRequestId) return;" in speech
    assert "speakBrowserWinston(text);" not in speech
    assert "markServerVoiceFailure(voice.detail || \"Server voice lock requires Fish Winston\");" in speech
    listening = js[js.index("function toggleWinstonListening") : js.index("function renderTranscript")]
    assert "Waiting for microphone permission" in listening


def test_room_regions_ground_phone_move_ipod_and_tighten_hotspots():
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    assert "phoneObjectRegion = { x: 0.08, y: 0.645, w: 0.26, h: 0.23 }" in js
    assert 'panel: "safe", label: "Credential safe", icon: "shield-check", x: 0.875, y: 0.57, w: 0.055, h: 0.15' in js
    assert 'panel: "phone", label: "Call Winston", icon: "phone-call", x: 0.13, y: 0.665, w: 0.17, h: 0.17' in js
    assert 'panel: "laptop", label: "Command center", icon: "laptop", x: 0.455, y: 0.738, w: 0.075, h: 0.07' in js
    assert 'panel: "calendar", label: "Calendar and P/L", icon: "calendar-days", x: 0.71, y: 0.575, w: 0.06, h: 0.085' in js
    assert 'panel: "music", label: "Music", icon: "music", x: 0.315, y: 0.742, w: 0.065, h: 0.075' in js
    assert 'panel: "bookshelf", label: "Strategy library", icon: "library", x: 0.035, y: 0.16, w: 0.07, h: 0.16' in js
    assert 'panel: "window", label: "Market weather", icon: "cloud-sun", x: 0.61, y: 0.18, w: 0.09, h: 0.1' in js
    assert 'panel: "drawer", label: "Backtest drawer", icon: "archive", x: 0.89, y: 0.875, w: 0.065, h: 0.06' in js
    assert 'panel: "notes", label: "Bull Report", icon: "file-text", x: 0.93, y: 0.425, w: 0.055, h: 0.085' in js
    assert "rotateX(24deg) rotateZ(2deg)" in css
    assert "drop-shadow(0 1px 1px" in css
    hotspot = css[css.index(".room-hotspot {") : css.index(".topbar {")]
    assert "border: 0;" in hotspot
    assert "color: transparent;" in hotspot
    assert "background: transparent;" in hotspot
    assert "box-shadow: none;" in hotspot
    assert "opacity: 1;" not in hotspot
    assert "pointermove" in js and "showHover(definition.label, event)" in js
    old_ipod_location = _png_rgb_at(STATIC / "v623-room-day.png", 450, 715)
    ipod_screen_on_mat = _png_rgb_at(STATIC / "v623-room-day.png", 550, 740)
    assert old_ipod_location[2] < old_ipod_location[0]
    assert ipod_screen_on_mat[2] > ipod_screen_on_mat[0] + 30


def test_conference_phone_asset_has_alpha_channel():
    payload = (STATIC / "winston-conference-phone.png").read_bytes()
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    assert payload[25] == 6  # PNG truecolor with alpha.
