import json
from pathlib import Path

from utils.paths import get_user_data_dir

DEFAULT_SETTINGS = {
    "gemini_enabled": False,
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
}


class SettingsService:
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.settings_path = get_user_data_dir(app_name) / "settings.json"

    def load(self) -> dict:
        if not self.settings_path.exists():
            return dict(DEFAULT_SETTINGS)
        try:
            with self.settings_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return dict(DEFAULT_SETTINGS)
        merged = dict(DEFAULT_SETTINGS)
        merged.update({key: value for key, value in data.items() if key in DEFAULT_SETTINGS})
        return merged

    def save(self, settings: dict) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        with self.settings_path.open("w", encoding="utf-8") as handle:
            json.dump({**DEFAULT_SETTINGS, **(settings or {})}, handle, indent=2)
