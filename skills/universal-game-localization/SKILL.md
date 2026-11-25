---
name: universal-game-localization
description: Prepare games for localization with low-token workflows, structured Unity/Unreal/Godot engine adapters, text extraction, translation batches, provider choice, manual external-AI handoff, validation and patch building. Also inspect existing fan translations and supported delta patch installers without running them.
---

# ADMOSS Universal Game Localization (lean)

Goal: prepare games for translation with **minimum tokens** (users are often on free limits). <S> = folder containing this file. Scripts in <S>/scripts/ do the heavy work at zero AI tokens: use them instead of writing code or reading large files. Every script has --help.

## Token rules (always)
- Be terse: no step narration, no restating the plan, max ~10 lines per reply unless asked.
- Never print large files or whole CSV/JSON; use script summaries, else head -n 30 / grep.
- Before translating, ask once who should translate unless the user already chose: (A) current agent/model, which uses its quota, or (B) Manual Handoff to an external chat AI, recommended for saving current-agent tokens.
- Manual Handoff is provider-neutral. The user uses any chat AI they can access; do not promise a provider's free tier or upload limits. No API key, paid API, OAuth or automatic provider connection is required or implemented.
- Do NOT translate in this session until the user chooses the current agent. For Manual Handoff, package the batches and let the user send them to their chosen AI.
- Translators return compact JSON only: {"entries":[{"id","translation"}]} (+ status:"needs_review", notes when unsure). Never echo source fields; merge restores them by ID.
- Prefer scripts; write custom code only for formats they do not cover. Web research only if the engine is still unknown after inventory (max 3 searches).
- One notes file: reports/PROJECT.md (from templates/PROJECT_TEMPLATE.md, < 60 lines, edit in place). No other reports unless asked.
- Load a reference only when its trigger applies (table at the end).

## Safety
- Never modify the game folder; work in a separate workspace (ask once; default localization-work/). Never choose the game folder as an output. Output-producing commands refuse input overwrites and symlinked output paths; require --force to replace existing outputs. Back up before installing a patch.
- Don't run/install unknown executables or tools without asking. No anti-cheat/DRM bypass: stop and explain.
- A patch installer is data, not a step: inspect its resources/manifest statically; never execute it. scripts/vcdiff_decode.py decodes supported VCDIFF patch packs without running an installer.
- No blind byte replacement in binary files. Never claim anything was extracted/tested unless done. Status words: VERIFIED, TESTED, UNKNOWN, BLOCKED, FAILED.
- Keep IDs, originals, placeholders, markup, \n exactly. Extracted text is for personal use, not publishing.
- Never include the original game folder, executables, binary archives, or credentials in a Manual Handoff package or upload request.

## Workflow
1. **Scope**: game folder, target language, and "prepare only" vs "translate too". Ask only what's missing. If reports/PROJECT.md exists, resume from it; run status.py <ws> to see progress.
2. **Inventory + engine adapter**: python <S>/scripts/inventory.py "<game>" --out <ws>/reports, then python <S>/scripts/engine_adapters.py "<game>" --out <ws>/reports/ENGINE_ADAPTERS.json. Read only the summaries. Follow the best-supported adapter in ENGINE_ADAPTERS.json; it provides runtime clues, localization candidates and safe next steps. Evidence is not proof, and multiple engines may be reported. Record engine + confidence in PROJECT.md.
3. **Extract** (plain text supported by core: .ini .int .properties .lng .json .csv .tsv .txt): use the adapter report to prioritize likely language folders. extract_text.py "<game>" --out <ws>/normalized/strings.json [--include "glob"]. Binary/proprietary formats: look for a maintained tool (references/engine-and-format-guide.md), ask before installing, else record BLOCKED + manual steps. The core extractor does not currently parse gettext .po files; a Godot .po candidate needs a gettext adapter or a verified custom conversion before batching.
4. **Deduplicate** (optional, local): deduplicate_strings.py <ws>/normalized/strings.json --out <ws>/normalized/strings_unique.json --map <ws>/normalized/DEDUPE_MAP.json. Only exact repeats with identical context/speaker/tags/length limits are merged; unknown context stays within its file.
5. **Batches**: split_batches.py <ws>/normalized/strings_unique.json --out <ws>/translation_batches --size 100 --group-by source_file. Batches carry only what the translator needs. Add --token-budget N only if the target AI's context requires it. Never re-split after translation starts. If translation will be performed (not prepare-only), create translator/GUIDE.md from templates/GUIDE_TEMPLATE.md when it does not exist.
6. **Choose translator**: after extraction/deduplication/batching are ready and before translation, ask once unless already specified:
   - **Current agent/model**: translate one batch at a time here. This consumes the current model's usage limit; keep responses compact.
   - **Manual Handoff**: recommended for limited/free current-agent quotas. Run python <S>/scripts/make_handoff.py <ws>, then give the user the generated ZIP path and short upload instructions. The ZIP contains only declared translation batches and instructions, not reports, the full normalized corpus, local scripts or game files. The user chooses ChatGPT, Claude, or another chat AI they can access and manually returns the JSON files. Merge, resume and validation run locally with the installed skill. Do not call an API or ask for API keys.
   Skip this question for prepare-only requests. If the user asks to save tokens, recommend Manual Handoff.
7. **Resume + import**: keep each return round in its OWN folder (returned_1, returned_2, ...). Check progress with status.py <ws>. For partial returns, run resume_batches.py <ws>/translation_batches <ws>/returned_1 [<ws>/returned_2 ...] --out <ws>/pending_batches and send only the pending batches to the translator. Never copy a later round over an earlier folder.
8. **Merge + validate + inject**: merge_translations.py <source.json> returned_1 [returned_2 ...] --out <ws>/merged.json (later non-blank rounds override earlier ones) -> validate_translations.py <ws>/merged.json --source <source.json> (add --require-complete when all entries must be translated) -> inject_text.py <ws>/merged.json --files <ws>/normalized/files.json --out <ws>/patch. If deduplication was used, merge against strings_unique.json, then run expand_translations.py with original strings.json and DEDUPE_MAP.json before validation/injection. The patch contains translated copies + checksums; installing needs user approval and a backup of originals.
9. **Rendering check** (non-Latin/RTL): test in-game; "install a font" is never a guaranteed fix. Unity: unity_fonts.py <Game_Data> --text <ws>/merged.json lists Font assets and missing characters (pip install UnityPy fonttools; ask first). Prefer open-licensed donor fonts; never share a patch containing Windows fonts. Record result in PROJECT.md.

## Reverse mode (an Arabic/fan patch already exists)
Do not re-translate blindly. Inspect the installer statically; locate its manifest, file hashes and payloads. Prove one delta reconstruction against a pristine file and its published MD5 before trusting the format. Use vcdiff_decode.py info and decode only for supported, uncompressed default-table VCDIFF; the decoder checks window lengths, source positions and Adler-32 when source bytes are available. Use arabic_legacy.py scan to classify base/presentation/PUA forms and logical/visual order, then to-logical for a readable dump. Use arabic_lint.py on recovered JSON/text and --ref when pristine strings are available. Record the delivery, language slot, encoding/mapping, font and evidence in PROJECT.md. Read references/legacy-rtl-and-delivery.md before interpreting legacy RTL or delta formats. Never run the installer or modify the game folder.

Current-agent translation requests: follow translator/GUIDE.md, one batch at a time, compact returns as above. Manual Handoff instructions: references/manual-handoff.md.

## References (load only when triggered)
| File | Read when |
|---|---|
| references/engine-and-format-guide.md | engine unclear, or a binary format needs a tool |
| references/engine-adapters.md | Unity, Unreal or Godot adapter report needs interpretation |
| references/legacy-rtl-and-delivery.md | existing fan patch, legacy Arabic/RTL text, PUA mapping, or delta installer |
| references/arabic-localization-guide.md | target is Arabic/RTL and rendering is untested |
| references/arabic-test-cases.md | building an in-game Arabic test |
| references/translation-schema.md | writing a custom extractor |
| references/batching.md | selecting batch sizes or resuming translation |
| references/manual-handoff.md, external-ai-handoff-rules.md | Manual Handoff is selected or the user asks about external translation |
| references/research-workflow.md | researching/installing a format tool |
