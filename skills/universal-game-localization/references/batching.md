# Translation batch guidance

- Default batch size: 100 entries; adjust to the target AI's upload/context limits (check current limits). `--token-budget` caps a conservative heuristic estimate, not an exact model token count.
- Keep each entry atomic. Never split one string across batches.
- Prefer context-aware batching: `split_batches.py --group-by source_file` (or `context`) keeps related strings together; `--max-chars` caps batch text volume.
- Include context, speaker, tags, notes, original text, ID and an empty translation.
- UTF-8 JSON is canonical; CSV is optional for human convenience.
- Name batches `batch_0001.json`, `batch_0002.json`, ... plus `BATCH_MANIFEST.json` (ID ranges, counts, character counts, SHA-256 of input and of every batch).
- The translator returns the same schema and filenames and must not remove fields.
- If translating only a subset, leave other translations blank; use `--require-complete` only when everything is expected.
- Merge only by stable ID. `merge_translations.py` rejects duplicates, unknown IDs and changed originals unless explicitly allowed.
- Keep source originals unchanged. Validate returned files (`validate_translations.py --source ...`) before and after merging.
- Re-running the splitter never overwrites existing batches unless `--force` is given: do not re-split after translation has started (IDs and batch contents must stay stable).

## Resume partial work

- Keep original batch files unchanged after translation begins.
- Put each round's returned JSON files in their own folder (`returned_1`, `returned_2`, ...), then run `resume_batches.py translation_batches returned_1 [returned_2 ...] --out pending_batches`. Never copy a later round over an earlier round's files: pending batches reuse the original filenames, so that would overwrite finished work.
- The resume helper marks non-empty translations as complete unless their status is `needs_review`; it emits only remaining entries, reusing the original batch filenames and entry IDs.
- Do not point the output at either input directory. Existing generated resume files require explicit `--force`; unrelated files are never removed.
- Finally merge every round in order: `merge_translations.py normalized/strings.json returned_1 returned_2 --out merged.json`. Later rounds replace earlier ones; a blank later entry never erases earlier text. The same ID twice inside one folder is still an error.
