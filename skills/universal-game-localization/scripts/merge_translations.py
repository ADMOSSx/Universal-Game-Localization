#!/usr/bin/env python3
"""Merge returned translated batch JSON files into the normalized source by stable ID.

Only `translation`, `notes` and (for flagged entries) `status` are taken from returned files.
Originals, IDs and every other field always come from the source file.
Tolerates files wrapped in ```json fences (common in AI replies) and bare lists of entries.
"""
from pathlib import Path
import argparse, json, re, sys

FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


def load_lenient(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    try:
        return json.loads(text)
    except json.JSONDecodeError as first:
        m = FENCE_RE.match(text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        raise SystemExit(f"Invalid JSON in {path}: {first}")


def entries_of(obj, path):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict) and isinstance(obj.get("entries"), list):
        return obj["entries"]
    raise SystemExit(f"{path}: expected an object with an 'entries' list (or a list of entries).")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", help="Normalized source JSON")
    p.add_argument("translated_dir", help="Directory with returned translated batch JSON files")
    p.add_argument("--out", default="merged_translations.json")
    p.add_argument("--allow-unknown-ids", action="store_true", help="ignore returned IDs not in the source")
    p.add_argument("--allow-changed-original", action="store_true",
                   help="continue even if a returned 'original' differs from the source (source is kept)")
    p.add_argument("--require-complete", action="store_true", help="fail if any source ID has no translation")
    args = p.parse_args()

    source = json.loads(Path(args.source).read_text(encoding="utf-8-sig"))
    src_entries = entries_of(source, args.source)
    index = {}
    for e in src_entries:
        eid = e.get("id")
        if eid in (None, ""):
            raise SystemExit("Source entry without an ID.")
        if eid in index:
            raise SystemExit(f"Duplicate source ID: {eid}")
        index[eid] = e

    files = [f for f in sorted(Path(args.translated_dir).glob("*.json"))
             if f.name not in {"BATCH_MANIFEST.json", "RESUME_MANIFEST.json"}]
    if not files:
        raise SystemExit(f"No JSON files found in {args.translated_dir}")
    incoming, duplicates, unknown, blank, changed = {}, [], [], [], []
    for f in files:
        for e in entries_of(load_lenient(f), f):
            if not isinstance(e, dict):
                raise SystemExit(f"{f}: each returned entry must be a JSON object.")
            eid = e.get("id")
            if not isinstance(eid, str) or not eid:
                raise SystemExit(f"{f}: every returned entry needs a non-empty string ID.")
            if eid in incoming:
                duplicates.append(eid)
            incoming[eid] = e
            if eid not in index:
                unknown.append(eid)
                continue
            if "original" in e and e["original"] != index[eid].get("original"):
                changed.append(eid)
            translation = e.get("translation", "")
            if not isinstance(translation, str):
                raise SystemExit(f"{f}: translation for {eid!r} must be a string.")
            if not translation.strip():
                blank.append(eid)

    if duplicates:
        raise SystemExit(f"Duplicate translated IDs (merge stopped): {duplicates[:20]}")
    if unknown and not args.allow_unknown_ids:
        raise SystemExit(f"Unknown IDs (merge stopped): {unknown[:20]}")
    if changed and not args.allow_changed_original:
        raise SystemExit(f"Returned 'original' differs from source for {len(changed)} entries "
                         f"(merge stopped): {changed[:20]}. Re-check them or use --allow-changed-original.")

    merged = dict(source)
    merged["entries"] = [dict(e) for e in src_entries]
    taken = 0
    for e in merged["entries"]:
        r = incoming.get(e["id"])
        if r is None or not str(r.get("translation", "")).strip():
            continue
        e["translation"] = r["translation"]
        e["status"] = "needs_review" if r.get("status") == "needs_review" else "translated"
        if r.get("notes"):
            e["notes"] = r["notes"]
        taken += 1

    not_returned = [e["id"] for e in merged["entries"] if e["id"] not in incoming]
    still_empty = [e["id"] for e in merged["entries"] if not str(e.get("translation", "")).strip()]
    if args.require_complete and still_empty:
        raise SystemExit(f"{len(still_empty)} entries still have no translation: {still_empty[:20]}")

    out = Path(args.out)
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"source_entries": len(src_entries), "returned_entries": len(incoming),
              "translations_applied": taken, "unknown_ids": unknown, "changed_originals": changed,
              "blank_returned": blank, "never_returned": not_returned, "still_empty": still_empty}
    out.with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Merged output: {out.resolve()}")
    print(f"Source entries: {len(src_entries)}; returned: {len(incoming)}; applied: {taken}; "
          f"still empty: {len(still_empty)}; never returned: {len(not_returned)}")
    if blank:
        print(f"Returned with blank translation: {len(blank)}")
    if unknown:
        print(f"Unknown IDs ignored: {len(unknown)}")


if __name__ == "__main__":
    main()
