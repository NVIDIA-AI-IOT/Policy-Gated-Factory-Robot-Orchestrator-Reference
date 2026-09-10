// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { rememberSessions, sessionTitle, sessionDate, verificationSummary } from "./display.js?v=console-cleanup4";

// PGFR Console SPA — zero-dependency ES module (no build step, no CDN).
// Renders the declared topology as SVG with live status classes, a node
// detail panel, and mission replay from the audit store.

// Layered auto-layout: x by node.layer, y stacked within the layer (in node
// order). Computed from the topology so tools/endpoints/cameras all place
// automatically — no hand-tuned coordinates.
const COLW = 210, NODEW = 176, H = 52, GAPY = 20, MX = 26, MY = 24;
let POS = {};
let CANVAS = { w: 1200, h: 560 };
function layout(nodes) {
  const byLayer = {};
  for (const n of nodes) (byLayer[n.layer || 0] ||= []).push(n);
  const layers = Object.keys(byLayer).map(Number).sort((a, b) => a - b);
  const maxCount = Math.max(1, ...layers.map((l) => byLayer[l].length));
  CANVAS.h = MY * 2 + maxCount * (H + GAPY);
  CANVAS.w = MX * 2 + Math.max(1, layers.length) * COLW;
  POS = {};
  for (const [column, l] of layers.entries()) {
    const col = byLayer[l];
    const colH = col.length * (H + GAPY) - GAPY;
    let y = (CANVAS.h - colH) / 2;
    for (const n of col) {
      POS[n.id] = { x: MX + column * COLW, y, w: NODEW };
      y += H + GAPY;
    }
  }
}

const graphEl = document.getElementById("graph");
let topologyError = "";
const detailEl = document.getElementById("detail");
const missionsEl = document.getElementById("missions");
const opsEl = document.getElementById("ops");
const topoMain = document.getElementById("topo");
const tabTopo = document.getElementById("tab-topo");

tabTopo.onclick = () => {
  topoMain.style.display = "grid";
  tabTopo.classList.add("active");
};
const ACTIVE_SESSION_KEY = "pgfr_active_mission";

window.PGFRSession = {
  get() {
    return localStorage.getItem(ACTIVE_SESSION_KEY) || "";
  },
  set(missionId) {
    const id = String(missionId || "");
    if (id) localStorage.setItem(ACTIVE_SESSION_KEY, id);
    else localStorage.removeItem(ACTIVE_SESSION_KEY);
    window.dispatchEvent(new CustomEvent("pgfr-session-change", { detail: { mission_id: id } }));
  },
};

let topo = { nodes: [], edges: [] };
let selected = null;
let showDetails = localStorage.getItem("pgfr_topology_details") === "true";
let displayedNodes = [];

const severity = {down: 0, degraded: 1, unknown: 2, ok: 3};
function worstStatus(a, b) {
  const left = Object.hasOwn(severity, a) ? a : "unknown";
  const right = Object.hasOwn(severity, b) ? b : "unknown";
  return severity[left] <= severity[right] ? left : right;
}

// The overview groups capabilities and feeds while retaining their worst status.
// Expanding it restores the individual nodes returned by the API.
function visibleTopology() {
  const nodes = topo.nodes || [], edges = topo.edges || [];
  if (showDetails) return {nodes, edges};
  const cameras = nodes.filter((n) => n.kind === "camera");
  const cameraIds = new Set(cameras.map((n) => n.id));
  const tools = nodes.filter((n) => n.kind === "tool");
  const hidden = new Set(tools.map((n) => n.id));
  const groupId = "camera-feeds";
  const remap = (id) => cameraIds.has(id) ? groupId : id;
  const visible = nodes.filter((n) => !hidden.has(n.id) && !cameraIds.has(n.id)).map((n) => {
    if (n.id !== "mcp") return n;
    return {...n, status: tools.reduce((status, t) => worstStatus(status, t.status), n.status),
      detail: {...n.detail, tools: tools.map((t) => ({name: t.label, status: t.status}))}};
  });
  if (cameras.length) visible.push({id: groupId, label: `Cameras (${cameras.length})`, kind: "camera",
    layer: cameras[0].layer, status: cameras.reduce((status, c) => worstStatus(status, c.status), "ok"),
    detail: {status_basis: "Camera feed freshness", cameras: cameras.map((c) => ({name: c.label, status: c.status, ...c.detail}))}});
  const mapped = edges.map((e) => ({...e, source: remap(e.source), target: remap(e.target)}));
  const visibleIds = new Set(visible.map((n) => n.id));
  const merged = new Map();
  for (const edge of mapped) {
    if (!visibleIds.has(edge.source)) continue;
    const walk = (target, status, visited) => {
      if (visited.has(target)) return;
      if (visibleIds.has(target)) {
        if (edge.source === target) return;
        const key = `${edge.source}|${target}|${edge.label === "feed" ? "feed" : "control"}`;
        const prior = merged.get(key);
        merged.set(key, {...edge, id: key, target, status: prior ? worstStatus(prior.status, status) : status});
        return;
      }
      if (!hidden.has(target)) return;
      for (const next of mapped.filter((e) => e.source === target))
        walk(next.target, worstStatus(status, next.status), new Set([...visited, target]));
    };
    walk(edge.target, edge.status, new Set([edge.source]));
  }
  return {nodes: visible, edges: [...merged.values()]};
}

function center(id, side) {
  const p = POS[id];
  if (!p) return { x: 0, y: 0 };
  const cy = p.y + H / 2;
  return side === "left" ? { x: p.x, y: cy } : { x: p.x + p.w, y: cy };
}

const KIND_ICON = { agent: "◆", model: "◇", service: "▣", tool: "ƒ", sim: "◈",
                    endpoint: "⬢", camera: "▮", store: "▤" };

// keep labels inside the block; full name shown via <title> + the detail panel
function trunc(s, max) { return s.length > max ? s.slice(0, max - 1) + "…" : s; }

let vb = null;              // current viewBox {x,y,w,h} — pan/zoom state
let lastStructure = null;
let lastTopoSig = null;     // skip rebuild (and view reset) when nothing changed

function render() {
  const {nodes, edges} = visibleTopology();
  displayedNodes = nodes;
  if (selected && !nodes.some((n) => n.id === selected)) { selected = null; renderNodeDetails(); }
  layout(nodes);
  const structure = nodes.map((n) => n.id + ":" + n.layer).join("|");
  if (structure !== lastStructure) { vb = null; lastStructure = structure; }
  const sig = JSON.stringify([nodes.map((n) => [n.id, n.label, n.kind, n.status]), edges, selected, topologyError, showDetails]);
  if (sig === lastTopoSig && graphEl.querySelector("svg")) return;  // preserve zoom/pan
  lastTopoSig = sig;
  if (!vb) vb = { x: 0, y: 0, w: CANVAS.w, h: CANVAS.h };
  const p0 = (id) => POS[id];
  let svg = `<svg id="topo-svg" viewBox="${vb.x} ${vb.y} ${vb.w} ${vb.h}" preserveAspectRatio="xMidYMid meet">
    <defs><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0,0 L8,4 L0,8 z" fill="#9aa1a8"/></marker></defs>`;
  for (const e of edges) {
    const sp = p0(e.source), tp = p0(e.target);
    if (!sp || !tp) continue;
    const forward = tp.x >= sp.x;
    const a = forward ? { x: sp.x + sp.w, y: sp.y + H / 2 } : { x: sp.x, y: sp.y + H / 2 };
    const b = forward ? { x: tp.x - 6, y: tp.y + H / 2 } : { x: tp.x + tp.w + 6, y: tp.y + H / 2 };
    const dx = Math.max(30, Math.abs(b.x - a.x) * 0.45) * (forward ? 1 : -1);
    const cls = e.label === "feed" ? "edge feed " : "edge ";
    svg += `<path class="${cls}${esc(e.status)}" d="M${a.x},${a.y} C${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x},${b.y}"/>`;
  }
  for (const n of nodes) {
    const p = POS[n.id];
    if (!p) continue;
    const icon = KIND_ICON[n.kind] || "•";
    svg += `<g class="node ${esc(n.kind)}" data-id="${esc(n.id)}" role="button" tabindex="0" aria-label="${esc(n.label)}"><title>${esc(n.label)}</title>
      <rect class="${esc(n.status)}" x="${p.x}" y="${p.y}" width="${p.w}" height="${H}" rx="6"
            ${selected === n.id ? 'stroke-width="3"' : ""}/>
      <text class="ic" x="${p.x + 11}" y="${p.y + 21}">${icon}</text>
      <text x="${p.x + 26}" y="${p.y + 20}">${esc(trunc(n.label, 24))}</text>
      <text class="host" x="${p.x + 26}" y="${p.y + 36}">${esc(n.kind)} · ${esc(n.status)}</text>
    </g>`;
  }
  svg += "</svg>";
  graphEl.innerHTML =
    `<div id="error" role="status">${esc(topologyError)}</div>` +
    `<label class="topology-options"><input id="topology-details" type="checkbox" ${showDetails ? "checked" : ""}> Show tools and cameras</label>` +
    `<div id="zoomctl"><button data-z="in">+</button><button data-z="out">−</button><button data-z="fit">fit</button></div>` +
    svg;
  for (const g of graphEl.querySelectorAll(".node")) {
    g.addEventListener("click", () => select(g.dataset.id));
    g.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(g.dataset.id); }
    });
  }
  document.getElementById("topology-details").onchange = (event) => {
    showDetails = event.target.checked;
    localStorage.setItem("pgfr_topology_details", String(showDetails));
    vb = null; render(); renderNodeDetails();
    document.getElementById("topology-details").focus();
  };
  wirePanZoom();
}

function fitView() { vb = { x: 0, y: 0, w: CANVAS.w, h: CANVAS.h }; applyVB(); }
function applyVB() {
  const s = document.getElementById("topo-svg");
  if (s) s.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
}
function zoomAt(factor, cx, cy) {
  // cx,cy in svg coords; keep that point fixed while scaling
  const nw = Math.min(CANVAS.w * 2.5, Math.max(CANVAS.w * 0.25, vb.w * factor));
  const nh = nw * (vb.h / vb.w);
  vb.x = cx - (cx - vb.x) * (nw / vb.w);
  vb.y = cy - (cy - vb.y) * (nh / vb.h);
  vb.w = nw; vb.h = nh;
  applyVB();
}
function wirePanZoom() {
  const svg = document.getElementById("topo-svg");
  if (!svg) return;
  const toSvg = (ev) => {
    const r = svg.getBoundingClientRect();
    return { x: vb.x + ((ev.clientX - r.left) / r.width) * vb.w,
             y: vb.y + ((ev.clientY - r.top) / r.height) * vb.h };
  };
  svg.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const p = toSvg(ev);
    zoomAt(ev.deltaY > 0 ? 1.12 : 0.89, p.x, p.y);
  }, { passive: false });
  let drag = null;
  svg.addEventListener("pointerdown", (ev) => {
    if (ev.target.closest(".node")) return;   // let node clicks through
    drag = { x: ev.clientX, y: ev.clientY };
    svg.setPointerCapture(ev.pointerId); svg.style.cursor = "grabbing";
  });
  svg.addEventListener("pointermove", (ev) => {
    if (!drag) return;
    const r = svg.getBoundingClientRect();
    vb.x -= ((ev.clientX - drag.x) / r.width) * vb.w;
    vb.y -= ((ev.clientY - drag.y) / r.height) * vb.h;
    drag = { x: ev.clientX, y: ev.clientY };
    applyVB();
  });
  const end = () => { drag = null; svg.style.cursor = "grab"; };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointerleave", end);
  svg.style.cursor = "grab";
  for (const b of graphEl.querySelectorAll("#zoomctl button")) {
    b.onclick = () => {
      const z = b.dataset.z;
      if (z === "fit") return fitView();
      zoomAt(z === "in" ? 0.8 : 1.25, vb.x + vb.w / 2, vb.y + vb.h / 2);
    };
  }
}

// Every value rendered into innerHTML below originates from client-settable
// journal fields (x-mission-id is unauthenticated, journaled verbatim). Escape
// unconditionally — an unescaped mission id is a stored-XSS -> robot-motion path.
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

const STATUSES = new Set(["ok", "degraded", "down", "unknown"]);
function badge(status) {
  const s = STATUSES.has(status) ? status : "unknown";
  return `<span class="badge b-${s}">${s}</span>`;
}

function renderNodeDetails() {
  const n = displayedNodes.find((x) => x.id === selected);
  if (!n) {
    detailEl.innerHTML = '<h2>System map</h2><p class="sidebar-note">Select a component to see its status.</p>';
    return;
  }
  const d = n.detail || {};
  const detailsOpen = detailEl.querySelector("details")?.open && detailEl.dataset.node === n.id;
  detailEl.dataset.node = n.id;
  const summary = d.status_basis || d.note || "";
  detailEl.innerHTML = `<h2>${esc(n.label)}</h2>
    <div class="component-status">${badge(n.status)}</div>
    ${summary ? `<p class="sidebar-note">${esc(summary)}</p>` : ""}
    ${d.model_ids?.length ? `<p class="component-model">${esc(d.model_ids.join(", "))}</p>` : ""}
    <details class="technical-details" ${detailsOpen ? "open" : ""}><summary>Technical details</summary>
      <pre>${esc(JSON.stringify(d, null, 2))}</pre></details>`;
}

function select(id) {
  selected = id;
  render();
  renderNodeDetails();
}

async function pollTopology() {
  try {
    const r = await fetch("/api/topology");
    if (!r.ok) throw new Error("Topology unavailable");
    topo = await r.json();
    topologyError = "";
  } catch {
    topologyError = "System status is unavailable. Retrying…";
  }
  render();
  renderNodeDetails();
}

const missionRecords = new Map();

async function pollMissions() {
  try {
    const [missionResult, chatResult] = await Promise.allSettled([
      fetch("/api/missions?limit=15").then((r) => r.json()),
      fetch("/api/chat-sessions").then((r) => r.json()),
    ]);
    if (missionResult.status === "rejected") throw missionResult.reason;
    if (chatResult.status === "fulfilled") rememberSessions(chatResult.value.sessions || []);
    const body = missionResult.value;
    const missions = body.missions || [];
    for (const mission of missions) missionRecords.set(mission.mission_id || mission.id, mission);
    if (!missions.length) {
      missionsEl.innerHTML = `<div class="muted">${esc(body.error || "No missions yet.")}</div>`;
      return;
    }
    missionsEl.innerHTML = missions
      .map((m) => {
        const id = m.mission_id || m.id || "?";
        const active = id === window.PGFRSession.get() ? " active" : "";
        const okN = m.verified_dispatches;
        const totalN = m.dispatches;
        const measured = typeof okN === "number" && typeof totalN === "number";
        // Three outcomes — a partial failure must NOT masquerade as calm "unknown":
        // all verified -> ok; none -> down; some held -> degraded; no verdict data -> unknown.
        let status = "unknown";
        if (measured && totalN > 0)
          status = okN === totalN ? "ok" : okN === 0 ? "down" : "degraded";
        const summary = [sessionDate(m), verificationSummary(okN, totalN)].filter(Boolean).join(" · ");
        const reason = totalN === 0 && m.last_reason
          ? `<div class="muted mission-note">${esc(trunc(String(m.last_reason), 160))}</div>` : "";
        return `<div class="mission${active}" role="button" tabindex="0" data-id="${esc(id)}">
          <strong>${esc(sessionTitle(m))}</strong> ${badge(status)}
          <div class="muted">${esc(summary)}</div>${reason}</div>`;
      })
      .join("");
    for (const el of missionsEl.querySelectorAll(".mission")) {
      el.addEventListener("click", () => showMission(el.dataset.id));
      el.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          showMission(el.dataset.id);
        }
      });
    }
  } catch {
    missionsEl.innerHTML = '<div class="muted">console API unreachable</div>';
  }
}

async function showMission(id) {
  window.PGFRSession.set(id);
  for (const el of missionsEl.querySelectorAll(".mission"))
    el.classList.toggle("active", el.dataset.id === id);
  let body;
  try {
    const r = await fetch(`/api/missions/${encodeURIComponent(id)}`);
    if (!r.ok) throw new Error("Mission unavailable");
    body = await r.json();
  } catch {
    opsEl.textContent = "Could not load this task. Try again.";
    return;
  }
  if (window.PGFRSession.get() !== id) return;
  const ops = body.operations || [];
  const mission = missionRecords.get(id) || { mission_id: id, started_at: ops[0]?.ts };
  opsEl.innerHTML =
    `<h2>${esc(sessionTitle(mission))}</h2>
     <details class="technical-details"><summary>Session ID</summary><code>${esc(id)}</code></details>` +
    (ops.length
      ? ops
          .map((op) => {
            const verified = op.verified === true;
            const cls = verified ? "verified" : op.verified === false ? "failed" : "";
            const what = op.action || op.op || "op";
            return `<div class="op ${cls}"><strong>${esc(what)}</strong>
              ${verified ? badge("ok") : op.verified === false ? badge("down") : badge("unknown")}
              <div class="muted">${esc(op.reason || "")}</div></div>`;
          })
          .join("")
      : '<div class="muted">no operations recorded</div>');
}

pollTopology();
pollMissions();
setInterval(pollTopology, 2000);
setInterval(pollMissions, 5000);
