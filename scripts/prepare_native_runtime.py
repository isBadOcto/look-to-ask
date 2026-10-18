"""Prepare documented native redistributables; never execute a vendor installer.

Only this repository's ignored .venv/native-runtime directory is written. The
Intel EXE is read as a ZIP, its MSI is opened with MSIDBOPEN_READONLY, and Windows
expand.exe reads its CAB. No installation, device, registry update or credential
access is performed. Intel terms apply only to Intel's proprietary portions.
"""

import ctypes
import hashlib
import importlib.metadata as metadata
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".venv/native-runtime"
OUTPUT = BASE / "output"
DLL_SHA256 = "d9d66ed25f1a0ea725fa3a41b22cfd5d182c19dbe4771d9c90ca02ad7466f6a1"
CT2_SHA256 = "ca1127837d032bf8217d0cbcd68e8cef1f93bda3111eff00ced98795d9e51160"
INTEL_URL = (
    "https://registrationcenter-download.intel.com/akdlm/IRC_NAS/"
    "0dc56e76-d2c0-4bb8-9c83-c2ee3952b855/w_ifx_runtime_p_2025.2.1.1001.exe"
)
INTEL_SHA256 = "bcf12069e8ab987d012f196d034b0e70d3eae099d8ee6512b55f901d44a2f8d1"
MSI_NAME = "w_ifx_runtime_p_2025.2.1.1001.msi"
MSI_SHA256 = "a13ada6fec2679c021b117ae1bc468fde520e2bc892ab208bbea9d3a69b6f86a"
CAB_SHA256 = "0dcc2457ca2547536c04ea418a2172b67820a3b68846a230e75e059362cad379"
OPENMP_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/bc/37/"
    "bab8e9283407798d8782f4d9b374436e51c7a297e1b6dc05073df550c010/"
    "intel_openmp-2025.2.0-py2.py3-none-win_amd64.whl"
)
OPENMP_WHEEL_SHA256 = "1710356ae0db744ca028ed380759a2007548ad1819f743be9d675603cb127377"
TBB_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/2e/e5/"
    "09786318a0fcd5a9b9589759ec91fe1815db064ab6bb6d4083ea24dbb859/"
    "tbb-2022.1.0-py3-none-win_amd64.whl"
)
TBB_WHEEL_SHA256 = "ae9cc327606f604324441abf3ab984c12ea4f6f1ea2a84230874fc40036d0913"

# Exact File-table identifiers in the pinned, official Intel runtime MSI.
MSI_FILES = (
    ("libiomp5md_dll.18BB45A0_2267_4162_BA13_1247E18E29B5", "libiomp5md.dll", DLL_SHA256),
    (
        "fredist_txt.8A0D7435_59A8_4C93_BB1B_7E4F1E20AF74",
        "LICENSES/Intel-OpenMP/fredist.txt",
        "8fc3a9aacb34ffa2b57c2539419b4c3b52b31ae5a0a1128387c461f049c699fa",
    ),
    (
        "LICENSE_rtf.8A0D7435_59A8_4C93_BB1B_7E4F1E20AF74",
        "LICENSES/Intel-OpenMP/Intel-Developer-Tools-EULA.rtf",
        "4e96f3006c9d51b38561f9802da896480dc48e7703a76c206292bf6d6d11a781",
    ),
    (
        "third_party_programs_txt.8A0D7435_59A8_4C93_BB1B_7E4F1E20AF74",
        "LICENSES/Intel-OpenMP/compiler-third-party-programs.txt",
        "a81491a0243fa1d072aa636c890a6dd082ca403aca4681672cf6f69d3d516f79",
    ),
    (
        "license_txt.B1868581_8745_4F2A_9E8D_D8895E99D5CA",
        "LICENSES/Intel-OpenMP/TCM-LICENSE.txt",
        "6c00ae54b2a610ea009e0f5c5d3aa79023eb694c7fb72857654c53c6e99d7c97",
    ),
    (
        "third_party_programs_txt.B1868581_8745_4F2A_9E8D_D8895E99D5CA",
        "LICENSES/Intel-OpenMP/TCM-third-party-programs.txt",
        "0c359ebe1a1c58c3bb42eb228b6c3310361fe75d99ddb2fa29c536bf2a290955",
    ),
)

TEXT_NOTICES = (
    (
        "LICENSES/OpenSSL-3.5.8/LICENSE.txt",
        "https://raw.githubusercontent.com/openssl/openssl/openssl-3.5.8/LICENSE.txt",
        "7d5450cb2d142651b8afa315b5f238efc805dad827d91ba367d8516bc9d49e7a",
    ),
    (
        "LICENSES/OpenSSL-3.5.8/AUTHORS.md",
        "https://raw.githubusercontent.com/openssl/openssl/openssl-3.5.8/AUTHORS.md",
        "b9f638dfc06b59c2d3b808186c3b30f713805a5db390f5b77b1703ac58acb83e",
    ),
    (
        "LICENSES/libffi/LICENSE.txt",
        "https://raw.githubusercontent.com/libffi/libffi/v3.4.8/LICENSE",
        "67894089811f93fca47a76f85e017da6f8582d4ba0905963c6e0f1ad6df7a195",
    ),
)


def checked_bytes(data, digest, label):
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError("Native source hash mismatch: " + label)
    return data


def download(url, digest, name, limit=128 * 1024 * 1024):
    cache = BASE / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / name
    if target.is_file():
        checked_bytes(target.read_bytes(), digest, name)
        return target
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError("Native download exceeds its size limit: " + name)
    checked_bytes(data, digest, name)
    target.write_bytes(data)
    return target


def read_msi_cab(msi_path, target):
    """Read the fixed MSI stream through Windows Installer's read-only API."""
    if target.exists():
        checked_bytes(target.read_bytes(), CAB_SHA256, "Intel runtime CAB")
        return
    api = ctypes.WinDLL("msi")
    uint = ctypes.c_uint
    api.MsiOpenDatabaseW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(uint)]
    api.MsiDatabaseOpenViewW.argtypes = [uint, ctypes.c_wchar_p, ctypes.POINTER(uint)]
    api.MsiViewExecute.argtypes = [uint, uint]
    api.MsiViewFetch.argtypes = [uint, ctypes.POINTER(uint)]
    api.MsiRecordReadStream.argtypes = [uint, uint, ctypes.c_void_p, ctypes.POINTER(uint)]
    api.MsiCloseHandle.argtypes = [uint]
    handles = []

    def check(result):
        if result != 0:
            raise RuntimeError("Read-only MSI inspection failed: " + str(result))

    try:
        db = uint()
        check(api.MsiOpenDatabaseW(str(msi_path), None, ctypes.byref(db)))
        handles.append(db)
        view = uint()
        check(
            api.MsiDatabaseOpenViewW(
                db, "SELECT `Data` FROM `_Streams` WHERE `Name`='data1.cab'", ctypes.byref(view)
            )
        )
        handles.append(view)
        check(api.MsiViewExecute(view, 0))
        record = uint()
        check(api.MsiViewFetch(view, ctypes.byref(record)))
        handles.append(record)
        buffer = ctypes.create_string_buffer(1024 * 1024)
        data = bytearray()
        while True:
            size = uint(len(buffer))
            check(api.MsiRecordReadStream(record, 1, buffer, ctypes.byref(size)))
            if not size.value:
                break
            data.extend(buffer.raw[: size.value])
            if len(data) > 128 * 1024 * 1024:
                raise RuntimeError("Intel MSI CAB exceeds its size limit")
        target.write_bytes(checked_bytes(bytes(data), CAB_SHA256, "Intel runtime CAB"))
    finally:
        for handle in reversed(handles):
            api.MsiCloseHandle(handle)


def prepare_intel_files():
    archive = download(INTEL_URL, INTEL_SHA256, "intel-fortran-runtime-2025.2.1.exe")
    cache = BASE / "cache"
    msi_path = cache / MSI_NAME
    if not msi_path.exists():
        with zipfile.ZipFile(archive) as bundle:
            if bundle.namelist() != [MSI_NAME]:
                raise RuntimeError("Unexpected Intel runtime ZIP members")
            msi_path.write_bytes(checked_bytes(bundle.read(MSI_NAME), MSI_SHA256, MSI_NAME))
    checked_bytes(msi_path.read_bytes(), MSI_SHA256, MSI_NAME)
    cab_path = cache / "intel-runtime-data1.cab"
    read_msi_cab(msi_path, cab_path)
    extracted = cache / "intel-cab-files"
    extracted.mkdir(exist_ok=True)
    expand = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/expand.exe"
    if not expand.is_file():
        raise RuntimeError("Windows expand.exe is required for read-only CAB extraction")
    result = []
    for file_id, relative, digest in MSI_FILES:
        source = extracted / file_id
        if not source.exists():
            subprocess.run(
                [str(expand), str(cab_path), "-F:" + file_id, str(extracted)],
                check=True,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        data = checked_bytes(source.read_bytes(), digest, file_id)
        result.append(
            (relative, data, {"url": INTEL_URL, "archive_sha256": INTEL_SHA256, "member": file_id})
        )
    designation = next(data for relative, data, _ in result if relative.endswith("/fredist.txt"))
    if b"<installdir>/bin/libiomp5md.dll" not in designation:
        raise RuntimeError("Intel's redistributable designation does not include the DLL")
    return result


def wheel_member(archive, url, archive_digest, member, digest, relative):
    with zipfile.ZipFile(archive) as wheel:
        data = checked_bytes(wheel.read(member), digest, member)
    return relative, data, {"url": url, "archive_sha256": archive_digest, "member": member}


def prepare_intel_notices():
    wheel = download(OPENMP_WHEEL_URL, OPENMP_WHEEL_SHA256, "intel-openmp-2025.2.0.whl")
    with zipfile.ZipFile(wheel) as bundle:
        dll_member = "intel_openmp-2025.2.0.data/data/Library/bin/libiomp5md.dll"
        checked_bytes(bundle.read(dll_member), DLL_SHA256, "Intel wheel/runtime DLL correspondence")
    entries = [
        (
            "intel_openmp-2025.2.0.dist-info/LICENSE.txt",
            "LICENSE.txt",
            "febfb69a5b058f55892dc7f341108a9ca29d50e9fe85723a57eebbb826436958",
        ),
        (
            "intel_openmp-2025.2.0.data/data/share/doc/compiler/licensing/openmp/third-party-programs.txt",
            "third-party-programs.txt",
            "f8ce918fe7311ce279e68380a2e233f8a42b1cd3dda8f4c48d6de97a0255c1d7",
        ),
    ]
    result = [
        wheel_member(
            wheel,
            OPENMP_WHEEL_URL,
            OPENMP_WHEEL_SHA256,
            member,
            digest,
            "LICENSES/Intel-OpenMP/" + name,
        )
        for member, name, digest in entries
    ]
    tbb = download(TBB_WHEEL_URL, TBB_WHEEL_SHA256, "tbb-2022.1.0.whl")
    for member, name, digest in (
        (
            "tbb-2022.1.0.dist-info/LICENSE.txt",
            "oneTBB-LICENSE.txt",
            "7721633d0ddff43fae25ebfd405f8166a0ce730cbcec44f2f3ad9d5eb8ac9a6f",
        ),
        (
            "tbb-2022.1.0.data/data/Library/share/doc/tbb/licensing/third-party-programs.txt",
            "oneTBB-third-party-programs.txt",
            "1f6de0bd498c04c9283c6306379e2db2492e1c4e7d2b248c8de0e8fe9124cd03",
        ),
    ):
        result.append(
            wheel_member(
                tbb,
                TBB_WHEEL_URL,
                TBB_WHEEL_SHA256,
                member,
                digest,
                "LICENSES/Intel-OpenMP/" + name,
            )
        )
    return result


def prepare_math_notices():
    """CTranslate2's Windows build statically links oneMKL and oneDNN."""
    url = (
        "https://files.pythonhosted.org/packages/9c/22/"
        "c099498c3294381349265dad4b1715edd8b739b6392c3076aa2a68231ae2/"
        "mkl_static-2025.3.0-py2.py3-none-win_amd64.whl"
    )
    digest = "2ff574382d21968e9ec1a45c067258c053588179e741a1983cda7f47587ac181"
    source = download(url, digest, "mkl-static-2025.3.0.whl", limit=256 * 1024 * 1024)
    result = []
    with zipfile.ZipFile(source) as wheel:
        for name in wheel.namelist():
            leaf = Path(name).name.lower()
            if name.endswith("/") or not any(
                x in leaf for x in ("license", "third-party", "redist", "copyright")
            ):
                continue
            result.append(
                (
                    "LICENSES/oneMKL-2025.3.0/" + name,
                    wheel.read(name),
                    {"url": url, "archive_sha256": digest, "member": name},
                )
            )
    if not result:
        raise RuntimeError("oneMKL's static wheel is missing its required notices")
    runtime_url = (
        "https://files.pythonhosted.org/packages/75/0e/"
        "b863a60889643e21d5d8d6b619f913703257878979b1df22d344a56276d0/"
        "mkl-2025.3.0-py2.py3-none-win_amd64.whl"
    )
    runtime_digest = "2dbf81b016150c2ce418d80707dcce11d0e3c56f20e1d54813174e7665405561"
    runtime = download(runtime_url, runtime_digest, "mkl-2025.3.0.whl", limit=256 * 1024 * 1024)
    with zipfile.ZipFile(runtime) as wheel:
        for name in wheel.namelist():
            if name.endswith("/") or not any(
                x in Path(name).name.lower()
                for x in ("license", "third-party", "redist", "copyright")
            ):
                continue
            result.append(
                (
                    "LICENSES/oneMKL-2025.3.0/" + name,
                    wheel.read(name),
                    {"url": runtime_url, "archive_sha256": runtime_digest, "member": name},
                )
            )
    return result


def verify_abi(dll_data):
    if metadata.version("ctranslate2") != "4.8.3":
        raise RuntimeError("Review native runtime compatibility after updating CTranslate2")
    original = Path(metadata.distribution("ctranslate2").locate_file("ctranslate2/ctranslate2.dll"))
    checked_bytes(original.read_bytes(), CT2_SHA256, "CTranslate2 4.8.3 DLL")
    with pefile.PE(str(original)) as app, pefile.PE(data=dll_data) as runtime:
        if runtime.FILE_HEADER.Machine != 0x8664:
            raise RuntimeError("The replacement OpenMP runtime is not Windows x64")
        required = {
            item.name.decode("ascii")
            for dependency in app.DIRECTORY_ENTRY_IMPORT
            if dependency.dll.lower() == b"libiomp5md.dll"
            for item in dependency.imports
            if item.name
        }
        provided = {
            item.name.decode("ascii")
            for item in runtime.DIRECTORY_ENTRY_EXPORT.symbols
            if item.name
        }
    if len(required) != 22 or required - provided:
        raise RuntimeError(
            "OpenMP export compatibility changed: " + repr(sorted(required - provided))
        )
    return sorted(required)


def prepare():
    if sys.platform != "win32":
        raise RuntimeError("Native runtime preparation requires Windows")
    if BASE.is_symlink() or not BASE.resolve().is_relative_to((ROOT / ".venv").resolve()):
        raise RuntimeError("Native outputs must remain inside the ignored build environment")
    entries = prepare_intel_files() + prepare_intel_notices() + prepare_math_notices()
    dll_data = next(data for relative, data, _ in entries if relative == "libiomp5md.dll")
    required = verify_abi(dll_data)
    for relative, url, digest in TEXT_NOTICES:
        source = download(url, digest, relative.replace("/", "-"))
        entries.append((relative, source.read_bytes(), {"url": url, "sha256": digest}))
    sqlite_url = (
        "https://sqlite.org/src/raw/src/sqlite.h.in?ci="
        "c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9"
    )
    sqlite_digest = "284f65ed5f4b69ffe838760c4b0cc752787573bd61bf5529415fc663ef1a3022"
    sqlite = download(sqlite_url, sqlite_digest, "sqlite-3.53.1-header.in").read_bytes()
    sqlite_notice = sqlite[: sqlite.index(b"*/") + 2] + b"\n"
    checked_bytes(
        sqlite_notice,
        "85806d613cfda5901f848b3b5b4b04396c8c64e89c97c0af3706c42b0c44bb47",
        "SQLite public-domain notice",
    )
    entries.append(
        (
            "LICENSES/SQLite-3.53.1/COPYRIGHT.txt",
            sqlite_notice,
            {"url": sqlite_url, "source_sha256": sqlite_digest},
        )
    )
    inventory = []
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for relative, data, source in entries:
        target = OUTPUT / relative
        if not target.resolve().is_relative_to(OUTPUT.resolve()):
            raise RuntimeError("Native output escaped its generated directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        inventory.append(
            {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "source": source}
        )
    provenance = {
        "schema": 1,
        "openmp": {
            "vendor": "Intel",
            "runtime_version": "5.0.20250422",
            "wheel_version": "2025.2.0",
            "redistributable_package_version": "2025.2.1.1001",
            "sha256": DLL_SHA256,
            "ctranslate2_version": "4.8.3",
            "ctranslate2_sha256": CT2_SHA256,
            "required_exports_verified": required,
            "permission": (
                "Intel Developer Tools EULA August 2024, section 2.1.D; "
                "fredist.txt explicitly lists libiomp5md.dll."
            ),
            "conditions": (
                "Intel portions only: product distribution, executable code only, "
                "no reverse engineering/decompilation/disassembly, preserve notices, "
                "convey section 7 liability limits. Separately licensed third-party "
                "software keeps its own terms under section 2.2."
            ),
            "tbb_evidence": (
                "The replacement DLL embeds the version string 2022.1.0; "
                "its vendor oneTBB and TCM notices are retained."
            ),
            "verification_limit": (
                "PE exports are verified; actual CPU/GPU inference must be "
                "tested separately before completion."
            ),
        },
        "cpython_dependencies": {
            "python": "3.12.14",
            "openssl": "3.5.8",
            "sqlite": "3.53.1",
            "libffi": (
                "MIT; v3.4.8 notice retained. DLL has no embedded version; version "
                "inferred from matching upstream standalone build sections and "
                "build recipe, not asserted from the filename."
            ),
            "note": (
                "Only public notices are supplied here; the main build collects "
                "the actual CPython DLLs with a clean PATH."
            ),
        },
        "ctranslate2_static_dependencies": {
            "oneMKL": "2025.3.0, Intel Simplified Software License (proprietary)",
            "oneDNN": "3.1.1, Apache-2.0; complete source/notices in the library source companion",
            "build_recipe": "CTranslate2 v4.8.3/python/tools/prepare_build_environment_windows.sh",
            "evidence": (
                "Pinned release recipe plus inspected MKL/oneDNN strings in the "
                "unchanged official CTranslate2 DLL"
            ),
        },
        "files": sorted(inventory, key=lambda item: item["path"]),
    }
    (OUTPUT / "PROVENANCE.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    return OUTPUT


if __name__ == "__main__":
    prepare()
    print("NATIVE_RUNTIME_READY (pinned public runtime/notices; no installer executed)")
