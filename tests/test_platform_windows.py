"""Route native-message fixtures without pressing keys or changing real registrations."""

import ctypes
import sys
from ctypes import wintypes

import pytest
from PySide6.QtWidgets import QApplication

from look_to_ask.platform_windows import GlobalHotkeys, HoldReleaseWatcher


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native hotkey message")
def test_ask_hotkey_dispatches_only_ask_and_unregisters_every_identifier(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls, released = [], []
    monkeypatch.setattr(ctypes.windll.user32, "RegisterHotKey", lambda *_args: 1)
    monkeypatch.setattr(
        ctypes.windll.user32,
        "UnregisterHotKey",
        lambda _window, identity: released.append(identity),
    )
    hotkeys = GlobalHotkeys(
        app,
        lambda: calls.append("quit"),
        lambda: calls.append("calibrate"),
        lambda: calls.append("ask"),
    )
    try:
        message = wintypes.MSG()
        message.message, message.wParam = 0x0312, hotkeys.ASK_ID
        assert hotkeys.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(message)) == (
            True,
            0,
        )
        assert calls == ["ask"]
    finally:
        hotkeys.close()
    assert set(released) == {hotkeys.QUIT_ID, hotkeys.RECALIBRATE_ID, hotkeys.ASK_ID}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows push-to-talk key state")
def test_voice_ignores_repeat_and_releases_once_using_high_bit(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    monkeypatch.setattr(ctypes.windll.user32, "RegisterHotKey", lambda *_args: 1)
    monkeypatch.setattr(ctypes.windll.user32, "UnregisterHotKey", lambda *_args: 1)
    monkeypatch.setattr(ctypes.windll.user32, "GetAsyncKeyState", lambda _key: 0x8000)

    def press():
        calls.append("press")
        return True

    hotkeys = GlobalHotkeys(
        app, lambda: None, lambda: None, None, press, lambda: calls.append("release")
    )
    try:
        msg = wintypes.MSG()
        msg.message, msg.wParam = 0x0312, hotkeys.VOICE_ID
        for _ in range(2):
            hotkeys.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))
        hotkeys.release_watcher._poll()
        assert calls == ["press"]
        monkeypatch.setattr(ctypes.windll.user32, "GetAsyncKeyState", lambda _key: 0x0001)
        hotkeys.release_watcher._poll()
        hotkeys.release_watcher._poll()
        assert calls == ["press", "release"]
    finally:
        hotkeys.close()


def test_mouse_hold_release_is_detected_even_when_button_hidden(monkeypatch):
    app = QApplication.instance() or QApplication([])
    watcher = HoldReleaseWatcher(app)
    calls = []
    monkeypatch.setattr(ctypes.windll.user32, "GetAsyncKeyState", lambda _key: 0)
    watcher.watch((0x01,), lambda: calls.append("released"))
    watcher._poll()
    assert calls == ["released"] and not watcher.timer.isActive()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registration errors")
def test_registration_failure_retains_windows_error_and_never_unregisters_failed_key(monkeypatch):
    app = QApplication.instance() or QApplication([])
    unregistered = []
    monkeypatch.setattr(ctypes.windll.user32, "RegisterHotKey", lambda *_args: 0)
    monkeypatch.setattr(ctypes.windll.kernel32, "GetLastError", lambda: 1409)
    monkeypatch.setattr(
        ctypes.windll.user32, "UnregisterHotKey", lambda *args: unregistered.append(args)
    )
    hotkeys = GlobalHotkeys(app, lambda: None, lambda: None, None, lambda: True, lambda: None)
    assert not hotkeys.available and not hotkeys.registered
    assert hotkeys.errors[hotkeys.VOICE_ID] == 1409
    hotkeys.close()
    assert not unregistered


@pytest.mark.skipif(sys.platform != "win32", reason="Windows alternative push-to-talk key")
def test_alternate_voice_hotkey_watches_v_release_and_works_when_space_is_unavailable(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    monkeypatch.setattr(
        ctypes.windll.user32, "RegisterHotKey", lambda _h, _id, _mod, key: key != 0x20
    )
    monkeypatch.setattr(ctypes.windll.user32, "UnregisterHotKey", lambda *_args: 1)
    monkeypatch.setattr(ctypes.windll.kernel32, "GetLastError", lambda: 1409)
    monkeypatch.setattr(
        ctypes.windll.user32, "GetAsyncKeyState", lambda key: 0x8000 if key != 0x20 else 0
    )

    def press():
        calls.append("press")
        return True

    hotkeys = GlobalHotkeys(
        app, lambda: None, lambda: None, None, press, lambda: calls.append("release")
    )
    try:
        assert hotkeys.VOICE_ID not in hotkeys.registered
        assert hotkeys.VOICE_ALT_ID in hotkeys.registered
        msg = wintypes.MSG()
        msg.message, msg.wParam = 0x0312, hotkeys.VOICE_ALT_ID
        hotkeys.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))
        hotkeys.release_watcher._poll()
        assert calls == ["press"]
        assert hotkeys.release_watcher.keys == (0x11, 0x12, ord("V"))
        monkeypatch.setattr(
            ctypes.windll.user32, "GetAsyncKeyState", lambda key: 0 if key == ord("V") else 0x8000
        )
        hotkeys.release_watcher._poll()
        assert calls == ["press", "release"]
    finally:
        hotkeys.close()
