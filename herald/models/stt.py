"""Local speech-to-text: Whisper large-v3-turbo on the GB10 GPU (10.4 s clip -> 0.31 s, 1.7 GiB, measured).
The vocabulary priming prompt is content (config/prompts/stt_prompt.txt), and so are the gates that decide whether
a clip is speech Herald reads at all (config/stt.yaml, herald/models/stt_gates.py)."""
from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from ..config import load_text
from ..core.ports import UsageRecorder
from ..telemetry import tracking
from .stt_gates import ClipSignals, SpeechGates, compression_ratio
from .weights import local_weights


class WhisperSTT:
    """The `SpeechToText` interface. The model loads on first use (or `warm()`).

    Every clip is first read by Whisper's own first decoder step (`_signals`): how probable it is that the window
    holds no speech, which language it hears and how surely it is one Herald reads, the way openai-whisper
    computes `no_speech_prob` and `detect_language`. The gates drop a clip on those signals before any text is
    decoded, and drop a decode that looped afterwards, so a silent or noisy cabin clip never reaches the extractor
    as words (and never costs the ~6-10 s a looping decode takes)."""

    WINDOW = 30.0                             # seconds in one Whisper input window (batching needs clips within it)

    def __init__(self, model: str, usage: Optional[UsageRecorder] = None, device: str = "cuda:0", offline: bool = True,
                 gates: Optional[SpeechGates] = None):
        self.model = model
        self.offline = offline
        self.usage = usage
        self.device = device
        self.prompt = load_text("prompts/stt_prompt.txt")
        self.gates = gates or SpeechGates.from_config()
        self._pipe = None
        self._tokens = None                   # (start token, no-speech token, {language code: token id}) once loaded
        self._lock = threading.Lock()

    def ready(self) -> bool:
        return self._pipe is not None

    def _load(self):
        with self._lock:
            if self._pipe is None:
                import torch
                from transformers import pipeline
                self._pipe = pipeline("automatic-speech-recognition", model=local_weights(self.model, self.offline),
                                      dtype=torch.bfloat16, device=self.device)
        return self._pipe

    def warm(self) -> None:
        """Load the model and run both legs once (the signals and a decode) so the first real clip pays no
        first-call cost; through the gates a silent clip would never reach the decoder."""
        pipe = self._load()
        silence = np.zeros(16000, dtype=np.float32)
        self._signals([silence])
        pipe({"raw": silence, "sampling_rate": 16000}, generate_kwargs=self._kwargs(pipe, None),
             return_timestamps=True)

    def _kwargs(self, pipe, language: Optional[str]) -> dict:
        kwargs = {"task": "transcribe"}
        if language:
            kwargs["language"] = language
        try:
            kwargs["prompt_ids"] = pipe.tokenizer.get_prompt_ids(self.prompt, return_tensors="pt").to(self.device)
        except Exception:
            pass
        return kwargs

    # ---------- the model's own signals ----------
    def _token_ids(self, pipe) -> tuple[int, int, dict[str, int]]:
        if self._tokens is None:
            cfg, tok = pipe.model.generation_config, pipe.tokenizer
            no_speech = tok.convert_tokens_to_ids("<|nospeech|>")
            if no_speech is None or no_speech == tok.unk_token_id:
                no_speech = cfg.no_timestamps_token_id - 1          # where transformers looks for it too
            languages = {token.strip("<|>"): i for token, i in cfg.lang_to_id.items()}
            self._tokens = (cfg.decoder_start_token_id, no_speech, languages)
        return self._tokens

    def _signals(self, clips: list[np.ndarray]) -> list[ClipSignals]:
        """One decoder step from <|startoftranscript|> on each clip's encoder output, with no prompt in front:
        P(<|nospeech|>) over the whole vocabulary, the most probable language token (openai-whisper's
        `no_speech_prob` and `detect_language`), and the language mass on the languages Herald reads. The
        features are the same 30 s log-mel window transcription sees, so a clip longer than the window is judged
        on its first 30 s."""
        import torch
        pipe = self._load()
        model = pipe.model
        start, no_speech, languages = self._token_ids(pipe)
        features = pipe.feature_extractor(clips, sampling_rate=16000, return_tensors="pt")["input_features"]
        codes = list(languages)
        read = [i for i, c in enumerate(codes) if c in self.gates.languages]
        with torch.inference_mode():
            encoded = model.get_encoder()(features.to(model.device, dtype=model.dtype))
            ids = torch.full((len(clips), 1), start, dtype=torch.long, device=model.device)
            logits = model(encoder_outputs=encoded, decoder_input_ids=ids, use_cache=False).logits[:, -1].float()
            p_no_speech = logits.softmax(-1)[:, no_speech].tolist()
            p_language = logits[:, [languages[c] for c in codes]].softmax(-1)
            best = p_language.argmax(-1)
            p_best = p_language.gather(1, best[:, None])[:, 0].tolist()
            p_read = p_language[:, read].sum(-1).tolist()
        return [ClipSignals(no_speech_prob=p_no_speech[i], language=codes[int(best[i])], language_prob=p_best[i],
                            read_prob=p_read[i]) for i in range(len(clips))]

    # ---------- results ----------
    def _result(self, out: Optional[dict], seconds: float, signals: Optional[ClipSignals] = None,
                dropped: Optional[str] = None, gate: bool = True) -> dict:
        text = (out or {}).get("text", "").strip()
        if self.prompt[:30] in text:          # Whisper occasionally echoes the prompt
            text = text.replace(self.prompt, "").strip()
        ratio = compression_ratio(text)
        if gate and dropped is None and text:
            dropped = self.gates.after_decoding(ratio)
        chunks = [] if dropped else [{"text": c["text"].strip(), "t": list(c.get("timestamp") or (None, None))}
                                     for c in (out or {}).get("chunks", [])]
        result = {"text": "" if dropped else text, "chunks": chunks, "seconds": round(seconds, 2),
                  "language": signals.language if signals else None,
                  "signals": {"no_speech_prob": round(signals.no_speech_prob, 4) if signals else None,
                              "language_prob": round(signals.language_prob, 4) if signals else None,
                              "read_language_prob": round(signals.read_prob, 4) if signals else None,
                              "compression_ratio": round(ratio, 3)}}
        if dropped:
            result["dropped"] = dropped
        return result

    def _record(self, result: dict) -> dict:
        if self.usage:
            self.usage.record_stt(result["seconds"])
            if result.get("dropped"):
                self.usage.record_stt_dropped(result["dropped"])
        return result

    @staticmethod
    def _mono16k(audio: np.ndarray, sr: int) -> np.ndarray:
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio = audio.astype(np.float32)
        if sr != 16000:
            import torch
            import torchaudio.functional as AF
            audio = AF.resample(torch.from_numpy(audio), sr, 16000).numpy()
        return audio

    def transcribe(self, audio: np.ndarray, sr: int, language: Optional[str] = None) -> dict:
        pipe = self._load()
        audio = self._mono16k(audio, sr)
        out = None
        with tracking(self.usage, "stt"):
            signals = self._signals([audio])[0]
            dropped = self.gates.before_decoding(signals)
            if dropped is None:               # the language it heard goes with the decode: not detected twice
                out = pipe({"raw": audio, "sampling_rate": 16000},
                           generate_kwargs=self._kwargs(pipe, language or signals.language), return_timestamps=True)
        return self._record(self._result(out, len(audio) / 16000, signals, dropped))

    def transcribe_many(self, clips: list[np.ndarray], sr: int, language: Optional[str] = None,
                        batch_size: int = 16, gate: bool = True) -> list[dict]:
        """`transcribe` for many clips in GPU batches: the same prompt, settings, gates and echo stripping (offline
        measurement and training-data work; the app transcribes one capture at a time). `gate=False` decodes every
        clip, for measuring what the gates would have dropped. Languages are not passed on here: a batch holds
        clips in any mix, so generation detects each clip's language itself, as it did before the gates."""
        pipe = self._load()
        audio = [self._mono16k(a, sr) for a in clips]
        signals: list[Optional[ClipSignals]] = [None] * len(audio)
        dropped: list[Optional[str]] = [None] * len(audio)
        if gate:
            for start in range(0, len(audio), batch_size):
                for i, s in enumerate(self._signals(audio[start:start + batch_size]), start=start):
                    signals[i], dropped[i] = s, self.gates.before_decoding(s)
        kept = [i for i in range(len(audio)) if dropped[i] is None]
        short = [i for i in kept if len(audio[i]) <= self.WINDOW * 16000]      # one Whisper window each
        outs: dict[int, dict] = {}
        if short:
            res = pipe([{"raw": audio[i], "sampling_rate": 16000} for i in short],
                       generate_kwargs=self._kwargs(pipe, language), return_timestamps=True, batch_size=batch_size)
            outs.update(zip(short, res))
        for i in [i for i in kept if i not in short]:                            # long-form: one at a time
            outs[i] = pipe({"raw": audio[i], "sampling_rate": 16000}, generate_kwargs=self._kwargs(pipe, language),
                           return_timestamps=True)
        return [self._record(self._result(outs.get(i), len(a) / 16000, signals[i], dropped[i], gate=gate))
                for i, a in enumerate(audio)]
