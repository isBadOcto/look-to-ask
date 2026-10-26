# Third-party notices

## Optional external Codex desktop application (0.5.0)

Codex desktop handoff invokes a separately installed desktop component through local
stdio and a native wake link. Codex executables, credentials and model access are not
bundled or copied into Look to Ask. The external application retains its own license,
account terms and data policy. This adapter adds no Python runtime dependencies;
`shiboken6` is already part of the pinned PySide6 distribution below.

Look to Ask's original code is MIT licensed. Third-party components retain their own licenses.
When building with the current Codex-provided CPython runtime, its SSL module requires
the 906-byte public `codex-rejected-cas.pem` distrust record. The bundle preserves this
record alongside the module, with SHA-256
`c916ce1b14ed8ca69e9b5c9fab22799a900dd610d6d4ec9b1347f4fd48e53718`.
It contains a public trusted-certificate record, no private key or account credentials;
certificate verification remains enabled. Ordinary CPython builds need no such asset.

Git contains source and build instructions, not binaries, private data or model caches. Phase 4
produces local, unpublished Windows test artifacts. Their `_internal/LICENSES` directory contains
installed-distribution notices and license texts extracted from pinned upstream sources.
Source-relative upstream texts are in `_internal/LICENSES/UPSTREAM-NOTICES.zip`; the ZIP
preserves deep attribution paths without requiring Windows long-path support during installation.
`dist/LicenseSources/SOURCES.json` records native source archives and hashes. The matching
`LookToAsk-0.4.6-LibrarySources.zip` and application Source.zip must accompany binary deliveries.
See [PACKAGING.md](docs/PACKAGING.md) and [RELINKING.md](docs/RELINKING.md).
The environment inventory is a superset including build tools, not a claim that every listed package
is shipped. The bundle manifest describes actual files. No public release has been made.

Version 0.4.6 replaces the earlier community FFmpeg build, which was found to contain
statically linked GPL FFTW despite reporting LGPL. Do not distribute old 0.4.5 binaries.
The current build uses a small, verifiable FFmpeg build with no external codecs/libraries.

## EyeTrax core (MIT)

Copyright (c) 2024 ck-zhang. The complete upstream permission notice is retained in
[`src/look_to_ask/_vendor/eyetrax/LICENSE`](src/look_to_ask/_vendor/eyetrax/LICENSE).
Source, version, pinned commit, local edits and hashes are documented alongside it in
[`UPSTREAM.md`](src/look_to_ask/_vendor/eyetrax/UPSTREAM.md) and `manifest.json`.
No virtual-camera module or GPL pyvirtualcam code is included or installed.

## Runtime libraries

Optional NVIDIA CUDA acceleration uses separately installed cuBLAS 12.8.4.1, cuDNN 9.10.2.21
and CUDA Runtime 12.8.90, provided by NVIDIA via their official PyPI Windows wheels. These
are proprietary, not MIT/open-source libraries, and are not included in the ordinary installer
or portable bundle. Their wheel license texts remain in the separate local installation.
See [DEPENDENCIES.md](docs/DEPENDENCIES.md) and [GPU setup](docs/SPEECH.zh.md).

MediaPipe and OpenCV: Apache-2.0. NumPy, SciPy and scikit-learn: BSD-family licenses.
screeninfo: MIT. **This application uses Qt / PySide6 / Shiboken6 6.8.3 under LGPLv3**;
it bundles QtCore, QtGui, QtWidgets, QtNetwork and QtSvg, image-format plugins and translations with
separately replaceable libraries in an onedir layout. This project's MIT license does not replace
Qt's LGPL obligations. See [Qt licensing](https://www.qt.io/licensing/open-source-lgpl-obligations)
and [Qt for Python third-party notices](https://doc.qt.io/qtforpython-6.8/licenses.html).
Qt/OpenCV/MediaPipe and scientific wheels may themselves bundle third-party native libraries;
retain the notices provided in their wheels when packaging. Installed-package metadata alone
is not a complete binary-distribution notice set.

This software is based in part on the work of the Independent JPEG Group.
Portions of this software are based on the work of the FreeType Team.
Qt's bundled PCRE2, HarfBuzz, FreeType, JPEG, PNG, zlib, Public Suffix List, TIFF and WebP
notices, their SPDX license texts and `qt_attribution.json` records are retained with source-relative
paths. QtImageFormats and QtTranslations sources are included alongside QtBase/QtSvg and PySide.
The LGPL and GPL texts are included. Users may debug modifications, reverse engineer for that
purpose, and replace compatible LGPL libraries; see the concrete instructions in RELINKING.md.

Microsoft CRT/UCRT DLLs are not redistributed. Windows 10/11 provides UCRT; users install
Microsoft's official Visual C++ v14 x64 Runtime separately. No entitlement to redistribute a
Microsoft runtime is inferred from a Python wheel's open-source license.
The camera enumerator's PE import and scikit-learn's two CRT preload paths are repaired in
build copies to use the system runtime; corresponding hashes and patch scripts are supplied.

The bundled **Intel OpenMP runtime is proprietary**, separately licensed from CTranslate2's
MIT code. Version `5.0.20250422` is taken from Intel's official `2025.2.1.1001` redistributable,
whose `fredist.txt` explicitly designates `libiomp5md.dll` for redistribution. It also matches
the official `intel_openmp 2025.2.0` wheel byte-for-byte. The wheel's newer, undocumented
runtime is excluded. Intel's full EULA, redistribution list, OpenMP/compiler/TCM/oneTBB notices,
source URLs and hashes are retained in `_internal/LICENSES/NativeRuntime/Intel-OpenMP`.
`_internal/LICENSES/Intel-Runtime-Terms.txt` contains the component-specific end-user terms;
the installer presents them separately for acceptance. Portable users must read and accept
them before using the Intel binary. Intel restrictions apply only to Intel's portions; separately
licensed open-source portions and all Qt/FFmpeg LGPL modification/debugging rights remain intact.

CPython 3.12.14: PSF-2.0 and its included component licenses. Its native OpenSSL 3.5.8 is
Apache-2.0, libffi is MIT, and SQLite 3.53.1 is public domain. Their separate notices are retained
under `_internal/LICENSES/NativeRuntime` in addition to CPython's own LICENSE. Build provenance
records the inspected DLL versions/hashes and the limit of the inferred libffi source version.

CTranslate2's official Windows build statically links **Intel oneMKL 2025.3.0**, under the
Intel Simplified Software License (proprietary), and **oneDNN 3.1.1**, under Apache-2.0.
The exact CTranslate2 release build recipe, oneDNN sources/notices and Intel's original
oneMKL static/runtime wheel licenses are retained. Intel's restrictions concern its own
proprietary portions only, never MIT application code or LGPL libraries.

NumPy's OpenBLAS `0.3.23-293-gc2f4bdbb` includes **libquadmath from GCC 10.3.0 under
LGPLv2.1-or-later**; it is not covered solely by the GCC Runtime Exception. The library source
companion therefore includes complete GCC 10.3.0/libquadmath, OpenBLAS, NumPy 1.26.4 sources
and the pinned OpenBLAS producer recipe. The existing NumPy wheel's full notices are retained.
See RELINKING.md for rebuilding/replacing the shared OpenBLAS library.

Tokenizers' Apache-2.0 license does not replace its Rust dependencies' notices. All 151 registry
crate sources from its pinned Python Cargo.lock are hash-verified; their original license,
copyright, Cargo and README texts are retained with paths. These include Oniguruma/onig,
esaxx, SentencePiece normalization and Unicode notices. This is a conservative source/notices
superset, not a claim that every build/development/other-platform crate is in the Windows binary.
MediaPipe's corresponding source and its pinned TensorFlow, Eigen (MPL-2.0), XNNPACK, ruy,
gemmlowp, protobuf, FlatBuffers, Abseil, CPUinfo, pthreadpool, RE2, SentencePiece and zlib
source/notices are also provided. Eigen's complete corresponding source is included for MPL.

The actual Windows/Python 3.12 installation inventory, including development dependencies,
is in [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md). Full library licenses are provided by
the installed distributions' `.dist-info`/license directories and upstream sources.

## Phase 3 local speech

[faster-whisper](https://github.com/SYSTRAN/faster-whisper) 1.2.1 and
[CTranslate2](https://github.com/OpenNMT/CTranslate2) 4.8.3: MIT.
[sounddevice](https://github.com/spatialaudio/python-sounddevice/) 0.5.6: MIT;
its Windows distribution includes PortAudio, whose notices must be retained separately.
ONNX Runtime: MIT; Hugging Face Hub/tokenizers: Apache-2.0.

The generic [Systran/faster-whisper-base](https://huggingface.co/Systran/faster-whisper-base)
model card declares MIT; observed cache revision is `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`.
Whisper weights are downloaded at user request, never copied into Git or the installer.
The package does include faster-whisper's generic Silero VAD ONNX resource; its upstream MIT
license is copied into `_internal/LICENSES/Silero-VAD-LICENSE.txt`. Model resources are not
personal recordings. FaceLandmarker is downloaded separately, as described below.

PyAV 17.1.0: BSD-3-Clause, official PyPI binding wheel. Packaging changes only copied PYD DLL
import names, with changes and original/repaired hashes recorded. All original wheel FFmpeg and
external codec DLLs are omitted. The replacement FFmpeg revision `e4c7fbf6c0` is compiled locally
as seven shared libraries under LGPLv2.1-or-later, with external detection, GPL, nonfree, version3,
network and programs disabled. Its complete source, actual build configuration and notices are
supplied. GCC runtime code uses the GCC Runtime Library Exception; MinGW runtime notices accompany
the build. The compiler itself is build-only and is not shipped. See RELINKING.md for rebuilding.
Source installations use the ordinary PyPI PyAV wheel, whose bundled FFmpeg license/features may
differ; the custom minimal build is a Windows packaging step.

## Phase 4 devices and packaging

`cv2-enumerate-cameras` 1.4.0: MIT, camera-name/index enumeration through DirectShow.
Native Windows Credential Manager is accessed through Python ctypes; no credential library is added.
PyInstaller 6.22.3 uses GPL terms with its application-bundling exception; dependencies keep their
own licenses. NSIS 3.13's installer core and the selected zlib compressor use the zlib/libpng license.
The portable NSIS SDK's full COPYING file accompanies the build. Build tools are not application
runtime dependencies. Public binary release remains a separate, explicitly authorized action.

## MediaPipe FaceLandmarker model

Downloaded by EyeTrax from Google's versioned model URL on first engine initialization:

`https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`

Local default cache: `%USERPROFILE%\.cache\eyetrax\mediapipe\face_landmarker.task`.
Observed size: 3,758,596 bytes. SHA-256:

`64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`

The [official model guide](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker#models)
links model cards for BlazeFace, FaceMesh-V2 and Blendshape, each specifying Apache-2.0.
The file is a pretrained generic asset, not user calibration data, and is not in this repository.
When distributing that asset later, retain its upstream attribution and Apache-2.0 notices.
