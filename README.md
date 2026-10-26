# FrameArtDash (FAD)

**Your Home Assistant dashboard as a painting on Samsung The Frame.**

FrameArtDash is a small Docker service. On a schedule it renders a Home Assistant dashboard (or any web page) with live data in headless Chromium. It turns the screenshot into a 4K "artwork" and uploads it to the Art Mode of a Samsung The Frame TV. The previous image is removed afterwards, so nothing piles up on the TV.

```
 ┌──────────────┐  render   ┌──────────────┐  diff   ┌──────────────┐  push   ┌───────────────┐
 │ HA dashboard │ ────────▶ │  Playwright  │ ──────▶ │    Pillow    │ ──────▶ │ The Frame     │
 │ (any URL)    │           │  screenshot  │         │ 3840×2160    │         │ Art Mode      │
 └──────────────┘           └──────────────┘         └──────────────┘         └───────────────┘
                                                                          select new → delete old
```

> [!NOTE]
> The Frame's Art Mode API is unofficial and may break with firmware updates. FrameArtDash uses
> [`samsungframetv`](https://github.com/NickWaterton/samsung-tv-ws-api) by Nick Waterton, which
> supports Frame models from 2017 to 2025. This project is not affiliated with Samsung or Home Assistant.

## Features

- **Live dashboards:** a Home Assistant long-lived access token is injected into the browser, so no login or OAuth is needed. Header and sidebar are hidden automatically.
- **Any web page:** a generic mode with optional Basic Auth and extra HTTP headers.
- **Gallery look:** the sharp dashboard sits centered as a "canvas" with a drop shadow. The background is a blurred copy of the dashboard, your own image, or a gradient. An optional canvas texture is available.
- **Only uploads on change:** a perceptual hash is compared with the last upload. If nothing relevant changed, nothing is sent, so the TV does not fade between identical images.
- **Keeps the TV tidy:** the new image is selected first and the old one deleted afterwards. The image on screen is never deleted. Orphans from crashed runs are cleaned up at startup.
- **Doesn't interrupt TV use:** the image is selected with `show=False`. Cycles are skipped when the TV is off, outside `ACTIVE_HOURS`, or (optionally) when it is not in Art Mode.
- **HTTP API:** `POST /refresh` for Home Assistant automations, `GET /healthz` for monitoring, and `GET /last.jpg` to preview the last image.
- **Multi-arch image:** `linux/amd64` and `linux/arm64` on GHCR.

## Quick start

### 1. Requirements

- A Samsung The Frame TV on your LAN. Enable *Settings → General → Network → Expert Settings → Power On with Mobile* (network standby).
- A Docker host **on the same LAN** as the TV. The TV is reached directly via websocket, not via the cloud.
- For Home Assistant: a long-lived access token (*Profile → Security → Long-lived access tokens*). A dedicated, non-admin HA user for the Frame is a good idea.

### 2. `docker-compose.yml`

```yaml
services:
  frameartdash:
    image: ghcr.io/cutzenfriend/frameartdash:latest
    container_name: frameartdash
    restart: unless-stopped
    environment:
      TZ: Europe/Berlin
      TARGET_URL: http://192.168.1.10:8123/frame-dash/art
      HA_TOKEN: ${HA_TOKEN}
      FRAME_HOST: 192.168.1.50
      INTERVAL_MIN: 10
      ACTIVE_HOURS: "06-23"
      STYLE: blur
    volumes:
      - ./data:/data
    ports:
      - "8080:8080"
```

### 3. Pair with the TV (once)

Turn the TV on and run:

```bash
docker compose run --rm frameartdash pair
```

Confirm the **Allow** prompt on the TV with the remote. The token is stored in `/data/tv-token.txt`.

### 4. Try a single cycle, then start the service

```bash
docker compose run --rm frameartdash once --force
```

```bash
docker compose up -d
```

To tune the look without touching the TV, render to a file:

```bash
docker compose run --rm frameartdash once --no-upload -o /data/preview.jpg
```

## Configuration

All settings are environment variables.

### Rendering

| Variable | Default | Description |
|---|---|---|
| `TARGET_URL` | *(required)* | Page to render, e.g. `http://ha.local:8123/frame-dash/art` |
| `HA_TOKEN` | | Home Assistant long-lived access token. Enables Home Assistant mode. |
| `HA_URL` | origin of `TARGET_URL` | Home Assistant base URL the token belongs to |
| `HA_THEME` | | Frontend theme to use, e.g. `frame` |
| `HA_DARK` | | `true`/`false` to force dark/light mode of the theme |
| `HA_LANGUAGE` | | Frontend language, e.g. `en`, `de` |
| `HIDE_CHROME` | `true` | Hide the Home Assistant sidebar and dashboard header |
| `WAIT_SELECTOR` | `home-assistant` in HA mode | CSS selector to wait for before taking the screenshot |
| `VIEWPORT` | `1920x1080` | Browser viewport in CSS pixels |
| `DEVICE_SCALE` | `2` | Device pixel ratio. `1920x1080` × `2` gives native 4K sharpness. |
| `WAIT_MS` | `3000` | Extra wait after loading, so charts and animations can finish |
| `EXTRA_CSS` | | CSS injected into the page |
| `BASIC_AUTH` | | `user:password` for HTTP Basic Auth (generic mode) |
| `EXTRA_HEADERS` | | JSON object of extra request headers, e.g. `{"X-Api-Key": "…"}` |
| `RENDER_TIMEOUT` | `60` | Seconds before rendering is aborted |

### Composition

| Variable | Default | Description |
|---|---|---|
| `STYLE` | `blur` | Background: `blur`, `image` or `gradient` |
| `BG_IMAGE` | | Background image for `STYLE=image`, e.g. `/data/bg.jpg` |
| `BG_GRADIENT` | `#20242e,#0b0d12` | Top and bottom color for `STYLE=gradient` |
| `BLUR_RADIUS` | `60` | Blur strength for `STYLE=blur` |
| `BLUR_BRIGHTNESS` | `0.45` | Brightness of the blurred background (1 = unchanged) |
| `CANVAS_PADDING` | `8` | Margin around the canvas in percent of the output size |
| `CANVAS_SHADOW` | `true` | Drop shadow below the canvas |
| `CANVAS_TEXTURE` | `false` | Subtle canvas grain on the dashboard |
| `OUTPUT_SIZE` | `3840x2160` | Size of the uploaded image |
| `JPEG_QUALITY` | `90` | JPEG quality (1–100) |

### Frame, schedule and service

| Variable | Default | Description |
|---|---|---|
| `FRAME_HOST` | | IP address of the Frame |
| `FRAME_PORT` | `8002` | Websocket port of the TV |
| `MATTE` | `none` | Matte for the uploaded image, e.g. `none`, `shadowbox_polar`, `modern_apricot` |
| `ONLY_IN_ARTMODE` | `false` | Only upload while the TV is in Art Mode |
| `UPLOAD_TIMEOUT` | `60` | Seconds to wait for the upload to finish |
| `CLEANUP_UNMANAGED` | `false` | ⚠️ Also delete **all other** uploaded `MY_*` pictures on the TV |
| `INTERVAL_MIN` | `10` | Minutes between cycles. Uploading a 4K JPEG takes a few seconds; below ~5 minutes makes little sense. |
| `ACTIVE_HOURS` | `06-23` | Time window for scheduled cycles (`HH[:MM]-HH[:MM]`, may wrap midnight; `always` disables it). Set `TZ`. |
| `DIFF_THRESHOLD` | `4` | Minimum perceptual hash distance (0–256) that counts as a change. `0` uploads every cycle. |
| `RETRIES` | `3` | Attempts for render, upload and select, with exponential backoff |
| `HTTP_PORT` | `8080` | Port of the HTTP API (`0` disables it) |
| `DATA_DIR` | `/data` | Token, state and debug images |
| `DEBUG_IMAGES` | `false` | Keep the last screenshot and composed image in `/data/debug/` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Home Assistant setup

A dedicated dashboard for the Frame looks much better than your everyday one. Use big tiles, few details and a calm dark theme. Examples:

- [`examples/homeassistant/dashboard.yaml`](examples/homeassistant/dashboard.yaml): a sections dashboard with clock, weather, sensors and a graph
- [`examples/homeassistant/theme.yaml`](examples/homeassistant/theme.yaml): a dark "gallery" theme (`HA_THEME=frame`, `HA_DARK=true`)
- [`examples/homeassistant/rest_command.yaml`](examples/homeassistant/rest_command.yaml): trigger a refresh from automations

Header and sidebar are hidden by FrameArtDash itself (`HIDE_CHROME=true`). If you already use [kiosk-mode](https://github.com/NemesisRE/kiosk-mode), you can set `HIDE_CHROME=false` and append `?kiosk` to `TARGET_URL` instead.

### Refresh from an automation

```yaml
rest_command:
  frameartdash_refresh:
    url: http://<docker-host>:8080/refresh
    method: POST
```

Call `rest_command.frameartdash_refresh` when someone enters the room. A refresh ignores `ACTIVE_HOURS` and the diff check, but still respects the TV's power state.

## HTTP API

| Endpoint | Description |
|---|---|
| `POST /refresh` | Start a cycle now (`202 Accepted`, or `409` if one is already running). `?wait=1` waits and returns the result. `?force=0` keeps the diff check and active hours. |
| `GET /healthz` | `200` while the scheduler runs, with the last result and the time of the last success |
| `GET /last.jpg` | The last composed image |

## CLI

The image's entrypoint is `fad`, and `run` is the default command.

| Command | Description |
|---|---|
| `fad run` | Scheduler loop and HTTP API |
| `fad once [--force] [--no-upload] [-o file.jpg]` | A single cycle |
| `fad pair [--force]` | Pair with the TV and store the token |
| `fad status` | Power state, current artwork, uploaded pictures and saved state |
| `fad cleanup` | Delete stale images uploaded by FrameArtDash |

## How cleanup works

`/data/state.json` records every content ID FrameArtDash uploaded, plus the one currently selected. After a new image has been uploaded **and** selected, all other recorded IDs are deleted. If a select fails, the new upload is still recorded, and it is removed in a later cycle. Pictures that you uploaded yourself are never touched unless `CLEANUP_UNMANAGED=true`.

## Troubleshooting

- **Cycle skipped: TV is off/standby.** The TV must be on (Art Mode or TV). Check network standby, and that the container can reach the TV (`fad status`).
- **`ms.channel.timeOut` / no Allow prompt.** Delete `/data/tv-token.txt` and run `fad pair --force` while the TV is on.
- **Login page in the image.** `HA_TOKEN` is invalid, or `HA_URL` doesn't match the origin you open in `TARGET_URL`.
- **Header still visible.** The HA frontend layout changes from time to time. Use `EXTRA_CSS`, or kiosk-mode with `?kiosk`.
- **Nothing gets uploaded.** The dashboard may not have changed enough. Lower `DIFF_THRESHOLD`, or call `/refresh`.
- **Inspect what is rendered.** Set `DEBUG_IMAGES=true` and look at `/data/debug/`, or open `http://<host>:8080/last.jpg`.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
pytest
TARGET_URL=https://example.com DATA_DIR=./data fad once --no-upload -o preview.jpg
```

## License

[MIT](LICENSE)
