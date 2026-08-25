#!/usr/bin/env python3
"""
Generate combined playback files for distance-based audio testing.

Creates a single WAV file that includes the corpus repeated at each
distance with beep prompts and silence gaps for auto-splitting.

Output:
  corpus/
    test_combined.wav    # ~21 min, with beep prompts between distances
    distances.json       # Timing metadata for auto-split

Usage:
    python gen_test_audio.py
"""

import json
import math
import wave
from pathlib import Path

CORPUS_DIR = Path(__file__).parent.parent / "corpus"

DISTANCES = [0.5, 1, 2, 3]
MOVE_TIME_SEC = 15     # Time to move between distances (after beep)
SILENCE_START_SEC = 3  # Leading silence
SAMPLE_RATE = 16000

# Corpus playback order per distance
CORPUS_FILES = ["full_zh.wav", "full_en.wav", "full_digits.wav"]
CORPUS_GAP_SEC = 2     # Gap between corpus files


def read_wav_samples(path):
    """Read WAV file, return (raw_bytes, sample_rate)."""
    with wave.open(str(path), 'rb') as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    return raw, sr


def make_silence(duration_sec, sample_rate):
    """Generate silence as raw bytes (16-bit mono)."""
    n = int(sample_rate * duration_sec)
    return b'\x00\x00' * n


def make_beep(freq_hz, duration_sec, sample_rate, amplitude=20000):
    """Generate a beep tone as raw bytes (16-bit mono).

    Returns (raw_bytes, duration_sec).
    """
    n = int(sample_rate * duration_sec)
    samples = bytearray()
    for i in range(n):
        t = i / sample_rate
        # Envelope: fade in/out over 50ms to avoid clicks
        env = 1.0
        fade = int(0.05 * sample_rate)
        if i < fade:
            env = i / fade
        elif i > n - fade:
            env = (n - i) / fade
        val = int(amplitude * env * math.sin(2 * math.pi * freq_hz * t))
        samples.extend(val.to_bytes(2, signed=True, byteorder='little'))
    return bytes(samples), duration_sec


def make_beep_prompt(distance_m, sample_rate):
    """Generate a voice-like beep prompt for a distance.

    Pattern: [beep×count] where count = distance × 2 (0.5m=1, 1m=2, 2m=4, 3m=6)
    Each beep: 800Hz, 200ms, 150ms gap between beeps.
    Then 1s silence before corpus starts.
    """
    count = max(1, int(distance_m * 2))
    beep_dur = 0.2
    beep_gap = 0.15
    freq = 880  # A5 note, clear and distinct

    prompt = bytearray()
    for i in range(count):
        beep, _ = make_beep(freq, beep_dur, sample_rate, amplitude=22000)
        prompt.extend(beep)
        if i < count - 1:
            prompt.extend(make_silence(beep_gap, sample_rate))

    # 1s pause after beeps
    prompt.extend(make_silence(1.0, sample_rate))
    total_dur = count * beep_dur + (count - 1) * beep_gap + 1.0
    return bytes(prompt), total_dur


def generate_combined():
    """Generate combined test audio with beep prompts."""
    # Load corpus files
    corpus_data = []
    for fname in CORPUS_FILES:
        path = CORPUS_DIR / fname
        if not path.exists():
            print(f"ERROR: {path} not found. Run gen_corpus.py first.")
            return
        raw, sr = read_wav_samples(path)
        duration = len(raw) // 2 / sr
        corpus_data.append((raw, sr, duration, fname))
        print(f"  {fname}: {duration:.1f}s")

    # Verify all same sample rate
    sr = corpus_data[0][1]
    for _, s, _, _ in corpus_data:
        assert s == sr, f"Sample rate mismatch: {sr} vs {s}"

    # Build timing info
    timing = {
        "sample_rate": sr,
        "distances": DISTANCES,
        "move_time_sec": MOVE_TIME_SEC,
        "corpus_files": CORPUS_FILES,
        "segments": [],
    }

    # Build combined audio
    # Pattern: [beep] [move_time] [corpus] [beep] [move_time] [corpus] ...
    combined = bytearray()
    offset_sec = 0.0

    # Leading silence
    combined.extend(make_silence(SILENCE_START_SEC, sr))
    offset_sec += SILENCE_START_SEC

    for i, dist in enumerate(DISTANCES):
        # First distance: no beep, start immediately
        # Later distances: beep prompt + move time
        if i > 0:
            prompt, prompt_dur = make_beep_prompt(dist, sr)
            combined.extend(prompt)
            offset_sec += prompt_dur

            combined.extend(make_silence(MOVE_TIME_SEC, sr))
            offset_sec += MOVE_TIME_SEC

        seg = {
            "distance_m": dist,
            "start_sec": round(offset_sec, 1),
            "prompt_beeps": int(dist * 2),
            "corpus_segments": [],
        }

        # Play all corpus files for this distance
        for j, (raw, _, dur, fname) in enumerate(corpus_data):
            seg["corpus_segments"].append({
                "file": fname,
                "start_sec": round(offset_sec, 1),
                "duration_sec": round(dur, 1),
            })
            combined.extend(raw)
            offset_sec += dur

            # Gap between corpus files
            if j < len(corpus_data) - 1:
                combined.extend(make_silence(CORPUS_GAP_SEC, sr))
                offset_sec += CORPUS_GAP_SEC

        seg["end_sec"] = round(offset_sec, 1)
        seg["duration_sec"] = round(seg["end_sec"] - seg["start_sec"], 1)
        timing["segments"].append(seg)

    timing["total_duration_sec"] = round(offset_sec, 1)

    # Write combined WAV
    out_path = CORPUS_DIR / "test_combined.wav"
    with wave.open(str(out_path), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(combined))

    size_kb = len(combined) / 1024
    print(f"\n  Output: {out_path.name} ({size_kb:.0f} KB, {offset_sec:.0f}s / {offset_sec/60:.1f}min)")

    # Write timing metadata
    timing_path = CORPUS_DIR / "distances.json"
    with open(timing_path, 'w') as f:
        json.dump(timing, f, indent=2)

    print(f"  Timing: {timing_path.name}")
    print(f"\n  Segments (beep = move to distance):")
    for seg in timing["segments"]:
        beeps = seg.get('prompt_beeps', '?')
        print(f"    {seg['distance_m']:3.1f}m: {seg['start_sec']:>7.1f}s - {seg['end_sec']:>7.1f}s "
              f"({seg['duration_sec']:.0f}s)  beep x{beeps}")
    print(f"\n  Beep guide:")
    print(f"    x1 beep  = 0.5m")
    print(f"    x2 beeps = 1m")
    print(f"    x4 beeps = 2m")
    print(f"    x6 beeps = 3m")

    return timing


if __name__ == "__main__":
    print("Generating combined test audio with beep prompts...\n")
    generate_combined()
    print("\nDone!")
