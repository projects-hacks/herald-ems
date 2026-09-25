// The classic recorder's mono PCM encoding, with a bounded downsample to 16 kHz.
export function encodeWav(chunks: Float32Array[], inputRate: number): Blob {
  const input = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
  let offset = 0;
  for (const chunk of chunks) { input.set(chunk, offset); offset += chunk.length; }
  const rate = 16000, ratio = inputRate / rate;
  const count = Math.floor(input.length / ratio);
  const view = new DataView(new ArrayBuffer(44 + count * 2));
  const word = (at: number, text: string) => [...text].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  word(0, "RIFF"); view.setUint32(4, 36 + count * 2, true); word(8, "WAVE"); word(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); word(36, "data"); view.setUint32(40, count * 2, true);
  for (let i = 0; i < count; i++) {
    const start = Math.floor(i * ratio), end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0; for (let j = start; j < end; j++) sum += input[j];
    const x = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
    view.setInt16(44 + i * 2, x < 0 ? x * 32768 : x * 32767, true);
  }
  return new Blob([view.buffer], { type: "audio/wav" });
}
