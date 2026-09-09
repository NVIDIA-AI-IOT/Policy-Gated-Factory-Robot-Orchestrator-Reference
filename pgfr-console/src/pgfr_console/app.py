# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PGFR Console — read-only observability plane over the floor seam.

Serves the aggregator API plus the no-build SPA. Holds no dispatch
capability: every route is a GET and every upstream call is a read.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .aggregator import Aggregator, Settings

STATIC_DIR = Path(__file__).parent / "static"


def build_app(aggregator: Aggregator | None = None) -> FastAPI:
    agg = aggregator or Aggregator()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def loop() -> None:
            while True:
                try:
                    await agg.poll_once()
                except Exception:
                    pass
                await asyncio.sleep(agg.settings.poll_interval_s)

        task = asyncio.create_task(loop())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="PGFR Console", lifespan=lifespan)
    app.state.aggregator = agg

    @app.middleware("http")
    async def security_headers(request, call_next):
        # Defense-in-depth behind the escaping: no inline eval, connect only to
        # self + the workflows service, deny framing.
        resp = await call_next(request)
        wf = os.environ.get("PGFR_WORKFLOWS_URL", "http://127.0.0.1:8610")
        chat = os.environ.get("PGFR_CHAT_URL", "http://127.0.0.1:8620")
        # The aggregator can keep using a loopback Chat URL while browsers use
        # an explicitly exposed trusted-LAN endpoint. Keeping these settings
        # separate avoids routing server-to-server health polling over the LAN.
        chat_public = os.environ.get("PGFR_CHAT_PUBLIC_URL") or chat
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            f"connect-src 'self' {wf} {chat_public}; "
            f"img-src 'self' data: {chat_public}; "
            "frame-ancestors 'none'"
        )
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "role": "read-only observability"}

    @app.get("/api/topology")
    async def topology() -> dict:
        snap = await agg.snapshot()
        if not snap.get("nodes"):
            snap = await agg.poll_once()
        return snap

    @app.get("/api/missions")
    async def missions(limit: int = 20) -> dict:
        return await agg.missions(limit=limit)

    @app.get("/api/chat-sessions")
    async def chat_sessions() -> dict:
        return await agg.chat_sessions()

    @app.get("/api/missions/{mission_id}")
    async def mission_detail(mission_id: str, limit: int = 200) -> dict:
        return await agg.mission_detail(mission_id, limit=limit)

    @app.get("/api/assurance")
    async def assurance() -> dict:
        # Verification and auditability proven from the audit store (read-only).
        return await agg.assurance()

    @app.get("/api/inspect")
    async def inspect(limit: int = 30) -> dict:
        # The audit feed that imprints inspectability: every recent floor op with
        # its full request, full result, physics-verified flag, timing, and the
        # exact frame the VLM saw — the data a normal agent harness discards.
        return await agg.inspect(limit=limit)

    @app.get("/api/gpu")
    async def gpu(
        minutes: int = 60,
        mission_id: str | None = None,
        t_from: str | None = None,
        t_to: str | None = None,
    ) -> dict:
        # Per-model GPU memory/utilization over time (read-only exporter proxy).
        # mission_id scopes the series to that session's journal window; from/to
        # (epoch or ISO) scopes to an explicit window; else the live ring.
        if mission_id:
            return await agg.gpu_for_mission(mission_id)
        return await agg.gpu_series(minutes=minutes, t_from=t_from, t_to=t_to)

    @app.get("/api/frame/{request_id}")
    async def frame(request_id: str):
        import re

        from fastapi.responses import Response

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
            raise HTTPException(422, "bad request_id")
        seam = agg.settings.seam_url
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{seam}/v1/frames/{request_id}")
        except Exception:
            raise HTTPException(502, "seam unreachable")
        if r.status_code != 200:
            raise HTTPException(404, "no frame")
        return Response(content=r.content, media_type="image/jpeg")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def main() -> None:
    import uvicorn

    settings = Settings()
    host = os.environ.get("PGFR_CONSOLE_HOST", "127.0.0.1")
    port = int(os.environ.get("PGFR_CONSOLE_PORT", "8600"))
    uvicorn.run(build_app(Aggregator(settings)), host=host, port=port)


if __name__ == "__main__":
    main()
