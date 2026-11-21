#!/usr/bin/env python3
"""Read-only inventory of a game folder. Engine hints are leads, not conclusions."""
from pathlib import Path
import argparse
import collections
import csv
import hashlib
import json
import os
import sys
import time

MAGIC = [
    (b"UnityFS", "Unity AssetBundle (UnityFS)"), (b"UnityWeb", "Unity web bundle"),
    (b"UnityRaw", "Unity raw bundle"), (b"SQLite format 3\x00", "SQLite database"),
    (b"RPGMV", "RPG Maker MV/MZ encrypted asset"), (b"RPA-3.0", "Ren'Py archive (RPA-3.0)"),
    (b"RPA-2.0", "Ren'Py archive (RPA-2.0)"), (b"GDPC", "Godot PCK"),
    (b"\x89PNG", "PNG image"), (b"\xff\xd8\xff", "JPEG image"), (b"GIF8", "GIF image"),
    (b"DDS ", "DDS texture"), (b"OggS", "Ogg audio"), (b"RIFF", "RIFF (wav/avi/webp)"),
    (b"fLaC", "FLAC audio"), (b"ID3", "MP3 (ID3)"), (b"%PDF", "PDF"),
    (b"<?xml", "XML text"), (b"\xef\xbb\xbf", "UTF-8 BOM text"),
    (b"\xff\xfe", "UTF-16 LE BOM text"), (b"\xfe\xff", "UTF-16 BE BOM text"),
    (b"PK\x03\x04", "ZIP-based archive"), (b"7z\xbc\xaf\x27\x1c", "7-Zip"),
    (b"Rar!", "RAR"), (b"\x1f\x8b", "gzip"), (b"\x34\x12\xaa\x55", "Valve VPK"),
    (b"OTTO", "OpenType (CFF) font"), (b"\x00\x01\x00\x00", "TrueType font (or other)"),
    (b"ttcf", "TrueType collection"), (b"wOFF", "WOFF"), (b"wOF2", "WOFF2"),
    (b"MZ", "Windows PE (exe/dll)"), (b"\x7fELF", "ELF binary"),
]
LOC_KEYWORDS = ("local", "lang", "i18n", "l10n", "string", "subtitle", "dialog", "translation", "caption", "text")
LOC_EXTS = {".po", ".pot", ".mo", ".locres", ".locmeta", ".resx", ".resw", ".xliff", ".xlf",
            ".strings", ".dlstrings", ".ilstrings", ".ini", ".int", ".lng", ".lang", ".loc", ".tsv",
            ".properties", ".rpy", ".rpyc"}
FONT_EXTS = {".ttf", ".otf", ".ttc", ".woff", ".woff2", ".fnt", ".fon", ".bmfc"}
ARCHIVE_EXTS = {".pak", ".ucas", ".utoc", ".vpk", ".pck", ".rpa", ".bsa", ".ba2", ".arc", ".bundle",
                ".assets", ".upk", ".dat", ".bin", ".zip", ".7z", ".rar", ".asar", ".rgss3a",
                ".rgss2a", ".rgssad", ".wad"}
EXEC_EXTS = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh", ".so", ".dylib", ".msi"}


def guess_magic(head):
    for signature, label in MAGIC:
        if head.startswith(signature):
            return label
    return ""


def sha256(path, limit_bytes):
    try:
        if path.stat().st_size > limit_bytes:
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def detect_engines(names, exts, dirs):
    evidence = collections.defaultdict(list)

    def add(engine, clue):
        evidence[engine].append(clue)

    if "unityplayer.dll" in names:
        add("Unity", "UnityPlayer.dll")
    if {"globalgamemanagers", "data.unity3d", "resources.assets"} & set(names):
        add("Unity", "Unity data files")
    if "managed" in dirs and any(name.endswith("_data") for name in dirs):
        add("Unity (Mono)", "*_Data/Managed present")
    if "gameassembly.dll" in names or "global-metadata.dat" in names:
        add("Unity (IL2CPP)", "GameAssembly.dll / global-metadata.dat")
    if {".uasset", ".umap", ".locres", ".utoc", ".ucas"} & set(exts):
        add("Unreal Engine 4/5", "UE package/locres/IoStore extensions")
    if ".pak" in exts and "paks" in dirs:
        add("Unreal Engine 4/5", "Paks directory with .pak")
    if ".upk" in exts or "cookedpc" in dirs:
        add("Unreal Engine 3", ".upk or CookedPC")
    if ".int" in exts and ({"localization", "localisation"} & dirs):
        add("Unreal Engine 3", "Localization/*.int")
    if ".pck" in exts or "project.godot" in names:
        add("Godot", ".pck / project.godot")
    if {"data.win", "game.unx", "game.droid", "game.ios"} & set(names):
        add("GameMaker", "data.win / game.unx")
    if "renpy" in dirs or {".rpa", ".rpyc", ".rpy"} & set(exts):
        add("Ren'Py", "renpy folder or script/archive extension")
    if {".rvdata2", ".rvdata", ".rxdata", ".rgss3a", ".rgss2a", ".rgssad"} & set(exts):
        add("RPG Maker (XP/VX/VXAce)", "rvdata/rxdata/rgss archive")
    if "rpg_core.js" in names:
        add("RPG Maker MV", "rpg_core.js")
    if "rmmz_core.js" in names:
        add("RPG Maker MZ", "rmmz_core.js")
    if ".vpk" in exts or "gameinfo.txt" in names:
        add("Source engine", ".vpk / gameinfo.txt")
    if ".asar" in exts or "package.nw" in names:
        add("Electron / NW.js", "app.asar / package.nw")
    if {".esm", ".esp", ".bsa", ".ba2", ".strings", ".dlstrings", ".ilstrings"} & set(exts):
        add("Bethesda Creation Engine", "esm/esp/bsa/ba2/strings files")
    if ".jar" in exts:
        add("Java-based", ".jar files")
    return sorted(
        [{"engine_candidate": name, "evidence": sorted(set(clues)),
          "script_confidence": "medium" if len(set(clues)) >= 2 else "low"}
         for name, clues in evidence.items()],
        key=lambda item: -len(item["evidence"])
    )


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_dir")
    parser.add_argument("--out", default="reports", help="output folder outside the game directory")
    parser.add_argument("--hash-limit-mb", type=int, default=0, help="SHA-256 files up to this size (0 disables)")
    args = parser.parse_args()
    if args.hash_limit_mb < 0:
        raise SystemExit("--hash-limit-mb cannot be negative.")

    root_arg = Path(args.game_dir)
    if root_arg.is_symlink():
        raise SystemExit("Refusing to inventory through a symbolic-link root.")
    root = root_arg.resolve()
    out_arg = Path(args.out)
    if out_arg.is_symlink():
        raise SystemExit("Refusing a symbolic-link output directory.")
    out = out_arg.resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a folder: {root}")
    if out == root or root in out.parents:
        raise SystemExit("Refusing to write reports inside the game folder.")
    if any(parent.is_symlink() for parent in (out, *out.parents) if parent.exists()):
        raise SystemExit("Output path contains a symbolic link.")
    out.mkdir(parents=True, exist_ok=True)

    rows, errors = [], []
    names, exts, dirs = {}, collections.Counter(), set()
    limit = args.hash_limit_mb * 1024 * 1024
    for dpath, dnames, fnames in os.walk(root, followlinks=False, onerror=lambda ex: errors.append(str(ex))):
        current = Path(dpath)
        dnames[:] = [name for name in dnames if not (current / name).is_symlink()]
        for name in dnames:
            dirs.add(name.lower())
        for filename in fnames:
            path = current / filename
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                errors.append(f"{rel}: symbolic link skipped")
                continue
            try:
                stat = path.stat()
                with path.open("rb") as stream:
                    head = stream.read(16)
            except OSError as ex:
                errors.append(f"{rel}: {ex}")
                continue
            ext = path.suffix.lower()
            names.setdefault(filename.lower(), rel)
            exts[ext] += 1
            rows.append({
                "path": rel, "size": stat.st_size, "ext": ext, "magic_hex": head[:8].hex(),
                "magic_guess": guess_magic(head),
                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                "sha256": sha256(path, limit) if limit else "",
            })

    with (out / "file_inventory.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "size", "ext", "magic_hex", "magic_guess", "modified", "sha256"])
        writer.writeheader()
        writer.writerows(rows)

    def is_localization_candidate(row):
        parts = [part.lower() for part in Path(row["path"]).parts]
        name_hint = any(word in Path(parts[-1]).stem for word in LOC_KEYWORDS)
        path_hint = any(word in part for part in parts[:-1] for word in LOC_KEYWORDS)
        return row["ext"] in LOC_EXTS or name_hint or path_hint

    def by_dir(paths, count=12):
        counts = collections.Counter(Path(path).parent.as_posix() for path in paths)
        return [{"dir": directory, "files": number} for directory, number in counts.most_common(count)]

    candidates = [row["path"] for row in rows if is_localization_candidate(row)]
    fonts = [row["path"] for row in rows if row["ext"] in FONT_EXTS]
    archives = [row for row in rows if row["ext"] in ARCHIVE_EXTS]
    executables = [row["path"] for row in rows if row["ext"] in EXEC_EXTS and "/" not in row["path"]]
    total_bytes = sum(row["size"] for row in rows)
    summary = {
        "game_dir": str(root), "total_files": len(rows), "total_mb": round(total_bytes / 1048576, 1),
        "top_extensions": [f"{ext or '(none)'}:{count}" for ext, count in exts.most_common(15)],
        "engine_hints": detect_engines(names, exts, dirs),
        "localization_candidates": {"count": len(candidates), "top_dirs": by_dir(candidates), "sample": candidates[:12]},
        "fonts": {"count": len(fonts), "sample": fonts[:8]},
        "archives": {"count": len(archives), "biggest": [
            {"path": row["path"], "mb": round(row["size"] / 1048576, 1)}
            for row in sorted(archives, key=lambda row: -row["size"])[:8]]},
        "root_executables": executables[:8], "unreadable_count": len(errors),
        "note": "Engine hints are leads only. Full file list is in file_inventory.csv; inspect selectively.",
    }
    (out / "INVENTORY_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Inventoried {len(rows)} files ({summary['total_mb']} MB). Reports in {out}")
    for hint in summary["engine_hints"][:5]:
        print(f"  hint: {hint['engine_candidate']} [{hint['script_confidence']}] <- {'; '.join(hint['evidence'])}")
    if errors:
        print(f"  {len(errors)} unreadable/symlink path(s) skipped.")


if __name__ == "__main__":
    main()
