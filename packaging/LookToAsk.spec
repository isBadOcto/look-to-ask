# Only application modules and installed runtime dependencies; never collect the workspace.
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, copy_metadata, collect_submodules

root = Path(SPECPATH).parent
sys.path.insert(0, str(root))
from scripts.native_packaging import allowed_binary, apply_native_policy, stage_sklearn_loader, ssl_runtime_data
data, binaries, hidden = [], [], []
data += ssl_runtime_data()
for package in ('mediapipe', 'cv2_enumerate_cameras'):
    d, b, h = collect_all(package)
    data += d
    binaries += b
    hidden += h
data += collect_data_files('look_to_ask')
data += collect_data_files('look_to_ask._vendor.eyetrax.models', include_py_files=True)
hidden += collect_submodules('look_to_ask._vendor.eyetrax.models')
data += collect_data_files('faster_whisper')
binaries += collect_dynamic_libs('ctranslate2')
for name in ('mediapipe', 'numpy', 'opencv-contrib-python', 'PySide6-Essentials', 'faster-whisper', 'sounddevice', 'av', 'cv2-enumerate-cameras'):
    data += copy_metadata(name)
data += [(str(root / 'build' / 'LICENSES'), 'LICENSES')]
data += [(str(root / 'LICENSE'), '.'), (str(root / 'README.md'), '.'), (str(root / 'THIRD_PARTY_NOTICES.md'), '.')]
data += [(str(root / 'docs' / name), 'docs') for name in ('PRODUCT.zh.md', 'CODEX-HANDOFF.zh.md', 'PACKAGING.md', 'DEPENDENCIES.md', 'TESTING.md', 'SPEECH.zh.md', 'TRANSLATIONS.md', 'RELINKING.md', 'LICENSE-AUDIT.zh.md')]
data += [(str(root / 'scripts/install_speech_gpu.ps1'), 'tools')]
data += [(str(root / 'tests/manual/targets.html'), 'demo')]
a = Analysis(
    [str(root / 'packaging/entrypoint.py')], pathex=[str(root / 'src')],
    binaries=binaries, datas=data, hiddenimports=hidden,
    excludes=['pytest', 'ruff', 'pip', 'tkinter', 'IPython', 'notebook', 'torch', 'PySide6.QtQml', 'PySide6.QtQuick'],
    hooksconfig={'matplotlib': {'backends': ['Agg']}},
    noarchive=False,
)
# Camera capture uses DSHOW/MSMF only; no video-file backend or software OpenGL is used.
a.binaries = apply_native_policy(a.binaries)
loader = stage_sklearn_loader()
a.pure = [(name, str(loader) if name == 'sklearn._distributor_init' else source, kind) for name, source, kind in a.pure]
a.datas = [item for item in a.datas if not item[0].lower().endswith('.dll') or allowed_binary(item[0])]
a.datas = [item for item in a.datas if not item[0].lower().endswith('.dylib')]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='LookToAsk',
    debug=False, strip=False, upx=False, console=False,
    icon=str(root / 'build' / 'LookToAsk.ico'),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='LookToAsk')
