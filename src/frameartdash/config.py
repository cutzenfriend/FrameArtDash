"""Configuration, read from environment variables."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from urllib.parse import urlsplit

STYLES = ("blur", "image", "gradient")


class ConfigError(ValueError):
    pass


def _str(env: dict[str, str], name: str, default: str = "") -> str:
    return env.get(name, default).strip()


def _bool(env: dict[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name}: expected a boolean, got {raw!r}")


def _int(env: dict[str, str], name: str, default: int, minimum: int | None = None) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        raise ConfigError(f"{name}: expected an integer, got {raw!r}") from None
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name}: must be >= {minimum}, got {value}")
    return value


def _float(env: dict[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError:
        raise ConfigError(f"{name}: expected a number, got {raw!r}") from None


def parse_size(value: str, name: str) -> tuple[int, int]:
    try:
        w, h = value.lower().replace(" ", "").split("x")
        size = int(w), int(h)
    except ValueError:
        raise ConfigError(f"{name}: expected WIDTHxHEIGHT, got {value!r}") from None
    if size[0] <= 0 or size[1] <= 0:
        raise ConfigError(f"{name}: dimensions must be positive, got {value!r}")
    return size


def parse_active_hours(value: str) -> tuple[time, time] | None:
    """Parse ``HH[:MM]-HH[:MM]``. The window may wrap midnight (``22-06``).

    An empty value or ``always`` disables the window. ``24`` is accepted as end of day.
    """
    value = value.strip().lower()
    if value in ("", "always", "*", "00-24", "0-24"):
        return None

    def parse_point(point: str) -> time:
        hh, _, mm = point.partition(":")
        hour, minute = int(hh), int(mm or 0)
        if hour == 24 and minute == 0:
            return time(23, 59, 59, 999999)
        return time(hour, minute)

    try:
        start, end = value.split("-")
        return parse_point(start), parse_point(end)
    except ValueError:
        raise ConfigError(f"ACTIVE_HOURS: expected e.g. '06-23' or '06:30-22:15', got {value!r}") from None


def in_window(window: tuple[time, time] | None, now: time) -> bool:
    if window is None:
        return True
    start, end = window
    if start <= end:
        return start <= now < end
    return now >= start or now < end


@dataclass(frozen=True)
class Settings:
    # Render
    target_url: str
    ha_token: str = ""
    ha_url: str = ""
    ha_theme: str = ""
    ha_dark: bool | None = None
    ha_language: str = ""
    hide_chrome: bool = True
    wait_selector: str = ""
    viewport: tuple[int, int] = (1920, 1080)
    device_scale: float = 2.0
    wait_ms: int = 3000
    extra_css: str = ""
    basic_auth: tuple[str, str] | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)
    render_timeout: int = 60

    # Compose
    output_size: tuple[int, int] = (3840, 2160)
    style: str = "blur"
    bg_image: str = ""
    bg_gradient: tuple[str, str] = ("#20242e", "#0b0d12")
    blur_radius: int = 60
    blur_brightness: float = 0.45
    canvas_padding: float = 8.0
    canvas_shadow: bool = True
    canvas_texture: bool = False
    jpeg_quality: int = 90

    # Frame
    frame_host: str = ""
    frame_port: int = 8002
    matte: str = "none"
    only_in_artmode: bool = False
    upload_timeout: int = 60
    cleanup_unmanaged: bool = False

    # Schedule / diff
    interval_min: int = 10
    active_hours: tuple[time, time] | None = None
    diff_threshold: int = 4
    retries: int = 3

    # Service
    http_port: int = 8080
    data_dir: Path = Path("/data")
    debug_images: bool = False
    log_level: str = "INFO"

    @property
    def ha_mode(self) -> bool:
        return bool(self.ha_token)

    @property
    def token_file(self) -> Path:
        return self.data_dir / "tv-token.txt"

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def debug_dir(self) -> Path:
        return self.data_dir / "debug"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ if env is None else env)

        target_url = _str(env, "TARGET_URL")
        if not target_url:
            raise ConfigError("TARGET_URL is required")
        if urlsplit(target_url).scheme not in ("http", "https"):
            raise ConfigError(f"TARGET_URL must be an http(s) URL, got {target_url!r}")

        ha_token = _str(env, "HA_TOKEN")
        ha_url = _str(env, "HA_URL")
        if not ha_url:
            parts = urlsplit(target_url)
            ha_url = f"{parts.scheme}://{parts.netloc}"
        ha_url = ha_url.rstrip("/")

        ha_dark_raw = _str(env, "HA_DARK")
        ha_dark = None if ha_dark_raw == "" else _bool(env, "HA_DARK", True)

        style = _str(env, "STYLE", "blur").lower()
        if style not in STYLES:
            raise ConfigError(f"STYLE must be one of {', '.join(STYLES)}, got {style!r}")
        bg_image = _str(env, "BG_IMAGE")
        if style == "image" and not bg_image:
            raise ConfigError("STYLE=image requires BG_IMAGE")

        gradient = [c.strip() for c in _str(env, "BG_GRADIENT", "#20242e,#0b0d12").split(",") if c.strip()]
        if len(gradient) == 1:
            gradient = gradient * 2
        if len(gradient) != 2:
            raise ConfigError("BG_GRADIENT: expected one or two colors, e.g. '#20242e,#0b0d12'")

        padding = _float(env, "CANVAS_PADDING", 8.0)
        if not 0 <= padding < 50:
            raise ConfigError(f"CANVAS_PADDING must be between 0 and 50 (percent), got {padding}")

        basic_auth = None
        if raw := _str(env, "BASIC_AUTH"):
            user, sep, password = raw.partition(":")
            if not sep:
                raise ConfigError("BASIC_AUTH: expected 'user:password'")
            basic_auth = (user, password)

        extra_headers: dict[str, str] = {}
        if raw := _str(env, "EXTRA_HEADERS"):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                raise ConfigError(f"EXTRA_HEADERS: invalid JSON ({e})") from None
            if not isinstance(parsed, dict):
                raise ConfigError("EXTRA_HEADERS: expected a JSON object")
            extra_headers = {str(k): str(v) for k, v in parsed.items()}

        wait_selector = env.get("WAIT_SELECTOR")
        if wait_selector is None:
            wait_selector = "home-assistant" if ha_token else ""

        quality = _int(env, "JPEG_QUALITY", 90, minimum=1)
        if quality > 100:
            raise ConfigError(f"JPEG_QUALITY must be <= 100, got {quality}")

        return cls(
            target_url=target_url,
            ha_token=ha_token,
            ha_url=ha_url,
            ha_theme=_str(env, "HA_THEME"),
            ha_dark=ha_dark,
            ha_language=_str(env, "HA_LANGUAGE"),
            hide_chrome=_bool(env, "HIDE_CHROME", True),
            wait_selector=wait_selector.strip(),
            viewport=parse_size(_str(env, "VIEWPORT", "1920x1080"), "VIEWPORT"),
            device_scale=_float(env, "DEVICE_SCALE", 2.0),
            wait_ms=_int(env, "WAIT_MS", 3000, minimum=0),
            extra_css=_str(env, "EXTRA_CSS"),
            basic_auth=basic_auth,
            extra_headers=extra_headers,
            render_timeout=_int(env, "RENDER_TIMEOUT", 60, minimum=5),
            output_size=parse_size(_str(env, "OUTPUT_SIZE", "3840x2160"), "OUTPUT_SIZE"),
            style=style,
            bg_image=bg_image,
            bg_gradient=(gradient[0], gradient[1]),
            blur_radius=_int(env, "BLUR_RADIUS", 60, minimum=0),
            blur_brightness=_float(env, "BLUR_BRIGHTNESS", 0.45),
            canvas_padding=padding,
            canvas_shadow=_bool(env, "CANVAS_SHADOW", True),
            canvas_texture=_bool(env, "CANVAS_TEXTURE", False),
            jpeg_quality=quality,
            frame_host=_str(env, "FRAME_HOST"),
            frame_port=_int(env, "FRAME_PORT", 8002, minimum=1),
            matte=_str(env, "MATTE", "none") or "none",
            only_in_artmode=_bool(env, "ONLY_IN_ARTMODE", False),
            upload_timeout=_int(env, "UPLOAD_TIMEOUT", 60, minimum=5),
            cleanup_unmanaged=_bool(env, "CLEANUP_UNMANAGED", False),
            interval_min=_int(env, "INTERVAL_MIN", 10, minimum=1),
            active_hours=parse_active_hours(_str(env, "ACTIVE_HOURS", "06-23")),
            diff_threshold=_int(env, "DIFF_THRESHOLD", 4, minimum=0),
            retries=_int(env, "RETRIES", 3, minimum=1),
            http_port=_int(env, "HTTP_PORT", 8080, minimum=0),
            data_dir=Path(_str(env, "DATA_DIR", "/data")),
            debug_images=_bool(env, "DEBUG_IMAGES", False),
            log_level=_str(env, "LOG_LEVEL", "INFO").upper(),
        )
