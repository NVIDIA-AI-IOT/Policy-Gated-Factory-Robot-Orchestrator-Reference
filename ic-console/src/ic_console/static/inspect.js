// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Inspector tab — the live audit feed that imprints how inspectable the backend
// is. Every value is escaped before innerHTML (same guarantee as the rest).

function iesc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

const inspectMain = document.getElementById("inspect");
const feedEl = document.getElementById("inspectfeed");
const statsEl = document.getElementById("inspectstats");
const tabInspect = document.getElementById("tab-inspect");
const iTabs = ["tab-topo", "tab-wf", "tab-chat"].map((id) => document.getElementById(id));
const iMains = ["topo", "builder", "chat"].map((id) => document.getElementById(id));

let inspectTimer = null;
tabInspect.onclick = () => {
  for (const m of iMains) m.style.display = "none";
  inspectMain.style.display = "grid";
  for (const b of iTabs) b.classList.remove("active");
  tabInspect.classList.add("active");
  const active = window.ICSession ? window.ICSession.get() : "";
  if (active) selectedMission = active;
  loadInspect();
  if (inspectTimer) clearInterval(inspectTimer);
  inspectTimer = setInterval(() => { if (inspectMain.style.display !== "none") loadInspect(); }, 5000);
};
// leaving the tab hides it + stops polling
for (const b of iTabs) {
  const prev = b.onclick;
  b.onclick = (e) => {
    inspectMain.style.display = "none";
    tabInspect.classList.remove("active");
    if (inspectTimer) { clearInterval(inspectTimer); inspectTimer = null; }
    if (prev) prev(e);
  };
}

function stat(n, label) {
  return `<div class="stat"><b>${iesc(n)}</b><span>${iesc(label)}</span></div>`;
}

function badge(v) {
  if (v === true) return `<span class="pill ok" style="margin:0">verified</span>`;
  if (v === false) return `<span class="pill fail" style="margin:0">unverified</span>`;
  return `<span class="pill info" style="margin:0">observed</span>`;
}

// Auditable key/value renderer: dense, monospaced, recursive — shows the FULL
// record (nested objects and arrays too), never a collapsed JSON blob and
// never playful chips.
function scalar(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}
function kvTree(obj, depth) {
  const pad = depth * 14;
  const rows = [];
  for (const [k, v] of Object.entries(obj || {})) {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      rows.push(`<div class="kv" style="padding-left:${pad}px"><span class="kk">${iesc(k)}</span></div>`);
      rows.push(kvTree(v, depth + 1));
    } else if (Array.isArray(v)) {
      if (v.length && typeof v[0] === "object") {
        rows.push(`<div class="kv" style="padding-left:${pad}px"><span class="kk">${iesc(k)}</span><span class="kd">[${v.length}]</span></div>`);
        v.forEach((el, i) => {
          rows.push(`<div class="kv" style="padding-left:${pad + 14}px"><span class="kk">${i}</span></div>`);
          rows.push(kvTree(el, depth + 2));
        });
      } else {
        rows.push(`<div class="kv" style="padding-left:${pad}px"><span class="kk">${iesc(k)}</span><span class="kvv">${iesc(v.map(scalar).join(", "))}</span></div>`);
      }
    } else {
      rows.push(`<div class="kv" style="padding-left:${pad}px"><span class="kk">${iesc(k)}</span><span class="kvv">${iesc(scalar(v))}</span></div>`);
    }
  }
  return rows.join("");
}
function fmtFields(obj) {
  const skip = new Set(["_meta", "request_id"]);
  const filtered = Object.fromEntries(Object.entries(obj || {}).filter(([k]) => !skip.has(k)));
  if (!Object.keys(filtered).length) return `<div class="muted" style="font-size:12px">—</div>`;
  return `<div class="kvtree">${kvTree(filtered, 0)}</div>`;
}

const missionsEl = document.getElementById("inspectmissions");
const timelineEl = document.getElementById("inspecttimeline");
const openIds = new Set();          // expanded subtasks (request_id) — persist across refreshes
let selectedMission = null;
let missionsSig = null, timelineSig = null;

function hms(iso) {
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toTimeString().slice(0, 8);
}
function endTime(iso, dur) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return new Date(d.getTime() + (dur || 0) * 1000).toTimeString().slice(0, 8);
}
const VLM_OPS = new Set(["perceive", "verify"]);

async function loadInspect() {
  let list;
  try {
    list = (await (await fetch("/api/missions?limit=25")).json()).missions || [];
  } catch {
    missionsEl.textContent = "audit store unreachable";
    return;
  }
  const sig = list.map((m) => m.mission_id + ":" + m.dispatches).join("|");
  if (sig !== missionsSig) {
    missionsSig = sig;
    missionsEl.innerHTML = list.length
      ? list.map((m) => {
          const id = m.mission_id;
          const ok = m.verified_dispatches, tot = m.dispatches;
          return `<div class="mrow ${id === selectedMission ? "active" : ""}" data-mid="${iesc(id)}">
            <div class="mt">${iesc(id)}</div>
            <div class="mm">${iesc(m.ops ?? "?")} subtasks · ${iesc(ok)}/${iesc(tot)} verified</div></div>`;
        }).join("")
      : `<div class="muted">no tasks yet</div>`;
    for (const r of missionsEl.querySelectorAll(".mrow"))
      r.onclick = () => selectMission(r.dataset.mid);
  }
  if (!selectedMission && list.length) selectMission(list[0].mission_id);
  else if (selectedMission) selectMission(selectedMission, true);
}

async function selectMission(mid, keepScroll) {
  selectedMission = mid;
  if (window.ICSession && window.ICSession.get() !== mid) window.ICSession.set(mid);
  for (const r of missionsEl.querySelectorAll(".mrow"))
    r.classList.toggle("active", r.dataset.mid === mid);
  let ops;
  try {
    ops = (await (await fetch(`/api/missions/${encodeURIComponent(mid)}`)).json()).operations || [];
  } catch { timelineEl.textContent = "task unreachable"; return; }

  const sig = mid + "#" + ops.map((o) => o.request_id || o.ts).join("|");
  if (keepScroll && sig === timelineSig) return;   // no change -> don't rebuild (keeps expansion)
  timelineSig = sig;

  // per-task stats
  const disp = ops.filter((o) => o.op === "dispatch" || o.action);
  const ver = disp.filter((o) => o.verified === true).length;
  const total = ops.reduce((a, o) => a + (o.duration_s || 0), 0);
  const span = ops.length ? `${hms(ops[0].ts)} → ${endTime(ops[ops.length - 1].ts, ops[ops.length - 1].duration_s)}` : "";
  statsEl.innerHTML =
    stat(ops.length, "subtasks") + stat(disp.length, "actions") +
    stat(ver, "physics-verified") + stat(total.toFixed(1) + "s", "task duration");

  const rows = ops.map((o, i) => {
    // dispatch shows the action (move/pick_and_place); perceive/verify show the
    // op name (the DB's action column holds the target/predicate for those).
    const verb = iesc(o.op === "dispatch" ? (o.action || "dispatch") : (o.op || o.action || "op"));
    const ep = o.endpoint ? `<span class="opep">${iesc(o.endpoint)}</span>` : "";
    const rid = o.request_id || "";
    const cls = o.verified === true ? "verified" : o.verified === false ? "failed" : "";
    const open = openIds.has(rid) ? " open" : "";
    // VLM query/response block for perceive & verify
    let vlm = "";
    if (VLM_OPS.has(o.op)) {
      const q = o.op === "verify"
        ? `verify: "${(o.request || {}).predicate || ""}"`
        : `perceive ${(o.request || {}).target || ""}`;
      const vis = (o.result || {}).vision || {};
      const ans = o.op === "verify"
        ? `answer: ${(o.result || {}).answer ?? "—"}` +
          ((o.result || {}).evidence ? ` — ${(o.result || {}).evidence}` : "")
        : (vis.summary || "(structured observation)");
      const meta = [vis.model, vis.latency_ms ? vis.latency_ms + "ms" : ""].filter(Boolean).join(" · ");
      vlm = `<div class="vlm">
        <div class="ql">VLM query</div><div class="qt">${iesc(q)}</div>
        <div class="ql">VLM response</div><div class="at">${iesc(ans)}</div>
        ${meta ? `<div class="meta">${iesc(meta)}</div>` : ""}</div>`;
    }
    const frame = rid
      ? `<div class="opframe"><h4>evidence frame · what the VLM saw</h4>
           <img loading="lazy" src="/api/frame/${encodeURIComponent(rid)}"/>
           <div class="opcap">frames/${iesc(rid)}.jpg</div></div>`
      : "";
    return `<div class="tlrow ${cls}${open}" data-rid="${iesc(rid)}">
      <div class="tlhead">
        <span class="tlstep">${i + 1}</span>
        <span class="tlverb">${verb}</span>${ep} ${badge(o.verified)}
        <span class="tltime">${iesc(hms(o.ts))} → ${iesc(endTime(o.ts, o.duration_s))}</span>
        <span class="tldur">${iesc((o.duration_s ?? 0))}s</span>
        <span class="chev">▸</span>
      </div>
      ${vlm}
      ${o.reason ? `<div class="tlreason">${iesc(o.reason)}</div>` : ""}
      <div class="tlbody">
        <div class="col"><h4>request</h4>${fmtFields(o.request)}</div>
        <div class="col"><h4>result</h4>${fmtFields(o.result)}</div>
        ${frame}
        <div class="opkey">audit key · request_id <span class="mono">${iesc(rid)}</span></div>
      </div></div>`;
  }).join("");
  timelineEl.innerHTML =
    `<div class="thead"><div class="tt">${iesc(mid)}</div>
       <div class="tm">${iesc(ops.length)} subtasks · ${iesc(span)} · ${total.toFixed(1)}s total · ${ver}/${disp.length} verified</div></div>
     <div class="tl">${rows}</div>`;
  for (const row of timelineEl.querySelectorAll(".tlrow")) {
    row.querySelector(".tlhead").onclick = () => {
      row.classList.toggle("open");
      const rid = row.dataset.rid;
      if (row.classList.contains("open")) openIds.add(rid); else openIds.delete(rid);
    };
  }
  for (const img of timelineEl.querySelectorAll(".opframe img")) {
    img.addEventListener("error", () => {
      const frame = img.closest(".opframe");
      if (frame) frame.remove();
    });
  }
}
