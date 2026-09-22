import re
from pathlib import Path


def test_broadcast_and_dashboard_share_one_room_controller():
    root = Path(__file__).resolve().parents[2]
    assets = root / "bot" / "static" / "dashboard"
    imports = []
    for name in ("app.js", "broadcast.js"):
        source = (assets / name).read_text()
        imports.append(re.search(r'from "([^"]*sovereign-room\.js[^"]*)"', source).group(1))
    assert imports[0] == imports[1], "Different module URLs create independent room state and misalign the TV"


def test_room_switch_clears_before_loading_and_has_one_loader_path():
    root = Path(__file__).resolve().parents[2]
    source = (root / "bot" / "static" / "dashboard" / "sovereign-room.js").read_text()
    start = source.index("export function syncRoomTheme")
    end = source.index("export function selectRoom", start)
    sync = source[start:end]
    assert sync.index('document.body.removeAttribute("data-room-asset")') < sync.index("const load=")
    select = source[end:source.index("function announce", end)]
    assert "if(adapter?.setTheme)adapter.setTheme" in select
    assert "else syncRoomTheme" in select
