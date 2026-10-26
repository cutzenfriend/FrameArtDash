"""Persistent state: which images on the Frame belong to us."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class State:
    current_id: str | None = None
    managed_ids: list[str] = field(default_factory=list)
    last_hash: str | None = None
    last_upload: str | None = None

    def add(self, content_id: str) -> None:
        if content_id not in self.managed_ids:
            self.managed_ids.append(content_id)

    def stale_ids(self) -> list[str]:
        """Managed images that are not the one currently selected."""
        return [cid for cid in self.managed_ids if cid != self.current_id]

    def forget(self, content_ids: list[str]) -> None:
        self.managed_ids = [cid for cid in self.managed_ids if cid not in content_ids]


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> State:
        try:
            raw = json.loads(self.path.read_text())
        except FileNotFoundError:
            return State()
        except (OSError, json.JSONDecodeError) as e:
            log.warning("Could not read %s (%s), starting with empty state", self.path, e)
            return State()
        return State(
            current_id=raw.get("current_id"),
            managed_ids=list(raw.get("managed_ids", [])),
            last_hash=raw.get("last_hash"),
            last_upload=raw.get("last_upload"),
        )

    def save(self, state: State) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(state), indent=2))
        os.replace(tmp, self.path)
