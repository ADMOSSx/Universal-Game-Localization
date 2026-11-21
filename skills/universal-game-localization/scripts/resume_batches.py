#!/usr/bin/env python3
"""Prepare only untranslated entries from existing batches without changing their IDs."""
from pathlib import Path
import argparse
import json
import re
import sys

BATCH_RE = re.compile(r"batch_\d{4}\.json\Z")
FENCE_RE = re.compile(r"^\s*\x60{3}[a-zA-Z0-9_-]*\s*\n(.*?)\n\s*\x60{3}\s*$", re.DOTALL)


def load_json(path):
    raw = path.read_text(encoding="utf-8-sig")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as first:
        match = FENCE_RE.match(raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        raise SystemExit(f"Invalid JSON in {path}: {first}")


def entries_of(data, path):
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("entries"), list):
        return data["entries"]
    raise SystemExit(f"{path}: expected an object with an entries list or a list of entries.")


def has_symlink_component(path):
    absolute = Path(path).absolute()
    return any(part.is_symlink() for part in (absolute, *absolute.parents)
               if part.exists() or part.is_symlink())


def is_inside(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batches", help="original translation_batches directory")
    parser.add_argument("returned", nargs="+", help="one or more directories with returned JSON batches (later rounds override earlier)")
    parser.add_argument("--out", default="pending_batches", help="folder for only the remaining entries")
    parser.add_argument("--force", action="store_true", help="replace only generated batch_NNNN.json files and manifest")
    args = parser.parse_args()

    batches_arg, out_arg = Path(args.batches), Path(args.out)
    returned_args = [Path(x) for x in args.returned]
    if any(path.is_symlink() for path in (batches_arg, out_arg, *returned_args)):
        raise SystemExit("Input and output directories must not be symbolic links.")
    if has_symlink_component(out_arg):
        raise SystemExit("Output path contains a symbolic-link component.")
    batches, out = batches_arg.resolve(), out_arg.resolve()
    returned_dirs = [x.resolve() for x in returned_args]
    if not batches.is_dir() or not all(x.is_dir() for x in returned_dirs):
        raise SystemExit("Both batches and returned must be existing directories.")
    if out == batches or is_inside(out, batches) or any(out == x or is_inside(out, x) for x in returned_dirs):
        raise SystemExit("Output must be separate from both input directories.")

    source_files = sorted(path for path in batches.iterdir() if BATCH_RE.fullmatch(path.name))
    if any(path.is_symlink() or not path.is_file() for path in source_files):
        raise SystemExit("Source batch paths must be regular files, not symbolic links.")
    if not source_files:
        raise SystemExit(f"No batch_NNNN.json files found in {batches}")

    completed, seen_returned, seen_by_round = set(), set(), {}
    returned_files = [(n, p) for n, rdir in enumerate(returned_dirs) for p in sorted(rdir.glob("*.json"))]
    for round_no, path in returned_files:
        if path.name in {"BATCH_MANIFEST.json", "RESUME_MANIFEST.json"}:
            continue
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"Returned path is not a regular file: {path}")
        data = load_json(path)
        for entry in entries_of(data, path):
            if not isinstance(entry, dict):
                raise SystemExit(f"{path}: each returned entry must be a JSON object.")
            eid = entry.get("id")
            if not isinstance(eid, str) or not eid:
                raise SystemExit(f"{path}: returned entry is missing a non-empty string ID.")
            if eid in seen_by_round.setdefault(round_no, set()):
                raise SystemExit(f"Duplicate returned ID inside one directory: {eid}")
            seen_by_round[round_no].add(eid)
            seen_returned.add(eid)
            translation = entry.get("translation", "")
            if not isinstance(translation, str):
                raise SystemExit(f"{path}: translation for {eid!r} must be a string.")
            if translation.strip():      # the latest non-blank answer decides
                if entry.get("status") != "needs_review":
                    completed.add(eid)
                else:
                    completed.discard(eid)

    pending_batches, pending_ids, total_entries = [], [], 0
    original_ids = set()
    for path in source_files:
        data = load_json(path)
        entries = entries_of(data, path)
        if not isinstance(data, dict):
            raise SystemExit(f"{path}: batch must be a JSON object with metadata.")
        if not all(isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"]
                   for entry in entries):
            raise SystemExit(f"{path}: all source batch entries need non-empty string IDs.")
        keep = []
        for entry in entries:
            eid = entry["id"]
            if eid in original_ids:
                raise SystemExit(f"Duplicate source ID across batches: {eid}")
            original_ids.add(eid)
            total_entries += 1
            if eid not in completed:
                keep.append(entry)
                pending_ids.append(eid)
        if keep:
            payload = dict(data)
            payload["entries"] = keep
            pending_batches.append((path.name, payload, len(keep)))

    unknown = sorted(seen_returned - original_ids)
    if unknown:
        raise SystemExit(f"Returned data contains {len(unknown)} ID(s) not present in source batches: {unknown[:10]}")

    manifest_path = out / "RESUME_MANIFEST.json"
    if out.exists():
        if not out.is_dir():
            raise SystemExit("Output exists and is not a directory.")
        existing = [item for item in out.iterdir()
                    if BATCH_RE.fullmatch(item.name) or item.name == "RESUME_MANIFEST.json"]
        unexpected = [item.name for item in out.iterdir() if item not in existing]
        if unexpected:
            raise SystemExit(f"Output contains unrelated files; refusing to modify it: {unexpected[:10]}")
        if existing and not args.force:
            raise SystemExit("Resume output already contains generated files; use --force to replace those files.")
        if any(item.is_symlink() or not item.is_file() for item in existing):
            raise SystemExit("Refusing to replace non-regular resume output files.")
    out.mkdir(parents=True, exist_ok=True)

    if args.force:
        for item in out.iterdir():
            if BATCH_RE.fullmatch(item.name) or item.name == "RESUME_MANIFEST.json":
                item.unlink()

    for name, payload, _ in pending_batches:
        destination = out / name
        if destination.exists():
            raise SystemExit(f"Refusing to overwrite {destination}")
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "source_batch_files": len(source_files),
        "source_entries": total_entries,
        "completed_entries": len(completed),
        "pending_entries": len(pending_ids),
        "pending_batches": [{"file": name, "entries": count} for name, _, count in pending_batches],
        "pending_ids": pending_ids,
        "note": "Original entry IDs and batch filenames are preserved. Non-empty needs_review entries remain pending.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Resume prepared: {len(pending_ids)} pending entries in {len(pending_batches)} batch file(s).")
    print(f"Completed: {len(completed)} / {total_entries}. Output: {out}")
    if not pending_ids:
        print("All source entries are complete; no translation batches need to be uploaded.")


if __name__ == "__main__":
    main()
