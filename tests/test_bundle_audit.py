"""Optional proprietary GPU runtimes must not leak into the ordinary release bundle."""

import pytest

from scripts.audit_bundle import audit_bundle


def test_native_audit_rejects_statically_embedded_fftw_even_with_lgpl_label(tmp_path):
    library = tmp_path / "_internal/av.libs/avformat-62.dll"
    library.parent.mkdir(parents=True)
    library.write_bytes(b"LGPL version 3 or later\0fftw_codelet_q1bv_2\0")
    with pytest.raises(ValueError, match="FFTW"):
        audit_bundle(tmp_path)


@pytest.mark.parametrize(
    "name",
    [
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "cudnn64_9.dll",
        "cudnn_ops64_9.dll",
        "cudart64_12.dll",
    ],
)
def test_standard_bundle_rejects_optional_nvidia_libraries(tmp_path, name):
    licenses = tmp_path / "_internal/LICENSES"
    licenses.mkdir(parents=True)
    (licenses / "LGPL.txt").write_text("test license fixture")
    (tmp_path / "_internal" / name).write_bytes(b"not a real library")
    with pytest.raises(ValueError, match="NVIDIA"):
        audit_bundle(tmp_path)


@pytest.mark.parametrize(
    "name",
    [
        "_internal/look_to_ask/_vendor/fovea/features.py",
        "tools/webgazer/core.mjs",
        "compare-webgazer.cmd",
    ],
)
def test_current_bundle_rejects_retired_experiment_files(tmp_path, name):
    licenses = tmp_path / "_internal/LICENSES"
    licenses.mkdir(parents=True)
    (licenses / "LGPL.txt").write_text("test license fixture")
    file = tmp_path / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("retired experiment fixture")
    with pytest.raises(ValueError, match="Retired experiment"):
        audit_bundle(tmp_path)
