from __future__ import annotations

import os
from pathlib import Path

from .rules import APP_NAME, TEMPLATE_NAME, TEMPLATE_SUBDIR


class TemplateNotFoundError(FileNotFoundError):
    """Raised when the template PDF cannot be located."""


def _default_appdata_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata)
    # Fallback for non-Windows environments (keeps behavior predictable in tests).
    return Path.home() / "AppData" / "Roaming"


def candidate_template_paths(base_dir: Path) -> list[Path]:
    exe_dir = base_dir
    user_dir = _default_appdata_dir() / APP_NAME
    return [
        exe_dir / TEMPLATE_SUBDIR / TEMPLATE_NAME,
        user_dir / TEMPLATE_SUBDIR / TEMPLATE_NAME,
    ]


def locate_template(base_dir: Path) -> Path:
    for candidate in candidate_template_paths(base_dir):
        if candidate.exists():
            return candidate
    expected = "\n".join(str(path) for path in candidate_template_paths(base_dir))
    raise TemplateNotFoundError(
        f"Template introuvable. Placez '{TEMPLATE_NAME}' dans l'un des chemins suivants:\n{expected}"
    )
