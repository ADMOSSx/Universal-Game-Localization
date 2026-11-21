#!/usr/bin/env python3
"""Collapse exact duplicate localization entries with matching semantic context.

The generated map is bound to the exact input file SHA-256. Use
expand_translations.py after merging translations to restore every original ID.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys


UNKNOWN_CONTEXT = {"", "unknown", "other", "n/a", "na", "none", "null"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_key(entry):
    context = str(entry.get("context") or "").strip().casefold()
    speaker = str(entry.get("speaker") or "").strip().casefold()
    raw_meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    # Only layout limits (max_chars, max_bytes, ...) decide whether two strings may share a translation.
    # Other metadata (e.g. the per-entry key an extractor stores) is identity, not meaning.
    metadata = {k: v for k, v in raw_meta.items() if str(k).startswith("max_")}
    # Unknown context is not enough evidence to reuse a translation across files.
    source_scope = (
        str(entry.get("source_file") or f"<missing-source-file:{entry.get('id', '')}>")
        if context in UNKNOWN_CONTEXT else ""
    )
    return canonical({
        "original": entry.get("original", ""),
        "context": context,
        "speaker": speaker,
        "tags": entry.get("tags", []),
        "formatting": entry.get("formatting", []),
        "placeholders": entry.get("placeholders", []),
        "notes": entry.get("notes", ""),
        "metadata": metadata,
        "source_scope": source_scope,
    })


def write_json(path: Path, data, force: bool):
    if path.is_symlink():
        raise SystemExit(f"Refusing symbolic-link output: {path}")
    if path.exists() and not force:
        raise SystemExit(f"Output already exists: {path}. Choose another path or use --force.")
    if path.exists() and not path.is_file():
        raise SystemExit(f"Refusing to replace non-regular output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    if temp.exists() or temp.is_symlink():
        raise SystemExit(f"Temporary output already exists: {temp}")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="normalized source JSON")
    parser.add_argument("--out", default="strings_unique.json", help="deduplicated normalized JSON")
    parser.add_argument("--map", dest="map_path", default="DEDUPE_MAP.json", help="ID expansion map")
    parser.add_argument("--force", action="store_true", help="replace the two explicitly named output files")
    args = parser.parse_args()

    source_path = Path(args.input)
    out_path, map_path = Path(args.out), Path(args.map_path)
    if not source_path.is_file() or source_path.is_symlink():
        raise SystemExit("Input must be a regular file, not a symlink.")
    source_resolved = source_path.resolve()
    if out_path.resolve() == source_resolved or map_path.resolve() == source_resolved:
        raise SystemExit("Output paths must not overwrite the normalized source.")
    if out_path.resolve() == map_path.resolve():
        raise SystemExit("--out and --map must be different paths.")

    source_hash = sha256(source_path)
    try:
        data = json.loads(source_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read normalized JSON: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise SystemExit("Input must be an object containing an 'entries' list.")
    entries = data["entries"]
    if not all(isinstance(item, dict) for item in entries):
        raise SystemExit("Every entry must be an object.")
    if any(not isinstance(item.get("original"), str) for item in entries):
        raise SystemExit("Every entry must contain a string 'original'.")
    if any("metadata" in item and not isinstance(item.get("metadata"), dict) for item in entries):
        raise SystemExit("Entry metadata must be a JSON object when present.")

    ids = [item.get("id") for item in entries]
    if any(not isinstance(value, str) or not value for value in ids):
        raise SystemExit("Every entry needs a non-empty string ID.")
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate source IDs; deduplication stopped.")

    groups_by_key = {}
    ordered_keys = []
    for entry in entries:
        # Existing translations are never collapsed or overwritten.
        if str(entry.get("translation") or "").strip():
            continue
        key = semantic_key(entry)
        if key not in groups_by_key:
            groups_by_key[key] = []
            ordered_keys.append(key)
        groups_by_key[key].append(entry)

    representative_ids = set()
    groups = []
    aliases = {}
    for key in ordered_keys:
        members = groups_by_key[key]
        representative = members[0]
        representative_ids.add(representative["id"])
        if len(members) > 1:
            member_ids = [item["id"] for item in members]
            rep_id = representative["id"]
            groups.append({
                "representative_id": rep_id,
                "member_ids": member_ids,
                "count": len(member_ids),
                "key_sha256": hashlib.sha256(key.encode("utf-8")).hexdigest(),
            })
            for alias_id in member_ids[1:]:
                aliases[alias_id] = rep_id

    # Keep original order and preserve already-translated entries independently.
    unique_entries = [
        entry for entry in entries
        if entry["id"] in representative_ids or str(entry.get("translation") or "").strip()
    ]
    if sha256(source_path) != source_hash:
        raise SystemExit("Normalized source changed during deduplication; no outputs were written.")

    unique_data = dict(data)
    unique_data["entries"] = unique_entries
    unique_data["deduplication"] = {
        "enabled": True,
        "source_entries": len(entries),
        "unique_entries": len(unique_entries),
        "collapsed_entries": len(entries) - len(unique_entries),
    }
    mapping = {
        "schema_version": "1.0",
        "source_sha256": source_hash,
        "source_entries": len(entries),
        "unique_entries": len(unique_entries),
        "groups": groups,
        "aliases": aliases,
    }

    # Preflight both destinations so a known conflict cannot leave a one-file result.
    for destination in (out_path, map_path):
        if destination.is_symlink():
            raise SystemExit(f"Refusing symbolic-link output: {destination}")
        if destination.exists() and not args.force:
            raise SystemExit(f"Output already exists: {destination}. Choose another path or use --force.")
        if destination.exists() and not destination.is_file():
            raise SystemExit(f"Refusing to replace non-regular output: {destination}")
        temp_path = destination.with_name(destination.name + ".tmp")
        if temp_path.exists() or temp_path.is_symlink():
            raise SystemExit(f"Temporary output already exists: {temp_path}")

    write_json(out_path, unique_data, args.force)
    try:
        write_json(map_path, mapping, args.force)
    except Exception:
        # Avoid leaving a half-written pair when the map cannot be created.
        if out_path.exists() and args.force is False:
            out_path.unlink()
        raise

    saved = len(entries) - len(unique_entries)
    print(f"Source entries: {len(entries)}")
    print(f"Unique entries: {len(unique_entries)}")
    print(f"Duplicate entries collapsed: {saved}")
    print(f"Translation groups: {len(groups)}")
    if saved:
        print(f"Estimated translation workload reduction: {saved / max(len(entries), 1):.1%} fewer entries.")
    print(f"Unique JSON: {out_path.resolve()}")
    print(f"Expansion map: {map_path.resolve()}")


if __name__ == "__main__":
    main()
