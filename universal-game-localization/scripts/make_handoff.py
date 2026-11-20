#!/usr/bin/env python3
"""Build HANDOFF_PACKAGE/ (+ ZIP with checksums) from a localization workspace (step 10 helper).

Copies only localization material: reports, translator docs, normalized strings, batches and
helper scripts. Excludes game binaries/archives, huge files and anything that looks like a secret.
Verifies the ZIP afterwards. Does not modify the workspace content it copies from.
"""
from pathlib import Path
import argparse, fnmatch, hashlib, json, shutil, sys, zipfile

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DIRS = ["reports", "translator", "normalized", "translation_batches"]
BLOCK_EXTS = {".exe", ".dll", ".so", ".dylib", ".msi", ".pak", ".ucas", ".utoc", ".upk", ".vpk", ".pck", ".rpa", ".bsa",
              ".ba2", ".bundle", ".assets", ".arc", ".bin", ".dat", ".zip", ".7z", ".rar", ".iso", ".bik", ".mp4", ".wav", ".ogg"}
SECRET_GLOBS = [".env*", "*.pem", "*.key", "id_rsa*", "credentials*", "*.pfx", "*token*", "*secret*"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def blocked(path: Path, max_bytes: int):
    if path.suffix.lower() in BLOCK_EXTS:
        return "blocked extension"
    if any(fnmatch.fnmatch(path.name.lower(), g) for g in SECRET_GLOBS):
        return "looks like a secret"
    if path.stat().st_size > max_bytes:
        return "larger than --max-file-mb"
    return ""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("workspace", help="localization workspace folder")
    p.add_argument("--out", default="", help="output folder (default: <workspace>/HANDOFF_PACKAGE)")
    p.add_argument("--include-source", action="store_true", help="also include source/ raw extraction snapshots")
    p.add_argument("--max-file-mb", type=float, default=25.0)
    p.add_argument("--force", action="store_true", help="replace an existing HANDOFF_PACKAGE")
    args = p.parse_args()

    ws = Path(args.workspace).resolve()
    out = Path(args.out).resolve() if args.out else ws / "HANDOFF_PACKAGE"
    if not ws.is_dir():
        raise SystemExit(f"Workspace not found: {ws}")
    if out.exists():
        if not args.force:
            raise SystemExit(f"{out} exists. Use --force to rebuild it (only this package folder is replaced).")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    max_bytes = int(args.max_file_mb * 1024 * 1024)

    dirs = DEFAULT_DIRS + (["source"] if args.include_source else [])
    copied, skipped = [], []
    for d in dirs:
        base = ws / d
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(ws)
            why = blocked(f, max_bytes)
            if why:
                skipped.append({"file": rel.as_posix(), "reason": why})
                continue
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            copied.append(rel.as_posix())

    # helper scripts, handoff rules and README
    (out / "scripts").mkdir()
    for name in ("split_batches.py", "merge_translations.py", "validate_translations.py"):
        shutil.copy2(SKILL_DIR / "scripts" / name, out / "scripts" / name)
        copied.append(f"scripts/{name}")
    master = ws / "translator" / "MASTER_TRANSLATION_PROMPT.md"
    if not master.exists():
        master = SKILL_DIR / "templates" / "MASTER_TRANSLATION_PROMPT.md"
    handoff_rules = (SKILL_DIR / "references" / "claude-handoff-template.md").read_text(encoding="utf-8")
    (out / "MASTER_INSTRUCTIONS.md").write_text(master.read_text(encoding="utf-8") + "\n\n---\n\n" + handoff_rules, encoding="utf-8")
    copied.append("MASTER_INSTRUCTIONS.md")
    readme_src = ws / "README_FIRST.md"
    if not readme_src.exists():
        readme_src = SKILL_DIR / "templates" / "README_FIRST_TEMPLATE.md"
    shutil.copy2(readme_src, out / "README_FIRST.md")
    copied.append("README_FIRST.md")

    manifest = {"files": [{"file": c, "size": (out / c).stat().st_size, "sha256": sha256(out / c)} for c in sorted(set(copied))],
                "skipped": skipped}
    (out / "HANDOFF_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "CHECKSUMS.sha256").write_text("".join(f"{m['sha256']}  {m['file']}\n" for m in manifest["files"]), encoding="utf-8")

    zip_path = out.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, Path(out.name) / f.relative_to(out))
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit(f"ZIP integrity check failed at {bad}")
        for m in manifest["files"]:
            if hashlib.sha256(z.read(f"{out.name}/{m['file']}")).hexdigest() != m["sha256"]:
                raise SystemExit(f"Checksum mismatch inside ZIP: {m['file']}")
    size_mb = zip_path.stat().st_size / 1048576
    print(f"Package: {out}\nZIP: {zip_path} ({size_mb:.1f} MB) - integrity verified")
    print(f"Files: {len(manifest['files'])}; skipped: {len(skipped)}")
    for s in skipped[:10]:
        print(f"  skipped {s['file']} ({s['reason']})")
    print("Upload order: README_FIRST.md, MASTER_INSTRUCTIONS.md, translator/GUIDE.md, then batch_0001.json, batch_0002.json ...")
    print("Check the AI service's current upload limits; upload batches one at a time if the ZIP is too big.")


if __name__ == "__main__":
    main()
