"""Missing wheel notices must never be replaced with unreviewed or altered texts."""

import tarfile
import zipfile
from io import BytesIO

import pytest

from scripts import prepare_build


def test_long_upstream_attribution_paths_are_preserved_inside_a_short_zip(tmp_path):
    member_name = "source/" + "deep-directory/" * 30 + "LICENSE.chromium"
    archive = tmp_path / "public-source.tar.gz"
    with tarfile.open(archive, "w:gz") as package:
        member = tarfile.TarInfo(member_name)
        content = b"PUBLIC LICENSE TEST FIXTURE"
        member.size = len(content)
        package.addfile(member, BytesIO(content))
    target = tmp_path / "UPSTREAM-NOTICES.zip"
    with zipfile.ZipFile(target, "w") as destination:
        prepare_build.collect_archive_notices(archive, destination)
    with zipfile.ZipFile(target) as result:
        assert result.read(archive.name + "/" + member_name) == content
    assert not (tmp_path / "source").exists()


@pytest.mark.parametrize(
    "name",
    [
        "qtbase/LICENSES/BSD-3-Clause.txt",
        "qtbase/src/3rdparty/pcre2/LICENCE-SLJIT",
        "qtbase/src/3rdparty/libpsl/src/LICENSE.chromium",
        "qtbase/src/3rdparty/freetype/docs/FTL.TXT",
        "pyside/signature/PSF-3.7.0.txt",
        "qtbase/src/3rdparty/qt_attribution.json",
    ],
)
def test_required_native_notices_are_not_lost_by_filename_filter(name):
    assert prepare_build.is_notice(name)


def test_native_notice_download_rejects_changed_text_before_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        prepare_build.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: BytesIO(b"ALTERED PUBLIC LICENSE TEST FIXTURE"),
    )
    with pytest.raises(RuntimeError, match="license hash mismatch"):
        prepare_build.supplement_native_notices(tmp_path)
    assert not list(tmp_path.rglob("LICENSE.txt"))


def test_dependency_upgrade_requires_license_review_without_download(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_build.metadata, "version", lambda _name: "UNREVIEWED-TEST-VERSION")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unreviewed versions must not reach a download")

    monkeypatch.setattr(prepare_build.urllib.request, "urlopen", forbidden)
    with pytest.raises(RuntimeError, match="Review the upstream license"):
        prepare_build.supplement_native_notices(tmp_path)
    assert not list(tmp_path.rglob("LICENSE.txt"))
