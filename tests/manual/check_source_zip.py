"""Check actual source artifact attribution, then run its vendored-source integrity tests."""

import subprocess
import sys
import zipfile
from pathlib import Path

from look_to_ask import __version__

ROOT = Path(__file__).resolve().parents[2]


def main():
    output = ROOT / f".venv/source-check-{__version__}"
    if output.exists() or not output.resolve().is_relative_to(ROOT.resolve()):
        raise RuntimeError("Use a fresh source-check folder inside the workspace")
    with zipfile.ZipFile(ROOT / f"dist/LookToAsk-{__version__}-Source.zip") as archive:
        for name in archive.namelist():
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                raise RuntimeError("Unsafe source ZIP member")
            if path.name.lower() in ("settings.json", ".env") or path.suffix.lower() in (
                ".wav",
                ".png",
                ".jpg",
                ".pkl",
                ".task",
                ".exe",
                ".dll",
            ):
                raise RuntimeError("Unexpected data/binary in source ZIP")
        assert archive.read("src/look_to_ask/_vendor/eyetrax/LICENSE")
        assert archive.read("src/look_to_ask/translations/en.ts")
        assert archive.read("src/look_to_ask/translations/en.qm")
        archive.extractall(output)
    subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_dependencies.py", "tests/test_i18n.py", "-q"],
        cwd=output,
        check=True,
    )
    print("SOURCE_ZIP_CHECK_OK (attributions and vendored hashes from extracted artifact)")


if __name__ == "__main__":
    main()
