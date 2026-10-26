"""Card types and their options. The web editor builds its forms from this."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Opt:
    key: str
    label: str
    kind: str = "text"  # text | textarea | number | bool | select | entity | entities | color | icon
    default: object = ""
    options: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()  # entity picker filter
    help: str = ""


@dataclass(frozen=True)
class CardType:
    type: str
    label: str
    icon: str
    group: str
    size: tuple[float, float]  # default width, height in % of the canvas
    options: tuple[Opt, ...] = field(default_factory=tuple)
    description: str = ""


NUMERIC = ("sensor", "input_number", "number", "counter")
DECIMALS = Opt("decimals", "Decimals", "number", "", help="Empty: automatic")

CARD_TYPES: tuple[CardType, ...] = (
    CardType(
        "clock",
        "Clock",
        "clock-outline",
        "Time",
        (22, 16),
        (
            Opt("format", "Format", "select", "24h", ("24h", "12h")),
            Opt("show_date", "Show date", "bool", True),
            Opt("date_format", "Date format", "select", "long", ("long", "short", "weekday", "day")),
        ),
        "Current time, optionally with the date",
    ),
    CardType(
        "date",
        "Date",
        "calendar-today",
        "Time",
        (24, 8),
        (Opt("format", "Format", "select", "long", ("long", "short", "weekday", "day")),),
    ),
    CardType(
        "countdown",
        "Countdown",
        "timer-sand",
        "Time",
        (18, 12),
        (
            Opt("title", "Title", "text", "Urlaub"),
            Opt(
                "entity",
                "Date entity",
                "entity",
                domains=("input_datetime", "sensor", "calendar"),
                help="input_datetime, date/timestamp sensor or calendar (next event)",
            ),
            Opt("date", "…or a fixed date", "text", "", help="YYYY-MM-DD"),
            Opt("icon", "Icon", "icon", "calendar-star"),
        ),
        "Days until a date",
    ),
    CardType(
        "text",
        "Text",
        "format-text",
        "Basics",
        (30, 8),
        (
            Opt(
                "text",
                "Text",
                "textarea",
                "Willkommen zuhause",
                help="Insert live values with {sensor.entity_id}",
            ),
            Opt("font", "Font", "select", "inherit", ("inherit", "sans", "serif", "mono")),
            Opt("weight", "Weight", "select", "400", ("300", "400", "500", "600", "700")),
        ),
        "Heading or free text with live values",
    ),
    CardType(
        "value",
        "Value",
        "numeric",
        "Basics",
        (16, 13),
        (
            Opt("entity", "Entity", "entity"),
            Opt("name", "Name", "text", "", help="Empty: entity name"),
            Opt("icon", "Icon", "icon", "", help="Empty: entity icon"),
            Opt("attribute", "Attribute", "text", "", help="Show an attribute instead of the state"),
            DECIMALS,
            Opt("show_icon", "Show icon", "bool", True),
            Opt("sparkline", "Sparkline", "bool", False),
            Opt("hours", "Sparkline hours", "number", 24),
        ),
        "One value with icon and name, optional trend line",
    ),
    CardType(
        "big",
        "Big number",
        "format-size",
        "Basics",
        (22, 18),
        (
            Opt("entity", "Entity", "entity"),
            Opt("name", "Label", "text", ""),
            DECIMALS,
            Opt("show_unit", "Show unit", "bool", True),
        ),
        "A single value, as large as possible",
    ),
    CardType(
        "status",
        "Status",
        "toggle-switch-outline",
        "Basics",
        (18, 9),
        (
            Opt("entity", "Entity", "entity"),
            Opt("name", "Name", "text", ""),
            Opt("icon", "Icon", "icon", ""),
            Opt("on_text", "Text when on", "text", ""),
            Opt("off_text", "Text when off", "text", ""),
        ),
        "On/off, open/closed and other states with a highlight when active",
    ),
    CardType(
        "entities",
        "Entity list",
        "format-list-bulleted",
        "Basics",
        (22, 26),
        (
            Opt("title", "Title", "text", ""),
            Opt("entities", "Entities", "entities"),
            Opt("show_icons", "Show icons", "bool", True),
            DECIMALS,
        ),
        "Several values in rows",
    ),
    CardType(
        "bar",
        "Bar",
        "poll",
        "Charts",
        (22, 9),
        (
            Opt("entity", "Entity", "entity", domains=NUMERIC),
            Opt("name", "Name", "text", ""),
            Opt("min", "Minimum", "number", 0),
            Opt("max", "Maximum", "number", 100),
            DECIMALS,
            Opt("color", "Color", "color", ""),
        ),
        "Progress bar, e.g. battery or tank level",
    ),
    CardType(
        "gauge",
        "Gauge",
        "gauge",
        "Charts",
        (15, 20),
        (
            Opt("entity", "Entity", "entity", domains=NUMERIC),
            Opt("name", "Name", "text", ""),
            Opt("min", "Minimum", "number", 0),
            Opt("max", "Maximum", "number", 100),
            DECIMALS,
            Opt("color", "Color", "color", ""),
        ),
    ),
    CardType(
        "graph",
        "Graph",
        "chart-line",
        "Charts",
        (34, 24),
        (
            Opt("title", "Title", "text", ""),
            Opt("entities", "Entities", "entities", domains=NUMERIC),
            Opt("hours", "Hours", "number", 24),
            Opt("fill", "Fill area", "bool", True),
            Opt("show_legend", "Legend", "bool", True),
            DECIMALS,
        ),
        "History of one or more sensors",
    ),
    CardType(
        "weather",
        "Weather",
        "weather-partly-cloudy",
        "Home",
        (30, 26),
        (
            Opt("entity", "Weather entity", "entity", domains=("weather",)),
            Opt("name", "Name", "text", ""),
            Opt("forecast_days", "Forecast days", "number", 5),
            Opt("show_details", "Humidity and wind", "bool", True),
        ),
        "Current weather and daily forecast",
    ),
    CardType(
        "energy",
        "Energy flow",
        "transmission-tower",
        "Home",
        (30, 30),
        (
            Opt("solar", "Solar power", "entity", domains=NUMERIC),
            Opt("grid", "Grid power", "entity", domains=NUMERIC, help="Positive = import"),
            Opt("battery", "Battery power", "entity", domains=NUMERIC, help="Positive = discharging"),
            Opt("battery_soc", "Battery level", "entity", domains=NUMERIC),
            Opt("home", "Home consumption", "entity", domains=NUMERIC),
            Opt("invert_grid", "Invert grid sign", "bool", False),
            Opt("invert_battery", "Invert battery sign", "bool", False),
        ),
        "Solar, grid, battery and home at a glance",
    ),
    CardType(
        "calendar",
        "Calendar",
        "calendar-month-outline",
        "Home",
        (26, 30),
        (
            Opt("title", "Title", "text", ""),
            Opt("entities", "Calendars", "entities", domains=("calendar",)),
            Opt("days", "Days ahead", "number", 7),
            Opt("max_events", "Max events", "number", 6),
        ),
        "Upcoming events",
    ),
    CardType(
        "todo",
        "To-do list",
        "format-list-checks",
        "Home",
        (20, 26),
        (
            Opt("entity", "List", "entity", domains=("todo",)),
            Opt("title", "Title", "text", ""),
            Opt("max_items", "Max items", "number", 8),
        ),
    ),
    CardType(
        "persons",
        "People",
        "account-group-outline",
        "Home",
        (24, 12),
        (
            Opt("entities", "People", "entities", domains=("person", "device_tracker")),
            Opt("show_names", "Show names", "bool", True),
            Opt("show_state", "Show state", "bool", True),
        ),
        "Who is at home",
    ),
    CardType(
        "media",
        "Now playing",
        "music-circle-outline",
        "Home",
        (28, 14),
        (
            Opt("entity", "Media player", "entity", domains=("media_player",)),
            Opt("show_cover", "Show cover", "bool", True),
            Opt("hide_idle", "Hide when nothing plays", "bool", True),
        ),
    ),
    CardType(
        "camera",
        "Camera",
        "cctv",
        "Home",
        (32, 24),
        (
            Opt("entity", "Camera", "entity", domains=("camera",)),
            Opt("show_name", "Show name", "bool", True),
            Opt("fit", "Fit", "select", "cover", ("cover", "contain")),
        ),
        "Snapshot at render time",
    ),
    CardType(
        "sun",
        "Sun",
        "weather-sunset",
        "Home",
        (22, 14),
        (
            Opt("entity", "Sun entity", "entity", "sun.sun", domains=("sun",)),
            Opt("show_arc", "Daylight arc", "bool", True),
        ),
        "Sunrise, sunset and the sun's position",
    ),
)

TYPES = {t.type: t for t in CARD_TYPES}

COMMON: tuple[Opt, ...] = (
    Opt("style", "Card style", "select", "inherit", ("inherit", "glass", "solid", "outline", "none")),
    Opt("align", "Alignment", "select", "left", ("left", "center", "right")),
    Opt("scale", "Text size (%)", "number", 100),
    Opt("show_if_entity", "Only show if entity…", "entity"),
    Opt("show_if_state", "…has state", "text", "", help="Comma-separated; prefix with ! to negate"),
)

STYLE: tuple[Opt, ...] = (
    Opt("card_style", "Default card style", "select", "glass", ("glass", "solid", "outline", "none")),
    Opt("font", "Font", "select", "sans", ("sans", "serif", "mono")),
    Opt("text_color", "Text color", "color", "#f4f1ea"),
    Opt("accent", "Accent color", "color", "#e3c27a"),
    Opt("tint", "Glass tint", "select", "dark", ("dark", "light")),
    Opt("opacity", "Glass opacity (%)", "number", 38),
    Opt("blur", "Glass blur (px)", "number", 18),
    Opt("radius", "Corner radius (px)", "number", 22),
    Opt("shadow", "Shadow", "bool", True),
    Opt("dim", "Darken background (%)", "number", 0),
)


def defaults(card_type: str) -> dict:
    t = TYPES[card_type]
    return {o.key: o.default for o in (*t.options, *COMMON)}


def style_defaults() -> dict:
    return {o.key: o.default for o in STYLE}


def schema_json() -> dict:
    return {
        "types": [asdict(t) for t in CARD_TYPES],
        "common": [asdict(o) for o in COMMON],
        "style": [asdict(o) for o in STYLE],
    }
