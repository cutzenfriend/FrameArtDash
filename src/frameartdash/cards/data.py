"""Fetch everything the visible cards need from Home Assistant."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from frameartdash.cards.i18n import Locale
from frameartdash.ha import HAClient, HAError

log = logging.getLogger(__name__)


@dataclass
class CardData:
    now: datetime
    locale: Locale
    states: dict[str, dict] = field(default_factory=dict)
    history: dict[str, list] = field(default_factory=dict)
    forecasts: dict[str, list] = field(default_factory=dict)
    events: dict[str, list] = field(default_factory=dict)  # per card id
    todos: dict[str, list] = field(default_factory=dict)
    images: dict[str, str] = field(default_factory=dict)  # entity id → data URI
    errors: dict[str, str] = field(default_factory=dict)  # card id → message

    def state(self, entity_id: str) -> dict | None:
        return self.states.get(entity_id) if entity_id else None


def visible(card: dict, states: dict[str, dict]) -> bool:
    opts = card["options"]
    entity = opts.get("show_if_entity")
    wanted = str(opts.get("show_if_state") or "").strip()
    if not entity or not wanted:
        return True
    state = (states.get(entity) or {}).get("state")
    negate = wanted.startswith("!")
    values = {v.strip() for v in wanted.lstrip("!").split(",") if v.strip()}
    return (state not in values) if negate else (state in values)


def _trackers(eid: str, states: dict[str, dict]) -> list[str]:
    """Device trackers behind a People entry: a person's assigned trackers, or a tracker itself."""
    if eid.startswith("device_tracker."):
        return [eid]
    return list(((states.get(eid) or {}).get("attributes") or {}).get("device_trackers") or [])


def person_ids(o: dict, states: dict[str, dict]) -> list[str]:
    """Entities of a People card.

    The picked entities plus (with all_persons) every person, minus the excluded ones. With
    all_persons or only_home, only entries backed by at least one device tracker are shown, and
    with only_home at least one of those trackers must itself report home. With both off, the
    picked entities are shown as before.
    """
    ids = list(o.get("entities") or [])
    if o.get("all_persons"):
        ids += sorted(e for e in states if e.startswith("person.") and e not in ids)
    excluded = set(o.get("exclude") or [])
    filtered = bool(o.get("all_persons") or o.get("only_home"))
    shown = []
    for eid in ids:
        trackers = _trackers(eid, states)
        if eid in excluded or (filtered and not trackers):
            continue
        if o.get("only_home") and not any((states.get(t) or {}).get("state") == "home" for t in trackers):
            continue
        shown.append(eid)
    return shown


def _hours(card: dict) -> float:
    try:
        return max(1.0, min(float(card["options"].get("hours") or 24), 24 * 7))
    except (TypeError, ValueError):
        return 24.0


async def collect(
    ha: HAClient, layout: dict, tz: str | None, lang: str, now: datetime | None = None
) -> CardData:
    zone = ZoneInfo(tz) if tz else None
    if now is None:
        now = datetime.now(zone) if zone else datetime.now().astimezone()
    elif zone:
        now = now.astimezone(zone)
    data = CardData(now=now, locale=Locale(lang))
    data.states = await ha.states()  # a failure here fails the render: nothing would be right

    cards = [c for c in layout["cards"] if visible(c, data.states)]
    tasks: list = []

    # History for graphs and sparklines, one request for the longest window.
    history_ids: set[str] = set()
    hours = 0.0
    for c in cards:
        o = c["options"]
        if c["type"] == "graph":
            history_ids.update(o.get("entities") or [])
            hours = max(hours, _hours(c))
        elif c["type"] == "value" and o.get("sparkline") and o.get("entity"):
            history_ids.add(o["entity"])
            hours = max(hours, _hours(c))

    async def get_history():
        data.history = await ha.history(sorted(history_ids), hours)

    if history_ids:
        tasks.append(("history", get_history()))

    for c in cards:
        o, cid = c["options"], c["id"]
        if c["type"] == "weather" and o.get("entity") and int(o.get("forecast_days") or 0) > 0:
            eid = o["entity"]

            async def forecast(eid=eid):
                resp = await ha.service("weather", "get_forecasts", {"entity_id": eid, "type": "daily"})
                data.forecasts[eid] = (resp.get(eid) or {}).get("forecast", [])

            tasks.append((cid, forecast()))
        elif c["type"] == "calendar" and o.get("entities"):

            async def events(c=c, o=o):
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=max(1, int(o.get("days") or 7)))
                found = []
                for eid in o["entities"]:
                    for ev in await ha.calendar(eid, start, end):
                        ev["calendar"] = eid
                        found.append(ev)
                data.events[c["id"]] = found

            tasks.append((cid, events()))
        elif c["type"] == "todo" and o.get("entity"):
            eid = o["entity"]

            async def todo(eid=eid):
                resp = await ha.service("todo", "get_items", {"entity_id": eid, "status": ["needs_action"]})
                data.todos[eid] = (resp.get(eid) or {}).get("items", [])

            tasks.append((cid, todo()))
        elif c["type"] in ("persons", "media", "camera"):
            if c["type"] == "persons":
                ids = person_ids(o, data.states)
            else:
                ids = o.get("entities") or ([o["entity"]] if o.get("entity") else [])
            for eid in ids:
                st = data.states.get(eid) or {}
                if c["type"] == "camera":
                    path = f"/api/camera_proxy/{eid}"
                elif c["type"] == "media" and (not o.get("show_cover") or st.get("state") != "playing"):
                    continue
                else:
                    path = (st.get("attributes") or {}).get("entity_picture")
                if not path or eid in data.images:
                    continue

                async def image(eid=eid, path=path):
                    if uri := await ha.image(path):
                        data.images[eid] = uri

                tasks.append((cid, image()))

    results = await asyncio.gather(*(t for _, t in tasks), return_exceptions=True)
    for (owner, _), result in zip(tasks, results, strict=True):
        if isinstance(result, Exception):
            message = str(result) if isinstance(result, HAError) else f"{type(result).__name__}: {result}"
            log.warning("Card data for %s failed: %s", owner, message)
            if owner == "history":
                for c in cards:
                    if c["type"] == "graph":
                        data.errors[c["id"]] = message
            else:
                data.errors[owner] = message
    return data
