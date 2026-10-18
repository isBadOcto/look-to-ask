"""Real upstream inference on an explicitly artificial no-face unit fixture.

No positive gaze accuracy is claimed. The cached pretrained asset is required;
tests do not download models or access the camera.
"""

from pathlib import Path

import numpy as np
import pytest

from look_to_ask.gaze import EyeTraxBackend


def test_real_landmarker_rejects_blank_image_and_closes():
    model = Path.home() / ".cache" / "eyetrax" / "mediapipe" / "face_landmarker.task"
    if not model.exists():
        pytest.skip("Pretrained model cache absent; run --check-engine explicitly first")
    backend = EyeTraxBackend(face_model=model)
    try:
        assert backend.features(np.zeros((480, 640, 3), dtype=np.uint8)) is None
        assert not backend.calibrated
    finally:
        backend.close()


def test_upstream_ridge_calibration_predicts_from_features_not_cursor():
    from look_to_ask._vendor.eyetrax.models.ridge import RidgeModel

    # Deliberately synthetic mathematical fixture, never a runtime input mode.
    features = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=float)
    targets = features * [1000, 800]
    model = RidgeModel(alpha=0.001)
    model.train(features, targets)
    prediction = model.predict([[0.75, 0.25]])[0]
    np.testing.assert_allclose(prediction, [750, 200], atol=1)


def test_real_backend_calibrates_and_predicts_with_upstream_eyetrax(eye_vector):
    model = Path.home() / ".cache" / "eyetrax" / "mediapipe" / "face_landmarker.task"
    if not model.exists():
        pytest.skip("Pretrained model cache absent; run --check-engine explicitly first")
    positions = [(0.5, 0.5)] + [
        (x, y) for x in (0.2, 0.5, 0.8) for y in (0.2, 0.5, 0.8) if (x, y) != (0.5, 0.5)
    ]
    # Explicit mathematical geometry, not camera frames or a claim of human precision.
    features = np.array([eye_vector(x, y) for x, y in positions for _ in range(3)])
    targets = np.repeat(np.array(positions) * [1000, 800], 3, axis=0)
    backend = EyeTraxBackend(face_model=model)
    try:
        diagnostics = backend.calibrate(features, targets)
        assert diagnostics.feature_count == 486
        assert diagnostics.sample_count == 27
        sample = eye_vector(0.65, 0.35)
        prediction = backend.predict(sample)
        assert np.isfinite(prediction).all()
        np.testing.assert_allclose(prediction, backend.estimator.predict([sample])[0])
        assert backend.calibrated
    finally:
        backend.close()
