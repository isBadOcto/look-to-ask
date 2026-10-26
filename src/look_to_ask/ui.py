"""Control window, calibration target and transparent gaze marker."""

import time
from dataclasses import replace

import cv2
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from look_to_ask.ask import AskController
from look_to_ask.calibration import ScreenRect
from look_to_ask.devices import list_cameras
from look_to_ask.gaze import CAMERA_RESOLUTIONS
from look_to_ask.i18n import install_language, tr
from look_to_ask.platform_windows import GlobalHotkeys, HoldReleaseWatcher
from look_to_ask.settings import AppSettings, SettingsError, SettingsStore, credential_target
from look_to_ask.tray import DesktopTray
from look_to_ask.vision import ApiConfig
from look_to_ask.voice import VoiceController
from look_to_ask.worker import TrackingWorker


class GazeMarker(QWidget):
    def __init__(self, screen: ScreenRect):
        super().__init__()
        self.screen = screen
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(44, 44)
        self._last_gaze = 0.0
        self._watchdog = QTimer(self)
        self._watchdog.timeout.connect(self._expire)
        self._watchdog.start(100)

    def update_gaze(self, x, y, timestamp=None):
        now = time.monotonic()
        timestamp = now if timestamp is None else timestamp
        if now - timestamp > 0.5:
            self.hide()
            return
        self._last_gaze = timestamp
        self.move(x - self.width() // 2, y - self.height() // 2)
        self.show()

    def _expire(self):
        if time.monotonic() - self._last_gaze > 0.5:
            self.hide()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#102a22"), 5))
        painter.drawEllipse(QRectF(8, 8, 28, 28))
        painter.setPen(QPen(QColor("#5ef0aa"), 3))
        painter.drawEllipse(QRectF(8, 8, 28, 28))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#5ef0aa"))
        painter.drawEllipse(QPointF(22, 22), 3, 3)


class CalibrationWindow(QWidget):
    visible_target = Signal(int)
    cancelled = Signal()
    exit_requested = Signal()

    def __init__(self, screen: ScreenRect):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setGeometry(screen.x, screen.y, screen.width, screen.height)
        self._target = None
        self._pending_ack = False
        self.message = tr("请保持头部稳定，只用眼睛跟随圆点。")
        self.caption = tr("Look to Ask · 9 点快速校准")

    def set_session(self, title, total):
        self.caption = tr("Look to Ask · {value0} 点{value1}", value0=total, value1=title)
        self._target = None
        self._pending_ack = False
        self.message = tr("请保持头部稳定，只用眼睛跟随圆点。")

    def set_target(self, index, x, y):
        self._target = (index, x, y)
        self._pending_ack = True
        self.show()
        self.raise_()
        self.activateWindow()
        self.update()

    def set_status(self, message):
        self.message = message
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#16222c"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#e5edf2"))
        font = painter.font()
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(
            self.rect().adjusted(20, 15, -20, -15),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self.caption + tr(" · 保持头部稳定，注视绿色圆点"),
        )
        painter.drawText(
            self.rect().adjusted(20, 15, -20, -4),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            self.message + tr("\nEsc 取消本次采样 · Ctrl+Alt+Q 退出程序"),
        )
        if self._target is not None:
            index, x, y = self._target
            painter.setPen(QPen(QColor("#5ef0aa"), 3))
            painter.drawEllipse(QPointF(x, y), 26, 26)
            painter.setBrush(QColor("#5ef0aa"))
            painter.drawEllipse(QPointF(x, y), 6, 6)
            if self._pending_ack:
                self._pending_ack = False
                QTimer.singleShot(0, lambda i=index: self.visible_target.emit(i))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        elif (
            event.key() == Qt.Key.Key_Q and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.exit_requested.emit()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.cancelled.emit()
        event.accept()


class ControlWindow(QWidget):
    def __init__(
        self, camera_index=None, face_model=None, *, camera_resolution=None, settings_store=None
    ):
        super().__init__()
        self.setWindowTitle("Look to Ask")
        self.settings_store = settings_store or SettingsStore()
        self.preferences = self.settings_store.load()
        self.ui_language = install_language(self.preferences.ui_language)
        camera_index = self.preferences.camera_index if camera_index is None else camera_index
        camera_resolution = camera_resolution or self.preferences.camera_resolution
        self.setMinimumWidth(470)
        self.camera_index = camera_index
        self.face_model = face_model
        self.worker = None
        self._closing = False
        self._calibrating = False
        self._has_calibration = False
        app = QApplication.instance()
        primary = app.primaryScreen()
        geometry = primary.geometry()
        self.screen = ScreenRect(geometry.x(), geometry.y(), geometry.width(), geometry.height())
        self.marker = GazeMarker(self.screen)
        self.calibration = CalibrationWindow(self.screen)
        self.calibration.visible_target.connect(self._target_visible)
        self.calibration.cancelled.connect(self._cancel_calibration)
        self.calibration.exit_requested.connect(self.close)
        self.ask = AskController(self)
        dialog = self.ask.dialog
        config = ApiConfig.from_env()
        dialog.base_url_edit.setText(
            self.preferences.api_base_url
            if "api_base_url" in self.settings_store.saved_fields
            else config.base_url
        )
        dialog.model_edit.setText(self.preferences.api_model or config.model)
        environment_key = ""
        remembered_key = ""
        try:
            effective_target = credential_target(dialog.base_url_edit.text())
            if self.preferences.destination == "api" and effective_target == credential_target(
                self.preferences.api_base_url
            ):
                remembered_key = self.settings_store.load_key(self.preferences)
            if effective_target == credential_target(config.base_url):
                environment_key = config.api_key
        except ValueError:
            pass  # Invalid environment configuration must not supply a key to another endpoint.
        dialog.key_edit.setText(remembered_key or environment_key)
        dialog.remember_key.setChecked(self.preferences.remember_key)
        dialog.speech_model_edit.setText(self.preferences.speech_model)
        dialog.language_selector.setCurrentIndex(
            dialog.language_selector.findData(self.preferences.language)
        )
        dialog.save_settings_requested.connect(self._save_settings)
        dialog.codex_thread_edit.setText(self.preferences.codex_thread)
        dialog.codex_executable_edit.setText(self.preferences.codex_executable)
        dialog.destination_selector.setCurrentIndex(
            dialog.destination_selector.findData(self.preferences.destination)
        )
        self._api_key_user_edited = False
        dialog.key_edit.textEdited.connect(self._api_key_edited)
        dialog.destination_selector.currentIndexChanged.connect(self._destination_selected)
        self.voice = VoiceController(self)
        self.voice.engine.finished.connect(self._speech_finished)
        self.mouse_release = HoldReleaseWatcher(self)
        self.voice.recording_ended.connect(self._stop_voice_watchers)
        self.hotkey_test_timer = QTimer(self)
        self.hotkey_test_timer.setSingleShot(True)
        self.hotkey_test_timer.timeout.connect(self._voice_hotkey_test_timeout)
        self._hotkey_test_pending = False
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = QWidget()
        scroll.setWidget(panel)
        outer.addWidget(scroll)
        layout = QVBoxLayout(panel)
        available = primary.availableGeometry()
        self.resize(min(560, available.width() - 30), min(760, available.height() - 50))
        title = QLabel("Look at anything, ask anything.")
        title.setStyleSheet("font-size: 21px; font-weight: 600; margin: 8px 0;")
        layout.addWidget(title)
        language_row = QHBoxLayout()
        language_row.addWidget(QLabel("Language / 语言"))
        self.ui_language_selector = QComboBox()
        for label, code in (("System / 跟随系统", "system"), ("简体中文", "zh"), ("English", "en")):
            self.ui_language_selector.addItem(label, code)
        self.ui_language_selector.setCurrentIndex(
            self.ui_language_selector.findData(self.preferences.ui_language)
        )
        self.ui_language_selector.currentIndexChanged.connect(self._ui_language_selected)
        language_row.addWidget(self.ui_language_selector, 1)
        layout.addLayout(language_row)
        self.ui_language_hint = QLabel(tr("界面语言保存后，下次启动生效；不影响语音识别语言。"))
        self.ui_language_hint.setWordWrap(True)
        layout.addWidget(self.ui_language_hint)
        intro = QLabel(
            tr(
                "看向屏幕内容，按住快捷键说出问题。"
                "\n首次使用：选择发送目标 → 选择摄像头 → 校准 → 准备语音。"
                "\n文字提问预览后点击发送；"
                "语音提问松开后自动发送截图与转写（Codex 模式含整张主屏）。"
                "\n麦克风只在按住时开启，音频本地识别、不保存、不上传。"
                "\n首次启动眼动引擎可能下载约 4 MB 的 MediaPipe 模型。"
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.status_label = QLabel(tr("点击开始，打开默认摄像头并进行校准。"))
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setMinimumHeight(60)
        layout.addWidget(self.status_label)
        self.voice_status = QLabel(tr("语音尚未准备；先填写 API 设置，再准备本地模型。"))
        if self.preferences.destination == "codex":
            self.voice_status.setText(tr("先检查 Codex 接收对话，再准备本地语音模型。"))
        self.voice_status.setWordWrap(True)
        self.voice_status.setTextFormat(Qt.TextFormat.PlainText)
        self.voice.status.connect(self._show_voice_status)
        layout.addWidget(self.voice_status)
        self.voice_hotkey_label = QLabel()
        self.voice_hotkey_label.setWordWrap(True)
        layout.addWidget(self.voice_hotkey_label)
        camera_row = QHBoxLayout()
        self.camera_selector = QComboBox()
        self.refresh_camera_button = QPushButton(tr("刷新摄像头"))
        self.refresh_camera_button.clicked.connect(self._refresh_cameras)
        camera_row.addWidget(self.camera_selector, 1)
        camera_row.addWidget(self.refresh_camera_button)
        layout.addLayout(camera_row)
        self._refresh_cameras()
        self.camera_selector.currentIndexChanged.connect(self._camera_selected)
        resolution_label = QLabel(tr("摄像头分辨率（停止后更改，需重新校准）："))
        self.resolution_selector = QComboBox()
        for label, resolution in CAMERA_RESOLUTIONS.items():
            name = tr("默认") if resolution == (640, 480) else tr("需摄像头支持")
            self.resolution_selector.addItem(label.replace("x", "×") + f" ({name})", resolution)
        self.resolution_selector.setCurrentIndex(
            list(CAMERA_RESOLUTIONS.values()).index(tuple(camera_resolution))
        )
        layout.addWidget(self.resolution_selector)
        self.mode_selector = QComboBox()
        self.mode_selector.addItem(tr("9 点快速校准（约 25–40 秒）"), "quick")
        self.mode_selector.addItem(tr("25 点边缘校准（约 1–2 分钟）"), "dense")
        self.mode_selector.setCurrentIndex(0)
        layout.addWidget(self.mode_selector)
        self.start_button = QPushButton(tr("开始校准"))
        self.start_button.clicked.connect(self.start_calibration)
        layout.addWidget(self.start_button)
        self.measure_button = QPushButton(tr("测量精度（独立 9 点，约 25–40 秒）"))
        self.measure_button.setEnabled(False)
        self.measure_button.clicked.connect(self.start_accuracy_measurement)
        layout.addWidget(self.measure_button)
        self.ask_button = QPushButton(tr("截取注视附近内容并提问（Ctrl+Alt+A）"))
        self.ask_button.setEnabled(False)
        self.ask_button.clicked.connect(self.ask.trigger)
        layout.addWidget(self.ask_button)
        settings_button = QPushButton(tr("发送目标 / API / 语音设置（不截图）"))
        settings_button.clicked.connect(self._show_settings)
        layout.addWidget(settings_button)
        self.prepare_voice_button = QPushButton(tr("准备语音模型（首次需下载，大小见设置）"))
        self.prepare_voice_button.clicked.connect(self.voice.prepare)
        layout.addWidget(self.prepare_voice_button)
        self.voice_button = QPushButton(tr("鼠标按住说话，松开自动提问（备用 Ctrl+Alt+V）"))
        self.voice_button.pressed.connect(self._voice_button_pressed)
        layout.addWidget(self.voice_button)
        self.test_voice_hotkey_button = QPushButton(tr("自检语音快捷键（10 秒，不录音/不截图）"))
        self.test_voice_hotkey_button.clicked.connect(self._test_voice_hotkey)
        layout.addWidget(self.test_voice_hotkey_button)
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setMaximumBlockCount(120)
        self.report_view.setMinimumHeight(170)
        self.report_view.setPlaceholderText(
            tr(
                "完成 EyeTrax 校准后，可点击测量精度做独立检查。"
                "\n拟合诊断不是独立精度；"
                "重复测量应保持校准编号不变。"
                "\n可对比 9 点和 25 点校准；"
                "报告只保留在当前窗口内存。"
            )
        )
        layout.addWidget(self.report_view)
        self.stop_button = QPushButton(tr("停止摄像头"))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_camera)
        layout.addWidget(self.stop_button)
        # Diagnostics and device settings stay out of the primary question workflow.
        advanced_box = QGroupBox(tr("高级选项"))
        advanced_layout = QVBoxLayout(advanced_box)
        toggle = QPushButton(tr("展开：校准选项、分辨率、精度测量和快捷键自检"))
        toggle.setCheckable(True)
        advanced_layout.addWidget(toggle)
        self.advanced_panel = QWidget()
        advanced = QVBoxLayout(self.advanced_panel)
        for widget in (
            resolution_label,
            self.resolution_selector,
            self.mode_selector,
            self.measure_button,
            self.report_view,
            self.test_voice_hotkey_button,
        ):
            layout.removeWidget(widget)
            advanced.addWidget(widget)
        self.marker_debug = QCheckBox(tr("Codex 模式显示注视标记（仅调试）"))
        advanced.addWidget(self.marker_debug)
        self.advanced_panel.hide()
        toggle.toggled.connect(self.advanced_panel.setVisible)
        advanced_layout.addWidget(self.advanced_panel)
        layout.addWidget(advanced_box)
        self.licenses_button = QPushButton(tr("开源许可证 · Qt / PySide6 LGPLv3"))
        self.licenses_button.clicked.connect(self._show_licenses)
        layout.addWidget(self.licenses_button)
        exit_button = QPushButton(tr("退出"))
        exit_button.clicked.connect(self.close)
        layout.addWidget(exit_button)
        self.minimize_button = QPushButton(tr("最小化到托盘（后台使用快捷键）"))
        layout.addWidget(self.minimize_button)
        self.tray = DesktopTray(self)
        self.minimize_button.clicked.connect(self.tray.minimize)
        if self.tray.available:
            app.setQuitOnLastWindowClosed(False)
        self.hotkeys = GlobalHotkeys(
            app,
            self.close,
            self.start_calibration,
            self.ask.trigger,
            self._voice_hotkey_pressed,
            self.voice.release,
        )
        labels = []
        for identity, name in ((self.hotkeys.VOICE_ID, "Space"), (self.hotkeys.VOICE_ALT_ID, "V")):
            registered = identity in self.hotkeys.registered
            error = self.hotkeys.errors.get(identity, 0)
            labels.append(
                tr("Ctrl+Alt+{value0} 已注册", value0=name)
                if registered
                else tr(
                    "Ctrl+Alt+{value0} 未注册（Windows 错误 {value1}）", value0=name, value1=error
                )
            )
            self.ask._record(
                "hotkey_registration",
                code=("registered_" if registered else "unavailable_") + name.lower(),
                error_code=error,
            )
        self.voice_hotkey_label.setText(
            "; ".join(labels) + tr("。可点自检检查按键是否到达；Space 无效可用 V。")
        )
        shortcuts = tr(
            "全局：Ctrl+Alt+A 文字 · Ctrl+Alt+Space / V 按住说话\n"
            "Ctrl+Alt+R 重校准 · Ctrl+Alt+Q 退出"
        )
        if not self.hotkeys.available:
            shortcuts = tr("全局快捷键未全部注册（可能被占用）；请使用窗口按钮。")
        if self.hotkeys.ASK_ID not in self.hotkeys.registered:
            shortcuts += tr("\nCtrl+Alt+A 未注册，请使用提问按钮。")
        if self.hotkeys.VOICE_ID not in self.hotkeys.registered:
            shortcuts += tr("\nSpace 语音热键未注册，请用已注册的 V 或鼠标按住。")
        layout.addWidget(QLabel(shortcuts + tr("\n窗口内：R 重新校准 · Esc 退出")))
        self._recalibrate_shortcut = QShortcut(QKeySequence("R"), self)
        self._recalibrate_shortcut.activated.connect(self.start_calibration)
        self._exit_shortcut = QShortcut(QKeySequence("Escape"), self)
        self._exit_shortcut.activated.connect(self.close)
        primary.geometryChanged.connect(self._display_changed)
        primary.logicalDotsPerInchChanged.connect(self._display_changed)
        app.primaryScreenChanged.connect(self._display_changed)
        if self.settings_store.warning:
            self._set_status(self.settings_store.warning)

    def _refresh_cameras(self):
        if self.worker is not None:
            return
        selected = self.camera_index
        try:
            cameras = list_cameras()
        except Exception:
            cameras = []
            self._set_status(tr("无法枚举名称，请选择摄像头索引；刷新不会打开摄像头。"))
        self.camera_selector.blockSignals(True)
        self.camera_selector.clear()
        for index, name in cameras:
            self.camera_selector.addItem(f"{name} (#{index})", index)
            self.camera_selector.setItemData(
                self.camera_selector.count() - 1, cv2.CAP_DSHOW, Qt.ItemDataRole.UserRole + 1
            )
        for index in sorted({0, 1, 2, 3, selected} - {i for i, _name in cameras}):
            self.camera_selector.addItem(tr("摄像头 #{value0}（手动索引）", value0=index), index)
        self.camera_selector.setCurrentIndex(self.camera_selector.findData(selected))
        self.camera_selector.blockSignals(False)
        self.camera_backend = self.camera_selector.currentData(Qt.ItemDataRole.UserRole + 1)

    def _camera_selected(self, _index):
        if self.worker is None:
            self.camera_index = self.camera_selector.currentData()
            self.camera_backend = self.camera_selector.currentData(Qt.ItemDataRole.UserRole + 1)
            self._has_calibration = False
            self._set_status(tr("摄像头已选择；点击开始校准。"))

    def _api_key_edited(self, _text):
        self._api_key_user_edited = True

    def _destination_selected(self):
        dialog = self.ask.dialog
        if (
            dialog.destination_selector.currentData() != "api"
            or not dialog.remember_key.isChecked()
            or dialog.key_edit.text()
            or self._api_key_user_edited
        ):
            return
        try:
            saved = self.settings_store.load()
            if credential_target(dialog.base_url_edit.text()) == credential_target(
                saved.api_base_url
            ):
                dialog.key_edit.setText(self.settings_store.load_key(saved))
        except ValueError:
            pass  # Never restore a key against an invalid or different endpoint.

    def _ui_language_selected(self):
        language = self.ui_language_selector.currentData()
        try:
            self.settings_store.save_ui_language(language)
        except SettingsError as exc:
            self.ui_language_selector.blockSignals(True)
            self.ui_language_selector.setCurrentIndex(
                self.ui_language_selector.findData(self.preferences.ui_language)
            )
            self.ui_language_selector.blockSignals(False)
            self.ui_language_hint.setText(str(exc))
        else:
            self.preferences = replace(self.preferences, ui_language=language)
            self.ui_language_hint.setText(tr("界面语言已保存，请退出并重新打开程序。"))

    def _save_settings(self):
        dialog = self.ask.dialog
        destination = dialog.destination_selector.currentData()
        if destination == "codex":
            from look_to_ask.codex_handoff import parse_thread_id

            try:
                settings = replace(
                    self.settings_store.load(),
                    camera_index=self.camera_index,
                    camera_resolution=tuple(self.resolution_selector.currentData()),
                    speech_model=dialog.speech_model_edit.text().strip(),
                    language=dialog.language_selector.currentData(),
                    ui_language=self.ui_language_selector.currentData(),
                    destination="codex",
                    codex_thread=parse_thread_id(dialog.codex_thread_edit.text()),
                    codex_executable=dialog.codex_executable_edit.text().strip(),
                )
                self.settings_store.save_preferences(settings)
                self.preferences = settings
                dialog.status_label.setText(tr("Codex 目标和语音设置已保存；API 密钥未改动。"))
            except (ValueError, SettingsError) as exc:
                dialog.status_label.setText(str(exc))
            return
        settings = AppSettings(
            camera_index=self.camera_index,
            camera_resolution=tuple(self.resolution_selector.currentData()),
            api_base_url=dialog.base_url_edit.text(),
            api_model=dialog.model_edit.text(),
            speech_model=dialog.speech_model_edit.text(),
            language=dialog.language_selector.currentData(),
            ui_language=self.ui_language_selector.currentData(),
            remember_key=dialog.remember_key.isChecked(),
            destination=destination,
            codex_thread=dialog.codex_thread_edit.text().strip(),
            codex_executable=dialog.codex_executable_edit.text().strip(),
        )
        try:
            self.settings_store.save(settings, dialog.key_edit.text())
        except SettingsError as exc:
            message = str(exc)
        else:
            self.preferences = settings
            message = (
                tr("设置已保存；API Key 存于 Windows 凭据管理器。")
                if settings.remember_key
                else tr("非敏感设置已保存；API Key 仅留本次会话。")
            )
        dialog.status_label.setText(message)
        self._set_status(message)

    def _show_licenses(self):
        self.ask.dialog.tabs.setCurrentWidget(self.ask.dialog.license_view)
        self.ask.dialog.show()
        self.ask.dialog.raise_()
        self.ask.dialog.activateWindow()

    def _show_settings(self):
        if not self.ask.pending:
            self.ask.dialog.tabs.setCurrentIndex(1)
            self.ask.dialog.show()
            self.ask.dialog.raise_()

    def _show_voice_status(self, message):
        self.voice_status.setText(message)
        self._set_status(tr("语音：") + message)

    def _voice_hotkey_pressed(self):
        key_name = "V" if self.hotkeys.last_voice_key == ord("V") else "Space"
        self.ask._record("voice_trigger_received", code="keyboard_" + key_name.lower())
        if self._hotkey_test_pending:
            self._hotkey_test_pending = False
            self.hotkey_test_timer.stop()
            self.ask._record("hotkey_test", code="received")
            self._show_voice_status(
                tr(
                    "已收到 Ctrl+Alt+{value0}；快捷键通路正常。本次自检没有录音或截图。",
                    value0=key_name,
                )
            )
            return False
        return self.voice.press()

    def _test_voice_hotkey(self):
        if self.voice.active or self.ask.pending or self.ask.client.busy:
            self._show_voice_status(tr("请先结束当前提问，再自检快捷键。"))
            return
        if not any(
            identity in self.hotkeys.registered
            for identity in (self.hotkeys.VOICE_ID, self.hotkeys.VOICE_ALT_ID)
        ):
            self._show_voice_status(self.voice_hotkey_label.text())
            return
        self._hotkey_test_pending = True
        self.hotkey_test_timer.start(10000)
        self.ask._record("hotkey_test", code="waiting")
        self._show_voice_status(
            tr("快捷键自检中：请在 10 秒内按 Ctrl+Alt+Space 或 Ctrl+Alt+V；本次不录音、不截图。")
        )

    def _voice_hotkey_test_timeout(self):
        if self._hotkey_test_pending:
            self._hotkey_test_pending = False
            self.ask._record("hotkey_test", code="not_received")
            self._show_voice_status(
                tr("10 秒内未收到快捷键；检查组合键是否被输入法或其他程序拦截，可先用鼠标按住。")
            )

    def _voice_button_pressed(self):
        self.ask._record("voice_trigger_received", code="mouse")
        if self.voice.press():
            # Hiding the button during screenshot can suppress Qt's released signal.
            self.mouse_release.watch((0x01,), self.voice.release)

    def _speech_finished(self):
        if self._closing:
            self.close()

    def _stop_voice_watchers(self):
        self.mouse_release.stop()
        self.hotkeys.release_watcher.stop()

    def start_calibration(self):
        if self._closing or self._calibrating:
            return
        if self.worker is None:
            self.camera_selector.setEnabled(False)
            self.refresh_camera_button.setEnabled(False)
            self._has_calibration = False
            self.measure_button.setEnabled(False)
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.resolution_selector.setEnabled(False)
            worker = TrackingWorker(
                self.screen,
                self.camera_index,
                self.face_model,
                camera_resolution=tuple(self.resolution_selector.currentData()),
                camera_backend=self.camera_backend,
            )
            self.worker = worker
            worker.ready.connect(self._begin_calibration)
            worker.target.connect(self.calibration.set_target)
            worker.status.connect(self._set_status)
            worker.error.connect(self._set_status)
            worker.gaze.connect(self._on_gaze)
            worker.lost.connect(self._on_lost)
            worker.calibrated.connect(self._calibration_finished)
            worker.calibration_cancelled.connect(self._calibration_cancelled)
            worker.validation_finished.connect(self._validation_finished)
            worker.fit_diagnostics.connect(self._append_report)
            worker.finished.connect(self._worker_finished)
            worker.start()
        elif not self.worker.stopping:
            self._begin_calibration()

    def _begin_calibration(self):
        if self.worker is None or self.worker.stopping or self._closing:
            return
        self.ask.invalidate("recalibrate")
        self.ask_button.setEnabled(False)
        self._calibrating = True
        self._has_calibration = False
        self.start_button.setEnabled(False)
        self.measure_button.setEnabled(False)
        self.mode_selector.setEnabled(False)
        self.resolution_selector.setEnabled(False)
        self.marker.hide()
        profile = self.mode_selector.currentData()
        self.calibration.set_session(
            tr("边缘校准") if profile == "dense" else tr("快速校准"),
            25 if profile == "dense" else 9,
        )
        self.worker.recalibrate(profile)

    def start_accuracy_measurement(self):
        if (
            self.worker is None
            or self.worker.stopping
            or self._closing
            or self._calibrating
            or not self._has_calibration
        ):
            return
        self.ask.invalidate("validation")
        self.ask_button.setEnabled(False)
        self._calibrating = True
        self.start_button.setEnabled(False)
        self.measure_button.setEnabled(False)
        self.mode_selector.setEnabled(False)
        self.marker.hide()
        self.calibration.set_session(tr("独立精度测量"), 9)
        self.worker.validate()

    def _target_visible(self, index):
        if self.worker is not None and self._calibrating:
            self.worker.target_visible(index)

    def _on_gaze(self, x, y, timestamp):
        self.ask.gaze.update(x, y, timestamp)
        if not self.ask.suppress_marker and (
            self.ask.dialog.destination_selector.currentData() != "codex"
            or self.marker_debug.isChecked()
        ):
            self.marker.update_gaze(x, y, timestamp)

    def _on_lost(self):
        self.ask.gaze.clear()
        self.marker.hide()

    def _set_status(self, message):
        if not self._closing:
            self.status_label.setText(message)
            self.calibration.set_status(message)
            tray = getattr(self, "tray", None)
            if tray is not None:
                tray.set_status(message)

    def _calibration_finished(self):
        self.camera_selector.setEnabled(False)
        self.refresh_camera_button.setEnabled(False)
        self._calibrating = False
        self._has_calibration = True
        self.ask_button.setEnabled(True)
        self.calibration.hide()
        self.start_button.setText(tr("重新校准"))
        self.start_button.setEnabled(True)
        self.measure_button.setEnabled(True)
        self.mode_selector.setEnabled(True)
        self._set_status(tr("校准完成。下方是内部拟合诊断；点击测量精度做独立检查。"))

    def _validation_finished(self, report):
        self._calibrating = False
        self.calibration.hide()
        self.start_button.setEnabled(True)
        self.measure_button.setEnabled(self._has_calibration)
        self.ask_button.setEnabled(self._has_calibration)
        self.mode_selector.setEnabled(True)
        self._append_report(report)
        self._set_status(tr("精度测量完成，详细结果在下方；原校准继续使用。"))

    def _append_report(self, report):
        if self.report_view.toPlainText():
            self.report_view.appendPlainText("\n──────────\n")
        self.report_view.appendPlainText(report)

    def _cancel_calibration(self):
        self.calibration.hide()
        self.marker.hide()
        if self.worker is not None and self._calibrating:
            self.worker.cancel_calibration()

    def _calibration_cancelled(self):
        self._calibrating = False
        self.calibration.hide()
        self.start_button.setText(tr("重新校准"))
        self.start_button.setEnabled(True)
        self.measure_button.setEnabled(self._has_calibration)
        self.ask_button.setEnabled(self._has_calibration)
        self.mode_selector.setEnabled(True)

    def stop_camera(self):
        self.ask.invalidate("camera_stopped")
        self.ask_button.setEnabled(False)
        self.marker.hide()
        self.calibration.hide()
        if self.worker is not None:
            self.worker.stop()
            self.start_button.setEnabled(False)
            self.measure_button.setEnabled(False)
            self.mode_selector.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.status_label.setText(tr("正在释放摄像头…（若正在下载模型，请等待下载结束或超时）"))

    def _worker_finished(self):
        self.camera_selector.setEnabled(True)
        self.refresh_camera_button.setEnabled(True)
        self.ask.invalidate("tracking_stopped")
        self.ask_button.setEnabled(False)
        self.marker.hide()
        self.calibration.hide()
        self._calibrating = False
        self._has_calibration = False
        worker = self.worker
        self.worker = None
        if worker is not None:
            if worker.stopping and not self._closing:
                self.status_label.setText(tr("摄像头已停止并释放。点击开始可重新校准。"))
            worker.deleteLater()
        self.stop_button.setEnabled(False)
        self.start_button.setText(tr("开始校准"))
        self.start_button.setEnabled(True)
        self.measure_button.setEnabled(False)
        self.mode_selector.setEnabled(True)
        self.resolution_selector.setEnabled(True)
        if self._closing:
            self.close()

    def _display_changed(self, *_args):
        self.stop_camera()
        self.start_button.setEnabled(False)
        self._closing = True
        self.status_label.setText(tr("显示器或缩放设置已改变，请退出并重新启动后校准。"))
        if self.worker is None:
            self.close()

    def changeEvent(self, event):
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and not self._closing
            and hasattr(self, "tray")
        ):
            QTimer.singleShot(0, self.tray.minimize)

    def closeEvent(self, event):
        self._closing = True
        self._hotkey_test_pending = False
        self.hotkey_test_timer.stop()
        self.voice.shutdown()
        self.mouse_release.stop()
        self.hotkeys.close()
        self.ask.shutdown()
        if self.worker is not None:
            self._closing = True
            self.stop_camera()
            event.ignore()
            return
        if self.voice.engine.isRunning():
            if not self.tray.background:
                self.show()
            message = tr("麦克风已关闭；等待本地语音任务结束后安全退出…")
            self.status_label.setText(message)
            self.tray.set_status(message)
            event.ignore()
            return
        self.hotkeys.close()
        self.marker.close()
        self.calibration.hide()
        self.tray.shutdown()
        event.accept()
        if self.tray.available:
            QApplication.instance().quit()
