"""Small previews of the current and the last uploaded images for the web UI."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)

PREVIEW_WIDTH = 1600
THUMB_WIDTH = 480


def _save(image: Image.Image, path: Path, width: int, quality: int) -> None:
    copy = image.copy()
    copy.thumbnail((width, width), Image.Resampling.LANCZOS)
    copy.save(path, "JPEG", quality=quality, optimize=True)


class History:
    """Keeps a preview of the current image plus thumbnails of the last few uploads."""

    def __init__(self, directory: Path, keep: int = 4) -> None:
        self.dir = directory
        self.keep = keep  # current + 3 previous
        self.index = directory / "history.json"

    def entries(self) -> list[dict]:
        try:
            return json.loads(self.index.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def add(self, image: Image.Image, content_id: str, when: datetime) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            stamp = when.strftime("%Y%m%d-%H%M%S")
            thumb = f"{stamp}.jpg"
            _save(image, self.dir / thumb, THUMB_WIDTH, 80)
            _save(image, self.dir / "current.jpg", PREVIEW_WIDTH, 85)

            entries = [{"file": thumb, "content_id": content_id, "time": when.isoformat(timespec="seconds")}]
            entries += [e for e in self.entries() if e.get("file") != thumb]
            for old in entries[self.keep :]:
                try:
                    (self.dir / old["file"]).unlink()
                except OSError:
                    pass
            tmp = self.index.with_suffix(".tmp")
            tmp.write_text(json.dumps(entries[: self.keep], indent=2))
            os.replace(tmp, self.index)
        except OSError as e:
            log.warning("Could not store history preview: %s", e)

    def path(self, name: str) -> Path | None:
        """Resolve a file name from the index safely (no path traversal)."""
        if name == "current.jpg" or any(e.get("file") == name for e in self.entries()):
            path = self.dir / name
            return path if path.is_file() else None
        return None
