"""Uploaded background images for ``STYLE=image``."""

from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 7680 * 4320
THUMB = (320, 180)
_SAFE = re.compile(r"[^a-z0-9_-]+")


class BackgroundError(ValueError):
    pass


class Backgrounds:
    def __init__(self, directory: Path) -> None:
        self.dir = directory

    def list(self) -> list[str]:
        if not self.dir.is_dir():
            return []
        return sorted(p.name for p in self.dir.glob("*.jpg") if not p.name.endswith(".thumb.jpg"))

    def _name(self, filename: str) -> str:
        stem = _SAFE.sub("-", Path(filename).stem.lower()).strip("-") or "background"
        name, n = f"{stem[:40]}.jpg", 2
        while (self.dir / name).exists():
            name, n = f"{stem[:40]}-{n}.jpg", n + 1
        return name

    def add(self, filename: str, data: bytes) -> str:
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.width * img.height > MAX_PIXELS:
                    raise BackgroundError("Image is larger than 8K")
                img = ImageOps.exif_transpose(img).convert("RGB")
        except (UnidentifiedImageError, OSError) as e:
            raise BackgroundError(f"Not a supported image: {e}") from None
        self.dir.mkdir(parents=True, exist_ok=True)
        name = self._name(filename)
        img.save(self.dir / name, "JPEG", quality=92)
        thumb = ImageOps.fit(img, THUMB, Image.Resampling.LANCZOS)
        thumb.save(self.dir / name.replace(".jpg", ".thumb.jpg"), "JPEG", quality=80)
        return name

    def path(self, name: str, thumb: bool = False) -> Path | None:
        if name not in self.list():
            return None
        return self.dir / (name.replace(".jpg", ".thumb.jpg") if thumb else name)

    def delete(self, name: str) -> bool:
        path = self.path(name)
        if path is None:
            return False
        path.unlink(missing_ok=True)
        self.dir.joinpath(name.replace(".jpg", ".thumb.jpg")).unlink(missing_ok=True)
        return True
