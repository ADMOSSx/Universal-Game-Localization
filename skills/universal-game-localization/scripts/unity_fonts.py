#!/usr/bin/env python3
"""List Unity Font assets and check Arabic glyph coverage. READ-ONLY.

Needs two packages (ask the user before installing):  pip install UnityPy fonttools
Usage: unity_fonts.py <game_Data folder or one .assets file> [--text normalized/merged.json]
With --text it also lists which characters used by the translation are missing from each font.
Why: Unity fonts live inside .assets files, so inventory.py cannot see them. A text component whose
font lacks the glyphs shows empty boxes. This tells you which Font assets exist and what they cover.
"""
from pathlib import Path
import argparse, io, json, sys


def used_codepoints(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    entries = data.get("entries", []) if isinstance(data, dict) else data
    return {ord(c) for e in entries for c in str(e.get("translation", "")) if ord(c) > 127 and not c.isspace()}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("target", help="<game>_Data folder or a single .assets file")
    p.add_argument("--text", default="", help="merged/normalized JSON; check its characters against each font")
    p.add_argument("--max-mb", type=float, default=80.0, help="skip .assets files larger than this")
    args = p.parse_args()
    try:
        import UnityPy
        from fontTools.ttLib import TTFont
    except ImportError:
        print("Missing packages. Ask the user, then run: pip install UnityPy fonttools")
        raise SystemExit(2)

    target = Path(args.target)
    files = [target] if target.is_file() else sorted(target.glob("*.assets"))
    if not files:
        raise SystemExit(f"No .assets files found in {target}")
    need = used_codepoints(args.text) if args.text else set()
    found = scanned = with_arabic = 0
    for f in files:
        if f.stat().st_size > args.max_mb * 1048576:
            print(f"skip {f.name} (larger than --max-mb)")
            continue
        try:
            env = UnityPy.load(str(f))
            scanned += 1
            fonts = [o for o in env.objects if o.type.name == "Font"]
        except Exception as ex:
            print(f"skip {f.name}: {type(ex).__name__}")
            continue
        for obj in fonts:
            d = obj.read()
            data = bytes(d.m_FontData or b"")
            found += 1
            line = f"{f.name} | {d.m_Name} | fallback names: {list(d.m_FontNames or [])}"
            if not data:
                print(line + " | no embedded data (uses OS fonts by name)")
                continue
            try:
                cmap = TTFont(io.BytesIO(data)).getBestCmap()
            except Exception as ex:
                print(line + f" | unreadable font data ({type(ex).__name__})")
                continue
            ar = sum(1 for c in cmap if 0x600 <= c <= 0x6FF)
            pf = sum(1 for c in cmap if 0xFB50 <= c <= 0xFDFF or 0xFE70 <= c <= 0xFEFF)
            with_arabic += bool(ar)
            line += f" | {len(data) // 1024} KB, {len(cmap)} chars, Arabic letters {ar}, presentation forms {pf}"
            if need:
                miss = sorted(c for c in need if c not in cmap)
                line += f" | missing {len(miss)}/{len(need)} used chars" + (
                    ": " + " ".join(f"U+{c:04X}" for c in miss[:10]) + (" ..." if len(miss) > 10 else "") if miss else "")
            print(line)
    print(f"Scanned {scanned} file(s): {found} Font asset(s), {with_arabic} with Arabic letters.")
    if found == 0:
        print("No Font assets here. Fonts may be in other .assets/bundles, or the game uses TextMesh Pro / bitmap fonts.")


if __name__ == "__main__":
    main()
