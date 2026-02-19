import pathlib, re
BASE = pathlib.Path(r"D:\Ronit Sharma\vs code\ML Models\hack")
FILES = ["index.html","dashboard.html","explore.html","settings.html","studio.html"]

for fname in FILES:
    txt = (BASE / fname).read_text(encoding="utf-8")
    acc  = re.search(r"--accent:#[A-Fa-f0-9]+", txt)
    phld = '<div id="nav-root"></div>' in txt
    scrp = '<script src="nav.js"></script>' in txt
    old_red = "#76192F" in txt or "#76192f" in txt
    old_rgba = "rgba(118,25,47," in txt
    btn  = re.search(r"\.btn-green\{[^}]+\}", txt)
    bc   = btn.group(0)[:90] if btn else "(not found)"
    print(f"{fname}:")
    print(f"  accent={acc.group(0) if acc else 'MISSING'}  nav-root={phld}  nav.js={scrp}")
    print(f"  old-wine-red={old_red}  old-rgba={old_rgba}")
    print(f"  btn-green: {bc}")
    print()
