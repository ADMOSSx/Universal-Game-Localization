# Normalized translation schema

UTF-8 JSON. Preserve source metadata. Example:

```json
{
  "schema_version": "1.0",
  "project": {
    "game_title": "Unknown",
    "engine": "Unknown",
    "source_language": "en",
    "target_language": "ar"
  },
  "entries": [
    {
      "id": "stable-id-or-generated-source-reference",
      "source_file": "relative/path",
      "context": "menu/subtitle/document/dialogue/unknown",
      "speaker": "",
      "original": "Original string",
      "translation": "",
      "notes": "",
      "tags": [],
      "placeholders": [],
      "formatting": [],
      "metadata": {},
      "status": "untranslated"
    }
  ]
}
```

## Fields
- `id` (required, unique, never changes after batch creation). If the source has no ID, derive a deterministic one from source path + key/index (or a hash of path+original) and document the method in `reports/PROJECT.md`.
- `original` is read-only. `translation` is the only field a translator fills (plus `notes` and `status`).
- `placeholders` / `formatting`: optional lists of tokens found in `original` (e.g. `{0}`, `%s`, `<b>`), useful for QA.
- `metadata` may carry `max_chars` (integer): the validator warns when a translation is longer.

## Status values
`untranslated` -> `translated` -> (`needs_review` when the translator is unsure) -> `approved` (set by a human reviewer).

## Rules
- Store translations as normal Unicode text in **logical order**. Never store pre-shaped Arabic presentation forms or visual-order (reversed) text in this file; any such workaround belongs to the build step and is applied to a copy.
- Keep escape sequences (`\n`), tags and variables byte-for-byte identical to the original.
