# Library sources, modification and replacement

Look to Ask is MIT licensed. It uses **Qt / PySide6 / Shiboken6 6.8.3 under LGPLv3**
and a separately built, audio-only **FFmpeg under LGPLv2.1-or-later**. Copies of the
LGPL and GPL texts and component attributions are under `_internal/LICENSES`.
You may modify these libraries, reverse engineer the application to debug those
modifications, and run compatible replacement libraries. This project imposes no
restriction on those LGPL rights. No signing check or checksum lock prevents replacement.

Deliver these four artifacts together: `Setup.exe` (or the portable ZIP),
`LookToAsk-0.4.6-Source.zip`, `LookToAsk-0.4.6-LibrarySources.zip`, and `SHA256SUMS.txt`.
The library source ZIP contains the complete pinned upstream archives, source manifest,
FFmpeg configuration/build records, and the application-owned import repair/build scripts.
The MIT application ZIP contains all application sources and the PyInstaller/NSIS recipes.
Do not offer only a link to an upstream repository in place of these source archives.

## Qt and PySide

Exit Look to Ask and back up the installation folder. Replace a **coherent Windows x64
shared-library set**, using compatible Qt 6.8 / PySide 6.8 ABI (prefer 6.8.3, MSVC 2022):

- `_internal/PySide6/Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Widgets.dll`, `Qt6Network.dll`, `Qt6Svg.dll`;
- `_internal/PySide6/pyside6.abi3.dll`, the corresponding `Qt*.pyd`, and any changed `plugins/` files;
- `_internal/shiboken6/shiboken6.abi3.dll` and `Shiboken.pyd` when changing the binding runtime.

Keep compatible plugin and translation versions. Launch `LookToAsk.exe --smoke-ui --report
qt-check.json` from a terminal, then exercise the normal UI. To modify Python bindings or
application integration, install your compatible PySide/Shiboken build into a Python 3.12
environment and rerun `scripts/build_windows.py` instead of replacing individual files.

Official PyPI wheels are used. PySide v6.8.3 pins Qt supermodule commit
`bab1fecd556ea561c4a89686293116741acfa1b4`. Its module commits are QtBase
`c07c2d5a527a644d36e7853d55132ae38921682f`, QtSvg
`c75099a75e81df35e7347a65e301bbf1011831a5`, QtImageFormats
`3b6b1fb96041f1bc85a8f42593bef2ee7bcdca6c`, and QtTranslations
`abe01d7de31d311db8bc485d4e7e8d0c30493425`. The supplied tagged archives match these commits.
PySide/Shiboken source commit is `3ae6c97953d563c33ff630f259716b01b81aa531`.
See the [official build instructions](https://doc.qt.io/qtforpython-6.8/building_from_source/index.html).
Building Qt/PySide themselves from source has **not** been tested here; matching official source
and wheel provenance is recorded, not a claim of bit-for-bit reproducibility.

## FFmpeg and PyAV

All seven FFmpeg DLLs live in `_internal/av.libs/`: `avcodec-62.dll`, `avdevice-62.dll`,
`avfilter-11.dll`, `avformat-62.dll`, `avutil-60.dll`, `swresample-6.dll`, `swscale-9.dll`.
They are compiled from supplied FFmpeg revision `e4c7fbf6c0`, without external codecs,
autodetection, GPL/nonfree/version3 features or network protocols. The enabled built-in
audio components support this application's in-memory voice workflow and PCM/WAV checks.
This is intentionally not a general video/file conversion distribution.

After installing the project dependencies, run:

```powershell
python scripts/fetch_license_sources.py
python scripts/build_minimal_ffmpeg.py
python scripts/build_windows.py
```

The native builder downloads a hash-pinned, build-only portable GCC/MinGW toolchain. It
does not modify the system PATH or install system software. Its source, actual configure
arguments, compiler identifiers, license texts and output hashes accompany the library sources.
To modify FFmpeg, unpack the supplied source, apply your changes, and use the recorded recipe
with your modified source (update the source/hash pins in a local copy of the builder).
Copy all seven compatible rebuilt DLLs into `_internal/av.libs/` after exiting the app.

PyAV 17.1.0 binding code is BSD-3-Clause and comes from the official Windows wheel
(SHA-256 `5df5c1172ef1cf65a1529d612f7da7798ce2cf82c1ff7212466b538a6cc7214c`).
`native_packaging.py` repairs only DLL import names in copies of its PYD files to use the
canonical DLLs above. No binding implementation is changed or claimed rebuilt from source.
The original wheel's bundled FFmpeg/external DLLs are excluded completely. The PyAV 17.1.0
source archive is supplied too. `BINDING-IMPORT-CHANGES.json` records original and repaired hashes.

## System libraries

Microsoft CRT/UCRT DLLs are **not redistributed**. Install Microsoft's official Visual C++
v14 x64 Runtime 14.51.36247 or newer separately; Windows 10/11 supplies UCRT. Installing the
Microsoft prerequisite may require administrator permission. The application installer itself
is per-user. The camera enumerator's copied PYD import is repaired from its wheel's hashed
MSVCP name to the system `MSVCP140.dll`; that small MIT patch is in `native_packaging.py`.
The scikit-learn wheel's two explicit package-local CRT preloads are likewise redirected to
`LOAD_LIBRARY_SEARCH_SYSTEM32` in a generated BSD-licensed copy of its loader. Its numerical
extension modules are unchanged; original/repaired loader hashes are recorded with the notices.

Optional NVIDIA GPU runtimes are also installed separately, under NVIDIA's terms. They are
not in the standard bundle. Models are downloaded on demand and are not in either source ZIP.

The packaged Intel OpenMP `libiomp5md.dll` is a documented, proprietary Intel redistributable,
version `5.0.20250422`, with its explicit `fredist.txt` designation. It remains separate from
MIT application code and the LGPL libraries. Preserve its full vendor license and notices;
the component-specific terms are in `_internal/LICENSES/Intel-Runtime-Terms.txt` and displayed
by the installer and the Licenses tab. These terms apply only to Intel's portions and do not
limit the LGPL replacement/debugging rights described above. An arbitrary LLVM OpenMP DLL
is not a compatible drop-in: this CTranslate2 build requires both MSVC and LLVM OpenMP APIs.

## NumPy / OpenBLAS and libquadmath

NumPy 1.26.4's `_internal/numpy.libs/libopenblas64__v0.3.23-293-gc2f4bdbb-gcc_10_3_0-*.dll`
is separately replaceable. It embeds libquadmath under LGPLv2.1-or-later. Its full original
wheel notice includes the LGPL text. The library source ZIP supplies GCC 10.3.0 (including
libquadmath), OpenBLAS commit `c2f4bdbbb43a1d20a7342f40122e18e573ce436a`, NumPy 1.26.4,
and producer `MacPython/openblas-libs` commit `f76e4c29cd7983c6f8ae2e41e8bdd5669dda60d8`.
That producer's `.travis.yml` pins this OpenBLAS revision; NumPy's `tools/openblas_support.py`
pins its Windows GCC 10.3.0 ILP64 binary variant. The archive contains the original Windows
build scripts, flags, patches and compiler download references needed to build the shared library.

To change libquadmath, rebuild the supplied GCC/libquadmath sources with a compatible Windows
x64 toolchain, then rebuild OpenBLAS using that producer recipe's Windows **ILP64** configuration
and your library. Preserve NumPy's exported symbol names, calling convention and dependencies.
Exit the app, back up the installation, and replace the complete shared DLL at the path above,
retaining its imported filename. Alternatively install your compatible rebuilt NumPy wheel in
the build environment and rerun the application packaging script. No checksum lock in the
application prevents replacement. You may modify and debug these LGPL portions under their terms.
This particular NumPy/OpenBLAS/libquadmath from-source rebuild has **not** been performed here;
the supplied official source/recipe correspondence and existing wheel are documented instead.

The source companion also includes MediaPipe's pinned Eigen source for its MPL-2.0 portions,
upstream sources and notices for its native dependencies, and all checksum-locked tokenizers
registry crate sources. Those archives are an attribution/source superset and are not executable
model caches or private user data.
