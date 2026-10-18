"""Locate optional NVIDIA DLLs without bundling them or changing system settings."""

import ctypes
import os
import sys
import sysconfig
from pathlib import Path

_directories = {}
_libraries = {}


def prepare_cuda_libraries():
    if sys.platform != "win32":
        return  # On other systems the native loader uses its normal library paths.
    roots = [Path(sysconfig.get_paths()["purelib"])]
    if os.environ.get("LOCALAPPDATA"):
        roots.insert(0, Path(os.environ["LOCALAPPDATA"]) / "LookToAsk/gpu")
    candidates = [
        root / "nvidia" / package / "bin"
        for root in roots
        for package in ("cuda_runtime", "cublas", "cudnn")
    ]
    for variable in ("CUDA_PATH", "CUDNN_PATH"):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / "bin")
    paths = [path.resolve() for path in candidates if path.is_dir()]
    for path in paths:
        value = str(path)
        if value not in _directories:
            _directories[value] = os.add_dll_directory(value)
            # cuDNN also loads companion libraries itself, so retain a process-local PATH.
            os.environ["PATH"] = value + os.pathsep + os.environ.get("PATH", "")
    for name in ("cublasLt64_12.dll", "cublas64_12.dll", "cudnn64_9.dll"):
        if name not in _libraries:
            file = next((path / name for path in paths if (path / name).is_file()), None)
            # Without an explicit file, search only registered/system directories, not cwd.
            _libraries[name] = ctypes.WinDLL(str(file or name), winmode=0x1000)
