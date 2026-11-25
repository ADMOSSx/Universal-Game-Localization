#!/usr/bin/env python3
"""Extract translatable strings from supported plain-text game files (read-only source)."""
from pathlib import Path
import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textio as T

LOC_WORDS = ("local", "lang", "i18n", "l10n", "subtitle", "dialog", "translation", "caption")
# Generic words must be a whole token, otherwise Textures/ or Context/ would match "text".
LOC_TOKENS = {"string", "strings", "text", "texts"}
LOC_EXTS = {".int", ".lng", ".properties"}


def has_localization_hint(rel):
    for part in Path(rel).parts:
        low = part.lower()
        if any(word in low for word in LOC_WORDS):
            return True
        if LOC_TOKENS & set(re.split(r"[^a-z0-9]+", low)):
            return True
    return False


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def ensure_output_outside_source(path, source_base):
    absolute = Path(path).absolute()
    if any(part.is_symlink() for part in (absolute, *absolute.parents)):
        raise SystemExit(f"Refusing output path with a symbolic-link component: {path}")
    resolved = path.resolve()
    base = source_base.resolve()
    if resolved == base or base in resolved.parents:
        raise SystemExit(f"Refusing to write output inside the source/game folder: {resolved}")
    return resolved


def atomic_write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if any(part.is_symlink() for part in (path.parent, *path.parent.parents)):
        raise SystemExit(f"Refusing output parent containing a symbolic link: {path.parent}")
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=".localization-", suffix=".tmp", delete=False)
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", help="game/mod folder (or a single file) to read")
    p.add_argument("--out", default="normalized/strings.json")
    p.add_argument("--files", default="", help="where to write files.json (default: next to --out)")
    p.add_argument("--include", action="append", default=[], help="glob relative to root, repeatable")
    p.add_argument("--exclude", action="append", default=[], help="glob relative to root, repeatable")
    p.add_argument("--csv-col", default=None, help="CSV/TSV text column (name or index; default: guessed)")
    p.add_argument("--csv-id-col", default=None, help="CSV/TSV column to use as ID (default: row number)")
    p.add_argument("--no-header", action="store_true")
    p.add_argument("--json-keys", default="", help="regex: only JSON strings under matching key names")
    p.add_argument("--title", default="Unknown")
    p.add_argument("--source-lang", default="en")
    p.add_argument("--target-lang", default="ar")
    p.add_argument("--max-mb", type=float, default=20.0)
    p.add_argument("--force", action="store_true", help="replace existing regular output JSON files")
    args = p.parse_args()

    root_arg = Path(args.root)
    if root_arg.is_symlink():
        raise SystemExit("Refusing to extract through a symbolic-link root.")
    root = root_arg.resolve()
    if not root.exists() or not (root.is_dir() or root.is_file()):
        raise SystemExit(f"Not a file or folder: {root}")
    base = root.parent if root.is_file() else root

    out_arg = Path(args.out)
    files_arg = Path(args.files) if args.files else out_arg.parent / "files.json"
    if out_arg.is_symlink() or files_arg.is_symlink():
        raise SystemExit("Output files must not be symbolic links.")
    out = ensure_output_outside_source(out_arg, base)
    fpath = ensure_output_outside_source(files_arg, base)
    if out == fpath:
        raise SystemExit("--out and --files must be different paths.")
    for target in (out, fpath):
        if target.exists():
            if not args.force:
                raise SystemExit(f"Refusing to overwrite existing output: {target} (use --force to replace regular files).")
            if target.is_symlink() or not target.is_file():
                raise SystemExit(f"Refusing to replace non-regular output: {target}")
    if args.max_mb <= 0:
        raise SystemExit("--max-mb must be greater than zero.")

    if root.is_file():
        candidates = [root]
    else:
        candidates = []
        for dpath, dnames, fnames in os.walk(root, followlinks=False):
            dnames[:] = [d for d in dnames if not (Path(dpath) / d).is_symlink()]
            for name in fnames:
                candidates.append(Path(dpath) / name)

    files, entries, skipped = {}, [], []
    for f in sorted(candidates):
        try:
            if f.is_symlink():
                skipped.append(f"{f}: symbolic link")
                continue
            rel = f.relative_to(base).as_posix() if not root.is_file() else f.name
            ext = f.suffix.lower()
            if ext not in T.ADAPTERS:
                continue
            hinted = has_localization_hint(rel)
            if args.include:
                selected = any(fnmatch.fnmatch(rel, pattern) for pattern in args.include)
            elif ext in LOC_EXTS:
                selected = True
            else:
                selected = hinted
            if any(fnmatch.fnmatch(rel, pattern) for pattern in args.exclude):
                selected = False
            if not selected:
                continue
            st = f.stat()
            if st.st_size > args.max_mb * 1048576:
                skipped.append(f"{rel} (larger than --max-mb)")
                continue
            raw = f.read_bytes()
            text, codec, bom = T.decode(raw)
            adapter = T.ADAPTERS[ext]
            opts = {"delim": "tab" if ext == ".tsv" else "comma", "no_header": args.no_header}
            if args.csv_col is not None:
                opts["csv_col"] = args.csv_col
            if args.csv_id_col is not None:
                opts["csv_id_col"] = args.csv_id_col
            if args.json_keys:
                opts["json_keys"] = args.json_keys
            items = T.parse(adapter, text, opts)
        except Exception as ex:
            skipped.append(f"{f}: {type(ex).__name__}: {ex}")
            continue
        if not items:
            continue
        files[rel] = {"adapter": adapter, "codec": codec, "bom": bom, "opts": opts,
                      "count": len(items), "size": len(raw), "source_sha256": sha256_bytes(raw)}
        for it in items:
            entries.append({"id": f"{rel}::{it['sid']}", "source_file": rel, "context": "unknown",
                            "original": it["original"], "translation": "", "status": "untranslated"})

    if not entries:
        print("No strings found. Use --include with an explicit relative glob, or the format needs a custom adapter.")
        if skipped:
            print("Skipped:", "; ".join(skipped[:5]))
        raise SystemExit(1)

    strings_payload = {"schema_version": "1.0",
                       "project": {"game_title": args.title, "source_language": args.source_lang,
                                   "target_language": args.target_lang},
                       "entries": entries}
    files_payload = {"root": str(base), "files": files, "integrity": "sha256"}
    atomic_write_text(out, json.dumps(strings_payload, ensure_ascii=False, indent=1))
    atomic_write_text(fpath, json.dumps(files_payload, ensure_ascii=False, indent=1))
    print(f"{len(entries)} strings from {len(files)} file(s) -> {out}")
    for rel, info in list(files.items())[:8]:
        print(f"  {rel}: {info['count']} ({info['adapter']}, {info['codec']})")
    if len(files) > 8:
        print(f"  ... +{len(files) - 8} more files (see {fpath.name})")
    if skipped:
        print(f"Skipped {len(skipped)} item(s); first {min(3, len(skipped))} shown:")
        for item in skipped[:3]:
            print(f"  {item}")


if __name__ == "__main__":
    main()
