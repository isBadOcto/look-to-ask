from PySide6.QtWidgets import QApplication

from look_to_ask.desktop import acquire_instance_lock


def test_second_instance_is_rejected_and_lock_is_released(tmp_path):
    app = QApplication.instance() or QApplication([])
    lock = acquire_instance_lock(tmp_path)
    assert lock is not None
    assert acquire_instance_lock(tmp_path) is None
    lock.unlock()
    later = acquire_instance_lock(tmp_path)
    assert later is not None
    later.unlock()
    app.processEvents()
