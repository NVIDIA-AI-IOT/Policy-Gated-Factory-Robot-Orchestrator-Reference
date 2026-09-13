// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Chat tab — talks to the pgfr-chat gateway (write path). All untrusted values
// (model text, tool args/results) are esc()'d before innerHTML.

import { escapeHtml as cesc, rememberSessions, sessionTitle, sessionDate } from "./display.js?v=console-maintenance1";

const CHAT_API = window.PGFR_CHAT_URL || `${location.protocol}//${location.hostname}:8620`;
const CHAT_TOKEN = window.PGFR_CHAT_TOKEN || "console";

const chatMain = document.getElementById("chat");
const topoMain = document.getElementById("topo");
const logEl = document.getElementById("chatlog");
const inputEl = document.getElementById("chatinput");
const sendEl = document.getElementById("chatsend");
const metaEl = document.getElementById("chatmeta");
const connectionEl = document.getElementById("chat-connection");
const copyEl = document.getElementById("copy-session-id");
const copyStatus = document.getElementById("copy-status");
let chatConnected = false;
const backendName = (backend) => backend === "openclaw" ? "OpenClaw" : "Default Chat";
function renderConnection() {
  connectionEl.textContent = chatConnected ? "Chat connected" : "Chat unavailable";
  connectionEl.dataset.state = chatConnected ? "connected" : "unavailable";
  metaEl.textContent = chatConnected ? `Assistant: ${backendName(selectedBackend)}` : "Check the Chat service on the control host.";
}
function renderSessionId() {
  document.getElementById("chatsession").textContent = sessionId || "New conversation";
  copyEl.disabled = !sessionId;
  copyStatus.textContent = "";
}
copyEl.onclick = async () => {
  if (!sessionId) return;
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(sessionId);
    else {
      // The workstation dashboard is also served over plain HTTP on the LAN.
      const field = document.createElement("textarea");
      field.value = sessionId;
      field.style.cssText = "position:fixed;opacity:0;pointer-events:none";
      document.body.append(field);
      field.select();
      try { if (!document.execCommand("copy")) throw new Error("Copy unavailable"); }
      finally { field.remove(); copyEl.focus(); }
    }
    copyStatus.textContent = "Copied";
  } catch { copyStatus.textContent = "Select the session ID to copy it."; }
};
const backendEl = document.getElementById("chatbackend");
const tabChat = document.getElementById("tab-chat");
const tabTopo = document.getElementById("tab-topo");
const resetEl = document.getElementById("reset-scene");
const resetDialog = document.getElementById("reset-dialog");
const resetStatus = document.getElementById("reset-status");
const newChatEl = document.getElementById("chatnew");
const emptyChatTemplate = document.getElementById("chatempty").outerHTML;
let resetAvailable = false;
let resetRunning = false;

let sessionId = localStorage.getItem("pgfr_chat_session") || "";
let chatRunning = false;
let stopRequestPending = false;
// The transcript is live DOM state while an SSE turn is running. Re-fetching
// the session when the operator returns from another pane can replace that
// state with the older persisted history (new sessions are persisted only
// after the stream completes), making the chat appear to vanish.
let renderedSessionId = "";
let sessionLoadGeneration = 0;
let sessionLoading = false;
let selectedBackend = localStorage.getItem("pgfr_chat_backend") || "traditional";
if (!["traditional", "openclaw"].includes(selectedBackend)) selectedBackend = "traditional";
backendEl.value = selectedBackend;

function setBackend(value) {
  selectedBackend = value === "openclaw" ? "openclaw" : "traditional";
  backendEl.value = selectedBackend;
  localStorage.setItem("pgfr_chat_backend", selectedBackend);
  renderConnection();
}

function setChatRunning(running) {
  chatRunning = running;
  sendEl.disabled = resetRunning || sessionLoading;
  sendEl.textContent = running ? "Stop" : "Send";
  sendEl.classList.toggle("stop", running);
  inputEl.disabled = running || resetRunning || sessionLoading;
  backendEl.disabled = running || resetRunning || sessionLoading || Boolean(sessionId);
  newChatEl.disabled = running || resetRunning;
  const needsRestore = sessionLoading || Boolean(sessionId && renderedSessionId !== sessionId);
  resetEl.disabled = running || resetRunning || needsRestore || !resetAvailable;
  resetEl.setAttribute("aria-busy", String(resetRunning));
  resetEl.innerHTML = resetRunning
    ? '<span aria-hidden="true">↻</span> Resetting…'
    : '<span aria-hidden="true">↻</span> Reset Scene';
  resetEl.title = running ? "Wait for the current Chat action to finish"
    : resetRunning ? "Waiting for the reset result"
    : needsRestore ? "Load the saved conversation or start a new chat before resetting"
    : resetAvailable ? "Return Isaac Sim to its starting layout" : "Scene reset is unavailable";
}

tabChat.onclick = () => {
  topoMain.style.display = "none";
  chatMain.style.display = "grid";
  for (const b of [tabTopo]) b.classList.remove("active");
  tabChat.classList.add("active");
  loadMeta();
  loadSessions();
  // A hidden pane does not stop the stream. Keep its transcript attached and
  // only restore from the server when this browser has not rendered it yet.
  if (!chatRunning && !resetRunning && sessionId && renderedSessionId !== sessionId)
    openSession(sessionId);
};
// when the other tabs are clicked, hide chat too
for (const b of [tabTopo]) {
  const prev = b.onclick;
  b.onclick = (e) => { chatMain.style.display = "none"; tabChat.classList.remove("active"); if (prev) prev(e); };
}

async function loadMeta() {
  try {
    const r = await fetch(CHAT_API + "/api/health");
    if (!r.ok) throw new Error("Chat gateway unavailable");
    const b = await r.json();
    resetAvailable = b.actions?.reset_scene === true;
    setChatRunning(chatRunning);
    const options = b.backends || {};
    const openclaw = backendEl.querySelector('option[value="openclaw"]');
    if (openclaw) {
      const ready = options.openclaw?.available !== false;
      openclaw.disabled = !ready;
      openclaw.textContent = ready ? "OpenClaw" : "OpenClaw (not configured)";
      if (!ready && selectedBackend === "openclaw" && !sessionId) setBackend("traditional");
    }
    chatConnected = true;
    renderConnection();
  } catch {
    resetAvailable = false;
    setChatRunning(chatRunning);
    chatConnected = false;
    renderConnection();
  }
}

const sessionsEl = document.getElementById("chatsessions");
async function loadSessions() {
  try {
    const list = (await (await fetch(CHAT_API + "/api/sessions")).json()).sessions || [];
    rememberSessions(list);
    if (!list.length) { sessionsEl.textContent = "No conversations yet"; return; }
    sessionsEl.innerHTML = list.map((s) =>
      `<div class="sess ${s.id === sessionId ? "active" : ""}" data-sid="${cesc(s.id)}">
         <span class="st" title="${cesc(sessionTitle(s))}">${cesc(sessionTitle(s))}
           <span class="sid">${cesc(sessionDate(s))}${s.backend === "openclaw" ? " · OpenClaw" : ""}</span></span>
         <button class="sd" data-del="${cesc(s.id)}" title="Delete conversation" aria-label="Delete conversation">✕</button></div>`).join("");
    for (const el of sessionsEl.querySelectorAll(".sess"))
      el.onclick = (e) => { if (!e.target.classList.contains("sd")) openSession(el.dataset.sid); };
    for (const b of sessionsEl.querySelectorAll(".sd"))
      b.onclick = (e) => { e.stopPropagation(); delSession(b.dataset.del); };
  } catch { sessionsEl.textContent = "Chat history is unavailable"; }
}

async function openSession(sid) {
  // Never replace a live transcript or let the operator switch/delete its
  // backing session while tool results are still arriving.
  if (chatRunning || resetRunning) return;
  const loadGeneration = ++sessionLoadGeneration;
  sessionLoading = true;
  setChatRunning(chatRunning);
  resetStatus.hidden = true;
  try {
    const r = await fetch(CHAT_API + `/api/sessions/${encodeURIComponent(sid)}`);
    if (chatRunning || resetRunning || loadGeneration !== sessionLoadGeneration) return;
    if (!r.ok) { newChat(); return; }
    const s = await r.json();
    if (chatRunning || resetRunning || loadGeneration !== sessionLoadGeneration) return;
    sessionId = s.id;
    renderedSessionId = sessionId;
    setBackend(s.backend || "traditional");
    localStorage.setItem("pgfr_chat_session", sessionId);
    if (window.PGFRSession) window.PGFRSession.set(s.mission_id);
    logEl.innerHTML = "";
    for (const m of s.history || []) {
    if (m.role === "tool") addTool(m);
    else addMsg(m.role === "user" ? "you" : "brain", m.content);
  }
    if (!(s.history || []).length) newChat();
    renderSessionId();
    backendEl.disabled = true;
    loadSessions();
  } catch { /* leave as-is */ } finally {
    if (loadGeneration === sessionLoadGeneration) {
      sessionLoading = false;
      setChatRunning(chatRunning);
    }
  }
}

function newChat() {
  if (chatRunning || resetRunning) return;
  sessionLoadGeneration += 1;
  sessionId = "";
  renderedSessionId = "";
  sessionLoading = false;
  resetStatus.hidden = true;
  localStorage.removeItem("pgfr_chat_session");
  if (window.PGFRSession) window.PGFRSession.set("");
  logEl.innerHTML = "";
  clearEmptyRestore();
  backendEl.disabled = false;
  renderSessionId();
  setChatRunning(chatRunning);
  loadSessions();
}
function clearEmptyRestore() {
  logEl.innerHTML = emptyChatTemplate;
}

// Suggestions prepare a message; only Send can submit it.
logEl.addEventListener("click", (event) => {
  const example = event.target.closest("[data-prompt]");
  if (!example || chatRunning || resetRunning) return;
  inputEl.value = example.dataset.prompt;
  inputEl.focus();
});

async function delSession(sid) {
  if (chatRunning || resetRunning) return;
  try {
    await fetch(CHAT_API + `/api/sessions/${encodeURIComponent(sid)}`,
      { method: "DELETE", headers: { "x-pgfr-chat": CHAT_TOKEN } });
    if (sid === sessionId) newChat();
    else loadSessions();
  } catch { /* ignore */ }
}
newChatEl.onclick = newChat;

function clearEmpty() {
  const e = document.getElementById("chatempty");
  if (e) e.remove();
}

const AVATAR = { you: "YOU", brain: "AI", system: "!" };

// Markdown-lite: the brain writes **bold**, `code` and "- " lists; printing
// them literally made mission reports unreadable. Everything is escaped FIRST,
// so only these fixed patterns can ever become markup.
function fmt(text) {
  const esc = cesc(text);
  const out = [];
  let list = null;
  for (const raw of esc.split("\n")) {
    const line = raw
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      (list ||= []).push(`<li>${bullet[1]}</li>`);
      continue;
    }
    if (list) { out.push(`<ul class="mdlist">${list.join("")}</ul>`); list = null; }
    if (line.trim()) out.push(`<div>${line}</div>`);
  }
  if (list) out.push(`<ul class="mdlist">${list.join("")}</ul>`);
  return out.join("") || cesc(text);
}

function addMsg(who, text) {
  clearEmpty();
  const role = who === "you" ? "user" : who === "system" ? "system" : "assistant";
  const div = document.createElement("div");
  div.className = "msg " + role;
  const body = role === "assistant" ? fmt(text) : cesc(text);
  div.innerHTML =
    `<div class="avatar">${cesc(AVATAR[who] || "AI")}</div>` +
    `<div><div class="who">${cesc(who)}</div><div class="bubble">${body}</div></div>`;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

let typingEl = null;
function showTyping(on) {
  if (on) {
    clearEmpty();
    typingEl = document.createElement("div");
    typingEl.className = "msg assistant";
    typingEl.innerHTML =
      `<div class="avatar">AI</div><div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>`;
    logEl.appendChild(typingEl);
    logEl.scrollTop = logEl.scrollHeight;
  } else if (typingEl) {
    typingEl.remove();
    typingEl = null;
  }
}

function addTool(entry, running) {
  const r = entry.result || {};
  const verified = r.verified === true;
  const failed = r.error || r.verified === false;
  const pill = running
    ? `<span class="pill info">running…</span>`
    : verified
    ? `<span class="pill ok">verified</span>`
    : failed
    ? `<span class="pill fail">${cesc(r.error ? "error" : "unverified")}</span>`
    : `<span class="pill info">done</span>`;
  const div = document.createElement("div");
  div.className = "toolcard";
  // Evidence frame (the camera image the VLM saw). request_id is validated
  // [A-Za-z0-9_-]; onerror removes the block (mock/no-camera ops).
  const rid = r.request_id;
  // A request_id means the Seam journaled an evidence frame. Show that frame
  // even when VLM inference failed: the operator still needs to inspect the
  // exact image that caused the error. A genuinely missing frame is removed by
  // the CSP-compatible error listener below.
  const frame = rid
    ? `<div class="framewrap"><div class="cap">▸ frame the VLM saw</div>
         <img class="frame" loading="lazy" alt="camera frame"
           src="${cesc(CHAT_API)}/api/frame/${encodeURIComponent(rid)}"/></div>`
    : "";
  const reason = r.reason || r.error || r.verification;
  // What the VLM actually read from the frame, and whether it agreed with
  // physics. perceive/verify carry no `reason`; without this the operator saw
  // an image and a verdict but never the model's reading of the scene.
  const v = r.vision || {};
  const predicateVlm = ["check_predicate", "verify"].includes(entry.name)
    ? [r.answer, r.evidence].filter(Boolean).join(" — ")
    : null;
  const vlmText = predicateVlm || v.summary || v.error || null;
  const agree = r.vision_agrees;
  const vlm = vlmText
    ? `<div class="tcvlm"><span class="tcvlm__tag">VLM</span> ${cesc(vlmText)}` +
      (agree === true ? ` <span class="pill ok">agrees with physics</span>` : "") +
      (agree === false ? ` <span class="pill fail">differs from physics</span>` : "") +
      `</div>`
    : "";
  const response = running
    ? ""
    : `<details class="tcresponse"><summary>tool response</summary>` +
      `<pre>${cesc(JSON.stringify(r, null, 2))}</pre></details>`;
  div.innerHTML =
    `<div class="tchead"><span class="tool">${cesc(entry.name)}()</span>${pill}</div>` +
    `<div class="tcargs">${cesc(JSON.stringify(entry.args || {}))}</div>` +
    (reason ? `<div class="tcreason">${cesc(reason)}</div>` : "") +
    vlm +
    response +
    frame;
  const img = div.querySelector("img.frame");
  if (img) {
    img.addEventListener("error", () => {
      const wrap = img.closest(".framewrap");
      if (wrap) wrap.remove();
    });
  }
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
  return div;
}

// Batch fallback: identical rendering, used only when the gateway has no
// streaming route (older deployment).
async function sendBatch(text, wasNew) {
  const r = await fetch(CHAT_API + "/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json", "x-pgfr-chat": CHAT_TOKEN },
    body: JSON.stringify({
      session_id: sessionId, message: text, backend: selectedBackend,
    }),
  });
  const body = await r.json();
  showTyping(false);
  if (!r.ok) { addMsg("system", body.detail ? JSON.stringify(body.detail) : r.statusText); return; }
  sessionId = body.session_id;
  renderedSessionId = sessionId;
  localStorage.setItem("pgfr_chat_session", sessionId);
  if (window.PGFRSession) window.PGFRSession.set(body.mission_id);
  renderSessionId();
  if (wasNew) loadSessions();
  for (const entry of body.transcript || []) {
    if (entry.role === "assistant" && entry.content) addMsg("brain", entry.content);
    else if (entry.role === "tool") addTool(entry);
  }
}

async function send() {
  if (chatRunning || resetRunning || sessionLoading) return;
  const text = inputEl.value.trim();
  if (!text) return;
  resetStatus.hidden = true;
  // Invalidate any restore fetch that started just before Send was pressed.
  sessionLoadGeneration += 1;
  inputEl.value = "";
  addMsg("you", text);
  setChatRunning(true);
  showTyping(true);
  try {
    // Stream the turn (SSE): each tool call shows the moment it starts and its
    // result — with the VLM frame — the moment the seam answers, instead of a
    // wall of text at the end. Falls back to the batch route if streaming is
    // unavailable, so an older gateway still works.
    const wasNew = !sessionId;
    const r = await fetch(CHAT_API + "/api/chat/stream", {
      method: "POST",
      headers: { "content-type": "application/json", "x-pgfr-chat": CHAT_TOKEN },
      body: JSON.stringify({
        session_id: sessionId, message: text, backend: selectedBackend,
      }),
    });
    if (r.status === 404) { await sendBatch(text, wasNew); return; }
    if (!r.ok) { showTyping(false); addMsg("system", `chat error ${r.status}`); return; }
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let pending = null;   // tool card placeholder awaiting its result
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 2);
        if (!line.startsWith("data:")) continue;
        let ev; try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
        if (ev.role === "meta") {
          sessionId = ev.session_id;
          renderedSessionId = sessionId;
          localStorage.setItem("pgfr_chat_session", sessionId);
          if (window.PGFRSession) window.PGFRSession.set(ev.mission_id);
          renderSessionId();
          if (wasNew) loadSessions();
          if (stopRequestPending) requestStop();
        } else if (ev.role === "assistant" && ev.content) {
          showTyping(false); addMsg("brain", ev.content); showTyping(true);
        } else if (ev.role === "tool_start") {
          showTyping(false);
          pending = addTool({ name: ev.name, args: ev.args, result: {} }, true);
        } else if (ev.role === "tool") {
          if (pending) { pending.remove(); pending = null; }
          addTool(ev);
          showTyping(true);
        } else if (ev.role === "error") {
          showTyping(false); addMsg("system", ev.error || "stream error");
        }
      }
    }
    showTyping(false);
  } catch (e) {
    showTyping(false);
    addMsg("system", "gateway unreachable: " + String(e.message));
  } finally {
    stopRequestPending = false;
    setChatRunning(false);
    inputEl.focus();
  }
}

async function requestStop() {
  if (!chatRunning) return;
  if (!sessionId) {
    stopRequestPending = true;
    sendEl.textContent = "Stopping…";
    return;
  }
  sendEl.disabled = true;
  sendEl.textContent = "Stopping…";
  try {
    const r = await fetch(
      CHAT_API + `/api/sessions/${encodeURIComponent(sessionId)}/stop`,
      { method: "POST", headers: { "x-pgfr-chat": CHAT_TOKEN } },
    );
    const body = await r.json();
    addMsg("system", body.reason || (body.accepted ? "stop requested" : "nothing is running"));
  } catch (e) {
    addMsg("system", "stop request failed: " + String(e.message));
  } finally {
    sendEl.disabled = false;
    if (chatRunning) sendEl.textContent = "Stopping…";
  }
}

sendEl.onclick = () => chatRunning ? requestStop() : send();
backendEl.onchange = () => {
  if (chatRunning || resetRunning || sessionId) {
    backendEl.value = selectedBackend;
    return;
  }
  setBackend(backendEl.value);
  loadMeta();
};
inputEl.addEventListener("keydown", (e) => {
  if (!chatRunning && !resetRunning && e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
});

resetEl.onclick = () => {
  if (chatRunning || resetRunning || sessionLoading || (sessionId && renderedSessionId !== sessionId) || !resetAvailable) return;
  resetDialog.showModal();
};
document.getElementById("cancel-reset-scene").onclick = () => resetDialog.close();
document.getElementById("confirm-reset-scene").onclick = async () => {
  if (chatRunning || resetRunning || sessionLoading || (sessionId && renderedSessionId !== sessionId) || !resetAvailable) return;
  resetDialog.close();
  resetRunning = true;
  sessionLoadGeneration += 1;
  setChatRunning(chatRunning);
  tabChat.click();
  resetStatus.hidden = false;
  resetStatus.dataset.state = "pending";
  resetStatus.textContent = "Resetting the scene. Waiting for verification…";
  addMsg("you", "Reset Scene");
  try {
    // One explicit operator request. Never retry a reset after a timeout.
    const response = await fetch(CHAT_API + "/api/reset-scene", {
      method: "POST",
      headers: { "content-type": "application/json", "x-pgfr-chat": CHAT_TOKEN },
      body: JSON.stringify({session_id: sessionId, backend: selectedBackend}),
    });
    const body = await response.json();
    if (!response.ok) {
      if (![400, 401, 403, 404, 409, 422].includes(response.status))
        throw new Error("Reset gateway failure");
      resetStatus.dataset.state = "refused";
      resetStatus.textContent = typeof body.detail === "string" ? body.detail : "Scene reset was not accepted.";
      addMsg("system", resetStatus.textContent);
      return;
    }
    if (!body.session_id || !body.mission_id || !body.result) throw new Error("Incomplete reset response");
    sessionId = body.session_id;
    renderedSessionId = sessionId;
    localStorage.setItem("pgfr_chat_session", sessionId);
    if (window.PGFRSession) window.PGFRSession.set(body.mission_id);
    renderSessionId();
    for (const entry of body.transcript || []) {
      if (entry.role === "tool") addTool(entry);
      else if (entry.role === "assistant" && entry.content) addMsg("brain", entry.content);
    }
    const result = body.result;
    const verified = result.status === "verified" && result.dispatched === true && result.verified === true
      && !result.delivery_uncertain && !result.transport_error && !result.error;
    resetStatus.dataset.state = verified ? "verified"
      : ["refused", "failed"].includes(result.status) ? result.status : "uncertain";
    resetStatus.textContent = verified ? "Scene reset verified. Ready for the next task."
      : result.status === "refused" ? "Reset refused. " + (result.reason || "The scene is busy.")
      : result.status === "failed" ? "Reset was not verified. Check the scene before continuing."
      : "Reset outcome unknown. Check Isaac Sim before trying again.";
  } catch {
    resetStatus.dataset.state = "uncertain";
    resetStatus.textContent = "Reset outcome unknown. Check Isaac Sim before trying again.";
    addMsg("system", resetStatus.textContent);
  } finally {
    resetRunning = false;
    setChatRunning(chatRunning);
    loadSessions();
  }
};

// Chat is the initial view; restore its history and saved session on page load.
tabChat.click();
