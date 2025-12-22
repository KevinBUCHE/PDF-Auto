import os
import sys
from pathlib import Path


def _prepend_path(p: Path) -> None:
    if not p:
        return
    try:
        p = p.resolve()
    except Exception:
        p = Path(str(p))
    if not p.exists():
        return
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    sp = str(p)
    if sp in parts:
        return
    os.environ["PATH"] = sp + (os.pathsep + current if current else "")


if getattr(sys, "frozen", False):
    base = Path(sys.executable).resolve().parent
    _prepend_path(base)
    _prepend_path(base / "_internal")
    _prepend_path(base / "_internal" / "PySide6")
    qt_root = base / "_internal" / "PySide6" / "Qt"
    _prepend_path(qt_root / "bin")
    _prepend_path(qt_root / "plugins")
