"""
BLE Client for reSpeaker Clip device.

Provides low-level BLE connection management and AT command communication.

Architecture:
- Notification handler (background thread) → Queue → send_command (async)
- Properly decouples receiving and sending
"""

import asyncio
import json
import threading
from typing import Optional
from collections import deque

try:
    from bleak import BleakClient, BleakScanner
    from bleak.exc import BleakError
except ImportError:
    raise ImportError(
        "bleak is required. Install with: pip install bleak"
    )

from .exceptions import (
    ConnectionError,
    TimeoutError,
    ResponseError,
)


# BLE UUIDs
SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
CMD_RECV_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
RESP_SEND_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
FILE_DATA_UUID = "6E400004-B5A3-F393-E0A9-E50E24DCCA9E"
AUDIO_VIS_UUID = "6E400005-B5A3-F393-E0A9-E50E24DCCA9E"

# Binary frame types (matching transport_ble.c)
FRAME_DATA          = 0x01
FRAME_FILE_START    = 0x10
FRAME_FILE_END      = 0x11
FRAME_TRANSFER_DONE = 0x12

# Device discovery filter
# Device name format: "Clip XXXX" where XXXX is last 4 hex digits of chip ID
DEVICE_NAME_FILTER = "Clip"

# Timeouts (seconds)
CONNECT_TIMEOUT = 10.0
COMMAND_TIMEOUT = 10.0


class ClipDevice:
    """
    BLE client for reSpeaker Clip device.

    Uses a Queue-based architecture to properly handle cross-thread
    communication between WinRT background notifications and asyncio.
    """

    def __init__(self, address: Optional[str] = None, name_filter: str = DEVICE_NAME_FILTER, debug: bool = False):
        self.address = address
        self.name_filter = name_filter
        self.client: Optional[BleakClient] = None
        self._connected = False
        self._debug = debug  # Enable/disable debug logging
        self._device_name = None  # Store device name when discovered

        # Message queue for receiving notifications
        self._response_queue: Optional[asyncio.Queue] = None

        # Buffer for assembling multi-packet responses
        self._response_buffer = bytearray()
        self._buffer_lock = threading.Lock()

        # Event loop reference for thread-safe queue puts
        self._loop = None

        # Optional callback for unsolicited events (e.g. state_change, wifi, usb, ble)
        # Signature: callback(event: dict) -> None
        # Events: {"event":"state","state":"RECORDING",...}
        #         {"event":"mark","session":"...","mark_count":N}
        #         {"event":"ble","status":"connected"|"disconnected"}
        #         {"event":"wifi","status":"on"|"off"}
        #         {"event":"usb","status":"on"|"off"}
        self.event_callback = None

        # File transfer state
        self._downloading = False
        self._session_files = {}  # {filename: bytes}
        self._current_file_data = bytearray()
        self._current_filename = None
        self._current_file_total = 0  # Total size of current file (from FILE_START frame)
        self._transfer_complete = False
        self._canceled = False
        self._file_lock = threading.Lock()

        # Audio visualization state
        self._audio_vis_callback = None  # Callback for audio visualization data
        self._audio_vis_data = bytearray()  # Buffer for audio vis data

    async def connect(self, timeout: float = CONNECT_TIMEOUT, sync_time: bool = True, lazy_device_name: bool = False) -> None:
        """Connect to the device.

        Args:
            timeout: Connection timeout in seconds
            sync_time: If True, automatically sync device time after connection (default: True)
            lazy_device_name: If True, skip AT+DEVICE? query (useful when recording is active)
        """
        if self._connected:
            return

        # Get event loop and create queue
        self._loop = asyncio.get_running_loop()
        self._response_queue = asyncio.Queue()

        if self.address is None:
            device = await BleakScanner.find_device_by_filter(
                lambda d, _: d.name and self.name_filter in d.name
            )
            if device is None:
                raise ConnectionError(f"Device '{self.name_filter}' not found")
            self.address = device.address
            self._device_name = device.name

        self.client = BleakClient(self.address, timeout=timeout)

        try:
            await self.client.connect()
            if self._debug:
                print(f"[connect] Connected to device, is_connected={self.client.is_connected}")

            await self.client.start_notify(RESP_SEND_UUID, self._notification_handler)
            if self._debug:
                print(f"[connect] Response notifications enabled, is_connected={self.client.is_connected}")

            await self.client.start_notify(FILE_DATA_UUID, self._file_data_handler)
            if self._debug:
                print(f"[connect] File data notifications enabled, is_connected={self.client.is_connected}")

            await self.client.start_notify(AUDIO_VIS_UUID, self._audio_vis_handler)
            if self._debug:
                print(f"[connect] Audio vis notifications enabled, is_connected={self.client.is_connected}")

            await asyncio.sleep(0.2)
            self._connected = True
            if self._debug:
                print(f"[connect] Connection complete, _connected={self._connected}, client.is_connected={self.client.is_connected}")

            # Automatically sync time after connection
            if sync_time:
                try:
                    import time
                    current_time = int(time.time())
                    await self.send_command(f"AT+TIME={current_time}", timeout=5.0)
                    if self._debug:
                        print(f"[connect] Time synchronized: {current_time}")
                    # Delay after TIME command to avoid interfering with audio encoding
                    await asyncio.sleep(0.2)
                except Exception as e:
                    if self._debug:
                        print(f"[connect] Time sync failed (non-fatal): {e}")
                    # Time sync failure is not fatal - device can still work with old time

            # Get device name if not already discovered (skip if lazy_device_name=True)
            if not lazy_device_name and self._device_name is None:
                try:
                    resp = await self.send_command("AT+DEVICE?", timeout=5.0)
                    self._device_name = resp.get("device", "Unknown_Device")
                    if self._debug:
                        print(f"[connect] Device name: {self._device_name}")
                except Exception as e:
                    if self._debug:
                        print(f"[connect] Get device name failed (non-fatal): {e}")
                    self._device_name = "Unknown_Device"

        except BleakError as e:
            raise ConnectionError(f"Connection failed: {e}")

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if not self._connected:
            return

        if self.client and self.client.is_connected:
            await self.client.stop_notify(RESP_SEND_UUID)
            await self.client.stop_notify(FILE_DATA_UUID)
            await self.client.stop_notify(AUDIO_VIS_UUID)
            await self.client.disconnect()

        self._connected = False
        self._loop = None
        self._response_queue = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._connected and self.client is not None and self.client.is_connected

    @property
    def device_name(self) -> Optional[str]:
        """Get the device name (if discovered)."""
        return self._device_name

    async def send_command(self, command: str, timeout: float = COMMAND_TIMEOUT) -> dict:
        """
        Send an AT command and wait for response.

        Uses asyncio.Queue to receive responses from the background
        notification handler, properly decoupling send and receive.

        Note: Automatically filters out state_change event notifications
        and waits for the actual command response.
        """
        if self._debug:
            print(f"[send_command] _connected={self._connected}, client={self.client is not None}, client.is_connected={self.client.is_connected if self.client else 'N/A'}")

        if not self.is_connected:
            if self._debug:
                print(f"[send_command] Connection check failed: _connected={self._connected}, client={self.client is not None}, is_connected={self.client.is_connected if self.client else 'N/A'}")
            raise ConnectionError("Not connected")

        if self._response_queue is None:
            raise ConnectionError("Queue not initialized - not connected?")

        # Clear any stale responses from the queue and buffer before sending new command
        while True:
            try:
                stale = self._response_queue.get_nowait()
                if self._debug:
                    print(f"[send_command] Discarding stale response: {stale[:50] if len(stale) > 50 else stale}")
            except asyncio.QueueEmpty:
                break

        with self._buffer_lock:
            self._response_buffer.clear()

        # Send command
        if self._debug:
            print(f"[send_command] Sending: {command}")
        await self.client.write_gatt_char(CMD_RECV_UUID, command.encode('utf-8'))

        # Wait for response from queue (with timeout)
        # Filter out state_change events - wait for actual command response
        start_time = asyncio.get_event_loop().time()
        while True:
            try:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    raise TimeoutError(f"No response to: {command}")

                response_data = await asyncio.wait_for(
                    self._response_queue.get(),
                    timeout=timeout - elapsed
                )
                if self._debug:
                    print(f"[send_command] Received response: {response_data[:100]}")

                # Parse JSON to check if it's an event notification
                try:
                    response = json.loads(response_data)

                    # Check if this is an unsolicited event notification
                    # Events have an "event" key at top level
                    if isinstance(response, dict) and 'event' in response:
                        if self.event_callback:
                            self.event_callback(response)
                        elif self._debug:
                            print(f"[send_command] Event: {response}, waiting for command response")
                        continue  # Skip events, wait for actual command response

                    # Not a state_change event, this is the actual response
                    return response

                except json.JSONDecodeError as e:
                    # Invalid JSON, return as-is
                    raise ResponseError(f"Invalid JSON: {response_data}")

            except asyncio.TimeoutError:
                raise TimeoutError(f"No response to: {command}")

    def _notification_handler(self, sender, data: bytearray):
        """
        Handle notifications from response characteristic.

        Called from WinRT background thread. Puts complete responses
        into the asyncio.Queue for the main event loop to process.

        This decouples the background thread receiving notifications
        from the async tasks sending commands.
        """
        if self._debug:
            print(f"[Notification] Received {len(data)} bytes")

        with self._buffer_lock:
            self._response_buffer.extend(data)

            # Try to decode and process the buffer
            # Handle potential incomplete UTF-8 sequences at buffer boundaries
            try:
                # Try decoding - may fail if multi-byte char is split across packets
                response_str = self._response_buffer.decode('utf-8')
            except UnicodeDecodeError:
                # Incomplete UTF-8 sequence, wait for more data
                if self._debug:
                    print(f"[Notification] Incomplete UTF-8 sequence, waiting for more data")
                return

            if self._debug:
                print(f"[Notification] Data: {response_str}")

            # Try to parse and queue complete JSON objects
            try:
                parsed = json.loads(response_str)

                # Check if this is an unsolicited event - dispatch immediately
                if isinstance(parsed, dict) and 'event' in parsed:
                    if self._debug:
                        print(f"[Notification] Event: {response_str[:80]}")
                    self._response_buffer.clear()
                    if self.event_callback:
                        self.event_callback(parsed)
                    return

                # Command response - queue for send_command to pick up
                if self._debug:
                    print(f"[Notification] Complete response, queuing to event loop")
                self._response_buffer.clear()

                if self._loop and not self._loop.is_closed() and self._response_queue:
                    self._loop.call_soon_threadsafe(
                        self._response_queue.put_nowait,
                        response_str
                    )
                return

            except json.JSONDecodeError:
                # Not complete JSON yet, or multiple JSON objects
                pass

            # Try to extract complete JSON object(s) from the buffer
            # This handles cases where multiple responses are concatenated
            remaining = response_str
            processed_count = 0

            while remaining:
                try:
                    # Try to parse from current position
                    parsed = json.loads(remaining)

                    # Success - check if event or command response
                    processed_count += 1

                    if isinstance(parsed, dict) and 'event' in parsed:
                        # Unsolicited event - dispatch immediately
                        if self._debug:
                            print(f"[Notification] Event #{processed_count}")
                        if self.event_callback:
                            self.event_callback(parsed)
                    elif self._loop and not self._loop.is_closed() and self._response_queue:
                        # Command response - queue for send_command
                        if self._debug:
                            print(f"[Notification] Complete response #{processed_count}, queuing")
                        self._loop.call_soon_threadsafe(
                            self._response_queue.put_nowait,
                            remaining
                        )

                    # We've consumed the entire remaining string
                    remaining = ""
                    self._response_buffer.clear()

                except json.JSONDecodeError:
                    # Try to find a complete JSON object by brace matching
                    if not remaining.startswith('{') and not remaining.startswith('['):
                        # Skip leading non-JSON characters
                        if self._debug:
                            print(f"[Notification] Skipping non-JSON prefix: {remaining[:20]}")
                        # Find start of JSON
                        start_idx = -1
                        for i, c in enumerate(remaining):
                            if c in '{[':
                                start_idx = i
                                break
                        if start_idx >= 0:
                            remaining = remaining[start_idx:]
                            continue
                        else:
                            # No JSON found, clear buffer
                            if self._debug:
                                print(f"[Notification] No JSON found, clearing buffer")
                            self._response_buffer.clear()
                            break

                    # Find matching closing brace
                    if remaining.startswith('{'):
                        depth = 0
                        end_idx = -1
                        in_string = False
                        escape_next = False

                        for i, c in enumerate(remaining):
                            if escape_next:
                                escape_next = False
                                continue
                            if c == '\\':
                                escape_next = True
                                continue
                            if c == '"':
                                in_string = not in_string
                                continue
                            if in_string:
                                continue
                            if c == '{':
                                depth += 1
                            elif c == '}':
                                depth -= 1
                                if depth == 0:
                                    end_idx = i + 1
                                    break

                        if end_idx > 0:
                            # Extract complete JSON
                            complete_json = remaining[:end_idx]

                            # Verify it's valid
                            try:
                                parsed = json.loads(complete_json)
                            except json.JSONDecodeError:
                                # Brace-matched but still invalid (e.g. truncated
                                # UTF-8 at a BLE notification boundary). Skip.
                                if self._debug:
                                    print(f"[Notification] Skipping invalid JSON fragment")
                                remaining = remaining[end_idx:].lstrip()
                                if remaining:
                                    self._response_buffer = bytearray(remaining.encode('utf-8'))
                                else:
                                    self._response_buffer.clear()
                                continue

                            processed_count += 1

                            if isinstance(parsed, dict) and 'event' in parsed:
                                # Event - dispatch immediately
                                if self._debug:
                                    print(f"[Notification] Event #{processed_count}")
                                if self.event_callback:
                                    self.event_callback(parsed)
                            elif self._loop and not self._loop.is_closed() and self._response_queue:
                                # Command response - queue
                                if self._debug:
                                    print(f"[Notification] Complete response #{processed_count}, queuing")
                                self._loop.call_soon_threadsafe(
                                    self._response_queue.put_nowait,
                                    complete_json
                                )

                            # Continue with remaining data
                            remaining = remaining[end_idx:].lstrip()
                            if remaining:
                                # Update buffer for next iteration
                                self._response_buffer = bytearray(remaining.encode('utf-8'))
                            else:
                                self._response_buffer.clear()
                            continue
                        else:
                            # Incomplete JSON, wait for more data
                            if self._debug:
                                print(f"[Notification] Incomplete JSON, waiting for more data")
                            break

            # Update buffer if there's remaining data
            if remaining:
                self._response_buffer = bytearray(remaining.encode('utf-8'))

    def _file_data_handler(self, sender, data: bytearray):
        """Handle binary frame protocol on File Data characteristic."""
        if len(data) < 1:
            return

        frame_type = data[0]

        if frame_type == FRAME_FILE_START:
            # FILE_START: type(1) + fn_len(1) + filename(N) + file_size(4)
            if len(data) < 2:
                return
            fn_len = data[1]
            if len(data) < 2 + fn_len + 4:
                return
            filename = data[2:2 + fn_len].decode('utf-8')
            file_size = int.from_bytes(data[2 + fn_len:2 + fn_len + 4], 'little')

            if self._debug:
                print(f"[FileData] FILE_START: {filename} ({file_size} bytes)")

            with self._file_lock:
                self._current_filename = filename
                self._current_file_total = file_size
                self._current_file_data = bytearray()

        elif frame_type == FRAME_DATA:
            # DATA: type(1) + seq(2) + len(2) + data(N)
            if len(data) < 5:
                return
            data_len = int.from_bytes(data[3:5], 'little')
            payload = data[5:5 + data_len]

            with self._file_lock:
                self._current_file_data.extend(payload)

        elif frame_type == FRAME_FILE_END:
            # FILE_END: type(1) + crc32(4)
            if len(data) < 5:
                return
            expected_crc = int.from_bytes(data[1:5], 'little')

            with self._file_lock:
                import zlib
                actual_crc = zlib.crc32(bytes(self._current_file_data)) & 0xFFFFFFFF

                if self._debug:
                    match = "OK" if actual_crc == expected_crc else "MISMATCH"
                    print(f"[FileData] FILE_END: crc=0x{expected_crc:08x} {match}")

                if self._current_filename and len(self._current_file_data) > 0:
                    if actual_crc == expected_crc:
                        self._session_files[self._current_filename] = bytes(self._current_file_data)
                        if self._debug:
                            print(f"[FileData] Saved: {self._current_filename} ({len(self._current_file_data)} bytes)")
                    else:
                        print(f"[FileData] CRC mismatch for {self._current_filename}!")

                self._current_file_data = bytearray()
                self._current_filename = None

        elif frame_type == FRAME_TRANSFER_DONE:
            # TRANSFER_DONE: type(1) + sid_len(1) + session_id(N) + file_count(4)
            if len(data) < 2:
                return
            sid_len = data[1]
            file_count = 0
            if len(data) >= 2 + sid_len + 4:
                session_id = data[2:2 + sid_len].decode('utf-8') if sid_len > 0 else ""
                file_count = int.from_bytes(data[2 + sid_len:2 + sid_len + 4], 'little')
                if self._debug:
                    print(f"[FileData] TRANSFER_DONE: {session_id} ({file_count} files)")

            self._transfer_complete = True

    def _audio_vis_handler(self, sender, data: bytearray):
        """
        Handle audio visualization data notifications.

        Receives 13 bytes representing bar heights (0-10).
        Calls the registered callback with the data.
        """
        if self._debug:
            print(f"[Audio Vis] Received {len(data)} bytes: {data[:13]}")

        if self._audio_vis_callback and self._loop:
            # Schedule the async callback as a task in the event loop
            try:
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._audio_vis_callback(bytes(data)))
                )
            except Exception as e:
                if self._debug:
                    print(f"[Audio Vis] Callback error: {e}")

    def set_audio_vis_callback(self, callback):
        """
        Set callback for audio visualization data.

        Args:
            callback: Async callback function that receives bytes data
                     Signature: async def callback(data: bytes) -> None
        """
        self._audio_vis_callback = callback

    # State management methods
    def _clear_file_state(self):
        """Clear file transfer state."""
        with self._file_lock:
            self._session_files.clear()
            self._current_file_data.clear()
            self._current_filename = None
            self._current_file_total = 0
            self._transfer_complete = False
            self._canceled = False

    def get_transfer_progress(self) -> dict:
        """
        Get current file transfer progress.

        Returns a dict with:
            - current_filename: Name of file being received (or None)
            - current_file_bytes: Bytes received for current file
            - current_file_total: Total size of current file (0 if unknown)
            - completed_bytes: Total bytes of all completed files
            - total_files: Number of completed files
        """
        with self._file_lock:
            completed_bytes = sum(len(data) for data in self._session_files.values())
            return {
                "current_filename": self._current_filename,
                "current_file_bytes": len(self._current_file_data),
                "current_file_total": self._current_file_total,
                "completed_bytes": completed_bytes,
                "total_files": len(self._session_files),
            }

    async def cancel(self):
        """Cancel the current transfer."""
        self._canceled = True

    async def get_file_data(self) -> bytes:
        return b''
