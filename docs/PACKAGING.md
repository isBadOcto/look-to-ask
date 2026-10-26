# Windows packaging

Local version: **0.5.0 x64**. Nothing is pushed or published by these scripts. Build on Windows x64
with Python 3.12. PyInstaller uses an onedir layout without UPX, so LGPL libraries remain replaceable.
NSIS provides per-user installation, Start menu entries and uninstall. Microsoft Visual C++ v14 x64
Runtime **14.51.36247 or newer** is a separate prerequisite; its own installation may require admin.
Windows 10/11 supplies UCRT. No Microsoft CRT/UCRT or optional NVIDIA DLLs are redistributed.

The standard bundle includes documented Intel OpenMP and statically linked oneMKL under
their original proprietary terms. NSIS displays a separate Intel component acceptance page;
portable recipients must read/accept `_internal/LICENSES/Intel-Runtime-Terms.txt`. These terms
do not cover MIT application code or restrict LGPL library modification/debugging rights.

## Build

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/build_windows.py
```

Obtain the portable NSIS 3.13 SDK from [NSIS](https://nsis.sourceforge.io/Download), extract to
`.venv/tools/nsis-3.13`, or pass `--nsis`. Tested archive URL:
`https://netactuate.dl.sourceforge.net/project/nsis/NSIS%203/3.13/nsis-3.13.zip`, SHA-256
`ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8`.
The native FFmpeg builder downloads a pinned portable GCC/MinGW toolchain into `.venv/native-tools`.
Git for Windows Bash is also required. No system PATH or software installation is changed.

The build compiles reviewed translations; verifies complete native source archives; builds minimal
FFmpeg; collects notices with preserved paths; creates icon/resources; stages repaired PyAV/camera
binding copies; freezes the application; audits files; compiles NSIS; creates portable, application
source and library source ZIPs; writes SHA-256 sums. Dependency resolution uses a clean PATH limited
to this Python environment and Windows, never unrelated native libraries from the caller's PATH.
Build scripts may replace generated `build/` and `dist/LookToAsk/`; keep personal files elsewhere.

`python scripts/build_windows.py --source-only` refreshes only the application source ZIP and hashes;
it does not update binaries or the library source companion. Rebuild fully after changing runtime,
license or native recipes. Application source packaging is allowlisted and excludes caches,
recordings, screenshots, calibration data, generated package metadata and hidden directories.

## Deliver together

- `dist/LookToAsk-0.5.0-Setup.exe`: unsigned current-user installer.
- `dist/LookToAsk-0.5.0-Windows-x64.zip`: extract the complete folder, retaining `_internal`.
- `dist/LookToAsk-0.5.0-Source.zip`: MIT application source, tests, dependency declarations and recipes.
- `dist/LookToAsk-0.5.0-LibrarySources.zip`: complete corresponding Qt/PySide/FFmpeg/PyAV source
  archives, hashes, native build records, notices and replacement instructions.
  Also includes NumPy/OpenBLAS/GCC 10.3 libquadmath sources/producer recipe, MediaPipe's pinned
  native sources (including MPL Eigen), and tokenizers' 151 checksum-locked registry crate sources.
- `dist/SHA256SUMS.txt`: artifact hashes. `dist/BUNDLE-MANIFEST.json`: actual relative file hashes.

Keep `LICENSE`, `THIRD_PARTY_NOTICES.md`, `_internal/LICENSES` and both source ZIPs with binary
hand-offs. [RELINKING.md](RELINKING.md) identifies the precise replaceable files and build steps.
Deep upstream license/attribution paths are preserved inside `_internal/LICENSES/UPSTREAM-NOTICES.zip`
so ordinary Windows installations do not exceed the filesystem path limit.
The source archive manifest and official Qt/PySide wheel provenance are included. Qt source builds
have not been tested; official source/wheel correspondence is verified, without promising identical
third-party rebuilds. FFmpeg itself is actually built using the supplied script and no external codecs.
The older community FFmpeg build contained GPL FFTW and is excluded, regardless of its LGPL string.

## Verify

```powershell
.\.venv\Scripts\python.exe scripts/audit_bundle.py
.\.venv\Scripts\python.exe tests/manual/check_frozen.py dist/LookToAsk/LookToAsk.exe .venv/frozen-0.5.0
.\tests\manual\check_installer.ps1 -Version 0.5.0
```

The real installer test refuses existing installations and uses a fresh verified workspace target.
For another run without deleting earlier evidence, use `-Attempt final` (or another fresh name).
It checks install files/registry/shortcuts, executes packaged dependency/engine/speech/UI checks from
an empty working directory, uninstalls, and verifies that inert settings remain. It never accesses
real camera/microphone/API credentials. See LICENSE-AUDIT.zh.md for actual results and limitations.
A clean Windows 10/11 machine without a runtime, actual gaze accuracy, microphone capture and a real
provider question remain human acceptance checks; follow [TESTING.md](TESTING.md).

The app stores preferences under `%LOCALAPPDATA%/LookToAsk`, keys only in memory or optionally Windows
Credential Manager. Uninstall preserves preferences, remembered keys and generic model caches.
To delete a remembered key, uncheck Remember and save before uninstall. No startup service/task,
auto-updater or background screenshots are installed. FaceLandmarker/Whisper are downloaded on
request, excluded from artifacts; generic Silero VAD is included with its MIT notice.

The bundle audit rejects private/model formats, retired experiments, foreign/GPL codec DLLs,
optional GPU runtimes, bundled CRT/UCRT, unsupported PortAudio variants and local metadata origins.
It records only relative paths and hashes. It is a bounded packaging check, not a universal secret
scanner. Review the actual source/artifacts before a future explicitly authorized publication.
