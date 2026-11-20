#!/usr/bin/env python3
"""Heuristic QA for normalized translation JSON.

ERRORS (exit code 2): duplicate IDs, placeholder/markup mismatch, mojibake / replacement
characters, and (with --source) changed originals, unknown IDs.
WARNINGS (exit 0 unless --strict): blanks, untranslated-looking text, newline/whitespace
differences, pre-shaped Arabic or bidi control characters, length risks, lost-encoding '???'.
This is NOT proof of semantic correctness or in-game rendering.
"""
from pathlib import Path
import argparse, collections, json, re, sys

TOKEN_RE = re.compile(
    r"\{\{[^{}]+\}\}"                      # {{name}}
    r"|\$\{[^}]+\}"                         # ${var}
    r"|\{[^{}]*\}"                          # {0} {name} {}
    r"|%%"                                  # literal percent
    r"|%(?:\d+\$)?[-+ 0#]*\d*(?:\.\d+)?[sdifuxXcgeEG]"   # printf: %s %d %1$s %.2f
    r"|\\[nrt]"                             # escaped \n \r \t
    r"|<[^>]+>"                             # <b> </b> <color=#fff>
    r"|\[/?[a-z]+(?:=[^\]]*)?\]"            # [b] [color=red] [/b]
    r"|\[[A-Z0-9_]+\]"                      # [PLAYER_NAME]
)
LATIN_RE = re.compile(r"[A-Za-z]")
ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
PRESENTATION_RE = re.compile(r"[\uFB50-\uFDFF\uFE70-\uFEFF]")
BIDI_CTRL_RE = re.compile(r"[\u200E\u200F\u202A-\u202E\u2066-\u2069\u061C]")
MOJIBAKE_RE = re.compile(r"[\u00D8\u00D9][\u0080-\u00BF]|\uFFFD")


def tokens(s):
    return collections.Counter(TOKEN_RE.findall(str(s or "")))


def strip_tokens(s):
    return TOKEN_RE.sub(" ", str(s or ""))


def short(ids, n=40):
    ids = list(ids)
    return repr(ids[:n]) + (f" ... (+{len(ids) - n} more)" if len(ids) > n else "")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="merged or batch JSON with 'entries'")
    p.add_argument("--source", help="normalized source JSON: also checks IDs and unchanged originals")
    p.add_argument("--report", default="validation_report.txt")
    p.add_argument("--lang", default="", help="target language code (default: project.target_language)")
    p.add_argument("--max-ratio", type=float, default=2.0, help="length-ratio warning threshold")
    p.add_argument("--strict", action="store_true", help="treat warnings as failures")
    p.add_argument("--require-complete", action="store_true", help="blank translations count as errors")
    args = p.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    entries = data.get("entries", []) if isinstance(data, dict) else data
    lang = (args.lang or (data.get("project", {}) or {}).get("target_language", "") if isinstance(data, dict) else args.lang).lower()
    is_ar = lang.startswith("ar")

    errors, warns = collections.defaultdict(list), collections.defaultdict(list)
    ids = [e.get("id") for e in entries]
    for x, c in collections.Counter(ids).items():
        if c > 1:
            errors["Duplicate IDs"].append(x)

    if args.source:
        src = json.loads(Path(args.source).read_text(encoding="utf-8-sig"))
        src_map = {e.get("id"): e for e in src.get("entries", [])}
        for e in entries:
            s = src_map.get(e.get("id"))
            if s is None:
                errors["Unknown IDs (not in source)"].append(e.get("id"))
            elif "original" in e and e["original"] != s.get("original"):
                errors["Original text changed vs source"].append(e.get("id"))
        missing = [i for i in src_map if i not in set(ids)]
        if missing:
            warns["Source IDs absent from this file"].extend(missing)

    translated = 0
    for e in entries:
        eid = e.get("id")
        orig, tr = str(e.get("original", "")), str(e.get("translation", ""))
        if not tr.strip():
            (errors if args.require_complete else warns)["Blank translations"].append(eid)
            continue
        translated += 1
        if tokens(orig) != tokens(tr):
            errors["Placeholder/markup mismatch"].append(eid)
        if MOJIBAKE_RE.search(tr):
            errors["Mojibake or U+FFFD in translation (encoding problem)"].append(eid)
        if re.search(r"\?{3,}", tr) and "???" not in orig:
            warns["Possible lost characters ('???')"].append(eid)
        if orig.count("\n") != tr.count("\n"):
            warns["Line-break count differs"].append(eid)
        if (orig[:1].isspace() != tr[:1].isspace()) or (orig[-1:].isspace() != tr[-1:].isspace()):
            warns["Leading/trailing whitespace differs"].append(eid)
        plain_orig = strip_tokens(orig)
        if tr.strip() == orig.strip() and len(LATIN_RE.findall(plain_orig)) > 3:
            warns["Identical to original (untranslated?)"].append(eid)
        if is_ar:
            if len(LATIN_RE.findall(plain_orig)) >= 2 and not ARABIC_RE.search(strip_tokens(tr)):
                warns["No Arabic letters in translation"].append(eid)
            if PRESENTATION_RE.search(tr):
                warns["Pre-shaped Arabic presentation forms (translator files must stay logical Unicode)"].append(eid)
        if BIDI_CTRL_RE.search(tr) and not BIDI_CTRL_RE.search(orig):
            warns["Invisible bidi control characters added"].append(eid)
        limit = (e.get("metadata") or {}).get("max_chars")
        if isinstance(limit, int) and limit > 0 and len(tr) > limit:
            warns["Exceeds metadata.max_chars"].append(eid)
        elif len(plain_orig.strip()) >= 8 and len(tr) > args.max_ratio * max(len(orig), 1):
            warns["Translation much longer than original (UI overflow risk)"].append(eid)

    lines = [f"Entries: {len(entries)}  (non-blank translations: {translated})", f"Target language: {lang or 'unknown'}", ""]
    for title, bucket in (("ERRORS", errors), ("WARNINGS", warns)):
        lines.append(f"== {title}: {sum(len(v) for v in bucket.values())} ==")
        for k, v in bucket.items():
            lines.append(f"- {k}: {len(v)}  {short(v)}")
        if not bucket:
            lines.append("- none")
        lines.append("")
    lines.append("NOTE: heuristic validator only. It cannot prove semantic correctness or in-game rendering.")
    Path(args.report).write_text("\n".join(lines), encoding="utf-8")
    brief = [f"Entries {len(entries)}, translated {translated}. Errors {sum(len(v) for v in errors.values())}, warnings {sum(len(v) for v in warns.values())}."]
    for title, bucket in (("ERR", errors), ("WARN", warns)):
        brief += [f"{title} {k}: {len(v)} {short(v, 5)}" for k, v in bucket.items()]
    brief.append(f"Full report: {args.report}")
    print("\n".join(brief))
    if errors or (args.strict and warns):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
