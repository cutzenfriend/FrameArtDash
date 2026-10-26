"""Web UI login (signed session cookie) and API key for automations."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path

log = logging.getLogger(__name__)

COOKIE = "fad_session"
SESSION_DAYS = 30


def _read_or_create(path: Path, factory) -> str:
    try:
        value = path.read_text().strip()
        if value:
            return value
    except FileNotFoundError:
        pass
    value = factory()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n")
    os.chmod(path, 0o600)
    return value


class Auth:
    def __init__(self, data_dir: Path, password: str | None) -> None:
        self.data_dir = data_dir
        if password:
            self.password = password
        else:
            self.password = _read_or_create(
                data_dir / "admin-password.txt", lambda: secrets.token_urlsafe(12)
            )
            log.warning(
                "ADMIN_PASSWORD is not set. Generated web UI password: %s (stored in %s)",
                self.password,
                data_dir / "admin-password.txt",
            )
        self._secret = _read_or_create(data_dir / ".session-secret", lambda: secrets.token_hex(32)).encode()
        self._api_key_file = data_dir / "api-key.txt"
        self.api_key = _read_or_create(self._api_key_file, lambda: secrets.token_urlsafe(24))

    def check_password(self, password: str) -> bool:
        return hmac.compare_digest(password.encode(), self.password.encode())

    def check_api_key(self, key: str | None) -> bool:
        return bool(key) and hmac.compare_digest(key.encode(), self.api_key.encode())

    def rotate_api_key(self) -> str:
        self.api_key = secrets.token_urlsafe(24)
        self._api_key_file.write_text(self.api_key + "\n")
        return self.api_key

    def _sign(self, payload: str) -> str:
        # The password is part of the key so changing ADMIN_PASSWORD logs everyone out.
        key = self._secret + self.password.encode()
        return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()

    def new_session(self) -> str:
        expires = str(int(time.time()) + SESSION_DAYS * 86400)
        return f"{expires}.{self._sign(expires)}"

    def check_session(self, value: str | None) -> bool:
        if not value or "." not in value:
            return False
        expires, sig = value.split(".", 1)
        if not hmac.compare_digest(sig, self._sign(expires)):
            return False
        try:
            return int(expires) > time.time()
        except ValueError:
            return False
