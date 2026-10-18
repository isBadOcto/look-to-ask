import hashlib
import json
import tomllib
from pathlib import Path


def test_runtime_avoids_unused_gpl_virtual_camera_and_duplicate_cv2_packages():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = project["dependencies"]
    assert not any(item.startswith("eyetrax==") for item in dependencies)
    assert not any(item.startswith("pyvirtualcam") for item in dependencies)
    assert not any(item.startswith("opencv-python==") for item in dependencies)
    assert any(item.startswith("opencv-contrib-python==") for item in dependencies)


def test_copied_eyetrax_sources_match_attributed_manifest():
    vendor = Path("src/look_to_ask/_vendor/eyetrax")
    manifest = json.loads((vendor / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["commit"] == "84e13a16af168ac7c383f7d50ec901cd6c0ad61d"
    for item in manifest["files"]:
        assert (
            hashlib.sha256((vendor / item["path"]).read_bytes()).hexdigest() == item["local_sha256"]
        )
    assert "Copyright" in (vendor / "LICENSE").read_text(encoding="utf-8")
