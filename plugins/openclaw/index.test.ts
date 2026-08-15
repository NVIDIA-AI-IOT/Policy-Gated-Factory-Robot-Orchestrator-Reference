// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

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
  it("registers the operator reset tool", () => {
    expect(loadRegisteredTools()).toContain("reset_scene");
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

  it("allows a safe dispatch_task (returns no block)", () => {
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

  it("blocks an unsafe dispatch_task with a reason", () => {
    const hook = loadBeforeToolCallHook();
    const result = hook({ toolName: "dispatch_task", params: { ...move, destination: "human" } });
    expect(result?.block).toBe(true);
    expect(result?.blockReason).toMatch(/unsafe/i);
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
