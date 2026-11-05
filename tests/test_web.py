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


async def test_card_editor_endpoints(client):
    await login(client)
    schema = await (await client.get("/api/cards/schema")).json()
    assert {t["type"] for t in schema["types"]} >= {"clock", "weather", "energy"}
    resp = await client.put(
        "/api/cards", json={"cards": [{"type": "clock", "x": 10, "y": 10, "w": 20, "h": 15}]}
    )
    assert resp.status == 200
    layout = await (await client.get("/api/cards")).json()
    assert layout["cards"][0]["type"] == "clock"
    assert (await client.put("/api/cards", json={"cards": [{"type": "nope"}]})).status == 400
    # Without HA credentials the canvas explains what is missing instead of failing.
    canvas = await client.get("/canvas.html")
    assert canvas.status == 200 and "Home Assistant" in await canvas.text()
    assert (await client.get("/static/mdi.json")).status == 200
    assert (await client.get("/static/../settings.json")).status == 404


class _ArtFrame:
    """Fake Frame for POST /artmode: reaches Art Mode after `confirm_after` checks."""

    def __init__(self, power="tv", confirm_after=1):
        self.power = power
        self.confirm_after = confirm_after
        self.set_calls: list[bool] = []
        self.checks = 0
        self.shown: list[tuple[str, bool]] = []

    async def power_state(self):
        return self.power

    async def set_art_mode(self, on=True):
        self.set_calls.append(on)

    async def art_mode(self):
        self.checks += 1
        return self.confirm_after is not None and self.checks >= self.confirm_after

    async def select(self, cid, show=False):
        self.shown.append((cid, show))


def _fake_connect(monkeypatch, fake):
    from contextlib import asynccontextmanager

    from frameartdash import web as web_mod

    @asynccontextmanager
    async def connect(settings):
        if isinstance(fake, Exception):
            raise fake
        yield fake

    monkeypatch.setattr(web_mod.frame_mod, "connect", connect)
    monkeypatch.setattr(web_mod, "ARTMODE_POLL_S", 0.01)
    monkeypatch.setattr(web_mod, "ARTMODE_WAIT_S", 0.2)
    return fake


def _fake_cycle(client, monkeypatch, events, status="uploaded", content_id="MY_F0101"):
    """Replace the service's cycle: records its order relative to the Art Mode switch."""
    from frameartdash.service import CycleResult

    async def run_cycle(force=False, upload=True):
        events.append(("cycle", force))
        if status == "uploaded":
            state = client.service.store.load()
            state.current_id = content_id
            client.service.store.save(state)
        return CycleResult(status)

    monkeypatch.setattr(client.service, "run_cycle", run_cycle)


@pytest.fixture
async def tv_client(client):
    await login(client)
    resp = await client.put("/api/settings", json={"values": {"FRAME_HOST": "10.0.0.5"}})
    assert resp.status == 200, await resp.text()
    client.key = {"Authorization": f"Bearer {client.auth.api_key}"}
    return client


async def test_artmode_needs_api_key(client):
    assert (await client.post("/artmode")).status == 401


async def test_artmode_refreshes_then_switches_from_an_app(tv_client, monkeypatch):
    events = []
    fake = _ArtFrame(power="tv", confirm_after=3)
    orig_set = fake.set_art_mode

    async def set_art_mode(on=True):
        events.append(("artmode", on))
        await orig_set(on)

    fake.set_art_mode = set_art_mode
    _fake_connect(monkeypatch, fake)
    _fake_cycle(tv_client, monkeypatch, events)
    resp = await tv_client.post("/artmode", headers=tv_client.key)
    body = await resp.json()
    assert resp.status == 200, body
    assert body == {"status": "art", "power_before": "tv", "changed": True, "cycle": "uploaded"}
    # Fresh picture first, then Art Mode, then the new picture put on screen.
    assert events == [("cycle", True), ("artmode", True)]
    assert fake.checks == 3
    assert fake.shown == [("MY_F0101", True)]


async def test_artmode_switches_even_if_the_cycle_fails(tv_client, monkeypatch):
    events = []
    fake = _ArtFrame(power="on")
    _fake_connect(monkeypatch, fake)
    _fake_cycle(tv_client, monkeypatch, events, status="error")
    resp = await tv_client.post("/artmode", headers=tv_client.key)
    body = await resp.json()
    assert resp.status == 200 and body["cycle"] == "error"
    assert fake.set_calls == [True]


async def test_artmode_already_art_is_a_no_op(tv_client, monkeypatch):
    events = []
    fake = _ArtFrame(power="art")
    _fake_connect(monkeypatch, fake)
    _fake_cycle(tv_client, monkeypatch, events)
    resp = await tv_client.post("/artmode", headers=tv_client.key)
    assert resp.status == 200 and (await resp.json())["changed"] is False
    assert fake.set_calls == [] and events == [] and fake.shown == []


@pytest.mark.parametrize("power", ["off", "standby"])
async def test_artmode_refuses_when_tv_is_off(tv_client, monkeypatch, power):
    events = []
    fake = _ArtFrame(power=power)
    _fake_connect(monkeypatch, fake)
    _fake_cycle(tv_client, monkeypatch, events)
    resp = await tv_client.post("/artmode", headers=tv_client.key)
    assert resp.status == 409 and (await resp.json())["status"] == "tv_off"
    assert fake.set_calls == [] and events == []


async def test_artmode_not_confirmed(tv_client, monkeypatch):
    events = []
    fake = _ArtFrame(power="tv", confirm_after=None)
    _fake_connect(monkeypatch, fake)
    _fake_cycle(tv_client, monkeypatch, events)
    resp = await tv_client.post("/artmode", headers=tv_client.key)
    assert resp.status == 504 and (await resp.json())["status"] == "not_confirmed"
    assert fake.shown == []


async def test_artmode_unreachable(tv_client, monkeypatch):
    from frameartdash.frame import FrameUnreachable

    _fake_connect(monkeypatch, FrameUnreachable("10.0.0.5 not reachable"))
    resp = await tv_client.post("/artmode", headers=tv_client.key)
    assert resp.status == 503 and (await resp.json())["status"] == "unreachable"


async def test_artmode_without_tv_configured(client):
    resp = await client.post("/artmode", headers={"Authorization": f"Bearer {client.auth.api_key}"})
    assert resp.status == 400
