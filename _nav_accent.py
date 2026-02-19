"""
Melodyfy Phase: Wine-red → off-white accent + shared nav injection
Run: D:\Ronit Sharma\vs code\ML Models\.conda\python.exe D:\Ronit Sharma\vs code\ML Models\hack\_nav_accent.py
"""
import re, os, pathlib

BASE = pathlib.Path(r"D:\Ronit Sharma\vs code\ML Models\hack")
FILES = [
    "index.html","dashboard.html","explore.html","studio.html",
    "library.html","community.html","projects.html",
    "project_tree.html","repo.html","settings.html",
]

# ---------- color substitutions (ordered, most-specific first) ----------
COLOR_SUBS = [
    # root vars — exact token replacements
    ("--accent:#76192F",          "--accent:#EDE8DF"),
    ("--accent-hover:#8A2B3F",    "--accent-hover:#F0EDE6"),
    ("--green-btn:#76192F",       "--green-btn:#EDE8DF"),
    ("--green-hover:#8A2B3F",     "--green-hover:#F0EDE6"),
    ("--green-accent:#76192F",    "--green-accent:#EDE8DF"),

    # standalone hex usages (not inside rgba)
    ("#76192F",  "#EDE8DF"),
    ("#76192f",  "#EDE8DF"),  # lowercase variant
    ("#8A2B3F",  "#F0EDE6"),
    ("#8a2b3f",  "#F0EDE6"),
    ("#5a1222",  "#1a1a20"),  # gradient dark-red stop → dark neutral
    ("#1e0810",  "#0e0e12"),  # beat-art gradient start

    # rgba tints
    ("rgba(118,25,47,",  "rgba(237,232,223,"),
    ("rgba(118, 25, 47,","rgba(237,232,223,"),  # with spaces

    # button border that used to be near-invisible white → subtle off-white
    ("border-color:rgba(240,246,252,.05)","border-color:rgba(237,232,223,.18)"),

    # btn-green text — dark text on off-white button
    # We match the likely patterns carefully
    (".btn-green{background:var(--accent);border-color:rgba(237,232,223,.18);color:#fff;",
     ".btn-green{background:var(--accent);border-color:rgba(237,232,223,.18);color:#07070a;"),
    # if color:#fff appears slightly differently
    ("background:var(--accent);border-color:rgba(237,232,223,.18);color:#fff",
     "background:var(--accent);border-color:rgba(237,232,223,.18);color:#07070a"),
]

# ---------- nav injection ----------
NAV_PLACEHOLDER = '<div id="nav-root"></div>'
SCRIPT_TAG      = '<script src="nav.js"></script>'

# regex to strip any existing <nav> block
NAV_RE = re.compile(r'<nav[\s\S]*?</nav>', re.IGNORECASE)

def process(fname):
    path = BASE / fname
    txt  = path.read_text(encoding="utf-8")
    orig = txt

    # 1. color subs
    for old, new in COLOR_SUBS:
        txt = txt.replace(old, new)

    # 2. replace nav block with placeholder (except settings which has no nav yet)
    if fname == "settings.html":
        # settings uses navbar-container, normalise to nav-root
        txt = txt.replace('<div id="navbar-container"></div>', NAV_PLACEHOLDER)
        # if nav-root not present at all, inject after <body>
        if NAV_PLACEHOLDER not in txt:
            txt = txt.replace('<body', NAV_PLACEHOLDER + '\n<body', 1)
    else:
        # replace the whole <nav>...</nav> with the placeholder
        m = NAV_RE.search(txt)
        if m:
            txt = txt[:m.start()] + NAV_PLACEHOLDER + txt[m.end():]
        else:
            # no nav found — inject right after <body ...>
            txt = re.sub(r'(<body[^>]*>)', r'\1\n' + NAV_PLACEHOLDER, txt, count=1)

    # 3. add nav.js script before </body> if not already there
    if SCRIPT_TAG not in txt:
        txt = txt.replace("</body>", SCRIPT_TAG + "\n</body>", 1)

    if txt != orig:
        path.write_text(txt, encoding="utf-8")
        print(f"  ✓  {fname}")
    else:
        print(f"  –  {fname}  (no change)")

print("=== Melodyfy: accent recolor + shared nav ===")
for f in FILES:
    process(f)
print("\nDone. nav.js already written.")
