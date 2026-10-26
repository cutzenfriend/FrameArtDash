"""A fake Home Assistant client with realistic data, for tests and demos."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

NOW = datetime(2026, 10, 26, 14, 16, tzinfo=UTC)


def _st(eid, state, **attrs):
    return {"entity_id": eid, "state": str(state), "attributes": attrs}


STATES = [
    _st(
        "sensor.wohnzimmer_temperatur",
        "23.5",
        unit_of_measurement="°C",
        device_class="temperature",
        friendly_name="Wohnzimmer",
    ),
    _st(
        "sensor.wohnzimmer_feuchte",
        "50",
        unit_of_measurement="%",
        device_class="humidity",
        friendly_name="Luftfeuchte",
    ),
    _st(
        "sensor.aussen_temperatur",
        "12.73",
        unit_of_measurement="°C",
        device_class="temperature",
        friendly_name="Draußen",
    ),
    _st("sensor.pv_power", "3796.8", unit_of_measurement="W", device_class="power", friendly_name="PV"),
    _st("sensor.home_power", "874.2", unit_of_measurement="W", device_class="power", friendly_name="Haus"),
    _st("sensor.grid_power", "-1850", unit_of_measurement="W", device_class="power", friendly_name="Netz"),
    _st(
        "sensor.battery_power",
        "-1062",
        unit_of_measurement="W",
        device_class="power",
        friendly_name="Batterie",
    ),
    _st(
        "sensor.battery_soc",
        "39",
        unit_of_measurement="%",
        device_class="battery",
        friendly_name="Hausbatterie",
    ),
    _st(
        "sensor.pv_forecast_today",
        "23.63",
        unit_of_measurement="kWh",
        device_class="energy",
        friendly_name="Prognose heute",
    ),
    _st("binary_sensor.haustuer", "off", device_class="door", friendly_name="Haustür"),
    _st("binary_sensor.terrassentuer", "on", device_class="door", friendly_name="Terrassentür"),
    _st("lock.garagentuer", "locked", friendly_name="Garagentür"),
    _st("light.couchtisch", "on", friendly_name="Couchtisch"),
    _st(
        "weather.home",
        "cloudy",
        temperature=12.3,
        temperature_unit="°C",
        humidity=64,
        wind_speed=13.5,
        wind_speed_unit="km/h",
        friendly_name="Home",
    ),
    _st(
        "sun.sun",
        "above_horizon",
        next_rising="2026-10-27T06:04:36+00:00",
        next_setting="2026-10-26T16:13:11+00:00",
        elevation=20.9,
        friendly_name="Sun",
    ),
    _st("person.alex", "home", friendly_name="Alex", entity_picture="/api/image/serve/alex/512x512"),
    _st("person.sam", "not_home", friendly_name="Sam"),
    _st(
        "media_player.soundbar",
        "playing",
        friendly_name="Soundbar",
        media_title="Clair de Lune",
        media_artist="Claude Debussy",
        entity_picture="/api/media_player_proxy/media_player.soundbar",
    ),
    _st("todo.einkauf", "3", friendly_name="Einkauf"),
    _st("calendar.familie", "off", friendly_name="Familie", start_time="2026-12-20 00:00:00"),
    _st("camera.einfahrt", "idle", friendly_name="Einfahrt"),
    _st("input_datetime.urlaub", "2026-12-20", has_date=True, has_time=False, friendly_name="Urlaub"),
]

# 1x1 JPEG-ish PNG pixel as image stand-in
PIXEL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8sGHjfwAHLwM3kU0VKgAAAABJRU5ErkJggg=="


class FakeHA:
    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def config(self):
        return {"time_zone": "Europe/Berlin", "language": "de"}

    async def states(self):
        self.calls.append("states")
        return {s["entity_id"]: s for s in STATES}

    async def history(self, entity_ids, hours):
        self.calls.append("history")
        out = {}
        for n, eid in enumerate(entity_ids):
            pts = []
            for i in range(97):
                t = NOW - timedelta(hours=hours) + timedelta(hours=hours) * i / 96
                if "pv" in eid:
                    v = (
                        max(0.0, 5200 * math.sin(math.pi * (t.hour + t.minute / 60 - 7) / 10))
                        if 7 <= t.hour < 17
                        else 0
                    )
                elif "home" in eid:
                    v = 600 + 400 * math.sin(i / 7) + (900 if 17 <= t.hour < 20 else 0)
                elif "aussen" in eid:
                    v = 9 + 4 * math.sin(math.pi * (t.hour - 8) / 12)
                else:
                    v = 22.5 + 0.8 * math.sin(i / 15 + n)
                pts.append((t, v))
            out[eid] = pts
        return out

    async def service(self, domain, service, data):
        self.calls.append(f"{domain}.{service}")
        eid = data["entity_id"]
        if domain == "weather":
            conds = ["cloudy", "partlycloudy", "rainy", "sunny", "partlycloudy", "cloudy", "snowy"]
            return {
                eid: {
                    "forecast": [
                        {
                            "datetime": (NOW + timedelta(days=i)).strftime("%Y-%m-%dT00:00:00Z"),
                            "condition": conds[i],
                            "temperature": 16 - i,
                            "templow": 8 - i,
                        }
                        for i in range(7)
                    ]
                }
            }
        if domain == "todo":
            return {
                eid: {
                    "items": [
                        {"summary": s, "status": "needs_action"} for s in ("Milch", "Kaffeebohnen", "Brot")
                    ]
                }
            }
        return {}

    async def calendar(self, entity_id, start, end):
        self.calls.append("calendar")
        return [
            {"summary": "Grüne Tonne", "start": {"date": "2026-10-27"}, "end": {"date": "2026-10-28"}},
            {
                "summary": "Elternabend Kindergarten",
                "start": {"dateTime": "2026-10-26T19:30:00+01:00"},
                "end": {"dateTime": "2026-10-26T21:00:00+01:00"},
            },
            {
                "summary": "Zahnarzt",
                "start": {"dateTime": "2026-10-29T08:15:00+01:00"},
                "end": {"dateTime": "2026-10-29T09:00:00+01:00"},
            },
        ]

    async def image(self, path):
        self.calls.append("image")
        return PIXEL


DEMO_LAYOUT = {
    "style": {"card_style": "glass", "font": "sans", "accent": "#e3c27a"},
    "cards": [
        {"id": "clock", "type": "clock", "x": 3, "y": 4, "w": 22, "h": 17, "options": {}},
        {
            "id": "weather",
            "type": "weather",
            "x": 3,
            "y": 24,
            "w": 30,
            "h": 27,
            "options": {"entity": "weather.home"},
        },
        {
            "id": "living",
            "type": "value",
            "x": 36,
            "y": 4,
            "w": 15,
            "h": 15,
            "options": {"entity": "sensor.wohnzimmer_temperatur", "sparkline": True},
        },
        {
            "id": "pv",
            "type": "big",
            "x": 53,
            "y": 4,
            "w": 20,
            "h": 15,
            "options": {"entity": "sensor.pv_power", "name": "Solar jetzt"},
        },
        {
            "id": "graph",
            "type": "graph",
            "x": 36,
            "y": 22,
            "w": 37,
            "h": 29,
            "options": {"title": "Leistung 24 h", "entities": ["sensor.pv_power", "sensor.home_power"]},
        },
        {
            "id": "energy",
            "type": "energy",
            "x": 76,
            "y": 4,
            "w": 21,
            "h": 47,
            "options": {
                "solar": "sensor.pv_power",
                "grid": "sensor.grid_power",
                "battery": "sensor.battery_power",
                "battery_soc": "sensor.battery_soc",
                "home": "sensor.home_power",
            },
        },
        {
            "id": "cal",
            "type": "calendar",
            "x": 3,
            "y": 55,
            "w": 24,
            "h": 30,
            "options": {"title": "Termine", "entities": ["calendar.familie"]},
        },
        {
            "id": "todo",
            "type": "todo",
            "x": 29,
            "y": 55,
            "w": 16,
            "h": 30,
            "options": {"entity": "todo.einkauf", "title": "Einkauf"},
        },
        {
            "id": "list",
            "type": "entities",
            "x": 47,
            "y": 55,
            "w": 19,
            "h": 22,
            "options": {
                "title": "Zuhause",
                "entities": [
                    "sensor.wohnzimmer_feuchte",
                    "sensor.aussen_temperatur",
                    "binary_sensor.haustuer",
                    "lock.garagentuer",
                ],
            },
        },
        {
            "id": "door",
            "type": "status",
            "x": 47,
            "y": 79,
            "w": 19,
            "h": 10,
            "options": {"entity": "binary_sensor.terrassentuer"},
        },
        {
            "id": "bar",
            "type": "bar",
            "x": 68,
            "y": 55,
            "w": 14,
            "h": 10,
            "options": {"entity": "sensor.battery_soc", "name": "Hausbatterie"},
        },
        {
            "id": "gauge",
            "type": "gauge",
            "x": 84,
            "y": 55,
            "w": 13,
            "h": 21,
            "options": {"entity": "sensor.wohnzimmer_feuchte", "name": "Luftfeuchte"},
        },
        {"id": "sun", "type": "sun", "x": 68, "y": 67, "w": 14, "h": 18, "options": {}},
        {
            "id": "people",
            "type": "persons",
            "x": 84,
            "y": 78,
            "w": 13,
            "h": 15,
            "options": {"entities": ["person.alex", "person.sam"]},
        },
        {
            "id": "media",
            "type": "media",
            "x": 3,
            "y": 88,
            "w": 24,
            "h": 9,
            "options": {"entity": "media_player.soundbar"},
        },
        {
            "id": "count",
            "type": "countdown",
            "x": 29,
            "y": 88,
            "w": 16,
            "h": 9,
            "options": {"title": "Urlaub", "entity": "input_datetime.urlaub", "scale": 80},
        },
        {
            "id": "text",
            "type": "text",
            "x": 47,
            "y": 90,
            "w": 35,
            "h": 7,
            "options": {
                "text": "Schönen Nachmittag! Draußen {sensor.aussen_temperatur}",
                "style": "none",
                "font": "serif",
                "scale": 90,
            },
        },
    ],
}
