# Board hardware

Read the current DTS and pinctrl files instead of copying pin numbers from old
notes:

- `boards/seeed/clip/clip_nrf5340_cpuapp.dts`
- `boards/seeed/clip/clip_nrf5340_cpunet.dts`
- `boards/seeed/clip/clip-pinctrl.dtsi`

Important labels include `pdm0` (microphones), `ch1115` (OLED), `npm1300`
(PMIC), `spi3` (external flash), `spi4` (SD), and `nrf70` (Wi-Fi). Verify both
active and sleep pinctrl before adding a pull or changing a bus: incorrect
sleep pulls can dominate idle current or back-power an unpowered peripheral.
