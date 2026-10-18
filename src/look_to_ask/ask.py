"""Active capture transaction, preview/consent UI and metadata-only session diagnostics."""

import json
import math
import re
import time
from collections import deque
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from look_to_ask.context import GazeState, capture_primary
from look_to_ask.i18n import tr
from look_to_ask.notices import license_text
from look_to_ask.platform_windows import flush_compositor
from look_to_ask.settings import AppSettings, credential_target
from look_to_ask.vision import ApiConfig, VisionClient


class DiagnosticLog:
    EVENTS = {
        "capture_requested",
        "capture_ready",
        "capture_failed",
        "capture_cancelled",
        "send_started",
        "send_rejected",
        "api_success",
        "api_failed",
        "context_closed",
        "voice_started",
        "voice_released",
        "voice_failed",
        "voice_cancelled",
        "asr_ready",
        "asr_completed",
        "voice_completed",
        "voice_trigger_received",
        "voice_rejected",
        "hotkey_registration",
        "hotkey_test",
    }
    FIELDS = {
        "capture_id",
        "gaze_global",
        "gaze_pixels",
        "gaze_in_roi",
        "roi_bounds",
        "focus_bounds",
        "image_size",
        "scale",
        "gaze_age_ms",
        "elapsed_ms",
        "answer_chars",
        "code",
        "stable_samples",
        "spread_px",
        "audio_ms",
        "asr_ms",
        "total_ms",
        "after_release_ms",
        "error_code",
        "input_rate",
        "rms_dbfs",
        "peak_dbfs",
        "full_scale_fraction",
        "speech_model",
        "speech_language",
        "beam_size",
        "speech_device",
        "speech_compute",
        "speech_fallback",
    }

    def __init__(self):
        self.records = deque(maxlen=100)
        self.started = time.monotonic()

    def record(self, event, **fields):
        if event not in self.EVENTS:
            raise ValueError("Unknown diagnostic event")
        safe = {name: value for name, value in fields.items() if name in self.FIELDS}
        for name in ("input_rate", "rms_dbfs", "peak_dbfs", "full_scale_fraction", "beam_size"):
            if name in safe and (
                type(safe[name]) not in (int, float) or not math.isfinite(safe[name])
            ):
                safe.pop(name)
        if "speech_model" in safe and safe["speech_model"] not in (
            "tiny",
            "base",
            "small",
            "medium",
            "large-v2",
            "large-v3",
            "turbo",
            "custom",
        ):
            safe["speech_model"] = "custom"
        if "speech_language" in safe and safe["speech_language"] not in ("zh", "en", "auto"):
            safe["speech_language"] = "unknown"
        for name, allowed in (
            ("speech_device", ("cuda", "cpu", "unknown")),
            ("speech_compute", ("float16", "int8", "unknown")),
            (
                "speech_fallback",
                ("", "cuda_unavailable", "gpu_load_failed", "gpu_inference_failed"),
            ),
        ):
            if name in safe and safe[name] not in allowed:
                safe[name] = "unknown"
        if "capture_id" in safe and not re.fullmatch(r"[a-f0-9]{8}", safe["capture_id"]):
            safe.pop("capture_id")
        if "code" in safe and not re.fullmatch(r"[a-z_0-9]+", safe["code"]):
            safe["code"] = "unknown"
        self.records.append(
            json.dumps(
                {"t_ms": round((time.monotonic() - self.started) * 1000), "event": event, **safe},
                ensure_ascii=False,
            )
        )

    @property
    def text(self):
        return "\n".join(self.records)


class ContextPreview(QWidget):
    def __init__(self):
        super().__init__()
        self.snapshot = None
        self.setMinimumHeight(210)

    def set_context(self, snapshot):
        self.snapshot = snapshot
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#17222b"))
        if self.snapshot is None:
            return
        image, g = self.snapshot.roi, self.snapshot.geometry
        scale = min(self.width() / image.width(), self.height() / image.height())
        width, height = image.width() * scale, image.height() * scale
        left, top = (self.width() - width) / 2, (self.height() - height) / 2
        painter.drawImage(QRectF(left, top, width, height), image)
        painter.setPen(QPen(QColor("#ffd166"), 2))
        painter.drawRect(
            QRectF(
                left + (g.focus_bounds[0] - g.roi_bounds[0]) * scale,
                top + (g.focus_bounds[1] - g.roi_bounds[1]) * scale,
                g.focus_bounds[2] * scale,
                g.focus_bounds[3] * scale,
            )
        )
        x, y = left + g.gaze_in_roi[0] * scale, top + g.gaze_in_roi[1] * scale
        painter.setPen(QPen(QColor("#111111"), 4))
        painter.drawLine(round(x - 10), round(y), round(x + 10), round(y))
        painter.drawLine(round(x), round(y - 10), round(x), round(y + 10))
        painter.setPen(QPen(QColor("#ff5ebc"), 2))
        painter.drawLine(round(x - 10), round(y), round(x + 10), round(y))
        painter.drawLine(round(x), round(y - 10), round(x), round(y + 10))


class AskDialog(QDialog):
    send_requested = Signal(object, str)
    cancel_requested = Signal()
    save_settings_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("Look to Ask · 屏幕提问"))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.snapshot = None
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(720, available.width() - 40), min(850, available.height() - 60))
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        self.status_label = QLabel(tr("截图只在主动触发时获取。"))
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status_label)
        self.preview = ContextPreview()
        layout.addWidget(self.preview)
        hint = QLabel(
            tr("粉色准星＝冻结的注视点；黄色框＝近邻小图。标记仅用于预览，不会覆盖上传原图。")
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.question_edit = QPlainTextEdit()
        self.question_edit.setPlaceholderText(
            tr("输入文字问题，例如：这个是什么意思？为什么这里报错？")
        )
        self.question_edit.setFixedHeight(75)
        layout.addWidget(self.question_edit)
        self.disclosure = QLabel()
        self.disclosure.setWordWrap(True)
        self.disclosure.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.disclosure)
        buttons = QHBoxLayout()
        self.send_button = QPushButton(tr("发送预览区域与问题"))
        self.send_button.setAutoDefault(False)
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self._send)
        buttons.addWidget(self.send_button)
        self.cancel_button = QPushButton(tr("取消请求"))
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        buttons.addWidget(self.cancel_button)
        close = QPushButton(tr("关闭并清除上下文"))
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.tabs = QTabWidget()
        self.answer_view = QPlainTextEdit()
        self.answer_view.setReadOnly(True)
        self.answer_view.setPlaceholderText(tr("AI 回答将显示在这里；尚未发送。"))
        self.tabs.addTab(self.answer_view, tr("回答"))
        settings = QWidget()
        form = QFormLayout(settings)
        config = ApiConfig.from_env()
        self.base_url_edit = QLineEdit(config.base_url)
        self.model_edit = QLineEdit(config.model)
        self.model_edit.setPlaceholderText(tr("填写支持图片的模型名"))
        self.key_edit = QLineEdit(config.api_key)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(tr("仅本机内存；本地服务可留空"))
        form.addRow(tr("API 基础地址"), self.base_url_edit)
        form.addRow(tr("视觉模型"), self.model_edit)
        form.addRow("API key", self.key_edit)
        self.remember_key = QCheckBox(tr("记住 API Key（仅 Windows 凭据管理器；不写配置文件）"))
        form.addRow(self.remember_key)
        self.speech_model_edit = QLineEdit(AppSettings().speech_model)
        self.speech_model_edit.setPlaceholderText(tr("medium（准确优先）/ small（较快）或本地目录"))
        self.speech_model_edit.setToolTip(
            tr(
                "medium 准确优先，首次约 1.5 GB；"
                "small 较快，约 490 MB；"
                "base 约 145 MB。"
                "中文提问请选择中文；大模型占用更多内存、CPU 识别也更慢。"
            )
        )
        self.language_selector = QComboBox()
        for label, value in ((tr("中文"), "zh"), (tr("英文"), "en"), (tr("自动检测"), "auto")):
            self.language_selector.addItem(label, value)
        form.addRow(tr("本地语音模型"), self.speech_model_edit)
        form.addRow(tr("识别语言"), self.language_selector)
        note = QLabel(
            tr(
                "OpenAI 兼容 Chat Completions。"
                "保存模型/地址等非敏感设置到本机；"
                "密钥默认只留本次会话。"
            )
        )
        note.setWordWrap(True)
        form.addRow(note)
        save = QPushButton(tr("保存设置"))
        save.setAutoDefault(False)
        save.clicked.connect(self.save_settings_requested.emit)
        form.addRow(save)
        self.tabs.addTab(settings, tr("API / 语音设置"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.tabs.addTab(self.log_view, tr("定位日志（内存）"))
        self.license_view = QPlainTextEdit()
        self.license_view.setReadOnly(True)
        self.license_view.setPlainText(license_text())
        self.tabs.addTab(self.license_view, tr("开源许可证"))
        self.tabs.setMinimumHeight(190)
        if not config.model:
            self.tabs.setCurrentIndex(1)
        layout.addWidget(self.tabs)
        copy = QPushButton(tr("复制定位日志（不含图片、问题、回答或密钥）"))
        copy.setAutoDefault(False)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.log_view.toPlainText()))
        layout.addWidget(copy)
        self.base_url_edit.textChanged.connect(self._disclose)
        self._key_endpoint = self._endpoint_identity()
        self.base_url_edit.textChanged.connect(self._endpoint_changed)
        self._disclose()

    def _endpoint_identity(self):
        try:
            return credential_target(self.base_url_edit.text())
        except ValueError:
            return None

    def _endpoint_changed(self):
        endpoint = self._endpoint_identity()
        if endpoint != self._key_endpoint:
            self.key_edit.clear()
            self.remember_key.setChecked(False)
            if self.isVisible():
                self.status_label.setText(
                    tr("API 地址已改变；请填写此接口的密钥，旧密钥不会发送到新接口。")
                )
        self._key_endpoint = endpoint

    def _disclose(self):
        try:
            host = urlsplit(self.base_url_edit.text()).hostname or tr("尚未填写的接口")
        except ValueError:
            host = tr("无效接口")
        self.disclosure.setText(
            tr(
                "点击发送后，两张裁剪原图和文字问题将发送到 {value0}；"
                "不发送整屏。截图默认不落盘，服务端保留规则由所选供应商决定。"
                "按住说话模式：松开按键后自动发送本次裁剪与转写；"
                "音频只在本机识别。",
                value0=host,
            )
        )

    def api_config(self):
        return ApiConfig(self.base_url_edit.text(), self.model_edit.text(), self.key_edit.text())

    def _send(self):
        self.send_requested.emit(
            self.api_config(),
            self.question_edit.toPlainText(),
        )

    def set_context(self, snapshot):
        self.snapshot = snapshot
        self.preview.set_context(snapshot)
        self.question_edit.clear()
        self.answer_view.clear()
        self.send_button.setEnabled(snapshot is not None)
        if snapshot is not None:
            g = snapshot.geometry
            self.status_label.setText(
                tr(
                    "上下文 {value0} 已冻结；"
                    "区域 {value1}×{value2} 像素，注视点 {value3}。"
                    "输入问题不会改变目标。",
                    value0=snapshot.capture_id,
                    value1=snapshot.roi.width(),
                    value2=snapshot.roi.height(),
                    value3=g.gaze_in_roi,
                )
            )

    def set_busy(self, busy):
        self.send_button.setEnabled(self.snapshot is not None and not busy)
        self.cancel_button.setEnabled(busy)


class AskController(QObject):
    context_ready = Signal(object)
    capture_failed = Signal()
    invalidated = Signal(str)

    def __init__(self, window, *, capture_factory=capture_primary, delay_ms=150):
        super().__init__(window)
        self.window = window
        self.gaze = GazeState()
        self.capture_factory = capture_factory
        self.delay_ms = delay_ms
        self.dialog = AskDialog()
        self.client = VisionClient(self)
        self.log = DiagnosticLog()
        self.pending = False
        self.reserved = False
        self._generation = 0
        self._shutting_down = False
        self._request_id = None
        self._started = 0.0
        self.dialog.send_requested.connect(self._send)
        self.dialog.cancel_requested.connect(self.client.cancel)
        self.dialog.finished.connect(self._closed)
        self.client.completed.connect(self._answered)
        self.client.failed.connect(self._failed)

    @property
    def suppress_marker(self):
        return self.pending or self.dialog.isVisible()

    def _record(self, event, **fields):
        self.log.record(event, **fields)
        self.dialog.log_view.setPlainText(self.log.text)

    def trigger(self, *, frozen_point=None, voice=False):
        w = self.window
        if self.pending or self.client.busy or (self.reserved and not voice):
            w._set_status(tr("已有截图或 AI 请求，请等待或在问答窗口取消。"))
            return
        if (
            w._closing
            or w._calibrating
            or not w._has_calibration
            or w.worker is None
            or w.worker.stopping
        ):
            w._set_status(tr("请先完成校准并等待正常跟踪，再触发屏幕提问。"))
            return
        try:
            point = (
                self.gaze.freeze(w.screen, now=time.monotonic())
                if frozen_point is None
                else frozen_point
            )
        except ValueError as exc:
            w._set_status(str(exc))
            return
        self.pending = True
        self.reserved = voice
        self._generation += 1
        generation = self._generation
        self.dialog.set_context(None)
        self._record(
            "capture_requested",
            gaze_global=point,
            gaze_age_ms=round((time.monotonic() - self.gaze.sample[2]) * 1000),
        )
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible():
                widget.hide()
        QTimer.singleShot(self.delay_ms, lambda: self._capture(generation, point))
        return True

    def _capture(self, generation, point):
        if not self.pending or generation != self._generation or self._shutting_down:
            return
        started = time.monotonic()
        try:
            if any(widget.isVisible() for widget in QApplication.topLevelWidgets()):
                raise ValueError(tr("截图期间应用窗口重新出现；请再次触发。"))
            flush_compositor()
            snapshot = self.capture_factory(self.window.screen, point)
        except Exception as exc:
            self.pending = False
            self.window.show()
            self._record("capture_failed", code="capture_failed")
            self.window._set_status(
                str(exc)
                if isinstance(exc, ValueError)
                else tr("截图失败；请检查当前桌面是否允许捕获。")
            )
            self.capture_failed.emit()
            return
        self.pending = False
        g = snapshot.geometry
        self._record(
            "capture_ready",
            capture_id=snapshot.capture_id,
            gaze_global=g.gaze_global,
            gaze_pixels=g.gaze_pixels,
            gaze_in_roi=g.gaze_in_roi,
            image_size=g.image_size,
            roi_bounds=g.roi_bounds,
            focus_bounds=g.focus_bounds,
            scale=g.scale,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        self.dialog.set_context(snapshot)
        self.window.show()
        if not self.reserved:
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()
            self.dialog.question_edit.setFocus()
        else:
            self.dialog.set_busy(True)
        self.context_ready.emit(snapshot)

    def _send(self, config, question, *, voice=False):
        snapshot = self.dialog.snapshot
        if snapshot is None or self.pending or self.client.busy or (self.reserved and not voice):
            return False
        self._request_id, self._started = snapshot.capture_id, time.monotonic()
        try:
            self.client.send(config, snapshot, question)
        except ValueError as exc:
            self.dialog.status_label.setText(str(exc))
            self._record("send_rejected", capture_id=snapshot.capture_id, code="invalid_settings")
            return False
        self.dialog.set_busy(True)
        self.dialog.answer_view.clear()
        self.dialog.status_label.setText(tr("正在请求 AI…可取消；不会继续截屏或追随新的注视点。"))
        self._record("send_started", capture_id=snapshot.capture_id)
        return True

    def _answered(self, answer):
        self._record(
            "api_success",
            capture_id=self._request_id,
            elapsed_ms=round((time.monotonic() - self._started) * 1000),
            answer_chars=len(answer),
        )
        if self.dialog.snapshot is not None:
            self.dialog.answer_view.setPlainText(answer)
            self.dialog.tabs.setCurrentIndex(0)
            self.dialog.status_label.setText(
                tr("回答完成。请核对‘注视对象’是否对应预览准星附近内容。")
            )
        self.dialog.set_busy(False)

    def _failed(self, message, code):
        self._record(
            "api_failed",
            capture_id=self._request_id,
            code=code,
            elapsed_ms=round((time.monotonic() - self._started) * 1000),
        )
        if self.dialog.snapshot is not None:
            self.dialog.status_label.setText(message)
        self.dialog.set_busy(False)

    def _closed(self, _result):
        self.client.cancel()
        self.dialog.set_context(None)
        self._record("context_closed")
        self.invalidated.emit("context_closed")
        if not self.window._closing and not self._shutting_down:
            self.window.show()

    def invalidate(self, reason):
        was_pending = self.pending
        self.pending = False
        self._generation += 1
        self.gaze.clear()
        self.client.cancel()
        self.dialog.set_context(None)
        self.dialog.hide()
        self.invalidated.emit(reason)
        if was_pending:
            self._record("capture_cancelled", code=reason)
            if not self.window._closing:
                self.window.show()

    def shutdown(self):
        self._shutting_down = True
        self.invalidate("shutdown")
        self.dialog.close()
