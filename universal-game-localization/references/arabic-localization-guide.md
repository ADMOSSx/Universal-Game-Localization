# Arabic (RTL) localization guide

Facts here are general guidance. **Every claim about a specific engine must be tested in that game** and recorded in `reports/PROJECT.md` with status VERIFIED/TESTED/UNKNOWN.

## 1. Decide the style first (write it in translator/GUIDE.md)
- Register: Modern Standard Arabic by default; use a dialect only if the owner asks. Stay consistent.
- Player address and gender: prefer neutral wording; if forced, state the default (usually masculine) and flag lines that depend on it.
- Numerals: Western digits (0-9) by default; Arabic-Indic digits only if the font/engine is tested and the owner wants them. Pick one.
- Punctuation: Arabic comma/semicolon/question mark (، ؛ ؟); quotes « » or " " - pick one.
- Proper nouns and game terms: decide transliterate vs keep Latin, and put them in the glossary before translating.
- Plurals: Arabic has singular, dual and several plural patterns. For strings like "{0} items", ask how the engine handles plurals; prefer wording that works for any number when it does not.

## 2. Keep three layers separate
1. **Translator files** (normalized JSON, batches): plain Unicode in *logical* order. No pre-shaped letters (U+FB50-FDFF, U+FE70-FEFF), no reversed text, no invisible direction marks.
2. **Build step**: the only place for engine workarounds, always applied to a copy.
3. **Renderer**: what the game actually draws. Only an in-game test proves it works.

## 3. Rendering pipeline - classify the engine
- **A. Native shaping + bidi** (text stack with HarfBuzz/ICU-style support): Arabic usually works once a font with Arabic glyphs is available. Still test.
- **B. No shaping/bidi**: letters appear isolated and/or reversed. Options: a runtime plugin or mod framework, or build-time conversion to presentation forms plus visual reordering. Must be tested per text type (menu, dialogue, subtitles).
- **C. Bitmap fonts / font atlases**: the atlas must contain every needed glyph form (isolated, initial, medial, final), lam-alef ligatures and any diacritics, with correct metrics.
Do not assume a category from the engine name or version; test with `arabic-test-cases.md`.

## 4. What to check in a test build
- Letter joining and lam-alef (لا) ligatures; diacritics not clipped (vertical metrics)
- Right-to-left order of whole sentences, and of mixed Arabic + Latin + digits
- Parentheses/brackets mirroring and punctuation position
- Placeholders (`{0}`, `%s`, `%d`, `<b>`) staying in the right place and not reordered; tags closing correctly
- Line wrapping (breaks on word boundaries, not mid-word), alignment (right-aligned where expected), text overflow (Arabic is often shorter than German but longer than English in UI)
- Menu/layout mirroring needs, controller button glyphs inside text, subtitle timing
- Font licensing: embedding/redistributing a font may be restricted. Record the license.

## 5. Handling placeholders in RTL
Keep tokens exactly as in the original. Their visual position can change inside RTL text; if a test shows corruption, solve it in the build step or with a *tested* direction-mark workaround - do not ask translators to add invisible characters.

## 6. Typical failures and what they usually mean (hypotheses, not diagnoses)
| Symptom | Likely cause to investigate |
|---|---|
| Letters disconnected | No shaping in renderer, or font missing contextual glyphs |
| Words/sentences reversed | No bidi support (or text already reversed once) |
| Boxes / `?` | Missing glyph coverage, or encoding/codepage mismatch |
| Garbled Latin-looking text (Ø§Ù„...) | UTF-8 read as a single-byte codepage |
| Digits or `{0}` jump to the wrong side | Neutral-character bidi behavior |
