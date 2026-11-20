# Universal Game Localization Skill

[![selftest](https://github.com/ADMOSSx/Universal-Game-Localization/actions/workflows/selftest.yml/badge.svg)](https://github.com/ADMOSSx/Universal-Game-Localization/actions/workflows/selftest.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**English** | [العربية](#العربية)

A lightweight [OpenCode](https://opencode.ai) skill that helps you **prepare any game for translation** (built with Arabic/RTL in mind): inspect the game folder, detect the engine, extract text, split it into translation batches, validate the result, and build a patch - while spending as few AI tokens as possible.

It is designed for people on **free AI limits**: the skill file is ~4 KB, the heavy work is done by plain Python scripts (zero tokens), and the actual translation is meant to happen in any free chat AI of your choice, not inside the agent.

> This is a preparation toolkit, **not** a magic extractor. Plain-text formats work out of the box; binary/proprietary formats (`.pak`, `.upk`, `.assets`, ...) need an external tool, and the skill will tell you so instead of guessing.

## How it works

```
game folder --inventory--> engine hints --extract_text--> strings.json --split_batches--> batches
                                                                                             |
                      patch (translated copies) <--inject_text-- merged <--merge/validate<-- translated by any AI
```

1. **Inventory** - read-only scan, compact summary + engine hints.
2. **Extract** - `.ini .int .properties .lng .json .csv .tsv .txt` to a normalized `strings.json`.
3. **Batch** - small, ID-stable JSON batches (grouped by file, size-capped) + a ready handoff package.
4. **Translate** - you upload the batches to a free AI (or ask the agent to, if you have tokens to spare).
5. **Merge + validate** - by stable ID; catches broken placeholders, changed originals, encoding damage (mojibake), pre-shaped Arabic, length risks.
6. **Inject** - writes translated **copies** of the files (same encoding/BOM/line endings) with SHA-256 manifest. The game folder is never touched.

## Install

### Option 1 - one command (recommended)
Needs [Node.js](https://nodejs.org). Installs for OpenCode, globally, with no prompts:

```bash
npx skills add ADMOSSx/Universal-Game-Localization --skill universal-game-localization -g -a opencode -y
```

Drop `-g` to install into the current project only, or drop `-a opencode` to pick other agents interactively (the same CLI supports Claude Code, Codex, Cursor and more). It uses the open [`skills` CLI](https://github.com/vercel-labs/skills); that CLI collects anonymous usage stats (set `DO_NOT_TRACK=1` to disable). Restart OpenCode afterwards.

### Option 2 - let your AI agent install it
Paste this into OpenCode (or any coding agent):

> Install the agent skill from https://github.com/ADMOSSx/Universal-Game-Localization. Run `npx skills add ADMOSSx/Universal-Game-Localization --skill universal-game-localization -g -a opencode -y`. If npx is not available, clone the repo and copy the folder `skills/universal-game-localization` into `~/.config/opencode/skills/` (on Windows: `%USERPROFILE%\.config\opencode\skills\`). Then run `python scripts/selftest.py` inside that folder and tell me if it prints SELFTEST PASSED.

### Option 3 - manual
Download the repo (**Code -> Download ZIP**) and copy `skills/universal-game-localization` to `%USERPROFILE%\.config\opencode\skills\`, so `...\skills\universal-game-localization\SKILL.md` exists. Restart OpenCode.

### Use it
Ask:
> Use the universal-game-localization skill. Analyze this game folder: `D:\Games\MyGame`. Prepare it for Arabic localization. Do not modify the original game.

Per-project install (`.opencode/skills/`) also works; see the [OpenCode skills docs](https://opencode.ai/docs/skills).

Requires **Python 3.9+**. Check the scripts work on your machine:

```powershell
cd "%USERPROFILE%\.config\opencode\skills\universal-game-localization"
python scripts\selftest.py        # last line should be: SELFTEST PASSED
```

## Scripts (no AI tokens used)

| Script | Purpose |
|---|---|
| `inventory.py` | Read-only folder audit: extensions, magic bytes, engine hints, localization candidates, fonts, archives |
| `extract_text.py` | Plain-text formats -> `normalized/strings.json` + `files.json` |
| `split_batches.py` | Batches by count/characters, optional `--group-by source_file`, manifest with hashes |
| `merge_translations.py` | Merge returned batches by ID (tolerates ```json fences; stops on unknown IDs / changed originals) |
| `validate_translations.py` | QA: placeholders/markup, mojibake, whitespace, untranslated text, Arabic-specific checks, length |
| `inject_text.py` | Build translated copies + `PATCH_MANIFEST.json` (reversible install data) |
| `make_handoff.py` | Build and verify a ZIP for another translator/AI (excludes binaries and secrets) |
| `selftest.py` | End-to-end self-test, including byte-for-byte round trips |

Typical run:

```powershell
python scripts\inventory.py "D:\Games\MyGame" --out localization-work\reports
python scripts\extract_text.py "D:\Games\MyGame" --out localization-work\normalized\strings.json
python scripts\split_batches.py localization-work\normalized\strings.json --out localization-work\translation_batches --group-by source_file
python scripts\make_handoff.py localization-work
:: ... translate the batches somewhere, put the returned files in returned_batches\ ...
python scripts\merge_translations.py localization-work\normalized\strings.json returned_batches --out merged.json
python scripts\validate_translations.py merged.json --source localization-work\normalized\strings.json
python scripts\inject_text.py merged.json --files localization-work\normalized\files.json --out localization-work\patch
```

## Limitations (honest list)

- Binary archives and proprietary formats are **not** extracted by the scripts.
- JSON/CSV files are re-serialized on injection (content kept; whitespace/quoting may change - the script warns).
- Arabic display depends on the game's font/text renderer. The skill gives a checklist and test strings, but **only an in-game test proves it works**.
- Engine detection is hint-based and never 100% certain.
- Online/multiplayer games with anti-cheat are out of scope; the skill stops and explains.

## Safety and legal

- The game folder is treated as read-only. Reports and output go to a separate workspace; scripts refuse to write inside the game folder.
- No automatic installs, no running unknown executables, no anti-cheat/DRM bypass.
- Extracted game text is copyrighted by its owners. Use it for your own localization work and do not publish it. Respect each game's license/EULA and local law.
- Not affiliated with or endorsed by OpenCode, Anthropic, or any game publisher.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The most useful help right now: **test on real games** and add results to [docs/SUPPORTED_GAMES.md](docs/SUPPORTED_GAMES.md). Changes: [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE)

---

<div dir="rtl">

## العربية

<a name="العربية"></a>

**Universal Game Localization Skill** هي skill خفيفة لـ [OpenCode](https://opencode.ai) تساعدك على **تجهيز أي لعبة للترجمة** (مع اهتمام خاص بالعربية واتجاه الكتابة من اليمين لليسار): فحص مجلد اللعبة، تحديد المحرك (engine)، استخراج النصوص، تقسيمها إلى دفعات (batches)، فحص الترجمة، وبناء باتش - مع استهلاك أقل قدر ممكن من التوكن.

صُممت للمستخدمين على **الحدود المجانية** للذكاء الاصطناعي: ملف الـ skill صغير (~4KB)، والعمل الثقيل تقوم به سكريبتات بايثون **بدون أي توكن**، والترجمة نفسها تتم في أي AI مجاني تختاره، وليس داخل الـ agent.

> هذه أداة تجهيز وليست استخراجًا سحريًا. الصيغ النصية العادية تعمل مباشرة، أما الصيغ الثنائية (`.pak` و`.upk` و`.assets`...) فتحتاج أداة خارجية، والـ skill ستخبرك بذلك بدل التخمين.

### طريقة العمل

1. **الجرد**: فحص للقراءة فقط مع ملخص مضغوط وتلميحات عن المحرك.
2. **الاستخراج**: من `.ini .int .properties .lng .json .csv .tsv .txt` إلى ملف `strings.json` موحّد.
3. **التقسيم**: دفعات صغيرة بمعرّفات ثابتة، مع حزمة تسليم جاهزة.
4. **الترجمة**: ترفع الدفعات إلى AI مجاني (أو تطلب من الـ agent إن كانت لديك توكنات كافية).
5. **الدمج والفحص**: حسب المعرّف؛ يكشف أخطاء المتغيرات (placeholders)، وتغيير النص الأصلي، وتلف الترميز، والحروف العربية المشكّلة مسبقًا، والنصوص الأطول من اللازم.
6. **الحقن**: يكتب **نسخًا** مترجمة من الملفات (بنفس الترميز ونهايات الأسطر) مع ملف checksums. مجلد اللعبة لا يُمَس أبدًا.

### التثبيت

**الطريقة 1 - أمر واحد (الأفضل):** تحتاج [Node.js](https://nodejs.org). هذا الأمر يثبّتها لـ OpenCode بشكل عام وبدون أسئلة:

```bash
npx skills add ADMOSSx/Universal-Game-Localization --skill universal-game-localization -g -a opencode -y
```

احذف `-g` للتثبيت داخل المشروع الحالي فقط. ثم أعد تشغيل OpenCode.

**الطريقة 2 - اجعل الـ AI يثبّتها:** الصق في OpenCode هذه الرسالة:

> ثبّت الـ skill من https://github.com/ADMOSSx/Universal-Game-Localization بتشغيل `npx skills add ADMOSSx/Universal-Game-Localization --skill universal-game-localization -g -a opencode -y`. وإن لم يتوفر npx فاستنسخ المستودع وانسخ المجلد `skills/universal-game-localization` إلى `%USERPROFILE%\.config\opencode\skills\`. ثم شغّل `python scripts/selftest.py` داخل المجلد وأخبرني هل ظهر SELFTEST PASSED.

**الطريقة 3 - يدويًا:** حمّل المستودع (Download ZIP) وانسخ `skills/universal-game-localization` إلى `%USERPROFILE%\.config\opencode\skills\` ثم أعد تشغيل OpenCode.

بعد التثبيت اكتب:
> Use the universal-game-localization skill. Analyze this game folder: `D:\Games\MyGame`. Prepare it for Arabic localization. Do not modify the original game.

يتطلب **Python 3.9 أو أحدث**. للتأكد أن السكريبتات تعمل: شغّل `python scripts\selftest.py` داخل مجلد الـ skill، ويجب أن يظهر `SELFTEST PASSED` في آخر سطر.

### حدود يجب معرفتها

- الأرشيفات الثنائية والصيغ الخاصة لا تستخرجها السكريبتات.
- ملفات JSON وCSV يُعاد كتابتها عند الحقن (المحتوى سليم، لكن المسافات أو علامات الاقتباس قد تتغير، وسيحذّرك السكريبت).
- ظهور العربية صحيحًا يعتمد على خط اللعبة ومحرك عرض النص. **التجربة داخل اللعبة هي الدليل الوحيد.**
- الألعاب الأونلاين التي تستخدم حماية (anti-cheat) خارج النطاق.

### الأمان والقانون

- مجلد اللعبة للقراءة فقط، والسكريبتات ترفض الكتابة داخله.
- لا تثبيت تلقائي، ولا تشغيل لملفات تنفيذية مجهولة، ولا تجاوز لحماية اللعبة.
- نصوص اللعبة المستخرجة محمية بحقوق أصحابها: استخدمها لعملك الشخصي ولا تنشرها، والتزم بشروط اللعبة والقوانين المحلية.
- المشروع غير تابع لـ OpenCode أو Anthropic أو أي ناشر ألعاب.

### المساهمة

اقرأ [CONTRIBUTING.md](CONTRIBUTING.md). أكثر مساعدة مفيدة الآن: **جرّب على ألعاب حقيقية** وأضف نتيجتك في [docs/SUPPORTED_GAMES.md](docs/SUPPORTED_GAMES.md).

</div>
