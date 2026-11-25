# Changelog

## 1.3.0 — 2026-11-25
- Added explicit current-agent versus Manual Handoff translator selection, with Manual Handoff recommended for users saving limited/free current-agent quotas.
- Reworked make_handoff.py to validate the normalized source, batch manifest, SHA-256 hashes, entry counts and stable IDs before creating a package.
- Added provider-neutral external-AI rules, a manual handoff guide, and clearer upload/return/resume instructions.
- Handoff ZIPs now redact the batch manifest's absolute local path, skip unlisted batch-folder files, include the translator guide while excluding reports, the normalized full-source corpus and local helper scripts, and render source/target metadata.
- Added regression coverage for empty/tampered batches, ZIP contents, path privacy and language placeholders.
- Corrected the Godot adapter: .po remains a localization candidate but is not listed as extractable by the core extractor until a gettext adapter exists.


## 1.2.0 — 2026-11-25

- Added read-only Unity, Unreal Engine 3/4/5 and Godot adapter discovery with runtime clues, localization candidates, confidence and engine-specific next steps.
- Added `engine_adapters.py`; Unity Mono/IL2CPP are distinguished, Unreal IoStore markers are recognized, and Godot PCK detection checks the `GDPC` magic header.
- Added `engine-adapters.md`, synthetic adapter regression tests and a package-manifest verifier.
- Kept proprietary archives opaque: adapters never unpack assets, execute installers or modify game files.
- Added a release workflow that verifies the checksum manifest and test matrix before producing the installable ZIP.

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
