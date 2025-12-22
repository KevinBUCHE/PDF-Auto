from __future__ import annotations

import shutil
from pathlib import Path

import PySide6


def _copy_tree(src: Path, dest: Path) -> int:
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


def main() -> None:
    pyside_root = Path(PySide6.__file__).resolve().parent
    qt_bin = pyside_root / "Qt" / "bin"
    qt_plugins = pyside_root / "Qt" / "plugins"

    qt_core = qt_bin / "Qt6Core.dll"
    if not qt_core.exists():
        raise FileNotFoundError(f"Qt6Core.dll not found in {qt_bin}")

    repo_root = Path(__file__).resolve().parents[1]
    dest_base = (
        repo_root
        / "dist"
        / "BDC Generator"
        / "_internal"
        / "PySide6"
        / "Qt"
    )
    dest_bin = dest_base / "bin"
    dest_plugins = dest_base / "plugins"

    print(f"PySide6 root: {pyside_root}")
    print(f"Copying Qt bin from {qt_bin} -> {dest_bin}")
    bin_count = _copy_tree(qt_bin, dest_bin)
    print(f"Copied {bin_count} files from Qt bin")

    print(f"Copying Qt plugins from {qt_plugins} -> {dest_plugins}")
    plugin_count = _copy_tree(qt_plugins, dest_plugins)
    print(f"Copied {plugin_count} files from Qt plugins")


if __name__ == "__main__":
    main()
