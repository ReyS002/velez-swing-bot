import re
from html.parser import HTMLParser
from pathlib import Path


DASHBOARD = Path(__file__).resolve().parents[1] / "static" / "dashboard"
WEBHOOK_SERVER = DASHBOARD.parents[1] / "webhook_server.py"


_CSS_BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)
_RGBA_ALPHA = re.compile(r"rgba\([^)]*?,\s*([01](?:\.\d+)?)\s*\)", re.IGNORECASE)
_HEX_COLOR = re.compile(r"#[0-9a-f]{3,8}\b", re.IGNORECASE)


def _css_blocks(styles: str, selector: str) -> list[str]:
    styles = re.sub(r"/\*.*?\*/", "", styles, flags=re.DOTALL)
    target = " ".join(selector.split())
    blocks = []
    for raw_selectors, body in _CSS_BLOCK.findall(styles):
        selectors = {" ".join(item.split()) for item in raw_selectors.split(",")}
        if target in selectors:
            blocks.append(body)
    return blocks


def _css_values(styles: str, selector: str, property_name: str) -> list[str]:
    values = []
    pattern = re.compile(rf"(?m)^\s*{re.escape(property_name)}\s*:\s*(.*?);", re.DOTALL)
    for block in _css_blocks(styles, selector):
        values.extend(match.strip() for match in pattern.findall(block))
    return values


def _background_alphas(styles: str, selector: str) -> list[float]:
    return [
        float(alpha)
        for value in _css_values(styles, selector, "background")
        for alpha in _RGBA_ALPHA.findall(value)
    ]


def _effective_opacity(parent: float, child: float) -> float:
    return 1 - ((1 - parent) * (1 - child))


class _IdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.ids.extend(value for key, value in attrs if key == "id" and value)


def test_dashboard_v644_preserves_tradingview_and_mobile_workflow_hooks():
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "app.js").read_text()
    server = WEBHOOK_SERVER.read_text()

    assert "v=6.40.4" in html
    assert 'const APP_BUILD = "v6.40.4"' in script
    frontend_version = re.search(r'const APP_BUILD = "(v[^"]+)"', script)
    backend_version = re.search(r'DASHBOARD_VERSION = "(v[^"]+)"', server)
    assert frontend_version and backend_version
    assert frontend_version.group(1) == backend_version.group(1) == "v6.40.4"
    assert "embed-widget-advanced-chart.js" in script
    assert 'style: "1"' in script
    assert 'data-workflow="desk"' in html
    assert 'data-workflow="trade"' in html
    assert 'data-workflow="review"' in html
    assert 'data-workflow="coach"' in html
    assert 'data-workflow="lab"' in html
    assert "data-mobile-pro-console-open" in html
    assert "Return to Desk" in html
    assert 'id="chart-screen"' not in html
    assert "function drawChart" not in script
    assert "desk_canvas_fallback" not in script
    assert 'source: "tradingview_symbol_link"' in script
    assert '<body class="room-clear sovereign">' in html
    assert "let roomClear = true;" in script
    assert 'document.body.classList.toggle("room-clear", roomClear)' in script
    assert 'closePanel({ clearRoom: false })' in script


def test_dashboard_decision_surfaces_use_server_apis_and_never_submit():
    script = (DASHBOARD / "app.js").read_text()

    required = {
        "/api/entitlements",
        "/api/pro/bootstrap",
        "/api/readiness",
        "/api/planner/preview",
        "/api/journal/intelligence",
        "/api/journal/structured-review/",
        "/api/market/context",
        "/api/playbook",
        "/api/notes/",
        "/api/annotations",
        "/api/missed-trades",
        "/api/discipline",
    }
    assert all(path in script for path in required)
    planner_start = script.index("async function calculateExecutionPlan")
    planner_end = script.index("async function refreshStructuredReview", planner_start)
    planner_code = script[planner_start:planner_end]
    assert "/api/planner/preview" in planner_code
    assert "submit_order" not in planner_code
    assert "/api/approvals" not in planner_code
    assert 'method: "POST"' in planner_code
    assert "can_submit" in script


def test_dashboard_hardening_hooks_and_honest_states_are_present():
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "app.js").read_text()
    styles = (DASHBOARD / "styles.css").read_text()

    assert 'id="desk-announcer"' in html
    assert "AbortController" in script
    assert 'document.addEventListener("visibilitychange"' in script
    assert "cleanupTradingViewWidgets" in script
    assert "setInterval(refreshState" not in script
    assert "@media (prefers-reduced-motion: reduce)" in styles
    assert "safe-area-inset-bottom" in styles
    assert "@media (max-height: 500px) and (orientation: landscape)" in styles
    assert "button:focus-visible" in styles
    assert "Unavailable" in script and "Unknown" in script and "Stale" in script
    assert styles.count("{") == styles.count("}")


def test_dashboard_startup_uses_the_defined_market_clock_helper():
    script = (DASHBOARD / "app.js").read_text()

    assert "sessionState()" not in script
    assert script.count("const session = marketClock();") == 2


def test_dashboard_css_is_structurally_valid():
    styles = (DASHBOARD / "styles.css").read_text()
    cleaned = re.sub(r"/\*.*?\*/", "", styles, flags=re.DOTALL)
    stack: list[str] = []
    pairs = {"}": "{", ")": "(", "]": "["}
    quote = None
    escaped = False
    for character in cleaned:
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character in "{([":
            stack.append(character)
        elif character in "})]":
            assert stack and stack.pop() == pairs[character]
    assert quote is None and not stack

    declaration = re.compile(r"[a-zA-Z_-][a-zA-Z0-9_-]*\s*:\s*[^;{}]+;", re.DOTALL)
    blocks = _CSS_BLOCK.findall(cleaned)
    assert len(blocks) > 300
    for selectors, body in blocks:
        assert not declaration.sub("", body).strip(), selectors.strip()


def test_dashboard_html_ids_are_unique():
    parser = _IdParser()
    parser.feed((DASHBOARD / "index.html").read_text())
    duplicates = sorted({value for value in parser.ids if parser.ids.count(value) > 1})
    assert duplicates == []


def test_glass_major_surfaces_stay_inside_approved_opacity_boundaries():
    styles = (DASHBOARD / "styles.css").read_text()

    root = _css_blocks(styles, ":root")[0]
    day = _css_blocks(styles, 'body[data-room-theme="day"]')[0]
    for variables in (root, day):
        ordinary = _RGBA_ALPHA.search(_css_values(f":root {{{variables}}}", ":root", "--glass")[0])
        strong = _RGBA_ALPHA.search(_css_values(f":root {{{variables}}}", ":root", "--glass-strong")[0])
        assert ordinary and 0.12 <= float(ordinary.group(1)) <= 0.30
        assert strong and 0.20 <= float(strong.group(1)) <= 0.38

    ordinary_surfaces = {
        ".glass-surface": 0.30,
        'body[data-room-theme="day"] .glass-surface': 0.30,
        ".mobile-glass": 0.30,
        'body[data-room-theme="day"] .mobile-glass': 0.30,
        ".pro-card": 0.30,
    }
    for selector, upper_bound in ordinary_surfaces.items():
        alphas = _background_alphas(styles, selector)
        assert alphas, f"{selector} must define a translucent background"
        assert 0.08 <= max(alphas) <= upper_bound, (selector, alphas)

    inner_surfaces = [
        ".panel-heading",
        'body[data-room-theme="day"] .panel-heading',
        ".decision-surface",
        'body[data-room-theme="day"] .decision-surface',
        ".metric",
        ".planner-result",
        ".planner-messages article",
        ".rolling-grid article",
        ".missed-grid article",
        ".breakdown-details",
        ".formula-details",
        ".playbook-card",
    ]
    for selector in inner_surfaces:
        alphas = _background_alphas(styles, selector)
        assert alphas, f"{selector} must keep an explicit translucent tint"
        assert 0.02 <= max(alphas) <= 0.18, (selector, alphas)


def test_glass_regressions_cannot_restore_opaque_major_panels():
    styles = (DASHBOARD / "styles.css").read_text()
    limits = {
        ".panel-heading": 0.36,
        'body[data-room-theme="day"] .panel-heading': 0.36,
        ".pro-card": 0.30,
        ".detail-panel": 0.38,
        'body[data-room-theme="day"] .detail-panel': 0.38,
        ".pro-console": 0.30,
        'body[data-room-theme="day"] .pro-console': 0.30,
        ".topbar": 0.40,
        'body[data-room-theme="day"] .topbar': 0.40,
        ".workflow-nav": 0.40,
        'body[data-room-theme="day"] .workflow-nav': 0.40,
    }
    for selector, limit in limits.items():
        backgrounds = _css_values(styles, selector, "background")
        assert backgrounds, f"{selector} must define or override its glass background"
        alphas = [float(alpha) for value in backgrounds for alpha in _RGBA_ALPHA.findall(value)]
        assert alphas and max(alphas) <= limit, (selector, alphas)
        assert not any(_HEX_COLOR.search(value) for value in backgrounds), (selector, backgrounds)

    pro_backgrounds = _css_values(styles, ".pro-console", "background")
    assert any("rgba(" in value and "transparent" in value for value in pro_backgrounds)


def test_principal_glass_surfaces_keep_controlled_backdrop_blur():
    styles = (DASHBOARD / "styles.css").read_text()
    principal_surfaces = [
        ".glass-surface",
        ".detail-panel",
        ".panel-heading",
        ".pro-console",
        ".pro-console-header",
        ".pro-card",
        ".mobile-glass",
        ".topbar",
        ".workflow-nav",
    ]
    for selector in principal_surfaces:
        values = _css_values(styles, selector, "backdrop-filter")
        blur_values = [float(value) for declaration in values for value in re.findall(r"blur\(([0-9.]+)px\)", declaration)]
        assert blur_values, f"{selector} must retain backdrop blur"
        assert all(8 <= value <= 14 for value in blur_values), (selector, blur_values)


def test_nested_glass_and_safety_states_do_not_compound_into_black_slabs():
    styles = (DASHBOARD / "styles.css").read_text()

    night_root = _css_blocks(styles, ":root")[0]
    strong_value = _css_values(f":root {{{night_root}}}", ":root", "--glass-strong")[0]
    detail_alpha = float(_RGBA_ALPHA.search(strong_value).group(1))
    panel_heading_alpha = max(_background_alphas(styles, ".panel-heading"))
    decision_alpha = max(_background_alphas(styles, ".decision-surface"))
    pro_overlay_alpha = max(_background_alphas(styles, ".pro-console"))
    pro_card_alpha = max(_background_alphas(styles, ".pro-card"))
    mobile_detail_alpha = max(_background_alphas(styles, ".detail-panel"))

    nested_pairs = {
        "detail/header": (detail_alpha, panel_heading_alpha),
        "detail/decision": (detail_alpha, decision_alpha),
        "mobile-detail/decision": (mobile_detail_alpha, decision_alpha),
        "pro-console/card": (pro_overlay_alpha, pro_card_alpha),
    }
    for name, (parent, child) in nested_pairs.items():
        assert _effective_opacity(parent, child) <= 0.48, (name, parent, child)

    state_surfaces = [
        ".decision-score.blocked",
        ".planner-result.blocked",
        ".sample-warning",
        ".locked-surface",
        ".empty-state.attention",
        ".data-disclosure",
        ".data-disclosure.good",
        ".mobile-data-state",
        ".mobile-data-state.good",
    ]
    for selector in state_surfaces:
        alphas = _background_alphas(styles, selector)
        assert alphas and max(alphas) <= 0.55, (selector, alphas)
    assert not _css_values(styles, ".entitlement-locked", "background")
