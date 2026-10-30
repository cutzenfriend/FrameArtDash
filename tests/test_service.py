import io
from contextlib import asynccontextmanager
from datetime import datetime

from PIL import Image, ImageDraw

from frameartdash.config import Settings
from frameartdash.service import Service


def _png(text: str) -> bytes:
    image = Image.new("RGB", (480, 270), (20, 20, 20))
    ImageDraw.Draw(image).text((40, 60), text, fill=(255, 255, 255), font_size=120)
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


class FakeFrame:
    def __init__(self, power="art"):
        self.power = power
        self.images: list[str] = ["MY_F0001"]  # someone else's upload
        self.selected: str | None = None
        self.calls: list[str] = []
        self.fail_select = False
        self._n = 100

    async def power_state(self):
        return self.power

    async def upload(self, jpeg):
        self._n += 1
        cid = f"MY_F{self._n:04d}"
        self.images.append(cid)
        self.calls.append(f"upload {cid}")
        return cid

    async def select(self, cid):
        if self.fail_select:
            raise RuntimeError("select failed")
        assert cid in self.images
        self.selected = cid
        self.calls.append(f"select {cid}")

    async def delete(self, cids):
        assert self.selected not in cids, "must never delete the selected image"
        self.images = [c for c in self.images if c not in cids]
        self.calls.append(f"delete {','.join(cids)}")

    async def my_photos(self):
        return list(self.images)


def _service(tmp_path, fake, texts, hour=12, **env):
    settings = Settings.from_env(
        {"TARGET_URL": "http://x", "FRAME_HOST": "tv", "DATA_DIR": str(tmp_path), "RETRIES": "1", **env}
    )
    shots = iter(texts)

    async def renderer(_settings):
        return _png(next(shots))

    @asynccontextmanager
    async def factory(_settings):
        yield fake

    return Service(
        settings, renderer=renderer, frame_factory=factory, clock=lambda: datetime(2026, 1, 1, hour)
    )


async def test_upload_select_then_delete_previous(tmp_path):
    fake = FakeFrame()
    svc = _service(tmp_path, fake, ["11.1", "99.9"])

    first = await svc.run_cycle()
    assert first.status == "uploaded"
    second = await svc.run_cycle()
    assert second.status == "uploaded"
    assert second.deleted == [first.content_id]

    assert fake.calls == [
        f"upload {first.content_id}",
        f"select {first.content_id}",
        f"upload {second.content_id}",
        f"select {second.content_id}",
        f"delete {first.content_id}",
    ]
    assert "MY_F0001" in fake.images  # unmanaged images stay
    state = svc.store.load()
    assert state.current_id == second.content_id
    assert state.managed_ids == [second.content_id]


async def test_unchanged_skips_upload(tmp_path):
    fake = FakeFrame()
    svc = _service(tmp_path, fake, ["11.1", "11.1", "11.1"])
    assert (await svc.run_cycle()).status == "uploaded"
    assert (await svc.run_cycle()).status == "unchanged"
    assert (await svc.run_cycle(force=True)).status == "uploaded"


async def test_skips_when_tv_off_or_outside_hours(tmp_path):
    assert (await _service(tmp_path, FakeFrame("off"), ["a"]).run_cycle()).status == "skipped"
    assert (await _service(tmp_path, FakeFrame(), ["a"], hour=3).run_cycle()).status == "skipped"
    only_art = _service(tmp_path, FakeFrame("tv"), ["a"], ONLY_IN_ARTMODE="true")
    assert (await only_art.run_cycle()).status == "skipped"


async def test_failed_select_keeps_previous_and_cleans_up_later(tmp_path):
    fake = FakeFrame()
    svc = _service(tmp_path, fake, ["11.1", "55.5", "99.9"])
    first = await svc.run_cycle()

    fake.fail_select = True
    failed = await svc.run_cycle()
    assert failed.status == "error"
    assert fake.selected == first.content_id
    state = svc.store.load()
    assert state.current_id == first.content_id
    orphan = state.stale_ids()
    assert len(orphan) == 1

    fake.fail_select = False
    third = await svc.run_cycle()
    assert sorted(third.deleted) == sorted([first.content_id, *orphan])


async def test_cleanup_unmanaged(tmp_path):
    fake = FakeFrame()
    svc = _service(tmp_path, fake, ["11.1"], CLEANUP_UNMANAGED="true")
    result = await svc.run_cycle()
    assert result.deleted == ["MY_F0001"]
    assert fake.images == [result.content_id]


async def test_unreachable_tv_is_skipped(tmp_path):
    from frameartdash.frame import FrameUnreachable

    svc = _service(tmp_path, FakeFrame(), ["a"])

    @asynccontextmanager
    async def unreachable(_settings):
        raise FrameUnreachable("tv not reachable")
        yield

    svc.frame_factory = unreachable
    result = await svc.run_cycle()
    assert result.status == "skipped"
    assert "not reachable" in result.reason


async def test_history_keeps_current_plus_three(tmp_path):
    fake = FakeFrame()
    texts = ["11.1", "22.2", "33.3", "44.4", "55.5"]
    svc = _service(tmp_path, fake, texts)
    for i in range(len(texts)):
        svc.clock = lambda i=i: datetime(2026, 1, 1, 12, i)
        assert (await svc.run_cycle()).status == "uploaded"
    entries = svc.history.entries()
    assert len(entries) == 4
    assert entries[0]["content_id"] == fake.selected
    assert svc.history.preview_info()["content_id"] == fake.selected
    assert len(list((tmp_path / "history").glob("2026*.jpg"))) == 4
    assert (tmp_path / "history" / "current.jpg").exists()


async def test_not_configured_is_skipped(tmp_path):
    svc = _service(tmp_path, FakeFrame(), ["a"])
    svc.apply_settings(Settings.from_env({"DATA_DIR": str(tmp_path)}))
    result = await svc.run_cycle()
    assert result.status == "skipped" and "URL" in result.reason


async def test_preview_rendered_when_tv_off_after_settings_change(tmp_path):
    fake = FakeFrame("off")
    svc = _service(tmp_path, fake, ["11.1", "22.2", "33.3"])
    # First start without a preview renders one even though the TV is off.
    first = await svc.run_cycle()
    assert first.status == "skipped" and "preview rendered" in first.reason
    assert svc.history.preview_info() is not None
    assert (tmp_path / "history" / "preview.jpg").exists()
    assert (tmp_path / "history" / "preview-raw.png").exists()
    # Later cycles with the TV off do not render again...
    second = await svc.run_cycle()
    assert "preview" not in second.reason
    # ...until the settings change.
    svc.apply_settings(svc.settings)
    third = await svc.run_cycle()
    assert "preview rendered" in third.reason
    assert fake.calls == []


async def test_dry_run_never_contacts_tv(tmp_path):
    svc = _service(tmp_path, FakeFrame(), ["11.1"], DRY_RUN="true")

    @asynccontextmanager
    async def boom(_settings):
        raise AssertionError("TV must not be contacted in test mode")
        yield

    svc.frame_factory = boom
    result = await svc.run_cycle()
    assert result.status == "rendered" and "test mode" in result.reason
    assert svc.history.preview_info()["seconds"] >= 0


async def test_cards_layout_uses_card_renderer(tmp_path):
    settings = Settings.from_env(
        {
            "LAYOUT": "cards",
            "HA_URL": "http://ha",
            "HA_TOKEN": "t",
            "FRAME_HOST": "tv",
            "DATA_DIR": str(tmp_path),
            "RETRIES": "1",
        }
    )
    calls = []

    async def card_renderer(s, layout):
        calls.append(layout)
        return _png("cards")

    async def renderer(s):
        raise AssertionError("dashboard renderer must not be used")

    @asynccontextmanager
    async def factory(_settings):
        yield FakeFrame()

    svc = Service(
        settings,
        renderer=renderer,
        frame_factory=factory,
        card_renderer=card_renderer,
        clock=lambda: datetime(2026, 1, 1, 12),
    )
    result = await svc.run_cycle()
    assert result.status == "uploaded"
    assert calls and calls[0]["cards"] == []
    assert svc.history.entries()


def test_cards_mode_needs_ha_credentials():
    s = Settings.from_env({"LAYOUT": "cards"})
    assert not s.configured and "Home Assistant" in s.not_configured_reason


async def test_transfer_socket_uses_tv_host_for_unspecified_ip(monkeypatch):
    from samsungframetv.async_art import SamsungTVAsyncArt

    from frameartdash.frame import _FrameArt

    seen = []

    async def fake_open(self, conn_info, secured=None):
        seen.append(conn_info["ip"])

    monkeypatch.setattr(SamsungTVAsyncArt, "_open_d2d_connection", fake_open)
    art = _FrameArt.__new__(_FrameArt)
    art.host = "192.168.1.66"
    await art._open_d2d_connection({"ip": "0.0.0.0", "port": "56603"})
    await art._open_d2d_connection({"ip": "192.168.1.66", "port": "1"})
    await art._open_d2d_connection({"ip": "10.0.0.9", "port": "1"})
    assert seen == ["192.168.1.66", "192.168.1.66", "10.0.0.9"]
