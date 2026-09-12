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
    room_js = (STATIC / "sovereign-room.js").read_text(encoding="utf-8")
    sovereign_css = (STATIC / "sovereign.css").read_text(encoding="utf-8")
    server = (STATIC.parents[1] / "webhook_server.py").read_text(encoding="utf-8")

    assert '<body class="room-clear sovereign">' in html
    assert "winston-conference-phone.png" not in html
    assert 'id="desk-phone-object"' not in html
    assert "deskPhoneObject" not in js
    assert "phoneObjectRegion" not in js
    assert "phone-glass.png" in room_js
    assert 'export const SOVEREIGN_VERSION = "1.9.0";' in room_js
    assert "body.sovereign:not([data-room-asset]) .photo-room" in sovereign_css
    assert "opacity .18s ease" in sovereign_css
    assert server.count('FileResponse(dashboard_index, headers={"Cache-Control": "no-store"})') == 2
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


def test_room_regions_keep_realistic_objects_in_all_five_rooms():
    import json
    import re

    source = (STATIC / "sovereign-room.js").read_text(encoding="utf-8")
    literal = source.split("export const ROOMS = ", 1)[1]
    literal = re.sub(r'([,{]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', literal)
    # Decode the first object without depending on which declaration follows it.
    rooms, _ = json.JSONDecoder().raw_decode(literal)
    assert set(rooms) == {"media", "pacific", "tokyo", "manhattan", "dubai"}
    for room in rooms.values():
        objects = room["objects"]
        assert objects["phone"][0] < objects["music"][0]
        assert objects["music"][2] < objects["phone"][2]
        assert objects["music"][0] + objects["music"][2] < objects["keyboard"][0]
        assert objects["music"][1] + objects["music"][3] < objects["keyboard"][1] + objects["keyboard"][3]
        assert objects["trackpad"][2] < objects["keyboard"][2]
        assert room["screen"][2] < 30
        assert set(objects) == {
            "phone", "music", "journal", "keyboard", "trackpad", "lamp",
            "mission", "notes", "bookshelf", "vault",
        }
        vx, vy, vw, vh = objects["vault"]
        bx, by, bw, bh = objects["bookshelf"]
        assert vy + vh < objects["journal"][1]
        assert vx + vw <= bx or bx + bw <= vx or vy + vh <= by or by + bh <= vy
        for x, y, width, height in [*objects.values(), room["screen"], room["broadcast"]]:
            assert 0 <= x < 100 and 0 <= y < 100
            assert width > 0 and height > 0
            assert x + width <= 100 and y + height <= 100
        for plate in room["images"].values():
            assert (STATIC / "sovereign" / plate).is_file()
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "showHover(definition.label, event)" in js
    assert "sovereignObjectMarkup(definition)" in js


def test_current_phone_asset_is_valid_truecolor_png():
    payload = (STATIC / "sovereign" / "phone-glass.png").read_bytes()
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    assert payload[25] == 2  # PNG truecolor; the SVG applies the silhouette clip.
    room_js = (STATIC / "sovereign-room.js").read_text(encoding="utf-8")
    assert 'clipPath id="phone-silhouette"' in room_js
