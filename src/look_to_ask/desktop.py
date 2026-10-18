"""Desktop resources and one process per user, using Qt's existing lock primitive."""

from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtGui import QIcon


def acquire_instance_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(directory / "application.lock"))
    return lock if lock.tryLock(0) else None


def app_icon():
    return QIcon(str(Path(__file__).parent / "assets/logo.svg"))
