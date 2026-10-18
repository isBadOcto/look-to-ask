"""Stage reviewed FFmpeg libraries and repair imports; never mutate installed packages."""

import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import re
import sys
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = re.compile(
    r"^(avcodec|avdevice|avfilter|avformat|avutil|swresample|swscale)-(\d+)(?:-[a-f0-9]+)?\.dll$",
    re.I,
)


def microsoft_runtime(name):
    leaf = Path(name.replace("\\", "/")).name.lower()
    return (
        leaf.startswith(("msvcp", "vcruntime", "vcomp", "concrt", "api-ms-win-"))
        or leaf == "ucrtbase.dll"
    )


def allowed_binary(name):
    leaf = Path(name.replace("\\", "/")).name.lower()
    if microsoft_runtime(name):
        return False
    if leaf.startswith(
        ("cublas", "cudnn", "cudart", "nvrtc", "opencv_videoio_ffmpeg", "opengl32sw")
    ):
        return False
    if "portaudio" in leaf and leaf != "libportaudio64bit.dll":
        return False
    match = FFMPEG.fullmatch(leaf)
    return not match or leaf == f"{match[1]}-{match[2]}.dll"


def canonical_ffmpeg(name):
    match = FFMPEG.fullmatch(name)
    return f"{match[1]}-{match[2]}.dll" if match else name


def patch_imports(source, target, transform):
    """Only shorten PE import strings in a copy, preserving code and import-table layout."""
    data = bytearray(Path(source).read_bytes())
    changes = []
    with pefile.PE(data=bytes(data)) as pe:
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            old = entry.dll.decode("ascii")
            new = transform(old)
            if new == old:
                continue
            if len(new) > len(old) or not new.isascii():
                raise ValueError("Replacement import must fit original storage")
            offset = pe.get_offset_from_rva(entry.struct.Name)
            data[offset : offset + len(old) + 1] = new.encode() + b"\0" * (len(old) + 1 - len(new))
            changes.append({"old": old, "new": new})
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_bytes(data)
    return changes


def stage_bindings():
    native = ROOT / ".venv/minimal-ffmpeg/output"
    manifest = native / "BUILD.json"
    # The native builder writes its validated manifest before packaging can proceed.
    if not manifest.is_file():
        raise RuntimeError("Run scripts/build_minimal_ffmpeg.py before packaging")
    output = ROOT / "build/native-bindings"
    records = []
    for module, folder in (("av", "av"), ("cv2_enumerate_cameras", "cv2_enumerate_cameras")):
        spec = importlib.util.find_spec(module)
        package = Path(spec.origin).parent
        for source in package.rglob("*.pyd"):
            relative = Path(folder) / source.relative_to(package)
            target = output / relative
            transform = (
                canonical_ffmpeg
                if module == "av"
                else (lambda name: "MSVCP140.dll" if name.lower().startswith("msvcp140-") else name)
            )
            changes = patch_imports(source, target, transform)
            records.append(
                {
                    "path": relative.as_posix(),
                    "changes": changes,
                    "original_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            )
    (ROOT / "build/LICENSES/BINDING-IMPORT-CHANGES.json").write_text(
        json.dumps(records, indent=2), "utf-8"
    )
    return output, native


def apply_native_policy(binaries):
    stage, native = stage_bindings()
    result = []
    for name, source, kind in binaries:
        if not allowed_binary(name) or "av.libs/" in name.replace("\\", "/").lower():
            continue
        replacement = stage / name
        if Path(name).name.lower() == "libiomp5md.dll":
            replacement = ROOT / ".venv/native-runtime/output/libiomp5md.dll"
            if not replacement.is_file():
                raise RuntimeError("Run scripts/prepare_native_runtime.py before packaging")
        selected = replacement if replacement.is_file() else Path(source)
        trusted = (ROOT / ".venv", ROOT / "build", Path(sys.base_prefix))
        if not any(selected.resolve().is_relative_to(path.resolve()) for path in trusted):
            raise RuntimeError("Native binary source is outside the reviewed environment: " + name)
        result.append((name, str(selected), kind))
    libraries = list(native.rglob("*.dll"))
    libraries = [path for path in libraries if FFMPEG.fullmatch(path.name)]
    if len(libraries) != 7:
        raise RuntimeError("Expected exactly seven minimal FFmpeg shared libraries")
    result.extend(("av.libs/" + path.name, str(path), "BINARY") for path in libraries)
    return result


def stage_sklearn_loader():
    """Redirect the wheel's absolute CRT preloads to Windows' installed system runtime."""
    source = Path(metadata.distribution("scikit-learn").locate_file("sklearn/_distributor_init.py"))
    original = source.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if metadata.version("scikit-learn") != "1.6.1" or digest != (
        "81c3269d5a0d57301c9eb529d74856f91f06ac935d50e9db84dccb8f7e90c70c"
    ):
        raise RuntimeError("Review the scikit-learn runtime loader after dependency changes")
    text = original.decode("utf-8")
    for variable, filename in (
        ("vcomp140_dll_filename", "vcomp140.dll"),
        ("msvcp140_dll_filename", "msvcp140.dll"),
    ):
        text = text.replace(
            f"WinDLL(op.abspath({variable}))", f'WinDLL("{filename}", winmode=0x800)'
        )
    target = ROOT / "build/native-bindings/sklearn/_distributor_init.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, "utf-8")
    notices = ROOT / "build/LICENSES"
    notices.mkdir(parents=True, exist_ok=True)
    (notices / "SKLEARN-LOADER-CHANGES.json").write_text(
        json.dumps(
            {
                "module": "sklearn._distributor_init",
                "version": "1.6.1",
                "original_sha256": digest,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "change": (
                    "Only two CRT preload paths changed to LOAD_LIBRARY_SEARCH_SYSTEM32; "
                    "numerical code unchanged"
                ),
            },
            indent=2,
        ),
        "utf-8",
    )
    return target
