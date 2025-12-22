import os
import sys
from pathlib import Path

def _add(p: Path):
    if p and p.exists():
        os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")

if getattr(sys, "frozen", False):
    base = Path(sys.executable).parent

    # racine
    _add(base)

    # PyInstaller onedir met souvent les libs ici
    _add(base / "_internal")
    _add(base / "_internal" / "PySide6")
    _add(base / "_internal" / "PySide6" / "Qt" / "bin")
    _add(base / "_internal" / "PySide6" / "Qt" / "plugins")
