#!/usr/bin/env python3
"""
Audio comparison test runner for Clip vs Anker D3200.

Guided workflow:
  1. Play reference corpus from phone/speaker
  2. Record simultaneously with both devices
  3. Export recordings to this computer
  4. Run analysis

Usage:
    # Step 1: Guided test (interactive)
    python audio_test_runner.py run

    # Step 2: Analyze all recordings (after export)
    python audio_test_runner.py analyze

    # Step 3: Generate comparison report
    python audio_test_runner.py report

    # Quick: analyze + report in one step
    python audio_test_runner.py analyze --report

    # Analyze specific files only
    python audio_test_runner.py analyze --only quiet/1m

    # WER analysis (requires whisper, slower)
    python audio_test_runner.py analyze --wer

Directory structure:
    tests/results/
      {environment}/
        {distance}/
          ref_zh.wav          # Reference (from corpus)
          ref_en.wav
          ref_digits.wav
          clip_zh.opus        # Clip raw opus (before decode)
          clip_en.opus
          clip_digits.opus
          clip_zh.wav         # Decoded (auto-generated)
          clip_en.wav
          clip_digits.wav
          anker_zh.ogg        # Anker raw
          anker_en.ogg
          anker_digits.ogg
          anker_zh.wav        # Decoded (auto-generated)
          anker_en.wav
          anker_digits.wav
"""

import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).parent.parent / "results"
CORPUS_DIR = Path(__file__).parent.parent / "corpus"

# Test matrix: (environment, distances)
TEST_MATRIX = {
    "quiet":   [0.5, 1, 2, 3],
    "meeting": [0.5, 1, 2, 3],
}

# Corpus types and their reference files
CORPUS_TYPES = {
    "zh":     {"ref": "full_zh.wav",     "lang": "zh", "ref_text_file": "zh_sentences.txt"},
    "en":     {"ref": "full_en.wav",     "lang": "en", "ref_text_file": "en_sentences.txt"},
    "digits": {"ref": "full_digits.wav", "lang": "zh", "ref_text_file": "digit_sequences.txt"},
}

# Device/mode names
# clip_enhanced = merge L+R + DSP + AGC (AT+MODE=merge)
# clip_normal   = stereo, no DSP (AT+MODE=stereo)
DEVICES = ["clip_enhanced", "clip_normal", "anker"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def decode_to_wav(src: Path, dst: Path, channels: int = 1, sample_rate: int = 16000):
    """Decode audio file to 16kHz mono WAV."""
    if dst.exists() and dst.stat().st_mtime > src.stat().st_mtime:
        return  # already decoded and newer
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-ar", str(sample_rate), "-ac", str(channels),
        "-sample_fmt", "s16", str(dst)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR decoding {src}: {result.stderr[:200]}")
        return False
    print(f"  Decoded: {src.name} -> {dst.name}")
    return True


def get_duration(path: Path) -> float:
    """Get audio file duration in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def get_rms_db(path: Path) -> float:
    """Get RMS level in dBFS."""
    import numpy as np
    with wave.open(str(path), 'rb') as wf:
        n = wf.getnframes()
        raw = wf.readframes(n)
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    rms = np.sqrt(np.mean(data**2))
    if rms < 1e-10:
        return -120.0
    return 20.0 * np.log10(rms / 32768.0)

# ---------------------------------------------------------------------------
# Step 1: Guided Test Runner
# ---------------------------------------------------------------------------

def cmd_run(args):
    """Interactive guided test."""
    print("=" * 60)
    print("  Audio Comparison Test: Clip vs Anker D3200")
    print("=" * 60)

    print("""
Preparation:
  1. Charge both devices fully
  2. Prepare a phone/speaker to play reference audio
  3. Use a sound level meter APP to calibrate speaker volume
  4. Target: 65 dB(A) at 1m from speaker
  5. Place both devices side-by-side, mics facing the speaker

Reference audio files (play from phone):
""")

    for ctype, info in CORPUS_TYPES.items():
        ref = CORPUS_DIR / info["ref"]
        if ref.exists():
            dur = get_duration(ref)
            print(f"  {info['ref']:20s}  {dur:5.1f}s  [{ctype}]")
        else:
            print(f"  {info['ref']:20s}  MISSING! Run gen_corpus.py first")

    input("\nPress Enter to start testing...")

    for env, distances in TEST_MATRIX.items():
        env_label = "Quiet Room" if env == "quiet" else "Meeting Room"
        print(f"\n{'=' * 60}")
        print(f"  Environment: {env_label}")
        print(f"{'=' * 60}")

        for dist in distances:
            test_dir = RESULTS_DIR / env / f"{dist}m"
            ensure_dir(test_dir)

            print(f"\n--- {env_label} / {dist}m ---")
            print(f"  Output dir: {test_dir}")
            print(f"""
  Setup:
    1. Place both devices {dist}m from the speaker
    2. Devices side-by-side, mics toward speaker
    3. Start recording on BOTH devices
    4. Play each corpus file:
    """)

            for ctype, info in CORPUS_TYPES.items():
                ref = CORPUS_DIR / info["ref"]
                if ref.exists():
                    dur = get_duration(ref)
                    print(f"       {ctype:8s}: {info['ref']} ({dur:.0f}s)")

            print(f"""
  Recording (3 devices × 3 corpus = 9 recordings):
    Round 1 — Clip Enhanced (AT+MODE=merge):
      1. Set Clip to Enhanced mode: AT+MODE=merge
      2. Start Clip recording (button or AT+RECORD)
      3. Play: zh -> en -> digits with 3s gap between
      4. Stop Clip recording

    Round 2 — Clip Normal (AT+MODE=stereo):
      1. Set Clip to Normal mode: AT+MODE=stereo
      2. Start Clip recording
      3. Play: zh -> en -> digits with 3s gap between
      4. Stop Clip recording

    Round 3 — Anker:
      1. Start Anker recording
      2. Play: zh -> en -> digits with 3s gap between
      3. Stop Anker recording

  Export:
    - Clip:  UDP sync or SD card reader
    - Anker: WiFi export from app
    Copy files to: {test_dir}/
    Name them: clip_enhanced_zh.ogg, clip_normal_zh.ogg, anker_zh.ogg, etc.
    """)

            done = input(f"  Done with {env_label}/{dist}m? [y/N]: ").strip().lower()
            if done == 'y':
                auto_organize(test_dir)

    print(f"\n{'=' * 60}")
    print(f"  All tests complete!")
    print(f"  Next step: python audio_test_runner.py analyze --report")
    print(f"{'=' * 60}")


def auto_organize(test_dir: Path):
    """Try to auto-detect and rename recording files."""
    files = list(test_dir.iterdir())
    renamed = 0
    for f in files:
        if f.is_dir() or f.suffix not in ('.ogg', '.opus', '.wav', '.mp3'):
            continue
        name = f.stem.lower()
        # Detect device
        device = None
        if 'clip_enhanced' in name or 'enhanced' in name:
            device = 'clip_enhanced'
        elif 'clip_normal' in name or 'normal' in name:
            device = 'clip_normal'
        elif 'clip' in name or 'respeaker' in name:
            device = 'clip_enhanced'  # default to enhanced
        elif 'anker' in name or 'd3200' in name:
            device = 'anker'

        # Detect corpus type
        corpus = None
        if 'zh' in name or 'cn' in name or 'chinese' in name:
            corpus = 'zh'
        elif 'en' in name or 'eng' in name or 'english' in name:
            corpus = 'en'
        elif 'digit' in name or 'num' in name or 'number' in name:
            corpus = 'digits'

        if device and corpus:
            new_name = f"{device}_{corpus}{f.suffix}"
            new_path = test_dir / new_name
            if f != new_path:
                f.rename(new_path)
                print(f"  Renamed: {f.name} -> {new_name}")
                renamed += 1

    if renamed == 0:
        print(f"  No auto-renames. Make sure files are named: clip_enhanced_zh.*, clip_normal_zh.*, anker_zh.*, etc.")

# ---------------------------------------------------------------------------
# Step 2: Analyze
# ---------------------------------------------------------------------------

def cmd_analyze(args):
    """Analyze all test recordings."""
    import numpy as np

    results = {}

    for env, distances in TEST_MATRIX.items():
        env_label = "Quiet Room" if env == "quiet" else "Meeting Room"

        for dist in distances:
            test_key = f"{env}/{dist}m"
            if args.only and test_key not in args.only:
                continue

            test_dir = RESULTS_DIR / env / f"{dist}m"
            if not test_dir.exists():
                print(f"  SKIP {test_key}: directory not found")
                continue

            print(f"\n{'=' * 50}")
            print(f"  Analyzing: {env_label} / {dist}m")
            print(f"{'=' * 50}")

            test_result = {"environment": env, "distance_m": dist, "devices": {}}

            # Decode all recordings to WAV
            for device in DEVICES:
                for ctype, info in CORPUS_TYPES.items():
                    # Find source file (any extension)
                    src = None
                    for ext in ['.ogg', '.opus', '.wav', '.mp3']:
                        candidate = test_dir / f"{device}_{ctype}{ext}"
                        if candidate.exists():
                            src = candidate
                            break

                    if not src:
                        continue

                    wav_path = test_dir / f"{device}_{ctype}.wav"
                    if decode_to_wav(src, wav_path):
                        dur = get_duration(wav_path)
                        rms = get_rms_db(wav_path)
                        print(f"    {device}_{ctype}: {dur:.1f}s, {rms:.1f} dBFS")

            # Run basic metrics (no ASR, fast)
            for device in DEVICES:
                device_result = {}
                for ctype, info in CORPUS_TYPES.items():
                    wav_path = test_dir / f"{device}_{ctype}.wav"
                    ref_path = test_dir / f"ref_{ctype}.wav"
                    corpus_ref = CORPUS_DIR / info["ref"]

                    if not wav_path.exists():
                        continue

                    # Use corpus reference if no local ref
                    if not ref_path.exists() and corpus_ref.exists():
                        import shutil
                        shutil.copy2(corpus_ref, ref_path)

                    metrics = analyze_basic(wav_path)
                    device_result[ctype] = metrics

                if device_result:
                    test_result["devices"][device] = device_result

            results[test_key] = test_result

    # Save results
    output_path = RESULTS_DIR / "analysis.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {output_path}")

    if args.report:
        cmd_report(results)


def analyze_basic(wav_path: Path) -> dict:
    """Compute basic audio metrics without reference alignment."""
    import numpy as np

    with wave.open(str(wav_path), 'rb') as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float64)

    duration = len(data) / sr

    # RMS and peak
    rms = np.sqrt(np.mean(data**2))
    peak = np.max(np.abs(data))
    rms_db = 20 * np.log10(rms / 32768 + 1e-10)
    peak_db = 20 * np.log10(peak / 32768 + 1e-10)

    # Noise floor (quietest 10% of 100ms windows)
    window = int(sr * 0.1)
    rms_vals = []
    for i in range(0, len(data) - window, window):
        seg = data[i:i+window]
        rms_vals.append(np.sqrt(np.mean(seg**2)))
    rms_arr = np.array(rms_vals)
    sorted_rms = np.sort(rms_arr)
    noise_rms = np.sqrt(np.mean(sorted_rms[:len(sorted_rms)//10]**2))
    speech_rms = np.sqrt(np.mean(sorted_rms[-len(sorted_rms)//4:]**2))
    noise_db = 20 * np.log10(noise_rms / 32768 + 1e-10)
    speech_db = 20 * np.log10(speech_rms / 32768 + 1e-10)
    snr = speech_db - noise_db

    # Frequency bands
    fft = np.fft.rfft(data * np.hanning(len(data)))
    magnitudes = np.abs(fft) / len(data) * 2
    freqs = np.fft.rfftfreq(len(data), 1/sr)

    def band_energy(lo, hi):
        mask = (freqs >= lo) & (freqs < hi)
        if not mask.any():
            return -120.0
        return float(20 * np.log10(np.mean(magnitudes[mask]**2) + 1e-20))

    freq_bands = {
        "100_500Hz": band_energy(100, 500),
        "500_2kHz":  band_energy(500, 2000),
        "2k_4kHz":   band_energy(2000, 4000),
        "4k_8kHz":   band_energy(4000, 8000),
    }

    # Dynamic range (level variation)
    window_2s = sr * 2
    levels = []
    for i in range(0, len(data) - window_2s, window_2s):
        seg = data[i:i+window_2s]
        r = np.sqrt(np.mean(seg**2))
        if r > 10:  # skip near-silence
            levels.append(20 * np.log10(r / 32768 + 1e-10))
    dynamic_range = max(levels) - min(levels) if len(levels) > 1 else 0

    return {
        "duration_s": round(duration, 1),
        "rms_dbfs": round(rms_db, 1),
        "peak_dbfs": round(peak_db, 1),
        "noise_floor_dbfs": round(noise_db, 1),
        "speech_level_dbfs": round(speech_db, 1),
        "snr_db": round(snr, 1),
        "dynamic_range_db": round(dynamic_range, 1),
        "freq_bands": {k: round(v, 1) for k, v in freq_bands.items()},
    }

# ---------------------------------------------------------------------------
# Step 3: Report
# ---------------------------------------------------------------------------

def cmd_report(results=None):
    """Generate human-readable comparison report."""
    if results is None:
        report_path = RESULTS_DIR / "analysis.json"
        if not report_path.exists():
            print("No analysis results found. Run 'analyze' first.")
            return
        with open(report_path) as f:
            results = json.load(f)

    print("\n" + "=" * 70)
    print("  COMPARISON REPORT: Clip vs Anker D3200")
    print("=" * 70)

    for test_key, test_data in results.items():
        env = test_data.get("environment", "")
        dist = test_data.get("distance_m", "")
        env_label = "Quiet Room" if env == "quiet" else "Meeting Room"

        print(f"\n{'─' * 70}")
        print(f"  {env_label} / {dist}m")
        print(f"{'─' * 70}")

        devices = test_data.get("devices", {})
        clip = devices.get("clip", {})
        anker = devices.get("anker", {})

        for ctype in ["zh", "en", "digits"]:
            c = clip.get(ctype, {})
            a = anker.get(ctype, {})
            if not c and not a:
                continue

            print(f"\n  [{ctype.upper()}]")

            # Comparison table
            metrics = [
                ("SNR",           "snr_db",           "dB",  True),
                ("Noise Floor",   "noise_floor_dbfs", "dBFS", False),
                ("Speech Level",  "speech_level_dbfs","dBFS", False),
                ("Dynamic Range", "dynamic_range_db", "dB",  False),
                ("Peak",          "peak_dbfs",        "dBFS", False),
            ]

            device_labels = {"clip_enhanced": "Clip-Enh", "clip_normal": "Clip-Norm", "anker": "Anker"}
            device_keys = [d for d in DEVICES if d in devices]

            header = f"  {'Metric':<16s}" + "".join(f" {device_labels.get(d, d):>10s}" for d in device_keys)
            print(header)
            print(f"  {'─'*16}" + "".join(f" {'─'*10}" for _ in device_keys))

            for label, key, unit, higher_better in metrics:
                vals = {d: devices[d].get(ctype, {}).get(key) for d in device_keys}
                line = f"  {label:<16s}"
                for d in device_keys:
                    v = vals[d]
                    line += f" {v:>9.1f}" if v is not None else f" {'N/A':>10s}"
                print(line)

            # Frequency bands
            print(f"\n  {'Freq Band':<16s}" + "".join(f" {device_labels.get(d, d):>10s}" for d in device_keys))
            print(f"  {'─'*16}" + "".join(f" {'─'*10}" for _ in device_keys))
            for band in ["100_500Hz", "500_2kHz", "2k_4kHz", "4k_8kHz"]:
                label = band.replace("_", "-")
                line = f"  {label:<16s}"
                for d in device_keys:
                    v = devices[d].get(ctype, {}).get("freq_bands", {}).get(band)
                    line += f" {v:>9.1f}" if v is not None else f" {'N/A':>10s}"
                print(line)

    # Summary
    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print("=" * 70)

    clip_wins = 0
    anker_wins = 0
    normal_wins = 0
    ties = 0

    for test_key, test_data in results.items():
        devices = test_data.get("devices", {})
        clip_e = devices.get("clip_enhanced", {})
        clip_n = devices.get("clip_normal", {})
        anker_d = devices.get("anker", {})

        for ctype in ["zh", "en", "digits"]:
            ce_snr = clip_e.get(ctype, {}).get("snr_db")
            cn_snr = clip_n.get(ctype, {}).get("snr_db")
            a_snr = anker_d.get(ctype, {}).get("snr_db")
            # Compare enhanced vs anker
            if ce_snr is not None and a_snr is not None:
                if ce_snr > a_snr + 1:
                    clip_wins += 1
                elif a_snr > ce_snr + 1:
                    anker_wins += 1
                else:
                    ties += 1
            # Compare normal vs anker
            if cn_snr is not None and a_snr is not None:
                if cn_snr > a_snr + 1:
                    normal_wins += 1

    total = clip_wins + anker_wins + ties
    print(f"\n  SNR Comparison (Clip Enhanced vs Anker, win = >1dB):")
    print(f"  Total comparisons: {total}")
    print(f"  Clip Enhanced wins: {clip_wins}")
    print(f"  Clip Normal wins:   {normal_wins}")
    print(f"  Anker wins:         {anker_wins}")
    print(f"  Ties:               {ties}")

    if total > 0:
        print(f"\n  Clip Enhanced win rate: {clip_wins/total*100:.0f}%")

    # WER summary
    wer_data = {}
    for test_key, test_data in results.items():
        devices = test_data.get("devices", {})
        for device in DEVICES:
            for ctype in ["zh", "en", "digits"]:
                wer = devices.get(device, {}).get(ctype, {}).get("wer_percent")
                if wer is not None:
                    wer_data.setdefault(test_key, {}).setdefault(device, {})[ctype] = wer

    if wer_data:
        print(f"\n  WER Comparison:")
        print(f"  {'Test':<15s} {'Corpus':<8s} {'Clip':>8s} {'Anker':>8s} {'Winner':>8s}")
        print(f"  {'─'*15} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        for test_key in sorted(wer_data.keys()):
            for ctype in ["zh", "en", "digits"]:
                cw = wer_data.get(test_key, {}).get("clip", {}).get(ctype)
                aw = wer_data.get(test_key, {}).get("anker", {}).get(ctype)
                if cw is not None or aw is not None:
                    if cw is not None and aw is not None:
                        winner = "Clip" if cw < aw else ("Anker" if aw < cw else "Tie")
                        print(f"  {test_key:<15s} {ctype:<8s} {cw:>7.1f}% {aw:>7.1f}% {winner:>8s}")

    print(f"\n{'=' * 70}")
    print(f"  Full data: {RESULTS_DIR / 'analysis.json'}")
    print(f"{'=' * 70}\n")


# ---------------------------------------------------------------------------
# Step 4: WER Analysis (optional, requires whisper)
# ---------------------------------------------------------------------------

def cmd_wer(args):
    """Run WER analysis on all decoded recordings."""
    try:
        import whisper
    except ImportError:
        print("ERROR: whisper not installed. Run: pip install openai-whisper")
        return

    import whisper
    from jiwer import wer as jiwer_wer
    import re

    report_path = RESULTS_DIR / "analysis.json"
    if not report_path.exists():
        print("No analysis results. Run 'analyze' first.")
        return
    with open(report_path) as f:
        results = json.load(f)

    print("Loading Whisper large-v3...")
    model = whisper.load_model("large-v3")

    for test_key, test_data in results.items():
        test_dir = RESULTS_DIR / test_data["environment"] / f"{test_data['distance_m']}m"

        for device in DEVICES:
            for ctype, info in CORPUS_TYPES.items():
                wav_path = test_dir / f"{device}_{ctype}.wav"
                if not wav_path.exists():
                    continue

                # Check if already computed
                existing = (results[test_key]
                    .get("devices", {})
                    .get(device, {})
                    .get(ctype, {})
                    .get("wer_percent"))
                if existing is not None and not args.force:
                    print(f"  SKIP {test_key}/{device}/{ctype} (already {existing:.1f}%)")
                    continue

                lang = info["lang"]
                print(f"  Transcribing: {test_key}/{device}/{ctype} [{lang}]...")
                result = model.transcribe(str(wav_path), language=lang)
                transcribed = result["text"].strip()

                # Get reference text
                ref_text = get_reference_text(ctype, lang)
                if not ref_text:
                    print(f"    No reference text for {ctype}, skipping WER")
                    # Still save transcription
                    results[test_key].setdefault("devices", {}).setdefault(device, {}).setdefault(ctype, {})
                    results[test_key]["devices"][device][ctype]["transcribed"] = transcribed
                    continue

                # Compute WER
                if lang == "zh":
                    ref_clean = re.sub(r'[^\w]', '', ref_text)
                    hyp_clean = re.sub(r'[^\w]', '', transcribed)
                else:
                    ref_clean = ref_text.lower()
                    hyp_clean = transcribed.lower()

                error = jiwer_wer(ref_clean, hyp_clean) * 100

                print(f"    WER: {error:.1f}%")
                print(f"    Ref:  {ref_text[:60]}...")
                print(f"    Hyp:  {transcribed[:60]}...")

                # Save
                results.setdefault(test_key, {}).setdefault("devices", {}).setdefault(device, {}).setdefault(ctype, {})
                results[test_key]["devices"][device][ctype]["wer_percent"] = round(error, 1)
                results[test_key]["devices"][device][ctype]["transcribed"] = transcribed
                results[test_key]["devices"][device][ctype]["reference_text"] = ref_text

    with open(report_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {report_path}")


def get_reference_text(ctype: str, lang: str) -> str:
    """Get reference text for a corpus type."""
    if ctype == "zh":
        from gen_corpus import ZH_SENTENCES
        return " ".join(ZH_SENTENCES)
    elif ctype == "en":
        from gen_corpus import EN_SENTENCES
        return " ".join(EN_SENTENCES)
    elif ctype == "digits":
        from gen_corpus import DIGIT_SEQUENCES
        return " ".join(DIGIT_SEQUENCES)
    return ""

# ---------------------------------------------------------------------------
# Step 1.5: Split continuous recording by distance
# ---------------------------------------------------------------------------

def cmd_split(args):
    """Split continuous recordings by distance using timestamps from distances.json."""
    timing_path = CORPUS_DIR / "distances.json"
    if not timing_path.exists():
        print(f"ERROR: {timing_path} not found. Run gen_test_audio.py first.")
        return

    with open(timing_path) as f:
        timing = json.load(f)

    segments = timing["segments"]
    print(f"Loaded {len(segments)} distance segments:")
    for seg in segments:
        print(f"  {seg['distance_m']}m: {seg['start_sec']}s - {seg['end_sec']}s")

    # Find source files to split (environment dirs)
    envs = ["quiet", "meeting"] if args.env == "all" else [args.env]

    for env in envs:
        env_dir = RESULTS_DIR / env
        if not env_dir.exists():
            print(f"\n  SKIP {env}: directory not found")
            continue

        # Find raw recording files (not yet split)
        raw_files = []
        for f in env_dir.iterdir():
            if f.is_file() and f.suffix in ('.ogg', '.opus', '.wav') and not f.stem.startswith('.'):
                # Skip if already a split file (in subdirectory)
                raw_files.append(f)

        if not raw_files:
            print(f"\n  SKIP {env}: no recording files found in {env_dir}")
            continue

        print(f"\n{'=' * 50}")
        print(f"  Splitting: {env} ({len(raw_files)} files)")
        print(f"{'=' * 50}")

        for raw_file in raw_files:
            name = raw_file.stem.lower()
            print(f"\n  Processing: {raw_file.name}")

            # Determine device from filename
            device = None
            if 'enhanced' in name or 'clip_enhanced' in name:
                device = 'clip_enhanced'
            elif 'normal' in name or 'clip_normal' in name:
                device = 'clip_normal'
            elif 'clip' in name:
                device = 'clip_enhanced'  # default
            elif 'anker' in name:
                device = 'anker'

            if not device:
                print(f"    Cannot detect device from filename. Use format: clip_enhanced_*, clip_normal_*, anker_*")
                continue

            # Decode to WAV first (if needed)
            wav_src = raw_file.with_suffix('.wav')
            if wav_src.exists() and wav_src.stat().st_mtime > raw_file.stat().st_mtime:
                print(f"    Using existing: {wav_src.name}")
            else:
                decode_to_wav(raw_file, wav_src, channels=1 if 'clip' in device else 1)

            if not wav_src.exists():
                print(f"    ERROR: failed to decode {raw_file.name}")
                continue

            # Split by distance segments
            import numpy as np
            with wave.open(str(wav_src), 'rb') as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                raw_pcm = wf.readframes(n_frames)

            data = np.frombuffer(raw_pcm, dtype=np.int16)
            total_dur = len(data) / sr
            print(f"    Duration: {total_dur:.1f}s, SR: {sr}Hz")

            for seg in segments:
                dist = seg['distance_m']
                start_sample = int(seg['start_sec'] * sr)
                end_sample = int(seg['end_sec'] * sr)

                if end_sample > len(data):
                    print(f"    SKIP {dist}m: recording too short (need {seg['end_sec']}s, have {total_dur:.0f}s)")
                    continue

                chunk = data[start_sample:end_sample]

                # Now split corpus segments within this distance
                for cseg in seg['corpus_segments']:
                    ctype = cseg['file'].replace('full_', '').replace('.wav', '')
                    c_start = int((cseg['start_sec'] - seg['start_sec']) * sr)
                    c_end = c_start + int(cseg['duration_sec'] * sr)

                    if c_end > len(chunk):
                        print(f"    SKIP {dist}m/{ctype}: segment extends beyond recording")
                        continue

                    corpus_chunk = chunk[c_start:c_end]

                    # Write output
                    out_dir = RESULTS_DIR / env / f"{dist}m"
                    ensure_dir(out_dir)
                    out_path = out_dir / f"{device}_{ctype}.wav"

                    with wave.open(str(out_path), 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(sr)
                        wf.writeframes(corpus_chunk.tobytes())

                    print(f"    {dist}m/{ctype}: {len(corpus_chunk)/sr:.1f}s -> {out_path.relative_to(RESULTS_DIR)}")

    print(f"\nSplit complete! Run 'analyze --report' to generate comparison.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Audio comparison test runner: Clip vs Anker D3200",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Interactive guided test")
    p_run.add_argument("--env", choices=["quiet", "meeting", "all"], default="all")
    p_run.add_argument("--distances", type=int, nargs="+", default=[1, 2, 3])

    # analyze
    p_analyze = sub.add_parser("analyze", help="Analyze all recordings")
    p_analyze.add_argument("--report", action="store_true", help="Generate report after analysis")
    p_analyze.add_argument("--only", nargs="+", help="Only analyze specific tests (e.g. quiet/1m)")

    # report
    sub.add_parser("report", help="Generate comparison report")

    # split
    p_split = sub.add_parser("split", help="Split continuous recordings by distance")
    p_split.add_argument("--env", choices=["quiet", "meeting", "all"], default="all")

    # wer
    p_wer = sub.add_parser("wer", help="Run WER analysis (requires whisper)")
    p_wer.add_argument("--force", action="store_true", help="Re-run even if already computed")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "split":
        cmd_split(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "report":
        cmd_report()
    elif args.command == "wer":
        cmd_wer(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
