from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from clip.transfer import FileReceiver

from conftest import FakeTransport

SID = "20260716022113"


def _start(name: str, size: int) -> bytes:
    encoded = name.encode()
    return b"\x10" + bytes((len(encoded),)) + encoded + struct.pack("<I", size)


def _data(sequence: int, payload: bytes, *, udp: bool = False) -> bytes:
    if udp:
        return b"\x01" + struct.pack("<HHI", sequence, len(payload), zlib.crc32(payload)) + payload
    return b"\x01" + struct.pack("<HH", sequence, len(payload)) + payload


def _end(payload: bytes) -> bytes:
    return b"\x11" + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF)


def _done(count: int) -> bytes:
    encoded = SID.encode()
    return b"\x12" + bytes((len(encoded),)) + encoded + struct.pack("<I", count)


@pytest.mark.asyncio
async def test_receiver_streams_to_part_then_atomically_publishes(tmp_path: Path) -> None:
    transport = FakeTransport()
    payload = b"streamed recording data"
    receiver = FileReceiver(transport, SID, tmp_path, udp=False)
    receiver.feed(_start("0001.opus", len(payload)))
    receiver.feed(_data(0, payload[:8]))
    receiver.feed(_data(1, payload[8:]))
    assert not (tmp_path / "0001.opus").exists()
    receiver.feed(_end(payload))
    receiver.feed(_done(1))
    await receiver.wait(0.1)
    assert (tmp_path / "0001.opus").read_bytes() == payload
    assert not (tmp_path / "0001.opus.part").exists()
    assert receiver.files[0].size_bytes == len(payload)


@pytest.mark.asyncio
async def test_udp_crc_failure_is_nacked_then_retransmitted(tmp_path: Path) -> None:
    class AckTransport(FakeTransport):
        def __init__(self) -> None:
            super().__init__()
            self.acks: list[bool] = []

        def send_file_ack(self, success: bool) -> None:
            self.acks.append(success)

    transport = AckTransport()
    payload = b"retry me"
    receiver = FileReceiver(transport, SID, tmp_path, udp=True)
    receiver.feed(_start("0001.opus", len(payload)))
    receiver.feed(_data(1, payload, udp=True))  # sequence 0 was lost
    receiver.feed(_end(payload))
    assert transport.acks == [False]
    assert not (tmp_path / "0001.opus").exists()

    receiver.feed(_start("0001.opus", len(payload)))
    receiver.feed(_data(0, payload, udp=True))
    receiver.feed(_end(payload))
    receiver.feed(_done(1))
    await receiver.wait(0.1)
    assert transport.acks == [False, True]
    assert (tmp_path / "0001.opus").read_bytes() == payload


@pytest.mark.asyncio
async def test_corrupt_udp_data_waits_for_file_end_then_nacks(tmp_path: Path) -> None:
    class AckTransport(FakeTransport):
        def __init__(self) -> None:
            super().__init__()
            self.acks: list[bool] = []

        def send_file_ack(self, success: bool) -> None:
            self.acks.append(success)

    transport = AckTransport()
    payload = b"crc"
    receiver = FileReceiver(transport, SID, tmp_path, udp=True)
    receiver.feed(_start("0001.opus", len(payload)))
    corrupt = _data(0, payload, udp=True)[:-1] + b"!"
    receiver.feed(corrupt)
    assert receiver.error is None
    receiver.feed(_end(payload))
    assert transport.acks == [False]
