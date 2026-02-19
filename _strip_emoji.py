"""
Strip picture-emoji from all hack/ HTML and JS files.
Keeps: typographic (— … – → ← ↑ ↓ ✓ ✗ ✕ ▶ ⏸ ⏹ ♯ ♭ ♩ ─ ═ ✦)
Removes: U+1F000-U+1FFFF (objects/faces/nature), U+FE0F (variation selector),
         specific misc-symbols still emoji-ish, BOM U+FEFF
"""
import re, pathlib

BASE  = pathlib.Path(r"D:\Ronit Sharma\vs code\ML Models\hack")
FILES = (list(BASE.glob("*.html")) +
         list(BASE.glob("*.js")))

# Characters to KEEP even if they'd otherwise be stripped
KEEP = set("—…–→←↑↓↗↙✓✗✕✖▶◀⏸⏹⏺⏭⏮▸⯈▾─━═║╔╗╚╝░▓♯♭♩♪♫✦◆◇•·⬇⬆⬅➡✸★☆⭐")

# Picture-emoji ranges to remove
STRIP_RE = re.compile(
    r"[\U0001F000-\U0001FFFF"   # main emoji block (food, faces, objects …)
    r"\U00002194-\U00002199"    # arrows (↔↕↗↘↙↖) — only if NOT in keep
    r"\U00002600-\U000026FF"    # misc symbols (☕⚡⚖☀☁…)
    r"\U00002700-\U000027BF"    # dingbats (✂✈✉…)
    r"\U0001F900-\U0001F9FF"    # supplemental symbols
    r"\U0001FA00-\U0001FA6F"    # chess / other
    r"\U0001FA70-\U0001FAFF"    # symbols & pictographs ext-A
    r"\uFE0F"                   # variation selector-16 (emoji presentation)
    r"\uFEFF"                   # BOM
    r"]",
    re.UNICODE
)

def clean(txt):
    def replacer(m):
        ch = m.group(0)
        return ch if ch in KEEP else ""
    return STRIP_RE.sub(replacer, txt)

def collapse_spaces(txt):
    # collapse multiple spaces introduced by removal (but not in <style>/<script> indentation)
    # only collapse 2+ consecutive spaces that aren't at line-start
    txt = re.sub(r"(?<!^)(?<!\n) {2,}", " ", txt, flags=re.MULTILINE)
    # trim trailing whitespace left after an emoji at end of a token
    txt = re.sub(r" +([<\n])", r"\1", txt)
    # strip orphan leading space in button/anchor text like "> Generate Beat"
    txt = re.sub(r'(>)\s+([A-Z])', lambda m: m.group(1)+m.group(2), txt)
    return txt

total = 0
for f in sorted(FILES):
    if f.stem.startswith("_"):
        continue
    orig = f.read_text(encoding="utf-8")
    cleaned = clean(orig)
    cleaned = collapse_spaces(cleaned)
    if cleaned != orig:
        removed = len(orig) - len(cleaned)
        f.write_text(cleaned, encoding="utf-8")
        total += removed
        print(f"  {f.name:<28}  -{removed} chars")
    else:
        print(f"  {f.name:<28}  (no change)")

print(f"\nDone — {total} chars removed across all files.")
