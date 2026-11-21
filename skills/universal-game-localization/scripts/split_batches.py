#!/usr/bin/env python3
"""Split normalized strings into stable, size-aware translation batches."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re
import sys

from _batchio import dump_batch, slim_entry


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def estimated_tokens(text):
    """Conservative heuristic, not an exact model tokenizer count."""
    chars = len(text)
    utf8_bytes = len(text.encode("utf-8"))
    return max(math.ceil(utf8_bytes / 2), math.ceil(chars / 1.5))


def entry_metrics(entry):
    serialized = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
    return {
        "chars": len(str(entry.get("original", ""))),
        "bytes": len(serialized.encode("utf-8")),
        "tokens": estimated_tokens(serialized) + 4,
    }


def build_units(entries, group_by):
    if not group_by:
        return [[entry] for entry in entries]
    groups, order = {}, []
    for entry in entries:
        key = str(entry.get(group_by, ""))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(entry)
    return [groups[key] for key in order]


def pack(units, size, max_chars, max_bytes, token_budget, prompt_overhead, response_reserve_ratio):
    batches, current = [], []
    chars = byte_count = tokens = 0
    oversized = []
    def estimated_total(input_tokens):
        response_tokens = math.ceil(input_tokens * response_reserve_ratio)
        return prompt_overhead + input_tokens + response_tokens
    for unit in units:
        for entry in unit:
            metric = entry_metrics(entry)
            next_chars = chars + metric["chars"]
            next_bytes = byte_count + metric["bytes"]
            next_tokens = tokens + metric["tokens"]
            exceeds = bool(current) and (
                len(current) + 1 > size
                or (max_chars and next_chars > max_chars)
                or (max_bytes and next_bytes > max_bytes)
                or (token_budget and estimated_total(next_tokens) > token_budget)
            )
            if exceeds:
                batches.append(current)
                current = []
                chars = byte_count = tokens = 0
                next_chars, next_bytes, next_tokens = metric["chars"], metric["bytes"], metric["tokens"]
            if not current and (
                (max_chars and metric["chars"] > max_chars)
                or (max_bytes and metric["bytes"] > max_bytes)
                or (token_budget and estimated_total(metric["tokens"]) > token_budget)
            ):
                oversized.append(entry.get("id"))
            current.append(entry)
            chars, byte_count, tokens = next_chars, next_bytes, next_tokens
    if current:
        batches.append(current)
    return batches, oversized


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="normalized strings JSON with an 'entries' list")
    p.add_argument("--out", default="translation_batches")
    p.add_argument("--size", type=int, default=100, help="maximum entries per batch")
    p.add_argument("--max-chars", type=int, default=0, help="soft cap on original characters per batch; 0 disables")
    p.add_argument("--max-bytes", type=int, default=0, help="cap on serialized entry bytes per batch; 0 disables")
    p.add_argument("--token-budget", type=int, default=0,
                   help="estimated total input + prompt + response budget per batch; 0 disables")
    p.add_argument("--prompt-overhead", type=int, default=350,
                   help="reserved prompt/system tokens per batch (default: 350)")
    p.add_argument("--response-reserve-ratio", type=float, default=0.75,
                   help="response reserve as a multiple of estimated input tokens (default: 0.75)")
    p.add_argument("--group-by", default="", help="preserve source order grouped by a field, e.g. source_file")
    p.add_argument("--full", action="store_true",
                   help="send every field to the translator (default: only what it needs: id, original, useful context)")
    p.add_argument("--pretty", action="store_true", help="indented JSON (default: compact, one entry per line)")
    p.add_argument("--force", action="store_true", help="replace only existing batch_NNNN.json files")
    args = p.parse_args()

    if args.size < 1 or any(x < 0 for x in (args.max_chars, args.max_bytes, args.token_budget, args.prompt_overhead)):
        raise SystemExit("Batch limits and prompt overhead must be non-negative; --size must be positive.")
    if not math.isfinite(args.response_reserve_ratio) or args.response_reserve_ratio < 0:
        raise SystemExit("--response-reserve-ratio must be a finite, non-negative number.")
    src = Path(args.input)
    try:
        data = json.loads(src.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as ex:
        raise SystemExit(f"Cannot read normalized JSON: {ex}")
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(data, dict) or not isinstance(entries, list):
        raise SystemExit("Input must be a JSON object containing an 'entries' list.")
    if not all(isinstance(entry, dict) for entry in entries):
        raise SystemExit("Every entry must be a JSON object.")
    ids = [entry.get("id") for entry in entries]
    if any(not isinstance(value, str) or not value for value in ids):
        raise SystemExit("Every entry needs a non-empty string 'id'.")
    if len(set(ids)) != len(ids):
        raise SystemExit("Duplicate IDs in input; fix the normalized file before batching.")

    out = Path(args.out)
    if out.is_symlink():
        raise SystemExit("Refusing to use a symbolic-link output directory.")
    out.mkdir(parents=True, exist_ok=True)
    existing = [f for f in out.glob("batch_*.json") if re.fullmatch(r"batch_\d{4}\.json", f.name)]
    if existing and not args.force:
        raise SystemExit(f"{out} already contains {len(existing)} batch file(s). Use --force or another --out.")
    if args.force:
        for old in existing:
            if old.is_symlink() or not old.is_file():
                raise SystemExit(f"Refusing to replace non-regular batch path: {old}")

    units = build_units(entries, args.group_by)       # group on the full entries, then slim what is sent
    if not args.full:
        units = [[slim_entry(e) for e in unit] for unit in units]
    batches, oversized = pack(units, args.size,
                              args.max_chars, args.max_bytes, args.token_budget,
                              args.prompt_overhead, args.response_reserve_ratio)
    if args.force:
        for old in existing:
            old.unlink()

    total = len(batches)
    manifest = {
        "input": str(src.resolve()), "input_sha256": sha256(src),
        "schema_version": data.get("schema_version", "unknown"),
        "total_entries": len(entries), "batch_size": args.size,
        "max_chars": args.max_chars, "max_bytes": args.max_bytes,
        "token_budget": args.token_budget, "prompt_overhead": args.prompt_overhead,
        "response_reserve_ratio": args.response_reserve_ratio,
        "token_estimator": "max(utf8_bytes/2, characters/1.5) + 4 per entry; conservative heuristic only",
        "group_by": args.group_by or None, "slim": not args.full, "total_batches": total, "oversized_entries": oversized,
        "batches": [],
    }
    base = {key: value for key, value in data.items() if key != "entries"}
    for number, batch_entries in enumerate(batches, 1):
        payload = dict(base)
        payload["batch"] = {"number": number, "total": total}
        payload["entries"] = batch_entries
        name = f"batch_{number:04d}.json"
        path = out / name
        path.write_text(dump_batch(payload, args.pretty), encoding="utf-8")
        metrics = [entry_metrics(entry) for entry in batch_entries]
        input_tokens = sum(item["tokens"] for item in metrics)
        output_reserve = math.ceil(input_tokens * args.response_reserve_ratio)
        total_estimate = args.prompt_overhead + input_tokens + output_reserve
        manifest["batches"].append({
            "file": name, "count": len(batch_entries),
            "chars": sum(item["chars"] for item in metrics),
            "serialized_bytes": sum(item["bytes"] for item in metrics),
            "estimated_input_tokens": input_tokens,
            "estimated_output_reserve_tokens": output_reserve,
            "prompt_overhead": args.prompt_overhead,
            "estimated_tokens": total_estimate,
            "first_id": batch_entries[0]["id"], "last_id": batch_entries[-1]["id"],
            "sha256": sha256(path),
        })
    (out / "BATCH_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    covered = sum(batch["count"] for batch in manifest["batches"])
    if covered != len(entries):
        raise SystemExit(f"INTERNAL ERROR: batches cover {covered} of {len(entries)} entries.")
    print(f"Created {total} batch(es) covering {covered} entries in {out.resolve()}")
    if args.token_budget:
        print(f"Estimated total budget: {args.token_budget} per batch; includes {args.prompt_overhead} prompt tokens "
              f"and {args.response_reserve_ratio:.2f}x response reserve (heuristic, not an exact tokenizer).")
    if oversized:
        print(f"WARNING: {len(oversized)} individual entry/entries exceed at least one configured limit.")
        for eid in oversized[:5]:
            print(f"  oversized: {eid}")


if __name__ == "__main__":
    main()
