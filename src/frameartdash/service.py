"""One render → compose → push → cleanup cycle, plus the scheduling loop."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from frameartdash import compose, frame as frame_mod, render as render_mod
from frameartdash.config import Settings, in_window
from frameartdash.state import State, StateStore

log = logging.getLogger(__name__)

Renderer = Callable[[Settings], Awaitable[bytes]]
FrameFactory = Callable[[Settings], Any]  # returns an async context manager yielding a Frame


@dataclass
class CycleResult:
    status: str  # uploaded | unchanged | skipped | rendered | error
    reason: str = ""
    content_id: str | None = None
    distance: int | None = None
    deleted: list[str] = field(default_factory=list)
    finished: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))

    def as_dict(self) -> dict:
        return asdict(self)


async def retry(op: Callable[[], Awaitable[Any]], attempts: int, what: str, base_delay: float = 2.0) -> Any:
    for attempt in range(1, attempts + 1):
        try:
            return await op()
        except Exception as e:
            if attempt == attempts:
                raise
            delay = base_delay * 2 ** (attempt - 1)
            log.warning("%s failed (%s), retry %d/%d in %.0fs", what, e, attempt, attempts - 1, delay)
            await asyncio.sleep(delay)


class Service:
    def __init__(
        self,
        settings: Settings,
        renderer: Renderer = render_mod.render,
        frame_factory: FrameFactory = frame_mod.connect,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.settings = settings
        self.renderer = renderer
        self.frame_factory = frame_factory
        self.clock = clock
        self.store = StateStore(settings.state_file)
        self.lock = asyncio.Lock()
        self.last_result: CycleResult | None = None
        self.last_success: str | None = None
        self.last_jpeg: bytes | None = None

    # -- cycle ---------------------------------------------------------------

    async def run_cycle(self, force: bool = False, upload: bool = True) -> CycleResult:
        """Run one cycle. ``force`` ignores the active hours and the diff check."""
        async with self.lock:
            try:
                result = await self._cycle(force=force, upload=upload)
            except Exception as e:
                log.error("Cycle failed: %s", e, exc_info=log.isEnabledFor(logging.DEBUG))
                result = CycleResult("error", reason=str(e) or type(e).__name__)
            self.last_result = result
            if result.status in ("uploaded", "unchanged", "rendered"):
                self.last_success = result.finished
            if result.status != "error":
                log.info("Cycle %s%s", result.status, f": {result.reason}" if result.reason else "")
            return result

    async def _cycle(self, force: bool, upload: bool) -> CycleResult:
        s = self.settings
        if upload and not force and not in_window(s.active_hours, self.clock().time()):
            return CycleResult("skipped", reason="outside ACTIVE_HOURS")

        state = self.store.load()

        if not upload:
            await self._render_and_compose(state, force=True)
            return CycleResult("rendered")

        try:
            return await self._push(state, force)
        except frame_mod.FrameUnreachable as e:
            return CycleResult("skipped", reason=str(e))

    async def _push(self, state: State, force: bool) -> CycleResult:
        s = self.settings
        async with self.frame_factory(s) as frame:
            power = await frame.power_state()
            if power not in frame_mod.POWER_ON_STATES:
                return CycleResult("skipped", reason=f"TV is {power}")
            if s.only_in_artmode and power != "art":
                return CycleResult("skipped", reason=f"TV is not in art mode ({power})")

            jpeg, new_hash, distance = await self._render_and_compose(state, force=force)
            if jpeg is None:
                return CycleResult("unchanged", reason=f"hash distance {distance}", distance=distance)

            content_id = await retry(lambda: frame.upload(jpeg), s.retries, "Upload")
            log.info("Uploaded %s (%d KiB)", content_id, len(jpeg) // 1024)
            # Track it right away so a failing select does not leave an orphan behind.
            state.add(content_id)
            self.store.save(state)

            await retry(lambda: frame.select(content_id), s.retries, "Select")
            state.current_id = content_id
            state.last_hash = new_hash
            state.last_upload = self.clock().astimezone().isoformat(timespec="seconds")
            self.store.save(state)

            deleted = await self._delete_stale(frame, state)
            return CycleResult("uploaded", content_id=content_id, distance=distance, deleted=deleted)

    async def _render_and_compose(self, state: State, force: bool) -> tuple[bytes | None, str, int | None]:
        s = self.settings
        png = await retry(lambda: self.renderer(s), s.retries, "Render")
        shot = compose.load(png)
        new_hash = compose.image_hash(shot)
        distance = compose.hash_distance(state.last_hash, new_hash)
        if not force and s.diff_threshold > 0 and distance is not None and distance < s.diff_threshold:
            return None, new_hash, distance

        image = await asyncio.to_thread(compose.compose, shot, s)
        jpeg = await asyncio.to_thread(compose.to_jpeg, image, s.jpeg_quality)
        self.last_jpeg = jpeg
        if s.debug_images:
            self._save_debug(png, jpeg)
        return jpeg, new_hash, distance

    def _save_debug(self, png: bytes, jpeg: bytes) -> None:
        try:
            self.settings.debug_dir.mkdir(parents=True, exist_ok=True)
            (self.settings.debug_dir / "screenshot.png").write_bytes(png)
            (self.settings.debug_dir / "frame.jpg").write_bytes(jpeg)
        except OSError as e:
            log.warning("Could not write debug images: %s", e)

    # -- cleanup -------------------------------------------------------------

    async def _delete_stale(self, frame, state: State) -> list[str]:
        """Delete every managed image except the selected one. Never raises."""
        stale = state.stale_ids()
        if self.settings.cleanup_unmanaged:
            try:
                for cid in await frame.my_photos():
                    if cid != state.current_id and cid not in stale:
                        stale.append(cid)
            except Exception as e:
                log.warning("Listing My Photos failed: %s", e)
        if not stale:
            return []
        try:
            await frame.delete(stale)
        except Exception as e:
            log.warning("Deleting %s failed, will retry next cycle: %s", ", ".join(stale), e)
            return []
        state.forget(stale)
        self.store.save(state)
        log.info("Deleted %s", ", ".join(stale))
        return stale

    async def cleanup(self) -> list[str]:
        """Remove orphaned images left over from earlier runs."""
        async with self.lock:
            state = self.store.load()
            if not state.stale_ids() and not self.settings.cleanup_unmanaged:
                return []
            async with self.frame_factory(self.settings) as frame:
                if (await frame.power_state()) not in frame_mod.POWER_ON_STATES:
                    log.info("TV is not on, skipping startup cleanup")
                    return []
                return await self._delete_stale(frame, state)

    # -- loop ----------------------------------------------------------------

    async def run_forever(self) -> None:
        try:
            await self.cleanup()
        except frame_mod.FrameUnreachable as e:
            log.info("Startup cleanup skipped: %s", e)
        except Exception as e:
            log.warning("Startup cleanup failed: %s", e)
        while True:
            await self.run_cycle()
            await asyncio.sleep(self.settings.interval_min * 60)
