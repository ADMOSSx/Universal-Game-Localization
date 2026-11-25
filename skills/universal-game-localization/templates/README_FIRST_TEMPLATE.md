# README FIRST — Manual Game Localization Handoff

**Game:** {GAME_TITLE}  
**Engine:** {ENGINE}  
**Source language:** {SOURCE_LANGUAGE}  
**Target language:** {TARGET_LANGUAGE}  
**Batches:** {BATCH_COUNT}  
**Entries:** {ENTRY_COUNT}

## What this package is
This is a translation-only handoff package prepared by ADMOSS Universal Game Localization. It does not contain the original game. No API key, paid API, provider connection, or code execution is needed.

Use any chat AI you can access, such as ChatGPT, Claude, or another translation-capable assistant. A provider's own free usage limits and file-upload limits still apply.

## Upload these files to your chosen AI
1. MASTER_INSTRUCTIONS.md
2. translator/GUIDE.md
3. One or a few files from translation_batches/ (for example batch_0001.json)

You may also upload BATCH_MANIFEST.json for batch counts. Do not upload the original game folder or any game executable/binary archives.

Ask the AI to translate only the supplied batches and return valid UTF-8 JSON files with the same filenames. If it cannot attach files, ask it to return each complete JSON object in a code block so you can save it under the original filename.

## After translation
1. Create a new folder named returned_1 in your local localization workspace.
2. Save the returned JSON batch files there. Do not overwrite anything in translation_batches/.
3. For another round, use a new folder such as returned_2.
4. Run scripts/status.py to check progress. Use scripts/resume_batches.py to generate only missing or review-needed entries.
5. Back in your local skill workspace, merge and validate all returned rounds before building a patch.

## Important
- Preserve all entry IDs, placeholders, markup, formatting and line breaks.
- Return only the entries you were given; do not invent missing IDs.
- Keep Arabic in logical Unicode order. Do not pre-shape or reverse it.
- The package contains no executable scripts. Resume, merge and validation are performed locally with the installed Universal Game Localization skill.
- Translation validation catches structural mistakes, but a human/in-game review is still required.
