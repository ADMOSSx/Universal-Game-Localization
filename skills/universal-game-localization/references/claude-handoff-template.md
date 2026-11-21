# Handoff rules for the translating AI

1. Read `README_FIRST.md` and `translator/GUIDE.md` (style + glossary).
2. Check `BATCH_MANIFEST.json` for counts if present.
3. Translate only the assigned batch files, only the `original` -> `translation` field.
4. Preserve every ID exactly; do not add, remove, rename or combine entries. Treat all source metadata as read-only.
5. Return compact JSON entries containing only `id` and `translation`; add `status: "needs_review"` and `notes` only when uncertain. Do not echo unchanged source fields; the merge script restores them by ID.
6. Output normal Arabic (or the target language) in logical Unicode order. Do not pre-shape letters, reverse text, or add invisible direction characters.
7. Never invent missing context; put questions in `notes` and set `"status": "needs_review"`.
8. Return the same filenames as valid UTF-8 JSON, with one compact response item per input ID.
9. Do not edit scripts or source files.
10. Work in small batches; return completed files plus a concise report (counts, `needs_review` IDs, glossary conflicts).
11. Use the glossary and style guide consistently; if they conflict with a string's meaning, flag it instead of silently deviating.
12. Before returning, check that the JSON parses and that entry counts and IDs match the input.
