"""Dependency-free Wi-Fi UDP transport for the Clip firmware."""

from __future__ import annotations

import asyncio
import json
import struct
import time
from typing import Any

from ..exceptions import CommandTimeoutError, ConnectionError, ProtocolError
from ..protocol import (
    FRAME_AT_RESPONSE,
    FRAME_DATA,
    FRAME_FILE_ACK,
    FRAME_FILE_END,
    FRAME_FILE_START,
    FRAME_HEARTBEAT,
    FRAME_TRANSFER_DONE,
)
from .base import BaseTransport

DEFAULT_HOST = "192.168.4.1"
DEFAULT_PORT = 8089


class _UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, owner: "UdpTransport") -> None:
        self.owner = owner

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.owner._datagram_transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, _address: Any) -> None:
        self.owner._on_datagram(data)

    def error_received(self, exc: Exception) -> None:
        self.owner._last_error = exc

    def connection_lost(self, _exc: Exception | None) -> None:
        self.owner._connected = False


class UdpTransport(BaseTransport):
    """Transport for the Clip AP's UDP service (default `192.168.4.1:8089`)."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        super().__init__()
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("port must be in range 1..65535")
        self.host = host
        self.port = port
        self._datagram_transport: asyncio.DatagramTransport | None = None
        self._responses: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._command_lock = asyncio.Lock()
        self._connected = False
        self._desynchronized = False
        self._last_error: Exception | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self._datagram_transport is not None and not self._datagram_transport.is_closing()

    @property
    def uses_udp_file_frames(self) -> bool:
        return True

    async def connect(self) -> None:
        if self.is_connected:
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.create_datagram_endpoint(
                lambda: _UdpProtocol(self), remote_addr=(self.host, self.port)
            )
        except OSError as exc:
            raise ConnectionError(f"could not open UDP transport to {self.host}:{self.port}: {exc}") from exc
        self._connected = True
        self._desynchronized = False
        self._last_error = None
        self._drain_responses()
        # The firmware learns the client address from every datagram.  A
        # heartbeat makes command responses routable before the first AT command.
        self._send_heartbeat()

    async def disconnect(self) -> None:
        self._connected = False
        self._desynchronized = False
        self._drain_responses()
        transport = self._datagram_transport
        self._datagram_transport = None
        if transport is not None:
            transport.close()

    async def send_command(self, command: str, *, timeout: float) -> dict[str, Any]:
        async with self._command_lock:
            if not self.is_connected:
                raise ConnectionError("UDP transport is not connected")
            if self._desynchronized:
                raise ConnectionError("a previous UDP command timed out; disconnect and reconnect before retrying")
            if self._last_error is not None:
                raise ConnectionError(f"UDP transport error: {self._last_error}")
            self._drain_responses()
            assert self._datagram_transport is not None
            self._datagram_transport.sendto(command.encode("utf-8"))
            try:
                return await asyncio.wait_for(self._responses.get(), timeout=timeout)
            except asyncio.TimeoutError as exc:
                self._desynchronized = True
                raise CommandTimeoutError(f"no response to {command}") from exc

    def _on_datagram(self, data: bytes) -> None:
        if not data:
            return
        frame_type = data[0]
        if frame_type == FRAME_AT_RESPONSE:
            self._on_at_response(data)
        elif frame_type in (FRAME_DATA, FRAME_FILE_START, FRAME_FILE_END, FRAME_TRANSFER_DONE):
            self._emit_file_frame(data)
        elif frame_type == FRAME_HEARTBEAT:
            return

    def _on_at_response(self, frame: bytes) -> None:
        if len(frame) < 3:
            self._desynchronized = True
            return
        payload_size = struct.unpack_from("<H", frame, 1)[0]
        if len(frame) != 3 + payload_size:
            self._desynchronized = True
            return
        try:
            response = json.loads(frame[3:].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._desynchronized = True
            return
        if not isinstance(response, dict):
            self._desynchronized = True
        elif "event" in response:
            self._emit_event(response)
        else:
            self._responses.put_nowait(response)

    def _send_heartbeat(self) -> None:
        if self._datagram_transport is None:
            return
        timestamp = int(time.monotonic() * 1000) & 0xFFFFFFFF
        self._datagram_transport.sendto(struct.pack("<BI", FRAME_HEARTBEAT, timestamp))

    def send_file_ack(self, success: bool) -> None:
        if self.is_connected:
            assert self._datagram_transport is not None
            self._datagram_transport.sendto(bytes((FRAME_FILE_ACK, 0 if success else 1)))

    def _drain_responses(self) -> None:
        while True:
            try:
                self._responses.get_nowait()
            except asyncio.QueueEmpty:
                return
