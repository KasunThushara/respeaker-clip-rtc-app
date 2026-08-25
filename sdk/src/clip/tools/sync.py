"""Download the newest, selected, or all recording sessions using the SDK."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .common import add_connection_options, make_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_options(parser)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--session", help="14-digit session ID")
    selection.add_argument("--all", action="store_true", help="download every listed session")
    parser.add_argument("--start-file", help="resume from NNNN.opus (valid only with --session)")
    parser.add_argument("--output", type=Path, default=Path("recordings"))
    parser.add_argument("--timeout", type=float, default=300.0, help="per-session transfer timeout in seconds")
    parser.add_argument("--delete", action="store_true", help="delete each session only after a successful download")
    parser.add_argument("--status", action="store_true", help="show device/session status without downloading")
    return parser


async def run(args: argparse.Namespace) -> int:
    if args.start_file and not args.session:
        raise ValueError("--start-file requires --session")
    client = make_client(args)
    async with client:
        if args.status:
            status = await client.status()
            sessions = await client.list_all_sessions()
            print(f"{status.device_name}: {status.state}, {status.battery_percent}% battery")
            for item in sessions:
                print(f"{item.id}: {item.files} files, {item.size_bytes} bytes")
            return 0

        sessions = await client.list_all_sessions()
        if args.session:
            selected = [item for item in sessions if item.id == args.session]
            if not selected:
                raise ValueError(f"session {args.session} was not found")
        elif args.all:
            selected = list(sessions)
        elif sessions:
            selected = [sessions[0]]  # Firmware lists sessions newest-first.
        else:
            print("No sessions on the device.")
            return 0

        for index, item in enumerate(selected, start=1):
            print(f"[{index}/{len(selected)}] {item.id}")

            def progress(name: str, received: int, total: int) -> None:
                print(f"\r  {name}: {received}/{total} bytes", end="", flush=True)

            result = await client.download_session(
                item.id,
                args.output,
                start_file=args.start_file if item.id == args.session else None,
                timeout=args.timeout,
                progress=progress,
            )
            print(f"\n  saved {len(result.files)} file(s) to {result.output_dir}")
            if args.delete:
                await client.delete_session(item.id, confirm=True)
                print("  deleted from device")
    return 0


def main() -> int:
    try:
        return asyncio.run(run(build_parser().parse_args()))
    except Exception as exc:
        print(f"sync: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
