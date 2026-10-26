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

- **Web UI for everything:** dashboard URL, Home Assistant token, TV IP, pairing, look, schedule and background images. The UI shows the image currently on the Frame plus the last three as thumbnails. The only container variable you need is a password.
- **Preview without the TV:** render exactly what would be uploaded (full 4K, plus the raw browser screenshot) while the TV is off. Saving settings always renders a fresh preview, and *test mode* keeps the TV out of it entirely.
- **Live dashboards:** a Home Assistant long-lived access token is injected into the browser, so no login or OAuth is needed. Header and sidebar are hidden automatically.
- **Any web page:** a generic mode with optional Basic Auth and extra HTTP headers.
- **Gallery look:** the sharp dashboard sits centered as a "canvas" with a drop shadow. The background is a blurred copy of the dashboard, an image you upload in the UI, or a gradient. An optional canvas texture is available.
- **Only uploads on change:** a perceptual hash is compared with the last upload. If nothing relevant changed, nothing is sent, so the TV does not fade between identical images.
- **Keeps the TV tidy:** the new image is selected first and the old one deleted afterwards. The image on screen is never deleted. Orphans from crashed runs are cleaned up at startup.
- **Doesn't interrupt TV use:** the image is selected with `show=False`. Cycles are skipped when the TV is off, outside the active hours, or (optionally) when it is not in Art Mode.
- **Home Assistant integration:** `POST /refresh` with an API key for automations, `GET /healthz` for monitoring.
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
      ADMIN_PASSWORD: ${FAD_PASSWORD}
    volumes:
      - ./data:/data
    ports:
      - "8080:8080"
```

```bash
docker compose up -d
```

### 3. Set it up in the web UI

Open `http://<docker-host>:8080` and sign in with `ADMIN_PASSWORD`.

1. **Source:** enter the dashboard URL (e.g. `http://homeassistant.local:8123/frame-dash/art`) and the Home Assistant token. Click **Render preview** to check the result without touching the TV.
2. **TV:** enter the IP address of the Frame and save. Turn the TV on, click **Start pairing**, and confirm **Allow** on the TV with the remote.
3. **Look:** choose the background (blur, image or gradient). Upload your own background images by drag and drop.
4. Click **Push to the Frame now**. After that, a new image is pushed every interval, but only if the dashboard has changed.

If `ADMIN_PASSWORD` is not set, a random password is generated on first start. It is printed in the container log and stored in `/data/admin-password.txt`.

## Settings

All settings are edited in the web UI and stored in `/data/settings.json` (keep the `data` folder private: it also holds the HA token and the TV token). Every setting can alternatively be given as an environment variable with the same name. A value saved in the UI takes precedence.

### Container environment

| Variable | Default | Description |
|---|---|---|
| `ADMIN_PASSWORD` | *(generated)* | Password for the web UI |
| `TZ` | `UTC` | Time zone, used for the active hours |
| `HTTP_PORT` | `8080` | Port of the web UI |
| `DATA_DIR` | `/data` | Settings, tokens, state, backgrounds and history |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Source

| Key | Default | Description |
|---|---|---|
| `TARGET_URL` | | Page to render, e.g. `http://ha.local:8123/frame-dash/art` |
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

### TV

| Key | Default | Description |
|---|---|---|
| `FRAME_HOST` | | IP address of the Frame |
| `FRAME_PORT` | `8002` | Websocket port of the TV |
| `MATTE` | `none` | Matte for the uploaded image, e.g. `none`, `shadowbox_polar`, `modern_apricot` |
| `DRY_RUN` | `false` | Test mode: render previews on schedule, never contact the TV |
| `ONLY_IN_ARTMODE` | `false` | Only upload while the TV is in Art Mode |
| `CLEANUP_UNMANAGED` | `false` | ⚠️ Also delete **all other** uploaded `MY_*` pictures on the TV |
| `UPLOAD_TIMEOUT` | `60` | Seconds to wait for the upload to finish |

### Look

| Key | Default | Description |
|---|---|---|
| `STYLE` | `blur` | Background: `blur`, `image` or `gradient` |
| `BG_IMAGE` | | Background image for `STYLE=image`: a file uploaded in the UI, or an absolute path |
| `BG_GRADIENT` | `#20242e,#0b0d12` | Top and bottom color for `STYLE=gradient` |
| `BLUR_RADIUS` | `60` | Blur strength for `STYLE=blur` |
| `BLUR_BRIGHTNESS` | `0.45` | Brightness of the blurred background (1 = unchanged) |
| `CANVAS_PADDING` | `8` | Margin around the canvas in percent of the output size |
| `CANVAS_SHADOW` | `true` | Drop shadow below the canvas |
| `CANVAS_TEXTURE` | `false` | Subtle canvas grain on the dashboard |
| `OUTPUT_SIZE` | `3840x2160` | Size of the uploaded image |
| `JPEG_QUALITY` | `90` | JPEG quality (1–100) |

### Schedule

| Key | Default | Description |
|---|---|---|
| `INTERVAL_MIN` | `10` | Minutes between cycles. Uploading a 4K JPEG takes a few seconds; below ~5 minutes makes little sense. |
| `ACTIVE_HOURS` | `06-23` | Time window for scheduled cycles (`HH[:MM]-HH[:MM]`, may wrap midnight; `always` disables it) |
| `DIFF_THRESHOLD` | `4` | Minimum perceptual hash distance (0–256) that counts as a change. `0` uploads every cycle. |
| `RETRIES` | `3` | Attempts for render, upload and select, with exponential backoff |
| `DEBUG_IMAGES` | `false` | Keep the last screenshot and composed image in `/data/debug/` |

Saving settings in the UI triggers a new cycle right away. That cycle skips the change check once, so a new look reaches the TV immediately. If the TV is off or unreachable, it still renders a preview, which the UI shows under **Preview**.

## Home Assistant setup

A dedicated dashboard for the Frame looks much better than your everyday one. Use big tiles, few details and a calm dark theme. Examples:

- [`examples/homeassistant/dashboard.yaml`](examples/homeassistant/dashboard.yaml): a sections dashboard with clock, weather, sensors and a graph
- [`examples/homeassistant/theme.yaml`](examples/homeassistant/theme.yaml): a dark "gallery" theme (HA theme `frame`, dark mode `true`)
- [`examples/homeassistant/rest_command.yaml`](examples/homeassistant/rest_command.yaml): trigger a refresh from automations

FrameArtDash hides the header and sidebar itself (*Hide header and sidebar*). If you already use [kiosk-mode](https://github.com/NemesisRE/kiosk-mode), you can switch that off and append `?kiosk` to the dashboard URL instead.

### Refresh from an automation

The web UI shows a ready-made snippet with your API key:

```yaml
rest_command:
  frameartdash_refresh:
    url: http://<docker-host>:8080/refresh
    method: POST
    headers:
      Authorization: "Bearer <api key from the web UI>"
```

Call `rest_command.frameartdash_refresh` when someone enters the room. A refresh ignores the active hours and the change check, but still respects the TV's power state.

## HTTP endpoints

| Endpoint | Auth | Description |
|---|---|---|
| `GET /` | password | Web UI |
| `POST /refresh` | API key | Start a cycle now (`202 Accepted`, or `409` if one is already running). Send the key as `Authorization: Bearer <key>`. |
| `GET /healthz` | none | `200` while the scheduler runs |
| `/api/*` | password | JSON API used by the web UI |

The web UI uses a session cookie and plain HTTP. Put it behind a reverse proxy with TLS if you open it beyond your LAN.

## CLI

The image's entrypoint is `fad`, and `run` is the default command. The other commands are handy for debugging. They read the same `settings.json`.

| Command | Description |
|---|---|
| `fad run` | Web UI and scheduler loop |
| `fad once [--force] [--no-upload] [-o file.jpg]` | A single cycle |
| `fad pair [--force]` | Pair with the TV and store the token |
| `fad status` | Power state, current artwork, uploaded pictures and saved state |
| `fad cleanup` | Delete stale images uploaded by FrameArtDash |

## How cleanup works

`/data/state.json` records every content ID FrameArtDash uploaded, plus the one currently selected. After a new image has been uploaded **and** selected, all other recorded IDs are deleted. If a select fails, the new upload is still recorded, and it is removed in a later cycle. Pictures that you uploaded yourself are never touched unless `CLEANUP_UNMANAGED=true`.

## Troubleshooting

- **Cycle skipped: TV is off/standby.** The TV must be on (Art Mode or TV). Check network standby, and that the container can reach the TV (**Check TV** in the UI).
- **`ms.channel.timeOut` / no Allow prompt.** Turn the TV on and start pairing again with *Request a new token*.
- **Login page in the image.** The Home Assistant token is invalid, or *Home Assistant URL* doesn't match the origin of the dashboard URL.
- **Header still visible.** The HA frontend layout changes from time to time. Use *Extra CSS*, or kiosk-mode with `?kiosk`.
- **Nothing gets uploaded.** The dashboard may not have changed enough. Lower the change threshold, or click **Push to the Frame now**.
- **Inspect what is rendered.** Click **Render preview**, or enable *Keep debug images* and look at `/data/debug/`.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
playwright install --only-shell chromium
pytest
DATA_DIR=./data ADMIN_PASSWORD=dev fad run   # web UI on http://localhost:8080
```

## License

[MIT](LICENSE)
