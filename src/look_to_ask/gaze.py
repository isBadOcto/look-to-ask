"""Small adapters around OpenCV capture and the unmodified EyeTrax library."""

import cv2
import numpy as np

from look_to_ask._vendor.eyetrax.constants import (
    LEFT_EYE_INDICES,
    MUTUAL_INDICES,
    RIGHT_EYE_INDICES,
)
from look_to_ask.i18n import tr
from look_to_ask.validation import inspect_calibration_fit

_FEATURE_INDICES = LEFT_EYE_INDICES + RIGHT_EYE_INDICES + MUTUAL_INDICES
_FEATURE_COUNT = len(_FEATURE_INDICES) * 3 + 3
_POSITIONS = {index: position for position, index in enumerate(_FEATURE_INDICES)}


def _valid_eye_geometry(features):
    """Keep the existing degeneracy guard in EyeTrax's normalized, Y-up coordinates."""
    values = np.asarray(features, dtype=float)
    if values.shape != (_FEATURE_COUNT,):
        raise ValueError(
            tr("EyeTrax 特征应为 {value0} 维，请检查上游版本。", value0=_FEATURE_COUNT)
        )
    coordinates = values[:-3].reshape(-1, 3)
    for outer, inner, upper, lower in (
        (33, 133, (159, 158, 157, 173, 160), (145, 144, 163, 153)),
        (263, 362, (386, 385, 384, 398, 387), (374, 373, 380, 382)),
    ):
        width = abs(coordinates[_POSITIONS[outer], 0] - coordinates[_POSITIONS[inner], 0])
        height = max(coordinates[_POSITIONS[i], 1] for i in upper) - min(
            coordinates[_POSITIONS[i], 1] for i in lower
        )
        if width < 0.008 or height < 0.003:
            return False
    return True


class CameraError(RuntimeError):
    pass


CAMERA_RESOLUTIONS = {
    "640x480": (640, 480),
    "1280x720": (1280, 720),
    "1920x1080": (1920, 1080),
}


def prediction_on_screen(prediction, width, height):
    """Reject impossible raw predictions instead of disguising them as screen edges."""
    prediction = np.asarray(prediction, dtype=float)
    if prediction.shape != (2,) or not np.isfinite(prediction).all():
        return None
    x, y = prediction
    if not (0 <= x < width and 0 <= y < height):
        return None
    return float(x), float(y)


def open_camera(index=0, *, resolution=(640, 480), capture_factory=None, api_preference=None):
    resolution = tuple(resolution)
    if resolution not in CAMERA_RESOLUTIONS.values():
        raise ValueError(tr("摄像头分辨率仅支持 640×480、1280×720 或 1920×1080。"))
    factory = capture_factory or cv2.VideoCapture
    observed_sizes = []
    if api_preference not in (None, cv2.CAP_DSHOW, cv2.CAP_MSMF):
        raise ValueError(tr("不支持的摄像头后端。"))
    apis = (cv2.CAP_DSHOW, cv2.CAP_MSMF) if api_preference is None else (api_preference,)
    for api in apis:
        capture = factory(index, api)
        try:
            if capture.isOpened():
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                # A driver can accept set() but ignore it. Inspect actual pixels;
                # allow a few initial frames for the negotiated mode to settle.
                for _ in range(3):
                    ok, frame = capture.read()
                    if not ok or frame is None or not frame.size:
                        break
                    actual = (frame.shape[1], frame.shape[0])
                    if resolution == (640, 480) or actual == resolution:
                        return capture
                    if actual not in observed_sizes:
                        observed_sizes.append(actual)
        except Exception:
            capture.release()
            raise
        capture.release()
    if observed_sizes:
        sizes = "、".join(f"{width}×{height}" for width, height in observed_sizes)
        raise CameraError(
            tr(
                "请求摄像头 {value0} 使用 {value1}×{value2}，实际返回 {value3}"
                "。已尝试的摄像头后端未取得所选尺寸；"
                "请选择较低采集尺寸，不能把回退结果当作所选尺寸。",
                value0=index,
                value1=resolution[0],
                value2=resolution[1],
                value3=sizes,
            )
        )
    raise CameraError(
        tr(
            "无法读取摄像头 {value0}。"
            "请关闭占用摄像头的软件，并在 Windows 设置 → 隐私和安全性 → "
            "摄像头中允许桌面应用访问；"
            "外接摄像头可尝试 --camera-index 1。",
            value0=index,
        )
    )


class EyeTraxBackend:
    def __init__(self, *, face_model=None, estimator=None):
        if estimator is None:
            from look_to_ask._vendor.eyetrax import GazeEstimator

            estimator = GazeEstimator(face_landmarker_model=face_model)
        self.estimator = estimator
        self.calibrated = False

    @property
    def mapping_label(self):
        return "EyeTrax"

    def features(self, frame):
        features, blink = self.estimator.extract_features(frame)
        if features is None or blink or not np.isfinite(features).all():
            return None
        if not _valid_eye_geometry(features):
            return None
        return features

    def calibrate(self, features, targets):
        self.calibrated = False
        # This is EyeTrax's existing personal coordinate mapping, not vision-model training.
        self.estimator.train(features, targets)
        diagnostics = inspect_calibration_fit(
            self.estimator.predict(features), targets, feature_count=np.asarray(features).shape[1]
        )
        self.calibrated = True
        return diagnostics

    def predict(self, features):
        if not self.calibrated:
            raise RuntimeError(tr("请先完成校准。"))
        return self.estimator.predict([features])[0]

    def close(self):
        self.calibrated = False
        self.estimator.close()
