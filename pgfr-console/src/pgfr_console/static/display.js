// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Escape untrusted values used in HTML text and quoted attributes.
export function escapeHtml(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

// Display labels only. API requests and stored session identities keep their original IDs.
const sessions = new Map();
const identity = (record) => typeof record === "string" ? record : record?.mission_id || record?.id || "";

export function rememberSessions(records) {
  for (const record of records || []) {
    if (record.mission_id) sessions.set(record.mission_id, {...sessions.get(record.mission_id), ...record});
    if (record.id) sessions.set(record.id, {...sessions.get(record.id), ...record});
  }
}

export function sessionTitle(record) {
  const id = identity(record);
  const title = (typeof record === "object" && record?.title) || sessions.get(id)?.title;
  if (typeof title === "string" && title.trim()) return title.trim();
  if (!id) return "New chat";
  if (/^(?:chat-)?[a-f0-9]{8,}$/i.test(id)) return "Conversation";
  const words = id.replace(/^(?:wf|chat)-/, "").split(/[-_]+/).filter((word) =>
    word && !/^[a-f0-9]{8,}$/i.test(word) && !/^\d{8}(?:T\d{6}Z?)?$/i.test(word));
  const names = {groot: "GR00T", gr00t: "GR00T", amr: "AMR", vlm: "VLM", gpu: "GPU", openclaw: "OpenClaw"};
  const label = words.map((word) => names[word.toLowerCase()] || word).join(" ");
  return label ? label[0].toUpperCase() + label.slice(1) : "Task";
}

export function sessionDate(record) {
  const item = typeof record === "object" && record ? record : {};
  const cached = sessions.get(identity(record)) || {};
  const value = item.started_at || item.updated || item.created || cached.updated || cached.created;
  if (!value) return "";
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  if (!Number.isFinite(date.getTime())) return "";
  return date.toLocaleString(undefined, {month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    ...(date.getFullYear() !== new Date().getFullYear() ? {year: "numeric"} : {})});
}

export function verificationSummary(verified, total) {
  if (typeof total !== "number" || typeof verified !== "number") return "Verification unavailable";
  if (total === 0) return "No robot actions";
  if (verified === total) return `${total} action${total === 1 ? "" : "s"} verified`;
  return `${verified} of ${total} actions verified`;
}
