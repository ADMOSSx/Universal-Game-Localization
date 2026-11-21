# Changelog

## Unreleased
- Security: handoff packaging now rejects workspace/ancestor output paths, only replaces verified generated packages, skips symlinks, and redacts local paths / likely embedded credentials.
- Security: extraction refuses output inside the source game and refuses overwriting existing extraction JSON unless `--force`; injection checks source SHA-256, path containment and symlinks, and refuses overwriting patch files/manifests unless `--force` is supplied.
- Reliability: JSON IDs use escaped JSON Pointers; CSV IDs are made unique when source ID columns contain duplicates; INI key collisions receive deterministic disambiguators.
- QA: validator now checks tag nesting and avoids rebuilding the source-ID set for every entry; merge rejects malformed entries and non-string translations.
- Batching: added serialized-size and heuristic token budgets with per-batch estimates; estimates are explicitly not exact tokenizer counts.
- Tests: expanded synthetic self-tests for JSON/CSV ID collisions, markup nesting, source integrity, safe output paths and overwrite protection.

## 0.3.3
- Docs: new README with banner, pipeline diagram, real terminal output and size chart (SVGs in `docs/images/`).

## 0.3.2
- Fix: `inject_text.py` re-wrote CRLF JSON files with LF endings; line endings are now preserved. Self-test fixtures are now byte-exact (Windows text mode had altered them).

## 0.3.1
- Fix: batch file detection used a case-insensitive glob on Windows and picked up `BATCH_MANIFEST.json` as a batch (caught by CI). Now matched with an exact `batch_NNNN.json` pattern.
- CI: pinned `ubuntu-24.04`, Python 3.10 and 3.12; minimum documented Python is 3.10.

## 0.3.0 (lean / low-token)
- SKILL.md cut from ~10 KB to ~4 KB; short description (it is loaded every session); references load only on a trigger table.
- Token rules: terse replies, never print big files, no translation unless asked, max 3 web searches, one notes file (`reports/PROJECT.md`) instead of ~12 reports.
- New `extract_text.py` + `inject_text.py`: plain-text formats go strings.json -> patched copies with no custom code (UTF-16/BOM, CRLF, quoted values, duplicate keys handled; identity round trip tested byte-for-byte).
- `inventory.py` summary is compact (dirs/counts instead of long file lists); `validate_translations.py` prints a short summary (full report goes to a file).
- Templates merged: `GUIDE_TEMPLATE.md` (style + glossary) replaces separate style/glossary/profile files.

## 0.2.0
Fixes
- translation-schema.md: JSON example had missing opening quotes (`notes"`, `tags"`, ...) - now valid JSON.
- README/INSTALL: removed doubled backslashes in Windows paths and commands; invocation uses "Use the skill" wording instead of relying on `@` autocomplete.
- Placeholder detection now covers `%1$s`, `%.2f`, `%%`, `{{x}}`, `${x}`, `{}`, BBCode-style tags.
- Scripts no longer crash on Arabic IDs in Windows consoles (UTF-8 stdout), on fenced ```json replies, or on list-shaped batch files.
- SKILL.md promised "context-aware" batches but the splitter only counted entries - now supports `--group-by` and `--max-chars`.
Improvements
- New helpers: `inventory.py`, `make_handoff.py`, `selftest.py`.
- merge: refuses changed originals, reports never-returned/blank IDs, writes `.report.json`, keeps `needs_review`.
- validate: `--source` check, mojibake, whitespace/newline, untranslated-looking, pre-shaped Arabic, bidi controls, length ratio / `max_chars`, `--strict`.
- split: manifest SHA-256 hashes, refuses to overwrite existing batches without `--force`.
- SKILL.md: quick start, PROGRESS.md resume, personal-use note on extracted text, script references at the right steps, agnostic wording for AI upload limits.
- New references: Arabic localization guide (register, 3-layer model, rendering pipelines, failure table); expanded Arabic test cases; engine tool leads (to verify) and more engine signatures.
- New templates: README_FIRST, STYLE_GUIDE, GLOSSARY; master prompt now covers logical-order Arabic and `needs_review`.

## 0.1.0
- Initial reusable skill package
