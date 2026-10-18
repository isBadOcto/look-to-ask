import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from look_to_ask.calibration import ScreenRect  # noqa: E402
from look_to_ask.ui import CalibrationWindow, ControlWindow, GazeMarker  # noqa: E402


def test_marker_is_click_through_does_not_take_focus_and_hides_on_loss():
    app = QApplication.instance() or QApplication([])
    marker = GazeMarker(ScreenRect(0, 0, 1000, 800))
    assert marker.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert marker.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    marker.update_gaze(500, 400)
    app.processEvents()
    assert marker.isVisible()
    assert marker.geometry().center().x() in (499, 500)
    marker.hide()
    assert not marker.isVisible()
    marker.close()


def test_calibration_uses_exact_primary_screen_geometry():
    app = QApplication.instance() or QApplication([])
    rect = ScreenRect(-1000, 50, 1000, 800)
    window = CalibrationWindow(rect)
    window.set_target(0, 500, 400)
    app.processEvents()
    assert window.geometry().x() == -1000
    assert window.geometry().y() == 50
    assert window.geometry().width() == 1000
    window.close()


def test_delayed_prediction_is_not_displayed_as_current_gaze():
    app = QApplication.instance() or QApplication([])
    marker = GazeMarker(ScreenRect(0, 0, 1000, 800))
    marker.update_gaze(500, 400, time.monotonic() - 1)
    app.processEvents()
    assert not marker.isVisible()
    marker.close()


def test_quick_is_default_dense_is_selectable_and_measurement_requires_calibration():
    app = QApplication.instance() or QApplication([])
    window = ControlWindow()
    assert window.mode_selector.currentData() == "quick"
    assert window.mode_selector.findData("dense") >= 0
    assert not window.measure_button.isEnabled()
    window._calibration_finished()
    app.processEvents()
    assert window.measure_button.isEnabled()
    window._worker_finished()
    assert not window.measure_button.isEnabled()
    window.close()


def test_session_caption_uses_actual_target_count_and_mode():
    app = QApplication.instance() or QApplication([])
    window = CalibrationWindow(ScreenRect(0, 0, 1920, 1080))
    window.set_session("边缘加强校准", 25)
    app.processEvents()
    assert "25" in window.caption and "边缘" in window.caption
    window.set_session("独立精度测量", 9)
    assert "测量" in window.caption
    window.close()


def test_calibration_and_independent_measurement_use_the_single_gaze_backend():
    app = QApplication.instance() or QApplication([])
    window = ControlWindow()
    calls = []

    class Worker:
        stopping = False

        def recalibrate(self, mode):
            calls.append(("calibrate", mode))

        def validate(self):
            calls.append(("validate", None))

    window.worker = Worker()
    window._begin_calibration()
    window._calibration_finished()
    window.start_accuracy_measurement()
    app.processEvents()
    assert calls == [("calibrate", "quick"), ("validate", None)]
    window._validation_finished("独立精度测量测试结果")
    assert "独立精度测量测试结果" in window.report_view.toPlainText()
    assert window._has_calibration
    window.worker = None
    window.close()


@pytest.mark.parametrize("resolution", [(1280, 720), (1920, 1080)])
def test_resolution_stays_locked_while_tracking_and_unlocks_after_stop(resolution):
    app = QApplication.instance() or QApplication([])
    window = ControlWindow(camera_resolution=resolution)

    class Worker:
        stopping = False

        def recalibrate(self, _mode):
            pass

        def deleteLater(self):
            pass

    assert tuple(window.resolution_selector.currentData()) == resolution
    window.worker = Worker()
    window._begin_calibration()
    assert not window.resolution_selector.isEnabled()
    window._calibration_finished()
    assert not window.resolution_selector.isEnabled()
    window._worker_finished()
    app.processEvents()
    assert window.resolution_selector.isEnabled()
    window.close()
