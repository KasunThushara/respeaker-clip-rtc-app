// Energy-based Voice Activity Detector.
//
// Operates on 16 kHz mono PCM16 frames (20 ms each). It keeps a running
// noise-floor estimate, marks frames above (noise floor + threshold) as
// speech, and uses a hangover timer so a brief pause inside a sentence does
// not split the utterance. When an utterance ends (silence longer than the
// hangover, or an explicit flush), the buffered PCM is handed to a callback.

const SAMPLE_RATE = 16000;
const FRAME_MS = 20;

// Convert an Int16Array to its RMS level in dBFS (0 dB = full scale).
export function rmsDb(pcm) {
  if (!pcm || pcm.length === 0) return -Infinity;
  let sum = 0;
  for (let i = 0; i < pcm.length; i++) sum += pcm[i] * pcm[i];
  const rms = Math.sqrt(sum / pcm.length) || 1e-9;
  return 20 * Math.log10(rms / 32768);
}

export class VAD {
  // config:
  //   thresholdDb     speech level above the noise floor (dB), default 6
  //   hangoverMs      silence after speech that closes an utterance, default 500
  //   minSpeechMs     minimum speech to accept an utterance, default 250
  //   maxUtteranceMs  force-flush long utterances, default 30000
  //   preRollMs       PCM captured before speech onset, default 300
  constructor({
    thresholdDb = 6,
    hangoverMs = 500,
    minSpeechMs = 250,
    maxUtteranceMs = 30000,
    preRollMs = 300,
  } = {}) {
    this.thresholdDb = thresholdDb;
    this.hangoverMs = hangoverMs;
    this.minSpeechMs = minSpeechMs;
    this.maxUtteranceMs = maxUtteranceMs;
    this.preRollMs = preRollMs;

    this.speaking = false;
    this.energy = 0; // dBFS of the most recent frame

    this._noiseFloor = -55;
    this._speechMs = 0;
    this._silenceMs = 0;
    this._utterMs = 0;
    this._preRoll = [];
    this._pcm = [];

    // external hooks
    this.onUtterance = null; // (pcm Int16Array) => void
    this.onState = null; // (speaking:boolean, energyDb:number) => void
  }

  reset() {
    this.speaking = false;
    this._speechMs = 0;
    this._silenceMs = 0;
    this._utterMs = 0;
    this._preRoll = [];
    this._pcm = [];
  }

  // Feed one frame of PCM (Int16Array, 320 samples for 20 ms @ 16 kHz).
  push(pcm) {
    const db = rmsDb(pcm);
    this.energy = db;

    // Adapt the noise floor only when we are confident there is no speech.
    if (!this.speaking && isFinite(db) && db > -90) {
      this._noiseFloor += 0.05 * (db - this._noiseFloor);
    }

    const isSpeech = isFinite(db) && db >= this._noiseFloor + this.thresholdDb;

    if (isSpeech) {
      this._speechMs += FRAME_MS;
      this._silenceMs = 0;

      if (!this.speaking) {
        // Start of an utterance: bring along the recent pre-roll.
        this._pcm = this._preRoll.slice();
        this.speaking = true;
        this._utterMs = 0;
      }
      this._pcm.push(pcm);
      this._utterMs += FRAME_MS;
    } else {
      if (this.speaking) {
        this._silenceMs += FRAME_MS;
        this._pcm.push(pcm); // keep trailing silence in the buffer
        this._utterMs += FRAME_MS;
        if (this._silenceMs >= this.hangoverMs) this._finish();
      } else {
        // Buffer the pre-roll ring (keeps word onsets for the next utterance).
        this._preRoll.push(pcm);
        if (this._preRoll.length > this.preRollMs / FRAME_MS) this._preRoll.shift();
      }
    }

    // Force-flush very long utterances so the transcript keeps flowing.
    if (this.speaking && this._utterMs >= this.maxUtteranceMs) this._finish();

    if (this.onState) this.onState(this.speaking, db);
  }

  _finish() {
    const totalSpeech = this._speechMs;
    const pcm = this._pcm;
    this.speaking = false;
    this._speechMs = 0;
    this._silenceMs = 0;
    this._utterMs = 0;
    this._preRoll = [];
    this._pcm = [];

    if (totalSpeech < this.minSpeechMs || pcm.length === 0) return; // noise/click

    let total = 0;
    for (const f of pcm) total += f.length;
    const out = new Int16Array(total);
    let o = 0;
    for (const f of pcm) {
      out.set(f, o);
      o += f.length;
    }
    if (this.onUtterance) this.onUtterance(out);
  }

  // Flush any in-progress utterance (e.g. on Stop).
  flush() {
    if (this.speaking) this._finish();
    this._preRoll = [];
  }
}
