# Wi-Fi AP and UDP transfer

The firmware starts Wi-Fi only through `AT+WIFI=on` while idle. It returns the
AP SSID, password, IP (`192.168.4.1`), and UDP port (`8089`). Do not hard-code
the returned SSID/password in a new client.

`AT+WIFI=off` stops the AP. Recording and Wi-Fi AP are mutually exclusive. The
AP uses the nRF7002 on 5 GHz; check host adapter and channel support before
diagnosing a transfer failure.

## UDP frames

All integer fields are little-endian.

| Frame | Value | Layout |
|---|---:|---|
| DATA | `0x01` | type, seq:u16, len:u16, payload_crc32:u32, payload |
| FILE_ACK | `0x03` | type, result (`0` OK, `1` NACK) |
| FILE_START | `0x10` | type, name length, logical name, size:u32 |
| FILE_END | `0x11` | type, full-file CRC32:u32 |
| TRANSFER_DONE | `0x12` | type, session length, session, count:u32 |
| AT response | `0x20` | type, JSON length:u16, JSON |
| Heartbeat | `0x30` | type, timestamp:u32 |

Send AT commands as a plain UDP datagram. The server learns the client address
from every datagram. Check each DATA payload CRC32; write only verified data.
After FILE_END, compare the accumulated file CRC32 and size, then send FILE_ACK.
NACK makes firmware retransmit the file.

## Host automatic handoff

The SDK can start Wi-Fi via BLE, join the AP on the host, verify `AT+GSTAT` over
UDP, and then transfer on Wi-Fi. The host backend is platform-specific:

| OS | Tool |
|---|---|
| Linux | NetworkManager `nmcli` |
| macOS | `networksetup` |
| Windows | `netsh wlan` |

The web browser cannot change host Wi-Fi; `clip.web` asks its local Python
backend to perform the handoff. Do not expose that local service without access
control.
