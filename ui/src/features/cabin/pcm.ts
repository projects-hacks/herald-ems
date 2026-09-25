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
