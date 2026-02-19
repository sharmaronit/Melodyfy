# Melodyfy 🎵

An AI-powered music production platform featuring beat generation, stem separation, audio analysis, and a full studio DAW interface — all in the browser.

---

## Features

- **AI Beat Generator** — Generate beats from text prompts across 15+ genres (Trap, Lo-fi, EDM, Jazz, Cinematic, etc.)
- **Stem Separation** — Upload any track and split it into Drums, Bass, Vocals, and Other using Demucs
- **Studio DAW** — Full mixer with per-channel Vol, Pan, Reverb, 8D Spatial Audio, Mute/Solo/Reset, waveform view, and export
- **Music Library** — Browse and replay all generated beats with animated visualizer
- **Repository** — Version-controlled project storage with commit history and file tree
- **Community** — Discover and share projects with other users
- **Audio Visualizer** — Pure Canvas 2D audio-reactive visualizer across all pages
- **BPM / Key Detection** — Auto-detects tempo, key, mood, and energy from uploaded audio
- **Hum-to-Beat** — Record a melody and convert it to a full beat

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML/CSS/JS, Web Audio API, Canvas 2D |
| Backend | Python, FastAPI, Uvicorn |
| AI Models | Meta MusicGen (beat generation), Demucs (stem separation) |
| Audio | Web Audio API — ConvolverNode, StereoPannerNode, OfflineAudioContext |

---

## Project Structure

```
hack/
├── index.html          # Landing page
├── dashboard.html      # User dashboard
├── studio.html         # DAW / Stem mixer
├── library.html        # Beat library
├── repo.html           # Project repository
├── community.html      # Community feed
├── settings.html       # User settings
├── project_tree.html   # File tree viewer
├── analytics.html      # Audio analytics
├── explore.html        # Explore page
├── nav.js              # Shared navigation component
├── visualizer.js       # Canvas 2D audio visualizer
├── api_server.py       # FastAPI backend
├── beat_generator.py   # MusicGen beat generation
├── stem_separator.py   # Demucs stem separation
└── requirements.txt    # Python dependencies
```

---

## Getting Started

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the backend

```bash
cd hack
python api_server.py
```

Backend runs on `http://localhost:8000`

### 3. Serve the frontend

```bash
python -m http.server 8080
```

Open `http://localhost:8080` in your browser.

> **Note:** The frontend must be served over HTTP (not `file://`) due to ES module requirements.

---

## Requirements

- Python 3.10+
- CUDA-capable GPU recommended for fast MusicGen inference
- Node.js not required — pure vanilla frontend

---

## Screenshots

> Studio DAW with stem mixer, reverb/8D audio effects, and audio-reactive visualizer.

---

## License

MIT
