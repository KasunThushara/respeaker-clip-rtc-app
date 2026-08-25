---
name: clip-dev
description: Develop, build, flash, test, or debug reSpeaker Clip firmware on the nRF5340 with NCS v3.3.0. Use for Zephyr board work, MCUboot/sysbuild, current AT commands, BLE or Wi-Fi UDP transport, SD recording storage, audio/DSP, OLED, PMIC, battery, low-power behavior, production images, and hardware tests.
---

# reSpeaker Clip firmware

Treat the checked-out source as authoritative. Read `CLAUDE.md` before changing
firmware: it contains the active NCS version, board sysbuild defaults, power
constraints, release workflow, and current hardware-test commands.

## Route the task

| Area | Source of truth | Read when needed |
|---|---|---|
| AT protocol | `applications/clip/src/at_commands.c` | `references/ble-at.md` |
| BLE/UDP transfer | `transport_ble.c`, `transport_udp.c`, `wifi_udp.c` | `references/wifi-udp.md` |
| Recording and DSP | `audio.c`, `applications/clip/Kconfig` | `references/audio.md` |
| FATFS sessions | `storage.c` | `references/storage.md` |
| Idle and power-off | `clip_event.c`, `storage.c`, `battery.c`, snippets | `references/power.md` |
| Build, flash, artifacts | `CLAUDE.md`, board `Kconfig.sysbuild` | `references/build-flash.md` |
| Python package | `sdk/` | Use the separate `clip-sdk` skill |

Keep `applications/clip/tests` intact. It is a legacy test/tool collection;
the installable SDK lives at `sdk/` and must not silently inherit legacy
commands or response shapes.

## Firmware workflow

1. Inspect `git status`; preserve unrelated worktree changes.
2. Confirm the command, Kconfig, device-tree, storage, or transport contract in
   source before editing docs or clients.
3. Keep host-visible session IDs as exactly 14 decimal digits
   `YYYYMMDDHHMMSS`; never expose physical FAT paths in the protocol.
4. Validate user-controlled command arguments before storage, path, or transfer
   access. `DOWNLOAD` only accepts `session` or `session:NNNN.opus`.
5. Build and test in proportion to the change. Flash only the image the user
   requested; `--recover` erases the device.
6. Update `docs/protocol.md` and `sdk/` whenever an AT response, command, or
   binary transfer frame changes.

## Current protocol rules

- Success is `{"ok":true,"data":...}` where `data` is command-specific.
  Failures use `{"ok":false,"msg":"..."}`; do not expect `error` or numeric
  error-code fields.
- Use `AT+GSTAT`, not `AT+STATUS?`. Current recording commands are `START`,
  `STOP`, `PAUSE`, `RESUME`, and `MARK`.
- Runtime commands for bitrate, codec complexity, AGC, noise suppression, and
  dereverb do not exist. Audio mode is `normal` or `enhanced`.
- `AT+PAIR=reset` acknowledges first, then erases SD and reboots. Do not make a
  client wait for the erase before receiving the response.
- `AT+WIFI=on` returns AP credentials; UDP uses port `8089`. A host may use BLE
  for control then switch file transfer to UDP.

## Build and flash

```sh
source ~/ncs/v3.3.0/zephyr/zephyr-env.sh
export ZEPHYR_EXTRA_MODULES="$PWD"

west build --build-dir build-clip --board clip/nrf5340/cpuapp applications/clip
west build --build-dir build-clip --pristine --board clip/nrf5340/cpuapp applications/clip
west flash --build-dir build-clip && nrfutil device reset
```

Use `--recover` only when needed: it erases both cores. Build production with
the `production` snippet; it disables console/UART logging and is required for
meaningful idle-current measurements.

## Validation checkpoints

- Build a pristine image after Kconfig, devicetree, sysbuild, or partition
  changes.
- Flash both app and network-core images when checking BLE behavior.
- For low power, test the production image with SD idle power-off and FS logging
  disabled; debug UART materially changes current.
- For storage changes, test new recording, `LIST`, `DOWNLOAD`, cancellation,
  deletion, and a power-cycle/remount path.
- For transfer changes, check BLE final CRC32 and UDP per-frame CRC32 plus
  `FILE_ACK` retransmission.
