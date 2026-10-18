"""Windows global hotkeys and compositor synchronization; no keyboard hooks."""

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer

from look_to_ask.i18n import tr


def flush_compositor():
    if sys.platform == "win32" and ctypes.windll.dwmapi.DwmFlush() != 0:
        raise ValueError(tr("Windows 桌面合成未完成，请稍后重新触发截图。"))


class HoldReleaseWatcher(QObject):
    """Poll only while holding a PTT trigger; high bit is current down state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._poll)
        self.keys = ()
        self.callback = None

    def watch(self, keys, callback):
        self.keys, self.callback = keys, callback
        self.timer.start()

    def _poll(self):
        if sys.platform != "win32" or not all(
            ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000 for key in self.keys
        ):
            callback = self.callback
            self.stop()
            if callback is not None:
                callback()

    def stop(self):
        self.timer.stop()
        self.keys, self.callback = (), None


class GlobalHotkeys(QAbstractNativeEventFilter):
    """RegisterHotKey does not install a keyboard hook or record keystrokes."""

    QUIT_ID = 0x4C41
    RECALIBRATE_ID = 0x4C42
    ASK_ID = 0x4C43
    VOICE_ID = 0x4C44
    VOICE_ALT_ID = 0x4C45

    def __init__(self, app, on_quit, on_recalibrate, on_ask=None, on_voice=None, on_release=None):
        super().__init__()
        self.app = app
        self.release_watcher = HoldReleaseWatcher(app)
        self.last_voice_key = None
        self.callbacks = {self.QUIT_ID: on_quit, self.RECALIBRATE_ID: on_recalibrate}
        keys = [(self.QUIT_ID, ord("Q")), (self.RECALIBRATE_ID, ord("R"))]
        if on_ask is not None:
            self.callbacks[self.ASK_ID] = on_ask
            keys.append((self.ASK_ID, ord("A")))
        if on_voice is not None and on_release is not None:
            for identity, key in ((self.VOICE_ID, 0x20), (self.VOICE_ALT_ID, ord("V"))):

                def begin_voice(key=key):
                    if not self.release_watcher.timer.isActive():
                        self.last_voice_key = key
                        if on_voice():
                            self.release_watcher.watch((0x11, 0x12, key), on_release)

                self.callbacks[identity] = begin_voice
                keys.append((identity, key))
        self.registered = []
        self.errors = {}
        if sys.platform == "win32":
            for identity, key in keys:
                if ctypes.windll.user32.RegisterHotKey(None, identity, 0x4003, key):
                    self.registered.append(identity)
                else:
                    self.errors[identity] = ctypes.windll.kernel32.GetLastError()
            app.installNativeEventFilter(self)

    @property
    def available(self):
        return len(self.registered) == len(self.callbacks)

    def nativeEventFilter(self, event_type, message):
        if sys.platform == "win32" and bytes(event_type) in (
            b"windows_generic_MSG",
            b"windows_dispatcher_MSG",
        ):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in self.callbacks:
                self.callbacks[msg.wParam]()
                return True, 0
        return False, 0

    def close(self):
        self.release_watcher.stop()
        if sys.platform == "win32":
            for identity in self.registered:
                ctypes.windll.user32.UnregisterHotKey(None, identity)
            self.registered.clear()
            self.app.removeNativeEventFilter(self)
