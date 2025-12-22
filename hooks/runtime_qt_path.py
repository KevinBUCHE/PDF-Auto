import os
import sys
from pathlib import Path


def _prepend_path(value: str) -> None:
    current = os.environ.get("PATH", "")
    if not current:
        os.environ["PATH"] = value
        return
    parts = current.split(os.pathsep)
    if value in parts:
        return
    os.environ["PATH"] = value + os.pathsep + current


if getattr(sys, "frozen", False):
    base_dir = Path(sys.executable).resolve().parent
    candidates = [
        base_dir,
        base_dir / "_internal",
        base_dir / "_internal" / "PySide6" / "Qt" / "bin",
        base_dir / "_internal" / "PySide6" / "Qt" / "plugins",
    ]
    for candidate in candidates:
        _prepend_path(str(candidate))
