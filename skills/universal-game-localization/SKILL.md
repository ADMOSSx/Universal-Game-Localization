---
name: universal-game-localization
description: Prepare a game for localization (e.g. Arabic) - inspect folder, detect engine, extract text, make translation batches, validate, build patch. Use when the user wants to translate/localize a game or extract its text.
---

# ADMOSS Universal Game Localization (lean)

Goal: prepare a game for translation with **minimum tokens** (users are on free limits). `<S>` = folder containing this file. Scripts in `<S>/scripts/` do the heavy work at zero token cost: use them instead of writing code or reading files. Every script has `--help`.

## Token rules (always)
- Be terse: no step narration, no restating the plan, max ~10 lines per reply unless asked.
- Never print large files or whole CSV/JSON; use script summaries, else `head -n 30` / `grep`.
- Do NOT translate in this session unless asked. Make batches for an external free AI instead.
- Translators return compact JSON only: `{"entries":[{"id","translation"}]}` (+ `status:"needs_review"`, `notes` when unsure). Never echo source fields; merge restores them by ID.
- Prefer scripts; write custom code only for formats they don't cover. Web research only if the engine is still unknown after inventory (max 3 searches).
- One notes file: `reports/PROJECT.md` (from `templates/PROJECT_TEMPLATE.md`, < 60 lines, edit in place). No other reports unless asked.
- Load a reference only when its trigger applies (table at the end).

## Safety
- Never modify the game folder; work in a separate workspace (ask once; default `localization-work/`). Scripts refuse to write inside the game, follow symlinks, or overwrite outputs without `--force`. Back up before installing a patch.
- Don't run/install unknown executables or tools without asking. No anti-cheat/DRM bypass: stop and explain.
- No blind byte replacement in binary files. Never claim anything was extracted/tested unless done. Status words: VERIFIED, TESTED, UNKNOWN, BLOCKED, FAILED.
- Keep IDs, originals, placeholders, markup, `\n` exactly. Extracted text is for personal use, not publishing.

## Workflow
1. **Scope**: game folder, target language, "prepare only" vs "translate too". Ask only what's missing. If `reports/PROJECT.md` exists, resume from it; run `status.py <ws>` to see progress.
2. **Inventory**: `python <S>/scripts/inventory.py "<game>" --out <ws>/reports`, read only `INVENTORY_SUMMARY.json`. Engine hints are leads; note engine + confidence in PROJECT.md.
3. **Extract** (plain text: .ini .int .properties .lng .json .csv .tsv .txt): `extract_text.py "<game>" --out <ws>/normalized/strings.json [--include "glob"]`. Binary/proprietary formats: look for a maintained tool (`references/engine-and-format-guide.md`), ask before installing, else record BLOCKED + manual steps.
4. **Deduplicate** (optional, local): `deduplicate_strings.py <ws>/normalized/strings.json --out <ws>/normalized/strings_unique.json --map <ws>/normalized/DEDUPE_MAP.json`. Only exact repeats with identical context/speaker/tags/length limits are merged; unknown context stays within its file.
5. **Batches**: `split_batches.py <ws>/normalized/strings_unique.json --out <ws>/translation_batches --size 100 --group-by source_file`. Batches carry only what the translator needs. Add `--token-budget N` only if the target AI's context requires it (small budgets create many more batches). Never re-split after translation starts.
6. **Handoff**: fill `translator/GUIDE.md` from `templates/GUIDE_TEMPLATE.md` (short; mark unknowns), then `make_handoff.py <ws>`; give the user the printed upload order.
   **Resume** after partial returns: save each round in its OWN folder, then `resume_batches.py <ws>/translation_batches <ws>/returned_1 [<ws>/returned_2 ...] --out <ws>/pending_batches` and upload only those.
7. **Import**: `merge_translations.py normalized/strings_unique.json returned_1 [returned_2 ...] --out merged_unique.json` (later rounds override earlier) -> `expand_translations.py normalized/strings.json merged_unique.json --map normalized/DEDUPE_MAP.json --out merged.json` (skip if you didn't deduplicate) -> `validate_translations.py merged.json --source normalized/strings.json` (fix errors) -> `inject_text.py merged.json --files normalized/files.json --out <ws>/patch`. The patch is translated copies + checksums; installing needs user approval and a backup of originals.
8. **Rendering check** (non-Latin/RTL): test in-game; "install a font" is never a guaranteed fix. Unity: `unity_fonts.py <Game_Data> --text <ws>/merged.json` lists Font assets and missing characters (`pip install UnityPy fonttools`; ask first); a component with an unpatched font shows boxes. Prefer open-licensed donor fonts; never share a patch containing Windows fonts. Record result in PROJECT.md.

Translate-too requests: follow `translator/GUIDE.md`, one batch at a time, compact returns as above.

`selftest.py` verifies the scripts work.

## References (load only when triggered)
| File | Read when |
|---|---|
| references/engine-and-format-guide.md | engine unclear, or a binary format needs a tool |
| references/arabic-localization-guide.md | target is Arabic/RTL and rendering is untested |
| references/arabic-test-cases.md | building an in-game Arabic test |
| references/translation-schema.md | writing a custom extractor |
| references/batching.md, claude-handoff-template.md, research-workflow.md | only if asked or in doubt |
