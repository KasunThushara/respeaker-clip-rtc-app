#!/usr/bin/env node
// Clip Live Stream — tiny local server.
//
//   1. Serves the web app (./static) for Web Bluetooth to work on localhost.
//   2. POST /api/transcribe forwards an audio upload to the Groq Whisper API
//      using the API key the user typed into the UI (never stored on disk).
//
// Usage:  node server.js [port]
// Defaults to port 8080. Open http://localhost:8080 in Chrome/Edge.

import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const PORT = Number(process.argv[2]) || 8080;
const ROOT = fileURLToPath(new URL("./static", import.meta.url));

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");

  if (req.method === "POST" && url.pathname === "/api/transcribe") {
    return handleTranscribe(req, res);
  }

  // ---- Static files --------------------------------------------------------
  let pathname = decodeURIComponent(url.pathname);
  if (pathname === "/") pathname = "/index.html";
  const file = normalize(join(ROOT, pathname));
  if (!file.startsWith(ROOT)) {
    res.writeHead(403).end("Forbidden");
    return;
  }
  try {
    const data = await readFile(file);
    res.writeHead(200, { "Content-Type": MIME[extname(file)] || "application/octet-stream" });
    res.end(data);
  } catch (_) {
    res.writeHead(404).end("Not found");
  }
});

// ---------------------------------------------------------------------------
// POST /api/transcribe
// ---------------------------------------------------------------------------
async function handleTranscribe(req, res) {
  const bytes = await readBody(req, 25 * 1024 * 1024);
  if (!bytes) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, msg: "no body" }));
    return;
  }
  const parts = parseMultipart(bytes, req.headers["content-type"] || "");
  const get = (name) => {
    const p = parts.find((x) => x.name === name);
    return p ? p.data.toString("utf8").trim() : "";
  };
  const filePart = parts.find((x) => x.filename);

  const apiKey = get("api_key");
  const model = get("model") || "whisper-large-v3-turbo";
  const language = get("language");

  if (!apiKey) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, msg: "missing api_key" }));
    return;
  }
  if (!filePart || filePart.data.length === 0) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, msg: "missing audio file" }));
    return;
  }

  // ==== ADJUST ME ===========================================================
  // This is the only part you need to change to point at your own proxy or to
  // tweak the Groq request. `filePart.data` is the WAV (16 kHz mono PCM16),
  // `filePart.filename` its name, `model` the selected model, `language` an
  // optional 2-letter code, and `apiKey` the key the user typed in the UI.
  // ==========================================================================
  try {
    const fd = new FormData();
    fd.append("model", model);
    if (language) fd.append("language", language);
    fd.append("temperature", "0");
    fd.append("response_format", "verbose_json");
    fd.append(
      "file",
      new Blob([filePart.data], { type: "audio/wav" }),
      filePart.filename || "utterance.wav",
    );

    const groq = await fetch("https://api.groq.com/openai/v1/audio/transcriptions", {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}` },
      body: fd,
    });
    const data = await groq.json();

    if (!groq.ok) {
      res.writeHead(groq.status, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: false, msg: (data && data.error && data.error.message) || "Groq error " + groq.status }));
      return;
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true, text: data.text || "" }));
  } catch (e) {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, msg: "proxy error: " + e.message }));
  }
}

// ---- helpers ---------------------------------------------------------------
function readBody(req, limit) {
  return new Promise((resolve) => {
    const chunks = [];
    let size = 0;
    req.on("data", (c) => {
      size += c.length;
      if (size > limit) {
        req.destroy();
        resolve(null);
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", () => resolve(null));
  });
}

function parseMultipart(buf, contentType) {
  const m = /boundary=(?:"([^"]+)"|([^;]+))/.exec(contentType);
  if (!m) return [];
  const boundary = "--" + (m[1] || m[2]).trim();
  const parts = [];
  const segments = buf.toString("latin1").split(boundary);
  for (const seg of segments) {
    if (seg === "--" || seg === "--\r\n") continue;
    const headerEnd = seg.indexOf("\r\n\r\n");
    if (headerEnd < 0) continue;
    const headerText = seg.slice(0, headerEnd);
    let bodyText = seg.slice(headerEnd + 4);
    if (bodyText.endsWith("\r\n")) bodyText = bodyText.slice(0, -2);
    const nameMatch = /name="([^"]*)"/.exec(headerText);
    const fileMatch = /filename="([^"]*)"/.exec(headerText);
    if (!nameMatch) continue;
    parts.push({
      name: nameMatch[1],
      filename: fileMatch ? fileMatch[1] : null,
      data: Buffer.from(bodyText, "latin1"),
    });
  }
  return parts;
}

server.listen(PORT, () => {
  console.log(`Clip Live Stream → http://localhost:${PORT}`);
});
