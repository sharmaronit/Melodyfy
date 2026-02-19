"""
celery_worker.py — Async task queue for BeatFlow AI
Broker:  Redis @ redis://localhost:6379/0
Backend: Redis @ redis://localhost:6379/1

Run worker:
    python -m celery -A celery_worker worker --loglevel=info --pool=solo

Note: --pool=solo is required on Windows.
"""
from __future__ import annotations
import os
import time
from celery import Celery

# ── Celery app ────────────────────────────────────────────────────
BROKER  = os.getenv("CELERY_BROKER_URL",  "redis://localhost:6379/0")
BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "beatflow",
    broker=BROKER,
    backend=BACKEND,
)

celery_app.conf.update(
    task_serializer       = "json",
    accept_content        = ["json"],
    result_serializer     = "json",
    timezone              = "UTC",
    enable_utc            = True,
    task_track_started    = True,
    task_acks_late        = True,
    worker_prefetch_multiplier = 1,      # one task at a time (GPU)
    task_time_limit       = 300,         # 5 min hard limit per task
    task_soft_time_limit  = 240,         # 4 min soft limit
)


# ── Helpers ───────────────────────────────────────────────────────
def _gpu_context():
    """Return (device, dtype) matching what api_server.py uses."""
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype  = torch.float16 if device == "cuda" else torch.float32
    return device, dtype


# ── Task 1: Generate beat ─────────────────────────────────────────
@celery_app.task(bind=True, name="beatflow.generate_beat")
def generate_beat_task(self, prompt: str, label: str, commit_id: str | None = None):
    """
    Async MusicGen generation.
    Updates DB commit record when done.
    Returns: {"audio_url", "duration", "elapsed", "device"}
    """
    self.update_state(state="PROGRESS", meta={"step": "loading model"})
    from transformers import AutoProcessor, MusicgenForConditionalGeneration
    import torch, soundfile as sf
    from pathlib import Path
    from datetime import datetime

    device, dtype = _gpu_context()

    t0        = time.time()
    processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
    model     = MusicgenForConditionalGeneration.from_pretrained(
        "facebook/musicgen-small", torch_dtype=dtype
    ).to(device)
    model.eval()

    self.update_state(state="PROGRESS", meta={"step": "generating"})
    inputs = processor(text=[prompt], padding=True, return_tensors="pt").to(device)

    with torch.inference_mode():
        with torch.autocast(device_type=device, dtype=dtype, enabled=(device == "cuda")):
            output = model.generate(**inputs, max_new_tokens=512)

    audio_np    = output[0, 0].cpu().float().numpy()
    sample_rate = model.config.audio_encoder.sampling_rate
    duration    = len(audio_np) / sample_rate

    ts       = datetime.now().strftime("%H%M%S")
    filename = f"beat_{ts}.wav"
    out_path = Path("beat_outputs") / filename
    out_path.parent.mkdir(exist_ok=True)
    sf.write(str(out_path), audio_np, sample_rate)
    elapsed = round(time.time() - t0, 1)

    result = {
        "audio_url": f"/audio/{filename}",
        "duration":  round(duration, 2),
        "elapsed":   elapsed,
        "device":    f"{device}",
    }

    # Update DB if commit_id provided
    if commit_id:
        try:
            from database import SessionLocal
            from models import Commit
            db = SessionLocal()
            commit = db.query(Commit).filter(Commit.id == commit_id).first()
            if commit:
                commit.audio_url    = result["audio_url"]
                commit.duration     = result["duration"]
                commit.elapsed_sec  = elapsed
                db.commit()
            db.close()
        except Exception as e:
            print(f"[WARN] DB update failed: {e}")

    return result


# ── Task 2: Stem separation ───────────────────────────────────────
@celery_app.task(bind=True, name="beatflow.separate_stems")
def separate_stems_task(self, audio_path: str, commit_id: str | None = None):
    """
    Async DEMUCS stem separation.
    Returns: {"stems": {"drums": url, "bass": url, ...}}
    """
    self.update_state(state="PROGRESS", meta={"step": "separating stems"})
    from audio_processing import separate_stems
    from pathlib import Path

    stems = separate_stems(audio_path)
    stems_dir = Path("stems_outputs")

    # Build URLs relative to /stems
    stem_urls = {}
    for name, path in stems.items():
        rel = Path(path).relative_to(stems_dir)
        stem_urls[name] = f"/stems/{rel.as_posix()}"

    result = {"stems": stem_urls}

    # Update DB
    if commit_id:
        try:
            from database import SessionLocal
            from models import Stem
            db = SessionLocal()
            for stem_type, url in stem_urls.items():
                s = Stem(commit_id=commit_id, type=stem_type, audio_url=url)
                db.add(s)
            db.commit()
            db.close()
        except Exception as e:
            print(f"[WARN] DB stem update failed: {e}")

    return result


# ── Task 3: Analyze audio ─────────────────────────────────────────
@celery_app.task(bind=True, name="beatflow.analyze_audio")
def analyze_audio_task(self, audio_path: str, commit_id: str | None = None):
    """Async Librosa audio analysis. Updates commit BPM/key/energy."""
    self.update_state(state="PROGRESS", meta={"step": "analyzing"})
    from audio_processing import analyze_audio

    result = analyze_audio(audio_path)

    if commit_id:
        try:
            from database import SessionLocal
            from models import Commit
            db = SessionLocal()
            c = db.query(Commit).filter(Commit.id == commit_id).first()
            if c:
                c.bpm    = result.get("bpm")
                c.key    = result.get("key")
                c.energy = result.get("energy")
                db.commit()
            db.close()
        except Exception as e:
            print(f"[WARN] DB analysis update failed: {e}")

    return result
