"""Render the target page to a PNG screenshot with headless Chromium."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from playwright.async_api import Error as PlaywrightError, async_playwright

from frameartdash.config import Settings

log = logging.getLogger(__name__)

# Seeds Home Assistant's frontend auth with a long-lived access token, the same
# way the HA frontend stores its own session. ``expires`` lies far in the future
# so the frontend never tries to refresh it.
_HA_INIT_SCRIPT = """
(cfg) => {
  if (window.location.origin !== cfg.origin) return;
  try {
    window.localStorage.setItem("hassTokens", JSON.stringify({
      hassUrl: cfg.origin,
      clientId: cfg.origin + "/",
      access_token: cfg.token,
      token_type: "Bearer",
      expires_in: 315360000,
      expires: Date.now() + 315360000000,
      refresh_token: ""
    }));
    if (cfg.hideSidebar) window.localStorage.setItem("dockedSidebar", JSON.stringify("always_hidden"));
    if (cfg.theme !== null) window.localStorage.setItem("selectedTheme", JSON.stringify(cfg.theme));
    if (cfg.language) window.localStorage.setItem("selectedLanguage", JSON.stringify(cfg.language));
  } catch (e) {}
}
"""

# Hides the Lovelace toolbar. The header lives in the shadow DOM of <hui-root>,
# which page-level CSS cannot reach, so a style element is injected there.
_HA_HIDE_HEADER = """
() => {
  const find = (root, tag) => {
    const hit = root.querySelector(tag);
    if (hit) return hit;
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) {
        const found = find(el.shadowRoot, tag);
        if (found) return found;
      }
    }
    return null;
  };
  const huiRoot = find(document, "hui-root");
  if (!huiRoot || !huiRoot.shadowRoot) return false;
  if (!huiRoot.shadowRoot.querySelector("style[data-fad]")) {
    const style = document.createElement("style");
    style.dataset.fad = "1";
    style.textContent = `
      .header, .toolbar, app-header, ha-app-layout > [slot=header] { display: none !important; }
      #view, hui-view-container { padding-top: 0 !important; margin-top: 0 !important; min-height: 100vh !important; }
    `;
    huiRoot.shadowRoot.appendChild(style);
  }
  huiRoot.style.setProperty("--header-height", "0px");
  return true;
}
"""


class RenderError(RuntimeError):
    pass


async def render(settings: Settings) -> bytes:
    """Load ``TARGET_URL`` and return a PNG screenshot of the viewport."""
    try:
        return await asyncio.wait_for(_render(settings), timeout=settings.render_timeout)
    except TimeoutError:
        raise RenderError(f"rendering took longer than {settings.render_timeout}s") from None
    except PlaywrightError as e:
        raise RenderError(str(e).splitlines()[0]) from e


async def _render(settings: Settings) -> bytes:
    started = time.monotonic()
    width, height = settings.viewport
    timeout_ms = settings.render_timeout * 1000

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--disable-dev-shm-usage", "--hide-scrollbars"])
        try:
            context = await browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=settings.device_scale,
                http_credentials=(
                    {"username": settings.basic_auth[0], "password": settings.basic_auth[1]}
                    if settings.basic_auth
                    else None
                ),
                extra_http_headers=settings.extra_headers or None,
                color_scheme="dark" if settings.ha_dark is not False else "light",
            )
            if settings.ha_mode:
                await context.add_init_script(
                    script=f"({_HA_INIT_SCRIPT})({json.dumps(_ha_init_config(settings))})"
                )

            page = await context.new_page()
            page.set_default_timeout(timeout_ms)
            log.debug("Loading %s", settings.target_url)
            response = await page.goto(settings.target_url, wait_until="load")
            if response is not None and response.status >= 400:
                raise RenderError(f"{settings.target_url} returned HTTP {response.status}")

            if settings.wait_selector:
                await page.wait_for_selector(settings.wait_selector, state="attached")
            try:
                await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 15000))
            except PlaywrightError:
                log.debug("No network idle reached, continuing")

            if settings.ha_mode:
                await _check_ha_login(page)
                if settings.hide_chrome:
                    if not await page.evaluate(_HA_HIDE_HEADER):
                        log.debug("hui-root not found, header not hidden (not a Lovelace dashboard?)")
            if settings.extra_css:
                await page.add_style_tag(content=settings.extra_css)

            if settings.wait_ms:
                await page.wait_for_timeout(settings.wait_ms)
            if settings.ha_mode and settings.hide_chrome:
                # Views can re-render while charts load, apply once more before the shot.
                await page.evaluate(_HA_HIDE_HEADER)

            png = await page.screenshot(type="png", animations="disabled")
        finally:
            await browser.close()

    log.info("Rendered %s in %.1fs", settings.target_url, time.monotonic() - started)
    return png


def _ha_init_config(settings: Settings) -> dict:
    theme = None
    if settings.ha_theme or settings.ha_dark is not None:
        theme = {"theme": settings.ha_theme or "default"}
        if settings.ha_dark is not None:
            theme["dark"] = settings.ha_dark
    return {
        "origin": settings.ha_url,
        "token": settings.ha_token,
        "hideSidebar": settings.hide_chrome,
        "theme": theme,
        "language": settings.ha_language,
    }


async def _check_ha_login(page) -> None:
    if "/auth/authorize" in page.url:
        raise RenderError(
            "Home Assistant redirected to the login page. Check HA_TOKEN, and HA_URL if "
            "TARGET_URL is not on the Home Assistant origin."
        )
