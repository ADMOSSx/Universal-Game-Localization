#!/usr/bin/env python3
"""arabic_legacy.py - detect / convert legacy Arabic text layouts used by old games.

Legacy layouts (very common in pre-Unicode-shaping engines):
  * base letters, logical order           -> modern, needs engine shaping (rare in 2005-2015 games)
  * presentation forms (FE70-FEFF), visual order (reversed per line)  <- most common
  * presentation forms remapped into PUA (e.g. F09A..F116 == FE80..FEFC)
  * PUA punctuation codes (e.g. F003=Arabic comma)

Commands
  scan <path> [--json]        per-file stats + order verdict
  to-logical <in> --out <f>   visual/PUA/presentation -> logical base letters (readable)
  to-visual <in> --out <f>    logical base letters -> presentation forms, visual order
                              [--pua 0xDE6] emit PUA-remapped forms instead
  verify <shaped> --logical <f>   round-trip check: logical -> shaped vs an existing file

Text decoding is auto-detected per file (UTF-16LE/BE BOM, else UTF-8, else UTF-16LE).
"""
import argparse, json, os, re, sys, unicodedata

from _safe_output import safe_write_bytes, safe_write_text, OutputSafetyError

# letter -> (isolated, final, initial, medial) in Presentation Forms-B; None = not a letter
FORMS = {
    "\u0621": ("\ufe80", None, None, None),
    "\u0622": ("\ufe81", "\ufe82", None, None),
    "\u0623": ("\ufe83", "\ufe84", None, None),
    "\u0624": ("\ufe85", "\ufe86", None, None),
    "\u0625": ("\ufe87", "\ufe88", None, None),
    "\u0626": ("\ufe89", "\ufe8a", "\ufe8b", "\ufe8c"),
    "\u0627": ("\ufe8d", "\ufe8e", None, None),
    "\u0628": ("\ufe8f", "\ufe90", "\ufe91", "\ufe92"),
    "\u0629": ("\ufe93", "\ufe94", None, None),
    "\u062a": ("\ufe95", "\ufe96", "\ufe97", "\ufe98"),
    "\u062b": ("\ufe99", "\ufe9a", "\ufe9b", "\ufe9c"),
    "\u062c": ("\ufe9d", "\ufe9e", "\ufe9f", "\ufea0"),
    "\u062d": ("\ufea1", "\ufea2", "\ufea3", "\ufea4"),
    "\u062e": ("\ufea5", "\ufea6", "\ufea7", "\ufea8"),
    "\u062f": ("\ufea9", "\ufeaa", None, None),
    "\u0630": ("\ufeab", "\ufeac", None, None),
    "\u0631": ("\ufead", "\ufeae", None, None),
    "\u0632": ("\ufeaf", "\ufeb0", None, None),
    "\u0633": ("\ufeb1", "\ufeb2", "\ufeb3", "\ufeb4"),
    "\u0634": ("\ufeb5", "\ufeb6", "\ufeb7", "\ufeb8"),
    "\u0635": ("\ufeb9", "\ufeba", "\ufebb", "\ufebc"),
    "\u0636": ("\ufebd", "\ufebe", "\ufebf", "\ufec0"),
    "\u0637": ("\ufec1", "\ufec2", "\ufec3", "\ufec4"),
    "\u0638": ("\ufec5", "\ufec6", "\ufec7", "\ufec8"),
    "\u0639": ("\ufec9", "\ufeca", "\ufecb", "\ufecc"),
    "\u063a": ("\ufecd", "\ufece", "\ufecf", "\ufed0"),
    "\u0641": ("\ufed1", "\ufed2", "\ufed3", "\ufed4"),
    "\u0642": ("\ufed5", "\ufed6", "\ufed7", "\ufed8"),
    "\u0643": ("\ufed9", "\ufeda", "\ufedb", "\ufedc"),
    "\u0644": ("\ufedd", "\ufede", "\ufedf", "\ufee0"),
    "\u0645": ("\ufee1", "\ufee2", "\ufee3", "\ufee4"),
    "\u0646": ("\ufee5", "\ufee6", "\ufee7", "\ufee8"),
    "\u0647": ("\ufee9", "\ufeea", "\ufeeb", "\ufeec"),
    "\u0648": ("\ufeed", "\ufeee", None, None),
    "\u0649": ("\ufeef", "\ufef0", None, None),
    "\u064a": ("\ufef1", "\ufef2", "\ufef3", "\ufef4"),
}
# lam + alef ligatures: (isolated, final)
LIG = {"\u0622": ("\ufef5", "\ufef6"), "\u0623": ("\ufef7", "\ufef8"),
       "\u0625": ("\ufef9", "\ufefa"), "\u0627": ("\ufefb", "\ufefc")}
HARAKAT = set("\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0653\u0654\u0655\u0670")
TRANSPARENT = HARAKAT | {"\u0640", "\u200c", "\u200d", "\u0651"}
PUA_BASE_DEFAULT = 0xDE6          # PUA = presentation_form - 0xDE6  (F09A == FE80)


def is_arabic(ch):
    c = ord(ch)
    return 0x0600 <= c <= 0x06FF or 0x0750 <= c <= 0x077F or 0xFB50 <= c <= 0xFDFF \
        or 0xFE70 <= c <= 0xFEFF or 0xF000 <= c <= 0xF1FF


def decode_bytes(b):
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16"), "utf-16-bom"
    # count odd/even zero bytes to guess UTF-16LE
    zeros_even = b[:4000:2].count(0)
    zeros_odd = b[1:4000:2].count(0)
    if zeros_odd > len(b[:4000:2]) * 0.3 and zeros_odd > zeros_even:
        return b.decode("utf-16le", "replace"), "utf-16le"
    try:
        return b.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return b.decode("utf-16le", "replace"), "utf-16le?"


def pua_to_form(ch, base=PUA_BASE_DEFAULT):
    c = ord(ch)
    if 0xF000 <= c <= 0xF8FF:
        return chr(c + base) if 0xFE70 <= c + base <= 0xFEFF else ch
    return ch


RUN_RE = re.compile(r"[\u0600-\u06ff\ufe70-\ufefc\uf000-\uf8ff\u0640 ]+")


def is_shaped(text):
    return any(0xFE70 <= ord(c) <= 0xFEFF or 0xF000 <= ord(c) <= 0xF8FF for c in text)


def detect_order(text):
    """'visual' or 'logical'. Shaped text is visual unless proven otherwise;
    base-letter text is logical unless the words read backwards."""
    verdict, conf = order_verdict(text)
    if verdict == "unknown":
        return "visual" if is_shaped(text) else "logical"
    return verdict


def to_logical(text, pua_base=PUA_BASE_DEFAULT, order="auto"):
    """forms/PUA + visual order -> base letters + logical order (readable).

    When order is visual, each maximal Arabic(+space) run is mapped to base
    letters and reversed in place; ASCII keys, placeholders, digits and markup
    keep their positions (this is the exact inverse of how these patches are
    built: shape each run, then reverse it). Already-logical text is only
    normalised, never mirrored."""
    if order == "auto":
        order = detect_order(text)
    if order != "visual":
        return unicodedata.normalize(
            "NFKC", "".join(pua_to_form(ch, pua_base) for ch in text))

    def fix(m):
        raw = "".join(pua_to_form(ch, pua_base) for ch in m.group(0))
        return unicodedata.normalize("NFKC", raw[::-1])
    return "\n".join(RUN_RE.sub(fix, line) for line in text.split("\n"))


def _letters(s):
    """split a logical line into (char, joins_prev, joins_next, transparent)"""
    res = []
    for ch in s:
        f = FORMS.get(ch)
        res.append((ch, f is not None and f[1] is not None, f is not None and f[2] is not None,
                    ch in TRANSPARENT))
    return res


def shape_logical(s):
    """logical base letters -> presentation forms, still logical order."""
    chars = list(s)
    out = []
    i = 0
    n = len(chars)
    while i < n:
        ch = chars[i]
        # lam + alef ligature
        if ch == "\u0644" and i + 1 < n and chars[i + 1] in LIG:
            prev = i - 1
            while prev >= 0 and chars[prev] in TRANSPARENT:
                prev -= 1
            joins = prev >= 0 and FORMS.get(chars[prev], (None,) * 4)[2] is not None
            iso, fin = LIG[chars[i + 1]]
            out.append(fin if joins else iso)
            i += 2
            continue
        f = FORMS.get(ch)
        if f is None:
            out.append(ch)
            i += 1
            continue
        prev = i - 1
        while prev >= 0 and chars[prev] in TRANSPARENT:
            prev -= 1
        nxt = i + 1
        while nxt < n and chars[nxt] in HARAKAT:
            nxt += 1
        prev_joins = prev >= 0 and FORMS.get(chars[prev], (None,) * 4)[2] is not None
        # a trailing kashida (tatweel) also connects: "بـ" is initial + tatweel
        next_joins = nxt < n and (chars[nxt] == "\u0640"
                                  or FORMS.get(chars[nxt], (None,) * 4)[1] is not None)
        iso, fin, ini, med = f
        if prev_joins and next_joins and med: out.append(med)
        elif prev_joins and fin: out.append(fin)
        elif next_joins and ini: out.append(ini)
        else: out.append(iso)
        i += 1
    return "".join(out)


def to_visual(logical, pua_base=None):
    """logical base text -> shaped forms in visual order (what old engines render)."""
    def fix(m):
        shaped = shape_logical(m.group(0))[::-1]
        if pua_base:
            shaped = "".join(chr(ord(c) - pua_base) if 0xFE70 <= ord(c) <= 0xFEFF else c
                             for c in shaped)
        return shaped
    return "\n".join(RUN_RE.sub(fix, line) for line in logical.split("\n"))


def order_verdict(text):
    """logical Arabic starts words with 'ال'; visual order ends them with 'لا'."""
    base = unicodedata.normalize("NFKC", "".join(pua_to_form(c) for c in text))
    toks = [t for t in re.split(r"\s+", base) if t]
    if not toks:
        return "unknown", 0.0
    head = sum(1 for t in toks if t.startswith("\u0627\u0644"))
    tail = sum(1 for t in toks if t.endswith("\u0644\u0627"))
    if head == tail == 0:
        return "unknown", 0.0
    frac = head / (head + tail)
    return ("logical" if frac >= 0.5 else "visual"), round(max(frac, 1 - frac), 3)


def scan_file(path):
    b = open(path, "rb").read()
    text, enc = decode_bytes(b)
    st = dict(file=path, size=len(b), encoding=enc, base=0, present=0, pua=0, arabic_runs=0)
    for ch in text:
        c = ord(ch)
        if 0x0600 <= c <= 0x06FF: st["base"] += 1
        elif 0xFE70 <= c <= 0xFEFF: st["present"] += 1
        elif 0xF000 <= c <= 0xF8FF: st["pua"] += 1
    if st["base"] + st["present"] + st["pua"]:
        st["arabic_runs"] = len(re.findall(r"[\u0600-\u06ff\uf000-\uf8ff\ufe70-\ufeff]{2,}", text))
        st["order"], st["order_conf"] = order_verdict(text)
        st["style"] = ("pua-forms" if st["pua"] > st["present"] else
                       "presentation" if st["present"] else "base-letters")
    else:
        st["order"], st["order_conf"], st["style"] = None, 0.0, None
    return st


def cmd_scan(args):
    rows = []
    p = args.path
    files = [p] if os.path.isfile(p) else [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs]
    for f in files:
        if os.path.getsize(f) > 400 * 1024 * 1024: continue
        try: rows.append(scan_file(f))
        except Exception as e: rows.append(dict(file=f, error=str(e)))
    ar = [r for r in rows if r.get("style")]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1)); return
    print(f"scanned {len(rows)} files, {len(ar)} contain Arabic")
    styles = {}
    for r in ar: styles[r["style"]] = styles.get(r["style"], 0) + 1
    for k, v in styles.items(): print(f"  style {k}: {v} files")
    orders = {}
    for r in ar: orders[r["order"]] = orders.get(r["order"], 0) + 1
    for k, v in orders.items(): print(f"  order {k}: {v} files")
    for r in ar[:args.limit]:
        print(f"  {os.path.basename(r['file']):38s} {r['style']:13s} {str(r['order']):8s} "
              f"conf={r['order_conf']} base={r['base']} pres={r['present']} pua={r['pua']}")


def cmd_to_logical(args):
    text, enc = decode_bytes(open(args.input, "rb").read())
    order = args.order
    if order == "auto":
        order = detect_order(text)
    out = to_logical(text, args.pua_base, order)
    safe_write_text(args.out, out, inputs=[args.input], force=args.force)
    print(f"{args.input} ({enc}, order={order}) -> {args.out}: {len(out)} chars, "
          f"base Arabic={sum(1 for c in out if 0x0600 <= ord(c) <= 0x06FF)}")


def cmd_to_visual(args):
    text = open(args.input, encoding="utf-8").read()
    out = to_visual(text, args.pua)
    enc = "utf-16le" if args.utf16 else "utf-8"
    data = out.encode(enc)
    if args.utf16 and args.bom: data = b"\xff\xfe" + data
    safe_write_bytes(args.out, data, inputs=[args.input], force=args.force)
    print(f"{args.input} -> {args.out}: {len(out)} chars as {enc}"
          + (f", PUA base 0x{args.pua:x}" if args.pua else ""))


def score(a, b):
    return sum(1 for x, y in zip(a, b) if x == y)


def cmd_verify(args):
    shaped, _ = decode_bytes(open(args.shaped, "rb").read())
    logical = open(args.logical, encoding="utf-8").read()
    # compare line by line, ignoring whitespace-only lines and CR differences
    a = [l.rstrip("\r") for l in shaped.split("\n") if l.strip()]
    mine = lambda base: [l.rstrip("\r") for l in to_visual(logical, base).split("\n") if l.strip()]

    base = args.pua
    if base is None and any(0xF000 <= ord(c) <= 0xF8FF for c in shaped):
        base = PUA_BASE_DEFAULT
    b = mine(base)
    same = score(a, b)
    if args.pua is None and base is not None and same < 0.5 * max(1, len(a)):
        # the patch may use its own offset: find the one that reproduces the most lines
        head = "\n".join(logical.split("\n")[:60])
        best, best_n = base, same
        for cand in range(0xD00, 0xE81):
            bb = [l.rstrip("\r") for l in to_visual(head, cand).split("\n") if l.strip()]
            n = score(a[:len(bb)], bb)
            if n > best_n:
                best, best_n = cand, n
        if best != base:
            print(f"PUA base auto-detected: 0x{best:x} (was 0x{base:x}: {same}/{len(a)})")
            base, b = best, mine(best)
            same = score(a, b)
    print(f"lines: existing={len(a)} regenerated={len(b)} identical={same} "
          f"({100.0*same/max(1,len(a)):.2f}%)" + (f" pua_base=0x{base:x}" if base else ""))
    bad = [(x, y) for x, y in zip(a, b) if x != y][:5]
    for x, y in bad:
        print("  existing:", x[:70]); print("  mine    :", y[:70])
    sys.exit(0 if same == len(a) == len(b) else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("path"); s.add_argument("--json", action="store_true")
    s.add_argument("--limit", type=int, default=40); s.set_defaults(func=cmd_scan)
    s = sub.add_parser("to-logical"); s.add_argument("input"); s.add_argument("--out", required=True)
    s.add_argument("--force", action="store_true", help="replace an existing output (never an input)")
    s.add_argument("--pua-base", type=lambda x: int(x, 0), default=PUA_BASE_DEFAULT)
    s.add_argument("--order", choices=("auto", "visual", "logical"), default="auto")
    s.set_defaults(func=cmd_to_logical)
    s = sub.add_parser("to-visual"); s.add_argument("input"); s.add_argument("--out", required=True)
    s.add_argument("--force", action="store_true", help="replace an existing output (never an input)")
    s.add_argument("--pua", type=lambda x: int(x, 0), default=None)
    s.add_argument("--utf16", action="store_true"); s.add_argument("--bom", action="store_true")
    s.set_defaults(func=cmd_to_visual)
    s = sub.add_parser("verify"); s.add_argument("shaped"); s.add_argument("--logical", required=True)
    s.add_argument("--pua", type=lambda x: int(x, 0), default=None)
    s.set_defaults(func=cmd_verify)
    a = ap.parse_args()
    try:
        a.func(a)
    except (OutputSafetyError, OSError, UnicodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
