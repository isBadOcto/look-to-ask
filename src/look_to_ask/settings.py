"""Non-sensitive settings in LocalAppData; secrets only in the optional Windows vault."""

import hashlib
import json
import os
from contextlib import suppress
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from look_to_ask.credentials import WindowsCredentials
from look_to_ask.i18n import UI_LANGUAGES, tr
from look_to_ask.vision import ApiConfig


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class AppSettings:
    camera_index: int = 0
    camera_resolution: tuple[int, int] = (640, 480)
    api_base_url: str = "https://api.openai.com/v1"
    api_model: str = ""
    speech_model: str = "medium"
    language: str = "zh"
    ui_language: str = "system"
    remember_key: bool = False
    destination: str = "api"
    codex_thread: str = ""
    codex_executable: str = ""

    def validate(self):
        if type(self.camera_index) is not int or not 0 <= self.camera_index <= 99:
            raise ValueError("Invalid camera index")
        if tuple(self.camera_resolution) not in ((640, 480), (1280, 720), (1920, 1080)):
            raise ValueError("Invalid camera resolution")
        if (
            self.language not in ("zh", "en", "auto")
            or self.ui_language not in UI_LANGUAGES
            or type(self.remember_key) is not bool
        ):
            raise ValueError("Invalid preferences")
        if not all(
            isinstance(s, str) and len(s) <= 2000
            for s in (
                self.api_base_url,
                self.api_model,
                self.speech_model,
                self.codex_thread,
                self.codex_executable,
            )
        ):
            raise ValueError("Invalid settings text")
        if self.destination not in ("api", "codex"):
            raise ValueError("Invalid destination")
        if self.codex_thread:
            from look_to_ask.codex_handoff import parse_thread_id

            parse_thread_id(self.codex_thread)
        _ = ApiConfig(self.api_base_url, self.api_model or "unconfigured").endpoint


def credential_target(base_url):
    endpoint = ApiConfig(base_url, "unconfigured").endpoint
    return "LookToAsk/API/" + hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


class SettingsStore:
    def __init__(self, path=None, *, credentials=None):
        self.path = (
            Path(path)
            if path
            else Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            / "LookToAsk/settings.json"
        )
        self.credentials = credentials or WindowsCredentials()
        self.warning = ""
        self.saved_fields = frozenset()

    def load(self):
        self.warning = ""
        self.saved_fields = frozenset()
        try:
            if not self.path.exists():
                return AppSettings()
            if self.path.stat().st_size > 16384:
                raise ValueError("Too large")
            data = json.loads(self.path.read_text("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Invalid settings")
            allowed = {f.name for f in fields(AppSettings)}
            safe = {k: v for k, v in data.items() if k in allowed}
            explicit_fields = frozenset(safe)
            safe.setdefault("ui_language", "zh")  # Existing installs used Chinese.
            if "camera_resolution" in safe:
                safe["camera_resolution"] = tuple(safe["camera_resolution"])
            settings = AppSettings(**safe)
            settings.validate()
            self.saved_fields = explicit_fields
            return settings
        except (OSError, ValueError, TypeError):
            self.warning = tr("本机设置无法读取，已使用默认值；保存设置可恢复。")
            return AppSettings()

    def load_key(self, settings):
        if not settings.remember_key:
            return ""
        try:
            return self.credentials.read(credential_target(settings.api_base_url))
        except (OSError, ValueError):
            self.warning = tr("无法读取 Windows 中保存的密钥；请重新填写或使用仅本次会话。")
            return ""

    def save_ui_language(self, language):
        """Save only a non-secret preference, with no credential-vault operations."""
        temporary = self.path.with_suffix(".tmp")
        try:
            settings = replace(self.load(), ui_language=language)
            settings.validate()
            saved = {name: getattr(settings, name) for name in self.saved_fields}
            saved["ui_language"] = language
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2), "utf-8")
            temporary.replace(self.path)
        except (OSError, ValueError, TypeError) as exc:
            raise SettingsError(tr("界面语言未能保存；请检查本机设置目录的权限。")) from exc
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    def save_destination(self, destination, thread, executable):
        """Persist destination preferences without any credential-vault operation."""
        from look_to_ask.codex_handoff import parse_thread_id

        temporary = self.path.with_suffix(".tmp")
        try:
            thread = parse_thread_id(thread) if thread else ""
            settings = replace(
                self.load(),
                destination=destination,
                codex_thread=thread,
                codex_executable=executable,
            )
            settings.validate()
            saved = {name: getattr(settings, name) for name in self.saved_fields}
            saved.update(destination=destination, codex_thread=thread, codex_executable=executable)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2), "utf-8")
            temporary.replace(self.path)
        except (OSError, ValueError, TypeError) as exc:
            raise SettingsError(tr("发送目标未能保存；请检查对话链接和本机设置目录。")) from exc
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    def save(self, settings, api_key):
        temporary = self.path.with_suffix(".tmp")
        try:
            settings.validate()
            _ = ApiConfig(
                settings.api_base_url, settings.api_model or "unconfigured", api_key
            ).endpoint
            previous = self.load()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(asdict(settings), ensure_ascii=False, indent=2), "utf-8"
            )
            target = credential_target(settings.api_base_url)
            if settings.remember_key and api_key:
                self.credentials.write(target, api_key)
            else:
                self.credentials.delete(target)
            if previous.remember_key and credential_target(previous.api_base_url) != target:
                self.credentials.delete(credential_target(previous.api_base_url))
            temporary.replace(self.path)
        except (OSError, ValueError, TypeError) as exc:
            raise SettingsError(
                tr("设置未能保存；检查本机目录权限或 Windows 凭据管理器。密钥不会写入配置文件。")
            ) from exc
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    def save_preferences(self, settings):
        """Save non-secret preferences while preserving the API credential binding."""
        temporary = self.path.with_suffix(".tmp")
        try:
            previous = self.load()
            settings.validate()
            if (settings.api_base_url, settings.remember_key) != (
                previous.api_base_url,
                previous.remember_key,
            ):
                raise ValueError("Credential binding changes require explicit API save")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(asdict(settings), ensure_ascii=False, indent=2), "utf-8"
            )
            temporary.replace(self.path)
        except (OSError, ValueError, TypeError) as exc:
            raise SettingsError(tr("发送目标未能保存；请检查对话链接和本机设置目录。")) from exc
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
