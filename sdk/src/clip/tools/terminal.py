"""Interactive current-firmware AT terminal over BLE or Wi-Fi UDP."""

from __future__ import annotations

import argparse
import asyncio
import json

from .common import add_connection_options, make_client, to_json

ALIASES = {
    "status": "AT+GSTAT",
    "gstat": "AT+GSTAT",
    "battery": "AT+BATT?",
    "storage": "AT+STORAGE?",
    "version": "AT+VERSION",
    "start": "AT+START",
    "stop": "AT+STOP",
    "pause": "AT+PAUSE",
    "resume": "AT+RESUME",
    "mark": "AT+MARK",
    "sessions": "AT+LIST",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_options(parser)
    return parser


async def run(args: argparse.Namespace) -> None:
    client = make_client(args)

    def event_callback(event: dict) -> None:
        print(f"\n[event] {json.dumps(event, ensure_ascii=False)}\nclip> ", end="", flush=True)

    async with client:
        client.on_event(event_callback)
        print("Connected. Enter AT+ commands; `help` lists aliases; `exit` quits.")
        try:
            print(to_json(await client.status()))
        except Exception as exc:
            print(f"Initial status unavailable: {exc}")
        while True:
            try:
                line = (await asyncio.to_thread(input, "clip> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not line:
                continue
            command = line.lower()
            if command in ("exit", "quit", "q"):
                return
            if command == "help":
                print("Aliases:", ", ".join(sorted(ALIASES)))
                print("Use any current firmware AT command, e.g. AT+LIST?2&10.")
                continue
            at_command = ALIASES.get(command, line if line.upper().startswith("AT+") else f"AT+{line}")
            try:
                print(to_json(await client.request(at_command)))
            except Exception as exc:
                print(f"Error: {exc}")


def main() -> int:
    try:
        asyncio.run(run(build_parser().parse_args()))
    except Exception as exc:
        print(f"terminal: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
