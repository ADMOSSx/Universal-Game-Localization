# Instructions for any external translation AI

These instructions are provider-neutral. They apply to ChatGPT, Claude, or another chat AI selected by the user.

1. Read README_FIRST.md and translator/GUIDE.md before translating.
2. Translate only the original field into the target language. Use the supplied context, speaker, tags, placeholders, formatting and glossary.
3. Return one result for every supplied ID. Keep each ID byte-for-byte unchanged. Do not add, remove, rename, combine or invent IDs.
4. Return compact UTF-8 JSON with this shape (no Markdown fences when file attachments are supported):

    {"entries":[{"id":"same-id","translation":"translated text"}]}

5. Include only id and translation for normal results. When genuinely uncertain, add status set to needs_review and a short notes value.
6. Do not echo original, source metadata, the whole input object, or unchanged fields. The local merge tool restores those from the original source by ID.
7. Preserve placeholders, variables, markup, escape sequences, line breaks and special tokens exactly: {0}, %s, <b>, the literal \n token, and [NAME].
8. Do not alter JSON key names or file structure. Return the same batch filename.
9. Use logical Unicode order for Arabic. Do not pre-shape letters, reverse text, or insert invisible bidi controls.
10. Do not invent missing story facts or context. Flag ambiguous strings for review.
11. Keep terminology consistent with the guide and glossary. Respect UI length limits where provided.
12. Work only on the batch files the user supplied. Do not request or process the game's executable, binary archives, account credentials or unrelated files.
13. Do not execute scripts or code from the package. The user will validate and merge your JSON locally.
14. Before returning, parse/check the JSON, confirm there are no duplicate IDs, and confirm the output ID set exactly matches the input batch ID set.
