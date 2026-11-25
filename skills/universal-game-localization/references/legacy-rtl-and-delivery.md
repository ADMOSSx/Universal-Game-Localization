# Legacy RTL layouts and delta-based patch delivery

Read when: Arabic text in the game looks reversed, blocky, or shows PUA glyphs; the target
engine predates HarfBuzz/DirectWrite shaping; or the patch you must inspect ships as a
delta installer instead of full files.

## 1. Three independent layers (check each separately)
| Layer | What you see | How to confirm |
|---|---|---|
| Shaping | letters already joined (ﺑـﺒـﺐ) instead of base letters (ب ب ب) | chars in FE70–FEFF or PUA F000–F1FF |
| Order | words read backwards (ﺔﻴﺑﺮﻌﻟﺍ = العربية) | words end with "لا" instead of starting with "ال" |
| Mapping | PUA codes (F09A…) instead of forms | PUA − 0xDE6 == a FE70–FEFF code |

`arabic_legacy.py scan` prints style + order + a confidence score per file.

## 2. Typical encodings
- **base letters + logical order** → modern engine (needs shaping at runtime; rare before ~2015).
- **presentation forms + visual order** → most common in 2005–2016 engines. Each *run* is
  shaped then reversed; ASCII keys, `{PLACEHOLDERS}`, digits and markup keep their position.
- **presentation forms remapped to PUA + custom punctuation** → engines with a private
  bitmap font. Observed mapping: `PUA = form − 0xDE6` (FE80→F09A … FEFC→F116), plus
  standalone codes for punctuation (one patch used F003=، F005=؟ F02B=.).
- Never mix styles inside one file; never store logical order when the engine expects visual
  (you get mirrored words). Determine it once, write it in PROJECT.md, then keep it.

## 3. Fonts
The engine must own every glyph you emit.
- Bitmap font atlases (UE3 `Font` assets) are the usual answer: the patch ships a font whose
  glyphs are already shaped and mapped to the codes in the text.
- Donor fonts: use an OFL/Apache font (Noto Sans Arabic is OFL 1.1 and was used by a shipped
  patch); convert outlines to the engine's atlas. Never ship Windows/system fonts.
- If the atlas lacks a code, the game draws boxes/nothing — check every code you emit,
  especially punctuation and kashida.
- A raw TTF inside a package is unusual; if `\x00\x01\x00\x00`/`OTTO` hits don't parse as a
  single valid sfnt table directory, they are false positives.

## 4. Language-slot hijack
Cheap way to add a language without UI work: replace the least-used language, then rename it
in every locale's language list. In one shipped patch that was a **14-byte** edit per file:
`(Name="Nihongo")` → `(Name="<shaped العربية>")` in 8 files, while the text moved into the
`JPN` folder. Look for `Name="`, `Language=`, `LangName` near a list of language names.
Document the swap: the user must select that slot in Options.

## 5. Delta patch packs
Shipped patch = manifest + one delta per target file.
Manifest usually carries, per file: path, md5/size before, md5/size after, payload name.
That is a free oracle: rebuild a file whose pristine copy you have and compare md5.
Checks that must all pass: each resource consumes exactly its declared length; every window's
`win_len` sums to `size_new`; rebuilt files match `md5_new`.

VCDIFF variant seen in the wild (RFC 3284 otherwise unchanged): **[description missing: this section was truncated in the repo, and sections 6-7 are gone too. Restore them from the original notes. `vcdiff_decode.py`'s header lists what the decoder supports.]**

## 8. Helper scope and safe use
- `arabic_legacy.py` handles Arabic Presentation Forms-B and the observed PUA offset (`0xDE6`).
  It does not infer custom punctuation PUA codes; preserve those until a font/codepoint map is proven.
- Keep translator JSON in logical Unicode. Apply shaping/visual order only to generated copies.
- Outputs require a separate path; use `--force` only to replace a known generated output. The tools
  never allow an output path to resolve to one of their input files and refuse symlinked destinations.
- `vcdiff_decode.py` is a conservative decoder, not a universal installer parser. Its exit codes are
  0 success, 1 malformed/unsupported input, 2 checksum/MD5 mismatch, and 3 requested MD5 could not
  be verified because source-copy bytes were unavailable.
