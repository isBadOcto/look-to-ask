"""Small Qt translation boundary. Language changes take effect on next launch."""

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLocale, QTranslator

UI_LANGUAGES = ("system", "zh", "en")
_translator = None


def resolve_language(preference):
    if preference not in UI_LANGUAGES:
        raise ValueError("Unsupported UI language")
    if preference == "system":
        return "zh" if QLocale().language() == QLocale.Language.Chinese else "en"
    return preference


def install_language(preference):
    global _translator
    app = QCoreApplication.instance()
    if app is None:
        raise RuntimeError("Create QApplication before installing translations")
    if _translator is not None:
        app.removeTranslator(_translator)
        _translator = None
    language = resolve_language(preference)
    if language == "en":
        translator = QTranslator(app)
        path = Path(__file__).parent / "translations/en.qm"
        if not translator.load(str(path)):
            raise RuntimeError("English translation catalog is missing or invalid")
        app.installTranslator(translator)
        _translator = translator
    return language


def tr(source, **values):
    """Translate app-owned templates only; values (including user text) stay intact."""
    translated = QCoreApplication.translate("LookToAsk", source)
    return translated.format(**values) if values else translated
