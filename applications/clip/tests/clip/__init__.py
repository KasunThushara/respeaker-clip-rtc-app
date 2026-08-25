"""
reSpeaker Clip - Python BLE Control Library

A Python library for controlling the reSpeaker Clip device via BLE and WiFi.
Provides high-level APIs for device management, AT commands, and file transfer.
"""

from .client import ClipDevice
from .commands import ClipCommands
from .transfer import FileTransfer, SessionSync
from .exceptions import (
    ClipError,
    ConnectionError,
    DisconnectedError,
    CommandError,
    TransferError,
    TimeoutError,
    ResponseError,
    StateError,
)
from .wifi import WiFiDevice, WiFiSync
from .codec import OggOpusWriter, convert_to_ogg_opus, parse_raw_opus_frames

__version__ = "1.0.0"
__all__ = [
    "ClipDevice",
    "ClipCommands",
    "FileTransfer",
    "SessionSync",
    "ClipError",
    "ConnectionError",
    "DisconnectedError",
    "CommandError",
    "TransferError",
    "TimeoutError",
    "ResponseError",
    "StateError",
    "WiFiDevice",
    "WiFiSync",
    "OggOpusWriter",
    "convert_to_ogg_opus",
    "parse_raw_opus_frames",
]
