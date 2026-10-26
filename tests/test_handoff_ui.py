"""Background handoff fixtures, never hardware gaze or actual Codex submissions."""

import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from test_ask import dispose, drain, prepare
from test_voice import Recorder, stable

from look_to_ask.screen_context import build_screen_context
from look_to_ask.settings import AppSettings, SettingsStore
from look_to_ask.ui import ControlWindow

THREAD = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize("xs,expected", [([100, 900, 100, 900, 100, 900], 500), ([350], 350)])
def test_codex_voice_freezes_real_recent_gaze_without_stability_gate(monkeypatch, xs, expected):
    app, window, voice, jobs, sends, points = setup_codex(monkeypatch)
    now = time.monotonic()
    for index, x in enumerate(xs):
        window.ask.gaze.update(x, 400, now - (len(xs) - index - 1) * 0.04)
    assert voice.press()
    voice.release()
    drain()
    voice.engine.transcribed.emit(jobs[-1][0], "fixture question", 10)
    assert points == [(expected, 400)]
    assert len(sends) == 1 and sends[0][1].geometry.gaze_global == (expected, 400)
    window.ask.codex_client.completed.emit("fixture-queue")
    dispose(window)
    app.processEvents()


@pytest.mark.parametrize("stale", [False, True])
def test_codex_still_requires_a_fresh_real_gaze_prediction(monkeypatch, stale):
    app, window, voice, jobs, sends, points = setup_codex(monkeypatch)
    if stale:
        window.ask.gaze.update(300, 400, time.monotonic() - 1)
    assert not voice.press()
    assert not voice.recorder.active and not jobs and not sends and not points
    dispose(window)
    app.processEvents()


def test_screen_capture_hides_own_ui_and_marker_without_window_lookup(monkeypatch):
    app, window, _voice, _jobs, _sends, points = setup_codex(monkeypatch)
    window.show()
    window.marker_debug.setChecked(True)
    stable(window)
    assert window.marker.isVisible()

    def forbidden(*_args):
        raise AssertionError("Application lookup must not run")

    window.ask.window_target_factory = forbidden
    assert window.ask.trigger()
    drain()
    assert points == [(300, 400)]
    assert window.ask.dialog.snapshot.geometry.roi_bounds == (0, 0, 1000, 800)
    dispose(window)
    app.processEvents()


def test_voice_preserves_specific_capture_failure_without_sending(monkeypatch):
    app, window, voice, _jobs, sends, _points = setup_codex(monkeypatch)
    messages = []
    voice.status.connect(messages.append)

    def reject(*_args):
        raise ValueError("fixture screenshot rejected")

    window.ask.screen_capture_factory = reject
    stable(window)
    assert voice.press()
    drain()
    assert not voice.active and not voice.recorder.active and not sends
    assert messages[-1] == "fixture screenshot rejected"
    assert "fixture screenshot rejected" not in window.ask.log.text
    dispose(window)
    app.processEvents()


def test_destination_settings_persist_without_touching_credentials(tmp_path):
    assert "destination" in AppSettings.__dataclass_fields__

    class NoVault:
        def __getattr__(self, name):
            raise AssertionError("Destination preferences must not access credentials")

    store = SettingsStore(tmp_path / "prefs.json", credentials=NoVault())
    store.save_destination("codex", "codex://threads/" + THREAD, "")
    saved = store.load()
    assert saved.destination == "codex" and saved.codex_thread == THREAD
    assert not saved.api_model and not saved.remember_key
    saved.validate()


def setup_codex(monkeypatch):
    app, window = prepare()
    dialog = window.ask.dialog
    assert hasattr(dialog, "destination_selector")
    dialog.destination_selector.setCurrentIndex(dialog.destination_selector.findData("codex"))
    dialog.codex_thread_edit.setText("codex://threads/" + THREAD)
    monkeypatch.setattr("look_to_ask.codex_handoff.locate_codex", lambda: "C:/fixture/codex.exe")
    dialog.codex_executable_edit.clear()
    dialog.model_edit.clear()
    dialog.key_edit.clear()
    voice = window.voice
    voice.recorder = Recorder()
    voice.engine.loaded_name = dialog.speech_model_edit.text()
    jobs, sends, points = [], [], []
    monkeypatch.setattr(voice.engine, "transcribe", lambda *args: jobs.append(args))
    monkeypatch.setattr(window.ask.codex_client, "send", lambda *args: sends.append(args))
    monkeypatch.setattr(
        window.ask.client, "send", lambda *_args: (_ for _ in ()).throw(AssertionError("API used"))
    )
    image = QImage(1000, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("cyan"))

    def capture(screen, point):
        assert not window.marker.isVisible() and not window.ask.dialog.isVisible()
        points.append(point)
        return build_screen_context(image, screen, point)

    window.ask.screen_capture_factory = capture
    return app, window, voice, jobs, sends, points


def test_three_background_voice_handoffs_freeze_point_and_never_open_preview(monkeypatch):
    app, window, voice, jobs, sends, points = setup_codex(monkeypatch)
    window.show()
    window.tray.minimize()
    assert window.tray.background
    for i in range(3):
        stable(window)
        assert voice.press()
        stable(window, x=700)
        voice.release()
        drain()
        voice.engine.transcribed.emit(jobs[-1][0], f"fixture question {i}", 10)
        assert len(sends) == i + 1 and points[-1] == (300, 400)
        assert not window.ask.dialog.isVisible() and not window.marker.isVisible()
        assert not window.isVisible() or window.windowState() & Qt.WindowState.WindowMinimized
        config, snapshot, question = sends[-1]
        assert config.thread_id == THREAD and snapshot.geometry.gaze_global == (300, 400)
        assert question == f"fixture question {i}"
        window.ask.codex_client.completed.emit("queue-fixture")
        assert not voice.active and not voice.recorder.active
        assert window.ask.dialog.snapshot is None
    assert "fixture question" not in window.ask.log.text
    dispose(window)
    app.processEvents()


def test_background_cancel_drops_late_transcription_and_stays_hidden(monkeypatch):
    app, window, voice, jobs, sends, _points = setup_codex(monkeypatch)
    window.tray.minimize()
    stable(window)
    assert voice.press()
    voice.release()
    identity = jobs[-1][0]
    voice.cancel()
    drain()
    voice.engine.transcribed.emit(identity, "late fixture", 10)
    assert not sends and not window.ask.dialog.isVisible()
    assert window.tray.background
    dispose(window)
    app.processEvents()


def test_mode_change_rejects_mismatched_window_and_api_snapshot(monkeypatch):
    app, window, voice, jobs, sends, _points = setup_codex(monkeypatch)
    stable(window)
    assert window.ask.trigger()
    drain()
    window.ask.dialog.destination_selector.setCurrentIndex(0)
    window.ask.dialog.model_edit.setText("fixture-model")
    assert not window.ask._send(window.ask.dialog.api_config(), "fixture")
    assert not sends
    dispose(window)
    app.processEvents()


def test_background_exit_waiting_for_native_speech_does_not_restore_window(monkeypatch):
    app, window = prepare()
    window.worker = None
    window.tray.available = True  # Simulate a real Windows tray, not offscreen taskbar fallback.
    window.tray.minimize()
    monkeypatch.setattr(window.voice.engine, "shutdown", lambda: None)
    monkeypatch.setattr(window.voice.engine, "isRunning", lambda: True)
    window.close()
    assert not window.isVisible() or window.isMinimized()
    monkeypatch.setattr(window.voice.engine, "isRunning", lambda: False)
    window.close()
    app.processEvents()


def test_synchronous_codex_failure_preserves_error_and_releases_voice(monkeypatch):
    app, window, voice, jobs, _sends, _points = setup_codex(monkeypatch)
    window.tray.minimize()

    def fail(*_args):
        window.ask.codex_client.failed.emit("fixture process could not start", "process_error")

    monkeypatch.setattr(window.ask.codex_client, "send", fail)
    stable(window)
    assert voice.press()
    voice.release()
    drain()
    voice.engine.transcribed.emit(jobs[-1][0], "fixture", 10)
    assert not voice.active and not window.ask.reserved
    assert not window.ask.dialog.cancel_button.isEnabled()
    assert "fixture process could not start" in window.status_label.text()
    dispose(window)
    app.processEvents()


def test_returning_to_api_restores_endpoint_bound_remembered_key(tmp_path):
    from dataclasses import replace

    from look_to_ask.settings import credential_target

    class Vault:
        def __init__(self):
            self.keys = {}

        def read(self, target):
            return self.keys.get(target, "")

        def write(self, target, value):
            self.keys[target] = value

        def delete(self, target):
            self.keys.pop(target, None)

    vault = Vault()
    store = SettingsStore(tmp_path / "preferences.json", credentials=vault)
    prefs = AppSettings(api_model="fixture-model", remember_key=True)
    store.save(prefs, "fixture-secret")
    store.save_preferences(replace(prefs, destination="codex", codex_thread=THREAD))
    app, temporary = prepare()
    dispose(temporary)
    window = ControlWindow(settings_store=store)
    dialog = window.ask.dialog
    assert not dialog.key_edit.text()
    dialog.destination_selector.setCurrentIndex(dialog.destination_selector.findData("api"))
    assert dialog.key_edit.text() == "fixture-secret"
    window._save_settings()
    assert vault.keys[credential_target(prefs.api_base_url)] == "fixture-secret"
    dispose(window)
    app.processEvents()
