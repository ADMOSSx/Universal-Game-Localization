#!/usr/bin/env python3
"""Write translated copies of source text files into a separate patch folder."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _textio as T


def sha(data):
    return hashlib.sha256(data).hexdigest()


def has_symlink_component(path):
    current = Path(path).absolute()
    parts = [current, *current.parents]
    return any(part.is_symlink() for part in parts if part.exists() or part.is_symlink())


def safe_relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError(f"Invalid source-relative path: {value!r}")
    rel = PurePosixPath(value)
    if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
        raise ValueError(f"Unsafe source-relative path: {value!r}")
    if rel.parts and ":" in rel.parts[0]:
        raise ValueError(f"Drive-qualified path is not allowed: {value!r}")
    return rel


def ensure_inside(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("merged", help="merged_translations.json")
    p.add_argument("--files", default="normalized/files.json")
    p.add_argument("--src-root", default="", help="original game folder (default: root stored in files.json)")
    p.add_argument("--out", default="patch")
    p.add_argument("--statuses", default="translated,approved", help="comma list; add needs_review to include flagged ones")
    p.add_argument("--force", action="store_true", help="allow replacing existing regular patch files")
    p.add_argument("--allow-unverified-source", action="store_true",
                   help="allow old files.json metadata that has no source hashes")
    args = p.parse_args()

    try:
        meta = json.loads(Path(args.files).read_text(encoding="utf-8-sig"))
        if not isinstance(meta, dict) or not isinstance(meta.get("files"), dict):
            raise ValueError("files metadata must contain a 'files' object.")
        root_arg = Path(args.src_root or meta["root"])
        if root_arg.is_symlink():
            raise ValueError("Source root must not be a symbolic link.")
        root = root_arg.resolve()
        if not root.is_dir():
            raise ValueError(f"Source root is not a directory: {root}")
        out_arg = Path(args.out)
        if out_arg.is_symlink() or has_symlink_component(out_arg):
            raise ValueError("Patch output path contains a symbolic link.")
        out = out_arg.resolve()
        if out == root or ensure_inside(out, root):
            raise ValueError("Refusing to write the patch inside the original game folder.")
        if out.exists() and not out.is_dir():
            raise ValueError("Patch output exists and is not a directory.")
        manifest_path = out / "PATCH_MANIFEST.json"
        if manifest_path.is_symlink() or (manifest_path.exists() and not manifest_path.is_file()):
            raise ValueError("PATCH_MANIFEST.json exists but is not a regular file.")
        if manifest_path.exists() and not args.force:
            raise ValueError("Patch manifest already exists; use --force to replace this patch.")
        merged_data = json.loads(Path(args.merged).read_text(encoding="utf-8-sig"))
        if not isinstance(merged_data, dict) or not isinstance(merged_data.get("entries"), list):
            raise ValueError("Merged data must be an object containing an entries list.")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as ex:
        raise SystemExit(f"Input validation failed: {ex}")

    allowed = {s.strip() for s in args.statuses.split(",") if s.strip()}
    per_file = {}
    for entry in merged_data["entries"]:
        if not isinstance(entry, dict):
            raise SystemExit("Malformed entry: every entry must be a JSON object.")
        translation = entry.get("translation", "")
        if not isinstance(translation, str):
            raise SystemExit(f"Translation for {entry.get('id')!r} is not a string.")
        if not translation.strip() or entry.get("status") not in allowed:
            continue
        eid = entry.get("id")
        rel_value = entry.get("source_file")
        if not isinstance(eid, str) or not isinstance(rel_value, str):
            raise SystemExit("Every translated entry needs string 'id' and 'source_file' fields.")
        rel = safe_relative_path(rel_value).as_posix()
        prefix = rel + "::"
        if not eid.startswith(prefix):
            raise SystemExit(f"Entry ID does not match source_file: {eid!r}")
        sid = eid[len(prefix):]
        per_file.setdefault(rel, {})[sid] = translation

    # Preflight every file before writing anything: source integrity, adapters and destinations.
    pending, problems = [], []
    for rel, trans in sorted(per_file.items()):
        info = meta["files"].get(rel)
        if not isinstance(info, dict):
            problems.append(f"{rel}: missing/invalid files.json metadata")
            continue
        adapter = info.get("adapter")
        if adapter not in ("ini", "json", "csv", "txt"):
            problems.append(f"{rel}: unsupported or invalid adapter {adapter!r}")
            continue
        src = root.joinpath(*PurePosixPath(rel).parts)
        if has_symlink_component(src) or not ensure_inside(src, root) or not src.is_file():
            problems.append(f"{rel}: missing source or unsafe symbolic-link path")
            continue
        try:
            data = src.read_bytes()
            expected = info.get("source_sha256")
            if not expected and not args.allow_unverified_source:
                problems.append(f"{rel}: source hash missing; re-extract or use --allow-unverified-source for legacy metadata")
                continue
            if expected and sha(data) != expected:
                problems.append(f"{rel}: source file changed since extraction (SHA-256 mismatch)")
                continue
            text, _, _ = T.decode(data)
            new_text, applied, skipped = T.apply(adapter, text, info.get("opts", {}), trans)
            stale = len(trans) - applied - len(skipped)
            if stale:
                problems.append(f"{rel}: {stale} entries no longer match source IDs")
            if skipped:
                problems.extend(f"{rel}: {sid} skipped - {why}" for sid, why in skipped)
            new_bytes, used = T.encode(new_text, info.get("codec", "utf-8"), info.get("bom", ""))
            dest = out.joinpath(*PurePosixPath(rel).parts)
            if not ensure_inside(dest, out):
                problems.append(f"{rel}: destination escapes patch directory")
                continue
            if has_symlink_component(dest):
                problems.append(f"{rel}: destination path contains a symbolic link")
                continue
            if dest.exists() and (dest.is_symlink() or not dest.is_file()):
                problems.append(f"{rel}: existing destination is not a regular file")
                continue
            if dest.exists() and not args.force:
                problems.append(f"{rel}: destination already exists (use --force to replace regular patch files)")
                continue
            pending.append((dest, new_bytes, {"file": rel, "applied": applied, "codec": used,
                                              "original_sha256": sha(data), "patched_sha256": sha(new_bytes)}))
        except (OSError, ValueError, TypeError, KeyError) as ex:
            problems.append(f"{rel}: {type(ex).__name__}: {ex}")

    if problems:
        print("Patch preflight failed; no files were written.")
        for item in problems[:15]:
            print("  ERROR", item)
        if len(problems) > 15:
            print(f"  ... +{len(problems) - 15} more")
        raise SystemExit(2)

    manifest = []
    for dest, data, record in pending:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if has_symlink_component(dest.parent) or not ensure_inside(dest, out):
            raise SystemExit(f"Unsafe destination appeared during patch creation: {dest}")
        temp = dest.with_name(dest.name + ".tmp-localization")
        if temp.exists() or temp.is_symlink():
            raise SystemExit(f"Temporary destination already exists: {temp}")
        try:
            with open(temp, "xb") as f:
                f.write(data)
            if dest.exists() and not args.force:
                raise FileExistsError(dest)
            os.replace(temp, dest)
        finally:
            if temp.exists():
                temp.unlink()
        manifest.append(record)

    out.mkdir(parents=True, exist_ok=True)
    (out / "PATCH_MANIFEST.json").write_text(
        json.dumps({"source_root": "<LOCAL_GAME_PATH>", "files": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"Patched copies: {len(manifest)} file(s), {sum(x['applied'] for x in manifest)} strings -> {out}")
    print("Source files were not modified.")


if __name__ == "__main__":
    main()
