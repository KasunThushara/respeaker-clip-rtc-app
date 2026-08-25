"""
WiFi (UDP) transport client for reSpeaker Clip device.

Uses the CLIP UDP Transfer Protocol on port 8089.
Compatible with ClipDevice's send_command interface.

UDP Frame Protocol:
  Server->Client:
    FILE_START    0x10  type(1) + fn_len(1) + filename(N) + file_size(4)
    DATA          0x01  type(1) + seq(2) + len(2) + crc32(4) + payload(N)
    FILE_END      0x11  type(1) + crc32(4)
    TRANSFER_DONE 0x12  type(1) + sid_len(1) + session_id(N) + file_count(4)
    AT_RESP       0x20  type(1) + len(2) + response_text(N)
    HEARTBEAT     0x30  type(1) + timestamp(4)

  Client->Server:
    FILE_ACK      0x03  type(1) + result(1)  — OK(0x00) or NACK(0x01)
    AT_CMD              plain text "AT+XXX\\n"
    HEARTBEAT     0x30  type(1) + timestamp(4)

WiFi AP Configuration:
  SSID:     ClipAP_XXXX
  IP:       192.168.4.1
  UDP Port: 8089
"""

import asyncio
import binascii
import json
import socket
import struct
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Callable, Any

from .exceptions import ConnectionError, TimeoutError, ResponseError
from .codec import convert_to_ogg_opus
from .utils import format_bytes


# Frame types
UDP_FRAME_DATA          = 0x01
UDP_FRAME_FILE_ACK      = 0x03
UDP_FRAME_FILE_START    = 0x10
UDP_FRAME_FILE_END      = 0x11
UDP_FRAME_TRANSFER_DONE = 0x12
UDP_FRAME_AT_RESP       = 0x20
UDP_FRAME_HEARTBEAT     = 0x30

UDP_DATA_HEADER_SIZE = 9  # type(1) + seq(2) + len(2) + crc32(4)

DEFAULT_HOST = "192.168.4.1"
DEFAULT_PORT = 8089
HEARTBEAT_INTERVAL_S = 5.0


def _ieee_crc32(data: bytes) -> int:
    """IEEE CRC32 matching Zephyr crc32_ieee_update(0, data, len)."""
    return binascii.crc32(data) & 0xFFFFFFFF


class WiFiDevice:
    """
    WiFi (UDP) transport client with async interface compatible with ClipDevice.

    Usage:
        >>> async with WiFiDevice() as device:
        ...     resp = await device.send_command("AT+LIST")
        ...     print(resp)
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._connected = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._recv_queue: Optional[asyncio.Queue] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self, timeout: float = None) -> None:
        """Connect to the device via UDP."""
        if self._connected:
            return

        self._loop = asyncio.get_running_loop()
        self._recv_queue = asyncio.Queue()
        self._stop_event.clear()

        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.settimeout(timeout or self.timeout)
            # Send a newline to establish connection
            self._sock.sendto(b"\n", (self.host, self.port))

            # Wait for any response to confirm connectivity
            self._sock.settimeout(2.0)
            try:
                data, _ = self._sock.recvfrom(4096)
                # Got a response — device is reachable
            except socket.timeout:
                pass  # No immediate response is OK for UDP

            self._sock.settimeout(self.timeout)
            self._connected = True

            # Start background receive thread
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()

            # Start heartbeat thread
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()

        except Exception as e:
            self._connected = False
            raise ConnectionError(f"UDP connect failed: {e}")

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        self._connected = False
        self._stop_event.set()

        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()

    async def send_command(self, command: str, timeout: float = None) -> dict:
        """
        Send an AT command and wait for response.

        Compatible with ClipDevice.send_command interface.
        """
        if not self._connected:
            raise ConnectionError("Not connected")

        if not command.upper().startswith("AT"):
            command = f"AT+{command}"

        with self._lock:
            self._sock.sendto((command + "\n").encode(), (self.host, self.port))

        # Wait for AT_RESP from the receive thread
        timeout_s = timeout or self.timeout
        deadline = time.time() + timeout_s

        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                msg = await asyncio.wait_for(self._recv_queue.get(), timeout=min(remaining, 1.0))
                if isinstance(msg, dict) and msg.get("_type") == "at_resp":
                    return msg.get("data", {"ok": False, "error": "No response"})
                # Non-AT_RESP message — put it back or discard
            except asyncio.TimeoutError:
                continue

        raise TimeoutError(f"No response to: {command}")

    def _recv_loop(self):
        """Background thread that receives UDP frames and queues them."""
        while not self._stop_event.is_set() and self._connected:
            try:
                self._sock.settimeout(1.0)
                data, _ = self._sock.recvfrom(4096)
                if not data or len(data) < 1:
                    continue

                frame_type = data[0]

                if frame_type == UDP_FRAME_AT_RESP:
                    # Parse AT response
                    if len(data) >= 3:
                        resp_len = data[1] | (data[2] << 8)
                        if len(data) >= 3 + resp_len:
                            resp_text = data[3:3 + resp_len].decode('utf-8', errors='replace')
                            try:
                                resp_json = json.loads(resp_text)
                            except json.JSONDecodeError:
                                resp_json = {"ok": True, "raw": resp_text}

                            if self._loop and not self._loop.is_closed() and self._recv_queue:
                                self._loop.call_soon_threadsafe(
                                    self._recv_queue.put_nowait,
                                    {"_type": "at_resp", "data": resp_json}
                                )

                elif frame_type == UDP_FRAME_HEARTBEAT:
                    continue  # Ignore heartbeat responses

                # Other frame types are handled by WiFiSync directly

            except socket.timeout:
                continue
            except OSError:
                break  # Socket closed
            except Exception:
                continue

    def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        while not self._stop_event.is_set() and self._connected:
            try:
                time.sleep(HEARTBEAT_INTERVAL_S)
                if self._stop_event.is_set() or not self._connected:
                    break
                ts = int(time.time() * 1000) & 0xFFFFFFFF
                hb = struct.pack('<BI', UDP_FRAME_HEARTBEAT, ts)
                with self._lock:
                    if self._sock:
                        self._sock.sendto(hb, (self.host, self.port))
            except Exception:
                break


class WiFiSync:
    """
    WiFi (UDP) file synchronization.

    Provides blocking download_session() and list_sessions() methods.

    Usage:
        >>> sync = WiFiSync()
        >>> sync.connect()
        >>> sessions = sync.list_sessions()
        >>> sync.download_session("20260326120000", Path("recordings"))
        >>> sync.disconnect()
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 timeout: float = 120.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._connected = False
        self._stop_event = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Connect to the device via UDP."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(self.timeout)
            self.sock.sendto(b"\n", (self.host, self.port))
            self._connected = True
            self._stop_event.clear()

            # Start heartbeat
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()

            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from the device."""
        self._connected = False
        self._stop_event.set()
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        while not self._stop_event.is_set() and self._connected:
            try:
                time.sleep(HEARTBEAT_INTERVAL_S)
                if self._stop_event.is_set() or not self._connected:
                    break
                ts = int(time.time() * 1000) & 0xFFFFFFFF
                hb = struct.pack('<BI', UDP_FRAME_HEARTBEAT, ts)
                if self.sock:
                    self.sock.sendto(hb, (self.host, self.port))
            except Exception:
                break

    def _recv_frame(self, timeout_s: float = 5.0):
        """Receive a single UDP frame."""
        self.sock.settimeout(timeout_s)
        try:
            data, _ = self.sock.recvfrom(8192)
            return data
        except socket.timeout:
            return None
        except Exception:
            return None

    def _send_file_ack(self, ok: bool):
        """Send FILE_ACK frame."""
        result = 0x00 if ok else 0x01
        ack = struct.pack('<BB', UDP_FRAME_FILE_ACK, result)
        try:
            self.sock.sendto(ack, (self.host, self.port))
        except Exception:
            pass

    def _send_at_command(self, cmd: str) -> dict:
        """Send AT command and wait for AT_RESP."""
        if not cmd.upper().startswith("AT"):
            cmd = f"AT+{cmd}"
        self.sock.sendto((cmd + "\n").encode(), (self.host, self.port))

        for _ in range(10):
            data = self._recv_frame(2.0)
            if data is None:
                continue
            if len(data) >= 3 and data[0] == UDP_FRAME_AT_RESP:
                resp_len = data[1] | (data[2] << 8)
                if len(data) >= 3 + resp_len:
                    response = data[3:3 + resp_len].decode('utf-8', errors='replace')
                    try:
                        return json.loads(response)
                    except json.JSONDecodeError:
                        return {"ok": True, "raw": response}
            # Ignore other frames
        return {"ok": False, "error": "No response"}

    def list_sessions(self) -> List[dict]:
        """List all sessions on the device (paginated)."""
        all_sessions = []
        page = 1
        while True:
            result = self._send_at_command(f"LIST?{page}&50")
            if not result.get("ok"):
                # Fallback: try without pagination
                if page == 1:
                    result = self._send_at_command("LIST")
                    if not result.get("ok"):
                        return []
                    data = result.get("data", [])
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        return data.get("sessions", [])
                break

            data = result.get("data", {})
            if isinstance(data, dict):
                sessions = data.get("sessions", [])
            elif isinstance(data, list):
                sessions = data
            else:
                break

            all_sessions.extend(sessions)

            total = data.get("total", 0) if isinstance(data, dict) else len(sessions)
            if len(all_sessions) >= total or len(sessions) == 0:
                break
            page += 1

        return all_sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a session from the device."""
        result = self._send_at_command(f"DELETE={session_id}")
        return result.get("ok", False)

    def download_session(
        self,
        session_id: str,
        output_dir: Path,
        convert_ogg: bool = True,
        start_file: Optional[str] = None,
        delete_after: bool = False,
        progress_callback: Optional[Callable] = None,
        cancel_after: Optional[float] = None,
    ) -> bool:
        """
        Download a session via UDP.

        Args:
            session_id: Session ID to download
            output_dir: Output directory
            convert_ogg: Convert to OGG Opus after download
            start_file: Start from specific file (e.g., "0015.opus")
            delete_after: Delete session from device after successful download
            progress_callback: Optional callback(filename, file_count, total_bytes,
                          current_file_bytes, current_file_total)
            cancel_after: If set, auto-cancel download after N seconds

        Returns:
            True if any files were received
        """
        session_dir = output_dir / "Clip" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        downloaded_files = []

        # Pre-fetch session size BEFORE starting download
        # (DOWNLOAD triggers data streaming, so LIST must be sent first)
        total_files = 0
        total_bytes = 0
        try:
            info_resp = self._send_at_command(f"LIST={session_id}")
            if info_resp.get("ok"):
                info_data = info_resp.get("data", {})
                total_files = info_data.get("files", info_data.get("total", 0))
                total_bytes = info_data.get("size", 0)
        except Exception:
            pass

        # Start download (with optional start file)
        if start_file:
            result = self._send_at_command(f"DOWNLOAD={session_id}:{start_file}")
        else:
            result = self._send_at_command(f"DOWNLOAD={session_id}")

        if not result.get("ok"):
            print(f"  Error: {result.get('error', 'unknown')}")
            return False

        # Override with DOWNLOAD response if available (more accurate)
        data = result.get("data", {})
        dl_files = data.get("files", data.get("total", 0))
        dl_bytes = data.get("bytes", data.get("size", 0))
        if dl_files > 0:
            total_files = dl_files
        if dl_bytes > 0:
            total_bytes = dl_bytes

        if total_files == 0:
            print(f"  Session {session_id}: no files (may have been deleted)")
            return False

        print(f"  Session {session_id}: {total_files} file(s), {format_bytes(total_bytes)}")

        # tqdm progress bar
        pbar = None
        try:
            from tqdm import tqdm
            try:
                import colorama
                colorama.init()
            except ImportError:
                pass
            pbar = tqdm(
                total=total_bytes if isinstance(total_bytes, int) else None,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=f"[{session_id[:8]}]",
                leave=False,
                ncols=80,
            )
        except ImportError:
            pass

        # Receive state
        current_name = None
        current_data = bytearray()
        current_size = 0
        files_received = 0
        frame_count = 0
        last_progress_time = time.time()
        file_crc = 0
        last_pbar_size = 0
        received_bytes = 0  # Cumulative bytes received across all files

        # Cancel support: 'c' key or --cancel-after timer
        cancel_triggered = threading.Event()

        def _cancel_download():
            if cancel_triggered.is_set():
                return
            cancel_triggered.set()
            print(f"\n  Canceling transfer...")
            try:
                self.sock.sendto(b"AT+CANCEL\n", (self.host, self.port))
            except Exception:
                pass

        def _key_monitor():
            """Watch for 'c' keypress to cancel download (cross-platform)."""
            import sys as _sys
            if not _sys.stdin.isatty():
                return
            try:
                import msvcrt
                # Windows
                while not cancel_triggered.is_set() and self._connected:
                    if msvcrt.kbhit():
                        ch = msvcrt.getch().decode('utf-8', errors='replace')
                        if ch == 'c':
                            _cancel_download()
                            break
                    cancel_triggered.wait(0.1)
            except ImportError:
                # Linux/Mac
                import tty, termios
                fd = _sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setcbreak(fd)
                    while not cancel_triggered.is_set() and self._connected:
                        try:
                            ch = _sys.stdin.read(1)
                            if ch == 'c':
                                _cancel_download()
                                break
                        except Exception:
                            break
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)

        key_thread = threading.Thread(target=_key_monitor, daemon=True)
        key_thread.start()

        cancel_timer = None
        if cancel_after is not None:
            def _cancel_after_timeout():
                _cancel_download()
            cancel_timer = threading.Timer(cancel_after, _cancel_after_timeout)
            cancel_timer.daemon = True
            cancel_timer.start()

        if cancel_after is not None:
            print(f"  Press 'c' or wait {cancel_after}s to cancel")
        else:
            print(f"  Press 'c' to cancel")

        try:
            while True:
                data = self._recv_frame(5.0)
                if data is None:
                    elapsed = time.time() - last_progress_time
                    if elapsed > 60:
                        print(f"\n  Timeout ({frame_count} frames, {elapsed:.0f}s)")
                        return False
                    continue

                if len(data) < 1:
                    continue

                frame_type = data[0]

                # Non-file frames
                if frame_type == UDP_FRAME_AT_RESP:
                    if len(data) >= 3:
                        resp_len = data[1] | (data[2] << 8)
                        if len(data) >= 3 + resp_len:
                            resp = data[3:3 + resp_len].decode('utf-8', errors='replace')
                            print(f"  AT Response: {resp}")
                    continue

                if frame_type == UDP_FRAME_HEARTBEAT:
                    continue

                # FILE_START
                if frame_type == UDP_FRAME_FILE_START:
                    if len(data) < 3:
                        continue
                    fn_len = data[1]
                    if len(data) < 2 + fn_len + 4:
                        continue
                    filename = data[2:2 + fn_len].decode('utf-8', errors='replace')
                    file_size = struct.unpack("<I", data[2 + fn_len:2 + fn_len + 4])[0]

                    current_name = filename
                    current_size = file_size
                    current_data = bytearray()
                    file_crc = 0
                    frame_count = 0

                    if pbar is not None:
                        pbar.set_description(f"[{files_received + 1:2d}] {filename[:12]}", refresh=True)
                    else:
                        print(f"\n  <- {filename} ({format_bytes(file_size)})")
                    last_progress_time = time.time()
                    continue

                # DATA
                if frame_type == UDP_FRAME_DATA:
                    if current_name is None:
                        continue  # No active file, discard stale frames
                    if len(data) < UDP_DATA_HEADER_SIZE:
                        continue
                    seq = data[1] | (data[2] << 8)
                    data_len = data[3] | (data[4] << 8)
                    recv_crc = struct.unpack("<I", data[5:9])[0]

                    if len(data) < UDP_DATA_HEADER_SIZE + data_len:
                        continue

                    payload = data[UDP_DATA_HEADER_SIZE:UDP_DATA_HEADER_SIZE + data_len]

                    # Per-frame CRC verification
                    calc_crc = _ieee_crc32(payload)
                    if calc_crc != recv_crc:
                        continue

                    current_data.extend(payload)
                    file_crc = binascii.crc32(payload, file_crc) & 0xFFFFFFFF
                    frame_count += 1
                    last_progress_time = time.time()
                    received_bytes += len(payload)

                    # Update progress bar
                    if pbar is not None:
                        delta = received_bytes - last_pbar_size
                        if delta >= 4096:  # Update every ~4KB to reduce overhead
                            pbar.update(delta)
                            last_pbar_size = received_bytes
                    else:
                        # Progress dots fallback
                        if frame_count < 5 or len(current_data) % (64 * 1024) < data_len:
                            print(".", end="", flush=True)

                    continue

                # FILE_END
                if frame_type == UDP_FRAME_FILE_END:
                    if len(data) < 5:
                        continue
                    server_crc = struct.unpack("<I", data[1:5])[0]
                    crc_ok = (file_crc == server_crc)

                    if crc_ok:
                        self._send_file_ack(True)

                        if current_name and current_data:
                            out_file = session_dir / current_name
                            out_file.write_bytes(bytes(current_data))
                            if current_name.endswith('.opus'):
                                downloaded_files.append((current_name, out_file))
                            files_received += 1

                        # Flush remaining progress for this file
                        if pbar is not None:
                            remaining = received_bytes - last_pbar_size
                            if remaining > 0:
                                pbar.update(remaining)
                                last_pbar_size = received_bytes
                    else:
                        self._send_file_ack(False)
                        current_name = None
                        current_data = bytearray()

                    last_progress_time = time.time()
                    continue

                # TRANSFER_DONE
                if frame_type == UDP_FRAME_TRANSFER_DONE:
                    if len(data) < 2:
                        break
                    sid_len = data[1]
                    if len(data) >= 2 + sid_len + 4:
                        sess = data[2:2 + sid_len].decode('utf-8', errors='replace')
                        file_count = struct.unpack("<I", data[2 + sid_len:2 + sid_len + 4])[0]
                    break

        except socket.timeout:
            print("  Connection timeout")
        except KeyboardInterrupt:
            print("\n  Interrupted, canceling transfer...")
            try:
                self._send_at_command("CANCEL")
                # Wait for TRANSFER_DONE from device
                deadline = time.time() + 3.0
                while time.time() < deadline:
                    try:
                        data = self._recv_frame(1.0)
                        if data and len(data) >= 1 and data[0] == UDP_FRAME_TRANSFER_DONE:
                            break
                    except Exception:
                        break
            except Exception:
                pass
        except Exception as e:
            print(f"  Error: {e}")
        finally:
            if cancel_timer is not None:
                cancel_timer.cancel()
            if pbar is not None:
                pbar.close()

        # Merge opus files and convert to OGG
        if convert_ogg and downloaded_files:
            print(f"\n  Merging {len(downloaded_files)} file(s)...")
            downloaded_files.sort(key=lambda x: x[0])

            merged_data = bytearray()
            for _, filepath in downloaded_files:
                with open(filepath, 'rb') as f:
                    merged_data.extend(f.read())

            merged_opus_path = session_dir / f"{session_id}.opus"
            merged_opus_path.write_bytes(bytes(merged_data))
            print(f"    Merged: {merged_opus_path.name} ({format_bytes(len(merged_data))})")

            ogg_path = session_dir / f"{session_id}.ogg"
            print(f"    Converting to OGG...", end="", flush=True)
            if convert_to_ogg_opus(merged_opus_path, ogg_path):
                print(" OK")
            else:
                print(" Failed")

        # Delete session from device if requested
        if delete_after and files_received > 0:
            print(f"  Deleting session from device...")
            time.sleep(0.3)  # Wait for device to finish transfer cleanup
            self.delete_session(session_id)

        return files_received > 0
