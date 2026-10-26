"""Web UI and HTTP API. Runs the scheduling loop alongside."""

from __future__ import annotations

import asyncio
import collections
import logging
import signal
import time
from importlib import resources

from aiohttp import web

from frameartdash import __version__, frame as frame_mod
from frameartdash.auth import COOKIE, SESSION_DAYS, Auth
from frameartdash.backgrounds import BackgroundError, Backgrounds
from frameartdash.cards import page as cards_page
from frameartdash.cards.schema import schema_json
from frameartdash.cards.store import LayoutError, LayoutStore
from frameartdash.config import FIELDS, GROUPS, SECRET_KEYS, ConfigError, SettingsStore
from frameartdash.ha import HAClient, HAError
from frameartdash.service import Service

log = logging.getLogger(__name__)

SERVICE = web.AppKey("service", Service)
STORE = web.AppKey("store", SettingsStore)
AUTH = web.AppKey("auth", Auth)
BACKGROUNDS = web.AppKey("backgrounds", Backgrounds)
WEBSTATE = web.AppKey("webstate", dict)
LOOP = web.AppKey("loop", asyncio.Task)

PUBLIC = {"/login", "/healthz", "/refresh", "/favicon.svg"}
STATIC_TYPES = {
    ".woff2": "font/woff2",
    ".json": "application/json",
    ".js": "text/javascript",
    ".css": "text/css",
}

# Keeps references to fire-and-forget tasks so they are not garbage collected.
_background: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


class LogBuffer(logging.Handler):
    """Keeps the last log lines for the web UI."""

    def __init__(self, size: int = 200) -> None:
        super().__init__(logging.INFO)
        self.lines: collections.deque[str] = collections.deque(maxlen=size)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:  # noqa: BLE001 - logging must never raise
            pass


LOGS = LogBuffer()


def _page(name: str) -> str:
    return resources.files("frameartdash.webui").joinpath(name).read_text(encoding="utf-8")


def _json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


# -- auth -------------------------------------------------------------------


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if request.path in PUBLIC or request.path.startswith("/static/"):
        return await handler(request)
    if request.app[AUTH].check_session(request.cookies.get(COOKIE)):
        return await handler(request)
    if request.path.startswith("/api/"):
        return _json_error("not logged in", 401)
    raise web.HTTPFound("/login")


async def login_page(request: web.Request) -> web.Response:
    return web.Response(text=_page("login.html"), content_type="text/html")


async def login(request: web.Request) -> web.Response:
    form = await request.post()
    if not request.app[AUTH].check_password(str(form.get("password", ""))):
        await asyncio.sleep(1)  # slow down guessing
        raise web.HTTPFound("/login?error=1")
    response = web.HTTPFound("/")
    response.set_cookie(
        COOKIE,
        request.app[AUTH].new_session(),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="Strict",
        secure=request.secure,
    )
    raise response


async def logout(request: web.Request) -> web.Response:
    response = web.HTTPFound("/login")
    response.del_cookie(COOKIE)
    raise response


# -- pages and images ---------------------------------------------------------


async def index(request: web.Request) -> web.Response:
    return web.Response(text=_page("index.html"), content_type="text/html")


async def static_file(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if "/" in name or suffix not in STATIC_TYPES:
        raise web.HTTPNotFound()
    try:
        data = resources.files("frameartdash.webui").joinpath(f"static/{name}").read_bytes()
    except (FileNotFoundError, IsADirectoryError):
        raise web.HTTPNotFound() from None
    cache = "public, max-age=86400" if suffix in (".woff2", ".json") else "no-cache"
    return web.Response(body=data, content_type=STATIC_TYPES[suffix], headers={"Cache-Control": cache})


async def favicon(request: web.Request) -> web.Response:
    return web.Response(text=_page("favicon.svg"), content_type="image/svg+xml")


def _file(path) -> web.FileResponse:
    if path is None:
        raise web.HTTPNotFound()
    return web.FileResponse(path, headers={"Cache-Control": "no-cache"})


async def preview_image(request: web.Request) -> web.FileResponse:
    name = "preview-raw.png" if request.query.get("raw") == "1" else "preview.jpg"
    response = _file(request.app[SERVICE].history.path(name))
    if request.query.get("download") == "1":
        response.headers["Content-Disposition"] = f'attachment; filename="frameartdash-{name}"'
    return response


async def history_image(request: web.Request) -> web.FileResponse:
    return _file(request.app[SERVICE].history.path(request.match_info["name"]))


# -- status and actions -------------------------------------------------------


async def status(request: web.Request) -> web.Response:
    service = request.app[SERVICE]
    state = service.store.load()
    s = service.settings
    return web.json_response(
        {
            "version": __version__,
            "configured": s.configured,
            "frame_host": s.frame_host,
            "target_url": s.target_url,
            "interval_min": s.interval_min,
            "paired": s.token_file.exists(),
            "busy": service.lock.locked(),
            "last_result": service.last_result.as_dict() if service.last_result else None,
            "last_success": service.last_success,
            "next_run": service.next_run.isoformat(timespec="seconds") if service.next_run else None,
            "current_id": state.current_id,
            "last_upload": state.last_upload,
            "history": service.history.entries(),
            "preview": service.history.preview_info(),
            "dry_run": s.dry_run,
            "layout": s.layout,
            "pairing": request.app[WEBSTATE]["pairing"],
            "api_key": request.app[AUTH].api_key,
        }
    )


async def refresh_api(request: web.Request) -> web.Response:
    service = request.app[SERVICE]
    if service.lock.locked():
        return _json_error("a cycle is already running", 409)
    _spawn(service.run_cycle(force=True))
    return web.json_response({"status": "accepted"}, status=202)


async def preview(request: web.Request) -> web.Response:
    result = await request.app[SERVICE].run_cycle(upload=False)
    if result.status != "rendered":
        return web.json_response({**result.as_dict(), "error": result.reason}, status=500)
    return web.json_response(result.as_dict())


async def tv_info(request: web.Request) -> web.Response:
    settings = request.app[SERVICE].settings
    if not settings.frame_host:
        return _json_error("no TV IP address configured")
    try:
        async with asyncio.timeout(25):
            async with frame_mod.connect(settings) as frame:
                info = {"power": await frame.power_state()}
                if info["power"] in frame_mod.POWER_ON_STATES:
                    info["current"] = await frame.current()
                    info["my_photos"] = len(await frame.my_photos())
    except frame_mod.FrameUnreachable as e:
        return web.json_response({"power": "unreachable", "error": str(e)})
    except Exception as e:  # noqa: BLE001 - shown in the UI
        return web.json_response({"power": "error", "error": str(e) or type(e).__name__})
    return web.json_response(info)


async def pair(request: web.Request) -> web.Response:
    pairing = request.app[WEBSTATE]["pairing"]
    settings = request.app[SERVICE].settings
    if not settings.frame_host:
        return _json_error("Enter the TV IP address first")
    if pairing["state"] == "waiting":
        return _json_error("pairing is already in progress", 409)
    try:
        force = bool((await request.json()).get("force", False))
    except (ValueError, AttributeError):
        force = False

    pairing.update(state="waiting", message="Press Allow on the TV now (60 s)…")

    async def run():
        try:
            ok = await frame_mod.pair(settings, force=bool(force))
            pairing.update(state="paired" if ok else "error", message="Paired" if ok else "No token received")
        except Exception as e:  # noqa: BLE001 - shown in the UI
            pairing.update(state="error", message=str(e) or type(e).__name__)
        log.info("Pairing: %s", pairing["message"])

    _spawn(run())
    return web.json_response(pairing, status=202)


async def rotate_api_key(request: web.Request) -> web.Response:
    return web.json_response({"api_key": request.app[AUTH].rotate_api_key()})


async def logs(request: web.Request) -> web.Response:
    return web.json_response({"lines": list(LOGS.lines)})


# -- settings -----------------------------------------------------------------


async def get_settings(request: web.Request) -> web.Response:
    store = request.app[STORE]
    values = store.effective()
    secrets_set = {k: bool(values[k]) for k in SECRET_KEYS}
    for key in SECRET_KEYS:
        values[key] = ""
    return web.json_response(
        {
            "groups": GROUPS,
            "fields": [
                {
                    "key": f.key,
                    "label": f.label,
                    "group": f.group,
                    "kind": f.kind,
                    "help": f.help,
                    "options": f.options,
                    "advanced": f.advanced,
                    "only": f.only,
                    "default": f.default,
                }
                for f in FIELDS
            ],
            "values": values,
            "secrets_set": secrets_set,
            "backgrounds": request.app[BACKGROUNDS].list(),
        }
    )


async def put_settings(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except ValueError:
        return _json_error("invalid JSON")
    values = body.get("values", {})
    if not isinstance(values, dict):
        return _json_error("values must be an object")
    changes: dict[str, str | None] = {}
    for key, value in values.items():
        if key in SECRET_KEYS and value in ("", None):
            continue  # empty secret field: keep the stored value
        changes[key] = None if value is None else str(value)
    for key in body.get("clear", []):
        changes[key] = ""
    try:
        settings = request.app[STORE].update(changes)
    except ConfigError as e:
        return _json_error(str(e))
    request.app[SERVICE].apply_settings(settings)
    log.info("Settings saved")
    return web.json_response({"status": "saved"})


# -- backgrounds --------------------------------------------------------------


async def list_backgrounds(request: web.Request) -> web.Response:
    return web.json_response({"backgrounds": request.app[BACKGROUNDS].list()})


async def upload_background(request: web.Request) -> web.Response:
    reader = await request.multipart()
    part = await reader.next()
    if part is None or part.name != "file":
        return _json_error("expected a 'file' field")
    data = await part.read(decode=False)
    try:
        name = await asyncio.to_thread(request.app[BACKGROUNDS].add, part.filename or "background", data)
    except BackgroundError as e:
        return _json_error(str(e))
    return web.json_response({"name": name}, status=201)


async def background_image(request: web.Request) -> web.FileResponse:
    thumb = request.query.get("thumb") == "1"
    return _file(request.app[BACKGROUNDS].path(request.match_info["name"], thumb=thumb))


async def delete_background(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    if request.app[STORE].effective().get("BG_IMAGE") == name:
        return _json_error("This background is in use. Select another one first.", 409)
    if not request.app[BACKGROUNDS].delete(name):
        raise web.HTTPNotFound()
    return web.json_response({"status": "deleted"})


# -- card layout ----------------------------------------------------------------


def _layouts(request: web.Request) -> LayoutStore:
    return LayoutStore(request.app[SERVICE].settings.cards_file)


async def get_cards(request: web.Request) -> web.Response:
    return web.json_response(_layouts(request).load())


async def put_cards(request: web.Request) -> web.Response:
    try:
        layout = _layouts(request).save(await request.json())
    except (ValueError, LayoutError) as e:
        return _json_error(str(e))
    return web.json_response(layout)


async def cards_schema(request: web.Request) -> web.Response:
    return web.json_response(schema_json())


async def canvas(request: web.Request) -> web.Response:
    """The card layout as the editor shows it (same HTML as the rendered picture)."""
    settings = request.app[SERVICE].settings
    if not (settings.ha_url and settings.ha_token):
        return web.Response(
            text="<body style='background:#111;color:#bbb;font:24px system-ui;display:grid;place-items:center;"
            "height:100vh;margin:0'>Enter the Home Assistant URL and token under Source first.</body>",
            content_type="text/html",
        )
    try:
        html, _ = await cards_page.build(settings, _layouts(request).load(), inline=False, edit=True)
    except HAError as e:
        return web.Response(
            text=f"<body style='background:#111;color:#d9826b;font:24px system-ui;padding:40px'>{e}</body>",
            content_type="text/html",
        )
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-store"})


async def ha_entities(request: web.Request) -> web.Response:
    """Entities for the editor's picker, cached for 30 seconds."""
    settings = request.app[SERVICE].settings
    cache = request.app[WEBSTATE].setdefault("entities", {"time": 0.0, "data": None})
    if cache["data"] is None or time.monotonic() - cache["time"] > 30 or request.query.get("fresh"):
        if not (settings.ha_url and settings.ha_token):
            return _json_error("Home Assistant URL and token are not configured")
        try:
            async with HAClient(settings.ha_url, settings.ha_token) as ha:
                states = await ha.states()
        except HAError as e:
            return _json_error(str(e), 502)
        cache["data"] = sorted(
            (
                {
                    "id": eid,
                    "name": st.get("attributes", {}).get("friendly_name", eid),
                    "state": st.get("state"),
                    "unit": st.get("attributes", {}).get("unit_of_measurement", ""),
                }
                for eid, st in states.items()
            ),
            key=lambda e: e["id"],
        )
        cache["time"] = time.monotonic()
    return web.json_response({"entities": cache["data"]})


# -- public endpoints ---------------------------------------------------------


async def healthz(request: web.Request) -> web.Response:
    loop_task = request.app.get(LOOP)
    alive = loop_task is not None and not loop_task.done()
    last = request.app[SERVICE].last_result
    body = {
        "status": "ok" if alive else "loop stopped",
        "version": __version__,
        "last_status": last.status if last else None,
    }
    return web.json_response(body, status=200 if alive else 503)


async def refresh_with_key(request: web.Request) -> web.Response:
    """For Home Assistant: ``POST /refresh`` with ``Authorization: Bearer <api key>``."""
    header = request.headers.get("Authorization", "")
    key = (
        header.removeprefix("Bearer ").strip() or request.headers.get("X-Api-Key") or request.query.get("key")
    )
    if not request.app[AUTH].check_api_key(key):
        return _json_error("invalid API key", 401)
    return await refresh_api(request)


# -- app ----------------------------------------------------------------------


def build_app(service: Service, store: SettingsStore, auth: Auth, run_loop: bool = True) -> web.Application:
    app = web.Application(middlewares=[auth_middleware], client_max_size=30 * 1024 * 1024)
    app[SERVICE] = service
    app[STORE] = store
    app[AUTH] = auth
    app[BACKGROUNDS] = Backgrounds(service.settings.backgrounds_dir)
    app[WEBSTATE] = {"pairing": {"state": "idle", "message": ""}}

    r = app.router
    r.add_get("/", index)
    r.add_get("/favicon.svg", favicon)
    r.add_get("/login", login_page)
    r.add_post("/login", login)
    r.add_post("/logout", logout)
    r.add_get("/healthz", healthz)
    r.add_post("/refresh", refresh_with_key)
    r.add_get("/api/status", status)
    r.add_get("/api/logs", logs)
    r.add_get("/api/settings", get_settings)
    r.add_put("/api/settings", put_settings)
    r.add_post("/api/refresh", refresh_api)
    r.add_post("/api/preview", preview)
    r.add_get("/api/preview.jpg", preview_image)
    r.add_get("/api/history/{name}", history_image)
    r.add_get("/api/tv", tv_info)
    r.add_post("/api/pair", pair)
    r.add_post("/api/api-key", rotate_api_key)
    r.add_get("/api/backgrounds", list_backgrounds)
    r.add_post("/api/backgrounds", upload_background)
    r.add_get("/api/backgrounds/{name}", background_image)
    r.add_delete("/api/backgrounds/{name}", delete_background)
    r.add_get("/static/{name}", static_file)
    r.add_get("/canvas.html", canvas)
    r.add_get("/api/cards", get_cards)
    r.add_put("/api/cards", put_cards)
    r.add_get("/api/cards/schema", cards_schema)
    r.add_get("/api/ha/entities", ha_entities)

    if run_loop:

        async def start_loop(app: web.Application):
            app[LOOP] = asyncio.create_task(service.run_forever(), name="fad-loop")
            yield
            app[LOOP].cancel()
            try:
                await app[LOOP]
            except asyncio.CancelledError:
                pass

        app.cleanup_ctx.append(start_loop)
    return app


async def serve(service: Service, store: SettingsStore, auth: Auth) -> None:
    logging.getLogger().addHandler(LOGS)
    app = build_app(service, store, auth)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    port = service.settings.http_port or 8080
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("Web UI listening on http://0.0.0.0:%d", port)

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
