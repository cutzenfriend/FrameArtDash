"""Thin async wrapper around the Samsung Frame art API (samsungframetv)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from samsungframetv.async_art import SamsungTVAsyncArt
from samsungframetv.exceptions import ConnectionFailure, UnauthorizedError

from frameartdash.config import Settings

log = logging.getLogger(__name__)

# Category of user uploaded pictures ("My Photos"); their content IDs start with MY_.
MY_PHOTOS = "MY-C0002"

# Power states reported by samsungframetv.get_power_state().
POWER_ON_STATES = ("on", "tv", "art")


class FrameError(RuntimeError):
    pass


class FrameUnreachable(FrameError):
    """The TV did not answer, typically because it is switched off."""


class Frame:
    def __init__(self, settings: Settings) -> None:
        if not settings.frame_host:
            raise FrameError("FRAME_HOST is not set")
        self.settings = settings
        self._tv: SamsungTVAsyncArt | None = None

    async def open(self) -> None:
        self.settings.token_file.parent.mkdir(parents=True, exist_ok=True)
        # The constructor checks the token synchronously, keep it off the event loop.
        self._tv = await asyncio.to_thread(
            SamsungTVAsyncArt,
            host=self.settings.frame_host,
            port=self.settings.frame_port,
            token_file=str(self.settings.token_file),
            timeout=10,
            name="FrameArtDash",
        )
        await self._tv.start_listening()

    async def close(self) -> None:
        if self._tv is not None:
            try:
                await self._tv.close()
            except Exception as e:  # noqa: BLE001 - closing must never raise
                log.debug("Error closing Frame connection: %s", e)
            self._tv = None

    @property
    def tv(self) -> SamsungTVAsyncArt:
        if self._tv is None:
            raise FrameError("Frame connection is not open")
        return self._tv

    async def power_state(self) -> str:
        """One of 'off', 'standby', 'tv', 'art' or 'on'."""
        return await self.tv.get_power_state()

    async def upload(self, jpeg: bytes) -> str:
        content_id = await self.tv.upload(
            jpeg,
            file_type="JPEG",
            matte=self.settings.matte,
            portrait_matte=self.settings.matte,
            timeout=self.settings.upload_timeout,
        )
        if not content_id:
            raise FrameError("upload finished without a content id")
        return content_id

    async def select(self, content_id: str) -> None:
        await self.tv.select_image(content_id, show=False)

    async def delete(self, content_ids: list[str]) -> None:
        if content_ids:
            await self.tv.delete_list(content_ids)

    async def my_photos(self) -> list[str]:
        items = await self.tv.available(MY_PHOTOS)
        return [item["content_id"] for item in items if item.get("content_id", "").startswith("MY_")]

    async def current(self) -> str | None:
        data = await self.tv.get_current()
        return data.get("content_id")


@asynccontextmanager
async def connect(settings: Settings):
    frame = Frame(settings)
    try:
        try:
            await frame.open()
        except UnauthorizedError:
            raise
        except (OSError, TimeoutError, ConnectionFailure) as e:
            raise FrameUnreachable(f"{settings.frame_host} not reachable ({e})") from e
        yield frame
    finally:
        await frame.close()


async def pair(settings: Settings, force: bool = False) -> bool:
    """Request a token; the user has to press Allow on the TV."""
    settings.token_file.parent.mkdir(parents=True, exist_ok=True)
    tv = await asyncio.to_thread(
        SamsungTVAsyncArt,
        host=settings.frame_host,
        port=settings.frame_port,
        token_file=str(settings.token_file),
        name="FrameArtDash",
    )
    try:
        token = await tv.pair(force=force)
    finally:
        await tv.close()
    return bool(token)
