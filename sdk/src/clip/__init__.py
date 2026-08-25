"""Public API for the independently packaged reSpeaker Clip SDK."""

from .client import ClipClient
from .exceptions import (
    ClipError,
    CommandError,
    CommandTimeoutError,
    ConnectionError,
    HostWifiError,
    HostWifiUnsupportedError,
    ProtocolError,
    TransferError,
    TransferTimeoutError,
)
from .models import (
    Battery,
    Bookmark,
    DownloadResult,
    DownloadedFile,
    PairingStatus,
    Session,
    SessionDetails,
    Status,
    Storage,
    WifiAccessPoint,
)
from .transports import BaseTransport, BleTransport, UdpTransport
from .wifi import (
    HostWifiConnection,
    MacOSBackend,
    NetworkManagerBackend,
    WifiHandoff,
    WindowsBackend,
    handoff_to_wifi,
    select_host_wifi_backend,
)

__version__ = "0.1.0"

__all__ = [
    "BaseTransport",
    "Battery",
    "BleTransport",
    "Bookmark",
    "ClipClient",
    "ClipError",
    "CommandError",
    "CommandTimeoutError",
    "ConnectionError",
    "DownloadResult",
    "DownloadedFile",
    "HostWifiError",
    "HostWifiUnsupportedError",
    "HostWifiConnection",
    "MacOSBackend",
    "NetworkManagerBackend",
    "PairingStatus",
    "ProtocolError",
    "Session",
    "SessionDetails",
    "Status",
    "Storage",
    "TransferError",
    "TransferTimeoutError",
    "UdpTransport",
    "WifiHandoff",
    "WifiAccessPoint",
    "WindowsBackend",
    "handoff_to_wifi",
    "select_host_wifi_backend",
]
