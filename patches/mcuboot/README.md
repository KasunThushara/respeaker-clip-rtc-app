# MCUboot Patches

This directory contains patches to be applied to the MCUboot source tree in NCS.
The patches are against **NCS v3.3.0** (`~/ncs/v3.3.0/bootloader/mcuboot`).
They are applied automatically (and idempotently) by `scripts/build_release.sh`,
which is used by CI (`.github/workflows/release.yml`) — manual application is only
needed for interactive development.

## Applying Patches (Required After Fresh NCS Install)

```sh
cd ~/ncs/v3.3.0/bootloader/mcuboot
git apply /path/to/reSpeaker_Clip/patches/mcuboot/0001-require-vbus-for-gpio-serial-recovery.patch
git apply /path/to/reSpeaker_Clip/patches/mcuboot/0002-add-oled-display-support.patch
git apply /path/to/reSpeaker_Clip/patches/mcuboot/0003-add-serial-upload-progress-hook.patch
git apply /path/to/reSpeaker_Clip/patches/mcuboot/0004-add-custom-mcumgr-commands.patch
git apply /path/to/reSpeaker_Clip/patches/mcuboot/0005-add-swap-copy-progress-hook.patch
```

To verify a patch is already applied:
```sh
cd ~/ncs/v3.3.0/bootloader/mcuboot
git status
```

## Patch Development Workflow

1. **Modify source directly** in `~/ncs/v3.3.0/bootloader/mcuboot/`
2. **Build**: `west build --build-dir build-clip --pristine --board clip/nrf5340/cpuapp applications/clip`
3. **Test**: Flash or export `dfu_application.zip`
4. **Export patches**: `git diff` from mcuboot tree → save to `patches/mcuboot/`
5. **Verify patches**: `git checkout -- .` then `git apply` each patch in order, rebuild
6. **Update this README**

---

## 0001-require-vbus-for-gpio-serial-recovery.patch

**File**: `boot/zephyr/io.c`
**Function**: `io_detect_pin()`

### Problem

The reSpeaker Clip board uses a single button (`gpio1.15`) for two purposes:
- **Short press**: user interaction (next track, toggle, etc.)
- **Long press (8s)**: hardware reset via `BOOT_SERIAL_ENTRANCE_GPIO` detect delay

MCUboot's `BOOT_SERIAL_ENTRANCE_GPIO` mode enters serial recovery when `io_detect_pin()`
returns `true` at boot. Without additional protection, **every long-press hardware reset
would enter DFU mode**, even with no USB cable connected and no intent to flash.

### Fix

The patch adds a VBUS detection check immediately after the GPIO debounce logic.
If the button is held at boot but USB is **not** connected, serial recovery is skipped
and the device boots normally.

**Logic**: `enter DFU ⟺ button held AND USB VBUS present`

### DFU Entry Methods (all still work)

| Method | Trigger | VBUS required? |
|--------|---------|----------------|
| **Button + USB** | Hold button at power-on/reset with USB connected | Yes |
| **AT+DFU** | App BLE command → `bootmode_set` + reboot | No |
| **`BOOT_SERIAL_BOOT_MODE`** | App sets retention register + reboot | No |

---

## 0002-add-oled-display-support.patch

**Files**: `boot/zephyr/CMakeLists.txt`, `boot/zephyr/Kconfig`, `boot/zephyr/main.c`, `boot/zephyr/io_display.c` (new), `boot/bootutil/src/loader.c`

### Summary

Adds OLED display support to MCUboot for showing OTA progress, status messages, and error conditions on the CH1115 display (88x48).

### What it adds

- **`io_display.c`**: Self-contained display helper using Zephyr Display API.
  - 6x12 pixel font (95 printable ASCII chars) for status text
  - Native 8x16 pixel font (95 printable ASCII chars) for boot animation
  - 24x24 OTA icon (column-major bitmap)
  - `draw_bitmap()` for column-major rendering
  - `io_display_show()` for two-line centered text
  - `io_display_show_progress()` for OTA icon + progress bar + percentage
  - `io_display_boot_animation()` for "seeed studio" boot animation with haptic feedback
- **`CONFIG_MCUBOOT_DISPLAY`**: New Kconfig option (selects I2C, depends on GPIO)
- **Progress hooks** in `main.c`:
  - `mcuboot_status_change()`: Shows OTA icon + "Updating..." + 0% on swap start
  - `boot_serial_upload_progress_hook()`: Serial recovery upload progress
  - `boot_copy_progress_hook()`: Real-time progress during image copy (`boot_copy_region()`)
- **Weak hook** in `loader.c`: `boot_copy_progress_hook(total, copied)` called after each chunk

### Display states

| Condition | Display |
|-----------|---------|
| Boot | "seeed studio" animation + double vibration |
| Serial recovery (button+USB or boot mode) | "Recovery Mode" |
| OTA image swap | OTA icon + "Updating..." + progress bar + real-time % |
| Serial recovery upload | OTA icon + "Updating..." + progress bar + upload % |
| No bootable image | "Error No Image" |
| Before jumping to app | Display off |

### Requirements

- `CONFIG_DISPLAY=y`, `CONFIG_I2C=y`, `CONFIG_REGULATOR=y` in MCUboot config
- I2C2, CH1115, and `oled_reg` must be enabled in MCUboot device tree overlay

---

## 0003-add-serial-upload-progress-hook.patch

**File**: `boot/boot_serial/src/boot_serial.c`

### Summary

Adds a weak callback `boot_serial_upload_progress_hook(img_index, curr_off, img_size)` in `bs_upload()` that fires after each flash chunk is written during serial recovery uploads, and once when upload completes (`curr_off == img_size`).

### What it adds

- `__weak boot_serial_upload_progress_hook()` default no-op
- Called after `curr_off += img_chunk_len + rem_bytes` (per-chunk progress)
- Called after upload completes (100%)
- Override in `main.c` provides display updates via `io_display_show_progress()`

---

## 0004-add-custom-mcumgr-commands.patch

**Files**: `boot/zephyr/CMakeLists.txt`, `boot/zephyr/boot_serial_extension_clip.c` (new)

### Summary

Adds custom mcumgr commands for reSpeaker Clip factory reset via serial recovery:
- **Erase SD card** (group 64 / PERUSER, command 0): Powers the SD card on-demand (LDO2 `regulator_enable` → write zeros → `regulator_disable`), destroying the FAT filesystem header
- **Erase LFS partition** (group 64 / PERUSER, command 1): Erases the first 128KB (2 LittleFS blocks) of the LFS partition on external flash to destroy the superblock, forcing a clean reformat that wipes BLE bonds and settings

### Why 128KB (two blocks), not one

The LittleFS superblock metadata pair is pinned at blocks {0,1} and never relocates under wear leveling (lfs.c: "can't relocate superblock, filesystem is now frozen"). LittleFS `block_size` equals the SPI NOR erase page (64KB here), so the {0,1} pair spans the first 128KB. Erasing a single 64KB block kills block 0 but leaves block 1, from which LittleFS recovers the superblock — so the bonds survive. Two blocks destroys the whole pair; the app's `fs_mount` then fails and Zephyr auto-formats a clean LittleFS.

### Requirements

- `CONFIG_ENABLE_MGMT_PERUSER=y`
- `CONFIG_DISK_ACCESS=y`, `CONFIG_SPI_SDHC=y` (for SD card erase)
- NPM1300 LDO2 + GPIO enabled in overlay (**NOT** `regulator-boot-on`). The erase-SD command powers the card on-demand (`regulator_enable` → erase → `regulator_disable`). `regulator-boot-on` would leak a permanent +1 into the app's regulator refcount (the NPM1300 regulator init seeds refcount from the physical PMIC register via `get_enabled()`), preventing the app's SD idle-power-gating from ever turning LDO2 off.
- `&flash_vdd` enabled in overlay (external SPI flash power; `regulator-boot-on` is fine here — the app keeps flash powered anyway)

---

## 0005-add-swap-copy-progress-hook.patch

**File**: `boot/bootutil/src/loader.c`

### Summary

Adds a weak callback `boot_copy_progress_hook(total, copied)` and calls it after each
chunk inside `boot_copy_region()` — i.e. during the OTA image swap/copy from slot1 to
slot0. This is the hook the OLED display (patch 0002) overrides to render real-time
swap progress (bytes_copied / total) on the CH1115 during a firmware update.

