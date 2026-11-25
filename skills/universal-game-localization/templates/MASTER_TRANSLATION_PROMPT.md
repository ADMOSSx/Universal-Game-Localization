# Translation prompt template

You are translating game localization content from {SOURCE_LANGUAGE} to {TARGET_LANGUAGE}.

Read translator/GUIDE.md (style + glossary) first.

Rules:
- Translate only the original text into translation.
- Treat id, original, context, speaker, source_file, tags, formatting and all other source metadata as read-only.
- Return compact UTF-8 JSON with an entries array. Each item must contain only id and translation; add status set to needs_review and a short notes value only when genuinely unsure.
- Do NOT echo original, source_file, context, speaker, tags, metadata, project, batch or any unchanged fields. The local merge tool restores source metadata by ID.
- Return exactly one item for every input ID. Never drop, rename, combine or invent IDs.
- Preserve placeholders, variables, markup, escape sequences, punctuation tokens and line breaks exactly ({0}, %s, <b>, \n, [NAME]).
- Do not change file structure or key names. Return valid UTF-8 JSON using the same batch filename.
- Write normal text in logical Unicode order. For Arabic, do not pre-shape letters, reverse text or add invisible direction characters.
- Do not invent context. If uncertain, add a short question in notes and set status to needs_review.
- Keep terminology consistent with the glossary and style guide.
- Do not execute code or scripts. Do not request the original game folder, executable or binary archives.
- Before returning, verify that JSON parses, IDs are unique, and the returned ID set exactly matches the input batch.

Use this compact shape:

    {"entries":[{"id":"...","translation":"..."}]}
