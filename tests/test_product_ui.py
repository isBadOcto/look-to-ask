from PySide6.QtWidgets import QApplication
from test_settings import Credentials

from look_to_ask.settings import AppSettings, SettingsStore
from look_to_ask.ui import ControlWindow


def test_licenses_are_readable_without_capture_or_device_start(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("look_to_ask.ui.list_cameras", lambda: [])
    window = ControlWindow(
        settings_store=SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    )
    window.licenses_button.click()
    dialog = window.ask.dialog
    assert dialog.tabs.currentWidget() is dialog.license_view
    assert "LGPL" in dialog.license_view.toPlainText()
    assert "Independent JPEG Group" in dialog.license_view.toPlainText()
    assert dialog.snapshot is None and window.worker is None
    assert not window.voice.recorder.active
    window.close()
    app.processEvents()


def test_default_speech_settings_show_medium_and_mandarin_without_opening_microphone(
    tmp_path, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("look_to_ask.ui.list_cameras", lambda: [])
    window = ControlWindow(
        settings_store=SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    )
    assert window.ask.dialog.speech_model_edit.text() == "medium"
    assert window.ask.dialog.language_selector.currentData() == "zh"
    assert not window.voice.recorder.active
    window.close()
    app.processEvents()


def test_camera_selection_persists_and_is_locked_until_camera_stops(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("look_to_ask.ui.list_cameras", lambda: [(0, "Built-in"), (2, "USB Camera")])
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    window = ControlWindow(settings_store=store)
    window.camera_selector.setCurrentIndex(window.camera_selector.findData(2))
    window.ask.dialog.model_edit.setText("vision")
    window.ask.dialog.key_edit.setText("PRIVATE-KEY")
    window._save_settings()
    assert store.load().camera_index == 2
    assert "PRIVATE-KEY" not in store.path.read_text("utf-8")
    window._calibration_finished()
    assert not window.camera_selector.isEnabled()
    window._worker_finished()
    assert window.camera_selector.isEnabled()
    window.close()
    app.processEvents()


def test_saved_api_and_optional_key_restore_without_starting_devices(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("look_to_ask.ui.list_cameras", lambda: [])
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    store.save(AppSettings(api_model="custom-vision", remember_key=True), "PRIVATE-KEY")
    window = ControlWindow(settings_store=store)
    assert window.ask.dialog.model_edit.text() == "custom-vision"
    assert window.ask.dialog.key_edit.text() == "PRIVATE-KEY"
    assert window.worker is None and not window.voice.recorder.active
    assert window.advanced_panel.isHidden()
    window.close()
    app.processEvents()


def test_changing_endpoint_clears_old_provider_key_and_remember_choice(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("look_to_ask.ui.list_cameras", lambda: [])
    window = ControlWindow(
        settings_store=SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    )
    dialog = window.ask.dialog
    dialog.key_edit.setText("TEST-ONLY-KEY")
    dialog.remember_key.setChecked(True)
    dialog.base_url_edit.setText("https://another.example/v1")
    assert dialog.key_edit.text() == "" and not dialog.remember_key.isChecked()
    window.close()
    app.processEvents()


def test_environment_key_is_not_reused_for_a_different_saved_endpoint(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("look_to_ask.ui.list_cameras", lambda: [])
    monkeypatch.setenv("LOOK_TO_ASK_API_BASE_URL", "https://original.example/v1")
    monkeypatch.setenv("LOOK_TO_ASK_API_KEY", "ENV-TEST-ONLY-KEY")
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    store.save(AppSettings(api_base_url="https://different.example/v1"), "")
    window = ControlWindow(settings_store=store)
    assert window.ask.dialog.key_edit.text() == ""
    window.close()
    app.processEvents()


def test_environment_key_is_available_for_the_same_canonical_endpoint(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("look_to_ask.ui.list_cameras", lambda: [])
    monkeypatch.setenv("LOOK_TO_ASK_API_BASE_URL", "https://same.example/v1/")
    monkeypatch.setenv("LOOK_TO_ASK_API_KEY", "ENV-TEST-ONLY-KEY")
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    store.save(AppSettings(api_base_url="https://same.example/v1"), "")
    window = ControlWindow(settings_store=store)
    assert window.ask.dialog.key_edit.text() == "ENV-TEST-ONLY-KEY"
    window.close()
    app.processEvents()
