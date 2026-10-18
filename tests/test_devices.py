from types import SimpleNamespace

import cv2

from look_to_ask.devices import list_cameras


def test_enumeration_preserves_dshow_indices_without_opening_video():
    calls = []

    def enumerate_devices(backend):
        calls.append(backend)
        return [
            SimpleNamespace(index=2, name="USB Camera"),
            SimpleNamespace(index=0, name="Built-in"),
        ]

    assert list_cameras(enumerator=enumerate_devices) == [(2, "USB Camera"), (0, "Built-in")]
    assert calls == [cv2.CAP_DSHOW]
