"""Start the Clip AP via BLE and automatically verify a Wi-Fi UDP handoff."""

from __future__ import annotations

import argparse
import asyncio

from .. import BleTransport, ClipClient
from ..wifi import handoff_to_wifi
from .common import to_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", help="BLE address; omit to scan by name")
    parser.add_argument("--name", default="Clip", help="BLE name substring when scanning")
    parser.add_argument("--timeout", type=float, default=30.0, help="host Wi-Fi join timeout in seconds")
    return parser


async def run(args: argparse.Namespace) -> int:
    if args.timeout <= 0:
        raise ValueError("--timeout must be positive")
    ble_client = ClipClient(BleTransport(address=args.address, name=args.name))
    handoff = None
    try:
        await ble_client.connect()
        handoff = await handoff_to_wifi(ble_client, timeout=args.timeout)
        print(to_json({"access_point": handoff.access_point, "host": handoff.host_connection, "status": await handoff.client.status()}))
        return 0
    finally:
        if handoff is not None:
            await handoff.close()
        await ble_client.disconnect()


def main() -> int:
    try:
        return asyncio.run(run(build_parser().parse_args()))
    except Exception as exc:
        print(f"wifi: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
