#!/usr/bin/env python3
"""Audit Arabic game text from localization JSON, legacy text files, or folders.

Supported JSON records:
  * canonical skill schema: {"entries":[{"id","original","translation"}]}
  * common pairs: {"entries":[{"id","source","target"}]} or {"en","ar"}
  * recovered corpora: {"resource_name":[{"off":N,"text":"..."}]}
  * a top-level list of any of the record forms above.

Checks (E = must fix, W = review):
  E Arabic ASCII punctuation, spacing, common spelling, bidi controls, placeholders,
    repeated structural errors, and (when a source is available) token mismatch.
  W length-ratio, repeated-word, tatweel, and glossary review.

Exit 0 clean, 1 errors, 2 nothing to check / unsupported input.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import arabic_legacy as AL

PUNCT = {",": "\u060c", ";": "\u061b", "?": "\u061f"}
AR = r"[\u0600-\u06ff\ufe70-\ufefc\uf000-\uf8ff]"
CHECKS = [
    ("ascii-punctuation", "E", re.compile(r"(?:%s[^\n]{0,20}?[,;?]|[,;?][^\n]{0,20}?%s)" % (AR, AR))),
    ("space-before-punct", "E", re.compile(r"[^\s]\s+[.,\u060c\u061f\u061b]")),
    ("hamza-imperative", "E", re.compile(r"\u0625(?:\u0636\u063a\u0637|\u0644\u0639\u0628|\u0641\u062a\u062d|\u0628\u062f\u0623|\u0633\u0645\u0639)")),
    ("ha-for-dhal", "E", re.compile(r"\u0647\u0627\u0630\u0627|\u0647\u0630\u0629|\u0647\u0630\u0649")),
    ("alef-maqsura", "E", re.compile(r"\u0627\u0644\u0630\u0649|\u0627\u0644\u062a\u0649|(?<!\u0625)\u0627\u0644\u0649(?=\s)")),
    ("tatweel", "W", re.compile(r"\u0640")),
    ("bidi-controls", "E", re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")),
    ("double-space", "E", re.compile(r"[^\s]  +[^\s]")),
    ("mixed-latin", "E", re.compile(r"%s[A-Za-z]|(?<!\\)[A-Za-z]%s" % (AR, AR))),
    ("triple-newline", "W", re.compile(r"\n{3,}")),
]
from validate_translations import TOKEN_RE  # single source of truth for placeholder/markup tokens
REPEAT_RE = re.compile(r"\b([\u0621-\u064a]{2,})\s+\1\b")


def _first(record: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return ""


def _record_unit(record: dict, key: str, filename: str, *, legacy_text: bool = False):
    source = _first(record, ("original", "source", "en", "source_text"))
    target = _first(record, ("translation", "target", "ar", "target_text"))
    if legacy_text and "text" in record:
        target = record.get("text", "")
        # Recovered patch corpora store pre-shaped text in visual order. Convert
        # each Arabic run back to logical Unicode before spelling checks.
        if isinstance(target, str):
            target = AL.to_logical(target, order="auto")
    if not isinstance(source, str) or not isinstance(target, str):
        return None
    if not source and not target:
        return None
    return dict(key=str(record.get("id", record.get("key", key))),
                source=source, target=target, file=filename)


def _json_units(path: str):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    units = []
    basename = os.path.basename(path)

    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                unit = _record_unit(item, str(i), basename, legacy_text="text" in item and
                                    not any(k in item for k in ("translation", "target", "ar")))
                if unit:
                    units.append(unit)
        return units

    if not isinstance(data, dict):
        return units

    if isinstance(data.get("entries"), list):
        for i, item in enumerate(data["entries"]):
            if isinstance(item, dict):
                unit = _record_unit(item, str(i), basename, legacy_text="text" in item and
                                    not any(k in item for k in ("translation", "target", "ar")))
                if unit:
                    units.append(unit)
        return units

    # Recovered corpora are keyed by resource name, with each value being a
    # list of {offset, known, text} records. Also support other list-valued maps.
    for resource, rows in data.items():
        if not isinstance(rows, list):
            continue
        for i, item in enumerate(rows):
            if isinstance(item, dict):
                unit = _record_unit(item, f"{resource}#{i}", str(resource),
                                    legacy_text="text" in item and
                                    not any(k in item for k in ("translation", "target", "ar")))
                if unit:
                    units.append(unit)
            elif isinstance(item, str):
                target = AL.to_logical(item, order="auto")
                if target.strip():
                    units.append(dict(key=f"{resource}#{i}", source="", target=target, file=str(resource)))
    return units


def load_units(path: str):
    """Return normalized list of {key, source, target, file}."""
    units = []
    p = Path(path)
    if p.is_dir():
        files = sorted(x for x in p.rglob("*") if x.is_file() and not x.is_symlink())
    else:
        files = [p]

    for item in files:
        f = str(item)
        ext = item.suffix.lower()
        try:
            if ext == ".json":
                units.extend(_json_units(f))
                continue
            if ext in (".tsv", ".txt"):
                with open(f, encoding="utf-8-sig", errors="replace") as stream:
                    for line_no, line in enumerate(stream, 1):
                        if "\t" not in line:
                            continue
                        source, target = line.rstrip("\r\n").split("\t", 1)
                        if source or target:
                            units.append(dict(key=str(line_no), source=source, target=target,
                                              file=item.name))
                continue
            if ext not in (".int", ".ini", ".properties", ".lng", ".cfg", ".dat"):
                continue
            raw = item.read_bytes()
            text, _ = AL.decode_bytes(raw)
            logical = AL.to_logical(text, order="auto")
            for line_no, line in enumerate(logical.splitlines(), 1):
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if re.search(AR, value):
                    units.append(dict(key=key.strip() or str(line_no), source="",
                                      target=value.strip(), file=item.name))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"WARNING: skipped {item}: {exc}", file=sys.stderr)
    return units


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="JSON corpus, TSV, .int/.ini file, or directory")
    ap.add_argument("--ref", help="pristine source-language folder/file for token+length checks")
    ap.add_argument("--glossary", help='TSV: english<TAB>arabic')
    ap.add_argument("--max", type=int, default=6, help="examples per check (0 = counts only)")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = ap.parse_args()
    if args.max < 0:
        ap.error("--max must be >= 0")

    units = load_units(args.path)
    if not units:
        print("no supported text records found", file=sys.stderr)
        sys.exit(2)

    ref = {}
    if args.ref:
        for unit in load_units(args.ref):
            ref[unit["key"].lower()] = unit["source"] or unit["target"]

    glossary = []
    if args.glossary:
        with open(args.glossary, encoding="utf-8-sig") as stream:
            for line in stream:
                if "\t" in line:
                    en, ar = line.rstrip("\r\n").split("\t", 1)
                    glossary.append((en.lower(), ar))

    found = []
    for unit in units:
        target = unit["target"]
        for name, severity, regex in CHECKS:
            for match in regex.finditer(target):
                found.append((severity, name, unit, match.group(0)[:60]))
        if target.count("{") != target.count("}"):
            found.append(("E", "unbalanced-braces", unit, ""))
        if target.count('"') % 2:
            found.append(("E", "odd-quotes", unit, ""))
        for match in REPEAT_RE.finditer(target):
            found.append(("W", "repeated-word", unit, match.group(0)))
        source = unit["source"] or ref.get(unit["key"].lower(), "")
        if source:
            source_tokens = sorted(TOKEN_RE.findall(source))
            target_tokens = sorted(TOKEN_RE.findall(target))
            if source_tokens != target_tokens:
                found.append(("E", "token-mismatch", unit, f"{source_tokens} -> {target_tokens}"))
            if len(source) > 3:
                ratio = len(target) / len(source)
                if ratio < 0.4 or ratio > 3.0:
                    found.append(("W", "length-ratio", unit,
                                  f"{ratio:.2f} ({len(source)}->{len(target)})"))
        for english, arabic in glossary:
            if english and english in source.lower() and arabic not in target:
                found.append(("W", "glossary", unit, f"{english} -> expected {arabic}"))

    grouped = {}
    for severity, name, unit, example in found:
        grouped.setdefault((severity, name), []).append((unit, example))
    errors = sum(len(items) for (severity, _), items in grouped.items() if severity == "E")
    warnings = sum(1 for item in found if item[0] == "W")

    if args.json:
        print(json.dumps(dict(
            units=len(units), errors=errors, warnings=warnings,
            checks={f"{severity}:{name}": len(items)
                    for (severity, name), items in grouped.items()},
            samples=[dict(check=name, severity=severity, file=unit["file"], key=unit["key"],
                          target=unit["target"][:160], example=example)
                     for (severity, name), items in grouped.items()
                     for unit, example in items[:2]],
        ), ensure_ascii=False, indent=1))
    else:
        print(f"{len(units)} strings, {errors} error(s), {warnings} warning(s)")
        for (severity, name), items in sorted(grouped.items()):
            print(f"  [{severity}] {name}: {len(items)}")
            for unit, example in items[:args.max]:
                print(f"      {unit['file']}:{unit['key'][:28]:28s} {unit['target'][:64]!r} {example}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
