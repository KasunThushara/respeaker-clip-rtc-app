#!/usr/bin/env python3
"""
DashScope Fun-ASR speech recognition via WebSocket streaming.

Supports local audio files (ogg, wav, mp3, etc.) by streaming them
directly to DashScope's real-time ASR endpoint.

Usage:
    python dashscope_asr.py <audio_file> [--language zh] [--model fun-asr-realtime]
    python dashscope_asr.py <audio_file> --output result.json
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid

try:
    import websocket
except ImportError:
    print("Error: websocket-client not installed. Run: pip install websocket-client")
    sys.exit(1)

DASHSCOPE_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference/"
CHUNK_SIZE = 3200  # 100ms of 16kHz 16-bit mono = 3200 bytes
CHUNK_INTERVAL = 0.1  # seconds between chunks


def get_api_key():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        print("Error: DASHSCOPE_API_KEY not set. Export it or pass --api-key.")
        sys.exit(1)
    return key


def convert_to_wav16k_mono(input_path, output_path):
    """Convert any audio to 16kHz mono WAV using ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg error: {result.stderr}")
        sys.exit(1)


def transcribe(audio_path, api_key=None, language="zh", model="fun-asr-realtime",
               semantic_punctuation=True, verbose=False):
    """
    Transcribe audio file using DashScope WebSocket ASR.

    Returns dict with 'text', 'sentences', 'duration_sec'.
    """
    api_key = api_key or get_api_key()

    # Convert to 16kHz mono WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = tmp.name
    try:
        convert_to_wav16k_mono(audio_path, tmp_wav)
        file_size = os.path.getsize(tmp_wav)
        audio_duration = (file_size - 44) / 32000.0  # 16kHz * 2bytes
        if verbose:
            print(f"  Audio: {audio_duration:.1f}s, {file_size/1024:.0f}KB")
    except Exception as e:
        os.unlink(tmp_wav)
        return {"error": str(e)}

    task_id = uuid.uuid4().hex[:32]
    sentences = []
    full_text_parts = []
    duration_sec = 0
    error_msg = None

    try:
        # Connect
        ws = websocket.create_connection(
            DASHSCOPE_WS_URL,
            header={"Authorization": f"bearer {api_key}"},
            timeout=30,
        )

        # Send run-task
        run_task = {
            "header": {
                "action": "run-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "asr",
                "function": "recognition",
                "model": model,
                "parameters": {
                    "format": "wav",
                    "sample_rate": 16000,
                    "semantic_punctuation_enabled": semantic_punctuation,
                },
                "input": {},
            },
        }
        if language:
            run_task["payload"]["parameters"]["language_hints"] = [language]
        ws.send(json.dumps(run_task))

        # Receive loop + send audio in a thread
        import threading

        audio_sent = threading.Event()
        send_error = [None]

        def send_audio():
            try:
                # Wait for task-started
                ws.settimeout(15)
                while True:
                    msg = ws.recv()
                    data = json.loads(msg)
                    event = data.get("header", {}).get("event")
                    if event == "task-started":
                        break
                    elif event == "task-failed":
                        send_error[0] = data.get("header", {}).get("error_message", "task failed before start")
                        return

                if verbose:
                    print("  Task started, streaming audio...")

                # Stream audio chunks
                with open(tmp_wav, "rb") as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        ws.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                        time.sleep(CHUNK_INTERVAL)

                # Send finish-task
                finish_task = {
                    "header": {
                        "action": "finish-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {"input": {}},
                }
                ws.send(json.dumps(finish_task))
                if verbose:
                    print("  Audio sent, waiting for results...")
            except Exception as e:
                send_error[0] = str(e)
            finally:
                audio_sent.set()

        sender = threading.Thread(target=send_audio, daemon=True)
        sender.start()

        # Receive results
        ws.settimeout(120)
        while True:
            try:
                msg = ws.recv()
                if isinstance(msg, bytes):
                    continue
                data = json.loads(msg)
                event = data.get("header", {}).get("event")

                if event == "result-generated":
                    sentence = data.get("payload", {}).get("output", {}).get("sentence", {})
                    text = sentence.get("text", "")
                    is_end = sentence.get("sentence_end", False)
                    is_heartbeat = sentence.get("heartbeat", False)

                    if is_heartbeat:
                        continue

                    if is_end and text:
                        begin = sentence.get("begin_time", 0)
                        end = sentence.get("end_time", 0)
                        sentences.append({
                            "text": text,
                            "begin_ms": begin,
                            "end_ms": end,
                        })
                        full_text_parts.append(text)
                        if verbose:
                            print(f"    [{begin/1000:.1f}s-{end/1000:.1f}s] {text}")

                    usage = data.get("payload", {}).get("usage")
                    if usage:
                        duration_sec = usage.get("duration", 0)

                elif event == "task-finished":
                    break

                elif event == "task-failed":
                    error_msg = data.get("header", {}).get("error_message", "unknown error")
                    if verbose:
                        print(f"  ERROR: {error_msg}")
                    break

            except websocket.WebSocketTimeoutException:
                if audio_sent.is_set() and send_error[0]:
                    error_msg = send_error[0]
                    break
                continue

        ws.close()

    except Exception as e:
        error_msg = str(e)

    # Cleanup
    try:
        os.unlink(tmp_wav)
    except:
        pass

    result = {
        "text": "".join(full_text_parts),
        "sentences": sentences,
        "duration_sec": duration_sec,
        "audio_file": os.path.basename(audio_path),
    }
    if error_msg:
        result["error"] = error_msg

    return result


def main():
    parser = argparse.ArgumentParser(description="DashScope ASR transcription")
    parser.add_argument("audio", help="Audio file path")
    parser.add_argument("--api-key", help="DashScope API key (or set DASHSCOPE_API_KEY)")
    parser.add_argument("--language", default="zh", help="Language hint (zh, en, ja)")
    parser.add_argument("--model", default="fun-asr-realtime", help="ASR model name")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--no-semantic-punctuation", action="store_true",
                        help="Disable semantic punctuation (use VAD)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.audio):
        print(f"Error: {args.audio} not found")
        sys.exit(1)

    print(f"Transcribing: {args.audio}")
    result = transcribe(
        args.audio,
        api_key=args.api_key,
        language=args.language,
        model=args.model,
        semantic_punctuation=not args.no_semantic_punctuation,
        verbose=args.verbose,
    )

    if "error" in result:
        print(f"\nError: {result['error']}")
        sys.exit(1)

    print(f"\n--- Transcription ({result['duration_sec']}s) ---")
    print(result["text"])

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nSaved to: {args.output}")
    else:
        print("\n--- JSON ---")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
