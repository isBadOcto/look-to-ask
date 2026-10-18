"""Voice turn fixtures; no actual microphone or external AI calls."""

import threading
import time

import numpy as np
import pytest
from PySide6.QtGui import QColor, QImage
from test_ask import dispose, drain, prepare

from look_to_ask.context import build_context
from look_to_ask.speech import SpeechError


class Recorder:
    MAX_SECONDS = 30
    active = False
    fault = False

    def start(self):
        self.active = True

    def stop(self):
        self.active = False
        return np.zeros(16000, np.float32), 1.0

    def cancel(self):
        self.active = False


def configure(monkeypatch):
    app, window = prepare()
    voice = window.voice
    voice.recorder = Recorder()
    voice.engine.loaded_name = window.ask.dialog.speech_model_edit.text()
    window.ask.dialog.model_edit.setText("test-vision")
    image = QImage(1000, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("green"))
    window.ask.capture_factory = lambda screen, point: build_context(image, screen, point)
    jobs, sends = [], []
    monkeypatch.setattr(voice.engine, "transcribe", lambda *args: jobs.append(args))
    monkeypatch.setattr(window.ask.client, "send", lambda *args: sends.append(args))
    return app, window, voice, jobs, sends


def stable(window, x=300):
    now = time.monotonic()
    window.ask.gaze.clear()
    for i in range(6):
        window._on_gaze(x, 400, now - 0.2 + i * 0.04)


def test_voice_reports_actual_gpu_backend_and_late_cpu_fallback(monkeypatch):
    app, window, voice, jobs, sends = configure(monkeypatch)
    statuses = []
    voice.status.connect(statuses.append)
    voice.engine.device, voice.engine.compute_type = "cuda", "float16"
    voice._prepared("medium", 100)
    assert "GPU" in statuses[-1] and '"speech_device": "cuda"' in window.ask.log.text
    stable(window)
    assert voice.press()
    voice.release()
    voice.engine.device, voice.engine.compute_type = "cpu", "int8"
    voice.engine.fallback_reason = "gpu_inference_failed"
    voice.engine.transcribed.emit(jobs[-1][0], "原始问题", 123)
    drain()
    assert len(sends) == 1 and sends[0][2] == "原始问题"
    assert '"speech_fallback": "gpu_inference_failed"' in window.ask.log.text
    assert "回退 CPU" in statuses[-1]
    window.ask.client.completed.emit("fixture answer")
    dispose(window)
    app.processEvents()


def test_voice_signal_diagnostics_warn_without_rewriting_or_logging_the_question(monkeypatch):
    app, window, voice, jobs, sends = configure(monkeypatch)
    statuses = []
    voice.status.connect(statuses.append)
    voice.recorder.signal_stats = {
        "input_rate": 44100,
        "rms_dbfs": -52.5,
        "peak_dbfs": -32.1,
        "full_scale_fraction": 0,
    }
    stable(window)
    assert voice.press()
    voice.release()
    voice.engine.transcribed.emit(jobs[-1][0], "PRIVATE-QUESTION", 123)
    drain()
    assert len(sends) == 1 and sends[0][2] == "PRIVATE-QUESTION"
    assert any("音量较低" in text for text in statuses)
    assert '"rms_dbfs": -52.5' in window.ask.log.text
    assert '"speech_language": "zh"' in window.ask.log.text
    assert "PRIVATE-QUESTION" not in window.ask.log.text
    window.ask.client.completed.emit("fixture answer")
    dispose(window)
    app.processEvents()


def test_voice_locks_press_context_even_if_eyes_move_and_sends_once(monkeypatch):
    app, window, voice, jobs, sends = configure(monkeypatch)
    stable(window)
    assert voice.press()
    window._on_gaze(800, 600, time.monotonic())
    voice.release()  # Release can precede screenshot completion.
    assert not voice.recorder.active and len(jobs) == 1
    voice.engine.transcribed.emit(jobs[0][0], "这是什么？", 70)
    assert not sends
    drain()
    assert len(sends) == 1 and sends[0][1].geometry.gaze_global == (300, 400)
    assert sends[0][2] == "这是什么？"
    voice.engine.transcribed.emit(jobs[0][0], "duplicate", 80)
    assert len(sends) == 1
    window.ask.client.completed.emit("answer")
    assert not voice.active and not window.ask.reserved
    assert "这是什么" not in window.ask.log.text and "total_ms" in window.ask.log.text
    dispose(window)
    app.processEvents()


def test_cancel_discards_late_asr_then_next_turn_uses_new_context(monkeypatch):
    app, window, voice, jobs, sends = configure(monkeypatch)
    stable(window)
    voice.press()
    drain()
    voice.release()
    old = jobs[-1][0]
    window.ask.dialog.reject()
    voice.engine.transcribed.emit(old, "stale", 10)
    assert not sends and not voice.active
    stable(window, 700)
    voice.press()
    drain()
    voice.release()
    voice.engine.transcribed.emit(jobs[-1][0], "second", 20)
    assert len(sends) == 1 and sends[0][1].geometry.gaze_global == (700, 400)
    window.ask.client.completed.emit("answer")
    dispose(window)
    app.processEvents()


def test_no_stable_gaze_no_api_or_capture_failure_never_sends(monkeypatch):
    app, window, voice, jobs, sends = configure(monkeypatch)
    assert not voice.press() and not voice.recorder.active
    stable(window)
    window.ask.dialog.model_edit.clear()
    assert not voice.press() and not voice.recorder.active
    window.ask.dialog.model_edit.setText("test-vision")
    window.ask.capture_factory = lambda *_args: (_ for _ in ()).throw(ValueError("no capture"))
    assert voice.press()
    drain()
    assert not voice.active and not voice.recorder.active
    voice.release()
    assert not jobs and not sends
    dispose(window)
    app.processEvents()


@pytest.mark.parametrize("stage", ["microphone", "release", "asr", "timeout", "recalibrate"])
def test_voice_errors_cancel_audio_and_context_without_sending(monkeypatch, stage):
    app, window, voice, jobs, sends = configure(monkeypatch)
    stable(window)
    if stage == "microphone":
        monkeypatch.setattr(
            voice.recorder, "start", lambda: (_ for _ in ()).throw(SpeechError("no mic"))
        )
        assert not voice.press()
    else:
        assert voice.press()
        drain()
        if stage == "release":
            monkeypatch.setattr(
                voice.recorder, "stop", lambda: (_ for _ in ()).throw(SpeechError("short"))
            )
            voice.release()
        elif stage == "asr":
            voice.release()
            voice.engine.failed.emit(jobs[-1][0], "no speech", "asr_failed")
        elif stage == "timeout":
            voice.limit.timeout.emit()
        else:
            window.ask.invalidate("recalibrate")
    assert not voice.active and not voice.recorder.active and not sends
    assert not window.ask.reserved and window.ask.dialog.snapshot is None
    dispose(window)
    app.processEvents()


def test_three_completed_turns_keep_independent_context_and_reject_overlap(monkeypatch):
    app, window, voice, jobs, sends = configure(monkeypatch)
    identifiers = []
    for index, x in enumerate((200, 500, 800)):
        stable(window, x)
        assert voice.press()
        assert not voice.press()
        window.ask.trigger()  # Typed shortcut must not replace a recording's context.
        drain()
        voice.release()
        voice.engine.transcribed.emit(jobs[-1][0], f"question-{index}", 42)
        voice.release()
        assert len(sends) == index + 1
        assert sends[-1][1].geometry.gaze_global == (x, 400)
        identifiers.append(sends[-1][1].capture_id)
        window.ask.client.completed.emit("test answer")
    assert len(set(identifiers)) == 3
    dispose(window)
    app.processEvents()


def test_overflow_during_recording_cancels_before_key_release(monkeypatch):
    app, window, voice, jobs, sends = configure(monkeypatch)
    stable(window)
    assert voice.press()
    voice.recorder.fault = True
    drain()
    assert not voice.recorder.active and not voice.active and not sends and not jobs
    dispose(window)
    app.processEvents()


def test_cancel_stops_both_release_watchers_before_next_turn(monkeypatch):
    app, window, voice, jobs, sends = configure(monkeypatch)
    stable(window)
    voice.press()
    window.hotkeys.release_watcher.watch((0x20,), voice.release)
    voice.cancel()
    assert not window.hotkeys.release_watcher.timer.isActive()
    stable(window, 700)
    assert voice.press()
    window.mouse_release.watch((0x01,), voice.release)
    window.hotkeys.release_watcher._poll()  # A late timer event has no old callback.
    assert voice.recorder.active and not jobs and not sends
    voice.cancel()
    assert not window.mouse_release.timer.isActive()
    dispose(window)
    app.processEvents()


def test_exit_waits_for_active_model_load_and_keeps_thread_alive():
    app, window = prepare()
    window.worker = None
    entered, finish = threading.Event(), threading.Event()

    def delayed_model(_name):
        entered.set()
        finish.wait(3)
        return object()

    window.voice.engine.model_factory = delayed_model
    window.show()
    try:
        window.voice.prepare()
        assert entered.wait(1)
        window.close()
        assert window.voice.engine.isRunning() and window.isVisible()
        finish.set()
        assert window.voice.engine.wait(2000)
        drain()
        assert not window.isVisible()
    finally:
        finish.set()
        window.voice.engine.wait(3000)
        dispose(window)


def test_rejected_hotkey_is_visible_in_main_status_and_metadata_log(monkeypatch):
    app, window, voice, jobs, sends = configure(monkeypatch)
    window._has_calibration = False
    assert not window._voice_hotkey_pressed()
    assert "校准" in window.status_label.text()
    assert "voice_trigger_received" in window.ask.log.text
    assert "not_calibrated" in window.ask.log.text
    window._has_calibration = True
    window.ask.pending = True
    assert not window._voice_hotkey_pressed()
    assert "截图" in window.status_label.text()
    assert "capture_busy" in window.ask.log.text
    assert not voice.recorder.active and not sends and not jobs
    window.ask.pending = False
    dispose(window)
    app.processEvents()


def test_hotkey_self_check_bypasses_recording_capture_and_preconditions(monkeypatch):
    app, window, voice, jobs, sends = configure(monkeypatch)
    window._has_calibration = False
    calls = []
    monkeypatch.setattr(voice, "press", lambda: calls.append("record"))
    if window.hotkeys.VOICE_ID not in window.hotkeys.registered:
        window.hotkeys.registered.append(window.hotkeys.VOICE_ID)  # Registration fixture only.
    window._test_voice_hotkey()
    assert window.hotkey_test_timer.isActive()
    assert not window._voice_hotkey_pressed()
    assert "已收到" in window.status_label.text()
    assert not window.hotkey_test_timer.isActive()
    assert not calls and not jobs and not sends and not window.ask.pending
    window.hotkey_test_timer.timeout.emit()
    assert "已收到" in window.status_label.text()  # A late timeout cannot erase success.
    dispose(window)
    app.processEvents()


def test_hotkey_timeout_and_registration_failure_are_explicit_without_recording(monkeypatch):
    app, window, voice, jobs, sends = configure(monkeypatch)
    if window.hotkeys.VOICE_ID not in window.hotkeys.registered:
        window.hotkeys.registered.append(window.hotkeys.VOICE_ID)
    window._test_voice_hotkey()
    window.hotkey_test_timer.timeout.emit()
    assert "未收到" in window.status_label.text()
    assert not window._hotkey_test_pending and "not_received" in window.ask.log.text
    window.hotkeys.registered.remove(window.hotkeys.VOICE_ID)
    if window.hotkeys.VOICE_ALT_ID in window.hotkeys.registered:
        window.hotkeys.registered.remove(window.hotkeys.VOICE_ALT_ID)
    window.voice_hotkey_label.setText("Ctrl+Alt+Space 未注册（Windows 错误 1409）")
    window._test_voice_hotkey()
    assert "未注册" in window.status_label.text()
    assert not voice.recorder.active and not jobs and not sends and not window.ask.pending
    dispose(window)
    app.processEvents()
