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
