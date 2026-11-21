# Translation prompt template

You are translating game localization content from {SOURCE_LANGUAGE} to {TARGET_LANGUAGE}.

Read `translator/GUIDE.md` (style + glossary) first.

Rules:
- Translate only the `original` text into `translation`.
- Treat `id`, `original`, `context`, `speaker`, `source_file`, `tags`, `formatting` and all other source metadata as read-only.
- Return a compact JSON object with an `entries` array. Each item must contain only `id` and `translation`; add `status: "needs_review"` and a short `notes` value only when unsure.
- Do NOT echo `original`, `source_file`, `context`, `speaker`, `tags`, `metadata`, `project`, `batch` or any unchanged fields. The merge tool restores them by ID.
- Return exactly one item for each input ID. Never drop, rename, combine or invent IDs.
- Preserve placeholders, variables, markup, escape sequences and line breaks exactly (`{0}`, `%s`, `<b>`, `\n`, `[NAME]`).
- Do not change file structure or key names.
- Write normal text in logical Unicode order: no pre-shaped letters, no reversed text, no invisible direction characters.
- Do not invent context. If uncertain, add a short question in `notes` and set `"status": "needs_review"`.
- Keep terminology consistent with the glossary and the style guide.
- Return valid UTF-8 JSON with the same filename and entry count. Use this compact shape: `{"entries":[{"id":"...","translation":"..."}]}`.
- Do not add or remove entries. A blank or uncertain translation must still keep its ID; use `needs_review` when appropriate.
