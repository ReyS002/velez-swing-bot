import { roomRect as sovereignRoomRect, roomRegions as sovereignRegions, roomHotspots as getSovereignHotspots, objectMarkup as sovereignObjectMarkup, roomSnapshot, syncRoomTheme, mountSovereign, updateSovereignChrome, workspaceAccountMarkup, workspaceConfiguration } from "./sovereign-room.js?v=1.8.0";
const $ = (selector) => document.querySelector(selector);
import { createDeskRecords } from "./desk-records.js?v=1.8.0";
const deskRecords = createDeskRecords({active:()=>activePanel,redraw:()=>renderPanel(),escapeHtml});
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const PHOTO_WIDTH = 1672;
const PHOTO_HEIGHT = 941;

const roomHotspots = $("#room-hotspots");
const winstonAudioPlayer = $("#winston-audio-player");
const screenTerminal = $("#screen-terminal");
const tradingViewScreen = $("#tradingview-screen");
const proConsole = $("#pro-console");
const proTradingViewScreen = $("#pro-tradingview-screen");
const proConsoleClose = $("#pro-console-close");
const mobileTradingViewScreen = $("#mobile-tradingview-screen");
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
const tradingModeSelect = $("#trading-mode-select");
const tradingModeStatus = $("#trading-mode-status");
const navRevealZone = $("#nav-reveal-zone");
const workflowButtons = $$(".workflow-button");
const dataDisclosure = $("#data-disclosure");
const dataDisclosureTitle = $("#data-disclosure-title");
const dataDisclosureDetail = $("#data-disclosure-detail");

let activePanel = "tv";
let panelOpen = false;
let activeWorkflow = "desk";
let roomClear = true;
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
let mentorState = null;
let mentorRefreshPromise = null;
let mentorAskState = null;
let mentorEyesState = null;
let mentorOpsState = {
  sourceHealth: null,
  setupWatch: null,
  noTrade: null,
  tradier: null,
  autopsyBackfill: null,
  pnlAttribution: null,
  strategyDrift: null,
  regimeCatalyst: null,
  crossBotRisk: null,
  replayLab: null,
  dailyRootCause: null,
  tradeQualityHeatmap: null,
  guardrailReport: null,
  brokerReconciliation: null,
  botParity: null,
  lastGoodWeekDelta: null,
  drillScheduler: null,
};
let coverageState = null;
let coverageRefreshPromise = null;
let scannerQualityState = null;
let scannerQualityRefreshPromise = null;
let watchlistQualityState = null;
let watchlistQualityRefreshPromise = null;
let lifecycleState = null;
let lifecycleRefreshPromise = null;
let riskState = null;
let riskRefreshPromise = null;
let tradingModeState = {
  ok: false,
  trading_mode: "dual",
  saving: false,
  error: null,
  timestamp: null,
};
let tradingModeRefreshPromise = null;
let hardeningState = null;
let hardeningRefreshPromise = null;
let latencyState = null;
let latencyRefreshPromise = null;
let entitlementState = { ok: false, tier: "core", features: {} };
let readinessState = null;
let plannerState = null;
let intelligenceState = null;
let marketContextState = null;
let playbookState = null;
let symbolNoteState = null;
let structuredReviewState = null;
let annotationsState = null;
let missedTradesState = null;
let disciplineState = null;
let decisionIntelligencePromise = null;
let decisionIntelligenceFetchedAt = 0;
let decisionIntelligenceKey = "";
let playbookQuery = "";
let dashboardRefreshController = null;
let dashboardRefreshTimer = null;
let dashboardDestroyed = false;
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
let roomTheme = localStorage.getItem("velez-room-theme") === "day" ? "day" : "night";
let tradingViewLoaded = false;
let tradingViewTimer = null;
let proConsoleOpen = false;
let proTradingViewLoaded = false;
let proTradingViewTimer = null;
let mobileTradingViewLoaded = false;
let mobileTradingViewTimer = null;
let appleMusicScriptPromise = null;
let appleMusicInstance = null;
let appleMusicReadyPromise = null;
let appleMusicPollTimer = null;

const APPLE_MUSIC_URL = "https://music.apple.com/us/browse";
const APPLE_MUSIC_FOCUS_URL = "https://music.apple.com/us/search?term=focus%20trading";
const APPLE_MUSIC_SCRIPT_URL = "https://js-cdn.music.apple.com/musickit/v3/musickit.js";
const APP_BUILD = "v6.40.4";
const WINSTON_REQUIRED_VOICE = "winston";
const WINSTON_AUDIO_UNLOCK_CLIP =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
const TRADING_MODE_LABELS = {
  intraday: "Intraday",
  swing: "Swing",
  dual: "Both",
};
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
  speechController: null,
  brain: {
    provider: "winston_rule_based_v1",
    model: "local_guardrail_rules",
    configured: true,
    available: true,
    detail: "Safe local Winston responses",
  },
  voice: {
    provider: "pockettts",
    configured: false,
    available: false,
    voice: WINSTON_REQUIRED_VOICE,
    model: "tts-1",
    detail: "Checking Winston voice service",
    statusLoaded: false,
    lastLatencyMs: null,
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

const panelCopy = {
  research: ["Winston's saved research", "Saved research"],
  performance: ["Bot-attributed results", "Performance"],
  account: ["Workspace access", "Account & access"],
  tv: ["TradingView | V6.23", "Trading Screen"],
  mission: ["Daily mission | V6.23", "Mission Card"],
  mentor: ["Eyes-on coaching | V6.26", "Velez Mentor AI"],
  laptop: ["Command center | V6.23", "Bot Console"],
  journal: ["Journal + broker ledger | V6.24", "Trade Journal"],
  calendar: ["Daily prep | V6.23", "Calendar"],
  safe: ["Approval inbox | V6.23", "Safe"],
  vault: ["Connections & security", "Vault checks"],
  music: ["Apple Music | V6.23", "Music"],
  phone: ["Winston lifecycle line | V6.23", "Desk Phone"],
  bookshelf: ["Strategy library | V6.23", "Bookshelf"],
  clock: ["Market sessions | V6.23", "Desk Clock"],
  window: ["Market weather | V6.23", "Window View"],
  lamp: ["Risk command | V6.23", "Desk Lamp"],
  drawer: ["Backtest lab | V6.23", "Desk Drawer"],
  notes: ["Bull Report | V6.23", "Bull Report"],
};

const screenRegion = { x: 0.348, y: 0.413, w: 0.296, h: 0.233 };
const hotspotDefinitions = getSovereignHotspots();

function fallbackState() {
  return {
    ok: false,
    timestamp: new Date().toISOString(),
    uptime_seconds: 0,
    execution_armed: false,
    broker: { ok: false, reason: "loading" },
    paper_endpoint: null,
    positions: [],
    positions_error: null,
    summary: {
      open_positions: null,
      unrealized_pl: null,
      symbols_watched: null,
      recent_decisions: null,
    },
    risk: {
      risk_per_trade: null,
      max_dollar_risk_per_trade: null,
      max_daily_loss_pct: null,
      max_open_positions: null,
      max_stop_pct: null,
      pyramid_add_fraction: null,
    },
    guardrails: {
      paper_only: null,
      time_in_force: null,
      take_profit_r: null,
      auth_required: null,
      approval_required: null,
      approval_mode_source: "Unknown",
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
      summary: { open_positions: null, open_orders: null, recent_fills: null, guardrails: null, management_actions: null, unrealized_pl: null, open_risk: null, average_r_multiple: null },
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
        provider: "pockettts",
        configured: false,
        available: false,
        voice: "winston",
        model: "tts-1",
        detail: "Checking Winston voice service",
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
      month_pl: null,
      unrealized_pl: dashboardState?.ok && !dashboardState?.positions_error ? dashboardState?.summary?.unrealized_pl : null,
      equity_change: null,
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

function fallbackMentorState() {
  return {
    ok: false,
    version: "bull_mentor_v1",
    timestamp: dashboardState.timestamp,
    scope: "weekly",
    mode: "retail",
    advisory_only: true,
    headline: "Velez Mentor is reading the journal and building an evidence-backed scorecard.",
    profile: {
      experience_level: "developing",
      primary_mode: "auto",
      coaching_style: "concise",
      goals: [],
      local_only: true,
    },
    sample: {
      decisions: { count: 0, confidence: "low" },
      performance: { count: 0, confidence: "insufficient", note: "Closed-trade performance needs more evidence." },
      execution: { count: 0, confidence: "low" },
    },
    scorecards: [
      { key: "risk_discipline", label: "Risk discipline", score: null, status: "insufficient", sample: 0 },
      { key: "setup_selection", label: "Setup selection", score: null, status: "insufficient", sample: 0 },
      { key: "execution_quality", label: "Execution quality", score: null, status: "insufficient", sample: 0 },
      { key: "process_consistency", label: "Process consistency", score: null, status: "insufficient", sample: 0 },
    ],
    metrics: {
      discipline: { decisions: 0, actionable: 0, average_receipt_score: null },
      performance: { terminal_trades: 0, sufficient_sample: false, expectancy_r: null },
      execution: { planned_parents: 0, participation_breaches: 0, slippage_samples: 0 },
      prop: { applicable: false },
    },
    patterns: [],
    recommendation: {
      title: "One-rule session",
      instruction: "Collect qualified journal evidence, then let Velez Mentor identify the first measurable development edge.",
      dimension: "process_consistency",
    },
    active_drills: [],
    recent_autopsies: [],
    evidence: [],
    goals: [],
    guardrails: {
      can_submit_orders: false,
      can_approve_orders: false,
      can_change_risk: false,
      facts_from_journal_only: true,
    },
  };
}

function currentMentorState() {
  return mentorState || fallbackMentorState();
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
  const verified = Boolean(dashboardState?.ok && !dashboardState?.positions_error);
  const unrealized = verified ? dashboardState?.summary?.unrealized_pl : null;
  return {
    ok: false,
    timestamp: dashboardState?.timestamp || new Date().toISOString(),
    summary: {
      open_positions: verified ? openPositions.length : null,
      open_orders: null,
      recent_fills: null,
      guardrails: null,
      management_actions: null,
      unrealized_pl: unrealized,
      open_risk: null,
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
  const openRisk = Number(currentLifecycleState().summary?.open_risk || 0);
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
  const quality = scannerQualityState || scanner.quality || {};
  const qualitySummary = quality.summary || {};
  const qualityEntries = quality.entries || [];
  const symbolStats = quality.symbol_stats || [];
  const sessionStats = quality.session_stats || [];
  const recommendations = quality.watchlist_recommendations || watchlistQualityState?.recommendations || [];
  const config = scanner.config || {};
  const decisions = scanner.decisions || [];
  const pause = scanner.pause || {};
  const exposure = scanner.exposure || {};
  const exposureItems = exposure.items || {};
  const today = scanner.today || {};
  const counts = today.counts || {};
  const rejectedReasons = today.rejected_reasons || {};
  const statusLabel = scanner.enabled ? (scanner.running ? "Running" : "Stopped") : "Disabled";
  const modeLabel = scanner.mode || "unknown";
  const controlMode = scanner.control_mode || (config.auto_submit ? "auto_submit" : "diagnostic");
  const modeButtons = [
    ["auto_submit", "Auto-submit"],
    ["diagnostic", "Diagnostic only"],
    ["paused", "Paused"],
  ];
  const detail = pause.paused
    ? pause.detail || "Scanner paused because max exposure is reached."
    : scanner.last_error || config.note || "VPS scanner watches newly closed bars from the bot watchlist.";
  return `
    <section class="tool-section">
      <div class="section-title">Hybrid VPS scanner</div>
      ${
        pause.paused
          ? `<div class="empty-state compact attention">Scanner paused: max exposure reached.</div>`
          : ""
      }
      <div class="metric-grid">
        ${metric("Scanner", statusLabel, modeLabel)}
        ${metric("Timeframe", config.timeframe || "1Min", `${config.interval_seconds || 60}s interval`)}
        ${metric("Last scan", scanner.last_scan_at ? timeAgo(scanner.last_scan_at) : "Warming", `${scanner.symbols_scanned || 0} lanes`)}
        ${metric("Exposure", `${exposure.active_exposure ?? 0}/${exposure.max_open_positions ?? dashboardState.risk?.max_open_positions ?? 0}`, `${exposure.positions ?? 0} positions | ${exposure.open_orders ?? 0} orders`)}
        ${metric("Futures", config.futures_configured ? "Polygon on" : "Key needed", config.futures_provider || "polygon")}
        ${metric("Signals", scanner.signals_found || 0, config.auto_submit ? "Routes to paper guardrails" : "Diagnostic only")}
      </div>
      <div class="metric-grid compact-metrics">
        ${metric("Today", counts.total || 0, "Scanner decisions")}
        ${metric("Submitted", counts.submitted || 0, `${counts.proposed || 0} proposed`)}
        ${metric("Rejected", counts.rejected || 0, Object.entries(rejectedReasons).map(([key, value]) => `${key}: ${value}`).join(", ") || "No scanner rejects")}
        ${metric("Cooldown", scanner.mode === "cooldown" ? "Active" : "Ready", `${config.symbol_cooldown_seconds || 0}s per symbol`)}
      </div>
      <div class="actions">
        ${modeButtons
          .map(
            ([mode, label]) => `
              <button class="${mode === controlMode ? "action-button" : "symbol-button"}" type="button" data-scanner-mode="${mode}" ${approvalToken ? "" : "disabled"} aria-pressed="${mode === controlMode ? "true" : "false"}">
                <i data-lucide="${mode === "auto_submit" ? "zap" : mode === "diagnostic" ? "stethoscope" : "pause"}"></i>
                ${label}
              </button>
            `,
          )
          .join("")}
        <button class="symbol-button" type="button" data-scanner-cancel-stale ${approvalToken ? "" : "disabled"}>
          <i data-lucide="trash-2"></i>
          Cancel stale orders
        </button>
        <button class="symbol-button" type="button" data-scanner-quality>
          <i data-lucide="activity"></i>
          Quality
        </button>
        <button class="symbol-button" type="button" data-watchlist-quality>
          <i data-lucide="badge-check"></i>
          Lane manager
        </button>
        <button class="symbol-button" type="button" data-scanner-quality-notify ${approvalToken ? "" : "disabled"}>
          <i data-lucide="send"></i>
          Send report
        </button>
      </div>
      <div class="metric-grid compact-metrics">
        ${metric("Quality", qualitySummary.total || 0, qualitySummary.readback || "Load scanner quality")}
        ${metric("Accepted", qualitySummary.accepted || 0, `${qualitySummary.rejected || 0} rejected | ${qualitySummary.skipped || 0} skipped`)}
        ${metric("Replay wins", qualitySummary.would_win || 0, `${qualitySummary.would_stop || 0} would stop`)}
        ${metric("Best lane", symbolStats[0]?.symbol || "N/A", symbolStats[0] ? `score ${symbolStats[0].score}` : "No stats")}
      </div>
      <div class="data-list">
        ${row("Mode", scanner.enabled ? "TradingView + VPS scanner" : "TradingView only")}
        ${row("Supported", (config.supported_assets || ["equity", "crypto"]).join(", "))}
        ${row("Futures map", Object.entries(config.futures_contracts || {}).map(([key, value]) => `${key}->${value}`).join(", ") || "Not configured")}
        ${row("Guardrail", "Uses the same Velez sizing/risk engine as webhooks")}
        ${row("Skipped", (scanner.skipped || []).join(", ") || "None")}
        ${row("Readback", detail)}
        ${row("Session filters", quality.filters ? `${quality.filters.rth_start}-${quality.filters.rth_end} ET${quality.filters.avoid_lunch ? ` | avoids ${quality.filters.lunch_start}-${quality.filters.lunch_end}` : ""}` : "Quality report not loaded")}
      </div>
      ${
        symbolStats.length
          ? `<div class="coverage-list">${symbolStats.slice(0, 6).map(scannerSymbolStatCard).join("")}</div>`
          : ""
      }
      ${
        recommendations.length
          ? `<div class="coverage-list">${recommendations.slice(0, 8).map(watchlistQualityRecommendationCard).join("")}</div>`
          : ""
      }
      ${
        sessionStats.length
          ? `<div class="coverage-list">${sessionStats.slice(0, 5).map(scannerSessionStatCard).join("")}</div>`
          : ""
      }
      <div class="data-list compact-list">
        ${row("Exposure symbols", (exposureItems.symbols || []).join(", ") || "None")}
        ${row("Positions", (exposureItems.positions || []).map((item) => `${item.symbol} ${item.side || ""} ${item.qty || ""}`.trim()).join(", ") || "None")}
        ${row("Open orders", (exposureItems.open_orders || []).map((item) => `${item.symbol} ${item.side || ""} ${item.type || ""} ${item.qty || ""}${item.counts_exposure ? " *" : ""}`.trim()).join(", ") || "None")}
        ${row("Staged", (exposureItems.pending_approvals || []).map((item) => `${item.symbol} ${item.side || ""} ${item.qty || ""}`.trim()).join(", ") || "None")}
      </div>
      <div class="empty-state compact">Scanner controls require the local approval token. Open-order rows marked with `*` are orders consuming exposure without a current position.</div>
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
      ${
        qualityEntries.length
          ? `<div class="replay-list">${qualityEntries.slice(0, 6).map(scannerQualityCard).join("")}</div>`
          : ""
      }
    </section>
  `;
}

function watchlistQualityMap() {
  const rows = watchlistQualityState?.symbols || [];
  const bySymbol = {};
  rows.forEach((item) => {
    if (item.symbol) bySymbol[item.symbol] = item.quality || {};
  });
  (scannerQualityState?.watchlist_recommendations || []).forEach((item) => {
    if (item.symbol && !bySymbol[item.symbol]) bySymbol[item.symbol] = item;
  });
  return bySymbol;
}

function watchlistQualityRecommendationCard(item) {
  const state = item.state || "keep_watching";
  const tone = state === "promote" ? "healthy" : state === "disable_candidate" ? "never" : state === "cool_down" ? "stale" : "new";
  const action = state === "disable_candidate" ? "disable" : state === "promote" ? "promote" : state === "cool_down" ? "cool_down" : "keep_watching";
  return `
    <article class="health-card ${coverageTone(tone)}">
      <div>
        <strong>${escapeHtml(item.symbol || "Symbol")}</strong>
        <span>${escapeHtml(`${state.replaceAll("_", " ")} | ${item.reason || "Quality lane review"}`)}</span>
      </div>
      <button class="symbol-button compact-action" type="button" data-watchlist-quality-action="${escapeHtml(action)}" data-watchlist-quality-symbol="${escapeHtml(item.symbol || "")}" ${approvalToken ? "" : "disabled"}>
        ${escapeHtml(action.replaceAll("_", " "))}
      </button>
    </article>
  `;
}

function scannerSymbolStatCard(item) {
  return `
    <article class="health-card ${coverageTone((item.score || 0) > 0 ? "healthy" : item.would_stop ? "never" : "stale")}">
      <div>
        <strong>${escapeHtml(item.symbol || "Symbol")}</strong>
        <span>${escapeHtml(`${item.accepted || 0} accepted | ${item.would_win || 0} win replay | ${item.would_stop || 0} stop replay`)}</span>
      </div>
      <small>${escapeHtml(`score ${item.score || 0}`)}</small>
    </article>
  `;
}

function scannerSessionStatCard(item) {
  return `
    <article class="health-card ${coverageTone(item.would_win > item.would_stop ? "healthy" : item.would_stop ? "stale" : "never")}">
      <div>
        <strong>${escapeHtml(item.bucket || "session")}</strong>
        <span>${escapeHtml(`${item.total || 0} event(s) | ${item.would_win || 0} wins | ${item.would_stop || 0} stops`)}</span>
      </div>
      <small>session</small>
    </article>
  `;
}

function scannerQualityCard(item) {
  const forward = item.forward_outcome || {};
  return replayEventCard({
    symbol: item.symbol,
    play: item.play || item.reason,
    side: `${item.status || "seen"} | ${item.grade || "PENDING"}`,
    order_type: `${forward.outcome || "pending"} ${forward.best_r === undefined ? "" : `${forward.best_r}R`}`.trim(),
    entry_price: item.entry_price,
    stop_price: item.stop_price,
    risk_dollars: item.lesson,
  });
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
                <span>${escapeHtml(item.submit_eligible === false ? "Conditions Not Met" : "Submit Reviewed Setup")}</span>
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
  if (!chartCaptures.length) return "No TradingView chart link saved yet";
  const latest = chartCaptures[0];
  return `${latest.symbol || "Chart"} bookmarked ${timeAgo(latest.timestamp)}`;
}

function captureCurrentChart() {
  const symbol = tradingViewLabel();
  const capture = {
    id: `${Date.now()}`,
    timestamp: new Date().toISOString(),
    symbol,
    source: "tradingview_symbol_link",
    url: `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(symbol)}`,
  };
  chartCaptures = [capture, ...chartCaptures].slice(0, 8);
  localStorage.setItem("trading-bull-chart-captures", JSON.stringify(chartCaptures));
  winstonTranscript("system", "TradingView chart link saved. Cross-origin chart pixels were not captured.");
  renderPanel();
}

function renderChartCaptureLane() {
  const latest = chartCaptures[0];
  return `
    <section class="tool-section">
      <div class="section-title">TradingView chart bookmark</div>
      <div class="data-list compact-list">
        ${row("Latest capture", chartCaptureSummary())}
        ${row("TradingView iframe", "Browser security prevents server-side iframe screenshots")}
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-chart-capture><i data-lucide="bookmark"></i> Save chart link</button>
        ${latest?.url ? `<a class="symbol-button" href="${escapeHtml(latest.url)}" target="_blank" rel="noopener noreferrer"><i data-lucide="external-link"></i> Open latest</a>` : ""}
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

function mentorScoreCard(item) {
  const score = item.score === null || item.score === undefined ? "—" : `${item.score}`;
  const tone = item.status === "strong" ? "good" : item.status === "focus" ? "bad" : "warn";
  return `
    <div class="health-card ${tone}">
      <div>
        <strong>${escapeHtml(item.label || item.key || "Mentor dimension")}</strong>
        <span>${escapeHtml(item.explanation || `${item.sample || 0} evidence item(s)`)}</span>
      </div>
      <small>${escapeHtml(score === "—" ? "Needs data" : `${score}/100`)}</small>
    </div>
  `;
}

function mentorEdgeCard(title, body, badge = "active") {
  return `
    <article class="health-card good mentor-edge-card">
      <div>
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(body || "Collecting evidence.")}</span>
      </div>
      <small>${escapeHtml(badge)}</small>
    </article>
  `;
}

function renderMentorEdges(mentor) {
  const edges = mentor.mentor_edges || {};
  const governor = edges.response_governor || mentor.response_governor || {};
  const fingerprint = edges.mistake_fingerprint || mentor.mistake_fingerprint || {};
  const shadow = edges.shadow_book || mentor.shadow_book || {};
  const challenge = edges.pre_trade_challenge || mentor.pre_trade_challenge || {};
  const replay = edges.trade_replay_coach || mentor.replay_coach || {};
  const institutional = edges.institutional_mode || mentor.institutional_read || {};
  const drill = edges.one_tap_drill_builder || mentor.drill || {};
  const persona = edges.personality_dial || mentor.personality || {};
  return `
    <section class="tool-section">
      <div class="section-title">Mentor edge suite</div>
      <div class="health-grid mentor-edge-grid">
        ${mentorEdgeCard("Response Governor", `${governor.style || "leo concise"} · ${governor.word_cap || 65} word cap`, governor.mode || "coach")}
        ${mentorEdgeCard("Mistake Fingerprint", fingerprint.readback || fingerprint.dominant?.label || "No recurring leak measured yet.", fingerprint.dominant?.key || "fingerprint")}
        ${mentorEdgeCard("Shadow Book", shadow.readback || "Tracking skipped and rejected setups.", `${shadow.blocked_count || 0} skipped`)}
        ${mentorEdgeCard("Pre-Trade Challenge", challenge.question || "One sharp stand-down question is ready.", challenge.dimension || "challenge")}
        ${mentorEdgeCard("Replay Coach", replay.readback || "Select a trade to replay entry facts versus outcome.", replay.ready ? "ready" : "waiting")}
        ${mentorEdgeCard("Institutional Lens", institutional.readback || "Liquidity, participation, slippage, and exposure checks.", institutional.applicable ? "active" : "standby")}
        ${mentorEdgeCard("One-Tap Drill", drill.title || "Build the next drill from this scorecard.", drill.dimension || "drill")}
        ${mentorEdgeCard("Personality Dial", persona.persona || "Leo concise: warm, sharp, no sermon.", persona.style || "leo_concise")}
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-mentor-build-drill><i data-lucide="dumbbell"></i> Build drill</button>
        <button class="symbol-button" type="button" data-mentor-eyes><i data-lucide="eye"></i> Eyes on TradingView</button>
      </div>
    </section>
  `;
}

function mentorStatusTone(status) {
  const cleaned = String(status || "").toLowerCase();
  if (["green", "high", "ok", "qualified_setup_detected"].includes(cleaned)) return "good";
  if (["red", "low", "source_blocked"].includes(cleaned)) return "bad";
  return "warn";
}

function renderMentorConfidenceMeter(confidence) {
  if (!confidence) return "";
  const score = Number(confidence.score || 0);
  const level = confidence.level || "low";
  return `
    <article class="health-card ${mentorStatusTone(level)} mentor-confidence-card">
      <div>
        <strong>Mentor Confidence Meter</strong>
        <span>${escapeHtml(confidence.readback || `Confidence ${score}/100`)}</span>
      </div>
      <small>${escapeHtml(`${score}/100 · ${level}`)}</small>
    </article>
  `;
}

function renderMentorSourceHealthCard(observation = null) {
  const health = mentorOpsState.sourceHealth?.health || observation?.source_health || {};
  const source = health.active_source || observation?.bars_source || "not checked";
  const status = health.status || (observation?.bars_loaded ? "green" : "yellow");
  const order = health.source_order || observation?.bars_source_order || [];
  return `
    <section class="tool-section">
      <div class="section-title">Chart Source Health</div>
      <div class="health-grid">
        <article class="health-card ${mentorStatusTone(status)}">
          <div>
            <strong>${escapeHtml(source)}</strong>
            <span>${escapeHtml(health.readback || observation?.readback || "Run a source check to verify chart bars.")}</span>
          </div>
          <small>${escapeHtml(status)}</small>
        </article>
        <article class="health-card ${mentorStatusTone(mentorOpsState.tradier?.status)}">
          <div>
            <strong>Tradier Diagnostics</strong>
            <span>${escapeHtml(mentorOpsState.tradier?.readback || "Tradier is available as a fallback check.")}</span>
          </div>
          <small>${escapeHtml(mentorOpsState.tradier?.token_present ? "token present" : "masked check")}</small>
        </article>
      </div>
      <div class="data-list compact-list">
        ${order.slice(0, 4).map((item) => row(item.source || "source", `${item.ok ? "OK" : "No"} · ${item.rows ?? item.reason ?? "checked"}`)).join("") || row("Source order", "Alpaca → Tradier → yfinance")}
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-mentor-source-health><i data-lucide="activity"></i> Check source</button>
        <button class="symbol-button" type="button" data-mentor-tradier-diagnostics><i data-lucide="shield-check"></i> Check Tradier</button>
      </div>
    </section>
  `;
}

function renderMentorSetupWatchCard(observation = null) {
  const watch = mentorOpsState.setupWatch?.watch || observation?.setup_watch || {};
  return `
    <section class="tool-section">
      <div class="section-title">Setup Watch Mode</div>
      <div class="health-card ${mentorStatusTone(watch.state)}">
        <div>
          <strong>${escapeHtml((watch.state || "watch not armed").replaceAll("_", " "))}</strong>
          <span>${escapeHtml(watch.readback || "Ask Mentor to watch the selected chart for a clean Velez setup.")}</span>
        </div>
        <small>${escapeHtml(watch.qualified ? "qualified" : "watch")}</small>
      </div>
      ${watch.blockers?.length ? `<div class="decision-meta">Blockers: ${escapeHtml(watch.blockers.join(", "))}</div>` : ""}
      <div class="actions">
        <button class="symbol-button" type="button" data-mentor-setup-watch><i data-lucide="radar"></i> Start watch</button>
      </div>
    </section>
  `;
}

function renderMentorNoTradeCoach(mentor) {
  const coach = mentorOpsState.noTrade?.coach || mentor.no_trade_coach || {};
  return `
    <section class="tool-section">
      <div class="section-title">No-trade Coach</div>
      <div class="review-list">
        <div class="review-line lesson">${escapeHtml(coach.question || "No-trade coaching will appear after blocked or ignored setups are journaled.")}</div>
        <div class="review-line">${escapeHtml(coach.readback || "Run the no-trade review to study the setups Mentor kept you out of.")}</div>
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-mentor-no-trade><i data-lucide="ban"></i> Review no-trades</button>
      </div>
    </section>
  `;
}

function renderMentorIntelligenceLab(mentor) {
  const pnl = mentorOpsState.pnlAttribution?.attribution || mentor.pnl_attribution || {};
  const drift = mentorOpsState.strategyDrift?.drift || mentor.strategy_drift || {};
  const regime = mentorOpsState.regimeCatalyst?.guardrail || mentor.regime_catalyst || {};
  const mirror = mentorOpsState.crossBotRisk?.mirror || mentor.cross_bot_risk || {};
  const replayLab = mentorOpsState.replayLab?.lab || {};
  const pnlValue = pnl.total_pnl === null || pnl.total_pnl === undefined ? "—" : money(pnl.total_pnl);
  const driftSeverity = drift.severity || "low";
  const regimeStatus = regime.status || "unknown";
  const mirrorStatus = mirror.status || "unknown";
  const replayText = replayLab.readback || "Run Replay Lab on the latest journal trade to find the first invalidation candle.";
  return `
    <section class="tool-section">
      <div class="section-title">Mentor intelligence lab</div>
      <div class="health-grid mentor-edge-grid">
        <article class="health-card ${mentorStatusTone(pnl.primary_drag ? "yellow" : "green")}">
          <div>
            <strong>P/L Attribution</strong>
            <span>${escapeHtml(pnl.readback || "Explain money movement by setup, sizing, exit, fill, regime, and no-trade buckets.")}</span>
          </div>
          <small>${escapeHtml(pnlValue)}</small>
        </article>
        <article class="health-card ${mentorStatusTone(driftSeverity)}">
          <div>
            <strong>Strategy Drift</strong>
            <span>${escapeHtml(drift.readback || "Compare current behavior against the bot's own baseline.")}</span>
          </div>
          <small>${escapeHtml(driftSeverity)}</small>
        </article>
        <article class="health-card ${mentorStatusTone(regimeStatus)}">
          <div>
            <strong>Regime + Catalyst</strong>
            <span>${escapeHtml(regime.readback || "Check market regime and loaded macro/earnings catalysts.")}</span>
          </div>
          <small>${escapeHtml(regimeStatus)}</small>
        </article>
        <article class="health-card ${mentorStatusTone(mirrorStatus)}">
          <div>
            <strong>Cross-Bot Risk Mirror</strong>
            <span>${escapeHtml(mirror.readback || "Mirror Velez exposure and configured Bull Pilot sources.")}</span>
          </div>
          <small>${escapeHtml(mirrorStatus)}</small>
        </article>
        <article class="health-card ${mentorStatusTone(replayLab.first_invalid ? "yellow" : "green")}">
          <div>
            <strong>Replay Lab</strong>
            <span>${escapeHtml(replayText)}</span>
          </div>
          <small>${escapeHtml(replayLab.first_invalid ? "invalidated" : "ready")}</small>
        </article>
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-mentor-pnl-attribution><i data-lucide="circle-dollar-sign"></i> Explain P/L</button>
        <button class="symbol-button" type="button" data-mentor-strategy-drift><i data-lucide="git-compare-arrows"></i> Check drift</button>
        <button class="symbol-button" type="button" data-mentor-regime-catalyst><i data-lucide="cloud-lightning"></i> Regime guard</button>
        <button class="symbol-button" type="button" data-mentor-cross-bot-risk><i data-lucide="combine"></i> Risk mirror</button>
        <button class="symbol-button" type="button" data-mentor-replay-lab><i data-lucide="film"></i> Replay Lab</button>
      </div>
      ${
        pnl.buckets?.length
          ? `<div class="data-list compact-list">${pnl.buckets.slice(0, 4).map((item) => row(item.label || item.bucket, `${money(item.pnl || 0)} · ${item.trades || 0} trade(s)`)).join("")}</div>`
          : ""
      }
      ${
        drift.flags?.length
          ? `<div class="review-list">${drift.flags.slice(0, 3).map((item) => `<div class="review-line">${escapeHtml(item.readback || item.label || item.metric)}</div>`).join("")}</div>`
          : ""
      }
      ${
        replayLab.first_invalid
          ? `<div class="review-line lesson">${escapeHtml(`First invalidation: ${replayLab.first_invalid.timestamp || "unknown"} · ${replayLab.first_invalid.reason || "review candle"}`)}</div>`
          : ""
      }
    </section>
  `;
}

function renderMentorSafeEnhancementLab(mentor) {
  const root = mentorOpsState.dailyRootCause?.brief || mentor.daily_root_cause || {};
  const heatmap = mentorOpsState.tradeQualityHeatmap?.heatmap || mentor.trade_quality_heatmap || {};
  const guardrail = mentorOpsState.guardrailReport?.report || mentor.guardrail_do_not_touch || {};
  const reconciliation = mentorOpsState.brokerReconciliation?.score || mentor.broker_reconciliation || {};
  const parity = mentorOpsState.botParity?.matrix || mentor.bot_parity_matrix || {};
  const changed = mentorOpsState.lastGoodWeekDelta?.delta || mentor.last_good_week_delta || {};
  const scheduler = mentorOpsState.drillScheduler?.scheduler || mentor.drill_scheduler || {};
  const worstHeatmap = heatmap.worst_rows?.[0] || heatmap.rows?.slice()?.sort((a, b) => Number(a.pnl || 0) - Number(b.pnl || 0))[0] || {};
  const deltaValue = changed.delta?.pnl === null || changed.delta?.pnl === undefined ? "—" : money(changed.delta.pnl);
  return `
    <section class="tool-section">
      <div class="section-title">Mentor safe enhancement lab</div>
      <div class="health-grid mentor-edge-grid">
        <article class="health-card ${mentorStatusTone(root.status)}">
          <div>
            <strong>Daily Root-Cause Brief</strong>
            <span>${escapeHtml(root.readback || "Find the first thing worth reviewing today across P/L, drift, no-trades, data, and cross-bot exposure.")}</span>
          </div>
          <small>${escapeHtml(root.root_cause || "ready")}</small>
        </article>
        <article class="health-card ${mentorStatusTone(worstHeatmap.grade === "avoid" ? "red" : worstHeatmap.grade === "leaky_winner" ? "yellow" : "green")}">
          <div>
            <strong>Trade Quality Heatmap</strong>
            <span>${escapeHtml(heatmap.readback || "Grade symbol/setup buckets by P/L, win rate, sample size, and cause bucket.")}</span>
          </div>
          <small>${escapeHtml(worstHeatmap.symbol ? `${worstHeatmap.symbol} · ${worstHeatmap.grade}` : "ready")}</small>
        </article>
        <article class="health-card ${mentorStatusTone(guardrail.status)}">
          <div>
            <strong>Do Not Touch Guardrails</strong>
            <span>${escapeHtml(guardrail.readback || "Read-only list of guardrails Mentor recommends keeping fixed.")}</span>
          </div>
          <small>${escapeHtml(guardrail.changes_applied === false ? "read-only" : "ready")}</small>
        </article>
        <article class="health-card ${mentorStatusTone(reconciliation.status)}">
          <div>
            <strong>Broker/Data Reconciliation</strong>
            <span>${escapeHtml(reconciliation.readback || "Score journal, broker, lifecycle, and approval queue alignment without taking broker actions.")}</span>
          </div>
          <small>${escapeHtml(reconciliation.score === undefined ? "ready" : `${reconciliation.score}/100`)}</small>
        </article>
        <article class="health-card ${mentorStatusTone(parity.status)}">
          <div>
            <strong>Bot-to-Bot Parity Matrix</strong>
            <span>${escapeHtml(parity.readback || "Compare Velez Mentor features against configured Bull Pilot evidence sources.")}</span>
          </div>
          <small>${escapeHtml(parity.rows?.length ? `${parity.rows.length} checks` : "ready")}</small>
        </article>
        <article class="health-card ${mentorStatusTone(changed.last_good ? "yellow" : "low")}">
          <div>
            <strong>Last Good Week Delta</strong>
            <span>${escapeHtml(changed.readback || "Compare this/latest week against the last positive week with enough closed trades.")}</span>
          </div>
          <small>${escapeHtml(deltaValue)}</small>
        </article>
        <article class="health-card ${mentorStatusTone("green")}">
          <div>
            <strong>Mentor Drill Scheduler</strong>
            <span>${escapeHtml(scheduler.readback || "Recommend a daily drill from the highest-priority root cause.")}</span>
          </div>
          <small>${escapeHtml(scheduler.recommended?.dimension || "daily")}</small>
        </article>
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-mentor-root-cause><i data-lucide="scan-search"></i> Root cause</button>
        <button class="symbol-button" type="button" data-mentor-quality-heatmap><i data-lucide="grid-3x3"></i> Heatmap</button>
        <button class="symbol-button" type="button" data-mentor-guardrail-report><i data-lucide="lock-keyhole"></i> Do-not-touch</button>
        <button class="symbol-button" type="button" data-mentor-reconciliation><i data-lucide="scale"></i> Reconcile score</button>
        <button class="symbol-button" type="button" data-mentor-bot-parity><i data-lucide="copy-check"></i> Bot parity</button>
        <button class="symbol-button" type="button" data-mentor-last-good-week><i data-lucide="history"></i> What changed</button>
        <button class="symbol-button" type="button" data-mentor-drill-scheduler><i data-lucide="calendar-clock"></i> Drill plan</button>
        <button class="symbol-button" type="button" data-mentor-drill-scheduler-create><i data-lucide="dumbbell"></i> Create drill</button>
      </div>
      ${
        root.evidence?.length
          ? `<div class="review-list">${root.evidence.slice(0, 3).map((item) => `<div class="review-line">${escapeHtml(item.readback || item.label || item.signal)}</div>`).join("")}</div>`
          : ""
      }
      ${
        heatmap.worst_rows?.length
          ? `<div class="data-list compact-list">${heatmap.worst_rows.slice(0, 4).map((item) => row(`${item.symbol} · ${item.setup}`, `${money(item.pnl || 0)} · ${item.grade} · ${item.trades} trade(s)`)).join("")}</div>`
          : ""
      }
      ${
        guardrail.rules?.length
          ? `<div class="data-list compact-list">${guardrail.rules.slice(0, 4).map((item) => row(item.key, `${item.recommendation || "hold"} · ${item.reason || "Keep fixed"}`)).join("")}</div>`
          : ""
      }
    </section>
  `;
}

function renderMentor() {
  const mentor = currentMentorState();
  const profile = mentor.profile || {};
  const discipline = mentor.metrics?.discipline || {};
  const performance = mentor.metrics?.performance || {};
  const execution = mentor.metrics?.execution || {};
  const trade = mentor.trade || null;
  const recommendation = mentor.recommendation || {};
  const drills = mentor.active_drills || [];
  const autopsies = mentor.recent_autopsies || [];
  const evidence = mentor.evidence || [];
  const response = mentorAskState?.reply || "";
  const scorecards = mentor.scorecards || [];
  const chartObservation = mentorEyesState?.chart_observation || mentor.chart_observation || null;
  const goals = profile.goals || mentor.goals || [];
  const selectedMode = profile.primary_mode || "auto";
  const selectedExperience = profile.experience_level || "developing";
  const selectedStyle = profile.coaching_style || "concise";
  const option = (value, label, selected) => `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
  return `
    ${renderCoachIntelligence()}
    <div class="mood-card calm mentor-hero">
      <i data-lucide="graduation-cap"></i>
      <div>
        <span>${escapeHtml(`${mentor.mode || "retail"} coaching | advisory only`)}</span>
        <strong>${escapeHtml(mentor.headline || "Velez Mentor is building your scorecard.")}</strong>
        <p>Every coaching claim comes from the local Velez journal. Velez Mentor cannot place orders, approve trades, or change risk.</p>
      </div>
    </div>
    ${renderMentorEdges(mentor)}
    <section class="tool-section">
      <div class="section-title">Evidence confidence</div>
      <div class="health-grid">
        ${renderMentorConfidenceMeter(chartObservation?.confidence_meter || mentor.mentor_confidence)}
        ${mentorEdgeCard("Evidence Mode", `Chart: ${chartObservation?.bars_source || "not checked"} · Journal: ${mentor.metrics?.discipline?.decisions || 0} decisions`, chartObservation?.source_health?.status || mentor.mentor_confidence?.level || "ready")}
      </div>
    </section>
    ${
      trade?.found
        ? `<section class="tool-section">
            <div class="section-title">Trade evidence review</div>
            <div class="decision journal-card">
              <div class="decision-top">
                <span class="decision-title">${escapeHtml([trade.symbol, trade.setup].filter(Boolean).join(" | ") || "Journal trade")}</span>
                <span class="badge">${escapeHtml(trade.status || "seen")}</span>
              </div>
              <div class="decision-meta">Alert ref ${escapeHtml(trade.alert_ref || "local")} | Estimated risk ${trade.estimated_risk === null || trade.estimated_risk === undefined ? "unavailable" : money(trade.estimated_risk)}</div>
              <div class="review-line lesson">${escapeHtml(trade.lesson || "Trade evidence is ready for review.")}</div>
              ${renderConfidenceReceipt(trade.receipt)}
            </div>
          </section>`
        : ""
    }
    <div class="metric-grid">
      ${metric("Journal sample", discipline.decisions || 0, `${mentor.sample?.decisions?.confidence || "low"} discipline confidence`)}
      ${metric("Closed outcomes", performance.terminal_trades || 0, performance.sufficient_sample ? `${performance.expectancy_r ?? 0}R expectancy` : "Expectancy withheld")}
      ${metric("Execution sample", execution.slippage_samples || 0, `${execution.participation_breaches || 0} participation breaches`)}
      ${metric("Active drills", drills.length, recommendation.title || "One focused improvement")}
    </div>
    <section class="tool-section">
      <div class="section-title">Development scorecard</div>
      <div class="health-grid">
        ${scorecards.map(mentorScoreCard).join("") || `<div class="empty-state compact">Scorecards need journal evidence.</div>`}
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-mentor-scope="today"><i data-lucide="sunrise"></i> Today</button>
        <button class="symbol-button active" type="button" data-mentor-scope="weekly"><i data-lucide="calendar-range"></i> Weekly</button>
        <button class="symbol-button" type="button" data-mentor-refresh><i data-lucide="refresh-cw"></i> ${mentorRefreshPromise ? "Reading" : "Refresh"}</button>
      </div>
    </section>
    <section class="tool-section">
      <div class="section-title">Current coaching edge</div>
      <div class="review-list">
        <div class="review-line lesson"><strong>${escapeHtml(recommendation.title || "One-rule session")}</strong><br />${escapeHtml(recommendation.instruction || "")}</div>
        ${(mentor.patterns || []).slice(0, 5).map((item) => `<div class="review-line">${escapeHtml(`${String(item.severity || "info").toUpperCase()} | ${item.message || item.key}`)}</div>`).join("")}
      </div>
    </section>
    ${renderMentorIntelligenceLab(mentor)}
    ${renderMentorSafeEnhancementLab(mentor)}
    ${renderMentorNoTradeCoach(mentor)}
    ${renderMentorSourceHealthCard(chartObservation)}
    ${renderMentorSetupWatchCard(chartObservation)}
    <section class="tool-section">
      <div class="section-title">TradingView eyes-on</div>
      <div class="review-line">Mentor reads the selected TradingView symbol/timeframe through connected bars, scanner logic, journal context, and optional browser capture metadata.</div>
      <div class="data-list compact-list">
        ${row("Selected chart", `${tradingViewBrokerSymbol()} · 5Min`)}
        ${row("Last read", chartObservation?.readback || mentorEyesState?.reply || "No chart observation requested yet")}
        ${row("Vision", chartObservation?.vision?.pixel_vision_used ? `Pixel vision used · ${chartObservation?.vision?.model || "provider"}` : chartObservation?.vision?.reason || chartObservation?.vision?.status || "Optional provider disabled")}
      </div>
      <div class="actions">
        <button class="symbol-button" type="button" data-mentor-eyes><i data-lucide="eye"></i> Ask about visible setup</button>
        <button class="symbol-button" type="button" data-chart-capture><i data-lucide="camera"></i> Capture desk chart</button>
      </div>
    </section>
    <section class="tool-section">
      <div class="section-title">Post-trade autopsies</div>
      ${
        autopsies.length
          ? `<div class="decision-list autopsy-list">${autopsies.slice(0, 5).map((autopsy) => `
              <article class="decision autopsy-card">
                <div class="decision-top">
                  <span class="decision-title">${escapeHtml(`${autopsy.symbol || "Trade"} · ${(autopsy.bar_classification?.label || "entry review").replaceAll("_", " ")}`)}</span>
                  <span class="badge">${escapeHtml(autopsy.outcome?.r_multiple === null || autopsy.outcome?.r_multiple === undefined ? autopsy.outcome?.status || "closed" : `${autopsy.outcome.r_multiple}R`)}</span>
                </div>
                <div class="decision-meta">${escapeHtml(`${timeAgo(autopsy.created_at)} | Ref ${autopsy.alert_ref || "local"} | ${autopsy.chart_source || "journal evidence"}`)}</div>
                ${autopsy.chart_url ? `<img class="autopsy-chart" src="${escapeHtml(autopsy.chart_url)}" alt="${escapeHtml(`${autopsy.symbol || "Trade"} Velez Mentor entry chart`)}" loading="lazy" />` : ""}
                <div class="review-list">
                  ${(autopsy.bullets || []).slice(0, 3).map((item, index) => `<div class="review-line"><strong>${index + 1}. ${escapeHtml(item.title || "Review")}</strong><br />${escapeHtml(item.text || "")}</div>`).join("")}
                </div>
              </article>
            `).join("")}</div>`
          : `<div class="empty-state compact">No closed-trade transition has produced an autopsy yet. Velez Mentor adds one automatically after Alpaca confirms a position is flat, and the backfill button can generate missing reviews from closed journal outcomes.</div>`
      }
      ${mentorOpsState.autopsyBackfill?.readback ? `<div class="review-line lesson">${escapeHtml(mentorOpsState.autopsyBackfill.readback)}</div>` : ""}
      <div class="actions">
        <button class="symbol-button" type="button" data-mentor-autopsy-backfill><i data-lucide="history"></i> Backfill autopsies</button>
      </div>
    </section>
    <section class="tool-section">
      <div class="section-title">Voice briefing desk</div>
      <div class="review-line">Scheduled morning and closing scripts combine Velez Mentor discipline, risk state, lifecycle state, P&amp;L, and market regime before PocketTTS sends a native Telegram voice note.</div>
      <div class="actions">
        <button class="symbol-button" type="button" data-mentor-briefing="morning"><i data-lucide="sunrise"></i> Send morning memo</button>
        <button class="symbol-button" type="button" data-mentor-briefing="evening"><i data-lucide="moon-star"></i> Send closing memo</button>
      </div>
    </section>
    <section class="tool-section">
      <div class="section-title">Active drills</div>
      ${
        drills.length
          ? `<div class="decision-list">${drills.slice(0, 5).map((drill) => `
              <article class="decision">
                <div class="decision-top">
                  <span class="decision-title">${escapeHtml(drill.title)}</span>
                  <span class="badge">${escapeHtml(drill.dimension || "process")}</span>
                </div>
                <div class="decision-meta">${escapeHtml(drill.instruction)}</div>
                <div class="actions compact-actions">
                  <button class="symbol-button" type="button" data-mentor-drill="${escapeHtml(drill.id)}" data-mentor-drill-status="completed"><i data-lucide="check"></i> Complete</button>
                  <button class="symbol-button" type="button" data-mentor-drill="${escapeHtml(drill.id)}" data-mentor-drill-status="dismissed"><i data-lucide="x"></i> Dismiss</button>
                </div>
              </article>
            `).join("")}</div>`
          : `<div class="empty-state compact">No active drill. Refresh the scorecard to create the next evidence-based exercise.</div>`
      }
    </section>
    <section class="tool-section">
      <div class="section-title">Ask Velez Mentor</div>
      <form class="winston-form" id="mentor-ask-form">
        <input id="mentor-question" type="text" maxlength="500" placeholder="What pattern should I work on next?" autocomplete="off" />
        <button class="icon-button primary" type="submit" title="Ask Velez Mentor" ${mentorAskState?.loading ? "disabled" : ""}><i data-lucide="send"></i></button>
      </form>
      ${response ? `<div class="review-list"><div class="review-line lesson">${escapeHtml(response)}</div></div>` : ""}
    </section>
    <section class="tool-section">
      <div class="section-title">Coaching profile</div>
      <form class="mentor-profile-form" id="mentor-profile-form">
        <select id="mentor-experience" aria-label="Experience level">
          ${option("beginner", "Beginner", selectedExperience)}
          ${option("developing", "Developing", selectedExperience)}
          ${option("advanced", "Advanced", selectedExperience)}
          ${option("professional", "Professional", selectedExperience)}
        </select>
        <select id="mentor-mode" aria-label="Primary coaching mode">
          ${option("auto", "Auto mode", selectedMode)}
          ${option("retail", "Retail", selectedMode)}
          ${option("institutional", "Institutional", selectedMode)}
          ${option("prop", "Prop firm", selectedMode)}
        </select>
        <select id="mentor-style" aria-label="Coaching style">
          ${option("leo_concise", "Leo concise", selectedStyle)}
          ${option("concise", "Concise", selectedStyle)}
          ${option("detailed", "Detailed", selectedStyle)}
          ${option("socratic", "Socratic", selectedStyle)}
          ${option("winston_analyst", "Winston analyst", selectedStyle)}
          ${option("prop_risk_officer", "Prop risk officer", selectedStyle)}
          ${option("velez_drill_sergeant", "Velez drill sergeant", selectedStyle)}
        </select>
        <input id="mentor-goals" type="text" maxlength="600" value="${escapeHtml(goals.join("; "))}" placeholder="Goals, separated by semicolons" />
        <button class="action-button" type="submit"><i data-lucide="save"></i> Save profile</button>
      </form>
      <div class="decision-meta">Profile, reports, evidence, and drills stay in Velez's local journal.</div>
    </section>
    <section class="tool-section">
      <div class="section-title">Evidence ledger</div>
      ${
        evidence.length
          ? `<div class="data-list compact-list">${evidence.slice(0, 10).map((item) => row(item.symbol || item.source || "Journal", `${item.label || "Evidence"} | Ref ${item.alert_ref || item.journal_id || "local"}`)).join("")}</div>`
          : `<div class="empty-state compact">No exception evidence in this scope. More journal decisions will improve confidence.</div>`
      }
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
  if (value === null || value === undefined || value === "") return "Unavailable";
  const number = Number(value);
  if (!Number.isFinite(number)) return "Unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(number);
}

function percent(value) {
  if (value === null || value === undefined || value === "") return "Unknown";
  const number = Number(value);
  if (!Number.isFinite(number)) return "Unknown";
  return `${(number * 100).toFixed(2)}%`;
}

function compact(value) {
  if (value === null || value === undefined || value === "") return "Unavailable";
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

function tradingViewBrokerSymbol() {
  const selected = tradingViewSymbols.find((item) => item.symbol === tradingViewSymbol);
  return selected?.label || tradingViewSymbol.split(":").pop() || tradingViewSymbol;
}

function normalizeTradingMode(mode) {
  const value = String(mode || "dual").toLowerCase().trim();
  return Object.prototype.hasOwnProperty.call(TRADING_MODE_LABELS, value) ? value : "dual";
}

function renderTradingModeControl() {
  if (!tradingModeSelect) return;

  const mode = normalizeTradingMode(tradingModeState.trading_mode);
  const wrapper = tradingModeSelect.closest(".mode-switcher");
  const status = tradingModeState.saving ? "saving" : tradingModeState.ok ? "good" : tradingModeState.error ? "bad" : "warn";

  if (document.activeElement !== tradingModeSelect) {
    tradingModeSelect.value = mode;
  }
  tradingModeSelect.disabled = Boolean(tradingModeState.saving);

  if (wrapper) {
    wrapper.dataset.status = status;
    wrapper.title = tradingModeState.error
      ? `Trading mode sync failed: ${tradingModeState.error}`
      : `Trading mode: ${TRADING_MODE_LABELS[mode]}`;
  }
  if (tradingModeStatus) {
    tradingModeStatus.textContent = tradingModeState.saving ? "Saving" : tradingModeState.ok ? TRADING_MODE_LABELS[mode] : "Sync";
  }
}

function marketDataDisclosureState() {
  const source = dashboardState.market_data || dashboardState.data_source || {};
  const verifiedLive =
    source.live === true ||
    source.is_live === true ||
    dashboardState.live_market_data === true ||
    dashboardState.is_live_market_data === true;
  if (verifiedLive) {
    return {
      live: true,
      title: "Live market data",
      detail: source.provider ? `Verified source: ${source.provider}` : "The current feed reports a verified live state.",
    };
  }
  return {
    live: false,
    title: dashboardState.ok ? "Market data not verified live" : "Not live market data",
    detail: "Do not use displayed prices for execution until the source is verified.",
  };
}

function announceDesk(message) {
  const announcer = $("#desk-announcer");
  if (!announcer || !message) return;
  announcer.textContent = "";
  requestAnimationFrame(() => {
    announcer.textContent = String(message);
  });
}

function featureAllowed(feature) {
  return Boolean(entitlementState?.features?.[feature]?.allowed);
}

function currentDecisionSymbol() {
  return String(latestDecision()?.symbol || tradingViewLabel() || "").toUpperCase().trim();
}

async function dashboardJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.reason || payload.detail || `status ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function unavailableFeature(feature, label) {
  return {
    ok: false,
    unavailable: true,
    reason: featureAllowed(feature) ? "Unavailable" : "feature_not_entitled",
    label,
  };
}

async function refreshDecisionIntelligence(options = {}) {
  const force = Boolean(options.force);
  if (decisionIntelligencePromise) return decisionIntelligencePromise;
  const selected = latestDecision() || {};
  const symbol = String(selected.symbol || currentDecisionSymbol() || "");
  const selectedKey = `${selected.alert_ref || ""}:${symbol}`;
  const workflowDataLoaded =
    (!["drawer", "bookshelf"].includes(activePanel) || playbookState) &&
    (activePanel !== "journal" || intelligenceState) &&
    (activePanel !== "mentor" || (missedTradesState && disciplineState));
  if (!force && workflowDataLoaded && selectedKey === decisionIntelligenceKey && decisionIntelligenceFetchedAt && Date.now() - decisionIntelligenceFetchedAt < 30000) {
    return readinessState;
  }
  const params = new URLSearchParams();
  if (selected.alert_ref) params.set("alert_ref", selected.alert_ref);
  if (symbol) params.set("symbol", symbol);

  decisionIntelligencePromise = (async () => {
    try {
      entitlementState = await dashboardJson("/api/entitlements");
    } catch (error) {
      entitlementState = { ok: false, tier: "core", features: {}, reason: error.message };
    }
    const readinessParams = new URLSearchParams(params);
    if (featureAllowed("advanced_readiness")) readinessParams.set("advanced", "true");
    const contextParams = new URLSearchParams();
    if (symbol) contextParams.set("symbol", symbol);
    if (selected.play) contextParams.set("play", selected.play);
    if (selected.side) contextParams.set("side", selected.side);
    const jobs = [
      ["readiness", `/api/readiness?${readinessParams.toString()}`],
      ["market", `/api/market/context?${contextParams.toString()}`],
      ["annotations", `/api/annotations?${params.toString()}`],
    ];
    if (["drawer", "bookshelf"].includes(activePanel)) jobs.push(["playbook", "/api/playbook"]);
    if (activePanel === "journal" && featureAllowed("performance_attribution")) jobs.push(["intelligence", "/api/journal/intelligence"]);
    if (activePanel === "mentor" && featureAllowed("missed_trade_analysis")) jobs.push(["missed", "/api/missed-trades?days=30"]);
    if (activePanel === "mentor" && featureAllowed("discipline_score")) jobs.push(["discipline", "/api/discipline?days=90"]);
    const results = await Promise.all(
      jobs.map(async ([key, url]) => {
        try {
          return [key, await dashboardJson(url)];
        } catch (error) {
          return [key, { ok: false, unavailable: true, reason: error.message, status: error.status }];
        }
      }),
    );
    results.forEach(([key, payload]) => {
      if (key === "readiness") readinessState = payload;
      if (key === "market") marketContextState = payload;
      if (key === "playbook") playbookState = payload;
      if (key === "annotations") annotationsState = payload;
      if (key === "intelligence") intelligenceState = payload;
      if (key === "missed") missedTradesState = payload;
      if (key === "discipline") disciplineState = payload;
    });
    if (!featureAllowed("performance_attribution")) intelligenceState = unavailableFeature("performance_attribution", "Performance attribution requires Pro.");
    if (!featureAllowed("missed_trade_analysis")) missedTradesState = unavailableFeature("missed_trade_analysis", "Missed-trade analysis requires Pro.");
    if (!featureAllowed("discipline_score")) disciplineState = unavailableFeature("discipline_score", "Discipline Score requires Pro.");
    decisionIntelligenceFetchedAt = Date.now();
    decisionIntelligenceKey = selectedKey;
    updateWorkflowChrome();
    renderDeskOverview();
    renderMobileViews();
    if (proConsoleOpen) renderProConsole();
    if (!panelFormIsEditing()) renderPanel();
    return readinessState;
  })().finally(() => {
    decisionIntelligencePromise = null;
  });
  return decisionIntelligencePromise;
}

function deskReadinessState() {
  if (readinessState?.ok) {
    const confidence = Number(readinessState.confidence || 0);
    return {
      score: Number(readinessState.score || 0),
      label: readinessState.label || "Readiness available",
      detail: confidence
        ? `${confidence}% evidence confidence · advisory only`
        : "Insufficient verified evidence · advisory only",
      confidence,
      components: readinessState.components || [],
      timestamp: readinessState.timestamp,
      authoritativeBlocked: Boolean(readinessState.authoritative_blocked),
    };
  }
  const health = currentHealthState();
  const lifecycle = currentLifecycleState();
  let score = 0;
  if (dashboardState.ok) score += 20;
  if (dashboardState.broker?.ok) score += 25;
  if (dashboardState.paper_endpoint) score += 20;
  if (health.overall === "green") score += 20;
  else if (health.overall === "yellow") score += 10;
  if (lifecycle.ok) score += 15;

  if (score >= 80) return { score, label: "System readiness only", detail: "Trade-specific evidence is loading" };
  if (score >= 55) return { score, label: "System checks incomplete", detail: "Trade-specific evidence is loading" };
  return { score, label: "Protective mode", detail: "Trade-specific evidence is unavailable" };
}

function panelWorkflow(panel) {
  if (["tv", "laptop", "safe"].includes(panel)) return "trade";
  if (["journal", "calendar", "notes"].includes(panel)) return "review";
  if (["mentor", "phone"].includes(panel)) return "coach";
  if (["drawer", "bookshelf"].includes(panel)) return "lab";
  return "desk";
}

function updateWorkflowChrome() {
  document.body.dataset.workflow = activeWorkflow;
  document.body.classList.toggle("room-clear", roomClear);
  workflowButtons.forEach((button) => {
    const selected = !roomClear && button.dataset.workflow === activeWorkflow;
    button.classList.toggle("active", selected);
    if (selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
    const required = button.dataset.workflow === "coach" ? "coach_intelligence" : button.dataset.workflow === "lab" ? "replay_lab" : null;
    const locked = Boolean(entitlementState.ok && required && !featureAllowed(required));
    button.classList.toggle("entitlement-locked", locked);
    if (locked) button.setAttribute("aria-label", `${button.textContent.trim()} — unavailable for this tier`);
    else button.removeAttribute("aria-label");
  });
  $$('[data-pro-console-open], [data-mobile-pro-console-open]').forEach((button) => {
    const locked = Boolean(entitlementState.ok && !featureAllowed("pro_console"));
    button.classList.toggle("entitlement-locked", locked);
    button.setAttribute("aria-disabled", String(locked));
  });
}

function setActiveWorkflow(workflow) {
  const workflowPanels = {
    trade: "laptop",
    review: "journal",
    coach: "mentor",
    lab: "drawer",
  };
  const nextWorkflow = Object.prototype.hasOwnProperty.call(workflowPanels, workflow) || workflow === "desk" ? workflow : "desk";
  if (nextWorkflow === activeWorkflow && !roomClear) {
    closePanel();
    renderMobileViews();
    return;
  }
  activeWorkflow = nextWorkflow;
  roomClear = false;
  updateWorkflowChrome();
  if (activeWorkflow === "desk") {
    closePanel({ clearRoom: false });
    renderDeskOverview();
    renderMobileViews();
    return;
  }
  if (activeWorkflow === "trade" && window.matchMedia("(max-width: 760px)").matches) {
    activePanel = "tv";
    closePanel({ clearRoom: false });
    updateActiveChrome();
    renderMobileViews();
    loadMobileTradingViewWidget();
    return;
  }
  setActivePanel(workflowPanels[activeWorkflow], { syncWorkflow: false });
}

function renderDataDisclosure() {
  if (!dataDisclosure || !dataDisclosureTitle || !dataDisclosureDetail) return;
  const disclosure = marketDataDisclosureState();
  dataDisclosure.classList.toggle("good", disclosure.live);
  dataDisclosureTitle.textContent = disclosure.title;
  dataDisclosureDetail.textContent = disclosure.detail;
}

function renderDeskOverview() {
  const session = marketClock();
  const readiness = deskReadinessState();
  const lifecycle = currentLifecycleState();
  const summary = lifecycle.summary || {};
  const latest = latestDecision();
  const openRisk = lifecycle.ok && Number.isFinite(Number(summary.open_risk)) ? Math.max(0, Number(summary.open_risk)) : null;
  const unrealizedSource = lifecycle.ok ? summary.unrealized_pl : dashboardState.ok && !dashboardState.positions_error ? dashboardState.summary?.unrealized_pl : null;
  const unrealized = Number.isFinite(Number(unrealizedSource)) && unrealizedSource !== null ? Number(unrealizedSource) : null;
  const positionsSource = lifecycle.ok ? summary.open_positions : dashboardState.ok && !dashboardState.positions_error ? dashboardState.summary?.open_positions : null;
  const openPositions = Number.isFinite(Number(positionsSource)) && positionsSource !== null ? Number(positionsSource) : null;
  const maxPositions = Number(dashboardState.risk?.max_open_positions || 0);
  const maxRisk = Number(dashboardState.risk?.max_dollar_risk_per_trade || 0);
  const riskUsed = openRisk !== null && maxRisk > 0 ? Math.min(100, Math.round((openRisk / maxRisk) * 100)) : null;
  const mode = normalizeTradingMode(tradingModeState.trading_mode);
  const now = new Date();

  const setText = (selector, value) => {
    const element = $(selector);
    if (element) element.textContent = value;
  };

  setText("#desk-date", new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric" }).format(now));
  setText("#desk-time", `${new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" }).format(now)} ET`);
  setText("#desk-overview-title", session.phase === "Pre-market" ? "Morning Brief" : session.phase === "After-hours" ? "Closing Desk" : "Live Desk");
  setText("#desk-guidance", session.phase === "Market open" ? "The session is active. Stay inside the plan and the guardrails." : session.next);
  setText("#desk-score-value", readiness.score);
  setText("#desk-readiness-label", readiness.label);
  setText("#desk-readiness-detail", readiness.detail);
  setText("#desk-session", session.phase);
  setText("#desk-mode", TRADING_MODE_LABELS[mode]);
  setText("#desk-broker", dashboardState.broker?.ok ? "Connected" : "Check");

  const score = $("#desk-score");
  if (score) score.style.setProperty("--score", readiness.score);

  setText("#desk-setup-state", latest?.status ? String(latest.status).replaceAll("_", " ") : "Waiting");
  setText("#desk-setup-title", latest ? [latest.symbol, latest.play].filter(Boolean).join(" · ") || "Latest decision" : "No decision loaded yet");
  setText("#desk-setup-detail", latest?.reason || "The latest screened setup will appear here.");

  setText("#desk-open-risk", openRisk === null ? "Unavailable" : money(openRisk));
  setText("#desk-open-risk-detail", openRisk === null ? "Awaiting authoritative lifecycle state" : openRisk > 0 ? `${riskUsed}% of per-trade risk ceiling` : "Verified: no measured open risk");
  setText("#desk-unrealized-pl", unrealized === null ? "Unavailable" : `${unrealized > 0 ? "+" : ""}${money(unrealized)}`);
  setText("#desk-position-count", openPositions === null ? "Position state unavailable" : `${openPositions} open position${openPositions === 1 ? "" : "s"}`);
  setText("#desk-daily-limit", dashboardState.risk?.max_daily_loss_pct == null ? "Unknown" : percent(dashboardState.risk.max_daily_loss_pct));
  setText("#desk-max-positions", dashboardState.risk?.max_open_positions == null ? "Unknown" : maxPositions);
  setText("#desk-approval-mode", dashboardState.guardrails?.approval_required == null ? "Unknown" : dashboardState.guardrails.approval_required ? "Required" : "Guarded");

  const pnlMetric = $(".desk-risk-metric.pnl");
  pnlMetric?.classList.toggle("positive", unrealized > 0);
  pnlMetric?.classList.toggle("negative", unrealized < 0);
  const meter = $("#desk-risk-meter-fill");
  if (meter) meter.style.width = `${riskUsed ?? 0}%`;
  const safe = openPositions !== null && dashboardState.broker?.ok && (!maxPositions || openPositions < maxPositions);
  const riskState = $("#desk-risk-state");
  if (riskState) {
    riskState.textContent = safe ? "SAFE" : "CHECKING";
    riskState.classList.toggle("safe", safe);
  }
  renderDataDisclosure();
}

function renderMobileViews() {
  const mobileDesk = $("#mobile-desk-view");
  const mobileTrade = $("#mobile-trade-view");
  if (!mobileDesk && !mobileTrade) return;

  const session = marketClock();
  const readiness = deskReadinessState();
  const lifecycle = currentLifecycleState();
  const summary = lifecycle.summary || {};
  const latest = latestDecision();
  const disclosure = marketDataDisclosureState();
  const openRisk = lifecycle.ok && Number.isFinite(Number(summary.open_risk)) ? Math.max(0, Number(summary.open_risk)) : null;
  const unrealizedSource = lifecycle.ok ? summary.unrealized_pl : dashboardState.ok && !dashboardState.positions_error ? dashboardState.summary?.unrealized_pl : null;
  const unrealized = Number.isFinite(Number(unrealizedSource)) && unrealizedSource !== null ? Number(unrealizedSource) : null;
  const positionsSource = lifecycle.ok ? summary.open_positions : dashboardState.ok && !dashboardState.positions_error ? dashboardState.summary?.open_positions : null;
  const openPositions = Number.isFinite(Number(positionsSource)) && positionsSource !== null ? Number(positionsSource) : null;
  const maxRisk = Number(dashboardState.risk?.max_dollar_risk_per_trade || 0);
  const riskUsed = openRisk !== null && maxRisk > 0 ? Math.min(100, Math.round((openRisk / maxRisk) * 100)) : null;
  const now = new Date();
  const setMobileText = (selector, value) => {
    const element = $(selector);
    if (element) element.textContent = value;
  };

  setMobileText("#mobile-date", new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric" }).format(now));
  setMobileText("#mobile-time", `${new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" }).format(now)} ET`);
  setMobileText("#mobile-session", session.phase.toUpperCase());
  setMobileText("#mobile-desk-guidance", session.phase === "Market open" ? "The session is active. Stay inside the plan and the guardrails." : session.next);
  setMobileText("#mobile-score-value", readiness.score);
  setMobileText("#mobile-readiness-label", readiness.label);
  setMobileText("#mobile-readiness-detail", readiness.detail);
  setMobileText("#mobile-open-risk", openRisk === null ? "Unavailable" : money(openRisk));
  setMobileText("#mobile-risk-detail", openRisk === null ? "Authoritative risk unavailable" : openRisk > 0 ? `${riskUsed}% of per-trade risk ceiling` : "Verified: no measured open risk");
  setMobileText("#mobile-unrealized-pl", unrealized === null ? "Unavailable" : `${unrealized > 0 ? "+" : ""}${money(unrealized)}`);
  setMobileText("#mobile-position-count", openPositions === null ? "Position state unavailable" : `${openPositions} open position${openPositions === 1 ? "" : "s"}`);
  setMobileText("#mobile-setup-state", latest?.status ? String(latest.status).replaceAll("_", " ").toUpperCase() : "WAITING");
  setMobileText("#mobile-setup-title", latest ? [latest.symbol, latest.play].filter(Boolean).join(" · ") || "Latest decision" : "No decision loaded yet");
  setMobileText("#mobile-setup-detail", latest?.reason || "The latest qualified setup will appear here.");

  setMobileText("#mobile-data-title", disclosure.title);
  setMobileText("#mobile-data-detail", disclosure.detail);
  setMobileText("#mobile-chart-symbol", `${tradingViewLabel()} · 5 MIN`);
  setMobileText("#mobile-trade-readiness", `${readiness.score}%`);
  setMobileText("#mobile-trade-risk", openRisk === null ? "Unavailable" : money(openRisk));
  setMobileText("#mobile-trade-pl", unrealized === null ? "Unavailable" : `${unrealized > 0 ? "+" : ""}${money(unrealized)}`);
  setMobileText("#mobile-trade-setup-state", latest?.status ? String(latest.status).replaceAll("_", " ").toUpperCase() : "WAITING");
  setMobileText("#mobile-trade-setup-title", latest ? [latest.symbol, latest.play].filter(Boolean).join(" · ") || "Latest decision" : "No setup selected");
  setMobileText("#mobile-trade-setup-detail", latest?.reason || "A qualified setup will populate the review workflow.");
  const regime = typeof marketContextState?.regime === "object" ? marketContextState.regime?.label : marketContextState?.regime;
  setMobileText("#mobile-context-state", readinessState?.authoritative_blocked ? "BLOCKED" : readinessState?.ok ? "ADVISORY" : "UNKNOWN");
  setMobileText(
    "#mobile-context-summary",
    readinessState?.ok
      ? `${readinessState.label} · ${readinessState.confidence || 0}% evidence · Regime ${regime || "Unknown"}. ${readinessState.unknown_components?.length || 0} unknown component(s).`
      : "Verified readiness, regime, and plan context is unavailable.",
  );

  const score = $("#mobile-score");
  if (score) score.style.setProperty("--score", readiness.score);
  $("#mobile-pnl-card")?.classList.toggle("positive", unrealized > 0);
  $("#mobile-pnl-card")?.classList.toggle("negative", unrealized < 0);
  $("#mobile-trade-pnl-wrap")?.classList.toggle("positive", unrealized > 0);
  $("#mobile-trade-pnl-wrap")?.classList.toggle("negative", unrealized < 0);
  $("#mobile-data-state")?.classList.toggle("good", disclosure.live);
  $$('[data-mobile-symbol]').forEach((button) => button.classList.toggle("active", button.dataset.mobileSymbol === tradingViewSymbol));
}

function renderStatus() {
  const brokerOk = Boolean(dashboardState.broker?.ok);
  const armed = Boolean(dashboardState.execution_armed);
  const openPositions = dashboardState.ok && !dashboardState.positions_error
    ? dashboardState.summary?.open_positions ?? dashboardState.positions?.length
    : null;

  renderTradingModeControl();

  executionPill.className = `status-pill ${armed ? "good" : "warn"}`;
  executionPill.textContent = armed ? "Execution Armed" : "Proposal Mode";

  brokerPill.className = `status-pill ${brokerOk ? "good" : "bad"}`;
  brokerPill.textContent = brokerOk ? "Alpaca Paper" : "Broker Check";

  positionsPill.className = `status-pill ${openPositions === null || openPositions === undefined ? "bad" : openPositions > 0 ? "good" : "warn"}`;
  positionsPill.textContent = openPositions === null || openPositions === undefined ? "Positions Unknown" : `${openPositions} Open`;
  renderDeskOverview();
  renderMobileViews();
  if (proConsoleOpen) renderProConsole();
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
  const receiptScore = receipt.score === null || receipt.score === undefined ? "Unknown" : `${receipt.score}/100`;
  return `
    <div class="receipt-card">
      <div class="decision-meta">${escapeHtml(receipt.summary || `Confidence ${receiptScore}`)}</div>
      <div class="data-list compact-list">
        ${row("Receipt", `${receiptScore} | Grade ${receipt.grade || "Unknown"}`)}
        ${row("Risk readback", receipt.risk_readback || "Risk receipt pending")}
        ${row("Next", receipt.next_action || "Wait for qualified structure")}
      </div>
      ${
        checks.length
          ? `<div class="health-grid receipt-grid">${checks.slice(0, 4).map((check) => healthComponentCard({ name: check.name, ok: check.ok, status: check.ok ? "pass" : "review", detail: check.detail || (check.weight == null ? "Weight unavailable" : `${check.weight} points`) })).join("")}</div>`
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
        <button class="symbol-button" type="button" data-mentor-trade="${escapeHtml(entry.alert_ref || "")}">
          <i data-lucide="graduation-cap"></i>
          Mentor
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
          <button class="symbol-button" type="button" data-mentor-trade="${escapeHtml(entry.alert_ref || "")}"><i data-lucide="graduation-cap"></i> Mentor review</button>
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
        ${metric("Paper trading", state.ok ? (state.execution_armed ? "Armed" : "Off") : "Unknown", state.ok ? (state.execution_armed ? "Qualified alerts can submit" : "Proposal mode") : "Risk state unavailable")}
        ${metric("Approval gate", state.ok ? (approvalRequired ? "Required" : "Current mode") : "Unknown", state.approval_mode_source || "Unknown")}
        ${metric("Max risk", money(risk.max_dollar_risk_per_trade), `${percent(risk.risk_per_trade)} equity cap`)}
        ${metric("Lot flow", lotSizing.enabled === false ? "Off" : lotSizing.max_lots == null ? "Unknown" : `1-${lotSizing.max_lots} lots`, `${percent(lotSizing.lot_risk_fraction)} risk per lot`)}
      </div>
      <div class="data-list compact-list">
        ${row("Daily loss", `${percent(risk.max_daily_loss_pct)} | ${risk.max_open_positions ?? "Unknown"} max positions`)}
        ${row("Paper only", compact(guardrails.paper_only))}
        ${row("Webhook auth", compact(guardrails.auth_required))}
        ${row("Max stop", percent(risk.max_stop_pct))}
        ${row("Pyramid add", percent(risk.pyramid_add_fraction))}
        ${row("Full core", lotSizing.max_lots == null ? "Unknown" : `${lotSizing.max_lots} lots = configured max risk`)}
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
  const needsAction = summary.needs_action || {};
  const partialPlans = lifecycle.partial_plans || [];
  const reductionPlan = lifecycle.reduction_plan || {};
  const scannerReopen = lifecycle.scanner_reopen || {};
  const performance = dashboardState.performance || {};
  const avgR = summary.average_r_multiple === null || summary.average_r_multiple === undefined ? "N/A" : `${Number(summary.average_r_multiple).toFixed(2)}R`;
  return `
    <section class="tool-section lifecycle-section">
      <div class="section-title">Trade lifecycle command center</div>
      <div class="metric-grid">
        ${metric("Active trades", summary.open_positions ?? "Unavailable", `${summary.open_orders ?? "Unavailable"} open broker orders`)}
        ${metric("Open risk", money(summary.open_risk), `${money(summary.unrealized_pl)} unrealized`)}
        ${metric("Avg R", avgR, `${summary.management_actions ?? "Unavailable"} rule checks`)}
        ${metric("Guardrails", summary.guardrails ?? (lifecycle.ok ? guardrails.length : "Unavailable"), lifecycle.ok ? "Broker reconciliation online" : "Needs refresh")}
        ${metric("Today P/L", performance.daily_pnl === null || performance.daily_pnl === undefined ? "N/A" : money(performance.daily_pnl), performance.source ? "Alpaca account" : "Broker read pending")}
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
        <button class="symbol-button" type="button" data-lifecycle-breakeven ${approvalToken ? "" : "disabled"}>
          <i data-lucide="shield-check"></i>
          Breakeven stops
        </button>
        <button class="symbol-button" type="button" data-lifecycle-partials>
          <i data-lucide="pie-chart"></i>
          Plan partials
        </button>
        <button class="symbol-button" type="button" data-lifecycle-doctor>
          <i data-lucide="stethoscope"></i>
          Position Doctor
        </button>
        <button class="symbol-button" type="button" data-lifecycle-auto-claim ${approvalToken ? "" : "disabled"}>
          <i data-lucide="link"></i>
          Auto-claim
        </button>
        <button class="symbol-button" type="button" data-lifecycle-reduction-plan>
          <i data-lucide="scissors"></i>
          Reduce plan
        </button>
      </div>
      <div class="data-list compact-list">
        ${row("Readback", lifecycle.readback || "Lifecycle readback pending")}
        ${row("Needs action", needsAction.readback || "No lifecycle action is due.")}
        ${row("Scanner reopen", scannerReopen.readback || "Run Position Doctor for scanner reopen status.")}
        ${row("Win rate", performance.win_rate === null || performance.win_rate === undefined ? "Not shown until completed broker lots exist." : `${(Number(performance.win_rate) * 100).toFixed(1)}% — ${performance.win_rate_status || "broker fill ledger"}`)}
        ${row("Updated", timeAgo(lifecycle.timestamp))}
        ${row("Mode", lifecycle.note || "Read-only lifecycle watch")}
      </div>
      ${
        needsAction.items?.length
          ? `<div class="health-grid">${needsAction.items.slice(0, 4).map((item) => healthComponentCard({ name: `${item.symbol} | ${item.action}`, ok: item.severity !== "critical" && item.severity !== "due", status: item.severity || "watch", detail: item.detail })).join("")}</div>`
          : ""
      }
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
        lifecycle.doctor_positions?.length
          ? `<div class="decision-list">${lifecycle.doctor_positions.slice(0, 6).map(positionDoctorCard).join("")}</div>`
          : ""
      }
      ${
        reductionPlan.suggestions?.length
          ? `<div class="replay-list">${reductionPlan.suggestions.slice(0, 6).map(reductionPlanCard).join("")}</div>`
          : ""
      }
      ${
        partialPlans.length
          ? `<div class="replay-list">${partialPlans.slice(0, 6).map(partialPlanCard).join("")}</div>`
          : ""
      }
      ${
        outcomes.length
          ? `<div class="replay-list lifecycle-outcomes">${outcomes.slice(0, 4).map(lifecycleOutcomeCard).join("")}</div>`
          : ""
      }
    </section>
  `;
}

function reductionPlanCard(item) {
  const options = item.options || [];
  return `
    <article class="decision lifecycle-card">
      <div class="decision-top">
        <span class="decision-title">${escapeHtml(item.symbol || "Position")} reduce</span>
        <span class="badge">${escapeHtml(item.current_r_multiple === null || item.current_r_multiple === undefined ? "R N/A" : `${Number(item.current_r_multiple).toFixed(2)}R`)}</span>
      </div>
      <div class="decision-meta">${escapeHtml(item.recommendation || "Review")} | ${escapeHtml(item.reason || "No reduction detail")}</div>
      <div class="actions">
        ${options.map((option) => `
          <button class="symbol-button" type="button" data-lifecycle-reduce-symbol="${escapeHtml(item.symbol || "")}" data-lifecycle-reduce-fraction="${escapeHtml(String(option.fraction || ""))}" ${approvalToken ? "" : "disabled"}>
            <i data-lucide="minus-circle"></i>
            ${escapeHtml(option.label || "Reduce")} ${escapeHtml(String(option.qty || ""))}
          </button>
        `).join("")}
      </div>
    </article>
  `;
}

function positionDoctorCard(position) {
  const candidates = position.claim_candidates || [];
  const actions = position.actions || [];
  const rValue = position.current_r_multiple === null || position.current_r_multiple === undefined ? "R N/A" : `${Number(position.current_r_multiple).toFixed(2)}R`;
  return `
    <article class="decision lifecycle-card">
      <div class="decision-top">
        <span class="decision-title">${escapeHtml(position.symbol || "Position")} doctor</span>
        <span class="badge">${escapeHtml(rValue)}</span>
      </div>
      <div class="decision-meta">${escapeHtml([position.side, `qty ${position.qty || 0}`, `P/L ${money(position.unrealized_pl || 0)}`].filter(Boolean).join(" | "))}</div>
      <div class="data-list compact-list">
        ${row("Broker", [`Entry ${position.entry_price ?? "N/A"}`, `Stop ${position.stop_price ?? "missing"}`, position.stop_source || "unknown"].join(" | "))}
        ${row("Journal", position.linked_alert_ref ? `${position.linked_alert_ref} | ${position.linked_setup || "setup"}` : "No journal link")}
        ${row("Next", position.next_action || "Review position state.")}
      </div>
      ${
        actions.length
          ? `<div class="health-grid lifecycle-rule-grid">${actions.map((item) => healthComponentCard({ name: item.name, ok: item.status === "ok" ? true : item.status === "blocked" ? false : "yellow", status: item.status || "watch", detail: item.detail })).join("")}</div>`
          : ""
      }
      <div class="actions">
        <button class="symbol-button" type="button" data-lifecycle-repair-stop="${escapeHtml(position.symbol || "")}" ${approvalToken ? "" : "disabled"}>
          <i data-lucide="shield-plus"></i>
          Repair stop
        </button>
        ${(position.reduction_options || []).map((option) => `
          <button class="symbol-button" type="button" data-lifecycle-reduce-symbol="${escapeHtml(position.symbol || "")}" data-lifecycle-reduce-fraction="${escapeHtml(String(option.fraction || ""))}" ${approvalToken ? "" : "disabled"}>
            <i data-lucide="minus-circle"></i>
            Exit ${escapeHtml(option.label || "")}
          </button>
        `).join("")}
        ${
          candidates.length
            ? candidates.map((candidate) => `
                <button class="symbol-button" type="button" data-lifecycle-claim-symbol="${escapeHtml(position.symbol || "")}" data-lifecycle-claim-ref="${escapeHtml(candidate.alert_ref || "")}" ${approvalToken ? "" : "disabled"}>
                  <i data-lucide="link"></i>
                  Claim ${escapeHtml(candidate.play || candidate.alert_ref || "journal")}
                </button>
              `).join("")
            : ""
        }
      </div>
    </article>
  `;
}

function partialPlanCard(plan) {
  return `
    <article class="decision lifecycle-card">
      <div class="decision-top">
        <span class="decision-title">${escapeHtml(plan.symbol || "Position")} partial plan</span>
        <span class="badge">${escapeHtml(plan.current_r_multiple === null || plan.current_r_multiple === undefined ? "R N/A" : `${Number(plan.current_r_multiple).toFixed(2)}R`)}</span>
      </div>
      <div class="decision-meta">${escapeHtml(plan.recommendation || "Hold")} | ${escapeHtml(plan.reason || "No plan detail")}</div>
      <div class="data-list compact-list">
        ${row("Options", (plan.options || []).map((item) => `${item.label}: ${item.qty}`).join(" | ") || "None")}
        ${row("Guardrail", plan.guardrail || "Planner only")}
      </div>
    </article>
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
        ${metric("Average", latency.average_latency_ms == null ? "Unavailable" : `${latency.average_latency_ms}ms`, "Probe average")}
        ${metric("Worst", latency.worst_latency_ms == null ? "Unavailable" : `${latency.worst_latency_ms}ms`, latency.warn_threshold_ms == null ? "Warning threshold unknown" : `Warn over ${latency.warn_threshold_ms}ms`)}
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
    <div class="actions">
      <button class="symbol-button" type="button" data-pro-console-open><i data-lucide="maximize-2"></i> Open Pro Console</button>
      <button class="symbol-button" type="button" data-mentor-eyes><i data-lucide="eye"></i> Ask Mentor about this setup</button>
      <button class="symbol-button" type="button" data-open-panel="mentor"><i data-lucide="graduation-cap"></i> Open Mentor</button>
    </div>
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

function evidenceValue(value, suffix = "") {
  return value === null || value === undefined || value === "" ? "Unavailable" : `${value}${suffix}`;
}

function renderReadinessIntelligence() {
  if (!readinessState?.ok) {
    return `<section class="decision-surface"><div class="section-title">Trade Readiness Score</div><div class="empty-state compact">Unavailable: verified trade evidence is still loading.</div></section>`;
  }
  const unknown = readinessState.unknown_components?.length || 0;
  return `
    <section class="decision-surface" data-feature="advanced-readiness">
      <div class="decision-heading">
        <div><small>ADVISORY · ${escapeHtml(timeAgo(readinessState.timestamp))}</small><h3>Trade Readiness Score</h3></div>
        <div class="decision-score ${readinessState.authoritative_blocked ? "blocked" : ""}">${escapeHtml(readinessState.score)}<small>/ 100</small></div>
      </div>
      <p class="decision-summary"><strong>${escapeHtml(readinessState.label || "Unknown")}</strong> · ${escapeHtml(readinessState.confidence || 0)}% evidence confidence${unknown ? ` · ${unknown} unknown` : ""}</p>
      <div class="decision-components">
        ${(readinessState.components || [])
          .map(
            (item) => `<details class="decision-component">
              <summary><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(evidenceValue(item.score, item.score === null || item.score === undefined ? "" : "%"))}</strong></summary>
              <p>${escapeHtml(item.reason || "No explanation available.")}</p>
              ${item.why_this_matters ? `<small><b>Why this matters:</b> ${escapeHtml(item.why_this_matters)}</small>` : ""}
              <em>${escapeHtml(item.source || "Unavailable")}${item.timestamp ? ` · ${escapeHtml(timeAgo(item.timestamp))}` : ""}</em>
            </details>`,
          )
          .join("")}
      </div>
      <p class="surface-guardrail">${escapeHtml(readinessState.guardrail || "This score is advisory and does not change execution permissions.")}</p>
    </section>`;
}

function renderMarketContextSurface() {
  const context = marketContextState;
  if (!context?.ok) {
    return `<section class="decision-surface"><div class="section-title">Market context</div><div class="empty-state compact">Unavailable: the verified top-down context engine has not returned current evidence.</div></section>`;
  }
  const regime = typeof context.regime === "object" ? context.regime?.label : context.regime;
  const daily = context.higher_timeframe_bias?.daily?.label || context.higher_timeframe_bias?.daily;
  const weekly = context.higher_timeframe_bias?.weekly?.label || context.higher_timeframe_bias?.weekly;
  const breadth = typeof context.breadth === "object" ? context.breadth?.label || context.breadth?.state || context.breadth?.summary : context.breadth;
  const sector = typeof context.sector_leadership === "object" ? context.sector_leadership?.label || context.sector_leadership?.leader || context.sector_leadership?.summary : context.sector_leadership;
  return `
    <section class="decision-surface">
      <div class="section-title">Market context <small>${escapeHtml(timeAgo(context.timestamp))}</small></div>
      <div class="context-grid">
        ${metric("Regime", evidenceValue(regime), context.advisory_only ? "Advisory context" : "Existing rule context")}
        ${metric("Daily / weekly", `${evidenceValue(daily)} / ${evidenceValue(weekly)}`, "Higher-timeframe bias")}
        ${metric("Breadth", evidenceValue(breadth), "Existing top-down engine")}
        ${metric("Sector lead", evidenceValue(sector), context.symbol_sector || "Unavailable")}
      </div>
      <p class="decision-summary">${escapeHtml(context.explanation || context.readback || "Explanation unavailable.")}</p>
      <p class="surface-guardrail"><b>Why this matters:</b> ${escapeHtml(context.guardrail || "Advisory context does not replace hard risk rules.")} · Source: ${escapeHtml(context.source || "Unavailable")}</p>
    </section>`;
}

function plannerInitialValue(key, fallback = "") {
  const latest = latestDecision() || {};
  const planned = plannerState?.plan || {};
  const mapping = {
    symbol: plannerState?.symbol || latest.symbol || currentDecisionSymbol(),
    direction: plannerState?.direction || (latest.side === "short" ? "sell" : latest.side),
    planned_entry: planned.planned_entry ?? latest.entry_price,
    stop: planned.stop ?? latest.stop_price,
    target_one: planned.target_one ?? latest.target_one,
    target_two: planned.target_two ?? latest.target_two ?? latest.take_profit_price ?? latest.target_price,
    invalidation_reason: planned.invalidation_reason ?? latest.invalidation_reason,
  };
  return mapping[key] ?? fallback;
}

function renderPlannerResult() {
  if (!plannerState) return `<div class="empty-state compact">Enter a complete plan to calculate broker-informed estimates. No planner action can stage or submit an order.</div>`;
  const messages = [...(plannerState.errors || []), ...(plannerState.warnings || [])];
  const risk = plannerState.risk || {};
  const plan = plannerState.plan || {};
  return `
    <div class="planner-result ${plannerState.ok ? "ready" : "blocked"}" role="status">
      <strong>${plannerState.ok ? "Ready for human review" : "Skip trade"}</strong>
      <span>${escapeHtml(plannerState.endpoint || "Unknown endpoint")} · Approval ${escapeHtml(plannerState.approval_state || "Unknown")}</span>
      <div class="planner-metrics">
        ${metric("Position size", evidenceValue(risk.calculated_position_size), risk.fractional_estimate ? "Calculated fractional estimate" : "Calculated whole-share estimate")}
        ${metric("Max planned loss", risk.maximum_planned_loss == null ? "Unavailable" : money(risk.maximum_planned_loss), `${percent(risk.configured_risk_percentage || 0)} configured risk`)}
        ${metric("Target 1", evidenceValue(plan.target_one_r, "R"), "Calculated estimate")}
        ${metric("Target 2", evidenceValue(plan.target_two_r, "R"), "Calculated estimate")}
        ${metric("Equity", risk.account_equity == null ? "Unavailable" : money(risk.account_equity), risk.account_equity_source || "Unavailable")}
        ${metric("Buying power", risk.buying_power == null ? "Unavailable" : money(risk.buying_power), risk.buying_power_source || "Unavailable")}
      </div>
      ${messages.length ? `<div class="planner-messages">${messages.map((item) => `<article><strong>${escapeHtml(String(item.code || "review").replaceAll("_", " "))}</strong><span>${escapeHtml(item.detail || "Review required.")}</span><small><b>Why this matters:</b> ${escapeHtml(item.why_this_matters || "Verify this evidence before committing risk.")}</small></article>`).join("")}</div>` : ""}
      <p class="surface-guardrail">${escapeHtml(plannerState.estimate_disclosure || "Calculated estimates are distinct from broker-confirmed values.")} ${escapeHtml(plannerState.guardrail || "")}</p>
    </div>`;
}

function renderExecutionPlanner() {
  return `
    <section class="decision-surface" data-feature="basic-planner">
      <div class="section-title">Risk and Execution Planner <small>READ-ONLY</small></div>
      <form id="execution-planner-form" class="planner-form">
        <label>Symbol<input name="symbol" required maxlength="20" autocomplete="off" value="${escapeHtml(plannerInitialValue("symbol"))}" /></label>
        <label>Direction<select name="direction" required><option value="buy" ${plannerInitialValue("direction", "buy") === "buy" ? "selected" : ""}>Long / buy</option><option value="sell" ${plannerInitialValue("direction") === "sell" ? "selected" : ""}>Short / sell</option></select></label>
        <label>Planned entry<input name="planned_entry" required inputmode="decimal" type="number" min="0.0001" step="any" value="${escapeHtml(plannerInitialValue("planned_entry"))}" /></label>
        <label>Stop<input name="stop" required inputmode="decimal" type="number" min="0.0001" step="any" value="${escapeHtml(plannerInitialValue("stop"))}" /></label>
        <label>Target one<input name="target_one" inputmode="decimal" type="number" min="0.0001" step="any" value="${escapeHtml(plannerInitialValue("target_one"))}" /></label>
        <label>Target two<input name="target_two" inputmode="decimal" type="number" min="0.0001" step="any" value="${escapeHtml(plannerInitialValue("target_two"))}" /></label>
        <label class="planner-wide">Invalidation reason<textarea name="invalidation_reason" required maxlength="500" rows="2" placeholder="What evidence makes this plan invalid?">${escapeHtml(plannerInitialValue("invalidation_reason"))}</textarea></label>
        <label class="check-label"><input name="allow_fractional" type="checkbox" ${plannerState?.risk?.fractional_estimate ? "checked" : ""} /> Allow fractional-share estimate</label>
        <button class="symbol-button primary" type="submit"><i data-lucide="calculator"></i> Calculate plan</button>
      </form>
      ${renderPlannerResult()}
    </section>`;
}

function performanceValue(value, kind = "number") {
  if (value === null || value === undefined) return "Unavailable";
  if (kind === "money") return money(value);
  if (kind === "percent") return `${Number(value).toFixed(1)}%`;
  return String(value);
}

function renderPerformanceIntelligence() {
  if (intelligenceState?.reason === "feature_not_entitled") return `<section class="decision-surface locked-surface"><div class="section-title">Performance intelligence <small>PRO</small></div><div class="empty-state compact">Server-side entitlement keeps advanced performance attribution in Pro. Basic journal and all safety state remain available.</div></section>`;
  if (!intelligenceState?.ok) return `<section class="decision-surface"><div class="section-title">Performance intelligence</div><div class="empty-state compact">Unavailable: persisted performance records are still loading.</div></section>`;
  const overall = intelligenceState.overall || {};
  const windows = intelligenceState.rolling_windows || {};
  const breakdownGroups = Object.entries(intelligenceState.breakdowns || {});
  return `
    <section class="decision-surface" data-feature="performance-attribution">
      <div class="section-title">Journal intelligence <small>${escapeHtml(intelligenceState.sample_size)} CLOSED RECORDS</small></div>
      ${intelligenceState.warning ? `<div class="sample-warning">${escapeHtml(intelligenceState.warning)} Metrics remain descriptive until the configured threshold is met.</div>` : ""}
      <div class="performance-grid">
        ${metric("Expectancy", performanceValue(overall.expectancy_r, "number") + (overall.expectancy_r == null ? "" : "R"), `${overall.r_sample_size || 0} R records`)}
        ${metric("Win rate", performanceValue(overall.win_rate, "percent"), `${overall.pnl_sample_size || 0} P/L records`)}
        ${metric("Avg win / loss", `${performanceValue(overall.average_win, "money")} / ${performanceValue(overall.average_loss, "money")}`, "Persisted dollar P/L")}
        ${metric("Profit factor", performanceValue(overall.profit_factor), overall.profit_factor_state || "Persisted P/L")}
        ${metric("Drawdown", performanceValue(overall.max_drawdown, "money"), "Peak-to-trough persisted P/L")}
        ${metric("Net P/L", performanceValue(overall.net_pnl, "money"), "Not sample data")}
      </div>
      <div class="rolling-grid">${["7", "30", "90"].map((days) => `<article><small>${days} DAYS</small><strong>${performanceValue(windows[days]?.expectancy_r)}${windows[days]?.expectancy_r == null ? "" : "R"}</strong><span>${windows[days]?.sample_size || 0} records · ${performanceValue(windows[days]?.win_rate, "percent")} wins</span></article>`).join("")}</div>
      <details class="breakdown-details"><summary>Strategy, regime, symbol, direction, time, and weekday breakdowns</summary>${breakdownGroups.map(([key, values]) => `<section><h4>${escapeHtml(key.replaceAll("_", " "))}</h4>${values?.length ? `<div class="data-list compact-list">${values.slice(0, 8).map((item) => row(item.key, `${item.sample_size} · ${performanceValue(item.expectancy_r)}${item.expectancy_r == null ? "" : "R"} · ${performanceValue(item.win_rate, "percent")}`)).join("")}</div>` : `<div class="empty-state compact">Insufficient persisted records.</div>`}</section>`).join("")}</details>
      <details class="formula-details"><summary>Documented formulas and sources</summary>${Object.entries(intelligenceState.formulas || {}).map(([key, value]) => `<p><strong>${escapeHtml(key.replaceAll("_", " "))}</strong> ${escapeHtml(value)}</p>`).join("")}<small>Source: ${escapeHtml(intelligenceState.source || "Unavailable")}</small></details>
    </section>`;
}

function reviewAlertRef() {
  return String(latestDecision()?.alert_ref || intelligenceState?.records?.[0]?.alert_ref || "");
}

function renderStructuredReview() {
  const alertRef = reviewAlertRef();
  if (!alertRef) return `<section class="decision-surface"><div class="section-title">Structured trade review</div><div class="empty-state compact">No persisted trade reference is available to review.</div></section>`;
  const review = structuredReviewState?.alert_ref === alertRef ? structuredReviewState.review || {} : {};
  const booleanOptions = (value) => `<option value="">Unknown</option><option value="true" ${value === true ? "selected" : ""}>Yes</option><option value="false" ${value === false ? "selected" : ""}>No</option>`;
  return `
    <section class="decision-surface">
      <div class="section-title">Structured trade review <small>${escapeHtml(alertRef)}</small></div>
      <form id="structured-review-form" class="review-form" data-alert-ref="${escapeHtml(alertRef)}">
        <label>Strategy / setup<input name="strategy" maxlength="120" value="${escapeHtml(review.strategy || latestDecision()?.play || "")}" /></label>
        <label>Tags<input name="setup_tags" maxlength="300" placeholder="pullback, A-grade, open" value="${escapeHtml((review.setup_tags || []).join(", "))}" /></label>
        <label>Actual entry<input name="actual_entry" type="number" min="0.0001" step="any" inputmode="decimal" value="${escapeHtml(review.actual_entry ?? "")}" /></label>
        <label>Actual exit<input name="actual_exit" type="number" min="0.0001" step="any" inputmode="decimal" value="${escapeHtml(review.actual_exit ?? "")}" /></label>
        <label>Entry quality<select name="entry_quality"><option value="">Unknown</option>${["on_plan", "early", "late", "chased"].map((value) => `<option value="${value}" ${review.entry_quality === value ? "selected" : ""}>${value.replaceAll("_", " ")}</option>`).join("")}</select></label>
        <label>Exit quality<select name="exit_quality"><option value="">Unknown</option>${["on_plan", "early", "late", "stop", "target"].map((value) => `<option value="${value}" ${review.exit_quality === value ? "selected" : ""}>${value.replaceAll("_", " ")}</option>`).join("")}</select></label>
        <label>Stop quality<select name="stop_quality"><option value="">Unknown</option>${["on_plan", "too_tight", "too_wide", "moved"].map((value) => `<option value="${value}" ${review.stop_quality === value ? "selected" : ""}>${value.replaceAll("_", " ")}</option>`).join("")}</select></label>
        <label>Target quality<select name="target_quality"><option value="">Unknown</option>${["on_plan", "too_close", "unrealistic", "structure_based"].map((value) => `<option value="${value}" ${review.target_quality === value ? "selected" : ""}>${value.replaceAll("_", " ")}</option>`).join("")}</select></label>
        <label>Missed / skipped classification<select name="skip_classification"><option value="">Not classified</option>${["valid_setup_intentionally_skipped", "valid_setup_missed", "invalid_setup_correctly_avoided", "setup_blocked_by_risk", "setup_lacking_sufficient_data"].map((value) => `<option value="${value}" ${review.skip_classification === value ? "selected" : ""}>${value.replaceAll("_", " ")}</option>`).join("")}</select></label>
        <label>Rules followed<select name="rule_followed">${booleanOptions(review.rule_followed)}</select></label>
        <label>Stop followed<select name="stop_followed">${booleanOptions(review.stop_followed)}</select></label>
        <label>Authorized setup<select name="authorized_setup">${booleanOptions(review.authorized_setup)}</select></label>
        <label>Valid skip followed<select name="valid_skip_followed">${booleanOptions(review.valid_skip_followed)}</select></label>
        <label class="planner-wide">Rules broken<textarea name="rule_broken" maxlength="1000" rows="2">${escapeHtml((review.rule_broken || []).join("\n"))}</textarea></label>
        <label class="planner-wide">Evidence and lesson<textarea name="notes" maxlength="2000" rows="3">${escapeHtml(review.notes || "")}</textarea></label>
        <button class="symbol-button primary" type="submit"><i data-lucide="save"></i> Save private review</button>
      </form>
      <p class="surface-guardrail">Persisted authenticated review only. Saving cannot stage, approve, or submit an order.</p>
    </section>`;
}

function renderCoachIntelligence() {
  const discipline = disciplineState;
  const missed = missedTradesState;
  if (discipline?.reason === "feature_not_entitled" || missed?.reason === "feature_not_entitled") {
    return `<section class="decision-surface locked-surface"><div class="section-title">Behavioral review <small>PRO</small></div><div class="empty-state compact">Coach analytics are enforced server-side for Pro. Risk, approval, and safety state remain Core.</div></section>`;
  }
  const score = discipline?.score;
  const categories = {
    valid_setup_intentionally_skipped: "Valid setup intentionally skipped",
    valid_setup_missed: "Valid setup missed",
    invalid_setup_correctly_avoided: "Invalid setup correctly avoided",
    setup_blocked_by_risk: "Setup blocked by risk",
    setup_lacking_sufficient_data: "Insufficient data",
  };
  return `
    <section class="decision-surface" data-feature="discipline-score">
      <div class="decision-heading"><div><small>PROCESS, NOT PROFITABILITY</small><h3>Trader Discipline Score</h3></div><div class="decision-score">${escapeHtml(evidenceValue(score))}${score == null ? "" : "<small>/ 100</small>"}</div></div>
      <p class="decision-summary"><strong>${escapeHtml(discipline?.label || "Unavailable")}</strong> · ${discipline?.sample_size || 0} of ${discipline?.minimum_sample || 0} required records</p>
      <div class="decision-components">${(discipline?.components || []).map((item) => `<details class="decision-component"><summary><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(evidenceValue(item.score, item.score == null ? "" : "%"))}</strong></summary><p>${escapeHtml(item.reason)}</p><small>${escapeHtml(item.recommendation)}</small></details>`).join("")}</div>
      ${(discipline?.recommendations || []).length ? `<div class="coach-recommendations"><strong>Evidence-linked next actions</strong>${discipline.recommendations.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</div>` : ""}
      <p class="surface-guardrail">${escapeHtml(discipline?.guardrail || "Insufficient evidence. No fake precision is shown.")}</p>
    </section>
    <section class="decision-surface" data-feature="missed-trade-analysis">
      <div class="section-title">Missed-trade review <small>30 DAYS</small></div>
      <div class="missed-grid">${Object.entries(categories).map(([key, label]) => `<article><strong>${escapeHtml(missed?.counts?.[key] || 0)}</strong><span>${escapeHtml(label)}</span></article>`).join("")}</div>
      ${(missed?.items || []).length ? `<div class="decision-list">${missed.items.slice(0, 12).map((item) => `<article class="decision-card"><strong>${escapeHtml([item.symbol, item.setup].filter(Boolean).join(" · ") || "Untraded alert")}</strong><span>${escapeHtml(categories[item.category] || item.category)}</span><p>${escapeHtml(item.explanation)}</p><small>${escapeHtml(timeAgo(item.timestamp))}</small></article>`).join("")}</div>` : `<div class="empty-state compact">No untraded persisted alerts need classification.</div>`}
      <p class="surface-guardrail">${escapeHtml(missed?.guardrail || "An untraded alert is never automatically labeled a mistake.")}</p>
    </section>`;
}

function renderPlaybookSurface() {
  const entries = playbookState?.entries || [];
  return `
    <section class="decision-surface" data-feature="playbook">
      <div class="section-title">Searchable Velez playbook <small>${escapeHtml(playbookState?.source || "LOADING")}</small></div>
      <form id="playbook-search-form" class="inline-form"><input id="playbook-query" name="query" type="search" maxlength="80" value="${escapeHtml(playbookQuery)}" placeholder="Search setups, triggers, or failure modes"/><button class="symbol-button" type="submit"><i data-lucide="search"></i> Search</button></form>
      ${entries.length ? `<div class="playbook-grid">${entries.map((item) => `<details class="playbook-card"><summary><span>${escapeHtml(item.title)}</span><small>${item.detected_alert_refs?.length || 0} linked records</small></summary><div><h4>Qualification</h4><ul>${(item.qualification || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul><h4>Entry / stop / targets</h4><p>${escapeHtml(item.entry_trigger)}</p><p>${escapeHtml(item.stop_logic)}</p><p>${escapeHtml(item.target_logic)}</p><h4>Invalidation</h4><p>${escapeHtml(item.invalidation)}</p><h4>Preferred regime</h4><p>${escapeHtml((item.preferred_regime || []).join(" · "))}</p><h4>Common failure modes</h4><ul>${(item.failure_modes || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul><small>${escapeHtml(item.example_state || "No verified example linked.")}</small></div></details>`).join("")}</div>` : `<div class="empty-state compact">${playbookState?.ok ? "No playbook entry matches the search." : "Playbook unavailable."}</div>`}
    </section>`;
}

function renderSymbolThesis() {
  const symbol = currentDecisionSymbol() || "SPY";
  const note = symbolNoteState?.symbol === symbol ? symbolNoteState.note || {} : {};
  const levels = (note.key_levels || []).map((item) => `${item.label}: ${item.price}`).join("\n");
  return `
    <section class="decision-surface" data-feature="thesis-notes">
      <div class="section-title">Private ticker thesis <small>${escapeHtml(symbol)}</small></div>
      <form id="symbol-note-form" class="note-form" data-symbol="${escapeHtml(symbol)}">
        <label>Thesis<textarea name="thesis" maxlength="1200" rows="3" placeholder="What must be true?">${escapeHtml(note.thesis || "")}</textarea></label>
        <label>Catalyst<textarea name="catalyst" maxlength="800" rows="2" placeholder="Verified catalyst or Unknown">${escapeHtml(note.catalyst || "")}</textarea></label>
        <label>Key levels<textarea name="key_levels" maxlength="800" rows="3" placeholder="Prior high: 105.20">${escapeHtml(levels)}</textarea></label>
        <label>Risks<textarea name="risks" maxlength="1200" rows="3" placeholder="One evidence-based risk per line">${escapeHtml((note.risks || []).join("\n"))}</textarea></label>
        <label>Invalidation<textarea name="invalidation" maxlength="800" rows="2" placeholder="What invalidates the thesis?">${escapeHtml(note.invalidation || "")}</textarea></label>
        <button class="symbol-button primary" type="submit"><i data-lucide="save"></i> Save private thesis</button>
      </form>
      <p class="surface-guardrail">Authenticated operator context. Notes are never presented as market or broker truth.</p>
    </section>`;
}

function renderLaptop() {
  const broker = dashboardState.broker || {};
  const symbols = dashboardState.symbols || [];
  const health = currentHealthState();
  const lifecycle = currentLifecycleState();
  const replay = currentReplayState();
  const latestReplay = replay.ok && replay.summary ? replay : replay.runs?.[0] || null;
  const pending = dashboardState.pending_approvals || [];
  const scanner = dashboardState.scanner || {};
  const qualityBySymbol = watchlistQualityMap();
  return `
    <section class="pro-console-launch">
      <div>
        <span>Trading workspace</span>
        <strong>Open Pro Console</strong>
        <small>TradingView, screened setups, execution planning, and risk command in one full-screen view.</small>
      </div>
      <button type="button" data-pro-console-open>
        Expand <i data-lucide="maximize-2"></i>
      </button>
    </section>
    ${renderReadinessIntelligence()}
    ${renderMarketContextSurface()}
    ${renderExecutionPlanner()}
    <div class="metric-grid">
      ${metric("Execution", dashboardState.execution_armed ? "Armed" : "Proposal", dashboardState.execution_armed ? "Paper orders enabled" : "No live submit")}
      ${metric("Broker", broker.ok ? "Connected" : "Needs check", broker.account_status || broker.reason || "Unknown")}
      ${metric("Open risk", money(lifecycle.ok ? lifecycle.summary?.open_risk : null), `${money(lifecycle.ok ? lifecycle.summary?.unrealized_pl : null)} unrealized P/L`)}
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
          .map((item) => {
            const quality = qualityBySymbol[item.symbol] || {};
            const state = quality.state || (item.enabled === false ? "disabled" : "watching");
            return `
              <button class="symbol-chip" type="button" data-remove-symbol="${escapeHtml(item.symbol)}" title="Remove ${escapeHtml(item.symbol)}">
                <span>${escapeHtml(item.symbol)}</span>
                <small>${escapeHtml(`${item.type || "equity"} | ${state.replaceAll("_", " ")}`)}</small>
                <i data-lucide="x"></i>
              </button>
            `;
          })
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
    ${renderPerformanceIntelligence()}
    ${renderStructuredReview()}
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
      ${metric("Month P/L", money(pnl.month_pl), pnl.detail || "Alpaca portfolio history")}
      ${metric("Open mark", money(pnl.unrealized_pl ?? dashboardState.summary?.unrealized_pl), "Open-position unrealized P/L")}
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
        <span class="${pnl.month_pl == null ? "" : Number(pnl.month_pl) >= 0 ? "positive" : "negative"}">${escapeHtml(money(pnl.month_pl))}</span>
        <span>${escapeHtml(`${alerts.count || 0} alerts`)}</span>
        <span>${escapeHtml(`${calendar.sessions?.length || 0} sessions`)}</span>
      </div>
    </section>
  `;
}

function renderSafe() {
  return `<section class="tool-section"><div class="section-title">Approval inbox</div>${renderApprovalInbox()}</section>`;
}

function renderVault() {
  const broker = dashboardState.broker || {};
  const apple = appleMusicBridgeStatus();
  const winston = dashboardState.winston || {};
  return `
    <section class="tool-section">
      <div class="section-title">Vault checks</div>
      <div class="health-grid">
        ${healthComponentCard({ name: "Alpaca paper", ok: Boolean(broker.ok && broker.paper), status: broker.ok ? "connected" : "check", detail: "Account key remains server-side" })}
        ${healthComponentCard({ name: "Webhook secret", ok: Boolean(dashboardState.guardrails?.auth_required), status: dashboardState.guardrails?.auth_required ? "armed" : "off", detail: "TradingView alerts require server auth" })}
        ${healthComponentCard({ name: "Approval token", ok: Boolean(approvalToken), status: approvalToken ? "local" : "empty", detail: "Only stored in this browser" })}
        ${healthComponentCard({ name: "Apple Music", ok: Boolean(apple.configured), status: apple.configured ? "signed" : "missing", detail: "Private key never reaches the browser" })}
      </div>
    </section>
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

  `;
}

function renderBookshelf() {
  return `
    ${renderPlaybookSurface()}
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
  const cities = [["New York", "America/New_York"], ["London", "Europe/London"], ["Tokyo", "Asia/Tokyo"], ["Dubai", "Asia/Dubai"]];
  const [city, zone] = cities[Number(document.body.dataset.sessionCity) || 0] || cities[0];
  const localTime = new Intl.DateTimeFormat("en-US", {timeZone: zone, dateStyle: "medium", timeStyle: "short"}).format(new Date());
  const clock = marketClock();
  const calendar = currentCalendarState();
  const upcoming = (calendar.sessions || []).filter((item) => item.date >= clock.date).slice(0, 5);
  const countdown = eventCountdownState();
  return `
    <section class="tool-section"><div class="section-title">${city} local clock</div><p>${localTime} · ${zone}</p><p class="muted">The session calendar and economic events below follow the connected US market feed. Local time does not confirm that an exchange is open.</p></section>
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
    ${renderPlaybookSurface()}
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
    ${renderSymbolThesis()}
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
    volume: sovereignMusicBaseVolume ?? (Number.isFinite(Number(music.volume)) ? Number(music.volume) : appleMusicState.playback.volume),
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
    const current = Number(sovereignMusicBaseVolume ?? music.volume ?? appleMusicState.playback.volume ?? 1);
    let next = Number(action?.value);
    if (!Number.isFinite(next)) {
      next = current + (action?.direction === "down" ? -0.12 : 0.12);
    }
    next = Math.max(0, Math.min(1, next));
    if (sovereignMusicBaseVolume !== null) { sovereignMusicBaseVolume = next; music.volume = next * 0.18; }
    else music.volume = next;
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
  if (payload.voice) {
    winstonState.voice = {
      ...winstonState.voice,
      ...payload.voice,
      statusLoaded: true,
    };
  }
  if (["ollama", "openai_compatible", "winston_rule_based_v1"].includes(payload.provider)) {
    winstonState.brain = {
      ...winstonState.brain,
      provider: payload.provider,
      model: payload.model || winstonState.brain.model,
      available: payload.degraded ? false : winstonState.brain.available,
      detail: payload.degraded ? payload.fallback_reason || "AI fallback used" : winstonState.brain.detail,
      lastLatencyMs: Number.isFinite(Number(payload.latency_ms)) ? Number(payload.latency_ms) : winstonState.brain.lastLatencyMs,
    };
  }
}

async function refreshWinstonStatus() {
  try {
    const response = await fetch("/api/winston/status", { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `status ${response.status}`);
    applyWinstonRuntime(data);
    const voice = winstonState.voice || {};
    if (
      ["fish", "pockettts"].includes(voice.provider)
      && String(voice.voice || "").trim().toLowerCase() !== WINSTON_REQUIRED_VOICE
    ) {
      winstonState.voice = {
        ...voice,
        available: false,
        detail: `Voice lock mismatch: expected ${WINSTON_REQUIRED_VOICE}`,
      };
    }
    refreshWinstonPanel();
    return true;
  } catch (error) {
    winstonState.brain = {
      ...winstonState.brain,
      available: winstonState.brain.provider === "winston_rule_based_v1",
      detail: error?.message || "Winston status unavailable",
    };
    winstonState.voice = {
      ...winstonState.voice,
      available: false,
      detail: `Winston voice status unavailable: ${error?.message || "status check failed"}`,
    };
    refreshWinstonPanel();
    return false;
  }
}

function winstonBrainLabel() {
  const provider = winstonState.brain?.provider || "winston_rule_based_v1";
  const model = String(winstonState.brain?.model || "").toLowerCase();
  const baseUrl = String(winstonState.brain?.base_url || "").toLowerCase();
  if (provider === "ollama") return "Hermes local LLM";
  if (provider === "openai_compatible" && (baseUrl.includes("api.groq.com") || model.includes("gpt-oss"))) return "Groq AI";
  if (provider === "openai_compatible" && model.includes("deepseek")) return "Locked emergency provider";
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
  const latency = brain.lastLatencyMs != null && Number.isFinite(Number(brain.lastLatencyMs))
    ? `${Math.round(Number(brain.lastLatencyMs))} ms last reply`
    : "";
  return [brain.model, latency, thinking, fallback, brain.detail].filter(Boolean).join(" | ") || "Winston ready";
}

function winstonVoiceLabel() {
  const voice = winstonState.voice || {};
  if (voice.provider === "fish" && voice.configured) return "Winston · Fish Audio";
  if (voice.provider === "pockettts" && voice.configured) return "Winston · PocketTTS";
  if (winstonState.muted) return "Winston voice muted";
  return "Winston voice unavailable";
}

function winstonVoiceDetail() {
  const voice = winstonState.voice || {};
  if (["fish", "pockettts"].includes(voice.provider) && voice.configured) {
    const latency = voice.lastLatencyMs != null && Number.isFinite(Number(voice.lastLatencyMs))
      ? `${Math.round(Number(voice.lastLatencyMs))} ms last synthesis`
      : "";
    return [
      voice.voice,
      voice.available ? "Winston voice locked" : "Winston unavailable — no generic fallback",
      latency,
    ].filter(Boolean).join(" | ");
  }
  return winstonState.muted ? "Muted" : (voice.detail || "Winston voice service is not configured");
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
  if (winstonState.speechController) {
    winstonState.speechController.abort();
    winstonState.speechController = null;
  }
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
  document.dispatchEvent(new CustomEvent("desk:winston-speaking", { detail: { speaking: false } }));
}

function unlockWinstonAudio() {
  if (!winstonAudioPlayer || winstonState.speaking) return;
  try {
    winstonAudioPlayer.muted = true;
    winstonAudioPlayer.src = WINSTON_AUDIO_UNLOCK_CLIP;
    const unlocked = winstonAudioPlayer.play();
    if (unlocked?.then) {
      unlocked
        .then(() => {
          if (winstonAudioPlayer.src.startsWith("data:audio/wav")) {
            winstonAudioPlayer.pause();
            winstonAudioPlayer.currentTime = 0;
          }
          winstonAudioPlayer.muted = false;
        })
        .catch(() => {
          winstonAudioPlayer.muted = false;
        });
    } else {
      winstonAudioPlayer.muted = false;
    }
  } catch (_) {
    winstonAudioPlayer.muted = false;
  }
}

function markServerVoiceFailure(detail) {
  winstonState.speaking = false;
  document.dispatchEvent(new CustomEvent("desk:winston-speaking", { detail: { speaking: false } }));
  winstonState.speechController = null;
  winstonState.voice = {
    ...winstonState.voice,
    available: false,
    voice: WINSTON_REQUIRED_VOICE,
    detail: detail || "Winston voice unavailable",
  };
  winstonState.message = "Winston voice unavailable — generic voice blocked";
  refreshWinstonPanel();
}

function speakBrowserWinston(text) {
  if (winstonState.muted || !("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new window.SpeechSynthesisUtterance(text);
  utterance.rate = 0.96;
  utterance.pitch = 0.92;
  // Prefer a male English voice so the fallback sounds closer to Jarvis,
  // rather than the system default (often female on macOS).
  try {
    const voices = window.speechSynthesis.getVoices();
    const male = voices.find(v => v.lang.startsWith("en") && v.name.toLowerCase().includes("male"))
      || voices.find(v => v.lang.startsWith("en") && (v.name.includes("Daniel") || v.name.includes("Alex") || v.name.includes("Tom") || v.name.includes("Fred")))
      || voices.find(v => v.lang.startsWith("en") && !v.name.toLowerCase().includes("female"));
    if (male) utterance.voice = male;
  } catch (_) { /* voice list unavailable — use default */ }
  utterance.onstart = () => {
    winstonState.speaking = true;
  document.dispatchEvent(new CustomEvent("desk:winston-speaking", { detail: { speaking: true } }));
    refreshWinstonPanel();
  };
  utterance.onend = () => {
    winstonState.speaking = false;
  document.dispatchEvent(new CustomEvent("desk:winston-speaking", { detail: { speaking: false } }));
    refreshWinstonPanel();
  };
  utterance.onerror = () => {
    winstonState.speaking = false;
  document.dispatchEvent(new CustomEvent("desk:winston-speaking", { detail: { speaking: false } }));
    refreshWinstonPanel();
  };
  window.speechSynthesis.speak(utterance);
}

function splitWinstonSpeech(text, maxChars = 180) {
  const sentences = String(text || "").match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [];
  const chunks = [];
  let current = "";
  const pushWords = (value) => {
    const words = value.trim().split(/\s+/);
    let piece = "";
    words.forEach((word) => {
      const next = piece ? `${piece} ${word}` : word;
      if (next.length > maxChars && piece) {
        chunks.push(piece);
        piece = word;
      } else {
        piece = next;
      }
    });
    if (piece) chunks.push(piece);
  };
  sentences.forEach((sentence) => {
    const cleaned = sentence.trim();
    if (!cleaned) return;
    if (cleaned.length > maxChars) {
      if (current) {
        chunks.push(current);
        current = "";
      }
      pushWords(cleaned);
      return;
    }
    const next = current ? `${current} ${cleaned}` : cleaned;
    if (next.length > maxChars && current) {
      chunks.push(current);
      current = cleaned;
    } else {
      current = next;
    }
  });
  if (current) chunks.push(current);
  return chunks.length ? chunks : [String(text || "").trim()];
}

async function fetchServerVoiceChunk(text, signal) {
  const response = await fetch("/api/winston/speech", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!response.ok) throw new Error(`Winston voice service ${response.status}`);
  const responseVoice = String(response.headers.get("X-Winston-Voice") || "").trim().toLowerCase();
  if (responseVoice !== WINSTON_REQUIRED_VOICE) {
    throw new Error(`voice lock rejected ${responseVoice || "missing voice header"}`);
  }
  const latencyMs = Number(response.headers.get("X-Winston-TTS-Latency-Ms"));
  const blob = await response.blob();
  if (!blob.size) throw new Error("empty Winston audio response");
  return { blob, latencyMs };
}

function prepareServerVoiceChunk(text, signal) {
  return fetchServerVoiceChunk(text, signal).then(
    (value) => ({ value }),
    (error) => ({ error }),
  );
}

async function playServerVoiceChunk(blob, speechId, signal) {
  const url = URL.createObjectURL(blob);
  const audio = winstonAudioPlayer || new Audio();
  audio.muted = false;
  audio.src = url;
  winstonState.audio = audio;
  let abortPlayback = null;
  try {
    await new Promise((resolve, reject) => {
      abortPlayback = () => reject(new DOMException("Winston playback cancelled", "AbortError"));
      signal?.addEventListener("abort", abortPlayback, { once: true });
      audio.onended = resolve;
      audio.onerror = () => reject(new Error("Winston audio playback failed"));
      const started = audio.play();
      if (started?.catch) started.catch(reject);
    });
  } finally {
    if (abortPlayback) signal?.removeEventListener("abort", abortPlayback);
    URL.revokeObjectURL(url);
    if (speechId === winstonState.speechRequestId) winstonState.audio = null;
  }
}

async function speakWinston(text) {
  if (winstonState.muted) return;
  const speechId = winstonState.speechRequestId + 1;
  stopWinstonAudio();
  winstonState.speechRequestId = speechId;
  if (!winstonState.voice?.statusLoaded) await refreshWinstonStatus();
  if (speechId !== winstonState.speechRequestId) return;
  const voice = winstonState.voice || {};

  if (voice.provider === "browser" && voice.statusLoaded) {
    markServerVoiceFailure(voice.detail || "Server voice lock requires Fish Winston");
    return;
  }

  if (!["fish", "pockettts"].includes(voice.provider) || !voice.configured) {
    markServerVoiceFailure(voice.detail || "Winston voice service is not configured");
    return;
  }

  if (String(voice.voice || "").trim().toLowerCase() !== WINSTON_REQUIRED_VOICE) {
    markServerVoiceFailure(`Voice lock mismatch: expected ${WINSTON_REQUIRED_VOICE}`);
    return;
  }

  const controller = new AbortController();
  winstonState.speechController = controller;
  try {
    winstonState.speaking = true;
  document.dispatchEvent(new CustomEvent("desk:winston-speaking", { detail: { speaking: true } }));
    refreshWinstonPanel();
    const chunks = splitWinstonSpeech(text);
    let prepared = prepareServerVoiceChunk(chunks[0], controller.signal);
    for (let index = 0; index < chunks.length; index += 1) {
      const result = await prepared;
      if (result.error) throw result.error;
      const current = result.value;
      if (speechId !== winstonState.speechRequestId) return;
      prepared = index + 1 < chunks.length
        ? prepareServerVoiceChunk(chunks[index + 1], controller.signal)
        : null;
      winstonState.voice = {
        ...winstonState.voice,
        available: true,
        voice: WINSTON_REQUIRED_VOICE,
        lastLatencyMs: Number.isFinite(current.latencyMs) ? current.latencyMs : winstonState.voice.lastLatencyMs,
        detail: "Winston voice locked",
      };
      refreshWinstonPanel();
      await playServerVoiceChunk(current.blob, speechId, controller.signal);
    }
    if (speechId === winstonState.speechRequestId) {
      winstonState.speaking = false;
  document.dispatchEvent(new CustomEvent("desk:winston-speaking", { detail: { speaking: false } }));
      winstonState.speechController = null;
      refreshWinstonPanel();
    }
  } catch (error) {
    if (error?.name === "AbortError") return;
    markServerVoiceFailure(error?.message || "Winston voice request failed");
  }
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
  winstonState.message = "Groq and Winston voice are ready";
  const greeting = "Winston here. Groq is online and Fish Winston voice is locked. How may I help?";
  winstonTranscript("winston", greeting);
  renderPanel();
  speakWinston(greeting);
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
  document.dispatchEvent(new CustomEvent("desk:winston-speaking", { detail: { speaking: false } }));
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
    winstonState.message = "Submitted through user-controlled workflow";
    winstonTranscript("winston", `${approvalLine(data.pending || {})}: Submitted through user-controlled workflow.`);
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

function winstonRoomContext() {
  const mission = dailyMission();
  const nowPlaying = appleMusicState.nowPlaying || {};
  return {
    environment: roomSnapshot(),
    active: {
      panel: activePanel,
      label: panelCopy[activePanel]?.[1] || activePanel,
      theme: document.body.dataset.roomTheme || "night",
    },
    chart: {
      symbol: tradingViewSymbol,
      label: tradingViewLabel(),
      broker_symbol: tradingViewBrokerSymbol(),
      timeframe: "5Min",
      loaded: tradingViewLoaded,
      latest_capture_at: chartCaptures[0]?.timestamp || null,
    },
    mission: {
      title: mission.title,
      rule: mission.rule,
      session: mission.clock?.phase,
      next: mission.clock?.next,
      weather: mission.weather?.label,
      risk_mood: mission.mood?.label,
    },
    music: {
      authorized: appleMusicState.authorized,
      ready: appleMusicState.ready,
      is_playing: appleMusicState.playback?.isPlaying,
      now_playing: {
        title: nowPlaying.title || "",
        artist: nowPlaying.artist || "",
        album: nowPlaying.album || "",
      },
    },
    phone: {
      call_active: winstonState.callActive,
      muted: winstonState.muted,
      listening: winstonState.listening,
      speaking: winstonState.speaking,
      status: winstonState.status,
    },
    notes: {
      manual_note: String(deskNote || "").slice(0, 1200),
    },
  };
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
      body: JSON.stringify({ message: text, room_context: winstonRoomContext() }),
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
  unlockWinstonAudio();
  stopWinstonAudio();
  winstonState.message = "Waiting for microphone permission";
  refreshWinstonPanel();
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
                      <span>${escapeHtml(item.submit_eligible === false ? "Conditions Not Met" : "Submit Reviewed Setup")}</span>
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

async function calculateExecutionPlan(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const fields = new FormData(form);
  const payload = {
    symbol: String(fields.get("symbol") || "").toUpperCase().trim(),
    direction: fields.get("direction"),
    planned_entry: fields.get("planned_entry"),
    stop: fields.get("stop"),
    target_one: fields.get("target_one") || null,
    target_two: fields.get("target_two") || null,
    invalidation_reason: fields.get("invalidation_reason"),
    allow_fractional: fields.get("allow_fractional") === "on",
  };
  try {
    plannerState = await dashboardJson("/api/planner/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    plannerState = error.payload || { ok: false, outcome: "skip_trade", errors: [{ code: "planner_unavailable", detail: error.message }] };
  }
  announceDesk(plannerState.ok ? "Plan calculated for human review. No order was staged." : "Plan is not valid. Skip-trade outcome shown.");
  renderPanel();
  if (proConsoleOpen) renderProConsole();
}

async function refreshStructuredReview() {
  const alertRef = reviewAlertRef();
  if (!alertRef) return null;
  try {
    structuredReviewState = await dashboardJson(`/api/journal/structured-review/${encodeURIComponent(alertRef)}`);
  } catch (error) {
    structuredReviewState = { ok: false, alert_ref: alertRef, review: null, reason: error.message };
  }
  if (activePanel === "journal" && !panelFormIsEditing()) renderPanel();
  return structuredReviewState;
}

async function saveStructuredReview(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const fields = new FormData(form);
  const alertRef = form.dataset.alertRef;
  const reviewBool = (key) => fields.get(key) === "true" ? true : fields.get(key) === "false" ? false : null;
  const payload = {
    strategy: fields.get("strategy"),
    setup_tags: String(fields.get("setup_tags") || "").split(",").map((item) => item.trim()).filter(Boolean),
    actual_entry: fields.get("actual_entry") || null,
    actual_exit: fields.get("actual_exit") || null,
    entry_quality: fields.get("entry_quality"),
    exit_quality: fields.get("exit_quality"),
    stop_quality: fields.get("stop_quality"),
    target_quality: fields.get("target_quality"),
    skip_classification: fields.get("skip_classification"),
    rule_followed: reviewBool("rule_followed"),
    stop_followed: reviewBool("stop_followed"),
    authorized_setup: reviewBool("authorized_setup"),
    valid_skip_followed: reviewBool("valid_skip_followed"),
    rule_broken: String(fields.get("rule_broken") || "").split("\n").map((item) => item.trim()).filter(Boolean),
    notes: fields.get("notes"),
  };
  try {
    const saved = await dashboardJson(`/api/journal/structured-review/${encodeURIComponent(alertRef)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    structuredReviewState = { ok: true, alert_ref: alertRef, review: saved.review };
    decisionIntelligenceFetchedAt = 0;
    announceDesk("Private trade review saved. Execution permissions were unchanged.");
    await refreshDecisionIntelligence({ force: true });
  } catch (error) {
    announceDesk(`Review was not saved: ${error.message}`);
  }
  renderPanel();
}

async function searchPlaybook(event) {
  event.preventDefault();
  playbookQuery = String(new FormData(event.currentTarget).get("query") || "").trim();
  try {
    playbookState = await dashboardJson(`/api/playbook?query=${encodeURIComponent(playbookQuery)}`);
  } catch (error) {
    playbookState = { ok: false, entries: [], reason: error.message };
  }
  renderPanel();
}

async function refreshSymbolNote() {
  const symbol = currentDecisionSymbol() || "SPY";
  try {
    symbolNoteState = await dashboardJson(`/api/notes/${encodeURIComponent(symbol)}`);
  } catch (error) {
    symbolNoteState = { ok: false, symbol, note: null, reason: error.message };
  }
  if (activePanel === "notes" && !panelFormIsEditing()) renderPanel();
  return symbolNoteState;
}

function parseKeyLevels(text) {
  return String(text || "")
    .split("\n")
    .map((line) => {
      const separator = line.lastIndexOf(":");
      const label = separator >= 0 ? line.slice(0, separator).trim() : "Key level";
      const price = Number(separator >= 0 ? line.slice(separator + 1).trim() : line.trim());
      return Number.isFinite(price) && price > 0 ? { label: label || "Key level", price } : null;
    })
    .filter(Boolean);
}

async function saveSymbolNote(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const fields = new FormData(form);
  const symbol = form.dataset.symbol;
  const payload = {
    thesis: fields.get("thesis"),
    catalyst: fields.get("catalyst"),
    key_levels: parseKeyLevels(fields.get("key_levels")),
    risks: String(fields.get("risks") || "").split("\n").map((item) => item.trim()).filter(Boolean),
    invalidation: fields.get("invalidation"),
  };
  try {
    const saved = await dashboardJson(`/api/notes/${encodeURIComponent(symbol)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    symbolNoteState = { ok: true, symbol, note: saved.note };
    annotationsState = await dashboardJson(`/api/annotations?symbol=${encodeURIComponent(symbol)}`).catch(() => annotationsState);
    announceDesk(`Private ${symbol} thesis saved.`);
  } catch (error) {
    announceDesk(`Thesis was not saved: ${error.message}`);
  }
  renderPanel();
  if (proConsoleOpen) renderProConsole();
}

function renderPanel() {
  capturePanelDrafts();
  const [kicker, title] = panelCopy[activePanel] || panelCopy.tv;
  panelKicker.textContent = kicker;
  panelTitle.textContent = title;

  const renderers = {
    tv: renderTradingScreen,
    account: workspaceAccountMarkup,
    mission: renderMission,
    mentor: renderMentor,
    laptop: renderLaptop,
    journal: renderJournal,
    calendar: renderCalendar,
    safe: renderSafe,
    vault: renderVault,
    music: renderMusic,
    phone: renderPhone,
    bookshelf: renderBookshelf,
    clock: renderClock,
    window: renderWindow,
    lamp: renderLamp,
    drawer: renderDrawer,
    research: deskRecords.renderResearch,
    performance: deskRecords.renderPerformance,
    notes: renderNotes,
  };

  panelBody.innerHTML = (renderers[activePanel] || renderTradingScreen)();
  deskRecords.bind(panelBody);
  $("#winston-call-toggle")?.addEventListener("click", () => {
    unlockWinstonAudio();
    if (winstonState.callActive) endWinstonCall();
    else startWinstonCall();
  });
  $("#winston-listen")?.addEventListener("click", toggleWinstonListening);
  $("#winston-brief")?.addEventListener("click", () => {
    unlockWinstonAudio();
    requestWinstonBrief();
  });
  $("#winston-morning-call")?.addEventListener("click", () => {
    unlockWinstonAudio();
    requestWinstonMorningCall();
  });
  $("#winston-research")?.addEventListener("click", () => {
    unlockWinstonAudio();
    requestWinstonResearch();
  });
  $("#winston-deep-research")?.addEventListener("click", () => {
    unlockWinstonAudio();
    requestWinstonResearch({ deep: true });
  });
  $("#winston-mute")?.addEventListener("click", toggleWinstonMute);
  $("#approval-token")?.addEventListener("input", (event) => {
    approvalToken = event.target.value || "";
    localStorage.setItem("trading-bull-approval-token", approvalToken);
  });
  $$("[data-approve-order]").forEach((button) => {
    button.addEventListener("click", () => {
      unlockWinstonAudio();
      approvePendingOrder(button.dataset.approveOrder, button.dataset.approvePhrase);
    });
  });
  $("#winston-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    unlockWinstonAudio();
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
  $("[data-lifecycle-breakeven]")?.addEventListener("click", moveBreakevenStops);
  $("[data-lifecycle-partials]")?.addEventListener("click", planLifecyclePartials);
  $("[data-lifecycle-doctor]")?.addEventListener("click", refreshPositionDoctor);
  $("[data-lifecycle-auto-claim]")?.addEventListener("click", autoClaimLifecyclePositions);
  $("[data-lifecycle-reduction-plan]")?.addEventListener("click", refreshReductionPlan);
  $$("[data-lifecycle-repair-stop]").forEach((button) => {
    button.addEventListener("click", () => repairLifecycleStop(button.dataset.lifecycleRepairStop || ""));
  });
  $$("[data-lifecycle-claim-symbol]").forEach((button) => {
    button.addEventListener("click", () => claimLifecyclePosition(button.dataset.lifecycleClaimSymbol || "", button.dataset.lifecycleClaimRef || ""));
  });
  $$("[data-lifecycle-reduce-symbol]").forEach((button) => {
    button.addEventListener("click", () => reduceLifecyclePosition(button.dataset.lifecycleReduceSymbol || "", Number(button.dataset.lifecycleReduceFraction || 0)));
  });
  $("[data-latency-refresh]")?.addEventListener("click", () => refreshLatency({ force: true }));
  $("[data-risk-refresh]")?.addEventListener("click", () => refreshRiskStatus({ force: true }));
  $("[data-hardening-refresh]")?.addEventListener("click", () => refreshHardening({ force: true }));
  $("[data-journal-refresh]")?.addEventListener("click", () => refreshJournal({ force: true }));
  $("[data-review-refresh]")?.addEventListener("click", () => refreshReview({ force: true }));
  $("[data-close-report-refresh]")?.addEventListener("click", () => refreshCloseReport({ force: true }));
  $("#execution-planner-form")?.addEventListener("submit", calculateExecutionPlan);
  $("#structured-review-form")?.addEventListener("submit", saveStructuredReview);
  $("#playbook-search-form")?.addEventListener("submit", searchPlaybook);
  $("#symbol-note-form")?.addEventListener("submit", saveSymbolNote);
  $("[data-mentor-refresh]")?.addEventListener("click", () => refreshMentor({ force: true }));
  $$("[data-mentor-scope]").forEach((button) => {
    button.addEventListener("click", () => refreshMentor({ force: true, scope: button.dataset.mentorScope || "weekly" }));
  });
  $("#mentor-ask-form")?.addEventListener("submit", askMentor);
  $("#mentor-profile-form")?.addEventListener("submit", saveMentorProfile);
  $$("[data-mentor-drill]").forEach((button) => {
    button.addEventListener("click", () => updateMentorDrill(button.dataset.mentorDrill, button.dataset.mentorDrillStatus));
  });
  $$("[data-mentor-briefing]").forEach((button) => {
    button.addEventListener("click", () => sendMentorBriefing(button.dataset.mentorBriefing || "evening"));
  });
  $$("[data-mentor-eyes]").forEach((button) => {
    button.addEventListener("click", () => observeMentorChart("What setup is visible on this TradingView chart?"));
  });
  $("[data-mentor-source-health]")?.addEventListener("click", checkMentorSourceHealth);
  $("[data-mentor-tradier-diagnostics]")?.addEventListener("click", checkMentorTradierDiagnostics);
  $("[data-mentor-setup-watch]")?.addEventListener("click", startMentorSetupWatch);
  $("[data-mentor-no-trade]")?.addEventListener("click", refreshMentorNoTradeCoach);
  $("[data-mentor-autopsy-backfill]")?.addEventListener("click", backfillMentorAutopsies);
  $("[data-mentor-pnl-attribution]")?.addEventListener("click", refreshMentorPnlAttribution);
  $("[data-mentor-strategy-drift]")?.addEventListener("click", refreshMentorStrategyDrift);
  $("[data-mentor-regime-catalyst]")?.addEventListener("click", refreshMentorRegimeCatalyst);
  $("[data-mentor-cross-bot-risk]")?.addEventListener("click", refreshMentorCrossBotRisk);
  $("[data-mentor-replay-lab]")?.addEventListener("click", refreshMentorReplayLab);
  $("[data-mentor-root-cause]")?.addEventListener("click", refreshMentorDailyRootCause);
  $("[data-mentor-quality-heatmap]")?.addEventListener("click", refreshMentorTradeQualityHeatmap);
  $("[data-mentor-guardrail-report]")?.addEventListener("click", refreshMentorGuardrailReport);
  $("[data-mentor-reconciliation]")?.addEventListener("click", refreshMentorBrokerReconciliation);
  $("[data-mentor-bot-parity]")?.addEventListener("click", refreshMentorBotParity);
  $("[data-mentor-last-good-week]")?.addEventListener("click", refreshMentorLastGoodWeekDelta);
  $("[data-mentor-drill-scheduler]")?.addEventListener("click", refreshMentorDrillScheduler);
  $("[data-mentor-drill-scheduler-create]")?.addEventListener("click", createMentorScheduledDrill);
  $("[data-mentor-build-drill]")?.addEventListener("click", buildMentorDrill);
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
  $$("[data-scanner-mode]").forEach((button) => {
    button.addEventListener("click", () => setScannerMode(button.dataset.scannerMode));
  });
  $("[data-scanner-cancel-stale]")?.addEventListener("click", cancelStaleScannerOrders);
  $("[data-scanner-quality]")?.addEventListener("click", () => refreshScannerQuality({ force: true }));
  $("[data-watchlist-quality]")?.addEventListener("click", () => refreshWatchlistQuality({ force: true }));
  $("[data-scanner-quality-notify]")?.addEventListener("click", sendScannerQualityReport);
  $$("[data-watchlist-quality-action]").forEach((button) => {
    button.addEventListener("click", () => applyWatchlistQualityAction(button.dataset.watchlistQualitySymbol || "", button.dataset.watchlistQualityAction || ""));
  });
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
  $$("[data-mentor-trade]").forEach((button) => {
    button.addEventListener("click", () => openMentorTrade(button.dataset.mentorTrade));
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
  Array.from(panelBody.querySelectorAll("[data-pro-console-open]")).forEach((button) => {
    button.addEventListener("click", openProConsole);
  });
  window.lucide?.createIcons();
  updateSovereignChrome({ panel: activePanel, open: panelOpen, state: dashboardState, music: appleMusicState, winston: winstonState });
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

function closePanel(options = {}) {
  panelOpen = false;
  if (options.clearRoom !== false) roomClear = true;
  if (window.matchMedia("(max-width: 760px)").matches && !["desk", "trade"].includes(activeWorkflow)) {
    activeWorkflow = "desk";
    renderMobileViews();
  }
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
  updateWorkflowChrome();
  updateSovereignChrome({ panel: activePanel, open: panelOpen, state: dashboardState, music: appleMusicState, winston: winstonState });
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
  syncRoomTheme(roomTheme);
}

function markTradingViewLoaded(loaded) {
  tradingViewLoaded = loaded;
  screenTerminal.classList.toggle("tradingview-loaded", loaded);
  if (activePanel === "tv") renderPanel();
}

function clearTradingViewContainer(container) {
  if (!container) return;
  container.querySelectorAll("iframe, script").forEach((node) => node.remove());
  container.replaceChildren();
}

function cleanupTradingViewWidgets() {
  clearTimeout(tradingViewTimer);
  clearTimeout(mobileTradingViewTimer);
  clearTimeout(proTradingViewTimer);
  clearTradingViewContainer(tradingViewScreen);
  clearTradingViewContainer(mobileTradingViewScreen);
  clearTradingViewContainer(proTradingViewScreen);
  markTradingViewLoaded(false);
  markMobileTradingViewLoaded(false);
  markProTradingViewLoaded(false);
}

function loadTradingViewWidget() {
  if (!tradingViewScreen) return;
  markTradingViewLoaded(false);
  clearTimeout(tradingViewTimer);
  clearTradingViewContainer(tradingViewScreen);

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

function markMobileTradingViewLoaded(loaded) {
  mobileTradingViewLoaded = loaded;
  mobileTradingViewScreen?.classList.toggle("tradingview-loaded", loaded);
}

function loadMobileTradingViewWidget(force = false) {
  if (!mobileTradingViewScreen || !window.matchMedia("(max-width: 760px)").matches) return;
  if (mobileTradingViewLoaded && !force) return;
  markMobileTradingViewLoaded(false);
  clearTimeout(mobileTradingViewTimer);
  clearTradingViewContainer(mobileTradingViewScreen);

  const containerId = `mobile-tradingview-widget-${Date.now()}`;
  mobileTradingViewScreen.innerHTML = `
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
    hide_top_toolbar: false,
    hide_side_toolbar: true,
    allow_symbol_change: true,
    save_image: false,
    withdateranges: true,
    details: false,
    hotlist: false,
    calendar: false,
    support_host: "https://www.tradingview.com",
  });
  script.onerror = () => markMobileTradingViewLoaded(false);
  mobileTradingViewScreen.querySelector(".tradingview-widget-container")?.append(script);

  let attempts = 0;
  const checkLoaded = () => {
    attempts += 1;
    const iframe = mobileTradingViewScreen.querySelector("iframe");
    if (iframe) {
      markMobileTradingViewLoaded(true);
      return;
    }
    if (attempts < 24 && activeWorkflow === "trade") {
      mobileTradingViewTimer = setTimeout(checkLoaded, 250);
    } else {
      markMobileTradingViewLoaded(false);
    }
  };
  mobileTradingViewTimer = setTimeout(checkLoaded, 450);
}

function setProText(selector, value) {
  const element = $(selector);
  if (element) element.textContent = value;
}

function markProTradingViewLoaded(loaded) {
  proTradingViewLoaded = loaded;
  proTradingViewScreen?.classList.toggle("tradingview-loaded", loaded);
}

function loadProTradingViewWidget() {
  if (!proTradingViewScreen) return;
  markProTradingViewLoaded(false);
  clearTimeout(proTradingViewTimer);
  clearTradingViewContainer(proTradingViewScreen);

  const containerId = `pro-tradingview-widget-${Date.now()}`;
  proTradingViewScreen.innerHTML = `
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
    hide_top_toolbar: false,
    hide_side_toolbar: false,
    allow_symbol_change: true,
    save_image: true,
    withdateranges: true,
    details: false,
    hotlist: false,
    calendar: false,
    support_host: "https://www.tradingview.com",
  });
  script.onerror = () => markProTradingViewLoaded(false);
  proTradingViewScreen.querySelector(".tradingview-widget-container")?.append(script);

  let attempts = 0;
  const checkLoaded = () => {
    attempts += 1;
    const iframe = proTradingViewScreen.querySelector("iframe");
    if (iframe) {
      markProTradingViewLoaded(true);
      return;
    }
    if (attempts < 24 && proConsoleOpen) {
      proTradingViewTimer = setTimeout(checkLoaded, 250);
    } else {
      markProTradingViewLoaded(false);
    }
  };
  proTradingViewTimer = setTimeout(checkLoaded, 450);
}

function renderProConsole() {
  if (!proConsole) return;
  const mode = normalizeTradingMode(tradingModeState.trading_mode);
  const lifecycle = currentLifecycleState();
  const lifecycleSummary = lifecycle.summary || {};
  const readiness = deskReadinessState();
  const disclosure = marketDataDisclosureState();
  const mentor = currentMentorState();
  const latest = latestDecision();
  const recent = (dashboardState.recent_decisions || []).slice(0, 3);
  const openRisk = lifecycle.ok && Number.isFinite(Number(lifecycleSummary.open_risk)) ? Math.max(0, Number(lifecycleSummary.open_risk)) : null;
  const unrealizedSource = lifecycle.ok ? lifecycleSummary.unrealized_pl : dashboardState.ok && !dashboardState.positions_error ? dashboardState.summary?.unrealized_pl : null;
  const unrealized = Number.isFinite(Number(unrealizedSource)) && unrealizedSource !== null ? Number(unrealizedSource) : null;
  const positionsSource = lifecycle.ok ? lifecycleSummary.open_positions : dashboardState.ok && !dashboardState.positions_error ? dashboardState.summary?.open_positions : null;
  const openPositions = Number.isFinite(Number(positionsSource)) && positionsSource !== null ? Number(positionsSource) : null;
  const maxPositions = Number(dashboardState.risk?.max_open_positions || 0);
  const safe = Boolean(
    dashboardState.broker?.ok &&
      dashboardState.paper_endpoint &&
      lifecycle.ok &&
      Number(lifecycleSummary.guardrails || 0) === 0 &&
      openPositions !== null &&
      (!maxPositions || openPositions < maxPositions),
  );
  const health = currentHealthState();

  setProText("#pro-mode", String(TRADING_MODE_LABELS[mode] || "Both").toUpperCase());
  setProText("#pro-execution", dashboardState.execution_armed ? (dashboardState.paper_endpoint ? "PAPER EXECUTION ARMED" : "EXECUTION ARMED") : "PROPOSAL MODE");
  setProText("#pro-broker", dashboardState.paper_endpoint ? "ALPACA PAPER" : dashboardState.broker?.ok ? "BROKER CONNECTED" : "BROKER CHECK");
  setProText("#pro-data-status", disclosure.live ? "LIVE DATA VERIFIED" : "DATA UNVERIFIED");
  setProText("#pro-chart-symbol", `${tradingViewLabel()} · 5 MIN`);
  setProText("#pro-readiness-label", readiness.label);
  setProText("#pro-readiness-score", readiness.score);
  setProText("#pro-mentor-note", mentor.recommendation?.instruction || "Open Coach for evidence-backed setup reasoning.");
  setProText("#pro-plan-title", latest ? [latest.symbol, latest.play].filter(Boolean).join(" · ") || "Latest decision" : "No setup selected");
  setProText("#pro-review-state", latest?.status ? String(latest.status).replaceAll("_", " ").toUpperCase() : "REVIEW REQUIRED");
  setProText("#pro-risk-label", safe ? "Within configured limits" : "Review desk controls");
  setProText("#pro-safe-state", safe ? "SAFE" : "CHECKING");
  setProText("#pro-open-risk", openRisk === null ? "Unavailable" : money(openRisk));
  setProText("#pro-unrealized-pl", unrealized === null ? "Unavailable" : `${unrealized > 0 ? "+" : ""}${money(unrealized)}`);
  setProText("#pro-open-positions", openPositions === null ? "Unknown" : `${openPositions} / ${maxPositions || "--"}`);
  setProText("#pro-approval", dashboardState.guardrails?.approval_required == null ? "Unknown" : dashboardState.guardrails.approval_required ? "Required" : "Guarded");
  setProText("#pro-paper-lock", dashboardState.paper_endpoint == null ? "Unknown" : dashboardState.paper_endpoint ? "Confirmed" : "Not verified");

  const disclosureElement = $("#pro-console-disclosure");
  disclosureElement?.classList.toggle("good", disclosure.live);
  setProText("#pro-disclosure-title", disclosure.title);
  setProText("#pro-disclosure-detail", disclosure.detail);

  const factors = readiness.components?.length
    ? readiness.components.map((item) => ({ label: item.label, value: item.score, reason: item.reason }))
    : [{ label: "Trade evidence", value: null, reason: "Unavailable" }];
  const factorList = $("#pro-factor-list");
  if (factorList) {
    factorList.innerHTML = factors
      .map(
        (factor) => `
          <div class="pro-factor">
            <span>${escapeHtml(factor.label)}</span>
            <div><i class="${factor.value == null || factor.value < 80 ? "warn" : ""}" style="width:${Number(factor.value || 0)}%"></i></div>
            <strong title="${escapeHtml(factor.reason || "")}">${factor.value == null ? "Unknown" : `${factor.value}%`}</strong>
          </div>
        `,
      )
      .join("");
  }

  const opportunityList = $("#pro-opportunity-list");
  if (opportunityList) {
    opportunityList.innerHTML = recent.length
      ? recent
          .map((decision) => {
            const title = [decision.symbol, decision.play].filter(Boolean).join(" · ") || "Screened setup";
            const status = String(decision.status || "seen").replaceAll("_", " ");
            return `
              <div class="pro-opportunity">
                <strong>${escapeHtml(title)}</strong>
                <span>${escapeHtml(decision.reason || "Awaiting qualification details")}</span>
                <small>${escapeHtml(timeAgo(decision.timestamp))}</small>
                <em>${escapeHtml(status)}</em>
              </div>
            `;
          })
          .join("")
      : `<div class="pro-opportunity"><strong>No screened setup yet</strong><span>The bot decision queue will appear here.</span><em>WAITING</em></div>`;
  }

  const planValues = $("#pro-plan-values");
  if (planValues) {
    const calculated = plannerState?.plan || {};
    const calculatedRisk = plannerState?.risk || {};
    const target = calculated.target_two ?? latest?.target_price ?? latest?.take_profit_price ?? latest?.take_profit;
    const values = [
      ["ENTRY", calculated.planned_entry ?? latest?.entry_price],
      ["STOP", calculated.stop ?? latest?.stop_price],
      ["TARGET", target],
      ["SIZE EST.", calculatedRisk.calculated_position_size ?? latest?.qty],
    ];
    planValues.innerHTML = values
      .map(([label, value]) => `<div class="pro-plan-value"><small>${label}</small><strong>${escapeHtml(value ?? "—")}</strong></div>`)
      .join("");
  }

  const annotationList = $("#pro-annotation-list");
  if (annotationList) {
    const levels = annotationsState?.levels || [];
    annotationList.innerHTML = levels.length
      ? `<small>VERIFIED ADJACENT LEVELS · ${escapeHtml(timeAgo(annotationsState.timestamp))}</small>${levels.map((item) => `<p><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.price)}</strong></p>`).join("")}${annotationsState.tradingview_url ? `<a href="${escapeHtml(annotationsState.tradingview_url)}" target="_blank" rel="noopener noreferrer">Open synchronized TradingView link</a>` : ""}`
      : `<small>VERIFIED ADJACENT LEVELS</small><p><span>Entry, stop, targets</span><strong>Unavailable</strong></p>`;
  }

  const score = $("#pro-readiness-score");
  if (score) score.style.borderColor = readiness.score >= 80 ? "rgba(104, 199, 131, 0.82)" : "rgba(226, 170, 75, 0.82)";
  $("#pro-safe-state")?.classList.toggle("safe", safe);
  const pnl = $("#pro-unrealized-pl");
  pnl?.classList.toggle("positive", unrealized > 0);
  pnl?.classList.toggle("negative", unrealized < 0);
  $$('[data-pro-symbol]').forEach((button) => button.classList.toggle("active", button.dataset.proSymbol === tradingViewSymbol));
  window.lucide?.createIcons();
}

async function openProConsole() {
  if (!proConsole) return;
  try {
    await dashboardJson("/api/pro/bootstrap");
  } catch (error) {
    announceDesk(error.status === 403 ? "Pro Console is not included in this account tier." : `Pro Console unavailable: ${error.message}`);
    return;
  }
  proConsoleOpen = true;
  document.body.classList.add("pro-console-open");
  proConsole.setAttribute("aria-hidden", "false");
  renderProConsole();
  if (!proTradingViewLoaded) loadProTradingViewWidget();
  proConsoleClose?.focus();
}

function closeProConsole() {
  if (!proConsole) return;
  proConsoleOpen = false;
  document.body.classList.remove("pro-console-open");
  proConsole.setAttribute("aria-hidden", "true");
  clearTimeout(proTradingViewTimer);
  clearTradingViewContainer(proTradingViewScreen);
  markProTradingViewLoaded(false);
}

function setTradingViewSymbol(symbol) {
  if (!tradingViewSymbols.some((item) => item.symbol === symbol)) return;
  tradingViewSymbol = symbol;
  localStorage.setItem("velez-tv-symbol", tradingViewSymbol);
  loadTradingViewWidget();
  renderMobileViews();
  if (activeWorkflow === "trade" && window.matchMedia("(max-width: 760px)").matches) {
    loadMobileTradingViewWidget(true);
  }
  if (proConsoleOpen) {
    renderProConsole();
    loadProTradingViewWidget();
  }
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

async function refreshTradingMode(options = {}) {
  const force = Boolean(options.force);
  if (tradingModeRefreshPromise) return tradingModeRefreshPromise;
  if (!force && tradingModeState.ok && Date.now() - new Date(tradingModeState.timestamp || 0).getTime() < 30000) {
    renderTradingModeControl();
    return tradingModeState;
  }

  tradingModeRefreshPromise = fetch("/api/settings/trading-mode", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      tradingModeState = {
        ok: !payload.error,
        trading_mode: normalizeTradingMode(payload.trading_mode),
        saving: false,
        error: payload.error || null,
        timestamp: new Date().toISOString(),
      };
      renderTradingModeControl();
      return tradingModeState;
    })
    .catch((error) => {
      tradingModeState = {
        ...tradingModeState,
        ok: false,
        saving: false,
        error: error.message,
        timestamp: new Date().toISOString(),
      };
      renderTradingModeControl();
      return tradingModeState;
    })
    .finally(() => {
      tradingModeRefreshPromise = null;
    });

  renderTradingModeControl();
  return tradingModeRefreshPromise;
}

async function setTradingMode(mode) {
  const previousMode = normalizeTradingMode(tradingModeState.trading_mode);
  const nextMode = normalizeTradingMode(mode);
  tradingModeState = {
    ...tradingModeState,
    trading_mode: nextMode,
    saving: true,
    error: null,
  };
  renderTradingModeControl();

  try {
    const response = await fetch("/api/settings/trading-mode", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trading_mode: nextMode }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.error || payload.ok === false) {
      throw new Error(payload.detail || payload.error || `status ${response.status}`);
    }
    tradingModeState = {
      ok: true,
      trading_mode: normalizeTradingMode(payload.trading_mode),
      saving: false,
      error: null,
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    tradingModeState = {
      ...tradingModeState,
      trading_mode: previousMode,
      ok: false,
      saving: false,
      error: error.message,
      timestamp: new Date().toISOString(),
    };
  }

  renderTradingModeControl();
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

async function moveBreakevenStops() {
  if (!approvalToken) {
    winstonTranscript("system", "Breakeven stop move blocked: approval token required.");
    return;
  }
  try {
    const response = await fetch("/api/lifecycle/actions/breakeven", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_token: approvalToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `breakeven move failed (${response.status})`);
    lifecycleState = data.lifecycle || lifecycleState;
    dashboardState.lifecycle = lifecycleState;
    renderPanel();
    winstonTranscript("system", `Breakeven stop review complete: moved ${data.moved_count || 0} stop(s).`);
  } catch (error) {
    winstonTranscript("system", `Breakeven stop move blocked: ${error?.message || "unknown error"}.`);
  }
}

async function planLifecyclePartials() {
  try {
    const response = await fetch("/api/lifecycle/partials/plan", { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `partial plan failed (${response.status})`);
    lifecycleState = { ...currentLifecycleState(), partial_plans: data.plans || [], timestamp: data.timestamp || new Date().toISOString() };
    dashboardState.lifecycle = lifecycleState;
    renderPanel();
    winstonTranscript("system", `Partial planner loaded ${data.plans?.length || 0} position plan(s).`);
  } catch (error) {
    winstonTranscript("system", `Partial planner blocked: ${error?.message || "unknown error"}.`);
  }
}

async function refreshPositionDoctor() {
  try {
    const response = await fetch("/api/lifecycle/doctor", { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `position doctor failed (${response.status})`);
    lifecycleState = { ...currentLifecycleState(), doctor_positions: data.positions || [], reduction_plan: data.reduction_plan || currentLifecycleState().reduction_plan, scanner_reopen: data.scanner_reopen || currentLifecycleState().scanner_reopen, summary: data.summary || currentLifecycleState().summary, timestamp: data.timestamp || new Date().toISOString() };
    dashboardState.lifecycle = lifecycleState;
    renderPanel();
    winstonTranscript("system", `Position Doctor loaded ${data.positions?.length || 0} position(s).`);
  } catch (error) {
    winstonTranscript("system", `Position Doctor blocked: ${error?.message || "unknown error"}.`);
  }
}

async function refreshReductionPlan() {
  try {
    const response = await fetch("/api/lifecycle/reduction/plan", { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `reduction plan failed (${response.status})`);
    lifecycleState = { ...currentLifecycleState(), reduction_plan: data.plan || {}, scanner_reopen: data.scanner_reopen || {}, timestamp: data.timestamp || new Date().toISOString() };
    dashboardState.lifecycle = lifecycleState;
    renderPanel();
    winstonTranscript("system", `Reduction plan loaded ${data.plan?.suggestions?.length || 0} suggestion(s).`);
  } catch (error) {
    winstonTranscript("system", `Reduction plan blocked: ${error?.message || "unknown error"}.`);
  }
}

async function autoClaimLifecyclePositions() {
  if (!approvalToken) {
    winstonTranscript("system", "Auto-claim blocked: approval token required.");
    return;
  }
  try {
    const response = await fetch("/api/lifecycle/actions/auto-claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_token: approvalToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `auto-claim failed (${response.status})`);
    lifecycleState = data.lifecycle || lifecycleState;
    dashboardState.lifecycle = lifecycleState;
    renderPanel();
    winstonTranscript("system", `Auto-claim complete: claimed ${data.claimed_count || 0} position(s).`);
  } catch (error) {
    winstonTranscript("system", `Auto-claim blocked: ${error?.message || "unknown error"}.`);
  }
}

async function claimLifecyclePosition(symbol, alertRef) {
  if (!approvalToken) {
    winstonTranscript("system", "Position claim blocked: approval token required.");
    return;
  }
  try {
    const response = await fetch("/api/lifecycle/actions/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, alert_ref: alertRef, approval_token: approvalToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `claim failed (${response.status})`);
    lifecycleState = data.lifecycle || lifecycleState;
    dashboardState.lifecycle = lifecycleState;
    renderPanel();
    winstonTranscript("system", `${symbol} claimed to journal ${data.claim?.alert_ref || alertRef}.`);
  } catch (error) {
    winstonTranscript("system", `Position claim blocked: ${error?.message || "unknown error"}.`);
  }
}

async function reduceLifecyclePosition(symbol, fraction) {
  if (!approvalToken) {
    winstonTranscript("system", "Exposure reduction blocked: approval token required.");
    return;
  }
  try {
    const response = await fetch("/api/lifecycle/actions/reduce", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, fraction, approval_token: approvalToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `reduction failed (${response.status})`);
    lifecycleState = data.verification?.lifecycle || lifecycleState;
    if (lifecycleState && data.verification?.scanner_reopen) lifecycleState.scanner_reopen = data.verification.scanner_reopen;
    dashboardState.lifecycle = lifecycleState;
    dashboardState.scanner = data.verification?.scanner || dashboardState.scanner;
    renderPanel();
    winstonTranscript("system", `${symbol} ${Math.round(Number(fraction) * 100)}% exposure reduction submitted; verification refreshed.`);
  } catch (error) {
    winstonTranscript("system", `${symbol} exposure reduction blocked: ${error?.message || "unknown error"}.`);
  }
}

async function repairLifecycleStop(symbol) {
  if (!approvalToken) {
    winstonTranscript("system", "Stop repair blocked: approval token required.");
    return;
  }
  try {
    const response = await fetch("/api/lifecycle/actions/repair-stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, approval_token: approvalToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `stop repair failed (${response.status})`);
    lifecycleState = data.lifecycle || lifecycleState;
    dashboardState.lifecycle = lifecycleState;
    renderPanel();
    winstonTranscript("system", `${symbol} stop repair ${data.status || "complete"}.`);
  } catch (error) {
    winstonTranscript("system", `${symbol} stop repair blocked: ${error?.message || "unknown error"}.`);
  }
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

async function refreshMentor(options = {}) {
  const force = Boolean(options.force);
  const scope = options.scope || currentMentorState().scope || "weekly";
  const alertRef = options.alertRef || "";
  if (mentorRefreshPromise) {
    if (!force) return mentorRefreshPromise;
    await mentorRefreshPromise;
    return refreshMentor(options);
  }
  const fetchedAt = mentorState?.timestamp ? new Date(mentorState.timestamp).getTime() : 0;
  if (!force && mentorState?.ok && mentorState.scope === scope && Date.now() - fetchedAt < 60000) return mentorState;
  const endpoint = scope === "trade" && alertRef
    ? `/api/mentor/trade/${encodeURIComponent(alertRef)}`
    : scope === "today"
      ? "/api/mentor/today"
      : "/api/mentor/weekly?days=7";
  mentorRefreshPromise = fetch(endpoint, { cache: "no-store" })
    .then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.ok) throw new Error(payload.reason || `mentor status ${response.status}`);
      mentorState = payload;
      return payload;
    })
    .catch((error) => {
      mentorState = { ...currentMentorState(), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return mentorState;
    })
    .finally(() => {
      mentorRefreshPromise = null;
      if (activePanel === "mentor") renderPanelIfIdle();
    });
  if (activePanel === "mentor") renderPanelIfIdle();
  return mentorRefreshPromise;
}

async function askMentor(event) {
  event?.preventDefault?.();
  const input = $("#mentor-question");
  const question = (input?.value || "").trim();
  if (!question) return;
  if (/\b(setup|chart|tradingview|trading view|entry candle|what do you see|eyes on)\b/i.test(question)) {
    await observeMentorChart(question);
    if (input) input.value = "";
    return;
  }
  mentorAskState = { loading: true, reply: "Velez Mentor is reviewing the evidence..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        scope: currentMentorState().scope || "weekly",
        alert_ref: currentMentorState().trade?.alert_ref || "",
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `mentor request failed (${response.status})`);
    mentorAskState = { loading: false, ...payload };
    if (payload.report) mentorState = payload.report;
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Velez Mentor request failed." };
  }
  renderPanel();
}

async function observeMentorChart(question = "What setup is visible on this TradingView chart?") {
  mentorAskState = { loading: true, reply: "Velez Mentor is putting eyes on the TradingView screen..." };
  renderPanel();
  const latestCapture = chartCaptures[0] || {};
  try {
    const response = await fetch("/api/mentor/chart/observe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        symbol: tradingViewBrokerSymbol(),
        timeframe: "5Min",
        screenshot: latestCapture.dataUrl || "",
        notes: latestCapture?.timestamp ? `Latest browser capture ${latestCapture.timestamp}` : "",
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `chart observation failed (${response.status})`);
    mentorEyesState = payload;
    mentorAskState = { loading: false, ...payload };
    if (payload.report) mentorState = payload.report;
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Mentor chart observation failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function checkMentorSourceHealth() {
  mentorAskState = { loading: true, reply: "Velez Mentor is checking chart source health..." };
  renderPanel();
  try {
    const response = await fetch(`/api/mentor/chart/source-health?symbol=${encodeURIComponent(tradingViewBrokerSymbol())}&timeframe=5Min`, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `source health failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, sourceHealth: payload };
    mentorAskState = { loading: false, reply: payload.health?.readback || "Chart source health checked." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Chart source health failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function checkMentorTradierDiagnostics() {
  mentorAskState = { loading: true, reply: "Velez Mentor is checking Tradier without exposing credentials..." };
  renderPanel();
  try {
    const response = await fetch(`/api/mentor/tradier/diagnostics?symbol=${encodeURIComponent(tradingViewBrokerSymbol())}&timeframe=5Min`, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `tradier diagnostics failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, tradier: payload };
    mentorAskState = { loading: false, reply: payload.readback || "Tradier diagnostics checked." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Tradier diagnostics failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function startMentorSetupWatch() {
  mentorAskState = { loading: true, reply: "Velez Mentor is starting Setup Watch..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/setup-watch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: tradingViewBrokerSymbol(),
        timeframe: "5Min",
        question: "Watch this chart for a clean Velez setup.",
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `setup watch failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, setupWatch: payload };
    mentorEyesState = { ...(mentorEyesState || {}), chart_observation: payload.chart_observation, reply: payload.watch?.readback };
    mentorAskState = { loading: false, reply: payload.watch?.readback || "Setup Watch started." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Setup Watch failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorNoTradeCoach() {
  mentorAskState = { loading: true, reply: "Velez Mentor is reviewing no-trade decisions..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/no-trade?limit=120", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `no-trade coach failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, noTrade: payload };
    mentorAskState = { loading: false, reply: payload.coach?.question || payload.coach?.readback || "No-trade coach refreshed." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "No-trade coach failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function backfillMentorAutopsies() {
  mentorAskState = { loading: true, reply: "Velez Mentor is backfilling missing closed-trade autopsies..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/autopsies/backfill?limit=100", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `autopsy backfill failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, autopsyBackfill: payload };
    mentorAskState = { loading: false, reply: payload.readback || "Autopsy backfill checked." };
    await refreshMentor({ force: true, scope: currentMentorState().scope || "weekly" });
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Autopsy backfill failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorPnlAttribution() {
  mentorAskState = { loading: true, reply: "Velez Mentor is attributing P/L by cause..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/pnl-attribution?days=30&limit=200", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `P/L attribution failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, pnlAttribution: payload };
    mentorAskState = { loading: false, reply: payload.attribution?.readback || "P/L attribution complete." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "P/L attribution failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorStrategyDrift() {
  mentorAskState = { loading: true, reply: "Velez Mentor is checking strategy drift..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/strategy-drift?recent_days=30&baseline_days=60", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `strategy drift failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, strategyDrift: payload };
    mentorAskState = { loading: false, reply: payload.drift?.readback || "Strategy drift check complete." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Strategy drift failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorRegimeCatalyst() {
  mentorAskState = { loading: true, reply: "Velez Mentor is checking regime and catalysts..." };
  renderPanel();
  try {
    const response = await fetch(`/api/mentor/regime-catalyst?symbol=${encodeURIComponent(tradingViewBrokerSymbol())}&timeframe=5Min`, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `regime/catalyst check failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, regimeCatalyst: payload };
    mentorAskState = { loading: false, reply: payload.guardrail?.readback || "Regime/catalyst guardrail checked." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Regime/catalyst check failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorCrossBotRisk() {
  mentorAskState = { loading: true, reply: "Velez Mentor is mirroring cross-bot exposure..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/cross-bot-risk", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `cross-bot risk failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, crossBotRisk: payload };
    mentorAskState = { loading: false, reply: payload.mirror?.readback || "Cross-bot risk mirror checked." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Cross-bot risk mirror failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorReplayLab() {
  const alertRef = currentMentorState().trade?.alert_ref || latestDecision()?.alert_ref || "";
  const symbol = latestDecision()?.symbol || tradingViewBrokerSymbol();
  mentorAskState = { loading: true, reply: "Velez Mentor is replaying the trade candle by candle..." };
  renderPanel();
  try {
    const query = alertRef ? `alert_ref=${encodeURIComponent(alertRef)}` : `symbol=${encodeURIComponent(symbol)}`;
    const response = await fetch(`/api/mentor/replay-lab?${query}`, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `replay lab failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, replayLab: payload };
    mentorAskState = { loading: false, reply: payload.lab?.readback || "Replay Lab complete." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Replay Lab failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorDailyRootCause() {
  mentorAskState = { loading: true, reply: "Velez Mentor is finding today's highest-probability root cause..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/daily-root-cause", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `root-cause brief failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, dailyRootCause: payload };
    mentorAskState = { loading: false, reply: payload.brief?.readback || "Daily Root-Cause Brief complete." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Daily Root-Cause Brief failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorTradeQualityHeatmap() {
  mentorAskState = { loading: true, reply: "Velez Mentor is grading symbol/setup quality..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/trade-quality-heatmap?days=90", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `trade heatmap failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, tradeQualityHeatmap: payload };
    mentorAskState = { loading: false, reply: payload.heatmap?.readback || "Trade Quality Heatmap complete." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Trade Quality Heatmap failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorGuardrailReport() {
  mentorAskState = { loading: true, reply: "Velez Mentor is reviewing do-not-touch guardrails without changing settings..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/guardrail-do-not-touch", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `guardrail report failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, guardrailReport: payload };
    mentorAskState = { loading: false, reply: payload.report?.readback || "Do-not-touch guardrail report complete." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Do-not-touch guardrail report failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorBrokerReconciliation() {
  mentorAskState = { loading: true, reply: "Velez Mentor is scoring broker/data reconciliation without taking broker actions..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/broker-reconciliation", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `reconciliation score failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, brokerReconciliation: payload };
    mentorAskState = { loading: false, reply: payload.score?.readback || "Broker/Data Reconciliation score complete." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Broker/Data Reconciliation failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorBotParity() {
  mentorAskState = { loading: true, reply: "Velez Mentor is comparing bot parity evidence..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/bot-parity", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `bot parity failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, botParity: payload };
    mentorAskState = { loading: false, reply: payload.matrix?.readback || "Bot-to-Bot Parity Matrix complete." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Bot-to-Bot Parity Matrix failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorLastGoodWeekDelta() {
  mentorAskState = { loading: true, reply: "Velez Mentor is comparing this week to the last good week..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/last-good-week-delta?lookback_days=180", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `last-good-week report failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, lastGoodWeekDelta: payload };
    mentorAskState = { loading: false, reply: payload.delta?.readback || "What Changed report complete." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "What Changed report failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function refreshMentorDrillScheduler() {
  mentorAskState = { loading: true, reply: "Velez Mentor is planning the next daily drill..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/drill-scheduler", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `drill scheduler failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, drillScheduler: payload };
    mentorAskState = { loading: false, reply: payload.scheduler?.readback || "Mentor Drill Scheduler refreshed." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Mentor Drill Scheduler failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function createMentorScheduledDrill() {
  mentorAskState = { loading: true, reply: "Velez Mentor is creating the scheduled daily drill..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/drill-scheduler", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `scheduled drill create failed (${response.status})`);
    mentorOpsState = { ...mentorOpsState, drillScheduler: payload };
    mentorState = {
      ...currentMentorState(),
      active_drills: payload.scheduler?.active_drills || currentMentorState().active_drills || [],
    };
    mentorAskState = { loading: false, reply: payload.scheduler?.readback || "Scheduled Mentor drill created." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Scheduled Mentor drill failed." };
  }
  if (activePanel !== "mentor") setActivePanel("mentor");
  renderPanel();
}

async function buildMentorDrill() {
  mentorAskState = { loading: true, reply: "Velez Mentor is building the next drill..." };
  renderPanel();
  try {
    const response = await fetch("/api/mentor/drills/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scope: currentMentorState().scope || "weekly",
        dimension: currentMentorState().recommendation?.dimension || "",
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `drill build failed (${response.status})`);
    mentorState = {
      ...(payload.report || currentMentorState()),
      active_drills: payload.active_drills || payload.report?.active_drills || currentMentorState().active_drills || [],
    };
    mentorAskState = { loading: false, reply: `Drill built: ${payload.drill?.title || "next Mentor drill"}.` };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Mentor drill build failed." };
  }
  renderPanel();
}

async function saveMentorProfile(event) {
  event?.preventDefault?.();
  const goals = ($("#mentor-goals")?.value || "")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
  try {
    const response = await fetch("/api/mentor/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        experience_level: $("#mentor-experience")?.value || "developing",
        primary_mode: $("#mentor-mode")?.value || "auto",
        coaching_style: $("#mentor-style")?.value || "concise",
        goals,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `profile update failed (${response.status})`);
    mentorState = payload.report || mentorState;
    mentorAskState = { loading: false, reply: "Coaching profile saved locally. The scorecard has been recomputed." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Mentor profile update failed." };
  }
  renderPanel();
}

async function updateMentorDrill(drillId, status) {
  if (!drillId) return;
  try {
    const response = await fetch(`/api/mentor/drills/${encodeURIComponent(drillId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `drill update failed (${response.status})`);
    mentorState = { ...currentMentorState(), active_drills: payload.active_drills || [] };
    mentorAskState = { loading: false, reply: status === "completed" ? "Drill completed and saved to mentor memory." : "Drill dismissed." };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Drill update failed." };
  }
  renderPanel();
}

async function sendMentorBriefing(kind) {
  mentorAskState = { loading: true, reply: `Velez Mentor is preparing the ${kind} voice memo...` };
  renderPanel();
  try {
    const response = await fetch(`/api/mentor/briefings/${encodeURIComponent(kind)}/telegram?force=true`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.reason || `voice briefing failed (${response.status})`);
    mentorAskState = {
      loading: false,
      reply: `${kind === "morning" ? "Morning" : "Closing"} voice memo sent to ${payload.delivered || 1} Telegram destination.`,
    };
  } catch (error) {
    mentorAskState = { loading: false, reply: error?.message || "Mentor voice briefing failed." };
  }
  renderPanel();
}

function openMentorTrade(alertRef) {
  if (!alertRef) return;
  setActivePanel("mentor");
  refreshMentor({ force: true, scope: "trade", alertRef });
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

async function setScannerMode(mode) {
  if (!approvalToken) {
    winstonTranscript("system", "Scanner mode change blocked: approval token required.");
    return;
  }
  try {
    const response = await fetch("/api/scanner/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, approval_token: approvalToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `scanner mode failed (${response.status})`);
    dashboardState.scanner = data.scanner || dashboardState.scanner;
    renderPanel();
    winstonTranscript("system", `Scanner mode set to ${data.mode || mode}.`);
  } catch (error) {
    winstonTranscript("system", `Scanner mode blocked: ${error?.message || "unknown error"}.`);
  }
}

async function cancelStaleScannerOrders() {
  if (!approvalToken) {
    winstonTranscript("system", "Stale-order cleanup blocked: approval token required.");
    return;
  }
  try {
    const response = await fetch("/api/scanner/orders/cancel-stale", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_token: approvalToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `stale-order cleanup failed (${response.status})`);
    dashboardState.scanner = data.scanner || dashboardState.scanner;
    renderPanel();
    winstonTranscript("system", data.message || `Canceled ${data.canceled_count || 0} stale scanner orders.`);
  } catch (error) {
    winstonTranscript("system", `Stale-order cleanup blocked: ${error?.message || "unknown error"}.`);
  }
}

async function refreshScannerQuality(options = {}) {
  const force = Boolean(options.force);
  if (scannerQualityRefreshPromise) return scannerQualityRefreshPromise;
  if (!force && scannerQualityState?.ok && Date.now() - new Date(scannerQualityState.timestamp || 0).getTime() < 60000) return scannerQualityState;
  scannerQualityRefreshPromise = fetch("/api/scanner/quality?limit=80", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      scannerQualityState = payload;
      dashboardState.scanner = { ...(dashboardState.scanner || {}), quality: payload };
      return payload;
    })
    .catch((error) => {
      scannerQualityState = { ...(scannerQualityState || {}), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return scannerQualityState;
    })
    .finally(() => {
      scannerQualityRefreshPromise = null;
      if (activePanel === "laptop") renderPanelIfIdle();
    });
  if (activePanel === "laptop") renderPanelIfIdle();
  return scannerQualityRefreshPromise;
}

async function refreshWatchlistQuality(options = {}) {
  const force = Boolean(options.force);
  if (watchlistQualityRefreshPromise) return watchlistQualityRefreshPromise;
  if (!force && watchlistQualityState?.ok && Date.now() - new Date(watchlistQualityState.timestamp || 0).getTime() < 60000) return watchlistQualityState;
  watchlistQualityRefreshPromise = fetch("/api/watchlist/quality", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`status ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      watchlistQualityState = payload;
      dashboardState.symbols = payload.symbols || dashboardState.symbols;
      return payload;
    })
    .catch((error) => {
      watchlistQualityState = { ...(watchlistQualityState || {}), ok: false, error: error.message, timestamp: new Date().toISOString() };
      return watchlistQualityState;
    })
    .finally(() => {
      watchlistQualityRefreshPromise = null;
      if (activePanel === "laptop") renderPanelIfIdle();
    });
  if (activePanel === "laptop") renderPanelIfIdle();
  return watchlistQualityRefreshPromise;
}

async function applyWatchlistQualityAction(symbol, action) {
  if (!approvalToken) {
    winstonTranscript("system", "Watchlist quality action blocked: approval token required.");
    return;
  }
  try {
    const response = await fetch("/api/watchlist/quality/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, action, approval_token: approvalToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `watchlist quality action failed (${response.status})`);
    watchlistQualityState = data.watchlist_quality || watchlistQualityState;
    dashboardState.symbols = watchlistQualityState?.symbols || dashboardState.symbols;
    dashboardState.scanner = data.scanner || dashboardState.scanner;
    renderPanel();
    winstonTranscript("system", `${symbol} lane marked ${data.action || action}.`);
  } catch (error) {
    winstonTranscript("system", `${symbol} quality action blocked: ${error?.message || "unknown error"}.`);
  }
}

async function sendScannerQualityReport() {
  if (!approvalToken) {
    winstonTranscript("system", "Scanner quality report blocked: approval token required.");
    return;
  }
  try {
    const response = await fetch("/api/scanner/quality/notify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_token: approvalToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.reason || `quality report failed (${response.status})`);
    scannerQualityState = data.quality || scannerQualityState;
    renderPanel();
    winstonTranscript("system", data.message || "Scanner quality report sent.");
  } catch (error) {
    winstonTranscript("system", `Scanner quality report blocked: ${error?.message || "unknown error"}.`);
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
  roomClear = false;
  activePanel = panel;
  if (["research","performance"].includes(panel)) deskRecords.load(panel);
  if (options.syncWorkflow !== false) {
    activeWorkflow = panelWorkflow(panel);
  }
  renderPanel();
  // The panel body is reused between views. Reset both possible scrollers so a
  // newly selected view never starts with its opening cards under the heading.
  if (detailPanel) detailPanel.scrollTop = 0;
  if (panelBody) panelBody.scrollTop = 0;
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
  if (panel === "mentor") {
    refreshMentor();
  }
  if (["laptop", "journal", "mentor", "drawer", "bookshelf", "notes"].includes(panel)) {
    refreshDecisionIntelligence();
  }
  if (panel === "journal") refreshStructuredReview();
  if (panel === "notes") refreshSymbolNote();
}

async function refreshState() {
  if (dashboardDestroyed) return;
  dashboardRefreshController?.abort();
  const controller = new AbortController();
  dashboardRefreshController = controller;
  try {
    const response = await fetch("/api/dashboard/state", { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Error(`status ${response.status}`);
    dashboardState = await response.json();
  } catch (error) {
    if (error?.name === "AbortError") return;
    dashboardState = {
      ...dashboardState,
      ok: false,
      broker: { ...dashboardState.broker, ok: false, reason: "dashboard_api_unreachable" },
      timestamp: new Date().toISOString(),
    };
  } finally {
    if (dashboardRefreshController === controller) dashboardRefreshController = null;
  }
  if (dashboardState.apple_music?.configured) {
    prepareAppleMusic();
  }
  if (dashboardState.winston) {
    applyWinstonRuntime(dashboardState.winston);
  }
  refreshTradingMode();
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
  if (activePanel === "mentor") {
    refreshMentor();
  }
  refreshDecisionIntelligence();
  renderStatus();
  if (!activePanelIsMusic() && activePanel !== "phone") {
    renderPanelIfIdle();
  }
  updateActiveChrome();
}

function scheduleDashboardRefresh(delay = 10000) {
  clearTimeout(dashboardRefreshTimer);
  if (dashboardDestroyed || document.hidden) return;
  dashboardRefreshTimer = setTimeout(async () => {
    await refreshState();
    scheduleDashboardRefresh();
  }, delay);
}

function handleDashboardVisibility() {
  if (document.hidden) {
    clearTimeout(dashboardRefreshTimer);
    dashboardRefreshController?.abort();
    return;
  }
  refreshState().finally(() => scheduleDashboardRefresh());
}

function roomRect() {
  return sovereignRoomRect();
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
    const region = hotspotDefinitions.find((item) => item.id === hotspot.dataset.objectId);
    if (region) applyRegion(hotspot, region, rect);
  });
  const expanded = document.body.classList.contains("sovereign-chart-expanded");
  if (!expanded) applyRegion(screenTerminal, sovereignRegions().screen, rect);
  screenTerminal.hidden = window.innerWidth < 720 && !expanded;
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
  hotspotDefinitions.splice(0, hotspotDefinitions.length, ...getSovereignHotspots());
  roomHotspots.innerHTML = "";
  hotspotDefinitions.forEach((definition) => {
    const button = document.createElement("button");
    button.className = `room-hotspot${["phone", "music", "journal"].includes(definition.id) ? " sovereign-prop" : ""}`;
    button.dataset.objectId = definition.id;
    button.type = "button";
    button.dataset.panel = definition.panel;
    button.dataset.label = definition.label;
    button.setAttribute("aria-label", definition.label);
    button.title = definition.label;
    button.innerHTML = sovereignObjectMarkup(definition);
    button.addEventListener("click", () => window.__sovereign ? window.__sovereign.open(definition.panel) : setActivePanel(definition.panel));
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

$$("[data-workflow]").forEach((button) => {
  button.addEventListener("click", () => setActiveWorkflow(button.dataset.workflow));
});

$$("[data-panel-shortcut]").forEach((button) => {
  button.addEventListener("click", () => {
    if (proConsoleOpen) closeProConsole();
    if (button.dataset.panelShortcut === "tv" && window.matchMedia("(max-width: 760px)").matches) {
      setActiveWorkflow("trade");
      return;
    }
    setActivePanel(button.dataset.panelShortcut);
  });
});

$$('[data-pro-symbol]').forEach((button) => {
  button.addEventListener("click", () => setTradingViewSymbol(button.dataset.proSymbol));
});

$$('[data-mobile-symbol]').forEach((button) => {
  button.addEventListener("click", () => setTradingViewSymbol(button.dataset.mobileSymbol));
});

$('[data-mobile-pro-console-open]')?.addEventListener("click", openProConsole);

$("#room-shortcut-more")?.addEventListener("click", () => {
  document.body.classList.toggle("nav-peek");
});

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
proConsoleClose?.addEventListener("click", closeProConsole);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (proConsoleOpen) {
      closeProConsole();
      return;
    }
    closePanel();
    document.body.classList.remove("nav-peek");
  }
});

screenTerminal.addEventListener("click", (event) => { if (event.target === screenTerminal) setActivePanel("tv"); });
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

tradingModeSelect?.addEventListener("change", (event) => {
  setTradingMode(event.target.value);
});

function init() {
  buildHotspots();
  window.addEventListener("load", () => window.lucide?.createIcons());
  window.addEventListener("resize", () => {
    positionRoomElements();
    renderMobileViews();
    if (activeWorkflow === "trade") loadMobileTradingViewWidget();
  });
  document.addEventListener("visibilitychange", handleDashboardVisibility);
  window.addEventListener("beforeunload", () => {
    dashboardDestroyed = true;
    clearTimeout(dashboardRefreshTimer);
    dashboardRefreshController?.abort();
    cleanupTradingViewWidgets();
  });
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
    refreshTradingMode,
    setTradingMode,
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
    openProConsole,
    closeProConsole,
    proConsole: () => ({ open: proConsoleOpen, chartLoaded: proTradingViewLoaded }),
    mobile: () => ({ active: window.matchMedia("(max-width: 760px)").matches, chartLoaded: mobileTradingViewLoaded }),
    room: () => ({ clear: roomClear, workflow: activeWorkflow, panelOpen }),
    setPanel: setActivePanel,
    openPanel,
    closePanel,
    state: () => dashboardState,
    clickObject: (panel) => setActivePanel(panel),
    summonJarvis: () => setActivePanel("phone"),
  };
  mountSovereign({ product: "Velez Swing", open: setActivePanel, close: closePanel, buildHotspots, position: positionRoomElements, setTheme: applyRoomTheme, state: () => dashboardState, openProConsole });
  window.__deskReady = true;
  window.__deskVersion = APP_BUILD;

  applyRoomTheme(roomSnapshot().theme);
  updateWorkflowChrome();
  positionRoomElements();
  loadTradingViewWidget();
  renderPanel();
  renderDeskOverview();
  renderMobileViews();
  updateActiveChrome();
  renderTradingModeControl();
  refreshWinstonStatus();
  refreshTradingMode({ force: true });
  refreshState().finally(() => scheduleDashboardRefresh());
}

init();

    let sovereignMusicBaseVolume = null;
 document.addEventListener("desk:winston-speaking", event => {
   const music = musicInstance();
   if (!music) return;
   try {
     if (event.detail?.speaking && sovereignMusicBaseVolume === null) {
       sovereignMusicBaseVolume = Number(music.volume ?? 1);
       music.volume = sovereignMusicBaseVolume * 0.18;
     } else if (!event.detail?.speaking && sovereignMusicBaseVolume !== null) {
       music.volume = sovereignMusicBaseVolume;
       sovereignMusicBaseVolume = null;
     }
   } catch (_) { /* The player may be disconnected during sign-out. */ }
 });

// Explicit audio handoff prevents phone recognition or narration overlapping a brief.
document.addEventListener("desk:brief-playback-start", () => {
  if (winstonState.callActive || winstonState.speaking || winstonState.listening) {
    winstonState.callActive = false;
    endWinstonCall();
  }
});
