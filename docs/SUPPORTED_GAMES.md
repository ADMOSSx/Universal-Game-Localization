# Community test results

Add a row per game you actually tried. Never attach game files or copyrighted text.
Status words: VERIFIED (confirmed working in-game for the tested areas), TESTED (ran, not checked in-game), PARTIAL (works in some places), FAILED, BLOCKED.

| Game | Engine | Text format | Extract | Inject | In-game Arabic | Notes |
|------|--------|-------------|---------|--------|----------------|-------|
| **Librerama 0.7.0** | Godot 4.6.2 | Gettext PO (.po); 348 source entries | TESTED (separate Godot PCK/PO workflow; not the core extractor) | TESTED (rebuilt localization package and launched the game) | **VERIFIED — main menu and settings** | Arabic is selectable in the language menu; screenshots confirm readable Arabic in the main menu, settings and an in-game dialog. The supplied test data contains 348/348 translation IDs with no blank values; 5 entries remain identical to their source text. This verifies the tested screens, not every game screen or minigame. Godot PCK unpacking and PO parsing are not currently provided by the core scripts. |
| Hollow Knight 1.5 | Unity 2020, legacy UI Text | 10 EN_* TextAssets in resources.assets (via UnityPy) | TESTED (AI-written UnityPy scripts, not this repo's) | TESTED (backup kept) | PARTIAL: menus show joined Arabic; map labels and bench text still boxes | fonts patched with Windows donor fonts (not shareable); text pre-shaped at build time; cause of remaining boxes not yet found |
| _placeholder (not a real test)_ | Unreal 3 | Localization/INT/*.int (UTF-16) | n/a | n/a | n/a | format example only; delete when adding real rows |

## Librerama test scope

The Librerama report is based on the v1.2.0 skill test package supplied by the project maintainer. It demonstrates a successful Arabic launch and visible Arabic rendering in the captured main-menu, language-selection, settings and dialog screens. It does **not** establish 100% coverage of all game content, minigames, runtime states, or automated extraction of Godot PCK / Gettext PO files by this repository's core scripts.
