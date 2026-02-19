"""
audio_processing.py
====================
All AI audio processing modules:
  - Phase 2A: DEMUCS  — stem separation (drums, bass, vocals, other)
  - Phase 2B: LIBROSA — BPM, key, energy, waveform analysis
  - Phase 2C: Melody Conditioning — hum/audio → music (MusicGen Melody)
  - Phase 3A: Audio Continuation  — extend a beat using MusicGen
  - Phase 3B: AI Mastering        — matchering (loudness normalization)
"""

from __future__ import annotations
import io, re, time
from pathlib import Path
from datetime import datetime
import numpy as np
import torch
import soundfile as sf

OUTPUT_DIR  = Path("beat_outputs")
STEMS_DIR   = Path("stems_outputs")
MASTER_DIR  = Path("mastered_outputs")
for d in [OUTPUT_DIR, STEMS_DIR, MASTER_DIR]:
    d.mkdir(exist_ok=True)

# Pre-import librosa at module level so it's cached for subsequent calls
import librosa


# ═══════════════════════════════════════════════════════════════════
# PHASE 2A — DEMUCS  (Stem Separation)
# ═══════════════════════════════════════════════════════════════════

def separate_stems(audio_path: str) -> dict[str, str]:
    """
    Split an audio file into drums, bass, vocals, other stems via demucs CLI.
    Returns dict of stem_name → saved file path.
    """
    import sys, subprocess

    audio_path = Path(audio_path).resolve()   # absolute path — critical!
    ts        = datetime.now().strftime("%H%M%S")
    stem_base = STEMS_DIR.resolve() / f"{audio_path.stem}_{ts}"
    stem_base.mkdir(parents=True, exist_ok=True)

    # Use run_demucs.py wrapper which patches torchaudio.load/save with
    # soundfile so demucs works without torchcodec (FFmpeg 5+ not available).
    wrapper = Path(__file__).resolve().parent / "run_demucs.py"
    result = subprocess.run(
        [sys.executable, str(wrapper),
         str(audio_path),
         str(stem_base)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "")[-2000:]
        raise RuntimeError(
            f"demucs failed (exit {result.returncode}):\n{detail}"
        )

    # demucs output layout: stem_base/htdemucs/{track_name}/{drum,bass,vocals,other}.wav
    track_dir = stem_base / "htdemucs" / audio_path.stem
    stem_names = ["drums", "bass", "vocals", "other"]
    saved = {}
    for name in stem_names:
        p = track_dir / f"{name}.wav"
        if p.exists():
            saved[name] = str(p)

    if not saved:
        raise RuntimeError(f"demucs produced no stems in {track_dir}")
    return saved


# ═══════════════════════════════════════════════════════════════════
# PHASE 2B — LIBROSA  (Audio Analysis)
# ═══════════════════════════════════════════════════════════════════

CHROMA_KEYS  = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
MINOR_OFFSET = 9  # relative minor

def analyze_audio(audio_path: str) -> dict:
    """
    Analyze a WAV and return BPM, key, energy, duration.
    """
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = len(y) / sr

    # BPM
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(round(float(tempo), 1))

    # Key detection via chroma
    chroma    = librosa.feature.chroma_cqt(y=y, sr=sr)
    key_idx   = int(chroma.mean(axis=1).argmax())
    key_major = CHROMA_KEYS[key_idx]
    key_minor = CHROMA_KEYS[(key_idx + MINOR_OFFSET) % 12]

    # Simple major/minor guess via spectral comparison
    chroma_mean   = chroma.mean(axis=1)
    major_profile = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
    minor_profile = np.array([6.33,2.68,3.52,5.38,2.60,3.97,2.49,5.21,3.37,2.45,4.02,1.94])
    corr_major = float(np.corrcoef(chroma_mean, np.roll(major_profile, key_idx))[0,1])
    corr_minor = float(np.corrcoef(chroma_mean, np.roll(minor_profile, key_idx))[0,1])
    mode = "Major" if corr_major >= corr_minor else "Minor"
    key  = f"{key_major} {mode}"

    # RMS energy (0-1 normalised)
    rms    = float(librosa.feature.rms(y=y).mean())
    energy = round(min(rms * 20, 1.0), 3)  # rough normalisation

    # Spectral centroid (brightness)
    centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())

    # Loudness estimate (dBFS)
    loudness_db = round(float(20 * np.log10(rms + 1e-9)), 1)

    return {
        "bpm":          bpm,
        "key":          key,
        "energy":       energy,
        "duration":     round(duration, 2),
        "loudness_db":  loudness_db,
        "brightness_hz": round(centroid, 1),
    }


# ═══════════════════════════════════════════════════════════════════
# PHASE 2C — MELODY CONDITIONING  (Hum → Beat)
# ═══════════════════════════════════════════════════════════════════

_melody_processor = None
_melody_model     = None

def _load_melody_model(device: str, dtype: torch.dtype):
    global _melody_processor, _melody_model
    if _melody_model is not None:
        return _melody_processor, _melody_model

    from transformers import AutoProcessor, MusicgenMelodyForConditionalGeneration
    print("[..] Loading MusicGen-Melody model...")
    _melody_processor = AutoProcessor.from_pretrained("facebook/musicgen-melody")
    _melody_model     = MusicgenMelodyForConditionalGeneration.from_pretrained(
        "facebook/musicgen-melody", torch_dtype=dtype
    ).to(device)
    _melody_model.eval()
    print(f"[OK] MusicGen-Melody ready on {device}")
    return _melody_processor, _melody_model


def hum_to_beat(
    audio_path: str,
    prompt: str,
    device: str,
    dtype: torch.dtype,
    max_new_tokens: int = 1500,   # ~30 seconds
) -> tuple[Path, float]:
    """
    Takes a hummed/recorded audio file + text prompt, generates a matching beat.
    """
    import librosa

    processor, model = _load_melody_model(device, dtype)

    # Load and resample to 32kHz as float32 numpy — processor MUST receive numpy, not tensor
    y, sr = librosa.load(audio_path, sr=32000, mono=True)
    y = y.astype(np.float32)   # ensure float32

    # Processor expects: audio=[1D numpy array], sampling_rate=int
    inputs = processor(
        audio=y,               # 1D float32 numpy array — NOT a tensor
        sampling_rate=32000,
        text=[prompt],
        padding=True,
        return_tensors="pt",
    )
    # Move all inputs to device AFTER processor converts them
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.inference_mode():
        with torch.autocast(device_type=device, dtype=dtype, enabled=(device == "cuda")):
            output = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                guidance_scale=5.0,    # stronger prompt adherence (default 3.0)
                do_sample=True,
                temperature=1.0,
            )

    audio_np    = output[0, 0].cpu().float().numpy()
    sample_rate = model.config.audio_encoder.sampling_rate
    duration    = len(audio_np) / sample_rate

    ts       = datetime.now().strftime("%H%M%S")
    out_path = OUTPUT_DIR / f"hum_to_beat_{ts}.wav"
    sf.write(str(out_path), audio_np, sample_rate)
    return out_path, duration


# ═══════════════════════════════════════════════════════════════════
# PHASE 3A — AUDIO CONTINUATION  (Extend a Beat)
# ═══════════════════════════════════════════════════════════════════

def continue_beat(
    audio_path: str,
    prompt: str,
    processor,          # MusicGen processor (passed in from api_server)
    model,              # MusicGen model (passed in from api_server)
    device: str,
    dtype: torch.dtype,
    max_new_tokens: int = 512,
) -> tuple[Path, float]:
    """
    Continues an existing beat using MusicGen audio continuation.
    """
    import librosa

    # Load audio, resample to MusicGen's expected 32kHz
    y, sr = librosa.load(audio_path, sr=32000, mono=True)
    audio_array = y[np.newaxis, np.newaxis, :]  # [1,1,samples]

    inputs = processor(
        audio=torch.from_numpy(audio_array).to(device),
        sampling_rate=32000,
        text=[prompt],
        padding=True,
        return_tensors="pt",
    ).to(device)

    with torch.inference_mode():
        with torch.autocast(device_type=device, dtype=dtype, enabled=(device == "cuda")):
            output = model.generate(**inputs, max_new_tokens=max_new_tokens)

    audio_np    = output[0, 0].cpu().float().numpy()
    sample_rate = model.config.audio_encoder.sampling_rate
    duration    = len(audio_np) / sample_rate

    ts       = datetime.now().strftime("%H%M%S")
    out_path = OUTPUT_DIR / f"continued_{Path(audio_path).stem}_{ts}.wav"
    sf.write(str(out_path), audio_np, sample_rate)
    return out_path, duration


# ═══════════════════════════════════════════════════════════════════
# PHASE 3B — AI MASTERING  (matchering)
# ═══════════════════════════════════════════════════════════════════

# Built-in reference track path (a well-mastered EDM reference)
BUILTIN_REFERENCE = Path(__file__).parent / "reference_master.wav"

def master_audio(target_path: str, reference_path: str | None = None) -> tuple[Path, dict]:
    """
    AI master a WAV file using pyloudnorm loudness normalization + peak limiting.
    Normalises to -14 LUFS (streaming standard), then hard-limits peaks to -1 dBFS.
    reference_path is accepted for API compatibility but not required.
    Returns (output_path, info_dict)
    """
    import pyloudnorm as pyln

    target = Path(target_path)
    ts     = datetime.now().strftime("%H%M%S")
    output = MASTER_DIR / f"mastered_{target.stem}_{ts}.wav"

    # Load audio
    audio, sr = librosa.load(str(target), sr=None, mono=False)
    # librosa returns shape (samples,) for mono or (channels, samples) for stereo
    if audio.ndim == 1:
        audio = audio[np.newaxis, :]          # → (1, samples)
    audio = audio.T                            # pyloudnorm expects (samples, channels)

    # ── 1. Measure current integrated loudness ────────────────────
    meter = pyln.Meter(sr)                     # EBU R128 meter
    loudness = meter.integrated_loudness(audio)

    # ── 2. Normalise to -14 LUFS (Spotify/YouTube standard) ───────
    target_lufs = -14.0
    audio_norm  = pyln.normalize.loudness(audio, loudness, target_lufs)

    # ── 3. Hard peak limiter — keep ceiling at -1 dBFS ────────────
    peak = np.abs(audio_norm).max()
    ceiling_linear = 10 ** (-1.0 / 20)        # -1 dBFS
    if peak > ceiling_linear:
        audio_norm = audio_norm * (ceiling_linear / peak)

    # ── 4. Write output ───────────────────────────────────────────
    sf.write(str(output), audio_norm.astype(np.float32), sr, subtype="PCM_16")

    # Measure final loudness for the response
    final_loudness = meter.integrated_loudness(audio_norm)
    final_peak_db  = round(float(20 * np.log10(np.abs(audio_norm).max() + 1e-9)), 1)

    info = {
        "original_lufs": round(float(loudness), 1),
        "mastered_lufs":  round(float(final_loudness), 1),
        "peak_db":        final_peak_db,
        "sample_rate":    sr,
        "duration":       round(audio_norm.shape[0] / sr, 2),
    }
    return output, info


def _make_builtin_reference() -> Path:   # kept for backward compat, no longer used
    sr    = 44100
    dur   = 10
    t     = np.linspace(0, dur, sr * dur)
    # Simple mix of sine waves at common EDM frequencies
    audio = (
        0.4  * np.sin(2 * np.pi * 60   * t) +   # sub bass
        0.3  * np.sin(2 * np.pi * 120  * t) +   # bass
        0.15 * np.sin(2 * np.pi * 440  * t) +   # mid
        0.05 * np.random.randn(len(t))           # high end noise
    )
    audio = audio / np.abs(audio).max() * 0.85
    sf.write(str(BUILTIN_REFERENCE), audio.astype(np.float32), sr)
    return BUILTIN_REFERENCE
