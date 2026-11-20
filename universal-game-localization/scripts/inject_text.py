#!/usr/bin/env python3
"""Write translated COPIES of plain-text game files into a patch folder (never touches the game).

Input: merged_translations.json + files.json (from extract_text.py) + the original game folder.
Output: <out>/<same relative paths> and PATCH_MANIFEST.json (SHA-256 of original and patched files,
for reversible install). Keeps each file's original encoding/BOM/line endings when possible.
Costs no AI tokens.
"""
from pathlib import Path
import argparse, hashlib, json, sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textio as T


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("merged", help="merged_translations.json")
    p.add_argument("--files", default="normalized/files.json")
    p.add_argument("--src-root", default="", help="original game folder (default: root stored in files.json)")
    p.add_argument("--out", default="patch")
    p.add_argument("--statuses", default="translated,approved", help="comma list; add needs_review to include flagged ones")
    args = p.parse_args()

    meta = json.loads(Path(args.files).read_text(encoding="utf-8"))
    root = Path(args.src_root or meta["root"]).resolve()
    out = Path(args.out).resolve()
    if out == root or root in out.parents:
        raise SystemExit("Refusing to write the patch inside the game folder.")
    ok = set(args.statuses.split(","))
    per_file = {}
    for e in json.loads(Path(args.merged).read_text(encoding="utf-8-sig"))["entries"]:
        if e.get("translation", "").strip() and e.get("status") in ok:
            rel, _, sid = e["id"].partition("::")
            per_file.setdefault(rel, {})[sid] = e["translation"]

    manifest, total, problems = [], 0, []
    for rel, trans in sorted(per_file.items()):
        info = meta["files"].get(rel)
        src = root / rel
        if info is None or not src.is_file():
            problems.append(f"{rel}: not in files.json or missing in source")
            continue
        data = src.read_bytes()
        text, _, _ = T.decode(data)
        new_text, applied, skipped = T.apply(info["adapter"], text, info["opts"], trans)
        stale = len(trans) - applied - len(skipped)
        if stale:
            problems.append(f"{rel}: {stale} entries no longer match the source file (changed or removed)")
        problems += [f"{rel}: {sid} skipped - {why}" for sid, why in skipped]
        if info["adapter"] in ("json", "csv") and T.apply(info["adapter"], text, info["opts"], {})[0] != text:
            problems.append(f"{rel}: {info['adapter']} formatting is re-serialized (content kept, whitespace/quoting may differ)")
        new_bytes, used = T.encode(new_text, info["codec"], info["bom"])
        if used != info["codec"]:
            problems.append(f"{rel}: original codec {info['codec']} cannot store this text; wrote UTF-8 (check the game can read it)")
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(new_bytes)
        manifest.append({"file": rel, "applied": applied, "codec": used, "original_sha256": sha(data), "patched_sha256": sha(new_bytes)})
        total += applied
    (out / "PATCH_MANIFEST.json").write_text(json.dumps({"source_root": str(root), "files": manifest}, indent=1), encoding="utf-8")
    print(f"Patched copies: {len(manifest)} file(s), {total} strings -> {out}")
    for pr in problems[:8]:
        print("  WARN", pr)
    if len(problems) > 8:
        print(f"  ... +{len(problems) - 8} more warnings")


if __name__ == "__main__":
    main()
