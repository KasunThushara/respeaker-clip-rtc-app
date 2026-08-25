"""Start a recording session and stop it after a duration or Ctrl-C."""

from __future__ import annotations

import argparse
import asyncio

from .common import add_connection_options, make_client, to_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_options(parser)
    parser.add_argument("--mode", choices=("normal", "enhanced"), default="enhanced")
    parser.add_argument("--duration", type=float, help="record this many seconds; default waits for Ctrl-C")
    parser.add_argument("--mark-every", type=float, help="insert a bookmark periodically")
    return parser


async def run(args: argparse.Namespace) -> int:
    if args.duration is not None and args.duration <= 0:
        raise ValueError("--duration must be positive")
    if args.mark_every is not None and args.mark_every <= 0:
        raise ValueError("--mark-every must be positive")
    client = make_client(args)
    async with client:
        session = await client.start_recording(args.mode)
        print(f"Recording session: {session or '(initializing)'}")
        duration_task = asyncio.create_task(asyncio.sleep(args.duration)) if args.duration else None
        marker_task = asyncio.create_task(_mark_periodically(client, args.mark_every)) if args.mark_every else None
        try:
            if duration_task is None:
                print("Press Ctrl-C to stop.")
                await asyncio.Event().wait()
            else:
                await duration_task
        except KeyboardInterrupt:
            print("Stopping...")
        finally:
            if marker_task:
                marker_task.cancel()
                try:
                    await marker_task
                except asyncio.CancelledError:
                    pass
            if duration_task:
                duration_task.cancel()
            result = await client.stop_recording()
            print(to_json(result))
    return 0


async def _mark_periodically(client, every_seconds: float) -> None:
    while True:
        await asyncio.sleep(every_seconds)
        bookmark = await client.bookmark()
        print(f"Bookmark at {bookmark.offset_seconds}s")


def main() -> int:
    try:
        return asyncio.run(run(build_parser().parse_args()))
    except Exception as exc:
        print(f"record: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
