// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// PGFR Console SPA — zero-dependency ES module (no build step, no CDN).
// Renders the declared topology as SVG with live status classes, a node
// detail panel, and mission replay from the audit store.

// Layered auto-layout: x by node.layer, y stacked within the layer (in node
// order). Computed from the topology so tools/endpoints/cameras all place
// automatically — no hand-tuned coordinates.
const COLW = 224, NODEW = 150, H = 46, GAPY = 20, MX = 26, MY = 24;
let POS = {};
let CANVAS = { w: 1200, h: 560 };
function layout(nodes) {
  const byLayer = {};
  for (const n of nodes) (byLayer[n.layer || 0] ||= []).push(n);
  const layers = Object.keys(byLayer).map(Number).sort((a, b) => a - b);
  const maxCount = Math.max(1, ...layers.map((l) => byLayer[l].length));
  CANVAS.h = MY * 2 + maxCount * (H + GAPY);
  CANVAS.w = MX * 2 + (Math.max(...layers) + 1) * COLW;
  POS = {};
  for (const l of layers) {
    const col = byLayer[l];
    const colH = col.length * (H + GAPY) - GAPY;
    let y = (CANVAS.h - colH) / 2;
    for (const n of col) {
      POS[n.id] = { x: MX + l * COLW, y, w: NODEW };
      y += H + GAPY;
    }
  }
}

const graphEl = document.getElementById("graph");
const errEl = document.getElementById("error");
const detailEl = document.getElementById("detail");
const missionsEl = document.getElementById("missions");
const opsEl = document.getElementById("ops");
const stampEl = document.getElementById("stamp");
const activeSessionEl = document.getElementById("active-session");
const ACTIVE_SESSION_KEY = "pgfr_active_mission";

function renderActiveSession(missionId) {
  if (activeSessionEl)
    activeSessionEl.textContent = missionId ? `session: ${missionId}` : "session: live";
}

window.PGFRSession = {
  get() {
    return localStorage.getItem(ACTIVE_SESSION_KEY) || "";
  },
  set(missionId) {
    const id = String(missionId || "");
    if (id) localStorage.setItem(ACTIVE_SESSION_KEY, id);
    else localStorage.removeItem(ACTIVE_SESSION_KEY);
    renderActiveSession(id);
    window.dispatchEvent(new CustomEvent("pgfr-session-change", { detail: { mission_id: id } }));
  },
};
renderActiveSession(window.PGFRSession.get());

let topo = { nodes: [], edges: [] };
let selected = null;

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
let lastTopoSig = null;     // skip rebuild (and view reset) when nothing changed

function render() {
  const nodes = topo.nodes || [];
  const edges = topo.edges || [];
  layout(nodes);
  const sig = nodes.map((n) => n.id + n.status).join("|") + "#" + selected;
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
    svg += `<g class="node ${esc(n.kind)}" data-id="${esc(n.id)}"><title>${esc(n.label)}</title>
      <rect class="${esc(n.status)}" x="${p.x}" y="${p.y}" width="${p.w}" height="${H}" rx="6"
            ${selected === n.id ? 'stroke-width="3"' : ""}/>
      <text class="ic" x="${p.x + 11}" y="${p.y + 21}">${icon}</text>
      <text x="${p.x + 26}" y="${p.y + 20}">${esc(trunc(n.label, 18))}</text>
      <text class="host" x="${p.x + 26}" y="${p.y + 36}">${esc(n.kind)} · ${esc(n.status)}</text>
    </g>`;
  }
  svg += "</svg>";
  graphEl.innerHTML =
    `<div id="error">${errEl.textContent || ""}</div>` +
    `<div id="zoomctl"><button data-z="in">+</button><button data-z="out">−</button><button data-z="fit">fit</button></div>` +
    svg;
  for (const g of graphEl.querySelectorAll(".node"))
    g.addEventListener("click", () => select(g.dataset.id));
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

function select(id) {
  selected = id;
  const n = (topo.nodes || []).find((x) => x.id === id);
  if (!n) return;
  detailEl.innerHTML = `<h2>Node</h2>
    <div><strong>${esc(n.label)}</strong> ${badge(n.status)}</div>
    <div class="muted">${esc(n.kind)} · ${esc(n.host || "?")}</div>
    <pre>${esc(JSON.stringify(n.detail || {}, null, 1))}</pre>`;
  render();
}

async function pollTopology() {
  try {
    const r = await fetch("/api/topology");
    topo = await r.json();
    errEl.textContent = "";
    stampEl.textContent = topo.generated_at ? `updated ${topo.generated_at.slice(11, 19)}Z` : "";
  } catch {
    errEl.textContent = "console API unreachable";
  }
  render();
  if (selected) select(selected);
}

async function pollMissions() {
  try {
    const r = await fetch("/api/missions?limit=15");
    const body = await r.json();
    const missions = body.missions || [];
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
        return `<div class="mission${active}" data-id="${esc(id)}">
          <strong>${esc(id)}</strong> ${badge(status)}
          <div class="muted">verified ${esc(measured ? okN : "?")}/${esc(measured ? totalN : "?")} dispatches</div></div>`;
      })
      .join("");
    for (const el of missionsEl.querySelectorAll(".mission")) {
      el.addEventListener("click", () => showMission(el.dataset.id));
    }
  } catch {
    missionsEl.innerHTML = '<div class="muted">console API unreachable</div>';
  }
}

async function showMission(id) {
  window.PGFRSession.set(id);
  const r = await fetch(`/api/missions/${encodeURIComponent(id)}`);
  const body = await r.json();
  const ops = body.operations || [];
  opsEl.innerHTML =
    `<h2>Mission ${esc(id)}</h2>` +
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
