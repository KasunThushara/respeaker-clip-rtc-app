#!/usr/bin/env python3
"""
AT Command Tests for Clip

Tests AT commands via BLE connection.
Requires: bleak, asyncio
"""

import asyncio
import json
import sys
from typing import Optional, Dict, Any
from bleak import BleakClient, BleakScanner

# UUIDs - Matching the Clip BLE service
SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
CMD_RECV_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
RESP_SEND_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"


class ClipDevice:
    """Clip BLE Device Interface"""

    def __init__(self, address: str):
        self.address = address
        self.client: Optional[BleakClient] = None
        self.cmd_chr = None
        self.resp_chr = None
        self.resp_data = []

    async def connect(self):
        """Connect to the device"""
        self.client = BleakClient(self.address)
        await self.client.connect()
        print(f"Connected to {self.address}")

        # Get service and characteristics
        services = self.client.services
        for service in services:
            print(f"Service: {service.uuid}")
            for char in service.characteristics:
                print(f"  Characteristic: {char.uuid}, properties: {char.properties}")

        # Find command and response characteristics
        for service in services:
            if str(service.uuid).lower() == SERVICE_UUID.lower():
                for char in service.characteristics:
                    if str(char.uuid).lower() == CMD_RECV_UUID.lower():
                        self.cmd_chr = char
                    elif str(char.uuid).lower() == RESP_SEND_UUID.lower():
                        self.resp_chr = char
                        # Subscribe to notifications
                        await self.client.start_notify(char.uuid, self._resp_notification)
                        print(f"Subscribed to response notifications")

        if not self.cmd_chr or not self.resp_chr:
            raise Exception("Could not find required characteristics")

    def _resp_notification(self, sender, data):
        """Handle notification from response characteristic"""
        try:
            text = data.decode('utf-8').strip()
            print(f"Notification: {text}")
            self.resp_data.append(text)
        except Exception as e:
            print(f"Notification error: {e}")

    async def disconnect(self):
        """Disconnect from the device"""
        if self.client:
            await self.client.disconnect()
            print("Disconnected")

    async def send_command(self, cmd: str) -> Dict[str, Any]:
        """
        Send AT command and get response

        Args:
            cmd: AT command string (e.g., "AT+GSTAT")

        Returns:
            Parsed JSON response
        """
        if not self.client or not self.client.is_connected:
            raise Exception("Not connected")

        # Clear previous response data
        self.resp_data = []

        # Send command
        print(f"Sending: {cmd}")
        await self.client.write_gatt_char(self.cmd_chr.uuid, cmd.encode())

        # Wait for response (with timeout)
        for _ in range(50):  # 5 seconds timeout
            await asyncio.sleep(0.1)
            if self.resp_data:
                break

        if not self.resp_data:
            return {"ok": False, "msg": "No response"}

        # Parse response
        response_text = self.resp_data[0]
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            return {"ok": False, "msg": "Invalid JSON", "raw": response_text}


def parse_response(response_str: str) -> Dict[str, Any]:
    """Parse JSON response"""
    try:
        return json.loads(response_str.strip())
    except json.JSONDecodeError:
        return {"ok": False, "msg": "Invalid JSON"}


async def test_basic_commands(device: ClipDevice):
    """Test basic AT commands"""
    print("\n=== Testing Basic Commands ===")

    # Test VERSION
    print("\n[TEST] AT+VERSION")
    response = await device.send_command("AT+VERSION")
    print(f"Response: {response}")
    assert response.get("ok") in [True, "true"], "VERSION command failed"
    assert "version" in response or "firmware" in response, "VERSION missing version info"

    # Test GSTAT
    print("\n[TEST] AT+GSTAT")
    response = await device.send_command("AT+GSTAT")
    print(f"Response: {response}")
    assert response.get("ok") in [True, "true"], "GSTAT command failed"
    data = response.get("data", response)
    assert "state" in data, "GSTAT missing state"

    print("\n✓ Basic commands test passed")


async def test_config_commands(device: ClipDevice):
    """Test configuration commands"""
    print("\n=== Testing Config Commands ===")

    # Test BITRATE GET
    print("\n[TEST] AT+BITRATE?")
    response = await device.send_command("AT+BITRATE?")
    print(f"Response: {response}")
    assert response.get("ok") in [True, "true"], "BITRATE? failed"

    # Test BITRATE SET
    print("\n[TEST] AT+BITRATE=32000")
    response = await device.send_command("AT+BITRATE=32000")
    print(f"Response: {response}")
    assert response.get("ok") in [True, "true"], "BITRATE=32000 failed"

    # Test COMPLEXITY
    print("\n[TEST] AT+COMPLEXITY=5")
    response = await device.send_command("AT+COMPLEXITY=5")
    print(f"Response: {response}")
    assert response.get("ok") in [True, "true"], "COMPLEXITY=5 failed"

    print("\n✓ Config commands test passed")


async def test_invalid_commands(device: ClipDevice):
    """Test invalid commands"""
    print("\n=== Testing Invalid Commands ===")

    # Test invalid command
    print("\n[TEST] AT+INVALID")
    response = await device.send_command("AT+INVALID")
    print(f"Response: {response}")
    assert response.get("ok") in [False, "false", None], "Invalid command should fail"

    print("\n✓ Invalid commands test passed")


async def scan_for_device(name_prefix: str = "Clip") -> Optional[str]:
    """Scan for Clip device"""
    print(f"Scanning for {name_prefix}...")
    devices = await BleakScanner.discover()
    for device in devices:
        if device.name and device.name.startswith(name_prefix):
            print(f"Found: {device.name} ({device.address})")
            return device.address
    return None


async def main():
    """Main test entry point"""
    # Check arguments
    if len(sys.argv) > 1:
        address = sys.argv[1]
    else:
        # Scan for device
        address = await scan_for_device("Clip")
        if not address:
            print("No Clip device found!")
            print("Usage: python test_at_commands.py <BLE_ADDRESS>")
            sys.exit(1)

    print(f"Using device: {address}")

    # Create device interface
    device = ClipDevice(address)

    try:
        # Connect
        await device.connect()

        # Run tests
        await test_basic_commands(device)
        await test_config_commands(device)
        await test_invalid_commands(device)

        print("\n" + "="*50)
        print("All tests passed!")
        print("="*50)

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        # Disconnect
        await device.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
