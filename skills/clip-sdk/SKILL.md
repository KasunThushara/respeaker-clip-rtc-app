---
name: clip-sdk
description: Develop, test, package, or debug the standalone reSpeaker Clip Python SDK in sdk/. Use for typed AT APIs, Bleak or UDP transports, streaming downloads, CLI tools, clip.web, BLE-to-Wi-Fi handoff, package extras, console scripts, and SDK compatibility with current Clip firmware.
---

# reSpeaker Clip Python SDK

Work only in `sdk/` unless the task explicitly changes the firmware protocol.
Do not move, import, or rewrite `applications/clip/tests`; it is the legacy
tool collection retained for hardware and historical use.

## Source and compatibility rules

1. Read the current command registrations in
   `applications/clip/src/at_commands.c` before adding or changing an SDK API.
2. Treat `docs/protocol.md` and firmware source as the protocol contract; update
   both SDK and protocol documentation when the firmware contract changes.
3. Do not emulate removed legacy commands such as `BITRATE`, `COMPLEXITY`,
   `NOISE`, `AGC`, `DEREVERB`, or `PURGE`.
4. Preserve response semantics: failures use `msg`, successful payloads are
   usually under `data`, and the protocol has no request ID.

## Implementation workflow

1. Keep AT requests serialized. After a timeout, reconnect before issuing a
   new request so a late response cannot be assigned to another command.
2. Validate session IDs (`YYYYMMDDHHMMSS`) and logical chunk names
   (`NNNN.opus`) before constructing an AT command or filesystem path.
3. Stream transfer payloads to `*.part`, verify declared length and final CRC32,
   then atomically rename. Never buffer a complete recording in memory.
4. Distinguish BLE frames from UDP frames: UDP DATA has a per-frame CRC32 and
   requires FILE_ACK after full-file verification.
5. Keep optional functionality in extras: `ble`, `web`, and their console
   commands must fail clearly when an optional dependency is absent.
6. Keep the local web service loopback-only by default. Browser code requests a
   host Wi-Fi handoff; only Python may invoke `nmcli`, `networksetup`, or
   `netsh`.

## Required checks

```sh
cd sdk
pytest -q
python -m pip wheel --no-deps --wheel-dir /tmp/clip-sdk-wheel .
```

Inspect wheel metadata and console scripts after changing `pyproject.toml`.
When testing `clip.web`, install the `web` extra; add `ble` only for BLE use.
Hardware transfer and host Wi-Fi join tests are integration tests: do not claim
them successful without a real Clip and a supported 5 GHz host adapter.

## Useful commands

```sh
python -m pip install -e '.[dev,ble]'
python -m pip install -e '.[web,ble]'
clip.terminal --transport ble
clip.sync --transport udp --all
clip.web --transport ble
clip.wifi --address AA:BB:CC:DD:EE:FF
```

Read [references/sdk-contract.md](references/sdk-contract.md) for frame,
packaging, and Wi-Fi handoff details.
