// ClipProtocol — GATT/AT client + STREAM_DATA frame parser.
//
// Talks to the reSpeaker Clip over Web Bluetooth. Service UUID and
// characteristics match the firmware on the feat/rtc-live-streaming branch.
//
// Service:  6e400001-b5a3-f393-e0a9-e50e24dcca9e
//   Command   (write)   6e400002-...  app -> device (AT command strings)
//   Response  (notify)  6e400003-...  device -> app (JSON)
//   FileData  (notify)  6e400004-...  device -> app (binary frames)
//   AudioVis  (notify)  6e400005-...  device -> app (7-byte energy levels)
//
// RTC live stream frames on FileData:
//   0x13 STREAM_START [type][sid_len][session_id]
//   0x14 STREAM_DATA  [type][seq:2 LE][len:2 LE][opus packet]  (one 20 ms frame)
//   0x15 STREAM_END   [type][reason:1]

export const CLIP_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e";
export const CH_CMD = "6e400002-b5a3-f393-e0a9-e50e24dcca9e";
export const CH_RSP = "6e400003-b5a3-f393-e0a9-e50e24dcca9e";
export const CH_FILE = "6e400004-b5a3-f393-e0a9-e50e24dcca9e";
export const CH_VIS = "6e400005-b5a3-f393-e0a9-e50e24dcca9e";

export const FRAME_FILE_START = 0x10;
export const FRAME_TRANSFER_DONE = 0x12;
export const FRAME_STREAM_START = 0x13;
export const FRAME_STREAM_DATA = 0x14;
export const FRAME_STREAM_END = 0x15;

export const STREAM_END_REASONS = ["stopped", "start timeout", "BLE disconnect"];

const enc = new TextEncoder();

// Parse one Uint8Array FileData notification into a frame descriptor.
export function parseFileDataFrame(u8) {
  if (!u8 || u8.length === 0) return { type: null };
  const type = u8[0];
  switch (type) {
    case FRAME_STREAM_DATA: {
      // [0x14][seq:2 LE][len:2 LE][payload]
      const seq = u8[1] | (u8[2] << 8);
      const len = u8[3] | (u8[4] << 8);
      return {
        type,
        seq,
        len,
        payload: u8.subarray(5, 5 + len),
      };
    }
    case FRAME_STREAM_START: {
      const sidLen = u8[1];
      const sessionId = new TextDecoder().decode(u8.subarray(2, 2 + sidLen));
      return { type, sessionId };
    }
    case FRAME_STREAM_END:
      return { type, reason: u8[1] || 0 };
    default:
      // File-transfer frames (0x10/0x11/0x12/0x01) are out of scope for the
      // streaming web app — just tag them so callers can ignore them.
      return { type };
  }
}

// A Web Bluetooth connection wrapper.
export class ClipConnection {
  constructor({ onResponse, onStreamFrame, onDisconnect, onVis }) {
    this.onResponse = onResponse;
    this.onStreamFrame = onStreamFrame;
    this.onDisconnect = onDisconnect;
    this.onVis = onVis;
    this.device = null;
    this.server = null;
    this.service = null;
    this.chars = {};
    this._rspBuf = "";
  }

  get connected() {
    return !!(this.server && this.server.connected);
  }

  async connect() {
    this.device = await navigator.bluetooth.requestDevice({
      filters: [{ services: [CLIP_SERVICE] }],
      // Accept devices advertising the service or named "Clip".
      optionalServices: [CLIP_SERVICE],
      // Fallback filter so discovery also works when the name is set.
    });
    this.device.addEventListener("gattserverdisconnected", () => {
      if (this.onDisconnect) this.onDisconnect();
    });

    this.server = await this.device.gatt.connect();
    this.service = await this.server.getPrimaryService(CLIP_SERVICE);
    const [cmd, rsp, file, vis] = await Promise.all([
      this.service.getCharacteristic(CH_CMD),
      this.service.getCharacteristic(CH_RSP),
      this.service.getCharacteristic(CH_FILE),
      this.service
        .getCharacteristic(CH_VIS)
        .catch(() => null),
    ]);
    this.chars = { cmd, rsp, file, vis };

    // Enable notifications BEFORE any AT command so the device accepts
    // AT+START=RTC (it requires file-data notifications to be enabled).
    await rsp.startNotifications();
    rsp.addEventListener("characteristicvaluechanged", (e) =>
      this._onResponse(e.target.value),
    );
    await file.startNotifications();
    file.addEventListener("characteristicvaluechanged", (e) =>
      this._onFileData(e.target.value),
    );
    if (vis) {
      try {
        await vis.startNotifications();
        vis.addEventListener("characteristicvaluechanged", (e) => {
          if (this.onVis) this.onVis(new Uint8Array(e.target.value.buffer));
        });
      } catch (_) {
        /* visualization is optional */
      }
    }
  }

  _onResponse(dataView) {
    const bytes = new Uint8Array(dataView.buffer.slice(0));
    this._rspBuf += new TextDecoder().decode(bytes);
    // Firmware sends one complete JSON response per notification, but keep a
    // small reassembly window in case a long response is split across
    // notifications. Process every balanced top-level JSON object found.
    for (;;) {
      const start = this._rspBuf.indexOf("{");
      if (start < 0) {
        this._rspBuf = "";
        break;
      }
      const end = this._findBalanced(this._rspBuf, start);
      if (end < 0) break; // need more data
      const json = this._rspBuf.slice(start, end + 1);
      this._rspBuf = this._rspBuf.slice(end + 1);
      let obj;
      try {
        obj = JSON.parse(json);
      } catch (_) {
        continue;
      }
      if (this.onResponse) this.onResponse(obj);
    }
  }

  _findBalanced(s, start) {
    let depth = 0;
    let inStr = false;
    let esc = false;
    for (let i = start; i < s.length; i++) {
      const c = s[i];
      if (inStr) {
        if (esc) esc = false;
        else if (c === "\\") esc = true;
        else if (c === '"') inStr = false;
        continue;
      }
      if (c === '"') inStr = true;
      else if (c === "{") depth++;
      else if (c === "}") {
        depth--;
        if (depth === 0) return i;
      }
    }
    return -1;
  }

  _onFileData(dataView) {
    const frame = parseFileDataFrame(new Uint8Array(dataView.buffer.slice(0)));
    if (this.onStreamFrame) this.onStreamFrame(frame);
  }

  async sendCommand(cmd) {
    if (!this.connected) throw new Error("not connected");
    let payload = cmd;
    if (!payload.endsWith("\n")) payload += "\n";
    await this.chars.cmd.writeValue(enc.encode(payload));
  }

  async disconnect() {
    try {
      if (this.server && this.server.connected) {
        await this.server.disconnect();
      }
    } finally {
      if (this.device) await this.device.gatt.disconnect().catch(() => {});
      this.device = null;
      this.server = null;
      this.service = null;
      this.chars = {};
    }
  }
}
