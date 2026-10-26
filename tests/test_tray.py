import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget  # noqa: E402

from look_to_ask import tray as tray_module  # noqa: E402


class TrayIcon(QObject):
    """Replace only the native tray boundary; windows and menu actions stay real."""

    ActivationReason = QSystemTrayIcon.ActivationReason
    activated = Signal(QSystemTrayIcon.ActivationReason)
    available = True
    instances = []

    def __init__(self, icon, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.menu = None
        self.tooltip = ""
        self.visible = False
        self.instances.append(self)

    @staticmethod
    def isSystemTrayAvailable():
        return TrayIcon.available

    def setContextMenu(self, menu):
        self.menu = menu

    def setToolTip(self, message):
        self.tooltip = message

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def showMessage(self, *_args, **_kwargs):
        raise AssertionError("The tray must never display a notification")


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.ask = SimpleNamespace(dialog=QWidget())
        self.marker = QWidget()
        self.actions = []
        self.activations = []

    def start_calibration(self):
        self.actions.append("calibrate")

    def stop_camera(self):
        self.actions.append("stop")

    def close(self):
        self.actions.append("quit")
        return super().close()

    def raise_(self):
        self.activations.append("raise")

    def activateWindow(self):
        self.activations.append("activate")


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    window = Window()
    dialog = window.ask.dialog
    marker = window.marker
    window.show()
    window.ask.dialog.show()
    window.marker.show()
    app.processEvents()
    yield window
    dialog.close()
    marker.close()
    window.close()
    app.processEvents()


def make_tray(monkeypatch, window, *, available=True):
    TrayIcon.available = available
    TrayIcon.instances = []
    monkeypatch.setattr(tray_module, "QSystemTrayIcon", TrayIcon)
    tray = tray_module.DesktopTray(window)
    return tray, TrayIcon.instances[0] if TrayIcon.instances else None


def test_startup_keeps_the_control_window_visible(window, monkeypatch):
    tray, icon = make_tray(monkeypatch, window)

    assert tray.available
    assert not tray.background
    assert window.isVisible()
    assert icon.visible
    assert not icon.icon.isNull()
    tray.shutdown()


def test_minimize_hides_control_preview_and_gaze_marker(window, monkeypatch):
    tray, _icon = make_tray(monkeypatch, window)

    tray.minimize()

    assert tray.background
    assert not window.isVisible()
    assert not window.ask.dialog.isVisible()
    assert not window.marker.isVisible()
    tray.shutdown()


def test_restore_opens_only_the_control_window(window, monkeypatch):
    tray, _icon = make_tray(monkeypatch, window)
    tray.minimize()

    tray.restore()

    assert not tray.background
    assert window.isVisible()
    assert not window.isMinimized()
    assert window.activations == ["raise", "activate"]
    assert not window.ask.dialog.isVisible()
    assert not window.marker.isVisible()
    tray.shutdown()


def test_missing_system_tray_keeps_a_reachable_taskbar_window(window, monkeypatch):
    tray, icon = make_tray(monkeypatch, window, available=False)

    tray.minimize()

    assert not tray.available
    assert tray.background
    assert window.isVisible()
    assert window.isMinimized()
    assert not window.ask.dialog.isVisible()
    assert not window.marker.isVisible()
    assert icon is None or not icon.visible
    tray.restore()
    assert window.isVisible()
    assert not window.isMinimized()
    tray.shutdown()


def test_minimize_supports_windows_without_preview_or_marker(window, monkeypatch):
    window.ask.dialog.close()
    window.marker.close()
    del window.ask
    del window.marker
    tray, _icon = make_tray(monkeypatch, window)

    tray.minimize()

    assert tray.background
    assert not window.isVisible()
    tray.shutdown()


def test_menu_actions_restore_recalibrate_stop_and_quit(window, monkeypatch):
    tray, icon = make_tray(monkeypatch, window)
    actions = [action for action in icon.menu.actions() if not action.isSeparator()]
    assert len(actions) == 4
    tray.minimize()

    actions[0].trigger()

    assert window.isVisible()
    assert not tray.background
    for action in actions[1:]:
        action.trigger()
    assert window.actions == ["calibrate", "stop", "quit"]
    tray.shutdown()


@pytest.mark.parametrize("reason", [
    QSystemTrayIcon.ActivationReason.Trigger,
    QSystemTrayIcon.ActivationReason.DoubleClick,
])
def test_primary_icon_activation_restores_control_window(window, monkeypatch, reason):
    tray, icon = make_tray(monkeypatch, window)
    tray.minimize()

    icon.activated.emit(reason)

    assert window.isVisible()
    assert not tray.background
    tray.shutdown()


def test_context_menu_activation_keeps_app_in_background(window, monkeypatch):
    tray, icon = make_tray(monkeypatch, window)
    tray.minimize()

    icon.activated.emit(QSystemTrayIcon.ActivationReason.Context)

    assert tray.background
    assert not window.isVisible()
    tray.shutdown()


def test_status_updates_only_the_tooltip_and_limits_its_length(window, monkeypatch):
    tray, icon = make_tray(monkeypatch, window)
    tray.minimize()

    tray.set_status("状态" * 100)

    assert icon.tooltip == "状态" * 63 + "状"
    assert tray.background
    assert not window.isVisible()
    tray.shutdown()


def test_shutdown_removes_the_icon_and_closes_its_menu(window, monkeypatch):
    tray, icon = make_tray(monkeypatch, window)
    menu = icon.menu
    menu.show()

    tray.shutdown()
    tray.shutdown()
    tray.set_status("stopped")

    assert not icon.visible
    assert icon.menu is None
    assert not menu.isVisible()
