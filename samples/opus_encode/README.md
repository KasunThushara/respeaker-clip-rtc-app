# Opus Streaming Encoder for reSpeaker Clip

Real-time audio encoding and streaming sample: captures the PDM microphone
array, encodes it with the Opus codec, and streams the compressed frames over
UART.

> This sample boots under the reSpeaker Clip's custom MCUboot by default (the
> board supplies the bootloader, signing, and network-core radio automatically —
> no per-app `sysbuild.conf` needed). To build **without** MCUboot, add a
> `sysbuild.conf` (`SB_CONFIG_BOOTLOADER_NONE=y`); see
> `docs/custom_app_guide.md` §7.

## Features

- **Real-time streaming encode**: DMIC capture → Opus encode → UART TX, no large buffer
- **Three audio modes**:
  - `mono` — single channel (left mic only)
  - `stereo` — stereo (left + right mics)
  - `merge` — averaged mono ((L + R) / 2)
- **Flow control**: start / stop / quit commands
- **Encode stats**: per-frame encode time (min / max / avg)
- **Auto-naming**: the Python receiver names output files by date/time

## Hardware

- **MCU**: nRF5340 (Cortex-M33 @ 64 MHz)
- **DMIC**: stereo PDM microphone array
- **Sample rate**: 16 kHz
- **Frame size**: 20 ms (320 samples/frame)
- **UART baud**: 921600 (board DTS default)

## Memory

- **FLASH**: ~173 KB (16.5%)
- **RAM**: ~60 KB (13.4%)
- **DMIC buffer**: 8 blocks × 1280 bytes = 10 KB

## Building

```sh
source ~/ncs/v3.3.0/zephyr/zephyr-env.sh
export ZEPHYR_EXTRA_MODULES=$(pwd)
west build --build-dir build-opus --board clip/nrf5340/cpuapp samples/opus_encode
```

## Flashing

```sh
west flash --build-dir build-opus && nrfutil device reset
```

## Usage

### Device commands (serial input)

In the serial terminal (minicom/screen/picocom), type:

| Key | Action |
|-----|--------|
| `1` | Switch to mono (left channel) |
| `2` | Switch to stereo |
| `3` | Switch to merge (L+R averaged) |
| `s` | Start recording |
| `e` | Stop recording |
| `q` | Quit |

### Python receiver

```sh
# Install dependencies
pip install pyserial opuslib

# Mono (left mic)
python3 samples/opus_encode/receive_opus.py /dev/ttyACM1 921600 . --mode mono

# Stereo
python3 samples/opus_encode/receive_opus.py /dev/ttyACM1 921600 . --mode stereo

# Merge
python3 samples/opus_encode/receive_opus.py /dev/ttyACM1 921600 . --mode merge
```

The script will:
1. Send the mode command to the device
2. Send the start command
3. Receive and decode the Opus stream
4. Stop on Ctrl+C and save a WAV file

Output filename format: `recording_YYYYMMDD_HHMMSS.wav`

## Protocol

### Header

```
>>> OPUS_STREAM_START
SAMPLE_RATE=16000
CHANNELS=1 or 2
FRAME_SIZE=320
BITRATE=24000 or 48000
>>> DATA_START
```

### Encoded frame

```
<4-hex-digit length>\n
<hex data>\n
```

Example:
```
0039
4ca7fd29c02216ac18a8d75f3f5edbcb0cb35dd54bbec791c3b3a5f2615edfceb37...
```

### End marker

```
>>> DATA_END
```

## Mode details

### Mono

- **Channels**: 1
- **Bitrate**: 24000 bps
- **Note**: left mic only
- **Use**: single-mic recording, lower bandwidth

### Stereo

- **Channels**: 2
- **Bitrate**: 48000 bps
- **Note**: full left + right data
- **Use**: stereo recording, directional info

### Merge

- **Channels**: 1
- **Bitrate**: 24000 bps
- **Note**: left + right averaged, `(L + R) / 2` with saturation
- **Use**: omnidirectional capture, reduced directionality

## Performance

Measured encode time (including processing):

| Mode | Avg time | Note |
|------|----------|------|
| mono | ~8–12 ms | left-channel extract only |
| stereo | ~11–13 ms | stereo encode |
| merge | ~11–13 ms | merge + mono encode |

Well within the 20 ms frame budget.

## Project structure

```
samples/opus_encode/
├── src/
│   └── main.c              # main application
├── CMakeLists.txt
├── prj.conf                # Zephyr Kconfig
└── receive_opus.py         # Python receiver
```

## Dependencies

- Zephyr RTOS v3.3.0 (NCS v3.3.0)
- Opus 1.5 codec library (`lib/opus/`)
- pyserial (Python)
- opuslib (Python)

## Troubleshooting

### Serial permission

```sh
sudo usermod -aG dialout $USER
# log out and back in for it to take effect
```

### Device unresponsive

```sh
nrfutil device reset
```

### Baud mismatch

The UART0 baud is set to 921600 by the board DTS default
(`boards/seeed/clip/clip_nrf5340_cpuapp.dts`, `&uart0` `current-speed`) — no
per-sample overlay is needed. To change it, edit the board DTS.

## License

Apache-2.0
