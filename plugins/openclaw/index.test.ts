// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";
import plugin from "./index.js";
import type { evaluateDispatchPolicy } from "./policy.js";

type BeforeToolCallEvent = { toolName: string; params: Record<string, unknown> };
type BeforeToolCallResult =
  ReturnType<typeof evaluateDispatchPolicy> extends infer _T
    ? { block?: boolean; blockReason?: string } | undefined
    : never;
type Hook = (event: BeforeToolCallEvent) => BeforeToolCallResult;

function loadRegisteredTools(): string[] {
  const tools: string[] = [];
  const api = {
    registerTool: (tool: { name: string }) => tools.push(tool.name),
    logger: { info: () => {}, warn: () => {}, error: () => {}, debug: () => {} },
    on: () => {},
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  plugin.register(api as any);
  return tools;
}

function loadToolDescription(toolName: string): string {
  let description = "";
  const api = {
    registerTool: (tool: { name: string; description?: string }) => {
      if (tool.name === toolName) description = tool.description ?? "";
    },
    logger: { info: () => {}, warn: () => {}, error: () => {}, debug: () => {} },
    on: () => {},
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  plugin.register(api as any);
  return description;
}

/** Drive the plugin's register() with a stub api that captures its hooks. */
function loadBeforeToolCallHook(): Hook {
  const hooks: Record<string, Hook> = {};
  const api = {
    registerTool: () => {},
    logger: { info: () => {}, warn: () => {}, error: () => {}, debug: () => {} },
    on: (name: string, handler: Hook) => {
      hooks[name] = handler;
    },
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  plugin.register(api as any);
  return hooks.before_tool_call;
}

describe("floor before_tool_call enforcement", () => {
  it("registers exactly the tools declared by the plugin contract", () => {
    const manifest = JSON.parse(
      readFileSync(new URL("./openclaw.plugin.json", import.meta.url), "utf8"),
    ) as { contracts: { tools: string[] } };
    expect(loadRegisteredTools()).toEqual(manifest.contracts.tools);
    expect(manifest.contracts.tools).toEqual([
      "floor_state",
      "perceive",
      "dispatch_task",
      "reset_scene",
      "task_status",
      "verify",
    ]);
  });

  it("never advises retrying an unverified physical dispatch", () => {
    const description = loadToolDescription("dispatch_task");
    expect(description).toContain("physical outcome unknown");
    expect(description).toContain("Never resend it blindly");
    expect(description).toContain("fresh floor_state");
    expect(description).not.toContain("did NOT take effect");
    expect(description).not.toContain("retry up to twice");
  });

  const move = {
    endpoint: "amr_franka_1",
    action: "move",
    color: "red",
    from: "table_1",
    destination: "red_rack",
  };

  it("registers a before_tool_call hook", () => {
    expect(typeof loadBeforeToolCallHook()).toBe("function");
  });

  it("allows a permitted dispatch_task (returns no block)", () => {
    const hook = loadBeforeToolCallHook();
    expect(hook({ toolName: "dispatch_task", params: move })).toBeUndefined();
  });

  it("allows a pick_and_place dispatch_task (the AMR haul)", () => {
    const hook = loadBeforeToolCallHook();
    const haul = {
      endpoint: "mobilebot",
      action: "pick_and_place",
      object_id: "tote",
      target_id: "rack_1",
    };
    expect(hook({ toolName: "dispatch_task", params: haul })).toBeUndefined();
  });

  it("blocks an unpermitted dispatch_task with a reason", () => {
    const hook = loadBeforeToolCallHook();
    const result = hook({ toolName: "dispatch_task", params: { ...move, destination: "human" } });
    expect(result?.block).toBe(true);
    expect(result?.blockReason).toMatch(/prohibited/i);
  });

  it("blocks an unsupported action", () => {
    const hook = loadBeforeToolCallHook();
    const result = hook({ toolName: "dispatch_task", params: { ...move, action: "weld" } });
    expect(result?.block).toBe(true);
    expect(result?.blockReason).toMatch(/not permitted/i);
  });

  it("does not gate tools other than dispatch_task", () => {
    const hook = loadBeforeToolCallHook();
    expect(hook({ toolName: "perceive", params: { target: "table_1" } })).toBeUndefined();
    expect(hook({ toolName: "floor_state", params: {} })).toBeUndefined();
  });
});
