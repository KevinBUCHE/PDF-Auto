import os
from pathlib import Path

from PySide6 import QtCore


def get_user_data_dir(app_name: str) -> Path:
    location = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.AppDataLocation)
    if location:
        base = Path(location)
        if base.name != app_name:
            base = base / app_name
    else:
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / app_name
    return base


def get_user_templates_dir(app_name: str) -> Path:
    return get_user_data_dir(app_name) / "Templates"


def get_template_path(app_name: str) -> Path:
    return get_user_templates_dir(app_name) / "bon de commande V1.pdf"


def get_logs_dir(app_name: str) -> Path:
    return get_user_data_dir(app_name) / "logs"


def get_log_file_path(app_name: str) -> Path:
    return get_logs_dir(app_name) / "bdc_generator.log"


def get_settings_path(app_name: str) -> Path:
    return get_user_data_dir(app_name) / "settings.json"
