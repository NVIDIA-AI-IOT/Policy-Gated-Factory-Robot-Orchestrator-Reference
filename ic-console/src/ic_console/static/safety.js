// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Safety tab — safety + auditability visualized the way industry does it:
//  · IEC 61508 / ISO 26262 safety interlock chain (fail-closed)
//  · SPC control chart for in-spec placement vs tolerance
//  · GSN assurance case (claim -> mechanism -> evidence)
//  · 21 CFR Part 11 / SOC 2 records-integrity coverage
// All figures are derived from the audit store (read-only), never asserted.
// Every value is escaped before innerHTML (same guarantee as the rest).

function sesc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

const safetyMain = document.getElementById("safety");
const tabSafety = document.getElementById("tab-safety");
// this file loads last, so it hides every other view and every other tab hides it
const sTabIds = ["tab-topo", "tab-wf", "tab-chat", "tab-inspect"];
const sMainIds = ["topo", "builder", "chat", "inspect"];
const sTabs = sTabIds.map((id) => document.getElementById(id));
const sMains = sMainIds.map((id) => document.getElementById(id));

let safetyTimer = null;
tabSafety.onclick = () => {
  for (const m of sMains) m.style.display = "none";
  safetyMain.style.display = "grid";
  for (const b of sTabs) b.classList.remove("active");
  tabSafety.classList.add("active");
  loadSafety();
  if (safetyTimer) clearInterval(safetyTimer);
  safetyTimer = setInterval(() => {
    if (safetyMain.style.display !== "none") loadSafety();
  }, 5000);
};
for (const b of sTabs) {
  const prev = b.onclick;
  b.onclick = (e) => {
    safetyMain.style.display = "none";
    tabSafety.classList.remove("active");
    if (safetyTimer) { clearInterval(safetyTimer); safetyTimer = null; }
    if (prev) prev(e);
  };
}

const pct = (num, den) => (den ? Math.round((num / den) * 100) : 0);
const mm = (m) => (m == null ? null : m * 1000);

async function loadSafety() {
  let d;
  try {
    const r = await fetch("/api/safety");
    d = await r.json();
  } catch {
    document.getElementById("safetyclaim").innerHTML =
      `<div class="claimbar hold"><div class="ct"><div class="cc">console API unreachable</div></div></div>`;
    return;
  }
  renderClaim(d);
  renderGate(d.gate || {});
  renderSPC(d.placement || []);
  renderGuarantees(d.gate || {}, d.coverage || {}, d.guarantees || []);
  renderCoverage(d.coverage || {});
}

// ---- top claim (GSN goal) with the live verification rate --------------
function renderClaim(d) {
  const g = d.gate || {};
  const rate = g.verified_rate;
  const held = g.unverified || 0;
  const hasData = g.dispatches > 0;
  const ratePct = rate == null ? "—" : Math.round(rate * 100) + "%";
  const cls = held > 0 ? "claimbar hold" : "claimbar";
  document.getElementById("safetyclaim").innerHTML = `
    <div class="${cls}">
      <div class="ct">
        <div class="cl">Top safety claim (G1)</div>
        <div class="cc">No physical action is reported complete unless the cell re-measured the world and it passed.</div>
        <div class="cx">${hasData
          ? sesc(g.physics_verified) + " of " + sesc(g.dispatches) + " dispatches physics-verified · "
            + sesc(held) + " held (fail-closed, never reported done)"
          : "no dispatches in the recent audit window"}</div>
      </div>
      <div class="cring"><b>${sesc(ratePct)}</b><span>verified rate</span></div>
    </div>`;
}

// ---- interlock chain (functional-safety idiom, fail-closed) ------------
function renderGate(g) {
  const N = g.dispatches || 0;
  const a = g.agent_class_ok || 0;
  const refused = g.operator_refused || 0;
  const v = g.physics_verified || 0;
  const held = g.unverified || 0;
  // geometry
  const W = 900, H = 220, boxW = 150, boxH = 66;
  const cy = 84;
  const xs = [30, 250, 470, 700];
  const box = (x, title, sub, cls) => `
    <rect x="${x}" y="${cy}" width="${boxW}" height="${boxH}" rx="8"
          fill="#fff" stroke="${cls}" stroke-width="2"/>
    <text x="${x + boxW / 2}" y="${cy + 25}" text-anchor="middle"
          font-size="12" font-weight="700" fill="#1a1a1a">${sesc(title)}</text>
    <text x="${x + boxW / 2}" y="${cy + 45}" text-anchor="middle"
          font-size="11" fill="#6a6f75">${sesc(sub)}</text>`;
  const arrow = (x1, x2, label, col) => `
    <line x1="${x1}" y1="${cy + boxH / 2}" x2="${x2}" y2="${cy + boxH / 2}"
          stroke="${col}" stroke-width="2" marker-end="url(#sarrow)"/>
    <text x="${(x1 + x2) / 2}" y="${cy + boxH / 2 - 8}" text-anchor="middle"
          font-size="10" fill="#6a6f75">${sesc(label)}</text>`;
  const GREEN = "#76b900", AMBER = "#b8860b", GRAY = "#b7bbc0";
  const heldCol = held > 0 ? AMBER : GRAY;
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    <defs><marker id="sarrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0,0 L8,4 L0,8 z" fill="#9aa1a8"/></marker></defs>
    <text x="${xs[0]}" y="${cy - 14}" font-size="10" font-weight="700" fill="#6a6f75">REQUEST</text>
    ${box(xs[0], "Dispatch", N + " requested", GRAY)}
    ${arrow(xs[0] + boxW, xs[1], "agent-class?", GREEN)}
    <text x="${xs[1]}" y="${cy - 14}" font-size="10" font-weight="700" fill="#6a6f75">INTERLOCK A · POLICY</text>
    ${box(xs[1], "Action allowed", a + " ok · " + refused + " refused", refused > 0 ? AMBER : GREEN)}
    ${arrow(xs[1] + boxW, xs[2], "re-measured?", GREEN)}
    <text x="${xs[2]}" y="${cy - 14}" font-size="10" font-weight="700" fill="#6a6f75">INTERLOCK B · PHYSICS</text>
    ${box(xs[2], "Verify in world", v + " passed", GREEN)}
    ${arrow(xs[2] + boxW, xs[3], "both satisfied", GREEN)}
    <text x="${xs[3]}" y="${cy - 14}" font-size="10" font-weight="700" fill="#5a8c00">OUTCOME</text>
    ${box(xs[3], "Reported done", v + " verified", GREEN)}
    <!-- fail-closed drop for held actions -->
    <line x1="${xs[2] + boxW / 2}" y1="${cy + boxH}" x2="${xs[2] + boxW / 2}" y2="${cy + boxH + 34}"
          stroke="${heldCol}" stroke-width="2" marker-end="url(#sarrow)"/>
    <rect x="${xs[2] + boxW / 2 - 70}" y="${cy + boxH + 34}" width="140" height="30" rx="6"
          fill="#fff" stroke="${heldCol}" stroke-width="2"/>
    <text x="${xs[2] + boxW / 2}" y="${cy + boxH + 54}" text-anchor="middle"
          font-size="11" font-weight="700" fill="${held > 0 ? AMBER : GRAY}">HELD ${held} · fail-closed</text>
  </svg>`;
  document.getElementById("safetygate").innerHTML = svg;
}

// ---- SPC control chart for placement offset vs tolerance ---------------
function renderSPC(placement) {
  const el = document.getElementById("safetyspc");
  const pts = placement.filter((p) => p.offset_m != null && p.tolerance_m != null);
  if (!pts.length) {
    el.innerHTML = `<div class="muted" style="padding:14px;background:#fff;border:1px solid var(--line);border-radius:10px">No measured placements in the recent audit window.</div>`;
    return;
  }
  const W = 900, H = 260, ml = 54, mr = 20, mt = 26, mb = 44;
  const iw = W - ml - mr, ih = H - mt - mb;
  const offs = pts.map((p) => mm(p.offset_m));
  const tol = mm(pts[0].tolerance_m);                    // success specification limit
  const ymax = Math.max(tol * 1.35, ...offs) * 1.08 || 1;
  const x = (i) => ml + (pts.length === 1 ? iw / 2 : (i / (pts.length - 1)) * iw);
  const y = (v) => mt + ih - (v / ymax) * ih;
  // held/out-of-spec uses AMBER to match the interlock chain + claim bar (one
  // meaning for "held, never reported done" across the whole tab).
  const GREEN = "#76b900", AMBER = "#b8860b";
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">`;
  // in-chart legend — pass/fail is NOT conveyed by colour alone (WCAG 1.4.1)
  svg += `<circle cx="${ml + 6}" cy="12" r="4" fill="${GREEN}"/>
          <text x="${ml + 15}" y="15" font-size="10" fill="#6a6f75">in spec</text>
          <text x="${ml + 78}" y="16" font-size="12" fill="${AMBER}" font-weight="700">✕</text>
          <text x="${ml + 90}" y="15" font-size="10" fill="#6a6f75">held (out of spec)</text>`;
  // axes
  svg += `<line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt + ih}" stroke="#d0d3d7"/>
          <line x1="${ml}" y1="${mt + ih}" x2="${ml + iw}" y2="${mt + ih}" stroke="#d0d3d7"/>`;
  // spec band (0..tolerance) + specification limit line (NOT a statistical UCL)
  svg += `<rect x="${ml}" y="${y(tol)}" width="${iw}" height="${mt + ih - y(tol)}"
            fill="rgba(118,185,0,.07)"/>
          <line x1="${ml}" y1="${y(tol)}" x2="${ml + iw}" y2="${y(tol)}"
            stroke="${AMBER}" stroke-width="1.5" stroke-dasharray="6 4"/>
          <text x="${ml + iw}" y="${y(tol) - 5}" text-anchor="end" font-size="10" fill="${AMBER}">
            spec limit · tolerance ${tol.toFixed(0)} mm</text>`;
  // target line (0 offset)
  svg += `<line x1="${ml}" y1="${y(0)}" x2="${ml + iw}" y2="${y(0)}" stroke="#b7bbc0" stroke-dasharray="2 3"/>
          <text x="${ml + iw}" y="${y(0) - 4}" text-anchor="end" font-size="9" fill="#9aa1a8">target 0 mm</text>
          <text x="${ml - 6}" y="${y(0) + 3}" text-anchor="end" font-size="9" fill="#6a6f75">0</text>
          <text x="${ml - 6}" y="${y(tol) + 3}" text-anchor="end" font-size="9" fill="#6a6f75">${tol.toFixed(0)}</text>
          <text x="14" y="${mt + ih / 2}" font-size="10" fill="#6a6f75" transform="rotate(-90 14 ${mt + ih / 2})" text-anchor="middle">offset (mm)</text>`;
  // connecting line
  svg += `<polyline fill="none" stroke="#c8ccd0" stroke-width="1.2" points="${
    pts.map((p, i) => `${x(i)},${y(mm(p.offset_m))}`).join(" ")}"/>`;
  // points — shape encodes state too: filled ● in-spec, amber ✕ held
  pts.forEach((p, i) => {
    const val = mm(p.offset_m);
    const inSpec = p.pass === true && val <= tol;
    const cx = x(i), cy = y(val);
    const label = [p.color, p.mission].filter(Boolean).map(sesc).join(" · ");
    const title = `<title>${label} — ${val.toFixed(1)} mm (${inSpec ? "in spec" : "held / out of spec"})</title>`;
    if (inSpec) {
      svg += `<circle cx="${cx}" cy="${cy}" r="5" fill="${GREEN}" stroke="#fff" stroke-width="1.5">${title}</circle>`;
    } else {
      const r = 5;
      svg += `<g>${title}
        <line x1="${cx - r}" y1="${cy - r}" x2="${cx + r}" y2="${cy + r}" stroke="${AMBER}" stroke-width="2.4"/>
        <line x1="${cx - r}" y1="${cy + r}" x2="${cx + r}" y2="${cy - r}" stroke="${AMBER}" stroke-width="2.4"/></g>`;
    }
    svg += `<text x="${cx}" y="${mt + ih + 14}" text-anchor="middle" font-size="9" fill="#6a6f75">${sesc(i + 1)}</text>`;
  });
  svg += `<text x="${ml + iw / 2}" y="${H - 6}" text-anchor="middle" font-size="10" fill="#6a6f75">completed move (chronological)${
    pts.length < 8 ? ` · n=${pts.length} (statistical control limits need n≥8)` : ""}</text>`;
  svg += `</svg>`;
  el.innerHTML = svg;
}

// ---- GSN assurance case: claim -> mechanism -> evidence -----------------
// Two evidence kinds, shown differently so a design-time claim never looks like
// a measured one: `live` claims get a figure from the audit store; `design`
// claims get a neutral "design-time" chip + the concrete proof that backs them.
function renderGuarantees(gate, cov, guarantees) {
  const live = {
    "Physics-verified, fail-closed": gate.verified_rate == null ? null
      : { n: Math.round(gate.verified_rate * 100) + "%", t: "verified" },
    "Operator actions blocked from agents":
      { n: (gate.operator_refused || 0), t: "in actuation log" },
    "Every action journaled with evidence": cov.ops
      ? { n: pct(cov.with_frame, cov.ops) + "%", t: "framed" } : null,
  };
  document.getElementById("safetyguarantees").innerHTML = guarantees.map((g) => {
    let evhtml, proof = "";
    if (g.basis === "live") {
      const e = live[g.name];
      evhtml = e
        ? `<div class="gev"><b>${sesc(e.n)}</b><span>${sesc(e.t)} · measured</span></div>`
        : `<div class="gev"><span class="pill info" style="margin:0">no data yet</span></div>`;
    } else {
      // design-time / test-enforced — explicitly NOT a runtime measurement
      evhtml = `<div class="gev"><span class="pill info" style="margin:0">design-time</span></div>`;
      if (g.proof) proof = `<div class="gproof">Backed by: <code>${sesc(g.proof)}</code></div>`;
    }
    return `<div class="gcard">
      <div><div class="gclaim">${g.basis === "live" ? "Claim · live evidence" : "Claim · design-time"}</div>
        <div class="gname">${sesc(g.name)}</div></div>
      ${evhtml}
      <div class="gmech"><strong style="color:#5a8c00">Mechanism · </strong>${sesc(g.how)}</div>
      ${proof}
    </div>`;
  }).join("");
}

// ---- records-integrity coverage (Part 11 / SOC 2 idiom) ----------------
function renderCoverage(cov) {
  const ops = cov.ops || 0;
  // Every figure is measured from the audit store — no hardcoded 100%.
  const p = (num) => (ops ? pct(num, ops) + "%" : "—");
  const tiles = [
    { n: p(cov.with_request), t: "Attributable",
      d: `${sesc(cov.with_request || 0)}/${sesc(ops)} ops carry a request id and full request payload` },
    { n: p(cov.with_timing), t: "Timestamped",
      d: `${sesc(cov.with_timing || 0)}/${sesc(ops)} ops carry a start time and duration on the record` },
    { n: (cov.dispatches ? pct(cov.with_verdict, cov.dispatches) : 0) + "%", t: "Complete",
      d: `${sesc(cov.with_verdict || 0)}/${sesc(cov.dispatches || 0)} dispatches carry a pass/fail verdict` },
    { n: p(cov.with_frame), t: "Evidence-anchored",
      d: `${sesc(cov.with_frame || 0)}/${sesc(ops)} ops store the exact frame the VLM saw` },
  ];
  document.getElementById("safetycoverage").innerHTML =
    `<div class="covgrid">` + tiles.map((t) =>
      `<div class="covtile"><div class="cvn">${sesc(t.n)}</div>
        <div class="cvt">${sesc(t.t)}</div><div class="cvd">${sesc(t.d)}</div></div>`
    ).join("") + `</div>`;
}
