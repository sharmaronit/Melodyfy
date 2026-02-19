import pathlib
BASE = pathlib.Path(r"D:\Ronit Sharma\vs code\ML Models\hack")
OLD = ['nav{position:sticky', '.nav-logo{', '.nav-links{', '.nav-links a{', '.nav-spacer{', '.btn-ghost{', '.btn-green{']
for f in sorted(BASE.glob("*.html")):
    if f.stem.startswith("_"): continue
    txt = f.read_text(encoding="utf-8")
    bad = [p for p in OLD if p in txt]
    has_root = 'id="nav-root"' in txt
    has_script = 'src="nav.js"' in txt
    status = "OK  " if not bad and has_root and has_script else "WARN"
    print(f"{status}  {f.name:<28}  nav-root={has_root}  nav.js={has_script}  stale={bad}")
