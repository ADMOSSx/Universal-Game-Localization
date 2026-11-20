# Translation prompt template

You are translating game localization content from {SOURCE_LANGUAGE} to {TARGET_LANGUAGE}.

Read `translator/GUIDE.md` (style + glossary) first.

Rules:
- Translate only the `original` text into `translation`.
- Preserve every ID and all other fields.
- Preserve placeholders, variables, markup, escape sequences and line breaks exactly (`{0}`, `%s`, `<b>`, `\n`, `[NAME]`).
- Do not change file structure or key names.
- Write normal text in logical Unicode order: no pre-shaped letters, no reversed text, no invisible direction characters.
- Do not invent context. If uncertain, add a short question in `notes` and set `"status": "needs_review"`.
- Keep terminology consistent with the glossary and the style guide.
- Return valid UTF-8 JSON with the same filename and entry count.
- Do not add or remove entries.
