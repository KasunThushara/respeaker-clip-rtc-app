# Audio and DSP

Audio is implemented in `applications/clip/src/audio.c`; inspect its current
Kconfig use before changing quality, latency, or CPU assumptions.

## Modes

| Mode | Channels | Processing | Opus rate |
|---|---:|---|---:|
| `normal` | 2 | stereo pass-through | `CONFIG_CLIP_NORMAL_BITRATE` per channel |
| `enhanced` | 1 | delay-aligned dual-mic merge, Speex noise suppression/dereverb, integer AGC, limiter | `CONFIG_CLIP_ENHANCED_BITRATE` |

Mode is selected by `AT+MODE` or `AT+START=<mode>`. There is no supported
runtime AT control for individual DSP parameters. Keep audio tuning in firmware
config and validate recordings rather than adding stale command wrappers.

## Segmentation and transfer

Audio encodes 20 ms frames and writes length-prefixed raw Opus packets to each
chunk. Segments are shorter while a transfer is active
(`CONFIG_CLIP_AUDIO_SEGMENT_DURATION_SYNC`) and longer otherwise
(`CONFIG_CLIP_AUDIO_SEGMENT_DURATION_NO_SYNC`). A pause/resume creates a new
logical chunk in the same session.

`dmic_read()` timeouts have recovery logic. Treat new timeout warnings as a
timing/storage/interrupt regression until measured; do not mask them with a
blind retry loop.
