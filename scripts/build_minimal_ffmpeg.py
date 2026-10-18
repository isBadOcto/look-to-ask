"""Build the audio-only LGPL FFmpeg DLLs using an isolated, pinned Windows toolchain.

Build-only downloads and intermediate files stay under .venv. No package installation,
system PATH modification, Git operation, device access or publishing is performed.
The existing BSD PyAV extension modules are staged separately by prepare_build.py;
this script builds FFmpeg from source, not those PyAV extension modules.
"""

import argparse
import ctypes
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".venv/minimal-ffmpeg"
TOOLS = ROOT / ".venv/native-tools"
OUTPUT = WORK / "output"
FFMPEG_SHA256 = "ce795707ff1c22e46f5c45ee330990b9fc19924e6f34bd547c73f297df80eb3c"
FFMPEG_REVISION = "e4c7fbf6c0"
FFMPEG_ARCHIVE = ROOT / f"dist/LicenseSources/ffmpeg-{FFMPEG_REVISION}.tar.gz"
WINLIBS_NAME = "winlibs-x86_64-posix-seh-gcc-14.2.0-mingw-w64ucrt-12.0.0-r3.zip"
WINLIBS_URL = (
    "https://github.com/brechtsanders/winlibs_mingw/releases/download/"
    "14.2.0posix-12.0.0-ucrt-r3/" + WINLIBS_NAME
)
ARTIFACTS = (
    (
        WINLIBS_NAME,
        WINLIBS_URL,
        "88868d745b807f083a117ff69348d8bc021ad7389aa503379dbed1866efcaeb9",
        "build-only GCC/MinGW/binutils/make distribution; component notices included",
    ),
    (
        "gcc-14.2.0.tar.xz",
        "https://ftp.gnu.org/gnu/gcc/gcc-14.2.0/gcc-14.2.0.tar.xz",
        "a7b39bc69cbf9e25826c5a60ab26477001f7c08d85cec04bc0e29cabed6f3cc9",
        "GPL-3.0-or-later; libgcc uses GCC Runtime Library Exception 3.1",
    ),
    (
        "mingw-w64-v12.0.0.tar.gz",
        "https://codeload.github.com/mingw-w64/mingw-w64/tar.gz/refs/tags/v12.0.0",
        "fa41d462041ed72e29a5101049e5991d4aea5c552fd75f7ac0074989fc54ceb7",
        "MinGW-w64 runtime: ZPL-2.1 and component-specific notices in COPYING",
    ),
)
LIBRARIES = {
    "avutil-60.dll": "avutil",
    "swresample-6.dll": "swresample",
    "swscale-9.dll": "swscale",
    "avcodec-62.dll": "avcodec",
    "avformat-62.dll": "avformat",
    "avfilter-11.dll": "avfilter",
    "avdevice-62.dll": "avdevice",
}
CONFIGURE_FLAGS = (
    "--arch=x86_64",
    "--target-os=mingw32",
    "--cc=gcc",
    "--cxx=g++",
    "--enable-shared",
    "--disable-static",
    "--disable-autodetect",
    "--disable-gpl",
    "--disable-nonfree",
    "--disable-version3",
    "--disable-network",
    "--disable-programs",
    "--disable-doc",
    "--disable-debug",
    "--disable-x86asm",
    "--disable-pthreads",
    "--enable-w32threads",
    "--disable-everything",
    "--enable-decoder=pcm_s16le,pcm_f32le",
    "--enable-encoder=pcm_s16le",
    "--enable-demuxer=wav",
    "--enable-muxer=wav",
    "--enable-filter=abuffer,abuffersink,aresample,aformat",
    # MinGW's time.h otherwise exposes clock_gettime/nanosleep from winpthreads,
    # even with FFmpeg pthreads disabled. Use FFmpeg's native Win32 time fallback.
    "--extra-cflags=-O2 -D_WIN32_WINNT=0x0A00 -DWIN_PTHREADS_TIME_H",
    "--extra-ldflags=-static-libgcc",
    "--extra-version=looktoask-audio1",
)
SYSTEM_DLLS = {
    "advapi32.dll",
    "bcrypt.dll",
    "crypt32.dll",
    "kernel32.dll",
    "msvcrt.dll",
    "ole32.dll",
    "oleaut32.dll",
    "secur32.dll",
    "shell32.dll",
    "ucrtbase.dll",
    "user32.dll",
    "ws2_32.dll",
}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(name, url, digest):
    destination = TOOLS / name
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix + ".partial")
        print("Downloading pinned build input:", name, flush=True)
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        temporary.replace(destination)
    if sha256(destination) != digest:
        raise RuntimeError("Pinned build input hash mismatch: " + name)
    return destination


def short_path(path):
    """Keep native make and FFmpeg away from workspace whitespace, without moving it."""
    buffer = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetShortPathNameW(str(path.resolve()), buffer, len(buffer))
    if not size or size >= len(buffer) or " " in buffer.value:
        raise RuntimeError("A Windows short path without spaces is required: " + str(path))
    return buffer.value.replace("\\", "/")


def extract_inputs(archive):
    toolchain = TOOLS / "winlibs"
    compiler = toolchain / "mingw64/bin/gcc.exe"
    if not compiler.is_file():
        print("Extracting isolated compiler toolchain", flush=True)
        toolchain.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                target = (toolchain / entry.filename).resolve()
                if not target.is_relative_to(toolchain.resolve()):
                    raise RuntimeError("Unsafe toolchain archive path")
            package.extractall(toolchain)
    source = WORK / "source" / f"FFmpeg-{FFMPEG_REVISION}"
    marker = WORK / "source/.archive-sha256"
    if not marker.is_file() or marker.read_text("ascii").strip() != FFMPEG_SHA256:
        source.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(FFMPEG_ARCHIVE) as package:
            package.extractall(source.parent, filter="data")
        marker.write_text(FFMPEG_SHA256 + "\n", "ascii")
    return toolchain / "mingw64", source


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


def public_text(value):
    """Remove machine-specific paths from public build evidence, keeping raw logs local."""
    if value.startswith("# ./configure "):
        # FFmpeg starts config.log with `set`, which includes the complete inherited
        # shell environment and function bodies. It is not public build evidence.
        start = re.search(r"(?m)^(?:check|test)_[a-z0-9_]+(?: [^(){}\n]+)?$", value)
        if start is None:
            raise RuntimeError("Cannot safely remove configure's shell environment dump")
        value = (
            value.splitlines()[0] + "\n# Shell environment dump omitted.\n" + value[start.start() :]
        )
    for path, label in (
        (ROOT, "<WORKSPACE>"),
        (Path(os.environ.get("TEMP", ".")), "<TEMP>"),
        (Path.home(), "<USERPROFILE>"),
    ):
        raw = str(path.resolve())
        variants = {raw, raw.replace("\\", "/"), raw.replace("\\", "/").replace(" ", "\\ ")}
        posix = raw.replace("\\", "/")
        variants.add("/" + posix[0].lower() + posix[2:])
        if path.exists():
            short = short_path(path)
            variants.update({short, short.replace("/", "\\"), "/" + short[0].lower() + short[2:]})
        for variant in sorted(variants, key=len, reverse=True):
            value = re.sub(re.escape(variant), lambda _match, label=label: label, value, flags=re.I)
    return re.sub(r"(?:/tmp|<TEMP>)/ffconf\.[^/\s]+", "<CONFIGURE_TMP>", value)


def build(toolchain, source, jobs, bash):
    flags = ["--prefix=/looktoask-ffmpeg", *CONFIGURE_FLAGS]
    script = (
        "#!/bin/bash\nset -euo pipefail\nexport LC_ALL=C\n"
        'SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"\n'
        'BUILD_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"\n'
        'VENV_ROOT="$(cd "$BUILD_ROOT/.." && pwd)"\n'
        'export PATH="$VENV_ROOT/native-tools/winlibs/mingw64/bin:/usr/bin:/bin"\n'
        'BUILD_SHELL="$(cygpath -ms /usr/bin/sh.exe)"\n'
        'INSTALL_ROOT="$(cygpath -ms "$BUILD_ROOT")/installroot"\n'
        "export SOURCE_DATE_EPOCH=1780747200\n"
        f'cd "$BUILD_ROOT/source/FFmpeg-{FFMPEG_REVISION}"\n'
        "bash --version\ngcc -v\nmingw32-make --version\n"
        "bash ./configure " + shlex.join(flags) + "\n"
        f'mingw32-make -j{jobs} SHELL="$BUILD_SHELL"\n'
        'mingw32-make install SHELL="$BUILD_SHELL" DESTDIR="$INSTALL_ROOT"\n'
    )
    recipe = OUTPUT / "build.sh"
    recipe.write_text(script, "utf-8", newline="\n")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "COMSPEC",
            "PATHEXT",
            "USERPROFILE",
            "HOMEDRIVE",
            "HOMEPATH",
            "PROGRAMFILES",
            "PROGRAMFILES(X86)",
            "PROGRAMDATA",
            "APPDATA",
            "LOCALAPPDATA",
            "NUMBER_OF_PROCESSORS",
            "PROCESSOR_ARCHITECTURE",
        }
    }
    environment["PATH"] = os.pathsep.join(
        (
            str(bash.parent.parent / "usr/bin"),
            str(Path(environment.get("SYSTEMROOT", "C:/Windows")) / "System32"),
        )
    )
    environment["CHERE_INVOKING"] = "1"
    logs = WORK / "logs"
    logs.mkdir(exist_ok=True)
    raw_log = logs / "build.log"
    print("Building seven minimal FFmpeg shared libraries; raw log:", raw_log, flush=True)
    with raw_log.open("w", encoding="utf-8") as log:
        result = subprocess.run(
            [str(bash), "--noprofile", "--norc", short_path(recipe)],
            cwd=short_path(source),
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    for name in ("config.h", "config_components.h", "ffbuild/config.mak", "ffbuild/config.log"):
        generated = source / name
        if generated.is_file():
            (OUTPUT / generated.name).write_text(
                public_text(generated.read_text("utf-8", errors="replace")), "utf-8"
            )
    (OUTPUT / "build.log").write_text(
        public_text(raw_log.read_text("utf-8", errors="replace")), "utf-8"
    )
    if result.returncode:
        raise RuntimeError(f"FFmpeg build failed ({result.returncode}); see {raw_log}")
    installed = WORK / "installroot/looktoask-ffmpeg"
    for child in installed.iterdir():
        if child.is_dir():
            shutil.copytree(child, OUTPUT / child.name, dirs_exist_ok=True)
        else:
            shutil.copyfile(child, OUTPUT / child.name)
    return flags


def notices(source, sources):
    folder = OUTPUT / "LICENSES"
    folder.mkdir(exist_ok=True)
    for name in ("COPYING.LGPLv2.1", "LICENSE.md", "CREDITS"):
        shutil.copyfile(source / name, folder / name)
    with tarfile.open(sources[1]) as package:
        for name in ("COPYING3", "COPYING.RUNTIME"):
            member = package.extractfile("gcc-14.2.0/" + name)
            if member is None:
                raise RuntimeError("Missing GCC runtime notice: " + name)
            (folder / ("GCC-" + name)).write_bytes(member.read())
    with tarfile.open(sources[2]) as package:
        for member in package.getmembers():
            if member.isfile() and member.name.endswith(("/COPYING", "/COPYING.MinGW-w64-runtime")):
                relative = member.name.split("/", 1)[-1].replace("/", "-")
                stream = package.extractfile(member)
                if stream is not None:
                    (folder / ("MinGW-" + relative)).write_bytes(stream.read())


def verify(toolchain):
    directory = OUTPUT / "bin"
    if {p.name for p in directory.glob("*.dll")} != set(LIBRARIES):
        raise RuntimeError("Expected exactly seven canonical FFmpeg DLLs")
    report = []
    handles = []
    with os.add_dll_directory(str(directory)):
        for name, prefix in LIBRARIES.items():
            path = directory / name
            data = path.read_bytes()
            if b"fftw_" in data.lower() or b"chromaprint" in data.lower():
                raise RuntimeError("Forbidden transitive codec library in " + name)
            native = subprocess.run(
                [str(toolchain / "bin/objdump.exe"), "-p", str(path)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            imports = re.findall(r"DLL Name:\s*(\S+)", native)
            unexpected = [
                item
                for item in imports
                if item.lower() not in SYSTEM_DLLS | set(LIBRARIES)
                and not item.lower().startswith("api-ms-win-crt-")
            ]
            if unexpected:
                raise RuntimeError(f"Unexpected native dependencies in {name}: {unexpected}")
            library = ctypes.CDLL(str(path))
            handles.append(library)
            license_function = getattr(library, prefix + "_license")
            license_function.restype = ctypes.c_char_p
            license_text = license_function().decode("utf-8")
            if license_text != "LGPL version 2.1 or later":
                raise RuntimeError("Unexpected FFmpeg license: " + license_text)
            configuration = getattr(library, prefix + "_configuration")
            configuration.restype = ctypes.c_char_p
            configure = configuration().decode("utf-8")
            version_function = getattr(library, prefix + "_version")
            version_function.restype = ctypes.c_uint
            version = version_function()
            report.append(
                {
                    "name": name,
                    "sha256": sha256(path),
                    "size": len(data),
                    "imports": imports,
                    "license": license_text,
                    "version": [version >> 16, (version >> 8) & 255, version & 255],
                    "configuration": configure,
                }
            )
    return report


def cached_build_valid(toolchain):
    try:
        manifest = json.loads((OUTPUT / "BUILD.json").read_text("utf-8"))
        expected_inputs = [
            {"name": name, "url": url, "sha256": digest, "license": license_text}
            for name, url, digest, license_text in ARTIFACTS
        ]
        if (
            manifest["ffmpeg_revision"] != FFMPEG_REVISION
            or manifest["ffmpeg_source"]["sha256"] != FFMPEG_SHA256
            or manifest["configure"] != ["--prefix=/looktoask-ffmpeg", *CONFIGURE_FLAGS]
            or manifest["recipe_script_sha256"] != sha256(Path(__file__))
            or manifest["build_script_sha256"] != sha256(OUTPUT / "build.sh")
            or manifest["gcc_sha256"] != sha256(toolchain / "bin/gcc.exe")
            or manifest["build_inputs"] != expected_inputs
        ):
            return False
        return (
            {item["name"] for item in manifest["dlls"]} == set(LIBRARIES)
            and all(
                sha256(OUTPUT / "bin" / item["name"]) == item["sha256"] for item in manifest["dlls"]
            )
            and all(sha256(TOOLS / name) == digest for name, _url, digest, _license in ARTIFACTS)
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 1, 8))
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    if os.name != "nt" or arguments.jobs < 1:
        parser.error("Windows x64 and a positive --jobs value are required")
    TOOLS.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if sha256(FFMPEG_ARCHIVE) != FFMPEG_SHA256:
        raise RuntimeError("Pinned FFmpeg source hash mismatch")
    toolchain = TOOLS / "winlibs/mingw64"
    if cached_build_valid(toolchain):
        write_json(OUTPUT / "NATIVE-VERIFICATION.json", verify(toolchain))
        print("MINIMAL_FFMPEG_NATIVE_VERIFICATION_OK CACHED_BUILD_REUSED")
        return
    if arguments.verify_only:
        raise RuntimeError("Build inputs or DLL hashes changed; rerun without --verify-only")
    driver_digest = sha256(Path(__file__))
    inputs = [fetch(name, url, digest) for name, url, digest, _license in ARTIFACTS]
    toolchain, source = extract_inputs(inputs[0])
    bash = Path("C:/Program Files/Git/bin/bash.exe")
    if not bash.is_file():
        raise RuntimeError("Git for Windows Bash is required; it is a build-only tool")
    flags = build(toolchain, source, arguments.jobs, bash)
    notices(source, inputs)
    files = verify(toolchain)
    write_json(OUTPUT / "NATIVE-VERIFICATION.json", files)
    write_json(
        OUTPUT / "BUILD.json",
        {
            "ffmpeg_revision": FFMPEG_REVISION,
            "ffmpeg_source": {
                "name": FFMPEG_ARCHIVE.name,
                "sha256": FFMPEG_SHA256,
                "url": "https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/" + FFMPEG_REVISION,
            },
            "build_inputs": [
                {"name": name, "url": url, "sha256": digest, "license": license_text}
                for name, url, digest, license_text in ARTIFACTS
            ],
            "configure": flags,
            "gcc_sha256": sha256(toolchain / "bin/gcc.exe"),
            "recipe_script_sha256": driver_digest,
            "build_script_sha256": sha256(OUTPUT / "build.sh"),
            "dlls": files,
            "external_libraries": [],
            "python_bindings_built_here": False,
            "scope": "Windows x64 WAV/PCM only; no devices, network, external codecs or GPL",
            "reproducibility": "Pinned inputs and recipe; bit-for-bit reproducibility not claimed",
        },
    )
    print("MINIMAL_FFMPEG_BUILD_OK", OUTPUT, flush=True)


if __name__ == "__main__":
    main()
