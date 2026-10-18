"""Keep all app-preference writes away from real user data during automated tests."""

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication, QLocale

from look_to_ask._vendor.eyetrax.constants import (
    LEFT_EYE_INDICES,
    MUTUAL_INDICES,
    RIGHT_EYE_INDICES,
)


@pytest.fixture(autouse=True)
def isolated_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))


@pytest.fixture(autouse=True)
def chinese_test_locale():
    """Legacy wording tests use a controlled locale, independent of the host OS."""
    from look_to_ask.i18n import install_language

    previous = QLocale()
    QLocale.setDefault(QLocale("zh_CN"))
    if QCoreApplication.instance():
        install_language("zh")
    yield
    if QCoreApplication.instance():
        install_language("zh")
    QLocale.setDefault(previous)


@pytest.fixture
def eye_vector():
    """Original artificial geometry fixture, never loaded by the app."""

    def make(nx=0.5, ny=0.5, *, shift=(0.0, 0.0), scale=1.0, nuisance=0.0):
        indices = LEFT_EYE_INDICES + RIGHT_EYE_INDICES + MUTUAL_INDICES
        points = {index: np.array([nuisance, nuisance, nuisance]) for index in indices}
        for outer, inner, upper, lower, ring in (
            (33, 133, (159, 158, 157, 173, 160), (145, 144, 163, 153), (468, 469, 470, 471, 472)),
            (263, 362, (386, 385, 384, 398, 387), (374, 373, 380, 382), (473, 474, 475, 476, 477)),
        ):
            left, right = (-0.5, -0.2) if outer == 33 else (0.2, 0.5)
            points[outer] = np.array([left if outer == 33 else right, 0, 0.0])
            points[inner] = np.array([right if outer == 33 else left, 0, 0.0])
            for index in upper:
                points[index] = np.array([(left + right) / 2, 0.06, 0.0])
            for index in lower:
                points[index] = np.array([(left + right) / 2, -0.06, 0.0])
            for index in ring:
                points[index] = np.array([left + (right - left) * nx, 0.06 - 0.12 * ny, 0.0])
        values = np.array([points[index] for index in indices]) * scale
        values[:, :2] += shift
        return np.concatenate([values.ravel(), [nuisance] * 3])

    return make
