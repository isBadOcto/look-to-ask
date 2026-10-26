"""One primary-screen screenshot and a gaze detail from those same native pixels."""

from dataclasses import replace

from PySide6.QtGui import QColor, QPainter, QPen

from look_to_ask.context import ContextSnapshot, build_context, capture_primary


def build_screen_context(image, screen, gaze_global):
    local = build_context(image, screen, gaze_global, roi_size=(560, 360), focus_size=(560, 360))
    overview = image.copy()
    overview.setDevicePixelRatio(1.0)
    geometry = replace(local.geometry, roi_bounds=(0, 0, image.width(), image.height()))
    return ContextSnapshot(local.capture_id, geometry, overview, local.focus)


def capture_screen_context(screen, gaze_global):
    return capture_primary(screen, gaze_global, builder=build_screen_context)


def annotate_screen_overview(snapshot):
    """Annotate a copy; preserve the native detail and original overview."""
    overview = snapshot.roi.copy()
    geometry = snapshot.geometry
    x, y, width, height = geometry.focus_bounds
    x, y = x - geometry.roi_bounds[0], y - geometry.roi_bounds[1]
    painter = QPainter(overview)
    painter.setPen(QPen(QColor("#ffe37d"), 2))
    painter.drawRect(x, y, max(0, width - 1), max(0, height - 1))
    gx, gy = geometry.gaze_in_roi
    painter.setPen(QPen(QColor("#ff735f"), 2))
    painter.drawLine(gx - 4, gy, gx + 4, gy)
    painter.drawLine(gx, gy - 4, gx, gy + 4)
    painter.end()
    return overview
