"""Real capture of a full-screen synthetic fixture; no camera, files or AI sends."""

import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from look_to_ask.calibration import ScreenRect
from look_to_ask.screen_context import capture_screen_context


def main():
    app = QApplication([])
    if "--fixture" in sys.argv:

        class Fixture(QWidget):
            def paintEvent(self, _event):
                painter = QPainter(self)
                painter.fillRect(self.rect(), QColor("#129876"))
                painter.fillRect(
                    self.width() // 2, 0, self.width(), self.height(), QColor("#23324a")
                )
                painter.end()

        window = Fixture()
        from PySide6.QtCore import Qt

        window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        window.showFullScreen()
        QTimer.singleShot(500, lambda: print(json.dumps({"hwnd": int(window.winId())}), flush=True))
        QTimer.singleShot(10000, app.quit)
        app.exec()
        return
    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--fixture"],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        metadata = json.loads(child.stdout.readline())
        app.processEvents()
        time.sleep(0.1)
        # Test-only ownership guard: acquire no pixels if the fixture is covered.
        # A visible topmost fixture need not own keyboard focus.
        native = ctypes.WinDLL("user32")
        native.WindowFromPoint.restype = ctypes.c_void_p
        native.WindowFromPoint.argtypes = [wintypes.POINT]
        native.GetAncestor.restype = ctypes.c_void_p
        native.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        rect = app.primaryScreen().geometry()
        dpr = app.primaryScreen().devicePixelRatio()
        width, height = round(rect.width() * dpr), round(rect.height() * dpr)
        for x, y in (
            (1, 1),
            (width - 2, 1),
            (1, height - 2),
            (width - 2, height - 2),
            (width // 2, height // 2),
        ):
            handle = native.WindowFromPoint(wintypes.POINT(x, y))
            if native.GetAncestor(handle, 2) != metadata["hwnd"]:
                raise RuntimeError("Fixture is covered; no screenshot acquired")
        screen = ScreenRect(rect.x(), rect.y(), rect.width(), rect.height())
        point = (screen.x + screen.width / 2, screen.y + screen.height / 2)
        snapshot = capture_screen_context(screen, point)
        image = snapshot.roi
        assert snapshot.geometry.roi_bounds == (0, 0, image.width(), image.height())
        assert image.pixelColor(image.width() // 4, image.height() // 2) == QColor("#129876")
        assert image.pixelColor(3 * image.width() // 4, image.height() // 2) == QColor("#23324a")
        assert snapshot.focus == image.copy(*snapshot.geometry.focus_bounds)
        print(
            json.dumps(
                {
                    "result": "PASS",
                    "overview": snapshot.geometry.image_size,
                    "detail": [snapshot.focus.width(), snapshot.focus.height()],
                    "images_saved": False,
                }
            )
        )
    finally:
        child.terminate()
        child.wait(timeout=5)


if __name__ == "__main__":
    main()
