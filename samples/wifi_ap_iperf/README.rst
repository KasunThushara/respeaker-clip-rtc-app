WiFi AP + iperf Throughput Test Sample
#######################################

.. contents::
   :local:
   :depth: 2

Overview
========

This sample demonstrates how to use the nRF7002 WiFi chip on the
reSpeaker Clip board in Access Point (AP) mode combined with zperf
client for network throughput testing.

The device acts as a WiFi hotspot. After connecting a PC to the AP,
the device can run iperf tests against the PC server to measure
network throughput.

Features
========

- WiFi AP (Access Point) mode
- Auto-generated unique SSID based on chip ID (``ClipAP_XXXX``)
- WPA2-PSK security with configurable password
- Built-in DHCP server for client IP assignment
- zperf client for TCP/UDP upload testing (device -> PC)
- Shell commands for AP and zperf control

Requirements
============

- reSpeaker Clip board with nRF5340 and nRF7002
- PC with iperf/iperf2/iperf3 installed
- Serial console for shell commands

Building and Flashing
=====================

.. code-block:: bash

   # Set environment
   source ~/ncs/v3.2.1/zephyr/zephyr-env.sh
   export ZEPHYR_EXTRA_MODULES=$(pwd)

   # Build
   west build --build-dir build-wifi-ap-iperf --pristine --board clip/nrf5340/cpuapp samples/wifi_ap_iperf

   # Flash and reset
   west flash --build-dir build-wifi-ap-iperf && nrfutil device reset

Usage
=====

Test Procedure:

1. **Connect PC to the AP**

   - SSID: ``ClipAP_XXXX`` (last 4 hex of chip ID)
   - Password: ``12345678``
   - PC will get IP: 192.168.4.x (via DHCP)

2. **Start iperf server on PC**

   .. code-block:: bash

      # TCP server
      iperf -s -i 1

      # UDP server
      iperf -s -u -i 1

3. **Run zperf from device (via serial console)**

   .. code-block:: console

      # TCP upload test (device -> PC)
      zperf tcp 192.168.4.10

      # UDP upload test (device -> PC)
      zperf udp 192.168.4.10

      # With custom parameters
      zperf udp 192.168.4.10 5001 10000 10000
      #                 IP    port duration rate(kbps)

Shell Commands
--------------

Connect via serial console (921600 baud) to use commands:

WiFi AP Commands:

.. code-block:: console

   # Start AP
   wifi_ap start

   # Stop AP
   wifi_ap stop

   # Show status
   wifi_ap status

zperf Commands:

.. code-block:: console

   # UDP upload test
   zperf udp <server_ip> [port] [duration_ms] [rate_kbps]

   # TCP upload test
   zperf tcp <server_ip> [port] [duration_ms]

   # Examples:
   zperf tcp 192.168.4.10              # TCP test, default params
   zperf udp 192.168.4.10 5001 10000 5000  # UDP, 10s, 5Mbps

Configuration
=============

Key configuration options in ``prj.conf``:

- ``CONFIG_NRF70_AP_MODE=y`` - Enable WiFi AP mode
- ``CONFIG_WIFI_NM_WPA_SUPPLICANT_AP=y`` - WPA supplicant AP support
- ``CONFIG_NET_ZPERF=y`` - Enable zperf
- ``CONFIG_NET_CONFIG_MY_IPV4_ADDR="192.168.4.1"`` - AP IP address

Network Settings
----------------

+-------------------+------------------+
| Setting           | Value            |
+===================+==================+
| AP IP Address     | 192.168.4.1      |
+-------------------+------------------+
| Subnet Mask       | 255.255.255.0    |
+-------------------+------------------+
| DHCP Pool Start   | 192.168.4.10     |
+-------------------+------------------+
| Default Channel   | 6                |
+-------------------+------------------+
| Security          | WPA2-PSK         |
+-------------------+------------------+
| Default Test Port | 5001             |
+-------------------+------------------+

Serial Output Example
=====================

.. code-block:: console

   *** Booting Zephyr OS build v3.2.1-ncs1 ***
   ================================================
      reSpeaker Clip WiFi AP + iperf Sample
   ================================================

   AP SSID: ClipAP_A1B2
   AP Password: 12345678

   ==========================================
   Starting WiFi AP
   ==========================================
   SSID: ClipAP_A1B2
   Password: 12345678
   Channel: 6
   IP: 192.168.4.1
   ==========================================

   DHCP server started (pool: 192.168.4.10 - 192.168.4.100)

   AP started! Waiting for connections...

   ========================================
   Station connected: AA:BB:CC:DD:EE:FF
   ========================================
   You can now run iperf tests to this device.
   ========================================

   uart:~$ zperf tcp 192.168.4.10
   Starting TCP upload to 192.168.4.10:5001
   Duration: 10000 ms
   Make sure iperf server is running on PC:
     iperf -s -i 1

   ========================================
   TCP Upload Results:
   ========================================
     Packets sent: 12345
     Total bytes: 12345678
     Duration: 10000 ms
     Throughput: 9876 kbps (9.88 Mbps)
   ========================================

Troubleshooting
===============

AP fails to start
-----------------
- Check that nRF7002 is properly powered
- Verify antenna is connected
- Check serial output for error messages

Clients cannot connect
----------------------
- Verify password is correct (``12345678``)
- Check that client supports 2.4GHz WiFi
- Check DHCP server is running (check logs)

zperf tests fail
----------------
- Verify PC is connected to correct AP
- Check PC has received IP address (192.168.4.x)
- Make sure iperf server is running on PC before running zperf
- Try using correct port (default 5001)

Low throughput
--------------
- Move device and PC closer together
- Reduce WiFi interference
- Check for CPU/memory constraints in logs
- Try both TCP and UDP tests

References
==========

- Nordic nRF70 SoftAP Sample
- Nordic WiFi Throughput Sample
- zperf documentation in Zephyr
