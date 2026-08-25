#!/usr/bin/env python3
"""
BLE Terminal for Clip

Interactive terminal for sending AT commands to Clip device via BLE.
Uses the clip SDK (ClipDevice + ClipCommands).

Usage:
    python tools/ble_terminal.py [BLE_ADDRESS]
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from clip import ClipDevice, ClipCommands


def _format_event(event: dict) -> str:
    """Format event dict for terminal display."""
    event_type = event.get('event', '')

    if event_type == 'state':
        state = event.get('state', '')
        session = event.get('session', '')
        duration = event.get('duration')
        if duration is not None:
            return f"[EVENT] State: {state} (session={session}, duration={duration}s)"
        return f"[EVENT] State: {state} (session={session})"

    elif event_type == 'mark':
        session = event.get('session', '')
        count = event.get('mark_count', 0)
        return f"[EVENT] Bookmark added (session={session}, count={count})"

    elif event_type == 'ble':
        return f"[EVENT] BLE {event.get('status', '')}"

    elif event_type == 'wifi':
        return f"[EVENT] WiFi {event.get('status', '')}"

    elif event_type == 'usb':
        return f"[EVENT] USB {event.get('status', '')}"

    return f"[EVENT] {json.dumps(event)}"


def _event_callback(event: dict):
    """Print events as they arrive (called from notification thread)."""
    print(f"\n{_format_event(event)}")
    print("clip> ", end="", flush=True)


async def interactive_mode(device: ClipDevice):
    """Interactive terminal mode using the SDK."""
    commands = ClipCommands(device)

    # Register event callback to display unsolicited events
    device.event_callback = _event_callback

    print("\n" + "=" * 50)
    print("Clip BLE Terminal - Interactive Mode")
    print("=" * 50)
    print("Commands:")
    print("  AT+<command>    - Send AT command")
    print("  START           - Alias for AT+START")
    print("  STOP            - Alias for AT+STOP")
    print("  PAUSE           - Alias for AT+PAUSE")
    print("  RESUME          - Alias for AT+RESUME")
    print("  MARK            - Alias for AT+MARK")
    print("  GSTAT           - Alias for AT+GSTAT")
    print("  VERSION         - Alias for AT+VERSION")
    print("  STATUS          - Alias for AT+GSTAT")
    print("  quit/exit       - Exit terminal")
    print("=" * 50 + "\n")

    # Show initial status
    try:
        resp = await device.send_command("AT+GSTAT")
        print(f"< {json.dumps(resp, indent=2)}")
    except Exception as e:
        print(f"Error: {e}")

    while True:
        try:
            cmd = input("clip> ").strip()

            if not cmd:
                continue

            # Handle exit commands
            if cmd.lower() in ['quit', 'exit', 'q']:
                print("Exiting...")
                break

            # Handle aliases
            cmd_upper = cmd.upper()
            if cmd_upper == "START":
                cmd = "AT+START"
            elif cmd_upper == "STOP":
                cmd = "AT+STOP"
            elif cmd_upper == "PAUSE":
                cmd = "AT+PAUSE"
            elif cmd_upper == "RESUME":
                cmd = "AT+RESUME"
            elif cmd_upper == "MARK":
                cmd = "AT+MARK"
            elif cmd_upper in ["GSTAT", "STATUS"]:
                cmd = "AT+GSTAT"
            elif cmd_upper == "VERSION":
                cmd = "AT+VERSION"

            # Add AT prefix if not present
            if not cmd.upper().startswith("AT+") and not cmd.upper().startswith("AT "):
                cmd = "AT+" + cmd

            # Send command via SDK
            print(f"> {cmd}")
            try:
                resp = await device.send_command(cmd)
                print(f"< {json.dumps(resp, indent=2)}")
            except Exception as e:
                print(f"Error: {e}")

        except EOFError:
            print("\nExiting...")
            break
        except KeyboardInterrupt:
            print("\nUse 'quit' to exit")
        except Exception as e:
            print(f"Error: {e}")


async def main():
    """Main entry point."""
    address = None

    if len(sys.argv) > 1:
        address = sys.argv[1]

    print(f"Using device: {address or 'auto-discover'}")

    device = ClipDevice(address=address)

    try:
        await device.connect()
        print(f"Device: {device.device_name}")

        await interactive_mode(device)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await device.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
