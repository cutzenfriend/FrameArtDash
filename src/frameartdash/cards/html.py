"""Render the card layout as one HTML page (1920×1080 CSS pixels)."""

from __future__ import annotations

import base64
import json
import math
import re
from datetime import date, datetime, timedelta
from functools import cache
from html import escape
from importlib import resources

from frameartdash.cards.data import CardData, visible
from frameartdash.cards.i18n import BINARY, WEATHER_ICONS

CANVAS = (1920, 1080)
PALETTE = ("var(--accent)", "#8fb6d9", "#9fd3a7", "#e59a8c", "#c3a8e6", "#e6d38a")
FONTS = {
    "sans": "'Inter', 'Helvetica Neue', Arial, sans-serif",
    "serif": "'Fraunces', Georgia, serif",
    "mono": "'JetBrains Mono', Menlo, monospace",
}

DOMAIN_ICONS = {
    "light": "lightbulb-outline",
    "switch": "toggle-switch-outline",
    "fan": "fan",
    "cover": "window-shutter",
    "lock": "lock-outline",
    "climate": "thermostat",
    "media_player": "speaker",
    "person": "account",
    "device_tracker": "map-marker-outline",
    "weather": "weather-partly-cloudy",
    "sun": "white-balance-sunny",
    "input_boolean": "toggle-switch-outline",
    "binary_sensor": "checkbox-blank-circle-outline",
    "camera": "cctv",
    "calendar": "calendar",
    "todo": "format-list-checks",
    "vacuum": "robot-vacuum",
    "alarm_control_panel": "shield-home-outline",
    "counter": "counter",
    "timer": "timer-outline",
    "input_datetime": "calendar-clock",
    "update": "package-up",
    "button": "gesture-tap-button",
}
CLASS_ICONS = {
    "temperature": "thermometer",
    "humidity": "water-percent",
    "power": "flash",
    "energy": "lightning-bolt",
    "battery": "battery",
    "illuminance": "brightness-5",
    "pressure": "gauge",
    "carbon_dioxide": "molecule-co2",
    "pm25": "blur",
    "voltage": "sine-wave",
    "current": "current-ac",
    "gas": "meter-gas",
    "water": "water",
    "monetary": "cash",
    "speed": "speedometer",
    "wind_speed": "weather-windy",
    "precipitation": "weather-rainy",
    "door": "door",
    "window": "window-closed-variant",
    "garage_door": "garage",
    "motion": "motion-sensor",
    "occupancy": "home-account",
    "moisture": "water-alert",
    "smoke": "smoke-detector",
    "opening": "door",
    "plug": "power-plug",
    "connectivity": "lan-connect",
    "timestamp": "clock-outline",
    "duration": "timer-outline",
    "volume": "cup-water",
    "distance": "map-marker-distance",
    "frequency": "sine-wave",
    "aqi": "air-filter",
}
ACTIVE = {
    "on",
    "open",
    "opening",
    "unlocked",
    "home",
    "playing",
    "heat",
    "cool",
    "heat_cool",
    "auto",
    "cleaning",
    "triggered",
    "detected",
    "problem",
}


# -- assets -----------------------------------------------------------------------


@cache
def _mdi() -> dict[str, int]:
    return json.loads(resources.files("frameartdash.webui").joinpath("static/mdi.json").read_text())


@cache
def _font_data(name: str) -> str:
    data = resources.files("frameartdash.webui").joinpath(f"static/{name}").read_bytes()
    return "data:font/woff2;base64," + base64.b64encode(data).decode()


def _font_faces(inline: bool) -> str:
    def src(name):
        return _font_data(name) if inline else f"/static/{name}"

    return "".join(
        f"@font-face{{font-family:'{family}';src:url('{src(file)}') format('woff2');font-weight:{weight};"
        "font-display:block;}"
        for family, file, weight in (
            ("Inter", "inter.woff2", "100 900"),
            ("Fraunces", "fraunces.woff2", "100 900"),
            ("JetBrains Mono", "jetbrains-mono.woff2", "100 800"),
            ("Material Design Icons", "mdi.woff2", "400"),
        )
    )


def icon(name: str | None, cls: str = "") -> str:
    name = (name or "").removeprefix("mdi:")
    code = _mdi().get(name) or _mdi().get("help-circle-outline")
    return f'<i class="mdi {cls}">&#x{code:x};</i>'


# -- entity helpers ---------------------------------------------------------------


def attrs(st: dict | None) -> dict:
    return (st or {}).get("attributes") or {}


def entity_name(st: dict | None, override: str = "", fallback: str = "") -> str:
    return override or attrs(st).get("friendly_name") or fallback


def entity_icon(st: dict | None, override: str = "") -> str:
    if override:
        return override
    a = attrs(st)
    if a.get("icon"):
        return a["icon"]
    eid = (st or {}).get("entity_id", "")
    domain = eid.split(".")[0]
    if domain == "weather":
        return WEATHER_ICONS.get((st or {}).get("state", ""), "weather-partly-cloudy")
    if domain == "person" and (st or {}).get("state") != "home":
        return "account-arrow-right-outline"
    return CLASS_ICONS.get(a.get("device_class", ""), DOMAIN_ICONS.get(domain, "eye-outline"))


def _decimals(opts: dict) -> int | None:
    value = opts.get("decimals")
    return None if value in ("", None) else int(value)


def to_float(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def state_text(st: dict | None, data: CardData) -> str:
    """Localized text for a non-numeric state."""
    loc = data.locale
    if not st:
        return "–"
    state = st.get("state", "")
    if state in ("unavailable", "unknown", ""):
        return "–"
    domain = st["entity_id"].split(".")[0]
    dc = attrs(st).get("device_class", "")
    if domain == "binary_sensor":
        on, off = BINARY.get(dc, ("on", "off"))
        return loc[on if state == "on" else off]
    if domain in ("person", "device_tracker"):
        return loc["home"] if state == "home" else (loc["away"] if state == "not_home" else state)
    if dc == "timestamp" or domain == "input_datetime":
        try:
            when = datetime.fromisoformat(state)
            if when.tzinfo:
                when = when.astimezone(data.now.tzinfo)
            day = loc.relative_day(when.date(), data.now.date())
            return f"{day}, {loc.time(when)}" if (when.hour or when.minute) else day
        except ValueError:
            return state
    if dc == "date":
        try:
            return loc.relative_day(date.fromisoformat(state), data.now.date())
        except ValueError:
            return state
    if domain == "weather":
        return loc.weather(state)
    return loc[state] if state in loc.t else state


def value_parts(st: dict | None, data: CardData, opts: dict, attribute: str = "") -> tuple[str, str]:
    """(value, unit) for display; unit is empty for non-numeric states."""
    if not st:
        return "–", ""
    raw = attrs(st).get(attribute) if attribute else st.get("state")
    unit = "" if attribute else attrs(st).get("unit_of_measurement", "")
    number = to_float(raw)
    if number is None:
        return (str(raw) if attribute else state_text(st, data)), ""
    return data.locale.quantity(number, unit, _decimals(opts))


def is_active(st: dict | None) -> bool:
    if not st:
        return False
    state = st.get("state", "")
    if st["entity_id"].startswith("binary_sensor."):
        return state == "on"
    number = to_float(state)
    return number > 0 if number is not None else state in ACTIVE


def _missing(entity: str) -> str:
    return f'<div class="note">{icon("alert-circle-outline")} {escape(entity or "no entity selected")}</div>'


# -- charts -------------------------------------------------------------------------


def _series_path(
    points, start: datetime, end: datetime, lo: float, hi: float, w=1000, h=300
) -> tuple[str, str]:
    span = (end - start).total_seconds() or 1
    rng = (hi - lo) or 1
    coords = []
    for when, value in points:
        x = max(0.0, min(1.0, (when - start).total_seconds() / span)) * w
        y = h - (value - lo) / rng * h
        coords.append((x, y))
    if not coords:
        return "", ""
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = line + f" L{coords[-1][0]:.1f},{h} L{coords[0][0]:.1f},{h} Z"
    return line, area


def _window(points, start: datetime, end: datetime, current: float | None):
    """Clip to the window and extend the line to both edges."""
    inside = [(t, v) for t, v in points if t >= start]
    before = [(t, v) for t, v in points if t < start]
    if before:
        inside.insert(0, (start, before[-1][1]))
    if current is not None:
        inside.append((end, current))
    elif inside:
        inside.append((end, inside[-1][1]))
    return inside


def chart_svg(series: list[tuple[list, str]], start, end, fill: bool, h=300) -> tuple[str, float, float]:
    values = [v for pts, _ in series for _, v in pts]
    if not values:
        return "", 0, 0
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.08 or max(abs(hi) * 0.05, 1)
    lo, hi = lo - pad, hi + pad
    parts = []
    for i, (pts, color) in enumerate(series):
        line, area = _series_path(pts, start, end, lo, hi, h=h)
        if not line:
            continue
        if fill:
            parts.append(
                f'<linearGradient id="g{i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{color}" '
                f'stop-opacity=".32"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient>'
                f'<path d="{area}" fill="url(#g{i})" stroke="none"/>'
            )
        parts.append(
            f'<path d="{line}" fill="none" stroke="{color}" stroke-width="2.4" '
            'vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>'
        )
    svg = f'<svg viewBox="0 0 1000 {h}" preserveAspectRatio="none">{"".join(parts)}</svg>'
    return svg, lo + pad, hi - pad


# -- cards --------------------------------------------------------------------------


def card_clock(card, o, data: CardData) -> str:
    loc, now = data.locale, data.now
    h12 = o.get("format") == "12h"
    time = loc.time(now, h12=h12)
    date_html = (
        f'<div class="sub">{escape(loc.date(now.date(), o.get("date_format", "long")))}</div>'
        if o.get("show_date")
        else ""
    )
    return f'<div class="hero clock">{escape(time)}</div>{date_html}'


def card_date(card, o, data: CardData) -> str:
    return (
        f'<div class="hero date">{escape(data.locale.date(data.now.date(), o.get("format", "long")))}</div>'
    )


def card_countdown(card, o, data: CardData) -> str:
    target: date | None = None
    if o.get("date"):
        try:
            target = date.fromisoformat(o["date"])
        except ValueError:
            pass
    elif st := data.state(o.get("entity")):
        a = attrs(st)
        raw = a.get("start_time") if st["entity_id"].startswith("calendar.") else st.get("state")
        try:
            parsed = datetime.fromisoformat(str(raw))
            target = (parsed.astimezone(data.now.tzinfo) if parsed.tzinfo else parsed).date()
        except (TypeError, ValueError):
            try:
                target = date.fromisoformat(str(raw))
            except (TypeError, ValueError):
                pass
    title = escape(o.get("title") or "")
    head = f'<div class="head">{icon(o.get("icon") or "calendar-star")}<span>{title}</span></div>'
    if target is None:
        return head + '<div class="hero">–</div>'
    days = (target - data.now.date()).days
    if days in (0, 1) or days < 0:
        return head + f'<div class="hero">{escape(data.locale.in_days(days))}</div>'
    unit = "Tage" if data.locale.lang == "de" else "days"
    return head + f'<div class="hero">{days}<span class="unit">{unit}</span></div>'


_PLACEHOLDER = re.compile(r"\{([a-z_]+\.[a-z0-9_]+)\}")


def card_text(card, o, data: CardData) -> str:
    def replace(m):
        st = data.state(m.group(1))
        value, unit = value_parts(st, data, {})
        return f"{value} {unit}" if unit else value

    raw = o.get("text") or ""
    parts, last = [], 0
    for m in _PLACEHOLDER.finditer(raw):
        parts.append(escape(raw[last : m.start()]))
        parts.append(f"<b>{escape(replace(m))}</b>")
        last = m.end()
    parts.append(escape(raw[last:]))
    font = o.get("font", "inherit")
    family = f"font-family:{FONTS[font]};" if font in FONTS else ""
    text = "".join(parts).replace("\n", "<br>")
    return f'<div class="text" style="{family}font-weight:{escape(str(o.get("weight") or 400))}">{text}</div>'


def _sparkline(eid: str, o, data: CardData) -> str:
    hours = float(o.get("hours") or 24)
    end = data.now
    start = end - timedelta(hours=hours)
    current = to_float((data.state(eid) or {}).get("state"))
    pts = _window(data.history.get(eid, []), start, end, current)
    svg, _, _ = chart_svg([(pts, "var(--accent)")], start, end, fill=True, h=120)
    return f'<div class="spark">{svg}</div>' if svg else ""


def card_value(card, o, data: CardData) -> str:
    st = data.state(o.get("entity"))
    if not st:
        return _missing(o.get("entity"))
    value, unit = value_parts(st, data, o, o.get("attribute", ""))
    ic = icon(entity_icon(st, o.get("icon")), "accent") if o.get("show_icon", True) else ""
    head = f'<div class="head">{ic}<span>{escape(entity_name(st, o.get("name")))}</span></div>'
    unit_html = f'<span class="unit">{escape(unit)}</span>' if unit else ""
    spark = _sparkline(st["entity_id"], o, data) if o.get("sparkline") else ""
    return f'{head}<div class="hero value">{escape(value)}{unit_html}</div>{spark}'


def card_big(card, o, data: CardData) -> str:
    st = data.state(o.get("entity"))
    if not st:
        return _missing(o.get("entity"))
    value, unit = value_parts(st, data, o)
    unit_html = f'<span class="unit">{escape(unit)}</span>' if unit and o.get("show_unit", True) else ""
    label = f'<div class="sub">{escape(o["name"])}</div>' if o.get("name") else ""
    return f'<div class="hero big">{escape(value)}{unit_html}</div>{label}'


def card_status(card, o, data: CardData) -> str:
    st = data.state(o.get("entity"))
    if not st:
        return _missing(o.get("entity"))
    active = is_active(st)
    text = (o.get("on_text") if active else o.get("off_text")) or state_text(st, data)
    if to_float(st.get("state")) is not None and not (o.get("on_text") or o.get("off_text")):
        text = " ".join(p for p in value_parts(st, data, o) if p)
    return (
        f'<div class="status {"on" if active else ""}">{icon(entity_icon(st, o.get("icon")), "dot")}'
        f'<div><div class="name">{escape(entity_name(st, o.get("name")))}</div>'
        f'<div class="state">{escape(text)}</div></div></div>'
    )


def card_entities(card, o, data: CardData) -> str:
    rows = []
    for eid in o.get("entities") or []:
        st = data.state(eid)
        value, unit = value_parts(st, data, o)
        ic = icon(entity_icon(st), "accent") if o.get("show_icons", True) else ""
        rows.append(
            f'<div class="row">{ic}<span class="name">{escape(entity_name(st, fallback=eid))}</span>'
            f'<span class="val">{escape(value)}<small>{escape(unit)}</small></span></div>'
        )
    title = f'<div class="title">{escape(o["title"])}</div>' if o.get("title") else ""
    return title + f'<div class="rows">{"".join(rows) or _missing("")}</div>'


def _range(o) -> tuple[float, float]:
    lo, hi = to_float(o.get("min")), to_float(o.get("max"))
    lo = 0.0 if lo is None else lo
    hi = 100.0 if hi is None or hi == lo else hi
    return lo, hi


def card_bar(card, o, data: CardData) -> str:
    st = data.state(o.get("entity"))
    if not st:
        return _missing(o.get("entity"))
    lo, hi = _range(o)
    number = to_float(st.get("state"))
    pct = 0 if number is None else max(0, min(100, (number - lo) / (hi - lo) * 100))
    value, unit = value_parts(st, data, o)
    color = escape(o.get("color") or "var(--accent)")
    return (
        f'<div class="head"><span>{escape(entity_name(st, o.get("name")))}</span>'
        f'<span class="right">{escape(value)}<small>{escape(unit)}</small></span></div>'
        f'<div class="track"><div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div>'
    )


def _arc(cx, cy, r, a0, a1) -> str:
    def pt(a):
        rad = math.radians(a)
        return cx + r * math.cos(rad), cy + r * math.sin(rad)

    x0, y0 = pt(a0)
    x1, y1 = pt(a1)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{x0:.2f},{y0:.2f} A{r},{r} 0 {large} 1 {x1:.2f},{y1:.2f}"


def card_gauge(card, o, data: CardData) -> str:
    st = data.state(o.get("entity"))
    if not st:
        return _missing(o.get("entity"))
    lo, hi = _range(o)
    number = to_float(st.get("state"))
    frac = 0 if number is None else max(0, min(1, (number - lo) / (hi - lo)))
    start, sweep = 150, 240
    value, unit = value_parts(st, data, o)
    color = escape(o.get("color") or "var(--accent)")
    track = _arc(50, 50, 40, start, start + sweep)
    fill = _arc(50, 50, 40, start, start + max(sweep * frac, 0.5))
    return (
        f'<div class="gauge"><svg viewBox="0 0 100 86"><path d="{track}" class="g-track"/>'
        f'<path d="{fill}" class="g-fill" style="stroke:{color}"/></svg>'
        f'<div class="g-val">{escape(value)}<small>{escape(unit)}</small></div></div>'
        f'<div class="sub center">{escape(entity_name(st, o.get("name")))}</div>'
    )


def card_graph(card, o, data: CardData) -> str:
    hours = float(o.get("hours") or 24)
    end = data.now
    start = end - timedelta(hours=hours)
    series, legend = [], []
    for i, eid in enumerate(o.get("entities") or []):
        st = data.state(eid)
        color = PALETTE[i % len(PALETTE)]
        pts = _window(data.history.get(eid, []), start, end, to_float((st or {}).get("state")))
        series.append((pts, color))
        value, unit = value_parts(st, data, o)
        legend.append(
            f'<span><i class="sw" style="background:{color}"></i>{escape(entity_name(st, fallback=eid))}'
            f" <b>{escape(value)} {escape(unit)}</b></span>"
        )
    svg, lo, hi = chart_svg(series, start, end, fill=bool(o.get("fill", True)))
    title = f'<div class="title">{escape(o["title"])}</div>' if o.get("title") else ""
    if not svg:
        return title + _missing("no history")
    loc = data.locale
    scale = f'<div class="axis"><span>{loc.number(hi)}</span><span>{loc.number(lo)}</span></div>'
    times = "".join(f"<span>{loc.time(start + (end - start) * f)}</span>" for f in (0, 0.5, 1))
    legend_html = f'<div class="legend">{"".join(legend)}</div>' if o.get("show_legend", True) else ""
    return f'{title}<div class="chart">{scale}{svg}</div><div class="times">{times}</div>{legend_html}'


def card_weather(card, o, data: CardData) -> str:
    st = data.state(o.get("entity"))
    if not st:
        return _missing(o.get("entity"))
    a, loc = attrs(st), data.locale
    temp = to_float(a.get("temperature"))
    unit = a.get("temperature_unit", "°")
    details = ""
    if o.get("show_details", True):
        bits = []
        if a.get("humidity") is not None:
            bits.append(f"{icon('water-percent')}{loc.number(float(a['humidity']), 0)} %")
        if a.get("wind_speed") is not None:
            bits.append(
                f"{icon('weather-windy')}{loc.number(float(a['wind_speed']), 0)} {escape(a.get('wind_speed_unit', ''))}"
            )
        details = f'<div class="details">{"".join(f"<span>{b}</span>" for b in bits)}</div>'
    name = o.get("name") or ""
    current = (
        f'<div class="w-now">{icon(WEATHER_ICONS.get(st["state"], "weather-partly-cloudy"), "w-icon")}'
        f'<div><div class="hero">{loc.number(temp, 1) if temp is not None else "–"}<span class="unit">{escape(unit)}</span></div>'
        f'<div class="sub">{escape(loc.weather(st["state"]))}{" · " + escape(name) if name else ""}</div></div>{details}</div>'
    )
    days = []
    for f in (data.forecasts.get(st["entity_id"]) or [])[: int(o.get("forecast_days") or 0)]:
        try:
            day = datetime.fromisoformat(f["datetime"]).astimezone(data.now.tzinfo).date()
        except (KeyError, ValueError):
            continue
        hi_t, lo_t = to_float(f.get("temperature")), to_float(f.get("templow"))
        days.append(
            f'<div class="day"><span class="wd">{escape(loc.t["weekdays_short"][day.weekday()])}</span>'
            f"{icon(WEATHER_ICONS.get(f.get('condition', ''), 'weather-partly-cloudy'))}"
            f'<span class="hi">{loc.number(hi_t, 0) if hi_t is not None else "–"}°</span>'
            f'<span class="lo">{loc.number(lo_t, 0) if lo_t is not None else ""}{"°" if lo_t is not None else ""}</span></div>'
        )
    forecast = f'<div class="forecast">{"".join(days)}</div>' if days else ""
    return current + forecast


def card_energy(card, o, data: CardData) -> str:
    loc = data.locale

    def power(key, invert=False):
        st = data.state(o.get(key))
        v = to_float((st or {}).get("state"))
        if v is None:
            return None, st
        return (-v if invert else v), st

    def fmt(v, st):
        if v is None:
            return "–"
        unit = attrs(st).get("unit_of_measurement", "W")
        return " ".join(loc.quantity(abs(v), unit))

    solar, s_st = power("solar")
    grid, g_st = power("grid", bool(o.get("invert_grid")))
    battery, b_st = power("battery", bool(o.get("invert_battery")))
    home, h_st = power("home")
    soc = to_float((data.state(o.get("battery_soc")) or {}).get("state"))
    eps = 15

    pos = {"solar": (50, 17), "grid": (15, 50), "battery": (85, 50), "home": (50, 82)}

    def node(cls, ic, label, value, extra=""):
        x, y = pos[cls]
        return (
            f'<div class="node {cls}" style="left:{x}%;top:{y}%"><div class="circle">{icon(ic)}<b>{escape(value)}</b>'
            f"{extra}</div><span>{escape(label)}</span></div>"
        )

    def flow(key, value, active):
        x, y = pos[key]
        hx, hy = pos["home"]
        return f'<line x1="{x}" y1="{y}" x2="{hx}" y2="{hy}" class="{"on" if active else ""}"/>'

    def sub(text):
        return f"<small>{escape(text)}</small>" if text else ""

    grid_dir = loc["import"] if (grid or 0) > eps else loc["export"] if (grid or 0) < -eps else ""
    bat_dir = loc["discharging"] if (battery or 0) > eps else loc["charging"] if (battery or 0) < -eps else ""
    soc_text = f"{loc.number(soc, 0)} %" if soc is not None else ""
    nodes, lines = [], []
    if o.get("solar"):
        nodes.append(node("solar", "solar-power-variant", loc["solar"], fmt(solar, s_st)))
        lines.append(flow("solar", solar, (solar or 0) > eps))
    if o.get("grid"):
        nodes.append(node("grid", "transmission-tower", loc["grid"], fmt(grid, g_st), sub(grid_dir)))
        lines.append(flow("grid", grid, abs(grid or 0) > eps))
    if o.get("battery") or o.get("battery_soc"):
        value = fmt(battery, b_st) if o.get("battery") else soc_text
        extra = sub(" · ".join(t for t in (soc_text if o.get("battery") else "", bat_dir) if t))
        nodes.append(node("battery", "home-battery-outline", loc["battery"], value, extra))
        lines.append(flow("battery", battery, abs(battery or 0) > eps))
    nodes.append(node("home", "home-lightning-bolt-outline", loc["house"], fmt(home, h_st)))
    svg = f'<svg class="flows" viewBox="0 0 100 100" preserveAspectRatio="none">{"".join(lines)}</svg>'
    return f'<div class="energy">{svg}{"".join(nodes)}</div>'


def card_calendar(card, o, data: CardData) -> str:
    loc = data.locale
    title = f'<div class="title">{escape(o["title"])}</div>' if o.get("title") else ""
    events = []
    for ev in data.events.get(card["id"], []):
        start = ev.get("start") or {}
        if "dateTime" in start:
            when = datetime.fromisoformat(start["dateTime"]).astimezone(data.now.tzinfo)
            events.append((when.date(), loc.time(when), when, ev))
        elif "date" in start:
            day = date.fromisoformat(start["date"])
            events.append((day, loc["all_day"], datetime.combine(day, datetime.min.time()), ev))
    events.sort(key=lambda e: (e[0], e[1] != loc["all_day"], e[2].replace(tzinfo=None)))
    calendars = o.get("entities") or []
    rows, last_day = [], None
    for day, time, _, ev in events[: int(o.get("max_events") or 6)]:
        if day != last_day:
            rows.append(f'<div class="day-label">{escape(loc.relative_day(day, data.now.date()))}</div>')
            last_day = day
        color = (
            PALETTE[calendars.index(ev["calendar"]) % len(PALETTE)]
            if ev.get("calendar") in calendars
            else PALETTE[0]
        )
        rows.append(
            f'<div class="event"><i class="sw" style="background:{color}"></i><span class="time">{escape(time)}</span>'
            f'<span class="what">{escape(ev.get("summary") or "")}</span></div>'
        )
    body = "".join(rows) or f'<div class="note">{escape(loc["no_events"])}</div>'
    return title + f'<div class="events">{body}</div>'


def card_todo(card, o, data: CardData) -> str:
    st = data.state(o.get("entity"))
    title = escape(o.get("title") or entity_name(st, fallback=o.get("entity") or ""))
    items = data.todos.get(o.get("entity"), [])[: int(o.get("max_items") or 8)]
    rows = "".join(
        f'<div class="item">{icon("checkbox-blank-circle-outline")}<span>{escape(i.get("summary", ""))}</span></div>'
        for i in items
    )
    body = rows or f'<div class="note">{icon("check-all")} {escape(data.locale["nothing_todo"])}</div>'
    return f'<div class="title">{title}</div><div class="items">{body}</div>'


def card_persons(card, o, data: CardData) -> str:
    people = []
    for eid in o.get("entities") or []:
        st = data.state(eid)
        name = entity_name(st, fallback=eid)
        home = (st or {}).get("state") == "home"
        pic = data.images.get(eid)
        avatar = f'<img src="{pic}" alt="">' if pic else f"<span>{escape(name[:1].upper())}</span>"
        label = f'<div class="pname">{escape(name)}</div>' if o.get("show_names", True) else ""
        state = (
            f'<div class="pstate">{escape(state_text(st, data))}</div>' if o.get("show_state", True) else ""
        )
        people.append(
            f'<div class="person {"home" if home else "away"}"><div class="avatar">{avatar}</div>{label}{state}</div>'
        )
    return f'<div class="people">{"".join(people) or _missing("")}</div>'


def card_media(card, o, data: CardData) -> str | None:
    st = data.state(o.get("entity"))
    if not st:
        return _missing(o.get("entity"))
    a = attrs(st)
    playing = st.get("state") in ("playing", "paused")
    if not playing:
        if o.get("hide_idle", True):
            return None
        return f'<div class="note">{icon("music-off")} {escape(data.locale["nothing_playing"])}</div>'
    cover = data.images.get(st["entity_id"]) if o.get("show_cover", True) else None
    art = (
        f'<img class="cover" src="{cover}" alt="">' if cover else f'<div class="cover">{icon("music")}</div>'
    )
    artist = a.get("media_artist") or a.get("media_album_name") or ""
    return (
        f'<div class="media">{art}<div><div class="mtitle">{escape(a.get("media_title") or "")}</div>'
        f'<div class="sub">{escape(artist)}</div><div class="src">{icon("speaker")} {escape(entity_name(st))}</div></div></div>'
    )


def card_camera(card, o, data: CardData) -> str:
    st = data.state(o.get("entity"))
    img = data.images.get(o.get("entity") or "")
    if not img:
        return _missing(o.get("entity") or "camera")
    fit = "contain" if o.get("fit") == "contain" else "cover"
    name = f'<div class="cam-name">{escape(entity_name(st))}</div>' if o.get("show_name", True) else ""
    return f'<img class="cam" style="object-fit:{fit}" src="{img}" alt="">{name}'


def card_sun(card, o, data: CardData) -> str:
    st = data.state(o.get("entity") or "sun.sun")
    if not st:
        return _missing(o.get("entity") or "sun.sun")
    a, loc, now = attrs(st), data.locale, data.now

    def parse(key):
        try:
            return datetime.fromisoformat(a[key]).astimezone(now.tzinfo)
        except (KeyError, ValueError):
            return None

    rising, setting = parse("next_rising"), parse("next_setting")
    up = st.get("state") == "above_horizon"
    # Today's sunrise lies in the past while the sun is up; approximate it from tomorrow's.
    sunrise = rising - timedelta(days=1) if (rising and up) else rising
    sunset = setting
    arc = ""
    if o.get("show_arc", True) and sunrise and sunset and sunset > sunrise:
        frac = (now - sunrise).total_seconds() / (sunset - sunrise).total_seconds()
        frac = max(0.0, min(1.0, frac)) if up else (0.0 if now < sunrise else 1.0)
        angle = math.pi * (1 - frac)
        x, y = 50 + 42 * math.cos(angle), 46 - 38 * math.sin(angle)
        arc = (
            f'<svg class="sun-arc" viewBox="0 0 100 50"><path d="M8,46 A42,38 0 0 1 92,46" class="g-track"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" class="{"sun-up" if up else "sun-down"}"/></svg>'
        )
    return (
        f'{arc}<div class="sun-times"><span>{icon("weather-sunset-up", "accent")}<b>{loc.time(sunrise) if sunrise else "–"}</b>'
        f"<small>{escape(loc['sunrise'])}</small></span><span>{icon('weather-sunset-down', 'accent')}"
        f"<b>{loc.time(sunset) if sunset else '–'}</b><small>{escape(loc['sunset'])}</small></span></div>"
    )


RENDERERS = {
    "clock": card_clock,
    "date": card_date,
    "countdown": card_countdown,
    "text": card_text,
    "value": card_value,
    "big": card_big,
    "status": card_status,
    "entities": card_entities,
    "bar": card_bar,
    "gauge": card_gauge,
    "graph": card_graph,
    "weather": card_weather,
    "energy": card_energy,
    "calendar": card_calendar,
    "todo": card_todo,
    "persons": card_persons,
    "media": card_media,
    "camera": card_camera,
    "sun": card_sun,
}


# -- page ---------------------------------------------------------------------------


def _hex_rgb(color: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    color = color.strip().lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    try:
        return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    except (ValueError, IndexError):
        return fallback


def render_card(card: dict, data: CardData, default_style: str, edit: bool) -> str:
    o = card["options"]
    style = o.get("style") if o.get("style") not in ("", "inherit") else default_style
    if data.errors.get(card["id"]):
        inner = f'<div class="note">{icon("alert-circle-outline")} {escape(data.errors[card["id"]])}</div>'
    else:
        try:
            inner = RENDERERS[card["type"]](card, o, data)
        except Exception as e:  # noqa: BLE001 - one broken card must not break the picture
            inner = f'<div class="note">{icon("alert-circle-outline")} {escape(type(e).__name__)}: {escape(str(e))}</div>'
    if inner is None:
        if not edit:
            return ""
        inner = f'<div class="note">{icon("eye-off-outline")} hidden</div>'
    scale = to_float(o.get("scale")) or 100
    return (
        f'<div class="card t-{card["type"]} s-{escape(style)} a-{escape(o.get("align", "left"))}" data-card="{escape(card["id"])}" '
        f'style="left:{card["x"]}%;top:{card["y"]}%;width:{card["w"]}%;height:{card["h"]}%;--s:{scale / 100:.3f}">'
        f'<div class="inner">{inner}</div></div>'
    )


def build_page(layout: dict, data: CardData, background: str, inline_assets: bool, edit: bool = False) -> str:
    s = layout["style"]
    r, g, b = _hex_rgb(s.get("text_color", "#f4f1ea"), (244, 241, 234))
    tint = (12, 14, 18) if s.get("tint") != "light" else (250, 248, 244)
    opacity = max(0, min(100, to_float(s.get("opacity")) or 0)) / 100
    dim = max(0, min(90, to_float(s.get("dim")) or 0)) / 100
    shadow = "0 18px 50px rgba(0,0,0,.35), 0 2px 8px rgba(0,0,0,.18)" if s.get("shadow", True) else "none"
    cards = [c for c in layout["cards"] if edit or visible(c, data.states)]
    body = "".join(render_card(c, data, s.get("card_style", "glass"), edit) for c in cards)
    font = FONTS.get(s.get("font"), FONTS["sans"])
    css = CSS.replace(
        "/*VARS*/",
        (
            f"--font:{font};--text:rgb({r},{g},{b});--text-rgb:{r},{g},{b};--accent:{escape(s.get('accent') or '#e3c27a')};"
            f"--tint:{tint[0]},{tint[1]},{tint[2]};--alpha:{opacity:.2f};--blur:{to_float(s.get('blur')) or 0}px;"
            f"--radius:{to_float(s.get('radius')) or 0}px;--shadow:{shadow};--dim:{dim:.2f};"
        ),
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        + _font_faces(inline_assets)
        + css
        + f"body{{background:{background}}}"
        + "</style></head><body class='"
        + ("edit" if edit else "")
        + "'><div class='dim'></div>"
        + body
        + "</body></html>"
    )


CSS = """
:root{/*VARS*/}
*{box-sizing:border-box}
html,body{margin:0;width:1920px;height:1080px;overflow:hidden}
body{position:relative;background-size:cover!important;background-position:center!important;font-family:var(--font);
  color:var(--text);-webkit-font-smoothing:antialiased;font-feature-settings:"tnum" 1,"cv11" 1}
.dim{position:absolute;inset:0;background:rgba(0,0,0,var(--dim));pointer-events:none}
.mdi{font-family:'Material Design Icons';font-style:normal;font-weight:400;line-height:1;display:inline-block}
.card{position:absolute;container-type:size;border-radius:var(--radius);overflow:hidden;font-size:calc(19px*var(--s));line-height:1.25}
.card .inner{position:absolute;inset:0;padding:1.05em 1.25em;display:flex;flex-direction:column;gap:.45em;justify-content:center}
.s-glass{background:rgba(var(--tint),var(--alpha));backdrop-filter:blur(var(--blur)) saturate(140%);
  -webkit-backdrop-filter:blur(var(--blur)) saturate(140%);border:1px solid rgba(255,255,255,.14);box-shadow:var(--shadow)}
.s-solid{background:rgba(var(--tint),.92);box-shadow:var(--shadow)}
.s-outline{border:1.5px solid rgba(var(--text-rgb),.55)}
.s-none{text-shadow:0 2px 14px rgba(0,0,0,.55),0 1px 3px rgba(0,0,0,.4)}
.s-none .inner{padding:.4em .2em}
.a-center .inner{align-items:center;text-align:center}.a-right .inner{align-items:flex-end;text-align:right}
.accent{color:var(--accent)}
.head{display:flex;align-items:center;gap:.5em;color:rgba(var(--text-rgb),.78);font-size:1em;white-space:nowrap;overflow:hidden}
.head span{overflow:hidden;text-overflow:ellipsis}.head .right{margin-left:auto;color:var(--text);font-weight:600}
.head .mdi{font-size:1.25em}
.title{font-size:1.05em;font-weight:600;letter-spacing:.01em;margin-bottom:.15em}
.sub{color:rgba(var(--text-rgb),.72);font-size:1.05em}.center{text-align:center}
.hero{font-weight:300;letter-spacing:-.02em;line-height:1;white-space:nowrap}
.hero .unit{font-size:.42em;font-weight:400;margin-left:.18em;opacity:.75;letter-spacing:0}
.value.hero{font-size:min(46cqh,22cqw)}.big.hero{font-size:min(68cqh,30cqw);font-weight:250}
.clock.hero{font-size:min(60cqh,27cqw);font-weight:250}.date.hero{font-size:min(50cqh,8cqw);font-weight:350;white-space:normal}
.t-countdown .hero{font-size:min(48cqh,24cqw)}
.text{font-size:1.6em;line-height:1.2;white-space:normal}
.note{color:rgba(var(--text-rgb),.6);font-size:.9em;display:flex;gap:.4em;align-items:center}
.spark{height:28cqh;margin:.2em -1.25em -1.05em}.spark svg{width:100%;height:100%;display:block}
.t-value .inner,.t-calendar .inner,.t-todo .inner,.t-entities .inner{justify-content:flex-start}.t-value .hero{margin-top:auto;margin-bottom:auto}
.status{display:flex;align-items:center;gap:.7em}.status .dot{font-size:2.1em;opacity:.55}
.status.on .dot{color:var(--accent);opacity:1;filter:drop-shadow(0 0 .35em var(--accent))}
.status .name{color:rgba(var(--text-rgb),.75)}.status .state{font-size:1.35em;font-weight:500}
.rows{display:flex;flex-direction:column;gap:.55em}.row{display:flex;align-items:center;gap:.6em}
.row .name{flex:1;color:rgba(var(--text-rgb),.82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .val{font-weight:600;white-space:nowrap}.row small,.right small,.g-val small{font-weight:400;opacity:.7;margin-left:.15em}
.row .mdi{font-size:1.2em;width:1.3em;text-align:center}
.track{height:max(.5em,12cqh);border-radius:99em;background:rgba(var(--text-rgb),.16);overflow:hidden}
.fill{height:100%;border-radius:99em}
.gauge{position:relative;flex:1;min-height:0}.gauge svg{width:100%;height:100%}
.g-track{fill:none;stroke:rgba(var(--text-rgb),.16);stroke-width:7;stroke-linecap:round}
.g-fill{fill:none;stroke-width:7;stroke-linecap:round}
.g-val{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:min(20cqh,18cqw);font-weight:350;padding-top:6%}
.chart{position:relative;flex:1;min-height:0;padding-left:3.2em}.chart svg{width:100%;height:100%;display:block;overflow:visible}
.axis{position:absolute;left:0;top:0;bottom:0;display:flex;flex-direction:column;justify-content:space-between;font-size:.72em;color:rgba(var(--text-rgb),.55)}
.times{display:flex;justify-content:space-between;padding-left:4.45em;font-size:.72em;color:rgba(var(--text-rgb),.55)}
.legend{display:flex;flex-wrap:wrap;gap:.3em 1.2em;font-size:.85em;color:rgba(var(--text-rgb),.8)}
.legend b{color:var(--text);font-weight:600;margin-left:.2em}
.sw{display:inline-block;width:.7em;height:.7em;border-radius:50%;margin-right:.45em;vertical-align:.05em}
.w-now{display:flex;align-items:center;gap:.6em}.w-icon{font-size:min(38cqh,15cqw);color:var(--accent)}
.w-now .hero{font-size:min(30cqh,13cqw)}.details{margin-left:auto;display:flex;flex-direction:column;gap:.35em;font-size:.9em;color:rgba(var(--text-rgb),.8)}
.details .mdi{margin-right:.35em}.a-center .w-now{justify-content:center}
.forecast{display:flex;justify-content:space-between;gap:.4em;margin-top:.4em;padding-top:.7em;border-top:1px solid rgba(var(--text-rgb),.14)}
.day{display:flex;flex-direction:column;align-items:center;gap:.25em;flex:1}.day .mdi{font-size:1.7em}
.day .wd{color:rgba(var(--text-rgb),.7);font-size:.9em}.day .hi{font-weight:600}.day .lo{color:rgba(var(--text-rgb),.6);font-size:.9em}
.energy{position:relative;flex:1;min-height:0}
.node{position:absolute;display:flex;flex-direction:column;align-items:center;gap:.3em;transform:translate(-50%,-50%);font-size:.85em;color:rgba(var(--text-rgb),.75)}
.circle{width:min(30cqh,24cqw);aspect-ratio:1;border-radius:50%;border:2px solid rgba(var(--text-rgb),.35);display:flex;flex-direction:column;
  align-items:center;justify-content:center;background:rgba(var(--tint),.82);color:var(--text);gap:.05em}
.circle .mdi{font-size:1.5em;color:var(--accent)}.circle b{font-size:1em;font-weight:600;white-space:nowrap}
.circle small{font-size:.68em;opacity:.75;white-space:nowrap}
.node.home .circle{border-color:var(--accent)}
.node>span{position:absolute;top:100%;margin-top:.3em;white-space:nowrap}
.node.solar>span{top:auto;bottom:100%;margin:0 0 .3em}
.flows{position:absolute;inset:0;width:100%;height:100%}
.flows line{stroke:rgba(var(--text-rgb),.2);stroke-width:2;vector-effect:non-scaling-stroke}
.flows line.on{stroke:var(--accent);stroke-width:3;filter:drop-shadow(0 0 4px var(--accent))}
.events{display:flex;flex-direction:column;gap:.38em;overflow:hidden}
.day-label{font-size:.8em;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);margin-top:.35em}
.event{display:flex;align-items:baseline;gap:.2em;white-space:nowrap}.event .time{color:rgba(var(--text-rgb),.65);min-width:5.2em;font-size:.92em}
.event .what{overflow:hidden;text-overflow:ellipsis}
.items{display:flex;flex-direction:column;gap:.45em;overflow:hidden}.item{display:flex;gap:.5em;align-items:center}
.item .mdi{opacity:.55}
.people{display:flex;gap:1.2em;justify-content:space-around;align-items:center;flex:1}
.person{display:flex;flex-direction:column;align-items:center;gap:.3em}
.avatar{width:min(52cqh,22cqw);aspect-ratio:1;border-radius:50%;overflow:hidden;display:flex;align-items:center;justify-content:center;
  background:rgba(var(--text-rgb),.15);font-size:1.6em;font-weight:600;border:2px solid var(--accent)}
.avatar img{width:100%;height:100%;object-fit:cover}.person.away .avatar{filter:grayscale(1);opacity:.5;border-color:transparent}
.pname{font-weight:600}.pstate{font-size:.85em;color:rgba(var(--text-rgb),.65)}
.media{display:flex;gap:1em;align-items:center;height:100%}.cover{height:min(100%,80cqh);aspect-ratio:1;border-radius:.6em;object-fit:cover;
  background:rgba(var(--text-rgb),.12);display:flex;align-items:center;justify-content:center;font-size:2em}
.mtitle{font-size:1.3em;font-weight:600}.src{font-size:.8em;color:rgba(var(--text-rgb),.6);margin-top:.4em}
.t-camera .inner{padding:0}.cam{position:absolute;inset:0;width:100%;height:100%}
.cam-name{position:absolute;left:0;right:0;bottom:0;padding:.8em 1em .6em;background:linear-gradient(transparent,rgba(0,0,0,.6));font-size:.9em}
.sun-arc{width:100%;flex:1;min-height:0}.sun-up{fill:var(--accent);filter:drop-shadow(0 0 3px var(--accent))}.sun-down{fill:rgba(var(--text-rgb),.4)}
.sun-times{display:flex;justify-content:space-between;gap:.6em}
.sun-times span{display:grid;grid-template-columns:auto auto;column-gap:.35em;align-items:center}
.sun-times b{font-weight:600}.sun-times small{grid-column:2;color:rgba(var(--text-rgb),.6);font-size:.8em}
body.edit .card{outline:1px dashed rgba(255,255,255,.0)}
"""
