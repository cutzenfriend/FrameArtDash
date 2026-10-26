"""Daemon: scheduling loop plus a small HTTP API."""

from __future__ import annotations

import asyncio
import logging
import signal

from aiohttp import web

from frameartdash import __version__
from frameartdash.service import Service

log = logging.getLogger(__name__)

SERVICE_KEY = web.AppKey("service", Service)
LOOP_KEY = web.AppKey("loop", asyncio.Task)

# Keeps references to fire-and-forget refresh tasks so they are not garbage collected.
_background: set[asyncio.Task] = set()


def _is_true(value: str | None) -> bool:
    return (value or "").lower() in ("1", "true", "yes", "on")


async def refresh(request: web.Request) -> web.Response:
    """Run a cycle now. Forced by default (ignores ACTIVE_HOURS and the diff check)."""
    service = request.app[SERVICE_KEY]
    force = request.query.get("force", "true").lower() not in ("0", "false", "no", "off")
    if _is_true(request.query.get("wait")):
        result = await service.run_cycle(force=force)
        return web.json_response(result.as_dict(), status=500 if result.status == "error" else 200)
    if service.lock.locked():
        return web.json_response({"status": "busy"}, status=409)
    task = asyncio.create_task(service.run_cycle(force=force))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return web.json_response({"status": "accepted"}, status=202)


async def healthz(request: web.Request) -> web.Response:
    service = request.app[SERVICE_KEY]
    loop_task = request.app.get(LOOP_KEY)
    alive = loop_task is not None and not loop_task.done()
    body = {
        "status": "ok" if alive else "loop stopped",
        "version": __version__,
        "last_success": service.last_success,
        "last_result": service.last_result.as_dict() if service.last_result else None,
    }
    return web.json_response(body, status=200 if alive else 503)


async def last_image(request: web.Request) -> web.Response:
    jpeg = request.app[SERVICE_KEY].last_jpeg
    if jpeg is None:
        return web.json_response({"status": "no image rendered yet"}, status=404)
    return web.Response(body=jpeg, content_type="image/jpeg", headers={"Cache-Control": "no-store"})


def build_app(service: Service) -> web.Application:
    app = web.Application()
    app[SERVICE_KEY] = service
    app.router.add_post("/refresh", refresh)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/last.jpg", last_image)

    async def start_loop(app: web.Application):
        app[LOOP_KEY] = asyncio.create_task(service.run_forever(), name="fad-loop")
        yield
        app[LOOP_KEY].cancel()
        try:
            await app[LOOP_KEY]
        except asyncio.CancelledError:
            pass

    app.cleanup_ctx.append(start_loop)
    return app


async def serve(service: Service) -> None:
    app = build_app(service)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    port = service.settings.http_port
    if port:
        await web.TCPSite(runner, "0.0.0.0", port).start()
        log.info("HTTP API listening on :%d (POST /refresh, GET /healthz, GET /last.jpg)", port)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - Windows
            pass
    try:
        await stop.wait()
    finally:
        log.info("Shutting down")
        await runner.cleanup()
