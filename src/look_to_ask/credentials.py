"""Windows Credential Manager adapter; no plaintext credential files or custom crypto."""

import ctypes
import sys
from ctypes import wintypes


class Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class WindowsCredentials:
    def _api(self):
        if sys.platform != "win32":
            raise OSError("Windows Credential Manager is unavailable")
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        api.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(Credential)),
        ]
        api.CredReadW.restype = wintypes.BOOL
        api.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        api.CredFree.restype = None
        return api

    def read(self, target):
        api, pointer = self._api(), ctypes.POINTER(Credential)()
        if not api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:
                return ""
            raise OSError("Cannot read Windows credential")
        try:
            return ctypes.string_at(
                pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize
            ).decode("utf-16-le")
        finally:
            api.CredFree(pointer)

    def write(self, target, secret):
        data = secret.encode("utf-16-le")
        if len(data) > 2560:
            raise OSError("Credential exceeds Windows size limit")
        blob = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        credential = Credential(
            Type=1,
            TargetName=target,
            CredentialBlobSize=len(data),
            CredentialBlob=blob,
            Persist=2,
            UserName="LookToAsk",
        )
        if not self._api().CredWriteW(ctypes.byref(credential), 0):
            raise OSError("Cannot save Windows credential")

    def delete(self, target):
        if not self._api().CredDeleteW(target, 1, 0) and ctypes.get_last_error() != 1168:
            raise OSError("Cannot delete Windows credential")
