"""Explicit numerical fixtures check metrics, never fabricate runtime gaze results."""

import numpy as np
import pytest

from look_to_ask.validation import inspect_calibration_fit, measure_accuracy


def test_accuracy_reports_centre_and_edges_separately_and_balances_points():
    points = [(500, 400), (80, 80), (920, 720)]
    # Different frame counts must not let the centre dominate the score.
    targets = np.array([points[0]] * 10 + [points[1]] * 2 + [points[2]] * 2)
    predictions = targets + np.array([[3, 4]] * 10 + [[30, 40]] * 2 + [[60, 80]] * 2)
    report = measure_accuracy(predictions, targets, points, 1000, 800, "quick")
    assert report.centre_error == pytest.approx(5)
    assert report.edge_error == pytest.approx(75)
    assert report.mean_error == pytest.approx((5 + 50 + 100) / 3)
    assert report.points[-1].bias_x == pytest.approx(60)
    assert report.points[-1].bias_y == pytest.approx(80)
    assert report.points[-1].sample_count == 2


def test_accuracy_does_not_clip_offscreen_predictions_to_make_error_look_smaller():
    points = [(500, 400), (80, 80)]
    targets = np.array(points)
    predictions = np.array([[500, 400], [-220, 80]])
    report = measure_accuracy(predictions, targets, points, 1000, 800, "dense")
    assert report.edge_error == pytest.approx(300)
    assert report.outside_fraction == pytest.approx(0.5)
    assert "逻辑像素" in report.format_text()
    assert "25 点" in report.format_text()


def test_incomplete_or_nonfinite_validation_is_not_reported_as_success():
    points = [(500, 400), (80, 80)]
    with pytest.raises(ValueError, match="每个"):
        measure_accuracy([[500, 400]], [[500, 400]], points, 1000, 800, "quick")
    with pytest.raises(ValueError, match="有限"):
        measure_accuracy([[float("nan"), 400], [80, 80]], points, points, 1000, 800, "quick")


def test_fit_diagnostics_are_explicitly_in_sample_and_balance_target_counts():
    targets = np.array([[500, 400]] * 10 + [[80, 80]] * 2 + [[920, 720]] * 2)
    predictions = targets + np.array([[3, 4]] * 10 + [[30, 40]] * 2 + [[60, 80]] * 2)
    report = inspect_calibration_fit(predictions, targets, feature_count=51)
    assert report.centre_error == pytest.approx(5)
    assert report.mean_error == pytest.approx((5 + 50 + 100) / 3)
    assert report.worst_error == pytest.approx(100)
    assert report.centre_bias == pytest.approx((3, 4))
    assert report.sample_count == 14
    assert report.target_count == 3
    text = report.format_text()
    assert "校准内部诊断" in text
    assert "不是独立精度" in text
    assert "51" in text


def test_bad_fit_outputs_do_not_produce_plausible_diagnostics():
    with pytest.raises(ValueError, match="有限"):
        inspect_calibration_fit([[float("nan"), 200]], [[500, 400]], 3)
