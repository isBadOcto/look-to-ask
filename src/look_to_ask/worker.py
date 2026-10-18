"""Own camera, EyeTrax and calibration on one thread; never send frames to the UI."""

import queue
import threading
import time
import uuid

import numpy as np
from PySide6.QtCore import QThread, Signal

from look_to_ask.calibration import CalibrationError, CalibrationSession, ScreenRect
from look_to_ask.gaze import CameraError, EyeTraxBackend, open_camera, prediction_on_screen
from look_to_ask.i18n import tr
from look_to_ask.validation import measure_accuracy


class TrackingWorker(QThread):
    ready = Signal()
    status = Signal(str)
    error = Signal(str)
    target = Signal(int, int, int)
    calibrated = Signal()
    gaze = Signal(int, int, float)
    lost = Signal()
    calibration_cancelled = Signal()
    validation_finished = Signal(str)
    fit_diagnostics = Signal(str)

    def __init__(
        self,
        screen: ScreenRect,
        camera_index=0,
        face_model=None,
        *,
        camera_resolution=(640, 480),
        camera_backend=None,
        camera_factory=open_camera,
        backend_factory=EyeTraxBackend,
    ):
        super().__init__()
        self.screen = screen
        self.camera_index = camera_index
        self.camera_resolution = tuple(camera_resolution)
        self.camera_backend = camera_backend
        self.face_model = face_model
        self._camera_factory = camera_factory
        self._backend_factory = backend_factory
        self._stop_event = threading.Event()
        self._commands = queue.SimpleQueue()

    @property
    def stopping(self):
        return self._stop_event.is_set()

    def stop(self):
        self._stop_event.set()

    def recalibrate(self, profile="quick"):
        self._commands.put(("calibrate", profile))

    def validate(self):
        self._commands.put(("validate", None))

    def cancel_calibration(self):
        self._commands.put(("cancel", None))

    def target_visible(self, index):
        self._commands.put(("visible", index))

    def run(self):
        if self.stopping:
            return
        camera = backend = None
        try:
            width, height = self.camera_resolution
            self.status.emit(
                tr("正在打开摄像头（请求 {value0}×{value1}）…", value0=width, value1=height)
            )
            options = {"resolution": self.camera_resolution}
            if self.camera_backend is not None:
                options["api_preference"] = self.camera_backend
            camera = self._camera_factory(self.camera_index, **options)
            if self.stopping:
                return
            self.status.emit(tr("正在加载本地眼动引擎（首次可能下载 MediaPipe 模型）…"))
            backend = self._backend_factory(face_model=self.face_model)
            from look_to_ask._vendor.eyetrax.filters.kalman_ema import KalmanEMASmoother

            smoother = KalmanEMASmoother()
            session = None
            failed_reads = 0
            last_status = 0.0
            last_prediction = 0.0
            idle_message = tr("尚未校准；点击重新校准。")
            calibration_profile = "quick"
            calibration_id = tr("未编号")
            measurement_number = 0
            self.ready.emit()
            while not self.stopping:
                while not self._commands.empty():
                    command, value = self._commands.get()
                    if command == "calibrate":
                        idle_message = tr("尚未校准；点击重新校准。")
                        backend.calibrated = False
                        calibration_profile = value
                        calibration_id = uuid.uuid4().hex[:8]
                        measurement_number = 0
                        session = CalibrationSession(
                            self.screen.width, self.screen.height, profile=value
                        )
                        smoother = KalmanEMASmoother()
                        self.lost.emit()
                        self.target.emit(0, *session.points[0])
                    elif command == "validate":
                        if not backend.calibrated:
                            self.calibration_cancelled.emit()
                            self.status.emit(tr("请先完成校准，再测量精度。"))
                            continue
                        idle_message = ""
                        session = CalibrationSession(
                            self.screen.width, self.screen.height, profile="validation"
                        )
                        self.lost.emit()
                        self.target.emit(0, *session.points[0])
                    elif command == "cancel":
                        if session is None:
                            continue  # Late/repeated Esc must not invalidate a completed model.
                        validating = session.profile == "validation"
                        session = None
                        if not validating:
                            backend.calibrated = False
                        self.lost.emit()
                        self.calibration_cancelled.emit()
                        idle_message = (
                            tr("精度测量已取消，原校准保留。")
                            if validating
                            else tr("校准已取消；点击重新校准。")
                        )
                        self.status.emit(idle_message)
                    elif command == "visible" and session is not None and session.index == value:
                        session.target_visible(time.monotonic())
                if self.stopping:
                    break
                ok, frame = camera.read()
                if not ok or frame is None or not frame.size:
                    failed_reads += 1
                    self.lost.emit()
                    if failed_reads >= 10:
                        raise CameraError(tr("摄像头连续读取失败；请检查连接或占用后重新启动。"))
                    self._stop_event.wait(0.05)
                    continue
                failed_reads = 0
                if (
                    self.camera_resolution != (640, 480)
                    and (frame.shape[1], frame.shape[0]) != self.camera_resolution
                ):
                    requested_width, requested_height = self.camera_resolution
                    raise CameraError(
                        tr(
                            "请求分辨率 {value0}×{value1}，摄像头实际分辨率变为 {value2}×"
                            "{value3}；请停止后重新选择并校准。",
                            value0=requested_width,
                            value1=requested_height,
                            value2=frame.shape[1],
                            value3=frame.shape[0],
                        )
                    )
                features = backend.features(frame)
                now = time.monotonic()
                message = idle_message or tr("尚未校准；点击重新校准。")
                if session is not None:
                    old_index = session.index
                    validating = session.profile == "validation"
                    sample = features
                    if validating and features is not None:
                        sample = backend.predict(features)
                    try:
                        session.observe(sample, now)
                    except CalibrationError as exc:
                        session = None
                        idle_message = str(exc)
                        if validating:
                            idle_message = tr("精度测量未完成，原校准保留。") + idle_message
                        self.calibration_cancelled.emit()
                        self.status.emit(idle_message)
                        continue
                    if session.done:
                        if validating:
                            samples, targets = session.sample_data()
                            report_text = measure_accuracy(
                                samples,
                                targets,
                                session.points,
                                self.screen.width,
                                self.screen.height,
                                calibration_profile,
                            ).format_text()
                            measurement_number += 1
                            self.validation_finished.emit(
                                tr(
                                    "校准编号 {value0}\n测量第 {value1} 次\n",
                                    value0=calibration_id,
                                    value1=measurement_number,
                                )
                                + report_text
                            )
                        else:
                            self.status.emit(tr("正在完成个人屏幕坐标校准…"))
                            diagnostics = backend.calibrate(*session.training_data())
                            if diagnostics is not None:
                                self.fit_diagnostics.emit(
                                    tr(
                                        "校准编号 {value0}\n"
                                        "摄像头请求分辨率 {value1}×{value2}\n"
                                        "摄像头实际分辨率 {value3}×{value4}\n",
                                        value0=calibration_id,
                                        value1=width,
                                        value2=height,
                                        value3=frame.shape[1],
                                        value4=frame.shape[0],
                                    )
                                    + diagnostics.format_text()
                                )
                            self.calibrated.emit()
                        idle_message = ""
                        session = None  # Release personal feature samples immediately.
                        last_prediction = 0.0
                        continue
                    if session.index != old_index:
                        self.target.emit(session.index, *session.points[session.index])
                    stage = tr("采样中") if session.collecting else tr("请稳定注视圆点")
                    if sample is None or not np.isfinite(sample).all():
                        stage = tr("未检测到睁开的眼睛，请面向摄像头")
                    mode = tr("精度测量") if validating else tr("校准")
                    message = tr(
                        "{value0} {value1}/{value2} · {value3} · 有效帧 {value4}",
                        value0=mode,
                        value1=session.index + 1,
                        value2=session.total,
                        value3=stage,
                        value4=session.sample_count,
                    )
                elif backend.calibrated and features is not None:
                    prediction = backend.predict(features)
                    raw_point = prediction_on_screen(
                        prediction, self.screen.width, self.screen.height
                    )
                    if raw_point is not None:
                        if now - last_prediction > 0.5:
                            smoother = KalmanEMASmoother()
                        # Neither raw predictions nor filter overshoot may become fake edge dots.
                        x, y = map(int, raw_point)
                        filtered = prediction_on_screen(
                            smoother.step(x, y), self.screen.width, self.screen.height
                        )
                        if filtered is None:
                            self.lost.emit()
                            message = tr("平滑结果越界，标记暂时隐藏；请测量精度检查原始预测。")
                        else:
                            point = self.screen.to_global(filtered)
                            self.gaze.emit(*point, now)
                            last_prediction = now
                            label = getattr(backend, "mapping_label", "EyeTrax")
                            message = tr(
                                "跟踪中 · {value0} · 绿色圆点表示估计注视位置", value0=label
                            )
                    else:
                        self.lost.emit()
                        message = tr("预测越界或无效，标记已隐藏；请测量精度或重新校准。")
                elif backend.calibrated:
                    self.lost.emit()
                    message = tr("跟踪丢失或眨眼 · 标记已隐藏")
                if session is None and backend.calibrated and idle_message:
                    message = idle_message + "\n" + message
                if now - last_status >= 0.2:
                    self.status.emit(message)
                    last_status = now
                self._stop_event.wait(0.005)
        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.lost.emit()
            try:
                if camera is not None:
                    camera.release()
            finally:
                if backend is not None:
                    backend.close()
