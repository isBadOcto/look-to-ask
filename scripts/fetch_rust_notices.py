"""Retain the complete checksum-locked tokenizers crate sources and their notices.

The lock covers a superset, including build and other-platform dependencies. This
does not assert that every crate is linked into the Windows extension.
"""

import hashlib
import json
import tarfile
import tomllib
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "2a0ff80c61f263cca608264a99b43dd487a3194a362d20c31193bc083e16a46b"


def fetch(package, folder):
    name, version = package["name"], package["version"]
    filename = f"{name}-{version}.crate"
    url = f"https://static.crates.io/crates/{name}/{filename}"
    path = folder / filename
    if not path.exists():
        with urllib.request.urlopen(url, timeout=60) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != package["checksum"]:
            raise RuntimeError("Crate download checksum mismatch: " + filename)
        path.write_bytes(content)
    if hashlib.sha256(path.read_bytes()).hexdigest() != package["checksum"]:
        raise RuntimeError("Cached crate checksum mismatch: " + filename)
    with tarfile.open(path) as archive:
        member = next(item for item in archive if item.name == f"{name}-{version}/Cargo.toml")
        cargo = tomllib.loads(archive.extractfile(member).read().decode())["package"]
    return {
        "name": filename,
        "url": url,
        "sha256": package["checksum"],
        "license": cargo.get("license"),
        "license_file": cargo.get("license-file"),
    }


def main():
    source = ROOT / "dist/LicenseSources/tokenizers-v0.23.3.tar.gz"
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA:
        raise RuntimeError("Tokenizers source checksum mismatch")
    with tarfile.open(source) as archive:
        lock = next(item for item in archive if item.name.endswith("bindings/python/Cargo.lock"))
        packages = tomllib.loads(archive.extractfile(lock).read().decode())["package"]
    if any(p.get("source", "").startswith("git+") for p in packages):
        raise RuntimeError("Review new Git crate sources before packaging")
    folder = ROOT / "dist/LicenseSources/TokenizersCrates"
    folder.mkdir(parents=True, exist_ok=True)
    packages = [p for p in packages if p.get("source", "").startswith("registry+")]
    with ThreadPoolExecutor(max_workers=8) as executor:
        records = list(executor.map(lambda package: fetch(package, folder), packages))
    (folder / "SOURCES.json").write_text(json.dumps(records, indent=2) + "\n", "utf-8")
    print("TOKENIZERS_CRATE_SOURCES_OK", len(records))


if __name__ == "__main__":
    main()
