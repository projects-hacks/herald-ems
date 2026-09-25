// Voice activity detection and endpointing for the cabin microphone: only speech is sent, cut where the speaker
// paused. Whisper invents text for silence and noise ("Thank you.", subtitle credits, a guessed language looping) and
// garbles words cut mid-way, so a fixed 8 s window is the wrong unit. Energy against an adaptive noise floor is the
// classic endpointer; the server's Whisper no-speech, language and repetition checks are the second layer.

export const ENDPOINT = {
  preRollMs: 300,        // audio kept from before speech starts, so the first syllable is not clipped
  hangoverMs: 800,       // a pause this long ends the utterance
  minSpeechMs: 350,      // shorter bursts (a cough, a door) are not sent
  maxUtteranceMs: 15000, // a long monologue is cut here (Whisper's window is 30 s)
  onsetRatio: 3,         // speech = louder than the noise floor by this factor...
  minRms: 0.008,         // ...and above this absolute level (full scale = 1)
  floorAlpha: 0.05,      // how fast the noise floor follows the room while nobody speaks
};

/** Feed blocks of samples; returns an utterance (the blocks to send) when one ends, otherwise null. */
export class Endpointer {
  private floor = ENDPOINT.minRms / ENDPOINT.onsetRatio;
  private pre: Float32Array[] = [];
  private preMs = 0;
  private utterance: Float32Array[] = [];
  private utteranceMs = 0;
  private speechMs = 0;
  private silenceMs = 0;
  private rate: number;
  constructor(rate: number) { this.rate = rate; }

  get speaking() { return this.utterance.length > 0; }

  push(block: Float32Array): Float32Array[] | null {
    const ms = (block.length / this.rate) * 1000;
    let sum = 0; for (let i = 0; i < block.length; i++) sum += block[i] * block[i];
    const rms = Math.sqrt(sum / Math.max(1, block.length));
    const voiced = rms > Math.max(ENDPOINT.minRms, this.floor * ENDPOINT.onsetRatio);
    if (!this.speaking) {
      if (!voiced) {
        this.floor += ENDPOINT.floorAlpha * (rms - this.floor);            // the room's own sound
        this.pre.push(block); this.preMs += ms;
        while (this.preMs > ENDPOINT.preRollMs && this.pre.length > 1) this.preMs -= (this.pre.shift()!.length / this.rate) * 1000;
        return null;
      }
      this.utterance = [...this.pre, block]; this.utteranceMs = this.preMs + ms; this.speechMs = ms; this.silenceMs = 0;
      this.pre = []; this.preMs = 0;
      return null;
    }
    this.utterance.push(block); this.utteranceMs += ms;
    if (voiced) { this.speechMs += ms; this.silenceMs = 0; } else this.silenceMs += ms;
    if (this.silenceMs >= ENDPOINT.hangoverMs || this.utteranceMs >= ENDPOINT.maxUtteranceMs) return this.end();
    return null;
  }

  /** Ends the current utterance (pause, or the call ends): what is left, if it held enough speech to send. */
  end(): Float32Array[] | null {
    const out = this.utterance, speech = this.speechMs;
    this.utterance = []; this.utteranceMs = 0; this.speechMs = 0; this.silenceMs = 0;
    return out.length && speech >= ENDPOINT.minSpeechMs ? out : null;
  }
}
