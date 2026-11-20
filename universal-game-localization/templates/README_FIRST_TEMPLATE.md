# README FIRST - Game localization handoff

**Game:** (title / version)  **Engine (confidence):** (e.g. Unreal 3, medium)
**Source language -> target language:** (e.g. English -> Arabic, Modern Standard Arabic)

## What you are asked to do
Translate ONLY the `original` field of the entries in the batch files I give you, into `translation`.
Work one batch at a time and return the same filename with valid UTF-8 JSON.

## Read in this order
1. `MASTER_INSTRUCTIONS.md`
2. `translator/GUIDE.md` (style + glossary)
3. The batch file(s) I upload (`BATCH_MANIFEST.json` is optional)

## Hard rules
- Keep every `id` and every other field unchanged. Do not add/remove entries.
- Keep placeholders, tags, variables, escape sequences and line breaks exactly (`{0}`, `%s`, `<b>`, `\n`, `[NAME]`).
- Output normal Arabic text (logical Unicode order). Do NOT pre-shape letters or add invisible direction characters.
- If unsure, add a short question in `notes` and set `"status": "needs_review"`.
- Do not invent story facts.

## Returning your work
Return the completed JSON file(s) plus a short report: entry count, any `needs_review` IDs, any glossary conflicts.
