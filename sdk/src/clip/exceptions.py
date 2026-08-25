"""Exception types exposed by the Clip SDK."""

from __future__ import annotations

from typing import Any


class ClipError(Exception):
    """Base class for all SDK errors."""


class ConnectionError(ClipError):
    """The selected transport could not connect or was disconnected."""


class CommandTimeoutError(ClipError):
    """The device did not send a command response before the deadline."""


class ProtocolError(ClipError):
    """The peer sent a malformed command response or transfer frame."""


class CommandError(ClipError):
    """The device rejected an AT command."""

    def __init__(self, message: str, *, command: str, response: dict[str, Any]):
        super().__init__(message)
        self.command = command
        self.response = response


class TransferError(ClipError):
    """A file transfer could not be completed safely."""


class TransferTimeoutError(TransferError):
    """A transfer did not complete before its deadline."""


class HostWifiError(ClipError):
    """The host computer could not join or manage the Clip Wi-Fi AP."""


class HostWifiUnsupportedError(HostWifiError):
    """No supported native Wi-Fi management tool was found for this platform."""
