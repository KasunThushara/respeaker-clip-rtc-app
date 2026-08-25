#!/usr/bin/env python3
"""
Serial AT Command Terminal for reSpeaker Clip

Interactive terminal for testing AT commands over USB CDC serial.
Device appears as a virtual serial port when connected via USB.

Usage:
    # Auto-detect serial port:
    python tests/tools/serial_terminal.py

    # Specify port:
    python tests/tools/serial_terminal.py /dev/ttyACM0

    # Specify port and baudrate:
    python tests/tools/serial_terminal.py /dev/ttyACM0 -b 115200
"""

import sys
import os
import time
import argparse
import threading
import serial
import serial.tools.list_ports


def find_clip_port():
    """Auto-detect Clip USB CDC serial port."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        # Match by Seeed VID 0x2886
        if port.vid == 0x2886:
            return port.device
        # Also try common CDC ACM patterns
        if "ttyACM" in port.device or "CUA" in port.device.upper():
            desc = (port.description or "").lower()
            mfr = (port.manufacturer or "").lower()
            if "seeed" in mfr or "clip" in desc or "respeaker" in desc:
                return port.device
    return None


class SerialTerminal:
    """Interactive serial terminal for AT commands."""

    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False

    def connect(self) -> bool:
        """Open serial port."""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
            time.sleep(0.1)
            # Flush any stale data
            if self.ser.in_waiting:
                self.ser.read(self.ser.in_waiting)
            print(f"Connected to {self.port} @ {self.baudrate}")
            return True
        except serial.SerialException as e:
            print(f"Failed to open {self.port}: {e}")
            return False

    def disconnect(self):
        """Close serial port."""
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()

    def reader(self):
        """Background thread: read responses from device."""
        while self.running:
            try:
                if self.ser and self.ser.in_waiting:
                    data = self.ser.read(self.ser.in_waiting)
                    if data:
                        text = data.decode("utf-8", errors="replace")
                        # Print response (strip trailing newline, add prefix)
                        for line in text.strip().split("\n"):
                            if line.strip():
                                print(f"< {line}")
                else:
                    time.sleep(0.01)
            except Exception:
                break

    def send(self, cmd: str):
        """Send AT command."""
        if not self.ser or not self.ser.is_open:
            return
        line = cmd.strip()
        if not line:
            return
        # Add AT prefix if not present
        if not line.upper().startswith("AT"):
            line = "AT+" + line
        print(f"> {line}")
        self.ser.write((line + "\r\n").encode())

    def run(self):
        """Run interactive terminal."""
        self.running = True

        # Start reader thread
        rx_thread = threading.Thread(target=self.reader, daemon=True)
        rx_thread.start()

        print("Serial AT Terminal (Ctrl+C to exit)")
        print("Commands: AT+GSTAT, AT+RECORD, AT+STOP, AT+LIST, AT+MSC=on, etc.")
        print()

        try:
            while self.running:
                try:
                    line = input("> ").strip()
                except EOFError:
                    break

                if not line:
                    continue

                if line.lower() in ("exit", "quit", "q"):
                    break

                self.send(line)

                # Brief wait for response
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\nInterrupted")

        self.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Serial AT Terminal for reSpeaker Clip")
    parser.add_argument("port", nargs="?", help="Serial port (auto-detect if omitted)")
    parser.add_argument("-b", "--baudrate", type=int, default=115200,
                        help="Baud rate (default: 115200)")
    args = parser.parse_args()

    port = args.port
    if not port:
        port = find_clip_port()
        if port:
            print(f"Auto-detected: {port}")
        else:
            # Fallback
            if os.path.exists("/dev/ttyACM0"):
                port = "/dev/ttyACM0"
            elif os.path.exists("/dev/ttyUSB0"):
                port = "/dev/ttyUSB0"
            else:
                print("No serial port found. Specify port manually:")
                print(f"  {sys.argv[0]} /dev/ttyACM0")
                sys.exit(1)

    term = SerialTerminal(port, args.baudrate)
    if not term.connect():
        sys.exit(1)

    term.run()


if __name__ == "__main__":
    main()
