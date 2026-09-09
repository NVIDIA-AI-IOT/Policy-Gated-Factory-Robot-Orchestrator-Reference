# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""pgfr-workflows API — CRUD for workflow specs, dry-run/run, publish-as-skill.

This is the write-path sibling of pgfr-console: the console page's Workflows tab
talks to this service directly from the browser. Specs live as YAML files in
a git-versioned directory; runs execute through the seam's policy gate under
a per-run mission id.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Literal

import yaml
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from pydantic import BaseModel, Field

from .authoring import author
from .runner import Runner, RunnerSettings
from .scheduler import Scheduler
from .spec import TOOLS, Schedule, Workflow

log = logging.getLogger("pgfr_workflows")

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,48}$")
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _require_write_token(host: str, token: str | None, service: str) -> None:
    if host.strip().lower() not in _LOOPBACK_HOSTS and not token:
        raise RuntimeError(
            f"{service} refuses non-loopback host {host!r} without its write token"
        )

# CSRF defense for the state-changing endpoints. A cross-origin page can fire a
# no-preflight "simple" POST (CORS governs response-reading, not side effects),
# so requiring a custom header forces a preflight that the origin allowlist
# then blocks; we also check Origin/Referer server-side and (optionally) a
# shared token. This service can move a robot arm — it must not fire from a
# random page the operator happens to visit.
def _csrf_guard(
    request: Request,
    x_pgfr_workflows: str | None,
    allowed_origins: list[str],
    token: str | None,
) -> None:
    if x_pgfr_workflows is None:
        raise HTTPException(403, "missing X-PGFR-Workflows header (CSRF guard)")
    origin = request.headers.get("origin")
    if origin is not None and origin not in allowed_origins:  # exact match, not prefix
        raise HTTPException(403, f"origin {origin!r} not allowed")
    if token and x_pgfr_workflows != token:
        raise HTTPException(403, "bad CSRF token")


class RunRequest(BaseModel):
    params: Dict[str, Any] = {}


class AssistRequest(BaseModel):
    kind: Literal["workflow", "skill"]
    instruction: str = Field(min_length=1, max_length=8000)


class ScheduleRequest(BaseModel):
    interval_s: int = Field(ge=30, le=86400)
    enabled: bool = False
    params: Dict[str, Any] = {}


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not _NAME_RE.match(name):
            raise HTTPException(422, f"bad workflow name: {name!r}")
        return self.root / f"{name}.yaml"

    def list(self) -> list[Dict[str, Any]]:
        out = []
        for p in sorted(self.root.glob("*.yaml")):
            try:
                wf = Workflow.model_validate(yaml.safe_load(p.read_text()))
                out.append(
                    {
                        "name": wf.name,
                        "description": wf.description,
                        "steps": len(wf.steps),
                        "params": wf.params,
                    }
                )
            except Exception as exc:
                out.append({"name": p.stem, "error": str(exc)})
        return out

    def load(self, name: str) -> Workflow:
        path = self._path(name)
        if not path.exists():
            raise HTTPException(404, f"no workflow named {name!r}")
        return Workflow.model_validate(yaml.safe_load(path.read_text()))

    def save(self, wf: Workflow) -> None:
        self._path(wf.name).write_text(
            yaml.safe_dump(wf.model_dump(exclude_none=True), sort_keys=False)
        )

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not path.exists():
            raise HTTPException(404, f"no workflow named {name!r}")
        path.unlink()


_AUTO = object()  # sentinel: default -> auto-make a backend; explicit None -> none


def build_app(
    store: Store | None = None,
    runner: Runner | None = None,
    skills_dir: Path | None = None,
    backend: Any = _AUTO,
    scheduler: Scheduler | None = None,
    run_scheduler: bool | None = None,
) -> FastAPI:
    store = store or Store(Path(os.environ.get("PGFR_WORKFLOWS_DIR", "workflows")))
    runner = runner or Runner()
    skills_dir = skills_dir or Path(os.environ.get("PGFR_SKILLS_DIR", "skills"))
    if backend is _AUTO:
        try:
            from pgfr_chat.backends import make_backend

            backend = make_backend()
        except Exception:
            backend = None  # assist endpoint reports unavailable
    allowed_origins = os.environ.get(
        "PGFR_WORKFLOWS_CORS", "http://127.0.0.1:8600"
    ).split(",")
    csrf_token = os.environ.get("PGFR_WORKFLOWS_TOKEN")  # optional shared secret
    scheduler = scheduler or Scheduler(store, runner)
    if run_scheduler is None:
        run_scheduler = os.environ.get("PGFR_WORKFLOWS_SCHEDULER", "1") != "0"

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if run_scheduler:
            scheduler.start()
        try:
            yield
        finally:
            scheduler.stop()

    app = FastAPI(title="PGFR Workflows", lifespan=lifespan)
    # Non-* allowlist: only the console origin, and only the methods/headers we
    # use. A foreign origin's preflight for PUT/POST/DELETE is refused here; the
    # per-endpoint _csrf_guard closes the no-preflight simple-POST gap.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["content-type", "x-pgfr-workflows"],
    )

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "workflows_dir": str(store.root)}

    @app.get("/api/tools")
    async def tools() -> dict:
        return {"tools": TOOLS}

    @app.get("/api/workflows")
    async def list_workflows() -> dict:
        return {"workflows": store.list()}

    @app.get("/api/workflows/{name}")
    async def get_workflow(name: str) -> dict:
        return store.load(name).model_dump()

    def guard(request: Request, header: str | None) -> None:
        _csrf_guard(request, header, allowed_origins, csrf_token)

    @app.put("/api/workflows/{name}")
    async def save_workflow(
        name: str, wf: Workflow, request: Request,
        x_pgfr_workflows: str | None = Header(default=None),
    ) -> dict:
        guard(request, x_pgfr_workflows)
        if wf.name != name:
            raise HTTPException(422, "name in path and body must match")
        # The schedule is owned SOLELY by the set/delete-schedule endpoints — an
        # editor Save can never resurrect or clobber it via a stale client
        # snapshot (which would silently re-arm timed physical actuation).
        # Always preserve whatever schedule is currently on disk.
        existing = store._path(name)
        if existing.exists():
            try:
                prior = Workflow.model_validate(yaml.safe_load(existing.read_text()))
                wf.schedule = prior.schedule
            except Exception:
                wf.schedule = None
        else:
            wf.schedule = None
        store.save(wf)
        return {"saved": wf.name, "steps": len(wf.steps)}

    @app.delete("/api/workflows/{name}")
    async def delete_workflow(
        name: str, request: Request, x_pgfr_workflows: str | None = Header(default=None)
    ) -> dict:
        guard(request, x_pgfr_workflows)
        store.delete(name)
        return {"deleted": name}

    @app.post("/api/assist")
    async def assist(
        body: AssistRequest, request: Request,
        x_pgfr_workflows: str | None = Header(default=None),
    ) -> dict:
        # Guarded like the write path: it calls a model (cost) and produces an
        # artifact the operator will save. Returns a schema-VALIDATED draft only
        # — it never writes; the user saves via PUT/publish (which re-validate).
        guard(request, x_pgfr_workflows)
        if backend is None:
            raise HTTPException(503, "no model backend (set PGFR_CHAT_MODEL_URL / PGFR_CHAT_BACKEND)")
        try:
            return await author(backend, body.kind, body.instruction)
        except Exception as exc:
            # Log the detail server-side; do NOT echo it to the client — the
            # backend exception text can carry the internal model URL / payload.
            log.warning("assist backend error: %s: %s", type(exc).__name__, exc)
            raise HTTPException(502, "model backend error (see server logs)")

    @app.get("/api/schedules")
    async def list_schedules() -> dict:
        import time as _t

        return {"schedules": scheduler.schedules(_t.time())}

    @app.post("/api/workflows/{name}/schedule")
    async def set_schedule(
        name: str, body: ScheduleRequest, request: Request,
        x_pgfr_workflows: str | None = Header(default=None),
    ) -> dict:
        # A schedule can trigger physical actions on a timer — CSRF-guarded, and
        # the schedule is stored ON the workflow (re-validated by Store.save).
        guard(request, x_pgfr_workflows)
        wf = store.load(name)
        wf.schedule = Schedule(interval_s=body.interval_s, enabled=body.enabled,
                               params=body.params)
        store.save(wf)
        return {"scheduled": name, "interval_s": body.interval_s, "enabled": body.enabled}

    @app.delete("/api/workflows/{name}/schedule")
    async def clear_schedule(
        name: str, request: Request, x_pgfr_workflows: str | None = Header(default=None)
    ) -> dict:
        guard(request, x_pgfr_workflows)
        wf = store.load(name)
        wf.schedule = None
        store.save(wf)
        scheduler.last_run.pop(name, None)
        scheduler.last_ok.pop(name, None)
        scheduler._seeded.discard(name)
        return {"unscheduled": name}

    @app.post("/api/workflows/{name}/dry-run")
    async def dry_run(name: str, body: RunRequest) -> dict:
        return runner.dry_run(store.load(name), body.params)  # read-only, no guard

    @app.post("/api/workflows/{name}/run")
    async def run(
        name: str, body: RunRequest, request: Request,
        x_pgfr_workflows: str | None = Header(default=None),
    ) -> dict:
        guard(request, x_pgfr_workflows)
        return await runner.run(store.load(name), body.params)

    @app.post("/api/workflows/{name}/publish")
    async def publish(
        name: str, request: Request, x_pgfr_workflows: str | None = Header(default=None)
    ) -> dict:
        guard(request, x_pgfr_workflows)
        wf = store.load(name)
        manifest = wf.to_skill_manifest()

        # Gate the write on the conformance kit if present. If it is absent we
        # report conformance="skipped" (never a false "passed") so callers are
        # not misled into trusting an unchecked manifest.
        conformance = "skipped"
        try:
            from pgfr_conformance.kit import check_skill_manifest  # type: ignore
        except ImportError:
            check_skill_manifest = None  # type: ignore
        if check_skill_manifest is not None:
            import os
            import tempfile

            fd, tmp_name = tempfile.mkstemp(suffix=".yaml")
            tmp = Path(tmp_name)
            try:
                tmp.write_text(yaml.safe_dump(manifest, sort_keys=False))
                failures = [r.name for r in check_skill_manifest(str(tmp)) if not r.passed]
            finally:
                os.close(fd)
                tmp.unlink(missing_ok=True)
            if failures:
                raise HTTPException(422, {"conformance_failures": failures})
            conformance = "passed"

        skill_dir = skills_dir / f"wf-{wf.name}"
        # Never overwrite a directory this service did not create (a stray
        # hand-authored skill happening to start with wf-).
        marker = skill_dir / ".pgfr-workflows-owned"
        if skill_dir.exists() and not marker.exists():
            raise HTTPException(409, f"{skill_dir} exists and is not workflow-owned")
        skill_dir.mkdir(parents=True, exist_ok=True)
        marker.write_text("generated by pgfr-workflows publish\n")
        manifest_path = skill_dir / "manifest.yaml"
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
        return {
            "published": wf.name,
            "conformance": conformance,
            "manifest": str(manifest_path),
        }

    return app


def main() -> None:
    import uvicorn

    host = os.environ.get("PGFR_WORKFLOWS_HOST", "127.0.0.1")
    port = int(os.environ.get("PGFR_WORKFLOWS_PORT", "8610"))
    _require_write_token(
        host, os.environ.get("PGFR_WORKFLOWS_TOKEN"), "PGFR Workflows"
    )
    uvicorn.run(build_app(runner=Runner(RunnerSettings())), host=host, port=port)


if __name__ == "__main__":
    main()
