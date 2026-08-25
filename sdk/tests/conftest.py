from __future__ import annotations

from collections import deque
from typing import Any

from clip.transports.base import BaseTransport


class FakeTransport(BaseTransport):
    """Offline transport used to test public command handling."""

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self.responses = deque(responses or [])
        self.commands: list[str] = []
        self.connected = False

    @property
    def is_connected(self) -> bool:
        return self.connected

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def send_command(self, command: str, *, timeout: float) -> dict[str, Any]:
        assert self.connected
        self.commands.append(command)
        if not self.responses:
            raise AssertionError(f"unexpected command {command}")
        return self.responses.popleft()
