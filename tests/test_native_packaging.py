"""Release policy must reject accidental native dependencies before creating artifacts."""

from pathlib import Path

import pytest

from scripts.native_packaging import allowed_binary, patch_imports, stage_sklearn_loader


def test_ssl_auxiliary_data_is_required_and_hash_checked(tmp_path, monkeypatch):
    import hashlib

    from scripts import native_packaging
    from scripts.native_packaging import ssl_runtime_data

    source = tmp_path / "ssl.py"
    source.write_text("cafile='codex-rejected-cas.pem'", "utf-8")
    with pytest.raises(RuntimeError, match="SSL"):
        ssl_runtime_data(source)
    asset = source.with_name("codex-rejected-cas.pem")
    asset.write_text("unreviewed certificate", "ascii")
    with pytest.raises(RuntimeError, match="SSL"):
        ssl_runtime_data(source)
    reviewed_fixture = b"-----BEGIN TRUSTED CERTIFICATE-----\npublic test fixture\n"
    monkeypatch.setattr(
        native_packaging, "SSL_AUXILIARY_SHA256", hashlib.sha256(reviewed_fixture).hexdigest()
    )
    asset.write_bytes(reviewed_fixture)
    assert ssl_runtime_data(source) == [(str(asset), ".")]


def test_unmodified_python_does_not_require_codex_ssl_asset(tmp_path):
    from scripts.native_packaging import ssl_runtime_data

    source = tmp_path / "ssl.py"
    source.write_text("# ordinary CPython SSL module", "utf-8")
    assert ssl_runtime_data(source) == []


@pytest.mark.parametrize(
    "name",
    [
        "MSVCP140.dll",
        "vcruntime140_1.dll",
        "PySide6/VCOMP140.DLL",
        "cameras.libs/msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll",
        "api-ms-win-crt-stdio-l1-1-0.dll",
        "ucrtbase.dll",
        "_sounddevice_data/portaudio-binaries/libportaudio64bit-asio.dll",
        "_sounddevice_data/portaudio-binaries/libportaudio32bit.dll",
        "_sounddevice_data/portaudio-binaries/libportaudio64bit-arm64.dll",
        "av.libs/avformat-62-deadbeef.dll",
    ],
)
def test_unreviewed_or_system_runtime_is_excluded(name):
    assert not allowed_binary(name)


@pytest.mark.parametrize(
    "name",
    [
        "onnxruntime/capi/onnxruntime.dll",
        "PySide6/Qt6Core.dll",
        "av.libs/avcodec-62.dll",
        "av.libs/swresample-6.dll",
        "_sounddevice_data/portaudio-binaries/libportaudio64bit.dll",
    ],
)
def test_required_libraries_remain(name):
    assert allowed_binary(name)


def test_actual_camera_import_can_be_repaired_without_redistributing_crt(tmp_path):
    import importlib.util

    import pefile

    spec = importlib.util.find_spec("cv2_enumerate_cameras")
    original = next(Path(spec.origin).parent.rglob("_windows_backend*.pyd"))
    target = tmp_path / original.name
    changes = patch_imports(
        original,
        target,
        lambda name: "MSVCP140.dll" if name.lower().startswith("msvcp140-") else name,
    )
    assert len(changes) == 1
    with pefile.PE(str(target)) as pe:
        names = [item.dll.decode() for item in pe.DIRECTORY_ENTRY_IMPORT]
    assert "MSVCP140.dll" in names
    assert not any("msvcp140-" in name.lower() for name in names)


def test_scikit_loader_preloads_only_installed_system_runtime(tmp_path, monkeypatch):
    from scripts import native_packaging

    monkeypatch.setattr(native_packaging, "ROOT", tmp_path)
    calls = []
    monkeypatch.setattr("ctypes.WinDLL", lambda name, **options: calls.append((name, options)))
    loader = stage_sklearn_loader()
    exec(compile(loader.read_text("utf-8"), str(loader), "exec"), {"__file__": str(loader)})
    assert calls == [("vcomp140.dll", {"winmode": 0x800}), ("msvcp140.dll", {"winmode": 0x800})]
    assert not list(tmp_path.rglob("*.dll"))
