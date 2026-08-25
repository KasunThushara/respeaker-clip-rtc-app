#!/usr/bin/env python3
"""
Generate reference audio corpus for audio quality testing.

Uses edge-tts (Microsoft Edge TTS) to generate 16kHz mono WAV files
from the standard test corpus defined in docs/audio_quality_standard.md Section 4.

Output structure:
    tests/corpus/
        zh/01.wav ~ 20.wav       # Chinese 20 sentences
        en/01.wav ~ 20.wav       # English 20 Harvard sentences
        digits/01.wav ~ 10.wav   # Digit sequences
        full_zh.wav              # All Chinese concatenated
        full_en.wav              # All English concatenated
        full_digits.wav          # All digits concatenated

Usage:
    python gen_corpus.py                  # Generate all
    python gen_corpus.py --zh             # Chinese only
    python gen_corpus.py --en             # English only
    python gen_corpus.py --digits         # Digits only
    python gen_corpus.py --concat         # Also generate concatenated files
"""

import argparse
import asyncio
import struct
import wave
from pathlib import Path

CORPUS_DIR = Path(__file__).parent / "corpus"

# --- Section 4.1: Chinese Balanced Corpus ---
ZH_SENTENCES = [
    "今天天气很好，我们去公园散步吧。",
    "明天早上八点开会，请准时到场。",
    "这个项目的预算已经超过了原定计划。",
    "人工智能技术正在改变我们的生活方式。",
    "请把窗户打开，房间太闷了。",
    "他每天晚上都会看一个小时的书。",
    "这道菜的口味偏辣，不太适合老人和小孩。",
    "会议结束后，我们需要整理一份详细的报告。",
    "上周末我去了一趟上海，参观了几家博物馆。",
    "春天的风景最美，到处都是鲜花和绿树。",
    "老师建议我们先复习基础知识，再做练习题。",
    "火车站离这里不远，走路大概十五分钟。",
    "服务员问我们要不要加点辣椒油。",
    "我们的产品具有高质量和优秀的性能。",
    "这部电影的剧情很精彩，值得推荐给大家。",
    "他是一位非常出色的工程师，解决了很多难题。",
    "夏天的时候，孩子们喜欢去河边游泳。",
    "这篇文章的重点是分析数据趋势和规律。",
    "每年春节，全家人都会聚在一起吃年夜饭。",
    "新款手机的功能越来越强大，价格也很合理。",
]

# --- Section 4.2: English Standard Corpus (Harvard sentences) ---
EN_SENTENCES = [
    "The birch canoe slid on the smooth planks.",
    "Glue the sheet to the dark blue background.",
    "It is easy to tell the depth of a well.",
    "These days a chicken leg is a rare dish.",
    "Rice is often served in round bowls.",
    "The juice of lemons makes fine punch.",
    "The box was thrown beside the parked truck.",
    "The hogs were fed chopped corn and garbage.",
    "Four hours of steady work faced us.",
    "A large size in stockings is hard to sell.",
    "The boy was there when the sun rose.",
    "A rod is used to catch pink salmon.",
    "The source of the huge river is the clear spring.",
    "Kick the ball straight and follow through.",
    "Help the woman get back to her feet.",
    "A pot of tea helps to pass the evening.",
    "Smoky fires lack flame and heat.",
    "The soft cushion broke the man's fall.",
    "The salt breeze came across from the sea.",
    "The girl at the booth sold fifty bonds.",
]

# --- Section 4.3: Digit Sequences ---
DIGIT_SEQUENCES = [
    "3 8 2 7 1 9 5 4",
    "6 0 4 9 2 8 1 7",
    "5 1 9 3 7 6 0 2",
    "8 4 2 6 0 5 9 1",
    "1 7 3 5 9 2 8 4",
    "9 0 6 4 1 7 3 5",
    "2 5 8 1 4 7 0 6",
    "7 2 9 4 6 1 5 0",
    "4 6 0 8 3 5 7 2",
    "0 3 7 1 8 4 6 9",
]

# TTS voice selection
ZH_VOICE = "zh-CN-YunxiNeural"    # Male, lively/sunshine - natural speech
EN_VOICE = "en-US-GuyNeural"      # Male, news - clear articulation

# Rate: -10% slightly slower for clearer pronunciation
ZH_RATE = "-10%"
EN_RATE = "-5%"


async def generate_one(text: str, output: Path, voice: str, rate: str = "+0%"):
    """Generate a single TTS WAV file using edge-tts."""
    import edge_tts

    mp3_path = output.with_suffix(".mp3")
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(mp3_path))

    # Convert MP3 to 16kHz mono WAV using ffmpeg
    import subprocess
    cmd = [
        "ffmpeg", "-y", "-i", str(mp3_path),
        "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
        str(output)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR converting {mp3_path}: {result.stderr[:200]}")
        return False

    # Remove intermediate MP3
    mp3_path.unlink()
    return True


def concat_wav(files: list[Path], output: Path, silence_ms=2000):
    """Concatenate multiple WAV files with silence between them."""
    import numpy as np

    all_samples = []
    sr = 16000
    silence_samples = int(sr * silence_ms / 1000)

    for f in files:
        with wave.open(str(f), 'rb') as wf:
            assert wf.getframerate() == sr
            assert wf.getnchannels() == 1
            n = wf.getnframes()
            raw = wf.readframes(n)
            samples = np.frombuffer(raw, dtype=np.int16)
            all_samples.append(samples)
            all_samples.append(np.zeros(silence_samples, dtype=np.int16))

    # Remove trailing silence
    if all_samples:
        all_samples.pop()

    combined = np.concatenate(all_samples)

    with wave.open(str(output), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(combined.tobytes())

    duration = len(combined) / sr
    print(f"  Concatenated {len(files)} files -> {output.name} ({duration:.1f}s)")


async def generate_set(sentences, voice, rate, subdir, do_concat):
    """Generate a set of WAV files for one corpus."""
    out_dir = CORPUS_DIR / subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    files = []
    for i, text in enumerate(sentences, 1):
        output = out_dir / f"{i:02d}.wav"
        print(f"  [{i:2d}/{len(sentences)}] {text[:40]}{'...' if len(text) > 40 else ''}")
        ok = await generate_one(text, output, voice, rate)
        if ok:
            files.append(output)
        else:
            print(f"  FAILED: {output}")

    if do_concat and files:
        concat_file = CORPUS_DIR / f"full_{subdir}.wav"
        concat_wav(files, concat_file)

    return files


async def main():
    parser = argparse.ArgumentParser(description="Generate reference audio corpus")
    parser.add_argument("--zh", action="store_true", help="Chinese corpus only")
    parser.add_argument("--en", action="store_true", help="English corpus only")
    parser.add_argument("--digits", action="store_true", help="Digit sequences only")
    parser.add_argument("--concat", action="store_true", help="Also generate concatenated full files")
    args = parser.parse_args()

    do_all = not (args.zh or args.en or args.digits)

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    if do_all or args.zh:
        print(f"\n=== Chinese Corpus ({len(ZH_SENTENCES)} sentences, voice: {ZH_VOICE}) ===")
        await generate_set(ZH_SENTENCES, ZH_VOICE, ZH_RATE, "zh", args.concat or do_all)

    if do_all or args.en:
        print(f"\n=== English Corpus ({len(EN_SENTENCES)} sentences, voice: {EN_VOICE}) ===")
        await generate_set(EN_SENTENCES, EN_VOICE, EN_RATE, "en", args.concat or do_all)

    if do_all or args.digits:
        print(f"\n=== Digit Sequences ({len(DIGIT_SEQUENCES)} groups, voice: {ZH_VOICE}) ===")
        await generate_set(DIGIT_SEQUENCES, ZH_VOICE, "+0%", "digits", args.concat or do_all)

    # Summary
    total = sum(1 for p in CORPUS_DIR.rglob("*.wav") if p.parent != CORPUS_DIR)
    concat = sum(1 for p in CORPUS_DIR.glob("full_*.wav"))
    print(f"\nDone! Generated {total} individual files + {concat} concatenated files in {CORPUS_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
