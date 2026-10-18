"""Explicit image/coordinate fixtures; no desktop or synthetic runtime gaze mode."""

import pytest
from PySide6.QtGui import QColor, QImage

from look_to_ask.calibration import ScreenRect
from look_to_ask.context import GazeState, build_context, encode_png


def test_voice_freezes_recent_stable_median_and_rejects_saccade():
    state = GazeState()
    screen = ScreenRect(0, 0, 1920, 1080)
    for i, x in enumerate([300, 302, 299, 301, 300, 303]):
        state.update(x, 400, 10 + i * 0.04)
    point, stats = state.freeze_stable(screen, now=10.21)
    assert point == (300.5, 400)
    assert stats["stable_samples"] == 6
    state.update(1500, 400, 10.22)
    with pytest.raises(ValueError, match="稳定"):
        state.freeze_stable(screen, now=10.23)
    state.clear()
    state.update(500, 400, 10.3)
    with pytest.raises(ValueError, match="稳定"):
        state.freeze_stable(screen, now=10.31)


@pytest.mark.parametrize(
    "scale,pixel,bounds,local",
    [
        (1.0, (750, 200), (550, 100, 400, 200), (200, 100)),
        (1.25, (937, 250), (687, 125, 501, 250), (250, 125)),
        (1.5, (1125, 300), (825, 150, 600, 300), (300, 150)),
        (2.0, (1500, 400), (1100, 200, 800, 400), (400, 200)),
    ],
)
def test_dpi_mapping_subtracts_screen_origin_and_never_double_scales(scale, pixel, bounds, local):
    image = QImage(round(1000 * scale), round(800 * scale), QImage.Format.Format_RGB32)
    image.fill(QColor("blue"))
    snapshot = build_context(
        image, ScreenRect(-1000, 50, 1000, 800), (-250, 250), roi_size=(400, 200)
    )
    geometry = snapshot.geometry
    assert geometry.gaze_pixels == pixel
    assert geometry.roi_bounds == bounds
    assert geometry.gaze_in_roi == local
    assert snapshot.roi.width() == bounds[2]
    assert snapshot.roi.devicePixelRatio() == 1.0


@pytest.mark.parametrize("point", [(0, 0), (999, 0), (0, 799), (999, 799)])
def test_edge_crop_keeps_gaze_inside_without_padding_or_offscreen_pixels(point):
    image = QImage(1500, 1200, QImage.Format.Format_RGB32)
    image.fill(QColor("green"))
    snapshot = build_context(image, ScreenRect(0, 0, 1000, 800), point)
    for bounds, crop in (
        (snapshot.geometry.roi_bounds, snapshot.roi),
        (snapshot.geometry.focus_bounds, snapshot.focus),
    ):
        x, y, width, height = bounds
        px, py = snapshot.geometry.gaze_pixels
        assert 0 <= x <= px < x + width <= 1500
        assert 0 <= y <= py < y + height <= 1200
        assert crop.pixelColor(px - x, py - y) == QColor("green")


def test_different_screen_regions_produce_different_real_crops_and_pngs():
    image = QImage(1200, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    from PySide6.QtGui import QPainter

    painter = QPainter(image)
    painter.fillRect(600, 0, 600, 800, QColor("blue"))
    painter.end()
    left = build_context(image, ScreenRect(0, 0, 1200, 800), (100, 400))
    right = build_context(image, ScreenRect(0, 0, 1200, 800), (1100, 400))
    assert left.focus.pixelColor(10, 10) == QColor("red")
    assert right.focus.pixelColor(10, 10) == QColor("blue")
    assert encode_png(left.focus).startswith(b"\x89PNG")
    assert encode_png(left.focus) != encode_png(right.focus)
    assert left.roi.width() == 560 < image.width()


def test_frozen_gaze_is_immutable_and_lost_or_stale_tracking_cannot_trigger_capture():
    gaze = GazeState()
    screen = ScreenRect(0, 0, 1000, 800)
    with pytest.raises(ValueError, match="注视"):
        gaze.freeze(screen, now=10)
    gaze.update(300, 400, 10)
    frozen = gaze.freeze(screen, now=10.2)
    gaze.update(700, 500, 10.3)
    assert frozen == (300, 400)
    with pytest.raises(ValueError, match="过期"):
        gaze.freeze(screen, now=11)
    gaze.clear()
    with pytest.raises(ValueError, match="注视"):
        gaze.freeze(screen, now=10.4)


@pytest.mark.parametrize("point", [(-1, 10), (1000, 10), (float("nan"), 10)])
def test_invalid_gaze_is_rejected_instead_of_clamped_to_a_different_target(point):
    image = QImage(1000, 800, QImage.Format.Format_RGB32)
    with pytest.raises(ValueError):
        build_context(image, ScreenRect(0, 0, 1000, 800), point)


def test_small_logical_screen_still_produces_local_crops_not_entire_screen():
    image = QImage(320, 240, QImage.Format.Format_RGB32)
    image.fill(QColor("blue"))
    snapshot = build_context(image, ScreenRect(0, 0, 320, 240), (160, 120))
    assert snapshot.roi.width() <= 256 < image.width()
    assert snapshot.roi.height() <= 192 < image.height()
    assert snapshot.focus.width() <= snapshot.roi.width()
    assert snapshot.focus.height() <= snapshot.roi.height()


@pytest.mark.parametrize("dpr,valid", [(1.5, True), (1.0, False)])
def test_capture_adapter_checks_pixmap_dpr_without_grabbing_real_desktop(monkeypatch, dpr, valid):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication

    from look_to_ask import context

    app = QApplication.instance() or QApplication([])
    image = QImage(1500, 1200, QImage.Format.Format_RGB32)
    image.fill(QColor("green"))
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr)

    class Screen:
        def geometry(self):
            return QRect(0, 0, 1000, 800)

        def grabWindow(self, window):
            assert window == 0
            return pixmap

    monkeypatch.setattr(context.QGuiApplication, "primaryScreen", lambda: Screen())
    if valid:
        snapshot = context.capture_primary(ScreenRect(0, 0, 1000, 800), (500, 400))
        assert snapshot.geometry.scale == (1.5, 1.5)
        assert snapshot.geometry.gaze_pixels == (750, 600)
        assert snapshot.geometry.gaze_in_roi == (420, 270)
    else:
        with pytest.raises(ValueError, match="DPI"):
            context.capture_primary(ScreenRect(0, 0, 1000, 800), (500, 400))
    app.processEvents()
