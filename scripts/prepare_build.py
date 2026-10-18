"""Prepare public notices, icon and a deterministic dependency inventory, never user data."""

import hashlib
import importlib.metadata as metadata
import json
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]


def is_notice(name):
    value = str(name).replace("\\", "/").lower()
    leaf = value.rsplit("/", 1)[-1]
    return (
        "/licenses/" in "/" + value
        or any(
            word in leaf
            for word in (
                "license",
                "licence",
                "copying",
                "notice",
                "copyright",
                "authors",
                "lgpl",
                "gpl",
                "third-party",
            )
        )
        or leaf
        in (
            "ftl.txt",
            "psf-3.7.0.txt",
            "qt_attribution.json",
            "bufferprocs_py37.h",
            "unzip.h",
            "zip.h",
        )
    )


def notice_path(name):
    """Keep attribution paths while refusing archive or wheel traversal components."""
    parts = Path(str(name).replace("\\", "/")).parts
    return Path(*(part for part in parts if part not in ("..", ".", "/", "\\")))


def collect_archive_notices(archive, destination):
    """Copy public texts without extracting executable/archive-controlled filesystem paths."""

    def keep(name):
        return is_notice(name) or (
            archive.suffix == ".crate"
            and Path(name).name.lower().startswith(("cargo.toml", "readme"))
        )

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as package:
            records = [
                (name, package.read(name))
                for name in package.namelist()
                if not name.endswith("/") and keep(name)
            ]
    else:
        with tarfile.open(archive) as package:
            records = [
                (member.name, package.extractfile(member).read())
                for member in package
                if member.isfile() and keep(member.name)
            ]
    for name, content in records:
        relative = Path(archive.name) / notice_path(name)
        if relative.is_absolute():
            raise RuntimeError("Archive notice path is not relative")
        destination.writestr(relative.as_posix(), content)


def verify_qt_provenance(output):
    source = ROOT / "packaging/native-provenance.json"
    report = json.loads(source.read_text("utf-8"))
    for wheel in report["wheel_comparison"]:
        if metadata.version(wheel["name"]) != wheel["version"]:
            raise RuntimeError("Qt wheel upgrade requires source provenance review")
        distribution = metadata.distribution(wheel["name"])
        for entry in wheel["matched_files"]:
            path = Path(distribution.locate_file(entry["path"]))
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                raise RuntimeError("Qt wheel provenance mismatch: " + entry["path"])
    shutil.copyfile(source, output / "QT-OFFICIAL-PROVENANCE.json")


def supplement_native_notices(output):
    """Some wheels omit license files; use reviewed, version-pinned upstream texts."""
    for name, version, url, digest in (
        (
            "ctranslate2",
            "4.8.3",
            "https://raw.githubusercontent.com/OpenNMT/CTranslate2/v4.8.3/LICENSE",
            "54aa79d9fe3c09e67a16dcd95b9e88676405a6ec174efda31036983cf7672ecb",
        ),
        (
            "tokenizers",
            "0.23.3",
            "https://raw.githubusercontent.com/huggingface/tokenizers/v0.23.3/LICENSE",
            "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
        ),
    ):
        if metadata.version(name) != version:
            raise RuntimeError("Review the upstream license after updating " + name)
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read(65537)
        if hashlib.sha256(content).hexdigest() != digest:
            raise RuntimeError("Upstream license hash mismatch: " + name)
        target = output / name / "LICENSE.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("The build's Python runtime is missing LICENSE.txt")
    target = output / "CPython"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(python_license, target / "LICENSE.txt")
    (target / "VERSION.txt").write_text(sys.version.split()[0] + "\n", "utf-8")


def main():
    output = ROOT / "build/LICENSES"
    if not output.resolve().is_relative_to(ROOT.resolve()):
        raise RuntimeError("License output must stay in the workspace")
    if output.exists():
        shutil.rmtree(output)  # Only the verified, generated license directory.
    output.mkdir(parents=True, exist_ok=True)
    inventory = []
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if not name or name.lower() == "look-to-ask":
            continue
        inventory.append(
            {
                "name": name,
                "version": dist.version,
                "license": dist.metadata.get("License-Expression")
                or dist.metadata.get("License")
                or "",
                "source": dist.metadata.get_all("Project-URL")
                or [dist.metadata.get("Home-page", "")],
            }
        )
        for file in dist.files or []:
            if not is_notice(file):
                continue
            source = Path(dist.locate_file(file))
            if not source.is_file():
                continue
            target = output / name / notice_path(file)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    supplement_native_notices(output)
    verify_qt_provenance(output)
    (output / "BUILD-ENVIRONMENT.json").write_text(
        json.dumps(sorted(inventory, key=lambda i: i["name"].lower()), indent=2), "utf-8"
    )
    for source in (
        ROOT / "LICENSE",
        ROOT / "THIRD_PARTY_NOTICES.md",
        ROOT / "docs/PACKAGING.md",
        ROOT / "docs/RELINKING.md",
    ):
        shutil.copyfile(source, output / source.name)
    shutil.copyfile(ROOT / "dist/LicenseSources/SOURCES.json", output / "SOURCES.json")
    shutil.copyfile(ROOT / ".venv/minimal-ffmpeg/output/BUILD.json", output / "FFMPEG-BUILD.json")
    shutil.copytree(ROOT / ".venv/minimal-ffmpeg/output/LICENSES", output / "FFmpeg-BuildRuntime")
    runtime = ROOT / ".venv/native-runtime/output"
    shutil.copytree(runtime / "LICENSES", output / "NativeRuntime")
    shutil.copyfile(runtime / "PROVENANCE.json", output / "NATIVE-RUNTIME-PROVENANCE.json")
    terms = (ROOT / "packaging/intel-runtime-header.txt").read_text("utf-8")
    terms += (runtime / "LICENSES/Intel-OpenMP/LICENSE.txt").read_text("cp1252")
    terms += "\n\nIntel oneMKL — Intel Simplified Software License\n\n"
    terms += (
        runtime / "LICENSES/oneMKL-2025.3.0/mkl_static-2025.3.0.dist-info/LICENSE.txt"
    ).read_text("utf-8")
    (output / "Intel-Runtime-Terms.txt").write_text(terms, "utf-8")
    with zipfile.ZipFile(output / "UPSTREAM-NOTICES.zip", "w", zipfile.ZIP_DEFLATED) as notices:
        for archive in sorted((ROOT / "dist/LicenseSources").rglob("*")):
            if archive.is_file() and archive.name.endswith(
                (".tar.gz", ".tar.xz", ".crate", ".zip")
            ):
                collect_archive_notices(archive, notices)
    nsis = ROOT / ".venv/tools/nsis-3.13/COPYING"
    if nsis.exists():
        (output / "NSIS").mkdir(exist_ok=True)
        shutil.copyfile(nsis, output / "NSIS/COPYING.txt")
    vad_license = output / "Silero-VAD-LICENSE.txt"
    if not vad_license.exists():
        urllib.request.urlretrieve(
            "https://raw.githubusercontent.com/snakers4/silero-vad/v6.0/LICENSE", vad_license
        )
    app = QApplication.instance() or QApplication([])
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QSvgRenderer(str(ROOT / "src/look_to_ask/assets/logo.svg")).render(painter)
    painter.end()
    image.save(str(ROOT / "build/LookToAsk.png"))
    Image.open(ROOT / "build/LookToAsk.png").save(
        ROOT / "build/LookToAsk.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    app.processEvents()
    print("BUILD_RESOURCES_READY (public licenses/icon only)")


if __name__ == "__main__":
    main()
