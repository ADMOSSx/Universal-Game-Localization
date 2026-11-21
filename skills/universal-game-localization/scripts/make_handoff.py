#!/usr/bin/env python3
"""Build a minimal, checksummed localization handoff package."""
from pathlib import Path
import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DIRS = ["reports", "translator", "normalized", "translation_batches"]
BLOCK_EXTS = {".exe", ".dll", ".so", ".dylib", ".msi", ".pak", ".ucas", ".utoc", ".upk", ".vpk", ".pck",
              ".rpa", ".bsa", ".ba2", ".bundle", ".assets", ".arc", ".bin", ".dat", ".zip", ".7z",
              ".rar", ".iso", ".bik", ".mp4", ".wav", ".ogg", ".locres", ".locmeta", ".mo", ".esm", ".esp", ".rgss3a", ".rgss2a", ".rgssad", ".wad"}
SECRET_GLOBS = [".env*", "*.pem", "*.key", "id_rsa*", "credentials*", "*.pfx", "*token*", "*secret*"]
SECRET_CONTENT_RE = re.compile(
    rb"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[\x27\x22]?[A-Za-z0-9_./+=-]{12,}"
)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inside(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def contains_symlink(path):
    p = Path(path).absolute()
    return any(x.is_symlink() for x in (p, *p.parents) if x.exists() or x.is_symlink())


def contains_secret_content(path: Path, chunk_size: int = 1 << 20):
    overlap = b""
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                return False
            data = overlap + chunk
            if SECRET_CONTENT_RE.search(data):
                return True
            overlap = data[-512:]


def blocked(path: Path, max_bytes: int):
    if path.is_symlink():
        return "symbolic link"
    if path.suffix.lower() in BLOCK_EXTS:
        return "blocked extension"
    if any(fnmatch.fnmatch(path.name.lower(), g) for g in SECRET_GLOBS):
        return "looks like a secret"
    try:
        if path.stat().st_size > max_bytes:
            return "larger than --max-file-mb"
        if contains_secret_content(path):
            return "possible embedded credential"
    except OSError as ex:
        return f"unreadable: {ex}"
    return ""


def sanitize_json_paths(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False

    path_keys = {"root", "game_dir", "source_root", "game_path", "source_path",
                 "source_folder", "workspace_path", "project_path", "input", "workspace"}
    def visit(value):
        if isinstance(value, dict):
            for key, item in list(value.items()):
                if key.lower() in path_keys:
                    if isinstance(item, str) and (Path(item).is_absolute() or (len(item) > 2 and item[1:3] == ":\\")):
                        value[key] = "<LOCAL_PATH_REDACTED>"
                    else:
                        visit(item)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def sanitize_project_paths(path):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    lines = text.splitlines()
    sanitized = []
    for line in lines:
        if line.lower().startswith("workspace / source path:"):
            line = "Workspace / source path: <LOCAL_PATH_REDACTED>"
        sanitized.append(line)
    path.write_text("\n".join(sanitized) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return True


def valid_package_marker(data):
    return isinstance(data, dict) and data.get("format") == "ADMOSS_HANDOFF_PACKAGE" and data.get("version") == 1


def verified_package_dir(path):
    marker = path / "ADMOSS_HANDOFF_PACKAGE.json"
    manifest_path = path / "HANDOFF_MANIFEST.json"
    if (not path.is_dir() or path.is_symlink() or marker.is_symlink() or manifest_path.is_symlink()
            or not marker.is_file() or not manifest_path.is_file()):
        return False
    try:
        if not valid_package_marker(json.loads(marker.read_text(encoding="utf-8"))):
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = manifest.get("files", [])
        if not isinstance(items, list):
            return False
        names = {item["file"] for item in items}
        required = {"ADMOSS_HANDOFF_PACKAGE.json", "README_FIRST.md", "MASTER_INSTRUCTIONS.md",
                    "scripts/split_batches.py", "scripts/resume_batches.py",
                    "scripts/merge_translations.py", "scripts/validate_translations.py"}
        if not required.issubset(names):
            return False
        expected = names | {"HANDOFF_MANIFEST.json", "CHECKSUMS.sha256"}
        actual = set()
        for item_path in path.rglob("*"):
            if item_path.is_symlink():
                return False
            if item_path.is_file():
                actual.add(item_path.relative_to(path).as_posix())
        if actual != expected:
            return False
        for item in items:
            rel = Path(item["file"])
            if rel.is_absolute() or ".." in rel.parts or "\\" in item["file"]:
                return False
            target = path / rel
            if contains_symlink(target) or not inside(target, path) or not target.is_file():
                return False
            if sha256(target) != item["sha256"]:
                return False
        return True
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def verified_package_zip(path, package_name):
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip():
                return False
            prefix = package_name + "/"
            marker_name = prefix + "ADMOSS_HANDOFF_PACKAGE.json"
            manifest_name = prefix + "HANDOFF_MANIFEST.json"
            marker = json.loads(archive.read(marker_name).decode("utf-8"))
            manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
            if not valid_package_marker(marker):
                return False
            items = manifest.get("files", [])
            if not isinstance(items, list):
                return False
            names = {item["file"] for item in items}
            required = {"ADMOSS_HANDOFF_PACKAGE.json", "README_FIRST.md", "MASTER_INSTRUCTIONS.md",
                        "scripts/split_batches.py", "scripts/resume_batches.py",
                        "scripts/merge_translations.py", "scripts/validate_translations.py"}
            if not required.issubset(names):
                return False
            expected = {prefix + name for name in names | {"HANDOFF_MANIFEST.json", "CHECKSUMS.sha256"}}
            if set(archive.namelist()) != expected:
                return False
            for item in items:
                rel = Path(item["file"])
                if rel.is_absolute() or ".." in rel.parts or "\\" in item["file"]:
                    return False
                name = prefix + rel.as_posix()
                if hashlib.sha256(archive.read(name)).hexdigest() != item["sha256"]:
                    return False
            return True
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
        return False


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("workspace", help="localization workspace folder")
    p.add_argument("--out", default="", help="output folder (default: <workspace>/HANDOFF_PACKAGE)")
    p.add_argument("--include-source", action="store_true", help="also include source/ raw extraction snapshots")
    p.add_argument("--max-file-mb", type=float, default=25.0)
    p.add_argument("--force", action="store_true", help="replace a previously generated package only")
    args = p.parse_args()

    ws_arg = Path(args.workspace)
    if ws_arg.is_symlink():
        raise SystemExit("Workspace must not be a symbolic link.")
    ws = ws_arg.resolve()
    if not ws.is_dir():
        raise SystemExit(f"Workspace not found: {ws}")
    out_arg = Path(args.out) if args.out else ws / "HANDOFF_PACKAGE"
    if contains_symlink(out_arg):
        raise SystemExit("Output path contains a symbolic link.")
    out = out_arg.resolve()
    if out == ws or inside(ws, out):
        raise SystemExit("Refusing to use the workspace or one of its ancestors as package output.")
    default_out = (ws / "HANDOFF_PACKAGE").resolve()
    if inside(out, ws) and out != default_out:
        raise SystemExit("When output is inside the workspace, only <workspace>/HANDOFF_PACKAGE is allowed.")
    if args.max_file_mb <= 0:
        raise SystemExit("--max-file-mb must be greater than zero.")

    zip_path = out.with_suffix(".zip")
    if out.exists():
        if not args.force:
            raise SystemExit(f"{out} exists. Use --force to replace a verified handoff package.")
        if not verified_package_dir(out):
            raise SystemExit("Refusing to delete an existing directory that is not a verified handoff package.")
    if zip_path.exists() or zip_path.is_symlink():
        if not args.force:
            raise SystemExit(f"{zip_path} exists. Use --force to replace a verified generated ZIP.")
        if zip_path.is_symlink() or not zip_path.is_file() or not verified_package_zip(zip_path, out.name):
            raise SystemExit("Refusing to replace a ZIP that is not a verified ADMOSS handoff package.")

    max_bytes = int(args.max_file_mb * 1024 * 1024)
    dirs = DEFAULT_DIRS + (["source"] if args.include_source else [])
    out.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".handoff-build-", dir=out.parent))
    staged = temp_root / out.name
    staged.mkdir()
    copied, skipped = [], []
    try:
        for dirname in dirs:
            base = ws / dirname
            if not base.is_dir() or base.is_symlink():
                continue
            for dpath, dnames, fnames in os.walk(base, topdown=True, followlinks=False):
                current = Path(dpath)
                dnames[:] = [d for d in dnames if not (current / d).is_symlink()]
                for name in sorted(fnames):
                    source = current / name
                    rel = source.relative_to(ws)
                    if source.is_symlink():
                        skipped.append({"file": rel.as_posix(), "reason": "symbolic link"})
                        continue
                    reason = blocked(source, max_bytes)
                    if reason:
                        skipped.append({"file": rel.as_posix(), "reason": reason})
                        continue
                    dest = staged / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
                    if dest.name in {"files.json", "INVENTORY_SUMMARY.json"} and dest.suffix.lower() == ".json":
                        if not sanitize_json_paths(dest):
                            raise SystemExit(f"Could not safely sanitize local paths in {rel}")
                    if dest.name == "PROJECT.md":
                        if not sanitize_project_paths(dest):
                            raise SystemExit(f"Could not safely sanitize local paths in {rel}")
                    copied.append(rel.as_posix())

        scripts_dir = staged / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        for name in ("split_batches.py", "resume_batches.py", "merge_translations.py", "validate_translations.py"):
            shutil.copy2(SKILL_DIR / "scripts" / name, scripts_dir / name)
            copied.append(f"scripts/{name}")

        master = ws / "translator" / "MASTER_TRANSLATION_PROMPT.md"
        if not master.is_file():
            master = SKILL_DIR / "templates" / "MASTER_TRANSLATION_PROMPT.md"
        rules = (SKILL_DIR / "references" / "claude-handoff-template.md").read_text(encoding="utf-8")
        (staged / "MASTER_INSTRUCTIONS.md").write_text(
            master.read_text(encoding="utf-8") + "\n\n---\n\n" + rules, encoding="utf-8")
        copied.append("MASTER_INSTRUCTIONS.md")

        readme = ws / "README_FIRST.md"
        if not readme.is_file():
            readme = SKILL_DIR / "templates" / "README_FIRST_TEMPLATE.md"
        shutil.copy2(readme, staged / "README_FIRST.md")
        copied.append("README_FIRST.md")

        marker_path = staged / "ADMOSS_HANDOFF_PACKAGE.json"
        marker_path.write_text(json.dumps({"format": "ADMOSS_HANDOFF_PACKAGE", "version": 1}, indent=2), encoding="utf-8")
        copied.append("ADMOSS_HANDOFF_PACKAGE.json")
        manifest_files = [{"file": name, "size": (staged / name).stat().st_size,
                           "sha256": sha256(staged / name)} for name in sorted(set(copied))]
        manifest = {"files": manifest_files, "skipped": skipped,
                    "privacy": "Local absolute game paths are redacted in copied JSON metadata."}
        (staged / "HANDOFF_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (staged / "CHECKSUMS.sha256").write_text(
            "".join(f"{item['sha256']}  {item['file']}\n" for item in manifest_files), encoding="utf-8")

        staged_zip = temp_root / (out.name + ".zip")
        with zipfile.ZipFile(staged_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(staged.rglob("*")):
                if file.is_file() and not file.is_symlink():
                    archive.write(file, Path(out.name) / file.relative_to(staged))
        with zipfile.ZipFile(staged_zip) as archive:
            bad = archive.testzip()
            if bad:
                raise SystemExit(f"ZIP integrity check failed at {bad}")
            for item in manifest_files:
                member = f"{out.name}/{item['file']}"
                if hashlib.sha256(archive.read(member)).hexdigest() != item["sha256"]:
                    raise SystemExit(f"Checksum mismatch inside ZIP: {item['file']}")

        # Replace only a previously verified package directory and regular generated ZIP.
        if out.exists():
            shutil.rmtree(out)
        if zip_path.exists():
            zip_path.unlink()
        os.replace(staged, out)
        os.replace(staged_zip, zip_path)
        print(f"Package: {out}\nZIP: {zip_path} ({zip_path.stat().st_size / 1048576:.1f} MB) - integrity verified")
        print(f"Files: {len(manifest_files)}; skipped: {len(skipped)}")
        for item in skipped[:8]:
            print(f"  skipped {item['file']} ({item['reason']})")
        print("Upload order: README_FIRST.md, MASTER_INSTRUCTIONS.md, translator/GUIDE.md, then batch_0001.json, batch_0002.json ...")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
