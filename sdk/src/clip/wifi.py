"""BLE-to-Wi-Fi handoff and native host Wi-Fi connection backends."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import time
from typing import Awaitable, Callable, Sequence
from xml.sax.saxutils import escape as xml_escape

from .client import ClipClient
from .exceptions import HostWifiError, HostWifiUnsupportedError
from .models import WifiAccessPoint
from .transports.udp import UdpTransport


@dataclass(frozen=True)
class HostWifiConnection:
    """Host-side information about a successful join to the Clip AP."""

    ssid: str
    backend: str
    interface: str | None = None
    profile: str | None = None


@dataclass
class WifiHandoff:
    """Result of switching data transfer from BLE control to Wi-Fi UDP."""

    access_point: WifiAccessPoint
    host_connection: HostWifiConnection
    client: ClipClient

    async def close(self) -> None:
        """Close only the SDK UDP socket; this does not disconnect host Wi-Fi."""
        await self.client.disconnect()


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str], float], Awaitable[_CommandResult]]


async def _run_command(args: Sequence[str], timeout: float) -> _CommandResult:
    """Run a native command without a shell or sensitive command logging."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            list(args),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HostWifiUnsupportedError(f"native Wi-Fi tool is unavailable: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HostWifiError(f"native Wi-Fi operation timed out after {timeout:g}s") from exc
    return _CommandResult(result.returncode, result.stdout, result.stderr)


class HostWifiBackend:
    """Base class for one native platform Wi-Fi connection mechanism."""

    name = "unknown"

    def __init__(self, runner: CommandRunner = _run_command) -> None:
        self._run = runner

    async def connect(self, ssid: str, password: str, *, timeout: float) -> HostWifiConnection:
        raise NotImplementedError

    async def _command(self, args: Sequence[str], timeout: float) -> _CommandResult:
        result = await self._run(args, timeout)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise HostWifiError(f"{self.name} could not join the Clip AP: {detail}")
        return result


class NetworkManagerBackend(HostWifiBackend):
    """Linux backend using NetworkManager's non-interactive ``nmcli`` command."""

    name = "NetworkManager (nmcli)"

    async def connect(self, ssid: str, password: str, *, timeout: float) -> HostWifiConnection:
        devices = await self._command(("nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"), timeout)
        interface = next(
            (
                fields[0]
                for line in devices.stdout.splitlines()
                if len((fields := line.split(":", 2))) == 3 and fields[1] == "wifi"
            ),
            None,
        )
        if not interface:
            raise HostWifiError("NetworkManager did not report a Wi-Fi interface")
        await self._command(
            ("nmcli", "--wait", str(max(1, int(timeout))), "device", "wifi", "connect", ssid, "password", password, "ifname", interface),
            timeout + 5,
        )
        return HostWifiConnection(ssid=ssid, backend=self.name, interface=interface)


class MacOSBackend(HostWifiBackend):
    """macOS backend using the built-in ``networksetup`` tool."""

    name = "macOS networksetup"

    async def connect(self, ssid: str, password: str, *, timeout: float) -> HostWifiConnection:
        hardware = await self._command(("networksetup", "-listallhardwareports"), timeout)
        interface = _macos_wifi_interface(hardware.stdout)
        if not interface:
            raise HostWifiError("networksetup did not report a Wi-Fi interface")
        await self._command(("networksetup", "-setairportnetwork", interface, ssid, password), timeout)
        return HostWifiConnection(ssid=ssid, backend=self.name, interface=interface)


class WindowsBackend(HostWifiBackend):
    """Windows backend using the built-in ``netsh wlan`` commands."""

    name = "Windows netsh"

    async def connect(self, ssid: str, password: str, *, timeout: float) -> HostWifiConnection:
        interfaces = await self._command(("netsh", "wlan", "show", "interfaces"), timeout)
        interface = _windows_wifi_interface(interfaces.stdout)
        if not interface:
            raise HostWifiError("netsh did not report a Wi-Fi interface")
        profile = "ClipSDK-" + hashlib.sha256(ssid.encode("utf-8")).hexdigest()[:12]
        profile_path = _write_windows_profile(profile, ssid, password)
        try:
            await self._command(
                ("netsh", "wlan", "add", "profile", f"filename={profile_path}", f"interface={interface}", "user=current"),
                timeout,
            )
            await self._command(
                ("netsh", "wlan", "connect", f"name={profile}", f"ssid={ssid}", f"interface={interface}"),
                timeout,
            )
        finally:
            profile_path.unlink(missing_ok=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = await self._command(("netsh", "wlan", "show", "interfaces"), min(5, timeout))
            if ssid in state.stdout:
                return HostWifiConnection(ssid=ssid, backend=self.name, interface=interface, profile=profile)
            await asyncio.sleep(1)
        raise HostWifiError(f"Windows did not associate with {ssid!r} before timeout")


def select_host_wifi_backend(
    system: str | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
    runner: CommandRunner = _run_command,
) -> HostWifiBackend:
    """Pick the appropriate native tool for the current host platform."""
    current = (system or platform.system()).lower()
    if current == "linux":
        if which("nmcli"):
            return NetworkManagerBackend(runner)
        raise HostWifiUnsupportedError("Linux automatic Wi-Fi join requires NetworkManager/nmcli")
    if current == "darwin":
        if which("networksetup"):
            return MacOSBackend(runner)
        raise HostWifiUnsupportedError("macOS automatic Wi-Fi join requires networksetup")
    if current in ("windows", "win32"):
        if which("netsh"):
            return WindowsBackend(runner)
        raise HostWifiUnsupportedError("Windows automatic Wi-Fi join requires netsh")
    raise HostWifiUnsupportedError(f"automatic Wi-Fi join is not implemented for {system or platform.system()}")


async def handoff_to_wifi(
    ble_client: ClipClient,
    *,
    backend: HostWifiBackend | None = None,
    access_point: WifiAccessPoint | None = None,
    timeout: float = 30.0,
) -> WifiHandoff:
    """Start the device AP over BLE, join it on the host, then verify UDP.

    The caller keeps ownership of ``ble_client``. It may stay connected for BLE
    control, or be disconnected after this function returns. The returned
    client carries commands and file transfer over Wi-Fi/UDP only.
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    access_point = access_point or await ble_client.start_wifi()
    if not access_point.running or not access_point.ssid or not access_point.password or not access_point.host or not access_point.port:
        raise HostWifiError("device did not return complete Wi-Fi AP credentials")
    selected = backend or select_host_wifi_backend()
    host_connection = await selected.connect(access_point.ssid, access_point.password, timeout=timeout)
    udp_client = ClipClient(UdpTransport(host=access_point.host, port=access_point.port))
    try:
        await udp_client.connect()
        await udp_client.status()  # Proves the UDP route, not merely a local socket.
    except Exception:
        await udp_client.disconnect()
        raise
    return WifiHandoff(access_point=access_point, host_connection=host_connection, client=udp_client)


def _macos_wifi_interface(output: str) -> str | None:
    for block in re.split(r"\n\s*\n", output):
        if "Wi-Fi" not in block and "AirPort" not in block:
            continue
        match = re.search(r"^Device:\s*(\S+)", block, flags=re.MULTILINE)
        if match:
            return match.group(1)
    return None


def _windows_wifi_interface(output: str) -> str | None:
    # netsh is localized. This works on English systems; localized systems have
    # a clear error instead of guessing an adapter and modifying the wrong one.
    for line in output.splitlines():
        if ":" not in line:
            continue
        left, right = (part.strip() for part in line.split(":", 1))
        if left.lower() == "name" and right:
            return right
    return None


def _write_windows_profile(profile: str, ssid: str, password: str) -> Path:
    xml = f"""<?xml version=\"1.0\"?>
<WLANProfile xmlns=\"http://www.microsoft.com/networking/WLAN/profile/v1\">
  <name>{xml_escape(profile)}</name>
  <SSIDConfig><SSID><name>{xml_escape(ssid)}</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType><connectionMode>auto</connectionMode>
  <MSM><security><authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption>
  <sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>{xml_escape(password)}</keyMaterial></sharedKey></security></MSM>
</WLANProfile>"""
    descriptor, temporary = tempfile.mkstemp(prefix="clip-wifi-", suffix=".xml")
    os.close(descriptor)
    path = Path(temporary)
    path.write_text(xml, encoding="utf-8")
    return path
