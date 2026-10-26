"""Command line interface: ``fad <command>``."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from frameartdash import __version__, frame as frame_mod
from frameartdash.config import ConfigError, Settings, SettingsStore
from frameartdash.service import Service

log = logging.getLogger("frameartdash")


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if level != "DEBUG":
        # samsungframetv logs every websocket event at INFO.
        logging.getLogger("samsungframetv").setLevel(logging.WARNING)


async def _cmd_run(settings: Settings, args: argparse.Namespace) -> int:
    from frameartdash.auth import Auth
    from frameartdash.web import serve

    log.info("FrameArtDash %s starting", __version__)
    if not settings.configured:
        log.info("Not configured yet: open the web UI to set it up")
    auth = Auth(settings.data_dir, os.environ.get("ADMIN_PASSWORD"))
    await serve(Service(settings), SettingsStore(), auth)
    return 0


async def _cmd_once(settings: Settings, args: argparse.Namespace) -> int:
    service = Service(settings)
    result = await service.run_cycle(force=args.force, upload=not args.no_upload)
    if args.output and service.last_jpeg:
        Path(args.output).write_bytes(service.last_jpeg)
        log.info("Wrote %s", args.output)
    print(json.dumps(result.as_dict(), indent=2))
    return 1 if result.status == "error" else 0


async def _cmd_pair(settings: Settings, args: argparse.Namespace) -> int:
    print(f"Pairing with {settings.frame_host}. Press 'Allow' on the TV when prompted...")
    if await frame_mod.pair(settings, force=args.force):
        print(f"Paired. Token stored in {settings.token_file}")
        return 0
    print("Pairing failed: no token received.", file=sys.stderr)
    return 1


async def _cmd_status(settings: Settings, args: argparse.Namespace) -> int:
    async with frame_mod.connect(settings) as frame:
        info = {"power": await frame.power_state()}
        if info["power"] in frame_mod.POWER_ON_STATES:
            info["current"] = await frame.current()
            info["my_photos"] = await frame.my_photos()
    info["state"] = json.loads(settings.state_file.read_text()) if settings.state_file.exists() else None
    print(json.dumps(info, indent=2))
    return 0


async def _cmd_cleanup(settings: Settings, args: argparse.Namespace) -> int:
    deleted = await Service(settings).cleanup()
    print(json.dumps({"deleted": deleted}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fad",
        description="FrameArtDash: render a dashboard as artwork for Samsung The Frame. "
        "Settings come from the web UI (/data/settings.json) or environment variables.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="run the web UI and the schedule loop (default)")

    once = sub.add_parser("once", help="run a single render -> compose -> push -> cleanup cycle")
    once.add_argument("--force", action="store_true", help="ignore ACTIVE_HOURS and the diff check")
    once.add_argument(
        "--no-upload", action="store_true", help="render and compose only, do not contact the TV"
    )
    once.add_argument("-o", "--output", help="also write the composed JPEG to this file")

    pair = sub.add_parser("pair", help="pair with the TV (press Allow on the TV)")
    pair.add_argument("--force", action="store_true", help="request a new token even if one exists")

    sub.add_parser("status", help="show TV power state, current art and managed images")
    sub.add_parser("cleanup", help="delete stale images uploaded by FrameArtDash")
    return parser


COMMANDS = {
    "run": _cmd_run,
    "once": _cmd_once,
    "pair": _cmd_pair,
    "status": _cmd_status,
    "cleanup": _cmd_cleanup,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"
    try:
        settings = SettingsStore().load()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2
    _setup_logging(settings.log_level)
    if command in ("pair", "status", "cleanup") and not settings.frame_host:
        print("Configuration error: no TV IP address (FRAME_HOST) configured", file=sys.stderr)
        return 2
    if command == "once" and not settings.configured:
        print("Configuration error: no dashboard URL (TARGET_URL) configured", file=sys.stderr)
        return 2
    try:
        return asyncio.run(COMMANDS[command](settings, args))
    except KeyboardInterrupt:
        return 130
