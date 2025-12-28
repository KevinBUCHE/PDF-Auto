"""
Runtime hook pour PyInstaller - Configure les chemins Qt au démarrage
"""
import os
import sys
from pathlib import Path


def _prepend_path(p: Path) -> None:
    """Ajoute un chemin au début de PATH"""
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


def _prepend_env_path(key: str, p: Path) -> None:
    """Ajoute un chemin au début d'une variable d'environnement"""
    if not p:
        return
    try:
        p = p.resolve()
    except Exception:
        p = Path(str(p))
    if not p.exists():
        return

    current = os.environ.get(key, "")
    parts = current.split(os.pathsep) if current else []
    sp = str(p)

    if sp in parts:
        return

    os.environ[key] = sp + (os.pathsep + current if current else "")


# Configuration des chemins Qt au runtime
if getattr(sys, "frozen", False):
    # Application exécutée via PyInstaller
    base = Path(sys.executable).resolve().parent

    # Ajouter les chemins critiques
    _prepend_path(base)
    _prepend_path(base / "_internal")
    _prepend_path(base / "_internal" / "PySide6")

    # Chemins Qt spécifiques
    qt_root = base / "_internal" / "PySide6" / "Qt"
    qt_bin = qt_root / "bin"
    qt_plugins = qt_root / "plugins"

    _prepend_path(qt_bin)
    _prepend_path(qt_plugins)

    # Variable d'environnement Qt
    _prepend_env_path("QT_PLUGIN_PATH", qt_plugins)
