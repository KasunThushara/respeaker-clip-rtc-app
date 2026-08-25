"""Shared argument parsing and connection helpers for installable SDK tools."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
from typing import Any

from .. import BleTransport, ClipClient, UdpTransport


def add_connection_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--transport", choices=("ble", "udp"), default="ble")
    parser.add_argument("--address", help="BLE address; omit to scan by name")
    parser.add_argument("--name", default="Clip", help="BLE name substring when scanning")
    parser.add_argument("--host", default="192.168.4.1", help="Clip Wi-Fi AP IP address")
    parser.add_argument("--port", type=int, default=8089, help="Clip Wi-Fi UDP port")


def make_client(args: argparse.Namespace) -> ClipClient:
    if args.transport == "ble":
        return ClipClient(BleTransport(address=args.address, name=args.name))
    return ClipClient(UdpTransport(host=args.host, port=args.port))


def to_json(value: Any) -> str:
    def encode(item: Any) -> Any:
        if is_dataclass(item):
            return {name: encode(field) for name, field in asdict(item).items()}
        if isinstance(item, tuple):
            return [encode(part) for part in item]
        return item

    return json.dumps(encode(value), ensure_ascii=False, indent=2)
