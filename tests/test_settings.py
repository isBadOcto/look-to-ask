import json

import pytest

from look_to_ask.settings import AppSettings, SettingsError, SettingsStore, credential_target


class Credentials:
    def __init__(self):
        self.values = {}

    def read(self, target):
        return self.values.get(target, "")

    def write(self, target, secret):
        self.values[target] = secret

    def delete(self, target):
        self.values.pop(target, None)


def test_new_install_prefers_medium_chinese_but_preserves_an_explicit_base_choice(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    assert store.load().speech_model == "medium" and store.load().language == "zh"
    store.path.write_text('{"speech_model":"base","language":"en"}', "utf-8")
    assert store.load().speech_model == "base" and store.load().language == "en"


def test_full_hd_camera_preference_roundtrips_without_credentials(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    settings = AppSettings(camera_resolution=(1920, 1080))
    store.save(settings, "")
    assert store.load() == settings


def test_settings_roundtrip_excludes_keys_and_unknown_private_fields(tmp_path):
    credentials = Credentials()
    store = SettingsStore(tmp_path / "settings.json", credentials=credentials)
    settings = AppSettings(camera_index=2, api_model="vision", remember_key=True)
    store.save(settings, "PRIVATE-KEY")
    text = store.path.read_text("utf-8")
    assert "PRIVATE-KEY" not in text and "api_key" not in text
    assert store.load() == settings and store.load_key(settings) == "PRIVATE-KEY"
    data = json.loads(text)
    data.update(api_key="DO-NOT-LOAD", screenshot="private", calibration=[1, 2])
    store.path.write_text(json.dumps(data), "utf-8")
    assert store.load() == settings
    store.save(AppSettings(api_model="vision"), "")
    assert not credentials.values


def test_corrupt_settings_fall_back_and_credentials_are_bound_to_endpoint(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    store.path.write_text("{broken", "utf-8")
    assert store.load() == AppSettings() and store.warning
    a = AppSettings(api_model="vision", remember_key=True)
    b = AppSettings(api_base_url="https://other.example/v1", api_model="vision", remember_key=True)
    store.save(a, "PRIVATE-KEY")
    assert credential_target(a.api_base_url) != credential_target(b.api_base_url)
    assert store.load_key(b) == ""


@pytest.mark.parametrize(
    "data",
    [
        {"camera_index": -1},
        {"camera_index": True},
        {"camera_resolution": [8, 9]},
        {"language": "bad"},
        {"api_base_url": "https://host/v1?api_key=SECRET"},
        {"remember_key": "false"},
    ],
)
def test_invalid_settings_never_apply_or_load_credentials(tmp_path, data):
    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    store.path.write_text(json.dumps(data), "utf-8")
    assert store.load() == AppSettings() and store.warning


def test_vault_failure_does_not_save_false_success_or_echo_key(tmp_path):
    class Broken(Credentials):
        def write(self, target, secret):
            raise OSError("PRIVATE-KEY")

    store = SettingsStore(tmp_path / "settings.json", credentials=Broken())
    with pytest.raises(SettingsError) as error:
        store.save(AppSettings(api_model="vision", remember_key=True), "PRIVATE-KEY")
    assert "PRIVATE-KEY" not in str(error.value)
    assert not store.path.exists()


def test_equivalent_url_edit_does_not_delete_just_saved_credential(tmp_path):
    from dataclasses import replace

    store = SettingsStore(tmp_path / "settings.json", credentials=Credentials())
    first = AppSettings(api_model="vision", remember_key=True)
    store.save(first, "TEST-ONLY-KEY")
    equivalent = replace(first, api_base_url=first.api_base_url + "/")
    store.save(equivalent, "TEST-ONLY-KEY")
    assert store.load_key(equivalent) == "TEST-ONLY-KEY"
