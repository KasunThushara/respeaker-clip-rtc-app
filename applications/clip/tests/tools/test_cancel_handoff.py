#!/usr/bin/env python3
"""
BLE-to-WiFi transfer handoff test.

Simulates: BLE transfer → AT+CANCEL → WiFi on → UDP resume from breakpoint.

Usage:
  python tools/test_cancel_handoff.py -s SESSION_ID
  python tools/test_cancel_handoff.py -s SESSION_ID --ble-time 5
  python tools/test_cancel_handoff.py -s SESSION_ID --ble-files 2
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clip import ClipDevice, SessionSync, ClipCommands
from clip.wifi import WiFiSync
from clip.utils import format_bytes

DEFAULT_WIFI_HOST = "192.168.4.1"
DEFAULT_WIFI_PORT = 8089
DEFAULT_BLE_CANCEL_TIMEOUT = 8


def connect_wifi_ap(ssid: str, password: str, timeout: float = 20.0) -> bool:
    """Auto-connect computer to WiFi AP (Windows/Linux)."""
    import subprocess

    def run_cmd(cmd, **kwargs):
        return subprocess.run(cmd, capture_output=True, timeout=timeout,
                              encoding='utf-8', errors='replace', **kwargs)

    try:
        if sys.platform == "win32":
            # Create WLAN profile XML
            profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{password}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""
            # Write temp profile file
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
                f.write(profile_xml)
                tmp_path = f.name

            run_cmd(["netsh", "wlan", "add", "profile", f"filename={tmp_path}"])
            Path(tmp_path).unlink(missing_ok=True)

            # Connect
            result = run_cmd(["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}"])
            out = (result.stdout or "").lower()
            if "successfully" in out or "已成功" in out or result.returncode == 0:
                print(f"    Connected to {ssid}")
                time.sleep(3)
                return True
            else:
                print(f"    Connect failed: {result.stdout.strip()}")
                return False

        elif sys.platform == "linux":
            # Linux: try nmcli
            result = run_cmd(["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list"])
            ssid = None
            for line in result.stdout.splitlines():
                if "ClipAP" in line:
                    ssid = line.strip().strip(":")
                    break

            if not ssid:
                print(f"    ClipAP not found in scan")
                return False

            print(f"    Found: {ssid}")
            result = run_cmd(
                ["nmcli", "dev", "wifi", "connect", ssid, "password", password]
            )
            if result.returncode == 0:
                print(f"    Connected to {ssid}")
                time.sleep(2)
                return True
            else:
                print(f"    Connect failed: {result.stderr.strip()}")
                return False
        else:
            print(f"    Unsupported platform: {sys.platform}")
            return False

    except FileNotFoundError:
        print(f"    Network tools not available")
        return False
    except Exception as e:
        print(f"    Error: {e}")
        return False


async def ble_phase(session_id: str, output_dir: Path, ble_time: float = None, ble_files: int = None):
    """Phase 1: BLE connect, start transfer, then cancel."""
    print("=" * 60)
    print("Phase 1: BLE Transfer -> Cancel")
    print("=" * 60)

    device = ClipDevice()
    await device.connect()
    print(f"  BLE connected")

    cmds = ClipCommands(device)

    # Auto-detect session
    if not session_id:
        sessions = await cmds.list_all_sessions()
        if not sessions:
            print("  No sessions found")
            await device.disconnect()
            return None, None
        session_id = sessions[0].id
        print(f"  Auto-detected session: {session_id}")

    # Get session info
    try:
        info = await cmds.get_session_info(session_id)
        print(f"  Session: {session_id} ({info.files} files, {format_bytes(info.size)})")
    except Exception:
        print(f"  Session: {session_id}")

    # Start BLE download as task
    sync = SessionSync(device)
    session_dir = output_dir / session_id

    ble_start = time.time()
    files_received = [0]
    stop_reason = ["timeout"]

    def progress_cb(filename, file_count, total_size):
        files_received[0] = file_count
        print(f"  [{file_count}] {filename} ({format_bytes(total_size)})", flush=True)

    sync_task = asyncio.create_task(
        sync.sync(session_id, session_dir, continuous=False, force=True,
                  progress_callback=progress_cb)
    )

    cancel_timeout = ble_time or DEFAULT_BLE_CANCEL_TIMEOUT
    print(f"\n  BLE transfer started, will cancel after {cancel_timeout}s"
          + (f" or {ble_files} files" if ble_files else "")
          + "...")

    while not sync_task.done():
        elapsed = time.time() - ble_start
        if elapsed >= cancel_timeout:
            stop_reason[0] = f"timeout ({cancel_timeout}s)"
            break
        if ble_files and files_received[0] >= ble_files:
            stop_reason[0] = f"{files_received[0]} files received"
            break
        await asyncio.sleep(0.3)

    # Cancel
    print(f"\n  Canceling BLE transfer (reason: {stop_reason[0]})...")
    t0 = time.time()
    await sync.cancel()
    cancel_ms = (time.time() - t0) * 1000
    print(f"  AT+CANCEL response: {cancel_ms:.0f}ms")

    # Suppress task exception
    try:
        await asyncio.wait_for(sync_task, timeout=2.0)
    except asyncio.TimeoutError:
        pass
    except Exception:
        pass

    ble_files_synced = files_received[0]
    print(f"  BLE synced: {ble_files_synced} files")

    # Enable WiFi AP after cancel (BLE may disconnect briefly, that's OK)
    wifi_info = None
    if not args.ble_only:
        print(f"\n  Enabling WiFi AP...")
        try:
            resp = await device.send_command("AT+WIFI=on", timeout=15)
            if resp and resp.get("ok"):
                data = resp.get("data", {})
                wifi_info = {
                    "ssid": data.get("ssid", ""),
                    "password": data.get("password", ""),
                    "ip": data.get("ip", DEFAULT_WIFI_HOST),
                    "port": data.get("port", DEFAULT_WIFI_PORT),
                }
                print(f"  WiFi AP: {wifi_info['ssid']} ({wifi_info['ip']})")
        except Exception:
            # BLE disconnects during WiFi startup, query status after reconnect
            await asyncio.sleep(6)
            try:
                resp = await device.send_command("AT+WIFI?", timeout=10)
                if resp and resp.get("ok"):
                    data = resp.get("data", {})
                    wifi_info = {
                        "ssid": data.get("ssid", ""),
                        "password": data.get("password", ""),
                        "ip": data.get("ip", DEFAULT_WIFI_HOST),
                        "port": data.get("port", DEFAULT_WIFI_PORT),
                    }
                    print(f"  WiFi AP: {wifi_info['ssid']} ({wifi_info['ip']})")
            except Exception as e:
                print(f"  WiFi query failed: {e}")

    await device.disconnect()
    print(f"  BLE disconnected\n")

    return session_id, ble_files_synced, wifi_info


def wifi_phase(session_id: str, output_dir: Path, start_file: str,
               host: str = DEFAULT_WIFI_HOST, port: int = DEFAULT_WIFI_PORT):
    """Phase 2: Connect WiFi AP, resume transfer via UDP."""
    print("=" * 60)
    print("Phase 2: WiFi UDP Resume")
    print("=" * 60)

    sync = WiFiSync(host, port, timeout=120.0)

    print(f"  Connecting WiFi AP ({DEFAULT_WIFI_HOST})...")
    if not sync.connect():
        print("  WiFi connect failed! Make sure your computer is connected to ClipAP_xxxx")
        return False

    print(f"  Connected")
    print(f"  Resuming from file: {start_file}\n")

    ok = sync.download_session(
        session_id, output_dir,
        convert_ogg=False,
        start_file=start_file,
    )

    sync.disconnect()

    if ok:
        print(f"\n  WiFi sync complete!")
    else:
        print(f"\n  WiFi sync failed")
    print()
    return ok


async def main():
    global args
    import argparse
    parser = argparse.ArgumentParser(description="BLE->WiFi cancel handoff test")
    parser.add_argument("--session", "-s", help="Session ID")
    parser.add_argument("--output", "-o", type=Path, default=Path("recordings"))
    parser.add_argument("--ble-time", type=float, default=None,
                       help=f"Cancel BLE after N seconds (default: {DEFAULT_BLE_CANCEL_TIMEOUT})")
    parser.add_argument("--ble-files", type=int, default=None,
                       help="Cancel BLE after N files received")
    parser.add_argument("--ble-only", action="store_true",
                       help="Only do BLE phase (cancel and stop)")
    args = parser.parse_args()

    # Phase 1: BLE transfer + cancel
    session_id, ble_files, wifi_info = await ble_phase(
        args.session, args.output, args.ble_time, args.ble_files
    )
    if not session_id:
        return 1

    if args.ble_only:
        print("  --ble-only: stopping after BLE phase")
        return 0

    # Wait for WiFi AP to be ready
    print("  Waiting for WiFi AP to start (8s)...")
    await asyncio.sleep(8)

    # WiFi AP info from AT+WIFI=on response
    ssid = wifi_info["ssid"] if wifi_info else "ClipAP_xxxx"
    password = wifi_info["password"] if wifi_info else "12345678"
    host = wifi_info["ip"] if wifi_info else DEFAULT_WIFI_HOST
    port = wifi_info["port"] if wifi_info else DEFAULT_WIFI_PORT

    print(f"\n  >>> Connect your computer to WiFi: {ssid}")
    print(f"  >>> Password: {password}")
    input("  >>> Press Enter when connected...")

    # Determine start file
    start_file = f"{ble_files + 1:04d}.opus"
    print(f"\n  BLE synced {ble_files} files, WiFi will resume from {start_file}")

    # Phase 2: WiFi resume
    ok = wifi_phase(session_id, args.output, start_file, host, port)

    # Turn off WiFi after sync
    print("  Closing WiFi AP...")
    try:
        udp_sync = WiFiSync(host, port, timeout=5.0)
        if udp_sync.connect():
            udp_sync._send_at_command("WIFI=off")
            udp_sync.disconnect()
            print("  WiFi AP closed")
    except Exception:
        pass

    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Session: {session_id}")
    print(f"  BLE synced: {ble_files} files")
    print(f"  AT+CANCEL response: <see above>")
    print(f"  WiFi resume: {'OK' if ok else 'FAILED'}")
    print("=" * 60)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
