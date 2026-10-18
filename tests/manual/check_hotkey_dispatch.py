"""Isolated Windows message fixture, NOT a physical keyboard test. No recording/capture."""

import ctypes
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from look_to_ask.ui import ControlWindow


def main():
    if sys.platform != "win32":
        raise SystemExit("Windows only")
    app = QApplication([])
    window = ControlWindow()
    if window.hotkeys.VOICE_ALT_ID not in window.hotkeys.registered:
        window.close()
        raise SystemExit("Ctrl+Alt+V registration unavailable; close other app instances first")
    result = []
    window.show()
    window._test_voice_hotkey()
    thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
    posted = ctypes.windll.user32.PostThreadMessageW(
        thread_id,
        0x0312,
        window.hotkeys.VOICE_ALT_ID,
        (ord("V") << 16) | 3,
    )

    def verify():
        result.append(
            bool(
                posted
                and "已收到 Ctrl+Alt+V" in window.voice_status.text()
                and not window.voice.recorder.active
                and not window.voice.engine.isRunning()
                and not window.ask.pending
                and window.ask.dialog.snapshot is None
            )
        )
        window.close()

    QTimer.singleShot(250, verify)
    app.exec()
    if result != [True]:
        raise SystemExit("NATIVE_DISPATCH_FAILED")
    print("NATIVE_DISPATCH_OK (thread-message fixture; no physical keys, mic, camera or capture)")


if __name__ == "__main__":
    main()
