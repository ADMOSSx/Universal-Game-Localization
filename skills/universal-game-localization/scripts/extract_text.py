#!/usr/bin/env python3
"""Extract translatable strings from plain-text game files into normalized/strings.json (read-only).

Supported without writing any custom code: ini-like (.ini .int .properties .lng), .json, .csv/.tsv, .txt.
Binary/proprietary formats are NOT handled here (investigate those separately).
Also writes files.json (per-file adapter/encoding) which inject_text.py needs. Costs no AI tokens.
"""
from pathlib import Path
import argparse, fnmatch, json, os, sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textio as T

LOC_WORDS = ("local", "lang", "i18n", "l10n", "string", "subtitle", "dialog", "translation", "caption", "text")
LOC_EXTS = {".int", ".lng", ".properties"}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", help="game/mod folder (or a single file) to read")
    p.add_argument("--out", default="normalized/strings.json")
    p.add_argument("--files", default="", help="where to write files.json (default: next to --out)")
    p.add_argument("--include", action="append", default=[], help="glob relative to root, repeatable (e.g. 'Localization/INT/*.int')")
    p.add_argument("--csv-col", default=None, help="CSV/TSV text column (name or index; default: guessed)")
    p.add_argument("--csv-id-col", default=None, help="CSV/TSV column to use as ID (default: row number)")
    p.add_argument("--no-header", action="store_true")
    p.add_argument("--json-keys", default="", help="regex: only JSON strings under matching key names")
    p.add_argument("--title", default="Unknown")
    p.add_argument("--source-lang", default="en")
    p.add_argument("--target-lang", default="ar")
    p.add_argument("--max-mb", type=float, default=20.0)
    args = p.parse_args()

    root = Path(args.root).resolve()
    base = root.parent if root.is_file() else root
    cand = [root] if root.is_file() else [Path(d) / f for d, _, fs in os.walk(root) for f in fs]
    files = {}
    entries = []
    skipped = []
    for f in sorted(cand):
        rel = f.relative_to(base).as_posix() if not root.is_file() else f.name
        ext = f.suffix.lower()
        if ext not in T.ADAPTERS:
            continue
        if args.include:
            if not any(fnmatch.fnmatch(rel, g) for g in args.include):
                continue
        elif not (root.is_file() or ext in LOC_EXTS or any(w in part.lower() for part in rel.split("/")[:-1] for w in LOC_WORDS)):
            continue
        if f.stat().st_size > args.max_mb * 1048576:
            skipped.append(f"{rel} (too big)")
            continue
        adapter = T.ADAPTERS[ext]
        opts = {"delim": "tab" if ext == ".tsv" else "comma", "no_header": args.no_header}
        if args.csv_col is not None:
            opts["csv_col"] = args.csv_col
        if args.csv_id_col is not None:
            opts["csv_id_col"] = args.csv_id_col
        if args.json_keys:
            opts["json_keys"] = args.json_keys
        try:
            text, codec, bom = T.decode(f.read_bytes())
            items = T.parse(adapter, text, opts)
        except Exception as ex:
            skipped.append(f"{rel} ({type(ex).__name__}: {ex})")
            continue
        if not items:
            continue
        files[rel] = {"adapter": adapter, "codec": codec, "bom": bom, "opts": opts, "count": len(items)}
        for it in items:
            entries.append({"id": f"{rel}::{it['sid']}", "source_file": rel, "context": "unknown",
                            "original": it["original"], "translation": "", "status": "untranslated"})

    if not entries:
        print("No strings found. Pass --include 'relative/glob' for the files to read, or the format needs a custom adapter.")
        if skipped:
            print("Skipped:", "; ".join(skipped[:5]))
        raise SystemExit(1)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema_version": "1.0",
                               "project": {"game_title": args.title, "source_language": args.source_lang,
                                           "target_language": args.target_lang},
                               "entries": entries}, ensure_ascii=False, indent=1), encoding="utf-8")
    fpath = Path(args.files) if args.files else out.parent / "files.json"
    fpath.write_text(json.dumps({"root": str(base), "files": files}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(entries)} strings from {len(files)} file(s) -> {out}")
    for rel, info in list(files.items())[:8]:
        print(f"  {rel}: {info['count']} ({info['adapter']}, {info['codec']})")
    if len(files) > 8:
        print(f"  ... +{len(files) - 8} more files (see {fpath.name})")
    if skipped:
        print(f"Skipped {len(skipped)}: " + "; ".join(skipped[:3]))


if __name__ == "__main__":
    main()
