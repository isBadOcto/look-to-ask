"""Read public license documents only; never open settings, credentials or user content."""

import sys
from pathlib import Path


def license_text():
    root = (
        Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    )
    texts = []
    for relative in (
        "THIRD_PARTY_NOTICES.md",
        "docs/RELINKING.md",
        "LICENSES/Intel-Runtime-Terms.txt",
    ):
        path = root / relative
        if path.is_file():
            texts.append(path.read_text("utf-8"))
    return "\n\n".join(texts)
