from pathlib import Path


ASSETS = Path(__file__).resolve().parents[1] / "static" / "dashboard"


def test_desk_intelligence_is_connected_to_shared_room_state():
    room = (ASSETS / "sovereign-room.js").read_text(encoding="utf-8")
    panel = (ASSETS / "sovereign-panel.js").read_text(encoding="utf-8")
    enhancements = (ASSETS / "sovereign-enhancements.js").read_text(encoding="utf-8")
    app = (ASSETS / "app.js").read_text(encoding="utf-8")
    html = (ASSETS / "index.html").read_text(encoding="utf-8")

    assert 'export const SOVEREIGN_VERSION = "1.13.1";' in room
    assert 'mountPanelExperience' in room and 'updatePanelExperience' in room
    assert 'desk:panel-request' in panel and 'desk:attention-open' in panel
    assert 'restoreScroll' in panel
    assert 'desk:awareness' in enhancements
    assert all(name in enhancements for name in ('"event"', '"approval"', '"connection"'))
    assert 'classList.remove("is-new"),3400' in enhancements
    assert 'renderSessionBriefChanges' in app and 'syncDeskAwareness' in app
    assert 'sovereign-motion.css?v=1.12.0' in html
    assert 'sovereign-enhancements.css?v=1.12.0' in html
