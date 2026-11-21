#!/usr/bin/env python3
"""Show translation progress in a few lines (read-only) so work can resume after a limit runs out.

Usage: status.py <workspace>            (auto-detects normalized/, translation_batches/, returned*/)
       status.py <workspace> --batches DIR --returned DIR [DIR ...]
Counts every ID in the batches by its latest non-blank answer across rounds (later folders win).
"""
from pathlib import Path
import argparse, re, sys
from merge_translations import entries_of, load_lenient

BATCH_RE = re.compile(r"batch_\d{4}\.json")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("workspace")
    p.add_argument("--batches", default="")
    p.add_argument("--returned", nargs="*", default=None)
    args = p.parse_args()
    ws = Path(args.workspace)
    batches = Path(args.batches) if args.batches else ws / "translation_batches"
    returned = [Path(x) for x in args.returned] if args.returned is not None else \
        sorted(d for d in ws.glob("returned*") if d.is_dir())
    files = sorted(f for f in batches.glob("*.json") if BATCH_RE.fullmatch(f.name)) if batches.is_dir() else []
    if not files:
        raise SystemExit(f"No batch files in {batches}. Run split_batches.py first.")
    scope = {}
    for f in files:
        for e in entries_of(load_lenient(f), f):
            scope[e["id"]] = f.name
    state = {}                                    # id -> "done" | "review"
    for d in returned:
        for f in sorted(d.glob("*.json")):
            if f.name in {"BATCH_MANIFEST.json", "RESUME_MANIFEST.json"}:
                continue
            for e in entries_of(load_lenient(f), f):
                if isinstance(e, dict) and e.get("id") in scope and str(e.get("translation", "")).strip():
                    state[e["id"]] = "review" if e.get("status") == "needs_review" else "done"
    done = sum(v == "done" for v in state.values())
    review = sum(v == "review" for v in state.values())
    missing = len(scope) - len(state)
    pending_files = {scope[i] for i in scope if state.get(i) != "done"}
    print(f"To translate: {len(scope)} entries in {len(files)} batch file(s); returned folders: {len(returned)}")
    print(f"Done: {done} ({done / len(scope):.0%}) | needs_review: {review} | not returned/blank: {missing}")
    if review + missing:
        rets = " ".join(str(d) for d in returned)
        print(f"Next: resume_batches.py {batches} {rets} --out {ws / 'pending_batches'}   ({len(pending_files)} file(s) still open)")
    else:
        print("Everything translated. Next: merge_translations.py, then validate_translations.py.")


if __name__ == "__main__":
    main()
