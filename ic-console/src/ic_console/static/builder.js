// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Workflow builder tab — talks to the ic-workflows service (write path).
// The console's own API stays read-only; all mutations go browser -> :8610.

const WF_API = window.IC_WORKFLOWS_URL || `${location.protocol}//${location.hostname}:8610`;

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

const topoMain = document.getElementById("topo");
const builderMain = document.getElementById("builder");
const tabTopo = document.getElementById("tab-topo");
const tabWf = document.getElementById("tab-wf");
const paletteEl = document.getElementById("palette");
const wfListEl = document.getElementById("wflist");
const stepsEl = document.getElementById("steps");
const resultEl = document.getElementById("wfresult");
const nameEl = document.getElementById("wfname");
const descEl = document.getElementById("wfdesc");
const paramsEl = document.getElementById("runparams");

let tools = {};
let steps = []; // [{tool, args: {k: v}, max_retries}]
let loadedSchedule = null; // preserved across edit+save so Save doesn't wipe it

tabTopo.onclick = () => switchTab("topo");
tabWf.onclick = () => { switchTab("wf"); refresh(); };
function switchTab(which) {
  const wf = which === "wf";
  topoMain.style.display = wf ? "none" : "grid";
  builderMain.style.display = wf ? "grid" : "none";
  tabTopo.classList.toggle("active", !wf);
  tabWf.classList.toggle("active", wf);
}

const WF_TOKEN = window.IC_WORKFLOWS_TOKEN || "console";
async function api(path, opts = {}) {
  const r = await fetch(WF_API + path, {
    headers: { "content-type": "application/json", "x-ic-workflows": WF_TOKEN },
    ...opts,
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail ? JSON.stringify(body.detail) : r.statusText);
  return body;
}

async function refresh() {
  try {
    tools = (await api("/api/tools")).tools;
    paletteEl.innerHTML = Object.entries(tools)
      .map(
        ([name, t]) =>
          `<div class="tool" data-tool="${esc(name)}">
             <strong>${esc(name)}</strong>
             <button class="miniex" data-ex="${esc(name)}" title="add a filled-in example step">example</button>
             <div class="muted">${esc(t.description)}</div></div>`
      )
      .join("");
    for (const el of paletteEl.querySelectorAll(".tool"))
      el.onclick = (e) => { if (!e.target.classList.contains("miniex")) addStep(el.dataset.tool); };
    for (const el of paletteEl.querySelectorAll(".miniex"))
      el.onclick = (e) => { e.stopPropagation(); addStep(el.dataset.ex, true); };

    const list = (await api("/api/workflows")).workflows;
    wfListEl.innerHTML = list.length
      ? list
          .map(
            (w) =>
              `<div class="wf" data-name="${esc(w.name)}"><strong>${esc(w.name)}</strong> <span class="muted">${esc(w.steps ?? "?")} steps</span><div class="muted">${esc(w.description || w.error || "")}</div></div>`
          )
          .join("")
      : '<div class="muted">none yet</div>';
    for (const el of wfListEl.querySelectorAll(".wf"))
      el.onclick = () => load(el.dataset.name);
  } catch (e) {
    paletteEl.innerHTML = `<div class="muted">workflow service unreachable at ${esc(WF_API)} — start it: ic-workflows</div>`;
  }
}

function addStep(tool, filled = false) {
  const args = {};
  const ex = tools[tool]?.example || {};
  for (const key of Object.keys(tools[tool]?.params || {})) {
    // A filled example step prefills the sample call; a blank step is empty.
    args[key] = filled && key in ex ? String(ex[key]) : "";
  }
  steps.push({ tool, args, max_retries: 0 });
  renderSteps();
}

function renderSteps() {
  stepsEl.innerHTML = steps
    .map((s, i) => {
      const fields = Object.entries(s.args)
        .map(([k, v]) => {
          const desc = (tools[s.tool]?.params || {})[k] || "";
          const ex = (tools[s.tool]?.examples || {})[k];
          const ph = ex ? `e.g. ${ex}   ·   or \${params.name}` : "literal or \${params.name} or \${steps.0.field}";
          return `<div class="field"><label>${esc(k)} <span class="muted">${esc(desc)}</span></label>
          <input data-step="${i}" data-key="${esc(k)}" value="${esc(v ?? "")}" placeholder="${esc(ph)}"/></div>`;
        })
        .join("");
      return `<div class="step"><div class="head"><strong>${i}. ${esc(s.tool)}</strong>
        <span>retries <input style="width:36px" data-retry="${i}" value="${esc(s.max_retries)}"/> <button class="x" data-del="${i}">✕</button></span></div>${fields}</div>`;
    })
    .join("");
  for (const input of stepsEl.querySelectorAll("input[data-step]"))
    input.oninput = () => (steps[+input.dataset.step].args[input.dataset.key] = input.value);
  for (const input of stepsEl.querySelectorAll("input[data-retry]"))
    input.oninput = () => (steps[+input.dataset.retry].max_retries = +input.value || 0);
  for (const btn of stepsEl.querySelectorAll("button[data-del]"))
    btn.onclick = () => { steps.splice(+btn.dataset.del, 1); renderSteps(); };
}

function currentSpec() {
  const params = {};
  for (const s of steps)
    for (const v of Object.values(s.args)) {
      const m = /^\$\{params\.(\w+)\}$/.exec(v);
      if (m) params[m[1]] = "string";
    }
  const spec = {
    name: nameEl.value.trim(),
    description: descEl.value.trim(),
    params,
    steps: steps.map((s) => ({
      tool: s.tool,
      args: Object.fromEntries(Object.entries(s.args).filter(([, v]) => v !== "")),
      max_retries: s.max_retries,
    })),
  };
  if (loadedSchedule) spec.schedule = loadedSchedule;  // don't wipe an existing schedule
  return spec;
}

async function load(name) {
  const wf = await api(`/api/workflows/${encodeURIComponent(name)}`);
  nameEl.value = wf.name;
  descEl.value = wf.description || "";
  steps = wf.steps.map((s) => ({ tool: s.tool, args: { ...s.args }, max_retries: s.max_retries || 0 }));
  renderSteps();
  // reflect any existing schedule in the controls
  const si = document.getElementById("schint"), se = document.getElementById("schen");
  loadedSchedule = wf.schedule || null;
  if (wf.schedule) {
    si.value = wf.schedule.interval_s;
    se.checked = !!wf.schedule.enabled;
    // reflect the SCHEDULE's params into the params box so re-Set round-trips
    // them (not a stale/empty run value).
    paramsEl.value = JSON.stringify(wf.schedule.params || {});
  } else { se.checked = false; }
  show({ loaded: name });
}

function show(obj) {
  resultEl.innerHTML = `<pre>${esc(JSON.stringify(obj, null, 1))}</pre>`;
}

document.getElementById("wfnew").onclick = () => {
  nameEl.value = ""; descEl.value = ""; steps = []; loadedSchedule = null; document.getElementById("schen").checked = false; renderSteps();
};
// A complete, valid sample workflow so you can see exactly what a filled-in
// one looks like: perceive → move the requested color to the tote → verify.
document.getElementById("wfexample").onclick = () => {
  nameEl.value = "sort-one-cube";
  descEl.value = "Perceive the conveyor, move one cube of the requested color into the tote, prove it.";
  steps = [
    { tool: "perceive", args: { target: "conveyor_1" }, max_retries: 0 },
    { tool: "dispatch_task",
      args: { action: "move", endpoint: "franka_left", color: "${params.color}",
              source: "conveyor_1", destination: "tote" }, max_retries: 0 },
    { tool: "check_predicate",
      args: { predicate: "the cube is in its tote compartment", region: "tote" }, max_retries: 0 },
  ];
  renderSteps();
  show({ hint: "Example loaded. 'color' uses ${params.color} — set it in Run params, e.g. {\"color\":\"red\"}. Try Dry-run, then Run." });
  paramsEl.value = '{"color": "red"}';
};
document.getElementById("wfsave").onclick = async () => {
  const spec = currentSpec();
  try { show(await api(`/api/workflows/${encodeURIComponent(spec.name)}`, { method: "PUT", body: JSON.stringify(spec) })); refresh(); }
  catch (e) { show({ error: String(e.message) }); }
};
document.getElementById("wfdry").onclick = () => execute("dry-run");
document.getElementById("wfrun").onclick = () => execute("run");
document.getElementById("wfpublish").onclick = async () => {
  try { show(await api(`/api/workflows/${encodeURIComponent(nameEl.value.trim())}/publish`, { method: "POST", body: "{}" })); }
  catch (e) { show({ error: String(e.message) }); }
};

// NL assistant: draft a schema-verified artifact into the editor for review.
async function assist(kind) {
  const instruction = document.getElementById("asktext").value.trim();
  const statusEl = document.getElementById("askstatus");
  if (!instruction) return;
  statusEl.textContent = "drafting…";
  try {
    const out = await api("/api/assist", {
      method: "POST",
      body: JSON.stringify({ kind, instruction }),
    });
    if (!out.ok) {
      statusEl.textContent = "";
      show({ assistant_failed: out.error, attempts: out.attempts });
      return;
    }
    statusEl.textContent = `verified in ${out.attempts} attempt(s) — review & save`;
    if (kind === "workflow") {
      const wf = out.draft;
      nameEl.value = wf.name || "";
      descEl.value = wf.description || "";
      steps = (wf.steps || []).map((s) => ({
        tool: s.tool, args: { ...(s.args || {}) }, max_retries: s.max_retries || 0,
      }));
      renderSteps();
      show({ drafted_workflow: wf.name, note: "Loaded into the editor. Dry-run, then Save." });
    } else {
      show({ drafted_skill: out.draft, note: "Schema-verified skill manifest. Save it as skills/wf-<name>/manifest.yaml or adapt a workflow + Publish." });
    }
  } catch (e) {
    statusEl.textContent = "";
    show({ error: String(e.message) });
  }
}
document.getElementById("askwf").onclick = () => assist("workflow");
document.getElementById("askskill").onclick = () => assist("skill");

// ---- scheduling: run the loaded workflow on a timer -----------------------
async function loadSchedules() {
  const el = document.getElementById("schlist");
  try {
    const list = (await api("/api/schedules")).schedules || [];
    if (!list.length) { el.textContent = "none"; return; }
    el.innerHTML = list.map((s) => {
      const last = s.last_run ? new Date(s.last_run * 1000).toLocaleTimeString() : "—";
      const state = s.running ? "running" : s.enabled ? "enabled" : "paused";
      const ok = s.last_ok === false ? " · last FAILED" : s.last_ok === true ? " · last ok" : "";
      return `<div class="wf" data-sch="${esc(s.name)}"><strong>${esc(s.name)}</strong>
        <span class="muted">every ${esc(s.interval_s)}s · ${esc(state)} · last ${esc(last)}${esc(ok)}</span></div>`;
    }).join("");
    for (const d of el.querySelectorAll(".wf")) d.onclick = () => load(d.dataset.sch);
  } catch { el.textContent = "workflow service unreachable"; }
}
document.getElementById("schsave").onclick = async () => {
  const name = nameEl.value.trim();
  if (!name) return show({ error: "load or save a workflow first" });
  const interval_s = parseInt(document.getElementById("schint").value, 10) || 120;
  const enabled = document.getElementById("schen").checked;
  try {
    const p = JSON.parse(paramsEl.value || "{}");
    show(await api(`/api/workflows/${encodeURIComponent(name)}/schedule`,
      { method: "POST", body: JSON.stringify({ interval_s, enabled, params: p }) }));
    loadedSchedule = { interval_s, enabled, params: p };
    loadSchedules();
  } catch (e) { show({ error: String(e.message) }); }
};
document.getElementById("schclear").onclick = async () => {
  const name = nameEl.value.trim();
  if (!name) return;
  try { show(await api(`/api/workflows/${encodeURIComponent(name)}/schedule`, { method: "DELETE" })); loadedSchedule = null; loadSchedules(); }
  catch (e) { show({ error: String(e.message) }); }
};
// refresh the schedule list when the Workflows tab is shown + periodically
tabWf.addEventListener("click", loadSchedules);
setInterval(() => { if (builderMain.style.display !== "none") loadSchedules(); }, 5000);

async function execute(kind) {
  let params;
  try { params = JSON.parse(paramsEl.value || "{}"); }
  catch { return show({ error: "run params is not valid JSON" }); }
  try {
    show(await api(`/api/workflows/${encodeURIComponent(nameEl.value.trim())}/${kind}`, { method: "POST", body: JSON.stringify({ params }) }));
  } catch (e) { show({ error: String(e.message) }); }
}

refresh();
