"""Build local Windows artifacts; no publish, push or credential access."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from look_to_ask import __version__ as VERSION

ROOT = Path(__file__).resolve().parents[1]


def build_environment():
    """Do not resolve native dependencies from unrelated applications on the caller's PATH."""
    env = {
        key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")
    }
    base = Path(sys.base_prefix)
    windows = Path(os.environ.get("WINDIR", "C:/Windows"))
    env.update(
        PYTHONUTF8="1",
        PATH=os.pathsep.join(
            map(
                str,
                (
                    Path(sys.executable).parent,
                    base,
                    base / "DLLs",
                    windows / "System32",
                    windows,
                ),
            )
        ),
    )
    return env


def source_companion():
    """Every binary delivery receives the exact LGPL sources and its actual build recipe."""
    target = ROOT / f"dist/LookToAsk-{VERSION}-LibrarySources.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as archive:
        source_root = ROOT / "dist/LicenseSources"
        for path in sorted(source_root.rglob("*")):
            if path.is_file():
                archive.write(path, "sources/" + path.relative_to(source_root).as_posix())
        native = ROOT / ".venv/minimal-ffmpeg/output"
        for path in sorted(native.rglob("*")):
            if path.is_file() and path.suffix.lower() not in (".dll", ".a", ".o", ".exe", ".lib"):
                archive.write(path, "ffmpeg-build/" + path.relative_to(native).as_posix())
        runtime = ROOT / ".venv/native-runtime/output"
        for path in sorted(runtime.rglob("*")):
            if path.is_file() and path.suffix.lower() not in (".dll", ".exe", ".msi", ".cab"):
                archive.write(path, "native-runtime/" + path.relative_to(runtime).as_posix())
        for name in (
            "scripts/build_minimal_ffmpeg.py",
            "scripts/native_packaging.py",
            "scripts/prepare_native_runtime.py",
            "packaging/intel-runtime-header.txt",
            "docs/RELINKING.md",
            "THIRD_PARTY_NOTICES.md",
            "packaging/native-provenance.json",
        ):
            archive.write(ROOT / name, name)


def check_frozen_imports(env):
    """Fail before compiling an installer if bundled imports need the developer's PATH."""
    working = ROOT / "build/frozen-import-check"
    working.mkdir(parents=True, exist_ok=True)
    report = working / "report.json"
    report.unlink(missing_ok=True)
    windows = Path(os.environ.get("WINDIR", "C:/Windows"))
    clean = {**env, "PATH": os.pathsep.join(map(str, (windows / "System32", windows)))}
    subprocess.run(
        [str(ROOT / "dist/LookToAsk/LookToAsk.exe"), "--check", "--report", str(report)],
        cwd=working,
        env=clean,
        timeout=60,
        check=True,
    )
    result = json.loads(report.read_text("utf-8"))
    if not result.get("ok") or not result.get("frozen"):
        raise RuntimeError(
            "Frozen dependency import check failed; inspect build/frozen-import-check"
        )
    print("FROZEN_DEPENDENCY_GATE_OK", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nsis", type=Path, default=ROOT / ".venv/tools/nsis-3.13/makensis.exe")
    parser.add_argument(
        "--source-only", action="store_true", help="Refresh source ZIP and hashes only"
    )
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Build on Windows x64")
    if not (ROOT / "dist/LookToAsk").resolve().is_relative_to(ROOT) or not (
        ROOT / "build"
    ).resolve().is_relative_to(ROOT):
        raise RuntimeError("Build output is outside this workspace")
    (ROOT / "dist").mkdir(exist_ok=True)
    if not args.source_only:
        env = build_environment()
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/translations.py"), "compile"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        for script in (
            "fetch_license_sources.py",
            "fetch_rust_notices.py",
            "build_minimal_ffmpeg.py",
            "prepare_native_runtime.py",
            "prepare_build.py",
        ):
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, env=env, check=True
            )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                str(ROOT / "packaging/LookToAsk.spec"),
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
        source_companion()
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/audit_bundle.py")], cwd=ROOT, env=env, check=True
        )
        check_frozen_imports(env)
        if not args.nsis.is_file():
            raise RuntimeError("Supply --nsis with the portable NSIS makensis.exe path")
        subprocess.run(
            [
                str(args.nsis.resolve()),
                "/INPUTCHARSET",
                "UTF8",
                f"/DVERSION={VERSION}",
                str(ROOT / "packaging/installer.nsi"),
            ],
            cwd=ROOT,
            check=True,
        )
        shutil.make_archive(
            str(ROOT / f"dist/LookToAsk-{VERSION}-Windows-x64"), "zip", ROOT / "dist", "LookToAsk"
        )
    with zipfile.ZipFile(
        ROOT / f"dist/LookToAsk-{VERSION}-Source.zip", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for directory in ("src", "docs", "scripts", "packaging", "tests"):
            for path in (ROOT / directory).rglob("*"):
                if any(
                    part.startswith(".")
                    or part.lower().endswith((".egg-info", ".dist-info"))
                    or part.lower()
                    in ("__pycache__", "screenshots", "recordings", "calibration-data")
                    for part in path.relative_to(ROOT).parts
                ):
                    continue
                if (
                    path.is_file()
                    and not path.is_symlink()
                    and (
                        path.name.upper() in ("LICENSE", "COPYING", "NOTICE")
                        or (path.name == "manifest.json" and "_vendor" in path.parts)
                        or path == ROOT / "packaging/native-provenance.json"
                        or path.suffix.lower()
                        in (
                            ".py",
                            ".md",
                            ".txt",
                            ".toml",
                            ".svg",
                            ".ps1",
                            ".cmd",
                            ".nsi",
                            ".spec",
                            ".html",
                            ".ts",
                            ".qm",
                        )
                    )
                ):
                    archive.write(path, path.relative_to(ROOT))
        for name in (
            "README.md",
            "AGENTS.md",
            "PLAN.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "pyproject.toml",
            "requirements-lock.txt",
            ".gitignore",
            ".gitattributes",
            "run.cmd",
        ):
            archive.write(ROOT / name, name)
    with zipfile.ZipFile(ROOT / f"dist/LookToAsk-{VERSION}-Source.zip") as archive:
        if not archive.read("src/look_to_ask/_vendor/eyetrax/LICENSE"):
            raise RuntimeError("Source ZIP is missing the EyeTrax license")
    sums = []
    for path in sorted((ROOT / "dist").glob(f"LookToAsk-{VERSION}-*")):
        if path.is_file():
            sums.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name)
    (ROOT / "dist/SHA256SUMS.txt").write_text("\n".join(sums) + "\n", "utf-8")
    print("LOCAL_SOURCE_ARCHIVE_OK" if args.source_only else "LOCAL_WINDOWS_BUILD_OK")


if __name__ == "__main__":
    main()
