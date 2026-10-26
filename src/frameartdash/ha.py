"""Minimal async client for the Home Assistant REST API."""

from __future__ import annotations

import base64
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import aiohttp

log = logging.getLogger(__name__)


class HAError(RuntimeError):
    pass


class HAClient:
    def __init__(self, base_url: str, token: str, timeout: float = 20) -> None:
        if not base_url or not token:
            raise HAError("Home Assistant URL and token are required")
        self.base = base_url.rstrip("/")
        self.token = token
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> HAClient:
        self._session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.token}"}, timeout=self.timeout
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._session:
            await self._session.close()

    async def _get(self, path: str, **params):
        assert self._session
        try:
            async with self._session.get(self.base + path, params=params or None) as resp:
                if resp.status == 401:
                    raise HAError("Home Assistant rejected the token (401)")
                if resp.status >= 400:
                    raise HAError(f"Home Assistant returned HTTP {resp.status} for {path}")
                return await resp.json()
        except aiohttp.ClientError as e:
            raise HAError(f"Home Assistant not reachable: {e}") from e

    async def config(self) -> dict:
        return await self._get("/api/config")

    async def states(self) -> dict[str, dict]:
        return {s["entity_id"]: s for s in await self._get("/api/states")}

    async def history(self, entity_ids: list[str], hours: float) -> dict[str, list[tuple[datetime, float]]]:
        """Numeric history per entity, oldest first. Non-numeric states are skipped."""
        if not entity_ids:
            return {}
        start = datetime.now(UTC) - timedelta(hours=hours)
        raw = await self._get(
            "/api/history/period/" + quote(start.isoformat()),
            filter_entity_id=",".join(entity_ids),
            minimal_response="",
            no_attributes="",
        )
        result: dict[str, list[tuple[datetime, float]]] = {}
        for series in raw:
            if not series:
                continue
            eid = series[0].get("entity_id")
            points = []
            for item in series:
                try:
                    value = float(item["state"])
                    when = datetime.fromisoformat(item.get("last_changed") or item["last_updated"])
                except (KeyError, TypeError, ValueError):
                    continue
                points.append((when, value))
            if eid:
                result[eid] = points
        return result

    async def service(self, domain: str, service: str, data: dict) -> dict:
        """Call a service that returns data (``?return_response``)."""
        assert self._session
        url = f"{self.base}/api/services/{domain}/{service}?return_response"
        try:
            async with self._session.post(url, json=data) as resp:
                if resp.status >= 400:
                    raise HAError(f"{domain}.{service} failed with HTTP {resp.status}")
                body = await resp.json()
        except aiohttp.ClientError as e:
            raise HAError(f"Home Assistant not reachable: {e}") from e
        return body.get("service_response", {}) if isinstance(body, dict) else {}

    async def calendar(self, entity_id: str, start: datetime, end: datetime) -> list[dict]:
        return await self._get(f"/api/calendars/{entity_id}", start=start.isoformat(), end=end.isoformat())

    async def image(self, path: str) -> str | None:
        """Fetch an image (entity_picture, camera proxy) as a data URI."""
        assert self._session
        url = path if path.startswith("http") else self.base + path
        try:
            async with self._session.get(url) as resp:
                if resp.status >= 400:
                    return None
                ctype = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
                data = await resp.read()
        except (aiohttp.ClientError, TimeoutError) as e:
            log.debug("Image %s failed: %s", path, e)
            return None
        if not ctype.startswith("image/") or len(data) > 8 * 1024 * 1024:
            return None
        return f"data:{ctype};base64,{base64.b64encode(data).decode()}"


# -- time zone ------------------------------------------------------------------

_config_cache: dict[str, tuple[float, dict]] = {}


async def ha_config(base_url: str, token: str) -> dict | None:
    """Home Assistant's /api/config, cached for an hour. None if unavailable."""
    key = base_url + token[-8:]
    cached = _config_cache.get(key)
    if cached and time.monotonic() - cached[0] < 3600:
        return cached[1]
    try:
        async with HAClient(base_url, token, timeout=8) as ha:
            config = await ha.config()
    except HAError as e:
        log.debug("Could not read HA config: %s", e)
        return None
    _config_cache[key] = (time.monotonic(), config)
    return config


def local_timezone() -> str | None:
    """IANA name of the container/host time zone, if it can be determined."""
    if tz := os.environ.get("TZ", "").strip().lstrip(":"):
        return tz
    try:
        if tz := Path("/etc/timezone").read_text().strip():
            return tz
    except OSError:
        pass
    try:
        target = os.readlink("/etc/localtime")
        if "zoneinfo/" in target:
            return target.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return None


async def resolve(settings) -> tuple[str | None, str]:
    """(time zone, language) for rendering: settings → Home Assistant → container."""
    tz = settings.time_zone or None
    lang = settings.ha_language or ""
    if (not tz or not lang) and settings.ha_url and settings.ha_token:
        config = await ha_config(settings.ha_url, settings.ha_token) or {}
        tz = tz or config.get("time_zone")
        lang = lang or config.get("language", "")
    return tz or local_timezone(), (lang or "en").split("-")[0].lower()
