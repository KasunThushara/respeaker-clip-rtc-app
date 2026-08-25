# T5838 PDM Microphone Test

## Overview

This sample demonstrates PDM (Pulse Density Modulation) microphone recording on the reSpeaker Clip board.

## Hardware

- **Board**: reSpeaker Clip (nRF5340)
- **Microphone**: T5838 PDM microphone or compatible PDM microphone array

## Features

- PDM/DMIC audio recording
- 16kHz sample rate, 16-bit depth, stereo
- 5 seconds recording duration
- LED status indicators:
  - Green: Recording in progress
  - Red: Error occurred
  - Blue: Success
- Audio data output to console

## Building

From project root:
```bash
source ~/ncs/v3.3.0/zephyr/zephyr-env.sh
export ZEPHYR_EXTRA_MODULES=$(pwd)
west build --build-dir build --pristine --board clip/nrf5340/cpuapp samples/t5838
```

This sample boots under the reSpeaker Clip's custom MCUboot by default (the board
supplies the bootloader, signing, and network-core radio automatically — no
per-app `sysbuild.conf` needed). To build **without** MCUboot, add a
`sysbuild.conf` (`SB_CONFIG_BOOTLOADER_NONE=y`); see `docs/custom_app_guide.md` §7.

## Flashing

```bash
west flash --build-dir build && nrfutil device reset
```

## Running

1. Connect via serial (**921600 baud**, the Clip UART0 debug console)
2. Reset the board
3. Speak or play audio near the microphone
4. View captured audio data on console

## Output

The sample will:
1. Configure PDM microphone
2. Record 5 seconds of audio
3. Print the first 100 samples to console
4. Show LED status indicators

## Requirements

- Zephyr RTOS NCS v3.3.0
- reSpeaker Clip board with PDM microphone
