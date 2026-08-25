// Audio helpers: wrap 16 kHz mono PCM16 samples into a WAV file blob.

// Convert an Int16Array of 16 kHz mono samples into a WAV (PCM16) byte array.
export function pcmToWav(pcm) {
  const numSamples = pcm.length;
  const buf = new ArrayBuffer(44 + numSamples * 2);
  const dv = new DataView(buf);
  const wstr = (o, s) => {
    for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i));
  };
  wstr(0, "RIFF");
  dv.setUint32(4, 36 + numSamples * 2, true);
  wstr(8, "WAVE");
  wstr(12, "fmt ");
  dv.setUint32(16, 16, true);
  dv.setUint16(20, 1, true); // PCM
  dv.setUint16(22, 1, true); // mono
  dv.setUint32(24, 16000, true);
  dv.setUint32(28, 16000 * 2, true);
  dv.setUint16(32, 2, true);
  dv.setUint16(34, 16, true);
  wstr(36, "data");
  dv.setUint32(40, numSamples * 2, true);
  new Int16Array(buf, 44).set(pcm);
  return new Uint8Array(buf);
}
