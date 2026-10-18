"""Camera doubles test cleanup only; runtime always uses the actual camera."""

import numpy as np
import pytest

from look_to_ask.gaze import CameraError, EyeTraxBackend, open_camera, prediction_on_screen


class Capture:
    def __init__(self, opened=True, readable=True):
        self.opened = opened
        self.readable = readable
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        return self.readable, np.zeros((2, 2, 3), dtype=np.uint8)

    def set(self, *_args):
        return True

    def release(self):
        self.released = True


def test_camera_falls_back_and_releases_failed_backend():
    captures = [Capture(readable=False), Capture()]
    calls = []

    def factory(index, api):
        calls.append((index, api))
        return captures[len(calls) - 1]

    camera = open_camera(0, capture_factory=factory)
    assert camera is captures[1]
    assert captures[0].released
    assert len(calls) == 2


def test_named_camera_does_not_fall_back_to_another_backends_index():
    import cv2

    calls = []

    def factory(index, api):
        calls.append((index, api))
        return Capture(opened=api == cv2.CAP_MSMF)

    with pytest.raises(CameraError):
        open_camera(2, api_preference=cv2.CAP_DSHOW, capture_factory=factory)
    assert calls == [(2, cv2.CAP_DSHOW)]


def test_unavailable_camera_has_actionable_error_and_releases_all_handles():
    captures = []

    def factory(*_args):
        capture = Capture(opened=False)
        captures.append(capture)
        return capture

    with pytest.raises(CameraError, match="隐私"):
        open_camera(0, capture_factory=factory)
    assert all(capture.released for capture in captures)


@pytest.mark.parametrize("resolution", [(1280, 720), (1920, 1080)])
def test_hd_request_uses_frame_size_to_detect_ignored_setting_and_falls_back(resolution):
    class SizedCapture(Capture):
        def __init__(self, size):
            super().__init__()
            self.size = size
            self.settings = {}

        def read(self):
            width, height = self.size
            return True, np.zeros((height, width, 3), dtype=np.uint8)

        def set(self, prop, value):
            self.settings[prop] = value
            return True  # A successful set does not guarantee the requested frame size.

    import cv2

    captures = [SizedCapture((640, 480)), SizedCapture(resolution)]
    remaining = iter(captures)
    camera = open_camera(0, resolution=resolution, capture_factory=lambda *_args: next(remaining))
    assert camera is captures[1]
    assert captures[0].released
    assert camera.settings[cv2.CAP_PROP_FRAME_WIDTH] == resolution[0]
    assert camera.settings[cv2.CAP_PROP_FRAME_HEIGHT] == resolution[1]


@pytest.mark.parametrize("resolution", [(1280, 720), (1920, 1080)])
def test_unsupported_hd_is_explicit_failure_and_releases_all_handles(resolution):
    class VgaCapture(Capture):
        def read(self):
            return True, np.zeros((480, 640, 3), dtype=np.uint8)

    captures = [VgaCapture(), VgaCapture()]
    remaining = iter(captures)
    with pytest.raises(CameraError, match=f"{resolution[0]}×{resolution[1]}.*640×480"):
        open_camera(0, resolution=resolution, capture_factory=lambda *_args: next(remaining))
    assert all(capture.released for capture in captures)


def test_backend_never_predicts_before_calibration_and_rejects_blinks():
    class Estimator:
        def extract_features(self, _frame):
            return np.ones(3), True

        def predict(self, _features):
            raise AssertionError("Predict must not run without valid calibration")

        def close(self):
            pass

    backend = EyeTraxBackend(estimator=Estimator())
    assert backend.features(np.zeros((2, 2, 3), dtype=np.uint8)) is None
    with pytest.raises(RuntimeError, match="校准"):
        backend.predict(np.ones(3))


@pytest.mark.parametrize(
    "geometry,valid",
    [
        ("normal", True),
        ("moved", True),
        ("flat", False),
        ("left_width", False),
        ("right_width", False),
        ("left_closed", False),
        ("right_closed", False),
        ("nan", False),
    ],
)
def test_existing_feature_validity_gate_is_preserved(eye_vector, geometry, valid):
    from look_to_ask._vendor.eyetrax.constants import (
        LEFT_EYE_INDICES,
        MUTUAL_INDICES,
        RIGHT_EYE_INDICES,
    )

    indices = LEFT_EYE_INDICES + RIGHT_EYE_INDICES + MUTUAL_INDICES
    vector = eye_vector(shift=(2, -1), scale=1.5) if geometry == "moved" else eye_vector()
    coordinates = vector[:-3].reshape(-1, 3)
    if geometry == "flat":
        coordinates[:] = 0
    elif geometry in ("left_width", "right_width"):
        outer, inner = (33, 133) if geometry == "left_width" else (263, 362)
        coordinates[indices.index(inner), 0] = coordinates[indices.index(outer), 0] + 0.007
    elif geometry in ("left_closed", "right_closed"):
        lids = (
            (159, 158, 157, 173, 160, 145, 144, 163, 153)
            if geometry == "left_closed"
            else (386, 385, 384, 398, 387, 374, 373, 380, 382)
        )
        coordinates[[indices.index(i) for i in lids], 1] = 0
    elif geometry == "nan":
        vector[0] = np.nan

    class Estimator:
        def extract_features(self, _frame):
            return vector, False

    result = EyeTraxBackend(estimator=Estimator()).features(np.zeros((2, 2, 3), np.uint8))
    assert (result is vector) if valid else (result is None)


def test_impossible_predictions_are_rejected_instead_of_being_shown_at_the_edge():
    assert prediction_on_screen([-5000, 400], 1920, 1080) is None
    assert prediction_on_screen([6000, 400], 1920, 1080) is None
    assert prediction_on_screen([500, -1], 1920, 1080) is None
    assert prediction_on_screen([float("nan"), 200], 1920, 1080) is None
    assert prediction_on_screen([1919, 1079], 1920, 1080) == (1919, 1079)


def test_calibration_diagnostics_use_actual_estimator_predictions_after_fit(eye_vector):
    class Estimator:
        fitted = False

        def train(self, features, targets):
            assert features.shape == (4, 486)
            assert targets.shape == (4, 2)
            self.fitted = True

        def predict(self, features):
            assert self.fitted
            return np.array([[503, 404], [503, 404], [110, 120], [110, 120]])

    backend = EyeTraxBackend(estimator=Estimator())
    report = backend.calibrate(
        np.array([eye_vector()] * 2 + [eye_vector(0.2, 0.2)] * 2),
        np.array([[500, 400]] * 2 + [[80, 80]] * 2),
    )
    assert backend.calibrated
    assert report.centre_error == pytest.approx(5)
    assert report.mean_error == pytest.approx(27.5)
    assert report.feature_count == 486
    assert "不是独立精度" in report.format_text()


def test_backend_prediction_uses_the_calibrated_eyetrax_estimator(eye_vector):
    class Estimator:
        def train(self, _features, _targets):
            pass

        def predict(self, features):
            return np.tile([900, 700], (len(features), 1))

    positions = [(0.5, 0.5), (0.2, 0.2), (0.8, 0.2), (0.2, 0.8), (0.8, 0.8)]
    backend = EyeTraxBackend(estimator=Estimator())
    backend.calibrate(
        np.array([eye_vector(x, y) for x, y in positions]), np.array(positions) * [1000, 800]
    )
    feature = eye_vector(0.65, 0.35, nuisance=15)
    np.testing.assert_allclose(backend.predict(feature), [900, 700])
    assert backend.calibrated


def test_invalid_fit_predictions_do_not_mark_backend_as_calibrated():
    class Estimator:
        def train(self, _features, _targets):
            pass

        def predict(self, _features):
            return [[float("nan"), 200], [80, 80]]

    backend = EyeTraxBackend(estimator=Estimator())
    with pytest.raises(ValueError, match="有限"):
        backend.calibrate(np.ones((2, 3)), np.array([[500, 400], [80, 80]]))
    assert not backend.calibrated
