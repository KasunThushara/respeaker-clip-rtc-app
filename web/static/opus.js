// Thin browser wrapper around the vendored opusscript (asm.js libopus) native
// module. Load `lib/opusscript_native.js` with a <script> tag first — it sets
// window.Module to a factory function.
//
// The device streams raw Opus packets (16 kHz, mono, 20 ms frames) so we only
// need the decode path. opusscript exposes the C++ handler directly, which we
// wrap here to avoid its Node-only Buffer dependency.

const SAMPLE_RATE = 16000;
const CHANNELS = 1;
const FRAME_SAMPLES = 320; // 20 ms @ 16 kHz
const MAX_PACKET = 1276 * 3; // libopus max packet size
const OPUS_APPLICATION_AUDIO = 2049;

let M = null;
let handler = null;
let packetPtr = null;
let outPtr = null;
let initPromise = null;

export function ensureOpus() {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    const factory = window.Module;
    if (typeof factory !== "function") {
      throw new Error(
        "opusscript native module not loaded (lib/opusscript_native.js missing?)",
      );
    }
    M = factory();
    handler = new M.OpusScriptHandler(SAMPLE_RATE, CHANNELS, OPUS_APPLICATION_AUDIO);
    packetPtr = M._malloc(MAX_PACKET);
    outPtr = M._malloc(FRAME_SAMPLES * 2);
  })();
  return initPromise;
}

// Decode one raw Opus packet into an Int16Array (mono 16 kHz). Returns null on
// error. Exactly one 20 ms frame per packet from the device => 320 samples.
export function decodeOpusPacket(packet) {
  if (!handler) throw new Error("opus not initialized (call ensureOpus first)");
  if (!(packet instanceof Uint8Array)) return null;
  if (packet.length === 0 || packet.length > MAX_PACKET) return null;

  M.HEAPU8.set(packet, packetPtr);
  const samples = handler._decode(packetPtr, packet.length, outPtr);
  if (samples < 0 || samples > FRAME_SAMPLES) return null;

  const out = new Int16Array(samples);
  const heap = M.HEAP16;
  const base = outPtr >> 1; // byte offset -> element index
  for (let i = 0; i < samples; i++) out[i] = heap[base + i];
  return out;
}

export function destroyOpus() {
  if (M) {
    try {
      M.OpusScriptHandler.destroy_handler(handler);
      M._free(packetPtr);
      M._free(outPtr);
    } catch (_) {
      /* ignore teardown errors */
    }
  }
  M = null;
  handler = null;
  packetPtr = null;
  outPtr = null;
  initPromise = null;
}
