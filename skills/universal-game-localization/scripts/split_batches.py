#!/usr/bin/env python3
"""Split normalized strings.json into translation batches (stable IDs, atomic entries).

Features: size limit by entry count and optionally by characters, optional grouping
(keep entries of the same source_file/context together), manifest with SHA-256 hashes.
Never overwrites existing batches unless --force is given.
"""
from pathlib import Path
import argparse, hashlib, json, re, sys


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_units(entries, group_by):
    """Return a list of units; each unit is a list of entries that should stay together."""
    if not group_by:
        return [[e] for e in entries]
    groups, order = {}, []
    for e in entries:
        key = str(e.get(group_by, ""))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(e)
    return [groups[k] for k in order]


def pack(units, size, max_chars):
    batches, cur, cur_chars = [], [], 0
    for unit in units:
        # A unit bigger than one batch is cut into pieces of at most `size` entries.
        pieces = [unit[i:i + size] for i in range(0, len(unit), size)] if len(unit) > size else [unit]
        for piece in pieces:
            chars = sum(len(str(e.get("original", ""))) for e in piece)
            too_many = len(cur) + len(piece) > size
            too_long = max_chars and cur and cur_chars + chars > max_chars
            if cur and (too_many or too_long):
                batches.append(cur)
                cur, cur_chars = [], 0
            cur.extend(piece)
            cur_chars += chars
    if cur:
        batches.append(cur)
    return batches


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="normalized strings JSON with an 'entries' list")
    p.add_argument("--out", default="translation_batches")
    p.add_argument("--size", type=int, default=100, help="max entries per batch (default 100)")
    p.add_argument("--max-chars", type=int, default=0,
                   help="optional soft cap on total original characters per batch (0 = off)")
    p.add_argument("--group-by", default="", help="entry field to keep together, e.g. source_file or context")
    p.add_argument("--force", action="store_true", help="overwrite existing batch files in --out")
    args = p.parse_args()

    if args.size < 1:
        raise SystemExit("--size must be at least 1")
    src = Path(args.input)
    data = json.loads(src.read_text(encoding="utf-8-sig"))
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise SystemExit("Input must be a JSON object containing an 'entries' list.")
    ids = [e.get("id") for e in entries]
    if any(i in (None, "") for i in ids):
        raise SystemExit("Every entry needs a non-empty 'id'.")
    if len(set(ids)) != len(ids):
        raise SystemExit("Duplicate IDs in input; fix the normalized file before batching.")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    existing = [f for f in out.glob("*.json") if re.fullmatch(r"batch_\d{4}\.json", f.name)]
    if existing and not args.force:
        raise SystemExit(f"{out} already contains {len(existing)} batch file(s). Use --force or another --out.")
    for old in existing:
        old.unlink()

    batches = pack(build_units(entries, args.group_by), args.size, args.max_chars)
    total = len(batches)
    manifest = {
        "input": str(src), "input_sha256": sha256(src),
        "schema_version": data.get("schema_version", "unknown"),
        "total_entries": len(entries), "batch_size": args.size,
        "max_chars": args.max_chars, "group_by": args.group_by or None,
        "total_batches": total, "batches": [],
    }
    base = {k: v for k, v in data.items() if k != "entries"}
    for n, batch_entries in enumerate(batches, 1):
        payload = dict(base)
        payload["batch"] = {"number": n, "total": total}
        payload["entries"] = batch_entries
        name = f"batch_{n:04d}.json"
        path = out / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["batches"].append({
            "file": name, "count": len(batch_entries),
            "chars": sum(len(str(e.get("original", ""))) for e in batch_entries),
            "first_id": batch_entries[0]["id"], "last_id": batch_entries[-1]["id"],
            "sha256": sha256(path),
        })
    (out / "BATCH_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    covered = sum(b["count"] for b in manifest["batches"])
    if covered != len(entries):
        raise SystemExit(f"INTERNAL ERROR: batches cover {covered} of {len(entries)} entries.")
    print(f"Created {total} batch(es) covering {covered} entries in {out.resolve()}")


if __name__ == "__main__":
    main()
