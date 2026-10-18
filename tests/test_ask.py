"""UI transaction fixtures: no desktop capture, camera or external AI calls."""

import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from look_to_ask.ask import DiagnosticLog  # noqa: E402
from look_to_ask.calibration import ScreenRect  # noqa: E402
from look_to_ask.context import build_context  # noqa: E402
from look_to_ask.ui import ControlWindow  # noqa: E402


def drain(milliseconds=60):
    app = QApplication.instance()
    deadline = time.monotonic() + milliseconds / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)


def prepare():
    app = QApplication.instance() or QApplication([])
    window = ControlWindow()
    window.screen = ScreenRect(0, 0, 1000, 800)
    window.worker = SimpleNamespace(stopping=False)
    window._has_calibration = True
    window.ask.delay_ms = 5
    return app, window


def dispose(window):
    window.worker = None
    window.close()


def test_capture_requires_real_fresh_gaze_and_calibration():
    app, window = prepare()
    captured = []
    window.ask.capture_factory = lambda *_args: captured.append(True)
    window.ask.trigger()
    assert not window.ask.pending
    window._on_gaze(300, 400, time.monotonic() - 1)
    window.ask.trigger()
    window._has_calibration = False
    window._on_gaze(300, 400, time.monotonic())
    window.ask.trigger()
    drain()
    assert not captured
    dispose(window)
    app.processEvents()


def test_hides_every_own_window_freezes_point_and_waits_for_explicit_send():
    app, window = prepare()
    captures = []
    image = QImage(1000, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("cyan"))

    def capture(screen, point):
        assert not any(widget.isVisible() for widget in (window, window.marker, window.ask.dialog))
        captures.append(point)
        return build_context(image, screen, point)

    window.ask.capture_factory = capture
    window.show()
    window._on_gaze(300, 400, time.monotonic())
    window.ask.trigger()
    assert not window.isVisible() and not window.marker.isVisible()
    window._on_gaze(800, 600, time.monotonic())
    assert not window.marker.isVisible()
    drain()
    assert captures == [(300, 400)]
    assert window.ask.dialog.snapshot.geometry.gaze_global == (300, 400)
    assert window.ask.dialog.isVisible()
    assert not window.ask.client.busy  # Capture/preview must not send automatically.
    window.ask.dialog.reject()
    assert window.ask.dialog.snapshot is None
    assert window.isVisible()
    dispose(window)
    app.processEvents()


def test_invalidating_pending_capture_does_not_capture_or_strand_hidden_control():
    app, window = prepare()
    captures = []
    window.ask.capture_factory = lambda *_args: captures.append(True)
    window.show()
    window._on_gaze(300, 400, time.monotonic())
    window.ask.trigger()
    window.ask.invalidate("recalibrate")
    drain()
    assert not captures and not window.ask.pending
    assert window.isVisible()
    dispose(window)
    app.processEvents()


def test_only_send_button_dispatches_current_snapshot_and_typed_question(monkeypatch):
    app, window = prepare()
    image = QImage(1000, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    window.ask.capture_factory = lambda screen, point: build_context(image, screen, point)
    calls = []
    monkeypatch.setattr(
        window.ask.client,
        "send",
        lambda config, snapshot, question: calls.append((snapshot.capture_id, question)),
    )
    window._on_gaze(300, 400, time.monotonic())
    window.ask.trigger()
    drain()
    assert not calls
    dialog = window.ask.dialog
    dialog.model_edit.setText("test-vision")
    dialog.question_edit.setPlainText("private question")
    dialog.send_button.click()
    assert calls == [(dialog.snapshot.capture_id, "private question")]
    assert "private question" not in window.ask.log.text
    dispose(window)
    app.processEvents()


def test_metadata_log_whitelist_excludes_content_credentials_and_arbitrary_errors():
    log = DiagnosticLog()
    log.record(
        "capture_ready",
        capture_id="a1b2c3d4",
        gaze_global=(30, 40),
        scale=(1.5, 1.5),
        api_key="SECRET",
        question="private",
        screenshot="base64",
    )
    assert "a1b2c3d4" in log.text and "30" in log.text
    assert not any(value in log.text for value in ("SECRET", "private", "base64", "api_key"))


def test_asr_metadata_rejects_content_disguised_as_levels_or_local_model_paths():
    log = DiagnosticLog()
    log.record(
        "asr_ready",
        speech_model="C:/PRIVATE/model",
        rms_dbfs="SECRET",
        peak_dbfs=float("nan"),
        beam_size=5,
        speech_language="private-text",
        audio="private-samples",
        speech_device="PRIVATE-DEVICE",
        speech_compute="PRIVATE-COMPUTE",
        speech_fallback="PRIVATE-ERROR",
    )
    assert "PRIVATE" not in log.text and "SECRET" not in log.text
    assert "private" not in log.text and "NaN" not in log.text
    assert '"speech_model": "custom"' in log.text and '"beam_size": 5' in log.text
