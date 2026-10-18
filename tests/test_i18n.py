"""UI language is a preference, independent from speech and private content."""

import ast
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, replace
from pathlib import Path
from string import Formatter

import pytest
from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication
from test_settings import Credentials

from look_to_ask.i18n import install_language, resolve_language, tr
from look_to_ask.settings import AppSettings, SettingsError, SettingsStore, credential_target


def test_system_locale_and_explicit_ui_choices():
    previous = QLocale()
    try:
        QLocale.setDefault(QLocale("en_CA"))
        assert resolve_language("system") == "en"
        assert resolve_language("zh") == "zh"
        QLocale.setDefault(QLocale("zh_TW"))
        assert resolve_language("system") == "zh"
        assert resolve_language("en") == "en"
    finally:
        QLocale.setDefault(previous)


def test_old_config_keeps_chinese_new_install_follows_system(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    assert store.load().ui_language == "system"
    store.path.write_text('{"speech_model":"base","language":"en"}', "utf-8")
    assert store.load().ui_language == "zh"
    assert store.load().language == "en"
    store.path.write_text('{"ui_language":"unknown"}', "utf-8")
    assert store.load() == AppSettings() and store.warning


def test_language_save_never_accesses_vault_and_preserves_preferences(tmp_path):
    class ForbiddenVault:
        def __getattr__(self, name):
            raise AssertionError(f"Language changes must not access credentials: {name}")

    store = SettingsStore(tmp_path / "settings.json", credentials=ForbiddenVault())
    original = AppSettings(
        camera_index=2,
        camera_resolution=(1920, 1080),
        remember_key=True,
        api_base_url="https://example.test/v1",
        api_model="vision",
        language="zh",
    )
    store.path.write_text(json.dumps(asdict(original)), "utf-8")
    store.save_ui_language("en")
    assert store.load() == replace(original, ui_language="en")
    assert "api_key" not in store.path.read_text("utf-8")
    with pytest.raises(SettingsError):
        store.save_ui_language("unknown")
    assert store.load() == replace(original, ui_language="en")


def test_qt_catalog_translates_templates_but_not_user_content():
    app = QApplication.instance() or QApplication([])
    install_language("en")
    assert tr("开始校准") == "Start calibration"
    install_language("zh")
    assert tr("开始校准") == "开始校准"
    assert app is QApplication.instance()


def test_language_choice_is_saved_for_restart_without_changing_speech(tmp_path):
    from look_to_ask.ui import ControlWindow

    app = QApplication.instance() or QApplication([])
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    store.save(AppSettings(ui_language="zh"), "")
    window = ControlWindow(settings_store=store)
    try:
        window.ui_language_selector.setCurrentIndex(window.ui_language_selector.findData("en"))
        assert store.load().ui_language == "en"
        assert window.start_button.text() == "开始校准"
        assert window.ask.dialog.language_selector.currentData() == "zh"
        window._save_settings()
        assert store.load().ui_language == "en"
    finally:
        window.close()
        app.processEvents()
    reopened = ControlWindow(settings_store=store)
    try:
        assert reopened.start_button.text() == "Start calibration"
        assert reopened.ask.dialog.language_selector.currentData() == "zh"
        private_text = "这个错误是什么？ PRIVATE QUESTION"
        reopened.ask.dialog.question_edit.setPlainText(private_text)
        assert reopened.ask.dialog.question_edit.toPlainText() == private_text
    finally:
        reopened.close()
        install_language("zh")
        app.processEvents()


def test_language_write_failure_keeps_current_choice_and_reports_failure(tmp_path, monkeypatch):
    from look_to_ask.ui import ControlWindow

    app = QApplication.instance() or QApplication([])
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    store.save(AppSettings(ui_language="zh"), "")
    window = ControlWindow(settings_store=store)

    def fail(_language):
        raise SettingsError("TEST language save failure")

    monkeypatch.setattr(store, "save_ui_language", fail)
    try:
        window.ui_language_selector.setCurrentIndex(window.ui_language_selector.findData("en"))
        assert window.ui_language_selector.currentData() == "zh"
        assert store.load().ui_language == "zh"
        assert window.ui_language_hint.text() == "TEST language save failure"
    finally:
        window.close()
        app.processEvents()


def test_ui_only_preference_keeps_environment_provider_across_restarts(tmp_path, monkeypatch):
    from look_to_ask.ui import ControlWindow

    monkeypatch.setattr("look_to_ask.ui.list_cameras", lambda: [])
    monkeypatch.setenv("LOOK_TO_ASK_API_BASE_URL", "https://environment.example/v1")
    monkeypatch.setenv("LOOK_TO_ASK_API_MODEL", "environment-vision")
    monkeypatch.setenv("LOOK_TO_ASK_API_KEY", "TEST-ONLY-ENV-KEY")
    app = QApplication.instance() or QApplication([])
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    for choice in ("en", "zh", "system"):
        window = ControlWindow(settings_store=store)
        try:
            assert window.ask.dialog.base_url_edit.text() == "https://environment.example/v1"
            assert window.ask.dialog.model_edit.text() == "environment-vision"
            assert window.ask.dialog.key_edit.text() == "TEST-ONLY-ENV-KEY"
            window.ui_language_selector.setCurrentIndex(
                window.ui_language_selector.findData(choice)
            )
            assert store.load().ui_language == choice
        finally:
            window.close()
            app.processEvents()
    assert "api_base_url" not in json.loads(store.path.read_text("utf-8"))
    assert "TEST-ONLY-ENV-KEY" not in store.path.read_text("utf-8")


def test_partial_legacy_config_does_not_restore_a_key_for_another_endpoint(tmp_path, monkeypatch):
    from look_to_ask.ui import ControlWindow

    monkeypatch.setattr("look_to_ask.ui.list_cameras", lambda: [])
    monkeypatch.setenv("LOOK_TO_ASK_API_BASE_URL", "https://environment.example/v1")
    monkeypatch.setenv("LOOK_TO_ASK_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    credentials = Credentials()
    credentials.write(credential_target("https://api.openai.com/v1"), "OTHER-PROVIDER-TEST-KEY")
    store = SettingsStore(tmp_path / "settings.json", credentials=credentials)
    store.path.write_text('{"remember_key":true,"ui_language":"zh"}', "utf-8")
    app = QApplication.instance() or QApplication([])
    window = ControlWindow(settings_store=store)
    try:
        assert window.ask.dialog.base_url_edit.text() == "https://environment.example/v1"
        assert window.ask.dialog.key_edit.text() == ""
        assert credentials.read(credential_target("https://api.openai.com/v1"))
    finally:
        window.close()
        app.processEvents()


def test_invalid_unused_environment_url_does_not_block_saved_key(tmp_path, monkeypatch):
    from look_to_ask.ui import ControlWindow

    monkeypatch.setattr("look_to_ask.ui.list_cameras", lambda: [])
    monkeypatch.setenv("LOOK_TO_ASK_API_BASE_URL", "invalid-unused-url")
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    store.save(AppSettings(api_model="vision", remember_key=True), "TEST-ONLY-SAVED-KEY")
    app = QApplication.instance() or QApplication([])
    window = ControlWindow(settings_store=store)
    try:
        assert window.ask.dialog.base_url_edit.text() == "https://api.openai.com/v1"
        assert window.ask.dialog.key_edit.text() == "TEST-ONLY-SAVED-KEY"
    finally:
        window.close()
        app.processEvents()


def test_catalog_is_complete_matches_runtime_and_preserves_format_fields():
    app = QApplication.instance() or QApplication([])
    package = Path(__file__).resolve().parents[1] / "src/look_to_ask"
    sources = set()
    for path in package.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
            ):
                assert isinstance(node.args[0], ast.Constant), (path, node.lineno)
                sources.add(node.args[0].value)
    catalog = ET.parse(package / "translations/en.ts")
    messages = catalog.findall(".//message")
    assert {m.findtext("source") for m in messages} == sources

    def fields(text):
        return sorted(
            (name, spec, conversion)
            for _, name, spec, conversion in Formatter().parse(text)
            if name is not None
        )

    install_language("en")
    for message in messages:
        source = message.findtext("source")
        translation = message.find("translation")
        assert translation.get("type") is None and translation.text, source
        assert fields(source) == fields(translation.text), source
        assert tr(source) == translation.text, "Recompile the QM catalog: " + source
    assert app is QApplication.instance()


def test_english_ui_preserves_question_answer_and_gaze_payload():
    from PySide6.QtGui import QColor, QImage

    from look_to_ask.ask import AskDialog
    from look_to_ask.calibration import ScreenRect
    from look_to_ask.context import build_context
    from look_to_ask.vision import ApiConfig, build_payload, parse_response

    app = QApplication.instance() or QApplication([])
    image = QImage(1920, 1080, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    snapshot = build_context(image, ScreenRect(0, 0, 1920, 1080), (1600, 900))
    question = "这个是什么意思？ What does this mean?"
    config = ApiConfig("https://example.test/v1", "vision")
    install_language("zh")
    original = build_payload(config, snapshot, question)
    install_language("en")
    assert build_payload(config, snapshot, question) == original
    dialog = AskDialog()
    try:
        dialog.set_context(snapshot)
        dialog.question_edit.setPlainText(question)
        answer = "PRIVATE 回答: 保持原文"
        raw = json.dumps({"choices": [{"message": {"content": answer}}]})
        dialog.answer_view.setPlainText(parse_response(raw))
        assert dialog.question_edit.toPlainText() == question
        assert dialog.answer_view.toPlainText() == answer
        assert "automatically" in dialog.disclosure.text().lower()
        assert "full screen" in dialog.disclosure.text().lower()
        assert str(snapshot.geometry.gaze_in_roi) in dialog.status_label.text()
    finally:
        dialog.close()
        app.processEvents()
