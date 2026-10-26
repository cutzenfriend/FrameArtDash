"""Assemble the card page: Home Assistant data, background and layout."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from frameartdash.cards.data import collect
from frameartdash.cards.html import build_page
from frameartdash.config import Settings
from frameartdash.ha import HAClient, resolve


def background_css(settings: Settings, inline: bool) -> str:
    if settings.style == "image" and settings.bg_image:
        path = Path(settings.bg_image)
        if not inline and path.parent == settings.backgrounds_dir:
            return f"url('/api/backgrounds/{path.name}')"
        try:
            data = path.read_bytes()
        except OSError:
            pass
        else:
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            return f"url('data:{mime};base64,{base64.b64encode(data).decode()}')"
    top, bottom = settings.bg_gradient
    return f"linear-gradient(170deg, {top}, {bottom})"


async def build(
    settings: Settings, layout: dict, inline: bool, edit: bool = False, client=HAClient
) -> tuple[str, str | None]:
    """Returns (html, time zone)."""
    tz, lang = await resolve(settings)
    async with client(settings.ha_url, settings.ha_token) as ha:
        data = await collect(ha, layout, tz, lang)
    return build_page(layout, data, background_css(settings, inline), inline, edit), tz
