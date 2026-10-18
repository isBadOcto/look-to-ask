"""Render only our widgets using empty test settings; never capture the desktop."""

import argparse
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from look_to_ask.settings import SettingsStore
from look_to_ask.ui import ControlWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--language", choices=("system", "zh", "en"), default="system")
    args = parser.parse_args()
    for prefix in ("OPENAI_", "LOOK_TO_ASK_API_"):
        for key in list(os.environ):
            if key.startswith(prefix):
                os.environ.pop(key)
    args.output.mkdir(parents=True, exist_ok=True)
    settings_path = args.output / "empty-settings.json"
    if settings_path.exists():
        raise RuntimeError("Use a fresh output folder, not personal settings")
    app = QApplication([])
    store = SettingsStore(settings_path)
    store.save_ui_language(args.language)
    window = ControlWindow(settings_store=store)
    window.show()
    app.processEvents()
    window.grab().save(str(args.output / "control.png"))
    window._show_settings()
    app.processEvents()
    window.ask.dialog.grab().save(str(args.output / "settings.png"))
    window._show_licenses()
    app.processEvents()
    window.ask.dialog.grab().save(str(args.output / "licenses.png"))
    window.close()
    app.processEvents()
    print("WIDGET_RENDER_OK (no camera, microphone, desktop or AI)")


if __name__ == "__main__":
    main()
