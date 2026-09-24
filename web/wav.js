// 16 kHz mono WAV from the browser microphone: the capture code shared by the NOW screen's push-to-talk (app.js)
// and the field-evaluation recorder (eval/field/recorder.html), so field clips are encoded exactly as the app's are.
function concat(chunks) { const n = chunks.reduce((a, c) => a + c.length, 0); const o = new Float32Array(n); let i = 0; for (const c of chunks) { o.set(c, i); i += c.length; } return o; }
function downsample(buf, from, to) {
  if (from === to) return buf;
  const ratio = from / to, out = new Float32Array(Math.floor(buf.length / ratio));
  for (let i = 0; i < out.length; i++) { const s = Math.floor(i * ratio), e = Math.min(Math.floor((i + 1) * ratio), buf.length); let sum = 0; for (let j = s; j < e; j++) sum += buf[j]; out[i] = sum / Math.max(1, e - s); }
  return out;
}
function encodeWav(samples, sr) {
  const b = new ArrayBuffer(44 + samples.length * 2), v = new DataView(b);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sr, true);
  v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) { const x = Math.max(-1, Math.min(1, samples[i])); v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true); }
  return b;
}
