"""Serve the FakeHA data over the Home Assistant REST API (for tests and local demos).

python tests/fake_ha_server.py 8124
"""

from __future__ import annotations

import base64
import sys
from datetime import datetime
from pathlib import Path

from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent))
from fake_ha import PIXEL, FakeHA  # noqa: E402

TOKEN = "test-token"


@web.middleware
async def auth(request, handler):
    if request.headers.get("Authorization") != f"Bearer {TOKEN}":
        return web.json_response({"message": "unauthorized"}, status=401)
    return await handler(request)


def build() -> web.Application:
    ha = FakeHA()
    app = web.Application(middlewares=[auth])

    async def config(request):
        return web.json_response(await ha.config())

    async def states(request):
        return web.json_response(list((await ha.states()).values()))

    async def history(request):
        ids = request.query.get("filter_entity_id", "").split(",")
        start = datetime.fromisoformat(request.match_info["start"])
        hours = (datetime.now(start.tzinfo) - start).total_seconds() / 3600
        data = await ha.history(ids, hours)
        return web.json_response(
            [
                [{"entity_id": eid, "state": str(v), "last_changed": t.isoformat()} for t, v in pts]
                for eid, pts in data.items()
            ]
        )

    async def service(request):
        body = await request.json()
        resp = await ha.service(request.match_info["domain"], request.match_info["service"], body)
        return web.json_response({"changed_states": [], "service_response": resp})

    async def calendar(request):
        return web.json_response(await ha.calendar(request.match_info["eid"], None, None))

    async def image(request):
        return web.Response(body=base64.b64decode(PIXEL.split(",", 1)[1]), content_type="image/png")

    app.router.add_get("/api/config", config)
    app.router.add_get("/api/states", states)
    app.router.add_get("/api/history/period/{start}", history)
    app.router.add_post("/api/services/{domain}/{service}", service)
    app.router.add_get("/api/calendars/{eid}", calendar)
    app.router.add_get("/api/camera_proxy/{eid}", image)
    app.router.add_get("/api/image/serve/{a}/{b}", image)
    app.router.add_get("/api/media_player_proxy/{eid}", image)
    return app


if __name__ == "__main__":
    web.run_app(build(), host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8124)
