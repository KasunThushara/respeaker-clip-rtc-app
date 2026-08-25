#!/usr/bin/env python3
"""
reSpeaker Clip Record Tool

Record and sync in real-time. Press SPACE to pause/resume, M to add bookmarks.

Usage:
    python tools/record.py [--mode MODE] [--duration SECONDS] [--output DIR]
"""

import asyncio
import sys
import signal
import time
import threading
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from clip import ClipDevice, ClipCommands, SessionSync
from clip.codec import convert_to_ogg_opus
from clip.utils import format_bytes, format_duration, format_speed


# ============================================================================
# Audio Visualization Display
# ============================================================================

class AudioVisualizer:
    """Display audio waveform visualization in terminal."""

    def __init__(self):
        self.bars = [0] * 13  # 13 energy history values (0-10)
        self.last_display = ""
        self.enabled = True

    def update(self, data: bytes):
        """Update energy history from BLE notification data (7 bytes packed format).

        Format: 13 values (4 bits each) packed into 7 bytes (oldest to newest).
        Byte 0: [val0:val1], Byte 1: [val2:val3], ..., Byte 5: [val10:val11]
        Byte 6: [val12:0x0]
        """
        if len(data) >= 7:
            # Unpack 7 bytes into 13 values (4 bits each)
            self.bars = []
            for i in range(6):
                byte_val = data[i]
                self.bars.append(byte_val & 0x0F)         # Low nibble
                self.bars.append((byte_val >> 4) & 0x0F)  # High nibble
            # Last byte: only low nibble is valid
            self.bars.append(data[6] & 0x0F)
            # Clamp values to 0-10 range
            self.bars = [min(10, max(0, b)) for b in self.bars]

    def render(self) -> str:
        """Render the visualization as ASCII art (energy trend: left=oldest, right=newest)."""
        if not self.enabled:
            return ""

        max_height = 10

        # Build visualization from top to bottom
        lines = []
        for level in range(max_height, 0, -1):
            line = "  "
            for height in self.bars:
                if height >= level:
                    # Different characters for different heights
                    if level >= 8:
                        line += "█"  # Full bar at top
                    elif level >= 5:
                        line += "▓"  # Medium-high
                    elif level >= 3:
                        line += "▒"  # Medium
                    else:
                        line += "░"  # Low
                else:
                    line += " "
                line += " "
            lines.append(line)

        # Add current energy level indicator (rightmost/newest)
        current_energy = self.bars[-1] if self.bars else 0
        energy_bar = "=" * current_energy + "-" * (10 - current_energy)
        lines.append(f"  [{energy_bar}] {current_energy}/10")

        return "\n".join(lines)

    def display(self, force_clear: bool = False):
        """Display the visualization (only if changed)."""
        new_display = self.render()
        if new_display != self.last_display or force_clear:
            # Clear previous visualization area
            if self.last_display:
                line_count = self.last_display.count('\n') + 1
                sys.stdout.write("\033[F\033[J" * line_count)  # Clear lines
            sys.stdout.write(new_display + "\n")
            sys.stdout.flush()
            self.last_display = new_display

    def clear(self):
        """Clear the visualization display."""
        if self.last_display:
            line_count = self.last_display.count('\n') + 1
            sys.stdout.write("\033[F\033[J" * line_count)
            sys.stdout.flush()
            self.last_display = ""


# ============================================================================
# Keyboard Listener
# ============================================================================

class KeyboardListener:
    """Non-blocking keyboard listener for space key presses."""

    def __init__(self):
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._key_queue: asyncio.Queue = None
        self._loop: asyncio.AbstractEventLoop = None

    async def start(self) -> 'KeyboardListener':
        """Start listening for keyboard input."""
        self._key_queue = asyncio.Queue()
        self._loop = asyncio.get_running_loop()
        self.running = True

        self._thread = threading.Thread(target=self._listen_thread, daemon=True)
        self._thread.start()
        return self

    def _listen_thread(self):
        """Background thread for reading keyboard input."""
        if sys.platform == 'win32':
            self._listen_windows()
        else:
            self._listen_unix()

    def _listen_windows(self):
        """Listen using msvcrt (Windows)."""
        import msvcrt

        while self.running:
            try:
                if msvcrt.kbhit():
                    ch = msvcrt.getch()
                    if ch == b' ':
                        if self._loop and not self._loop.is_closed():
                            self._loop.call_soon_threadsafe(
                                self._key_queue.put_nowait, 'space'
                            )
                    elif ch == b'm' or ch == b'M':
                        if self._loop and not self._loop.is_closed():
                            self._loop.call_soon_threadsafe(
                                self._key_queue.put_nowait, 'mark'
                            )
                    elif ch == b'q' or ch == b'Q':
                        if self._loop and not self._loop.is_closed():
                            self._loop.call_soon_threadsafe(
                                self._key_queue.put_nowait, 'quit'
                            )
                    elif ch == b'\x03':  # Ctrl+C
                        break
                else:
                    time.sleep(0.05)
            except Exception:
                break

    def _listen_unix(self):
        """Listen using termios (Unix/Linux/macOS)."""
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)
            while self.running:
                ch = sys.stdin.read(1)
                if not self.running:
                    break
                if ch == ' ':
                    if self._loop and not self._loop.is_closed():
                        self._loop.call_soon_threadsafe(
                            self._key_queue.put_nowait, 'space'
                        )
                elif ch == 'm' or ch == 'M':
                    if self._loop and not self._loop.is_closed():
                        self._loop.call_soon_threadsafe(
                            self._key_queue.put_nowait, 'mark'
                        )
                elif ch == '\x03':  # Ctrl+C
                    if self._loop and not self._loop.is_closed():
                        self._loop.call_soon_threadsafe(
                            self._key_queue.put_nowait, 'ctrl_c'
                        )
                    break
                elif ch == 'q' or ch == 'Q':
                    if self._loop and not self._loop.is_closed():
                        self._loop.call_soon_threadsafe(
                            self._key_queue.put_nowait, 'quit'
                        )
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def stop(self):
        """Stop listening."""
        self.running = False

    async def get_key(self, timeout: float = 0.1) -> Optional[str]:
        """Get key press with timeout."""
        try:
            return await asyncio.wait_for(self._key_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None


# ============================================================================
# Main Recording Function
# ============================================================================

async def record_and_sync(
    mode: str = "normal",
    duration: int = None,
    output_dir: Path = Path("recordings"),
    device_address: str = None,
    delete: bool = False,
):
    """Record and sync in real-time. Press SPACE to add bookmarks."""
    device = ClipDevice(address=device_address, debug=False)
    commands = ClipCommands(device)
    sync = SessionSync(device)

    # Display unsolicited events
    device.event_callback = lambda e: print(
        f"\n[EVENT] {e.get('event', '?')}: {e.get('state', e.get('status', ''))}"
    )

    # Audio visualizer for waveform display
    visualizer = AudioVisualizer()

    # Audio visualization callback
    async def audio_vis_callback(data: bytes):
        visualizer.update(data)

    # Helper to get device name for directory organization
    def get_device_name():
        name = device.device_name
        if name:
            # Sanitize device name for filesystem use
            # Replace spaces with underscores and remove invalid chars
            name = name.replace(' ', '_')
            name = ''.join(c for c in name if c.isalnum() or c in '_.-')
            return name
        return "Unknown_Device"

    recording = False
    session_id = None
    sync_task = None
    stop_event = asyncio.Event()
    keyboard: Optional[KeyboardListener] = None
    attach_mode = False  # Track if we attached to existing recording

    sync_start_time = time.time()
    sync_stats = {'file_count': 0, 'total_bytes': 0, 'last_filename': ''}
    bookmark_count = 0

    def progress_callback(filename: str, file_count: int, total_size: int):
        sync_stats['last_filename'] = filename
        sync_stats['file_count'] = file_count
        sync_stats['total_bytes'] = total_size

    def signal_handler(sig, frame):
        print("\n\nStopping...")
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, signal_handler)
    except ValueError:
        pass

    try:
        print("=" * 60)
        print("reSpeaker Clip - Record & Sync")
        print("=" * 60)

        print("\nConnecting to device...")
        await device.connect()

        # Set up audio visualization callback
        device.set_audio_vis_callback(audio_vis_callback)

        device_name = device.device_name
        if device_name:
            print(f"Device: {device_name}")

        # Get device name for directory organization
        device_dir_name = get_device_name()
        print(f"Device directory: {device_dir_name}")

        # Get current device state
        state = await commands.get_state()
        print(f"Battery: {state.battery}%")
        print(f"Storage: {format_bytes(state.free_space * 1024 * 1024)} free")

        # Check if already recording
        if state.state == "RECORDING":
            print("\nDevice is already recording!")
            print("Attaching to existing session...")

            # Get current session from GSTAT response
            if not state.session_id:
                print("Error: No session ID in GSTAT response")
                return 1

            session_id = state.session_id
            print(f"Session ID: {session_id}")

            # Delay before next command to avoid interfering with audio encoding
            await asyncio.sleep(0.2)

            # Try to get session info for format details
            session_info = None
            try:
                session_info = await commands.get_session_info(session_id)
                channels = session_info.channels
                sample_rate = session_info.sample_rate
                mode = session_info.mode
                print(f"Format: {mode} ({'stereo' if channels == 2 else 'mono'}), {sample_rate//1000}kHz")
            except Exception:
                # Use defaults if session info not available
                channels = 2 if mode in ["normal", "stereo"] else 1
                sample_rate = 16000

            # Delay after session info to let audio encoding stabilize
            await asyncio.sleep(0.3)

            recording = True
            attach_mode = True  # Flag: we attached to existing recording

        else:
            # Not recording - start new recording
            print(f"\nStarting recording in {mode} mode...")

            # Ensure idle state before starting
            await commands.ensure_idle()

            session_id = await commands.start_recording(mode)
            print(f"Session ID: {session_id}")

            await asyncio.sleep(0.3)
            recording = True
            attach_mode = False
            session_info = None  # No pre-fetched session info

            channels = 2 if mode == "stereo" else 1
            sample_rate = 16000

        # Organize recordings by device name
        output_path = output_dir / device_dir_name / session_id
        output_path.mkdir(parents=True, exist_ok=True)

        # Save session.json immediately with format info
        import json
        session_json = {
            "session_id": session_id,
            "mode": mode,
            "channels": channels,
            "sample_rate": sample_rate,
        }
        session_json_path = output_path / "session.json"
        session_json_path.write_text(json.dumps(session_json, indent=2))

        if attach_mode:
            print(f"Syncing to: {output_path}")
            print(f"\nAttached to existing recording")
        else:
            print(f"Starting real-time sync to: {output_path}")
        print(f"\nControls:")
        print(f"  SPACE  - Pause/Resume recording")
        print(f"  M      - Add bookmark mark")
        print(f"  Q      - Stop recording")
        print(f"  Ctrl+C - Stop recording")
        print(f"\nRecording...\n")

        keyboard = await KeyboardListener().start()
        paused = False

        sync_task = asyncio.create_task(
            sync.sync(
                session_id,
                output_path,
                delete_after=delete,
                continuous=True,
                progress_callback=progress_callback,
                session_info=session_info,  # Pass pre-fetched session info to avoid redundant AT+LIST
            )
        )

        start_time = asyncio.get_event_loop().time()
        # In attach mode, use initial duration from GSTAT (already fetched above)
        # Then track locally - no need to poll GSTAT
        recording_duration = state.duration if (attach_mode and state.duration is not None) else 0.0

        while recording:
            try:
                key = await keyboard.get_key(timeout=0.1)
                if key == 'space':
                    # Toggle pause/resume
                    paused = not paused
                    if paused:
                        try:
                            await commands.pause_recording()
                            print(f"\n  [PAUSED]")
                        except Exception as e:
                            print(f"\n  [Pause failed: {e}]")
                            paused = False
                    else:
                        try:
                            await commands.resume_recording()
                            print(f"\n  [RESUMED]")
                        except Exception as e:
                            print(f"\n  [Resume failed: {e}]")
                            paused = False
                elif key == 'mark':
                    # Add bookmark
                    try:
                        bookmark = await commands.add_bookmark()
                        bookmark_count += 1
                        print(f"\n  [Mark #{bookmark_count}]")
                    except Exception as e:
                        print(f"\n  [Mark failed: {e}]")
                elif key == 'quit' or key == 'ctrl_c':
                    print("\nStopping recording...")
                    break

                await asyncio.wait_for(stop_event.wait(), timeout=0.1)
                break
            except asyncio.TimeoutError:
                pass

            # Check if sync task died due to BLE disconnect
            if sync_task.done():
                try:
                    sync_result = sync_task.result()
                except Exception as e:
                    print(f"\n\nSync stopped: {e}")
                    print("BLE connection lost, saving what we have...")
                    recording = False
                    break

            # Check BLE connection
            if not device.is_connected:
                print(f"\n\nBLE disconnected, saving what we have...")
                recording = False
                break

            elapsed = asyncio.get_event_loop().time() - start_time
            if duration and elapsed >= duration:
                print(f"\nDuration ({duration}s) reached")
                break

            # Update audio visualization display
            if not paused:
                visualizer.display()

            try:
                current_speed = sync_stats['total_bytes'] / (time.time() - sync_start_time) if (time.time() - sync_start_time) > 0 else 0
                if attach_mode:
                    # Attached mode: use local timing from initial device duration
                    state_str = "[Monitoring]" if not paused else "[Paused]   "
                    # recording_duration is the initial duration from device, add local elapsed time
                    display_duration = recording_duration + elapsed
                else:
                    state_str = "[PAUSED]" if paused else "[Recording]"
                    display_duration = elapsed  # Use sync elapsed time
                status = f"\r{state_str} {format_duration(display_duration).ljust(10)} | "
                status += f"Files: {sync_stats['file_count']} | "
                status += f"Total: {format_bytes(sync_stats['total_bytes'])} | "
                status += f"Speed: {format_speed(current_speed)} | "
                status += f"Marks: {bookmark_count}"
                print(status, end='', flush=True)
            except Exception:
                pass

        if keyboard:
            keyboard.stop()

        # Clear audio visualization display
        visualizer.clear()

        # Stop recording (same behavior for both attach and normal mode)
        print(f"\n\nStopping recording...")

        # Try to stop recording on device (may fail if BLE disconnected)
        result = None
        if device.is_connected:
            try:
                result = await commands.stop_recording()
            except Exception as e:
                print(f"  Warning: Could not stop recording on device: {e}")
                print(f"  (Recording will continue on device until timeout)")
        else:
            print(f"  Warning: BLE disconnected, could not stop recording on device")
            print(f"  (Recording will continue on device until timeout)")

        # Only wait for sync if BLE is still connected
        sync_result = None
        if device.is_connected and sync_task and not sync_task.done():
            print("Waiting for sync to complete...")
            wait_start = time.time()
            last_count = 0

            while not sync_task.done():
                await asyncio.sleep(0.3)
                elapsed = time.time() - wait_start

                # Stop waiting if BLE disconnected
                if not device.is_connected:
                    print("  BLE disconnected, stopping sync wait...")
                    break

                if elapsed > 1.0:
                    current_files = sync_stats['file_count']
                    if current_files > last_count:
                        print(f"  Progress: {sync_stats['last_filename']} ({current_files} files, {elapsed:.0f}s)", flush=True)
                        last_count = current_files
                    else:
                        print(f"  Waiting... ({current_files} files, {elapsed:.0f}s)", flush=True)

                if elapsed > 60.0:
                    print("  Timeout, stopping sync...")
                    await sync.cancel()
                    break

            try:
                if sync_task.done():
                    sync_result = sync_task.result()
                else:
                    sync_result = None
            except Exception:
                sync_result = None
        elif not device.is_connected:
            print("BLE disconnected, skipping sync wait (files will remain on device)")
            # Cancel the sync task
            if sync_task and not sync_task.done():
                try:
                    await sync.cancel()
                except Exception:
                    pass

        # Delete session from device after successful sync
        # Note: Get audio format info BEFORE deleting
        channels = 2 if mode in ["normal", "stereo"] else 1
        sample_rate = 16000
        audio_mode = mode

        # Try reading from local session.json first (authoritative, avoids race
        # with device's update_session_json truncating the file)
        local_session_json = output_path / "session.json"
        if local_session_json.exists():
            try:
                import json
                with open(local_session_json) as f:
                    local_meta = json.load(f)
                channels = local_meta.get("channels", channels)
                sample_rate = local_meta.get("sample_rate", sample_rate)
            except Exception:
                pass

        try:
            if device.is_connected:
                session_info = await commands.get_session_info(session_id)
                if session_info:
                    # Only override if device returns valid (non-zero) values
                    if session_info.channels > 0:
                        channels = session_info.channels
                    if session_info.sample_rate > 0:
                        sample_rate = session_info.sample_rate
                    if session_info.mode:
                        audio_mode = session_info.mode
        except Exception:
            pass  # Use defaults from mode/local session.json

        # Delete session from device (same for both attach and normal mode)
        if delete and device.is_connected and session_id:
            try:
                print(f"Deleting session from device: {session_id}")
                await commands.delete_session(session_id)
                print(f"  Session deleted successfully")
            except Exception as e:
                print(f"  Warning: Could not delete session: {e}")
                print(f"  (Session will remain on device)")

        duration_sec = result.get('duration', 0) if result else 0
        sync_elapsed = time.time() - sync_start_time
        avg_speed = sync_stats['total_bytes'] / sync_elapsed if sync_elapsed > 0 else 0

        merged_path = output_path / f"{session_id}.opus"
        if merged_path.exists():
            total_bytes = merged_path.stat().st_size
        else:
            total_bytes = sync_stats['total_bytes']

        bookmarks = sync_result.get('bookmarks', []) if sync_result else []

        print("\n" + "=" * 60)
        print("\n" + "=" * 60)
        print("Recording Summary")
        print("=" * 60)
        print(f"  Session: {session_id}")
        print(f"  Duration: {format_duration(duration_sec)}")

        ch_str = "stereo" if channels == 2 else "mono"
        print(f"  Format: {audio_mode} ({ch_str}), {sample_rate//1000}kHz, Opus")
        if merged_path.exists():
            print(f"  Merged file: {merged_path.name} ({format_bytes(total_bytes)})")
        print(f"  Total synced: {format_bytes(total_bytes)}")
        print(f"  Avg speed: {format_speed(avg_speed)}")
        print(f"  Bookmarks: {bookmark_count}")

        if bookmarks:
            print(f"\n  Bookmark details:")
            for bm in bookmarks[:5]:
                print(f"    {bm.offset}s")
            if len(bookmarks) > 5:
                print(f"    ... and {len(bookmarks) - 5} more")

        # Convert to OGG Opus (no dependencies!)
        if merged_path.exists() and merged_path.stat().st_size > 0:
            # Use channels/sample_rate from session_info we already fetched
            ch_str = "stereo" if channels == 2 else "mono"
            print(f"\nConverting to OGG Opus ({ch_str}, {sample_rate//1000}kHz)...")
            ogg_path = output_path / f"{session_id}.ogg"
            convert_to_ogg_opus(merged_path, ogg_path, sample_rate=sample_rate, channels=channels)
        else:
            # No merged file - check if we have individual .opus files to merge
            opus_files = list(output_path.glob("*.opus"))
            if opus_files:
                print(f"\nNo merged file found, merging {len(opus_files)} individual files...")
                merged_path = output_path / f"{session_id}.opus"
                with open(merged_path, "wb") as outfile:
                    for opus_file in sorted(opus_files, key=lambda x: x.name):
                        outfile.write(opus_file.read_bytes())
                print(f"  Created: {merged_path.name} ({format_bytes(merged_path.stat().st_size)})")

                # Now convert to OGG
                ch_str = "stereo" if channels == 2 else "mono"
                print(f"\nConverting to OGG Opus ({ch_str}, {sample_rate//1000}kHz)...")
                ogg_path = output_path / f"{session_id}.ogg"
                convert_to_ogg_opus(merged_path, ogg_path, sample_rate=sample_rate, channels=channels)
            else:
                print(f"\nNo audio files found to convert")

        print(f"\n  Location: {output_path}")
        print("=" * 60)

        return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        if keyboard:
            keyboard.stop()
        if recording and session_id:
            await commands.stop_recording()
        return 0
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        try:
            await device.disconnect()
        except Exception:
            pass


async def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="reSpeaker Clip Record & Sync Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Record and sync (stop with Ctrl+C or Q)
  python tools/record.py

  # Record in enhanced mode (mono + DSP)
  python tools/record.py --mode enhanced

  # Record for 30 seconds
  python tools/record.py --duration 30

Controls during recording:
  SPACE  - Pause/Resume recording
  M      - Add bookmark mark
  Q      - Stop recording
  Ctrl+C - Stop recording

Output files:
  {session}.opus - Raw merged Opus (device format)
  {session}.ogg  - OGG Opus (standard format, playable)
        """
    )

    parser.add_argument("--device", "-d", help="Device MAC address")
    parser.add_argument("--mode", "-m", default="normal",
                       choices=["normal", "enhanced", "stereo", "merge"],
                       help="Recording mode (default: normal)")
    parser.add_argument("--duration", "-t", type=int,
                       help="Auto-stop after N seconds (default: wait for Ctrl+C)")
    parser.add_argument("--output", "-o", type=Path, default=Path("recordings"),
                       help="Output directory (default: recordings/)")
    parser.add_argument("--delete", action="store_true",
                       help="Delete session from device after sync")

    args = parser.parse_args()

    await record_and_sync(
        mode=args.mode,
        duration=args.duration,
        output_dir=args.output,
        device_address=args.device,
        delete=args.delete,
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
