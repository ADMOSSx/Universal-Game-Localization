#!/usr/bin/env python3
"""Read-only inventory of a game folder (step 1 helper).

Writes reports/file_inventory.csv and reports/INVENTORY_SUMMARY.json.
It only READS files (first 16 bytes of each, plus optional SHA-256). It never edits, runs,
or extracts anything. Engine hints are LEADS, not conclusions: verify before relying on them.
"""
from pathlib import Path
import argparse, collections, csv, hashlib, json, os, sys, time

MAGIC = [
    (b"UnityFS", "Unity AssetBundle (UnityFS)"), (b"UnityWeb", "Unity web bundle"), (b"UnityRaw", "Unity raw bundle"),
    (b"SQLite format 3\x00", "SQLite database"), (b"RPGMV", "RPG Maker MV/MZ encrypted asset"),
    (b"RPA-3.0", "Ren'Py archive (RPA-3.0)"), (b"RPA-2.0", "Ren'Py archive (RPA-2.0)"), (b"GDPC", "Godot PCK"),
    (b"\x89PNG", "PNG image"), (b"\xff\xd8\xff", "JPEG image"), (b"GIF8", "GIF image"), (b"DDS ", "DDS texture"),
    (b"OggS", "Ogg audio"), (b"RIFF", "RIFF (wav/avi/webp)"), (b"fLaC", "FLAC audio"), (b"ID3", "MP3 (ID3)"),
    (b"%PDF", "PDF"), (b"<?xml", "XML text"), (b"\xef\xbb\xbf", "UTF-8 BOM text"), (b"\xff\xfe", "UTF-16 LE BOM text"),
    (b"\xfe\xff", "UTF-16 BE BOM text"), (b"PK\x03\x04", "ZIP-based archive"), (b"7z\xbc\xaf\x27\x1c", "7-Zip"),
    (b"Rar!", "RAR"), (b"\x1f\x8b", "gzip"), (b"\x34\x12\xaa\x55", "Valve VPK"), (b"OTTO", "OpenType (CFF) font"),
    (b"\x00\x01\x00\x00", "TrueType font (or other)"), (b"ttcf", "TrueType collection"), (b"wOFF", "WOFF font"),
    (b"wOF2", "WOFF2 font"), (b"MZ", "Windows PE (exe/dll)"), (b"\x7fELF", "ELF binary"),
]
LOC_KEYWORDS = ("local", "lang", "i18n", "l10n", "string", "subtitle", "dialog", "translation", "caption", "text")
LOC_EXTS = {".po", ".pot", ".mo", ".locres", ".locmeta", ".resx", ".resw", ".xliff", ".xlf", ".strings", ".dlstrings",
            ".ilstrings", ".int", ".lng", ".lang", ".loc", ".tsv", ".properties", ".rpy", ".rpyc"}
FONT_EXTS = {".ttf", ".otf", ".ttc", ".woff", ".woff2", ".fnt", ".fon", ".bmfc"}
ARCHIVE_EXTS = {".pak", ".ucas", ".utoc", ".vpk", ".pck", ".rpa", ".bsa", ".ba2", ".arc", ".bundle", ".assets",
                ".upk", ".dat", ".bin", ".zip", ".7z", ".rar", ".asar", ".rgss3a", ".rgss2a", ".rgssad", ".wad"}
EXEC_EXTS = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh", ".so", ".dylib", ".msi"}


def guess_magic(head: bytes) -> str:
    for sig, name in MAGIC:
        if head.startswith(sig):
            return name
    return ""


def sha256(path, limit_bytes):
    try:
        if os.path.getsize(path) > limit_bytes:
            return ""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def detect_engines(names, exts, dirs):
    ev = collections.defaultdict(list)
    def add(engine, text): ev[engine].append(text)
    if "unityplayer.dll" in names: add("Unity", "UnityPlayer.dll")
    if {"globalgamemanagers", "data.unity3d", "resources.assets"} & set(names): add("Unity", "Unity data files (globalgamemanagers/resources.assets/data.unity3d)")
    if "managed" in dirs and any(d.endswith("_data") for d in dirs): add("Unity (Mono)", "*_Data/Managed present")
    if "gameassembly.dll" in names or "global-metadata.dat" in names: add("Unity (IL2CPP)", "GameAssembly.dll / global-metadata.dat")
    if {".uasset", ".umap", ".locres", ".utoc", ".ucas"} & set(exts): add("Unreal Engine 4/5", "UE package/locres/IoStore extensions")
    if ".pak" in exts and "paks" in dirs: add("Unreal Engine 4/5", "Content/Paks/*.pak")
    if ".upk" in exts or "cookedpc" in dirs: add("Unreal Engine 3", ".upk or CookedPC folder")
    if ".int" in exts and ("localization" in dirs or "localisation" in dirs): add("Unreal Engine 3", "Localization/*.int")
    if ".pck" in exts: add("Godot", ".pck")
    if "project.godot" in names: add("Godot", "project.godot")
    if {"data.win", "game.unx", "game.droid", "game.ios"} & set(names): add("GameMaker", "data.win / game.unx")
    if "renpy" in dirs: add("Ren'Py", "renpy/ folder")
    if {".rpa", ".rpyc", ".rpy"} & set(exts): add("Ren'Py", ".rpa/.rpyc/.rpy files")
    if {".rvdata2", ".rvdata", ".rxdata", ".rgss3a", ".rgss2a", ".rgssad"} & set(exts): add("RPG Maker (VX/VXAce/XP)", "rvdata/rxdata/rgss archive")
    if "rpg_core.js" in names: add("RPG Maker MV", "js/rpg_core.js")
    if "rmmz_core.js" in names: add("RPG Maker MZ", "js/rmmz_core.js")
    if {".rpgmvp", ".rpgmvm", ".rpgmvo"} & set(exts): add("RPG Maker MV/MZ", "encrypted .rpgmv* assets")
    if ".vpk" in exts or "gameinfo.txt" in names: add("Source engine", ".vpk / gameinfo.txt")
    if {".asar"} & set(exts) or "package.nw" in names: add("Electron / NW.js (web-based)", "app.asar / package.nw")
    if {".esm", ".esp", ".bsa", ".ba2", ".strings", ".dlstrings", ".ilstrings"} & set(exts): add("Bethesda Creation Engine", "esm/esp/bsa/ba2/strings files")
    if ".jar" in exts: add("Java-based", ".jar files")
    out = []
    for engine, evidence in ev.items():
        out.append({"engine_candidate": engine, "evidence": sorted(set(evidence)),
                    "script_confidence": "medium" if len(set(evidence)) >= 2 else "low"})
    return sorted(out, key=lambda x: -len(x["evidence"]))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("game_dir")
    p.add_argument("--out", default="reports", help="output folder (use your workspace, never the game folder)")
    p.add_argument("--hash-limit-mb", type=int, default=0, help="SHA-256 files up to this size (0 = no hashing)")
    args = p.parse_args()

    root = Path(args.game_dir).resolve()
    out = Path(args.out).resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a folder: {root}")
    if root == out or root in out.parents:
        raise SystemExit("Refusing to write reports inside the game folder. Choose a separate --out workspace.")
    out.mkdir(parents=True, exist_ok=True)

    rows, errors = [], []
    names, exts, dirs = {}, collections.Counter(), set()
    ext_bytes = collections.Counter()
    limit = args.hash_limit_mb * 1024 * 1024
    for dpath, dnames, fnames in os.walk(root, followlinks=False, onerror=lambda e: errors.append(str(e))):
        for d in dnames:
            dirs.add(d.lower())
        for fn in fnames:
            fp = Path(dpath) / fn
            rel = fp.relative_to(root).as_posix()
            try:
                st = fp.stat()
                with open(fp, "rb") as f:
                    head = f.read(16)
            except OSError as ex:
                errors.append(f"{rel}: {ex}")
                continue
            ext = fp.suffix.lower()
            names.setdefault(fn.lower(), rel)
            exts[ext] += 1
            ext_bytes[ext] += st.st_size
            rows.append({"path": rel, "size": st.st_size, "ext": ext, "magic_hex": head[:8].hex(),
                         "magic_guess": guess_magic(head), "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                         "sha256": sha256(fp, limit) if limit else ""})

    with open(out / "file_inventory.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["path", "size", "ext", "magic_hex", "magic_guess", "modified", "sha256"])
        w.writeheader()
        w.writerows(rows)

    def is_loc(r):
        low = r["path"].lower()
        return r["ext"] in LOC_EXTS or any(k in part for part in low.split("/")[:-1] for k in LOC_KEYWORDS)
    def by_dir(paths, n=12):
        c = collections.Counter(str(Path(x).parent.as_posix()) for x in paths)
        return [{"dir": d, "files": k} for d, k in c.most_common(n)]
    loc = [r["path"] for r in rows if is_loc(r)]
    fonts = [r["path"] for r in rows if r["ext"] in FONT_EXTS]
    arch = [r for r in rows if r["ext"] in ARCHIVE_EXTS]
    exes = [r["path"] for r in rows if r["ext"] in EXEC_EXTS and "/" not in r["path"]]
    summary = {
        "game_dir": str(root), "total_files": len(rows), "total_mb": round(sum(r["size"] for r in rows) / 1048576, 1),
        "top_extensions": [f"{e or '(none)'}:{c}" for e, c in exts.most_common(15)],
        "engine_hints": detect_engines(names, exts, dirs),
        "localization_candidates": {"count": len(loc), "top_dirs": by_dir(loc), "sample": loc[:12]},
        "fonts": {"count": len(fonts), "sample": fonts[:8]},
        "archives": {"count": len(arch), "biggest": [{"path": r["path"], "mb": round(r["size"] / 1048576, 1)}
                                                      for r in sorted(arch, key=lambda r: -r["size"])[:8]]},
        "root_executables": exes[:8],
        "unreadable_count": len(errors),
        "note": "Hints are leads only; verify before concluding. Full list is in file_inventory.csv (do not read it whole; grep it).",
    }
    (out / "INVENTORY_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Inventoried {len(rows)} files ({summary['total_mb']} MB). Reports in {out}")
    for h in summary["engine_hints"][:5]:
        print(f"  hint: {h['engine_candidate']} [{h['script_confidence']}] <- {'; '.join(h['evidence'])}")
    if errors:
        print(f"  {len(errors)} unreadable path(s) listed in summary")


if __name__ == "__main__":
    main()
