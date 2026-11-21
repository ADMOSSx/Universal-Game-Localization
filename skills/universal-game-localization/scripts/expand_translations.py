#!/usr/bin/env python3
"""Restore deduplicated translations to every original entry ID safely."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_entries(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read {path}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise SystemExit(f"{path}: expected an object containing an 'entries' list.")
    if not all(isinstance(item, dict) for item in data["entries"]):
        raise SystemExit(f"{path}: every entry must be an object.")
    return data


UNKNOWN_CONTEXT = {"", "unknown", "other", "n/a", "na", "none", "null"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_key(entry):
    context = str(entry.get("context") or "").strip().casefold()
    speaker = str(entry.get("speaker") or "").strip().casefold()
    raw_meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    # Only layout limits (max_chars, max_bytes, ...) decide whether two strings may share a translation.
    # Other metadata (e.g. the per-entry key an extractor stores) is identity, not meaning.
    metadata = {k: v for k, v in raw_meta.items() if str(k).startswith("max_")}
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
    parser.add_argument("source", help="original normalized strings.json")
    parser.add_argument("translated_unique", help="merged translations for strings_unique.json")
    parser.add_argument("--map", dest="map_path", required=True, help="DEDUPE_MAP.json from deduplicate_strings.py")
    parser.add_argument("--out", default="merged_translations.json")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source_path, translated_path, map_path, out_path = (
        Path(args.source), Path(args.translated_unique), Path(args.map_path), Path(args.out)
    )
    if any(p.is_symlink() or not p.is_file() for p in (source_path, translated_path, map_path)):
        raise SystemExit("Source, translated input and map must be regular files (not symlinks).")
    if out_path.resolve() in {source_path.resolve(), translated_path.resolve(), map_path.resolve()}:
        raise SystemExit("Output must not overwrite an input file.")

    source_data = load_entries(source_path)
    translated_data = load_entries(translated_path)
    try:
        mapping = json.loads(map_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read deduplication map: {exc}")
    if not isinstance(mapping, dict) or not isinstance(mapping.get("groups"), list):
        raise SystemExit("Invalid deduplication map.")

    actual_source_hash = sha256(source_path)
    if mapping.get("source_sha256") != actual_source_hash:
        raise SystemExit("Source SHA-256 does not match the deduplication map; refusing to expand stale results.")

    source_entries = source_data["entries"]
    source_index = {}
    for item in source_entries:
        if not isinstance(item.get("original"), str):
            raise SystemExit("Source contains an entry with a non-string original.")
        if "metadata" in item and not isinstance(item.get("metadata"), dict):
            raise SystemExit("Source entry metadata must be a JSON object when present.")
        eid = item.get("id")
        if not isinstance(eid, str) or not eid:
            raise SystemExit("Source contains an entry without a valid ID.")
        if eid in source_index:
            raise SystemExit(f"Duplicate source ID: {eid}")
        source_index[eid] = item

    unique_index = {}
    for item in translated_data["entries"]:
        eid = item.get("id")
        if not isinstance(eid, str) or not eid:
            raise SystemExit("Translated unique data contains an entry without a valid ID.")
        if eid in unique_index:
            raise SystemExit(f"Duplicate translated ID: {eid}")
        if eid not in source_index:
            raise SystemExit(f"Unknown translated ID: {eid}")
        if item.get("original") != source_index[eid].get("original"):
            raise SystemExit(f"Original text changed for representative {eid}; refusing to expand.")
        unique_index[eid] = item

    aliases = mapping.get("aliases", {})
    if not isinstance(aliases, dict):
        raise SystemExit("Invalid aliases map.")
    expected_representatives = set(source_index) - set(aliases)
    if set(unique_index) != expected_representatives:
        missing = sorted(expected_representatives - set(unique_index))
        unexpected = sorted(set(unique_index) - expected_representatives)
        raise SystemExit(
            f"Unique translation IDs do not match the map (missing={missing[:10]}, unexpected={unexpected[:10]})."
        )

    alias_members_by_rep = {}
    seen_aliases = set()
    seen_representatives = set()
    for group in mapping["groups"]:
        if not isinstance(group, dict):
            raise SystemExit("Malformed deduplication group.")
        rep = group.get("representative_id")
        members = group.get("member_ids")
        expected_key_hash = group.get("key_sha256")
        if (not isinstance(rep, str) or not isinstance(members, list) or len(members) < 2
                or members[0] != rep or len(members) != len(set(members))):
            raise SystemExit("Malformed deduplication group members.")
        if rep in seen_representatives or rep not in source_index:
            raise SystemExit(f"Duplicate or unknown representative ID: {rep!r}")
        seen_representatives.add(rep)
        if any(member not in source_index for member in members):
            raise SystemExit(f"Deduplication group {rep!r} contains an unknown source ID.")
        for member_id in members:
            fingerprint = hashlib.sha256(semantic_key(source_index[member_id]).encode("utf-8")).hexdigest()
            if fingerprint != expected_key_hash:
                raise SystemExit(f"Duplicate group {rep!r} contains entries with mismatched context or metadata.")
        for alias_id in members[1:]:
            if alias_id in seen_aliases or aliases.get(alias_id) != rep:
                raise SystemExit(f"Deduplication alias mapping is inconsistent for {rep!r}.")
            seen_aliases.add(alias_id)
        alias_members_by_rep[rep] = members[1:]
    if seen_aliases != set(aliases):
        raise SystemExit("Deduplication map contains aliases not represented by a group.")

    result = dict(source_data)
    result_entries = [dict(entry) for entry in source_entries]
    result_index = {entry["id"]: entry for entry in result_entries}
    applied = 0
    reused = 0
    needs_review = 0

    for rep_id, returned in unique_index.items():
        translation = returned.get("translation", "")
        if not isinstance(translation, str):
            raise SystemExit(f"Translation for {rep_id!r} must be a string.")
        if not translation.strip():
            continue
        target = result_index[rep_id]
        target["translation"] = translation
        target["status"] = "needs_review" if returned.get("status") == "needs_review" else "translated"
        if returned.get("notes"):
            target["notes"] = returned["notes"]
        applied += 1
        if target["status"] == "needs_review":
            needs_review += 1

        for alias_id in alias_members_by_rep.get(rep_id, []):
            alias = result_index[alias_id]
            if str(alias.get("translation") or "").strip():
                continue
            alias["translation"] = translation
            alias["status"] = target["status"]
            if returned.get("notes"):
                alias["notes"] = returned["notes"]
            reused += 1

    if sha256(source_path) != actual_source_hash:
        raise SystemExit("Original normalized source changed during expansion; no output was written.")
    result["entries"] = result_entries
    write_json(out_path, result, args.force)
    print(f"Original entries restored: {len(result_entries)}")
    print(f"Unique translations applied: {applied}")
    print(f"Duplicate entries filled from reused translations: {reused}")
    print(f"Entries marked needs_review: {needs_review}")
    print(f"Expanded output: {out_path.resolve()}")


if __name__ == "__main__":
    main()
