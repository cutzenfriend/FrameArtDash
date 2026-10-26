from datetime import time

import pytest

from frameartdash.config import ConfigError, Settings, in_window, parse_active_hours

BASE = {"TARGET_URL": "http://ha.local:8123/frame-dash/0"}


def test_defaults():
    s = Settings.from_env(BASE)
    assert s.viewport == (1920, 1080)
    assert s.output_size == (3840, 2160)
    assert s.style == "blur"
    assert s.interval_min == 10
    assert s.ha_url == "http://ha.local:8123"
    assert not s.ha_mode
    assert s.wait_selector == ""


def test_ha_mode_sets_wait_selector():
    s = Settings.from_env({**BASE, "HA_TOKEN": "abc"})
    assert s.ha_mode
    assert s.wait_selector == "home-assistant"


@pytest.mark.parametrize(
    "env",
    [
        {},
        {**BASE, "STYLE": "neon"},
        {**BASE, "STYLE": "image"},
        {**BASE, "VIEWPORT": "big"},
        {**BASE, "INTERVAL_MIN": "0"},
        {**BASE, "HIDE_CHROME": "maybe"},
        {**BASE, "EXTRA_HEADERS": "[1]"},
        {**BASE, "BASIC_AUTH": "nopassword"},
        {"TARGET_URL": "file:///etc/passwd"},
    ],
)
def test_invalid(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_parse_extras():
    s = Settings.from_env({**BASE, "BASIC_AUTH": "u:p:w", "EXTRA_HEADERS": '{"X-A": 1}'})
    assert s.basic_auth == ("u", "p:w")
    assert s.extra_headers == {"X-A": "1"}


def test_active_hours():
    assert parse_active_hours("") is None
    assert parse_active_hours("always") is None
    window = parse_active_hours("06-23")
    assert in_window(window, time(6, 0))
    assert in_window(window, time(22, 59))
    assert not in_window(window, time(23, 0))
    assert not in_window(window, time(5, 59))


def test_active_hours_wrapping_and_minutes():
    window = parse_active_hours("22:30-06")
    assert in_window(window, time(23, 0))
    assert in_window(window, time(2, 0))
    assert not in_window(window, time(12, 0))
    assert in_window(parse_active_hours("06-24"), time(23, 59))
