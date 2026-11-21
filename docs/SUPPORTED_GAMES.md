# Community test results

Add a row per game you actually tried. Never attach game files or copyrighted text.
Status words: VERIFIED (confirmed working in-game), TESTED (ran, not checked in-game), PARTIAL (works in some places), FAILED, BLOCKED.

| Game | Engine | Text format | Extract | Inject | In-game Arabic | Notes |
|------|--------|-------------|---------|--------|----------------|-------|
| Hollow Knight 1.5 | Unity 2020, legacy UI Text | 10 `EN_*` TextAssets in `resources.assets` (via UnityPy) | TESTED (AI-written UnityPy scripts, not this repo's) | TESTED (backup kept) | PARTIAL: menus show joined Arabic; map labels and bench text still boxes | fonts patched with Windows donor fonts (not shareable); text pre-shaped at build time; cause of remaining boxes not yet found |
| _example_ | Unreal 3 | `Localization/INT/*.int` (UTF-16) | TESTED | TESTED | UNKNOWN | needs font with Arabic glyphs |
