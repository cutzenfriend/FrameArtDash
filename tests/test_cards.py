import re
from datetime import datetime

import pytest
from aiohttp.test_utils import TestServer
from fake_ha import DEMO_LAYOUT, NOW, FakeHA
from fake_ha_server import TOKEN, build as build_fake_ha

from frameartdash.cards.data import collect, visible
from frameartdash.cards.html import RENDERERS, build_page
from frameartdash.cards.i18n import Locale
from frameartdash.cards.schema import CARD_TYPES, TYPES
from frameartdash.cards.store import LayoutError, LayoutStore, normalize
from frameartdash.ha import HAClient, HAError


def test_every_type_has_a_renderer():
    assert set(TYPES) == set(RENDERERS)
    assert len(CARD_TYPES) >= 19


def test_normalize_clamps_and_fills_defaults():
    layout = normalize(
        {"cards": [{"type": "value", "x": 95, "y": -4, "w": 30, "h": 500, "options": {"entity": "sensor.x"}}]}
    )
    card = layout["cards"][0]
    assert card["w"] == 30 and card["h"] == 100
    assert card["x"] == 70 and card["y"] == 0  # pulled back onto the canvas
    assert card["options"]["entity"] == "sensor.x"
    assert card["options"]["style"] == "inherit"
    assert layout["style"]["card_style"] == "glass"


def test_normalize_rejects_unknown_types_and_duplicates():
    with pytest.raises(LayoutError):
        normalize({"cards": [{"type": "nope"}]})
    with pytest.raises(LayoutError):
        normalize({"cards": [{"id": "a", "type": "clock"}, {"id": "a", "type": "date"}]})


def test_layout_store_roundtrip(tmp_path):
    store = LayoutStore(tmp_path / "cards.json")
    assert store.load()["cards"] == []
    saved = store.save(DEMO_LAYOUT)
    assert store.load() == saved
    (tmp_path / "cards.json").write_text("{broken")
    assert store.load()["cards"] == []


def test_visibility_conditions():
    states = {"media_player.x": {"state": "playing"}}
    card = {"options": {"show_if_entity": "media_player.x", "show_if_state": "playing,paused"}}
    assert visible(card, states)
    card["options"]["show_if_state"] = "!playing"
    assert not visible(card, states)


def test_locale_formatting():
    de, en = Locale("de"), Locale("en")
    assert de.number(1234.5, 1) == "1.234,5"
    assert en.number(1234.5, 1) == "1,234.5"
    assert de.quantity(3796.8, "W") == ("3,8", "kW")
    assert de.quantity(874.2, "W") == ("874", "W")
    assert de.number(12.73) == "12,7"


async def test_demo_layout_renders_without_errors():
    layout = normalize(DEMO_LAYOUT)
    async with FakeHA() as ha:
        data = await collect(ha, layout, "Europe/Berlin", "de", now=NOW)
    assert not data.errors
    html = build_page(layout, data, "linear-gradient(#000,#111)", inline_assets=False)
    assert html.count('class="card ') == len(layout["cards"])
    assert "alert-circle" not in html and "Error" not in html
    assert "16:16" in html or "15:16" in html  # clock in local time (Berlin)
    for text in (
        "Bewölkt",
        "Elternabend Kindergarten",
        "Kaffeebohnen",
        "Clair de Lune",
        "Einspeisung",
        "Zuhause",
    ):
        assert text in html, text
    assert not re.search(r"\{sensor\.", html)  # placeholders replaced


async def test_missing_entity_and_failing_fetch_only_affect_their_card():
    layout = normalize(
        {
            "cards": [
                {"id": "a", "type": "value", "options": {"entity": "sensor.does_not_exist"}},
                {"id": "b", "type": "weather", "options": {"entity": "weather.home"}},
                {"id": "c", "type": "clock"},
            ]
        }
    )

    class Broken(FakeHA):
        async def service(self, *args):
            raise HAError("boom")

    async with Broken() as ha:
        data = await collect(ha, layout, "Europe/Berlin", "en", now=NOW)
    assert data.errors == {"b": "boom"}
    html = build_page(layout, data, "#000", inline_assets=False)
    assert "sensor.does_not_exist" in html and "boom" in html


async def test_ha_client_against_fake_server():
    async with TestServer(build_fake_ha()) as server:
        base = str(server.make_url("")).rstrip("/")
        async with HAClient(base, TOKEN) as ha:
            states = await ha.states()
            assert states["sensor.pv_power"]["state"] == "3796.8"
            history = await ha.history(["sensor.pv_power"], 24)
            assert len(history["sensor.pv_power"]) > 10
            assert isinstance(history["sensor.pv_power"][0][0], datetime)
            forecast = await ha.service(
                "weather", "get_forecasts", {"entity_id": "weather.home", "type": "daily"}
            )
            assert forecast["weather.home"]["forecast"]
            assert (await ha.image("/api/camera_proxy/camera.einfahrt")).startswith("data:image/png")
        with pytest.raises(HAError, match="401"):
            async with HAClient(base, "wrong") as ha:
                await ha.states()
