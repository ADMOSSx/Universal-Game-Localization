# Release verification — 1.3.0

Date: 2026-11-25

## Verification scope

The v1.3.0 CI release workflow checks the package manifest, compiles all Python helpers, runs the full helper regression suite, and runs the Unity/Unreal/Godot adapter self-test on:

- Ubuntu 24.04 + Python 3.10
- Ubuntu 24.04 + Python 3.12
- Windows + Python 3.10
- Windows + Python 3.12

The release workflow publishes only after all matrix jobs succeed. See the GitHub Actions run linked from the v1.3.0 release for the actual result.

## Manual Handoff regression coverage

The full synthetic self-test covers:
- Refusal to create an empty handoff package when batches or the normalized source are missing.
- SHA-256, ID-set, entry-count and batch-manifest preflight checks.
- Rejection of tampered batches before any output package is written.
- Exclusion of files not listed in the verified batch manifest.
- Inclusion of the translator guide and only the declared translation batches; exclusion of normalized full-source files, reports, local scripts and game files.
- Redaction of the normalized source's absolute local path from the copied batch manifest.
- Rendering of source/target language and game metadata in handoff instructions.
- ZIP integrity and manifest hash verification.
- Safe replacement rules for previously generated handoff packages.

## Scope and limitations

- Manual Handoff is a manual file-transfer workflow, not an API integration. It requires no API key or paid API, but the chosen chat service's own free-tier, context and file-upload limits still apply.
- The original game folder and binary archives are not part of the handoff package.
- The handoff workflow accepts normalized JSON batches. Godot .po files can be detected as localization candidates but are not yet parsed by the core extractor; gettext support remains a separate adapter task.
- A successful structural validator does not prove semantic translation quality or in-game rendering.
- No game executable or patch installer is run by the test suite; the suite uses synthetic files.
