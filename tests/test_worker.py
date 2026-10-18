"""Thread lifecycle tests use explicit doubles; no double is shipped as a runtime mode."""

import time
from types import SimpleNamespace

import numpy as np
import pytest

from look_to_ask import worker as worker_module
from look_to_ask.calibration import CalibrationSession, ScreenRect
from look_to_ask.validation import FitDiagnostics
from look_to_ask.worker import TrackingWorker


def test_camera_is_released_when_model_initialization_fails():
    class Camera:
        released = False

        def release(self):
            self.released = True

    camera = Camera()

    def broken_backend(**_kwargs):
        raise RuntimeError("test model error")

    worker = TrackingWorker(
        ScreenRect(0, 0, 1000, 800),
        camera_factory=lambda _index, **_kwargs: camera,
        backend_factory=broken_backend,
    )
    worker.run()
    assert camera.released


def test_stop_request_before_start_never_opens_camera():
    def unexpected_camera(_index, **_kwargs):
        raise AssertionError("Stopped worker must not open camera")

    worker = TrackingWorker(ScreenRect(0, 0, 1000, 800), camera_factory=unexpected_camera)
    worker.stop()
    worker.run()


def test_stop_is_an_event_and_does_not_wait_for_worker_event_loop():
    worker = TrackingWorker(ScreenRect(0, 0, 1000, 800))
    started = time.monotonic()
    worker.stop()
    assert time.monotonic() - started < 0.1
    assert worker.stopping


def test_calibration_timeout_reason_remains_visible_until_user_retries(monkeypatch):
    messages = []

    class Camera:
        reads = 0

        def read(self):
            self.reads += 1
            if self.reads >= 4:
                worker.stop()
            return True, np.zeros((2, 2, 3), dtype=np.uint8)

        def release(self):
            pass

    class Backend:
        calibrated = False

        def features(self, _frame):
            return None

        def close(self):
            pass

    ticks = iter(range(100, 200))
    monkeypatch.setattr(worker_module, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    monkeypatch.setattr(
        worker_module,
        "CalibrationSession",
        lambda width, height, **kwargs: CalibrationSession(width, height, timeout=0.1, **kwargs),
    )
    worker = TrackingWorker(
        ScreenRect(0, 0, 1000, 800),
        camera_factory=lambda _index, **_kwargs: Camera(),
        backend_factory=lambda **_kwargs: Backend(),
    )
    worker.status.connect(messages.append)
    worker.recalibrate()
    worker.target_visible(0)
    worker.run()
    assert "超时" in messages[-1]


def test_validation_predicts_from_new_frames_without_fitting_or_clipping(monkeypatch):
    reports = []
    captured = {}

    class Camera:
        reads = 0

        def read(self):
            self.reads += 1
            if self.reads > 10:
                worker.stop()
            return True, np.zeros((2, 2, 3), dtype=np.uint8)

        def release(self):
            pass

    class Backend:
        calibrated = True
        predictions = 0

        def features(self, _frame):
            return np.ones(3)

        def predict(self, _features):
            self.predictions += 1
            return np.array([-220, 200])  # Must remain outside the screen in the report.

        def calibrate(self, *_args):
            raise AssertionError("Validation must never fit its own samples")

        def close(self):
            pass

    def session_factory(width, height, **kwargs):
        session = CalibrationSession(
            width, height, settling=0, sample_seconds=0, min_samples=1, **kwargs
        )
        captured["session"] = session
        return session

    monkeypatch.setattr(worker_module, "CalibrationSession", session_factory)
    backend = Backend()
    worker = TrackingWorker(
        ScreenRect(0, 0, 1000, 800),
        camera_factory=lambda _index, **_kwargs: Camera(),
        backend_factory=lambda **_kwargs: backend,
    )
    worker.target.connect(lambda index, _x, _y: worker.target_visible(index))
    worker.validation_finished.connect(reports.append)
    # An Esc queued during the final sample may arrive after completion.
    worker.validation_finished.connect(lambda _report: worker.cancel_calibration())
    worker.validate()
    worker.run()
    predictions, _targets = captured["session"].sample_data()
    assert backend.predictions >= 9
    assert len(reports) == 1
    assert np.all(predictions[:, 0] == -220)
    assert predictions.shape[1] == 2
    assert "独立精度测量" in reports[0] and "100.0%" in reports[0]
    assert backend.calibrated


def test_cancelling_validation_keeps_the_existing_calibration():
    class Backend:
        calibrated = True

        def features(self, _frame):
            worker.stop()
            return None

        def close(self):
            pass

    class Camera:
        def read(self):
            return True, np.zeros((2, 2, 3), dtype=np.uint8)

        def release(self):
            pass

    backend = Backend()
    worker = TrackingWorker(
        ScreenRect(0, 0, 1000, 800),
        camera_factory=lambda _index, **_kwargs: Camera(),
        backend_factory=lambda **_kwargs: backend,
    )
    worker.validate()
    worker.cancel_calibration()
    worker.cancel_calibration()  # Repeated Esc must be idempotent.
    worker.run()
    assert backend.calibrated


@pytest.mark.parametrize(
    "raw_prediction,filtered_prediction",
    [([6000, 400], (500, 400)), ([500, 400], (6000, 400))],
)
def test_tracking_never_disguises_raw_or_filtered_outliers_as_edge_markers(
    monkeypatch, raw_prediction, filtered_prediction
):
    from look_to_ask._vendor.eyetrax.filters import kalman_ema

    displayed = []

    class Smoother:
        def step(self, _x, _y):
            return filtered_prediction

    class Backend:
        calibrated = True

        def features(self, _frame):
            worker.stop()
            return np.ones(3)

        def predict(self, _features):
            return np.array(raw_prediction)

        def close(self):
            pass

    class Camera:
        def read(self):
            return True, np.zeros((2, 2, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(kalman_ema, "KalmanEMASmoother", Smoother)
    worker = TrackingWorker(
        ScreenRect(0, 0, 1920, 1080),
        camera_factory=lambda _index, **_kwargs: Camera(),
        backend_factory=lambda **_kwargs: Backend(),
    )
    worker.gaze.connect(lambda x, y, _time: displayed.append((x, y)))
    worker.run()
    assert displayed == []


@pytest.mark.parametrize("resolution", [(1280, 720), (1920, 1080)])
def test_fit_diagnostics_and_repeated_measurements_identify_the_same_calibration(
    monkeypatch, resolution
):
    diagnostics = []
    reports = []
    requested = []

    class Camera:
        reads = 0

        def read(self):
            self.reads += 1
            if self.reads > 100:
                worker.stop()
            return True, np.zeros((resolution[1], resolution[0], 3), dtype=np.uint8)

        def release(self):
            pass

    class Backend:
        calibrated = False

        def features(self, _frame):
            return np.ones(3)

        def calibrate(self, _features, _targets):
            self.calibrated = True
            return FitDiagnostics(9, 9, 3, 5, 10, 20, (3, 4))

        def predict(self, _features):
            return np.array([500, 400])

        def close(self):
            pass

    monkeypatch.setattr(
        worker_module,
        "CalibrationSession",
        lambda width, height, **kwargs: CalibrationSession(
            width, height, settling=0, sample_seconds=0, min_samples=1, **kwargs
        ),
    )

    def camera_factory(index, *, resolution):
        requested.append((index, resolution))
        return Camera()

    worker = TrackingWorker(
        ScreenRect(0, 0, 1000, 800),
        camera_resolution=resolution,
        camera_factory=camera_factory,
        backend_factory=lambda **_kwargs: Backend(),
    )
    worker.target.connect(lambda index, _x, _y: worker.target_visible(index))
    worker.fit_diagnostics.connect(diagnostics.append)
    worker.calibrated.connect(worker.validate)

    def next_measurement(report):
        reports.append(report)
        if len(reports) == 1:
            worker.validate()
        elif len(reports) == 2:
            worker.recalibrate()
        else:
            worker.stop()

    worker.validation_finished.connect(next_measurement)
    worker.recalibrate()
    worker.run()
    assert len(diagnostics) == 2
    assert requested == [(0, resolution)]
    label = f"{resolution[0]}×{resolution[1]}"
    assert f"请求分辨率 {label}" in diagnostics[0]
    assert f"实际分辨率 {label}" in diagnostics[0]
    assert len(reports) == 3
    first_id = diagnostics[0].splitlines()[0]
    second_id = diagnostics[1].splitlines()[0]
    assert first_id != second_id
    assert first_id in reports[0] and first_id in reports[1]
    assert second_id in reports[2]
    assert "测量第 1 次" in reports[0]
    assert "测量第 2 次" in reports[1]
    assert "测量第 1 次" in reports[2]


def test_full_hd_driver_downgrade_during_tracking_stops_and_releases_camera():
    errors, extracted = [], []

    class Camera:
        reads = 0
        released = False

        def read(self):
            self.reads += 1
            if self.reads > 2:
                raise AssertionError("A downgraded stream must stop immediately")
            width, height = (1920, 1080) if self.reads == 1 else (1280, 720)
            return True, np.zeros((height, width, 3), dtype=np.uint8)

        def release(self):
            self.released = True

    camera = Camera()
    backend = SimpleNamespace(
        calibrated=False,
        features=lambda frame: extracted.append(frame.shape),
        close=lambda: None,
    )
    worker = TrackingWorker(
        ScreenRect(0, 0, 1920, 1080),
        camera_resolution=(1920, 1080),
        camera_factory=lambda *_args, **_kwargs: camera,
        backend_factory=lambda **_kwargs: backend,
    )
    worker.error.connect(errors.append)
    worker.run()
    assert len(errors) == 1 and "1920×1080" in errors[0] and "1280×720" in errors[0]
    assert extracted == [(1080, 1920, 3)]
    assert camera.released
