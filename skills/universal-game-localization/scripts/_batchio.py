"""Shared helpers for writing translation batches (standard library only).

slim_entry(): the view of an entry that is actually sent to the translating AI. Everything the AI does not
need (source_file, empty translation, status, unknown context, per-entry metadata, empty lists) is dropped
because every byte sent costs tokens. merge_translations.py restores all fields from the normalized source by ID.
dump_batch(): compact JSON, one entry per line (valid JSON, no indentation whitespace).
"""
import json

UNKNOWN_CONTEXT = {"", "unknown", "other", "n/a", "na", "none", "null"}


def slim_entry(entry):
    out = {"id": entry["id"], "original": entry.get("original", "")}
    if str(entry.get("context") or "").strip().casefold() not in UNKNOWN_CONTEXT:
        out["context"] = entry["context"]
    for key in ("speaker", "notes"):
        if str(entry.get(key) or "").strip():
            out[key] = entry[key]
    for key in ("tags", "placeholders", "formatting"):
        if entry.get(key):
            out[key] = entry[key]
    meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    for key, value in meta.items():          # layout limits help the translator, other metadata does not
        if str(key).startswith("max_"):
            out[key] = value
    if str(entry.get("translation") or "").strip():
        out["translation"] = entry["translation"]
        if entry.get("status") not in (None, "", "untranslated"):
            out["status"] = entry["status"]
    return out


def dump_batch(payload, pretty=False):
    if pretty:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    head = {k: v for k, v in payload.items() if k != "entries"}
    head_text = compact(head)[:-1]           # drop the closing brace, entries are appended below
    sep = "," if head else ""
    rows = ",\n".join(compact(e) for e in payload["entries"])
    return f'{head_text}{sep}"entries":[\n{rows}\n]}}\n'
