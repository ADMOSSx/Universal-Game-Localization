---
name: universal-game-localization
description: Prepare a game for localization (e.g. Arabic) - inspect folder, detect engine, extract text, make translation batches, validate, build patch. Use when the user wants to translate/localize a game or extract its text.
---

# ADMOSS Universal Game Localization (lean)

Goal: prepare a game for translation with **minimum tokens** (users are on free limits). `<S>` = folder containing this file. Scripts in `<S>/scripts/` do the heavy work at zero token cost - use them instead of writing code or reading files.

## Token rules (always)
- Be terse. No step narration, no restating the plan, no long summaries (max ~10 lines per reply unless asked).
- Never cat/print large files or whole CSV/JSON. Use script summaries; otherwise `head -n 30` / `grep`.
- Do NOT translate in this session unless the user asks. Make batches for an external free AI instead.
- Prefer the scripts. Write custom code only for formats they don't cover.
- Web research only if the engine/format is still unknown after the inventory; max 3 searches.
- One notes file: `reports/PROJECT.md` (template: `templates/PROJECT_TEMPLATE.md`, keep < 60 lines, edit sections, don't rewrite). No other reports unless asked.
- Read a reference only when its trigger applies (table at the end).

## Safety
- Never modify the game folder; work in a separate workspace (ask once where; default `localization-work/`). Extraction records SHA-256; patching refuses changed source files. Reject symlink/path escapes and never overwrite patch files without `--force`. Back up before installing a patch.
- Don't run/install unknown executables or tools without asking. No anti-cheat/DRM bypass - stop and explain.
- No blind byte replacement in binary files. Don't claim anything was extracted/tested unless done. Status words: VERIFIED, TESTED, UNKNOWN, BLOCKED, FAILED.
- Keep IDs, originals, placeholders, markup, `\n` exactly. Extracted text is for personal use, not publishing.

## Workflow
1. **Scope**: game folder, target language, "prepare only" vs "translate too". Ask only what's missing. If `reports/PROJECT.md` exists, resume from it.
2. **Inventory**: `python <S>/scripts/inventory.py "<game>" --out <ws>/reports`, then read only `INVENTORY_SUMMARY.json`. Engine hints are leads; confirm with evidence. Note engine + confidence in PROJECT.md.
3. **Extract**: for plain text (.ini .int .properties .lng .json .csv .tsv .txt):
   `python <S>/scripts/extract_text.py "<game>" --out <ws>/normalized/strings.json [--include "glob"] [--exclude "glob"]`. `files.json` records source hashes; outputs inside the game are refused.
   Binary/proprietary formats: look for a maintained tool (`references/engine-and-format-guide.md`), ask before installing, otherwise record BLOCKED + manual steps in PROJECT.md.
4. **Batches**: `python <S>/scripts/split_batches.py <ws>/normalized/strings.json --out <ws>/translation_batches --size 100 --group-by source_file --token-budget 2500`. Token counts are heuristic estimates; set limits to the model's actual context. Don't re-split after translation starts.
5. **Handoff** (when the user will translate elsewhere): fill `translator/GUIDE.md` from `templates/GUIDE_TEMPLATE.md` (style + glossary, keep it short; mark unknowns), then `python <S>/scripts/make_handoff.py <ws>`. Tell the user the upload order printed by the script (limits vary; batch by batch).
6. **Import**: `merge_translations.py normalized/strings.json returned_dir --out merged.json` -> `validate_translations.py merged.json --source normalized/strings.json` (fix errors) -> `inject_text.py merged.json --files normalized/files.json --out <ws>/patch`. It verifies source hashes and refuses existing patch files by default. Legacy metadata without hashes needs explicit `--allow-unverified-source`. Patch = translated copies + checksums; installing into the game needs user approval and a backup of originals.
7. **Rendering check** (non-Latin/RTL targets): the font/engine must be tested in-game; "install a font" is never a guaranteed fix. Record result in PROJECT.md.

Translate-too requests: translate batch by batch following `translator/GUIDE.md`, returning the same JSON (only `translation`, optional `notes`/`status`). Do it in the smallest useful chunks.

`python <S>/scripts/selftest.py` verifies the scripts work.

## References (load only when triggered)
| File | Read when |
|---|---|
| references/engine-and-format-guide.md | engine still unclear, or binary format needs a tool |
| references/arabic-localization-guide.md | target is Arabic/RTL and rendering is untested |
| references/arabic-test-cases.md | building an in-game Arabic test |
| references/translation-schema.md | writing a custom extractor |
| references/batching.md, claude-handoff-template.md, research-workflow.md | rarely; only if asked or in doubt |
