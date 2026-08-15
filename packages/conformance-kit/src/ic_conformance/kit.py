# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Industrial Claw conformance kit — the certification bar for seam implementations.

Black-box: point it at any floor-service endpoint and it verifies the contract —
schemas, policy gate, honesty semantics. "New adapter = pass the kit."

    ic-conformance run --target http://127.0.0.1:8766 [--target-region conveyor_1]

All default checks are READ-ONLY or policy-refused by design (nothing moves).
Exit code 0 = certified; 1 = failures (listed).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _post(client: Any, path: str, body: dict, headers: dict | None = None) -> Any:
    return client.post(path, json=body, headers={"Content-Type": "application/json", **(headers or {})})


def check_health(client: Any) -> CheckResult:
    r = client.get("/v1/health")
    ok = r.status_code in (200, 503)
    body = r.json() if ok else {}
    ok = ok and "status" in body and "backend" in body
    return CheckResult("health endpoint (GET /v1/health, degraded-aware)", ok,
                       f"status={r.status_code} body_keys={sorted(body)[:5]}")


def check_openapi(client: Any) -> CheckResult:
    r = client.get("/openapi.json")
    ok = r.status_code == 200 and "/v1/dispatch" in r.json().get("paths", {})
    return CheckResult("OpenAPI contract served (/openapi.json)", ok, f"status={r.status_code}")


def check_floor_state(client: Any) -> CheckResult:
    r = _post(client, "/v1/floor-state", {})
    body = r.json()
    ok = (r.status_code == 200 and isinstance(body.get("endpoints"), list)
          and body.get("_meta", {}).get("api") == "v1")
    return CheckResult("floor-state contract (+_meta freshness)", ok,
                       f"endpoints={len(body.get('endpoints', []))}")


def check_request_id(client: Any) -> CheckResult:
    r = _post(client, "/v1/floor-state", {})
    rid = r.headers.get("x-request-id", "")
    return CheckResult("request traceability (x-request-id header)", bool(rid), f"rid={rid or 'MISSING'}")


def check_policy_unknown_action(client: Any) -> CheckResult:
    r = _post(client, "/v1/dispatch", {"action": "__conformance_probe__", "endpoint": "none"})
    body = r.json()
    ok = body.get("dispatched") is False and str(body.get("reason", "")).startswith("policy:")
    return CheckResult("policy gate: unknown action refused", ok, f"reason={body.get('reason', '')[:60]}")


def check_policy_missing_params(client: Any) -> CheckResult:
    r = _post(client, "/v1/dispatch", {"action": "move", "endpoint": "any"})
    body = r.json()
    ok = body.get("dispatched") is False and "missing required" in str(body.get("reason", ""))
    return CheckResult("policy gate: required params enforced", ok, f"reason={body.get('reason', '')[:60]}")


def check_policy_operator_gate(client: Any) -> CheckResult:
    r = _post(client, "/v1/dispatch", {"action": "reset", "endpoint": "any"})
    body = r.json()
    ok = body.get("dispatched") is False and "operator-only" in str(body.get("reason", ""))
    return CheckResult("policy gate: operator-only actions gated", ok, f"reason={body.get('reason', '')[:60]}")


def check_validation_errors(client: Any) -> CheckResult:
    r = _post(client, "/v1/perceive", {})
    return CheckResult("malformed requests die at the door (422)", r.status_code == 422,
                       f"status={r.status_code}")


def make_perceive_check(region: str) -> Callable[[Any], CheckResult]:
    def check_perceive(client: Any) -> CheckResult:
        r = _post(client, "/v1/perceive", {"target": region})
        body = r.json()
        ok = (r.status_code == 200 and "_meta" in body
              and ("vision" in body or "counts" in body))
        return CheckResult(f"perceive contract (target={region})", ok, f"keys={sorted(body)[:6]}")
    return check_perceive


DEFAULT_CHECKS: list[Callable[[Any], CheckResult]] = [
    check_health,
    check_openapi,
    check_floor_state,
    check_request_id,
    check_policy_unknown_action,
    check_policy_missing_params,
    check_policy_operator_gate,
    check_validation_errors,
]


def run_checks(client: Any, region: str = "conveyor_1") -> list[CheckResult]:
    checks = DEFAULT_CHECKS + [make_perceive_check(region)]
    results = []
    for c in checks:
        try:
            results.append(c(client))
        except Exception as exc:
            results.append(CheckResult(getattr(c, "__name__", str(c)), False, f"error: {exc}"))
    return results


async def check_mcp_server(command: list[str]) -> list[CheckResult]:
    """Certify an MCP server over stdio: instructions + annotations + tool hygiene."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    results: list[CheckResult] = []
    params = StdioServerParameters(command=command[0], args=command[1:])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            instr = init.instructions or ""
            results.append(CheckResult("instructions shipped in the handshake",
                                       len(instr) > 80 and "REPLACE ME" not in instr,
                                       f"{len(instr)} chars"))
            tools = (await s.list_tools()).tools
            results.append(CheckResult("server exposes tools", len(tools) > 0, f"{len(tools)} tools"))
            for t in tools:
                ann = t.annotations
                ok = bool(t.description) and ann is not None and ann.title is not None                     and ann.readOnlyHint is not None
                results.append(CheckResult(f"tool hygiene: {t.name}", ok,
                                           "description+annotations" if ok else "missing description/annotations"))
    return results


def main() -> int:
    import argparse

    import httpx

    ap = argparse.ArgumentParser(prog="ic-conformance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run the conformance checks against a live seam")
    run.add_argument("--target", required=True, help="e.g. http://127.0.0.1:8766")
    run.add_argument("--target-region", default="conveyor_1")
    mcp_p = sub.add_parser("mcp", help="certify an MCP server over stdio")
    mcp_p.add_argument("--command", nargs="+", required=True, help="server launch command")
    skill_p = sub.add_parser("skill", help="validate a skill manifest")
    skill_p.add_argument("--manifest", required=True)
    args = ap.parse_args()

    if args.cmd == "mcp":
        import asyncio

        results = asyncio.run(check_mcp_server(args.command))
        return _report(results)
    if args.cmd == "skill":
        results = check_skill_manifest(args.manifest)
        return _report(results)

    with httpx.Client(base_url=args.target, timeout=90.0) as client:
        results = run_checks(client, args.target_region)
    return _report(results)


def check_skill_manifest(path: str) -> list[CheckResult]:
    """Validate a skill manifest: required fields + only policy-known agent actions."""
    import yaml

    results: list[CheckResult] = []
    try:
        m = yaml.safe_load(open(path)) or {}
    except Exception as exc:
        return [CheckResult("manifest parses", False, str(exc))]
    for f in ("name", "version", "description", "requires_tools", "allowed_actions", "done_criteria"):
        results.append(CheckResult(f"manifest field: {f}", f in m and m[f] not in (None, "", []),
                                   str(m.get(f, "MISSING"))[:50]))
    agent_actions = {"move", "pick_and_place", "inspect", "navigate_to"}
    extra = set(m.get("allowed_actions", [])) - agent_actions
    results.append(CheckResult("allowed_actions are agent-class policy actions", not extra,
                               f"violations: {sorted(extra)}" if extra else "ok"))
    return results


def _report(results: list[CheckResult]) -> int:
    width = max(len(r.name) for r in results)
    failed = 0
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        failed += 0 if r.passed else 1
        print(f"  [{mark}] {r.name.ljust(width)}  {r.detail}")
    total = len(results)
    print(f"\n{'CERTIFIED' if failed == 0 else 'NOT CONFORMANT'}: {total - failed}/{total} checks passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
