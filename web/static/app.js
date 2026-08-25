// Clip Live Stream — Web Bluetooth + Groq transcription.
//
// Flows:
//   1. Connect to the Clip over Web Bluetooth (Chrome/Edge, localhost or HTTPS).
//   2. Press Start: AT+START=RTC -> AT+DOWNLOAD=<session> -> STREAM_DATA frames.
//   3. Each 20 ms Opus packet is decoded to PCM (opus.js) and fed to the VAD.
//   4. When an utterance ends (silence), its PCM is wrapped in a WAV and POSTed
//      to /api/transcribe, which forwards it to Groq Whisper.
//   5. Press Stop: AT+STOP (flushes any pending utterance first).
//
// Demo mode replays a bundled sample stream (no Bluetooth) so the UI and the
// transcription pipeline can be tested on any machine.

import { ClipConnection, parseFileDataFrame, FRAME_STREAM_START, FRAME_STREAM_DATA, FRAME_STREAM_END, STREAM_END_REASONS } from "./protocol.js";
import { ensureOpus, decodeOpusPacket } from "./opus.js";
import { VAD } from "./vad.js";
import { pcmToWav } from "./audio.js";

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// Tiny state
// ---------------------------------------------------------------------------
const state = {
  conn: null,
  streaming: false,
  sessionId: null,
  demo: false,
  demoIdx: 0,
  demoFrame: null,
  visBars: null,
  lastRms: -100,
  speaking: false,
  transcribeChain: Promise.resolve(),
  utteranceIndex: 0,
};

const vad = new VAD({
  thresholdDb: parseFloat(localStorage.getItem("clip.threshold") || "6"),
});
vad.onUtterance = (pcm) => queueTranscription(pcm);
vad.onState = (speaking, db) => {
  state.speaking = speaking;
  state.lastRms = db;
};

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
function toast(msg, isError) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "show" + (isError ? " err" : "");
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.className = ""), 3000);
}
function setConnText(text, ok) {
  $("conn-text").textContent = text;
  $("conn-dot").className = ok === null ? "dot" : ok ? "dot on" : "dot off";
}

// ---------------------------------------------------------------------------
// AT command layer (FIFO response correlation)
// ---------------------------------------------------------------------------
const cmdQueue = [];

function sendAt(raw) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      const i = cmdQueue.indexOf(entry);
      if (i >= 0) cmdQueue.splice(i, 1);
      reject(new Error("AT response timeout: " + raw));
    }, 10000);
    const entry = { resolve, reject, timer };
    cmdQueue.push(entry);
    state.conn
      .sendCommand(raw)
      .then(() => {
        /* response resolves later */
      })
      .catch((e) => {
        clearTimeout(timer);
        const i = cmdQueue.indexOf(entry);
        if (i >= 0) cmdQueue.splice(i, 1);
        reject(e);
      });
  });
}

function onDeviceResponse(json) {
  // Optional: surface device-pushed events for logging.
  const entry = cmdQueue.shift();
  if (entry) {
    clearTimeout(entry.timer);
    entry.resolve(json);
  }
}

async function gstat() {
  try {
    const r = await sendAt("AT+GSTAT");
    if (r && r.ok && r.data) {
      $("stat-state").textContent = r.data.state || "--";
      const b = r.data.battery;
      if (typeof b === "number") $("stat-batt").textContent = b + "%";
      if (r.data.mode) $("stat-mode").textContent = r.data.mode;
    }
  } catch (e) {
    /* ignore polling errors */
  }
}

// ---------------------------------------------------------------------------
// Transcription (WAV -> /api/transcribe -> Groq)
// ---------------------------------------------------------------------------
function addTranscript(text, meta, durationSec) {
  const line = document.createElement("div");
  line.className = "tl";
  const ts = new Date().toLocaleTimeString();
  line.innerHTML =
    `<span class="tl-ts">${ts}</span><span class="tl-meta">${meta}</span>` +
    `<span class="tl-text"></span>`;
  const txt = line.querySelector(".tl-text");
  if (durationSec) line.dataset.dur = durationSec.toFixed(1) + "s";
  if (text) {
    txt.textContent = text;
  } else {
    txt.className += " pending";
    txt.textContent = "…";
  }
  $("transcript").appendChild(line);
  $("transcript").scrollTop = $("transcript").scrollHeight;
  return line;
}

function queueTranscription(pcm) {
  const idx = ++state.utteranceIndex;
  const line = addTranscript(null, `#${idx}`, pcm.length / 16000);
  const txt = line.querySelector(".tl-text");
  txt.textContent = "Transcribing…";
  txt.className += " pending";

  // Serialize so utterances are transcribed and displayed in order.
  state.transcribeChain = state.transcribeChain
    .then(async () => {
      const wav = pcmToWav(pcm);
      const blob = new Blob([wav], { type: "audio/wav" });
      const fd = new FormData();
      fd.append("api_key", localStorage.getItem("clip.groq_key") || "");
      fd.append("model", $("model-select").value || "whisper-large-v3-turbo");
      const lang = $("lang-input").value.trim();
      if (lang) fd.append("language", lang);
      fd.append("file", blob, "utterance.wav");

      let resp;
      try {
        resp = await fetch("/api/transcribe", { method: "POST", body: fd });
      } catch (e) {
        txt.className = "tl-text err";
        txt.textContent = "Proxy unreachable: " + e.message;
        throw e;
      }
      let data = null;
      try {
        data = await resp.json();
      } catch (_) {
        data = null;
      }
      if (!resp.ok || !data || !data.ok) {
        const msg = (data && (data.msg || data.error)) || ("HTTP " + resp.status);
        txt.className = "tl-text err";
        txt.textContent = "Transcription failed: " + msg;
        throw new Error(msg);
      }
      const text = (data.text || "").trim();
      if (text) {
        txt.className = "tl-text";
        txt.textContent = text;
      } else {
        txt.className = "tl-text muted";
        txt.textContent = "(no speech detected)";
      }
      return text;
    })
    .catch(() => {});
}

// ---------------------------------------------------------------------------
// Stream frame handling
// ---------------------------------------------------------------------------
function onStreamFrame(frame) {
  if (!frame || frame.type == null) return;
  switch (frame.type) {
    case FRAME_STREAM_START:
      $("stream-status").textContent = "Streaming session " + (frame.sessionId || "");
      break;
    case FRAME_STREAM_DATA: {
      let pcm;
      try {
        pcm = decodeOpusPacket(frame.payload);
      } catch (e) {
        break;
      }
      if (pcm) vad.push(pcm);
      break;
    }
    case FRAME_STREAM_END:
      $("stream-status").textContent =
        "Stream ended (" + (STREAM_END_REASONS[frame.reason] ?? frame.reason) + ")";
      break;
  }
}

function onVis(data) {
  // 13 packed nibbles (0..10). Map into 13 bars for the spectrum display.
  if (!data || data.length < 7) return;
  const vals = [];
  for (let i = 0; i < 6; i++) {
    vals.push(data[i] & 0x0f, (data[i] >> 4) & 0x0f);
  }
  vals.push(data[6] & 0x0f);
  state.visBars = vals;
}

// ---------------------------------------------------------------------------
// Start / Stop streaming
// ---------------------------------------------------------------------------
async function startStreaming() {
  if (state.streaming) return;
  const key = localStorage.getItem("clip.groq_key");
  if (!key) {
    toast("Enter your Groq API key first", true);
    $("key-input").focus();
    return;
  }

  $("btn-stream").disabled = true;
  $("stream-status").textContent = "Starting…";
  state.utteranceIndex = 0;
  $("transcript").innerHTML = "";
  vad.reset();

  try {
    await ensureOpus();
    if (state.demo) {
      const packets = window.SAMPLE_PACKETS || [];
      if (!packets.length) {
        throw new Error("no demo packets bundled");
      }
      state.demoIdx = 0;
      $("stream-status").textContent = "Demo streaming…";
      startDemoLoop();
      state.streaming = true;
      setStreamUI(true);
      return;
    }

    const start = await sendAt("AT+START=RTC");
    if (!start || !start.ok) {
      const msg = (start && start.msg) || "start failed";
      throw new Error(msg);
    }
    const session = start.data && start.data.session;
    $("stream-status").textContent = "Session " + (session || "?") + " — starting stream…";

    const dl = await sendAt("AT+DOWNLOAD=" + (session || ""));
    if (!dl || !dl.ok) {
      throw new Error((dl && dl.msg) || "download failed");
    }
    state.sessionId = session || null;
    state.streaming = true;
    setStreamUI(true);
  } catch (e) {
    toast("Error: " + e.message, true);
    $("stream-status").textContent = "Failed";
    try {
      await state.conn.sendCommand("AT+STOP\n");
    } catch (_) {}
  } finally {
    $("btn-stream").disabled = false;
  }
}

async function stopStreaming() {
  if (!state.streaming) return;
  vad.flush(); // finalize any in-progress utterance

  if (state.demo) {
    stopDemoLoop();
  } else {
    try {
      await sendAt("AT+STOP");
    } catch (e) {
      toast("Stop error: " + e.message, true);
    }
  }
  state.streaming = false;
  setStreamUI(false);
  $("stream-status").textContent = "Stopped";
}

function setStreamUI(on) {
  $("btn-stream").textContent = on ? "Stop Streaming" : "Start Streaming";
  $("btn-stream").classList.toggle("recording", on);
  $("btn-connect").disabled = on;
}

// ---------------------------------------------------------------------------
// Demo mode (no Bluetooth): replay bundled opus packets
// ---------------------------------------------------------------------------
function startDemoLoop() {
  const packets = window.SAMPLE_PACKETS || [];
  if (!packets.length) {
    toast("No demo packets bundled", true);
    return;
  }
  let last = performance.now();  state.demoFrame = setInterval(() => {
    const now = performance.now();
    const elapsed = now - last;
    last = now;
    // Feed ~1 packet per 20ms of wall time; skip packets if we fall behind
    // so the demo runs in real time.
    const n = Math.max(1, Math.round(elapsed / 20));
    for (let i = 0; i < n; i++) {
      if (state.demoIdx >= packets.length) {
        stopDemoLoop();
        state.streaming = false;
        setStreamUI(false);
        $("stream-status").textContent = "Demo finished";
        return;
      }
      const b64 = packets[state.demoIdx++];
      try {
        const bin = atob(b64);
        const u8 = new Uint8Array(bin.length);
        for (let j = 0; j < bin.length; j++) u8[j] = bin.charCodeAt(j);
        const pcm = decodeOpusPacket(u8);
        if (pcm) vad.push(pcm);
      } catch (e) {
        /* skip bad packet */
      }
    }
  }, 20);
}
function stopDemoLoop() {
  if (state.demoFrame) {
    clearInterval(state.demoFrame);
    state.demoFrame = null;
  }
}

// ---------------------------------------------------------------------------
// Meter rendering (energy + spectrum)
// ---------------------------------------------------------------------------
function drawMeter() {
  const canvas = $("meter-canvas");
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.scale(dpr, dpr);

  ctx.fillStyle = "#0b1220";
  ctx.fillRect(0, 0, w, h);

  // live spectrum bars (from AudioVis when connected, else energy fallback)
  const bars = state.visBars ? state.visBars : null;
  const N = bars ? bars.length : 24;
  const gap = 2, bw = (w - gap * (N - 1)) / N;
  for (let i = 0; i < N; i++) {
    let level;
    if (bars) {
      level = (bars[i] || 0) / 10;
    } else {
      const db = state.lastRms;
      level = db < -70 ? 0 : Math.max(0, (db + 70) / 60);
    }
    const bh = Math.max(2, level * (h - 8));
    const x = i * (bw + gap), y = h - bh;
    const hue = state.speaking ? 10 : 150; // red-ish when speaking, green idle
    ctx.fillStyle = `hsl(${hue}, 80%, ${40 + level * 30}%)`;
    ctx.fillRect(x, y, bw, bh);
  }

  // speaking indicator
  $("vad-state").textContent = state.streaming
    ? state.speaking
      ? "speaking"
      : "listening"
    : "idle";
  $("vad-state").className = "vad-state " + (state.speaking ? "speaking" : "");
  requestAnimationFrame(drawMeter);
}

// ---------------------------------------------------------------------------
// Connection handling
// ---------------------------------------------------------------------------
async function doConnect() {
  if (state.conn && state.conn.connected) {
    toast("Already connected");
    return;
  }
  if (!("bluetooth" in navigator)) {
    toast("Web Bluetooth not available in this browser (use Chrome/Edge)", true);
    return;
  }
  $("btn-connect").disabled = true;
  setConnText("Scanning…", null);
  try {
    const conn = new ClipConnection({
      onResponse: onDeviceResponse,
      onStreamFrame: onStreamFrame,
      onVis: onVis,
      onDisconnect: onDisconnected,
    });
    await conn.connect();
    state.conn = conn;
    setConnText("Connected", true);
    toast("Connected");
    await gstat();
  } catch (e) {
    setConnText("Disconnected", false);
    toast("Connect failed: " + e.message, true);
  } finally {
    $("btn-connect").disabled = false;
  }
}

function onDisconnected() {
  if (state.streaming) {
    state.streaming = false;
    stopDemoLoop();
    setStreamUI(false);
    $("stream-status").textContent = "Disconnected";
  }
  setConnText("Disconnected", false);
  toast("Device disconnected", true);
}

async function doDisconnect() {
  if (state.streaming) await stopStreaming();
  if (state.conn) {
    await state.conn.disconnect().catch(() => {});
    state.conn = null;
  }
  setConnText("Disconnected", false);
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
  $("btn-connect").addEventListener("click", () => {
    if (state.conn && state.conn.connected) doDisconnect();
    else doConnect();
  });
  $("btn-stream").addEventListener("click", () => {
    if (state.streaming) stopStreaming();
    else startStreaming();
  });
  $("demo-toggle").addEventListener("change", (e) => {
    state.demo = e.target.checked;
    if (state.demo) toast("Demo mode on — no Bluetooth needed");
    else toast("Demo mode off");
  });
  $("threshold-range").addEventListener("input", (e) => {
    const v = parseFloat(e.target.value);
    vad.thresholdDb = v;
    $("threshold-val").textContent = v.toFixed(0) + " dB";
    localStorage.setItem("clip.threshold", String(v));
  });

  // Load saved settings.
  const savedKey = localStorage.getItem("clip.groq_key") || "";
  if (savedKey) $("key-input").value = savedKey;
  const savedLang = localStorage.getItem("clip.lang");
  if (savedLang) $("lang-input").value = savedLang;
  const savedModel = localStorage.getItem("clip.model");
  if (savedModel) $("model-select").value = savedModel;

  $("key-input").addEventListener("change", (e) => {
    localStorage.setItem("clip.groq_key", e.target.value.trim());
  });
  $("lang-input").addEventListener("change", (e) => {
    localStorage.setItem("clip.lang", e.target.value.trim());
  });
  $("model-select").addEventListener("change", (e) => {
    localStorage.setItem("clip.model", e.target.value);
  });

  $("threshold-range").value = vad.thresholdDb;
  $("threshold-val").textContent = vad.thresholdDb.toFixed(0) + " dB";

  drawMeter();
  // Poll status every 5s while connected (not while streaming to reduce noise).
  setInterval(async () => {
    if (state.conn && state.conn.connected && !state.streaming) await gstat();
  }, 5000);
});
