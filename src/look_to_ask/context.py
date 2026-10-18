"""On-demand primary-screen crops, in memory; all geometry uses actual pixel sizes."""

import math
import uuid
from collections import deque
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication, QImage

from look_to_ask.calibration import ScreenRect
from look_to_ask.i18n import tr


def _local_point(screen, point):
    x, y = point
    x, y = x - screen.x, y - screen.y
    if not (
        math.isfinite(x) and math.isfinite(y) and 0 <= x < screen.width and 0 <= y < screen.height
    ):
        raise ValueError(tr("注视点不在已校准主屏内；请重新看向内容后触发。"))
    return x, y


class GazeState:
    """Last real prediction only; never use cursor position or fabricate a fallback."""

    def __init__(self):
        self.sample = None
        self.history = deque(maxlen=60)

    def update(self, x, y, timestamp):
        if all(math.isfinite(value) for value in (x, y, timestamp)):
            if self.sample is None or timestamp >= self.sample[2]:
                self.sample = (x, y, timestamp)
                self.history.append(self.sample)

    def clear(self):
        self.sample = None
        self.history.clear()

    def freeze(self, screen, *, now):
        if self.sample is None:
            raise ValueError(tr("没有有效注视点；请校准并看向主屏内容后重试。"))
        x, y, timestamp = self.sample
        if not 0 <= now - timestamp <= 0.5:
            raise ValueError(tr("注视点已过期；请等待跟踪恢复后重试。"))
        _local_point(screen, (x, y))
        return x, y

    def freeze_stable(self, screen, *, now):
        self.freeze(screen, now=now)
        samples = [s for s in self.history if 0 <= now - s[2] <= 0.25]
        if len(samples) < 4 or samples[-1][2] - samples[0][2] < 0.1:
            raise ValueError(tr("请稳定注视目标约半秒，再按住说话。"))
        points = np.asarray([s[:2] for s in samples])
        point = np.median(points, axis=0)
        spread = float(np.quantile(np.linalg.norm(points - point, axis=1), 0.9))
        if spread > max(35, 0.03 * math.hypot(screen.width, screen.height)):
            raise ValueError(tr("注视区域正在移动；请稳定注视目标后重试。"))
        _local_point(screen, point)
        return tuple(float(v) for v in point), {
            "stable_samples": len(samples),
            "spread_px": round(spread, 1),
        }


@dataclass(frozen=True)
class ContextGeometry:
    screen: ScreenRect
    image_size: tuple[int, int]
    gaze_global: tuple[float, float]
    gaze_pixels: tuple[int, int]
    roi_bounds: tuple[int, int, int, int]
    focus_bounds: tuple[int, int, int, int]

    @property
    def scale(self):
        return self.image_size[0] / self.screen.width, self.image_size[1] / self.screen.height

    @property
    def gaze_in_roi(self):
        return self.gaze_pixels[0] - self.roi_bounds[0], self.gaze_pixels[1] - self.roi_bounds[1]

    @property
    def gaze_in_focus(self):
        return self.gaze_pixels[0] - self.focus_bounds[0], self.gaze_pixels[1] - self.focus_bounds[
            1
        ]


@dataclass(frozen=True)
class ContextSnapshot:
    capture_id: str
    geometry: ContextGeometry
    roi: QImage
    focus: QImage


def build_context(image, screen, gaze_global, *, roi_size=(560, 360), focus_size=(160, 120)):
    if image.isNull() or screen.width <= 0 or screen.height <= 0:
        raise ValueError(tr("截图或屏幕尺寸无效，不能定位内容。"))
    lx, ly = _local_point(screen, gaze_global)
    sx, sy = image.width() / screen.width, image.height() / screen.height
    # Very high DPI can make the logical desktop smaller than the default ROI.
    # Keep a surrounding margin rather than turning a "local crop" into the whole screen.
    roi_size = (min(roi_size[0], screen.width * 0.8), min(roi_size[1], screen.height * 0.8))
    focus_size = (min(focus_size[0], roi_size[0]), min(focus_size[1], roi_size[1]))

    def bounds(size):
        width, height = min(size[0], screen.width), min(size[1], screen.height)
        if width <= 0 or height <= 0:
            raise ValueError(tr("裁剪尺寸必须大于零。"))
        left = min(max(lx - width / 2, 0), screen.width - width)
        top = min(max(ly - height / 2, 0), screen.height - height)
        x, y = math.floor(left * sx), math.floor(top * sy)
        right = min(image.width(), math.ceil((left + width) * sx))
        bottom = min(image.height(), math.ceil((top + height) * sy))
        return x, y, right - x, bottom - y

    roi_bounds, focus_bounds = bounds(roi_size), bounds(focus_size)
    geometry = ContextGeometry(
        screen,
        (image.width(), image.height()),
        tuple(gaze_global),
        (math.floor(lx * sx), math.floor(ly * sy)),
        roi_bounds,
        focus_bounds,
    )
    roi, focus = image.copy(*roi_bounds), image.copy(*focus_bounds)
    roi.setDevicePixelRatio(1.0)
    focus.setDevicePixelRatio(1.0)
    # The complete screen is deliberately not retained in the returned object.
    return ContextSnapshot(uuid.uuid4().hex[:8], geometry, roi, focus)


def encode_png(image):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if image.isNull() or not image.save(buffer, "PNG"):
        raise ValueError(tr("无法编码裁剪图像。"))
    return bytes(buffer.data())


def capture_primary(screen, gaze_global):
    """Called on the GUI thread only, after the app has hidden its own windows."""
    primary = QGuiApplication.primaryScreen()
    if primary is None:
        raise ValueError(tr("找不到主显示器。"))
    rect = primary.geometry()
    if (rect.x(), rect.y(), rect.width(), rect.height()) != (
        screen.x,
        screen.y,
        screen.width,
        screen.height,
    ):
        raise ValueError(tr("主屏或缩放已改变；请重启并重新校准。"))
    pixmap = primary.grabWindow(0)
    if pixmap.isNull():
        raise ValueError(tr("无法获取主屏截图；请检查桌面或受保护内容。"))
    # grabWindow is DPI aware. Its native pixel size must agree with its DPR;
    # multiplying the coordinates by DPR again would incorrectly double-scale.
    dpr = pixmap.devicePixelRatio()
    if (
        abs(pixmap.width() - screen.width * dpr) > 2
        or abs(pixmap.height() - screen.height * dpr) > 2
    ):
        raise ValueError(tr("截图尺寸与主屏 DPI 不一致；拒绝分析可能错位的内容。"))
    return build_context(pixmap.toImage(), screen, gaze_global)
