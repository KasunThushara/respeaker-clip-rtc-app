from __future__ import annotations

import pytest

from clip import ClipClient, WifiAccessPoint
from clip.exceptions import HostWifiUnsupportedError
from clip.tools.web import WebConfig, WebService
from clip.wifi import (
    HostWifiConnection,
    NetworkManagerBackend,
    WifiHandoff,
    _CommandResult,
    _macos_wifi_interface,
    _windows_wifi_interface,
    select_host_wifi_backend,
)

from conftest import FakeTransport


def test_selects_supported_native_backend_by_platform() -> None:
    installed = lambda _command: "/native/tool"
    assert isinstance(select_host_wifi_backend("Linux", which=installed), NetworkManagerBackend)
    assert select_host_wifi_backend("Darwin", which=installed).name == "macOS networksetup"
    assert select_host_wifi_backend("Windows", which=installed).name == "Windows netsh"
    with pytest.raises(HostWifiUnsupportedError):
        select_host_wifi_backend("Linux", which=lambda _command: None)


@pytest.mark.asyncio
async def test_network_manager_uses_argument_vector_and_detects_interface() -> None:
    commands: list[tuple[str, ...]] = []

    async def runner(args, _timeout):
        commands.append(tuple(args))
        if args[:4] == ("nmcli", "-t", "-f", "DEVICE,TYPE,STATE"):
            return _CommandResult(0, "eth0:ethernet:connected\nwlan0:wifi:disconnected\n", "")
        return _CommandResult(0, "", "")

    connection = await NetworkManagerBackend(runner).connect("ClipAP_8673", "12345678", timeout=30)
    assert connection.interface == "wlan0"
    assert commands[1][:6] == ("nmcli", "--wait", "30", "device", "wifi", "connect")
    assert "12345678" in commands[1]  # Passed as one argv item, never through a shell.


def test_platform_interface_parsers() -> None:
    assert _macos_wifi_interface("Hardware Port: Wi-Fi\nDevice: en0\nEthernet Address: aa:bb\n") == "en0"
    assert _windows_wifi_interface("    Name                   : Wi-Fi\n    State                  : connected\n") == "Wi-Fi"


@pytest.mark.asyncio
async def test_web_service_replaces_ble_client_after_verified_handoff(monkeypatch, tmp_path) -> None:
    old_transport = FakeTransport()
    new_transport = FakeTransport()
    old_client = ClipClient(old_transport)
    new_client = ClipClient(new_transport)
    service = WebService(old_client, WebConfig(tmp_path))

    async def fake_handoff(client, *, access_point, timeout):
        assert client is old_client
        assert timeout == 12
        assert access_point.ssid == "ClipAP_8673"
        return WifiHandoff(
            WifiAccessPoint(True, "ClipAP_8673", "12345678", "192.168.4.1", 8089, True),
            HostWifiConnection("ClipAP_8673", "NetworkManager (nmcli)", "wlan0"),
            new_client,
        )

    monkeypatch.setattr("clip.tools.web.handoff_to_wifi", fake_handoff)
    old_transport.responses.append({"ok": True, "data": {"ssid": "ClipAP_8673", "password": "12345678", "ip": "192.168.4.1", "port": 8089}})
    await old_client.connect()
    state = await service.switch_to_wifi(timeout=12)
    assert service.client is new_client
    assert state["transport"] == "udp"
    assert state["backend"] == "NetworkManager (nmcli)"
