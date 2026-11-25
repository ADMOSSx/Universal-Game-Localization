# Engine adapters: Unity, Unreal and Godot

The adapter layer is a **read-only layout classifier**, not a universal archive extractor. Run it after inventory:

```bash
python scripts/engine_adapters.py "<game-or-project-folder>" --out "<workspace>/reports/ENGINE_ADAPTERS.json"
```

The report includes primary_engine, every matching detected_engines entry, confidence, evidence, runtime clues, likely localization paths, opaque asset paths, core-readable formats, safe next steps and explicit limitations. More than one candidate can be returned when a folder contains tools, mods or bundled sub-games. Treat evidence as a lead and confirm the actual game executable/build before selecting a tool.

## Unity

Recognizes combinations of UnityPlayer.dll, globalgamemanagers, resources.assets, a *_Data directory, ProjectSettings/ProjectVersion.txt, Unity bundles/assets and runtime markers. It distinguishes:

- **Mono** when *_Data/Managed/ assemblies are present.
- **IL2CPP** when GameAssembly.dll or *_Data/il2cpp_data/Metadata/global-metadata.dat is present.
- **Unknown runtime** when the folder is clearly Unity but those markers are absent.

Check StreamingAssets, Localization, Localisation, and relevant resource folders for readable JSON/CSV/TSV/TXT/XML/PO data. .assets, .bundle and .resource files remain opaque; this adapter does not unpack them. Unity version/serialization and IL2CPP constraints must be checked before choosing external tooling. unity_fonts.py remains a separate optional helper that requires UnityPy and fontTools.

## Unreal Engine

Separates strong **UE3** layout clues (.upk, CookedPC, Localization/*.int) from **UE4/UE5** clues (.uasset, .umap, .locres, .locmeta, Engine/, Content/Paks/, .utoc, .ucas). Paired .utoc + .ucas is reported as an IoStore clue. An Engine/Build/Build.version file is read only when it is small and parseable; its version is recorded as a clue, not proof that all game packages match it.

UE3 .int files may be plain text and can be handled by the core extractor if their encoding and syntax are supported. UE4/UE5 localization resources and package containers are binary and are **not** extracted by the core text extractor. Do not confuse .pak-only tools with IoStore support, and do not infer UE4 versus UE5 from an extension alone.

## Godot

Recognizes project.godot and PCK files with the GDPC magic header. For an editable project, it reports a project name/version clue (when present) and localization candidates such as .po, .pot, .csv, .json, .tres and .tscn in locale/translation folders. A visible project.godot generally indicates project/source layout; a PCK indicates an exported resource pack. Some exported games embed their PCK in the executable, so a missing sidecar PCK does not rule out Godot.

The core extractor can process supported plain-text formats, but it does not unpack .pck or decode Godot .translation resources. Preserve resource identifiers, UIDs and paths; translate only identified user-facing fields.

## Safety and status

- Scanning skips symbolic links and does not execute game code, launch installers, or modify source files.
- Candidate paths do not prove that a file contains user-facing text.
- Opaque binary containers remain BLOCKED until a version-compatible tool and a safe copy are verified.
- Ask before installing external tools. Never bypass DRM or anti-cheat.
- Only an in-game smoke test can prove that a localization patch renders correctly.

To run adapter regression tests:

```bash
python scripts/selftest_adapters.py
```
