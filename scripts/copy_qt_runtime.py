"""
Script pour copier les DLLs Qt de PySide6 dans le build PyInstaller
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import PySide6


def _copy_tree(src: Path, dest: Path) -> int:
    """Copie récursivement un dossier"""
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        target = dest / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        count += 1
    return count


def _parse_args() -> argparse.Namespace:
    """Parse les arguments de ligne de commande"""
    parser = argparse.ArgumentParser(
        description="Copy PySide6 Qt runtime files into a PyInstaller dist."
    )
    parser.add_argument(
        "dist_root",
        nargs="?",
        default=None,
        help='Path to the PyInstaller dist root (e.g. "dist/BDC Generator").',
    )
    return parser.parse_args()


def main() -> None:
    """Fonction principale"""
    args = _parse_args()

    # Trouver PySide6
    pyside_root = Path(PySide6.__file__).resolve().parent
    qt_bin = pyside_root / "Qt" / "bin"
    qt_plugins = pyside_root / "Qt" / "plugins"

    # Vérifier que Qt existe
    qt_core = qt_bin / "Qt6Core.dll"
    if not qt_core.exists():
        raise FileNotFoundError(f"Qt6Core.dll not found in {qt_bin}")

    # Déterminer le dossier de destination
    if args.dist_root:
        dist_root = Path(args.dist_root)
    else:
        dist_root = Path(__file__).resolve().parents[1] / "dist" / "BDC Generator"

    dest_base = dist_root / "_internal" / "PySide6" / "Qt"
    dest_bin = dest_base / "bin"
    dest_plugins = dest_base / "plugins"

    # Copier les fichiers
    print(f"PySide6 root: {pyside_root}")
    print(f"Copying Qt bin from {qt_bin} -> {dest_bin}")
    bin_count = _copy_tree(qt_bin, dest_bin)
    print(f"Copied {bin_count} files from Qt bin")

    print(f"Copying Qt plugins from {qt_plugins} -> {dest_plugins}")
    plugin_count = _copy_tree(qt_plugins, dest_plugins)
    print(f"Copied {plugin_count} files from Qt plugins")

    print(f"\nTotal: {bin_count + plugin_count} files copied")


if __name__ == "__main__":
    main()
