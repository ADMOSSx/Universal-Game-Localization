# ADMOSS Universal Game Localization Skill (v0.3.0 - lean)

A reusable OpenCode skill that prepares game localization: inspect, detect, extract (where possible), batch, validate, plan reinsertion, and hand off to a translator/AI. It is **not** a universal extractor and does not promise every game is supported.

## Built for free/low token limits
The skill file is ~4 KB, the agent keeps one short notes file (`reports/PROJECT.md`), and the scripts do extraction, batching, merging, validation and patch-building with zero AI tokens. Translation is done outside OpenCode (e.g. a free chat AI) unless you explicitly ask.

## What's included
- `SKILL.md` - the workflow the agent follows (10 steps + resume/progress support)
- `scripts/` - Python 3 helpers (standard library only):
  - `inventory.py` read-only folder audit + engine hints (compact summary)
  - `extract_text.py` / `inject_text.py` plain-text formats (.ini .int .properties .lng .json .csv .tsv .txt) -> strings.json and back into translated COPIES, keeping encoding/BOM/line endings
  - `split_batches.py` batches (grouping, size caps, hashes)
  - `merge_translations.py` safe merge by stable ID
  - `validate_translations.py` QA (placeholders, mojibake, Arabic checks, length)
  - `make_handoff.py` builds and verifies the handoff ZIP
  - `selftest.py` end-to-end check of all helpers
- `references/` - engine/format guide, research workflow, schema, batching, Arabic guide and test strings
- `templates/` - PROJECT notes, GUIDE (style + glossary), README_FIRST, master prompt

## Install (Windows)
1. Extract the ZIP.
2. Copy the folder `universal-game-localization` to `%USERPROFILE%\.config\opencode\skills\` (create `skills` if missing).
3. Check that `%USERPROFILE%\.config\opencode\skills\universal-game-localization\SKILL.md` exists.
4. Restart OpenCode.
5. Ask: `Use the universal-game-localization skill. Analyze this game folder: D:\path\to\game. Prepare it for Arabic localization. Do not modify original game files.`

Per-project alternative: `.opencode\skills\universal-game-localization\SKILL.md`. Docs: https://opencode.ai/docs/skills (check it for other supported locations).

Requires Python 3.8+ (`python --version`; on Windows `py` also works).

## Verify the helpers
```powershell
cd "%USERPROFILE%\.config\opencode\skills\universal-game-localization"
python scripts\selftest.py
```
Expected last line: `SELFTEST PASSED`.

## Helper usage
```powershell
python scripts\inventory.py "D:\Games\MyGame" --out localization-work\reports
python scripts\extract_text.py "D:\Games\MyGame" --out localization-work\normalized\strings.json
python scripts\split_batches.py normalized\strings.json --out translation_batches --size 100 --group-by source_file
python scripts\merge_translations.py normalized\strings.json returned_batches --out merged_translations.json
python scripts\validate_translations.py merged_translations.json --source normalized\strings.json --report validation_report.txt
python scripts\make_handoff.py localization-work
python scripts\inject_text.py merged_translations.json --files localization-work\normalized\files.json --out localization-work\patch
```
Input for the batch/merge/validate scripts is normalized JSON with an `entries` array (see `references\translation-schema.md`).

## Safety
The skill directs the agent to work on copies, ask before installing or running unknown tools, and never bypass anti-cheat/DRM. The scripts never modify game files; `inventory.py` refuses to write inside the game folder, and `split_batches.py` / `make_handoff.py` refuse to overwrite existing output without `--force`.
