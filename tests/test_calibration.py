"""Deterministic unit fixtures; these do not demonstrate real gaze accuracy."""

import numpy as np
import pytest

from look_to_ask.calibration import CalibrationError, CalibrationSession, ScreenRect


def test_screen_clamps_local_coordinates_and_applies_primary_screen_origin():
    screen = ScreenRect(-1920, 100, 1920, 1080)
    assert screen.to_global((-10, 1200)) == (-1920, 1179)
    assert screen.to_global((960, 540)) == (-960, 640)
    assert screen.to_global((float("nan"), 1)) is None
    assert screen.to_global((1, float("inf"))) is None


def test_nine_points_are_unique_and_inside_screen():
    session = CalibrationSession(1920, 1080)
    assert len(set(session.points)) == 9
    assert session.points[0] == (960, 540)
    assert all(0 < x < 1920 and 0 < y < 1080 for x, y in session.points)


def test_wait_for_visible_target_then_settle_and_reject_invalid_features():
    session = CalibrationSession(1000, 800)
    session.observe(np.ones(3), 100)
    assert session.sample_count == 0  # Target hasn't been painted/acknowledged.
    session.target_visible(100)
    session.observe(None, 100.1)
    session.observe(np.array([float("nan"), 1, 2]), 100.2)
    session.observe(np.ones(3), 101)
    session.observe(np.ones(3), 101.9)
    assert session.sample_count == 0
    session.observe(np.ones(3), 102.01)
    assert session.sample_count == 1


def test_every_target_requires_enough_real_samples_and_training_requires_completion():
    session = CalibrationSession(1000, 800, settling=0, sample_seconds=1, min_samples=3)
    with pytest.raises(CalibrationError, match="完成"):
        session.training_data()
    for index in range(9):
        start = index * 10.0
        session.target_visible(start)
        session.observe(np.array([index, 1, 2]), start)
        session.observe(None, start + 0.3)  # No face/blink does not become a sample.
        session.observe(np.array([index, 1, 2]), start + 0.5)
        session.observe(np.array([index, 1, 2]), start + 1.1)
        assert session.index == index + 1
    assert session.done
    features, targets = session.training_data()
    assert features.shape == (27, 3)
    assert targets.shape == (27, 2)
    assert tuple(targets[-1]) == session.points[-1]


def test_no_face_times_out_instead_of_training_an_incomplete_model():
    session = CalibrationSession(1000, 800, timeout=15)
    session.target_visible(0)
    with pytest.raises(CalibrationError, match="超时"):
        session.observe(None, 15.1)
    assert not session.done


def test_feature_dimension_changes_are_not_silently_accepted():
    session = CalibrationSession(1000, 800, settling=0)
    session.target_visible(0)
    session.observe(np.ones(3), 0)
    with pytest.raises(CalibrationError, match="维度"):
        session.observe(np.ones(4), 0.1)


def test_dense_grid_covers_edges_with_25_unique_targets_and_starts_at_centre():
    session = CalibrationSession(1920, 1080, profile="dense")
    assert len(set(session.points)) == session.total == 25
    assert session.points[0] == (960, 540)
    assert min(x for x, _ in session.points) == 77
    assert max(x for x, _ in session.points) == 1843
    assert min(y for _, y in session.points) == 64
    assert max(y for _, y in session.points) == 1016


def test_dense_grid_finishes_only_after_all_25_targets():
    session = CalibrationSession(
        1920, 1080, profile="dense", settling=0, sample_seconds=0, min_samples=1
    )
    for index in range(25):
        session.target_visible(index)
        session.observe(np.ones(3), index)
        assert session.done == (index == 24)
    features, targets = session.training_data()
    assert features.shape == (25, 3)
    assert targets.shape == (25, 2)


def test_validation_uses_new_nine_point_session_without_changing_training_grid():
    session = CalibrationSession(1920, 1080, profile="validation")
    assert session.total == 9
    assert session.points[0] == (960, 540)
    assert min(x for x, _ in session.points) == 115
    with pytest.raises(ValueError, match="模式"):
        CalibrationSession(1920, 1080, profile="unknown")


def test_validation_samples_cannot_be_used_to_fit_calibration():
    session = CalibrationSession(
        1920, 1080, profile="validation", settling=0, sample_seconds=0, min_samples=1
    )
    for index in range(9):
        session.target_visible(index)
        session.observe(np.array([100, 200]), index)
    assert session.sample_data()[0].shape == (9, 2)
    with pytest.raises(CalibrationError, match="不能"):
        session.training_data()
