"""Honest held-out gaze measurements; no fitting, clipping or persistent logging."""

from dataclasses import dataclass

import numpy as np

from look_to_ask.i18n import tr


@dataclass(frozen=True)
class FitDiagnostics:
    sample_count: int
    target_count: int
    feature_count: int
    centre_error: float
    mean_error: float
    worst_error: float
    centre_bias: tuple[float, float]

    def format_text(self):
        x, y = self.centre_bias
        return tr(
            "校准内部诊断（同一批拟合数据，不是独立精度）\n"
            "目标 {value0} 个，样本 {value1} 帧，特征 {value2} 维\n"
            "中心拟合残差 {value3:.0f}，全部目标平均 {value4:.0f}，最差目标"
            " {value5:.0f} 逻辑像素（每目标等权）\n"
            "中心拟合偏移 x={value6:+.0f}, y={value7:+.0f}\n"
            "拟合残差小不代表实测准确；"
            "请与随后独立测量比较。",
            value0=self.target_count,
            value1=self.sample_count,
            value2=self.feature_count,
            value3=self.centre_error,
            value4=self.mean_error,
            value5=self.worst_error,
            value6=x,
            value7=y,
        )


def inspect_calibration_fit(predictions, targets, feature_count):
    """Evaluate the real fitted outputs without presenting training error as accuracy."""
    predictions = np.asarray(predictions, dtype=float)
    targets = np.asarray(targets, dtype=float)
    if (
        predictions.ndim != 2
        or predictions.shape[1] != 2
        or predictions.shape != targets.shape
        or len(targets) == 0
        or not np.isfinite(predictions).all()
        or not np.isfinite(targets).all()
    ):
        raise ValueError(tr("拟合诊断需要维度一致的有限二维坐标。"))
    # CalibrationSession always presents the centre first, regardless of profile.
    centre_samples = (targets == targets[0]).all(axis=1)
    offsets = predictions - targets
    errors = np.linalg.norm(offsets, axis=1)
    points = np.unique(targets, axis=0)
    point_errors = [errors[(targets == point).all(axis=1)].mean() for point in points]
    return FitDiagnostics(
        len(targets),
        len(points),
        feature_count,
        float(errors[centre_samples].mean()),
        float(np.mean(point_errors)),
        float(np.max(point_errors)),
        tuple(float(v) for v in offsets[centre_samples].mean(axis=0)),
    )


@dataclass(frozen=True)
class PointAccuracy:
    target: tuple[int, int]
    mean_error: float
    bias_x: float
    bias_y: float
    sample_count: int


@dataclass(frozen=True)
class AccuracyReport:
    width: int
    height: int
    profile: str
    points: tuple[PointAccuracy, ...]
    outside_fraction: float

    @property
    def centre_error(self):
        return self.points[0].mean_error

    @property
    def edge_error(self):
        return float(np.mean([point.mean_error for point in self.points[1:]]))

    @property
    def mean_error(self):
        return float(np.mean([point.mean_error for point in self.points]))

    def format_text(self):
        mode = tr("25 点边缘校准") if self.profile == "dense" else tr("9 点快速校准")
        diagonal = float(np.hypot(self.width, self.height))
        lines = [
            tr(
                "{value0} → 独立精度测量 · {value1}×{value2}",
                value0=mode,
                value1=self.width,
                value2=self.height,
            ),
            tr(
                "中心 {value0:.0f}，周边平均 {value1:.0f}，全部平均 "
                "{value2:.0f} 逻辑像素（屏幕对角线的 {value3:.1%}）",
                value0=self.centre_error,
                value1=self.edge_error,
                value2=self.mean_error,
                value3=self.mean_error / diagonal,
            ),
            tr("原始预测误差，未裁剪、未平滑、未用于拟合；每点等权。"),
            tr(
                "越界预测占有效帧 {value0:.1%}（跟踪时会隐藏这类结果）。",
                value0=self.outside_fraction,
            ),
        ]
        for point in self.points:
            x, y = point.target
            horizontal = -1 if x < self.width * 0.4 else 1 if x > self.width * 0.6 else 0
            vertical = -1 if y < self.height * 0.4 else 1 if y > self.height * 0.6 else 0
            name = {
                (-1, -1): tr("左上"),
                (1, -1): tr("右上"),
                (-1, 1): tr("左下"),
                (1, 1): tr("右下"),
                (-1, 0): tr("左"),
                (1, 0): tr("右"),
                (0, -1): tr("上"),
                (0, 1): tr("下"),
                (0, 0): tr("中心"),
            }[horizontal, vertical]
            lines.append(
                tr(
                    "{value0}: 平均误差 {value1:.0f}，偏移 x={value2:+.0f}, y="
                    "{value3:+.0f}，有效帧 {value4}",
                    value0=name,
                    value1=point.mean_error,
                    value2=point.bias_x,
                    value3=point.bias_y,
                    value4=point.sample_count,
                )
            )
        lines.append(tr("偏移正值=右/下，负值=左/上。结果仅保留在当前窗口内存。"))
        return "\n".join(lines)


def measure_accuracy(predictions, targets, points, width, height, profile):
    predictions = np.asarray(predictions, dtype=float)
    targets = np.asarray(targets, dtype=float)
    if (
        predictions.ndim != 2
        or predictions.shape[1] != 2
        or targets.shape != predictions.shape
        or not np.isfinite(predictions).all()
        or not np.isfinite(targets).all()
    ):
        raise ValueError(tr("测量必须是维度一致的有限二维坐标。"))
    if len(points) < 2 or width <= 0 or height <= 0:
        raise ValueError(tr("测量需要中心与周边目标，以及有效屏幕尺寸。"))
    records = []
    for point in points:
        selected = (targets == point).all(axis=1)
        if not selected.any():
            raise ValueError(tr("每个目标都必须完成真实预测采样。"))
        offsets = predictions[selected] - targets[selected]
        bias_x, bias_y = offsets.mean(axis=0)
        records.append(
            PointAccuracy(
                tuple(point),
                float(np.linalg.norm(offsets, axis=1).mean()),
                float(bias_x),
                float(bias_y),
                int(selected.sum()),
            )
        )
    outside = (
        (predictions[:, 0] < 0)
        | (predictions[:, 0] >= width)
        | (predictions[:, 1] < 0)
        | (predictions[:, 1] >= height)
    )
    return AccuracyReport(width, height, profile, tuple(records), float(outside.mean()))
