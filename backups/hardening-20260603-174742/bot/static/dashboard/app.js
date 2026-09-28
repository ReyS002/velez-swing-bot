const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const PHOTO_WIDTH = 1680;
const PHOTO_HEIGHT = 945;

const roomHotspots = $("#room-hotspots");
const screenTerminal = $("#screen-terminal");
const tradingViewScreen = $("#tradingview-screen");
const chartCanvas = $("#chart-screen");
const chartCtx = chartCanvas.getContext("2d");
const panelTitle = $("#panel-title");
const panelKicker = $("#panel-kicker");
const panelBody = $("#panel-body");
const detailPanel = $("#detail-panel");
const panelClose = $("#panel-close");
const hoverTag = $("#hover-tag");
const executionPill = $("#execution-pill");
const brokerPill = $("#broker-pill");
const positionsPill = $("#positions-pill");
const themeToggle = $("#theme-toggle");
const navRevealZone = $("#nav-reveal-zone");

let activePanel = "tv";
let panelOpen = false;
let dashboardState = fallbackState();
let calendarState = null;
let calendarFetchedAt = 0;
let calendarRefreshPromise = null;
let journalState = null;
let journalRefreshPromise = null;
let healthState = null;
let healthRefreshPromise = null;
let replayState = null;
let replayRunPromise = null;
let reviewState = null;
let reviewRefreshPromise = null;
let closeReportState = null;
let closeReportRefreshPromise = null;
let coverageState = null;
let coverageRefreshPromise = null;
let lifecycleState = null;
let lifecycleRefreshPromise = null;
let riskState = null;
let riskRefreshPromise = null;
let hardeningState = null;
let hardeningRefreshPromise = null;
let latencyState = null;
let latencyRefreshPromise = null;
let tradeReviewState = null;
let tradeReviewPromise = null;
let webhookTestState = null;
let riskUpdatePromise = null;
let approvalToken = localStorage.getItem("trading-bull-approval-token") || "";
let deskNote = localStorage.getItem("trading-bull-desk-note") || "";
let watchlistDraft = { symbol: "", type: "equity" };
let tradingViewCoverageDraft = localStorage.getItem("trading-bull-tv-coverage-symbols") || "";
let chartCaptures = readLocalJson("trading-bull-chart-captures", []);
let endOfDayRitual = readLocalJson("trading-bull-eod-ritual", null);
let frame = 0;
let roomTheme = localStorage.getItem("velez-room-theme") === "day" ? "day" : "night";
let tradingViewLoaded = false;
let tradingViewTimer = null;
let appleMusicScriptPromise = null;
let appleMusicInstance = null;
let appleMusicReadyPromise = null;
let appleMusicPollTimer = null;

const APPLE_MUSIC_URL = "https://music.apple.com/us/browse";
const APPLE_MUSIC_FOCUS_URL = "https://music.apple.com/us/search?term=focus%20trading";
const APPLE_MUSIC_SCRIPT_URL = "https://js-cdn.music.apple.com/musickit/v3/musickit.js";
const APP_BUILD = "v6.21";
const tradingViewSymbols = [
  { label: "SPY", symbol: "AMEX:SPY" },
  { label: "QQQ", symbol: "NASDAQ:QQQ" },
];
const savedTradingViewSymbol = localStorage.getItem("velez-tv-symbol");
let tradingViewSymbol = tradingViewSymbols.some((item) => item.symbol === savedTradingViewSymbol) ? savedTradingViewSymbol : "AMEX:SPY";

const appleMusicState = {
  status: "idle",
  authorized: false,
  ready: false,
  message: "Ready to connect",
  expiresAt: null,
  nowPlaying: null,
  playback: {
    isPlaying: false,
    currentTime: 0,
    duration: 0,
    progress: 0,
    volume: 1,
  },
  searchTerm: localStorage.getItem("trading-bull-music-search") || "trading focus",
  searchStatus: "idle",
  searchMessage: "Search Apple Music from the desk",
  searchResults: [],
};

const SpeechRecognitionApi = window.SpeechRecognition || window.webkitSpeechRecognition;
const winstonState = {
  callActive: false,
  muted: false,
  listening: false,
  speaking: false,
  status: "idle",
  message: "Phone line ready",
  speechRequestId: 0,
  audio: null,
  brain: {
    provider: "winston_rule_based_v1",
    model: "local_guardrail_rules",
    configured: true,
    available: true,
    detail: "Safe local Winston responses",
  },
  voice: {
    provider: "browser",
    configured: true,
    available: true,
    voice: "browser_default",
    model: "Web Speech API",
    detail: "Browser speech synthesis fallback",
  },
  transcript: [
    {
      role: "winston",
      text: "Phone line is ready. Start a call for the daily brief, watchlist status, risk readback, or guarded trade approval checks.",
      timestamp: new Date().toISOString(),
    },
  ],
  recognition: null,
};

const palette = {
  ink: "#f4f1e8",
  muted: "#aeb8b0",
  green: "#68c783",
  red: "#e46b61",
  amber: "#e2aa4b",
  blue: "#93c8ff",
  grid: "rgba(244, 241, 232, 0.12)",
};

const panelCopy = {
  tv: ["TradingView | V6.21", "Trading Screen"],
  mission: ["Daily mission | V6.21", "Mission Card"],
  laptop: ["Command center | V6.21", "Bot Console"],
  journal: ["Journal + lifecycle | V6.21", "Trade Journal"],
  calendar: ["Daily prep | V6.21", "Calendar"],
  safe: ["Approval inbox | V6.21", "Safe"],
  music: ["Apple Music | V6.21", "Music"],
  phone: ["Winston lifecycle line | V6.21", "Desk Phone"],
  bookshelf: ["Strategy library | V6.21", "Bookshelf"],
  clock: ["Market sessions | V6.21", "Desk Clock"],
  window: ["Market weather | V6.21", "Window View"],
  lamp: ["Risk command | V6.21", "Desk Lamp"],
  drawer: ["Backtest lab | V6.21", "Desk Drawer"],
  notes: ["Bull Report | V6.21", "Bull Report"],
};

const screenRegion = { x: 0.348, y: 0.413, w: 0.296, h: 0.233 };
const hotspotDefinitions = [
  { panel: "laptop", label: "Command center", icon: "laptop", x: 0.365, y: 0.714, w: 0.31, h: 0.13 },
  { panel: "mission", label: "Daily mission", icon: "target", x: 0.45, y: 0.615, w: 0.12, h: 0.075 },
  { panel: "journal", label: "Trade journal", icon: "book-open", x: 0.72, y: 0.735, w: 0.14, h: 0.105 },
  { panel: "calendar", label: "Calendar and P/L", icon: "calendar-days", x: 0.69, y: 0.58, w: 0.09, h: 0.1 },
  { panel: "safe", label: "Credential safe", icon: "shield-check", x: 0.845, y: 0.565, w: 0.075, h: 0.18 },
  { panel: "music", label: "Music", icon: "music", x: 0.222, y: 0.758, w: 0.09, h: 0.085 },
  { panel: "phone", label: "Call Winston", icon: "phone-call", x: 0.192, y: 0.575, w: 0.068, h: 0.17 },
  { panel: "bookshelf", label: "Strategy library", icon: "library", x: 0.025, y: 0.13, w: 0.125, h: 0.36 },
  { panel: "clock", label: "Market sessions", icon: "clock", x: 0.795, y: 0.13, w: 0.08, h: 0.12 },
  { panel: "window", label: "Market weather", icon: "cloud-sun", x: 0.34, y: 0.12, w: 0.32, h: 0.24 },
  { panel: "lamp", label: "Risk mood light", icon: "lamp", x: 0.155, y: 0.355, w: 0.095, h: 0.115 },
  { panel: "drawer", label: "Backtest drawer", icon: "archive", x: 0.67, y: 0.825, w: 0.28, h: 0.135 },
  { panel: "notes", label: "Bull Report", icon: "file-text", x: 0.88, y: 0.44, w: 0.105, h: 0.12 },
];

function fallbackState() {
  return {
    ok: false,
    timestamp: new Date().toISOString(),
    uptime_seconds: 0,
    execution_armed: false,
    broker: { ok: false, reason: "loading" },
    paper_endpoint: true,
    positions: [],
    positions_error: null,
    summary: {
      open_positions: 0,
      unrealized_pl: 0,
      symbols_watched: 0,
      recent_decisions: 0,
    },
    risk: {
      risk_per_trade: 0.005,
      max_dollar_risk_per_trade: 1000,
      max_daily_loss_pct: 0.02,
      max_open_positions: 3,
      max_stop_pct: 0.1,
      pyramid_add_fraction: 0.5,
    },
    guardrails: {
      paper_only: true,
      time_in_force: "day",
      take_profit_r: null,
      auth_required: true,
      approval_required: false,
      approval_mode_source: "environment",
    },
    symbols: [{ symbol: "SPY", type: "equity", contract_multiplier: 1, session: "rth" }],
    recent_decisions: [],
    pending_approvals: [],
    alert_coverage: {
      ok: false,
      timestamp: new Date().toISOString(),
      stale_minutes: 240,
      symbols_csv: "SPY",
      summary: { symbols: 1, healthy: 0, stale: 0, never: 1 },
      rows: [],
    },
    scanner: {
      enabled: false,
      running: false,
      mode: "loading",
      last_scan_at: null,
      last_error: null,
      symbols_scanned: 0,
      signals_found: 0,
      decisions: [],
      config: {
        timeframe: "1Min",
        interval_seconds: 60,
        auto_submit: false,
        futures_provider: "polygon",
        futures_configured: false,
        futures_contracts: {},
        note: "Scanner loading.",
      },
    },
    lifecycle: {
      ok: false,
      timestamp: new Date().toISOString(),
      summary: { open_positions: 0, open_orders: 0, recent_fills: 0, guardrails: 0, management_actions: 0, unrealized_pl: 0, open_risk: 0, average_r_multiple: null },
      positions: [],
      open_orders: [],
      recent_fills: [],
      guardrails: [],
      outcomes: [],
      errors: {},
      readback: "Lifecycle reconciliation is loading.",
      note: "Broker lifecycle API loading.",
    },
    apple_music: {
      configured: false,
      missing: ["APPLE_MUSIC_TEAM_ID", "APPLE_MUSIC_KEY_ID", "APPLE_MUSIC_PRIVATE_KEY_PATH"],
      key_id_tail: "",
      team_id_tail: "",
      token_ttl_hours: 12,
      origin_locked: false,
    },
    winston: {
      brain: {
        provider: "winston_rule_based_v1",
        model: "local_guardrail_rules",
        configured: true,
        available: true,
        detail: "Safe local Winston responses",
      },
      voice: {
        provider: "browser",
        configured: true,
        available: true,
        voice: "browser_default",
        model: "Web Speech API",
        detail: "Browser speech synthesis fallback",
      },
    },
  };
}

function fallbackCalendarState() {
  const now = new Date();
  return {
    ok: false,
    timestamp: now.toISOString(),
    range: {
      start: "",
      end: "",
      lookahead_end: "",
      month_label: now.toLocaleString("en-US", { month: "long", year: "numeric" }),
      timezone: "America/New_York",
    },
    pnl: {
      month_pl: 0,
      unrealized_pl: dashboardState?.summary?.unrealized_pl || 0,
      equity_change: 0,
      detail: "Calendar feed loading",
    },
    alerts: {
      count: dashboardState?.summary?.recent_decisions || 0,
      by_day: {},
      recent: [],
      source: "session_journal",
    },
    session: {
      status: "Loading",
      label: "Checking market calendar",
    },
    sessions: [],
    earnings: [],
    events: [],
    journal: {
      status: "Monthly journal lane ready",
      sessions_logged: 0,
      recent_count: 0,
    },
    sources: {},
  };
}

function currentCalendarState() {
  return calendarState || fallbackCalendarState();
}

function fallbackJournalState() {
  return {
    ok: false,
    timestamp: dashboardState.timestamp,
    summary: {
      entries: dashboardState.recent_decisions?.length || 0,
      actionable: (dashboardState.recent_decisions || []).filter((item) => ["proposed", "submitted"].includes(item.status)).length,
      blocked: (dashboardState.recent_decisions || []).filter((item) => ["rejected", "ignored", "error"].includes(item.status)).length,
      submitted: 0,
      proposed: 0,
      top_setup: "Loading",
      top_symbol: "Loading",
    },
    counts: {},
    entries: dashboardState.recent_decisions || [],
    research: [],
    replays: [],
  };
}

function currentJournalState() {
  return journalState || fallbackJournalState();
}

function fallbackHealthState() {
  return {
    ok: false,
    timestamp: dashboardState.timestamp,
    overall: dashboardState.broker?.ok ? "yellow" : "red",
    summary: dashboardState.broker?.ok ? "Health API loading" : "Broker check needed",
    dashboard_version: dashboardState.dashboard_version || APP_BUILD,
    execution_armed: dashboardState.execution_armed,
    approval_required: false,
    components: [
      { name: "Dashboard API", ok: Boolean(dashboardState.ok), status: dashboardState.ok ? "online" : "loading", detail: "Waiting for bot health endpoint" },
      { name: "Alpaca paper", ok: Boolean(dashboardState.broker?.ok), status: dashboardState.broker?.ok ? "connected" : "needs check", detail: dashboardState.broker?.reason || dashboardState.broker?.account_status || "" },
    ],
  };
}

function currentHealthState() {
  return healthState || fallbackHealthState();
}

function fallbackReplayState() {
  return {
    ok: false,
    runs: [],
    summary: "Replay has not been run yet.",
    signals_found: 0,
    bars_loaded: 0,
    events: [],
  };
}

function currentReplayState() {
  return replayState || fallbackReplayState();
}

function fallbackReviewState() {
  const journal = currentJournalState();
  const entries = journal.entries || [];
  const actionable = entries.filter((item) => ["proposed", "submitted"].includes(item.status));
  const blocked = entries.filter((item) => ["rejected", "ignored", "error"].includes(item.status));
  return {
    ok: false,
    timestamp: dashboardState.timestamp,
    date: new Date().toISOString().slice(0, 10),
    lines: [
      `${entries.length} recent journal decision${entries.length === 1 ? "" : "s"} in view.`,
      `${actionable.length} actionable, ${blocked.length} blocked or ignored.`,
      `Watchlist: ${(dashboardState.symbols || []).map((item) => item.symbol).filter(Boolean).join(", ") || "No symbols configured"}.`,
    ],
    lesson: "Stay patient until structure, location, and risk are all aligned.",
    counts: {
      decisions: entries.length,
      actionable: actionable.length,
      blocked: blocked.length,
    },
  };
}

function currentReviewState() {
  return reviewState || fallbackReviewState();
}

function fallbackCloseReportState() {
  const review = currentReviewState();
  return {
    ok: false,
    timestamp: dashboardState.timestamp,
    title: "Daily Close Report",
    summary: review.summary || (review.lines || []).join(" "),
    sections: {
      performance: review.lines || [],
      coverage: ["Alert coverage loading."],
      risk: ["Risk status loading."],
      tomorrow: [dailyMission().rule],
      action_items: ["Close report API loading."],
    },
    latest: [],
  };
}

function currentCloseReportState() {
  return closeReportState || fallbackCloseReportState();
}

function fallbackCoverageState() {
  const rows = (dashboardState.symbols || []).map((item) => {
    const latest = (dashboardState.recent_decisions || []).find((decision) => decision.symbol === item.symbol);
    return {
      symbol: item.symbol,
      type: item.type || "equity",
      enabled: item.enabled !== false,
      status: latest ? "stale" : "never",
      detail: latest ? `Last alert ${timeAgo(latest.timestamp)}` : "No alert seen in this browser state",
      age_seconds: null,
      last_alert: latest || null,
    };
  });
  return {
    ok: false,
    timestamp: dashboardState.timestamp,
    stale_minutes: 240,
    symbols_csv: rows.map((item) => item.symbol).join(","),
    summary: {
      symbols: rows.length,
      healthy: 0,
      stale: rows.filter((item) => item.last_alert).length,
      never: rows.filter((item) => !item.last_alert).length,
    },
    rows,
    note: "Coverage API loading.",
  };
}

function currentCoverageState() {
  return coverageState || dashboardState.alert_coverage || fallbackCoverageState();
}

function fallbackLifecycleState() {
  const openPositions = dashboardState?.positions || [];
  const unrealized = dashboardState?.summary?.unrealized_pl || 0;
  return {
    ok: false,
    timestamp: dashboardState?.timestamp || new Date().toISOString(),
    summary: {
      open_positions: openPositions.length,
      open_orders: 0,
      recent_fills: 0,
      guardrails: 0,
      management_actions: 0,
      unrealized_pl: unrealized,
      open_risk: 0,
      average_r_multiple: null,
    },
    positions: openPositions.map((item) => ({
      symbol: item.symbol,
      qty: item.qty,
      signed_qty: Number(item.qty || 0),
      side: item.side || "long",
      avg_entry_price: item.avg_entry_price,
      current_price: item.current_price,
      unrealized_pl: item.unrealized_pl,
      stop_source: "loading",
      current_r_multiple: null,
      management: [{ name: "Lifecycle", status: "watch", detail: "Broker reconciliation is loading." }],
      next_action: "Run lifecycle reconciliation from the command center.",
    })),
    open_orders: [],
    recent_fills: [],
    guardrails: [],
    outcomes: [],
    errors: {},
    readback: "Lifecycle reconciliation is loading.",
    note: "Broker lifecycle API loading.",
  };
}

function currentLifecycleState() {
  return lifecycleState || dashboardState.lifecycle || fallbackLifecycleState();
}

function fallbackRiskState() {
  return {
    ok: false,
    timestamp: dashboardState.timestamp,
    execution_armed: dashboardState.execution_armed,
    approval_required: Boolean(dashboardState.guardrails?.approval_required),
    approval_mode_source: dashboardState.guardrails?.approval_mode_source || "environment",
    approval_token_configured: false,
    pending_approvals: dashboardState.pending_approvals?.length || 0,
    risk: dashboardState.risk || {},
    guardrails: dashboardState.guardrails || {},
  };
}

function currentRiskState() {
  return riskState || fallbackRiskState();
}

function fallbackHardeningState() {
  return {
    ok: false,
    timestamp: dashboardState.timestamp,
    overall: "loading",
    checks: [
      { name: "VPS hardening", ok: false, status: "loading", detail: "Checking restart, backup, and heartbeat helpers" },
    ],
    paths: {},
    helpers: [],
  };
}

function currentHardeningState() {
  return hardeningState || fallbackHardeningState();
}

function fallbackLatencyState() {
  return {
    ok: false,
    timestamp: dashboardState.timestamp,
    overall: "loading",
    total_latency_ms: 0,
    average_latency_ms: 0,
    worst_latency_ms: 0,
    checks: [
      { name: "Latency monitor", ok: false, status: "loading", latency_ms: 0, detail: "Checking VPS probes" },
    ],
    summary: "Latency API loading.",
  };
}

function currentLatencyState() {
  return latencyState || fallbackLatencyState();
}

function currentTradeReviewState() {
  return tradeReviewState;
}

function readLocalJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (error) {
    return fallback;
  }
}

function tradingDayKey(value = new Date()) {
  return etParts(value).date;
}

function todaysRitual() {
  if (!endOfDayRitual?.timestamp) return null;
  const ritualDay = endOfDayRitual.date || tradingDayKey(new Date(endOfDayRitual.timestamp));
  return ritualDay === tradingDayKey() ? endOfDayRitual : null;
}

const strategyShelf = [
  {
    title: "Elephant Bar",
    tag: "Institutional ignition",
    rule: "Dominant body, tiny wicks, clears structure near the 20 SMA or 200 SMA.",
    action: "Enter close if it clears; use 50% body pullback when climactic.",
  },
  {
    title: "Bull / Bear 180",
    tag: "Two-bar trap",
    rule: "Bar 2 must recover 80-100% of Bar 1 at a key moving average.",
    action: "Stop goes one tick beyond the two-bar sequence.",
  },
  {
    title: "Tails",
    tag: "Failed auction",
    rule: "Top or bottom tail must be at least 66% of the full candle range.",
    action: "Use only after extension or at a major moving average test.",
  },
  {
    title: "Pyramiding",
    tag: "Add only to winners",
    rule: "No losing adds. New add equals 50% of the current held size.",
    action: "Only add after risk is mitigated and pullback volume fades.",
  },
  {
    title: "No Chasing",
    tag: "Location discipline",
    rule: "If price moves more than 5% past the trigger body, wait.",
    action: "Queue a 50% retracement entry or stand down.",
  },
  {
    title: "Opening Gap Go",
    tag: "Open control",
    rule: "Qualified gap plus first-bar control and clean space beyond prior structure.",
    action: "Use the opening range as the stop anchor and respect gap size limits.",
  },
  {
    title: "Opening Gap Fade",
    tag: "Gap-fill trap",
    rule: "Gap rejects into extension, 200 SMA pressure, or nearby structure.",
    action: "Trade back toward prior close only when gap-fill space remains.",
  },
  {
    title: "Time + Space",
    tag: "Opening range",
    rule: "Small-gap open breaks the first range with clear room before obstacles.",
    action: "Score time, clean space, location, and range quality before entry.",
  },
];

function etParts(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
    .formatToParts(date)
    .reduce((acc, part) => {
      if (part.type !== "literal") acc[part.type] = part.value;
      return acc;
    }, {});
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: Number(parts.hour) * 60 + Number(parts.minute),
    label: `${parts.hour}:${parts.minute} ET`,
  };
}

function minutesFromClock(value) {
  const match = String(value || "").match(/(\d{1,2}):(\d{2})/);
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2]);
}

function durationLabel(minutes) {
  const abs = Math.max(0, Math.round(Number(minutes) || 0));
  const hours = Math.floor(abs / 60);
  const mins = abs % 60;
  if (hours && mins) return `${hours}h ${mins}m`;
  if (hours) return `${hours}h`;
  return `${mins}m`;
}

function marketClock() {
  const calendar = currentCalendarState();
  const session = calendar.session || {};
  const now = etParts();
  const currentSession = (calendar.sessions || []).find((item) => item.date === now.date) || {};
  const open = minutesFromClock(currentSession.open || "09:30");
  const close = minutesFromClock(currentSession.close || "16:00");
  let phase = session.status || "Checking";
  let next = session.label || "Session feed loading";
  if (currentSession.date && open !== null && close !== null) {
    if (now.minutes < open) {
      phase = "Pre-market";
      next = `Open in ${durationLabel(open - now.minutes)}`;
    } else if (now.minutes <= close) {
      phase = "Market open";
      next = `Close in ${durationLabel(close - now.minutes)}`;
    } else {
      phase = "After-hours";
      next = "Regular session closed";
    }
  }
  return {
    now: now.label,
    phase,
    next,
    session: session.label || currentSession.label || "09:30-16:00 ET",
    date: session.date || now.date,
  };
}

function riskMood() {
  const health = currentHealthState();
  const brokerOk = Boolean(dashboardState.broker?.ok);
  const armed = Boolean(dashboardState.execution_armed);
  const openPositions = Number(dashboardState.summary?.open_positions || dashboardState.positions?.length || 0);
  const maxPositions = Number(dashboardState.risk?.max_open_positions || 0);
  const openRisk = Number(dashboardState.summary?.unrealized_pl || 0);
  if (!brokerOk || health.overall === "red") {
    return { tone: "danger", label: "Red", headline: "Protective mode", detail: "Broker or core health needs attention before trusting automation." };
  }
  if ((maxPositions && openPositions >= maxPositions) || openRisk < 0 || !armed || health.overall === "yellow") {
    return { tone: "caution", label: "Amber", headline: "Caution light", detail: "Stay selective. Review open exposure, health, and upcoming calendar risk." };
  }
  return { tone: "calm", label: "Green", headline: "Calm desk", detail: "Core services are connected and the paper endpoint is locked." };
}

function marketWeather() {
  const calendar = currentCalendarState();
  const health = currentHealthState();
  const mood = riskMood();
  const highEvent = (calendar.timeline || calendar.events || []).find((item) => String(item.importance || "").toLowerCase() === "high");
  if (mood.tone === "danger") {
    return { tone: "storm", label: "Storm watch", detail: "Operational health is the main market-weather input right now.", icon: "cloud-lightning" };
  }
  if (highEvent) {
    return { tone: "mixed", label: "Event risk", detail: `${calendarDate(highEvent.date)} | ${highEvent.title || highEvent.symbol}`, icon: "cloud-sun" };
  }
  if (health.overall === "green" && dashboardState.execution_armed) {
    return { tone: "clear", label: "Clear watch", detail: "No high-impact calendar item is leading the current timeline.", icon: "sun" };
  }
  return { tone: "haze", label: "Neutral tape", detail: "Desk state is usable, but still waiting for stronger context.", icon: "cloud" };
}

function parseCalendarDateTime(item) {
  if (!item?.date) return null;
  const rawTime = String(item.time || "09:30").trim();
  let hours = 9;
  let minutes = 30;
  const match = rawTime.match(/(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?/i);
  if (match) {
    hours = Number(match[1]);
    minutes = Number(match[2] || 0);
    const meridian = String(match[3] || "").toUpperCase();
    if (meridian === "PM" && hours < 12) hours += 12;
    if (meridian === "AM" && hours === 12) hours = 0;
  }
  const [year, month, day] = String(item.date).split("-").map(Number);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day, hours, minutes);
}

function nextDeskEvent() {
  const calendar = currentCalendarState();
  const now = Date.now();
  const items = [...(calendar.timeline || []), ...(calendar.events || []), ...(calendar.earnings || [])]
    .map((item) => ({ ...item, when: parseCalendarDateTime(item) }))
    .filter((item) => item.when && item.when.getTime() >= now)
    .sort((a, b) => a.when.getTime() - b.when.getTime());
  return items[0] || null;
}

function countdownLabel(item) {
  if (!item?.when) return "No countdown";
  const diff = item.when.getTime() - Date.now();
  if (diff <= 0) return "Now";
  const minutes = Math.round(diff / 60000);
  if (minutes < 90) return `${minutes}m`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)}h`;
  return `${Math.round(minutes / (60 * 24))}d`;
}

function eventCountdownState() {
  const event = nextDeskEvent();
  if (!event) {
    return {
      label: "No event loaded",
      detail: "Calendar has no upcoming macro or earnings item in view.",
      tone: "calm",
      minutes: null,
    };
  }
  const minutes = Math.round((event.when.getTime() - Date.now()) / 60000);
  const tone = minutes <= 5 ? "danger" : minutes <= 30 ? "caution" : String(event.importance || "").toLowerCase() === "high" ? "caution" : "calm";
  return {
    event,
    label: countdownLabel(event),
    detail: `${calendarDate(event.date)} ${event.time || ""} | ${event.title || event.symbol || "Event"}`,
    tone,
    minutes,
  };
}

function dailyMission() {
  const clock = marketClock();
  const countdown = eventCountdownState();
  const mood = riskMood();
  const weather = marketWeather();
  const pending = dashboardState.pending_approvals || [];
  const rule = mood.tone === "danger"
    ? "Fix readiness before taking risk."
    : countdown.tone !== "calm"
      ? "Respect event risk. Size down or stand aside."
      : "Only trade clean location: 20 SMA, extension, or 200 SMA.";
  return {
    title: clock.phase === "Market open" ? "Execute with patience" : "Prep, review, protect",
    clock,
    countdown,
    mood,
    weather,
    rule,
    pending,
    watchlist: (dashboardState.symbols || []).map((item) => item.symbol).filter(Boolean),
  };
}

function watchlistHeat() {
  const decisions = dashboardState.recent_decisions || [];
  const clock = marketClock();
  return (dashboardState.symbols || []).map((item) => {
    const latest = decisions.find((decision) => decision.symbol === item.symbol);
    let tone = "neutral";
    let label = "No setup";
    let detail = clock.phase;
    if (latest) {
      const status = String(latest.status || "").toLowerCase();
      if (["submitted", "proposed"].includes(status)) {
        tone = "hot";
        label = latest.play || "Actionable";
      } else if (["rejected", "ignored", "error"].includes(status)) {
        tone = "blocked";
        label = "Blocked";
      } else {
        tone = "watch";
        label = latest.play || latest.reason || "Watching";
      }
      detail = `${latest.reason || status} | ${timeAgo(latest.timestamp)}`;
    }
    return { ...item, tone, label, detail };
  });
}

function renderWatchlistHeatStrip() {
  const heat = watchlistHeat();
  if (!heat.length) return `<div class="empty-state compact">No watchlist symbols configured.</div>`;
  return `
    <div class="heat-strip">
      ${heat
        .map(
          (item) => `
            <button class="heat-chip ${escapeHtml(item.tone)}" type="button" data-open-panel="tv" title="${escapeHtml(item.detail)}">
              <strong>${escapeHtml(item.symbol)}</strong>
              <span>${escapeHtml(item.label)}</span>
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

function plannedTradingViewSymbols() {
  return new Set(
    String(tradingViewCoverageDraft || "")
      .split(/[\s,]+/)
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean),
  );
}

function coverageTone(status) {
  if (status === "healthy") return "good";
  if (status === "stale") return "warn";
  return "bad";
}

function renderAlertCoveragePanel() {
  const coverage = currentCoverageState();
  const rows = coverage.rows || [];
  const planned = plannedTradingViewSymbols();
  const uncovered = rows.filter((item) => !planned.has(String(item.symbol || "").toUpperCase()));
  const summary = coverage.summary || {};
  const testLabel = webhookTestState?.message || (webhookTestState?.reason ? `Test blocked: ${webhookTestState.reason}` : "No dry-run test yet");
  return `
    <section class="tool-section">
      <div class="section-title">Alert coverage</div>
      <div class="metric-grid">
        ${metric("Bot watchlist", summary.symbols ?? rows.length, "Trading Bull Desk symbols")}
        ${metric("TV group", planned.size || 0, uncovered.length ? `${uncovered.length} not marked covered` : "Marked covered")}
        ${metric("Recent alerts", summary.healthy || 0, `${summary.stale || 0} stale | ${summary.never || 0} never`)}
        ${metric("Coverage", `${summary.coverage_score || 0}%`, `${summary.payload_current || 0} payloads current`)}
        ${metric("Pipe test", webhookTestState?.ok ? "Passed" : "Ready", testLabel)}
      </div>
      <form class="coverage-form" id="coverage-form">
        <label for="coverage-symbols">TradingView Watchlist Alert symbols</label>
        <textarea id="coverage-symbols" rows="2" spellcheck="false" placeholder="SPY, QQQ, TQQQ">${escapeHtml(tradingViewCoverageDraft)}</textarea>
        <div class="actions">
          <button class="symbol-button" type="button" data-copy-watchlist><i data-lucide="copy"></i> Use bot watchlist</button>
          <button class="symbol-button" type="submit"><i data-lucide="save"></i> Save coverage list</button>
          <button class="action-button" type="button" data-webhook-test ${approvalToken ? "" : "disabled"}><i data-lucide="radio-tower"></i> Test webhook pipe</button>
          <button class="symbol-button" type="button" data-coverage-refresh><i data-lucide="refresh-cw"></i> Refresh coverage</button>
        </div>
      </form>
      <div class="coverage-list">
        ${
          rows.length
            ? rows
                .map((item) => {
                  const symbol = String(item.symbol || "").toUpperCase();
                  const plannedText = planned.has(symbol) ? "TV group" : "Not marked";
                  const latest = item.last_alert || {};
                  const checklist = item.checklist || [];
                  return `
                    <article class="health-card ${coverageTone(item.status)}">
                      <div>
                        <strong>${escapeHtml(symbol || "Symbol")}</strong>
                        <span>${escapeHtml([plannedText, latest.play || latest.reason || item.detail, latest.timeframe].filter(Boolean).join(" | "))}</span>
                        ${
                          checklist.length
                            ? `<span>${escapeHtml(checklist.map((check) => `${check.ok ? "OK" : "Review"} ${check.name}`).slice(0, 3).join(" | "))}</span>`
                            : ""
                        }
                      </div>
                      <small>${escapeHtml(item.status === "healthy" ? timeAgo(latest.timestamp) : `${item.status || "unknown"} | ${item.coverage_score || 0}/5`)}</small>
                    </article>
                  `;
                })
                .join("")
            : `<div class="empty-state compact">Add symbols to the bot watchlist, then mark the TradingView Watchlist Alert group here.</div>`
        }
      </div>
      <div class="empty-state compact">${escapeHtml(coverage.note || "TradingView still owns the actual watchlist alert; this confirms what has reached the bot.")}</div>
    </section>
  `;
}

function renderScannerPanel() {
  const scanner = dashboardState.scanner || {};
  const config = scanner.config || {};
  const decisions = scanner.decisions || [];
  const statusLabel = scanner.enabled ? (scanner.running ? "Running" : "Stopped") : "Disabled";
  const modeLabel = scanner.mode || "unknown";
  const detail = scanner.last_error || config.note || "VPS scanner watches newly closed bars from the bot watchlist.";
  return `
    <section class="tool-section">
      <div class="section-title">Hybrid VPS scanner</div>
      <div class="metric-grid">
        ${metric("Scanner", statusLabel, modeLabel)}
        ${metric("Timeframe", config.timeframe || "1Min", `${config.interval_seconds || 60}s interval`)}
        ${metric("Last scan", scanner.last_scan_at ? timeAgo(scanner.last_scan_at) : "Warming", `${scanner.symbols_scanned || 0} lanes`)}
        ${metric("Futures", config.futures_configured ? "Polygon on" : "Key needed", config.futures_provider || "polygon")}
        ${metric("Signals", scanner.signals_found || 0, config.auto_submit ? "Routes to paper guardrails" : "Diagnostic only")}
      </div>
      <div class="data-list">
        ${row("Mode", scanner.enabled ? "TradingView + VPS scanner" : "TradingView only")}
        ${row("Supported", (config.supported_assets || ["equity", "crypto"]).join(", "))}
        ${row("Futures map", Object.entries(config.futures_contracts || {}).map(([key, value]) => `${key}->${value}`).join(", ") || "Not configured")}
        ${row("Guardrail", "Uses the same Velez sizing/risk engine as webhooks")}
        ${row("Readback", detail)}
      </div>
      ${
        decisions.length
          ? `<div class="coverage-list">${decisions
              .map(
                (item) => `
                  <article class="health-card ${coverageTone(item.status === "submitted" || item.status === "proposed" ? "healthy" : item.status === "ignored" ? "stale" : "never")}">
                    <div>
                      <strong>${escapeHtml(item.symbol || "Scanner")}</strong>
                      <span>${escapeHtml([item.play || item.reason, item.side, item.status].filter(Boolean).join(" | "))}</span>
                    </div>
                    <small>${escapeHtml(item.timestamp ? timeAgo(item.timestamp) : "new")}</small>
                  </article>
                `,
              )
              .join("")}</div>`
          : `<div class="empty-state compact">Scanner is warming up. It ignores old candles and only acts on newly closed bars after startup.</div>`
      }
    </section>
  `;
}

function renderApprovalInbox() {
  const pending = dashboardState.pending_approvals || [];
  if (!pending.length) return `<div class="empty-state compact">No staged paper order is waiting for approval.</div>`;
  return `
    <div class="approval-list">
      ${pending
        .map(
          (item) => `
            <article class="approval-card">
              <strong>${escapeHtml(approvalLine(item))}</strong>
              <span>${escapeHtml(`Phrase: ${item.approval_phrase || "not staged"}`)}</span>
              <span>${escapeHtml(`Expires ${expiresIn(item.expires_at)} | ${item.decision_alert_ref || "local alert"}`)}</span>
              <button class="symbol-button" type="button" data-open-panel="phone"><i data-lucide="phone-call"></i> Open phone approval</button>
              <button class="action-button" type="button" data-approve-order="${escapeHtml(item.id)}" data-approve-phrase="${escapeHtml(item.approval_phrase)}">
                <i data-lucide="shield-check"></i>
                <span>Approve Paper</span>
              </button>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function deskPrepLines() {
  const calendar = currentCalendarState();
  const clock = marketClock();
  const latest = latestDecision();
  const pending = dashboardState.pending_approvals || [];
  const events = calendar.timeline || calendar.events || [];
  return [
    `${clock.phase}: ${clock.next}`,
    `Watchlist: ${(dashboardState.symbols || []).map((item) => item.symbol).filter(Boolean).join(", ") || "No symbols configured"}`,
    events[0] ? `Next event: ${calendarDate(events[0].date)} | ${events[0].title || events[0].symbol}` : "No calendar event loaded",
    latest ? `Latest alert: ${latest.symbol || "Symbol"} ${latest.play || latest.reason || "decision"} ${timeAgo(latest.timestamp)}` : "No TradingView alert in journal yet",
    pending.length ? `${pending.length} approval pending` : "No paper approval pending",
  ];
}

function chartCaptureSummary() {
  if (!chartCaptures.length) return "No browser chart capture saved yet";
  const latest = chartCaptures[0];
  return `${latest.symbol || "Chart"} captured ${timeAgo(latest.timestamp)}`;
}

function captureCurrentChart() {
  try {
    const dataUrl = chartCanvas.toDataURL("image/png");
    const capture = {
      id: `${Date.now()}`,
      timestamp: new Date().toISOString(),
      symbol: tradingViewLabel(),
      source: tradingViewLoaded ? "desk_canvas_with_tradingview_overlay" : "desk_canvas_fallback",
      dataUrl,
    };
    chartCaptures = [capture, ...chartCaptures].slice(0, 8);
    localStorage.setItem("trading-bull-chart-captures", JSON.stringify(chartCaptures));
    winstonTranscript("system", "Chart capture saved in this browser.");
  } catch (error) {
    winstonTranscript("system", `Chart capture blocked: ${error?.message || "browser security"}.`);
  }
  renderPanel();
}

function renderChartCaptureLane() {
  const latest = chartCaptures[0];
  return `
    <section class="tool-section">
      <div class="section-title">Trade screenshot capture</div>
      <div class="data-list compact-list">
        ${row("Latest capture", chartCaptureSummary())}
        ${row("TradingView iframe", "Browser security prevents server-side iframe screenshots")}
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-chart-capture><i data-lucide="camera"></i> Capture desk chart</button>
        ${latest?.dataUrl ? `<a class="symbol-button" href="${latest.dataUrl}" download="trading-bull-chart-${escapeHtml(latest.id)}.png"><i data-lucide="download"></i> Download latest</a>` : ""}
      </div>
    </section>
  `;
}

function generateEndOfDayReview() {
  const review = currentReviewState();
  const mission = dailyMission();
  return {
    timestamp: new Date().toISOString(),
    date: tradingDayKey(),
    status: "locked",
    summary: review.lines?.join(" ") || review.summary || "Daily review saved.",
    lesson: review.lesson || mission.rule,
    risk: riskMood().headline,
    capture: chartCaptureSummary(),
  };
}

function completeEndOfDayRitual() {
  endOfDayRitual = generateEndOfDayReview();
  localStorage.setItem("trading-bull-eod-ritual", JSON.stringify(endOfDayRitual));
  winstonTranscript("system", "End-of-day ritual locked for this browser.");
  renderPanel();
  updateActiveChrome();
}

function resetEndOfDayRitual() {
  endOfDayRitual = null;
  localStorage.removeItem("trading-bull-eod-ritual");
  winstonTranscript("system", "End-of-day ritual reopened.");
  renderPanel();
  updateActiveChrome();
}

function renderEventCountdownCard() {
  const countdown = eventCountdownState();
  return `
    <section class="tool-section">
      <div class="section-title">Market event countdown</div>
      <div class="mood-card ${escapeHtml(countdown.tone)} countdown-card">
        <i data-lucide="${countdown.tone === "danger" ? "alarm-clock" : "timer"}"></i>
        <div>
          <span>${escapeHtml(countdown.label)}</span>
          <strong>${escapeHtml(countdown.event?.title || countdown.event?.symbol || "No major event loaded")}</strong>
          <p>${escapeHtml(countdown.detail)}</p>
        </div>
      </div>
    </section>
  `;
}

function renderDailyReviewCard(title = "Winston after-action review") {
  const review = currentReviewState();
  const lines = review.lines || [];
  return `
    <section class="tool-section">
      <div class="section-title">${escapeHtml(title)}</div>
      <div class="review-list">
        ${lines.slice(0, 5).map((line) => `<div class="review-line">${escapeHtml(line)}</div>`).join("")}
        <div class="review-line lesson">${escapeHtml(review.lesson || "Review the cleanest rule before the next session.")}</div>
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-review-refresh>
          <i data-lucide="rotate-cw"></i>
          ${reviewRefreshPromise ? "Reviewing" : "Refresh review"}
        </button>
      </div>
    </section>
  `;
}

function renderCloseReportCard() {
  const report = currentCloseReportState();
  const sections = report.sections || {};
  const actions = sections.action_items || [];
  const coverage = report.coverage?.summary || {};
  return `
    <section class="tool-section">
      <div class="section-title">Daily close report</div>
      <div class="metric-grid">
        ${metric("Coverage", coverage.coverage_score !== undefined ? `${coverage.coverage_score}%` : "Loading", `${coverage.healthy || 0} healthy lanes`)}
        ${metric("Actions", actions.length || 0, actions[0] || "No close actions loaded")}
      </div>
      <div class="review-list">
        ${(sections.performance || []).slice(0, 3).map((line) => `<div class="review-line">${escapeHtml(line)}</div>`).join("")}
        ${(sections.tomorrow || []).slice(0, 2).map((line) => `<div class="review-line lesson">${escapeHtml(line)}</div>`).join("")}
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-close-report-refresh>
          <i data-lucide="file-check-2"></i>
          ${closeReportRefreshPromise ? "Building report" : "Build close report"}
        </button>
      </div>
    </section>
  `;
}

function renderEndOfDayRitualCard() {
  const ritual = todaysRitual();
  return `
    <section class="tool-section">
      <div class="section-title">End-of-day lock ritual</div>
      <div class="ritual-card ${ritual ? "locked" : ""}">
        <i data-lucide="${ritual ? "lock-keyhole" : "unlock-keyhole"}"></i>
        <div>
          <strong>${escapeHtml(ritual ? "Desk locked for today" : "Ready to lock the desk")}</strong>
          <span>${escapeHtml(ritual ? ritual.lesson : "Save the review, risk readback, and latest chart capture before stepping away.")}</span>
          <small>${escapeHtml(ritual ? `${timeAgo(ritual.timestamp)} | ${ritual.capture}` : chartCaptureSummary())}</small>
        </div>
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-eod-ritual>
          <i data-lucide="${ritual ? "refresh-cw" : "lock-keyhole"}"></i>
          ${ritual ? "Refresh lock" : "End day"}
        </button>
        ${ritual ? `<button class="symbol-button" type="button" data-eod-reset><i data-lucide="unlock-keyhole"></i> Reopen</button>` : ""}
      </div>
    </section>
  `;
}

function objectStatus(panel) {
  const pending = dashboardState.pending_approvals || [];
  const countdown = eventCountdownState();
  const mood = riskMood();
  const health = currentHealthState();
  const lifecycle = currentLifecycleState();
  if (panel === "safe" && pending.length) return "attention";
  if (panel === "phone" && (pending.length || winstonState.callActive || winstonState.speaking || winstonState.listening)) {
    return pending.length ? "attention" : "live";
  }
  if (["laptop", "journal", "phone"].includes(panel) && Number(lifecycle.summary?.guardrails || 0) > 0) return "attention";
  if (["calendar", "clock", "mission"].includes(panel) && countdown.tone !== "calm") return "attention";
  if (panel === "lamp" && mood.tone !== "calm") return mood.tone === "danger" ? "attention" : "caution";
  if (panel === "window" && ["storm", "mixed"].includes(marketWeather().tone)) return "caution";
  if (panel === "laptop" && ["red", "yellow"].includes(String(health.overall || "").toLowerCase())) return "caution";
  if (panel === "music" && appleMusicState.playback.isPlaying) return "live";
  if (panel === "journal" && chartCaptures.length) return "saved";
  if (panel === "notes" && todaysRitual()) return "locked";
  return "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function money(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "$0.00";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(number);
}

function percent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "0%";
  return `${(number * 100).toFixed(2)}%`;
}

function compact(value) {
  if (value === null || value === undefined || value === "") return "None";
  return String(value);
}

function calendarDate(value) {
  const date = value ? new Date(`${value}T12:00:00`) : null;
  if (!date || Number.isNaN(date.getTime())) return "Pending";
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function calendarItemLine(item) {
  const when = [calendarDate(item.date), item.time].filter(Boolean).join(" ");
  const source = item.source ? ` | ${item.source}` : "";
  return `${when} | ${item.title || item.symbol || "Event"}${source}`;
}

function timeAgo(value) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "Just now";
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  return `${hours}h ago`;
}

function expiresIn(value) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "No active token";
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  if (seconds <= 0) return "Expired";
  if (seconds < 3600) return `${Math.ceil(seconds / 60)}m remaining`;
  return `${Math.ceil(seconds / 3600)}h remaining`;
}

function formatDuration(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "0:00";
  const minutes = Math.floor(number / 60);
  const seconds = Math.floor(number % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function metric(label, value, sub = "") {
  return `
    <div class="metric">
      <span class="label">${escapeHtml(label)}</span>
      <span class="value">${escapeHtml(value)}</span>
      ${sub ? `<span class="sub">${escapeHtml(sub)}</span>` : ""}
    </div>
  `;
}

function row(label, value) {
  return `
    <div class="data-row">
      <span class="row-label">${escapeHtml(label)}</span>
      <span class="row-value">${escapeHtml(value)}</span>
    </div>
  `;
}

function latestDecision() {
  return dashboardState.recent_decisions?.[0] || null;
}

function tradingViewLabel() {
  return tradingViewSymbols.find((item) => item.symbol === tradingViewSymbol)?.label || tradingViewSymbol;
}

function renderStatus() {
  const brokerOk = Boolean(dashboardState.broker?.ok);
  const armed = Boolean(dashboardState.execution_armed);
  const openPositions = dashboardState.summary?.open_positions ?? dashboardState.positions?.length ?? 0;

  executionPill.className = `status-pill ${armed ? "good" : "warn"}`;
  executionPill.textContent = armed ? "Execution Armed" : "Proposal Mode";

  brokerPill.className = `status-pill ${brokerOk ? "good" : "bad"}`;
  brokerPill.textContent = brokerOk ? "Alpaca Paper" : "Broker Check";

  positionsPill.className = `status-pill ${openPositions > 0 ? "good" : "warn"}`;
  positionsPill.textContent = `${openPositions} Open`;
}

function decisionCard(decision) {
  const side = String(decision.side || "").toLowerCase();
  const title = [decision.symbol, decision.play].filter(Boolean).join(" | ") || decision.reason;
  const prices = [
    decision.entry_price ? `Entry ${decision.entry_price}` : "",
    decision.stop_price ? `Stop ${decision.stop_price}` : "",
    decision.qty ? `Qty ${decision.qty}` : "",
  ]
    .filter(Boolean)
    .join(" | ");
  return `
    <article class="decision">
      <div class="decision-top">
        <span class="decision-title">${escapeHtml(title)}</span>
        <span class="badge ${escapeHtml(side)}">${escapeHtml(decision.status || "seen")}</span>
      </div>
      <div class="decision-meta">${escapeHtml([side.toUpperCase(), decision.reason].filter(Boolean).join(" | "))}</div>
      <div class="decision-meta">${escapeHtml(prices || "Waiting for a qualified setup")}</div>
      <div class="decision-meta">${escapeHtml(timeAgo(decision.timestamp))} | Ref ${escapeHtml(decision.alert_ref || "local")}</div>
    </article>
  `;
}

function renderConfidenceReceipt(receipt) {
  if (!receipt) return "";
  const checks = receipt.checks || [];
  return `
    <div class="receipt-card">
      <div class="decision-meta">${escapeHtml(receipt.summary || `Confidence ${receipt.score ?? 0}/100`)}</div>
      <div class="data-list compact-list">
        ${row("Receipt", `${receipt.score ?? 0}/100 | Grade ${receipt.grade || "N/A"}`)}
        ${row("Risk readback", receipt.risk_readback || "Risk receipt pending")}
        ${row("Next", receipt.next_action || "Wait for qualified structure")}
      </div>
      ${
        checks.length
          ? `<div class="health-grid receipt-grid">${checks.slice(0, 4).map((check) => healthComponentCard({ name: check.name, ok: check.ok, status: check.ok ? "pass" : "review", detail: check.detail || `${check.weight || 0} points` })).join("")}</div>`
          : ""
      }
    </div>
  `;
}

function journalCard(entry) {
  const side = String(entry.side || "").toLowerCase();
  const readback = entry.readback || [];
  const metrics = entry.metrics || {};
  const chart = entry.chart_context || {};
  const receipt = entry.confidence_receipt || null;
  const title = [entry.symbol, entry.setup || entry.play].filter(Boolean).join(" | ") || entry.reason;
  return `
    <article class="decision journal-card">
      <div class="decision-top">
        <span class="decision-title">${escapeHtml(title)}</span>
        <span class="badge ${escapeHtml(side)}">${escapeHtml(entry.grade ? `Grade ${entry.grade}` : entry.status || "seen")}</span>
      </div>
      <div class="decision-meta">${escapeHtml([String(entry.status || "seen").toUpperCase(), entry.reason].filter(Boolean).join(" | "))}</div>
      <div class="journal-readback">
        ${readback.slice(0, 4).map((line) => `<span>${escapeHtml(line)}</span>`).join("")}
      </div>
      <div class="decision-meta">${escapeHtml([metrics.risk_dollars ? `Risk ${money(metrics.risk_dollars)}` : "", metrics.target_r ? `${metrics.target_r}R target` : "", timeAgo(entry.timestamp)].filter(Boolean).join(" | "))}</div>
      ${renderConfidenceReceipt(receipt)}
      <div class="actions compact-actions">
        <button class="symbol-button" type="button" data-review-alert="${escapeHtml(entry.alert_ref || "")}">
          <i data-lucide="scan-search"></i>
          Review
        </button>
        <button class="symbol-button" type="button" data-replay-setup="${escapeHtml(entry.setup || entry.play || "")}" data-replay-symbol="${escapeHtml(entry.symbol || "SPY")}">
          <i data-lucide="play"></i>
          Replay setup
        </button>
      </div>
      ${
        chart.url
          ? `<a class="decision-link" href="${escapeHtml(chart.url)}" target="_blank" rel="noreferrer">
              <i data-lucide="external-link"></i>
              <span>${escapeHtml([chart.symbol || entry.symbol, chart.timeframe || entry.timeframe || "chart"].filter(Boolean).join(" | "))}</span>
            </a>`
          : ""
      }
    </article>
  `;
}

function renderTradeReview() {
  const review = currentTradeReviewState();
  if (tradeReviewPromise) {
    return `<section class="tool-section"><div class="section-title">Trade review</div><div class="empty-state compact">Loading selected trade review...</div></section>`;
  }
  if (!review?.ok) {
    return `<section class="tool-section"><div class="section-title">Trade review</div><div class="empty-state compact">Select Review on a journal card to inspect rule checks, sizing, and what happened next.</div></section>`;
  }
  const entry = review.entry || {};
  const checks = review.rule_checks || [];
  const after = review.timeline?.after || [];
  return `
    <section class="tool-section review-panel">
      <div class="section-title">Trade review</div>
      <div class="decision journal-card">
        <div class="decision-top">
          <span class="decision-title">${escapeHtml([entry.symbol, entry.setup].filter(Boolean).join(" | ") || "Selected trade")}</span>
          <span class="badge ${escapeHtml(String(entry.side || "").toLowerCase())}">${escapeHtml(entry.grade ? `Grade ${entry.grade}` : entry.status || "seen")}</span>
        </div>
        <div class="decision-meta">${escapeHtml(review.verdict || "Review ready")}</div>
        <div class="data-list compact-list">
          ${row("Entry", [entry.side, entry.qty ? `qty ${entry.qty}` : "", entry.entry_price ? `entry ${entry.entry_price}` : "", entry.stop_price ? `stop ${entry.stop_price}` : ""].filter(Boolean).join(" | ") || "No order levels")}
          ${row("After", review.what_happened_after || "No later journal item")}
          ${row("Replay", review.replay_scenario || "bull_elephant")}
        </div>
        ${renderConfidenceReceipt(entry.confidence_receipt)}
        <div class="health-grid">
          ${checks.map(healthComponentCard).join("")}
        </div>
        <div class="actions">
          <button class="action-button" type="button" data-replay-scenario="${escapeHtml(review.replay_scenario || "bull_elephant")}" data-replay-symbol="${escapeHtml(entry.symbol || "SPY")}">
            <i data-lucide="play"></i>
            Replay this setup
          </button>
          ${entry.chart_context?.url ? `<a class="symbol-button" href="${escapeHtml(entry.chart_context.url)}" target="_blank" rel="noreferrer"><i data-lucide="external-link"></i> Open chart</a>` : ""}
        </div>
      </div>
      ${
        after.length
          ? `<div class="replay-list">${after.slice(0, 3).map((item) => replayEventCard({ symbol: item.symbol, play: item.setup || item.play, side: item.status, order_type: item.reason, entry_price: item.entry_price, stop_price: item.stop_price, risk_dollars: item.metrics?.risk_dollars })).join("")}</div>`
          : ""
      }
    </section>
  `;
}

function healthTone(value) {
  if (value === "green" || value === true) return "good";
  if (value === "red" || value === false) return "bad";
  return "warn";
}

function healthComponentCard(component) {
  return `
    <article class="health-card ${healthTone(component.ok)}">
      <div>
        <strong>${escapeHtml(component.name)}</strong>
        <span>${escapeHtml(component.detail || "No detail")}</span>
      </div>
      <small>${escapeHtml(component.status || "unknown")}</small>
    </article>
  `;
}

function renderRiskCommandCenter() {
  const state = currentRiskState();
  const risk = state.risk || {};
  const guardrails = state.guardrails || {};
  const lotSizing = risk.lot_sizing || {};
  const approvalRequired = Boolean(state.approval_required);
  const nextMode = !approvalRequired;
  return `
    <section class="tool-section">
      <div class="section-title">Risk command center</div>
      <div class="metric-grid">
        ${metric("Paper trading", state.execution_armed ? "Armed" : "Off", state.execution_armed ? "Qualified alerts can submit" : "Proposal mode")}
        ${metric("Approval gate", approvalRequired ? "Required" : "Current mode", state.approval_mode_source || "environment")}
        ${metric("Max risk", money(risk.max_dollar_risk_per_trade || 0), `${percent(risk.risk_per_trade)} equity cap`)}
        ${metric("Lot flow", lotSizing.enabled === false ? "Off" : `1-${lotSizing.max_lots || 4} lots`, `${percent(lotSizing.lot_risk_fraction || 0.25)} risk per lot`)}
      </div>
      <div class="data-list compact-list">
        ${row("Daily loss", `${percent(risk.max_daily_loss_pct)} | ${risk.max_open_positions || 0} max positions`)}
        ${row("Paper only", compact(guardrails.paper_only))}
        ${row("Webhook auth", compact(guardrails.auth_required))}
        ${row("Max stop", percent(risk.max_stop_pct))}
        ${row("Pyramid add", percent(risk.pyramid_add_fraction ?? 0.5))}
        ${row("Full core", `${lotSizing.max_lots || 4} lots = configured max risk`)}
      </div>
      <div class="actions">
        <button class="action-button" type="button" data-risk-approval-toggle="${String(nextMode)}" ${approvalToken && !riskUpdatePromise ? "" : "disabled"} aria-pressed="${approvalRequired ? "true" : "false"}">
          <i data-lucide="shield-check"></i>
          <span>${approvalRequired ? "Keep approval required" : "Require Winston approval"}</span>
        </button>
        <button class="symbol-button" type="button" data-risk-refresh><i data-lucide="refresh-cw"></i> Refresh risk</button>
        <button class="symbol-button" type="button" data-notification-test><i data-lucide="send"></i> Test notifications</button>
      </div>
      <div class="empty-state compact">
        ${escapeHtml(approvalToken ? "Approval-mode changes require the local approval token and never expose secrets in the browser." : "Enter the approval token in the phone panel before changing approval mode or running the webhook dry-run test.")}
      </div>
    </section>
  `;
}

function renderLifecycleCommandCenter() {
  const lifecycle = currentLifecycleState();
  const summary = lifecycle.summary || {};
  const positions = lifecycle.positions || [];
  const guardrails = lifecycle.guardrails || [];
  const outcomes = lifecycle.outcomes || [];
  const avgR = summary.average_r_multiple === null || summary.average_r_multiple === undefined ? "N/A" : `${Number(summary.average_r_multiple).toFixed(2)}R`;
  return `
    <section class="tool-section lifecycle-section">
      <div class="section-title">Trade lifecycle command center</div>
      <div class="metric-grid">
        ${metric("Active trades", summary.open_positions || 0, `${summary.open_orders || 0} open broker orders`)}
        ${metric("Open risk", money(summary.open_risk || 0), `${money(summary.unrealized_pl || 0)} unrealized`)}
        ${metric("Avg R", avgR, `${summary.management_actions || 0} rule checks`)}
        ${metric("Guardrails", summary.guardrails || guardrails.length || 0, lifecycle.ok ? "Broker reconciliation online" : "Needs refresh")}
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-lifecycle-refresh>
          <i data-lucide="refresh-cw"></i>
          Refresh lifecycle
        </button>
        <button class="symbol-button" type="button" data-lifecycle-reconcile>
          <i data-lucide="scan-line"></i>
          Reconcile now
        </button>
      </div>
      <div class="data-list compact-list">
        ${row("Readback", lifecycle.readback || "Lifecycle readback pending")}
        ${row("Updated", timeAgo(lifecycle.timestamp))}
        ${row("Mode", lifecycle.note || "Read-only lifecycle watch")}
      </div>
      ${
        guardrails.length
          ? `<div class="health-grid">${guardrails.slice(0, 6).map(lifecycleGuardrailCard).join("")}</div>`
          : `<div class="empty-state compact">No lifecycle guardrail alerts are active.</div>`
      }
      ${
        positions.length
          ? `<div class="decision-list">${positions.slice(0, 6).map(lifecyclePositionCard).join("")}</div>`
          : `<div class="empty-state compact">No Alpaca paper positions are open. The command center will fill in when a paper trade is live.</div>`
      }
      ${
        outcomes.length
          ? `<div class="replay-list lifecycle-outcomes">${outcomes.slice(0, 4).map(lifecycleOutcomeCard).join("")}</div>`
          : ""
      }
    </section>
  `;
}

function lifecyclePositionCard(position) {
  const side = String(position.side || "").toLowerCase();
  const rValue = position.current_r_multiple === null || position.current_r_multiple === undefined ? "R N/A" : `${Number(position.current_r_multiple).toFixed(2)}R`;
  const stop = position.stop_price === null || position.stop_price === undefined ? "Stop missing" : `Stop ${position.stop_price}`;
  const management = position.management || [];
  return `
    <article class="decision lifecycle-card">
      <div class="decision-top">
        <span class="decision-title">${escapeHtml([position.symbol, side.toUpperCase(), `qty ${position.signed_qty ?? position.qty ?? 0}`].filter(Boolean).join(" | "))}</span>
        <span class="badge ${escapeHtml(side === "short" ? "sell" : "buy")}">${escapeHtml(rValue)}</span>
      </div>
      <div class="decision-meta">${escapeHtml([`Entry ${position.entry_price ?? "N/A"}`, stop, `P/L ${money(position.unrealized_pl || 0)}`].join(" | "))}</div>
      <div class="decision-meta">${escapeHtml(position.next_action || "No lifecycle action due.")}</div>
      ${
        management.length
          ? `<div class="health-grid lifecycle-rule-grid">${management.slice(0, 3).map((item) => healthComponentCard({ name: item.name, ok: item.status !== "due", status: item.status || "watch", detail: item.detail })).join("")}</div>`
          : ""
      }
      <div class="data-list compact-list">
        ${row("Setup", position.linked_setup || "No journal link")}
        ${row("Stop source", position.stop_source || "unknown")}
      </div>
    </article>
  `;
}

function lifecycleGuardrailCard(item) {
  const severity = item.severity === "critical" ? false : item.severity === "warn" ? "yellow" : true;
  return healthComponentCard({
    name: [item.symbol, item.name].filter(Boolean).join(" | ") || "Lifecycle guardrail",
    ok: severity,
    status: item.status || item.severity || "watch",
    detail: item.detail || "Review lifecycle state.",
  });
}

function lifecycleOutcomeCard(item) {
  return replayEventCard({
    symbol: item.symbol,
    play: item.status,
    side: item.r_multiple === null || item.r_multiple === undefined ? "logged" : `${Number(item.r_multiple).toFixed(2)}R`,
    order_type: item.notes,
    entry_price: "",
    stop_price: "",
    risk_dollars: item.pnl,
  });
}

function renderHardeningPanel() {
  const hardening = currentHardeningState();
  return `
    <section class="tool-section">
      <div class="section-title">VPS hardening</div>
      <div class="metric-grid">
        ${metric("Status", String(hardening.overall || "loading").toUpperCase(), hardening.note || "Restart, backup, heartbeat")}
        ${metric("Backup path", hardening.paths?.backup_dir || "Checking", "Daily helper script")}
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-hardening-refresh><i data-lucide="server"></i> Refresh VPS checks</button>
      </div>
      <div class="health-grid">
        ${(hardening.checks || []).map(healthComponentCard).join("")}
      </div>
      ${
        hardening.helpers?.length
          ? `<div class="data-list compact-list">${hardening.helpers.map((item) => row(item.name, `${item.path} | ${item.purpose}`)).join("")}</div>`
          : ""
      }
    </section>
  `;
}

function renderLatencyPanel() {
  const latency = currentLatencyState();
  return `
    <section class="tool-section">
      <div class="section-title">VPS uptime + latency</div>
      <div class="metric-grid">
        ${metric("Status", String(latency.overall || "loading").toUpperCase(), latency.summary || "Probe status")}
        ${metric("Uptime", latency.uptime_seconds ? `${Math.floor(latency.uptime_seconds / 60)}m` : "Loading", "Webhook container")}
        ${metric("Average", `${latency.average_latency_ms || 0}ms`, "Probe average")}
        ${metric("Worst", `${latency.worst_latency_ms || 0}ms`, `Warn over ${latency.warn_threshold_ms || 1200}ms`)}
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-latency-refresh><i data-lucide="gauge"></i> Refresh latency</button>
      </div>
      <div class="health-grid">
        ${(latency.checks || []).map((check) => healthComponentCard({ ...check, status: `${check.status || "ok"} | ${check.latency_ms || 0}ms` })).join("")}
      </div>
    </section>
  `;
}

function timelineItem(item) {
  return `
    <article class="timeline-item ${escapeHtml(item.kind || "event")}">
      <span>${escapeHtml([calendarDate(item.date), item.time].filter(Boolean).join(" "))}</span>
      <strong>${escapeHtml(item.title || item.symbol || "Calendar item")}</strong>
      <small>${escapeHtml([item.kind, item.source, item.importance].filter(Boolean).join(" | "))}</small>
    </article>
  `;
}

function replayEventCard(event) {
  return `
    <article class="replay-event">
      <strong>${escapeHtml([event.symbol, event.play].filter(Boolean).join(" | "))}</strong>
      <span>${escapeHtml([String(event.side || "").toUpperCase(), event.order_type, event.qty ? `qty ${event.qty}` : ""].filter(Boolean).join(" | "))}</span>
      <small>${escapeHtml([event.entry_price ? `Entry ${event.entry_price}` : "", event.stop_price ? `Stop ${event.stop_price}` : "", event.risk_dollars ? `Risk ${money(event.risk_dollars)}` : ""].filter(Boolean).join(" | "))}</small>
    </article>
  `;
}

function renderTradingScreen() {
  const last = latestDecision();
  const watched = (dashboardState.symbols || []).map((item) => item.symbol).filter(Boolean).join(", ");
  const symbolButtons = tradingViewSymbols
    .map(
      (item) => `
        <button class="symbol-button ${item.symbol === tradingViewSymbol ? "active" : ""}" type="button" data-symbol="${escapeHtml(item.symbol)}">
          ${escapeHtml(item.label)}
        </button>
      `,
    )
    .join("");
  return `
    <div class="metric-grid">
      ${metric("Chart", tradingViewLoaded ? "TradingView" : "Canvas fallback", tradingViewLabel())}
      ${metric("Last setup", last?.play || "Scanning", last?.symbol || "No alert yet")}
      ${metric("Risk unit", money(dashboardState.risk?.max_dollar_risk_per_trade), `${percent(dashboardState.risk?.risk_per_trade)} equity cap`)}
      ${metric("Watchlist", watched || "None", `${dashboardState.summary?.symbols_watched || 0} symbols`)}
    </div>
    <div class="actions">${symbolButtons}</div>
    <div class="data-list">
      ${row("Feed", dashboardState.ok ? "Dashboard API online" : "Waiting for bot state")}
      ${row("Decision", last?.status || "Standing by")}
      ${row("Paper", dashboardState.paper_endpoint ? "Paper endpoint locked" : "Endpoint warning")}
      ${row("Updated", timeAgo(dashboardState.timestamp))}
    </div>
    <section class="tool-section">
      <div class="section-title">Watchlist heat</div>
      ${renderWatchlistHeatStrip()}
    </section>
    ${renderChartCaptureLane()}
  `;
}

function renderMission() {
  const mission = dailyMission();
  const review = currentReviewState();
  const ritual = todaysRitual();
  return `
    <div class="mood-card ${escapeHtml(mission.mood.tone)}">
      <i data-lucide="target"></i>
      <div>
        <span>Daily mission</span>
        <strong>${escapeHtml(mission.title)}</strong>
        <p>${escapeHtml(mission.rule)}</p>
      </div>
    </div>
    <div class="metric-grid">
      ${metric("Session", mission.clock.phase, mission.clock.next)}
      ${metric("Event timer", mission.countdown.label, mission.countdown.detail)}
      ${metric("Risk mood", mission.mood.label, mission.mood.headline)}
      ${metric("Approvals", mission.pending.length, mission.pending.length ? "Needs review" : "None pending")}
    </div>
    <section class="tool-section">
      <div class="section-title">Mission checklist</div>
      <div class="data-list compact-list">
        ${row("Rule", mission.rule)}
        ${row("Weather", `${mission.weather.label} | ${mission.weather.detail}`)}
        ${row("Review", review.lesson || "Review after the session")}
        ${row("Chart capture", chartCaptureSummary())}
      </div>
    </section>
    <section class="tool-section">
      <div class="section-title">Watchlist heat</div>
      ${renderWatchlistHeatStrip()}
    </section>
    <div class="actions">
      <button class="symbol-button" type="button" data-open-panel="clock"><i data-lucide="clock"></i> Event clock</button>
      <button class="symbol-button" type="button" data-open-panel="safe"><i data-lucide="inbox"></i> Approval inbox</button>
      <button class="symbol-button" type="button" data-eod-ritual><i data-lucide="lock-keyhole"></i> End day</button>
    </div>
    ${renderEventCountdownCard()}
    ${renderDailyReviewCard("Winston after-action review")}
    ${
      ritual
        ? `<div class="ritual-card locked compact"><i data-lucide="lock-keyhole"></i><div><strong>Today is locked</strong><span>${escapeHtml(ritual.lesson)}</span></div></div>`
        : ""
    }
  `;
}

async function submitWatchlistSymbol(event) {
  event.preventDefault();
  const symbolInput = $("#watchlist-symbol");
  const typeInput = $("#watchlist-type");
  const symbol = (symbolInput?.value || "").trim().toUpperCase();
  const type = typeInput?.value || "equity";
  if (!symbol) return;
  try {
    const response = await fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol,
        type,
        contract_multiplier: type === "future" ? 50 : 1,
        session: type === "future" ? "full" : "rth",
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `watchlist add failed (${response.status})`);
    dashboardState.symbols = data.symbols || dashboardState.symbols;
    dashboardState.summary = { ...dashboardState.summary, symbols_watched: dashboardState.symbols.length };
    watchlistDraft = { symbol: "", type };
    if (symbolInput) symbolInput.value = "";
  } catch (error) {
    winstonTranscript("system", error?.message || "Watchlist update failed");
  }
  renderPanel();
}

async function removeWatchlistSymbol(symbol) {
  if (!symbol) return;
  try {
    const response = await fetch(`/api/watchlist/${encodeURIComponent(symbol)}`, { method: "DELETE", cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `watchlist remove failed (${response.status})`);
    dashboardState.symbols = data.symbols || dashboardState.symbols.filter((item) => item.symbol !== symbol);
    dashboardState.summary = { ...dashboardState.summary, symbols_watched: dashboardState.symbols.length };
  } catch (error) {
    winstonTranscript("system", error?.message || "Watchlist removal failed");
  }
  renderPanel();
}

function renderLaptop() {
  const broker = dashboardState.broker || {};
  const symbols = dashboardState.symbols || [];
  const health = currentHealthState();
  const replay = currentReplayState();
  const latestReplay = replay.ok && replay.summary ? replay : replay.runs?.[0] || null;
  const pending = dashboardState.pending_approvals || [];
  const scanner = dashboardState.scanner || {};
  return `
    <div class="metric-grid">
      ${metric("Execution", dashboardState.execution_armed ? "Armed" : "Proposal", dashboardState.execution_armed ? "Paper orders enabled" : "No live submit")}
      ${metric("Broker", broker.ok ? "Connected" : "Needs check", broker.account_status || broker.reason || "Unknown")}
      ${metric("Open risk", money(dashboardState.summary?.unrealized_pl || 0), `${dashboardState.summary?.open_positions || 0} open positions`)}
      ${metric("Scanner", scanner.enabled ? (scanner.running ? "Running" : "Stopped") : "Off", scanner.mode || "Hybrid watchlist")}
    </div>
    <div class="data-list">
      ${row("Max positions", dashboardState.risk?.max_open_positions ?? "None")}
      ${row("Daily loss cap", percent(dashboardState.risk?.max_daily_loss_pct))}
      ${row("Pyramid add", percent(dashboardState.risk?.pyramid_add_fraction ?? 0.5))}
      ${row("TIF", dashboardState.guardrails?.time_in_force || "day")}
    </div>
    ${renderRiskCommandCenter()}
    ${renderLifecycleCommandCenter()}
    ${renderCloseReportCard()}
    ${renderScannerPanel()}
    ${renderAlertCoveragePanel()}
    <section class="tool-section">
      <div class="section-title">Command shortcuts</div>
      <div class="quick-grid">
        <button class="object-card compact" type="button" data-open-panel="clock">
          <i data-lucide="clock"></i>
          <strong>Sessions</strong>
          <span>${escapeHtml(marketClock().next)}</span>
        </button>
        <button class="object-card compact" type="button" data-open-panel="mission">
          <i data-lucide="target"></i>
          <strong>Mission</strong>
          <span>${escapeHtml(dailyMission().rule)}</span>
        </button>
        <button class="object-card compact" type="button" data-open-panel="lamp">
          <i data-lucide="lamp"></i>
          <strong>Risk Lamp</strong>
          <span>${escapeHtml(riskMood().headline)}</span>
        </button>
        <button class="object-card compact" type="button" data-open-panel="safe">
          <i data-lucide="shield-check"></i>
          <strong>Vault</strong>
          <span>${escapeHtml(pending.length ? `${pending.length} pending` : "No pending approvals")}</span>
        </button>
        <button class="object-card compact" type="button" data-open-panel="drawer">
          <i data-lucide="archive"></i>
          <strong>Backtest</strong>
          <span>${escapeHtml(latestReplay?.summary || "Replay ready")}</span>
        </button>
      </div>
    </section>
    ${renderHardeningPanel()}
    ${renderLatencyPanel()}
    <section class="tool-section">
      <div class="section-title">Bot health</div>
      <div class="actions">
        <button class="symbol-button" type="button" data-health-refresh>
          <i data-lucide="activity"></i>
          Refresh health
        </button>
      </div>
      <div class="health-grid">
        ${(health.components || []).slice(0, 6).map(healthComponentCard).join("")}
      </div>
    </section>
    <section class="tool-section">
      <div class="section-title">Watchlist</div>
      <form class="inline-form" id="watchlist-form">
        <input id="watchlist-symbol" type="text" placeholder="Symbol" maxlength="12" autocomplete="off" value="${escapeHtml(watchlistDraft.symbol)}" />
        <select id="watchlist-type" aria-label="Asset type">
          <option value="equity" ${watchlistDraft.type === "equity" ? "selected" : ""}>Equity</option>
          <option value="future" ${watchlistDraft.type === "future" ? "selected" : ""}>Future</option>
          <option value="crypto" ${watchlistDraft.type === "crypto" ? "selected" : ""}>Crypto</option>
          <option value="forex" ${watchlistDraft.type === "forex" ? "selected" : ""}>Forex</option>
        </select>
        <button class="icon-button primary" type="submit" title="Add symbol">
          <i data-lucide="plus"></i>
        </button>
      </form>
      <div class="chip-list">
        ${symbols
          .map(
            (item) => `
              <button class="symbol-chip" type="button" data-remove-symbol="${escapeHtml(item.symbol)}" title="Remove ${escapeHtml(item.symbol)}">
                <span>${escapeHtml(item.symbol)}</span>
                <small>${escapeHtml(item.type || "equity")}</small>
                <i data-lucide="x"></i>
              </button>
            `,
          )
          .join("")}
      </div>
      ${renderWatchlistHeatStrip()}
    </section>
    <section class="tool-section">
      <div class="section-title">Replay mode</div>
      <form class="inline-form" id="replay-form">
        <select id="replay-scenario" aria-label="Replay scenario">
          <option value="bull_elephant">Bull elephant sample</option>
          <option value="bear_180">Bear 180 sample</option>
          <option value="buy_setup">Velez buy setup</option>
          <option value="sell_setup">Velez sell setup</option>
          <option value="nrb_acorn">NRB / Acorn</option>
          <option value="color_change_add">Color-change add</option>
          <option value="fab4_trap">Fab 4 trap breakout</option>
          <option value="failed_new_high">Failed new high</option>
          <option value="failed_new_low">Failed new low</option>
          <option value="opening_gap_go">Opening gap go</option>
          <option value="opening_gap_fade">Opening gap fade</option>
          <option value="time_space_breakout">Time + space breakout</option>
        </select>
        <select id="replay-symbol" aria-label="Replay symbol">
          ${(symbols.length ? symbols : [{ symbol: "SPY" }])
            .map((item) => `<option value="${escapeHtml(item.symbol)}">${escapeHtml(item.symbol)}</option>`)
            .join("")}
        </select>
        <button class="icon-button primary" type="submit" title="Run replay" ${replayRunPromise ? "disabled" : ""}>
          <i data-lucide="${replayRunPromise ? "loader" : "play"}"></i>
        </button>
      </form>
      <div class="actions">
        <button class="symbol-button" type="button" data-risk-replay>
          <i data-lucide="calculator"></i>
          Risk replay
        </button>
      </div>
      <div class="data-list compact-list">
        ${row("Latest replay", latestReplay?.summary || "No replay run yet")}
        ${row("Signals", latestReplay?.signals_found ?? 0)}
        ${row("Risk replay", latestReplay?.risk_replay?.summary || "Run a what-if sizing replay")}
      </div>
      ${
        latestReplay?.events?.length
          ? `<div class="replay-list">${latestReplay.events.slice(-3).map(replayEventCard).join("")}</div>`
          : `<div class="empty-state compact">Replay runs locally and never submits broker orders.</div>`
      }
      ${
        latestReplay?.risk_replay?.variants?.length
          ? `<div class="replay-list">${latestReplay.risk_replay.variants.slice(-3).map((item) => replayEventCard({ ...item, order_type: `risk ${money(item.risk_budget)}`, risk_dollars: item.estimated_risk })).join("")}</div>`
          : ""
      }
    </section>
  `;
}

function renderJournal() {
  const journal = currentJournalState();
  const lifecycle = currentLifecycleState();
  const entries = journal.entries || [];
  const replays = journal.replays || [];
  const research = journal.research || [];
  const outcomes = lifecycle.outcomes || [];
  return `
    <div class="metric-grid">
      ${metric("Entries", journal.summary?.entries || entries.length, "Persistent SQLite journal")}
      ${metric("Actionable", journal.summary?.actionable || 0, "Proposed or submitted")}
      ${metric("Blocked", journal.summary?.blocked || 0, "Rejected, ignored, or error")}
      ${metric("Top setup", journal.summary?.top_setup || "None", journal.summary?.top_symbol || "No symbol")}
    </div>
    <div class="actions">
      <button class="symbol-button" type="button" data-journal-refresh>
        <i data-lucide="refresh-cw"></i>
        Refresh journal
      </button>
    </div>
    ${renderChartCaptureLane()}
    ${renderDailyReviewCard("Winston after-action review")}
    ${renderCloseReportCard()}
    ${renderTradeReview()}
    <section class="tool-section">
      <div class="section-title">Lifecycle outcomes</div>
      <div class="actions">
        <button class="symbol-button" type="button" data-lifecycle-refresh>
          <i data-lucide="refresh-cw"></i>
          Refresh lifecycle
        </button>
      </div>
      ${
        outcomes.length
          ? `<div class="replay-list">${outcomes.slice(0, 6).map(lifecycleOutcomeCard).join("")}</div>`
          : `<div class="empty-state compact">Trade outcome events will appear here after a live paper position is reconciled.</div>`
      }
    </section>
    ${
      entries.length
        ? `<div class="decision-list">${entries.slice(0, 12).map(journalCard).join("")}</div>`
        : `<div class="empty-state compact">No TradingView alerts are saved yet. Replay history is shown below.</div>`
    }
    <section class="tool-section">
      <div class="section-title">Review lane</div>
      <div class="data-list compact-list">
        ${row("What worked", entries.find((item) => ["submitted", "proposed"].includes(item.status))?.setup || "Waiting for actionable setup")}
        ${row("What blocked", entries.find((item) => ["rejected", "ignored", "error"].includes(item.status))?.reason || "No blocked alert in view")}
        ${row("Latest research", research[0]?.topic || "No Winston research note saved yet")}
      </div>
    </section>
    ${
      replays.length
        ? `<section class="tool-section"><div class="section-title">Replay history</div><div class="replay-list">${replays.slice(0, 3).map((item) => replayEventCard({ symbol: item.symbol, play: item.scenario, side: "scan", order_type: `${item.signals_found || 0} signals`, entry_price: "", stop_price: "", risk_dollars: "" })).join("")}</div></section>`
        : ""
    }
  `;
}

function renderCalendar() {
  const calendar = currentCalendarState();
  const pnl = calendar.pnl || {};
  const alerts = calendar.alerts || {};
  const events = calendar.events || [];
  const earnings = calendar.earnings || [];
  const timeline = calendar.timeline || [];
  const session = calendar.session || {};
  const journal = calendar.journal || {};
  const sourceNotes = calendar.sources || {};
  const alpha = sourceNotes.alpha_vantage || {};
  const macroSources = sourceNotes.macro || [];
  const macroReady = macroSources.filter((source) => source.ok).length;
  const earningsLabel = earnings.length
    ? `${calendarDate(earnings[0].date)} | ${earnings[0].symbol || earnings[0].title}`
    : alpha.configured === false
      ? "Alpha Vantage key needed"
      : "No watchlist earnings found";
  const macroLabel = events.length ? calendarItemLine(events[0]) : macroReady ? "No major macro events found" : "Macro feeds checking";
  const refreshLabel = calendarRefreshPromise ? "Refreshing..." : `Updated ${timeAgo(calendar.timestamp)}`;
  return `
    <div class="metric-grid">
      ${metric("Month P/L", money(pnl.month_pl || 0), pnl.detail || "Alpaca portfolio history")}
      ${metric("Open mark", money(pnl.unrealized_pl || dashboardState.summary?.unrealized_pl || 0), "Open-position unrealized P/L")}
      ${metric("Alerts", alerts.count || 0, `${journal.sessions_logged || 0} journal days this month`)}
      ${metric("Events", events.length + earnings.length, calendar.range?.month_label || "Monthly feed")}
    </div>
    <div class="actions">
      <button class="symbol-button" type="button" data-calendar-refresh>
        <i data-lucide="refresh-cw"></i>
        Refresh feeds
      </button>
    </div>
    <div class="data-list">
      ${row("Session", `${session.status || "Unknown"} | ${session.label || "No market session loaded"}`)}
      ${row("Macro", macroLabel)}
      ${row("Earnings", earningsLabel)}
      ${row("Review", journal.status || "Monthly journal lane ready")}
      ${row("Feed", refreshLabel)}
      ${events.slice(1, 4).map((item, index) => row(`Macro ${index + 2}`, calendarItemLine(item))).join("")}
      ${earnings.slice(1, 4).map((item, index) => row(`Earn ${index + 2}`, `${calendarDate(item.date)} | ${item.symbol} | ${item.name || item.title}`)).join("")}
    </div>
    ${renderEventCountdownCard()}
    <section class="tool-section">
      <div class="section-title">Upcoming desk timeline</div>
      ${
        timeline.length
          ? `<div class="timeline-list">${timeline.slice(0, 8).map(timelineItem).join("")}</div>`
          : `<div class="empty-state compact">Calendar timeline is waiting for sessions, macro events, earnings, or journal activity.</div>`
      }
    </section>
    <section class="tool-section">
      <div class="section-title">Month pulse</div>
      <div class="pulse-row">
        <span class="${Number(pnl.month_pl || 0) >= 0 ? "positive" : "negative"}">${escapeHtml(money(pnl.month_pl || 0))}</span>
        <span>${escapeHtml(`${alerts.count || 0} alerts`)}</span>
        <span>${escapeHtml(`${calendar.sessions?.length || 0} sessions`)}</span>
      </div>
    </section>
  `;
}

function renderSafe() {
  const broker = dashboardState.broker || {};
  const apple = appleMusicBridgeStatus();
  const winston = dashboardState.winston || {};
  return `
    <div class="metric-grid">
      ${metric("Keys", "Redacted", "Stored outside the browser")}
      ${metric("Webhook", dashboardState.guardrails?.auth_required ? "Auth on" : "Auth off", "Secret never displayed")}
      ${metric("Account", broker.account_number_tail ? `...${broker.account_number_tail}` : "Hidden", broker.paper ? "Paper account" : "No account exposed")}
      ${metric("Endpoint", dashboardState.paper_endpoint ? "Paper" : "Review", "Alpaca base URL")}
    </div>
    <div class="data-list">
      ${row("Trading blocked", compact(broker.trading_blocked))}
      ${row("Broker status", broker.account_status || broker.reason || "Unknown")}
      ${row("Approval token", approvalToken ? "Stored in this browser" : "Not entered")}
      ${row("Apple key", apple.configured ? appleMusicTokenLabel(apple) : appleMusicMissingLabel(apple.missing))}
      ${row("Winston brain", [winston.brain?.provider, winston.brain?.model].filter(Boolean).join(" | ") || "Checking")}
      ${row("Winston voice", [winston.voice?.provider, winston.voice?.voice].filter(Boolean).join(" | ") || "Checking")}
    </div>
    <section class="tool-section">
      <div class="section-title">Approval inbox</div>
      ${renderApprovalInbox()}
    </section>
    <section class="tool-section">
      <div class="section-title">Vault checks</div>
      <div class="health-grid">
        ${healthComponentCard({ name: "Alpaca paper", ok: Boolean(broker.ok && broker.paper), status: broker.ok ? "connected" : "check", detail: "Account key remains server-side" })}
        ${healthComponentCard({ name: "Webhook secret", ok: Boolean(dashboardState.guardrails?.auth_required), status: dashboardState.guardrails?.auth_required ? "armed" : "off", detail: "TradingView alerts require server auth" })}
        ${healthComponentCard({ name: "Approval token", ok: Boolean(approvalToken), status: approvalToken ? "local" : "empty", detail: "Only stored in this browser" })}
        ${healthComponentCard({ name: "Apple Music", ok: Boolean(apple.configured), status: apple.configured ? "signed" : "missing", detail: "Private key never reaches the browser" })}
      </div>
    </section>
  `;
}

function renderBookshelf() {
  return `
    <div class="metric-grid">
      ${metric("Plays", strategyShelf.length, "Core Velez rule cards")}
      ${metric("Location", "Required", "No structure, no trade")}
      ${metric("Tail rule", "66%", "Minimum wick share")}
      ${metric("Add rule", "50%", "Pyramid into winners only")}
    </div>
    <div class="strategy-shelf">
      ${strategyShelf
        .map(
          (item) => `
            <article class="strategy-card">
              <span>${escapeHtml(item.tag)}</span>
              <strong>${escapeHtml(item.title)}</strong>
              <p>${escapeHtml(item.rule)}</p>
              <small>${escapeHtml(item.action)}</small>
            </article>
          `,
        )
        .join("")}
    </div>
    <div class="actions">
      <button class="symbol-button" type="button" data-open-panel="tv"><i data-lucide="monitor"></i> Watch chart</button>
      <button class="symbol-button" type="button" data-open-panel="drawer"><i data-lucide="archive"></i> Run replay</button>
    </div>
  `;
}

function renderClock() {
  const clock = marketClock();
  const calendar = currentCalendarState();
  const upcoming = (calendar.sessions || []).filter((item) => item.date >= clock.date).slice(0, 5);
  const countdown = eventCountdownState();
  return `
    <div class="metric-grid">
      ${metric("Now", clock.now, "America/New_York")}
      ${metric("Session", clock.phase, clock.session)}
      ${metric("Next", clock.next, clock.date)}
      ${metric("Event timer", countdown.label, countdown.detail)}
    </div>
    ${renderEventCountdownCard()}
    <section class="tool-section">
      <div class="section-title">Session tape</div>
      <div class="timeline-list">
        ${upcoming.length ? upcoming.map((item) => timelineItem({ date: item.date, time: item.open, title: `Regular session ${item.label}`, kind: "session", source: "NYSE" })).join("") : `<div class="empty-state compact">Session feed is still loading.</div>`}
      </div>
    </section>
    <section class="tool-section">
      <div class="section-title">Caution windows</div>
      <div class="data-list compact-list">
        ${row("Open", "First 15 minutes: wait for clean structure")}
        ${row("Lunch", "Lower conviction unless range expands")}
        ${row("Close", "Tighten risk into late-session volatility")}
      </div>
    </section>
  `;
}

function renderWindow() {
  const weather = marketWeather();
  const calendar = currentCalendarState();
  const symbols = (dashboardState.symbols || []).map((item) => item.symbol).filter(Boolean);
  return `
    <div class="mood-card ${escapeHtml(weather.tone)}">
      <i data-lucide="${escapeHtml(weather.icon)}"></i>
      <div>
        <span>Market weather</span>
        <strong>${escapeHtml(weather.label)}</strong>
        <p>${escapeHtml(weather.detail)}</p>
      </div>
    </div>
    <div class="metric-grid">
      ${metric("Watchlist", symbols.length || 0, symbols.join(", ") || "No symbols")}
      ${metric("Open positions", dashboardState.summary?.open_positions || 0, money(dashboardState.summary?.unrealized_pl || 0))}
      ${metric("Macro", calendar.events?.length || 0, calendar.events?.[0]?.title || "No macro item loaded")}
      ${metric("Earnings", calendar.earnings?.length || 0, calendar.earnings?.[0]?.symbol || "No watchlist earnings")}
    </div>
    <section class="tool-section">
      <div class="section-title">Window read</div>
      <div class="data-list compact-list">
        ${deskPrepLines().map((line, index) => row(`Note ${index + 1}`, line)).join("")}
      </div>
    </section>
    <section class="tool-section">
      <div class="section-title">Watchlist heat</div>
      ${renderWatchlistHeatStrip()}
    </section>
  `;
}

function renderLamp() {
  const mood = riskMood();
  const health = currentHealthState();
  return `
    <div class="mood-card ${escapeHtml(mood.tone)}">
      <i data-lucide="lamp"></i>
      <div>
        <span>Risk mood light</span>
        <strong>${escapeHtml(mood.headline)}</strong>
        <p>${escapeHtml(mood.detail)}</p>
      </div>
    </div>
    <div class="metric-grid">
      ${metric("Lamp", mood.label, health.summary || "Health summary")}
      ${metric("Risk unit", money(dashboardState.risk?.max_dollar_risk_per_trade), `${percent(dashboardState.risk?.risk_per_trade)} equity cap`)}
      ${metric("Positions", dashboardState.summary?.open_positions || 0, `${dashboardState.risk?.max_open_positions || 0} max`)}
      ${metric("Daily cap", percent(dashboardState.risk?.max_daily_loss_pct), "Stop before damage compounds")}
    </div>
    <section class="tool-section">
      <div class="section-title">Risk ritual</div>
      <div class="data-list compact-list">
        ${row("Before entry", "Location must be valid: 20 SMA, extension, or 200 SMA")}
        ${row("Event risk", eventCountdownState().detail)}
        ${row("After entry", "No losing adds. Trail or reduce on heavy opposing volume")}
        ${row("After exit", "Journal reason, R result, and lesson")}
      </div>
    </section>
    ${renderRiskCommandCenter()}
  `;
}

function renderDrawer() {
  const replay = currentReplayState();
  const symbols = dashboardState.symbols || [];
  const latestReplay = replay.ok && replay.summary ? replay : replay.runs?.[0] || null;
  return `
    <div class="metric-grid">
      ${metric("Replay", latestReplay?.signals_found ?? 0, latestReplay?.summary || "No replay run yet")}
      ${metric("Bars", latestReplay?.bars_loaded ?? 0, "Local scan only")}
      ${metric("Scenarios", "12", "Core, adds, traps, gaps")}
      ${metric("Safety", "No orders", "Replay never submits broker orders")}
    </div>
    <section class="tool-section">
      <div class="section-title">Backtest lab</div>
      <form class="inline-form" id="replay-form">
        <select id="replay-scenario" aria-label="Replay scenario">
          <option value="bull_elephant">Bull elephant sample</option>
          <option value="bear_180">Bear 180 sample</option>
          <option value="buy_setup">Velez buy setup</option>
          <option value="sell_setup">Velez sell setup</option>
          <option value="nrb_acorn">NRB / Acorn</option>
          <option value="color_change_add">Color-change add</option>
          <option value="fab4_trap">Fab 4 trap breakout</option>
          <option value="failed_new_high">Failed new high</option>
          <option value="failed_new_low">Failed new low</option>
          <option value="opening_gap_go">Opening gap go</option>
          <option value="opening_gap_fade">Opening gap fade</option>
          <option value="time_space_breakout">Time + space breakout</option>
        </select>
        <select id="replay-symbol" aria-label="Replay symbol">
          ${(symbols.length ? symbols : [{ symbol: "SPY" }])
            .map((item) => `<option value="${escapeHtml(item.symbol)}">${escapeHtml(item.symbol)}</option>`)
            .join("")}
        </select>
        <button class="icon-button primary" type="submit" title="Run replay" ${replayRunPromise ? "disabled" : ""}>
          <i data-lucide="${replayRunPromise ? "loader" : "play"}"></i>
        </button>
      </form>
      <div class="actions">
        <button class="symbol-button" type="button" data-risk-replay>
          <i data-lucide="calculator"></i>
          Risk replay
        </button>
      </div>
      <div class="data-list compact-list">
        ${row("Risk replay", latestReplay?.risk_replay?.summary || "Run a what-if sizing replay")}
      </div>
    </section>
    ${
      latestReplay?.events?.length
        ? `<div class="replay-list">${latestReplay.events.slice(-5).map(replayEventCard).join("")}</div>`
        : `<div class="empty-state compact">Run a replay to test how the Velez rules classify a sample sequence.</div>`
    }
    ${
      latestReplay?.risk_replay?.variants?.length
        ? `<div class="replay-list">${latestReplay.risk_replay.variants.slice(-5).map((item) => replayEventCard({ ...item, order_type: `risk ${money(item.risk_budget)}`, risk_dollars: item.estimated_risk })).join("")}</div>`
        : ""
    }
  `;
}

function renderNotes() {
  const ritual = todaysRitual();
  return `
    <div class="metric-grid">
      ${metric("Prep", "Live", marketClock().next)}
      ${metric("Watchlist", dashboardState.summary?.symbols_watched || 0, (dashboardState.symbols || []).map((item) => item.symbol).join(", ") || "No symbols")}
      ${metric("Review", currentReviewState().counts?.decisions || 0, currentReviewState().lesson || "After-action ready")}
      ${metric("Ritual", ritual ? "Locked" : "Open", ritual ? timeAgo(ritual.timestamp) : "End day when ready")}
    </div>
    <section class="tool-section">
      <div class="section-title">Bull Report prep card</div>
      <div class="note-stack">
        ${deskPrepLines().map((line) => `<div class="sticky-line">${escapeHtml(line)}</div>`).join("")}
      </div>
    </section>
    ${renderDailyReviewCard("Bull Report after-action review")}
    ${renderCloseReportCard()}
    ${renderEndOfDayRitualCard()}
    <section class="tool-section">
      <div class="section-title">Manual note</div>
      <form id="desk-note-form" class="note-form">
        <textarea id="desk-note" rows="5" placeholder="Write the one rule you must not forget today...">${escapeHtml(deskNote)}</textarea>
        <button class="symbol-button" type="submit"><i data-lucide="save"></i> Save note</button>
      </form>
    </section>
  `;
}

function appleMusicBridgeStatus() {
  return dashboardState.apple_music || fallbackState().apple_music;
}

function appleMusicMissingLabel(missing) {
  if (!missing || missing.length === 0) return "Ready";
  return missing.map((item) => item.replace("APPLE_MUSIC_", "").replaceAll("_", " ")).join(", ");
}

function appleMusicPlayerLabel() {
  if (appleMusicState.authorized) return "Connected";
  if (appleMusicState.status === "connecting") return "Connecting";
  if (appleMusicState.status === "preparing") return "Preparing";
  if (appleMusicState.status === "error") return "Needs check";
  if (appleMusicState.ready) return "Ready";
  return appleMusicBridgeStatus().configured ? "Ready" : "Setup needed";
}

function appleMusicTokenLabel(status) {
  if (!status.configured) return "Missing config";
  return status.key_id_tail ? `Key ...${status.key_id_tail}` : "Server ready";
}

function appleMusicArtworkUrl(artwork, size = 180) {
  if (!artwork?.url) return "";
  if (window.MusicKit?.formatArtworkURL) {
    return window.MusicKit.formatArtworkURL(artwork, size, size);
  }
  return artwork.url.replace("{w}", String(size)).replace("{h}", String(size)).replace("{f}", "jpg");
}

function normalizeAppleMusicItem(item, fallbackKind = "songs") {
  const attributes = item?.attributes || item || {};
  const kind = item?.type || fallbackKind;
  return {
    id: item?.id || attributes.playParams?.id || "",
    kind,
    title: attributes.name || attributes.title || item?.title || "Untitled",
    artist: attributes.artistName || attributes.artist || attributes.curatorName || attributes.editorialNotes?.short || "",
    album: attributes.albumName || "",
    duration: attributes.durationInMillis ? attributes.durationInMillis / 1000 : Number(attributes.duration || item?.duration || 0),
    artwork: appleMusicArtworkUrl(attributes.artwork),
    url: attributes.url || "",
  };
}

function musicQueueKey(kind) {
  const normalized = String(kind || "songs");
  if (normalized.includes("album")) return "album";
  if (normalized.includes("playlist")) return "playlist";
  if (normalized.includes("station")) return "station";
  return "song";
}

function renderArtwork(item) {
  if (item?.artwork) {
    return `<img src="${escapeHtml(item.artwork)}" alt="" />`;
  }
  return `<i data-lucide="music-2"></i>`;
}

function renderPlayerControls() {
  const isPlaying = Boolean(appleMusicState.playback.isPlaying);
  return `
    <div class="player-controls" aria-label="Apple Music controls">
      <button class="icon-button" id="apple-music-prev" type="button" title="Previous">
        <i data-lucide="skip-back"></i>
      </button>
      <button class="icon-button primary" id="apple-music-toggle" type="button" title="${isPlaying ? "Pause" : "Play"}">
        <i data-lucide="${isPlaying ? "pause" : "play"}"></i>
      </button>
      <button class="icon-button" id="apple-music-next" type="button" title="Next">
        <i data-lucide="skip-forward"></i>
      </button>
    </div>
  `;
}

function renderMusicSearchResults() {
  if (appleMusicState.searchStatus === "loading") {
    return `<div class="empty-state compact">Searching Apple Music...</div>`;
  }
  if (appleMusicState.searchStatus === "error") {
    return `<div class="empty-state compact">${escapeHtml(appleMusicState.searchMessage)}</div>`;
  }
  if (!appleMusicState.searchResults.length) {
    return `<div class="empty-state compact">${escapeHtml(appleMusicState.searchMessage)}</div>`;
  }
  return `
    <div class="music-results">
      ${appleMusicState.searchResults
        .map(
          (item) => `
            <article class="music-result">
              <div class="music-result-art">${renderArtwork(item)}</div>
              <div class="music-result-copy">
                <span class="music-result-title">${escapeHtml(item.title)}</span>
                <span class="music-result-meta">${escapeHtml([item.artist, musicQueueKey(item.kind)].filter(Boolean).join(" | "))}</span>
              </div>
              <button class="icon-button" type="button" title="Play" data-music-play="${escapeHtml(item.id)}" data-music-kind="${escapeHtml(item.kind)}">
                <i data-lucide="play"></i>
              </button>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderMusic() {
  const bridge = appleMusicBridgeStatus();
  const configured = Boolean(bridge.configured);
  const connecting = ["connecting", "preparing"].includes(appleMusicState.status);
  const actionLabel = appleMusicState.authorized ? "Reconnect" : "Connect Music";
  const nowPlaying = appleMusicState.nowPlaying;
  const progress = Math.max(0, Math.min(100, Math.round((appleMusicState.playback.progress || 0) * 100)));
  return `
    <div class="metric-grid">
      ${metric("Player", appleMusicPlayerLabel(), appleMusicState.message)}
      ${metric("Now playing", nowPlaying?.title || "No song queued", nowPlaying?.artist || "Pick a result below")}
    </div>
    <div class="music-player">
      <div class="music-artwork">${renderArtwork(nowPlaying)}</div>
      <div class="music-track">
        <span class="music-title">${escapeHtml(nowPlaying?.title || "Trading Bull Desk Player")}</span>
        <span class="music-artist">${escapeHtml(nowPlaying?.artist || (appleMusicState.authorized ? "Ready for playback" : "Authorize Apple Music first"))}</span>
        <div class="music-progress" aria-label="Playback progress">
          <span style="width: ${progress}%"></span>
        </div>
        <div class="music-time">
          <span>${escapeHtml(formatDuration(appleMusicState.playback.currentTime))}</span>
          <span>${escapeHtml(formatDuration(appleMusicState.playback.duration))}</span>
        </div>
      </div>
    </div>
    ${renderPlayerControls()}
    <div class="actions">
      <button class="action-button" id="apple-music-connect" type="button" ${!configured || connecting ? "disabled" : ""}>
        <i data-lucide="${connecting ? "loader" : "radio"}"></i>
        <span>${connecting ? "Connecting" : actionLabel}</span>
      </button>
      ${
        appleMusicState.authorized
          ? `<button class="action-button subtle" id="apple-music-disconnect" type="button">
              <i data-lucide="log-out"></i>
              <span>Sign Out</span>
            </button>`
          : ""
      }
      <a class="text-link" href="${APPLE_MUSIC_URL}" target="_blank" rel="noreferrer">
        <i data-lucide="play"></i>
        <span>Open Player</span>
      </a>
      <a class="text-link" href="${APPLE_MUSIC_FOCUS_URL}" target="_blank" rel="noreferrer">
        <i data-lucide="search"></i>
        <span>Focus Search</span>
      </a>
    </div>
    <form class="music-search" id="apple-music-search-form">
      <input id="apple-music-search-input" type="search" value="${escapeHtml(appleMusicState.searchTerm)}" placeholder="Search songs, albums, playlists" autocomplete="off" />
      <button class="icon-button primary" type="submit" title="Search">
        <i data-lucide="search"></i>
      </button>
    </form>
    ${renderMusicSearchResults()}
    <div class="data-list">
      ${row("iPod", configured ? "MusicKit bridge online" : "Waiting for Apple developer config")}
      ${row("User auth", appleMusicState.authorized ? "Authorized in this browser" : appleMusicState.ready ? "Ready for authorization" : "Click Connect Music")}
      ${row("Token bridge", configured ? appleMusicTokenLabel(bridge) : "Not available yet")}
      ${row("Origin lock", bridge.origin_locked ? "On for this bot URL" : "Off")}
      ${row("Expires", expiresIn(appleMusicState.expiresAt))}
    </div>
  `;
}

function activePanelIsMusic() {
  return activePanel === "music";
}

function refreshMusicPanel() {
  if (activePanelIsMusic()) {
    if (document.activeElement?.closest?.("#apple-music-search-form")) return;
    renderPanel();
    updateActiveChrome();
  }
}

function musicInstance() {
  try {
    return appleMusicInstance || window.MusicKit?.getInstance?.() || null;
  } catch (error) {
    return appleMusicInstance || null;
  }
}

function appleMusicAuthorized(music = musicInstance()) {
  if (appleMusicState.authorized) return true;
  const value = music?.isAuthorized;
  if (typeof value === "boolean") return value;
  if (typeof value === "function") {
    try {
      const result = value.call(music);
      return typeof result === "boolean" ? result : false;
    } catch (error) {
      return false;
    }
  }
  return false;
}

function appleMusicStorefront() {
  return musicInstance()?.storefrontId || "us";
}

function updateNowPlayingFromMusic(music = musicInstance()) {
  if (!music) return;
  const item = music.nowPlayingItem ? normalizeAppleMusicItem(music.nowPlayingItem) : null;
  const duration = Number(music.currentPlaybackDuration || item?.duration || 0);
  const currentTime = Number(music.currentPlaybackTime || 0);
  const progress = duration > 0 ? currentTime / duration : Number(music.currentPlaybackProgress || 0);
  appleMusicState.nowPlaying = item;
  appleMusicState.playback = {
    isPlaying: Boolean(music.isPlaying),
    currentTime,
    duration,
    progress: Number.isFinite(progress) ? progress : 0,
    volume: Number.isFinite(Number(music.volume)) ? Number(music.volume) : appleMusicState.playback.volume,
  };
}

function startAppleMusicPolling() {
  if (appleMusicPollTimer) return;
  appleMusicPollTimer = setInterval(() => {
    updateNowPlayingFromMusic();
    refreshMusicPanel();
  }, 1500);
}

async function fetchAppleMusicDeveloperToken() {
  const response = await fetch("/api/apple-music/developer-token", { cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok || !data.developer_token) {
    throw new Error(data.reason || `developer token request failed (${response.status})`);
  }
  appleMusicState.expiresAt = data.expires_at || null;
  return data.developer_token;
}

function loadMusicKitScript() {
  if (window.MusicKit) return Promise.resolve(window.MusicKit);
  if (appleMusicScriptPromise) return appleMusicScriptPromise;

  appleMusicScriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${APPLE_MUSIC_SCRIPT_URL}"]`);
    const finish = () => {
      if (window.MusicKit) resolve(window.MusicKit);
      else reject(new Error("MusicKit script loaded without MusicKit"));
    };

    window.addEventListener("musickitloaded", finish, { once: true });
    if (existing) {
      existing.addEventListener("load", finish, { once: true });
      existing.addEventListener("error", () => reject(new Error("MusicKit script failed to load")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = APPLE_MUSIC_SCRIPT_URL;
    script.async = true;
    script.addEventListener("load", finish, { once: true });
    script.addEventListener("error", () => reject(new Error("MusicKit script failed to load")), { once: true });
    document.head.append(script);
  });

  return appleMusicScriptPromise;
}

async function ensureAppleMusicReady() {
  if (appleMusicInstance && typeof appleMusicInstance.authorize === "function") {
    appleMusicState.ready = true;
    return appleMusicInstance;
  }
  if (appleMusicReadyPromise) return appleMusicReadyPromise;

  appleMusicReadyPromise = (async () => {
    const developerToken = await fetchAppleMusicDeveloperToken();
    const MusicKit = await loadMusicKitScript();
    const configured = MusicKit.configure({
      developerToken,
      app: {
        name: "Trading Bull Desk",
        build: APP_BUILD,
      },
    });
    if (configured && typeof configured.then === "function") {
      await configured;
    }

    appleMusicInstance = MusicKit.getInstance?.();
    if (!appleMusicInstance || typeof appleMusicInstance.authorize !== "function") {
      throw new Error("MusicKit authorization is unavailable in this browser");
    }

    appleMusicState.ready = true;
    updateNowPlayingFromMusic(appleMusicInstance);
    return appleMusicInstance;
  })();

  try {
    return await appleMusicReadyPromise;
  } catch (error) {
    appleMusicReadyPromise = null;
    appleMusicInstance = null;
    appleMusicState.ready = false;
    throw error;
  }
}

function prepareAppleMusic() {
  const bridge = appleMusicBridgeStatus();
  if (!bridge.configured || appleMusicState.ready || appleMusicState.authorized || appleMusicReadyPromise) return;

  appleMusicState.status = "preparing";
  appleMusicState.message = "Preparing MusicKit authorization";
  refreshMusicPanel();

  ensureAppleMusicReady()
    .then(() => {
      if (!appleMusicState.authorized) {
        appleMusicState.status = "idle";
        appleMusicState.message = "Ready to authorize Apple Music";
      }
      refreshMusicPanel();
    })
    .catch((error) => {
      appleMusicState.status = "error";
      appleMusicState.message = error?.message || "MusicKit setup failed";
      refreshMusicPanel();
    });
}

function authorizeAppleMusic(music) {
  if (appleMusicAuthorized(music)) return Promise.resolve();
  return music.authorize();
}

function withAppleMusicTimeout(promise) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      reject(new Error("Apple Music authorization did not finish. Allow pop-ups, then try Connect Music again."));
    }, 90000);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function connectAppleMusic() {
  appleMusicState.status = "connecting";
  appleMusicState.message = appleMusicState.ready ? "Opening Apple Music authorization" : "Preparing MusicKit authorization";

  try {
    let music = appleMusicInstance;
    let authorizationPromise = null;

    if (music && typeof music.authorize === "function") {
      authorizationPromise = authorizeAppleMusic(music);
      renderPanel();
    } else {
      renderPanel();
      music = await ensureAppleMusicReady();
      authorizationPromise = authorizeAppleMusic(music);
    }

    await withAppleMusicTimeout(authorizationPromise);

    appleMusicState.status = "connected";
    appleMusicState.authorized = true;
    appleMusicState.ready = true;
    appleMusicState.message = "Apple Music authorized in this browser";
    startAppleMusicPolling();
    updateNowPlayingFromMusic(music);
  } catch (error) {
    appleMusicState.status = "error";
    appleMusicState.authorized = false;
    appleMusicState.ready = Boolean(appleMusicInstance && typeof appleMusicInstance.authorize === "function");
    appleMusicState.message = error?.message || "Apple Music connection failed";
  }

  renderPanel();
}

function musicAuthRequired() {
  if (appleMusicState.authorized) return false;
  appleMusicState.message = "Authorize Apple Music to play inside the desk";
  return true;
}

async function searchAppleMusic(event) {
  event?.preventDefault();
  const input = $("#apple-music-search-input");
  const term = (input?.value || appleMusicState.searchTerm || "").trim();
  if (!term) return;

  appleMusicState.searchTerm = term;
  localStorage.setItem("trading-bull-music-search", term);
  appleMusicState.searchStatus = "loading";
  appleMusicState.searchMessage = "Searching Apple Music...";
  renderPanel();

  try {
    const items = await fetchAppleMusicItems(term, 6);
    appleMusicState.searchResults = items.slice(0, 8);
    appleMusicState.searchStatus = items.length ? "ready" : "idle";
    appleMusicState.searchMessage = items.length ? "Choose a result to play" : "No Apple Music results found";
  } catch (error) {
    appleMusicState.searchStatus = "error";
    appleMusicState.searchMessage = error?.message || "Apple Music search failed";
  }

  renderPanel();
}

async function fetchAppleMusicItems(term, limit = 6) {
  const storefront = appleMusicStorefront();
  const response = await fetch(
    `/api/apple-music/search?term=${encodeURIComponent(term)}&storefront=${encodeURIComponent(storefront)}&limit=${encodeURIComponent(limit)}`,
    { cache: "no-store" },
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.reason || `Apple Music search failed (${response.status})`);
  }
  const results = data.results || {};
  return [
    ...(results?.songs?.data || []).map((item) => normalizeAppleMusicItem(item, "songs")),
    ...(results?.albums?.data || []).map((item) => normalizeAppleMusicItem(item, "albums")),
    ...(results?.playlists?.data || []).map((item) => normalizeAppleMusicItem(item, "playlists")),
  ];
}

function preferredMusicItem(items, kind) {
  const normalized = String(kind || "auto").toLowerCase();
  if (normalized.includes("album")) return items.find((item) => musicQueueKey(item.kind) === "album") || items[0];
  if (normalized.includes("playlist")) return items.find((item) => musicQueueKey(item.kind) === "playlist") || items[0];
  if (normalized.includes("song") || normalized.includes("track")) return items.find((item) => musicQueueKey(item.kind) === "song") || items[0];
  return items[0];
}

async function playAppleMusicSearch(query, kind = "auto") {
  const term = String(query || "").trim();
  if (!term) return "I need a song, artist, album, or playlist name first.";
  const bridge = appleMusicBridgeStatus();
  if (!bridge.configured) return "Apple Music is not configured on this bot yet.";

  appleMusicState.searchTerm = term;
  localStorage.setItem("trading-bull-music-search", term);
  appleMusicState.searchStatus = "loading";
  appleMusicState.searchMessage = `Searching Apple Music for ${term}`;
  refreshMusicPanel();

  try {
    const items = await fetchAppleMusicItems(term, 8);
    appleMusicState.searchResults = items.slice(0, 8);
    appleMusicState.searchStatus = items.length ? "ready" : "idle";
    appleMusicState.searchMessage = items.length ? "Choose a result to play" : "No Apple Music results found";
    const selected = preferredMusicItem(items, kind);
    if (!selected) return `I could not find ${term} on Apple Music.`;

    if (!appleMusicAuthorized()) {
      appleMusicState.status = appleMusicState.ready ? "idle" : "preparing";
      appleMusicState.message = `Found ${selected.title}. Connect Music once to play from Winston.`;
      refreshMusicPanel();
      return `I found ${selected.title}${selected.artist ? ` by ${selected.artist}` : ""}. Click Connect Music on the iPod once, then ask me again and I can play it here.`;
    }

    const played = await playAppleMusicItem(selected.id, selected.kind, { allowAuthorize: false });
    if (!played) return `Apple Music needs attention: ${appleMusicState.message}.`;
    return `Queued ${selected.title}${selected.artist ? ` by ${selected.artist}` : ""} on the desk iPod.`;
  } catch (error) {
    appleMusicState.searchStatus = "error";
    appleMusicState.message = error?.message || "Apple Music command failed";
    appleMusicState.searchMessage = appleMusicState.message;
    refreshMusicPanel();
    return `Apple Music needs attention: ${appleMusicState.message}.`;
  }
}

async function playAppleMusicItem(id, kind, options = {}) {
  if (!id) return false;
  const allowAuthorize = options.allowAuthorize !== false;
  appleMusicState.status = "connecting";
  appleMusicState.message = appleMusicAuthorized() ? "Loading Apple Music queue" : "Authorize Apple Music to play";
  renderPanel();

  try {
    let music = await ensureAppleMusicReady();
    if (!appleMusicAuthorized(music)) {
      if (!allowAuthorize) {
        appleMusicState.status = "idle";
        appleMusicState.message = "Connect Music once before Winston can play Apple Music.";
        renderPanel();
        return false;
      }
      await connectAppleMusic();
      music = musicInstance() || music;
      if (!appleMusicAuthorized(music)) {
        appleMusicState.status = "idle";
        appleMusicState.message = "Apple Music authorization is still needed.";
        renderPanel();
        return false;
      }
    }
    appleMusicState.authorized = true;
    const queueKey = musicQueueKey(kind);
    await music.setQueue({ [queueKey]: id });
    await music.play();
    appleMusicState.status = "connected";
    appleMusicState.message = "Playing inside Trading Bull Desk";
    updateNowPlayingFromMusic(music);
    startAppleMusicPolling();
    renderPanel();
    return true;
  } catch (error) {
    appleMusicState.status = "error";
    appleMusicState.message = error?.message || "Apple Music playback failed";
  }

  renderPanel();
  return false;
}

async function toggleAppleMusicPlayback() {
  try {
    const music = await ensureAppleMusicReady();
    if (!appleMusicAuthorized(music)) {
      await connectAppleMusic();
      if (!appleMusicAuthorized(music)) return;
    }
    appleMusicState.authorized = true;
    if (music.isPlaying) {
      await music.pause();
      appleMusicState.message = "Paused";
    } else if (music.nowPlayingItem) {
      await music.play();
      appleMusicState.message = "Playing inside Trading Bull Desk";
    } else if (appleMusicState.searchResults[0]) {
      await playAppleMusicItem(appleMusicState.searchResults[0].id, appleMusicState.searchResults[0].kind);
      return;
    } else {
      await searchAppleMusic();
      return;
    }
    updateNowPlayingFromMusic(music);
  } catch (error) {
    appleMusicState.status = "error";
    appleMusicState.message = error?.message || "Apple Music control failed";
  }

  renderPanel();
}

async function skipAppleMusic(direction, options = {}) {
  try {
    const music = await ensureAppleMusicReady();
    if (!appleMusicAuthorized(music)) {
      if (options.allowAuthorize === false) {
        appleMusicState.status = "idle";
        appleMusicState.message = "Connect Music once before Winston can skip Apple Music.";
        renderPanel();
        return false;
      }
      await connectAppleMusic();
      if (!appleMusicAuthorized(music)) return false;
    }
    appleMusicState.authorized = true;
    if (direction === "next" && typeof music.skipToNextItem === "function") {
      await music.skipToNextItem();
    } else if (direction === "previous" && typeof music.skipToPreviousItem === "function") {
      await music.skipToPreviousItem();
    }
    updateNowPlayingFromMusic(music);
  } catch (error) {
    appleMusicState.status = "error";
    appleMusicState.message = error?.message || "Apple Music skip failed";
  }

  renderPanel();
  return true;
}

async function setAppleMusicVolume(action) {
  try {
    const music = await ensureAppleMusicReady();
    const current = Number(music.volume ?? appleMusicState.playback.volume ?? 1);
    let next = Number(action?.value);
    if (!Number.isFinite(next)) {
      next = current + (action?.direction === "down" ? -0.12 : 0.12);
    }
    next = Math.max(0, Math.min(1, next));
    music.volume = next;
    appleMusicState.playback = { ...appleMusicState.playback, volume: next };
    appleMusicState.message = `Volume ${Math.round(next * 100)}%`;
    refreshMusicPanel();
    return appleMusicState.message;
  } catch (error) {
    appleMusicState.status = "error";
    appleMusicState.message = error?.message || "Apple Music volume failed";
    refreshMusicPanel();
    return `Apple Music volume needs attention: ${appleMusicState.message}.`;
  }
}

async function pauseAppleMusic() {
  try {
    const music = await ensureAppleMusicReady();
    if (music.pause) await music.pause();
    updateNowPlayingFromMusic(music);
    appleMusicState.message = "Paused";
    refreshMusicPanel();
    return "The desk iPod is paused.";
  } catch (error) {
    appleMusicState.status = "error";
    appleMusicState.message = error?.message || "Apple Music pause failed";
    refreshMusicPanel();
    return `Apple Music pause needs attention: ${appleMusicState.message}.`;
  }
}

async function resumeAppleMusic() {
  try {
    const music = await ensureAppleMusicReady();
    if (!appleMusicAuthorized(music)) {
      appleMusicState.status = "idle";
      appleMusicState.message = "Connect Music once before Winston can resume Apple Music.";
      refreshMusicPanel();
      return "Apple Music needs Connect Music first.";
    }
    if (music.play) await music.play();
    appleMusicState.authorized = true;
    appleMusicState.message = "Playing inside Trading Bull Desk";
    updateNowPlayingFromMusic(music);
    startAppleMusicPolling();
    refreshMusicPanel();
    return "The desk iPod is playing.";
  } catch (error) {
    appleMusicState.status = "error";
    appleMusicState.message = error?.message || "Apple Music resume failed";
    refreshMusicPanel();
    return `Apple Music resume needs attention: ${appleMusicState.message}.`;
  }
}

function nowPlayingReadback() {
  updateNowPlayingFromMusic();
  const item = appleMusicState.nowPlaying;
  if (!item) return "Nothing is playing on the desk iPod right now.";
  return `Now playing: ${item.title}${item.artist ? ` by ${item.artist}` : ""}.`;
}

async function handleWinstonActions(actions = []) {
  const updates = [];
  for (const action of actions || []) {
    if (!action || !action.type) continue;
    if (action.type.startsWith("music.") && activePanel !== "music") {
      setActivePanel("music");
    }
    if (action.type === "panel.open") {
      setActivePanel(action.panel);
      continue;
    }
    if (action.type === "music.play_search") {
      updates.push(await playAppleMusicSearch(action.query, action.kind));
      continue;
    }
    if (action.type === "music.pause") {
      updates.push(await pauseAppleMusic());
      continue;
    }
    if (action.type === "music.resume") {
      updates.push(await resumeAppleMusic());
      continue;
    }
    if (action.type === "music.next") {
      const skipped = await skipAppleMusic("next", { allowAuthorize: false });
      updates.push(skipped ? "Skipped to the next iPod track." : "Apple Music needs Connect Music first.");
      continue;
    }
    if (action.type === "music.previous") {
      const skipped = await skipAppleMusic("previous", { allowAuthorize: false });
      updates.push(skipped ? "Went back one iPod track." : "Apple Music needs Connect Music first.");
      continue;
    }
    if (action.type === "music.volume") {
      updates.push(await setAppleMusicVolume(action));
      continue;
    }
    if (action.type === "music.now_playing") {
      updates.push(nowPlayingReadback());
    }
  }
  return updates.filter(Boolean);
}

async function disconnectAppleMusic() {
  try {
    const music = appleMusicInstance || window.MusicKit?.getInstance?.();
    if (music?.unauthorize) await music.unauthorize();
  } finally {
    appleMusicState.status = "idle";
    appleMusicState.authorized = false;
    appleMusicState.message = appleMusicState.ready ? "Ready to authorize Apple Music" : "Signed out of Apple Music in this browser";
    renderPanel();
  }
}

function applyWinstonRuntime(payload = {}) {
  if (payload.brain) winstonState.brain = { ...winstonState.brain, ...payload.brain };
  if (payload.voice) winstonState.voice = { ...winstonState.voice, ...payload.voice };
  if (["ollama", "openai_compatible", "winston_rule_based_v1"].includes(payload.provider)) {
    winstonState.brain = {
      ...winstonState.brain,
      provider: payload.provider,
      model: payload.model || winstonState.brain.model,
      available: payload.degraded ? false : winstonState.brain.available,
      detail: payload.degraded ? payload.fallback_reason || "AI fallback used" : winstonState.brain.detail,
    };
  }
}

async function refreshWinstonStatus() {
  try {
    const response = await fetch("/api/winston/status", { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `status ${response.status}`);
    applyWinstonRuntime(data);
  } catch (error) {
    winstonState.brain = {
      ...winstonState.brain,
      available: winstonState.brain.provider === "winston_rule_based_v1",
      detail: error?.message || "Winston status unavailable",
    };
  }
  refreshWinstonPanel();
}

function winstonBrainLabel() {
  const provider = winstonState.brain?.provider || "winston_rule_based_v1";
  const model = String(winstonState.brain?.model || "").toLowerCase();
  if (provider === "ollama") return "Hermes local LLM";
  if (provider === "openai_compatible" && model.includes("deepseek")) return "DeepSeek hybrid";
  if (provider === "openai_compatible") return "AI provider";
  if (provider === "winston_trade_guardrail_v1") return "Trade guardrail";
  if (provider === "winston_rule_based_v1") return "Safe local rules";
  return provider.replaceAll("_", " ");
}

function winstonBrainDetail() {
  const brain = winstonState.brain || {};
  const fallback = brain.fallback?.configured
    ? `fallback ${brain.fallback.model || brain.fallback.provider}`
    : "";
  const thinking = brain.thinking ? `thinking ${brain.thinking}` : "";
  return [brain.model, thinking, fallback, brain.detail].filter(Boolean).join(" | ") || "Winston ready";
}

function winstonVoiceLabel() {
  const voice = winstonState.voice || {};
  if (voice.provider === "pockettts" && voice.configured) return "Hermes PocketTTS";
  if (!("speechSynthesis" in window)) return "Voice output unavailable";
  if (!SpeechRecognitionApi) return "Browser voice output";
  return "Browser input and output";
}

function winstonVoiceDetail() {
  const voice = winstonState.voice || {};
  if (voice.provider === "pockettts" && voice.configured) {
    return [voice.voice, voice.available ? "Server voice ready" : "Server voice fallback"].filter(Boolean).join(" | ");
  }
  return winstonState.muted ? "Muted" : "Speaker ready";
}

function winstonTranscript(role, text) {
  winstonState.transcript.unshift({
    role,
    text,
    timestamp: new Date().toISOString(),
  });
  winstonState.transcript = winstonState.transcript.slice(0, 10);
}

function pendingApprovals() {
  return dashboardState.pending_approvals || [];
}

function approvalLine(item) {
  return `${item.symbol || "Symbol"} ${String(item.side || "").toUpperCase()} ${item.qty || 0} | Entry ${item.entry_price || "mkt"} | Stop ${item.stop_price || "n/a"}`;
}

function dailyBriefFallback() {
  const broker = dashboardState.broker || {};
  const symbols = (dashboardState.symbols || []).map((item) => item.symbol).filter(Boolean).join(", ") || "No symbols";
  const latest = latestDecision();
  const pending = pendingApprovals();
  return [
    `Trading Bull Desk is ${dashboardState.execution_armed ? "armed for paper execution" : "in proposal mode"}.`,
    `Broker status is ${broker.ok ? "connected to Alpaca Paper" : `not ready: ${broker.reason || "needs check"}`}.`,
    `Watchlist: ${symbols}.`,
    `${dashboardState.summary?.open_positions || 0} open positions with ${money(dashboardState.summary?.unrealized_pl || 0)} unrealized P/L.`,
    latest ? `Latest alert: ${latest.symbol || "symbol"} ${latest.play || latest.reason || "decision"} ${timeAgo(latest.timestamp)}.` : "No TradingView alerts have reached the journal yet.",
    pending.length ? `${pending.length} paper order approval is staged. Exact phrase: ${pending[0].approval_phrase}.` : "No paper orders are waiting for guarded approval.",
  ].join(" ");
}

function stopWinstonAudio() {
  winstonState.speechRequestId += 1;
  if (winstonState.audio) {
    try {
      winstonState.audio.pause();
      if (winstonState.audio.src?.startsWith("blob:")) URL.revokeObjectURL(winstonState.audio.src);
    } catch (error) {
      // Audio cleanup is best-effort; browser support varies.
    }
    winstonState.audio = null;
  }
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  winstonState.speaking = false;
}

function speakBrowserWinston(text) {
  if (winstonState.muted || !("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new window.SpeechSynthesisUtterance(text);
  utterance.rate = 0.96;
  utterance.pitch = 0.92;
  utterance.onstart = () => {
    winstonState.speaking = true;
    refreshWinstonPanel();
  };
  utterance.onend = () => {
    winstonState.speaking = false;
    refreshWinstonPanel();
  };
  utterance.onerror = () => {
    winstonState.speaking = false;
    refreshWinstonPanel();
  };
  window.speechSynthesis.speak(utterance);
}

async function speakWinston(text) {
  if (winstonState.muted) return;
  const voice = winstonState.voice || {};
  const speechId = winstonState.speechRequestId + 1;
  stopWinstonAudio();
  winstonState.speechRequestId = speechId;

  if (voice.provider === "pockettts" && voice.configured) {
    try {
      winstonState.speaking = true;
      refreshWinstonPanel();
      const response = await fetch("/api/winston/speech", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) throw new Error(`server voice ${response.status}`);
      const blob = await response.blob();
      if (!blob.size) throw new Error("empty audio response");
      if (speechId !== winstonState.speechRequestId) return;
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      winstonState.audio = audio;
      audio.onended = () => {
        if (speechId === winstonState.speechRequestId) {
          URL.revokeObjectURL(url);
          winstonState.audio = null;
          winstonState.speaking = false;
          refreshWinstonPanel();
        }
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        winstonState.audio = null;
        winstonState.speaking = false;
        speakBrowserWinston(text);
      };
      await audio.play();
      return;
    } catch (error) {
      winstonState.voice = {
        ...winstonState.voice,
        available: false,
        detail: error?.message || "Server voice fallback",
      };
      winstonState.speaking = false;
      refreshWinstonPanel();
    }
  }

  speakBrowserWinston(text);
}

function refreshWinstonPanel() {
  if (activePanel === "phone") {
    renderPanel();
    updateActiveChrome();
  }
}

function startWinstonCall() {
  winstonState.callActive = true;
  winstonState.status = "connected";
  winstonState.message = "Opening morning call";
  winstonTranscript("winston", "Winston here. Opening the morning call.");
  renderPanel();
  requestWinstonMorningCall();
}

function endWinstonCall() {
  if (winstonState.recognition) {
    winstonState.recognition.stop();
    winstonState.recognition = null;
  }
  stopWinstonAudio();
  winstonState.callActive = false;
  winstonState.listening = false;
  winstonState.speaking = false;
  winstonState.status = "idle";
  winstonState.message = "Phone line ready";
  winstonTranscript("system", "Call ended.");
  renderPanel();
}

function toggleWinstonMute() {
  winstonState.muted = !winstonState.muted;
  if (winstonState.muted) stopWinstonAudio();
  winstonState.message = winstonState.muted ? "Speaker muted" : "Speaker live";
  renderPanel();
}

async function requestWinstonBrief() {
  winstonState.status = "thinking";
  winstonState.message = "Preparing daily desk brief";
  renderPanel();
  try {
    const response = await fetch("/api/winston/brief", { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `brief failed (${response.status})`);
    applyWinstonRuntime(data);
    const text = data.summary || dailyBriefFallback();
    winstonState.status = "connected";
    winstonState.message = "Daily brief ready";
    winstonTranscript("winston", text);
    speakWinston(text);
  } catch (error) {
    const text = dailyBriefFallback();
    winstonState.status = "connected";
    winstonState.message = error?.message || "Using local desk brief";
    winstonTranscript("winston", text);
    speakWinston(text);
  }
  renderPanel();
}

async function requestWinstonMorningCall() {
  if (!winstonState.callActive) winstonState.callActive = true;
  winstonState.status = "thinking";
  winstonState.message = "Preparing morning call";
  renderPanel();
  try {
    const response = await fetch("/api/winston/morning-call", { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `morning call failed (${response.status})`);
    applyWinstonRuntime(data);
    const text = data.summary || dailyBriefFallback();
    winstonState.status = "connected";
    winstonState.message = "Morning call ready";
    winstonTranscript("winston", text);
    speakWinston(text);
  } catch (error) {
    const text = `Morning call fallback. ${dailyBriefFallback()}`;
    winstonState.status = "connected";
    winstonState.message = error?.message || "Using local morning call";
    winstonTranscript("winston", text);
    speakWinston(text);
  }
  renderPanel();
}

async function requestWinstonResearch(options = {}) {
  const deep = Boolean(options.deep);
  if (!winstonState.callActive) winstonState.callActive = true;
  const input = $("#winston-input");
  const topic = (input?.value || "daily prep for the watchlist").trim();
  if (input) input.value = "";
  winstonTranscript("you", `${deep ? "Deep research" : "Research"}: ${topic}`);
  winstonState.status = "thinking";
  winstonState.message = deep ? "Deep Research is building a memo" : "Research Mode is gathering context";
  renderPanel();
  try {
    const response = await fetch(deep ? "/api/winston/deep-research" : "/api/winston/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `research failed (${response.status})`);
    applyWinstonRuntime(data);
    winstonState.status = "connected";
    winstonState.message = data.degraded ? "Research fallback ready" : deep ? "Deep research memo ready" : "Research note ready";
    winstonTranscript("winston", data.reply || "Research Mode did not return a note.");
    speakWinston(data.reply || "Research Mode did not return a note.");
  } catch (error) {
    const fallback = `Research Mode could not complete that request: ${error?.message || "unknown error"}.`;
    winstonState.status = "connected";
    winstonState.message = "Research unavailable";
    winstonTranscript("winston", fallback);
    speakWinston(fallback);
  }
  renderPanel();
}

async function approvePendingOrder(id, phrase) {
  const token = approvalToken.trim();
  if (!token) {
    winstonState.message = "Approval token needed";
    winstonTranscript("system", "Enter the approval token in the phone panel before submitting a staged paper order.");
    renderPanel();
    return;
  }
  winstonState.status = "thinking";
  winstonState.message = "Submitting guarded paper approval";
  renderPanel();
  try {
    const response = await fetch(`/api/orders/pending/${encodeURIComponent(id)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_phrase: phrase, approval_token: token }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `approval failed (${response.status})`);
    winstonState.status = "connected";
    winstonState.message = "Paper order submitted";
    winstonTranscript("winston", `${approvalLine(data.pending || {})} has been submitted to Alpaca paper.`);
    speakWinston(`${data.pending?.symbol || "The staged order"} has been submitted to Alpaca paper.`);
    await refreshState();
  } catch (error) {
    winstonState.status = "connected";
    winstonState.message = error?.message || "Approval blocked";
    winstonTranscript("winston", `Approval blocked: ${winstonState.message}.`);
    speakWinston(`Approval blocked: ${winstonState.message}.`);
  }
  renderPanel();
}

function approvalPhraseFromPrompt(prompt) {
  const match = String(prompt || "").match(/\bapprove\s+paper\s+order\s+([a-f0-9]{8})\b/i);
  if (!match) return null;
  const id = match[1].toUpperCase();
  const pending = pendingApprovals().find((item) => item.id === id);
  return pending ? { id, phrase: pending.approval_phrase } : { id, phrase: `APPROVE PAPER ORDER ${id}` };
}

async function sendWinstonPrompt(prompt) {
  const text = String(prompt || "").trim();
  if (!text) return;
  if (!winstonState.callActive) winstonState.callActive = true;
  winstonTranscript("you", text);
  const approval = approvalPhraseFromPrompt(text);
  if (approval) {
    await approvePendingOrder(approval.id, approval.phrase);
    return;
  }
  winstonState.status = "thinking";
  winstonState.message = "Winston is checking the desk";
  renderPanel();
  try {
    const response = await fetch("/api/winston/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `message failed (${response.status})`);
    applyWinstonRuntime(data);
    winstonState.status = "connected";
    winstonState.message = data.intent || "Response ready";
    const reply = data.reply || dailyBriefFallback();
    winstonTranscript("winston", reply);
    speakWinston(reply);
    const actionUpdates = await handleWinstonActions(data.actions || []);
    actionUpdates.forEach((line) => winstonTranscript("winston", line));
    if (actionUpdates.length) speakWinston(actionUpdates.at(-1));
  } catch (error) {
    const fallback = localWinstonReply(text);
    winstonState.status = "connected";
    winstonState.message = error?.message || "Local response ready";
    winstonTranscript("winston", fallback);
    speakWinston(fallback);
  }
  renderPanel();
}

function localWinstonReply(prompt) {
  const text = prompt.toLowerCase();
  const symbols = (dashboardState.symbols || []).map((item) => item.symbol).filter(Boolean).join(", ") || "No symbols configured";
  if (text.includes("mission")) {
    const mission = dailyMission();
    return `Daily mission: ${mission.title}. ${mission.rule} ${mission.countdown.detail}`;
  }
  if (text.includes("review") || text.includes("after action")) {
    const review = currentReviewState();
    return `${review.lines?.join(" ") || review.summary || "No review loaded yet"} ${review.lesson || ""}`.trim();
  }
  if (text.includes("morning call")) return `Morning call fallback. ${dailyBriefFallback()}`;
  if (text.includes("brief") || text.includes("daily") || text.includes("morning")) return dailyBriefFallback();
  if (text.includes("watch")) return `Current watchlist is ${symbols}. I am watching for qualified Velez setups only.`;
  if (text.includes("position") || text.includes("p/l") || text.includes("profit")) {
    return `${dashboardState.summary?.open_positions || 0} positions are open with ${money(dashboardState.summary?.unrealized_pl || 0)} unrealized P/L.`;
  }
  if (text.includes("risk")) {
    return `Risk is capped at ${money(dashboardState.risk?.max_dollar_risk_per_trade)} per trade, ${dashboardState.risk?.max_open_positions || 0} max open positions, and ${percent(dashboardState.risk?.max_daily_loss_pct)} daily loss cap.`;
  }
  if (text.includes("approve") || text.includes("trade") || text.includes("order")) {
    const pending = pendingApprovals();
    if (pending.length) return `Trade approval is guarded. The staged paper order is ${approvalLine(pending[0])}. Say or type exactly: ${pending[0].approval_phrase}.`;
    return "Trade approval is guarded. No paper order is staged right now. A TradingView proposal must create a pending approval before I can submit anything.";
  }
  return "I can brief the desk, research the watchlist, check positions, summarize risk, or read back guarded paper-trade approvals.";
}

function toggleWinstonListening() {
  if (!SpeechRecognitionApi) {
    winstonState.message = "Voice input is not available in this browser";
    winstonTranscript("system", "Voice input is not available here. Type into the phone prompt instead.");
    renderPanel();
    return;
  }
  if (winstonState.listening && winstonState.recognition) {
    winstonState.recognition.stop();
    return;
  }

  const recognition = new SpeechRecognitionApi();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = "en-US";
  recognition.onstart = () => {
    winstonState.listening = true;
    winstonState.message = "Listening";
    refreshWinstonPanel();
  };
  recognition.onresult = (event) => {
    const transcript = Array.from(event.results || [])
      .map((result) => result[0]?.transcript || "")
      .join(" ")
      .trim();
    if (transcript) sendWinstonPrompt(transcript);
  };
  recognition.onerror = (event) => {
    winstonState.message = event?.error ? `Voice input: ${event.error}` : "Voice input stopped";
    winstonTranscript("system", winstonState.message);
  };
  recognition.onend = () => {
    winstonState.listening = false;
    winstonState.recognition = null;
    refreshWinstonPanel();
  };
  winstonState.recognition = recognition;
  recognition.start();
}

function renderTranscript() {
  return winstonState.transcript
    .map(
      (item) => `
        <article class="transcript-line ${escapeHtml(item.role)}">
          <span>${escapeHtml(item.role === "you" ? "You" : item.role === "system" ? "System" : "Winston")}</span>
          <p>${escapeHtml(item.text)}</p>
        </article>
      `,
    )
    .join("");
}

function renderPhone() {
  const connected = winstonState.callActive;
  const listening = winstonState.listening;
  const speaking = winstonState.speaking;
  const pending = pendingApprovals();
  const lifecycle = currentLifecycleState();
  return `
    <div class="metric-grid">
      ${metric("Line", connected ? "Connected" : "Standby", winstonState.message)}
      ${metric("Brain", winstonBrainLabel(), winstonBrainDetail())}
      ${metric("Voice", winstonVoiceLabel(), winstonVoiceDetail())}
      ${metric("Broker", dashboardState.broker?.ok ? "Alpaca Paper" : "Needs check", dashboardState.execution_armed ? "Paper execution armed" : "Proposal mode")}
      ${metric("Approvals", pending.length, pending[0]?.approval_phrase || "No staged paper order")}
      ${metric("Lifecycle", lifecycle.summary?.open_positions || 0, lifecycle.readback || "No active trade readback")}
      ${metric("Watchlist", dashboardState.summary?.symbols_watched || 0, (dashboardState.symbols || []).map((item) => item.symbol).filter(Boolean).join(", ") || "None")}
    </div>
    <div class="call-card ${connected ? "connected" : ""}">
      <div class="call-orb ${listening ? "listening" : speaking ? "speaking" : ""}">
        <i data-lucide="${connected ? "phone-call" : "phone"}"></i>
      </div>
      <div class="call-copy">
        <span class="call-name">Winston</span>
        <span class="call-status">${escapeHtml(connected ? (listening ? "Listening" : speaking ? "Speaking" : "On the line") : "Tap call to connect")}</span>
      </div>
      <div class="call-wave" aria-hidden="true"><span></span><span></span><span></span><span></span></div>
    </div>
    <div class="actions">
      <button class="action-button" id="winston-call-toggle" type="button">
        <i data-lucide="${connected ? "phone-off" : "phone-call"}"></i>
        <span>${connected ? "End Call" : "Call Winston"}</span>
      </button>
      <button class="action-button subtle" id="winston-listen" type="button" ${connected ? "" : "disabled"}>
        <i data-lucide="${listening ? "mic-off" : "mic"}"></i>
        <span>${listening ? "Stop" : "Speak"}</span>
      </button>
      <button class="action-button subtle" id="winston-brief" type="button" ${connected ? "" : "disabled"}>
        <i data-lucide="newspaper"></i>
        <span>Daily Brief</span>
      </button>
      <button class="action-button subtle" id="winston-morning-call" type="button" ${connected ? "" : "disabled"}>
        <i data-lucide="sunrise"></i>
        <span>Morning Call</span>
      </button>
      <button class="action-button subtle" id="winston-research" type="button" ${connected ? "" : "disabled"}>
        <i data-lucide="search"></i>
        <span>Research</span>
      </button>
      <button class="action-button subtle" id="winston-deep-research" type="button" ${connected ? "" : "disabled"}>
        <i data-lucide="brain-circuit"></i>
        <span>Deep Research</span>
      </button>
      <button class="action-button subtle" id="winston-mute" type="button">
        <i data-lucide="${winstonState.muted ? "volume-x" : "volume-2"}"></i>
        <span>${winstonState.muted ? "Unmute" : "Mute"}</span>
      </button>
    </div>
    <div class="approval-box">
      <label for="approval-token">Approval token</label>
      <input id="approval-token" type="password" placeholder="Required for paper order approval" value="${escapeHtml(approvalToken)}" autocomplete="off" />
      <span>Stored in this browser only. Exact phrase still required.</span>
    </div>
    ${
      pending.length
        ? `<div class="approval-list">
            ${pending
              .map(
                (item) => `
                  <article class="approval-card">
                    <strong>${escapeHtml(approvalLine(item))}</strong>
                    <span>Phrase: ${escapeHtml(item.approval_phrase)}</span>
                    <button class="action-button" type="button" data-approve-order="${escapeHtml(item.id)}" data-approve-phrase="${escapeHtml(item.approval_phrase)}">
                      <i data-lucide="shield-check"></i>
                      <span>Approve Paper</span>
                    </button>
                  </article>
                `,
              )
              .join("")}
          </div>`
        : `<div class="empty-state compact">No staged paper order is waiting for approval.</div>`
    }
    <form class="winston-form" id="winston-form">
      <input id="winston-input" type="text" placeholder="Ask for brief, research, watchlist, risk, positions..." autocomplete="off" ${connected ? "" : "disabled"} />
      <button class="icon-button primary" type="submit" title="Send" ${connected ? "" : "disabled"}>
        <i data-lucide="send"></i>
      </button>
    </form>
    <div class="transcript-list">${renderTranscript()}</div>
  `;
}

function renderPanel() {
  capturePanelDrafts();
  const [kicker, title] = panelCopy[activePanel] || panelCopy.tv;
  panelKicker.textContent = kicker;
  panelTitle.textContent = title;

  const renderers = {
    tv: renderTradingScreen,
    mission: renderMission,
    laptop: renderLaptop,
    journal: renderJournal,
    calendar: renderCalendar,
    safe: renderSafe,
    music: renderMusic,
    phone: renderPhone,
    bookshelf: renderBookshelf,
    clock: renderClock,
    window: renderWindow,
    lamp: renderLamp,
    drawer: renderDrawer,
    notes: renderNotes,
  };

  panelBody.innerHTML = (renderers[activePanel] || renderTradingScreen)();
  $("#winston-call-toggle")?.addEventListener("click", () => {
    if (winstonState.callActive) endWinstonCall();
    else startWinstonCall();
  });
  $("#winston-listen")?.addEventListener("click", toggleWinstonListening);
  $("#winston-brief")?.addEventListener("click", requestWinstonBrief);
  $("#winston-morning-call")?.addEventListener("click", requestWinstonMorningCall);
  $("#winston-research")?.addEventListener("click", requestWinstonResearch);
  $("#winston-deep-research")?.addEventListener("click", () => requestWinstonResearch({ deep: true }));
  $("#winston-mute")?.addEventListener("click", toggleWinstonMute);
  $("#approval-token")?.addEventListener("input", (event) => {
    approvalToken = event.target.value || "";
    localStorage.setItem("trading-bull-approval-token", approvalToken);
  });
  $$("[data-approve-order]").forEach((button) => {
    button.addEventListener("click", () => approvePendingOrder(button.dataset.approveOrder, button.dataset.approvePhrase));
  });
  $("#winston-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("#winston-input");
    const prompt = input?.value || "";
    if (input) input.value = "";
    sendWinstonPrompt(prompt);
  });
  $("#apple-music-connect")?.addEventListener("click", connectAppleMusic);
  $("#apple-music-disconnect")?.addEventListener("click", disconnectAppleMusic);
  $("#apple-music-search-form")?.addEventListener("submit", searchAppleMusic);
  $("#apple-music-toggle")?.addEventListener("click", toggleAppleMusicPlayback);
  $("#apple-music-next")?.addEventListener("click", () => skipAppleMusic("next"));
  $("#apple-music-prev")?.addEventListener("click", () => skipAppleMusic("previous"));
  $("[data-calendar-refresh]")?.addEventListener("click", () => refreshCalendar({ force: true }));
  $("[data-health-refresh]")?.addEventListener("click", () => refreshHealth({ force: true }));
  $("[data-coverage-refresh]")?.addEventListener("click", () => refreshCoverage({ force: true }));
  $$("[data-lifecycle-refresh]").forEach((button) => {
    button.addEventListener("click", () => refreshLifecycle({ force: true }));
  });
  $$("[data-lifecycle-reconcile]").forEach((button) => {
    button.addEventListener("click", () => refreshLifecycle({ force: true, reconcile: true }));
  });
  $("[data-latency-refresh]")?.addEventListener("click", () => refreshLatency({ force: true }));
  $("[data-risk-refresh]")?.addEventListener("click", () => refreshRiskStatus({ force: true }));
  $("[data-hardening-refresh]")?.addEventListener("click", () => refreshHardening({ force: true }));
  $("[data-journal-refresh]")?.addEventListener("click", () => refreshJournal({ force: true }));
  $("[data-review-refresh]")?.addEventListener("click", () => refreshReview({ force: true }));
  $("[data-close-report-refresh]")?.addEventListener("click", () => refreshCloseReport({ force: true }));
  $$("[data-chart-capture]").forEach((button) => {
    button.addEventListener("click", captureCurrentChart);
  });
  $$("[data-eod-ritual]").forEach((button) => {
    button.addEventListener("click", completeEndOfDayRitual);
  });
  $$("[data-eod-reset]").forEach((button) => {
    button.addEventListener("click", resetEndOfDayRitual);
  });
  $("#replay-form")?.addEventListener("submit", runReplay);
  $("[data-risk-replay]")?.addEventListener("click", runRiskReplay);
  $("#coverage-form")?.addEventListener("submit", saveCoverageSymbols);
  $("[data-copy-watchlist]")?.addEventListener("click", copyWatchlistToCoverage);
  $("[data-webhook-test]")?.addEventListener("click", runWebhookPipeTest);
  $("[data-risk-approval-toggle]")?.addEventListener("click", (event) => {
    toggleApprovalMode(event.currentTarget.dataset.riskApprovalToggle === "true");
  });
  $("[data-notification-test]")?.addEventListener("click", runNotificationTest);
  $("#watchlist-form")?.addEventListener("submit", submitWatchlistSymbol);
  $("#watchlist-symbol")?.addEventListener("input", (event) => {
    watchlistDraft.symbol = (event.target.value || "").toUpperCase();
    event.target.value = watchlistDraft.symbol;
  });
  $("#watchlist-type")?.addEventListener("change", (event) => {
    watchlistDraft.type = event.target.value || "equity";
  });
  $("#desk-note-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("#desk-note");
    deskNote = input?.value || "";
    localStorage.setItem("trading-bull-desk-note", deskNote);
    winstonTranscript("system", "Desk note saved.");
    renderPanel();
  });
  $$("[data-open-panel]").forEach((button) => {
    button.addEventListener("click", () => setActivePanel(button.dataset.openPanel));
  });
  $$("[data-remove-symbol]").forEach((button) => {
    button.addEventListener("click", () => removeWatchlistSymbol(button.dataset.removeSymbol));
  });
  $$("[data-review-alert]").forEach((button) => {
    button.addEventListener("click", () => requestTradeReview(button.dataset.reviewAlert));
  });
  $$("[data-replay-setup]").forEach((button) => {
    button.addEventListener("click", () => runReplayScenario(setupToReplayScenario(button.dataset.replaySetup), button.dataset.replaySymbol || "SPY"));
  });
  $$("[data-replay-scenario]").forEach((button) => {
    button.addEventListener("click", () => runReplayScenario(button.dataset.replayScenario || "bull_elephant", button.dataset.replaySymbol || "SPY"));
  });
  $$("[data-music-play]").forEach((button) => {
    button.addEventListener("click", () => playAppleMusicItem(button.dataset.musicPlay, button.dataset.musicKind));
  });
  $$(".symbol-button").forEach((button) => {
    if (button.dataset.symbol) button.addEventListener("click", () => setTradingViewSymbol(button.dataset.symbol));
  });
  window.lucide?.createIcons();
}

function capturePanelDrafts() {
  const symbolInput = $("#watchlist-symbol");
  const typeInput = $("#watchlist-type");
  const coverageInput = $("#coverage-symbols");
  if (symbolInput) watchlistDraft.symbol = (symbolInput.value || "").toUpperCase();
  if (typeInput) watchlistDraft.type = typeInput.value || "equity";
  if (coverageInput) tradingViewCoverageDraft = coverageInput.value || "";
}

function panelFormIsEditing() {
  const active = document.activeElement;
  if (!active || !panelBody.contains(active)) return false;
  if (!["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName)) return false;
  return Boolean(active.closest("form"));
}

function renderPanelIfIdle() {
  if (panelFormIsEditing()) return false;
  renderPanel();
  return true;
}

function openPanel() {
  panelOpen = true;
  updateActiveChrome();
}

function closePanel() {
  panelOpen = false;
  updateActiveChrome();
}

function updateActiveChrome() {
  $$(".object-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.panel === activePanel);
    const status = objectStatus(button.dataset.panel);
    if (status) button.dataset.status = status;
    else delete button.dataset.status;
  });
  $$(".room-hotspot").forEach((hotspot) => {
    hotspot.classList.toggle("active", hotspot.dataset.panel === activePanel);
    const status = objectStatus(hotspot.dataset.panel);
    if (status) hotspot.dataset.status = status;
    else delete hotspot.dataset.status;
  });
  screenTerminal.classList.toggle("active", activePanel === "tv");
  if (detailPanel) {
    detailPanel.setAttribute("aria-hidden", String(!panelOpen));
  }
  document.body.classList.toggle("phone-active", activePanel === "phone");
  document.body.classList.toggle("panel-open", panelOpen);
}

function applyRoomTheme(theme) {
  roomTheme = theme === "day" ? "day" : "night";
  document.body.dataset.roomTheme = roomTheme;
  localStorage.setItem("velez-room-theme", roomTheme);
  if (themeToggle) {
    const isDay = roomTheme === "day";
    themeToggle.setAttribute("aria-pressed", String(isDay));
    themeToggle.setAttribute("aria-label", isDay ? "Switch to night room" : "Switch to day room");
    themeToggle.innerHTML = `<i data-lucide="${isDay ? "moon" : "sun"}"></i><span>${isDay ? "Night" : "Day"}</span>`;
    window.lucide?.createIcons();
  }
}

function markTradingViewLoaded(loaded) {
  tradingViewLoaded = loaded;
  screenTerminal.classList.toggle("tradingview-loaded", loaded);
  if (activePanel === "tv") renderPanel();
}

function loadTradingViewWidget() {
  if (!tradingViewScreen) return;
  markTradingViewLoaded(false);
  clearTimeout(tradingViewTimer);

  const containerId = `tradingview-widget-${Date.now()}`;
  tradingViewScreen.innerHTML = `
    <div class="tradingview-widget-container" id="${containerId}">
      <div class="tradingview-widget-container__widget"></div>
    </div>
  `;

  const script = document.createElement("script");
  script.type = "text/javascript";
  script.async = true;
  script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
  script.textContent = JSON.stringify({
    autosize: true,
    symbol: tradingViewSymbol,
    interval: "5",
    timezone: "America/New_York",
    theme: "dark",
    style: "1",
    locale: "en",
    hide_top_toolbar: true,
    hide_side_toolbar: true,
    allow_symbol_change: true,
    save_image: false,
    calendar: false,
    support_host: "https://www.tradingview.com",
  });
  script.onerror = () => markTradingViewLoaded(false);
  tradingViewScreen.querySelector(".tradingview-widget-container").append(script);

  let attempts = 0;
  const checkLoaded = () => {
    attempts += 1;
    const iframe = tradingViewScreen.querySelector("iframe");
    if (iframe) {
      markTradingViewLoaded(true);
      return;
    }
    if (attempts < 24) {
      tradingViewTimer = setTimeout(checkLoaded, 250);
    } else {
      markTradingViewLoaded(false);
    }
  };
  tradingViewTimer = setTimeout(checkLoaded, 450);
}

function setTradingViewSymbol(symbol) {
  if (!tradingViewSymbols.some((item) => item.symbol === symbol)) return;
  tradingViewSymbol = symbol;
  localStorage.setItem("velez-tv-symbol", tradingViewSymbol);
  loadTradingViewWidget();
  if (activePanel === "tv") renderPanel();
}

function calendarIsStale(maxAgeMs = 5 * 60 * 1000) {
  return !calendarFetchedAt || Date.now() - calendarFetchedAt > maxAgeMs;
}

async function refreshCalendar(options = {}) {
  const force = Boolean(options.force);
  if (calendarRefreshPromise) return calendarRefreshPromise;
  if (!force && calendarState?.ok && !calendarIsStale()) return calendarState;

  calendarRefreshPromise = fetch("/api/calendar/month", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      calendarState = payload;
      calendarFetchedAt = Date.now();
      return payload;
    })
    .catch((error) => {
      calendarState = {
        ...currentCalendarState(),
        ok: false,
        timestamp: new Date().toISOString(),
        error: error.message,
      };
      return calendarState;
    })
    .finally(() => {
      calendarRefreshPromise = null;
      if (["mission", "calendar", "clock", "window", "notes"].includes(activePanel)) renderPanel();
    });

  if (["mission", "calendar", "clock", "window", "notes"].includes(activePanel)) renderPanel();
  return calendarRefreshPromise;
}

async function refreshJournal(options = {}) {
  const force = Boolean(options.force);
  if (journalRefreshPromise) return journalRefreshPromise;
  if (!force && journalState?.ok) return journalState;

  journalRefreshPromise = fetch("/api/journal/recent?limit=80", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      journalState = payload;
      return payload;
    })
    .catch((error) => {
      journalState = { ...currentJournalState(), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return journalState;
    })
    .finally(() => {
      journalRefreshPromise = null;
      if (activePanel === "journal") renderPanel();
    });

  if (activePanel === "journal") renderPanel();
  return journalRefreshPromise;
}

async function refreshHealth(options = {}) {
  const force = Boolean(options.force);
  if (healthRefreshPromise) return healthRefreshPromise;
  if (!force && healthState?.ok && Date.now() - new Date(healthState.timestamp || 0).getTime() < 30000) return healthState;

  healthRefreshPromise = fetch("/api/bot/health", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      healthState = payload;
      return payload;
    })
    .catch((error) => {
      healthState = { ...currentHealthState(), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return healthState;
    })
    .finally(() => {
      healthRefreshPromise = null;
      if (["mission", "laptop", "lamp", "window"].includes(activePanel)) renderPanelIfIdle();
    });

  if (["mission", "laptop", "lamp", "window"].includes(activePanel)) renderPanelIfIdle();
  return healthRefreshPromise;
}

async function refreshCoverage(options = {}) {
  const force = Boolean(options.force);
  if (coverageRefreshPromise) return coverageRefreshPromise;
  if (!force && coverageState?.ok && Date.now() - new Date(coverageState.timestamp || 0).getTime() < 30000) return coverageState;

  coverageRefreshPromise = fetch("/api/alerts/coverage", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      coverageState = payload;
      return payload;
    })
    .catch((error) => {
      coverageState = { ...currentCoverageState(), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return coverageState;
    })
    .finally(() => {
      coverageRefreshPromise = null;
      if (activePanel === "laptop") renderPanelIfIdle();
    });

  if (activePanel === "laptop") renderPanelIfIdle();
  return coverageRefreshPromise;
}

async function refreshLifecycle(options = {}) {
  const force = Boolean(options.force);
  const reconcile = Boolean(options.reconcile);
  if (lifecycleRefreshPromise) return lifecycleRefreshPromise;
  if (!force && lifecycleState?.ok && Date.now() - new Date(lifecycleState.timestamp || 0).getTime() < 15000) return lifecycleState;

  lifecycleRefreshPromise = fetch(reconcile ? "/api/lifecycle/reconcile" : "/api/lifecycle/state", {
    method: reconcile ? "POST" : "GET",
    cache: "no-store",
  })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      lifecycleState = payload;
      dashboardState.lifecycle = payload;
      dashboardState.summary = {
        ...dashboardState.summary,
        open_positions: payload.summary?.open_positions ?? dashboardState.summary?.open_positions ?? 0,
        unrealized_pl: payload.summary?.unrealized_pl ?? dashboardState.summary?.unrealized_pl ?? 0,
      };
      return payload;
    })
    .catch((error) => {
      lifecycleState = { ...currentLifecycleState(), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return lifecycleState;
    })
    .finally(() => {
      lifecycleRefreshPromise = null;
      if (["laptop", "journal", "phone"].includes(activePanel)) renderPanelIfIdle();
    });

  if (["laptop", "journal", "phone"].includes(activePanel)) renderPanelIfIdle();
  return lifecycleRefreshPromise;
}

async function refreshRiskStatus(options = {}) {
  const force = Boolean(options.force);
  if (riskRefreshPromise) return riskRefreshPromise;
  if (!force && riskState?.ok && Date.now() - new Date(riskState.timestamp || 0).getTime() < 30000) return riskState;

  riskRefreshPromise = fetch("/api/risk/status", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      riskState = payload;
      dashboardState.guardrails = {
        ...dashboardState.guardrails,
        approval_required: payload.approval_required,
        approval_mode_source: payload.approval_mode_source,
      };
      return payload;
    })
    .catch((error) => {
      riskState = { ...currentRiskState(), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return riskState;
    })
    .finally(() => {
      riskRefreshPromise = null;
      if (["laptop", "lamp"].includes(activePanel)) renderPanelIfIdle();
    });

  if (["laptop", "lamp"].includes(activePanel)) renderPanelIfIdle();
  return riskRefreshPromise;
}

async function refreshHardening(options = {}) {
  const force = Boolean(options.force);
  if (hardeningRefreshPromise) return hardeningRefreshPromise;
  if (!force && hardeningState?.ok && Date.now() - new Date(hardeningState.timestamp || 0).getTime() < 60000) return hardeningState;

  hardeningRefreshPromise = fetch("/api/vps/hardening", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      hardeningState = payload;
      return payload;
    })
    .catch((error) => {
      hardeningState = { ...currentHardeningState(), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return hardeningState;
    })
    .finally(() => {
      hardeningRefreshPromise = null;
      if (activePanel === "laptop") renderPanelIfIdle();
    });

  if (activePanel === "laptop") renderPanelIfIdle();
  return hardeningRefreshPromise;
}

async function refreshLatency(options = {}) {
  const force = Boolean(options.force);
  if (latencyRefreshPromise) return latencyRefreshPromise;
  if (!force && latencyState?.ok && Date.now() - new Date(latencyState.timestamp || 0).getTime() < 30000) return latencyState;

  latencyRefreshPromise = fetch("/api/vps/latency", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      latencyState = payload;
      return payload;
    })
    .catch((error) => {
      latencyState = { ...currentLatencyState(), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return latencyState;
    })
    .finally(() => {
      latencyRefreshPromise = null;
      if (activePanel === "laptop") renderPanelIfIdle();
    });

  if (activePanel === "laptop") renderPanelIfIdle();
  return latencyRefreshPromise;
}

async function refreshReplayLatest() {
  if (replayRunPromise) return replayRunPromise;
  try {
    const response = await fetch("/api/replay/latest", { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `replay latest failed (${response.status})`);
    replayState = { ...fallbackReplayState(), ok: true, runs: data.runs || [] };
  } catch (error) {
    replayState = { ...currentReplayState(), ok: false, error: error?.message || "Replay history failed" };
  }
  if (["laptop", "journal", "drawer"].includes(activePanel)) renderPanelIfIdle();
}

async function refreshReview(options = {}) {
  const force = Boolean(options.force);
  if (reviewRefreshPromise) return reviewRefreshPromise;
  const fetchedAt = reviewState?.timestamp ? new Date(reviewState.timestamp).getTime() : 0;
  if (!force && reviewState?.ok && Date.now() - fetchedAt < 60000) return reviewState;

  reviewRefreshPromise = fetch("/api/review/daily", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      reviewState = payload;
      return payload;
    })
    .catch((error) => {
      reviewState = { ...currentReviewState(), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return reviewState;
    })
    .finally(() => {
      reviewRefreshPromise = null;
      if (["mission", "journal", "notes", "laptop"].includes(activePanel)) renderPanelIfIdle();
    });

  if (["mission", "journal", "notes", "laptop"].includes(activePanel)) renderPanelIfIdle();
  return reviewRefreshPromise;
}

async function refreshCloseReport(options = {}) {
  const force = Boolean(options.force);
  if (closeReportRefreshPromise) return closeReportRefreshPromise;
  const fetchedAt = closeReportState?.timestamp ? new Date(closeReportState.timestamp).getTime() : 0;
  if (!force && closeReportState?.ok && Date.now() - fetchedAt < 60000) return closeReportState;

  closeReportRefreshPromise = fetch("/api/review/close", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      closeReportState = payload;
      return payload;
    })
    .catch((error) => {
      closeReportState = { ...currentCloseReportState(), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return closeReportState;
    })
    .finally(() => {
      closeReportRefreshPromise = null;
      if (["journal", "notes", "laptop"].includes(activePanel)) renderPanelIfIdle();
    });

  if (["journal", "notes", "laptop"].includes(activePanel)) renderPanelIfIdle();
  return closeReportRefreshPromise;
}

function saveCoverageSymbols(event) {
  event.preventDefault();
  const input = $("#coverage-symbols");
  tradingViewCoverageDraft = (input?.value || "")
    .split(/[\s,]+/)
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean)
    .join(", ");
  localStorage.setItem("trading-bull-tv-coverage-symbols", tradingViewCoverageDraft);
  winstonTranscript("system", "TradingView coverage list saved in this browser.");
  renderPanel();
}

async function copyWatchlistToCoverage() {
  tradingViewCoverageDraft = (dashboardState.symbols || []).map((item) => item.symbol).filter(Boolean).join(", ");
  localStorage.setItem("trading-bull-tv-coverage-symbols", tradingViewCoverageDraft);
  try {
    await navigator.clipboard?.writeText(tradingViewCoverageDraft);
    winstonTranscript("system", "Bot watchlist copied for TradingView Watchlist Alerts.");
  } catch (error) {
    winstonTranscript("system", "Bot watchlist marked covered. Browser clipboard write was unavailable.");
  }
  renderPanel();
}

async function runWebhookPipeTest() {
  const token = approvalToken.trim();
  if (!token) {
    webhookTestState = { ok: false, reason: "approval_token_required" };
    winstonTranscript("system", "Enter the approval token in the phone panel before running the webhook dry-run test.");
    renderPanel();
    return;
  }
  const symbol = dashboardState.symbols?.[0]?.symbol || "SPY";
  webhookTestState = { ok: false, message: "Webhook dry-run test running..." };
  renderPanel();
  try {
    const response = await fetch("/api/webhook/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_token: token, symbol }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `webhook test failed (${response.status})`);
    webhookTestState = data;
    if (data.coverage) coverageState = data.coverage;
    winstonTranscript("system", "Webhook pipe dry-run passed. No order was staged or submitted.");
    await refreshJournal({ force: true });
    await refreshState();
    await refreshCoverage({ force: true });
  } catch (error) {
    webhookTestState = { ok: false, reason: error?.message || "webhook_test_failed" };
    winstonTranscript("system", `Webhook dry-run blocked: ${webhookTestState.reason}.`);
  }
  renderPanel();
}

async function toggleApprovalMode(enabled) {
  const token = approvalToken.trim();
  if (!token) {
    winstonTranscript("system", "Enter the approval token in the phone panel before changing approval mode.");
    return;
  }
  riskUpdatePromise = fetch("/api/risk/approval-mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled, approval_token: token }),
  })
    .then((response) => response.json().then((data) => ({ response, data })).catch(() => ({ response, data: {} })))
    .then(({ response, data }) => {
      if (!response.ok || !data.ok) throw new Error(data.reason || `approval mode failed (${response.status})`);
      riskState = data;
      dashboardState.guardrails = {
        ...dashboardState.guardrails,
        approval_required: data.approval_required,
        approval_mode_source: data.approval_mode_source,
      };
      winstonTranscript("system", data.approval_required ? "Approval mode is now required for qualified paper alerts." : "Approval mode is back to current auto-submit behavior.");
      return data;
    })
    .catch((error) => {
      winstonTranscript("system", `Approval mode update blocked: ${error?.message || "unknown error"}.`);
      return currentRiskState();
    })
    .finally(() => {
      riskUpdatePromise = null;
      if (["laptop", "lamp"].includes(activePanel)) renderPanel();
    });
  renderPanel();
  await riskUpdatePromise;
}

async function runNotificationTest() {
  try {
    const response = await fetch("/api/notifications/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel: "all" }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `notification test failed (${response.status})`);
    winstonTranscript("system", `Notification test dispatched to ${data.targets?.join(", ") || "configured targets"}.`);
  } catch (error) {
    winstonTranscript("system", `Notification test blocked: ${error?.message || "unknown error"}.`);
  }
}

function setupToReplayScenario(setup) {
  const normalized = String(setup || "").toLowerCase();
  if (normalized.includes("bear_180")) return "bear_180";
  if (normalized.includes("buy_setup")) return "buy_setup";
  if (normalized.includes("sell_setup")) return "sell_setup";
  if (normalized.includes("nrb") || normalized.includes("acorn")) return "nrb_acorn";
  if (normalized.includes("color_change")) return "color_change_add";
  if (normalized.includes("fab4")) return "fab4_trap";
  if (normalized.includes("failed_new_high")) return "failed_new_high";
  if (normalized.includes("failed_new_low")) return "failed_new_low";
  if (normalized.includes("opening_gap_go")) return "opening_gap_go";
  if (normalized.includes("opening_gap_fade")) return "opening_gap_fade";
  if (normalized.includes("time_space")) return "time_space_breakout";
  return "bull_elephant";
}

async function requestTradeReview(alertRef = "") {
  if (tradeReviewPromise) return tradeReviewPromise;
  tradeReviewState = null;
  tradeReviewPromise = fetch(`/api/journal/review?alert_ref=${encodeURIComponent(alertRef || "")}`, { cache: "no-store" })
    .then((response) => response.json().then((data) => ({ response, data })).catch(() => ({ response, data: {} })))
    .then(({ response, data }) => {
      if (!response.ok || !data.ok) throw new Error(data.reason || `review failed (${response.status})`);
      tradeReviewState = data;
      return data;
    })
    .catch((error) => {
      tradeReviewState = { ok: false, reason: error?.message || "review_failed" };
      winstonTranscript("system", `Trade review failed: ${tradeReviewState.reason}.`);
      return tradeReviewState;
    })
    .finally(() => {
      tradeReviewPromise = null;
      if (activePanel === "journal") renderPanel();
    });
  if (activePanel === "journal") renderPanel();
  return tradeReviewPromise;
}

function runReplayScenario(scenario, symbol) {
  replayRunPromise = fetch("/api/replay/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol: symbol || dashboardState.symbols?.[0]?.symbol || "SPY", scenario: scenario || "bull_elephant" }),
  })
    .then((response) => response.json().then((data) => ({ response, data })).catch(() => ({ response, data: {} })))
    .then(({ response, data }) => {
      if (!response.ok || !data.ok) throw new Error(data.reason || `replay failed (${response.status})`);
      replayState = data;
      winstonTranscript("system", data.summary || "Replay complete.");
      return data;
    })
    .catch((error) => {
      replayState = { ...currentReplayState(), ok: false, summary: error?.message || "Replay failed" };
      return replayState;
    })
    .finally(() => {
      replayRunPromise = null;
      if (["laptop", "drawer", "journal"].includes(activePanel)) renderPanel();
      refreshJournal({ force: true });
    });
  renderPanel();
  return replayRunPromise;
}

function runRiskReplayScenario(scenario, symbol) {
  replayRunPromise = fetch("/api/replay/risk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol: symbol || dashboardState.symbols?.[0]?.symbol || "SPY", scenario: scenario || "bull_elephant" }),
  })
    .then((response) => response.json().then((data) => ({ response, data })).catch(() => ({ response, data: {} })))
    .then(({ response, data }) => {
      if (!response.ok || !data.ok) throw new Error(data.reason || `risk replay failed (${response.status})`);
      replayState = data;
      winstonTranscript("system", data.risk_replay?.summary || "Risk replay complete.");
      return data;
    })
    .catch((error) => {
      replayState = { ...currentReplayState(), ok: false, summary: error?.message || "Risk replay failed" };
      return replayState;
    })
    .finally(() => {
      replayRunPromise = null;
      if (["laptop", "drawer", "journal"].includes(activePanel)) renderPanel();
      refreshJournal({ force: true });
    });
  renderPanel();
  return replayRunPromise;
}

async function runReplay(event) {
  event.preventDefault();
  const scenario = $("#replay-scenario")?.value || "bull_elephant";
  const symbol = $("#replay-symbol")?.value || dashboardState.symbols?.[0]?.symbol || "SPY";
  return runReplayScenario(scenario, symbol);
}

async function runRiskReplay(event) {
  event?.preventDefault?.();
  const scenario = $("#replay-scenario")?.value || "bull_elephant";
  const symbol = $("#replay-symbol")?.value || dashboardState.symbols?.[0]?.symbol || "SPY";
  return runRiskReplayScenario(scenario, symbol);
}

function setActivePanel(panel, options = {}) {
  if (!panelCopy[panel]) return;
  activePanel = panel;
  renderPanel();
  if (options.openPanel !== false) {
    panelOpen = true;
  }
  updateActiveChrome();
  if (["mission", "calendar", "clock", "window", "notes"].includes(panel)) {
    refreshCalendar();
  }
  if (panel === "journal") {
    refreshJournal();
  }
  if (["mission", "laptop", "lamp", "window"].includes(panel)) {
    refreshHealth();
  }
  if (["laptop"].includes(panel)) {
    refreshCoverage();
    refreshLifecycle();
    refreshHardening();
    refreshLatency();
  }
  if (["journal", "phone"].includes(panel)) {
    refreshLifecycle();
  }
  if (["laptop", "lamp"].includes(panel)) {
    refreshRiskStatus();
  }
  if (["laptop", "drawer"].includes(panel)) {
    refreshReplayLatest();
  }
  if (["mission", "journal", "notes", "laptop"].includes(panel)) {
    refreshReview();
  }
  if (["journal", "notes", "laptop"].includes(panel)) {
    refreshCloseReport();
  }
}

async function refreshState() {
  try {
    const response = await fetch("/api/dashboard/state", { cache: "no-store" });
    if (!response.ok) throw new Error(`status ${response.status}`);
    dashboardState = await response.json();
  } catch (error) {
    dashboardState = {
      ...dashboardState,
      ok: false,
      broker: { ...dashboardState.broker, ok: false, reason: "dashboard_api_unreachable" },
      timestamp: new Date().toISOString(),
    };
  }
  if (dashboardState.apple_music?.configured) {
    prepareAppleMusic();
  }
  if (dashboardState.winston) {
    applyWinstonRuntime(dashboardState.winston);
  }
  if (["mission", "calendar", "clock", "window", "notes"].includes(activePanel)) {
    refreshCalendar();
  }
  if (["mission", "laptop", "lamp", "window"].includes(activePanel)) {
    refreshHealth();
  }
  if (activePanel === "laptop") {
    refreshCoverage();
    refreshLifecycle();
    refreshHardening();
    refreshLatency();
  }
  if (["journal", "phone"].includes(activePanel)) {
    refreshLifecycle();
  }
  if (["laptop", "lamp"].includes(activePanel)) {
    refreshRiskStatus();
  }
  if (activePanel === "journal") {
    refreshJournal();
  }
  if (activePanel === "drawer") {
    refreshReplayLatest();
  }
  if (["mission", "journal", "notes", "laptop"].includes(activePanel)) {
    refreshReview();
  }
  if (["journal", "notes", "laptop"].includes(activePanel)) {
    refreshCloseReport();
  }
  renderStatus();
  if (!activePanelIsMusic() && activePanel !== "phone") {
    renderPanelIfIdle();
  }
  updateActiveChrome();
}

function roomRect() {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const scale = Math.max(viewportWidth / PHOTO_WIDTH, viewportHeight / PHOTO_HEIGHT);
  const width = PHOTO_WIDTH * scale;
  const height = PHOTO_HEIGHT * scale;
  return {
    left: (viewportWidth - width) / 2,
    top: (viewportHeight - height) / 2,
    width,
    height,
  };
}

function applyRegion(element, region, rect) {
  element.style.left = `${rect.left + region.x * rect.width}px`;
  element.style.top = `${rect.top + region.y * rect.height}px`;
  element.style.width = `${region.w * rect.width}px`;
  element.style.height = `${region.h * rect.height}px`;
}

function positionRoomElements() {
  const rect = roomRect();
  $$(".room-hotspot").forEach((hotspot) => {
    const region = hotspotDefinitions.find((item) => item.panel === hotspot.dataset.panel);
    if (region) applyRegion(hotspot, region, rect);
  });
  applyRegion(screenTerminal, screenRegion, rect);
  screenTerminal.hidden = window.innerWidth < 720;
}

function showHover(label, event) {
  hoverTag.hidden = false;
  hoverTag.textContent = label;
  hoverTag.style.left = `${event.clientX}px`;
  hoverTag.style.top = `${event.clientY}px`;
}

function hideHover() {
  hoverTag.hidden = true;
}

function buildHotspots() {
  roomHotspots.innerHTML = "";
  hotspotDefinitions.forEach((definition) => {
    const button = document.createElement("button");
    button.className = "room-hotspot";
    button.type = "button";
    button.dataset.panel = definition.panel;
    button.dataset.label = definition.label;
    button.setAttribute("aria-label", definition.label);
    button.title = definition.label;
    button.innerHTML = `<i data-lucide="${definition.icon}"></i><span>${definition.label}</span>`;
    button.addEventListener("click", () => setActivePanel(definition.panel));
    button.addEventListener("pointermove", (event) => showHover(definition.label, event));
    button.addEventListener("pointerleave", hideHover);
    button.addEventListener("focus", () => {
      hoverTag.hidden = false;
      hoverTag.textContent = definition.label;
      const bounds = button.getBoundingClientRect();
      hoverTag.style.left = `${bounds.left + bounds.width / 2}px`;
      hoverTag.style.top = `${bounds.top + bounds.height / 2}px`;
    });
    button.addEventListener("blur", hideHover);
    roomHotspots.append(button);
  });
}

$$(".object-button").forEach((button) => {
  button.addEventListener("click", () => {
    setActivePanel(button.dataset.panel);
    document.body.classList.remove("nav-peek");
  });
});

navRevealZone?.addEventListener("click", () => {
  document.body.classList.toggle("nav-peek");
});

navRevealZone?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    document.body.classList.toggle("nav-peek");
  }
});

panelClose?.addEventListener("click", closePanel);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closePanel();
    document.body.classList.remove("nav-peek");
  }
});

screenTerminal.addEventListener("click", () => setActivePanel("tv"));
screenTerminal.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    setActivePanel("tv");
  }
});
screenTerminal.addEventListener("pointermove", (event) => showHover("Trading screen", event));
screenTerminal.addEventListener("pointerleave", hideHover);

themeToggle?.addEventListener("click", () => {
  applyRoomTheme(roomTheme === "day" ? "night" : "day");
});

function drawRoundRect(ctx, x, y, width, height, radius) {
  const resolvedRadius = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + resolvedRadius, y);
  ctx.lineTo(x + width - resolvedRadius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + resolvedRadius);
  ctx.lineTo(x + width, y + height - resolvedRadius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - resolvedRadius, y + height);
  ctx.lineTo(x + resolvedRadius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - resolvedRadius);
  ctx.lineTo(x, y + resolvedRadius);
  ctx.quadraticCurveTo(x, y, x + resolvedRadius, y);
  ctx.closePath();
  ctx.fill();
}

let seed = 19;
function random() {
  seed = (seed * 1664525 + 1013904223) >>> 0;
  return seed / 4294967296;
}

const candles = [];
for (let index = 0; index < 92; index += 1) {
  const previous = index ? candles[index - 1].close : 500;
  const drift = Math.sin(index * 0.18) * 0.9 + (random() - 0.45) * 3.4;
  const open = previous;
  const close = Math.max(465, open + drift);
  const high = Math.max(open, close) + 1.1 + random() * 4.2;
  const low = Math.min(open, close) - 1.1 - random() * 4.2;
  candles.push({ open, high, low, close });
}

function fitCanvasToCss() {
  const bounds = chartCanvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(bounds.width * dpr));
  const height = Math.max(1, Math.round(bounds.height * dpr));
  if (chartCanvas.width !== width || chartCanvas.height !== height) {
    chartCanvas.width = width;
    chartCanvas.height = height;
  }
  chartCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { width: bounds.width, height: bounds.height };
}

function drawChart(time) {
  if (screenTerminal.hidden) return;
  const { width, height } = fitCanvasToCss();
  if (width < 10 || height < 10) return;

  const lastDecision = latestDecision();
  const animatedCandles = candles.map((candle, index) => {
    if (index !== candles.length - 1) return candle;
    const pulse = Math.sin(time * 1.4) * 2.1;
    return { ...candle, close: candle.close + pulse, high: candle.high + Math.max(0, pulse) };
  });

  const min = Math.min(...animatedCandles.map((candle) => candle.low)) - 5;
  const max = Math.max(...animatedCandles.map((candle) => candle.high)) + 5;
  const marginX = Math.max(20, width * 0.05);
  const top = Math.max(30, height * 0.16);
  const bottom = Math.max(22, height * 0.16);
  const y = (price) => height - bottom - ((price - min) / (max - min)) * (height - top - bottom);
  const candleWidth = (width - marginX * 2) / animatedCandles.length;

  chartCtx.clearRect(0, 0, width, height);
  const bg = chartCtx.createLinearGradient(0, 0, width, height);
  bg.addColorStop(0, "rgba(7, 18, 20, 0.96)");
  bg.addColorStop(1, "rgba(3, 8, 10, 0.92)");
  chartCtx.fillStyle = bg;
  chartCtx.fillRect(0, 0, width, height);

  chartCtx.strokeStyle = palette.grid;
  chartCtx.lineWidth = 1;
  for (let i = 0; i < 5; i += 1) {
    const lineY = top + i * ((height - top - bottom) / 4);
    chartCtx.beginPath();
    chartCtx.moveTo(marginX, lineY);
    chartCtx.lineTo(width - marginX, lineY);
    chartCtx.stroke();
  }

  chartCtx.font = `800 ${Math.max(9, width * 0.022)}px Inter, sans-serif`;
  chartCtx.fillStyle = palette.ink;
  chartCtx.fillText("TRADINGVIEW ALERT STREAM", marginX, Math.max(17, height * 0.12));
  chartCtx.font = `700 ${Math.max(7, width * 0.013)}px Inter, sans-serif`;
  chartCtx.fillStyle = palette.muted;
  chartCtx.fillText(lastDecision ? `${lastDecision.symbol || ""} ${lastDecision.play || ""}` : "Trading Bull scanner", marginX, Math.max(28, height * 0.18));

  const sma20 = animatedCandles.map((_, index) => {
    const slice = animatedCandles.slice(Math.max(0, index - 19), index + 1);
    return slice.reduce((sum, item) => sum + item.close, 0) / slice.length;
  });
  const sma200 = animatedCandles.map((_, index) => 496 + Math.sin(index * 0.035) * 6);

  function drawLine(points, color, widthValue) {
    chartCtx.strokeStyle = color;
    chartCtx.lineWidth = widthValue;
    chartCtx.beginPath();
    points.forEach((price, index) => {
      const px = marginX + index * candleWidth + candleWidth * 0.5;
      const py = y(price);
      if (index === 0) chartCtx.moveTo(px, py);
      else chartCtx.lineTo(px, py);
    });
    chartCtx.stroke();
  }

  drawLine(sma200, "rgba(136, 161, 174, 0.72)", Math.max(1.2, width * 0.0025));
  drawLine(sma20, "rgba(226, 170, 75, 0.88)", Math.max(1.1, width * 0.0022));

  animatedCandles.forEach((candle, index) => {
    const up = candle.close >= candle.open;
    const px = marginX + index * candleWidth + candleWidth * 0.5;
    const openY = y(candle.open);
    const closeY = y(candle.close);
    const highY = y(candle.high);
    const lowY = y(candle.low);
    const volume = Math.min(height * 0.16, 9 + Math.abs(candle.close - candle.open) * 2.2 + (index % 9));

    chartCtx.fillStyle = up ? "rgba(104, 199, 131, 0.15)" : "rgba(228, 107, 97, 0.15)";
    chartCtx.fillRect(px - candleWidth * 0.22, height - bottom * 0.65 - volume, candleWidth * 0.44, volume);
    chartCtx.strokeStyle = up ? palette.green : palette.red;
    chartCtx.fillStyle = up ? palette.green : palette.red;
    chartCtx.lineWidth = Math.max(1, candleWidth * 0.15);
    chartCtx.beginPath();
    chartCtx.moveTo(px, highY);
    chartCtx.lineTo(px, lowY);
    chartCtx.stroke();
    chartCtx.fillRect(px - candleWidth * 0.28, Math.min(openY, closeY), candleWidth * 0.56, Math.max(2, Math.abs(closeY - openY)));
  });

  const lastPrice = animatedCandles.at(-1).close;
  const lastY = y(lastPrice);
  chartCtx.strokeStyle = "rgba(244, 241, 232, 0.24)";
  chartCtx.setLineDash([6, 6]);
  chartCtx.beginPath();
  chartCtx.moveTo(marginX, lastY);
  chartCtx.lineTo(width - marginX * 2.1, lastY);
  chartCtx.stroke();
  chartCtx.setLineDash([]);
  chartCtx.fillStyle = "rgba(244, 241, 232, 0.16)";
  drawRoundRect(chartCtx, width - marginX * 2.02, lastY - 11, marginX * 1.52, 22, 7);
  chartCtx.font = `800 ${Math.max(7, width * 0.014)}px Inter, sans-serif`;
  chartCtx.fillStyle = palette.ink;
  chartCtx.fillText(lastPrice.toFixed(2), width - marginX * 1.86, lastY + 5);
}

function animate(now = 0) {
  window.__deskFrame = frame;
  frame += 1;
  drawChart(now / 1000);
  requestAnimationFrame(animate);
}

function init() {
  buildHotspots();
  window.addEventListener("load", () => window.lucide?.createIcons());
  window.addEventListener("resize", positionRoomElements);
  window.lucide?.createIcons();

  window.__deskDebug = {
    version: APP_BUILD,
    roomRect,
    hotspots: () => hotspotDefinitions,
    theme: () => roomTheme,
    setTheme: applyRoomTheme,
    tradingView: () => ({ symbol: tradingViewSymbol, loaded: tradingViewLoaded }),
    appleMusic: () => ({ ...appleMusicState, bridge: appleMusicBridgeStatus() }),
    calendar: () => currentCalendarState(),
    journal: () => currentJournalState(),
    health: () => currentHealthState(),
    lifecycle: () => currentLifecycleState(),
    latency: () => currentLatencyState(),
    replay: () => currentReplayState(),
    review: () => currentReviewState(),
    closeReport: () => currentCloseReportState(),
    captures: () => chartCaptures,
    ritual: () => endOfDayRitual,
    refreshCalendar,
    refreshJournal,
    refreshHealth,
    refreshLifecycle,
    refreshReview,
    refreshCloseReport,
    refreshLatency,
    captureCurrentChart,
    runReplay,
    runRiskReplay,
    prepareAppleMusic,
    connectAppleMusic,
    winston: () => ({ ...winstonState, recognition: Boolean(winstonState.recognition) }),
    setTradingViewSymbol,
    setPanel: setActivePanel,
    openPanel,
    closePanel,
    state: () => dashboardState,
    clickObject: (panel) => setActivePanel(panel),
    summonJarvis: () => setActivePanel("phone"),
  };
  window.__deskReady = true;
  window.__deskVersion = APP_BUILD;

  applyRoomTheme(roomTheme);
  positionRoomElements();
  loadTradingViewWidget();
  renderPanel();
  updateActiveChrome();
  refreshWinstonStatus();
  refreshState();
  setInterval(refreshState, 5000);
  requestAnimationFrame(animate);
}

init();
