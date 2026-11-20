# Universal Game Localization

A reusable game-localization toolkit for AI agents, designed to keep token usage low. It helps inspect game folders, identify likely engines and formats, extract supported text, create translation batches, validate translations, and prepare patch files. Arabic and RTL localization guidance is included.

> This toolkit is not a universal extractor: support depends on each game's engine, file formats, and available tools.

## Skill

The OpenCode skill is in [`universal-game-localization/`](universal-game-localization/). Start with its [README](universal-game-localization/README.md) and [SKILL.md](universal-game-localization/SKILL.md).

## Install (Windows / OpenCode)

1. Copy the `universal-game-localization` folder into `%USERPROFILE%\.config\opencode\skills\`.
2. Confirm that `...\skills\universal-game-localization\SKILL.md` exists.
3. Restart OpenCode.
4. Ask your agent to use the `universal-game-localization` skill and analyze your game folder.

Requires Python 3.8+ for the helper scripts. Run the self-test from the skill folder:

```powershell
python scripts\selftest.py
```

Expected result: `SELFTEST PASSED`. See the skill README for full workflow, helper commands, safety notes, and supported formats.
"# Universal-Game-Localization" 
