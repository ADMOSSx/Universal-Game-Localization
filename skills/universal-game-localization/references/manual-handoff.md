# Manual translation handoff (no API integration)

Use this workflow when the user chooses an external translator instead of the current agent model.

## Principles
- Manual handoff is the recommended low-token route for users on limited/free model quotas.
- It uses a chat AI the user can access (for example ChatGPT, Claude, or another service). Do not promise that a provider's free tier, upload feature, or limits are permanent or available to every account.
- No API key, paid API, OAuth connection, or automatic provider call is required or implemented.
- The skill remains responsible for extraction, stable IDs, batching, package safety, importing, validation, patching and in-game checks. The external AI only translates the supplied batch data.
- Never ask the user to upload the original game folder, executable, binary archives, or unrelated assets to a chat AI.

## Selection point
After extraction, deduplication and batch creation are ready, ask once:
1. **Current agent** — translate batches here. This consumes the current agent/model's usage limit.
2. **Manual handoff** — create a ZIP for a chat AI the user chooses. This keeps translation outside the current agent's context and needs no API setup.

Skip the question when the user already selected a route or requested prepare-only. If the user emphasizes saving tokens or staying within free limits, recommend Manual Handoff.

## Create the package
Run from the installed skill folder:

    python scripts/make_handoff.py "<workspace>"

The script requires:
- normalized/strings.json or normalized/strings_unique.json
- translation_batches/BATCH_MANIFEST.json
- every listed batch_NNNN.json, with matching SHA-256 and entry IDs

It refuses to package missing, modified, incomplete, duplicate-ID or mismatched batches. It sanitizes the batch manifest's local path, skips likely secrets/symlinks and blocks game executables and binary archives. The package contains only translation batches and instructions; it excludes reports, the normalized full-source corpus, local helper scripts and game files.

Default outputs:
- <workspace>/HANDOFF_PACKAGE/
- <workspace>/HANDOFF_PACKAGE.zip

## What the user uploads
Ask the user to extract the ZIP locally, then upload these to the chosen chat AI:
1. README_FIRST.md
2. MASTER_INSTRUCTIONS.md
3. translator/GUIDE.md
4. One or a few translation_batches/batch_NNNN.json files

BATCH_MANIFEST.json can be included as reference. The user does not need to upload the original game or execute any script inside the package. Instruct the external AI to return the same filenames as valid UTF-8 JSON attachments; if it cannot attach files, return the JSON in a code block so the user can save it under the original filename.

## Import returned batches
The user creates a new folder for each translation round:
- returned_1/
- returned_2/
- and so on.

Save returned JSON files with their original batch_NNNN.json names. Never overwrite original files in translation_batches/ or copy a later round over an earlier return folder.

Check progress:

    python scripts/status.py "<workspace>"

For unfinished or needs_review entries, create pending-only batches:

    python scripts/resume_batches.py "<workspace>/translation_batches" "<workspace>/returned_1" --out "<workspace>/pending_batches"

For later rounds, pass every returned folder in chronological order to resume_batches.py and merge_translations.py. Never re-split the original batches after translation starts.

## Merge and QA
Merge all rounds against the exact normalized source used by the splitter:
- Use normalized/strings_unique.json when deduplication was used.
- Otherwise use normalized/strings.json.

Example without deduplication:

    python scripts/merge_translations.py "<workspace>/normalized/strings.json" "<workspace>/returned_1" "<workspace>/returned_2" --out "<workspace>/merged.json"
    python scripts/validate_translations.py "<workspace>/merged.json" --source "<workspace>/normalized/strings.json" --require-complete

When deduplication was used, merge against strings_unique.json, then run expand_translations.py with the original strings.json and DEDUPE_MAP.json before validation. Only validated translations should proceed to injection/patching. A validator pass is structural QA, not proof of semantic accuracy or in-game rendering.
