"""One push-to-talk turn binds local transcription to the context frozen at press."""

import time

from PySide6.QtCore import QObject, QTimer, Signal

from look_to_ask.i18n import tr
from look_to_ask.speech import SPEECH_BEAM_SIZE, PushToTalkRecorder, SpeechWorker


class VoiceController(QObject):
    status = Signal(str)
    recording_ended = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window, self.ask = window, window.ask
        self.recorder = PushToTalkRecorder()
        self.engine = SpeechWorker(self)
        self.active = False
        self._identity = 0
        self._released = self._sending = False
        self._snapshot = self._text = self._config = None
        self._started = 0.0
        self._released_at = 0.0
        self._shutting_down = False
        self.limit = QTimer(self)
        self.limit.setSingleShot(True)
        self.limit.timeout.connect(
            lambda: self.cancel(tr("超过 30 秒，本次语音已取消。"), "too_long")
        )
        self.monitor = QTimer(self)
        self.monitor.setInterval(20)
        self.monitor.timeout.connect(self._check_recording)
        self.engine.prepared.connect(self._prepared)
        self.engine.transcribed.connect(self._transcribed)
        self.engine.failed.connect(self._failed)
        self.ask.context_ready.connect(self._captured)
        self.ask.capture_failed.connect(
            lambda: self.cancel(tr("截图失败，本次语音没有发送。"), "capture_failed")
        )
        self.ask.invalidated.connect(lambda reason: self.cancel(tr("本次语音已取消。"), reason))
        self.ask.dialog.cancel_requested.connect(lambda: self.cancel(tr("本次语音已取消。")))
        self.ask.client.completed.connect(lambda _answer: self._finished("ok"))
        self.ask.client.failed.connect(lambda _message, code: self._finished(code))

    def prepare(self):
        if self.active or self._shutting_down:
            return
        try:
            self.engine.prepare(self.ask.dialog.speech_model_edit.text())
        except ValueError as exc:
            self.status.emit(str(exc))
            return
        name = self.ask.dialog.speech_model_edit.text().strip()
        size = {"base": "145 MB", "small": "490 MB", "medium": "1.5 GB"}.get(name)
        note = tr("首次约 {value0}", value0=size) if size else tr("首次可能下载通用模型")
        self.status.emit(tr("正在准备本地语音模型；{value0}。尚未开启麦克风。", value0=note))

    def _prepared(self, name, elapsed_ms):
        preset = (
            name
            if name in ("tiny", "base", "small", "medium", "large-v2", "large-v3", "turbo")
            else "custom"
        )
        self.ask._record(
            "asr_ready",
            elapsed_ms=elapsed_ms,
            speech_model=preset,
            beam_size=SPEECH_BEAM_SIZE,
            **self._backend_fields(),
        )
        label = preset if preset != "custom" else tr("自定义模型")
        self.status.emit(
            tr(
                "语音模型 {value0} 已就绪（{value1}）。"
                "稳定注视目标，按住 Ctrl+Alt+Space 或 Ctrl+Alt+V 说话，松开自动"
                "发送。",
                value0=label,
                value1=self._backend_label(),
            )
        )

    def _backend_fields(self):
        return {
            "speech_device": self.engine.device,
            "speech_compute": self.engine.compute_type,
            "speech_fallback": self.engine.fallback_reason,
        }

    def _backend_label(self):
        if self.engine.device == "cuda":
            return tr("GPU 加速")
        if self.engine.device == "cpu":
            return tr("已回退 CPU") if self.engine.fallback_reason else "CPU"
        return tr("本地识别")

    def _reject(self, message, code):
        self.ask._record("voice_rejected", code=code)
        self.status.emit(message)
        return False

    def press(self):
        w = self.window
        if self.active:
            return self._reject(tr("本轮语音仍在处理；请先松开按键并等回答完成。"), "voice_busy")
        if self._shutting_down:
            return self._reject(tr("程序正在退出。"), "shutting_down")
        if self.ask.pending:
            return self._reject(tr("正在获取截图，请稍后再按住说话。"), "capture_busy")
        if self.ask.client.busy:
            return self._reject(tr("AI 请求尚未结束；请等待或先取消。"), "api_busy")
        if self.engine.busy:
            return self._reject(tr("语音引擎仍在处理，请稍后重试。"), "engine_busy")
        if (
            w._closing
            or w._calibrating
            or not w._has_calibration
            or w.worker is None
            or w.worker.stopping
        ):
            return self._reject(tr("请先完成校准并恢复正常跟踪。"), "not_calibrated")
        try:
            config = self.ask.dialog.api_config()
            _ = config.endpoint  # Validate before recording or taking a screenshot.
        except ValueError as exc:
            return self._reject(str(exc), "invalid_settings")
        try:
            point, stats = self.ask.gaze.freeze_stable(w.screen, now=time.monotonic())
        except ValueError as exc:
            return self._reject(str(exc), "gaze_not_ready")
        if self.engine.loaded_name != self.ask.dialog.speech_model_edit.text().strip():
            self.ask._record("voice_rejected", code="model_not_ready")
            self.prepare()
            return False
        self._started = time.monotonic()
        try:
            self.recorder.start()
        except ValueError as exc:
            self.status.emit(str(exc))
            self.ask._record("voice_failed", code="microphone_failed")
            return False
        self._identity += 1
        self.active = True
        self._released = self._sending = False
        self._snapshot = self._text = None
        self._config = config
        if not self.ask.trigger(frozen_point=point, voice=True):
            self.cancel(tr("无法获取注视上下文，本次未录音发送。"), "context_unavailable")
            return False
        self.limit.start(self.recorder.MAX_SECONDS * 1000)
        self.monitor.start()
        self.ask._record("voice_started", gaze_global=point, **stats)
        self.status.emit(tr("正在录音（最多 30 秒）…目标已锁定；松开后自动发送裁剪与转写。"))
        return True

    def _check_recording(self):
        if self.active and not self._released and self.recorder.fault:
            self.cancel(tr("麦克风溢出或录音异常，本次没有发送；请重试。"), "audio_overflow")

    def release(self):
        if not self.active or self._released:
            return
        self.limit.stop()
        self.monitor.stop()
        self.recording_ended.emit()
        self._released = True
        self._released_at = time.monotonic()
        try:
            audio, duration = self.recorder.stop()
            self.engine.transcribe(
                self._identity,
                audio,
                self.ask.dialog.language_selector.currentData(),
            )
        except ValueError as exc:
            self.cancel(str(exc), "recording_failed")
            return
        stats = getattr(self.recorder, "signal_stats", None) or {}
        self.ask._record(
            "voice_released",
            audio_ms=round(duration * 1000),
            speech_language=self.ask.dialog.language_selector.currentData(),
            **stats,
        )
        hint = (
            tr("录音有较多满幅样本，可尝试降低麦克风输入音量。")
            if stats.get("full_scale_fraction", 0) >= 0.01
            else tr("录音平均音量较低，可尝试靠近麦克风或提高输入音量。")
            if stats.get("rms_dbfs", 0) < -45
            else ""
        )
        self.status.emit(tr("麦克风已关闭，正在本地识别…") + hint)
        self._show_processing()

    def _show_processing(self):
        if self.active and self._released and not self.ask.pending and self._snapshot is not None:
            self.ask.dialog.show()
            self.ask.dialog.set_busy(True)
            self.ask.dialog.status_label.setText(
                tr("麦克风已关闭；本地识别后自动发送此固定区域。可取消。")
            )

    def _captured(self, snapshot):
        if self.active:
            self._snapshot = snapshot
            self._show_processing()
            self._maybe_send()

    def _transcribed(self, identity, text, elapsed_ms):
        if not self.active or identity != self._identity or self._sending:
            return
        self._text = text
        self.ask._record("asr_completed", asr_ms=elapsed_ms, **self._backend_fields())
        self._maybe_send()

    def _maybe_send(self):
        if not (self.active and self._released and self._snapshot and self._text) or self._sending:
            return
        if self.ask.dialog.snapshot is not self._snapshot:
            self.cancel(tr("上下文已改变，本次语音没有发送。"), "context_changed")
            return
        self.ask.dialog.question_edit.setPlainText(self._text)
        self.ask.dialog.show()
        self._sending = True
        if not self.ask._send(self._config, self._text, voice=True):
            self._finished("send_rejected")
            return
        self.status.emit(tr("本地识别完成（{value0}），正在请求 AI…", value0=self._backend_label()))

    def _failed(self, identity, message, code):
        if identity == 0:
            self.status.emit(message)
            self.ask._record("voice_failed", code=code, **self._backend_fields())
        elif self.active and identity == self._identity:
            self.ask._record("voice_failed", code=code, **self._backend_fields())
            self.cancel(f"{message}（{self._backend_label()}）", code)

    def _finished(self, code):
        if not self.active or not self._sending:
            return
        self.ask._record(
            "voice_completed",
            capture_id=self._snapshot.capture_id,
            code=code,
            total_ms=round((time.monotonic() - self._started) * 1000),
            after_release_ms=round((time.monotonic() - self._released_at) * 1000),
        )
        self.active = self.ask.reserved = False
        self._snapshot = self._text = self._config = None
        self.ask.dialog.set_busy(False)
        self.status.emit(
            tr("本轮语音回答完成，可以继续按住说话。")
            if code == "ok"
            else tr("本轮 AI 请求未完成，可重试或文字提问。")
        )

    def cancel(self, message=None, code="cancelled"):
        message = tr("本次语音已取消。") if message is None else message
        if not self.active:
            return
        self.active = False  # Invalidate before signals from abort/invalidate can reenter.
        self._identity += 1
        self.limit.stop()
        self.monitor.stop()
        self.recording_ended.emit()
        self.recorder.cancel()
        self.ask.reserved = False
        self._snapshot = self._text = self._config = None
        self.ask._record("voice_cancelled", code=code)
        self.ask.invalidate(code)
        self.status.emit(message)

    def shutdown(self):
        self._shutting_down = True
        self.cancel()
        self.engine.shutdown()
