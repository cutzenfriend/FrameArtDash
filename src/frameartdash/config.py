"""Settings: edited in the web UI, persisted in ``/data/settings.json``.

Every setting has a key (``TARGET_URL`` …). Values are looked up in this order:
``settings.json`` (written by the web UI), then environment variables, then the
built-in default. Only ``ADMIN_PASSWORD``, ``HTTP_PORT``, ``DATA_DIR``,
``LOG_LEVEL`` and ``TZ`` are meant to be set as container environment.
"""

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


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    group: str
    default: str = ""
    kind: str = "text"  # text | url | secret | number | bool | select | textarea | background
    help: str = ""
    options: tuple[str, ...] = ()
    advanced: bool = False


GROUPS = ("Source", "TV", "Look", "Schedule")

FIELDS: tuple[Field, ...] = (
    # Source
    Field(
        "TARGET_URL",
        "Dashboard URL",
        "Source",
        kind="url",
        help="Page to render, e.g. http://homeassistant.local:8123/frame-dash/art",
    ),
    Field(
        "HA_TOKEN",
        "Home Assistant token",
        "Source",
        kind="secret",
        help="Long-lived access token (HA profile → Security). Enables Home Assistant mode.",
    ),
    Field(
        "HA_URL",
        "Home Assistant URL",
        "Source",
        kind="url",
        advanced=True,
        help="Only needed if the token belongs to another origin than the dashboard URL.",
    ),
    Field("HA_THEME", "HA theme", "Source", help="Frontend theme, e.g. frame. Empty: dashboard default."),
    Field(
        "HA_DARK",
        "Dark mode",
        "Source",
        kind="select",
        options=("", "true", "false"),
        help="Force dark or light mode of the theme.",
    ),
    Field("HA_LANGUAGE", "HA language", "Source", advanced=True, help="e.g. en, de"),
    Field("HIDE_CHROME", "Hide header and sidebar", "Source", "true", kind="bool"),
    Field(
        "WAIT_SELECTOR",
        "Wait for selector",
        "Source",
        advanced=True,
        help="CSS selector to wait for. Defaults to home-assistant in HA mode.",
    ),
    Field("VIEWPORT", "Viewport", "Source", "1920x1080", help="Browser size in CSS pixels"),
    Field(
        "DEVICE_SCALE",
        "Device scale",
        "Source",
        "2",
        kind="number",
        help="1920x1080 × 2 renders at native 4K sharpness",
    ),
    Field(
        "WAIT_MS",
        "Extra wait (ms)",
        "Source",
        "3000",
        kind="number",
        help="Time for charts and animations to finish",
    ),
    Field("EXTRA_CSS", "Extra CSS", "Source", kind="textarea", advanced=True),
    Field("BASIC_AUTH", "Basic auth", "Source", kind="secret", advanced=True, help="user:password"),
    Field(
        "EXTRA_HEADERS",
        "Extra headers",
        "Source",
        kind="textarea",
        advanced=True,
        help='JSON object, e.g. {"X-Api-Key": "…"}',
    ),
    Field("RENDER_TIMEOUT", "Render timeout (s)", "Source", "60", kind="number", advanced=True),
    # TV
    Field("FRAME_HOST", "TV IP address", "TV", help="IP of the Samsung The Frame"),
    Field("FRAME_PORT", "TV port", "TV", "8002", kind="number", advanced=True),
    Field("MATTE", "Matte", "TV", "none", help="none, shadowbox_polar, modern_apricot, …"),
    Field(
        "DRY_RUN",
        "Test mode",
        "TV",
        "false",
        kind="bool",
        help="Render previews on schedule but never contact the TV.",
    ),
    Field("ONLY_IN_ARTMODE", "Only while in Art Mode", "TV", "false", kind="bool"),
    Field(
        "CLEANUP_UNMANAGED",
        "Delete all other uploaded pictures",
        "TV",
        "false",
        kind="bool",
        help="Careful: removes every MY_* picture on the TV that FrameArtDash did not upload.",
    ),
    Field("UPLOAD_TIMEOUT", "Upload timeout (s)", "TV", "60", kind="number", advanced=True),
    # Look
    Field("STYLE", "Background", "Look", "blur", kind="select", options=STYLES),
    Field("BG_IMAGE", "Background image", "Look", kind="background", help="Used with background = image"),
    Field("BG_GRADIENT", "Gradient colors", "Look", "#20242e,#0b0d12", help="Top,bottom"),
    Field("BLUR_RADIUS", "Blur radius", "Look", "60", kind="number"),
    Field("BLUR_BRIGHTNESS", "Blur brightness", "Look", "0.45", kind="number", help="1 = unchanged"),
    Field("CANVAS_PADDING", "Margin (%)", "Look", "8", kind="number"),
    Field("CANVAS_SHADOW", "Drop shadow", "Look", "true", kind="bool"),
    Field("CANVAS_TEXTURE", "Canvas texture", "Look", "false", kind="bool"),
    Field("OUTPUT_SIZE", "Output size", "Look", "3840x2160", advanced=True),
    Field("JPEG_QUALITY", "JPEG quality", "Look", "90", kind="number", advanced=True),
    # Schedule
    Field("INTERVAL_MIN", "Interval (min)", "Schedule", "10", kind="number"),
    Field(
        "ACTIVE_HOURS",
        "Active hours",
        "Schedule",
        "06-23",
        help="HH[:MM]-HH[:MM], may wrap midnight; 'always' disables it",
    ),
    Field(
        "DIFF_THRESHOLD",
        "Change threshold",
        "Schedule",
        "4",
        kind="number",
        help="Minimum image change (0–256) that triggers an upload. 0 uploads every cycle.",
    ),
    Field("RETRIES", "Retries", "Schedule", "3", kind="number", advanced=True),
    Field("DEBUG_IMAGES", "Keep debug images", "Schedule", "false", kind="bool", advanced=True),
)

FIELD_MAP = {f.key: f for f in FIELDS}
DEFAULTS = {f.key: f.default for f in FIELDS}
SECRET_KEYS = frozenset(f.key for f in FIELDS if f.kind == "secret")


def _str(env: dict[str, str], name: str, default: str = "") -> str:
    value = env.get(name)
    if value is None:
        value = DEFAULTS.get(name, default)
    return str(value).strip()


def _bool(env: dict[str, str], name: str, default: bool = False) -> bool:
    raw = _str(env, name)
    if raw == "":
        return default
    value = raw.lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name}: expected a boolean, got {raw!r}")


def _int(env: dict[str, str], name: str, minimum: int | None = None, default: int = 0) -> int:
    raw = _str(env, name)
    if raw == "":
        return default
    try:
        value = int(float(raw))
    except ValueError:
        raise ConfigError(f"{name}: expected an integer, got {raw!r}") from None
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name}: must be >= {minimum}, got {value}")
    return value


def _float(env: dict[str, str], name: str) -> float:
    raw = _str(env, name)
    try:
        return float(raw)
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
    target_url: str = ""
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
    dry_run: bool = False
    upload_timeout: int = 60
    cleanup_unmanaged: bool = False

    # Schedule / diff
    interval_min: int = 10
    active_hours: tuple[time, time] | None = None
    diff_threshold: int = 4
    retries: int = 3

    # Service (environment only)
    http_port: int = 8080
    data_dir: Path = Path("/data")
    debug_images: bool = False
    log_level: str = "INFO"

    @property
    def ha_mode(self) -> bool:
        return bool(self.ha_token)

    @property
    def configured(self) -> bool:
        return bool(self.target_url)

    @property
    def token_file(self) -> Path:
        return self.data_dir / "tv-token.txt"

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def debug_dir(self) -> Path:
        return self.data_dir / "debug"

    @property
    def backgrounds_dir(self) -> Path:
        return self.data_dir / "backgrounds"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        """Build settings from a flat key/value mapping (environment or merged settings)."""
        env = dict(os.environ if env is None else env)
        data_dir = Path(_str(env, "DATA_DIR", "/data"))

        target_url = _str(env, "TARGET_URL")
        if target_url and urlsplit(target_url).scheme not in ("http", "https"):
            raise ConfigError(f"TARGET_URL must be an http(s) URL, got {target_url!r}")

        ha_token = _str(env, "HA_TOKEN")
        ha_url = _str(env, "HA_URL")
        if not ha_url and target_url:
            parts = urlsplit(target_url)
            ha_url = f"{parts.scheme}://{parts.netloc}"
        ha_url = ha_url.rstrip("/")

        ha_dark = None if _str(env, "HA_DARK") == "" else _bool(env, "HA_DARK")

        style = _str(env, "STYLE").lower() or "blur"
        if style not in STYLES:
            raise ConfigError(f"STYLE must be one of {', '.join(STYLES)}, got {style!r}")
        bg_image = _str(env, "BG_IMAGE")
        if bg_image and not os.path.isabs(bg_image):
            bg_image = str(data_dir / "backgrounds" / bg_image)
        if style == "image" and not bg_image:
            raise ConfigError("Background 'image' requires a background image")

        gradient = [c.strip() for c in _str(env, "BG_GRADIENT").split(",") if c.strip()]
        if len(gradient) == 1:
            gradient = gradient * 2
        if len(gradient) != 2:
            raise ConfigError("BG_GRADIENT: expected one or two colors, e.g. '#20242e,#0b0d12'")

        padding = _float(env, "CANVAS_PADDING")
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

        wait_selector = _str(env, "WAIT_SELECTOR") or ("home-assistant" if ha_token else "")

        quality = _int(env, "JPEG_QUALITY", minimum=1)
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
            wait_selector=wait_selector,
            viewport=parse_size(_str(env, "VIEWPORT"), "VIEWPORT"),
            device_scale=_float(env, "DEVICE_SCALE"),
            wait_ms=_int(env, "WAIT_MS", minimum=0),
            extra_css=_str(env, "EXTRA_CSS"),
            basic_auth=basic_auth,
            extra_headers=extra_headers,
            render_timeout=_int(env, "RENDER_TIMEOUT", minimum=5),
            output_size=parse_size(_str(env, "OUTPUT_SIZE"), "OUTPUT_SIZE"),
            style=style,
            bg_image=bg_image,
            bg_gradient=(gradient[0], gradient[1]),
            blur_radius=_int(env, "BLUR_RADIUS", minimum=0),
            blur_brightness=_float(env, "BLUR_BRIGHTNESS"),
            canvas_padding=padding,
            canvas_shadow=_bool(env, "CANVAS_SHADOW", True),
            canvas_texture=_bool(env, "CANVAS_TEXTURE"),
            jpeg_quality=quality,
            frame_host=_str(env, "FRAME_HOST"),
            frame_port=_int(env, "FRAME_PORT", minimum=1),
            matte=_str(env, "MATTE") or "none",
            only_in_artmode=_bool(env, "ONLY_IN_ARTMODE"),
            dry_run=_bool(env, "DRY_RUN"),
            upload_timeout=_int(env, "UPLOAD_TIMEOUT", minimum=5),
            cleanup_unmanaged=_bool(env, "CLEANUP_UNMANAGED"),
            interval_min=_int(env, "INTERVAL_MIN", minimum=1),
            active_hours=parse_active_hours(_str(env, "ACTIVE_HOURS")),
            diff_threshold=_int(env, "DIFF_THRESHOLD", minimum=0),
            retries=_int(env, "RETRIES", minimum=1),
            http_port=_int(env, "HTTP_PORT", minimum=0, default=8080),
            data_dir=data_dir,
            debug_images=_bool(env, "DEBUG_IMAGES"),
            log_level=(_str(env, "LOG_LEVEL") or "INFO").upper(),
        )


class SettingsStore:
    """Reads and writes ``settings.json`` and merges it with the environment."""

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = dict(os.environ if env is None else env)
        self.data_dir = Path(self.env.get("DATA_DIR", "/data"))
        self.path = self.data_dir / "settings.json"

    def stored(self) -> dict[str, str]:
        try:
            raw = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as e:
            raise ConfigError(f"Could not read {self.path}: {e}") from None
        return {k: str(v) for k, v in raw.items() if k in FIELD_MAP}

    def merged(self, stored: dict[str, str] | None = None) -> dict[str, str]:
        return {**self.env, **(self.stored() if stored is None else stored)}

    def load(self) -> Settings:
        return Settings.from_env(self.merged())

    def effective(self) -> dict[str, str]:
        """Current raw value of every UI field (settings.json → env → default)."""
        merged = self.merged()
        return {f.key: str(merged.get(f.key, f.default)) for f in FIELDS}

    def update(self, changes: dict[str, str | None]) -> Settings:
        """Apply UI changes. ``None`` resets a key to env/default. Validates before writing."""
        stored = self.stored()
        for key, value in changes.items():
            if key not in FIELD_MAP:
                raise ConfigError(f"Unknown setting {key}")
            if value is None:
                stored.pop(key, None)
            else:
                stored[key] = str(value).strip()
        settings = Settings.from_env(self.merged(stored))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(stored, indent=2, sort_keys=True))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        return settings
