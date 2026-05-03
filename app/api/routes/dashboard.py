from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.services.performance_service import performance_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
STREAM_INTERVAL_SECONDS = 5


@router.get("", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD_HTML


@router.get("/data")
def dashboard_data() -> dict:
    return performance_service.daily_summary()


@router.websocket("/ws")
async def dashboard_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            snapshot = await asyncio.to_thread(performance_service.daily_summary)
            await websocket.send_json(
                jsonable_encoder(
                    {
                        "type": "snapshot",
                        "stream_interval_seconds": STREAM_INTERVAL_SECONDS,
                        "data": snapshot,
                    }
                )
            )
            await asyncio.sleep(STREAM_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return


DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sandy-Trading-AI Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f8;
      --panel: #ffffff;
      --panel-soft: #f9fbfc;
      --ink: #111827;
      --muted: #667085;
      --line: #d9e2ec;
      --good: #087443;
      --warn: #a15c00;
      --bad: #b42318;
      --accent: #155eef;
      --teal: #026b67;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 22px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: 22px; letter-spacing: 0; }
    h2 { font-size: 15px; margin-bottom: 10px; }
    h3 { font-size: 13px; margin-bottom: 8px; }
    main { max-width: 1500px; margin: 0 auto; padding: 16px 22px 28px; }
    nav {
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding: 8px;
      margin-bottom: 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    button, .link-button {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      border-radius: 8px;
      padding: 8px 11px;
      font-weight: 750;
      font-size: 13px;
      cursor: pointer;
      white-space: nowrap;
      text-decoration: none;
    }
    button:hover, button.active, .link-button:hover {
      border-color: var(--accent);
      color: var(--accent);
      background: #f4f8ff;
    }
    button.primary { background: var(--accent); color: white; border-color: var(--accent); }
    button.danger { color: var(--bad); border-color: #efc0b9; background: #fff7f5; }
    .top-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
    .subtle { color: var(--muted); font-size: 13px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }
    .grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 12px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-width: 0;
      overflow: hidden;
    }
    .soft { background: var(--panel-soft); }
    .span-3 { grid-column: span 3; }
    .span-4 { grid-column: span 4; }
    .span-5 { grid-column: span 5; }
    .span-6 { grid-column: span 6; }
    .span-7 { grid-column: span 7; }
    .span-8 { grid-column: span 8; }
    .span-12 { grid-column: span 12; }
    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.6fr) minmax(300px, 0.8fr);
      gap: 12px;
      align-items: stretch;
      margin-bottom: 14px;
    }
    .hero-main {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
    }
    .hero-side {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f9fbfc;
      padding: 16px;
    }
    .eyebrow { color: var(--muted); text-transform: uppercase; font-size: 12px; font-weight: 800; }
    .headline { font-size: 28px; line-height: 1.18; font-weight: 850; margin-top: 6px; overflow-wrap: anywhere; }
    .value { font-size: 24px; line-height: 1.1; font-weight: 850; margin-top: 4px; overflow-wrap: anywhere; }
    .value.small { font-size: 18px; }
    .label { color: var(--muted); font-size: 12px; text-transform: uppercase; font-weight: 800; }
    .row { display: flex; align-items: start; justify-content: space-between; gap: 12px; padding: 7px 0; border-bottom: 1px solid #edf1f5; }
    .row:last-child { border-bottom: 0; }
    .stack { display: grid; gap: 8px; }
    .tab { display: none; }
    .tab.active { display: block; }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      width: fit-content;
      max-width: 100%;
      padding: 4px 8px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: #f8fafc;
      font-size: 12px;
      font-weight: 850;
      overflow-wrap: anywhere;
    }
    .pill.good { color: var(--good); border-color: #a8dbc7; background: #edf8f3; }
    .pill.warn { color: var(--warn); border-color: #f2d197; background: #fff8e8; }
    .pill.bad { color: var(--bad); border-color: #eeb3ab; background: #fff2ef; }
    .pill.accent { color: var(--accent); border-color: #bad2ff; background: #f3f7ff; }
    .dot { width: 8px; height: 8px; border-radius: 999px; background: currentColor; display: inline-block; }
    .good { color: var(--good); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    .accent { color: var(--accent); }
    .teal { color: var(--teal); }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-size: 12px; text-transform: uppercase; }
    tbody tr:hover { background: #f8fbff; }
    .table-wrap { overflow-x: auto; }
    .events { display: grid; gap: 8px; }
    .event { border-left: 3px solid var(--line); padding: 9px 10px; border-radius: 0 8px 8px 0; background: #fbfcff; }
    .event.good { border-color: var(--good); }
    .event.warn { border-color: var(--warn); }
    .event.bad { border-color: var(--bad); }
    .event.accent { border-color: var(--accent); }
    .metric-band {
      display: grid;
      grid-template-columns: repeat(5, minmax(140px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
      min-width: 0;
    }
    .bar { height: 8px; border-radius: 999px; background: #e8edf4; overflow: hidden; margin-top: 7px; }
    .bar > div { height: 100%; width: 0; background: var(--good); }
    .profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .profile { border: 1px solid var(--line); border-radius: 8px; background: #fbfcff; padding: 12px; display: grid; gap: 7px; }
    .footer-note { margin-top: 14px; color: var(--muted); font-size: 12px; }
    @media (max-width: 1100px) {
      .span-3, .span-4, .span-5, .span-6, .span-7, .span-8 { grid-column: span 12; }
      .hero, .metric-band, .profile-grid { grid-template-columns: 1fr; }
      header { align-items: flex-start; flex-direction: column; }
      main { padding: 12px; }
      .headline { font-size: 23px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Sandy-Trading-AI</h1>
      <div class="subtle">Operator dashboard for shadow-live intraday research</div>
    </div>
    <div class="top-actions">
      <span id="streamStatus" class="pill warn"><span class="dot"></span> Connecting</span>
      <span id="modePill" class="pill">Mode</span>
      <span id="killPill" class="pill">Kill switch</span>
      <button id="pauseBtn">Pause Dashboard</button>
      <button id="refreshBtn">Refresh</button>
      <button id="runShadowBtn" class="primary">Run Shadow Cycle</button>
    </div>
  </header>
  <main>
    <nav aria-label="Dashboard sections">
      <button class="active" data-tab="mission">Mission Control</button>
      <button data-tab="markets">India / US Markets</button>
      <button data-tab="daily">Daily Review</button>
      <button data-tab="training">Training</button>
      <button data-tab="ledger">Shadow Ledger</button>
      <button data-tab="riskops">Risk & Safety</button>
    </nav>

    <section id="mission" class="tab active">
      <div class="hero">
        <div class="hero-main">
          <div class="eyebrow">Monday Intraday Readiness</div>
          <div id="missionHeadline" class="headline">Loading trading posture...</div>
          <div id="missionDetail" class="subtle" style="margin-top:8px"></div>
          <div id="missionPills" style="display:flex; gap:7px; flex-wrap:wrap; margin-top:12px"></div>
        </div>
        <div class="hero-side">
          <h2>Live Boundary</h2>
          <div class="stack" id="liveBoundaryRows"></div>
        </div>
      </div>

      <div class="metric-band">
        <div class="metric"><div class="label">Real Orders</div><div id="realOrdersMetric" class="value">0</div><div class="subtle">must stay zero in shadow mode</div></div>
        <div class="metric"><div class="label">Shadow P&L</div><div id="shadowPnlMetric" class="value">-</div><div id="shadowPnlPctMetric" class="subtle"></div></div>
        <div class="metric"><div class="label">Trainable Samples</div><div id="samplesMetric" class="value">-</div><div id="sampleTargetMetric" class="subtle"></div></div>
        <div class="metric"><div class="label">Stop-Loss Coverage</div><div id="stopCoverageMetric" class="value">-</div><div class="bar"><div id="stopCoverageBar"></div></div></div>
        <div class="metric"><div class="label">Next India Session</div><div id="nextSessionMetric" class="value small">-</div><div id="zerodhaTokenMetric" class="subtle"></div></div>
      </div>

      <div class="grid">
        <div class="panel span-6">
          <h2>What The Bot Is Doing</h2>
          <div id="botAction" class="value small">-</div>
          <div id="studiedSymbols" class="subtle" style="margin-top:8px"></div>
        </div>
        <div class="panel span-6">
          <h2>Monday Plan</h2>
          <div id="mondayPlan" class="events"></div>
        </div>
        <div class="panel span-6">
          <h2>India Readiness</h2>
          <div id="indiaReadiness" class="stack"></div>
        </div>
        <div class="panel span-6">
          <h2>US Readiness</h2>
          <div id="usReadiness" class="stack"></div>
        </div>
        <div class="panel span-12">
          <h2>Live Feed</h2>
          <div id="liveFeed" class="events"></div>
        </div>
      </div>
    </section>

    <section id="markets" class="tab">
      <div class="grid">
        <div class="panel span-6"><h2>India Market</h2><div id="indiaMarketCard" class="stack"></div></div>
        <div class="panel span-6"><h2>US Market</h2><div id="usMarketCard" class="stack"></div></div>
        <div class="panel span-6">
          <h2>India Shadow Book</h2>
          <div class="table-wrap"><table><thead><tr><th>Symbol</th><th>Stop</th><th>Target</th><th>R/R</th><th>P&L</th><th>Marked</th></tr></thead><tbody id="indiaRows"></tbody></table></div>
        </div>
        <div class="panel span-6">
          <h2>US Shadow Book</h2>
          <div class="table-wrap"><table><thead><tr><th>Symbol</th><th>Stop</th><th>Target</th><th>R/R</th><th>P&L INR</th><th>Marked</th></tr></thead><tbody id="usRows"></tbody></table></div>
        </div>
      </div>
    </section>

    <section id="daily" class="tab">
      <div class="grid">
        <div class="panel span-12">
          <h2>Daily Shadow Review</h2>
          <div id="dailySubtitle" class="subtle"></div>
        </div>
        <div class="panel span-6"><h2>India Daily Review</h2><div id="indiaDaily" class="stack"></div></div>
        <div class="panel span-6"><h2>US Daily Review</h2><div id="usDaily" class="stack"></div></div>
        <div class="panel span-12">
          <h2>Market Comparison</h2>
          <div class="table-wrap"><table><thead><tr><th>Market</th><th>Date</th><th>Signals</th><th>Shadow Marks</th><th>Real Orders</th><th>Would-Have P&L</th><th>Win/Loss/Flat</th></tr></thead><tbody id="dailyComparison"></tbody></table></div>
        </div>
        <div class="panel span-12">
          <h2>Everyday P&L History</h2>
          <div class="table-wrap"><table><thead><tr><th>Date</th><th>India P&L</th><th>India Marks</th><th>US P&L</th><th>US Marks</th><th>Total Shadow P&L</th><th>Real Orders</th></tr></thead><tbody id="historyRows"></tbody></table></div>
        </div>
      </div>
    </section>

    <section id="training" class="tab">
      <div class="grid">
        <div class="panel span-5">
          <h2>Intraday Model Training</h2>
          <div id="modelState" class="stack"></div>
        </div>
        <div class="panel span-7">
          <h2>Algorithm Diagnostics</h2>
          <div id="modelActions" class="events"></div>
        </div>
        <div class="panel span-12">
          <h2>Model Feature Diagnostics</h2>
          <div class="table-wrap"><table><thead><tr><th>Feature</th><th>Samples</th><th>Correlation To P&L</th><th>Hint</th></tr></thead><tbody id="featureRows"></tbody></table></div>
        </div>
        <div class="panel span-12">
          <h2>Strategy Lab</h2>
          <h3>Intraday Strategy Playbook</h3>
          <div id="strategyProfiles" class="profile-grid"></div>
        </div>
      </div>
    </section>

    <section id="ledger" class="tab">
      <div class="panel">
        <h2>Shadow Ledger</h2>
        <div class="subtle">Shadow transactions only. These are not Zerodha orders, broker fills, or recommendations.</div>
        <div class="table-wrap" style="margin-top:10px">
          <table><thead><tr><th>Symbol</th><th>Market</th><th>Status</th><th>Entry</th><th>Current</th><th>Stop</th><th>Target</th><th>Qty</th><th>Hyp. Notional</th><th>Hyp. P&L</th><th>Marked</th></tr></thead><tbody id="ledgerRows"></tbody></table>
        </div>
      </div>
    </section>

    <section id="riskops" class="tab">
      <div class="grid">
        <div class="panel span-6">
          <h2>Risk & Safety</h2>
          <div id="riskRows" class="stack"></div>
        </div>
        <div class="panel span-6">
          <h2>Broker & Provider Health</h2>
          <div id="healthRows" class="events"></div>
        </div>
        <div class="panel span-6">
          <h2>Zerodha Daily Auth</h2>
          <div id="zerodhaRows" class="stack"></div>
          <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px">
            <a class="link-button" href="/zerodha/login" target="_blank" rel="noreferrer">Open Zerodha Login</a>
            <button id="reconnectBtn">Reconnect</button>
          </div>
        </div>
        <div class="panel span-6">
          <h2>Email Status</h2>
          <div id="emailRows" class="stack"></div>
          <div class="subtle" style="margin-top:8px">Delivery mode is local Mailpit unless external SMTP is configured.</div>
          <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px">
            <a class="link-button" href="http://127.0.0.1:8025" target="_blank" rel="noreferrer">Open Mailpit</a>
            <button id="sendEmailBtn">Send Summary Email</button>
          </div>
        </div>
        <div class="panel span-12">
          <h2>Orders</h2>
          <div class="table-wrap"><table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody id="orderRows"></tbody></table></div>
        </div>
      </div>
    </section>

    <div class="footer-note">No live order endpoint is exposed from this dashboard. Learned signals remain shadow-only until deterministic risk, compliance, provider, broker, FX, calendar, and kill-switch gates pass.</div>
  </main>

  <script>
    let latestData = null;
    let socket = null;
    let paused = false;
    let messageCount = 0;
    let transport = "polling";
    let fallbackTimer = null;

    const q = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
    const num = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 3 });
    const fmtInr = (value) => `INR ${inr.format(Number(value || 0))}`;
    const pct = (value) => `${(Number(value || 0) * 100).toFixed(2)}%`;
    const shortTime = (value) => value ? new Date(value).toLocaleString("en-IN", { hour12: false }) : "-";
    const pnlClass = (value) => Number(value || 0) > 0 ? "good" : (Number(value || 0) < 0 ? "bad" : "warn");
    const emptyRow = (cols, text) => `<tr><td colspan="${cols}" class="subtle">${esc(text)}</td></tr>`;
    const row = (label, value) => `<div class="row"><span class="subtle">${esc(label)}</span><strong>${esc(value)}</strong></div>`;
    const pill = (text, klass = "") => `<span class="pill ${klass}"><span class="dot"></span>${esc(text)}</span>`;
    const eventCard = (title, detail, meta = "", klass = "") => `<div class="event ${klass}"><strong>${esc(title)}</strong><div class="subtle">${esc(detail)}</div><div class="mono subtle">${esc(meta)}</div></div>`;

    document.querySelectorAll("nav button").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll("nav button").forEach((item) => item.classList.remove("active"));
        document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        q(button.dataset.tab).classList.add("active");
      });
    });

    q("pauseBtn").addEventListener("click", () => {
      paused = !paused;
      q("pauseBtn").textContent = paused ? "Resume Dashboard" : "Pause Dashboard";
      if (!paused) connectWebSocket();
    });
    q("refreshBtn").addEventListener("click", () => load());
    q("reconnectBtn").addEventListener("click", () => connectWebSocket());
    q("runShadowBtn").addEventListener("click", async () => {
      q("runShadowBtn").disabled = true;
      q("runShadowBtn").textContent = "Running...";
      try {
        await fetch("/shadow/run-cycle", { method: "POST" });
        await load();
      } finally {
        q("runShadowBtn").disabled = false;
        q("runShadowBtn").textContent = "Run Shadow Cycle";
      }
    });
    q("sendEmailBtn").addEventListener("click", async () => {
      q("sendEmailBtn").disabled = true;
      try {
        await fetch("/alerts/daily-summary/email", { method: "POST" });
        await load();
      } finally {
        q("sendEmailBtn").disabled = false;
      }
    });

    async function load() {
      const data = await fetch("/dashboard/data", { cache: "no-store" }).then((response) => response.json());
      latestData = data;
      render(data);
    }

    function connectWebSocket() {
      if (paused) return;
      clearInterval(fallbackTimer);
      if (socket) socket.close();
      q("streamStatus").className = "pill warn";
      q("streamStatus").innerHTML = '<span class="dot"></span> Connecting';
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}/dashboard/ws`);
      socket.onopen = () => {
        transport = "websocket";
        q("streamStatus").className = "pill good";
        q("streamStatus").innerHTML = '<span class="dot"></span> Live';
      };
      socket.onmessage = (event) => {
        if (paused) return;
        const payload = JSON.parse(event.data);
        if (payload.type === "snapshot") {
          messageCount += 1;
          latestData = payload.data;
          render(payload.data);
        }
      };
      socket.onerror = () => startFallback();
      socket.onclose = () => startFallback();
    }

    function startFallback() {
      if (paused) return;
      transport = "polling";
      q("streamStatus").className = "pill warn";
      q("streamStatus").innerHTML = '<span class="dot"></span> Polling';
      clearInterval(fallbackTimer);
      fallbackTimer = setInterval(load, 15000);
      load();
    }

    function render(data) {
      renderHeader(data);
      renderMission(data);
      renderMarkets(data);
      renderDaily(data);
      renderTraining(data);
      renderLedger(data);
      renderRiskOps(data);
    }

    function totalOrders(data) {
      return Object.values(data.orders || {}).reduce((sum, value) => sum + Number(value || 0), 0);
    }

    function renderHeader(data) {
      const system = data.system || {};
      q("modePill").className = "pill accent";
      q("modePill").innerHTML = `<span class="dot"></span>${esc(system.trading_mode || "-")}`;
      q("killPill").className = system.kill_switch ? "pill good" : "pill bad";
      q("killPill").innerHTML = `<span class="dot"></span>Kill ${system.kill_switch ? "ON" : "OFF"}`;
    }

    function renderMission(data) {
      const system = data.system || {};
      const readiness = data.readiness || {};
      const bot = data.bot_activity || {};
      const shadow = data.shadow || {};
      const model = (data.training || {}).intraday_model || data.model_training || {};
      const orders = totalOrders(data);
      const canLive = system.live_trading_enabled && !system.kill_switch && orders === 0 && model.status === "CALIBRATED_SHADOW_ONLY";
      q("missionHeadline").textContent = canLive
        ? "Live readiness needs final human review before any order path."
        : "Monday stays shadow-only until evidence and gates are strong enough.";
      q("missionDetail").textContent = bot.current_action || "Waiting for the next shadow cycle.";
      q("missionPills").innerHTML = [
        pill(system.live_trading_enabled ? "Live flag enabled" : "Live disabled", system.live_trading_enabled ? "bad" : "good"),
        pill(system.kill_switch ? "Kill switch on" : "Kill switch off", system.kill_switch ? "good" : "bad"),
        pill(model.status || "WAITING_FOR_MARKET_DATA", model.status === "CALIBRATED_SHADOW_ONLY" ? "good" : "warn"),
        pill(`${transport} ${messageCount ? messageCount + " updates" : ""}`.trim(), "accent"),
      ].join("");
      q("liveBoundaryRows").innerHTML = [
        row("Live trading", system.live_trading_enabled ? "enabled" : "disabled"),
        row("Kill switch", system.kill_switch ? "on" : "off"),
        row("Real orders today", orders),
        row("Shadow cadence", `${data.training?.current_loop_interval_seconds || 300}s`),
        row("Safety blockers", (system.safety_errors || []).length || "none"),
        row("Promotion", model.promotion_status || "LIVE_BLOCKED_BY_DESIGN"),
      ].join("");
      q("realOrdersMetric").textContent = orders;
      q("realOrdersMetric").className = `value ${orders ? "bad" : "good"}`;
      q("shadowPnlMetric").textContent = fmtInr(shadow.hypothetical_pnl_inr);
      q("shadowPnlMetric").className = `value ${pnlClass(shadow.hypothetical_pnl_inr)}`;
      q("shadowPnlPctMetric").textContent = pct(shadow.hypothetical_pnl_pct);
      q("samplesMetric").textContent = `${model.trainable_samples || 0}/${model.min_total_samples_required || 200}`;
      q("sampleTargetMetric").textContent = `${model.status || "WAITING"} | India ${(model.markets?.INDIA?.trainable_samples) || 0}, US ${(model.markets?.US?.trainable_samples) || 0}`;
      q("stopCoverageMetric").textContent = pct(model.stop_loss_coverage || 0);
      q("stopCoverageBar").style.width = `${Math.max(0, Math.min(Number(model.stop_loss_coverage || 0) * 100, 100))}%`;
      q("nextSessionMetric").textContent = readiness.next_india_session_date || "-";
      const zerodha = data.zerodha_auth || {};
      q("zerodhaTokenMetric").textContent = zerodha.access_token_generated_at
        ? `Zerodha token ${shortTime(zerodha.access_token_generated_at)}`
        : "Zerodha token missing";
      q("botAction").textContent = bot.current_action || "-";
      q("studiedSymbols").textContent = `Studied today: ${(bot.studied_symbols_today || []).join(", ") || "none yet"}`;
      q("mondayPlan").innerHTML = [
        eventCard("Monday entry posture", "Run India intraday in shadow mode first; do not place live orders from an unproven model.", readiness.next_india_session_date || "", "accent"),
        eventCard("Risk posture", "Every hypothesis requires stop-loss, target, reward/risk, fresh market data, and no short/margin/derivatives.", `Stop coverage ${pct(model.stop_loss_coverage || 0)}`, "good"),
        eventCard("Evidence gate", (model.next_actions || ["Collect market-hours samples before any promotion."])[0], model.status || "", "warn"),
      ].join("");
      q("indiaReadiness").innerHTML = readinessCard(data.markets?.INDIA, readiness.ready_for_india_shadow_now);
      q("usReadiness").innerHTML = readinessCard(data.markets?.US, readiness.ready_for_us_shadow_now);
      q("liveFeed").innerHTML = liveFeedRows(data);
    }

    function readinessCard(market, ready) {
      market = market || {};
      const checks = (market.readiness_checks || []).slice(0, 5);
      return [
        row("Status", ready ? "ready for shadow" : "waiting"),
        row("Symbols", `${market.configured_symbol_count || 0}`),
        row("Last cycle", `${market.observed_last_cycle || 0} observed`),
        row("Shadow P&L", fmtInr(market.hypothetical_pnl_inr || 0)),
        ...checks.map((check) => row(check.name || "check", check.passed ? "pass" : (check.detail || "open"))),
      ].join("");
    }

    function liveFeedRows(data) {
      const items = [];
      (data.shadow?.recent_observations || []).slice(0, 5).forEach((item) => items.push(
        eventCard(
          `${item.market} ${item.symbol}`,
          `Stop ${num.format(item.assessment?.stop_loss || 0)} | target ${num.format(item.assessment?.take_profit || 0)} | P&L ${fmtInr(item.hypothetical_pnl_inr)}`,
          shortTime(item.last_marked_at),
          pnlClass(item.hypothetical_pnl_inr),
        )
      ));
      (data.recent_risk_events || []).slice(0, 3).forEach((item) => items.push(
        eventCard(`Risk: ${item.event_type}`, item.message, shortTime(item.created_at), item.severity === "ERROR" ? "bad" : "warn")
      ));
      return items.join("") || eventCard("No feed items", "Waiting for market-hours shadow observations.", "", "warn");
    }

    function renderMarkets(data) {
      const markets = data.markets || {};
      q("indiaMarketCard").innerHTML = marketCard(markets.INDIA);
      q("usMarketCard").innerHTML = marketCard(markets.US);
      const observations = data.shadow?.recent_observations || [];
      q("indiaRows").innerHTML = observationRows(observations.filter((item) => item.market === "INDIA"), 6);
      q("usRows").innerHTML = observationRows(observations.filter((item) => item.market === "US"), 6);
    }

    function marketCard(market) {
      market = market || {};
      return [
        row("Shadow ready", market.shadow_ready_now ? "yes" : "no"),
        row("Configured symbols", `${market.configured_symbol_count || 0}: ${(market.configured_symbols || []).join(", ")}`),
        row("Observed last cycle", market.observed_last_cycle || 0),
        row("Active observations", market.active_observations || 0),
        row("Would-have P&L", fmtInr(market.hypothetical_pnl_inr || 0)),
        row("Win/Loss/Flat", `${market.winners || 0}/${market.losers || 0}/${market.flat || 0}`),
      ].join("");
    }

    function observationRows(rows, cols) {
      if (!rows.length) return emptyRow(cols, "No shadow observations for this market yet.");
      return rows.slice(0, 20).map((item) => `<tr>
        <td>${esc(item.symbol)}</td>
        <td>${num.format(item.assessment?.stop_loss || 0)}</td>
        <td>${num.format(item.assessment?.take_profit || 0)}</td>
        <td>${num.format(item.assessment?.reward_risk_ratio || 0)}</td>
        <td class="${pnlClass(item.hypothetical_pnl_inr)}">${fmtInr(item.hypothetical_pnl_inr)}</td>
        <td>${shortTime(item.last_marked_at)}</td>
      </tr>`).join("");
    }

    function renderDaily(data) {
      const review = data.daily_review || {};
      const markets = review.markets || {};
      const india = markets.INDIA || {};
      const us = markets.US || {};
      q("dailySubtitle").textContent = review.summary || "P&L is hypothetical unless real orders are explicitly shown.";
      q("indiaDaily").innerHTML = dailyCard(india);
      q("usDaily").innerHTML = dailyCard(us);
      q("dailyComparison").innerHTML = [india, us].map((item) => `<tr>
        <td>${esc(item.display_name || item.market || "-")}</td>
        <td>${esc(item.review_date || "-")}</td>
        <td>${item.signals || 0}</td>
        <td>${item.shadow_hypotheses || 0}</td>
        <td class="${Number(item.real_orders || 0) ? "bad" : "good"}">${item.real_orders || 0}</td>
        <td class="${pnlClass(item.hypothetical_pnl_inr)}">${fmtInr(item.hypothetical_pnl_inr || 0)} (${pct(item.hypothetical_pnl_pct || 0)})</td>
        <td>${item.winners || 0}/${item.losers || 0}/${item.flat || 0}</td>
      </tr>`).join("");
      q("historyRows").innerHTML = (review.history || []).length
        ? review.history.map((item) => {
            const indiaRow = item.INDIA || {};
            const usRow = item.US || {};
            return `<tr>
              <td>${esc(item.review_date || "-")}</td>
              <td class="${pnlClass(indiaRow.hypothetical_pnl_inr)}">${fmtInr(indiaRow.hypothetical_pnl_inr || 0)}</td>
              <td>${indiaRow.shadow_hypotheses || 0}</td>
              <td class="${pnlClass(usRow.hypothetical_pnl_inr)}">${fmtInr(usRow.hypothetical_pnl_inr || 0)}</td>
              <td>${usRow.shadow_hypotheses || 0}</td>
              <td class="${pnlClass(item.total_hypothetical_pnl_inr)}">${fmtInr(item.total_hypothetical_pnl_inr || 0)}</td>
              <td class="${Number(item.total_real_orders || 0) ? "bad" : "good"}">${item.total_real_orders || 0}</td>
            </tr>`;
          }).join("")
        : emptyRow(7, "No daily review history yet.");
    }

    function dailyCard(item) {
      const lessons = [...(item.lessons || []), ...(item.next_focus || [])].slice(0, 4);
      return [
        row("Status", item.status || "NO_DATA"),
        row("Date", item.review_date || "-"),
        row("Would-have P&L", `${fmtInr(item.hypothetical_pnl_inr || 0)} (${pct(item.hypothetical_pnl_pct || 0)})`),
        row("Signals / marks", `${item.signals || 0} / ${item.shadow_hypotheses || 0}`),
        row("Real orders", item.real_orders || 0),
        ...lessons.map((lesson) => row("Insight", lesson)),
      ].join("");
    }

    function renderTraining(data) {
      const training = data.training || {};
      const model = training.intraday_model || data.model_training || {};
      q("modelState").innerHTML = [
        row("Status", model.status || "WAITING_FOR_MARKET_DATA"),
        row("Shadow-only model", model.shadow_only === false ? "no" : "yes"),
        row("No order placement", model.no_order_placement === false ? "no" : "yes"),
        row("Trainable samples", `${model.trainable_samples || 0}/${model.min_total_samples_required || 200}`),
        row("Stop-Loss Coverage", pct(model.stop_loss_coverage || 0)),
        row("Artifact", model.artifact_path || "-"),
      ].join("");
      q("modelActions").innerHTML = (model.next_actions || training.model_notes || [])
        .slice(0, 7)
        .map((item) => eventCard("Model action", item, model.status || "", "accent"))
        .join("") || eventCard("Collect data", "Run market-hours shadow cycles.", "", "warn");
      q("featureRows").innerHTML = (model.feature_diagnostics || []).length
        ? model.feature_diagnostics.map((item) => `<tr><td>${esc(item.name)}</td><td>${item.samples || 0}</td><td>${item.correlation_to_pnl_pct == null ? "-" : num.format(item.correlation_to_pnl_pct)}</td><td>${esc(item.directional_hint || "-")}</td></tr>`).join("")
        : emptyRow(4, "Not enough samples for feature diagnostics yet.");
      q("strategyProfiles").innerHTML = (data.strategy_lab?.profiles || []).map((profile) => `<div class="profile">
        <div style="display:flex; justify-content:space-between; gap:8px; align-items:start">
          <strong>${esc(profile.name)}</strong>
          ${pill(profile.status || "-", profile.status === "DISABLED_HIGH_RISK" ? "bad" : "accent")}
        </div>
        <div class="subtle">${esc(profile.entry_model || "")}</div>
        <div class="subtle"><strong>Stop:</strong> ${esc(profile.stop_model || "")}</div>
        <div class="subtle"><strong>Controls:</strong> ${esc((profile.risk_controls || []).join(" | "))}</div>
      </div>`).join("");
    }

    function renderLedger(data) {
      const rows = data.shadow?.recent_observations || [];
      q("ledgerRows").innerHTML = rows.length
        ? rows.slice(0, 50).map((item) => `<tr>
            <td>${esc(item.symbol)}</td>
            <td>${esc(item.market)}</td>
            <td>${esc(item.status)}</td>
            <td>${num.format(item.entry_price || 0)}</td>
            <td>${num.format(item.current_price || 0)}</td>
            <td>${num.format(item.assessment?.stop_loss || 0)}</td>
            <td>${num.format(item.assessment?.take_profit || 0)}</td>
            <td>${item.hypothetical_quantity || 0}</td>
            <td>${fmtInr(item.hypothetical_notional_inr || 0)}</td>
            <td class="${pnlClass(item.hypothetical_pnl_inr)}">${fmtInr(item.hypothetical_pnl_inr || 0)}</td>
            <td>${shortTime(item.last_marked_at)}</td>
          </tr>`).join("")
        : emptyRow(11, "No shadow ledger rows yet.");
    }

    function renderRiskOps(data) {
      const system = data.system || {};
      const risk = data.risk || {};
      q("riskRows").innerHTML = [
        row("Trading mode", system.trading_mode || "-"),
        row("Live enabled", system.live_trading_enabled ? "true" : "false"),
        row("Kill switch", system.kill_switch ? "true" : "false"),
        row("Safety errors", (system.safety_errors || []).join(", ") || "none"),
        row("Decisions today", risk.decisions_today || 0),
        row("Risk events today", risk.risk_events_today || 0),
        row("Max risk per trade", pct(risk.max_risk_per_trade_pct || 0)),
      ].join("");
      const brokers = (data.brokers || []).map((item) => eventCard(`${item.broker_name} ${item.market}`, `auth=${item.auth_status}, account=${item.account_status}, trading=${item.trading_enabled}`, (item.rejection_reasons || []).join(", ") || "healthy", item.trading_enabled ? "good" : "warn"));
      const providers = (data.providers || []).map((item) => eventCard(`${item.provider_name} ${item.market}`, `status=${item.status}, freshness=${item.freshness_status}`, item.last_error || "no error", item.status === "OK" ? "good" : "warn"));
      q("healthRows").innerHTML = [...brokers, ...providers].join("");
      const zerodha = data.zerodha_auth || {};
      q("zerodhaRows").innerHTML = [
        row("Access token", zerodha.access_token_present ? "present" : "missing"),
        row("Generated", zerodha.access_token_generated_at ? shortTime(zerodha.access_token_generated_at) : "-"),
        row("Login time", zerodha.access_token_login_time || "-"),
        row("Daily manual login", zerodha.manual_daily_login_required ? "required by Kite" : "not required"),
        row("Zero intervention", zerodha.zero_intervention_possible ? "possible" : "not possible"),
      ].join("");
      const email = data.email || {};
      q("emailRows").innerHTML = [
        row("Enabled", email.enabled ? "yes" : "no"),
        row("SMTP", `${email.smtp_host || "-"}:${email.smtp_port || "-"}`),
        row("Delivery mode", email.local_preview_url ? "local preview" : "external SMTP"),
        row("Recipient", email.recipient_masked || "-"),
      ].join("");
      q("orderRows").innerHTML = Object.entries(data.orders || {}).map(([status, count]) => `<tr><td>${esc(status)}</td><td>${count}</td></tr>`).join("") || emptyRow(2, "No orders.");
    }

    connectWebSocket();
  </script>
</body>
</html>
"""
