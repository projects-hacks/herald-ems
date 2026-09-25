// Shared mono PCM and WAV encoding for ambient audio and push-to-talk.
export function encodeWav(chunks: Float32Array[], inputRate: number): Blob {
  const input = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
  let offset = 0;
  for (const chunk of chunks) { input.set(chunk, offset); offset += chunk.length; }
  const rate = 16000, ratio = inputRate / rate;
  const count = Math.floor(input.length / ratio);
  const samples = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    const start = Math.floor(i * ratio), end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0; for (let j = start; j < end; j++) sum += input[j];
    const x = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
    samples[i] = x;
  }
  return wav(samples, rate);
}

export function wav(samples: Float32Array, rate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const word = (at: number, text: string) => [...text].forEach((ch, i) => view.setUint8(at + i, ch.charCodeAt(0)));
  word(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); word(8, "WAVE"); word(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); word(36, "data");
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, i) => { const n = Math.max(-1, Math.min(1, sample)); view.setInt16(44 + i * 2, n * (n < 0 ? 32768 : 32767), true); });
  return new Blob([buffer], { type: "audio/wav" });
}

export function join(chunks: Float32Array[]): Float32Array {
  const out = new Float32Array(chunks.reduce((sum, c) => sum + c.length, 0));
  let offset = 0;
  chunks.forEach((c) => { out.set(c, offset); offset += c.length; });
  return out;
}
