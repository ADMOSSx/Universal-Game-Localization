"""Shared helpers for extract_text.py / inject_text.py (standard library only).
Adapters: ini (.ini .int .properties .lng), json, csv (.csv .tsv), txt.
Entry IDs are derived from file path + key/path/row/line, so injection re-parses the source
and needs no extra location data inside the batches (keeps batches small).
"""
import csv, io, json, re, collections

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
        return data.decode("latin-1"), "latin-1", ""   # lossless byte round-trip


def encode(text, codec, bom_hex):
    """Return (bytes, codec_used). Falls back to UTF-8 if the original codec cannot hold the text."""
    try:
        return bytes.fromhex(bom_hex) + text.encode(codec), codec
    except UnicodeEncodeError:
        return text.encode("utf-8"), "utf-8"


# ---------- ini-like ----------
def ini_parse(text, opts):
    lines = text.splitlines(keepends=True)
    items, section, seen = [], "", collections.Counter()
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
        v = body[m.end():]
        quoted = len(v) >= 2 and v[0] == '"' and v[-1] == '"'
        val = v[1:-1] if quoted else v
        if not has_text(val) or SKIP_VALUE.match(val):
            continue
        k = f"{section}::{key}"
        seen[k] += 1
        items.append({"sid": k if seen[k] == 1 else f"{k}#{seen[k]}", "original": val, "line": i,
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
            skipped.append((it["sid"], "real line break in translation (keep the literal \\n token)"))
            continue
        q = '"' if it["quoted"] else ""
        lines[it["line"]] = it["prefix"] + q + t + q + it["eol"]
        applied += 1
    return "".join(lines), applied, skipped


# ---------- json ----------
def _walk(node, path, out, key_re):
    if isinstance(node, str):
        if has_text(node) and not SKIP_VALUE.match(node):
            keys = [p for p in path if isinstance(p, str)]
            if key_re is None or (keys and key_re.search(keys[-1])):
                out.append((path, node))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, path + [i], out, key_re)
    elif isinstance(node, dict):
        for k, v in node.items():
            _walk(v, path + [k], out, key_re)


def _pstr(path):
    return "".join(f"[{p}]" if isinstance(p, int) else (("." if i else "") + p) for i, p in enumerate(path))


def json_parse(text, opts):
    data = json.loads(text)
    found = []
    _walk(data, [], found, re.compile(opts["json_keys"]) if opts.get("json_keys") else None)
    return data, [{"sid": _pstr(p), "original": s, "path": p} for p, s in found]


def json_apply(text, opts, trans):
    data, items = json_parse(text, opts)
    applied = 0
    for it in items:
        t = trans.get(it["sid"])
        if t is None:
            continue
        node = data
        for p in it["path"][:-1]:
            node = node[p]
        node[it["path"][-1]] = t
        applied += 1
    indent = 2 if "\n" in text.strip() else None
    out = json.dumps(data, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"))
    eol = "\r\n" if "\r\n" in text else "\n"
    if eol != "\n":
        out = out.replace("\n", eol)   # json.dumps only emits structural newlines; string newlines are escaped
    return out + (eol if text.endswith("\n") else ""), applied, []


# ---------- csv / tsv ----------
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
        if header and col in header:
            col = header.index(col)
        else:
            col = int(col)
    idc = opts.get("csv_id_col")
    if isinstance(idc, str):
        idc = header.index(idc) if header and idc in header else int(idc)
    return int(col), idc


def csv_parse(text, opts):
    delim = "\t" if opts.get("delim") == "tab" else ","
    rows = _csv_rows(text, delim)
    col, idc = _csv_cols(rows, opts)
    start = 0 if opts.get("no_header") else 1
    items = []
    for n, row in enumerate(rows[start:], start):
        if len(row) <= col or not has_text(row[col]):
            continue
        sid = f"{row[idc]}" if idc is not None and len(row) > idc and row[idc] else f"row{n}"
        items.append({"sid": sid, "original": row[col], "row": n})
    return rows, items, col


def csv_apply(text, opts, trans):
    delim = "\t" if opts.get("delim") == "tab" else ","
    rows, items, col = csv_parse(text, opts)
    applied = 0
    for it in items:
        t = trans.get(it["sid"])
        if t is not None:
            rows[it["row"]][col] = t
            applied += 1
    buf = io.StringIO()
    csv.writer(buf, delimiter=delim, lineterminator="\r\n" if "\r\n" in text else "\n").writerows(rows)
    return buf.getvalue(), applied, []


# ---------- plain text lines ----------
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
    return {"ini": ini_apply, "json": json_apply, "csv": csv_apply, "txt": txt_apply}[adapter](text, opts, trans)
