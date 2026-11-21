"""Shared helpers for extract_text.py / inject_text.py (standard library only).
Adapters: ini (.ini .int .properties .lng), json, csv (.csv .tsv), txt.
Entry IDs are deterministic and collision-resistant within each source file.
"""
import csv
import io
import json
import re
import collections

ALPHA = re.compile(r"[^\W\d_]", re.UNICODE)
SECT = re.compile(r"^\s*\[(.+?)\]\s*$")
KV = re.compile(r"^\s*[^=;#!\[\s][^=]*?\s*=\s*")
SKIP_VALUE = re.compile(r"^[\w./\\:-]+\.(png|jpg|jpeg|ogg|wav|mp3|json|js|ogv|webm|ttf|otf|dds|tga)$", re.I)
ADAPTERS = {".ini": "ini", ".int": "ini", ".properties": "ini", ".lng": "ini",
            ".json": "json", ".csv": "csv", ".tsv": "csv", ".txt": "txt"}
HEADER_GUESS = ("text", "string", "english", "en", "original", "source", "content", "message", "dialogue")


def has_text(s):
    return bool(ALPHA.search(s))


def decode(data: bytes):
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8"), "utf-8", "efbbbf"
    if data.startswith(b"\xff\xfe"):
        return data[2:].decode("utf-16-le"), "utf-16-le", "fffe"
    if data.startswith(b"\xfe\xff"):
        return data[2:].decode("utf-16-be"), "utf-16-be", "feff"
    try:
        return data.decode("utf-8"), "utf-8", ""
    except UnicodeDecodeError:
        # Latin-1 is a reversible byte mapping, not an encoding-detection claim.
        return data.decode("latin-1"), "latin-1", ""


def encode(text, codec, bom_hex):
    """Return (bytes, codec_used); fall back to UTF-8 if the original codec cannot store text."""
    try:
        return bytes.fromhex(bom_hex) + text.encode(codec), codec
    except UnicodeEncodeError:
        return text.encode("utf-8"), "utf-8"


# ---------- INI-like ----------
def ini_parse(text, opts):
    lines = text.splitlines(keepends=True)
    items, section, seen, used = [], "", collections.Counter(), set()
    for i, raw in enumerate(lines):
        body = raw.rstrip("\r\n")
        m = SECT.match(body)
        if m:
            section = m.group(1)
            continue
        m = KV.match(body)
        if not m:
            continue
        key = body[:m.end()].split("=", 1)[0].strip()
        value = body[m.end():]
        quoted = len(value) >= 2 and value[0] == '"' and value[-1] == '"'
        val = value[1:-1] if quoted else value
        if not has_text(val) or SKIP_VALUE.match(val):
            continue
        key_id = f"{section}::{key}"
        seen[key_id] += 1
        sid = key_id if seen[key_id] == 1 else f"{key_id}#{seen[key_id]}"
        if sid in used:
            sid = f"{sid}~line{i + 1}"
        while sid in used:
            sid += "~"
        used.add(sid)
        items.append({"sid": sid, "original": val, "line": i,
                      "prefix": body[:m.end()], "quoted": quoted, "eol": raw[len(body):]})
    return lines, items


def ini_apply(text, opts, trans):
    lines, items = ini_parse(text, opts)
    applied, skipped = 0, []
    for it in items:
        t = trans.get(it["sid"])
        if t is None:
            continue
        if "\n" in t or "\r" in t:
            skipped.append((it["sid"], "real line break in translation (keep the literal \\\\n token)"))
            continue
        q = '"' if it["quoted"] else ""
        lines[it["line"]] = it["prefix"] + q + t + q + it["eol"]
        applied += 1
    return "".join(lines), applied, skipped


# ---------- JSON ----------
def _walk(node, path, out, key_re):
    if isinstance(node, str):
        if has_text(node) and not SKIP_VALUE.match(node):
            keys = [p for p in path if isinstance(p, str)]
            if key_re is None or (keys and key_re.search(keys[-1])):
                out.append((path, node))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _walk(value, path + [i], out, key_re)
    elif isinstance(node, dict):
        for key, value in node.items():
            _walk(value, path + [key], out, key_re)


def _pstr(path):
    """Collision-safe JSON Pointer ID with a namespace prefix."""
    if not path:
        return "json:@root"
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in path]
    return "json:/" + "/".join(escaped)


def json_parse(text, opts):
    data = json.loads(text)
    found = []
    _walk(data, [], found, re.compile(opts["json_keys"]) if opts.get("json_keys") else None)
    items = [{"sid": _pstr(path), "original": value, "path": path} for path, value in found]
    ids = [item["sid"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("JSON path ID collision detected; extraction stopped.")
    return data, items


def json_apply(text, opts, trans):
    data, items = json_parse(text, opts)
    applied = 0
    for it in items:
        t = trans.get(it["sid"])
        if t is None:
            continue
        if not isinstance(t, str):
            raise TypeError(f"Translation for {it['sid']} must be a string.")
        node = data
        for part in it["path"][:-1]:
            node = node[part]
        node[it["path"][-1]] = t
        applied += 1
    indent = 2 if "\n" in text.strip() else None
    out = json.dumps(data, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"))
    eol = "\r\n" if "\r\n" in text else "\n"
    if eol != "\n":
        out = out.replace("\n", eol)
    return out + (eol if text.endswith("\n") else ""), applied, []


# ---------- CSV / TSV ----------
def _csv_rows(text, delim):
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))


def _csv_cols(rows, opts):
    header = None if opts.get("no_header") else (rows[0] if rows else [])
    col = opts.get("csv_col")
    if col is None:
        if header:
            names = [h.strip().lower() for h in header]
            col = next((names.index(g) for g in HEADER_GUESS if g in names), 1 if len(names) > 1 else 0)
        else:
            col = 0
    elif isinstance(col, str):
        col = header.index(col) if header and col in header else int(col)
    idc = opts.get("csv_id_col")
    if isinstance(idc, str):
        idc = header.index(idc) if header and idc in header else int(idc)
    return int(col), idc


def csv_parse(text, opts):
    delim = "\t" if opts.get("delim") == "tab" else ","
    rows = _csv_rows(text, delim)
    col, idc = _csv_cols(rows, opts)
    start = 0 if opts.get("no_header") else 1
    items, used = [], set()
    for n, row in enumerate(rows[start:], start):
        if len(row) <= col or not has_text(row[col]):
            continue
        base = str(row[idc]) if idc is not None and len(row) > idc and row[idc] else f"row{n}"
        sid = base
        suffix = 2
        while sid in used:
            sid = f"{base}~row{n}" if suffix == 2 else f"{base}~row{n}-{suffix}"
            suffix += 1
        used.add(sid)
        items.append({"sid": sid, "original": row[col], "row": n})
    return rows, items, col


def csv_apply(text, opts, trans):
    delim = "\t" if opts.get("delim") == "tab" else ","
    rows, items, col = csv_parse(text, opts)
    applied = 0
    for it in items:
        t = trans.get(it["sid"])
        if t is not None:
            if not isinstance(t, str):
                raise TypeError(f"Translation for {it['sid']} must be a string.")
            rows[it["row"]][col] = t
            applied += 1
    buf = io.StringIO()
    csv.writer(buf, delimiter=delim, lineterminator="\r\n" if "\r\n" in text else "\n").writerows(rows)
    return buf.getvalue(), applied, []


# ---------- Plain text lines ----------
def txt_parse(text, opts):
    lines = text.splitlines(keepends=True)
    items = []
    for i, raw in enumerate(lines):
        body = raw.rstrip("\r\n")
        if has_text(body):
            items.append({"sid": f"line{i + 1}", "original": body, "line": i, "eol": raw[len(body):]})
    return lines, items


def txt_apply(text, opts, trans):
    lines, items = txt_parse(text, opts)
    applied, skipped = 0, []
    for it in items:
        t = trans.get(it["sid"])
        if t is None:
            continue
        if not isinstance(t, str):
            raise TypeError(f"Translation for {it['sid']} must be a string.")
        if "\n" in t or "\r" in t:
            skipped.append((it["sid"], "real line break in translation"))
            continue
        lines[it["line"]] = t + it["eol"]
        applied += 1
    return "".join(lines), applied, skipped


def parse(adapter, text, opts):
    if adapter == "ini":
        return ini_parse(text, opts)[1]
    if adapter == "json":
        return json_parse(text, opts)[1]
    if adapter == "csv":
        return csv_parse(text, opts)[1]
    return txt_parse(text, opts)[1]


def apply(adapter, text, opts, trans):
    adapters = {"ini": ini_apply, "json": json_apply, "csv": csv_apply, "txt": txt_apply}
    if adapter not in adapters:
        raise ValueError(f"Unsupported adapter: {adapter}")
    return adapters[adapter](text, opts, trans)
