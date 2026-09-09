// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import { evaluateDispatchPolicy } from "./policy.js";

describe("evaluateDispatchPolicy", () => {
  const move = {
    endpoint: "amr_franka_1",
    action: "move",
    color: "red",
    from: "table_1",
    destination: "red_rack",
  };
  const haul = {
    endpoint: "mobilebot",
    action: "pick_and_place",
    object_id: "tote",
    target_id: "rack_1",
  };

  it("allows a well-formed move to a permitted destination", () => {
    expect(evaluateDispatchPolicy(move)).toEqual({ allow: true });
  });

  it("blocks actions outside the allowlist (move and pick_and_place permitted)", () => {
    const decision = evaluateDispatchPolicy({ ...move, action: "weld" });
    expect(decision.allow).toBe(false);
    if (!decision.allow) {
      expect(decision.reason).toMatch(/not permitted/i);
    }
  });

  it("blocks a move missing a required parameter (precondition)", () => {
    const { destination: _omitted, ...partial } = move;
    const decision = evaluateDispatchPolicy(partial);
    expect(decision.allow).toBe(false);
    if (!decision.allow) {
      expect(decision.reason).toMatch(/destination/);
    }
  });

  it("blocks moving an object onto an unpermitted destination", () => {
    const decision = evaluateDispatchPolicy({ ...move, destination: "human" });
    expect(decision.allow).toBe(false);
    if (!decision.allow) {
      expect(decision.reason).toMatch(/prohibited/i);
    }
  });

  it("allows a well-formed pick_and_place (the AMR haul)", () => {
    expect(evaluateDispatchPolicy(haul)).toEqual({ allow: true });
  });

  it("blocks a pick_and_place missing target_id", () => {
    const { target_id: _omitted, ...partial } = haul;
    const decision = evaluateDispatchPolicy(partial);
    expect(decision.allow).toBe(false);
    if (!decision.allow) {
      expect(decision.reason).toMatch(/target_id/);
    }
  });

  it("blocks a pick_and_place onto an prohibited target", () => {
    const decision = evaluateDispatchPolicy({ ...haul, target_id: "human" });
    expect(decision.allow).toBe(false);
    if (!decision.allow) {
      expect(decision.reason).toMatch(/prohibited/i);
    }
  });
});
