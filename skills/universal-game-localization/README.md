# ADMOSS Universal Game Localization

**Version:** 1.2.0  
**Skill ID:** `universal-game-localization`

A low-token workflow for inspecting game files, identifying engine-specific localization paths, extracting and batching text, validating returned translations, and building a patch. It includes structured read-only adapters for **Unity, Unreal Engine 3/4/5 and Godot**, plus a static **reverse mode** for studying existing fan translations and supported VCDIFF patch packs without executing installers.

## Install / update

1. Extract the `universal-game-localization` folder from the ZIP.
2. Replace the previous installed folder with this complete folder. Do not copy only `SKILL.md`:
   the scripts and references are part of the skill.
3. Open a new agent session and check that the skill metadata/description mentions **reverse mode**.
4. Run `python scripts/arabic_legacy.py --help`, `python scripts/arabic_lint.py --help`, and
   `python scripts/vcdiff_decode.py --help` from inside the extracted skill folder.

The exact installation directory depends on the agent/client that loads skills. Keep the folder
name `universal-game-localization` and place it in that client's configured skills directory.

## Engine adapters (new in 1.2.0)

Run this after inventory to produce a structured JSON report:

```bash
python scripts/engine_adapters.py "<game-or-project-folder>" --out "<workspace>/reports/ENGINE_ADAPTERS.json"
```

The report separates Unity Mono/IL2CPP clues, Unreal 3 versus Unreal 4/5 and IoStore markers, and Godot project/PCK evidence. It lists likely localization files, opaque binary containers, confidence and safe next steps. It is a classifier, not an archive extractor; proprietary assets remain untouched. Read `references/engine-adapters.md` for details and limitations.

## Main workflow

Read `SKILL.md`. It keeps the agent instructions intentionally short; reference material is loaded
only when the task requires it. For Arabic legacy/RTL work or an existing patch, also read
`references/legacy-rtl-and-delivery.md`.

## Reverse-mode tools

- `scripts/arabic_legacy.py`: scan legacy Arabic encodings; convert Presentation Forms/observed PUA
  visual-order strings to logical Unicode and shape logical text for a legacy renderer.
- `scripts/arabic_lint.py`: audit the skill's JSON schema (`original`/`translation`), source/target
  JSON, TSV, `.int`/`.ini` and recovered text corpora.
- `scripts/engine_adapters.py`: read-only Unity/Unreal/Godot classification with localization candidates and per-engine next steps.
- `scripts/verify_manifest.py`: verify the package checksums (or regenerate them with `--write`).
- `scripts/selftest_adapters.py`: synthetic Unity/Unreal/Godot adapter regression tests.
- `scripts/vcdiff_decode.py`: inspect/decode uncompressed VCDIFF using the default code table;
  checks source positions, window sizes and Adler-32. Unsupported compressed/custom-table variants
  fail closed instead of producing a guessed result.

`arabic_lint.py` is read-only. The output-producing commands in `arabic_legacy.py` and
`vcdiff_decode.py` require explicit output paths, refuse to overwrite their inputs or write through
symlinked destinations, and require `--force` to replace an existing generated output.

## Tests

```bash
python scripts/verify_manifest.py # package integrity
python scripts/selftest_adapters.py # engine adapter regression tests
python scripts/selftest_legacy.py  # quick tests for reverse-mode tools
python scripts/selftest.py         # full regression suite for all helpers
```

The quick suite uses synthetic test data and, when present beside the skill bundle, also verifies
the Outlast evidence fixtures. The installable skill ZIP intentionally excludes game files and
recovered copyrighted game text. Set `PYTHONIOENCODING=utf-8` in Windows terminals when displaying
Arabic output.
