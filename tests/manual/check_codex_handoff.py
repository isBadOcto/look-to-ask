"""Explicit live desktop submission of synthetic image fixtures, not gaze/audio validation.

Run with --thread <codex link> --send-fixtures. This sends three real image pairs
to that conversation. No screenshot, microphone, clipboard, or image files are used.
"""

import argparse
import ctypes
import json
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from look_to_ask.calibration import ScreenRect
from look_to_ask.codex_handoff import CodexClient, CodexConfig
from look_to_ask.screen_context import build_screen_context


def fixture_snapshot(turn):
    image = QImage(1200, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("#eeeeee"))
    painter = QPainter(image)
    painter.setFont(QFont("Arial", 32))
    for x, color, label in (
        (120, "#a31919", "LEFT A7"),
        (470, "#176e39", "CENTER C8"),
        (820, "#1548b0", "RIGHT B9"),
    ):
        painter.fillRect(x, 180, 260, 400, QColor(color))
        painter.setPen(QColor("white"))
        painter.drawText(x + 10, 360, label)
    painter.end()
    point = ((250, 600, 950)[turn], 380)
    return build_screen_context(image, ScreenRect(0, 0, 1200, 800), point)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread", required=True)
    parser.add_argument("--send-fixtures", required=True, action="store_true")
    parser.add_argument("--count", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    app = QApplication([])
    client = CodexClient()
    config = CodexConfig(args.thread).validate()
    user = ctypes.WinDLL("user32")
    user.GetForegroundWindow.restype = ctypes.c_void_p
    foreground = user.GetForegroundWindow()
    state = {"turn": 0, "started": 0, "exit": 1, "queue_ms": []}

    def send():
        state["started"] = time.monotonic()
        client.send(
            config,
            fixture_snapshot(state["turn"]),
            f"Look to Ask 传输夹具测试 {state['turn'] + 1}："
            "请只回答注视区域对应卡片的英文文字和底色。"
            "这些是生成的测试图，不是真实眼动数据。",
        )

    def submitted(_queue_id):
        state["queue_ms"].append(round((time.monotonic() - state["started"]) * 1000))
        state["turn"] += 1
        if state["turn"] < args.count:
            QTimer.singleShot(500, send)
        else:
            state["exit"] = 0
            print(json.dumps({
                "live_image_pairs_accepted": state["turn"],
                "queue_ms": state["queue_ms"],
                "foreground_unchanged": foreground == user.GetForegroundWindow(),
                "note": "Check actual images and answers in the Codex desktop conversation.",
            }))
            app.quit()

    def failed(_message, code):
        print(json.dumps({"delivery_error": code}))
        app.quit()

    client.completed.connect(submitted)
    client.failed.connect(failed)
    QTimer.singleShot(0, send)
    app.exec()
    return state["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
