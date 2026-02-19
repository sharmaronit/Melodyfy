"""
BeatFlow AI — FastAPI server
Run: python api_server.py

Endpoints
─────────────────────────────────────────────
GET   /health
POST  /generate          → beat from text prompt (sync)
POST  /generate/async    → dispatch Celery task, returns task_id
GET   /tasks/{task_id}   → poll Celery task status
POST  /analyze           → BPM / key / energy / waveform peaks
POST  /separate          → DEMUCS stem split (+ optional commit_id to link stems in DB)
POST  /continue          → extend a beat
POST  /hum               → melody → beat
POST  /master            → AI mastering

POST  /auth/register     → create account
POST  /auth/login        → JWT token
GET   /auth/me           → current user
PATCH /auth/me           → update bio / avatar_url

GET   /users             → list / search users
GET   /users/{username}  → user profile + public repos
POST  /users/{username}/follow   → follow (auth)
DELETE /users/{username}/follow  → unfollow (auth)

GET   /projects                  → list public repos
GET   /projects/search           → search by q, mood, bpm_min, bpm_max, sort
POST  /projects                  → create repo (auth)
GET   /projects/{id}             → repo detail + commits
POST  /projects/{id}/commit      → save beat as commit (auth)
POST  /projects/{id}/fork        → fork repo (auth)
GET   /projects/{id}/tree        → commit tree for visualization
POST  /projects/{id}/star        → star repo (auth)
DELETE /projects/{id}/star       → unstar repo (auth)
POST  /projects/{id}/play        → increment play count

GET   /projects/{repo_id}/commits/{commit_id}/comments   → list comments
POST  /projects/{repo_id}/commits/{commit_id}/comments   → add comment (auth)
DELETE /comments/{comment_id}    → delete own comment (auth)
"""

from __future__ import annotations
import time, re, sys, shutil, asyncio, json
from datetime import datetime
from pathlib import Path

# ── FastAPI / Uvicorn ─────────────────────────────────────────────
try:
    from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import JSONResponse, StreamingResponse
    import uvicorn
    from pydantic import BaseModel
    from typing import Optional, List
    import asyncio
except ImportError:
    print("[X] FastAPI not installed. Run:")
    print("    pip install fastapi uvicorn[standard] pydantic")
    sys.exit(1)

# ── Torch / Transformers ──────────────────────────────────────────
import torch
from transformers import AutoProcessor, MusicgenForConditionalGeneration

# ── Database ──────────────────────────────────────────────────────
from database import init_db, get_db
from models import User, Repository, Commit, Stem, Star, Follow, Comment
from auth import (
    hash_password, verify_password,
    create_access_token, get_current_user, get_current_user_optional
)
from sqlalchemy.orm import Session

# ── Pre-load audio_processing (imports librosa at module level) ───
import audio_processing as _ap

# ── Config ───────────────────────────────────────────────────────
MODEL_NAME      = "facebook/musicgen-small"
DURATION_TOKENS = 512          # ~10 seconds
OUTPUT_DIR      = Path("beat_outputs")
STEMS_DIR       = Path("stems_outputs")
MASTER_DIR      = Path("mastered_outputs")
UPLOAD_TMP      = Path("upload_tmp")
for _d in [OUTPUT_DIR, STEMS_DIR, MASTER_DIR, UPLOAD_TMP]:
    _d.mkdir(exist_ok=True)

# In-memory SSE progress store  { task_id: {"status":…,"pct":…} }
_gen_progress: dict = {}

# ── Mood → prompt map (mirrors beat_generator.py) ─────────────────
MOOD_PROMPTS: dict[str, str] = {
    "EDM / Club Banger":  "energetic EDM beat with heavy bass drops, synthesizers, and pulsing drums at 128 bpm, club music",
    "Trap / Hip-Hop":     "dark trap beat with 808 bass, hi-hats, and atmospheric pads, hip hop production, 140 bpm",
    "Lo-fi Chill":        "lo-fi hip hop beat with vinyl crackle, mellow chords, relaxed drums, chill study music",
    "Synthwave":          "synthwave retro 80s electronic music with lush synthesizers, driving beat, nostalgic neon vibes",
    "Deep House":         "deep house music with groovy bassline, smooth synthesizers, four-on-the-floor drums, midnight dance floor",
    "Drum and Bass":      "fast drum and bass with rapid breakbeats, heavy sub-bass, aggressive energy, 174 bpm",
    "Ambient":            "ambient atmospheric music with evolving synthesizer pads, ethereal textures, slow floating soundscape",
    "Phonk":              "phonk music with memphis rap samples, dark twisted bass, aggressive drums, drifting energy",
    "Calm Piano":         "calm solo piano music, emotional and introspective, soft dynamics, gentle melody",
    "Acoustic Guitar":    "fingerpicked acoustic guitar, warm and intimate, folk style, gentle arpeggios",
    "Jazz":               "smooth jazz with saxophone lead, soft piano chords, upright bass, brushed drums, late night bar vibe",
    "Blues":              "soulful blues guitar with electric guitar riffs, steady rhythm, emotional and raw, Delta blues feel",
    "Orchestral":         "cinematic orchestral music with strings, brass, and dramatic crescendos, epic film score feeling",
    "R&B / Soul":         "modern R&B soul music with warm chord progressions, smooth bass, subtle drums, emotional vocals bed",
    "Epic Cinematic":     "epic cinematic orchestral battle music with massive drums, brass fanfare, intense strings, heroic",
    "Metal":              "heavy metal music with distorted electric guitars, fast double kick drums, aggressive energy",
    "Indie Rock":         "indie rock with jangly guitars, energetic drums, catchy melody, stadium anthemic feel",
    "Afrobeats":          "afrobeats music with percussion, talking drums, bright guitar riffs, danceable groove, West African rhythm",
    "Meditation":         "peaceful meditation music with singing bowls, soft pads, nature ambience, slow breathing rhythm",
    "Nature Sounds":      "gentle acoustic music blended with nature sounds, birds, stream, forest atmosphere, peaceful",
    "Sleep Drone":        "slow droning ambient music, very soft, hypnotic, warm bass tones, for sleep and relaxation",
    "Bossa Nova":         "bossa nova Brazilian jazz with nylon string guitar, light percussion, romantic and breezy",
    "8-Bit Game":         "retro video game chiptune music with 8-bit synth melodies, catchy loop, upbeat pixel adventure mood",
    "Middle Eastern":     "Middle Eastern music with oud, darbuka drums, haunting scales, traditional yet modern fusion",
}

# ── Load model once at startup ────────────────────────────────────
print("[..] Loading MusicGen model…")
_device     = "cuda" if torch.cuda.is_available() else "cpu"
_dtype      = torch.float16 if _device == "cuda" else torch.float32
_gpu_name   = torch.cuda.get_device_name(0) if _device == "cuda" else "CPU"
_processor  = AutoProcessor.from_pretrained(MODEL_NAME)
_model      = MusicgenForConditionalGeneration.from_pretrained(
    MODEL_NAME, torch_dtype=_dtype
).to(_device)
_model.eval()
print(f"[OK] Model ready on {_device} ({_gpu_name}) dtype={_dtype}")

# ── FastAPI app ───────────────────────────────────────────────────
app = FastAPI(title="BeatFlow AI", version="2.0.0")

@app.on_event("startup")
def on_startup():
    init_db()
    print("[OK] Database initialised")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated audio files
app.mount("/audio",   StaticFiles(directory=str(OUTPUT_DIR)), name="audio")
app.mount("/stems",   StaticFiles(directory=str(STEMS_DIR)),  name="stems")
app.mount("/mastered",StaticFiles(directory=str(MASTER_DIR)), name="mastered")

# Serve the frontend HTML files at /ui/ (same origin → no CORS issues)
_FRONTEND_DIR = Path(__file__).parent
app.mount("/ui", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")


@app.get("/", include_in_schema=False)
async def root_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui/index.html")


class GenerateRequest(BaseModel):
    prompt: str
    name:   str = "Custom"


class GenerateResponse(BaseModel):
    url:      str
    filename: str
    duration: float
    elapsed:  float
    device:   str


class FilenameRequest(BaseModel):
    filename: str


class ContinueRequest(BaseModel):
    filename: str
    prompt:   str


class MasterRequest(BaseModel):
    filename:  str
    reference: Optional[str] = None  # filename of reference track in beat_outputs


def _safe_name(label: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", label.replace(" ", "_"))[:30]


def _generate(prompt: str, label: str) -> tuple[Path, float]:
    """Generate audio and save as WAV. Returns (path, duration_seconds)."""
    inputs = _processor(
        text=[prompt],
        padding=True,
        return_tensors="pt",
    ).to(_device)

    with torch.inference_mode():
        with torch.autocast(device_type=_device, dtype=_dtype, enabled=(_device == "cuda")):
            output = _model.generate(**inputs, max_new_tokens=DURATION_TOKENS)

    # Shape: [batch, channels, samples] → numpy [samples]
    audio_np = output[0, 0].cpu().float().numpy()
    sample_rate = _model.config.audio_encoder.sampling_rate
    duration    = len(audio_np) / sample_rate

    ts       = datetime.now().strftime("%H%M%S")
    filename = f"{_safe_name(label)}_{ts}.wav"
    out_path = OUTPUT_DIR / filename

    try:
        import torchaudio
        import io
        wav_tensor = torch.from_numpy(audio_np).unsqueeze(0)
        buf = io.BytesIO()
        torchaudio.save(buf, wav_tensor, sample_rate, format="wav")
        out_path.write_bytes(buf.getvalue())
    except Exception:
        import soundfile as sf
        sf.write(str(out_path), audio_np, sample_rate)

    return out_path, duration


# ── Endpoints ─────────────────────────────────────────────────────
@app.get("/health")
def health():
    redis_ok = False
    try:
        import redis as _redis
        _r = _redis.Redis(socket_connect_timeout=1, socket_timeout=1)
        _r.ping()
        redis_ok = True
    except Exception:
        pass
    return {
        "status":    "ok",
        "device":    _device,
        "gpu_name":  _gpu_name,
        "dtype":     str(_dtype).replace("torch.", ""),
        "redis":     "connected" if redis_ok else "unavailable",
    }


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    # Resolve prompt: if name matches a known mood AND prompt is empty/same, use canonical
    prompt = MOOD_PROMPTS.get(req.name, req.prompt) if not req.prompt else req.prompt

    t0 = time.time()
    try:
        path, duration = _generate(prompt, req.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    elapsed = round(time.time() - t0, 1)
    return GenerateResponse(
        url=f"/audio/{path.name}",
        filename=path.name,
        duration=duration,
        elapsed=elapsed,
        device=f"{_device} ({_gpu_name})",
    )


# ── Phase 2B: Audio Analysis ──────────────────────────────────────
@app.post("/analyze")
def analyze(req: FilenameRequest):
    """Analyze a generated beat: BPM, key, energy, loudness, waveform peaks."""
    audio_path = OUTPUT_DIR / req.filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.filename}")
    try:
        from audio_processing import analyze_audio
        result = analyze_audio(str(audio_path))
        # Append waveform peaks (100 samples, normalized -1..1) for frontend visualizer
        try:
            import librosa, numpy as np
            y, sr = librosa.load(str(audio_path), sr=None, mono=True)
            n_peaks = 100
            chunk   = max(1, len(y) // n_peaks)
            peaks   = [float(round(float(np.max(np.abs(y[i*chunk:(i+1)*chunk]))), 4))
                       for i in range(n_peaks)]
            result["waveform_peaks"] = peaks
        except Exception:
            result["waveform_peaks"] = []
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Phase 2A: Stem Separation (DEMUCS) ────────────────────────────
class SeparateRequest(BaseModel):
    filename:  str
    commit_id: Optional[str] = None   # if provided, stems are saved to DB


@app.post("/separate")
def separate(req: SeparateRequest, db: Session = Depends(get_db)):
    """Separate beat into drums, bass, vocals, other stems.
    Pass commit_id to auto-save stems to the Stem table."""
    audio_path = OUTPUT_DIR / req.filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.filename}")
    try:
        from audio_processing import separate_stems
        stems = separate_stems(str(audio_path))
        # Return web-accessible URLs for each stem
        stem_urls = {}
        stems_dir_abs = STEMS_DIR.resolve()
        for name, path in stems.items():
            rel = Path(path).resolve().relative_to(stems_dir_abs)
            stem_urls[name] = f"/stems/{rel.as_posix()}"
        # Persist to DB if commit_id is given
        if req.commit_id:
            commit_obj = db.query(Commit).filter(Commit.id == req.commit_id).first()
            if commit_obj:
                for stem_type, url in stem_urls.items():
                    existing = db.query(Stem).filter(
                        Stem.commit_id == req.commit_id, Stem.type == stem_type
                    ).first()
                    if not existing:
                        s = Stem(commit_id=req.commit_id, type=stem_type, audio_url=url)
                        db.add(s)
                db.commit()
        return {"stems": stem_urls, "saved_to_db": req.commit_id is not None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Phase 3A: Audio Continuation ─────────────────────────────────
@app.post("/continue")
def continue_beat_endpoint(req: ContinueRequest):
    """Extend an existing beat with a new prompt."""
    audio_path = OUTPUT_DIR / req.filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.filename}")
    try:
        from audio_processing import continue_beat
        t0 = time.time()
        out_path, duration = continue_beat(
            audio_path=str(audio_path),
            prompt=req.prompt,
            processor=_processor,
            model=_model,
            device=_device,
            dtype=_dtype,
        )
        elapsed = round(time.time() - t0, 1)
        return {
            "url":      f"/audio/{out_path.name}",
            "filename": out_path.name,
            "duration": round(duration, 2),
            "elapsed":  elapsed,
            "device":   f"{_device} ({_gpu_name})",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Phase 2C: Hum / Melody → Beat (MusicGen Melody) ───────────────
@app.post("/hum")
async def hum_to_beat_endpoint(
    file: UploadFile = File(...),
    prompt: str = Form(default="upbeat electronic beat"),
):
    """Upload a hummed/recorded melody and get a generated beat."""
    try:
        ts       = datetime.now().strftime("%H%M%S")
        tmp_path = UPLOAD_TMP / f"hum_{ts}_{file.filename}"
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        from audio_processing import hum_to_beat
        t0 = time.time()
        out_path, duration = hum_to_beat(
            audio_path=str(tmp_path),
            prompt=prompt,
            device=_device,
            dtype=_dtype,
        )
        elapsed = round(time.time() - t0, 1)
        tmp_path.unlink(missing_ok=True)
        return {
            "url":      f"/audio/{out_path.name}",
            "filename": out_path.name,
            "duration": round(duration, 2),
            "elapsed":  elapsed,
            "device":   f"{_device} ({_gpu_name})",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Audio File Upload ─────────────────────────────────────────────
@app.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    """Upload any audio file to be used with analyze / separate / master tools."""
    ext = Path(file.filename).suffix.lower() if file.filename else ".wav"
    if ext not in {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a"}:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {ext}")
    import uuid
    fname = f"upload_{uuid.uuid4().hex[:10]}{ext}"
    dest  = OUTPUT_DIR / fname
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": fname, "audio_url": f"/audio/{fname}"}


# ── Phase 3B: AI Mastering (matchering) ──────────────────────────
@app.post("/master")
def master_endpoint(req: MasterRequest):
    """AI master a beat using matchering."""
    target_path = OUTPUT_DIR / req.filename
    if not target_path.exists():
        raise HTTPException(status_code=404, detail=f"Target not found: {req.filename}")

    reference_path = None
    if req.reference:
        reference_path = str(OUTPUT_DIR / req.reference)
        if not Path(reference_path).exists():
            raise HTTPException(status_code=404, detail=f"Reference not found: {req.reference}")

    try:
        from audio_processing import master_audio
        t0 = time.time()
        out_path, info = master_audio(str(target_path), reference_path)
        elapsed = round(time.time() - t0, 1)
        return {
            "url":      f"/mastered/{out_path.name}",
            "filename": out_path.name,
            "elapsed":  elapsed,
            "analysis": info,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Run ───────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────
# AUTH ENDPOINTS
# ─────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email:    str
    password: str

class LoginRequest(BaseModel):
    email:    str
    password: str


@app.post("/auth/register", status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(400, "Email already registered")
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(400, "Username taken")
    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
    )
    db.add(user); db.commit(); db.refresh(user)
    # Auto-create private "My Beats" library repo
    lib_repo = Repository(
        owner_id=user.id,
        name="My Beats",
        description="Auto-saved beats library",
        is_public=False,
    )
    db.add(lib_repo); db.commit(); db.refresh(lib_repo)
    user.library_repo_id = lib_repo.id
    db.commit()
    token = create_access_token(user.id, user.username)
    return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email}}


@app.post("/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    token = create_access_token(user.id, user.username)
    return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email}}


@app.get("/auth/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "bio": current_user.bio,
        "created_at": current_user.created_at.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────
# PROJECT / REPOSITORY ENDPOINTS
# ─────────────────────────────────────────────────────────────────

class CreateRepoRequest(BaseModel):
    name:        str
    description: Optional[str] = ""
    is_public:   Optional[bool] = True


@app.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    """List public repositories ordered by newest."""
    repos = db.query(Repository).filter(Repository.is_public == True)\
               .order_by(Repository.updated_at.desc()).limit(50).all()
    return [_repo_summary(r) for r in repos]


@app.get("/projects/search")
def search_projects(
    q:       Optional[str]   = Query(None, description="Text search in name/description"),
    mood:    Optional[str]   = Query(None, description="Filter by mood (exact match)"),
    bpm_min: Optional[float] = Query(None, description="Minimum BPM (across commits)"),
    bpm_max: Optional[float] = Query(None, description="Maximum BPM (across commits)"),
    sort:    Optional[str]   = Query("newest", description="newest | popular | most_played"),
    limit:   int             = Query(30, le=100),
    offset:  int             = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Search public repositories.
    - q       : full-text search in name + description
    - mood    : filter commits by mood tag
    - bpm_min/max: filter by BPM range of the latest commit
    - sort    : newest (default) | popular (stars) | most_played
    """
    from sqlalchemy import or_
    query = db.query(Repository).filter(Repository.is_public == True)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Repository.name.ilike(like),
                Repository.description.ilike(like))
        )

    if mood or bpm_min is not None or bpm_max is not None:
        query = query.join(Commit, Commit.repository_id == Repository.id)
        if mood:
            query = query.filter(Commit.mood.ilike(f"%{mood}%"))
        if bpm_min is not None:
            query = query.filter(Commit.bpm >= bpm_min)
        if bpm_max is not None:
            query = query.filter(Commit.bpm <= bpm_max)
        query = query.distinct()

    if sort == "popular":
        query = query.order_by(Repository.star_count.desc())
    elif sort == "most_played":
        query = query.order_by(Repository.play_count.desc())
    else:
        query = query.order_by(Repository.updated_at.desc())

    repos = query.offset(offset).limit(limit).all()
    return [_repo_summary(r) for r in repos]


@app.post("/projects", status_code=201)
def create_project(
    req: CreateRepoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = Repository(
        owner_id=current_user.id,
        name=req.name,
        description=req.description,
        is_public=req.is_public,
    )
    db.add(repo); db.commit(); db.refresh(repo)
    return _repo_summary(repo)


@app.get("/projects/{repo_id}")
def get_project(repo_id: str, db: Session = Depends(get_db)):
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(404, "Repository not found")
    commits = db.query(Commit).filter(Commit.repository_id == repo_id)\
                .order_by(Commit.created_at.desc()).all()
    return {**_repo_summary(repo), "commits": [_commit_summary(c) for c in commits]}


@app.post("/projects/{repo_id}/fork")
def fork_project(
    repo_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    source = db.query(Repository).filter(Repository.id == repo_id).first()
    if not source:
        raise HTTPException(404, "Repository not found")
    fork = Repository(
        owner_id=current_user.id,
        name=f"{source.name}-fork",
        description=f"Forked from {source.name}",
        is_public=True,
        forked_from=source.id,
    )
    db.add(fork); db.commit(); db.refresh(fork)
    source.star_count = (source.star_count or 0) + 1
    db.commit()
    return _repo_summary(fork)


# ─────────────────────────────────────────────────────────────────
# COMMIT ENDPOINTS  (Git-for-Audio version control)
# ─────────────────────────────────────────────────────────────────

class CommitRequest(BaseModel):
    filename:   str
    message:    Optional[str] = "New beat"
    prompt:     Optional[str] = ""
    mood:       Optional[str] = ""
    parent_hash: Optional[str] = None   # hash of parent commit (branching)


@app.post("/projects/{repo_id}/commit", status_code=201)
def create_commit(
    repo_id: str,
    req: CommitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a generated beat as a commit in a repository."""
    repo = db.query(Repository).filter(
        Repository.id == repo_id, Repository.owner_id == current_user.id
    ).first()
    if not repo:
        raise HTTPException(404, "Repository not found or not yours")

    audio_path = OUTPUT_DIR / req.filename
    if not audio_path.exists():
        raise HTTPException(404, f"Audio file not found: {req.filename}")

    # Find parent commit
    parent_id = None
    if req.parent_hash:
        parent = db.query(Commit).filter(Commit.commit_hash == req.parent_hash,
                                          Commit.repository_id == repo_id).first()
        if parent:
            parent_id = parent.id
    else:
        # Default: latest commit in this repo
        latest = db.query(Commit).filter(Commit.repository_id == repo_id)\
                    .order_by(Commit.created_at.desc()).first()
        if latest:
            parent_id = latest.id

    # Auto-analyze
    bpm = key = energy = None
    try:
        from audio_processing import analyze_audio
        info   = analyze_audio(str(audio_path))
        bpm    = info.get("bpm")
        key    = info.get("key")
        energy = info.get("energy")
    except Exception:
        pass

    commit = Commit(
        repository_id = repo_id,
        parent_id     = parent_id,
        author_id     = current_user.id,
        message       = req.message,
        prompt        = req.prompt,
        audio_url     = f"/audio/{req.filename}",
        mood          = req.mood,
        bpm           = bpm,
        key           = key,
        energy        = energy,
    )
    db.add(commit)
    repo.updated_at = datetime.utcnow()
    db.commit(); db.refresh(commit)
    return _commit_summary(commit)


@app.get("/projects/{repo_id}/tree")
def commit_tree(repo_id: str, db: Session = Depends(get_db)):
    """
    Returns the full commit tree as nodes + edges for React Flow visualization.
    """
    commits = db.query(Commit).filter(Commit.repository_id == repo_id).all()
    nodes = [{"id": c.id, "hash": c.commit_hash, "message": c.message,
              "audio_url": c.audio_url, "bpm": c.bpm, "key": c.key,
              "created_at": c.created_at.isoformat()} for c in commits]
    edges = [{"source": c.parent_id, "target": c.id}
             for c in commits if c.parent_id]
    return {"nodes": nodes, "edges": edges}


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────
def _user_public(u: User) -> dict:
    return {
        "id":           u.id,
        "username":     u.username,
        "bio":          u.bio,
        "avatar_url":   u.avatar_url,
        "created_at":   u.created_at.isoformat(),
        "repo_count":   len([r for r in u.repositories if r.is_public]),
        "follower_count": len(u.followers),
        "following_count": len(u.following),
    }


def _repo_summary(r: Repository) -> dict:
    return {
        "id":          r.id,
        "name":        r.name,
        "description": r.description,
        "owner":       r.owner.username if r.owner else None,
        "is_public":   r.is_public,
        "forked_from": r.forked_from,
        "star_count":  r.star_count,
        "play_count":  r.play_count,
        "created_at":  r.created_at.isoformat(),
        "updated_at":  r.updated_at.isoformat() if r.updated_at else None,
        "commit_count": len(r.commits),
    }


def _commit_summary(c: Commit) -> dict:
    return {
        "id":          c.id,
        "hash":        c.commit_hash,
        "message":     c.message,
        "prompt":      c.prompt,
        "audio_url":   c.audio_url,
        "duration":    c.duration,
        "bpm":         c.bpm,
        "key":         c.key,
        "energy":      c.energy,
        "mood":        c.mood,
        "parent_id":   c.parent_id,
        "author":      c.author.username if c.author else None,
        "created_at":  c.created_at.isoformat(),
        "stems":       [{"type": s.type, "url": s.audio_url} for s in c.stems],
    }

# ─────────────────────────────────────────────────────────────────
# ASYNC GENERATION  (Celery → Redis)
# ─────────────────────────────────────────────────────────────────

class AsyncGenerateRequest(BaseModel):
    prompt: str
    name:   str = "Custom"


@app.post("/generate/async")
def generate_async(req: AsyncGenerateRequest):
    """
    Dispatch beat generation to Celery worker.
    Returns task_id immediately; poll GET /tasks/{task_id} for status.
    Falls back to 503 with guidance if Redis is not reachable.
    """
    prompt = MOOD_PROMPTS.get(req.name, req.prompt) if not req.prompt else req.prompt
    try:
        from celery_worker import generate_beat_task, celery_app as _ca
        # Ping broker to verify connectivity before dispatching
        conn = _ca.connection(transport_options={"max_retries": 1, "interval_start": 0,
                                                  "interval_step": 0, "interval_max": 0})
        conn.ensure_connection(max_retries=1)
        conn.close()
        task = generate_beat_task.delay(prompt, req.name)
        return {"task_id": task.id, "status": "pending",
                "poll_url": f"/tasks/{task.id}"}
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Task queue unavailable (is Redis running?): {type(e).__name__}. "
                   "Start Redis and a Celery worker, or use POST /generate for sync generation."
        )


@app.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    """
    Poll Celery task result.
    States: PENDING, PROGRESS, SUCCESS, FAILURE
    """
    try:
        from celery.result import AsyncResult
        from celery_worker import celery_app as _celery
        result = AsyncResult(task_id, app=_celery)
        state  = result.state
        if state == "PENDING":
            return {"task_id": task_id, "status": "pending"}
        if state == "PROGRESS":
            return {"task_id": task_id, "status": "processing",
                    "meta": result.info or {}}
        if state == "SUCCESS":
            return {"task_id": task_id, "status": "completed", "result": result.result}
        if state == "FAILURE":
            return {"task_id": task_id, "status": "failed",
                    "error": str(result.result)}
        return {"task_id": task_id, "status": state.lower()}
    except Exception as e:
        raise HTTPException(503, f"Task queue unavailable: {e}")


# ─────────────────────────────────────────────────────────────────
# STAR / PLAY
# ─────────────────────────────────────────────────────────────────

@app.post("/projects/{repo_id}/star", status_code=200)
def star_project(
    repo_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Star a repository. Idempotent."""
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(404, "Repository not found")
    existing = db.query(Star).filter(Star.user_id == current_user.id,
                                     Star.repo_id == repo_id).first()
    if existing:
        return {"starred": True, "star_count": repo.star_count}  # already starred
    star = Star(user_id=current_user.id, repo_id=repo_id)
    db.add(star)
    repo.star_count = (repo.star_count or 0) + 1
    db.commit()
    return {"starred": True, "star_count": repo.star_count}


@app.delete("/projects/{repo_id}/star", status_code=200)
def unstar_project(
    repo_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unstar a repository. Idempotent."""
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(404, "Repository not found")
    star = db.query(Star).filter(Star.user_id == current_user.id,
                                  Star.repo_id == repo_id).first()
    if star:
        db.delete(star)
        repo.star_count = max(0, (repo.star_count or 1) - 1)
        db.commit()
    return {"starred": False, "star_count": repo.star_count}


@app.post("/projects/{repo_id}/play", status_code=200)
def play_project(repo_id: str, db: Session = Depends(get_db)):
    """Increment play count for analytics. No auth required."""
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(404, "Repository not found")
    repo.play_count = (repo.play_count or 0) + 1
    db.commit()
    return {"play_count": repo.play_count}


# ─────────────────────────────────────────────────────────────────
# USER PROFILES & FOLLOW SYSTEM
# ─────────────────────────────────────────────────────────────────

class UpdateMeRequest(BaseModel):
    bio:        Optional[str] = None
    avatar_url: Optional[str] = None
    username:   Optional[str] = None


@app.patch("/auth/me")
def update_me(
    req: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current user's profile fields."""
    if req.bio        is not None: current_user.bio        = req.bio
    if req.avatar_url is not None: current_user.avatar_url = req.avatar_url
    if req.username   is not None:
        clash = db.query(User).filter(
            User.username == req.username, User.id != current_user.id
        ).first()
        if clash:
            raise HTTPException(400, "Username already taken")
        current_user.username = req.username
    db.commit(); db.refresh(current_user)
    return {"id": current_user.id, "username": current_user.username,
            "email": current_user.email, "bio": current_user.bio,
            "avatar_url": current_user.avatar_url}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str


@app.patch("/auth/me/password")
def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change password — requires current password verification."""
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if len(req.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")
    current_user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"ok": True}


@app.get("/users")
def list_users(
    q:     Optional[str] = Query(None, description="Search username"),
    limit: int           = Query(30, le=100),
    db: Session = Depends(get_db),
):
    """List / search users (public profiles only)."""
    query = db.query(User).filter(User.is_active == True)
    if q:
        query = query.filter(User.username.ilike(f"%{q}%"))
    users = query.order_by(User.username).limit(limit).all()
    return [_user_public(u) for u in users]


@app.get("/users/{username}")
def get_user_profile(
    username: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Public profile + repos. Includes whether caller follows this user."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(404, "User not found")
    repos = db.query(Repository).filter(
        Repository.owner_id == user.id, Repository.is_public == True
    ).order_by(Repository.updated_at.desc()).all()

    is_following = False
    if current_user:
        is_following = db.query(Follow).filter(
            Follow.follower_id == current_user.id,
            Follow.followee_id == user.id,
        ).first() is not None

    return {
        **_user_public(user),
        "repos": [_repo_summary(r) for r in repos],
        "is_following": is_following,
    }


@app.post("/users/{username}/follow", status_code=200)
def follow_user(
    username: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Follow a user. Idempotent."""
    target = db.query(User).filter(User.username == username).first()
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == current_user.id:
        raise HTTPException(400, "Cannot follow yourself")
    existing = db.query(Follow).filter(
        Follow.follower_id == current_user.id,
        Follow.followee_id == target.id,
    ).first()
    if not existing:
        db.add(Follow(follower_id=current_user.id, followee_id=target.id))
        db.commit()
    return {"following": True, "username": username}


@app.delete("/users/{username}/follow", status_code=200)
def unfollow_user(
    username: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unfollow a user. Idempotent."""
    target = db.query(User).filter(User.username == username).first()
    if not target:
        raise HTTPException(404, "User not found")
    follow = db.query(Follow).filter(
        Follow.follower_id == current_user.id,
        Follow.followee_id == target.id,
    ).first()
    if follow:
        db.delete(follow)
        db.commit()
    return {"following": False, "username": username}


# ─────────────────────────────────────────────────────────────────
# COMMENTS ON COMMITS
# ─────────────────────────────────────────────────────────────────

class CommentRequest(BaseModel):
    body: str


@app.get("/projects/{repo_id}/commits/{commit_id}/comments")
def list_comments(repo_id: str, commit_id: str, db: Session = Depends(get_db)):
    """List all comments on a commit, oldest first."""
    commit = db.query(Commit).filter(
        Commit.id == commit_id, Commit.repository_id == repo_id
    ).first()
    if not commit:
        raise HTTPException(404, "Commit not found")
    return [
        {"id": c.id, "body": c.body,
         "author": c.author.username if c.author else None,
         "created_at": c.created_at.isoformat()}
        for c in commit.comments
    ]


@app.post("/projects/{repo_id}/commits/{commit_id}/comments", status_code=201)
def add_comment(
    repo_id:    str,
    commit_id:  str,
    req:        CommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a comment to a commit."""
    commit = db.query(Commit).filter(
        Commit.id == commit_id, Commit.repository_id == repo_id
    ).first()
    if not commit:
        raise HTTPException(404, "Commit not found")
    if not req.body.strip():
        raise HTTPException(400, "Comment body cannot be empty")
    comment = Comment(commit_id=commit_id, author_id=current_user.id,
                      body=req.body.strip())
    db.add(comment); db.commit(); db.refresh(comment)
    return {"id": comment.id, "body": comment.body,
            "author": current_user.username,
            "created_at": comment.created_at.isoformat()}


@app.delete("/comments/{comment_id}", status_code=200)
def delete_comment(
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete your own comment."""
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(404, "Comment not found")
    if comment.author_id != current_user.id:
        raise HTTPException(403, "Cannot delete someone else\'s comment")
    db.delete(comment); db.commit()
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════════
# BEATS LIBRARY
# ═══════════════════════════════════════════════════════════════════

@app.get("/library")
def get_library(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all commits saved to the user's private My Beats library."""
    if not current_user.library_repo_id:
        return []
    commits = db.query(Commit).filter(
        Commit.repository_id == current_user.library_repo_id
    ).order_by(Commit.created_at.desc()).all()
    return [_commit_summary(c) for c in commits]


class LibrarySaveRequest(BaseModel):
    filename:    str                          # beat_outputs/<name>.wav
    mood:        Optional[str] = ""
    bpm:         Optional[float] = None
    key:         Optional[str] = ""
    energy:      Optional[float] = None
    duration:    Optional[float] = None
    description: Optional[str] = ""


@app.post("/library/save", status_code=201)
def save_to_library(
    req: LibrarySaveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One-click save a generated beat to the user's My Beats library."""
    # Ensure library repo exists (for accounts pre-dating this feature)
    if not current_user.library_repo_id:
        lib_repo = Repository(
            owner_id=current_user.id,
            name="My Beats",
            description="Auto-saved beats library",
            is_public=False,
        )
        db.add(lib_repo); db.commit(); db.refresh(lib_repo)
        current_user.library_repo_id = lib_repo.id
        db.commit()

    audio_url = f"/audio/{req.filename}" if not req.filename.startswith("/") else req.filename
    commit = Commit(
        repository_id=current_user.library_repo_id,
        author_id=current_user.id,
        message=req.description or f"Saved: {req.mood or req.filename}",
        audio_url=audio_url,
        mood=req.mood,
        bpm=req.bpm,
        key=req.key,
        energy=req.energy,
        duration=req.duration or 0.0,
    )
    db.add(commit); db.commit(); db.refresh(commit)
    # Bump repo updated_at
    repo = db.query(Repository).filter(
        Repository.id == current_user.library_repo_id
    ).first()
    if repo:
        repo.updated_at = datetime.utcnow()
        db.commit()
    return {"id": commit.id, "message": commit.message, "audio_url": commit.audio_url}


# ═══════════════════════════════════════════════════════════════════
# PATCH PROJECT
# ═══════════════════════════════════════════════════════════════════

class PatchProjectRequest(BaseModel):
    name:        Optional[str]  = None
    description: Optional[str] = None
    is_public:   Optional[bool] = None


@app.patch("/projects/{repo_id}")
def patch_project(
    repo_id: str,
    req: PatchProjectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update name / description / visibility of a project (owner only)."""
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(404, "Project not found")
    if repo.owner_id != current_user.id:
        raise HTTPException(403, "Not owner")
    if req.name        is not None: repo.name        = req.name
    if req.description is not None: repo.description = req.description
    if req.is_public   is not None: repo.is_public   = req.is_public
    repo.updated_at = datetime.utcnow()
    db.commit(); db.refresh(repo)
    return _repo_summary(repo)


# ═══════════════════════════════════════════════════════════════════
# BRANCHES
# ═══════════════════════════════════════════════════════════════════

@app.get("/projects/{repo_id}/branches")
def list_branches(
    repo_id: str,
    db: Session = Depends(get_db),
):
    """Return root commits (commits whose parent_hash is null) as branch roots."""
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(404, "Project not found")
    roots = db.query(Commit).filter(
        Commit.repository_id == repo_id,
        Commit.parent_id == None,
    ).order_by(Commit.created_at).all()
    return [_commit_summary(c) for c in roots]


# ═══════════════════════════════════════════════════════════════════
# DIFF  GET /projects/{repo_id}/commits/{hash_a}/diff/{hash_b}
# ═══════════════════════════════════════════════════════════════════

@app.get("/projects/{repo_id}/commits/{hash_a}/diff/{hash_b}")
def diff_commits(
    repo_id: str,
    hash_a:  str,
    hash_b:  str,
    db: Session = Depends(get_db),
):
    """Compare two commits: BPM/key/energy delta + per-stem diff."""
    ca = db.query(Commit).filter(
        Commit.id == hash_a, Commit.repository_id == repo_id
    ).first()
    cb = db.query(Commit).filter(
        Commit.id == hash_b, Commit.repository_id == repo_id
    ).first()
    if not ca or not cb:
        raise HTTPException(404, "One or both commits not found in this project")

    def _safe_delta(new, old):
        if new is None or old is None:
            return None
        return round(new - old, 4)

    # Stem diff
    stems_a = {s.type: s for s in db.query(Stem).filter(Stem.commit_id == ca.id).all()}
    stems_b = {s.type: s for s in db.query(Stem).filter(Stem.commit_id == cb.id).all()}
    all_types = sorted(set(stems_a) | set(stems_b))
    stem_diff = []
    for st in all_types:
        if st in stems_a and st in stems_b:
            status = "changed" if stems_a[st].audio_url != stems_b[st].audio_url else "unchanged"
        elif st in stems_b:
            status = "added"
        else:
            status = "removed"
        stem_diff.append({
            "stem_type": st,
            "status":    status,
            "a_url":     stems_a[st].audio_url if st in stems_a else None,
            "b_url":     stems_b[st].audio_url if st in stems_b else None,
        })

    return {
        "commit_a": _commit_summary(ca),
        "commit_b": _commit_summary(cb),
        "deltas": {
            "bpm":          _safe_delta(cb.bpm,      ca.bpm),
            "energy":       _safe_delta(cb.energy,   ca.energy),
            "duration":     _safe_delta(cb.duration, ca.duration),
            "key_changed":  ca.key != cb.key,
            "key_a":        ca.key,
            "key_b":        cb.key,
        },
        "stems": stem_diff,
    }


# ═══════════════════════════════════════════════════════════════════
# TRACKED GENERATION + SSE PROGRESS
# ═══════════════════════════════════════════════════════════════════

import threading, uuid as _uuid_mod

class TrackedGenerateRequest(BaseModel):
    name:   str
    prompt: Optional[str] = ""


@app.post("/generate/tracked")
def generate_tracked(req: TrackedGenerateRequest):
    """Start an async generation and return a task_id for SSE polling."""
    task_id = str(_uuid_mod.uuid4())
    _gen_progress[task_id] = {"status": "queued", "pct": 0, "url": None, "error": None}

    prompt = MOOD_PROMPTS.get(req.name, req.prompt) if not req.prompt else req.prompt

    def _run():
        try:
            _gen_progress[task_id].update({"status": "generating", "pct": 10})
            path, duration = _generate(prompt, req.name)
            _gen_progress[task_id].update({
                "status": "done", "pct": 100,
                "url": f"/audio/{path.name}",
                "filename": path.name,
                "duration": duration,
            })
        except Exception as e:
            _gen_progress[task_id].update({"status": "error", "pct": 0, "error": str(e)})

    threading.Thread(target=_run, daemon=True).start()
    return {"task_id": task_id}


@app.get("/sse/progress/{task_id}")
async def sse_progress(task_id: str):
    """Server-Sent Events stream for generation progress."""
    async def event_stream():
        for _ in range(300):          # max 5 min (300 × 1 s)
            info = _gen_progress.get(task_id, {"status": "unknown", "pct": 0})
            data = json.dumps(info)
            yield f"data: {data}\n\n"
            if info.get("status") in ("done", "error"):
                _gen_progress.pop(task_id, None)
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ── Run ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
