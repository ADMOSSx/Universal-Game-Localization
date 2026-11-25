# Release verification — 1.1.0

Date: 2026-11-25

## Focused reverse-mode regression suite

Command:

```bash
python scripts/selftest_legacy.py
```

Result in the full review bundle: `LEGACY RTL + VCDIFF SELFTEST PASSED`.

Covered cases:

- Arabic logical → legacy visual/presentation-form → logical round-trip.
- Observed PUA offset mapping (`0xDE6`, including `F09A` → `FE80`).
- Canonical localization JSON lint (`original` / `translation`), bad and good examples.
- Existing output refusal, `--force`, input-overwrite refusal and symlink-output refusal.
- VCDIFF source-window offset, standard checksum-after layout, overlapping target copies, and chained `VCD_TARGET` unknown-byte propagation.
- Corrupt Adler-32 rejection and refusal to claim an expected MD5 when source bytes are unavailable.
- Actual Outlast fixtures when present alongside the review bundle.

## Outlast fixture results

- `arabic_lint.py evidence/_arabic_corpus.json --max 0`: 5,259 records, 0 errors, 28 warnings (16 repeated-word warnings and 12 tatweel warnings).
- `r_007.delta` + `OLGame.int`: Adler-32 MATCH; reconstructed MD5 `09c420931bbe509803a688204bb2080a` MATCH.
- `r_010.delta` without pristine source: 37.0% known bytes (19,173 / 51,838); 32,665 bytes remain source-dependent/unknown. Adler-32 is NOT VERIFIED without complete source bytes. This is byte coverage, not a claim that 37% of text strings are readable.

## Scope and limitations

- Python compilation and CLI help checks were run for the release scripts.
- The new focused reverse-mode suite passed.
- The historical full `scripts/selftest.py` did not complete within the five-minute execution window in this environment. It is **not marked as passed**; run it in the target environment before treating the entire legacy helper suite as verified.
- The VCDIFF decoder deliberately supports only version-0, default-code-table, uncompressed windows with no unsupported header/delta indicators. It fails closed for compressed sections, custom code tables and unsupported flags.
- No patch installer or game executable was launched. No user game folder was modified.
- The installable release excludes Outlast game files, delta payloads and recovered game text.
