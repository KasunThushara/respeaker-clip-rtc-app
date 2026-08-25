# Custom App Development Guide for reSpeaker Clip

This guide explains how to build your own Zephyr RTOS applications for the
reSpeaker Clip — and have them **automatically boot under the platform's custom
MCUboot bootloader**, with no bootloader boilerplate of your own.

> **Audience**: developers building custom firmware for the reSpeaker Clip
> platform. The official clip app (`applications/clip/`) is one such app;
> yours can be any Zephyr application targeting `clip/nrf5340/cpuapp`.

## Overview

The reSpeaker Clip is a **platform**: it ships with a full-featured voice
recorder app, but you can write your own. The board itself provides the entire
boot/upgrade infrastructure, so a custom app is just three files:

```
my_app/
├── CMakeLists.txt
├── prj.conf
└── src/main.c
```

Build it, and you get a complete signed image that boots under the custom
MCUboot — no `sysbuild.conf`, no `sysbuild/` folder, no signing-key setup.
Everything the bootloader needs is defaulted by the board.

### What the board provides automatically

| Concern | Provided by | Where |
|---------|-------------|-------|
| Bootloader (custom MCUboot, RSA-signed, OLED, USB serial recovery) | board sysbuild Kconfig | `boards/seeed/clip/Kconfig.sysbuild` |
| Dual-image OTA (app core + network core) | board sysbuild Kconfig | same |
| Network-core BLE controller image | board sysbuild Kconfig | same |
| MCUboot config (OLED, CDC, SD erase, PMIC) + device-tree overlay | board sysbuild glue | `boards/seeed/clip/sysbuild/{mcuboot.conf,mcuboot.overlay}` |
| Network-core radio config | board sysbuild glue | `boards/seeed/clip/sysbuild/ipc_radio/prj.conf` |
| Fixed flash partition layout | board (auto-discovered) | `boards/seeed/clip/pm_static_clip_nrf5340_cpuapp.yml` |
| RSA-2048 signing key | board sysbuild Kconfig | `boards/seeed/clip/sysbuild/root-rsa-2048.pem` |
| Console UART baud (921600) | board device tree | `clip_nrf5340_cpuapp.dts` `&uart0` |

The mechanism: `boards/seeed/clip/Kconfig.sysbuild` sets every `SB_CONFIG_*`
default for the board (Zephyr auto-sources it), and the module's
`sysbuild/CMakeLists.txt` (registered via `sysbuild-cmake:` in
`zephyr/module.yml`) points the mcuboot and ipc_radio images at the board's
shared config. An app inherits all of this for free.

### Firmware Upgrade Paths

| Path | When to use | Requires |
|------|------------|----------|
| **BLE OTA** | Production wireless upgrades | Your app includes mcumgr (see [§5](#5-ble-ota-optional-recommended)) |
| **USB Serial DFU** | App won't boot, BLE is dead, recovery | USB cable + `nrfutil` (see [§6](#6-usb-serial-dfu-the-safety-net)) |
| **J-Link** | First-time flash, MCUboot update | J-Link probe + `west` (see [§4](#4-first-time-flash-j-link)) |

### Boot Flow

```
Power On
  │
  ▼
MCUboot (88KB @ 0x00000000)        ← custom, RSA-signed, OLED boot animation
  │  Verify signature of slot0 image (RSA-2048, project key)
  ▼
Application (slot0 @ 0x00016000)
```

If the image fails signature verification (or no valid image exists), MCUboot
enters **serial recovery mode** — the OLED shows "Recovery Mode" and the device
accepts firmware upload over USB.

## 1. Prerequisites

- [nRF Connect SDK (NCS) v3.3.0](https://docs.nordicsemi.com/bundle/ncs-latest/page/nrf/index.html)
- Zephyr SDK (toolchain)
- `west` (Zephyr's meta-tool)
- `nrfutil` (for serial DFU — see [§6](#6-usb-serial-dfu-the-safety-net))
- J-Link probe (for first-time flash only)

```bash
source ~/ncs/v3.3.0/zephyr/zephyr-env.sh
export ZEPHYR_EXTRA_MODULES=$(pwd)
```

> `ZEPHYR_EXTRA_MODULES` must be an **environment variable** (not `-D`),
> because Kconfig module discovery runs before CMake configuration.

## 2. Create a Custom App

The easiest way to start is to copy a sample:

```bash
cp -r samples/hello_world samples/my_app
```

A custom app needs only:

| File | Purpose |
|------|---------|
| `CMakeLists.txt` | Standard Zephyr app CMake (`find_package(Zephyr)`) |
| `prj.conf` | Your app's Kconfig |
| `src/main.c` | Your code |
| `boards/clip_nrf5340_cpuapp.overlay` | *(optional)* app-specific device-tree tweaks |

That's it — **no `sysbuild.conf`, no `sysbuild/` folder, no symlinks.** The
board supplies the bootloader, signing key, network-core image, and flash
layout automatically.

### Build

```bash
west build --build-dir build-myapp --pristine \
    --board clip/nrf5340/cpuapp samples/my_app
```

The build produces three images (sysbuild):

| Output file | Description |
|-------------|-------------|
| `build-myapp/merged.hex` | MCUboot + app core + net core (full flash) |
| `build-myapp/merged_CPUNET.hex` | Network core only |
| `build-myapp/dfu_application.zip` | BLE OTA package (app + net core) |
| `build-myapp/my_app/zephyr/zephyr.signed.bin` | Signed app image (for USB serial DFU) |

## 3. Signing Key

Every app is signed with the project's RSA-2048 key, automatically:

```
boards/seeed/clip/sysbuild/root-rsa-2048.pem
```

MCUboot verifies the signature at boot — images signed with a different key are
rejected. The board's `Kconfig.sysbuild` sets this as the default
(`$(ZEPHYR_RESPEAKER_CLIP_MODULE_DIR)/boards/seeed/clip/sysbuild/root-rsa-2048.pem`),
so you do not configure it.

> **Do NOT lose or change this key.** Devices already in the field have the
> public key baked into MCUboot — they cannot accept images signed with a
> different key without reflashing the bootloader (J-Link).

## 4. First-Time Flash (J-Link)

For a brand-new device or when updating MCUboot itself:

```bash
west flash --build-dir build-myapp && nrfutil device reset
```

> `west flash --reset` does NOT work on this board — always use
> `nrfutil device reset` after flashing.

This installs MCUboot + your app + the network core in one shot. Only needed
once — subsequent upgrades are wireless.

> If flashing fails with "debug port unavailable" / "access port protected",
> the core is asleep or locked. Recover with
> `west flash --build-dir build-myapp --recover && nrfutil device reset`.

## 5. BLE OTA (optional, recommended)

If your app needs wireless upgrade capability, add these Kconfig flags to your
`prj.conf`:

```kconfig
# BLE
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y

# MCUmgr OTA over BLE (NCS sample)
CONFIG_NCS_SAMPLE_MCUMGR_BT_OTA_DFU=y
CONFIG_MCUMGR_GRP_IMG_UPDATABLE_IMAGE_NUMBER=2
CONFIG_MCUMGR_MGMT_NOTIFICATION_HOOKS=y
CONFIG_MCUMGR_GRP_IMG_STATUS_HOOKS=y
CONFIG_MCUMGR_GRP_IMG_UPLOAD_CHECK_HOOK=y
```

Build and upload the `signed.bin` over BLE:

```sh
nrfutil install mcu-manager
nrfutil mcu-manager ble image-upload \
    --firmware build-myapp/my_app/zephyr/zephyr.signed.bin \
    --device <BLE_ADDRESS>
```

After upload, reset the device. MCUboot verifies the new image's signature and
swaps it into the primary slot on the next boot. The OLED shows an OTA progress
bar during the swap.

## 6. USB Serial DFU (the safety net)

**This always works** — even if your custom app won't boot, BLE is dead, or the
device is in a boot loop. MCUboot's serial recovery mode runs from the
bootloader partition, independent of the application.

### When to use

- Your app crashed / boot loops / won't start
- BLE OTA is not available (app doesn't include mcumgr, or BLE is broken)
- You need to flash a different app over USB without opening the device

### How to enter recovery mode

Two ways (USB connected):

- **1200 baud** (easiest — every app has it, no button): open the app's USB CDC-ACM
  port at **1200 baud** and the app reboots into recovery automatically. The clip app
  needs `AT+USB=on` over BLE first (its USB is BLE-gated); samples and custom apps
  with the default CDC (`CONFIG_CLIP_USB_DFU_DEFAULT_CDC=y`) auto-enable USB, so no
  BLE step. See [usb_dfu.md](usb_dfu.md#1200-baud-auto-trigger-app-update).
- **Button**: hold the **user button** while connecting USB. The OLED shows
  "Recovery Mode" and the device enumerates as a USB CDC serial port.

In either case the recovery CDC-ACM port has PID `0x8069` (the `0x8000` bit marks
bootloader mode; the running app uses PID `0x0069`, both Seeed VID `0x2886`).

> The VBUS gating patch ensures the **button** path only enters when USB power is
> present — a long-press reset on battery does **not** trigger DFU. The 1200-baud
> path is not VBUS-gated (VBUS is present anyway — the trigger arrives over USB).

### Reflash

```sh
# Install nrfutil mcu-manager (one-time)
nrfutil install mcu-manager

# Upload the signed image
nrfutil mcu-manager serial image-upload \
    --firmware build-myapp/my_app/zephyr/zephyr.signed.bin \
    --serial-port /dev/ttyACM1

# Reset to apply (MCUboot verifies the signature and swaps on next boot)
nrfutil mcu-manager serial reset --serial-port /dev/ttyACM1
```

> On this machine the Clip's UART0 debug console enumerates as `/dev/ttyACM1`
> (the J-Link probe is `/dev/ttyACM0`). In MCUboot serial-recovery mode the
> DFU CDC port is the same ACM device.
>
> **nrfutil docs**: <https://docs.nordicsemi.com/bundle/nrfutil/latest/page/guides/device_tools/mcu_manager_serial.html>

### MCUboot recovery features

While in recovery mode, MCUboot also exposes custom mcumgr commands:

| Command | Purpose |
|---------|---------|
| Erase SD card | Destroys the FAT filesystem (factory reset / privacy) |
| Erase settings | Destroys the LittleFS superblock (clears BLE bonds + app settings) |

These are accessible via mcumgr SMP over the same USB CDC serial port.

## 7. Deviating from the board defaults

The board defaults are a fallback — your app can override any of them:

### Building WITHOUT MCUboot (factory / RF-cert / direct-flash image)

By default every clip app boots under MCUboot. For a **factory, RF-certification,
or power-measurement image** that you flash directly over J-Link (no bootloader,
no OTA, no USB serial recovery), add a `sysbuild.conf` to the app:

```kconfig
# sysbuild.conf — build without the MCUboot bootloader
SB_CONFIG_BOOTLOADER_NONE=y            # no MCUboot (app core)
SB_CONFIG_SECURE_BOOT_NETCORE=n        # also skip b0n (network-core secure boot)
# SB_CONFIG_NETCORE_NONE=y             # optional: also drop the BLE network-core image
                                       #           (set this if the app doesn't use BLE)
```

This is exactly what the `tests/` targets do (`tests/clip`, `tests/dtm`,
`tests/wifi_radio`, `tests/re`). The result is a direct-flash image — flash it
with `west flash` and `nrfutil device reset`. There is no signature check and no
recovery mode, so keep a J-Link available.

### Other deviations

- **Different MCUboot config**: provide `my_app/sysbuild/mcuboot.conf` and/or
  `my_app/sysbuild/mcuboot.overlay`. The board's versions are skipped when your
  app supplies its own.
- **WiFi (nRF7002)**: just enable `CONFIG_WIFI=y` (+ the nRF70 driver flags) in
  your `prj.conf`. NCS adds the WiFi firmware image automatically — no
  `sysbuild.conf` change needed (see `samples/http_server`).
- **Console baud / other device-tree**: use a `boards/clip_nrf5340_cpuapp.overlay`.

## 8. Troubleshooting

### "Signature verification failed" on boot

The signing key in your build doesn't match the key in MCUboot on the device.
This should not happen with the board default key. If you overrode the key,
revert to `boards/seeed/clip/sysbuild/root-rsa-2048.pem` and reflash.

### Boot loop (MCUboot keeps restarting)

The app image is too large for the slot. Reduce features or enable size
optimizations:

```
CONFIG_SIZE_OPTIMIZATIONS_AGGRESSIVE=y
CONFIG_LTO=y
```

### "Network core access port is protected" / "debug port unavailable"

The core is asleep or locked. Recover:

```bash
west flash --build-dir build-myapp --recover && nrfutil device reset
```

### "unknown SB_CONFIG_*" variable

The Zephyr environment isn't sourced:

```bash
source ~/ncs/v3.3.0/zephyr/zephyr-env.sh
export ZEPHYR_EXTRA_MODULES=$(pwd)
```

### Can't enter recovery mode

- **Hold the button BEFORE plugging USB** — not after
- USB must be plugged in (VBUS gating — battery-only won't enter DFU)
- If the device is in deep sleep, unplug USB first, then hold button + replug
