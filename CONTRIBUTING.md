# Contributing

Thanks for helping! Rules that keep this project useful for people on free AI limits:

1. **Keep `SKILL.md` short.** Everything the agent loads costs the user tokens. Put detail in `references/` (loaded only on a trigger) or in a script (costs zero tokens).
2. **Prefer scripts over instructions.** If the agent would have to write the same code repeatedly, add a tested script instead. Scripts use the Python standard library only.
3. **Never include game files or extracted game text** in issues, PRs, or tests. Tests must use small synthetic data (see `scripts/selftest.py`).
4. **Don't claim what wasn't tested.** Engine/format/Arabic-rendering notes need a status: VERIFIED, TESTED, UNKNOWN, BLOCKED or FAILED.
5. **Safety first:** nothing may modify the original game folder, bypass anti-cheat/DRM, or run unknown executables automatically.

## Dev loop
```
python skills/universal-game-localization/scripts/selftest.py
```
Must print `SELFTEST PASSED` on Python 3.9+ (CI checks Windows and Linux). Add a round-trip check to `selftest.py` for any new adapter.

## Good first contributions
- Report results for a game in `docs/SUPPORTED_GAMES.md`
- New text adapters in `skills/universal-game-localization/scripts/_textio.py` (e.g. PO, XML) with a byte-for-byte identity test
- Ren'Py / Unity / Unreal 3 notes in `references/engine-and-format-guide.md` (verified tool names, links, versions)
