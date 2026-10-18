"""Source packaging must exclude generated metadata and local private directories."""

import zipfile

from scripts import build_windows


def test_source_only_archive_does_not_collect_generated_or_private_files(tmp_path, monkeypatch):
    public_files = (
        "README.md",
        "AGENTS.md",
        "PLAN.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "pyproject.toml",
        "requirements-lock.txt",
        ".gitignore",
        ".gitattributes",
        "run.cmd",
        "src/look_to_ask/_vendor/eyetrax/LICENSE",
        "src/look_to_ask/app.py",
    )
    private_files = (
        "src/look_to_ask.egg-info/requires.txt",
        "src/example.dist-info/LICENSE",
        "tests/.pytest_cache/README.md",
        "src/look_to_ask/__pycache__/unexpected.py",
        "tests/Screenshots/private.svg",
        "tests/Recordings/private.txt",
        "tests/calibration-data/private.txt",
    )
    for name in public_files + private_files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("PUBLIC OR PRIVATE TEST FIXTURE, NEVER USER DATA", "utf-8")
    monkeypatch.setattr(build_windows, "ROOT", tmp_path)
    monkeypatch.setattr(build_windows.sys, "argv", ["build_windows.py", "--source-only"])
    build_windows.main()
    archive = tmp_path / f"dist/LookToAsk-{build_windows.VERSION}-Source.zip"
    with zipfile.ZipFile(archive) as zipped:
        names = set(zipped.namelist())
        assert "src/look_to_ask/app.py" in names
        assert "src/look_to_ask/_vendor/eyetrax/LICENSE" in names
        assert ".gitattributes" in names
        assert not names.intersection(private_files)
    assert not (tmp_path / "dist/LookToAsk").exists()
