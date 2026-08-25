#!/usr/bin/env python3
"""
Audio quality benchmark tool for Clip vs competitor comparison.

Computes SNR, STOI, PESQ, and WER between a reference recording and a test recording.
Supports batch processing of multiple test files against a single reference.

Usage:
    # Single file
    python audio_benchmark.py --ref ref.wav --test recording.wav -o result.json

    # Batch (directory of WAV files)
    python audio_benchmark.py --ref ref.wav --test recordings/ -o results.json

    # Skip ASR (objective metrics only, faster)
    python audio_benchmark.py --ref ref.wav --test recording.wav --no-asr -o result.json

Dependencies:
    pip install numpy scipy pystoi pesq jiwer
    # Optional for ASR: pip install openai-whisper
"""

import argparse
import json
import sys
import wave
from pathlib import Path


def read_wav(path):
    """Read a WAV file and return (samples, sample_rate) as float32 numpy array."""
    import numpy as np

    with wave.open(str(path), 'rb') as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sample_width == 2:
        dtype = np.int16
    elif sample_width == 4:
        dtype = np.int32
    else:
        raise ValueError(f"Unsupported sample width: {sample_width} bytes")

    data = np.frombuffer(raw, dtype=dtype).astype(np.float32)

    # Mix to mono if stereo
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)

    # Normalize to [-1, 1]
    if dtype == np.int16:
        data /= 32768.0
    elif dtype == np.int32:
        data /= 2147483648.0

    return data, sample_rate


def resample_if_needed(samples, src_rate, target_rate):
    """Resample to target rate if needed."""
    if src_rate == target_rate:
        return samples

    from scipy.signal import resample
    num_samples = int(len(samples) * target_rate / src_rate)
    return resample(samples, num_samples).astype(samples.dtype)


def align_signals(ref, test):
    """Align test signal to reference using cross-correlation.

    Returns (aligned_test, offset) where offset is the number of samples
    the test signal was shifted relative to the reference.
    """
    import numpy as np
    from scipy.signal import correlate

    # Use a shorter segment for correlation to save time
    max_len = min(len(ref), len(test), 16000 * 30)  # max 30 seconds for alignment
    ref_seg = ref[:max_len]
    test_seg = test[:max_len]

    correlation = correlate(ref_seg, test_seg, mode='full')
    lag = np.argmax(correlation) - len(test_seg) + 1

    if lag > 0:
        # Test starts later — prepend zeros to test
        aligned = np.concatenate([np.zeros(lag, dtype=test.dtype), test])
    elif lag < 0:
        # Test starts earlier — trim beginning of test
        aligned = test[-lag:]
    else:
        aligned = test

    # Trim or pad to match reference length
    if len(aligned) < len(ref):
        aligned = np.concatenate([aligned, np.zeros(len(ref) - len(aligned), dtype=aligned.dtype)])
    elif len(aligned) > len(ref):
        aligned = aligned[:len(ref)]

    return aligned, int(lag)


def compute_snr(ref, test):
    """Compute SNR in dB between reference and test."""
    import numpy as np

    noise = ref[:len(test)] - test[:len(ref)]
    signal_power = np.mean(ref[:len(test)] ** 2)
    noise_power = np.mean(noise ** 2)

    if noise_power < 1e-10:
        return 99.0  # effectively no noise

    return float(10 * np.log10(signal_power / noise_power))


def compute_stoi(ref, test, sr):
    """Compute STOI (Short-Time Objective Intelligibility)."""
    from stoi import stoi
    return float(stoi(ref, test, sr, extended=False))


def compute_pesq(ref, test, sr):
    """Compute PESQ (Perceptual Evaluation of Speech Quality)."""
    from pesq import pesq as pesq_func

    # PESQ requires 16kHz or 8kHz
    if sr != 16000:
        ref = resample_if_needed(ref, sr, 16000)
        test = resample_if_needed(test, sr, 16000)
        sr = 16000

    return float(pesq_func(sr, ref, test, 'wb'))


def compute_thd(signal, sr, fundamental_freq=1000):
    """Compute THD (Total Harmonic Distortion) for a given fundamental frequency."""
    import numpy as np

    n = len(signal)
    window = np.hanning(n)
    windowed = signal * window

    fft = np.fft.rfft(windowed)
    magnitudes = np.abs(fft) * 2.0 / n

    freq_resolution = sr / n
    fund_bin = int(round(fundamental_freq / freq_resolution))

    if fund_bin == 0 or fund_bin >= len(magnitudes):
        return 0.0

    fund_power = magnitudes[fund_bin] ** 2

    harmonic_power = 0.0
    for h in range(2, 11):  # 2nd through 10th harmonics
        h_bin = fund_bin * h
        if h_bin >= len(magnitudes):
            break
        harmonic_power += magnitudes[h_bin] ** 2

    if fund_power < 1e-10:
        return 0.0

    return float(np.sqrt(harmonic_power / fund_power) * 100)


def compute_wer(ref_text, test_audio_path, language='zh'):
    """Compute WER using Whisper ASR."""
    import whisper
    from jiwer import wer as jiwer_wer

    model = whisper.load_model("large-v3")
    result = model.transcribe(str(test_audio_path), language=language)
    transcribed = result["text"].strip()

    if language == 'zh':
        # Character-level: remove punctuation and whitespace
        import re
        ref_clean = re.sub(r'[^\w]', '', ref_text)
        hyp_clean = re.sub(r'[^\w]', '', transcribed)
        error = jiwer_wer(ref_clean, hyp_clean)
    else:
        error = jiwer_wer(ref_text, transcribed)

    return float(error * 100), transcribed


def benchmark_single(ref_path, test_path, no_asr=False, ref_text=None, language='zh'):
    """Run full benchmark on a single test file against a reference.

    Returns a dict with all computed metrics.
    """
    result = {
        "reference": str(ref_path),
        "test_file": str(test_path),
    }

    print(f"  Loading reference: {ref_path}")
    ref, ref_sr = read_wav(ref_path)
    print(f"  Loading test: {test_path}")
    test, test_sr = read_wav(test_path)

    # Resample to common rate
    target_sr = 16000
    ref = resample_if_needed(ref, ref_sr, target_sr)
    test = resample_if_needed(test, test_sr, target_sr)

    print(f"  Ref: {len(ref)} samples ({len(ref)/target_sr:.1f}s), "
          f"Test: {len(test)} samples ({len(test)/target_sr:.1f}s)")

    # Align
    print("  Aligning signals...")
    test_aligned, offset = align_signals(ref, test)
    print(f"  Alignment offset: {offset} samples ({offset/target_sr*1000:.0f}ms)")

    # SNR
    snr = compute_snr(ref, test_aligned)
    print(f"  SNR: {snr:.1f} dB")

    # STOI
    stoi = compute_stoi(ref, test_aligned, target_sr)
    print(f"  STOI: {stoi:.3f}")

    # PESQ
    pesq = compute_pesq(ref, test_aligned, target_sr)
    print(f"  PESQ: {pesq:.2f}")

    metrics = {
        "snr_db": round(snr, 1),
        "stoi": round(stoi, 3),
        "pesq": round(pesq, 2),
    }
    result["metrics"] = metrics

    # ASR
    if not no_asr and ref_text:
        print(f"  Running ASR ({language})...")
        wer_val, transcribed = compute_wer(ref_text, test_path, language)
        print(f"  WER({language}): {wer_val:.1f}%")
        result["asr"] = {
            "engine": "whisper-large-v3",
            "language": language,
            "wer_percent": round(wer_val, 1),
            "reference_text": ref_text,
            "transcribed_text": transcribed,
        }
    elif not no_asr:
        print("  Skipping ASR (no reference text provided, use --ref-text)")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Audio quality benchmark: compute SNR/STOI/PESQ/WER between reference and test recordings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file test
  python audio_benchmark.py --ref ref.wav --test recording.wav -o result.json

  # Batch test all WAV files in a directory
  python audio_benchmark.py --ref ref.wav --test recordings/ -o results.json

  # With ASR (provide reference text)
  python audio_benchmark.py --ref ref.wav --test recording.wav \\
      --ref-text "今天天气很好" --language zh -o result.json

  # Objective metrics only (no ASR, faster)
  python audio_benchmark.py --ref ref.wav --test recording.wav --no-asr -o result.json
        """
    )

    parser.add_argument("--ref", required=True, type=Path, help="Reference WAV file")
    parser.add_argument("--test", required=True, type=Path,
                        help="Test WAV file or directory of WAV files")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON file")
    parser.add_argument("--no-asr", action="store_true",
                        help="Skip ASR transcription (objective metrics only)")
    parser.add_argument("--ref-text", type=str, help="Reference text for WER calculation")
    parser.add_argument("--language", type=str, default="zh", choices=["zh", "en"],
                        help="Language for ASR (default: zh)")

    args = parser.parse_args()

    if not args.ref.exists():
        print(f"Error: Reference file not found: {args.ref}")
        return 1

    # Collect test files
    if args.test.is_dir():
        test_files = sorted(args.test.glob("*.wav"))
        if not test_files:
            print(f"Error: No WAV files found in {args.test}")
            return 1
    elif args.test.exists():
        test_files = [args.test]
    else:
        print(f"Error: Test file not found: {args.test}")
        return 1

    print(f"Reference: {args.ref}")
    print(f"Test files: {len(test_files)}")
    print()

    results = []
    for i, tf in enumerate(test_files):
        print(f"[{i+1}/{len(test_files)}] {tf.name}")
        result = benchmark_single(
            args.ref, tf,
            no_asr=args.no_asr,
            ref_text=args.ref_text,
            language=args.language,
        )
        results.append(result)
        print()

    # Output
    output_data = results if len(results) > 1 else results[0]

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"Results saved to {args.output}")
    else:
        print(json.dumps(output_data, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
