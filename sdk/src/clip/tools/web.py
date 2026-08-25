"""Local web control panel backed exclusively by the current Clip SDK API."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import ClipClient
from ..exceptions import ClipError, CommandTimeoutError, ConnectionError
from ..models import DownloadResult, Status
from ..validation import chunk_name, session_id
from ..wifi import WifiHandoff, handoff_to_wifi

STATIC_DIR = Path(__file__).with_name("web_static")


@dataclass(frozen=True)
class WebConfig:
    recordings_dir: Path
    poll_interval: float = 2.0


class WebService:
    """Owns one Clip connection, status broadcaster, and exclusive sync task."""

    def __init__(self, client: ClipClient, config: WebConfig) -> None:
        self.client = client
        self.config = config
        self._status_task: asyncio.Task[None] | None = None
        self._sync_task: asyncio.Task[None] | None = None
        self._sync_lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._handoff_lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._last_status: dict[str, Any] | None = None
        self._last_error: str | None = None
        self._sync: dict[str, Any] = {"active": False}
        self._network: dict[str, Any] = {
            "transport": "udp" if client.transport.uses_udp_file_frames else "ble",
            "switching": False,
        }
        self._pending_access_point = None

    async def start(self) -> None:
        self.config.recordings_dir.mkdir(parents=True, exist_ok=True)
        self._status_task = asyncio.create_task(self._status_loop(), name="clip-web-status")

    async def close(self) -> None:
        for task in (self._status_task, self._sync_task):
            if task is not None:
                task.cancel()
        for task in (self._status_task, self._sync_task):
            if task is not None:
                with suppress(asyncio.CancelledError):
                    await task
        await self.client.disconnect()

    async def ensure_connected(self) -> None:
        if self.client.is_connected:
            return
        async with self._connect_lock:
            if not self.client.is_connected:
                await self.client.connect()

    async def status(self) -> dict[str, Any]:
        status = await self._call(lambda: self.client.status())
        payload = self._status_payload(status)
        self._last_status = payload
        return payload

    async def sessions(self) -> list[dict[str, Any]]:
        values = await self._call(lambda: self.client.list_all_sessions())
        return [
            {"id": item.id, "files": item.files, "size": item.size_bytes, "bookmarks": item.bookmarks}
            for item in values
        ]

    async def settings(self) -> dict[str, Any]:
        mode = await self._call(lambda: self.client.mode())
        autodel = await self._call(lambda: self.client.auto_delete_days())
        brightness = await self._call(lambda: self.client.brightness())
        log = await self._call(lambda: self.client.log_mode())
        return {"mode": mode, "autodel": "off" if autodel is None else autodel, "brightness": brightness, "log": log}

    async def update_setting(self, key: str, value: Any) -> dict[str, Any]:
        if key == "mode":
            return {"mode": await self._call(lambda: self.client.set_mode(str(value)))}
        if key == "autodel":
            days = None if value == "off" else int(value)
            saved = await self._call(lambda: self.client.set_auto_delete_days(days))
            return {"autodel": "off" if saved is None else saved}
        if key == "brightness":
            return {"brightness": await self._call(lambda: self.client.set_brightness(int(value)))}
        if key == "log":
            return {"log": await self._call(lambda: self.client.set_log_mode(str(value)))}
        raise ValueError(f"unsupported setting {key!r}")

    async def start_recording(self, mode: str) -> dict[str, Any]:
        session = await self._call(lambda: self.client.start_recording(mode))
        await self._broadcast({"type": "recording", "action": "started", "session": session})
        return {"session": session}

    async def stop_recording(self) -> dict[str, Any]:
        result = await self._call(lambda: self.client.stop_recording())
        await self._broadcast({"type": "recording", "action": "stopped", "data": result})
        return result

    async def pause_recording(self) -> None:
        await self._call(lambda: self.client.pause_recording())

    async def resume_recording(self) -> None:
        await self._call(lambda: self.client.resume_recording())

    async def bookmark(self) -> dict[str, Any]:
        value = await self._call(lambda: self.client.bookmark())
        return {"offset": value.offset_seconds}

    async def delete_session(self, value: str) -> None:
        await self._call(lambda: self.client.delete_session(session_id(value), confirm=True))

    async def start_sync(self, value: str, *, start_file: str | None, delete_after: bool) -> dict[str, Any]:
        sid = session_id(value)
        if start_file is not None:
            chunk_name(start_file)
        async with self._sync_lock:
            if self._sync_task is not None and not self._sync_task.done():
                raise RuntimeError("another session download is already active")
            self._sync = {"active": True, "session": sid, "files": 0, "bytes": 0, "filename": None, "error": None}
            self._sync_task = asyncio.create_task(
                self._sync_worker(sid, start_file=start_file, delete_after=delete_after),
                name=f"clip-web-sync-{sid}",
            )
        await self._broadcast({"type": "sync", "data": self._sync})
        return dict(self._sync)

    async def sync_state(self) -> dict[str, Any]:
        return dict(self._sync)

    async def network_state(self) -> dict[str, Any]:
        return dict(self._network)

    async def switch_to_wifi(self, *, timeout: float) -> dict[str, Any]:
        """Perform the device/host handoff requested by the local web page."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if self._sync_task is not None and not self._sync_task.done():
            raise RuntimeError("wait for the active download to finish before switching transport")
        async with self._handoff_lock:
            if self._network["transport"] == "udp":
                return dict(self._network)
            if self._sync_task is not None and not self._sync_task.done():
                raise RuntimeError("wait for the active download to finish before switching transport")
            self._network["switching"] = True
            self._network.pop("error", None)
            await self._broadcast({"type": "network", "data": dict(self._network)})
            old_client = self.client
            try:
                if self._pending_access_point is None:
                    self._pending_access_point = await old_client.start_wifi()
                access_point = self._pending_access_point
                self._network.update({"ssid": access_point.ssid, "host": access_point.host, "port": access_point.port})
                await self._broadcast({"type": "network", "data": dict(self._network)})
                handoff: WifiHandoff = await handoff_to_wifi(
                    old_client, access_point=access_point, timeout=timeout
                )
                self.client = handoff.client
                self._pending_access_point = None
                self._network = {
                    "transport": "udp",
                    "switching": False,
                    "ssid": handoff.access_point.ssid,
                    "host": handoff.access_point.host,
                    "port": handoff.access_point.port,
                    "backend": handoff.host_connection.backend,
                    "interface": handoff.host_connection.interface,
                }
                await old_client.disconnect()
            except Exception as exc:
                self._network.update({"switching": False, "error": str(exc)})
                await self._broadcast({"type": "network", "data": dict(self._network)})
                raise
            await self._broadcast({"type": "network", "data": dict(self._network)})
            return dict(self._network)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)
        self._subscribers.add(queue)
        if self._last_status is not None:
            queue.put_nowait({"type": "status", "data": self._last_status})
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    async def _call(self, operation):
        async with self._handoff_lock:
            await self.ensure_connected()
            try:
                return await operation()
            except (ConnectionError, CommandTimeoutError):
                # A command timeout is intentionally terminal for a transport
                # connection because the protocol has no request id.  The next
                # request starts from a clean reconnect.
                with suppress(Exception):
                    await self.client.disconnect()
                raise

    async def _sync_worker(self, sid: str, *, start_file: str | None, delete_after: bool) -> None:
        try:
            def progress(filename: str, received: int, total: int) -> None:
                self._sync.update({"files": len(self._sync.get("completed", [])), "bytes": received, "filename": filename, "file_bytes": total})
                asyncio.create_task(self._broadcast({"type": "sync", "data": dict(self._sync)}))

            result: DownloadResult = await self._call(
                lambda: self.client.download_session(
                    sid, self.config.recordings_dir, start_file=start_file, progress=progress
                )
            )
            self._sync.update(
                {
                    "active": False,
                    "files": len(result.files),
                    "bytes": sum(item.size_bytes for item in result.files),
                    "output_dir": result.output_dir,
                    "completed": [item.name for item in result.files],
                }
            )
            if delete_after:
                await self._call(lambda: self.client.delete_session(sid, confirm=True))
                self._sync["deleted"] = True
            await self._broadcast({"type": "sync", "data": dict(self._sync)})
        except asyncio.CancelledError:
            self._sync.update({"active": False, "error": "canceled"})
            await self._broadcast({"type": "sync", "data": dict(self._sync)})
            raise
        except Exception as exc:
            self._sync.update({"active": False, "error": str(exc)})
            await self._broadcast({"type": "sync", "data": dict(self._sync)})

    async def _status_loop(self) -> None:
        while True:
            try:
                payload = await self.status()
                self._last_error = None
                await self._broadcast({"type": "status", "data": payload})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                message = str(exc)
                if message != self._last_error:
                    self._last_error = message
                    await self._broadcast({"type": "connection", "connected": False, "error": message})
            await asyncio.sleep(self.config.poll_interval)

    async def _broadcast(self, message: dict[str, Any]) -> None:
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with suppress(asyncio.QueueFull):
                    queue.put_nowait(message)

    def _status_payload(self, status: Status) -> dict[str, Any]:
        return {
            "state": status.state,
            "recording": status.recording,
            "session": status.session_id,
            "duration": status.duration_seconds,
            "battery": status.battery_percent,
            "charging": status.charging,
            "temperature": status.temperature_c,
            "voltage": status.voltage_mv,
            "mode": status.mode,
            "bitrate": status.bitrate,
            "free_space": status.free_space_mb,
            "device": status.device_name,
            "sync": dict(self._sync),
            "network": dict(self._network),
        }


def create_app(service: WebService):
    """Create the optional FastAPI application without importing it at SDK import time."""
    try:
        from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
        from fastapi.responses import FileResponse
    except ImportError as exc:
        raise RuntimeError("web support requires: pip install 'respeaker-clip-sdk[web]'") from exc

    @asynccontextmanager
    async def lifespan(_app):
        await service.start()
        try:
            yield
        finally:
            await service.close()

    app = FastAPI(title="reSpeaker Clip", version="0.1.0", lifespan=lifespan)

    def fail(exc: Exception):
        status = 409 if isinstance(exc, (ValueError, RuntimeError)) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/api/status")
    async def api_status():
        try:
            return {"ok": True, "data": await service.status()}
        except Exception as exc:
            fail(exc)

    @app.get("/api/sessions")
    async def api_sessions():
        try:
            return {"ok": True, "data": await service.sessions()}
        except Exception as exc:
            fail(exc)

    @app.get("/api/settings")
    async def api_settings():
        try:
            return {"ok": True, "data": await service.settings()}
        except Exception as exc:
            fail(exc)

    @app.put("/api/settings")
    async def api_settings_update(update: dict[str, Any]):
        try:
            return {"ok": True, "data": await service.update_setting(str(update["key"]), update["value"])}
        except Exception as exc:
            fail(exc)

    @app.post("/api/record/start")
    async def api_record_start(request: dict[str, Any]):
        try:
            return {"ok": True, "data": await service.start_recording(str(request.get("mode", "enhanced")))}
        except Exception as exc:
            fail(exc)

    @app.post("/api/record/stop")
    async def api_record_stop():
        try:
            return {"ok": True, "data": await service.stop_recording()}
        except Exception as exc:
            fail(exc)

    @app.post("/api/record/pause")
    async def api_record_pause():
        try:
            await service.pause_recording()
            return {"ok": True}
        except Exception as exc:
            fail(exc)

    @app.post("/api/record/resume")
    async def api_record_resume():
        try:
            await service.resume_recording()
            return {"ok": True}
        except Exception as exc:
            fail(exc)

    @app.post("/api/record/bookmark")
    async def api_record_bookmark():
        try:
            return {"ok": True, "data": await service.bookmark()}
        except Exception as exc:
            fail(exc)

    @app.post("/api/sync/{value}", status_code=202)
    async def api_sync(value: str, request: dict[str, Any]):
        try:
            start_file = request.get("start_file")
            if start_file is not None and not isinstance(start_file, str):
                raise ValueError("start_file must be a string")
            return {"ok": True, "data": await service.start_sync(value, start_file=start_file, delete_after=bool(request.get("delete_after", False)))}
        except Exception as exc:
            fail(exc)

    @app.get("/api/sync")
    async def api_sync_state():
        return {"ok": True, "data": await service.sync_state()}

    @app.get("/api/network")
    async def api_network_state():
        return {"ok": True, "data": await service.network_state()}

    @app.post("/api/network/wifi")
    async def api_network_wifi(request: dict[str, Any]):
        try:
            timeout = float(request.get("timeout", 30.0))
            return {"ok": True, "data": await service.switch_to_wifi(timeout=timeout)}
        except Exception as exc:
            fail(exc)

    @app.delete("/api/sessions/{value}")
    async def api_session_delete(value: str, confirm: bool = False):
        if not confirm:
            raise HTTPException(status_code=400, detail="pass confirm=true to delete a session")
        try:
            await service.delete_session(value)
            return {"ok": True}
        except Exception as exc:
            fail(exc)

    @app.websocket("/ws")
    async def websocket(websocket):
        await websocket.accept()
        queue = service.subscribe()
        sender = asyncio.create_task(_websocket_sender(websocket, queue))
        try:
            while True:
                # No arbitrary AT-command bridge: REST routes provide a
                # constrained, validated public control surface.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            with suppress(asyncio.CancelledError):
                await sender
            service.unsubscribe(queue)

    return app


async def _websocket_sender(websocket, queue: asyncio.Queue[dict[str, Any]]) -> None:
    while True:
        await websocket.send_json(await queue.get())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local web interface for reSpeaker Clip")
    parser.add_argument("--bind", default="127.0.0.1", help="web server bind address (default: loopback only)")
    parser.add_argument("--port", type=int, default=5000, help="web server port")
    parser.add_argument("--transport", choices=("ble", "udp"), default="ble")
    parser.add_argument("--address", help="BLE address; omit to scan by name")
    parser.add_argument("--name", default="Clip", help="BLE name substring when scanning")
    parser.add_argument("--device-host", default="192.168.4.1", help="Clip Wi-Fi AP IP address")
    parser.add_argument("--device-port", type=int, default=8089, help="Clip Wi-Fi UDP port")
    parser.add_argument("--recordings-dir", type=Path, default=Path("recordings"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        import uvicorn
        from .. import BleTransport, UdpTransport
    except ImportError:
        print("clip.web requires: pip install 'respeaker-clip-sdk[web]' (add ,ble for BLE)")
        return 1
    transport = (
        BleTransport(address=args.address, name=args.name)
        if args.transport == "ble"
        else UdpTransport(host=args.device_host, port=args.device_port)
    )
    service = WebService(ClipClient(transport), WebConfig(args.recordings_dir))
    try:
        app = create_app(service)
    except RuntimeError as exc:
        print(f"clip.web: {exc}")
        return 1
    print(f"Clip web UI: http://{args.bind}:{args.port}")
    if args.bind not in ("127.0.0.1", "::1", "localhost"):
        print("Warning: device controls are exposed on the network; use a trusted network or reverse-proxy authentication.")
    uvicorn.run(app, host=args.bind, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
