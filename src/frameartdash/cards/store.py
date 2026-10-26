"""The card layout, persisted in ``/data/cards.json``."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from frameartdash.cards.schema import COMMON, STYLE, TYPES, defaults, style_defaults


class LayoutError(ValueError):
    pass


def _clamp(value, lo: float, hi: float, default: float) -> float:
    try:
        return round(min(max(float(value), lo), hi), 2)
    except (TypeError, ValueError):
        return default


def _coerce(opt, value):
    if opt.kind == "bool":
        return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
    if opt.kind == "number":
        if value in ("", None):
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise LayoutError(f"{opt.label}: expected a number, got {value!r}") from None
        return int(number) if number == int(number) else number
    if opt.kind == "entities":
        if isinstance(value, str):
            value = [v.strip() for v in value.replace("\n", ",").split(",")]
        return [str(v).strip() for v in value or [] if str(v).strip()]
    if opt.kind == "select" and opt.options and str(value) not in opt.options:
        return opt.default
    return "" if value is None else str(value)


def normalize_card(raw: dict) -> dict:
    card_type = raw.get("type")
    if card_type not in TYPES:
        raise LayoutError(f"Unknown card type {card_type!r}")
    t = TYPES[card_type]
    options = defaults(card_type)
    given = raw.get("options") or {}
    for opt in (*t.options, *COMMON):
        if opt.key in given:
            options[opt.key] = _coerce(opt, given[opt.key])
    w = _clamp(raw.get("w"), 2, 100, t.size[0])
    h = _clamp(raw.get("h"), 2, 100, t.size[1])
    return {
        "id": str(raw.get("id") or secrets.token_hex(4))[:16],
        "type": card_type,
        "x": _clamp(raw.get("x"), 0, 100 - w, (100 - w) / 2),
        "y": _clamp(raw.get("y"), 0, 100 - h, (100 - h) / 2),
        "w": w,
        "h": h,
        "options": options,
    }


def normalize(raw: dict) -> dict:
    style = style_defaults()
    for opt in STYLE:
        if opt.key in (raw.get("style") or {}):
            style[opt.key] = _coerce(opt, raw["style"][opt.key])
    cards = [normalize_card(c) for c in raw.get("cards") or []]
    if len({c["id"] for c in cards}) != len(cards):
        raise LayoutError("Card ids must be unique")
    return {"version": 1, "style": style, "cards": cards}


class LayoutStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict:
        try:
            return normalize(json.loads(self.path.read_text()))
        except FileNotFoundError:
            return normalize({})
        except (json.JSONDecodeError, LayoutError):
            return normalize({})

    def save(self, raw: dict) -> dict:
        layout = normalize(raw)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(layout, indent=2, ensure_ascii=False))
        os.replace(tmp, self.path)
        return layout
