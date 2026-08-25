"""Typed values returned by the public Clip client API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


def _data(response: dict[str, Any]) -> dict[str, Any]:
    value = response.get("data", {})
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class Status:
    state: str
    recording: bool
    session_id: str | None
    duration_seconds: int
    battery_percent: int
    charging: bool
    temperature_c: int | None
    voltage_mv: int | None
    mode: str
    bitrate: int
    free_space_mb: int
    device_name: str

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> "Status":
        data = _data(response)
        return cls(
            state=str(data.get("state", "UNKNOWN")),
            recording=bool(data.get("recording", False)),
            session_id=data.get("session") if isinstance(data.get("session"), str) else None,
            duration_seconds=int(data.get("duration", 0)),
            battery_percent=int(data.get("battery", 0)),
            charging=bool(data.get("charging", False)),
            temperature_c=_int_or_none(data.get("temp")),
            voltage_mv=_int_or_none(data.get("voltage")),
            mode=str(data.get("mode", "normal")),
            bitrate=int(data.get("bitrate", 0)),
            free_space_mb=int(data.get("free_space", 0)),
            device_name=str(data.get("device", "Unknown")),
        )


@dataclass(frozen=True)
class Battery:
    percent: int
    charging: bool
    voltage_mv: int
    temperature_c: int

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> "Battery":
        data = _data(response)
        return cls(
            percent=int(data.get("battery", 0)),
            charging=bool(data.get("charging", False)),
            voltage_mv=int(data.get("voltage", 0)),
            temperature_c=int(data.get("temp", 0)),
        )


@dataclass(frozen=True)
class Storage:
    total_mb: int
    free_mb: int
    used_mb: int
    used_percent: int
    recorded_mb: int

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> "Storage":
        data = _data(response)
        return cls(
            total_mb=int(data.get("total_mb", 0)),
            free_mb=int(data.get("free_mb", 0)),
            used_mb=int(data.get("used_mb", 0)),
            used_percent=int(data.get("used_pct", 0)),
            recorded_mb=int(data.get("recorded_mb", 0)),
        )


@dataclass(frozen=True)
class Session:
    id: str
    files: int
    size_bytes: int
    bookmarks: int

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "Session":
        return cls(
            id=str(data.get("id", "")),
            files=int(data.get("files", 0)),
            size_bytes=int(data.get("size", 0)),
            bookmarks=int(data.get("bookmarks", 0)),
        )


@dataclass(frozen=True)
class SessionDetails:
    session_id: str
    files: int
    size_bytes: int
    synced_files: int
    bookmarks: int
    channels: int
    sample_rate_hz: int
    mode: str

    @classmethod
    def from_response(cls, session_id: str, response: dict[str, Any]) -> "SessionDetails":
        data = _data(response)
        return cls(
            session_id=session_id,
            files=int(data.get("files", 0)),
            size_bytes=int(data.get("size", 0)),
            synced_files=int(data.get("synced", 0)),
            bookmarks=int(data.get("bookmarks", 0)),
            channels=int(data.get("channels", 0)),
            sample_rate_hz=int(data.get("sample_rate", 0)),
            mode=str(data.get("mode", "")),
        )


@dataclass(frozen=True)
class Bookmark:
    offset_seconds: int

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "Bookmark":
        return cls(offset_seconds=int(data.get("offset", 0)))


@dataclass(frozen=True)
class WifiAccessPoint:
    running: bool
    ssid: str | None = None
    password: str | None = None
    host: str | None = None
    port: int | None = None
    connected: bool | None = None

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> "WifiAccessPoint":
        data = _data(response)
        return cls(
            running=bool(data.get("running", data.get("wifi") != "off")),
            ssid=_str_or_none(data.get("ssid")),
            password=_str_or_none(data.get("password")),
            host=_str_or_none(data.get("ip")),
            port=_int_or_none(data.get("port")),
            connected=_bool_or_none(data.get("connected")),
        )


@dataclass(frozen=True)
class PairingStatus:
    paired: bool
    peer_address: str | None


@dataclass(frozen=True)
class DownloadedFile:
    name: str
    path: str
    size_bytes: int


@dataclass(frozen=True)
class DownloadResult:
    session_id: str
    files: tuple[DownloadedFile, ...]
    expected_files: int
    output_dir: str


def _int_or_none(value: Any) -> int | None:
    return None if value is None else int(value)


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
