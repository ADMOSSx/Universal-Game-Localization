#!/usr/bin/env python3
"""End-to-end self-test of the helper scripts using throw-away data (touches nothing else).
Run:  python scripts/selftest.py
"""
from pathlib import Path
import json, re, subprocess, sys, tempfile

HERE = Path(__file__).resolve().parent
PY = sys.executable
sys.path.insert(0, str(HERE))
import _textio as T
import split_batches as B


def run(*args, expect=0):
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == expect, f"{args[0]} exit {r.returncode} (expected {expect})\n{r.stdout}\n{r.stderr}"
    return r.stdout


def main():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        game = t / "game"; (game / "Localization" / "INT").mkdir(parents=True); (game / "Content" / "Paks").mkdir(parents=True)
        (game / "Localization" / "INT" / "Game.int").write_text("[Game]\nHello=Hello\n", encoding="utf-8")
        (game / "Config").mkdir()
        (game / "Config" / "Game.ini").write_text("[General]\nTitle=Example\n", encoding="utf-8")
        (game / "Content" / "Paks" / "main.pak").write_bytes(b"\x00" * 64)
        ws = t / "ws"
        out = run(HERE / "inventory.py", game, "--out", ws / "reports", "--hash-limit-mb", "1")
        assert "Unreal" in out, out
        inventory_summary = json.loads((ws / "reports" / "INVENTORY_SUMMARY.json").read_text(encoding="utf-8"))
        assert "Config/Game.ini" in inventory_summary["localization_candidates"]["sample"]
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

        # Resume emits only untranslated entries while retaining original batch filenames and IDs.
        partial_return = t / "partial-return"; partial_return.mkdir()
        source_batch_files = sorted(path for path in batches.glob("*.json") if re.fullmatch(r"batch_\d{4}\.json", path.name))
        first_batch = json.loads(source_batch_files[0].read_text(encoding="utf-8"))
        completed_entry = dict(first_batch["entries"][0], translation="Done", status="translated")
        (partial_return / "partial.json").write_text(
            json.dumps({"entries": [completed_entry]}, ensure_ascii=False), encoding="utf-8")
        pending = t / "pending"
        run(HERE / "resume_batches.py", batches, partial_return, "--out", pending)
        resume_manifest = json.loads((pending / "RESUME_MANIFEST.json").read_text(encoding="utf-8"))
        assert resume_manifest["completed_entries"] == 1
        assert resume_manifest["pending_entries"] == 24
        assert sorted(p.name for p in pending.glob("batch_*.json")) == sorted(
            b.name for b in source_batch_files)
        pending_first = json.loads((pending / source_batch_files[0].name).read_text(encoding="utf-8"))
        assert all(e["id"] != completed_entry["id"] for e in pending_first["entries"])
        run(HERE / "resume_batches.py", batches, partial_return, "--out", pending, expect=1)
        run(HERE / "resume_batches.py", batches, partial_return, "--out", pending, "--force")
        unknown_return = t / "unknown-return"; unknown_return.mkdir()
        (unknown_return / "unknown.json").write_text(
            json.dumps({"entries": [{"id": "not-in-source", "translation": ""}]}), encoding="utf-8")
        run(HERE / "resume_batches.py", batches, unknown_return, "--out", t / "unknown-pending", expect=1)

        returned = t / "returned"; returned.mkdir()
        for i, b in enumerate(sorted(f for f in batches.glob("*.json") if re.fullmatch(r"batch_\d{4}\.json", f.name))):
            d = json.loads(b.read_text(encoding="utf-8"))
            for e in d["entries"]:
                e["translation"] = f"مرحبا {{0}} عنصر {e['id']}\n"
            text = json.dumps(d, ensure_ascii=False)
            (returned / b.name).write_text(("```json\n" + text + "\n```") if i == 0 else text, encoding="utf-8")  # first one fenced
        (returned / "RESUME_MANIFEST.json").write_text(
            json.dumps({"pending_entries": 0}), encoding="utf-8")
        merged = ws / "merged.json"
        run(HERE / "merge_translations.py", src, returned, "--out", merged, "--require-complete")
        run(HERE / "validate_translations.py", merged, "--source", src, "--report", ws / "v.txt")

        bad = json.loads(merged.read_text(encoding="utf-8")); bad["entries"][0]["translation"] = "مرحبا بدون متغير\n"
        badp = ws / "bad.json"; badp.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        run(HERE / "validate_translations.py", badp, "--report", ws / "v2.txt", expect=2)  # placeholder mismatch caught

        # Markup order must be validated, and JSON path IDs must not collide.
        markup = {"entries": [{"id": "m1", "original": "<b>Hello</b>", "translation": "</b>Hello<b>"}]}
        markup_path = ws / "markup.json"; markup_path.write_text(json.dumps(markup), encoding="utf-8")
        run(HERE / "validate_translations.py", markup_path, "--report", ws / "v3.txt", expect=2)
        json_text = '{"menu.title":"Main","menu":{"title":"Settings"},"a/b":"Slash","a~b":"Tilde"}'
        _, json_items = T.json_parse(json_text, {})
        json_ids = [item["sid"] for item in json_items]
        assert len(json_ids) == len(set(json_ids)) == 4, json_ids
        assert B.estimated_tokens("مرحبا") >= 5  # conservative multilingual estimate
        assert "json:/menu.title" in json_ids and "json:/menu/title" in json_ids
        assert "json:/a~1b" in json_ids and "json:/a~0b" in json_ids
        root_data, root_items = T.json_parse('"Top-level dialogue"', {})
        assert root_items[0]["sid"] == "json:@root"
        root_patched, root_count, _ = T.json_apply('"Top-level dialogue"', {},
                                                    {"json:@root": "ترجمة"})
        assert root_count == 1 and json.loads(root_patched) == "ترجمة"
        csv_opts = {"delim": "comma", "no_header": False, "csv_id_col": "id", "csv_col": "text"}
        _, csv_items, _ = T.csv_parse("id,text\nsame,Hello\nsame,Goodbye\n", csv_opts)
        csv_ids = [item["sid"] for item in csv_items]
        assert len(csv_ids) == len(set(csv_ids)) == 2, csv_ids

        # --- plain-text extract -> inject round trip (identity must reproduce files byte-for-byte) ---
        rt = t / "rt"; (rt / "Localization").mkdir(parents=True)
        (rt / "Localization" / "Game.int").write_bytes(b"\xff\xfe" + "[Menu]\r\nPlay=\"Play Game\"\r\nQuit=Quit now\r\n; note\r\n[Menu]\r\nPlay=Again\r\n".encode("utf-16-le"))
        (rt / "Localization" / "ui.json").write_bytes(b'{\r\n  "title": "Main Menu",\r\n  "items": [\r\n    "Start",\r\n    "Options"\r\n  ],\r\n  "icon": "menu.png"\r\n}\r\n')
        (rt / "Localization" / "ui_lf.json").write_bytes(b'{\n  "name": "Hero",\n  "tip": "Press Start"\n}\n')
        (rt / "Localization" / "t.csv").write_bytes(b"id,text\r\na1,Hello there\r\na2,Goodbye\r\n")
        (rt / "Localization" / "lines.txt").write_bytes(b"First line\nSecond line\n")
        out = run(HERE / "extract_text.py", rt, "--out", t / "n" / "strings.json")
        assert "strings from 5 file(s)" in out, out
        file_meta = json.loads((t / "n" / "files.json").read_text(encoding="utf-8"))
        assert all(info.get("source_sha256") for info in file_meta["files"].values())
        run(HERE / "extract_text.py", rt, "--out", t / "n" / "strings.json", expect=1)
        run(HERE / "extract_text.py", rt, "--out", rt / "strings.json", expect=1)
        d = json.loads((t / "n" / "strings.json").read_text(encoding="utf-8"))
        ids = [e["id"] for e in d["entries"]]
        assert "Localization/Game.int::Menu::Play#2" in ids and not any("icon" in i for i in ids), ids
        for e in d["entries"]:
            e["translation"], e["status"] = e["original"], "translated"
        (t / "n" / "ident.json").write_text(json.dumps(d), encoding="utf-8")
        run(HERE / "inject_text.py", t / "n" / "ident.json", "--files", t / "n" / "files.json", "--out", t / "p1")
        for f in ("Game.int", "ui.json", "ui_lf.json", "t.csv", "lines.txt"):
            assert (t / "p1" / "Localization" / f).read_bytes() == (rt / "Localization" / f).read_bytes(), f"round trip differs: {f}"
        run(HERE / "inject_text.py", t / "n" / "ident.json", "--files", t / "n" / "files.json",
            "--out", t / "p1", expect=1)
        for e in d["entries"]:
            e["translation"] = "مرحبا " + e["id"].split("::")[-1]
        (t / "n" / "ar.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        run(HERE / "inject_text.py", t / "n" / "ar.json", "--files", t / "n" / "files.json", "--out", t / "p2")
        raw = (t / "p2" / "Localization" / "Game.int").read_bytes()
        assert raw[:2] == b"\xff\xfe" and "مرحبا" in raw[2:].decode("utf-16-le"), "UTF-16 patch wrong"
        source_bytes = (rt / "Localization" / "Game.int").read_bytes()
        (rt / "Localization" / "Game.int").write_bytes(source_bytes + b"; changed\r\n")
        run(HERE / "inject_text.py", t / "n" / "ar.json", "--files", t / "n" / "files.json",
            "--out", t / "stale-patch", expect=2)
        (rt / "Localization" / "Game.int").write_bytes(source_bytes)
        run(HERE / "inject_text.py", t / "n" / "ar.json", "--files", t / "n" / "files.json", "--out", rt / "bad", "--src-root", rt, expect=1)

        # A source file named PATCH_MANIFEST.json must not overwrite the generated manifest.
        conflict_game = t / "conflict-game"; conflict_game.mkdir()
        (conflict_game / "PATCH_MANIFEST.json").write_text('{"hello":"Hello"}', encoding="utf-8")
        conflict_norm = t / "conflict-normalized"; conflict_norm.mkdir()
        conflict_strings = conflict_norm / "strings.json"
        run(HERE / "extract_text.py", conflict_game, "--include", "PATCH_MANIFEST.json",
            "--out", conflict_strings)
        conflict_data = json.loads(conflict_strings.read_text(encoding="utf-8"))
        for entry in conflict_data["entries"]:
            entry["translation"], entry["status"] = "مرحبا", "translated"
        conflict_merged = conflict_norm / "merged.json"
        conflict_merged.write_text(json.dumps(conflict_data, ensure_ascii=False), encoding="utf-8")
        conflict_patch = t / "conflict-patch"
        run(HERE / "inject_text.py", conflict_merged, "--files", conflict_norm / "files.json",
            "--out", conflict_patch, expect=2)
        assert not conflict_patch.exists()

        (ws / "reports" / "GAME_PROFILE.json").write_text("{}", encoding="utf-8")
        (ws / "reports" / "PROJECT.md").write_text(
            "# Project\nWorkspace / source path: C:\\Games\\SecretGame\n", encoding="utf-8")
        run(HERE / "make_handoff.py", ws, "--force", "--out", ws, expect=1)
        # An arbitrary existing ZIP must not be deleted by --force.
        arbitrary_zip = t / "custom.zip"; arbitrary_zip.write_text("keep me", encoding="utf-8")
        run(HERE / "make_handoff.py", ws, "--force", "--out", t / "custom", expect=1)
        assert arbitrary_zip.read_text(encoding="utf-8") == "keep me"
        run(HERE / "make_handoff.py", ws)
        assert (ws / "HANDOFF_PACKAGE.zip").exists()
        assert (ws / "HANDOFF_PACKAGE" / "scripts" / "resume_batches.py").is_file()
        assert (ws / "HANDOFF_PACKAGE" / "ADMOSS_HANDOFF_PACKAGE.json").is_file()
        copied_project = (ws / "HANDOFF_PACKAGE" / "reports" / "PROJECT.md").read_text(encoding="utf-8")
        assert "SecretGame" not in copied_project and "<LOCAL_PATH_REDACTED>" in copied_project
        run(HERE / "make_handoff.py", ws, "--force")
    print("SELFTEST PASSED")


if __name__ == "__main__":
    main()
