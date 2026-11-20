#!/usr/bin/env python3
"""End-to-end self-test of the helper scripts using throw-away data (touches nothing else).
Run:  python scripts/selftest.py
"""
from pathlib import Path
import json, subprocess, sys, tempfile

HERE = Path(__file__).resolve().parent
PY = sys.executable


def run(*args, expect=0):
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == expect, f"{args[0]} exit {r.returncode} (expected {expect})\n{r.stdout}\n{r.stderr}"
    return r.stdout


def main():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        game = t / "game"; (game / "Localization" / "INT").mkdir(parents=True); (game / "Content" / "Paks").mkdir(parents=True)
        (game / "Localization" / "INT" / "Game.int").write_text("[Game]\nHello=Hello\n", encoding="utf-8")
        (game / "Content" / "Paks" / "main.pak").write_bytes(b"\x00" * 64)
        ws = t / "ws"
        out = run(HERE / "inventory.py", game, "--out", ws / "reports", "--hash-limit-mb", "1")
        assert "Unreal" in out, out
        run(HERE / "inventory.py", game, "--out", game / "reports", expect=1)  # must refuse writing into the game folder

        entries = [{"id": f"e{i:03d}", "source_file": f"f{i % 3}.int", "context": "menu", "original": f"Hello {{0}} item {i}\n",
                    "translation": "", "status": "untranslated", "metadata": {}} for i in range(25)]
        src = ws / "normalized" / "strings.json"; src.parent.mkdir(parents=True)
        src.write_text(json.dumps({"schema_version": "1.0", "project": {"target_language": "ar"}, "entries": entries}), encoding="utf-8")
        batches = ws / "translation_batches"
        run(HERE / "split_batches.py", src, "--out", batches, "--size", "10", "--group-by", "source_file")
        run(HERE / "split_batches.py", src, "--out", batches, "--size", "10", expect=1)  # refuses to overwrite
        manifest = json.loads((batches / "BATCH_MANIFEST.json").read_text(encoding="utf-8"))
        assert sum(b["count"] for b in manifest["batches"]) == 25

        returned = t / "returned"; returned.mkdir()
        for i, b in enumerate(sorted(batches.glob("batch_*.json"))):
            d = json.loads(b.read_text(encoding="utf-8"))
            for e in d["entries"]:
                e["translation"] = f"مرحبا {{0}} عنصر {e['id']}\n"
            text = json.dumps(d, ensure_ascii=False)
            (returned / b.name).write_text(("```json\n" + text + "\n```") if i == 0 else text, encoding="utf-8")  # first one fenced
        merged = ws / "merged.json"
        run(HERE / "merge_translations.py", src, returned, "--out", merged, "--require-complete")
        run(HERE / "validate_translations.py", merged, "--source", src, "--report", ws / "v.txt")

        bad = json.loads(merged.read_text(encoding="utf-8")); bad["entries"][0]["translation"] = "مرحبا بدون متغير\n"
        badp = ws / "bad.json"; badp.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        run(HERE / "validate_translations.py", badp, "--report", ws / "v2.txt", expect=2)  # placeholder mismatch caught

        # --- plain-text extract -> inject round trip (identity must reproduce files byte-for-byte) ---
        rt = t / "rt"; (rt / "Localization").mkdir(parents=True)
        (rt / "Localization" / "Game.int").write_bytes(b"\xff\xfe" + "[Menu]\r\nPlay=\"Play Game\"\r\nQuit=Quit now\r\n; note\r\n[Menu]\r\nPlay=Again\r\n".encode("utf-16-le"))
        (rt / "Localization" / "ui.json").write_text('{\n  "title": "Main Menu",\n  "items": [\n    "Start",\n    "Options"\n  ],\n  "icon": "menu.png"\n}\n', encoding="utf-8")
        (rt / "Localization" / "t.csv").write_text("id,text\r\na1,Hello there\r\na2,Goodbye\r\n", encoding="utf-8")
        (rt / "Localization" / "lines.txt").write_bytes(b"First line\nSecond line\n")
        out = run(HERE / "extract_text.py", rt, "--out", t / "n" / "strings.json")
        assert "strings from 4 file(s)" in out, out
        d = json.loads((t / "n" / "strings.json").read_text(encoding="utf-8"))
        ids = [e["id"] for e in d["entries"]]
        assert "Localization/Game.int::Menu::Play#2" in ids and not any("icon" in i for i in ids), ids
        for e in d["entries"]:
            e["translation"], e["status"] = e["original"], "translated"
        (t / "n" / "ident.json").write_text(json.dumps(d), encoding="utf-8")
        run(HERE / "inject_text.py", t / "n" / "ident.json", "--files", t / "n" / "files.json", "--out", t / "p1")
        for f in ("Game.int", "ui.json", "t.csv", "lines.txt"):
            assert (t / "p1" / "Localization" / f).read_bytes() == (rt / "Localization" / f).read_bytes(), f"round trip differs: {f}"
        for e in d["entries"]:
            e["translation"] = "مرحبا " + e["id"].split("::")[-1]
        (t / "n" / "ar.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        run(HERE / "inject_text.py", t / "n" / "ar.json", "--files", t / "n" / "files.json", "--out", t / "p2")
        raw = (t / "p2" / "Localization" / "Game.int").read_bytes()
        assert raw[:2] == b"\xff\xfe" and "مرحبا" in raw[2:].decode("utf-16-le"), "UTF-16 patch wrong"
        run(HERE / "inject_text.py", t / "n" / "ar.json", "--files", t / "n" / "files.json", "--out", rt / "bad", "--src-root", rt, expect=1)

        (ws / "reports" / "GAME_PROFILE.json").write_text("{}", encoding="utf-8")
        run(HERE / "make_handoff.py", ws)
        assert (ws / "HANDOFF_PACKAGE.zip").exists()
    print("SELFTEST PASSED")


if __name__ == "__main__":
    main()
