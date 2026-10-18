"""Exercise Windows Credential Manager with a unique inert test entry, then remove it."""

import uuid

from look_to_ask.credentials import WindowsCredentials


def main():
    vault = WindowsCredentials()
    target = "LookToAsk/Test/" + uuid.uuid4().hex
    try:
        assert vault.read(target) == ""
        vault.write(target, "INERT-TEST-ONLY-中文")
        assert vault.read(target) == "INERT-TEST-ONLY-中文"
        vault.write(target, "UPDATED-INERT-TEST")
        assert vault.read(target) == "UPDATED-INERT-TEST"
        vault.delete(target)
        assert vault.read(target) == ""
        print("WINDOWS_CREDENTIAL_CHECK_OK (inert test entry removed)")
    finally:
        vault.delete(target)


if __name__ == "__main__":
    main()
