"""Same-frame desktop/detail geometry; images are synthetic fixtures only."""

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from look_to_ask.calibration import ScreenRect


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5, 2.0])
@pytest.mark.parametrize("point", [(-100, 50), (600, 550), (1499, 1249)])
def test_screen_overview_and_detail_share_native_pixels_and_gaze(scale, point):
    from look_to_ask.screen_context import build_screen_context

    screen = ScreenRect(-100, 50, 1600, 1200)
    image = QImage(round(1600 * scale), round(1200 * scale), QImage.Format.Format_RGB32)
    image.fill(QColor("#129876"))
    snapshot = build_screen_context(image, screen, point)
    geometry = snapshot.geometry
    assert geometry.roi_bounds == (0, 0, image.width(), image.height())
    assert snapshot.roi == image
    assert snapshot.focus == image.copy(*geometry.focus_bounds)
    x, y = geometry.gaze_in_focus
    assert 0 <= x < snapshot.focus.width() and 0 <= y < snapshot.focus.height()
    assert snapshot.focus.width() <= 560 * scale + 1
    assert snapshot.focus.height() <= 360 * scale + 1


def test_annotation_does_not_modify_screen_or_detail():
    from look_to_ask.screen_context import annotate_screen_overview, build_screen_context

    image = QImage(1000, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("cyan"))
    snapshot = build_screen_context(image, ScreenRect(0, 0, 1000, 800), (400, 400))
    before = snapshot.focus.copy()
    assert annotate_screen_overview(snapshot) != image
    assert snapshot.roi == image and snapshot.focus == before


def test_capture_grabs_primary_once_without_any_application_lookup(monkeypatch):
    from look_to_ask import screen_context

    app = QApplication.instance() or QApplication([])
    image = QImage(1250, 1000, QImage.Format.Format_RGB32)
    image.fill(QColor("cyan"))
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(1.25)

    class Primary:
        grabs = 0

        def geometry(self):
            return QRect(-100, 50, 1000, 800)

        def grabWindow(self, handle):
            assert handle == 0
            self.grabs += 1
            return pixmap

    primary = Primary()
    monkeypatch.setattr("look_to_ask.context.QGuiApplication.primaryScreen", lambda: primary)
    snapshot = screen_context.capture_screen_context(ScreenRect(-100, 50, 1000, 800), (400, 400))
    assert primary.grabs == 1
    assert snapshot.geometry.image_size == (1250, 1000)
    assert snapshot.roi == image
    assert snapshot.focus == image.copy(*snapshot.geometry.focus_bounds)
    app.processEvents()
