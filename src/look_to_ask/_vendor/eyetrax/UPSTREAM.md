# EyeTrax core subset

- Source: https://github.com/ck-zhang/EyeTrax
- Version: 0.4.0
- Commit: `84e13a16af168ac7c383f7d50ec901cd6c0ad61d` (2026-02-24)
- License: MIT; the original copyright and permission notice are in `LICENSE`.
- `manifest.json` records original and local SHA-256 hashes for every copied module.

We reuse upstream gaze feature extraction, Ridge calibration, Kalman and EMA code.
No gaze algorithm or pretrained model is trained or replaced here. The upstream `.task`
asset is downloaded to the normal EyeTrax cache, not committed to this repository.

Changes to copied files: absolute `eyetrax.*` imports use our private package namespace;
`filters/__init__.py` omits imports/exports for unused KDE and noop modules.
Package `__init__.py` and `utils/__init__.py` are small local entry points.
Only Ridge is included, so upstream model auto-discovery finds Ridge alone.
Other copied modules are otherwise unchanged; exclude this directory from automatic formatting.

Reason for vendoring: the PyPI distribution unconditionally requires GPLv2 `pyvirtualcam`
and `opencv-python`, while MediaPipe also requires `opencv-contrib-python`. Phase 1 uses
neither virtual cameras nor upstream CLI/demo/calibration UI. This attributed MIT subset
avoids the unused GPL dependency and installs a single `cv2` distribution. Updates require
an explicit upstream source review and manifest refresh, rather than an unbounded pip upgrade.

Upstream save/load helpers exist in BaseModel but our application never invokes them.
Upstream optional filter tuning/camera helpers exist for source fidelity but are not invoked.
