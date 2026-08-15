// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { execFile } from "node:child_process";
import { rm } from "node:fs/promises";
import { promisify } from "node:util";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { Type } from "typebox";
import { evaluateDispatchPolicy } from "./policy.js";

// Granular factory-floor primitives IC composes to run missions. The real
// behaviour lives in the Python engine (PerceptionAgent / ActionAgent over a
// persistent mock floor); this plugin is a thin bridge that shells out to the
// `industrial_claw` CLI and relays its JSON. The floor file is the swappable
// "world" — replace it with a ROS 2 / Isaac Sim backend and these contracts
// stay the same.
//
// Wiring (set for the gateway via `launchctl setenv`):
//   IC_FLOOR_CLI    absolute path to the industrial_claw binary
//                   (e.g. <repo>/ic-spine/.venv/bin/industrial_claw)
//   IC_FLOOR_STATE  path to the shared floor-state JSON file the primitives read/write

const execFileAsync = promisify(execFile);

const text = (obj: unknown) => ({
  content: [{ type: "text" as const, text: JSON.stringify(obj, null, 2) }],
});

type FloorResult = { ok: true; data: unknown } | { ok: false; error: string };

async function runFloor(args: string[]): Promise<FloorResult> {
  const bin = process.env.IC_FLOOR_CLI?.trim();
  if (!bin) {
    return {
      ok: false,
      error:
        "IC_FLOOR_CLI is not set — point it at the industrial_claw binary " +
        "(e.g. <repo>/ic-spine/.venv/bin/industrial_claw).",
    };
  }
  try {
    const { stdout } = await execFileAsync(bin, args, {
      env: process.env,
      // Long enough for the slowest floor action (the AMR haul ~2min). Sits just above
      // the backend's own result timeout so a genuine stall returns JSON, not a SIGKILL.
      timeout: Number(process.env.IC_FLOOR_TIMEOUT_MS) || 200_000,
      maxBuffer: 1024 * 1024,
    });
    return { ok: true, data: JSON.parse(stdout) };
  } catch (err) {
    // execFile rejects on a non-zero exit, but the CLI still prints structured
    // JSON on stdout for expected failures (e.g. dispatch dispatched:false → exit 2).
    const e = err as { stdout?: string; stderr?: string; message?: string };
    if (e.stdout) {
      try {
        return { ok: true, data: JSON.parse(e.stdout) };
      } catch {
        /* fall through to the error path */
      }
    }
    return { ok: false, error: (e.stderr || e.message || "floor CLI failed").trim() };
  }
}

const relay = (r: FloorResult) => text(r.ok ? r.data : { error: r.error });

// Fetch the exact camera frame the VLM judged for a perceive/verify op (the
// seam journals it per request id and serves it read-only). Best-effort: any
// failure degrades to the text-only result, never to an error.
async function fetchFrameB64(rid: string): Promise<string | null> {
  const svc = process.env.IC_FLOOR_SERVICE?.trim();
  if (!svc || !/^[A-Za-z0-9_-]{1,64}$/.test(rid)) return null;
  try {
    const res = await fetch(new URL(`/v1/frames/${rid}`, svc), {
      signal: AbortSignal.timeout(5_000),
    });
    if (!res.ok) return null;
    const buf = Buffer.from(await res.arrayBuffer());
    if (buf.length === 0 || buf.length > 4 * 1024 * 1024) return null;
    return buf.toString("base64");
  } catch {
    return null;
  }
}

// relay + the frame the VLM saw, shaped for the Control UI's toolResult
// renderer: it keeps only text/attachment/canvas blocks (raw `image` blocks
// render in assistant messages only — verified against chat-page.js), and an
// attachment needs {url, kind, label}; a data: URL satisfies the CSP.
async function relayWithFrame(r: FloorResult) {
  if (!r.ok) return text({ error: r.error });
  const meta = (r.data as { _meta?: { request_id?: unknown } })?._meta;
  const rid = typeof meta?.request_id === "string" ? meta.request_id : null;
  const b64 = rid ? await fetchFrameB64(rid) : null;
  if (!b64) return text(r.data);
  return {
    content: [
      { type: "text" as const, text: JSON.stringify(r.data, null, 2) },
      {
        type: "attachment" as const,
        attachment: {
          // Self-contained data URL — no extra infrastructure, no proxy.
          url: `data:image/jpeg;base64,${b64}`,
          kind: "image",
          label: `frame the VLM saw (${rid})`,
          mimeType: "image/jpeg",
        },
      },
    ],
  } as unknown as ReturnType<typeof text>;
}

async function callService(base: string, path: string, body: unknown): Promise<FloorResult> {
  try {
    const res = await fetch(new URL(path, base), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(Number(process.env.IC_FLOOR_TIMEOUT_MS) || 200_000),
    });
    // The service returns structured JSON even for expected failures (4xx).
    return { ok: true, data: await res.json() };
  } catch (err) {
    return { ok: false, error: (err as Error).message || "floor service request failed" };
  }
}

// Route a floor op to the persistent service (IC_FLOOR_SERVICE) when set — that's
// the long-lived ROS 2 node — else spawn the per-call CLI (mock).
async function floorOp(
  servicePath: string,
  serviceBody: unknown,
  cliArgs: string[],
): Promise<FloorResult> {
  const svc = process.env.IC_FLOOR_SERVICE?.trim();
  return svc ? callService(svc, servicePath, serviceBody) : runFloor(cliArgs);
}

export default definePluginEntry({
  id: "industrial-claw-floor",
  name: "Industrial Claw Floor",
  description:
    "Granular factory-floor primitives IC composes to run missions: perceive, dispatch_task, floor_state. Backed by the Python engine over a persistent mock floor until ROS 2 / Isaac Sim is wired.",
  register(api) {
    // Reset the mock floor when the gateway (re)starts so each relaunch is a
    // fresh scene; within a session dispatch_task → perceive still persists.
    const statePath = process.env.IC_FLOOR_STATE?.trim();
    if (statePath) {
      void rm(statePath, { force: true }).catch(() => {});
    }

    api.registerTool({
      name: "floor_state",
      description:
        "List the floor's action endpoints (robots / AGVs / conveyors) with status, battery, and location. Call this to see what you can dispatch to.",
      parameters: Type.Object({}),
      async execute() {
        return relay(await floorOp("/floor-state", {}, ["floor-state"]));
      },
    });

    api.registerTool({
      name: "perceive",
      description:
        "Look at a floor target with a camera + vision and return a structured observation, with the camera frame attached. Targets map to FOUR PHYSICALLY DISTINCT cameras — a whole-floor survey perceives one of each, never the same camera twice: 'conveyor_1' (left band), 'conveyor_2' (RIGHT band — a different camera; the right workcell is invisible without it), 'table_1' (wide overhead: blocks AND both totes), 'rack_1' (the shelf). 'tote'/'tote_r' are close crops of the left/right band cameras. Block COUNTS come from the symbolic state in the result, never from counting a frame: up to TWO identical blocks per color, and one view may show only part of the table. Shapes: red=cube, blue=cylinder, green=brick — expected, not a discrepancy.",
      parameters: Type.Object({
        target: Type.String({ description: "What to look at, e.g. 'table_1'." }),
      }),
      async execute(_id, params) {
        const target = String(params.target);
        return relayWithFrame(await floorOp("/v1/perceive", { target }, ["perceive", target]));
      },
    });

    api.registerTool({
      name: "dispatch_task",
      description:
        "Send ONE action to ONE endpoint. Two verbs: `move` a colored block from a source to a destination (args: color, from, destination), or `pick_and_place` an object onto a target (args: object_id, target_id) — e.g. an AMR hauling a loaded tote to a rack. ACTS then CONFIRMS: it re-checks the floor and returns `verified` (true only if the effect actually landed) plus `verification` evidence. If `dispatched` is false or `verified` is false, the action did NOT take effect — retry up to twice (same or another endpoint); if it still isn't verified, stop and report the failure to the operator, do not claim success. EXCEPTION: with wait=false the response is {goal_id, status:'running'} and has NO verified field — that is NOT a failure; never retry an async dispatch, poll task_status instead.",
      parameters: Type.Object({
        endpoint: Type.String({
          description: "Endpoint id from floor_state, e.g. 'amr_franka_1'.",
        }),
        action: Type.String({ description: "Action verb: 'move' or 'pick_and_place'." }),
        color: Type.Optional(
          Type.String({ description: "move: block color to move, e.g. 'red' or 'green'." }),
        ),
        from: Type.Optional(Type.String({ description: "move: source location, e.g. 'table_1'." })),
        destination: Type.Optional(
          Type.String({ description: "move: destination, e.g. 'red_rack'." }),
        ),
        object_id: Type.Optional(
          Type.String({ description: "pick_and_place: object to move, e.g. 'tote'." }),
        ),
        target_id: Type.Optional(
          Type.String({ description: "pick_and_place: where to place it, e.g. 'rack_1'." }),
        ),
        backend: Type.Optional(
          Type.String({
            description:
              "move only: 'groot' routes the pick to the learned GR00T policy stack " +
              "(per-color specialists); omit for the scripted controller.",
          }),
        ),
        wait: Type.Optional(
          Type.Boolean({
            description:
              "false = async: returns a goal_id immediately (robot keeps working); " +
              "poll task_status until done. Default true = wait for the verified result.",
          }),
        ),
      }),
      async execute(_id, params) {
        // Env-gated default: route moves through the learned policy stack.
        // Explicit model choice wins; injected value lands in the journal.
        const defaultBackend = process.env.IC_DEFAULT_BACKEND;
        if (defaultBackend && params.action === "move" && params.backend === undefined) {
          params = { ...params, backend: defaultBackend };
        }
        const args = [
          "dispatch",
          "--endpoint",
          String(params.endpoint),
          "--action",
          String(params.action),
        ];
        if (params.color) args.push("--color", String(params.color));
        if (params.from) args.push("--from", String(params.from));
        if (params.destination) args.push("--destination", String(params.destination));
        if (params.object_id) args.push("--object-id", String(params.object_id));
        if (params.target_id) args.push("--target-id", String(params.target_id));
        const body = {
          endpoint: params.endpoint,
          action: params.action,
          color: params.color,
          from: params.from,
          destination: params.destination,
          object_id: params.object_id,
          target_id: params.target_id,
          backend: params.backend,
          wait: params.wait,
        };
        return relay(await floorOp("/dispatch", body, args));
      },
    });

    api.registerTool({
      name: "reset_scene",
      description:
        "OPERATOR: reset the current hardened Isaac scene to its configured staged state. " +
        "Use only when the user explicitly asks to reset or between demo takes. " +
        "Refuses while a task is running.",
      parameters: Type.Object({}),
      async execute(_id) {
        const svc = process.env.IC_FLOOR_SERVICE?.trim();
        if (!svc) return relay({ ok: false, error: "reset_scene needs IC_FLOOR_SERVICE" });
        try {
          const res = await fetch(new URL("/v1/dispatch", svc), {
            method: "POST",
            headers: { "content-type": "application/json", "x-role": "operator" },
            body: JSON.stringify({
              endpoint: "mobilebot",
              action: "reset_scene",
              scene_profile: "groot_three_object",
              arm: "both",
              color: "red",
              layout_left: 3,
              layout_right: 3,
              seed: 31302,
            }),
            signal: AbortSignal.timeout(60_000),
          });
          return relay({ ok: true, data: await res.json() });
        } catch (err) {
          return relay({ ok: false, error: (err as Error).message || "reset failed" });
        }
      },
    });

    api.registerTool({
      name: "task_status",
      description:
        "Check an ASYNC dispatch (dispatch_task with wait=false): returns status " +
        "'running' | 'done' (with success+verified) | 'unknown'. Poll this instead of " +
        "blocking; report honestly — 'running' is not success.",
      parameters: Type.Object({
        goal_id: Type.String({ description: "goal_id returned by the async dispatch." }),
      }),
      async execute(_id, params) {
        const svc = process.env.IC_FLOOR_SERVICE?.trim();
        if (!svc) return relay({ ok: false, error: "task_status needs IC_FLOOR_SERVICE" });
        try {
          const res = await fetch(new URL(`/v1/tasks/${encodeURIComponent(String(params.goal_id))}`, svc), {
            signal: AbortSignal.timeout(15_000),
          });
          return relay({ ok: true, data: await res.json() });
        } catch (err) {
          return relay({ ok: false, error: (err as Error).message || "task_status failed" });
        }
      },
    });

    api.registerTool({
      name: "verify",
      description:
        "VISUALLY confirm a yes/no question about the floor with a camera + VLM. " +
        "Ask only what the region camera can decide: cube-in-tote and cube-on-conveyor " +
        "read well (region-cropped); the rack camera sees shelf EDGES — 'is a gray tote " +
        "on the rack?' works, but COUNTING totes or seeing tote CONTENTS on the rack does " +
        "not. For tote counts on the rack, trust floor_state's tote_on_rack and " +
        "tote_r_on_rack fields (physics ground truth) and cite them. Use it AFTER an action to check the effect actually happened — e.g. \"is the blue block in the blue tote compartment?\" or \"is the tote on the rack?\". Choose the camera via `region`: 'conveyor_1'/'table_1' (table cam), 'rack_1' (rack cam), 'tote' (zoom cam). Returns answer ('yes'|'no'|'unknown') + evidence; 'no'/'unknown' means NOT confirmed.",
      parameters: Type.Object({
        predicate: Type.String({
          description: "The yes/no question to check, e.g. 'is the tote on the rack?'.",
        }),
        region: Type.Optional(
          Type.String({ description: "Area/camera to look at: conveyor_1 | rack_1 | tote." }),
        ),
      }),
      async execute(_id, params) {
        const predicate = String(params.predicate);
        const args = ["verify", predicate];
        if (params.region) args.push("--region", String(params.region));
        return relayWithFrame(
          await floorOp("/v1/verify", { predicate, region: params.region }, args),
        );
      },
    });

    // Enforcement: gate every dispatch_task BEFORE it reaches the floor. IC stays
    // agentic (it composes the primitives freely) but the policy is a hard guardrail
    // — unsafe verbs, malformed moves, and unsafe destinations are blocked here, and
    // every decision is traced.
    api.on("before_tool_call", (event) => {
      if (event.toolName !== "dispatch_task") {
        return;
      }
      const decision = evaluateDispatchPolicy(event.params);
      if (!decision.allow) {
        api.logger.warn(
          `[floor-policy] BLOCK dispatch_task — ${decision.reason} :: ${JSON.stringify(event.params)}`,
        );
        return {
          block: true,
          blockReason: `Floor safety policy blocked this action: ${decision.reason}`,
        };
      }
      api.logger.info(
        `[floor-policy] ALLOW dispatch_task ${String(event.params.action)} → ${String(event.params.endpoint)}`,
      );
    });
  },
});
