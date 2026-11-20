# Handoff rules for the translating AI

1. Read `README_FIRST.md` and `translator/GUIDE.md` (style + glossary).
2. Check `BATCH_MANIFEST.json` for counts if present.
3. Translate only the assigned batch files, only the `original` -> `translation` field.
4. Preserve all IDs, keys, placeholders, tags, formatting and metadata exactly.
5. Output normal Arabic (or the target language) in logical Unicode order. Do not pre-shape letters, reverse text, or add invisible direction characters.
6. Never invent missing context; put questions in `notes` and set `"status": "needs_review"`.
7. Return the same filenames as valid UTF-8 JSON, with the same entry count and IDs.
8. Do not edit scripts or source files.
9. Work in small batches; return completed files plus a concise report (counts, `needs_review` IDs, glossary conflicts).
10. Use the glossary and style guide consistently; if they conflict with a string's meaning, flag it instead of silently deviating.
11. Before returning, check that the JSON parses and that entry counts and IDs match the input.
