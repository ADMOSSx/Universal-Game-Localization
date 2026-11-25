# Release verification — 1.4.0

Date: 2026-11-25

## Automated verification

The v1.4.0 release workflow verifies the package manifest, compiles all Python helpers, runs the full helper regression suite, and runs the Unity/Unreal/Godot adapter self-test on this matrix:

- Ubuntu 24.04 + Python 3.10
- Ubuntu 24.04 + Python 3.12
- Windows + Python 3.10
- Windows + Python 3.12

The synthetic regression suite covers extraction and injection round trips, stable IDs, compact batches, token-budget estimates, deduplication and expansion, multi-round merge/resume, Arabic lint, placeholder and markup checks, Manual Handoff package integrity/privacy, safe output paths, and manifest symlink rejection. It also checks that auto-detected return rounds are processed in natural numeric order.

The workflow publishes the installable ZIP only after all four matrix jobs succeed. This file describes the release checks; the actual GitHub Actions run linked from the release is the source of the final run result.

## Real-game evidence and scope

The repository currently records one community game report: **Hollow Knight 1.5**. Arabic is reported as partially working in-game. That extraction/injection experiment used separate UnityPy scripts, not this repository's core text extractor. See `docs/SUPPORTED_GAMES.md` for the exact scope and remaining issues.

The automated suite uses synthetic fixtures. It does not run a game executable, install a patch, or prove semantic translation quality or in-game font/rendering behavior. Arabic is the only language with dedicated RTL checks and test-suite coverage; other target languages remain unverified.

## Manual Handoff coverage

- Refuses to create an empty handoff package when batches or the normalized source are missing.
- Verifies normalized-source and batch SHA-256 hashes, entry counts, unique IDs and exact source-to-batch coverage.
- Rejects tampered batches before writing an output package.
- Excludes files not listed in the verified batch manifest.
- Includes the translator guide and declared translation batches while excluding normalized full-source files, reports, local scripts and game files.
- Redacts the normalized source's absolute local path from the copied batch manifest.
- Verifies ZIP integrity and package manifest hashes.
- Enforces safe replacement rules for previously generated handoff packages.

## Scope and limitations

- Manual Handoff is manual file transfer, not an API integration. It requires no API key or paid API, but the chosen chat service's own free-tier, context and upload limits still apply.
- The original game folder and binary archives are not part of the handoff package.
- The handoff workflow accepts normalized JSON batches. Godot .po files can be detected as localization candidates but are not yet parsed by the core extractor; gettext support remains a separate adapter task.
- A successful structural validator does not prove semantic accuracy or in-game rendering.
- No game executable or patch installer is run by the test suite.
