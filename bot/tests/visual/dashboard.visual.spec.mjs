import { expect, test } from "@playwright/test";

const FIXED_NOW = "2026-09-04T18:30:00.000Z";
const FIXED_TIMESTAMP = "2026-09-04T18:28:00.000Z";

const lifecycle = {
  ok: true,
  timestamp: FIXED_TIMESTAMP,
  summary: {
    open_positions: 1,
    open_orders: 2,
    recent_fills: 1,
    guardrails: 0,
    management_actions: 2,
    unrealized_pl: 284.75,
    open_risk: 125,
    average_r_multiple: 1.18,
  },
  positions: [
    {
      symbol: "SPY",
      qty: 12,
      signed_qty: 12,
      side: "long",
      avg_entry_price: 641.2,
      current_price: 643.58,
      unrealized_pl: 284.75,
      stop_source: "broker",
      current_r_multiple: 1.18,
      management: [{ name: "Breakeven", status: "ready", detail: "First target protected" }],
      next_action: "Hold the planned stop and monitor target two.",
    },
  ],
  open_orders: [],
  recent_fills: [],
  guardrails: [],
  outcomes: [],
  errors: {},
  readback: "One paper position is open and inside configured limits.",
  note: "Deterministic visual-test lifecycle fixture.",
};

const dashboard = {
  ok: true,
  timestamp: FIXED_TIMESTAMP,
  dashboard_version: "v6.40.3",
  uptime_seconds: 43_200,
  execution_armed: false,
  broker: { ok: true, account_status: "ACTIVE", reason: "paper account connected" },
  paper_endpoint: true,
  positions_error: null,
  positions: lifecycle.positions,
  summary: {
    open_positions: 1,
    unrealized_pl: 284.75,
    symbols_watched: 3,
    recent_decisions: 2,
  },
  risk: {
    risk_per_trade: 0.005,
    max_dollar_risk_per_trade: 500,
    max_daily_loss_pct: 0.02,
    max_open_positions: 3,
    max_stop_pct: 0.03,
    pyramid_add_fraction: 0.5,
    lot_sizing: { enabled: true, max_lots: 4, lot_risk_fraction: 0.25 },
  },
  guardrails: {
    paper_only: true,
    time_in_force: "day",
    take_profit_r: 2,
    auth_required: true,
    approval_required: true,
    approval_mode_source: "visual fixture",
  },
  market_data: { live: true, provider: "Alpaca IEX" },
  symbols: [
    { symbol: "SPY", type: "equity", contract_multiplier: 1, session: "rth" },
    { symbol: "QQQ", type: "equity", contract_multiplier: 1, session: "rth" },
    { symbol: "AAPL", type: "equity", contract_multiplier: 1, session: "rth" },
  ],
  recent_decisions: [
    {
      alert_ref: "visual-spy-001",
      timestamp: FIXED_TIMESTAMP,
      symbol: "SPY",
      play: "Bull Elephant",
      setup: "Bull Elephant",
      side: "buy",
      status: "proposed",
      reason: "Trend, location, and risk are aligned; approval is required.",
      entry_price: 643.5,
      stop_price: 641.9,
      target_price: 646.7,
      qty: 12,
    },
    {
      alert_ref: "visual-qqq-002",
      timestamp: "2026-09-04T18:20:00.000Z",
      symbol: "QQQ",
      play: "Elephant Bar",
      setup: "Elephant Bar",
      side: "buy",
      status: "seen",
      reason: "Watching for a qualified pullback above support.",
      entry_price: 581.2,
      stop_price: 579.8,
      target_price: 584,
      qty: 8,
    },
  ],
  pending_approvals: [],
  alert_coverage: {
    ok: true,
    timestamp: FIXED_TIMESTAMP,
    stale_minutes: 240,
    symbols_csv: "SPY,QQQ,AAPL",
    summary: { symbols: 3, healthy: 3, stale: 0, never: 0 },
    rows: [],
  },
  scanner: {
    enabled: true,
    running: true,
    mode: "paper",
    last_scan_at: FIXED_TIMESTAMP,
    last_error: null,
    symbols_scanned: 3,
    signals_found: 1,
    decisions: [],
    config: { timeframe: "5Min", interval_seconds: 60, auto_submit: false },
  },
  lifecycle,
  performance: { daily_pnl: 284.75, source: "paper account" },
  apple_music: { configured: false, missing: [], token_ttl_hours: 12, origin_locked: true },
  winston: {
    brain: { provider: "winston_rule_based_v1", model: "local_guardrail_rules", configured: true, available: true, detail: "Ready" },
    voice: { provider: "pockettts", configured: true, available: true, voice: "winston", model: "tts-1", detail: "Ready" },
  },
};

const fixtures = {
  "/api/dashboard/state": dashboard,
  "/api/settings/trading-mode": { ok: true, trading_mode: "dual", timestamp: FIXED_TIMESTAMP },
  "/api/entitlements": {
    ok: true,
    tier: "pro",
    features: Object.fromEntries(
      ["advanced_readiness", "coach_intelligence", "discipline_score", "missed_trade_analysis", "performance_attribution", "pro_console", "replay_lab"].map((feature) => [feature, { allowed: true }]),
    ),
  },
  "/api/readiness": {
    ok: true,
    timestamp: FIXED_TIMESTAMP,
    score: 86,
    confidence: 92,
    label: "Plan aligned",
    authoritative_blocked: false,
    unknown_components: [],
    components: [
      { label: "Broker and lifecycle", score: 100, reason: "Paper broker and lifecycle are verified." },
      { label: "Risk discipline", score: 88, reason: "Open risk is within the configured ceiling." },
      { label: "Setup quality", score: 82, reason: "Trend and location evidence are aligned." },
      { label: "Market context", score: 76, reason: "The session is constructive but selective." },
    ],
  },
  "/api/market/context": {
    ok: true,
    timestamp: FIXED_TIMESTAMP,
    symbol: "SPY",
    regime: { label: "Bull trend" },
  },
  "/api/annotations": {
    ok: true,
    timestamp: FIXED_TIMESTAMP,
    symbol: "SPY",
    levels: [
      { label: "Planned entry", price: 643.5 },
      { label: "Protective stop", price: 641.9 },
      { label: "Target two", price: 646.7 },
    ],
  },
  "/api/pro/bootstrap": { ok: true, tier: "pro" },
  "/api/lifecycle/state": lifecycle,
  "/api/bot/health": {
    ok: true,
    timestamp: FIXED_TIMESTAMP,
    overall: "green",
    summary: "All paper-trading systems are ready.",
    dashboard_version: "v6.40.3",
    execution_armed: false,
    approval_required: true,
    components: [
      { name: "Dashboard API", ok: true, status: "online", detail: "State is current" },
      { name: "Alpaca paper", ok: true, status: "connected", detail: "Paper account active" },
    ],
  },
  "/api/alerts/coverage": dashboard.alert_coverage,
  "/api/risk/status": {
    ok: true,
    timestamp: FIXED_TIMESTAMP,
    execution_armed: false,
    approval_required: true,
    approval_mode_source: "visual fixture",
    approval_token_configured: true,
    pending_approvals: 0,
    risk: dashboard.risk,
    guardrails: dashboard.guardrails,
  },
  "/api/vps/hardening": {
    ok: true,
    timestamp: FIXED_TIMESTAMP,
    overall: "green",
    checks: [{ name: "Service supervision", ok: true, status: "ready", detail: "Restart policy verified" }],
    paths: {},
    helpers: [],
  },
  "/api/vps/latency": {
    ok: true,
    timestamp: FIXED_TIMESTAMP,
    overall: "green",
    total_latency_ms: 32,
    average_latency_ms: 16,
    worst_latency_ms: 21,
    checks: [{ name: "Dashboard", ok: true, status: "fast", latency_ms: 11, detail: "Local response" }],
    summary: "All probes are within budget.",
  },
  "/api/replay/latest": { ok: true, runs: [], summary: "Replay lab ready.", signals_found: 0, bars_loaded: 0, events: [] },
  "/api/journal/recent": {
    ok: true,
    timestamp: FIXED_TIMESTAMP,
    summary: { entries: 2, actionable: 1, blocked: 0, submitted: 0, proposed: 1, top_setup: "Bull Elephant", top_symbol: "SPY" },
    counts: { proposed: 1, seen: 1 },
    entries: dashboard.recent_decisions,
    research: [],
    replays: [],
  },
  "/api/review/daily": {
    ok: true,
    timestamp: FIXED_TIMESTAMP,
    date: "2026-09-04",
    lines: ["Two screened decisions reviewed.", "One qualified setup is awaiting approval.", "Risk remained inside the daily plan."],
    lesson: "Keep the first pullback selective and preserve the planned stop.",
    counts: { decisions: 2, actionable: 1, blocked: 0 },
  },
  "/api/review/close": {
    ok: true,
    timestamp: FIXED_TIMESTAMP,
    title: "Daily Close Report",
    summary: "Process stayed disciplined and risk remained controlled.",
    sections: {
      performance: ["Paper P/L is positive with one open position."],
      coverage: ["SPY, QQQ, and AAPL alerts are current."],
      risk: ["No guardrail breaches."],
      tomorrow: ["Wait for location before entry."],
      action_items: ["Review the SPY execution after the close."],
    },
    latest: dashboard.recent_decisions,
  },
};

fixtures["/api/desk/config"]={product:"Velez Bot",broker_provider:"alpaca",authenticated:true,tier:"Pro"};
fixtures["/api/broadcast/config"]={enabled:true,preview:true};
fixtures["/api/broadcast/market"]={ok:false,items:[],reason:"market_feed_unavailable"};
const iconStub = `
  window.lucide = {
    createIcons() {
      document.querySelectorAll("i[data-lucide]").forEach((node) => {
        const name = node.getAttribute("data-lucide") || "circle";
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("fill", "none");
        svg.setAttribute("stroke", "currentColor");
        svg.setAttribute("stroke-width", "2");
        svg.setAttribute("stroke-linecap", "round");
        svg.setAttribute("stroke-linejoin", "round");
        svg.setAttribute("aria-hidden", "true");
        svg.setAttribute("class", "lucide lucide-" + name);
        svg.innerHTML = '<circle cx="12" cy="12" r="8"></circle><path d="m8.5 12 2.3 2.3 4.7-5"></path>';
        node.replaceWith(svg);
      });
    }
  };
`;

async function installDeterministicEnvironment(page) {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.addInitScript(({ fixedNow }) => {
    const timestamp = new Date(fixedNow).valueOf();
    const NativeDate = Date;
    class FixedDate extends NativeDate {
      constructor(...args) {
        super(...(args.length ? args : [timestamp]));
      }

      static now() {
        return timestamp;
      }
    }
    window.Date = FixedDate;
    window.localStorage.clear();
    window.localStorage.setItem("velez-room-theme", "night");
  }, { fixedNow: FIXED_NOW });

  await page.route("https://unpkg.com/**", (route) => route.fulfill({ contentType: "text/javascript", body: iconStub }));
  await page.route("https://s3.tradingview.com/**", (route) => route.fulfill({ contentType: "text/javascript", body: "" }));
  await page.route("**/api/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const payload = fixtures[pathname];
    await route.fulfill({
      status: payload ? 200 : 503,
      contentType: "application/json",
      body: JSON.stringify(payload || { ok: false, reason: "No deterministic visual fixture for this endpoint." }),
    });
  });

  return pageErrors;
}

async function openDashboard(page, viewport) {
  await page.setViewportSize(viewport);
  const pageErrors = await installDeterministicEnvironment(page);
  await page.goto("/dashboard", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__deskReady === true && window.__deskDebug?.state()?.ok === true);
  await expect(page.locator("#desk-score-value")).toHaveText("86");
  await page.evaluate(async () => {
    const imageLoads = Array.from(document.images, (image) => {
      if (image.complete) return Promise.resolve();
      return new Promise((resolve) => {
        image.addEventListener("load", resolve, { once: true });
        image.addEventListener("error", resolve, { once: true });
      });
    });
    await Promise.all(imageLoads);
  });
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-delay: 0s !important;
        animation-duration: 0s !important;
        caret-color: transparent !important;
        transition-delay: 0s !important;
        transition-duration: 0s !important;
      }
      .visual-chart-fixture {
        display: grid;
        width: 100%;
        height: 100%;
        min-height: 180px;
        place-items: stretch;
        overflow: hidden;
        background:
          linear-gradient(rgba(255,255,255,.045) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px),
          linear-gradient(160deg, #101719, #071012);
        background-size: 42px 42px, 42px 42px, auto;
      }
      .visual-chart-fixture svg { width: 100%; height: 100%; }
    `,
  });
  await page.waitForFunction(()=>Boolean(document.body.dataset.roomAsset));
  return pageErrors;
}

async function installChartFixture(page, selector) {
  await page.locator(selector).evaluate((container) => {
    container.innerHTML = `
      <div class="visual-chart-fixture" aria-label="Deterministic SPY chart fixture">
        <svg viewBox="0 0 1000 420" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stop-color="#d9ad59" stop-opacity=".28" />
              <stop offset="1" stop-color="#d9ad59" stop-opacity="0" />
            </linearGradient>
          </defs>
          <path d="M0 340 L90 318 L170 326 L255 250 L335 270 L420 208 L510 226 L600 160 L690 184 L785 112 L875 134 L1000 72 L1000 420 L0 420 Z" fill="url(#area)" />
          <path d="M0 340 L90 318 L170 326 L255 250 L335 270 L420 208 L510 226 L600 160 L690 184 L785 112 L875 134 L1000 72" fill="none" stroke="#efc36e" stroke-width="5" />
          <line x1="0" y1="205" x2="1000" y2="205" stroke="#78c896" stroke-width="2" stroke-dasharray="10 9" opacity=".72" />
          <circle cx="1000" cy="72" r="9" fill="#efc36e" />
        </svg>
      </div>`;
  });
}

async function capture(page, name, pageErrors) {
  await page.evaluate(() => document.activeElement?.blur());
  const viewport = page.viewportSize();
  if (viewport) await page.mouse.move(viewport.width - 2, viewport.height - 2);
  await expect(page).toHaveScreenshot(name, { fullPage: false });
  expect(pageErrors, "dashboard must not raise uncaught errors").toEqual([]);
}

const desktop = { width: 1440, height: 900 };
const mobile = { width: 390, height: 844 };

for(const room of ["media","pacific","tokyo","manhattan","dubai"]){
 for(const theme of ["night","day"]){
  test(room+" — "+theme,async({page})=>{
   const errors=await openDashboard(page,desktop);
   await page.locator("#sovereign-room-select").selectOption(room);
   await page.evaluate(theme=>window.__deskDebug.setTheme(theme),theme);
   await page.waitForFunction(()=>document.body.dataset.roomAsset?.includes(document.body.dataset.environment==="media"?"executive":document.body.dataset.environment==="pacific"?"hawaii":document.body.dataset.environment));
   await installChartFixture(page,"#tradingview-screen");
   await capture(page,room+"-"+theme+".png",errors);
  });
 }
}
for(const [id,label] of [["laptop","Command"],["journal","Trade journal"],["drawer","Research lab"],["account","Account & access"]]){
 test("mobile "+label,async({page})=>{
  const errors=await openDashboard(page,mobile);
  await page.locator('.sovereign-dock [data-desk-action="tools"]').click();
  await page.locator('#sovereign-tools [data-desk-action="'+id+'"]').click();
  await expect(page.locator("#panel-title")).toHaveText(label);
  await capture(page,"mobile-"+id+".png",errors);
 });
}
test("desktop Pro Console remains available",async({page})=>{
 const errors=await openDashboard(page,desktop);
 await page.locator('.sovereign-dock [data-desk-action="tools"]').click();
 await page.locator('#sovereign-tools [data-desk-action="pro-console"]').click();
 await expect(page.locator("#pro-console")).toHaveAttribute("aria-hidden","false");
 await installChartFixture(page,"#pro-tradingview-screen");
 await capture(page,"desktop-pro-console-night.png",errors);
});
