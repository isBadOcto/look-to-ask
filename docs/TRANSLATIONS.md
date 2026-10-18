# Interface translations

Look to Ask supports English and Simplified Chinese. The main window always exposes a bilingual
**Language / 语言** selector. Changes save immediately, without accessing credentials, and apply on
next launch. This keeps running calibration, recordings and requests intact. New installs follow
the system locale (Chinese → Simplified Chinese; other locales → English). Older configurations
retain Chinese until the user chooses otherwise.

`settings.AppSettings.ui_language` stores `system`, `zh`, or `en`. The separate `language` setting
controls speech recognition. Changing one must never change the other.

## Files

- `src/look_to_ask/i18n.py`: locale resolution, Qt translator lifetime, and `tr()` for app text.
- `src/look_to_ask/translations/en.ts`: editable Qt XML catalog with Chinese source and English text.
- `src/look_to_ask/translations/en.qm`: compiled public runtime catalog, included in source/wheel and
  frozen packages. Keep it with the source so a fresh checkout can start without translation tools.
- `scripts/translations.py`: update source references or compile the reviewed catalog using the
  `pyside6-lrelease` tool already supplied by the pinned PySide6 dependency.
- `tests/test_i18n.py`: migration, preference isolation, restart behavior, write failure, full catalog
  coverage/format fields and runtime text, and preservation of question/answer/gaze payload.

## Change wording

Use literal Chinese source text for app-owned messages: `tr("开始校准")`. For variable text, translate
the template before formatting, for example `tr("校准编号 {id}", id=calibration_id)`. Keep format fields
and numeric specifications intact. Never pass user questions, transcripts, model answers, API keys,
camera names or provider content through `tr()`. UI translations must not alter API grounding prompts.
Use complete phrases rather than assembling translated word fragments.

```powershell
.\.venv\Scripts\python.exe scripts/translations.py update
# Edit translations/en.ts. Finish new entries; preserve placeholders and meaningful newlines.
.\.venv\Scripts\python.exe scripts/translations.py compile
.\.venv\Scripts\python.exe -m pytest tests/test_i18n.py -q
.\.venv\Scripts\python.exe -m ruff check .
```

The updater retains existing translations and marks new entries unfinished. Compilation rejects
unfinished entries and mismatched format fields. Tests also compare the compiled QM against TS text
and current source messages, detecting stale catalogs. The Windows build compiles the catalog again
and includes both files; no translation service or network access is used at runtime.

For another language, add a reviewed TS/QM catalog, register its code and displayed name in `i18n.py`
and the UI selector, extend locale resolution/catalog compilation and add tests. Catalog files alone
do not register a new language. Keep the bilingual language selector discoverable.

## Manual checks

Choose English, quit, reopen, and inspect controls, settings, privacy disclosures, calibration
instructions, independent accuracy reports and error messages. Switch back to Simplified Chinese and
repeat. Recognition language/model, camera and API preferences should stay unchanged. Ask a Mandarin
question in the English interface and verify the transcript and answer are not translated by the UI.
At 100%, 125% and 150% Windows scaling, check wrapping, scrolling and access to Quit and Send.
