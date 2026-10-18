"""UI coordinates and sampling schedule; gaze estimation remains in EyeTrax."""

from dataclasses import dataclass

import numpy as np

from look_to_ask.i18n import tr


class CalibrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScreenRect:
    x: int
    y: int
    width: int
    height: int

    def to_global(self, point) -> tuple[int, int] | None:
        if not np.isfinite(point).all():
            return None
        px = round(float(np.clip(point[0], 0, self.width - 1)))
        py = round(float(np.clip(point[1], 0, self.height - 1)))
        return self.x + px, self.y + py


class CalibrationSession:
    """Collect valid samples at quick, dense or measurement targets, in memory."""

    def __init__(
        self,
        width,
        height,
        *,
        profile="quick",
        settling=1.0,
        sample_seconds=1.5,
        min_samples=15,
        timeout=15.0,
    ):
        if width <= 0 or height <= 0:
            raise ValueError(tr("屏幕尺寸必须大于 0"))
        order = [(1, 1), (0, 0), (2, 0), (0, 2), (2, 2), (1, 0), (0, 1), (2, 1), (1, 2)]
        if profile == "quick":
            self.points = [
                (round(width * (0.1 + col * 0.4)), round(height * (0.1 + row * 0.4)))
                for row, col in order
            ]
        elif profile in ("dense", "validation"):
            size, ratio = (5, 0.04) if profile == "dense" else (3, 0.06)
            # Keep rings clear of instructions, including on smaller logical screens.
            margin_x = min(max(64, round(width * ratio)), width * 0.2)
            margin_y = min(max(64, round(height * ratio)), height * 0.2)
            xs = np.linspace(margin_x, width - margin_x, size)
            ys = np.linspace(margin_y, height - margin_y, size)
            if profile == "dense":
                order = [(2, 2)] + [
                    (row, col)
                    for row in range(5)
                    for col in (range(5) if row % 2 == 0 else range(4, -1, -1))
                    if (row, col) != (2, 2)
                ]
            self.points = [(round(xs[col]), round(ys[row])) for row, col in order]
        else:
            raise ValueError(tr("未知采样模式：{value0}", value0=profile))
        self.profile = profile
        self.settling = settling
        self.sample_seconds = sample_seconds
        self.min_samples = min_samples
        self.timeout = timeout
        self.index = 0
        self._shown_at = None
        self._valid_since = None
        self._collect_since = None
        self._dimension = None
        self._current = []
        self._features = []
        self._targets = []

    @property
    def total(self):
        return len(self.points)

    @property
    def done(self):
        return self.index == self.total

    @property
    def sample_count(self):
        return len(self._current)

    @property
    def collecting(self):
        return self._collect_since is not None

    def target_visible(self, now):
        if self._shown_at is None and not self.done:
            self._shown_at = now

    def observe(self, features, now):
        if self.done or self._shown_at is None:
            return
        if now - self._shown_at > self.timeout:
            raise CalibrationError(
                tr(
                    "第 {value0}/{value1} 点超时：请检查光线、脸部位置后重试。",
                    value0=self.index + 1,
                    value1=self.total,
                )
            )
        if features is None or not np.isfinite(features).all():
            if not self.collecting:
                self._valid_since = None
            return
        features = np.asarray(features, dtype=np.float64)
        if features.ndim != 1:
            raise CalibrationError(tr("眼睛特征维度无效，请重新启动。"))
        if self._dimension is None:
            self._dimension = features.size
        if features.size != self._dimension:
            raise CalibrationError(tr("眼睛特征维度变化，请重新启动。"))
        if self._valid_since is None:
            self._valid_since = now
        if now - self._valid_since < self.settling:
            return
        if self._collect_since is None:
            self._collect_since = now
        self._current.append(features.copy())
        if (
            now - self._collect_since >= self.sample_seconds
            and self.sample_count >= self.min_samples
        ):
            self._features.extend(self._current)
            self._targets.extend([self.points[self.index]] * self.sample_count)
            self.index += 1
            self._shown_at = self._valid_since = self._collect_since = None
            self._current = []

    def sample_data(self):
        if not self.done:
            raise CalibrationError(tr("必须完成全部 {value0} 点采样。", value0=self.total))
        return np.asarray(self._features), np.asarray(self._targets)

    def training_data(self):
        if self.profile == "validation":
            raise CalibrationError(tr("精度测量数据不能用于校准拟合。"))
        return self.sample_data()
