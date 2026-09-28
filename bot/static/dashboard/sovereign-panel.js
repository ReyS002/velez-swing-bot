/* Shared panel rhythm: status, freshness, and a real return path. */
let mounted = false;
let adapter = null;
let history = [];
let restoring = false;
let attention = null;

const $ = (selector) => document.querySelector(selector);

function freshness(value) {
  const timestamp = Date.parse(value || "");
  if (!Number.isFinite(timestamp)) return "Awaiting a desk update";
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 15) return "Updated just now";
  if (seconds < 60) return `Updated ${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Updated ${minutes}m ago`;
  return `Updated ${Math.floor(minutes / 60)}h ago`;
}

function panelStatus(panel, state) {
  const broker = state?.broker || {};
  const brokerUnavailable = broker.ok === false && !["", "loading", "checking"].includes(String(broker.reason || "").toLowerCase());
  if (attention?.panel === panel) return { label: attention.message || "Desk item needs attention", tone: attention.tone || "attention" };
  if (!state?.timestamp) return { label: "Loading the latest desk state", tone: "loading" };
  if (state.ok === false) return { label: "Desk state unavailable — retrying", tone: "unavailable" };
  if (panel === "vault" && brokerUnavailable) return { label: "Connection needs attention", tone: "attention" };
  if (panel === "safe" && (state.pending_approvals || []).length) return { label: `${state.pending_approvals.length} approval${state.pending_approvals.length === 1 ? "" : "s"} needs review`, tone: "attention" };
  if (panel === "safe") return { label: "No approvals waiting", tone: "empty" };
  if (panel === "calendar" && !state?.timestamp) return { label: "Calendar feed is loading", tone: "loading" };
  return { label: "Ready", tone: "ready" };
}

function updateBackButton() {
  const back = $("#panel-back");
  if (!back) return;
  const previous = history.at(-1);
  back.hidden = !previous;
  back.disabled = !previous;
  back.textContent = previous ? `Back to ${previous.label || "previous view"}` : "Back";
}

function updateStatus({ panel, open, state } = {}) {
  const context = $("#panel-context");
  const detail = $("#detail-panel");
  if (!context || !detail) return;
  if (!open) {
    context.hidden = true;
    detail.removeAttribute("data-panel-state");
    return;
  }
  const status = panelStatus(panel, state);
  context.hidden = false;
  context.dataset.state = status.tone;
  context.querySelector("[data-panel-status]").textContent = status.label;
  context.querySelector("[data-panel-freshness]").textContent = freshness(state?.timestamp);
  detail.dataset.panelState = status.tone;
}

function captureHistory(event) {
  const detail = event.detail || {};
  if (!detail.wasOpen || !detail.previous || detail.previous === detail.panel || detail.restore) return;
  const entry = { panel: detail.previous, label: detail.previousLabel || detail.previous, scrollTop: Number(detail.scrollTop) || 0 };
  const last = history.at(-1);
  if (!last || last.panel !== entry.panel || last.scrollTop !== entry.scrollTop) history.push(entry);
}

function restorePrevious() {
  const previous = history.pop();
  if (!previous || !adapter?.open) return;
  restoring = true;
  adapter.open(previous.panel, { restore: true, restoreScroll: previous.scrollTop });
  requestAnimationFrame(() => {
    restoring = false;
    updateBackButton();
  });
}

export function mountPanelExperience(options = {}) {
  if (mounted) return;
  mounted = true;
  adapter = options;
  const heading = $("#detail-panel .panel-heading");
  const close = $("#panel-close");
  if (!heading || !close) return;
  const actions = document.createElement("div");
  actions.className = "panel-experience-actions";
  const back = document.createElement("button");
  back.id = "panel-back";
  back.type = "button";
  back.hidden = true;
  back.disabled = true;
  back.addEventListener("click", restorePrevious);
  actions.append(back, close);
  heading.append(actions);
  const context = document.createElement("div");
  context.id = "panel-context";
  context.hidden = true;
  context.innerHTML = '<span data-panel-status></span><span data-panel-freshness></span>';
  heading.insertAdjacentElement("afterend", context);
  document.addEventListener("desk:panel-request", captureHistory);
  document.addEventListener("desk:attention-open", (event) => {
    attention = event.detail || null;
    updateStatus({ panel: attention?.panel, open: true, state: adapter?.state?.() });
  });
  close.addEventListener("click", () => {
    history = [];
    attention = null;
    updateBackButton();
  });
}

export function updatePanelExperience(payload = {}) {
  if (!mounted) return;
  if (!payload.open) {
    history = [];
    attention = null;
  } else if (!restoring && attention?.panel && attention.panel !== payload.panel) {
    attention = null;
  }
  updateBackButton();
  updateStatus(payload);
}
