# Power and battery behavior

Use `CLAUDE.md` and current source for measured values; current depends on image,
BLE state, SD state, and the physical measurement point.

## Required distinctions

- `AT+POWEROFF` calls the Clip power-off event and enters PMIC ship mode. It is
  not a substitute for testing nRF SYSTEM OFF or peripheral leakage.
- Debug UART console is a material idle-current contributor. The `production`
  snippet disables console/UART log backend; use it for power validation.
- SD low power is an explicit lifecycle: FATFS unmount, disk deinit, SPI4
  runtime suspend, CS low, then LDO2 off. FS logging can keep SD active.
- Main/radio DCDC and `CONFIG_NRF70_QSPI_LOW_POWER` are part of the low-power
  configuration. Do not regress them while changing unrelated Kconfig.

## Battery model

`battery.c` uses the nRF fuel-gauge library, a 240 mAh model, and a persisted
state record in settings. The display percent is monotonic within a charge or
discharge phase to avoid 1% visual bounce; charging and discharging have
different monotonic directions. Persist fuel-gauge state before reboot/power
events and whenever the displayed SoC changes.

## Validate changes

1. Test debug and production separately.
2. Confirm `AT+LOG=off` before idle-current checks.
3. Wait beyond `CONFIG_CLIP_SD_IDLE_DELAY_MS` and confirm SD/LDO2/SPI4 state.
4. Check BLE advertising, Wi-Fi off, USB detached, and OLED state explicitly.
5. Record rail, voltage, fixture, firmware image, and elapsed idle time with
   every power number.
