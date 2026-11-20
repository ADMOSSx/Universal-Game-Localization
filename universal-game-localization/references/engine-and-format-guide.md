# Engine and format detection guide

Treat this as a starting checklist, not an exhaustive or definitive detector.

## Evidence examples
- Unreal: `Engine/`, `*.pak`, `*.ucas`, `*.utoc`, `*.uasset`, `*.umap`, `*.locres`, `*.locmeta`, `*.int`, `*.ini`, `Binaries/`; version clues from metadata and package tools.
- Unity: `UnityPlayer.dll`, `GameName_Data/`, `globalgamemanagers`, `resources.assets`, `sharedassets*.assets`, `StreamingAssets`, `*.bundle`; Mono vs IL2CPP evidence such as `Managed/` assemblies or `GameAssembly.dll` plus `il2cpp_data`.
- Godot: `*.pck`, executable metadata, `project.godot` (usually development project, not always shipped).
- GameMaker: `data.win`, `*.yy` (project), runner artifacts; file versions vary.
- Ren'Py: `renpy/`, `game/`, `*.rpa`, `*.rpyd`, scripts `*.rpy`/compiled `*.rpyc`.
- RPG Maker: `data/`, `www/`, `js/`, `*.rvdata2`, `*.rpgmvp`, `*.json`; distinguish engine generations.
- Unreal Engine 3 (older): `*.upk`, `CookedPC/`, `Localization/INT/*.int`.
- Bethesda Creation Engine: `*.esm`, `*.esp`, `*.bsa`/`*.ba2`, `*.strings`/`*.dlstrings`/`*.ilstrings`.
- Electron/NW.js (web-based): `app.asar`, `package.nw`, plain JS/JSON resources.
- Source: VPK, `pak01_dir.vpk`, `*.bsp`, `resource/`, localization `*.txt`.
- CryEngine: `*.pak`, `*.cry`, engine metadata; archive extension alone is not proof.
- Proprietary/custom: executable strings, directory patterns, magic bytes, vendor DLLs, asset signatures, documentation.

## Generic formats
TXT, CSV, TSV, JSON, XML, YAML, INI, PO, MO, RESX, SQLite, HTML, JS, script files. Extract only known translatable fields; preserve keys, tags, variables, code and formatting.

## Archive caution
A `.pak`, `.dat`, `.bin`, `.arc`, `.bundle`, or `.assets` extension is not enough to identify the format. Inspect magic bytes and metadata. Do not brute-force, alter, or repack blindly. Ask before installing third-party tools.

## Tool leads (to research and verify - NOT recommendations to install)
Names change, break and get abandoned. Before suggesting any, check the current official page, license, version compatibility with the game and platform, and record it in `TOOL_RESEARCH.md`. Do not run or install anything without the user's approval.
- Unreal 4/5: FModel, UAssetGUI / UAssetAPI, UnrealLocres, repak / UnrealPak
- Unreal 3: UE Explorer, Gildor's UModel (UE Viewer), localization `.int` text files
- Unity: AssetStudio, UABE / UABEA, UnityPy; runtime text frameworks (e.g. XUnity.AutoTranslator, BepInEx) change how the game runs - check for anti-cheat first
- Ren'Py: unrpa (archives), translation framework built into Ren'Py (`game/tl/`)
- RPG Maker: data JSON/rvdata2 editors; MV/MZ assets may be encrypted
- Godot: godotpcktool, gdsdecomp (PCK extraction/decompile)
- GameMaker: UndertaleModTool
- Source: VPK tools; localization `resource/*.txt`
- Generic: QuickBMS (needs a game-specific script - verify the source), 7-Zip for standard archives, FontForge / fontTools for fonts

## Quick magic-byte references
`UnityFS` Unity bundle; `GDPC` Godot PCK; `RPA-3.0` Ren'Py; `PK\x03\x04` ZIP-based; `MZ` Windows PE; `34 12 AA 55` Valve VPK; `RPGMV` RPG Maker encrypted asset. Many Unreal `.pak` footers are at the END of the file, so an unrecognized header does not rule it out.
