// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// GPU tab — per-model GPU load over time, from the read-only exporter proxy.
// Hand-rolled SVG, no deps. Two single-axis charts (never dual-axis): a
// stacked memory area per model against the card total, and a whole-GPU
// utilization strip. Fixed series order + fixed categorical palette
// (validated: adjacent-pair CVD ΔE ≥ 8, normal ≥ 15; three low-contrast
// slots are relieved by the legend, tooltip, and the Now table).

import { escapeHtml as gesc, rememberSessions, sessionTitle, sessionDate } from "./display.js?v=console-maintenance1";

const gpuMain = document.getElementById("gpu");
const tabGpu = document.getElementById("tab-gpu");
const gTabIds = ["tab-topo", "tab-chat", "tab-inspect"];
const gMainIds = ["topo", "chat", "inspect"];
const gTabs = gTabIds.map((id) => document.getElementById(id));
const gMains = gMainIds.map((id) => document.getElementById(id));

let gpuTimer = null;
tabGpu.onclick = () => {
  for (const m of gMains) m.style.display = "none";
  gpuMain.style.display = "grid";
  for (const b of gTabs) b.classList.remove("active");
  tabGpu.classList.add("active");
  loadGpu();
  if (gpuTimer) clearInterval(gpuTimer);
  gpuTimer = setInterval(() => {
    if (gpuMain.style.display !== "none") loadGpu();
  }, 5000);
};
for (const b of gTabs) {
  const prev = b.onclick;
  b.onclick = (e) => {
    gpuMain.style.display = "none";
    tabGpu.classList.remove("active");
    if (gpuTimer) { clearInterval(gpuTimer); gpuTimer = null; }
    if (prev) prev(e);
  };
}

// Fixed identity -> fixed slot; never cycled. Anything else folds to "Other".
// Two fixed sets — the active one is picked from the measured samples
// (unified=true marks the Jetson/Thor probe), never asserted.
const WS_SERIES = [
  { key: "isaac-sim", label: "Isaac Sim", color: "#2a78d6" },
  { key: "groot-red-left", label: "GR00T red · L", color: "#eb6834" },
  { key: "groot-blue-left", label: "GR00T blue · L", color: "#1baf7a" },
  { key: "groot-green-left", label: "GR00T green · L", color: "#eda100" },
  { key: "groot-red-right", label: "GR00T red · R", color: "#e87ba4" },
  { key: "groot-blue-right", label: "GR00T blue · R", color: "#008300" },
  { key: "groot-green-right", label: "GR00T green · R", color: "#4a3aa7" },
  { key: "other", label: "Other", color: "#e34948" },
];
const THOR_SERIES = [
  { key: "cosmos-reason-vlm", label: "Cosmos Reason VLM", color: "#76b900" },
  { key: "cosmos-edge-vlm", label: "Cosmos3 Edge VLM", color: "#008300" },
  { key: "nemotron-vlm", label: "Nemotron VLM", color: "#e87ba4" },
  { key: "vllm-server", label: "Other vLLM server", color: "#8c6bb1" },
  { key: "legacy-vlm", label: "Legacy VLM (mixed)", color: "#8090a0" },
  { key: "openclaw-gateway", label: "OpenClaw", color: "#2a78d6" },
  { key: "groot-shared-left", label: "GR00T shared · left", color: "#eb6834" },
  { key: "groot-shared-right", label: "GR00T shared · right", color: "#1baf7a" },
  { key: "groot-specialists", label: "GR00T specialist policies", color: "#4a3aa7" },
  { key: "groot-relays", label: "GR00T relays", color: "#b05a9c" },
  { key: "ros2", label: "ROS 2", color: "#eda100" },
  { key: "other", label: "Other", color: "#e34948" },
];
// Preserve historical telemetry written before the shared/specialist roles
// were named explicitly. New samples arrive with the canonical keys above.
const THOR_ROLE_ALIASES = {
  "cosmos-vlm": "legacy-vlm",
  "groot-r": "groot-specialists",
  "groot-b": "groot-specialists",
  "groot-g": "groot-specialists",
  "groot-server": "groot-relays",
};
let SERIES = THOR_SERIES;
let KNOWN = new Set(SERIES.filter((s) => s.key !== "other").map((s) => s.key));

const RANGES = [
  { label: "15m", minutes: 15 },
  { label: "1h", minutes: 60 },
  { label: "6h", minutes: 360 },
  { label: "24h", minutes: 1440 },
];
let rangeMin = 60;

let sessionId = null; // non-null = reviewing one mission's window, not live

const rangeEl = document.getElementById("gpurange");
rangeEl.innerHTML =
  RANGES.map(
    (r) => `<button data-min="${r.minutes}" class="${r.minutes === rangeMin ? "active" : ""}">${r.label}</button>`,
  ).join("") +
  `<select id="gpusession" aria-label="GPU history">
     <option value="">Live</option></select>`;
for (const b of rangeEl.querySelectorAll("button")) {
  b.onclick = () => {
    sessionId = null;
    document.getElementById("gpusession").value = "";
    rangeMin = Number(b.dataset.min);
    for (const x of rangeEl.querySelectorAll("button")) x.classList.toggle("active", x === b);
    loadGpu();
  };
}
document.getElementById("gpusession").onchange = (ev) => {
  sessionId = ev.target.value || null;
  for (const x of rangeEl.querySelectorAll("button")) x.classList.remove("active");
  if (!sessionId) {
    rangeMin = 60;
    rangeEl.querySelector('button[data-min="60"]').classList.add("active");
  }
  loadGpu();
};

let sessionsRequest = null;
let sessionsLoadedAt = 0;
async function loadSessions() {
  if (sessionsRequest) return sessionsRequest;
  if (Date.now() - sessionsLoadedAt < 30000) return;
  sessionsRequest = (async () => {
    const read = async (url) => {
      const response = await fetch(url);
      if (!response.ok) throw new Error("History unavailable");
      return response.json();
    };
    const results = await Promise.allSettled([
      read("/api/chat-sessions"), read("/api/missions?limit=15"),
    ]);
    if (results.every((r) => r.status === "rejected")) return;
    const chatBody = results[0].status === "fulfilled" ? results[0].value : {};
    const missionBody = results[1].status === "fulfilled" ? results[1].value : {};
    const combined = [...(chatBody.sessions || []), ...(missionBody.missions || [])];
    rememberSessions(combined);
    const seen = new Set();
    const missions = combined.filter((m) => {
      const id = m.mission_id || m.id || "";
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
    const sel = document.getElementById("gpusession");
    sel.innerHTML = '<option value="">Live</option>' +
      (sessionId && !seen.has(sessionId)
        ? `<option value="${gesc(sessionId)}">${gesc(sessionTitle(sessionId))}</option>` : "") +
      missions.map((m) => {
        const id = m.mission_id || m.id || "";
        const date = sessionDate(m);
        const label = `${sessionTitle(m)}${date ? ` · ${date}` : ""}`;
        return `<option value="${gesc(id)}">${gesc(label)}</option>`;
      }).join("");
    sel.value = sessionId || "";
    sessionsLoadedAt = Date.now();
  })().finally(() => { sessionsRequest = null; });
  return sessionsRequest;
}

const memEl = document.getElementById("gpumemchart");
const utilEl = document.getElementById("gputilchart");
const legendEl = document.getElementById("gpulegend");
const tableEl = document.getElementById("gputable");
const tipEl = document.getElementById("gputip");
const scopeEl = document.getElementById("gpuscope");
const liveEl = document.getElementById("gpulive");

let lastSamples = [];
let gpuRequest = null;
let gpuRequestScope = "";
let gpuGeneration = 0;
let displayedScope = "";
const memoryNote = document.getElementById("gpu-memory-note");
const sessionDetails = document.getElementById("gpu-session-details");
const sessionIdEl = document.getElementById("gpu-session-id");

function updateSessionDetails() {
  if (sessionDetails) {
    sessionDetails.hidden = !sessionId;
    if (sessionIdEl && sessionIdEl.textContent !== (sessionId || "")) sessionDetails.open = false;
  }
  if (sessionIdEl) sessionIdEl.textContent = sessionId || "";
}

function seriesMem(sample) {
  const out = {};
  for (const s of SERIES) out[s.key] = 0;
  for (const [role, p] of Object.entries(sample.procs || {})) {
    const canonical = sample.unified ? (THOR_ROLE_ALIASES[role] || role) : role;
    const key = KNOWN.has(canonical) ? canonical : "other";
    out[key] += Number(p.mem_mib) || 0;
  }
  return out;
}

function pct(used, total) {
  return total > 0 ? Math.round((100 * used) / total) : 0;
}

function renderLive(sample) {
  if (!liveEl || !sample) {
    if (liveEl) liveEl.innerHTML = "";
    return;
  }
  const ramUsed = Number(sample.ram_used_mib ?? sample.mem_used_mib) || 0;
  const ramTotal = Number(sample.ram_total_mib ?? sample.mem_total_mib) || 0;
  const unified = Boolean(sample.unified);
  const gpuMem = unified
    ? "shared with RAM"
    : `${(Number(sample.mem_used_mib || 0) / 1024).toFixed(1)} / ${(Number(sample.mem_total_mib || 0) / 1024).toFixed(1)} GiB`;
  const power = sample.gpu_power_mw == null
    ? "—"
    : `${(Number(sample.gpu_power_mw) / 1000).toFixed(1)} W`;
  const age = Math.max(0, Math.round((Date.now() - Date.parse(sample.ts)) / 1000));
  const freshness = !Number.isFinite(age) ? "Unknown"
    : age < 60 ? `${age}s ago` : age < 3600 ? `${Math.floor(age / 60)}m ago`
      : `${Math.floor(age / 3600)}h ago`;
  liveEl.innerHTML = [
    ["GPU utilization", `${Number(sample.gpu_util_pct) || 0}%`],
    [unified ? "GPU memory" : "GPU memory used", gpuMem],
    ["System RAM", `${(ramUsed / 1024).toFixed(1)} / ${(ramTotal / 1024).toFixed(1)} GiB · ${pct(ramUsed, ramTotal)}%`],
    ["GPU power", power],
    [sessionId ? "Sample time" : "Updated", sessionId ? fmtDateTime(sample.ts) : freshness],
  ].map(([label, value]) =>
    `<div class="gpu-metric"><span>${gesc(label)}</span><strong>${gesc(value)}</strong></div>`
  ).join("");
}

const W = 900, HM = 260, HU = 90, PL = 52, PR = 10, PT = 8, PB = 20;

function xScale(samples) {
  const t0 = Date.parse(samples[0].ts);
  const t1 = Date.parse(samples[samples.length - 1].ts) || t0 + 1;
  return (ts) => PL + ((Date.parse(ts) - t0) / Math.max(1, t1 - t0)) * (W - PL - PR);
}

function fmtTime(ts) {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDateTime(ts) {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function fmtWindow(window) {
  if (!window.from || !window.to) return "";
  const from = new Date(window.from), to = new Date(window.to);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) return "";
  const end = from.toDateString() === to.toDateString() ? fmtTime(window.to) : fmtDateTime(window.to);
  return `${fmtDateTime(window.from)} – ${end}`;
}

function renderMem(samples) {
  if (!samples.length) { memEl.innerHTML = '<div class="muted">no samples</div>'; return; }
  const total = Math.max(...samples.map((s) => Number(s.mem_total_mib) || 0), 1);
  const x = xScale(samples);
  const y = (mib) => PT + (1 - mib / total) * (HM - PT - PB);
  // per-sample cumulative stacks in fixed series order
  const stacks = samples.map((s) => {
    const mem = seriesMem(s);
    let acc = 0;
    const bands = {};
    for (const sr of SERIES) { bands[sr.key] = [acc, acc + mem[sr.key]]; acc += mem[sr.key]; }
    return bands;
  });
  let svg = `<svg viewBox="0 0 ${W} ${HM}" preserveAspectRatio="none" data-kind="mem">`;
  // recessive grid + axis labels (quarters of the card total)
  for (let i = 0; i <= 4; i++) {
    const v = (total * i) / 4;
    svg += `<line x1="${PL}" y1="${y(v)}" x2="${W - PR}" y2="${y(v)}" stroke="#eef0f2" stroke-width="1"/>`
      + `<text x="${PL - 6}" y="${y(v) + 3}" text-anchor="end" font-size="9" fill="#6a6f75">${Math.round(v / 1024)}G</text>`;
  }
  // stacked bands, bottom-up, with a 2px surface gap between fills
  for (const sr of SERIES) {
    let top = "", bottom = "";
    samples.forEach((s, i) => {
      const [b0, b1] = stacks[i][sr.key];
      top += `${i ? "L" : "M"}${x(s.ts).toFixed(1)},${y(b1).toFixed(1)} `;
      bottom = `L${x(s.ts).toFixed(1)},${y(b0).toFixed(1)} ` + bottom;
    });
    svg += `<path d="${top}${bottom}Z" fill="${sr.color}" stroke="#ffffff" stroke-width="2" stroke-linejoin="round"/>`;
  }
  svg += `<line id="gpucross" x1="-9" y1="${PT}" x2="-9" y2="${HM - PB}" stroke="#6a6f75" stroke-width="1" stroke-dasharray="3 3"/>`;
  svg += `<text x="${W - PR}" y="${HM - 6}" text-anchor="end" font-size="9" fill="#6a6f75">${gesc(fmtTime(samples[samples.length - 1].ts))}</text>`;
  svg += `<text x="${PL}" y="${HM - 6}" font-size="9" fill="#6a6f75">${gesc(fmtTime(samples[0].ts))}</text>`;
  svg += "</svg>";
  const tip = tipEl.outerHTML;             // keep the tooltip node
  memEl.innerHTML = svg + tip;
  wireHover(memEl.querySelector("svg"), samples, stacks);
}

function renderUtil(samples) {
  if (!samples.length) { utilEl.innerHTML = ""; return; }
  const x = xScale(samples);
  const y = (pct) => PT + (1 - pct / 100) * (HU - PT - PB);
  let svg = `<svg viewBox="0 0 ${W} ${HU}" preserveAspectRatio="none">`;
  for (const v of [0, 50, 100]) {
    svg += `<line x1="${PL}" y1="${y(v)}" x2="${W - PR}" y2="${y(v)}" stroke="#eef0f2" stroke-width="1"/>`
      + `<text x="${PL - 6}" y="${y(v) + 3}" text-anchor="end" font-size="9" fill="#6a6f75">${v}%</text>`;
  }
  let d = "";
  samples.forEach((s, i) => {
    d += `${i ? "L" : "M"}${x(s.ts).toFixed(1)},${y(Number(s.gpu_util_pct) || 0).toFixed(1)} `;
  });
  svg += `<path d="${d}" fill="none" stroke="#1a1a1a" stroke-width="2" stroke-linejoin="round"/>`;
  svg += "</svg>";
  utilEl.innerHTML = svg;
}

function wireHover(svg, samples, stacks) {
  const tip = memEl.querySelector("#gputip");
  const cross = svg.querySelector("#gpucross");
  svg.addEventListener("mousemove", (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    const t0 = Date.parse(samples[0].ts);
    const t1 = Date.parse(samples[samples.length - 1].ts) || t0 + 1;
    const frac = Math.min(1, Math.max(0, (px - PL) / (W - PL - PR)));
    const target = t0 + frac * (t1 - t0);
    let best = 0, bd = Infinity;
    samples.forEach((s, i) => {
      const d = Math.abs(Date.parse(s.ts) - target);
      if (d < bd) { bd = d; best = i; }
    });
    const s = samples[best];
    const bands = stacks[best];
    cross.setAttribute("x1", ((Date.parse(s.ts) - t0) / Math.max(1, t1 - t0)) * (W - PL - PR) + PL);
    cross.setAttribute("x2", cross.getAttribute("x1"));
    const rows = SERIES.map((sr) => {
      const v = bands[sr.key][1] - bands[sr.key][0];
      return v > 0
        ? `<div class="tr"><span><span class="sw" style="background:${sr.color};width:8px;height:8px;display:inline-block;border-radius:2px;margin-right:5px"></span>${gesc(sr.label)}</span><b>${(v / 1024).toFixed(1)}G</b></div>`
        : "";
    }).join("");
    tip.innerHTML = `<div class="tt0">${gesc(fmtTime(s.ts))} · util ${gesc(s.gpu_util_pct)}% · ${(s.mem_used_mib / 1024).toFixed(1)}/${(s.mem_total_mib / 1024).toFixed(0)}G</div>${rows}`;
    tip.style.display = "block";
    const paneR = memEl.getBoundingClientRect();
    const tx = Math.min(ev.clientX - paneR.left + 14, paneR.width - tip.offsetWidth - 8);
    tip.style.left = `${Math.max(0, tx)}px`;
    tip.style.top = `${ev.clientY - paneR.top + 14}px`;
  });
  svg.addEventListener("mouseleave", () => {
    tip.style.display = "none";
    cross.setAttribute("x1", -9);
    cross.setAttribute("x2", -9);
  });
}

// Thor (Jetson) card — power line (the activity signal; Thor's tegrastats has
// no GPU-% field) over the shared time window, single axis, same idiom.
const thorCard = document.getElementById("gputhorcard");
const thorChartEl = document.getElementById("gputhorchart");
const thorTableEl = document.getElementById("gputhortable");

function renderThor(body) {
  if (!body) { thorCard.style.display = "none"; return; }
  const samples = body.samples || [];
  thorCard.style.display = "block";
  const thorTitle = document.getElementById("gputhortitle");
  if (thorTitle) {
    thorTitle.textContent = "Thor GPU power";
  }
  if (!samples.length) {
    thorChartEl.innerHTML = `<div class="muted">${gesc(body.error || "no samples")}</div>`;
    thorTableEl.innerHTML = "";
    return;
  }
  const x = xScale(samples);
  const watts = samples.map((s) => (Number(s.gpu_power_mw) || 0) / 1000);
  const maxW = Math.max(...watts, 1);
  const top = maxW <= 5 ? 5 : Math.ceil(maxW / 5) * 5; // stable 5 W grid steps
  const y = (w) => PT + (1 - w / top) * (HU - PT - PB);
  let svg = `<svg viewBox="0 0 ${W} ${HU}" preserveAspectRatio="none">`;
  for (const v of [0, top / 2, top]) {
    svg += `<line x1="${PL}" y1="${y(v)}" x2="${W - PR}" y2="${y(v)}" stroke="#eef0f2" stroke-width="1"/>`
      + `<text x="${PL - 6}" y="${y(v) + 3}" text-anchor="end" font-size="9" fill="#6a6f75">${v}W</text>`;
  }
  let d = "";
  samples.forEach((s, i) => {
    d += `${i ? "L" : "M"}${x(s.ts).toFixed(1)},${y(watts[i]).toFixed(1)} `;
  });
  svg += `<path d="${d}" fill="none" stroke="#76b900" stroke-width="2" stroke-linejoin="round"/>`;
  svg += `<text x="${W - PR}" y="${HU - 6}" text-anchor="end" font-size="9" fill="#6a6f75">${gesc(fmtTime(samples[samples.length - 1].ts))}</text>`;
  svg += "</svg>";
  thorChartEl.innerHTML = svg;
  const s = samples[samples.length - 1];
  const procRows = Object.entries(s.procs || {})
    .sort((a, b) => (b[1].mem_mib || 0) - (a[1].mem_mib || 0))
    .map(([role, p]) => {
      const pids = Array.isArray(p.pids) && p.pids.length ? p.pids : [p.pid];
      return `<tr><td class="name">${gesc(role)}</td><td>${gesc(pids.filter(Boolean).join(", "))}</td><td>${((p.mem_mib || 0) / 1024).toFixed(1)} GiB RSS</td></tr>`;
    })
    .join("");
  thorTableEl.innerHTML =
    `<details><summary>Process details</summary><table class="gpu-table"><tr><th>Workload</th><th>PID(s)</th><th>RAM</th></tr>${procRows}</table></details>`;
}

function renderLegend(samples) {
  const active = new Set(samples.flatMap((sample) => Object.entries(seriesMem(sample)).filter(([, value]) => value > 0).map(([key]) => key)));
  legendEl.innerHTML = SERIES.filter((series) => active.has(series.key)).map(
    (s) => `<span class="chip"><span class="sw" style="background:${s.color}"></span>${gesc(s.label)}</span>`,
  ).join("");
}

function renderTable(samples) {
  if (!samples.length) { tableEl.innerHTML = '<div class="muted">No samples</div>'; return; }
  const s = samples[samples.length - 1];
  const mem = seriesMem(s);
  const smAvailable = Boolean(s.per_process_sm_available ?? !s.unified);
  const rows = SERIES.filter((sr) => mem[sr.key] > 0).map((sr) => {
    const raw = s.procs?.[sr.key];
    const sm = raw && raw.sm_pct != null ? `${gesc(raw.sm_pct)}%` : "—";
    return `<tr><td class="name"><span class="sw" style="background:${sr.color};width:9px;height:9px;display:inline-block;border-radius:2px;margin-right:6px"></span>${gesc(sr.label)}</td>`
      + `<td>${(mem[sr.key] / 1024).toFixed(2)} GiB</td>${smAvailable ? `<td>${sm}</td>` : ""}</tr>`;
  }).join("");
  tableEl.innerHTML = `<table class="gpu-table"><tr><th>Process</th><th>${s.unified ? "RAM" : "GPU memory"}</th>${smAvailable ? "<th>Compute use</th>" : ""}</tr>${rows}</table>`;
}

async function loadGpu() {
  const scope = sessionId || `live-${rangeMin}`;
  if (gpuRequest && gpuRequestScope === scope) return;
  const generation = ++gpuGeneration;
  if (gpuRequest) gpuRequest.abort();
  const controller = new AbortController();
  gpuRequest = controller;
  gpuRequestScope = scope;
  updateSessionDetails();
  if (scope !== displayedScope) {
    displayedScope = scope;
    memEl.innerHTML = '<div class="muted">Loading GPU activity…</div>';
    utilEl.innerHTML = "";
    legendEl.innerHTML = "";
    tableEl.innerHTML = "";
    renderLive(null);
    renderThor(null);
    if (memoryNote) memoryNote.hidden = true;
  }
  if (scopeEl) scopeEl.textContent = sessionId ? `History · ${sessionTitle(sessionId)}` : `Live · Last ${rangeMin} minutes`;
  let body;
  try {
    const url = sessionId
      ? `/api/gpu?mission_id=${encodeURIComponent(sessionId)}`
      : `/api/gpu?minutes=${rangeMin}`;
    const [r] = await Promise.all([fetch(url, { signal: controller.signal }), loadSessions()]);
    if (!r.ok) throw new Error("GPU telemetry unavailable");
    body = await r.json();
    if (generation !== gpuGeneration) return;
  } catch (error) {
    if (generation !== gpuGeneration || error.name === "AbortError") return;
    memEl.innerHTML = '<div class="muted">GPU telemetry is unavailable. Check the connection.</div>';
    utilEl.innerHTML = "";
    legendEl.innerHTML = "";
    tableEl.innerHTML = "";
    renderLive(null);
    renderThor(null);
    if (memoryNote) memoryNote.hidden = true;
    return;
  } finally {
    if (generation === gpuGeneration) gpuRequest = null;
  }
  let latestReceived = null;
  if (!sessionId) {
    // Exporters may cap sample count instead of applying the requested time
    // range. Bound both measured streams before choosing the primary charts.
    const from = Date.now() - rangeMin * 60000;
    const recent = (samples) => (samples || []).filter((sample) => {
      const ts = Date.parse(sample.ts);
      if (Number.isFinite(ts) && (latestReceived === null || ts > latestReceived)) latestReceived = ts;
      return Number.isFinite(ts) && ts >= from;
    });
    body = {
      ...body,
      samples: recent(body.samples),
      ...(body.thor ? { thor: { ...body.thor, samples: recent(body.thor.samples) } } : {}),
    };
  }
  // A Thor-only deployment configures PGFR_GPU_URL_THOR without a workstation
  // exporter. Promote its measured stream into the main charts.
  const measuredThor = body.thor;
  if (!(body.samples || []).length && (measuredThor?.samples || []).length) {
    body = {
      ...measuredThor,
      mission_id: body.mission_id,
      telemetry_basis: body.telemetry_basis,
      window: body.window,
      thor: measuredThor,
    };
  }
  if (scopeEl) {
    const windowLabel = fmtWindow(body.window || {});
    scopeEl.textContent = sessionId
      ? `History · ${sessionTitle(sessionId)}${windowLabel ? ` · ${windowLabel}` : ""}`
      : `Live · Last ${rangeMin} minutes`;
  }
  if (body.error && !(body.samples || []).length) {
    memEl.innerHTML = `<div class="muted">${gesc(body.error)}${sessionId ? "" : " — check the GPU telemetry configuration"}</div>`;
    utilEl.innerHTML = "";
    legendEl.innerHTML = "";
    tableEl.innerHTML = '<div class="muted">No samples</div>';
    renderLive(null);
    renderThor(body.thor);
    if (memoryNote) memoryNote.hidden = true;
    return;
  }
  lastSamples = body.samples || [];
  // Choose memory labels from measured samples, not the machine name.
  const isThor = lastSamples.some((s) => s.unified);
  SERIES = isThor ? THOR_SERIES : WS_SERIES;
  KNOWN = new Set(SERIES.filter((s) => s.key !== "other").map((s) => s.key));
  const memTitle = document.getElementById("gpumemtitle");
  if (memTitle) memTitle.textContent = isThor ? "Thor memory usage" : "GPU memory usage";
  const utilTitle = document.getElementById("gputiltitle");
  if (utilTitle) utilTitle.textContent = "GPU utilization";
  const nowTitle = document.getElementById("gpunowtitle");
  if (nowTitle) nowTitle.textContent = "Latest sample";
  if (memoryNote) memoryNote.hidden = !isThor;
  renderLive(lastSamples[lastSamples.length - 1]);
  renderMem(lastSamples);
  renderUtil(lastSamples);
  const primaryPower = lastSamples.some((s) => s.gpu_power_mw != null);
  renderThor(body.thor || (primaryPower ? { samples: lastSamples } : null));
  renderLegend(lastSamples);
  renderTable(lastSamples);
  if (!sessionId && !lastSamples.length) {
    const previous = latestReceived === null ? "" : ` Last sample: ${fmtDateTime(latestReceived)}.`;
    memEl.innerHTML = `<div class="muted">No samples in the last ${rangeMin} minutes.${gesc(previous)}</div>`;
  }
}
