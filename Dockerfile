# --- build: turn the project into a wheel -----------------------------------
FROM python:3.12-slim-bookworm AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .

# --- runtime: Python + Chromium headless shell only -------------------------
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DATA_DIR=/data \
    HTTP_PORT=8080

COPY --from=build /wheels /wheels
# Only the headless shell build of Chromium (no full Chromium, Firefox or WebKit).
# Its system libraries are installed by hand: Playwright's --with-deps would also pull
# in the desktop graphics stack (Mesa/LLVM) and CJK fonts, which the shell never uses.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 libdbus-1-3 libdrm2 libgbm1 \
      libxkbcommon0 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
      libxi6 libxrandr2 libasound2 libexpat1 libglib2.0-0 libwayland-server0 \
      fontconfig fonts-liberation fonts-dejavu-core fonts-noto-color-emoji tzdata \
 && pip install /wheels/*.whl \
 && playwright install --only-shell chromium \
 && missing="$(ldd /ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell | grep 'not found' || true)" \
 && if [ -n "$missing" ]; then echo "Missing libraries:"; echo "$missing"; exit 1; fi \
 && rm -rf /wheels /var/lib/apt/lists/* /var/cache/apt/* /root/.cache /tmp/* \
 && fad --version

VOLUME /data
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD python3 -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"HTTP_PORT\", \"8080\")}/healthz', timeout=5)" || exit 1

ENTRYPOINT ["fad"]
CMD ["run"]
