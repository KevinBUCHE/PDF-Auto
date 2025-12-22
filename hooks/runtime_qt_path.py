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
    _prepend_path(str(base_dir))
