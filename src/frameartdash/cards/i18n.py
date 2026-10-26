"""Localized texts and value formatting for cards (German and English)."""

from __future__ import annotations

from datetime import date, datetime

TEXT = {
    "de": {
        "weekdays": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
        "weekdays_short": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
        "months": [
            "Januar",
            "Februar",
            "März",
            "April",
            "Mai",
            "Juni",
            "Juli",
            "August",
            "September",
            "Oktober",
            "November",
            "Dezember",
        ],
        "today": "Heute",
        "tomorrow": "Morgen",
        "yesterday": "Gestern",
        "all_day": "ganztägig",
        "in_days": "in {n} Tagen",
        "days_ago": "vor {n} Tagen",
        "no_events": "Keine Termine",
        "nothing_todo": "Alles erledigt",
        "unavailable": "nicht verfügbar",
        "nothing_playing": "Keine Wiedergabe",
        "sunrise": "Aufgang",
        "sunset": "Untergang",
        "home": "Zuhause",
        "away": "Unterwegs",
        "solar": "Solar",
        "grid": "Netz",
        "battery": "Batterie",
        "house": "Haus",
        "import": "Bezug",
        "export": "Einspeisung",
        "discharging": "Entlädt",
        "humidity": "Feuchte",
        "wind": "Wind",
        "now": "jetzt",
        "on": "An",
        "off": "Aus",
        "open": "Offen",
        "closed": "Geschlossen",
        "locked": "Verriegelt",
        "unlocked": "Entriegelt",
        "detected": "Erkannt",
        "clear": "Frei",
        "wet": "Nass",
        "dry": "Trocken",
        "low": "Niedrig",
        "normal": "Normal",
        "problem": "Problem",
        "ok": "OK",
        "charging": "Lädt",
        "not_charging": "Lädt nicht",
        "connected": "Verbunden",
        "disconnected": "Getrennt",
        "playing": "Wiedergabe",
        "paused": "Pausiert",
        "idle": "Bereit",
        "standby": "Standby",
        "heat": "Heizen",
        "cool": "Kühlen",
        "auto": "Auto",
        "heat_cool": "Heizen/Kühlen",
        "opening": "Öffnet",
        "closing": "Schließt",
        "armed_home": "Scharf (Zuhause)",
        "armed_away": "Scharf (Abwesend)",
        "armed_night": "Scharf (Nacht)",
        "disarmed": "Unscharf",
        "triggered": "Ausgelöst",
        "docked": "Angedockt",
        "cleaning": "Reinigt",
        "returning": "Kehrt zurück",
    },
    "en": {
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "weekdays_short": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "months": [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        "today": "Today",
        "tomorrow": "Tomorrow",
        "yesterday": "Yesterday",
        "all_day": "all day",
        "in_days": "in {n} days",
        "days_ago": "{n} days ago",
        "no_events": "No events",
        "nothing_todo": "All done",
        "unavailable": "unavailable",
        "nothing_playing": "Nothing playing",
        "sunrise": "Sunrise",
        "sunset": "Sunset",
        "home": "Home",
        "away": "Away",
        "solar": "Solar",
        "grid": "Grid",
        "battery": "Battery",
        "house": "Home",
        "import": "Import",
        "export": "Export",
        "discharging": "Discharging",
        "humidity": "Humidity",
        "wind": "Wind",
        "now": "now",
        "on": "On",
        "off": "Off",
        "open": "Open",
        "closed": "Closed",
        "locked": "Locked",
        "unlocked": "Unlocked",
        "detected": "Detected",
        "clear": "Clear",
        "wet": "Wet",
        "dry": "Dry",
        "low": "Low",
        "normal": "Normal",
        "problem": "Problem",
        "ok": "OK",
        "charging": "Charging",
        "not_charging": "Not charging",
        "connected": "Connected",
        "disconnected": "Disconnected",
        "playing": "Playing",
        "paused": "Paused",
        "idle": "Idle",
        "standby": "Standby",
        "heat": "Heat",
        "cool": "Cool",
        "auto": "Auto",
        "heat_cool": "Heat/Cool",
        "opening": "Opening",
        "closing": "Closing",
        "armed_home": "Armed home",
        "armed_away": "Armed away",
        "armed_night": "Armed night",
        "disarmed": "Disarmed",
        "triggered": "Triggered",
        "docked": "Docked",
        "cleaning": "Cleaning",
        "returning": "Returning",
    },
}

WEATHER = {
    "de": {
        "clear-night": "Klar",
        "cloudy": "Bewölkt",
        "exceptional": "Außergewöhnlich",
        "fog": "Nebel",
        "hail": "Hagel",
        "lightning": "Gewitter",
        "lightning-rainy": "Gewitter, Regen",
        "partlycloudy": "Teilweise bewölkt",
        "pouring": "Starkregen",
        "rainy": "Regnerisch",
        "snowy": "Schnee",
        "snowy-rainy": "Schneeregen",
        "sunny": "Sonnig",
        "windy": "Windig",
        "windy-variant": "Windig, bewölkt",
    },
    "en": {
        "clear-night": "Clear",
        "cloudy": "Cloudy",
        "exceptional": "Exceptional",
        "fog": "Fog",
        "hail": "Hail",
        "lightning": "Lightning",
        "lightning-rainy": "Thunderstorm",
        "partlycloudy": "Partly cloudy",
        "pouring": "Pouring",
        "rainy": "Rainy",
        "snowy": "Snowy",
        "snowy-rainy": "Sleet",
        "sunny": "Sunny",
        "windy": "Windy",
        "windy-variant": "Windy, cloudy",
    },
}

WEATHER_ICONS = {
    "clear-night": "weather-night",
    "cloudy": "weather-cloudy",
    "exceptional": "alert-circle-outline",
    "fog": "weather-fog",
    "hail": "weather-hail",
    "lightning": "weather-lightning",
    "lightning-rainy": "weather-lightning-rainy",
    "partlycloudy": "weather-partly-cloudy",
    "pouring": "weather-pouring",
    "rainy": "weather-rainy",
    "snowy": "weather-snowy",
    "snowy-rainy": "weather-snowy-rainy",
    "sunny": "weather-sunny",
    "windy": "weather-windy",
    "windy-variant": "weather-windy-variant",
}

# binary_sensor device classes: (text when on, text when off)
BINARY = {
    "door": ("open", "closed"),
    "garage_door": ("open", "closed"),
    "window": ("open", "closed"),
    "opening": ("open", "closed"),
    "lock": ("unlocked", "locked"),
    "motion": ("detected", "clear"),
    "occupancy": ("detected", "clear"),
    "presence": ("home", "away"),
    "moisture": ("wet", "dry"),
    "battery": ("low", "normal"),
    "problem": ("problem", "ok"),
    "safety": ("problem", "ok"),
    "smoke": ("detected", "clear"),
    "gas": ("detected", "clear"),
    "battery_charging": ("charging", "not_charging"),
    "connectivity": ("connected", "disconnected"),
    "plug": ("connected", "disconnected"),
}


class Locale:
    def __init__(self, lang: str) -> None:
        self.lang = lang if lang in TEXT else "en"
        self.t = TEXT[self.lang]
        self.decimal = "," if self.lang == "de" else "."
        self.group = "." if self.lang == "de" else ","

    def __getitem__(self, key: str) -> str:
        return self.t.get(key, key)

    # -- numbers -----------------------------------------------------------------

    def number(self, value: float, decimals: int | None = None) -> str:
        if decimals is None:
            a = abs(value)
            decimals = 0 if a >= 100 or value == int(value) else (1 if a >= 10 else (1 if a >= 1 else 2))
        text = f"{value:,.{decimals}f}"
        return text.replace(",", "\x00").replace(".", self.decimal).replace("\x00", self.group)

    def quantity(
        self, value: float, unit: str, decimals: int | None = None, scale: bool = True
    ) -> tuple[str, str]:
        """Formatted number and unit, with W→kW and Wh→kWh scaling for large values."""
        if scale and unit in ("W", "Wh") and abs(value) >= 1000:
            value, unit = value / 1000, "k" + unit
            if decimals is None:
                decimals = 1 if abs(value) < 100 else 0
        return self.number(value, decimals), unit

    # -- dates -------------------------------------------------------------------

    def time(self, dt: datetime, seconds: bool = False, h12: bool = False) -> str:
        if h12:
            return dt.strftime("%-I:%M:%S %p" if seconds else "%-I:%M %p")
        return dt.strftime("%H:%M:%S" if seconds else "%H:%M")

    def date(self, d: date, fmt: str = "long") -> str:
        wd = self.t["weekdays"][d.weekday()]
        month = self.t["months"][d.month - 1]
        if fmt == "short":
            return (
                f"{self.t['weekdays_short'][d.weekday()]}, {d.day}.{d.month}."
                if self.lang == "de"
                else f"{self.t['weekdays_short'][d.weekday()]}, {month[:3]} {d.day}"
            )
        if fmt == "weekday":
            return wd
        if fmt == "day":
            return f"{d.day}. {month}" if self.lang == "de" else f"{month} {d.day}"
        return f"{wd}, {d.day}. {month}" if self.lang == "de" else f"{wd}, {month} {d.day}"

    def relative_day(self, d: date, today: date) -> str:
        delta = (d - today).days
        if delta == 0:
            return self.t["today"]
        if delta == 1:
            return self.t["tomorrow"]
        if delta == -1:
            return self.t["yesterday"]
        if 1 < delta < 7:
            return self.t["weekdays"][d.weekday()]
        return self.date(d, "short")

    def in_days(self, n: int) -> str:
        if n == 0:
            return self.t["today"]
        if n == 1:
            return self.t["tomorrow"]
        if n > 1:
            return self.t["in_days"].format(n=n)
        return self.t["days_ago"].format(n=-n)

    def weather(self, condition: str) -> str:
        return WEATHER.get(self.lang, WEATHER["en"]).get(condition, condition)
