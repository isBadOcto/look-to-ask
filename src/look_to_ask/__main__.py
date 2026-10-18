"""Application entry point and explicit, non-recording diagnostic commands."""

import argparse
import importlib
import importlib.metadata
import json
import os
import sys
import time
import traceback
from pathlib import Path

from look_to_ask.i18n import tr


def check_dependencies():
    print(f"Python {sys.version.split()[0]} · {sys.platform}")
    from look_to_ask._vendor.eyetrax import __version__ as eye_version

    print(f"EyeTrax core {eye_version}: vendored MIT source, import OK")
    for package, module in (
        ("mediapipe", "mediapipe"),
        ("numpy", "numpy"),
        ("opencv-contrib-python", "cv2"),
        ("PySide6-Essentials", "PySide6.QtWidgets"),
        ("faster-whisper", "faster_whisper"),
        ("sounddevice", "sounddevice"),
    ):
        importlib.import_module(module)
        print(f"{package} {importlib.metadata.version(package)}: import OK")
    model = Path.home() / ".cache" / "eyetrax" / "mediapipe" / "face_landmarker.task"
    print(f"FaceLandmarker cache: {'present' if model.exists() else 'not downloaded'}")
    print("CHECK_OK (no camera, microphone or screen capture)")


def probe_camera(index, resolution=(640, 480)):
    from look_to_ask.gaze import open_camera

    camera = open_camera(index, resolution=resolution)
    try:
        for _ in range(12):
            ok, frame = camera.read()
            if not ok or frame is None or not frame.size:
                raise RuntimeError(tr("摄像头已打开，但未能连续返回有效帧。"))
            if resolution != (640, 480) and (frame.shape[1], frame.shape[0]) != resolution:
                raise RuntimeError(tr("摄像头未能连续返回所选分辨率，不能作为高清测试。"))
        print(f"CAMERA_OK index={index}, frames=12, size={frame.shape[1]}x{frame.shape[0]}")
        print(f"Requested size: {resolution[0]}x{resolution[1]}")
        print("Frames processed in memory only; camera released.")
    finally:
        camera.release()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Look to Ask — Windows gaze and push-to-talk screen questions"
    )
    parser.add_argument(
        "--camera-index", type=int, default=None, help="Override saved camera index"
    )
    parser.add_argument("--face-model", type=Path, help="Local MediaPipe face_landmarker.task path")
    parser.add_argument(
        "--camera-resolution",
        choices=("640x480", "1280x720", "1920x1080"),
        default=None,
        help="Capture resolution; 720p/1080p are optional experiments, not accuracy guarantees",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="Import dependencies without opening camera"
    )
    mode.add_argument(
        "--check-engine", action="store_true", help="Load real EyeTrax model; may download model"
    )
    mode.add_argument(
        "--probe-camera", action="store_true", help="Read 12 real frames, store nothing"
    )
    mode.add_argument(
        "--smoke-ui", action="store_true", help="Open/close UI only; no camera or gaze"
    )
    mode.add_argument(
        "--check-speech", action="store_true", help="Load local Whisper/VAD, never record audio"
    )
    parser.add_argument(
        "--speech-model", default="medium", help="Model for explicit --check-speech only"
    )
    parser.add_argument(
        "--speech-device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="Backend for explicit --check-speech only; cuda fails instead of falling back",
    )
    parser.add_argument(
        "--speech-fixture",
        type=Path,
        help="Explicit --check-speech only: decode a local WAV and run three recognition turns",
    )
    parser.add_argument(
        "--report", type=Path, help="Write metadata-only diagnostic report for an explicit check"
    )
    args = parser.parse_args(argv)
    camera_resolution = (
        tuple(int(value) for value in args.camera_resolution.split("x"))
        if args.camera_resolution
        else None
    )
    if args.camera_index is not None and args.camera_index < 0:
        parser.error("--camera-index must be nonnegative")
    if args.report and not any((args.check, args.check_engine, args.check_speech, args.smoke_ui)):
        parser.error("--report requires an explicit non-recording check")
    if args.speech_fixture and not args.check_speech:
        parser.error("--speech-fixture requires --check-speech")
    from look_to_ask import __version__

    speech_details = {}

    def finish(code, error=None, error_module=None, error_frames=None):
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(
                    {
                        "version": __version__,
                        "ok": code == 0,
                        "error_type": error,
                        "missing_module": error_module,
                        "frames": error_frames,
                        "frozen": bool(getattr(sys, "frozen", False)),
                        "platform": sys.platform,
                        "check": "dependencies"
                        if args.check
                        else "engine"
                        if args.check_engine
                        else "speech"
                        if args.check_speech
                        else "ui",
                        **speech_details,
                    }
                ),
                "utf-8",
            )
        return code

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    try:
        if args.check:
            check_dependencies()
            return finish(0)
        if args.check_engine:
            from look_to_ask.gaze import EyeTraxBackend

            backend = EyeTraxBackend(face_model=args.face_model)
            backend.close()
            print("ENGINE_OK (real MediaPipe/EyeTrax initialized; gaze accuracy not tested)")
            return finish(0)
        if args.check_speech:
            from faster_whisper.vad import get_vad_model

            from look_to_ask.speech import load_model

            model = load_model(args.speech_model, device=args.speech_device)
            get_vad_model()
            speech_details.update(
                speech_device=model.device,
                speech_compute=model.compute_type,
                speech_fallback=model.fallback_reason,
            )
            if args.speech_fixture:
                from faster_whisper.audio import decode_audio

                from look_to_ask.speech import transcribe_audio

                with args.speech_fixture.open("rb") as fixture:
                    audio = decode_audio(fixture)
                turns = []
                for _ in range(3):
                    started = time.perf_counter()
                    text = transcribe_audio(model, audio, "zh")
                    turns.append(
                        {
                            "chars": len(text),
                            "asr_ms": round((time.perf_counter() - started) * 1000),
                        }
                    )
                speech_details["inference_turns"] = turns
                speech_details.update(
                    speech_device=model.device,
                    speech_compute=model.compute_type,
                    speech_fallback=model.fallback_reason,
                )
                model.close()
                print("SPEECH_INFERENCE_OK (three local fixture turns; no audio/text in report)")
                return finish(0)
            print(
                f"SPEECH_ENGINE_OK (device={model.device}, compute={model.compute_type}; "
                "model/VAD loaded; microphone not opened; inference not tested)"
            )
            return finish(0)
        if args.probe_camera:
            probe_camera(args.camera_index or 0, camera_resolution or (640, 480))
            return 0
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox

        from look_to_ask.ui import ControlWindow

        app = QApplication([sys.argv[0]])
        app.setApplicationName("LookToAsk")
        app.setOrganizationName("LookToAsk")
        from look_to_ask.desktop import acquire_instance_lock, app_icon
        from look_to_ask.i18n import install_language
        from look_to_ask.settings import SettingsStore

        settings_store = SettingsStore()
        install_language(settings_store.load().ui_language)
        app.setWindowIcon(app_icon())
        instance_lock = None
        if not args.smoke_ui:
            instance_lock = acquire_instance_lock(settings_store.path.parent)
            if instance_lock is None:
                QMessageBox.information(
                    None,
                    "Look to Ask",
                    tr("程序已经运行。请切换到现有窗口；重复启动会占用摄像头和快捷键。"),
                )
                return 0
        window = ControlWindow(
            args.camera_index,
            args.face_model,
            camera_resolution=camera_resolution,
            settings_store=settings_store,
        )
        if args.smoke_ui:
            notices = window.ask.dialog.license_view.toPlainText()
            speech_details.update(
                ui_language=window.ui_language,
                license_notice_loaded="LGPL" in notices and "Independent JPEG Group" in notices,
            )
        window.show()
        if args.smoke_ui:
            window.status_label.setText(tr("UI 自动冒烟测试：未打开摄像头或开始注视预测。"))
            QTimer.singleShot(400, window.close)
        result = app.exec()
        if instance_lock:
            instance_lock.unlock()
        if args.smoke_ui and result == 0:
            print("UI_SMOKE_OK (no camera, screen capture or AI request)")
        return finish(result)
    except Exception as exc:
        if sys.stderr is not None:
            if args.check_speech:
                print(
                    f"SPEECH_CHECK_FAILED ({type(exc).__name__}); "
                    "check model name/path, network and disk space.",
                    file=sys.stderr,
                )
            else:
                print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        elif not args.report:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                tr(
                    "程序无法启动（{value0}）。请重新安装或查看 README 的排错步骤。",
                    value0=type(exc).__name__,
                ),
                "Look to Ask",
                0x10,
            )
        return finish(
            1,
            type(exc).__name__,
            exc.name if isinstance(exc, ModuleNotFoundError) else None,
            [
                {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                for f in traceback.extract_tb(exc.__traceback__)
            ],
        )


if __name__ == "__main__":
    raise SystemExit(main())
