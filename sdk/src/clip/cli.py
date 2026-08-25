"""Small command line interface for the standalone Clip SDK."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import sys
from typing import Any

from .client import ClipClient
from .transports import BleTransport, UdpTransport


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clip-sdk", description="reSpeaker Clip SDK command-line client")
    parser.add_argument("--transport", choices=("ble", "udp"), default="ble", help="connection transport (default: ble)")
    parser.add_argument("--address", help="BLE MAC/address; omit to scan by name")
    parser.add_argument("--name", default="Clip", help="BLE scan name substring (default: Clip)")
    parser.add_argument("--host", default="192.168.4.1", help="Wi-Fi UDP host")
    parser.add_argument("--port", type=int, default=8089, help="Wi-Fi UDP port")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("status", "battery", "storage", "sessions", "version"):
        sub.add_parser(action)
    raw = sub.add_parser("command", help="send a current-firmware AT command")
    raw.add_argument("at_command")
    download = sub.add_parser("download", help="stream a session to a local directory")
    download.add_argument("session_id")
    download.add_argument("destination", type=Path)
    download.add_argument("--start-file", help="logical file to resume from, e.g. 0016.opus")
    download.add_argument("--timeout", type=float, default=300.0)
    return parser


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


async def _execute(args: argparse.Namespace) -> Any:
    transport = (
        BleTransport(address=args.address, name=args.name)
        if args.transport == "ble"
        else UdpTransport(host=args.host, port=args.port)
    )
    async with ClipClient(transport) as client:
        if args.action == "status":
            return await client.status()
        if args.action == "battery":
            return await client.battery()
        if args.action == "storage":
            return await client.storage()
        if args.action == "sessions":
            return await client.list_all_sessions()
        if args.action == "version":
            return {"firmware": await client.firmware_version()}
        if args.action == "command":
            return await client.request(args.at_command)
        if args.action == "download":
            def progress(name: str, received: int, total: int) -> None:
                print(f"\r{name}: {received}/{total} bytes", end="", file=sys.stderr, flush=True)

            result = await client.download_session(
                args.session_id,
                args.destination,
                start_file=args.start_file,
                timeout=args.timeout,
                progress=progress,
            )
            print(file=sys.stderr)
            return result
    raise AssertionError(f"unknown action {args.action}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = asyncio.run(_execute(args))
    except Exception as exc:
        print(f"clip-sdk: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(_serialize(result), ensure_ascii=False, indent=2))
    return 0
