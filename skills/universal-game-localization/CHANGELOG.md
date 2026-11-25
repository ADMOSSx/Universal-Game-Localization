# Changelog

## 1.1.0 — 2026-11-25

- Added reverse mode for static analysis of existing fan translations and delta patch installers.
- Added legacy RTL reference covering Presentation Forms, visual order, PUA mapping, fonts, language
  slot reuse and delta patch delivery.
- Added `arabic_legacy.py` for scan, logical/visual conversion and round-trip verification.
- Added `arabic_lint.py` support for the skill's canonical JSON schema (`original` / `translation`),
  source/target pairs and recovered resource corpora.
- Hardened `vcdiff_decode.py`: source offsets, VCD_TARGET windows, exact section/window bounds,
  Adler-32 validation, overlapping target copies, and explicit incomplete-verification reporting.
- Added atomic output handling: no input overwrite, no symlink destination, and no output replacement
  without `--force`.
- Added focused regression tests for PUA round-trip, lint schema, real Outlast evidence, source
  positions, overlapping VCDIFF copies, checksum failures and output safety.

## 1.0.0 — previous snapshot

- Inventory, text extraction, batching, translation merge/resume, validation, patch injection and
  Unity font inventory helpers.
