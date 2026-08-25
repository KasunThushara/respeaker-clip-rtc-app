# OLED display

The Clip uses the CH1115 display on I2C2. Device-tree ownership is in
`boards/seeed/clip/clip_nrf5340_cpuapp.dts`; runtime code is under
`applications/clip/src/display.c` and UI modules.

Use `AT+BRIGHTNESS=<0-255>` for the supported user setting. Keep production UI
updates short and avoid synchronous I2C or full-screen redraw loops in
recording/transfer timing paths. For test firmware, follow the existing
`tests/clip` OLED test commands rather than adding application-only probes.
