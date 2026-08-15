// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// GPU tab — per-model GPU load over time, from the read-only exporter proxy.
// Hand-rolled SVG, no deps. Two single-axis charts (never dual-axis): a
// stacked memory area per model against the card total, and a whole-GPU
// utilization strip. Fixed series order + fixed categorical palette
// (validated: adjacent-pair CVD ΔE ≥ 8, normal ≥ 15; three low-contrast
// slots are relieved by the legend, tooltip, and the Now table).

function gesc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

const gpuMain = document.getElementById("gpu");
const tabGpu = document.getElementById("tab-gpu");
const gTabIds = ["tab-topo", "tab-wf", "tab-chat", "tab-inspect"];
const gMainIds = ["topo", "builder", "chat", "inspect"];
const gTabs = gTabIds.map((id) => document.getElementById(id));
const gMains = gMainIds.map((id) => document.getElementById(id));

let gpuTimer = null;
tabGpu.onclick = () => {
  for (const m of gMains) m.style.display = "none";
  gpuMain.style.display = "grid";
  for (const b of gTabs) b.classList.remove("active");
  tabGpu.classList.add("active");
  const active = window.ICSession ? window.ICSession.get() : "";
  if (active) sessionId = active;
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
  { key: "other", label: "Other (training / router / cert)", color: "#e34948" },
];
const THOR_SERIES = [
  { key: "cosmos-reason-vlm", label: "Cosmos Reason VLM", color: "#76b900" },
  { key: "cosmos-edge-vlm", label: "Cosmos3 Edge VLM", color: "#008300" },
  { key: "nemotron-vlm", label: "Nemotron VLM", color: "#e87ba4" },
  { key: "vllm-server", label: "Other vLLM server", color: "#8c6bb1" },
  { key: "legacy-vlm", label: "Legacy VLM (mixed)", color: "#8090a0" },
  { key: "openclaw-gateway", label: "OpenClaw gateway (brain)", color: "#2a78d6" },
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
  `<select id="gpusession" style="margin-left:auto;font:inherit;font-size:11px;border:1px solid var(--line);border-radius:14px;padding:3px 10px;background:#fff;color:var(--muted)">
     <option value="">live view — pick a session…</option></select>`;
for (const b of rangeEl.querySelectorAll("button")) {
  b.onclick = () => {
    sessionId = null;
    if (window.ICSession) window.ICSession.set("");
    document.getElementById("gpusession").value = "";
    rangeMin = Number(b.dataset.min);
    for (const x of rangeEl.querySelectorAll("button")) x.classList.toggle("active", x === b);
    loadGpu();
  };
}
document.getElementById("gpusession").onchange = (ev) => {
  sessionId = ev.target.value || null;
  if (window.ICSession) window.ICSession.set(sessionId || "");
  for (const x of rangeEl.querySelectorAll("button")) x.classList.remove("active");
  if (!sessionId) {
    rangeMin = 60;
    rangeEl.querySelector('button[data-min="60"]').classList.add("active");
  }
  loadGpu();
};

async function loadSessions() {
  try {
    const [chatResponse, missionResponse] = await Promise.all([
      fetch("/api/chat-sessions"),
      fetch("/api/missions?limit=15"),
    ]);
    const chatBody = await chatResponse.json();
    const missionBody = await missionResponse.json();
    const sel = document.getElementById("gpusession");
    const current = sessionId || sel.value;
    const combined = [...(chatBody.sessions || []), ...(missionBody.missions || [])];
    const seen = new Set();
    const missions = combined.filter((m) => {
      const id = m.mission_id || m.id || "";
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
    const known = new Set(missions.map((m) => m.mission_id || m.id || ""));
    sel.innerHTML =
      '<option value="">live view — pick a session…</option>' +
      (sessionId && !known.has(sessionId)
        ? `<option value="${gesc(sessionId)}">${gesc(sessionId)}</option>`
        : "") +
      missions
        .map((m) => {
          const id = m.mission_id || m.id || "";
          return id ? `<option value="${gesc(id)}">${gesc(id)}</option>` : "";
        })
        .join("");
    sel.value = current;
  } catch {
    /* selector just stays as-is */
  }
}

const memEl = document.getElementById("gpumemchart");
const utilEl = document.getElementById("gputilchart");
const legendEl = document.getElementById("gpulegend");
const tableEl = document.getElementById("gputable");
const tipEl = document.getElementById("gputip");
const scopeEl = document.getElementById("gpuscope");
const liveEl = document.getElementById("gpulive");

let lastSamples = [];

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
  liveEl.innerHTML = [
    ["GPU utilization", `${Number(sample.gpu_util_pct) || 0}%`],
    [unified ? "GPU memory" : "GPU memory used", gpuMem],
    ["System RAM", `${(ramUsed / 1024).toFixed(1)} / ${(ramTotal / 1024).toFixed(1)} GiB · ${pct(ramUsed, ramTotal)}%`],
    ["GPU power", power],
    ["Freshness", `${age}s ago`],
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
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
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
  const thorHost = samples.length ? samples[samples.length - 1].host : null;
  if (thorTitle) {
    thorTitle.textContent = `${thorHost || "Thor"} · Jetson brain — GPU power (W), unified RAM`;
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
    `<table class="gpu-table"><tr><th>workload</th><th>PID(s)</th><th>memory (unified)</th></tr>${procRows}</table>`
    + `<div class="muted" style="margin-top:6px;font-size:11px">sampled ${gesc(fmtTime(s.ts))}`
    + ` · GPU ${((Number(s.gpu_power_mw) || 0) / 1000).toFixed(1)} W · util ${gesc(s.gpu_util_pct)}%`
    + ` · unified RAM ${(s.mem_used_mib / 1024).toFixed(0)}/${(s.mem_total_mib / 1024).toFixed(0)} GiB</div>`;
}

function renderLegend() {
  legendEl.innerHTML = SERIES.map(
    (s) => `<span class="chip"><span class="sw" style="background:${s.color}"></span>${gesc(s.label)}</span>`,
  ).join("");
}

function renderTable(samples) {
  if (!samples.length) { tableEl.innerHTML = '<div class="muted">no samples</div>'; return; }
  const s = samples[samples.length - 1];
  const mem = seriesMem(s);
  const rows = SERIES.filter((sr) => mem[sr.key] > 0).map((sr) => {
    const raw = s.procs?.[sr.key];
    const smAvailable = Boolean(s.per_process_sm_available ?? !s.unified);
    const sm = raw && smAvailable && raw.sm_pct != null ? `${gesc(raw.sm_pct)}%` : "—";
    return `<tr><td class="name"><span class="sw" style="background:${sr.color};width:9px;height:9px;display:inline-block;border-radius:2px;margin-right:6px"></span>${gesc(sr.label)}</td>`
      + `<td>${(mem[sr.key] / 1024).toFixed(2)} GiB</td><td>${sm}</td></tr>`;
  }).join("");
  tableEl.innerHTML = `<table class="gpu-table"><tr><th>process</th><th>memory</th><th>SM</th></tr>${rows}</table>`
    + `<div class="muted" style="margin-top:6px;font-size:11px">sampled ${gesc(fmtTime(s.ts))} · whole GPU ${(s.mem_used_mib / 1024).toFixed(1)}/${(s.mem_total_mib / 1024).toFixed(0)} GiB · util ${gesc(s.gpu_util_pct)}%${s.unified ? " · per-process SM unavailable on Thor; process memory is RSS attribution" : ""}</div>`;
}

async function loadGpu() {
  let body;
  try {
    const url = sessionId
      ? `/api/gpu?mission_id=${encodeURIComponent(sessionId)}`
      : `/api/gpu?minutes=${rangeMin}`;
    const r = await fetch(url);
    body = await r.json();
  } catch {
    memEl.innerHTML = '<div class="muted">console API unreachable</div>';
    renderLive(null);
    return;
  }
  // A Thor-only deployment configures IC_GPU_URL_THOR without a workstation
  // exporter. Promote that measured stream into the main charts instead of
  // showing an empty primary pane and hiding all live data in a sub-card.
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
    const w = body.window || {};
    const from = w.from ? fmtTime(w.from) : "";
    const to = w.to ? fmtTime(w.to) : "";
    scopeEl.textContent = sessionId
      ? `session ${sessionId}${from && to ? ` · ${from} → ${to}` : ""} · ${body.telemetry_basis === "chat-session" ? "IC Chat activity window" : "journaled floor-operation window"}`
      : `live telemetry · last ${rangeMin} minutes`;
  }
  loadSessions();
  if (body.error && !(body.samples || []).length) {
    memEl.innerHTML = `<div class="muted">${gesc(body.error)}${sessionId ? "" : " — set IC_GPU_URL to the exporter (ops/ic_gpu_exporter.py :8601 on the serving host)"}</div>`;
    utilEl.innerHTML = "";
    tableEl.innerHTML = '<div class="muted">unknown</div>';
    renderLive(null);
    renderThor(body.thor); // Thor is measured independently; one host down must not blank the other
    return;
  }
  lastSamples = body.samples || [];
  // Host identity and series set come from the measured samples themselves
  // (unified=true marks the Jetson/Thor probe), never asserted.
  const isThor = lastSamples.some((s) => s.unified);
  SERIES = isThor ? THOR_SERIES : WS_SERIES;
  KNOWN = new Set(SERIES.filter((s) => s.key !== "other").map((s) => s.key));
  const host = lastSamples.length ? lastSamples[lastSamples.length - 1].host : null;
  const hostLabel = host
    ? `${host} · ${isThor ? "Thor (Jetson brain)" : "workstation"}`
    : "…";
  const memKind = isThor ? "Unified RAM by process (MiB)" : "GPU memory by model (MiB)";
  const memTitle = document.getElementById("gpumemtitle");
  if (memTitle) {
    memTitle.textContent = sessionId
      ? `${memKind} — ${hostLabel} — session ${sessionId}`
      : `${memKind} — ${hostLabel}`;
  }
  const utilTitle = document.getElementById("gputiltitle");
  if (utilTitle) utilTitle.textContent = `GPU utilization (%) — ${hostLabel}`;
  const nowTitle = document.getElementById("gpunowtitle");
  if (nowTitle) nowTitle.textContent = `Now — ${hostLabel}`;
  renderLive(lastSamples[lastSamples.length - 1]);
  renderMem(lastSamples);
  renderUtil(lastSamples);
  // Power card: from the secondary exporter if configured, else from the
  // primary samples themselves when they carry the Jetson power signal.
  const primaryPower = lastSamples.some((s) => s.gpu_power_mw != null);
  renderThor(body.thor || (primaryPower ? { samples: lastSamples } : null));
  renderLegend();
  renderTable(lastSamples);
}
