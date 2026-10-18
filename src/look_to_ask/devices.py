"""Friendly camera enumeration via existing native library; never opens video streams."""

import cv2


def list_cameras(*, enumerator=None):
    if enumerator is None:
        from cv2_enumerate_cameras import enumerate_cameras

        enumerator = enumerate_cameras
    return [(camera.index, camera.name) for camera in enumerator(cv2.CAP_DSHOW)]
