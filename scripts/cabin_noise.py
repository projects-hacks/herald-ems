"""Synthetic ambulance-cabin noise for the measured ASR layer (MODEL_PLAN §0k "Measured ASR noise").

The noise is built from four parts, each normalized to unit RMS before mixing:
- engine rumble: the first four harmonics (weights 1, .6, .35, .2) of a firing frequency drawn from `engine_hz`,
  with a slow +-3% rpm wobble;
- road noise: brown noise (white noise through a leaky integrator, pole 0.995) plus pink noise (white noise shaped
  1/sqrt(f) in the frequency domain), weights 1.0 and 0.6;
- a siren wail on `siren_share` of clips: a 700-1500 Hz sine sweep at 0.15-0.35 Hz with its 2nd harmonic, weight 0.35;
- monitor beeps on `beep_share` of clips: an 80 ms tone at 880-1000 Hz every 0.55-1.0 s (a heart-rate beep),
  5 ms ramps, weight 0.3.
The sum is scaled so speech RMS over speech-active samples (|x| > 2% of the peak) / noise RMS equals the SNR.
Training-data preparation only; nothing here runs in the product."""
from __future__ import annotations

import numpy as np

SR = 16000


def _unit(x: np.ndarray) -> np.ndarray:
    r = float(np.sqrt(np.mean(x ** 2)))
    return x / r if r > 0 else x


def _pink(n: int, rng: np.random.Generator) -> np.ndarray:
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.arange(len(spec), dtype=np.float64)
    f[0] = 1.0
    return np.fft.irfft(spec / np.sqrt(f), n)


def _brown(n: int, rng: np.random.Generator) -> np.ndarray:
    from scipy.signal import lfilter
    return lfilter([1.0], [1.0, -0.995], rng.standard_normal(n))


def cabin_noise(n: int, rng: np.random.Generator, cfg: dict, sr: int = SR) -> tuple[np.ndarray, dict]:
    """`n` samples of cabin noise at unit RMS, and which parts it has."""
    t = np.arange(n) / sr
    f0 = rng.uniform(*cfg["engine_hz"])
    wobble = 1 + 0.03 * np.sin(2 * np.pi * rng.uniform(0.05, 0.2) * t + rng.uniform(0, 2 * np.pi))
    phase = 2 * np.pi * np.cumsum(f0 * wobble) / sr
    engine = sum(a * np.sin(k * phase + rng.uniform(0, 2 * np.pi)) for k, a in ((1, 1), (2, .6), (3, .35), (4, .2)))
    noise = _unit(engine) + _unit(_brown(n, rng)) + 0.6 * _unit(_pink(n, rng))
    parts = {"engine_hz": round(f0, 1), "siren": False, "beeps": False}
    if rng.random() < cfg["siren_share"]:
        lo, hi, rate = rng.uniform(700, 900), rng.uniform(1200, 1500), rng.uniform(0.15, 0.35)
        freq = lo + (hi - lo) * (0.5 + 0.5 * np.sin(2 * np.pi * rate * t + rng.uniform(0, 2 * np.pi)))
        ph = 2 * np.pi * np.cumsum(freq) / sr
        noise = noise + 0.35 * _unit(np.sin(ph) + 0.3 * np.sin(2 * ph))
        parts["siren"] = True
    if rng.random() < cfg["beep_share"]:
        period, tone, dur = rng.uniform(0.55, 1.0), rng.uniform(880, 1000), int(0.08 * sr)
        ramp = np.minimum(1, np.minimum(np.arange(dur), np.arange(dur)[::-1]) / (0.005 * sr))
        beep = np.sin(2 * np.pi * tone * np.arange(dur) / sr) * ramp
        track = np.zeros(n)
        for s in np.arange(rng.uniform(0, period), n / sr, period):
            i = int(s * sr)
            track[i:i + dur] += beep[:max(0, min(dur, n - i))]
        noise = noise + 0.3 * _unit(track)
        parts["beeps"] = True
    return _unit(noise).astype(np.float32), parts


def mix(speech: np.ndarray, snr_db: float | None, rng: np.random.Generator, cfg: dict, sr: int = SR) -> tuple[np.ndarray, dict]:
    """Speech padded with `lead_seconds` either side and mixed with cabin noise at `snr_db` (None = clean)."""
    pad = [int(rng.uniform(*cfg["lead_seconds"]) * sr) for _ in range(2)]
    x = np.concatenate([np.zeros(pad[0], np.float32), speech.astype(np.float32), np.zeros(pad[1], np.float32)])
    if snr_db is None:
        return x, {}
    active = speech[np.abs(speech) > 0.02 * np.max(np.abs(speech))] if len(speech) else speech
    s_rms = float(np.sqrt(np.mean(active ** 2))) if len(active) else 0.0
    noise, parts = cabin_noise(len(x), rng, cfg, sr)
    y = x + noise * (s_rms / (10 ** (snr_db / 20)))
    peak = float(np.max(np.abs(y)))
    return (y / peak * 0.95 if peak > 0.99 else y).astype(np.float32), parts
