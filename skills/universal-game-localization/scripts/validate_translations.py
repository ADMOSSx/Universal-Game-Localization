#!/usr/bin/env python3
"""Heuristic structural and localization QA for normalized translation JSON."""
from pathlib import Path
import argparse
import collections
import json
import re
import sys

TOKEN_RE = re.compile(
    r"\{\{[^{}]+\}\}"
    r"|\$\{[^}]+\}"
    r"|\{[^{}]*\}"
    r"|%%"
    r"|%(?:\d+\$)?[-+0#]*\d*(?:\.\d+)?[sdifuxXcgeEG]"
    r"|\\[nrt]"
    r"|<[^>]+>"
    r"|\[/?[a-z]+(?:=[^\]]*)?\]"
    r"|\[[A-Z0-9_]+\]"
)
HTML_TAG_RE = re.compile(r"<\s*(/?)\s*([A-Za-z][\w:-]*)\b[^<>]*?(/?)\s*>")
BBCODE_RE = re.compile(r"\[\s*(/?)\s*(b|i|u|color|size|url|center|left|right|quote|code|list)(?:=[^\]]*)?\s*\]", re.I)
LATIN_RE = re.compile(r"[A-Za-z]")
ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
PRESENTATION_RE = re.compile(r"[\uFB50-\uFDFF\uFE70-\uFEFF]")
BIDI_CTRL_RE = re.compile(r"[\u200E\u200F\u202A-\u202E\u2066-\u2069\u061C]")
MOJIBAKE_RE = re.compile(r"[\u00D8\u00D9][\u0080-\u00BF]|\uFFFD")
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def tokens(value):
    return collections.Counter(TOKEN_RE.findall(str(value or "")))


def strip_tokens(value):
    return TOKEN_RE.sub(" ", str(value or ""))


def short(values, n=40):
    values = list(values)
    return repr(values[:n]) + (f" ... (+{len(values) - n} more)" if len(values) > n else "")


def markup_issues(value):
    """Return unbalanced/misnested HTML-like and common BBCode tags."""
    found = []
    for match in HTML_TAG_RE.finditer(value):
        closing, name, self_closing = match.groups()
        name = name.lower()
        found.append((match.start(), bool(closing), name, bool(self_closing) or name in VOID_TAGS))
    for match in BBCODE_RE.finditer(value):
        closing, name = match.groups()
        found.append((match.start(), bool(closing), name.lower(), False))
    found.sort()
    stack, issues = [], []
    for _, closing, name, self_closing in found:
        if self_closing:
            if closing:
                issues.append(f"unexpected closing tag </{name}>")
            continue
        if closing:
            if not stack:
                issues.append(f"unexpected closing tag </{name}>")
            elif stack[-1] != name:
                issues.append(f"misnested closing tag </{name}>; expected </{stack[-1]}>")
                if name in stack:
                    while stack and stack[-1] != name:
                        stack.pop()
                    if stack:
                        stack.pop()
            else:
                stack.pop()
        else:
            stack.append(name)
    if stack:
        issues.append("unclosed tag(s): " + ", ".join(stack[-8:]))
    return issues


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
    if args.max_ratio <= 0:
        raise SystemExit("--max-ratio must be greater than zero.")

    try:
        data = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            entries = data.get("entries", [])
            project = data.get("project", {}) or {}
        else:
            entries, project = data, {}
        if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
            raise ValueError("input must contain a list of entry objects")
        lang = (args.lang or project.get("target_language", "")).lower()
    except (OSError, json.JSONDecodeError, AttributeError, ValueError) as ex:
        raise SystemExit(f"Invalid input: {ex}")
    is_ar = lang.startswith("ar")

    errors, warns = collections.defaultdict(list), collections.defaultdict(list)
    ids = [entry.get("id") for entry in entries]
    ids_set = set(ids)
    for value, count in collections.Counter(ids).items():
        if count > 1:
            errors["Duplicate IDs"].append(value)

    if args.source:
        try:
            source = json.loads(Path(args.source).read_text(encoding="utf-8-sig"))
            source_entries = source.get("entries", []) if isinstance(source, dict) else source
            if not isinstance(source_entries, list) or not all(isinstance(item, dict) for item in source_entries):
                raise ValueError("source must contain a list of entry objects")
            source_map = {}
            for item in source_entries:
                eid = item.get("id")
                if eid in source_map:
                    errors["Duplicate source IDs"].append(eid)
                source_map[eid] = item
            for entry in entries:
                source_entry = source_map.get(entry.get("id"))
                if source_entry is None:
                    errors["Unknown IDs (not in source)"].append(entry.get("id"))
                elif "original" in entry and entry["original"] != source_entry.get("original"):
                    errors["Original text changed vs source"].append(entry.get("id"))
            missing = [eid for eid in source_map if eid not in ids_set]
            if missing:
                warns["Source IDs absent from this file"].extend(missing)
        except (OSError, json.JSONDecodeError, ValueError, AttributeError) as ex:
            raise SystemExit(f"Invalid source file: {ex}")

    translated = 0
    for entry in entries:
        eid = entry.get("id")
        orig_value = entry.get("original", "")
        trans_value = entry.get("translation", "")
        if not isinstance(orig_value, str):
            errors["Non-string original values"].append(eid)
            continue
        if not isinstance(trans_value, str):
            errors["Non-string translation values"].append(eid)
            continue
        orig, tr = orig_value, trans_value
        if not tr.strip():
            (errors if args.require_complete else warns)["Blank translations"].append(eid)
            continue
        translated += 1
        if tokens(orig) != tokens(tr):
            errors["Placeholder/markup token mismatch"].append(eid)
        orig_issues = markup_issues(orig)   # e.g. a key hint like <E> is "unclosed" in the original too
        issues = [i for i in markup_issues(tr) if i not in orig_issues]
        if issues:
            errors["Unbalanced or misnested markup"].append(f"{eid}: {short(issues, 3)}")
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
            warns["Identical to original (possibly untranslated)"].append(eid)
        if is_ar:
            if len(LATIN_RE.findall(plain_orig)) >= 2 and not ARABIC_RE.search(strip_tokens(tr)):
                warns["No Arabic letters in translation"].append(eid)
            if PRESENTATION_RE.search(tr):
                warns["Pre-shaped Arabic presentation forms (translator files should use logical Unicode)"].append(eid)
        if BIDI_CTRL_RE.search(tr) and not BIDI_CTRL_RE.search(orig):
            warns["Invisible bidi control characters added"].append(eid)
        metadata = entry.get("metadata") or {}
        limit = metadata.get("max_chars") if isinstance(metadata, dict) else None
        if isinstance(limit, int) and limit > 0 and len(tr) > limit:
            warns["Exceeds metadata.max_chars"].append(eid)
        elif len(plain_orig.strip()) >= 8 and len(tr) > args.max_ratio * max(len(orig), 1):
            warns["Translation much longer than original (UI overflow risk)"].append(eid)

    lines = [f"Entries: {len(entries)}  (non-blank translations: {translated})",
             f"Target language: {lang or 'unknown'}", ""]
    for title, bucket in (("ERRORS", errors), ("WARNINGS", warns)):
        lines.append(f"== {title}: {sum(len(values) for values in bucket.values())} ==")
        for label, values in bucket.items():
            lines.append(f"- {label}: {len(values)}  {short(values)}")
        if not bucket:
            lines.append("- none")
        lines.append("")
    lines.append("NOTE: heuristic QA only. It cannot prove semantic accuracy or in-game rendering.")
    Path(args.report).write_text("\n".join(lines), encoding="utf-8")
    brief = [f"Entries {len(entries)}, translated {translated}. Errors {sum(map(len, errors.values()))}, warnings {sum(map(len, warns.values()))}."]
    for title, bucket in (("ERR", errors), ("WARN", warns)):
        brief += [f"{title} {label}: {len(values)} {short(values, 5)}" for label, values in bucket.items()]
    brief.append(f"Full report: {args.report}")
    print("\n".join(brief))
    if errors or (args.strict and warns):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
