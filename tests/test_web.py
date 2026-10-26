import io
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from frameartdash.auth import Auth
from frameartdash.config import SettingsStore
from frameartdash.service import Service
from frameartdash.web import build_app


@pytest.fixture
async def client(tmp_path):
    store = SettingsStore({"DATA_DIR": str(tmp_path)})
    service = Service(store.load())
    auth = Auth(tmp_path, "s3cret")
    app = build_app(service, store, auth, run_loop=False)
    async with TestClient(TestServer(app)) as c:
        c.auth = auth
        c.store = store
        c.service = service
        yield c


async def login(client):
    resp = await client.post("/login", data={"password": "s3cret"}, allow_redirects=False)
    assert resp.status == 302 and resp.headers["Location"] == "/"


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 450), (10, 120, 200)).save(buf, "JPEG")
    return buf.getvalue()


async def test_requires_login(client):
    resp = await client.get("/", allow_redirects=False)
    assert resp.status == 302 and resp.headers["Location"] == "/login"
    assert (await client.get("/api/status")).status == 401
    resp = await client.post("/login", data={"password": "wrong"}, allow_redirects=False)
    assert resp.headers["Location"] == "/login?error=1"
    assert (await client.get("/healthz")).status in (200, 503)


async def test_settings_roundtrip_hides_secrets(client):
    await login(client)
    resp = await client.put(
        "/api/settings",
        json={
            "values": {
                "TARGET_URL": "http://ha.local:8123/frame-dash/art",
                "HA_TOKEN": "abc",
                "FRAME_HOST": "10.0.0.5",
            }
        },
    )
    assert resp.status == 200, await resp.text()
    data = await (await client.get("/api/settings")).json()
    assert data["values"]["TARGET_URL"] == "http://ha.local:8123/frame-dash/art"
    assert data["values"]["HA_TOKEN"] == ""
    assert data["secrets_set"]["HA_TOKEN"] is True
    assert client.service.settings.frame_host == "10.0.0.5"

    # An empty secret keeps the stored value, clear removes it.
    await client.put("/api/settings", json={"values": {"HA_TOKEN": ""}})
    assert client.store.load().ha_token == "abc"
    await client.put("/api/settings", json={"values": {}, "clear": ["HA_TOKEN"]})
    assert client.store.load().ha_token == ""

    resp = await client.put("/api/settings", json={"values": {"STYLE": "neon"}})
    assert resp.status == 400


async def test_background_upload_select_delete(client):
    await login(client)
    form = {"file": io.BytesIO(_jpeg())}
    resp = await client.post("/api/backgrounds", data=form)
    assert resp.status == 201, await resp.text()
    name = (await resp.json())["name"]
    assert (await client.get(f"/api/backgrounds/{name}?thumb=1")).status == 200

    await client.put("/api/settings", json={"values": {"STYLE": "image", "BG_IMAGE": name}})
    assert client.service.settings.bg_image.endswith(name)
    assert (await client.delete(f"/api/backgrounds/{name}")).status == 409
    await client.put("/api/settings", json={"values": {"STYLE": "blur", "BG_IMAGE": ""}})
    assert (await client.delete(f"/api/backgrounds/{name}")).status == 200

    bad = await client.post("/api/backgrounds", data={"file": io.BytesIO(b"not an image")})
    assert bad.status == 400
    assert (await client.get("/api/backgrounds/../settings.json")).status == 404


async def test_refresh_needs_api_key(client):
    assert (await client.post("/refresh")).status == 401
    resp = await client.post("/refresh", headers={"Authorization": f"Bearer {client.auth.api_key}"})
    assert resp.status == 202


async def test_status_and_history(client):
    await login(client)
    from datetime import datetime

    client.service.history.add(Image.new("RGB", (3840, 2160)), "MY_F0001", datetime(2026, 10, 26, 12, 0))
    status = await (await client.get("/api/status")).json()
    assert status["configured"] is False
    assert status["history"][0]["content_id"] == "MY_F0001"
    assert (await client.get("/api/history/current.jpg")).status == 200
    assert (await client.get("/api/history/" + status["history"][0]["file"])).status == 200
    assert (await client.get("/api/history/state.json")).status == 404
    json.dumps(status)


async def test_preview_endpoint_without_tv(client):
    await login(client)
    assert (await client.get("/api/preview.jpg")).status == 404
    resp = await client.post("/api/preview")
    assert resp.status == 500
    assert "URL" in (await resp.json())["error"]

    png = io.BytesIO()
    Image.new("RGB", (480, 270), (30, 30, 30)).save(png, "PNG")

    async def renderer(_settings):
        return png.getvalue()

    client.service.renderer = renderer
    await client.put("/api/settings", json={"values": {"TARGET_URL": "http://example.test/"}})
    resp = await client.post("/api/preview")
    assert resp.status == 200, await resp.text()
    status = await (await client.get("/api/status")).json()
    assert status["preview"]["size_kb"] > 0
    assert (await client.get("/api/preview.jpg")).content_type == "image/jpeg"
    raw = await client.get("/api/preview.jpg?raw=1")
    assert raw.content_type == "image/png"
    dl = await client.get("/api/preview.jpg?download=1")
    assert "attachment" in dl.headers["Content-Disposition"]
