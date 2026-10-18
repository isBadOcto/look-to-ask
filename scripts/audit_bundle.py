"""Inspect bundle contents and record relative filenames/hashes, never user data."""

import hashlib
import json
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.native_packaging import FFMPEG, allowed_binary  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def audit_bundle(bundle):
    bundle = Path(bundle)
    forbidden = {".pkl", ".task", ".wav", ".mp3", ".mp4", ".safetensors"}
    entries = []
    for file in sorted(bundle.rglob("*")):
        if not file.is_file():
            continue
        name = file.relative_to(bundle).as_posix()
        lower = name.lower()
        if file.suffix.lower() == ".dll" and "av.libs/" in lower:
            if b"fftw_" in file.read_bytes().lower():
                raise ValueError("Unexpected FFTW code in FFmpeg: " + name)
        if (
            "webgazer" in lower
            or "/_vendor/fovea/" in lower
            or lower.endswith("look_to_ask/mapping.py")
        ):
            raise ValueError("Retired experiment in current bundle: " + name)
        if file.suffix.lower() in forbidden or file.name in ("settings.json", ".env"):
            raise ValueError("Unexpected private/model file in bundle: " + name)
        if any(word in lower for word in ("x264", "x265", "pyvirtualcam", "opencv_videoio_ffmpeg")):
            raise ValueError("Unexpected unused/GPL codec: " + name)
        if file.suffix.lower() == ".dll" and file.name.lower().startswith(
            ("cublas", "cudnn", "cudart", "nvrtc")
        ):
            raise ValueError(
                "Optional NVIDIA runtime must remain outside the standard bundle: " + name
            )
        if file.suffix.lower() == ".dll" and not allowed_binary(name):
            raise ValueError("Unreviewed/system native library: " + name)
        if file.name == "direct_url.json" and "file:///" in file.read_text("utf-8"):
            raise ValueError("Local dependency path in bundle metadata")
        entries.append(
            {
                "path": name,
                "size": file.stat().st_size,
                "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            }
        )
    if not (bundle / "_internal/LICENSES").is_dir():
        raise ValueError("Missing third-party notices")
    if not any("lgpl" in p["path"].lower() for p in entries):
        raise ValueError("Missing LGPL license text")
    native = json.loads((bundle / "_internal/LICENSES/FFMPEG-BUILD.json").read_text("utf-8"))
    expected = {entry["name"]: entry["sha256"] for entry in native["dlls"]}
    actual = {
        Path(entry["path"]).name: entry["sha256"]
        for entry in entries
        if "/av.libs/" in entry["path"] and entry["path"].endswith(".dll")
    }
    if (
        len(expected) != 7
        or actual != expected
        or not all(FFMPEG.fullmatch(name) for name in actual)
    ):
        raise ValueError("FFmpeg binaries do not match the verified minimal build")
    runtime = json.loads(
        (bundle / "_internal/LICENSES/NATIVE-RUNTIME-PROVENANCE.json").read_text("utf-8")
    )
    openmp = [entry for entry in entries if entry["path"].endswith("/libiomp5md.dll")]
    if len(openmp) != 1 or openmp[0]["sha256"] != runtime["openmp"]["sha256"]:
        raise ValueError("Intel OpenMP does not match the documented redistributable")
    for required in (
        "Intel-Runtime-Terms.txt",
        "NativeRuntime/Intel-OpenMP/fredist.txt",
        "NativeRuntime/Intel-OpenMP/LICENSE.txt",
        "FFmpeg-BuildRuntime/GCC-COPYING.RUNTIME",
    ):
        if not (bundle / "_internal/LICENSES" / required).is_file():
            raise ValueError("Missing native component terms: " + required)
    return entries


def main():
    entries = audit_bundle(ROOT / "dist/LookToAsk")
    (ROOT / "dist/BUNDLE-MANIFEST.json").write_text(json.dumps(entries, indent=2), "utf-8")
    print(
        "BUNDLE_AUDIT_OK",
        len(entries),
        "files",
        round(sum(p["size"] for p in entries) / 1048576, 1),
        "MiB",
    )


if __name__ == "__main__":
    main()
