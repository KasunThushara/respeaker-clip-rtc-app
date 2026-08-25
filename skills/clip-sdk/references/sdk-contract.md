# SDK contract

## Package layout

- Distribution: `respeaker-clip-sdk`; import name: `clip`.
- Editable install: `cd sdk && python -m pip install -e '.[dev,ble]'`.
- Extras: `ble` installs Bleak; `web` installs FastAPI/Uvicorn. `wifi` has no
  Python dependency because it selects the host's native network utility.
- Console commands: `clip-sdk`, `clip.terminal`, `clip.sync`, `clip.record`,
  `clip.web`, and `clip.wifi`.

## Current API boundaries

- `ClipClient` serializes commands and raises `CommandError` from `msg`.
- BLE and UDP return JSON command responses independently from binary transfer
  frames.
- Session IDs are 14 digits. Protocol filenames are logical `NNNN.opus` names,
  not device paths.
- `FileReceiver` writes to a `.part` file, checks size and CRC32, and uses an
  atomic rename. UDP emits FILE_ACK only after full-file verification.

## Wi-Fi handoff

`handoff_to_wifi()` sends `AT+WIFI=on` through an existing BLE client, uses the
returned credentials to join the host OS to the Clip AP, then verifies the UDP
route with `AT+GSTAT`.

| Host OS | Native connector |
|---|---|
| Linux | NetworkManager `nmcli` |
| macOS | `networksetup` |
| Windows | `netsh wlan` |

The browser cannot join Wi-Fi directly. `clip.web` asks its local Python
backend to perform the handoff, then replaces its BLE client with a UDP client.
The Clip AP is 5 GHz; verify the host adapter and regulatory channel support.
