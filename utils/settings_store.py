import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from utils.paths import get_settings_path


@dataclass
class AppSettings:
    gemini_api_key: str = ""
    use_gemini: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        return cls(
            gemini_api_key=data.get("gemini_api_key", "") or "",
            use_gemini=bool(data.get("use_gemini")),
        )

    def to_dict(self) -> dict:
        return {
            "gemini_api_key": self.gemini_api_key or "",
            "use_gemini": bool(self.use_gemini),
        }


def load_settings(app_name: str) -> AppSettings:
    settings_path = get_settings_path(app_name)
    if settings_path.exists():
        try:
            with settings_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return AppSettings.from_dict(data)
        except Exception:  # pylint: disable=broad-except
            pass
    return AppSettings()


def save_settings(app_name: str, settings: AppSettings) -> Path:
    settings_path = get_settings_path(app_name)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with settings_path.open("w", encoding="utf-8") as handle:
        json.dump(settings.to_dict(), handle, ensure_ascii=False, indent=2)
    return settings_path
