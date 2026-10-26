"""Explicit desktop background lifecycle, without native notifications."""

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from look_to_ask.desktop import app_icon
from look_to_ask.i18n import tr


class DesktopTray(QObject):
    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self.background = False
        self._closed = False
        self._icon = None
        self._menu = None
        if not self.available:
            return

        self._menu = QMenu(window)
        for label, callback in (
            (tr("打开控制面板"), self.restore),
            (tr("重新校准"), window.start_calibration),
            (tr("停止摄像头"), window.stop_camera),
            (tr("退出"), window.close),
        ):
            self._menu.addAction(label).triggered.connect(callback)
        self._icon = QSystemTrayIcon(app_icon(), self)
        self._icon.setContextMenu(self._menu)
        self._icon.setToolTip("Look to Ask")
        self._icon.activated.connect(self._activate)
        self._icon.show()

    def minimize(self):
        if self._closed or self.background:
            return
        self.background = True
        ask = getattr(self._window, "ask", None)
        for widget in (getattr(ask, "dialog", None), getattr(self._window, "marker", None)):
            if widget is not None:
                widget.hide()
        if self.available:
            self._window.hide()
        else:
            self._window.showMinimized()

    def restore(self):
        if self._closed:
            return
        self.background = False
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    def _activate(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.restore()

    def set_status(self, message: str):
        if self._icon is not None:
            self._icon.setToolTip(message[:127])

    def shutdown(self):
        self._closed = True
        if self._icon is not None:
            self._icon.hide()
            self._icon.setContextMenu(None)
            self._icon.deleteLater()
            self._icon = None
        if self._menu is not None:
            self._menu.close()
            self._menu.deleteLater()
            self._menu = None
